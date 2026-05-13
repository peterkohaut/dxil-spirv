#!/usr/bin/env python3
"""SM 6.9 sweep: recompile the public shader corpus at -T xx_6_9 and pipe each
through dxil-spirv to surface bugs around SM 6.9 (new long-vector ops, new
validator metadata, DXIL version bumps).

Buckets failures into:
  - dxc:      DXC could not produce DXIL at SM 6.9 (HLSL-level reason)
  - spirv:    DXC succeeded but dxil-spirv crashed / errored / failed validation

Reuses the per-filename dot-token -> CLI flag mapping from test_shaders.py.

With --ll-dir, also generates LLVM IR (.ll) files for each shader compiled at
both the original SM version (inferred from the filename, defaulting to 6.2)
and the forced SM 6.9 version.  Files are written as:
  <ll-dir>/<rel-path>.orig.ll   — original SM
  <ll-dir>/<rel-path>.sm69.ll   — forced SM 6.9
"""
import os
import re
import sys
import subprocess
import tempfile
import multiprocessing
import json
import argparse

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DXC = REPO + '/external/dxc-build/bin/dxc'
DXIL_SPIRV = REPO + '/build/dxil-spirv'

STAGE_PREFIX_BY_EXT = {
    '.vert': 'vs',
    '.frag': 'ps',
    '.comp': 'cs',
    '.tesc': 'hs',
    '.tese': 'ds',
    '.geom': 'gs',
    '.mesh': 'ms',
    '.task': 'as',
    '.rmiss': 'lib',
    '.rint':  'lib',
    '.rgen':  'lib',
    '.rhit':  'lib',
    '.rcall': 'lib',
    '.rany':  'lib',
    '.rclosest': 'lib',
}

_SM_TOKEN_RE = re.compile(r'\.sm6([0-9])\.')


def _sm_minor(shader_path):
    """Return the SM 6.x minor version implied by the filename, or 2 (default)."""
    m = _SM_TOKEN_RE.search(shader_path)
    return int(m.group(1)) if m else 2


def _stage_prefix(shader_path):
    _, ext = os.path.splitext(shader_path)
    if '.node.' in shader_path and ext == '.comp':
        return 'lib'
    return STAGE_PREFIX_BY_EXT.get(ext)


def get_target(shader_path):
    """Forced SM 6.9 target (sweep mode)."""
    prefix = _stage_prefix(shader_path)
    return f'{prefix}_6_9' if prefix else None


def get_original_target(shader_path):
    """Natural SM target inferred from the filename."""
    prefix = _stage_prefix(shader_path)
    if prefix is None:
        return None, None
    minor = _sm_minor(shader_path)
    return f'{prefix}_6_{minor}', minor


def _common_dxc_flags(shader):
    flags = []
    if '.denorm-ftz.' in shader:
        flags += ['-denorm', 'ftz']
    if '.denorm-preserve.' in shader:
        flags += ['-denorm', 'preserve']
    if '.no-legacy-cbuf-layout.' in shader:
        flags += ['-no-legacy-cbuf-layout']
    return flags


def make_dxc_cmd(shader, target):
    """DXC command for the forced SM 6.9 pass (always enables 16-bit types)."""
    return ([DXC, '-Qstrip_reflect', '-Qstrip_debug', '-Vd', '-T', target,
             '-enable-16bit-types'] + _common_dxc_flags(shader))


def make_dxc_cmd_orig(shader, target, sm_minor):
    """DXC command for the original-SM pass (omits -enable-16bit-types below 6.2)."""
    cmd = [DXC, '-Qstrip_reflect', '-Qstrip_debug', '-Vd', '-T', target]
    if sm_minor >= 2:
        cmd += ['-enable-16bit-types']
    cmd += _common_dxc_flags(shader)
    return cmd


def make_dxc_ll_cmd(shader, target, sm_minor=9):
    """DXC command for direct .ll generation via -Fc (no binary output needed)."""
    cmd = [DXC, '-Vd', '-T', target]
    if sm_minor >= 2:
        cmd += ['-enable-16bit-types']
    cmd += _common_dxc_flags(shader)
    return cmd


