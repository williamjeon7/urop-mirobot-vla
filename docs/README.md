# 문서 규칙과 목록
UROP 최소 수행조건 Vision-sensor로 얻어진 이미지를 로봇의 행동 rollout trajectories를 모은 후 기존 VLA를 fine-tuning 하여 real-world task에서 deploy 및 실제상황에서도 vision input만으로 Task라도 달성하는것을 목표

> **기준** · 확인 2026-11-06
> 문서를 어디에 두고 어떻게 쓸지. 아래 목록이 이 저장소 문서의 색인이다.

문서가 늘어나면 "이게 무슨 문서였지", "아직 맞는 내용인가"를 매번 열어서 판단하게 된다.
그걸 파일을 열지 않고도 알 수 있게 하는 것이 아래 규칙의 목적이다.

---

## 목록

### 절차 — 따라 하면 되는 것

| 문서 | 내용 |
|---|---|
| [SETUP_LINUX.md](SETUP_LINUX.md) | 서버→터널→노트북→로봇 3창 실행 절차, 트러블슈팅 |
| [VENDORED.md](VENDORED.md) | 외부 저장소(cosmos-policy, RosForMirobot) 받는 법 |
| [PAPERS.md](PAPERS.md) | 논문 목록과 받는 법 (LIBERO, robosuite, Cosmos Policy). PDF 는 gitignore |
| [MODELS.md](MODELS.md) | 모델 가중치 받는 법, HF 캐시 위치 |
| [W10/DEPLOY_MIROBOT.md](W10/DEPLOY_MIROBOT.md) | Mirobot 최초 설치, 재연결, 매 실험 실행과 영상 저장 |

### 주차별 — 그 주 조사·실험으로 나온 것

