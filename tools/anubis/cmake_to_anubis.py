#!/usr/bin/env python3
"""Generate ANUBIS files for vendored third-party code from a CMake build.

Not part of the build. It translates what superdex's CMake configures for the
vendored libraries Anubis has no hand-written rules for (Filament, the imguios
third-party libs, ...) into cc_static_library targets, so they can be
regenerated when the vendored code is upgraded.

Inputs:
  * compile_commands.json of a configured build: the exact per-file flags,
    including directory-level add_definitions() that target properties miss.
  * targets_dump.json, written by dump_targets.cmake (pass it with
    -DCMAKE_PROJECT_INCLUDE=...): each target's raw usage requirements, which
    separate PUBLIC/INTERFACE from PRIVATE and give the dependency edges.

Usage:
  cmake_to_anubis.py <build_dir> <dump_dir> <superdex_root> <platform> <out.json>
then render with --render. Output for a platform is a JSON description; the
renderer merges per-platform descriptions with select() where they differ.
"""
import json, os, re, shlex, sys, collections

SRC_EXT_C = ('.c',)
SRC_EXT_CPP = ('.cpp', '.cc', '.cxx')

def strip_genex(items, platform):
    """Resolve the few generator expressions that appear in the dump."""
    out = []
    for it in items:
        if not it or it.startswith('::@'):
            continue
        it = re.sub(r'\$<LINK_ONLY:(.*)>$', r'\1', it)
        m = re.match(r'\$<BUILD_INTERFACE:(.*)>$', it)
        if m:
            it = m.group(1)
        if it.startswith('$<INSTALL_INTERFACE:'):
            continue
        if it.startswith('$<'):
            # Platform/config conditionals: keep the payload only when it
            # plainly applies (Release, this platform).
            m = re.match(r'\$<\$<(.*)>:(.*)>$', it)
            if not m:
                continue
            cond, val = m.groups()
            pid = {'linux': 'Linux', 'windows': 'Windows'}[platform]
            if 'PLATFORM_ID' in cond and pid not in cond:
                continue
            if 'CONFIG:Debug' in cond:
                continue
            it = val
            if not it or it.startswith('$<'):
                continue
        out.append(it)
    return out

def split_list(s):
    return [x for x in s.split(';') if x] if s else []

# clang-cl spellings -> clang driver spellings (Anubis drives clang, not
# clang-cl, for Windows targets).
CL_DROP = re.compile(r'^(/nologo|--target=.*|/O[12dx]|/Ob[0-3]|-MD|/MD|/MT|/EHsc|-TP|-TC|/Zc:.*|/Zi|/MP|/bigobj|/GS-?|/wd\d+|/W[0-4]|-W[0-4]|/WX-?|/utf-8|--)$')
CL_MAP = {'/fp:fast': ['-ffast-math'], '/Gy': ['-ffunction-sections'], '/Gw': ['-fdata-sections'], '/GR-': ['-fno-rtti'],
          '/W0': ['-w'],
          # clang-cl's /arch:AVX2 implies these; spelled as mochi's Linux flags.
          '/arch:AVX2': ['-mavx2', '-mfma', '-mbmi2', '-mlzcnt', '-mf16c', '-mpclmul']}
# Defines the toolchain/mode sets globally; not per-target state.
GLOBAL_DEFINES = {'_ITERATOR_DEBUG_LEVEL=0'}

def parse_cmd(cmd):
    toks = shlex.split(cmd)
    defs, incs, flags = [], [], []
    i = 1
    while i < len(toks):
        t = toks[i]
        if t in ('-o', '-MF', '-MT', '-MQ', '/imsvc', '-imsvc'):
            # /imsvc <dir> is the MSVC/SDK sysroot; -imsvc<dir> (joined) is a
            # dependency's SYSTEM include and handled below.
            i += 2; continue
        if t.startswith(('/Fo', '/Fd')):
            i += 1; continue
        if t == '--':
            break
        if t == '-c':
            i += 1; continue
        if not t.startswith(('-', '/')) or (t.startswith('/') and t.endswith(SRC_EXT_C + SRC_EXT_CPP)):
            i += 1; continue  # the source file itself
        if t.startswith(('-D', '/D')):
            d = t[2:] or toks[i + 1]
            if d not in GLOBAL_DEFINES:
                defs.append(d)
            i += 1 if t[2:] else 2; continue
        if t in ('-I', '-isystem', '/I'):
            incs.append(toks[i + 1]); i += 2; continue
        if t.startswith(('-I', '/I')):
            incs.append(t[2:]); i += 1; continue
        if t.startswith('-imsvc'):
            incs.append(t[6:]); i += 1; continue
        if t.startswith('/FI'):
            flags += ['-include', t[3:]]; i += 1; continue
        if t.startswith('/clang:'):
            flags.append(t[7:]); i += 1; continue
        if t in ('-std:c++20', '/std:c++20', '/std:c++latest'):
            flags.append('-std=c++20'); i += 1; continue
        if t.startswith(('-std:', '/std:')):
            flags.append('-std=' + t[5:]); i += 1; continue
        if t in CL_MAP:
            flags += CL_MAP[t]; i += 1; continue
        if CL_DROP.match(t):
            i += 1; continue
        if t in ('-MD', '-MMD', '-fPIC', '-fcolor-diagnostics', '-fdiagnostics-color=always') or re.match(r'-O[0-3sz]?$', t):
            i += 1; continue
        flags.append(t); i += 1
    return defs, incs, flags

