# 정책 실행 도구 — 학습한 정책을 실물 Mirobot 에서 돌리기

> **설계** · 확인 2026-11-05 · 기준 `cosmos-policy@18a2acc`, 옛 파랑 녹화 10개 `docs/W9/data/raw/layoutblue1–10`(11/02 `영상1–10` 에서 이름 변경), HDF5 `data/hdf5_mix/mirobot_real/`
> 학습한 정책을 실물 Mirobot 에서 end-to-end 로 돌리는 도구. 무엇을 왜 만들었는지, 녹화로 확인한 것, 남은 결정.

**2026-11-06 실행 도구 추가:** 현재 학습된 `follow` 모델은 아래 B 방식의 가상 Panda 변환기로 연결했다.
노트북 준비부터 실제 실행까지는 **[DEPLOY_MIROBOT.md](DEPLOY_MIROBOT.md)**를 따른다. 아래의 결정 대기·루프 미구현 기록은 이전 조사 시점의 상태다.

계획: [../meetings/2026-11-2.md](../meetings/2026-11-2.md) action plan 3번. 학습 쪽 배경: [../W9/FINETUNE.md](../W9/FINETUNE.md) 7절(평가 경로 — 있는 것·빠진 것).

현재 90개 시연을 학습하고 실제 로봇에서 평가하는 논문 실험 절 형식의 계획과 실행 명령은 [MIROBOT_EXPERIMENT.md](MIROBOT_EXPERIMENT.md)에 정리했다. 이 문서의 수치 검증은 아래에 적은 11/03의 옛 녹화를 대상으로 한 결과다.

## 0. 왜, 무엇을

학습은 한 번 끝까지 갔지만(W9 1차 파인튜닝) **학습한 정책을 돌려 볼 도구가 없었다.** 교수님 의견(11/02)은 어떤 정책으로든 end-to-end 를 먼저 해 보라는 것이다.
end-to-end 한 바퀴는 이렇다.

```
D405 프레임 ─┐                          ┌─ Mirobot 목표 자세 16개 (X Y Z A B C) + 집게 M4 S..
`?` 응답 ────┼─[관측 만들기]─ 정책 ─ action 16개 ─[명령 만들기]─┘
지시문 ──────┘   policy_obs.py              policy_io.py
```

**원칙 — 관측과 명령은 학습 데이터를 만든 계산과 똑같아야 한다.** 그래서 학습 HDF5 를 만든 동료 코드(`docs/W9/d405/`)를 불러 쓰고 복사하지 않는다.
같은지는 녹화 에피소드로 잰다 — 로봇도 GPU 도 필요 없다 (2절).

## 1. 만든 것

| 파일 | 하는 일 | 왜 이렇게 |
| --- | --- | --- |
| `common/policy_io.py` | action → 목표 자세(`apply_action`), LIBERO 파지점 자세 → Mirobot `X Y Z A B C`(`libero_to_mirobot_pose`), action[6] → `M4 S40/S60` | 학습 변환(`common/servo.py`, `common/proprio.py`)의 역. 표준 라이브러리만 (`common/` 규약) |
| `tools/policy_obs.py` | D405 RGB → 256×256 손목 영상(`wrist_from_rgb`), `?` 위치·자세 + 집게 명령 기록 → proprio 9칸(`MirobotFrame.proprio`) | 동료 함수(`color_calibration.apply_rgb`, `prepare.gripper_track`)와 `common/proprio.py` 를 그대로 쓴다 |
| `tools/check_policy_io.py` | 위 둘을 녹화 에피소드로 검사 → `docs/W10/data/policy_io_check.json` | 실물에 붙이기 전에 계산이 학습 데이터와 같은지 |
| `tests/test_policy_io.py` | 역변환 단위 테스트 3개 | `servo_action` ↔ `apply_action`, Mirobot ↔ LIBERO 왕복 |
| `tools/eval_offline.py` | 체크포인트 합치기(CPU) + HDF5 관측으로 정책 실행 → 예측 action vs 라벨, 추론 시간 (GPU) | 실물 전에 정책이 라벨을 따라가는지, 한 번 묻는 데 몇 초인지. 4절 |

- **좌표 기준** — 실행 때도 녹화 때와 같은 기준 파일을 쓴다: `reference.jsonl`(Panda 시작 자세)과 `source.gcode` 머리말(짝·배율 0.663·공구). 세 색 seed 2 기준 파일은 이 값이 모두 같다(11/03 확인)
- **실행 환경** — `cosmos-policy/.venv` (정책과 같은 환경. cv2·h5py·robosuite·libero 있음)

## 2. 녹화로 확인한 것 (layoutblue1–10, 4,383칸, 11/03)

```bash
cosmos-policy/.venv/bin/python -m tools.check_policy_io     # 약 5분, GPU 안 씀. 새 녹화는 --episodes 영상11 … --hdf5-dir <dir>
python3 -m tests.test_policy_io
```

