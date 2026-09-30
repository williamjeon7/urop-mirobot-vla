# 출발 가중치 — LIBERO policy 냐 video model 이냐

> **설계** · 확인 2026-09-30 · 기준 `cosmos-policy@18a2acc`, 논문 arXiv 2601.16163v1, HuggingFace 모델 카드(9/30)
> fine-tuning 을 시작할 가중치 두 후보(`Cosmos-Policy-LIBERO-Predict2-2B`, `Cosmos-Predict2-2B-Video2World`)가 무엇이고 어떻게 다른지, 우리는 어느 쪽에서 출발하는지.

작업 목록은 [CHECKLIST.md](CHECKLIST.md) 2-3절이다. 여기는 **비교와 판단의 근거**를 둔다.
코드 경로는 `cosmos-policy/cosmos_policy/` 기준, 논문은 `papers/cosmos.pdf` ([../PAPERS.md](../PAPERS.md)).

## 0. 결론 먼저

**`Cosmos-Policy-LIBERO-Predict2-2B` 에서 출발한다. `Cosmos-Predict2-2B-Video2World` 는 대안으로 둔다.**

1. **입력 배열이 우리 구성과 같다** — 카메라 2대(3인칭 1 + 손목 1) + proprio + 문장. video model 에서 출발하면 이 배열부터 배워야 한다
2. **탁상 조작을 이미 안다** — 150개(계획서 6절)라는 적은 데이터에서는 가까운 데서 출발하는 편이 유리할 것이다
3. **action 의미가 달라도 사전학습 이득이 남는다는 선례가 있다** — OpenVLA-OFT (4절)

**걸리는 것** — 이 모델이 배운 action·proprio 는 Panda 기준이다. 유지할지((가)) 덮어쓸지((나))는 [CHECKLIST.md](CHECKLIST.md) 2-4·2-5 에서 정한다.
**어느 쪽이든 먼저 풀 것** — HF 에서 video model 저장소 약관 동의. tokenizer 가 거기 있어서 LIBERO 에서 출발해도 필요하다 (6절).

---

## 1. 두 가중치는 무엇인가

**구조는 같고 가중치만 다르다.** LIBERO policy 는 video model 을 구조 변경 없이 fine-tuning 한 것이다 (논문 4절, "no architectural changes").

```
Cosmos-Predict2-2B-Video2World ──── LIBERO 데모로 전체 fine-tuning ────▶ Cosmos-Policy-LIBERO-Predict2-2B
  영상 생성 모델                     H100 64장 · 48시간 · 40K step           로봇 policy
  그림 + 문장 → 이어지는 영상                                                 그림 2장 + proprio + 문장
                                                                              → action 16개 + 미래 그림 + value
```

### 1-1. `Cosmos-Predict2-2B-Video2World` — 영상 생성 모델

| | |
|---|---|
| 무엇 | latent video diffusion model — **시작 그림과 문장을 받아 이어지는 짧은 영상을 만든다** (논문 3절) |
| 구성 | 2B diffusion transformer(DiT) + Wan2.1 VAE tokenizer(그림 ↔ latent) + T5-XXL(문장) |
| 변형 | 480p/720p × 10/16fps. cosmos-policy 는 **`model-480p-16fps.pt`** 를 초기값으로 쓴다 (`config/experiment/cosmos_policy_experiment_configs.py:148`) |
| 로봇 | **본 적 없다** — action·proprio·value 라는 개념이 없다 |
| 라이선스 | NVIDIA Open Model License (상업 이용 가능) |
| 접근 | **gated** — HF 에서 연락처 공유에 동의해야 받는다 (모델 카드) |

### 1-2. `Cosmos-Policy-LIBERO-Predict2-2B` — LIBERO 로봇 policy

