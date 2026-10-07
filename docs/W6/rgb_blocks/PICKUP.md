# Panda Pick up 구현 기록

> **진행 기록** · 시작 2026-10-06
> RGB 블록 Tabletop에서 Panda가 색상별 블록을 실제로 집어 들어 올리는 action과 성공 Goal을 구현한다.

## 1. 범위

- Task: `Pick up the red / green / blue block on the table.`
- 파이프라인([2026-10-05 회의](../../meetings/2026-10-05.md))에서 **LIBERO / Panda Action 수행** 단계를 맡는다.
  다음 단계에서는 LIBERO 좌표(x, y, z)와 자세 값을 받아 Mirobot 좌표로 변환한다.
- 시작 시점 커밋 `6f64688`: 블록 등록, 색상별 BDDL, 브라우저 뷰어까지 완료한 상태.
  pick up action과 성공 Predicate는 아직 없다.

## 2. 시작 상태 확인 (2026-10-06)

`test_rgb_blocks.py --task red --headless --steps 60 --size 512 --seed 0` 실행 결과:

| 항목 | 값 |
| --- | --- |
| 세 블록 `table_contact` | 모두 `true` |
| 초기 goal / 60 step 후 goal | `True` / `True` (배치 확인용 Goal이므로 정상) |
| 블록 중심 z (40 mm 블록) | 약 0.920 m → 테이블 윗면 약 0.90 m |

### 2.1 블록 배치 조정 범위 (2026-10-06 확인)

> **10/7 배치 변경**: 블록 자리를 Mirobot이 닿는 세 점으로 옮겼다. 영역 반폭이 30 mm라 위치는 사실상 고정이다.
> 아래 seed 표는 **변경 전 배치**의 값이다. 새 배치와 재검증은 [../CHECKLIST.md](../CHECKLIST.md) 2절에 있다.

- 좌표: 테이블 중심이 (0, 0), 윗면 z = 0.90 m, 테이블 크기 x −0.5~0.5, y −0.6~0.6.
  Panda base는 (−0.66, 0, 0.912)이므로 x가 클수록 로봇에서 멀어진다.
- BDDL `:ranges (x1 y1 x2 y2)`는 **놓일 영역**이다. 영역 안 위치는 seed로 무작위 결정된다.

| seed (`--task red`) | red (x, y) | green | blue |
| --- | --- | --- | --- |
| 0 | (+0.013, −0.287) | (−0.093, +0.010) | (−0.204, +0.211) |
| 1 | (−0.172, −0.216) | (−0.059, −0.012) | (−0.188, +0.227) |
| 2 | (−0.149, −0.303) | (−0.093, −0.052) | (−0.177, +0.311) |

| 항목 | 조정 방법 |
| --- | --- |
| 영역 | BDDL `:ranges` — `tabletop.bddl`, `tasks/*.bddl` 4개를 함께 수정 |
| 정확한 위치 | 직접 지정 불가. 범위를 매우 좁게 잡으면 사실상 고정 (미검증) |
| 크기 | `objects.py` `BLOCK_SIZE_MM` (≤ 120 mm) |
| 회전 yaw | `objects.py` `self.rotation = (0, 0)`으로 고정. BDDL `:yaw_rotation`은 fixture에만 적용 |

## 3. 기존 Pick up action 유무

- LIBERO(robosuite)에는 "pick up" 같은 고수준 action이 **없다**.
  Panda가 받는 것은 매 step 입력하는 7차원 OSC_POSE action 하나다.
  - `[0:3]` EEF 위치 변화, `[3:6]` 회전 변화, `[6]` gripper (`-1` open, `+1` close)
- 따라서 pick up은 이 action을 여러 step 이어서 만드는 **scripted controller**로 구현한다.
- 참고 코드: W5 [`test_custom_task_variants.py`](../../W5/custom_task_validation/test_custom_task_variants.py)
  `run_robot_attempt`의 task B(우유 잡아 들기).
  잡는 높이와 그리퍼 방향이 우유 기준이므로 블록에 맞게 수정해야 한다.

## 4. 결정 사항

