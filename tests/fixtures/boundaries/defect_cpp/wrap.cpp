extern "C" int wrap_add(int a, int b) { return a + b; }
class Calc {
public:
  int add(int a, int b);
};
int Calc::add(int a, int b) { return a + b; }
