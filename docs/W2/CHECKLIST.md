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

## 1. 의견 ① — LIBERO 입출력 규약과 Mirobot 변환

**과제**
Mirobot 에서 얻은 관측을 정책에 넣으려면 **어떤 형식이어야 하는지**를 밝힌다.
그러려면 먼저 LIBERO 가 무엇을 주고받는지(A), 그다음 우리 데이터를 어떻게
바꿔야 하는지(B) 를 알아야 한다.

**산출물**
① Mirobot → LIBERO 변환 명세, ② 그러기 위해 수집 때 남겨야 할 필드 목록.
후자는 계획서 §6(`계획서:312-321`)과 대조한다 — **필드 하나가 빠지면 재수집
외에 복구가 없기 때문**이다.

**대상**: `cosmos-policy/cosmos_policy/experiments/robot/libero/`
전부 clone 안에 있고 실행이 필요 없다.

> 원문: "LIBERO 에서 롤아웃별로 나오는 정보 확인 — 이미지와 롤아웃 샘플이
> 어떻게 관리되고 있는지"

> ※ 실물 운영 시 **LIBERO 도 MuJoCo 도 루프에 없다.** 돌아가는 것은
> Cosmos Policy 다. LIBERO 가 남기는 것은 **규약**뿐이고, 정책이 그 규약으로
> 학습됐으므로 우리도 지켜야 한다.

---

# A. LIBERO 입출력 규약

## A-1. 정책 입력 — 관측

- [x] `prepare_observation()` — `run_libero_eval.py:324`
- [x] `get_libero_image()` / `get_libero_wrist_image()` — `libero_utils.py:45,53`

키는 **3개뿐**이다.

| 키 | 형태 | dtype | 원본 obs 키 |
|---|---|---|---|
| `primary_image` | (256, 256, 3) | uint8 | `agentview_image` — 3인칭 고정 |
| `wrist_image` | (256, 256, 3) | uint8 | `robot0_eye_in_hand_image` — 손목 1인칭 |
| `proprio` | (9,) | float64 | 아래 3개를 `np.concatenate` |

`proprio` 는 시뮬이 주는 값이 아니라 **매 스텝 조립**된다 (`:334`):

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

**전처리를 하지 않는다.** `obs` 에서 꺼내 그대로 반환하고 `flip_images=True` 일 때만
`np.flipud` 를 건다. docstring 의 "preprocesses it" 과 `prepare_observation` 의
`resize_size` 인자는 **둘 다 동작하지 않는다** — 리사이즈 코드를 떼어낸 잔재.

해상도가 둘이다: 시뮬 렌더링 **256**(`env_img_res`, `:246`), 정책 입력 **224**
(`MODEL_IMAGE_SIZES["cosmos"]`, `robot_utils.py:41`). 256→224 축소는 **정책 내부**에서
한다. `:246` 주석이 명시한다 — *"not policy input resolution"*.

→ 이식 시 **원본 크기 uint8 을 그대로 넘기면 된다.**

### 정규화 — min·max 다

- 통계 로드: `load_dataset_stats()` (`cosmos_utils.py:233`), 호출 `:824`
- 적용: `cosmos_utils.py:637-645`(액션 역정규화), `:664-675`(proprio 정규화)
- 스위치: `run_libero_eval.py:936`

```python
# proprio: 원래 값 → [-1, +1]           cosmos_utils.py:670
rescaled = 2 * ((arr - curr_min) / (curr_max - curr_min)) - 1

# 액션: [-1, +1] → 원래 단위 (역방향)    cosmos_utils.py:645
actions = 0.5 * (actions + 1) * (actions_max - actions_min) + actions_min
```

mean·std 도 분위수도 아니다. 키는 `actions_min/max`, `proprio_min/max`.

→ **모델은 [-1, +1] 공간에서만 산다.** 실제 단위 환산은 전적으로
`libero_dataset_statistics.json` 에 의존한다.

## A-2. 정책 출력 — 액션

```python
[Δx, Δy, Δz, Δrx, Δry, Δrz, gripper]     # libero_utils.py:42
```

- **절대 좌표가 아니라 델타**다
- **관절 제어가 아니다.** Panda 는 7관절인데 액션이 6+1 이다. 관절 변환은
  robosuite 컨트롤러가 내부에서 한다
