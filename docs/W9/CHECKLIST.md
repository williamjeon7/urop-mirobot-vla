# W9 — 작업 목록 (3·4번: 시간 동기화, LIBERO 호환 HDF5)

> **절차** · 확인 2026-10-28 · **갱신 2026-10-29** · 기준 10/28 action plan, `5ab0ded`, `cosmos-policy@18a2acc`
> 10/28 action plan 중 3번(Timestamp 기반 데이터 동기화)과 4번(LIBERO 호환 HDF5 데이터셋 생성)을 할 일로 쪼갠 것.
> `→` 뒤 빈칸은 **미리 채우지 않는다**.

계획 원문: [../meetings/2026-10-28.md](../meetings/2026-10-28.md).
1·2·5번(동료·공동)은 여기서 다루지 않는다. 3·4번과 맞닿는 곳 — 넘겨받는 것, 넘겨주는 것 — 만 적는다.
W5에서 넘어온 것: [../W5/CHECKLIST.md](../W5/CHECKLIST.md) 7-2절(시간 맞추기), 2-4절의 `libero_follow` 시간 기준 모드.
작업 기록(시간 순서 목차): [WORKLOG.md](WORKLOG.md). 자세한 설명: [DATASET_HDF5.md](DATASET_HDF5.md)(HDF5 형식·도구), [FOLLOW.md](FOLLOW.md)(따라가기·proprio).

## 0. 이번 주 목표

**Mirobot 실물 기록과 Panda 시뮬 기록을 Cosmos Policy 의 LIBERO 로더가 그대로 읽는 HDF5 로 만든다.**

- **3번** — 녹화가 끝난 뒤 서버에서, 0.05초 격자 한 칸 = `Image(t) + Proprio(t) + Action(t)` 로 묶는다. **실시간이 아니다**
- **4번** — 그 칸들을 LIBERO 형식 HDF5 로 쓰고, Cosmos 로더로 읽어 확인한다

### 10/28 정한 것

| 항목 | 결정 | 자세히 |
| --- | --- | --- |
| 카메라 | Mirobot 쪽은 **손목 D405 하나**. 외부 영상(agentview)은 시뮬 Panda 렌더링 | 2절 |
| 맞추는 방법 | **(나)** — 녹화 뒤 서버에서, 시뮬 Panda 가 실물 자세를 0.05초 격자로 따라가며 외부 영상과 action 을 다시 만든다 | 아래 그림, 3-2 |
| proprio 위치·자세 | **실물 Mirobot 기록**을 Panda 형식으로 변환한다. 실행할 때와 같은 출처 | 3-2 |
| proprio 손가락 2칸 | **B'** — Mirobot `M4` 명령 기준, 값은 Panda 뜻(열림 0.04, 블록 잡음 0.019) | 3-2 |
| 시뮬·실물 결과가 다른 에피소드 | **둘 다 성공한 것만 학습.** 나머지는 표시해서 보관(실패 감지용) | 3-3 |
| 따라가기 오차 기준 | **10/5 실물 기록으로 먼저 재고 정한다.** 그동안 잠정 기준 실물 5 mm · 2° | 3-3 |
| 녹화 방식 | 2번 담당이 먼저 찍고, 받은 뒤 확인해 부족하면 다시 요청한다 | 2절 |

```
[녹화 — 로봇 노트북, 실시간 (2번)]       [녹화 뒤 — 서버, 언제든 (3·4번)]
Mirobot 이 G-code 실행                     ① 상태 기록을 0.05초 격자 t_k 에 맞춘다
 ├ 손목 D405 프레임 + 시각         ──▶     ② 시뮬 Panda 가 "t_(k+1) 의 실물 자세"로 가도록 action k 를 낸다
 ├ 로봇 상태(`?`) + 시각                      → action 라벨, 스텝 k 의 외부 영상 (실물과 같은 장면·seed)
 └ 그리퍼 명령(`M4`) + 시각                 ③ 칸 k 묶기 (아래)
                                            ④ 시뮬·실물 둘 다 성공한 에피소드만 HDF5 로

칸 k = ( 외부: 시뮬 스텝 k 렌더링 | 손목: t_k 에 가장 가까운 실물 프레임 |
         proprio: 실물 t_k 자세 → Panda 형식, 손가락은 B' | action k: 시뮬이 t_(k+1) 로 가도록 낸 것 )
```

