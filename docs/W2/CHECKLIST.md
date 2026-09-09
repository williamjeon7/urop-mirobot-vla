# W2 — 확인 목록

> **절차** · 확인 2026-09-09 · 기준 `cosmos-policy@18a2acc`
> 9/7 미팅 B 의견 세 항목을 수행하기 위한 작업 목록. 결론은 내가 채운다.

## 사용법

각 의견마다 **대상 → 확인 → 정리** 순서다. `→` 뒤 빈칸은 **내가 채운다.**
채우지 못하면 아직 이해하지 못한 것이다.

발표에서 필요한 것은 문서를 알아보는 능력이 아니라 **덮고 재구성하는 능력**이다.
그래서 결론을 미리 적지 않는다.

---

## 0. 주의 — 아직 확인되지 않은 주장

대화에서 나온 내용 중 **사실처럼 발표하면 안 되는 것들.**

| 주장 | 상태 | 어디서 다루나 |
|---|---|---|
| 모델이 정규화된 값을 주고받는다 | docstring CLI 예시만 봄 | 의견 ① |
| Panda 가 7관절 / 컨트롤러가 OSC | repo 에서 확인 안 함 | 의견 ③ |
| 형식만 맞춰서는 안 되고 재학습이 필요 | 추론. zero-shot 시도한 적 없음 | 해석 |
| 의견의 의도가 "수집 규격 선행 조사" | 추론. 교수님이 그렇게 말한 적 없음 | 다음 미팅 확인 |

확인된 것: proprio 9차원 = 우리 STATE 순서 동일(`run_libero_eval.py:334`),
액션 7차원 = Cartesian 델타 6 + 그리퍼 1(`libero_utils.py:42`),
계획서가 파인튜닝 전제(`계획서:138-160`), 액션 표현 잠정 권고 EE 4차원(`계획서:325`).

---

## 1. 의견 ① — 롤아웃 데이터의 생성·누적·저장 경로 파악

**과제**
에피소드 하나를 돌렸을 때 어떤 데이터가 **어디서 만들어져 어떻게 쌓이고
무엇으로 저장되는지** 전 경로를 추적한다.

**산출물**
우리가 Mirobot 데모를 수집할 때 **남겨야 할 필드 목록.**
계획서 §6 수집 규격(`계획서:312-321`)과 대조해 빠진 것을 찾는다.
이것이 필요한 이유는 — 필드 하나가 빠지면 **재수집 외에 복구가 없기 때문**이다.

**대상**: `cosmos-policy/cosmos_policy/experiments/robot/libero/`
전부 clone 안에 있고 실행이 필요 없다. 오늘 완결 가능.

> 원문: "LIBERO 에서 롤아웃별로 나오는 정보 확인 — 이미지와 롤아웃 샘플이
> 어떻게 관리되고 있는지"

### 정책이 받는 것

- [x] `prepare_observation()` — `run_libero_eval.py:324`
- [x] `get_libero_image()` / `get_libero_wrist_image()` — `libero_utils.py:45,53`

**관측 키와 형태** — 키는 **3개뿐**이다.

| 키 | 형태 | dtype | 원본 obs 키 |
|---|---|---|---|
| `primary_image` | (256, 256, 3) | uint8 | `agentview_image` — 3인칭 고정 카메라 |
| `wrist_image` | (256, 256, 3) | uint8 | `robot0_eye_in_hand_image` — 손목 1인칭 |
| `proprio` | (9,) | float64 | 아래 3개를 `np.concatenate` |

`proprio` 는 시뮬이 주는 값이 아니라 **매 스텝 조립**된다 (`run_libero_eval.py:334`):

```python
np.concatenate((obs["robot0_gripper_qpos"],  # 2
                obs["robot0_eef_pos"],       # 3  meter, MuJoCo world frame
                obs["robot0_eef_quat"]))     # 4  (w, x, y, z) 순, norm=1
```

`sample_libero_10_observation.pkl` 실측값:

```
gripper  [0] 0.038723   [1] -0.038722     ← 부호만 반대인 대칭
eef_pos  [2] -0.046149  [3] -0.003568  [4] 0.702046
eef_quat [5] 0.999637   [6] -0.000455  [7] -0.026944  [8] -0.000121
```

**전처리는 하지 않는다.** `get_libero_image()` 는 `obs` 에서 꺼내 그대로 반환하고,
`flip_images=True` 일 때만 `np.flipud` 를 건다. **평가 시 기본값은 `True`**
(`PolicyEvalConfig.flip_images = True`, `:201`) — 함수 시그니처의 `False`(`:324`)는
쓰이지 않는다. 호출부가 `cfg.flip_images` 를 넘기기 때문(`:408`).
docstring 의 "preprocesses it" 과 `prepare_observation(obs, resize_size, ...)` 의
`resize_size` 인자는 **둘 다 실제로 동작하지 않는다** — 리사이즈 코드를 떼어낸 흔적.

