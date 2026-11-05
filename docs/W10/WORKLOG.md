# W10 — 작업 기록

> **기록** · 확인 2026-11-06
> W10 에 한 작업의 시간 순서 목차. 항목마다 왜 · 한 것 · 대표 결과 · 자세한 문서 링크. 적는 규칙은 [../README.md](../README.md) "새 문서를 만들 때" 5절.

| 주제 문서 | 다루는 것 |
| --- | --- |
| [POLICY_RUN.md](POLICY_RUN.md) | 학습한 정책을 실물에서 돌리는 도구 — 관측·명령 계산 검사, action 라벨 방식(결정 대기), 오프라인 평가 |
| [MIROBOT_EXPERIMENT.md](MIROBOT_EXPERIMENT.md) | Mirobot demonstration 학습과 실물 실행을 논문 실험 절 형식으로 정리한 실험 계획 |
| [HDF5_ALIGNMENT.md](HDF5_ALIGNMENT.md) | (노트북) 녹화 60개의 정렬 기준과 미통과 5개 |
| [DATA_CHECK.md](DATA_CHECK.md) | 녹화 → Cosmos 학습 데이터 점검, 새 녹화 때 다시 돌리는 명령 |
| [TRAINING.md](TRAINING.md) | 이 데이터로 학습하고 스텝별·색별로 비교하는 순서 |
| [TRAINING_RESULT.md](TRAINING_RESULT.md) | 시연 90개·4,000 update 파인튜닝의 완료 근거·실행 조건·저장 산출물 |

---

## 11/03 1. 11/02 미팅 기록과 이번 주 action plan

- **왜** — 교수님 의견(Mirobot 데이터만으로 먼저 파인튜닝, 정책은 Cosmos 가 아니어도 되니 end-to-end 먼저)을 할 일로 바꿔야 했다
- **한 것** — 미팅 기록과 action plan, 로봇 노트북에 줄 녹화 시작 프롬프트(색마다 30개, 배치 좌표 기록, `?` 원문 저장)
- **결과** — 사용자 결정: 실물은 색마다 30개를 처음부터 다시, 세 색이 모이면 한 번에 학습, 담당 칸은 비움
- **문서** — [../meetings/2026-11-2.md](../meetings/2026-11-2.md)

## 11/03 2. 정책 실행 도구 — 관측·명령 계산을 녹화로 검사

- **왜** — 학습은 끝까지 갔지만 학습한 정책을 실물에서 돌려 볼 도구가 없었다 ([../W9/FINETUNE.md](../W9/FINETUNE.md) 7절)
- **한 것** — `common/policy_io.py`(action → Mirobot 목표), `tools/policy_obs.py`(프레임·`?` → 정책 입력), `tools/check_policy_io.py`, 테스트 3개
- **결과** — 영상 픽셀 차 0(4,383칸), 역변환 0 mm. 그런데 학습 action 을 실물에 더하면 16개 묶음 끝이 평균 44 mm 어긋난다 — action 라벨 방식 결정 대기(A·B·C, 제안 C)
- **문서** — [POLICY_RUN.md](POLICY_RUN.md) 1–3절

## 11/03 3. 오프라인 평가 스크립트, 체크포인트 합치기

- **왜** — 실물 전에 정책이 라벨을 따라가는지, 한 번 묻는 데 몇 초인지 알아야 실행 루프를 설계할 수 있다
- **한 것** — `tools/eval_offline.py`. 학습 체크포인트(DCP 조각)를 추론 로더가 읽는 한 파일로 합치는 단계 포함. 11/05 색별 요약 추가
- **결과** — 1차 체크포인트 합침(3.91 GB). **GPU 첫 실행 대기**
- **문서** — [POLICY_RUN.md](POLICY_RUN.md) 4절

## 11/04 (노트북) 녹화 60개와 정렬 점검

- **왜** — 이번 주 목표 90개 중 1차 수집
- **한 것** — 배치 L01–L20 × 세 색, `Mirobot_data/W10/` 에 저장, 70 ms 기준 정렬
- **결과** — 55개 통과, 5개 미통과(L09_blue · L10_blue 카메라 초당 4장, L13_red · L13_blue · L19_green 한 칸이 70 ms 를 넘음)
- **문서** — [HDF5_ALIGNMENT.md](HDF5_ALIGNMENT.md), [../../Mirobot_data/README.md](../../Mirobot_data/README.md)

