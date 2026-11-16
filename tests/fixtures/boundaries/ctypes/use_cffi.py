from cffi import FFI

ffi = FFI()
ffi.cdef("int add_ints(int, int);")
clib = ffi.dlopen("calc")


def go_cffi():
    return clib.add_ints(1, 2)
