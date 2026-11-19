import sys; sys.path.insert(0, "audit/scratch")
from h import *
F = {
"src/a.h": '''
#pragma once
class Foo {
 public:
  int get(int x);
  int get(int x, int y);
  void put();
};
class Bar {
 public:
  void put();
  int get(int x);
};
#define CALL_PUT(o) do { (o).put(); helper(); } while (0)
#define OUTER(o) CALL_PUT(o)
#define TWO(a) one(a)
#define TWO2(a) two(a)
''',
"src/a.cc": '''
#include "a.h"
void helper() {}
void one(int) {}
int Foo::get(int x) { return x; }
int Foo::get(int x, int y) { return x + y; }
void Foo::put() { helper(); }
void Bar::put() { one(1); }
int Bar::get(int x) { return x; }
void useFoo(Foo& f) { f.get(1); }
void useFoo2(Foo& f) { f.get(1, 2); }
void useBar(Bar* b) { b->put(); }
void viaMacro(Foo& f) { CALL_PUT(f); }
void viaOuter(Bar& f) { OUTER(f); }
void viaLocal() { Foo f; f.put(); Bar b; b.get(1); }
''',
"test/t.cc": '''
#include "../src/a.h"
class FooTest : public ::testing::Test {
 public:
  Foo foo_;
  void SetUp() {}
};
TEST_F(FooTest, Puts) { foo_.put(); }
TEST_F(FooTest, Gets) { foo_.get(1, 2); }
TEST(Plain, X) { Bar b; b.get(2); }
''',
}
d = mk(F); print(d)
print(build(d)[1][-300:])
for kind, n in [("change", "src/a.cc::Foo::put"), ("change", "Bar::put"), ("change", "Foo::get"), ("refactor", "Foo::get"), ("change", "helper"), ("change", "one")]:
    print("=====", kind, n); print(dk("pack", "--project", d, kind, n)[1][:1600])
print(dk("symbol", "--project", d, "Foo::get", "--source")[1])
print(dk("outline", "--project", d, "src/a.cc")[1])
