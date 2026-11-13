"""Genera i file IES sintetici degli esempi (nessun prodotto reale).

Downlight: I(gamma) = I0 · cos^n(gamma) per gamma <= 90°, zero sopra; il flusso vale
2·pi·I0/(n+1), quindi I0 = flusso·(n+1)/(2·pi).
Lineare: due piani C (0° e 90°) con distribuzioni diverse, per provare l'interpolazione in C.

    python examples/make_example_ies.py
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def write_ies(path, name, lumens, watts, vertical, planes, curves, width=0.3, length=0.3):
    lines = [
        "IESNA:LM-63-2002",
        "[TEST] dati sintetici generati da make_example_ies.py",
        "[MANUFAC] esempio",
        f"[LUMCAT] {name}",
        f"[LUMINAIRE] {name} (apparecchio fittizio)",
        "TILT=NONE",
        f"1 {lumens:.1f} 1 {len(vertical)} {len(planes)} 1 2 {width} {length} 0",
        f"1 1 {watts}",
        " ".join(f"{a:g}" for a in vertical),
        " ".join(f"{a:g}" for a in planes),
    ]
    for curve in curves:
        lines.append(" ".join(f"{v:.2f}" for v in curve))
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def downlight(flux=3000.0, n=1.5):
    i0 = flux * (n + 1) / (2 * math.pi)
    vertical = list(range(0, 181, 5))
    curve = [i0 * math.cos(math.radians(a)) ** n if a < 90 else 0.0 for a in vertical]
    return vertical, curve


def main():
    v, c = downlight(3000.0, 1.5)
    write_ies(os.path.join(HERE, "downlight_3000lm.ies"), "DL-3000", 3000.0, 24, v, [0.0], [c])
    # lineare: piano C0 più largo (n=1), piano C90 più stretto (n=3), simmetria nei quadranti
    v1, c0 = downlight(4000.0, 1.0)
    _, c90 = downlight(4000.0, 3.0)
    write_ies(os.path.join(HERE, "lineare_4000lm.ies"), "LIN-4000", 4000.0, 32, v1, [0.0, 90.0], [c0, c90],
              width=0.08, length=1.2)
    print("file IES di esempio scritti in", HERE)


if __name__ == "__main__":
    main()
