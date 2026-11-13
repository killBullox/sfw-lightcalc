"""Lettura dei file fotometrici IES LM-63.

Il formato LM-63 descrive la distribuzione delle intensità luminose di un apparecchio:
intestazione con parole chiave tra parentesi quadre ([TEST], [LUMCAT], [LUMINAIRE], ...),
riga TILT, poi una sequenza di numeri:

    n_lampade, lumen_per_lampada, moltiplicatore, n_angoli_verticali, n_angoli_orizzontali,
    tipo_fotometrico, unità (1 = piedi, 2 = metri), larghezza, lunghezza, altezza,
    fattore_ballast, (riservato), watt_in_ingresso,
    angoli verticali, angoli orizzontali, matrice delle candele (un blocco per piano C).

Il modulo legge il file in un oggetto `Photometry`, interpola l'intensità I(gamma, C) e
calcola il flusso integrando la distribuzione. Gestisce anche gli archivi ZIP di file IES.
"""
from __future__ import annotations

import math
import os
import re
import zipfile
from dataclasses import dataclass, field

_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_KW = re.compile(r"^\s*\[([A-Z_]+)\]\s*(.*)$", re.IGNORECASE)


class IESError(ValueError):
    """File IES non leggibile o incompleto."""


@dataclass
class Photometry:
    vertical: list[float]                 # angoli gamma [deg], 0 = nadir
    horizontal: list[float]               # piani C [deg]
    candela: list[list[float]]            # candela[iC][iGamma], già moltiplicate
    lamp_lumens: float                    # flusso nominale delle lampade [lm]
    width_m: float = 0.0
    length_m: float = 0.0
    input_watts: float = 0.0
    keywords: dict[str, str] = field(default_factory=dict)

    # ---- intensità -------------------------------------------------------
    def _interp_gamma(self, row: list[float], gamma: float) -> float:
        va = self.vertical
        if gamma <= va[0]:
            return row[0]
        if gamma >= va[-1]:
            return row[-1] if va[-1] >= 180 else 0.0
        lo, hi = 0, len(va) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if va[mid] <= gamma:
                lo = mid
            else:
                hi = mid
        t = (gamma - va[lo]) / (va[hi] - va[lo]) if va[hi] > va[lo] else 0.0
        return row[lo] + (row[hi] - row[lo]) * t

    def _c_plane(self, c: float) -> float:
        """Riporta l'angolo C nell'intervallo coperto dal file, sfruttando le simmetrie LM-63."""
        c %= 360.0
        hmax = self.horizontal[-1]
        if len(self.horizontal) == 1:
            return 0.0
        if hmax <= 90.0:                  # simmetria nei quattro quadranti
            c = c % 180.0
            if c > 90.0:
                c = 180.0 - c
        elif hmax <= 180.0:               # simmetria rispetto al piano 0-180
            if c > 180.0:
                c = 360.0 - c
        return c

    def intensity(self, gamma: float, c: float = 0.0) -> float:
        """Intensità [cd] alla direzione (gamma da nadir, piano C), interpolazione bilineare."""
        if len(self.horizontal) == 1:
            return max(0.0, self._interp_gamma(self.candela[0], gamma))
        c = self._c_plane(c)
        ha = self.horizontal
        if c <= ha[0]:
            return max(0.0, self._interp_gamma(self.candela[0], gamma))
        if c >= ha[-1]:
            return max(0.0, self._interp_gamma(self.candela[-1], gamma))
        for i in range(len(ha) - 1):
            if ha[i] <= c <= ha[i + 1]:
                t = (c - ha[i]) / (ha[i + 1] - ha[i]) if ha[i + 1] > ha[i] else 0.0
                a = self._interp_gamma(self.candela[i], gamma)
                b = self._interp_gamma(self.candela[i + 1], gamma)
                return max(0.0, a + (b - a) * t)
        return 0.0

    def mean_curve(self) -> list[float]:
        """Intensità media sui piani C per ogni angolo gamma (curva di rivoluzione)."""
        n = len(self.candela)
        return [sum(self.candela[j][i] for j in range(n)) / n for i in range(len(self.vertical))]

    # ---- flusso ----------------------------------------------------------
    def luminaire_flux(self, steps: int = 180) -> float:
        """Flusso emesso [lm] = integrale di I(gamma) sull'angolo solido (curva media sui piani C)."""
        curve = self.mean_curve()
        top = min(180.0, self.vertical[-1])
        d = top / steps
        tot = 0.0
        for k in range(steps):
            g0, g1 = k * d, (k + 1) * d
            gm = (g0 + g1) / 2
            i_m = self._interp_gamma(curve, gm)
            omega = 2 * math.pi * (math.cos(math.radians(g0)) - math.cos(math.radians(g1)))
            tot += i_m * omega
        return tot

    @property
    def luminous_area_m2(self) -> float:
        a = abs(self.width_m) * abs(self.length_m)
        if self.width_m < 0 or self.length_m < 0:   # apertura circolare (convenzione LM-63)
            a = math.pi * (max(abs(self.width_m), abs(self.length_m)) / 2) ** 2
        return a if a > 1e-4 else 0.05 * 0.05


