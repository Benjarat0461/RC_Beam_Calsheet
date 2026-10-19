"""Streamlit app: Reinforced concrete beam design per ACI 318-19.

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


def ok(flag: bool) -> str:
    return OK if flag else NG


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
st.title("🏗️ ออกแบบคานคอนกรีตเสริมเหล็ก ตามมาตรฐาน ACI 318-19")
st.caption("หน้าตัดสี่เหลี่ยมผืนผ้า · วิธีกำลัง (Strength Design) · หน่วย SI (mm, MPa, kN)")

with st.sidebar:
    st.header("ข้อมูลโครงการ")
    project = st.text_input("ชื่อโครงการ", "Project")
    beam_id = st.text_input("ชื่อคาน", "B1")

    st.header("1) วัสดุ")
    fc_unit = st.radio("หน่วยกำลังอัดคอนกรีต", ["ksc", "MPa"], horizontal=True)
    if fc_unit == "ksc":
        fc_ksc = st.number_input("f'c (ksc, ทรงกระบอก)", 150.0, 800.0, 240.0, 10.0)
        fc = fc_ksc * aci.KSC_TO_MPA
    else:
        fc = st.number_input("f'c (MPa)", 17.0, 80.0, 24.0, 1.0)
    st.caption(f"f'c = {fc:.2f} MPa = {fc / aci.KSC_TO_MPA:.0f} ksc")

    grades = list(aci.STEEL_GRADES) + ["กำหนดเอง"]
    g_main = st.selectbox("เหล็กเสริมหลัก", grades, index=2)
    fy = (st.number_input("fy เหล็กหลัก (MPa)", 200.0, 550.0, 420.0, 5.0)
          if g_main == "กำหนดเอง" else aci.STEEL_GRADES[g_main])
    g_stir = st.selectbox("เหล็กปลอก", grades, index=0)
    fyt = (st.number_input("fyt เหล็กปลอก (MPa)", 200.0, 550.0, 235.0, 5.0)
           if g_stir == "กำหนดเอง" else aci.STEEL_GRADES[g_stir])
    lam = st.number_input("λ (คอนกรีตน้ำหนักปกติ = 1.0)", 0.75, 1.0, 1.0, 0.05)
    d_agg = st.number_input("ขนาดมวลรวมโตสุด (mm)", 10.0, 40.0, 20.0, 5.0)

    st.header("2) หน้าตัดคาน")
    b = st.number_input("ความกว้าง b (mm)", 150.0, 2000.0, 300.0, 25.0)
    h = st.number_input("ความลึก h (mm)", 200.0, 3000.0, 600.0, 25.0)
    cover = st.number_input("ระยะหุ้มถึงผิวเหล็กปลอก (mm)", 20.0, 100.0, 40.0, 5.0,
                            help="ACI 318-19 Table 20.5.1.3.1: ไม่สัมผัสดิน/อากาศ = 40 mm")
    span = st.number_input("ความยาวช่วงคาน L (m)", 0.5, 30.0, 6.0, 0.5)
    support = st.selectbox("สภาพที่รองรับ (สำหรับความลึกต่ำสุด Table 9.3.1.1)",
                           ["Simply supported", "One end continuous", "Both ends continuous",
                            "Cantilever"])

    st.header("3) แรงกระทำ")
    load_mode = st.radio("วิธีป้อนแรง", ["ป้อน Mu, Vu โดยตรง", "น้ำหนักแผ่สม่ำเสมอ"])
    if load_mode == "ป้อน Mu, Vu โดยตรง":
        Mu_kNm = st.number_input("Mu (kN·m)", 0.0, 1e5, 250.0, 5.0)
        Vu_kN = st.number_input("Vu ที่หน้าตัดวิกฤต (kN)", 0.0, 1e5, 200.0, 5.0)
        load_info = None
    else:
        sys = st.selectbox("ระบบโครงสร้าง", ["คานช่วงเดียวธรรมดา", "คานยื่น"])
        wD_sdl = st.number_input("น้ำหนักบรรทุกคงที่เพิ่มเติม wD (kN/m)", 0.0, 1e4, 15.0, 1.0)
        wL = st.number_input("น้ำหนักบรรทุกจร wL (kN/m)", 0.0, 1e4, 10.0, 1.0)
        self_wt = st.checkbox("รวมน้ำหนักคานเอง (24 kN/m³)", True)
        load_info = dict(sys=sys, wD_sdl=wD_sdl, wL=wL, self_wt=self_wt)

    st.header("4) เหล็กเสริม")
    bars = list(aci.BAR_SIZES)
    db_t_name = st.selectbox("เหล็กรับแรงดึง (ล่าง)", bars, index=bars.index("DB20"))
    db_c_name = st.selectbox("เหล็กรับแรงอัด/เหล็กยึดปลอก (บน)", bars, index=bars.index("DB16"))
    ds_name = st.selectbox("เหล็กปลอก", bars, index=bars.index("RB9"))
    legs = st.number_input("จำนวนขาเหล็กปลอก", 2, 8, 2, 1)
    mode = st.radio("การเลือกเหล็ก", ["ออกแบบอัตโนมัติ", "กำหนดเอง (ตรวจสอบ)"])
    if mode == "กำหนดเอง (ตรวจสอบ)":
        n_t_user = st.number_input("จำนวนเหล็กล่าง (เส้น)", 2, 60, 4, 1)
        n_c_user = st.number_input("จำนวนเหล็กบน (เส้น)", 2, 60, 2, 1)
        s_user = st.number_input("ระยะเรียงเหล็กปลอก s (mm)", 50.0, 600.0, 200.0, 25.0)
    else:
        n_t_user = n_c_user = s_user = None

db_t = aci.BAR_SIZES[db_t_name]
db_c = aci.BAR_SIZES[db_c_name]
d_s = aci.BAR_SIZES[ds_name]

# ---------------------------------------------------------------------------
# Loads
# ---------------------------------------------------------------------------
d_est = h - cover - d_s - db_t / 2.0
if load_info is None:
    Mu_kNm_design, Vu_kN_design = Mu_kNm, Vu_kN
    load_lines = [f"Mu = {Mu_kNm:.2f} kN·m (ผู้ใช้กำหนด)", f"Vu = {Vu_kN:.2f} kN (ผู้ใช้กำหนด)"]
else:
    w_sw = 24.0 * b * h / 1e6 if load_info["self_wt"] else 0.0
    wD = load_info["wD_sdl"] + w_sw
    wu, combo = aci.factored_line_load(wD, load_info["wL"])
    if load_info["sys"] == "คานช่วงเดียวธรรมดา":
        Mu_kNm_design = wu * span ** 2 / 8.0
        Vu_kN_design = wu * max(span / 2.0 - d_est / 1000.0, 0.0)
        m_txt, v_txt = "wu·L²/8", "wu·(L/2 − d)"
    else:
        Mu_kNm_design = wu * span ** 2 / 2.0
        Vu_kN_design = wu * max(span - d_est / 1000.0, 0.0)
        m_txt, v_txt = "wu·L²/2", "wu·(L − d)"
    load_lines = [
        f"น้ำหนักคานเอง = 24 × {b / 1000:.3f} × {h / 1000:.3f} = {w_sw:.2f} kN/m",
        f"wD = {wD:.2f} kN/m, wL = {load_info['wL']:.2f} kN/m",
        f"wu = max(1.4D, 1.2D + 1.6L) = {wu:.2f} kN/m  [{combo}]  (ACI 5.3.1)",
        f"Mu = {m_txt} = {Mu_kNm_design:.2f} kN·m",
        f"Vu (ที่ระยะ d จากหน้าที่รองรับ, 9.4.3.2) = {v_txt} = {Vu_kN_design:.2f} kN",
    ]

Mu = Mu_kNm_design * 1e6
Vu = Vu_kN_design * 1e3

# ---------------------------------------------------------------------------
# Design
# ---------------------------------------------------------------------------
errors = []
if fy > 550:
    errors.append("fy สำหรับเหล็กรับแรงดัดต้องไม่เกิน 550 MPa (Table 20.2.2.4a)")
if fc < 17:
    errors.append("f'c ต้องไม่น้อยกว่า 17 MPa (Table 19.2.1.1)")
for e in errors:
    st.error(e)

try:
    flex = aci.design_flexure(Mu, b, h, fc, fy, cover, d_s, d_agg, db_t, db_c,
                              n_t=n_t_user, n_c=n_c_user)
except ValueError as exc:
    st.error(f"ไม่สามารถออกแบบได้: {exc}")
    st.stop()

res = flex.result
d = flex.d
shear = aci.shear_design(Vu, b, d, fc, fyt, flex.tension.area, d_s, int(legs), lam, s_user)
h_min = aci.min_thickness(span * 1000.0, support, fy)
s_crack = aci.crack_control_spacing(fy, cover + d_s)
n_bot = flex.tension.layers[0]
s_bot_cc = (b - 2 * cover - 2 * d_s - db_t) / (n_bot - 1) if n_bot > 1 else 0.0

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

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
t_lay = " + ".join(f"{k}" for k in flex.tension.layers)
c_lay = " + ".join(f"{k}" for k in flex.compression.layers)
bot_txt = f"{flex.tension.n}-{db_t_name}" + (f" ({t_lay} ชั้น)" if len(flex.tension.layers) > 1 else "")
top_txt = f"{flex.compression.n}-{db_c_name}" + (f" ({c_lay} ชั้น)" if len(flex.compression.layers) > 1 else "")
stir_txt = f"{ds_name} @ {shear.s_provided:.0f} mm ({legs} ขา)"

if all_ok:
    st.success(f"**{beam_id} {b:.0f}×{h:.0f} mm** — ผ่านทุกข้อกำหนด")
else:
    st.error(f"**{beam_id} {b:.0f}×{h:.0f} mm** — มีรายการไม่ผ่าน กรุณาปรับหน้าตัดหรือเหล็กเสริม")

c1, c2, c3, c4 = st.columns(4)
c1.metric("เหล็กล่าง", bot_txt, f"As = {flex.tension.area:.0f} mm²", delta_color="off")
c2.metric("เหล็กบน", top_txt, f"A's = {flex.compression.area:.0f} mm²", delta_color="off")
c3.metric("เหล็กปลอก", stir_txt, delta_color="off")
c4.metric("อัตราส่วนการใช้งาน", f"M {Mu / res.phi_Mn:.2f} | V {Vu / shear.phi_Vn:.2f}"
          if res.phi_Mn > 0 and shear.phi_Vn > 0 else "-")

tab_sum, tab_flex, tab_shear, tab_sec, tab_sheet = st.tabs(
    ["📋 สรุปผล", "📐 แรงดัด", "✂️ แรงเฉือน", "🧱 หน้าตัด", "📝 รายการคำนวณ"])

with tab_sum:
    st.subheader("แรงออกแบบ")
    for line in load_lines:
        st.write("• " + line)
    st.subheader("ผลการตรวจสอบ")
    st.table({"รายการ": list(checks), "ผล": [ok(v) for v in checks.values()]})
    st.subheader("ความลึกต่ำสุด (Table 9.3.1.1) — ไม่ต้องตรวจสอบการแอ่นตัว")
    if h >= h_min:
        st.info(f"h = {h:.0f} mm ≥ h,min = {h_min:.0f} mm → ไม่ต้องคำนวณการแอ่นตัว")
    else:
        st.warning(f"h = {h:.0f} mm < h,min = {h_min:.0f} mm → ต้องคำนวณการแอ่นตัวตาม 24.2")
    if h > 900:
        st.warning("h > 900 mm → ต้องเสริมเหล็กผิว (skin reinforcement) ตาม 9.7.2.3")

with tab_flex:
    b1 = aci.beta1(fc)
    eps_ty = fy / aci.ES
    st.markdown(f"""
