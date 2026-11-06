# 학습한 W10 모델을 실제 Mirobot에서 실행하기

> **절차** · 확인 2026-11-06 · 기준 `w10_mirobot_l01_l30_follow_4000/iter_000004000`
> Windows 노트북에 연결한 Mirobot과 D405를 OASYS의 VS Code 터미널에서 실행한다.

처음 사용하는 경우에는 1절부터 순서대로 진행한다. 설치가 끝난 뒤에는 연결 상태에 따라 시작할 곳이 달라진다.

| 언제 | 할 일 | 읽을 곳 |
| --- | --- | --- |
| 처음 설치하거나 Windows 코드를 새로 받을 때 | 자동 설치와 SSH 키 등록 | [1. 처음 한 번 설치하기](#1-처음-한-번-설치하기) |
| 다음날, 재부팅 후, 연결창을 닫았을 때 | Windows 연결 프로그램 다시 켜기 | [2. 실험을 시작할 때 연결하기](#2-실험을-시작할-때-연결하기) |
| 연결된 상태에서 실험을 한 번 더 할 때 | 배치 확인, 색 선택, 모델 실행 | [3. 매 실험마다 실행하기](#3-매-실험마다-실행하기) |

한 실험이 끝나도 Windows 연결 프로그램은 계속 사용할 수 있다. 색을 바꿀 때마다 설치나 키 등록을 반복할 필요는 없다.

## 먼저 알아둘 두 터미널

Mirobot과 D405의 USB는 Windows 노트북에 꽂는다. 모델과 가중치는 OASYS에 둔다.
같은 VS Code 창에서 다음 두 터미널을 사용한다.

| 터미널 | 구분하는 법 | 하는 일 |
| --- | --- | --- |
| OASYS Bash | `<USER>@OASYS:~/UROP$` | 설치 준비, 연결 확인, 모델 실행 |
| Windows 로컬 PowerShell | `PS C:\...>` | 최초 설치 명령 실행, USB 연결 프로그램 유지 |

Windows 로컬 터미널은 현재 `UROP [SSH: OASYS]` 창에서 **Ctrl+Shift+P → `Terminal: Create New Integrated Terminal (Local)`**로 연다. 시작 화면으로 돌아갈 필요는 없다. [VS Code 안내](https://code.visualstudio.com/docs/terminal/advanced#_local-terminals-in-remote-windows)

새 로컬 터미널이 Git Bash나 명령 프롬프트로 열렸다면 `powershell.exe -NoProfile`을 입력해 PowerShell로 바꾼다. `PS C:\...>`가 표시되는지 확인한다.

아래 명령은 OASYS의 `~/UROP`에 코드와 학습 가중치가 준비된 환경을 기준으로 한다. 다른 서버를 처음 구성한다면 [외부 저장소 준비](../VENDORED.md)와 [모델 준비](../MODELS.md)를 먼저 확인한다.

## 1. 처음 한 번 설치하기

### 1-1. 장치를 연결하고 설치 준비 명령 실행

Mirobot 전원을 켜고 Mirobot과 D405를 Windows 노트북에 USB로 연결한다.
장치를 사용 중인 녹화 프로그램, 시리얼 모니터, 카메라 뷰어는 닫는다.

OASYS Bash에서 실행한다.

```bash
cd ~/UROP
bash tools/connect_windows.sh
```

이 명령은 필요한 서버 환경을 준비하고, Windows에서 실행할 `irm ... | iex` 한 줄을 출력한다. 명령에 들어 있는 연결 주소는 15분 동안 유효하다. 이 터미널은 설치가 끝날 때까지 켜 둔다.

### 1-2. 출력된 한 줄을 Windows에서 실행

같은 VS Code 창에서 Windows 로컬 PowerShell을 연다.
1-1에서 출력된 한 줄을 그대로 붙여 넣는다. 예전에 사용한 주소를 다시 쓰지 않는다.

설치 프로그램이 다음 작업을 처리한다.

- 현재 서버 코드를 Windows의 `$HOME\mirobot-policy`에 받는다.
- 전용 SSH 키를 만들고 공개키를 서버에 등록한다. 기존 키는 보존한다.
- Python 3.10, `urop` 가상환경, 로봇·카메라 패키지를 준비한다.
- USB 연결 프로그램과 SSH 역터널을 시작한다.

ZIP을 따로 내려받거나, 공개키를 복사해서 전달하거나, `pip install`을 직접 입력할 필요는 없다.
서버로 보내는 키는 로봇 연결용 포트 전달에 사용한다. 개인키는 Windows에 남는다.

로컬 PowerShell에서 연결 주소에 접속하지 못하면 VS Code의 **Ports** 탭에 `8766`이 있는지 확인한다.
없으면 **Ctrl+Shift+P → `Forward a Port` → `8766`**을 실행한다.
**Local Address**에 다른 로컬 포트가 표시되면 출력된 명령의 `127.0.0.1:8766` 부분만 그 주소에 맞춘다.

### 1-3. 설치 완료 확인

Windows 터미널에 `Keep this window open`이 나오면 그 터미널을 계속 켜 둔다.
OASYS에 `WINDOWS_CONNECTED`가 나오면 임시 설치 서버는 자동으로 닫힌다.
설치 과정에서는 로봇을 움직이거나 녹화하지 않는다.

이제 OASYS Bash에서 확인한다.

```bash
bash tools/run_mirobot_local.sh --devices
bash tools/run_mirobot_local.sh --check
```

`--devices`에서 `COM3`와 D405 `262422272124`가 보이고, `--check`가 다음 문장으로 끝나면 연결이 준비된 것이다.

```text
Bridge, latest RGB, Cartesian state and preprocessing: OK (no commands sent)
```

연결 확인은 모델을 불러오거나 로봇을 움직이지 않는다. 영상과 I 번호도 만들지 않는다.
전원을 켠 뒤 `Locked`나 `A106`이 나오면 5절의 초기화를 먼저 진행한다.
처음 설치한 날에는 2절을 건너뛰고 3절로 간다.

## 2. 실험을 시작할 때 연결하기

설치 후 다음날 다시 실험하거나 Windows 연결 터미널을 닫았을 때 사용하는 절차다.
연결이 계속 살아 있으면 이 절도 건너뛴다.

### 2-1. Windows 연결 프로그램 다시 켜기

Mirobot 전원과 두 USB 연결을 확인한다. 같은 VS Code 창에서 Windows 로컬 PowerShell을 열고 실행한다.

```powershell
& "$HOME\mirobot-policy\start_mirobot_windows.cmd"
```

이 프로그램은 기존 가상환경과 SSH 키를 사용한다. 시작할 때 패키지를 확인하는 `pip` 출력이 나오는 것은 정상이다.
최초 설치용 `connect_windows.sh`나 임시 `irm` 명령은 다시 실행하지 않는다.

브리지와 SSH 터널은 이 Windows 터미널에서 계속 실행한다. SSH 연결이 끊어져도 브리지는 유지하고 터널을 자동 재연결한다.
이미 연결 프로그램이 켜져 있으면 새로 하나 더 띄우지 않는다.

### 2-2. OASYS에서 연결 확인

기존 OASYS Bash를 선택해 실행한다.

```bash
cd ~/UROP
bash tools/run_mirobot_local.sh --check
```

오류가 없으면 3절로 간다. `Connection refused`가 나오면 Windows 연결 프로그램의 오류부터 확인한다.

## 3. 매 실험마다 실행하기

여기부터는 OASYS Bash만 사용한다. Windows 연결 터미널은 켜 둔 상태로 둔다.

### 3-1. 블록과 카메라 확인

카메라 장착 방향, 작업대, 공구를 시연 수집 때 조건에 맞춘다.
빨강·초록·파랑 블록을 놓고 이번에 집을 색을 정한다. 로봇 주변을 비운 뒤 연결을 확인한다.

```bash
bash tools/run_mirobot_local.sh --check
```

영상 저장 없이 연결만 확인하려면 여기까지 실행하면 된다.
미리보기는 자동 녹화를 포함한다. 아래 실제 실행 예시는 영상 저장을 끈다.

### 3-2. 처음에는 명령 미리보기

처음 모델을 실행하거나 배치를 바꿨다면 먼저 빨강 블록 명령을 확인한다.

```bash
bash tools/run_mirobot_local.sh --color red --max-steps 4 --no-record-video
```

모델이 명령을 계산하고 `preview:` 4줄을 출력한다. 로봇은 움직이지 않으며, 호밍이나 그리퍼 조작도 하지 않는다.
MP4는 저장하지 않고 모델 입력 사진과 정책 로그만 실행 폴더에 저장한다. 손목 영상의 방향과 색이 학습 때 조건에 맞는지 확인한다.

오류가 나오면 3-3을 실행하지 말고 [문제가 생겼을 때](#5-문제가-생겼을-때)를 확인한다.

### 3-3. 실제로 집기 동작 실행하기

미리보기를 확인한 뒤 실행한다. 이 명령은 실제 로봇을 움직인다.
픽업을 시각적으로 확인할 때까지 action을 반복한다. 이 명령은 MP4를 저장하지 않는다.

```bash
bash tools/run_mirobot_local.sh --color red --execute --until-pickup --open-loop-steps 16 --motion-scale 2 --max-step-mm 24 --pickup-timeout 600 --no-record-video
```

한 번 실행할 때마다 다음 순서로 진행한다.

1. 호밍하고 로봇이 멈췄는지 확인한다.
2. 그리퍼를 `M4 S40`으로 열고 1초 기다린다.
3. 초기 위치 `X198.67 Y0 Z230.72 A0 B0 C0`로 이동해 도착을 확인한다.
4. 모델을 준비하고 관측, 추론, 한 action 이동을 반복한다.
5. 그리퍼가 닫히고 로봇이 15 mm 이상 상승한 뒤, 목표색 블록이 연속 관측에서 그리퍼 근처에 유지되면 픽업으로 판정하고 정지한다.
6. 정책 로그를 OASYS에 저장한다. MP4는 저장하지 않는다.

초기화가 실패하면 모델 동작으로 넘어가지 않는다. 모델을 불러오는 준비 시간은 녹화에 포함하지 않는다.
픽업 실행은 예측 chunk에서 최대 16 action을 실행한 뒤 다시 관측하고 추론한다.
XYZ 이동량은 학습 action의 2배로 적용하되 action 값은 ±1로 제한하고, 한 목표 이동은 최대 24 mm로 제한한다. 이는 Windows bridge의 25 mm hard limit보다 낮다. 픽업 판정에는 목표색 영역의 크기와 위치 안정성도 사용한다. 각 목표 도착은 확인하며, 실제/가상 위치 차이가 12 mm를 넘거나 600초 안에 픽업을 확인하지 못하면 안전 종료한다.
영상 기반 판정은 조명이나 가림에 영향을 받을 수 있으므로 실행 중 로봇을 계속 지켜본다. 즉시 중단해야 하면 비상정지를 사용한다.

다음 실험에서 다른 색을 집으려면 블록을 다시 놓고 색만 바꿔 실행한다. 각 줄은 별도 실험이다.

```bash
bash tools/run_mirobot_local.sh --color green --execute --until-pickup --open-loop-steps 16 --motion-scale 2 --max-step-mm 24 --pickup-timeout 600 --no-record-video
bash tools/run_mirobot_local.sh --color blue --execute --until-pickup --open-loop-steps 16 --motion-scale 2 --max-step-mm 24 --pickup-timeout 600 --no-record-video
```

매번 초기화부터 자동으로 진행하므로 Windows 연결 프로그램을 다시 켜거나 그리퍼를 수동으로 열 필요는 없다.
`--open-loop-steps`는 새 관측을 받기 전에 실행할 action 수이며 1부터 16까지 지정한다.
픽업 실행에서는 학습 chunk를 따라 최대 16 action을 사용한다. 각 이동의 도착 확인과 시각적 픽업 검사는 action마다 수행한다.
실제 속도에는 추론과 통신 시간이 포함되므로 시연의 20 Hz와 같지 않다.

### 3-4. 종료하기

한 실험이 끝나도 Windows 연결 프로그램은 계속 켜 둔다. 다음 실험은 3-1부터 반복한다.
그날 실험을 모두 마쳤을 때 Windows 로컬 PowerShell에서 아래 명령으로 종료한다.

```powershell
& "$HOME\mirobot-policy\start_mirobot_windows.cmd" -Stop
```

실행 중 OASYS에서 `Ctrl+C`를 누르면 추가 명령 전송을 멈추고 실행 로그를 마무리한다.
이미 전송된 이동은 계속될 수 있다. 즉시 정지해야 하면 로봇의 비상정지를 사용한다.
실험 종료 후 자동으로 홈으로 돌아가거나 그리퍼를 열지는 않는다. 마지막 자세와 잡은 블록을 확인하고 정리한다.

## 4. 영상과 로그 찾기

실시간 미리보기와 실제 실행 로그는 OASYS의 `Mirobot_data/W10/` 아래 번호 폴더에 저장한다.
녹화 실행은 Windows 쪽 기록 번호도 확인해 양쪽에서 사용하지 않은 다음 번호를 예약한다. 실패한 번호는 다시 쓰지 않는다.
번호 폴더를 지우면 남아 있는 OASYS와 Windows 기록을 기준으로 다음 번호를 정한다. 양쪽 기록을 모두 지운 경우에만 I1부터 다시 시작한다.

```text
Mirobot_data/W10/I1/
├── I1.mp4                  D405 손목 카메라 영상
├── I1_frames.jsonl          프레임 번호와 촬영 시각
├── I1_video.json            녹화 시작·종료 시각과 프레임 수
├── initialization.jsonl     초기화 기록 (--execute 실행)
└── policy/
    ├── events.jsonl         관측·예측·명령·녹화 이벤트
    ├── summary.json         성공·실패, 실행 횟수, 영상 경로
    └── wrist_0000.png       모델이 사용한 첫 입력 영상
```

정상적으로 영상을 가져오면 `OASYS 영상 저장 완료:` 뒤에 경로가 출력된다.
MP4는 녹화가 끝난 뒤 재생한다. 원본은 Windows의 `$HOME\mirobot-policy\policy_recordings\I1\`에도 남는다.
전송이 실패했을 때는 이 Windows 원본부터 확인한다.

영상은 색 보정 전 D405 RGB를 640×480, 30 fps로 인코딩한다. 모델 입력에는 학습 때의 색 보정을 적용한다.
프레임 누락이 있으면 MP4의 재생 길이와 실제 경과 시간이 다를 수 있으므로 정확한 시각은 `I1_frames.jsonl`을 본다.
영상이 없거나 실행이 멈췄다면 `policy/summary.json`의 `status`, `error`, `video_error`를 확인한다.

## 5. 문제가 생겼을 때

| 증상 | 확인할 것 |
| --- | --- |
| Windows 설치용 주소에 접속되지 않음 | Ports 탭의 `8766`과 Local Address 확인. 15분이 지났으면 최초 설치 명령을 새로 발급 |
| Windows 브리지 유지 종료 | `-Stop`을 실행했거나 Windows USB 브리지 프로세스 자체가 실패했는지 확인. SSH 터널 단절만으로는 브리지가 종료되지 않으며 자동 재연결한다 |
| `Windows USB 연결 프로그램/역터널이 아직 연결되지 않았습니다` 또는 `Connection refused` | 2절의 Windows 연결 프로그램을 켜고 `--check` 실행 |
| `remote port forwarding failed` | 이전 연결 프로그램이 켜져 있는지 확인하고 중복 실행 종료 |
| `COM3` access denied | 시리얼 모니터, 녹화 프로그램, 다른 브리지 종료 |
| `Expected one D405` | USB 연결과 카메라를 사용 중인 다른 프로그램 확인 |
| `colour-profile camera setting` | 시연 때의 D405·보정 프로필과 같은지 확인 |
| `Robot must be Idle` | 로봇이 움직이고 있는지 확인하고 정지 후 다시 검사 |
| `Locked`, `A106` | 호밍·초기화 필요. 아래 명령으로 준비한 뒤 `--check` 실행 |
| `stale or unsynchronized` | USB와 네트워크 상태 확인. RGB 전송 지연 점검 |
| `Target step too large`, Z 하한, tracking gap | 시작 자세·카메라 입력·예측 명령 확인. 오류가 난 실행은 중단 |
| `Bridge /recording/names` 또는 녹화 이름 조회 오류 | preview/실행에서 `--no-record-video`를 사용하거나, Windows 코드를 갱신하려면 아래 코드 업데이트 절차를 진행 |
| CUDA out of memory | `nvidia-smi`로 여유 GPU 확인. 아래 GPU 변경 예시 사용 |
| 녹화 시작 실패, 영상 0프레임 | Windows 연결 터미널의 예외와 `summary.json` 확인. 아래 시간대 오류 항목 참고 |

### 전원을 켠 뒤 로봇이 잠겨 있을 때

연결 프로그램은 시작할 때 호밍하지 않는다. `Locked`나 `A106`이 나오면 모델을 실행하기 전에 초기화한다.
`fault`도 보고되면 2절의 연결 프로그램을 다시 켠 뒤 진행한다.

Windows 연결 터미널은 유지하고 OASYS Bash에서 아래 명령을 실행한다.
**실제로 호밍하고 그리퍼를 연 뒤 초기 위치로 이동한다.** 로봇 주변을 비운 뒤 실행한다. 모델과 녹화는 시작하지 않는다.

```bash
urop/bin/python - <<'PY'
from server.policy_client import PolicyClient
result = PolicyClient("http://127.0.0.1:8891").prepare()
print("초기화 완료:", result["state"], result["cart6"])
PY
bash tools/run_mirobot_local.sh --check
```

### Windows에서 시간대 오류가 나올 때

Windows 터미널에 `ZoneInfoNotFoundError`나 `Asia/Seoul` 시간대 누락 오류가 나오면, 연결 프로그램을 종료한 뒤 로컬 PowerShell에서 실행한다.

```powershell
& "$HOME\mirobot-policy\urop\Scripts\python.exe" -m pip install tzdata
& "$HOME\mirobot-policy\start_mirobot_windows.cmd"
```

최신 설치 파일의 `requirements/policy_robot.txt`에는 이 패키지를 포함했다.
기존 Windows 설치에는 최신 코드를 다시 받거나 위 명령으로 패키지를 설치한 뒤 연결을 다시 시작한다.
Windows의 시간대 데이터는 [Python 문서](https://docs.python.org/3.10/library/zoneinfo.html#data-sources)를 참고한다.

### 코드를 수정한 뒤 Windows에 반영할 때

Windows 연결 프로그램을 먼저 종료하고 1절의 자동 설치를 다시 진행한다.
기존 가상환경과 키는 재사용한다. OASYS와 Windows의 코드는 서로 다른 파일이므로 서버에서 수정한 것만으로 Windows 파일이 바뀌지는 않는다.
`git pull`도 해당 컴퓨터의 Git 추적 파일만 갱신한다. `dist/`의 ZIP은 Git 제외 대상이다.

## 6. 확인한 범위

2026-11-06에 확인한 내용이다. 연결을 다시 열었다면 2절의 `--check`로 현재 상태를 확인한다.

| 항목 | 결과 |
| --- | --- |
| Windows USB 연결 | Mirobot `COM3`, D405 `262422272124` 확인 |
| 호밍·그리퍼 열기·초기 위치 준비 | 실제 장치에서 확인 |
| XYZ 끝점 탐색 | Z 66–280 mm (보고값 65.72–279.72), X 140–270 mm (Y0에서 140.01–269.99), Y ±180 mm (X200에서 −179.97–179.99) |
| 적용한 축 제한 | X 145–265 mm, Y −175–175 mm(실측 끝점에서 5 mm 여유), Z 66–275 mm(닫힌 그리퍼 기준 실측 하한). 수평 반경 280 mm도 적용 |
| 녹화 없는 Z축 왕복 | 5 mm 상승 명령에 보고 좌표 4.734 mm 상승, 복귀 오차 0.271 mm. 최종 `Idle`, `Pump PWM:40` |
| 저장 관측과 임시 카메라 입력을 사용한 모델 검사 | 모델 687개 키 로드와 추론, 임시 MP4 인코딩·전송 확인. 임시 파일 삭제 |
| 실제 카메라 모델 미리보기 `I1` | 모델 로드 후 녹화 시작 요청에서 실패. 추론 0회, 명령 0개, 영상 0프레임 |
| 학습 모델의 실물 집기 | 아직 확인하지 않음 |

`I1`의 실패 기록은 `Mirobot_data/W10/I1/policy/summary.json`에 있다.
시간대 패키지와 녹화 시작 전 검사 코드를 보완했으며, 관련 테스트 62개와 subtest 14개가 통과했다. 새 코드로 Windows 녹화를 다시 확인해야 한다.
실제 장치 왕복 검사와 모델의 집기 성공은 구분해서 판단한다.
자세한 작업 기록은 [WORKLOG.md](WORKLOG.md), 학습 결과는 [TRAINING_RESULT.md](TRAINING_RESULT.md), 실험 판정 기준은 [MIROBOT_EXPERIMENT.md](MIROBOT_EXPERIMENT.md)에 있다.

## 참고: 오프라인 검사와 다른 연결 방식

### 로봇 없이 모델만 검사

OASYS Bash에서 실행한다. 저장 관측을 사용하므로 Windows 연결과 USB 장치는 필요 없다.
MP4와 I 번호는 만들지 않으며 로그는 `cosmos-policy/W10/evaluations/real/`에 남는다.

```bash
bash tools/run_mirobot_policy.sh --offline-smoke --color red --max-steps 4
```

### GPU 변경

기본은 물리 GPU 2번이다. 다른 GPU를 쓰려면 실행 명령 앞에 지정한다.

```bash
CUDA_VISIBLE_DEVICES=0 bash tools/run_mirobot_local.sh --color red --max-steps 4
```

### USB를 OASYS 본체에 직접 꽂은 경우

Mirobot과 D405가 실제로 OASYS에 연결된 경우에만 사용한다. Windows 연결 프로그램은 필요 없다.

```bash
cd ~/UROP
bash tools/setup_mirobot_local.sh
bash tools/run_mirobot_local.sh --devices
bash tools/run_mirobot_local.sh --serial-port /dev/ttyUSB0 --color red --execute --max-steps 4
```

`/dev/ttyUSB0`은 감지된 포트로 바꾼다. 자동 초기화와 녹화 방식은 3절과 같다.
서버에서 장치 접근 권한 오류가 나면 관리자가 해당 계정의 시리얼·USB 권한을 설정해야 한다.

### 기본 설정과 코드 위치

| 항목 | 기본값 |
| --- | --- |
| OASYS 저장소 | `~/UROP` |
| Windows 설치 폴더 | `$HOME\mirobot-policy` |
| Python | Windows `urop`와 서버 `cosmos-policy/.venv`, 모두 3.10 |
| USB 브리지 주소 | `http://127.0.0.1:8891` |
| 로봇·카메라 | `COM3` 115200 baud, D405 `262422272124` 640×480·30 fps |
| 색 보정·좌표 기준 | `Mirobot_data/W10/L01_red/` |
| 모델 | `w10_mirobot_l01_l30_follow_4000/iter_000004000` |
| 실측 안전 좌표 범위 | X 145–265 mm, Y −175–175 mm, Z 66–275 mm, 수평 반경 280 mm 이내 |
| 동작 제한 | 한 목표 이동 최대 24 mm(bridge hard limit 25 mm), 자세각 ±30°; 모델 예측 action도 축별 좌표 범위 검사 |

실물과 가상 상태의 위치 차이가 12 mm를 넘거나 추론 중 로봇이 움직이면 실행을 중단한다.
모델은 `follow` 라벨로 학습했으며 실행 중 가상 Panda의 컨트롤러 목표를 Mirobot 명령으로 변환한다. 좌표 변환 배경은 [POLICY_RUN.md](POLICY_RUN.md)에 있다.

| 파일 | 역할 |
| --- | --- |
| `tools/connect_windows.sh` | 최초 설치·연결 준비 |
| `start_mirobot_windows.cmd` | 설치 후 Windows 연결 프로그램 재시작 |
| `tools/run_mirobot_local.sh` | 실험 실행 명령 |
| `robot/policy_bridge.py` | Windows USB 통신과 녹화 |
| `server/run_policy.py` | 모델 추론과 실제 명령 실행 |
| `trajectories/policy_start.gcode` | 초기 자세와 그리퍼 열림 설정 |
