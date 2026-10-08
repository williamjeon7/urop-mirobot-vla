# W6 분업 — Panda 쪽과 Mirobot 쪽

> **절차** · 확인 2026-10-08 · 기준 `e80dc1d` + 번역기 분리
> 10/8 팀 결정: 이번 주는 지금의 pick up을 Mirobot으로 옮겨 실제 경향성을 확인한다([CHECKLIST.md](CHECKLIST.md) 0장).
> 일을 **Panda 쪽**(동작을 만들고 손 좌표를 남김)과 **Mirobot 쪽**(손 좌표를 Mirobot 명령으로 바꾸고 실물에서 확인)으로 나눈다.
> 두 쪽은 **손 좌표 JSONL**(2장) 하나로 만난다. `→` 뒤 빈칸은 미리 채우지 않는다.

## 1. 경계

```text
[Panda 쪽]                                   [Mirobot 쪽]
pickup.py · scenarios.py · BDDL · 뷰어         poses_to_gcode.py · common/workspace.py · common/rotation.py
   │                                            run_gcode.py · (실물 로봇)
   │  action → 시뮬 Panda → 손 좌표
   ▼
손 좌표 JSONL (panda-poses/1, 2장)  ───────────▶  짝·배율·F → Mirobot G0 · 그리퍼 M4 → dry-run → 실물
                                     넘겨주는 지점
```

| | Panda 쪽 | Mirobot 쪽 |
| --- | --- | --- |
| 묻는 것 | 시뮬에서 지시한 블록을 제대로 집는가 | 그 손 좌표가 Mirobot에서 같은 동작이 되는가 |
| 결과물 | 손 좌표 JSONL | Mirobot G-code와 실물 측정 결과 |
| 실행 환경 | 서버 conda `libero` (LIBERO·MuJoCo) | 표준 라이브러리만. 서버 venv, 노트북 어디서든 |

### 1.1 번역기를 두 파일로 나눴다 (10/8)

전에는 `tools/action_to_gcode.py` 하나가 두 쪽 일을 같이 했다. 경계에 맞춰 나눴다.

| 파일 | 하는 일 | 쪽 |
| --- | --- | --- |
| [`tools/action_to_poses.py`](../../tools/action_to_poses.py) **새 파일** | action을 시뮬 Panda에 다시 넣어 step마다 손 좌표를 남긴다. 원래 실행과 같은 step에서 Goal이 뜨는지로 재현을 확인한다 | Panda |
| [`tools/poses_to_gcode.py`](../../tools/poses_to_gcode.py) **새 파일** | 손 좌표 → Mirobot G0, 그리퍼 `M4`, `--every`, 범위·각도·Z 경고, 역변환 검산 | Mirobot |
| [`tools/action_to_gcode.py`](../../tools/action_to_gcode.py) | 위 둘을 차례로 부른다. 기존 사용법·옵션·출력은 그대로다(W5 `PIPELINE.md`) | — |

`pickup.py --log`는 실행하면서 손 좌표 JSONL을 바로 남긴다. 그래서 pick up은 `action_to_poses.py` 없이 `poses_to_gcode.py`로 넘어간다.
`action_to_poses.py`는 정책(VLA)처럼 action만 있을 때, 그리고 같은 action이 같은 좌표를 내는지 재현을 볼 때 쓴다.

**나눈 뒤 확인한 것** (red pick up seed 0, LIBERO-90 기록 60 step)

| 비교 | 결과 |
| --- | --- |
| 이전 `action_to_gcode` ↔ 새 `action_to_gcode` (W6 pick up, LIBERO-90 둘 다) | G0·M4 줄 **완전히 같음**. 주석 두 줄의 문구만 다름 |
| 새 `action_to_gcode` ↔ `action_to_poses` → `poses_to_gcode` | **완전히 같음** |
| 새 `action_to_gcode` ↔ `pickup.py` 기록 → `poses_to_gcode` | 149줄 중 73줄이 **0.01**(G-code 마지막 자리) 다름. 두 Python 환경의 시뮬 손 위치 차이 0.0012 mm가 반올림에 드러난 것 |
| `poses_to_gcode`를 numpy·LIBERO 없이 실행 | 된다. 결과도 같다 |
| 역변환 검산 (absolute · relative) | 최대 0.012 mm (Mirobot 기준, 반올림 크기) |
| 테스트 | `tests/` 48개 통과 (`test_poses_to_gcode.py` 7개 새로) |

