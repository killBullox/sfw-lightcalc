"""Progetto illuminotecnico di un locale: layout, calcolo, verifica dei requisiti.

Flusso:
1. griglia regolare di apparecchi (passo dal rapporto interdistanza/altezza);
2. calcolo dell'illuminamento sui punti della zona del compito con il motore scelto;
3. finché l'illuminamento medio Em o l'uniformità U0 = Emin/Em sono sotto il requisito,
   si aggiunge un apparecchio sopra il punto più buio misurato e si ricalcola;
4. se Em supera il requisito di oltre il 15%, gli apparecchi si regolano (dimming) al
   requisito più 5%: Em ed Emin scalano, U0 non cambia, UGR cala di 8·log10(dimming);
5. UGR con il metodo tabellare CIE 117.

Formato del locale (dizionario, unità in metri e lux):
    {"id": "ufficio", "polygon": [[x, y], ...], "height": 2.7, "workplane": 0.8,
     "reflectances": {"ceiling": 0.7, "walls": 0.5, "floor": 0.2},
     "em_target": 500, "u0_target": 0.6, "ugr_max": 19,
     "luminaire": {"ies": "percorso.ies"} oppure {"flux_lm": 3000}}
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from . import geometry as g
from .ies import Photometry, lambertian, read_ies
from .ugr import ugr as compute_ugr

DEFAULT_REFL = {"ceiling": 0.7, "walls": 0.5, "floor": 0.2}


@dataclass
class RoomResult:
    id: str
    em: float
    emin: float
    emax: float
    u0: float
    ugr: float | None
    dimming: float
    n_luminaires: int
    n_points: int
    em_ok: bool
    u0_ok: bool
    ugr_ok: bool | None
    grid: list[list[float]]
    positions: list[list[float]]
    backend: str

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_room(room: dict) -> dict:
    """Completa il locale con i valori predefiniti e controlla i dati essenziali."""
    poly = g.open_ring(room.get("polygon") or [])
    if len(poly) < 3:
        raise ValueError(f"locale {room.get('id')}: servono almeno 3 vertici")
    refl = {**DEFAULT_REFL, **(room.get("reflectances") or {})}
    out = {
        "id": str(room.get("id", "locale")),
        "polygon": poly,
        "height": float(room.get("height", 3.0)),
        "workplane": float(room.get("workplane", 0.8)),
        "reflectances": refl,
        "em_target": float(room.get("em_target", 500)),
        "u0_target": float(room.get("u0_target", 0.6)),
        "ugr_max": room.get("ugr_max"),
        "luminaire": room.get("luminaire") or {},
    }
    if out["height"] <= out["workplane"]:
        raise ValueError(f"locale {out['id']}: altezza non superiore al piano di lavoro")
    return out


def load_photometry(lum: dict, base_dir: str = ".") -> tuple[Photometry, str | None]:
    ies = lum.get("ies")
    if ies:
        import os
        path = ies if os.path.isabs(ies) else os.path.join(base_dir, ies)
        return read_ies(path), path
    flux = float(lum.get("flux_lm", 0))
    if flux <= 0:
        raise ValueError("apparecchio senza file IES né flusso")
    return lambertian(flux), None


def design_room(room: dict, backend, base_dir: str = ".", max_added: int = 8,
                grid_step: float | None = None) -> RoomResult:
    r = normalize_room(room)
    ph, ies_path = load_photometry(r["luminaire"], base_dir)
    poly, h, wp = r["polygon"], r["height"], r["workplane"]
    positions = g.regular_layout(poly, h - wp)
    points = g.task_grid(poly, step=grid_step)

    lux: list[float] = []
    for it in range(max_added + 1):
        lux = backend.illuminance(r, ph, positions, points, ies_path)
        em = sum(lux) / len(lux)
        emin = min(lux)
        u0 = emin / em if em > 0 else 0.0
        if (u0 >= r["u0_target"] and em >= 0.95 * r["em_target"]) or it == max_added:
            break
        positions.append(points[lux.index(emin)])

    em, emin, emax = sum(lux) / len(lux), min(lux), max(lux)
    u0 = emin / em if em > 0 else 0.0

    l_b = max(1.0, r["reflectances"]["walls"] * em / math.pi)
    ugr_val = compute_ugr(positions, ph, poly, h, l_b)

    dimming = 1.0
    if em > 1.15 * r["em_target"]:
        dimming = max(0.1, 1.05 * r["em_target"] / em)
        em, emin, emax = em * dimming, emin * dimming, emax * dimming
        if ugr_val is not None:
            ugr_val = round(ugr_val + 8 * math.log10(dimming), 1)

    ugr_max = r["ugr_max"]
    return RoomResult(
        id=r["id"], em=round(em, 1), emin=round(emin, 1), emax=round(emax, 1), u0=round(u0, 3),
        ugr=ugr_val, dimming=round(dimming, 3), n_luminaires=len(positions), n_points=len(lux),
        em_ok=em >= 0.95 * r["em_target"], u0_ok=u0 >= r["u0_target"],
        ugr_ok=None if ugr_max is None or ugr_val is None else ugr_val <= float(ugr_max),
        grid=[[round(x, 2), round(y, 2), round(v * dimming, 1)] for (x, y), v in zip(points, lux)],
        positions=[[round(x, 2), round(y, 2)] for x, y in positions],
        backend=getattr(backend, "name", type(backend).__name__),
    )
