#!/usr/bin/env python3
"""Add declared-header lists to ANUBIS files that predate them.

Anubis fails a compile that reads a file its target didn't declare. This
adds, to every C/C++ rule that lacks them:

  public_headers            headers under each `public_include_dirs` entry
  private_headers/headers   headers under each private include dir and next
                            to the sources

as globs over header-like extensions (only patterns that match a file). Broad on purpose: a starting point
that can be narrowed by hand. Rules that already have a list are left alone.

    tools/anubis/add_header_lists.py path/to/ANUBIS ...
"""
import glob
import os
import re
import sys

# `h*`: .h .hpp .hxx .hh. OpenCASCADE adds .lxx .gxx .pxx.
EXTS = ["h*", "inc", "inl", "ipp", "def"]
OCCT_EXTS = ["h*", "lxx", "gxx", "pxx"]
RULES = ("cc_static_library", "cc_shared_library", "cc_binary", "py_extension")
STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')


def fields(block):
    """{name: text} for the fields at 4-space indent in a rule block."""
    out, name = {}, None
    for line in block.splitlines(keepends=True):
        m = re.match(r"    (\w+) = ", line)
        if m:
            name = m.group(1)
            out[name] = ""
        if name:
            out[name] += line
    return out


def strings(text):
    # Drop comments first: a `#` inside a string doesn't occur in these files.
    text = "\n".join(l.split("#")[0] for l in text.splitlines())
    return STRING.findall(text)


def src_dir(pattern):
    parts = pattern.split("/")[:-1]
    keep = []
    for p in parts:
        if any(c in p for c in "*?["):
            return "/".join(keep), True
        keep.append(p)
    return "/".join(keep), False


def patterns(dirs):
    """dirs: {dir: recursive}. Nested dirs fold into a recursive parent."""
    out = []
    for d, rec in sorted(dirs.items()):
        parent, covered = d, False
        while parent != "." and not covered:
            parent = parent.rpartition("/")[0] or "."
            covered = dirs.get(parent, False)
        if covered:
            continue
        prefix = "" if d in ("", ".") else d + "/"
        for e in OCCT_EXTS if d.startswith("occt/") else EXTS:
            out.append(f"{prefix}**/*.{e}" if rec else f"{prefix}*.{e}")
    return out


def glob_field(name, pats, root):
    # Anubis rejects a glob that matches nothing; keep patterns that match.
    pats = [p for p in pats if glob.glob(os.path.join(root, p), recursive=True)]
    if not pats:
        return f"    {name} = [],\n"
    body = "".join(f'        "{p}",\n' for p in pats)
    return f"    {name} = glob([\n{body}    ]),\n"


def process(text, root):
    out, pos = [], 0
    for m in re.finditer(r"^(%s)\(\n(.*?)^\)\n" % "|".join(RULES), text, re.S | re.M):
        rule, block = m.group(1), m.group(2)
        f = fields(block)
        binary = rule == "cc_binary"
        add = ""
        if not binary and "public_include_dirs" in f and "public_headers" not in f:
            dirs = {d.rstrip("/") or ".": True for d in strings(f["public_include_dirs"])}
            add += glob_field("public_headers", patterns(dirs), root)
        private_name = "headers" if binary else "private_headers"
        if private_name not in f:
            dirs = {}
            inc = f.get("include_dirs" if binary else "private_include_dirs", "")
            for d in strings(inc):
                dirs[d.rstrip("/") or "."] = True
            srcs = re.sub(r"excludes = \[.*?\]", "", f.get("srcs", ""), flags=re.S)
            for s in strings(srcs):
                d, wild = src_dir(s)
                key = d or "."
                # Next to the sources; recursive unless they sit in the
                # ANUBIS file's own directory.
                dirs[key] = dirs.get(key, False) or wild or key != "."
            if dirs:
                add += glob_field(private_name, patterns(dirs), root)
        out.append(text[pos:m.start(2)])
        if add and not block.rstrip().endswith(","):
            block = block.rstrip() + ",\n"
        out.append(block + add)
        pos = m.end(2)
    out.append(text[pos:])
    return "".join(out)


for path in sys.argv[1:]:
    old = open(path).read()
    new = process(old, os.path.dirname(os.path.abspath(path)))
    if new != old:
        open(path, "w").write(new)
        print("updated", path)
