# W5 — 작업 목록

> **절차** · 확인 2026-09-29 · 기준 `cosmos-policy@18a2acc`, `RosForMirobot-master@8a60a4c`, 9/28 보고
> 9/28 보고에서 정한 이번 주 계획 — pretrained model 의 action 의미를 Mirobot 에 어떻게 맞출지 먼저 정하고, 그 결과로 LIBERO 환경 구성 두 방향(9/21 action plan 2·3번)을 조사·비교한다. `→` 뒤 빈칸은 **미리 채우지 않는다**.

계획 원문은 [../meetings/2026-09-28/Seokhwan action plan.md](../meetings/2026-09-28/Seokhwan%20action%20plan.md), 2·3번 원문은 [../meetings/2026-09-21.md](../meetings/2026-09-21.md) 에 있다.
W4 에서 넘어온 것은 [../W4/CHECKLIST.md](../W4/CHECKLIST.md) 9절이 목록이고, **진행은 여기 7절에 적는다.**

## 0. 이번 주 목표

**Cosmos Policy 를 Mirobot 에 쓸 때 action 을 어떻게 다룰지 정하고, 그 위에서 LIBERO 환경을 어떻게 구성할지 판단을 낸다.**

| | 할 일 | 무엇이 필요한가 |
|---|---|---|
| ① | **action 의미를 어떻게 맞추나** — 실행 단계에서 환산 vs fine-tuning 에서 새로 학습 | 코드·논문 확인은 9/29 에 해 뒀다 (2-2). **출발점 후보가 하나 더 있다**는 것이 드러났다 (2-3) |
| ② | **Mirobot 에 맞춰 LIBERO 환경을 새로 만들기** (2번) | 조사. 재료(URDF)는 있고, 빈 곳이 드러났다 (4-1) |
| ③ | **LIBERO 환경을 골라 Mirobot 을 맞추기** (3번) | 조사. 후보 장면은 좁혀진다 (5-1) |
| ④ | **②·③ 비교와 판단** | ①②③ 결과. 다음 미팅에 가져간다 |

**① 이 선결이다.** ① 의 답에 따라 ②·③ 을 비교하는 기준이 바뀐다 (1절).

**실물이 필요한 작업은 없다.** 로봇 노트북에서 할 일은 7절의 기록 옮기기뿐이다.
계획서 로드맵의 W5(파일럿 10 에피소드)와는 다르다 — 방향은 미팅이 정한다 ([../README.md](../README.md)).

### 한 줄 요약 — 끝나면 채운다

| | 한 줄 |
|---|---|
| ① | |
| ② | |
| ③ | |
| ④ | |

## 1. 순서

```
① action 의미 ── 이미 아는 것(W3) + 코드·논문 → 출발점 → (가) 환산 / (나) 재학습 → 정한다
                 ▼
   공통 ──────── LIBERO 환경을 무엇에 쓰나 (3절)
                 ▼
② 새로 만들기 ─┐
③ 골라 맞추기 ─┘  같은 항목으로 나란히 조사
                 ▼
④ 비교와 판단 ── 표 한 장 + 판단 → 다음 미팅
```

**왜 ① 이 먼저인가** — (가) 로 가면 정책은 Panda 식 action 을 계속 내므로 시뮬에서는 **Panda 가 기준**으로 남는다.
(나) 로 가면 action 의 의미를 Mirobot 이 정하므로, 시뮬에 Mirobot 을 세운다면 **실물처럼 위치 제어**로 움직여야 한다.
어느 쪽이냐에 따라 ②·③ 에서 만들어야 할 것이 달라진다.

---

## 2. ① action 의미를 어떻게 맞추나

> "Cartesian 7차원이라는 action 형식은 그대로 쓸 수 있지만, 같은 값이 두 로봇에서 다르게 움직이기 때문에 …
> 그 값의 의미를 어떻게 맞출지 정해야 합니다." — 9/28 보고

[../W3/CHECKLIST.md](../W3/CHECKLIST.md) 10절 첫째 질문(9/17)이 이것이다. 그때 후보는 셋(스케일 조정 / 제어 주기 / 재학습)이었고,
9/28 보고에서 둘로 좁혔다.

### 2-1. 이미 아는 것 — 같은 action, 다른 움직임 (W3)

