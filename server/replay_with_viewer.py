#!/usr/bin/env python3
"""Replay a Mirobot demo through the TCP bridge while serving sim frames.

This script is meant to run on the SSH server. It sends the same G-code stream
as server/replay_network.py, and also serves the exported simulation frames
in a small browser viewer.

Open the viewer in a browser:

    http://<ssh-server-ip>:8888

Dry-run:

    python -m server.replay_with_viewer --demo 0 --max-steps 10

Real execution:

    python -m server.replay_with_viewer \
      --bridge-host <LAPTOP_IP> --demo 0 --execute
"""

from __future__ import annotations

import argparse
import io
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageDraw

from common.demos import DEMOS
from common.gcode import (
    DEFAULT_CLOSE_CMD,
    DEFAULT_OPEN_CMD,
    DEFAULT_Z_OFFSET_MM,
    gripper_gcode,
    state_to_gcode,
)
from common.protocol import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT
from common.schema import TASK_INSTRUCTION
from server.bridge_client import BridgeClient, run_home, send_gcode


# 시뮬레이션 프레임이 export 되어 있는 위치. artifacts/ 는 .gitignore 대상이라
# 새 환경에서는 직접 만들어야 한다. docs/VENDORED.md 참조.
DEFAULT_EXPORT_ROOT = (
    Path(__file__).resolve().parents[1]
    / "cosmos-policy/artifacts/mirobot/datasets/active/wrist_under_v1_pick_place"
)


class ViewerState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.jpeg = self._placeholder("waiting for replay")
        self.step_text = "waiting"

    def _placeholder(self, text: str) -> bytes:
        image = Image.new("RGB", (512, 256), (32, 32, 32))
        draw = ImageDraw.Draw(image)
        draw.text((20, 20), text, fill=(240, 240, 240))
        return self._encode(image)

    def _encode(self, image: Image.Image) -> bytes:
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=88)
        return out.getvalue()

    def update(self, jpeg: bytes, step_text: str) -> None:
        with self.lock:
            self.jpeg = jpeg
            self.step_text = step_text

    def snapshot(self) -> tuple[bytes, str]:
        with self.lock:
            return self.jpeg, self.step_text


