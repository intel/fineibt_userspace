// TEST @LDFLAGS -lm

#include <stdio.h>
#include <math.h>

int main(int argc, char **argv) {
    float numf = 1.0f;
    double numd = 1.0;
    long double numl = 1.0l;
    asm volatile ("":"+m"(numf),"+m"(numd),"+m"(numl)::"memory");

#define do(func) printf(#func " %f %lf %Lf\n", func ## f(numf), func(numd), func ## l(numl));
#define do2(func) printf(#func " %f %lf %Lf\n", func ## f(numf, numf), func(numd, numd), func ## l(numl, numl));

    do(sqrt);
    do(log);
    do(log2);
    do(log10);
    do(exp);
    do(exp2);
    do2(pow);
    do(sin);
    do(cos);
    do(floor);
    do(ceil);
    do(trunc);
    do(round);
    //do(roundeven);
    do2(copysign);

    return 0;
}
