from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _run():
    return AppTest.from_file(APP, default_timeout=60).run()


def test_default_inputs_pass_in_mks_units():
    at = _run()
    assert not at.exception
    assert len(at.success) == 1 and "30×60 cm" in at.success[0].value
    assert "cm" in at.metric[2].value


def test_uniform_load_and_manual_modes():
    at = _run()
    at.sidebar.radio[0].set_value("น้ำหนักแผ่สม่ำเสมอ").run()
    assert not at.exception
    at.sidebar.radio[1].set_value("กำหนดเอง (ตรวจสอบ)").run()
    assert not at.exception
    assert at.metric[2].value.startswith("RB9 @ 20.0 cm")


def test_undersized_beam_reports_ng():
    at = _run()
    mu = next(w for w in at.sidebar.number_input if w.label == "Mu (kg-m)")
    mu.set_value(200000.0).run()
    assert not at.exception
    assert len(at.error) >= 1
