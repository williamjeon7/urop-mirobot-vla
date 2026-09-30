# 1\. LIBERO BDDL 새로운 task를 작업명세서로 작성했을 때 시뮬레이션에서 돌아가는 지 검증

로컬 Windows PC의 Nvidia RTX 5070으로 진행했다. 명령어는 VSCode의 PowerShell 터미널 기준이다. 아래 순서대로 설치 → 기존 task 확인 → custom BDDL 초기화 → action 및 goal 검사를 진행한다.

먼저 파이프라인과 각 요소의 역할을 정리하고, 실제 명령어·코드·검증 결과는 아래 [실행과정 1~9번](#실행과정)에서 설명한다.

## 작업명세서, BDDL, Parser 및 실행 Pipeline

### 전체 파이프라인

작업명세서를 BDDL로 작성한 뒤, LIBERO가 내용을 해석해 환경을 구성한다. `env.reset()`으로 초기 상태를 만들고, `env.step(action)`으로 로봇을 움직이며, `env.check_success()`로 goal condition을 확인한다.

실행과정의 1~4번은 설치, 5번은 Panda 초기 자세와 기존 benchmark Task의 초기 장면을 렌더링하는 준비 과정이다. 6~7번은 기존 서랍 Task로 로딩부터 실제 Panda 동작까지 확인하고, 8번은 같은 파이프라인에 변경한 BDDL 두 개를 넣어 새 Task를 검증한다. 9번은 새 물체·Fixture·Predicate·카메라와 제어 설정을 코드에 추가한 뒤 같은 검증 절차를 적용한다.

```text
작업명세서
    ↓
사람이 수행할 task 정의
예: "가운데 서랍을 연다."
    ↓
[실행과정 6번: BDDL 준비 / 환경 생성 / 초기 상태 확인]
BDDL 작성 / 기존 BDDL 복사 및 수정
    ↓
custom_tasks/custom_test.bddl
    ↓
9장: 새 물체·Predicate·Problem 모듈을 import하여 등록
     (환경 생성 전에 수행)
    ↓
OffScreenRenderEnv(bddl_file_name=...)
    ↓
get_problem_info()로 problem 이름 확인
    ↓
TASK_MAPPING에서 BDDL의 problem 이름에 해당하는 환경 선택
6~8장: LIBERO_Tabletop_Manipulation
9장 D·F: 새로 등록한 환경
    ↓
BDDL Parser로 내용 해석
(objects / regions / fixtures / init / goal)
    ↓
robosuite / MuJoCo scene 구성
    ↓
env.reset()
    ↓
BDDL의 :init 조건을 기반으로 초기 상태 생성
Panda 초기 자세 / Cabinet / Object 배치
    ↓
obs 반환 → obs["agentview_image"]
    ↓
초기 상태 PNG 또는 화면 확인
    ↓
[실행과정 7번: action 전달 / observation 갱신 / goal 검사]
env.check_success()로 초기 goal 확인
현재 서랍 task에서는 False 예상
    ↓
action 생성
현재 7.2: zero action / 이후: 실제 작업 수행 action
    ↓
env.step(action)
    ↓
컨트롤러를 통해 Panda action 실행
MuJoCo 물리 시뮬레이션 진행
    ↓
새로운 observation / reward / done / info 반환
    ↓
agentview_image 갱신
(실시간 viewer 사용 시 cv2.imshow()로 화면 갱신)
    ↓
env.check_success()
    ↓
BDDL의 :goal 조건 만족 여부 확인
    ├─ False → goal 미충족 → 다음 action으로 반복
    └─ True  → goal 충족 → task 성공
```

아래 표는 실행 파이프라인의 각 단계와 세부 목차의 대응이다. 7.3과 8.5, 9.4.6의 **시뮬레이터 상태 직접 변경**은 Goal 판정만 따로 확인하는 시험이며, Panda가 그 동작을 수행했다는 증거는 아니다.

| 파이프라인 단계 | 기존 서랍 Task | 변경한 Custom Task |
| --- | --- | --- |
| BDDL 준비·환경 선택 | 6.1 기존 BDDL 복사, 6.2 `custom_tasks` 구성 | 8.1 검증 기준, 8.2 Task 설계, 8.3 두 BDDL 작성 |
| BDDL 로딩·`env.reset()`·초기 이미지 | 6.3 직접 실행, 6.4 실시간 화면, 6.5 Windows 렌더링 설정 | 8.4 환경 로딩·초기 상태·사진 확인 |
| 초기 Goal·`env.step(action)` | 7.1 초기 `False`, 7.2 zero action과 관측값 확인 | 8.4 초기 `False`, 8.5 실제 OSC_POSE action과 영상 확인 |
| Goal 판정과 실제 수행 구분 | 7.3 서랍 joint 직접 변경, 7.4 Panda로 서랍 열기 | 8.5 물체 상태 직접 변경과 Panda action 결과를 따로 기록 |
| 검증의 적용 범위와 결론 | 6~7번의 서랍 Task 결과 | 8.6 BDDL·코드 확장 범위, 9.6의 5~9장 종합 결과 |

9장의 C~F도 **설계 → 구현 → BDDL 작성 → 초기 상태 → Action·Goal** 순서로 진행한다. 각 사례의 1~5번 소절은 이 순서에 대응하며, 추가 구현 방법과 전체 정리까지 다음 표에 연결했다.

| 파이프라인 단계 | 9장 세부 목차 | 코드가 담당하는 부분 |
| --- | --- | --- |
| 검증 기준과 Task 설계 | 9.1 공통 기준, 9.2.1 C, 9.3.1 D, 9.4.1 E, 9.5.1 F | BDDL만으로 표현할 수 없는 변경 요소 선정 |
| 환경 구성·판정 함수 준비 | 9.2.2 C, 9.3.2 D, 9.4.2 E, 9.5.2 F | C의 새 Object 등록, D의 Fixture·배치 높이, E의 Predicate 등록, F의 카메라·컨트롤러 설정 |
| 추가 요소의 구현 방법 | 9.1.1 코드 작성 항목, 9.3.6 장면·Init 확장, 9.5.6 로봇·작업대 설정 | 환경 생성과 초기화 단계에서 작성·적용할 코드 |
| BDDL 준비·Problem 선택 | 9.2.3 C, 9.3.3 D, 9.4.3 E, 9.5.3 F | 등록한 요소를 BDDL 이름과 연결 |
| BDDL 로딩·`reset()`·초기 상태 | 9.2.4 C, 9.3.4 D, 9.4.4 E, 9.5.4 F | 초기 사진, Init 조건, 초기 Goal `False` 검사 |
| `step(action)`·최종 Goal | 9.2.5 C, 9.3.5 D, 9.4.5 E, 9.5.5 F | 실제 Panda 동작, 놓기·후퇴 이후 Goal 유지 확인 |
| Predicate 의미와 결론 | 9.4.6 경계 조건 검사, 9.6 전체 정리 | E의 거부 조건 검증, 5~9장 결과와 적용 범위 정리 |

새 요소의 등록은 환경 생성 전에 끝내야 한다. D의 배치 높이는 초기 상태를 만들 때, E의 판정 함수는 `check_success()`를 호출할 때 사용된다. F의 카메라와 컨트롤러는 환경을 구성할 때 설정하며, 실제 실행 중에는 각각 화면 관측과 로봇 제어를 담당한다.

### 작업명세서란?

작업명세서는 로봇이 어떤 작업을 수행해야 하는지를 사람이 이해할 수 있는 형태로 정의한 것이다. 작업명세서에는 다음 내용이 포함된다.

- 어떤 물체를 사용할 것인지
- 물체의 초기 위치는 어디인지
- 로봇이 어떤 행동을 수행해야 하는지
- 어떤 상태가 되면 작업이 성공한 것인지

예를 들어, "테이블 위에 있는 우유를 집어서 바구니 안에 넣는다."라는 문장은 사람이 이해할 수 있는 작업명세서이다. 즉, 작업명세서는 **"로봇에게 어떤 작업을 시킬 것인가?"**를 정의하는 상위 개념이다.

### BDDL이란? — 작업명세서와의 차이

BDDL은 사람이 작성한 작업명세서를 LIBERO 시뮬레이터가 읽고 사용할 수 있도록 구조화한 작업 정의 파일이다. 작업명세서와 BDDL은 서로 다른 task가 아니라 같은 task를 서로 다른 형태로 표현한 것이다.

작업명세서가 "우유를 집어서 바구니 안에 넣는다."라면, BDDL에서는 사용할 물체, 배치 영역, 초기 상태, 성공 조건 등을 나누어 정의한다. 작업명세서는 무엇을 수행할지 사람이 이해하기 쉽게 정의하고, BDDL은 그 작업을 LIBERO에서 사용할 수 있도록 구체적으로 표현한다.

BDDL 파일의 전체 구조와 각 항목은 실행과정 6.2의 예시에서 확인할 수 있다. BDDL에 목표를 적으면 환경과 성공 조건이 정의되며, 그 목표를 달성할 action은 별도로 만들어 입력해야 한다.

### BDDL Parser란?

BDDL Parser는 `.bddl` 파일에 작성된 내용을 읽고 해석하는 프로그램이다. `custom_test.bddl`은 텍스트 형태의 작업 정의 파일이기 때문에 MuJoCo가 그 내용을 바로 이해하는 것은 아니다.

따라서 Parser가 problem, domain, language, objects, regions, fixtures, init condition, goal condition을 읽고 LIBERO가 사용할 수 있는 형태로 해석한다.

예를 들어 BDDL에 다음과 같이 작성되어 있으면,

```lisp
(:objects
    milk_1 - milk
)
```

"milk 타입의 milk_1이라는 물체가 필요하다."라고 해석한다. 여기서 인스턴스(instance)는 장면에 생성할 개별 물체를 뜻한다. `milk_1 - milk`의 오른쪽 `milk`는 LIBERO에 등록된 Object 종류(type), 왼쪽 `milk_1`은 그 종류로 만들 인스턴스의 이름이다. 또한 `:goal`을 해석해서 어떤 상태가 되어야 task가 성공한 것인지 LIBERO가 판단할 수 있도록 정보를 전달한다.

### LIBERO_Tabletop_Manipulation이란?

BDDL 파일의 첫 부분에는 다음과 같은 내용이 들어간다.

```lisp
(define (problem LIBERO_Tabletop_Manipulation)
```

이 의미는 "이 작업은 LIBERO_Tabletop_Manipulation이라는 Tabletop 조작 문제 형식을 사용한다."라는 뜻이다. LIBERO는 이 problem 이름을 확인하고, 이에 해당하는 Tabletop manipulation 환경을 생성한다.

실제 코드에서는 `OffScreenRenderEnv`가 `get_problem_info()`로 problem 이름을 읽고, `TASK_MAPPING`에서 환경 클래스를 선택한다. 선택된 환경은 `robosuite_parse_problem()`으로 나머지 BDDL 내용을 해석해 장면과 조건을 구성한다.

MuJoCo는 로봇과 물체의 움직임, 접촉 등 실제 물리 simulation을 수행하는 엔진이다. LIBERO와 robosuite는 BDDL로 정의된 환경을 구성하고, action 전달과 observation 반환, 성공 조건 판정을 연결한다.

### env.reset()이란?

LIBERO 환경을 생성한 뒤 `obs = env.reset()`을 실행하면 BDDL에 정의된 scene과 `:init` 조건을 기준으로 시뮬레이션의 초기 상태를 만든다. Drawer task라면 Panda 로봇 초기 자세, Tabletop과 Cabinet, 서랍의 초기 상태, 주변 object 배치 등을 준비한다.

5번의 `env.set_init_state(init_states[0])`는 benchmark에 저장된 특정 상태를 재현한다. 반면 6번의 `env.reset()`은 BDDL의 배치 영역과 초기 조건을 기반으로 초기화하므로 실행할 때 물체의 위치가 영역 안에서 달라질 수 있다.

이때 얻는 `obs`에는 카메라 이미지, 로봇 상태 등의 observation이 들어 있다.

### agentview_image란?

`agentview_image`는 LIBERO 시뮬레이션 환경을 외부 카메라 시점에서 촬영한 RGB 이미지이다. `obs["agentview_image"]`로 가져와 OpenCV를 이용해 저장하거나 실시간으로 확인할 수 있다.

PNG를 저장할 때는 6.3 코드처럼 이미지 방향을 보정하고 RGB를 OpenCV용 BGR로 변환한다. 화면을 계속 확인하려면 `env.step()`으로 새로운 observation을 받고, `cv2.imshow()`와 `cv2.waitKey()`를 반복 호출한다. 실시간 viewer의 전체 코드는 7.2에 있다.

### env.step(action)이란?

`env.reset()`은 초기 환경만 생성한다. 실제로 로봇을 움직이려면 action을 입력해야 한다.

```python
obs, reward, done, info = env.step(action)
```

`env.step(action)`은 하나의 action을 컨트롤러에 전달하고 시뮬레이션의 제어 step을 한 번 진행한다. 이 제어 주기 안에서 MuJoCo의 물리 계산은 여러 timestep 실행될 수 있다.

이 예제의 Panda는 기본 `OSC_POSE` 컨트롤러를 사용한다. Action의 7차원 구성과 zero action 테스트 방법은 7.2에서 설명한다.

### env.check_success()란?

BDDL의 `:goal`에는 task 성공 조건이 정의되어 있다. Drawer task라면 "가운데 drawer가 열린 상태"가 goal condition이 될 수 있다.

`success = env.check_success()`로 현재 시뮬레이션 상태가 goal condition을 만족하는지 확인한다.

- `False` → 아직 task 성공 조건을 만족하지 않음
- `True` → BDDL에 정의된 goal condition 만족

이 함수는 현재 상태를 검사하는 역할이며 로봇을 움직이거나 goal을 자동으로 달성하지 않는다. 7.2의 `False`는 zero action 테스트에서 예상하는 결과다. 7.3에서는 서랍이 열린 상태에서 `True`가 되는지 확인해, BDDL의 goal 정의와 Panda action 수행을 나누어 검증한다.

---

## 실행과정

### 1\. LIBERO 공식 코드 받기

VSCode PowerShell 터미널에서 다음 명령 실행

`git clone https://github.com/Lifelong-Robot-Learning/LIBERO.git`

### 2\. Tabletop 코드 확인

`cd LIBERO`로 이동한 뒤 다음 명령으로 Tabletop 환경 코드를 확인한다. 이후 상대 경로가 포함된 명령과 Python 실행은 이 LIBERO 루트에서 진행한다. 새 터미널을 열었다면 해당 폴더로 다시 이동하고 `conda activate libero`를 실행한다.

`ls libero/libero/envs/problems` -> libero_tabletop_manipulation.py 확인

### 3\. LIBERO 전용 conda 환경 생성

#### 3.1) Anaconda 설치: winget으로 설치 진행

`winget --version` -> 설치 가능한 지 확인, 정상적으로 버전 나오면 됨

`winget install -e --id Anaconda.Anaconda3` -> Anaconda 설치

설치가 끝나면 VSCode를 완전히 종료한 후 다시 실행한다.

#### 3.2) PowerShell에서 conda activate 바로 사용하기

먼저 설치를 확인한다.

```powershell
& "$env:USERPROFILE\anaconda3\Scripts\conda.exe" --version
```

새 PowerShell 터미널에서도 `conda`를 바로 쓰려면 아래 명령을 한 번 실행한다.

```powershell
$liberoCondaProfile = $PROFILE.CurrentUserAllHosts
New-Item -ItemType Directory -Path (Split-Path -Parent $liberoCondaProfile) -Force | Out-Null
if (-not (Test-Path -LiteralPath $liberoCondaProfile)) {
    New-Item -ItemType File -Path $liberoCondaProfile | Out-Null
}
if ((Get-Content -LiteralPath $liberoCondaProfile -Raw) -notlike '*anaconda3\shell\condabin\conda-hook.ps1*') {
    Add-Content -LiteralPath $liberoCondaProfile -Value @'
$condaHook = Join-Path $env:USERPROFILE 'anaconda3\shell\condabin\conda-hook.ps1'
if (Test-Path -LiteralPath $condaHook) { . $condaHook }
'@
}
```

VSCode 터미널을 닫고 새 PowerShell 터미널을 열어 `conda --version`으로 확인한다. 이후에는 hook 명령을 따로 입력할 필요가 없다.

프로필 실행이 차단된다는 오류가 날 때만 현재 사용자 실행 정책을 확인하고 `RemoteSigned`로 설정한다.

```powershell
Get-ExecutionPolicy -List
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

#### 3.3) LIBERO 환경 생성

1. `conda create -n libero python=3.8.13 -y`

**CondaToSNonInteractiveError가 발생하면:** Anaconda 채널 이용약관 동의 후 다시 진행한다.

```powershell
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2
```

명령어를 순서대로 입력해 동의한 후, conda 환경 생성 명령을 다시 실행한다.

2. `conda activate libero`

3. `python --version`

`python --version`을 실행하면 `Python 3.8.13`이라고 나와야 한다. 이번 LIBERO 환경은 이 버전을 기준으로 한다. 그리고 터미널 앞에 `(libero)`가 뜨는지 확인한다. 이후 설치와 실행은 이 환경에서 진행한다.

### 4\. LIBERO 설치

앞에서 만든 `libero` 환경을 활성화한 상태에서 설치를 진행한다.

1. `python -m pip install "pip<25" setuptools wheel`

VSCode에서 `Ctrl+Shift+P` → `Python: Select Interpreter`를 열어 `libero` conda 환경을 선택한다.

2. `pip install -r requirements.txt`

LIBERO 의존성 설치

**Windows에서 egl_probe 빌드 오류가 나면:** 먼저 CMake를 설치한다.

`pip install cmake`

`cmake --version` -> 확인

그 후 Windows 패치된 `egl_probe`를 설치한다.

```powershell
pip install https://github.com/mhandb/egl_probe/archive/fix_windows_build.zip
```

Windows 패치된 `egl_probe` 설치가 성공하면 `pip install -r requirements.txt`를 다시 실행한다.

패치 설치도 실패하면 당시 진행한 것처럼 Windows WGL 테스트에 필요한 나머지 패키지를 설치하고 `egl_probe`는 건너뛴다. 전체 requirements 설치가 실패한 상태에서 바로 다음 단계로 넘어가면 다른 패키지도 누락될 수 있으므로 아래 명령을 실행한다.

```powershell
pip install robomimic==0.2.0 --no-deps
pip install hydra-core==1.2.0 numpy==1.22.4 wandb==0.13.1 easydict==1.9 transformers==4.21.1 opencv-python==4.6.0.66 einops==0.4.1 thop==0.1.1-2209072238 robosuite==1.4.0 bddl==1.0.1 future==0.18.2 matplotlib==3.5.3 cloudpickle==2.1.0 gym==0.25.2
```

이 우회 경로를 사용한 뒤 `pip install robomimic`을 다시 실행하면 `egl_probe` 설치가 반복될 수 있다. 여기서는 버전을 지정한 `--no-deps` 명령을 사용한다.

**Windows 렌더링 설정**

렌더링은 Windows용 `wgl`로 설정한다. 먼저 현재 터미널에서 아래 명령을 실행한다.

```powershell
$env:MUJOCO_GL="wgl"
```

그래도 `invalid value for environment variable MUJOCO_GL: egl` 오류가 나면 `binding_utils.py`가 `egl`을 강제로 설정하는지 확인한다. 이번 실행에서는 해당 설정을 `wgl`로 바꿔 진행했다. 수정할 파일은 현재 활성화한 conda 환경 안에 있다.

`code "$env:CONDA_PREFIX\Lib\site-packages\robosuite\utils\binding_utils.py"`

파일에서 `os.environ["MUJOCO_GL"] = "egl"`을 찾아 Windows에서 실행되는 분기에 대해 `"wgl"`로 바꾸고 저장한다. 기존 운영체제 분기를 유지하려면 다음처럼 작성한다.

```python
if _SYSTEM == "Darwin":
    os.environ["MUJOCO_GL"] = "cgl"
elif _SYSTEM == "Windows":
    os.environ["MUJOCO_GL"] = "wgl"
else:
    os.environ["MUJOCO_GL"] = "egl"
```

**로그 경로 오류가 발생하면**

`C:\tmp\robosuite.log` 관련 `FileNotFoundError`가 발생하면 로그 폴더를 만든 뒤 import를 다시 확인한다.

```powershell
New-Item -ItemType Directory -Force C:\tmp
Test-Path C:\tmp
```

`Test-Path` 결과가 `True`이면 폴더가 준비된 것이다.

3. `pip install mujoco` -> mujoco 설치

당시 사용한 MuJoCo 버전은 `2.3.2`다. 같은 조합으로 재현하려면 `pip install mujoco==2.3.2`로 설치하고 `python -c "import mujoco; print(mujoco.__version__)"`으로 확인한다.

LIBERO 루트에서 `pip install -e .`도 실행해 로컬 LIBERO 패키지를 현재 환경에 등록한다.

4. `python -c "import robosuite; print('ROBOSUITE OK')"` 실행 후 `ROBOSUITE OK`가 나오면 다음 단계로 넘어간다. 오류가 남아 있으면 위의 설치·렌더링·로그 경로 처리를 확인한다.

### 5\. Panda 초기 자세와 기존 LIBERO Task의 초기 장면 확인

#### 5.1) `python -c "import libero; import robosuite; import robomimic; import bddl; print('LIBERO OK')"`

`LIBERO OK`가 나오면 설치 확인 완료

#### 5.2) Task를 불러오기 전 Panda 초기 자세만 렌더링

먼저 작업 물체를 배치하기 전에 Panda 모델과 렌더링이 정상적으로 동작하는지 확인했다. [`test_panda_initial_pose.py`](./custom_task_validation/test_panda_initial_pose.py)는 LIBERO의 `MountedPanda`와 빈 TableArena를 구성한다. BDDL이나 benchmark 초기 상태를 불러오는 단계는 다음 절에서 진행한다.

파일을 기존 테스트 코드와 같은 `docs/W5/LIBERO` 루트에 저장하고, 해당 폴더의 PowerShell에서 실행한다.

```powershell
conda activate libero
python .\test_panda_initial_pose.py
```

초기 자세에 무작위 잡음을 넣지 않고 `MountedPanda.init_qpos`를 적용했다. 실행 결과 작업 물체는 0개, 테이블 상판 높이는 0.90 m였으며, Panda의 7개 관절 각도가 초기 설정과 일치했다. 사진은 로봇 전체가 보이도록 초기 자세 확인용 카메라에서 512×512로 저장했다.

![Task를 불러오기 전 Panda 초기 자세와 빈 테이블](./images/panda_initial_pose.png)

이 단계에서 로봇의 초기 자세와 화면 출력을 확인한 뒤, 다음 절에서 물체와 초기 배치가 포함된 기존 Task의 장면을 생성한다.

#### 5.3) 기존 LIBERO benchmark Task의 초기 상태를 불러와 PNG 저장

기존 benchmark의 BDDL로 환경을 구성하고, `env.set_init_state(init_states[0])`로 저장된 초기 상태를 재현한다. 아래 코드는 이 장면을 PNG로 저장한다. 이후 6장에서 서랍 Custom Task를 별도로 구성하고, 그 Task의 Action 실행과 Goal 검사를 7장에서 다룬다.

LIBERO 폴더 안에 `test_libero_tabletop.py`를 만들고 다음 코드 저장

```python
import os
import cv2
import numpy as np

os.environ["MUJOCO_GL"] = "wgl"

from libero.libero import benchmark, get_libero_path
from libero.libero.envs.env_wrapper import OffScreenRenderEnv

# 1) benchmark에서 기존 task 하나 선택
task_suite = benchmark.get_benchmark_dict()["libero_object"]()
task_id = 0
task = task_suite.get_task(task_id)

# 2) 실제 bddl 파일 경로
bddl_file = os.path.join(
    get_libero_path("bddl_files"),
    task.problem_folder,
    task.bddl_file,
)

# 3) init state
init_states = task_suite.get_task_init_states(task_id)

print("Task language :", task.language)
print("BDDL file     :", bddl_file)

# 4) Offscreen 환경 생성
env = OffScreenRenderEnv(
    bddl_file_name=bddl_file,
    camera_heights=256,
    camera_widths=256,
)

# 5) reset + 초기 상태 세팅
env.reset()
obs = env.set_init_state(init_states[0])

print("Observation keys:", list(obs.keys()))

# 6) image key 찾기
img_key = None
for k, v in obs.items():
    if isinstance(v, np.ndarray) and v.ndim == 3:
        img_key = k
        break

if img_key is None:
    raise RuntimeError("이미지 observation을 찾지 못했습니다.")

print("Using image key:", img_key)

frame = obs[img_key]

# LIBERO / robosuite offscreen은 위아래 뒤집혀 나오는 경우가 많아서 뒤집어서 저장
frame = frame[::-1]

if frame.dtype != np.uint8:
    frame = np.clip(frame, 0, 255).astype(np.uint8)

cv2.imwrite("libero_tabletop_test.png", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
print("Saved: libero_tabletop_test.png")

env.close()
```

코드 저장 후

```powershell
$env:MUJOCO_GL="wgl"
python .\test_libero_tabletop.py
```

실행 후 `libero_tabletop_test.png`가 생성되면 성공

![LIBERO Tabletop 테스트](./images/libero_tabletop_test.png)

### 6\. 새 LIBERO BDDL task를 작업명세서로 작성하고, 실제 Tabletop 시뮬레이션에서 돌아가는지 검증

> **6번은 위 [전체 파이프라인](#전체-파이프라인)의 `BDDL 준비 → 환경 생성 → env.reset() → 초기 이미지 확인` 구간이다.** 작업을 시작할 수 있는 환경이 만들어지는지 확인한다.

#### 6.1) 기존 BDDL 하나 복사

5번에서 사용한 benchmark task의 BDDL 경로는 다음 명령으로 확인할 수 있다.

`python -c "from libero.libero import benchmark,get_libero_path; import os; s=benchmark.get_benchmark_dict()['libero_object'](); t=s.get_task(0); print(os.path.join(get_libero_path('bddl_files'),t.problem_folder,t.bddl_file))"`

#### 6.2) custom_tasks 폴더 생성

LIBERO 루트에서 `custom_tasks` 폴더와 `custom_test.bddl` 파일을 만든다. 이미 존재하면 생성 명령은 생략한다.

```powershell
mkdir custom_tasks
New-Item .\custom_tasks\custom_test.bddl -ItemType File
```

그 후 기존 Tabletop BDDL 하나를 복사해서 실행 가능한지 먼저 확인한다.

**현재 task: 나무 캐비닛의 가운데 서랍 열기**

영어 작업 명령은 `Open the middle layer of the drawer`다. Panda 로봇이 가운데 서랍 손잡이를 잡고 당겨 서랍을 여는 작업이다. BDDL의 성공 조건은 가운데 서랍 영역인 `wooden_cabinet_1_middle_region`이 열린 상태가 되는 것이다.

```powershell
Copy-Item `
".\libero\libero\bddl_files\libero_goal\open_the_middle_drawer_of_the_cabinet.bddl" `
".\custom_tasks\custom_test.bddl" `
-Force
```

복사 확인

`Get-Content .\custom_tasks\custom_test.bddl | Select-Object -First 10`

예시

```lisp
(define (problem LIBERO_Tabletop_Manipulation)
  (:domain robosuite)
  (:language Open the middle layer of the drawer)
    (:regions
      (plate_region
          (:target main_table)
          (:ranges (
              (0.04 -0.03 0.060000000000000005 -0.01)
            )
          )
```

**첫 custom task에서의 고려 요소**

첫 custom task에서는 `(define (problem LIBERO_Tabletop_Manipulation)` 부분을 유지한다. 이 이름은 LIBERO가 Tabletop manipulation 환경 클래스를 선택할 때 사용한다.

처음부터 새로운 object를 추가하기보다는 LIBERO가 이미 지원하는 object를 사용하고 goal을 바꾸는 것이 목표다. 수정할 때는 다음 항목을 함께 확인한다.

- Objects → 어떤 물체를 사용할 것인가
- Regions → 테이블 위 어디에 배치하거나 어떤 물체의 영역을 사용할 것인가
- Init → 시작할 때 물체가 어디에 있고 어떤 상태인가
- Goal → 어떤 상태가 되면 task 성공인가

현재 `custom_test.bddl`은 기존 서랍 task를 그대로 복사한 파일이다. 우선 이 파일로 로딩과 초기화가 되는지 확인하고, 새로운 작업을 정의할 때 `:language`와 `:goal`을 함께 수정한다. 대상이 달라지면 `:obj_of_interest`도 맞춰 주고, 배치가 달라지면 `:regions`와 `:init`을 확인한다. 자연어 설명만 바꿔서는 성공 조건이 바뀌지 않는다.

BDDL의 각 항목은 다음과 같다.

```lisp
(define (problem LIBERO_Tabletop_Manipulation)

(:domain robosuite)

(:language ...)
; 자연어 작업 명령

(:regions
    ...
)
; 물체/fixture가 배치될 영역

(:fixtures
    ...
)
; 테이블, 캐비닛, 스토브 등 고정 환경 요소

(:objects
    ...
)
; 조작 대상 물체

(:obj_of_interest
    ...
)
; task에서 중요하게 보는 대상

(:init
    ...
)
; 시작 상태

(:goal
    ...
)
; 성공 조건
)
```

이 구조를 바탕으로 물체, 초기 상태, 성공 조건을 정의한다. Parser와 환경 생성 과정은 위 [전체 파이프라인](#전체-파이프라인)에서 확인할 수 있다.

#### 6.3) Custom BDDL 직접 실행

아직 benchmark에 등록하지 않고 `OffScreenRenderEnv`에 BDDL 경로를 직접 전달한다. Benchmark 등록은 여러 task를 suite로 관리하기 위한 절차이며, BDDL 한 개를 실행하기 위한 필수 절차는 아니다.

```text
LIBERO/
├─ custom_tasks/
│  └─ custom_test.bddl  ← 실제 작업 정의 파일
├─ test_libero_tabletop.py
├─ test_custom_bddl.py  ← BDDL을 읽어서 실행·검증하는 Python 코드
├─ libero/
└─ ...
```

##### 1) test_custom_bddl.py 생성

LIBERO 최상위 폴더에서 `test_custom_bddl.py`를 만들고 아래 코드 그대로 넣기

```python
import os
import cv2

# Windows MuJoCo rendering
# robosuite / LIBERO import 전에 설정해야 함
os.environ["MUJOCO_GL"] = "wgl"

from libero.libero.envs.env_wrapper import OffScreenRenderEnv

# test_custom_bddl.py가 있는 LIBERO 루트를 기준으로 BDDL 경로 생성
base_dir = os.path.dirname(os.path.abspath(__file__))

bddl_path = os.path.join(
    base_dir,
    "custom_tasks",
    "custom_test.bddl"
)

print("BDDL path:", bddl_path)

if not os.path.exists(bddl_path):
    raise FileNotFoundError(f"BDDL 파일이 없습니다: {bddl_path}")

# Custom BDDL을 직접 읽어 LIBERO 환경 생성
env = OffScreenRenderEnv(
    bddl_file_name=bddl_path,
    camera_heights=256,
    camera_widths=256,
)

print("Environment created")

# BDDL의 scene 및 :init 조건을 기반으로 환경 초기화
# benchmark에 저장된 특정 init_state를 재현하는 것은 아님
obs = env.reset()

print("Environment reset success")
print("Observation keys:")
print(obs.keys())

# agentview 카메라 이미지 가져오기
image = obs["agentview_image"]

# LIBERO / robosuite 렌더링 이미지 방향 보정
image = image[::-1]

# OpenCV 저장을 위해 RGB -> BGR 변환
image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

cv2.imwrite("custom_bddl_test.png", image)

print("Saved: custom_bddl_test.png")

env.close()
```

##### 2) 실행

현재 터미널이 `(libero)` 환경인지 확인한 뒤 LIBERO 루트에서 실행한다. 전에 `egl` 오류가 나서 Windows에서는 `wgl`로 렌더링 설정을 바꿔 진행했다.

```powershell
conda activate libero
$env:MUJOCO_GL="wgl"
python .\test_custom_bddl.py
```

```text
Environment created
Environment reset success
Saved: custom_bddl_test.png
```

문구가 나오고 PNG에 예상한 장면이 보이면 BDDL 로딩, 환경 생성, 초기화, 이미지 출력이 정상적으로 이루어진 것이다. 현재는 initial state를 띄우는 과정이다. 7번에서는 action 전달과 goal 판정을 확인하고, 실제 서랍 열기 성공은 목표를 달성하는 action을 실행한 뒤 검증한다.

![Custom BDDL Test](./images/custom_bddl_test.png)

---

#### 6.4) 시뮬레이터를 실시간으로 모니터링하기

초기 PNG 한 장 대신 시뮬레이션 화면을 계속 확인하려면 PNG 저장 부분을 반복문으로 바꾼다. `env.step()`으로 새로운 observation을 받고, `agentview_image`를 OpenCV 창에 출력한다. 종료할 때는 시뮬레이터 그림을 한 번 클릭하고 `q`를 누른다.

이 과정은 위 파이프라인에서 7번의 action 실행과 observation 갱신 구간까지 연결된다. 다만 zero action만 입력하기 때문에 실제 서랍 열기 동작을 수행하는 예제는 아니다.

실시간 viewer는 7.2의 전체 코드에 초기 goal 검사와 zero action 테스트까지 포함되어 있다. 실시간 화면을 확인하려면 7.2의 코드로 파일 내용을 교체한 뒤 실행한다.

![LIBERO 실시간 agentview](./images/libero_live_agentview.png)

#### 6.5) Windows 렌더링 설정 유지하기

`conda activate libero`로 해당 환경에 들어간 상태에서 설정한다. 이 설정은 `libero` 환경을 활성화할 때 적용된다.

`$env:MUJOCO_GL="wgl"`을 실행할 때마다 입력하는 대신 `MUJOCO_GL=wgl`을 영구 설정하면 편하다.

```powershell
conda env config vars set MUJOCO_GL=wgl
```

설정한 후 conda 환경을 껐다 다시 켜야 적용된다.

```powershell
conda deactivate
conda activate libero
```

```powershell
$env:MUJOCO_GL
```

확인 후 결과가 `wgl`이면 설정 완료

앞으로는 두 명령어만 입력하면 실행이 가능하다.

```powershell
conda activate libero
python .\test_custom_bddl.py
```

### 7. LIBERO Custom Task Action 실행 및 Goal Condition 검증

> **7번은 위 [전체 파이프라인](#전체-파이프라인)의 `초기 goal 확인 → action 전달 → observation 갱신 → goal 검사` 구간이다.** 6번에서 만든 환경에 action을 전달하고, 실행 전후의 성공 조건을 확인한다. 7.2에서는 zero action으로 연결을 점검하고, 7.3에서는 goal condition이 정상적으로 판정되는지 확인한다.

이 단계에서 작성할 파일은 LIBERO 루트의 `test_custom_bddl.py`다. 6.4에서 설명한 실시간 viewer에 초기 goal 검사, zero action 10회 테스트, 화면의 `Success` 표시를 추가한다. 7.1은 초기 goal 검사 부분을 설명하고, 7.2는 그대로 저장해서 실행할 수 있는 전체 코드를 제공한다.

먼저 6.2에서 준비한 `custom_tasks/custom_test.bddl`이 있는지 확인한다. 터미널의 현재 위치는 `custom_tasks`나 `libero` 하위 폴더가 아닌, `requirements.txt`와 `custom_tasks`가 있는 LIBERO 루트여야 한다. 이 저장소에서는 `docs/W5/LIBERO`에 해당한다.

```powershell
conda activate libero
Test-Path .\custom_tasks\custom_test.bddl
```

결과가 `True`이면 아래 코드 작성으로 진행한다. `False`이면 6.2의 BDDL 복사 과정과 현재 폴더를 확인한다.

#### 7.1) initial state에서 goal이 False인지 확인

현재 서랍 task는 시작할 때 가운데 서랍이 닫혀 있고 goal은 열린 상태이므로 `False`가 예상된다. `True`가 나오면 초기 상태가 이미 goal을 만족하는지 BDDL과 장면을 확인한다.

`obs = env.reset()`과 초기화 성공 출력 다음에 아래 두 줄을 실행하면 초기 상태의 goal 충족 여부를 확인할 수 있다. 이 부분은 7.2의 전체 코드에 포함되어 있으므로, 전체 코드를 사용할 때 별도로 추가하지 않는다. 실행 후 `Initial goal success: False`를 확인한다.

```python
success = env.check_success()
print("Initial goal success:", success)
```

#### 7.2) env.step(action)이 정상적으로 동작하는지 확인

처음부터 Panda가 서랍을 당기는 action을 실행하지 않고, 먼저 값이 모두 0인 `zero action`을 여러 step 입력하여 `env.step(action)`의 action pipeline이 정상적으로 동작하는지 확인한다.

`env.step(action)`은 현재 action을 컨트롤러를 통해 MuJoCo 시뮬레이션에 반영하고 제어 step을 한 번 진행한 뒤, 새로운 observation과 reward 등의 정보를 반환한다.

이 예제의 기본 Panda 컨트롤러(`OSC_POSE`)에서 action은 다음과 같이 7차원으로 구성된다.

```text
[dx, dy, dz, dRx, dRy, dRz, gripper]
```

- `dx, dy, dz`: End-Effector 위치 변화량
- `dRx, dRy, dRz`: End-Effector 회전 변화량
- `gripper`: Gripper 제어값

이번 단계에서는 실제 task를 수행하는 것이 목적이 아니므로 모든 값을 0으로 설정한다.

`numpy`는 `test_custom_bddl.py` 파일 상단 import 부분에 넣는다. 아래 전체 코드에 이미 포함되어 있으므로 따로 추가하지 않는다.

**test_custom_bddl.py 작성**

LIBERO 루트에서 다음 명령으로 `test_custom_bddl.py`를 연다. 파일이 없으면 VSCode에서 새로 작성하고, 있으면 기존 내용을 아래 전체 코드로 교체한다. 파일 이름은 `test_custom_bddl.py`로 저장한다.

```powershell
code .\test_custom_bddl.py
```

아래는 현재 [`test_custom_bddl.py`](./custom_task_validation/test_custom_bddl.py)와 동일한 전체 코드다. 파일 처음부터 끝까지 이 코드 하나만 넣으면 되며, 6.3의 PNG 코드를 아래에 이어 붙이지 않는다. BDDL 경로는 Python 파일이 있는 폴더를 기준으로 계산하므로, `test_custom_bddl.py`와 `custom_tasks` 폴더를 같은 LIBERO 루트에 둔다.

실행 순서는 BDDL 경로 설정 → 환경 생성 → reset 1회 → 초기 goal 확인 → zero action 10회 테스트 → 실시간 viewer다. 10회 테스트는 `while True:` 반복문 앞에서 한 번만 실행된다. 환경 생성 전에 `env.step()`을 호출하거나 `env.reset()`을 중복으로 넣지 않는다.

```python
import os
import cv2
import numpy as np

os.environ["MUJOCO_GL"] = "wgl"

from libero.libero.envs.env_wrapper import OffScreenRenderEnv


base_dir = os.path.dirname(os.path.abspath(__file__))

bddl_path = os.path.join(
    base_dir,
    "custom_tasks",
    "custom_test.bddl"
)


# LIBERO 환경 생성
env = OffScreenRenderEnv(
    bddl_file_name=bddl_path,
    camera_heights=512,
    camera_widths=512,
)


# --------------------------------------------------
# 초기 상태 생성
# --------------------------------------------------

obs = env.reset()

print("Environment reset success")


# --------------------------------------------------
# 초기 상태에서 goal condition 확인
# --------------------------------------------------

success = env.check_success()

print("Initial goal success:", success)


# --------------------------------------------------
# Action interface 동작 확인
# --------------------------------------------------

# Panda OSC_POSE action
# [dx, dy, dz, dRx, dRy, dRz, gripper]

action = np.zeros(7, dtype=np.float32)

for step in range(10):

    # zero action을 입력하고 제어 step 한 번 진행
    obs, reward, done, info = env.step(action)

    # 각 step 이후 goal condition 확인
    success = env.check_success()

    print(
        f"Step: {step:02d} | "
        f"Reward: {reward} | "
        f"Done: {done} | "
        f"Success: {success}"
    )


# --------------------------------------------------
# 실시간 Viewer 시작
# --------------------------------------------------

print("LIBERO live viewer 시작")
print("종료: q 키")


while True:

    # 현재는 아무 행동도 하지 않는 zero action
    action = np.zeros(7, dtype=np.float32)

    # 한 control step 진행
    obs, reward, done, info = env.step(action)

    # 현재 goal condition 확인
    success = env.check_success()

    # agentview 카메라
    image = obs["agentview_image"]

    # 화면 방향 보정
    image = image[::-1]

    # OpenCV용 RGB -> BGR
    image = cv2.cvtColor(
        image,
        cv2.COLOR_RGB2BGR
    )

    # 화면에 현재 goal 성공 여부 표시
    cv2.putText(
        image,
        f"Success: {success}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2
    )

    # 실시간 화면 출력
    cv2.imshow(
        "LIBERO Live - agentview",
        image
    )

    # q 누르면 종료
    if cv2.waitKey(20) & 0xFF == ord("q"):
        break


env.close()

cv2.destroyAllWindows()
```

![7.2 실행 결과: Success False](./images/bddl_zero_action_test.png)

**실행 및 결과 확인**

VSCode에서 `Ctrl+S`로 저장한 뒤, 앞서 확인한 LIBERO 루트의 PowerShell 터미널에서 실행한다. Python 파일 안에서 robosuite / LIBERO를 import하기 전에 `MUJOCO_GL=wgl`을 설정하므로, 4번의 Windows 렌더링 오류 처리를 완료했다면 아래 명령으로 실행할 수 있다.

```powershell
conda activate libero
python .\test_custom_bddl.py
```

정상적으로 실행되면 다음과 비슷한 결과가 출력된다.

```text
Environment reset success
Initial goal success: False

Step: 00 | Reward: ... | Done: ... | Success: False
Step: 01 | Reward: ... | Done: ... | Success: False
Step: 02 | Reward: ... | Done: ... | Success: False
...
Step: 09 | Reward: ... | Done: ... | Success: False
LIBERO live viewer 시작
종료: q 키
```

10회 테스트가 끝나면 512×512 크기의 `LIBERO Live - agentview` 창이 열린다. Viewer 반복문에서도 zero action으로 `env.step()`을 호출하고, 매 step마다 `env.check_success()`를 다시 검사한다. 카메라 이미지는 상하 방향을 보정하고 RGB에서 BGR로 변환한 뒤 표시한다.

`cv2.putText()`가 영상 왼쪽 위에 `Success: False` 또는 `Success: True`를 표시하므로 화면을 보면서 현재 goal 충족 여부를 확인할 수 있다. Viewer 구간의 성공 여부는 화면에서 확인하고, 터미널의 `Step: 00`~`Step: 09` 출력은 viewer 시작 전 10회 테스트 결과다.

현재 파일은 PNG를 저장하는 대신 실시간 화면을 출력한다. 종료할 때는 영상 창을 클릭하고 `q`를 누른다. 반복문을 빠져나온 뒤 `env.close()`로 환경을 닫고 `cv2.destroyAllWindows()`로 OpenCV 창을 정리한다.

현재 입력한 action이 `np.zeros(7, dtype=np.float32)`이므로 Panda에 의도적인 위치 및 회전 변화량을 주지 않는다.

따라서 `Success: False`가 계속 출력되어도 정상이다. Zero action을 입력해도 물리 시뮬레이션은 계속 진행되므로 접촉이나 중력에 따른 변화까지 멈추는 것은 아니다.

> 7.2의 목적은 실제 서랍 열기 전에 `action → env.step() → MuJoCo simulation → observation 반환`과 goal 검사 과정이 정상적으로 동작하는지 확인하는 것이다. 전체 흐름에서의 위치는 위 [전체 파이프라인](#전체-파이프라인)에 표시했다.

이 단계가 정상적으로 동작하면 다음 단계에서 zero action을 실제 Panda movement action으로 변경하여 서랍을 여는 동작을 수행하고, 최종적으로 `env.check_success()`가 `False → True`로 변경되는지 검증한다.

#### 7.3) BDDL Goal Condition 정상 동작 확인

바로 Panda로 서랍을 잡아당기기 전에, 먼저 서랍을 실제로 열린 상태로 만들었을 때 `env.check_success()`가 `True`가 되는지 확인한다.

두 문제를 분리시켜서 판단하기 위함이다.

1. BDDL의 goal 정의가 정상인가? → goal 정의 확인
2. Panda action으로 서랍을 실제로 열 수 있는가? → action이 문제인지 확인

이 단계는 파이프라인의 `env.check_success() → BDDL의 :goal 조건 만족 여부 확인`에 해당한다.

현재 goal이 
```lisp
(:goal
    (And
        (Open wooden_cabinet_1_middle_region)
    )
)
```
 가운데 서랍 joint를 직접 열린 상태로 바꾼 뒤 env.check_success()가 True가 되는 지 확인

 `test_custom_bddl.py`에서 밑 코드를 7.2 zero action 10회 테스트가 끝난 직후, 실시간 viewer보다 앞에 넣는다.
 ```python
 # --------------------------------------------------
# 7.3 BDDL Goal Condition 정상 동작 확인
# --------------------------------------------------

print("\n===== Goal Condition Test =====")

# 초기 상태에서는 서랍이 닫혀 있으므로 False가 정상
success_before = env.check_success()
print("Before opening drawer:", success_before)


# BDDL goal에서 사용하는 가운데 서랍 region 이름
drawer_region = "wooden_cabinet_1_middle_region"

# 해당 region에 연결된 joint 확인
drawer_site = env.env.object_sites_dict[drawer_region]

print("Drawer joints:", drawer_site.joints)


# 가운데 서랍 joint를 직접 열린 상태로 변경
for joint_name in drawer_site.joints:

    # joint ID
    joint_id = env.sim.model.joint_name2id(joint_name)

    # 해당 joint의 허용 범위
    joint_range = env.sim.model.jnt_range[joint_id]

    # 현재 joint 위치
    qpos_addr = env.sim.model.get_joint_qpos_addr(joint_name)
    current_qpos = env.sim.data.qpos[qpos_addr]

    print(
        f"Joint: {joint_name} | "
        f"Current: {current_qpos} | "
        f"Range: {joint_range}"
    )

    # 현재 위치에서 더 먼 joint limit 방향을 open 방향으로 사용
    low = joint_range[0]
    high = joint_range[1]

    if abs(current_qpos - low) > abs(current_qpos - high):
        target_qpos = low
    else:
        target_qpos = high

    # joint limit 끝에 정확히 붙이지 않고 90% 정도까지 이동
    target_qpos = current_qpos + 0.9 * (target_qpos - current_qpos)

    env.sim.data.set_joint_qpos(
        joint_name,
        target_qpos
    )

    print("Set joint qpos:", target_qpos)


# 변경된 joint 상태를 MuJoCo에 반영
env.sim.forward()


# Goal condition 다시 확인
success_after = env.check_success()

print("After opening drawer:", success_after)
```

![7.3 실행 결과: Success True](./images/bddl_goal_condition_success.png)

```text
===== 7.3 Goal Condition Test =====
Drawer region: wooden_cabinet_1_middle_region
Drawer joints: ['wooden_cabinet_1_middle_level']
Before opening drawer: False
wooden_cabinet_1_middle_level -> range=[-0.16  0.01], target=-0.0069999999999999785
Goal after high-direction test: False
High direction was not open. Trying opposite direction.
wooden_cabinet_1_middle_level -> opposite target=-0.14300000000000002
After opening drawer: True
BDDL Goal Condition test SUCCESS
```
이 부분으로 출력이 성공했는 지 판단
```text
Before opening drawer: False
...
After opening drawer: True
BDDL Goal Condition test SUCCESS
```

이렇게 나오면 성공

#### 7.4) Panda OSC_POSE Action으로 실제 서랍 열기 및 Task Success 검증

7.3에서는 가운데 서랍의 MuJoCo joint 값을 직접 변경하여 BDDL의 Goal Condition이 `False → True`로 변경되는지 확인하였다. 7.4에서는 Panda 로봇에 실제 OSC_POSE action을 입력하여 서랍을 열고, 최종적으로 `env.check_success()`가 `True`가 되는지 확인한다.

**7.4에서 사용하는 용어**

**Drawer joint 뜻:** `Drawer`는 서랍, `joint`는 관절 또는 연결부를 뜻한다. 여기서는 **서랍의 이동 관절**, 즉 서랍이 캐비닛에 연결되어 레일을 따라 앞뒤로 움직이도록 하는 부분을 말한다.

실제 서랍으로 생각하면, 서랍 본체는 `body`, 레일을 따라 움직이는 방식은 `joint`, 손잡이의 모양과 접촉 부분은 `geom`에 해당한다. `site`는 물체에 붙여 둔 기준 위치나 영역이다.

| 용어 | 뜻 | 이번 코드에서의 역할 |
| --- | --- | --- |
| `body` | 함께 움직이는 물체의 한 부분 | 가운데 서랍 본체. 여기에 손잡이 geom과 서랍 내부 site가 붙어 있다. |
| `Drawer joint` — 서랍의 이동 관절 | 서랍을 캐비닛에 연결해 레일을 따라 앞뒤로 움직이게 하는 부분 | `wooden_cabinet_1_middle_level`. 한 축을 따라 이동하는 slide joint다. |
| `qpos` | joint의 현재 위치 값 | 이 slide joint에서는 이동량이며 단위는 m다. 현재 값과 goal을 비교해 서랍이 얼마나 열렸는지 확인한다. |
| `joint range` | joint가 움직일 수 있는 위치 범위 | `[-0.16, 0.01]`. 이 범위 자체가 성공 조건은 아니며, 성공 여부는 `env.check_success()`로 확인한다. |
| `joint axis` | joint 위치 값이 증가하는 방향 | 이 서랍이 레일을 따라 움직이는 방향을 나타낸다. 열리는 쪽은 이번 task에서 이 축의 반대 방향이다. |
| `site` | 위치·방향 또는 영역을 지정하는 가상의 기준. 자체적으로 충돌을 만들지는 않는다. | `wooden_cabinet_1_middle_region`은 서랍 내부 영역이다. Panda의 `grip_site`는 그리퍼 제어 기준 위치다. |
| `geom` | 물체를 이루는 모양. 설정에 따라 화면 표시나 충돌 계산에 사용된다. | `wooden_cabinet_1_g29`는 손잡이의 충돌 geom이다. 코드에서는 그 위치를 읽어 그리퍼의 접근 목표로 사용한다. |
| `EEF` / `End-Effector` | 로봇 팔 끝에서 작업하는 부분 | 이번 Panda에서는 그리퍼 끝의 제어 기준 위치를 뜻한다. `obs["robot0_eef_pos"]`로 현재 위치를 읽는다. |
| `local` / `world` 좌표계 | 물체에 붙은 좌표 기준 / 시뮬레이션 전체의 좌표 기준 | 캐비닛이 회전하면 local 축과 world 축도 달라진다. Panda가 어느 방향으로 당길지 정하려면 world axis를 사용한다. |

Joint·site·geom의 기본 정의는 [MuJoCo 공식 XML 문서](https://mujoco.readthedocs.io/en/stable/XMLreference.html#body-joint)를 참고했다. 표의 이름과 값은 현재 LIBERO의 wooden cabinet 모델과 실행 코드를 기준으로 한다.

**서랍 내부 영역과 손잡이 위치의 구분**

`wooden_cabinet_1_middle_region`은 가운데 서랍 내부에 설정된 site다. 7.3에서는 이 영역에 연결된 joint를 찾아 서랍이 열렸는지 확인한다. 이 site의 위치를 그대로 손잡이 위치로 사용하면 서랍 안쪽을 향하게 된다.

7.4에서는 손잡이 geom인 `wooden_cabinet_1_g29`의 위치를 접근 목표로 사용한다. 따라서 joint는 **어느 방향으로 움직이고 얼마나 열렸는지**, 손잡이 geom은 **그리퍼가 어디로 접근해야 하는지**를 확인하는 데 쓰인다.

**코드에 나온 변수 읽기**

- `joint_name2id()` / `geom_name2id()`: 이름으로 해당 joint·geom의 내부 번호를 찾는다. `joint_id`, `body_id`, `handle_id`는 좌표가 아니라 이 번호다.
- `geom_xpos[handle_id]`: 현재 손잡이 geom의 world 좌표 위치를 읽는다. 코드에서는 이를 `handle_pos`에 저장한다.
- `body_xmat[body_id]`: 서랍 body가 world 좌표계에서 어떤 방향을 향하는지 나타내는 회전 행렬이다. `body_rotation @ joint_axis_local`로 local 축을 world 축으로 바꾼다.
- `opening_direction`: 실제로 서랍을 당길 방향이다. 이번 task는 qpos가 감소할 때 열리므로 `-axis_world`를 사용한다.

기존 7.4.1의 정보 확인 내용은 이 단계에 합치고, 실행 코드는 아래 두 파일로 분리한다. 두 파일 모두 LIBERO 루트에 저장하며, `test_custom_bddl.py`에 이어 붙이지 않는다.

| 실행 파일 | 역할 |
| --- | --- |
| [`test_panda_drawer_info.py`](./custom_task_validation/test_panda_drawer_info.py) | Panda EEF 위치, Drawer joint world axis, 손잡이 관련 site·geom 정보 확인 |
| [`test_panda_drawer_action.py`](./custom_task_validation/test_panda_drawer_action.py) | 손잡이에 접근 → 잡기 → 당기기 → Task Success 확인 |

두 파일은 각각 `env.reset()`으로 닫힌 초기 상태에서 시작한다. 7.3의 joint 직접 변경 코드를 실행하지 않으므로, 이미 열린 서랍에서 `True`가 나오는 경우와 구분할 수 있다.

**먼저 Panda End-Effector와 Drawer Joint 정보 확인**

7.3에서 확인한 가운데 서랍 joint는 `wooden_cabinet_1_middle_level`이고, 범위는 `[-0.16, 0.01]`이다. `qpos ≈ -0.007`에서는 Goal이 `False`, `qpos ≈ -0.143`에서는 `True`였으므로 joint qpos가 음수 방향으로 이동할수록 열리는 구조임을 확인하였다.

하지만 joint qpos의 음수 방향이 곧바로 world 좌표계의 -X, -Y, -Z를 의미하는 것은 아니다. 따라서 action을 작성하기 전에 Panda End-Effector 위치, 서랍 joint의 world axis, 손잡이 위치를 먼저 확인한다.

LIBERO 루트에 `test_panda_drawer_info.py`를 만들고 아래 전체 코드를 저장한다. 위치와 joint 정보를 출력한 뒤 종료하는 코드다.

```python
import os

# robosuite / LIBERO import 전에 Windows 렌더링 설정
os.environ["MUJOCO_GL"] = "wgl"

from libero.libero.envs.env_wrapper import OffScreenRenderEnv


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    bddl_path = os.path.join(base_dir, "custom_tasks", "custom_test.bddl")

    env = OffScreenRenderEnv(
        bddl_file_name=bddl_path,
        camera_heights=512,
        camera_widths=512,
    )

    try:
        obs = env.reset()

        # Panda End-Effector 현재 위치
        eef_pos = obs["robot0_eef_pos"]

        print("\n===== Panda / Drawer Info =====")
        print("EEF position:", eef_pos)
        print("Initial goal success:", env.check_success())

        # 가운데 서랍 joint
        joint_name = "wooden_cabinet_1_middle_level"
        joint_id = env.sim.model.joint_name2id(joint_name)

        # joint range와 local axis
        joint_range = env.sim.model.jnt_range[joint_id]
        joint_axis_local = env.sim.model.jnt_axis[joint_id]

        # 해당 joint가 연결된 body의 회전 행렬
        body_id = env.sim.model.jnt_bodyid[joint_id]
        body_rotation = env.sim.data.body_xmat[body_id].reshape(3, 3)

        # joint axis를 world 좌표계로 변환
        joint_axis_world = body_rotation @ joint_axis_local

        print("Drawer joint:", joint_name)
        print("Drawer joint range:", joint_range)
        print("Drawer joint local axis:", joint_axis_local)
        print("Drawer joint world axis:", joint_axis_world)

        # 서랍 손잡이와 관련된 site 이름과 위치 확인
        print("\n===== Cabinet / Handle Sites =====")

        for i in range(env.sim.model.nsite):
            name = env.sim.model.site_id2name(i)
            if name is not None:
                lower_name = name.lower()
                if "cabinet" in lower_name or "handle" in lower_name:
                    print("SITE:", name, "POSITION:", env.sim.data.site_xpos[i])

        # site 출력에서 손잡이를 찾기 어려울 때 참고할 geom 정보
        print("\n===== Cabinet / Handle Geoms =====")

        for i in range(env.sim.model.ngeom):
            name = env.sim.model.geom_id2name(i)
            if name is not None:
                lower_name = name.lower()
                if "cabinet" in lower_name or "handle" in lower_name:
                    print("GEOM:", name, "POSITION:", env.sim.data.geom_xpos[i])

    finally:
        env.close()


if __name__ == "__main__":
    main()
```

LIBERO 루트의 PowerShell 터미널에서 실행한다.

```powershell
conda activate libero
python .\test_panda_drawer_info.py
```

출력에서 `Initial goal success: False`, joint range, world axis, Cabinet / Handle 관련 site 또는 geom 이름과 위치를 확인한다. 현재 asset의 가운데 손잡이 충돌 geom은 `wooden_cabinet_1_g29`다. World axis는 대략 `[0, -1, 0]`이므로 이 배치에서 서랍이 열리는 방향은 반대쪽인 world `+Y`다. 물체 위치는 초기화할 때 달라질 수 있으므로 코드에서 현재 모델의 좌표를 읽어 사용한다.

**Panda OSC_POSE Action으로 실제 서랍 열기**

실제 서랍 열기는 다음 순서로 진행한다.

```text
손잡이 위치와 서랍이 움직이는 축 확인
    ↓
Gripper open → 손잡이 앞쪽 위에서 자세 맞추기 → 손잡이에 접근
    ↓
Gripper close → 손잡이를 잡은 상태로 잠시 유지
    ↓
서랍 opening 방향으로 End-Effector 이동
    ↓
env.check_success(): False → True 확인
```

OSC_POSE action의 구성은 7.2와 같으며, 마지막 값으로 gripper를 제어한다. PandaGripper에서는 `-1`이 open, `+1`이 close다. 위치와 회전 오차를 기본 OSC_POSE의 action scale에 맞춰 변환하고, joint 값은 직접 수정하지 않는다.

LIBERO 루트에 `test_panda_drawer_action.py`를 만들고 아래 전체 코드를 저장한다. `HANDLE_GEOM`은 현재 wooden cabinet asset의 손잡이 이름이므로, 다른 asset을 사용하면 정보 확인 코드로 이름을 다시 확인한다.

```python
import argparse
import os

os.environ["MUJOCO_GL"] = "wgl"

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from libero.libero.envs.env_wrapper import OffScreenRenderEnv


JOINT_NAME = "wooden_cabinet_1_middle_level"
HANDLE_GEOM = "wooden_cabinet_1_g29"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true", help="OpenCV 창 없이 실행")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    env = OffScreenRenderEnv(
        bddl_file_name=os.path.join(base_dir, "custom_tasks", "custom_test.bddl"),
        camera_heights=128 if args.headless else 512,
        camera_widths=128 if args.headless else 512,
    )

    try:
        env.seed(args.seed)
        obs = env.reset()
        print("Initial goal success:", env.check_success())
        if env.check_success():
            raise RuntimeError("서랍이 닫힌 초기 상태에서 시작해야 합니다.")

        joint_id = env.sim.model.joint_name2id(JOINT_NAME)
        body_id = env.sim.model.jnt_bodyid[joint_id]
        rotation = env.sim.data.body_xmat[body_id].reshape(3, 3)
        axis_world = rotation @ env.sim.model.jnt_axis[joint_id]
        # 이 task는 joint qpos의 음수 방향으로 서랍이 열린다.
        opening_direction = -axis_world / np.linalg.norm(axis_world)

        handle_id = env.sim.model.geom_name2id(HANDLE_GEOM)
        handle_pos = env.sim.data.geom_xpos[handle_id].copy()
        print("Handle position:", handle_pos)
        print("Opening direction:", opening_direction)

        # 손가락은 손잡이 위아래로 닫히고, 손끝은 서랍을 향한다.
        tool_z = -opening_direction
        tool_x = np.array([0.0, 0.0, 1.0])
        tool_y = np.cross(tool_z, tool_x)
        target_rotation = np.column_stack((tool_x, tool_y, tool_z))

        step_count = 0
        eef_site_id = env.env.robots[0].eef_site_id

        def eef_rotation():
            # obs의 eef_quat은 hand body 기준이며 grip_site와 회전 offset이 있다.
            return env.sim.data.site_xmat[eef_site_id].reshape(3, 3).copy()

        def step_toward(target, gripper, phase):
            nonlocal obs, step_count
            # OSC_POSE는 정규화된 delta action을 받는다.
            # 기본 output_max: 위치 0.05 m, 회전 0.5 rad.
            current_rotation = eef_rotation()
            rotation_error = Rotation.from_matrix(
                target_rotation @ current_rotation.T
            ).as_rotvec()
            action = np.zeros(7, dtype=np.float32)
            action[:3] = np.clip((target - obs["robot0_eef_pos"]) / 0.05, -0.4, 0.4)
            action[3:6] = np.clip(rotation_error / 0.5, -0.4, 0.4)
            action[6] = gripper
            obs, reward, done, info = env.step(action)
            step_count += 1
            if step_count % 25 == 0:
                print(
                    f"{phase} | Step: {step_count} | "
                    f"Joint: {env.sim.data.get_joint_qpos(JOINT_NAME):.4f} | "
                    f"Success: {env.check_success()}"
                )
            if not args.headless:
                frame = cv2.cvtColor(obs["agentview_image"][::-1], cv2.COLOR_RGB2BGR)
                cv2.putText(
                    frame, f"{phase} | Success: {env.check_success()}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2,
                )
                cv2.imshow("Panda Drawer Action", frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                    raise KeyboardInterrupt

        def move_to(target, gripper, phase, max_steps=200):
            for _ in range(max_steps):
                step_toward(target, gripper, phase)
                error = np.linalg.norm(target - obs["robot0_eef_pos"])
                rotation_error = Rotation.from_matrix(
                    target_rotation @ eef_rotation().T
                ).magnitude()
                if error < 0.015 and rotation_error < 0.12:
                    return
            raise RuntimeError(
                f"{phase}: 목표 위치에 도달하지 못했습니다. "
                f"EEF error={error:.4f} m, rotation error={rotation_error:.4f} rad"
            )

        # 1. 손잡이 앞쪽 위에서 자세를 맞춘 뒤 서랍에 접근한다.
        pregrasp = handle_pos + 0.10 * opening_direction
        above = pregrasp + np.array([0.0, 0.0, 0.15])
        move_to(above, -1.0, "Above handle")
        move_to(pregrasp, -1.0, "Before handle")

        # 2. 손잡이 중앙에 접근한 뒤 gripper를 닫는다.
        grasp = handle_pos.copy()
        move_to(grasp, -1.0, "Approach handle")
        for _ in range(30):
            step_toward(grasp, 1.0, "Close gripper")

        # 3. 손잡이를 잡은 상태로 서랍의 opening 방향으로 당긴다.
        start = obs["robot0_eef_pos"].copy()
        for distance in np.linspace(0.0, 0.18, 180):
            step_toward(start + distance * opening_direction, 1.0, "Pull drawer")
            if env.check_success():
                break

        success = env.check_success()
        print("Final drawer joint:", env.sim.data.get_joint_qpos(JOINT_NAME))
        print("Final goal success:", success)
        output_path = os.path.join(base_dir, "images", "panda_drawer_action_result.png")
        frame = cv2.cvtColor(obs["agentview_image"][::-1], cv2.COLOR_RGB2BGR)
        cv2.putText(
            frame, f"Success: {success}", (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if not cv2.imwrite(output_path, frame):
            raise RuntimeError("결과 이미지 저장 실패")
        print("Saved:", output_path)
        if not success:
            raise RuntimeError("서랍 열기에 실패했습니다. 접근 위치와 grasp 상태를 확인하세요.")

    finally:
        env.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("사용자가 실행을 종료했습니다.")
```

![7.4 Panda action 실행 결과: Success True](./images/panda_drawer_action_result.png)

저장한 뒤 실행한다. 창에는 각 단계와 현재 성공 여부가 표시된다. 실행 중 영상 창에서 `q`, `Q`, `ESC`를 누르거나 터미널에서 `Ctrl+C`를 누르면 종료한다.

```powershell
conda activate libero
python .\test_panda_drawer_action.py
```

창 없이 실행하려면 다음 명령을 사용한다. 이 경우 렌더링 이미지는 128×128이며, 일반 실행에서는 512×512다.

```powershell
python .\test_panda_drawer_action.py --headless
```

현재 `custom_test.bddl`, 기본 OSC_POSE 컨트롤러, `seed=0`으로 창 없이 실행했을 때 다음 결과를 확인하였다.

```text
Initial goal success: False
...
Final drawer joint: -0.1400351567647335
Final goal success: True
```

결과 이미지는 `LIBERO/images/panda_drawer_action_result.png`에 저장된다. Panda가 `env.step(action)`으로 손잡이를 잡고 서랍을 연 뒤 `env.check_success()`가 `False → True`로 바뀌면 실제 task 수행에 성공한 것이다. 목표 위치에 도달하지 못하거나 최종 goal이 `False`이면 오류를 출력하므로, 접근 위치와 grasp 상태를 확인한다.

### 8. BDDL 구성 요소 변경 및 새로운 요소 추가를 통한 Custom Task 검증

#### 8.1) 검증 목적과 고려 사항

기존 Tabletop 환경에서 새로운 Custom Task를 정의할 때 `Object`, `Region`, `Init`, `Goal` 네 요소를 검토한다. 네 요소를 모두 변경해야 하는 것은 아니다. 먼저 기존 Task에서 유지할 항목과 바꿀 항목을 정하고, 변경한 정의가 환경의 초기 상태와 성공 판정에 실제로 반영되는지 확인한다.

| 요소 | 구체적으로 고려할 사항 |
| --- | --- |
| `Object` | 조작 대상이 무엇인지, 기존 BDDL의 물체를 그대로 사용할지 또는 LIBERO에 등록된 다른 물체를 `:objects`에 추가할지 정한다. 새 물체를 쓰면 배치할 공간과 초기 조건도 함께 확인한다. |
| `Region` | 물체의 시작 위치와 목표 위치를 어느 `:target`을 기준으로 정의할지 정한다. Table을 유지하고 작업 영역만 바꾸는 경우에는 `main_table`을 그대로 두고 `:ranges`의 좌표가 물체 크기와 로봇 도달 범위에 맞는지 확인한다. |
| `Init` | 시작 시 각 물체가 어느 Region에 놓이고 Fixture가 어떤 상태여야 하는지 정한다. `:init`에서 참조하는 물체와 Region의 이름이 실제 정의와 일치하는지, 초기 배치가 Goal을 이미 만족하지 않는지 확인한다. |
| `Goal` | 성공으로 인정할 물체와 상태 또는 영역을 정한다. `:goal`에 사용한 Predicate가 LIBERO에서 지원되는지 확인하고, 초기 상태에서는 `False`, 목표 상태에서는 `True`가 되는지 검사한다. |

`Predicate`는 시뮬레이션의 현재 상태가 조건을 만족하는지 `True` 또는 `False`로 판단하는 함수다. 아래 코드는 `docs/W5/LIBERO/libero/libero/envs/predicates/base_predicates.py`의 [`On`과 `Open` 구현](./custom_task_validation/reference_code/libero/libero/envs/predicates/base_predicates.py)에서 가져왔다.

```python
class On(BinaryAtomic):
    def __call__(self, arg1, arg2):
        return arg2.check_ontop(arg1)

class Open(UnaryAtomic):
    def __call__(self, arg):
        return arg.is_open()
```

예를 들어 BDDL의 `(On wine_bottle_1 main_table_wine_bottle_region)`은 `On`에 와인병과 영역을 전달한다. `check_ontop()`이 와인병이 그 영역 위에 있다고 판단하면 `True`를 반환한다. `(Open wooden_cabinet_1_middle_region)`은 `is_open()`으로 해당 서랍이 열렸는지 판단한다. `:init`은 시작할 때 만족시킬 조건을, `:goal`은 성공 여부를 확인할 조건을 적는 곳이다. `And`는 여러 조건을 모두 만족해야 한다는 논리 연산자다.

| 요소 | BDDL에서 확인할 항목 | 검증 기준 |
| --- | --- | --- |
| `Object` | `:objects`의 인스턴스 이름과 물체 종류, `:obj_of_interest`의 대상 | 물체 종류가 LIBERO에 등록되어 있고 인스턴스 이름이 중복되지 않는지, Init·Goal에서 참조하는 물체가 실제로 선언되어 생성되는지 확인한다. |
| `Region` | `:regions`의 영역 이름, `:target`, `:ranges`, 필요한 경우 `:yaw_rotation` | `:target`이 존재하는 Table·Fixture·Object를 가리키는지, 좌표 범위와 회전이 유효한지, 물체를 놓을 수 있고 로봇이 도달할 수 있는지 확인한다. Table을 유지하면서 작업 영역만 바꾸는 경우에는 `:target`을 유지하고 `:ranges`를 검토한다. |
| `Init` | `:init`의 각 Predicate와 인수로 사용한 Object·Region·Fixture 이름 | 참조하는 이름과 Predicate가 유효한지, 서로 충돌하는 초기 조건이 없는지, `env.reset()` 후 지정한 위치와 상태가 재현되는지 확인한다. |
| `Goal` | `:goal`의 Predicate, 논리 조합(`And` 등), 목표 대상 | 성공 조건이 Task 지시문과 일치하고 지원되는 Predicate로 표현되는지 확인한다. 초기 상태에서는 `env.check_success()`가 `False`이고 목표를 달성한 상태에서는 `True`인지 검증한다. |

`Fixture`는 캐비닛·스토브처럼 장면에 배치되는 고정 요소이고, `Table`은 물체 배치의 기준면이다. 기존 Fixture와 Table을 유지한다면 추가 선언은 필요 없다. Table 위 작업 영역만 바꾸는 경우에는 Region의 `:target`을 유지하고 `:ranges`를 조정한다. Fixture나 Table 자체를 바꿀 경우에는 연결된 Region과 Init의 참조도 함께 확인한다.

LIBERO에 이미 등록된 물체와 지원되는 Predicate는 BDDL에 추가해 사용할 수 있다. LIBERO에 없는 물체 모델이나 새로운 판정 방식이 필요하다면 BDDL 수정 외에 모델 등록 또는 Predicate 구현이 필요하다. 해당 확장 범위는 뒤에서 별도로 정리한다.

#### 8.2) 새로운 Task 설계 및 Object·Region·Init·Goal 선정

기존 서랍 열기 Task를 기준으로 **두 개의 BDDL 변경안**을 설계한다. 두 변경안은 물체가 어디에 선언되어 있는지에 따라 구분한다.

- **검증안 A — 현재 Custom BDDL의 물체 사용:** [`custom_test.bddl`](./custom_task_validation/custom_tasks/custom_test.bddl)의 `:objects`에 선언되어 있고 [초기 상태 이미지](./images/custom_bddl_test.png)에서도 확인되는 `plate_1`을 사용한다. 검은색 그릇은 BDDL에 선언되어 있지만 이 이미지에서 명확히 식별되지 않으므로 검증 대상으로 선택하지 않는다.
- **검증안 B — LIBERO에 등록된 물체 추가:** 현재 `custom_test.bddl`의 `:objects`에는 `milk`가 없다. 하지만 LIBERO의 [`hope_objects.py`](./custom_task_validation/reference_code/libero/libero/envs/objects/hope_objects.py)에 `Milk` 클래스가 있고, [기존 LIBERO BDDL](./custom_task_validation/reference_code/libero/libero/bddl_files/libero_object/pick_up_the_milk_and_place_it_in_the_basket.bddl)에서 `milk_1 - milk`를 사용한다. 따라서 새 물체 모델을 구현하지 않고 Custom BDDL에 `milk_1` 인스턴스를 추가한다.

현재 Custom BDDL에서 `plate_1`은 다음 `:objects` 항목에 선언되어 있다.

```lisp
(:objects
    akita_black_bowl_1 - akita_black_bowl
    cream_cheese_1 - cream_cheese
    wine_bottle_1 - wine_bottle
    plate_1 - plate
)
```

두 변경안은 별도 BDDL 파일로 저장해 로딩 결과와 Goal 판정을 구분한다. Table인 `main_table`, 기존 Fixture, Panda 로봇과 제어 설정은 유지한다.

| 구분 | 검증안 A: 기존 물체 사용 | 검증안 B: 새 물체 인스턴스 추가 |
| --- | --- | --- |
| Task 지시문 | 접시를 스토브 앞쪽으로 밀기 (`Push the plate to the front of the stove`) | 우유를 접시 위에 올려놓기 (`Put the milk on the plate`) |
| `Object` | 현재 Custom BDDL의 `:objects`에 선언된 `plate_1` 사용 | 현재 Custom BDDL에는 없는 `milk_1 - milk`를 `:objects`에 추가하고 기존 `plate_1`은 유지 |
| `Region` | 기존 `main_table_plate_region`에서 시작하고, 현재 BDDL의 `main_table_stove_front_region`을 목표 영역으로 사용. 시작 Region의 범위는 초기 `On` 판정에 맞게 조정 | `main_table`을 대상으로 `milk_region` 추가. 기존 시작 Region의 범위도 초기 `On` 판정에 맞게 조정 |
| `Init` | `(On plate_1 main_table_plate_region)` 유지 | `(On milk_1 main_table_milk_region)` 추가. 접시는 기존 영역에 유지 |
| `Goal` | `(And (On plate_1 main_table_stove_front_region))` | `(And (On milk_1 plate_1))` |
| 함께 맞출 항목 | `:language`를 Task 지시문으로 수정하고 `:obj_of_interest`에 `plate_1`과 `main_table_stove_front_region`을 함께 지정 | `:language`를 Task 지시문으로 수정하고 `:obj_of_interest`에 `milk_1`과 `plate_1`을 함께 지정 |

검증안 A는 현재 Custom BDDL에 있는 접시와 시작 위치를 유지하면서 Region의 범위를 조정하고 `On` Goal을 판정하는 기준 사례다. 검증안 B에서는 추가한 `milk_1`이 생성되는지, 새 Region과 Init이 우유를 의도한 위치에 놓는지, 우유를 접시 위로 옮겼을 때 Goal이 달성되는지를 순서대로 확인한다.

새 Region의 좌표는 기존 물체와의 겹침, 우유의 크기, Panda의 접근 가능 범위를 보고 8.3에서 확정한다. 두 검증안 모두 `env.reset()` 직후 Goal은 `False`여야 하며, 목표 상태를 만든 뒤 `env.check_success()`가 `True`가 되어야 한다. 이 값은 **검증 기준**이다. Goal 판정과 실제 로봇 Action의 성공 여부는 각각 기록한다.

#### 8.3) 변경 요소를 반영한 Custom BDDL 작성

8.2에서 정의한 검증안 A와 검증안 B를 실제 BDDL 파일로 작성한다.

작성하기 전에 LIBERO 공식 파일을 기준으로 사용할 요소가 실제로 존재하는지 확인

```text
검증안 A
push_the_plate_to_the_front_of_the_stove.bddl
→ LIBERO 공식 BDDL에 실제 존재

검증안 B에서 사용하는 milk
hope_objects.py
→ Milk class 실제 존재

milk_1 - milk
→ 기존 LIBERO BDDL에서 실제 사용

(On milk_1 ...)
→ 기존 LIBERO BDDL의 Init에서 실제 사용

(On object plate_1)
→ 기존 put_the_bowl_on_the_plate.bddl에서 실제 사용
```

따라서 검증안 A는 LIBERO의 공식 Task를 바탕으로 시작 Region 범위를 조정하고,
검증안 B는 LIBERO에 실제로 존재하는 Object와 Predicate를 조합하여
현재 BDDL에는 없는 새로운 Task를 작성한다.

단, 검증안 B의 `milk + main_table + plate` 조합 자체가
LIBERO 공식 BDDL에 그대로 존재하는 것은 아니다.

즉 검증안 B는 다음과 같다.

```text
실제로 존재하는 LIBERO 요소
        +
새로운 BDDL 조합
        ↓
Custom Task 작성
```

실제 환경에서 정상적으로 생성되는지는 8.4에서 검증한다.

---

##### 8.3.1) 검증용 BDDL 파일 분리

기존 `custom_test.bddl`은 서랍 Task 기준 파일로 그대로 보관한다.

검증안 A와 B는 다음 두 파일로 분리한다.

```text
custom_tasks/

├── custom_test.bddl
│   └── 기존 가운데 서랍 Task
│
├── custom_goal_change.bddl
│   └── 검증안 A
│       기존 Object와 Region을 사용하고 서랍 Task의 Goal 변경
│
└── custom_milk_task.bddl
    └── 검증안 B
        milk Object + 새 Region + 새 Init + 새 Goal
```

---

##### 8.3.2) 검증안 A — 공식 Goal 변경 Task 작성

검증안 A의 Task는 다음과 같다.

```text
Push the plate to the front of the stove
```

이 Task는 LIBERO 공식 BDDL에 실제로 존재한다.

파일 위치:

```text
libero/libero/bddl_files/libero_goal/
push_the_plate_to_the_front_of_the_stove.bddl
```

공식 BDDL을 복사해 Task 구조의 기준으로 사용한다. 복사 후 초기 배치의 `On` 판정과 사진상 위치가 일치하도록 시작 Region 세 곳의 범위를 조정한다. 선언되지 않은 `bowl_drainer_1`을 참조하는 미사용 Region 두 개도 제거한다.

LIBERO 루트의 PowerShell에서 실행한다.

```powershell
Copy-Item `
".\libero\libero\bddl_files\libero_goal\push_the_plate_to_the_front_of_the_stove.bddl" `
".\custom_tasks\custom_goal_change.bddl" `
-Force
```

복사 후 파일을 열어 아래 Region 범위를 적용한다.

```powershell
code .\custom_tasks\custom_goal_change.bddl
```

| 시작 Region | 적용할 `:ranges` | 유지하는 것 |
| --- | --- | --- |
| `plate_region` | `(0.03 -0.04 0.07 0.0)` | 중심 `(0.05, -0.02)`, `:target main_table` |
| `wine_bottle_region` | `(-0.22 -0.07 -0.18 -0.03)` | 중심 `(-0.20, -0.05)`, `:target main_table` |
| `cream_cheese_region` | `(-0.07 0.11 -0.03 0.15)` | 중심 `(-0.05, 0.13)`, `:target main_table` |

세 Region은 중심을 유지하고 폭을 0.02 m에서 0.04 m로 넓혔다. 두 검증안에 같은 범위를 적용했으며, `seed=0`에서 `env.reset()` 후 각 `On` 조건을 다시 평가해 확인한다.

수정한 파일을 저장한 뒤 내용을 확인한다.

```powershell
Get-Content .\custom_tasks\custom_goal_change.bddl
```

검증안 A의 핵심 정의는 다음과 같다.

```lisp
(:language Push the plate to the front of the stove)
```

Object는 기존 `plate_1`을 그대로 사용한다.

```lisp
(:objects
    akita_black_bowl_1 - akita_black_bowl
    cream_cheese_1 - cream_cheese
    wine_bottle_1 - wine_bottle
    plate_1 - plate
)
```

plate의 초기 Region 이름과 중심은 유지하고 범위를 다음과 같이 적용한다.

```lisp
(plate_region
    (:target main_table)
    (:ranges (
        (0.03 -0.04 0.07 0.0)
    ))
)
```

초기 상태는 다음과 같다.

```lisp
(On plate_1 main_table_plate_region)
```

Goal에서 사용하는 `stove_front_region` 역시
기존 BDDL에 실제로 존재한다.

```lisp
(stove_front_region
    (:target main_table)
    (:ranges (
        (-0.09 0.16999999999999998 -0.010000000000000002 0.25)
    ))
)
```

`obj_of_interest`는 공식 BDDL과 동일하게 다음 두 항목을 사용한다.

```lisp
(:obj_of_interest
    plate_1
    main_table_stove_front_region
)
```

Goal은 다음과 같다.

```lisp
(:goal
    (And
        (On plate_1 main_table_stove_front_region)
    )
)
```

따라서 검증안 A의 구조는 다음과 같다.

```text
plate_1

초기 상태:
main_table_plate_region

        ↓
Panda Action

목표 상태:
main_table_stove_front_region

        ↓

(On plate_1 main_table_stove_front_region)

        ↓

env.check_success()
False → True
```

검증안 A에서는 새로운 Object나 Region을 추가하지 않는다.

```text
Object  → 기존 것 사용
Region  → 기존 것 사용
Init    → 기존 것 사용
Goal    → 변경
```

따라서 기존 서랍 Task에서 Goal이 달라진 작업도 시뮬레이터에 로딩되는지 확인하는 기준 Task로 사용한다. 이 Goal 자체는 공식 접시 밀기 Task에서 가져왔다.

---

##### 8.3.3) 검증안 B — milk Object를 추가한 새로운 Custom BDDL 작성

검증안 B의 Task는 다음과 같다.

```text
Put the milk on the plate
```

현재 `custom_test.bddl`에는 `milk`가 존재하지 않는다.

하지만 LIBERO의

```text
libero/libero/envs/objects/hope_objects.py
```

파일에는 다음과 같이 `Milk`가 실제 Object로 등록되어 있다.

```python
@register_object
class Milk(HopeBaseObject):
    def __init__(self, name="milk", obj_name="milk"):
        ...
```

또한 LIBERO 공식 BDDL인

```text
pick_up_the_milk_and_place_it_in_the_basket.bddl
```

에서도 실제로 다음 선언을 사용한다.

```lisp
milk_1 - milk
```

따라서 새로운 Object 모델을 만드는 것이 아니라
LIBERO가 이미 지원하는 `milk` Object의 instance인
`milk_1`을 현재 Tabletop BDDL에 추가한다.

먼저 기존 BDDL을 복사한다.

```powershell
Copy-Item `
".\custom_tasks\custom_test.bddl" `
".\custom_tasks\custom_milk_task.bddl" `
-Force
```

파일을 연다.

```powershell
code .\custom_tasks\custom_milk_task.bddl
```

검증안 A와 같은 기준으로 `plate_region`, `wine_bottle_region`, `cream_cheese_region`의 범위도 위 표에 맞춘다.

---

##### 8.3.4) 새로운 milk Region 추가

`milk_1`을 초기 상태에서 `main_table` 위에 배치하려면
새로운 Region이 필요하다.

이번에는 임의의 좌표를 새로 추측하지 않고,
현재 동일한 Tabletop 환경에서 LIBERO 공식 BDDL이 실제로 사용하는
`stove_front_region`의 좌표 범위를 기준으로 사용한다.

공식 Region은 다음과 같다.

```lisp
(stove_front_region
    (:target main_table)
    (:ranges (
        (-0.09 0.16999999999999998 -0.010000000000000002 0.25)
    ))
)
```

이 좌표는 현재 Tabletop 장면에서 실제 BDDL이 사용하는
`main_table` 위의 영역이다.

검증안 B에서는 같은 좌표 범위를 사용하지만
새로운 Region 이름인 `milk_region`을 만든다.

`:regions` 내부에 다음 내용을 추가한다.

```lisp
(milk_region
    (:target main_table)
    (:ranges (
        (-0.09 0.16999999999999998 -0.010000000000000002 0.25)
    ))
)
```

즉,

```text
기존 실제 Region
stove_front_region
        ↓
동일한 main_table 좌표 범위 사용
        ↓
새 Region 이름
milk_region
```

으로 작성한다.

Region 이름이 `milk_region`이고 target이 `main_table`이므로
Init에서 사용하는 전체 Region 이름은 다음과 같다.

```text
main_table_milk_region
```

주의할 점은 이 좌표가 기존 LIBERO 장면에서 사용된다는 것은 확인했지만,
`milk_1`을 이 위치에 놓았을 때 물체 크기까지 포함하여
충돌 없이 초기화되는지는 아직 실행으로 확인하지 않은 상태다.

이 부분은 8.4의 `env.reset()`에서 직접 검증한다.

---

##### 8.3.5) milk Object 추가

`:objects`에 다음 한 줄을 추가한다.

```lisp
milk_1 - milk
```

변경 후 다음과 같다.

```lisp
(:objects
    akita_black_bowl_1 - akita_black_bowl
    cream_cheese_1 - cream_cheese
    wine_bottle_1 - wine_bottle
    plate_1 - plate
    milk_1 - milk
)
```

여기서

```text
milk
= LIBERO에 실제 등록되어 있는 Object type

milk_1
= 현재 Custom BDDL에서 새로 만든 instance
```

이다.

---

##### 8.3.6) obj_of_interest 변경

기존 서랍 Task의 `obj_of_interest`는 다음과 같다.

```lisp
(:obj_of_interest
    wooden_cabinet_1_middle_region
)
```

새로운 Task에서는 `milk_1`을 조작하여 `plate_1` 위에 올리는 것이므로
두 Object를 사용한다.

```lisp
(:obj_of_interest
    milk_1
    plate_1
)
```

기존 LIBERO의 Object-to-Object Task에서도
조작 대상과 목표 대상을 함께 `obj_of_interest`에 지정하는 형태를 사용한다.

---

##### 8.3.7) 새로운 Init Condition 추가

기존 Init Condition은 유지하면서
milk의 초기 배치 조건을 추가한다.

```lisp
(On milk_1 main_table_milk_region)
```

전체 Init은 다음과 같다.

```lisp
(:init
    (On wine_bottle_1 main_table_wine_bottle_region)
    (On akita_black_bowl_1 main_table_akita_black_bowl_region)
    (On plate_1 main_table_plate_region)
    (On cream_cheese_1 main_table_cream_cheese_region)

    (On milk_1 main_table_milk_region)

    (On wooden_cabinet_1 main_table_cabinet_region)
    (On flat_stove_1 main_table_stove_region)
    (On wine_rack_1 main_table_wine_rack_region)
)
```

따라서 `env.reset()`을 실행하면 의도한 초기 상태는 다음과 같다.

```text
milk_1
    ↓
main_table_milk_region

plate_1
    ↓
main_table_plate_region
```

milk와 plate가 서로 다른 Region에서 시작하므로
초기 Goal은 `False`가 되어야 한다.

---

##### 8.3.8) 새로운 Goal 작성

기존 Goal:

```lisp
(:goal
    (And
        (Open wooden_cabinet_1_middle_region)
    )
)
```

을 제거하고 다음 Goal을 사용한다.

```lisp
(:goal
    (And
        (On milk_1 plate_1)
    )
)
```

`On` Predicate 자체는 기존 LIBERO에서 실제로 사용되고 있으며,
Object를 `plate_1` 위에 올려놓는 Goal 역시
기존 `put_the_bowl_on_the_plate.bddl`에서 사용되는 방식이다.

이번 Custom Task에서는 그 첫 번째 Object만

```text
akita_black_bowl_1
```

대신

```text
milk_1
```

으로 변경한다.

따라서 목표 상태는 다음과 같다.

```text
milk_1
        ↓
plate_1 위로 이동
        ↓
(On milk_1 plate_1)
        ↓
env.check_success() == True
```

---

##### 8.3.9) custom_milk_task.bddl 전체 코드

최종 `custom_milk_task.bddl`은 다음과 같이 작성한다.

```lisp
(define (problem LIBERO_Tabletop_Manipulation)

  (:domain robosuite)

  (:language Put the milk on the plate)

  (:regions

    (plate_region
        (:target main_table)
        (:ranges (
            (0.03 -0.04 0.07 0.0)
        ))
    )

    (akita_black_bowl_region
        (:target main_table)
        (:ranges (
            (-0.09999999999999999 -0.01 -0.08 0.01)
        ))
    )

    (wine_bottle_region
        (:target main_table)
        (:ranges (
            (-0.22 -0.07 -0.18 -0.03)
        ))
    )

    (cream_cheese_region
        (:target main_table)
        (:ranges (
            (-0.07 0.11 -0.03 0.15)
        ))
    )

    (stove_front_region
        (:target main_table)
        (:ranges (
            (-0.09 0.16999999999999998 -0.010000000000000002 0.25)
        ))
    )

    (milk_region
        (:target main_table)
        (:ranges (
            (-0.09 0.16999999999999998 -0.010000000000000002 0.25)
        ))
    )

    (cabinet_region
        (:target main_table)
        (:ranges (
            (0.02 -0.25 0.04 -0.23)
        ))
        (:yaw_rotation (
            (3.141592653589793 3.141592653589793)
        ))
    )

    (stove_region
        (:target main_table)
        (:ranges (
            (-0.42 0.2 -0.4 0.22)
        ))
    )

    (wine_rack_region
        (:target main_table)
        (:ranges (
            (-0.27 -0.27 -0.25 -0.25)
        ))
        (:yaw_rotation (
            (3.141592653589793 3.141592653589793)
        ))
    )

    (top_region
        (:target wooden_cabinet_1)
    )

    (middle_region
        (:target wooden_cabinet_1)
    )

    (bottom_region
        (:target wooden_cabinet_1)
    )

    (top_side
        (:target wooden_cabinet_1)
    )

    (cook_region
        (:target flat_stove_1)
    )

    (top_region
        (:target wine_rack_1)
    )
  )

  (:fixtures
    main_table - table
    wooden_cabinet_1 - wooden_cabinet
    flat_stove_1 - flat_stove
    wine_rack_1 - wine_rack
  )

  (:objects
    akita_black_bowl_1 - akita_black_bowl
    cream_cheese_1 - cream_cheese
    wine_bottle_1 - wine_bottle
    plate_1 - plate
    milk_1 - milk
  )

  (:obj_of_interest
    milk_1
    plate_1
  )

  (:init
    (On wine_bottle_1 main_table_wine_bottle_region)
    (On akita_black_bowl_1 main_table_akita_black_bowl_region)
    (On plate_1 main_table_plate_region)
    (On cream_cheese_1 main_table_cream_cheese_region)
    (On milk_1 main_table_milk_region)
    (On wooden_cabinet_1 main_table_cabinet_region)
    (On flat_stove_1 main_table_stove_region)
    (On wine_rack_1 main_table_wine_rack_region)
  )

  (:goal
    (And
        (On milk_1 plate_1)
    )
  )

)
```

---

##### 8.3.10) 작성한 두 BDDL 확인

검증안 A:

```powershell
Get-Content .\custom_tasks\custom_goal_change.bddl
```

다음 항목을 확인한다.

```text
Push the plate to the front of the stove

plate_1

main_table_stove_front_region

(On plate_1 main_table_stove_front_region)
```

검증안 B:

```powershell
Get-Content .\custom_tasks\custom_milk_task.bddl
```

다음 항목을 확인한다.

```text
Put the milk on the plate

milk_region

milk_1 - milk

milk_1
plate_1

(On milk_1 main_table_milk_region)

(On milk_1 plate_1)
```

이 단계까지는 BDDL 파일을 작성한 것이다.

검증안 A는 LIBERO 공식 BDDL을 바탕으로 하며, 시작 Region 세 곳의 범위를 위 표처럼 조정하고 미사용 Region을 정리했다. 사용한 Object와 Goal은 공식 정의를 따른다.

검증안 B는 각 구성 요소 자체는 LIBERO에서 실제 지원되는 것을 확인했지만,
`milk + main_table + plate` 조합은 새로 작성한 Custom Task이므로
아직 실행 성공을 가정하지 않는다.

다음 8.4에서 두 파일을 각각 `OffScreenRenderEnv`에 전달하여

```text
BDDL Parser 성공
        ↓
환경 생성 성공
        ↓
env.reset() 성공
        ↓
Object 실제 생성 확인
        ↓
초기 배치 확인
        ↓
Initial Goal == False 확인
```

순서로 실제 시뮬레이션에서 검증한다.
#### 8.4) 환경 로딩과 초기 상태 검증

8.3에서 작성한 두 파일을 각각 `OffScreenRenderEnv`에 전달했다. 실행 코드는 [`test_custom_task_variants.py`](./custom_task_validation/test_custom_task_variants.py)이며, 파일은 앞 절과 같은 `docs/W5/LIBERO` 루트에 둔다. Windows의 `libero` conda 환경(Python 3.8.13), `MUJOCO_GL=wgl`, `seed=0`, `agentview` 512×512을 사용했다. 스크립트는 이 환경에서 오래 걸리는 Numba 초기화를 피하기 위해 `NUMBA_DISABLE_JIT=1`을 설정한다.

```powershell
cd .\docs\W5\LIBERO
conda activate libero
python .\test_custom_task_variants.py --task both --seed 0 --size 512
```

각 환경에서 BDDL 로딩, `env.reset()`, 화면 저장, 초기 `env.check_success()`를 확인했다. 성공 판정이 처음부터 `True`라면 Task가 시작 전에 끝난 것이므로 초기 조건과 Goal을 다시 검토해야 한다.

| 확인 항목 | 검증안 A: 접시 이동 | 검증안 B: 우유 추가 |
| --- | --- | --- |
| BDDL 로딩·환경 생성·`reset()` | 성공 | 성공 |
| 장면에 생성된 조작 대상 | `plate_1` 확인 | `milk_1`, `plate_1` 확인 |
| 초기 장면 | 접시가 시작 위치에 있음 | 우유 상자가 접시와 떨어진 위치에 보임 |
| 초기 `check_success()` | `False` | `False` |
| `:init`의 `On` 조건 재평가 | 7개 모두 `True` | 8개 모두 `True` |

사진에서 확인한 배치를 코드로도 확인했다. A의 7개, B의 8개 초기 `On` 조건이 모두 `True`였다. B의 우유는 지정한 `milk_region` 위에 있었고, 다른 물체나 고정물과 의도하지 않은 접촉도 없었다. 조건별 결과는 [A 결과 JSON](./images/custom_task_validation/A_result.json)과 [B 결과 JSON](./images/custom_task_validation/B_result.json)에 있다.

초기 장면 사진은 [검증안 A](./images/custom_task_validation/A_initial.png), [검증안 B](./images/custom_task_validation/B_initial.png)에 저장했다. 사진에서 B의 우유가 보인다는 사실은 `milk_1`이 시뮬레이터 장면에 생성됐다는 시각적 근거다. 화면 밖에서 생성됐거나 다른 물체와 겹친 경우를 성공으로 처리하지 않기 위해 사진을 함께 확인했다.

![검증안 A의 초기 장면](./images/custom_task_validation/A_initial.png)

![검증안 B의 초기 장면](./images/custom_task_validation/B_initial.png)

초기 프레임에서 Panda가 움직이는 과정까지 확인하려면 [A 시뮬레이션 영상](./images/custom_task_validation/A_robot_action.mp4)과 [B 시뮬레이션 영상](./images/custom_task_validation/B_robot_action.mp4)을 연다. 각 영상의 첫 프레임이 위 초기 장면이며, 이후 프레임은 8.5의 실제 `env.step(action)` 실행이다. 초기화만으로 작업 성공이 증명되는 것은 아니다.

#### 8.5) Action 실행과 Goal Condition 검증

Panda의 7차원 `OSC_POSE` action을 `env.step(action)`에 전달해 두 작업을 수행했다. 그리퍼의 현재 위치와 자세를 읽어 목표와의 오차를 줄인다. A는 닫힌 그리퍼를 접시 표면에 접촉시킨 뒤, 접시를 들어 올리지 않고 +Y와 -X 방향으로 이동시킨다. B는 우유를 잡아 들어 올리고 접시 위로 옮긴 뒤 그리퍼를 연다. 두 경우 모두 그리퍼를 물러나게 한 뒤 Goal을 다시 확인했다.

| 구분 | 총 Panda action step 수 | 영상에서 확인한 것 | action 종료 후 Goal |
| --- | ---: | --- | --- |
| A | 790 | 접시가 테이블 위에서 이동해 스토브 앞 목표 Region에 도달함 | `True` |
| B | 274 | 우유를 잡아 약 0.170 m 들어 올린 뒤 접시 위에 놓고 그리퍼를 놓음 | `True` |

총 step 수에는 마지막 Goal 검증 구간(A 40 step, B 30 step)이 포함된다.

![검증안 A의 action 종료 장면](./images/custom_task_validation/A_action_end.png)

![검증안 B의 action 종료 장면](./images/custom_task_validation/B_action_end.png)

동작 전 과정을 [A 성공 영상](./images/custom_task_validation/A_robot_action.mp4), [B 성공 영상](./images/custom_task_validation/B_robot_action.mp4)에서 볼 수 있다. A는 접촉 종료 후 40 step, B는 놓기와 후퇴 후 30 step 동안 Goal이 계속 `True`였다. 최종 상태에서 물체는 그리퍼에 잡혀 있지 않았다. 영상의 동작 구간에서는 물체 위치나 관절 상태를 직접 바꾸지 않았다.

| A: 접시 이동 | B: 우유를 접시 위에 놓기 |
| --- | --- |
| [![A 성공 영상 미리보기](./images/custom_task_validation/A_robot_action.gif)](./images/custom_task_validation/A_robot_action.mp4) | [![B 성공 영상 미리보기](./images/custom_task_validation/B_robot_action.gif)](./images/custom_task_validation/B_robot_action.mp4) |

VS Code Markdown Preview와 GitHub 본문에서는 실제 영상 프레임으로 만든 GIF가 재생된다. 미리보기를 누르면 H.264 MP4를 열거나 내려받을 수 있다. 결과 파일과 [실행 코드·BDDL](./custom_task_validation/README.md)은 GitHub에서 접근할 수 있도록 상위 저장소에도 저장했다.

Goal 정의가 작동하는지는 별도 시험으로 확인했다. 같은 seed로 다시 `reset()`하고 20 step 동안 초기 물체를 안정시킨 뒤, A는 접시의 자유 관절 위치를 목표 Region 중심으로, B는 우유의 위치를 접시 위로 **직접** 옮겼다. `sim.forward()`로 상태를 반영하고 30 step 동안 물리 시뮬레이션을 진행한 뒤 사진과 `env.check_success()`를 확인했다. 두 경우 모두 `False → True`가 나왔다.

| 구분 | 초기 Goal | 물체 상태 직접 변경 후 Goal | 해석 |
| --- | --- | --- | --- |
| A | `False` | `True` | `(On plate_1 main_table_stove_front_region)` 판정 동작 |
| B | `False` | `True` | `(On milk_1 plate_1)` 판정 동작 |

![검증안 A의 Goal 판정 시험](./images/custom_task_validation/A_predicate_probe.png)

![검증안 B의 Goal 판정 시험](./images/custom_task_validation/B_predicate_probe.png)

이 두 사진은 **직접 상태 변경 시험**의 결과다. B의 `On`은 두 물체의 접촉과 높이·수평 위치 관계를 검사한다. 이 시험은 판정식 확인용이며, Panda가 작업을 수행한 근거는 위 성공 영상과 action 종료 사진이다. 수치 기록은 [A 결과 JSON](./images/custom_task_validation/A_result.json)과 [B 결과 JSON](./images/custom_task_validation/B_result.json)에 남겼다. 이번 성공은 `seed=0`의 배치와 작성한 제어 규칙에서 확인한 결과이며, 학습된 정책의 성능을 평가한 것은 아니다.

#### 8.6) BDDL로 설정 가능한 범위와 LIBERO에 없는 새로운 요소를 추가할 때 필요한 확장 구조 정리

이번 검증안 B는 **LIBERO에 이미 등록된** `milk` 물체를 새 BDDL에서 사용한 사례다. `milk_1`이 화면에 생성되고 초기화된 것은 확인했지만, 이 결과를 LIBERO에 없는 물체까지 BDDL만으로 만들 수 있다는 뜻으로 확대하면 안 된다.

| 바꾸려는 것 | BDDL만으로 가능한 범위 | 추가 구현이 필요한 경우 |
| --- | --- | --- |
| Object·Fixture | 등록된 종류를 `:objects`, `:fixtures`에서 선택하고 인스턴스 이름을 지정 | 새로운 형상·물성의 물체는 asset과 [Object 등록 코드](./custom_task_validation/reference_code/libero/libero/envs/objects/hope_objects.py) 필요 |
| Region·Init | 기존 장면의 기준 대상에 대해 `:target`, `:ranges`, 지원되는 초기 Predicate를 지정 | 새 장면 구조나 지원되지 않는 초기 상태는 환경 코드와 초기화 방식 수정 필요 |
| Goal | [기존 Predicate](./custom_task_validation/reference_code/libero/libero/envs/predicates/base_predicates.py)의 `On`, `Open` 등을 조합 | 새로운 판정 의미는 Predicate 구현 및 등록 필요 |
| 로봇·카메라·제어 | BDDL에서 고르는 Task 조건과 별개 | 로봇 모델, 작업대 크기, 카메라와 컨트롤러는 [환경 생성 코드](./custom_task_validation/reference_code/libero/libero/envs/bddl_base_domain.py)와 [wrapper 설정](./custom_task_validation/reference_code/libero/libero/envs/env_wrapper.py)에서 변경 |

실제 사진 [B 초기 장면](./images/custom_task_validation/B_initial.png)과 [B 시뮬레이션 영상](./images/custom_task_validation/B_robot_action.mp4)은 **등록된 물체를 BDDL에 추가한 결과**의 예시다. 8장의 실행 범위는 기존 요소의 조합이며, 새 물체·Fixture·Predicate와 환경 설정의 추가 구현은 9장에서 검증한다.

![기존 LIBERO 물체를 추가한 검증안 B의 장면](./images/custom_task_validation/B_initial.png)


---

### 9. BDDL에서 표현할 수 없는 요소를 LIBERO 코드로 확장한 Custom Task 검증

#### 9.1) 검증 목적과 공통 기준

8장에서는 기존 LIBERO에 등록된 물체와 Predicate를 BDDL에서 다시 조합했다. 9장에서는 그 범위를 한 단계 넓힌다. 새 물체(C), 새 고정 지지대(D), 새 성공 조건(E), 카메라·제어 설정(F)을 실제 코드에 추가하고, 각 요소를 참조하는 BDDL이 시뮬레이터에서 실행되는지 확인한다. 여기서 핵심은 BDDL 문법만 통과하는지가 아니라 **새 요소가 화면에 나타나고 Panda의 동작으로 Goal에 도달하는지**다.

네 사례 모두 기존 Tabletop 장면과 Panda를 사용했다. 실행 코드는 [test_extended_custom_tasks.py](./custom_task_validation/test_extended_custom_tasks.py)이며, Windows `libero` 환경에서 `seed=0`, 512×512 화면으로 최종 실행 결과를 각각 한 번 기록했다. 각 실험에서 `env.reset()` 직후 `:init`의 `On` 조건을 다시 검사하고 초기 Goal `False`를 확인했다. 이후 미리 정한 경유점을 따라가는 규칙 기반 제어로 `env.step(action)`에 접근·파지·들기·이동·놓기·그리퍼 이탈 명령을 전달했다. 마지막에는 추가 제어 step을 실행하면서 Goal이 계속 `True`인지 확인했다. Action 구간에는 물체의 MuJoCo 상태를 직접 바꾸지 않았다.

```powershell
cd .\docs\W5\LIBERO
conda activate libero
python .\test_extended_custom_tasks.py --case all --seed 0 --size 512
```

실행 결과의 사진과 영상은 각 사례 아래에 연결했다. 영상은 로봇 동작의 증거이고, JSON의 `goal_after_robot_action`과 `goal_true_throughout_verification`은 성공 판정의 근거다.

##### 9.1.1) BDDL 밖에서 작성해야 하는 코드

8.6에서 정리한 확장 항목은 아래 파일에서 구현한다. BDDL에는 구현된 요소의 이름과 작업 조건을 적고, Python과 XML에는 **그 요소를 생성하거나 상태를 판정하는 방법**을 작성해야 한다. 파일 경로는 기존 실행 파일과 같은 LIBERO 루트를 기준으로 한다.

| 확장 항목 | 코드에서 작성해야 하는 내용 | 적용 방법을 설명하는 절 |
| --- | --- | --- |
| 새 Object의 형상·물성 | `assets/`의 XML에 충돌·시각 형상, 크기, 질량, 마찰, 배치 기준 site를 정의한다. `envs/objects/`의 클래스에서 XML 경로·자유 관절·회전 범위를 지정하고 `@register_object`로 등록한다. | 9.2.2 C의 XML·Object 클래스 |
| 새 장면·초기 상태 | 장면 XML과 Arena 연결, Fixture·Region 생성, 배치 sampler, 초기 관절·물체 상태를 작성한다. 새 Problem을 등록하고 초기화 함수가 새 조건을 실제 상태로 적용하게 한다. | 9.3.2 D의 Fixture·배치 코드, 9.3.6 장면·Init 확장 |
| 새 Goal 의미 | Predicate 클래스의 `__call__()`에 검사할 대상·접촉·거리·자세 기준과 `True/False` 반환을 작성한다. 실행 전에 Predicate 사전에 이름을 등록한다. | 9.4.2 E의 함수·등록 코드 |
| 로봇·작업대·카메라·제어 | 로봇 모델과 초기 관절각, 작업대 크기·높이, 카메라 위치·방향, 컨트롤러 설정을 작성한다. Wrapper에서 사용할 로봇·카메라·제어 종류를 선택한다. | 9.5.2 F의 카메라·제어 코드, 9.5.6 로봇·작업대 설정 |

구현 후에는 **모듈 import·등록 → BDDL에서 이름 연결 → `reset()`과 Init 확인 → Panda Action → Goal·사진·영상 확인** 순서로 검증한다. Table 위 영역이나 이미 지원되는 Init만 바꾸는 경우에는 `:target`, `:ranges`, `:init`을 수정하면 된다.

#### 9.2) C — LIBERO에 없던 Object 모델 추가

##### 9.2.1) Task 설계와 변경 요소

Task는 **새로 만든 파란색 표식 상자를 접시 위에 놓기**다. `milk`처럼 기존에 등록된 물체의 인스턴스를 늘리는 경우와 달리, 이 사례에서는 물체의 형상과 등록 클래스를 새로 만들었다.

| 요소 | C에서 사용한 정의 |
| --- | --- |
| Object | 새 종류 `custom_marker_box`, 장면 인스턴스 `custom_marker_box_1` |
| Region | `main_table`의 `custom_marker_box_region`에서 시작 |
| Init | `(On custom_marker_box_1 main_table_custom_marker_box_region)` |
| Goal | `(On custom_marker_box_1 plate_1)` |

접시는 8장에서 사용한 `plate_1`을 유지했다. 따라서 결과 차이는 새 물체 모델과 그 초기 배치에서 확인할 수 있다.

##### 9.2.2) 물체 Asset과 클래스 등록

[marker_box.xml](./custom_task_validation/libero/libero/assets/custom_validation_objects/marker_box.xml)에 크기 52×52×110 mm인 상자를 정의했다. 여기서 **Asset**은 형상과 물리 속성을 담은 MuJoCo XML 파일이다. XML의 `collision` geom은 로봇 손가락이나 접시와의 접촉을 계산하는 형상이다. `visual` geom과 주황색 `marker` geom은 화면에서 물체를 식별하기 위한 형상이며 충돌 계산에서는 제외했다. XML 파일만 놓으면 LIBERO가 새 물체 종류를 알 수 없으므로 [custom_validation_objects.py](./custom_task_validation/libero/libero/envs/objects/custom_validation_objects.py)의 `CustomMarkerBox` 클래스를 `@register_object`로 등록했다. **Registry**는 BDDL의 종류 이름을 Python 클래스에 연결하는 목록이며, `@register_object`는 클래스를 정의할 때 이 등록 함수를 실행하는 데코레이터 표기다. [실행 코드](./custom_task_validation/test_extended_custom_tasks.py)는 새 물체 모듈을 명시적으로 import해 등록을 활성화한다.

새 물체를 작성할 때는 XML에서 아래와 같이 형상과 물성을 먼저 정한다. Box의 `size`는 각 방향의 **절반 크기**이므로 전체 크기는 두 배다. `mass`는 kg 단위 질량이고, `friction`은 미끄럼·비틀림·구름 마찰 계수다. `bottom_site`와 `top_site`는 배치 높이를 계산하는 기준점이다.

```xml
<geom name="collision" type="box" size="0.026 0.026 0.055"
      mass="0.1" friction="1 0.005 0.0001" group="0"
      solref="0.01 1" solimp="0.95 0.99 0.001"/>
<site name="bottom_site" pos="0 0 -0.055" size="0.001" rgba="0 0 0 0"/>
<site name="top_site" pos="0 0 0.055" size="0.001" rgba="0 0 0 0"/>
```

다음으로 클래스의 생성자에서 XML을 읽고 관절·회전 속성을 지정한다. `CustomMarkerBox`는 등록 과정에서 `custom_marker_box`라는 종류 이름으로 연결된다.

```python
@register_object
class CustomMarkerBox(MujocoXMLObject):
    """A 52 x 52 x 110 mm box with one collision shape and an orange marker."""
```

생성자의 관절 설정은 `joints=[dict(type="free", damping="0.0005")] if joints is None else joints`다. `free` joint는 상자가 테이블 위에서 위치와 자세를 바꾸는 **자유 관절**이다. 이것이 있어야 Panda가 집어 들고 접시 위로 옮길 수 있다. 위 코드는 등록 부분만 발췌했다.

XML 작성 후 클래스에 `category_name`, `rotation`, `rotation_axis`, `object_properties`를 지정한다. 실행 파일에서 `import libero.libero.envs.objects.custom_validation_objects`를 수행한 뒤, 9.2.3의 `custom_marker_box_1 - custom_marker_box` 선언으로 장면에 생성한다.

##### 9.2.3) BDDL 작성

[custom_new_object_task.bddl](./custom_task_validation/custom_tasks/custom_new_object_task.bddl)의 핵심 선언은 다음과 같다. `:objects`에서 새 종류를 참조하며, 시작 Region과 Goal은 기존 BDDL과 같은 `On` Predicate를 사용한다.

```lisp
(custom_marker_box_region
    (:target main_table)
    (:ranges ((-0.09 0.16999999999999998 -0.010000000000000002 0.25)))
)

(:objects
    akita_black_bowl_1 - akita_black_bowl
    cream_cheese_1 - cream_cheese
    wine_bottle_1 - wine_bottle
    plate_1 - plate
    custom_marker_box_1 - custom_marker_box
)

(On custom_marker_box_1 main_table_custom_marker_box_region)
(And (On custom_marker_box_1 plate_1))
```

마지막 두 줄은 각각 `:init`과 `:goal` 안에서 발췌했다. 기존 물체·Fixture의 나머지 선언과 Init은 [전체 BDDL](./custom_task_validation/custom_tasks/custom_new_object_task.bddl)에 있다.

##### 9.2.4) 환경 로딩과 초기 상태

```powershell
python .\test_extended_custom_tasks.py --case C --seed 0 --size 512
```

환경 생성과 `reset()`이 성공했고, 초기 Goal은 `False`였다. 8개의 `On` 초기 조건이 모두 `True`였으며, 새 상자와 주변 물체 사이의 의도하지 않은 초기 접촉도 기록되지 않았다. [초기 사진](./images/extended_task_validation/C_initial.png)에는 파란 상자와 주황색 표식이 테이블 위에 보인다. 이는 XML 형상·물체 등록·BDDL 선언이 실제 장면으로 연결됐음을 보여준다.

![C: 새 상자의 초기 배치](./images/extended_task_validation/C_initial.png)

##### 9.2.5) Panda Action과 Goal 검증

Panda가 상자에 접근해 파지하고 약 0.173 m 들어 올린 다음 접시 위에 놓았다. 그리퍼가 상자에서 떨어진 뒤에도 Goal은 `True`였고, 30개 검증 step 동안 유지됐다. 이 검증 구간을 포함해 총 277 action step이 기록됐으며 접시와 상자의 접촉도 확인했다. 물체 상태를 직접 설정한 성공 판정은 사용하지 않았다.

![C: 상자를 접시에 놓은 최종 장면](./images/extended_task_validation/C_action_end.png)

[![C: 상자를 접시로 옮기는 동작 미리보기](./images/extended_task_validation/C_robot_action.gif)](./images/extended_task_validation/C_robot_action.mp4)

[C 결과 JSON](./images/extended_task_validation/C_result.json)

#### 9.3) D — 새 Fixture와 윗면 Region 추가

##### 9.3.1) Task 설계와 변경 요소

Task는 **우유를 새로 만든 받침대 위에 놓기**다. 기존 물체 `milk_1`을 사용하되, 놓을 대상은 새 Fixture인 `raised_support_1`로 바꿨다. Fixture는 테이블에 고정되어 작업의 기준이 되는 요소다.

| 요소 | D에서 사용한 정의 |
| --- | --- |
| Object | 기존 `milk_1 - milk` 사용 |
| Fixture | 새 종류 `raised_support`, 인스턴스 `raised_support_1` |
| Region | 받침대 시작 영역 `main_table_support_region`, 받침대 윗면 `raised_support_1_top_region` |
| Init | `(On raised_support_1 main_table_support_region)` 및 기존 물체 배치 |
| Goal | `(On milk_1 raised_support_1_top_region)` |

##### 9.3.2) 받침대 형상과 배치 코드

[raised_support.xml](./custom_task_validation/libero/libero/assets/custom_validation_objects/raised_support.xml)에 가로·세로 12 cm, 높이 4 cm인 블록을 정의했다. `support_block` geom은 우유를 실제로 받치는 충돌 면이고, `support_visual`은 화면 표시용이다. `top_region` site는 윗면의 위치와 범위를 표시하는 기준 요소이며 BDDL Goal이 참조한다. [custom_validation_fixtures.py](./custom_task_validation/libero/libero/envs/objects/custom_validation_fixtures.py)의 `RaisedSupport`를 `@register_object`로 등록했다. 자유 관절을 만들지 않아 받침대는 배치된 위치에 고정된다.

기본 Tabletop 환경의 Fixture 배치기는 기존 Fixture를 위한 `z_offset=-0.04 m`를 사용한다. 이 값을 새 받침대에 그대로 적용하면 아래로 가라앉으므로 [libero_custom_support.py](./custom_task_validation/libero/libero/envs/problems/libero_custom_support.py)에서 이 Fixture의 배치 sampler에 한해 `z_offset=0.0`을 적용했다. **배치 sampler**는 BDDL Region에서 실제 배치 좌표를 뽑는 코드이며, `z_offset`은 높이 보정 값이다. 새 환경 클래스 `Libero_Custom_Support`를 `@register_problem`으로 등록하고 Tabletop의 Region sampler도 연결했다. **Problem 등록**은 BDDL 첫 줄의 이름으로 실행할 환경 클래스를 찾게 하는 과정이다. 여기서는 BDDL만 수정해서는 물리적 받침대와 올바른 배치 높이를 만들 수 없었다.

```python
REGION_SAMPLERS["libero_custom_support"] = {"table": TableRegionSampler}

@register_problem
class Libero_Custom_Support(_TabletopBase):
    def _add_placement_initializer(self):
        super()._add_placement_initializer()
        for name, fixture in self.fixtures_dict.items():
            if isinstance(fixture, RaisedSupport):
                self.placement_initializer.samplers[name + "_sampler"].z_offset = 0.0
```

##### 9.3.3) BDDL 작성

[custom_new_fixture_task.bddl](./custom_task_validation/custom_tasks/custom_new_fixture_task.bddl)의 핵심은 새 Problem `LIBERO_Custom_Support`, Fixture, 시작 위치, 윗면 Region을 연결하는 부분이다.

```lisp
(support_region (:target main_table) (:ranges ((0.09 0.13 0.11 0.15))))
(top_region (:target raised_support_1))

(:fixtures
    main_table - table
    wooden_cabinet_1 - wooden_cabinet
    flat_stove_1 - flat_stove
    wine_rack_1 - wine_rack
    raised_support_1 - raised_support
)

(On raised_support_1 main_table_support_region)
(On milk_1 raised_support_1_top_region)
```

마지막 두 줄은 각각 `:init`과 `:goal` 안에서 발췌했다. `:init`에는 `And`가 없고, `:goal`에서만 `And`가 조건을 묶는다. `top_region`의 실제 site는 위 XML asset 안에 있다. BDDL의 `:regions` 선언은 그 site를 `raised_support_1_top_region`이라는 이름으로 연결한다. 기존 Init 조건은 [전체 BDDL](./custom_task_validation/custom_tasks/custom_new_fixture_task.bddl)에 남아 있다.

##### 9.3.4) 환경 로딩과 초기 상태

```powershell
python .\test_extended_custom_tasks.py --case D --seed 0 --size 512
```

새 환경 Problem을 불러온 뒤 `reset()`이 성공했다. 초기 Goal은 `False`, 9개의 `On` 초기 조건은 모두 `True`였다. 받침대가 테이블 위에 놓였고 초기 물체와 받침대 사이에 원하지 않은 접촉이 없었다. [초기 사진](./images/extended_task_validation/D_initial.png)에서 우유와 파란 받침대가 서로 떨어져 보인다.

![D: 우유와 새 받침대의 초기 배치](./images/extended_task_validation/D_initial.png)

##### 9.3.5) Panda Action과 Goal 검증

Panda가 우유를 잡아 약 0.170 m 들어 올리고 받침대 위에 놓았다. 총 290 action step이 기록됐고, 그리퍼를 이탈시킨 뒤 마지막 40개 검증 step 동안 `env.check_success()`가 `True`로 유지됐다. 우유와 받침대의 접촉도 `True`였다.

![D: 우유가 받침대 위에 놓인 최종 장면](./images/extended_task_validation/D_action_end.png)

[![D: 우유를 받침대에 놓는 동작 미리보기](./images/extended_task_validation/D_robot_action.gif)](./images/extended_task_validation/D_robot_action.mp4)

[D 결과 JSON](./images/extended_task_validation/D_result.json)

##### 9.3.6) 새 장면과 지원되지 않는 Init을 작성하는 방법

D는 기존 Tabletop 장면에 Fixture와 윗면 Region을 추가한 사례다. 테이블이나 주변 구조 자체를 새로 만들려면 **장면 모델과 초기화 코드**도 작성해야 한다.

장면은 `libero/libero/assets/scenes/` 아래 XML로 만들고, [환경 생성 코드](./custom_task_validation/reference_code/libero/libero/envs/bddl_base_domain.py)의 `scene_xml`과 연결한다. 기존 [TableArena](./custom_task_validation/reference_code/libero/libero/envs/arenas/table_arena.py)를 사용할 때는 `table` body, `table_collision`, `table_visual`, `table_top`, 다리와 바닥·벽 texture처럼 이 클래스가 찾는 XML 요소를 유지한다. 기존 장면 XML을 복사해 필요한 형상을 추가하는 방식으로 시작할 수 있다.

```python
# 새 XML을 assets/scenes/에 작성한 뒤 실행 파일에서 선택한다.
env = OffScreenRenderEnv(
    bddl_file_name="custom_tasks/custom_milk_task.bddl",
    scene_xml="scenes/my_tabletop_scene.xml",
)
```

위 파일명은 새 장면을 만들 때 사용할 예시다. TableArena와 구조가 다른 작업 공간을 만들면 Arena 클래스와 새 Problem의 `_load_model()`을 작성해 연결하고, `_load_fixtures_in_arena()`·`_load_sites_in_arena()`에서 고정물과 Region 기준도 정의해야 한다. Tabletop은 `arena_type="table"`을 사용하므로 이 선택을 바꾸는 구현도 새 환경에서 담당한다.

초기 상태는 [기본 환경 코드](./custom_task_validation/reference_code/libero/libero/envs/bddl_base_domain.py)의 `_add_placement_initializer()`가 BDDL 조건을 배치·속성 sampler로 바꾸고, `_reset_internal()`이 샘플링한 위치·자세·관절값을 적용한다. 새로운 Init 의미를 사용하려면 **조건을 해석하는 분기, 설정할 상태값, reset 시 적용하는 코드**를 작성해야 한다. 예를 들어 서랍을 정해진 위치에서 시작하도록 만들 때는 새 Problem 클래스에 다음 초기화 함수를 작성할 수 있다.

```python
def _reset_internal(self):
    super()._reset_internal()
    if not self.deterministic_reset:
        drawer = self.object_states_dict["wooden_cabinet_1_middle_region"]
        drawer.set_joint(-0.08)
        self.sim.forward()
```

`-0.08 m`는 초기화 방법을 설명하기 위한 예시값이다. 새 조건 이름을 `:init`에 적으려면 해당 이름을 처리하는 sampler·초기화 분기도 함께 추가한다. Predicate 사전에 함수를 등록하는 작업은 상태를 **검사**하는 기능이며, 원하는 초기 상태를 **생성**하는 코드는 별도로 필요하다. `reset()`이 끝나면 새 관측값의 사진과 Init 판정이 일치하는지 확인한다.

#### 9.4) E — 새로운 Goal Predicate 추가

##### 9.4.1) Task 설계와 변경 요소

8장의 `(On milk_1 plate_1)`은 우유가 접시 위에 놓였는지를 판정한다. E에서는 **접시 중앙에서 똑바로 선 상태**까지 성공 조건에 포함했다. 장면의 물체와 배치는 B를 유지하고 Goal만 더 엄격하게 만들었다.

| 요소 | E에서 사용한 정의 |
| --- | --- |
| Object | 기존 `milk_1`, `plate_1` 유지 |
| Region·Init | B의 시작 Region과 초기 조건 유지 |
| Goal | `(CenteredUprightOn milk_1 plate_1)` |
| 추가 판정 | 기존 `On`, XY 중심 거리 ≤ 0.01 m, 우유의 수직 방향 내적 ≥ 0.95 |

##### 9.4.2) Predicate 구현과 등록

[custom_validation_predicates.py](./custom_task_validation/libero/libero/envs/predicates/custom_validation_predicates.py)의 `CenteredUprightOn`은 기존 `On`이 `True`인지 먼저 확인한다. 다음으로 우유와 접시 중심의 평면 거리(XY)를 1 cm 이내로 제한한다. **로컬 Y축**은 우유 상자에 고정된 방향이며, 이 asset에서는 상자 윗면을 향한다. 이를 시뮬레이터의 수직 Z축과 비교한 내적이 1이면 완전히 같은 방향이다. 기준 0.95는 수직에서 약 18.2° 이내의 기울기를 허용한다.

```python
if not On()(milk, plate):
    return False
xy_distance = np.linalg.norm(milk_pos[:2] - plate_pos[:2])
local_y_world_z = float(rotation[2, 1])
return bool(xy_distance <= 0.01 and local_y_world_z >= 0.95)
```

새 함수를 파일에 만드는 것만으로는 LIBERO의 Goal 평가 코드가 이름을 찾지 못한다. [실행 코드](./custom_task_validation/test_extended_custom_tasks.py)는 E 환경을 만들기 전에 모듈을 import하고 `get_predicate_fn_dict()["centereduprighton"] = CenteredUprightOn()`으로 Predicate registry에 명시적으로 등록한다. 이는 BDDL에 없는 **판정 의미 자체**를 Python에서 추가한 사례다.

두 물체를 받는 조건은 E처럼 `BinaryAtomic`을 상속해 `__call__(self, milk, plate)`를 작성한다. 함수 안에서 시뮬레이터의 현재 값을 읽어 위 기준을 검사하고 bool을 반환한다. 실행 파일의 등록 부분은 다음과 같다.

```python
from libero.libero.envs.predicates import get_predicate_fn_dict
from libero.libero.envs.predicates.custom_validation_predicates import CenteredUprightOn

get_predicate_fn_dict()["centereduprighton"] = CenteredUprightOn()
```

등록 후 BDDL의 `:goal`에 `(CenteredUprightOn milk_1 plate_1)`을 작성하고, 9.4.6처럼 만족하는 상태와 기준을 벗어난 상태를 모두 검사한다.

##### 9.4.3) BDDL 작성

[custom_new_predicate_task.bddl](./custom_task_validation/custom_tasks/custom_new_predicate_task.bddl)은 B의 물체·Region·Init을 유지하면서 지시문과 Goal을 변경했다.

```lisp
(:language Put the milk upright at the center of the plate)

(:goal
    (And (CenteredUprightOn milk_1 plate_1))
)
```

BDDL에는 Predicate의 **이름과 대상**을 적고, 접촉·거리·자세를 계산하는 실제 함수는 위 Python 코드에 둔다. [전체 BDDL](./custom_task_validation/custom_tasks/custom_new_predicate_task.bddl)에서 기존 Init도 확인할 수 있다.

##### 9.4.4) 환경 로딩과 초기 상태

```powershell
python .\test_extended_custom_tasks.py --case E --seed 0 --size 512
```

새 Predicate를 등록한 뒤 BDDL 로딩과 `reset()`이 성공했다. 초기 Goal은 `False`였고, 8개의 `On` 초기 조건이 모두 `True`였다. [초기 사진](./images/extended_task_validation/E_initial.png)의 우유는 접시와 떨어져 있으므로 이 판정은 자연스럽다.

![E: 우유와 접시의 초기 배치](./images/extended_task_validation/E_initial.png)

##### 9.4.5) Panda Action과 Goal 검증

Panda가 우유를 파지해 약 0.170 m 들어 올리고 접시 위에 놓았다. 총 274 action step 후 기존 `On`과 새 `CenteredUprightOn`이 모두 `True`였다. 우유·접시 중심의 XY 거리는 **0.000707 m**, 우유 로컬 Y축과 수직 Z축의 내적은 **0.999681**로 기록됐다. 그리퍼가 이탈한 뒤에도 총 step에 포함된 마지막 30개 검증 step 동안 Goal이 유지됐다.

![E: 중앙에 똑바로 놓인 우유의 최종 장면](./images/extended_task_validation/E_action_end.png)

[![E: 우유를 접시 중앙에 놓는 동작 미리보기](./images/extended_task_validation/E_robot_action.gif)](./images/extended_task_validation/E_robot_action.mp4)

[E 결과 JSON](./images/extended_task_validation/E_result.json)

##### 9.4.6) 새 Predicate의 경계 조건 검사

새 조건이 기존 `On`보다 엄격한지도 별도 시험했다. [경계 조건 검사 코드](./custom_task_validation/test_custom_predicate_conditions.py)는 우유의 MuJoCo 상태를 **직접 변경**해 접시 중심에서의 거리와 기울기를 바꾼다. 이 검사는 Predicate 자체를 확인하기 위한 것으로 위 Panda 동작 영상에는 포함되지 않는다.

```powershell
python .\test_custom_predicate_conditions.py
```

| 직접 설정한 상태 | XY 거리 | 우유 로컬 Y축·수직 Z축 내적 | 기존 `On` | 새 `CenteredUprightOn` |
| --- | ---: | ---: | --- | --- |
| 중심 | 0 m | 0.999971 | `True` | `True` |
| 1 cm 안쪽 | 0.0099 m | 0.999971 | `True` | `True` |
| 1 cm 바깥쪽 | 0.0101 m | 0.999971 | `True` | `False` |
| 중심에서 더 벗어남 | 0.015 m | 0.999971 | `True` | `False` |
| 중심에서 20° 기울임 | 0 m | 0.937041 | `True` | `False` |

결과는 [E 경계 조건 JSON](./images/extended_task_validation/E_predicate_conditions.json)에 기록했다. 기존 `On`이 모두 `True`여도 거리 또는 자세 기준을 벗어나면 새 조건만 `False`가 됐다.

#### 9.5) F — 카메라와 제어 설정을 바꾼 환경 추가

##### 9.5.1) Task 설계와 변경 요소

F는 B의 **우유를 접시 위에 놓기** Task를 유지하면서 관찰 시점과 Panda 제어 설정을 바꾼다. 같은 BDDL 물체 배치와 Goal을 사용하므로 새 환경 코드의 역할을 따로 볼 수 있다.

| 요소 | F에서 사용한 정의 |
| --- | --- |
| Object·Region·Init | B의 우유·접시 및 시작 배치 유지 |
| Goal | `(On milk_1 plate_1)` 유지 |
| 카메라 | `custom_overview` 추가, 넓은 작업 장면을 촬영 |
| 제어 | `OSC_POSE`의 `kp=180`, `damping_ratio=1.0` 설정 |

##### 9.5.2) 새 환경 Problem 등록

[libero_custom_camera_control.py](./custom_task_validation/libero/libero/envs/problems/libero_custom_camera_control.py)는 기존 Tabletop 환경을 상속하고 `@register_problem`으로 새 환경 이름을 등록한다. D와 같은 방식으로 새 Problem 이름에 Tabletop 배치 sampler도 연결했으며, 기존 `agentview`를 유지한 채 `custom_overview` 카메라를 추가했다.

```python
controller["kp"] = 180
controller["damping_ratio"] = 1.0
kwargs["controller_configs"] = controller

mujoco_arena.set_camera(
    camera_name="custom_overview",
    pos=[0.9, 0.0, 1.8],
    quat=[0.6380177736282349, 0.3048497438430786,
          0.30484986305236816, 0.6380177736282349],
)
```

위 코드는 생성자의 제어 설정과 `_setup_camera()`의 카메라 설정을 각각 발췌했다. `kp`는 목표 자세와 현재 자세의 오차에 반응하는 강도를 정하는 제어 이득이다. 여섯 값은 말단의 **위치 3축과 회전 3축**에 대응한다. 기본 실험의 실제 controller 값은 모두 150이었고, F에서는 모두 180으로 읽혔다. `damping_ratio`는 목표 근처의 진동을 줄이기 위한 감쇠 비율로 코드에서 1.0을 전달했다. 이 값의 효과를 성능 향상으로 단정하지 않고, **설정 변경과 실행 성공을 확인한 결과**로 기록한다.

##### 9.5.3) BDDL 작성

[custom_camera_control_task.bddl](./custom_task_validation/custom_tasks/custom_camera_control_task.bddl)은 Problem 이름을 새 환경 클래스에 맞춰 바꾸고 B의 Goal을 유지했다.

```lisp
(define (problem LIBERO_Custom_Camera_Control)
  (:domain robosuite)
  (:language Put the milk on the plate)
```

Goal은 `(And (On milk_1 plate_1))`이다. 카메라 위치나 제어 이득의 수치는 BDDL에 적지 않았다. 이 파일은 새 Problem을 선택하고 작업 조건을 정의하며, 카메라·컨트롤러 구현은 환경 코드가 담당한다. Object·Region·Init은 [전체 BDDL](./custom_task_validation/custom_tasks/custom_camera_control_task.bddl)에 있다.

##### 9.5.4) 환경 로딩과 초기 상태

```powershell
python .\test_extended_custom_tasks.py --case F --seed 0 --size 512
```

새 Problem으로 환경을 만들고 `custom_overview`에서 초기 화면을 받았다. 초기 Goal은 `False`, 8개의 `On` 초기 조건은 모두 `True`였다. [초기 사진](./images/extended_task_validation/F_initial.png)은 기존 시점보다 테이블 주변을 넓게 보여준다. JSON에는 관측 카메라 이름 `custom_overview`와 controller 이득 `[180, 180, 180, 180, 180, 180]`이 기록됐다.

![F: custom_overview로 본 초기 장면](./images/extended_task_validation/F_initial.png)

##### 9.5.5) Panda Action과 Goal 검증

동일한 우유 집기·이동·놓기 동작을 새 환경에서 실행했다. 총 262 action step 뒤 우유와 접시의 접촉 및 Goal `True`를 확인했고, 그리퍼 이탈 후 마지막 30개 검증 step 내내 `True`가 유지됐다. 이 검증 구간도 총 step에 포함된다. [최종 사진](./images/extended_task_validation/F_action_end.png)과 영상은 새 카메라 시점에서 기록됐다. 이 결과는 새 카메라와 제어 설정을 적용한 환경에서도 Task가 실제로 수행됨을 보여준다.

![F: custom_overview로 본 Goal 달성 장면](./images/extended_task_validation/F_action_end.png)

[![F: 새 카메라 시점의 우유 놓기 동작 미리보기](./images/extended_task_validation/F_robot_action.gif)](./images/extended_task_validation/F_robot_action.mp4)

[F 결과 JSON](./images/extended_task_validation/F_result.json)

##### 9.5.6) 로봇·작업대·관측 설정을 작성하는 방법

로봇과 관측 설정은 [Wrapper](./custom_task_validation/reference_code/libero/libero/envs/env_wrapper.py)를 통해 환경에 전달한다. F를 불러올 때의 핵심 설정은 다음과 같다. 컨트롤러의 `kp`와 `damping_ratio`는 9.5.2의 환경 클래스에서 설정한다.

```python
from libero.libero.envs.env_wrapper import OffScreenRenderEnv
import libero.libero.envs.problems.libero_custom_camera_control

env = OffScreenRenderEnv(
    bddl_file_name="custom_tasks/custom_camera_control_task.bddl",
    robots=["Panda"],
    initialization_noise=None,
    controller="OSC_POSE",
    camera_names=["custom_overview"],
    camera_heights=512,
    camera_widths=512,
)
```

Tabletop 환경은 `Panda` 앞에 `Mounted`를 붙여 `MountedPanda` 모델을 선택한다. 로봇의 초기 관절각은 [mounted_panda.py](./custom_task_validation/reference_code/libero/libero/envs/robots/mounted_panda.py)의 `init_qpos`, 설치 위치는 `base_xpos_offset`에 정의되어 있다. 초기 자세를 바꾸려면 로봇 클래스의 `init_qpos`에 관절 수와 제한 범위에 맞는 값을 작성하고, `initialization_noise=None`으로 자세에 무작위 잡음을 넣지 않는다.

새 로봇 모델을 추가할 때는 **관절·actuator가 있는 로봇 XML, 모델 클래스, 초기 관절각, mount·gripper, 설치 위치, 사용할 컨트롤러**를 작성해야 한다. Actuator는 관절을 구동하는 요소다. 모델을 import해 등록하고, [robots/__init__.py](./custom_task_validation/reference_code/libero/libero/envs/robots/__init__.py)에서 해당 모델 이름을 `ROBOT_CLASS_MAPPING`에 연결한다. 기존 단일 팔 로봇은 다음처럼 연결되어 있다.

```python
ROBOT_CLASS_MAPPING.update({"MountedPanda": SingleArm})
```

새 모델도 Tabletop의 `Mounted` 이름 규칙과 맞춰 등록해야 한다. 이후 관절 수, 그리퍼, 컨트롤러에 맞게 Action 구성과 접근 경로를 정한다. C~F의 실제 작업 검증에서는 로봇 모델을 `MountedPanda`로 유지했다.

작업대 크기는 [libero_tabletop_manipulation.py](./custom_task_validation/libero/libero/envs/problems/libero_tabletop_manipulation.py)의 `table_full_size`, 상판 높이는 `table_offset`에서 정한다. 전달받은 크기는 환경 생성자의 다음 코드로 읽는다.

```python
if "table_full_size" in kwargs:
    self.table_full_size = kwargs["table_full_size"]
else:
    self.table_full_size = (1.0, 1.2, 0.05)
self.table_offset = (0, 0, 0.90)
```

실행 파일에서 `table_full_size=(1.1, 1.3, 0.05)`를 전달하면 길이 1.1 m, 폭 1.3 m, 두께 0.05 m로 생성된다. 크기를 바꾼 후에는 Region이 상판 범위에 들어가는지, 로봇 설치 위치와 도달 범위가 맞는지 확인한다. 상판 높이를 바꾸면 배치 기준 좌표와 Fixture의 높이 보정도 함께 검토한다.

```powershell
python .\test_tabletop_configuration.py
```

[설정 확인 코드](./custom_task_validation/test_tabletop_configuration.py)로 변경한 크기를 적용해 `reset()`을 검사했다. 실제 충돌 형상의 절반 크기는 `(0.55, 0.65, 0.025) m`, 로봇 base의 X 위치는 `-0.71 m`였다. 이 검사는 크기 설정과 초기화의 확인이며, 변경한 작업대에서 Task Action을 수행한 결과는 포함하지 않는다.

#### 9.6) Initial Pose 설정부터 Custom Task 확장까지의 전체 검증 결과

이번 작업의 목적은 **LIBERO BDDL로 새로운 Task를 작업명세서로 작성했을 때 시뮬레이터에서 실제로 실행되는지 눈으로 확인하는 것**이다. 이를 위해 5장에서 로봇의 초기 자세와 화면 출력을 준비하고, 6~7장에서 Custom BDDL의 로딩·동작·성공 판정을 확인했다. 8~9장에서는 변경 범위를 나누어 같은 과정을 적용했다. 이 결과는 새 Task를 설계할 때 장면 구성, 물체 배치, 수행 가능성, Goal의 의미를 검토하는 근거가 된다.

##### 9.6.1) 5장 — Panda Initial Pose 설정과 기존 Task의 초기 장면

5.2에서는 BDDL을 불러오기 전에 Panda와 빈 테이블만 만들었다. [초기 자세 코드](./custom_task_validation/test_panda_initial_pose.py)는 `SingleArmEnv`에서 `MountedPanda`를 사용하고, 로봇 클래스의 `init_qpos`에 정의된 7개 관절각으로 시작한다. `initialization_noise=None`으로 자세에 잡음을 넣지 않았으며, 실제 관절값이 초기 설정과 일치하는지 검사했다. TableArena의 크기는 `(1.0, 1.2, 0.05) m`, 상판 높이는 `0.90 m`로 설정하고 작업 물체를 추가하지 않았다. [초기 자세 사진](./images/panda_initial_pose.png)에서 Panda 모델과 빈 작업 공간이 정상적으로 렌더링되는 것을 확인했다.

5.3에서는 기존 LIBERO benchmark의 BDDL로 물체가 있는 환경을 만들고, `env.set_init_state(init_states[0])`로 저장된 초기 상태를 재현했다. [기존 Task 초기 장면](./images/libero_tabletop_test.png)은 그 결과다. 5.2는 로봇의 기본 초기 자세를 확인한 단계이고, 5.3은 benchmark에 저장된 장면을 불러온 단계다. 이때 확인한 것은 초기 장면의 생성과 렌더링이다.

##### 9.6.2) 6~7장 — Custom BDDL 로딩에서 실제 Panda 동작까지

6장에서는 `custom_test.bddl`을 `OffScreenRenderEnv`에 직접 전달했다. Parser가 물체·Fixture·Region·Init·Goal을 해석하고, `env.reset()`으로 서랍 Task의 [초기 장면](./images/custom_bddl_test.png)을 생성했다. 하나의 BDDL을 실행하는 과정에서 별도의 benchmark 등록은 필요하지 않았다.

7장에서는 초기 Goal `False`와 zero action의 관측 갱신을 확인했다. 이어 7.3에서 서랍 joint를 직접 바꿔 Goal 판정식의 동작을 검사했고, 7.4에서는 닫힌 상태로 다시 시작해 Panda의 `OSC_POSE` Action으로 실제 서랍을 열었다. [Action 종료 사진](./images/panda_drawer_action_result.png)에서 열린 서랍과 Goal `True`를 확인했다. 이 과정으로 **초기 장면 → 로봇 Action → 관측 변화 → Goal 판정**의 실행 흐름을 확인했다.

##### 9.6.3) 8~9장 — Task를 추가하는 경우별 결과

8장의 A·B는 기존 LIBERO 요소를 BDDL에서 선택하거나 조합한 사례다. 9장의 C~F는 필요한 요소를 Python·XML로 구현한 뒤 BDDL에 연결한 사례다. 여섯 경우 모두 초기 Goal이 `False`였고, 지정한 초기 `On` 조건도 모두 충족했다.

| 경우 | 추가하거나 변경한 내용과 수행한 작업 | 초기 `On` | 총 Action step | 마지막 검증 구간 |
| --- | --- | ---: | ---: | --- |
| [8-A](./images/custom_task_validation/A_robot_action.mp4) | 기존 `plate_1`과 Region으로 Goal 변경. 접시를 테이블 위에서 스토브 앞으로 이동 | 7/7 | 790 | 접촉 종료·후퇴 후 40 step 모두 `True` |
| [8-B](./images/custom_task_validation/B_robot_action.mp4) | 등록된 `milk`를 새 인스턴스로 추가하고 Region·Init·Goal 작성. 우유를 접시 위에 놓기 | 8/8 | 274 | 놓기·후퇴 후 30 step 모두 `True` |
| [9-C](./images/extended_task_validation/C_robot_action.mp4) | 새 상자의 XML·Object 클래스·등록 코드 작성. 상자를 접시 위에 놓기 | 8/8 | 277 | 놓기·후퇴 후 30 step 모두 `True` |
| [9-D](./images/extended_task_validation/D_robot_action.mp4) | 새 받침대 Fixture·윗면 site·배치 높이 코드 작성. 우유를 받침대 위에 놓기 | 9/9 | 290 | 놓기·후퇴 후 40 step 모두 `True` |
| [9-E](./images/extended_task_validation/E_robot_action.mp4) | 새 Predicate 함수·등록 코드 작성. 우유를 접시 중앙에 세워 놓기 | 8/8 | 274 | 놓기·후퇴 후 30 step 모두 `True` |
| [9-F](./images/extended_task_validation/F_robot_action.mp4) | 새 카메라·제어 설정을 환경 코드에 작성. 변경한 환경에서 우유를 접시 위에 놓기 | 8/8 | 262 | 놓기·후퇴 후 30 step 모두 `True` |

마지막 검증 구간은 총 Action step에 포함된다. 표의 경우 이름을 누르면 전체 MP4를 볼 수 있으며, 각 실험 절에는 움직이는 GIF와 초기·종료 사진, 결과 JSON을 연결했다.

**A에서는 현재 Custom BDDL에 있는 접시를 사용했다.** 공식 접시 밀기 BDDL을 기준으로 시작 Region 범위를 조정하고 목표를 스토브 앞 영역으로 정했다. Panda가 접시를 들어 올리지 않고 이동시켰으며, [종료 사진](./images/custom_task_validation/A_action_end.png)의 위치와 Goal 판정이 일치했다.

**B에서는 현재 Custom BDDL에 없던 등록 물체를 추가했다.** `milk_1 - milk`를 선언하고 우유의 시작 Region·Init과 접시 위 Goal을 작성했다. Panda가 우유를 잡아 들어 올린 뒤 놓고 물러나는 모습을 [종료 사진](./images/custom_task_validation/B_action_end.png)과 영상에서 확인했다.

**C·D는 새 물체와 고정 구조를 구현한 경우다.** C는 LIBERO에 없던 상자의 형상·물성을 XML과 Object 클래스로 정의했고, D는 새 받침대와 윗면 Region을 만들고 초기 배치 높이를 맞췄다. 두 경우 모두 새 요소가 장면에 나타났으며 Panda가 물체를 목표 위에 놓았다.

**E·F는 판정과 실행 환경을 확장한 경우다.** E는 기존 `On`에 중심 거리와 직립 기준을 더했다. 실제 동작 후 새 조건이 충족됐고, 별도 경계 검사에서는 기준을 벗어난 상태가 거부됐다. F는 카메라와 제어 이득을 바꾼 환경에서 같은 우유 놓기 Task를 수행했다. F의 결과는 설정 적용과 Task 실행의 확인이며, 제어 성능이 향상됐다는 비교 결과는 아니다.

##### 9.6.4) 검증의 의미와 적용 범위

5~9장에서는 **초기 자세 설정 → 기존 장면 확인 → Custom BDDL 로딩 → 실제 로봇 동작 → BDDL 변경과 코드 확장**의 순서로 검증 범위를 넓혔다. BDDL은 사용할 요소와 초기 상태·성공 조건을 정의하고, LIBERO 코드는 물체·장면·판정 함수·실행 환경을 구현한다. 실제 목표 달성에는 접근 자세·파지·접촉·이동 경로를 정한 Action이 함께 필요했다.

시뮬레이터의 사진·영상과 Predicate 판정을 함께 확인해, 명세가 의도한 장면으로 생성되고 로봇 동작으로 목표에 도달하는지 검토했다. 직접 상태를 바꾸는 Predicate 시험은 별도로 수행했으며, A~F 성공 영상의 동작 구간에서는 `env.step(action)`만 사용했다. 이 절차를 통해 새 Task를 설계할 때 **초기 배치가 가능한지, 로봇이 수행할 수 있는지, 성공 조건이 눈으로 본 결과와 맞는지**를 확인할 수 있었다.

실제 Task 성공 결과는 `seed=0`에서 각 사례를 최종 기록한 한 번의 규칙 기반 제어에 해당한다. 새 장면·로봇 모델·미지원 Init의 작성 방법은 확장 가이드이며, C~F의 실행 성공에 포함된 사례는 아니다. 작업대 크기 변경은 설정 적용과 `reset()`까지만 추가로 확인했다. 다양한 초기 배치의 성공률과 학습 정책의 성능은 별도의 평가가 필요하다.
