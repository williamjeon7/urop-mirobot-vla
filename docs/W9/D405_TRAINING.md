# D405 HDF5를 Cosmos Policy LIBERO에 파인튜닝하기

**이 문서는 전부 [서버: OASYS Linux Bash]에서 실행합니다.** Windows 노트북에서 촬영·색 보정·키보드 녹화·영상 검토를 마치고, 원본 `raw/`와 `calibration/`을 전송한 다음 시작합니다. 전송 절차는 [D405_GUIDE.md 6절](D405_GUIDE.md#6-서버에서-외부-영상action-생성--hdf5)을 따릅니다.

서버에서 `cd ~/UROP` 후 기존 `cosmos-policy/.venv/bin/python`으로 실행합니다. 로컬의 `Scripts/python.exe`나 수집용 W9 환경으로 학습하지 않습니다. W9 수집 환경 설치는 CUDA·모델 가중치 준비와 별개입니다.

## 1. 서버 환경 — [서버: OASYS Bash]

기존 `cosmos-policy/.venv`와 LIBERO 에셋이 있는 서버라면 재설치하지 말고 그 환경을 쓰세요. 이 저장소와 `docs/W6/rgb_blocks` 및 에셋이 필요합니다. CPU용 W9 requirements로 Cosmos 환경을 덮어쓰지 마세요.

새 서버라면 [공식 SETUP.md](https://github.com/NVlabs/cosmos-policy/blob/main/SETUP.md)에 따라 NVIDIA 드라이버·Docker GPU 환경을 준비한 뒤 공식 저장소를 설치합니다. W9 안에 소스를 둘 경우:

```bash
mkdir -p docs/W9/vendor
git clone https://github.com/NVlabs/cosmos-policy.git docs/W9/vendor/cosmos-policy
```

기존 문서의 검증 기준은 `cosmos-policy@18a2acc`입니다. 새 버전에서 설정 이름이 바뀌었는지 확인하세요. 공식 컨테이너에서의 LIBERO 의존성 설치 명령은 다음과 같습니다:

```bash
uv sync --extra cu128 --group libero --python 3.10
```

이 명령은 Cosmos 저장소 안에서 실행합니다. 로컬 CUDA·드라이버와 호환되는 컨테이너는 공식 안내를 따르세요. 학습 스크립트는 `cosmos_policy.scripts.train`입니다. 기본 영상 모델의 다른 train.py를 쓰지 않습니다.

**이후 예시**는 서버의 저장소 루트에서 `cosmos-policy/.venv/bin/python`을 사용합니다. W9/vendor에 설치했다면 경로를 `docs/W9/vendor/cosmos-policy/.venv/bin/python`으로 바꾸세요. 외부 체크아웃에 설치된 패키지가 import되도록 공식 설치 환경을 사용합니다.

## 2. HDF5 만들기와 실제 로더 확인 — [서버: OASYS Bash]

Windows 노트북에서 전송한 원본이 OASYS의 `docs/W9/data/raw/`에 있는지 확인합니다. 이후 모든 명령은 서버 저장소 루트에서 실행합니다:

```bash
cosmos-policy/.venv/bin/python -m docs.W9.d405.export_hdf5 \
  docs/W9/data/raw/red_s2_001 --out docs/W9/data/hdf5/mirobot_real \
  --real-success --layout-confirmed

cosmos-policy/.venv/bin/python -m tools.check_cosmos_dataset \
  --data-dir docs/W9/data/hdf5 --recompute-stats
```

첫 명령은 실물 성공·배치 확인 후 실행합니다. 추종 오차나 시뮬 실패는 먼저 해결해야 합니다. 두 번째 검사는 데이터 통계를 만들지만 T5는 임시 가짜 값으로 모양만 확인합니다.

실물+시뮬 데이터를 혼합했다면 전체 폴더에 대해 통계를 계산합니다. 정규화 통계는 정책 실행의 역정규화에도 같은 파일을 사용해야 합니다. 기존 LIBERO 통계 유지와 새 데이터 통계 사용은 별도 실험 선택이며 현재 train 도구는 이 데이터 폴더의 통계를 사용합니다. 기존 설계 논점은 [DATASET_HDF5.md 7절](DATASET_HDF5.md#7-정규화-통계-문제)을 보세요.

## 3. 실제 지시문 T5 임베딩 — [서버: OASYS Bash]

새로운 지시문(예: `pick up the red block on the table`)은 기존 LIBERO 임베딩에 없을 수 있습니다. 단어·대소문자·마침표까지 일치해야 합니다.

서버의 T5-11B 캐시가 이미 있다면:

```bash
cosmos-policy/.venv/bin/python -m docs.W9.d405.make_t5 docs/W9/data/hdf5
```

없다면 **대용량 T5-11B 다운로드와 GPU 메모리 확보가 필요**합니다. 다운로드를 하기로 한 뒤:

```bash
cosmos-policy/.venv/bin/python -m docs.W9.d405.make_t5 docs/W9/data/hdf5 --allow-download
```

`torch`, `transformers`, `sentencepiece`는 서버 Cosmos 환경에 설치되어 있어야 합니다. 출력은 `docs/W9/data/hdf5/t5_embeddings.pkl`입니다. 이 파일은 직접 만든 신뢰할 수 있는 pickle만 로드하세요.

```bash
cosmos-policy/.venv/bin/python -m docs.W9.d405.check_dataset docs/W9/data/hdf5 \
  --t5 docs/W9/data/hdf5/t5_embeddings.pkl
```

학습 도구는 누락·잘못된 모양·0으로 채운 가짜 임베딩을 거부합니다.

## 4. LIBERO Policy 체크포인트 — [서버: OASYS Bash]

기존 서버 캐시의 가중치가 있다면 그 로컬 `.pt` 경로를 사용합니다. 새로 받아야 하면 서버에서:

```bash
hf download nvidia/Cosmos-Policy-LIBERO-Predict2-2B \
  Cosmos-Policy-LIBERO-Predict2-2B.pt \
  --local-dir docs/W9/data/models/libero
```

모델 저장소의 접근 조건·로그인이 필요한 경우 해당 계정에서 먼저 준비합니다. 기본 Video2World가 아니라 **LIBERO Policy 가중치에서 이어 학습**하도록 아래 도구가 `checkpoint.load_path`를 명시합니다.

## 5. 명령을 먼저 확인한 뒤 실행 — [서버: OASYS Bash]

```bash
cosmos-policy/.venv/bin/python -m docs.W9.d405.train \
  --cosmos-repo cosmos-policy \
  --data-dir docs/W9/data/hdf5 \
  --checkpoint docs/W9/data/models/libero/Cosmos-Policy-LIBERO-Predict2-2B.pt \
  --gpus 1 --batch-size 1 --accum 8 --steps 1000
```

위 명령은 실제 학습을 시작하지 않고 명령을 출력합니다. 준비가 되면 같은 명령 뒤에 `--run`을 붙입니다.

이 작은 배치·학습률·1,000스텝은 **연결 확인을 위한 시작 설정**이며 검증된 최적 학습 조건이 아닙니다. 1 GPU면 반드시 학습된다는 뜻도 아닙니다. VRAM이 부족하면 중단되며 서버 GPU 구성에 맞춰 설정해야 합니다. 공식 학습 안내는 대규모 GPU 환경을 기준으로 합니다. [공식 LIBERO 학습 문서](https://github.com/NVlabs/cosmos-policy/blob/main/LIBERO.md), [공식 요구사항](https://github.com/NVlabs/cosmos-policy#system-requirements).

도구는 DataLoader와 DistributedSampler의 데이터 경로를 함께 바꾸고, 기본 설정에 들어 있는 별도 rollout 데이터 경로를 비웁니다. 사용자 성공 데모만 학습 대상으로 삼는 출발 설정입니다. 실패·가치 함수 학습의 비율을 설계하려면 별도로 설정해야 합니다.

## 6. 실행 전에 남겨둘 것 — [서버: OASYS Bash]

- 데이터 구분은 프레임이 아닌 **에피소드·배치(seed) 단위**로 합니다. 같은 에피소드의 이웃 프레임을 검증 데이터로 나누면 안 됩니다. 검증 에피소드는 학습 폴더 밖에 두세요.
- 데이터·T5·통계·색 보정 프로필·카메라 설정·학습 config·checkpoint를 함께 보관합니다.
- 데이터가 바뀌면 정규화 통계도 다시 계산하고 새 지시문 임베딩을 준비합니다.
- 추론에서도 D405 RGB에 같은 색 보정→crop/회전→resize를 적용합니다. 시뮬용 이미지 flip을 실물 RGB에 무조건 적용하지 마세요.
- loss 감소와 실제 집기 성공률을 따로 확인합니다. 학습된 action은 Panda OSC_POSE이며 Mirobot 관절각이나 G-code로 바로 보내지 않습니다. 기존 변환·실행 파이프라인을 사용합니다.

서버에서의 실제 학습·시뮬 검증은 아직 실행하지 않았습니다. 현재 OASYS 설치·검증 결과와 이전 Windows 시험 기록은 [D405_INSTALLATION.md](D405_INSTALLATION.md)를 보세요.
