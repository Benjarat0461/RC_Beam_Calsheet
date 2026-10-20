"""Streamlit app: Reinforced concrete beam design per ACI 318-19 (MKS units: cm, kg).

All inputs and outputs are in cm, kg, kg-m and ksc (kg/cm²). The calculation
core in aci318.py works in SI; values are converted exactly at the boundary.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import math
from datetime import date

import matplotlib.pyplot as plt
import streamlit as st
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

import aci318 as aci

st.set_page_config(page_title="RC Beam Design – ACI 318-19", page_icon="🏗️", layout="wide")

OK, NG = "✅ OK", "❌ NG"

# ---------------------------------------------------------------------------
# Unit conversion (MKS <-> SI)
# ---------------------------------------------------------------------------
G = 9.80665                 # N per kgf
KSC = aci.KSC_TO_MPA        # MPa per ksc


def cm_to_mm(x): return x * 10.0
def mm_to_cm(x): return x / 10.0
def ksc_to_mpa(x): return x * KSC
def mpa_to_ksc(x): return x / KSC
def kg_to_n(x): return x * G
def n_to_kg(x): return x / G
def kgm_to_nmm(x): return x * G * 1000.0
def nmm_to_kgm(x): return x / (G * 1000.0)
def mm2_to_cm2(x): return x / 100.0


STEEL_GRADES_KSC = {
    "SR24 (fy = 2,400 ksc)": 2400.0,
    "SD30 (fy = 3,000 ksc)": 3000.0,
    "SD40 (fy = 4,000 ksc)": 4000.0,
    "SD50 (fy = 5,000 ksc)": 5000.0,
}


def ok(flag: bool) -> str:
    return OK if flag else NG


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
st.title("🏗️ ออกแบบคานคอนกรีตเสริมเหล็ก ตามมาตรฐาน ACI 318-19")
st.caption("หน้าตัดสี่เหลี่ยมผืนผ้า · วิธีกำลัง (Strength Design) · หน่วย MKS: cm, kg, kg-m, ksc (kg/cm²)")

with st.sidebar:
    st.header("ข้อมูลโครงการ")
    project = st.text_input("ชื่อโครงการ", "Project")
    beam_id = st.text_input("ชื่อคาน", "B1")

    st.header("1) วัสดุ")
    fc_k = st.number_input("f'c (ksc, ทรงกระบอก)", 175.0, 800.0, 240.0, 10.0,
                           help="ACI 318-19 Table 19.2.1.1: f'c ≥ 17 MPa (≈ 175 ksc)")
    grades = list(STEEL_GRADES_KSC) + ["กำหนดเอง"]
    g_main = st.selectbox("เหล็กเสริมหลัก", grades, index=2)
    fy_k = (st.number_input("fy เหล็กหลัก (ksc)", 2000.0, 5600.0, 4000.0, 100.0)
            if g_main == "กำหนดเอง" else STEEL_GRADES_KSC[g_main])
    g_stir = st.selectbox("เหล็กปลอก", grades, index=0)
    fyt_k = (st.number_input("fyt เหล็กปลอก (ksc)", 2000.0, 5600.0, 2400.0, 100.0)
             if g_stir == "กำหนดเอง" else STEEL_GRADES_KSC[g_stir])
    coef_sets = {aci.EIT.name: aci.EIT, aci.ACI_SI.name: aci.ACI_SI}
    k = coef_sets[st.selectbox("ค่าสัมประสิทธิ์ในสมการ", list(coef_sets),
                               help="วสท.: ใช้ค่าปัดในหน่วย kg-cm เช่น Vc = 0.53√f'c·bw·d, "
                                    "As,min = 14/fy·b·d")]
    lam = st.number_input("λ (คอนกรีตน้ำหนักปกติ = 1.0)", 0.75, 1.0, 1.0, 0.05)
    agg_cm = st.number_input("ขนาดมวลรวมโตสุด (cm)", 1.0, 4.0, 2.0, 0.5)

    st.header("2) หน้าตัดคาน")
    b_cm = st.number_input("ความกว้าง b (cm)", 15.0, 200.0, 30.0, 2.5)
    h_cm = st.number_input("ความลึก h (cm)", 20.0, 300.0, 60.0, 2.5)
    cover_cm = st.number_input("ระยะหุ้มถึงผิวเหล็กปลอก (cm)", 2.0, 10.0, 4.0, 0.5,
                               help="ACI 318-19 Table 20.5.1.3.1: ไม่สัมผัสดิน/อากาศ = 4 cm")
    span = st.number_input("ความยาวช่วงคาน L (m)", 0.5, 30.0, 6.0, 0.5)
    support = st.selectbox("สภาพที่รองรับ (สำหรับความลึกต่ำสุด Table 9.3.1.1)",
                           ["Simply supported", "One end continuous", "Both ends continuous",
                            "Cantilever"])

    st.header("3) แรงกระทำ")
    combo_key = st.radio("ตัวคูณน้ำหนัก", list(aci.LOAD_COMBOS),
                         format_func=aci.LOAD_COMBOS.get)
    phi_set = aci.COMBO_PHI[combo_key]
    st.caption(f"φ ดัด = {phi_set.tension:.2f} (tension-controlled) ถึง {phi_set.compression:.2f} "
               f"(compression-controlled) · φ เฉือน = {phi_set.shear:.2f}  [{phi_set.name}]")
    load_mode = st.radio("วิธีป้อนแรง", ["ป้อน Mu, Vu โดยตรง", "น้ำหนักแผ่สม่ำเสมอ"])
    if load_mode == "ป้อน Mu, Vu โดยตรง":
        Mu_in = st.number_input("Mu (kg-m)", 0.0, 1e7, 25000.0, 500.0)
        Vu_in = st.number_input("Vu ที่หน้าตัดวิกฤต (kg)", 0.0, 1e7, 20000.0, 500.0)
        st.caption("Mu, Vu ที่ป้อนต้องคำนวณด้วยตัวคูณน้ำหนักที่เลือกด้านบน")
        load_info = None
    else:
        system = st.selectbox("ระบบโครงสร้าง", ["คานช่วงเดียวธรรมดา", "คานยื่น"])
        wD_sdl = st.number_input("น้ำหนักบรรทุกคงที่เพิ่มเติม wD (kg/m)", 0.0, 1e6, 1500.0, 100.0)
        wL = st.number_input("น้ำหนักบรรทุกจร wL (kg/m)", 0.0, 1e6, 1000.0, 100.0)
        self_wt = st.checkbox("รวมน้ำหนักคานเอง (2,400 kg/m³)", True)
        load_info = dict(system=system, wD_sdl=wD_sdl, wL=wL, self_wt=self_wt)

    st.header("4) เหล็กเสริม")
    bars = list(aci.BAR_SIZES)
    db_t_name = st.selectbox("เหล็กรับแรงดึง (ล่าง)", bars, index=bars.index("DB20"))
    db_c_name = st.selectbox("เหล็กรับแรงอัด/เหล็กยึดปลอก (บน)", bars, index=bars.index("DB16"))
    ds_name = st.selectbox("เหล็กปลอก", bars, index=bars.index("RB9"))
    legs = st.number_input("จำนวนขาเหล็กปลอก", 2, 8, 2, 1)
    use_b10 = st.checkbox("จำนวนเหล็กต่อชั้น = b/10 (เช่น b = 30 cm → 3 เส้น)", True,
                          help="ชั้นที่ 2 ขึ้นไปวางตรงกับตำแหน่งเหล็กชั้นแรก เริ่มจากมุมเข้าหากลาง")
    mode = st.radio("การเลือกเหล็ก", ["ออกแบบอัตโนมัติ", "กำหนดเอง (ตรวจสอบ)"])
    if mode == "กำหนดเอง (ตรวจสอบ)":
        n_t_user = st.number_input("จำนวนเหล็กล่าง (เส้น)", 2, 60, 4, 1)
        n_c_user = st.number_input("จำนวนเหล็กบน (เส้น)", 2, 60, 2, 1)
        s_user_cm = st.number_input("ระยะเรียงเหล็กปลอก s (cm)", 5.0, 60.0, 20.0, 2.5)
    else:
        n_t_user = n_c_user = s_user_cm = None

# Coefficients shown in the kg-cm form of each equation
C = k.mks


def cf(x: float) -> str:
    return f"{x:.3g}"


# --- convert inputs to SI for the calculation core ---
fc, fy, fyt = ksc_to_mpa(fc_k), ksc_to_mpa(fy_k), ksc_to_mpa(fyt_k)
b, h, cover = cm_to_mm(b_cm), cm_to_mm(h_cm), cm_to_mm(cover_cm)
d_agg = cm_to_mm(agg_cm)
s_user = cm_to_mm(s_user_cm) if s_user_cm else None
db_t = aci.BAR_SIZES[db_t_name]
db_c = aci.BAR_SIZES[db_c_name]
d_s = aci.BAR_SIZES[ds_name]

# ---------------------------------------------------------------------------
# Loads (kg, m)
# ---------------------------------------------------------------------------
d_est_m = (h - cover - d_s - db_t / 2.0) / 1000.0
if load_info is None:
    Mu_kgm, Vu_kg = Mu_in, Vu_in
    load_lines = [f"Mu = {Mu_kgm:,.0f} kg-m (ผู้ใช้กำหนด)", f"Vu = {Vu_kg:,.0f} kg (ผู้ใช้กำหนด)"]
else:
    w_sw = 2400.0 * b_cm / 100.0 * h_cm / 100.0 if load_info["self_wt"] else 0.0
    wD = load_info["wD_sdl"] + w_sw
    wu, combo = aci.factored_line_load(wD, load_info["wL"], combo_key)
    if load_info["system"] == "คานช่วงเดียวธรรมดา":
        Mu_kgm = wu * span ** 2 / 8.0
        Vu_kg = wu * max(span / 2.0 - d_est_m, 0.0)
        m_txt, v_txt = "wu·L²/8", "wu·(L/2 − d)"
    else:
        Mu_kgm = wu * span ** 2 / 2.0
        Vu_kg = wu * max(span - d_est_m, 0.0)
        m_txt, v_txt = "wu·L²/2", "wu·(L − d)"
    load_lines = [
        f"น้ำหนักคานเอง = 2,400 × {b_cm / 100:.2f} × {h_cm / 100:.2f} = {w_sw:,.0f} kg/m",
        f"wD = {wD:,.0f} kg/m, wL = {load_info['wL']:,.0f} kg/m",
        (f"wu = max(1.4D, 1.2D + 1.6L) = {wu:,.0f} kg/m  [{combo}]  (ACI 5.3.1)"
         if combo_key == "ACI" else
         f"wu = 1.4 × {wD:,.0f} + 1.7 × {load_info['wL']:,.0f} = {wu:,.0f} kg/m  (1.4D + 1.7L)"),
        f"Mu = {m_txt} = {Mu_kgm:,.0f} kg-m",
        f"Vu (ที่ระยะ d จากหน้าที่รองรับ, 9.4.3.2) = {v_txt} = {Vu_kg:,.0f} kg",
    ]

phi_lines = [
    f"ตัวคูณน้ำหนัก: {aci.LOAD_COMBOS[combo_key]}",
    f"φ แรงดัด: {phi_set.tension:.2f} (tension-controlled) ถึง {phi_set.compression:.2f} "
    f"(compression-controlled), แปรผันเชิงเส้นตาม εt ในช่วง transition",
    f"φ แรงเฉือน: {phi_set.shear:.2f}",
    f"อ้างอิง: {phi_set.name}",
]

Mu = kgm_to_nmm(Mu_kgm)
Vu = kg_to_n(Vu_kg)

# ---------------------------------------------------------------------------
# Design (SI core)
# ---------------------------------------------------------------------------
errors = []
if fy > 550:
    errors.append("fy สำหรับเหล็กรับแรงดัดต้องไม่เกิน 550 MPa ≈ 5,600 ksc (Table 20.2.2.4a)")
if fc < 17:
    errors.append("f'c ต้องไม่น้อยกว่า 17 MPa ≈ 175 ksc (Table 19.2.1.1)")
for e in errors:
    st.error(e)

try:
    flex = aci.design_flexure(Mu, b, h, fc, fy, cover, d_s, d_agg, db_t, db_c,
                              n_t=n_t_user, n_c=n_c_user, k=k, p=phi_set,
                              max_per_layer=aci.bars_per_layer_rule(b) if use_b10 else None)
except ValueError as exc:
    st.error(f"ไม่สามารถออกแบบได้: {exc}")
    st.stop()

res = flex.result
d = flex.d
shear = aci.shear_design(Vu, b, d, fc, fyt, flex.tension.area, d_s, int(legs), lam, s_user, k=k, p=phi_set)
h_min = aci.min_thickness(span * 1000.0, support, fy, k)
s_crack = aci.crack_control_spacing(fy, cover + d_s, k)
s_bot_cc = flex.tension.cc_spacing

checks = {
    "กำลังรับโมเมนต์ φMn ≥ Mu": flex.checks["strength"],
    "εt ≥ 0.004 (9.3.3.1)": flex.checks["eps_t"],
    "As ≥ As,min (9.6.1.2 / 9.6.1.3)": flex.checks["as_min"],
    "ระยะช่องว่างเหล็กล่าง (25.2.1)": flex.checks["spacing_t"],
    "ระยะช่องว่างเหล็กบน (25.2.1)": flex.checks["spacing_c"],
    "จำนวนชั้นเหล็กเหมาะสม": flex.checks["layers"],
    "ขนาดหน้าตัดรับแรงเฉือน (22.5.1.2)": Vu <= shear.phi_Vn_max,
    "กำลังรับแรงเฉือน φVn ≥ Vu": shear.phi_Vn >= Vu,
    "ระยะเรียงเหล็กปลอก s ≤ s,max (9.7.6.2.2)": shear.s_provided <= shear.s_max + 1e-6,
    "ระยะเหล็กควบคุมรอยร้าว (24.3.2)": s_bot_cc <= s_crack,
}
all_ok = all(checks.values()) and not errors

# --- results in MKS for display ---
phi_Mn_kgm = nmm_to_kgm(res.phi_Mn)
Mn_kgm = nmm_to_kgm(res.Mn)
phi_Vn_kg = n_to_kg(shear.phi_Vn)
Vc_kg = n_to_kg(shear.Vc)
Vs_kg = n_to_kg(shear.Vs)
Vs_req_kg = n_to_kg(shear.Vs_req)
phi_Vn_max_kg = n_to_kg(shear.phi_Vn_max)
d_cm, dt_cm, dc_cm = mm_to_cm(d), mm_to_cm(flex.dt), mm_to_cm(flex.d_comp)
As_cm2 = mm2_to_cm2(flex.tension.area)
Asc_cm2 = mm2_to_cm2(flex.compression.area)
s_prov_cm = mm_to_cm(shear.s_provided)

# --- singly / doubly reinforced decision and required steel (at the actual d, d') ---
req = flex.req
req_lines = [
    f"φMn,max (เสริมเหล็กรับแรงดึงอย่างเดียว ที่ขีดจำกัด tension-controlled εt = εty + 0.003): "
    f"c = 0.003/(0.003 + {fy / aci.ES:.5f} + 0.003)·d = {mm_to_cm(req.c_tc):.2f} cm, "
    f"a = β₁c = {mm_to_cm(req.a_tc):.2f} cm",
    f"φMn,max = {req.phi:.2f} × 0.85f'c·a·b·(d − a/2) = {nmm_to_kgm(req.phi_Mn_max_singly):,.0f} kg-m "
    f"{'≥' if not req.doubly else '<'} Mu = {Mu_kgm:,.0f} kg-m",
]
if not req.doubly:
    req_lines += [
        "→ **หน้าตัดเสริมเหล็กรับแรงดึงอย่างเดียว (Singly reinforced)**",
        f"Rn = Mu/(φbd²) = {mpa_to_ksc(Mu / (req.phi * b * d ** 2)):.2f} ksc, "
        f"ρ = 0.85f'c/fy·[1 − √(1 − 2Rn/0.85f'c)] = {req.rho:.5f}",
        f"As,req = ρbd = {mm2_to_cm2(req.As):.2f} cm²",
    ]
else:
    req_lines += [
        "→ **Mu > φMn,max ต้องออกแบบเป็นคานเสริมเหล็กรับแรงอัด (Doubly reinforced) อัตโนมัติ**",
        f"Mn1 = 0.85f'c·a·b·(d − a/2) = {nmm_to_kgm(req.Mn1):,.0f} kg-m, "
        f"As1 = 0.85f'c·a·b/fy = {mm2_to_cm2(req.As1):.2f} cm²",
        f"Mn2 = Mu/φ − Mn1 = {Mu_kgm:,.0f}/{req.phi:.2f} − {nmm_to_kgm(req.Mn1):,.0f} = "
        f"{nmm_to_kgm(req.Mn2):,.0f} kg-m",
        f"ε's = 0.003(c − d')/c = {req.eps_sc:.5f} → f's = Es·ε's ≤ fy = {mpa_to_ksc(req.fsc):,.0f} ksc "
        f"({'เหล็กรับแรงอัดคราก' if req.sc_yields else 'เหล็กรับแรงอัดยังไม่คราก'})",
        f"A's,req = Mn2/[(f's − 0.85f'c)(d − d')] = {mm2_to_cm2(req.Asc):.2f} cm²",
        f"As2 = A's(f's − 0.85f'c)/fy = {mm2_to_cm2(req.As2):.2f} cm²",
        f"As,req = As1 + As2 = {mm2_to_cm2(req.As):.2f} cm²",
    ]

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
t_lay = " + ".join(str(k) for k in flex.tension.layers)
c_lay = " + ".join(str(k) for k in flex.compression.layers)
bot_txt = f"{flex.tension.n}-{db_t_name}" + (f" ({t_lay} ชั้น)" if len(flex.tension.layers) > 1 else "")
top_txt = f"{flex.compression.n}-{db_c_name}" + (f" ({c_lay} ชั้น)" if len(flex.compression.layers) > 1 else "")
stir_txt = f"{ds_name} @ {s_prov_cm:.1f} cm ({legs} ขา)"

beam_type = ("คานเสริมเหล็กรับแรงอัด (Doubly reinforced)" if req.doubly
             else "คานเสริมเหล็กรับแรงดึงอย่างเดียว (Singly reinforced)")
if all_ok:
    st.success(f"**{beam_id} {b_cm:g}×{h_cm:g} cm** — ผ่านทุกข้อกำหนด · {beam_type}")
else:
    st.error(f"**{beam_id} {b_cm:g}×{h_cm:g} cm** — มีรายการไม่ผ่าน กรุณาปรับหน้าตัดหรือเหล็กเสริม")

c1, c2, c3, c4 = st.columns(4)
c1.metric("เหล็กล่าง", f"{flex.tension.n}-{db_t_name}",
          f"As = {As_cm2:.2f} cm² · ชั้น {t_lay}", delta_color="off")
c2.metric("เหล็กบน (รับแรงอัด)" if req.doubly else "เหล็กบน", f"{flex.compression.n}-{db_c_name}",
          f"A's = {Asc_cm2:.2f} cm² · ชั้น {c_lay}", delta_color="off")
c3.metric("เหล็กปลอก", stir_txt)
c4.metric("อัตราส่วนการใช้งาน", f"M {Mu / res.phi_Mn:.2f} | V {Vu / shear.phi_Vn:.2f}"
          if res.phi_Mn > 0 and shear.phi_Vn > 0 else "-")

tab_sum, tab_flex, tab_shear, tab_sec, tab_sheet = st.tabs(
    ["📋 สรุปผล", "📐 แรงดัด", "✂️ แรงเฉือน", "🧱 หน้าตัด", "📝 รายการคำนวณ"])

with tab_sum:
    st.subheader("แรงออกแบบ")
    for line in load_lines:
        st.write("• " + line)
    st.subheader("ตัวคูณลดกำลัง φ (เปลี่ยนตามตัวคูณน้ำหนัก)")
    p1, p2, p3 = st.columns(3)
    p1.metric("φ ดัด (ใช้จริง)", f"{res.phi:.3f}", res.classification, delta_color="off")
    p2.metric("φ ดัด tension / compression", f"{phi_set.tension:.2f} / {phi_set.compression:.2f}")
    p3.metric("φ เฉือน", f"{phi_set.shear:.2f}")
    st.caption(f"{aci.LOAD_COMBOS[combo_key]} → {phi_set.name}")
    st.subheader("ประเภทหน้าตัด")
    (st.warning if req.doubly else st.info)(
        f"φMn,max เสริมเหล็กรับแรงดึงอย่างเดียว = {nmm_to_kgm(req.phi_Mn_max_singly):,.0f} kg-m "
        f"{'<' if req.doubly else '≥'} Mu = {Mu_kgm:,.0f} kg-m → **{beam_type}**")
    if mode != "ออกแบบอัตโนมัติ" and res.phi_Mn < Mu:
        st.error(f"เหล็กที่กำหนดรับโมเมนต์ไม่พอ ต้องการ As ≥ {mm2_to_cm2(req.As):.2f} cm²"
                 + (f" และ A's ≥ {mm2_to_cm2(req.Asc):.2f} cm²" if req.doubly else "")
                 + " — เลือก \"ออกแบบอัตโนมัติ\" เพื่อให้โปรแกรมจัดเหล็กให้")
    st.subheader("ผลการตรวจสอบ")
    st.table({"รายการ": list(checks), "ผล": [ok(v) for v in checks.values()]})
    st.subheader("ความลึกต่ำสุด (Table 9.3.1.1) — ไม่ต้องตรวจสอบการแอ่นตัว")
    h_min_cm = mm_to_cm(h_min)
    if h >= h_min:
        st.info(f"h = {h_cm:g} cm ≥ h,min = {h_min_cm:.1f} cm → ไม่ต้องคำนวณการแอ่นตัว")
    else:
        st.warning(f"h = {h_cm:g} cm < h,min = {h_min_cm:.1f} cm → ต้องคำนวณการแอ่นตัวตาม 24.2")
    if h > 900:
        st.warning("h > 90 cm → ต้องเสริมเหล็กผิว (skin reinforcement) ตาม 9.7.2.3")

with tab_flex:
    b1 = aci.beta1(fc)
    eps_ty = fy / aci.ES
    st.markdown("**ขั้นที่ 1: ตรวจสอบความจำเป็นของเหล็กรับแรงอัด และหาเหล็กเสริมที่ต้องการ (22.2)**")
    st.markdown("\n".join(f"{i}. {l}" for i, l in enumerate(req_lines, 1)))
    st.markdown("**ขั้นที่ 2: ตรวจสอบหน้าตัดที่เลือกด้วย strain compatibility**")
    st.markdown(f"""
