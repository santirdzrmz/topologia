"""
simulate_topodata.py

Python port of `simulate_topodata.R`. Generates the fictitious "Maestro"
(vendor master) and "Pagos" (payments) tables with embedded structure for
topological / descriptive analysis demos (clusters, a latent "size"
manifold, periodic payment cadences -> loops, outliers, structured
missingness and referential integrity between tables).

Random draws go through `r_rng.RRandom`, a port of R's RNG, so with the same
seed the output matches the R script's CSVs. The order of random draws
below mirrors the R code line by line; do not reorder.

Usage:  python simulate_topodata.py [out_dir]
"""
import csv
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from r_rng import RRandom

SEED = 8347
N_VENDORS = 400
DATE_RANGE = (date(2023, 1, 1), date(2025, 12, 31))
OUT_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "simulated_data")
OUTLIER_PAYMENT_FRAC = 0.015

rng = RRandom(SEED)

# --------------------------------------------------------------------------
# 1. Vendor archetypes (clusters)
# --------------------------------------------------------------------------
NA = None
ARCHETYPE_COLS = ["tipo_proveedor", "weight", "size_mean_log", "size_sd_log",
                  "terminos_dias", "ciclo_dias", "ciclo_jitter",
                  "n_pagos_mean", "metodo_pago", "moneda"]
ARCHETYPES = [
    ("COMERCIALIZADORES", 0.30, 10.8, 0.45, 45, 30, 4, 10, "TRANSFER", "MXN"),
    ("SERVICIOS", 0.28, 9.3, 0.55, 30, 14, 2, 16, "TRANSFER", "MXN"),
    ("TRANSPORTISTAS", 0.20, 10.3, 0.45, 15, 7, 1.5, 26, "TRANSFER", "MXN"),
    ("IMPORTADORES", 0.19, 12.3, 0.60, 75, 90, 10, 6, "TRANSFER", "USD"),
    ("OUTLIER", 0.03, 12.8, 1.30, 20, NA, NA, 5, "CHEQUE", "MXN"),
]
ARCHETYPES = [dict(zip(ARCHETYPE_COLS, a)) for a in ARCHETYPES]

SITES = [
    ("20MTY - PL_MONTERREY_CCO_UO", "20MTY", "NUEVO LEON"),
    ("27MTY - PL_MONTERREY_CEDIS_UO", "27MTY", "NUEVO LEON"),
    ("30GDL - PL_GUADALAJARA_CCO_UO", "30GDL", "JALISCO"),
    ("10CDMX - PL_CDMX_CCO_UO", "10CDMX", "CIUDAD DE MEXICO"),
    ("40QRO - PL_QUERETARO_CCO_UO", "40QRO", "QUERETARO"),
    ("50TIJ - PL_TIJUANA_CCO_UO", "50TIJ", "BAJA CALIFORNIA"),
]
SITE_COLS = ["unidad_operativa", "site", "estado"]
SITES = [dict(zip(SITE_COLS, s)) for s in SITES]

WORD_ROOT = ["EJEMPLO", "FICTICIA", "DEMO", "MODELO", "PRUEBA", "SIMULADA",
             "GENERICA", "REFERENCIA"]
WORD_THEME = ["DEL NORTE", "DE OCCIDENTE", "INDUSTRIAL", "LOGISTICA",
              "COMERCIAL", "NACIONAL", "INTEGRAL", "DEL BAJIO"]
LEGAL_SUF = ["S.A. DE C.V.", "S. DE R.L. DE C.V."]
NAME_PREFIX = ["COMERCIALIZADORA", "SOLUCIONES", "TRANSPORTES", "IMPORTADORA",
               "PROVEEDORA"]
GRUPO_PAGO = {"COMERCIALIZADORES": "SERVICIOS-GENERALES",
              "SERVICIOS": "SERVICIOS-GENERALES",
              "TRANSPORTISTAS": "LOGISTICA-NACIONAL",
              "IMPORTADORES": "PROVEEDORES-IMPORTACION",
              "OUTLIER": "SIN-CLASIFICAR"}
LETTERS = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
ALNUM = LETTERS + [str(i) for i in range(10)]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def irange(a, b):
    """R's a:b for integers."""
    return range(a, b + 1)


def smp(x, size=None, replace=False, prob=None):
    # keep ranges lazy: some populations (1e11:1e12) are far too big to list
    x = x if isinstance(x, range) else list(x)
    return rng.sample(x, size, replace, prob)


