"""
cargar_mysql.py — Sube las 80 corridas + CONTROL a MySQL 8.0 (base femsa_fraude).

Uso (desde la carpeta donde está Resultados_80_Pruebas):
    pip install pandas mysql-connector-python
    python cargar_mysql.py Resultados_80_Pruebas
    python cargar_mysql.py Resultados_80_Pruebas --user root --host localhost --port 3306
    python cargar_mysql.py Resultados_80_Pruebas --reemplazar     # vuelve a cargar corridas que ya existían

Pide la contraseña al iniciar (no se guarda en ningún lado).
Antes de cargar ejecuta 01_esquema.sql (debe estar junto a este script).
No usa LOAD DATA LOCAL INFILE, así que no hay que cambiar nada en Workbench ni en el servidor.
"""
import argparse
import getpass
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd
import mysql.connector

LOTE = 2000
FECHAS_PAGO = {"fecha_d_pago", "fecha_factura", "fecha_vencimiento"}   # formato dd/mm/yy
DECIMALES = {"importe_ap", "total_tax_amount", "importe_doc"}


def snake(col):
    col = unicodedata.normalize("NFKD", col).encode("ascii", "ignore").decode().strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", col).strip("_")


def leer(f):
    return pd.read_csv(f, dtype=str, encoding="utf-8-sig", keep_default_na=False)


def buscar(carpeta, prefijo):
    c = sorted(p for p in carpeta.glob("*.csv") if p.name.lower().startswith(prefijo.lower()))
    return c[0] if c else None


def preparar(df, columnas_tabla):
    """Renombra a snake_case, convierte tipos y deja solo las columnas que existen en la tabla."""
    df = df.rename(columns=snake)
    faltan = [c for c in df.columns if c not in columnas_tabla]
    if faltan:
        raise ValueError(f"columnas que no están en la tabla: {faltan}")
    df = df.apply(lambda s: s.str.strip())
    for c in df.columns:
        if c in FECHAS_PAGO:
            df[c] = pd.to_datetime(df[c], format="%d/%m/%y", errors="coerce").dt.strftime("%Y-%m-%d")
        elif c in DECIMALES:
            df[c] = pd.to_numeric(df[c].str.replace(r"[$,\s]", "", regex=True), errors="coerce")
    df = df.astype(object).where(df.notna() & (df != ""), None)   # '' y NaN -> NULL
    return df


def insertar(cur, tabla, df):
    cols = list(df.columns)
    sql = f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
    filas = [tuple(None if (isinstance(v, float) and pd.isna(v)) else v for v in r)
             for r in df.itertuples(index=False, name=None)]
    for i in range(0, len(filas), LOTE):
        cur.executemany(sql, filas[i:i + LOTE])
    return len(filas)


def bool01(s):
    return (s.astype(str).str.strip().str.lower() == "true").astype(int)


def columnas(cur, tabla):
    cur.execute(f"SHOW COLUMNS FROM {tabla}")
    return {r[0] for r in cur.fetchall()}


def ejecutar_esquema(cur, archivo):
    texto = Path(archivo).read_text(encoding="utf-8")
    texto = re.sub(r"--[^\n]*", "", texto)
    for stmt in [s.strip() for s in texto.split(";") if s.strip()]:
        cur.execute(stmt)


def cargar_corrida(cn, cur, carpeta, cols, reemplazar):
    nombre = carpeta.name
    cur.execute("SELECT COUNT(*) FROM corridas WHERE corrida=%s", (nombre,))
    if cur.fetchone()[0]:
        if not reemplazar:
            return "ya existía (omitida)"
        for t in ("pagos", "maestro", "etiquetas_pagos", "etiquetas_maestro", "corridas"):
            cur.execute(f"DELETE FROM {t} WHERE corrida=%s", (nombre,))

    meta = {}
    if (carpeta / "resumen.json").exists():
        meta = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8-sig"))
    niv = meta.get("niveles_porcentaje", {})
    cur.execute("INSERT INTO corridas VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (nombre, meta.get("tratamiento"), meta.get("replica"), meta.get("semilla"),
                 niv.get("A"), niv.get("B"), niv.get("C"), niv.get("D")))

    n = {}
    for tabla, prefijo in (("maestro", "Maestro"), ("pagos", "Pagos")):
        f = buscar(carpeta, prefijo)
        if f is None:
            raise FileNotFoundError(f"falta {prefijo}*.csv")
        df = preparar(leer(f), cols[tabla])
        df.insert(0, "fila", range(len(df)))
        df.insert(0, "corrida", nombre)
        n[tabla] = insertar(cur, tabla, df)

    if (carpeta / "etiquetas_pagos.csv").exists():
        e = leer(carpeta / "etiquetas_pagos.csv")
        df = pd.DataFrame({"corrida": nombre, "fila": e["fila_pago_original"].astype(int),
                           **{c.lower(): bool01(e[c]) for c in "ABCD"}})
        n["etiquetas_pagos"] = insertar(cur, "etiquetas_pagos", df)
    if (carpeta / "etiquetas_maestro.csv").exists():
        e = leer(carpeta / "etiquetas_maestro.csv")
        df = pd.DataFrame({"corrida": nombre, "fila": e["fila_maestro_original"].astype(int),
                           "id_proveedor": e["Id Proveedor"].str.strip(), "c": bool01(e["C"])})
        n["etiquetas_maestro"] = insertar(cur, "etiquetas_maestro", df)
    cn.commit()
    return ", ".join(f"{k}={v}" for k, v in n.items())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ruta", help="carpeta Resultados_80_Pruebas")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=3306)
    ap.add_argument("--user", default="root")
    ap.add_argument("--password", default=None, help="si no se da, se pide en pantalla")
    ap.add_argument("--reemplazar", action="store_true")
    a = ap.parse_args()

    ruta = Path(a.ruta)
    carpetas = sorted(p for p in ruta.iterdir() if p.is_dir() and buscar(p, "Pagos"))
    if not carpetas:
        sys.exit(f"No encontré carpetas con Pagos*.csv dentro de {ruta}")

    pw = a.password if a.password is not None else getpass.getpass(f"Contraseña MySQL de {a.user}: ")
    cn = mysql.connector.connect(host=a.host, port=a.port, user=a.user, password=pw, autocommit=False)
    cur = cn.cursor()
    ejecutar_esquema(cur, Path(__file__).with_name("01_esquema.sql"))
    cur.execute("USE femsa_fraude")
    cols = {t: columnas(cur, t) for t in ("maestro", "pagos")}

    errores = 0
    for i, c in enumerate(carpetas, 1):
        t0 = time.time()
        try:
            msg = cargar_corrida(cn, cur, c, cols, a.reemplazar)
            print(f"[{i:>2}/{len(carpetas)}] {c.name:<10} {msg}  ({time.time() - t0:.1f}s)")
        except Exception as e:
            cn.rollback()
            errores += 1
            print(f"[{i:>2}/{len(carpetas)}] {c.name:<10} ERROR: {e}")

    cur.execute("SELECT COUNT(*), (SELECT COUNT(*) FROM pagos), (SELECT COUNT(*) FROM maestro) FROM corridas")
    nc, npg, nm = cur.fetchone()
    print(f"\nListo. En femsa_fraude hay {nc} corridas, {npg:,} pagos y {nm:,} filas de maestro. Errores: {errores}")
    cur.close()
    cn.close()


if __name__ == "__main__":
    main()
