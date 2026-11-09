# W10 녹화 → Cosmos 학습 데이터 점검

> **기록** · 확인 2026-11-05 · 기준 `Mirobot_data/W10` L01–L20 (60개, 커밋 `15cebaee`), `cosmos-policy@18a2acc`
> 이번 주 수집한 실물 녹화를 Cosmos Policy 학습에 바로 넣을 수 있는지 서버에서 확인한 것. 단계, 결과, 남은 결정.

계획: 이번 주 세부 계획 11/5 "수집한 데이터를 Cosmos Policy 에 바로 넣을 수 있는 상태인지 확인" ([../meetings/2026-11-02.md](../meetings/2026-11-02.md) action plan 1·2번).
노트북 쪽 1차 점검(11/04): [HDF5_ALIGNMENT.md](HDF5_ALIGNMENT.md) — 정렬 기준과 미통과 5개. 수집 방법: [../../Mirobot_data/README.md](../../Mirobot_data/README.md).

## 0. 결론

- **지금 있는 55개는 Cosmos Policy 에 바로 넣을 수 있다** — `data/hdf5_w10/` (11/05). 구조·T5 검사, 실제 Cosmos 로더(`training_ready`), 학습 설정(`--dryrun`) 모두 통과
- 55개 = 17,320칸, 빨강 19 (5,989칸) · 초록 19 (6,057칸) · 파랑 17 (5,274칸). 60개 중 5개는 정렬 기준 미통과로 뺐다 (2절)
- **미통과 5개는 90개를 다 찍은 뒤 다시 찍는다** (11/05 사용자). 새 녹화가 오면 `tools/build_real_dataset.py` 를 다시 돌린다 (6절)
- 학습 전에 정할 것 하나 — action 라벨 방식 ([POLICY_RUN.md](POLICY_RUN.md) 3절). 지금 HDF5 는 W9 와 같은 시뮬 따라가기 라벨이다 (5절)

## 1. 단계와 도구

녹화(노트북) → 정렬(노트북, `prepare --max-frame-ms 70`) 까지는 노트북에서 끝나 있다. 서버에서 한 것:

| 단계 | 도구 | 하는 일 |
| --- | --- | --- |
| 1. 녹화 점검 | `tools/inventory_recordings.py` (새로 만듦) | 폴더마다 완료·색 일치·PNG 수·F8 구간·`layout.json`·`real_success`·정렬 파일·입력 해시·카메라/로봇 간격을 보고 `ready` 를 고른다. 나머지 30개를 받은 뒤에도 같은 명령으로 다시 돌린다 |
| 2. HDF5 변환 | `docs/W9/d405/export_real_hdf5.py` (동료) | **색마다 따로** 돌린다 — `--target` 이 한 번에 넣은 모든 녹화에 붙고 metadata 색과 대조하지 않는다. action 라벨은 빈 탁상 시뮬 Panda 따라가기 (W9 와 같은 방식) |
| 3. T5 · 통계 | 복사 | 지시문 세 문장이 1차와 같아 `data/hdf5_mix/t5_embeddings.pkl` 을 그대로(해시 같음). 통계는 공식 LIBERO (`dataset_statistics.json`, HF 캐시 것과 같음) |
| 4. 구조 검사 | `docs/W9/d405/check_dataset.py` (동료) | 키·모양·dtype·유한값·action 범위·쿼터니언·0.05 s 간격, 파일 이름 = 지시문, T5 |
| 5. 로더 검사 | `tools/check_cosmos_dataset.py` | 학습과 같은 인자로 Cosmos `LIBERODataset` 을 만들어 샘플을 뽑는다 (실제 T5, 공식 통계) |
| 6. 학습 설정 | `docs/W9/d405/train.py --dryrun` (동료) | GPU 없이 실제 Cosmos 학습 설정을 풀어 손목 전용 값(state_t 7 등)이 맞는지 |

산출물은 `data/hdf5_w10/` — `mirobot_real/*.hdf5`(git 제외), `t5_embeddings.pkl`, `dataset_statistics.json`, 검사 결과 json.

## 2. 녹화 점검 (60개)

```bash
cosmos-policy/.venv/bin/python -m tools.inventory_recordings Mirobot_data/W10    # → docs/W10/data/inventory_W10.json
```

| 항목 | 결과 |
| --- | --- |
| `ready` | **55개, 17,320칸** — 빨강 19 · 초록 19 · 파랑 17. 세 색이 다 있는 배치 16개 (L09·L10·L13·L19 빼고) |
| 60개 공통 | 완료, 폴더 색 = metadata 색 = reference, PNG 수 = `frames.jsonl`, F8 구간 하나, **`?` 원문(`raw`) 저장됨** |
| 카메라 저장 속도 | 대부분 11–12.4 fps, 정렬 최대 오차 41.8–66.3 ms (ready 55개) |
| 미통과 | 5개 — 아래 |

노트북 점검(HDF5_ALIGNMENT.md)과 숫자가 같다.

**미통과 5개.**

| 녹화 | 이유 | 들여다본 것 (11/05) |
| --- | --- | --- |
| L09_blue, L10_blue | 카메라가 초당 4장밖에 저장 못 함(정렬 오차 121–147 ms), `layout.json`·성공 기록 없음 | 다시 찍어야 한다 |
| L13_red, L13_blue, L19_green | 정렬 오차 70.4 · 70.4 · 71.4 ms — 기준 70 ms 를 **한 칸만** 넘는다 | 넘는 칸은 다가가는 도중(칸 87 · 210 · 42, 닫기 전)이고 두 번째로 큰 오차는 64.5 · 67.2 · 67.3 ms. 앞뒤를 잘라 통과시킬 수는 없다(시연 앞부분이 사라진다) |

