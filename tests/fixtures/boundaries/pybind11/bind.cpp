#include <pybind11/pybind11.h>
namespace py = pybind11;
int add_ints(int a, int b) { return a + b; }
int mul(int a, int b) { return a * b; }
double mul(double a, double b) { return a * b; }
struct K {
  int go(int x) { return x; }
};
PYBIND11_MODULE(demo, m) {
  m.def("add", &add_ints);
  m.def("sub", [](int a, int b) { return a - b; });
  m.def("mul", py::overload_cast<int, int>(&mul));
  py::class_<K>(m, "K").def("go", &K::go);
}
