import sys; sys.path.insert(0, "audit")
from probe import *
files = {
    "lib.h": '''
#pragma once
namespace ns {
class A { public:
  int run(int x);
  int run(int x, int y);
  void stop();
};
class B { public:
  int run(int x);
  void stop();
};
int free_fn(int);
int free_fn(int, int);
}
''',
    "lib.cc": '''
#include "lib.h"
namespace ns {
int A::run(int x) { return x; }
int A::run(int x, int y) { return x + y; }
void A::stop() {}
int B::run(int x) { return x * 2; }
void B::stop() {}
int free_fn(int a) { return a; }
int free_fn(int a, int b) { return a + b; }
}
''',
    "use.cc": '''
#include "lib.h"
#include "macros.h"
void do_a() {
  ns::A a;
  a.run(1);
}
void do_a2() {
  ns::A a;
  a.run(1, 2);
}
void do_b(ns::B* b) {
  b->run(3);
  b->stop();
}
void do_ref(ns::A& r) { r.stop(); }
void do_free() { ns::free_fn(1, 2); }
void via_macro() { CALL_STOP(); }
void via_macro2() { MAYBE(1); }
''',
    "macros.h": '''
#define CALL_STOP() do_ref_helper()
#define MAYBE(x) ns::free_fn(x)
void do_ref_helper();
''',
    "t.cc": '''
#include "lib.h"
TEST_F(Fix, Case1) {
  ns::A a;
  a.stop();
}
''',
}
d, out = build(files)
print(out)
for q in sys.argv[1:]:
    print("=====", q)
    print(devkb(d, *q.split())[1][:2500])
