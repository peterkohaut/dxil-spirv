---
name: sm69-sweep
description: Use when the user wants to find dxil-spirv bugs surfaced by Shader Model 6.9 — recompiles the entire public shader corpus at -T xx_6_9 and pipes each DXIL through dxil-spirv, then buckets failures. Trigger phrases include "run the SM 6.9 sweep", "test SM 6.9 against the corpus", "what breaks at SM 6.9", "find SM 6.9 bugs", or any request to re-validate the converter against the SM 6.9 long-vector / cooperative-vector / SER opcodes.
---

# SM 6.9 sweep

This skill drives `scripts/sm69_sweep.py` — a regression-style sweep that exists specifically to surface SM 6.9 gaps in dxil-spirv. Use it whenever the user wants to test SM 6.9 coverage or re-check progress after changes to the converter.

## What it does

For every HLSL source under `shaders/` (excluding `shaders/reference/` and `shaders/asm/`), the sweep:

1. Recompiles with the bundled DXC forced to the SM 6.9 profile of the matching stage (`vs_6_9`, `ps_6_9`, `cs_6_9`, `hs_6_9`, `ds_6_9`, `gs_6_9`, `ms_6_9`, `as_6_9`, `lib_6_9`).
2. Mirrors the per-filename dot-token flag detection from `test_shaders.py`, so `.bindless.`, `.ssbo.`, `.root-constant.`, `.nvapi.`, etc. activate the right `dxil-spirv` flags.
3. Pipes the DXIL through `build/dxil-spirv --asm --validate [...flags]`.
4. Buckets each shader as `ok`, `dxc-fail` (HLSL-level reason, not a converter bug), or `spirv-fail` (real converter bug).

This is **not** a regression test — there's no golden-output check. The pass/fail signal is "did dxil-spirv produce a SPIR-V module that passes `spirv-val`?"

## Preconditions

- `build/dxil-spirv` exists (run `cmake --build build` if not).
- `external/dxc-build/bin/dxc` exists (run `./checkout_dxc.sh && ./build_dxc.sh` if not).
- DXC's bundled version supports `xx_6_9` profiles (the one checked in by `checkout_dxc.sh` does).

## Running the sweep

```sh
# Full sweep, parallel across all cores:
python3 scripts/sm69_sweep.py --jobs 16 --out /tmp/sm69_results.json

# Quick smoke test on the first N shaders:
python3 scripts/sm69_sweep.py --limit 20

# Sweep a specific subfolder by passing --folder:
python3 scripts/sm69_sweep.py --folder shaders/vectorization
```

The driver writes its raw per-shader results as JSON to `--out` (default `/tmp/sm69_results.json`) and prints a per-status count to stderr. A full sweep on the public corpus is ~780 shaders and runs in roughly a minute on 16 cores.

## Reading the results

After a run, cluster failures by first `[ERROR]` line to identify bug patterns. Paste-ready snippet:

```python
import json, collections
r = json.load(open('/tmp/sm69_results.json'))
spv = [x for x in r if x['status'] == 'spirv-fail']
def first(x):
    for l in x.get('stderr','').splitlines():
        s = l.strip()
        if s.startswith('[ERROR]') or 'Assertion' in s or 'stack smashing' in s:
            return s
    return '<no error>'
for k, v in collections.Counter(first(x) for x in spv).most_common(30):
    print(f'{v:5d}  {k}')
```

## Reproducing a single failure

```sh
DXIL=$(mktemp --suffix=.dxil)
./external/dxc-build/bin/dxc -Qstrip_reflect -Qstrip_debug -Vd \
    -T <STAGE>_6_9 -enable-16bit-types -Fo $DXIL <shader>
./build/dxil-spirv $DXIL --asm --validate [...per-shader flags...]
rm -f $DXIL
```

The per-shader flag set is what `scripts/sm69_sweep.py:make_dxil_spirv_cmd` would produce; check that function for the exact mapping (e.g. `.ssbo.` → `--ssbo-uav --ssbo-srv`, `.nvapi.` → `--nvapi 127 0`, etc.).

## Known failure clusters (May 2026 baseline on `ser`)

When evaluating new converter changes, expect these as the dominant remaining bug categories. If you see new patterns, that's a regression worth investigating.

| Bucket | Example shader | Root cause |
|---|---|---|
| `int-op-on-fp-vector` (~195) | `shaders/llvm-builtin/fsub.frag` | DXC SM 6.9 keeps native `<N x float>` vectors; LLVM-builtin dispatch in dxil-spirv picks an integer SPIR-V op. |
| `op-MaxArguments-overflow` (3) | `shaders/vectorization/copy-float4x4.ssbo.comp` | `ir.hpp:93` hardcodes `MaxArguments=13`; long-vector ops with ≥14 args overrun a fixed-size array (`*** stack smashing detected ***`). |
| `typevector-1-component` (3) | `shaders/stages/mesh-basic.mesh` | Converter emits `OpTypeVector %float 1`. |
| `compositeextract-overtraverse` (2) | `shaders/nvapi/shuffle.nvapi.ssbo.comp` | `OpCompositeExtract` traverses past a scalar leaf. |
| Other one-offs | — | `Vector16` capability missing, composite-constituent count mismatch, undefined ID, pre-existing fp16/root-constant limitations. |

For the full list and per-cluster shader inventory, see `sm69_report.md` at the repo root.

## DXC-side failures

47 shaders fail at DXC (not dxil-spirv). 41 are SM 6.9 spec changes requiring `[raypayload]` on raytracing payload structs. These are **not** converter bugs — flag them as informational only.

## When to re-run

- After changes to `opcodes/dxil/*.cpp` or `opcodes_dxil_builtins.cpp` (new opcode handlers).
- After changes to `bc/` (LLVM bitcode reader — especially vector type handling).
- After changes to `ir.hpp` / `spirv_module.*` (e.g. lifting `MaxArguments`).
- After bumping the bundled DXC (DXC may emit new DXIL forms).
- Before claiming "SM 6.9 is done."
