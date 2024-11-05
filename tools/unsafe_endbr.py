#!/usr/bin/env python3
#
# Analyze a binary to verify every ENDBR instruction has a FineIBT check.
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


@dataclass
class Stats:
    unsafe_endbr_start: int = 0
    unsafe_endbr_interior: int = 0

    def __add__(self, other) -> "Stats":
        assert isinstance(other, Stats)
        return Stats(
            self.unsafe_endbr_start + other.unsafe_endbr_start,
            self.unsafe_endbr_interior + other.unsafe_endbr_interior,
        )

    def report(self) -> int:
        errors = 0
        if self.unsafe_endbr_start:
            print(f"Unsafe ENDBR at start of function: {self.unsafe_endbr_start}")
            errors += self.unsafe_endbr_start
        if self.unsafe_endbr_interior:
            print(f"Unsafe ENDBR in middle of function: {self.unsafe_endbr_interior}")
            errors += self.unsafe_endbr_interior
        return errors


def check_function(func: Func) -> Stats:
    stats = Stats()
    decoder = iced_x86.Decoder(64, func.data, ip=func.addr)
    for inst in decoder:
        offset = inst.ip - func.addr

        locstr = f"{inst.ip:#x} {func.name}+{offset:#x}"

        if inst.code == Code.ENDBR32:
            raise Exception(f"{locstr}: Unexpected ENDBR32!")
        elif inst.code == iced_x86.Code.ENDBR64:
            nextinst = decoder.decode()
            if nextinst.code != Code.SUB_RM32_IMM32:
                print(f"{locstr}: ENDBR64 without hash check")
                if offset == 0:
                    stats.unsafe_endbr_start += 1
                else:
                    stats.unsafe_endbr_interior += 1
    return stats


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} FILE")
        sys.exit()

    stats = Stats()

    with open(sys.argv[1], "rb") as f:
        elf = ELFFile(f)
        for func in iter_funcs(elf):
            stats += check_function(func)

    if not stats.report():
        print("No errors, binary seems OK")


if __name__ == "__main__":
    main()
