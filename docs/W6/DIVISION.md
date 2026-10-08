# W6 분업 — Panda 쪽과 Mirobot 쪽

> **절차** · 확인 2026-10-08 · 기준 `b8a6ea2`(번역기 분리 + 견본 18개)
> 10/8 팀 결정: 이번 주는 지금의 간단한 pick up을 그대로 Mirobot으로 옮겨 실제 경향성을 확인한다([CHECKLIST.md](CHECKLIST.md) 0장).
> 일을 **Panda 쪽**(시뮬 Panda의 손 좌표를 남김)과 **Mirobot 쪽**(손 좌표를 Mirobot 명령으로 바꾸고 실물에서 확인)으로 나눈다.
> 두 쪽은 **손 좌표 JSONL**(3장) 하나로 만난다. `→` 뒤 빈칸은 미리 채우지 않는다.
> 이 문서는 **역할로만** 쓴다. 누가 어느 쪽을 맡는지는 적지 않는다.
> 처음 읽는다면 **1장**(두 작업이 무엇인지)부터 읽는다. 4·5장은 할 일 목록이다.

## 1. 두 작업은 무엇을 하나

### 1.1 먼저 알아 둘 것 — Panda의 명령은 좌표가 아니다

시뮬레이션 Panda는 매 step 7개 숫자(action)를 받는다(OSC_POSE).
`[0:3]`은 "손을 이만큼 움직여라", `[3:6]`은 "이만큼 돌려라", `[6]`은 그리퍼(−1 열기, +1 닫기)다.
**변화량 명령**이라서, 같은 숫자를 넣어도 실제로 얼마나 가는지는 컨트롤러와 물리 시뮬레이션이 정한다.
그래서 action만 보고는 손이 어디 있는지 알 수 없고, **시뮬에서 실제로 돌려 봐야 손 좌표**(world 기준 x, y, z와 자세)가 나온다.

Mirobot은 반대로 `G0 X Y Z A B C`처럼 **"이 좌표로 가라"는 절대 좌표 명령**을 받는다.
그래서 두 로봇 사이는 "Panda 손 좌표 → Mirobot 손 좌표"로 이어야 한다. 이 손 좌표 파일이 두 작업이 만나는 지점이다.

```text
  Panda 쪽                                           Mirobot 쪽
  ─────────────────────────────────────────────      ──────────────────────────────────────────────
  pick up(pickup.py) → action → 시뮬 Panda → 손 좌표   ──▶  Mirobot 좌표로 변환 → G-code → 실물 Mirobot
  (블록을 제대로 집는가?)                    (파일)      (블록 기준으로 같은 행동을 하는가?)
```

### 1.2 Panda 쪽 — 시뮬 Panda의 손 좌표를 정확히 남겨 넘긴다

**이번 주는 지금 만든 간단한 pick up을 그대로 쓴다**(10/8 팀 결정, CHECKLIST 0장). 동작을 새로 만들거나 다듬는 일은 뒤로 미룬다.

- **손 좌표 파일을 만들어 넘긴다.** `pickup.py`가 지시한 색 블록으로 가서 내려가고, 잡고, 들어 올리는 action을 내고,
  실행하면서 step마다 손 위치·자세, action, 관절값을 기록한다(3장 형식). 견본은 `docs/W6/poses/`에 있다.
  시뮬에서 성공했는지도 함께 판정한다(`Up` Goal, 잡고 있는지, 다른 블록을 밀지 않았는지).
- **Mirobot 쪽 결과에 맞춰 값만 조정한다.** 실물 측정이 요구할 때 잡는 높이와 블록 크기를 바꾸고 견본을 다시 만든다(4장 2·3). 동작의 구조는 그대로 둔다.
- **재현 확인**: 같은 action을 새 시뮬에서 다시 넣었을 때 **같은 손 좌표가 나오는지** 본다(`tools/action_to_poses.py`).
  - **비교하는 것은 좌표(결과)다. action(입력)이 아니다.** action은 원래 실행에서 그대로 복사해 넣으므로 항상 같다.
    달라질 수 있는 것은 그 결과로 손이 간 곳이다. 시작 자세, 블록 배치(seed), 컨트롤러, 시뮬 버전이 다르면 같은 action이 다른 곳으로 간다.
  - **step 사이 이동량이 아니라 world 기준 절대 좌표를 비교한다.** 이동량만 보면 시작부터 일정하게 어긋난 경우를 놓친다.
    예를 들어 시작 자세가 1 cm 다르면 매 step 이동량은 같아도 손은 내내 블록 1 cm 옆에 있다.
  - 지금까지: 손 **위치**는 step마다 최대 0.0012 mm 차이, Goal이 처음 뜨는 step도 같다. 손 **자세**는 아직 비교하지 않았다(4장 7).
