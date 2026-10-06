# RGB 정육면체 시뮬레이터

> **절차** · 확인 2026-10-06
> RGB 블록 장면과 색상별 Task를 선택해 localhost에서 초기 배치를 확인한다.

## 1. 실행

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

## 2. 브라우저

VS Code 하단 PORTS에서 포트 전달을 눌러 `8766`을 추가한다.
로컬 PC 브라우저에서 http://localhost:8766을 연다.
이미 연결된 SSH를 사용하므로 추가 비밀번호는 없다.

## 3. 종료

실행한 터미널에서 `Ctrl+C`를 누른다. 다른 터미널에서 종료하려면:

```bash
bash ~/UROP/docs/W6/rgb_blocks/run_browser.sh --stop
```

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
| [test_rgb_blocks.py](./test_rgb_blocks.py) | 환경 초기화·배치·크기·관측 확인 |

## 6. 환경 확인

OASYS에서 `libero` 환경을 활성화하고 창 없이 확인한다.

```bash
source ~/miniforge3/etc/profile.d/conda.sh
conda activate libero
python -B ~/UROP/docs/W6/rgb_blocks/test_rgb_blocks.py --headless --steps 60 --size 512 --seed 0
python -B ~/UROP/docs/W6/rgb_blocks/test_rgb_blocks.py --task blue --headless --steps 60 --size 512 --seed 0
```

이 검증은 초기 조건과 RGB 세 블록의 크기·관측을 확인하고 이동 없는 Action으로 60 step 진행한다.
`--size`는 카메라 해상도이며 블록 크기는 `BLOCK_SIZE_MM`으로 조절한다.
