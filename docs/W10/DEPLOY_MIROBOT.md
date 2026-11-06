# 학습한 W10 모델을 실제 Mirobot에서 실행하기

> **절차** · 확인 2026-11-06 · 기준 `w10_mirobot_l01_l30_follow_4000/iter_000004000`
> 로봇 노트북과 GPU 서버를 연결하고, 학습한 모델의 명령을 확인한 뒤 실제로 실행하는 순서.

## 1. 어디서 무엇을 실행하나

노트북에 Mirobot과 D405를 USB로 연결한다. 모델은 GPU 서버에 두며 노트북으로 복사하지 않는다.

```text
노트북: Mirobot + D405 → robot.policy_bridge :8891
                                ↑ SSH 역터널
서버: server.run_policy → 실시간 관측 → Cosmos → follow 변환 → 로봇 명령
```

다음 세 터미널을 유지한다.

| 창 | 위치 | 역할 |
| --- | --- | --- |
| A | Windows 로봇 노트북 PowerShell | 장치 준비, 이후 브리지 실행 |
| B | Windows 로봇 노트북 PowerShell | SSH 역터널 유지 |
| C | GPU 서버 Linux | 모델 실행 |

기본 설정은 다음과 같다. COM 포트만 장치 목록에 맞게 바꾼다.

| 항목 | 설정 |
| --- | --- |
| 서버 저장소 | `~/UROP` |
| GPU | 물리 GPU 2번, 4090 한 장 |
| 로봇 포트 | `COM3`, 115200 baud |
| D405 | `262422272124`, RGB 640×480, 30 fps |
| 색 보정·좌표 기준 | `Mirobot_data/W10/L01_red/`의 원본 파일 |
| 명령 | `--color red`, `green`, `blue` |
| 모델 | 마지막 4,000-step 체크포인트 |

카메라 장착 방향과 작업대·공구는 시연 수집 때 조건에 맞춘다. 빨강·초록·파랑 블록을 놓고 지시 색을 고른다.
기존 녹화 프로그램·시리얼 브리지·카메라 뷰어는 닫는다. 같은 USB 장치를 두 프로그램이 동시에 열면 실패한다.

## 2. 처음 한 번: 노트북 실행 파일 가져오기

서버에서 준비된 ZIP은 `dist/mirobot-policy-robot.zip`이다. 가중치와 녹화 영상은 들어 있지 않다.
코드를 수정한 뒤 ZIP을 다시 만들려면 **창 C**에서 실행한다.

```bash
cd ~/UROP
cosmos-policy/.venv/bin/python -m tools.package_policy_robot
```

**창 A**, 노트북 PowerShell에서 ZIP을 받고 압축을 푼다. 서버 접속 주소는 기존 실험용 설정이다.
현재 SSH 접속에 다른 주소를 쓰고 있다면 아래 `<SERVER_IP>`, `100`을 그 주소와 포트로 바꾼다.

```powershell
cd $HOME
scp -P 100 <USER>@<SERVER_IP>:~/UROP/dist/mirobot-policy-robot.zip .
Expand-Archive .\mirobot-policy-robot.zip -DestinationPath . -Force
cd .\mirobot-policy
py -3.10 -m venv urop
.\urop\Scripts\python.exe -m pip install -r requirements/policy_robot.txt
.\urop\Scripts\python.exe -m pip install -e .
```

이후 노트북 명령은 `cd $HOME\mirobot-policy`에서 실행한다. 가상환경 활성화 없이 Python 경로를 직접 쓰므로 PowerShell 실행 정책 설정은 필요 없다.
이미 실행 중인 브리지가 있다면 먼저 종료하고 새 ZIP을 푼다. `urop` 환경이 이미 있으면 생성·설치 단계는 생략할 수 있다.

## 3. 로봇 없이 먼저 모델 확인 — 창 C

GPU 서버에서 실행한다. 저장된 빨강 시연의 첫 관측을 입력하고 4개 목표 명령을 출력한다. 로봇에는 연결하지 않는다.

```bash
cd ~/UROP
bash tools/run_mirobot_policy.sh --offline-smoke --color red --max-steps 4
```

