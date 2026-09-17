# W3 — 작업 목록

> **절차** · 확인 2026-09-17 · 기준 `cosmos-policy@18a2acc`, 9/13·9/17 실물 측정
> 9/14 미팅 의견의 작업 목록. `→` 뒤 빈칸은 **미리 채우지 않는다** — 그 부분을 읽을 때 요청하면 그때 채운다.

의견 원문과 결정은 [../meetings/2026-09-14.md](../meetings/2026-09-14.md) 에 있다. 여기는 **작업**만 둔다.

## 0. 이번 주 목표

**Mirobot 과 LIBERO(Panda) 사이에서 proprio 를 서로 바꿔 넣어도 같은 행동이 나오는지 보여준다.**

다음 미팅에서 보여줄 것:

| 방향 | 순서 |
|---|---|
| Mirobot → LIBERO | Mirobot 실물 동작 → 같은 궤적을 따라간 Panda 영상 |
| LIBERO → Mirobot | LIBERO demo 의 Panda 영상 → 변환한 궤적으로 Mirobot 실물 동작 |

**조건**

- **시간은 보지 않는다** — 속도·주기는 무시하고 정지점(waypoint)을 순서대로 지나가면 된다
- **판단은 눈으로** — Mirobot 에 카메라가 아직 없다
- **궤적에 자세 변화가 들어가야 한다** — top-down 만으로는 쿼터니언이 상수라 변환이 맞는지 드러나지 않는다

**범위 밖** — timestep(동기화·수집 주파수·청크 지연), 그리퍼 proprio 방식, 네트워크 왕복, 카메라, 학습

## 1. 순서

```
① OASYS 에 LIBERO 환경 ─────────┐   가장 먼저. 오래 걸릴 수 있다
② 오일러각 → 쿼터니언 ──────────┤   ①과 서로 기다리지 않으므로 같이 진행
                                 ▼
③ LIBERO 시뮬에서 Panda 움직여 보기 — 축·순서·프레임 확인 → ② 완성
                                 ▼
④ 두 방향 재생   5-1 Mirobot → LIBERO   5-2 LIBERO → Mirobot
                                 ▼
⑤ 미팅 준비
```

**규칙** — 실행은 장비가 있는 곳에서 한다. 코드와 문서는 **git** 으로 옮긴다.
`*.mp4` 와 `data/` 는 gitignore 라 **scp** 로 옮긴다.

---

## 2. ① OASYS 에 LIBERO 시뮬 환경

**산출물** 서버에서 LIBERO 환경을 만들고 dummy action 으로 몇 스텝 돌린 MP4 한 개.
**어디서** **OASYS** — mujoco·LIBERO·GPU 렌더링이 서버에만 있다.

**알고 있는 것**

| | | 근거 |
|---|---|---|
| 공식 방식 | Docker 컨테이너 안에서 `uv sync --extra cu128 --group libero --python 3.10` | `cosmos-policy/LIBERO.md:25`, `cosmos-policy/SETUP.md` |
| LIBERO·robosuite | 위 명령에 안 들어 있다. `pip install -e LIBERO`, `pip install -e robosuite` 로 따로 | `cosmos-policy/pyproject_simplified.toml:75-77` |
| 버전 | robosuite 1.4.1, mujoco 3.3.2, bddl | `../VENDORED.md:45` |
| 화면 없는 렌더링 | Docker 이미지에 `libegl1-mesa-dev` 가 들어 있다 → EGL | `cosmos-policy/docker/Dockerfile:32` |
| 지금 서버 | conda `urop` 에는 시뮬 패키지가 없다. Cosmos Policy 체크포인트는 HF 캐시에 있다 | `../SETUP_LINUX.md:108-112`, `../MODELS.md:78` |

**절차**

- [x] 서버에 무엇이 있는지 본다
  ```bash
  nvidia-smi                                   # GPU
  docker --version && docker images | grep -i cosmos   # Docker 사용 가능 여부, 이미지 존재
  ls <cosmos-policy clone 경로>/.venv          # uv 환경이 이미 있나
  ```
  → (9/15) GPU **RTX 4090 × 4** (24GB). **Docker 없음** (podman·apptainer 도 없고 docker 그룹 권한도 없다).
  uv 0.12.5 있음. **`~/UROP/cosmos-policy/.venv` 가 이미 있다** (9/7 생성, 13GB, Python 3.10.21).
  서버에 EGL 라이브러리(`libEGL_nvidia`)가 있다. LIBERO demo 데이터(hdf5)는 서버에 없다
