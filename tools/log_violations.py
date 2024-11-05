#!/usr/bin/env python3
#
# Run a FineIBT-enabled program and ignore any FineIBT violations that occur.
# Instead of crashing the program, log the violation and continue.
#
# This tool is an external tool using ptrace, instead of installing a signal
# handler within the process itself. So no recompilation and instrumentation
# changes are required, and this works even when glibc itself is experiencing
# FineIBT issues (e.g., printf not working).
#
# Usage:
#  tools/log_violations.py PROGRAM ARGS...
#

import ctypes
import os
import struct
import sys
from ctypes import c_int, c_uint64, c_ulonglong
from dataclasses import dataclass
from os import WEXITSTATUS, WIFEXITED, WIFSIGNALED, WIFSTOPPED, WSTOPSIG, WTERMSIG
from signal import SIGCHLD, SIGILL, SIGSTOP, SIGTRAP, strsignal
from typing import Optional

from elftools.dwarf.descriptions import describe_form_class
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

# unistd_64.h
SYS_execve = 59

# ptrace.h + ptrace-abi.h
# Requests for ptrace call
PTRACE_TRACEME = 0
PTRACE_PEEKTEXT = 1
PTRACE_PEEKDATA = 2
PTRACE_PEEKUSR = 3
PTRACE_POKETEXT = 4
PTRACE_POKEDATA = 5
PTRACE_POKEUSR = 6
PTRACE_CONT = 7
PTRACE_KILL = 8
PTRACE_SINGLESTEP = 9
PTRACE_GETREGS = 12
PTRACE_SETREGS = 13
PTRACE_GETFPREGS = 14
PTRACE_SETFPREGS = 15
PTRACE_ATTACH = 16
PTRACE_DETACH = 17
PTRACE_GETFPXREGS = 18
PTRACE_SETFPXREGS = 19
PTRACE_SYSCALL = 24
PTRACE_ARCH_PRCTL = 30
PTRACE_SYSEMU = 31
PTRACE_SYSEMU_SINGLESTEP = 32
PTRACE_SINGLEBLOCK = 33
PTRACE_SETOPTIONS = 0x4200
PTRACE_GETEVENTMSG = 0x4201
PTRACE_GETSIGINFO = 0x4202
PTRACE_SETSIGINFO = 0x4203
PTRACE_GETREGSET = 0x4204
PTRACE_SETREGSET = 0x4205
PTRACE_SEIZE = 0x4206
PTRACE_INTERRUPT = 0x4207
PTRACE_LISTEN = 0x4208
PTRACE_PEEKSIGINFO = 0x4209
PTRACE_GETSIGMASK = 0x420A
PTRACE_SETSIGMASK = 0x420B
PTRACE_SECCOMP_GET_FILTER = 0x420C
PTRACE_SECCOMP_GET_METADATA = 0x420D
PTRACE_GET_SYSCALL_INFO = 0x420E
PTRACE_GET_RSEQ_CONFIGURATION = 0x420F

# Wait extended result codes for the above trace options.
PTRACE_EVENT_FORK = 1
PTRACE_EVENT_VFORK = 2
PTRACE_EVENT_CLONE = 3
PTRACE_EVENT_EXEC = 4
PTRACE_EVENT_VFORK_DONE = 5
PTRACE_EVENT_EXIT = 6
PTRACE_EVENT_SECCOMP = 7
PTRACE_EVENT_STOP = 128

SIGEVENTSYSCALL = SIGTRAP | 0x80

# Options set using PTRACE_SETOPTIONS or using PTRACE_SEIZE @data param
PTRACE_O_TRACESYSGOOD = 1
PTRACE_O_TRACEFORK = 1 << PTRACE_EVENT_FORK
PTRACE_O_TRACEVFORK = 1 << PTRACE_EVENT_VFORK
PTRACE_O_TRACECLONE = 1 << PTRACE_EVENT_CLONE
PTRACE_O_TRACEEXEC = 1 << PTRACE_EVENT_EXEC
PTRACE_O_TRACEVFORKDONE = 1 << PTRACE_EVENT_VFORK_DONE
PTRACE_O_TRACEEXIT = 1 << PTRACE_EVENT_EXIT
PTRACE_O_TRACESECCOMP = 1 << PTRACE_EVENT_SECCOMP
PTRACE_O_EXITKILL = 1 << 20
PTRACE_O_SUSPEND_SECCOMP = 1 << 21

