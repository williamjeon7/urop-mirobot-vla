#!/usr/bin/env python3
"""common/demos.py 의 내장 데모를 HDF5 로 변환한다.

`robot/replay_hdf5.py` 는 `--hdf5` 기본 경로로 수집된 데이터셋
(`cosmos-policy/artifacts/.../SCENE1_demos.hdf5`) 을 기대하는데, 그 파일은
저장소에 없다. `.gitignore` 가 `artifacts/` 와 `*.hdf5` 를 막고 있고 애초에
우리가 직접 수집한 데이터라 외부에서 받을 수도 없다.

그래서 이 스크립트가 있다. 내장 데모 10개를 같은 구조의 HDF5 로 만들어 주면
데이터셋 없이도 `replay_hdf5.py` 의 경로를 시험할 수 있다.

**HDF5 를 저장소에 커밋하지 않는 이유**는 같은 데이터가 두 벌이 되기 때문이다.
`demos.py` 를 고쳤는데 HDF5 를 안 고치면 두 재생 스크립트가 서로 다른 궤적을
돌리게 되고, 드라이런 출력을 매번 대조하지 않으면 알아채지 못한다. 실물 대신
만드는 법을 남기는 것은 `VENDORED.md`(clone 명령), `MODELS.md`(HF repo ID),
`requirements/`(설치 목록) 와 같은 원칙이다.

    python -m tools.demos_to_hdf5
    python -m tools.demos_to_hdf5 --out data/demos.hdf5

만든 뒤:

    python -m robot.replay_hdf5 --hdf5 data/demos.hdf5 --demo-index 0 --max-steps 5

출력은 `python -m robot.replay_demo0 --max-steps 5` 와 완전히 같아야 한다.
같은 숫자를 담아 놓은 것이므로 다르면 변환이 잘못된 것이다.

## 구조

`replay_hdf5.py:64 load_demo()` 가 기대하는 그대로 쓴다.

    /data                       그룹
      attrs["task_instruction"] 태스크 문장
      /demo_0
        actions       (T, 7)
        robot_states  (T, 9)    ← demos.py 의 "states". 이름만 다르고 레이아웃 동일
      /demo_1 ...

이미지는 담지 않는다. `demos.py` 에 애초에 없다. 실제 수집 데이터셋에는
`agentview_rgb` / `eye_in_hand_rgb` 가 함께 들어가야 한다.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np

from common.demos import DEMOS
from common.schema import ACTION_DIM, STATE_DIM, TASK_INSTRUCTION

DEFAULT_OUT = Path("data") / "demos.hdf5"


def convert(out_path: Path, instruction: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with h5py.File(out_path, "w") as file:
        data = file.create_group("data")
        data.attrs["task_instruction"] = instruction

        for key in sorted(DEMOS, key=int):
            demo = DEMOS[key]
            actions = np.asarray(demo["actions"], dtype=np.float64)
            states = np.asarray(demo["states"], dtype=np.float64)

            if actions.shape[1] != ACTION_DIM:
                raise ValueError(f"demo_{key}: action 차원이 {actions.shape[1]}, {ACTION_DIM} 이어야 한다")
            if states.shape[1] != STATE_DIM:
                raise ValueError(f"demo_{key}: state 차원이 {states.shape[1]}, {STATE_DIM} 이어야 한다")
            if len(actions) != len(states):
                raise ValueError(f"demo_{key}: 길이 불일치 {len(actions)} vs {len(states)}")

            group = data.create_group(f"demo_{key}")
            group.create_dataset("actions", data=actions)
            group.create_dataset("robot_states", data=states)
            print(f"  demo_{key}: actions {actions.shape}, robot_states {states.shape}")


def main() -> None:
    parser = argparse.ArgumentParser(description="common/demos.py 를 HDF5 로 변환한다.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"출력 경로. 기본 {DEFAULT_OUT}")
    parser.add_argument(
        "--instruction",
        default=TASK_INSTRUCTION,
        help="/data 에 붙일 task_instruction attribute. 기본은 common.schema 값",
    )
    args = parser.parse_args()

    print(f"instruction: {args.instruction}")
    print(f"demos: {len(DEMOS)}")
    convert(args.out, args.instruction)

    size_kb = args.out.stat().st_size / 1024
    print(f"wrote: {args.out.resolve()} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