def make_dxil_spirv_cmd(shader, dxil_path, validate=True):
    cmd = [DXIL_SPIRV, dxil_path, '--vertex-input', 'ATTR', '0', '--asm']
    if '.bc.' in shader:
        cmd += ['--raw-llvm']
    cmd += ['--allow-arithmetic-relaxed-precision', '--subgroup-size', '32', '64']

    if '.root-constant.' in shader:
        cmd += ['--root-constant', '0', '0', '4', '12',
                '--root-constant', '1', '0', '0', '16']
    if '.stream-out.' in shader:
        cmd += ['--stream-output', 'SV_Position', '0', '16', '32', '1',
                '--stream-output', 'StreamOut', '0', '0', '32', '0',
                '--stream-output', 'StreamOut', '1', '0', '16', '1']
    if '.rt-swizzle.' in shader:
        cmd += ['--output-rt-swizzle', '0', 'wxyz',
                '--output-rt-swizzle', '1', 'yxwz']
    if '.bindless.' in shader:
        cmd.append('--bindless')
    if '.nobda.' in shader:
        cmd.append('--no-bda')
    if '.local-root-signature.' in shader:
        cmd.append('--local-root-signature')
    if '.uav-counter-texel-buffer.' in shader:
        cmd.append('--uav-counter-force-texel-buffer')
    if '.uav-counter-ssbo.' in shader:
        cmd.append('--uav-counter-force-ssbo')
    if '.inline-ubo.' in shader:
        cmd += ['--root-constant-inline-ubo', '6', '1']
    if '.cbv-as-ssbo.' in shader:
        cmd.append('--bindless-cbv-as-ssbo')
    if validate and '.invalid.' not in shader:
        cmd.append('--validate')
    if '.demote-to-helper.' in shader:
        cmd.append('--enable-shader-demote')
    if '.i8dot.' in shader:
        cmd.append('--enable-shader-i8-dot')
    if '.dual-source-blending.' in shader:
        cmd.append('--enable-dual-source-blending')
    if '.ssbo.' in shader:
        cmd += ['--ssbo-uav', '--ssbo-srv']
    if '.ssbo-rtas.' in shader:
        cmd.append('--ssbo-rtas')
    if '.input-attachment.' in shader:
        cmd.append('--input-attachments')
    if '.raw-va-stride-offset.' in shader:
        cmd += ['--physical-address-descriptor-indexing', '4', '3']
    if '.ssbo-align.' in shader:
        cmd += ['--ssbo-alignment', '64']
    if '.typed-uav-without-format.' in shader:
        cmd.append('--typed-uav-read-without-format')
    if '.typed-buffer-offset.' in shader:
        cmd += ['--bindless', '--bindless-typed-buffer-offsets']
    if '.root-descriptor.' in shader:
        cmd += ['--root-descriptor', 'cbv', '0', '0',
                '--root-descriptor', 'srv', '0', '0',
                '--root-descriptor', 'uav', '0', '0',
                '--root-descriptor', 'uav', '0', '1']
    if '.offset-layout.' in shader:
        cmd += ['--bindless-offset-buffer-layout', '0', '1', '2']
    if '.lib.' in shader:
        cmd += ['--debug-all-entry-points']
    if '.16bit-io.' in shader:
        cmd += ['--storage-input-output-16bit']
    if '.descriptor-qa.' in shader:
        cmd += ['--descriptor-qa', '10', '10', 'deadbeef']
    if '.native-fp16.' in shader:
        cmd += ['--min-precision-native-16bit']
    if '.invariant.' in shader:
        cmd += ['--invariant-position']
    if '.partitioned.' in shader:
        cmd += ['--subgroup-partitioned-nv']
    if '.noderivs.' in shader:
        cmd += ['--no-compute-shader-derivatives']
    if '.quad-maximal-reconvergence.' in shader:
        cmd += ['--quad-control-maximal-reconvergence']
    if '.raw-access-chains.' in shader:
        cmd += ['--raw-access-chains-nv']
    if '.extended-robustness.' in shader:
        cmd += ['--extended-robustness']
    if 'bda-instrumentation.' in shader:
        cmd += ['--instruction-instrumentation', '4', '0', '2', 'abcd']
    if '.auto-group-shared-barrier.' in shader:
        cmd += ['--shader-quirk', '8']
    if '.vkmm.' in shader:
        cmd += ['--vkmm']
    if '.full-wmma.' in shader:
        cmd += ['--full-wmma', '1', '1']
    if '.nv-coopmat2.' in shader:
        cmd += ['--full-wmma', '0', '1']
    if '.nvapi.' in shader:
        cmd += ['--nvapi', '127', '0']
    if '.heap-robustness-cbv.' in shader:
        cmd += ['--meta-descriptor', '0', '3', '10', '20']
    if '.heap-raw-va-cbv.' in shader:
        cmd += ['--meta-descriptor', '1', '4', '10', '21']
    if '.heap-robustness.' in shader:
        cmd += ['--descriptor-heap-robustness']
    if '.view-instancing.' in shader:
        cmd += ['--view-instancing', '--meta-descriptor', '2', '3', '10', '22']
    if '.view-instance-mask.' in shader:
        cmd += ['--meta-descriptor', '3', '3', '10', '23']
    if '.last-pre-raster.' in shader:
        cmd += ['--view-instancing-last-pre-rasterization-stage']
    if '.view-instancing-multiview.' in shader:
        cmd += ['--view-index-to-view-instance-spec-id', '1000']
    if '.view-instancing-viewport-offset.' in shader:
        cmd += ['--view-instance-to-viewport-spec-id', '1001']
    if '.mixed-float-dot-product.' in shader:
        cmd += ['--mixed-float-dot-product']
    return cmd


