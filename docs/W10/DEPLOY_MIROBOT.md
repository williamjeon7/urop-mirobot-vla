# 학습한 W10 모델을 실제 Mirobot에서 실행하기

> **절차** · 확인 2026-11-07 · 기준 `w10_mirobot_l01_l30_follow_4000/iter_000004000`
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

OASYS Bash에서 실행한다. 처음 한 번은 서버 접속 정보 파일부터 만든다 (Git 에 올라가지 않는 파일).

```bash
cd ~/UROP
cp -n config/connection.example.json config/connection.local.json   # 처음 한 번 — OASYS 주소·계정·SSH 포트를 채운다
bash tools/connect_windows.sh
```

이 명령은 필요한 서버 환경을 준비하고, Windows에서 실행할 `irm ... | iex` 한 줄을 출력한다. 이 주소는 **이 터미널에서 `Ctrl+C` 로 끌 때까지 만료 없이 몇 번이든** 쓸 수 있다. 설치할 때마다 그 시점의 서버 코드를 보낸다. 시간 제한이 필요하면 `--ttl 900` 처럼 초를 준다.
서버 접속 정보는 `config/connection.local.json` 에서 읽고, 설치하면서 Windows 의 `mirobot-policy\config\connection.local.json` 에도 같은 값을 저장한다. 그 뒤 Windows 연결 프로그램은 이 파일을 읽는다.

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
`Locked`나 `A106`이 나오면 아래 2-3으로 호밍한다.

### 2-3. 호밍하기

연결 프로그램은 시작할 때 호밍하지 않는다. 전원을 켠 직후, `Locked`·`A106`이 나올 때, 손으로 로봇을 움직였을 때 실행한다.
3-3의 실제 집기 실행은 **호밍하지 않는다.** 그리퍼를 열고 초기 위치로만 간다. 그래서 그날 처음 실행하기 전, 전원을 켠 뒤, 잠겼을 때는 여기서 먼저 호밍한다.

**실제로 로봇이 움직인다.** 로봇 주변을 비우고 OASYS Bash에서 실행한다. Windows 연결 터미널은 켜 둔다.

```bash
urop/bin/python - <<'PY'
from server.policy_client import PolicyClient
result = PolicyClient("http://127.0.0.1:8891").prepare()
print("초기화 완료:", result["state"], result["cart6"])
PY
bash tools/run_mirobot_local.sh --check
```

하는 일: 호밍(`$H`) → 그리퍼 열기(`M4 S40`) → 초기 위치 `X198.67 Y0 Z230.72 A0 B0 C0` 이동과 도착 확인. 모델과 녹화는 시작하지 않는다.
`초기화 완료: Idle` 과 초기 위치 좌표가 나오면 정상이다. `fault`가 보고되면 2-1의 연결 프로그램을 다시 켠 뒤 실행한다.

## 3. 매 실험마다 실행하기

여기부터는 OASYS Bash만 사용한다. Windows 연결 터미널은 켜 둔 상태로 둔다.

### 3-1. 블록과 카메라 확인

