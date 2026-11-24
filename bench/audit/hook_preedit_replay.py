import json,glob,os,re,sys,collections,statistics as st,subprocess
sys.path.insert(0,'.')
from pathlib import Path
from devkb import hook
proj=Path('.').resolve()
tracked=set(subprocess.run(['git','ls-files'],capture_output=True,text=True).stdout.split())
WRITE=re.compile(r"(\bsed\s+-i|\btee\b|>\s*[\w./~$\"'-]+\.(?:py|ts|tsx|js|c|cc|cpp|h|hpp)\b|\bgit\s+(?:apply|checkout\s+--|restore|stash)|\bpatch\b|\bmv\b|\bcp\b|open\([^)]*['\"][wa]['\"]|\.write_text\(|\.write\(|\bpython3?\s+-\s*<<|\bcat\s*>)")
sess=collections.defaultdict(list)
for f in glob.glob(os.path.expanduser('~/.claude/projects/-home-namiq-orchestra-ip-devkb/*.jsonl')):
    sid=os.path.basename(f)
    for l in open(f):
        try:d=json.loads(l)
        except Exception:continue
        if d.get('timestamp','')<'2026-11-20T08:00':continue
        c=(d.get('message') or {}).get('content')
        if isinstance(c,list):
            for b in c:
                if isinstance(b,dict) and b.get('type')=='tool_use' and b['name'] in('Bash','Edit','Write','MultiEdit'):
                    sess[sid].append((b['name'],b['input']))
sizes={}
def size(rel):
    if rel not in sizes:
        r=subprocess.run([sys.executable,'-m','devkb.cli','pack','--project',str(proj),'file',rel],capture_output=True,text=True,timeout=60)
        t=r.stdout.strip();sizes[rel]=None if r.returncode or not t or 'The graph has no code' in t else min(len(t),hook.LIMIT)
    return sizes[rel]
def rels_of(tool,inp):
    out=[]
    if tool=='Bash':
        for m in hook._PATH.finditer(inp.get('command') or ''):
            try: rel=(proj/m.group(1)).resolve().relative_to(proj).as_posix()
            except ValueError: continue
            if rel in tracked and rel not in out: out.append(rel)
    else:
        raw=inp.get('file_path') or ''
        try: rel=Path(raw).resolve().relative_to(proj).as_posix()
        except ValueError: return out
        if rel in tracked: out.append(rel)
    return out
inj=[]  # (sid,idx,rel,size,write_intent)
for sid,calls in sess.items():
    seen=set()
    for i,(tool,inp) in enumerate(calls):
        if tool!='Bash':continue
        cmd=inp.get('command') or ''
        wi=bool(WRITE.search(cmd))
        n=0
        for rel in rels_of(tool,inp):
            if rel in seen:continue
            s=size(rel)
            if not s:continue
            seen.add(rel);inj.append((sid,i,rel,s,wi));n+=1
            if n>=hook.BASH_FILES:break
# later change?
def later_changed(sid,i,rel):
    for j,(tool,inp) in enumerate(sess[sid][i+1:],i+1):
        if tool in('Edit','Write','MultiEdit') and rel in rels_of(tool,inp):return True
        if tool=='Bash' and WRITE.search(inp.get('command') or '') and rel in rels_of(tool,inp):return True
    return False
tot=len(inj);w=[x for x in inj if x[4]]
hit=[x for x in inj if later_changed(x[0],x[1],x[2])]
print('packs',tot,'chars',sum(x[3] for x in inj))
print('on write-intent commands',len(w),'chars',sum(x[3] for x in w),'| on read commands',tot-len(w),'chars',sum(x[3] for x in inj if not x[4]))
print('injected file later changed in session:',len(hit),'of',tot,'=',round(len(hit)/tot,2),'chars of those',sum(x[3] for x in hit))
print('chars if capped at 3200 (800 tokens):',sum(min(x[3],3200) for x in inj),'| write-intent only capped:',sum(min(x[3],3200) for x in w))
print('injected, never changed later: files',len({x[2] for x in inj if x not in hit}))
