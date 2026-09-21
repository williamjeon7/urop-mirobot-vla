# 값이 어떻게 바뀌나 — Mirobot ↔ LIBERO 변환 파이프라인

> **참조** · 확인 2026-09-20 · 9/17 LIBERO 측정, 9/17·9/20 Mirobot 실물
> 한 자세가 두 로봇 사이를 오갈 때 거치는 단계. 회전 규약은 [ROTATION.md](ROTATION.md),
> 축·측정값은 [LIBERO_AXES.md](LIBERO_AXES.md), 제어 방식 차이는 [CONTROL.md](CONTROL.md), 작업은 [CHECKLIST.md](CHECKLIST.md).

## 1. 무엇을 바꾸고 무엇을 안 바꾸나

| | 바꾼다 | 어떻게 |
|---|---|---|
| **자세** | ✓ | 표현(오일러 ↔ 쿼터니언), 저장 순서(`wxyz`/`xyzw`), 기준 프레임 `F` |
| **위치** | ✓ | 단위(m ↔ mm), 원점(기준점 짝), 기준점(플랜지 ↔ 파지점), 스케일 |
| **축 방향** | ✗ | 두 월드 축이 같다 — `X↔x`(앞) `Y↔y`(왼쪽) `Z↔z`(위), 부호도 같다 |
| **시간·속도** | ✗ | 이번 주는 정지점 순서만 본다 |

## 2. LIBERO → Mirobot (5-2)

`seg1-end` waypoint 하나를 끝까지 따라간 예다 (9/17 복합 동작).

```
① 기록                 flange_pos (-0.1464, +0.0137, +1.2651) m        LIBERO 월드, 플랜지
                       flange_quat_xyzw (0.9874, -0.0004, -0.1583, -0.0002)
                                  ▼
② 저장 순서            wxyz (-0.0002, 0.9874, -0.0004, -0.1583)        quat_xyzw_to_wxyz
                                  ▼
③ 프레임 회전 F⁻¹      (0.9874, 0.0002, 0.1583, -0.0004)               libero_to_mirobot_quat  = q ⊗ F⁻¹
                                  ▼
④ 오일러 (extrinsic XYZ, 도)   A 0.01  B 18.22  C -0.04                quat_to_euler_xyz_deg
                       (relative 모드면 시작 자세를 먼저 빼서 B 14.94)

① 위치 변위            (-0.1464) - (-0.2062) = +0.0598 m  →  +59.81 mm  시작 플랜지 기준
                                  ▼
② Mirobot 홈에 더하기  198.67 + 59.81 = 258.48 mm                      libero_to_mirobot_xyz_mm
                                  ▼
③ G-code               G0 X258.48 Y0.43 Z222.31 A0.01 B14.94 C-0.06
```

- **기준점 짝** — "Panda 시작 플랜지 ↔ Mirobot 홈 `(198.67, 0, 230.72)`". 절대 좌표가 아니라 **변위**를 옮긴다
- **왜 플랜지인가** — Mirobot 은 플랜지를 보고하고 Panda proprio 는 파지점이다 ([CONTROL.md](CONTROL.md) 2절)
- **`F` = x축 180°, 오른쪽 곱** — Mirobot 은 top-down 을 `(0,0,0)`, LIBERO 는 x축 180° 로 적는다 ([LIBERO_AXES.md](LIBERO_AXES.md) 4절)
- **absolute / relative** — 기록된 자세를 그대로 옮길지(absolute), 시작 자세를 `(0,0,0)` 으로 두고 움직임만 옮길지(relative).
  relative 는 Panda 시작의 3.3° 기울기를 지운다

## 3. Mirobot → LIBERO (5-1)

역순이다. 다만 LIBERO 는 "가라" 가 아니라 변화량을 받으므로 **추종 루프**가 붙는다.