| action `Δx = 0.5` (목표를 25mm 앞에 잡는다) | 결과 | 근거 |
|---|---|---|
| Panda — 같은 값을 계속 준다 | 스텝당 **약 6.5mm** 로 계속 간다 (26%) | [LIBERO_AXES.md](../W3/LIBERO_AXES.md) 2절 |
| Panda — 한 번만 주고 그다음은 0 | **5.9mm 에서 선다** | [CONTROL.md](../W3/CONTROL.md) 3절 ① |
| Mirobot — `G0` 로 `현재 + 25mm` | **25mm 를 다 가서 선다** | [CONTROL.md](../W3/CONTROL.md) 1절 |

**26% 는 상수가 아니다.** 같은 값을 계속 줄 때의 정상 상태 비율이고, Panda 의 한 스텝 이동은 **지금 속도**에 달려 있다
(spring-damper — `kp = 150`, `kd ≈ 24.5`, 한 스텝 0.05초). 9/28 보고의 "한 스텝에 약 26%" 는 이것을 줄인 말이다.
→ (가) 환산이 **곱하기 하나로는 끝나지 않는다**는 뜻이다.

### 2-2. 코드·논문으로 확인한 것 (9/29)

경로는 `cosmos-policy/cosmos_policy/` 기준이다.

| | 내용 | 근거 |
|---|---|---|
| chunk | LIBERO 는 action 16개를 한 번에 내고, **16개를 전부 실행한 뒤** 다시 추론한다. 그 사이는 open-loop | `constants.py:28`, `experiments/robot/libero/run_libero_eval.py:215-216` |
| 정규화 | 학습 데이터의 차원별 min/max 로 `[-1, 1]` 에 맞춰 학습하고, 추론 때 `libero_dataset_statistics.json` 으로 되돌린다 | `datasets/dataset_utils.py:179`, `run_libero_eval.py:210-212` |
| **action head 가 없다** | action chunk 를 펼쳐 latent frame 하나에 반복해 채우고(latent injection), 생성된 latent 에서 평균으로 읽어 낸다. 논문도 "no architectural changes" | `models/policy_text2world_model.py:45`, `experiments/robot/cosmos_utils.py:557`, 논문 4.1절 |
| **출발점** | LIBERO·RoboCasa·ALOHA checkpoint 는 **모두 video model `Cosmos-Predict2-2B-Video2World`** 에서 각각 fine-tuning 했다. 한 로봇의 policy 에서 다른 로봇으로 옮긴 경우는 설정에도 논문에도 없다 | `config/experiment/cosmos_policy_experiment_configs.py:62,148,228,305` |
| 실물 선례 — ALOHA | proprio·action 모두 관절 14차원, chunk 50 (25Hz), 데모 185개, video model 에서 출발 | 논문 5.1절 |
| video model 의 몫 | 처음부터 학습하면 LIBERO 평균 −3.9점, ALOHA `fold shirt` −18.7점. 동작도 튄다 | 논문 5.2절 |

### 2-3. 그래서 질문이 하나 앞에 선다 — 어디서 출발하나

"pretrained model" 후보가 **둘**이다. 9/28 보고는 첫째만 가정했다.

| 출발점 | action 을 | 선례 | 맞출 것 |
|---|---|---|---|
| `Cosmos-Policy-LIBERO-Predict2-2B` | Panda OSC 변화량으로 **배웠다** | 없다 | action 의미 — (가) 또는 (나) |
| `Cosmos-Predict2-2B-Video2World` | **배운 적 없다** | 논문의 세 checkpoint 전부 (실물 ALOHA 포함) | 없다 — Mirobot 데이터가 정한다. 대신 LIBERO 에서 배운 조작을 못 쓴다 |

- [ ] **두 출발점에서 얻는 것과 잃는 것** — LIBERO policy 에서 출발하면 탁상 조작, 같은 카메라 구성(3인칭 + 손목), 7차원을 이미 안다.
  대신 Panda 의 의미를 맞추거나 덮어써야 한다
  → 
- [ ] **다른 로봇의 policy 에서 fine-tuning 한 선례** — Cosmos 밖(OpenVLA·π0 계열)에서 action 공간이 다른 로봇으로 옮길 때 무엇을 했나
  → 

### 2-4. (가) 실행 단계에서 환산 — Panda 의 의미를 유지한다

