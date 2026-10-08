# RGB 정육면체 시뮬레이터

> **절차** · 확인 2026-10-08
> RGB 블록 장면과 색상별 Task를 선택해 localhost에서 초기 배치와 Panda pick up을 확인한다.

## 1. 실행

### 1.1. OASYS 서버에서 실행

OASYS의 Bash 터미널에서 실행한다:

```bash
bash ~/UROP/docs/W6/rgb_blocks/run_browser.sh
```

서버는 옵션 없이 한 번만 실행한다. 무엇을 볼지는 **브라우저 위쪽 설정 줄**에서 고르고 "불러오기"를 누른다.

| 설정 | 선택 |
| --- | --- |
| task | `scene`(세 블록), `red`, `green`, `blue` — 어떤 BDDL을 쓸지 정한다 |
| 동작 | 배치 확인(Panda 정지, 60 step) · pick up · 손 뻗기(블록 위, 손끝이 Mirobot 기준 작업대 위 30 mm) |
| 시나리오 | pick up일 때만. `adjacent`는 한쪽, `sandwich`는 양쪽에 이웃 블록을 면 사이 20 mm로 붙인다([scenarios.py](./scenarios.py)) |
| seed | 블록 배치. 같은 seed는 같은 장면이다 |

`scene`은 지정한 블록이 없어서 배치 확인만 할 수 있다. task를 바꾸면 환경을 새로 만든다(약 1초).
색상 Task에서도 Red/Green/Blue 블록이 모두 테이블에 있고, 선택한 블록이 관심 대상이다.
`scene`의 Goal은 배치 조건이라 시작부터 `True`다. 색상 Task의 Goal은 `(Up <color>_block_1)`이라
블록을 들어 올리기 전에는 `False`가 정상이다.

episode가 끝나면 마지막 장면에서 멈추고 기다린다. 영상 아래 조작판에서 다음을 할 수 있다.

| 조작 | 동작 |
| --- | --- |
| ⏸ / ▶ (Space) | 일시정지·재생. 일시정지하면 시뮬레이션도 멈춘다(계산 중이던 한 step은 끝까지 진행된다) |
| ◀ 1 / 1 ▶ (← →) | 한 step 뒤로·앞으로. 가장 최근 장면에서 앞으로 가면 시뮬레이션이 한 step 진행한다 |
| 슬라이더, ⏮ ⏭ | 지금 episode의 지나간 장면을 다시 본다. 재생하면 그 지점부터 이어서 보여 준다 |
| "다음 seed" | 같은 설정으로 seed만 1 올려 다시 시작한다 |
| "끝나면 자동으로 다음 seed" | 켜면 episode가 끝날 때마다 다음 seed로 넘어간다 |

지나간 장면은 지금 episode의 것만 메모리에 둔다. 파일로 저장하지 않는다.

`--task`·`--mode`·`--scenario`·`--seed`는 처음 열 때의 설정이다. 실행 중 설정은 브라우저에서 바꾼다.

설계와 검증 기록은 [PICKUP.md](./PICKUP.md)에 있다.

### 1.2. 로컬에서 실행 (Windows)

로컬 저장소 루트(`mirobot-vla`)의 **PowerShell**에서 실행한다.
W5의 `libero` 환경이 없다면 [NewTaskBDDL.md](../../W5/NewTaskBDDL.md)의 3–5장을 먼저 진행한다.

처음 한 번 설치 경로를 저장한다.

```powershell
.\docs\W6\rgb_blocks\run_local.cmd -Setup
```

경로를 찾지 못하거나 설치 위치를 옮겼다면 `-Setup`에 `-PythonPath`(실제 `python.exe` 경로)와
`-ConfigDirectory`(`config.yaml`이 있는 폴더)를 지정한다.

이후에는 다음 명령으로 실행한다.

```powershell
.\docs\W6\rgb_blocks\run_local.cmd
```

브라우저에서 http://localhost:8766을 연다. 화면과 조작은 1.1과 같고, 로컬 실행에는 포트 전달이 필요 없다.
`8766`이 OASYS 포트 전달이나 다른 프로그램에서 사용 중이면 다음처럼 실행하고 http://localhost:8767을 연다.

```powershell
.\docs\W6\rgb_blocks\run_local.cmd -Port 8767
```

