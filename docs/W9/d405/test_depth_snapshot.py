"""Depth snapshot geometry/metadata tests; never use a camera or robot."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import cv2
import numpy as np

from .depth_snapshot import capture_snapshot, measure_points, offline_points


def fake_sdk(depth_scale=.001):
    calls = []
    depth_intr = SimpleNamespace(width=3, height=2, fx=10., fy=20., ppx=1., ppy=.5,
                                 coeffs=[0.]*5, model='distortion.none')
    color_intr = SimpleNamespace(width=5, height=4, fx=99., fy=99., ppx=2., ppy=1.5,
                                 coeffs=[0.]*5, model='distortion.none')

    class Profile:
        def __init__(self, kind, intrinsics):
            self.kind, self.intrinsics = kind, intrinsics
        def as_video_stream_profile(self): return self
        def width(self): return self.intrinsics.width
        def height(self): return self.intrinsics.height
        def fps(self): return 30
        def format(self): return 'z16' if self.kind == 'depth' else 'rgb8'
        def stream_type(self): return self.kind
        def get_intrinsics(self): return self.intrinsics
        def get_extrinsics_to(self, other):
            return SimpleNamespace(rotation=[1., 0., 0., 0., 1., 0., 0., 0., 1.],
                                   translation=[.01, 0., 0.])

    class Frame:
        def __init__(self, data, number): self.data, self.number = data, number
        def get_data(self): return self.data
        def get_timestamp(self): return self.number*33.3
        def get_frame_number(self): return self.number
        def get_frame_timestamp_domain(self): return 'hardware_clock'

    class Pipeline:
        def __init__(self): self.number, self.stopped = 0, False
        def start(self, config):
            calls.append(('start',))
            device = SimpleNamespace(first_depth_sensor=lambda: SimpleNamespace(get_depth_scale=lambda: depth_scale))
            return SimpleNamespace(get_stream=lambda kind: Profile(kind, depth_intr if kind == 'depth' else color_intr),
                                   get_device=lambda: device)
        def wait_for_frames(self, timeout):
            self.number += 1
            depth = Frame(np.full((2, 3), 1000+self.number, np.uint16), self.number)
            color = Frame(np.full((4, 5, 3), [10, 20, 30], np.uint8), self.number+100)
            return SimpleNamespace(get_depth_frame=lambda: depth, get_color_frame=lambda: color)
        def stop(self): self.stopped = True

    pipeline = Pipeline()
    device = SimpleNamespace(get_info=lambda key: 'RealSense D405' if key == 'name' else 'SERIAL')

    def deproject(intrinsics, pixel, depth):
        calls.append(('deproject', intrinsics.fx, tuple(pixel), depth))
        return [(pixel[0]-intrinsics.ppx)/intrinsics.fx*depth,
                (pixel[1]-intrinsics.ppy)/intrinsics.fy*depth, depth]

    sdk = SimpleNamespace(context=lambda: SimpleNamespace(query_devices=lambda: [device]),
                          camera_info=SimpleNamespace(name='name', serial_number='serial'),
                          stream=SimpleNamespace(depth='depth', color='color'),
                          format=SimpleNamespace(z16='z16', rgb8='rgb8'),
                          pipeline=lambda: pipeline,
                          config=lambda: SimpleNamespace(enable_device=lambda serial: calls.append(('device', serial)),
                                                         enable_stream=lambda *args: calls.append(('stream', *args))),
                          intrinsics=lambda: SimpleNamespace(), distortion=SimpleNamespace(none='none'),
                          rs2_deproject_pixel_to_point=deproject)
    return sdk, pipeline, calls


class DepthSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_capture_preserves_native_depth_and_color_geometry_and_timestamps(self):
        sdk, pipeline, calls = fake_sdk()
        path = capture_snapshot(self.root/'snapshot', frames=3, settle_frames=1, sdk=sdk)
        metadata = json.loads(path.read_text())
        self.assertTrue(metadata['complete'])
        self.assertFalse(metadata['aligned'])
        self.assertFalse(metadata['robot_io'])
        self.assertIsNone(metadata['camera_to_robot'])
        self.assertEqual(metadata['depth_intrinsics']['width'], 3)
        self.assertEqual(metadata['color_intrinsics']['width'], 5)
        self.assertEqual(metadata['depth_scale_m_per_unit'], .001)
        self.assertTrue(metadata['depth_preview_is_visualization_only'])
        self.assertTrue((path.parent/'depth_preview.png').is_file())
        self.assertEqual(metadata['factory_depth_to_color']['translation_m'], [.01, 0., 0.])
        self.assertNotEqual(metadata['timestamps'][0]['depth_number'], metadata['timestamps'][0]['color_number'])
        stack = np.load(path.parent/'depth_stack.npy', allow_pickle=False)
        self.assertEqual(stack.shape, (3, 2, 3))
        self.assertEqual(stack.dtype, np.uint16)
        image = cv2.imdecode(np.fromfile(path.parent/'depth_u16.png', dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        np.testing.assert_array_equal(image, stack[1])
        color = cv2.imdecode(np.fromfile(path.parent/'color.png', dtype=np.uint8), cv2.IMREAD_COLOR)
        np.testing.assert_array_equal(color[0, 0], [30, 20, 10])
        self.assertTrue(pipeline.stopped)
        calls.clear()
        with self.assertRaises(FileExistsError):
            capture_snapshot(path.parent, sdk=sdk)
        self.assertEqual(calls, [])

    def test_camera_failure_retains_incomplete_metadata_and_stops_pipeline(self):
        sdk, pipeline, _ = fake_sdk(depth_scale=0)
        with self.assertRaisesRegex(ValueError, 'depth scale'):
            capture_snapshot(self.root/'bad', frames=1, settle_frames=0, sdk=sdk)
        metadata = json.loads((self.root/'bad'/'metadata.json').read_text())
        self.assertFalse(metadata['complete'])
        self.assertIn('error', metadata)
        self.assertTrue(pipeline.stopped)

    def test_each_valid_native_pixel_is_deprojected_and_zero_depth_is_ignored(self):
        stack = np.full((2, 3, 3), 1000, np.uint16)
        stack[0, 0, 0] = 0
        calls = []
        def deproject(pixel, depth):
            calls.append((tuple(pixel), depth))
            return [(pixel[0]-1)*.001, (pixel[1]-1)*.001, depth]
        result = measure_points(stack, .001, {'origin': [1, 1]}, deproject,
                                radius=1, min_valid=10, max_spread_m=.01)['origin']
        self.assertTrue(result['accepted'])
        self.assertEqual(result['valid_count'], 17)
        self.assertEqual(len(calls), 17)
        self.assertGreater(len(set(pixel for pixel, _ in calls)), 1)
        np.testing.assert_allclose(result['xyz_camera_m'], [0., 0., 1.])

    def test_missing_and_mixed_surface_depth_are_not_accepted(self):
        missing = np.zeros((2, 3, 3), np.uint16)
        deproject = lambda pixel, depth: [0, 0, depth]
        point = measure_points(missing, .001, {'origin': [1, 1]}, deproject,
                               min_valid=1)['origin']
        self.assertFalse(point['accepted'])
        self.assertIsNone(point['xyz_camera_m'])
        mixed = np.stack([np.full((3, 3), value, np.uint16) for value in (100, 500)])
        point = measure_points(mixed, .001, {'edge': [1, 1]}, deproject,
                               radius=1, min_valid=10, max_spread_m=.01)['edge']
        self.assertFalse(point['accepted'])
        self.assertEqual(point['status'], 'unstable_or_mixed_surfaces')

    def test_points_reject_pixel_errors_and_non_uint16_depth(self):
        data = np.ones((2, 3, 3), np.uint16)
        for pixel in ([3, 0], [0, -1], [1.5, 1], [True, 0]):
            with self.subTest(pixel=pixel), self.assertRaises(ValueError):
                measure_points(data, .001, {'origin': pixel}, lambda pixel, depth: [0, 0, depth])
        with self.assertRaises(ValueError):
            measure_points(data.astype(float), .001, {'origin': [0, 0]}, lambda pixel, depth: [0, 0, depth])

    def test_offline_points_uses_saved_native_depth_intrinsics_and_never_overwrites(self):
        sdk, _, calls = fake_sdk()
        capture_snapshot(self.root/'snapshot', frames=3, settle_frames=0, sdk=sdk)
        pixels = self.root/'pixels.json'
        pixels.write_text('{"origin":[1,1]}')
        out = self.root/'points.json'
        report = offline_points(self.root/'snapshot', pixels, out,
                                radius=0, min_valid=2, sdk=sdk)
        self.assertTrue(report['points']['origin']['accepted'])
        self.assertEqual(report['point_frame'], 'depth_camera_optical')
        self.assertIsNone(report['camera_to_robot'])
        self.assertTrue(all(call[1] == 10 for call in calls if call[0] == 'deproject'))
        with self.assertRaises(FileExistsError):
            offline_points(self.root/'snapshot', pixels, out, sdk=sdk)


if __name__ == '__main__':
    unittest.main(verbosity=2)
