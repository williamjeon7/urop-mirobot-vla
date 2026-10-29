# Cosmos LIBERO 형식 HDF5 — 형식, 만드는 법, 확인

> **설계** · 확인 2026-10-29 · 기준 `cosmos-policy@18a2acc`, W6 `docs/W6/rgb_blocks/pickup.py`
> 5번 파인튜닝에 넣을 에피소드를 Cosmos LIBERO 로더가 그대로 읽는 HDF5 로 만드는 방법. 목표 형식, 짝 맞추기, 파일 이름 규칙,
> 두 도구(`tools/pickup_to_hdf5.py`, `tools/check_cosmos_dataset.py`)의 배경과 동작, 시험판 결과, 정규화 통계 문제.

할 일과 상태는 [CHECKLIST.md](CHECKLIST.md) 4절, 시간 순서 기록은 [WORKLOG.md](WORKLOG.md).
Mirobot 에피소드의 외부 영상·action·proprio 를 만드는 방법은 [FOLLOW.md](FOLLOW.md).

## 0. 한눈에

- **목표** — Panda 시뮬 90 + Mirobot 실물 10 에피소드를 로더가 읽는 HDF5 로 (10/28 action plan 4·5번)
- **된 것** — Panda 시뮬 쪽 도구가 있고, 시험판 6개가 Cosmos 로더로 끝까지 읽힌다 (10/29)
- **남은 것** — 지시문 확정(3절), Panda 90개 배분, no-op 거르기, 정규화 통계(7절, 5번과), Mirobot 쪽([FOLLOW.md](FOLLOW.md))

## 1. 목표 형식 — Cosmos LIBERO 로더가 읽는 것

`cosmos_policy/datasets/libero_dataset.py` 기준. 줄 번호는 `cosmos-policy@18a2acc`.

| 무엇 | 형태 | 비고 | 근거 |
| --- | --- | --- | --- |
| `data/demo_<i>/obs/agentview_rgb` | (T, 256, 256, 3) uint8 | 또는 `agentview_rgb_jpeg`. **위아래가 바로 선 영상** (시뮬은 `np.flipud`) | `libero_dataset.py:182-187`, `regenerate_libero_dataset.py:74, 242` |
| `data/demo_<i>/obs/eye_in_hand_rgb` | (T, 256, 256, 3) uint8 | 또는 `eye_in_hand_rgb_jpeg`. **없으면 KeyError** | `libero_dataset.py:189-194` |
| `data/demo_<i>/actions` | (T, 7) → float32 | Panda OSC_POSE 식 (action 번역) | `:196` |
| `data/demo_<i>/robot_states` | (T, 9) → float32 | 손가락 qpos 2 + 손 위치 3 (m, LIBERO world) + 쿼터니언 4 **`xyzw`** | `:200`, `regenerate_libero_dataset.py:222` |
| 지시문 | **파일 이름** | `<아무거나>_SCENE<n>_<단어_단어…>_demo.hdf5` → `SCENE` 뒤 단어를 공백으로 이은 문장 (3절) | `:203-212` |
| 묶음(suite) | `data_dir` 바로 아래 폴더 이름 | 뽑을 때는 폴더와 무관하게 **step 단위로 고르게** 뽑는다 | `:226`, `:519` |

- **한 칸의 짝** — `obs(t)` 는 action(t) 를 넣기 **전** 관측이다 (2절)
- **로더 밖에서 필요한 것** — `data_dir/dataset_statistics.json` (처음 한 번 계산해 저장, `dataset_common.py:262`, 7절), `t5_embeddings.pkl` (지시문 → T5 임베딩, 3절)
- `obs` 의 다른 키(`ee_states`, `joint_states`, `gripper_states`)와 `states`·`rewards`·`dones` 는 로더가 읽지 않는다
- **90/10 은 step 수 비율이다** — 로더가 step 단위로 고르게 뽑으므로, 실물 에피소드가 길면(Mirobot 이 느리면) 실물 비중이 커진다

## 2. 짝 맞추기 — 관측은 action 을 넣기 전

- **규칙** — 칸 t 의 영상·`robot_states` 는 action t 를 넣기 **전** 상태다. LIBERO 재생성 코드가 관측을 기록한 뒤 `env.step(action)` 한다
  (`regenerate_libero_dataset.py:213-260`). 실행할 때도 지금 관측을 보고 다음 action 을 낸다
- **왜 중요한가** — 한 칸 밀리면 모델은 "이미 일어난 움직임"을 action 으로 배운다. 형식 검사로는 안 잡히고 학습 결과에서만 드러난다
- **`pickup_to_hdf5` 에서** — W6 `run_pickup` 의 `on_step` 은 action **뒤** 관측을 준다. 그래서 reset 관측부터 한 칸씩 밀어 짝짓고, 마지막 관측은 짝이 없어 버린다
- **확인 방법** — action t 와 손 이동(칸 t → t+1)의 상관을 본다. 짝이 맞으면 한 칸 민 것보다 높다 (결과 6절)

