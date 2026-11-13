"""Motore di calcolo con Radiance (https://www.radiance-online.org), con le interriflessioni complete.

Radiance non fa parte di questo pacchetto: va installato a parte. I programmi oconv, rtrace,
xform e ies2rad si cercano nella cartella indicata dalla variabile d'ambiente RADIANCE_BIN,
altrimenti nel PATH.

Scena: pavimento, pareti e soffitto con materiale `plastic` alle riflettanze indicate;
apparecchi da file IES (convertiti con ies2rad) oppure emettitori lambertiani quadrati di
30 cm calibrati sul flusso. L'illuminamento si ricava con `rtrace -I` sui punti del piano di
lavoro (conversione da radianza a lux: 179 · (0,265 R + 0,670 G + 0,065 B)).
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile

from .geometry import Point2, ccw, open_ring
from .ies import Photometry


def _bin_dir() -> str | None:
    return os.environ.get("RADIANCE_BIN")


def exe(name: str) -> str | None:
    """Percorso del programma Radiance, oppure None se non è installato."""
    d = _bin_dir()
    if d:
        for cand in (os.path.join(d, name + ".exe"), os.path.join(d, name)):
            if os.path.exists(cand):
                return cand
    return shutil.which(name)


def available() -> bool:
    return all(exe(n) for n in ("oconv", "rtrace"))


def _poly_rad(mat: str, name: str, verts: list[tuple[float, float, float]]) -> str:
    out = [f"{mat} polygon {name}", "0", "0", str(len(verts) * 3)]
    out += [f" {x:.4f} {y:.4f} {z:.4f}" for x, y, z in verts]
    return "\n".join(out) + "\n"


def room_scene(polygon: list, height: float, refl: dict) -> str:
    """Geometria del locale in formato Radiance: normali verso l'interno."""
    poly = ccw(open_ring(polygon))
    parts = []
    for nm, rho in (("mfloor", refl["floor"]), ("mwall", refl["walls"]), ("mceil", refl["ceiling"])):
        parts.append(f"void plastic {nm}\n0\n0\n5 {rho:.3f} {rho:.3f} {rho:.3f} 0 0\n")
    parts.append(_poly_rad("mfloor", "floor", [(x, y, 0.0) for x, y in poly]))
    parts.append(_poly_rad("mceil", "ceiling", [(x, y, height) for x, y in reversed(poly)]))
    n = len(poly)
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[(i + 1) % n]
        parts.append(_poly_rad("mwall", f"wall{i}", [(xi, yi, 0.0), (xi, yi, height), (xj, yj, height), (xj, yj, 0.0)]))
    return "".join(parts)


def luminaires_scene(positions: list[Point2], height: float, ph: Photometry,
                     ies_path: str | None, work: str, side: float = 0.3) -> str:
    parts = []
    flux = ph.luminaire_flux()
    for idx, (x, y) in enumerate(positions, start=1):
        used = False
        if ies_path and os.path.exists(ies_path) and exe("ies2rad") and exe("xform"):
            base = os.path.join(work, f"ies{idx}")
            subprocess.run([exe("ies2rad"), "-o", base, ies_path], capture_output=True)
            rad = base + ".rad"
            if os.path.exists(rad) and os.path.getsize(rad) > 0:
                parts.append(f"!{exe('xform')} -t {x:.3f} {y:.3f} {height:.3f} {rad}\n")
                used = True
        if not used:
            lum = flux / (math.pi * side * side)      # luminanza lambertiana [cd/m²]
            val = lum / 179.0
            parts.append(f"void light lum{idx}\n0\n0\n3 {val:.5f} {val:.5f} {val:.5f}\n")
            h2 = side / 2
            parts.append(_poly_rad(f"lum{idx}", f"panel{idx}", [
                (x - h2, y - h2, height), (x - h2, y + h2, height),
                (x + h2, y + h2, height), (x + h2, y - h2, height)]))
    return "".join(parts)


class RadianceBackend:
    name = "radiance"

    def __init__(self, ab: int = 4, ad: int = 1024):
        if not available():
            raise RuntimeError("Radiance non trovato: imposta RADIANCE_BIN o aggiungi i programmi al PATH")
        self.ab, self.ad = ab, ad

    def illuminance(self, room: dict, ph: Photometry, positions: list[Point2],
                    points: list[Point2], ies_path: str | None = None) -> list[float]:
        work = tempfile.mkdtemp(prefix="sfw_lightcalc_")
        try:
            scene = room_scene(room["polygon"], room["height"], room["reflectances"])
            scene += luminaires_scene(positions, room["height"], ph, ies_path, work)
            rad = os.path.join(work, "scene.rad")
            with open(rad, "w", encoding="ascii") as fh:
                fh.write(scene)
            oc = subprocess.run([exe("oconv"), rad], capture_output=True)
            if oc.returncode != 0 or not oc.stdout:
                raise RuntimeError("oconv: " + oc.stderr.decode(errors="ignore")[:200])
            octree = os.path.join(work, "scene.oct")
            with open(octree, "wb") as fh:
                fh.write(oc.stdout)
            wp = room["workplane"]
            stdin = "".join(f"{x:.3f} {y:.3f} {wp:.3f} 0 0 1\n" for x, y in points)
            rt = subprocess.run([exe("rtrace"), "-I", "-h", "-w", "-ab", str(self.ab), "-ad", str(self.ad),
                                 "-as", str(self.ad // 2), "-aa", "0.15", "-ar", "64", "-lw", "1e-4", octree],
                                input=stdin.encode(), capture_output=True)
            lux = []
            for line in rt.stdout.decode(errors="ignore").splitlines():
                c = line.split()
                if len(c) >= 3:
                    lux.append(179 * (0.265 * float(c[0]) + 0.670 * float(c[1]) + 0.065 * float(c[2])))
            if len(lux) != len(points):
                raise RuntimeError("rtrace: " + rt.stderr.decode(errors="ignore")[:200])
            return lux
        finally:
            shutil.rmtree(work, ignore_errors=True)