## 11/05 4. 학습 데이터 점검 — Cosmos 에 바로 넣을 수 있는가

- **왜** — 이번 주 계획 11/5 "수집한 데이터를 Cosmos Policy 에 바로 넣을 수 있는 상태인지 확인"
- **한 것** — `tools/inventory_recordings.py`(녹화 점검), `tools/build_real_dataset.py`(점검 → 색별 변환 → 구조 검사 한 번에). 55개 HDF5, Cosmos 로더·학습 설정 `--dryrun`
- **결과** — **55개 · 17,320칸 `training_ready`** (`data/hdf5_w10/`). 변환기가 적는 허용치 기록 40 → 실제 70 ms 로 고침. 사용자 결정: 미통과 5개는 90개를 다 찍은 뒤 다시 찍는다
- **문서** — [DATA_CHECK.md](DATA_CHECK.md)

## 11/05 5. 학습 진행 안내

- **왜** — 데이터가 모이면 바로 학습하고 스텝별·색별로 비교할 수 있게 (사용자 요청)
- **한 것** — 정할 것 세 가지(라벨 방식, 평가용으로 뺄 배치, step 수), 데이터 최신화, 학습 명령, 비교 방법과 양식
- **결과** — 오프라인 비교는 지금 도구로 된다. **실물 성공률은 실행 루프가 있어야** 잴 수 있다
- **문서** — [TRAINING.md](TRAINING.md)

## 11/05 6. Cosmos Policy를 공용 자원과 주차별 작업으로 정리

- **왜** — 다음 주 W11·W12 및 실물·시뮬·혼합 데이터셋을 같은 규칙으로 추가하기 위해 (사용자 요청, 지금은 W10만)
- **한 것** — 공용 가중치 `cosmos-policy/models/`, 원래 문서 `docs/upstream/`, 과거 설정·영상 `archive/`, W10의 `datasets`·`configs`·`runs`·`evaluations`를 실물·시뮬·혼합으로 구분. 원본 90개는 링크로 연결
- **결과** — 원본 90개·27,820칸 모두 ready. 공용 모델 7개의 기본·새 캐시 오프라인 조회 통과. **데이터 변환과 학습은 실행하지 않음**, W11·W12 폴더는 아직 없음
- **문서** — 로컬 [구조 안내](../../cosmos-policy/README.md), [학습 방법](../../cosmos-policy/W10/TRAINING.md)

## 11/05 7. Mirobot 학습·실물 실행 실험 계획

- **왜** — Mirobot demonstration을 Cosmos Policy에 학습시키고 실제로 실행하는 과정을 논문 실험 절 형식으로 남기기 위해 (사용자 요청)
- **한 것** — 실험 목적·장비·데이터·학습 조건, 체크포인트별 오프라인 평가 명령, 실물 실행의 잔여 구현, 평가 프로토콜·지표·결과표 작성
- **결과** — 현재 `follow` 모델을 기준으로 계획을 정리. 측정 전 결과는 빈칸으로 두고, 새 평가 횟수·판정 수치는 제안으로 명시. 문서 작성 과정에서 학습·GPU 추론·로봇 동작을 실행하지 않음
- **문서** — [MIROBOT_EXPERIMENT.md](MIROBOT_EXPERIMENT.md)

## 11/06 8. 파인튜닝 완료 확인

- **왜** — 학습 완료 여부와 저장된 결과를 확인하고 Markdown 기록으로 남기기 위해 (사용자 요청)
- **한 것** — 마지막 학습 로그, 네 체크포인트의 파일·메타데이터, latest 포인터, 해당 프로세스 종료와 GPU 메모리 반환 확인
- **결과** — 11/05 20:36:58 KST에 4,000 update 정상 완료. 마지막 배치 loss 0.0549. 오프라인 GPU 추론·실물 성공률은 미측정
- **문서** — [TRAINING_RESULT.md](TRAINING_RESULT.md)
