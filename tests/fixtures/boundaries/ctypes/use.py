import ctypes

lib = ctypes.CDLL("./libcalc.so")


class Other:
    def add_ints(self, a, b):
        return a + b


def go():
    return lib.add_ints(1, 2)


def not_a_handle(obj):
    return obj.add_ints(1, 2)


def dynamic(name):
    return getattr(lib, name)(1, 2)


def hidden():
    return lib.helper(1)


def twice():
    return lib.dup(1)