정책은 Panda 식 변화량을 그대로 내고, **실행할 때** Mirobot 절대 좌표로 바꾼다.
**뒷부분은 W3 에 이미 있다** — Panda 가 실제로 간 자세를 절대 좌표로 보내는 것이 W3 5-2(LIBERO → Mirobot) 다.
남는 것은 "이 action 을 받으면 Panda 가 어디로 가나" 를 로봇 노트북에서 구하는 부분이다.

```
정책 action ──▶ Panda 가 갈 자세 ──▶ W3 변환 ──▶ Mirobot G0 (절대)
                (시뮬 Panda 또는 가상 spring-damper)
```

- [ ] **Panda 의 반응을 무엇으로 구하나** — 시뮬 Panda 를 옆에서 돌리기 / 가상 spring-damper(`kp`·`kd`·0.05초)로 계산하기
  → 
- [ ] **가상 spring-damper 가 맞는지 — 실물 없이 된다.** 서버 `data/follow/*.jsonl` 에 스텝마다 `action` 과 `eef_pos` 가 있다
  (`tools/libero_follow.py:157`). 기록된 action 열을 모형에 넣어 예측한 위치를 기록된 위치와 댄다
  → 
- [ ] **fine-tuning 도 한다면 학습 라벨도 Panda 식이어야 한다** — Mirobot 데모를 "Panda 가 이 궤적을 따라가려면 받았을 action" 으로 바꾼다.
  그 도구도 있다 — `tools/libero_follow.py` 가 Mirobot 궤적을 Panda 로 따라가며 스텝마다 action 을 남긴다 (W3 5-1).
  **단 시간축이 안 맞는다** — 도착을 확인하고 넘어가는 방식이라 스텝 수가 Mirobot 기록과 다르다
  → 
- [ ] **chunk 16개가 open-loop 로 실행된다** (2-2) — 환산 오차가 chunk 안에서 쌓이는지
  → 
- [ ] **입력도 Panda 형식이어야 한다** — proprio(파지점·쿼터니언·손가락 2칸)를 Mirobot 값에서 만들어 넣는다.
  W3 변환이 여기에 쓰인다. 파지점 기준이라 **손끝이냐 플랜지냐 회신**(W4 8절)에 걸린다
  → 

### 2-5. (나) fine-tuning 에서 Mirobot 방식으로 새로 학습 — 의미를 새로 정한다

Mirobot 데모의 action 라벨을 **Mirobot 기준**으로 정하고, 모델이 그 의미를 새로 배우게 한다.

- [ ] **라벨을 무엇으로** — 다음 스텝의 절대 자세 / 스텝 사이 자세 차 / 다음 waypoint 의 절대 자세.
  계획서 6절 "상위집합 기록" 원칙대로 모으면 **학습 시점에 고를 수 있다.** 지금 확인할 것은 **기록 형식이 세 후보를 다 담는가**다
  → 
- [ ] **크기 차이는 정규화가 흡수하는가** — min/max 로 `[-1, 1]` 에 맞추므로(2-2) "약 4배" 같은 크기 차이는 통계가 흡수할 것이다.
  남는 것은 의미(목표 오프셋 vs 실제 이동)다
  → 
- [ ] **그래도 LIBERO policy 에서 출발할 이유가 남는가** — (나) 는 LIBERO 에서 배운 action 의미를 덮어쓴다. 그러면 video model 출발(2-3)과 무엇이 다른가.
  데이터는 150개 계획이고(계획서 6절), ALOHA 는 185개로 video model 에서 출발했다
  → 
- [ ] **실행 모습** — Mirobot 이 목표 16개를 받아 차례로 간다. 멈추지 않는 `--stream` 실행이 된다 → 7절 `--stream` 누적 확인과 이어진다.
  명령 주기도 걸린다 — W3 에서 `--stream` 기록이 9.3Hz 로 찍혔다 (설정 20Hz, [../W3/CHECKLIST.md](../W3/CHECKLIST.md) 5-1 (나))
  → 

### 2-6. 정한다

- [ ] **출발점 × (가)/(나) 를 한 표로** — 모델이 배운 것을 쓰는가 / 새로 만들 것 / 선례 / 위험
  → 
