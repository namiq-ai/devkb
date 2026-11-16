#ifndef GUARDED_H
#define GUARDED_H
#ifdef __cplusplus
extern "C" {
#endif
int g_add(int a, int b);
#ifdef __cplusplus
class Hidden { public: int y; };
}
#endif
#endif
