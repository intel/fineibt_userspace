#!/bin/bash

# Sets up a FineIBT-enabled toolchain.

set -eu
set -x

CURDIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

LLVM="${CURDIR}/llvm"
GLIBC="${CURDIR}/glibc"
KERNEL="${CURDIR}/linux"

TOOLCHAIN_BASE="${CURDIR}/toolchains/fineibt"
BUILD="${TOOLCHAIN_BASE}/build"
# We install LLVM (clang/lld/compiler-rt) separate from the sysroot containing
# glibc, to avoid it using the new (incompatible) libc.so and crashing.
INSTALL_LLVM="${TOOLCHAIN_BASE}/llvm"
INSTALL_SYSROOT="${TOOLCHAIN_BASE}/sysroot"

build_llvm() {
    # Builds LLVM's clang and lld.
    # We install lld as default linker in this toolchain.
    # We set compiler-rt as default rtlib, but we build this separately.
    local bdir="${BUILD}/llvm"
    cmake \
        -G Ninja \
        -S "${LLVM}/llvm" \
        -B "${bdir}" \
        -DCMAKE_INSTALL_PREFIX="${INSTALL_LLVM}" \
        -DLLVM_ENABLE_PROJECTS="clang;lld" \
        -DLLVM_TARGETS_TO_BUILD=X86 \
        -DCMAKE_BUILD_TYPE=Release \
        -DLLVM_ENABLE_ASSERTIONS=ON \
        -DCLANG_DEFAULT_RTLIB=compiler-rt \
        -DLLVM_ENABLE_LTO=OFF \
        -DLLVM_USE_LINKER=lld \
        -DLLVM_PARALLEL_LINK_JOBS=8 \
        -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
    cmake --build "${bdir}"
    cmake --install "${bdir}"
    ln -s "${INSTALL_LLVM}/bin/ld.lld" "${INSTALL_LLVM}/bin/ld"
}

build_crt() {
    # Build compiler-rt with the custom clang/lld.
    # To avoid circular dependencies, we must build this compiler-rt explicitly
    # with libgcc.

    # TODO change CXX flags when FineIBT supports C++: -DCMAKE_CXX_FLAGS="--rtlib=libgcc -Wl,-znow -Wl,-z,force-ibt,-z,force-fineibt -fcf-protection=branch -mfineibt" \

    local bdir="${BUILD}/compiler-rt"
    cmake \
        -G Ninja \
        -S "${LLVM}/compiler-rt" \
        -B "${bdir}" \
        -DCMAKE_INSTALL_PREFIX="${INSTALL_LLVM}/lib/clang/18" \
        -DCMAKE_BUILD_TYPE=Release \
        -DLLVM_CONFIG_PATH="${INSTALL_LLVM}/bin/llvm-config" \
        -DCMAKE_C_COMPILER="${INSTALL_LLVM}/bin/clang" \
        -DCMAKE_CXX_COMPILER="${INSTALL_LLVM}/bin/clang++" \
        -DCMAKE_C_FLAGS="--rtlib=libgcc -Wl,-znow -Wl,-z,force-ibt,-z,force-fineibt -fcf-protection=branch -mfineibt" \
        -DCMAKE_CXX_FLAGS="--rtlib=libgcc -Wl,-znow -Wl,-z,force-ibt,-z,force-fineibt" \
        -DCOMPILER_RT_BUILD_SANITIZERS=OFF \
        -DCOMPILER_RT_BUILD_XRAY=OFF \
        -DCOMPILER_RT_BUILD_LIBFUZZER=OFF \
        -DCOMPILER_RT_BUILD_PROFILE=OFF \
        -DCOMPILER_RT_CRT_USE_EH_FRAME_REGISTRY=OFF
    cmake --build "${bdir}"
    cmake --install "${bdir}"
}

build_libunwind() {
    # Build libunwind with the custom clang/lld.

    local bdir="${BUILD}/libunwind"
    cmake \
        -G Ninja \
        -S "${LLVM}/runtimes" \
        -B "${bdir}" \
        -DLLVM_ENABLE_RUNTIMES="libunwind" \
        -DCMAKE_INSTALL_PREFIX="${INSTALL_LLVM}/lib/clang/18" \
        -DCMAKE_BUILD_TYPE=Release \
        -DLLVM_CONFIG_PATH="${INSTALL_LLVM}/bin/llvm-config" \
        -DCMAKE_C_COMPILER="${INSTALL_LLVM}/bin/clang" \
        -DCMAKE_CXX_COMPILER="${INSTALL_LLVM}/bin/clang++" \
        -DCMAKE_C_FLAGS="-Wl,-znow -Wl,-z,force-ibt,-z,force-fineibt -fcf-protection=branch -mfineibt" \
        -DCMAKE_CXX_FLAGS="-Wl,-znow -Wl,-z,force-ibt,-z,force-fineibt"
    cmake --build "${bdir}"
    cmake --install "${bdir}"
}

build_glibc() {
    # Build glibc with custom clang/lld/compiler-rt
    local bdir="${BUILD}/glibc"
    mkdir -p "$bdir"
    pushd "$bdir"

    # glibc wants prefix="" and specifying DESTDIR in make install instead.
    ${GLIBC}/configure \
        CC="${INSTALL_LLVM}/bin/clang" \
        CXX="${INSTALL_LLVM}/bin/clang++" \
        CFLAGS="-O2 -ggdb" \
        --enable-bind-now \
        --enable-cet \
        --enable-fineibt \
        --prefix=
    make -j`nproc`
    make -j`nproc` install DESTDIR="${INSTALL_SYSROOT}"

    popd
}

install_kernel_headers() {
    pushd "${KERNEL}"

    if [ ! -f "${KERNEL}/.config" ]; then
        echo "Linux was not configured, please run ./build-kernel.sh"
        exit 1
    fi
    make headers_install INSTALL_HDR_PATH="${INSTALL_SYSROOT}"

    popd
}

install_configs() {
    # Install clang config files with default flags to use our toolchain.
    RTDIR=$(${INSTALL_LLVM}/bin/clang --print-resource-dir)
    cat >${INSTALL_LLVM}/bin/clang.cfg <<EOF
# Enable FineIBT by default
-fcf-protection=branch -mfineibt
-Wl,-znow
-Wl,-zforce-ibt -Wl,-zforce-fineibt

# Use binaries from toolchain
-B${INSTALL_LLVM}/bin

# Use includes and libraries relative to toolchain
--sysroot=${INSTALL_SYSROOT}

# Configure include paths
-nostdinc
-isystem ${INSTALL_SYSROOT}/include
# Compiler-rt (path depends on LLVM version)
-isystem ${RTDIR}/include

# At runtime, search for libraries (e.g., libc.so) in toolchain
-Wl,-rpath=${INSTALL_SYSROOT}/lib

# Search for libraries from compiler runtimes (e.g., libunwind)
-L${RTDIR}/lib
-Wl,-rpath=${RTDIR}/lib

# Use the loader from our own libc.
-Wl,--dynamic-linker=${INSTALL_SYSROOT}/lib/ld-linux-x86-64.so.2
EOF

}

rm -rf "${INSTALL_LLVM}" "${INSTALL_SYSROOT}"

echo "Setting up toolchain..."
echo " toolchain dir: ${TOOLCHAIN_BASE}"

echo "Building LLVM..."
build_llvm
echo "Building compiler-rt..."
build_crt
echo "Building libunwind..."
build_libunwind
echo "Building glibc..."
build_glibc
echo "Installing kernel headers..."
install_kernel_headers
echo "Installing compiler configs..."
install_configs
