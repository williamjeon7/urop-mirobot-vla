# W6 — 작업 목록

> **절차** · 확인 2026-10-07 · 기준 10/5 action plan, `dd9c28c`
> Mirobot을 촬영할 카메라가 아직 도착하지 않았다. 그래서 이번 주는 **Panda(시뮬레이션) 정보만으로 할 수 있는 일**로 범위를 정했다.
> `→` 뒤 빈칸은 **미리 채우지 않는다**.

계획 원문: [../meetings/2026-10-05.md](../meetings/2026-10-05.md).
W5에서 넘어온 것: [../W5/CHECKLIST.md](../W5/CHECKLIST.md) 4-3절(색 블록 장면), 9절(다음 action plan).
pick up 구현의 결정과 결과: [rgb_blocks/PICKUP.md](rgb_blocks/PICKUP.md).
**분업(10/8)과 넘겨주는 파일 형식: [DIVISION.md](DIVISION.md)** — Panda 쪽 / Mirobot 쪽 할 일은 거기서 관리한다.

## 0. 이번 주 목표

**시뮬레이션에서 잘 되는 pick up을 Mirobot 명령으로 바꿔 보냈을 때도 같은 동작이 나오는지 확인한다.**
10/5 파이프라인의 마지막 칸인 "실제 로봇 명령"까지 Panda 정보만으로 잇는다.
시뮬레이션 Panda가 pick up을 수행하고, 그 결과를 좌표·자세 → Mirobot 좌표 → G-code(`--dry-run`) → 실물 순서로 넘긴다.

**10/8 팀 결정 — 이번 주 우선순위: 지금의 pick up을 Mirobot으로 옮겨 실제 경향성을 확인한다.**
pick up이 단조롭다는 점(그리퍼 방향 고정, 블록 회전 0°, 가까운 블록 미대응)은 알고 있지만, 다양화는 그다음으로 미룬다.
"경향성"은 Mirobot이 지시한 색 블록 쪽으로 가서, 내려가고, 집고, 드는 흐름이 시뮬과 같은지를 눈으로 보는 것이다(정밀 측정보다 흐름 우선).

**실물 확인은 세 단계로 나눈다 (10/7 정함).** 카메라가 없으므로 W5 9-③처럼 종이 표시와 자로 확인한다.

| 단계 | 확인 | 필요한 것 |
| --- | --- | --- |
| 1 | 손끝이 블록 자리 위로 정확히 가는가 (mm) | 좌표 변환, 배율 0.663 |
| 2 | 작업대에 부딪히지 않고 잡을 높이까지 내려가는가 | Z 하한 66~71 mm |
| 3 | 실제로 집어 드는가 | **그리퍼 명령**(번역기에 없음), 실물 블록 크기 |

1·2단계는 W5 4-3에서 정한 "손 뻗기"와 같은 범위다. 손 뻗기로 좌표 변환을 먼저 확인하고, 그다음 그리퍼를 더해 pick up으로 넘어간다.

**지금은 로봇을 조작할 수 없다 (10/7).** 실물 블록도 아직 없다. 그래서 로봇 없이 할 수 있는 일을 먼저 한다.
서버에서는 dry-run과 역변환 검산으로 변환을 확인한다(4절). dry-run은 필요조건이다.
Z 하한 아래 줄이 있으면 실물 실행도 파일 전체를 보내지 않는다. 다만 soft limit 거부와 실제 손끝 오차는 실물에서만 보인다.

### 지금 상태 (10/7)

