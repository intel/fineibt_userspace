#!/usr/bin/env python3
#
# Analyze a binary to check for interior ENDBR instructions (i.e., landing pads not at start of function).
# These can be caused by C/C++ exceptions, setjmp, or address-taken labels (e.g., for computed goto).
#

import sys
from dataclasses import dataclass
from typing import Iterable

import iced_x86
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
from iced_x86 import Code


@dataclass
class Func:
    name: str
    addr: int
    size: int
    data: bytes


def iter_funcs(elf: ELFFile) -> Iterable[Func]:
    symtab = elf.get_section_by_name(".symtab")
    if not symtab or not isinstance(symtab, SymbolTableSection):
        raise Exception("ELF file does not have symbol table")
    for sym in symtab.iter_symbols():
        if not sym.entry.st_info.type == "STT_FUNC":
            continue
        if sym.name.startswith("__fineibt_plthash"):
            continue
        vaddr = sym.entry.st_value
        size = sym.entry.st_size
        if vaddr == 0 or size == 0:
            continue

        section = elf.get_section(sym.entry.st_shndx)
        sec_vaddr = section["sh_addr"]
        sec_size = section["sh_size"]
        assert vaddr >= sec_vaddr and vaddr + size <= sec_vaddr + sec_size
        off_in_sec = vaddr - sec_vaddr
        data = section.data()[off_in_sec : off_in_sec + size]
        yield Func(sym.name, vaddr, size, data)


def check_function(func: Func) -> int:
    interior_endbr = 0
    decoder = iced_x86.Decoder(64, func.data, ip=func.addr)
    for inst in decoder:
        offset = inst.ip - func.addr

        locstr = f"{inst.ip:#x} {func.name}+{offset:#x}"

        if inst.code == Code.ENDBR32:
            raise Exception(f"{locstr}: Unexpected ENDBR32!")
        elif inst.code == iced_x86.Code.ENDBR64:
            if offset == 0:
                continue
            print(f"{locstr}: interior ENDBR64")
            interior_endbr += 1
    return interior_endbr


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} FILE")
        sys.exit()

    interior_endbr = 0

    with open(sys.argv[1], "rb") as f:
        elf = ELFFile(f)
        for func in iter_funcs(elf):
            interior_endbr += check_function(func)

    print(f"Finished, found {interior_endbr} interior ENDBRs")


if __name__ == "__main__":
    main()
