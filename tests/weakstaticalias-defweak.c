// OBJ
#include <stdio.h>

#define weak_alias(old, new) \
        extern __typeof(old) new __attribute__((__weak__, __alias__(#old)))

static void _dummy(void)
{
    puts("weak dummy\n");
}

weak_alias(_dummy, dummy);