| 파이프라인 단계 | 상태 | 어디 |
| --- | --- | --- |
| MuJoCo Object XML | 완료 (동료) | [rgb_blocks/objects.py](rgb_blocks/objects.py), `assets/` |
| BDDL | 완료 (동료). 색상 task Goal을 `Up`으로 바꿨다 (10/6). **블록 자리를 Mirobot 범위로 옮겼다 (10/7)** | `rgb_blocks/tasks/*.bddl` |
| LIBERO Tabletop · Simulator 작동 | 완료 (동료) | `preview.py`, `browser_viewer.py` |
| **LIBERO / Panda Action 수행** | **완료 (10/6)** — red/green/blue × seed 0–4, 15/15 성공. 새 자리에서도 15/15 (10/7) | [rgb_blocks/pickup.py](rgb_blocks/pickup.py), PICKUP.md |
| 좌표·자세 획득 | **완료 (10/7)** — `pickup.py --log`가 매 step action·EEF·관절값을 JSONL로 남긴다 | 3절 |
| Mirobot 좌표계로 변환 | **손 뻗기 완료 (10/7)** — 번역기가 우리 장면에서 돌고, G-code 3개가 `--dry-run`을 경고 없이 통과했다. pick up은 Z 하한에 걸린다 | 4절 |
| 실제 로봇 명령 | 도구는 있다(`tools/run_gcode.py`). 카메라 없이도 할 수 있다 | 5절 |

**범위 밖 (카메라 도착 후)** — 6절
- 영상만으로 하는 pick up과 VLA 학습 데이터 수집
- D405 색·화각 보정을 이 장면에 적용 ([../W5/D405_LIBERO_CAMERA.md](../W5/D405_LIBERO_CAMERA.md), 동료)

## 1. 순서

```
2. 먼저 맞출 것 — W5 결정과 10/5 action plan이 다른 점
        ▼
3. 좌표·자세 획득 ── pickup.py가 기록을 남기게 한다
        ▼
4. Mirobot 변환 ──── 번역기를 우리 장면에 연결 → G-code → run_gcode --dry-run
        ▼
5. 실물 ─────────── 로봇 노트북에서 종이 표시와 자로 확인 (카메라 불필요)
```

## 2. 먼저 맞출 것 — W5 결정과 10/5 action plan이 다른 점

W5 CHECKLIST 4-3절은 10/5 커밋 `209ed24`로, 10/5 action plan보다 먼저 또는 같은 날 정해졌다.
두 문서가 서로 다르게 말하는 곳이 있다. 3–5절을 진행하기 전에 정한다.

| | W5 CHECKLIST (10/5) | 10/5 action plan · W6 구현 |
| --- | --- | --- |
| 과제 | **손 뻗기만** — "빨간 블록으로 움직여". 그리퍼 문제(proprio 2칸 vs 1칸, `L`)를 피하려고 정함 | **Pick up** — 집어 들기. 구현 완료 |
| 성공 판정 | 손끝–대상 수평 거리 ≤ 몇 cm인 새 predicate (4-3 G) | `Up`(z ≥ 1.0 m) + `_check_grasp` + 다른 블록 `On` 유지 |
| 블록 배치 | Mirobot이 닿는 곳에서 거꾸로 계산 → 탁상 **x −0.282~−0.116, y ±0.151 m** (4-3 D, [TABLE_ALIGNMENT.md](../W5/TABLE_ALIGNMENT.md) 5절) | 현재 region x −0.25~0.05. red y −0.37~−0.17, green y −0.10~0.10, blue y 0.17~0.37 → **red·blue는 범위 밖, green은 x 일부만 겹친다** |
| 블록 크기 | 실물 크기 ÷ s (s = 0.663) | 40 mm. 실물 블록 크기는 아직 미정 |
| LIBERO 환경 용도 | **(a) 실물 배치 기준**. 카메라 색·화각 보정은 지금 하지 않는다. (b) 시뮬 데이터 · (c) 시뮬 평가 의도가 있었는지 교수님께 여쭐 예정 (W5 8절) | 시뮬+실제 데이터를 섞어 학습한다는 이해 (10/7 대화). 근거는 동료의 D405 보정 작업 |

- [ ] **과제** — pick up인가, 손 뻗기인가. 10/5 action plan이 W5 4-3을 대체한 것인지 확인한다
  → **둘 다 단계로 간다 (10/7).** 실물은 손 뻗기(0장 1·2단계)로 좌표 변환을 먼저 확인하고, 그리퍼를 더해 pick up(3단계)으로 간다.
  시뮬 pick up은 그대로 둔다. 10/5 action plan이 W5 4-3을 대체했는지는 미팅에서 확인한다 (8절)
