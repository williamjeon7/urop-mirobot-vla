# D405 설치 → 녹화 → 0.05초 타임스텝 → Cosmos Policy 학습

**가지고 계신 Calibrite ColorChecker Classic Mini와 `inverse_kinematics.py`를 사용하는 주 절차는 [COLORCHECKER_MINI.md](COLORCHECKER_MINI.md)입니다.** 이 문서는 설치·데이터 변환 전체를 설명합니다.
처음에는 **1~3번으로 카메라만 확인**하세요. 실물 학습 데이터는 4번부터 만듭니다.
모든 명령은 저장소 루트 `C:\mirobot-vla`에서 실행합니다. 새 코드·환경·녹화 결과는 `docs/W9` 안에 둡니다.

## 0. 무엇을 설치하고 만들었나

| 위치 | 역할 |
| --- | --- |
| `.venv/` | W9 전용 Python 3.10 환경. 다른 환경에 영향 없음 |
| `d405/setup.ps1` | Python 패키지 설치 및 연결된 D405 조회 |
| `d405/install_viewer.ps1` | 공식 Windows RealSense Viewer를 `downloads/`에 다운로드 |
| `d405/capture.py` | D405 RGB 녹화. 선택적으로 G-code 실행·로봇 상태 기록까지 |
| `d405/robot_capture.py` | 명령 순서를 보존하며 이동·그리퍼 동작 중 로봇 상태를 폴링 |
| `d405/teleop.py` | 기존 inverse_kinematics.py의 COM3·키 조작에 상태 기록과 F8/F9 구간 표시 연결 |
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

## 1. 설치

이 PC에는 작업 중 W9 전용 환경과 SDK 패키지를 설치했습니다. 다시 설치하거나 다른 PC에서 시작할 때:

```powershell
cd C:\mirobot-vla
powershell -ExecutionPolicy Bypass -File docs/W9/d405/setup.ps1
```

Python 3.10이 필요합니다. 가상환경 활성화 없이 아래처럼 전용 Python을 직접 부르므로 PowerShell 활성화 문제를 피할 수 있습니다.

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --list
```

`RealSense D405`와 RGB 해상도가 나오면 연결 확인이 끝났습니다. 장치가 없으면 USB 케이블·포트를 확인하세요. SDK 폴더 접근 오류가 나면 일반 Windows PowerShell에서 실행하세요.

### Viewer로 화면 보기

공식 Viewer는 카메라 설정을 눈으로 확인할 때 씁니다. 설치 도구:

```powershell
powershell -ExecutionPolicy Bypass -File docs/W9/d405/install_viewer.ps1
```

`docs/W9/downloads/` 안의 `*RealSense.Viewer.exe`를 더블클릭합니다. D405를 선택하고 Color/RGB 스트림을 켜세요. 학습 녹화를 시작하기 전에는 Viewer를 닫으세요. Python과 동시에 카메라를 열 수 없습니다.

공식 다운로드: [RealSense Windows 배포 안내](https://github.com/realsenseai/librealsense/blob/master/doc/distribution_windows.md), [공식 릴리스](https://github.com/realsenseai/librealsense/releases).

## 2. 카메라만 10초 녹화

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --out docs/W9/data/raw/camera_test_001 --seconds 10 --preview
```

화면이 나오고 10초 뒤 끝납니다. 미리보기 창의 `Esc`는 중단이며 완료된 데이터로 표시되지 않습니다. 같은 출력 폴더는 덮어쓰지 않으므로 다음 녹화에서는 `002`처럼 이름을 바꾸세요.

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

## 3. 녹화 영상 확인

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.preview docs/W9/data/raw/camera_test_001
```

같은 폴더에 `review.mp4`가 생깁니다. 더블클릭해서 확인하세요. 이 MP4는 중앙 프레임 간격으로 재생하는 **확인용**이며 시간 정렬 원본은 PNG+JSONL입니다.

확인할 것: 집게와 대상 블록이 보이는지, 빛 반사가 심하지 않은지, 손목 카메라가 흔들리거나 장착 위치가 바뀌지 않는지. 학습 이미지에는 글자나 프레임 번호를 그리지 않습니다.

## 4. 로봇과 카메라를 함께 기록

카메라와 로봇은 **같은 PC에서 이 프로그램 하나로** 수집합니다. 기존 HTTP 카메라 브리지나 별도 Viewer 녹화는 이 단계에서 사용하지 않습니다.

**이번에 사용할 방식은 기존 `robot/inverse_kinematics.py`로 직접 조작하는 teleop입니다.** [COLORCHECKER_MINI.md 5번](COLORCHECKER_MINI.md#5-inverse_kinematicspy로-조작하면서-녹화)의 명령으로 실행하세요. COM3·기존 키 조작을 유지하고 F8/F9 사이만 학습 구간으로 표시합니다. 시작·종료 호밍은 기존 코드 동작을 유지합니다.

아래는 필요할 때만 사용하는 **별도의 저장된 G-code 재생 모드**입니다. 직접 조작할 때는 사용하지 않아도 됩니다. 기존 red/seed 2 예시 파일을 검사만 하려면:

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --gcode trajectories/2026_10_11-w6-pickup-red-s2-e5.gcode
```

