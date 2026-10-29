# D405 설치 → 녹화 → 0.05초 타임스텝 → Cosmos Policy 학습

**가지고 계신 Calibrite ColorChecker Classic Mini와 `inverse_kinematics.py`를 사용하는 주 절차는 [COLORCHECKER_MINI.md](COLORCHECKER_MINI.md)입니다.** 이 문서는 설치·데이터 변환 전체를 설명합니다.
처음에는 **1~3번으로 카메라만 확인**하세요. 실물 학습 데이터는 4번부터 만듭니다.
**1~5절은 [로컬: Windows PowerShell], 6~8절은 [서버: OASYS Bash]**입니다. 로컬 저장소는 `C:\mirobot-vla`(실제 경로에 맞춰 변경), 서버 저장소는 `~/UROP`입니다. 6절의 전송 명령만 로컬 PowerShell에서 실행합니다. 새 코드·환경·녹화 결과는 `docs/W9` 안에 둡니다.

## 0. 무엇을 설치하고 만들었나

| 위치 | 역할 |
| --- | --- |
| `.venv/` | Windows Python 3.10 수집·보정 환경. 서버 환경과 별도 |
| `d405/setup.ps1` | Windows 노트북의 Python 패키지 설치·D405 조회 |
| `d405/setup.sh` | OASYS의 보조 검사 환경 설치. 현재 연결 구성에서 카메라 수집은 로컬에서 수행 |
| `d405/terminal_keyboard.py` | SSH 터미널 입력. 관리자 권한 없이 동작 키·F8/F9 처리 |
| `d405/capture.py` | D405 RGB 녹화. 선택적으로 G-code 실행·로봇 상태 기록까지 |
| `d405/robot_capture.py` | 명령 순서를 보존하며 이동·그리퍼 동작 중 로봇 상태를 폴링 |
| `d405/teleop.py` | 기존 inverse_kinematics.py에 로봇 포트·상태 기록·F8/F9 연결. 현재 수집은 Windows에서 실행 |
| `d405/color_calibration.py` | Classic Mini 24패치 촬영에서 RGB 색 보정 프로필 생성·적용 |
| `d405/preview.py` | 녹화된 PNG를 확인용 MP4로 변환 |
| `d405/prepare.py` | 프레임·로봇 상태를 0.05초 격자로 맞춤 |
| `d405/export_hdf5.py` | 서버에서 Panda를 따라가게 하며 외부 영상·action 생성, HDF5 저장 |
| `d405/check_dataset.py` | HDF5 키·모양·값·지시문 검사 |
| `d405/make_t5.py` | 서버에서 실제 지시문의 T5 임베딩 생성 |
| `d405/train.py` | LIBERO Policy 체크포인트 파인튜닝 명령 생성·실행 |
| `d405/test_pipeline.py` | 장비 없이 시간 정렬·RGB·HDF5 등 검증 |
| `data/` | 원본 녹화·변환 결과. Git 제외 |

기존 `common/` 좌표·자세 변환과 `docs/W6/rgb_blocks/` 장면을 가져다 씁니다. 이 저장소 전체가 필요하며 W9 폴더만 따로 복사해서는 실행되지 않습니다.

**학습하려는 모델은 `nvidia/Cosmos-Policy-LIBERO-Predict2-2B`입니다.** 일반 영상 생성 모델용 MP4 학습과 입력 형식이 다릅니다. 영상과 함께 로봇 상태·action·지시문이 필요합니다.

## 1. 설치 — [로컬: Windows PowerShell]

Windows 노트북에 Python 3.10과 최신 저장소 코드를 준비한 뒤 로컬 PowerShell에서 실행합니다.

```powershell
cd C:\mirobot-vla
powershell -ExecutionPolicy Bypass -File docs/W9/d405/setup.ps1
```