| | |
|---|---|
| 무엇 | 위 모델을 LIBERO 네 suite 데모(suite 당 500개)로 **전체 가중치** fine-tuning 한 policy. 실패 데모(10~20%)는 policy 학습에서 뺐다 (논문 5.1절) |
| 입력 | 3인칭(agentview)·손목(eye-in-hand) **224×224** 각 1장, **proprio 9차원**(그리퍼 2 + eef 위치 3 + 쿼터니언 4), 문장 |
| 출력 | **action 16 × 7**(Panda OSC 변화량 6 + 그리퍼 1), 16스텝 뒤의 두 카메라 그림과 proprio, value |
| latent 배열 | blank · proprio · wrist · primary · action · 미래 proprio · 미래 wrist · 미래 primary · value — **9칸** (`cosmos_policy_experiment_configs.py:116`) |
| 학습 | 40K step, H100 64장, global batch 1920, 48시간 (논문 A.2.2) |
| 성능 | LIBERO 평균 **98.5%** |
| 추론 | GPU 1장 6.8GB (모델 카드). H100 에서 chunk 하나에 0.61초 (논문 A.4.2) |
| 라이선스 | NVIDIA One-Way Noncommercial (NSCLv1) — **연구용**. 우리 용도에는 문제없다 |
| 파일 | 가중치 3.7GB + T5 임베딩 + action 정규화 통계 ([../MODELS.md](../MODELS.md)) |

---

## 2. 나란히 놓으면

| | LIBERO policy | video model |
|---|---|---|
| 배운 것 | 영상 + **Panda 조작** (action 까지) | **영상만** |
| action | Panda OSC 변화량으로 배웠다 — 한 스텝에 목표의 약 26%만 간다 ([CHECKLIST.md](CHECKLIST.md) 2-1) | 모른다 |
| 입력 배열 | **9칸 — 카메라 2대. 우리와 같다** | 없다 — 데이터에 맞춰 새로 배운다 |
| 장면 | 탁상 조작 (Spatial·Object·Goal·Long) | 일반 영상 |
| 문장 ↔ 물체 | "X 를 집어 바구니에" 를 이미 배웠다 (LIBERO-Object) | 없다 |
| step 당 학습 비용 | **같다** — 구조가 같다 | 같다 |
| 필요한 step 수 | 적을 것으로 **예상** — 확인 안 됨 | 논문의 새 로봇 경로. ALOHA 185개에 H100 8장 · 48시간 · 50K step (논문 A.2.4) |
| 선례 | Cosmos 안에는 없다. VLA 전반에는 있다 (4절) | 논문의 세 checkpoint 전부 (실물 ALOHA 포함) |
| 라이선스 | 연구용 | 상업 가능 |
| 접근 | 모델 카드상 gated 아님. 단 tokenizer 는 video model 저장소에서 받는다 (6절) | gated |

---

## 3. 우리 프로젝트에서 — 얻는 것과 잃는 것

### LIBERO policy 에서 출발하면

- **얻는 것**
  - 입력 배열이 우리 구성(고정 카메라 1 + 손목 1)과 같다. ALOHA·RoboCasa 는 카메라 3대라 11칸이다
  - 탁상에서 물체를 집어 옮기는 영상과, 문장으로 대상을 고르는 구조를 이미 안다 — 우리 task(색 블록 → 그릇, 계획서 5절)가 LIBERO-Object 를 본떴다
  - 7차원 action 틀이 같다
- **잃는 것 / 걸리는 것**
  - action 의미가 Panda 기준이다 — 같은 값이 Mirobot 에서는 약 4배 크게 움직인다 ([CHECKLIST.md](CHECKLIST.md) 2-1)
  - proprio 도 Panda 기준(파지점 위치 + 쿼터니언 + 손가락 2칸)이다. 위치·자세는 W3 변환으로 만들 수 있다 (파지점 기준, 9/30 회신). 손가락 2칸 vs Mirobot 서보 1개는 아직 정해지지 않았다
  - 정규화 통계는 어느 쪽이든 Mirobot 데이터로 새로 잡는다 — LIBERO 통계를 그대로 쓰는 것은 (가) 뿐이다

### video model 에서 출발하면

- **얻는 것** — Panda 습관이 없다. 논문이 새 로봇마다 쓴 경로 그대로다
- **잃는 것** — 입력 배열, 탁상 조작, 문장-물체 대응을 **우리 데이터 150개로** 처음부터 배워야 한다.
  ALOHA 는 185개로 됐지만 H100 8장 48시간이 들었다. 우리 GPU 는 24GB 공유다 (계획서 2절)

