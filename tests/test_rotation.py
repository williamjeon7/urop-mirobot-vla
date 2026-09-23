"""`common/rotation.py` 확인 테스트.

`docs/W3/ROTATION.md` 1~7절에서 정한 규약을 하나씩 못 박는다. 규약은 틀려도 숫자가
멀쩡해 보이기 때문에(norm 은 늘 1 이다) "답을 이미 아는 경우" 로만 검사한다.

**왕복 테스트는 충분하지 않다.** 두 방향이 나란히 같은 규약으로 틀리면 왕복은 통과한다.
그래서 바깥 기준(9/13 실측, 문서에 적힌 각도, scipy) 과 맞춰 보는 항목이 따로 있다.

    T1   (0,0,0) → 항등
    T2   한 축씩 90° — 성분 자리와 부호
    T3   extrinsic 과 intrinsic 이 44.90° 다르다        ← 곱 순서를 잡는다
    T4   9/13 실측 재현 (Ry10 → J6 10°)                 ← 규약 자체를 잡는다
    T5   왕복 — 오일러 → 쿼터니언 → 오일러 → 쿼터니언
    T6   wxyz ↔ xyzw, LIBERO 샘플 읽기                  ← 저장 순서를 잡는다
    T7   axis-angle 왕복
    T8   부호 연속성 — 176°→184° 스윕
    T9   오차 함수가 −q 를 알아서 처리하는가
    T10  짐벌락 ry = ±90°
    T11  불변량 — norm, 회전행렬 직교·det=+1
    T12  scipy 대조 (서버 .venv 에만 있다. 없으면 skip)  ← 독립 구현과 대조
    T13  프레임 회전 F — 홈, 왕복, LIBERO 실측으로 post/pre 가르기  ← 기준 프레임을 잡는다

pytest 없이도 돌아간다:

    python -m tests.test_rotation      # 또는 pytest tests/test_rotation.py

저장소 최상위에서 `-m` 으로 부른다. `python tests/test_rotation.py` 는 검색 경로에
`tests/` 만 들어가서 `common` 을 못 찾는다 (env 에 `pip install -e .` 가 돼 있으면 예외).
"""

from __future__ import annotations

import math
import random

from common.rotation import (
    IDENTITY,
    euler_xyz_deg_to_quat,
    quat_from_axis_deg,
    FRAME_F,
    axis_angle_to_quat,
    enforce_sign_continuity,
    libero_to_mirobot_quat,
    mirobot_to_libero_quat,
    quat_conj,
    quat_mul,
    quat_error_axis_angle,
    quat_to_axis_angle,
    quat_to_euler_xyz_deg,
    quat_to_matrix,
    quat_normalize,
    quat_wxyz_to_xyzw,
    quat_xyzw_to_wxyz,
)


def angle_between_deg(q1, q2) -> float:
    """두 쿼터니언이 나타내는 자세의 차이(도).

    `acos(dot)` 를 쓰지 않는다 — 두 자세가 거의 같을 때(dot ≈ 1) acos 는 정밀도를 잃어
    실제로는 0 인 차이를 1e-6° 쯤으로 보고한다. 상대 회전을 구해 `atan2` 로 뽑으면
    0 근처에서도 안정적이다. `|r_w|` 의 절댓값이 q = −q 를 흡수한다.
    """
    r = quat_mul(quat_conj(q1), q2)
    return math.degrees(2.0 * math.atan2(math.sqrt(r[1] ** 2 + r[2] ** 2 + r[3] ** 2), abs(r[0])))


def test_t1_identity():
    q = euler_xyz_deg_to_quat(0.0, 0.0, 0.0)
    assert angle_between_deg(q, IDENTITY) < 1e-9


def test_t2_single_axis():
    c = math.cos(math.radians(45.0))  # 90° 의 절반
    for axis, (rx, ry, rz), idx in [("x", (90, 0, 0), 1), ("y", (0, 90, 0), 2), ("z", (0, 0, 90), 3)]:
        q = euler_xyz_deg_to_quat(rx, ry, rz)
        assert abs(q[0] - c) < 1e-12, f"{axis}: w 가 cos45 가 아니다 — {q}"
        assert abs(q[idx] - c) < 1e-12, f"{axis}: {axis} 자리가 sin45 가 아니다 — {q}"
        assert sum(abs(v) for i, v in enumerate(q) if i not in (0, idx)) < 1e-12, f"{axis}: 다른 축이 섞였다 — {q}"