## 3. 파일 이름 = 지시문

- **규칙** — 로더는 파일 이름에서 지시문을 만든다. 끝의 `_demo.hdf5` 를 떼고 `_` 로 나눈 뒤, `SCENE` 이 든 단어 뒤의 단어를 공백으로 잇는다 (`libero_dataset.py:203-212`).
  예: `PANDA_SIM_SCENE1_pick_up_the_red_block_on_the_table_demo.hdf5` → "pick up the red block on the table". `SCENE` 앞부분(`PANDA_SIM`)은 버려진다
- **실행할 때 넣는 문장과 글자 하나까지 같아야 한다** — T5 임베딩을 문장 문자열로 찾는다. 다르면 못 찾거나 다른 임베딩이 들어간다
- **지금 문장이 셋이다**

  | 어디 | 문장 |
  | --- | --- |
  | W6 `tasks.py` (실행 쪽) | "Pick up the red block on the table." — 대문자·마침표 |
  | W6 BDDL `:language` | "Pick up the red block on the table" — 대문자 |
  | 시험판 파일 이름 (10/29) | "pick up the red block on the table" — 소문자·마침표 없음 |

- **잠정 (10/29, 임의 판단 — 확정 전)** — 소문자·마침표 없음. 체크포인트의 LIBERO 지시문 40개가 모두 이 모양이다(`libero_t5_embeddings.pkl` 열쇠).
  확정하면 실행 쪽(`tasks.py`·BDDL)을 같은 문장으로 맞춘다
- **T5** — 우리 지시문은 기존 `libero_t5_embeddings.pkl` 에 없다. 새로 만들려면 `google-t5/t5-11b` 인코더가 필요하다 (`get_t5_emb.py:25`). **크기가 커서 받기 전에 확인한다**

## 4. `tools/pickup_to_hdf5.py` — Panda 시뮬 pick up → HDF5

- **배경** — W6 pick up 은 화면 표시와 손 좌표 JSONL(`--log`)만 남겼고, Cosmos 가 학습할 때 읽는 형식으로 저장하는 기능이 없었다
- **동작** — 색 × seed 마다 W6 장면을 새로 만들고 `run_pickup` 을 돌린다. step 마다 두 카메라(256×256, `np.flipud`), `robot_states`, 로더가 안 읽는 상태값을
  모으고(`on_step`), action 은 `record` 에서 꺼낸다. `pickup_success` 인 에피소드만 색별 파일 하나에 `demo_0`, `demo_1`, … 로 쓴다
- **실행** — conda `libero` 에서

  ```bash
  conda activate libero
  python -m tools.pickup_to_hdf5 --colors red green blue --seeds 0-1 --out data/hdf5/panda_sim
  ```

  `--seeds` 는 `0-29` 나 `0,3,5`. 출력 폴더 이름(`panda_sim`)이 로더의 묶음 이름이 된다. 데이터는 `data/`(git 제외)
