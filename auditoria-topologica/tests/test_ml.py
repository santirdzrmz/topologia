import unittest
import numpy as np
import pandas as pd
from detectors import load_case
from ml import features, run_ml, PROFILES, MODELS, compare, metrics

class MLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, cls.m, cls.sql = load_case('T01_R01')

    def test_no_label_features_and_missing_values(self):
        p = self.p.iloc[:100].copy()
        p['IMPORTE_AP'] = ''
        p['FECHA_D_PAGO'] = ''
        for profile in PROFILES:
            x = features(p, self.m, profile)
            self.assertFalse(any('etiqueta' in c.lower() for c in x))
            result, _, _ = run_ml(p, self.m, MODELS[0], profile, 7)
            self.assertTrue(np.isfinite(result['Puntuación']).all())
            self.assertEqual(result['Alerta ML'].sum(), 7)

    def test_reproducibility_budget_and_evaluation(self):
        results = {}
        for model in MODELS:
            first, _, _ = run_ml(self.p, self.m, model, PROFILES[0], 10)
            second, _, _ = run_ml(self.p, self.m, model, PROFILES[0], 10)
            pd.testing.assert_frame_equal(first, second)
            self.assertEqual(first['Alerta ML'].sum(), 539)
            results[model] = first
        summary, coverage, curves = compare('T01_R01', self.sql, results)
        self.assertEqual(len(summary), 3)
        self.assertEqual(len(coverage), 8)
        self.assertFalse(curves.empty)
        sql = summary.set_index('Detector').loc['SQL']
        self.assertEqual(sql.Recall, 1)
        self.assertEqual(sql['Precisión'], 1)
        self.assertTrue(compare('CONTROL', self.sql, results)[0].empty)

    def test_metrics_known_confusion(self):
        result = metrics([1,1,0,0], [1,0,1,0], [4,3,2,1])
        self.assertEqual(result['Precisión'], .5)
        self.assertEqual(result['Recall'], .5)
        self.assertEqual(result['Average precision'], 1)