### 4.1 성공 Goal — A안: LIBERO 기본 `Up` predicate (2026-10-06 결정)

| 안 | 내용 | 결과 |
| --- | --- | --- |
| **A** | BDDL Goal을 `(Up <color>_block_1)`로 둔다. grasp 여부는 스크립트에서 `_check_grasp`로 따로 확인한다. | **채택** |
| B | grasp 확인과 상대 높이를 묶은 새 predicate(`PickedUp` 등)를 등록한다. | 보류 (A가 동작한 뒤 필요하면 추가) |

A안을 고른 이유: LIBERO 코드를 수정하지 않고 Goal이 `False → True`로 바뀌는 것을 확인할 수 있다.

`Up` 정의(`LIBERO/libero/libero/envs/predicates/base_predicates.py`):

```python
class Up(BinaryAtomic):
    def __call__(self, arg1):
        return arg1.get_geom_state()["pos"][2] >= 1.0
```

- 높이 기준이 **절대값 z ≥ 1.0 m**다. 40 mm 블록은 중심을 약 **8 cm** 이상 들어 올려야 한다.
- 높이만 판정하므로 BDDL만 보면 "잡고 있는지"는 알 수 없다. → 스크립트에서 `_check_grasp`로 따로 확인한다.

**BDDL 동작 검증 (2026-10-06)**

`tasks/red.bddl`의 Goal만 `(And (Up red_block_1))`로 바꾼 사본을 scratchpad에 만들었다.
저장소 파일은 수정하지 않았다. W5 8.5의 직접 상태 변경 시험과 같은 방식으로 블록의 free joint z를 직접 바꿨다.

| 확인 | 결과 |
| --- | --- |
| parser 결과 `goal_state` | `[['up', 'red_block_1']]` |
| 초기 goal | `False` |
| 블록 z = 0.990 m | `False` |
| 블록 z = 1.010 m | `True` |

→ `Up`은 BDDL Goal에서 정상 동작한다.

### 4.2 Action 구조 (2026-10-06, 추천안으로 진행)

구현을 먼저 끝내기로 하면서 아래 두 항목은 추천안으로 진행했다. 바꿔야 하면 다시 정한다.

- **마지막 상태: 들고 있는 상태로 종료.** 내려놓으면 블록이 테이블로 돌아가 `Up`이 다시 `False`가 된다.
- **EEF 자세 출력: stdout만.** 단계마다 위치 `xyz_m`와 자세 `rxyz_deg`를 출력하고 파일로 저장하지 않는다.
  `rxyz_deg`는 scipy `as_euler("xyz")`(extrinsic x→y→z, deg)다. Mirobot 변환 단계에서 각도 규약을 맞춰야 한다.

```text
settle   (20 step, gripper open)
approach 블록 중심 위 +0.15 m
lower    블록 중심 높이 (grip_site와 finger pad 높이가 거의 같음)
grasp    gripper close 30 step → _check_grasp 확인
lift     +0.15 m (블록 z 약 1.06 m)
verify   30 step 유지 — goal True, 계속 잡고 있는지 확인
```

- 그리퍼 자세는 top-down이고 `TOP_DOWN = [[0,1,0],[1,0,0],[0,0,-1]]`로 W5 task B와 같다.
  Panda reset 자세와 거의 같으며 손가락은 world y 방향으로 벌어진다. 블록 yaw가 0이므로 손가락이 블록 면과 나란하다.
- 제어 방식은 W5와 같은 feedback 제어다. `action[:3] = clip((목표 − EEF)/0.05, ±0.5)`, 회전은 rotvec 오차/0.5를 쓴다.
- 물체 위치나 관절 값은 직접 바꾸지 않는다. 오직 `env.step(action)`으로만 움직인다.

### 4.3 성공 판정 (2026-10-06)

"지시한 색의 블록을 들어 올렸는가"를 아래 세 조건으로 판정한다.

| 조건 | 확인 위치 | 의미 |
| --- | --- | --- |
| `(Up <color>_block_1)` | BDDL Goal (`env.check_success()`) | 지시한 색 블록이 z ≥ 1.0 m |
| `_check_grasp(gripper, block)` | `pickup.py` | 그 블록을 그리퍼가 잡고 있음 |
| 나머지 두 블록의 `On ... region` | `pickup.py` | 다른 색 블록은 건드리지 않음 |

