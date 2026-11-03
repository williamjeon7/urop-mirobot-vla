"""Pure registration tests; no robot, camera or user measurements are fabricated."""
import copy
import unittest

import numpy as np

from .register_robot_frame import (build_registration, build_registration_from_tip, depth_to_mirobot,
                                   initial_pose_from_status, paper_to_mirobot)


class RobotFrameTests(unittest.TestCase):
    def setUp(self):
        self.camera = np.eye(4)
        self.camera[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
        self.camera[:3, 3] = [.1, .2, .3]
        self.table = dict(format='w9-depth-paper-registration/1', unit='m',
                          T_C_depth_from_T=self.camera.tolist())
        self.flange = [198.67, 0, 230.72, 0, 0, 0]
        self.tool = [15, 0, -55]

    def registration(self, **changes):
        arguments = dict(table_camera_report=self.table, j1_paper_xy_mm=[10, -20],
                         tip_height_mm=168, initial_flange_cart=self.flange, tool_mm=self.tool,
                         axes_parallel_confirmed=True)
        arguments.update(changes)
        return build_registration(**arguments)

    def test_translation_sign_height_and_si_units(self):
        before = copy.deepcopy(self.table)
        result = self.registration()
        np.testing.assert_allclose(result['paper_origin_mirobot_mm'], [-10, 20, 7.72])
        np.testing.assert_allclose(result['initial_tool_point_mirobot_mm'], [213.67, 0, 175.72])
        np.testing.assert_allclose(paper_to_mirobot([1, -2, 0], result), [0, 0, 7.72])
        self.assertFalse(result['independently_validated'])
        self.assertEqual(result['camera_mount'], 'forearm')
        self.assertEqual(self.table, before)

    def test_camera_composition_and_inverse_are_correct(self):
        report = self.registration()
        paper_m = np.array([.02, -.03, .015])
        camera_m = self.camera[:3, :3]@paper_m+self.camera[:3, 3]
        expected = paper_to_mirobot((paper_m*100).tolist(), report)
        np.testing.assert_allclose(depth_to_mirobot(camera_m, report), expected, atol=1e-10)
        np.testing.assert_allclose(np.array(report['T_M_from_C_depth'])@np.array(report['T_C_depth_from_M']),
                                   np.eye(4), atol=1e-12)

    def test_tool_offset_rotates_with_actual_cartesian_abc(self):
        result = self.registration(initial_flange_cart=[198.67, 0, 230.72, 90, 0, 0])
        np.testing.assert_allclose(result['initial_tool_point_mirobot_mm'], [213.67, 55, 230.72], atol=1e-10)
        self.assertAlmostEqual(result['paper_origin_mirobot_mm'][2], 62.72)

    def test_measured_tip_projection_derives_cartesian_origin_without_claiming_j1(self):
        result = build_registration_from_tip(
            self.table, [223.67, -20], 168, self.flange, self.tool,
            axes_parallel_confirmed=True)
        np.testing.assert_allclose(result['paper_origin_mirobot_mm'], [-10, 20, 7.72])
        np.testing.assert_allclose(result['derived_controller_cartesian_xy_origin_paper_mm'], [10, -20])
        self.assertNotIn('j1_centre_paper_xy_mm', result['user_measurements'])
        self.assertEqual(result['user_measurements']['open_finger_tip_midpoint_paper_xy_mm'], [223.67, -20])
        self.assertFalse(any('J1' in item for item in result['assumptions']))
        np.testing.assert_allclose(paper_to_mirobot([22.367, -2, 16.8], result), [213.67, 0, 175.72])
        with self.assertRaisesRegex(ValueError, 'confirmation'):
            build_registration_from_tip(self.table, [223.67, -20], 168, self.flange, self.tool)

    def test_missing_confirmation_invalid_measurements_and_degenerate_transforms_rejected(self):
        cases = [dict(axes_parallel_confirmed=False), dict(j1_paper_xy_mm=[None, 0]),
                 dict(j1_paper_xy_mm=[float('nan'), 0]), dict(tip_height_mm=-1),
                 dict(tip_height_mm=float('inf')), dict(tool_mm=[0, 0]),
                 dict(table_camera_report=dict(self.table, unit='cm')),
                 dict(table_camera_report=dict(self.table, T_C_depth_from_T=np.zeros((4, 4)).tolist())),
                 dict(table_camera_report=dict(self.table, T_C_depth_from_T=np.diag([-1, 1, 1, 1]).tolist())),
                 dict(table_camera_report=dict(self.table, T_C_depth_from_T=None))]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.registration(**changes)

    def test_idle_status_and_stability_requirements(self):
        rows = [dict(raw='<Idle,Cartesian:...>', cart=self.flange.copy()) for _ in range(3)]
        np.testing.assert_allclose(initial_pose_from_status(dict(rows=rows)), self.flange)
        with self.assertRaises(ValueError):
            initial_pose_from_status(dict(rows=rows[:2]))
        bad = copy.deepcopy(rows)
        bad[1]['raw'] = '<Run,Cartesian:...>'
        with self.assertRaises(ValueError):
            initial_pose_from_status(dict(rows=bad))
        bad = copy.deepcopy(rows)
        bad[1]['cart'][0] += 1
        with self.assertRaises(ValueError):
            initial_pose_from_status(dict(rows=bad))

    def test_point_inputs_must_be_finite_and_in_expected_report_units(self):
        result = self.registration()
        with self.assertRaises(ValueError):
            paper_to_mirobot([0, float('nan'), 0], result)
        with self.assertRaises(ValueError):
            depth_to_mirobot([0, 0, .3], dict(result, unit='mm'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
