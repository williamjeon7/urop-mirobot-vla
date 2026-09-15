# W3 — 작업 목록

> **절차** · 확인 2026-09-15 · 기준 `cosmos-policy@18a2acc`, 9/13 실물 측정
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

---

## 2. ① OASYS 에 LIBERO 시뮬 환경

**산출물** 서버에서 LIBERO 환경을 만들고 dummy action 으로 몇 스텝 돌린 MP4 한 개.

**알고 있는 것**

| | | 근거 |
|---|---|---|
| 공식 방식 | Docker 컨테이너 안에서 `uv sync --extra cu128 --group libero --python 3.10` | `cosmos-policy/LIBERO.md:25`, `cosmos-policy/SETUP.md` |
| LIBERO·robosuite | 위 명령에 안 들어 있다. `pip install -e LIBERO`, `pip install -e robosuite` 로 따로 | `cosmos-policy/pyproject_simplified.toml:75-77` |
| 버전 | robosuite 1.4.1, mujoco 3.3.2, bddl | `../VENDORED.md:45` |
| 화면 없는 렌더링 | Docker 이미지에 `libegl1-mesa-dev` 가 들어 있다 → EGL | `cosmos-policy/docker/Dockerfile:32` |
| 지금 서버 | conda `urop` 에는 시뮬 패키지가 없다. Cosmos Policy 체크포인트는 HF 캐시에 있다 | `../SETUP_LINUX.md:108-112`, `../MODELS.md:78` |

**절차**

- [ ] 서버에 무엇이 있는지 본다
  ```bash
  nvidia-smi                                   # GPU
  docker --version && docker images | grep -i cosmos   # Docker 사용 가능 여부, 이미지 존재
  ls <cosmos-policy clone 경로>/.venv          # uv 환경이 이미 있나
  ```
  →
- [ ] 설치 경로 — Docker(공식) / Docker 없이 uv 직접 →
- [ ] LIBERO·robosuite 설치 →
- [ ] import 확인 (`MUJOCO_GL=egl` 은 mujoco 화면 없는 렌더링의 일반적인 설정)
  ```bash
  MUJOCO_GL=egl python -c "from libero.libero.envs import OffScreenRenderEnv; print('ok')"
  ```
  →
- [ ] 환경 하나 만들고 dummy action 20스텝 → MP4
  - 환경 생성 `get_libero_env()` (`libero_utils.py:30`), dummy action `[0,0,0,0,0,0,-1]` (`:42`)
  - 영상 저장 `save_rollout_video()` (`:61`) — `./rollouts/<날짜>/` 에 30fps
  - **렌더 이미지는 상하가 뒤집혀 나온다** — `np.flipud` 후 저장
    (`cosmos-policy/README.md:57`, `regenerate_libero_dataset.py:242`)

  →

**막힌 것 / 걸린 시간** →

---

## 3. ② 오일러각 → 쿼터니언

**산출물** Mirobot `RxRyRz` ↔ LIBERO `eef_quat` 변환 함수와 확인용 테스트.

**알고 있는 것**

| | | 근거 |
|---|---|---|
| Mirobot 규약 | `RxRyRz` 는 **extrinsic XYZ**, 단위 도(°) | 9/13 실측, `../W2/CHECKLIST.md` 4절 "좌표" |
| Mirobot top-down | 홈 자세 = `(0,0,0)` = 항등 회전 | 같은 곳 |
| Mirobot 보고 위치 | 그리퍼 끝이 아니라 **플랜지** | `../W2/CHECKLIST.md` 4절 "`?` 응답 형식" |
| LIBERO 순서 | **`xyzw` 로 보인다** — `robot0_eef_quat` 를 robosuite `T.quat2axisangle` 에 그대로 넣는다 | `regenerate_libero_dataset.py:237`, `libero_utils.py:294` |
| LIBERO top-down | 샘플 `[5:9] = 0.9996, −0.0005, −0.027, −0.0001` → `xyzw` 로 읽으면 x축 180° | `../W2/W2_진행사항.md` 1절 |
| 우리 스키마 | `wxyz` 순 | `common/schema.py:27` |
| 파서 | `Cartesian` 6개 중 XYZ 3개만 담는다 | `robot/serial_bridge.py:180-182` |