def parse_ies_text(text: str) -> Photometry:
    """Converte il testo di un file IES LM-63 in `Photometry`."""
    keywords: dict[str, str] = {}
    lines = text.splitlines()
    tilt_at = None
    for i, line in enumerate(lines):
        m = _KW.match(line)
        if m:
            keywords.setdefault(m.group(1).upper(), m.group(2).strip())
        if line.strip().upper().startswith("TILT"):
            tilt_at = i
            break
    if tilt_at is None:
        raise IESError("riga TILT mancante")
    tilt = lines[tilt_at].split("=", 1)[-1].strip().upper()
    body = "\n".join(lines[tilt_at + 1:])
    nums = [float(x) for x in _NUM.findall(body)]
    if tilt == "INCLUDE":                       # salta il blocco di inclinazione
        n_pairs = int(nums[1])
        nums = nums[2 + 2 * n_pairs:]
    if len(nums) < 13:
        raise IESError("intestazione numerica incompleta")
    n_lamp, lm_lamp, mult, n_v, n_h, _ptype, units, width, length = nums[:9]
    watts = nums[12]
    n_v, n_h = int(n_v), int(n_h)
    idx = 13
    need = n_v + n_h + n_v * n_h
    if n_v < 2 or n_h < 1 or len(nums) < idx + need:
        raise IESError("angoli o candele incompleti")
    vertical = nums[idx:idx + n_v]; idx += n_v
    horizontal = nums[idx:idx + n_h]; idx += n_h
    mult = mult or 1.0
    candela = [[v * mult for v in nums[idx + j * n_v: idx + (j + 1) * n_v]] for j in range(n_h)]
    to_m = 0.3048 if int(units) == 1 else 1.0
    return Photometry(
        vertical=vertical, horizontal=horizontal, candela=candela,
        lamp_lumens=(n_lamp if n_lamp > 0 else 1) * lm_lamp,
        width_m=width * to_m, length_m=length * to_m, input_watts=watts, keywords=keywords,
    )


def read_ies(path: str) -> Photometry:
    with open(path, "rb") as fh:
        return parse_ies_text(fh.read().decode("latin-1"))


def lambertian(flux_lm: float, side_m: float = 0.3) -> Photometry:
    """Apparecchio ideale lambertiano verso il basso: I(gamma) = (flusso/pi)·cos(gamma)."""
    i0 = max(flux_lm, 1.0) / math.pi
    vertical = [float(a) for a in range(0, 91, 5)]
    return Photometry(vertical=vertical, horizontal=[0.0],
                      candela=[[i0 * math.cos(math.radians(a)) for a in vertical]],
                      lamp_lumens=flux_lm, width_m=side_m, length_m=side_m,
                      keywords={"LUMINAIRE": "lambertiano ideale"})


def extract_zip(zip_path: str, out_dir: str) -> list[dict]:
    """Estrae i file .ies di uno ZIP in `out_dir` (nomi resi unici) e ne riassume i metadati."""
    os.makedirs(out_dir, exist_ok=True)
    out = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".ies"):
                continue
            data = zf.read(name)
            base = os.path.basename(name) or "file.ies"
            dest = os.path.join(out_dir, base)
            k = 1
            while os.path.exists(dest):
                with open(dest, "rb") as fh:
                    if fh.read() == data:
                        break
                dest = os.path.join(out_dir, f"{os.path.splitext(base)[0]}_{k}.ies")
                k += 1
            with open(dest, "wb") as fh:
                fh.write(data)
            entry = {"file": dest, "name": base, "flux_lm": None, "lumcat": None, "description": None}
            try:
                ph = parse_ies_text(data.decode("latin-1"))
                entry.update(flux_lm=round(ph.lamp_lumens), lumcat=ph.keywords.get("LUMCAT"),
                             description=ph.keywords.get("LUMINAIRE") or ph.keywords.get("TEST"))
            except IESError as exc:
                entry["error"] = str(exc)
            out.append(entry)
    return out
