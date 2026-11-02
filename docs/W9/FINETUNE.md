# 1차 파인튜닝 — Panda 90 + Mirobot 10

> **기록** · 확인 2026-11-02 · 기준 `cosmos-policy@18a2acc`, 동료 진입점 `docs/W9/d405/train.py` · `tools/train_cosmos_libero.py`, 서버 RTX 4090 24 GB × 4
> Panda 시뮬 90 + Mirobot 실물 10 을 합쳐 LIBERO 체크포인트에서 처음으로 끝까지 학습한다. 합친 데이터, 실행 방법, GPU 시간 측정과 설정 결정, 본학습 상태, 평가 경로.

할 일과 상태는 [CHECKLIST.md](CHECKLIST.md) 4절, 시간 순서 기록은 [WORKLOG.md](WORKLOG.md) 11/02 20–22.
HDF5 형식은 [DATASET_HDF5.md](DATASET_HDF5.md), 걸리는 점은 [ISSUES.md](ISSUES.md).

## 0. 한눈에

- **왜** — 11/02 사용자 방향: 결과와 상관없이 합쳐서 1차 파인튜닝까지 먼저 하고, 결과가 너무 나쁘면 그때 pick up 정교화나 Mirobot 이미지 재가공 ([ISSUES.md](ISSUES.md) 0절)
- **데이터** — `data/hdf5_mix/`: 에피소드 100, step 17,524 (Panda 75% : Mirobot 25%), 손목만, 공식 LIBERO 통계, T5 세 문장 (2절)
- **설정** — **GPU 2개 · 2000 step** (11/02 사용자). GPU 4개가 오히려 느렸다 — 초당 2.0 vs 2.7 샘플 (4·5절)
- **상태** — 11/02 10:47 시작, 진행 중 (step 당 약 5.9 s). 1000 step 체크포인트 12:30 전후, 2000 step 14:10 전후 예상. **성능 결과는 아직** (6절)
- **평가** — 정책을 돌려 볼 도구가 아직 없다. W10 에서 만든다 (7절)

## 1. 배경

- 동료의 Mirobot 학습은 **GPU 4개로 가중치 1회 갱신 점검**(smoke)이었다 — 경로가 돈다는 확인이지 학습된 모델은 아니다
  ([MIROBOT_DATA_COLLECTION.md](MIROBOT_DATA_COLLECTION.md) 1·9절). `outputs/cosmos_policy/w9_mirobot/` 에도 `iter_000000001` 체크포인트 3개뿐이다
- 그래서 이번이 **처음으로 끝까지 하는 학습**이다. 실물 빨강·초록 녹화(2번 요청)는 시간이 걸려, 그동안 지금 데이터(Panda 세 색 90 + Mirobot 파랑 10)로 돌린다

## 2. 합친 데이터 `data/hdf5_mix/`

| 경로 | 내용 |
| --- | --- |
| `panda_sim/` (3 파일, 각 약 120 KB) | 원본 `data/hdf5/panda_sim/`(90개, 4.9 GB)을 **외부 링크로 가리키는 얇은 HDF5** — 데모마다 `observation_mode=wrist_only`, `wrapped_from` 속성. `tools/wrap_hdf5.py` |
| `mirobot_real/` (10 파일, 675 MB) | 동료 HDF5 의 손가락만 0.0140 으로 고친 사본 (11/01, `tools/rewrite_fingers.py`, [FOLLOW.md](FOLLOW.md) 3-4절) |
| `dataset_statistics.json` | 공식 LIBERO 통계 — HF 캐시 `libero_dataset_statistics.json` 과 같고, 동료 `docs/W9/data/hdf5/dataset_statistics.json` 과도 같다 ([DATASET_HDF5.md](DATASET_HDF5.md) 7절) |
| `t5_embeddings.pkl` (3.1 MB) | 지시문 3개 `pick up the {red, green, blue} block on the table` |
| `loader_validation.json`, `training_config_validation.json`, `dataset_statistics_post_norm.json`, `*.log` | 검사 결과와 실행 기록 |

### 2-1. 심볼릭 링크 대신 얇은 HDF5 (임의 판단)

