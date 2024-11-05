// TEST @CFLAGS -fexceptions

#include <stdio.h>

void indirect_func(void) { }
void (*fptrs[])(void) = { indirect_func };

void cleanupfunc (int *p) { }

int main(void) {
    // Defining a variable with cleanup func will result in all calls later on
    // to become invokes, so that the cleanup runs even if the call causes an
    // exception.
    int var_with_cleanup __attribute__((cleanup (cleanupfunc))) = (0);

    fptrs[0]();
}