| 검사 | 결과 | 뜻 |
| --- | --- | --- |
| 영상 — 녹화 PNG → `wrist_from_rgb` vs HDF5 `eye_in_hand_rgb` | **4,383칸 모두 픽셀 차 0** | 실행 때 같은 함수로 프레임을 만들면 학습 영상과 같다 |
| 역변환 — LIBERO 자세 → Mirobot `X Y Z A B C` vs 녹화 `?` 값 | **0.0000 mm**, 각도 차 0 | 정책 출력을 Mirobot 명령으로 바꾸는 좌표 계산은 맞다 |
| 손가락 2칸 | 차 최대 4e-9 | B' 손가락(0.0140) 계산이 같다 |
| proprio — 그 시각 **직전 `?` 응답 하나**로 만든 위치 vs HDF5(앞뒤 응답 보간) | 평균 0.6 · p95 1.8 · 최대 3.9 mm. 응답 나이 평균 31 · 최대 103 ms | 실행 때는 보간할 "다음 응답" 이 없다. 응답이 16–17 Hz 라 이만큼 늦은 자세가 들어간다 |
| action → 목표 — 학습 action 을 **실물** 현재 자세에 더한 목표 vs 실제 다음 자세 | 평균 2.9 · p95 4.9 · 최대 8.2 mm (움직이는 칸만 평균 3.8 mm), 회전 최대 0.48° | 3절. 한 칸(0.05 s) 이동은 평균 1.0 · 최대 3.8 mm 라 그 3–4배다 |

## 3. 걸리는 점 — action 을 Mirobot 목표로 바꾸는 법 (결정 대기)

**학습 action 의 뜻.** Mirobot 녹화의 action 은 블록 없는 시뮬 Panda 가 실물 자세를 따라가며 받은 OSC_POSE 명령이다
(`docs/W9/d405/action_labels.py`). 칸 k 의 action 은 "**시뮬 Panda 의 현재 자세**에서 실물 다음 자세로 가라" 다.

```
action[k] × 스케일(0.05 m · 0.5 rad) = 실물[k+1] − 시뮬[k]
```

시뮬은 실물을 약 0.14 s 늦게 따라간다([../W9/FOLLOW.md](../W9/FOLLOW.md) 4-3). 그런데 **실행 때 실물에는 시뮬이 없다.**
실물 현재 자세에 action 을 더하면 `실물[k+1] + (실물[k] − 시뮬[k])` — 시뮬이 늦은 만큼 앞선 곳이 목표가 된다. 2절 "action → 목표" 의 2.9 mm 가 이 늦음과 정확히 같다(HDF5 `follow_error_mm_deg` 평균과 영상마다 일치).

**묶음으로 실행하면 쌓인다.** Cosmos LIBERO 평가는 action 16개를 다시 묻지 않고 차례로 실행한다(`num_open_loop_steps 16`).
묶음 첫 실물 자세에서 16개를 차례로 더해 가면 늦음이 16번 더해진다 — 16번째 목표의 어긋남이 **평균 44 · p95 72 · 최대 87 mm** 다
(layoutblue1–10 의 모든 칸에서 시작한 묶음, `chunk16_open_loop_mm`). 블록 한 변이 20 mm 라 이대로는 쓸 수 없다.

| 후보 | 방법 | 좋은 점 | 걸리는 점 |
| --- | --- | --- | --- |
| A. 칸마다 실물에 더하기 | 칸마다 새 `?` 응답을 받아 그 자세에 action 하나를 더한다 (시뮬 안에서 OSC 가 하는 것과 같은 모양) | 시뮬 없음, 간단 | 목표가 늘 시뮬 늦음(평균 3–4 mm)만큼 앞선다 → 시연보다 빨리 움직이려 한다. 칸마다(20 Hz) 응답·명령이 오가야 하는데 응답은 16–17 Hz |
| B. 시뮬 Panda 를 루프 안에서 같이 | 라벨을 만든 빈 탁상 Panda(`action_labels.create_translator`)에 예측 action 을 넣고, 그 시뮬의 목표 자세를 Mirobot 에 보낸다 | 라벨을 만든 계산을 그대로 거꾸로 — 녹화 데이터에서는 목표가 실물 다음 자세와 같다. 서버 환경에 robosuite·libero 가 있다 | 실행 때 MuJoCo 를 같이 돌린다. 시작 때 시뮬을 실물 자세로 맞춰야 한다(라벨 만들 때의 warmup 과 같은 방식) |
| C. 라벨을 다시 만들기 | action = 실물 자세 차이(`servo_action(실물[k], 실물[k+1])`)로 HDF5 를 다시 쓰고, 실행 때는 묶음 첫 자세에서 차례로 더한다 | 거꾸로 계산이 정확하다 — 16개를 쌓아도 어긋남 0 (`chunk16_open_loop_real_labels_mm`, 최대 6e-16 mm). 실행 때 시뮬 없음. 다시 쓰는 도구가 이미 있다(`export_real_hdf5.export_episode` 의 `action_generator` 인자) | 라벨이 약 4배 작아진다(위치 평균 0.010 vs 지금 0.042, LIBERO 통계 표준편차 0.34–0.44) — 공식 통계로 펴면 0 근처에 몰려 학습이 어려울 수 있다(확인 안 함) |

