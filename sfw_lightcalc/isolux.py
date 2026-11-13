"""Mappe isolux: curve di illuminamento a falsi colori sul piano di lavoro, con quote e apparecchi.

La griglia dei valori calcolati si interpola su un raster fine mascherato al poligono del
locale; si disegnano aree piene, isolinee etichettate, contorno, quote dei lati e simboli
degli apparecchi. Restituisce l'immagine PNG come bytes.
"""
from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.path import Path  # noqa: E402
from scipy.interpolate import griddata  # noqa: E402

FALSE_COLOURS = LinearSegmentedColormap.from_list("isolux", [
    (0.00, "#2b2d7f"), (0.15, "#2e5fb0"), (0.32, "#2e8bc0"), (0.48, "#3fbf8f"),
    (0.63, "#8fd14f"), (0.75, "#f2e600"), (0.87, "#f39c12"), (1.00, "#c0392b"),
])


def nice_levels(vmin: float, vmax: float, n: int = 12) -> list[float]:
    """Livelli delle isolinee a passo «tondo» (1, 2, 2,5, 5, 10 per potenze di dieci)."""
    if vmax <= vmin:
        vmax = vmin + 1.0
    raw = (vmax - vmin) / n
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    step = min([1, 2, 2.5, 5, 10], key=lambda s: abs(s * mag - raw)) * mag
    v = math.floor(vmin / step) * step
    out = []
    while v <= vmax + step:
        out.append(round(v, 3))
        v += step
    return [x for x in out if x >= vmin - step]


def _dimensions(ax, poly: np.ndarray, diag: float) -> None:
    n = len(poly)
    a = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))
    counter_clockwise = a > 0
    off, tick, col = 0.085 * diag, 0.022 * diag, "#333333"
    for i in range(n):
        p1, p2 = poly[i], poly[(i + 1) % n]
        edge = p2 - p1
        L = float(np.hypot(*edge))
        if L < 0.12:
            continue
        d = edge / L
        right = np.array([d[1], -d[0]])
        out = right if counter_clockwise else -right
        a1, b1 = p1 + out * off, p2 + out * off
        ax.plot([a1[0], b1[0]], [a1[1], b1[1]], color=col, lw=0.7, zorder=8)
        ax.plot([p1[0], a1[0]], [p1[1], a1[1]], color=col, lw=0.4, alpha=0.7, zorder=8)
        ax.plot([p2[0], b1[0]], [p2[1], b1[1]], color=col, lw=0.4, alpha=0.7, zorder=8)
        t = (d + out) * tick
        for c in (a1, b1):
            ax.plot([c[0] - t[0], c[0] + t[0]], [c[1] - t[1], c[1] + t[1]], color=col, lw=0.7, zorder=8)
        ang = math.degrees(math.atan2(d[1], d[0]))
        ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
        lab = (a1 + b1) / 2 + out * tick * 1.4
        ax.text(lab[0], lab[1], f"{L:.2f}", ha="center", va="center", fontsize=6.5, rotation=ang,
                rotation_mode="anchor", color=col, zorder=9,
                bbox=dict(boxstyle="square,pad=0.05", fc="white", ec="none", alpha=0.75))


def render(polygon: list, grid: list[list[float]], luminaires: list[list[float]] | None = None,
           title: str | None = None, resolution: int = 260) -> bytes:
    poly = np.asarray(polygon, dtype=float)
    pts = np.asarray(grid, dtype=float)
    if len(poly) < 3 or len(pts) < 1:
        raise ValueError("servono un poligono e almeno un punto di calcolo")
    xy, z = pts[:, :2], pts[:, 2]
    minx, miny = poly.min(axis=0)
    maxx, maxy = poly.max(axis=0)
    w, h = maxx - minx, maxy - miny
    diag = max(w, h)
    pad = 0.16 * diag

    gx, gy = np.meshgrid(np.linspace(minx, maxx, resolution), np.linspace(miny, maxy, resolution))
    zn = griddata(xy, z, (gx, gy), method="nearest")
    zi = zn
    collinear = len(pts) < 4 or np.ptp(xy[:, 0]) < 1e-9 or np.ptp(xy[:, 1]) < 1e-9
    if not collinear:                      # una sola fila di punti: niente triangolazione
        try:
            zl = griddata(xy, z, (gx, gy), method="linear")
            zi = np.where(np.isnan(zl), zn, zl)
        except Exception:                  # punti degeneri: resta l'interpolazione nearest
            zi = zn
    inside = Path(poly).contains_points(np.column_stack([gx.ravel(), gy.ravel()])).reshape(gx.shape)
    zi = np.ma.array(zi, mask=~inside)

    levels = nice_levels(float(z.min()), float(z.max()))
    fig_w = 6.4
    fig, ax = plt.subplots(figsize=(fig_w, max(2.2, min(fig_w * (h + 2 * pad) / (w + 2 * pad), 8.5))), dpi=150)
    try:
        cf = ax.contourf(gx, gy, zi, levels=levels, cmap=FALSE_COLOURS, extend="both")
        cl = ax.contour(gx, gy, zi, levels=levels, colors="#1a1a1a", linewidths=0.35, alpha=0.55)
        ax.clabel(cl, inline=True, fontsize=6, fmt="%d")
        ax.plot(np.append(poly[:, 0], poly[0, 0]), np.append(poly[:, 1], poly[0, 1]), color="#111", lw=1.6)
        if luminaires:
            lm = np.asarray(luminaires, dtype=float)
            ax.scatter(lm[:, 0], lm[:, 1], s=64, marker="o", facecolors="white", edgecolors="#111",
                       linewidths=1.1, zorder=6)
            ax.scatter(lm[:, 0], lm[:, 1], s=64, marker="+", color="#111", linewidths=0.9, zorder=7)
        _dimensions(ax, poly, diag)
        ax.set_xlim(minx - pad, maxx + pad)
        ax.set_ylim(miny - pad, maxy + pad)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
        if title:
            ax.set_title(title, fontsize=8)
        ax.text(0.99, 0.01, "quote in m", transform=ax.transAxes, ha="right", va="bottom", fontsize=6, color="#888")
        cbar = fig.colorbar(cf, ax=ax, fraction=0.046, pad=0.02)
        cbar.set_label("E [lx]", fontsize=7)
        cbar.ax.tick_params(labelsize=6.5)
        fig.tight_layout(pad=0.4)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.06)
        return buf.getvalue()
    finally:
        plt.close(fig)
