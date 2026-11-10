"""Genera 80 escenarios sintéticos independientes de cualquier archivo externo."""
import argparse
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
N_PROVIDERS, N_PAYMENTS = 400, 5390


def generate(root):
    root.mkdir(parents=True, exist_ok=False)
    rng = np.random.default_rng(42)
    vendors = np.arange(N_PROVIDERS)
    accounts = np.array([f'{v + 1:018d}' for v in vendors])
    master = pd.DataFrame({'Id Proveedor': [f'DEMO-{v:04d}' for v in vendors],
                           'Cuenta': accounts})
    payer = np.concatenate([vendors, rng.choice(vendors, N_PAYMENTS - N_PROVIDERS)])
    rng.shuffle(payer)
    date = pd.Timestamp('2025-01-01') + pd.to_timedelta(rng.integers(0, 365, N_PAYMENTS), unit='D')
    invoice = date - pd.to_timedelta(rng.integers(1, 90, N_PAYMENTS), unit='D')
    due = invoice + pd.to_timedelta(30, unit='D')
    amounts = rng.lognormal(8.5, .6, N_PROVIDERS)[payer] * rng.lognormal(0, .35, N_PAYMENTS)
    payments = pd.DataFrame({
        'VENDOR_ID': master['Id Proveedor'].to_numpy()[payer],
        'VENDOR_NAME': [f'Proveedor ficticio {v:04d}' for v in payer],
        'BANK_ACCOUNT_NUM': accounts[payer],
        'UUID': [f'FACTURA-DEMO-{i:05d}' for i in range(N_PAYMENTS)],
        'FECHA_D_PAGO': date.strftime('%d/%m/%y'),
        'FECHA_FACTURA': invoice.strftime('%d/%m/%y'),
        'FECHA_VENCIMIENTO': due.strftime('%d/%m/%y'),
        'IMPORTE_AP': np.round(amounts, 2),
    })
    control = root / 'CONTROL'
    control.mkdir()
    payments.to_csv(control / 'Pagos.csv', index=False)
    master.to_csv(control / 'Maestro.csv', index=False)

    design = []
    for treatment, (d, c, b, a) in enumerate(product((5, 10), (2, 7), (1, 3), (2, 5)), 1):
        design.append(dict(tratamiento=treatment, A=a, B=b, C=c, D=d, replicas=5))
        for replica in range(1, 6):
            r = np.random.default_rng(42000 + treatment * 100 + replica)
            m, p = master.copy(), payments.copy()
            labels = pd.DataFrame(False, index=p.index, columns=list('ABCD'))
            labels.insert(0, 'fila_pago_original', p.index)
            pair = r.choice(vendors, size=N_PROVIDERS*c//100, replace=False).reshape(-1, 2)
            for source, destination in pair:
                m.loc[destination, 'Cuenta'] = accounts[source]
                p.loc[payer == destination, 'BANK_ACCOUNT_NUM'] = accounts[source]
            affected = np.isin(payer, pair.ravel())
            labels.loc[affected, 'C'] = True

            a_rows = r.choice(p.index[~affected], round(N_PAYMENTS*a/100), replace=False)
            p.loc[a_rows, 'VENDOR_ID'] = [f'EXTERNO-{i:05d}' for i in a_rows]
            labels.loc[a_rows, 'A'] = True
            b_rows = r.choice(p.index[~labels['A']], round(N_PAYMENTS*b/100), replace=False)
            p.loc[b_rows, 'BANK_ACCOUNT_NUM'] = [f'NO-AUTORIZADA-{i:05d}' for i in b_rows]
            labels.loc[b_rows, 'B'] = True
            uuid_pairs = r.choice(p.index, 2*round(N_PAYMENTS*d/200), replace=False).reshape(-1, 2)
            p.loc[uuid_pairs[:, 1], 'UUID'] = p.loc[uuid_pairs[:, 0], 'UUID'].to_numpy()
            labels.loc[uuid_pairs.ravel(), 'D'] = True

            case = root / f'T{treatment:02d}_R{replica:02d}'
            case.mkdir()
            p.to_csv(case / 'Pagos.csv', index=False)
            m.to_csv(case / 'Maestro.csv', index=False)
            labels.to_csv(case / 'etiquetas_pagos.csv', index=False)
    pd.DataFrame(design).to_csv(root / 'matriz_experimental.csv', index=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data')
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f'{args.output} ya existe; elige otro destino para no sobreescribirlo.')
    generate(args.output)
    print(f'Datos generados en {args.output.resolve()}')
