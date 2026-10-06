# RGB 정육면체 시뮬레이터

> **절차** · 확인 2026-10-06
> RGB 블록 장면과 색상별 Task를 선택해 localhost에서 초기 배치를 확인한다.

## 1. 실행

### 1.1. OASYS 서버에서 실행

OASYS의 Bash 터미널에서 실행한다:

```bash
bash ~/UROP/docs/W6/rgb_blocks/run_browser.sh
```

기본 모드는 `scene`이며 RGB 세 블록을 모두 표시한다. 색상별 Task는 다음처럼 선택한다.
다른 모드로 바꿀 때는 먼저 실행 중인 서버를 종료한 뒤 다시 실행한다.

```bash
bash ~/UROP/docs/W6/rgb_blocks/run_browser.sh --task red
bash ~/UROP/docs/W6/rgb_blocks/run_browser.sh --task green
bash ~/UROP/docs/W6/rgb_blocks/run_browser.sh --task blue
```

각 색상 모드에서도 Red/Green/Blue 블록이 모두 테이블에 존재하며 선택한 블록을 관심 대상으로 지정한다.
BDDL에는 색상별 `Pick up` 지시문을 넣지만 집기 동작과 집기 성공 Predicate는 아직 구현하지 않았다.
현재 Goal은 초기 배치 확인용이므로 초기 `goal=True`는 정상이다.

### 1.2. 로컬 노트북 모니터에서 실행 (Windows)

노트북에서 시뮬레이션을 실행하고 OpenCV 창으로 화면을 확인한다.
VS Code에서 로컬 저장소를 열고 **SSH 원격 터미널이 아닌 노트북의 PowerShell**에서 실행한다.
W5의 `libero` 환경이 설치되어 있어야 한다. 처음 설정하는 노트북은
[NewTaskBDDL.md](../../W5/NewTaskBDDL.md)의 3–5장(환경 설치·Windows WGL/DLL 설정)을 먼저 진행한다.

**노트북마다 한 번 초기 설정한다.** 로컬 저장소 루트(`mirobot-vla`)에서 다음을 실행한다.
실행기가 Anaconda·Miniforge·Miniconda의 `libero` 환경을 찾아 Windows WGL/DLL 설정을 확인하고,
Python과 LIBERO 설정 경로를 `windows.local.json`에 저장한다. 이 파일은 Git에서 제외된다.

```powershell
.\docs\W6\rgb_blocks\run_local.cmd -Setup
```

환경이 다른 위치에 있거나 여러 환경 중 하나를 지정하려면 초기 설정 때 경로를 전달한다.
LIBERO 설정 폴더가 기본 위치(`$env:USERPROFILE\.libero`)와 다르면 `-ConfigDirectory`도 지정한다.

```powershell
.\docs\W6\rgb_blocks\run_local.cmd -Setup -PythonPath 'D:\miniforge3\envs\libero\python.exe'
# 설정 폴더도 다른 경우:
.\docs\W6\rgb_blocks\run_local.cmd -Setup -PythonPath 'D:\miniforge3\envs\libero\python.exe' -ConfigDirectory 'D:\libero-config'
```

**이후에는 새 터미널에서도 실행 명령만 입력한다.** 로컬 저장소 루트에서 다음을 실행하면
저장된 경로를 읽고 PATH·WGL·Numba 설정을 자동 적용한다.
RGB 세 블록이 OpenCV 창에 표시되며, 창을 클릭한 뒤 `q`, `Q`, `Esc`를 누르거나 창을 닫으면 종료된다.

```powershell
.\docs\W6\rgb_blocks\run_local.cmd
```

색상별 Task는 아래 명령 중 하나로 실행한다. 다른 Task를 열기 전에 기존 창을 종료한다.
로컬에서도 세 블록이 모두 표시되며 Goal은 집기 성공이 아닌 초기 배치 확인용이다.

```powershell
.\docs\W6\rgb_blocks\run_local.cmd -Task red
.\docs\W6\rgb_blocks\run_local.cmd -Task green
.\docs\W6\rgb_blocks\run_local.cmd -Task blue
```

노트북에서도 브라우저 화면을 쓰려면 다음을 실행하고
http://localhost:8766을 연다. 로컬 실행이므로 포트 전달은 필요 없다.
종료는 실행한 터미널에서 `Ctrl+C`를 누른다.

