import math

import pytest

from sfw_lightcalc.direct import DirectBackend, direct_illuminance, interreflection_estimate
from sfw_lightcalc.ies import lambertian


def test_inverse_square_under_luminaire():
    ph = lambertian(1000)
    # sotto l'apparecchio: E = I0 / h², con I0 = flusso / pi
    e = direct_illuminance(ph, (0, 0), 3.0, (0, 0), 0.0)
    assert e == pytest.approx((1000 / math.pi) / 9, rel=1e-6)


def test_cosine_cubed_off_axis():
    ph = lambertian(1000)
    h = 2.0
    for d in (1.0, 2.0, 3.0):
        r = math.hypot(d, h)
        cos_g = h / r
        expected = (1000 / math.pi) * cos_g * cos_g / r ** 2   # I0·cos · cos / r²
        assert direct_illuminance(ph, (0, 0), h, (d, 0), 0.0) == pytest.approx(expected, rel=0.01)


def test_nothing_above_the_luminaire():
    assert direct_illuminance(lambertian(1000), (0, 0), 2.0, (0, 0), 2.5) == 0.0


def test_interreflection_grows_with_reflectance():
    sq = [(0, 0), (5, 0), (5, 5), (0, 5)]
    low = interreflection_estimate(sq, 3, 10000, 0.3, 0.3, 0.1)
    high = interreflection_estimate(sq, 3, 10000, 0.8, 0.6, 0.3)
    assert 0 < low < high


def test_backend_adds_indirect_component():
    room = {"polygon": [(0, 0), (4, 0), (4, 4), (0, 4)], "height": 3.0, "workplane": 0.8,
            "reflectances": {"ceiling": 0.7, "walls": 0.5, "floor": 0.2}}
    ph = lambertian(3000)
    pts = [(2, 2), (1, 1)]
    only_direct = DirectBackend(include_indirect=False).illuminance(room, ph, [(2, 2)], pts)
    total = DirectBackend().illuminance(room, ph, [(2, 2)], pts)
    assert all(t > d for t, d in zip(total, only_direct))
    assert only_direct[0] > only_direct[1]