def rand_rfc(n):
    letters4 = ["".join(smp(LETTERS, 4)) for _ in range(n)]
    digits6 = ["%06d" % d for d in smp(irange(10000, 999999), n)]
    alnum3 = ["".join(smp(ALNUM, 3)) for _ in range(n)]
    return [a + b + c for a, b, c in zip(letters4, digits6, alnum3)]


def date_str(d):
    return "%02d-%s-%02d" % (d.day, MONTHS[d.month - 1], d.year % 100)


def slash_date(d):
    return "%02d/%02d/%02d" % (d.day, d.month, d.year % 100)


def fmt_money(x):
    return " $%s " % format(x, ",.2f")


def r_round(x, digits=0):
    return round(x, digits)


def runif_lt(n, p):
    return [u < p for u in rng.runif(n)]


def uuid_like():
    parts = [("".join(smp(ALNUM, k))) for k in (8, 4, 4, 4, 12)]
    return "-".join(parts)


# --------------------------------------------------------------------------
# 2. Simulate vendors (Maestro)
# --------------------------------------------------------------------------
N = N_VENDORS
cluster_idx = rng.sample_int(len(ARCHETYPES), N, True,
                             [a["weight"] for a in ARCHETYPES])
arche = [ARCHETYPES[i - 1] for i in cluster_idx]
site_idx = rng.sample_int(len(SITES), N, True)
site_info = [SITES[i - 1] for i in site_idx]

log_size = rng.rnorm(N, [a["size_mean_log"] for a in arche],
                     [a["size_sd_log"] for a in arche])
size_factor = [math.exp(v) for v in log_size]

# scale(): R sums sequentially (numpy's pairwise sum can differ in the last bit)
def _seqsum(xs):
    t = 0.0
    for x in xs:
        t += x
    return t


_mean = _seqsum(log_size) / N
_c = [v - _mean for v in log_size]
_sd = math.sqrt(_seqsum([c * c for c in _c]) / (N - 1))
_scaled = [c / _sd for c in _c]
_z = rng.rnorm(N, 0.0, 1.0)
risk_score = [1.0 / (1.0 + math.exp(-(z - 0.4 * s))) for z, s in zip(_z, _scaled)]

vendor_id = smp(irange(5000, 99999), N)
bank_account = [str(v).zfill(18)
                for v in smp(range(10 ** 11, 10 ** 12), N)]
creacion = [DATE_RANGE[0] - timedelta(days=d)
            for d in smp(irange(30, 2500), N, True)]
actualiza = [c + timedelta(days=d) for c, d in zip(creacion,
                                                    smp(irange(30, 900), N, True))]

nombre = [
    "%s %s DE %s, %s" % (NAME_PREFIX[cluster_idx[i] - 1], r, t, l)
    for i, (r, t, l) in enumerate(zip(smp(WORD_ROOT, N, True),
                                      smp(WORD_THEME, N, True),
                                      smp(LEGAL_SUF, N, True)))
]
rfc = rand_rfc(N)
cabecera = ["%d Usuario Demo" % v for v in smp(irange(100000, 999999), N)]
site_id_prov = smp(irange(300000, 900000), N)
fa = smp(["Si", "No"], N, True, [0.85, 0.15])
actualiza_str = [date_str(d) for d in actualiza]
sucursales = ["%d Perfil Prueba" % v for v in smp(irange(1000000, 9999999), N)]
calculo_imp = smp(["Y", "N"], N, True, [0.6, 0.4])
imp_incl = smp(["Y", "N"], N, True, [0.5, 0.5])
aplica_ret = smp(["Y", "N"], N, True, [0.2, 0.8])
dir_a = smp(WORD_ROOT, N, True)
dir_b = smp(irange(100, 9999), N, True)
dir_c = smp(irange(1, 50), N, True)
dir_d = smp(WORD_ROOT, N, True)
direccion = [
    "AV %s %d INT %d COLONIA %s %s %s" % (
        dir_a[i], dir_b[i], dir_c[i], dir_d[i],
        site_info[i]["site"].lstrip("0123456789"), site_info[i]["estado"])
    for i in range(N)
]

# type 7 quantile (R default)
_sf_sorted = np.sort(np.array(size_factor))
_h = (N - 1) * 0.35
_lo = int(math.floor(_h))
q35 = _sf_sorted[_lo] + (_h - _lo) * (_sf_sorted[_lo + 1] - _sf_sorted[_lo])

