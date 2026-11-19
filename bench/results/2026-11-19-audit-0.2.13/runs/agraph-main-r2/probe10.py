import sys; sys.path.insert(0, "audit")
from probe import *
files = {
    "x.h": '''
#pragma once
namespace n1 { class W { public: void go(); void go(int); static void make(); }; }
namespace n2 { class W { public: void go(); }; }
class Own { public: void tick(); void tock(); };
class Base { public: virtual void v(); };
class Derived : public Base { public: void v() override; };
''',
    "x.cc": '''
#include "x.h"
namespace n1 { void W::go() {} void W::go(int) {} void W::make() {} }
namespace n2 { void W::go() {} }
void Own::tick() { tock(); }
void Own::tock() {}
void Base::v() {}
void Derived::v() {}
''',
    "u.cc": '''
#include "x.h"
using Alias = n1::W;
typedef n2::W TW;
struct Holder { n2::W w_; n1::W* p_; void run(); };
void Holder::run() { w_.go(); p_->go(1); }
void f1() { n1::W w; w.go(); }
void f2() { n2::W w; w.go(); }
void f3() { Alias a; a.go(); }
void f4() { TW t; t.go(); }
void f5() { auto a = n1::W(); a.go(); }
void f6() { n1::W::make(); }
void f7(Base* b) { b->v(); }
void f8() { n1::W w; { n2::W w; w.go(); } }
void f9(int go) { go = 1; }
void f10(std::vector<n1::W>& v) { v[0].go(); }
void f11() { n1::W w; auto fn = [&]() { w.go(2); }; fn(); }
''',
    "u_test.cc": '''
#include "x.h"
TEST(Suite, Name) { n2::W w; w.go(); }
TEST_F(Fixture, Name2) { Own o; o.tick(); }
''',
}
d, out = build(files)
print(out)
for q in sys.argv[1:]:
    print("=====", q)
    r = devkb(d, *q.split())[1]
    print("\n".join(l for l in r.splitlines() if l.strip() and not l.startswith(("This pack", "C/C++", "---", "Built"))))
