"""실물 Mirobot 관측 → 정책 입력 (W10, docs/W10/POLICY_RUN.md).

정책을 실물에서 돌릴 때 카메라 프레임과 `?` 응답을 학습 HDF5 와 **같은 계산**으로 바꾼다.
학습 데이터를 만든 동료 코드(`docs/W9/d405/`)를 그대로 불러 쓰고, 고치거나 복사하지 않는다.

* `wrist_from_rgb` — D405 RGB 프레임(640×480, RGB 순서) → 256×256 손목 영상.
  `export_hdf5.wrist_image` 와 같은 순서: 색 보정 → 가운데 정사각 자르기 → INTER_AREA 축소
* `MirobotFrame` — 녹화 때 쓴 좌표 기준(`reference.jsonl` meta, `source.gcode` 머리말)을 들고,
  `?` 응답 위치·자세 → LIBERO 자세, 집게 명령 기록 → 손가락 2칸(B'), 둘을 합쳐 `robot_states` 9칸
* `latest_closure` — 집게 명령 기록 → 지금 닫힌 정도 (0 열림 ~ 1 잡음). `prepare.gripper_track` 을 그대로 쓴다
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from common.policy_io import libero_to_mirobot_pose
from common.proprio import fingers, mirobot_to_libero_pose, robot_states, settings_from_gcode
from common.rotation import quat_xyzw_to_wxyz
from common.workspace import grip_to_flange
from docs.W9.d405.color_calibration import apply_rgb, load_profile
from docs.W9.d405.prepare import gripper_track

IMAGE_SIZE = 256


def wrist_from_rgb(rgb: np.ndarray, profile, rotate: int = 0) -> np.ndarray:
    """RGB uint8 (H, W, 3) → 학습과 같은 256×256 손목 영상."""
    image = apply_rgb(rgb, profile)
    image = np.rot90(image, rotate // 90)
    h, w = image.shape[:2]
    n = min(h, w)
    image = image[(h - n) // 2:(h + n) // 2, (w - n) // 2:(w + n) // 2]
    return cv2.resize(image, (IMAGE_SIZE, IMAGE_SIZE), interpolation=cv2.INTER_AREA)


def read_rgb(path) -> np.ndarray:
    """녹화 PNG → RGB. `capture_storage.read_image` 와 같이 읽는다 (한글 경로 대응)."""
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Unreadable PNG: {path}")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def latest_closure(commands, t_s: float, duration_s: float, initial_s: float, open_s: float,
                   closed_s: float) -> float:
    """집게 명령 기록(`{"t_s", "cmd": "M4 S60"}` 목록) → 시각 `t_s` 의 닫힌 정도."""
    closed, _ = gripper_track(commands, [t_s], duration_s, initial_s, open_s, closed_s)
    return float(closed[0])


class MirobotFrame:
    """녹화 때의 좌표 기준. 실행 때도 같은 기준 파일을 쓴다 (세 색 seed 2 기준은 값이 같다)."""

    def __init__(self, reference_meta: dict, gcode_text: str):
        self.settings = settings_from_gcode(gcode_text)
        self.ref_q = quat_xyzw_to_wxyz(tuple(reference_meta["start_eef_quat_xyzw"]))
        self.ref_flange = grip_to_flange(reference_meta["start_eef_pos"], self.ref_q)

    @classmethod
    def from_files(cls, reference_jsonl, gcode) -> "MirobotFrame":
        first = json.loads(Path(reference_jsonl).read_text(encoding="utf-8").splitlines()[0])
        return cls(first.get("meta", first), Path(gcode).read_text(encoding="utf-8"))

    def to_libero(self, cart6):
        """`?` 보고 X Y Z(mm) A B C(도) → LIBERO 파지점 위치(m), 자세(wxyz)."""
        return mirobot_to_libero_pose(cart6[:3], cart6[3:6], self.ref_flange, self.ref_q, self.settings)

    def to_mirobot(self, pos_m, q_wxyz):
        """LIBERO 파지점 자세 → Mirobot 플랜지 X Y Z(mm), A B C(도). 실행 명령에 쓴다."""
        return libero_to_mirobot_pose(pos_m, q_wxyz, self.ref_flange, self.ref_q, self.settings)

    def proprio(self, cart6, closure: float) -> np.ndarray:
        """학습 HDF5 `robot_states` 와 같은 9칸 (손가락 2 · 위치 3 · 쿼터니언 xyzw 4)."""
        pos, q = self.to_libero(cart6)
        return np.asarray(robot_states(fingers(closure), pos, q), np.float32)