- [x] 설치 경로 — Docker(공식) / Docker 없이 uv 직접 → **uv 직접 — 9/7 에 만든 `.venv` 를 그대로 쓴다.**
  conda 는 끄고 켠다. **`uv run`·`uv sync` 는 쓰지 않는다** — lock 에 맞춰 다시 동기화하므로
  `--extra cu128 --group libero` 를 빠뜨리면 libero 패키지가 지워질 수 있다
  ```bash
  conda deactivate                          # (base)/(urop) 이 없어질 때까지
  cd ~/UROP && source cosmos-policy/.venv/bin/activate   # 프롬프트에 (cosmos-policy)
  ```
- [x] LIBERO·robosuite 설치 → **새로 설치하지 않았다 — 이미 들어 있다.** libero 0.1.1 (pypi), **robosuite 1.4.0**, mujoco 3.3.2,
  bddl 1.0.1, torch 2.7.0+cu128, scipy 1.15.3. robosuite 는 위 표의 1.4.1 이 아니라 `uv.lock` 대로 **1.4.0** — ③ 액션 크기는 1.4.0 기준
- [x] import 확인 (`MUJOCO_GL=egl` 은 mujoco 화면 없는 렌더링의 일반적인 설정)
  ```bash
  MUJOCO_GL=egl python -c "from libero.libero.envs import OffScreenRenderEnv; print('ok')"
  ```
  → **ok** (약 20초). `mujoco.GLContext` 생성도 된다. 끝에 `c.free()` 를 안 부르면 종료 때
  `Exception ignored in GLContext.__del__ ... EGLError` 가 찍히는데 해제 순서 문제일 뿐 결과와 무관
- [x] 환경 하나 만들고 dummy action 20스텝 → MP4
  - 환경 생성 `get_libero_env()` (`libero_utils.py:30`), dummy action `[0,0,0,0,0,0,-1]` (`:42`)
  - 영상 저장 `save_rollout_video()` (`:61`) — `./rollouts/<날짜>/` 에 30fps
  - **렌더 이미지는 상하가 뒤집혀 나온다** — `np.flipud` 후 저장
    (`cosmos-policy/README.md:57`, `regenerate_libero_dataset.py:242`)

  → **`rollouts/2026_09_15/11_52_14--dummy--libero_10_0--20steps.mp4`** — 256×256, 21프레임(초기 1 + 20), 0.7초.
  `flipud` 후 똑바로 선다. 스크립트 `tools/libero_dummy_mp4.py` (`libero_utils` 는 torch·wandb 를 끌고 와서 쓰지 않고 같은 절차를 옮겼다)
  ```bash
  cd ~/UROP && python -m tools.libero_dummy_mp4        # --suite --task --steps --res --out
  ```
  - 태스크 `libero_10[0]` "put both the alphabet soup and the tomato sauce in the basket"
  - 첫 관측 `eef_pos [-0.0375, -0.0054, 0.713]`, `eef_quat [0.9998, -0.0122, 0.0146, -0.0012]`.
    dummy 20스텝 뒤 z 가 약 1cm 내려간다
  - 영상은 `agentview` 만 저장. 관측에는 `robot0_eye_in_hand_image` (256×256) 도 있다

**막힌 것 / 걸린 시간** → 설치 0 (이미 있었다). 확인부터 직접 실행한 MP4 까지 약 30분 (11:20 → 11:52).
- **에셋 자동 다운로드** — pypi libero 는 `~/.libero/config.yaml` 의 `assets` 를 보지 않고 패키지 안 `assets/` 만 찾는다.
  없으면 HF `jadechoghari/libero-assets` 에서 **408MB 를 `~/.cache/libero/assets` 로 받는다** (`libero/libero/__init__.py:68-97`).
  첫 테스트 실행에서 승인 없이 받아졌다. 내용은 서버의 openpi 복사본(`~/LIBERO/openpi/third_party/libero`, 공식 LIBERO)과 같다.
  이후 실행은 `Local assets not found. Downloading...` 을 찍지만 바로 `Assets already downloaded` 로 넘어간다
- `python -m tools.…` 는 `~/UROP` 에서 실행해야 한다 (`cosmos-policy/` 안에서는 `No module named 'tools'`)

