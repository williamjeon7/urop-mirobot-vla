"""작업 공간 변환 — Mirobot ↔ LIBERO 위치.

자세는 `common/rotation.py` 가 맡는다. 여기는 **위치**만 — 단위, 원점, 스케일, 그리고 어느 점끼리 맞추나.

* **축** — 두 로봇의 월드 축은 같다. `X↔x`(앞), `Y↔y`(로봇 기준 왼쪽), `Z↔z`(위), 부호도 같다
  (`docs/W3/LIBERO_AXES.md` 4절). 그래서 축을 바꾸거나 돌리지 않고 **변위를 그대로** 옮긴다
* **원점** — 서로 다르다. Mirobot 은 베이스 기준, LIBERO 는 월드 기준이다. 두 기준점을 짝지어 두고
  **기준점으로부터의 변위**만 옮긴다 — 기본 짝은 "Mirobot 홈 ↔ Panda 시작 자세".
  Mirobot 쪽 짝은 바꿀 수 있다 (`MAPPINGS`, 10/1) — 홈은 이미 수평 199mm 라 바깥쪽 여유가 작다
* **점** — **파지점끼리** 맞춘다 (9/30 교수님 회신, `docs/meetings/2026-09-28/Professor reply.md`).
  Mirobot 은 플랜지를 보고하고 LIBERO proprio `eef_pos` 는 파지점이라, 양쪽을 각자의 길이로 파지점까지 내려
  변위를 옮기고 Mirobot 에 줄 때 다시 플랜지로 올린다. 9/21 까지 만든 궤적·기록은 **플랜지끼리** 맞춘 것이라
  `point="flange"` 로 그대로 읽는다 — 파일 머리말에 `; point …` 표시가 없으면 플랜지다 (`LEGACY_POINT`)
* **스케일** — 변위에만 곱한다. 세 축에 같은 비율 (축마다 다르면 궤적이 찌그러진다). 짝을 중심으로 늘고 준다
* **짝과 배율은 파일에 적는다** — 새 G-code 머리말 `; pair X… Y… Z… scale …`. 실행(Panda→Mirobot)과
  학습 라벨·proprio(Mirobot→Panda)가 **같은 값**을 써야 해서, 읽는 쪽이 머리말에서 그대로 가져간다

표준 라이브러리만 쓴다 (`common/` 규약).
"""

from __future__ import annotations

import re

Vec3 = tuple[float, float, float]

# 9/13 실측 홈 — `$H` 뒤 `?` 보고. 이때 RxRyRz = (0, 0, 0) 이다 (docs/W2/CHECKLIST.md 4절)
MIROBOT_HOME_MM: Vec3 = (198.67, 0.0, 230.72)


def libero_to_mirobot_xyz_mm(p_libero_m, ref_libero_m, ref_mirobot_mm: Vec3 = MIROBOT_HOME_MM,
                             scale: float = 1.0) -> Vec3:
    """LIBERO 위치(m, 월드) → Mirobot 위치(mm). `ref_mirobot + (p − ref_libero) × 1000 × scale`.

    변위만 옮기므로 **점의 종류를 가리지 않는다** — 넣는 점과 두 기준점이 같은 종류(플랜지끼리, 파지점끼리)면 된다.
    """
    return tuple(r + (p - q) * 1000.0 * scale for p, q, r in zip(p_libero_m, ref_libero_m, ref_mirobot_mm))  # type: ignore[return-value]


def mirobot_to_libero_xyz_m(p_mirobot_mm, ref_libero_m, ref_mirobot_mm: Vec3 = MIROBOT_HOME_MM,
                            scale: float = 1.0) -> Vec3:
    """Mirobot 위치(mm) → LIBERO 위치(m, 월드). 위 함수의 역."""
    return tuple(q + (p - r) / 1000.0 / scale for p, q, r in zip(p_mirobot_mm, ref_libero_m, ref_mirobot_mm))  # type: ignore[return-value]


# ── 플랜지 ↔ 파지점 (docs/W3/CONTROL.md 2절) ───────────────────
# Panda 의 proprio `eef_pos` 는 파지점이고 플랜지는 그보다 공구 축(z)으로 97mm 위다.
# 컨트롤러가 움직이는 점도 파지점이라, 플랜지 목표를 줄 때는 파지점 목표로 바꿔서 넣어야 한다.
PANDA_FLANGE_TO_GRIP_M = 0.097  # robosuite/models/assets/grippers/panda_gripper.xml:20-21


def flange_to_grip(p_flange, q_wxyz, offset_m: float = PANDA_FLANGE_TO_GRIP_M) -> Vec3:
    """플랜지 위치 → 파지점 위치. 공구 축(회전행렬 3열) 방향으로 offset 만큼 내려간다.

    **LIBERO 자세 규약**의 쿼터니언을 넣는다 — 3열이 손가락 쪽을 향하는 규약이다. 단위는 가리지 않는다
    (위치가 mm 면 offset 도 mm 로 준다).
    """
    from common.rotation import quat_to_matrix  # 위치가 회전을 쓰는 유일한 자리

    z_axis = [quat_to_matrix(q_wxyz)[i][2] for i in range(3)]
    return tuple(p + a * offset_m for p, a in zip(p_flange, z_axis))  # type: ignore[return-value]