처음엔 심볼릭 링크로 합쳤다. 동료 `docs/W9/d405/train.py` 의 `observation_mode` 가 Panda 데모에 그 속성이 없어 `two_view` 로 읽고
"Do not mix wrist-only and two-view episodes" 로 멈췄다 (`tools/check_cosmos_dataset.py` 도 같은 함수를 쓴다).
원본은 고치지도 복사하지도 않기로 해서, 데이터는 원본을 가리키고 속성만 더한 파일을 만들었다. **원본을 옮기거나 지우면 이 파일들은 읽히지 않는다.**

### 2-2. T5 임베딩

동료 `docs/W9/d405/make_t5.py` 로 만들었다 — GPU 0 하나, float32(동료와 같은 방식), 567 s. 파랑 임베딩은 동료 것과 비트 단위로 같다.
모델은 동료가 받아 둔 HF 캐시(T5-11B 약 43 GB)를 오프라인으로 읽었다 — 캐시 크기·파일 변화 없음.

### 2-3. 검사 결과

| 검사 | 결과 |
| --- | --- |
| 로더 (`tools/check_cosmos_dataset.py`, 실제 T5, 공식 통계) | passed, `training_ready` True. 에피소드 100, step 17,524, 지시문 3개. 샘플 201개 · 배치 video (2, 3, 25, 224, 224), actions (2, 16, 7) 모두 유한 |
| 묶음별 step | `panda_sim` 13,141 (**75%**) : `mirobot_real` 4,383 (**25%**) — 로더가 묶음 구분 없이 step 단위로 고르게 뽑아 (`libero_dataset.py:519` `idx % num_steps`) 90/10 이 아니라 75:25 다. **1차는 그대로 둔다** (임의 판단, 조정 안 함) |
| 정규화 | 공식 통계로 편 값이 모두 [−1, 1] 안. 쿼터니언 x 만 통계 최댓값 1.0 에 붙어 반올림 수준으로 넘는 칸이 있다 |
| 학습 설정 (`train.py --dryrun`, GPU 안 씀) | passed — `wrist_only`, `state_t` 7, 조건 프레임 3, 25 프레임, 외부 영상 입력 없음. 이때는 GPU 4개 · 1000 step 으로 풀어 봤고, 실제 본학습 값은 6절 `config.yaml` 로 확인 |

### 2-4. 다시 만들기

```bash
cosmos-policy/.venv/bin/python -m tools.wrap_hdf5 data/hdf5/panda_sim/*.hdf5 \
  --out data/hdf5_mix/panda_sim --attr observation_mode=wrist_only
# GPU 를 쓴다 — 사용자가 tmux 에서 (3절)
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUDA_VISIBLE_DEVICES=0 \
  cosmos-policy/.venv/bin/python -m docs.W9.d405.make_t5 data/hdf5_mix --model google-t5/t5-11b
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 cosmos-policy/.venv/bin/python -m tools.check_cosmos_dataset \
  --data-dir data/hdf5_mix --statistics <HF 캐시>/libero_dataset_statistics.json \
  --t5 data/hdf5_mix/t5_embeddings.pkl --report data/hdf5_mix/loader_validation.json
```

- `mirobot_real/` 은 `tools/rewrite_fingers.py` 로 만든다 ([FOLLOW.md](FOLLOW.md) 3-4절)
- **git** — `data/hdf5_mix/` 의 json·pkl·log(약 3.2 MB)가 git 에 잡힌다 (`*.hdf5` 는 빠짐). 10/29 부터 `data/` 가 추적되는 문제 때문이다. 커밋하지 않았다 — 미정 ([CHECKLIST.md](CHECKLIST.md) 4-3 저장 위치)

## 3. 실행 — 사용자가 tmux 에서 직접

GPU 작업(학습·시간 측정·T5)은 **사용자가 tmux 에서 직접 실행**한다 (11/02 사용자 요청). 서버 GPU 를 같이 쓰므로 `nvidia-smi` 를 보고 `CUDA_VISIBLE_DEVICES` 로 고른다.

```bash
cd ~/UROP
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export CUDA_VISIBLE_DEVICES=0,1
CKPT=$(cosmos-policy/.venv/bin/python -c 'from huggingface_hub import hf_hub_download; print(hf_hub_download("nvidia/Cosmos-Policy-LIBERO-Predict2-2B", "Cosmos-Policy-LIBERO-Predict2-2B.pt", local_files_only=True))')
echo "$CKPT"
cosmos-policy/.venv/bin/python -m docs.W9.d405.train \
  --cosmos-repo cosmos-policy --data-dir data/hdf5_mix --checkpoint "$CKPT" \
  --gpus 2 --steps 2000 --job-name w9_mix_p90m10_2000 --run \
  2>&1 | tee outputs/cosmos_policy/w9_mirobot/w9_mix_p90m10_2000.log
```

