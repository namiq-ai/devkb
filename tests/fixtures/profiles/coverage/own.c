static int helper(void) { return 1; }
static int twice(void) { return helper() + helper(); }
int api_c(void) { return twice(); }
