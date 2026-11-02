"""Geometric contracts for image-derived layouts; no physical devices needed."""
import unittest

import cv2
import numpy as np

try:
    import pyrealsense2  # noqa: F401
except ImportError:
    pyrealsense2 = None

from tools.w9_layout_geometry import fit_table_pose, paper_to_pixel, pixel_to_paper, pixel_rays
from tools.reconstruct_w9_layouts import boundary_samples, colored_contour, cube_vertices, fit_cube


@unittest.skipIf(pyrealsense2 is None, 'RealSense SDK geometry package is required')
class LayoutGeometryTests(unittest.TestCase):
    def setUp(self):
        self.intr = dict(width=640, height=480, fx=392.20758, fy=391.23218,
                         ppx=318.44736, ppy=236.28888,
                         coeffs=[-.0503479, .0518655, -.00071152, .00036072, -.0171521],
                         model='distortion.inverse_brown_conrady')
        # +X image-up, +Y image-left, +Z up, with the camera 25 cm above paper.
        self.R = np.array([[0., -1., 0.], [-1., 0., 0.], [0., 0., -1.]])
        self.center = np.array([-5., 2., 25.])
        self.t = -self.R @ self.center

    def test_inverse_brown_sdk_pixel_ray_roundtrip(self):
        pixels = np.array([[20., 180.], [318., 236.], [610., 465.]])
        rays = pixel_rays(pixels, self.intr)
        camera_points = rays * 20.
        paper_points = (camera_points - self.t) @ self.R
        recovered = paper_to_pixel(paper_points, self.intr, self.R, self.t)
        np.testing.assert_allclose(recovered, pixels, atol=1e-3)

    def test_pose_fit_recovers_held_out_grid_points(self):
        # A tilted view checks the plane pose rather than only an axis-aligned case.
        self.R = cv2.Rodrigues(np.array([.07, -.04, .02]))[0] @ self.R
        self.t = -self.R @ self.center
        xy = np.array([[x, y] for x in (-15., -5., 5.) for y in (-10., 0., 10.)])
        pixels = paper_to_pixel(np.column_stack((xy, np.zeros(len(xy)))),
                                self.intr, self.R, self.t)
        R, t, report = fit_table_pose(xy, pixels, self.intr)
        np.testing.assert_allclose(-R.T @ t, self.center, atol=1e-3)
        held_out = np.array([[-12., -3., 0.], [-2., 7., 0.], [2., -6., 0.]])
        held_pixels = paper_to_pixel(held_out, self.intr, self.R, self.t)
        reconstructed = pixel_to_paper(held_pixels, self.intr, R, t)
        np.testing.assert_allclose(reconstructed, held_out[:, :2], atol=1e-3)
        self.assertLess(report['reprojection_rms_px'], 1e-3)

    def test_height_correction_recovers_cube_footprint(self):
        top = np.array([[-12., -7., 2.], [-3., 8., 2.]])
        pixels = paper_to_pixel(top, self.intr, self.R, self.t)
        corrected = pixel_to_paper(pixels, self.intr, self.R, self.t, height_cm=2.)
        uncorrected = pixel_to_paper(pixels, self.intr, self.R, self.t)
        np.testing.assert_allclose(corrected, top[:, :2], atol=1e-3)
        self.assertGreater(np.max(np.linalg.norm(uncorrected - top[:, :2], axis=1)), .5)

    def test_single_point_shapes_and_scalar_height(self):
        pixel = paper_to_pixel([-4., 1., 2.], self.intr, self.R, self.t)
        self.assertEqual(pixel.shape, (2,))
        self.assertEqual(pixel_rays(pixel, self.intr).shape, (3,))
        np.testing.assert_allclose(pixel_to_paper(pixel, self.intr, self.R, self.t, 2.),
                                   [-4., 1.], atol=1e-3)

    def test_rotated_cube_all_face_silhouette_recovers_footprint(self):
        # The observed silhouette includes top AND visible sides. Treating its
        # centroid as a top-face center would therefore use the wrong height.
        R = cv2.Rodrigues(np.array([.08, -.05, .03]))[0] @ self.R
        t = -R @ self.center
        for x, y, yaw in [(-12., 7., 23.), (-9., -5., 61.), (-14., 0., 3.)]:
            with self.subTest(x=x, y=y, yaw=yaw):
                pixels = paper_to_pixel(cube_vertices(x, y, yaw), self.intr, R, t)
                hull = cv2.convexHull(pixels.astype(np.float32)).reshape(-1, 2)
                contour = boundary_samples(hull, count=12)
                estimate = fit_cube(contour, self.intr, R, t)
                np.testing.assert_allclose(estimate['xy_cm'], [x, y], atol=.03)
                yaw_error = abs((estimate['yaw_mod_90_deg'] - yaw + 45) % 90 - 45)
                self.assertLess(yaw_error, .5)
                self.assertLess(estimate['silhouette_rms_virtual_px'], .15)

    def test_green_threshold_retains_low_saturation_faces(self):
        # Low saturation was the actual source of truncated green blocks in the
        # first-pass reconstruction; the full face must remain in the mask.
        hsv = np.zeros((480, 640, 3), np.uint8)
        hsv[:, :, 2] = 200
        hsv[280:321, 280:316] = [60, 30, 150]
        image = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        contour = colored_contour(image, 'green')
        self.assertEqual(cv2.boundingRect(contour.astype(np.int32)), (280, 280, 36, 41))
        with self.assertRaisesRegex(ValueError, 'got 0'):
            colored_contour(image, 'green', saturation=65)

    def test_rejects_missing_ambiguous_and_incompatible_silhouettes(self):
        image = np.full((480, 640, 3), 160, np.uint8)
        with self.assertRaisesRegex(ValueError, 'got 0'):
            colored_contour(image, 'blue')
        image[260:300, 100:130] = [200, 50, 20]
        image[260:300, 400:430] = [200, 50, 20]
        with self.assertRaisesRegex(ValueError, 'got 2'):
            colored_contour(image, 'blue')
        incompatible = np.array([[250., 250.], [340., 250.],
                                 [340., 340.], [250., 340.]])
        with self.assertRaisesRegex(ValueError, 'Poor 2cm cube'):
            fit_cube(boundary_samples(incompatible), self.intr, self.R, self.t)

    def test_rejects_invalid_and_behind_camera_geometry(self):
        with self.assertRaisesRegex(ValueError, 'above the paper'):
            pixel_to_paper([318., 236.], self.intr, np.eye(3), [0., 0., 25.])
        with self.assertRaisesRegex(ValueError, 'behind the camera'):
            pixel_to_paper([318., 236.], self.intr, self.R, self.t, 30.)
        with self.assertRaisesRegex(ValueError, 'behind the camera'):
            paper_to_pixel([-5., 2., 30.], self.intr, self.R, self.t)
        with self.assertRaisesRegex(ValueError, 'collinear'):
            fit_table_pose([[0., 0.], [1., 0.], [2., 0.], [3., 0.]],
                           [[100., 100.], [120., 100.], [140., 100.], [160., 100.]], self.intr)
        with self.assertRaisesRegex(ValueError, 'finite'):
            pixel_rays([float('nan'), 0.], self.intr)


if __name__ == '__main__':
    unittest.main()