---

## 3. ② 오일러각 → 쿼터니언

**산출물** Mirobot `RxRyRz` ↔ LIBERO `eef_quat` 변환 함수와 확인용 테스트.
**어디서** **아무 데나** — 장비가 필요 없는 순수 코드. scipy 는 서버 `.venv` 에만 있다 (테스트 대조용).

표현·규약·근거는 [ROTATION.md](ROTATION.md) 에 있다 — 회전 세 가지 표현, 파이프라인 자리별 대응,
바꿔야 할 네 층(표현·단위·저장 순서·기준 프레임). 여기는 **작업**만 둔다.

**절차**

- [x] 변환 코드 위치 (`common/` 에 두면 노트북·서버 양쪽에서 쓴다) → **`common/rotation.py`** (9/16). 세 기계 모두 import 된다
- [x] 라이브러리 — scipy 는 저장소에도 서버 `urop` env 에도 없다. scipy 추가 / numpy 로 직접
  - scipy 라면 `Rotation.from_euler("xyz", ..., degrees=True)` — **소문자가 extrinsic**. `as_quat()` 은 `xyzw`
  → **표준 라이브러리만.** numpy 도 안 쓴다 — `requirements/robot.txt` 에 numpy 가 없고(opencv 를 통해 딸려올 뿐),
  숫자 3~4개라 이득도 없다. scipy 는 **테스트 대조용**으로만 (T12, 서버 `.venv`)
- [x] 프레임 회전을 뺀 1·3·4 단계 먼저 작성 → 함수 12개. 목록은 [ROTATION.md](ROTATION.md) 8절
- [x] 테스트 — 답을 이미 아는 경우로
  - `(0,0,0)` → 항등
  - 9/13 `euler` 측정값 재현 (`../W2/CHECKLIST.md` 4절 "RxRyRz 의 오일러 규약")
  - 왕복: 오일러 → 쿼터니언 → 오일러 가 원래 값
  - 부호: 180° 근처에서 조금씩 도는 궤적에서 부호가 튀지 않는지

  → **`tests/test_rotation.py` 12개 통과** (`python -m tests.test_rotation`). 설계 T1~T13 은 그 파일 주석에 있다.
  규약을 잡는 것은 T3(extrinsic·intrinsic 44.90° 차이)·T4(9/13 실측 재현)·T6(순서)·T12(scipy 500개 `1e-9` 일치)다.
  왕복(T5)만으로는 못 잡는다 — 양방향이 같은 규약으로 틀리면 통과한다
- [x] ③ 결과로 프레임 회전 추가 → **`mirobot_to_libero_quat` / `libero_to_mirobot_quat`, `FRAME_F` = x축 180° (9/17).**
  T13 추가 — 홈, 왕복, LIBERO 실측 자세가 Mirobot `Ry +3.28` 로 읽히는지, 월드 축 +10° 가 세 축 모두 부호 그대로 옮겨지는지. 13개 통과

---

## 4. ③ LIBERO 시뮬에서 Panda 움직여 보기

**산출물** LIBERO 좌표계 확인 표. ②의 프레임 회전과 ④의 추종 루프가 여기에 달려 있다.
**어디서** **OASYS** — 시뮬 실행. 스크립트도 여기서 쓰고 커밋한다.
**기록** 측정 결과는 [LIBERO_AXES.md](LIBERO_AXES.md) 에 모은다. 여기는 결과 한 줄만.

**알고 있는 것**

| | | 근거 |
|---|---|---|
| 관측 | `robot0_eef_pos`(m), `robot0_eef_quat`, `robot0_joint_pos`, `agentview_image` | `run_libero_eval.py:334`, `regenerate_libero_dataset.py:223-243` |
| 액션 | `[Δx, Δy, Δz, Δrx, Δry, Δrz, gripper]` 델타. 컨트롤러는 **OSC_POSE 확정**, 회전은 axis-angle | `env_wrapper.py:17,47`, `osc.py:250` (9/16) |
| 그리퍼 | `-1` 이 열림 | `libero_utils.py:42` |

**절차** — 시험마다 환경을 리셋한다

- [x] 첫 관측의 `robot0_eef_quat` — top-down 이면 `xyzw` 기준 `[±1, 0, 0, 0]` 근처인가
  → **그렇다 (9/17).** 세 관측 모두 x축 약 180°, 그리퍼가 아래를 본다. 장면마다 1~3° 기울어 있다 — [LIBERO_AXES.md](LIBERO_AXES.md) 1절
