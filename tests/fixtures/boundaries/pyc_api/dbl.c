#include <Python.h>
static PyObject *dbl_one(PyObject *self, PyObject *args) { return 0; }
static PyObject *dbl_two(PyObject *self, PyObject *args) { return 0; }
static PyMethodDef first[] = {{"add", dbl_one, METH_VARARGS, ""}, {NULL, NULL, 0, NULL}};
static PyMethodDef second[] = {{"add", dbl_two, METH_VARARGS, ""}, {NULL, NULL, 0, NULL}};
PyMODINIT_FUNC PyInit_dbl(void) { return 0; }
