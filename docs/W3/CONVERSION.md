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
| `common/rotation.py` | 표현·순서·프레임 회전. `euler_xyz_deg_to_quat`, `quat_to_euler_xyz_deg`, `quat_wxyz_to_xyzw`, `mirobot_to_libero_quat`, `libero_to_mirobot_quat`, `quat_error_axis_angle`, `enforce_sign_continuity` |
| `common/workspace.py` | 위치. `libero_to_mirobot_xyz_mm`, `mirobot_to_libero_xyz_m`, `flange_to_grip`, `grip_to_flange`, `MIROBOT_HOME_MM` |
| `common/servo.py` | 목표 → 액션. `servo_action`, `pose_gap`, `reached`, `fit_to_unit` |
| `tools/libero_compound_rollout.py` | Panda 복합 동작을 만들고 기록 (LIBERO → Mirobot 의 입력) |
| `tools/libero_to_mirobot_gcode.py` | waypoint → G-code, 되돌려 검산 |
| `tools/run_gcode.py` | G-code 를 Mirobot 에 한 줄씩, 정지 확인, `?` 기록 |
| `tools/roundtrip_check.py` | 실물 보고값을 뽑고 LIBERO 로 되돌려 원본과 비교 |
| `tools/libero_follow.py` | 목표 목록을 Panda 가 따라감 (5-1) |

테스트는 `tests/test_rotation.py`(13), `tests/test_workspace.py`(4), `tests/test_servo.py`(6).

## 5. 어디까지 맞는지 확인됐나

| 구간 | 확인 | 결과 |
|---|---|---|
| 변환 → 역변환 (계산만) | G-code 도구의 검산 | 위치 **0.007mm**, 자세 **0.006°** (파일 반올림 몫) |
| LIBERO → Mirobot 좌표 → LIBERO (시뮬) | `libero_follow --gcode` 로 되따라감 | **2.34mm · 0.34°** (추종 루프 수렴 오차 포함) |
| **실물 한 바퀴** — 변환 → Mirobot 실행 → 보고값 → 역변환 | `roundtrip_check compare` (9/20) | **0.30mm · 0.05°** — 거의 전부가 Mirobot 보고 Z 의 상수 오프셋(−0.27mm) |
| 프레임 회전 `F` | Mirobot 실물 `A15`·`B15`·`C20` 방향 (9/17) | LIBERO `Δrx+`·`Δry+`·`Δrz+` 와 같은 쪽 |

**왕복은 `F` 를 잡지 못한다** — 나갈 때 곱하고 들어올 때 나눠 상쇄된다. `F` 는 축별 시험으로만 잡힌다
([CHECKLIST.md](CHECKLIST.md) 5-1 (가)·(나), `tests/test_rotation.py` 의 T5 함정과 같은 구조).

## 6. 아직 남은 어긋남

| | 내용 |
|---|---|
| **회전 중심** | Panda 는 파지점, Mirobot(Cartesian `G0`)은 플랜지를 중심으로 돈다. 9/20 실물에서 기울기 16.59° 때 팔이 27.0mm 되돌아왔고 `97 × sin16.59° = 27.7mm` 와 맞는다. 플랜지끼리 맞춘 결과라 **손끝 궤적은 두 로봇이 다르다** |
| **Mirobot 플랜지 → 파지점 길이** | 미측정 (손목 카메라 마운트 뒤). 손끝끼리 맞추려면 필요하다 |
| **보고 Z 상수 오프셋** | Mirobot 이 명령보다 0.25~0.29mm 낮게 보고한다. 실제로 낮은지 보고만 낮은지는 외부 측정을 안 해 모른다 |
| **절대/상대 혼동** | `measured` 파일은 relative 로 만든 궤적의 보고값이다. `libero_follow --gcode` 는 absolute 로 읽어 3.3° 어긋난다 |
