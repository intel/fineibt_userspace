#ifndef COMMON_H
#define COMMON_H

#include <stdlib.h>
#include <stdio.h>

#define error(msg, ...) \
    do { \
        fprintf(stderr, msg "\n", ##__VA_ARGS__); \
        exit(1); \
    } while (0)

#define assert(cond) \
    do { \
        if (!(cond)) \
            error("assert failed: " #cond); \
    } while (0)

__attribute__((noinline))
static void dispatch(void (*fptr)(void)) {
    void (*volatile fptr_local)(void) = fptr;
    asm volatile ("":::"memory");
    fptr_local();
}

#endif
