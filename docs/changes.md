# FineIBT changelog

Clang:
 * Add `-mfineibt` flag
 * Define `__CET__` to 0x11
 * Use kcfi hash generation and propagation for FineIBT
 * Modify kcfi hash generation (32->31 bits)
 * Add `coarsecf_check` attribute for functions

LLVM:
 * IR pass: Stub generation: rename potential indirect targets and emit a new
   function with a tailcall to the original.
 * IR: LibFunc hashes: add hashes for any function that may be generated
   post-frontend (and thus post normal hash generation).
 * SelectionDAG: Implement kcfi hashes for Invokes
 * Machine pass: Add hash sets (`mov r11d, hash`) for indirect calls.
 * Machine pass: Rewrite stubs with hash checks (`sub`, `jne`, `ud2`)
 * Machine pass: Emit hash metadata for linker PLT generation
 * AsmPrinter: Set `GNU_PROPERTY_X86_FEATURE_1_FINEIBT`

LLD:
 * Process `GNU_PROPERTY_X86_FEATURE_1_FINEIBT`
 * Add `-zforce-fineibt` flag
 * Rewrite relocations for direct calls to `.nocfi` functions (not stub)
 * Detect aliases between different symbols
 * Emit `.dynamic` fields describing stub section entries

compiler-rt:
 * Define `__do_init` and `__do_fini` as coarsecf_check

glibc:
 * Pull in clang compatibility patches from `azanella/clang` branch
 * Support using compiler-rt instead of libgcc
 * Add `--enable-fineibt` build option
 * Build: Force IBT/FineIBT flags for manually constructed functions
 * Mark as `coarsecf_check`: `__libc_start_main`
 * Fix function types of constructors/desctructors
 * Fix function type of qsort internals