시간 측정은 같은 명령에서 `--steps 20`, `--job-name w9_mix_timing20_2gpu`(또는 `_4gpu` 와 `CUDA_VISIBLE_DEVICES=0,1,2,3` · `--gpus 4`).

- **`--gpus` 는 `CUDA_VISIBLE_DEVICES` 의 GPU 개수와 같아야 한다** — 모델을 그 수로 나눠 든다 (`model.config.fsdp_shard_size`)
- **두 학습을 동시에 못 돌린다** — 통신 포트가 12341 로 고정이다 (`train.py:85`)
- **`HF_HUB_OFFLINE=1` 필수** — 설정을 읽을 때 Video2World·ALOHA 체크포인트도 `hf_hub_download` 로 찾는다. 캐시에 있어서 오프라인이면 받지 않는다 (11/02 설정 확인)
- 서버 메모리는 GPU 프로세스마다 이미지 약 6.9 GB 를 올린다 — 손목만 학습해도 외부 영상까지 읽는다
- 체크포인트는 `outputs/cosmos_policy/w9_mirobot/<job>/checkpoints/iter_<번호>` (DCP 형식), 1000 step 마다 (`save_iter`, `cosmos_policy_experiment_configs.py:151`)

**loss 보기** — 5 step 마다 rank 0 의 한 배치 값이 찍힌다 (`iter_speed.py:86`, `logging_iter` 5 — `cosmos_policy_experiment_configs.py:91`). 한 배치 값이라 들쭉날쭉하니 수백 step 의 추세를 본다.

```bash
grep -a -o -E "[0-9]+ : iter_speed [0-9.]+ seconds per iteration \| Loss: [0-9.]+" outputs/cosmos_policy/w9_mirobot/w9_mix_p90m10_2000.log | tail
```

## 4. GPU 시간 측정 (11/02)

20 step 씩 두 번. step 은 **가중치를 한 번 갱신하는 단위**다 — GPU 마다 batch 1 을 8 번 누적한 뒤 1 을 센다 (`trainer.py:237-240`).

| | GPU 2개 (`w9_mix_timing20_2gpu`) | GPU 4개 (`w9_mix_timing20_4gpu`) |
| --- | --- | --- |
| step 당 시간 | **5.88–5.89 s** | 15.74–15.83 s |
| step 당 샘플 | 16 (2 × 1 × 8) | 32 (4 × 1 × 8) |
| **초당 샘플** | **2.7** | 2.0 |
| GPU 메모리 (최대 할당 / 예약) | 17.3 / 19.2 GB | 9.7 / 10.9 GB |
| 준비 (모델 + 데이터 로더) | 8.9 + 8.0 s | 9.8 + 12.2 s |
| 20 step | 10:26:13 – 10:28:19 (약 2분) | 10:39:39 – 10:45:04 (약 5.5분) |
| 체크포인트 저장 | 약 1.5분, 11 GB | 약 1분, 7.4 GB |

- **GPU 4개가 약 25% 느리다.** 원인은 GPU 사이 데이터 주고받기(PCIe 연결)로 추정한다 — 확인하지 않았다
- 사전학습 가중치는 정상으로 올라갔다 — `text2world_model.py:840` 이 `_IncompatibleKeys(missing_keys=[], unexpected_keys=[], incorrect_shapes=[])` 를 찍는다.
  로그의 "Training from scratch" 는 이 job 의 학습 상태(step 수·optimizer)를 이어받을 체크포인트가 없다는 뜻이다
- 측정 모델은 **사실상 학습 전**이다 — 5절 warmup 때문에 20 step 째 학습률이 약 2e-7
- 측정 체크포인트 두 개(11 GB + 7.4 GB)는 쓸모가 없다 — 지울지 미정
- 계획서의 GPU 원칙 "평소 2장, 4장은 협의" ([../plan/UROP_프로젝트_계획.md](../plan/UROP_프로젝트_계획.md) 2절)와도 맞는다

