import unittest

import numpy as np

from mapper import build_mapper


class MapperTests(unittest.TestCase):
    def test_nodes_share_rows_only_in_overlap_and_leave_noise_uncovered(self):
        points = np.array([[0], [0], [0], [0], [0], [10]])
        nodes, edges, covered = build_mapper(
            points, np.arange(6), n_intervals=2, overlap=0.5, min_samples=2,
        )

        self.assertEqual([node[3].tolist() for node in nodes], [[0, 1, 2, 3], [2, 3, 4]])
        self.assertEqual(edges, {(0, 1): 2})
        np.testing.assert_array_equal(covered, [True, True, True, True, True, False])

    def test_constant_lens_does_not_duplicate_nodes(self):
        points = np.zeros((5, 2))
        nodes, edges, covered = build_mapper(points, np.zeros(5))

        self.assertEqual(len(nodes), 1)
        self.assertEqual(edges, {})
        self.assertTrue(covered.all())

    def test_no_groups_still_returns_a_mask_for_every_row(self):
        nodes, edges, covered = build_mapper(np.array([[0], [10]]), np.zeros(2), min_samples=2)

        self.assertEqual((nodes, edges), ([], {}))
        np.testing.assert_array_equal(covered, [False, False])