```powershell
.\docs\W6\rgb_blocks\run_local.cmd -Browser
# 색상 선택 예시: 위 명령 끝에 -Task blue 추가
```

Python 또는 LIBERO 설정 폴더를 옮겼다면 `-Setup`에 새 경로를 지정해 다시 저장한다.

## 2. OASYS 화면을 로컬 브라우저로 보기

VS Code 하단 PORTS에서 포트 전달을 눌러 `8766`을 추가한다.
로컬 PC 브라우저에서 http://localhost:8766을 연다.
이미 연결된 SSH를 사용하므로 추가 비밀번호는 없다.

## 3. 종료 및 Conda 환경 해제

### 3.1. 실행기 종료

OASYS 서버는 실행한 터미널에서 `Ctrl+C`를 누른다. 다른 터미널에서 종료하려면:

```bash
bash ~/UROP/docs/W6/rgb_blocks/run_browser.sh --stop
```

로컬 OpenCV 창은 `q`, `Q`, `Esc` 또는 창 닫기로 종료한다.
로컬 브라우저 실행은 터미널에서 `Ctrl+C`로 종료하며, `-Headless` 검증은 지정한 step이 끝나면 자동 종료된다.

`run_local.cmd`는 별도 PowerShell 프로세스에서 `libero`의 Python을 직접 실행하고,
`run_browser.sh`는 별도 Bash 프로세스 안에서 환경을 활성화한다.
두 실행기 모두 원래 터미널의 Conda 환경을 바꾸지 않으므로 실행기 사용 후에는 별도로 `deactivate`할 필요가 없다.

### 3.2. 직접 활성화한 Conda 환경 해제

현재 터미널에서 `conda activate libero`를 직접 실행했다면, 검증이나 뷰어를 종료한 뒤
**같은 터미널**에서 아래 명령을 실행한다. OASYS Bash와 로컬 PowerShell 모두 동일하다.
실행 전에 직접 활성화한 환경은 실행기를 종료해도 유지된다.

```shell
conda deactivate
```

현재 환경이 해제되고 이전 환경으로 돌아간다. 이전 환경이 `base`이면 프롬프트에 `(base)`가 표시될 수 있다.

## 4. 블록 크기

[objects.py](./objects.py)의 `BLOCK_SIZE_MM = 40.0` 값을 수정한다(mm).
서버를 종료하고 다시 실행해야 적용된다.

## 5. 파일

| 파일 | 역할 |
| --- | --- |
| [objects.py](./objects.py), [assets/](./assets/) | RGB 정육면체 모델과 크기·등록 |
| [tabletop.bddl](./tabletop.bddl) | 기본 `scene`의 물체·초기 배치·배치 Goal |
| [tasks.py](./tasks.py), [tasks/](./tasks/) | 색상별 Task 선택과 BDDL 지시문·관심 대상 |
| [browser_viewer.py](./browser_viewer.py), [run_browser.sh](./run_browser.sh) | localhost 실시간 화면과 Bash 실행 진입점 |
| [run_local.cmd](./run_local.cmd), [run_local.ps1](./run_local.ps1) | Windows 노트북 초기 설정·OpenCV/브라우저 실행 |
| [test_rgb_blocks.py](./test_rgb_blocks.py) | 환경 초기화·배치·크기·관측 확인 |

## 6. 환경 확인

로컬 노트북은 1.2의 초기 설정 후 저장소 루트에서 창 없이 확인한다.

```powershell
.\docs\W6\rgb_blocks\run_local.cmd -Headless -Steps 60 -Size 512 -Seed 0
.\docs\W6\rgb_blocks\run_local.cmd -Task blue -Headless -Steps 60 -Size 512 -Seed 0
```

OASYS에서 `libero` 환경을 활성화하고 창 없이 확인한다.

```bash
source ~/miniforge3/etc/profile.d/conda.sh
conda activate libero
python -B ~/UROP/docs/W6/rgb_blocks/test_rgb_blocks.py --headless --steps 60 --size 512 --seed 0
python -B ~/UROP/docs/W6/rgb_blocks/test_rgb_blocks.py --task blue --headless --steps 60 --size 512 --seed 0
conda deactivate
```

이 검증은 초기 조건과 RGB 세 블록의 크기·관측을 확인하고 이동 없는 Action으로 60 step 진행한다.
`--size`는 카메라 해상도이며 블록 크기는 `BLOCK_SIZE_MM`으로 조절한다.