def main():
    build, dump_dir, root, platform, out = sys.argv[1:6]
    cc = json.load(open(os.path.join(build, 'compile_commands.json')))
    dump = json.load(open(os.path.join(dump_dir, 'targets_dump.json')))
    dump.pop('_end', None)
    per_target = collections.defaultdict(list)
    for e in cc:
        m = re.search(r'CMakeFiles/([^/]+)\.dir/', e['output'])
        if m:
            per_target[m.group(1)].append(e)
    result = {}
    for name, t in dump.items():
        info = {
            'type': t['type'],
            'source_dir': t['source_dir'],
            'public_includes': strip_genex(split_list(t.get('INTERFACE_INCLUDE_DIRECTORIES', '')), platform),
            'public_defines': strip_genex(split_list(t.get('INTERFACE_COMPILE_DEFINITIONS', '')), platform),
            'public_flags': strip_genex(split_list(t.get('INTERFACE_COMPILE_OPTIONS', '')), platform),
            'deps': strip_genex(split_list(t.get('INTERFACE_LINK_LIBRARIES', '') or t.get('LINK_LIBRARIES', '')), platform)
                  + strip_genex(split_list(t.get('LINK_LIBRARIES', '')), platform),
            'files': [],
        }
        for e in per_target.get(name, []):
            if e['file'].endswith('.rc') or (platform == 'windows' and e['file'].endswith('.S')):
                continue  # resource scripts; MASM (see extra_srcs)
            defs, incs, flags = parse_cmd(e['command'])
            info['files'].append({'file': os.path.realpath(e['file']), 'defines': defs, 'includes': incs, 'flags': flags})
        # OBJECT libraries folded in via $<TARGET_OBJECTS:x> become static deps.
        info['deps'] += re.findall(r'\$<TARGET_OBJECTS:([^>]+)>', t.get('SOURCES', ''))
        info['deps'] = list(dict.fromkeys(info['deps']))
        result[name] = info
    json.dump({'platform': platform, 'build': os.path.realpath(build), 'dump_build': os.path.realpath(dump_dir), 'root': os.path.realpath(root), 'targets': result},
              open(out, 'w'), indent=1)



# ----------------------------------------------------------------------------
# Rendering: description JSON -> ANUBIS files
# ----------------------------------------------------------------------------
#
# render(config) where config (a JSON file) has:
#   descs:     {platform: description json path}
#   roots:     target names to start from (their dep closure is emitted)
#   groups:    {anubis_dir (relative to superdex root): [source_dir prefixes]}
#              every emitted target lives in the ANUBIS of the first group
#              whose prefix contains its CMake SOURCE_DIR
#   external:  {cmake target: anubis label} for targets with hand-written rules
#   ignore:    cmake link items to drop (system libs, linker flags)
#   remap:     {build-dir include path suffix: path relative to superdex root}
#   resources: {cmake target: .c file} for targets whose CMake source is a
#              configure-time bin_to_c.py output; the .c is a checked-in
#              `#embed` of the same .bin
#   group_override: {cmake target: anubis_dir} where SOURCE_DIR misleads
#   extra_deps: {platform: {cmake target: [anubis labels]}} for system
#              dependencies CMake finds on the host (X11/GL headers)
#   system_libs: {platform: [names]} CMake link items that are OS import
#              libraries; emitted as public_libraries (`name.lib`)
#   extra_srcs: {platform: {cmake target: [files]}} stand-ins for sources
#              in languages Anubis has no rule for

SYSTEM_LIBS = {'dl', 'm', 'rt', 'pthread', 'Threads::Threads', 'X11::X11'}

def _lang(path):
    return 'c' if path.endswith(SRC_EXT_C) else 'cpp'

def _last_std(flags):
    std = [f for f in flags if f.startswith('-std=')]
    rest = [f for f in flags if not f.startswith('-std=')]
    return rest + std[-1:]

def _clean_flags(flags):
    flags = _last_std(flags)
    if '-w' in flags:
        flags = [f for f in flags if not (f.startswith('-W') and not f.startswith('-Wl,')) or f == '-w']
    return list(dict.fromkeys(flags))

