// TEST @RETURNCODE -4
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void a(void) { puts("a\n"); }
void b(int t) { puts("b\n"); }
int c(void) { puts("c\n"); return 0; }

typedef void (*fptr_t)(void);
fptr_t fptrs[] = { a, (fptr_t)b, (fptr_t)c };

int main(int argc, char **argv)
{
    int n = 1;
    if (argc > 1) n = atoi(argv[1]);
    fptrs[n]();

    return 0;
}

