"""Verify real MP4 encoding and recording boundaries using temporary frames."""
import json
import time
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError

import cv2
import numpy as np
import pytest

from robot.policy_video import PolicyVideo


def test_video_records_only_between_start_and_stop_and_decodes(tmp_path):
    path = tmp_path / "I1/I1.mp4"
    video = PolicyVideo(path, 64, 48, 30)
    frame = np.full((48, 64, 3), (10, 20, 220), dtype=np.uint8)
    video.write(frame, time.monotonic(), 0, 0)
    assert not path.exists()
    video.start()
    for i in range(12):
        video.write(frame, time.monotonic(), i, i*1000/30)
    result = video.stop()
    video.write(frame, time.monotonic(), 99, 999)
    assert result["frames"] == 12
    assert video.stop()["frames"] == 12
    cap = cv2.VideoCapture(str(path))
    try:
        assert cap.isOpened()
        assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 12
        ok, decoded = cap.read()
        assert ok and decoded.shape == (48, 64, 3)
        assert decoded[..., 2].mean() > 200
    finally:
        cap.release()
    rows = [json.loads(line) for line in (path.parent / "I1_frames.jsonl").read_text().splitlines()]
    assert len(rows) == 12
    assert rows[-1]["frame_number"] == 11
    assert json.loads((path.parent / "I1_video.json").read_text())["recording"] is False
    with pytest.raises(RuntimeError, match="already finished"):
        video.start()


def test_video_does_not_overwrite_existing_file(tmp_path):
    path = tmp_path / "I1.mp4"
    path.write_bytes(b"keep original")
    with pytest.raises(FileExistsError):
        PolicyVideo(path, 64, 48, 30).start()
    assert path.read_bytes() == b"keep original"


def test_missing_timezone_fails_before_creating_files_or_opening_writer(tmp_path):
    path = tmp_path / "I1/I1.mp4"
    video = PolicyVideo(path, 64, 48, 30)
    with patch("robot.policy_video.ZoneInfo", side_effect=ZoneInfoNotFoundError("Asia/Seoul")), \
         patch.object(cv2, "VideoWriter") as writer:
        with pytest.raises(RuntimeError, match="tzdata"):
            video.start()
    writer.assert_not_called()
    assert video.writer is None
    assert video.result is None
    assert not path.parent.exists()