모델 초기화 중 로그가 많이 나온다. 정상 완료 기준은 다음과 같다.

```text
Loaded trained policy: 687 keys, no missing net.* or unexpected keys
Query 0: ... s, actions (16, 7)
preview: G0 X... Y... Z... A... B... C... ; M4 S40
Completed 4 steps (offline_smoke); log: ...
```

이 검사는 **가중치 로드·추론·목표 변환**을 확인한다. 실제 집기 성공을 판정하는 검사는 아니다.

GPU를 바꾸려면 다음과 같이 실행한다. 이미 `CUDA_VISIBLE_DEVICES`가 설정되어 있으면 그 값을 우선 사용한다.

```bash
CUDA_VISIBLE_DEVICES=0 bash tools/run_mirobot_policy.sh --offline-smoke --color red --max-steps 4
```

## 4. USB 장치 확인과 시작 자세 준비 — 창 A

```powershell
cd $HOME\mirobot-policy
.\urop\Scripts\python.exe -m docs.W9.d405.devices --check
```

`robot_found: true`, `camera_found: true`를 확인한다. 다른 COM 포트이면 이후 모든 `COM3`을 실제 포트로 바꾼다.
장치 확인 단계에서는 로봇을 움직이지 않는다.

다음 명령은 **실제로 호밍하고 집게를 연 뒤 시작 자세로 이동한다.** 로봇 주변을 비우고 실행한다.

```powershell
.\urop\Scripts\python.exe -m tools.run_gcode trajectories/policy_start.gcode --port COM3 --home --auto
```

목표는 플랜지 `X198.67 Y0 Z230.72 A0 B0 C0`, 집게 `M4 S40`이다.
이 준비 명령이 정상 종료한 뒤 브리지를 띄운다. 브리지는 시작할 때 호밍하거나 집게를 움직이지 않으며, 초기 집게 상태가 열림이라고 가정한다.

## 5. 브리지 시작 — 창 A

먼저 관측만 허용하는 모드로 실행한다.

```powershell
.\urop\Scripts\python.exe -m robot.policy_bridge --serial-port COM3
```

HTTP 포트 `8891`에서 기다리는 로그가 나오면 이 창을 유지한다.
이 브리지 하나가 D405 RGB와 로봇 `?` 상태 조회를 함께 담당한다. 기존 `robot.serial_bridge`와 `robot.camera_bridge`는 필요 없다.

카메라 색 보정 프로필에 저장된 노출·화이트밸런스·게인 등을 재현하고, 서버가 원본 RGB에 색 보정을 한 번 적용한다.
프로필과 카메라가 다르거나 설정을 재현하지 못하면 시작을 중단한다.

## 6. 역터널 연결 — 창 B

노트북의 **새 PowerShell 창**에서 실행한다.

```powershell
ssh -p <SSH_PORT> -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -R 8891:127.0.0.1:8891 <USER>@<SERVER_IP>
```

접속 후 화면에 출력이 없어도 정상이다. 이 창을 닫지 않는다.
이제 서버의 `127.0.0.1:8891`이 노트북 브리지로 연결된다.
`remote port forwarding failed`가 나오면 서버 8891 포트를 쓰는 이전 터널을 종료한 뒤 다시 연결한다.

## 7. 실시간 관측과 명령 미리보기 — 창 C

먼저 카메라·로봇 상태 연결만 확인한다. 모델은 로드하지 않는다.

```bash
cd ~/UROP
bash tools/run_mirobot_policy.sh --bridge-check
```

`cart6` 6개 값, `state: Idle`, 카메라 정보와 다음 메시지를 확인한다.

```text
Bridge, latest RGB, Cartesian state and preprocessing: OK (no commands sent)
```

실시간 카메라 관측을 모델에 넣고 목표 명령을 확인한다.

```bash
bash tools/run_mirobot_policy.sh --color red --max-steps 4
```

`preview:` 4줄이 나오며 로봇은 움직이지 않는다. 이 모드는 관측 한 번으로 예측한 chunk만 미리 보고 종료한다.
저장된 `wrist_0000.png`에서 학습 때와 같은 방향·색의 손목 영상인지 확인한다.

## 8. 실제로 4번만 움직이기