OpenCV 배치 확인 창은 `-OpenCV`, 창 없는 검증은 6절의 `-Headless`를 사용한다. 종료 방법은 3절에 있다.

## 2. OASYS 화면을 로컬 브라우저로 보기

VS Code 하단 PORTS에서 포트 전달을 눌러 `8766`을 추가한다.
로컬 PC 브라우저에서 http://localhost:8766을 연다.

## 3. 종료 및 Conda 환경 해제

### 3.1. 실행기 종료

OASYS·로컬 서버는 실행한 터미널에서 `Ctrl+C`로 종료한다. 브라우저 탭만 닫으면 서버는 계속 실행된다.
다른 터미널에서 종료하려면:

```bash
bash ~/UROP/docs/W6/rgb_blocks/run_browser.sh --stop
```

```powershell
.\docs\W6\rgb_blocks\run_local.cmd -Stop
# 다른 포트로 실행한 경우:
.\docs\W6\rgb_blocks\run_local.cmd -Stop -Port 8767
```

`-OpenCV` 창은 `q`, `Q`, `Esc` 또는 창 닫기로 종료하며,
`-Headless` 검증은 지정한 step이 끝나면 자동 종료된다.

### 3.2. 직접 활성화한 Conda 환경 해제

실행기는 원래 터미널의 Conda 환경을 바꾸지 않는다.
`conda activate libero`를 직접 실행한 경우에만 종료 후 같은 터미널에서 해제한다.

```shell
conda deactivate
```

## 4. 블록 크기

[objects.py](./objects.py)의 `BLOCK_SIZE_MM = 40.0` 값을 수정한다(mm).
서버를 종료하고 다시 실행해야 적용된다.
세 블록은 Mirobot 작업 영역(파지점 X 150~260, Y ±100 mm)을 시뮬로 옮긴 영역 하나에 무작위로 놓이고, 색 순서도 seed마다 바뀐다
([../CHECKLIST.md](../CHECKLIST.md) 2절). 이 영역에는 최대 60 mm까지 쓸 수 있다.

## 5. 파일

| 파일 | 역할 |
| --- | --- |
| [objects.py](./objects.py), [assets/](./assets/) | RGB 정육면체 모델과 크기·등록 |
| [tabletop.bddl](./tabletop.bddl) | 기본 `scene`의 물체·초기 배치·배치 Goal |
| [tasks.py](./tasks.py), [tasks/](./tasks/) | 색상별 Task 선택과 BDDL 지시문·관심 대상·`Up` Goal |
| [pickup.py](./pickup.py), [PICKUP.md](./PICKUP.md) | Panda OSC_POSE pick up action과 성공 판정, 진행 기록 |
| [scenarios.py](./scenarios.py) | 블록이 가까이 붙은 시작 배치 (`--scenario`) |
| [browser_viewer.py](./browser_viewer.py), [run_browser.sh](./run_browser.sh) | localhost 실시간 화면과 Bash 실행 진입점 |
| [run_local.cmd](./run_local.cmd), [run_local.ps1](./run_local.ps1) | Windows 초기 설정·기본 브라우저 서버 실행/종료·OpenCV/Headless 확인 |
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
색상 Task에서는 시작 Goal이 `False`인지도 확인한다.

Panda pick up은 창 없이 다음처럼 확인한다. 성공하면 exit 0으로 끝난다.

```bash
python -B ~/UROP/docs/W6/rgb_blocks/pickup.py --task red --seed 0
```

`--mode reach`는 블록을 집지 않고 블록 위에서 멈춘다. 이때 손끝은 Mirobot 기준 작업대 위 30 mm에 온다.
`--log`를 주면 Mirobot 변환용 기록을 `data/pickup/`에 남긴다.
변환과 검사는 저장소 루트에서 `cosmos-policy/.venv`로 실행한다([../CHECKLIST.md](../CHECKLIST.md) 4절).

```bash
python -B ~/UROP/docs/W6/rgb_blocks/pickup.py --task green --mode reach --seed 0 --log
cd ~/UROP
cosmos-policy/.venv/bin/python -m tools.action_to_gcode --log data/pickup/<기록>.jsonl --scale 0.663 --out trajectories/<이름>.gcode
cosmos-policy/.venv/bin/python -m tools.run_gcode trajectories/<이름>.gcode --dry-run
```
`--size`는 카메라 해상도이며 블록 크기는 `BLOCK_SIZE_MM`으로 조절한다.