- [x] 위치 축 — 한 성분만 `+` 로 몇 스텝

  | 액션 | `eef_pos` 에서 커진 축 | agentview 영상에서 방향 |
  |---|---|---|
  | `Δx +` | x (+115mm / 20스텝) | 카메라 쪽으로 다가옴 — 로봇 **앞** |
  | `Δy +` | y (+125mm) | 화면 오른쪽 — 로봇 기준 **왼쪽** (agentview 는 로봇을 마주 봐서 좌우가 바뀐다) |
  | `Δz +` | z (+123mm) | 화면 위 — **위** |

  → **액션 축 = 월드 축, 부호도 같다 (9/17).** 곁가지 10% 이하, 자세 변화 0.24° 이하 — [LIBERO_AXES.md](LIBERO_AXES.md) 2절

- [x] 회전 축 — 한 성분만 `+` 로 몇 스텝

  | 액션 | `eef_quat` 에서 변한 성분 | 그리퍼가 기우는 방향 |
  |---|---|---|
  | `Δrx +` | 월드 x축 둘레 +27.5° (0.2 × 20스텝) | 로봇 기준 **왼쪽**(`+y`)을 향해 기움 — frontview 에서 반시계 |
  | `Δry +` | 월드 y축 둘레 +24.2° | **뒤**(`−x`, 베이스 쪽)를 향해 기움 — sideview 에서 반시계 |
  | `Δrz +` | 월드 z축 둘레 +25.3° | 수평 유지, 위에서 보아 **반시계** — birdview |

  → **회전 3칸 = 월드 축 둘레 오른손 회전 (9/17, 영상 확인).** 손끝(파지점)은 제자리이고 그 위의 손이 돈다.
  실제 회전은 목표 오프셋의 23~25% — [LIBERO_AXES.md](LIBERO_AXES.md) 3절

- [x] 액션 크기 — `1.0` 한 스텝이 몇 m·몇 rad 인가 (robosuite OSC 기본값은 0.05m·0.5rad 로 알려져 있으나 **미확인**)
  → **확인 (9/16, 서버 소스).** LIBERO 는 robosuite 기본 `OSC_POSE` 를 그대로 쓴다 (`env_wrapper.py:17,47`).
  `controllers/config/osc_pose.json` 의 `output_max = [0.05, 0.05, 0.05, 0.5, 0.5, 0.5]`, 입력은 `[-1, 1]` 로 잘린다
  → **액션 1.0 = 0.05m / 0.5rad (28.6°)**. `"control_delta": true` 라 현재 자세 기준 **변화량**이다.
  회전 3개는 **axis-angle** 로 읽는다 (`osc.py:250`).
  **실측 (9/17)** — 이 값은 한 스텝의 **목표 오프셋**이다. 실제 이동은 그 **약 26%** (액션 0.5 에서 스텝당 6.4~6.7mm) — [LIBERO_AXES.md](LIBERO_AXES.md) 2절
- [x] Mirobot 축과 대응 — Mirobot 은 홈에서 앞이 X+, J1+ 방향이 Y+ (`../W2/CHECKLIST.md` 4절 "관절 순서")

  | Mirobot | LIBERO |
  |---|---|
  | X | x (부호 같음) — 앞 |
  | Y | y (부호 같음) — 로봇 기준 왼쪽. Mirobot 쪽은 9/17 실물에서 눈으로 확인 (8절) |
  | Z | z (부호 같음) — 위 |

  → **두 월드 좌표계는 평행이동만 다르다 (9/17).** 프레임 회전 후보 중 왼쪽 곱(pre)은 탈락 쪽 — [LIBERO_AXES.md](LIBERO_AXES.md) 4절

- [x] **프레임 회전 결정** → ②에 반영
  → **확정 (9/17): 오른쪽 곱(post), `F = x축 180°`.** 회전 세 축 모두 Mirobot 9/13 기록과 부호가 맞고, pre 는 y·z 에서 뒤집힌다.
  실물 2건도 이 결론 쪽이다 — Mirobot `Y+` 는 왼쪽, 그리퍼 조는 홈에서 좌우(`Y`)로 벌어져 Panda 와 같다 → 공구 축 90° 추가 없음 (8절).
  근거는 [LIBERO_AXES.md](LIBERO_AXES.md) 4절. ② 코드 반영은 3절 마지막 항목
