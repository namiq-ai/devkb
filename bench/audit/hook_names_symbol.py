import json,collections,os,subprocess,re,sys
p=os.path.expanduser('~/.claude/hooks/devkb-guardrail.log')
rows=[json.loads(l) for l in open(p) if l.strip().startswith('{')]
W=[r for r in rows if r['t']>='2026-11-20T01:59' and r.get('action')=='pass-through' and (r.get('reason') or '').startswith('not-complete')]
names=collections.Counter();intent={}
for r in W:
    for n,v in zip(r.get('names') or [],r.get('verdicts') or []):
        if v=='cannot-resolve':names[n]+=1;intent.setdefault(n,r.get('intent'))
print(len(names),'unique names,',sum(names.values()),'occurrences')
out={}
for n in names:
    q=subprocess.run(['.venv/bin/devkb','symbol',n,'--project','.'],capture_output=True,text=True,timeout=60).stdout.splitlines()
    head=q[0] if q else ''
    m=re.search(r'(\d+) match(?:es)? \((\w+)',head)
    if m:out[n]=(int(m.group(1)),m.group(2))
    elif 'no symbol' in head:out[n]=(0,'none')
    else:out[n]=(-1,head[:30])
cls=collections.Counter()
for n,c in names.items():
    k,kind=out[n]
    key='no symbol' if k==0 else ('exact, one' if kind=='exact' and k==1 else ('exact, several' if kind=='exact' else 'other kind of match'))
    cls[key]+=c
print(cls)
json.dump({n:[names[n],out[n]] for n in names},open('/tmp/hook_names_symbol.json','w'))
