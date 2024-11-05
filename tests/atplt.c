// TEST @LIB atplt_lib @CFLAGS -fno-PIC @LDFLAGS -no-pie

#include "common.h"

extern void lib_func(void);
extern void lib_call_func(void);

void (*volatile fptr)(void) = &lib_func;

int main(int argc, char **argv)
{
    printf("lib_func @ %p\n", lib_func);
    lib_func();
    dispatch(lib_func);
    lib_call_func();
}
