"""CPU tests: timeline pairing, quaternion wrap, missing data, RGB and HDF5 contracts."""
from __future__ import annotations

import json
import queue
import tempfile
import time
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

import cv2
import h5py
import numpy as np

from common.rotation import quat_from_axis_deg
from .check_dataset import check
from .export_hdf5 import wrist_image, write_demo
from .prepare import gripper_track, nearest_indices, prepare, slerp
from .robot_capture import validate_gcode
from .train import training_command
from .teleop import TeleopSession
from .color_calibration import (D65, RGB_XYZ, adapt_xyz, apply_rgb, decode_srgb, encode_srgb,
                                fit_matrix, lab_to_xyz, xyz_to_lab)

REPO = Path(__file__).resolve().parents[3]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixture(self):
        ep = self.root/'red_s2_001'
        ep.mkdir()
        reference = (REPO/'docs/W6/poses/pickup-red-s2.jsonl').read_text(encoding='utf-8').splitlines()[0]
        (ep/'reference.jsonl').write_text(reference+'\n', encoding='utf-8')
        (ep/'source.gcode').write_text((REPO/'trajectories/2026_10_11-w6-pickup-red-s2-e5.gcode').read_text(encoding='utf-8'), encoding='utf-8')
        (ep/'metadata.json').write_text(json.dumps(dict(complete=True, robot=True, seed=2, color='red',
            gripper_seconds=0.2, initial_s=40, open_s=40, closed_s=60)), encoding='utf-8')
        frames = [dict(t_s=k/30, number=k+1, file=f'rgb/{k}.png') for k in range(61)]
        events = [dict(kind='state', t_s=k/20, cart=[198.67+k*0.1, 0, 230.72, 0, 0, 0]) for k in range(41)]
        events += [dict(kind='command', t_s=0.525, cmd='M4 S60'), dict(kind='complete', t_s=2.01)]
        events.sort(key=lambda r: r['t_s'])
        for name, rows in [('frames', frames), ('robot', events)]:
            (ep/(name+'.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')
        return ep

    def test_grid_has_one_extra_target_and_gripper_switch_is_not_shifted(self):
        aligned, report = prepare(self.fixture())
        self.assertEqual(aligned['robot_states'].shape, (41, 9))
        self.assertEqual(len(aligned['frame_indices']), 40)
        np.testing.assert_allclose(np.diff(aligned['times']), 0.05)
        self.assertEqual(aligned['gripper_actions'][9], -1)
        self.assertEqual(aligned['gripper_actions'][10], 1)  # target t=.55 crosses command at .525
        self.assertAlmostEqual(report['robot_hz_median'], 20)
        # Position is interpolated from physical measurement, not all-zero placeholder labels.
        self.assertGreater(np.linalg.norm(aligned['positions'][-1]-aligned['positions'][0]), 0)

    def test_missing_state_interval_is_rejected(self):
        ep = self.fixture()
        path = ep/'robot.jsonl'
        rows = [json.loads(r) for r in path.read_text().splitlines()]
        rows = [r for r in rows if r['kind'] != 'state' or not 0.6 <= r['t_s'] <= 0.9]
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'state gap'):
            prepare(ep)

    def test_missing_camera_and_duplicate_times_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Camera frame'):
            nearest_indices(np.array([0., 1.]), np.array([0.5]), 0.04)
        ep = self.fixture()
        path = ep/'frames.jsonl'
        lines = path.read_text().splitlines()
        lines[1] = lines[0]
        path.write_text('\n'.join(lines), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'increasing'):
            prepare(ep)

    def test_quaternion_179_to_minus179_takes_short_path(self):
        a, b = quat_from_axis_deg('z', 179), quat_from_axis_deg('z', -179)
        middle = slerp(a, b, .5)
        self.assertAlmostEqual(abs(middle[3]), 1., places=6)
        np.testing.assert_allclose(slerp(a, -np.array(a), .5), a, atol=1e-7)

    def test_gripper_ramp_and_mid_ramp_reversal(self):
        events = [dict(t_s=1., cmd='M4 S60'), dict(t_s=1.5, cmd='M4 S40')]
        actual, control = gripper_track(events, [1., 1.25, 1.5, 2.], 1., 40, 40, 60)
        np.testing.assert_allclose(actual, [0., .25, .5, .25])
        np.testing.assert_allclose(control, [1, 1, -1, -1])
        repeated = [dict(t_s=1., cmd='M4 S60'), dict(t_s=1.25, cmd='M4 S60')]
        actual, _ = gripper_track(repeated, [1.5, 2.], 1., 40, 40, 60)
        np.testing.assert_allclose(actual, [.5, 1.])

    def test_gcode_is_prevalidated_before_any_device_open(self):
        path = self.root/'motion.gcode'
        for invalid in ['G90\nG0 X0 Y0 Z30 A0 B0 C0\n', 'G91\n', 'G90\n$H\n', 'G90\nG0 X0 Y0 Z100\n']:
            path.write_text(invalid, encoding='utf-8')
            with self.assertRaises(ValueError):
                validate_gcode(path)
        path.write_text('G90\nM20\nG0 X198 Y0 Z230 A0 B0 C0\nM4 S60\n', encoding='utf-8')
        self.assertEqual(len(validate_gcode(path)), 4)

    def test_rgb_crop_rotation_and_hdf5_loader_contract(self):
        ep = self.fixture()
        aligned, _ = prepare(ep)
        png = self.root/'red.png'
        bgr = np.zeros((20, 30, 3), np.uint8)
        bgr[:, :, 2] = 255
        cv2.imwrite(str(png), bgr)
        rgb = wrist_image(png, 90)
        self.assertEqual(rgb.shape, (256, 256, 3))
        np.testing.assert_array_equal(rgb[0, 0], [255, 0, 0])
        suite = self.root/'hdf5'/'mirobot_real'
        suite.mkdir(parents=True)
        instruction = 'pick up the red block on the table'
        path = suite/'MIROBOT_red_s2_SCENE1_pick_up_the_red_block_on_the_table_demo.hdf5'
        n = len(aligned['times'])-1
        write_demo(path, instruction, [rgb]*n, [rgb]*n, np.zeros((n, 7)),
                   aligned['robot_states'][:-1], aligned['times'][:-1], {},
                   aligned['frame_error_s'], np.zeros((n, 2)))
        report = check(suite.parent)
        self.assertEqual(report['episodes'], 1)
        self.assertEqual(report['steps'], 40)
        self.assertEqual(report['instructions'], [instruction])
        with h5py.File(path, 'r+') as f:
            f['data/demo_0/robot_states'][0, 5:9] = 0
        with self.assertRaisesRegex(ValueError, 'quaternion'):
            check(suite.parent)

    def test_training_overrides_both_datasets_and_policy_checkpoint(self):
        cmd = training_command(Path('/cosmos'), Path('/data'), Path('/libero.pt'))
        for prefix in ['dataloader_train.dataset', 'dataloader_train.sampler.dataset']:
            self.assertIn(prefix+'.rollout_data_dir=""', cmd)
            self.assertIn(prefix+'.demonstration_sampling_prob=1.0', cmd)
        self.assertIn('checkpoint.load_path='+json.dumps(str(Path('/libero.pt'))), cmd)

    def test_manual_interval_excludes_homing_and_exit(self):
        ep = self.fixture()
        meta_path = ep/'metadata.json'
        meta = json.loads(meta_path.read_text())
        meta['teleop'] = True
        meta_path.write_text(json.dumps(meta), encoding='utf-8')
        path = ep/'robot.jsonl'
        rows = [json.loads(r) for r in path.read_text().splitlines()]
        rows.extend([dict(kind='capture_start', t_s=.25), dict(kind='capture_end', t_s=1.75)])
        rows.sort(key=lambda r: r['t_s'])
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')
        aligned, _ = prepare(ep)
        self.assertAlmostEqual(aligned['times'][0], .25)
        self.assertAlmostEqual(aligned['times'][-1], 1.75)
        self.assertEqual(len(aligned['gripper_actions']), 30)

    def test_srgb_roundtrip_and_d50_d65_adaptation(self):
        pixels = np.array([[0, 12, 255], [32, 128, 200]], np.uint8)
        np.testing.assert_array_equal(encode_srgb(decode_srgb(pixels)), pixels)
        d50 = np.array([.9642, 1., .8249])
        np.testing.assert_allclose(adapt_xyz([d50], d50, D65), [D65], atol=1e-8)
        lab = np.array([[50., 10., -15.], [95., 0., 0.]])
        np.testing.assert_allclose(xyz_to_lab(lab_to_xyz(lab, d50), d50), lab, atol=1e-8)
        np.testing.assert_array_equal(apply_rgb(pixels, dict(matrix=np.eye(3).tolist())), pixels)

    def test_chart_fit_improves_unseen_patches_for_known_cast(self):
        rng = np.random.default_rng(42)
        measured_rgb = rng.integers(50, 180, size=(24, 3)).astype(np.uint8)
        measured = decode_srgb(measured_rgb)
        truth = np.array([[1.15, .02, 0], [0, .85, .01], [.01, 0, 1.05]])
        reference_lab = xyz_to_lab((measured@truth)@RGB_XYZ.T, D65)
        matrix, report = fit_matrix(measured_rgb, reference_lab, D65)
        np.testing.assert_allclose(matrix, truth, atol=1e-6)
        self.assertLess(report['heldout_mean_after'], report['heldout_mean_before']/100)

    def test_teleop_has_one_serial_reader_and_status_query_needs_no_ok(self):
        class FakeSerial:
            def __init__(self, *args, **kwargs):
                self.lines, self.is_open = queue.Queue(), True
                self.writes = []
            def write(self, value):
                self.writes.append(value)
                self.lines.put(b'<Idle,Cartesian:198.67,0,230.72,0,0,0>\n' if value == b'?\n' else b'ok\n')
            def readline(self):
                try:
                    return self.lines.get(timeout=.005)
                except queue.Empty:
                    return b''
            def close(self):
                self.is_open = False
        session = TeleopSession(self.root, time.perf_counter_ns(), threading.Event(), 40)
        self.addCleanup(session.log.close)
        self.addCleanup(session.close)
        with patch('serial.Serial', FakeSerial):
            session.open_serial(port='FAKE')
            self.assertTrue(session.send_gcode('G90'))
            self.assertTrue(session.send_gcode('?'))
            session.emit('capture_start')
            session.started = True
            self.assertTrue(session.send_gcode('M4 S60'))
            session.emit('capture_end')
            session.ended = True
            session.finish()
        rows = [json.loads(r) for r in (self.root/'robot.jsonl').read_text().splitlines()]
        self.assertTrue(any(r['kind'] == 'state' for r in rows))
        self.assertEqual([r['cmd'] for r in rows if r['kind'] == 'command'], ['G90', '?', 'M4 S60'])
        self.assertEqual(rows[-1]['kind'], 'complete')


if __name__ == '__main__':
    unittest.main(verbosity=2)
