# W10 학습 진행 — Mirobot 실물 데이터만으로 Cosmos Policy 파인튜닝

> **절차** · 확인 2026-11-06 · 기준 `data/hdf5_w10` (55개 준비 당시 계획), `cosmos-policy@18a2acc`, W9 1차 파인튜닝 실측값([../W9/FINETUNE.md](../W9/FINETUNE.md))
> 이번 주 수집한 실물 녹화로 Cosmos Policy 를 학습하고 스텝별·색별로 비교하는 순서. 먼저 정할 것, 데이터, 학습 명령, 결과 비교에서 되는 것과 아직 안 되는 것.

배경: 11/02 미팅 — Mirobot 데이터만으로 먼저 파인튜닝, 정책은 Cosmos 가 아니어도 됨 ([../meetings/2026-11-2.md](../meetings/2026-11-2.md)).
데이터 점검: [DATA_CHECK.md](DATA_CHECK.md). 실행 도구·action 라벨 문제: [POLICY_RUN.md](POLICY_RUN.md). 1차(혼합) 학습 기록: [../W9/FINETUNE.md](../W9/FINETUNE.md).

**서버의 최신 90개용 경로와 실행 안내**는 [cosmos-policy/W10/TRAINING.md](../../cosmos-policy/W10/TRAINING.md)를 본다.
공용 가중치는 `cosmos-policy/models/`, 주차별 데이터·설정·학습·평가는 `cosmos-policy/W10/`으로 정리했다.
이 문서 아래는 55개 준비 시점의 계획이며, 구조 정리 과정에서 학습은 실행하지 않았다.

이후 수행한 90개·4,000 update 학습은 정상 완료했다. 실제 실행 조건·완료 시각·체크포인트는 [TRAINING_RESULT.md](TRAINING_RESULT.md)에 기록했다.

## 0. 한눈에 — 순서

| # | 할 일 | 상태 (11/05) |
| --- | --- | --- |
| 1 | **정할 것 세 가지** — action 라벨 방식, 평가용으로 뺄 배치, step 수 (1절) | **결정 대기** |
| 2 | 데이터 최신화 — 90개 + 다시 찍은 5개를 받아 `build_real_dataset` → 로더 · `--dryrun` (2절) | 55개까지 끝 |
| 3 | 학습 — GPU 2개, tmux 에서 직접 (3절) | |
| 4 | 결과 비교 — 체크포인트(1000 step 마다)별 · 색별. 오프라인은 지금 된다, **실물 성공률은 실행 루프가 있어야** 한다 (4절) | 오프라인 도구는 GPU 첫 실행 대기 |

## 1. 먼저 정할 것 (결정 대기)

| 항목 | 선택지 | 제안 (임의 판단) | 왜 |
| --- | --- | --- | --- |
| **action 라벨** | 지금 HDF5 그대로(시뮬 Panda 따라가기 라벨) / C: 실물 자세 차이로 다시 만들기 | **C** | 지금 라벨로 학습하면 실물에서 action 16개 묶음을 차례로 실행할 때 끝 목표가 평균 44 mm 어긋난다 ([POLICY_RUN.md](POLICY_RUN.md) 3절, 후보 A·B·C). C 는 **학습 전에** HDF5 를 다시 만들어야 한다 — `build_real_dataset` 에 라벨 옵션을 더하고(약 30분) 다시 만든다(약 10분, 시뮬 불필요). 정하지 않고 학습하면 지금 라벨로 학습되고, 나중에 C 로 가면 다시 학습한다 |
| **평가용으로 뺄 배치** | 90개 모두 학습 / 배치 2–3개(× 세 색)를 빼서 오프라인 평가에만 | 배치 3개(녹화 9개) 빼기 | 학습에 쓴 녹화로 잰 오프라인 지표는 "학습 데이터를 따라 하는가" 만 보여 준다. 실물 평가는 녹화하지 않은 새 배치로 하면 되지만, 실물 실행 루프가 아직 없어서 당장은 오프라인 지표가 유일한 비교 수단이다 |
| **step 수** | 2000 / 3000 / 4000 (아래 표) | 90개면 **4000** (밤새, 체크포인트 4개) | 1차는 데이터를 약 1.8번 봤다(2000 step). 90개를 2000 step 이면 1.1번뿐이다. 체크포인트가 1000 step 마다라 4000 이면 1000·2000·3000·4000 을 비교할 수 있다 |