- [ ] **파생 — 계획서 6절 "액션 표현" 을 코드 기준으로 다시 본다.** 지금 표는 Cartesian 7차원의 근거로
  "사전학습 헤드를 그대로 쓴다" 를, joint 의 단점으로 "출력층 재학습" 을 든다. **Cosmos Policy 에는 action head 가 없다** (2-2) —
  ALOHA 는 같은 구조로 관절 14차원을 쓴다. 4절 LoRA 설계의 "액션 / value 헤드 → 전체 학습" 도 같은 전제다.
  **"헤드" 근거가 빠지면 Cartesian 을 고른 이유로 무엇이 남는가**
  → 

---

## 3. ②·③ 에 들어가기 전에 — 무엇에 쓸 환경인가

**2번과 3번은 목적이 정해져야 비교가 된다.**

- [ ] **LIBERO 환경을 무엇에 쓰나** — (a) 실물 작업대·카메라 배치의 기준 / (b) 시뮬에서 Mirobot 데이터 생성 / (c) 실물 전에 정책을 시뮬에서 평가.
  계획서는 LIBERO 를 **Panda 로 그대로** 쓰는 시뮬 검증 트랙에 두고(5절), 학습 데이터는 **실물에서** 모은다(6절). 2·3번은 여기서 한 발 나간 것이다.
  (a) 만이면 시뮬에 Mirobot 이 없어도 되고, (b)·(c) 면 로봇 모델(4-2)이 필요하다
  → 
- [ ] **3번의 "Mirobot 을 맞춘다" 가 무엇인지** — 시뮬 안에 Mirobot 을 세워 장면에 맞추는가, 실물 Mirobot 의 배치를 LIBERO 장면에 맞추는가
  → 
- 스스로 못 정하면 8절 질문으로 가져간다

---

## 4. ② Mirobot 에 맞춰 LIBERO 환경을 새로 만들기 (2번)

로봇 모델과 장면(작업대·물체 배치)을 **Mirobot 크기로 새로** 만든다.

### 4-1. 재료 — 있는 것과 빈 곳 (9/29 확인)

| | 상태 |
|---|---|
| URDF | `RosForMirobot-master/mirobot_urdf_2/urdf/mirobot_urdf_2.urdf` — joint 6개의 origin·axis·limit, STL 7개. **`Link6` 에서 끝난다 — 그리퍼도 tool frame 도 없다** |
| 영점 자세 | URDF 로 계산한 `Link6` 원점이 `(198.67, −0.12, 238.72)`mm. 펌웨어 홈 `(198.67, 0, 230.72)` 과 **x 는 같고 z 가 8.00mm 높다** — 베이스 원점을 다른 곳에 잡았다 |
| 관절 한계 | **URDF 값이 실제와 다르다** — J1 `−100°~+160°`, J2 `−30°~+70°`, J3 `−170°~+60°`, J4 `±350°`, J5 `−205°~+36°`, J6 `±360°`. J5 의 펌웨어 값은 `+30°` 다 (W4 4절) |
| 질량·관성 | 링크마다 **1g**, 베이스 10g — 자리만 채운 값이다 |
| 메시 경로 | `package://mirobot_urdf_2/meshes/...` — ROS 경로라 MuJoCo 에서 바로 안 읽힌다 |

### 4-2. 할 일

- [ ] **URDF → MJCF** — 메시 경로 정리, 베이스 원점 8mm 를 펌웨어 기준에 맞출지
  → 
- [ ] **robosuite 로봇으로 등록** — Panda 가 어떤 파일로 이뤄지는지 서버 소스에서 본다
  (robosuite `models/robots/manipulators/panda_robot.py`, `models/assets/robots/panda/robot.xml`, LIBERO `envs/robots/mounted_panda.py`).
  이름 규칙, `init_qpos`, 기본 그리퍼·마운트·컨트롤러 가운데 무엇을 요구하나
  → 
- [ ] **컨트롤러** — OSC_POSE(Panda 와 같은 힘 제어, **실제에 가까운 질량·관성이 필요하다** — 4-1) / 관절 위치 제어(실물 Mirobot 과 같은 방식).
  ① 이 (나) 라면 후자가 자연스럽다. OSC 절대 모드(`control_delta: false`)도 있지만 문제 보고가 있다 ([CONTROL.md](../W3/CONTROL.md) 3절)
  → 
