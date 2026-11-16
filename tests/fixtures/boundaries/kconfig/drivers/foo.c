#if defined(CONFIG_FOO)
static int enabled = 1;
#endif
#ifdef CONFIG_FOO
int foo_a(void) { return 1; }
#endif
int foo_init(void) {
	if (IS_ENABLED(CONFIG_FOO)) {
		return CONFIG_FOO_BUF_SIZE;
	}
	return CONFIG_BAR;
}
int foo_dev(void) { return DT_NODELABEL(foo); }
/* CONFIG_BAZ in a comment */
const char *s = "CONFIG_BAZ in a string";
#if 0
int dead = CONFIG_BAZ;
#endif