스크립트는 W9 가상환경에 패키지를 설치하고 카메라만 조회합니다. 로봇 이동 명령을 보내지 않습니다. D405와 Mirobot USB는 Windows 노트북에 연결합니다.

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --list
docs/W9/.venv/Scripts/python.exe -m serial.tools.list_ports -v
```

D405는 RealSense USB 장치이며 COM 포트를 쓰지 않습니다. Mirobot은 실제 `COM3` 등의 시리얼 포트를 확인해 `--port`로 지정합니다. Windows에서 장치가 조회되지 않으면 USB 연결을 확인하세요. 현재 OASYS에 D405가 없는 것은 정상이며 SSH가 노트북 USB를 자동 전달하지 않습니다.

### Viewer — [로컬: Windows PowerShell]

필요하면 `powershell -ExecutionPolicy Bypass -File docs/W9/d405/install_viewer.ps1`로 Windows Viewer를 준비합니다. 녹화 전에는 Viewer를 닫으세요. Python과 동시에 카메라를 열 수 없습니다.

## 2. 카메라만 10초 녹화 — [로컬: Windows PowerShell]

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --out docs/W9/data/raw/camera_test_001 --seconds 10 --preview
```

노트북에서 미리보기를 띄우고 10초간 녹화한 뒤 끝납니다. 미리보기 창의 `Esc`는 중단이며 완료된 데이터로 표시되지 않습니다. 같은 출력 폴더는 덮어쓰지 않으므로 다음 녹화에서는 `002`처럼 이름을 바꾸세요.

기본값은 **RGB 640×480, 요청 30fps**입니다. 실제 프레임 간격은 조명·노출·USB·저장 속도에 따라 달라집니다. 처음 45프레임 동안 자동 노출·화이트밸런스를 안정화하고, 지원하는 설정은 그 값으로 고정합니다.

저장 구조:

```text
docs/W9/data/raw/camera_test_001/
  metadata.json       카메라 설정, 내부 파라미터, 완료 여부, 패키지 버전
  frames.jsonl        각 PNG의 시각, 장치 시각, 프레임 번호
  rgb/00000000.png    손목 RGB 원본
  rgb/00000001.png
```

**MP4만 남기지 마세요.** 학습에서 어느 프레임이 어느 자세와 짝인지 알려면 `frames.jsonl`이 필요합니다. 이 수집기는 PNG와 기록 파일을 원본으로 사용합니다. 깊이 영상은 현재 LIBERO RGB 로더에 들어가지 않아 수집하지 않습니다.

## 3. 녹화 영상 확인 — [로컬: Windows PowerShell]

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.preview docs/W9/data/raw/camera_test_001
```

같은 폴더에 `review.mp4`가 생깁니다. 노트북의 영상 플레이어로 확인하세요. 이 MP4는 중앙 프레임 간격으로 재생하는 **확인용**이며 시간 정렬 원본은 PNG+JSONL입니다.

확인할 것: 집게와 대상 블록이 보이는지, 빛 반사가 심하지 않은지, 손목 카메라가 흔들리거나 장착 위치가 바뀌지 않는지. 학습 이미지에는 글자나 프레임 번호를 그리지 않습니다.

## 4. 로봇과 카메라를 함께 기록 — [로컬: Windows PowerShell]

카메라와 로봇은 **Windows 노트북에서 이 프로그램 하나로** 수집합니다. 기존 HTTP 카메라 브리지나 별도 Viewer 녹화는 이 단계에서 사용하지 않습니다.

**이번에 사용할 방식은 기존 `robot/inverse_kinematics.py`로 직접 조작하는 teleop입니다.** [COLORCHECKER_MINI.md 5번](COLORCHECKER_MINI.md#5-inverse_kinematicspy로-조작하면서-녹화)의 명령으로 실행하세요. 로봇 포트를 `--port`로 지정하고 기존 Windows 키보드 입력으로 조작합니다. F8/F9 사이만 학습 구간으로 표시합니다. 시작·종료 호밍은 기존 코드 동작을 유지합니다.

아래는 필요할 때만 사용하는 **별도의 저장된 G-code 재생 모드**입니다. 직접 조작할 때는 사용하지 않아도 됩니다. 기존 red/seed 2 예시 파일을 검사만 하려면:

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --gcode trajectories/2026_10_11-w6-pickup-red-s2-e5.gcode
```