def grip_to_flange(p_grip, q_wxyz, offset_m: float = PANDA_FLANGE_TO_GRIP_M) -> Vec3:
    """파지점 위치 → 플랜지 위치."""
    return flange_to_grip(p_grip, q_wxyz, -offset_m)


# Mirobot 은 플랜지만 보고한다. 파지점은 거기서 공구 축으로 55mm 아래다 — 9/21 자로 잰 값, ±5mm
# (docs/W3/CHECKLIST.md 8절). **이 ±5mm 는 왕복 검증으로는 안 보인다** — 나갈 때와 들어올 때 같은 값을 써서
# 상쇄된다(`F` 와 같은 구조). 외부 측정(캘리퍼스)으로만 줄일 수 있다.
MIROBOT_FLANGE_TO_GRIP_M = 0.055

# 홈에서 RxRyRz = (0,0,0) 이면 공구 축이 정확히 아래를 향한다 → 파지점은 플랜지 바로 아래 55mm
MIROBOT_HOME_GRIP_MM: Vec3 = (MIROBOT_HOME_MM[0], MIROBOT_HOME_MM[1],
                              MIROBOT_HOME_MM[2] - MIROBOT_FLANGE_TO_GRIP_M * 1000.0)


def mirobot_flange_to_grip_mm(p_flange_mm, q_mirobot_wxyz, offset_m: float = MIROBOT_FLANGE_TO_GRIP_M) -> Vec3:
    """Mirobot 플랜지(mm) → 파지점(mm).

    **Mirobot 자세 규약에서 공구 축은 −z 다.** top-down 을 (0,0,0) 으로 적어 LIBERO 규약과 `F`(x축 180°)
    만큼 다르다 (`common/rotation.py` `FRAME_F`). 그래서 LIBERO 규약으로 바꾼 뒤 `flange_to_grip` 에 넣는다 —
    Mirobot 쿼터니언을 그대로 넣으면 파지점이 55mm **위**로 잡힌다.
    """
    from common.rotation import mirobot_to_libero_quat

    return flange_to_grip(p_flange_mm, mirobot_to_libero_quat(q_mirobot_wxyz), offset_m * 1000.0)


def mirobot_grip_to_flange_mm(p_grip_mm, q_mirobot_wxyz, offset_m: float = MIROBOT_FLANGE_TO_GRIP_M) -> Vec3:
    """Mirobot 파지점(mm) → 플랜지(mm). G0 에 넣는 것은 플랜지다."""
    return mirobot_flange_to_grip_mm(p_grip_mm, q_mirobot_wxyz, -offset_m)


# ── 어느 점끼리 맞추나 ────────────────────────────────────────
# 9/21 까지는 플랜지끼리 맞췄다 — Mirobot 의 플랜지→파지점 길이를 몰라서였다 (docs/W3/CONTROL.md 2-1절).
# 9/30 회신으로 **파지점끼리** 로 바꿨다. 새 G-code 는 머리말에 `; point grip` 을 적고,
# 표시가 없는 파일(9/17~9/28 궤적)은 플랜지로 만든 것이므로 플랜지로 읽는다.
POINTS = ("grip", "flange")
DEFAULT_POINT = "grip"
LEGACY_POINT = "flange"
_POINT_RE = re.compile(r"^;\s*point\s+(grip|flange)\b", re.MULTILINE)


def point_marker(point: str) -> str:
    """G-code 머리말에 적는 줄."""
    return f"; point {point}"


def read_point_marker(text: str) -> str | None:
    """G-code 본문에서 `; point grip|flange` 를 찾는다. 없으면 None — 부르는 쪽이 `LEGACY_POINT` 로 읽는다."""
    m = _POINT_RE.search(text)
    return m.group(1) if m else None


# ── 짝과 배율 ────────────────────────────────────────────────
# Mirobot 쪽 짝을 홈(수평 199mm)에 두면 바깥쪽 여유가 경고선(280mm)까지 81mm 뿐이다. LIBERO 정책은 시작점에서
# 바깥으로 300~400mm 를 움직여서, 그대로면 배율을 0.23 까지 줄여야 들어간다. 짝을 베이스 쪽으로 당기면 배율을
# 키울 수 있다 — X 120 이면 0.44 (10/1, LIBERO-Spatial 정책 10개 에피소드 기준, docs/W5/PIPELINE.md 4-4).
# **"candidate" 는 10/5 에 내려놓았다** — 시작 자세 `G0 X123.15 Y0.01 Z230.63 …` 가 실물에서 `Soft limit:Y`(어깨 J2)로 거부됐다.
# 새 방식은 **짝은 홈 그대로, 시뮬 Panda 의 시작 자세를 거기에 맞추고, 배율은 세로 정렬 `(230.72 − Zt) / 264.1` 로** 정한다
# (docs/W5/TABLE_ALIGNMENT.md). `Zt` 가 오면 그 배율로 항목을 새로 둔다. 기록으로 남겨 두고 쓰지 않는다.
MAPPINGS: dict[str, tuple[Vec3 | None, float]] = {
    "home": (None, 1.0),                                          # 9/30 까지 — 그 점의 홈, 배율 1
    "candidate": ((120.0, 0.0, MIROBOT_HOME_GRIP_MM[2]), 0.44),   # 파지점 기준. 높이는 홈 파지점과 같다
}
DEFAULT_MAPPING = "home"

