import copy
import unittest
from research.verified_execution import protocol as p


class CanonicalTests(unittest.TestCase):
    def test_exact_typed_canonical_domain(self):
        self.assertNotEqual(p.canonical(False), p.canonical(0))
        self.assertEqual(p.canonical(chr(127)), b'"\\u007f"')
        with self.assertRaises(p.ProtocolError):p.parse_canonical(bytes([34,127,34]))
        self.assertEqual(p.canonical({"z": 2, "a": "\n\t"}), b'{"a":"\\n\\t","z":2}')
        self.assertNotEqual(p.object_digest("A", {"x": 1}), p.object_digest("B", {"x": 1}))
        for raw in (b'{"x":1,"x":2}', b'{ "x":1}', b'{"x":1.0}', b'{"x":-0}', b'"\\u0061"', b'9007199254740992', b'NaN', '"é"'.encode()):
            with self.subTest(raw=raw), self.assertRaises(p.ProtocolError):
                p.parse_canonical(raw)
        for value in (1.5, 2**53, "é", {1:"x"}):
            with self.assertRaises(p.ProtocolError):
                p.canonical(value)


class MerkleTests(unittest.TestCase):
    def test_all_counts_and_positions(self):
        context = "ab"*32
        for n in range(1,65):
            leaves = [p.canonical({"index": i, "text": "test"}) for i in range(n)]
            root = p.merkle_root(context, leaves)
            for i, leaf in enumerate(leaves):
                proof = p.inclusion_proof(context, leaves, i)
                self.assertTrue(p.verify_inclusion(context,n,i,leaf,proof,root))
                self.assertFalse(p.verify_inclusion(context,n,i,leaf+b" ",proof,root))
                self.assertFalse(p.verify_inclusion("cd"*32,n,i,leaf,proof,root))
                self.assertFalse(p.verify_inclusion(context,n,i,leaf,proof+["00"*32],root))
                self.assertFalse(p.verify_inclusion(context,n,n,leaf,proof,root))
                self.assertFalse(p.verify_inclusion(context,n,True,leaf,proof,root))
                if n>1:
                    self.assertFalse(p.verify_inclusion(context,n,(i+1)%n,leaf,proof,root))
                if n<64:
                    self.assertFalse(p.verify_inclusion(context,n+1,i,leaf,proof,root))

    def test_padding_is_constrained_even_under_attacker_chosen_root(self):
        c,n,i = "12"*32,5,4
        payload = b'{"v":1}'
        # A root recomputed from malformed padded siblings must still reject.
        proof=["00"*32]*3
        h=p.leaf_hash(c,n,i,payload)
        cursor=i
        for sibling in proof:
            h=p._parent(h,bytes.fromhex(sibling)) if cursor%2==0 else p._parent(bytes.fromhex(sibling),h)
            cursor//=2
        root=p._wrap(c,n,h)
        self.assertFalse(p.verify_inclusion(c,n,i,payload,proof,root))

    def test_bounds(self):
        for count in (0,65,True,-1):
            self.assertFalse(p.verify_inclusion("ab"*32,count,0,b"x",[],"00"*32))
        self.assertFalse(p.verify_inclusion("ab"*32,1,0,b"x"*4097,[],"00"*32))


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.x=p.make_example(16)

    def test_valid_branches_and_shared_result_different_trace(self):
        for n in (4,16,64):
            for value in (-7,7):
                x=p.make_example(n,value)
                self.assertTrue(p.verify_trace(x['blueprint'],x['request'],x['trace']))
        other=p.run(self.x['blueprint'],self.x['request'],self.x['snapshot'],'run-b','runner-b','12'*32)
        self.assertEqual(p.result_digest(other['result']),self.x['result_digest'])
        self.assertNotEqual(p.trace_commitment(other),self.x['trace_root'])

    def test_count_preserving_omissions_and_semantic_faults(self):
        mutations={
            'duplicate': lambda t:t['records'].__setitem__(2,copy.deepcopy(t['records'][1])),
            'wrong_id': lambda t:t['records'][2].__setitem__('node_id','unrelated'),
            'wrong_parent':lambda t:t['records'][2].__setitem__('input',999),
            'wrong_output':lambda t:t['records'][2].__setitem__('output',999),
            'wrong_edge':lambda t:t['records'][13].__setitem__('edge_taken','n015'),
            'both_terminals':lambda t:t['records'][15].__setitem__('status','ok'),
            'skipped_output':lambda t:t['records'][15].__setitem__('output',False),
            'integer_boolean':lambda t:t['records'][13].__setitem__('output',1),
            'wrong_terminal_result':lambda t:t['result'].__setitem__('outcome',False),
            'wrong_projection':lambda t:t['result'].__setitem__('semantic_projection_digest','00'*32),
            'wrong_market':lambda t:t['context'].__setitem__('request_digest','00'*32),
            'unknown_field':lambda t:t['records'][1].__setitem__('hidden',1),
        }
        for name,mutate in mutations.items():
            t=copy.deepcopy(self.x['trace']);mutate(t)
            self.assertEqual(len(t['records']),16)
            with self.subTest(name=name), self.assertRaises(p.ProtocolError):
                p.verify_trace(self.x['blueprint'],self.x['request'],t)

    def test_bound_committee_policy_retains_exact_semantics(self):
        policy={**p.AGREEMENT_POLICY,'quorum_policy_digest':'ab'*32,'attempt_policy_digest':'cd'*32}
        req=copy.deepcopy(self.x['request']);req['agreement_policy_digest']=p.agreement_policy_digest(policy)
        trace=p.run(self.x['blueprint'],req,self.x['snapshot'],agreement_policy=policy)
        self.assertTrue(p.verify_trace(self.x['blueprint'],req,trace,agreement_policy=policy))
        with self.assertRaises(p.ProtocolError):p.verify_trace(self.x['blueprint'],req,trace)
        with self.assertRaises(p.ProtocolError):p.agreement_policy_digest({**p.AGREEMENT_POLICY,'quorum_policy_digest':'ab'*32})
        with self.assertRaises(p.ProtocolError):p.agreement_policy_digest({**policy,'equivalence':'loose-label-only'})

    def test_blueprint_shape_is_authenticated(self):
        bp=copy.deepcopy(self.x['blueprint'])
        bp['nodes'][2]['parent']=0
        with self.assertRaises(p.ProtocolError):p.verify_trace(bp,self.x['request'],self.x['trace'])
        req=copy.deepcopy(self.x['request']);req['market_id']='other'
        with self.assertRaises(p.ProtocolError):p.verify_trace(self.x['blueprint'],req,self.x['trace'])

    def test_source_forgery_and_authenticated_falsehood(self):
        x=p.make_example(4,-7)
        snap=copy.deepcopy(x['snapshot']);snap['reports'][0]['body']['value']=7
        req=copy.deepcopy(x['request']);req['snapshot_digest']=p.object_digest('QM_EXEC_SNAPSHOT_V1',snap)
        # Build a coherent invented record with the new request, retaining the
        # stale genuine signature. A host cannot turn it into authentic data.
        fresh=p.make_example(4,7)['trace']; fresh['context']['request_digest']=p.request_digest(req)
        fresh['context']['snapshot_digest']=req['snapshot_digest'];fresh['records'][0]['input']=snap
        fresh['result']['request_digest']=p.request_digest(req);fresh['result']['snapshot_digest']=req['snapshot_digest']
        fresh['result']['semantic_projection_digest']=p.object_digest('QM_EXEC_SEMANTICS_V1',fresh['records'])
        self.assertTrue(p.verify_trace(x['blueprint'],req,fresh,authenticate=False))
        with self.assertRaises(p.ProtocolError):p.verify_trace(x['blueprint'],req,fresh)
        # A source deliberately signing the same false report passes: source
        # authenticity does not establish truth. The fixture's stipulated truth
        # is negative, external to the execution protocol.
        signed=p.make_example(4,7)
        self.assertTrue(p.verify_trace(signed['blueprint'],signed['request'],signed['trace']))
        self.assertTrue(signed['result']['outcome'])

    def test_snapshot_preimage_and_freshness(self):
        t=copy.deepcopy(self.x['trace']);t['records'][0]['input']['reports']=[]
        with self.assertRaises(p.ProtocolError):p.verify_trace(self.x['blueprint'],self.x['request'],t)
        body=copy.deepcopy(self.x['snapshot']['reports'][0]['body']);body['observed_at']=111
        snap={'version':1,'reports':[p.sign_test_source(body,p.test_keys()['source_a'])]}
        req=copy.deepcopy(self.x['request']);req['snapshot_digest']=p.object_digest('QM_EXEC_SNAPSHOT_V1',snap)
        with self.assertRaises(p.ProtocolError):p.run(self.x['blueprint'],req,snap)


class AvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.x=p.make_example(4)

    def session(self, trace=None):
        t=trace or self.x['trace']
        return p.RevealSession(self.x['blueprint'],self.x['request'],t['context'],p.trace_commitment(t),t['result'])

    def reveal_all(self,s,t=None,at=3):
        trace=t or self.x['trace']; ps=[p.canonical(r) for r in trace['records']];c=p.context_digest(trace['context'])
        for i in range(len(ps)):s.reveal(i,ps[i],p.inclusion_proof(c,ps,i),at)

    def test_public_trace_copy_cannot_mutate_revealed_commitment(self):
        s=self.session();self.reveal_all(s)
        external=s.revealed_trace();external['records'][1]['output']=False
        external['context']['run_id']='forged';external['result']['outcome']=False
        self.assertEqual(s.revealed_trace()['records'],self.x['trace']['records'])
        self.assertFalse(s.challenge(self.x['blueprint'],self.x['request'],4))
        self.assertEqual(s.finalize(13),'finalized')

    def test_accepted_sessions_have_representable_timeout_deadlines(self):
        t=self.x['trace']
        args=(self.x['blueprint'],self.x['request'],t['context'],self.x['trace_root'],t['result'])
        with self.assertRaises(p.ProtocolError):p.RevealSession(*args,proposed_at=p.MAX_INTEGER)
        s=p.RevealSession(*args,proposed_at=p.MAX_INTEGER-20)
        self.assertEqual(s.finalize(p.MAX_INTEGER-10),'unavailable')

    def test_deadlines_start_after_last_reveal(self):
        s=self.session();self.reveal_all(s,at=9)
        self.assertEqual(s.challenge_deadline,19)
        self.assertEqual(s.finalize(18),'challenging')
        self.assertEqual(s.finalize(19),'finalized')
        with self.assertRaises(p.ProtocolError):s.challenge(self.x['blueprint'],self.x['request'],19)
        self.assertEqual(s.finalize(99),'finalized')

    def test_withholding_late_reveal_and_early_finalization(self):
        s=self.session()
        self.assertEqual(s.finalize(9),'revealing')
        self.assertEqual(s.finalize(10),'unavailable')
        with self.assertRaises(p.ProtocolError):self.reveal_all(s,at=10)
        self.assertEqual(s.finalize(100),'unavailable')

    def test_challenge_detects_fraud_only_after_authenticated_reveal(self):
        t=copy.deepcopy(self.x['trace']);t['records'][1]['output']=False
        s=self.session(t);self.reveal_all(s,t)
        self.assertFalse(s.challenge_inclusion(1,b'{}',[],4))
        self.assertEqual(s.status,'challenging')
        self.assertTrue(s.challenge(self.x['blueprint'],self.x['request'],4))
        self.assertEqual(s.finalize(100),'rejected')

    def test_source_preimages_cannot_be_replaced_by_a_fresh_root_placeholder(self):
        for replacement in ({}, {'version':1,'reports':[]}, {'version':1,'reports':[{'body':{},'signature':'00'*256}]}):
            t=copy.deepcopy(self.x['trace']);t['records'][0]['input']=replacement
            s=self.session(t);ps=[p.canonical(r) for r in t['records']];c=p.context_digest(t['context'])
            with self.assertRaises(p.ProtocolError):s.reveal(0,ps[0],p.inclusion_proof(c,ps,0),3)
            for i in range(1,4):s.reveal(i,ps[i],p.inclusion_proof(c,ps,i),3)
            self.assertEqual(len(s.records),3)
            self.assertIsNone(s.challenge_deadline)
            self.assertEqual(s.finalize(10),'unavailable')
        t=copy.deepcopy(self.x['trace']);t['records'][0]['input']['reports'][0]['body']['data']='changed'
        s=self.session(t);ps=[p.canonical(r) for r in t['records']];c=p.context_digest(t['context'])
        with self.assertRaises(p.ProtocolError):s.reveal(0,ps[0],p.inclusion_proof(c,ps,0),3)

    def test_valid_challenge_false_and_monitoring_still_required(self):
        s=self.session();self.reveal_all(s)
        self.assertFalse(s.challenge(self.x['blueprint'],self.x['request'],4))
        self.assertEqual(s.finalize(13),'finalized')
        t=copy.deepcopy(self.x['trace']);t['result']['outcome']=False
        bad=self.session(t);self.reveal_all(bad,t)
        self.assertEqual(bad.finalize(13),'finalized') # optimistic semantic gate

    def test_duplicate_bad_proof_and_wrong_context_do_not_advance_coverage(self):
        s=self.session();t=self.x['trace'];ps=[p.canonical(r) for r in t['records']];c=p.context_digest(t['context'])
        with self.assertRaises(p.ProtocolError):s.reveal(0,ps[0],[],1)
        self.assertEqual(len(s.records),0)
        proof=p.inclusion_proof(c,ps,0);s.reveal(0,ps[0],proof,2)
        with self.assertRaises(p.ProtocolError):s.reveal(0,ps[0],proof,3)
        self.assertEqual(len(s.records),1)
        self.assertEqual(s.finalize(10),'unavailable')
        s=self.session();self.reveal_all(s)
        wrong=copy.deepcopy(self.x['request']);wrong['market_id']='other'
        with self.assertRaises(p.ProtocolError):s.challenge(self.x['blueprint'],wrong,4)
        self.assertEqual(s.status,'challenging')



