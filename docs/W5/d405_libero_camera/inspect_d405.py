"""Save the active D405 color stream's calibration and one RGB frame.

Run after the camera arrives. Requires pyrealsense2, numpy and Pillow.
Does not change exposure or white-balance controls.
"""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="Required if more than one camera is attached")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "measured")
    args = parser.parse_args()
    import numpy as np
    import pyrealsense2 as rs
    from PIL import Image

    devices = list(rs.context().query_devices())
    if not args.serial and len(devices) != 1:
        parser.error("Connect one D405, or select its serial number with --serial")
    if args.serial:
        matches = [d for d in devices if d.get_info(rs.camera_info.serial_number) == args.serial]
        if not matches:
            parser.error("The requested camera serial number was not found")
        device = matches[0]
    else:
        device = devices[0]
    if "D405" not in device.get_info(rs.camera_info.name):
        parser.error("The selected camera is not a D405")
    pipe, config = rs.pipeline(), rs.config()
    config.enable_device(device.get_info(rs.camera_info.serial_number))
    config.enable_stream(rs.stream.color, args.width, args.height, rs.format.rgb8, args.fps)
    profile = pipe.start(config)
    try:
        # Allow automatic exposure to settle before recording a reference frame.
        for _ in range(30):
            frames = pipe.wait_for_frames(5000)
        color = frames.get_color_frame()
        intr = color.profile.as_video_stream_profile().get_intrinsics()
        data = {
            "device": device.get_info(rs.camera_info.name),
            "serial": device.get_info(rs.camera_info.serial_number),
            "firmware": device.get_info(rs.camera_info.firmware_version),
            "width": intr.width, "height": intr.height, "fps": color.profile.fps(),
            "format": str(color.profile.format()),
            "fx": intr.fx, "fy": intr.fy, "cx": intr.ppx, "cy": intr.ppy,
            "distortion_model": str(intr.model), "distortion_coefficients": list(intr.coeffs),
            "fov_deg": list(rs.rs2_fov(intr)),
            "timestamp_ms": color.get_timestamp(),
            "timestamp_domain": str(color.get_frame_timestamp_domain()),
            "frame_number": color.get_frame_number(),
            "K": [[intr.fx, 0, intr.ppx], [0, intr.fy, intr.ppy], [0, 0, 1]],
            "scope": "Device stream calibration only; mounting pose is not measured.",
        }
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "d405_color_profile.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        Image.fromarray(np.asanyarray(color.get_data())).save(args.out / "d405_rgb.png")
        print("Saved profile and RGB frame to", args.out.resolve())
    finally:
        pipe.stop()


if __name__ == "__main__":
    main()
