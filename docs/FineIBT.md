# User-space FineIBT proposal

* **Date:** 2023-10-04
* **Authors:** Koen Koning (koen.koning@intel.com), João Moreira (joao.moreira@intel.com), Stephen Röttger (sroettger@google.com)

This document is a proposal for a user-space FineIBT design. FineIBT is
a fine-grained control flow integrity (CFI) scheme and is a software-only
enhancement to the existing hardware-based indirect branch tracking (IBT)
feature. FineIBT instrumentation is automatically inserted during compilation
and imposes minimal additional overhead.  FineIBT's core design has proven
effective at preventing control-flow hijacking and is already deployed within
the Linux kernel.

In this document, we adapt the FineIBT design to user-space (64-bit Linux)
applications. The primary challenge here is compatibility: user-space programs
typically use multiple separate (and independently maintained and compiled)
shared libraries.
This document splits up user-space FineIBT into several components, with a core
FineIBT design, and several additional proposals for enhancements to both
compatibility and security.

This proposal is based on the following work on FineIBT:

* [Hardware-Assisted Fine-Grained Control-Flow Integrity: Adding Lasers to Intel's CET/IBT](https://static.sched.com/hosted_files/lssna2021/8f/LSS_FINEIBT_JOAOMOREIRA.pdf), Linux Security Summit 2021 by João Moreira
* [FineIBT: Fine-grain Control-flow Enforcement with Indirect Branch Tracking](https://arxiv.org/abs/2303.16353), March'23 by Alexander Gaidis et al. (To appear at RAID'23)
* [Limit FineIBT to Address-Taken Functions](https://docs.google.com/document/d/1tdqgyNIF6QVVOxrgrKXyOdDdb4wzeIB5Xrj2hgTZ5pc/edit?resourcekey=0-JZVCUDPMfZ1cdY_c2-qXFA), Google draft proposal Nov'22 by Stephen Röttger and João Moreira:

This document uses the AT&T syntax for assembly listings. For corresponding
Intel syntax listings, see ``asm-intel.md``.

## IBT

FineIBT is a software-extension of Intel IBT (Indirect Branch Tracking). IBT is
a hardware-enforced coarse-grained CFI scheme first available on Intel
processors in 2020. IBT ensures that indirect branches (i.e., indirect jumps and
indirect calls) can only transfer control to a list of predetermined locations.
These locations are marked with endbranch (``endbr64``) instructions inside the
code itself, and act as nop instructions otherwise. This prevents an attacker
from escalating arbitrary memory corruption bug into arbitrary code execution.
If an indirect branch targets a location that is not an endbranch instruction,
the CPU raises a #CP fault.

This scheme is coarse-grained: any indirect branch can jump to any function, or
other location, marked with an endbranch (e.g., an attacker can overwrite any
function pointer to execute ``system()``).

For more details on the IBT implementation on Linux, see this
[talk by H.J. Lu from August 2020](https://lpc.events/event/7/contributions/729/attachments/496/903/CET-LPC-2020.pdf).
User-space IBT support is currently work-in-progress: it is supported by all
major compilers and linkers and support is available within glibc, but kernel
support has not yet been upstreamed.

## FineIBT

FineIBT builds on top of IBT checks and adds a more fine-grained CFI scheme.
Every indirect call site, and every callee (i.e., locations marked with
endbranch) is assigned a hash at compile-time. A branch is only considered valid
if the hashes on both sides match. FineIBT calculates these hashes based on the
function signature (i.e., return type and argument types).

The automatically inserted instrumentation for FineIBT looks as follows:

    # Caller
    caller_func:
        ...
        mov $hash, %r11d        # FineIBT: Set hash
        call *%rax
        ...

    # Newly-inserted callee
    func:
        endbr64                 # IBT: Mark as valid target
        sub $hash1, %r11d       # FineIBT: Check hash
        je func.nocfi           # FineIBT: If match, continue
        ud2                     # FineIBT: If mismatch, error

    # Original callee
    func.nocfi:
        ...

The caller places a hash in the ``r11`` register, which the ``sub-je`` pair in
the callee verifies. If the hash mismatches, the check fails and the ``ud2``
instruction aborts execution.

FineIBT in the Linux kernel places the FineIBT hash check directly in front of
the original function (i.e., in the function prologue) using its run-time
code-rewriting mechanism. User-space FineIBT, on the other hand, places this
code separately (i.e., in a stub) and relies on compile-time instrumentation.

FineIBT is secure, i.e., for every indirect branch fine-grained CFI is enforced,
because of the combination of two properties:

 * IBT: Every indirect call _must_ target an endbranch.
 * FineIBT: Every endbranch _must_ be instrumented with a FineIBT hash check.

FineIBT offers benefits over other existing fine-grained CFI solutions, such as
Clang-CFI, while having comparable (minimal) overhead. In particular, FineIBT:

* Does not require LTO compilation.
* Efficiently deals with separate DSOs (i.e., shared libraries).
* Offers a higher degree of protection against speculative execution attacks.

For the proposed design outlined in this document, we focus solely on 64-bit ELF
applications and libraries.

Our current proposal for user-space FineIBT imposes the limitation that only
eager binding in the loader is supported (i.e., no lazy binding). This
limitation is not fundamental and may be addressable later, if this poses
a problem for deployment.

This proposal utilizes (load-time) binary rewriting as an optimization or
enhancement for several aspects of the design. For scenarios where this is not
possible (e.g., system call filters being in place for security, such as with
SELinux), fallback mechanisms are provided (although these may be less
efficient).


## User-space FineIBT

Our user-space FineIBT proposal is split up in 4 separate components:

1. **FineIBT core**
   * Call-site instrumentation, callee instrumentation (stub generation), hash
     generation, relocation rewriting, PLT generation.
   * Includes ABI changes (new PLT format).
   * Compatibility **strict mode**: all libraries must be FineIBT-enabled,
     otherwise loading fails with an error.
2. **C++** support and security.
   * Exceptions: Support C++ exceptions with specialized hashes.
   * Virtual calls: Utilize different hashes and checks to provide type-safety
     for C++ virtual function calls.
3. **Global Disable Mode**: Compatibility with non-FineIBT libraries.
   * When a non-FineIBT DSO is loaded, FineIBT enforcement is disabled for all
     components to preserve compatibility.
4. **Target reduction**: Enhance security by reducing set of valid targets.
   * After loading, all symbols not indirectly called by any of the libraries
     are eliminated as valid targets for indirect branches.


## FineIBT core

### Hash generation

FineIBT uses a type-based, 31-bit, hash value to enforce its fine-grained CFI.
By using the function type (i.e., a combination of a function's return type and
argument types), hashes are stable across different compilation units and shared
objects.

For this, FineIBT uses a similar type generation as is used by kCFI. These
hashes are obtained by a (Itanium C++ ABI) mangled string of the type, hashing
it through ``xxHash64``, and truncating the result to the lower 31 bit.

FineIBT hashes only use 31 bits out of the available 32 bits. This allows the
target program to use FineIBT for any generated code (e.g., JITed code) with its
own namespace for hashes.

For C++ virtual methods the constant string ``".vcall"`` is appended to the
mangled type string before being hashed. For more details, refer to the "Virtual
Call Protection" section later in this document.

    suffix = is_virtual_method ? ".vcall" : "";
    mask = (1ul << 31) - 1;  // Lower 31 bits
    hash = xxHash64(cxxmangle(function_type) + suffix) & mask;

For cross-language compatibility, other languages should implement a type
mapping, and then use the Itanium C++ ABI mangling as described above. For
a discussion on Rust compatibility, see the
[Rust CFI design doc](https://rcvalle.com/docs/rust-cfi-design-doc.pdf).

### Caller instrumentation

Preceding every indirect branch (indirect call, indirect jmp) the following
instructions are generated:

    mov $hash, %r11d    # 41 BB nn nn nn nn

Every indirect call is rewritten to target the newly-inserted FineIBT stub
(``func``; see below).
Every direct call _to an instrumented function_ is rewritten to target the
original (renamed) function (``func.nocfi``; see below).

### Callee instrumentation

For every potential indirect call target (i.e., exported or address-taken
function), the following happens:

1. Rename the symbol from ``func`` to ``func.nocfi``. The function prologue
   itself is unchanged and does not have an endbranch instruction.
2. Insert a new symbol named ``func`` in the ``.fineibt.stub`` section, which
   serves as the new target of indirect calls to ``func``. This stub has an
   endbranch, FineIBT hash check, and direct call to ``func.nocfi``.

Specifically, the stub contains the following instructions:

    func:
        endbr64             # F3 0F 1E FA
        sub $hash, %r11d    # 41 81 EB nn nn nn nn
        je func.nocfi       # 0F 84 mm mm mm mm
        ud2                 # 0F 0B
        nop * 13            #  pad from 19 to 32 bytes

In contrast to the FineIBT implementation in the Linux kernel, user-space
FineIBT does not use function prologues, but separate stubs instead. This is
mainly for the purposes of binary rewriting (see global disable mode and target
reduction). Another advantage is little interference with the original code
locality, where most code is executed using direct calls. Downsides of this
approach are a hit on locality for code using indirect branches, and a slightly
larger FineIBT check code (since a larger offset must be encoded in the branch
instructions).

``r11`` is chosen because it is the only available register marked as
caller-save in the AMD64 ABI, allowing the instrumentation to clobber it without
issue. This differs from Linux kernel mode FineIBT, which uses ``r10`` instead:
the kernel uses ``r11`` for holding function pointers, whereas user space uses
``r10`` already for static chain pointers.

The ``sub-je`` pair of instructions are chosen because of macro-op fusion, and
that ``sub`` is a destructive operation (i.e., does not leak the hash beyond the
FineIBT check).

The ``ud2`` instruction is used for throwing an error, similar to
``__builtin_trap()``. Its execution triggers a ``SIGILL``, which can be caught
with a signal handler for additional debug information if required.

FineIBT instrumented is suppressed for functions marked with
``__attribute__((nocf_check))``. Such functions can never be called indirectly.

### Symbols and relocations

For every function that can be indirectly called (and thus has a FineIBT stub),
two symbols are generated:

* ``func.nocfi`` The original function entry (no endbranch or FineIBT check)
* ``func`` The new function entry (with both endbranch and FineIBT check).
  This symbol is placed in the ``fineibt.stubs`` section.

We distinguish two cases: symbols with internal linkage (i.e., that are local to
the translation unit; e.g., ``static`` in C) and symbols with external linkage
(i.e., visible to other translation units, and may be overridden by symbols with
the same name from other DSOs).

FineIBT preserves address equality of symbols accross DSOs.

#### Internal linkage

For symbols with internal linkage, the compiler handles all references to these
symbols (i.e., these symbols are already resolved by the time a ``.o`` object
file is produced). For FineIBT, the compiler should:

* For direct calls, refer to ``func.nocfi``.
* For address-take operations, refer to ``func``.

#### External linkage

For symbols with external linkage, the compiler emits relocations that are
handled by the linker.
For FineIBT, all relocations should target the ``func`` symbol. This will ensure
all indirect references through the GOT are protected.

For relocations on direct calls (i.e., ``R_X86_64_PLT32``) the linker either
rewrites the call with the correct function address (if the symbol was found in
one of the input files of the linker), or generates a PLT entry (if the symbol
was not found and requires dynamic linking).

For the former case where no PLT entry is needed, the linker should rewrite the
call to the ``func.nocfi`` variant, even though the relocation targets ``func``.
Typically, the linker obtains the target for this rewrite by appending
``.nocfi`` to the symbol name. An exception is aliases, e.g., where
``aliasfunc`` is an alias for ``func``. For this case the relocation should be
rewritten to ``func.nocfi``, not ``aliasfunc.nocfi``. If a ``.nocfi`` variant
does not exist for a given symbol, the linker should check if a ``.nocfi``
variant exists for any alias symbol (i.e., any symbol pointing to the same
address).

### PLT format

FineIBT requires a modified PLT layout. FineIBT currently only supports **eager
binding**, due to complexity of (securely) supporting lazy binding. Therefore,
FineIBT should enforce eager binding during linking (``-Wl,-znow``) or during
loading (``LD_BIND_NOW=1``). Enabling FineIBT can automatically enable eager
binding, or an implementation may decide to throw an error if eager binding is
not explicitly enabled. In the future, lazy binding may be supported.

The basic format of a FineIBT PLT entry is as follows:

    func@plt:
        mov $hash, %r11d        # 41 BB nn nn nn nn
        jmpq *func@GOT(%rip)    # FF 25 mm mm mm mm   Calls func
        int3 * 4                #  pad from 12 to 16 byte

As an optimization, the loader can use run-time binary rewriting to the
following format, as outlined in [recent x86-64 psABI changes](https://gitlab.com/x86-psABIs/x86-64-ABI/-/merge_requests/50)
(unrelated to FineIBT):

    func@plt:
        jmp func.nocfi          # E9 nn nn nn nn
        int3 * 11               #  pad from 5 to 16 byte

This method has two advantages: less overhead by skipping the FineIBT
instrumentation, and reduced speculation due to the removal of the indirect
branch.

PLT-entries can be address-taken within position-dependent (i.e., ``-fno-pic``)
code. For such address-taken PLT entries, FineIBT requires a separate PLT entry
in addition to the above normal PLT entry. This entry has the following format:

    func@plt.at:
        endbr64                 # F3 0F 1E FA
        sub $hash, %r11d        # 41 81 EB nn nn nn nn
        je func@plt             # 0F 84 mm mm mm mm
        ud2                     # 0F 0B
        int3 * 13               #  pad from 19 to 32 byte

The linker can recognize this by ``R_X86_64_32(S)`` relocations targeting
``func``, which would normally point to the same PLT entry as generated by
``R_X86_64_PLT32`` (or would generate a PLT entry on its own if no such
relocation exists).

#### Hash information for linker

PLT entries are generated by the linker, but the linker lacks the information to
generate the FineIBT hash that is part of the PLT code. Therefore, the compiler
is expected to provide this information inside a separate section of the object
file. The ``.fineibt.hashinfo`` section contains a hash for every symbol that
might require a PLT entry, and is discarded by the linker (i.e., not part of the
final linked object).

Each entry is 8 bytes and is pointed to by the name of the symbol (e.g.,
``func``) prefixed by ``__fineibt_hash_`` (e.g., ``__fineibt_hash_func``). The
hash itself is stored in the _last_ 4 bytes of each entry; the first 4 bytes of
each entry should be ignored. This allows for better debuggability with existing
tools such as ``objdump``. As an example of such a section:

    Disassembly of section .fineibt.hashinfo:
    0000000000000000 <__fineibt_hash_puts>:
        0f 1f 00                nopl   (%rax)
        b8 61 e8 05 36          mov    0x3605e861,%eax

    0000000000000008 <__fineibt_hash_strtol>:
        0f 1f 00                nopl   (%rax)
        b8 73 e5 c8 4c          mov    0x4cc8e573,%eax

Here, ``puts`` has the hash ``0x3605e861``, stored in the last four bytes of
``__fineibt_hash_puts`` (at address 4, in little endian). The ``0f 1f 00 b8``
bytes (``nop`` and ``mov imm32,%eax``) are ignored and never executed, and only
present for readable debug output.

### Special cases

In some cases, indirect control flow is generated that is not compatible with
the normal FineIBT design and its hash generation. Because of IBT enforcement,
the destinations of these constructs must have an endbranch instruction. To
preserve the security guarantees of FineIBT as much as possible, a specialized
hash is used to limit these cases where possible.

#### Coarse CFI

For compatibility reasons, a programmer may mark a function as "coarse", i.e.,
for it to not have fine-grained CFI enforcement. This is done by attaching the
following attribute to a function: ``__attribute__((coarsecf_check))``. The
compiler still generates a stub for coarse functions but does not insert a hash
check.

Usage of this attribute introduces **unprotected** endbranches in the code, and
it is the responsibility of the programmer to assess the risk of leaving such
gaps in the fine-grained control flow protection.

#### Setjmp/longjmp

The ``longjmp`` function uses an indirect jump to transfer control to the
``setjmp`` location (i.e., the instruction after the call to ``setjmp``), and
must receive an endbranch. As a protection, an inline-FineIBT check is emitted
after this endbranch that enforces a hash of ``0x40000002`` is present.
A FineIBT-compatible ``setjmp`` implementation should not clobber ``r11`` and
``longjmp`` should load this static hash value in ``r11`` before its jump.

        ...
        mov $0x40000002, %r11d
        call setjmp
        endbr64
        sub $0x40000002, %r11d
        je 1f
        ud2
    1:
        ...

#### Address-taken labels and computed goto

If labels (i.e., arbitrary basic blocks) have their address taken, an endbranch
is inserted alone with an inline FineIBT check for hash ``0x40000003``. Any
computed goto will set this hash value before jumping. Any direct control flow
to an address-taken label should bypass the FineIBT check. Any use other than
using computed goto's to jump directly to address-taken labels is
**unsupported**.

        # void *tbl[] = { &&do_a, &&do_b };
        ...
        mov $0x40000003, %r11d
        jmp *(%rcx,%rax,8)  # goto *tbl[n]
        ...

        ...
        jmp do_a.nocfi  # Optional, for fall-through control flow
    do_a:
        endbr64
        sub $0x40000003, %r11d
        je do_a.nocfi
        ud2
    do_a.nocfi:
        ...


## C++ Support and Security

### Exceptions

With IBT enabled, an endbranch must normally be placed at every C++ exception
landing pad.  To reduce large amounts of inline FineIBT instrumentation for
every endbranch, we instead propose to use an indirect jump with ``notrack``
prefix inside the C++ unwinder. Since its targets are normally landing pads
coming from read-only binary data, this should not pose a security risk,
although further study is required.

Note that this would break IBT in the case a non-FineIBT (i.e., IBT-only)
unwinder is used. In this case IBT *must* be disabled well to preserve
compatibility.

### C++ Virtual Call Protection

In C++ code, calls to virtual methods of objects are implemented via indirect
calls, where the function pointer is read from the object's vtable. Every object
has a pointer to the class' vtable, where for that specific class function
pointers are stored to every virtual method. These function pointers can point
to virtual methods of the class itself, or to that of a parent class (if they
are not overridden). A call such as ``b->foo(arg)`` is translated to the
following indirect call: ``b->_vtable[FOO_OFFSET](b, arg)``.

This can be exploited by attackers in one of the following manners:

1. Corrupt the vtable pointer in an object. Note that the vtable itself resides
   in read-only memory and cannot be corrupted.
2. Leverage a type-confusion bug to pass an object outside of the intended type
   hierarchy.

FineIBT itself only provides basic protection for C++ virtual method calls.
Normal FineIBT hash checks are emitted for virtual method, with a minor change
in the hash, where a ``".vcall"`` suffix is added to the mangled type:

    hash = xxHash64(cxxmangle(function_type) + ".vcall") & mask

The addition of this suffix ensures virtual method call sites can only call
virtual methods, and normal function pointers cannot.

This mechanism does not protect against type confusion, i.e., it does not check
whether the object belongs to the type hierarchy of the method. For this,
``clang-cfi-vcall`` must still be used, but combining this with FineIBT allows
for optimizations: instead of performing the checks at the call site, the checks
can now be performed in the callee, reducing code size impact from checks. For
this check, inserting a ``llvm.type.test`` call at the start of the function is
sufficient. Note that this does require building with LTO.


## Global Disable Mode

To achieve compatibility with non-FineIBT DSOs, global disable mode disables
enforcement of FineIBT checks globally (across all DSOs). This disabling
operation typically happens during the startup of the process, when all linked
shared objects are loaded. However, a ``dlopen()`` operation at runtime may also
require disabling of FineIBT.

Disabling FineIBT can be considered separate from disabling IBT. While a non-IBT
DSO cannot have FineIBT support, a non-FineIBT DSO could still have IBT support.
Whether it is worth considering these two separately in practice is yet to be
determined.

To reduce runtime overhead (both with FineIBT enabled and disabled), global
disable mode is implemented by removing FineIBT checks altogether. This is
achieved by overwriting existing checks, effectively replacing the check with
a direct jump to the function's implementation. This overwriting can either be
achieved through binary rewriting (replacing the opcode bytes in-place), or by
generating new FineIBT stubs in separate pages, and replacing the virtual
mappings.

The FineIBT stubs when FineIBT is disabled have the following format:

    func:
        endbr64             # F3 0F 1E FA
        nopl 0x0(%rax)      # 0F 1F 80 00 00 00 00
        jmp func.nocfi      # 40 E9 mm mm mm mm
        ud2                 # 0F 0B
        nop * 13            #  pad from 19 to 32 byte

The ``endbr64`` is kept intact to allow for disabling IBT and FineIBT
separately. The ``sub`` is replaced by a nop of the same size. The conditional
jump is replaced by an unconditional jump (with an empty REX prefix to preserve
padding). This sequence should ensure execution of stubs concurrent to patching
behaves correctly.

### Non-rewriting compatibility

In some cases rewriting the stub code may not be possible, such as with SELinux
security filters in place. To allow global disable mode to work in such
circumstances, one of the two following stub formats can be used. Both introduce
some additional overhead for indirect calls in disabled mode, but note that in
most cases they are patched out as described above.

Using a global disable bit (which must be write-protected):

    func:
        endbr64                 # F3 0F 1E FA
        sub $hash, %r11d        # 41 81 EB nn nn nn nn
    1:
        je func.nocfi           # 0F 84 mm mm mm mm
        cmpb $0x1, %fs:0x100    # 64 80 3C 25 00 01 00 00 01
        je 1b                   # 74 EF
        ud2                     # 0F 0B
        nop * 2                 #  pad from 30 to 32 bytes

Coupling FineIBT to IBT (i.e., disabling FineIBT requires disabling IBT as
well):

    func:
        endbr64                     # F3 0F 1E FA
        sub $hash, %r11d            # 41 81 EB nn nn nn nn
        je func.nocfi               # 0F 84 mm mm mm mm
        lea func.nocfi(%rip), %r11  # 4C 8D 1D mm mm mm mm
        jmp *%r11                   # 41 FF E3
        int3 * 5                    #  pad from 27 to 32 bytes


## Target Reduction

In the design described so far, a FineIBT-stub must be generated for any
function that _may_ have its address taken. This includes any symbol with an
external linkage, even if such symbols are never used in practice. This can
become especially problematic with large generic libraries such as the
C library. Since, for example, the ``system()`` function has external linkage
and thus may have its address taken, it must be considered a valid FineIBT
target. This is problematic because, even if the majority of programs do not use
this function, it is an ideal function for an attacker to utilize.  While
FineIBT's fine-grained CFI is of course still enforced, this significantly
increases the set of functions sharing a hash, and thus increases the potential
for an attacker to find a valid gadget despite CFI.

The goal of the target reduction component (also known as *NOPout* in previous
literature) is thus to minimize the functions that are valid indirect branch
targets, based on their actual usage. This is only possible at runtime, when all
libraries have been loaded. At this point, the loader can check the symbols
referenced by all libraries and eliminate FineIBT stubs for all functions that
are not referenced. For this, the loader must dynamically generate or rewrite
code.

If a function is disabled, the stub code is rewritten to omit the endbranch. The
other instructions (i.e., the hash check) are left as-is, to allow restoring
this entry as a valid target later without needing to store the hash externally.

    func:
        nop                 # 0F 1F 40 00
        sub $hash, %r11d    # 41 81 EB nn nn nn nn
        je func.nocfi       # 0F 84 mm mm mm mm
        ud2                 # 0F 0B
        nop * 13            #  pad from 19 to 32 byte

### dlopen

An application can dynamically load another library at runtime, which may
reference functions that may have previously been eliminated. Therefore, upon
a ``dlopen`` call, indirection stubs may need to be updated to become valid
targets again (i.e., add back the endbranch).

Additionally, target reduction is applied to the functions in the newly loaded
library, eliminating all functions as valid targets until they are explicitly
used by ``dlsym``.

### dlsym

An application may obtain the address of any globally visible symbol with
a ``dlsym`` call. This may include symbols that were previously invalidated. To
maintain compatibility, the use of ``dlsym`` must add back the endbranch in
order to allow this function pointer to be used.

This theoretically allows an attacker to bypass the target reduction, if the
attacker has access to a ``dlsym`` gadget with arbitrary arguments. Since this
will be difficult or impossible in most applications, this should not harm the
security of target reduction in the common case.
