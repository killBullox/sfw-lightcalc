import pytest

from sfw_lightcalc import geometry as g

RECT = [(0, 0), (6, 0), (6, 4), (0, 4)]
L_SHAPE = [(0, 0), (8, 0), (8, 3), (4, 3), (4, 6), (0, 6)]


def test_area_orientation_and_ring():
    assert g.area(RECT) == pytest.approx(24)
    assert g.signed_area(list(reversed(RECT))) < 0
    assert g.signed_area(g.ccw(list(reversed(RECT)))) > 0
    assert g.open_ring(RECT + [RECT[0]]) == [(float(x), float(y)) for x, y in RECT]
    assert g.area(L_SHAPE) == pytest.approx(36)


def test_contains_and_edge_distance():
    assert g.contains(L_SHAPE, 1, 5)
    assert not g.contains(L_SHAPE, 6, 5)          # fuori, nella rientranza della L
    assert g.edge_distance(RECT, 3, 2) == pytest.approx(2)


def test_en12464_grid_step():
    # p = 0,2 · 5^log10(d): per d = 10 m vale 1 m
    assert g.grid_step_en12464(10) == pytest.approx(1.0)
    assert g.grid_step_en12464(1000) == 10.0


def test_task_grid_excludes_border_band():
    pts = g.task_grid(RECT, step=0.5, margin=0.5)
    assert pts
    assert all(g.edge_distance(RECT, x, y) >= 0.5 - 1e-9 for x, y in pts)


def test_task_grid_small_room_uses_whole_area():
    small = [(0, 0), (1.2, 0), (1.2, 1.0), (0, 1.0)]
    pts = g.task_grid(small, step=0.2, margin=0.5)
    assert len(pts) > 10


def test_regular_layout_inside_l_shape():
    pos = g.regular_layout(L_SHAPE, mounting_height=2.2)
    assert len(pos) >= 4
    assert all(g.contains(L_SHAPE, x, y) for x, y in pos)
