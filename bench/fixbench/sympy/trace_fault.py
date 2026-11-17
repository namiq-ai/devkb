"""Print the first call stack (snippet -> faulty function) seen when running a bug's snippet.
Usage: python trace_fault.py <snippet.py> <file-suffix> <function-name> [def-lineno|0] [ancestor-function-name]"""
import sys, runpy
snip, fsuf, fname = sys.argv[1:4]
lineno = int(sys.argv[4]) if len(sys.argv) > 4 else 0
anc = sys.argv[5] if len(sys.argv) > 5 else None
found = []
def prof(frame, event, arg):
    if event == 'call' and not found and frame.f_code.co_name == fname and frame.f_code.co_filename.endswith(fsuf) and (not lineno or frame.f_code.co_firstlineno == lineno):
        st = []; f = frame
        while f:
            st.append(f); f = f.f_back
        st.reverse()
        i = next(k for k, f in enumerate(st) if f.f_code.co_filename.endswith(snip.split('/')[-1]))
        chain = [f for f in st[i+1:] if '/sympy/' in f.f_code.co_filename and '/sympy/core/cache.py' not in f.f_code.co_filename and 'multipledispatch' not in f.f_code.co_filename]
        if anc is None or any(f.f_code.co_name == anc for f in chain[:-1]):
            found.append(chain)
sys.setprofile(prof)
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    runpy.run_path(snip, run_name='__main__')
sys.setprofile(None)
ch = found[0]
for f in ch:
    print('  %s:%d %s' % (f.f_code.co_filename.split('/src/')[-1], f.f_code.co_firstlineno, f.f_code.co_name))
print('call distance (sympy frames, excl. cache/dispatch wrappers):', len(ch) - 1)
