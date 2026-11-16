import ctypes

lib = ctypes.CDLL("./libcalc.so")


def go():
    return lib.add_ints(1, 2)
