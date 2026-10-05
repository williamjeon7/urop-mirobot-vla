# LIBERO Tabletop: Red · Green · Blue 정육면체

테이블 위의 빨강·초록·파랑 정육면체와 Panda를 실제 LIBERO 시뮬레이션으로 확인한다.
세 블록은 색상만 다르고 기본 한 변은 **40 mm**다. 아래 1→2→3 순서대로 따라 하면 된다.

## localhost 브라우저에서 실시간 확인

지금처럼 VS Code로 **OASYS에 연결된 상태**에서 아래 순서대로 진행하면 된다.
시뮬레이터는 OASYS에서 실행하고, 화면은 내 PC의 브라우저에서 본다.
로컬 PC에 Conda나 LIBERO를 설치하거나 저장소를 다시 내려받을 필요는 없다.
화면은 실시간으로 전달되며 이미지·GIF·영상 파일은 저장하지 않는다.
이미 OASYS에서 서버가 실행 중이면 중복 실행하지 말고 **2번 포트 전달부터** 진행한다.

### 1. OASYS 터미널에서 서버 실행

VS Code 상단 **Terminal(터미널) → New Terminal(새 터미널)**을 누른다.
`<USER>@OASYS`가 표시된 **Remote-SSH 터미널**에 다음을 순서대로 입력한다.
로컬 PC의 PowerShell에 입력하는 것이 아니다:

```bash
cd ~/UROP
source ~/miniforge3/etc/profile.d/conda.sh
conda activate libero
python docs/W6/rgb_blocks/browser_viewer.py
```

이 터미널은 서버가 실행되는 동안 열어 둔다. 기본 포트는 `8766`이다.
기존에 사용 중인 `8765` 포트는 건드리지 않는다. 초기 화면 생성에는 잠시 시간이 걸릴 수 있다.

### 2. VS Code에서 포트 전달

현재 OASYS에 연결된 VS Code 하단에서 **PORTS(포트)** 탭을 누른다.
탭이 보이지 않으면 `Ctrl+Shift+P`를 누르고 `Ports: Focus on Ports View`를 검색해 실행한다.

**Forward a Port(포트 전달)**를 누른 뒤 `8766`을 입력하고 Enter를 누른다.
이미 `8766`이 자동으로 등록돼 있으면 추가하지 않아도 된다.
해당 줄의 지구본 모양 **Open in Browser(브라우저에서 열기)** 버튼을 누른다.
또는 내 PC의 Chrome·Edge 등에서 `http://localhost:8766`을 연다.

내 PC에서 `8766`을 이미 사용 중이면 VS Code가 다른 로컬 포트를 배정할 수 있다.
그때는 PORTS 탭의 **Forwarded Address(전달된 주소)**에 적힌 주소를 그대로 연다.
이 전달은 기존 VS Code SSH 연결을 사용하며 별도의 비밀번호 입력이나 로컬 프로그램 실행은 필요 없다.

### 3. 화면 확인과 종료

브라우저에 테이블, Panda, 빨강·초록·파랑 정육면체가 보이고 **step 숫자가 계속 증가**하면
정상적으로 실행 중이다. `Goal=True`는 초기 배치 조건이 맞다는 뜻이며, 블록을 집었다는 뜻이 아니다.
브라우저를 닫아도 서버는 계속 실행된다. 모두 종료하려면 1번의 OASYS 터미널을 클릭하고 `Ctrl+C`를 누른다.

화면이 연결되지 않으면 OASYS 터미널에서 서버가 계속 실행 중인지, PORTS 탭에 `8766`이 등록됐는지,
브라우저 주소가 그 탭의 전달된 주소와 같은지 확인한다.
서버에서 포트 사용 중 오류가 나오면 `python docs/W6/rgb_blocks/browser_viewer.py --port 8767`로 실행하고,
2번에서도 `8767`을 전달한다. 다른 프로그램을 종료할 필요는 없다.

### 검증한 범위

OASYS에서 실제 MuJoCo/EGL 시뮬레이션과 HTTP 서버를 실행해 확인했다.
페이지·상태 응답은 정상이고, 실시간 스트림의 서로 다른 JPEG 3프레임을
512×512 이미지로 읽었다. 빨강·초록·파랑 블록 색상, step 증가, `Goal=True`,
약 20 fps 갱신, 오류 없음과 파일 미저장을 확인했다.

로컬 PC의 VS Code 포트 전달 버튼과 브라우저는 여기서 직접 조작할 수 없어
화면 표시는 별도로 확인하지 않았다. **2번을 진행해 로컬 브라우저에서 실제 화면을 확인하면 된다.**

### 시뮬레이션 동작

[W5 NewTaskBDDL 6.3–6.5·7.2](../../W5/NewTaskBDDL.md)의 환경 생성과 zero action
모니터링을 재사용하고, 표시 부분만 OpenCV 창 대신 브라우저 스트림으로 바꿨다.
파이프라인은 `RGB Object 등록 → tabletop.bddl 로딩 → env.reset() → env.step(zero action)
→ agentview_image → OpenCV JPEG 인코딩 → 브라우저 표시 → env.check_success()`다.