step 수와 데이터를 보는 횟수 (1 step = GPU 2개 × batch 1 × 누적 8 = 샘플 16개, step 당 약 5.9 s — W9 실측):

| step | 샘플 | 55개 (17,320칸) | 90개 (약 28,000칸, 추정) | 시간 (GPU 2개, 저장 포함) |
| --- | --- | --- | --- | --- |
| 1000 | 16,000 | 0.9번 | 0.6번 | 약 1시간 40분 |
| 2000 | 32,000 | 1.8번 | 1.1번 | 약 3시간 20분 |
| 3000 | 48,000 | 2.8번 | 1.7번 | 약 5시간 |
| 4000 | 64,000 | 3.7번 | 2.3번 | 약 6시간 40분 |

- 학습률은 처음 1000 step 동안 목표(1e-5)의 1e-6 배에서 1 배로 오른다 (warmup). 1000 step 체크포인트는 warmup 이 막 끝난 상태다
- 1차(혼합) loss: 처음 200 step 평균 2.56 → 1000 step 무렵 0.11 → 마지막 200 step 0.06. loss 는 성능이 아니다

## 2. 데이터 최신화

```bash
cd ~/UROP
git pull --ff-only && git lfs pull
cosmos-policy/.venv/bin/python -m tools.build_real_dataset Mirobot_data/W10 --out data/hdf5_w10
# 끝에 찍히는 두 명령(Cosmos 로더 검사, 학습 설정 --dryrun)도 돌린다 — 둘 다 GPU 메모리를 쓰지 않는다
```

- 점검 → 색별 변환 → 허용치 기록(70 ms) → T5·통계 → 구조 검사까지 한 번에. 이미 만든 HDF5 는 확인만 한다 ([DATA_CHECK.md](DATA_CHECK.md) 6절)
- 출력 첫 줄의 `ready` 수와 `제외` 목록을 본다. 제외된 녹화(정렬 기준 미통과 등)는 학습에 안 들어간다
- **평가용 배치를 빼기로 했으면** — 그 배치의 HDF5 를 학습 폴더 **밖**으로 옮긴다 (예: `data/hdf5_w10_heldout/mirobot_real/`). 로더가 `data/hdf5_w10/*/` 아래를 모두 읽으므로 같은 폴더 안 하위 폴더로 옮기면 학습에 들어간다

## 3. 학습 — GPU, tmux 에서 직접

GPU 는 서버에서 같이 쓰므로 `nvidia-smi` 로 빈 GPU 두 개를 고른다. 학습은 한 번에 하나만 돌릴 수 있다 (통신 포트 12341 고정).

```bash
tmux new -s w10_train
cd ~/UROP
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export CUDA_VISIBLE_DEVICES=0,1          # 고른 GPU 두 개
CKPT=$(cosmos-policy/.venv/bin/python -c 'from huggingface_hub import hf_hub_download; print(hf_hub_download("nvidia/Cosmos-Policy-LIBERO-Predict2-2B", "Cosmos-Policy-LIBERO-Predict2-2B.pt", local_files_only=True))')
JOB=w10_mirobot90_4000                    # 데이터·step 이 드러나게
cosmos-policy/.venv/bin/python -m docs.W9.d405.train \
  --cosmos-repo cosmos-policy --data-dir data/hdf5_w10 --checkpoint "$CKPT" \
  --gpus 2 --steps 4000 --job-name $JOB --run \
  2>&1 | tee outputs/cosmos_policy/w9_mirobot/$JOB.log
```

