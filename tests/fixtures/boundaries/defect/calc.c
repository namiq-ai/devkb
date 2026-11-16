int Java_demo_Calc_nativeAdd(void *env, void *cls, int a, int b) { return a + b; }
int add_ints(int a, int b) { return a + b; }
static int local_sum(int a, int b) { return a + b; }
int total(int a) { return local_sum(a, local_sum(a, 1)); }
void *PyInit_calc(void) { return 0; }
