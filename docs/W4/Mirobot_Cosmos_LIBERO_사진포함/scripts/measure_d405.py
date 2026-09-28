"""Static RGB-D measurements on a marked work surface; no robot motion commands."""
import argparse
import json
import time
from pathlib import Path

import numpy as np


def fit_work_frame(camera_mm, work_mm):
    camera_mm, work_mm = np.asarray(camera_mm, dtype=float), np.asarray(work_mm, dtype=float)
    if (camera_mm.shape != work_mm.shape or camera_mm.ndim != 2 or camera_mm.shape[1] != 3
            or len(camera_mm) < 3 or not np.all(np.isfinite(camera_mm))
            or not np.all(np.isfinite(work_mm))):
        raise ValueError("같은 순서의 실제 XYZ(mm) 좌표를 입력하세요.")
    c, w = camera_mm.mean(0), work_mm.mean(0)
    U, s, Vt = np.linalg.svd((camera_mm - c).T @ (work_mm - w))
    if s[1] <= 1e-8:
        raise ValueError("기준점이 한 직선에 몰려 있습니다.")
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[-1] *= -1
        R = Vt.T @ U.T
    t = w - R @ c
    residual = camera_mm @ R.T + t - work_mm
    return R, t, float(np.sqrt(np.mean(np.sum(residual**2, axis=1))))