def load_platform(desc, cfg):
    root = desc['root']; build = desc['build']
    def mapdir(p):
        p = os.path.normpath(p)
        b = next((b for b in (build, desc.get('dump_build', build)) if p.startswith(b + '/')), None)
        if b:
            rel = p[len(b) + 1:]
            for k, v in cfg['remap'].items():
                if rel == k:
                    return v
            return None  # build-dir path with nothing to map: drop
        if p.startswith(root + '/') or p == root:
            return os.path.relpath(p, root)
        return None
    tgts = {}
    for name, t in desc['targets'].items():
        files = []
        for f in t['files']:
            files.append(dict(file=os.path.relpath(f['file'], root), defines=f['defines'],
                              includes=[x for x in (mapdir(i) for i in f['includes']) if x],
                              flags=f['flags']))
        tgts[name] = dict(type=t['type'], source_dir=os.path.relpath(os.path.realpath(t['source_dir']), root),
                          public_includes=[x for x in (mapdir(i) for i in t['public_includes']) if x],
                          public_defines=t['public_defines'], public_flags=t['public_flags'],
                          syslibs=[d.lower() + '.lib' for d in t['deps']
                                   if d.lower() in cfg.get('system_libs', {}).get(desc['platform'], [])],
                          deps=[d for d in t['deps'] if d not in SYSTEM_LIBS and not d.startswith(('-', '/'))
                                and d not in cfg.get('ignore', [])],
                          files=files)
    # Sources CMake builds with a language Anubis lacks (bluegl's MASM
    # trampolines) swapped for an equivalent C/C++ file, compiled with the
    # target's other flags.
    for n, extra in cfg.get('extra_srcs', {}).get(desc['platform'], {}).items():
        f0 = tgts[n]['files'][0]
        tgts[n]['files'] += [dict(f0, file=x) for x in extra]
    return tgts

def closure(tgts, roots, cfg):
    seen = []
    stack = list(roots)
    while stack:
        n = stack.pop()
        if n in seen or n in cfg['external'] or n not in tgts:
            continue
        seen.append(n)
        stack.extend(tgts[n]['deps'])
    return seen

def public_of(tgts, n, cfg, memo):
    """Transitive public (includes, defines) of n, as Anubis will propagate it."""
    if n in memo:
        return memo[n]
    memo[n] = (set(), set())
    inc, dfn = set(), set()
    t = tgts.get(n)
    if t:
        inc |= set(t['public_includes']); dfn |= set(t['public_defines'])
        for d in t['deps']:
            if d in tgts:
                a, b = public_of(tgts, d, cfg, memo)
                inc |= a; dfn |= b
    memo[n] = (inc, dfn)
    return memo[n]

def target_spec(tgts, n, cfg):
    t = tgts[n]
    memo = {}
    dep_inc, dep_def = set(), set()
    for d in t['deps']:
        a, b = public_of(tgts, d, cfg, memo)
        dep_inc |= a; dep_def |= b
    by_lang = collections.defaultdict(list)
    for f in t['files']:
        by_lang[_lang(f['file'])].append(f)
    specs = []
    for lang, files in sorted(by_lang.items(), key=lambda kv: kv[0] != 'cpp'):
        incs, defs, flags = [], [], []
        for f in files:
            incs += f['includes']; defs += f['defines']; flags += f['flags']
        incs = [i for i in dict.fromkeys(incs) if i not in dep_inc and i not in t['public_includes']]
        defs = [d for d in dict.fromkeys(defs) if d not in dep_def and d not in t['public_defines'] and d != 'NDEBUG']
        specs.append(dict(lang=lang, srcs=sorted(f['file'] for f in files), private_includes=incs,
                          private_defines=defs, private_flags=_clean_flags(flags)))
    if not specs:
        specs.append(dict(lang='cpp', srcs=[], private_includes=[], private_defines=[], private_flags=[]))
    return specs

def group_of(src_dir, cfg):
    for g, prefixes in cfg['groups'].items():
        for p in prefixes:
            if src_dir == p or src_dir.startswith(p + '/'):
                return g
    raise SystemExit(f'no group for {src_dir}')

