"""Synthetic depth/table registration geometry tests; no camera or robot access."""
import json
from pathlib import Path
import unittest

import numpy as np

from .register_depth_table import fit_plane, rigid_fit


class DepthTableGeometryTests(unittest.TestCase):
    @staticmethod
    def known_transform():
        z, x = np.deg2rad(37), np.deg2rad(-24)
        rz = np.array([[np.cos(z), -np.sin(z), 0],
                       [np.sin(z), np.cos(z), 0], [0, 0, 1]])
        rx = np.array([[1, 0, 0], [0, np.cos(x), -np.sin(x)],
                       [0, np.sin(x), np.cos(x)]])
        return rz@rx, np.array([.013, -.027, .251])

    def test_rigid_fit_maps_table_points_to_camera_and_inverts(self):
        rng = np.random.default_rng(29)
        table = rng.uniform(-.1, .1, size=(30, 3))
        expected_r, expected_t = self.known_transform()
        camera = table@expected_r.T+expected_t
        rotation, translation = rigid_fit(table, camera)
        np.testing.assert_allclose(rotation, expected_r, atol=1e-12)
        np.testing.assert_allclose(translation, expected_t, atol=1e-12)
        np.testing.assert_allclose((camera-translation)@rotation, table, atol=1e-12)
        self.assertAlmostEqual(np.linalg.det(rotation), 1, places=12)

    def test_planar_points_preserve_right_handed_normal_and_metric_units(self):
        table = np.array([[0, 0, 0], [.1, 0, 0], [0, .1, 0],
                          [.1, .1, 0], [-.1, .1, 0]])
        # Optical X right, Y down, Z forward: table X up, Y left, Z toward camera.
        expected_r = np.array([[0., -1., 0.], [-1., 0., 0.], [0., 0., -1.]])
        expected_t = np.array([.007, -.048, .252])
        camera = table@expected_r.T+expected_t
        rotation, translation = rigid_fit(table, camera)
        np.testing.assert_allclose(rotation, expected_r, atol=1e-12)
        np.testing.assert_allclose(translation, expected_t, atol=1e-12)
        np.testing.assert_allclose(np.cross(rotation[:, 0], rotation[:, 1]), rotation[:, 2], atol=1e-12)
        self.assertAlmostEqual(np.linalg.norm(camera[1]-camera[0]), .1, places=12)

    def test_source_collinearity_is_rejected(self):
        line = np.array([[0., 0., 0.], [1., 0., 0.], [2., 0., 0.]])
        with self.assertRaisesRegex(ValueError, 'collinear'):
            rigid_fit(line, line+1)

    def test_destination_collinearity_is_rejected(self):
        source = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
        line = np.array([[0., 0., 0.], [1., 0., 0.], [2., 0., 0.]])
        with self.assertRaisesRegex(ValueError, 'collinear'):
            rigid_fit(source, line)

    def test_improper_reflection_is_not_returned_as_a_rotation(self):
        rng = np.random.default_rng(30)
        source = rng.normal(size=(20, 3))*.1
        reflected = source*np.array([-1, 1, 1])
        rotation, translation = rigid_fit(source, reflected)
        self.assertAlmostEqual(np.linalg.det(rotation), 1, places=12)
        self.assertGreater(np.linalg.norm(source@rotation.T+translation-reflected), .1)

    def test_plane_fit_recovers_noisy_metric_plane_and_rejects_outliers(self):
        rng = np.random.default_rng(31)
        xy = rng.uniform(-.15, .15, size=(500, 2))
        z = .25+.1*xy[:, 0]-.07*xy[:, 1]+rng.normal(0, .00015, len(xy))
        paper = np.column_stack([xy, z])
        clutter = rng.uniform([-.15, -.15, .35], [.15, .15, .55], size=(100, 3))
        centre, normal, keep = fit_plane(np.vstack([paper, clutter]), threshold_m=.001)
        expected = np.array([-.1, .07, 1.]); expected /= np.linalg.norm(expected)
        self.assertGreater(abs(normal@expected), .99999)
        self.assertLess(abs(centre[2]-.25-.1*centre[0]+.07*centre[1]), .0001)
        self.assertGreaterEqual(np.count_nonzero(keep[:500]), 498)
        self.assertFalse(keep[500:].any())

    def test_too_few_native_depth_points_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Too few'):
            fit_plane(np.zeros((99, 3)))

    def test_saved_snapshot_transform_has_consistent_frame_sign_and_inverse(self):
        path = Path(__file__).resolve().parents[1]/'data/calibration/depth_registration_20261102_01/table_to_camera.json'
        if not path.exists():
            self.skipTest('Local native RGB-D calibration artifact is not available.')
        report = json.loads(path.read_text(encoding='utf-8'))
        forward = np.asarray(report['T_C_depth_from_T'])
        inverse = np.asarray(report['T_T_from_C_depth'])
        np.testing.assert_allclose(forward@inverse, np.eye(4), atol=1e-10)
        np.testing.assert_allclose(forward[:3, :3].T@forward[:3, :3], np.eye(3), atol=1e-10)
        self.assertAlmostEqual(np.linalg.det(forward[:3, :3]), 1, places=10)
        self.assertLess(forward[1, 0], -.9)  # +table X is up in this snapshot.
        self.assertLess(forward[0, 1], -.9)  # +table Y is left in this snapshot.
        self.assertLess(forward[2, 2], -.9)  # +table Z faces the camera.
        self.assertEqual(report['unit'], 'm')
        self.assertIsNone(report['robot_registration'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