- `--gpus` 는 `CUDA_VISIBLE_DEVICES` 의 GPU 개수와 같아야 한다. GPU 4개는 2개보다 느렸다 (W9 실측 초당 2.0 vs 2.7 샘플)
- `HF_HUB_OFFLINE=1` 필수 — 설정을 읽을 때 다른 체크포인트도 찾는데 캐시에 있어 받지 않는다
- 체크포인트: `outputs/cosmos_policy/w9_mirobot/$JOB/checkpoints/iter_000001000` … (1000 step 마다, 한 번에 약 11 GB, 저장 약 1.5분)
- loss 보기 (5 step 마다 한 배치 값이라 들쭉날쭉 — 수백 step 추세를 본다):

```bash
grep -a -o -E "[0-9]+ : iter_speed [0-9.]+ seconds per iteration \| Loss: [0-9.]+" outputs/cosmos_policy/w9_mirobot/$JOB.log | tail
```

## 4. 결과 비교 — 스텝별 · 색별

"스텝별" 은 체크포인트(1000·2000·… step)별로 본다는 뜻으로 읽었다 (해석).

### 4-1. 오프라인 — 지금 할 수 있다

녹화 HDF5 의 관측을 정책에 넣어 예측 action 을 라벨과 비교한다. 로봇이 필요 없다. 도구는 [POLICY_RUN.md](POLICY_RUN.md) 4절 `tools/eval_offline.py`.

```bash
# 체크포인트마다: 합치기(CPU, 몇 초) → 평가(GPU 하나, tmux)
cosmos-policy/.venv/bin/python -m tools.eval_offline --ckpt outputs/cosmos_policy/w9_mirobot/$JOB/checkpoints/iter_000001000 --convert-only
CUDA_VISIBLE_DEVICES=2 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 cosmos-policy/.venv/bin/python -m tools.eval_offline \
  --ckpt outputs/cosmos_policy/w9_mirobot/$JOB/checkpoints/iter_000001000 \
  --hdf5 "data/hdf5_w10_heldout/mirobot_real/*.hdf5" --every 16 \
  2>&1 | tee outputs/cosmos_policy/w9_mirobot/${JOB}_eval_1000.log
```

- 결과 `docs/W10/data/eval_offline_<job>_<iter>.json` — 녹화별 값과 **지시문(색)별 요약**(`by_instruction`)
- 지표: 칸마다 위치 차(mm), 묶음 끝 차(16칸 합, mm), 집게 부호 일치율, 정책 한 번 추론 시간. **"모두 0" 기준선보다 작아야** 의미가 있다
- 뺀 배치가 없으면 `--hdf5` 를 학습 데이터로 준다 — 이때는 "학습 데이터를 따라 하는가" 만 본다
- 녹화 하나에 16칸마다 한 번 묻으면 약 20번이다. 추론 시간이 아직 잰 적이 없어 전체 시간은 첫 실행에서 정한다. **`eval_offline` 은 GPU 로 한 번도 돌려 보지 않았다** — 먼저 1차 체크포인트로 한 번 돌려 확인한다 (POLICY_RUN 4절 명령)

### 4-2. 실물 성공률 — 실행 루프가 있어야 한다

색별 실물 성공률(집어 들었나)과 언어 준수율(지시한 색 쪽으로 손을 뻗었나 — 계획서 최소 목표 60%, 무작위 33%)은 정책을 실물에서 돌려야 잴 수 있다.
그 도구(카메라·로봇 상태 → 정책 → Mirobot 명령)는 아직 없다 — 관측·명령 계산은 녹화로 확인해 뒀고([POLICY_RUN.md](POLICY_RUN.md) 2절), 남은 것은 루프와 action 라벨 방식(1절)이다.

- 평가 배치는 **녹화에 쓰지 않은 새 배치**로 한다 ([../../Mirobot_data/README.md](../../Mirobot_data/README.md) 폴더 규칙)
- 색마다 같은 횟수, 같은 배치에서 세 색을 모두 시킨다 (녹화와 같은 방식)

## 5. 결과 정리 양식

| job | 데이터 (학습 / 뺀 배치) | 라벨 | step | 색 | 칸 위치 차 mm (0 기준) | 묶음 끝 차 mm (0 기준) | 집게 일치 | 추론 s | 실물 성공 | 언어 준수 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | | 1000 | red | | | | | | |
| | | | 1000 | green | | | | | | |
| | | | 1000 | blue | | | | | | |
