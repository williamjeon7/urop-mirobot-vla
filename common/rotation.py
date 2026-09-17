"""회전 표현 변환 — Mirobot 오일러각 ↔ 쿼터니언 ↔ axis-angle.

규약과 근거는 `docs/W3/ROTATION.md` 에 있다. 요약만 옮기면:

* Mirobot `RxRyRz` 는 **extrinsic XYZ**, 단위는 **도** — `R = Rz·Ry·Rx` (4절)
* 이 모듈 안에서 쿼터니언은 **언제나 `wxyz`** 다. `xyzw` 는 LIBERO 로 나갈 때만 쓰고
  함수 이름에 순서를 박는다 (5절)
* `q` 와 `−q` 는 같은 자세다. 궤적의 부호는 따로 맞춘다 (7절)

**표준 라이브러리만 쓴다.** 로봇 노트북에는 numpy 가 명시돼 있지 않고(`requirements/robot.txt`),
여기서 다루는 것은 숫자 3~4개짜리 계산이라 numpy 가 이득도 아니다.
"""

from __future__ import annotations

import math

# 쿼터니언은 wxyz 순서의 길이 4 튜플이다.
Quat = tuple[float, float, float, float]

IDENTITY: Quat = (1.0, 0.0, 0.0, 0.0)


def quat_normalize(q: Quat) -> Quat:
    """길이를 1 로 맞춘다. 곱을 반복하면 부동소수 오차가 쌓인다."""
    w, x, y, z = q
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if n == 0.0:
        raise ValueError("길이가 0 인 쿼터니언은 회전이 아니다")
    return (w / n, x / n, y / n, z / n)


