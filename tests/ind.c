// TEST
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void a(void) { puts("a\n"); }
void b(void) { puts("b\n"); }
void c(void) { puts("c\n"); }

void (*fptrs[])(void) = { a, b, c };

int main(int argc, char **argv)
{
    int n = 0;
    if (argc > 1) n = atoi(argv[1]);
    fptrs[n]();

    return 0;
}