class TargetedFaultTests(unittest.TestCase):
    def test_two_membership_proofs_are_required(self):
        x=p.make_example(16); t=x['trace'];c=p.context_digest(t['context'])
        payloads=[p.canonical(r) for r in t['records']]
        args=(x['blueprint'],x['request'],t['context'],p.merkle_root(c,payloads),2,payloads[2],p.inclusion_proof(c,payloads,2),payloads[1],p.inclusion_proof(c,payloads,1))
        self.assertFalse(p.verify_local_fault(*args))
        t['records'][2]['output']=999
        payloads=[p.canonical(r) for r in t['records']]
        args=(x['blueprint'],x['request'],t['context'],p.merkle_root(c,payloads),2,payloads[2],p.inclusion_proof(c,payloads,2),payloads[1],p.inclusion_proof(c,payloads,1))
        self.assertTrue(p.verify_local_fault(*args))
        bad=list(args);bad[6]=[]
        self.assertFalse(p.verify_local_fault(*bad))
        bad=list(args);bad[8]=[]
        self.assertFalse(p.verify_local_fault(*bad))
        bad=list(args);bad[7]=b'{}'
        self.assertFalse(p.verify_local_fault(*bad))

    def test_local_checks_cover_every_slot_and_detect_each_typed_mutation(self):
        x=p.make_example(16)
        for index in range(16):
            for corrupt in (False,True):
                t=copy.deepcopy(x['trace'])
                if corrupt:t['records'][index]['output']={'bad':'output'}
                ps=[p.canonical(r) for r in t['records']];c=p.context_digest(t['context'])
                parent=x['blueprint']['nodes'][index]['parent']
                args=[x['blueprint'],x['request'],t['context'],p.merkle_root(c,ps),index,ps[index],p.inclusion_proof(c,ps,index)]
                if parent is not None:args.extend([ps[parent],p.inclusion_proof(c,ps,parent)])
                self.assertEqual(p.verify_local_fault(*args),corrupt)

    def test_source_key_alias_rejected(self):
        x=p.make_example()
        for mutate in (lambda n:n.upper(),lambda n:'0'+n,lambda n:'0x'+n):
            bp=copy.deepcopy(x['blueprint']);bp['source_key']['n']=mutate(bp['source_key']['n'])
            with self.assertRaises(p.ProtocolError):p.validate_blueprint(bp)


if __name__ == "__main__":
    unittest.main()
