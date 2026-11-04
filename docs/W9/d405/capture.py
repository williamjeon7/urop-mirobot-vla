"""D405 RGB PNG + per-frame timestamps, optionally execute validated Mirobot G-code."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import queue
import shutil
import threading
import sys
import time
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--list', action='store_true', help='List RealSense devices and RGB profiles; no robot motion')
    output = p.add_mutually_exclusive_group()
    output.add_argument('--out', type=Path, help='Explicit new episode folder (e.g. chart_001)')
    output.add_argument('--out-root', type=Path, help='Numbered episode parent; default docs/W9/data/raw')
    p.add_argument('--serial', help='D405 serial; required if more than one D405 is connected')
    p.add_argument('--width', type=int, default=640)
    p.add_argument('--height', type=int, default=480)
    p.add_argument('--fps', type=int, default=30)
    p.add_argument('--seconds', type=float, default=10, help='Camera-only duration')
    p.add_argument('--preview', action='store_true')
    p.add_argument('--color', choices=['red', 'green', 'blue'], default='red')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--reference', type=Path, help='Original W6 Panda pose JSONL used to create G-code')
    p.add_argument('--gcode', type=Path)
    p.add_argument('--teleop', action='store_true', help='Use existing robot/inverse_kinematics.py; F8/F9 mark episode')
    p.add_argument('--homing', action='store_true',
                   help='Teleop: run the original $H at start and q exit. By default homing is skipped and '
                        'the arm only moves to the initial pose; home separately with '
                        'python -m docs.W9.d405.home_robot after power-on or a collision.')
    p.add_argument('--no-homing', action='store_true', help=argparse.SUPPRESS)  # old commands; now the default
    p.add_argument('--mapping-gcode', type=Path, help='Coordinate mapping header only; not executed in teleop mode')
    p.add_argument('--color-profile', type=Path, help='Fixed Classic Mini correction; raw PNG remains unmodified')
    p.add_argument('--layout', type=Path, help='Manually measured initial paper coordinates JSON (cm)')
    p.add_argument('--layout-photo', type=Path, help='Initial-layout PNG/JPEG, overriding the template photo path')
    p.add_argument('--port', help='Robot serial device, e.g. /dev/serial/by-id/... (not the D405)')
    p.add_argument('--execute', action='store_true', help='Execute G-code; omission means validate only')
    p.add_argument('--gripper-seconds', type=float, default=1.0, help='Measured servo transition/hold seconds')
    p.add_argument('--auto-stop-seconds', type=float, default=3.0, help='Recording tail after post-Close upward Z command')
    p.add_argument('--pickup-timeout', type=float, default=15.0)
    p.add_argument('--episode-timeout', type=float, default=120.0)
    p.add_argument('--initial-s', type=float, default=40, help='Actual gripper command before capture')
    p.add_argument('--open-s', type=float, default=40)
    p.add_argument('--closed-s', type=float, default=60)
    a = p.parse_args()
    if a.seconds <= 0 or a.gripper_seconds <= 0 or a.open_s == a.closed_s:
        p.error('Positive durations and distinct open/closed S values required.')
    if not all(__import__('math').isfinite(v) and v > 0 for v in
               (a.auto_stop_seconds, a.pickup_timeout, a.episode_timeout)):
        p.error('Auto-stop and timeout durations must be finite positive seconds.')
    layout_inputs = None
    if a.layout_photo and not a.layout:
        p.error('--layout-photo requires --layout with all three measured block centres.')
    if a.layout:
        from .layout_record import load_capture_layout
        try:
            layout_inputs = load_capture_layout(a.layout, a.color, a.layout_photo)
        except (OSError, ValueError, KeyError) as error:
            p.error(f'Invalid layout: {error}')
    entries = None
    if (a.homing or a.no_homing) and not a.teleop:
        p.error('--homing / --no-homing only apply to --teleop.')
    if a.homing and a.no_homing:
        p.error('Choose either --homing or the default (no homing), not both.')
    if a.teleop:
        if a.gcode or not a.reference or not a.mapping_gcode:
            p.error('--teleop requires --reference and --mapping-gcode; do not pass --gcode.')
        if not a.execute:
            print('Teleop launch requires --execute. Homing is skipped unless --homing is given.')
            return
        if os.name == 'posix' and not sys.stdin.isatty():
            p.error('Teleop needs an interactive terminal; use SSH with -t or VS Code terminal.')
        ref = json.loads(a.reference.read_text(encoding='utf-8').splitlines()[0])['meta']
        if ref['seed'] != a.seed or ref['task'] != a.color:
            p.error('Reference seed/task differ from --seed/--color.')
    if a.gcode:
        from .robot_capture import validate_gcode
        entries = validate_gcode(a.gcode)
        import re
        for _, command in entries:
            match = re.fullmatch(r'M4\s+S(\d+(?:\.\d+)?)', command, re.I)
            if match and not min(a.open_s, a.closed_s) <= float(match.group(1)) <= max(a.open_s, a.closed_s):
                p.error('G-code gripper S is outside --open-s/--closed-s endpoints.')
        print(f'Validated {len(entries)} commands, absolute coordinates, Z >= 66 mm.')
        if not a.execute:
            print('Validation only. Add --execute to capture and run the robot.')
            return
        if not a.reference:
            p.error('--reference is required for robot capture.')
        ref = json.loads(a.reference.read_text(encoding='utf-8').splitlines()[0])['meta']
        if ref['seed'] != a.seed or ref['task'] != a.color:
            p.error('Reference seed/task differ from --seed/--color.')
    elif a.execute and not a.teleop:
        p.error('--execute requires --gcode.')

    if (a.teleop or entries) and a.execute and not a.port:
        if os.name == 'nt':
            a.port = 'COM3' if a.teleop else 'COM4'
        else:
            p.error('Specify the robot serial device with --port /dev/serial/by-id/...')
    if a.preview and sys.platform.startswith('linux') and not (
            os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        p.error('No GUI display. Remove --preview when capturing over headless SSH.')

    import cv2
    import numpy as np
    import pyrealsense2 as rs
    devices = list(rs.context().query_devices())
    if a.list:
        print(f'RealSense devices: {len(devices)}')
        for dev in devices:
            print(dev.get_info(rs.camera_info.name), dev.get_info(rs.camera_info.serial_number))
            for sensor in dev.query_sensors():
                profiles = sorted({(v.as_video_stream_profile().width(), v.as_video_stream_profile().height(),
                                    v.fps(), str(v.format())) for v in sensor.get_stream_profiles()
                                   if v.stream_type() == rs.stream.color})
                for row in profiles:
                    print('  RGB profile:', row)
        return
    candidates = [d for d in devices if 'D405' in d.get_info(rs.camera_info.name)
                  and (not a.serial or d.get_info(rs.camera_info.serial_number) == a.serial)]
    if len(candidates) != 1:
        p.error(f'Expected one D405, found {len(candidates)}. Check USB / --serial / --list.')
    dev = candidates[0]
    serial_number = dev.get_info(rs.camera_info.serial_number)
    from .capture_storage import clear_take, reserve_episode, write_image
    if a.out is None:
        a.out = reserve_episode(a.out_root or Path(__file__).resolve().parents[1] / 'data' / 'raw')
    else:
        a.out.mkdir(parents=True, exist_ok=False)  # never overwrite an episode
    print('Recording folder:', a.out, flush=True)
    (a.out / 'rgb').mkdir()
    source_gcode = a.mapping_gcode if a.teleop else a.gcode
    if source_gcode:
        shutil.copyfile(source_gcode, a.out / 'source.gcode')
        shutil.copyfile(a.reference, a.out / 'reference.jsonl')
    color_profile = None
    if a.color_profile:
        from .color_calibration import load_profile
        color_profile = load_profile(a.color_profile)
        if (color_profile['camera_serial'] != serial_number or
                (color_profile['width'], color_profile['height'], color_profile['fps']) != (a.width, a.height, a.fps)):
            raise ValueError('Colour profile camera / resolution / fps differs from requested capture.')
        shutil.copyfile(a.color_profile, a.out / 'color_profile.json')
    clock_ns = time.perf_counter_ns()
    from datetime import datetime
    meta = dict(format='w9-d405/1', clock='perf_counter_ns, shared process', clock_ns=clock_ns,
                recorded_at=datetime.now().astimezone().isoformat(timespec='seconds'),  # local wall time
                serial=serial_number, color=a.color, seed=a.seed, gripper_seconds=a.gripper_seconds,
                initial_s=a.initial_s, open_s=a.open_s, closed_s=a.closed_s,
                real_success=None, complete=False, robot=bool(entries or a.teleop), teleop=a.teleop,
                width=a.width, height=a.height, fps=a.fps, timestamp_basis='host receipt; NOT exposure time',
                robot_port=a.port,
                packages={n: importlib.metadata.version(n) for n in
                          ['pyrealsense2', 'numpy', 'opencv-python', 'pyserial', 'h5py']})
    if a.teleop:
        meta['homing'] = '$H at start and q exit' if a.homing else 'skipped; initial-pose move only'
        meta['discarded_takes'] = 0  # RESET count; robot.jsonl has a capture_reset mark for each
    meta_path = a.out / 'metadata.json'
    def save_meta():
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding='utf-8')
    save_meta()
    if layout_inputs is not None:
        from .layout_record import create_layout
        coordinates, photo = layout_inputs
        create_layout(a.out, coordinates, photo, target=a.color)
    pipe, config = rs.pipeline(), rs.config()
    config.enable_device(serial_number)
    config.enable_stream(rs.stream.color, a.width, a.height, rs.format.rgb8, a.fps)
    stop, ready = threading.Event(), threading.Event()
    recording, first_recorded_frame = threading.Event(), threading.Event()
    from .recording_controls import RecordingControls
    controls = RecordingControls() if a.teleop else None
    if not a.teleop:
        recording.set()
    errors = queue.Queue()
    profile = None
    worker = None
    preview_title = 'D405 live - recording controls' if a.teleop else 'D405 - Esc stops capture'
    set_aside = queue.Queue()  # RESET requests; only the camera thread touches frame files
    def camera_loop():
        log = None
        try:
            if a.preview:
                cv2.namedWindow(preview_title)
                if controls:
                    cv2.setMouseCallback(preview_title, controls.mouse)
            log = (a.out / 'frames.jsonl').open('x', encoding='utf-8')
            index = 0
            while not stop.is_set():
                try:
                    request = set_aside.get_nowait()
                except queue.Empty:
                    request = None
                if request is not None:
                    # RESET: delete the discarded take and restart numbering at 0.
                    log.close()
                    clear_take(a.out)
                    log = (a.out / 'frames.jsonl').open('x', encoding='utf-8')
                    index = 0
                    request['done'].set()
                frames = pipe.wait_for_frames(2000)
                receipt_ns = time.perf_counter_ns()
                frame = frames.get_color_frame()
                if not frame:
                    continue
                image = np.asanyarray(frame.get_data())
                if recording.is_set():
                    name = f'rgb/{index:08d}.png'
                    write_image(a.out / name, cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
                    log.write(json.dumps(dict(file=name, t_s=(receipt_ns-clock_ns)/1e9,
                                             device_ms=frame.get_timestamp(),
                                             domain=str(frame.get_frame_timestamp_domain()),
                                             number=frame.get_frame_number())) + '\n')
                    log.flush()
                    first_recorded_frame.set()
                    index += 1
                ready.set()
                if a.preview:
                    from .color_calibration import apply_rgb
                    view = cv2.cvtColor(apply_rgb(image, color_profile), cv2.COLOR_RGB2BGR)
                    cv2.imshow(preview_title, controls.draw(view) if controls else view)
                    if cv2.waitKey(1) & 0xff == 27:
                        stop.set()
        except Exception as e:
            errors.put(e)
            stop.set()
        finally:
            if log is not None:
                log.close()
            if a.preview:
                cv2.destroyAllWindows()
    try:
        profile = pipe.start(config)
        color_stream_profile = profile.get_stream(rs.stream.color).as_video_stream_profile()
        intr = color_stream_profile.get_intrinsics()
        meta['intrinsics'] = dict(width=intr.width, height=intr.height, fx=intr.fx, fy=intr.fy,
                                  ppx=intr.ppx, ppy=intr.ppy, coeffs=intr.coeffs, model=str(intr.model))
        # Auto exposure/WB settle before recording; lock supported controls.
        for _ in range(45):
            pipe.wait_for_frames(2000)
        locked = {}
        for sensor in profile.get_device().query_sensors():
            for auto, value in [(rs.option.enable_auto_exposure, rs.option.exposure),
                                (rs.option.enable_auto_white_balance, rs.option.white_balance)]:
                if sensor.supports(auto) and sensor.supports(value):
                    measured = (color_profile['camera_options'].get(str(value), sensor.get_option(value))
                                if color_profile else sensor.get_option(value))
                    sensor.set_option(auto, 0)
                    sensor.set_option(value, measured)
                    locked[str(value)] = measured
            for option in [rs.option.gain, rs.option.gamma, rs.option.saturation,
                           rs.option.brightness, rs.option.contrast, rs.option.hue, rs.option.sharpness]:
                if sensor.supports(option):
                    measured = sensor.get_option(option)
                    if color_profile and str(option) in color_profile['camera_options']:
                        measured = color_profile['camera_options'][str(option)]
                        sensor.set_option(option, measured)
                    locked[str(option)] = measured
        meta['locked_camera_options'] = locked
        if color_profile:
            for key, value in color_profile['camera_options'].items():
                if key not in locked or abs(locked[key]-value) > max(1, abs(value)*.001):
                    raise ValueError('Cannot reproduce the colour-profile camera settings.')
            # Discard buffered frames from before the profile settings took effect.
            # The SDK option readback can update before delivered RGB frames do.
            for _ in range(15):
                pipe.wait_for_frames(2000)
            meta['profile_settle_frames'] = 15
        save_meta()
        worker = threading.Thread(target=camera_loop, name='d405-capture')
        worker.start()
        if not ready.wait(10) or stop.is_set():
            raise RuntimeError('Camera did not become ready.')
        if a.teleop:
            from .teleop import run
            def start_recording():
                first_recorded_frame.clear()  # every take (also after RESET) waits for its own frame
                recording.set()
                if not first_recorded_frame.wait(5) or stop.is_set():
                    raise RuntimeError('Camera did not save a frame after recording started.')
            def discard_take():
                recording.clear()  # RESET: stop saving frames of the discarded take
                meta['discarded_takes'] += 1
                request = dict(number=meta['discarded_takes'], done=threading.Event())
                set_aside.put(request)  # the camera thread deletes the discarded frames
                if not request['done'].wait(10) or stop.is_set():
                    raise RuntimeError('Camera did not clear the discarded take.')
            meta['teleop_recording_mode'] = 'buttons_or_f8_f9_after_initial_idle'
            print('Live preview during homing. After initial Idle: START/F8, STOP/F9, '
                  'RESET discards the take, q saves and exits.')
            run(a.out, clock_ns, stop, a.initial_s, port=a.port, controls=controls,
                on_start=start_recording, on_end=recording.clear,
                on_reset=discard_take, skip_homing=not a.homing,
                auto_stop_seconds=a.auto_stop_seconds, pickup_timeout=a.pickup_timeout,
                episode_timeout=a.episode_timeout, closed_s=a.closed_s)
        elif entries:
            from .robot_capture import run_robot
            run_robot(a.port, entries, a.out, clock_ns, stop, a.gripper_seconds, a.initial_s)
        else:
            stop.wait(a.seconds)
        if stop.is_set():
            raise RuntimeError('Capture interrupted before completion.')
        meta['complete'] = True
    except BaseException as e:
        meta['error'] = f'{type(e).__name__}: {e}'
        raise
    finally:
        stop.set()
        if worker:
            worker.join(timeout=5)
        if profile:
            pipe.stop()
        if not errors.empty():
            meta['complete'] = False
            meta['error'] = str(errors.get())
        result_path = a.out / 'capture_result.json'
        if result_path.exists():
            meta.update(json.loads(result_path.read_text(encoding='utf-8')))
        if a.teleop and meta.get('termination_status') in ('task_failed', 'abnormal', 'timeout'):
            meta['complete'] = False
            meta.setdefault('error', meta.get('termination_reason'))
        save_meta()
    if not meta['complete']:
        raise RuntimeError(meta.get('error', 'Incomplete capture'))
    print('Saved:', a.out, '(real_success still needs review)')
    from .preview import create_review
    create_review(a.out)


if __name__ == '__main__':
    main()