- **결정 (11/05, 사용자)** — 90개를 다 찍은 뒤 미통과 녹화를 다시 찍는다. 블록 자리는 같은 배치 다른 색의 `layout.json` 에 있다 (L09·L10 은 파랑만 빠졌다)

## 3. HDF5 변환 (55개)

| 항목 | 결과 |
| --- | --- |
| 변환 | 55개 모두 성공 (색마다 따로, `--real-success`). 파일 이름 `MIROBOT_L01_red_SCENE1_pick_up_the_red_block_on_the_table_demo.hdf5` — `SCENE1` 뒤가 지시문 |
| 크기 | 2.7 GB (`data/hdf5_w10/mirobot_real/`, git 제외) |
| 칸 수 | 녹화당 평균 315칸 (232–397) |
| action 라벨 | 위치 칸 최대 0.256 · 평균 0.044, 회전 칸 최대 0.013, 자르기(크기 1 초과) 0칸. 집게는 녹화마다 정확히 한 번 닫힌다 (닫힌 칸 24%) |
| 시뮬 따라가기 오차 | 평균 3.04 mm, 녹화별 최대 5.8–6.7 mm, 회전 최대 0.39°. 잠정 기준 5 mm 를 49/55 개가 한 번은 넘는다 — W9 영상1–10 도 모두 넘었다 ([../W9/FOLLOW.md](../W9/FOLLOW.md) 4절). 라벨 방식 결정(5절)과 이어진다 |
| proprio | 손가락 0.0140–0.0398 (B'), 손 자세 쿼터니언 4칸은 상수(보고 자세 A·B·C = 0) — 공식 통계로 펴므로 문제 없다 |
| 허용치 기록 | 변환기가 정렬 보고서에 키가 없어 `accepted_max_frame_ms` 를 **40** 으로 적었다 → 실제 기준 **70** 으로 고쳐 적었다(설명 속성 `accepted_max_frame_ms_note` 추가). 로더는 이 값을 읽지 않는다 |

## 4. 로더·학습 설정

| 검사 | 결과 |
| --- | --- |
| 구조·T5 (`check_dataset`) | 55개 · 17,320칸 · 지시문 3개, 모두 T5 임베딩 있음 |
| Cosmos 로더 (`check_cosmos_dataset`) | `passed`, **`training_ready: true`**, 손목 전용, 실제 T5, 공식 통계, 정규화 값 유한, 샘플 111개 · 배치 video (2, 3, 25, 224, 224) · actions (2, 16, 7) → `data/hdf5_w10/loader_validation.json` |
| 학습 설정 (`train --dryrun`) | `passed` — 손목 전용, `state_t` 7, 조건 프레임 3, `chunk_duration` 25, `fsdp_shard_size` 2, 외부 영상 없음 → `data/hdf5_w10/training_config_validation.json` |

- `--dryrun` 은 GPU 메모리를 쓰지 않지만, 설정을 읽을 때 모델 코드가 flash-attn 을 확인해서 **CUDA 가 보여야** 한다 (`CUDA_VISIBLE_DEVICES=''` 이면 실패)
- 학습 출력 폴더 이름은 `outputs/cosmos_policy/w9_mirobot/<job>` 이다 — `train.py` 의 `job.group` 이 `w9_mirobot` 으로 고정돼 있다 (동작에는 상관없음)

## 5. 학습 전에 정할 것 — action 라벨 방식

지금 HDF5 의 action 은 W9 와 같은 **시뮬 Panda 따라가기 라벨**이다. 이 라벨로 학습한 정책을 실물에서 돌리면 action 을 Mirobot 목표로 바꾸는 방법이 문제가 된다 —
16개 묶음을 차례로 더하면 끝 목표가 평균 44 mm 어긋난다 ([POLICY_RUN.md](POLICY_RUN.md) 3절, 후보 A·B·C). C(라벨을 실물 자세 차이로 다시 만들기)로 가면 **학습 전에** HDF5 를 다시 만들어야 한다.
다시 만드는 데 시뮬이 필요 없어 금방이다 (변환기의 `action_generator` 인자).

## 6. 다시 하기 — 새 녹화가 왔을 때

```bash
git pull --ff-only && git lfs pull
cosmos-policy/.venv/bin/python -m tools.build_real_dataset Mirobot_data/W10 --out data/hdf5_w10      # 점검 → 변환 → 허용치 → T5·통계 → 구조 검사
# 끝에 찍히는 두 명령: Cosmos 로더 검사, 학습 설정 --dryrun
```

- 이미 만든 HDF5 는 입력이 같으면 확인만 한다(55개 3초). 새 녹화만 만든다 (녹화당 약 45 s, 6개씩 동시에)
- 다시 찍은 녹화는 새 이름(`L13_red_2`)으로 저장된다 — 녹화 도구가 같은 이름이면 시작 전에 멈춘다. 점검 도구는 `_2` 붙은 이름도 같은 배치·색으로 읽고, 옛 `L13_red` 는 ready 가 아니라 저절로 빠진다
- ready 가 아닌데 폴더에 남은 HDF5 가 있으면 경고한다 (학습에 들어가므로 직접 확인)
- 표만 보려면 `cosmos-policy/.venv/bin/python -m tools.inventory_recordings Mirobot_data/W10`

학습 명령(GPU — tmux 에서 직접)은 1차와 같고 데이터 폴더와 이름만 바꾼다 ([../W9/FINETUNE.md](../W9/FINETUNE.md) 3절):

```bash
cosmos-policy/.venv/bin/python -m docs.W9.d405.train --cosmos-repo cosmos-policy --data-dir data/hdf5_w10 \
  --checkpoint "$CKPT" --gpus 2 --steps 2000 --job-name <이름> --run
```
