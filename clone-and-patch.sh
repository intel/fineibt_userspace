#!/bin/sh
set -eu
set -x

[ -d llvm ] || git clone https://github.com/llvm/llvm-project.git llvm
cd llvm
git checkout llvmorg-18.1.1  # should be dba2a75e9c7e
git am ../patches/llvm/*.patch
git checkout -b fineibt
cd ..

[ -d glibc ] || git clone https://sourceware.org/git/glibc.git glibc
cd glibc
git checkout 1bc61cf8e0  # base for older version of azanella/clang branch
git am ../patches/glibc-clang/*.patch
git am ../patches/glibc-fineibt/*.patch
git checkout -b fineibt
cd ..

[ -d patches/linux ] || \
    git clone --depth=1 --single-branch \
    -b mainline-tracking-v5.13-yocto-210727T062416Z \
    https://github.com/intel/linux-intel-quilt.git \
    patches/linux
[ -d linux ] || git clone https://github.com/torvalds/linux.git linux
cd linux
git checkout v5.13  # should be 62fb9874f5da
git am ../patches/linux/patches/*.cet
git checkout -b fineibt
cd ..
