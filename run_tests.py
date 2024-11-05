#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
#
# Run (and debug) FineIBT tests using custom toolchains.
#

import argparse
import os
import shlex
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, TextIO, Union

try:
    from termcolor import colored
except ImportError:

    def colored(
        text: str,
        color: Optional[str] = None,
        on_color: Optional[str] = None,
        attrs: Optional[Iterable[str]] = None,
    ) -> str:
        return text


txtwarn = colored("[WARNING]", "yellow", attrs=("bold",))
txterror = colored("[ERROR]", "red", attrs=("bold",))
txtfail = colored("[FAIL]", "red", attrs=("bold",))
txtpass = colored("[PASS]", "green", attrs=("bold",))
txtlang = {
    "c": colored("[C]  ", "blue"),
    "cpp": colored("[C++]", "blue"),
    "s": colored("[ASM]", "blue"),
}


class BuildError(Exception):
    pass


class RunError(Exception):
    pass


@dataclass
class CompiledObject:
    name: str
    lang: str
    srcdir: Path
    builddir: Optional[Path] = None

    cflags: list[str] = field(default_factory=list)
    disable_ibt: bool = False
    disable_fineibt: bool = False

    @property
    def src(self) -> Path:
        return self.srcdir / f"{self.name}.{self.lang}"

    @property
    def ofile(self) -> Path:
        assert self.builddir is not None
        return self.builddir / f"{self.name}.o"

    @property
    def irfile_pre(self) -> Path:
        assert self.builddir is not None
        return self.builddir / f"{self.name}.pre.ll"

    @property
    def irfile_post(self) -> Path:
        assert self.builddir is not None
        return self.builddir / f"{self.name}.ll"

    @property
    def bin(self) -> Path:
        assert self.builddir is not None
        return self.builddir / self.name

    def parse_args(
        self, cflags=[], disable_ibt=None, disable_fineibt=None, **kwargs: list[str]
    ) -> None:
        if kwargs:
            raise ValueError(f"Unknown args: {','.join(kwargs.keys())}")

        self.cflags = cflags
        self.disable_ibt = disable_ibt is not None
        self.disable_fineibt = disable_fineibt is not None


@dataclass
class Test(CompiledObject):
    expected_return_code: int = 0
    objfiles: list[str] = field(default_factory=list)
    libs: list[str] = field(default_factory=list)
    ldflags: list[str] = field(default_factory=list)

    def parse_args(
        self, returncode=["0"], ldflags=[], obj=[], lib=[], **kwargs: list[str]
    ) -> None:
        super().parse_args(**kwargs)
        self.expected_return_code = int(returncode[0])
        self.ldflags = ldflags
        self.objfiles = obj
        self.libs = lib


@dataclass
class ObjFile(CompiledObject):
    @property
    def bin(self) -> Path:
        return self.ofile


@dataclass
class Lib(CompiledObject):
    ldflags: list[str] = field(default_factory=list)

    def parse_args(self, ldflags=[], **kwargs: list[str]) -> None:
        super().parse_args(**kwargs)
        self.ldflags = ldflags

    @property
    def bin(self) -> Path:
        assert self.builddir is not None
        return self.builddir / f"{self.name}.so"


def run(
    cmd: Iterable[Union[str, Path]],
    outfile: Optional[TextIO] = None,
    stdout: bool = True,
    print_cmd: bool = False,
) -> None:
    for c in cmd:
        assert isinstance(c, (str, Path)), f"{c} has unsupported type {type(c)}"
    cmd = [str(c) for c in cmd]

    if print_cmd:
        print(f"# {shlex.join(cmd)}")

    # If outputting to file, capture the output. Otherwise, run as-is (attached
    # to stdout) so we can get colors in the output.
    if outfile is None and stdout:
        subprocess.run(cmd, text=True, check=True)
    else:
        with subprocess.Popen(
            cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        ) as proc:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip("\n")
                if stdout:
                    print(line)
                if outfile:
                    outfile.write(line + "\n")
        if proc.returncode:
            raise subprocess.CalledProcessError(proc.returncode, proc.args)


