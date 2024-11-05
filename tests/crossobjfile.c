// TEST @OBJ crossobjfile_objfile2
#include <stdio.h>
#include <stdlib.h>

extern void ext_direct(void);
extern void ext_indirect_data(void);
extern void ext_indirect_got(void);
extern void ext_both(void);

void loc(void) { puts("local\n"); }

__attribute__((noinline))
void dispatch(void (*fptr)(void)) {
    asm volatile ("":::"memory");
    fptr();
}

void (*fptrs[])(void) = { ext_indirect_data, ext_both, loc };

int main(int argc, char **argv)
{
    int n = 0;
    if (argc > 1) n = atoi(argv[1]);

    ext_direct();

    dispatch(ext_indirect_got);

    fptrs[n](); // ext_indirect_data

    ext_both();
    dispatch(ext_both);
}