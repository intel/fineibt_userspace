# Userspace FineIBT prototype

FineIBT is an enhancement for Intel IBT, that enables fine-grained control flow
integrity (CFI) at high efficiency. Through automatic compiler instrumentation,
existing (C/C++) programs can be hardened against exploits.

This repository contains design documents, toolchain patches, and tests for
enabling FineIBT in userspace. The patches and tools in this repository are for
research purposes only: this is not a final product, and we do not provide
additional support.


# Building

Install the dependencies:

    sudo apt install python3-pip build-essential cmake ninja-build flex bison \
        pahole libncurses-dev flex libssl-dev libelf-dev
    pip3 install iced-x86 pyelftools xxhash

Use the following script to clone upstream versions of llvm, glibc and linux,
and to apply the FineIBT patches on top (required before building toolchains):

    ./clone-and-patch.sh

To set up toolchains:

    ./build-kernel.sh       # Linux headers required for toolchains
    ./build-toolchain-baseline.sh
    ./build-toolchain-fineibt.sh

This builds and installs the respective toolchains under the `toolchains/`
directory. The toolchains include a `clang.cfg` to use the correct libraries and
flags. For example, running `toolchains/fineibt/llvm/bin/clang` will
automatically use the custom glibc and will enable FineIBT flags.

To run the tests, use:

    ./run_tests.py -t fineibt  # baseline, fineibt, or path to bin dir of llvm


# IBT support

FineIBT requires IBT support from the hardware, kernel, and toolchain. This
repository uses an **old** version of IBT support, using the 5.13 kernel with an
old version of the userspace IBT patches. These patches enable IBT automatically
for processes that have the IBT ELF bit set.

These patches are fetched from:
https://github.com/intel/linux-intel-quilt/tree/mainline-tracking-v5.13-yocto-210727T062416Z

In the future, both the kernel and glibc should use the latest IBT patches.


# Glibc Clang support

Upstream glibc does not support compilation with clang. For this, we base our
work on the `azanella/clang` branch (available in the glibc upstream git).
Our glibc patches do not track upstream rebases of this branch, and may thus use
an out-of-date patchset with commits no longer available upstream.

