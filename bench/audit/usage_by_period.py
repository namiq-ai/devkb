"""devkb usage by period (0.2.15): the guardrail log, devkb telemetry and the working sessions' tool mix, cut at the merge times of the fixes that change what an
agent sees (CUTS). Run from the repository root: python bench/audit/usage_by_period.py. Times are local (-0600). See docs/analysis/devkb-usage-0.2.15-by-period.md."""
import json,os,collections,datetime as dt,re,sys
sys.path.insert(0,'bench/audit')
import toolmix as tm
CST=dt.timezone(dt.timedelta(hours=-6))
CUTS=[("E1 0.2.14 hook, before #375","2026-11-20T02:00","2026-11-20T12:35"),
      ("E2 after #375 (reminder names a runnable command; teach lines off on duplicates)","2026-11-20T12:35","2026-11-20T19:38"),
      ("E3 after #369 (benchmark prompts say how to run commands: no more refused devkb attempts)","2026-11-20T19:38","2026-11-21T17:28"),
      ("E4 after #401 (pack test-mention changes, router off by default, QB harness)","2026-11-21T17:28","2026-11-22T15:46"),
      ("E5 after #408/#410 (bare head, stale scope)","2026-11-22T15:46","2026-11-23T00:00")]
def ep(t):
    for n,a,b in CUTS:
        if a<=t<b:return n
    return None
WORK=('42e9d8fb','acc99be4','d417ed39')
L=[json.loads(l) for l in open(os.path.expanduser('~/.claude/hooks/devkb-guardrail.log')) if l.startswith('{')]
out={}
for n,_,_ in CUTS:
    xs=[r for r in L if ep(r['t'])==n]
    w=[r for r in xs if (r.get('session') or '').startswith(WORK)]
    b=[r for r in xs if r not in w]
    A=('alongside','substitute','span-hint','read-answer')
    dec=lambda ys:[r for r in ys if r.get('action')]
    row={}
    for nm,ys in(('work',dec(w)),('bench',dec(b))):
        ys=[r for r in ys if r['action']!='remind']
        ans=sum(1 for r in ys if r['action'] in A)
        pt=collections.Counter(r.get('reason') for r in ys if r['action']=='pass-through')
        row[nm]=dict(dec=len(ys),ans=ans,stale=pt.get('stale-graph',0),notc=pt.get('not-complete',0),dup=sum(v for k,v in pt.items() if str(k).startswith('duplicate')),sess=len({r.get('session') for r in ys}))
    out[n]=row
T=[json.loads(l) for l in open('.devkb/process-api-telemetry.jsonl') if l.strip()]
tel=collections.defaultdict(collections.Counter)
for r in T:
    t=dt.datetime.fromtimestamp(r['t']).strftime('%Y-%m-%dT%H:%M')
    e=ep(t)
    if e:tel[e][r['tool']]+=1
P=os.path.expanduser('~/.claude/projects/-home-namiq-orchestra-ip-devkb/')
mix=collections.defaultdict(lambda:collections.Counter())
for sid in ['42e9d8fb-2f92-4096-8e3b-514de4ed47de','acc99be4-a9d2-4bb8-b20b-85e94e522474','d417ed39-0d79-431d-a033-6a2a16f5d4cd']:
    for l in open(P+sid+'.jsonl'):
        try:d=json.loads(l)
        except:continue
        m=d.get('message')
        c=m.get('content') if isinstance(m,dict) else None
        if d.get('type')!='assistant' or not isinstance(c,list):continue
        ts=d.get('timestamp')
        try:t=dt.datetime.fromisoformat(ts.replace('Z','+00:00')).astimezone(CST).strftime('%Y-%m-%dT%H:%M')
        except Exception:continue
        e=ep(t)
        if not e:continue
        for b in c:
            if isinstance(b,dict) and b.get('type')=='tool_use':
                cl=tm.classify(b['name'],b.get('input') or {})
                mix[e][cl]+=1
                if b['name'].startswith('mcp__devkb'):mix[e]['mcp']+=1
for n,_,_ in CUTS:
    print('##',n)
    print('  guard work ',out[n]['work']);print('  guard bench',out[n]['bench'])
    print('  telemetry ',dict(tel[n]),' | session mix',dict(mix[n]))