- [ ] **그리퍼와 파지점** — 그리퍼 모델이 없다. 최소한 플랜지에서 55mm 떨어진 파지점(`grip_site`)을 둔다 (W3 8절 실측).
  손끝이냐 플랜지냐 회신과 이어진다
  → 
- [ ] **관절 한계는 펌웨어 값으로** — 9/28 `$$` 기록(로봇 노트북 `data/probe/`)에서 여섯 축을 옮긴다. W4 4절에는 J5 만 적었다
  → 
- [ ] **장면** — BDDL 로 작업대 크기와 물체 위치를 Mirobot 도달 범위(약 315mm)에 맞춰 새로 쓴다. LIBERO 물체·장면 파일을 그대로 가져다 쓸 수 있나
  → 

---

## 5. ③ LIBERO 환경을 골라 Mirobot 을 맞추기 (3번)

**있는 장면을 그대로 두고** Mirobot 을 거기에 맞춘다.

### 5-1. 후보 장면

- Cosmos checkpoint 는 LIBERO 네 suite 를 모두 학습했다 (`cosmos-policy/LIBERO.md:39`)
- **우리 task 와 구조가 가장 가까운 것은 LIBERO-Object** — 여러 물체 가운데 문장이 고른 것을 바구니에 넣는다
  (`cosmos_policy/experiments/robot/libero/libero_object_metainfo.json`). 계획서 5절의 "색이 다른 블록 → 그릇" 도 이 축을 본떴다.
  다음은 LIBERO-Goal `put_the_cream_cheese_in_the_bowl`, LIBERO-Spatial(그릇 → 접시)

- [ ] **후보 장면의 치수** — 작업대 크기, 물체가 놓이는 범위, 로봇 베이스에서의 거리 (BDDL·장면 파일, 서버)
  → 
- [ ] **장면 종류** — suite 마다 탁상인지 바닥인지 다를 수 있다. 확인한다
  → 

### 5-2. 맞추는 방법

- [ ] **도달 범위가 핵심 제약이다** — Panda 약 855mm, Mirobot 약 315mm, **2.7배.** 장면을 줄이나 / Mirobot 을 물체 가까이 두나 / 범위 안 물체만 쓰나.
  **W4 8절 "궤적 축소 방법" 과 같은 문제다** → 8절 질문
  → 
- [ ] **카메라** — 3인칭·손목 카메라를 Mirobot 크기에 맞춰 옮기나, LIBERO 위치를 그대로 두나.
  LIBERO policy 에서 출발한다면(2-3) 학습 때 본 그림과 닮을수록 유리할 것이다
  → 
- [ ] **시작 자세** — Mirobot 은 홈 고정이다 (W4 4절 파생 결정). LIBERO 는 3.25° 에 판마다 노이즈가 얹힌다 ([LIBERO_AXES.md](../W3/LIBERO_AXES.md) 1절)
  → 
- [ ] **시뮬 안에 Mirobot 을 세운다면 로봇 모델은 ② 와 같다** (4-2 의 앞 다섯 항목). ③ 이 ② 와 다른 점은 **장면을 새로 만들지 않는다**는 것뿐이다.
  3절의 답에 따라 이 항목은 필요 없을 수도 있다
  → 

---

## 6. ④ ②·③ 비교와 판단

- [ ] **같은 기준으로 표 한 장**

  | 기준 | ② 새로 만들기 | ③ 골라 맞추기 |
  |---|---|---|
  | 새로 만들 것 | | |
  | 도달 범위 (315mm) | | |
  | LIBERO 학습 그림과의 거리 — ① 의 출발점에 따라 무게가 달라진다 | | |
  | 실물 작업대와의 대응 | | |
  | ① 의 결론과 맞는가 | | |
  | 예상 작업량 | | |

  → 
- [ ] **판단** — 어느 쪽인지와 그 이유. 9/28 보고에서 "제 판단을 함께 말씀드리겠다" 고 했다
  → 

---

## 7. W4 에서 넘어온 것

목록과 사정은 [../W4/CHECKLIST.md](../W4/CHECKLIST.md) 9절에 있다. **진행은 여기 적는다.** ①~④ 가 먼저다.