- **(미룸) 동작 다듬기** — 그리퍼를 돌려 잡기, 블록 회전, 가까운 블록 대응처럼 pick up 자체를 바꾸는 일은
  지금 동작이 Mirobot에서 확인된 뒤에 한다(4장 5). 동작이 바뀌면 Mirobot 쪽이 확인할 대상도 바뀌기 때문이다.

### 1.3 Mirobot 쪽 — 그 손 좌표를 Mirobot 명령으로 바꾸고, 실물이 같은 행동을 하는지 잰다

- **변환을 만들고 다듬는다.** Panda 손 좌표 → Mirobot G0(`tools/poses_to_gcode.py`). 들어가는 값은 다음과 같다.
  - **짝**: "Panda 시작 자세 ↔ Mirobot 홈"을 같은 점으로 보고, 거기서 움직인 만큼만 옮긴다(두 로봇의 원점이 다르기 때문)
  - **배율 0.663**: Panda가 100 mm 움직이면 Mirobot은 66.3 mm. 작업대 높이를 맞추는 세로 정렬로 정했다(W5 TABLE_ALIGNMENT)
  - **자세 변환 F**(x축 180°): 두 로봇이 "손이 아래를 향함"을 다르게 적는 차이
  - **파지점 ↔ 플랜지**: 짝과 변위는 파지점(손가락 사이)끼리 맞춘다. Mirobot G0는 플랜지(손목 끝) 좌표라서
    Panda는 파지점→플랜지 97 mm, Mirobot은 55 mm(자로 잰 값, ±5 mm)를 오간다(W5 회신 "파지점끼리", 9/30)
  - **그리퍼**: Panda의 `action[6]` 부호가 바뀌는 곳에 Mirobot `M4 S40`(열기)·`M4 S60`(닫기)을 넣는다
  - **안전 검사**: 보내기 전에 `run_gcode --dry-run`으로 도달 거리·각도·Z 하한(작업대 충돌)을 본다
- **실물에서 같은 행동을 하는지 잰다.** "같다"의 뜻은 다음과 같다.
  - **동작이 아니라 행동이 같다.** Panda는 관절 7개, Mirobot은 6개라 관절 움직임은 다르다. **손끝이 같은 곳으로 가는지**를 본다
  - **크기는 0.663배다.** 블록 자리도 같은 비율로 옮겨 두었으므로(CHECKLIST 2절), 블록을 기준으로 보면 같은 행동이 된다
  - **비교하는 것**: 손끝이 블록 자리(종이 표시) 위 몇 mm에 오는지, 그리고 지시한 색으로 가서 내려가고 집고 드는 흐름이 시뮬과 같은지
- **결과를 Panda 쪽에 돌려준다.** 집게 폭, 손끝 오차, 실패 장면이 Panda 쪽의 잡는 높이·블록 크기를 바꾼다(6장).

## 2. 경계

```text
[Panda 쪽]                                   [Mirobot 쪽]
pickup.py · action_to_poses.py · BDDL · 뷰어    poses_to_gcode.py · common/workspace.py · common/rotation.py
   │                                            run_gcode.py · (실물 로봇)
   │  action → 시뮬 Panda → 손 좌표
   ▼
손 좌표 JSONL (panda-poses/1, 3장)  ───────────▶  짝·배율·F → Mirobot G0 · 그리퍼 M4 → dry-run → 실물
                                     넘겨주는 지점
```

| | Panda 쪽 | Mirobot 쪽 |
| --- | --- | --- |
| 묻는 것 | 시뮬 Panda의 손 좌표가 정확한가 (지시한 블록을 집고, 다시 돌려도 같은가) | 그 손 좌표가 Mirobot에서 블록 기준으로 같은 행동이 되는가 |
| 결과물 | 손 좌표 JSONL (`docs/W6/poses/`) | Mirobot G-code와 실물 측정 결과 |
| 실행 환경 | 서버 conda `libero` (Python 3.8, LIBERO·MuJoCo) | 표준 라이브러리, **Python 3.9 이상**. 서버 `cosmos-policy/.venv`(3.10)·로봇 노트북 |

`common/`은 `tuple[...]` 표기를 써서 Python 3.8에서는 import부터 실패한다. 그래서 conda `libero`에서는 `poses_to_gcode.py`를 돌릴 수 없다.