왜 이렇게 묶는지 — 시계 대신 자세로 맞추는 이유, 한 칸 앞 목표, 0.05초 고정, 시뮬 원본 action 을 안 쓰는 이유 — 는 [FOLLOW.md](FOLLOW.md) 1·2절.

### 목표 형식

Cosmos LIBERO 로더가 읽는 형식(키·모양, 짝, 파일 이름 = 지시문, 묶음·비율)은 [DATASET_HDF5.md](DATASET_HDF5.md) 1–3절.

### 지금 상태 (10/28)

| 단계 | 상태 | 어디 |
| --- | --- | --- |
| 실물 기록 (2번, 동료) | 아직. 2번 담당이 먼저 찍고 받은 뒤 확인한다 (10/28). 지금은 D405 Viewer 로 MP4 시험 녹화 단계 | [../W7/CHECKLIST.md](../W7/CHECKLIST.md) |
| 카메라 | **손목 D405 하나 (10/28).** 외부(agentview) 영상은 시뮬 Panda 렌더링으로 채운다 | 2절 |
| 로봇 상태 기록 | **있다** — `run_gcode --stream` 이 보낸 줄 시각과 `?` 응답(Cartesian·Angle)을 남긴다. **11.3 Hz** (10/5, 목표 20 Hz 이상) | `tools/run_gcode.py:163`, W5 7-2 |
| 10/5 실물 상태 기록 | 로봇 노트북 `data/gcode_run/` 에만 있다. 서버로 옮기면 따라가기 오차를 지금 잴 수 있다 | 3-3 |
| 카메라 프레임 시각 | **없다** — Viewer MP4 에는 프레임별 시각이 없다. `robot/camera_bridge.py` 는 최신 프레임 하나만 보낸다 | 3-1 |
| 두 기록의 시계 | **다르다** — 로봇은 `perf_counter`(프로세스 안 상대 시각), 카메라 브리지는 `time.time()` | W5 7-2 |
| 라벨(시뮬 Panda 따라가기) | 도착 기준뿐. 시간 기준 모드 없음 | `tools/libero_follow.py`, W5 2-4 |
| 시뮬 Panda 기록 | step 마다 action·손·관절·그리퍼 JSONL (`pickup.py --log`). **영상은 없다** | [../W6/CHECKLIST.md](../W6/CHECKLIST.md) 3절 |
| 두 카메라 256 px 렌더링 | 있다 — pick up 하며 두 시점을 step 마다 찍는다 | [panda_cameras/two_view_video.py](panda_cameras/two_view_video.py) |
| HDF5 | **Panda 시뮬 90개 만듦, Cosmos 로더로 읽힘** (10/29). 1번 환경 수정 뒤 다시 만든다 | `tools/pickup_to_hdf5.py`, `tools/check_cosmos_dataset.py`, [DATASET_HDF5.md](DATASET_HDF5.md) |
| 좌표·회전 변환 | 있다 — Mirobot ↔ LIBERO 위치 왕복 최대 0.013 mm (W6). proprio 로 쓰려면 조립이 남았다 | 3-2, `common/workspace.py`, `common/rotation.py` |

## 1. 순서

```
2. 먼저 맞출 것 ── 받은 기록 확인 기준, 시뮬 배치, 누가 무엇을
        ▼
3. 시간 맞추기 ─── (녹화 뒤, 서버) 0.05초 격자 → 시뮬 따라가기 → 칸 묶기 → 오차·누락 검증
        ▼
4. HDF5 ────────── Panda 시뮬 (실물 없이 먼저) → Mirobot 실물 → 로더로 읽기
```

실물 녹화 없이 지금 할 수 있는 것:

1. **따라가기 오차 재기** (3-3) — 10/5 실물 기록을 서버로 옮기면 된다
2. **proprio 변환 조립과 왕복 확인** (3-2)
3. **Panda 시뮬 HDF5** (4-1) — 다만 1번(환경 수정, 동료)이 끝난 장면에서 다시 뽑아야 한다

## 2. 먼저 맞출 것

- [x] **카메라 몇 대인가** — 로더는 `agentview_rgb` 와 `eye_in_hand_rgb` 를 둘 다 요구한다(없으면 KeyError).
  출발 체크포인트도 3인칭 + 손목 두 장으로 배웠다 ([../W5/CHECKPOINT.md](../W5/CHECKPOINT.md) 0절).
  action plan 2번에는 D405 하나만 적혀 있다. 고정 카메라와 손목 카메라를 둘 다 찍는지 확인한다
  → **손목 D405 하나 (10/28).** 외부 영상은 시뮬 Panda 것을 쓴다. `eye_in_hand_rgb` = 실물, `agentview_rgb` = 시뮬 렌더링으로 채운다
- [x] **외부 영상을 어디서 찍나** — (가) G-code 를 만든 시뮬 원본에서 실물과 손 자리가 같은 스텝을 골라 붙이기 /
  (나) 시뮬 Panda 가 실물 자세를 따라가게 하며 다시 찍기
  → **(나) (10/28).** 라벨을 만드는 시뮬과 같은 시뮬이라 외부 영상·action 이 한 번에 나온다. 녹화가 끝난 뒤 서버에서 한다(실시간 아님).
  실행할 때는 번역기의 시뮬 Panda(서버, ACTION_MEANING 1-9)에서 찍는다 — 그때는 시뮬이 명령을 직접 내므로 같은 순간이다
- [ ] **시뮬 블록 배치 = 실물 배치** — 외부 영상에 보이는 블록은 시뮬 블록이다. 에피소드마다 실물 블록을 놓은 자리
  (seed → 종이 표시, [../W6/MIROBOT_PICKUP.md](../W6/MIROBOT_PICKUP.md))와 시뮬 배치가 같아야 한다
  →
- [ ] **받은 기록 확인** — 2번 담당이 먼저 찍고, 받은 뒤 아래를 확인해 부족하면 다시 요청한다 (10/28).
  **1·2가 없으면 나중에 만들 수 없다** — 다시 찍어야 한다
  1. 손목 프레임마다 시각, 로봇 기록과 같은 시계 (3-1)
  2. 로봇 상태 기록 — 시각 포함, 20 Hz 이상 (3-1)
  3. 카메라 조건 — 노출·화이트밸런스 고정, 에피소드 사이 카메라 위치 그대로
  4. 화면 — 손가락이 보이고, 방향이 Panda 손목 영상과 같다 ([panda_cameras/both_flipud.png](panda_cameras/both_flipud.png) 오른쪽)
  5. 빠진 프레임, 에피소드마다 seed·색·실물 성공 여부, 그리퍼 명령(`M4 S` 값과 보낸 시각)
  →
- [ ] **라벨 만들기는 누가** — `libero_follow` 에 시간 기준 모드를 넣는 일(W5 2-4에서 넘어옴, 3-2). 4번 `actions` 에 필요하고,
  5번 "Action Space 및 Proprioception 형식 통일"과 겹친다
  →
- [ ] **4번 범위에 Panda 시뮬 90 에피소드가 들어가나** — action plan 4번은 실물 영상 변환 위주이고, 5번이 Panda 90 + Mirobot 10 혼합이다
  →

## 3. 시간 맞추기 (3번) — 녹화 뒤, 서버

실시간이 아니다. 녹화된 기록을 놓고 서버에서 몇 번이든 다시 돌릴 수 있다.

### 3-1. 받은 기록 확인 — 같은 시계, 충분히 촘촘하게

W5 7-2에서 넘어온 두 조건이다. **(1) 기록마다 시각, (2) 20 Hz 보다 촘촘하게** (ACTION_MEANING 1-4).