| 주차 | 문서 | 내용 |
|---|---|---|
| W2 | [W2/W2_진행사항.md](W2/W2_진행사항.md) | LIBERO 관측/액션 구조, 우리 스키마와의 대응 |
| W2 | [W2/CHECKLIST.md](W2/CHECKLIST.md) | 9/7 미팅 의견 세 항목 확인 목록 |
| W3 | [W3/CHECKLIST.md](W3/CHECKLIST.md) | 9/14 미팅 의견 **작업 목록과 상태·결과** — Mirobot ↔ LIBERO proprio 교환 검증 |
| W3 | [W3/ROTATION.md](W3/ROTATION.md) | **회전 규약과 근거** — 표현 세 가지, 왜 extrinsic XYZ·`xyzw`·`F` |
| W3 | [W3/CONVERSION.md](W3/CONVERSION.md) | **값이 어떻게 바뀌나** — 두 방향 변환 단계와 **코드 지도**(함수·모듈) |
| W3 | [W3/LIBERO_AXES.md](W3/LIBERO_AXES.md) | **LIBERO 측정 원자료** — 축·회전 시험 표, 프레임 회전 `F` 의 근거 |
| W3 | [W3/CONTROL.md](W3/CONTROL.md) | 두 로봇이 명령을 받아 움직이는 방식 비교 — **회전 중심** 포함 |
| W4 | [W4/CHECKLIST.md](W4/CHECKLIST.md) | 9/21 보고에 대한 **교수님 회신 질문 5개** 에 답하는 작업 목록 |
| W4 | [W4/ANSWER.md](W4/ANSWER.md) | **교수님께 보낼 답** — 개념과 판단 근거만. 숫자의 주인은 W3 |
| W5 | [W5/CHECKLIST.md](W5/CHECKLIST.md) | 9/28 보고에서 정한 **작업 목록** — action 의미 맞추기(선결), LIBERO 환경 구성 두 방향 비교, W4 에서 넘어온 것 |
| W5 | [W5/CHECKPOINT.md](W5/CHECKPOINT.md) | **출발 가중치** — LIBERO policy vs video model 비교, 우리는 LIBERO policy 에서 출발 |
| W5 | [W5/ACTION_MEANING.md](W5/ACTION_MEANING.md) | **action 의미** — (가) 실행 단계에서 환산 vs (나) fine-tuning 에서 재학습 |
| W5 | [W5/D405_LIBERO_CAMERA.md](W5/D405_LIBERO_CAMERA.md) | **RGB 카메라 비교** — 카메라 파라미터 설명, 동일 장면의 시야각 비교, D405 공개 RGB 시야각에 따른 투영 변환 실험 |
| W6 | [W6/rgb_blocks/README.md](W6/rgb_blocks/README.md) | RGB 블록 장면·색상별 Task 선택, localhost 실행과 초기 배치 검증 |
| W6 | [W6/PANDA_REPLAY.md](W6/PANDA_REPLAY.md) | Panda 동작 재생 18개, LIBERO → Mirobot 좌표 변환식과 실제 계산 예시, 시뮬 사진·GIF |
| W7 | [W7/CHECKLIST.md](W7/CHECKLIST.md) | D405 컬러 영상 확인과 첫 MP4 촬영의 진행 상태·촬영 기록 |
| W7 | [W7/SETUP_D405_WINDOWS.md](W7/SETUP_D405_WINDOWS.md) | Windows에서 D405 Viewer 다운로드·실행, 컬러 영상 확인과 MP4 시험 녹화 |
| W9 | [W9/CHECKLIST.md](W9/CHECKLIST.md) | 10/28 action plan **3·4번 작업 목록** — 0.05초 격자 시간 동기화, Cosmos LIBERO 로더가 읽는 HDF5 형식과 검증 |
| W9 | [W9/MIROBOT_DATA_COLLECTION.md](W9/MIROBOT_DATA_COLLECTION.md) | **통합 수집 절차** — 색 보정·영상1부터 자동 번호 촬영·0.05초 정렬·서버 HDF5·통계·실제 T5 준비와 검사 |
| W9 | [W9/WORKLOG.md](W9/WORKLOG.md) | **작업 기록** — 시간 순서 목차. 항목마다 왜·한 것·대표 결과·주제 문서 링크. 10/29 부터 |
| W9 | [W9/DATASET_HDF5.md](W9/DATASET_HDF5.md) | **Cosmos LIBERO 형식 HDF5** — 로더가 읽는 형식, 짝 맞추기, 파일 이름 = 지시문, 만드는·확인하는 도구, 시험판 결과, 정규화 통계 문제 |
| W9 | [W9/FOLLOW.md](W9/FOLLOW.md) | **시뮬 Panda 따라가기** — Mirobot 에피소드의 외부 영상·action·proprio. (나) 방식의 이유, 한 칸 앞 목표, proprio 변환(B'), 따라가기 오차와 남은 결정 |
| W9 | [W9/WHY_VLA.md](W9/WHY_VLA.md) | **왜 VLA 인가** — 3색 블록은 직접 짠 코드로도 풀리는데 VLA 를 쓰는 이유, 직접 짠 코드의 역할. 미결: 직접 짠 버전을 기준선으로 잴지 |
| W9 | [W9/ISSUES.md](W9/ISSUES.md) | **걸리는 점** — Mirobot 손목 카메라 화면이 돌고 기움(Panda 와 다름), pick up 정교화, 변환 코드 정확도(블록 좌표), 실물 기록의 빈칸 |
| W9 | [W9/MIROBOT_COORDINATES.md](W9/MIROBOT_COORDINATES.md) | **좌표 규약·실측** — Mirobot·종이·Depth 좌표와 실제 기준점 측정·카메라 등록 |
| W9 | [W9/FINETUNE.md](W9/FINETUNE.md) | **1차 파인튜닝** — Panda 90 + Mirobot 10 합친 데이터, tmux 실행 명령, GPU 2개 vs 4개 시간 측정, 2000 step 결정, 본학습 상태, 평가 경로(있는 것·빠진 것) |
| W10 | [W10/POLICY_RUN.md](W10/POLICY_RUN.md) | **정책 실행 도구** — 관측·명령 계산과 follow action 변환의 조사 기록. 현재 실물 실행 절차는 DEPLOY_MIROBOT.md |
| W10 | [W10/MIROBOT_EXPERIMENT.md](W10/MIROBOT_EXPERIMENT.md) | **실험 계획** — Mirobot demonstration으로 Cosmos Policy 파인튜닝 후 실물 블록 집기. 논문 실험 절 형식의 설정·평가 절차·지표·결과표 |
| W10 | [W10/TRAINING_RESULT.md](W10/TRAINING_RESULT.md) | **학습 완료 기록** — 시연 90개·4,000 update 정상 종료, 마지막 loss·소요 시간·체크포인트 저장 확인 |
| W10 | [W10/HDF5_ALIGNMENT.md](W10/HDF5_ALIGNMENT.md) | **정렬 기준과 미통과 녹화** (노트북, 11/04) — 70 ms 기준, 60개 중 55개 통과, 미통과 5개 |
| W10 | [W10/DATA_CHECK.md](W10/DATA_CHECK.md) | **학습 데이터 점검** (서버, 11/05) — 55개를 HDF5 로 바꿔 Cosmos 로더·학습 설정까지 통과, 새 녹화 때 다시 돌리는 명령, 학습 전 라벨 방식 결정 |
| W10 | [W10/TRAINING.md](W10/TRAINING.md) | **학습 진행** — 정할 것(라벨 방식·평가용 배치·step 수), 데이터 최신화, 학습 명령, 스텝별·색별 비교 (오프라인은 가능, 실물 성공률은 실행 루프 필요) |
| W10 | [W10/WORKLOG.md](W10/WORKLOG.md) | **작업 기록** — 시간 순서 목차. 항목마다 왜·한 것·대표 결과·주제 문서 링크 |

### 계획 — 왜 이렇게 하는지, 무엇을 기준으로 판단하는지

| 문서 | 내용 |
|---|---|
| [plan/UROP_프로젝트_계획.md](plan/UROP_프로젝트_계획.md) | 설계 근거, 자원·정책 선택 이유 |
| [plan/운영기준.md](plan/운영기준.md) | 게이트 기준, 채점 루브릭, 흔한 함정 |

### 기록 — 날짜별

| 문서 | 내용 |
|---|---|
| [meetings/](meetings/) | 주간 미팅. 파일 하나 = 미팅 하나 |

> 셋이 어긋나면 **`meetings/` 가 최신**이다. 방향은 매주 미팅에서 정해진다.

---

## 새 문서를 만들 때

### 1. 어디에 둘지

| 성격 | 위치 |
|---|---|
| 그 주 조사·실험으로 나온 것 | `docs/W<주차>/` |
| 주차와 무관하게 계속 찾게 되는 절차 | `docs/` |
| 왜 이렇게 하는지, 판단 기준 | `docs/plan/` |
| 미팅에서 나온 것 | `docs/meetings/` |

주차 번호는 `plan/UROP_프로젝트_계획.md` 의 W1~W14 표기를 따른다.

`docs/` 루트에는 **주차와 상관없이 계속 열게 되는 것만** 둔다. 로봇을 돌리다 막혔을 때
`SETUP_LINUX.md` 를 "몇 주차에 만들었더라" 하고 찾게 되면 안 되기 때문이다.
반대로 특정 주의 조사 결과를 루트에 두면 루트가 금세 뒤죽박죽이 된다.

주차 폴더의 문서가 계속 참조된다 싶으면 그때 루트로 올린다. 옮기면
`grep -rn "<파일명>" README.md docs/` 로 참조를 같이 고친다.

### 2. 이름

- `docs/`, `docs/plan/`, `docs/W<주차>/` — **대문자 스네이크**, 주제 하나.
  `LIBERO.md`, `SETUP_LINUX.md`
  - 한글 이름도 쓴다 (`운영기준.md`). 다만 한 폴더 안에서는 통일한다.
- 주차 폴더 자체 — **`W2`**, `W10` 처럼 번호만.
- `docs/meetings/` — **`YYYY-MM-DD.md`**. 미팅 날짜.

### 3. 머리말 — 필수

제목 바로 아래에 인용 블록으로 세 줄을 넣는다.

```markdown
# LIBERO — 관측 · 액션 구조

> **참조** · 확인 2026-09-09 · 기준 `cosmos-policy@18a2acc`
> LIBERO 의 관측/액션 구조와 우리 스키마(`common/schema.py`)의 대응 관계.
```

| 항목 | 쓰는 법 |
|---|---|
| 성격 | `절차` / `참조` / `기준` / `설계` / `기록` 중 하나 |
| 확인 | 내용을 마지막으로 확인한 날짜 (`YYYY-MM-DD`) |
| 기준 | 무엇을 보고 썼는지 — 커밋 해시, 버전, 장비. 없으면 생략 |
| 한 줄 설명 | 파일을 열지 않아도 무슨 내용인지 알 수 있게 |

**`확인` 날짜가 핵심이다.** 외부 저장소나 모델은 바뀌는데 문서는 안 바뀐다.
날짜가 오래됐으면 "믿기 전에 확인해야 한다"는 신호로 읽는다.

### 4. 목록에 추가

이 파일의 목록 표에 한 줄 추가한다. 여기 없는 문서는 없는 것과 같다.

### 5. 작업 기록과 주제 문서 (10/29)

한 일을 나중에 다시 만들거나 이유를 설명할 수 있게, 주차 폴더에 두 종류로 남긴다. 적는 기준은
**"나중에 이 결과를 다시 만들거나, 왜 이렇게 됐는지 설명해야 할 때 필요한가"** 다.

| 문서 | 무엇 | 형식 |
|---|---|---|
| `W<주차>/WORKLOG.md` | 그 주에 한 작업의 **시간 순서 목차** | 항목 하나 = 작업 단계 하나, 3–5줄 — **왜**(필요했던 이유·배경) · 한 것 · 대표 결과 · 주제 문서 링크 |
| `W<주차>/<주제>.md` | 자세한 설명 | 무엇을 하는지, 왜 이렇게 설계했는지, 선택지와 결정(누가 정했는지 · 확인 없이 정한 것 표시), 실행법, 결과 표 |

- 주제 문서는 작업 단계마다가 아니라 **주제마다** 만든다. WORKLOG 한 항목(약 10줄)에 안 들어가거나, 선택지 비교·결정이 있거나,
  다른 주차·담당이 다시 찾아볼 내용일 때
- 찾아본 과정, 바로 고친 사소한 실수, 다른 문서가 주인인 사실은 적지 않는다 (링크만)
- 작업 목록(`CHECKLIST.md`)의 `→` 에는 한 줄 결과와 주제 문서 링크만 둔다
- 새로 만든 코드의 맨 위 설명에는 **배경(왜 만들었나)** 한 줄을 넣는다

---

## 문서를 고칠 때

- **한 사실의 주인은 한 문서다.** 같은 내용을 두 곳에 적지 말고, 주인을 정해 나머지는 **링크**로 건다.
  주인은 그 사실이 나온 곳이다 — 측정은 측정 기록 문서, 작업 결과는 작업 목록, 규약은 규약 문서.
- 내용을 확인하거나 갱신했으면 **머리말의 `확인` 날짜를 갱신**한다.
- 틀린 내용을 발견하면 고치거나, 못 고치면 **틀렸다고 적어 둔다.**
  방치된 틀린 문서는 없는 문서보다 나쁘다.
- 문서를 지울 때는 참조하는 다른 문서를 같이 고친다.
  `grep -rn "<파일명>" README.md docs/` 로 확인한다.
  지운 내용은 git 히스토리에 남으므로 필요하면 `git show <커밋>:<경로>` 로 꺼낸다.