def quat_mul(a: Quat, b: Quat) -> Quat:
    """쿼터니언 곱 `a ⊗ b` — "b 를 먼저, a 를 나중에" 적용한 회전이다."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def quat_from_axis_deg(axis: str, deg: float) -> Quat:
    """x·y·z 한 축 둘레의 회전. `q = [cos(θ/2), 축·sin(θ/2)]`."""
    half = math.radians(deg) / 2.0
    c, s = math.cos(half), math.sin(half)
    if axis == "x":
        return (c, s, 0.0, 0.0)
    if axis == "y":
        return (c, 0.0, s, 0.0)
    if axis == "z":
        return (c, 0.0, 0.0, s)
    raise ValueError(f"축은 x·y·z 중 하나여야 한다: {axis!r}")


def euler_xyz_deg_to_quat(rx: float, ry: float, rz: float) -> Quat:
    """Mirobot `RxRyRz`(도, extrinsic XYZ) → 쿼터니언 `wxyz`.

    고정축 x→y→z 순서라 나중 회전이 왼쪽에 붙는다 — `R = Rz·Ry·Rx`,
    쿼터니언으로는 `qz ⊗ qy ⊗ qx` (ROTATION.md 4절).
    """
    qx = quat_from_axis_deg("x", rx)
    qy = quat_from_axis_deg("y", ry)
    qz = quat_from_axis_deg("z", rz)
    return quat_normalize(quat_mul(qz, quat_mul(qy, qx)))


def quat_to_matrix(q: Quat) -> tuple[tuple[float, float, float], ...]:
    """쿼터니언 `wxyz` → 3×3 회전행렬.

    모든 항이 성분 둘의 곱이라 `q` 와 `−q` 가 같은 행렬을 준다 (ROTATION.md 7절).
    """
    w, x, y, z = quat_normalize(q)
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
        (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
        (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)),
    )


# ry 가 ±90° 에 이만큼 가까우면 짐벌락으로 본다. cos(ry) 가 이 값 아래로 내려가면
# rx 와 rz 가 한 자유도로 합쳐져 따로 뽑을 수 없다.
GIMBAL_EPS = 1e-9


def quat_to_euler_xyz_deg(q: Quat) -> tuple[float, float, float]:
    """쿼터니언 `wxyz` → Mirobot `RxRyRz`(도, extrinsic XYZ).

    `R = Rz·Ry·Rx` 의 마지막 행이 `[−sin(ry), cos(ry)·sin(rx), cos(ry)·cos(rx)]` 다.
    여기서 `ry` 를 먼저 뽑고 나머지를 `atan2` 로 구한다.

    **짐벌락** (`ry = ±90°`) 에서는 `rx` 와 `rz` 가 한 자유도로 합쳐진다. 답이 무수히 많으므로
    `rx = 0` 으로 두고 전부 `rz` 에 몰아준다 — 자세는 같지만 값은 원래 입력과 다를 수 있다.
    """
    m = quat_to_matrix(q)
    cos_ry = math.sqrt(m[0][0] * m[0][0] + m[1][0] * m[1][0])
    ry = math.atan2(-m[2][0], cos_ry)

    if cos_ry < GIMBAL_EPS:
        rx = 0.0
        # ry = +90° 면 R01 = sin(rx−rz), R02 = cos(rx−rz) / −90° 면 부호가 뒤집힌다
        rz = math.atan2(-m[0][1], m[0][2]) if m[2][0] < 0 else math.atan2(-m[0][1], -m[0][2])
    else:
        rx = math.atan2(m[2][1], m[2][2])
        rz = math.atan2(m[1][0], m[0][0])

    return (math.degrees(rx), math.degrees(ry), math.degrees(rz))


def quat_conj(q: Quat) -> Quat:
    """켤레 = 단위 쿼터니언의 역회전."""
    w, x, y, z = q
    return (w, -x, -y, -z)


# ── 저장 순서 (ROTATION.md 5절) ────────────────────────────────
# 모듈 안에서는 wxyz 로만 다루고, 바깥으로 나갈 때만 바꾼다.
# LIBERO·robosuite·scipy·ROS 가 xyzw, MuJoCo·Eigen·common/schema.py 가 wxyz 다.


def quat_wxyz_to_xyzw(q: Quat) -> tuple[float, float, float, float]:
    """우리 `wxyz` → LIBERO proprio 의 `xyzw` (`robosuite/robots/single_arm.py:309`)."""
    w, x, y, z = q
    return (x, y, z, w)


def quat_xyzw_to_wxyz(q: tuple[float, float, float, float]) -> Quat:
    """LIBERO `xyzw` → 우리 `wxyz`."""
    x, y, z, w = q
    return (w, x, y, z)


# ── axis-angle (ROTATION.md 1절, 5-2 의 데이터셋 `ee_ori`) ──────
# 축 단위벡터 × 각도(rad). 크기가 곧 회전량이라 델타를 적기 좋다.


def axis_angle_to_quat(vec: tuple[float, float, float]) -> Quat:
    """axis-angle(rad) → 쿼터니언 `wxyz`. 크기가 0 이면 항등."""
    ax, ay, az = vec
    angle = math.sqrt(ax * ax + ay * ay + az * az)
    if angle < 1e-12:
        return IDENTITY
    half = angle / 2.0
    s = math.sin(half) / angle  # 축 정규화와 sin 을 한 번에
    return (math.cos(half), ax * s, ay * s, az * s)


def quat_to_axis_angle(q: Quat) -> tuple[float, float, float]:
    """쿼터니언 `wxyz` → axis-angle(rad). **항상 짧은 쪽**(각도 ≤ 180°) 으로 돌려준다.

    robosuite 의 `quat2axisangle` 은 `w < 0` 일 때 각도가 180° 를 넘어 최대 360° 까지 나온다
    (`utils/transform_utils.py:490`). 우리는 `w ≥ 0` 으로 뒤집고 시작한다 — 액션 델타는
    짧은 쪽이어야 하기 때문이다 (ROTATION.md 7절). 자세는 어느 쪽이든 같다.
    """
    w, x, y, z = quat_normalize(q)
    if w < 0.0:  # q 와 −q 는 같은 자세. 짧은 쪽을 고른다
        w, x, y, z = -w, -x, -y, -z
    sin_half = math.sqrt(x * x + y * y + z * z)
    if sin_half < 1e-12:
        return (0.0, 0.0, 0.0)
    angle = 2.0 * math.atan2(sin_half, w)  # acos(w) 보다 0·180° 근처에서 안정적이다
    k = angle / sin_half
    return (x * k, y * k, z * k)


# ── 궤적과 오차 (ROTATION.md 7절) ──────────────────────────────


def enforce_sign_continuity(quats, q_prev: Quat | None = None) -> list[Quat]:
    """궤적의 쿼터니언 부호를 이웃끼리 맞춘다.

    `q` 와 `−q` 는 같은 자세지만 숫자로는 가장 멀다(거리 2.0). 스텝마다 부호가 뒤집히면
    정책 입력·보간·오차 계산이 없던 급회전을 본다. **직전과 내적이 음수면 뒤집는다.**

    `w ≥ 0` 으로 맞추는 흔한 방법은 쓰지 않는다 — top-down 이 x축 180° 라 `w ≈ 0` 이고,
    그 근처에서는 스텝마다 뒤집힌다 (7절 측정: 최대 튐 2.000 vs 0.009).

    `q_prev` 는 이어서 재생할 때 **직전 상태**를 넣는 자리다. 없으면 첫 값은 그대로 둔다 —
    궤적 바깥과 비교되지 않는 한 전체 부호는 행동을 바꾸지 않는다.
    """
    out: list[Quat] = []
    ref = q_prev
    for q in quats:
        q = tuple(float(v) for v in q)  # 리스트로 들어와도 받는다
        if ref is not None and sum(a * b for a, b in zip(q, ref)) < 0.0:
            q = tuple(-v for v in q)
        out.append(q)  # type: ignore[arg-type]
        ref = q
    return out


def quat_error_axis_angle(q_current: Quat, q_target: Quat) -> tuple[float, float, float]:
    """현재 자세에서 목표 자세로 가는 회전을 axis-angle(rad) 로. **OSC_POSE 액션의 회전 3칸**이다.

    robosuite 는 델타를 **월드 프레임에서 왼쪽에 곱한다** — `goal = R_delta · R_current`
    (`robosuite/utils/control_utils.py:177`). 그래서 `q_err = q_target ⊗ q_current⁻¹` 다.

    부호는 **이 함수 안에서** 맞춘다 (`quat_to_axis_angle` 이 짧은 쪽을 고른다). 호출하는 쪽이
    `q` 와 `−q` 를 신경 쓰지 않아도 되게 하려는 것이다 — 안 그러면 10° 돌 것을 350° 돈다.
    """
    return quat_to_axis_angle(quat_mul(q_target, quat_conj(q_current)))


# ── 프레임 회전 (ROTATION.md 6절, LIBERO_AXES.md 4절) ──────────
# q_libero = q_mirobot ⊗ F. 두 로봇의 월드 축은 같고(평행이동만 다르다) 공구 좌표축만 돌아가 있다.
# Mirobot 은 top-down 을 (0,0,0) 으로, LIBERO 는 x축 180° 로 적는다.
#
# **확정 (9/17)** — LIBERO 회전 축 시험에서 Ry·Rz 부호가 오른쪽 곱으로만 맞았고, Mirobot 실물에서
# Y+ = 로봇 기준 왼쪽, 그리퍼 조 좌우(Panda 와 같음)를 확인해 공구 축 90° 도 붙지 않는다 (docs/W3/CHECKLIST.md 8절).
# 실물에서 A15·B15·C20 이 LIBERO 의 Δrx+·Δry+·Δrz+ 와 같은 쪽으로 기울고 돈 것도 눈으로 봤다.
FRAME_F: Quat = quat_from_axis_deg("x", 180.0)


def mirobot_to_libero_quat(q_mirobot: Quat) -> Quat:
    """Mirobot 자세(wxyz) → LIBERO 자세(wxyz). `q ⊗ F` — 오른쪽 곱이라 월드 축 회전은 그대로 옮겨진다."""
    return quat_mul(q_mirobot, FRAME_F)


def libero_to_mirobot_quat(q_libero: Quat) -> Quat:
    """LIBERO 자세(wxyz) → Mirobot 자세(wxyz). `q ⊗ F⁻¹`."""
    return quat_mul(q_libero, quat_conj(FRAME_F))
