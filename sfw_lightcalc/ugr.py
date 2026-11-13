"""Abbagliamento molesto: UGR con il metodo tabellare CIE 117 (stesso approccio dei software di calcolo).

    UGR = 8 · log10( 0,25 / Lb · Σ Ls² · ω / p² )

Ls luminanza media dell'apparecchio verso l'occhio (I / area proiettata), ω angolo solido
dell'apparecchio visto dall'osservatore, p indice di posizione di Guth, Lb luminanza di sfondo.
Il valore riportato è quello della direzione di vista peggiore, mediato sugli osservatori.
"""
from __future__ import annotations

import math

from .geometry import Point2, bbox, contains, edge_distance, open_ring
from .ies import Photometry


def guth_position_index(sigma_deg: float, tau_deg: float) -> float:
    """Indice di posizione di Guth (approssimazione analitica). sigma: scarto angolare dalla
    linea di vista; tau: angolo dalla verticale nel piano perpendicolare alla vista."""
    if sigma_deg <= 0.1:
        return 1.0
    s, t = sigma_deg, tau_deg
    v = ((35.2 - 0.31889 * t - 1.22 * math.exp(-2 * t / 9)) * s * 1e-3
         + (21 + 0.26667 * t - 0.002963 * t * t) * s * s * 1e-5)
    try:
        return max(1.0, math.exp(v))
    except OverflowError:
        return 1e9


def observers(poly: list[Point2], max_obs: int = 25, margin: float = 0.5) -> list[Point2]:
    poly = open_ring(poly)
    minx, miny, maxx, maxy = bbox(poly)
    a = (maxx - minx) * (maxy - miny)
    st = max(0.6, math.sqrt(max(a, 0.1)) / 3)
    out = []
    y = miny + st / 2
    while y < maxy and len(out) < max_obs:
        x = minx + st / 2
        while x < maxx and len(out) < max_obs:
            if contains(poly, x, y) and edge_distance(poly, x, y) >= margin:
                out.append((x, y))
            x += st
        y += st
    if not out:
        out = [((minx + maxx) / 2, (miny + maxy) / 2)]
    return out


def ugr(positions: list[Point2], ph: Photometry, poly: list[Point2], mount_z: float,
        background_luminance: float, eye_z: float = 1.2) -> float | None:
    if background_luminance <= 0 or not positions:
        return None
    area = ph.luminous_area_m2
    obs = observers(poly)
    per_direction = []
    for vx, vy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        vals = []
        for ox, oy in obs:
            total = 0.0
            for lx, ly in positions:
                dx, dy, dz = lx - ox, ly - oy, mount_z - eye_z
                r2 = dx * dx + dy * dy + dz * dz
                r = math.sqrt(r2)
                if r < 0.2 or dx * vx + dy * vy < -0.05 * r:      # fuori dal campo visivo
                    continue
                gamma = math.degrees(math.acos(max(-1.0, min(1.0, dz / r))))
                cg = math.cos(math.radians(gamma))
                if cg <= 0.03:
                    continue
                ap = area * cg
                i = ph.intensity(gamma, math.degrees(math.atan2(-dy, -dx)))
                if i <= 0:
                    continue
                ls = i / ap
                omega = ap / r2
                ux, uy, uz = dx / r, dy / r, dz / r
                cos_sig = max(-1.0, min(1.0, ux * vx + uy * vy))
                sigma = math.degrees(math.acos(cos_sig))
                px, py, pz = ux - cos_sig * vx, uy - cos_sig * vy, uz
                pn = math.sqrt(px * px + py * py + pz * pz)
                tau = math.degrees(math.acos(max(-1.0, min(1.0, pz / pn)))) if pn > 1e-6 else 0.0
                p = guth_position_index(sigma, tau)
                total += ls * ls * omega / (p * p)
            if total > 0:
                vals.append(8 * math.log10(0.25 / background_luminance * total))
        if vals:
            per_direction.append(sum(vals) / len(vals))
    return round(max(per_direction), 1) if per_direction else None