**창 A**의 브리지를 `Ctrl+C`로 종료한 뒤 실행 허용 모드로 다시 띄운다. **창 B의 터널은 유지한다.**

```powershell
.\urop\Scripts\python.exe -m robot.policy_bridge --serial-port COM3 --execute
```

**창 C**에서 실행한다.

```bash
bash tools/run_mirobot_policy.sh --color red --execute --max-steps 4
```

`send:`가 실제 전송이다. 기본은 **action 1개 실행 → 도착 확인 → 새 관측으로 다시 추론**이다.
4번 실행하면 종료한다. 모델은 매번 16개를 예측하지만 이 설정에서는 첫 action만 사용한다.
추론과 통신·도착 대기 시간이 추가되므로 학습 시연의 20 Hz 속도로 움직이지 않는다.

기본 제한은 플랜지 Z 66 mm 이상, 수평 반경 280 mm 이내, 자세각 ±30°, 한 번 이동 10 mm·5° 이내다.
실측/가상 상태 차이가 12 mm를 넘거나 로봇이 추론 중 이동하면 중단한다. 범위를 넘는 action을 임의로 줄여 보내지 않는다.

한 번에 여러 action을 실행하려면 미리보기와 짧은 실행을 확인한 다음 다음처럼 지정한다.

```bash
bash tools/run_mirobot_policy.sh --color red --execute --max-steps 80 --open-loop-steps 4
```

`--open-loop-steps`는 1–16이다. 각 목표의 도착을 기다리는 구성은 동일하다. 이 속도에서 집기가 되는지는 실물에서 확인해야 한다.
실행 종료 후 다른 색을 시험하려면 **창 A의 브리지 종료 → 4절의 시작 자세 준비 → 브리지 `--execute` 재시작 → 다음 명령** 순서로 반복한다.

```bash
bash tools/run_mirobot_policy.sh --color green --execute --max-steps 80
bash tools/run_mirobot_policy.sh --color blue --execute --max-steps 80
```

각 줄은 별도 시행이다. 이전 시행이 끝난 자세에서 다음 시행을 바로 시작하지 않는다.

## 9. 기록과 중단

매 실행의 기록 위치가 `Run log:`로 출력된다.

```text
cosmos-policy/W10/evaluations/real/<시각>_<색>_<모드>/
├── events.jsonl       관측·예측 action·목표·응답·중단 사유
├── wrist_0000.png     모델에 넣은 색 보정된 손목 영상
└── summary.json       완료/실패, 모드, 실행 수, 모델 경로
```

다른 위치에 저장하려면 `--log-dir <새 폴더>`를 준다. 기존 폴더를 덮어쓰지 않는다.
시행이 끝나도 자동으로 홈으로 가거나 집게를 열지 않는다. 잡은 블록은 상태를 확인하고 정리한다.

창 C에서 `Ctrl+C`를 누르면 다음 명령 전송을 중단한다. 이미 전송된 이동의 취소는 보장하지 않는다.
즉시 물리적 정지가 필요하면 로봇의 비상정지를 사용한다.
통신 오류 후에는 실제 도착 여부가 불확실할 수 있어 명령을 자동 재전송하지 않는다. 로봇 상태를 확인하고 브리지를 재시작한다.

## 10. 문제가 생기면

| 증상 | 확인할 것 |
| --- | --- |
| `Cannot reach bridge` / connection refused | 창 A 브리지와 창 B 터널이 살아 있는지 확인 |
| `Bridge is read-only` | 창 A를 `--execute`로 다시 시작하고, 창 C에도 `--execute` 추가 |
| COM 포트 access denied | 녹화 프로그램·기존 브리지·시리얼 모니터 종료 |
| `Expected one D405` | USB 연결, 카메라 사용 프로그램, 장치 serial 확인 |
| `colour-profile camera setting` | 수집 때 D405·프로필을 사용 중인지 확인; 자동 설정으로 우회하지 않음 |
| `Robot must be Idle` / Locked / A106 | 브리지 종료 후 4절의 시작 자세 준비를 다시 실행 |
| `stale or unsynchronized` | 터널 지연·USB 부하 확인; RGB는 PNG라 느린 망에서 지연될 수 있음 |
| `Target step too large` / Z floor / tracking gap | 기록된 입력 영상·시작 자세·예측 action 확인; 제한을 늘려 우회하지 않고 원인 확인 |
| CUDA out of memory | `nvidia-smi`에서 빈 GPU 확인 후 `CUDA_VISIBLE_DEVICES=0` 등으로 변경 |
| Python/모듈 import 오류 | 서버는 `cosmos-policy/.venv`, 노트북은 ZIP의 `urop` Python 3.10 사용 |

