#include <pybind11/pybind11.h>
int add_a(int a, int b) { return a + b; }
int add_b(int a, int b) { return a + b + 1; }
PYBIND11_MODULE(twin, m) {
  m.def("add", &add_a);
  m.def("add", &add_b);
}
