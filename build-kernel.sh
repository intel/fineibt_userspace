#!/bin/bash

# Configures and builds the Linux kernel with IBT patches

set -eu
set -x

CURDIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

KERNEL="${CURDIR}/linux"

build_kernel() {
    pushd "${KERNEL}"

    sysconfig="/boot/config-$(uname -r)"
    if [[ -e $sysconfig ]]; then
        echo "Reusing system kernel .config: $sysconfig"
        cp -v $sysconfig .config
        yes "" | make oldconfig
    else
        make defconfig
    fi
    ./scripts/config \
        --set-str "SYSTEM_TRUSTED_KEYS" "" \
        --set-str "SYSTEM_REVOCATION_KEYS" "" \
        --set-str "LOCALVERSION" "-cet" \
        --set-str "CONFIG_MODULE_SIG_KEY" "" \
        --enable "ARCH_HAS_SHADOW_STACK" \
        --enable "X86_SHADOW_STACK" \
        --enable "X86_IBT"

    # build the kernel
    make -j$(nproc)

    popd
}

build_kernel

echo "Kernel built successfully."
echo "To install it on the local system, either generate a package:"
echo "  cd $KERNEL"
echo "  make bindeb-pkg"
echo "  sudo dpkg -i linux-headers-*.deb linux-image-*.deb"
echo "Or install it directly:"
echo "  cd $KERNEL"
echo "  sudo make modules_install"
echo "  sudo make headers_install"
echo "  sudo make install"
