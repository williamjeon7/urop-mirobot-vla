# %% 이 셀 위의 Run Cell을 누르면 시뮬레이션 움짤이 바로 표시됩니다.
from pathlib import Path
import importlib
import sys

from IPython import get_ipython

if get_ipython() is None:
    raise SystemExit(
        "VS Code에서 이 파일을 열고 'Run Cell'을 누르세요. "
        "커널은 Python (libero)를 선택하세요. 일반 터미널은 움짤을 표시할 수 없습니다."
    )

# 실행 위치가 UROP 또는 이 파일의 폴더여도 프로젝트를 찾습니다.
directory = Path.cwd().resolve()
project = next((path for path in (directory, *directory.parents)
                if (path / "docs/W6/rgb_blocks/animation.py").is_file()), None)
if project is None:
    raise RuntimeError("UROP 작업공간에서 이 셀을 실행하세요.")
if str(project) not in sys.path:
    sys.path.insert(0, str(project))

import docs.W6.rgb_blocks.objects as block_config
import docs.W6.rgb_blocks.preview as preview
import docs.W6.rgb_blocks.animation as animation

# objects.py의 BLOCK_SIZE_MM을 바꾸고 다시 실행하면 즉시 반영됩니다.
for module in (block_config, preview, animation):
    importlib.reload(module)

# 아래 숫자는 코드에서 직접 조절합니다.
DURATION_S = 4.0
FPS = 20
RESOLUTION = 480
CAMERA_SWEEP_DEG = 15.0  # 0이면 고정 카메라. 블록이나 로봇을 강제로 옮기지 않습니다.

animation.show_animation(duration_s=DURATION_S, fps=FPS, resolution=RESOLUTION,
                         camera_sweep_deg=CAMERA_SWEEP_DEG)