시작할 때 goal이 `False`여야 하고, verify 30 step 동안 계속 `True`여야 한다.

## 5. 구현 (2026-10-06)

| 파일 | 변경 |
| --- | --- |
| [pickup.py](./pickup.py) | **신규.** `run_pickup(env, obs, target, on_step=None)`과 CLI |
| [tasks/red·green·blue.bddl](./tasks/) | Goal을 `(And (Up <color>_block_1))`로 교체 |
| [tasks.py](./tasks.py) | 색상 task는 `goal_kind: "pickup"`, `pickup_implemented: True` |
| [preview.py](./preview.py) `scene_state` | 배치 판정을 `:init` 조건으로 수행. goal `True`는 `scene`에서만 요구 |
| [test_rgb_blocks.py](./test_rgb_blocks.py) | 배치는 `:init`으로 확인. pickup task는 시작 goal이 `False`인지 확인 |
| [browser_viewer.py](./browser_viewer.py) | "배치 정상" 표시는 `placement_ok`를 기준으로 함. `--pickup` 모드 추가 (5.1) |
| [test_browser_viewer_http.py](./test_browser_viewer_http.py) | `zero_actions_only: False`(pickup 모드)를 정상 상태로 인정. 모드가 다른 서버는 재사용하지 않음 (47 tests OK) |

실행:

```bash
source ~/miniforge3/etc/profile.d/conda.sh
conda activate libero
python -B ~/UROP/docs/W6/rgb_blocks/pickup.py --task red --seed 0
```

성공하면 exit 0, 실패하면 exit 1이다. 단계별 JSON 한 줄과 마지막 요약을 stdout에 출력한다.

### 5.1 브라우저에서 pick up 보기 (2026-10-06)

```bash
bash ~/UROP/docs/W6/rgb_blocks/run_browser.sh --task red --pickup
```

- `pickup.py`의 `run_pickup`을 `on_step` callback으로 연결했다. Panda가 움직이는 모든 step을 20 FPS 실시간으로 보여준다.
- seed → seed+1 → … 순서로 반복한다. 각 episode가 끝나면 결과 자세를 3초 보여준 뒤 다음 seed로 reset한다.
  같은 env에서 `env.seed(s); env.reset()`을 하면 처음 만든 env와 같은 배치가 나오는 것을 확인했다.
- 화면 아래에 episode, seed, phase, step, goal, 누적 성공 수, 직전 결과가 표시된다.
  터미널에는 단계별 JSON과 seed별 결과를 출력한다.
- **사용자 화면 확인 (2026-10-06)**: red에서 블록을 정상적으로 집었고, goal이 단계에 맞게 `False → True`로 바뀌는 것을 확인했다.
  green, blue도 정상 동작을 확인했다. 뷰어 실행 기록: green seed 0–4, blue seed 0–2 모두 성공.
- `--pickup` 없이 실행하면 기존처럼 Panda가 움직이지 않는 배치 확인 화면이다. `--pickup`은 red / green / blue에서만 쓸 수 있다.

### 5.2 손 뻗기 모드와 기록 (2026-10-07)

- `--mode reach`: settle → approach → hover(손끝이 Mirobot 기준 작업대 위 30 mm) → 20 step 유지 → rise → 시작 자세로 return.
  성공 조건은 블록 위 수평 오차 < 5 mm, 어떤 블록에도 닿지 않음, 모든 블록이 제자리, Goal이 `False`로 끝남이다.
  seed 0에서 세 색 모두 성공했다(수평 오차 0.2–0.4 mm, 손끝 29.9–30.0 mm).
- `--log`: 번역기 입력용 JSONL. 형식과 Mirobot 변환 결과는 [../CHECKLIST.md](../CHECKLIST.md) 3·4절에 있다.
- 공통 동작은 `PandaMover`로 묶었다. `run_pickup`의 동작과 결과는 바뀌지 않았다(red seed 0, 146 step).

