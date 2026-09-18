#!/usr/bin/env python3
"""Python twin of the dataviz skill's validate_palette.js (node unavailable here).

Same thresholds, same Machado-Oliveira-Fernandes (2009) severity-1.0 transforms,
same OKLab Delta E x100 metric. Usage:
    python validate_palette.py "#aaa111,#bbb222" --mode light [--pairs all] [--surface #fff]
"""
import itertools
import math
import sys

BAND = {"light": (0.43, 0.77), "dark": (0.48, 0.67)}
CHROMA_FLOOR = 0.10
CVD_TARGET, CVD_FLOOR = 8.0, 6.0
NORMAL_FLOOR = 15.0
CONTRAST_MIN = 3.0
DEFAULT_SURFACE = {"light": "#fcfcfb", "dark": "#1a1a19"}

MACHADO = {
    "protan": [[0.152286, 1.052583, -0.204868],
               [0.114503, 0.786281, 0.099216],
               [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968],
               [0.280085, 0.672501, 0.047413],
               [-0.011820, 0.042940, 0.968881]],
    "tritan": [[1.255528, -0.076749, -0.178779],
               [-0.078411, 0.930809, 0.147602],
               [0.004733, 0.691367, 0.303900]],
}


def hex2srgb(h):
    h = h.strip().lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def s2lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin(h):
    return [s2lin(c) for c in hex2srgb(h)]


def rel_lum(h):
    r, g, b = lin(h)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    hi, lo = sorted([rel_lum(a), rel_lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def oklab_from_lin(rgb):
    r, g, b = rgb
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s]


def oklch(h):
    L, a, b = oklab_from_lin(lin(h))
    return L, math.hypot(a, b)


def simulate(h, kind):
    r, g, b = lin(h)
    M = MACHADO[kind]
    return [min(1, max(0, M[i][0] * r + M[i][1] * g + M[i][2] * b)) for i in range(3)]


def delta_e(h1, h2, kind=None):
    a = oklab_from_lin(simulate(h1, kind) if kind else lin(h1))
    b = oklab_from_lin(simulate(h2, kind) if kind else lin(h2))
    return 100 * math.dist(a, b)


def validate(palette, mode="light", surface=None, pairs="adjacent"):
    surface = surface or DEFAULT_SURFACE[mode]
    lo, hi = BAND[mode]
    ok = True
    print(f"\n=== palette {palette}  mode={mode}  surface={surface}  pairs={pairs} ===")

    off = [(c, round(oklch(c)[0], 3)) for c in palette if not (lo <= oklch(c)[0] <= hi)]
    ok &= not off
    print(f"[{'PASS' if not off else 'FAIL'}] Lightness band  "
          + (f"outside L {lo}-{hi}: {off}" if off else f"all {len(palette)} inside L {lo}-{hi}"))

    lowc = [(c, round(oklch(c)[1], 3)) for c in palette if oklch(c)[1] < CHROMA_FLOOR]
    ok &= not lowc
    print(f"[{'PASS' if not lowc else 'FAIL'}] Chroma floor    "
          + (f"below {CHROMA_FLOOR} (reads gray): {lowc}" if lowc else f"all >= {CHROMA_FLOOR}"))

    n = len(palette)
    pairlist = (list(itertools.combinations(range(n), 2)) if pairs == "all"
                else [(i, i + 1) for i in range(n - 1)])
    if pairlist:
        worst = min(((delta_e(palette[i], palette[j], k), k, palette[i], palette[j])
                     for k in ("protan", "deutan") for i, j in pairlist), key=lambda t: t[0])
        d, kind, c1, c2 = worst
        status = "PASS" if d >= CVD_TARGET else ("WARN" if d >= CVD_FLOOR else "FAIL")
        ok &= d >= CVD_FLOOR
        print(f"[{status}] CVD {pairs:8s}  worst dE {d:.1f} ({kind}) {c1} vs {c2}  "
              f"[target {CVD_TARGET}, floor {CVD_FLOOR}]")

        wn = min(((delta_e(palette[i], palette[j]), palette[i], palette[j])
                  for i, j in pairlist), key=lambda t: t[0])
        ok &= wn[0] >= NORMAL_FLOOR
        print(f"[{'PASS' if wn[0] >= NORMAL_FLOOR else 'FAIL'}] Normal vision   "
              f"worst dE {wn[0]:.1f} {wn[1]} vs {wn[2]}  [floor {NORMAL_FLOOR}]")

    for c in palette:
        r = contrast(c, surface)
        print(f"     contrast {c} vs surface = {r:.2f}:1"
              + ("  <- WARN sub-3:1, relief rule (direct labels/table)" if r < CONTRAST_MIN else ""))

    print(f"==> {'OK' if ok else 'HAS FAILURES'}")
    return ok


if __name__ == "__main__":
    pal = [c.strip() for c in sys.argv[1].split(",") if c.strip()]
    args = sys.argv[2:]
    mode = args[args.index("--mode") + 1] if "--mode" in args else "light"
    pairs = args[args.index("--pairs") + 1] if "--pairs" in args else "adjacent"
    surface = args[args.index("--surface") + 1] if "--surface" in args else None
    sys.exit(0 if validate(pal, mode, surface, pairs) else 1)
