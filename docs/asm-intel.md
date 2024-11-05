# FineIBT asm snippets - Intel syntax

### Before an indirect call

    mov r11d, hash                      # 41 BB nn nn nn nn


### Stub (no global disable fallback support)

    func:
        endbr64                         # F3 0F 1E FA
        sub r11d, hash                  # 41 81 EB nn nn nn nn
        je func.nocfi                   # 0F 84 mm mm mm mm
        ud2                             # 0F 0B
        nop * 13                        #  pad from 19 to 32 bytes


### Stub (with global disable fallback support using global bit)

Use a short backward jump after checking the disable bit to keep within 32B – these two conditionals must match for that to work.

    func:
        endbr64                         # F3 0F 1E FA
        sub r11d, hash                  # 41 81 EB nn nn nn nn
    .L0:
        je func.nocfi                   # 0F 84 mm mm mm mm
        cmp byte ptr fs:0x100, 0x1      # 64 80 3C 25 00 01 00 00 01
        je .L0                          # 74 EF
        ud2                             # 0F 0B
        nop * 2                         #  pad from 30 to 32 bytes


### Stub (with global disable fallback support using IBT)

    func:
        endbr64                         # F3 0F 1E FA
        sub r11d, hash                  # 41 81 EB nn nn nn nn
        je func.nocfi                   # 0F 84 mm mm mm mm
        lea r11, [rip+func.nocfi]       # 4C 8D 1D mm mm mm mm
        jmp r11                         # 41 FF E3
        nop * 5                         #  pad from 27 to 32 bytes


### Stub (patched out at runtime)

    func:
        endbr64                         # F3 0F 1E FA
        nop dword ptr [rax+0x0]         # 0F 1F 80 00 00 00 00
        jmp func.nocfi                  # 40 E9 mm mm mm mm
        ud2                             # 0F 0B
        nop * 13                        #  pad from 19 to 32 bytes


### PLT (normal)

    func@plt:
        mov r11d, hash                  # 41 BB nn nn nn nn
        jmp [rip + func@GOT]            # FF 25 mm mm mm mm  Calls func
        nop * 4                         #  pad from 12 to 16 byte


### PLT (rewritten at runtime)

    func@plt:
        jmp func.nocfi                  # E9 mm mm mm mm
        nop * 11                        #  pad from 5 to 16 byte


### PLT (address-taken)

    func@plt.at:
        endbr64                         # F3 0F 1E FA
        sub r11d, hash                  # 41 81 EB nn nn nn nn
        je func@plt                     # 0F 84 mm mm mm mm
        ud2                             # 0F 0B
        nop * 13                        #  pad from 19 to 32 byte
