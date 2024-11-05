// TEST @LDFLAGS -lm

#include "common.h"

#include <complex.h>

long double cabsl1(long double complex z)
{
    return cabsl(z);
}
long double cabsl2(long double complex z)
{
    return creall(z) + cimagl(z);
}

long double (*fptrs[])(long double complex) = { cabsl1, cabsl2 };

int main(int argc, char **argv)
{
    int n = 0;
    if (argc > 1) n = atoi(argv[1]);

    long double complex z = (1.0 * n) - 4.0 * I;

    printf("oper: %Lf\n", fptrs[n](z));

    return 0;
}
