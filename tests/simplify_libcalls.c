// TEST
#include <stdio.h>

int main(int argc, char **argv)
{
    // Rewritten to puts by LLVM IR pass "simplify-libcalls"
    printf("Hello, world!\n");
    return 0;
}
