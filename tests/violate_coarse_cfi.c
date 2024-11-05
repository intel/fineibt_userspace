// TEST @RETURNCODE -11
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <assert.h>


#define ARCH_X86_CET_STATUS             0x3001
#define ARCH_X86_CET_DISABLE            0x3002
#define ARCH_X86_CET_LOCK               0x3003
#define GNU_PROPERTY_X86_FEATURE_1_IBT  (1U << 0)

extern int arch_prctl(int code, unsigned long arg2);

static int get_ibt_status(void)
{
       struct {
               uint64_t status;
               uint64_t shstk_addr;
               uint64_t shstk_size;
       } status = { 0 };
       arch_prctl(ARCH_X86_CET_STATUS, (uint64_t)&status);
       return !!(status.status & GNU_PROPERTY_X86_FEATURE_1_IBT);
}

__attribute__((weak)) extern void __start_fineibt_stub;
__attribute__((weak)) extern void __stop_fineibt_stub;

__attribute__((noinline))
void targetfunc(void) {
    // Marker to scan for, so we can bypass any prologue or memory layout
    // changes.
    asm volatile("mov $0xdeadbeef,%eax");

    puts("FAIL, reached targetfunc without #CP\n");
}

void *find_targetfunc_from_stub(char *stub)
{
    assert(*(uint32_t*)(stub) == 0xfa1e0ff3); // ENDBR64
    assert(*(uint16_t*)(stub+4) == 0x8141); // REX SUB
    assert(*(uint16_t*)(stub+11) == 0x840f); // JE
    int32_t off = *(int32_t*)(stub+13); // JE <off>
    return (void*)((uint64_t)stub + off + 17);
}

int main(int argc, char **argv)
{
    printf("IBT status: %s\n", get_ibt_status() ? "enabled" : "DISABLED(!!)");

    char *ptr = (char*)targetfunc;

    if (&__start_fineibt_stub <= (void*)ptr && (void*)ptr < &__stop_fineibt_stub)
        ptr = find_targetfunc_from_stub(ptr);

    void (*target)(void) = NULL;
    unsigned i;
    for (i = 0; i < 128; i++)
        if (*(uint32_t*)(ptr + i) == 0xdeadbeef) {
            void *targetptr = ptr + i + 4;
            assert(*(uint8_t*)(targetptr - 5) == 0xb8); // MOV eax, 0xdeadbeef
            assert(*(uint32_t*)(targetptr) != 0xfa1e0ff3); // ENDBR64
            target = (void (*)(void))(targetptr);
            break;
        }
    if (!target) {
        fprintf(stderr, "Could not find targetfunc marker?!\n");
        return 1;
    }
    printf("Jumping to %p (no endbr)\n", target);
    target();

    return 0;
}