→ 이식 시 **원본 크기 uint8 을 그대로 넘기면 된다.** 정규화·리사이즈는 정책 내부 몫.

**확인 필요**
- 그리퍼 2차원이 대칭값인데 Mirobot 그리퍼는 무엇으로 채울 것인가 → 
- `eef_pos_z = 0.702` vs 우리 demo_0 `z = 0.177` — 좌표계 원점이 다르다.
  `common/gcode.py` 의 `+54mm` 오프셋과 같은 종류의 정렬이 필요 → 
- 쿼터니언이 `wxyz` 순. 라이브러리에 따라 `xyzw` 를 쓰므로 이식 시 확인 → 

### 롤아웃 동안 쌓이는 것

- [x] `run_episode()` 루프 — 매 스텝 무엇이 append 되나
- [x] `replay_images` / `replay_wrist_images` — `run_libero_eval.py:377,409`
- [x] `primary_images_list` / `wrist_images_list` / `proprio_list` — `:386-388`
- [x] `collected_data` 로 묶이는 배열들 — `:621-623`

**누적 경로가 두 갈래다.** 같은 이미지를 목적이 달라 따로 쌓는다.

| 갈래 | 변수 | 조건 | 용도 |
|---|---|---|---|
| A | `replay_images`, `replay_wrist_images` | 항상 | 결과 **영상** |
| B | `primary_images_list`, `wrist_images_list`, `proprio_list`, `actions_list` | `data_collection=True` 일 때만 | **학습 데이터** |

**주기가 셋 다 다르다.**

| | 주기 | 근거 |
|---|---|---|
| 이미지 추출·누적 | 매 스텝 | `:408-409` 무조건 실행 |
| 정책 호출 | **16스텝에 한 번** | `:419` 큐가 빌 때만. `num_open_loop_steps=16` (`:216`) |
| 액션 실행 | 매 스텝 | `:598` 큐에서 popleft |

처음 `NUM_STEPS_WAIT = 10` 스텝은 물체 안정화용 더미 액션이고 **누적되지 않는다**
(`:402-405`, `continue`).

**한 롤아웃이 남기는 배열** (`:620-626`) — `T` = 실제 실행 스텝 수

