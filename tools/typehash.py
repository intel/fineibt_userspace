#!/usr/bin/env python3
#
# Retrieve mangled types for functions, calculate type hashes, and
# automatically process LLVM's TargetLibraryInfo.def to add mangled
# types.
#

import argparse
import glob
import os
import re
import subprocess
import xxhash

EXCLUDED = [
    "__cxa_guard_abort",
    "__cxa_guard_acquire",
    "__cxa_guard_release",
]


def get_sym_typestr(syms: list[str], signatures: list[str] = []) -> dict[str, str]:
    """Returns the mangled type strings for every name in `syms`.
    An optional list of signatures can be provided, otherwise
    a signature must be defined in one of the standard header files."""

    template = """
#include <cstdio>
#include <typeinfo>

#include <cstdint>
#include <complex.h>
#include <dirent.h>
#include <new>

#define complex _Complex
enum class __hot_cold_t : uint8_t;

{signatures}

int main(int argc, char **argv) {{
    {body}
    return 0;
}}
"""

    sym_template = 'printf("{sym} _ZTS%s\\n", typeid({sym}).name());'

    body = "\n    ".join(sym_template.format(sym=sym) for sym in syms)
    prog = template.format(signatures="\n".join(signatures), body=body)
    tmpfile = f"/tmp/typehashpy_bin-{os.getpid()}"

    subprocess.run(
        ["g++", "-xc++", "-o", tmpfile, "-"],
        input=prog,
        text=True,
        check=True,
    )
    proc = subprocess.run(tmpfile, capture_output=True, text=True)
    out = proc.stdout.strip()
    os.unlink(tmpfile)

    mangled = dict(l.split(" ") for l in out.splitlines())
    return mangled


def get_typestr_for_signature(signature: str) -> str:
    """Retrieves the mangled type string for a given C/C++ signature."""

    # Crude sanity check
    if "func" not in signature:
        raise Exception("Signature must be of a function named `func`")

    sym_typestrs = get_sym_typestr(["func"], [signature + ";"])
    return sym_typestrs["func"]


def get_hash_for_typestr(typestr: str) -> int:
    """Returns the hash for a given mangled type string."""

    if not typestr.startswith("_ZTS") or not typestr.endswith("E"):
        raise Exception(f"Invalid typestr {typestr}")

    h = xxhash.xxh64(typestr).intdigest()
    h &= (1 << 31) - 1
    return h


def extract_syms_signatures(deffile: str) -> tuple[list[str], list[str]]:
    """Parses the contents of a deffile (i.e., TargetLibraryInfo.def)
    looking for which symbols are defined and their listed type
    signature.

    Some sanitization over the input is done, since the type signature
    portion is used somewhat loosely."""

    signatures = []
    syms = []
    cursig, curname1 = None, None
    for l in deffile.splitlines():
        if l.startswith("/// "):
            if cursig is None:
                cursig = l[4:]
            else:
                if not cursig.endswith(";"):
                    cursig += l[4:].strip()

        elif l.startswith("TLI_DEFINE_ENUM_INTERNAL"):
            symmatch = re.match(r"^TLI_DEFINE_ENUM_INTERNAL\((.+)\)$", l)
            assert symmatch is not None
            curname1 = symmatch.group(1)

        elif l.startswith("TLI_DEFINE_STRING_INTERNAL"):
            assert cursig is not None and curname1 is not None

            symmatch = re.match(r'^TLI_DEFINE_STRING_INTERNAL\("(.+)"\)$', l)
            assert symmatch is not None
            curname2 = symmatch.group(1)

            if curname2 in EXCLUDED:
                cursig, curname1 = None, None
                continue

            symname = curname1 if curname2.startswith("??") else curname2

            # Fixing up names/signatures. AAAH
            if not cursig.endswith(";"):
                cursig += ";"
            cursig = re.sub(r"operator [^(]+", symname, cursig)
            cursig = re.sub(r"\.\.\.,[^)]+", "...", cursig)  # See execle
            cursig = re.sub(r"\[,.*\]", ", ...", cursig)  # See open64
            cursig = re.sub(r"(\(.*)new(.*\))", r"\1_new\2", cursig)
            cursig = re.sub(r"(\(.*)restrict(.*\))", r"\1__restrict\2", cursig)
            if "__sqrt_finite" in cursig:
                cursig = cursig.replace("__sqrt_finite", symname)
            if "cabs" in symname:
                cursig = cursig.replace("cabs", symname)
            if symname in ("__atomic_load", "__atomic_store", "cabs"):
                symname = curname1
                cursig = cursig.replace(curname2, curname1)
            if symname not in cursig:
                symname = curname1

            syms.append(symname)
            signatures.append(cursig)
            cursig, curname1 = None, None
    assert cursig is None and curname1 is None
    return syms, signatures