## 6. 결과 (2026-10-06)

`pickup.py`를 red / green / blue × seed 0–4로 15회 실행했다. **15/15 성공.**

| 항목 | 결과 |
| --- | --- |
| 초기 goal | 모두 `False` |
| grasp 확인 / verify 후에도 잡고 있음 | 모두 `True` / `True` |
| 들어 올린 높이 | 0.143–0.147 m |
| verify 30 step 동안 goal | 모두 계속 `True` |
| 다른 블록 배치 유지 | 모두 `True` |
| 총 step | 146–185 (20 Hz 기준 약 7–9초) |

**10/7 재검증 (새 배치)**: red / green / blue × seed 0–4, **15/15 성공**. 모두 146 step이고, 들어 올린 높이는 0.146–0.147 m다.

red seed 0 단계별 EEF (`xyz_m`, `rxyz_deg`):

| phase | step | EEF xyz (m) | Rx, Ry, Rz (deg) | 블록 z (m) | goal |
| --- | ---: | --- | --- | ---: | --- |
| settle | 20 | (−0.209, 0.000, 1.173) | (179.9, 0.0, 90.0) | 0.920 | False |
| approach | 57 | (0.016, −0.289, 1.073) | (−179.2, −0.5, 90.0) | 0.920 | False |
| lower | 23 | (0.012, −0.286, 0.924) | (179.9, 0.1, 90.0) | 0.920 | False |
| grasp | 30 | (0.014, −0.287, 0.921) | (−180.0, −0.1, 90.0) | 0.919 | False |
| lift | 25 | (0.011, −0.286, 1.066) | (179.6, 0.2, 90.0) | 1.064 | True |
| verify | 30 | (0.011, −0.286, 1.065) | (180.0, 0.0, 90.0) | 1.064 | True |

기존 검증 재실행: `test_rgb_blocks.py --headless --steps 60 --size 512 --seed 0`를 scene / red / green / blue로 모두 통과했다.
`scene`은 goal `True`를 유지했고, 색상 task는 goal `False`이면서 배치가 정상이었다.
`python -m unittest test_browser_viewer_http`는 45개 테스트를 모두 통과했다.

## 7. 한계와 나아갈 방향 (2026-10-06)

**한계**: 지금 pick up은 **어느 블록이 어떤 색이고 어디에 있는지 이미 아는 상태**에서 그 위치로 이동한다.
- 색: task 설정(`tasks.py`)에서 대상 물체 이름(`red_block_1`)을 받는다. 화면에서 빨간색을 찾는 것이 아니다.
- 좌표: 시뮬레이터 정답 좌표(`get_geom_state()["pos"]`, MuJoCo `body_xpos`)를 읽는다.
- 카메라 영상(`agentview_image`)은 화면 표시에만 쓰이고 pick up 판단에는 쓰이지 않는다.

**나아갈 방향**: 색과 좌표 정보 없이 **카메라 영상만으로 블록의 색과 좌표를 판단**하고 pick up을 수행한다.
실제 Mirobot 환경에는 정답 좌표가 없으므로 이 단계가 꼭 필요하다.

## 8. 다음 단계

- [x] 뷰어로 기본 pick up 동작 확인 — red / green / blue 모두 정상 (2026-10-06)
- [x] README / AGENTS.md 갱신: `--pickup` 실행법, `Up` Goal, 시작 goal 해석 (2026-10-06)
- [ ] 아직 확인하지 않은 범위 (기본 pick up을 다듬은 뒤 진행)
      - 위치: 현재 region 밖, 로봇에서 먼 곳
      - 블록 회전(yaw) — 지금은 0°로 고정, 그리퍼 방향도 고정
      - 블록끼리 가까운 배치
      - 시뮬레이터 정답 좌표 대신 실제 단계에서 블록 위치를 얻는 방법
- [ ] 좌표·자세 획득 → Mirobot 변환 → 실물: 이번 주 진행은 [../CHECKLIST.md](../CHECKLIST.md) 3–5절에서 관리한다
- [ ] 이해 높이기: ③ LIBERO Tabletop, ④ Simulator 작동, 7차원 action 구조 설명
