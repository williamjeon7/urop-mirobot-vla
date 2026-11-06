"""Record continuous camera frames only while a policy inference run is active."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import threading
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class PolicyVideo:
    def __init__(self, path, width, height, fps):
        self.path = Path(path)
        self.size, self.fps = (width, height), fps
        self.lock = threading.Lock()
        self.writer = self.frames_file = None
        self.result = None
        self.count = 0

    def start(self):
        import cv2
        with self.lock:
            if self.writer is not None:
                return dict(self.result, recording=True)
            if self.result is not None:
                raise RuntimeError("This video has already finished; start a new inference run")
            try:
                started_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
            except ZoneInfoNotFoundError as error:
                raise RuntimeError("Asia/Seoul time zone data is missing; install the Windows robot requirements (tzdata)") from error
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Reserve the filename before OpenCV opens it; never replace an old recording.
            with self.path.open("xb"):
                pass
            try:
                self.frames_file = self.path.with_name(self.path.stem + "_frames.jsonl").open("x", encoding="utf-8")
                writer = cv2.VideoWriter(str(self.path), cv2.VideoWriter_fourcc(*"mp4v"), self.fps, self.size)
                if not writer.isOpened():
                    writer.release()
                    raise RuntimeError(f"MP4 encoder could not open {self.path}")
                self.writer = writer
                self.started = time.monotonic()
                self.result = dict(path=str(self.path), fps=self.fps, width=self.size[0], height=self.size[1],
                                   started_at=started_at,
                                   start_monotonic_s=self.started)
                return dict(self.result, recording=True)
            except BaseException:
                if self.frames_file is not None:
                    self.frames_file.close()
                raise

    def write(self, bgr, received, frame_number, device_ms):
        with self.lock:
            if self.writer is None or received < self.started:
                return
            if (bgr.shape[1], bgr.shape[0]) != self.size:
                raise ValueError("Recording frame size differs from the camera profile")
            self.writer.write(bgr)
            self.frames_file.write(json.dumps(dict(video_frame=self.count, frame_number=frame_number,
                device_ms=device_ms, frame_monotonic_s=received, t_s=received-self.started)) + "\n")
            self.count += 1

    def stop(self):
        with self.lock:
            if self.writer is None:
                return dict(self.result or {"path": str(self.path)}, recording=False, frames=self.count)
            try:
                self.writer.release()
            finally:
                self.writer = None
                self.frames_file.close()
            self.result.update(recording=False, frames=self.count, duration_s=time.monotonic()-self.started,
                encoded_duration_s=self.count/self.fps,
                stopped_at=datetime.now(ZoneInfo("Asia/Seoul")).isoformat())
            self.path.with_name(self.path.stem + "_video.json").write_text(
                json.dumps(self.result, indent=2, ensure_ascii=False), encoding="utf-8")
            return dict(self.result)
