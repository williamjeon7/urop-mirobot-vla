# Cosmos LIBERO 형식 HDF5 — 형식, 만드는 법, 확인

> **설계** · 확인 2026-10-29 · 기준 `cosmos-policy@18a2acc`, W6 `docs/W6/rgb_blocks/pickup.py`
> 5번 파인튜닝에 넣을 에피소드를 Cosmos LIBERO 로더가 그대로 읽는 HDF5 로 만드는 방법. 목표 형식, 짝 맞추기, 파일 이름 규칙,
> 두 도구(`tools/pickup_to_hdf5.py`, `tools/check_cosmos_dataset.py`)의 배경과 동작, 시험판 결과, 정규화 통계 문제.

할 일과 상태는 [CHECKLIST.md](CHECKLIST.md) 4절, 시간 순서 기록은 [WORKLOG.md](WORKLOG.md).
Mirobot 에피소드의 외부 영상·action·proprio 를 만드는 방법은 [FOLLOW.md](FOLLOW.md).

실물 D405 수집 코드와 설치·실행 방법: [D405_GUIDE.md](D405_GUIDE.md).
Calibrite Classic Mini 색상표 보정과 기존 키보드 조작으로 수집: [COLORCHECKER_MINI.md](COLORCHECKER_MINI.md).

## 0. 한눈에

- **목표** — Panda 시뮬 90 + Mirobot 실물 10 에피소드를 로더가 읽는 HDF5 로 (10/28 action plan 4·5번)
- **된 것** — Panda 시뮬 쪽 도구가 있고, **90개(색마다 30)를 만들었다** (10/29, 6-2절). 1번 환경 수정 뒤 같은 명령으로 다시 만든다
- **남은 것** — no-op 거르기(Mirobot 데이터를 보고), 정규화 통계(7절, 5번과), Mirobot 쪽([FOLLOW.md](FOLLOW.md))

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

- **확정 (10/29, 사용자 결정)** — **소문자·마침표 없음**: `pick up the <색> block on the table`. 체크포인트의 LIBERO 지시문 40개가 모두 이 모양이다(`libero_t5_embeddings.pkl` 열쇠).
  W6 `tasks.py`·BDDL 은 고치지 않는다 — HDF5 는 지시문을 파일 이름에서만 가져온다. 대신 **정책을 실행하는 스크립트는 BDDL·`tasks.py` 의 문장이 아니라 이 문장을 넘긴다**
- **T5** — 우리 지시문은 기존 `libero_t5_embeddings.pkl` 에 없다. 새로 만들려면 `google-t5/t5-11b` 인코더가 필요하다 (`get_t5_emb.py:25`). **크기가 커서 받기 전에 확인한다**

## 4. `tools/pickup_to_hdf5.py` — Panda 시뮬 pick up → HDF5

- **배경** — W6 pick up 은 화면 표시와 손 좌표 JSONL(`--log`)만 남겼고, Cosmos 가 학습할 때 읽는 형식으로 저장하는 기능이 없었다
- **이미 있는 것을 안 쓰고 다시 돌리는 이유** — 있는 것 중 학습용으로 그대로 쓸 수 있는 것이 없다 (10/29 확인)

  | 이미 있는 것 | 못 쓰는 이유 |
  | --- | --- |
  | W6 손 좌표 기록 (`docs/W6/poses/*.jsonl` 18개, `data/pickup/`) | 숫자만 있고 **영상이 없다** |
  | W6 시뮬 영상 (`docs/W6/images/` mp4·gif 19개) | **외부 카메라뿐**(손목 없음 — 로더가 KeyError), 화면 위에 **글자 세 줄**, 크기·간격이 다르다 (mp4 512×512 185프레임 — 145 스텝과 1:1 아님, gif 384×384 6.7 fps), 압축으로 색이 변한다, seed 0–2 의 9개뿐 |

  시뮬은 seed 가 같으면 같은 배치·같은 움직임이 나온다(W6 재현 확인). 그래서 "다시 돌린다" 는 **같은 pick up 을 학습 형식(256×256, 두 카메라, 글자 없음, 스텝과 1:1)으로 다시 찍는 것**이고,
  에피소드 하나에 서버 계산 약 2초라 1번 환경 수정 뒤에도 명령 한 줄로 다시 만든다
