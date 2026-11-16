#include <Python.h>
static PyObject *py_add(PyObject *self, PyObject *args) { return 0; }
static PyMethodDef methods[] = {{"add", py_add, METH_VARARGS, ""}, {NULL, NULL, 0, NULL}};
PyMODINIT_FUNC PyInit_calc(void) { return 0; }
