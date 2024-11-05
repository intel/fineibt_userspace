// TEST @OBJ weakstaticalias-defweak
#include <stdio.h>
#include <stdlib.h>

extern void dummy(void);

void a(void) { puts("a\n"); }

void (*fptrs[])(void) = { dummy, a };

int main(int argc, char **argv)
{
    int n = 0;
    if (argc > 1) n = atoi(argv[1]);

    dummy();

    fptrs[n]();
}
