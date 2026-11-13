"""Calcolo punto per punto dell'illuminamento orizzontale, senza programmi esterni.

Componente diretta: per ogni apparecchio a soffitto rivolto verso il basso e ogni punto del
piano di lavoro vale la legge dell'inverso del quadrato con il coseno,

    E_dir = I(gamma, C) · cos(gamma) / r²

con gamma angolo dalla verticale (nadir) e C l'azimut nel piano dell'apparecchio.

Componente indiretta (stima): metodo della sfera integratrice, illuminamento uniforme
dovuto alle interriflessioni

    E_ind = Φ_tot · ρ_m / (A_tot · (1 − ρ_m))

con Φ_tot flusso totale degli apparecchi, A_tot superficie interna del locale e ρ_m la
riflettanza media pesata sulle aree. È un'approssimazione: per il calcolo completo delle
interriflessioni si usa il motore Radiance (modulo radiance).
"""
from __future__ import annotations

import math

from .geometry import Point2, area, perimeter
from .ies import Photometry


def direct_illuminance(ph: Photometry, lum_xy: Point2, mount_z: float,
                       pt_xy: Point2, plane_z: float, rotation_deg: float = 0.0) -> float:
    """Illuminamento orizzontale diretto [lx] di un apparecchio nel punto dato."""
    dx = pt_xy[0] - lum_xy[0]
    dy = pt_xy[1] - lum_xy[1]
    dz = mount_z - plane_z
    if dz <= 0:
        return 0.0
    r2 = dx * dx + dy * dy + dz * dz
    r = math.sqrt(r2)
    cos_g = dz / r
    gamma = math.degrees(math.acos(max(-1.0, min(1.0, cos_g))))
    c = (math.degrees(math.atan2(dy, dx)) - rotation_deg) % 360.0
    return ph.intensity(gamma, c) * cos_g / r2


def interreflection_estimate(poly: list[Point2], height: float, total_flux: float,
                             rho_ceiling: float, rho_walls: float, rho_floor: float) -> float:
    """Componente indiretta uniforme [lx] con il metodo della sfera integratrice."""
    a_floor = area(poly)
    a_walls = perimeter(poly) * height
    a_tot = 2 * a_floor + a_walls
    if a_tot <= 0:
        return 0.0
    rho_m = (rho_ceiling * a_floor + rho_floor * a_floor + rho_walls * a_walls) / a_tot
    rho_m = min(rho_m, 0.95)
    return total_flux * rho_m / (a_tot * (1 - rho_m))


class DirectBackend:
    """Motore di calcolo interno: diretto punto per punto più stima delle interriflessioni."""

    name = "direct"

    def __init__(self, include_indirect: bool = True):
        self.include_indirect = include_indirect

    def illuminance(self, room: dict, ph: Photometry, positions: list[Point2],
                    points: list[Point2], ies_path: str | None = None) -> list[float]:
        poly = room["polygon"]
        h = room["height"]
        wp = room["workplane"]
        refl = room["reflectances"]
        values = []
        for p in points:
            e = sum(direct_illuminance(ph, q, h, p, wp) for q in positions)
            values.append(e)
        if self.include_indirect:
            flux = ph.luminaire_flux() * len(positions)
            e_ind = interreflection_estimate(poly, h, flux, refl["ceiling"], refl["walls"], refl["floor"])
            values = [v + e_ind for v in values]
        return values
