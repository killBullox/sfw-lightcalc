"""Riga di comando.

    python -m sfw_lightcalc run esempio.json --out risultati [--backend direct|radiance] [--no-maps]
    python -m sfw_lightcalc ies-info apparecchio.ies
    python -m sfw_lightcalc extract archivio.zip cartella

`run` legge un progetto JSON {"rooms": [ ... ]} (formato in room.py), calcola ogni locale,
scrive risultati.json e una mappa isolux PNG per locale nella cartella di uscita.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .direct import DirectBackend
from .ies import extract_zip, read_ies
from .room import design_room


def make_backend(name: str):
    if name == "direct":
        return DirectBackend()
    if name == "radiance":
        from .radiance import RadianceBackend
        return RadianceBackend()
    raise ValueError(f"motore sconosciuto: {name}")


def run_project(path: str, out_dir: str, backend_name: str = "direct", maps: bool = True) -> dict:
    with open(path, encoding="utf-8") as fh:
        job = json.load(fh)
    base = os.path.dirname(os.path.abspath(path))
    backend = make_backend(backend_name)
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for room in job.get("rooms", []):
        try:
            res = design_room(room, backend, base_dir=base).to_dict()
            if maps:
                from .isolux import render
                png = render(room["polygon"], res["grid"], res["positions"],
                             title=f"{res['id']}: Em {res['em']:.0f} lx, U0 {res['u0']:.2f}")
                map_path = os.path.join(out_dir, f"isolux_{res['id']}.png")
                with open(map_path, "wb") as fh:
                    fh.write(png)
                res["map"] = os.path.basename(map_path)
        except (ValueError, OSError, RuntimeError) as exc:
            res = {"id": room.get("id"), "error": str(exc)}
        results.append(res)
    summary = {"backend": backend_name, "rooms": results}
    with open(os.path.join(out_dir, "risultati.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    return summary


def _table(summary: dict) -> str:
    rows = [f"{'locale':<16}{'Em':>8}{'Emin':>8}{'U0':>7}{'UGR':>7}{'app.':>6}  esito"]
    for r in summary["rooms"]:
        if "error" in r:
            rows.append(f"{str(r['id']):<16}  errore: {r['error']}")
            continue
        ok = r["em_ok"] and r["u0_ok"] and r["ugr_ok"] is not False
        ugr = "-" if r["ugr"] is None else f"{r['ugr']:.1f}"
        rows.append(f"{r['id']:<16}{r['em']:>8.0f}{r['emin']:>8.0f}{r['u0']:>7.2f}{ugr:>7}{r['n_luminaires']:>6}  "
                    + ("conforme" if ok else "NON conforme"))
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sfw_lightcalc", description="Calcolo illuminotecnico dei locali")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="calcola un progetto JSON")
    p_run.add_argument("project")
    p_run.add_argument("--out", default="risultati")
    p_run.add_argument("--backend", choices=["direct", "radiance"], default="direct")
    p_run.add_argument("--no-maps", action="store_true")
    p_info = sub.add_parser("ies-info", help="riassume un file IES")
    p_info.add_argument("ies")
    p_zip = sub.add_parser("extract", help="estrae i file IES da uno ZIP")
    p_zip.add_argument("zip")
    p_zip.add_argument("out")
    a = ap.parse_args(argv)

    if a.cmd == "run":
        summary = run_project(a.project, a.out, a.backend, maps=not a.no_maps)
        print(_table(summary))
        return 0 if all("error" not in r for r in summary["rooms"]) else 1
    if a.cmd == "ies-info":
        ph = read_ies(a.ies)
        print(json.dumps({
            "luminaire": ph.keywords.get("LUMINAIRE"), "lumcat": ph.keywords.get("LUMCAT"),
            "lamp_lumens": ph.lamp_lumens, "luminaire_lumens": round(ph.luminaire_flux(), 1),
            "input_watts": ph.input_watts, "vertical_angles": len(ph.vertical),
            "c_planes": len(ph.horizontal), "peak_cd": max(max(r) for r in ph.candela),
        }, ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "extract":
        print(json.dumps(extract_zip(a.zip, a.out), ensure_ascii=False, indent=1))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
