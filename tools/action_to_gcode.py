#!/usr/bin/env python3
"""W5 ① 번역기 — action 을 시뮬 Panda 에 넣고, 그 손 자세를 Mirobot G-code 로 옮긴다. (서버 .venv 전용)

    # 기록에 남은 action 열로 끝까지 도는지 본다
    python -m tools.action_to_gcode --log data/follow/2026_09_28-10_36_55.jsonl
    python -m tools.run_gcode <나온 파일> --dry-run        # 도달 범위·Z 하한 경고가 있나

    # LIBERO suite 밖의 장면 (W6 RGB 블록) — 기록 meta 의 bddl · register · seed 를 그대로 쓴다
    python -m tools.action_to_gcode --log data/pickup/<기록>.jsonl --scale 0.663

**10/8 두 단계로 나눴다** (`docs/W6/DIVISION.md`). 이 파일은 둘을 차례로 부르기만 한다 — 사용법과 출력은 그대로다.

    action ──▶ tools/action_to_poses.py ──▶ 손 좌표 ──▶ tools/poses_to_gcode.py ──▶ Mirobot G0 (절대)
               시뮬 Panda (LIBERO 필요)                 짝·배율·F, 그리퍼 M4 (표준 라이브러리)

policy 가 내는 action 은 "여기로 가라" 가 아니라 **Panda OSC 에 주는 변화량**이라 곱하기로는 Mirobot 좌표로
못 바꾼다 — 시뮬 Panda 를 옆에서 같이 돌려 그 답을 얻는다 (`docs/W5/ACTION_MEANING.md` 1-9).
**이 도구는 열린 고리다** — 받은 action 을 그대로 넣고 나온 자세를 적을 뿐, 실물이 어디 있는지 보지 않는다.
실제 운용에서는 chunk 사이에 시뮬 Panda 를 Mirobot 의 실제 자세로 다시 데려다 놓아야 한다 (W5 CHECKLIST 2-4).

남는 것
  <--out>                              Mirobot G-code (`; point` 머리말이 붙는다)
  data/translate/<날짜>-<시각>.jsonl    스텝마다 action·Panda 자세·Mirobot 명령
"""

from __future__ import annotations

import argparse

from tools import action_to_poses, poses_to_gcode
from tools.action_to_poses import first_goal_step, read_actions, register_objects  # noqa: F401 — 예전 import 경로


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action_to_poses.add_arguments(parser)
    poses_to_gcode.add_arguments(parser)
    args = parser.parse_args()

    meta, rows = action_to_poses.simulate(args)
    lines, out_rows, info = poses_to_gcode.convert(
        meta, rows, args, str(args.log), "번역기 — action → 시뮬 Panda → Mirobot  (tools/action_to_gcode.py)")
    print(f"action {len(rows)}개 — {args.log}")
    print(f"settle {meta['settle']}, orientation {args.orientation}, point {args.point}, every {args.every}")
    print(f"짝 {args.mapping} — Mirobot 쪽 {tuple(round(v, 2) for v in info['meta']['ref_mirobot_mm'])} mm, "
          f"배율 {info['meta']['scale']:g}\n")
    poses_to_gcode.report(info["kept"], out_rows, info["gripper_at"], info["roundtrip_mm"])
    action_to_poses.report_replay(meta, len(rows))
    out = args.out or poses_to_gcode.default_out(args.log)
    log_path = poses_to_gcode.write_outputs(lines, out_rows, info, out, args.log_dir)
    print(f"saved {out}\nsaved {log_path}")


if __name__ == "__main__":
    main()
