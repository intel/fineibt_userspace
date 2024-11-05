// TEST
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    const void *dispatch_table[] = { &&do_a, &&do_b, &&do_c };

    int n = 0;
    if (argc > 1) n = atoi(argv[1]);

    goto *dispatch_table[n];

do_a:
    printf("a\n");
    return 0;
do_b:
    printf("b\n");
    return 0;
do_c:
    printf("c\n");
    return 0;
}
