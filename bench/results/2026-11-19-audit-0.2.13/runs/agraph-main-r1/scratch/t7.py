import sys; sys.path.insert(0, "audit/scratch")
from h import *
exec(open("audit/scratch/t6.py").read().split("d = mk(F)")[0].split("from h import *")[1])
d = mk(F); build(d)
for kind, n in [("change", "src/a.cc::Foo.get"), ("change", "Foo.put"), ("change", "Foo::put"), ("refactor", "src/a.cc::Foo.get"), ("change", "Bar.get")]:
    print("=====", kind, n); print(dk("pack", "--project", d, kind, n)[1][:1800])
print(dk("symbol", "--project", d, "Foo.get")[1])
print(dk("symbol", "--project", d, "src/a.cc::Foo.get")[1])
print(dk("uses", "--project", d, "put")[1])