- **이 결정은 세 색 90개 학습 전에** 내려야 한다 — C 는 라벨이 바뀌어 학습 데이터부터 다르다
- 제안(임의 판단) — **C**. Mirobot 데이터만으로 학습하기로 했으니(11/02) 라벨을 시뮬 Panda 에 묶어 둘 이유가 약하고, 실행 계산이 가장 단순하고 정확하다.
  "현재 로봇 자세 기준 목표" 라는 뜻은 Panda 시뮬 라벨(로봇 = 시뮬)과도 같다. 라벨이 작은 문제는 학습 결과로 확인하고, 안 되면 B 로 간다
- 정하지 않은 것: 묶음 16개 중 몇 개를 실행하고 다시 물을지, Mirobot 에 목표를 보내는 간격(20 Hz 를 따라갈 수 있는지)

## 4. 다음

| 할 일 | 필요한 것 | 상태 |
| --- | --- | --- |
| 오프라인 평가 — 체크포인트 + HDF5 → 예측 action vs 라벨, 정책 한 번 추론 시간 | GPU (사용자가 tmux 에서), 1차 혼합 체크포인트 `w9_mix_p90m10_2000` | `tools/eval_offline.py` 작성, 체크포인트 합침(아래). **GPU 실행 대기** |
| 실행 루프 — 카메라·`?` → 관측 → 정책 → 명령. 처음엔 명령만 출력 | 3절 결정, 통신은 기존 브리지(`robot/camera_bridge.py`, `server/bridge_client.py`) | 3절 결정 뒤 |
| 실물 연결 시험 | 노트북(카메라·로봇) — 녹화가 끝난 뒤 | |

오프라인 평가를 위해 확인한 것 (11/03, 읽기만):

- **추론 함수** — `cosmos_utils.get_action` 은 손목만(`use_third_person_image=False`)을 지원하고, 설정은 10개 남짓만 읽는다(`suite`, `use_wrist_image`, `use_proprio`, `normalize_proprio`, `unnormalize_actions`, `chunk_size`, `trained_with_image_aug`, `use_jpeg_compression` 등)
- **영상 처리를 학습과 맞추기** — 학습 로더(`datasets/libero_dataset.py`)는 HDF5 영상을 뒤집거나 JPEG 로 압축하지 않고 무작위 자르기 증강만 한다.
  그래서 추론은 `flip_images False` · `use_jpeg_compression False` · `trained_with_image_aug True`(가운데 자르기). 공식 LIBERO 평가 명령(`flip_images True`, `use_jpeg_compression True`)을 그대로 쓰면 안 된다
- **모델 설정** — 학습 때 덮어쓴 값(`state_t=7`, 조건 프레임 3, `chunk_duration=25`)을 추론에도 줘야 한다. `load_model_from_checkpoint(..., experiment_opts=[...])` 로 줄 수 있다
- **체크포인트 형식** — 학습 체크포인트는 DCP(조각 파일, `iter_*/model`, 키 687개 모두 `net.*`, EMA 없음)인데, 추론 로더는 `load_from_local = True` 로 고정돼 DCP 읽는 쪽에 닿지 않는다(`model_loader.py:217`).
  CPU 에서 `torch.distributed.checkpoint.format_utils.dcp_to_torch_save` 로 한 파일(.pt)로 합쳐 넘긴다 (메모리·디스크 여유 있음). `strict=False` 로 읽으므로 **맞은 키 수를 꼭 확인한다** — 안 맞아도 오류 없이 빈 모델이 된다

`tools/eval_offline.py` (11/03):

- **합치기** — `--convert-only` 로 `iter_*/model_consolidated.pt` 를 만든다. `w9_mix_p90m10_2000/iter_000002000` 은 합쳐 뒀다 (3.91 GB, 6 s, 키 687개 bf16)
- **불러오기** — 모델은 `cosmos_predict2_2b_480p_libero__inference_only` + 손목 전용 덮어쓰기로 만들고(`skip_load_model`), 가중치는 직접 넣어 **안 맞는 키가 있으면 멈춘다**.
  CPU 만으로는 시험 못 했다 — 모델 코드가 import 때 flash-attn 을 확인하는데 CUDA 가 보여야 통과한다
- **입력** — HDF5 의 손목 영상·`robot_states`·지시문 T5(`data/hdf5_mix/t5_embeddings.pkl`), 통계는 학습과 같은 공식 LIBERO 통계. 기본은 16칸마다 한 번 묻는다
- **지표** — 칸마다 위치 차, 묶음 끝 차(16칸 합), 회전 차, 집게 부호 일치, 추론 시간. **기준선은 "모두 0"** — 정책이 이보다 나아야 의미가 있다
- **주의** — 기본 대상 Mirobot 10개는 1차 학습에 들어간 에피소드다. 일반화가 아니라 "학습 데이터를 따라가는가 · 경로가 도는가" 를 본다