- **선택지와 결정**

  | 항목 | 정한 것 | 누가 · 언제 | 이유 |
  | --- | --- | --- | --- |
  | 지시문 문장 | 소문자·마침표 없음 | 임의 판단 10/29, **확정 전** | 3절 |
  | 파일 이름·폴더 | `PANDA_SIM_SCENE1_…`, `data/hdf5/panda_sim` | 임의 판단 10/29 | 폴더 이름이 묶음 이름이 된다 |
  | 로더가 안 읽는 키 | `obs/joint_states`·`gripper_states`·`ee_states`(위치 + axis-angle), `phases` 를 남긴다 | 임의 판단 10/29 | 상위집합 기록 원칙 ([계획 6절](../plan/UROP_프로젝트_계획.md#로깅-스키마-상위집합-기록-원칙)) |
  | 영상 저장 | 원본 uint8 (JPEG 아님) | action plan 4번 | 로더는 둘 다 읽는다. 원본은 에피소드 하나에 약 57 MB |
  | no-op | 거르지 않고 세기만 | 임의 판단 10/29 | 거를지는 미정 (CHECKLIST 4-3). LIBERO 재생성은 걸렀다 (`regenerate_libero_dataset.py:89, 209`) |
  | 성공한 것만 | `pickup_success` | LIBERO 재생성과 같음 | 성공 시연만 학습한다 (Mirobot 도 같음, 10/28) |
  | 실행 환경 | conda `libero` (Python 3.8, W6 pick up 과 같은 환경). 그래서 `common/` 을 쓰지 않는다 | 임의 판단 10/29 | [FOLLOW.md](FOLLOW.md) 5절의 환경 통일 결정에 따라 바뀔 수 있다 |

## 5. `tools/check_cosmos_dataset.py` — Cosmos 로더로 읽어 보기

- **배경** — 1절 표대로 썼어도 실제 학습 코드가 읽는지는 로더로 읽어 봐야 안다. 파일 이름 규칙이나 정규화처럼 표에 드러나지 않는 것이 있다
- **동작** — 학습 설정(`cosmos_policy_experiment_configs.py:41-61` — chunk 16, 이미지 증강, 손목 영상, proprio)과 같은 인자로 `LIBERODataset` 을 만들고,
  에피소드·step 수, 묶음별 step, 지시문, 정규화 통계, 샘플 한 칸의 모양을 찍는다
- **실행** — `cosmos-policy/.venv/bin/python -m tools.check_cosmos_dataset --data-dir data/hdf5`. 데이터를 바꾼 뒤에는 `--recompute-stats`
- **T5 는 가짜다** — 지시문마다 0 으로 채운 (1, 512, 1024) bfloat16 (진짜와 같은 모양)을 임시 파일로 만들어 샘플 모양만 본다. **학습에는 못 쓴다** (임의 판단 10/29)
- **부작용** — 로더가 `<data-dir>/dataset_statistics.json` 과 `dataset_statistics_post_norm.json` 을 만든다. 있으면 다시 계산하지 않고 읽는다

## 6. 시험판 결과 (10/29)

3색 × seed 0–1, 4절의 명령 그대로.

| | red s0 | red s1 | green s0 | green s1 | blue s0 | blue s1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 칸 수 | 145 | 149 | 144 | 144 | 151 | 147 |
| 성공 | ○ | ○ | ○ | ○ | ○ | ○ |

- **크기·시간** — 에피소드 하나에 약 2초, 약 57 MB (색마다 2개씩 113–117 MB). LIBERO 규칙의 no-op 0개
- **영상** — 위아래 바로 서 있고, 단계가 settle → lower → lift → verify 순서다
- **쿼터니언** — norm 1, 시작 자세 `xyzw` ≈ (1.000, 0.000, −0.028, 0.000) — 아래를 향한 top-down. x 성분이 에피소드 내내 +1 근처로 이어진다
- **짝** — action t 와 손 이동(t → t+1)의 상관 x 0.947 · y 0.945 · z 0.984. 한 칸 밀면 0.877 · 0.769 · 0.944 로 떨어진다 → 지금 짝이 맞다
- **로더** — 에피소드 6, step 880, 묶음 `panda_sim` 100%. 지시문 3개가 파일 이름에서 정확히 나왔다.
  샘플 한 칸: video (3, 33, 224, 224) uint8, actions (16, 7), proprio (9,), future_proprio (9,) — 모양 정상

## 7. 정규화 통계 문제

로더는 데이터에서 min·max 를 계산해 `2(x − min)/(max − min) − 1` 로 [−1, 1] 에 편다 (`dataset_utils.py:201-209`).
우리 데이터는 범위가 좁아서, 같은 값이 LIBERO 체크포인트 때보다 훨씬 크게 펴진다.

| | 우리 시험판 | LIBERO 체크포인트 통계 | 배율 |
| --- | --- | --- | ---: |
| 회전 action x | −0.008 ~ 0.009 | −0.258 ~ 0.356 | 약 36배 |
| 회전 action y | −0.114 ~ 0.043 | −0.375 ~ 0.375 | 약 5배 |
| 회전 action z | −0.011 ~ 0.008 | −0.364 ~ 0.375 | 약 39배 |
| proprio 쿼터니언 x | 0.9996 ~ 1.000 | 0.29 ~ 1.0 | — 거의 변하지 않아 작은 흔들림이 [−1, 1] 로 부풀려짐 |

우리 값은 모두 LIBERO 통계 범위 안이다.

| 선택지 | 방법 | 좋은 점 | 걸리는 점 |
| --- | --- | --- | --- |
| A. 우리 데이터로 계산 | 그대로 둔다 (로더 기본) | 우리 값이 [−1, 1] 을 넓게 쓴다 | 체크포인트가 배운 "숫자의 뜻"이 바뀐다. 거의 안 변하는 칸은 흔들림이 부풀려진다 |
| B. LIBERO 통계 그대로 | `libero_dataset_statistics.json` 을 `data_dir` 에 `dataset_statistics.json` 으로 둔다 — 로더가 계산하지 않고 읽는다 | 체크포인트와 같은 뜻으로 이어서 배운다 | 우리 값은 [−1, 1] 의 좁은 부분만 쓴다 |

**아직 정하지 않았다** — 학습 설정이라 5번과 정한다 (CHECKLIST 5절 미팅 질문).
