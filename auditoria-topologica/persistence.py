"""Homología persistente por corrida sobre pagos y señales de auditoría."""
import math

import numpy as np
import pandas as pd

MASS_FRACTION = 0.25
RELATIONAL_WEIGHT = 4.0
MAX_LANDMARKS = 600


def behavior(payments):
    p = payments.reset_index(drop=True)
    amount = pd.to_numeric(p['IMPORTE_AP'].str.replace(',', '', regex=False), errors='coerce')
    log_amount = np.sign(amount) * np.log1p(amount.abs())
    vendor = p['VENDOR_ID'].str.strip()
    center = log_amount.groupby(vendor).transform('median')
    mad = (log_amount - center).abs().groupby(vendor).transform('median')
    positive = mad[mad.gt(0)]
    floor = positive.median() if not positive.empty else 1.0
    invoice, paid, due = (
        pd.to_datetime(p[field], format='%d/%m/%y', errors='coerce')
        for field in ('FECHA_FACTURA', 'FECHA_D_PAGO', 'FECHA_VENCIMIENTO')
    )
    return pd.DataFrame({
        'Importe log': log_amount,
        'Desviación de importe': (log_amount - center) / (1.4826 * mad.clip(lower=floor)),
        'Días factura a pago': (paid - invoice).dt.days,
        'Días factura a vencimiento': (due - invoice).dt.days,
    }).replace([np.inf, -np.inf], np.nan)


def fit_reference(payments):
    x = behavior(payments)
    center = x.median().fillna(0)
    quartiles = x.quantile([0.25, 0.75])
    scale = (quartiles.loc[0.75] - quartiles.loc[0.25]) / 1.349
    scale = scale.where(scale.gt(0), x.std())
    return center, scale.where(scale.gt(0), 1.0)


def point_cloud(payments, flags, reference):
    center, scale = reference
    continuous = ((behavior(payments).fillna(center) - center) / scale).clip(-8, 8)
    return np.column_stack((continuous.to_numpy(), RELATIONAL_WEIGHT * flags.to_numpy(dtype=float)))


def mass_scores(points, fraction=MASS_FRACTION):
    """Escala en que la componente de cada pago alcanza la masa solicitada."""
    n = len(points)
    threshold = math.ceil(fraction * n)
    scores = np.zeros(n)
    if threshold <= 1:
        return scores

    # Prim usa memoria lineal y conserva aristas de longitud cero entre duplicados.
    selected = np.zeros(n, dtype=bool)
    nearest = np.full(n, np.inf)
    parent = np.zeros(n, dtype=int)
    current = 0
    edges = []
    for _ in range(n - 1):
        selected[current] = True
        distances = np.linalg.norm(points - points[current], axis=1)
        better = ~selected & (distances < nearest)
        nearest[better] = distances[better]
        parent[better] = current
        nearest[current] = np.inf
        current = int(nearest.argmin())
        edges.append((nearest[current], parent[current], current))

    roots = np.arange(n)
    members = {i: [i] for i in range(n)}
    for distance, left, right in sorted(edges):
        a, b = roots[left], roots[right]
        if len(members[a]) < len(members[b]):
            a, b = b, a
        if len(members[a]) + len(members[b]) >= threshold:
            for group in (members[a], members[b]):
                if len(group) < threshold:
                    scores[group] = distance
        roots[members[b]] = a
        members[a].extend(members.pop(b))
    return scores


def diagrams(points):
    """Diagramas finitos de Vietoris–Rips con submuestra max-min cuando aplica."""
    if len(points) < 2:
        return [np.empty((0, 2)), np.empty((0, 2))]
    from ripser import ripser

    result = ripser(points, maxdim=1, n_perm=min(MAX_LANDMARKS, len(points)))
    return [d[np.isfinite(d[:, 1])] for d in result['dgms']]