- [ ] **LIBERO 환경 용도** — (a)/(b)/(c) 중 무엇인가. W5 8절 질문의 답을 받았는지 확인한다
  →
- [ ] **블록 region을 Mirobot 범위(4-3 D)로 옮길지** — 옮기면 BDDL 4개를 고치고 pick up을 다시 검증한다.
  W5 9절이 제안한 블록 자리는 Mirobot X200 Y0, X240 Y±60이다. 시뮬 좌표로는 약 (−0.206, 0), (−0.146, ±0.090) m다.
  이 시뮬 좌표는 TABLE_ALIGNMENT 5절 표에서 선형으로 계산한 값이며, 아직 검산하지 않았다
  → **옮겼다 (10/7).** `common/workspace.py`의 `mirobot_to_libero_xyz_m`로 다시 계산했고, 선형 근사와 같았다.
  짝은 Panda 시작 파지점 (−0.2085, 0) ↔ Mirobot 홈 파지점이고, s = 0.663이다.

  | 색 | Mirobot 파지점 (mm) | 시뮬 중심 (m) | BDDL `:ranges` |
  | --- | --- | --- | --- |
  | red | X240 Y−60 | (−0.1462, −0.0905) | (−0.1762 −0.1205 −0.1162 −0.0605) |
  | green | X200 Y0 | (−0.2065, 0.0000) | (−0.2365 −0.0300 −0.1765 0.0300) |
  | blue | X240 Y+60 | (−0.1462, +0.0905) | (−0.1762 0.0605 −0.1162 0.1205) |

  - LIBERO는 영역에서 블록 반경(40 mm 블록이면 28.3 mm)을 뺀 범위에 블록을 놓는다.
    그래서 반폭을 30 mm로 잡으면 seed마다 축별로 ±1.7 mm 안에 놓여 사실상 고정이다(Mirobot 기준 약 ±1.1 mm).
    seed 0–2에서 놓인 위치가 1 mm 단위 출력으로 목표와 1–2 mm 안에 있음을 확인했다
  - 같은 영역을 BDDL 4개(`tabletop.bddl`, `tasks/*.bddl`)에 똑같이 적었다
  - 블록 사이 간격이 0.109 m로 좁아져서 블록 크기 상한을 120 mm에서 **60 mm**로 내렸다 (`preview.py`)
  - 재검증: `test_rgb_blocks` scene/red/green/blue 통과, `pickup.py` 15/15 (모두 146 step, 들어 올린 높이 0.146–0.147 m), 뷰어 테스트 47 OK
  - 대가: 위치 다양성이 없어진다. 시뮬 데이터 수집(6절)에서 다양한 위치가 필요해지면 그때 영역을 넓힌다
  - **무작위 배치로 넓혔다 (10/7, 사용자 결정 A)** — 세 점 주변 **Mirobot ±10 mm**(시뮬 ±15.1 mm), 영역 반폭 0.0434 m.
    ±20 mm는 red와 green이 겹칠 수 있어서 안 된다. 실물 블록 26.5 mm 기준으로 √2 × 26.5 = 37.5 mm 간격이 필요한데, ±20 mm면 20 mm까지, ±15 mm면 31.6 mm까지 가까워진다.
    ±10 mm면 최소 44.7 mm다. **실물 블록이 26.5 mm보다 크면 다시 계산한다.**
    pick up 세 색 × seed 0–19, **60/60 성공** (146–147 step). 블록은 중심에서 최대 15.0 mm까지 놓였다.
    모서리의 수평 거리는 최대 259.6 mm다. 모서리 도달은 실물에서 확인해야 한다(5절)
  - **세 블록이 Mirobot 작업 영역 전체를 공유하도록 넓혔다 (10/7, 사용자 결정 1)** — 위 ±10 mm 배치를 대신한다.
    블록이 너무 가깝게 모여 있다는 의견에 따라 바꿨다. W5 4-3 D의 Mirobot 파지점 X 150~260, Y ±100 mm를 시뮬로 옮기면
    블록 중심 x −0.2819~−0.1160, y ±0.1508 m다. BDDL에는 영역 `work_region` 하나를 두고, 블록 반경 0.0283 m만큼 넓힌
    `(-0.3102 -0.1791 -0.0877 0.1791)`을 쓴다. 세 블록 모두 `(On … main_table_work_region)`이다.
    **색 순서도 seed마다 무작위다.** 나중에 VLA 데이터로 쓸 때 위치만 외워 지시문을 무시하는 것을 막는다(계획서 1장 언어 준수율).
    - seed 0–199 배치: 중심 x −0.2813~−0.1161, y −0.1502~+0.1503. 좌우 색 순서 6가지 모두 나왔다(27~46번).
      블록 중심 간격은 최소 56.7 mm, 가장 가까운 쌍의 중앙값은 85.3 mm다. 200개 모두 Mirobot 작업 영역 안이다
    - pick up 세 색 × seed 0–19: **59/60**. 실패한 red seed 16은 들어 올렸지만 green을 11 mm 밀었다
      (y로 66 mm, 면 사이 26 mm, 손가락이 벌어지는 방향). 무작위 배치에서 자연히 나온 "가까운 블록" 사례다 (PICKUP.md 5.3)
    - 손 뻗기 세 색 × seed 0–9, 30개 G-code: dry-run 경고 0, 수평 최대 271.5 mm, 역변환 최대 0.013 mm
    - 영역 안쪽 끝(Mirobot X 150~170)이 작업대 높이에서 닿는지는 아직 실측하지 않았다(W5 TABLE_ALIGNMENT 6절). 실물 단계에서 모서리를 먼저 확인한다
    - `scenarios.py adjacent`는 옮길 자리에 세 번째 블록이 있으면 반대쪽에 놓는다. 양쪽 다 막히면 겹쳐 놓지 않고 그 episode를 실패로 알린다
