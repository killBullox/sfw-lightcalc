import math
import os
import zipfile

import pytest

from conftest import EXAMPLES
from sfw_lightcalc.ies import IESError, extract_zip, lambertian, parse_ies_text, read_ies

DOWNLIGHT = os.path.join(EXAMPLES, "downlight_3000lm.ies")
LINEAR = os.path.join(EXAMPLES, "lineare_4000lm.ies")


def test_reads_header_and_keywords():
    ph = read_ies(DOWNLIGHT)
    assert ph.keywords["LUMCAT"] == "DL-3000"
    assert ph.lamp_lumens == pytest.approx(3000)
    assert ph.input_watts == pytest.approx(24)
    assert ph.vertical[0] == 0 and ph.vertical[-1] == 180
    assert len(ph.horizontal) == 1


def test_integrated_flux_matches_nominal():
    # distribuzione cos^1.5 costruita per 3000 lm: l'integrazione numerica deve ritrovarli
    assert read_ies(DOWNLIGHT).luminaire_flux() == pytest.approx(3000, rel=0.01)
    assert read_ies(LINEAR).luminaire_flux() == pytest.approx(4000, rel=0.15)


def test_intensity_interpolation_in_gamma():
    ph = read_ies(DOWNLIGHT)
    i0 = 3000 * 2.5 / (2 * math.pi)
    assert ph.intensity(0) == pytest.approx(i0, rel=1e-3)
    assert ph.intensity(60) == pytest.approx(i0 * math.cos(math.radians(60)) ** 1.5, rel=0.02)
    assert ph.intensity(120) == 0


def test_intensity_c_planes_and_symmetry():
    ph = read_ies(LINEAR)
    # a 60° il piano C0 (cos^1) è più largo del piano C90 (cos^3)
    wide, narrow = ph.intensity(60, 0), ph.intensity(60, 90)
    assert wide > narrow
    mid = ph.intensity(60, 45)
    assert narrow < mid < wide
    # simmetria nei quadranti: C=180 come C=0, C=270 come C=90
    assert ph.intensity(60, 180) == pytest.approx(wide)
    assert ph.intensity(60, 270) == pytest.approx(narrow)


def test_lambertian_flux():
    assert lambertian(2000).luminaire_flux() == pytest.approx(2000, rel=0.01)


def test_rejects_broken_file():
    with pytest.raises(IESError):
        parse_ies_text("IESNA:LM-63-2002\n[TEST] senza TILT\n1 2 3\n")
    with pytest.raises(IESError):
        parse_ies_text("TILT=NONE\n1 1000 1 5 1 1 2 0 0 0\n")


def test_tilt_include_block_is_skipped():
    text = open(DOWNLIGHT, encoding="ascii").read().replace(
        "TILT=NONE", "TILT=INCLUDE\n1\n3\n0 45 90\n1 1 1")
    assert parse_ies_text(text).lamp_lumens == pytest.approx(3000)


def test_extract_zip(tmp_path):
    zp = tmp_path / "pacchetto.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.write(DOWNLIGHT, "cartella/downlight.ies")
        zf.write(LINEAR, "lineare.IES")
        zf.writestr("leggimi.txt", "non e' un IES")
    out = extract_zip(str(zp), str(tmp_path / "ies"))
    assert {e["name"] for e in out} == {"downlight.ies", "lineare.IES"}
    assert {e["flux_lm"] for e in out} == {3000, 4000}
    assert all(os.path.exists(e["file"]) for e in out)
