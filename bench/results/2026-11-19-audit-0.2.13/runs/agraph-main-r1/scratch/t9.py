import sys, json, os; sys.path.insert(0, "audit/scratch")
from h import *
F = {
"a.h": '''
#define LOG(x) fa(x)
#define REC(x) REC2(x)
#define REC2(x) REC(x) + ga(x)
#define DEBUGONLY(x) dbg(x)
''',
"b.h": '''
#define LOG(x) fb(x)
''',
"fa.cc": "void fa(int){}\nvoid fb(int){}\nvoid ga(int){}\nvoid dbg(int){}\nvoid other(int){}\n",
"c.cc": '''
#include "a.h"
#undef DEBUGONLY
void DEBUGONLY(int);
void use1() { LOG(1); }
void use2() { REC(1); }
void use3() { DEBUGONLY(2); }
''',
"d.cc": '''
#include "b.h"
void use4() { LOG(1); }
''',
"e.cc": '''
void LOG(int);
void use5() { LOG(1); }
struct S { void other(int); };
#define call_other(s) (s).other(1)
void use6(S& s) { call_other(s); }
''',
}
d = mk(F); print(build(d)[1][-100:])
for n in ["fa", "fb", "ga", "dbg", "other"]:
    print("=====", n); print(dk("pack", "--project", d, "change", n)[1][:900])
