void *dlsym(void *h, const char *n);
void *by_variable(void *h, const char *name) { return dlsym(h, name); }
void *by_literal(void *h) { return dlsym(h, "lib_add"); }
