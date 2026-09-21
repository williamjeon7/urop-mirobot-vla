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

## 3-1. 시작 자세를 어떻게 다룰까 — relative 와 absolute

**문제** — LIBERO Panda 의 시작 자세는 정확한 top-down 이 아니고, task·초기 상태마다 **1.5°~6.8°** 씩 다르다
([LIBERO_AXES.md](LIBERO_AXES.md) 1절 "왜 기울어져 있나"). Mirobot 은 홈에서 `RxRyRz = (0,0,0)` 으로 딱 떨어진다.
둘을 어떻게 짝지을지 정해야 한다.

**두 버전을 다 만들어 봤다.** `--orientation` 으로 고른다 (쓰는 쪽·읽는 쪽 둘 다 같은 값이어야 한다).

| | 내보낼 때 (`libero_to_mirobot_gcode.py:61-63`) | 읽어올 때 (`libero_follow.py:74`) | Mirobot `(0,0,0)` 이 뜻하는 것 |
|---|---|---|---|
| **absolute** | `q_mirobot = q_libero ⊗ F⁻¹` | `q_libero = q_mirobot ⊗ F` | **정확한 top-down** |
| **relative** | `q_mirobot = q_libero ⊗ q_시작⁻¹` | `q_libero = q_mirobot ⊗ q_시작` | **그 판의 Panda 시작 자세** (기운 채로) |

**이름이 거꾸로 읽힌다 — 맞춰 주는 쪽은 `absolute` 다.** "relative = 기준을 맞춘다" 로 읽히기 쉬운데 반대다.
relative 는 시작 기울기를 파일에서 **지우는** 것이라 Mirobot 이 홈에 그대로 있으면 되고, 맞추는 동작이 없다.
absolute 는 Mirobot 이 실제로 그만큼 기울여 Panda 시작 자세를 따라간다. 두 파일의 첫 줄이 그 차이다.

```
relative   G0 X198.67 Y0.00 Z230.72 A0.00  B-0.00 C0.00     홈 그대로
absolute   G0 X198.67 Y0.00 Z230.72 A-0.01 B 3.28 C0.02     3.28° 기울여 맞춤
           (둘째 줄도 B 4.01 vs B 7.29 — 궤적 전체가 3.28° 씩 옮겨가 있다)
```

| 이름 | 무엇에 상대적/절대적인가 |
|---|---|
| **relative** | **Panda 시작 자세**에 상대적 → 시작이 정의상 0, Mirobot 은 홈에 그대로 |
| **absolute** | **월드 top-down**(`F` 규약)에 절대적 → Panda 가 기울어 있으면 Mirobot 도 기울인다 |

### 결과

- **왕복 오차는 둘 다 0 이다.** 같은 값으로 나눴다 곱하므로 대수적으로 정확히 상쇄된다.
  실측 왕복 자세 오차 **0.05°** 가 그 증거다 (9/20~21, [CHECKLIST.md](CHECKLIST.md) 5-1 (가)).
  시작 기울기를 "미미해서 무시" 한 것이 아니라 **빼 뒀다 도로 얹는 것**이다
- **relative 는 대신 절대 대응이 옮겨간다.** Mirobot 홈을 "기운 Panda 시작 자세" 와 짝지으므로,
  실물 Mirobot 의 절대 자세가 Panda 와 내내 **3.28° 다르다** (그날 판의 기울기만큼).
  손끝으로 치면 `97 × sin3.28° = 5.6mm`. 눈으로는 안 보이지만 0 은 아니다
- **relative 파일은 그 판에 묶인다.** "그날 그 시작 자세로부터의 회전" 이라, task 나 초기 상태를 바꾸면 뜻이 달라진다.
  absolute 는 Mirobot 절대 자세라 어디서 읽든 같다
- **쓰는 쪽과 읽는 쪽이 어긋나면** 궤적 전체가 시작 기울기만큼 **일정하게** 치우친다 (모양은 맞고 통째로 기운다).
  커지는 오차가 아니다

| 파일 | 방식 | 실물 |
|---|---|---|
| `2026_09_17-compound-relative.gcode` | relative | **9/20 실행** — 7/7 도착, J5 최대 21.34° |
| `2026_09_17-compound-absolute.gcode` | absolute | 미실행. 시작이 `B 3.28`, J5 약 24.6° 로 추정 |
| `2026_09_21-mirobot-origin.gcode` | absolute | 미실행 (5-1 (나)) |

### 정한 것 (9/21) — **absolute 를 기본으로 한다**

9/17 에 relative 를 고른 이유는 Mirobot 이 홈에서 출발해 첫 줄이 깔끔하다는 것과, absolute 면 모든 waypoint 의 `B` 에
3.28° 가 얹혀 J5 가 올라간다는 것이었다. 그때는 J5 여유를 몰랐다. 9/20 에 21.34° 까지 문제없는 것을 봤으니
이제 **대응 관계가 판에 묶이지 않는 absolute 가 낫다**. 9/17 relative 파일은 이미 실물에서 돈 기록이 있어 그대로 둔다.

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
| **실물 왕복** (숫자가 도는 것이다 — 로봇이 도는 것이 아니다) — 변환 → Mirobot 실행 → 보고값 → 역변환 | `roundtrip_check compare` (9/20) | **0.30mm · 0.05°** → [CHECKLIST.md](CHECKLIST.md) 5-1 (가) |
| 프레임 회전 `F` | Mirobot 실물 `A15`·`B15`·`C20` 방향 (9/17) | LIBERO `Δrx+`·`Δry+`·`Δrz+` 와 같은 쪽 → [LIBERO_AXES.md](LIBERO_AXES.md) 4절 |

**왕복은 `F` 를 잡지 못한다.** `F` 는 축별 시험으로만 잡힌다 — 왜인지는 [CHECKLIST.md](CHECKLIST.md) 5-1 (가)·(나).

## 6. 아직 남은 어긋남

목록만 둔다. 설명과 숫자는 링크 쪽이 주인이다.

| | 내용 | 어디에 |
|---|---|---|
| **회전 중심** | Panda 는 파지점, Mirobot(Cartesian `G0`)은 플랜지를 중심으로 돈다. 손끝이 `ΔL` 만큼 어긋난다 | [CONTROL.md](CONTROL.md) **2-1절** · 실물 숫자는 [CHECKLIST.md](CHECKLIST.md) 5-2 |
| **Mirobot 플랜지 → 파지점 길이** | **55mm 로 쟀다 (9/21, 자, ±5mm).** `ΔL = 42mm` — 이제 손끝끼리 맞출 수 **있다**. 어느 쪽으로 맞출지가 남았다 | [CONTROL.md](CONTROL.md) 2-1절 · [CHECKLIST.md](CHECKLIST.md) 8절·10절 |
| **보고 Z 상수 오프셋** | 명령보다 낮게 보고한다. 실제로 낮은지 보고만 낮은지는 외부 측정을 안 해 모른다 | 숫자는 [CHECKLIST.md](CHECKLIST.md) 5-1·5-2 |
| **절대/상대 혼동** | `measured` 파일은 relative, `libero_follow --gcode` 는 absolute 로 읽는다 | [CHECKLIST.md](CHECKLIST.md) 5-1 (가) |