maestro_cols = [
    "Unidad Operativa", "Id Proveedor", "Tipo Proveedor", "Nombre Proveedor",
    "RFC", "Registro Impositivo", "Fecha Creacion Prov",
    "Actualizacion Provedor", "Cabecera Actualizada Por",
    "Fecha Proveedor Inactivo", "Parent Vendor Id", "Fuente Abasto Padre",
    "Site Id Proveedor", "Site", "FA", "Fuente Abasto", "Fecha Site Inactivo",
    "Actualizacion Site", "Sucrusales Actualizadas por", "Metodo de Pago",
    "Terminos Pago", "Grupo Pago", "Calculo Impuesto", "Impuesto",
    "Impuesto Incluidos", "Aplica Grupo Retencion", "Grupo Retencion",
    "Correo", "Direccion", "Pais", "Telefono", "Banco", "Prioridad Cuenta",
    "Cuenta", "Inactivacion Cuenta", "Actualizacion Cuenta",
    "Referencia Bancaria", "Referencia Adicional", "Cuenta Pasivo",
    "Cuenta Anticipo", "Estatus Fe", "Pago Independiente", "Resico",
    "Sucursal Compra", "Sucursal Pago",
]

maestro = []
for i in range(N):
    a = arche[i]
    maestro.append({
        "Unidad Operativa": site_info[i]["unidad_operativa"],
        "Id Proveedor": vendor_id[i],
        "Tipo Proveedor": a["tipo_proveedor"],
        "Nombre Proveedor": nombre[i],
        "RFC": rfc[i],
        "Registro Impositivo": rfc[i] + ".",
        "Fecha Creacion Prov": date_str(creacion[i]),
        "Actualizacion Provedor": actualiza_str[i],
        "Cabecera Actualizada Por": cabecera[i],
        "Fecha Proveedor Inactivo": NA,
        "Parent Vendor Id": NA,
        "Fuente Abasto Padre": NA,
        "Site Id Proveedor": site_id_prov[i],
        "Site": site_info[i]["site"],
        "FA": fa[i],
        "Fuente Abasto": NA,
        "Fecha Site Inactivo": NA,
        "Actualizacion Site": actualiza_str[i],
        "Sucrusales Actualizadas por": sucursales[i],
        "Metodo de Pago": a["metodo_pago"],
        "Terminos Pago": "%d dias" % a["terminos_dias"],
        "Grupo Pago": GRUPO_PAGO[a["tipo_proveedor"]],
        "Calculo Impuesto": calculo_imp[i],
        "Impuesto": "TASA-0%IVA" if a["moneda"] == "USD" else "TASA-16%IVA",
        "Impuesto Incluidos": imp_incl[i],
        "Aplica Grupo Retencion": aplica_ret[i],
        "Grupo Retencion": NA,
        "Correo": NA,
        "Direccion": direccion[i],
        "Pais": "MX",
        "Telefono": NA,
        "Banco": NA,
        "Prioridad Cuenta": NA,
        "Cuenta": bank_account[i],
        "Inactivacion Cuenta": NA,
        "Actualizacion Cuenta": NA,
        "Referencia Bancaria": NA,
        "Referencia Adicional": NA,
        "Cuenta Pasivo": NA,
        "Cuenta Anticipo": NA,
        "Estatus Fe": "Validado",
        "Pago Independiente": NA,
        "Resico": "Y" if size_factor[i] < q35 else "N",
        "Sucursal Compra": "Y",
        "Sucursal Pago": "N",
    })

# latent factors kept for payment simulation + diagnostics
vendor_latent = [{
    "Id Proveedor": vendor_id[i],
    "tipo_proveedor": arche[i]["tipo_proveedor"],
    "site": site_info[i]["site"],
    "size_factor": size_factor[i],
    "risk_score": risk_score[i],
    "terminos_dias": arche[i]["terminos_dias"],
    "ciclo_dias": arche[i]["ciclo_dias"],
    "ciclo_jitter": arche[i]["ciclo_jitter"],
    "n_pagos_mean": arche[i]["n_pagos_mean"],
    "moneda": arche[i]["moneda"],
    "bank_account": bank_account[i],
    "nombre": nombre[i],
} for i in range(N)]

