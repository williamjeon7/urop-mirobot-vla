# 손 좌표 견본 — Panda 쪽 → Mirobot 쪽

> **기록** · 만든 날 2026-10-08
> Mirobot 쪽이 바로 변환을 시작할 수 있도록 Panda 쪽이 올려 두는 손 좌표 JSONL(`panda-poses/1`)이다.
> 형식과 분업은 [../DIVISION.md](../DIVISION.md) 2장·5장에 있다.

## 1. 파일

세 색 × seed 0–2 × 두 동작, 모두 18개다. 이름은 `<동작>-<색>-s<seed>.jsonl`이다. 파일 하나는 73–98 KB다.

- `pickup-*`: 블록 중심 +15 mm에서 잡아 15 cm 들어 올린다. 그리퍼 열기→닫기가 한 번 있다(`action[6]` −1 → +1)
- `reach-*`: 블록 위에서 손끝이 Mirobot 기준 작업대 위 30 mm에 멈췄다가 시작 자세로 돌아온다. 그리퍼는 계속 연다. 실물 1·2단계용이다

만든 설정: 블록 40 mm(`objects.py`), Mirobot 작업 영역 무작위 배치(`tasks/*.bddl`), 블록 회전 0°, 시나리오 없음.

## 2. seed별 블록 위치 — 종이 표시

**같은 seed는 동작·색과 관계없이 배치가 같다**(6개 파일 모두 확인). 그래서 seed마다 종이 한 벌이면 된다.
값은 블록 중심의 **Mirobot 파지점 X·Y (mm)**다. meta `blocks_start_xyz_m`를 짝(Panda 시작 ↔ Mirobot 홈)·배율 0.663으로 옮겼다
(`common/workspace.py` `libero_to_mirobot_xyz_mm`). 실물 블록 한 변은 시뮬 40 mm ÷ 0.663 ≈ 26.5 mm에 해당한다.

| seed | red | green | blue |
| --- | --- | --- | --- |
| 0 | X 256.0 Y −23.3 | X 208.2 Y 13.6 | X 157.8 Y −82.6 ⚠ |
| 1 | X 172.5 Y 75.6 | X 223.7 Y −16.5 | X 165.4 Y −60.4 ⚠ |
| 2 | X 182.9 Y −46.6 | X 236.4 Y 70.8 | X 243.1 Y −84.1 |

- ⚠ X 150–170은 작업대 높이에서 닿는지 **아직 실측하지 않은** 안쪽 끝이다(W5 TABLE_ALIGNMENT 6절). 처음 실물 시험은 seed 2부터 하는 것을 추천한다
- 종이 표시는 **Mirobot 원점(받침대 J1 중심)에서 자로 재서** 놓는다. 로봇을 그 자리로 보내서 표시하면 변환이 아니라 반복 정밀도만 잰다
- `blocks_start_xyz_m`의 z(0.93)는 reset 직후, 블록이 내려앉기 전 값이다. 쓰는 것은 x·y뿐이다

## 3. 시뮬 결과와 변환 확인 (10/8)

모든 파일을 `tools/poses_to_gcode.py --scale 0.663`(pickup은 `--gripper`) → `tools/run_gcode.py --dry-run`으로 확인했다.

| 파일 | step | 시뮬 결과 | 수평 최대 | Z 최저 | Z 경고 줄 |
| --- | ---: | --- | ---: | ---: | ---: |
| pickup-red-s0 / s1 / s2 | 145 / 149 / 144 | 성공, 0.144–0.147 m 상승 | 260.4 / 202.6 / 202.6 mm | 72.5 / 70.9 / 71.7 mm | 0 / 1 / 0 |
| pickup-green-s0 / s1 / s2 | 144 / 144 / 146 | 성공 | 209.4 / 226.2 / 248.7 mm | 72.2 / 72.3 / 72.3 mm | 0 |
| pickup-blue-s0 / s1 / s2 | 151 / 147 / 149 | 성공 | 202.6 / 202.6 / 259.1 mm | 70.1 / 70.9 / 72.4 mm | 1 / 1 / 0 |
| reach-* (9개) | 112–121 | 성공, 블록 위 수평 오차 0.1–0.5 mm | 202.6–260.1 mm | 83.4–85.4 mm | 0 |

- Z 하한(66 mm) 아래 줄은 18개 모두 없다. 경고 줄(66–71 mm)은 pickup 3개에 1줄씩이다
- 역변환 검산(파일 값으로 되돌린 손 좌표와 원래의 차이)은 최대 0.013 mm다(반올림 크기)
- 수평 202.6 mm는 시작 자세 쪽 값이다(블록이 홈 가까이 있을 때 그 값이 최대)
- pickup G-code는 `M4 S40`(시작)·`M4 S60`(잡을 때) 두 줄을 포함하므로 `run_gcode --auto`로만 실행한다

## 4. 쓰는 법 · 다시 만드는 법

```bash
# Mirobot 쪽 — 저장소 루트, conda 를 끈 셸
cosmos-policy/.venv/bin/python -m tools.poses_to_gcode --poses docs/W6/poses/pickup-red-s2.jsonl --scale 0.663 --gripper --out trajectories/<이름>.gcode
cosmos-policy/.venv/bin/python -m tools.run_gcode trajectories/<이름>.gcode --dry-run

# Panda 쪽 — 다시 만들 때 (서버 conda libero)
python -B docs/W6/rgb_blocks/pickup.py --task red --mode pickup --seed 2 --log docs/W6/poses/pickup-red-s2.jsonl
```

잡는 높이나 블록 크기가 바뀌면(DIVISION 3장 ②③) Panda 쪽이 이 폴더를 다시 만들고 push한다. 형식은 그대로라 변환 코드는 고치지 않아도 된다.