## 5. 결정 (11/02, 사용자) — GPU 2개 · 2000 step

| | 1000 step | **2000 step (결정)** |
| --- | --- | --- |
| 시간 (GPU 2개) | 약 1시간 40분 | 약 3시간 20분 |
| 데이터를 보는 횟수 (17,524 샘플) | 약 0.9 번 | 약 1.8 번 |
| 학습률 | 내내 warmup 중 | 앞 절반 warmup, 뒤 절반은 목표 근처 |
| 체크포인트 | 1000 | 1000 · 2000 — 둘을 비교할 수 있다 |

- **GPU 2개** — 더 빠르고, 남는 2·3번은 평가 작업에 쓴다
- **warmup** — 학습률은 처음 1000 step 동안 목표의 1e-6 배에서 1 배까지 선형으로 오른다 (`cosmos_policy_experiment_configs.py:100-106`).
  목표 학습률은 동료 진입점 값 1e-5 다 (`train.py:64` — 공식 LIBERO 실험 설정은 1e-4, `:98`). 1000 step 으로 끝내면 목표에 닿자마자 끝난다

## 6. 본학습 상태 (11/02 10:51 기준)

| 항목 | 값 |
| --- | --- |
| job | `w9_mix_p90m10_2000` — GPU 0·1, 로그 `outputs/cosmos_policy/w9_mirobot/w9_mix_p90m10_2000.log` |
| 실제 설정 (`config.yaml`) | `fsdp_shard_size` 2, `max_iter` 2000, `grad_accum_iter` 8, lr 1e-5, `save_iter` 1000, `logging_iter` 5, `use_third_person_images` False |
| 시작 | 10:47:22 실행, 10:47:45 학습 시작 |
| 진행 | 10:50:51 에 30 step, step 당 5.75–5.99 s, loss 3.2–8.5 (한 배치 값) |
| 재현 | 같은 seed 라 처음 두 step 의 loss 가 2 GPU 측정과 같다 (4.2508, 8.5381) — 같은 데이터·설정이 들어갔다 |
| 예상 | 1000 step 체크포인트 12:30 전후, 2000 step 14:10 전후 (저장 시간 포함) |
| **성능** | **아직 모른다** — 정책을 돌려 볼 도구가 없다 (7절) |

## 7. 평가 경로 — 있는 것 / 빠진 것 (11/02 조사, 읽기만)

| 경로 | 지금 있는 것 | 빠진 것 |
| --- | --- | --- |
| (a) Panda 시뮬 (W6 3색 장면) | `run_libero_eval.py` — 공식 LIBERO 묶음만 받는다 (`:289` assert). 관측 준비 `prepare_observation` (`:324`), 정책 실행 `cosmos_utils.py:851 get_action`, 손목만 옵션 | W6 `create_env` + 관측 준비 + action 묶음 실행 + 판정을 묶은 스크립트. **학습에 seed 0–29 를 썼으니 평가는 30 부터** |
| (b) Mirobot 실물 | 조각만 — `tools/action_to_poses.py` → `poses_to_gcode.py` → `run_gcode.py` (열린 고리, 일괄), 통신 `server/bridge_client.py` · `robot/serial_bridge.py` | 실시간 루프 전체 — D405 프레임에 학습과 같은 처리(색 보정, 가운데 자르기, 256), `?` → proprio (`common/proprio.py`), action 묶음 → 명령, 묶음마다 실제 자세로 다시 맞추기 ([../W5/CHECKLIST.md](../W5/CHECKLIST.md) 2-4) |
| (c) 오프라인 | 없음 | HDF5 에피소드로 예측 action 오차를 재는 스크립트. 지금은 100개가 모두 학습에 들어가 떼어 둔 데이터가 없다 |

- 학습한 체크포인트는 DCP 형식이다 — 추론 로더가 DCP 를 읽는다 (`cosmos_policy/_src/predict2/utils/model_loader.py:205`)
- 평가 지표는 계획서의 **언어 준수율** — 세 블록 중 지시한 색 쪽으로 손을 뻗었나, 목표 60%, 무작위 33% ([../plan/UROP_프로젝트_계획.md](../plan/UROP_프로젝트_계획.md) 1절). 평가 도구와 함께 W10 에서 다룬다