def test_t3_extrinsic_vs_intrinsic():
    """같은 숫자를 두 규약으로 읽으면 44.90° 어긋난다 (ROTATION.md 4절)."""
    rx, ry, rz = 30.0, 40.0, 50.0
    qx, qy, qz = (quat_from_axis_deg(a, d) for a, d in (("x", rx), ("y", ry), ("z", rz)))
    extrinsic = euler_xyz_deg_to_quat(rx, ry, rz)          # Rz·Ry·Rx
    intrinsic = quat_mul(qx, quat_mul(qy, qz))             # Rx·Ry·Rz
    assert angle_between_deg(extrinsic, quat_mul(qz, quat_mul(qy, qx))) < 1e-12
    assert abs(angle_between_deg(extrinsic, intrinsic) - 44.90) < 0.01


def test_t4_measured_9_13():
    """9/13 실측 — J5 를 y 로 10° 기울이고 J6(공구축) 로 10° 돌린 자세.

    물리 회전은 `Ry(10)·Rz(10)`, 로봇이 보고한 값은 `RxRyRz = (1.755, 9.853, 10.151)`.
    extrinsic 으로 읽어야 이 둘이 같아진다 (ROTATION.md 4절).
    """
    physical = quat_mul(quat_from_axis_deg("y", 10.0), quat_from_axis_deg("z", 10.0))
    reported = euler_xyz_deg_to_quat(1.755, 9.853, 10.151)
    assert angle_between_deg(physical, reported) < 0.02, angle_between_deg(physical, reported)

    intrinsic_reading = quat_mul(
        quat_from_axis_deg("x", 1.755),
        quat_mul(quat_from_axis_deg("y", 9.853), quat_from_axis_deg("z", 10.151)),
    )
    assert angle_between_deg(physical, intrinsic_reading) > 1.0  # 잘못 읽으면 확실히 벌어진다


def test_t5_round_trip():
    """오일러 → 쿼터니언 → 오일러 → 쿼터니언 이 같은 회전인가.

    오일러 값 자체를 비교하지 않는 이유는 같은 자세를 적는 방법이 여럿이기 때문이다
    (짐벌락, ±180°). **자세로 비교한다.** 이 테스트만으로는 규약을 잡지 못한다 — T3·T4 가 그 몫이다.
    """
    rng = random.Random(0)
    worst = 0.0
    for _ in range(1000):
        e = (rng.uniform(-180, 180), rng.uniform(-90, 90), rng.uniform(-180, 180))
        q = euler_xyz_deg_to_quat(*e)
        q2 = euler_xyz_deg_to_quat(*quat_to_euler_xyz_deg(q))
        worst = max(worst, angle_between_deg(q, q2))
    assert worst < 1e-9, f"왕복 오차 {worst}°"


def test_t10_gimbal_lock():
    """ry = ±90° — rx 와 rz 가 한 자유도로 합쳐진다."""
    for ry in (90.0, -90.0):
        for rx, rz in [(0.0, 0.0), (30.0, 0.0), (0.0, 30.0), (25.0, -40.0)]:
            q = euler_xyz_deg_to_quat(rx, ry, rz)
            out = quat_to_euler_xyz_deg(q)
            assert all(math.isfinite(v) for v in out), f"NaN/inf — {out}"
            assert abs(out[0]) < 1e-9, f"짐벌락에서는 rx 를 0 으로 몰아준다 — {out}"
            assert abs(abs(out[1]) - 90.0) < 1e-9, f"ry 가 ±90° 가 아니다 — {out}"
            # 값은 달라도 자세는 같아야 한다
            assert angle_between_deg(q, euler_xyz_deg_to_quat(*out)) < 1e-9


# 9/15 OASYS 첫 관측의 robot0_eef_quat. LIBERO 가 내보낸 값이므로 xyzw 다 (ROTATION.md 5절).
LIBERO_FIRST_OBS_XYZW = (0.9998, -0.0122, 0.0146, -0.0012)


