import unittest

import numpy as np

from persistence import diagrams, mass_scores


class PersistenceTests(unittest.TestCase):
    def test_duplicate_payments_stay_together_until_they_reach_the_bulk(self):
        points = np.array([[0.0], [1.0], [2.0], [9.0], [9.0]])
        np.testing.assert_allclose(mass_scores(points, 0.4), [1, 1, 1, 0, 0])
        np.testing.assert_allclose(mass_scores(points, 0.6), [1, 1, 1, 7, 7])

    def test_square_has_one_finite_cycle(self):
        points = np.array([[0, 0], [0, 1], [1, 1], [1, 0]])
        h0, h1 = diagrams(points)
        np.testing.assert_allclose(h0, [[0, 1], [0, 1], [0, 1]])
        np.testing.assert_allclose(h1, [[1, np.sqrt(2)]])