```
Mirobot G0 / ? 보고값   X Y Z (mm), A B C (도)
        ▼
오일러 → 쿼터니언        euler_xyz_deg_to_quat            extrinsic XYZ = qz ⊗ qy ⊗ qx
        ▼
프레임 회전 F           mirobot_to_libero_quat  = q ⊗ F
        ▼
위치                    mirobot_to_libero_xyz_m          홈 기준 변위 → m → Panda 시작 플랜지에 더함
        ▼
플랜지 → 파지점          flange_to_grip                   컨트롤러가 움직이는 점이 파지점이라 97mm 내려 목표를 잡는다
        ▼
추종 루프                servo_action = (목표 − 현재) / (0.05m, 0.5rad), 방향 유지하며 크기만 ≤ 1
        ▼
도착 판정                위치 2mm·자세 1° 안 + 한 스텝 이동 0.3mm·0.05° 이하
```

## 4. 코드 지도

| 파일 | 맡는 것 |
|---|---|
| `common/rotation.py` | 표현·저장 순서·프레임 회전 — 함수는 아래 표 |
| `common/workspace.py` | 위치. `libero_to_mirobot_xyz_mm`, `mirobot_to_libero_xyz_m`, `flange_to_grip`, `grip_to_flange`, `MIROBOT_HOME_MM` |
| `common/servo.py` | 목표 → 액션. `servo_action`, `pose_gap`, `reached`, `fit_to_unit` |
| `tools/libero_compound_rollout.py` | Panda 복합 동작을 만들고 기록 (LIBERO → Mirobot 의 입력) |
| `tools/libero_to_mirobot_gcode.py` | waypoint → G-code, 되돌려 검산 |
| `tools/run_gcode.py` | G-code 를 Mirobot 에 한 줄씩, 정지 확인, `?` 기록 |
| `tools/roundtrip_check.py` | 실물 보고값을 뽑고 LIBERO 로 되돌려 원본과 비교 |
| `tools/libero_follow.py` | 목표 목록을 Panda 가 따라감 (5-1) |

### `common/rotation.py` 의 함수

**표준 라이브러리만 쓴다** ([CHECKLIST.md](CHECKLIST.md) 3절 ②). 비고의 절 번호는 [ROTATION.md](ROTATION.md) 의 절이다 — 규약과 근거는 거기 있다.

| 함수 | 입력 → 출력 | 비고 |
|---|---|---|
| `euler_xyz_deg_to_quat(rx, ry, rz)` | Mirobot 오일러(도) → `wxyz` | `qz ⊗ qy ⊗ qx` (4절) |
| `quat_to_euler_xyz_deg(q)` | `wxyz` → 오일러(도) | 짐벌락이면 `rx = 0` 으로 몰아준다 (4절) |
| `quat_wxyz_to_xyzw(q)` / `quat_xyzw_to_wxyz(q)` | 저장 순서 변환 | LIBERO 출입구 (5절) |
| `axis_angle_to_quat(vec)` / `quat_to_axis_angle(q)` | axis-angle(rad) ↔ `wxyz` | 짧은 쪽 관례 (8절). robosuite 는 최대 360° |
| `enforce_sign_continuity(quats, q_prev=None)` | 궤적 → 부호 맞춘 궤적 | 직전과 내적 < 0 이면 뒤집기 (7절) |
| `quat_error_axis_angle(q_current, q_target)` | 두 자세 → axis-angle(rad) | **OSC_POSE 액션의 회전 3칸.** 부호를 함수 안에서 맞춘다 (7절) |
| `mirobot_to_libero_quat(q)` / `libero_to_mirobot_quat(q)` | 프레임 회전 | `q ⊗ F` / `q ⊗ F⁻¹`, `FRAME_F` = x축 180° (6절, 9/17 확정) |
| `quat_mul(a, b)` · `quat_conj(q)` · `quat_normalize(q)` · `quat_from_axis_deg(axis, deg)` · `quat_to_matrix(q)` | 보조 | `quat_mul(a, b)` = "b 먼저, a 나중" |

### 두 방향에서 쓰는 순서

