/** Independently written Node canonical-byte / Merkle verifier.
 * No Python invocation or generated Python algorithm is used. Not a full DAG
 * or RSA implementation: its cross-language scope is intentionally explicit.
 * Usage: node independent_verifier.mjs vectors.json > report.json
 */
import crypto from 'node:crypto';
import fs from 'node:fs';

const MAX_OBJECT = 64*4096+16384;
function canon(x, depth=0) {
  if (depth>32) throw Error('nesting');
  if (x === null) return 'null';
  if (typeof x === 'boolean') return x ? 'true':'false';
  if (typeof x === 'number') {
    if (!Number.isSafeInteger(x) || Object.is(x, -0)) throw Error('integer');
    return String(x);
  }
  if (typeof x === 'string') {
    if ([...x].some(c=>c.codePointAt(0)>127)) throw Error('ASCII');
    return JSON.stringify(x).replace(/\u007f/g, '\\u007f');
  }
  if (Array.isArray(x)) return '['+x.map(v=>canon(v,depth+1)).join(',')+']';
  if (typeof x === 'object') return '{'+Object.keys(x).sort().map(k=>canon(k,depth+1)+':'+canon(x[k],depth+1)).join(',')+'}';
  throw Error('type');
}
function parseCanonical(hex) {
  const buf=Buffer.from(hex,'hex');
  if (buf.length>MAX_OBJECT || [...buf].some(v=>v>127)) throw Error('bytes');
  const raw=buf.toString('ascii'), v=JSON.parse(raw), again=canon(v);
  // Re-encoding rejects duplicate keys as well as number/key-order aliases.
  if (again!==raw) throw Error('noncanonical');
  return v;
}
const sha=(...args)=>crypto.createHash('sha256').update(Buffer.concat(args)).digest();
const tag=s=>Buffer.from(s+'\0','ascii');
const hex=s=>{
  if (typeof s!=='string'||!/^[0-9a-f]{64}$/.test(s)) throw Error('hex');
  return Buffer.from(s,'hex');
};
const u64=n=>{
  if (!Number.isSafeInteger(n)||n<0) throw Error('integer');
  const out=Buffer.alloc(8); out.writeBigUInt64BE(BigInt(n)); return out;
};
const leaf=(c,n,i,p)=>sha(tag('QM_EXEC_LEAF_V1'),hex(c),u64(n),u64(i),sha(p));
const pad=(c,n,i)=>sha(tag('QM_EXEC_PAD_V1'),hex(c),u64(n),u64(i));
const node=(a,b)=>sha(tag('QM_EXEC_NODE_V1'),a,b);
const wrap=(c,n,r)=>sha(tag('QM_EXEC_ROOT_V1'),hex(c),u64(n),r).toString('hex');
function root(c,payloads) {
  const n=payloads.length;
  if (n<1||n>64) throw Error('count');
  let row=payloads.map((p,i)=>leaf(c,n,i,Buffer.from(p,'hex')));
  const width=2**Math.ceil(Math.log2(n));
  while (row.length<width) row.push(pad(c,n,row.length));
  while (row.length>1) row=Array.from({length:row.length/2},(_,i)=>node(row[2*i],row[2*i+1]));
  return wrap(c,n,row[0]);
}
function verify(v) {
  try {
    const {context,count:n,index:i,payload_hex,proof,root:r}=v;
    if (!Number.isInteger(n)||n<1||n>64||!Number.isInteger(i)||i<0||i>=n||typeof payload_hex!=='string'||!/^(?:[0-9a-f]{2})*$/.test(payload_hex)) return false;
    const p=Buffer.from(payload_hex,'hex');
    if (p.length>4096||!Array.isArray(proof)||proof.length!==Math.ceil(Math.log2(n))) return false;
    hex(r);
    let current=leaf(context,n,i,p), cursor=i;
    proof.forEach((s,level)=>{
      const sibling=hex(s), start=(cursor^1)*2**level;
      if (start>=n) {
        let pads=Array.from({length:2**level},(_,j)=>pad(context,n,start+j));
        while (pads.length>1) pads=Array.from({length:pads.length/2},(_,j)=>node(pads[2*j],pads[2*j+1]));
        if (!sibling.equals(pads[0])) throw Error('padding');
      }
      current=cursor%2===0?node(current,sibling):node(sibling,current);
      cursor=Math.floor(cursor/2);
    });
    return wrap(context,n,current)===r;
  } catch { return false; }
}
const vectors=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const report={implementation:'independent Node.js canonical/Merkle verifier v1',node_version:process.version,
 canonical:vectors.canonical.map(v=>{let accepted=false,canonical_hex=null;try{canonical_hex=Buffer.from(canon(parseCanonical(v.raw_hex)),'ascii').toString('hex');accepted=true;}catch{}return {id:v.id,accepted,canonical_hex};}),
 trees:vectors.trees.map(v=>({id:v.id,root:root(v.context,v.payloads_hex)})),
 proofs:vectors.proofs.map(v=>({id:v.id,accepted:verify(v)}))};
process.stdout.write(JSON.stringify(report,null,2)+'\n');
