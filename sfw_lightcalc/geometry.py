"""Geometria del locale: poligoni, griglia di calcolo sulla zona del compito, layout degli apparecchi.

Coordinate in metri sul piano (x, y). I poligoni sono liste di vertici [(x, y), ...],
aperti o chiusi (l'ultimo vertice uguale al primo viene ignorato).
"""
from __future__ import annotations

import math

Point2 = tuple[float, float]


def open_ring(poly: list) -> list[Point2]:
    pts = [(float(x), float(y)) for x, y in poly]
    if len(pts) > 1 and math.isclose(pts[0][0], pts[-1][0]) and math.isclose(pts[0][1], pts[-1][1]):
        pts = pts[:-1]
    return pts


def signed_area(poly: list[Point2]) -> float:
    a = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2


def area(poly: list[Point2]) -> float:
    return abs(signed_area(poly))


def ccw(poly: list[Point2]) -> list[Point2]:
    return poly if signed_area(poly) >= 0 else list(reversed(poly))


def bbox(poly: list[Point2]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def centroid(poly: list[Point2]) -> Point2:
    a = signed_area(poly)
    if abs(a) < 1e-12:
        return sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)
    cx = cy = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        f = x1 * y2 - x2 * y1
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    return cx / (6 * a), cy / (6 * a)


def contains(poly: list[Point2], x: float, y: float) -> bool:
    """Punto nel poligono (ray casting)."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def edge_distance(poly: list[Point2], x: float, y: float) -> float:
    """Distanza minima del punto dai lati del poligono."""
    best = math.inf
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
        px, py = ax + t * dx, ay + t * dy
        best = min(best, math.hypot(x - px, y - py))
    return best


def grid_step_en12464(length_m: float) -> float:
    """Passo massimo della griglia di calcolo (UNI EN 12464-1): p = 0,2 · 5^log10(d), con d la
    dimensione maggiore dell'area; il passo non supera 10 m."""
    d = max(length_m, 0.1)
    return min(10.0, 0.2 * 5 ** math.log10(d))


def task_grid(poly: list[Point2], step: float | None = None, margin: float = 0.5,
              max_points: int = 400) -> list[Point2]:
    """Punti di calcolo regolari sulla zona del compito.

    La UNI EN 12464-1 esclude una fascia perimetrale (di norma 0,5 m) dalla valutazione
    dell'uniformità: si tengono quindi solo i punti a distanza >= margin dai lati. Nei locali
    piccoli, dove la fascia lascerebbe meno del 15% dell'area, si valuta tutto il locale.
    """
    poly = open_ring(poly)
    minx, miny, maxx, maxy = bbox(poly)
    w, h = maxx - minx, maxy - miny
    if w <= 0 or h <= 0:
        return [centroid(poly)]
    if step is None:   # la norma fissa il passo massimo: qui al più 0,5 m per mappe leggibili
        step = min(grid_step_en12464(max(w, h)), 0.5)
    while (w / step + 1) * (h / step + 1) > max_points and step < max(w, h):
        step *= 1.25

    def build(m: float) -> list[Point2]:
        out = []
        y = miny + step / 2
        while y < maxy:
            x = minx + step / 2
            while x < maxx:
                if contains(poly, x, y) and (m <= 0 or edge_distance(poly, x, y) >= m):
                    out.append((x, y))
                x += step
            y += step
        return out

    pts = build(margin)
    full = build(0.0)
    if margin > 0 and len(pts) < max(1, 0.15 * len(full)):
        pts = full
    return pts or [centroid(poly)]


def regular_layout(poly: list[Point2], mounting_height: float, shr_max: float = 1.2,
                   min_step: float = 0.8, max_step: float = 4.0) -> list[Point2]:
    """Griglia regolare di apparecchi ritagliata sul poligono.

    Passo = SHR_max · altezza di montaggio sul piano di lavoro (spacing-to-height ratio),
    limitato tra min_step e max_step. Gli apparecchi stanno a mezzo passo dai bordi del
    rettangolo di ingombro; si tengono quelli interni al locale (con 5 cm di tolleranza).
    Il numero finale lo chiude il calcolo (vedi room.design_room), non questa funzione.
    """
    poly = open_ring(poly)
    if area(poly) <= 0:
        return [centroid(poly)]
    s = max(min_step, min(shr_max * max(mounting_height, 0.5), max_step))
    minx, miny, maxx, maxy = bbox(poly)
    w, h = maxx - minx, maxy - miny
    ncol = max(1, round(w / s))
    nrow = max(1, round(h / s))
    dx, dy = w / ncol, h / nrow
    out = []
    for i in range(ncol):
        for j in range(nrow):
            x, y = minx + (i + 0.5) * dx, miny + (j + 0.5) * dy
            if contains(poly, x, y) and edge_distance(poly, x, y) >= 0.05:
                out.append((x, y))
    return out or [centroid(poly)]


def perimeter(poly: list[Point2]) -> float:
    n = len(poly)
    return sum(math.dist(poly[i], poly[(i + 1) % n]) for i in range(n))
