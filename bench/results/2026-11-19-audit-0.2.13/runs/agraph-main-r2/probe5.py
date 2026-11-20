import sys; sys.path.insert(0, "audit")
from probe import *
files = {
    "m.h": '''
#pragma once
#define CHECK(x) check_impl(x, __LINE__)
#define LOG(x) do { log_it(x); CHECK(x); } while (0)
#ifdef FAST
#define MODE() fast_mode()
#else
#define MODE() slow_mode()
#endif
#define NOARGS helper_noargs()
#define PASTE(a) a##_suffix()
#define SELF(x) SELF(x)
#define A1(x) B1(x)
#define B1(x) A1(x) + leaf1()
void check_impl(int, int);
void log_it(int);
void fast_mode();
void slow_mode();
void helper_noargs();
void leaf1();
''',
    "m.cc": '''
#include "m.h"
void check_impl(int, int) {}
void log_it(int) {}
void fast_mode() {}
void slow_mode() {}
void helper_noargs() {}
void leaf1() {}
void c1() { CHECK(1); }
void c2() { LOG(2); }
void c3() { MODE(); }
void c4() { NOARGS; }
void c5() { SELF(1); }
void c6() { A1(1); }
void c7() { int NOARGS_x = 0; }
void c8() { (void)sizeof(CHECK); }
''',
    "test_m.cc": '''
#include "m.h"
void test_c() { LOG(3); }
''',
}
d, out = build(files)
print(out)
for q in sys.argv[1:]:
    print("=====", q)
    print(devkb(d, *q.split())[1][:2500])