- 그리퍼는 **부호**로 판정 — `common/gcode.py:43` 이 `action[6] < 0` 이면 열기.
  기본 액션 `[0,0,0,0,0,0,-1]` 이 그 예

정책은 액션 외에 **미래 이미지 1~2장**과 **value** 도 내놓는다. 미래 이미지는
`generated_images` 에서 특정 인덱스만 뽑은 것이지(`cosmos_utils.py:758`) 16장이 아니다.
용도는 계획 선택(value 최대, `:578-592`)과 사후 영상뿐 — **실행 중 실제와 비교하는
코드는 없다.**

> Failure Detection 재료가 될 수 있다. 예측 미래와 실제 프레임이 둘 다 저장되므로
> 비교하면 "계획대로 안 가고 있다"를 잡을 수 있다. 단 개수가 달라(청크당 1 대 매 스텝)
> 시간축 정렬이 필요하다.

## A-3. 시간 구조

- [x] `run_episode()` 루프 — `run_libero_eval.py:340-648`

| | 주기 | 근거 |
|---|---|---|
| 이미지 추출·누적 | **매 스텝** | `:408-409` 무조건 실행 |
| 정책 호출 | **16스텝에 한 번** | `:419` 큐가 빌 때만. `num_open_loop_steps=16` (`:216`) |
| 액션 실행 | 매 스텝 | `:598` 큐에서 popleft |

처음 `NUM_STEPS_WAIT = 10` 스텝은 물체 안정화용 더미 액션이고 **누적되지 않는다**
(`:402-405`, `continue`). 실물에는 없는 구간이다.

16스텝 동안은 **open-loop** — 눈을 감고 계획대로 간다. 어긋나도 그 안에서는
보정하지 않고, 다음 청크에서 실제 관측으로 리셋된다. 오차가 청크를 넘어
누적되지는 않지만 **청크 안에서는 최대 16스텝치를 감수**한다.

→ 계획서 §6 이 "제어 주파수 다운샘플링을 학습 시점에 변경 가능하게" 요구한 이유.

## A-4. 무엇이 남는가

저장 코드가 **두 종류**다. 목적이 다르다.

| | `run_libero_eval.py` | `regenerate_libero_dataset.py` |
|---|---|---|
| 언제 | 학습된 **정책을 평가**할 때 | **데이터셋을 만들** 때 |
| 입력 | 정책 | 사람이 수집한 원본 demo |
| 우리와의 관계 | 정책이 생긴 뒤 | **지금 우리가 하려는 일** |

### (a) 평가 롤아웃 — `collected_data`

출력 경로가 둘이다.

| | MP4 영상 | HDF5 데이터 |
|---|---|---|
| 함수 | `save_rollout_video()` (`libero_utils.py:61`) | `_save_episode_data()` (`:750`) |
| 조건 | 항상 | **`data_collection=True` 일 때만** |
| 위치 | `./rollouts/<날짜>/` | `<local_log_dir>/rollout_data/` |
| 용도 | 사람이 눈으로 확인 | 학습 데이터 |

파일명에 성공 여부가 박힌다 — 열지 않고 가를 수 있다.

```
episode_data--suite=<>--<날짜시각>--task=<id>--ep=<n>--success=<T/F>--<note>.hdf5
```

**파일 하나 = 롤아웃 하나.** 한 파일 안에서 T개 스텝이 첫 축으로 쌓인다.