- [ ] **같은 시계** — 로봇과 카메라 기록에 같은 시스템 시각(`time.time()`)이 남았는지.
  `perf_counter` 는 프로세스마다 기준점이 달라 다른 프로그램의 시각과 바로 비교할 수 없다. 지금 `run_gcode` 는 `t0` 기준 상대 시각만 남긴다(`run_gcode.py:185, 221`)
  →
- [ ] **D405 프레임 시각** — Viewer MP4 에는 없다. `.bag` 녹화나 `pyrealsense2` 기록이어야 한다.
  D405 가 주는 프레임 시각(`get_timestamp()`, ms)의 기준(`get_frame_timestamp_domain()`)이 하드웨어 시계인지 호스트 시계인지 확인한다
  →
- [ ] **상태 기록 20 Hz 이상** — 10/5 실측 11.3 Hz (간격 43–150 ms). 보내기와 묻기가 한 루프에 묶인 탓으로 추정한다(확인 안 함).
  모자라면 둘을 떼 달라고 요청한다. 9/13 `?` 만 묻던 `move_and_poll` 은 77 Hz 였다
  →
- [ ] **상태 시각의 폭** — `?` 를 보낸 시각과 응답을 받은 시각이 둘 다 있으면 가운데를 상태 시각으로 쓰고, 폭을 불확실성으로 본다.
  지금은 받은 뒤 시각만 남는다(`run_gcode.py:221`)
  →
