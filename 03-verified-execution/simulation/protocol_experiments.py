"""Frozen reproducible conformance, attacks, and disclosure/cost measurements.

Run: python -m research.verified_execution.protocol_experiments --output-dir PATH
This executes a restricted grammar, not the production runner or a real TEE.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from . import protocol as p

CONFIG = {
    'version': 1,
    'protocol_profile': p.PROFILE,
    'randomness': 'none; exhaustive deterministic vectors; wall-clock microbenchmark repeats',
    'tree_counts': list(range(1,65)),
    'semantic_counts': [4,16,64],
    'source_values': [-7,7],
    'benchmark_counts': [4,16,64],
    'hash_batches': 7,
    'hash_iterations_per_batch': 1000,
    'parse_batches': 7,
    'parse_iterations_per_batch': 100,
    'local_batches': 7,
    'local_iterations_per_batch': 100,
    'benchmark_warmup_iterations': 20,
    'reference_truth_for_source_attack': False,
    'clock_units': 'abstract ordered ledger rounds, not measured network time',
    'reveal_deadline': 10,
    'challenge_window': 10,
    'command': 'python -m research.verified_execution.protocol_experiments --output-dir 03-verified-execution/output/protocol',
    'measurement_scope': 'local Python reference implementations; no network, hardware attestation, contract, or fee measurement',
}


def write(path,value):
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


def accepts(fn,*args,**kwargs):
    try:return bool(fn(*args,**kwargs))
    except p.ProtocolError:return False


def conformance_vectors():
    raw_good=[b'null',b'true',b'false',b'0',b'-9007199254740991',b'9007199254740991',b'{"a":[1,false,null],"b":"line\\n\\t\\u0001"}',b'"ascii/quote\\\"slash\\\\"']
    raw_bad=[b'{"x":1,"x":2}',b'{"x":1, "y":2}',b'{"b":1,"a":2}',b'1.0',b'1e0',b'-0',b'9007199254740992',b'NaN',b'Infinity',b'"\\u0061"','"é"'.encode(),b'[true,]',b'null\n']
    raw_good.append(p.canonical(''.join(chr(i) for i in range(128))))
    raw_bad.append(bytes([34,127,34]))  # DEL has one specified escaped encoding.
    canonical=[{'id':f'canonical-valid-{i}', 'raw_hex':raw.hex(), 'expected':True} for i,raw in enumerate(raw_good)]
    canonical += [{'id':f'canonical-invalid-{i}', 'raw_hex':raw.hex(), 'expected':False} for i,raw in enumerate(raw_bad)]
    trees,proofs=[],[]
    c='ab'*32
    for n in CONFIG['tree_counts']:
        payloads=[p.canonical({'index':i,'data':'x'*(16+(i%7))}) for i in range(n)]
        root=p.merkle_root(c,payloads)
        trees.append({'id':f'tree-{n}','context':c,'payloads_hex':[v.hex() for v in payloads],'root':root})
        for i,raw in enumerate(payloads):
            v={'id':f'valid-{n}-{i}','context':c,'count':n,'index':i,'payload_hex':raw.hex(),'proof':p.inclusion_proof(c,payloads,i),'root':root,'expected':True}
            proofs.append(v)
        base=proofs[-1]
        changes={'wrong-payload':{'payload_hex':(payloads[-1]+b' ').hex()},'wrong-context':{'context':'cd'*32},'wrong-root':{'root':'00'*32},'out-of-range':{'index':n},'negative-index':{'index':-1},'Boolean-index':{'index':True},'extra-sibling':{'proof':base['proof']+['00'*32]},'wrong-count':{'count':n-1 if n==64 else n+1}}
        if n>1:changes['missing-sibling']={'proof':base['proof'][:-1]}
        for name,changed in changes.items():
            v=copy.deepcopy(base);v.update(changed);v.update(id=f'{name}-{n}',expected=False);proofs.append(v)
    # Root selected by the attacker must not authorize noncanonical padding.
    c,n,i='12'*32,5,4;payload=b'{"v":1}';proof=['00'*32]*3
    h=p.leaf_hash(c,n,i,payload);cursor=i
    for sibling in proof:
        h=p._parent(h,bytes.fromhex(sibling)) if cursor%2==0 else p._parent(bytes.fromhex(sibling),h);cursor//=2
    proofs.append({'id':'attacker-root-invalid-padding','context':c,'count':n,'index':i,'payload_hex':payload.hex(),'proof':proof,'root':p._wrap(c,n,h),'expected':False})
    return {'canonical':canonical,'trees':trees,'proofs':proofs}


def run_python_vectors(vectors):
    canonical=[]
    for v in vectors['canonical']:
        try:value=p.parse_canonical(bytes.fromhex(v['raw_hex']));accepted=True;raw=p.canonical(value).hex()
        except p.ProtocolError:accepted=False;raw=None
        canonical.append({'id':v['id'],'accepted':accepted,'canonical_hex':raw})
    return {'implementation':'Python reference v1','python_version':platform.python_version(), 'canonical':canonical,
      'trees':[{'id':v['id'],'root':p.merkle_root(v['context'],[bytes.fromhex(x) for x in v['payloads_hex']])} for v in vectors['trees']],
      'proofs':[{'id':v['id'],'accepted':p.verify_inclusion(v['context'],v['count'],v['index'],bytes.fromhex(v['payload_hex']),v['proof'],v['root'])} for v in vectors['proofs']]}


def check_cross_language(vectors, py, node):
    for field in ('canonical','trees','proofs'):
        if py[field]!=node[field]:raise AssertionError(f'cross-language mismatch: {field}')
    for field in ('canonical','proofs'):
        expected={v['id']:v['expected'] for v in vectors[field]}
        for actual in py[field]:
            if actual['accepted']!=expected[actual['id']]:raise AssertionError(f"wrong conformance result: {actual['id']}")
    for expected,actual in zip(vectors['trees'],py['trees']):
        assert expected['root']==actual['root']


def semantic_vectors():
    out=[]
    for n in CONFIG['semantic_counts']:
        for value in CONFIG['source_values']:
            x=p.make_example(n,value)
            out.append({'id':f'valid-{n}-{value}','expected':True,'accepted':accepts(p.verify_trace,x['blueprint'],x['request'],x['trace']),'example':x})
    x=p.make_example(16)
    changes={
      'duplicate-slot-same-count':lambda t:t['records'].__setitem__(2,copy.deepcopy(t['records'][1])),
      'unrelated-slot-same-count':lambda t:t['records'][2].__setitem__('node_id','unrelated'),
      'reordered-slots-same-count':lambda t:t['records'].__setitem__(slice(1,3),list(reversed(t['records'][1:3]))),
      'wrong-parent-input':lambda t:t['records'][2].__setitem__('input',999),
      'wrong-arithmetic-output':lambda t:t['records'][2].__setitem__('output',999),
      'wrong-branch-edge':lambda t:t['records'][13].__setitem__('edge_taken','n015'),
      'two-active-terminals':lambda t:t['records'][15].__setitem__('status','ok'),
      'skipped-terminal-has-output':lambda t:t['records'][15].__setitem__('output',False),
      'Boolean-as-number':lambda t:t['records'][13].__setitem__('output',1),
      'wrong-terminal-result':lambda t:t['result'].__setitem__('outcome',False),
      'wrong-result-projection':lambda t:t['result'].__setitem__('semantic_projection_digest','00'*32),
      'cross-request-replay':lambda t:t['context'].__setitem__('request_digest','00'*32),
      'cross-snapshot-replay':lambda t:t['context'].__setitem__('snapshot_digest','00'*32),
      'source-preimage-omitted':lambda t:t['records'][0]['input'].__setitem__('reports',[]),
      'unknown-record-field':lambda t:t['records'][1].__setitem__('uncommitted-assumption',True),
    }
    for name,mutate in changes.items():
        t=copy.deepcopy(x['trace']);mutate(t)
        root=p.trace_commitment(t)
        # Fresh valid commitments are essential: these are semantic defects,
        # not merely stale-hash tamper cases.
        c=p.context_digest(t['context']);ps=[p.canonical(r) for r in t['records']]
        memberships=all(p.verify_inclusion(c,len(ps),i,raw,p.inclusion_proof(c,ps,i),root) for i,raw in enumerate(ps))
        out.append({'id':name,'expected':False,'accepted':accepts(p.verify_trace,x['blueprint'],x['request'],t),'leaf_count_unchanged':len(ps)==16,'all_merkle_memberships_valid':memberships,'fresh_root':root,'example':{'blueprint':x['blueprint'],'request':x['request'],'trace':t}})
    for row in out:assert row['expected']==row['accepted']
    return out


def source_vectors():
    keys=p.test_keys();truth=False;rows=[]
    for n in (1,3):
        for mode in ('authentic-truth','unauthenticated-host-forgery','authenticated-host-forgery','authentic-common-source-error'):
            reports=[];auth=[]
            for authority,key in list(sorted(keys.items()))[:n]:
                body={'authority':authority,'request_id':'source-attack-001','value':truth}
                if mode=='authentic-common-source-error':body['value']=not truth
                report=p.sign_test_source(body,key)
                if 'host-forgery' in mode:report['body']['value']=not truth
                reports.append(report)
                auth.append(p.authentic_source(report,p.public_key(key)))
            check_auth=mode!='unauthenticated-host-forgery'
            accepted=all(auth) if check_auth else True
            outcome=sum(r['body']['value'] for r in reports)>n//2
            rows.append({'id':f'{n}-sources-{mode}','source_count':n,'mode':mode,'source_authentication_required':check_auth,'signature_validity':auth,'accepted':accepted,'majority_value':outcome,'stipulated_truth':truth,'accepted_wrong':accepted and outcome!=truth,'reports':reports})
    return rows


def availability_vectors():
    x=p.make_example(4);rows=[]
    for mode in ('no-reveal','one-leaf-withheld','late-final-leaf','complete-at-9','honest-challenge','false-challenge','invalid-challenger-proof','semantic-fraud-challenged','semantic-fraud-unmonitored','missing-source-preimage-blocked'):
        t=copy.deepcopy(x['trace'])
        if mode.startswith('semantic-fraud'):t['result']['outcome']=False
        if mode=='missing-source-preimage-blocked':t['records'][0]['input']={'version':1,'reports':[]}
        ps=[p.canonical(r) for r in t['records']];c=p.context_digest(t['context'])
        s=p.RevealSession(x['blueprint'],x['request'],t['context'],p.merkle_root(c,ps),t['result'])
        events=[]
        n=0 if mode=='no-reveal' else 3 if mode in ('one-leaf-withheld','late-final-leaf') else 4
        for i in range(n):
            now=9 if mode=='complete-at-9' else 3
            try:
                events.append({'event':'reveal','index':i,'time':now,'status':s.reveal(i,ps[i],p.inclusion_proof(c,ps,i),now)})
            except p.ProtocolError:
                if mode!='missing-source-preimage-blocked':raise
                events.append({'event':'source-preimage-reveal-rejected','index':i,'time':now,'status':s.status})
        if mode=='late-final-leaf':
            try:s.reveal(3,ps[3],p.inclusion_proof(c,ps,3),10)
            except p.ProtocolError:events.append({'event':'late-reveal-rejected','time':10,'status':s.status})
        if mode in ('honest-challenge','false-challenge','semantic-fraud-challenged'):
            won=s.challenge(x['blueprint'],x['request'],4)
            events.append({'event':'semantic-challenge','time':4,'successful':won,'status':s.status})
        if mode=='invalid-challenger-proof':
            won=s.challenge_inclusion(0,ps[0],[],4)
            events.append({'event':'invalid-membership-challenge','time':4,'successful':won,'status':s.status})
        for now in (10,13,19):
            events.append({'event':'finalize','time':now,'status':s.finalize(now)})
        rows.append({'id':mode,'revealed_leaves':len(s.records),'challenge_deadline':s.challenge_deadline,'final_status':s.status,'events':events,'reference_semantics_valid':accepts(p.verify_trace,x['blueprint'],x['request'],t)})
    return rows


def benchmark(fn,batches,iterations):
    for _ in range(CONFIG['benchmark_warmup_iterations']):fn()
    rows=[]
    for batch in range(batches):
        start=time.perf_counter_ns()
        for _ in range(iterations):fn()
        elapsed=time.perf_counter_ns()-start
        rows.append({'batch':batch,'iterations':iterations,'elapsed_ns':elapsed,'ns_per_operation':elapsed/iterations})
    return {'median_ns':statistics.median(v['ns_per_operation'] for v in rows),'minimum_ns':min(v['ns_per_operation'] for v in rows),'maximum_ns':max(v['ns_per_operation'] for v in rows),'raw_batches':rows}


def benchmarks():
    rows=[]
    for n in CONFIG['benchmark_counts']:
        x=p.make_example(n);t=x['trace'];ps=[p.canonical(r) for r in t['records']];c=p.context_digest(t['context']);root=x['trace_root'];raw=p.canonical(t)
        # Interior deterministic step: parent 0 for n=4, otherwise middle add.
        index=1 if n==4 else n//2
        parent=x['blueprint']['nodes'][index]['parent']
        proof=p.inclusion_proof(c,ps,index);parent_proof=p.inclusion_proof(c,ps,parent)
        whole_expected=hashlib.sha256(b'QM_EXEC_WHOLE_TRACE_V1\0'+raw).hexdigest()
        whole=lambda:hashlib.sha256(b'QM_EXEC_WHOLE_TRACE_V1\0'+raw).hexdigest()==whole_expected
        selective=lambda:p.verify_inclusion(c,n,index,ps[index],proof,root)
        whole_parse=lambda:p.parse_canonical(raw)
        selective_parse=lambda:p.parse_canonical(ps[index])
        full_semantics=lambda:p.verify_trace(x['blueprint'],x['request'],t)
        local=lambda:p.verify_local_fault(x['blueprint'],x['request'],t['context'],root,index,ps[index],proof,ps[parent],parent_proof)
        row={'count':n,'selected_index':index,'parent_index':parent,'full_trace_bytes':len(raw),'complete_leaf_reveal_bytes':sum(map(len,ps)),
             'source_leaf_bytes':len(ps[0]),'selective_leaf_bytes':len(ps[index]),'sibling_hash_bytes':32*len(proof),
             'selective_one_leaf_wire_bytes':len(ps[index])+32*len(proof)+8,
             'selective_two_leaf_wire_bytes':len(ps[index])+len(ps[parent])+32*(len(proof)+len(parent_proof))+16,
             'baseline_whole_trace_digest':whole_expected,'trace_merkle_root':root,
             'byte_accounting':'stored request/context/root/count and ordinary transaction framing excluded from both; selective proof adds u64 index; two independent paths not multiproof',
             'timing':{}}
        for label,fn,group in [('whole_trace_hash',whole,'hash'),('merkle_one_leaf_inclusion',selective,'hash'),('whole_trace_canonical_parse',whole_parse,'parse'),('selective_leaf_canonical_parse',selective_parse,'parse'),('full_semantic_replay_including_RSA',full_semantics,'local'),('two_leaf_local_check',local,'local')]:
            row['timing'][label]=benchmark(fn,CONFIG[group+'_batches'],CONFIG[group+'_iterations_per_batch'])
        row['one_leaf_disclosure_reduction']=1-row['selective_one_leaf_wire_bytes']/len(raw)
        row['two_leaf_disclosure_reduction']=1-row['selective_two_leaf_wire_bytes']/len(raw)
        rows.append(row)
    return rows


def run_all(output_dir):
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    write(output_dir/'config.json',CONFIG) # freeze before generating/evaluating vectors
    own=Path(__file__).parent
    sources=[own/'protocol.py',own/'protocol_experiments.py',own/'independent_verifier.mjs',own/'fixtures'/'TEST_ONLY_RSA_KEYS.json']
    source_hashes={str(path.relative_to(own)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    write(output_dir/'source_hashes.json',source_hashes)
    vectors=conformance_vectors();write(output_dir/'conformance_vectors.json',vectors)
    python=run_python_vectors(vectors);write(output_dir/'python_verifier_results.json',python)
    node_binary=shutil.which('node')
    if not node_binary:raise RuntimeError('Node.js is required for the independent verifier experiment')
    result=subprocess.run([node_binary,str(own/'independent_verifier.mjs'),str(output_dir/'conformance_vectors.json')],check=True,capture_output=True,text=True)
    node=json.loads(result.stdout);write(output_dir/'node_verifier_results.json',node)
    check_cross_language(vectors,python,node)
    semantic=semantic_vectors();write(output_dir/'semantic_vectors.json',semantic)
    source=source_vectors();write(output_dir/'source_authentication_vectors.json',source)
    availability=availability_vectors();write(output_dir/'availability_vectors.json',availability)
    performance=benchmarks();write(output_dir/'disclosure_benchmarks.json',performance)
    a=p.make_example(16);b=p.run(a['blueprint'],a['request'],a['snapshot'],'run-b','runner-b','12'*32)
    agreement={'request':a['request'],'request_digest':p.request_digest(a['request']),'traces':[a['trace'],b],'result_digests':[a['result_digest'],p.result_digest(b['result'])],'trace_roots':[a['trace_root'],p.trace_commitment(b)],'same_result':a['result_digest']==p.result_digest(b['result']),'different_traces':a['trace_root']!=p.trace_commitment(b)}
    write(output_dir/'shared_result_example.json',agreement)
    assert agreement['same_result'] and agreement['different_traces']
    summary={'config':CONFIG,'environment':{'python':sys.version,'node':node['node_version'],'platform':platform.platform(),'machine':platform.machine()},
      'conformance':{'canonical_vectors':len(vectors['canonical']),'trees':len(vectors['trees']),'proof_vectors':len(vectors['proofs']),'valid_proofs':sum(v['expected'] for v in vectors['proofs']),'invalid_proofs':sum(not v['expected'] for v in vectors['proofs']),'cross_language_mismatches':0},
      'semantics':{'vectors':len(semantic),'accepted_controls':sum(v['expected'] for v in semantic),'rejected_attacks':sum(not v['expected'] for v in semantic),'count_preserving_new_root_attacks':sum(v.get('leaf_count_unchanged',False) for v in semantic)},
      'availability':{'vectors':len(availability),'complete_reveal_required_for_finalization':all(row['revealed_leaves']==4 for row in availability if row['final_status']=='finalized'),'missing_source_preimage_blocks_finalization':next(v for v in availability if v['id']=='missing-source-preimage-blocked')['final_status']=='unavailable','unchallenged_wrong_result_can_finalize':next(v for v in availability if v['id']=='semantic-fraud-unmonitored')['final_status']=='finalized'},
      'source_authentication':{'vectors':len(source),'host_forges_all_unauthenticated_sources':all(v['accepted_wrong'] for v in source if v['mode']=='unauthenticated-host-forgery'),'authenticated_host_forgeries_blocked':all(not v['accepted'] for v in source if v['mode']=='authenticated-host-forgery'),'authentic_common_error_remains':all(v['accepted_wrong'] for v in source if v['mode']=='authentic-common-source-error')},
      'performance':[{k:v for k,v in row.items() if k!='timing'} for row in performance],
      'source_hashes':source_hashes}
    write(output_dir/'summary.json',summary)
    # Detect accidental code mutation during a run; this is a frozen code/config experiment.
    assert source_hashes=={str(path.relative_to(own)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    files={str(path.relative_to(output_dir)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(output_dir.iterdir()) if path.is_file() and path.name!='manifest.json'}
    write(output_dir/'manifest.json',{'sha256':files,'source_sha256':source_hashes})
    return summary


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',required=True);args=parser.parse_args()
    summary=run_all(args.output_dir)
    print(json.dumps({k:summary[k] for k in ('conformance','semantics','availability','source_authentication')},indent=2))


if __name__=='__main__':main()
