"""작업 공간 변환 — Mirobot ↔ LIBERO 위치.

자세는 `common/rotation.py` 가 맡는다. 여기는 **위치**만 — 단위, 원점, 스케일.

* **축** — 두 로봇의 월드 축은 같다. `X↔x`(앞), `Y↔y`(로봇 기준 왼쪽), `Z↔z`(위), 부호도 같다
  (`docs/W3/LIBERO_AXES.md` 4절). 그래서 축을 바꾸거나 돌리지 않고 **변위를 그대로** 옮긴다
* **원점** — 서로 다르다. Mirobot 은 베이스 기준, LIBERO 는 월드 기준이다. 두 기준점을 짝지어 두고
  **기준점으로부터의 변위**만 옮긴다 — 기본 짝은 "Mirobot 홈 ↔ Panda 시작 자세"
* **점** — 플랜지끼리 맞춘다. Mirobot 은 플랜지를 보고하고, LIBERO 는 `robot0_right_hand` 바디 위치를 쓴다
  (proprio 의 `eef_pos` 는 그보다 9.7cm 아래 파지점이다 — LIBERO_AXES.md 0절)
* **스케일** — 변위에만 곱한다. 세 축에 같은 비율 (축마다 다르면 궤적이 찌그러진다)

표준 라이브러리만 쓴다 (`common/` 규약).
"""

from __future__ import annotations

Vec3 = tuple[float, float, float]

# 9/13 실측 홈 — `$H` 뒤 `?` 보고. 이때 RxRyRz = (0, 0, 0) 이다 (docs/W2/CHECKLIST.md 4절)
MIROBOT_HOME_MM: Vec3 = (198.67, 0.0, 230.72)


def libero_to_mirobot_xyz_mm(p_libero_m, ref_libero_m, ref_mirobot_mm: Vec3 = MIROBOT_HOME_MM,
                             scale: float = 1.0) -> Vec3:
    """LIBERO 플랜지 위치(m, 월드) → Mirobot `X Y Z`(mm). `ref_mirobot + (p − ref_libero) × 1000 × scale`."""
    return tuple(r + (p - q) * 1000.0 * scale for p, q, r in zip(p_libero_m, ref_libero_m, ref_mirobot_mm))  # type: ignore[return-value]


def mirobot_to_libero_xyz_m(p_mirobot_mm, ref_libero_m, ref_mirobot_mm: Vec3 = MIROBOT_HOME_MM,
                            scale: float = 1.0) -> Vec3:
    """Mirobot `X Y Z`(mm) → LIBERO 플랜지 위치(m, 월드). 위 함수의 역."""
    return tuple(q + (p - r) / 1000.0 / scale for p, q, r in zip(p_mirobot_mm, ref_libero_m, ref_mirobot_mm))  # type: ignore[return-value]


# ── 플랜지 ↔ 파지점 (docs/W3/CONTROL.md 2절) ───────────────────
# Panda 의 proprio `eef_pos` 는 파지점이고 플랜지는 그보다 공구 축(z)으로 97mm 위다.
# 컨트롤러가 움직이는 점도 파지점이라, 플랜지 목표를 줄 때는 파지점 목표로 바꿔서 넣어야 한다.
PANDA_FLANGE_TO_GRIP_M = 0.097  # robosuite/models/assets/grippers/panda_gripper.xml:20-21


def flange_to_grip(p_flange, q_wxyz, offset_m: float = PANDA_FLANGE_TO_GRIP_M) -> Vec3:
    """플랜지 위치 → 파지점 위치. 공구 축(회전행렬 3열) 방향으로 offset 만큼 내려간다."""
    from common.rotation import quat_to_matrix  # 위치가 회전을 쓰는 유일한 자리

    z_axis = [quat_to_matrix(q_wxyz)[i][2] for i in range(3)]
    return tuple(p + a * offset_m for p, a in zip(p_flange, z_axis))  # type: ignore[return-value]


def grip_to_flange(p_grip, q_wxyz, offset_m: float = PANDA_FLANGE_TO_GRIP_M) -> Vec3:
    """파지점 위치 → 플랜지 위치."""
    return flange_to_grip(p_grip, q_wxyz, -offset_m)