| รายการ | ค่า | อ้างอิง |
|---|---|---|
| β₁ | {b1:.3f} | Table 22.2.2.4.3 |
| d (ถึงศูนย์ถ่วงเหล็กล่าง) | {d:.1f} mm | |
| dt (ถึงเหล็กชั้นนอกสุด) | {flex.dt:.1f} mm | |
| d' (ถึงศูนย์ถ่วงเหล็กบน) | {flex.d_comp:.1f} mm | |
| As,req | {flex.As_req:.0f} mm² | 22.2 |
| A's,req | {flex.Asc_req:.0f} mm² | {"ต้องใช้เหล็กรับแรงอัด" if flex.Asc_req > 0 else "หน้าตัดเสริมเหล็กรับแรงดึงอย่างเดียว"} |
| As,min = max(0.25√f'c, 1.4)·b·d/fy | {flex.As_min:.0f} mm² | 9.6.1.2 |
| As,provided | {flex.tension.area:.0f} mm² | |
| ρ = As/(b·d) | {flex.tension.area / (b * d):.4f} | |
| c (strain compatibility) | {res.c:.1f} mm | 22.2.1 |
| a = β₁c | {res.a:.1f} mm | 22.2.2.4.1 |
| εt | {res.eps_t:.5f} (εty = {eps_ty:.5f}) | |
| การจำแนกหน้าตัด | {res.classification} | Table 21.2.2 |
| φ | {res.phi:.3f} | Table 21.2.2 |
| Mn | {res.Mn / 1e6:.2f} kN·m | |
| **φMn** | **{res.phi_Mn / 1e6:.2f} kN·m** | |
| Mu | {Mu / 1e6:.2f} kN·m | {ok(res.phi_Mn >= Mu)} |
""")
    st.markdown("**แรงและหน่วยแรงในเหล็กเสริมแต่ละชั้น** (+ = อัด, − = ดึง)")
    st.table({
        "ความลึกจากผิวบน (mm)": [f"{s['depth']:.1f}" for s in res.steel],
        "As (mm²)": [f"{s['area']:.0f}" for s in res.steel],
        "ความเครียด ε": [f"{s['strain']:.5f}" for s in res.steel],
        "fs (MPa)": [f"{s['stress']:.1f}" for s in res.steel],
        "แรง (kN)": [f"{s['force'] / 1e3:.1f}" for s in res.steel],
    })
    st.markdown(f"""
**การควบคุมรอยร้าว (24.3.2)**: fs = ⅔fy = {2 / 3 * fy:.0f} MPa, cc = {cover + d_s:.0f} mm
s,max = min[380(280/fs) − 2.5cc, 300(280/fs)] = **{s_crack:.0f} mm**;
ระยะเหล็กล่างชั้นนอก (ศูนย์กลางถึงศูนย์กลาง) = {s_bot_cc:.0f} mm → {ok(s_bot_cc <= s_crack)}

**ระยะช่องว่างระหว่างเหล็ก (25.2.1)**: ต้องการ ≥ max(25, db, 4/3·dagg)
— ล่าง: {flex.tension.clear_spacing:.0f} ≥ {flex.tension.s_clear_min:.0f} mm {ok(flex.checks['spacing_t'])}
— บน: {flex.compression.clear_spacing:.0f} ≥ {flex.compression.s_clear_min:.0f} mm {ok(flex.checks['spacing_c'])}
""")

with tab_shear:
    sqrt_fc = min(math.sqrt(fc), 8.3)
    st.markdown(f"""
| รายการ | ค่า | อ้างอิง |
|---|---|---|
| Vu | {Vu / 1e3:.2f} kN | |
| √f'c (≤ 8.3 MPa) | {sqrt_fc:.2f} MPa | 22.5.3.1 |
| fyt ใช้คำนวณ (≤ 420 MPa) | {min(fyt, 420):.0f} MPa | 20.2.2.4 |
| ρw = As/(bw·d) | {flex.tension.area / (b * d):.4f} | |
| λs = √(2/(1+0.004d)) ≤ 1 | {shear.lambda_s:.3f} | 22.5.5.1.3 |
| Vc | {shear.Vc / 1e3:.2f} kN | Table 22.5.5.1 |
| φVc | {aci.PHI_SHEAR * shear.Vc / 1e3:.2f} kN | φ = 0.75 |
| ต้องใช้ Av,min หรือไม่ (Vu > φ0.083λ√f'c·bw·d) | {"ใช่" if shear.av_min_required else "ไม่ (แต่แนะนำให้ใส่)"} | 9.6.3.1 |
| Av,min/s | {shear.Av_min_s:.4f} mm²/mm | 9.6.3.4 |
| Vs,req = Vu/φ − Vc | {shear.Vs_req / 1e3:.2f} kN | 22.5.8.5.3 |
| Av ({legs} ขา {ds_name}) | {shear.Av:.1f} mm² | |
| s,max | {shear.s_max:.0f} mm | 9.7.6.2.2 |
| s,required | {shear.s_req:.0f} mm | |
| **s,provided** | **{shear.s_provided:.0f} mm** | |
| Vs = Av·fyt·d/s | {shear.Vs / 1e3:.2f} kN | 22.5.8.5.3 |
| **φVn = φ(Vc + Vs)** | **{shear.phi_Vn / 1e3:.2f} kN** | {ok(shear.phi_Vn >= Vu)} |
| φ(Vc + 0.66√f'c·bw·d) | {shear.phi_Vn_max / 1e3:.2f} kN | 22.5.1.2 {ok(Vu <= shear.phi_Vn_max)} |
""")
    for n in shear.notes:
        st.info(n)

with tab_sec:
    fig, ax = plt.subplots(figsize=(4.5, 4.5 * h / b if h / b < 2.5 else 10))
    ax.add_patch(Rectangle((0, 0), b, h, fc="#d9d9d9", ec="black", lw=1.5))
    ax.add_patch(FancyBboxPatch((cover + d_s / 2, cover + d_s / 2), b - 2 * cover - d_s,
                                h - 2 * cover - d_s, boxstyle=f"round,pad=0,rounding_size={2 * d_s}",
                                fill=False, ec="#1f4e79", lw=2))

    def draw(layout, db, from_top: bool, color):
        x0 = cover + d_s + db / 2
        width = b - 2 * (cover + d_s) - db
        for k, y in zip(layout.layers, layout.depths):
            yy = h - y if from_top else y
            xs = [x0 + width / 2] if k == 1 else [x0 + i * width / (k - 1) for i in range(k)]
            for x in xs:
                ax.add_patch(Circle((x, yy), db / 2, fc=color, ec="black"))

    draw(flex.tension, db_t, False, "#c00000")
    draw(flex.compression, db_c, True, "#2e75b6")
    ax.annotate("", (0, -30), (b, -30), arrowprops=dict(arrowstyle="<->"))
    ax.text(b / 2, -60, f"b = {b:.0f}", ha="center", va="top")
    ax.annotate("", (-30, 0), (-30, h), arrowprops=dict(arrowstyle="<->"))
    ax.text(-60, h / 2, f"h = {h:.0f}", ha="right", va="center", rotation=90)
    ax.set_xlim(-150, b + 50)
    ax.set_ylim(-130, h + 50)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"{beam_id}  {b:.0f}×{h:.0f}")
    col_a, col_b = st.columns([1, 1])
    col_a.pyplot(fig)
    col_b.markdown(f"""
**เหล็กบน:** {top_txt}
**เหล็กล่าง:** {bot_txt}
**เหล็กปลอก:** {stir_txt}
**ระยะหุ้ม:** {cover:.0f} mm
**f'c:** {fc:.1f} MPa ({fc / aci.KSC_TO_MPA:.0f} ksc), **fy:** {fy:.0f} MPa, **fyt:** {fyt:.0f} MPa
""")

with tab_sheet:
    sheet = f"""# รายการคำนวณออกแบบคาน {beam_id}
โครงการ: {project}  วันที่: {date.today():%d/%m/%Y}  มาตรฐาน: ACI 318-19

## 1. ข้อมูล
- f'c = {fc:.2f} MPa, fy = {fy:.0f} MPa, fyt = {fyt:.0f} MPa, Es = 200,000 MPa, λ = {lam}
- b × h = {b:.0f} × {h:.0f} mm, ระยะหุ้ม = {cover:.0f} mm, L = {span:.2f} m ({support})

## 2. แรงออกแบบ
""" + "\n".join(f"- {l}" for l in load_lines) + f"""

## 3. ออกแบบรับแรงดัด
- β1 = {aci.beta1(fc):.3f}, d = {d:.1f} mm, dt = {flex.dt:.1f} mm, d' = {flex.d_comp:.1f} mm
- As,req = {flex.As_req:.0f} mm², A's,req = {flex.Asc_req:.0f} mm², As,min = {flex.As_min:.0f} mm²
- ใช้เหล็กล่าง {bot_txt}: As = {flex.tension.area:.0f} mm²; เหล็กบน {top_txt}: A's = {flex.compression.area:.0f} mm²
- c = {res.c:.1f} mm, a = {res.a:.1f} mm, εt = {res.eps_t:.5f} → {res.classification}, φ = {res.phi:.3f}
- φMn = {res.phi:.3f} × {res.Mn / 1e6:.2f} = {res.phi_Mn / 1e6:.2f} kN·m {"≥" if res.phi_Mn >= Mu else "<"} Mu = {Mu / 1e6:.2f} kN·m → {ok(res.phi_Mn >= Mu)}

## 4. ออกแบบรับแรงเฉือน
- Vc = {shear.Vc / 1e3:.2f} kN, φVc = {0.75 * shear.Vc / 1e3:.2f} kN
- Vs,req = {shear.Vs_req / 1e3:.2f} kN, s,max = {shear.s_max:.0f} mm
- ใช้เหล็กปลอก {stir_txt}: Vs = {shear.Vs / 1e3:.2f} kN
- φVn = {shear.phi_Vn / 1e3:.2f} kN {"≥" if shear.phi_Vn >= Vu else "<"} Vu = {Vu / 1e3:.2f} kN → {ok(shear.phi_Vn >= Vu)}

## 5. สรุปการตรวจสอบ
""" + "\n".join(f"- {k}: {ok(v)}" for k, v in checks.items()) + f"""
- ความลึกต่ำสุด h,min = {h_min:.0f} mm (Table 9.3.1.1) → {"ไม่ต้องตรวจการแอ่นตัว" if h >= h_min else "ต้องตรวจการแอ่นตัว"}
"""
    st.markdown(sheet)
    st.download_button("⬇️ ดาวน์โหลดรายการคำนวณ (.md)", sheet, file_name=f"{beam_id}_calc.md")

st.caption("หมายเหตุ: โปรแกรมนี้ใช้เพื่อช่วยคำนวณเบื้องต้น ผู้ออกแบบต้องตรวจสอบผลการคำนวณและรับผิดชอบงานออกแบบด้วยตนเอง "
           "(ไม่รวมการออกแบบรับแรงบิด ระยะฝังยึด/ต่อทาบ และการคำนวณการแอ่นตัว)")
