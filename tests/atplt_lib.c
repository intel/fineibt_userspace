// LIB

#include "common.h"

void lib_func(void) {
    puts("lib_func\n");
}

void lib_call_func(void) {
    printf("lib_func @ %p\n", lib_func);
    lib_func();
}