def parse_file_info(file: Path) -> CompiledObject:
    srcdir = file.parent
    name, lang = file.stem, file.suffix[1:]

    conts = file.read_text()
    line = conts.splitlines()[0].strip()
    if not line.startswith("//"):
        raise ValueError("File does not start with '//'")
    line = line[2:].strip()
    filetype, *args = line.split()
    if filetype not in ("TEST", "OBJ", "LIB"):
        raise ValueError(f"Invalid type '{filetype}', expected (TEST,OBJ,LIB)")
    parsed_args: dict[str, list[str]] = {}
    curarg = None
    for arg in args:
        if arg.startswith("@"):
            curarg = arg[1:].lower()
            assert curarg not in parsed_args
            parsed_args[curarg] = []
        else:
            assert curarg is not None
            parsed_args[curarg].append(arg)

    objty = {"TEST": Test, "OBJ": ObjFile, "LIB": Lib}[filetype]
    obj = objty(name, lang, srcdir)
    obj.parse_args(**parsed_args)
    return obj


def collect_tests(
    directory: Path,
) -> tuple[dict[str, Test], dict[str, ObjFile], dict[str, Lib]]:
    tests: dict[str, Test] = {}
    objfiles: dict[str, ObjFile] = {}
    libs: dict[str, Lib] = {}

    for file in directory.iterdir():
        if file.suffix not in (".c", ".cpp", ".s"):
            continue

        try:
            obj = parse_file_info(file)
        except ValueError as e:
            print(f"{txterror} Invalid test file {file}: {e}")
            continue

        if isinstance(obj, Test):
            assert obj.name not in tests
            tests[obj.name] = obj
        elif isinstance(obj, ObjFile):
            assert obj.name not in objfiles
            objfiles[obj.name] = obj
        elif isinstance(obj, Lib):
            assert obj.name not in libs
            libs[obj.name] = obj

    return tests, objfiles, libs


def get_compiler(obj: CompiledObject, args: argparse.Namespace) -> str:
    assert obj.lang in ("c", "s", "cpp")
    base = "clang"
    if obj.lang == "cpp":
        base = "clang++"

    muslbin = os.path.join(args.toolchain, f"musl-lld-{base}")
    if os.path.exists(muslbin):
        return muslbin

    return os.path.join(args.toolchain, base)


def build_obj(
    obj: CompiledObject,
    args: argparse.Namespace,
    deps: Mapping[str, CompiledObject] = {},
) -> None:
    assert isinstance(obj, (Test, ObjFile, Lib))

    logpath = Path(".") / "tests" / "logs" / f"{obj.name}.build"

    logpath.parent.mkdir(parents=True, exist_ok=True)

    obj.ofile.unlink(missing_ok=True)
    obj.bin.unlink(missing_ok=True)

    compiler = get_compiler(obj, args)

    cflags = [f"-O{args.opt}", "-ggdb"]
    ldflags = ["-fuse-ld=lld", "-Wl,-znow"]

    cflags += obj.cflags
    if isinstance(obj, (Test, Lib)):
        ldflags += obj.ldflags

    # Enable debug output for LLD, and disable its multi-threading
    ldflags += ["-Wl,--threads=1", "-Wl,--verbose"]

    libpath = obj.bin.parent
    ldflags += [f"-L{libpath}", f"-Wl,-rpath,{libpath}"]

    if args.print_ir_before:
        assert args.ibt and args.fineibt
        cflags += ["-mllvm", "--print-before=FineIBT"]
    if args.print_ir_after:
        assert args.ibt and args.fineibt
        cflags += ["-mllvm", "--print-after=FineIBT"]
    if args.print_ir:
        cflags += ["-mllvm", "--print-isel-input"]

    if isinstance(obj, Lib):
        cflags += ["-fPIC"]
        ldflags += ["-shared"]

    if args.no_pie and isinstance(obj, Test):
        cflags += ["-fno-PIC"]
        ldflags += ["-no-pie"]

    base_compile_cmd = [compiler, *cflags, "-c", obj.src]
    compile_cmd = base_compile_cmd + ["-o", obj.ofile]
    link_cmd = [compiler, *ldflags, "-o", obj.bin, obj.ofile]

    if isinstance(obj, Test):
        # Ensure these come at end
        link_cmd += [deps[objfile_name].ofile for objfile_name in obj.objfiles]
        link_cmd += [f"-l:{deps[libname].bin.name}" for libname in obj.libs]

    with open(logpath, "w") as logfile:
        try:
            runargs = {"stdout": args.verbose, "print_cmd": args.print_cmd}

            run(compile_cmd, outfile=logfile, **runargs)

            if not args.compile_only and not isinstance(obj, ObjFile):
                run(link_cmd, outfile=logfile, **runargs)
        except subprocess.CalledProcessError:
            raise BuildError()

    if args.disassemble or args.relocs:
        if args.compile_only:
            o = obj.ofile
        else:
            o = obj.bin
        if args.disassemble:
            run(["objdump", "-Mintel", "-r", "-d", o], print_cmd=args.print_cmd)
        if args.relocs:
            # For dynamic relocs, readelf is clearer, otherwise objdump is
            if isinstance(obj, ObjFile):
                run(["objdump", "--reloc", o], print_cmd=args.print_cmd)
            else:
                print(f"Relocations for {o}")
                run(["readelf", "--relocs", o], print_cmd=args.print_cmd)