기본 플랜지 Z 하한은 기존 프로젝트와 같은 66mm입니다. 이 수집기는 G90, M20, 모든 좌표가 적힌 G0, M4 S, G4 P만 받습니다. G4 P는 초 단위로 해석하고 PC에서 대기하며 계속 상태를 기록합니다. 호밍·상대 좌표·임의 명령은 받지 않습니다.

G-code 자동 재생을 원할 때만, 기존 방법으로 로봇 호밍·장착·작업 공간을 준비한 뒤:

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --out docs/W9/data/raw/red_s2_001 --color red --seed 2 --reference docs/W6/poses/pickup-red-s2.jsonl --gcode trajectories/2026_10_11-w6-pickup-red-s2-e5.gcode --port COM3 --initial-s 40 --open-s 40 --closed-s 60 --gripper-seconds 1.0 --execute
```

**바꿔야 하는 값:** `COM3`는 예시이므로 실제 Mirobot COM 포트로 바꿉니다. D405는 시리얼 장치가 아닙니다. `initial-s`는 녹화 전 실제 집게 명령값입니다. `open-s` / `closed-s`는 이 G-code의 열림·잡기 값(예에서는 S40/S60)이며, 사용 중인 집게에서 확인하세요. `gripper-seconds 1.0`도 예시입니다. 영상에서 실제 닫힘 시간을 재서 입력하세요. 측정값이 없으면 정확한 그리퍼 proprio가 아닙니다.

수집기는 waypoint마다 도착을 기다립니다. 기존 `--stream`과 달리 이동 사이의 M4 순서를 보존하고, 이동·집기·대기 중 모두 20Hz를 목표로 `?` 상태를 요청합니다. 실제 속도는 포트 응답에 따라 낮아질 수 있습니다. 이 방식으로 수집한 실물 궤적을 기준으로 나중에 라벨을 만듭니다.

추가 저장 파일:

```text
robot.jsonl         상태(cart = X Y Z A B C), 명령과 전송 시각, 왕복 지연
serial.jsonl        저수준 Probe 기록
source.gcode        실행 파일 또는 teleop에서 사용한 좌표 보정 머리말 파일
reference.jsonl     G-code 생성에 쓴 Panda 기록 원본
```

프레임·로봇 기록의 `t_s`는 한 프로세스의 같은 기준 시각을 사용합니다. **프레임 시각은 PC 수신 시각이며 센서 노출 시각을 정확히 보장하지 않습니다.** 장치 시각·프레임 번호도 보관하므로 누락과 지연을 점검할 수 있습니다. 로봇 응답도 측정·전송 지연이 있습니다.

`Ctrl+C`나 미리보기 `Esc`는 수집을 중단합니다. 이미 보낸 이동을 즉시 취소하는 비상정지 기능은 아닙니다. 실물 수집 중에는 물리 비상정지에 접근할 수 있어야 합니다.

## 5. 0.05초 단위로 묶기 — [로컬: Windows PowerShell]

실물 녹화가 정상적으로 끝나면:

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.prepare docs/W9/data/raw/red_s2_001
```

같은 폴더에 `aligned.npz`, `alignment_report.json`이 생깁니다. 준비 동작을 잘라내려면 `--start 5 --end 25`처럼 **capture 기준 초**로 지정할 수 있습니다. 경계는 카메라·로봇 기록이 겹치는 범위 안으로 제한됩니다.

| 타임스텝 | 손목 영상·proprio | action 목표 |
| --- | --- | --- |
| k=0 | t=시작 시각 | 시작+0.05초 자세 |
| k=1 | 시작+0.05초 | 시작+0.10초 자세 |
| k=2 | 시작+0.10초 | 시작+0.15초 자세 |

즉 **관측을 먼저 저장하고 그다음 action**을 붙입니다. 마지막 자세는 앞선 action의 목표로만 씁니다. 타임스텝마다 MP4를 잘라 만드는 작업은 필요 없습니다.

처리 규칙:

- 이미지: 해당 시각에 가장 가까운 실제 D405 프레임을 고릅니다. 기본 허용 오차 40ms를 넘으면 중단합니다.
- 위치: 실물 Cartesian을 기존 좌표 변환으로 Panda 좌표로 바꾸고 선형 보간합니다.
- 회전: 쿼터니언 SLERP로 보간하므로 179°→−179° 같은 경계를 안전하게 처리합니다.
- 손가락: 기존 B' 규칙의 열림 0.0398m, 잡기 0.0191m를 사용합니다. 명령·측정한 닫힘 시간으로 이어 붙이는 추정값입니다.
- 로봇 상태 공백: 기본 150ms 초과는 거부합니다. 20Hz 미만 기록을 보간해도 새 측정 정보가 생기지는 않습니다.

보고서의 `robot_hz_median`, `max_robot_gap_ms`, `max_frame_error_ms`, `skipped_camera_frame_numbers`를 확인하세요. 20Hz 상태 기록을 우선 목표로 하세요. `--max-state-gap-ms 75`로 더 엄격하게 검사할 수 있습니다.

카메라 수신 지연을 별도 실험으로 측정했다면 `--camera-latency-ms 20`처럼 보정합니다. **20은 설명용 숫자입니다. 측정 없이 넣지 마세요.** 허용 오차는 기본값이며 검증된 로봇 성능 기준이 아닙니다.

## 6. 서버에서 외부 영상·action 생성 → HDF5

**이 절부터 서버 작업입니다.** 먼저 로컬 1~5절을 마치고 `review.mp4`와 `alignment_report.json`을 확인합니다. MP4만 전송하지 말고 원본 PNG·JSONL·metadata·reference·보정 파일을 포함한 폴더 전체를 옮깁니다. `data/`는 Git 제외 대상이므로 코드 push/pull로는 전송되지 않습니다.

### 6-1. [서버: OASYS Bash] 받을 폴더 준비

VS Code Remote의 OASYS 터미널 또는 SSH 접속 후 실행합니다.

```bash
cd ~/UROP
mkdir -p docs/W9/data
```

### 6-2. [로컬: Windows PowerShell] 서버로 전송

노트북의 로컬 PowerShell로 돌아와 실행합니다. `OASYS_HOST`를 평소 SSH에 사용하는 실제 주소 또는 SSH 별칭으로 바꾸세요. `raw/`와 `calibration/`이 전송되어 서버의 `data/` 아래 같은 구조로 저장됩니다. 같은 이름의 기존 기록을 덮어쓰지 않도록 에피소드마다 고유 이름을 사용하세요.

```powershell
cd C:\mirobot-vla
scp -r docs/W9/data/raw docs/W9/data/calibration <USER>@OASYS_HOST:~/UROP/docs/W9/data/
```

가상환경 `.venv`와 Windows 실행 파일은 복사하지 않습니다. 전송이 끝나면 **이후 명령은 서버 터미널로 전환**합니다.

### 6-3. [서버: OASYS Bash] 원본 확인 → 시뮬 추종·HDF5 생성

```bash
cd ~/UROP
ls docs/W9/data/raw/red_s2_001/
```

`metadata.json`, `frames.jsonl`, `robot.jsonl`, `rgb/`, `reference.jsonl`, `source.gcode`, `color_profile.json` 등 원본이 전송됐는지 확인합니다. **이미 설치된 LIBERO/Cosmos 환경**을 사용합니다. 아래 `cosmos-policy/.venv/bin/python`은 예시 경로이며 실제 설치 위치가 다르면 바꾸세요. 수집용 W9 환경과 별도입니다.

```bash
cosmos-policy/.venv/bin/python -m docs.W9.d405.export_hdf5 \
  docs/W9/data/raw/red_s2_001 \
  --out docs/W9/data/hdf5/mirobot_real \
  --real-success --layout-confirmed
```

외부 영상·action은 시뮬 Panda가 실물 기록을 따라가며 생성합니다.

`--real-success`는 **실물에서 목표 블록을 집어 들었음을 영상으로 확인했다**는 뜻입니다. `--layout-confirmed`는 **실물 블록 위치가 reference의 시뮬 배치와 보정에 맞는다**는 뜻입니다. 실패 영상에 붙이지 마세요.

실행 중 다음을 확인합니다:

1. reset 자세와 블록 배치가 reference와 일치하는가.
2. k칸의 시뮬 관측을 저장한 후 k+1칸의 실물 자세로 이동하는가.
3. 시뮬도 마지막 0.5초 동안 목표 블록을 잡고 들어 올린 상태인가.
4. 추종 오차가 기본 실물 환산 5mm·2° 이내인가.