_PAIR_RE = re.compile(r"^;\s*pair\s+X(-?[\d.]+)\s+Y(-?[\d.]+)\s+Z(-?[\d.]+)\s+scale\s+([\d.]+)", re.MULTILINE)
_OLD_SCALE_RE = re.compile(r"^;.*?\bscale\s+([0-9.]+)", re.MULTILINE)  # 9/30 까지 머리말 설명 줄의 "scale 1.0"


def mirobot_home_mm(point: str) -> Vec3:
    """그 점의 Mirobot 홈 — 짝을 따로 정하지 않았을 때의 Mirobot 쪽 기준."""
    return MIROBOT_HOME_GRIP_MM if point == "grip" else MIROBOT_HOME_MM


def resolve_mapping(name: str, point: str) -> tuple[Vec3, float]:
    """이름 → (Mirobot 쪽 짝, 배율). 짝은 `point` 의 점으로 돌려준다."""
    ref, scale = MAPPINGS[name]
    if ref is None:
        return mirobot_home_mm(point), scale
    if point != "grip":
        raise ValueError(f"짝 {name!r} 은 파지점 기준으로 정한 값이다 — --point grip 으로 쓸 것")
    return ref, scale


def pair_marker(ref_mirobot_mm: Vec3, scale: float) -> str:
    """G-code 머리말에 적는 줄. 짝은 `; point` 의 점으로 적는다."""
    x, y, z = ref_mirobot_mm
    return f"; pair X{x:.2f} Y{y:.2f} Z{z:.2f} scale {scale:g}"


def read_pair_marker(text: str, point: str) -> tuple[Vec3, float]:
    """G-code 본문 → (Mirobot 쪽 짝, 배율).

    `; pair …` 가 없으면 10/1 전 파일이다 — 짝은 그 점의 홈, 배율은 옛 머리말 설명 줄의 `scale …`(없으면 1).
    """
    m = _PAIR_RE.search(text)
    if m:
        return (float(m.group(1)), float(m.group(2)), float(m.group(3))), float(m.group(4))
    old = _OLD_SCALE_RE.search(text)
    return mirobot_home_mm(point), float(old.group(1)) if old else 1.0


def libero_to_mirobot_flange_mm(p_flange_m, q_libero, q_mirobot, ref_flange_m, ref_q_libero,
                                point: str = DEFAULT_POINT, scale: float = 1.0,
                                ref_mirobot_mm: Vec3 | None = None) -> Vec3:
    """Panda 플랜지 위치(m) → Mirobot `G0` 의 `X Y Z`(플랜지, mm). `point` 끼리 변위를 옮긴다.

    q_libero        그 자리의 Panda 자세 (LIBERO 규약)
    q_mirobot       같은 자리에서 Mirobot 에 줄 자세 (Mirobot 규약 — absolute/relative 는 부르는 쪽이 정한다)
    ref_*           짝지을 Panda 기준 (보통 시작 자세)
    ref_mirobot_mm  짝지을 Mirobot 기준 — `point` 의 점으로 적는다. None 이면 그 점의 홈 (`mirobot_home_mm`)
    """
    ref_m = ref_mirobot_mm or mirobot_home_mm(point)
    if point == "flange":
        return libero_to_mirobot_xyz_mm(p_flange_m, ref_flange_m, ref_m, scale)
    grip = libero_to_mirobot_xyz_mm(flange_to_grip(p_flange_m, q_libero), flange_to_grip(ref_flange_m, ref_q_libero),
                                    ref_m, scale)
    return mirobot_grip_to_flange_mm(grip, q_mirobot)


def mirobot_to_libero_flange_m(p_mirobot_mm, q_mirobot, q_libero, ref_flange_m, ref_q_libero,
                               point: str = DEFAULT_POINT, scale: float = 1.0,
                               ref_mirobot_mm: Vec3 | None = None) -> Vec3:
    """Mirobot `X Y Z`(플랜지, mm — G0 든 `?` 보고값이든) → Panda 플랜지 위치(m). 위 함수의 역."""
    ref_m = ref_mirobot_mm or mirobot_home_mm(point)
    if point == "flange":
        return mirobot_to_libero_xyz_m(p_mirobot_mm, ref_flange_m, ref_m, scale)
    grip = mirobot_to_libero_xyz_m(mirobot_flange_to_grip_mm(p_mirobot_mm, q_mirobot),
                                   flange_to_grip(ref_flange_m, ref_q_libero), ref_m, scale)
    return grip_to_flange(grip, q_libero)