OASYS에 `DISPLAY`가 없어도 EGL로 렌더링하며, OpenCV로 JPEG를 만들어 메모리에서 스트리밍한다.
서버는 OASYS의 `127.0.0.1`에만 열고 외부에 직접 공개하지 않는다.
카메라나 물체 위치를 강제로 바꾸지 않는다. zero action에서도 중력·접촉과 물리 시뮬레이션은
진행되지만 **자동 집기 동작은 없다**. 현재 Goal은 세 블록의 초기 배치 조건이므로
시작부터 `True`가 정상이다. 기본 카메라 해상도는 512×512, seed는 0, 갱신 목표는 20 fps다.

### 화면 없이 환경 검증

```bash
conda activate libero
python docs/W6/rgb_blocks/test_rgb_blocks.py --headless --steps 60 --size 512 --seed 0
```

창 없이 지정한 step 수를 실행하고 결과만 터미널에 출력한다.
이미지·동영상·JSON 파일은 만들지 않는다.

### 선택 사항: 로컬 Windows OpenCV 창

브라우저 대신 W5처럼 OpenCV 창으로 보고 싶으면, W5 환경이 준비된 **로컬 Windows PC**에서
기존 UROP 저장소의 [`run_local.cmd`](./run_local.cmd)를 더블클릭하거나 PowerShell에서 실행한다:

```powershell
.\docs\W6\rgb_blocks\run_local.cmd
```

이 실행기는 활성화된 `libero` 환경이나 기존 Anaconda·Miniforge·Miniconda 환경을 찾아
W5의 WGL/DLL 설정을 적용한다. 다른 설치 위치라면 `-PythonPath "C:\path\to\libero\python.exe"`를 지정한다.
패키지 설치나 기존 환경 설정 파일 변경은 하지 않으며, 기존 LIBERO `config.yaml`이 없으면
W5 설정을 먼저 요청하고 종료한다. OpenCV 창은 `q`, `Q`, `Esc` 또는 창 닫기로 종료한다.
이 선택 사항은 로컬 PC에 W5 환경이 필요하지만, 기본 브라우저 방식에는 필요하지 않다.

## 코드에서 수치 조절

**`objects.py` 상단의 `BLOCK_SIZE_MM = 40.0`** 숫자를 수정한다.
예를 들어 `BLOCK_SIZE_MM = 60.0`이면 세 정육면체의 한 변이 모두 60 mm다.
수정 후 실행 중인 서버를 `Ctrl+C`로 종료하고 다시 실행하면 변경한 값으로 새 시뮬레이션을 만든다.
현재 BDDL 배치에서는 0 초과 120 mm 이하를 지원한다.

크기를 바꾸면 시각 형상·충돌 형상·위아래 기준점·수평 반경이 함께 바뀐다.
XML의 box `size`는 각 축의 반길이(m)다. 밀도는 일정하게 유지하므로 질량은
한 변 길이의 세제곱에 비례한다(40 mm일 때 50 g).

브라우저 화면 설정은 `browser_viewer.py` 상단에서 수정한다:

```python
PORT = 8766
CAMERA_SIZE = 512
SEED = 0
FPS = 20.0
```

`PORT`를 바꾸면 VS Code에서 전달하는 포트 번호도 함께 바꾼다.

OpenCV 창·headless 검증용 `test_rgb_blocks.py`에서는 화면 크기와 초기 배치 seed도 직접 수정할 수 있다:

```python
CAMERA_SIZE = 512
SEED = 0
MONITORING_STEPS = 60
```

명령줄의 `--size`는 카메라 해상도이고 정육면체 크기가 아니다.
정육면체 크기는 항상 `objects.py`의 `BLOCK_SIZE_MM`에서 변경한다.

## 정지 화면 및 물체 사용

이미지는 파일로 저장하지 않는다. `render_scene()`은 메모리에 있는 PIL 이미지와
메타데이터를 반환한다. 스크립트 실행 시 표준 출력에 JPEG data URL을 내보내며,
표준 오류에 물체 크기·위치·접촉 확인 결과를 출력한다. 노트북에서는 다음처럼 표시한다:

```python
from docs.W6.rgb_blocks.preview import render_scene

image, scene = render_scene()
display(image)
```

다른 LIBERO 스크립트에서는 환경 생성 **전**에 등록한다:

```python
from docs.W6.rgb_blocks import register_blocks, RedBlock

register_blocks()  # BLOCK_SIZE_MM을 적용해 BDDL의 세 블록 등록
red = RedBlock(name="red_block_1", edge_length_m=0.03)  # 개별 생성도 가능
```

`assets/`는 기본 40 mm의 MuJoCo Object XML 세 개, `objects.py`는 크기 조절·등록 코드,
`tabletop.bddl`은 초기 배치, `browser_viewer.py`는 localhost 브라우저 실시간 스트림 코드다.
`test_rgb_blocks.py`는 W5 방식의 OpenCV 모니터링·headless 검증 코드이며,
`run_local.cmd`·`run_local.ps1`은 선택 사항인 로컬 Windows 실행 진입점이다.
`preview.py`의 정지 화면 및 `animation.py`·`show_simulation.py`의 셀 GIF 기능은 별도로 남아 있다.
BDDL의 goal은 초기 배치 확인용 `On` 조건이다. 자동 집기 태스크 및 실물 로봇 명령은 포함하지 않는다.
