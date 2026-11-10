"""palette_check.py - colour-blind (protan/deutan) + OKLab distance search used to pick the paperwork legend colours.
Only needed if a legend colour is added or changed. Prints the best order for each candidate extra colour. Reads and writes nothing."""
import itertools, math
MACHADO = {
    "protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
}
def hex2srgb(h): h = h.lstrip('#'); return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
def s2lin(c): return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
def lin(h): return [s2lin(c) for c in hex2srgb(h)]
def oklab(rgb):
    r, g, b = rgb
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s, 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s]
def sim(h, k):
    r, g, b = lin(h); M = MACHADO[k]
    return [min(1, max(0, M[i][0] * r + M[i][1] * g + M[i][2] * b)) for i in range(3)]
def de(h1, h2, k=None):
    a = oklab(sim(h1, k) if k else lin(h1)); b = oklab(sim(h2, k) if k else lin(h2))
    return 100 * math.dist(a, b)
def L_C(h):
    L, a, b = oklab(lin(h)); return L, math.hypot(a, b)
base = ["#0072b2", "#d55e00", "#009e73", "#8e2d9e", "#2fb4c9", "#d9a400", "#cc79a7"]
cands = {'crimson': '#b2182b', 'olive': '#8c8c1f', 'brown': '#8a5a2b', 'lime': '#6aa84f', 'indigo': '#3b3b98', 'teal': '#00796b', 'maroon': '#7a1f3d', 'slate': '#5a6b8c'}
for name, c in cands.items():
    cols = base + [c]; best = None
    for perm in itertools.permutations(cols):
        cv = min(min(de(perm[i], perm[i + 1], k) for k in ('protan', 'deutan')) for i in range(7))
        nv = min(de(perm[i], perm[i + 1]) for i in range(7))
        sc = min(cv * 2, nv)
        if best is None or sc > best[0]: best = (round(sc, 1), round(cv, 1), round(nv, 1), perm)
    print(name, L_C(c)[0].__round__(2), L_C(c)[1].__round__(3), best)