## 2. 넘겨주는 파일 — 손 좌표 JSONL (`panda-poses/1`)

한 줄에 JSON 하나다. 첫 줄이 `meta`, 그 뒤가 step마다 한 줄이다. `pickup.py --log`가 남긴 파일은 마지막에 `result` 줄이 하나 더 있고, 읽는 쪽은 건너뛴다.
red pick up 한 번(145 step)이 약 95 KB다.

**meta — 반드시 있어야 하는 것**

| 키 | 뜻 |
| --- | --- |
| `format` | `"panda-poses/1"` |
| `start_eef_pos` | **짝의 Panda 쪽** — 첫 action 직전 손(파지점) 위치, m, LIBERO world |
| `start_eef_quat_xyzw` | 같은 때 손 자세, 쿼터니언 xyzw (LIBERO 순서) |

**meta — 있으면 쓰는 것**: `task`, `instruction`, `target`, `seed`, `bddl`, `register`, `scenario`, `block_size_mm`, `mode`(pickup·reach), `settle`,
`blocks_start_xyz_m`(블록 이름 → 중심 m, reset 직후 — 종이 표시용, 10/8 추가).

**step 줄**

| 키 | 뜻 | 쓰는 곳 |
| --- | --- | --- |
| `step` | 1부터 | 줄 이름, `--every` |
| `eef_pos` | 손(파지점) 위치, m, LIBERO world (테이블 중심 원점, 윗면 z 0.90) | 좌표 변환 |
| `eef_quat_xyzw` | 손 자세 | 좌표 변환 |
| `action` | Panda OSC_POSE 7개. `[6]`의 **부호**가 그리퍼(−1 열기, +1 닫기) | 그리퍼 `M4` |
| `goal` 또는 `done` | 그 step의 Goal | 재현 확인 |
| `phase`, `eef_rxyz_deg`, `joint_pos`(7), `gripper_qpos` | `pickup.py`만 남김 | 사람이 볼 때 |

**좌표의 약속**: LIBERO world, m. 점은 파지점(`robot0_eef_pos`, 손가락 사이)이다. 쿼터니언은 xyzw로 남기고 계산할 때 wxyz로 바꾼다.
Panda 시작 자세는 LIBERO 기본값이다(약 (−0.2085, 0, 1.1733), 노이즈 없음).

**형식을 바꿀 때**: 키를 빼거나 뜻을 바꾸면 `format`을 `panda-poses/2`로 올리고 이 장을 고친 뒤 상대에게 알린다. 키를 더하는 것은 버전을 올리지 않는다.

## 3. Panda 쪽 할 일

이번 주 우선순위(0장 팀 결정)에 따라 1–3을 먼저, 4–6은 그다음이다.

- [ ] **1. 견본 손 좌표를 넘긴다** — `data/`는 git에서 빠지므로 `git pull`로 못 받는다. 5장 잠정안대로 `docs/W6/poses/`에 올린다.
  세 색 × seed 몇 개, `pickup` 모드. 실물 1·2단계용 `reach` 모드도 함께
  → **올렸다 (10/8)** — [poses/](poses/README.md) 18개(세 색 × seed 0–2 × pickup·reach). 18개 모두 dry-run 통과.
  meta에 블록 시작 위치 `blocks_start_xyz_m`를 더했다(형식 버전은 그대로). seed별 종이 표시 좌표는 poses/README.md 2장
- [ ] **2. 잡는 높이를 Mirobot 쪽 결과에 맞춘다** — 지금은 블록 중심 +15 mm(`pickup.py` `GRASP_ABOVE_CENTRE_M`). Z 하한 66 mm 때문이다.
  실물 블록 크기와 집게 폭(S60)이 정해지면 다시 정한다
  →
- [ ] **3. 실물 블록 크기를 반영한다** — 시뮬 크기 = 실물 ÷ 0.663(`objects.py` `BLOCK_SIZE_MM`).
  바꾸면 무작위 배치 간격과 손 뻗기 높이(블록 위 30 mm)가 맞는지 다시 확인하고 pick up 성공률을 다시 잰다
  →