def test_t6_storage_order():
    """`wxyz` ↔ `xyzw`. 같은 네 숫자가 순서에 따라 전혀 다른 자세가 된다."""
    q = euler_xyz_deg_to_quat(10.0, 20.0, 30.0)
    assert quat_xyzw_to_wxyz(quat_wxyz_to_xyzw(q)) == q
    w, x, y, z = q
    assert quat_wxyz_to_xyzw(q) == (x, y, z, w)

    # xyzw 로 읽으면 top-down(x축 약 180°), wxyz 로 읽으면 거의 항등이다 — 177° 차이
    #
    # ROTATION.md 5절 표는 이 자세를 180.14° 로 적었는데, 여기서는 179.86° 다.
    # 우리 함수가 **짧은 쪽**을 돌려주기 때문이다 (360 − 180.14). 축을 반대로 잡은 같은 자세다.
    as_xyzw = quat_xyzw_to_wxyz(LIBERO_FIRST_OBS_XYZW)
    as_wxyz = LIBERO_FIRST_OBS_XYZW
    assert abs(angle_between_deg(as_xyzw, IDENTITY) - 179.86) < 0.05
    assert abs(angle_between_deg(as_wxyz, IDENTITY) - 2.18) < 0.05
    # 축도 갈린다: xyzw 로 읽어야 x 축 둘레다 (그리퍼가 아래를 본다)
    ax, ay, az = quat_to_axis_angle(as_xyzw)
    norm = math.sqrt(ax * ax + ay * ay + az * az)
    assert abs(ax) / norm > 0.999, (ax, ay, az)


def test_t7_axis_angle():
    """axis-angle ↔ 쿼터니언. 5-2 의 데이터셋 `ee_ori` 가 이 형식이다."""
    q = axis_angle_to_quat((0.0, 0.0, math.pi / 2))
    assert angle_between_deg(q, quat_from_axis_deg("z", 90.0)) < 1e-12

    assert axis_angle_to_quat((0.0, 0.0, 0.0)) == IDENTITY
    assert quat_to_axis_angle(IDENTITY) == (0.0, 0.0, 0.0)

    rng = random.Random(1)
    worst = 0.0
    for _ in range(1000):
        vec = tuple(rng.uniform(-1.8, 1.8) for _ in range(3))  # 크기 최대 약 3.1rad
        q = axis_angle_to_quat(vec)
        worst = max(worst, angle_between_deg(q, axis_angle_to_quat(quat_to_axis_angle(q))))
    assert worst < 1e-9, f"왕복 오차 {worst}°"

    # 항상 짧은 쪽으로 — 입력을 뒤집어도 같은 벡터가 나온다 (robosuite 와 다른 점)
    q = euler_xyz_deg_to_quat(170.0, 0.0, 0.0)
    flipped = tuple(-v for v in q)
    assert max(abs(a - b) for a, b in zip(quat_to_axis_angle(q), quat_to_axis_angle(flipped))) < 1e-12
    assert math.degrees(math.sqrt(sum(v * v for v in quat_to_axis_angle(flipped)))) <= 180.0 + 1e-9


