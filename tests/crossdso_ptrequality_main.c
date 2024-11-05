// TEST @LIB crossdso_ptrequality_lib1

#include "common.h"

extern void lib1_func1(void);
extern void lib1_func2(void);

extern void *lib1_get_lib1_func1_fptr(void);
extern void *lib1_get_lib1_func2_fptr(void);
extern void *lib1_get_main_func1_fptr(void);
extern void *lib1_get_main_func2_fptr(void);

void main_func1(void) { puts("main_func_1\n"); }
void main_func2(void) { puts("main_func_2\n"); }

void (*fptrs[])(void) = { main_func2, lib1_func2 };

int main(int argc, char **argv)
{
    // fptrs from perspective of main (i.e., this dso).
    void *ptr_main_main_func1 = main_func1;
    void *ptr_main_main_func2 = fptrs[0];
    void *ptr_main_lib1_func1 = lib1_func1;
    void *ptr_main_lib1_func2 = fptrs[1];

    // fptrs from perspective of lib1 dso.
    void *ptr_lib1_main_func1 = lib1_get_main_func1_fptr();
    void *ptr_lib1_main_func2 = lib1_get_main_func2_fptr();
    void *ptr_lib1_lib1_func1 = lib1_get_lib1_func1_fptr();
    void *ptr_lib1_lib1_func2 = lib1_get_lib1_func2_fptr();

    printf("From perspective of main dso:\n");
    printf(" main_func1: %p\n", ptr_main_main_func1);
    printf(" main_func2: %p\n", ptr_main_main_func2);
    printf(" lib_func1: %p\n", ptr_main_lib1_func1);
    printf(" lib_func2: %p\n", ptr_main_lib1_func2);
    printf("From perspective of lib dso:\n");
    printf(" main_func1: %p\n", ptr_lib1_main_func1);
    printf(" main_func2: %p\n", ptr_lib1_main_func2);
    printf(" lib_func1: %p\n", ptr_lib1_lib1_func1);
    printf(" lib_func2: %p\n", ptr_lib1_lib1_func2);

    assert(ptr_main_main_func1 == ptr_lib1_main_func1);
    assert(ptr_main_main_func2 == ptr_lib1_main_func2);

    assert(ptr_main_lib1_func1 == ptr_lib1_lib1_func1);
    assert(ptr_main_lib1_func2 == ptr_lib1_lib1_func2);
}