### 2.1 번역기를 두 파일로 나눴다 (10/8)

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
| 역변환 검산 (absolute · relative) | 최대 0.012 mm (Mirobot 기준, 반올림 크기). 견본 18개는 최대 0.013 mm |
| 테스트 | `tests/` 48개 통과 (`test_poses_to_gcode.py` 7개 새로) |

## 3. 넘겨주는 파일 — 손 좌표 JSONL (`panda-poses/1`)

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
만든 쪽에 따라 더 있다 — `action_to_poses.py`는 `scene`, `first_done`, `expected_done` 등을 남긴다. 읽는 쪽은 모르는 키를 무시한다.

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

## 4. Panda 쪽 할 일

이번 주에는 지금의 간단한 pick up을 그대로 쓴다(1.2). 우선순위는 다음과 같다.

| 순서 | 항목 | 이유 |
| --- | --- | --- |
| 먼저 | 1 견본 넘기기 (끝남), 7 재현 확인에 자세 추가 | Mirobot 쪽이 받는 좌표가 정확한지가 이번 주 일의 바탕이다 |
| Mirobot 결과가 오면 | 2 잡는 높이, 3 블록 크기 | 값만 바꾸고 동작 구조는 그대로 둔다 |
| 그다음 | 4 브라우저 시연 | 미팅 결과물 |
| 미룸 | 5 pick up 다양화, 6 카메라 도착 후 | 지금 동작이 Mirobot에서 확인된 뒤 |

- [x] **1. 견본 손 좌표를 넘긴다** — `data/`는 git에서 빠지므로 `git pull`로 못 받는다. 6장대로 `docs/W6/poses/`에 올린다.
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
- [ ] **7. 재현 확인에 자세도 넣는다** — `action_to_poses.py`가 원래 기록과 step마다 손 **위치와 자세**(쿼터니언 각도 차)를 비교해 최대 차이를 출력하게 한다.
  지금은 Goal step만 출력하고, 위치 비교는 따로 스크립트로 했다(1.2). 자세는 Mirobot A·B·C로 그대로 넘어가므로 같이 본다
  →

## 5. Mirobot 쪽 할 일

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
  종이 표시는 **Mirobot 원점(받침대 J1 중심)에서 자로 재서** 놓는다 — 로봇을 보내서 표시하면 변환이 아니라 반복 정밀도만 잰다.
  seed별 블록 좌표는 [poses/README.md](poses/README.md) 2장. 처음은 안쪽 끝을 쓰지 않는 seed 2부터
  →
- [ ] **6. 작업 영역 안쪽 끝** — Mirobot X 150–170이 작업대 높이(플랜지 Z 70 근처)에서 닿는지(W5 TABLE_ALIGNMENT 6절). 무작위 배치가 이 범위를 쓴다.
  견본에서는 seed 0 blue(X 157.8)와 seed 1 blue(X 165.4)가 이 범위다
  →
- [ ] **7. 실물 3단계 (pick up)** — 그리퍼까지. 블록 대용품(약 26 mm)으로 경향성을 본다: 지시한 색으로 가는가, 내려가는가, 집는가, 드는가
  →
- [ ] **8. Z 경고 구간** — 플랜지 Z 66–71 mm 줄은 경고만 하고 보낸다. 견본 pick up 9개 중 3개에 있다
  (blue-s0 11줄, blue-s1 4줄, red-s1 4줄. 최저 70.1 mm). 잡는 높이가 하한 가까이 내려가서다. 그대로 둘지 정한다
  →
- [ ] **(나중에)** W3 `tools/libero_to_mirobot_gcode.py`(waypoint만, 그리퍼 없음)와 `poses_to_gcode.py`를 합칠지
  →

## 6. 함께 정할 것

- [x] **손 좌표를 넘기는 방법** — (가) 견본을 git이 추적하는 폴더(예: `docs/W6/poses/`)에 올린다 / (나) Mirobot 쪽이 서버에서 `pickup.py --log`를 직접 실행한다.
  (가)는 파일 하나에 약 95 KB다
  → **(가)로 했다 (10/8).** Panda 쪽이 `docs/W6/poses/`에 견본을 올리고 push한다. 이름은 `<mode>-<색>-s<seed>.jsonl`.
  Mirobot 쪽은 `git pull`로 받는다. 서버 conda 환경 없이도 변환을 시작할 수 있어서다. 더 필요한 seed는 (나)로 직접 만들어도 된다
- [x] **실물 로봇 담당** — 로봇 앞에서 측정할 사람. 측정 결과는 CHECKLIST 5절에 남긴다
  → **Mirobot 쪽 (10/8 정함).** 실물 로봇을 다룰 시간이 더 있는 쪽이 Mirobot 쪽을 맡았다.
  "Panda 좌표가 Mirobot으로 실제로 잘 변환되는지 확인"도 Mirobot 쪽 일이다.
  W6–W7 수집은 계획서 10장대로 둘이 같이 한다(한 명 조작, 한 명 리셋)
