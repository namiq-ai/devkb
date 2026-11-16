struct ops { int (*read)(void); };
int my_read(void) { return 0; }
int on_a(void) { return 1; }
int on_b(void) { return 2; }
static const struct ops o = { .read = my_read };
int (*handlers[])(void) = { on_a, on_b };