def make_handler(state: ViewerState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def do_GET(self) -> None:
            if self.path.startswith("/frame.jpg"):
                jpeg, step_text = state.snapshot()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Step", step_text)
                self.send_header("Content-Length", str(len(jpeg)))
                self.end_headers()
                self.wfile.write(jpeg)
                return

            html = b"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Mirobot Sim Viewer</title>
  <style>
    body { margin: 0; background: #111; color: #eee; font-family: system-ui, sans-serif; }
    main { height: 100vh; display: grid; grid-template-rows: auto 1fr; }
    header { padding: 10px 14px; background: #1c1c1c; font-size: 14px; }
    img { width: 100%; height: 100%; object-fit: contain; image-rendering: auto; }
  </style>
</head>
<body>
<main>
  <header id="status">Mirobot simulation frames</header>
  <img id="frame" src="/frame.jpg">
</main>
<script>
const img = document.getElementById("frame");
const status = document.getElementById("status");
async function tick() {
  const url = "/frame.jpg?t=" + Date.now();
  const resp = await fetch(url, {cache: "no-store"});
  status.textContent = resp.headers.get("X-Step") || "running";
  const blob = await resp.blob();
  img.src = URL.createObjectURL(blob);
}
setInterval(tick, 120);
tick();
</script>
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

    return Handler


def start_viewer(host: str, port: int, state: ViewerState) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def frame_path(export_dir: Path, camera_name: str, step_idx: int) -> Path:
    return export_dir / camera_name / f"frame_{step_idx:04d}.png"


def load_side_by_side_frame(export_dir: Path, step_idx: int, demo_idx: int) -> bytes:
    agent_path = frame_path(export_dir, "agentview_rgb", step_idx)
    wrist_path = frame_path(export_dir, "eye_in_hand_rgb", step_idx)

    agent = Image.open(agent_path).convert("RGB")
    wrist = Image.open(wrist_path).convert("RGB")
    if agent.size != wrist.size:
        wrist = wrist.resize(agent.size)

    label_h = 28
    combined = Image.new("RGB", (agent.width + wrist.width, agent.height + label_h), (20, 20, 20))
    combined.paste(agent, (0, label_h))
    combined.paste(wrist, (agent.width, label_h))

    draw = ImageDraw.Draw(combined)
    draw.text((10, 7), f"demo_{demo_idx} step {step_idx:04d} | agentview", fill=(245, 245, 245))
    draw.text((agent.width + 10, 7), "eye_in_hand", fill=(245, 245, 245))

    out = io.BytesIO()
    combined.save(out, format="JPEG", quality=90)
    return out.getvalue()


def replay_demo_with_viewer(client: BridgeClient | None, demo_idx: int, args, state: ViewerState, dry_run: bool) -> None:
    demo = DEMOS[str(demo_idx)]
    actions = demo["actions"]
    states = demo["states"]
    export_dir = Path(args.export_dir)
    indices = list(range(0, len(states), args.stride))
    if args.max_steps > 0:
        indices = indices[: args.max_steps]

    print(f"===== demo_{demo_idx} | states={len(states)} | replayed={len(indices)} =====")
    print(f"viewer frames: {export_dir}")

    last_gripper = None
    for step_idx in indices:
        try:
            jpeg = load_side_by_side_frame(export_dir, step_idx, demo_idx)
            state.update(jpeg, f"demo_{demo_idx} step {step_idx:04d}")
        except Exception as exc:
            print(f"viewer frame skipped for step {step_idx}: {exc}")

        robot_state = states[step_idx]
        action = actions[step_idx]
        print(f"[demo_{demo_idx} step {step_idx:04d}]")
        send_gcode(
            client,
            state_to_gcode(
                robot_state,
                args.x_offset_mm,
                args.y_offset_mm,
                args.z_offset_mm,
                args.a_deg,
                args.b_deg,
                args.c_deg,
            ),
            dry_run,
        )

        grip_cmd = gripper_gcode(action, args.open_cmd, args.close_cmd)
        if grip_cmd != last_gripper:
            send_gcode(client, grip_cmd, dry_run)
            last_gripper = grip_cmd

        if args.period > 0:
            time.sleep(args.period)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a Mirobot demo with a browser simulation-frame viewer.")
    parser.add_argument("--demo", type=int, default=0, help="Demo index. Default: 0")
    parser.add_argument("--export-dir", default=str(DEFAULT_EXPORT_ROOT / "demo_0_export"))
    parser.add_argument("--viewer-host", default="0.0.0.0")
    parser.add_argument("--viewer-port", type=int, default=8888)
    parser.add_argument("--bridge-host", default=DEFAULT_BRIDGE_HOST, help="Windows PC IP address")
    parser.add_argument("--bridge-port", type=int, default=DEFAULT_BRIDGE_PORT)
    parser.add_argument("--bridge-timeout", type=float, default=20.0)
    parser.add_argument("--execute", action="store_true", help="Actually send commands. Without this, dry-run only.")
    parser.add_argument("--skip-home", action="store_true")
    parser.add_argument("--start-pause", type=float, default=5.0, help="Seconds to wait before homing/replay so the viewer can be opened.")
    parser.add_argument("--hold-viewer-after", type=float, default=10.0, help="Seconds to keep the viewer open after replay.")
    parser.add_argument("--period", type=float, default=0.20)
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--x-offset-mm", type=float, default=0.0)
    parser.add_argument("--y-offset-mm", type=float, default=0.0)
    parser.add_argument("--z-offset-mm", type=float, default=DEFAULT_Z_OFFSET_MM)
    parser.add_argument("--a-deg", type=float, default=0.0)
    parser.add_argument("--b-deg", type=float, default=0.0)
    parser.add_argument("--c-deg", type=float, default=0.0)
    parser.add_argument("--open-cmd", default=DEFAULT_OPEN_CMD)
    parser.add_argument("--close-cmd", default=DEFAULT_CLOSE_CMD)
    args = parser.parse_args()

    if str(args.demo) not in DEMOS:
        parser.error(f"demo_{args.demo} is not embedded. Available demos: {sorted(int(k) for k in DEMOS.keys())}")
    if args.stride < 1:
        parser.error("--stride must be >= 1")
    if args.period < 0:
        parser.error("--period must be >= 0")
    if args.start_pause < 0 or args.hold_viewer_after < 0:
        parser.error("--start-pause and --hold-viewer-after must be >= 0")

    viewer_state = ViewerState()
    viewer = start_viewer(args.viewer_host, args.viewer_port, viewer_state)

    dry_run = not args.execute
    print(f"instruction: {TASK_INSTRUCTION}")
    print(f"selected demo: {args.demo}")
    print(f"mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")
    print(f"bridge: {args.bridge_host}:{args.bridge_port}")
    print(f"viewer: http://{args.viewer_host}:{args.viewer_port}")
    print("If running over SSH, forward/open the viewer port and use that URL in a browser.")

    client = None
    if args.execute:
        client = BridgeClient(args.bridge_host, args.bridge_port, args.bridge_timeout)
        client.connect()

    try:
        if args.start_pause > 0:
            print(f"starting in {args.start_pause:.1f}s; open the viewer now")
            time.sleep(args.start_pause)
        if not args.skip_home:
            run_home(client, dry_run)
        replay_demo_with_viewer(client, args.demo, args, viewer_state, dry_run)
        if args.hold_viewer_after > 0:
            print(f"holding viewer for {args.hold_viewer_after:.1f}s")
            time.sleep(args.hold_viewer_after)
    finally:
        if client is not None:
            client.close()
            print("bridge connection closed")
        viewer.shutdown()
        viewer.server_close()
        print("viewer closed")


if __name__ == "__main__":
    main()