def point_measurements(p):
    p = np.asarray(p)
    delta = p[1] - p[0]
    a, b = p[0] - p[1], p[2] - p[1]
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom <= 0:
        raise ValueError("서로 다른 세 점을 선택하세요.")
    return dict(points_mm=p.tolist(), length_mm=float(np.linalg.norm(delta)),
                horizontal_mm=float(np.linalg.norm(delta[:2])),
                midpoint_P1P2_mm=((p[0] + p[1]) / 2).tolist(),
                line_yaw_deg=(float(np.degrees(np.arctan2(delta[1], delta[0])))
                              if np.linalg.norm(delta[:2]) > 1e-8 else None),
                angle_at_P2_deg=float(np.degrees(np.arccos(np.clip(a @ b / denom, -1, 1)))))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--serial")
    parser.add_argument("--width-mm", type=float, default=200)
    parser.add_argument("--depth-mm", type=float, default=150)
    parser.add_argument("--height-check-mm", type=float)
    parser.add_argument("--origin-mm", type=float, nargs=2, default=[0, 0])
    parser.add_argument("--patch-spread-mm", type=float, default=5)
    parser.add_argument("--register-base", type=Path)
    parser.add_argument("--base-transform", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    if min(args.width_mm, args.depth_mm, args.patch_spread_mm) <= 0:
        parser.error("기준점 간격과 깊이 선택 기준은 양수여야 합니다.")
    if args.height_check_mm is not None and args.height_check_mm <= 0:
        parser.error("검증 물체의 실제 높이(mm)를 입력하세요.")
    work = np.array([[0, 0, 0], [args.width_mm, 0, 0],
                     [args.width_mm, args.depth_mm, 0], [0, args.depth_mm, 0.]])
    work += np.array([*args.origin_mm, 0])
    if args.register_base:
        raw = json.loads(args.register_base.read_text(encoding="utf-8-sig"))
        base = [raw[key] for key in "ABCD"]
        try:
            R_bw, t_bw, error = fit_work_frame(work, base)
        except ValueError as error:
            parser.error(str(error))
        result = dict(R_BW=R_bw.tolist(), t_BW_mm=t_bw.tolist(), fit_rmse_mm=error,
                      reference_width_mm=args.width_mm, reference_depth_mm=args.depth_mm,
                      reference_origin_mm=args.origin_mm)
        Path("work_to_base.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return
    if args.summary:
        saved = json.loads(args.summary.read_text(encoding="utf-8"))
        samples = [r for r in saved["records"] if r["mode"] == "m"][-5:]
        if len(samples) < 5:
            parser.error("같은 세 점을 새 프레임에서 5회 측정한 뒤 실행하세요.")
        result = {}
        for name in ("length_mm", "horizontal_mm", "angle_at_P2_deg", "points_mm"):
            values = np.asarray([r[name] for r in samples])
            result[name] = {key: value.tolist() for key, value in dict(
                mean=values.mean(0), std=values.std(0, ddof=1),
                min=values.min(0), max=values.max(0)).items()}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    base_transform = None
    if args.base_transform:
        base_transform = json.loads(args.base_transform.read_text(encoding="utf-8"))
        R_bw, t_bw = np.asarray(base_transform["R_BW"]), np.asarray(base_transform["t_BW_mm"])
        if (R_bw.shape != (3, 3) or t_bw.shape != (3,)
                or not np.all(np.isfinite(R_bw)) or not np.all(np.isfinite(t_bw))
                or not np.allclose(R_bw.T @ R_bw, np.eye(3), atol=1e-6)
                or not np.isclose(np.linalg.det(R_bw), 1, atol=1e-6)):
            parser.error("올바른 work_to_base.json을 사용하세요.")
        if not np.allclose([args.width_mm, args.depth_mm],
                           [base_transform["reference_width_mm"], base_transform["reference_depth_mm"]]):
            parser.error("베이스 등록에 쓴 W, D와 같은 값을 입력하세요.")
        if not np.allclose(args.origin_mm, base_transform["reference_origin_mm"]):
            parser.error("베이스 등록에 쓴 A의 종이 좌표와 같은 --origin-mm을 입력하세요.")

    import cv2
    import pyrealsense2 as rs

    devices = [d.get_info(rs.camera_info.serial_number) for d in rs.context().query_devices()]
    if args.list or not args.serial:
        print("Camera serials:", devices)
        return
    if args.serial not in devices:
        parser.error("카메라 serial과 실제 기준점 간격을 확인하세요.")

    config, pipe = rs.config(), rs.pipeline()
    config.enable_device(args.serial)
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
    profile = pipe.start(config)
    scale = profile.get_device().first_depth_sensor().get_depth_scale()
    # Show RGB in the native depth pixel grid; preserve depth Z and intrinsics.
    align = rs.align(rs.stream.depth)
    clicks, records, frozen, mode, R, t = [], [], False, "", None, None
    cv2.namedWindow("D405", cv2.WINDOW_AUTOSIZE)
    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and frozen and mode:
            clicks.append((x, y))
    cv2.setMouseCallback("D405", on_mouse)
    print("C: A B C D calibration | M: P1 P2 P3 | V: E check | H: height check | R: live | Q: quit")
    try:
        while True:
            if not frozen:
                frames = align.process(pipe.wait_for_frames())
                df, cf = frames.get_depth_frame(), frames.get_color_frame()
                if not df or not cf:
                    continue
                depth = np.asanyarray(df.get_data()).copy()
                color = np.asanyarray(cf.get_data()).copy()
                intr = df.profile.as_video_stream_profile().intrinsics
                captured_at = time.time()
            view = color.copy()
            for index, xy in enumerate(clicks):
                cv2.circle(view, xy, 4, (0, 0, 255), -1)
                cv2.putText(view, str(index + 1), xy, cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 0, 255), 2)
            cv2.putText(view, "C:cal M:3pts V:check H:height R:live Q:quit", (8, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 255, 0), 1)
            cv2.imshow("D405", view)
            key = cv2.waitKey(20) & 255
            if key == ord("q") or cv2.getWindowProperty("D405", cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == ord("r"):
                frozen, mode = False, ""
                clicks.clear()
            if key in map(ord, "cmvh"):
                mode, frozen = chr(key), True
                clicks.clear()
                if mode == "c":
                    R, t = None, None
            needed = {"c": 4, "m": 3, "v": 1, "h": 1}.get(mode, 0)
            if not needed or len(clicks) < needed:
                continue
            try:
                points = []
                for u, v in clicks[:needed]:
                    if depth[v, u] == 0:
                        raise ValueError("클릭점 깊이가 0입니다. 유효 깊이가 있는 표면 안쪽을 다시 고르세요.")
                    patch = depth[max(0, v-1):v+2, max(0, u-1):u+2]
                    valid = patch[patch > 0]
                    if not valid.size:
                        raise ValueError("깊이가 없는 점입니다. 같은 표면의 유효 점을 다시 고르세요.")
                    if (float(valid.max()) - float(valid.min())) * scale * 1000 > args.patch_spread_mm:
                        raise ValueError("주변 깊이 차이가 큽니다. 물체 경계나 배경을 피해 같은 표면을 다시 고르세요.")
                    z_m = float(np.median(valid)) * scale
                    points.append(np.asarray(rs.rs2_deproject_pixel_to_point(intr, [u, v], z_m)) * 1000)
                points = np.asarray(points)
                if mode == "c":
                    R, t, rmse = fit_work_frame(points, work)
                    if t[2] <= 0 or R[2, 2] >= 0:
                        R, t = None, None
                        raise ValueError("A B C D 순서와 작업면 +Z 방향을 확인하세요.")
                    result = dict(calibration_fit_rmse_mm=rmse, camera_height_mm=float(t[2]),
                                  camera_position_mm=t.tolist(),
                                  camera_down_deg=float(np.degrees(np.arctan2(-R[2, 2], np.linalg.norm(R[:2, 2])))))
                else:
                    if R is None:
                        raise ValueError("먼저 C를 눌러 A B C D를 선택하세요.")
                    p = points @ R.T + t
                    if mode == "m":
                        result = point_measurements(p)
                        if base_transform:
                            result["points_base_mm"] = (p @ R_bw.T + t_bw).tolist()
                    elif mode == "v":
                        expected = work.mean(0)
                        result = dict(check_point_mm=p[0].tolist(), position_error_mm=float(np.linalg.norm(p[0] - expected)))
                    else:
                        if args.height_check_mm is None:
                            raise ValueError("--height-check-mm에 자로 잰 높이를 입력하고 다시 실행하세요.")
                        result = dict(height_mm=float(p[0, 2]), height_error_mm=float(p[0, 2] - args.height_check_mm))
                stem = Path(f"d405_{args.serial}_{time.time_ns()}")
                result.update(mode=mode, captured_at=captured_at, capture_prefix=str(stem),
                              clicked_pixels=clicks[:needed], camera_points_mm=points.tolist(),
                              R_wc=R.tolist(), t_wc_mm=t.tolist())
                records.append(result)
                print(json.dumps(result, ensure_ascii=False))
                cv2.imwrite(str(stem) + ".png", color)
                np.savez_compressed(str(stem) + ".npz", depth_z16=depth, depth_scale=scale,
                                    intrinsics=np.array([intr.width, intr.height, intr.fx, intr.fy, intr.ppx, intr.ppy]),
                                    distortion_model=str(intr.model), distortion_coeffs=np.array(intr.coeffs))
                Path(f"d405_{args.serial}_results.json").write_text(json.dumps(
                    dict(serial=args.serial, reference_width_mm=args.width_mm,
                         reference_depth_mm=args.depth_mm, reference_origin_mm=args.origin_mm,
                         base_transform=base_transform, R_wc=R.tolist(), t_wc_mm=t.tolist(), records=records),
                    ensure_ascii=False, indent=2), encoding="utf-8")
            except ValueError as error:
                print(error)
            mode = ""
            clicks.clear()
    finally:
        pipe.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
