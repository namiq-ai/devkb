import json,glob,re,subprocess,collections,sys,statistics as st
sys.path.insert(0,"bench/readtools")
from tool_usage import usage
E,SP=sys.argv[1],sys.argv[2]
rows=[]
for f in sorted(glob.glob(E+"/nav/*.jsonl")):
    arm,tid,rep=re.match(r".*/(plain|devkb)-(N\d)-r(\d)\.jsonl",f).groups()
    res={}; best={}; cost=0; turns=0; msgs=set(); tools=collections.Counter()
    for l in open(f):
        try:e=json.loads(l)
        except ValueError: continue
        if e.get("type")=="assistant":
            if e["message"].get("id"): msgs.add(e["message"]["id"])
            for x in e["message"]["content"]:
                if x.get("type")=="tool_use": tools[x["name"].replace("mcp__devkb__","devkb:")]+=1
        if e.get("type")=="result":
            res=e; cost=max(cost,e.get("total_cost_usd",0)); turns+=e.get("num_turns",0)
            for u in (e.get("modelUsage") or {}).values():
                for k,v in u.items():
                    if isinstance(v,(int,float)): best[k]=max(best.get(k,0),v)
    open(SP+"/ans.txt","w").write(res.get("result") or "")
    sc=float(subprocess.run(["python3","bench/readtools/nav_score.py",E+"/nav-tasks.json",tid,SP+"/ans.txt"],capture_output=True,text=True).stdout.strip() or 0)
    u,size=usage(f)
    ctx=best.get("inputTokens",0)+best.get("cacheCreationInputTokens",0)+best.get("cacheReadInputTokens",0)
    rows.append(dict(arm=arm,tid=tid,rep=rep,score=sc,turns=turns,msgs=len(msgs),cost=cost,ctx=ctx,out=best.get("outputTokens",0),grep=u.get("grep",0),load=u.get("file load",0),
                     dk=sum(v for k,v in tools.items() if k.startswith("devkb:")),dktools=dict((k,v) for k,v in tools.items() if k.startswith("devkb:")),text=sum(size.values())))
json.dump(rows,open(E+"/nav-rows.json","w"))
m=lambda xs: sum(xs)/len(xs)
NAMES={"N1":"symbol: exact lines of a function","N2":"symbol: qualified method lines","N3":"symbol: misspelled name","N4":"outline: methods of a class","N5":"uses: files with a constant","N6":"uses: every reference","N7":"search_docs: doc and heading","N8":"symbol glob: names by prefix"}
print("| Question | Tool it exercises | Arm | Score | Turns | Model calls | Grep | File load | devkb | Text returned | Tokens (ctx / out) | Cost |"); print("|"+"---|"*12)
for tid in sorted({r['tid'] for r in rows}):
    for arm in ("plain","devkb"):
        v=[r for r in rows if r['tid']==tid and r['arm']==arm]
        print(f"| {tid} {NAMES[tid] if arm=='plain' else ''} | | {arm} | {m([r['score'] for r in v]):.2f} | {m([r['turns'] for r in v]):.1f} | {m([r['msgs'] for r in v]):.1f} | {m([r['grep'] for r in v]):.1f} | {m([r['load'] for r in v]):.1f} | {m([r['dk'] for r in v]):.1f} | {m([r['text'] for r in v])/1000:.1f}k | {m([r['ctx'] for r in v])/1000:.0f}k / {m([r['out'] for r in v])/1000:.1f}k | ${m([r['cost'] for r in v]):.3f} |")
for arm in ("plain","devkb"):
    v=[r for r in rows if r['arm']==arm]
    print(f"| **All 16 runs** | | **{arm}** | {m([r['score'] for r in v]):.2f} | {m([r['turns'] for r in v]):.1f} | {m([r['msgs'] for r in v]):.1f} | {m([r['grep'] for r in v]):.1f} | {m([r['load'] for r in v]):.1f} | {m([r['dk'] for r in v]):.1f} | {m([r['text'] for r in v])/1000:.1f}k | {m([r['ctx'] for r in v])/1000:.0f}k / {m([r['out'] for r in v])/1000:.1f}k | ${m([r['cost'] for r in v]):.3f} |")
d=[r for r in rows if r['arm']=='devkb']
print(); print("runs using a devkb tool:",sum(1 for r in d if r['dk']),"of",len(d),"| by question:",{t:sum(1 for r in d if r['tid']==t and r['dk']) for t in sorted({r['tid'] for r in d})})
c=collections.Counter()
for r in d:
    for k,n in r['dktools'].items(): c[k]+=n
print("tools:",dict(c))