def _jump(a, b) -> float:
    """숫자 거리 ‖a − b‖. 자세가 아니라 **네 숫자**의 거리다 (ROTATION.md 7절)."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def test_t8_sign_continuity():
    """176°→184° 스윕. 1° 씩 움직이므로 정상 튐은 약 0.009 다."""
    raw = [quat_from_axis_deg("x", deg) for deg in range(176, 185)]
    w_positive = [q if q[0] >= 0 else tuple(-v for v in q) for q in raw]  # 흔한 규칙 A
    assert max(_jump(a, b) for a, b in zip(w_positive, w_positive[1:])) > 1.9  # 180° 를 넘을 때 뒤집힌다

    fixed = enforce_sign_continuity(w_positive)
    assert max(_jump(a, b) for a, b in zip(fixed, fixed[1:])) < 0.01

    # 자세는 건드리지 않는다
    assert all(angle_between_deg(a, b) < 1e-9 for a, b in zip(raw, fixed))

    # q_prev 를 주면 첫 값도 거기에 맞춘다 (이어서 재생)
    first = enforce_sign_continuity(raw, q_prev=tuple(-v for v in raw[0]))[0]
    assert _jump(first, tuple(-v for v in raw[0])) < 1e-12

    # 입력 전체를 뒤집어도 이웃 관계는 그대로다 — 전체 부호 하나는 자유롭게 남는다
    flipped = enforce_sign_continuity([tuple(-v for v in q) for q in raw])
    assert max(_jump(a, b) for a, b in zip(flipped, flipped[1:])) < 0.01


def test_t9_error_uses_shortest_path():
    """오차 함수가 −q 를 스스로 처리하는가 — 7절 결정 3."""
    current = euler_xyz_deg_to_quat(0.0, 0.0, 178.0)
    target = euler_xyz_deg_to_quat(0.0, 0.0, -178.0)  # 실제로는 4° 차이

    err = quat_error_axis_angle(current, target)
    assert abs(math.degrees(math.sqrt(sum(v * v for v in err))) - 4.0) < 1e-6

    # 목표를 −q 로 줘도 같은 델타가 나온다
    flipped = quat_error_axis_angle(current, tuple(-v for v in target))
    assert max(abs(a - b) for a, b in zip(err, flipped)) < 1e-12

    # 델타를 실제로 적용하면 목표에 닿는가 — robosuite 와 같은 왼쪽 곱
    reached = quat_mul(axis_angle_to_quat(err), current)
    assert angle_between_deg(reached, target) < 1e-9


def test_t11_invariants():
    rng = random.Random(2)
    for _ in range(200):
        q = euler_xyz_deg_to_quat(rng.uniform(-180, 180), rng.uniform(-90, 90), rng.uniform(-180, 180))
        assert abs(math.sqrt(sum(v * v for v in q)) - 1.0) < 1e-12

        m = quat_to_matrix(q)
        for i in range(3):  # 행들이 단위벡터이고 서로 직교하는가
            assert abs(sum(v * v for v in m[i]) - 1.0) < 1e-12
            for j in range(i + 1, 3):
                assert abs(sum(m[i][k] * m[j][k] for k in range(3))) < 1e-12
        det = (
            m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
        )
        assert abs(det - 1.0) < 1e-12  # −1 이면 거울상이다


def test_t12_scipy_oracle():
    """독립 구현과 대조. scipy 는 서버 `.venv` 에만 있다 — 없으면 건너뛴다."""
    try:
        from scipy.spatial.transform import Rotation
    except ImportError:
        print("    (scipy 없음, T12 skip)")  # em-dash 는 cp949 콘솔에서 죽는다
        return

    rng = random.Random(3)
    for _ in range(500):
        e = (rng.uniform(-180, 180), rng.uniform(-90, 90), rng.uniform(-180, 180))
        ref = Rotation.from_euler("xyz", e, degrees=True)  # 소문자 = extrinsic
        ours = euler_xyz_deg_to_quat(*e)
        assert angle_between_deg(ours, quat_xyzw_to_wxyz(tuple(ref.as_quat()))) < 1e-9

        back = quat_to_euler_xyz_deg(ours)
        assert max(abs(a - b) for a, b in zip(back, ref.as_euler("xyz", degrees=True))) < 1e-9

        aa = quat_to_axis_angle(ours)
        assert max(abs(a - b) for a, b in zip(aa, ref.as_rotvec())) < 1e-9


def test_t13_frame_rotation():
    """q_libero = q_mirobot ⊗ F, F = x축 180° (9/17 확정). LIBERO_AXES.md 4절."""
    # 홈 — Mirobot 항등 = LIBERO top-down
    assert angle_between_deg(mirobot_to_libero_quat(IDENTITY), quat_from_axis_deg("x", 180.0)) < 1e-9

    rng = random.Random(4)
    for _ in range(200):
        q = euler_xyz_deg_to_quat(rng.uniform(-180, 180), rng.uniform(-90, 90), rng.uniform(-180, 180))
        assert angle_between_deg(libero_to_mirobot_quat(mirobot_to_libero_quat(q)), q) < 1e-9

    # 9/17 LIBERO 안정 후 자세 — 그리퍼가 베이스 쪽(−x)으로 3.3° 기움. Mirobot 에서 뒤로 기울기는 Ry+
    settled = quat_xyzw_to_wxyz((0.9996, 0.0002, -0.0286, 0.0001))
    rx, ry, rz = quat_to_euler_xyz_deg(libero_to_mirobot_quat(settled))
    assert abs(rx) < 0.1 and abs(ry - 3.28) < 0.05 and abs(rz) < 0.1, (rx, ry, rz)

    # 월드 축 회전이 부호 그대로 옮겨지는가 — pre(F ⊗ q) 였다면 Ry·Rz 부호가 뒤집힌다
    for axis, idx in (("x", 0), ("y", 1), ("z", 2)):
        q_libero = quat_mul(quat_from_axis_deg(axis, 10.0), FRAME_F)       # top-down 에서 월드 축 +10°
        euler = quat_to_euler_xyz_deg(libero_to_mirobot_quat(q_libero))
        assert abs(euler[idx] - 10.0) < 1e-9, (axis, euler)

    # Mirobot Ry +10 (플랜지 뒤로, 9/13) → LIBERO 에서 그리퍼가 −x 를 향해야 한다
    m = quat_to_matrix(mirobot_to_libero_quat(euler_xyz_deg_to_quat(0.0, 10.0, 0.0)))
    assert m[0][2] < -0.17 and m[2][2] < -0.98, [m[i][2] for i in range(3)]


if __name__ == "__main__":
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            ran += 1
    print(f"\n{ran}개 통과")