def process_deffile(fname: str) -> None:
    """Parses and rewrites a given TargetLibraryInfo.def"""

    with open(fname) as f:
        deffile = f.read()

    syms, signatures = extract_syms_signatures(deffile)
    if not syms:
        raise Exception(f"Found no TLI_DEFINE_ENUM_INTERNAL in {fname}")
    mangled = get_sym_typestr(syms, signatures)

    out = []
    cursym1, cursym2, curmangled = None, None, None
    for l in deffile.split("\n"):
        if l.startswith("TLI_DEFINE_ENUM_INTERNAL"):
            symmatch = re.match(r"^TLI_DEFINE_ENUM_INTERNAL\((.+)\)$", l)
            assert symmatch is not None
            cursym1 = symmatch.group(1)

        elif l.startswith("TLI_DEFINE_STRING_INTERNAL"):
            symmatch = re.match(r'^TLI_DEFINE_STRING_INTERNAL\("(.+)"\)$', l)
            assert symmatch is not None
            cursym2 = symmatch.group(1)
        elif l.startswith("TLI_DEFINE_TYPEMANGLED_INTERNAL"):
            symmatch = re.match(r'^TLI_DEFINE_TYPEMANGLED_INTERNAL\("(.+)"\)$', l)
            assert symmatch is not None
            curmangled = symmatch.group(1)
        elif not l:
            if cursym1 or cursym2 or curmangled:
                assert cursym1 and cursym2
                if cursym1 in mangled:
                    symmangled = mangled[cursym1]
                elif cursym2 in mangled:
                    symmangled = mangled[cursym2]
                else:
                    print(f"{cursym1}/{cursym2} not in mangled database")
                    symmangled = "<UNKNOWN>"
                if curmangled:
                    assert curmangled == symmangled
                else:
                    out.append(f'TLI_DEFINE_TYPEMANGLED_INTERNAL("{symmangled}")')
                cursym1, cursym2, curmangled = None, None, None
        out.append(l)

    with open(fname, "w") as f:
        f.write("\n".join(out))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_stdfunc = subparsers.add_parser(
        "stdfunc", aliases=["func"], help="get info for standard library function"
    )
    parser_stdfunc.add_argument("func", nargs="+")

    parser_typesig = subparsers.add_parser(
        "signature", aliases=["sig"], help="get info for a given C/C++ definition"
    )
    parser_typesig.add_argument(
        "signature", help="signature for a function named `func`"
    )

    parser_typestr = subparsers.add_parser(
        "typestr", aliases=["mangled"], help="get info for a given mangled type string"
    )
    parser_typestr.add_argument("typestr", nargs="+")

    parser_deffile = subparsers.add_parser(
        "process-deffile", help="Process TargetLibraryInfo.def"
    )
    parser_deffile.add_argument("file")

    args = parser.parse_args()

    if args.command in ("stdfunc", "func"):
        sym_typestrs = get_sym_typestr(args.func)
        for sym, typestr in sym_typestrs.items():
            if "Do" in typestr:
                print(
                    "signature with noexcept:",
                    sym,
                    typestr,
                    hex(get_hash_for_typestr(typestr)),
                )
                typestr = typestr.replace("Do", "")
                print(sym, typestr, hex(get_hash_for_typestr(typestr)))
            else:
                print(sym, typestr, hex(get_hash_for_typestr(typestr)))

    elif args.command in ("signature", "sig"):
        typestr = get_typestr_for_signature(args.signature)
        print(typestr, hex(get_hash_for_typestr(typestr)))

    elif args.command in ("typestr", "mangled"):
        for typestr in args.typestr:
            print(typestr, hex(get_hash_for_typestr(typestr)))

    elif args.command == "process-deffile":
        process_deffile(args.file)

    else:
        raise Exception(f'Unknown command "{args.command}"')


if __name__ == "__main__":
    main()
