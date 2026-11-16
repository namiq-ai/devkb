#!/usr/bin/env python3
"""Compiler-backed call truth for a C/C++ repository, independent of devkb's extractor (libclang).

  truth_clang.py REPO OUT.json [--std c++17] [-I dir ...] [-D name ...]

Parses every tracked .c/.cc/.cpp/.cxx file as a translation unit, collects each function definition inside REPO
(by USR) and each call expression inside such a definition with the USR of the function it refers to. Output:
{"defs": {usr: [file, start_line, end_line, qualified_name]}, "edges": [[caller_usr, callee_usr], ...]}
Only edges whose both ends are definitions inside REPO are kept. Needs `libclang` (pip install libclang).
"""
import json, subprocess, sys
from pathlib import Path

SKIP = ("third_party", "/vendor/", "/build/")
C_EXTS = (".c",)
CXX_EXTS = (".cc", ".cpp", ".cxx")


def parse_args(argv):
    """`REPO OUT [--std S] [-I dir | -Idir] [-D name[=v] | -Dname[=v]]`: the verification flags (SPEC-DKB-002 story 1.5).

    `-D__interrupt= -D__ramfunc=` lets the compiler read the same dialect keywords devkb's scanner tolerates."""
    opts = {"repo": argv[0], "out": argv[1], "std": "c++17", "incs": [], "defs": []}
    i = 2
    while i < len(argv):
        a = argv[i]
        if a == "--std":
            opts["std"] = argv[i + 1]; i += 2
        elif a in ("-I", "-D"):
            opts["incs" if a == "-I" else "defs"].append(argv[i + 1]); i += 2
        elif a.startswith("-I") and len(a) > 2:
            opts["incs"].append(a[2:]); i += 1
        elif a.startswith("-D") and len(a) > 2:
            opts["defs"].append(a[2:]); i += 1
        else:
            i += 1
    return opts


def unit_language(rel):
    """The language the compiler is asked to read a translation unit as: by extension, never by devkb's decision."""
    return "c" if rel.endswith(C_EXTS) else "cpp"


def system_includes(cxx):
    """The compiler's own header search path (libclang from pip has no resource directory, so `stddef.h` is not found,
    standard types become invalid and one function gets a different USR in each translation unit)."""
    out = subprocess.run(["g++" if cxx else "gcc", "-E", "-x", "c++" if cxx else "c", "-", "-v"], input="", capture_output=True, text=True).stderr
    dirs, on = [], False
    for line in out.splitlines():
        if line.startswith("#include <...>"): on = True; continue
        if line.startswith("End of search list"): break
        if on and line.startswith(" "): dirs.append(line.strip())
    return [f"-isystem{d}" for d in dirs]


def qualified(c):
    parts = []
    while c is not None and c.kind != K.TRANSLATION_UNIT:
        if c.spelling:
            parts.append(c.spelling)
        c = c.semantic_parent
    return ".".join(reversed(parts))


def main(argv):
    global K, FUNC
    import clang.cindex as ci
    K = ci.CursorKind
    FUNC = {K.FUNCTION_DECL, K.CXX_METHOD, K.CONSTRUCTOR, K.DESTRUCTOR, K.CONVERSION_FUNCTION, K.FUNCTION_TEMPLATE}
    o = parse_args(argv)
    repo, out, std, incs, defs_ = Path(o["repo"]).resolve(), o["out"], o["std"], o["incs"], o["defs"]
    files = [f for f in subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True, text=True).stdout.split()
             if f.endswith((".c", ".cc", ".cpp", ".cxx")) and not any(s in "/" + f for s in SKIP)]
    idx = ci.Index.create()
    defs, edges, visible = {}, set(), {}
    def_lang, header_langs = {}, {}      # usr -> language of the translation unit that read it; header -> includer languages
    lines_cache = {}
    inside = lambda p: p and str(Path(p).resolve()).startswith(str(repo)) and not any(s in p for s in SKIP)
    for rel in files:
        lang = ["-x", "c", "-std=gnu11"] if rel.endswith(".c") else ["-x", "c++", f"-std={std}"]
        args = lang + system_includes(not rel.endswith(".c")) + [f"-I{repo}"] + [f"-I{repo / d}" for d in incs] + [f"-D{d}" for d in defs_]
        try:
            tu = idx.parse(str(repo / rel), args=args, options=ci.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES * 0)
        except ci.TranslationUnitLoadError:
            continue
        unit_lang = unit_language(rel)
        for inc in tu.get_includes():      # a header's language is the language of the translation units that include it
            if inc.include is not None and inside(inc.include.name):
                header_langs.setdefault(str(Path(inc.include.name).resolve().relative_to(repo)), set()).add(unit_lang)

        def walk(node, caller):
            try:
                kids = list(node.get_children())
            except ValueError:  # libclang's Python bindings do not know every template argument kind
                return
            for c in kids:
                try:
                    k = c.kind
                except ValueError:
                    continue
                here = caller
                try:
                    if k in FUNC and c.is_definition() and c.location.file and inside(c.location.file.name):
                        usr = c.get_usr()
                        rel_f = str(Path(c.location.file.name).resolve().relative_to(repo))
                        defs.setdefault(usr, [rel_f, c.extent.start.line, c.extent.end.line, qualified(c)])
                        def_lang.setdefault(usr, unit_lang)
                        here = usr
                    elif k == K.CALL_EXPR and caller:
                        ref = c.referenced
                        if ref is not None and ref.kind in FUNC:
                            e = (caller, ref.get_usr()); edges.add(e)
                            # is the callee's name written on the call's own source line? (else a macro produced the call)
                            loc = c.location
                            if loc.file:
                                ls = lines_cache.setdefault(loc.file.name, Path(loc.file.name).read_text(errors="replace").splitlines())
                                line = ls[loc.line - 1] if 0 < loc.line <= len(ls) else ""
                                visible[e] = visible.get(e, False) or (ref.spelling.lstrip("~") in line)
                except ValueError:
                    pass
                walk(c, here)
        walk(tu.cursor, None)
    edges = sorted((a, b) for a, b in edges if a in defs and b in defs and a != b)
    macro_only = [list(e) for e in edges if not visible.get(e, True)]
    json.dump({"defs": defs, "edges": [list(e) for e in edges], "macro_only": macro_only, "lang": def_lang,
               "header_langs": {h: sorted(v) for h, v in header_langs.items()}}, open(out, "w"))
    print(f"{repo.name}: {len(files)} TUs, {len(defs)} definitions, {len(edges)} call edges between them ({len(macro_only)} only through a macro)")


if __name__ == "__main__":
    main(sys.argv[1:])
