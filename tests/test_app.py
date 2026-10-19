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
    assert at.sidebar.selectbox[2].value.startswith("วสท.")
    shear_md = next(m.value for m in at.markdown if "Table 22.5.5.1" in m.value)
    assert "0.53λ√f'c" in shear_md and "2.1λρw" in shear_md


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


def test_av_min_display_units():
    at = _run()
    md = next(m.value for m in at.markdown if "9.6.3.4" in m.value)
    line = next(l for l in md.splitlines() if "Av,min/s" in l)
    # 3.5 · 30 cm / 2400 ksc = 0.04375 cm²/cm
    assert "0.0437" in line or "0.0438" in line
