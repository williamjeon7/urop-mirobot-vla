# W10 Cosmos Policy 파인튜닝 완료 기록

> **기록** · 확인 2026-11-06 · 기준 `w10_mirobot_l01_l30_follow_4000` 학습 로그·저장 체크포인트
> Mirobot 실물 demonstration 90개로 수행한 Cosmos Policy 파인튜닝의 완료 근거, 학습 조건, 산출물과 평가 범위.

## 1. 완료 결과

**4,000 optimizer update를 모두 수행하고 마지막 체크포인트를 저장한 뒤 정상 종료했다.** 완료 시각은 **2026-11-05 20:36:58 (한국 시간)**이다. 11/06에 종료 로그, 저장 파일, 마지막 체크포인트 포인터와 학습 프로세스 종료를 확인했다.

| 항목 | 확인 결과 |
| --- | --- |
| 완료 update | 4,000 / 4,000 |
| 훈련 시작 로그 | 2026-11-05 13:58:39 KST |
| 완료 로그 | 2026-11-05 20:36:58 KST |
| 위 두 로그 사이 시간 | 6시간 38분 19초, 중간·최종 체크포인트 저장 포함 |
| 마지막 로그의 배치 loss | `0.0549` |
| 마지막 체크포인트 | `iter_000004000` |
| 정상 종료 메시지 | `Done with training.` |
| 검사한 실패 메시지 | Python traceback, CUDA out of memory, ChildFailedError 없음 |
| 프로세스·GPU | 해당 학습 프로세스 종료, GPU 메모리 반환 확인 |

위 완료 판정은 학습 실행과 저장의 완료를 뜻한다. 오프라인 예측 성능이나 실제 로봇의 집기 성공률은 아직 측정하지 않았다.

## 2. 학습 조건

| 항목 | 실제 실행 설정 |
| --- | --- |
| job 이름 | `w10_mirobot_l01_l30_follow_4000` |
| 초기 가중치 | `Cosmos-Policy-LIBERO-Predict2-2B.pt` |
| 학습 데이터 | L01–L30 × 빨강·초록·파랑, 에피소드 90개, 27,820 timestep |
| 지시문 | `pick up the blue/green/red block on the table`의 세 문장 |
| 입력 | 손목 RGB + proprio + 지시문 T5 임베딩 |
| action 라벨 | 기존 `follow` 방식, 시뮬 Panda 기준 OSC_POSE |
| GPU | RTX 4090 2개, 물리 장치 2·3번 |
| batch size / GPU | 1 |
| gradient accumulation | 8 |
| 유효 batch size | optimizer update당 16개 샘플 |
| 학습률 / update 수 | `1e-5` / 4,000 |
| 저장 간격 | 1,000 update |
| 관측 설정 | `wrist_only`, `state_t=7`, 조건 프레임 3, `chunk_duration=25` |

초기 LIBERO 가중치를 읽을 때 `missing_keys=[]`, `unexpected_keys=[]`, `incorrect_shapes=[]`를 확인했다. 이번 실행은 해당 가중치에서 새 optimizer 상태로 파인튜닝한 것이며, 이전 학습 상태를 이어 받은 실행은 아니다.

원본 실행 설정은 아래 `config.yaml`, 데이터 및 명령의 설명은 [학습 안내](TRAINING.md)와 [실험 계획](MIROBOT_EXPERIMENT.md)을 참고한다.

## 3. 저장 위치와 체크포인트

서버 저장소 루트는 `~/UROP`다. 아래 경로는 이 루트를 기준으로 한다.

```text
cosmos-policy/W10/datasets/real/mirobot_l01_l30/processed/
cosmos-policy/W10/runs/real/cosmos_policy/w9_mirobot/
├── w10_mirobot_l01_l30_follow_4000.log
└── w10_mirobot_l01_l30_follow_4000/
    ├── config.yaml
    └── checkpoints/
        ├── latest_checkpoint.txt
        ├── iter_000001000/
        ├── iter_000002000/
        ├── iter_000003000/
        └── iter_000004000/
```

| update | 저장 완료 시각, 2026-11-05 KST | 디렉터리 전체 크기 |
| --- | --- | --- |
| 1,000 | 15:38:07 | 약 10.94 GiB |
| 2,000 | 17:21:33 | 약 10.94 GiB |
| 3,000 | 18:59:04 | 약 10.94 GiB |
| 4,000 | 20:36:58 | 약 10.94 GiB |

네 체크포인트 각각에 `model/`, `optim/`, `scheduler/`, `trainer/`의 DCP 파일과 메타데이터가 있다. `latest_checkpoint.txt`의 내용은 `iter_000004000`이다. 최종 `model/`의 두 가중치 조각과 메타데이터도 확인했다. 이 확인은 저장 성공 로그와 파일 존재 검사이며, 추론 모델로 실제 로딩하는 검사는 별도다.

학습 산출물과 원본 로그는 서버에 보관한다. `cosmos-policy/` 아래의 체크포인트·대용량 데이터는 프로젝트 Git에 포함하지 않는다.

## 4. 완료 근거와 loss 해석

원본 로그의 종료 구간은 다음과 같다. 저장 경로는 가독성을 위해 끝부분만 표시했다.

```text
Saving last checkpoint file iter_000004000
[11-05 20:36:58] Saved checkpoint to .../checkpoints/iter_000004000
[11-05 20:36:58] 4000 : iter_speed 25.34 seconds per iteration | Loss: 0.0549
[11-05 20:36:58] Done with training.
```

마지막 배치 loss `0.0549`는 전체 데이터의 평균이나 검증 loss가 아니다. 3,805–4,000 update에서 5 update마다 기록된 배치 loss 40개를 산술평균하면 **0.0992**다. 이 값 역시 로그에 남은 배치 값의 요약이며, 별도로 수행한 평가 결과는 아니다.

일반 학습 구간의 로그 속도는 대략 5.8초/update였다. 마지막 `25.34초/update`에는 체크포인트 저장 시간이 포함되어 있으므로 일반 학습 속도로 해석하지 않는다. 학습 loss만으로 일반화 성능이나 실물 집기 성공을 판정하지 않는다.

## 5. 다음 평가

2026-11-06 후속: 최종 가중치 통합·687개 키의 엄격 로드·실제 GPU 추론과 `follow` 실행 루프를 확인했다.
실물 연결은 [DEPLOY_MIROBOT.md](DEPLOY_MIROBOT.md)의 순서대로 진행한다. 실제 집기 평가는 아직 수행하지 않았다.

1. 저장된 체크포인트를 추론용 `model_consolidated.pt`로 합치고 GPU에서 실제 로딩을 검증한다.
2. 동일한 HDF5·정규화 통계·T5 임베딩으로 예측 action과 추론 시간을 평가한다.
3. 현재 `follow` 라벨 규약에 맞는 동작 번역과 실물 실행 루프를 구현·검증한다.
4. 학습 배치와 다른 배치에서 언어 준수율과 지시 색 집기 성공률을 측정한다.

평가 명령과 판정·기록 양식은 [실험 계획 3–6절](MIROBOT_EXPERIMENT.md#3-실험-방법)에 있다. 학습 데이터 90개를 모두 사용했으므로 같은 HDF5의 오프라인 평가는 학습 데이터 재현 정도로 보고한다. 실물 실행 루프와 실물 성공률은 이번 학습 완료 확인에 포함되지 않는다.
