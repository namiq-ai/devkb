#include "only_cpp.h"
#include "mixed.h"
int user1(int x) { return only_cpp_fn(x) + mixed_fn(x); }
