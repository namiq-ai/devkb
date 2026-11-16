static int helper(void) { return 1; }
int init(void) { return helper(); }
int dup(void) { return 1; }
int run_a(void) { return helper(); }