- [ ] **실물 블록 크기** — 시뮬 크기 = 실물 ÷ 0.663
  →

## 3. 좌표·자세 획득 — Panda 정보

`pickup.py`가 지금은 단계별 EEF `xyz_m`와 `rxyz_deg`(scipy extrinsic xyz, 도)를 stdout에만 출력한다.
이 각도 규약은 Mirobot `RxRyRz`(extrinsic XYZ, 9/13)와 같다. EEF는 `grip_site`(파지점)이고, 변환기 기본값 `DEFAULT_POINT = "grip"`과 맞다.

- [ ] **무엇을 기록하나** — 번역기 입력에 맞추면 **매 step action**이 필요하다. 사람이 확인할 값으로는 단계별 keyframe을 쓴다
  → **매 step 기록 (10/7).** `pickup.py --log`가 `data/pickup/<시각>-<mode>-<task>-s<seed>.jsonl`을 남긴다.
  첫 줄 `meta`에는 bddl, register, seed, `settle 0`이 들어가고, step마다 `action`, `eef_pos`, `eef_quat_xyzw`,
  `eef_rxyz_deg`, `joint_pos`(7), `gripper_qpos`, `goal`이 들어간다. 마지막 줄은 `result`다. 단계별 keyframe은 지금처럼 stdout에 출력한다
- [ ] **관절값 추가** — Panda 7관절과 그리퍼. 10/5 회의 노트에 들어 있다.
  Mirobot은 6관절이라 관절값을 그대로 옮기지는 않고, 기록만 해 둔다
  → `joint_pos`로 기록한다 (10/7). 관측에는 꺼져 있어서 `sim.data.qpos`에서 읽는다
- [ ] **파일 저장 허락** — `data/`(git 제외)에 JSONL로 저장한다. rgb_blocks AGENTS.md는 요청 없이 결과 파일을 저장하지 않는 기준이다
  → **허락 (10/7).** `--log`를 줄 때만 저장한다. G-code는 기존 관례대로 `trajectories/`(git 포함)에 둔다

## 4. Mirobot 좌표 변환 — W5 번역기 연결

