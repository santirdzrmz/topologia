"""Mapper unidimensional sobre el comportamiento de los pagos."""
from collections import Counter, defaultdict
from itertools import combinations

import numpy as np
from sklearn.cluster import DBSCAN


def build_mapper(points, lens, n_intervals=8, overlap=0.35, eps=0.8, min_samples=5):
    """Agrupa cada intervalo y conecta los grupos que comparten filas.

    Los índices de cada nodo son posiciones de fila en la matriz de entrada.
    """
    if len(points) == 0:
        return [], {}, np.zeros(0, dtype=bool)

    width = 1 / (n_intervals - (n_intervals - 1) * overlap)
    starts = np.arange(n_intervals) * width * (1 - overlap)
    ends = np.minimum(starts + width, 1)
    ends[-1] = 1
    bounds = np.quantile(lens, np.column_stack((starts, ends)))
    # Los empates pueden hacer idénticas varias preimágenes.
    intervals = dict.fromkeys(map(tuple, bounds))

    nodes = []
    memberships = defaultdict(list)
    for interval, (low, high) in enumerate(intervals, start=1):
        rows = np.flatnonzero((lens >= low) & (lens <= high))
        if len(rows) < min_samples:
            continue
        labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(points[rows])
        for label in np.unique(labels[labels >= 0]):
            members = rows[labels == label]
            node_id = len(nodes)
            nodes.append((interval, low, high, members))
            for row in members:
                memberships[row].append(node_id)

    edges = Counter(pair for node_ids in memberships.values() for pair in combinations(node_ids, 2))
    covered = np.zeros(len(points), dtype=bool)
    covered[list(memberships)] = True
    return nodes, dict(edges), covered
