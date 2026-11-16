struct dev { int (*fetch)(struct dev *); };
int fetch(struct dev *d) { return 0; }
int use(struct dev *p) { return p->fetch(p); }