**변환 단계 (Mirobot → LIBERO)**

1. `RxRyRz`(°) → 회전 — extrinsic XYZ
2. **프레임 회전** — Mirobot top-down(항등)을 LIBERO top-down(x축 180°)에 맞춘다. 앞에 곱할지 뒤에 곱할지는 ③에서 정한다
3. `xyzw` 순서로 저장
4. **부호 연속성** — `q` 와 `−q` 는 같은 자세다. top-down 근처는 `w≈0` 이라 "w≥0 으로 맞추기" 를 쓰면
   스텝마다 부호가 뒤집힌다 → **직전 쿼터니언과의 내적이 음수면 뒤집는다**

LIBERO → Mirobot 은 역순이다. 단 LIBERO 데이터셋의 자세는 쿼터니언이 아니라 **axis-angle** 로 저장돼 있다 (5-2).

**절차**

- [ ] 변환 코드 위치 (`common/` 에 두면 노트북·서버 양쪽에서 쓴다) →
- [ ] 라이브러리 — scipy 는 저장소에도 서버 `urop` env 에도 없다. scipy 추가 / numpy 로 직접 →
  - scipy 라면 `Rotation.from_euler("xyz", ..., degrees=True)` — **소문자가 extrinsic**. `as_quat()` 은 `xyzw`
- [ ] 프레임 회전을 뺀 1·3·4 단계 먼저 작성 →
- [ ] 테스트 — 답을 이미 아는 경우로
  - `(0,0,0)` → 항등
  - 9/13 `euler` 측정값 재현 (`../W2/CHECKLIST.md` 4절 "RxRyRz 의 오일러 규약")
  - 왕복: 오일러 → 쿼터니언 → 오일러 가 원래 값
  - 부호: 180° 근처에서 조금씩 도는 궤적에서 부호가 튀지 않는지

  →
- [ ] ③ 결과로 프레임 회전 추가 →

---

## 4. ③ LIBERO 시뮬에서 Panda 움직여 보기

**산출물** LIBERO 좌표계 확인 표. ②의 프레임 회전과 ④의 추종 루프가 여기에 달려 있다.

**알고 있는 것**

| | | 근거 |
|---|---|---|
| 관측 | `robot0_eef_pos`(m), `robot0_eef_quat`, `robot0_joint_pos`, `agentview_image` | `run_libero_eval.py:334`, `regenerate_libero_dataset.py:223-243` |
| 액션 | `[Δx, Δy, Δz, Δrx, Δry, Δrz, gripper]` 델타. 컨트롤러는 OSC_POSE 로 **추정** | `../W2/W2_진행사항.md` 2절 |
| 그리퍼 | `-1` 이 열림 | `libero_utils.py:42` |

**절차** — 시험마다 환경을 리셋한다

- [ ] 첫 관측의 `robot0_eef_quat` — top-down 이면 `xyzw` 기준 `[±1, 0, 0, 0]` 근처인가 →
- [ ] 위치 축 — 한 성분만 `+` 로 몇 스텝

  | 액션 | `eef_pos` 에서 커진 축 | agentview 영상에서 방향 |
  |---|---|---|
  | `Δx +` | | |
  | `Δy +` | | |
  | `Δz +` | | |

- [ ] 회전 축 — 한 성분만 `+` 로 몇 스텝

  | 액션 | `eef_quat` 에서 변한 성분 | 그리퍼가 기우는 방향 |
  |---|---|---|
  | `Δrx +` | | |
  | `Δry +` | | |
  | `Δrz +` | | |