| 키 | shape | 내용 |
|---|---|---|
| `primary_images` | (T, 256, 256, 3) uint8 | 3인칭 |
| `wrist_images` | (T, 256, 256, 3) uint8 | 손목 |
| `proprio` | (T, 9) float64 | |
| `actions` | (T, 7) | |
| `success` | bool | 배열 아님 → HDF5 **attribute** |
| `future_primary_images` | (T', 256, 256, 3) | 조건부 — 모델이 미래 프레임을 예측할 때만 |
| `future_wrist_images` | (T', 256, 256, 3) | 조건부 |

### 저장되는 것

- [x] `save_rollout_video()` — `libero_utils.py:61`
- [x] `data_collection=True` 옵션
- [x] metainfo 의 `success` 라벨과 `initial_state`

**형식: 에피소드 하나당 HDF5 파일 하나** (`run_libero_eval.py:750-770`)

```
<local_log_dir>/rollout_data/
  episode_data--suite=<스위트>--<날짜시각>--task=<id>--ep=<n>--success=<T/F>--<note>.hdf5
```

- **파일명에 성공 여부가 박힌다** — 열지 않고도 성공/실패를 가를 수 있다
- `jpeg_compress=True` 면 4차원 uint8 배열을 **프레임별 JPEG(품질 95)** 로 압축해
  `<키>_jpeg` 이름으로 저장 (`:761-763`). 가변길이라 `h5py.vlen_dtype`
- 배열이 아닌 값(`success`)은 **HDF5 attribute** 로 (`:768`)
- `task_description` 도 attribute 로 함께 저장 (`:770`) ← **자연어 지시문**

**성공/실패 모두 저장한다.** 주석에 명시: *"This captures ALL episodes
regardless of success/failure"* — Failure Detection 재료가 여기서 나온다.

### 딸린 확인 — 정규화 (0절 미확인 항목)

`run_libero_eval.py:50-52` 는 파일 상단 **사용 예시 주석**이지 동작 코드가 아니다.
실제로 어디서 쓰이는지 봐야 "Mirobot 값을 그냥 넣으면 왜 안 되는지" 를 설명할 수 있다.

```bash
grep -n "dataset_stats\|unnormalize\|normalize_proprio" \
  cosmos-policy/cosmos_policy/experiments/robot/libero/run_libero_eval.py
```

- 통계 파일을 읽는 곳 → `load_dataset_stats()` (`cosmos_utils.py:233`).
  `:824` 에서 호출되어 이후 전 경로에 인자로 전달된다
- 실제로 도는 곳 → `cosmos_utils.py:637-645`(액션 역정규화),
  `:664-675`(proprio 정규화). 적용 스위치는 `run_libero_eval.py:936`
- 어떤 통계값인가 → **min·max** 다 (mean·std 도 분위수도 아님).
  키는 `actions_min/max`, `proprio_min/max`

```python
# proprio: 원래 값 → [-1, +1]           cosmos_utils.py:670
rescaled = 2 * ((arr - curr_min) / (curr_max - curr_min)) - 1

# 액션: [-1, +1] → 원래 단위 (역방향)    cosmos_utils.py:645
actions = 0.5 * (actions + 1) * (actions_max - actions_min) + actions_min
```

→ **모델은 [-1, +1] 공간에서만 산다.** 실제 단위와의 환산은 전적으로
`libero_dataset_statistics.json` 의 min/max 에 의존한다.
Mirobot 데이터를 넣으려면 **우리 데이터의 min/max 로 통계 파일을 새로 만들어야**
한다. LIBERO 통계를 그대로 쓰면 값이 범위 밖으로 나가거나 뭉친다.

### 딸린 확인 — 이미지 방향

`flip_images` 기본값은 `False`. **실물 카메라에서 위아래가 어긋나면 학습이 통째로 틀어진다.**

- 학습 시 어떤 값이었나 / 근거 → **`True`**. `PolicyEvalConfig.flip_images` 기본값이
  `True` 이고(`:201`), README 의 실행 예시도 `--flip_images True` 로 넘긴다(`:69,100`).
  즉 **상하 반전된 이미지로 학습·평가된다.**
  → 실물 카메라 프레임도 같은 방향으로 맞춰야 한다. 방향이 뒤집혀도 **에러가 나지 않으므로**
  조용히 성능만 나빠진다

### 정리

- **우리가 남겨야 할 필드 목록** → 


- 계획서 §6 수집 규격(`계획서:312-321`)과 대조해 빠진 것 → 


---

## 2. 의견 ② — 우리 재생·시뮬 코드의 동작 상태 파악

**과제**
`robot/` · `server/` 의 재생·시뮬 스크립트 6개가 **각각 무엇을 하고 지금 도는지**
확인한다. 특히 유일한 실시간 시뮬인 `replay_with_mujoco.py`(716줄)가
돌지 않는 원인과 복구에 필요한 것을 특정한다.

**산출물**
파일별 동작 여부 표 + **무엇이 빠졌는지 목록.**
복구가 과제인지 상태 정리가 과제인지는 미팅에서 확인한다(§5).

**대상은 우리 저장소 코드다** — LIBERO 쪽이 아니다.

> 원문: "시뮬 코드 확인"

### 현황 (확인됨)

| 파일 | 줄 | 상태 |
|---|---|---|
| `robot/replay_serial.py` | 170 | 동작 — 시리얼 직결 재생 |
| `robot/replay_demo0.py` | 123 | 동작 — demo_0 만, 첫 연결 확인용 |
| `robot/replay_hdf5.py` | 169 | 동작. 단 기본 `--hdf5` 경로의 파일이 없음 |
| `server/replay_network.py` | 132 | 동작 — 브리지 경유 |
| `server/replay_with_viewer.py` | 290 | 저장된 프레임을 읽어 보여줌. 실시간 시뮬 아님 |
| `server/replay_with_mujoco.py` | **716** | **미동작** |

`replay_with_mujoco.py` 가 유일한 실시간 시뮬인데 돌지 않는다. 원인 확인됨:

```python
# server/replay_with_mujoco.py:41-42
from cosmos_policy.experiments.robot.mirobot import MirobotCosmosEnv
from cosmos_policy.experiments.robot.mirobot.paths import WRIST_UNDER_V1_XML_PATH
```

clone 한 `cosmos_policy/experiments/robot/` 에는 `aloha/ libero/ robocasa/` 만 있고
**`mirobot/` 이 없다.** 업스트림에 존재하지 않는 모듈이다.

### 확인할 것

- [ ] 716줄이 무엇을 하려던 코드인가 — 구조만 읽어도 파악 가능
- [ ] `MirobotCosmosEnv` 가 원래 무엇이었나. git 히스토리·서버에 남아 있나
- [ ] `WRIST_UNDER_V1_XML_PATH` — MuJoCo 모델 XML 은 어디 있나
- [ ] `replay_with_viewer.py`(290줄)로 대체 가능한가
- [ ] `replay_hdf5.py` 의 기본 경로 파일은 어디서 오나
- [ ] `replay_serial.py` / `replay_network.py` 의 재생 루프 구조

### 정리

- **무엇이 빠졌나** → 


- **복구가 과제인가, 상태 정리가 과제인가** → (미팅에서 확인)


---

## 3. 의견 ③ — 액션을 Cartesian 에 둘 것인가 관절 공간에 둘 것인가

**과제**
정책이 내보낼 액션을 **EE(손끝 좌표) 공간에 둘지, 관절각 공간에 둘지** 결정한다.
LIBERO 가 어느 쪽을 쓰는지, 그것이 6축 Mirobot 에 적용 가능한지가 근거가 된다.

**산출물**
결정 + 근거. `../plan/운영기준.md` §7 에 남긴다.
이 결정이 **데모 수집 형식을 바꾸므로** 의견 ①과 묶여 있다.

> 원문: "LIBERO 를 쓴다면 FK 와 IK 를 비교해서 어느 쪽을 쓰는 것이 맞을지 판단"

### 왜 질문을 바꿔 적었나

**FK 와 IK 는 고르는 것이 아니다.** 서로의 역연산이고 둘 다 쓴다.
손이 어디 있는지 알려면 FK, 원하는 곳으로 보내려면 IK.

진짜 선택지는 **"정책의 출력을 어느 공간에 둘 것이냐"** 다.
계획서 `:325` 의 미결 표와 `plan/운영기준.md` §7 이 같은 얘기다.

| | 관절각 7차원 | EE 4차원 |
|---|---|---|
| 구성 | J1~J6 + 그리퍼 | x, y, z + 그리퍼 (자세 고정) |
| 장점 | IK 문제 없음 | 차원 절반. 소량 데이터에 유리 |
| 단점 | 관절-시각 대응을 모델이 학습해야 함 | SDK IK 블랙박스, 특이점 근처 불연속 |

**계획서 잠정 권고: EE 4차원.**

### 조사 (오늘 가능)

- [ ] LIBERO 컨트롤러가 OSC 인지 IK 솔버인지 → robosuite 설정 필요.
      `libero` 패키지는 clone 에 없음 (`libero_utils.py:23-24` 가 외부 import)
- [ ] Mirobot 펌웨어가 IK 를 푸는 방식 (`G0 X.. Y.. Z..` → 관절각)
- [ ] 관절 수 7 대 6 — 관절 공간 액션이 호환되나 → 
- [ ] `common/gcode.py` 가 IK 를 신경 쓰지 않는 이유 확인

### 실물 실험 (로봇 필요 — 오늘 불가할 수 있음)

계획서가 지정한 W2 절차:

> 확정 전 **W2 에 직선 궤적을 EE 좌표로 명령하며 관절각 로깅**
> → 튀는 구간 있으면 관절각으로 전환

- [ ] 직선 궤적을 EE 좌표로 명령
- [ ] 관절각 로깅
- [ ] 튀는 구간 유무 → 
- [ ] top-down 자세가 J5 범위(-180°~+40°) 안인지 (`계획서:258`)

### 결정

- **EE 4차원 / 관절각 7차원** → 
- **근거** → 

> 결정하면 `../plan/운영기준.md` §7 에 남긴다.

---

## 4. 덮고 답해보기

문서를 닫고 답이 나오면 이해한 것이다.

1. **롤아웃 하나가 남기는 것은 무엇인가? 우리는 무엇을 남겨야 하나?** → 


2. **우리 시뮬 코드는 지금 어떤 상태인가?** → 


3. **왜 EE 4차원인가? LIBERO 가 왜 근거가 되나?** → 


---

## 5. 다음 미팅에 가져갈 질문

- [ ] 세 항목이 A/B 중 누구 몫인지 (`../meetings/2026-09-07.md` 주석)
- [ ] "시뮬 코드 확인" 이 `replay_with_mujoco.py` 복구를 뜻하는지, 상태 정리인지
- [ ] "수집 규격 선행 조사" 라는 해석이 맞는지
- [ ] 

---

## 관련 문서

- [W2_진행사항.md](W2_진행사항.md) — 관측/액션 구조, 우리 스키마와의 대응
- [../meetings/2026-09-07.md](../meetings/2026-09-07.md) — 원래 의견
- [../plan/UROP_프로젝트_계획.md](../plan/UROP_프로젝트_계획.md) §6 — 수집 규격, 액션 표현 미결
- [../plan/운영기준.md](../plan/운영기준.md) §7 — 결정해야 할 항목
- [../VENDORED.md](../VENDORED.md) — cosmos-policy clone
