"""Reinforced concrete beam design per ACI 318-19 (SI units).

Units: mm, MPa (N/mm^2), N, N-mm unless stated otherwise.
All clause references are to ACI 318-19.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

ES = 200_000.0          # 20.2.2.2 modulus of elasticity of reinforcement, MPa
EPS_CU = 0.003          # 22.2.2.1 maximum usable concrete strain
PHI_SHEAR = 0.75        # Table 21.2.1(b)
KSC_TO_MPA = 0.0980665

# Nominal bar diameters (mm) common in Thailand (TIS 20 / TIS 24)
BAR_SIZES = {
    "RB6": 6, "RB9": 9, "DB10": 10, "DB12": 12, "DB16": 16, "DB20": 20,
    "DB25": 25, "DB28": 28, "DB32": 32, "DB36": 36, "DB40": 40,
}

STEEL_GRADES = {
    "SR24 (fy = 235 MPa)": 235.0,
    "SD30 (fy = 295 MPa)": 295.0,
    "SD40 (fy = 390 MPa)": 390.0,
    "SD50 (fy = 490 MPa)": 490.0,
    "ASTM A615 Gr.60 (fy = 420 MPa)": 420.0,
}


@dataclass(frozen=True)
class Coefficients:
    """Code coefficients, expressed for SI calculation (MPa, mm).

    Square-root terms are the c in c·√f'c[MPa]; stress terms are in MPa.
    `mks` holds the same coefficients as displayed for f'c, fy in ksc.
    """
    name: str
    vc: float = 0.17             # Table 22.5.5.1(a)
    vc_rho: float = 0.66         # Table 22.5.5.1(b), (c)
    vc_max: float = 0.42         # 22.5.5.1.1
    vs_max: float = 0.66         # 22.5.1.2
    av_trig: float = 0.083       # 9.6.3.1
    avmin1: float = 0.062        # 9.6.3.4(a)
    avmin2: float = 0.35         # 9.6.3.4(b), MPa
    smax_vs: float = 0.33        # 9.7.6.2.2
    sqrt_fc_max: float = 8.3     # 22.5.3.1, √MPa
    fyt_max: float = 420.0       # Table 20.2.2.4a, MPa
    asmin1: float = 0.25         # 9.6.1.2(a)
    asmin2: float = 1.4          # 9.6.1.2(b), MPa
    fs_ref: float = 280.0        # 24.3.2, MPa
    hmin_fy: float = 700.0       # Table 9.3.1.1.1, MPa
    mks: dict = field(default_factory=dict, compare=False)


def _mks_display(c: "Coefficients") -> dict:
    k = math.sqrt(KSC_TO_MPA)                 # c_mks = c_si / k for √f'c terms
    out = {f: getattr(c, f) / k for f in
           ("vc", "vc_rho", "vc_max", "vs_max", "av_trig", "avmin1", "smax_vs", "asmin1",
            "sqrt_fc_max")}
    out.update({f: getattr(c, f) / KSC_TO_MPA for f in ("avmin2", "fyt_max", "asmin2",
                                                         "fs_ref", "hmin_fy")})
    return out


def _from_mks(name: str, **mks: float) -> Coefficients:
    """Build SI coefficients that reproduce the given (rounded) MKS equations exactly."""
    k = math.sqrt(KSC_TO_MPA)
    si = {f: v * k for f, v in mks.items()
          if f in ("vc", "vc_rho", "vc_max", "vs_max", "av_trig", "avmin1", "smax_vs",
                   "asmin1", "sqrt_fc_max")}
    si.update({f: v * KSC_TO_MPA for f, v in mks.items()
               if f in ("avmin2", "fyt_max", "asmin2", "fs_ref", "hmin_fy")})
    return Coefficients(name=name, mks=dict(mks), **si)


_aci = Coefficients(name="ACI 318-19 (แปลงหน่วยตรงจาก SI)")
ACI_SI = replace(_aci, mks=_mks_display(_aci))

# Rounded kg-cm coefficients as used by the Engineering Institute of Thailand (วสท.)
EIT = _from_mks(
    "วสท. (ค่าปัดหน่วย kg-cm)",
    vc=0.53, vc_rho=2.1, vc_max=1.33, vs_max=2.1, av_trig=0.27, avmin1=0.2,
    avmin2=3.5, smax_vs=1.1, sqrt_fc_max=26.5, fyt_max=4200.0, asmin1=0.8,
    asmin2=14.0, fs_ref=2800.0, hmin_fy=7000.0,
)


def bar_area(db: float) -> float:
    return math.pi * db ** 2 / 4.0


# ---------------------------------------------------------------------------
# Material / strength-reduction factors
# ---------------------------------------------------------------------------
def beta1(fc: float) -> float:
    """Table 22.2.2.4.3."""
    if fc <= 28.0:
        return 0.85
    if fc >= 55.0:
        return 0.65
    return 0.85 - 0.05 * (fc - 28.0) / 7.0


def phi_flexure(eps_t: float, fy: float) -> float:
    """Table 21.2.2 for deformed reinforcement, other (non-spiral) transverse reinforcement."""
    eps_ty = fy / ES
    if eps_t >= eps_ty + 0.003:
        return 0.90
    if eps_t <= eps_ty:
        return 0.65
    return 0.65 + 0.25 * (eps_t - eps_ty) / 0.003


def section_class(eps_t: float, fy: float) -> str:
    eps_ty = fy / ES
    if eps_t >= eps_ty + 0.003:
        return "Tension-controlled"
    if eps_t <= eps_ty:
        return "Compression-controlled"
    return "Transition"


def as_min_flexure(fc: float, fy: float, bw: float, d: float,
                   k: Coefficients = ACI_SI) -> float:
    """9.6.1.2."""
    return max(k.asmin1 * math.sqrt(fc) / fy, k.asmin2 / fy) * bw * d


def min_thickness(span: float, support: str, fy: float, k: Coefficients = ACI_SI) -> float:
    """Table 9.3.1.1 (normalweight concrete), with 9.3.1.1.1 modification for fy != 420."""
    divisor = {
        "Simply supported": 16.0,
        "One end continuous": 18.5,
        "Both ends continuous": 21.0,
        "Cantilever": 8.0,
    }[support]
    return span / divisor * (0.4 + fy / k.hmin_fy)


# ---------------------------------------------------------------------------
# Bar arrangement
# ---------------------------------------------------------------------------
@dataclass
class BarLayout:
    n: int
    db: float
    layers: list[int]            # bars per layer, layer 0 nearest the face
    depths: list[float]          # depth of each layer centroid measured from the *same* face
    clear_spacing: float         # clear spacing between bars in the fullest layer
    s_clear_min: float

    @property
    def area(self) -> float:
        return self.n * bar_area(self.db)

    @property
    def centroid(self) -> float:
        return sum(k * y for k, y in zip(self.layers, self.depths)) / self.n


def min_clear_spacing(db: float, d_agg: float) -> float:
    """25.2.1: max(25 mm, db, 4/3 d_agg)."""
    return max(25.0, db, 4.0 / 3.0 * d_agg)


def arrange_bars(n: int, db: float, b: float, cover: float, d_stirrup: float,
                 d_agg: float) -> BarLayout:
    """Place n bars in as few layers as possible.

    Depths are measured from the face nearest to the bars (cover face).
    Clear vertical spacing between layers = max(25 mm, db) per 25.2.2.
    """
    s_min = min_clear_spacing(db, d_agg)
    width = b - 2.0 * cover - 2.0 * d_stirrup
    per_layer = max(int((width - db) // (db + s_min)) + 1, 1)
    layers: list[int] = []
    remaining = n
    while remaining > 0:
        k = min(per_layer, remaining)
        layers.append(k)
        remaining -= k
    y0 = cover + d_stirrup + db / 2.0
    v_gap = max(25.0, db) + db
    depths = [y0 + i * v_gap for i in range(len(layers))]
    k_max = max(layers)
    clear = (width - k_max * db) / (k_max - 1) if k_max > 1 else width - db
    return BarLayout(n=n, db=db, layers=layers, depths=depths, clear_spacing=clear,
                     s_clear_min=s_min)


# ---------------------------------------------------------------------------
# Flexural analysis by strain compatibility (22.2)
# ---------------------------------------------------------------------------
@dataclass
class FlexureResult:
    c: float
    a: float
    eps_t: float
    phi: float
    Mn: float               # N-mm
    phi_Mn: float           # N-mm
    classification: str
    steel: list[dict] = field(default_factory=list)


def analyze_flexure(b: float, h: float, fc: float, fy: float,
                    steel: list[tuple[float, float]], dt: float) -> FlexureResult:
    """Nominal moment of a rectangular section.

    steel: list of (area mm^2, depth from compression face mm), every layer.
    dt: depth of the extreme tension layer.
    """
    b1 = beta1(fc)

    def forces(c: float):
        a = min(b1 * c, h)
        cc = 0.85 * fc * a * b
        items = [("concrete", cc, a / 2.0)]
        layers = []
        for area, y in steel:
            eps = EPS_CU * (c - y) / c                       # + compression
            fs = max(-fy, min(fy, ES * eps))
            f_net = fs - (0.85 * fc if (fs > 0 and y < a) else 0.0)   # displaced concrete
            force = area * f_net
            items.append(("steel", force, y))
            layers.append({"area": area, "depth": y, "strain": eps, "stress": fs, "force": force})
        return items, layers, a

    def net(c: float) -> float:
        return sum(f for _, f, _ in forces(c)[0])

    lo, hi = 1e-6, 5.0 * h
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if net(mid) > 0:
            hi = mid
        else:
            lo = mid
    c = 0.5 * (lo + hi)
    items, layers, a = forces(c)
    # moment about the top fibre; with sum(F) = 0 this equals the internal couple
    Mn = -sum(f * y for _, f, y in items)
    eps_t = EPS_CU * (dt - c) / c
    phi = phi_flexure(eps_t, fy)
    return FlexureResult(c=c, a=a, eps_t=eps_t, phi=phi, Mn=Mn, phi_Mn=phi * Mn,
                         classification=section_class(eps_t, fy), steel=layers)


def required_steel(Mu: float, b: float, d: float, d_comp: float, fc: float, fy: float):
    """Closed-form required reinforcement (rectangular stress block).

    Returns (As_req, As'_req). Singly reinforced if the section can stay
    tension-controlled (eps_t >= eps_ty + 0.003); otherwise compression steel
    is added keeping c at the tension-controlled limit.
    """
    phi = 0.90
    b1 = beta1(fc)
    eps_ty = fy / ES
    c_tc = EPS_CU / (EPS_CU + eps_ty + 0.003) * d
    a_tc = b1 * c_tc
    Mn_tc = 0.85 * fc * a_tc * b * (d - a_tc / 2.0)
    Mn_req = Mu / phi
    if Mn_req <= Mn_tc:
        Rn = Mn_req / (b * d ** 2)
        rho = 0.85 * fc / fy * (1.0 - math.sqrt(max(0.0, 1.0 - 2.0 * Rn / (0.85 * fc))))
        return rho * b * d, 0.0
    As1 = 0.85 * fc * a_tc * b / fy
    M2 = Mn_req - Mn_tc
    eps_sc = EPS_CU * (c_tc - d_comp) / c_tc
    fsc = min(fy, ES * eps_sc)
    if fsc - 0.85 * fc <= 0:
        raise ValueError("Compression steel ineffective (too close to neutral axis); increase section depth.")
    As_c = M2 / ((fsc - 0.85 * fc) * (d - d_comp))
    As2 = As_c * (fsc - 0.85 * fc) / fy
    return As1 + As2, As_c


def crack_control_spacing(fy: float, cc: float, k: Coefficients = ACI_SI) -> float:
    """24.3.2: s <= 380(280/fs) - 2.5cc <= 300(280/fs), fs = 2/3 fy."""
    fs = 2.0 / 3.0 * fy
    return min(380.0 * k.fs_ref / fs - 2.5 * cc, 300.0 * k.fs_ref / fs)


# ---------------------------------------------------------------------------
# Shear (22.5, 9.6.3, 9.7.6.2)
# ---------------------------------------------------------------------------
@dataclass
class ShearResult:
    Vc: float
    Vs_req: float
    Av: float
    Av_min_s: float          # Av,min / s  (mm^2/mm)
    s_req: float             # spacing required for strength (inf if none)
    s_max: float
    s_provided: float
    Vs: float
    phi_Vn: float
    phi_Vn_max: float        # 22.5.1.2 upper limit on section
    av_min_required: bool
    lambda_s: float
    notes: list[str] = field(default_factory=list)


def shear_design(Vu: float, bw: float, d: float, fc: float, fyt: float, As: float,
                 d_stirrup: float, legs: int, lam: float = 1.0,
                 s_user: float | None = None, k: Coefficients = ACI_SI) -> ShearResult:
    notes = []
    sqrt_fc = min(math.sqrt(fc), k.sqrt_fc_max)            # 22.5.3.1
    fyt_eff = min(fyt, k.fyt_max)                          # 20.2.2.4
    if fyt > k.fyt_max:
        notes.append(f"fyt limited to {k.fyt_max:.0f} MPa (Table 20.2.2.4a)")
    Av = legs * bar_area(d_stirrup)
    Av_min_s = max(k.avmin1 * sqrt_fc, k.avmin2) * bw / fyt_eff  # 9.6.3.4
    rho_w = As / (bw * d)
    lam_s = min(1.0, math.sqrt(2.0 / (1.0 + 0.004 * d)))  # 22.5.5.1.3

    Vc_max = k.vc_max * lam * sqrt_fc * bw * d                  # 22.5.5.1.1
    # Table 22.5.5.1 (Nu = 0)
    Vc_a = k.vc * lam * sqrt_fc * bw * d
    Vc_b = k.vc_rho * lam * rho_w ** (1.0 / 3.0) * sqrt_fc * bw * d
    Vc_c = k.vc_rho * lam_s * lam * rho_w ** (1.0 / 3.0) * sqrt_fc * bw * d
    Vc_with_min = min(max(Vc_a, Vc_b), Vc_max)
    Vc_without = min(Vc_c, Vc_max)

    # 9.6.3.1: Av,min required where Vu > phi 0.083 lambda sqrt(fc') bw d
    av_min_required = Vu > PHI_SHEAR * k.av_trig * lam * sqrt_fc * bw * d

    Vs_lim_sec = k.vs_max * sqrt_fc * bw * d                    # 22.5.1.2
    Vc = Vc_with_min   # stirrups at least Av,min are always provided in this design
    phi_Vn_max = PHI_SHEAR * (Vc + Vs_lim_sec)

    Vs_req = max(0.0, Vu / PHI_SHEAR - Vc)
    s_strength = Av * fyt_eff * d / Vs_req if Vs_req > 0 else math.inf
    s_avmin = Av / Av_min_s
    # 9.7.6.2.2 maximum spacing
    if Vs_req <= k.smax_vs * sqrt_fc * bw * d:
        s_max = min(d / 2.0, 600.0)
    else:
        s_max = min(d / 4.0, 300.0)
        notes.append("Vs > smax_vs·√fc'·bw·d → s,max halved (9.7.6.2.2)")
    s_req = min(s_strength, s_avmin, s_max)
    if s_user is not None and s_user > 0:
        s_prov = s_user
    else:
        s_prov = max(25.0 * math.floor(s_req / 25.0), 50.0)

    if s_prov > s_avmin + 1e-9:
        Vc = Vc_without
        notes.append("Provided Av < Av,min → Vc per Table 22.5.5.1(c) with size effect λs")
    Vs = Av * fyt_eff * d / s_prov
    Vs = min(Vs, Vs_lim_sec)
    phi_Vn = PHI_SHEAR * (Vc + Vs)
    return ShearResult(Vc=Vc, Vs_req=Vs_req, Av=Av, Av_min_s=Av_min_s, s_req=s_req,
                       s_max=s_max, s_provided=s_prov, Vs=Vs, phi_Vn=phi_Vn,
                       phi_Vn_max=phi_Vn_max, av_min_required=av_min_required,
                       lambda_s=lam_s, notes=notes)


# ---------------------------------------------------------------------------
# Loads
# ---------------------------------------------------------------------------
def factored_line_load(wD: float, wL: float) -> tuple[float, str]:
    """5.3.1 Eq. (5.3.1a) and (5.3.1b), governing combination."""
    w1 = 1.4 * wD
    w2 = 1.2 * wD + 1.6 * wL
    return (w1, "1.4D") if w1 >= w2 else (w2, "1.2D + 1.6L")


# ---------------------------------------------------------------------------
# Complete flexural design / check
# ---------------------------------------------------------------------------
@dataclass
class FlexureDesign:
    tension: BarLayout
    compression: BarLayout
    d: float
    dt: float
    d_comp: float
    As_req: float
    Asc_req: float
    As_min: float
    result: FlexureResult
    checks: dict[str, bool]


def _check_flexure(Mu, b, h, fc, fy, cover, d_stirrup, d_agg, n_t, db_t, n_c, db_c,
                   As_req, Asc_req, k: Coefficients = ACI_SI) -> FlexureDesign:
    tens = arrange_bars(n_t, db_t, b, cover, d_stirrup, d_agg)
    comp = arrange_bars(n_c, db_c, b, cover, d_stirrup, d_agg)
    d = h - tens.centroid
    dt = h - tens.depths[0]
    steel = [(k * bar_area(db_c), y) for k, y in zip(comp.layers, comp.depths)]
    steel += [(k * bar_area(db_t), h - y) for k, y in zip(tens.layers, tens.depths)]
    res = analyze_flexure(b, h, fc, fy, steel, dt)
    As_min = as_min_flexure(fc, fy, b, d, k)
    checks = {
        "strength": res.phi_Mn >= Mu,
        # 9.6.1.3: As,min need not be satisfied if As,prov >= 4/3 As,req
        "as_min": tens.area >= As_min or tens.area >= 4.0 / 3.0 * As_req,
        "eps_t": res.eps_t >= 0.004,                          # 9.3.3.1
        "spacing_t": tens.clear_spacing >= tens.s_clear_min - 1e-9,
        "spacing_c": comp.clear_spacing >= comp.s_clear_min - 1e-9,
        "fit": d > 0.5 * h,
        # practical detailing: at most 3 tension layers and 2 compression layers
        "layers": len(tens.layers) <= 3 and len(comp.layers) <= 2,
    }
    return FlexureDesign(tension=tens, compression=comp, d=d, dt=dt,
                         d_comp=comp.centroid, As_req=As_req, Asc_req=Asc_req,
                         As_min=As_min, result=res, checks=checks)


def design_flexure(Mu: float, b: float, h: float, fc: float, fy: float, cover: float,
                   d_stirrup: float, d_agg: float, db_t: float, db_c: float,
                   n_hanger: int = 2, n_t: int | None = None,
                   n_c: int | None = None, k: Coefficients = ACI_SI) -> FlexureDesign:
    """Select (or check, if n_t/n_c given) longitudinal bars for factored moment Mu (N-mm)."""
    d0 = h - cover - d_stirrup - db_t / 2.0
    dc0 = cover + d_stirrup + db_c / 2.0
    As_req, Asc_req = required_steel(Mu, b, d0, dc0, fc, fy)
    manual = n_t is not None and n_c is not None
    if manual:
        return _check_flexure(Mu, b, h, fc, fy, cover, d_stirrup, d_agg, n_t, db_t,
                              n_c, db_c, As_req, Asc_req, k)

    As_min0 = as_min_flexure(fc, fy, b, d0, k)
    As_target = max(As_req, min(As_min0, 4.0 / 3.0 * As_req))
    nt = max(2, math.ceil(As_target / bar_area(db_t)))
    nc = max(n_hanger, math.ceil(Asc_req / bar_area(db_c)) if Asc_req > 0 else 0, 2)
    best = None
    for _ in range(100):
        best = _check_flexure(Mu, b, h, fc, fy, cover, d_stirrup, d_agg, nt, db_t,
                              nc, db_c, As_req, Asc_req, k)
        ck = best.checks
        if ck["strength"] and ck["as_min"] and ck["eps_t"]:
            break
        if not ck["eps_t"]:
            nc += 1
        else:
            nt += 1
        if not (ck["fit"] and ck["layers"]):
            break
    return best