- [ ] **4. 브라우저 시연** — 미팅 결과물 1: Mirobot 작업 영역 안 무작위 배치에서 pick up 성공률
  →
- [ ] **5. pick up 다양화 (팀 결정으로 미룸)** — 그리퍼를 0°/90° 중 빈 쪽으로 돌려 잡기, 블록 회전(yaw), 가까운 블록(`--scenario`).
  그리퍼를 90° 돌리면 Mirobot C ≈ 90°로 `run_gcode` 각도 경고선 30°를 넘는다 — Mirobot 쪽과 같이 본다
  →
- [ ] **6. 카메라 도착 후** — 영상 기반 pick up, VLA 데이터(CHECKLIST 6절)
  →

## 4. Mirobot 쪽 할 일

- [ ] **1. 변환을 읽고 검토한다** — `poses_to_gcode.py` → `common/workspace.py`(짝·배율·파지점↔플랜지 `L` 55 mm) → `common/rotation.py`(`F` = x축 180°).
  근거는 W3 `CONVERSION.md`·`LIBERO_AXES.md`, W5 `TABLE_ALIGNMENT.md`. 견본으로 `--dry-run`까지 돌려 본다
  →
- [ ] **2. 기본 짝·배율** — 지금은 `--scale 0.663`을 손으로 준다. `common/workspace.py` 기본값을 홈·0.663으로 바꿀지 정한다(W5 CHECKLIST 9-①).
  바꾸면 W3–W5 도구에도 영향이 간다
  →
- [ ] **3. 그리퍼** — `M4 S40` 열기 / `M4 S60` 닫기는 W4 값이다(W5 10/5 실측은 활짝 S30, 완전히 닫힘 S70).
  S60일 때 집게 폭(mm), 닫히는 시간(초)을 잰다. 지금은 닫은 뒤 같은 자리 G0 30줄이 기다림 역할이다. `G4` dwell이 되는지도 본다
  →
- [ ] **4. 줄 수** — pick up은 145줄 안팎이라 `--auto`로는 오래 걸린다. `--every N`을 정한다(그리퍼 줄은 항상 남는다)
  →
- [ ] **5. 실물 1·2단계 (손 뻗기)** — W5 9-③: 블록 자리에 종이 표시, 손끝 위치·높이를 자로 잰다. `run_gcode --auto`.
  종이 표시는 **Mirobot 원점(받침대 J1 중심)에서 자로 재서** 놓는다 — 로봇을 보내서 표시하면 변환이 아니라 반복 정밀도만 잰다
  →
- [ ] **6. 작업 영역 안쪽 끝** — Mirobot X 150–170이 작업대 높이(플랜지 Z 70 근처)에서 닿는지(W5 TABLE_ALIGNMENT 6절). 무작위 배치가 이 범위를 쓴다
  →
- [ ] **7. 실물 3단계 (pick up)** — 그리퍼까지. 블록 대용품(약 26 mm)으로 경향성을 본다: 지시한 색으로 가는가, 내려가는가, 집는가, 드는가
  →
- [ ] **8. Z 경고 구간** — pick up 30개 중 5개에 플랜지 Z 66–71 mm 줄(경고만)이 있다. 그대로 둘지 정한다
  →
- [ ] **(나중에)** W3 `tools/libero_to_mirobot_gcode.py`(waypoint만, 그리퍼 없음)와 `poses_to_gcode.py`를 합칠지
  →

## 5. 함께 정할 것

- [ ] **손 좌표를 넘기는 방법** — (가) 견본을 git이 추적하는 폴더(예: `docs/W6/poses/`)에 올린다 / (나) Mirobot 쪽이 서버에서 `pickup.py --log`를 직접 실행한다.
  (가)는 파일 하나에 약 95 KB다
  → **잠정 (10/8): (가).** Panda 쪽이 `docs/W6/poses/`에 견본을 올리고 push한다. 이름은 `<mode>-<색>-s<seed>.jsonl`.
  Mirobot 쪽은 `git pull`로 받는다. 서버 conda 환경 없이도 변환을 시작할 수 있어서다. 더 필요한 seed는 (나)로 직접 만들어도 된다
