// LIB

#include "common.h"
__attribute__((noinline))
static int func1(int a) { asm volatile (""); return a; }
__attribute__((noinline))
static int func2(int a) { return a + 1; }
__attribute__((noinline,section("dummy_section")))
static int func3(int a) { return func1(a + 2); }

static int (*fptrs[])(int) = { func1, func2, func3 };

int libfunc(int a, int b) {
    func1(1);
    return fptrs[a](b);
}
