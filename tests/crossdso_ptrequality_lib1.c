// LIB
#include "common.h"

void main_func1(void);
void main_func2(void);

void lib1_func1(void) { puts("lib1_func_1\n"); }
void lib1_func2(void) { puts("lib2_func_2\n"); }

void (*lib1_fptrs[])(void) = { main_func2, lib1_func2 };

void *lib1_get_lib1_func1_fptr(void) {
    return lib1_func1;
}
void *lib1_get_lib1_func2_fptr(void) {
    return lib1_fptrs[1];
}
void *lib1_get_main_func1_fptr(void) {
    return main_func1;
}
void *lib1_get_main_func2_fptr(void) {
    return lib1_fptrs[0];
}