하나라도 어긋나면 HDF5를 만들지 않고 `export_report.json`에 결과를 남깁니다. 기존 프로토타입에서는 이동 구간 최대 약 8mm가 나왔으므로 기본 5mm를 넘을 수 있습니다. 실제 기록을 검토해서 기준을 채택한 경우에만 `--max-follow-mm 10`처럼 바꾸세요. 성공을 통과시키려고 무작정 올리지 마세요.

D405 영상은 중앙 정사각 crop→256×256 RGB로 만듭니다. 손목 카메라 장착 방향이 다르면 `--rotate 90` / `180` / `270`(반시계 방향)을 쓰세요. 실제 D405 영상에 시뮬 전용 `flipud`를 무조건 적용하지 않습니다. 학습과 실행에서 같은 crop·회전을 사용해야 합니다.

결과:

```text
docs/W9/data/hdf5/
  mirobot_real/
    MIROBOT_red_s2_001_SCENE1_pick_up_the_red_block_on_the_table_demo.hdf5

data/demo_0/obs/agentview_rgb      (T,256,256,3)  시뮬 외부 RGB
data/demo_0/obs/eye_in_hand_rgb    (T,256,256,3)  D405 손목 RGB
data/demo_0/actions               (T,7)          Panda OSC_POSE
data/demo_0/robot_states          (T,9)          손가락2+위치3+쿼터니언xyzw4
```

파일 하나당 실물 에피소드 하나입니다. 여러 에피소드를 같은 suite 폴더에 두면 됩니다. `SCENE1` 뒤 파일 이름이 지시문이므로 임의로 바꾸지 마세요. 실물 관절각·XYZ mm를 `actions`에 직접 넣으면 안 됩니다.

## 7. HDF5 검사와 파인튜닝 — [서버: OASYS Bash]

OASYS의 기존 Cosmos 환경에서 구조 확인:

```bash
cosmos-policy/.venv/bin/python -m docs.W9.d405.check_dataset docs/W9/data/hdf5
```

서버에서 실제 Cosmos 로더 확인:

```bash
cosmos-policy/.venv/bin/python -m tools.check_cosmos_dataset \
  --data-dir docs/W9/data/hdf5 --recompute-stats
```

이 기존 검사기는 모양 확인에 **가짜 T5**를 임시로 사용합니다. 학습 임베딩은 따로 만들어야 합니다. 이후의 서버 환경 설치·실제 T5·체크포인트 다운로드·학습 실행은 [D405_TRAINING.md](D405_TRAINING.md)를 순서대로 따르세요.

Panda 시뮬 HDF5도 섞는다면 `docs/W9/data/hdf5/panda_sim/` 아래에 둡니다. 90개/10개 에피소드가 step 비율 90/10을 보장하지 않습니다. `check_dataset`의 suite별 step 수를 확인하고 원하는 혼합 비율은 서버 로더 설정에서 별도로 결정하세요.

## 8. 테스트와 현재 검증 범위 — [서버: OASYS Bash]

서버 보조 W9 환경에서 장비 없이 실행합니다. 필요한 경우 먼저 `bash docs/W9/d405/setup.sh`로 준비합니다. 이때 D405 0대 조회는 현재 연결 구성에서 정상입니다.

```bash
docs/W9/.venv/bin/python -m docs.W9.d405.test_pipeline
```

테스트는 임시 폴더에서만 가짜 기록을 만들며 학습 폴더에 넣지 않습니다. 시간 정렬, 다음 칸 목표, 회전 경계, 데이터 공백 거부, RGB 채널, HDF5 키·차원, 명령 사전 검사를 확인합니다.

작업 시점의 실제 설치·검증 결과는 [D405_INSTALLATION.md](D405_INSTALLATION.md)에 기록합니다. 실물 로봇 수집과 GPU 서버에서의 시뮬 추종·파인튜닝은 별도 검증이 필요합니다.

관련 기존 문서: [데이터 형식](DATASET_HDF5.md), [Panda 따라가기 설계](FOLLOW.md).