---

## 4. 선례 — action 의미가 다른 로봇으로 옮긴 경우

**OpenVLA-OFT** ([arXiv 2502.19645](https://arxiv.org/abs/2502.19645)) — Cosmos Policy 코드의 뿌리다 (`constants.py` 머리말).

| | 사전학습 (OpenVLA) | fine-tuning 대상 (ALOHA) |
|---|---|---|
| 팔 | 단일 | 양팔 |
| 카메라 | 3인칭 1대 | 3대 |
| proprio | 없음 | 관절 14차원 |
| 제어 | 3~10Hz | 25Hz |
| action | **상대 end-effector** | **절대 관절각** |

이렇게 다 다른데도 태스크당 20~300 데모로 fine-tuning 해 **처음부터 학습한 ACT·Diffusion Policy 보다 높았다.**
→ action 의미를 덮어써도(우리의 (나)) 사전학습 이득이 남을 수 있다.

**Cosmos Policy 안에서는 선례가 없다** — 세 checkpoint 모두 video model 에서 따로 출발했고, 공식 문서에도 새 로봇을
어느 checkpoint 에서 시작하라는 안내가 없다. OpenVLA-OFT 는 action 을 MLP head 로 내고 Cosmos 는 latent 에 채우므로,
**구조가 달라 그대로 옮겨지는 근거는 아니다.**

---

## 5. 판단과 바꿀 조건

**LIBERO policy 에서 출발한다.** 근거는 0절 세 가지.

**확인 못 한 것** — "가까운 데서 출발하니 덜 든다" 는 예상이다. 확인하려면 계획서의 W3 게이트(학습 소요 역산)를 돌려야 한다.

**video model 로 바꿀 조건** — 아래가 보이면 다시 본다. 판단은 **같은 데이터, 같은 step 수**로 두 출발점을 나란히 돌려 비교할 때만 공정하다.

- fine-tuning 뒤에도 Panda 식 움직임(목표를 앞에 두고 조금씩 따라가는 버릇)이 남아 Mirobot 에서 지워지지 않는다
- 같은 step 에서 action loss 가 video model 출발보다 늦게 내려간다

---

## 6. 먼저 풀 것 — HF 접근

**tokenizer 가 video model 저장소에 있다.** LIBERO policy 에서 출발해도 코드가 그림 ↔ latent 변환기(Wan2.1 VAE)를
`nvidia/Cosmos-Predict2-2B-Video2World/tokenizer/` 에서 받는다 (`config/defaults/tokenizer.py:27`, `tokenizers/wan2pt1.py:208,211`).
이 저장소는 gated 다 (1-1).

- **9/28 의 `GatedRepoError: 401` 은 이 tokenizer 에서 났을 가능성이 있다** — 추정이다. LIBERO policy 모델 카드에는 gated 표시가 없다.
  [../W4/CHECKLIST.md](../W4/CHECKLIST.md) 9절 곁가지는 "LIBERO policy 가 gated" 로 적었는데, 서버 로그(`codex_robot_icl_20260928/summary.json`)에서 **어느 파일을 받다 막혔는지** 확인한다
- **할 일** — HF 계정으로 video model 저장소 약관에 동의하고, 서버에 토큰을 둔다. 어느 출발점이든 이게 먼저다

---

## 관련 문서

- [CHECKLIST.md](CHECKLIST.md) — 2-3 이 이 문서의 작업 목록, 2-4·2-5 가 (가)·(나), 7절 곁가지가 HF 접근
- [../MODELS.md](../MODELS.md) — 가중치 받는 법, 캐시 위치
- [../plan/UROP_프로젝트_계획.md](../plan/UROP_프로젝트_계획.md) — 2절 자원, 4절 정책 선택·자원 제약, 6절 액션 표현·데이터 예산
- [../PAPERS.md](../PAPERS.md) — Cosmos Policy 논문
- 모델 카드 — [Cosmos-Policy-LIBERO-Predict2-2B](https://huggingface.co/nvidia/Cosmos-Policy-LIBERO-Predict2-2B), [Cosmos-Predict2-2B-Video2World](https://huggingface.co/nvidia/Cosmos-Predict2-2B-Video2World)
