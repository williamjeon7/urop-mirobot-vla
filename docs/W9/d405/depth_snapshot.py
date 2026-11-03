"""Calibration-only native D405 RGB/depth evidence and offline 3-D sampling.

Never opens a robot port or changes the training capture pipeline. Native depth
pixels and native colour pixels are different grids; this tool does not align
them or infer a camera-to-robot/table transform.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time

import numpy as np

from .capture_storage import write_image


def _intrinsics(intrinsics):
    return {key: getattr(intrinsics, key) for key in ('width', 'height', 'fx', 'fy', 'ppx', 'ppy')} | {
        'model': str(intrinsics.model), 'coeffs': list(intrinsics.coeffs),
    }


def _extrinsics(extrinsics):
    return {
        'rotation': list(extrinsics.rotation), 'rotation_storage': 'RealSense SDK column-major 3x3',
        'translation_m': list(extrinsics.translation),
    }


def _stream(profile):
    return {'width': profile.width(), 'height': profile.height(), 'fps': profile.fps(),
            'format': str(profile.format()), 'stream_type': str(profile.stream_type())}


def capture_snapshot(out, serial=None, frames=30, settle_frames=30,
                     width=640, height=480, fps=30, sdk=None):
    """Save unaligned native streams. This function never performs robot I/O."""
    if not isinstance(frames, int) or isinstance(frames, bool) or frames < 1 or settle_frames < 0:
        raise ValueError('Need at least one saved frame and nonnegative settling frames.')
    if min(width, height, fps) <= 0:
        raise ValueError('Positive stream dimensions and fps are required.')
    out = Path(out)
    # Refuse overwrite before starting any camera operation.
    out.mkdir(parents=True, exist_ok=False)
    metadata = {'format': 'w9-native-depth/1', 'complete': False,
                'purpose': 'calibration_only_not_training_capture',
                'aligned': False,
                'pixel_warning': 'Native depth and colour pixel grids are different; never reuse colour [u,v] directly as depth [u,v].',
                'camera_optical_axes': {'x': 'right', 'y': 'down', 'z': 'forward'},
                'camera_to_robot': None, 'camera_to_table': None,
                'robot_io': False, 'timestamps': []}
    pipeline = None
    started = False
    try:
        if sdk is None:
            import pyrealsense2 as sdk
        devices = list(sdk.context().query_devices())
        candidates = [device for device in devices
                      if 'D405' in device.get_info(sdk.camera_info.name)
                      and (serial is None or device.get_info(sdk.camera_info.serial_number) == serial)]
        if len(candidates) != 1:
            raise ValueError(f'Expected one selected D405, found {len(candidates)}. Specify --serial or check USB.')
        serial = candidates[0].get_info(sdk.camera_info.serial_number)
        pipeline = sdk.pipeline()
        config = sdk.config()
        config.enable_device(serial)
        config.enable_stream(sdk.stream.depth, width, height, sdk.format.z16, fps)
        config.enable_stream(sdk.stream.color, width, height, sdk.format.rgb8, fps)
        profile = pipeline.start(config)
        started = True
        depth_profile = profile.get_stream(sdk.stream.depth).as_video_stream_profile()
        color_profile = profile.get_stream(sdk.stream.color).as_video_stream_profile()
        depth_scale = float(profile.get_device().first_depth_sensor().get_depth_scale())
        if not math.isfinite(depth_scale) or depth_scale <= 0:
            raise ValueError('Camera reported an invalid depth scale.')
        metadata.update(serial=serial, depth_scale_m_per_unit=depth_scale,
                        depth_intrinsics=_intrinsics(depth_profile.get_intrinsics()),
                        color_intrinsics=_intrinsics(color_profile.get_intrinsics()),
                        factory_depth_to_color=_extrinsics(depth_profile.get_extrinsics_to(color_profile)),
                        factory_color_to_depth=_extrinsics(color_profile.get_extrinsics_to(depth_profile)),
                        depth_profile=_stream(depth_profile), color_profile=_stream(color_profile),
                        settle_frames=settle_frames, requested_saved_frames=frames)
        for _ in range(settle_frames):
            pipeline.wait_for_frames(5000)
        depths = []
        representative_color = None
        representative_index = frames//2
        for index in range(frames):
            pair = pipeline.wait_for_frames(5000)
            receipt_ns = time.perf_counter_ns()
            depth = pair.get_depth_frame()
            color = pair.get_color_frame()
            if not depth or not color:
                raise RuntimeError('A frameset did not contain both native depth and colour.')
            depth_array = np.asanyarray(depth.get_data())
            if depth_array.dtype != np.uint16 or depth_array.shape != (
                    metadata['depth_intrinsics']['height'], metadata['depth_intrinsics']['width']):
                raise ValueError('Unexpected native Z16 depth dimensions or dtype.')
            depths.append(depth_array.copy())
            if index == representative_index:
                representative_color = np.asanyarray(color.get_data()).copy()
            metadata['timestamps'].append({
                'index': index, 'host_receipt_perf_counter_ns': receipt_ns,
                'depth_device_ms': depth.get_timestamp(), 'depth_number': depth.get_frame_number(),
                'depth_timestamp_domain': str(depth.get_frame_timestamp_domain()),
                'color_device_ms': color.get_timestamp(), 'color_number': color.get_frame_number(),
                'color_timestamp_domain': str(color.get_frame_timestamp_domain()),
            })
        stack = np.stack(depths)
        np.save(out/'depth_stack.npy', stack, allow_pickle=False)
        write_image(out/'depth_u16.png', stack[representative_index])
        import cv2
        write_image(out/'color.png', cv2.cvtColor(representative_color, cv2.COLOR_RGB2BGR))
        native = stack[representative_index]
        nonzero = native[native > 0]
        low, high = (np.percentile(nonzero, [2, 98]).tolist() if nonzero.size else [0., 1.])
        high = max(high, low+1.)
        view = cv2.applyColorMap(np.rint(np.clip((native.astype(float)-low)/(high-low), 0, 1)*255).astype(np.uint8),
                                cv2.COLORMAP_TURBO)
        view[native == 0] = 0
        write_image(out/'depth_preview.png', view)
        metadata.update(complete=True, saved_frames=len(stack),
                        representative_index=representative_index,
                        depth_stack='depth_stack.npy', depth_image='depth_u16.png', color_image='color.png',
                        depth_preview='depth_preview.png', depth_preview_is_visualization_only=True,
                        depth_preview_range_m=[low*depth_scale, high*depth_scale])
    except BaseException as error:
        metadata['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        if started:
            try:
                pipeline.stop()
            except Exception as error:
                metadata['stop_error'] = str(error)
        (out/'metadata.json').write_text(json.dumps(metadata, indent=2, allow_nan=False), encoding='utf-8')
    return out/'metadata.json'


def _pixels(value, width, height):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('Each point needs native-depth pixel [u,v].')
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise ValueError('Native-depth pixel coordinates must be integer [u,v].')
    u, v = value
    if not (0 <= u < width and 0 <= v < height):
        raise ValueError(f'Native-depth pixel outside image: {value}')
    return u, v


def measure_points(depth_stack, depth_scale, pixels, deproject,
                   radius=2, min_valid=20, min_valid_fraction=.5,
                   max_spread_m=.01, min_depth_m=0., max_depth_m=None):
    """Deproject every valid native-depth sample, then summarize spatial/temporal scatter.

    ``deproject([u,v], z_m)`` must use the saved native depth intrinsics. Returned
    XYZ is the neighbourhood median, not an exact feature intersection or an
    accuracy certificate. Mixed surfaces/edges need manual inspection.
    """
    stack = np.asarray(depth_stack)
    if stack.ndim != 3 or stack.dtype != np.uint16 or len(stack) < 1:
        raise ValueError('Need nonempty (frames,height,width) uint16 native depth data.')
    if not math.isfinite(depth_scale) or depth_scale <= 0:
        raise ValueError('Positive finite depth scale is required.')
    if (not isinstance(radius, int) or isinstance(radius, bool) or radius < 0
            or not isinstance(min_valid, int) or min_valid < 1
            or not 0 <= min_valid_fraction <= 1 or not math.isfinite(max_spread_m) or max_spread_m <= 0
            or not math.isfinite(min_depth_m) or min_depth_m < 0
            or (max_depth_m is not None and (not math.isfinite(max_depth_m) or max_depth_m <= min_depth_m))):
        raise ValueError('Invalid sampling limits.')
    if not isinstance(pixels, dict) or not pixels:
        raise ValueError('Need a nonempty JSON object mapping point names to native-depth [u,v].')
    count, height, width = stack.shape
    result = {}
    for name, pixel in pixels.items():
        u, v = _pixels(pixel, width, height)
        bounds = (max(0, u-radius), min(width, u+radius+1), max(0, v-radius), min(height, v+radius+1))
        x0, x1, y0, y1 = bounds
        sampled = count*(x1-x0)*(y1-y0)
        points, depths = [], []
        for frame in stack:
            for y in range(y0, y1):
                for x in range(x0, x1):
                    raw = int(frame[y, x])
                    z = raw*depth_scale
                    if raw == 0 or z <= min_depth_m or (max_depth_m is not None and z > max_depth_m):
                        continue
                    point = np.asarray(deproject([x, y], z), dtype=float)
                    if point.shape != (3,) or not np.all(np.isfinite(point)):
                        continue
                    points.append(point)
                    depths.append(z)
        valid = len(points)
        row = {'native_depth_pixel': [u, v], 'radius_px': radius, 'sample_count': sampled,
               'valid_count': valid, 'valid_fraction': valid/sampled,
               'xyz_camera_m': None, 'accepted': False,
               'status': 'insufficient_valid_depth',
               'scatter_note': 'Combines temporal noise and spatial neighbourhood variation; not independent measurement accuracy.'}
        if valid >= min_valid and valid/sampled >= min_valid_fraction:
            values = np.asarray(points)
            center = np.median(values, axis=0)
            spread = float(np.percentile(np.linalg.norm(values-center, axis=1), 95))
            row.update(xyz_camera_m=center.tolist(),
                       median_depth_m=float(np.median(depths)),
                       depth_iqr_m=float(np.percentile(depths, 75)-np.percentile(depths, 25)),
                       xyz_mad_m=np.median(abs(values-center), axis=0).tolist(),
                       xyz_p95_radius_m=spread,
                       accepted=spread <= max_spread_m,
                       status='ok' if spread <= max_spread_m else 'unstable_or_mixed_surfaces')
        result[name] = row
    return result


def _restore_intrinsics(data, sdk):
    intrinsics = sdk.intrinsics()
    for key in ('width', 'height', 'fx', 'fy', 'ppx', 'ppy', 'coeffs'):
        setattr(intrinsics, key, data[key])
    name = data['model'].split('.')[-1]
    try:
        intrinsics.model = getattr(sdk.distortion, name)
    except AttributeError as error:
        raise ValueError(f'Unsupported saved depth distortion model: {data["model"]}') from error
    return intrinsics


def offline_points(snapshot, pixels_path, out, radius=2, min_valid=20,
                   max_spread_mm=10., min_depth_m=0., max_depth_m=None, sdk=None):
    snapshot, out = Path(snapshot), Path(out)
    if out.exists():
        raise FileExistsError(out)
    metadata = json.loads((snapshot/'metadata.json').read_text(encoding='utf-8'))
    if metadata.get('format') != 'w9-native-depth/1' or not metadata.get('complete') or metadata.get('aligned') is not False:
        raise ValueError('Need a complete native-depth snapshot from this tool.')
    stack = np.load(snapshot/'depth_stack.npy', allow_pickle=False)
    intr = metadata['depth_intrinsics']
    if stack.shape[1:] != (intr['height'], intr['width']):
        raise ValueError('Depth stack and native-depth intrinsics dimensions differ.')
    pixels = json.loads(Path(pixels_path).read_text(encoding='utf-8'))
    if sdk is None:
        import pyrealsense2 as sdk
    sdk_intrinsics = _restore_intrinsics(intr, sdk)
    points = measure_points(stack, metadata['depth_scale_m_per_unit'], pixels,
                            lambda pixel, depth: sdk.rs2_deproject_pixel_to_point(sdk_intrinsics, pixel, depth),
                            radius=radius, min_valid=min_valid, max_spread_m=max_spread_mm/1000,
                            min_depth_m=min_depth_m, max_depth_m=max_depth_m)
    document = {'format': 'w9-depth-points/1', 'source_snapshot': str(snapshot),
                'pixel_frame': 'native_depth', 'point_frame': 'depth_camera_optical', 'unit': 'm',
                'camera_optical_axes': metadata['camera_optical_axes'],
                'intrinsics': intr, 'neighbourhood_deprojection': 'each valid pixel in each frame; median XYZ',
                'spread_limit_mm': max_spread_mm, 'spread_limit_status': 'sampling diagnostic, not a calibrated accuracy tolerance',
                'camera_to_robot': None, 'camera_to_table': None,
                'alignment_warning': 'Coordinates were not obtained from native colour pixels. Colour.png is not pixel-aligned to native depth.',
                'points': points}
    with out.open('x', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2, allow_nan=False)
        handle.write('\n')
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    capture = commands.add_parser('capture', help='Capture RGB plus native depth for calibration only')
    capture.add_argument('--out', type=Path, required=True)
    capture.add_argument('--serial')
    capture.add_argument('--frames', type=int, default=30)
    capture.add_argument('--settle-frames', type=int, default=30)
    capture.add_argument('--width', type=int, default=640)
    capture.add_argument('--height', type=int, default=480)
    capture.add_argument('--fps', type=int, default=30)
    points = commands.add_parser('points', help='Offline native-depth pixels to camera XYZ and scatter')
    points.add_argument('snapshot', type=Path)
    points.add_argument('--pixels', type=Path, required=True)
    points.add_argument('--out', type=Path, required=True)
    points.add_argument('--radius', type=int, default=2)
    points.add_argument('--min-valid', type=int, default=20)
    points.add_argument('--max-spread-mm', type=float, default=10.)
    points.add_argument('--min-depth-m', type=float, default=0.)
    points.add_argument('--max-depth-m', type=float)
    args = parser.parse_args()
    if args.command == 'capture':
        print('Saved:', capture_snapshot(args.out, args.serial, args.frames, args.settle_frames,
                                          args.width, args.height, args.fps))
    else:
        result = offline_points(args.snapshot, args.pixels, args.out, args.radius, args.min_valid,
                                args.max_spread_mm, args.min_depth_m, args.max_depth_m)
        print('Saved:', args.out)
        if not all(point['accepted'] for point in result['points'].values()):
            parser.exit(1, 'Some native-depth points lack valid/stable depth. Inspect the saved diagnostics.\n')


if __name__ == '__main__':
    main()
