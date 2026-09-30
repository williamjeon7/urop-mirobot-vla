# action 의미 — action 번역이냐 action 재학습이냐

> **설계** · 확인 2026-09-30 · 기준 `cosmos-policy@18a2acc`, W3 측정 ([../W3/LIBERO_AXES.md](../W3/LIBERO_AXES.md) 2절, [../W3/CONTROL.md](../W3/CONTROL.md) 3절)
> LIBERO policy 에서 출발할 때, 그 모델이 배운 Panda 식 action 을 Mirobot 에 어떻게 맞출지 — 두 방법의 구조, 비용, 판단.

작업 목록은 [CHECKLIST.md](CHECKLIST.md) 2-4·2-5·2-6 이다. 여기는 **두 방법의 설명과 비교, 판단 근거**를 둔다.
출발점을 LIBERO policy 로 정한 이유는 [CHECKPOINT.md](CHECKPOINT.md).

## 0. 질문

**같은 action 이 두 로봇에서 다르게 움직인다** ([CHECKLIST.md](CHECKLIST.md) 2-1). action `Δx = 0.5` 는 "목표를 25mm 앞에 잡아라" 인데,
Panda 는 그 목표를 스프링으로 당겨 **한 스텝에 약 6.5mm** 만 가고, Mirobot 에 `현재 + 25mm` 를 주면 **25mm 를 다 간다.**

LIBERO policy 는 Panda 쪽 의미로 action 을 배웠다. 이것을 어떻게 할지가 질문이고, 방법이 둘이다.

| | 한 줄 |
|---|---|
| **action 번역** (가) — 실행 단계에서 환산 | Panda 의 의미를 **유지**한다. 모델은 계속 Panda 식 action 을 내고, 실행할 때 번역한다 |
| **action 재학습** (나) — fine-tuning 에서 재학습 | Mirobot 의 의미로 **새로 배운다**. 라벨을 Mirobot 기준으로 만들어 fine-tuning 한다 |

두 방법을 **action 번역**, **action 재학습**이라 부른다 (9/30). 처음에는 (가)·(나) 로 불렀다. **우리는 action 번역으로 간다** (4절).

---

## 1. action 번역 (가) — 실행 단계에서 환산

### 1-1. 한 줄로

**모델 입장에서는 여전히 Panda 를 조종하고 있다.** 우리는 모델과 Mirobot 사이에 "Panda 라면 이 action 을 받고 어디로 갔을까"
를 계산하는 **번역기**를 두고, Mirobot 에는 그 자리로 가라고 시킨다.

### 1-2. 실행할 때 — chunk 하나가 도는 모습

```
① 관측     Mirobot 카메라 2장 + Mirobot 상태
              │ proprio 를 Panda 형식으로 — 파지점 위치 · 쿼터니언 (좌표 변환, 9/30 파지점 기준)
              │                            손가락 2칸 ← 서보 1개 (미정)
② 정책     Cosmos (LIBERO 에서 출발) → action 16개 — Panda 식 변화량
③ 번역기   "Panda 가 이 16개를 차례로 받으면 어디로 가나" → Panda 파지점 자세 16개      ← 연결 코드만 새로
              (서버의 시뮬 Panda — robosuite OSC 에 그대로 넣고 손 자세를 읽는다, 1-9)
④ 좌표 변환 Panda 자세 → Mirobot G0 절대 좌표 — common/workspace.py · rotation.py  ← 이미 있다
⑤ 실행     Mirobot 이 16자리를 차례로 간다 → 다시 ①
```

**새로 만들 것은 ③ 의 연결 코드뿐이다** — 번역기 자체는 robosuite 가 한다 (1-9). ④ **좌표 변환**은 Panda 손의 위치·자세를 Mirobot 명령으로 바꾸는 계산이다 — 기준점끼리 짝지어 변위만 옮기고
(Panda 시작 자세 ↔ Mirobot 홈), 단위와 자세 표현을 바꾼다. "Panda 가 실제로 간 자세를 Mirobot 절대 좌표로 보내는" 경로로 9/17~9/28 실물에서 이미 검증했다
([../W3/CONTROL.md](../W3/CONTROL.md) 4절 — LIBERO → Mirobot 은 action 차이의 영향을 받지 않는다).