# --------------------------------------------------------------------------
# 3. Simulate payments (Pagos) -- periodic cadence per vendor (-> loops)
# --------------------------------------------------------------------------
def simulate_vendor_payments(v):
    n_pagos = max(1, int(rng.rpois1(v["n_pagos_mean"])))
    d0, d1 = DATE_RANGE
    span = (d1 - d0).days

    if v["ciclo_dias"] is None:
        # OUTLIER archetype: irregular timing, no periodicity
        offs = sorted(smp(irange(0, span), n_pagos))
        fechas = sorted(d0 + timedelta(days=o) for o in offs)
    else:
        start = d0 + timedelta(days=smp(irange(0, v["ciclo_dias"]), 1)[0])
        noise = rng.rnorm(n_pagos, 0.0, v["ciclo_jitter"])
        fechas = [start + timedelta(days=int(round(k * v["ciclo_dias"] + e)))
                  for k, e in enumerate(noise)]
        fechas = [f for f in fechas if d0 <= f <= d1]
        if not fechas:
            fechas = [d0 + timedelta(days=smp(irange(1, 30), 1)[0])]

    n = len(fechas)
    sf = v["size_factor"]
    phase = math.fmod(sf, 2 * math.pi)
    seasonal = [1 + 0.15 * math.sin(2 * math.pi * f.timetuple().tm_yday / 365 + phase)
                for f in fechas]
    ln = rng.rlnorm(n, 0.0, 0.25)
    importe = [sf * s * l for s, l in zip(seasonal, ln)]

    fac_off = smp(irange(0, 3), n, True)
    ven_off = smp(irange(0, 2), n, True)
    return {
        "FECHA_D_PAGO": fechas,
        "VENDOR_ID": [v["Id Proveedor"]] * n,
        "SITE": [v["site"]] * n,
        "VENDOR_NAME": [v["nombre"]] * n,
        "FECHA_FACTURA": [f - timedelta(days=v["terminos_dias"] + o)
                          for f, o in zip(fechas, fac_off)],
        "FECHA_VENCIMIENTO": [f - timedelta(days=o) for f, o in zip(fechas, ven_off)],
        "IMPORTE_AP": [round(x, 2) for x in importe],
        "moneda": [v["moneda"]] * n,
        "bank_account": [v["bank_account"]] * n,
    }


raw = [simulate_vendor_payments(v) for v in vendor_latent]
P = {k: [x for r in raw for x in r[k]] for k in raw[0]}
n_pay = len(P["VENDOR_ID"])
site = P["SITE"]
imp = P["IMPORTE_AP"]
moneda = P["moneda"]
bank = P["bank_account"]


def ri(a, b, n):
    return smp(irange(a, b), n, True)


P["TIPO"] = ["CENTRO"] * n_pay
P["INVOICE_ID"] = ri(10000000, 99999999, n_pay)
_a, _b = ri(10, 99, n_pay), ri(1000, 9999, n_pay)
P["SEGMENT4"] = ["%dMX%d" % (x, y) for x, y in zip(_a, _b)]
_a, _b = ri(100000, 999999, n_pay), ri(1, 9, n_pay)
P["SEGMENT1"] = ["%s%dA%d" % (b[:3], x, y) for b, x, y in zip(bank, _a, _b)]

_flag = runif_lt(n_pay, 0.3)
_val = ri(1000000000, 9999999999, n_pay)
P["ATTRIBUTE1"] = [str(v) if f else None for f, v in zip(_flag, _val)]
P["REFERENCIA"] = [None] * n_pay

_flag = runif_lt(n_pay, 0.5)
_a, _b, _c = ri(1, 9, n_pay), ri(100, 999, n_pay), ri(20, 25, n_pay)
_true = ["%dABC%d/%sMTY%02d" % (a, b, s, c) for a, b, s, c in zip(_a, _b, site, _c)]
_false = [uuid_like() for _ in range(n_pay)]
P["NUM_FACTURA"] = [t if f else u for f, t, u in zip(_flag, _true, _false)]

P["PAGADO"] = [fmt_money(x) for x in imp]
_tc = rng.runif(n_pay, 17, 19)  # drawn after PAGO_MX in R, but PAGO_MX uses no RNG
P["PAGO_MX"] = [fmt_money(x * 18.5) if m == "USD" else None
                for x, m in zip(imp, moneda)]
P["TIPO_CAMBIO"] = [round(t, 4) if m == "USD" else None for t, m in zip(_tc, moneda)]
P["TOTAL_TAX_AMOUNT"] = [round(0.0 if m == "USD" else x * 0.16 / 1.16, 2)
                         for x, m in zip(imp, moneda)]
_a, _b, _c = (ri(10000000, 99999999, n_pay), ri(1000000, 9999999, n_pay),
              ri(1000, 9999, n_pay))
P["DESCRIPTION"] = ["%d Almacen %s %d CD_%s_%d" % (a, s, b, s, c)
                    for a, s, b, c in zip(_a, site, _b, _c)]
