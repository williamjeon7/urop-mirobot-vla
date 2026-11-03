"""CPU tests: timeline pairing, quaternion wrap, missing data, RGB and HDF5 contracts."""
from __future__ import annotations

import json
import hashlib
import io
import os
import runpy
import queue
import tempfile
import time
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
from contextlib import nullcontext, redirect_stderr

import cv2
import h5py
import numpy as np

from common.rotation import quat_from_axis_deg
from .check_dataset import check
from .export_hdf5 import main as export_main, wrist_image, write_demo
from .prepare import gripper_track, input_hashes, input_hashes_match, nearest_indices, prepare, slerp
from .robot_capture import validate_gcode
from .train import training_command
from .teleop import SCRIPT_POSE, TeleopSession
from tools.run_gcode import pose_of
from .capture_storage import read_image, reserve_episode, write_image
from .preview import create_review
from .color_calibration import (D65, RGB_XYZ, adapt_xyz, apply_rgb, decode_srgb, encode_srgb,
                                fit_matrix, lab_to_xyz, linear_to_lab, load_profile,
                                sample_patches, xyz_to_lab)
from .color_refinement import fit_affine
from .recording_controls import RecordingControls

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

    def test_numbering_continues_after_highest_reserved_episode(self):
        (self.root/'영상1').mkdir()
        (self.root/'영상3').mkdir()  # Includes incomplete captures; never reuse their number.
        (self.root/'chart_001').mkdir()
        (self.root/'영상_notes').mkdir()
        self.assertEqual(reserve_episode(self.root).name, '영상4')
        self.assertEqual(reserve_episode(self.root).name, '영상5')
        self.assertEqual(reserve_episode(self.root/'new').name, '영상1')

    def test_renamed_blue_recordings_keep_numbering_and_hdf5_identity(self):
        from .capture_storage import resolve_blue_episode
        from .export_real_hdf5 import episode_id
        self.assertEqual(resolve_blue_episode(self.root, 1), self.root/'영상1')
        for number in range(1, 11):
            (self.root/f'layoutblue{number}').mkdir()
            self.assertEqual(episode_id(self.root/f'layoutblue{number}'), f'video{number}')
            self.assertEqual(resolve_blue_episode(self.root, number), self.root/f'layoutblue{number}')
        self.assertEqual(reserve_episode(self.root).name, '영상11')
        self.assertEqual(episode_id('layoutblue11'), 'layoutblue11')

    def test_clipped_chart_keeps_diagnostics_without_a_profile(self):
        prefix = self.root/'classic_mini.json'
        image = np.full((401, 601, 3), 100, dtype=np.uint8)
        image[0:100, 0:100, 0] = 0
        with self.assertRaisesRegex(ValueError, 'row 1 col 1: low=100.0%, high=0.0%'):
            sample_patches(image, [[0, 0], [600, 0], [600, 400], [0, 400]], prefix)
        self.assertFalse(prefix.exists())
        self.assertTrue(prefix.with_suffix('.patches.png').is_file())
        report = json.loads(prefix.with_suffix('.sampling.json').read_text(encoding='utf-8'))
        self.assertFalse(report['clipping_passed'])
        self.assertEqual(report['patches'][0]['low_fraction'], 1)
        self.assertEqual(report['patches'][0]['high_fraction'], 0)

    def test_affine_profile_fits_unseen_patch_colours_and_preserves_v1(self):
        rng = np.random.default_rng(27)
        rgb = rng.integers(50, 180, size=(24, 3)).astype(np.uint8)
        expected_matrix = np.diag([1.08, .94, 1.04])
        expected_offset = np.array([.004, .006, .003])
        lab = linear_to_lab(decode_srgb(rgb)@expected_matrix+expected_offset, D65)
        matrix, offset, report = fit_affine(rgb, lab, D65)
        self.assertEqual(len(report['cross_validation_deltaE76']), 24)
        self.assertLess(report['cross_validation_mean'], .5)
        profile = dict(format='w9-color/2', matrix=matrix.tolist(), offset=offset.tolist())
        path = self.root/'profile.json'
        path.write_text(json.dumps(profile), encoding='utf-8')
        profile = load_profile(path)
        unseen = rng.integers(60, 170, size=(3, 4, 3)).astype(np.uint8)
        predicted = apply_rgb(unseen, profile)
        expected = encode_srgb(decode_srgb(unseen)@expected_matrix+expected_offset)
        self.assertLessEqual(np.max(abs(predicted.astype(int)-expected.astype(int))), 2)
        v1 = dict(format='w9-color/1', matrix=np.eye(3).tolist())
        np.testing.assert_array_equal(apply_rgb(unseen, v1), unseen)
        path.write_text(json.dumps(dict(profile, offset=[0, 0])), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'offset'):
            load_profile(path)

    def test_korean_episode_images_and_numbered_mp4(self):
        ep = reserve_episode(self.root)
        (ep/'rgb').mkdir()
        image = np.zeros((48, 64, 3), dtype=np.uint8)
        image[:, :, 2] = 200
        rows = []
        for k in range(4):
            name = f'rgb/{k:08d}.png'
            write_image(ep/name, image)
            rows.append(dict(file=name, t_s=k/20))
        np.testing.assert_array_equal(read_image(ep/rows[0]['file']), image)
        self.assertEqual(wrist_image(ep/rows[0]['file']).shape, (256, 256, 3))
        (ep/'frames.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')
        out = create_review(ep)
        self.assertEqual(out.name, '영상1.mp4')
        # Decode through an ASCII path to check the actual video, not only its filename.
        copy = self.root/'decode.mp4'
        copy.write_bytes(out.read_bytes())
        reader = cv2.VideoCapture(str(copy))
        try:
            self.assertTrue(reader.isOpened())
            self.assertEqual(int(reader.get(cv2.CAP_PROP_FRAME_COUNT)), 4)
            ok, frame = reader.read()
            self.assertTrue(ok)
            self.assertEqual(frame.shape, image.shape)
        finally:
            reader.release()
        with self.assertRaises(FileExistsError):
            create_review(ep)

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

    def test_input_hashes_are_portable_between_lf_and_crlf_checkouts(self):
        ep = self.fixture()
        (ep/'color_profile.json').write_bytes(b'{\n  "matrix": []\n}\n')
        expected = {name: hashlib.sha256((ep/name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                    for name in input_hashes(ep)}
        for name in expected:
            path = ep/name
            path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
        self.assertEqual(input_hashes(ep), expected)
        self.assertTrue(input_hashes_match(ep, expected))

    def test_input_hashes_accept_legacy_crlf_reports(self):
        ep = self.fixture()
        recorded = {name: hashlib.sha256((ep/name).read_bytes().replace(b'\r\n', b'\n')
                                        .replace(b'\n', b'\r\n')).hexdigest()
                    for name in input_hashes(ep)}
        self.assertNotEqual(recorded, input_hashes(ep))
        self.assertTrue(input_hashes_match(ep, recorded))
        for name in recorded:
            path = ep/name
            path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
        self.assertTrue(input_hashes_match(ep, recorded))

    def test_input_hashes_reject_substantive_edits_to_any_input(self):
        ep = self.fixture()
        (ep/'color_profile.json').write_bytes(b'{\n  "matrix": []\n}\n')
        canonical = input_hashes(ep)
        legacy = {name: hashlib.sha256((ep/name).read_bytes().replace(b'\r\n', b'\n')
                                      .replace(b'\n', b'\r\n')).hexdigest()
                  for name in canonical}
        for name in canonical:
            with self.subTest(input=name):
                path = ep/name
                original = path.read_bytes()
                path.write_bytes(original + b' ')
                self.assertFalse(input_hashes_match(ep, canonical))
                self.assertFalse(input_hashes_match(ep, legacy))
                path.write_bytes(original)

    def test_input_hashes_require_exact_input_key_set(self):
        ep = self.fixture()
        (ep/'color_profile.json').write_bytes(b'{}\n')
        recorded = input_hashes(ep)
        for missing in recorded:
            with self.subTest(missing=missing):
                self.assertFalse(input_hashes_match(ep, {k: v for k, v in recorded.items() if k != missing}))
        self.assertFalse(input_hashes_match(ep, dict(recorded, extra='unused')))
        self.assertFalse(input_hashes_match(ep, None))
        (ep/'color_profile.json').unlink()
        self.assertFalse(input_hashes_match(ep, recorded))

    def test_export_checks_legacy_hashes_and_rejects_changed_inputs_before_simulator(self):
        ep = self.fixture()
        aligned, report = prepare(ep)
        report['input_sha256'] = {
            name: hashlib.sha256((ep/name).read_bytes().replace(b'\r\n', b'\n')
                                 .replace(b'\n', b'\r\n')).hexdigest()
            for name in report['input_sha256']}
        np.savez_compressed(ep/'aligned.npz', **aligned)
        (ep/'alignment_report.json').write_text(json.dumps(report), encoding='utf-8')
        args = ['export_hdf5', str(ep), '--out', str(self.root/'hdf5'),
                '--real-success', '--layout-confirmed']
        def simulator_unavailable(**kwargs):
            raise RuntimeError('simulator boundary reached')
        with patch('sys.argv', args), patch.dict(os.environ), patch.dict('sys.modules', {
                'preview': SimpleNamespace(create_env=simulator_unavailable)}):
            with self.assertRaisesRegex(RuntimeError, 'simulator boundary reached'):
                export_main()
            with (ep/'robot.jsonl').open('ab') as log:
                log.write(b' ')
            with self.assertRaisesRegex(ValueError, 'Capture inputs changed'):
                export_main()

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

    def test_layout_target_mismatch_is_rejected_before_device_access(self):
        from .capture import main
        layout = self.root/'wrong_target.json'
        layout.write_text(json.dumps(dict(target='green', unit='cm',
            blocks=dict(red=[-2, 3], green=[-4, 1], blue=[-6, 0]))), encoding='utf-8')
        argv = ['capture', '--color', 'red', '--layout', str(layout)]
        with patch('sys.argv', argv), patch('pyrealsense2.context') as context, \
                patch('serial.Serial') as serial, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main()
        self.assertEqual(caught.exception.code, 2)
        context.assert_not_called()
        serial.assert_not_called()

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

    def test_reset_keeps_only_the_last_take_for_alignment(self):
        ep = self.fixture()
        meta_path = ep/'metadata.json'
        meta = json.loads(meta_path.read_text())
        meta['teleop'] = True
        meta_path.write_text(json.dumps(meta), encoding='utf-8')
        path = ep/'robot.jsonl'
        rows = [json.loads(r) for r in path.read_text().splitlines()]
        rows.extend([dict(kind='capture_start', t_s=.1), dict(kind='capture_reset', t_s=.5, discarded_take=True),
                     dict(kind='capture_start', t_s=.9), dict(kind='capture_end', t_s=1.875)])
        rows.sort(key=lambda r: r['t_s'])
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')
        aligned, report = prepare(ep)
        self.assertAlmostEqual(aligned['times'][0], .9)
        self.assertEqual(len(aligned['gripper_actions']), 19)
        self.assertEqual(report['skipped_camera_frame_numbers'], 0)

    def test_reset_button_discards_take_and_resyncs_controller_position(self):
        controls = RecordingControls()
        events, sent = [], []
        keyboard = SimpleNamespace(poll=lambda: None, is_pressed=lambda key: False)
        session = TeleopSession(self.root, time.perf_counter_ns(), threading.Event(), 40,
                               controls=controls, keyboard=keyboard,
                               on_start=lambda: events.append('start'), on_end=lambda: events.append('end'),
                               on_reset=lambda: events.append('reset'))
        self.addCleanup(session.log.close)
        def fake_send(command):
            sent.append(command)
            session.last_motion = pose_of(command) or session.last_motion
            return True
        session.send_gcode = fake_send
        session.wait_idle_at = lambda goal, timeout=120, what='': goal
        session.initial_command = 'G0 X198.67 Y0 Z230.72 A0 B0 C0'
        session.last_motion = [213.67, -20, 75, 0, 0, 5]
        session.script_globals = dict(zip(SCRIPT_POSE, session.last_motion))
        session.initial_ready = True
        controls.set_state('ready')
        controls.draw(np.zeros((480, 640, 3), np.uint8))
        controls.mouse(cv2.EVENT_LBUTTONUP, 30, 510, 0, None)   # START
        session.tick()
        self.assertEqual(controls.state, 'recording')
        controls.mouse(cv2.EVENT_LBUTTONUP, 320, 560, 0, None)  # RESET row
        session.tick()
        # Straight up first, then the original initial pose.
        self.assertEqual(sent, ['G0 X213.670 Y-20.000 Z230.720 A0.000 B0.000 C5.000',
                                'G0 X198.67 Y0 Z230.72 A0 B0 C0'])
        self.assertEqual(controls.state, 'ready')
        self.assertFalse(session.started)
        self.assertEqual([session.script_globals[n] for n in SCRIPT_POSE], [198.67, 0, 230.72, 0, 0, 0])
        controls.request('start')
        session.tick()
        controls.request('end')
        session.tick()
        self.assertEqual(events, ['start', 'reset', 'start', 'end'])
        rows = [json.loads(r) for r in (self.root/'robot.jsonl').read_text().splitlines()]
        self.assertEqual([r['kind'] for r in rows],
                         ['capture_start', 'capture_reset', 'capture_start', 'capture_end'])
        self.assertTrue(rows[1]['discarded_take'])
        controls.set_state('homing')
        controls.request('reset')
        self.assertEqual(controls.pending(), [])

    def test_no_homing_skips_start_home_and_returns_to_initial_pose_on_exit(self):
        class FakeSerial:
            def __init__(self, *args, **kwargs):
                self.lines, self.is_open, self.writes = queue.Queue(), True, []
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
        session = TeleopSession(self.root, time.perf_counter_ns(), threading.Event(), 40, skip_homing=True)
        self.addCleanup(session.log.close)
        self.addCleanup(session.close)
        with patch('serial.Serial', FakeSerial):
            session.open_serial(port='FAKE')
            self.assertTrue(session.send_gcode('$H'))  # original script start
            self.assertTrue(session.send_gcode('G0 X198.67 Y0 Z230.72 A0 B0 C0'))
            self.assertTrue(session.send_gcode('G0 X213.67 Y-20 Z75 A0 B0 C0'))
            session.start_capture()                     # F8 (no preview controls in this test)
            self.assertTrue(session.send_gcode('$H'))  # original script q exit, F9 not pressed
            writes = [w for w in session.ser.writes if w != b'?\n']
        self.assertNotIn(b'$H\n', writes)
        self.assertEqual(writes[-2:], [b'G0 X213.670 Y-20.000 Z230.720 A0.000 B0.000 C0.000\n',
                                       b'G0 X198.67 Y0 Z230.72 A0 B0 C0\n'])
        rows = [json.loads(r) for r in (self.root/'robot.jsonl').read_text().splitlines()]
        kinds = [r['kind'] for r in rows if r['kind'] not in ('state', 'query_timeout')]
        self.assertEqual(kinds, ['gripper_initial', 'homing_skipped', 'command', 'command',
                                 'capture_start', 'capture_end', 'homing_skipped', 'command', 'command'])

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
        session = TeleopSession(self.root, time.perf_counter_ns(), threading.Event(), 40,
                               port='/dev/serial/by-id/test-robot')
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

    def test_buttons_wait_for_fresh_idle_at_initial_pose_and_record_once(self):
        controls = RecordingControls()
        controls.request('start')
        self.assertEqual(controls.pending(), [])
        events = []
        keyboard = SimpleNamespace(poll=lambda: None, is_pressed=lambda key: False)
        session = TeleopSession(self.root, time.perf_counter_ns(), threading.Event(), 40,
                               controls=controls, keyboard=keyboard,
                               on_start=lambda: events.append('start'), on_end=lambda: events.append('end'))
        self.addCleanup(session.log.close)
        session.last_motion = [198.67, 0, 230.72, 0, 0, 0]
        def feed():
            for cart, state, fresh in [
                (session.last_motion, 'Idle', False),
                ([0]*6, 'Idle', True),
                (session.last_motion, 'Run', True),
                *[(session.last_motion, 'Idle', True)]*3,
            ]:
                time.sleep(.01)
                with session.status_condition:
                    session.status_revision += 1
                    query_time = (time.perf_counter_ns()-session.clock_ns)/1e9 if fresh else -1
                    session.latest_status = (cart, state, query_time)
                    session.status_condition.notify_all()
        thread = threading.Thread(target=feed)
        thread.start()
        session.wait_initial_ready(timeout=1)
        thread.join()
        self.assertEqual(controls.state, 'ready')
        controls.draw(np.zeros((480, 640, 3), np.uint8))
        controls.mouse(cv2.EVENT_LBUTTONUP, 30, 510, 0, None)
        session.tick()
        self.assertEqual(controls.state, 'recording')
        controls.mouse(cv2.EVENT_LBUTTONUP, 500, 510, 0, None)
        session.tick()
        self.assertEqual(controls.state, 'ended')
        controls.request('start')
        session.tick()
        self.assertEqual(events, ['start', 'end'])
        controls.set_state('homing')
        session.initial_ready = False
        with self.assertRaises(TimeoutError):
            session.wait_initial_ready(timeout=.02)
        self.assertEqual(controls.state, 'homing')

    def test_teleop_linux_port_overrides_original_controller_port(self):
        session = TeleopSession(self.root, time.perf_counter_ns(), threading.Event(), 40,
                               port='/dev/serial/by-id/test-robot')
        self.addCleanup(session.log.close)
        self.addCleanup(session.close)
        with patch('serial.Serial') as serial, patch('threading.Thread'):
            session.open_serial(port='COM3', baudrate=115200)
            self.assertEqual(serial.call_args.kwargs['port'], '/dev/serial/by-id/test-robot')
            session.open_serial('COM3', 115200)
            self.assertEqual(serial.call_args.args[0], '/dev/serial/by-id/test-robot')
            self.assertNotIn('port', serial.call_args.kwargs)

    @unittest.skipUnless(os.name == 'posix', 'Linux/SSH terminal input')
    def test_terminal_keys_fragmented_arrows_and_restore_after_error(self):
        import pty
        import termios
        from .terminal_keyboard import TerminalKeyboard
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        stream = os.fdopen(slave, 'rb', buffering=0)
        self.addCleanup(stream.close)
        saved = termios.tcgetattr(slave)
        with self.assertRaisesRegex(RuntimeError, 'test interruption'):
            with TerminalKeyboard(stream) as keys:
                os.write(master, b'\x1b[')
                keys.poll()
                self.assertFalse(keys.is_pressed('up'))
                os.write(master, b'Aw[')
                keys.poll()
                self.assertTrue(keys.is_pressed('up'))
                self.assertTrue(keys.is_pressed('w'))
                self.assertFalse(keys.is_pressed('w'))
                self.assertTrue(keys.is_pressed('f8'))
                os.write(master, b'\x1b[20~')
                keys.poll()
                self.assertTrue(keys.is_pressed('f9'))
                os.write(master, b'\x1b[15~')  # Unsupported F5 must not move J4/J5.
                keys.poll()
                self.assertFalse(keys.is_pressed('1'))
                self.assertFalse(keys.is_pressed('5'))
                raise RuntimeError('test interruption')
        self.assertEqual(termios.tcgetattr(slave), saved)

    def test_original_controller_uses_injected_keyboard_without_global_hooks(self):
        from unittest.mock import Mock
        keyboard = Mock()
        keyboard.is_pressed.side_effect = lambda key: key == 'q'
        session = Mock()
        # Run the actual controller with fake I/O: every setup/home/exit command
        # goes to the recorder mock, never to real hardware.
        with patch.dict('sys.modules', {'keyboard': None}), patch('serial.Serial') as serial, \
                patch('time.sleep'):
            runpy.run_path(str(REPO/'robot/inverse_kinematics.py'),
                           init_globals={'_w9_session': session, '_w9_keyboard': keyboard})
        serial.assert_not_called()
        session.tick.assert_called_once()
        self.assertEqual(session.send_gcode.call_args_list[-1].args, ('M30',))

    @unittest.skipUnless(os.name == 'posix', 'OASYS Linux preflight')
    def test_linux_capture_rejects_missing_robot_port_before_device_access(self):
        from .capture import main
        args = ['capture', '--gcode', str(REPO/'trajectories/2026_10_11-w6-pickup-red-s2-e5.gcode'),
                '--reference', str(REPO/'docs/W6/poses/pickup-red-s2.jsonl'),
                '--seed', '2', '--execute']
        error = io.StringIO()
        with patch('sys.argv', args), patch('pyrealsense2.context') as context, \
                patch('serial.Serial') as serial, redirect_stderr(error):
            with self.assertRaises(SystemExit) as caught:
                main()
        self.assertEqual(caught.exception.code, 2)
        self.assertIn('--port', error.getvalue())
        context.assert_not_called()
        serial.assert_not_called()

    @unittest.skipUnless(os.name == 'posix', 'OASYS Linux preflight')
    def test_headless_capture_and_chart_fit_report_gui_requirement(self):
        from .capture import main as capture_main
        from .color_calibration import main as fit_main
        for main, args, hint in [
            (capture_main, ['capture', '--out', 'unused', '--preview'], '--preview'),
            (fit_main, ['color_calibration', 'fit', '--image', 'unused.png',
                        '--camera-metadata', 'unused.json', '--out', 'unused-profile.json'], '--corners'),
        ]:
            with self.subTest(command=args[0]), patch('sys.argv', args), \
                    patch('sys.platform', 'linux'), patch.dict(os.environ, {}, clear=True), \
                    patch('cv2.imshow') as show, redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit) as caught:
                    main()
                self.assertEqual(caught.exception.code, 2)
                self.assertIn(hint, error.getvalue())
                show.assert_not_called()

    def test_capture_keeps_colour_correction_separate_from_sdk_stream_profile(self):
        import pyrealsense2 as rs
        from .capture import main as capture_main
        intr = SimpleNamespace(width=640, height=480, fx=1., fy=1., ppx=0., ppy=0.,
                               coeffs=[0.]*5, model='test')
        stream = SimpleNamespace(get_intrinsics=lambda: intr)
        device = SimpleNamespace(get_info=lambda key: 'D405' if key == rs.camera_info.name else 'TEST_SERIAL')
        sensor = SimpleNamespace(supports=lambda option: True, get_option=lambda option: 10.,
                                 set_option=lambda option, value: None)
        profile = SimpleNamespace(get_stream=lambda kind: SimpleNamespace(as_video_stream_profile=lambda: stream),
                                  get_device=lambda: SimpleNamespace(query_sensors=lambda: [sensor]))
        frame = SimpleNamespace(get_data=lambda: np.zeros((480, 640, 3), np.uint8),
                                get_timestamp=lambda: time.perf_counter()*1000,
                                get_frame_timestamp_domain=lambda: 'test', get_frame_number=lambda: 1)
        def wait_for_frames(timeout):
            time.sleep(.001)
            return SimpleNamespace(get_color_frame=lambda: frame)
        pipeline = SimpleNamespace(start=lambda config: profile, wait_for_frames=wait_for_frames, stop=lambda: None)
        config = SimpleNamespace(enable_device=lambda serial: None, enable_stream=lambda *args: None)
        video_writer = cv2.VideoWriter
        for mode in ('raw', 'corrected', 'teleop'):
            corrected = mode != 'raw'
            teleop = mode == 'teleop'
            with self.subTest(corrected=corrected):
                out = self.root/('with_teleop' if teleop else 'with_profile') if corrected else self.root/'recordings'/'영상1'
                argv = ['capture', '--seconds', '.02']
                argv += ['--out', str(out)] if corrected else ['--out-root', str(out.parent)]
                if corrected:
                    correction = self.root/'correction.json'
                    correction.write_text(json.dumps(dict(format='w9-color/2', matrix=np.eye(3).tolist(), offset=[0,0,0],
                        camera_serial='TEST_SERIAL', width=640, height=480, fps=30,
                        camera_options={'Exposure': 10., 'White Balance': 10.})), encoding='utf-8')
                    argv += ['--color-profile', str(correction)]
                if teleop:
                    argv += ['--teleop', '--seed', '2', '--execute', '--port', 'FAKE',
                             '--reference', str(REPO/'docs/W6/poses/pickup-red-s2.jsonl'),
                             '--mapping-gcode', str(REPO/'trajectories/2026_10_11-w6-pickup-red-s2-e5.gcode')]
                    layout = self.root/'layout_input.json'
                    layout.write_text(json.dumps(dict(target='red', unit='cm',
                        blocks=dict(red=[-2, 3], green=[-4, 1], blue=[-6, 0]))), encoding='utf-8')
                    photo = self.root/'initial_photo.png'
                    write_image(photo, np.full((48, 64, 3), 100, np.uint8))
                    argv += ['--layout', str(layout), '--layout-photo', str(photo)]
                def fake_teleop(*args, controls, on_start, on_end, **kwargs):
                    time.sleep(.02)
                    self.assertEqual(list((out/'rgb').glob('*.png')), [])
                    self.assertEqual((out/'frames.jsonl').read_text(), '')
                    self.assertEqual(controls.state, 'homing')
                    saved_layout = json.loads((out/'layout.json').read_text(encoding='utf-8'))
                    self.assertEqual(saved_layout['target'], 'red')
                    self.assertEqual(saved_layout['blocks']['green'], [-4, 1])
                    self.assertEqual((out/'layout.png').read_bytes(), photo.read_bytes())
                    controls.set_state('ready')
                    on_start()
                    time.sleep(.02)
                    on_end()
                    time.sleep(.02)  # Let any PNG already being written finish.
                    count = len(list((out/'rgb').glob('*.png')))
                    self.assertGreater(count, 0)
                    time.sleep(.02)
                    self.assertEqual(len(list((out/'rgb').glob('*.png'))), count)
                # The fake camera runs much faster than a D405. Use its requested
                # 30 fps for the real codec, and simulate the mocked teleop's TTY.
                with patch('sys.argv', argv), patch('sys.stdin.isatty', return_value=True), \
                        patch.object(cv2, 'VideoWriter', side_effect=lambda path, codec, fps, size:
                                     video_writer(path, codec, 30., size)), \
                        patch.object(rs, 'context', return_value=SimpleNamespace(
                        query_devices=lambda: [device])), patch.object(rs, 'pipeline', return_value=pipeline), \
                        patch.object(rs, 'config', return_value=config), \
                        (patch('docs.W9.d405.teleop.run', side_effect=fake_teleop) if teleop else nullcontext()):
                    capture_main()
                metadata = json.loads((out/'metadata.json').read_text(encoding='utf-8'))
                self.assertTrue(metadata['complete'])
                self.assertGreater(len(list((out/'rgb').glob('*.png'))), 0)
                self.assertEqual((out/'color_profile.json').exists(), corrected)
                if corrected:
                    self.assertEqual(metadata['profile_settle_frames'], 15)
                self.assertTrue((out/('review.mp4' if corrected else '영상1.mp4')).is_file())


if __name__ == '__main__':
    unittest.main(verbosity=2)