서버와 노트북이 같은 망에 있으면 터널 대신 브리지를 `--listen-host 0.0.0.0`으로 열고,
서버 명령에 `--bridge-url http://<노트북IP>:8891`을 추가할 수 있다. 기본 절차는 로컬 바인딩과 SSH 터널을 사용한다.

## 11. 현재 검증 범위와 파일

이 모델은 `follow` 라벨로 학습했다. 실행 시 가상 Panda를 함께 유지해 **시뮬레이션을 한 스텝 진행하기 전 컨트롤러 목표**를 Mirobot 명령으로 바꾼다.
실물 현재 자세에 예측 action을 누적해서 더하는 방식은 사용하지 않는다.

2026-11-06에 확인한 결과는 다음과 같다.

| 검사 | 결과 |
| --- | --- |
| 최종 가중치 실제 GPU 로드 | 687개 키·shape 엄격 검사 통과 |
| 녹화 관측으로 실제 추론 | 유한한 `(16, 7)` action, 첫 추론 1.39초, 목표 4개 미리보기 완료 |
| `follow` 역변환 | L01_red의 저장 action 376개 → 다음 실측 목표 위치 차이 최대 약 `5.4e-7 mm` |
| 프로젝트 자동 테스트 | 157 passed, 8 skipped, 14 subtests passed |
| 실제 로봇·D405 연결과 집기 | 아직 수행하지 않음; 위 절차로 노트북에서 확인 |

GPU smoke 기록은 `cosmos-policy/W10/evaluations/real/20261106_134336_039844_red_offline_smoke/`에 있다.
이 시간은 녹화 관측 한 번의 실측값이며 모델 초기화·통신·로봇 이동 시간은 제외한다.
현재 Cosmos의 손목 전용 반환값 초기화 오류는 `server/policy_runtime.py`의 호환 처리에서 보정하며, 외부 저장소 파일은 수정하지 않는다.

프로젝트 테스트를 다시 실행하려면 서버에서 다음을 사용한다.

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MUJOCO_GL=egl \
  cosmos-policy/.venv/bin/python -m pytest -q tests
```

저장소 전체에 `pytest`를 실행하면 외부 Cosmos 테스트와 예전 하드웨어·그래픽 실험도 수집된다.
그 전체 수집은 별도 제한 모델 권한과 그래픽 설정 문제로 실패했으므로, 위 통과 수는 `tests/` 범위다.

| 파일 | 역할 |
| --- | --- |
| `robot/policy_bridge.py` | D405 원본 RGB·실측 상태 전송, 제한을 확인한 명령 실행 |
| `server/policy_client.py` | 브리지 접속·관측 신선도 검사·응답 확인 |
| `server/policy_runtime.py` | 학습 설정·정규화·T5를 맞춘 최종 가중치 로드와 추론 |
| `server/follow_translator.py` | 학습 라벨과 같은 가상 Panda 동역학을 통한 목표 변환 |
| `server/run_policy.py` | 관측·추론·변환·실행·기록 루프 |
| `tools/run_mirobot_policy.sh` | 서버 Python/GPU/오프라인 환경 기본값 |
| `tools/package_policy_robot.py` | 노트북 전송 ZIP 생성 |
| `trajectories/policy_start.gcode` | 시행 전 시작 자세·집게 열림 준비 |

학습 완료 근거는 [TRAINING_RESULT.md](TRAINING_RESULT.md), 기존 좌표 검증은 [POLICY_RUN.md](POLICY_RUN.md), 실험 판정 기준은 [MIROBOT_EXPERIMENT.md](MIROBOT_EXPERIMENT.md)를 참고한다.
