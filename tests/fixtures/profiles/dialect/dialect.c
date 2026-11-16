__attribute__((section(".ram"))) int ram_fn(int x) { return x; }
__interrupt void isr_a(void) { }
__irq void isr_b(void) { }
__ramfunc int fast_fn(int x) { return x + 1; }
__root int kept_fn(void) { return 1; }
__weak int weak_fn(void) { return 2; }
__packed struct pk { char a; int b; };
__svc(0) int svc_fn(int x) { return x; }
int asm_fn(void) {
  __asm__ volatile ("nop");
  __attribute__((aligned(4))) static int buf;
  __asm__("nop");
  return 0;
}