def run_test(test: Test, args) -> None:
    assert isinstance(test, Test)

    logpath = Path(".") / "tests" / "logs" / f"{test.name}.run"
    logpath.parent.mkdir(parents=True, exist_ok=True)

    if args.gdb:
        old_sigint_handler = signal.signal(signal.SIGINT, lambda num, frame: None)
        run(["gdb", "--quiet", "--args", test.bin], print_cmd=args.print_cmd)
        signal.signal(signal.SIGINT, old_sigint_handler)
    else:
        with open(logpath, "w") as logfile:
            try:
                run(
                    [test.bin],
                    outfile=logfile,
                    stdout=args.verbose,
                    print_cmd=args.print_cmd,
                )
                rc = 0
            except subprocess.CalledProcessError as e:
                rc = e.returncode

            if rc != test.expected_return_code:
                if test.expected_return_code:
                    raise RunError(
                        f"returned status {rc}, expected {test.expected_return_code}"
                    )
                else:
                    raise RunError(f"returned status {rc}")


def verify_toolchain(toolchain_arg: str) -> Path:
    if toolchain_arg in ("baseline", "fineibt"):
        toolchain = Path(f"toolchains/{toolchain_arg}/llvm/bin")
    else:
        toolchain = Path(toolchain_arg)

    if not (toolchain / "clang").is_file():
        raise ValueError(f"'clang' does not exist in {toolchain}")
    if not (toolchain / "clang++").is_file():
        raise ValueError(f"'clang++' does not exist in {toolchain}")

    clang_conf = toolchain / "clang.cfg"
    if not clang_conf.is_file():
        print(
            f"{txtwarn} {clang_conf} missing; clang will use default arguments and system libraries"
        )

    clangpp_conf = toolchain / "clang++.cfg"
    if not clangpp_conf.is_file():
        print(
            f"{txtwarn} {clangpp_conf} missing; clang++ will use default arguments and system libraries"
        )

    return toolchain