- [ ] **`data/gcode_run/` 을 서버로 옮긴다** — 로봇 노트북에만 있다. 오면 바로 되는 것 둘
  - [ ] `F` 수치화 (W4 5-1-1) — `F` 의 근거가 아직 **눈**이다
  - [ ] 보고 `Z` 오프셋 98 waypoint 확인 (W4 5-2)
  → 
- [ ] **`--stream` 누적 확인** (W4 5-2) — ① 이 (나) 면 chunk 를 연속 실행하게 되어 **실제로 쓰는 모습이 이것**이다 (2-5)
  → 
- [ ] **그리퍼** — proprio 대응(Panda 2칸 vs Mirobot 1칸), 9/28 실물 개폐 시험 결과 확인 (W4 6절)
  → 
- [ ] **문서 반영 셋** — ANSWER ③ 에 J5 `-200°~+30°`, ② 에 IK/FK 읽기, `CONTROL.md`·② 에 "멈춤 기준은 파지점" (W4 9절)
  → 
- [ ] **누적 판정의 대조군** — 교란을 넣어 도구가 누적을 잡아내는지 본다 (W4 9절)
  → 

### 곁가지

- [ ] **HF 접근 — 9/28 에 `Cosmos-Policy-LIBERO-Predict2-2B` 가 `GatedRepoError: 401`** (W4 9절).
  다만 [../MODELS.md](../MODELS.md) 에는 9/9 에 OASYS 캐시에 **이미 받아져 있다**고 적혀 있다 — 권한 문제인지, 캐시·토큰이 다른 환경이었는지부터 본다.
  **2-3 의 둘째 출발점 `Cosmos-Predict2-2B-Video2World` 도 받을 수 있는지** 같이 확인한다
  → 
- [ ] **계획서 6절 로깅 스키마의 "관절각 명령값 / 실측값 분리"** — W4 ④ 4절 이후로 `?` 는 실측이 아니라 펄스 카운터의 계산값이다.
  "필드 하나가 빠지면 재수집 외에 복구 불가" 라고 적힌 목록이라 **수집(W6) 전에** 문구와 실제로 남길 값을 고친다
  → 

---

## 8. 다음 미팅에 가져갈 질문

- [ ] **궤적 축소 방법** — Panda 도달 약 855mm vs Mirobot 약 315mm. 비율 축소 / 범위 안 구간만 / 기타.
  W4 8절에서 넘어왔고 **아직 여쭙지 않았다.** ③ 의 핵심 제약이다 (5-2)
- [ ] **손끝이냐 플랜지냐** — 9/28 에 여쭸다 ([../W4/ANSWER.md](../W4/ANSWER.md) ①). **회신 대기.** (가) 의 proprio(2-4)와 그리퍼 파지점(4-2)이 여기에 걸린다
- [ ] **(3절에서 못 정하면) LIBERO 환경을 무엇에 쓰려는 것인지** — 배치 기준 / 시뮬 데이터 / 시뮬 평가
- [ ] **① 은 제어 주기와 떼어 놓을 수 없다** — Panda 의 한 스텝은 0.05초이고 chunk 16개는 0.8초다.
  9/14 "timestep 은 아직 고려하지 않아도 된다" 의 범위를 넘는지 여쭙는다

---

## 관련 문서

- [../meetings/2026-09-28/Seokhwan action plan.md](../meetings/2026-09-28/Seokhwan%20action%20plan.md) — 9/28 보고와 이번 주 계획 원문
- [../meetings/2026-09-21.md](../meetings/2026-09-21.md) — 9/21 action plan 2·3번 원문
- [../W4/CHECKLIST.md](../W4/CHECKLIST.md) 9절 — W4 에서 넘어온 목록
- [../W3/CONTROL.md](../W3/CONTROL.md) — 두 로봇이 명령을 받아 움직이는 방식, Panda 를 목표까지 보내는 세 방식(3절)
- [../W3/LIBERO_AXES.md](../W3/LIBERO_AXES.md) 2·3절 — action 대비 실제 이동(26%)
- [../plan/UROP_프로젝트_계획.md](../plan/UROP_프로젝트_계획.md) — 4절 자원·LoRA, 5절 태스크, 6절 액션 표현·데이터 수집
- [../MODELS.md](../MODELS.md) — checkpoint 와 캐시
- `cosmos-policy/LIBERO.md`, `papers/cosmos.pdf` ([../PAPERS.md](../PAPERS.md)) — 학습 설정과 논문
