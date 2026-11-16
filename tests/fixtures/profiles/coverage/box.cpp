class Box {
public:
  int get();
};
int Box::get() { return 1; }
int use_box(Box *b) { return b->get(); }