W5에서 **action 번역**으로 정했다 (9/30).
번역기 `tools/action_to_gcode.py`는 action을 시뮬 Panda에 넣고, 나온 손 자세를 `common/workspace.py`로 Mirobot G0 절대 좌표로 바꾼다.
**10/8 두 단계로 나눴다** — `action_to_poses.py`(action → 손 좌표)와 `poses_to_gcode.py`(손 좌표 → G-code). `action_to_gcode.py`는 둘을 차례로 부른다([DIVISION.md](DIVISION.md) 2.1).
`pickup.py`의 action도 같은 OSC_POSE 7차원이다.

- [ ] **번역기를 우리 장면에서 돌게 하기** — 지금은 LIBERO suite 장면만 받는다(`--suite`, `--task-name`).
  W5 9-①은 "빈 탁상 + 고정 시작 자세"를 제안했다. RGB 블록 BDDL을 쓰는 방법을 정한다
  → **된다 (10/7).** `--bddl`, `--register 파일.py:함수`, `--seed`를 추가했고, 주지 않으면 기록 meta의 값을 쓴다. 기존 suite 사용법은 그대로다.
  초기 자세 노이즈는 LIBERO 기본값이 `None`이라 시작 자세가 같다.
  **재현 확인** — 번역기는 `cosmos-policy/.venv`(LIBERO site-packages)에서, pickup은 conda `libero`(W6 LIBERO)에서 돈다.
  그래도 step마다 손 위치 차이가 손 뻗기는 최대 1.2e-15 m, pick up은 1.2e-6 m였다. pick up의 Goal도 같은 step 105에서 처음 뜬다
- [ ] **기본 짝·배율을 홈 · 0.663으로** — W5 9-①. 지금 `common/workspace.py`는 `DEFAULT_MAPPING = "home"`, 배율 1.0 그대로다
  → 기본값은 바꾸지 않았다. 이번에는 `--scale 0.663`을 직접 줬다. 기본값 변경은 다른 도구에도 영향을 주므로 W5 9-① 항목으로 남긴다
- [x] **pick up G-code를 실물로 보낼 수 있게 (10/8)** — 팀 결정(0장)에 따라 pick up을 그대로 옮긴다.
  - **잡는 높이**: 블록 중심 +15 mm에서 잡는다(`pickup.py` `GRASP_ABOVE_CENTRE_M`). 중심에서 잡으면 플랜지 Z 63.5 mm로 하한 66 mm에 걸린다.
    시뮬 pick up 세 색 × seed 0–19 **60/60** (전날 실패한 red seed 16도 성공 — 손가락이 더 높은 곳에서 닫혀 옆 블록을 덜 건드린다)
  - **그리퍼**: Panda는 action[6]의 부호만 쓴다(robosuite `panda_gripper.py` `format_action`, step마다 0.01씩).
    Mirobot은 `M4 S<값>` 한 줄이 목표 개폐 위치다. 번역기 `--gripper`가 부호가 바뀌는 첫 step 앞에 `M4`를 넣는다.
    기본값은 W4·`robot/inverse_kinematics.py`의 열기 `M4 S40`, 닫기 `M4 S60` (W5 10/5 실측은 활짝 S30, 완전히 닫힘 S70).
    S60이 몇 mm인지, 닫히는 데 몇 초 걸리는지는 아직 재지 않았다. 닫기 뒤 같은 자리 G0 30줄(grasp 단계)이 기다림이 된다
  - **`run_gcode --stream` 거부**: `--stream`은 설정 줄을 먼저 몰아 보내서 이동 사이 `M4`의 순서가 바뀐다.
    이런 파일은 dry-run에서 경고하고 `--stream`이면 보내지 않는다(`stream_blocker`, 테스트 2개). **`--auto`로만 실행한다**
  - pick up 세 색 × seed 0–9, 30개 G-code (`--scale 0.663 --gripper`, scratchpad): Z 하한 아래 0, 수평 최대 271.8 mm, Z 최저 69.8 mm,
    `M4` 2줄씩(스텝 1 열기, grasp 시작 닫기), 재실행 Goal step 30/30 같음. 5개는 Z 71 mm 경고(66–71, 경고만)
  - 줄이 145개 안팎이라 `--auto`로는 오래 걸린다. `--every 5`면 그리퍼 줄을 남긴 채 약 30줄이다(아직 실물에서 안 해 봄)