ptrace_request_enum = c_uint64
c_pid_t = c_int


# sys/user.h
class user_regs_struct(ctypes.Structure):
    _fields_ = [
        ("r15", c_ulonglong),
        ("r14", c_ulonglong),
        ("r13", c_ulonglong),
        ("r12", c_ulonglong),
        ("rbp", c_ulonglong),
        ("rbx", c_ulonglong),
        ("r11", c_ulonglong),
        ("r10", c_ulonglong),
        ("r9", c_ulonglong),
        ("r8", c_ulonglong),
        ("rax", c_ulonglong),
        ("rcx", c_ulonglong),
        ("rdx", c_ulonglong),
        ("rsi", c_ulonglong),
        ("rdi", c_ulonglong),
        ("orig_rax", c_ulonglong),
        ("rip", c_ulonglong),
        ("cs", c_ulonglong),
        ("eflags", c_ulonglong),
        ("rsp", c_ulonglong),
        ("ss", c_ulonglong),
        ("fs_base", c_ulonglong),
        ("gs_base", c_ulonglong),
        ("ds", c_ulonglong),
        ("es", c_ulonglong),
        ("fs", c_ulonglong),
        ("gs", c_ulonglong),
    ]

    def dump(self):
        for reg in (
            "rip",
            "rax",
            "rbx",
            "rcx",
            "rdx",
            "rdi",
            "rsi",
            "r8",
            "r9",
            "r10",
            "r11",
            "r12",
            "r13",
            "r14",
            "r15",
            "rbp",
            "rsp",
        ):
            print(f"{reg:<3}: {getattr(self, reg):#018x}")


libc = ctypes.cdll.LoadLibrary("libc.so.6")

# long ptrace(enum __ptrace_request request, pid_t pid, void *addr, void *data);
# libc.ptrace.argtypes = [ptrace_request_enum, c_pid_t, c_uint64, c_uint64]
# libc.ptrace.restype = c_long


PTRACE_OPTIONS = (
    PTRACE_O_TRACESYSGOOD
    | PTRACE_O_EXITKILL
    | PTRACE_O_TRACEFORK
    | PTRACE_O_TRACECLONE
    | PTRACE_O_TRACEVFORK
    | PTRACE_O_TRACEEXEC
)


def ptrace_traceme():
    if libc.ptrace(PTRACE_TRACEME, 0, 0, 0) == -1:
        raise Exception("PTRACE_TRACEME")


def ptrace_setoptions(pid: int, opts: int):
    if libc.ptrace(PTRACE_SETOPTIONS, pid, 0, opts) == -1:
        raise Exception("PTRACE_SETOPTIONS")


def ptrace_getregs(pid: int) -> user_regs_struct:
    regs = user_regs_struct()
    if libc.ptrace(PTRACE_GETREGS, pid, 0, ctypes.byref(regs)) == -1:
        raise Exception("PTRACE_GETREGS")
    return regs


def ptrace_setregs(pid: int, regs: user_regs_struct):
    if libc.ptrace(PTRACE_SETREGS, pid, 0, ctypes.byref(regs)) == -1:
        raise Exception("PTRACE_SETREGS")


def ptrace_cont(pid: int, signal: int = 0):
    if libc.ptrace(PTRACE_CONT, pid, 0, signal) == -1:
        raise Exception("PTRACE_CONT")


def ptrace_geteventmsg(pid: int) -> int:
    msg = c_uint64(0)
    if libc.ptrace(PTRACE_GETEVENTMSG, pid, 0, ctypes.byref(msg)) == -1:
        raise Exception("PTRACE_GETEVENTMSG")
    return int.from_bytes(msg, byteorder="little", signed=True)


def ptrace_peekdata(pid: int, addr: int) -> list[int]:
    libc.ptrace.restype = c_uint64
    data = libc.ptrace(PTRACE_PEEKDATA, pid, ctypes.c_void_p(addr), 0)
    libc.ptrace.restype = ctypes.c_long
    if data == -1:
        raise Exception("PTRACE_PEEKDATA")
    return list(struct.pack("@N", data))


