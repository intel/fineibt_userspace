// TEST
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

__attribute__((noinline))
static void ind_only(void) { asm volatile(""); }
__attribute__((noinline))
static void ind_direct(void) { asm volatile(""); }
__attribute__((noinline))
static void direct_only(void) { asm volatile(""); }

void (*fptrs[])(void) = { ind_only, ind_direct };

int main(int argc, char **argv)
{
    int n = 0;
    if (argc > 1) n = atoi(argv[1]);
    fptrs[n]();

    ind_direct();
    direct_only();

    return 0;
}