- [ ] **그리퍼** — 번역기와 G-code는 위치·자세(G0)만 다루고 그리퍼 개폐 명령은 없다.
  pick up이면 필요하다(`common/servo.py` 확인). 손 뻗기로 정하면 필요 없다
  →
- [ ] **`run_gcode --dry-run`** — 도달 범위(수평 280 mm), 각도 30°, Z 하한(66 막기 · 71 경고) 경고가 있는지 확인한다
  → **손 뻗기 3개는 통과, pick up은 막힘 (10/7, seed 0)**

  | G-code (`trajectories/`) | 줄 | 수평 최대 | 각도 최대 | Z 최저 | 블록 위 정지 플랜지 | 목표와 차이 | dry-run |
  | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
  | `2026_10_07-w6-reach-red-s0.gcode` | 114 | 251.3 mm | 2.9° | 85.3 mm | X240.74 Y−60.39 Z85.55 | 0.84 mm | 경고 없음 |
  | `2026_10_07-w6-reach-green-s0.gcode` | 113 | 202.6 mm | 2.9° | 85.2 mm | X199.93 Y0.06 Z85.63 | 0.09 mm | 경고 없음 |
  | `2026_10_07-w6-reach-blue-s0.gcode` | 115 | 248.8 mm | 2.9° | 85.3 mm | X238.70 Y59.19 Z85.55 | 1.53 mm | 경고 없음 |
  | `2026_10_07-w6-pickup-red-s0.gcode` | 146 | 251.3 mm | 2.9° | **62.5 mm** | — | — | **Z 66 아래 32줄 → 보내지 않음** |

  - 손 뻗기는 블록 위에서 손끝이 작업대 위 30 mm에 오도록 멈춘다(플랜지 Z ≈ Zt 55.7 + 30). 목표와의 차이는 블록 배치(±1.1 mm)와 정지 오차를 합친 값이다
  - 마지막 줄은 홈 근처다(X 195~198, Z 228). 처음 몇 줄은 Panda 시작 기울기 3°를 바로잡는 동작이다(B 2.9° → 0)
  - **무작위 배치 변환 확인 (10/7)** — 손 뻗기 세 색 × seed 0–4, 15개 G-code (scratchpad, 저장소에 넣지 않음).
    번역기 경고 0, `run_gcode --dry-run` 경고 0/15, 수평 최대 260.2 mm, Z 최저 85.2 mm.
    **역변환 검산**: G-code를 LIBERO 파지점으로 되돌린 값과 원래 `eef_pos`의 차이가 Mirobot 기준 **최대 0.013 mm**였다(파일 소수 둘째 자리 반올림).
    변환과 역변환에 같은 값을 쓰므로 `F`와 `L`의 오차는 이 검산으로 잡히지 않는다(roundtrip_check와 같은 한계)
  - **pick up이 막히는 이유**: 블록 중심(작업대 위 20 mm)에서 잡으면 플랜지 Z = 55.7 + 0.663 × 11.8 ≈ 63.5 mm다.
    닫은 집게가 작업대에 닿는 높이(60.7 mm)에 여유를 둔 하한 66 mm보다 낮다. 3단계로 가려면 정해야 한다 — 잡는 높이를 블록 위쪽으로 /
    실물 블록 크기 / 이 파일만 `--z-floor` 낮추기(Zt 측정 때처럼)

## 5. 실물 — 로봇 노트북 (카메라 불필요)

W5 9-③: 블록 자리에 종이로 표시하고, 손끝의 위치·높이를 자로 잰다. 처음에는 `--auto`로 한 줄씩 실행한다.
보낼 파일은 4절 표의 손 뻗기 G-code 3개다. 로봇 노트북이 받으려면 push가 필요하다.
줄이 113~115개라 `--auto`로는 waypoint마다 멈춰 오래 걸린다. 줄 수를 줄이려면 번역기 `--every N`을 쓴다(아직 안 함).

