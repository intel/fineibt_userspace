// TEST

#include "common.h"

struct mystruct {
    long a;
    long b;
    long c;
    long d;
    long e;
    long f;
};

long func1(struct mystruct s) { return s.a; }
long func2(struct mystruct s) { return s.f; }

long (*fptrs[])(struct mystruct s) = { func1, func2 };

int main(int argc, char **argv)
{
    int n = 0;
    if (argc > 1) n = atoi(argv[1]);

    struct mystruct s = { n * 3, n * n };

    printf("oper: %ld\n", fptrs[n](s));

    return 0;
}