- [x] LIBERO eef 위치의 기준점 — 그리퍼 끝인가 플랜지인가. Mirobot 은 플랜지라 자세를 바꾸면 위치 차이가 생긴다
  → **위치와 자세의 기준이 서로 다르다 (9/16, 서버 소스).**
  - `eef_pos` = `grip_site` = **손가락 사이 파지점** (`single_arm.py:213,305`). 이 site 는 손(플랜지) 프레임에서 **z + 0.097m** (`panda_gripper.xml:20-21`)
  - `eef_quat` = `right_hand` **바디의 자세** (`single_arm.py:309`) = 플랜지 프레임
  - Mirobot 은 위치·자세 **둘 다 플랜지**다. 그래서 자세를 기울이면 파지점이 플랜지 둘레로 원호를 그린다.
    반지름은 Mirobot 의 플랜지→파지점 길이이고 **미측정**이다 (8절). 9.7cm 는 Panda 값이다
    → 5-1 위치 변환에서 **오프셋 보정이 필요**하다 (보정 없이 맞추면 자세를 바꿀 때마다 위치가 어긋난다)

---

## 5. ④ 두 방향 재생

**어디서** 실물은 **로봇 노트북**, 시뮬은 **OASYS**. 기기 사이를 오가는 것은 waypoint 목록(작다)과 MP4(scp).

**공통** — 시간을 보지 않으므로 **waypoint 단위**로 재생한다. 한 waypoint 에 도달(정지)한 것을 확인하고 다음으로 간다.

### 5-1. Mirobot → LIBERO

**어디서** Mirobot 실물 = 로봇 노트북, Panda 추종·영상 = OASYS.

```
waypoint (Mirobot mm·°) ──▶ Mirobot 실물   G0 X Y Z A B C
        │
        └── 변환 ──▶ LIBERO (m·xyzw) ──▶ Panda 추종 ──▶ MP4
```

- [ ] **시험 궤적** — 홈 근처에서 한 축씩 크게. 작은 각도부터 늘린다

  | # | 동작 | Mirobot waypoint (X Y Z Rx Ry Rz) |
  |---|---|---|
  | 1 | 홈 | `198.67 0 230.72 0 0 0` (9/13) |
  | 2 | Rx 만 | |
  | 3 | Ry 만 | |
  | 4 | Rz 만 | |
  | 5 | 위치 이동 + 자세 | |

  각도 →
- [x] **실물에서 먼저** — `G0` 의 `A B C` 가 `?` 보고 `RxRyRz` 와 **같은 값·같은 규약**인가. 한 축씩 명령하고 보고값과 비교 →
  **`A`·`B`·`C` 모두 같다 (9/17)** — 8절
  - 명령 형식 `G0 X.. Y.. Z.. A.. B.. C..` (`common/gcode.py:35`)
  - 정지 확인은 프로브 방식 (`tools/probe_mirobot.py` 의 `wait_settled`)
- [ ] **위치 변환** — mm → m 과 원점. *제안*: Mirobot 홈을 Panda 초기 eef 위치에 맞추고 변위만 옮긴다 →
- [ ] **자세 변환** — ②의 함수
- [ ] **Panda 추종 루프** — waypoint 마다 `(목표 − 현재)` 를 액션 크기(③)로 나눠 `[-1, 1]` 로 자르고,
  가까워질 때까지 반복. 매 스텝 이미지 저장. 자세 오차는 쿼터니언 차이를 axis-angle 로
  - 수렴 기준 →
- [ ] MP4 →

### 5-2. LIBERO → Mirobot

**어디서** demo 내려받기·변환·영상 = OASYS, 실행 = 로봇 노트북.

```
LIBERO demo (ee_pos m, ee_ori axis-angle) ──▶ waypoint 추출 ──▶ 변환·축소 ──▶ Mirobot G0
     │
     └── agentview 이미지 ──▶ Panda MP4   (시뮬 없이 데이터셋 이미지로)
```

**알고 있는 것**

