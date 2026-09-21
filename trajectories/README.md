# 궤적 파일

Mirobot 에 보낼 `G0` 명령 목록. 영상·기록(`rollouts/`, `data/`)은 gitignore 라, **로봇 노트북으로 옮겨야 하는 것만** 여기에 둔다.

| 파일 | 내용 |
|---|---|
| `2026_09_17-compound-relative.gcode` | LIBERO Panda 복합 동작(구간 3개)을 옮긴 것. **시작 자세를 `(0,0,0)` 으로 두고 움직임만** — 첫 실물 실행용 |
| `2026_09_17-compound-absolute.gcode` | 같은 궤적을 기록된 자세 그대로 — 시작이 `B 3.28`, 최대 `B 18.22`. J5 를 20° 까지 확인한 뒤에 |
| `2026_09_20-compound-measured.jsonl` | relative 궤적을 **9/20 실물에서 실행한 `?` 보고값** (명령값도 같이). 왕복 검증의 입력 |
| `2026_09_20-compound-measured.gcode` | 같은 보고값을 G-code 로 — `tools/libero_follow --gcode` 에 바로 넣을 수 있다 |
| `2026_09_21-mirobot-origin.gcode` | **Mirobot 에서 출발하는 궤적** (5-1 (나)). 앞 7줄은 한 축씩(A20/B20/C25, 사이사이 홈), 뒤 9줄은 블록 → 그릇 흉내. 각도는 **절대값** — 읽는 쪽도 `--orientation absolute` |

원본은 서버의 `data/compound/2026_09_17-10_44_39.jsonl`, 영상은 `rollouts/2026_09_17/compound/10_44_39--compound.mp4`.
만든 도구는 `tools/libero_to_mirobot_gcode.py`, 규약은 [../docs/W3/LIBERO_AXES.md](../docs/W3/LIBERO_AXES.md) 4절.
`measured` 파일을 만들고 LIBERO 로 되돌려 원본과 대 보는 것은 `tools/roundtrip_check.py`,
왕복이 무엇을 잡고 무엇을 못 잡는지는 [../docs/W3/CHECKLIST.md](../docs/W3/CHECKLIST.md) 5-1 (가).

**실행기** — `tools/run_gcode.py` (로봇 노트북, 시리얼 직결)

```bash
python -m tools.run_gcode trajectories/2026_09_17-compound-relative.gcode --port COM4 --dry-run   # 좌표만 본다
python -m tools.run_gcode trajectories/2026_09_17-compound-relative.gcode --port COM4             # 줄마다 확인하며
```

기본은 줄마다 묻는다 (Enter 보냄 / s 건너뜀 / q 중단). `--auto` 로 연달아, `--home` 으로 시작 전 호밍.
`G0` 마다 `wait_settled` 로 멈춤을 확인하고 `?` 보고값을 `data/gcode_run/*.jsonl` 에 남긴다.

**실행 규칙**
- `;` 로 시작하는 줄은 설명이다. 건너뛴다
- 앞의 `G90`(절대) `M20`(Cartesian) 을 먼저 보낸다
- `G0` 은 **한 줄씩** 보내고, 멈춘 것을 확인한 뒤 다음 줄로 간다
- 각 줄 뒤 `?` 보고값을 남긴다 — Mirobot → LIBERO 방향(5-1)의 입력이 된다