def q(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

def fmt_list(items, indent, rel=None, func='RelPaths'):
    if not items:
        return '[]'
    pad = ' ' * indent
    if rel is not None:
        items = [os.path.relpath(i, rel) for i in items]
    body = ''.join(f'{pad}    {q(i)},\n' for i in items)
    if func:
        return f'{func}([\n{body}{pad}])'
    return f'[\n{body}{pad}]'

def per_platform(values, indent, render):
    """values: {platform: list}. Emit one list, or a select() if they differ."""
    plats = sorted(values)
    vals = [values[p] for p in plats]
    if all(v == vals[0] for v in vals):
        return render(vals[0], indent)
    pad = ' ' * indent
    arms = ''.join(f'{pad}    ({p}) = {render(values[p], indent + 4)},\n' for p in plats)
    return f'select(\n{pad}    (target_platform) => {{\n{arms}{pad}    }}\n{pad})'

def render(cfg_path):
    cfg = json.load(open(cfg_path))
    plats = {p: load_platform(json.load(open(path)), cfg) for p, path in cfg['descs'].items()}
    names = []
    for p, tgts in plats.items():
        for n in closure(tgts, cfg['roots'], cfg):
            if n not in names:
                names.append(n)
    files = collections.defaultdict(list)
    for n in sorted(names):
        present = {p: t for p, t in plats.items() if n in t}
        any_t = next(iter(present.values()))[n]
        g = cfg.get('group_override', {}).get(n) or group_of(any_t['source_dir'], cfg)
        files[g].append((n, present))
    for g, entries in files.items():
        out = [f'# GENERATED by tools/anubis/cmake_to_anubis.py from superdex\'s CMake build.\n'
               f'# Do not edit; regenerate when the vendored code changes.\n']
        for n, present in entries:
            res = cfg.get('resources', {}).get(n)
            label_name = re.sub(r'[^A-Za-z0-9_]', '_', n)
            if res:
                if isinstance(res, str):
                    res = {'c': res}
                pub = ''.join(f'    public_include_dirs = RelPaths([{q(os.path.relpath(i, g))}]),\n'
                              for i in res.get('public_includes', []))
                out.append(f'cc_static_library(\n    name = {q(label_name)},\n    lang = "c",\n'
                           f'    srcs = RelPaths([{q(os.path.relpath(res["c"], g))}]),\n' + pub +
                           f'    private_compiler_flags = ["-std=c23", "-w"],\n)\n')
                continue
            specs = {p: target_spec(t, n, cfg) for p, t in present.items()}
            langs = sorted({s['lang'] for v in specs.values() for s in v}, key=lambda l: l != 'cpp')
            for li, lang in enumerate(langs):
                nm = label_name if li == 0 else f'{label_name}_{lang}'
                def field(key):
                    return {p: next((s[key] for s in v if s['lang'] == lang), []) for p, v in specs.items()}
                def deps_for(p):
                    t = present[p][n]
                    labels = []
                    for d in t['deps']:
                        if d in cfg['external']:
                            labels.append(cfg['external'][d])
                        elif d in plats[p]:
                            dg = cfg.get('group_override', {}).get(d) or group_of(plats[p][d]['source_dir'], cfg)
                            dn = re.sub(r'[^A-Za-z0-9_]', '_', d)
                            labels.append(f':{dn}' if dg == g else f'//{dg}:{dn}')
                    if li == 0:
                        labels += cfg.get('extra_deps', {}).get(p, {}).get(n, [])
                    if li == 0 and len(langs) > 1:
                        labels.append(f':{label_name}_{langs[1]}')
                    return list(dict.fromkeys(labels))
                pub = lambda key: {p: (present[p][n][key] if li == 0 else []) for p in present}
                fields = [
                    ('srcs', per_platform(field('srcs'), 4, lambda v, i: fmt_list(v, i, g))),
                    ('deps', per_platform({p: deps_for(p) for p in present}, 4, lambda v, i: fmt_list(v, i, None, 'Targets'))),
                    ('public_include_dirs', per_platform(pub('public_includes'), 4, lambda v, i: fmt_list(v, i, g))),
                    ('public_defines', per_platform(pub('public_defines'), 4, lambda v, i: fmt_list(v, i, None, None))),
                    ('public_libraries', per_platform(pub('syslibs'), 4, lambda v, i: fmt_list(v, i, None, None))),
                    ('public_compiler_flags', per_platform(pub('public_flags'), 4, lambda v, i: fmt_list(v, i, None, None))),
                    ('private_include_dirs', per_platform(field('private_includes'), 4, lambda v, i: fmt_list(v, i, g))),
                    ('private_defines', per_platform(field('private_defines'), 4, lambda v, i: fmt_list(v, i, None, None))),
                    ('private_compiler_flags', per_platform(field('private_flags'), 4, lambda v, i: fmt_list(v, i, None, None))),
                ]
                body = ''.join(f'    {k} = {v},\n' for k, v in fields if v != '[]')
                out.append(f'cc_static_library(\n    name = {q(nm)},\n    lang = {q(lang)},\n'
                           + ('' if 'srcs =' in body else '    srcs = [],\n') + body + ')\n')
        path = os.path.join(cfg['superdex_root'], g, 'ANUBIS')
        open(path, 'w').write('\n'.join(out))
        print(f'wrote {path} ({len(entries)} targets)')

if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == '--render':
    render(sys.argv[2])

elif __name__ == '__main__':
    main()