- [ ] **실물 로봇 담당** — 로봇 앞에서 측정할 사람. 측정 결과는 CHECKLIST 5절에 남긴다
  → **잠정 (10/8): Mirobot 쪽(동료).** "Panda 좌표가 Mirobot으로 실제로 잘 변환되는지 확인"이 Mirobot 쪽 일이라서다.
  W6–W7 수집은 계획서 10장대로 둘이 같이 한다(한 명 조작, 한 명 리셋). **동료 확인 필요**
- [ ] **결과를 돌려주는 방법** — Mirobot 쪽 측정(손끝 오차, 집게 폭, 실패 장면)이 Panda 쪽의 잡는 높이·블록 크기를 바꾼다(3장 2·3)
  → **잠정 (10/8):** Mirobot 쪽은 측정값을 4장 해당 항목의 `→` 뒤와 CHECKLIST 5절에 적고 push한다.
  Panda 쪽 값을 바꿔야 하는 결과(예: S60 집게 폭이 블록보다 넓다, 손끝이 n mm 어긋난다)는 3장 해당 항목에 한 줄 남겨 알린다.
  Panda 쪽이 견본을 새로 만들면 `docs/W6/poses/`를 갱신하고 push한다

**공용 코드 규칙 (잠정, 동료 확인 필요)**: `common/`과 `tools/`의 공용 파일은 Mirobot 쪽이 맡는다. Panda 쪽이 고칠 일이 생기면 먼저 알린다.
예외로 `tools/action_to_poses.py`는 Panda 쪽이 맡는다. `docs/W6/rgb_blocks/`와 `docs/W6/poses/`도 Panda 쪽이다. 2장 형식은 둘이 같이 바꾼다.

## 6. 실행 예

```bash
# Panda 쪽 — 서버 conda libero
source ~/miniforge3/etc/profile.d/conda.sh && conda activate libero
python -B docs/W6/rgb_blocks/pickup.py --task red --seed 0 --log            # data/pickup/<시각>-pickup-red-s0.jsonl
python -B docs/W6/rgb_blocks/pickup.py --task red --seed 0 --mode reach --log
conda deactivate

# Mirobot 쪽 — 저장소 루트, cosmos-policy/.venv (또는 표준 라이브러리 Python 3.9+)
cosmos-policy/.venv/bin/python -m tools.poses_to_gcode --poses data/pickup/<기록>.jsonl --scale 0.663 --gripper --out trajectories/<이름>.gcode
cosmos-policy/.venv/bin/python -m tools.run_gcode trajectories/<이름>.gcode --dry-run
# 로봇 노트북 — 그리퍼가 든 파일은 --auto 로만 (--stream 은 거부된다)
python -m tools.run_gcode trajectories/<이름>.gcode --port COM4 --auto

# 재현 확인 (선택) — 같은 action 을 시뮬에 다시 넣어 같은 step 에서 Goal 이 뜨는지
cosmos-policy/.venv/bin/python -m tools.action_to_poses --log data/pickup/<기록>.jsonl --out data/poses/<이름>.jsonl
```

한 셸에서 conda `libero`를 켠 채로 `cosmos-policy/.venv` Python을 실행하면 출력이 비는 일이 있었다(10/7·10/8). 위처럼 `conda deactivate`한 뒤 실행한다.

## 관련 문서

- [CHECKLIST.md](CHECKLIST.md) — 이번 주 목표, 실물 3단계, 블록 배치, 변환 확인 기록
- [rgb_blocks/PICKUP.md](rgb_blocks/PICKUP.md) — pick up 설계·결과
- [../W5/PIPELINE.md](../W5/PIPELINE.md) — 번역기(`action_to_gcode.py`)를 처음 만든 기록
- [../W5/TABLE_ALIGNMENT.md](../W5/TABLE_ALIGNMENT.md) — 짝·배율 0.663·세로 정렬
- [../plan/UROP_프로젝트_계획.md](../plan/UROP_프로젝트_계획.md) 10장 — 2인 협업, 인터페이스 불일치가 가장 큰 실패 원인
