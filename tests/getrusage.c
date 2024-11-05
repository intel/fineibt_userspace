// TEST
#include <stdio.h>
#include <sys/resource.h>

int main(int argc, char **argv)
{
    struct rusage u;
    getrusage(RUSAGE_SELF, &u);
    printf("maxrss: %ld\n", u.ru_maxrss);
    return 0;
}