### 1-3. 왜 번역기가 필요한가 — 곱하기로는 안 된다

"Panda 는 26% 만 가니 action 에 0.26 을 곱해 Mirobot 에 주자" 는 **틀린다.** Panda 의 한 스텝 이동은 action 크기만이 아니라
**지금 속도**에 달려 있기 때문이다 (spring-damper).

| 같은 action `Δx = 0.5` | Panda 가 간 거리 |
|---|---|
| 20스텝 계속 준다 | 스텝당 **약 6.5mm** — 속도가 붙은 뒤 |
| 한 번만 주고 그다음은 0 | 모두 합쳐 **5.9mm** 에서 선다 |

같은 첫 스텝이라도 앞뒤에 무엇이 오느냐에 따라 결과가 다르다. 그래서 번역기는 **속도를 기억하면서** 스텝을 따라가야 하고,
chunk 가 바뀌어도 그 속도를 이어받아야 한다.

**번역기는 서버의 시뮬 Panda 로 한다 (1-9).** 아래 **가상 spring-damper** 는 시뮬 Panda 를 통째로 돌리지 않고 컨트롤러만 흉내 내는
계산이다 — 가벼운 대안·검산용으로 둔다.

```
매 스텝 (0.05초)
  목표   = 현재 + action × (0.05 m, 0.5 rad)          robosuite control_utils.py:135
  가속도 = kp × (목표 − 현재) − kd × 속도              kp = 150, kd ≈ 24.5  (osc.py:158,319)
  → 0.05초 동안 적분해 다음 위치·속도
```

실제 OSC 는 팔의 질량 행렬까지 쓰므로 이 계산은 **근사**다. 얼마나 맞는지는 아직 모른다 (1-7).

### 1-4. 학습할 때 — 라벨도 Panda 식이어야 한다

Mirobot 카메라 그림은 LIBERO 와 다르니 **fine-tuning 은 action 번역에서도 한다.** 그때 Mirobot 데모의 action 라벨을
**"Panda 가 이 궤적을 따라가려면 받았어야 할 action"** 으로 만들어야 모델이 배운 의미가 유지된다.

| 라벨 만드는 법 | 장점 | 걸리는 것 |
|---|---|---|
| 시뮬 Panda 로 Mirobot 궤적을 따라가게 하며 action 을 기록 — **`tools/libero_follow.py` 가 이미 한다** (Mirobot 궤적 → 시뮬 Panda 재생 도구) | 진짜 OSC 반응이다 | **시간축이 안 맞는다** — 도착을 확인하고 넘어가는 방식이라 스텝이 Mirobot 기록과 다르다. 카메라 그림과 짝지으려면 다시 맞춰야 한다 |
| 가상 spring-damper 를 **거꾸로** 푼다 — 기록된 자세열(20Hz 로 다시 뽑은 것)에서 "다음 자세로 가게 하는 action" 을 계산 | 시간축이 그대로다 | 모형이 근사다 |

**라벨과 실행에 같은 모형을 쓰면 서로 맞는다.** 모형이 실제 OSC 와 조금 달라도, 라벨을 만든 모형과 실행 때 번역하는 모형이 같으면
우리 파이프라인 안에서는 일관된다. 모형이 정확할수록 LIBERO 에서 배운 것을 더 살린다.

**정함 (9/30) — 시뮬 Panda 로 따라가게 해서 라벨을 만든다.** 진짜 OSC 반응을 그대로 쓰는 쪽이다. 대신 따라가는 방식을 바꾼다.

```
Mirobot 데모 (실물) — 카메라 그림 + 타임스탬프 찍힌 자세 기록
        │ 자세 기록을 0.05초 격자에 맞춘다 (가장 가까운 기록, 또는 앞뒤 기록 사이 짧은 보간)
        │ 좌표 변환 → Panda 목표
        ▼
시뮬 Panda — 스텝 k 의 목표 = "k × 0.05초 시점의 Mirobot 자세"   ← 시간이 되면 다음으로
        │ 매 스텝 준 action 을 기록
        ▼
학습 한 칸 = (k × 0.05초의 Mirobot 카메라 그림, 그때의 Mirobot 상태를 Panda 형식으로, 스텝 k 의 action)
```