| | | 근거 |
|---|---|---|
| demo 출처 | HF 데이터셋 `nvidia/LIBERO-Cosmos-Policy` (학습용, 크기 미확인) | `cosmos-policy/LIBERO.md:32` |
| 에피소드 구조 | `demo_i/obs/ee_pos`(m), `ee_ori`(**axis-angle**), `joint_states`, `agentview_rgb` 또는 `agentview_rgb_jpeg`. `robot_states` = `[gripper 2, pos 3, quat 4]` | `regenerate_libero_dataset.py:307-333` — 실제 파일로 확인 필요 |
| 이미지 방향 | 데이터셋 이미지는 상하 반전을 **이미 바로잡아** 저장한다 | `:241-246` |

**절차**

- [ ] 데이터셋 전체가 아니라 **에피소드 하나**만 — 서버에 이미 있는지 먼저, 없으면 파일 목록을 보고 일부만 받는다 →
- [ ] demo 고르기 — **자세 변화가 큰** demo (`ee_ori` 변화 폭으로) →
- [ ] waypoint 추출 — 수백 스텝을 몇십 개로. 간격 →
- [ ] **크기 축소** — Panda 궤적이 Mirobot 도달 범위(약 315mm)를 넘는다. 비율 축소 / 범위 안 구간만 / 기타 →
- [ ] 자세 변환 — axis-angle → 회전 → 프레임 회전의 역 → extrinsic XYZ 오일러(°)
- [ ] **J5 범위** `-180° ~ +40°` — 넘는 waypoint 를 표시하고 클램핑 →
  - 참고 (9/17): J4 = 0 이면 **`J5 = Ry − (J2 + J3)`** 로 계산된다 — 8절. `Rx` 가 들어간 waypoint 에는 그대로 못 쓴다
- [ ] Panda MP4 — 데이터셋 이미지를 그대로 이어 붙인다 →
- [ ] Mirobot 실행 →

---

## 6. ⑤ 미팅 준비

**어디서** **발표할 노트북** — MP4 와 궤적 파일을 모아 둔다.

- [ ] Panda MP4 두 개 (5-1, 5-2) 를 노트북에 받아 두기
- [ ] 영상 시점을 미팅에서 Mirobot 을 보는 방향과 맞추기 — agentview 가 어느 쪽에서 보는지는 ③ 표
- [ ] Mirobot 궤적 두 개를 명령 파일로 저장 — 미팅에서 한 번에 실행
- [ ] Mirobot 동작 휴대폰 백업 영상
- [ ] 로봇 노트북·케이블·COM 포트 (9/13 은 COM4)

---

## 7. 주중에 정할 것

- 블록 → 그릇 task 에서 **어떤 동작에서 자세가 바뀌게 할지** →
- LIBERO → Mirobot **궤적 축소 방법** (5-2) →
- 변환 코드 위치·라이브러리 (②) →
- Mirobot 원점을 LIBERO 에 맞추는 방법 (5-1) →

## 8. 실물에서 확인할 것

**9/17 실물** — 로봇 노트북, `tools/probe_mirobot.py`, Cartesian 모드 `G0` 절대좌표, 홈 근처.
로그 `data/probe/20260917_110955.jsonl` (홈·`Y+`·그리퍼·`A`), `data/probe/20260917_112310.jsonl` (`B`·`C` — 프로브를 다시 켜고 `home`).
`20260917_112310.jsonl` 22·23줄의 `B15`·`A15` 는 `raw` 없이 보낸 것이라 아래에 옮기지 않았다.
발췌는 `Angle(ABCDXYZ)` = `[J4, J5, J6, D, J1, J2, J3]` 와 `Cartesian coordinate(XYZ RxRyRz)` 두 필드만 옮겼다.

- [x] **Mirobot `Y+` 가 로봇 기준 왼쪽인가** — [LIBERO_AXES.md](LIBERO_AXES.md) 4절, `F` 확정 조건 1
  → **왼쪽 (눈).** `G0 X198.67 Y30 Z230.72 A0 B0 C0` 을 로봇 뒤에서 `X+` 쪽을 보며 확인했다.
  J1 +8.594° (`atan(30/198.67)` = 8.59°, 위에서 보아 반시계), J6 −8.591° 로 `Rz = 0` 을 유지한다

  ```
  홈    Angle 0.000,0.000,0.000,0.000,0.000,0.000,0.000     Cartesian 198.670,0.000,230.720,0.000,0.000,0.000
  Y30   Angle 0.000,-0.091,-8.591,0.000,8.594,1.181,-1.094  Cartesian 198.672,30.024,230.439,0.000,0.000,0.000
  Y0    Angle 0.000,-0.091,0.000,0.000,0.000,-0.018,0.109   Cartesian 198.668,0.000,230.449,0.000,0.000,0.000
  ```
