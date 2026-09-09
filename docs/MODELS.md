# 모델 가중치

> **절차** · 확인 2026-09-09 · 기준 서버 OASYS HF 캐시 24GB
> 어느 환경에 어떤 모델이 필요한지, 받는 법과 캐시 위치.

**모델 파일은 이 저장소에 없다.** `.gitignore` 가 `*.pt` / `*.safetensors` / `*.ckpt` 를
막고 있고, 합쳐서 20GB 가 넘어 git 으로 다룰 크기가 아니다. 아래 절차로 각자 받는다.

## 먼저 — 내 환경에 모델이 필요한가?

이 저장소는 세 종류의 환경에서 clone 된다.

| 환경 | 필요한 모델 | 이유 |
|---|---|---|
| **개인 노트북** (코드 확인용) | **없음** | 코드를 읽고 드라이런으로 동작만 보는 용도. `pip install -e .` 하나면 된다. `README.md` 의 "코드만 확인하려면" 참조. |
| ↳ cosmos-policy 코드까지 볼 때 | **없음** | `cosmos-policy` 를 따로 clone 해야 한다 (약 20MB, `.gitignore` 라 mirobot-vla clone 에 안 따라옴). LIBERO 관측 샘플과 메타정보는 설치 없이 열린다. `docs/VENDORED.md` 참조. |
| **로봇 노트북** (Windows, 실기) | **없음** | `robot/` 은 시리얼로 G-code 를 보내는 것뿐이다. 저장된 데모 궤적(`common/demos.py`)을 재생하므로 추론이 없다. |
| **GPU 서버** (Linux, 학습/추론) | cosmos-policy 계열 | 정책 학습과 추론을 여기서 돌린다. |

즉 **모델이 실제로 필요한 건 GPU 서버 한 곳뿐이다.** 나머지 두 환경은 받을 필요가 없다.

## 모델 목록

| 모델 | 크기 | 용도 | 받는 법 |
|---|---|---|---|
| [nvidia/Cosmos-Policy-LIBERO-Predict2-2B](https://huggingface.co/nvidia/Cosmos-Policy-LIBERO-Predict2-2B) | 3.7GB | 주 정책. LIBERO 4개 태스크 스위트로 학습된 사전학습 체크포인트 | **자동** (아래 참조) |
| [nvidia/Cosmos-Policy-RoboCasa-Predict2-2B](https://huggingface.co/nvidia/Cosmos-Policy-RoboCasa-Predict2-2B) | — | RoboCasa 버전. LIBERO 대신 쓸 경우 | 자동 |
| [microsoft/Phi-3.5-vision-instruct](https://huggingface.co/microsoft/Phi-3.5-vision-instruct) | 7.8GB | Phi 변형 트랙의 백본 (계획 2안, 아직 미구현) | `hf download` |
| [microsoft/Phi-4-multimodal-instruct](https://huggingface.co/microsoft/Phi-4-multimodal-instruct) | 12GB | Phi 변형 대안 | `hf download` |
| [physical-intelligence/fast](https://huggingface.co/physical-intelligence/fast) | 724KB | FAST 액션 토크나이저 | 자동 |

## Cosmos Policy 체크포인트 — 따로 받지 않아도 된다

eval 스크립트에 `--ckpt_path nvidia/Cosmos-Policy-LIBERO-Predict2-2B` 처럼 **HuggingFace
repo ID 를 그대로** 넘기면 실행 시점에 알아서 받아서 캐시에 넣는다. 미리 `hf download`
할 필요가 없다. 자세한 실행 명령은 `cosmos-policy/LIBERO.md` 를 본다.

체크포인트 repo 안에는 가중치 말고도 실행에 필요한 파일이 같이 들어 있다:

```
Cosmos-Policy-LIBERO-Predict2-2B.pt    3.7GB   가중치
libero_t5_embeddings.pkl                41MB   태스크 문장 T5 임베딩
libero_dataset_statistics.json           4KB   액션 정규화 통계
config.json
```

뒤의 두 개도 eval 인자로 넘겨야 한다 (`--dataset_stats_path`, `--t5_text_embeddings_path`).

## 데이터셋 — 이건 수동이고, 학습할 때만 필요하다

```bash
hf download nvidia/LIBERO-Cosmos-Policy --repo-type dataset --local-dir LIBERO-Cosmos-Policy
export BASE_DATASETS_DIR=$(pwd)
```

추론만 할 거면 건너뛴다. 사전학습 체크포인트가 이미 있기 때문이다.

## 캐시 위치

받은 파일은 저장소가 아니라 HuggingFace 캐시로 들어간다.

```
~/.cache/huggingface/hub/
```

`HF_HOME` 환경변수로 위치를 바꿀 수 있다. 홈 디렉토리 용량이 부족하면 큰 디스크로
옮기는 게 낫다:

```bash
export HF_HOME=/mnt/hdd/home/$USER/.cache/huggingface
```

Docker 로 cosmos-policy 를 돌릴 때 `-v $HOME/.cache:/home/cosmos/.cache` 를 붙이면
호스트 캐시를 그대로 재사용한다 (`cosmos-policy/SETUP.md` 참조).

## 이 서버(OASYS)의 현재 상태

2026-09-09 기준, 아래는 **이미 받아져 있다**. 다시 받을 필요 없다.

```
~/.cache/huggingface/hub/   합계 24GB
  nvidia--Cosmos-Policy-LIBERO-Predict2-2B    3.7GB
  microsoft--Phi-3.5-vision-instruct          7.8GB
  microsoft--Phi-4-multimodal-instruct         12GB
  physical-intelligence--fast                 724KB
```

clone 한 저장소 안에 모델이 안 보이는 건 정상이다. 캐시에 있고, 코드가 거기서 찾아 쓴다.

## 관련 문서

- `docs/VENDORED.md` — cosmos-policy 저장소 자체를 받는 법
- `cosmos-policy/LIBERO.md` — LIBERO 학습/평가 전체 명령
- `cosmos-policy/SETUP.md` — Docker 기반 실행 환경
