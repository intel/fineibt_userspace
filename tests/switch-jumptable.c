// TEST
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    int n = 0;
    if (argc > 1) n = atoi(argv[1]);
    int a = 0, b = 0, c = 0;
    if (argc > 2) a = atoi(argv[2]);
    if (argc > 3) b = atoi(argv[3]);
    if (argc > 4) c = atoi(argv[4]);

    switch (n) {
    case 0:
        printf("a\n");
        a += 1;
        break;
    case 1:
        printf("b\n");
        a -= 1;
        break;
    case 2:
        printf("c\n");
        b += 1;
        break;
    case 3:
        printf("d\n");
        b -= 1;
        break;
    case 4:
        printf("e\n");
        b += 7;
        break;
    case 5:
        printf("f\n");
        c += 9;
        break;
    case 6:
        printf("g\n");
        c += 7;
        break;
    case 7:
        printf("h\n");
        b += 4;
        break;
    case 8:
        printf("i\n");
        a += 4;
        break;
    case 9:
        printf("j\n");
        b += 2;
        break;
    case 10:
        printf("k\n");
        c += 2;
        break;
    }
    printf("a=%d b=%d c=%d\n", a, b, c);
    return 0;
}
