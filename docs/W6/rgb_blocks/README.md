# LIBERO Tabletop: Red · Green · Blue 정육면체

세 물체는 색상만 다르고 모두 같은 크기의 정육면체다. 기본 한 변은 **40 mm**다.
XML의 box `size`는 각 축의 반길이(m)이며, Python 코드에서 세 축을 함께 조절한다.
시각 형상, 충돌 형상, 위·아래 위치 기준점, 수평 반경도 함께 변경한다.
밀도는 일정하게 유지하므로 질량은 한 변 길이의 세제곱에 비례한다(40 mm일 때 50 g).

UROP 작업공간에서 실행:

```bash
conda activate libero
cd ~/UROP
python docs/W6/rgb_blocks/preview.py
```

크기는 **`objects.py` 상단의 `BLOCK_SIZE_MM = 40.0`** 숫자를 수정한다.
예를 들어 `BLOCK_SIZE_MM = 60.0`으로 바꾸면 세 정육면체의 한 변이 모두 60 mm가 된다.
현재 BDDL 배치에서는 0 초과 120 mm 이하를 지원한다.
`preview.py`의 `RESOLUTION`, `SEED`도 코드에서 수정할 수 있다.

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
`tabletop.bddl`은 테이블 위 초기 배치, `preview.py`는 시뮬레이터 실행·렌더링 코드다.
BDDL의 goal은 초기 배치 확인용 `On` 조건이다. 집기 태스크 및 실물 로봇 명령은 포함하지 않는다.