- [ ] **그리퍼** — `?` 응답에 그리퍼 값이 있는지. 손가락 2칸은 `M4` 명령으로 만들지만(B'), 값이 있으면 검증에 쓴다
  →
- [ ] **에피소드 경계** — 시작은 첫 줄을 보낸 시각(홈에서 정지), 끝은 마지막 이동 뒤 Idle 로 멈춘 시각(`run_gcode` 의 정지 판정)으로 할지
  →

### 3-2. 0.05초 격자에 묶기

격자 `t_k = t_start + k × 0.05 s`.

- [ ] **시뮬 따라가기 — action 라벨과 외부 영상** — 실물과 같은 장면·seed 에서 시뮬 Panda 를 실물 시작 자세에 둔다.
  스텝 k 마다 **`t_(k+1)` 의 실물 자세**를 목표로 action k 를 낸다(시간 기준, 도착을 기다리지 않는다). action k 를 내기 **전에** agentview 를 찍는다.
  `libero_follow` 에 시간 기준 모드로 넣는다 (W5 2-4)
  → 간단한 버전을 scratchpad 시험 코드로 만들어 가짜 실물 기록으로 돌렸다 (10/29). 도구 자리(`libero_follow` 확장 / 새 파일)와 실행 환경은 미정 — [FOLLOW.md](FOLLOW.md) 4·5절
- [ ] **시뮬 그리퍼** — 실물 `M4` 명령 시각에 시뮬 그리퍼 action 부호를 바꾼다. 실물 서보가 늦게 닫히면(손목 영상으로 확인) 그만큼 옮긴다.
  시뮬 블록을 실제로 집어야 외부 영상이 맞는다
  →
- [ ] **Image(t_k)** — 손목은 `t_k` 에 가장 가까운 실물 프레임 (30 FPS 면 최대 16.7 ms 차이, 두 프레임을 섞지 않는다).
  외부는 시뮬 스텝 k 렌더링 (`np.flipud`)
  →
- [ ] **Proprio 위치·자세 — 실물 (10/28)** — 앞뒤 상태 기록 사이를 보간하고(위치는 선형, 자세는 slerp) Panda 형식으로 바꾼다.
  부품은 있다 — 위치 `common/workspace.py` `mirobot_to_libero_flange_m`, 자세 `common/rotation.py` `euler_xyz_deg_to_quat`·`mirobot_to_libero_quat`·`quat_wxyz_to_xyzw`. 남은 조립:
  - 입력 — G-code 대신 `?` 응답의 Cartesian 을 읽는다
  - 위치 — 플랜지가 아니라 **파지점**으로 낸다 (`robot0_eef_pos` 는 파지점)
  - 쿼터니언 — **`xyzw`** 로 낸다. `common/schema.py` STATE 는 `wxyz` 다 ([../W3/ROTATION.md](../W3/ROTATION.md) 5절)
  - 설정 — 그 에피소드 G-code 를 만든 짝·배율·공구·자세 모드로 읽는다. 머리말 `; pair`·`; tool`·`; point` 에서 가져온다(`libero_follow.targets_from_gcode` 와 같은 방식).
    다르게 읽으면 궤적 전체가 밀리거나 기운다
  → 변환은 **`common/proprio.py` (10/29)** — 파지점 위치, `xyzw`, 머리말 설정 읽기, 쿼터니언 부호 맞추기까지. `?` 응답을 읽어 넣는 부분은 아직 — [FOLLOW.md](FOLLOW.md) 3절
- [x] **proprio 9칸 왕복 확인** — 시뮬 Panda proprio → G-code → 다시 proprio 가 같은지. 위치는 W6 에서 확인했고(최대 0.013 mm), 자세(쿼터니언)는 아직이다
  → **위치 최대 0.0112 mm, 자세 최대 0.0070°, 부호 모두 같음** (W6 실제 파일 쌍 G0 31줄, 10/29). G-code 반올림만큼이다 — [FOLLOW.md](FOLLOW.md) 3-3절
- [ ] **손가락 2칸 — B' (10/28)** — Mirobot `M4` 명령을 기준으로 하되, 값은 Panda 가 쓰는 뜻에 맞춘다.
  단순히 S30 → 0.04, S70 → 0 으로 바꾸면 블록을 잡은 장면이 "빈손으로 닫음"(0 근처)처럼 보여 Panda 데이터와 뜻이 반대가 된다

  | Mirobot 명령 | 손가락 값 (왼쪽. 오른쪽은 부호 반대) | 근거 |
  | --- | --- | --- |
  | 열기 | 0.0396–0.0399 (Panda 열림) | 시뮬 pick up red seed 0 (10/7), approach·lower |
  | 닫기 | **0.019** — Panda 가 40 mm 블록을 잡았을 때 | 같은 기록, grasp 끝·lift |
  | 그 사이 | 닫히는 시간 동안 두 값을 잇는다. 닫히는 시간은 손목 영상(손가락이 보임)으로 잰다 | |

  시뮬 블록 크기가 바뀌면 "닫기" 값을 다시 잰다. 실물이 블록을 놓쳐도 "잡음" 값이 나오지만, 그런 에피소드는 3-3 에서 빠진다
  → 값 변환은 `common/proprio.py` `fingers` (10/29). 닫히는 동안은 직선으로 잇는다(임의 판단). 닫히는 시간은 손목 영상이 와야 잰다
- [ ] **Action(k)** — 시뮬 따라가기의 action k
  →
- [ ] **짝 규칙** — `Image(t_k)`·`Proprio(t_k)` 는 action k 를 내기 **전** 상태다. LIBERO 재생성 데이터와 같은 순서로 맞춘다 ([DATASET_HDF5.md](DATASET_HDF5.md) 2절)
  →

### 3-3. 검증

- [ ] **따라가기 오차 — 먼저 재고 기준을 정한다 (10/28)** — 칸마다 시뮬 손과 실물 손(Panda 좌표로 바꾼 것)의 위치·자세 차이.
  잠정 기준은 에피소드 안 최대값이 **실물 5 mm**(시뮬 약 7.5 mm, 외부 영상에서 약 2 px) · **2°** 이하
  - 먼저 10/5 실물 `run_gcode --stream` 기록(로봇 노트북 `data/gcode_run/`)으로 잰다. 넘는 구간이 접근인지 집기인지도 본다
  - 넘으면 (1) 스텝마다 시뮬을 저장해 두고 다음 스텝에 목표에 도착하는 action 을 찾는다 — 저장했다 되돌렸을 때 같은 결과가 나오는지 먼저 확인한다
    (2) 그래도 넘는 에피소드는 표시하고 뺀다
  → **가짜 실물 기록(10/5 실측 속도)으로 위치 최대 8.2 mm(움직일 때), 집는 순간 2.2 mm, 자세 0.68°** (10/29). 10/5 실물 기록으로는 아직 — [FOLLOW.md](FOLLOW.md) 4절
- [ ] **속도** — Mirobot 속도를 시뮬 크기(÷ 0.663)로 키워도 Panda action 한계(±1) 안에서 따라가는지
  → 가짜 기록(2.34배 느림)에서는 시뮬이 블록을 집어 들었다 (10/29). 실물 기록으로 다시 본다 — [FOLLOW.md](FOLLOW.md) 4절
- [ ] **시뮬·실물 결과 — 둘 다 성공한 것만 학습 (10/28)** — 시뮬 성공은 대상 블록을 집어 들었는가(블록이 들림, 손가락이 잡고 있음). 다른 블록 1 cm 조건은 뺐다 (10/29, [DATASET_HDF5.md](DATASET_HDF5.md) 4절),
  실물 성공은 2번 기록. 결과가 다른 에피소드는 표시해서 보관한다 — 4단계 실패 감지 데이터로 쓴다 ([계획 7절](../plan/UROP_프로젝트_계획.md#7-failure-detection-설계))
  →
- [ ] **누락** — 에피소드마다 프레임 간격이 1.5 프레임(50 ms)을 넘는 곳, 상태 무응답, 격자 칸 중 앞뒤 상태 기록이 0.1초 넘게 떨어진 칸을 센다
  →
- [ ] **손목 영상 ↔ 로봇 기록 시계 오차** — 영상과 기록 양쪽에 보이는 사건으로 잰다. 기준은 LIBERO 한 스텝(50 ms)보다 작게 (제안)
  - 출발 — 상태가 처음 바뀐 시각 vs 영상에서 팔이 처음 움직인 프레임
  - 그리퍼 닫기 — `M4` 보낸 시각 vs 영상에서 손가락이 움직이기 시작한 프레임
  →
- [ ] **눈으로 확인** — 한 에피소드를 외부(시뮬)·손목(실물) 두 그림을 나란히 놓고 Proprio 숫자(손 위치·그리퍼)를 붙인 영상으로 만든다.
  시뮬 손과 실물 손목 영상이 같은 순간에 출발·정지·집기를 하는지 본다
  →

## 4. LIBERO 호환 HDF5 (4번)

### 4-1. Panda 시뮬 — 실물 없이 지금

- [x] **기록 스크립트** — `pickup.py` 를 돌리며 step 마다 두 카메라(256×256, `np.flipud`), `robot_states`, `actions` 를 모은다.
  `on_step` 은 action **뒤** 관측을 넘기므로 앞 관측과 짝짓는다 ([DATASET_HDF5.md](DATASET_HDF5.md) 2절). 두 카메라 렌더링은 `panda_cameras/two_view_video.py` 와 같다
  → **`tools/pickup_to_hdf5.py` (10/29).** 시험판 3색 × seed 0–1 = 6/6 성공, 짝 순서 확인 — [DATASET_HDF5.md](DATASET_HDF5.md) 4·6절
- [x] **`robot_states`** — `robot0_gripper_qpos`(2) + `robot0_eef_pos`(3) + `robot0_eef_quat`(4, `xyzw`) 를 그대로 이어 붙인다 (`regenerate_libero_dataset.py:222`)
  → 그대로 이어 붙였다. 쿼터니언 norm 1, 시작 자세가 `xyzw` top-down 으로 읽힌다 (10/29) — [DATASET_HDF5.md](DATASET_HDF5.md) 6절
- [x] **성공한 에피소드만** — LIBERO 재생성 데이터도 성공한 것만 남겼다 (`regenerate_libero_dataset.py:299-300`)
  → 대상 블록을 집어 들었는가만 본다 — W6 의 "다른 블록 1 cm" 조건은 뺐다 (10/29 사용자 결정). 90개 모두 성공 — [DATASET_HDF5.md](DATASET_HDF5.md) 4·6절
- [ ] **배치** — seed 마다 무작위 위치·색 순서 (W6 `work_region`). 90개를 세 색에 어떻게 나눌지 (예: 색마다 30 seed)
  → 잠정 색마다 30개, 세 색이 seed 0–29 를 같이 쓴다 (10/29, 임의 판단). 같은 seed = 같은 배치를 확인했다 — [DATASET_HDF5.md](DATASET_HDF5.md) 6-2절
- [ ] **1번 환경 수정 뒤 다시 뽑기** — 카메라 위치·색·테이블이 바뀌면 이전 영상은 쓸 수 없다
  →

### 4-2. Mirobot 실물

- [ ] **손목 영상 256×256 으로** — D405 848×480 을 어떻게 줄일지(가운데 정사각형 자르기 → 줄이기 등)는 1번 카메라 맞추기 결과를 따른다.
  Panda 손목 카메라 기준은 fovy 75°, 파지점에서 접근축 뒤로 9.7 cm · 옆으로 5 cm ([panda_cameras/cameras.json](panda_cameras/cameras.json))
  →
- [ ] **외부 영상** — `agentview_rgb` 는 3-2 시뮬 따라가기의 렌더링이다. 4-1 과 같은 장면·카메라라 Panda 시뮬 데이터와 외부 영상의 분포가 같다
  →
- [ ] **RGB 순서** — OpenCV 로 읽은 프레임은 BGR 이라 바꾼다 ([../W5/D405_LIBERO_CAMERA.md](../W5/D405_LIBERO_CAMERA.md) 2.3절)
  →
- [ ] **원본 uint8 vs JPEG** — 로더는 둘 다 읽는다. 원본은 두 카메라 × 256×256×3 = 한 칸 384 KB, 300 칸이면 약 118 MB. LIBERO 재생성은 JPEG 95. action plan 은 uint8
  →
- [ ] **`actions`·`robot_states`** — 3-2 의 결과. `robot_states` = [손가락 B' 2, 실물 위치 3, 실물 쿼터니언 `xyzw` 4], `actions` = 시뮬 따라가기의 action
  →

### 4-3. 공통 — 파일·폴더·남길 것

- [ ] **파일 이름 = 지시문** — 지시문 하나에 파일 하나, 그 안에 `demo_0`, `demo_1`, …
  예: `MIROBOT_SCENE1_pick_up_the_red_block_on_the_table_demo.hdf5` → "pick up the red block on the table".
  **실행할 때 넣는 문장과 글자 하나까지 같아야 한다** — T5 임베딩을 문장으로 찾는다. 지금 W6 문장은 `tasks.py` "Pick up the red block on the table." (대문자·마침표),
  BDDL `:language` 는 마침표 없음이라 이미 둘이 다르다. 하나로 정한다
  → 잠정 `pick up the <색> block on the table` 로 시험판을 만들었고, 로더가 파일 이름에서 그대로 되살렸다 (10/29).
  확정과 실행 쪽(`tasks.py`·BDDL) 문장 맞추기는 남았다
- [ ] **폴더와 비율** — Panda 시뮬과 Mirobot 실물을 다른 폴더에 둔다. 로더는 step 단위로 고르게 뽑으므로 **90/10 은 에피소드 수가 아니라 step 수 비율**로 나온다.
  실물 에피소드가 더 길면(Mirobot 이 느리면) 실물 비중이 커진다. 5번과 맞춘다
  →
- [ ] **no-op 거르기** — LIBERO 재생성 데이터는 위치·회전 칸이 모두 0 에 가깝고(문턱 1e-4) 그리퍼가 앞 step 과 같은 action 을 뺐다 (`regenerate_libero_dataset.py:89, 209`).
  우리도 같은 규칙을 쓸지. 시뮬 pick up 의 grasp 단계, 실물에서 멈춰 있는 칸이 영향을 받는다
  → Panda 시뮬 시험판은 이 규칙으로 0개였다 (10/29). 실물은 아직
- [ ] **더 남길 것** — 로더는 안 읽지만 상위집합 기록 원칙([계획 6절](../plan/UROP_프로젝트_계획.md#로깅-스키마-상위집합-기록-원칙))대로
  `obs/joint_states`, `obs/ee_states`, Mirobot 원본 값(Cartesian mm·deg, 관절각, `M4 S`, 시각), seed, 시뮬·실물 성공 여부, 따라가기 오차를 같이 남길지
  → Panda 시뮬은 `obs/joint_states`·`gripper_states`·`ee_states`, `phases`, seed 를 남긴다 (10/29, 임의 판단). Mirobot 쪽은 실물 때
- [ ] **저장 위치** — `data/` 아래 (git 제외, `*.hdf5` 도 제외). HDF5 는 커밋하지 않고 만드는 스크립트를 남긴다 (`tools/demos_to_hdf5.py` 와 같은 원칙)
  →

### 4-4. 로딩 검증

- [ ] **Cosmos 로더로 읽기** — `LIBERODataset(data_dir=…)` 로 에피소드 수, step 수, 지시문 목록(`unique_commands`), 한 칸의 모양을 확인한다.
  `t5_text_embeddings_path=""` 면 만드는 데까지는 T5 없이 된다
  → **`tools/check_cosmos_dataset.py` (10/29).** 에피소드 6, step 880, 지시문 3개, 샘플 모양 정상 (T5 는 가짜) — [DATASET_HDF5.md](DATASET_HDF5.md) 5·6절
- [ ] **T5 임베딩** — 우리 지시문은 기존 `libero_t5_embeddings.pkl` 에 없다. 새로 만들려면 `google-t5/t5-11b` 인코더가 필요하다 (`get_t5_emb.py:25`).
  **크기가 커서 받기 전에 확인한다**
  →
- [ ] **`dataset_statistics.json`** — `data_dir` 에 처음 한 번 계산해 저장하고 다음부터는 읽기만 한다. **데이터를 바꾸면 지워야 다시 계산된다.**
  Panda·Mirobot 이 한 통계로 정규화된다 — 5번과 공유
  → **우리 데이터로 계산하면 회전 action 이 x·z 약 29–32배, y 약 5배 크게 펴지고, 쿼터니언 칸은 작은 흔들림이 부풀려진다** (10/29, 90개 기준).
  우리 값은 LIBERO 통계 범위 안이라 LIBERO 통계를 그대로 쓸 수 있다. 5번과 정한다 — [DATASET_HDF5.md](DATASET_HDF5.md) 7절
- [x] **되돌려 보기** — HDF5 에서 에피소드 하나를 꺼내 두 카메라 그림 + Proprio 숫자 + action 을 영상으로 만든다 (3-3 과 같은 영상을 HDF5 에서)
  → **`tools/hdf5_to_mp4.py` (10/29).** 색마다 무작위 2개를 서버 `docs/W9/hdf5_check/` 에 (git 제외) — [DATASET_HDF5.md](DATASET_HDF5.md) 6-3절

## 5. 미팅에 가져갈 질문

- 외부 영상을 시뮬로 채우는 것 — 정책이 블록 위치를 시뮬 화면에서 읽을 수 있어서, 언어 준수율이 실물 인식이 아니라 시뮬 화면으로 풀릴 수 있다.
  보고서에 한계로 적을지, 고정 카메라를 더할지 (USB 웹캠도 `robot/camera_bridge.py` 로 받을 수 있다) (2절)
- 90/10 은 에피소드 비율인가 step 비율인가 (4-3)
- 정규화 통계 — 우리 데이터로 새로 계산할지, LIBERO 통계를 그대로 쓸지. 새로 계산하면 회전 action 이 수십 배 크게 펴진다 (4-4)
- Panda 시뮬 HDF5 와 라벨 만들기(시뮬 따라가기)는 누가 (2절)