_flag = runif_lt(n_pay, 0.15)
_a, _b = ri(1000000, 9999999, n_pay), ri(100, 999, n_pay)
P["PAYMENT_REASON_COMMENTS"] = ["DEMO%dREAUT%d" % (a, b) if f else None
                                for f, a, b in zip(_flag, _a, _b)]
P["TIPO_1"] = [None] * n_pay
P["GPO_PAGO"] = smp(["VENDOR-TR", "PS-TR"], n_pay, True)
P["PLZ"] = smp([12, 30, 45, 60], n_pay, True)
P["NO_DOC"] = ri(3000000000, 3000999999, n_pay)
P["IMPORTE_DOC"] = [round(x * u, 2) for x, u in zip(imp, rng.runif(n_pay, 1, 12))]
P["BANK_ACCOUNT_NUM"] = bank
P["BANK_ACCOUNT_NAME"] = ["%s EGRESOS PAGOS CEDIS" % s for s in site]
P["CHECK_ID"] = ri(30000000, 30999999, n_pay)
P["BANK_NUM"] = ["%04d" % x for x in ri(1, 99, n_pay)]
P["INVOICE_ID_1"] = P["INVOICE_ID"]
P["APPROVAL_DESCRIPTION"] = [None] * n_pay
P["SOURCE"] = ["SIMULADO"] * n_pay
P["UUID"] = [uuid_like() for _ in range(n_pay)]

# --------------------------------------------------------------------------
# 4. Inject sporadic anomalous payments (outliers) into normal vendors
# --------------------------------------------------------------------------
n_outlier = int(round(n_pay * OUTLIER_PAYMENT_FRAC))
outlier_rows = [i - 1 for i in rng.sample_int(n_pay, n_outlier)]
mult = rng.runif(n_outlier, 6, 25)
for r, m in zip(outlier_rows, mult):
    imp[r] = imp[r] * m
    P["PAGADO"][r] = fmt_money(imp[r])
flip = [r for r, u in zip(outlier_rows, rng.runif(n_outlier)) if u < 0.5]
for r, o in zip(flip, ri(5, 30, len(flip))):
    P["FECHA_VENCIMIENTO"][r] = P["FECHA_FACTURA"][r] - timedelta(days=o)

# --------------------------------------------------------------------------
# 5. Format & select final columns
# --------------------------------------------------------------------------
pagos_cols = [
    "TIPO", "FECHA_D_PAGO", "VENDOR_ID", "INVOICE_ID", "SITE", "SEGMENT4",
    "VENDOR_NAME", "SEGMENT1", "ATTRIBUTE1", "REFERENCIA", "FECHA_FACTURA",
    "FECHA_VENCIMIENTO", "NUM_FACTURA", "IMPORTE_AP", "PAGADO", "PAGO_MX",
    "TIPO_CAMBIO", "TOTAL_TAX_AMOUNT", "DESCRIPTION",
    "PAYMENT_REASON_COMMENTS", "TIPO_1", "GPO_PAGO", "PLZ", "NO_DOC",
    "IMPORTE_DOC", "BANK_ACCOUNT_NUM", "BANK_ACCOUNT_NAME", "CHECK_ID",
    "BANK_NUM", "INVOICE_ID_1", "APPROVAL_DESCRIPTION", "SOURCE", "UUID",
]
for c in ("FECHA_D_PAGO", "FECHA_FACTURA", "FECHA_VENCIMIENTO"):
    P[c] = [slash_date(d) for d in P[c]]
pagos = [{c: P[c][i] for c in pagos_cols} for i in range(n_pay)]


# --------------------------------------------------------------------------
# 6. Write outputs (same quoting/NA conventions as R's write.csv)
# --------------------------------------------------------------------------
def _cell(x):
    if x is None:
        return ""
    if isinstance(x, str):
        return '"' + x.replace('"', '""') + '"'
    if isinstance(x, float):
        return "%.15g" % x
    return str(x)


def write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write(",".join('"%s"' % c for c in cols) + "\n")
        for r in rows:
            f.write(",".join(_cell(r[c]) for c in cols) + "\n")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(OUT_DIR / "Maestro_simulado.csv", maestro_cols, maestro)
    write_csv(OUT_DIR / "Pagos_simulado.csv", pagos_cols, pagos)
    gt_cols = ["Id Proveedor", "tipo_proveedor", "site", "size_factor", "risk_score"]
    write_csv(OUT_DIR / "Maestro_ground_truth_clusters.csv", gt_cols, vendor_latent)
    print("Vendors: %d | Payments: %d | Outlier payments injected: %d"
          % (len(maestro), len(pagos), n_outlier))
