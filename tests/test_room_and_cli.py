import json
import os
import shutil

import pytest

from conftest import EXAMPLES
from sfw_lightcalc import radiance
from sfw_lightcalc.cli import main, run_project
from sfw_lightcalc.direct import DirectBackend
from sfw_lightcalc.isolux import nice_levels, render
from sfw_lightcalc.room import design_room, normalize_room
from sfw_lightcalc.ugr import guth_position_index

OFFICE = {"id": "ufficio", "polygon": [[0, 0], [6, 0], [6, 4.5], [0, 4.5]], "height": 2.7,
          "workplane": 0.8, "em_target": 500, "u0_target": 0.6, "ugr_max": 19,
          "luminaire": {"ies": "downlight_3000lm.ies"}}


def test_normalize_room_defaults_and_errors():
    r = normalize_room({"polygon": [[0, 0], [1, 0], [1, 1]], "luminaire": {"flux_lm": 100}})
    assert r["reflectances"]["ceiling"] == 0.7 and r["em_target"] == 500
    with pytest.raises(ValueError):
        normalize_room({"polygon": [[0, 0], [1, 0]]})
    with pytest.raises(ValueError):
        normalize_room({"polygon": [[0, 0], [1, 0], [1, 1]], "height": 0.5, "workplane": 0.8})


def test_design_meets_targets():
    res = design_room(OFFICE, DirectBackend(), base_dir=EXAMPLES)
    assert res.em_ok and res.u0_ok
    assert res.em >= 475 and res.u0 >= 0.6
    assert res.n_luminaires >= 4
    assert len(res.grid) == res.n_points


def test_layout_grows_when_targets_are_higher():
    low = design_room({**OFFICE, "em_target": 300}, DirectBackend(), base_dir=EXAMPLES)
    high = design_room({**OFFICE, "em_target": 1000}, DirectBackend(), base_dir=EXAMPLES)
    assert high.n_luminaires > low.n_luminaires


def test_dimming_brings_em_back_to_target():
    res = design_room({**OFFICE, "em_target": 150, "u0_target": 0.3}, DirectBackend(), base_dir=EXAMPLES)
    assert res.dimming < 1
    assert res.em == pytest.approx(150 * 1.05, rel=0.01)


def test_guth_index_grows_off_axis():
    assert guth_position_index(0, 0) == 1.0
    assert guth_position_index(30, 30) > guth_position_index(10, 30)


def test_isolux_png_and_levels():
    png = render([[0, 0], [4, 0], [4, 3], [0, 3]],
                 [[x + 0.5, y + 0.5, 300 + 50 * x] for x in range(4) for y in range(3)], [[2, 1.5]])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    lv = nice_levels(300, 450)
    assert lv == sorted(lv) and lv[0] <= 300 and lv[-1] >= 450


def test_isolux_single_row_of_points():
    png = render([[0, 0], [10, 0], [10, 1], [0, 1]], [[x + 0.5, 0.5, 100 + x] for x in range(10)])
    assert png.startswith(b"\x89PNG")


def test_run_project_writes_results_and_maps(tmp_path):
    summary = run_project(os.path.join(EXAMPLES, "progetto_esempio.json"), str(tmp_path))
    assert [r["id"] for r in summary["rooms"]] == ["ufficio", "sala_riunioni_L", "corridoio"]
    assert all("error" not in r for r in summary["rooms"])
    saved = json.loads((tmp_path / "risultati.json").read_text(encoding="utf-8"))
    assert saved["backend"] == "direct"
    for r in summary["rooms"]:
        assert (tmp_path / r["map"]).exists()


def test_cli_entry_points(tmp_path, capsys):
    assert main(["ies-info", os.path.join(EXAMPLES, "downlight_3000lm.ies")]) == 0
    assert "DL-3000" in capsys.readouterr().out
    assert main(["run", os.path.join(EXAMPLES, "progetto_esempio.json"), "--out", str(tmp_path), "--no-maps"]) == 0
    assert "ufficio" in capsys.readouterr().out


def test_radiance_scene_text():
    scene = radiance.room_scene([[0, 0], [2, 0], [2, 2], [0, 2]], 3.0,
                                {"ceiling": 0.7, "walls": 0.5, "floor": 0.2})
    assert scene.count(" polygon ") == 6         # pavimento, soffitto, 4 pareti
    assert "void plastic mwall" in scene


@pytest.mark.skipif(not radiance.available(), reason="Radiance non installato")
def test_radiance_backend_close_to_direct():
    rad = design_room(OFFICE, radiance.RadianceBackend(), base_dir=EXAMPLES)
    assert rad.em > 0 and rad.n_points > 0