- **동작** — 색 × seed 마다 W6 장면을 새로 만들고 `run_pickup` 을 돌린다. step 마다 두 카메라(256×256, `np.flipud`), `robot_states`, 로더가 안 읽는 상태값을
  모으고(`on_step`), action 은 `record` 에서 꺼낸다. **대상 블록을 집어 든** 에피소드만(`target_picked`) 색별 파일 하나에 `demo_0`, `demo_1`, … 로 쓴다.
  `--count N` 이면 색마다 성공이 N 개가 될 때까지 seed 0, 1, 2, … 를 이어 간다 (실패는 건너뜀)
- **실행** — `cosmos-policy/.venv` 에서 (10/29 실행 환경 통일. conda `libero` 에서도 돈다)

  ```bash
  cosmos-policy/.venv/bin/python -m tools.pickup_to_hdf5 --count 30                              # 본 생성 — 색마다 성공 30개
  cosmos-policy/.venv/bin/python -m tools.pickup_to_hdf5 --colors red green blue --seeds 0-1      # 시험판
  ```

  기본 출력은 `data/hdf5/panda_sim` — 폴더 이름(`panda_sim`)이 로더의 묶음 이름이 된다. 데이터는 `data/`(git 제외)
- **선택지와 결정**

  | 항목 | 정한 것 | 누가 · 언제 | 이유 |
  | --- | --- | --- | --- |
  | 지시문 문장 | 소문자·마침표 없음 | 10/29 사용자 결정 (처음엔 임의 판단) | 3절 |
  | 파일 이름·폴더 | `PANDA_SIM_SCENE1_…`, `data/hdf5/panda_sim` | 임의 판단 10/29 | 폴더 이름이 묶음 이름이 된다 |
  | 로더가 안 읽는 키 | `obs/joint_states`·`gripper_states`·`ee_states`(위치 + axis-angle), `phases` 를 남긴다 | 임의 판단 10/29 | 상위집합 기록 원칙 ([계획 6절](../plan/UROP_프로젝트_계획.md#로깅-스키마-상위집합-기록-원칙)) |
  | 영상 저장 | 원본 uint8 (JPEG 아님) | action plan 4번 | 로더는 둘 다 읽는다. 원본은 에피소드 하나에 약 57 MB |
  | no-op | 지금은 거르지 않고 세기만. **Mirobot 데이터를 만든 뒤 비율을 보고 정한다** | 10/29 사용자 결정 | Panda 90개는 0개라 결과가 같다. Mirobot 은 기다리는 구간에서 생길 수 있다. LIBERO 재생성은 걸렀다 (`regenerate_libero_dataset.py:89, 209`) |
  | 성공한 것만 | **대상 블록을 집어 들었는가만** 본다 (`target_picked`) | 성공만 남기는 것은 LIBERO 재생성과 같음. 판정 범위는 **10/29 사용자 결정** | 아래 "성공 판정" |
  | 색마다 개수·seed | 30개, seed 0–29 를 세 색이 같이 쓴다 | 10/29 사용자 결정 (처음엔 임의 판단) | 같은 seed = 같은 블록 배치 — 한 배치를 지시문만 바꿔 세 번 쓴다 (6-2절). 언어 준수율을 직접 가르치는 짝이다 (LIBERO-Goal 과 같은 생각). 다양성이 모자라면 일부 seed 를 색마다 따로 쓴다 |
  | 실행 환경 | **`.venv`** — 따라가기·로더·학습과 같은 환경. 처음엔 conda `libero`(W6 pick up 환경)로 만들었다 | 10/29 사용자 결정 | 두 환경의 렌더링이 미세하게 다르다 ([FOLLOW.md](FOLLOW.md) 5-3). 지금 90개는 conda `libero` 로 만든 것 — 1번 환경 수정 뒤 `.venv` 로 다시 만든다. 도구는 Python 3.8 에서도 돌게 `common/` 을 쓰지 않는다 |

**성공 판정 (10/29 사용자 결정)** — 성공은 "원하는 블록을 집어 들었는가" 만 본다: 처음엔 안 든 상태에서(`Up` 아님) 손가락이 잡고,
확인 구간(30 스텝) 내내 `Up` 이고 계속 잡고 있다. W6 `pickup_success` 에 있던 **"다른 블록이 1 cm 넘게 밀리면 실패" 는 뺐다.**

- 그 조건은 10/7 블록을 일부러 붙이는 시험을 만들 때 BDDL 영역 검사(`On`)를 대신하려고 넣었고, 1 cm 라는 값의 근거는 기록돼 있지 않다
- 계획서 채점표도 "성공" 과 "간섭(다른 블록을 건드렸는가)" 을 **따로 기록하는 항목**으로 둔다 (`plan/운영기준.md`). 간섭은 성공 조건에 섞지 않고
  에피소드마다 `others_max_move_m`(다른 블록이 움직인 최대 거리)와 `other_blocks_in_place`(옛 판정)로 **기록만** 남긴다
- 10/8 잡는 높이를 바꾼 뒤로 이 조건 때문에 빠진 에피소드는 없었다. 90개에서도 최대 4.3 mm 라 결과는 같다
- W6 `pickup.py` 의 `pickup_success`(W6 뷰어·문서가 쓴다)는 **그대로 둔다** (10/29 사용자 결정) — W6 의 기록(59/60, 60/60)·문서와 코드가 어긋나지 않게

## 5. `tools/check_cosmos_dataset.py` — Cosmos 로더로 읽어 보기

- **배경** — 1절 표대로 썼어도 실제 학습 코드가 읽는지는 로더로 읽어 봐야 안다. 파일 이름 규칙이나 정규화처럼 표에 드러나지 않는 것이 있다
- **동작** — 학습 설정(`cosmos_policy_experiment_configs.py:41-61` — chunk 16, 이미지 증강, 손목 영상, proprio)과 같은 인자로 `LIBERODataset` 을 만들고,
  에피소드·step 수, 묶음별 step, 지시문, 정규화 통계, 샘플 한 칸의 모양을 찍는다
- **실행** — `cosmos-policy/.venv/bin/python -m tools.check_cosmos_dataset --data-dir data/hdf5`. 데이터를 바꾼 뒤에는 `--recompute-stats`
- **T5 는 가짜다** — 지시문마다 0 으로 채운 (1, 512, 1024) bfloat16 (진짜와 같은 모양)을 임시 파일로 만들어 샘플 모양만 본다. **학습에는 못 쓴다** (임의 판단 10/29)
- **부작용** — 로더가 `<data-dir>/dataset_statistics.json` 과 `dataset_statistics_post_norm.json` 을 만든다. 있으면 다시 계산하지 않고 읽는다

## 6. 결과 (10/29)

### 6-1. 시험판 — 3색 × seed 0–1

4절의 시험판 명령. 본 생성(6-2)이 같은 파일 이름으로 덮어써서 지금은 남아 있지 않다.

| | red s0 | red s1 | green s0 | green s1 | blue s0 | blue s1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 칸 수 | 145 | 149 | 144 | 144 | 151 | 147 |
| 성공 | ○ | ○ | ○ | ○ | ○ | ○ |

- **크기·시간** — 에피소드 하나가 **로봇 시간 약 7.3초**(145칸 × 0.05초) 분량이고, 서버가 그것을 계산·렌더링해 쓰는 데 **약 2초**가 걸린다
  (실시간을 기다리지 않는다. 첫 에피소드는 로딩 때문에 5.1초). 파일은 에피소드 하나에 약 57 MB (색마다 2개씩 113–117 MB). LIBERO 규칙의 no-op 0개
- **영상** — 위아래 바로 서 있고, 단계가 settle → lower → lift → verify 순서다
- **쿼터니언** — norm 1, 시작 자세 `xyzw` ≈ (1.000, 0.000, −0.028, 0.000) — 아래를 향한 top-down. x 성분이 에피소드 내내 +1 근처로 이어진다
- **짝** — action t 와 손 이동(t → t+1)의 상관 x 0.947 · y 0.945 · z 0.984. 한 칸 밀면 0.877 · 0.769 · 0.944 로 떨어진다 → 지금 짝이 맞다
- **로더** — 에피소드 6, step 880, 묶음 `panda_sim` 100%. 지시문 3개가 파일 이름에서 정확히 나왔다.
  샘플 한 칸: video (3, 33, 224, 224) uint8, actions (16, 7), proprio (9,), future_proprio (9,) — 모양 정상

### 6-2. 본 생성 — 색마다 30개 (90개)

`python -m tools.pickup_to_hdf5 --count 30` (conda `libero`, 3분 31초).

- **90/90 성공**, 실패한 seed 없음 → 세 색 모두 seed 0–29. 에피소드 길이 143–153칸(평균 146, 로봇 시간 약 7.3초), 전체 13,140칸
- **크기** — 색마다 약 1.72 GB, 모두 4.9 GB (`data/hdf5/panda_sim/`, git 제외)
- **같은 seed 의 세 색은 첫 화면이 같다** — 30 seed 모두 외부 영상 첫 프레임이 픽셀까지 같다. 한 블록 배치를 지시문만 바꿔 세 번 쓴 셈이라,
  "같은 장면에서 지시문에 따라 다른 블록으로 간다" 를 배우는 짝이 된다
- **다른 블록이 움직인 거리** — 최대 4.3 mm. 옛 1 cm 조건을 넘은 에피소드 0개
- **로더** — `check_cosmos_dataset --recompute-stats`: 에피소드 90, step 13,140, 지시문 3개, 샘플 모양은 시험판과 같다

### 6-3. 눈으로 확인 — HDF5 에서 mp4 로 꺼내기

`tools/hdf5_to_mp4.py` — 학습에 들어가는 바로 그 프레임을 사람이 보려고 만들었다(`pickup_to_hdf5` 는 영상 파일을 따로 만들지 않는다).
왼쪽 외부·오른쪽 손목을 2배로 늘려 나란히, 20 fps(로봇 시간 그대로). 프레임 위에는 아무것도 그리지 않고, 칸 번호·단계·action·robot_states 는 아래 띠에 적는다.

```bash
python -m tools.hdf5_to_mp4 data/hdf5/panda_sim/*.hdf5 --random 2 --out docs/W9/hdf5_check   # 난수 seed 20261029
```

색마다 무작위 2개 → 서버 `docs/W9/hdf5_check/` 에 6개 (각 1.3–1.4 MB, 7.15–7.5초, **git 제외** — 위 명령으로 다시 만든다): red seed 14·17, green seed 7·20, blue seed 11·14.
**red 14 와 blue 14 는 같은 배치에서 지시문만 다른 짝**이다 — 같은 76번째 칸에서 각각 빨강·파랑 블록을 잡고 있다(손가락 0.0194).

## 7. 정규화 통계 문제

로더는 데이터에서 min·max 를 계산해 `2(x − min)/(max − min) − 1` 로 [−1, 1] 에 편다 (`dataset_utils.py:201-209`).
우리 데이터는 범위가 좁아서, 같은 값이 LIBERO 체크포인트 때보다 훨씬 크게 펴진다. 시험판(6개)에서 처음 보았고(약 36–39배), 90개로 다시 쟀다.

| | 우리 90개 | LIBERO 체크포인트 통계 | 배율 |
| --- | --- | --- | ---: |
| 회전 action x | −0.010 ~ 0.011 | −0.258 ~ 0.356 | 약 29배 |
| 회전 action y | −0.114 ~ 0.044 | −0.375 ~ 0.375 | 약 5배 |
| 회전 action z | −0.012 ~ 0.011 | −0.364 ~ 0.375 | 약 32배 |
| proprio 쿼터니언 x | 1.000 근처 (소수 셋째 자리까지 같음) | 0.29 ~ 1.0 | — 거의 변하지 않아 작은 흔들림이 [−1, 1] 로 부풀려짐 |

우리 값은 모두 LIBERO 통계 범위 안이다.

| 선택지 | 방법 | 좋은 점 | 걸리는 점 |
| --- | --- | --- | --- |
| A. 우리 데이터로 계산 | 그대로 둔다 (로더 기본) | 우리 값이 [−1, 1] 을 넓게 쓴다 | 체크포인트가 배운 "숫자의 뜻"이 바뀐다. 거의 안 변하는 칸은 흔들림이 부풀려진다 |
| B. LIBERO 통계 그대로 | `libero_dataset_statistics.json` 을 `data_dir` 에 `dataset_statistics.json` 으로 둔다 — 로더가 계산하지 않고 읽는다 | 체크포인트와 같은 뜻으로 이어서 배운다 | 우리 값은 [−1, 1] 의 좁은 부분만 쓴다 |

**아직 정하지 않았다** — 학습 설정이라 5번과 정한다 (CHECKLIST 5절 미팅 질문).