def run(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout)
        return p.returncode, p.stdout.decode('utf-8', errors='replace'), p.stderr.decode('utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        return 124, '', 'TIMEOUT'
    except Exception as e:
        return 125, '', f'SUBPROCESS_ERROR: {e}'


def _write(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def output_paths_for(shader, ll_dir, folder):
    """Return (orig_base, sm69_base) path prefixes; append .ll or .dxil as needed."""
    rel = os.path.relpath(shader, folder)
    base = os.path.join(ll_dir, rel)
    return base + '.orig', base + '.sm69'


def test_one(args_tuple):
    shader, ll_dir, folder = args_tuple
    target = get_target(shader)
    if target is None:
        return {'shader': shader, 'status': 'skip', 'reason': 'no-target'}

    # .bc. shaders are pre-baked DXIL; pointless to recompile at 6.9.
    if '.bc.' in shader:
        return {'shader': shader, 'status': 'skip', 'reason': 'raw-bc'}

    # shaders explicitly targeting SM 6.0 are not candidates for SM 6.9 forcing.
    if '.sm60.' in shader:
        return {'shader': shader, 'status': 'skip', 'reason': 'sm60'}

    result = {'shader': shader}

    orig_target, sm_minor = get_original_target(shader) if ll_dir else (None, None)

    if ll_dir and orig_target:
        orig_base, sm69_base = output_paths_for(shader, ll_dir, folder)
        os.makedirs(os.path.dirname(orig_base), exist_ok=True)
        sm69_dxil = sm69_base + '.dxil'
        orig_dxil = orig_base + '.dxil'
    else:
        sm69_dxil = None
        orig_dxil = None
        orig_base = None
        sm69_base = None

    # --- SM 6.9 pass: compile, save DXIL, test with dxil-spirv ---
    dxil_fd, tmp_dxil = tempfile.mkstemp(suffix='.dxil')
    os.close(dxil_fd)
    try:
        dxc_cmd = make_dxc_cmd(shader, target) + ['-Fo', tmp_dxil, shader]
        rc, out, err = run(dxc_cmd)
        if rc != 0:
            result.update({'status': 'dxc-fail', 'target': target,
                           'stderr': (err or out)[-800:], 'cmd': dxc_cmd})
            return result

        if sm69_dxil:
            os.replace(tmp_dxil, sm69_dxil)
            dxil_for_spirv = sm69_dxil
        else:
            dxil_for_spirv = tmp_dxil

        spv_cmd = make_dxil_spirv_cmd(shader, dxil_for_spirv)
        rc, out, err = run(spv_cmd)
        if rc != 0:
            result.update({'status': 'spirv-fail', 'target': target,
                           'rc': rc, 'stderr': (err or out)[-1500:], 'cmd': spv_cmd})
            if sm69_base:
                _, out_novalidate, _ = run(make_dxil_spirv_cmd(shader, dxil_for_spirv, validate=False))
                if out_novalidate:
                    _write(sm69_base + '.spvasm', out_novalidate)
        else:
            result['status'] = 'ok'
            if sm69_base and out:
                _write(sm69_base + '.spvasm', out)
    finally:
        try:
            os.remove(tmp_dxil)
        except OSError:
            pass

    if not ll_dir or orig_target is None:
        return result

    # --- Original SM DXIL + SPIR-V assembly ---
    rc, _, _ = run(make_dxc_cmd_orig(shader, orig_target, sm_minor) + ['-Fo', orig_dxil, shader])
    if rc == 0:
        rc, out, _ = run(make_dxil_spirv_cmd(shader, orig_dxil))
        if rc != 0:
            _, out, _ = run(make_dxil_spirv_cmd(shader, orig_dxil, validate=False))
        if out:
            _write(orig_base + '.spvasm', out)

    # --- .ll files (with debug info) ---
    run(make_dxc_ll_cmd(shader, target, sm_minor=9) + ['-Fc', sm69_base + '.ll', shader])
    run(make_dxc_ll_cmd(shader, orig_target, sm_minor) + ['-Fc', orig_base + '.ll', shader])

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--folder', default=os.path.join(REPO, 'shaders'))
    ap.add_argument('--out', default='/tmp/sm69_results.json')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--jobs', type=int, default=multiprocessing.cpu_count())
    ap.add_argument('--ll-dir', default='',
                    help='Directory to write .orig.ll and .sm69.ll files into. '
                         'Skipped when empty (default).')
    args = ap.parse_args()

    ll_dir = args.ll_dir

    all_files = []
    for root, dirs, files in os.walk(args.folder):
        # Skip directories that don't contain HLSL inputs.
        dirs[:] = [d for d in dirs if d not in ('reference', 'asm')]
        for f in files:
            if f.startswith('.'):
                continue
            ext = os.path.splitext(f)[1]
            if ext not in STAGE_PREFIX_BY_EXT:
                continue
            all_files.append(os.path.join(root, f))
    all_files.sort()
    if args.limit:
        all_files = all_files[:args.limit]

    label = 'with .ll generation' if ll_dir else ''
    print(f'Sweeping {len(all_files)} shaders with -T xx_6_9 on {args.jobs} workers {label}',
          file=sys.stderr)

    work = [(s, ll_dir, args.folder) for s in all_files]

    results = []
    with multiprocessing.Pool(args.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(test_one, work, chunksize=4)):
            results.append(r)
            if (i + 1) % 100 == 0:
                print(f'  {i+1}/{len(all_files)}', file=sys.stderr)

    by_status = {}
    for r in results:
        by_status.setdefault(r['status'], []).append(r)

    print_summary(results, by_status)

    with open(args.out, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nWrote {args.out}', file=sys.stderr)


def first_error(r):
    for line in r.get('stderr', '').splitlines():
        s = line.strip()
        if s.startswith('[ERROR]') or 'Assertion' in s or 'stack smashing' in s:
            return s
    return '<no error>'


def print_summary(results, by_status):
    col = 12

    print('\n=== Status ===', file=sys.stderr)
    order = ['ok', 'spirv-fail', 'dxc-fail', 'skip']
    all_keys = order + [k for k in sorted(by_status) if k not in order]
    total = len(results)
    for k in all_keys:
        if k not in by_status:
            continue
        n = len(by_status[k])
        print(f'  {k:<{col}} {n:>5}', file=sys.stderr)
    print(f'  {"total":<{col}} {total:>5}', file=sys.stderr)

    spirv_fails = by_status.get('spirv-fail', [])
    if spirv_fails:
        print(f'\n=== spirv-fail clusters ({len(spirv_fails)} shaders) ===', file=sys.stderr)
        clusters = {}
        for r in spirv_fails:
            clusters.setdefault(first_error(r), []).append(r['shader'])
        for err, shaders in sorted(clusters.items(), key=lambda x: -len(x[1])):
            print(f'  {len(shaders):>3}  {err}', file=sys.stderr)
            for s in shaders:
                print(f'         {os.path.relpath(s, REPO)}', file=sys.stderr)

    dxc_fails = by_status.get('dxc-fail', [])
    if dxc_fails:
        print(f'\n=== dxc-fail clusters ({len(dxc_fails)} shaders) ===', file=sys.stderr)
        clusters = {}
        for r in dxc_fails:
            key = '<no error>'
            for line in r.get('stderr', '').splitlines():
                s = line.strip()
                if not s or s.startswith('warning'):
                    continue
                # strip leading "path:line:col: " prefix from DXC errors
                if ': error:' in s:
                    s = s[s.index(': error:') + 2:]
                elif ': fatal error:' in s:
                    s = s[s.index(': fatal error:') + 2:]
                key = s[:100]
                break
            clusters.setdefault(key, []).append(r['shader'])
        for err, shaders in sorted(clusters.items(), key=lambda x: -len(x[1])):
            print(f'  {len(shaders):>3}  {err}', file=sys.stderr)
            for s in shaders:
                print(f'         {os.path.relpath(s, REPO)}', file=sys.stderr)


if __name__ == '__main__':
    main()
