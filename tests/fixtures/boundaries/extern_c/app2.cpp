#include <string.h>
extern "C" int vendor_fn(int);
int probe() { foo(1.0); return strlen("x") + vendor_fn(1); }