카메라 장착 방향, 작업대, 공구를 시연 수집 때 조건에 맞춘다.
빨강·초록·파랑 블록을 놓고 이번에 집을 색을 정한다. 블록 좌표는 묻지 않고 실행 뒤 자동으로 잰다([블록 좌표](#블록-좌표-실행-뒤-자동-측정--직접-적는-칸)).
로봇 주변을 비운 뒤 연결을 확인한다.

```bash
bash tools/run_mirobot_local.sh --check
```

영상 저장 없이 연결만 확인하려면 여기까지 실행하면 된다.
미리보기는 저장·녹화를 하지 않는다. 아래 실제 실행(3-3)은 영상을 저장한다.

### 3-2. 처음에는 명령 미리보기

처음 모델을 실행하거나 배치를 바꿨다면 먼저 빨강 블록 명령을 확인한다.

```bash
bash tools/run_mirobot_local.sh --color red --max-steps 4 --no-record-video
```

모델이 명령을 계산하고 `preview:` 4줄을 출력한다. 로봇은 움직이지 않으며, 호밍이나 그리퍼 조작도 하지 않는다.
미리보기는 시행이 아니므로 **아무것도 저장하지 않고 번호(`I1red` 등)도 쓰지 않는다.** 화면 출력으로 손목 영상의 방향과 색, 명령 값이 학습 때 조건에 맞는지 확인한다.
미리보기 기록이 필요하면 `--save` 를 붙인다. 그러면 실제 실행과 같은 방식으로 다음 번호 폴더에 저장된다.

오류가 나오면 3-3을 실행하지 말고 [문제가 생겼을 때](#5-문제가-생겼을-때)를 확인한다.

### 3-3. 실제로 집기 동작 실행하기

미리보기를 확인한 뒤 실행한다. 이 명령은 실제 로봇을 움직인다.
픽업을 시각적으로 확인할 때까지 action을 반복하고, 실행 영상을 MP4로 저장한다(4절).

```bash
bash tools/run_mirobot_local.sh --color red --execute --until-pickup --open-loop-steps 16 --motion-scale 2 --max-step-mm 24 --pickup-timeout 600
```

한 번 실행할 때마다 다음 순서로 진행한다.

1. 로봇이 `Idle`(멈춰 있고 잠기지 않음)인지 확인한다. **호밍은 하지 않는다.** `Locked` 등이면 움직이지 않고 멈추므로 [2-3. 호밍하기](#2-3-호밍하기) 뒤 다시 실행한다.
2. 그리퍼를 `M4 S40`으로 열고 1초 기다린다.
3. 지금 자세에서 초기 위치 `X198.67 Y0 Z230.72 A0 B0 C0`로 바로 이동해 도착(2 mm·1° 이내)을 확인한다. 브리지가 한 번에 25 mm까지만 받으므로 멀면 24 mm씩 이어서 간다. 이동 경로에 블록이나 손이 없게 한다.
4. 모델을 준비하고 관측, 추론, 한 action 이동을 반복한다.
5. 그리퍼가 닫히고 로봇이 15 mm 이상 상승한 뒤, 블록이 연속 관측에서 그리퍼 근처에 유지되면 집기로 보고 정지한다. 세 색을 모두 본다. 지시한 색이면 **성공으로 자동 기록**하고, **다른 색이면 그 자리에서 멈추고 실패로 자동 기록**한다(유형 `wrong_object`, 집은 색). `result.md` 에는 "성공 (자동 판정, 영상 확인 전)"처럼 표시된다. 자동 확인은 바닥에 놓인 블록을 들린 것으로 잘못 볼 수 있으므로, 영상을 보고 정답을 넣으면 그 값으로 바뀐다("사람의 최종 판정").
6. 정책 로그와 MP4 영상을 OASYS 시행 폴더에 저장한다. 영상을 남기지 않으려면 명령 끝에 `--no-record-video` 를 붙인다.
7. **초기 위치로 돌아간다.** 어떤 이유로 끝났든(집기·다른 색·한계·시간 초과) 먼저 제자리에서 Z 230.72 mm 까지 올린 뒤 초기 위치 `X198.67 Y0 Z230.72` 로 간다. 블록 위를 낮게 가로지르지 않기 위해서다. 그리퍼는 그대로 둔다(들고 있던 블록은 들고 온다). `Ctrl+C` 로 멈췄거나 로봇이 `Idle` 이 아니면(고장·잠김) 움직이지 않는다. 기록은 `return_to_initial.jsonl`, 결과는 `launch.json` 의 `return_to_initial`. 돌아가지 않게 하려면 `--no-return` 을 붙인다.

초기화가 실패하면 모델 동작으로 넘어가지 않는다.

**실행 중 화면 보기:** 실행을 시작하면 터미널에 `실시간 화면: http://127.0.0.1:8893` 이 나온다. 화면은 모델을 불러온 뒤부터 갱신된다. VS Code 오른쪽 아래 **Open in Browser** 알림을 누르거나, **Ports** 탭에서 `8893` 의 지구본 아이콘을 눌러 노트북 브라우저로 연다. 손목 카메라 사진과 지시 색·추론·동작 번호·단계·로봇 XYZ 가 보인다. 실행이 원래 받는 관측 사진을 그대로 보여 주므로 로봇 쪽 통신은 늘지 않고, 초당 몇 장 갱신된다(영상처럼 매끄럽지 않다). 끄려면 명령 끝에 `--live-view-port 0`.

**녹화 구간:** 호밍·초기 위치 이동·모델 준비가 끝나고 **로봇이 정책으로 처음 움직이기 직전**에 시작해서, 실행이 끝나는 순간에 멈춘다. 끝나는 경우는 집기 판정·다른 색 집기(5번), 시간 초과(600초), 안전 정지(도착 오차·위치 차이 등), `Ctrl+C` 다. 어느 경우든 그때까지의 영상이 저장되고, 끝난 이유는 `result.md` 의 "종료·판정 근거"에 적힌다.
영상 0초는 첫 이동 명령 직전이다. 실행 기록 시각과의 차이는 `result.json` 의 `failure_detection.video_start_rollout_t_s` 에 있다.
픽업 실행은 예측 chunk에서 최대 16 action을 실행한 뒤 다시 관측하고 추론한다.
XYZ 이동량은 학습 action의 2배로 적용하되 action 값은 ±1로 제한하고, 한 목표 이동은 최대 24 mm로 제한한다. 이는 Windows bridge의 25 mm hard limit보다 낮다. 픽업 판정에는 목표색 영역의 크기와 위치 안정성도 사용한다. 각 목표 도착은 확인하며, 실제/가상 위치 차이가 12 mm를 넘거나 600초 안에 픽업을 확인하지 못하면 안전 종료한다.
**한계 때문에 멈추지 않음 (11/08):** 모델이 낸 목표가 어떤 한계를 넘어도 실행을 멈추지 않고 **한계 안으로 잘라서** 계속 간다. 자르는 한계는 위치(X 140–270, Y −180–180, Z 바닥–280 mm, 수평 반경 280 mm. 2026-11-06 실측 끝점), 자세각 ±30°, 한 동작 이동 24 mm·5°다. 바닥은 Windows 브리지가 알려 주는 값을 따른다. 지금 설치된 브리지는 66 mm 를 강제하므로 그 아래로는 못 간다. 저장소의 새 브리지는 60 mm(닫힌 그리퍼가 작업대에 닿는 60.7 mm 바로 아래)라서, 노트북을 갱신하면 작업대에 닿을 만큼 내려갈 수 있다. 실제·가상 자세 차이로 멈추는 검사(`--max-drift-mm`)는 기본으로 끈다(잘라 낸 만큼 실제 팔이 가상 팔보다 뒤처지기 때문). 자른 동작 수는 `summary.json` 의 `clamped_steps`, 동작별 원래 목표와 자른 양은 `events.jsonl` 의 `policy_cart6`·`clamped`, 적용한 한계는 `limits` 이벤트에 남는다. 이제 멈추는 경우는 집기 판정·다른 색 집기·시간 초과·`Ctrl+C`, 그리고 로봇이 명령 위치에 도착하지 못했을 때(2 mm 넘게 어긋남)뿐이다.
영상 기반 판정은 조명이나 가림에 영향을 받을 수 있으므로 실행 중 로봇을 계속 지켜본다. 즉시 중단해야 하면 비상정지를 사용한다.

#### 블록 좌표 (실행 뒤 자동 측정 + 직접 적는 칸)

정책은 손목 영상만 보고 끝까지 동작하므로(end-to-end) 실행 중에는 블록 좌표·크기·회전각을 묻지도 쓰지도 않는다. **모델에는 들어가지 않는다.**
실행이 끝나면 시행 폴더의 `layout.json` 에 세 블록 좌표를 한꺼번에 쓴다.

| 축 | 0 인 곳 | + 방향 | 범위 |
| --- | --- | --- | --- |
| x = 매트 **세로** 눈금 | 로봇 베이스 중심 | 로봇에서 멀어지는 쪽 | −9 ~ 30 cm |
| y = 매트 **가로** 눈금 | 가운데 `0` 중심선 | 로봇 기준 왼쪽 | −30 ~ 30 cm |

학습 데이터 `layout.json` 의 `blocks` 와는 x 만 다르다(`blocks` X = x − 30). 새 `layout.json` 에도 `blocks` 를 같이 적는다.

- **자동 측정 (`auto`)**: 호밍 뒤 초기 자세에서 저장한 첫 손목 사진(`policy/rgb_0000.png`)으로 계산한다. 11/02 에 같은 자세에서 맞춘 종이↔카메라 변환에, 색 윤곽을 2 cm 정육면체로 맞추는 방식이다. W10 L01–L30 첫 프레임 90개 블록으로 확인한 오차는 평균 약 0.2 cm, 최대 0.5 cm 다. 로봇이 초기 자세(X198.67 Y0 Z230.72)가 아니거나 색 블록을 하나로 찾지 못하면 그 값은 비우고 이유를 `auto.errors` 에 적는다. 카메라 장착이나 매트 위치가 바뀌면 이 변환을 다시 재야 한다.
- **직접 적는 칸 (`manual`)**: `manual.paper_xy_cm` 은 처음에 `null` 이다. 자로 잰 값을 적으면 그 색은 직접 적은 값을 쓰고, 자동 측정과의 차이를 `manual_minus_auto_cm` 에 남긴다. 파일을 직접 고쳐도 되고, 명령으로 넣어도 된다.

```bash
urop/bin/python -m tools.annotate_mirobot_result Mirobot_data/W10/I1red --block-xy red 21 -8 --block-xy green 21 0 --block-xy blue 22 8
```

`layout.json` 의 맨 위 `paper_xy_cm`·`blocks`·`source_by_color` 가 최종 사용 값과 그 출처(`manual`/`auto`/`not_measured`)다. `result.md` 에 표로 같이 나온다.

다음 실험에서 다른 색을 집으려면 블록을 다시 놓고 색만 바꿔 실행한다. 각 줄은 별도 실험이다.

```bash
bash tools/run_mirobot_local.sh --color green --execute --until-pickup --open-loop-steps 16 --motion-scale 2 --max-step-mm 24 --pickup-timeout 600
bash tools/run_mirobot_local.sh --color blue --execute --until-pickup --open-loop-steps 16 --motion-scale 2 --max-step-mm 24 --pickup-timeout 600
```

매번 그리퍼 열기와 초기 위치 이동을 자동으로 하므로 Windows 연결 프로그램을 다시 켜거나 그리퍼를 수동으로 열 필요는 없다. 호밍은 하지 않으므로 이전 실행이 블록을 든 채 끝났다면 블록을 치운 뒤 실행한다.
`--open-loop-steps`는 새 관측을 받기 전에 실행할 action 수이며 1부터 16까지 지정한다.
픽업 실행에서는 학습 chunk를 따라 최대 16 action을 사용한다. 각 이동의 도착 확인과 시각적 픽업 검사는 action마다 수행한다.
실제 속도에는 추론과 통신 시간이 포함되므로 시연의 20 Hz와 같지 않다.

#### 용어: action, chunk, 16

실행 로그·`result.md`·명령 옵션에 나오는 말이다.

| 용어 | 뜻 | 이 모델에서 |
| --- | --- | --- |
| **action** | 로봇을 "지금 자세에서 조금 움직여라"는 명령 하나 | 숫자 7개. 위치 변화 3개(x·y·z), 자세 변화 3개(회전), 그리퍼 1개(열기/닫기 부호). 각 값은 −1 ~ 1 |
| **chunk (묶음)** | 모델이 **한 번 추론할 때** 내놓는 action 여러 개 | **16개.** 시연 데이터가 0.05초(20 Hz)마다 한 칸이므로, 시연 기준 약 0.8초 분량의 움직임이다 |
| **추론 (query)** | 손목 사진 + 로봇 자세 + 지시문을 넣고 chunk 하나를 받는 것 | 한 번에 약 1.4초(GPU). `result.md` 의 "추론 횟수" |
| **동작 (step)** | 로봇에 실제로 보낸 action 하나 | `result.md` 의 "완료 동작 수" |
| **`--open-loop-steps 16`** | 다시 사진을 보기 전에 chunk 에서 몇 개를 실행할지 | 16 = 받은 chunk 를 다 실행하고 새로 추론. 1이면 action 하나마다 새로 추론(느리지만 매번 화면을 봄) |
| **`--motion-scale 2`** | 위치 action 을 몇 배로 키울지 | 위치 3개만 2배(±1 로 자름). 이번 실물 실행에서는 한 동작에 약 2–3 mm 움직였다 |
| **`--max-step-mm 24`** | 한 동작의 최대 이동 거리 | 넘으면 안전을 위해 멈춘다 (브리지 한계 25 mm) |
| **디노이징 단계** | 모델이 chunk 를 만들 때 거치는 계산 횟수 | 5. 실패 탐지용 특징은 단계마다 저장한다 |

한 번 실행의 흐름은 다음과 같다.

```text
사진·자세 보기 → 추론 1회 → chunk(action 16개)
  → action 1: 목표 계산 → 로봇 이동 → 도착 확인 → 집기 확인
  → action 2: ...
  → action 16
→ 다시 사진·자세 보기 → 추론 2회 → ...   (집기 판정·시간 초과·안전 정지까지 반복)
```

실패 탐지(SAFE·Hide-and-Seek)에서는 **추론 1회가 시간 한 칸**이다. `result.json` 의 `failure_detection` 에서 `episode_length_queries`(T)는 추론 횟수, `exec_horizon` 은 추론마다 실행한 action 수(= `--open-loop-steps`), `pred_horizon` 은 chunk 길이(16)다.

### 3-4. 종료하기

한 실험이 끝나도 Windows 연결 프로그램은 계속 켜 둔다. 다음 실험은 3-1부터 반복한다.
그날 실험을 모두 마쳤을 때 Windows 로컬 PowerShell에서 아래 명령으로 종료한다.

```powershell
& "$HOME\mirobot-policy\start_mirobot_windows.cmd" -Stop
```

실행 중 OASYS에서 `Ctrl+C`를 누르면 추가 명령 전송을 멈추고 실행 로그를 마무리한다.
이미 전송된 이동은 계속될 수 있다. 즉시 정지해야 하면 로봇의 비상정지를 사용한다.
실행이 끝나면 3-3의 7번대로 초기 위치로 돌아온다(호밍은 하지 않고, 그리퍼도 열지 않는다). `Ctrl+C` 로 멈춘 경우는 돌아오지 않는다. 잡은 블록은 손으로 빼서 정리한다. 다음 실행은 시작할 때 그리퍼를 열므로, 블록을 든 채 두면 초기 위치에서 떨어진다.

## 4. 영상과 로그 찾기

실시간 미리보기와 실제 실행 로그는 OASYS의 `Mirobot_data/W10/` 아래 번호 폴더에 저장한다.
번호는 OASYS에 남아 있는 폴더만 기준으로 정한다(아래 번호 규칙).

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

**번호 규칙 (11/08부터).** 시행 폴더는 색별 번호 `I1red`, `I2red`, `I1green`, ... 이고, 색마다 항상 1부터 빈 번호 없이 이어진다.
폴더를 지우면 뒤 번호가 하나씩 당겨진다(`I1red` 를 지우면 `I2red` → `I1red`). 폴더 안의 파일 이름(`I2red.mp4` 등)과 JSON·CSV 안의 이름·경로도 함께 바뀌고, 바뀐 기록은 `renumber_history.jsonl` 에 남는다.
번호 정리는 실행을 시작할 때와 끝날 때 자동으로 한다. 실행 사이에 지운 것을 바로 반영하려면 아래를 실행한다. 실행 중인 시행이 있으면 그 색은 건드리지 않는다.

```bash
urop/bin/python -m tools.renumber_trials
```

Windows 쪽 영상 원본은 원래 이름을 유지한다. 어느 이름인지는 `launch.json` 의 `bridge_recording_name` 에 있다. 같은 이름이 Windows에 이미 있으면 Windows 쪽만 다음 빈 이름으로 녹화한다.

### 4-1. 논문 형식 결과에 쓰는 파일

시행 폴더에는 위 파일에 더해 아래가 생긴다.
SAFE([vla-safe/SAFE](https://github.com/vla-safe/SAFE))와 Hide-and-Seek(코드 미공개, [deeplearning-wisc/hide_and_seek](https://github.com/deeplearning-wisc/hide_and_seek))가 시행마다 쓰는 값에 맞췄다.

| 파일 | 내용 |
| --- | --- |
| `experiment.json` | 실행 인자, 체크포인트·통계·코드 해시, git 커밋, 패키지 버전 |
| `layout.json` | 세 블록 좌표. 자동 측정(`auto`), 직접 적는 칸(`manual`), 최종 사용 값(`paper_xy_cm`, 매트 눈금 x=세로 y=가로) |
| `policy/features_NNNN.npz` | 추론마다 Cosmos 마지막 디노이징 단계의 action 헤드 입력(`action_spatial_tokens`), 디노이징 단계별 평균(`action_token_mean_by_step`). 실패 탐지기 입력 |
| `policy/rgb_NNNN.png` | 관측마다 받은 원본 RGB |
| `predictions.csv`, `commands.csv`, `robot_trajectory.csv` | 추론별 action chunk, 보낸 명령, 로봇 자세 시계열 |
| `ground_truth.json` | 사람이 영상을 보고 넣는 성공·실패 정답 (아래 명령) |
| `result.json`, `result.md` | 요약. `failure_detection` 에 성공 여부(0/1), 과제(색), 시간축 길이 T(추론 횟수), 추론마다 실행한 action 수, chunk 길이, 실패 유형·시작 추론 번호, 분할, 가장 가까운 학습 배치 |

**판정은 세 칸이다** (`ground_truth.json` 의 `verdicts`). 위에서부터 처음 입력된 칸을 최종 판정으로 쓴다.

| 칸 | 누가 넣나 | 비고 |
| --- | --- | --- |
| `human` 사람의 최종 판정 | 아래 명령 (`--annotator` 생략) | 다른 칸이 무엇이든 이 값이 최종 |
| `claude_video_review` | Claude 가 영상을 보고 넣음 (`--annotator claude_video_review`) | 사람 칸을 덮어쓰지 않는다 |
| `auto` | 실행 중 자동 집기 확인(그리퍼 닫힘·상승·블록이 손가락에 맞닿아 크게 보임) | 실행이 끝나면 자동으로 채워짐 |

`result.md` 의 "판정" 표에 세 칸이 모두 나온다. 사람의 최종 판정을 넣는 법(성공):

```bash
urop/bin/python -m tools.annotate_mirobot_result Mirobot_data/W10/I1red --success yes --selected-color red --failure-type none --split test --reason "빨강을 들어 올려 끝까지 유지"
```

실패는 `--success no` 와 실패 유형, 실패가 처음 보인 시각(**영상 플레이어에 보이는 재생 시각**, 초)을 넣는다. 카메라가 초당 30장보다 적게 찍어 MP4가 실제보다 빨리 재생되므로(예: 110.6초를 55.3초로), `I1red_frames.jsonl` 의 프레임 시각으로 실제 경과 시간으로 바꿔 저장하고, 몇 번째 추론인지도 자동으로 계산한다. 유형은 Hide-and-Seek 의 분류 `drop`, `wrong_object`, `collision`, `stuck_off_track`, `goal_violation`, `other` 중 하나다. `--selected-color` 가 지시한 색과 다르면 성공으로 적을 수 없고, 실패·`wrong_object` 로 자동으로 적힌다.

```bash
urop/bin/python -m tools.annotate_mirobot_result Mirobot_data/W10/I2red --success no --selected-color green --failure-type wrong_object --failure-onset-s 42 --split test --reason "초록 블록을 집음"
```

정답이 쌓이면 시행을 SAFE 형식(시행마다 `hidden_states` (T, D), `action_vectors` (T, 16×7))으로 모으고 색별 성공률·분할별 개수·실패 유형 표를 만든다. 서버 파일만 읽고 로봇은 움직이지 않는다.

```bash
urop/bin/python -m tools.export_failure_dataset Mirobot_data/W10 --out outputs/failure_dataset
```

bACC·wACC·TWA·AUROC·탐지 시각은 `common/failure_metrics.py` 에 두 논문의 정의대로 있다(실패 = 양성).

Hide-and-Seek 탐지기는 공식 코드가 아직 없어(11/08 기준 README 만 있음) 논문 4절과 부록 B.1·B.2 대로 `server/hide_and_seek.py` 에 다시 구현했다. 논문에 값이 없어 정한 것(시간 단위 = 추론 1회, warm-up 50 epoch, 특징 표준화, 여백·가중치는 π0 값)은 파일 첫머리와 출력 `metrics.json` 의 `config` 에 적혀 있다.
정답 입력 때 `--split` 으로 `train`(성공·실패 모두), `calibration`(성공만 쓰임), `test` 를 나눠 두고, 모으기 출력 폴더로 학습·평가한다. 작은 LSTM이라 CPU로 몇 분이면 된다.

```bash
cosmos-policy/.venv/bin/python -m server.hide_and_seek --data outputs/failure_dataset --out outputs/hide_and_seek/seed0 --seed 0
# 한 색을 학습에서 빼고 unseen 으로 평가
cosmos-policy/.venv/bin/python -m server.hide_and_seek --data outputs/failure_dataset --out outputs/hide_and_seek/unseen_blue --unseen-task blue
```

결과는 `metrics.json`(α 0.15·0.20·0.25 평균 bACC·wACC·TWA, 최고 점수 AUROC)과 `scores.csv`(시행별 시간축 점수)다. 논문처럼 seed 3개 평균을 낸다.
가짜 데이터로 확인한 결과, 학습 시행이 40개일 때는 과적합으로 AUROC 0.87, 200개일 때 0.97(정답 신호를 직접 쓴 기준 0.98)이었다. 실제 시행 수가 적으면 결과 해석에 주의한다.

## 5. 문제가 생겼을 때

| 증상 | 확인할 것 |
| --- | --- |
| Windows 설치용 주소에 접속되지 않음 | Ports 탭의 `8766`과 Local Address 확인. 설치 준비 터미널(`connect_windows.sh`)을 껐다면 다시 실행해 새 주소를 받기 |
| `connection.local.json is missing` (OASYS) | `config/connection.example.json` 을 `config/connection.local.json` 으로 복사하고 주소·계정·SSH 포트 채우기 |
| `Missing ...\config\connection.local.json` (Windows) | 11/07 이전에 설치한 Windows 코드. 1절 자동 설치를 다시 하면 이 파일이 생긴다 |
| Windows 브리지 유지 종료 | `-Stop`을 실행했거나 Windows USB 브리지 프로세스 자체가 실패했는지 확인. SSH 터널 단절만으로는 브리지가 종료되지 않으며 자동 재연결한다 |
| `Windows USB 연결 프로그램/역터널이 아직 연결되지 않았습니다` 또는 `Connection refused` | 2절의 Windows 연결 프로그램을 켜고 `--check` 실행 |
| `remote port forwarding failed` | 이전 연결 프로그램이 켜져 있는지 확인하고 중복 실행 종료 |
| `COM3` access denied | 시리얼 모니터, 녹화 프로그램, 다른 브리지 종료 |
| `Expected one D405` | USB 연결과 카메라를 사용 중인 다른 프로그램 확인 |
| `colour-profile camera setting` | 시연 때의 D405·보정 프로필과 같은지 확인 |
| `Robot must be Idle` | 로봇이 움직이고 있는지 확인하고 정지 후 다시 검사 |
| `Locked`, `A106` | 호밍·초기화 필요. [2-3. 호밍하기](#2-3-호밍하기)의 명령으로 준비한 뒤 `--check` 실행 |
| `Idle pose differs from target by more than 2 mm/deg` | 11/08 이전에 설치한 Windows 브리지가 로봇이 출발하기 전 위치를 "멈춘 위치"로 읽어 2 mm 넘는 이동을 거부한 것. 서버가 이제 그런 브리지에는 **정책 실행 중 이동**을 1.8 mm 이하로 나눠 보내고 멈춤을 직접 확인한다. 시작·복귀 이동은 빠르게 24 mm씩 한 번에 보낸다(지금까지 이 크기에서 잠긴 적은 없지만, 드물게 잠길 수 있다). 이미 이 오류가 났다면 브리지가 잠겨 있으므로 2-1로 Windows 연결 프로그램을 껐다 켠 뒤 다시 실행 |
| `stale or unsynchronized`, `Cannot reach bridge` | 관측이 늦거나 통신이 잠깐 끊긴 것. 11/08부터 **최대 15초 동안 자동으로 다시 받고**, 이동 명령은 같은 요청 번호로 다시 보낸다(브리지는 같은 번호를 두 번 실행하지 않으므로 로봇이 두 번 움직이지 않는다). 다시 시도한 횟수는 `summary.json` 의 `stale_observation_retries`·`command_retries`. 15초 넘게 계속되면 멈추므로 그때는 USB·네트워크와 Windows 연결 프로그램을 확인 |
| `Target step too large`, Z 하한, tracking gap | 시작 자세·카메라 입력·예측 명령 확인. 오류가 난 실행은 중단 |
| `Bridge /recording/names` 또는 녹화 이름 조회 오류 | preview/실행에서 `--no-record-video`를 사용하거나, Windows 코드를 갱신하려면 아래 코드 업데이트 절차를 진행 |
| CUDA out of memory | `nvidia-smi`로 여유 GPU 확인. 아래 GPU 변경 예시 사용 |
| 녹화 시작 실패, 영상 0프레임 | Windows 연결 터미널의 예외와 `summary.json` 확인. 아래 시간대 오류 항목 참고 |

### 전원을 켠 뒤 로봇이 잠겨 있을 때

`Locked`나 `A106`이 나오면 모델을 실행하기 전에 [2-3. 호밍하기](#2-3-호밍하기)의 명령으로 초기화한다.

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
| 서버 SSH 접속 정보 | `config/connection.local.json` (Git 제외, 예시 `config/connection.example.json`) |
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
| `config/connection.local.json` | 서버 SSH 주소·계정·포트. Git 제외 |
| `start_mirobot_windows.cmd` | 설치 후 Windows 연결 프로그램 재시작 |
| `tools/run_mirobot_local.sh` | 실험 실행 명령 |
| `robot/policy_bridge.py` | Windows USB 통신과 녹화 |
| `server/run_policy.py` | 모델 추론과 실제 명령 실행 |
| `trajectories/policy_start.gcode` | 초기 자세와 그리퍼 열림 설정 |