- [x] **그리퍼 조가 홈에서 벌어지는 방향** — [LIBERO_AXES.md](LIBERO_AXES.md) 4절, `F` 확정 조건 2
  → **좌우(`Y`) (눈)** — Panda 와 같다 → `F` 에 공구 축 90° 가 붙지 않는다.
  `grip M4 S40` 열림, `grip M4 S60` 닫힘. `?` 에서 바뀐 필드는 `Pump PWM` 뿐 (`0 → 40`, `40 → 60`), Angle 불변
- [x] `G0` 의 `A B C` = 보고 `RxRyRz` 인가 (5-1)
  → **`A`·`B`·`C` 모두 같다 — 순서·부호 일치 (9/17).**
  `A10` 에서 J4 +10.000, 플랜지 위치를 붙잡느라 J1 −1.212, J6 +1.227. `B` 는 아래 항목.
  `C20` 은 **J6 만 +20.000** 이고 나머지 관절과 플랜지 위치는 홈 줄과 소수점까지 같다 — top-down 에서 J6 축이 플랜지를 지나므로 보정할 것이 없다

  ```
  A10   Angle 10.000,-0.011,1.227,0.000,-1.212,-0.018,0.234  Cartesian 198.670,0.014,230.449,10.002,0.000,0.000
  A0    복귀 — 위 Y0 줄과 같음
  C20   Angle 0.000,-0.091,20.000,0.000,0.000,-0.018,0.109   Cartesian 198.668,0.000,230.449,0.000,0.000,20.000
  C0    복귀 — 위 Y0 줄과 같음
  ```
- [ ] **기울인 자세에서 J5 범위** — 9/13 은 top-down 만 봤다. 자세를 기울인 채 `line` 을 다시 돌린다 (`tools/probe_mirobot.py`)
  → **홈에서 `B` 만 ±15° (9/17)** — 에러 0, 8회 모두 `Idle`. 기울인 채 `line` 은 아직이다

  ```
  B       J5       J2       J3   J2+J3+J5   보고 Ry   플랜지 X / Z
  +5    4.886    1.089   -0.969     5.006     5.006   198.645 / 230.439
  +10   9.807    2.178   -1.984    10.001    10.000   198.625 / 230.440
  +15  14.681    3.241   -2.922    15.000    15.000   198.599 / 230.435
  0    -0.091   -0.018    0.109     0.000     0.000   198.668 / 230.449
  -5   -5.114   -1.133    1.250    -4.997    -4.996   198.690 / 230.446
  -10 -10.193   -2.244    2.438    -9.999    -9.999   198.724 / 230.435
  -15 -15.306   -3.355    3.656   -15.005   -15.005   198.739 / 230.473
  0    위 0 줄과 같음
  J1·J4·J6 은 8회 모두 0.000
  ```

  - **`J5 = Ry − (J2 + J3)`** — J4 = 0 일 때 8회 모두 0.001° 이내. J2 도 J3·J5 와 같은 부호 규약이다
    (`../W2/CHECKLIST.md` 4절에서 간접으로만 봤던 것). `Rx` 가 들어가 J4 ≠ 0 이면 이 식은 그대로 성립하지 않는다
  - J5 는 기울기와 거의 1:1 — `B +15` 에서 +14.68°. J2+J3 가 `B` 부호와 상관없이 +0.1 ~ +0.3 으로 올라 `+` 쪽을 조금 덜 쓴다
  - 9/13 `x +60` 의 J2+J3 = −6.92 에 대면 그 자리에서 `Ry` 상한은 약 +33° 다 (*합쳐서 재지 않은 추정*)
  - 범위 `-180° ~ +40°` 는 제조사 매뉴얼(WLKATA Mirobot User Manual V1.1, 4.2절 표)과 같다. 펌웨어 설정은 여전히 안 읽었다