- **"도착하면 다음으로" 가 아니라 "시간이 되면 다음으로"** — 지금 `libero_follow` 는 waypoint 마다 도착을 확인한다.
  그러면 Mirobot 이 멈추지 않은 구간에도 라벨에 멈칫거림이 찍히고, 스텝이 카메라 그림과 짝지어지지 않는다.
  시간 기준으로 절대 목표를 따라가며 action 으로 바꾸는 것은 MimicGen 이 정해진 자세열을 재생하는 방식과 같다 ([../W3/CONTROL.md](../W3/CONTROL.md) 3절)
- **0.05초는 action 번역에서 고정이다** — LIBERO policy 는 "action 하나 = 0.05초" 로 배웠다. 간격을 바꾸면 같은 action 이 다르게 움직인다
  (0.1초면 스프링이 두 배 오래 당긴다). **LIBERO 쪽 주기를 Mirobot 에 맞추는 것은 action 뜻을 바꾸는 일이라 action 재학습에 해당한다**
- **Mirobot 기록이 20Hz 여도 격자 맞추기는 필요하다** — Hz 는 평균이고 기록 하나하나의 시각은 흔들린다. 그래서 필요한 조건은
  "정확히 20Hz" 가 아니라 **(1) 기록마다 타임스탬프, (2) 20Hz 보다 촘촘하게** 다
  - 이미 대비돼 있는 것 — `tools/run_gcode.py --stream` 이 `?` 응답마다 `t_s` 를 남기고 20Hz 고정 격자로 묻는다
  - 아직 안 된 것 — 고친 코드로 실물 Hz 를 안 쟀다 (9/21 의 9.3Hz 는 기록 간격 버그였다, `run_gcode.py:115-118`).
    그리고 **카메라와 로봇 기록의 시계가 다르다** — 로봇은 `perf_counter`, 카메라(`robot/camera_bridge.py`)는 `time.time()`.
    같은 격자에 맞추려면 같은 시계로 찍어야 한다

### 1-5. 얻는 것

