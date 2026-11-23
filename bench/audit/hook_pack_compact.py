import json,re,sys,subprocess,collections,statistics as st
sys.path.insert(0,'.')
from devkb import hook
exec(open('bench/audit/hook_preedit_replay.py').read().split("inj=[]")[0])
files=set()
for sid,calls in sess.items():
    for tool,inp in calls:
        if tool=='Bash':
            for r in rels_of(tool,inp):files.add(r)
files=sorted(f for f in files if size(f))
texts={}
for f in files:
    r=subprocess.run([sys.executable,'-m','devkb.cli','pack','--project',str(proj),'file',f],capture_output=True,text=True,timeout=60)
    texts[f]=r.stdout.strip()
def sections(t):
    parts=re.split(r'\n(?=## |\*\*Incomplete)',t)
    return parts
def compact(t,k=6):
    out=[]
    for p in sections(t):
        lines=p.splitlines()
        if p.startswith('## Tests') or p.startswith('## Functions') or p.startswith('## Files'):
            head,body=lines[0],lines[1:]
            body_items=[l for l in body if l.strip()]
            keep=body_items[:k]
            more=len(body_items)-len(keep)
            out.append('\n'.join([head]+keep+([f'(+{more} more: devkb pack --project . file FILE)'] if more>0 else [])))
        else: out.append(p)
    # honesty first
    inc=[p for p in out if p.startswith('**Incomplete')]
    rest=[p for p in out if not p.startswith('**Incomplete')]
    return '\n'.join(inc+rest)
cut_loses=0;n=0;cur=[];cmp_=[];inc_total=0
for f,t in texts.items():
    if not t:continue
    n+=1
    has_inc='**Incomplete' in t
    inc_total+=has_inc
    if len(t)>hook.LIMIT:
        kept=t[:hook.LIMIT].rsplit('\n',1)[0]
        if has_inc and '**Incomplete' not in kept:cut_loses+=1
    cur.append(min(len(t),hook.LIMIT));cmp_.append(len(compact(t)))
print('distinct files',n,'with an Incomplete note',inc_total,'over the cap',sum(1 for f,t in texts.items() if len(t)>hook.LIMIT))
print('Incomplete note LOST by the 6000 cut:',cut_loses)
print('current median/p90/total chars',st.median(cur),sorted(cur)[int(len(cur)*.9)],sum(cur))
print('compact(6 per list, Incomplete first) median/p90/total',st.median(cmp_),sorted(cmp_)[int(len(cmp_)*.9)],sum(cmp_),'over 3200:',sum(1 for x in cmp_ if x>3200))
