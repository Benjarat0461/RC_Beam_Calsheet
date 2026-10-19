import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aci318 as aci  # noqa: E402


def test_beta1():
    assert aci.beta1(24) == 0.85
    assert aci.beta1(35) == pytest.approx(0.80)
    assert aci.beta1(70) == 0.65


def test_phi_flexure():
    fy = 420
    assert aci.phi_flexure(0.006, fy) == 0.90
    assert aci.phi_flexure(0.002, fy) == 0.65
    assert aci.phi_flexure(0.0021 + 0.0015, fy) == pytest.approx(0.775)


def test_singly_reinforced_matches_hand_calc():
    # b=300, d=540, 4-DB25, fc=28, fy=420
    As = 4 * aci.bar_area(25)
    res = aci.analyze_flexure(300, 600, 28, 420, [(As, 540)], 540)
    a = As * 420 / (0.85 * 28 * 300)
    Mn = As * 420 * (540 - a / 2)
    assert res.a == pytest.approx(a, rel=1e-6)
    assert res.Mn == pytest.approx(Mn, rel=1e-6)
    assert res.phi == 0.90


def test_required_steel_round_trip():
    Mu = 300e6
    As, Asc = aci.required_steel(Mu, 300, 540, 60, 28, 420)
    assert Asc == 0
    res = aci.analyze_flexure(300, 600, 28, 420, [(As, 540)], 540)
    assert res.phi_Mn == pytest.approx(Mu, rel=1e-4)


def test_doubly_reinforced_required():
    As, Asc = aci.required_steel(800e6, 300, 540, 60, 28, 420)
    assert Asc > 0
    res = aci.analyze_flexure(300, 600, 28, 420, [(Asc, 60), (As, 540)], 540)
    assert res.phi_Mn >= 800e6 * 0.999


def test_design_flexure_passes():
    fd = aci.design_flexure(250e6, 300, 600, 24, 390, 40, 9, 20, 20, 16)
    assert all(fd.checks.values())
    assert fd.result.phi_Mn >= 250e6


def test_shear_hand_calc():
    sh = aci.shear_design(150e3, 300, 540, 25, 420, 1500, 10, 2)
    Vc = 0.17 * 5 * 300 * 540
    Vc_b = 0.66 * (1500 / (300 * 540)) ** (1 / 3) * 5 * 300 * 540
    assert sh.Vc == pytest.approx(max(Vc, Vc_b))
    assert sh.phi_Vn >= 150e3
    assert sh.s_provided <= sh.s_max


def test_crack_spacing():
    # fy=420 -> fs=280: min(380 - 2.5*50, 300) = 255
    assert aci.crack_control_spacing(420, 50) == pytest.approx(255)


def test_min_thickness():
    assert aci.min_thickness(6000, "Simply supported", 420) == pytest.approx(375)


def test_eit_coefficients_reproduce_kg_cm_equations():
    # b = 30 cm, d = 54 cm, f'c = 240 ksc, fy = 4000 ksc, As = 15 cm^2, Vu = 10 t
    K, G = aci.KSC_TO_MPA, 9.80665
    fc, fy = 240 * K, 4000 * K
    sh = aci.shear_design(10000 * G, 300, 540, fc, 2400 * K, 1500, 9, 2, k=aci.EIT)
    vc_a = 0.53 * math.sqrt(240) * 30 * 54
    vc_b = 2.1 * (15 / (30 * 54)) ** (1 / 3) * math.sqrt(240) * 30 * 54
    assert sh.Vc / G == pytest.approx(max(vc_a, vc_b), rel=1e-9)
    as_min = aci.as_min_flexure(fc, fy, 300, 540, aci.EIT) / 100
    assert as_min == pytest.approx(max(0.8 * math.sqrt(240), 14) / 4000 * 30 * 54, rel=1e-9)
    assert aci.min_thickness(6000, "Simply supported", fy, aci.EIT) == pytest.approx(
        6000 / 16 * (0.4 + 4000 / 7000))


def test_default_coefficients_unchanged():
    assert aci.ACI_SI.vc == 0.17 and aci.ACI_SI.mks["vc"] == pytest.approx(0.543, abs=1e-3)


def test_load_combinations():
    assert aci.factored_line_load(1000, 500) == (pytest.approx(2000), "1.2D + 1.6L")
    assert aci.factored_line_load(1000, 0) == (pytest.approx(1400), "1.4D")
    assert aci.factored_line_load(1000, 500, "1.4D+1.7L") == (pytest.approx(2250), "1.4D + 1.7L")
