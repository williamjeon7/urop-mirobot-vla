"""Independent tests for immutable layout measurements and pickup reviews."""
import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from .layout_record import (PAPER_FRAME, create_layout, copy_layout_template,
                            load_capture_layout, record_outcome)


class LayoutRecordTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.episode = self.root/'episode'
        self.episode.mkdir()
        (self.episode/'metadata.json').write_text('{"color":"red","complete":true}', encoding='utf-8')
        for name in ['robot.jsonl', 'frames.jsonl', 'existing.hdf5']:
            (self.episode/name).write_bytes(b'preserve original bytes\r\n')
        (self.episode/'rgb').mkdir()
        (self.episode/'rgb'/'frame.png').write_bytes(b'original frame')
        self.original = {str(path.relative_to(self.episode)): path.read_bytes()
                         for path in self.episode.rglob('*') if path.is_file()}
        ok, encoded = cv2.imencode('.png', np.full((10, 20, 3), 100, np.uint8))
        self.assertTrue(ok)
        self.photo = self.root/'photo.jpg'  # Deliberately misleading suffix.
        self.photo.write_bytes(encoded.tobytes())
        self.coordinates = dict(red=[-2, 3], green=[-5.5, -1], blue=[-8, 0])

    def assert_originals_unchanged(self):
        for name, contents in self.original.items():
            self.assertEqual((self.episode/name).read_bytes(), contents)

    def test_manual_layout_photo_true_extension_and_originals_preserved(self):
        path = create_layout(self.episode, self.coordinates, self.photo)
        layout = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(layout['target'], 'red')
        self.assertEqual(layout['photo'], 'layout.png')
        self.assertEqual(layout['blocks']['green'], [-5.5, -1.0])
        self.assertEqual(layout['coordinate_frame']['robot_base_registration_status'], 'not_measured')
        self.assertIsNone(layout['coordinate_frame']['robot_base_registration'])
        self.assertFalse(layout['independent_measurement_verified'])
        self.assertIn('not verified', layout['photo_provenance']['view'])
        self.assertEqual((self.episode/'layout.png').read_bytes(), self.photo.read_bytes())
        self.assert_originals_unchanged()

    def test_mismatch_invalid_coords_and_bad_photo_write_nothing(self):
        for coordinates, photo, target in [
            (self.coordinates, self.photo, 'green'),
            (dict(self.coordinates, red=[float('nan'), 0]), self.photo, None),
            (dict(self.coordinates, blue=[float('inf'), 0]), self.photo, None),
            (dict(red=[0, 0], blue=[1, 2]), self.photo, None),
            (dict(self.coordinates, green=[True, 0]), self.photo, None),
            (self.coordinates, self.episode/'existing.hdf5', None),
        ]:
            with self.subTest(coordinates=coordinates, target=target), self.assertRaises(ValueError):
                create_layout(self.episode, coordinates, photo, target)
        self.assertFalse((self.episode/'layout.json').exists())
        self.assertFalse((self.episode/'layout.png').exists())
        self.assert_originals_unchanged()

    def test_existing_layout_or_photo_is_never_overwritten(self):
        path = create_layout(self.episode, self.coordinates, self.photo)
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            create_layout(self.episode, dict(self.coordinates, red=[9, 9]), self.photo)
        self.assertEqual(path.read_bytes(), before)
        path.unlink()
        with self.assertRaises(FileExistsError):
            create_layout(self.episode, self.coordinates, self.photo)
        self.assertFalse(path.exists())

    def test_outcome_is_separate_target_checked_and_immutable(self):
        with self.assertRaises(ValueError):
            record_outcome(self.episode, True, target='green')
        with self.assertRaises(ValueError):
            record_outcome(self.episode, 'yes')
        path = record_outcome(self.episode, False)
        document = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(document['target'], 'red')
        self.assertIs(document['real_success'], False)
        with self.assertRaises(FileExistsError):
            record_outcome(self.episode, True)
        self.assert_originals_unchanged()

    def test_same_layout_can_be_copied_for_a_different_target(self):
        template = create_layout(self.episode, self.coordinates, self.photo)
        second = self.root/'second'
        second.mkdir()
        (second/'metadata.json').write_text('{"color":"green"}', encoding='utf-8')
        result = copy_layout_template(second, template)
        self.assertEqual(json.loads(result.read_text())['target'], 'green')
        self.assertEqual((second/'layout.png').read_bytes(), self.photo.read_bytes())
        self.assert_originals_unchanged()

    def test_capture_template_preflight_with_relative_photo_or_override(self):
        template = self.root/'manual.json'
        document = dict(target='red', unit='cm', blocks=self.coordinates, photo=self.photo.name)
        template.write_text(json.dumps(document), encoding='utf-8')
        coordinates, photo = load_capture_layout(template, 'red')
        self.assertEqual(coordinates, self.coordinates)
        self.assertEqual(photo, self.photo)
        document.pop('photo')
        document['coordinate_frame'] = PAPER_FRAME
        template.write_text(json.dumps(document), encoding='utf-8')
        self.assertEqual(load_capture_layout(template, 'red', self.photo)[1], self.photo)
        self.assertFalse((self.episode/'layout.json').exists())
        self.assert_originals_unchanged()

    def test_capture_template_rejects_mismatch_estimates_unknown_frame_and_missing_photo(self):
        template = self.root/'manual.json'
        base = dict(target='red', unit='cm', blocks=self.coordinates, photo=self.photo.name)
        for changes in [dict(target='green'), dict(unit='mm'), dict(estimated=True),
                        dict(coordinate_source='estimated_from_initial_frame'),
                        dict(source='estimated_from_initial_frame'),
                        dict(coordinate_frame={'id': 'robot_base'}), dict(photo='')]:
            with self.subTest(changes=changes):
                template.write_text(json.dumps(dict(base, **changes)), encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_capture_layout(template, 'red')
        self.assert_originals_unchanged()


if __name__ == '__main__':
    unittest.main(verbosity=2)