- [ ] **IK 해 안정** — 같은 좌표·자세를 다른 출발점에서 여러 번 명령했을 때 관절각이 같은가 (`../W2/CHECKLIST.md` 3-6 셋째 증상) →
- [x] 자세만 바꿀 때 플랜지 위치가 유지되는가 — Cartesian 모드 `G0` 으로 `A B C` 만 바꿔서
  → **유지된다 (9/17).** `A10` 0.02mm, `B ±15` X 0.07mm·Z 0.03mm 이내, `C20` 변화 없음. 복귀하면 이전 줄과 한 글자도 다르지 않다.
  플랜지가 제자리이므로 **파지점은 원호를 그린다** — 4절 "LIBERO eef 위치의 기준점"
- [ ] **플랜지 → 파지점 길이** — 5-1 오프셋 보정의 반지름 (Panda 는 97mm, 4절)
  → **손목 카메라 마운트를 정한 뒤 잰다** — 마운트가 플랜지와 그리퍼 사이에 들어가면 길이가 바뀐다.
  제조사 스펙·매뉴얼·`RosForMirobot` URDF(`Link6` 에서 끝남)에 그리퍼 길이는 없다. 공개된 것은 서보 그리퍼 개폐 범위 0~30mm 뿐
- **체크 항목 외 발견 (9/17)**
  - `?` 한 번에 상태 줄이 **2줄** 온 적이 있다 (27.9ms·43.6ms, 내용 같음). `../W2/CHECKLIST.md` 4절 기록은 1줄.
    늦게 온 줄이 다음 명령 `M4 S60` 의 응답에 **잘린 채** `ok` 앞에 섞였다 (`CDXYZ):0.000,-0.091,...`). 브리지 파싱에 영향이 있는지는 안 봤다
  - `Z230.72` 를 되풀이해 보내면 230.439 ~ 230.449 에 서고 **쌓이지 않는다** — `../W2/CHECKLIST.md` 4절 "보고 Z 가 명령보다 ≈0.28mm 낮다" 의
    누적은 보고값을 다음 명령의 출발점으로 쓸 때만 생긴다

---

## 9. 덮고 답해보기

문서를 닫고 답이 나오면 이해한 것이다.

1. **Mirobot 의 `RxRyRz` 를 LIBERO proprio 에 넣으려면 무엇을 몇 단계로 바꾸나?** →


2. **왜 top-down 궤적만으로는 이번 주 검증이 안 되나?** →


3. **LIBERO → Mirobot 방향이 Mirobot → LIBERO 보다 어려운 이유는?** →


---

## 10. 다음 미팅에 가져갈 질문

- [ ] **같은 액션이 두 로봇에서 다르게 움직인다 — 정책 출력을 Mirobot 에 옮길 때 액션의 의미를 어떻게 맞출까?** (9/17)

  | | 액션 `x = 0.5` 를 한 번 받으면 |
  |---|---|
  | LIBERO Panda | 25mm 앞을 **목표로 잡고**, 한 스텝에 **약 6.5mm** 감 (스프링-댐퍼) |
  | Mirobot | `현재 + 25mm` 로 `G0` 를 보내면 **25mm 를 다 가서 멈춤** (위치 제어) |

  - LIBERO 데모와 Cosmos Policy 의 액션에는 "목표를 앞에 두면 조금씩 따라간다" 는 Panda 컨트롤러 특성이 섞여 있다.
    그대로 옮기면 Mirobot 은 한 스텝에 약 4배 크게 움직인다 — [LIBERO_AXES.md](LIBERO_AXES.md) 2절
  - 후보 — 액션 스케일 조정 / timestep·제어 주기로 맞추기 / Mirobot 데이터로 재학습. timestep·학습은 이번 주 범위 밖이라 방향만 묻는다
  - 이번 주 두 방향 재생에는 영향이 없다. LIBERO → Mirobot 은 Panda 의 **실제 결과**를 기록해 보내고,
    Mirobot → LIBERO 는 closed-loop 추종으로 도착을 확인한다

---

## 관련 문서

- [../meetings/2026-09-14.md](../meetings/2026-09-14.md) — 의견 원문과 결정
- [../W2/CHECKLIST.md](../W2/CHECKLIST.md) — 9/13 실물 측정(4절), Cartesian 을 고른 근거(3절)
- [../W2/W2_진행사항.md](../W2/W2_진행사항.md) — LIBERO 관측/액션 규약
- [../plan/UROP_프로젝트_계획.md](../plan/UROP_프로젝트_계획.md) — §5 파지 자세, §6 액션 표현
- `cosmos-policy/LIBERO.md`, `cosmos-policy/SETUP.md` — 환경 구성