| `collected_data` 키 | shape | 저장 형태 |
|---|---|---|
| `primary_images` | (T, 256, 256, 3) uint8 | dataset |
| `wrist_images` | (T, 256, 256, 3) uint8 | dataset |
| `proprio` | (T, 9) float64 | dataset |
| `actions` | (T, 7) | dataset |
| `success` | bool | **attribute** (`:768`) |
| `task_description` | str | **attribute** (`:770`) |
| `future_primary_images` | (T', ...) | 조건부 (`:628-634`) |
| `future_wrist_images` | (T', ...) | 조건부 (`:636-642`) |

이미지 판정은 키 이름이 아니라 **모양으로** 한다 (`:759`):

```python
is_image = v.ndim == 4 and v.shape[-1] == 3 and v.dtype == np.uint8
```

`jpeg_compress=True` 면 키가 `<이름>_jpeg` 가 되고 shape 이 `(T,)` 가변길이
바이트열로 바뀐다. **손실 압축**(품질 95)이라 원본 픽셀값이 보존되지 않는다.

**성공·실패를 모두 저장한다** — *"captures ALL episodes regardless of
success/failure"*.

### (b) 데이터셋 생성 — 우리가 흉내낼 쪽

- [ ] `regenerate_libero_dataset.py` (21KB) **제대로 읽을 것** — 지금은 grep 수준

`:309-335` 이 남기는 필드 (12개+):

```
obs_grp:  gripper_states, joint_states, ee_states, ee_pos, ee_ori,
          agentview_rgb, eye_in_hand_rgb   (+ _jpeg 압축본)
ep_grp:   actions, states, robot_states, rewards, dones
```

**정책 입력(3개)보다 훨씬 넓다.** 특히 `joint_states`(`obs["robot0_joint_pos"]`,
`:232`)는 **저장하되 정책에는 주지 않는다** — 관절각을 버린 게 아니라 의도적으로
입력에서 뺀 설계다. 의견 ③ 의 근거가 된다.

- `states` / `robot_states` 가 각각 무엇인지 → 

## A-5. metainfo — 저장이 아니라 입력이다

`libero_*_metainfo.json` 은 롤아웃이 **만들어내는** 것이 아니라 **시작할 때 읽는**
기존 데이터셋의 라벨이다.

- `load_initial_states()` (`:308-321`) → `env.set_init_state()` (`:361`)
- 담긴 것: 태스크별 demo 목록, `success` 라벨, `initial_state` 벡터
- 목적: **같은 초기 배치를 재현**해 공정하게 비교

> `success` 가 두 종류다. metainfo 의 것은 **사람이 수집한 demo** 의 성공 여부,
> HDF5 attribute 의 것은 **이번 롤아웃**의 성공 여부다.

---

# B. Mirobot 정보를 어떻게 변환하나

## B-1. 변환 명세

> **어느 값을 정책에 줄 것인가**(Cartesian 이냐 관절각이냐)는 의견 ③ 이다.
> LIBERO 의 proprio 9차원에는 관절각 슬롯이 없으므로, 규약을 지키는 한
> 아래는 선택이 아니라 의무다.

**목표 형식**

```python
observation = {
    "primary_image": (256, 256, 3) uint8 RGB,
    "wrist_image":   (256, 256, 3) uint8 RGB,
    "proprio":       (9,) float64,
}
# + task_description (str), + min/max 정규화 → [-1, +1]
```

### 이미지

| 단계 | 지금 (`robot/camera_bridge.py`) | 필요 | 성격 |
|---|---|---|---|
| 1 | JPEG 바이트 (`:82`) | 생 numpy 배열 | `:78`~`:82` 사이에 갈래 내기 |
| 2 | 1280×720 (16:9, `:201-202`) | 정사각형 | **결정 필요** |
| 3 | — | 256×256 | `cv2.resize` |
| 4 | **BGR** | **RGB** | `cv2.cvtColor(..., COLOR_BGR2RGB)` |
| 5 | — | 상하 반전 | `flip_images=True` 로 학습됨 |
| dtype | uint8 | uint8 | 그대로 |

**손목 카메라가 없다.** `camera_bridge.py` 는 카메라 하나만 연다.

4번은 특히 조심할 것 — 바꾸지 않으면 **빨간 큐브가 파랗게 들어가는데 에러가 나지
않는다.** 태스크가 `"pick up the red cube"` 인 만큼 치명적이다.

5번 근거: `PolicyEvalConfig.flip_images = True` (`:201`). 함수 시그니처의
`False`(`:324`)는 쓰이지 않는다 — 호출부가 `cfg.flip_images` 를 넘긴다(`:408`).

### proprio 9차원

Mirobot 이 주는 것 (`serial_bridge.py:99-134` `query_robot_status()`):

| 키 | 내용 | 출처 |
|---|---|---|
| `mpos` | Cartesian XYZ (mm) | `Cartesian coordinate(XYZ RxRyRz)` (`:180`) |
| `joint` | 관절각 **7개** | `Angle(ABCDXYZ)` (`:184`) |
| `gripper` | — | **파싱 코드 없음** |

| idx | LIBERO | Mirobot | 상태 |
|---|---|---|---|
| 0,1 | `gripper_qpos` 2개 (대칭) | `status["gripper"]` | 값이 없음 |
| 2,3,4 | `eef_pos` xyz **meter** | `mpos[0:3]` **mm** | `/1000` + 원점 정렬 |
| 5~8 | `eef_quat` (w,x,y,z) | `RxRyRz` **오일러각** | 파싱에서 버려짐 |

세 줄 다 그대로는 안 된다.

- **그리퍼** — 값이 없을 뿐 아니라 **위치 개념 자체가 없을 가능성이 크다.**
  B-2 참조
- **위치** — mm → m + **원점 정렬**. LIBERO `z=0.702` 대 우리 demo_0 `z=0.177`.
  `common/gcode.py` 의 `+54mm` 오프셋과 같은 종류
- **자세** — 오일러 → 쿼터니언 변환식이 필요한데, `:180` 이 `RxRyRz` 를 버리고
  XYZ 3개만 취한다. **파싱부터 복구**해야 한다

### 정규화

`libero_dataset_statistics.json` 을 그대로 쓰면 안 된다. **우리 데이터의 min/max 로
새로 만들어야 한다.** LIBERO 통계를 쓰면 값이 범위 밖으로 나가거나 뭉친다.

### 일의 성격

| | 항목 |
|---|---|
| 기계적 | mm→m, BGR→RGB, 리사이즈, 오일러→쿼터니언 |
| **결정 필요** | 종횡비 처리, 그리퍼 2차원 규약, 좌표계 원점 |
| 코드 추가 | 손목 카메라, 그리퍼 파싱, `RxRyRz` 파싱 복구, 생 배열 경로 |

## B-2. 그리퍼 — 위치 제어가 아니다

**관찰**: `robot/inverse_kinematics.py` 로 조작할 때 **키를 누르고 있으면 점점 더
열리고 닫힌다.** 그런데 코드는 `M4 S40` / `M4 S60` 두 값만 보낸다(`:95-101`).
`S` 를 증감시키는 변수가 없다.

**해석**: 절대 위치 명령이라면 같은 값을 반복해도 이미 도달한 곳이라 움직이지
않아야 한다. 계속 움직인다는 것은 `S` 가 **위치가 아니라 방향·속도**라는 뜻이다.
GRBL 에서 `M4` 는 스핀들 역회전, `S` 는 회전 속도다. Mirobot 이 그 출력을 그리퍼에
연결했다면 `S50` 근처가 중립이고 `S40`/`S60` 이 양쪽 방향이 된다.

> 추정이다. 맨 아래 "실물에서 확인할 것" 으로 검증한다.

| | 위치 제어 (LIBERO/Panda) | Mirobot (관찰된 동작) |
|---|---|---|
| 명령 의미 | "이 개도로 가라" (절대) | "이 방향으로 돌아라" |
| 개도를 정하는 것 | 명령값 | **명령 지속 시간** |
| 중간 개도 지정 | 가능 | 시간으로만 |
| 현재 개도 추적 | 명령값 = 현재값 | 시간 적분 — **매우 부정확** |
| 정지 조건 | 목표 도달 | 명령 중단 또는 **기계적 스톱** |

**따라오는 것 셋**

1. **proprio 그리퍼 2차원을 제대로 채울 방법이 없다.** 명령값으로 대신해도
   `S40` 은 "여는 중"이지 개도가 아니다. 피드백도 없다.
   → 실질적으로 **열림/닫힘 이진값으로 근사**할 수밖에 없다.
2. **그런데 우리 데모도 이미 이진이다.** `common/demos.py` 확인 결과 액션 그리퍼
   성분의 고유값은 `[-1, +1]` 둘뿐이고, 상태 qpos 도 2값(`0.0` / `0.012`)뿐이다.
   `common/gcode.py:40` 의 부호 이진화가 **정보 손실이 아니게 된다** — 우연히
   맞아떨어진다.
3. **"얼마나 오래 보낼 것인가"가 새 파라미터가 된다.** 지금 코드에는 그 개념이
   없다. `robot/replay_serial.py:99-102` 는 명령이 **바뀔 때 한 번만** 보낸다:

```python
grip_cmd = gripper_gcode(action, args.open_cmd, args.close_cmd)
if grip_cmd != last_gripper:
    send_gcode(ser, grip_cmd, dry_run)   # ← 한 번뿐
    last_gripper = grip_cmd
```

수동 조작에서는 사람이 원하는 만큼 키를 누르고 있어 문제가 드러나지 않았지만,
자동 재생에서는 **충분히 닫히지 않을 수 있다.**

## B-3. 타임스탬프와 동기화

시뮬은 스텝이 곧 시간이라 필요가 없다. 실물은 카메라와 로봇이 **비동기**로 돌아
타임스탬프 없이는 사후 정렬이 불가능하다.

**현재 상태 — 반쪽이다**

| | 타임스탬프 | 근거 |
|---|---|---|
| 카메라 | 있음 — `latest_time = time.time()` | `camera_bridge.py:90`, 노출은 `:138` |
| 로봇 상태 | **없음** | `query_robot_status()` dict 에 시각 필드 없음 |

### 어디서 찍나 — 소스에서

| | 위치 | 상태 |
|---|---|---|
| 카메라 | `cap.read()` 직후 | 이미 있음 (`camera_bridge.py:90`) |
| 로봇 | 시리얼 응답 수신 직후 (`serial_bridge.py:118` 부근) | **추가 필요** |

서버(`bridge_client`)에서 찍으면 **네트워크 왕복 지연이 섞인다.** SSH 역터널을
쓰면 특히 그렇다. 반드시 노트북 쪽에서 찍는다.

둘 다 같은 노트북 프로세스이므로 **시계가 같다.** 서버가 개입하지 않는 한
시계 동기 문제는 없다.

### 어떤 시계 — 둘 다 남긴다

| | 용도 | 주의 |
|---|---|---|
| `time.time()` | 절대 시각. 로그와 대조 | NTP 보정으로 **뒤로 갈 수 있다** |
| `perf_counter()` / `monotonic()` | 간격 측정. 단조 증가 | 프로세스 기준이라 **프로세스 간 비교 불가** |

`serial_bridge.py` 는 내부 타임아웃에 이미 `time.monotonic()` 을 쓴다(`:55,80`).

### 수집 주파수의 상한

`STATUS_READ_TIMEOUT_S = 1.0` (`serial_bridge.py:42`) 은 **타임아웃이지 실제
지연이 아니다.** 실제 왕복 시간이 수집 주파수의 상한을 정한다. 로봇 상태를
초당 5번밖에 못 읽으면 30fps 카메라가 있어도 5Hz 데이터셋이 된다.

계획서 §6 의 "제어 주파수 다운샘플링" 논의는 이 숫자가 나온 뒤에야 가능하다.

### 더 근본적인 것 — 로봇은 안 보는 사이에도 움직인다

`G0 X.. Y.. Z..` 를 보내면 도달까지 시간이 걸린다. 그 사이에 상태를 조회하면
**이동 중인 위치**가 나온다. "시각 t 의 상태"가 목표 도달 상태가 아닐 수 있다.

계획서의 **명령값/실측값 분리** 요구가 여기와 맞물린다. 명령 시각과 실측 시각을
따로 남겨야 "명령 후 얼마 만에 도달했는가"를 알 수 있고, 그것이 실패 진단의
재료가 된다.

## B-4. 그래서 무엇을 남겨야 하나

> 아래는 **초안**이다. 근거는 A 절에 있으니 확인하고 고칠 것.
> `regenerate_libero_dataset.py` 를 제대로 읽으면(A-4b) 더 정확해진다.

기준 둘 — ① 위 변환을 할 수 있어야 하고, ② **아직 정해지지 않은 것**
(액션 표현 §7, 크롭 방식, 제어 주파수)을 나중에 바꿀 수 있어야 한다.
그래서 정책 입력보다 넓게 남긴다.

| 필드 | 형태 | LIBERO 대응 | 왜 남기나 |
|---|---|---|---|
| `primary_images` | (T, H, W, 3) uint8 | `primary_images` | **원본 해상도로** |
| `wrist_images` | (T, H, W, 3) uint8 | `wrist_images` | **원본 해상도로** |
| `ee_pose` | (T, 6) | `ee_states` | EE 4차원 안(§7)의 재료 |
| `joint_states` | (T, 6) | `joint_states` | **관절각 안의 재료.** §7 미결이라 둘 다 |
| `joint_commands` | (T, 6) | 없음 | 명령값. 실측과의 차이가 실패 신호 |
| `gripper_state` | (T, ?) | `gripper_states` | proprio 조립에 필요 |
| `actions` | (T, 7) | `actions` | 학습 타깃 |
| `timestamps` | 스트림별 | 없음 | 실물은 카메라와 로봇이 비동기 |
| `task_description` | str | attribute | 자연어 지시문 |
| `success` | bool | attribute | 에피소드 결과 |
| 에피소드 메타 | 배치, 대상 색 | `initial_state` (시뮬 전용) | **직접 기록** |

`proprio` 9차원은 **저장하지 않아도 된다.** `gripper_state` + `ee_pose` 에서
조립되는 파생값이라 학습 시점에 만들 수 있다 (LIBERO 도 `:334` 에서 매 스텝 조립).

### 계획서 §6 대조 — 네 개가 빠진다

| 계획서 §6 요구 | LIBERO | 조치 |
|---|---|---|
| 관절각 6개 | `joint_states` | 그대로 |
| — **명령값/실측값 분리** | 없음 | **우리가 추가** |
| EE pose 6자유도 | `ee_states` | 그대로 |
| 그리퍼 상태 | `gripper_states` | 기구가 달라 표현 결정 필요 |
| **타임스탬프** (스트림별) | 없음 | **우리가 추가** |
| 카메라 **원본 해상도** | 256 렌더본만 | **원본 별도 보관** |
| 태스크 지시문 | attribute | 그대로 |
| 에피소드 메타 | 성공만 | 배치·색 **직접 기록** |

1. **타임스탬프** — 시뮬은 스텝이 곧 시간이다. 실물은 카메라와 로봇 상태가 같은
   순간의 것이라는 보장이 없어, 없으면 사후 정렬이 불가능하다
2. **명령/실측 분리** — 시뮬은 명령대로 움직인다. 실물은 다르고 **그 차이가 실패의
   직접적 신호**다
3. **원본 해상도** — 16:9 → 1:1 변환 방식을 되돌릴 수 없게 된다
4. **물체 배치·대상 색** — `initial_state` 는 시뮬 상태 벡터라 실물에 대응물이 없다

**넷 다 "시뮬에는 필요 없지만 실물에는 필요한 것"** 이다. 형식 변환만으로는 부족하다는
근거이고, `계획서:312` 의 경고가 가리키는 것이 이 넷이다.

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
- [x] **Mirobot 은 두 방식을 모두 지원한다** — 아래
- [x] `serial_bridge.py` 가 관절각을 이미 읽고 있다 — 아래
- [ ] 관절 수 7 대 6 — 관절 공간 액션이 호환되나 → 
- [ ] `common/gcode.py` 가 IK 를 신경 쓰지 않는 이유 확인

#### Mirobot 은 두 모드를 다 쓴다 — 구분은 모드 설정이다

G-code 문자열은 **똑같고** 모드에 따라 `X Y Z` 의 의미가 바뀐다.

| | `robot/forward_kinematics.py` | `robot/inverse_kinematics.py` |
|---|---|---|
| 모드 | `G91` (상대) | `M20` + `G90` (절대 Cartesian) |
| 초기 명령 | `G0 X0 Y0 Z0 A0 B0 C0` (`:40`) | `G0 X198.67 Y0 Z230.72 ...` (`:41`) |
| `X,Y,Z` 의 뜻 | **관절각 J1,J2,J3 (도)** | **좌표 x,y,z (mm)** |
| `A,B,C` 의 뜻 | 관절각 J4,J5,J6 | 자세 각도 |
| IK 를 푸는 주체 | 없음 — 관절을 직접 지정 | **Mirobot 펌웨어** |

`forward_kinematics.py:74` 가 `G0 X{current_j1} ...` 로 관절각을 `X` 에 넣는다.
같은 `G0 X..` 인데 `M20`/`M21` 스위치에 따라 mm 이기도 하고 도(degree)이기도 하다.

**즉 선택지가 실제로 둘 다 열려 있다.** 펌웨어가 IK 를 풀어 주므로 Cartesian 으로
가도 되고, 관절각을 직접 줘도 된다. 하드웨어가 한쪽을 강제하지 않는다.

#### 관절각 데이터는 이미 확보된다

`serial_bridge.py:184` 가 `Angle(ABCDXYZ)` 에서 **관절각 7개**를 파싱해
`status["joint"]` 에 담는다. 관절 공간으로 결정되더라도 **데이터 수집은 이미 된다.**

반면 Cartesian 쪽은 `:180` 이 `RxRyRz` 를 버리고 XYZ 3개만 취한다 —
**자세 정보가 유실된다.** 이건 의견 ① 의 proprio 변환 문제이기도 하다.

> 역설적으로 **지금 코드는 관절각 쪽이 더 온전하다.** EE 자세를 쓰려면
> 파싱을 먼저 고쳐야 한다. 이것이 §7 결정에 영향을 주는지 검토할 것 → 

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

## 4. 추후 고려사항

의견 ①②③ 에서 나온 미결 항목을 한곳에 모은다. 정해지면 해당 절과
`../plan/운영기준.md` §7 에 반영한다.

### 결정해야 할 것

**관측 변환 (의견 ①)**

- 그리퍼를 이진값으로 근사할 것인가, 다른 방법이 있는가 →
- 그리퍼 명령을 **얼마나 오래 유지**할 것인가 (반복 횟수 / 지속 시간) →
- 좌표계 원점 정렬 — 오프셋을 어떻게 구할 것인가 →
- 종횡비 16:9 → 1:1 — 크롭 / 왜곡 / 레터박스 →
- 쿼터니언 순서 `wxyz` 확인 (라이브러리에 따라 `xyzw`) →
- 손목 카메라를 어떻게 붙일 것인가 (하드웨어 + `camera_bridge.py` 확장) →
- 타임스탬프 정렬 방식 — 최근접 이웃 / 보간 →
- 목표 수집 주파수 →

**액션 표현 (의견 ③)**

- EE 4차원 / 관절각 7차원 →
- 근거 →

> 계획서 잠정 권고는 EE 4차원(`계획서:325`). 결정하면 `운영기준.md` §7 에 남긴다.

**시뮬 코드 (의견 ②)**

- `replay_with_mujoco.py` 복구가 과제인가, 상태 정리가 과제인가 → (미팅 확인)

### 실물에서 확인할 것

로봇을 연결해야 답이 나오는 항목. 여기 답에 따라 위 결정이 달라진다.

**그리퍼**

- [ ] `M4 S50` 같은 **중간값**이 중간 개도를 만드는가, 방향만 바뀌는가
- [ ] 명령을 한 번만 보내면 어디까지 움직이는가 (기계적 스톱까지? 조금만?)
- [ ] 데모 재생(`replay_serial.py`) 시 **파지가 실제로 되는가**
      → 되면 B-2 의 추정이 틀렸거나 한 번 명령으로 충분한 구조
- [ ] `?` 응답 **원문**에 그리퍼 관련 필드가 있는가
      → 지금 브리지는 `Cartesian coordinate` 와 `Angle(ABCDXYZ)` 만 파싱한다.
        응답에 더 있는데 안 읽고 있을 수 있다

**타이밍**

- [ ] `__STATUS__` 왕복 시간 실측 (100회 반복) → **수집 주파수 상한**
- [ ] 로봇이 **이동 중에도** 실시간 위치를 보고하는가, 정지 상태만 보고하는가

**좌표**

- [ ] `Cartesian coordinate(XYZ RxRyRz)` 응답에 실제로 6개 값이 오는가
      → 오면 `serial_bridge.py:180` 파싱만 고치면 EE 자세 확보
- [ ] 계획서 지정 W2 절차 — 직선 궤적을 EE 좌표로 명령하며 관절각 로깅.
      튀는 구간이 있으면 관절각으로 전환 (`계획서:327`)
- [ ] top-down 자세가 J5 범위(-180°~+40°) 안인지 (`계획서:258`)

---

## 5. 덮고 답해보기

문서를 닫고 답이 나오면 이해한 것이다.

1. **롤아웃 하나가 남기는 것은 무엇인가? 우리는 무엇을 남겨야 하나?** → 


2. **우리 시뮬 코드는 지금 어떤 상태인가?** → 


3. **왜 EE 4차원인가? LIBERO 가 왜 근거가 되나?** → 


---

## 6. 다음 미팅에 가져갈 질문

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