```python
# 5-1  Mirobot → LIBERO
q = euler_xyz_deg_to_quat(rx, ry, rz)          # 도 → wxyz
q = mirobot_to_libero_quat(q)                   # q ⊗ F
proprio_quat = quat_wxyz_to_xyzw(q)             # LIBERO 로
traj = enforce_sign_continuity(traj)            # 궤적 전체에 한 번
action[3:6] = quat_error_axis_angle(q_cur, q_target)   # 추종 루프

# 5-2  LIBERO → Mirobot
q = axis_angle_to_quat(ee_ori)                  # 데이터셋 ee_ori
q = libero_to_mirobot_quat(q)                   # q ⊗ F⁻¹
rx, ry, rz = quat_to_euler_xyz_deg(q)           # G0 A B C
```

### 테스트

`tests/test_rotation.py`(13), `tests/test_workspace.py`(4), `tests/test_servo.py`(6). 저장소 최상위에서 `-m` 으로 돌린다.

```bash
cd ~/UROP && python -m tests.test_rotation
```

설계(T1~T13)와 각 항목이 무엇을 잡는지는 그 파일 주석에 있다 — 문서와 이중으로 두지 않는다.
통과 기록은 [CHECKLIST.md](CHECKLIST.md) 3절 ②. scipy 대조(T12)는 scipy 가 있는 환경(서버 `.venv`)에서만 돈다.

## 5. 어디까지 맞는지 확인됐나

파이프라인 전체를 한눈에 보는 표다. **숫자의 주인은 그 측정을 한 문서**이고, 여기는 한 줄 요약과 링크만 둔다.

| 구간 | 확인 | 결과 |
|---|---|---|
| 변환 → 역변환 (계산만) | G-code 도구의 검산 | 위치 **0.007mm** · 자세 **0.006°** (파일 반올림 몫) |
| LIBERO → Mirobot 좌표 → LIBERO (시뮬) | `libero_follow --gcode` 로 되따라감 | **2.34mm · 0.34°** → [CHECKLIST.md](CHECKLIST.md) 5-1 |
| **실물 한 바퀴** — 변환 → Mirobot 실행 → 보고값 → 역변환 | `roundtrip_check compare` (9/20) | **0.30mm · 0.05°** → [CHECKLIST.md](CHECKLIST.md) 5-1 (가) |
| 프레임 회전 `F` | Mirobot 실물 `A15`·`B15`·`C20` 방향 (9/17) | LIBERO `Δrx+`·`Δry+`·`Δrz+` 와 같은 쪽 → [LIBERO_AXES.md](LIBERO_AXES.md) 4절 |

**왕복은 `F` 를 잡지 못한다.** `F` 는 축별 시험으로만 잡힌다 — 왜인지는 [CHECKLIST.md](CHECKLIST.md) 5-1 (가)·(나).

## 6. 아직 남은 어긋남

목록만 둔다. 설명과 숫자는 링크 쪽이 주인이다.

| | 내용 | 어디에 |
|---|---|---|
| **회전 중심** | Panda 는 파지점, Mirobot(Cartesian `G0`)은 플랜지를 중심으로 돈다. 손끝이 `ΔL` 만큼 어긋난다 | [CONTROL.md](CONTROL.md) **2-1절** · 실물 숫자는 [CHECKLIST.md](CHECKLIST.md) 5-2 |
| **Mirobot 플랜지 → 파지점 길이** | 미측정. 손끝끼리 맞추려면 필요하다 | [CHECKLIST.md](CHECKLIST.md) 8절 |
| **보고 Z 상수 오프셋** | 명령보다 낮게 보고한다. 실제로 낮은지 보고만 낮은지는 외부 측정을 안 해 모른다 | 숫자는 [CHECKLIST.md](CHECKLIST.md) 5-1·5-2 |
| **절대/상대 혼동** | `measured` 파일은 relative, `libero_follow --gcode` 는 absolute 로 읽는다 | [CHECKLIST.md](CHECKLIST.md) 5-1 (가) |