- [ ] **결과를 돌려주는 방법** — Mirobot 쪽 측정(손끝 오차, 집게 폭, 실패 장면)이 Panda 쪽의 잡는 높이·블록 크기를 바꾼다(4장 2·3)
  → **잠정 (10/8):** Mirobot 쪽은 측정값을 5장 해당 항목의 `→` 뒤와 CHECKLIST 5절에 적고 push한다.
  Panda 쪽 값을 바꿔야 하는 결과(예: S60 집게 폭이 블록보다 넓다, 손끝이 n mm 어긋난다)는 4장 해당 항목에 한 줄 남겨 알린다.
  Panda 쪽이 견본을 새로 만들면 `docs/W6/poses/`를 갱신하고 push한다

**공용 코드 규칙 (잠정, 두 쪽이 확인)**: `common/`과 `tools/`의 공용 파일은 Mirobot 쪽이 맡는다. Panda 쪽이 고칠 일이 생기면 먼저 알린다.
예외로 `tools/action_to_poses.py`는 Panda 쪽이 맡는다. `docs/W6/rgb_blocks/`와 `docs/W6/poses/`도 Panda 쪽이다. 3장 형식은 둘이 같이 바꾼다.

## 7. 실행 예

```bash
# Panda 쪽 — 서버 conda libero
source ~/miniforge3/etc/profile.d/conda.sh && conda activate libero
python -B docs/W6/rgb_blocks/pickup.py --task red --seed 0 --log            # data/pickup/<시각>-pickup-red-s0.jsonl
python -B docs/W6/rgb_blocks/pickup.py --task red --seed 0 --mode reach --log
conda deactivate

# Mirobot 쪽 — 저장소 루트, cosmos-policy/.venv (또는 표준 라이브러리 Python 3.9+). 견본으로 시작한다
cosmos-policy/.venv/bin/python -m tools.poses_to_gcode --poses docs/W6/poses/pickup-red-s2.jsonl --scale 0.663 --gripper --out trajectories/<이름>.gcode
cosmos-policy/.venv/bin/python -m tools.poses_to_gcode --poses docs/W6/poses/reach-red-s2.jsonl --scale 0.663 --out trajectories/<이름>.gcode   # 손 뻗기는 --gripper 없이
cosmos-policy/.venv/bin/python -m tools.run_gcode trajectories/<이름>.gcode --dry-run
# 로봇 노트북 — 그리퍼가 든 파일은 --auto 로만 (--stream 은 거부된다)
python -m tools.run_gcode trajectories/<이름>.gcode --port COM4 --auto

# 재현 확인 (선택) — 같은 action 을 시뮬에 다시 넣어 같은 step 에서 Goal 이 뜨는지
cosmos-policy/.venv/bin/python -m tools.action_to_poses --log data/pickup/<기록>.jsonl --out data/poses/<이름>.jsonl
```

한 셸에서 conda `libero`를 켠 채로 `cosmos-policy/.venv` Python을 실행하면 출력이 비는 일이 있었다(10/7·10/8). 위처럼 `conda deactivate`한 뒤 실행한다.

## 관련 문서

- [CHECKLIST.md](CHECKLIST.md) — 이번 주 목표, 실물 3단계, 블록 배치, 변환 확인 기록
- [poses/README.md](poses/README.md) — 견본 18개, seed별 블록 좌표(종이 표시), 변환 확인 결과
- [rgb_blocks/PICKUP.md](rgb_blocks/PICKUP.md) — pick up 설계·결과
- [../W5/PIPELINE.md](../W5/PIPELINE.md) — 번역기(`action_to_gcode.py`)를 처음 만든 기록
- [../W5/TABLE_ALIGNMENT.md](../W5/TABLE_ALIGNMENT.md) — 짝·배율 0.663·세로 정렬
- [../W3/CONVERSION.md](../W3/CONVERSION.md), [../W3/LIBERO_AXES.md](../W3/LIBERO_AXES.md) — 좌표·자세 변환의 근거
- [../meetings/2026-09-28/Professor reply.md](../meetings/2026-09-28/Professor%20reply.md) — 파지점끼리 맞추라는 회신 (9/30)
- [../plan/UROP_프로젝트_계획.md](../plan/UROP_프로젝트_계획.md) 10장 — 2인 협업, 인터페이스 불일치가 가장 큰 실패 원인