- **모델이 배운 action 의 의미가 그대로다.** LIBERO 에서 배운 "어떻게 다가가서 집는가" 가 action 수준까지 살아 있을 수 있다
- **정규화 통계도 LIBERO 것을 그대로 쓸 수 있다** — 라벨이 같은 의미라 범위도 비슷할 것이다 (벗어나는지 확인)
- **시뮬 Panda 데이터를 변환 없이 섞을 수 있다** — action 뜻이 같으므로, 실물 Mirobot 데모에 **우리 task 를 LIBERO 에 만들어 Panda 로 뽑은
  롤아웃**을 더해 학습할 수 있다. 실물 데모를 덜 모아도 된다
  - 선례 — Sim-and-Real Co-Training ([arXiv 2503.24361](https://arxiv.org/abs/2503.24361)): 실물 데모(태스크당 20~50)에 닮은 시뮬 데이터를 섞어
    실물 성공률이 평균 38% 올랐다. 조건은 task 정의·성공 기준을 같게, 카메라 위치를 맞추고, 섞는 비율을 조정할 것
  - 걸리는 것 — 시뮬 장면을 **Mirobot 도달 범위(약 315mm)에 맞춰** 만들어야 한다. 실물·시뮬 개수와 비율은 그 작업 때 실험으로 정한다
  - 그래서 action 번역이라면 **LIBERO 에 만든 우리 task 장면**(②·③ 공통)으로 데이터까지 만들 수 있다 — 시뮬에 Mirobot 모델 없이 Panda 로 뽑는다

### 1-6. 치르는 것

- **번역기가 하나 더 들어간다** — 매 chunk 시뮬 Panda 를 돌린다. **policy 추론과 같은 서버에서** 하므로 로봇 노트북에는 robosuite 가 필요 없다 (1-9)
  - 시뮬 Panda 와 실물 Mirobot 이 **어긋나지 않게 맞추는 일**이 생긴다 — Mirobot 이 클램핑 등으로 번역된 자리에 못 가면, 다음 chunk 전에
    시뮬 Panda 를 Mirobot 의 실제 자세로 다시 데려다 놓아야 한다
- **오차가 겹친다** — 좌표 변환(0.3mm 급, 검증됨) + Mirobot `L` ±5mm. 번역기는 진짜 OSC 라 근사가 아니다 (가상 spring-damper 를 쓰면 근사가 하나 더)
- **입력도 Panda 형식이어야 한다** — proprio 손가락 2칸을 Mirobot 서보 1개에서 만들어야 한다 (미정)
- **속도가 안 맞을 수 있다** — 번역된 16자리는 Panda 의 20Hz 간격이다. Mirobot 이 그 속도로 명령을 받아 따라가는지 **아직 모른다.**
  9/21 `--stream` 기록이 9.3Hz 였던 것은 Mirobot 한계가 아니라 기록 간격 버그였고 고쳤다 — 고친 뒤 실물에서는 아직 안 쟀다
  (`tools/run_gcode.py:115-118`. 9/13 `move_and_poll` 은 77Hz). 늦으면 chunk 가 0.8초보다 길어져 다음 관측이 밀린다.
  못 따라가면 번역기는 20Hz 로 계산하고 Mirobot 에는 두 번에 한 번만 보낸다
  → [CHECKLIST.md](CHECKLIST.md) 8절 timestep 질문
- **Mirobot 에 Panda 의 버릇을 입힌다** — Mirobot 은 목표에 딱 서는 로봇인데, 번역기를 거치면 "목표를 앞에 두고 조금씩 따라가는"
  Panda 의 움직임을 흉내 낸다. 부드러워지는 장점일 수도, 불필요한 우회일 수도 있다
- **도달 범위** — Panda 식 목표가 Mirobot 약 315mm 를 넘을 수 있다. 번역 뒤 클램핑이 필요하다

### 1-7. 실물 없이 확인할 수 있는 것

- **번역기 → 좌표 변환 → G-code 를 끝까지 (서버)** — action chunk 를 시뮬 Panda 에 넣고, 읽은 자세를 좌표 변환해 Mirobot 명령이 범위 안에
  나오는지 본다 (`--dry-run`). action 은 `data/follow/*.jsonl` 에 기록된 것을 쓰면 된다 → [CHECKLIST.md](CHECKLIST.md) 2-4, 7-1
- (대안을 쓸 때만) **가상 spring-damper 가 시뮬 Panda 와 맞는가** — 같은 기록의 action 을 모형에 넣어 예측한 위치를 기록된 `eef_pos` 와 댄다

### 1-8. 선례 — Mirage (9/30 조사)

**우리와 같은 출발점에서 action 번역과 같은 방법을 썼다** ([Mirage, arXiv 2402.19249](https://arxiv.org/abs/2402.19249), RSS 2024).

| | Mirage | 우리 |
|---|---|---|
| 출발 policy | robosuite Franka Panda, **OSC 변화량** action | LIBERO Panda (robosuite OSC), 같다 |
| 옮긴 곳 | UR5e · IIWA · Kinova · Sawyer (시뮬), UR5 (실물) | Mirobot (실물) |
| 번역기 | 논문은 **forward dynamics 모형**이라 적었지만, 공개 코드의 시뮬 실험은 **robosuite 안의 Franka 를 옆에서 돌려** 그 손 자세를 넘긴다 (1-9) | 시뮬 Panda (robosuite) — 같다 |
| 실행 | 번역된 자세를 좌표계 변환해 **blocking 제어**(가서 멈춘다)로 간다 | Mirobot `G0` 도 가서 멈춘다 |
| 그림 | cross-painting — Panda 를 그려 넣어 fine-tuning 없이 옮긴다 | Mirobot 그림으로 fine-tuning 한다 |

- **번역기가 필요하다는 실험** — 변화량을 대상 로봇에 그대로 주면(non-blocking) Stack 이 **95% → 36%**, Can 이 98% → 87% 로 떨어졌다
- **"가서 멈추는" 실행으로 됐다** — Mirobot 이 20Hz 를 못 따라가도, 스텝마다 도착하고 넘어가는 실행이 선택지로 남는다 (1-6)
- **한계** — 논문이 "blocking OSC 로 실행하므로 준정적(quasistatic) 작업에 가장 맞는다" 고 적었다. 우리 블록 → 그릇 task 는 여기에 든다

### 1-9. 번역기 — 서버의 시뮬 Panda 로 한다 (9/30)

**떼어 쓸 번역기 라이브러리는 없다.** Mirage 공개 코드([BerkeleyAutomation/mirage](https://github.com/BerkeleyAutomation/mirage), 마지막 커밋 2024-04)는
ROS 2 · Gazebo · 자체 수정 robosuite 를 통째로 요구하는 실험 틀이고, 논문의 forward dynamics 모형 파일은 저장소에 없으며, 최상위에 LICENSE 가 없다.

**그런데 그 코드가 실제로 번역하는 방식이 답이다** — `mirage/benchmark/robosuite/evaluate_policy_demo_source_robot_server.py` 에서
Source Robot(Franka)을 robosuite 안에서 policy action 그대로 실행하고(OSC, non-blocking), 그 손 자세(`compute_eef_pose`)를 Target Robot 에
넘겨 blocking 으로 가게 한다. **번역기가 따로 있는 게 아니라 시뮬 Panda 를 옆에서 같이 돌린 것**이다.

```
서버   policy ─▶ action 16개 ─▶ 시뮬 Panda (robosuite 1.4.0 OSC, LIBERO 학습 때와 같다) ─▶ 스텝마다 손 자세
                                                                                           │ 좌표 변환
로봇 노트북                                                                          Mirobot G0 ◀┘
```

- **배포된 코드를 쓴다** — robosuite 자체다. 서버에 이미 있고, OSC 가 진짜 Panda 반응이라 근사가 없다
- **서버에서 돌린다** — policy 추론이 어차피 서버에 있으니 시뮬 Panda 도 옆에서 돌린다. 로봇 노트북에는 robosuite 가 필요 없다
- **새로 짤 것은 연결 코드뿐** — action 을 시뮬 Panda 에 넣고 손 자세를 읽어 좌표 변환으로 넘긴다. `tools/libero_follow.py` 가 이미 비슷한 일을 한다
- **맞춰 둘 것** — 시뮬 Panda 와 실물 Mirobot 이 어긋나면(클램핑, 도달 실패) 다음 chunk 전에 시뮬 Panda 를 Mirobot 의 실제 자세로 다시 데려다 놓는다
- **가상 spring-damper 는 대안·검산용** — 로봇 노트북 단독으로 돌려야 할 일이 생기거나 속도가 문제일 때

---

## 2. action 재학습 (나) — fine-tuning 에서 다시 배운다

### 2-1. 한 줄로

**Mirobot 데모에서 "Mirobot 이 실제로 어떻게 움직였나" 를 그대로 정답으로 삼아, action 의 뜻을 새로 가르친다.**

```
학습   Mirobot 실물 데모 ── 카메라 그림 + 타임스탬프 찍힌 자세 기록
             │ 기록에서 바로 라벨을 뽑는다                          ← 시뮬 Panda 불필요
             ▼
       (그림, 상태, Mirobot 식 action) 으로 LIBERO policy 를 fine-tuning

실행   모델 ──▶ action 16개 (Mirobot 식) ──▶ Mirobot G0             ← 번역기 없음
```

### 2-2. 출발 가중치는 같다 — LIBERO 에서 무엇이 남나

**action 재학습도 `Cosmos-Policy-LIBERO-Predict2-2B` 에서 출발한다.** 가중치를 버리는 것이 아니라 action 의 뜻 부분만 덮어쓴다.

| LIBERO 에서 배운 것 | action 번역 | action 재학습 |
|---|---|---|
| 입력 배열 (카메라 2대 + proprio + action + 미래 + value 의 9칸) | 쓴다 | 쓴다 |
| 탁상 장면을 보는 눈, 물체 위치 파악 | 쓴다 | 쓴다 |
| 문장으로 대상 고르기 | 쓴다 | 쓴다 |
| action 이 16스텝짜리 7차원 흐름이라는 틀 | 쓴다 | 쓴다 |
| **action 숫자의 뜻** (Panda 식 "목표를 여기 잡아라") | 쓴다 | **덮어쓴다** |

뜻을 덮어써도 사전학습 이득이 남을 수 있다는 선례가 OpenVLA-OFT 다 ([CHECKPOINT.md](CHECKPOINT.md) 4절).

### 2-3. Mirobot 식 action 의 후보

| 후보 | 뜻 | Mirobot 에 줄 때 | 특징 |
|---|---|---|---|
| **다음 스텝의 절대 자세** | "다음엔 여기로 가" | 그대로 `G0` | 목표가 늘 절대 좌표라 오차가 쌓이지 않는다. LIBERO 가 배운 모양(변화량)과는 가장 멀다 |
| **스텝 사이 자세 차** | "이번 스텝에 이만큼 움직여" | 현재 + 차 → `G0` | LIBERO 와 모양이 같다(Δx…Δrz). chunk 안에서 차를 이어 더하니 오차가 쌓일 수 있다 |
| **다음 waypoint 자세** | "다음 경유점은 여기" | 그대로 `G0` | 스크립트 궤적과 잘 맞지만 "한 action = 한 스텝" 틀과 맞지 않는다 |

둘째 후보는 겉모양이 action 번역과 같아 헷갈리기 쉽다. action 번역의 `Δx` 는 "목표를 25mm 앞에 잡아라"(Panda 는 6.5mm 간다)이고,
action 재학습의 `Δx` 는 "6.5mm 움직여라"(Mirobot 은 정말 6.5mm 간다)다.

### 2-4. 시뮬 Panda 데이터는 — 자세만 옮겨 쓴다

action 재학습의 라벨은 "어디로 갔나" 에서 뽑으므로, 시뮬 Panda 롤아웃에서 **action 은 버리고 실제로 간 자세만** 좌표 변환으로 옮겨 라벨을 새로 만든다.

- **Mirobot 이 갈 수 있는 자세인지 걸러야 한다** — Panda 는 관절이 7개라 Mirobot(6개, J5 `+30°` 까지)이 못 가는 자세도 간다
- **움직이는 버릇이 섞인다** — 시뮬 자세열에는 Panda 가 스프링으로 다가가는 속도 변화가 찍혀 있고, 실물 데모는 스텝 모터의 움직임이다
- **그림 차이는 action 번역과 같다**

버릇이 섞이지 않게 하려면 시뮬 장면에 **Mirobot 시뮬 모델**을 세워 뽑아야 한다. 그 모델은 없고 새로 만들어야 한다 —
URDF 변환, 그리퍼 모델(URDF 에 없다), 질량·관절 한계 수정, robosuite 등록 ([CHECKLIST.md](CHECKLIST.md) 4-1·4-2).

## 3. 나란히 놓으면

| | action 번역 | action 재학습 |
|---|---|---|
| 출발 가중치 | LIBERO policy | LIBERO policy (같다) |
| action 의 뜻 | Panda 식을 **유지** | Mirobot 식으로 **덮어쓴다** |
| LIBERO 에서 가져가는 것 | 다섯 줄 모두 (2-2) | 넷 — action 의 뜻은 다시 배운다 |
| 학습 라벨 | 시뮬 Panda 로 만든다 — "시간이 되면 다음으로" 따라가기 (1-4) | Mirobot 기록에서 바로 |
| 실행 경로 | 번역기 → 좌표 변환 → Mirobot | 바로 Mirobot |
| 새로 만들 코드 | 번역기, `libero_follow` 시간 기준 모드 | 라벨 뽑는 코드 |
| **시뮬 Panda 데이터** | **그대로 섞는다** (1-5) | 자세만 옮겨 라벨을 새로. 도달·관절 거르기, 버릇이 섞인다 (2-4) |
| **Mirobot 시뮬 모델** | **필요 없다** — 시뮬에는 Panda | 시뮬 데이터를 제대로 쓰거나 시뮬 평가를 하려면 **필요하다** |
| 스텝 간격 | 0.05초 **고정** | 우리가 정한다 |
| 오차가 끼는 곳 | 좌표 변환 + `L` ±5mm + 시뮬 Panda 와 실물의 어긋남 (번역기는 진짜 OSC, 1-9) | 좌표 변환 + `L` ±5mm |
| proprio | Panda 형식 — 손가락 2칸 ← 서보 1개 대응 필요 | Mirobot 형식으로 둘 수도 있다 |
| 정규화 통계 | LIBERO 것을 쓸 수 있다 | Mirobot 데이터로 새로 |
| 선례 | **Mirage** (RSS 2024) — robosuite Panda 의 OSC 변화량 policy 를 다른 팔로 옮겼다 (1-8) | OpenVLA-OFT (뜻을 덮어쓴 fine-tuning) |
| Mirobot 이 20Hz 를 못 따라가면 | 번역기는 20Hz, Mirobot 에는 솎아서 보낸다 | 간격을 Mirobot 에 맞춘다 |

## 4. 판단

**action 번역으로 간다 (9/30).**

1. **Mirobot 시뮬 모델을 만들지 않는다** — 새로 만드는 비용(그리퍼 모델부터)을 들이지 않기로 했다. action 번역은 시뮬에 Panda 를 그대로 세운다
2. **시뮬 Panda 데이터를 그대로 섞을 수 있다** — LIBERO 에 만들 우리 task 장면(②·③ 공통)에서 Panda 로 데이터를 뽑아 실물 데모를 보탤 수 있다
3. **LIBERO 에서 배운 것을 다섯 줄 모두 쓴다**
4. **같은 출발점(robosuite Panda OSC)에서 같은 방법으로 다른 팔에 옮긴 선례가 있다** — Mirage (1-8)

**다시 볼 조건**

- **시뮬 Panda 와 실물 Mirobot 이 자꾸 어긋날 때** — 번역된 자리에 Mirobot 이 못 가는 일(도달 범위·관절 한계)이 잦으면 동기화가 무너진다
  ([CHECKLIST.md](CHECKLIST.md) 2-4, 7-1). 번역기 자체는 robosuite OSC 라 Panda 반응과 어긋나지 않는다 (1-9)
- **Mirobot 이 20Hz 에 한참 못 미쳐** 솎아 보내기로도 움직임이 무너질 때 ([CHECKLIST.md](CHECKLIST.md) 7-2)

**action 번역을 제대로 했는데도 성능이 나쁠 때의 순서** — Mirage 의 95% → 36% 는 **번역기를 뺐을 때**의 숫자라 action 번역의 근거다 (1-8).
그래도 action 번역이 기대만큼 안 되면 아래 순서로 본다.

1. **번역기와 동기화를 고친다** — 시뮬 Panda 와 실물 Mirobot 이 어긋나는 지점을 찾는다 (1-9 맞춰 둘 것)
2. **실행을 바꾼다** — 스텝마다 도착을 확인하고 넘어간다 (Mirage 의 blocking 실행)
3. **그래도 안 되면 action 재학습** — 실물 데모만 쓰면 action 재학습도 Mirobot 시뮬 모델 없이 된다. 대신 시뮬 Panda 데이터를 섞는 이점은 잃는다

**따라 바뀌는 것**

- 번역기 확인이 "action 번역이 남을 때만" 에서 **반드시 할 것**이 된다 — 9/30 에 번역기를 시뮬 Panda 로 정해, 확인할 것은
  **action → 시뮬 Panda → 좌표 변환 → G-code 가 끝까지 도는지**다 (1-7, 1-9)
- ② 의 **로봇 모델 작업이 필요 없어진다** — ②·③ 은 장면을 어떻게 만드나만 남는다
- **시뮬 Panda 궤적이 Mirobot 이 갈 수 있는 자세인지는 따로 거른다.** 지금 도구는 수평 거리만 본다
  (`tools/run_gcode.py:56`, 280mm 경고). 관절 한계(J5 `+30°` 등)까지 보려면 Mirobot 역기구학 계산이 필요하다 — 시뮬 모델이 아니라 계산식이다

---

## 관련 문서

- [CHECKLIST.md](CHECKLIST.md) — 2-1 같은 action 다른 움직임, 2-4·2-5·2-6 작업 목록
- [CHECKPOINT.md](CHECKPOINT.md) — 출발 가중치 (LIBERO policy)
- [../W3/CONTROL.md](../W3/CONTROL.md) — 두 로봇이 명령을 받아 움직이는 방식, Panda 를 목표까지 보내는 세 방식(3절), LIBERO → Mirobot 경로(4절)
- [../W3/LIBERO_AXES.md](../W3/LIBERO_AXES.md) 2·3절 — action 대비 실제 이동 측정