def start_child(argv: list[str]) -> int:
    pid = os.fork()
    if not pid:
        # Child
        print(f" # ptrace child running pid={os.getpid()}")
        print(f" # {os.getpid()}  Starting {argv}")
        if ptrace_traceme() == -1:
            print("ptrace(TRACEME) failed")
        os.execve(argv[0], argv, os.environ)
        print("execve failed")
        sys.exit(1)

    # Wait for just-forked process to start
    wpid, status = os.waitpid(pid, 0)
    assert wpid == pid
    assert WIFSTOPPED(status)
    ptrace_setoptions(pid, PTRACE_OPTIONS)
    regs = ptrace_getregs(pid)
    assert regs.orig_rax == SYS_execve
    ptrace_cont(pid)
    return pid


@dataclass
class ProcMapping:
    start_addr: int
    end_addr: int
    perms: str
    offset: int
    dev: str
    inode: int
    path: str


def get_proc_maps(pid: int) -> list[ProcMapping]:
    ret = []
    with open(f"/proc/{pid}/maps") as f:
        for line in f.readlines():
            line = line.strip()
            parts = line.split()
            addr_start, addr_end = [int(a, 16) for a in parts[0].split("-")]
            perms = parts[1]
            offset = int(parts[2], 16)
            dev = parts[3]
            inode = int(parts[4])
            path = "" if inode == 0 else parts[5]
            ret.append(
                ProcMapping(addr_start, addr_end, perms, offset, dev, inode, path)
            )
    return ret


# From pyelftools/examples/dwarf_decode_address.py
def get_sym_from_dwarf(addr: int, elffile: ELFFile) -> Optional[str]:
    if not elffile.has_dwarf_info():
        return None
    dwarfinfo = elffile.get_dwarf_info()
    for CU in dwarfinfo.iter_CUs():
        for DIE in CU.iter_DIEs():
            try:
                if DIE.tag == "DW_TAG_subprogram":
                    lowpc = DIE.attributes["DW_AT_low_pc"].value
                    highpc_attr = DIE.attributes["DW_AT_high_pc"]
                    highpc_attr_class = describe_form_class(highpc_attr.form)
                    if highpc_attr_class == "address":
                        highpc = highpc_attr.value
                    elif highpc_attr_class == "constant":
                        highpc = lowpc + highpc_attr.value
                    else:
                        print("Error: invalid DW_AT_high_pc class:", highpc_attr_class)
                        continue
                    if lowpc <= addr < highpc:
                        return DIE.attributes["DW_AT_name"].value
            except KeyError:
                continue
    return None


def get_sym_from_symtab(addr: int, elffile: ELFFile) -> Optional[str]:
    symtab = elffile.get_section_by_name(".symtab")
    if not symtab or not isinstance(symtab, SymbolTableSection):
        return None
    for sym in symtab.iter_symbols():
        if not sym.entry.st_info.type == "STT_FUNC":
            continue
        start_addr = sym.entry.st_value
        end_addr = start_addr + sym.entry.st_size
        if start_addr <= addr < end_addr:
            return sym.name


def get_sym_for_proc(pid: int, addr: int) -> str:
    # We know the virtual address in the address space of process <pid>.
    # We need to grab the mapping (from /proc/pid/maps) to figure out the elf
    # file this came from.
    # To look up the symbol in the elf file (using either symtab or dwarf) we
    # also need to know the symbol's vaddr relative to the elf file, for which
    # we need to map the entry of /proc/pid/maps to a segment of the ELF binary.

    mappings = get_proc_maps(pid)
    curpath, curpathidx = None, 0
    for mapping in mappings:
        if mapping.path == curpath:
            curpathidx += 1
        else:
            curpath = mapping.path
            curpathidx = 0
        if mapping.start_addr <= addr < mapping.end_addr:
            break
    else:
        raise Exception(f"Cannot find {addr:#x} in mappings for proc {pid}")
    assert mapping.path
    assert not mapping.path.startswith("[")
    libname = os.path.basename(mapping.path)

    # Address within the file disregarding vaddr offset
    addr = addr - mapping.start_addr + mapping.offset

    with open(mapping.path, "rb") as f:
        elffile = ELFFile(f)
        loadable_segments = filter(
            lambda s: s.header.p_type == "PT_LOAD", elffile.iter_segments()
        )
        seghdr = list(loadable_segments)[curpathidx].header

        # Virtual addr in binary
        file_virt_diff = seghdr.p_vaddr - seghdr.p_offset
        addr = addr + file_virt_diff

        funcname = get_sym_from_symtab(addr, elffile)
        if not funcname:
            funcname = get_sym_from_dwarf(addr, elffile)
        if not funcname:
            funcname = "<unknown>"

        return f"{funcname}@{libname}+{addr:#x}"