- [ ] 액션 크기 — `1.0` 한 스텝이 몇 m·몇 rad 인가 (robosuite OSC 기본값은 0.05m·0.5rad 로 알려져 있으나 **미확인**) →
- [ ] Mirobot 축과 대응 — Mirobot 은 홈에서 앞이 X+, J1+ 방향이 Y+ (`../W2/CHECKLIST.md` 4절 "관절 순서")

  | Mirobot | LIBERO |
  |---|---|
  | X | |
  | Y | |
  | Z | |

- [ ] **프레임 회전 결정** → ②에 반영 →
- [ ] LIBERO eef 위치의 기준점 — 그리퍼 끝인가 플랜지인가. Mirobot 은 플랜지라 자세를 바꾸면 위치 차이가 생긴다 →

---

## 5. ④ 두 방향 재생

**공통** — 시간을 보지 않으므로 **waypoint 단위**로 재생한다. 한 waypoint 에 도달(정지)한 것을 확인하고 다음으로 간다.

### 5-1. Mirobot → LIBERO

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
- [ ] **실물에서 먼저** — `G0` 의 `A B C` 가 `?` 보고 `RxRyRz` 와 **같은 값·같은 규약**인가. 한 축씩 명령하고 보고값과 비교 →
  - 명령 형식 `G0 X.. Y.. Z.. A.. B.. C..` (`common/gcode.py:35`)
  - 정지 확인은 프로브 방식 (`tools/probe_mirobot.py` 의 `wait_settled`)
- [ ] **위치 변환** — mm → m 과 원점. *제안*: Mirobot 홈을 Panda 초기 eef 위치에 맞추고 변위만 옮긴다 →
- [ ] **자세 변환** — ②의 함수
- [ ] **Panda 추종 루프** — waypoint 마다 `(목표 − 현재)` 를 액션 크기(③)로 나눠 `[-1, 1]` 로 자르고,
  가까워질 때까지 반복. 매 스텝 이미지 저장. 자세 오차는 쿼터니언 차이를 axis-angle 로
  - 수렴 기준 →
- [ ] MP4 →

### 5-2. LIBERO → Mirobot

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
- [ ] Panda MP4 — 데이터셋 이미지를 그대로 이어 붙인다 →
- [ ] Mirobot 실행 →

---

## 6. ⑤ 미팅 준비

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

- [ ] `G0` 의 `A B C` = 보고 `RxRyRz` 인가 (5-1) →
- [ ] **기울인 자세에서 J5 범위** — 9/13 은 top-down 만 봤다. 자세를 기울인 채 `line` 을 다시 돌린다 (`tools/probe_mirobot.py`) →
- [ ] **IK 해 안정** — 같은 좌표·자세를 다른 출발점에서 여러 번 명령했을 때 관절각이 같은가 (`../W2/CHECKLIST.md` 3-6 셋째 증상) →
- [ ] 자세만 바꿀 때 플랜지 위치가 유지되는가 — Cartesian 모드 `G0` 으로 `A B C` 만 바꿔서 →

---

## 9. 덮고 답해보기

문서를 닫고 답이 나오면 이해한 것이다.

1. **Mirobot 의 `RxRyRz` 를 LIBERO proprio 에 넣으려면 무엇을 몇 단계로 바꾸나?** →


2. **왜 top-down 궤적만으로는 이번 주 검증이 안 되나?** →


3. **LIBERO → Mirobot 방향이 Mirobot → LIBERO 보다 어려운 이유는?** →


---

## 10. 다음 미팅에 가져갈 질문

- [ ]

---

## 관련 문서

- [../meetings/2026-09-14.md](../meetings/2026-09-14.md) — 의견 원문과 결정
- [../W2/CHECKLIST.md](../W2/CHECKLIST.md) — 9/13 실물 측정(4절), Cartesian 을 고른 근거(3절)
- [../W2/W2_진행사항.md](../W2/W2_진행사항.md) — LIBERO 관측/액션 규약
- [../plan/UROP_프로젝트_계획.md](../plan/UROP_프로젝트_계획.md) — §5 파지 자세, §6 액션 표현
- `cosmos-policy/LIBERO.md`, `cosmos-policy/SETUP.md` — 환경 구성
