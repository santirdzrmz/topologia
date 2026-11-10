"""Detección transductiva: ajustar y puntuar cada escenario sin etiquetas."""
import math
import time
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import RobustScaler
from sklearn.metrics import average_precision_score, precision_recall_curve
from detectors import DATA, read_csv, detect

MODELS = ['Isolation Forest', 'LOF']
PROFILES = ['Comportamiento', 'Comportamiento + auditoría']

def features(payments, master, profile):
    if profile not in PROFILES:
        raise ValueError('Perfil desconocido')
    p = payments.reset_index(drop=True)
    vendor = p['VENDOR_ID'].str.strip()
    amount = pd.to_numeric(p['IMPORTE_AP'].str.replace(',', '', regex=False), errors='coerce')
    date = pd.to_datetime(p['FECHA_D_PAGO'], format='%d/%m/%y', errors='coerce')
    invoice = pd.to_datetime(p['FECHA_FACTURA'], format='%d/%m/%y', errors='coerce')
    due = pd.to_datetime(p['FECHA_VENCIMIENTO'], format='%d/%m/%y', errors='coerce')
    median = amount.groupby(vendor).transform('median')
    x = pd.DataFrame({
        'Importe log': np.sign(amount) * np.log1p(amount.abs()),
        'Desviación de importe': (amount - median) / (median.abs() + 1),
        'Pagos del proveedor': vendor.map(vendor.value_counts()),
        'Días factura a pago': (date - invoice).dt.days,
        'Días desde vencimiento': (date - due).dt.days,
        'Día de semana': date.dt.dayofweek,
        'Día del mes': date.dt.day,
    })
    if profile == PROFILES[1]:
        # Señales explícitas de negocio: no son etiquetas, pero codifican las reglas SQL.
        flags = detect(p, master)
        for key in flags:
            x[f'Regla SQL {key}'] = flags[key].astype(int)
        account = p['BANK_ACCOUNT_NUM'].str.strip().replace('', np.nan)
        uuid = p['UUID'].str.strip().str.upper().replace('', np.nan)
        x['Frecuencia UUID'] = uuid.map(uuid.value_counts()).fillna(0)
        x['Proveedores por cuenta de pago'] = account.map(pd.DataFrame({'a':account,'v':vendor}).groupby('a').v.nunique()).fillna(0)
    return x.replace([np.inf, -np.inf], np.nan)

def run_ml(payments, master, model, profile, budget=10, neighbors=35):
    if model not in MODELS or not 0 < budget <= 100 or len(payments) < 3:
        raise ValueError('Modelo, presupuesto o tamaño de muestra inválido')
    start = time.perf_counter()
    x = features(payments, master, profile)
    # Medianas y escala se estiman dentro del escenario, nunca a partir de etiquetas.
    filled = x.fillna(x.median()).fillna(0)
    scaled = RobustScaler().fit_transform(filled)
    if model == MODELS[0]:
        estimator = IsolationForest(n_estimators=150, random_state=42, n_jobs=1)
        estimator.fit(scaled)
        scores = -estimator.score_samples(scaled)
    else:
        estimator = LocalOutlierFactor(n_neighbors=min(neighbors, len(x)-1), n_jobs=1)
        estimator.fit_predict(scaled)
        scores = -estimator.negative_outlier_factor_
    k = max(1, math.ceil(len(x) * budget / 100))
    order = np.argsort(-scores, kind='stable')
    alerts = np.zeros(len(x), dtype=bool)
    alerts[order[:k]] = True
    result = pd.DataFrame({'Puntuación': scores, 'Alerta ML': alerts}, index=x.index)
    return result, x, time.perf_counter()-start

def truth_for(case, index):
    path = DATA / case / 'etiquetas_pagos.csv'
    if not path.exists():
        return None
    labels = read_csv(path)
    ids = pd.to_numeric(labels.pop('fila_pago_original'), errors='raise').astype(int)
    if ids.duplicated().any() or set(ids) != set(index):
        raise ValueError('Las etiquetas no corresponden a los pagos')
    labels.index = ids
    return labels.loc[index, ['A','B','C','D']].apply(lambda c: c.str.lower().eq('true'))

def metrics(truth, pred, scores=None):
    truth, pred = np.asarray(truth, dtype=bool), np.asarray(pred, dtype=bool)
    tp = int((truth & pred).sum()); fp = int((~truth & pred).sum()); fn = int((truth & ~pred).sum())
    return {'Alertas': int(pred.sum()), 'Aciertos': tp, 'Falsos positivos': fp, 'Omitidos': fn,
            'Precisión': tp/(tp+fp) if tp+fp else np.nan,
            'Recall': tp/(tp+fn) if tp+fn else np.nan,
            'F1': 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else np.nan,
            'Average precision': average_precision_score(truth, scores) if scores is not None and truth.any() else np.nan}

def compare(case, sql, predictions):
    truth = truth_for(case, sql.index)
    if truth is None:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    target = truth.any(axis=1)
    rows = [dict(Detector='SQL', **metrics(target, sql.any(axis=1)))]
    per_factor, curves = [], []
    for name, result in predictions.items():
        rows.append(dict(Detector=name, **metrics(target, result['Alerta ML'], result['Puntuación'])))
        for factor in truth:
            # Recall de cobertura: una alerta general no atribuye causalidad A–D.
            per_factor.append({'Detector':name, 'Factor':factor, 'Recall de cobertura': float(result.loc[truth[factor], 'Alerta ML'].mean()) if truth[factor].any() else np.nan})
        if target.any():
            precision, recall, _ = precision_recall_curve(target, result['Puntuación'])
            curves.extend({'Detector':name, 'Recall':r, 'Precisión':p} for p,r in zip(precision, recall))
    return pd.DataFrame(rows), pd.DataFrame(per_factor), pd.DataFrame(curves)