def handle_sigill(pid: int) -> bool:
    """
    00000000000000 <func>:
    0000:       f3 0f 1e fa             endbr64
    0004:       41 81 eb ac 0c 9c 01    sub    r11d,0x19c0cac
    000b:       0f 84 af fe ff ff       je     ... <func.nocfi>
    0011:       0f 0b                   ud2
    """
    print(f" # {pid} Handling SIGILL")
    regs = ptrace_getregs(pid)

    # Parse the instructions in the stub
    ud2 = ptrace_peekdata(pid, regs.rip)
    endbr = ptrace_peekdata(pid, regs.rip - 17)
    sub = ptrace_peekdata(pid, regs.rip - 13)
    je = ptrace_peekdata(pid, regs.rip - 6)
    assert ud2[:2] == [0x0F, 0x0B]
    assert endbr[:4] == [0xF3, 0x0F, 0x1E, 0xFA]
    assert sub[:3] == [0x41, 0x81, 0xEB]
    assert je[:2] == [0x0F, 0x84]

    stub_addr = regs.rip - 17
    expected_hash = int.from_bytes(sub[3:7], byteorder="little")
    je_off = int.from_bytes(je[2:6], byteorder="little", signed=True)
    callee_addr = regs.rip + je_off

    given_hash = regs.r11

    # Read the stack for the caller
    caller_addr = int.from_bytes(ptrace_peekdata(pid, regs.rsp), byteorder="little")

    print(f" # {pid}  Hash mismatch {given_hash:x} != {expected_hash:x}")

    caller_sym = get_sym_for_proc(pid, caller_addr)
    stub_sym = get_sym_for_proc(pid, stub_addr)
    callee_sym = get_sym_for_proc(pid, callee_addr)
    print(f" # {pid}   {caller_sym} -> {stub_sym} -> {callee_sym}")

    # Skip to the intended callee, ignoring the ud2
    regs.rip = ctypes.c_ulong(callee_addr)
    ptrace_setregs(pid, regs)
    ptrace_cont(pid)
    return True


def main():
    pids = []
    pids.append(start_child(sys.argv[1:]))

    while True:
        try:
            pid, status = os.wait()
        except ChildProcessError:
            break

        if WIFSTOPPED(status):
            sig = WSTOPSIG(status)
            event = status >> 16
            if sig == SIGTRAP and event in (
                PTRACE_EVENT_FORK,
                PTRACE_EVENT_VFORK,
                PTRACE_EVENT_CLONE,
            ):
                newpid = ptrace_geteventmsg(pid)
                print(f" # {pid} forked into {newpid}")
                ptrace_cont(pid)
            elif sig == SIGTRAP and event == PTRACE_EVENT_EXEC:
                print(f" # {pid} exec (swallowing)")
                ptrace_cont(pid)
            elif sig == SIGEVENTSYSCALL:
                # Syscall (we don't expect these)
                print(f" # {pid} Got syscall")
                assert False, "unreachable"
            elif sig == SIGILL and handle_sigill(pid):
                continue
            elif sig == SIGSTOP and pid not in pids:
                print(f" # {pid} New process started")
                pids.append(pid)
                ptrace_setoptions(pid, PTRACE_OPTIONS)
                ptrace_cont(pid)
            else:
                print(f" # {pid} signal {status} {sig} {strsignal(sig)}")
                # ptrace_getregs(pid).dump()
                ptrace_cont(pid, sig)
        elif WIFEXITED(status):
            code = WEXITSTATUS(status)
            print(f" # {pid} exited normally with status {code}")
            pids.remove(pid)
        elif WIFSIGNALED(status):
            sig = WTERMSIG(status)
            print(f" # {pid} exited terminated with signal {sig}")
            pids.remove(pid)
        else:
            assert False, "unreachable"


if __name__ == "__main__":
    main()