- [ ] 작업대 높이에서 안쪽 한계(X 150~170) 확인 (W5 9절)
  →
- [ ] G-code 실행과 손끝 오차 측정
  →

## 6. 카메라 도착 후 — 이번 주 범위 밖

- [ ] D405 색·화각·해상도 보정을 RGB 블록 장면에 적용 (동료 [D405_LIBERO_CAMERA.md](../W5/D405_LIBERO_CAMERA.md)). 지금 장면은 LIBERO 기본 `agentview` 512×512다
- [ ] 영상만으로 색과 좌표를 판단하는 pick up — 지금은 정답 좌표와 대상 이름을 쓴다 (PICKUP.md 7장)
- [ ] VLA 학습 데이터 — episode마다 영상·지시문·action·proprio. 계획서 6장 로깅 스키마와 같은 형식으로
- [ ] pick up이 확인하지 않은 범위 — region 밖, 블록 회전(yaw), 가까운 배치 (PICKUP.md 8장)
  → 가까운 배치는 `--scenario`로 재현했다 (10/7). 그리퍼 방향 고정이라 실패한다. 그리퍼를 돌려 잡는 것은 아직이다 (PICKUP.md 5.3)

## 7. 끝난 것

- [x] **Panda pick up과 `Up` Goal** (10/6) — 15/15 성공, 브라우저 `--pickup`으로 세 색 화면 확인, `dd9c28c` push
- [x] **동료 README 문장 정정** — "로컬 Goal은 배치 확인용"을 "색상 task goal False가 정상"으로 고쳤다 (10/6, 같은 커밋)
- [x] **블록 자리를 Mirobot 범위로** (10/7) — 2절. 새 자리에서 pick up 15/15
- [x] **좌표·자세 기록과 번역기 연결** (10/7) — 3·4절. 손 뻗기 G-code 3개 dry-run 통과
- [x] **브라우저 조작판** (10/7) — seed 선택, 일시정지, 한 step 이동, 되돌리기, 자동 진행. 10/6부터 상태 문구가 멈춰 있던 페이지 오류도 고쳤다
- [x] **가까운 배치 시나리오** (10/7) — `--scenario adjacent|sandwich`, 지금 pick up은 실패 (PICKUP.md 5.3)

## 8. 다음 미팅에 가져갈 질문

- [ ] 첫 과제는 pick up인가, 손 뻗기인가 (2절)
- [ ] LIBERO 환경 용도 — 배치 기준 / 시뮬 데이터(실제 데이터와 혼합) / 시뮬 평가 (2절, W5 8절)

## 관련 문서

- [../meetings/2026-10-05.md](../meetings/2026-10-05.md) — 이번 주 action plan과 파이프라인
- [rgb_blocks/PICKUP.md](rgb_blocks/PICKUP.md) — pick up 결정·구현·결과
- [rgb_blocks/README.md](rgb_blocks/README.md) — RGB 블록 장면 실행법
- [../W5/CHECKLIST.md](../W5/CHECKLIST.md) — 4-3 색 블록 장면 결정, 8 미팅 질문, 9 다음 action plan
- [DIVISION.md](DIVISION.md) — 10/8 분업, 손 좌표 JSONL 형식, 각 쪽 할 일
- [../W5/PIPELINE.md](../W5/PIPELINE.md) — 번역기 `action_to_gcode.py` 기록
- [../W5/TABLE_ALIGNMENT.md](../W5/TABLE_ALIGNMENT.md) — 좌표 맞추기, 배율 0.663, 블록 자리 계산
- [../W5/D405_LIBERO_CAMERA.md](../W5/D405_LIBERO_CAMERA.md) — D405와 LIBERO 영상 보정 (동료)
- [../plan/UROP_프로젝트_계획.md](../plan/UROP_프로젝트_계획.md) — 6장 스크립트 궤적 생성, 로깅 스키마, 액션 표현
