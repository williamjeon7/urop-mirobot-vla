# LIBERO Tabletop: Red · Green · Blue 정육면체

세 물체는 색상만 다르고 모두 같은 크기의 정육면체다. 기본 한 변은 **40 mm**다.
XML의 box `size`는 각 축의 반길이(m)이며, Python 코드에서 세 축을 함께 조절한다.
시각 형상, 충돌 형상, 위·아래 위치 기준점, 수평 반경도 함께 변경한다.
밀도는 일정하게 유지하므로 질량은 한 변 길이의 세제곱에 비례한다(40 mm일 때 50 g).

## W5 NewTaskBDDL과 같은 실행 방식

[W5 NewTaskBDDL 6.4·7.2](../../W5/NewTaskBDDL.md)처럼 일반 Python 실행으로
OpenCV 창을 열고, `env.step(action)` 이후 `agentview_image`와 Goal을 계속 갱신한다.
W5가 실행됐던 **로컬 Windows PC의 `libero` 환경**에서 프로젝트 루트를 열고 실행한다:

```powershell
conda activate libero
python docs/W6/rgb_blocks/test_rgb_blocks.py --steps 60 --size 512 --seed 0
```

OpenCV 창을 클릭한 뒤 `q`, `Q`, `Esc` 또는 창 닫기로 종료한다.
GUI 모드는 60 step 이후에도 종료할 때까지 계속 갱신한다. 화면을 저장하거나 녹화하지 않는다.
Jupyter, localhost, SSH 터널이나 별도 로컬 뷰어 실행은 필요 없다.

파이프라인은 `RGB Object 등록 → tabletop.bddl 로딩 → env.reset() → env.step(zero action)
→ agentview_image → cv2.imshow() → env.check_success()`다. W5의 zero action 검증과 같고,
카메라나 물체 위치를 강제로 바꾸지 않는다. 현재 Goal은 세 블록의 초기 배치 조건이므로
시작부터 `True`가 정상이다. 집기 목표가 아니며 Panda를 이동시키는 동작은 넣지 않았다.

### OASYS SSH에서 실행하는 경우

현재 OASYS SSH 터미널에는 `DISPLAY`가 없어 OpenCV 창을 직접 띄울 수 없다.
W5는 로컬 Windows PC에서 실행한 예제이므로, 같은 창을 보려면 해당 PC 또는 화면이
연결된 Linux 데스크톱에서 실행해야 한다. 이 서버에서는 아래 명령으로 환경만 검증할 수 있다:

```bash
conda activate libero
python docs/W6/rgb_blocks/test_rgb_blocks.py --headless --steps 60 --size 512 --seed 0
```

`--headless`는 창 없이 지정한 step 수를 실행하고 결과를 터미널에 출력한다.
이미지·동영상·JSON 파일은 만들지 않는다.

Windows에서는 W5에서 준비한 WGL/DLL 호환 설정을 그대로 사용한다. 다른 PC에서 새로
설치한다면 [W5 설치·Windows 렌더링 설정](../../W5/NewTaskBDDL.md)을 먼저 적용한다.
실행 코드는 Windows에서 `MUJOCO_GL=wgl`, Linux에서 기본 `egl`을 선택한다.
W6 전용 경로 설정이 없는 PC에서는 기존에 작동하는 W5의 LIBERO 경로 설정을 사용한다.

## 코드에서 수치 조절

**`objects.py` 상단의 `BLOCK_SIZE_MM = 40.0`** 숫자를 수정한다.
예를 들어 `BLOCK_SIZE_MM = 60.0`이면 세 정육면체의 한 변이 모두 60 mm다.
수정 후 스크립트를 다시 실행하면 변경한 값으로 새 시뮬레이션을 만든다.
현재 BDDL 배치에서는 0 초과 120 mm 이하를 지원한다.

`test_rgb_blocks.py`에서 화면 크기와 초기 배치 seed도 직접 수정할 수 있다:

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
`tabletop.bddl`은 초기 배치, `test_rgb_blocks.py`는 W5 방식의 OpenCV 모니터링 코드다.
`preview.py`의 정지 화면 및 `animation.py`·`show_simulation.py`의 셀 GIF 기능은 별도로 남아 있다.
BDDL의 goal은 초기 배치 확인용 `On` 조건이다. 자동 집기 태스크 및 실물 로봇 명령은 포함하지 않는다.