기본 플랜지 Z 하한은 기존 프로젝트와 같은 66mm입니다. 이 수집기는 G90, M20, 모든 좌표가 적힌 G0, M4 S, G4 P만 받습니다. G4 P는 초 단위로 해석하고 PC에서 대기하며 계속 상태를 기록합니다. 호밍·상대 좌표·임의 명령은 받지 않습니다.

G-code 자동 재생을 원할 때만, 기존 방법으로 로봇 호밍·장착·작업 공간을 준비한 뒤:

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --out docs/W9/data/raw/red_s2_001 --color red --seed 2 --reference docs/W6/poses/pickup-red-s2.jsonl --gcode trajectories/2026_10_11-w6-pickup-red-s2-e5.gcode --port COM4 --initial-s 40 --open-s 40 --closed-s 60 --gripper-seconds 1.0 --execute
```

**바꿔야 하는 값:** `COM4`는 실제 포트입니다. `initial-s`는 녹화 전 실제 집게 명령값입니다. `open-s` / `closed-s`는 이 G-code의 열림·잡기 값(예에서는 S40/S60)이며, 사용 중인 집게에서 확인하세요. `gripper-seconds 1.0`도 예시입니다. 영상에서 실제 닫힘 시간을 재서 입력하세요. 측정값이 없으면 정확한 그리퍼 proprio가 아닙니다.

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

## 5. 0.05초 단위로 묶기

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

원본 `docs/W9/data/raw/red_s2_001/` 전체를 서버 저장소의 같은 위치로 옮깁니다. `.gitignore` 대상이므로 Git push로는 전송되지 않습니다. VS Code 파일 전송 또는 scp를 사용하세요. 외부 영상은 기존 결정대로 Panda 시뮬이 실물 궤적을 따라가며 새로 렌더링합니다.

서버에서 저장소 루트로 이동하고, **이미 설치된 LIBERO/Cosmos Python 환경**을 사용하세요. 아래 `cosmos-policy/.venv/bin/python`은 기존 문서의 예시 경로입니다. 실제 경로가 다르면 바꿉니다. 로컬 Windows W9 가상환경을 서버로 복사하면 안 됩니다.

```bash
cosmos-policy/.venv/bin/python -m docs.W9.d405.export_hdf5 \
  docs/W9/data/raw/red_s2_001 \
  --out docs/W9/data/hdf5/mirobot_real \
  --real-success --layout-confirmed
```

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

## 7. HDF5 검사와 파인튜닝

Windows에서 구조 확인:

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.check_dataset docs/W9/data/hdf5
```

서버에서 실제 Cosmos 로더 확인:

```bash
cosmos-policy/.venv/bin/python -m tools.check_cosmos_dataset \
  --data-dir docs/W9/data/hdf5 --recompute-stats
```

이 기존 검사기는 모양 확인에 **가짜 T5**를 임시로 사용합니다. 학습 임베딩은 따로 만들어야 합니다. 이후의 서버 환경 설치·실제 T5·체크포인트 다운로드·학습 실행은 [D405_TRAINING.md](D405_TRAINING.md)를 순서대로 따르세요.

Panda 시뮬 HDF5도 섞는다면 `docs/W9/data/hdf5/panda_sim/` 아래에 둡니다. 90개/10개 에피소드가 step 비율 90/10을 보장하지 않습니다. `check_dataset`의 suite별 step 수를 확인하고 원하는 혼합 비율은 서버 로더 설정에서 별도로 결정하세요.

## 8. 테스트와 현재 검증 범위

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.test_pipeline
```

테스트는 임시 폴더에서만 가짜 기록을 만들며 학습 폴더에 넣지 않습니다. 시간 정렬, 다음 칸 목표, 회전 경계, 데이터 공백 거부, RGB 채널, HDF5 키·차원, 명령 사전 검사를 확인합니다.

작업 시점의 실제 설치·검증 결과는 [D405_INSTALLATION.md](D405_INSTALLATION.md)에 기록합니다. 실물 로봇 수집과 GPU 서버에서의 시뮬 추종·파인튜닝은 별도 검증이 필요합니다.

관련 기존 문서: [데이터 형식](DATASET_HDF5.md), [Panda 따라가기 설계](FOLLOW.md).
