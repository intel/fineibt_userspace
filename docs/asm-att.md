# FineIBT asm snippets - AT&T syntax

### Before an indirect call

    mov $hash, %r11d                    # 41 BB nn nn nn nn


### Stub (no global disable fallback support)

    func:
        endbr64                         # F3 0F 1E FA
        sub $hash, %r11d                # 41 81 EB nn nn nn nn
        je func.nocfi                   # 0F 84 mm mm mm mm
        ud2                             # 0F 0B
        nop * 13                        #  pad from 19 to 32 bytes


### Stub (with global disable fallback support using global bit)

Use a short backward jump after checking the disable bit to keep within 32B – these two conditionals must match for that to work.

    func:
        endbr64                         # F3 0F 1E FA
        sub $hash, %r11d                # 41 81 EB nn nn nn nn
    1:
        je func.nocfi                   # 0F 84 mm mm mm mm
        cmpb $0x1, %fs:0x100            # 64 80 3C 25 00 01 00 00 01
        je 1b                           # 74 EF
        ud2                             # 0F 0B
        nop * 2                         #  pad from 30 to 32 bytes


### Stub (with global disable fallback support using IBT)

    func:
        endbr64                         # F3 0F 1E FA
        sub $hash, %r11d                # 41 81 EB nn nn nn nn
        je func.nocfi                   # 0F 84 mm mm mm mm
        lea func.nocfi(%rip), %r11      # 4C 8D 1D mm mm mm mm
        jmp *%r11                       # 41 FF E3
        nop * 5                         #  pad from 27 to 32 bytes


### Stub (patched out at runtime)

    func:
        endbr64                         # F3 0F 1E FA
        nopl 0x0(%rax)                  # 0F 1F 80 00 00 00 00
        jmp func.nocfi                  # 40 E9 mm mm mm mm
        ud2                             # 0F 0B
        nop * 13                        #  pad from 19 to 32 bytes


### PLT (normal)

    func@plt:
        mov $hash, %r11d                # 41 BB nn nn nn nn
        jmp *func@GOT(%rip)             # FF 25 mm mm mm mm  Calls func
        nop * 4                         #  pad from 12 to 16 byte


### PLT (rewritten at runtime)

    func@plt:
        jmp func.nocfi                  # E9 mm mm mm mm
        nop * 11                        #  pad from 5 to 16 byte


### PLT (address-taken)

    func@plt.at:
        endbr64                         # F3 0F 1E FA
        sub $hash, %r11d                # 41 81 EB nn nn nn nn
        je func@plt                     # 0F 84 mm mm mm mm
        ud2                             # 0F 0B
        nop * 13                        #  pad from 19 to 32 byte
