// TEST

#include <string.h>

int main(int argc, char **argv) {
    char buf1[128], buf2[128];
    void *(*fptr)(void*,const void*,size_t) = &memcpy;
    asm volatile ("":"+m"(fptr)::"memory");
    memcpy(buf1, buf2, 128);
    memcpy(buf1, buf2, argc);
    fptr(buf1, buf2, 128);
    return 0;
}
