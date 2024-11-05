// LIB @DISABLE_FINEIBT
#include <stdio.h>
#include <stdlib.h>

void ext_direct(void) { puts("ext_direct"); }
void ext_indirect_data(void) { puts("ext_indirect_data"); }
void ext_indirect_got(void) { puts("ext_indirect_got"); }
void ext_both(void) { puts("ext_both"); }

void ext_call(void (*fptr)(void)) { fptr(); }