def parse_options(tests: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose output")
    parser.add_argument(
        "-p", "--print-cmd", action="store_true", help="print executed commands"
    )

    parser.add_argument("-c", "--compile-only", action="store_true", help="do not link")
    parser.add_argument(
        "-l", "--link-only", action="store_true", help="do not recompile"
    )

    parser.add_argument(
        "-d",
        "--disassemble",
        action="store_true",
        help="show dissassembly of final built object",
    )
    parser.add_argument("-r", "--relocs", action="store_true", help="dump relocations")
    parser.add_argument(
        "--print-ir", action="store_true", help="dump final LLVM IR (before ISel)"
    )
    parser.add_argument(
        "--print-ir-before",
        action="store_true",
        help="dump LLVM IR before FineIBT pass",
    )
    parser.add_argument(
        "--print-ir-after", action="store_true", help="dump LLVM IR after FineIBT pass"
    )

    parser.add_argument("-g", "--gdb", action="store_true", help="run test case in GDB")

    parser.add_argument(
        "-t",
        "--toolchain",
        default="fineibt",
        help="'baseline', 'fineibt', or path of LLVM toolchain (bin dir)",
    )
    parser.add_argument(
        "--opt",
        default="2",
        choices=("0", "1", "2", "3", "s"),
        help="optimization level of compiler",
    )
    parser.add_argument(
        "--no-ibt", dest="ibt", action="store_false", help="compile without IBT"
    )
    parser.add_argument(
        "--no-fineibt",
        dest="fineibt",
        action="store_false",
        help="compile without FineIBT",
    )
    parser.add_argument(
        "--no-pie", action="store_true", help="disable position independent executables"
    )

    parser_tests = parser.add_argument(
        "tests", nargs="*", help="test cases to run (omit to run all)"
    )

    if "_ARGCOMPLETE" in os.environ:
        import argcomplete

        # Only set choices if we want to fetch the argcomplete options - otherwise
        # there's a bug in py3.11 and below where nargs='*' and choices interfere with
        # each other. Otherwise, we check for option validity later on anyway.
        parser_tests.choices = tests

        argcomplete.autocomplete(parser)

    args = parser.parse_args()

    return args


def main() -> None:
    src_dir = Path(".") / "tests"
    build_dir = src_dir / "build"

    build_dir.mkdir(parents=True, exist_ok=True)

    # Scan the tests directory for tests and their dependencies
    tests, objfiles, libs = collect_tests(src_dir)

    args = parse_options(list(tests.keys()))

    if args.verbose:
        args.print_cmd = True
    do_test_run = not args.compile_only and not args.link_only and not args.disassemble
    args.toolchain = verify_toolchain(args.toolchain)

    # Only use subset of tests if requested by user
    selected_tests: list[Test] = list(tests.values())
    if args.tests:
        selected_tests = []
        for test in args.tests:
            if test not in tests:
                print(f"{txterror} Test '{test}' unknown.")
                print("Valid options: " + ", ".join(tests.keys()))
                sys.exit(1)
            selected_tests.append(tests[test])

    # Determine which objfiles and libs are required by the selected tests
    required_objfiles, required_libs = set(), set()
    for test in selected_tests:
        for objfile_name in test.objfiles:
            if objfile_name not in objfiles:
                print(
                    f"{txterror} Test '{test.name}' is requesting unknown objfile"
                    f" '{objfile_name}'"
                )
                sys.exit(1)
            required_objfiles.add(objfile_name)
        for lib_name in test.libs:
            if lib_name not in libs:
                print(
                    f"{txterror} Test '{test.name}' is requesting unknown lib"
                    f" '{lib_name}'"
                )
                sys.exit(1)
            required_libs.add(lib_name)

    # Build any dependencies (objfiles, libs) before tests
    deps: dict[str, Union[ObjFile, Lib]] = {}
    for objfile_name in required_objfiles:
        objfile = objfiles[objfile_name]
        objfile.builddir = build_dir
        try:
            build_obj(objfile, args)
            deps[objfile_name] = objfile
        except BuildError:
            print(f"{txterror} Could not build objfile '{objfile_name}'")
            sys.exit(1)
    for lib_name in required_libs:
        lib = libs[lib_name]
        lib.builddir = build_dir
        try:
            build_obj(lib, args)
            deps[lib_name] = lib
        except BuildError:
            print(f"{txterror} Could not build library '{lib_name}'")
            sys.exit(1)

    # Build and run each test
    for test in selected_tests:
        lang = txtlang[test.lang]
        try:
            test.builddir = build_dir
            build_obj(test, args, deps)
            if do_test_run:
                run_test(test, args)
            print(f"{txtpass} {lang} {test.name}")
        except BuildError:
            print(f"{txtfail} {lang} {test.name} (build error)")
        except RunError as e:
            print(f"{txtfail} {lang} {test.name} {e}")


if __name__ == "__main__":
    main()