| รายการ | ค่า | อ้างอิง |
|---|---|---|
| β₁ | {b1:.3f} | Table 22.2.2.4.3 |
| d (ถึงศูนย์ถ่วงเหล็กล่าง) | {d_cm:.2f} cm | |
| dt (ถึงเหล็กชั้นนอกสุด) | {dt_cm:.2f} cm | |
| d' (ถึงศูนย์ถ่วงเหล็กบน) | {dc_cm:.2f} cm | |
| As,req | {mm2_to_cm2(flex.As_req):.2f} cm² | 22.2 |
| A's,req | {mm2_to_cm2(flex.Asc_req):.2f} cm² | {beam_type} |
| A's,provided | {Asc_cm2:.2f} cm² | |
| As,min = max({cf(C['asmin1'])}√f'c, {cf(C['asmin2'])})·b·d/fy | {mm2_to_cm2(flex.As_min):.2f} cm² | 9.6.1.2 |
| As,provided | {As_cm2:.2f} cm² | |
| ρ = As/(b·d) | {flex.tension.area / (b * d):.4f} | |
| c (strain compatibility) | {mm_to_cm(res.c):.2f} cm | 22.2.1 |
| a = β₁c | {mm_to_cm(res.a):.2f} cm | 22.2.2.4.1 |
| εt | {res.eps_t:.5f} (εty = fy/Es = {eps_ty:.5f}) | |
| การจำแนกหน้าตัด | {res.classification} | Table 21.2.2 |
| φ = {phi_set.compression:.2f} + {phi_set.tension - phi_set.compression:.2f}(εt − εty)/0.003, {phi_set.compression:.2f} ≤ φ ≤ {phi_set.tension:.2f} | **{res.phi:.3f}** | {phi_set.name} |
| Mn | {Mn_kgm:,.0f} kg-m | |
| **φMn** | **{phi_Mn_kgm:,.0f} kg-m** | |
| Mu | {Mu_kgm:,.0f} kg-m | {ok(res.phi_Mn >= Mu)} |
""")
    st.caption("Es = 2.04 × 10⁶ ksc (200,000 MPa), εcu = 0.003")
    st.markdown("**แรงและหน่วยแรงในเหล็กเสริมแต่ละชั้น** (+ = อัด, − = ดึง)")
    st.table({
        "ความลึกจากผิวบน (cm)": [f"{mm_to_cm(s['depth']):.2f}" for s in res.steel],
        "As (cm²)": [f"{mm2_to_cm2(s['area']):.2f}" for s in res.steel],
        "ความเครียด ε": [f"{s['strain']:.5f}" for s in res.steel],
        "fs (ksc)": [f"{mpa_to_ksc(s['stress']):,.0f}" for s in res.steel],
        "แรง (kg)": [f"{n_to_kg(s['force']):,.0f}" for s in res.steel],
    })
    fs_k = 2.0 / 3.0 * fy_k
    st.markdown(f"""
**การควบคุมรอยร้าว (24.3.2)**: fs = ⅔fy = {fs_k:,.0f} ksc, cc = {cover_cm + d_s / 10:.1f} cm
s,max = min[38({C['fs_ref']:,.0f}/fs) − 2.5cc, 30({C['fs_ref']:,.0f}/fs)] = **{mm_to_cm(s_crack):.1f} cm**;
ระยะเหล็กล่างชั้นนอก (ศูนย์กลางถึงศูนย์กลาง) = {mm_to_cm(s_bot_cc):.1f} cm → {ok(s_bot_cc <= s_crack)}

**ระยะช่องว่างระหว่างเหล็ก (25.2.1)**: ต้องการ ≥ max(2.5 cm, db, 4/3·dagg)
— ล่าง: {mm_to_cm(flex.tension.clear_spacing):.1f} ≥ {mm_to_cm(flex.tension.s_clear_min):.1f} cm {ok(flex.checks['spacing_t'])}
— บน: {mm_to_cm(flex.compression.clear_spacing):.1f} ≥ {mm_to_cm(flex.compression.s_clear_min):.1f} cm {ok(flex.checks['spacing_c'])}

**การจัดเหล็กเป็นชั้น**: จำนวนเหล็กต่อชั้นสูงสุด = {flex.tension.per_layer} เส้น (ล่าง), {flex.compression.per_layer} เส้น (บน)
{"— ตามกฎ b/10 = " + f"{b_cm:g}/10 → {aci.bars_per_layer_rule(b)} เส้น และไม่เกินที่ระยะช่องว่างยอมให้" if use_b10 else "— จำกัดด้วยระยะช่องว่างขั้นต่ำเท่านั้น"};
ชั้นที่ 2 ขึ้นไปวางตรงกับตำแหน่งเหล็กชั้นแรก (เริ่มจากมุมเข้าหากลาง)
""")
    layer_rows = []
    for name, lay, from_top in (("ล่าง", flex.tension, False), ("บน", flex.compression, True)):
        for i, (kk, y, xs) in enumerate(zip(lay.layers, lay.depths, lay.x), 1):
            layer_rows.append({
                "เหล็ก": name, "ชั้น": i, "จำนวน": kk,
                "ระยะถึงศูนย์กลางเหล็ก (cm)": f"{mm_to_cm(y):.2f} จากผิว{'บน' if from_top else 'ล่าง'}",
                "ตำแหน่ง x จากขอบซ้าย (cm)": ", ".join(f"{mm_to_cm(x):.1f}" for x in xs),
            })
    st.table(layer_rows)
    for name, lay in (("ล่าง", flex.tension), ("บน", flex.compression)):
        if not lay.symmetric:
            st.warning(f"เหล็ก{name}ชั้นบนวางไม่สมมาตร (จำนวนคี่บนเหล็กชั้นแรกจำนวนคู่) "
                       "— แนะนำปรับจำนวนเหล็กให้เป็นเลขคู่")

with tab_shear:
    sqrt_fc_k = min(math.sqrt(fc_k), C['sqrt_fc_max'])
    st.markdown(f"""
| รายการ | ค่า | อ้างอิง |
|---|---|---|
| Vu | {Vu_kg:,.0f} kg | |
| √f'c (≤ {cf(C['sqrt_fc_max'])}) | {sqrt_fc_k:.2f} √ksc | 22.5.3.1 |
| fyt ใช้คำนวณ (≤ {C['fyt_max']:,.0f} ksc) | {min(fyt_k, C['fyt_max']):,.0f} ksc | 20.2.2.4 |
| ρw = As/(bw·d) | {flex.tension.area / (b * d):.4f} | |
| λs = √(2/(1+0.04d)) ≤ 1 (d เป็น cm) | {shear.lambda_s:.3f} | 22.5.5.1.3 |
| Vc = max({cf(C['vc'])}λ√f'c, {cf(C['vc_rho'])}λρw^⅓√f'c)·bw·d ≤ {cf(C['vc_max'])}λ√f'c·bw·d | {Vc_kg:,.0f} kg | Table 22.5.5.1 |
| φVc | {phi_set.shear * Vc_kg:,.0f} kg | φ = {phi_set.shear:.2f} ({phi_set.name}) |
| ต้องใช้ Av,min หรือไม่ (Vu > φ{cf(C['av_trig'])}λ√f'c·bw·d) | {"ใช่" if shear.av_min_required else "ไม่ (แต่แนะนำให้ใส่)"} | 9.6.3.1 |
| Av,min/s = max({cf(C['avmin1'])}√f'c, {cf(C['avmin2'])})·bw/fyt | {shear.Av_min_s / 10:.4f} cm²/cm | 9.6.3.4 |
| Vs,req = Vu/φ − Vc | {Vs_req_kg:,.0f} kg | 22.5.8.5.3 |
| Av ({legs} ขา {ds_name}) | {mm2_to_cm2(shear.Av):.2f} cm² | |
| s,max (d/2 ≤ 60 cm หรือ d/4 ≤ 30 cm ถ้า Vs > {cf(C['smax_vs'])}√f'c·bw·d) | {mm_to_cm(shear.s_max):.1f} cm | 9.7.6.2.2 |
| s,required | {mm_to_cm(shear.s_req):.1f} cm | |
| **s,provided** | **{s_prov_cm:.1f} cm** | |
| Vs = Av·fyt·d/s | {Vs_kg:,.0f} kg | 22.5.8.5.3 |
| **φVn = φ(Vc + Vs)** | **{phi_Vn_kg:,.0f} kg** | {ok(shear.phi_Vn >= Vu)} |
| φ(Vc + {cf(C['vs_max'])}√f'c·bw·d) | {phi_Vn_max_kg:,.0f} kg | 22.5.1.2 {ok(Vu <= shear.phi_Vn_max)} |
""")
    for n in shear.notes:
        if n.startswith("fyt limited"):
            n = f"fyt จำกัดไม่เกิน {C['fyt_max']:,.0f} ksc (Table 20.2.2.4a)"
        n = n.replace("smax_vs·√fc'", f"{cf(C['smax_vs'])}√f'c")
        st.info(n)

with tab_sec:
    # drawing in cm
    cv, ds_c = cover_cm, d_s / 10.0
    fig, ax = plt.subplots(figsize=(4.5, min(4.5 * h_cm / b_cm, 10)))
    ax.add_patch(Rectangle((0, 0), b_cm, h_cm, fc="#d9d9d9", ec="black", lw=1.5))
    ax.add_patch(FancyBboxPatch((cv + ds_c / 2, cv + ds_c / 2), b_cm - 2 * cv - ds_c,
                                h_cm - 2 * cv - ds_c,
                                boxstyle=f"round,pad=0,rounding_size={2 * ds_c}",
                                fill=False, ec="#1f4e79", lw=2))

    def draw(layout, db_mm, from_top: bool, color):
        r = db_mm / 20.0
        for y, xs in zip(layout.depths, layout.x):
            y_cm = y / 10.0
            yy = h_cm - y_cm if from_top else y_cm
            for x in xs:
                ax.add_patch(Circle((x / 10.0, yy), r, fc=color, ec="black"))

    draw(flex.tension, db_t, False, "#c00000")
    draw(flex.compression, db_c, True, "#2e75b6")
    ax.annotate("", (0, -3), (b_cm, -3), arrowprops=dict(arrowstyle="<->"))
    ax.text(b_cm / 2, -6, f"b = {b_cm:g} cm", ha="center", va="top")
    ax.annotate("", (-3, 0), (-3, h_cm), arrowprops=dict(arrowstyle="<->"))
    ax.text(-6, h_cm / 2, f"h = {h_cm:g} cm", ha="right", va="center", rotation=90)
    ax.set_xlim(-15, b_cm + 5)
    ax.set_ylim(-13, h_cm + 5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"{beam_id}  {b_cm:g}×{h_cm:g} cm")
    col_a, col_b = st.columns([1, 1])
    col_a.pyplot(fig)
    col_b.markdown(f"""
**เหล็กบน:** {top_txt}
**เหล็กล่าง:** {bot_txt}
**เหล็กปลอก:** {stir_txt}
**ระยะหุ้ม:** {cover_cm:g} cm
**f'c:** {fc_k:,.0f} ksc, **fy:** {fy_k:,.0f} ksc, **fyt:** {fyt_k:,.0f} ksc
""")

with tab_sheet:
    sheet = f"""# รายการคำนวณออกแบบคาน {beam_id}
โครงการ: {project}  วันที่: {date.today():%d/%m/%Y}  มาตรฐาน: ACI 318-19  หน่วย: cm, kg  
ค่าสัมประสิทธิ์: {k.name}

## 1. ข้อมูล
- f'c = {fc_k:,.0f} ksc, fy = {fy_k:,.0f} ksc, fyt = {fyt_k:,.0f} ksc, Es = 2.04×10⁶ ksc, λ = {lam}
- b × h = {b_cm:g} × {h_cm:g} cm, ระยะหุ้ม = {cover_cm:g} cm, L = {span:.2f} m ({support})

## 2. แรงออกแบบและตัวคูณลดกำลัง
""" + "\n".join(f"- {l}" for l in load_lines + phi_lines) + f"""

## 3. ออกแบบรับแรงดัด
- β1 = {aci.beta1(fc):.3f}, d = {d_cm:.2f} cm, dt = {dt_cm:.2f} cm, d' = {dc_cm:.2f} cm
""" + "\n".join(f"- {l}" for l in req_lines) + f"""
- As,req = {mm2_to_cm2(flex.As_req):.2f} cm², A's,req = {mm2_to_cm2(flex.Asc_req):.2f} cm², As,min = {mm2_to_cm2(flex.As_min):.2f} cm²
- ใช้เหล็กล่าง {bot_txt}: As = {As_cm2:.2f} cm²; เหล็กบน {top_txt}: A's = {Asc_cm2:.2f} cm²
- c = {mm_to_cm(res.c):.2f} cm, a = {mm_to_cm(res.a):.2f} cm, εt = {res.eps_t:.5f} → {res.classification}, φ = {res.phi:.3f}
- φMn = {res.phi:.3f} × {Mn_kgm:,.0f} = {phi_Mn_kgm:,.0f} kg-m {"≥" if res.phi_Mn >= Mu else "<"} Mu = {Mu_kgm:,.0f} kg-m → {ok(res.phi_Mn >= Mu)}

## 4. ออกแบบรับแรงเฉือน
- Vc = max({cf(C['vc'])}λ√f'c, {cf(C['vc_rho'])}λρw^⅓√f'c)·bw·d = {Vc_kg:,.0f} kg, φ = {phi_set.shear:.2f}, φVc = {phi_set.shear * Vc_kg:,.0f} kg
- Vs,req = {Vs_req_kg:,.0f} kg, s,max = {mm_to_cm(shear.s_max):.1f} cm
- ใช้เหล็กปลอก {stir_txt}: Vs = {Vs_kg:,.0f} kg
- φVn = {phi_Vn_kg:,.0f} kg {"≥" if shear.phi_Vn >= Vu else "<"} Vu = {Vu_kg:,.0f} kg → {ok(shear.phi_Vn >= Vu)}

## 5. สรุปการตรวจสอบ
""" + "\n".join(f"- {k}: {ok(v)}" for k, v in checks.items()) + f"""
- ความลึกต่ำสุด h,min = {mm_to_cm(h_min):.1f} cm (Table 9.3.1.1) → {"ไม่ต้องตรวจการแอ่นตัว" if h >= h_min else "ต้องตรวจการแอ่นตัว"}
"""
    st.markdown(sheet)
    st.download_button("⬇️ ดาวน์โหลดรายการคำนวณ (.md)", sheet, file_name=f"{beam_id}_calc.md")

st.caption("หมายเหตุ: โปรแกรมนี้ใช้เพื่อช่วยคำนวณเบื้องต้น ผู้ออกแบบต้องตรวจสอบผลการคำนวณและรับผิดชอบงานออกแบบด้วยตนเอง "
           "(ไม่รวมการออกแบบรับแรงบิด ระยะฝังยึด/ต่อทาบ และการคำนวณการแอ่นตัว) · "
           f"ค่าสัมประสิทธิ์: {k.name} · 1 kg = 9.80665 N")
