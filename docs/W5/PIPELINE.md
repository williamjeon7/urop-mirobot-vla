# 파이프라인 — policy 에서 Mirobot 까지

> **절차** · 확인 2026-10-01 · **갱신 2026-10-05** · 기준 `cosmos-policy@18a2acc`, `nvidia/Cosmos-Policy-LIBERO-Predict2-2B@cb689ec`, 서버(OASYS)
> action 번역으로 정한 뒤(9/30) 그 길을 실제로 이어 붙이고 어디까지 도는지 적는다. `→` 뒤 빈칸은 **미리 채우지 않는다**.

**왜 action 번역인가, 왜 번역기가 시뮬 Panda 인가**는 여기 적지 않는다 — 판단은 [ACTION_MEANING.md](ACTION_MEANING.md) 1-9, 출발 가중치는 [CHECKPOINT.md](CHECKPOINT.md).
여기는 **만든 것, 돌리는 법, 확인한 것과 아직 못 한 것**만 둔다. 작업 목록과 진행 표시는 [CHECKLIST.md](CHECKLIST.md) 2-4 · 7-1.

## 0. 한 줄로

```
policy ──action──▶ 번역기 ──손 자세──▶ 좌표 변환 ──▶ Mirobot G0 ──▶ 실물
(Cosmos)   변화량     시뮬 Panda          파지점 기준     절대 좌표
           16개씩     (robosuite OSC)    common/workspace
```

**지금 어디까지 왔나 (10/1)** — 서버에서 **policy 가 돌고**(LIBERO-Spatial 10/10), **번역기가 돌고**(기록된 action 1157개 → G0 1157줄, 경고 0),
**좌표 변환이 파지점 기준으로 서버에서도 맞는다.** **정책이 낸 action 도 번역기를 지난다** — 정책이 돈 장면에서 10개 중 8개가
같은 결과로 재현되고, **Mirobot 도달 범위는 10개 전부 크게 넘는다**(수평 최대 494~567mm, 변위를 약 1/4 로 줄여야 들어간다). **짝을 X 120 으로 당기고 배율 0.44 로 줄이면 10개 모두 들어간다** (후보, 4-4). 남은 것은 **실물**이다.

| 토막 | 상태 |
|---|---|
| policy | **돈다** (3-2) |
| 번역기 | **돈다** — 단, 지금까지 넣은 action 은 정책 출력이 아니다 (3-3) |
| 좌표 변환 | **맞는다** — 파지점 기준, 서버 확인 (3-1) |
| 정책 action → 번역기 | **돈다 — 1:1 로는 넘치고, 후보 짝·배율이면 들어간다** (4-1, 4-4) |
| 실물 | **아직** (4절) |

---

## 1. 토막마다 무엇을 보장하나

| 토막 | 들어오는 것 | 나가는 것 | 보장하는 것 | 보장하지 **않는** 것 |
|---|---|---|---|---|
| **policy** | 카메라 2장 + proprio 9칸 + 지시문 | action 16개 (Panda OSC 변화량) | LIBERO 장면에서 학습대로 움직인다 | 우리 과제·우리 장면 |
| **번역기** | action | 스텝마다 Panda 손 자세(파지점) | 그 action 을 받은 Panda 가 **실제로 어디로 가는지** — 학습 때와 같은 컨트롤러라 근사가 없다 | 실물이 그 자리에 있다는 것 (열린 고리) |
| **좌표 변환** | Panda 자세 | Mirobot `G0 X Y Z A B C` | 같은 파지점 자세를 Mirobot 좌표로 옮긴다 | 도달 범위 안이라는 것, 실물이 그대로 간다는 것 |
| **Mirobot** | G0 줄 | 움직임 | 받은 줄을 거부·알람 없이 실행했다 | **어디로 갔는지** — `?` 는 측정이 아니다 (W4 ANSWER ④ 4절) |

**번역기가 하는 일은 하나다 — "action → 자세"**. action 은 "지금 자리에서 이만큼" 이라 좌표 뜻이 없어서, Panda 가 실행해 봐야 자세가 나온다.
그래서 **정책이 끼었을 때만** 필요하다. Mirobot 좌표를 Panda 로 옮기는 반대 방향(W3)에는 action 이 없어 번역기가 낄 자리가 없다.

---

## 2. 돌리는 법 (서버, `cosmos-policy/.venv`)

```bash
# 1) policy — LIBERO 장면에서 돌리며 action 을 남긴다
#    action 은 화면에 스텝마다 찍히고(`t: … action: [ … ]`), --data_collection True 면 HDF5 로도 남는다
cd cosmos-policy && CUDA_VISIBLE_DEVICES=0 .venv/bin/python -m cosmos_policy.experiments.robot.libero.run_libero_eval \
  --config cosmos_predict2_2b_480p_libero__inference_only \
  --ckpt_path nvidia/Cosmos-Policy-LIBERO-Predict2-2B --config_file cosmos_policy/config/config.py \
  --dataset_stats_path nvidia/Cosmos-Policy-LIBERO-Predict2-2B/libero_dataset_statistics.json \
  --t5_text_embeddings_path nvidia/Cosmos-Policy-LIBERO-Predict2-2B/libero_t5_embeddings.pkl \
  --task_suite_name libero_spatial --num_trials_per_task 1 --seed 195 --deterministic True \
  --available_gpus "0" --local_log_dir <로그 폴더>

# 2) 번역기 — action → 시뮬 Panda → 좌표 변환 → G-code
python -m tools.action_to_gcode --log <action 기록> [--every N] [--out <파일>.gcode]

# 3) 범위 확인 — 보내지 않고 표만
python -m tools.run_gcode <파일>.gcode --dry-run
```

**`action_to_gcode --log` 이 받는 세 형식**

| 형식 | 무엇 |
|---|---|
| `.jsonl` | `action` 칸이 있는 줄 — `libero_follow` · `action_to_gcode` 기록 |
| `.hdf5` | `run_libero_eval --data_collection True` 의 episode 파일 (`actions`) |
| 그 밖 | eval 의 화면 출력 — `t: … action: [ … ]` 줄을 긁는다. 재실행 없이 쓰려고. **소수 셋째 자리로 반올림돼 있다** (4-1) |

**정책 action 은 정책이 돈 장면에서 번역한다** — `--suite` · `--task-id`(eval 은 태스크 0 부터 차례로) · `--init-state`(1회차 = 0) ·
`--episode`(한 실행에 여럿일 때). 대기 스텝은 기록에서 읽는다 (eval 은 10).

```bash
python -m tools.action_to_gcode --log <eval 화면 출력> --episode 5 --suite libero_spatial --task-id 4 --init-state 0 \
    --mapping candidate          # 짝 X 120 · 배율 0.44 (후보, 4-4). 빼면 홈 · 배율 1
```

**짝과 배율은 파일에 적힌다** — 머리말 `; pair X… Y… Z… scale …`. 읽는 도구가 그대로 따라 읽으니 따로 맞춰 줄 필요가 없다.

**남는 것** — G-code(머리말 `; point grip`, 줄마다 `; c<chunk>s<step>` 라벨), `data/translate/<날짜>-<시각>.jsonl`(스텝마다 action · Panda 자세 · Mirobot 명령).

**처음 돌리기 전에** — policy 는 HF 에서 **세 파일**을 받는다. 출발 가중치만이 아니다 (3-2).

---

## 3. 확인한 것

### 3-1. 바탕 — 테스트와 파지점 전환 (10/1)

- **테스트 30개 통과** — `tests.test_workspace` 11 · `test_rotation` 13 · `test_servo` 6. 서버 scipy 로 **T12 도 돈다**
- **파지점 전환을 서버에서 한 번** — 9/30 에 바꾸고 LIBERO 가 있는 곳에서는 처음이다

  | 확인 | 결과 |
  |---|---|
  | 옛 기록 `drift_check` (`2026_09_21-09_45_06`) | 머리말 **`point flange`** 로 읽힌다. 끝에서 끝 **2.092mm · 2.496mm · 0.346°** — 전환 전과 같다 |
  | grip G-code 생성 (9/17 absolute) | 머리말 **`; point grip`**. 자세는 그대로, 위치만 기운 각에 따라 **0.3~10.3mm** 달라진다 |
  | 그 파일을 `libero_follow` 로 | **7/7 도착**, 137스텝, 최대 1.90mm · 0.34°. 끝에서 끝 **1.898mm** = 추종 잔차와 같다 → 변환 왕복 손실은 반올림 수준 |
  | `roundtrip_check compare` (9/20 실물) | `point flange` 로 읽어 **최대 0.30mm · 0.05°** — 기존 값 그대로 |

  **옛 파일이 그대로 읽힌다** — 표시 없는 9/17~9/28 파일은 전부 플랜지로 읽혀 숫자가 안 변했다

### 3-2. policy 토막 — 서버에서 처음 돌았다 (10/1)

- **9/28 의 401 은 tokenizer 였다** — `nvidia/Cosmos-Predict2-2B-Video2World/tokenizer/tokenizer.pth`. 서버에 **토큰이 아예 없어서** 익명 요청이 거절됐다.
  그 저장소는 `gated="auto"` 라 약관 동의 즉시 열린다. LIBERO policy 저장소는 `gated=False`. 자세한 것은 [CHECKPOINT.md](CHECKPOINT.md) 6절
- **policy 가 받는 파일은 셋이다** — 출발 가중치만으로는 안 돈다

  | 파일 | 크기 | 왜 |
  |---|---|---|
  | `Cosmos-Policy-LIBERO-Predict2-2B.pt` | 3.7 GB | 출발 가중치 (9/9 부터 캐시에 있었다) |
  | `Cosmos-Predict2-2B-Video2World/tokenizer/tokenizer.pth` | 0.5 GB | 그림 ↔ latent. 경로가 코드에 박혀 있다 (`config/defaults/tokenizer.py:27`) |
  | `Cosmos-Predict2-2B-Video2World/model-480p-16fps.pt` | 3.9 GB | `…libero__inference_only` config 가 베이스 video model 을 먼저 세운다 |

  - 같은 실행이 **`Cosmos-Policy-ALOHA-Predict2-2B.pt` 도 받았다** — 쓰지 않는 체크포인트다. config 레지스트리가 끌어오는 것으로 보인다 (추정)
- **LIBERO-Spatial 10태스크 × 1회 — 10/10 성공 (100%)**. 모델 카드 98.5% 와 맞는다. **이 프로젝트에서 정책이 로봇을 움직인 첫 실행이다**
  - action **1019개**, 에피소드 10개 (길이 76~128스텝). 스텝 10 부터 찍힌다 — 앞 10스텝은 대기(`NUM_STEPS_WAIT`)
  - 영상 `cosmos-policy/rollouts/2026_10_01/` (에피소드마다 일반 · 미래 예측 두 개)
  - 끝의 `EGLError: EGL_NOT_INITIALIZED` 는 종료 때 렌더러를 정리하며 나는 경고다. exit 0

### 3-3. 번역기 — `tools/action_to_gcode.py` (10/1)

- **같은 action → 같은 궤적** — 9/28 추종 기록의 action 을 다시 넣으면 기록된 자세와 **차이 0.000mm** (위치·쿼터니언 모두). 시뮬이 결정론적이다
- **끝까지 돈다** — 같은 기록의 action **1157개 → G0 1157줄**
  `trajectories/2026_10_01-translated-mirobot-origin-x4.gcode`

  | | 값 | 경고선 |
  |---|---|---|
  | 수평 최대 | **250.9mm** | 280 |
  | 각도 최대 | **25.1°** | 30 |
  | Z 최저 | **173.0mm** | — |

  `run_gcode --dry-run` **경고 없음**. 9/28 실물이 이미 돈 동작(A 궤적)과 같은 자리들을 지난다 — 그때 수평 최대 258mm
- **세 입력 형식** — eval 화면 출력 형식으로 만든 가짜 기록에서 jsonl 과 **같은 줄**이 나온다

**다만 이 1157개는 정책 출력이 아니다** — 우리 추종 루프가 만든 얌전한 action 이다. 그래서 이건 **배관 확인**이고 번역기의 진짜 시험은 4-1 이다.

### 3-4. 정책 action 은 이만큼 크다 (10/1, 에피소드 5 · 128스텝)

*"pick up the black bowl in the top drawer of the wooden cabinet and place it on the plate"*

| | 최소 | 최대 | 절대 평균 |
|---|---|---|---|
| `dx` | −0.768 | +0.954 | 0.345 |
| `dy` | −0.425 | +0.898 | 0.281 |
| `dz` | −0.957 | +0.955 | **0.505** |
| `drx` | −0.080 | +0.026 | 0.015 |
| `dry` | −0.234 | +0.164 | 0.053 |
| `drz` | −0.115 | +0.253 | 0.061 |
| 그리퍼 | −1.006 | +1.007 | 1.002 |

- 위치 성분이 **±0.95 까지** 간다 — 액션 1.0 이 50mm 라 한 스텝 목표가 최대 약 48mm 다. 3-3 의 추종 루프 action 보다 훨씬 크다
- 회전은 작다 — 절대 평균 0.015~0.061 (액션 1.0 = 0.5rad)
- 그리퍼가 **±1 을 살짝 넘는다** (±1.006) — 학습 통계로 되돌린(unnormalize) 값이라 그렇다. 컨트롤러가 잘라 쓴다 (추정)

---

## 4. 아직 확인 안 한 것

### 4-1. 정책 action 을 번역기에 — 번역기의 진짜 시험

- [ ] **같은 장면 · 같은 초기 상태로 돌려야 한다** — `action_to_gcode` 의 기본은 `libero_90` `KITCHEN_SCENE1` 의 초기 상태 0 이다.
  정책은 `libero_spatial` 의 다른 장면에서 돌았다. 다른 장면·다른 시작 자세에 같은 action 을 넣으면 **그 정책이 간 궤적이 아니다**.
  `--suite` · `--task-name` 에 더해 **초기 상태 번호**를 받아야 한다 (eval 은 `seed 195`, trial 0)
  → **고쳤다 (10/1).** `--task-id` · `--init-state` · `--episode` 를 붙였고, eval 이 장면을 세우는 순서
  (`env.seed(0)` → `reset()` → `set_init_state` → 대기)와 같다. **대기 동작을 eval 과 똑같이** 바꿨다 — 그리퍼 정확히 −1.
  정책 action 의 그리퍼는 −1.005 처럼 넘쳐서, 첫 action 에서 빌려 오던 이전 방식은 대기 중에도 다른 값을 넣었다.
  대기 스텝 수는 기록의 첫 `t` 에서 읽는다 (eval 은 대기 중엔 안 찍으므로 첫 `t` = 10)
  - **재현 검산 — 과제 성공(`done`)이 처음 뜨는 스텝.** eval 은 성공 순간 멈췄으니 같은 장면이면 마지막 action 에서 떠야 한다

    | | 결과 |
    |---|---|
    | 10개 에피소드 | **8개가 마지막 action 에서 성공** · 태스크 0 은 한 스텝 일찍(75/76) · 태스크 1 은 성공 없음 |
    | 대조 — 장면이 다름(KITCHEN_SCENE1) | **성공 없음** → 검산이 장면 차이는 잡는다 |
    | 대조 — 대기만 30스텝 | **128/128 그대로, 자세 0.1mm 차** → 작은 차이는 **못 가린다** |

    그래서 이 검산이 말하는 것은 **"같은 결과"** 까지다. 자세까지 같은지는 eval 의 proprio 와 대야 안다
  - **두 개가 어긋난 이유 — 화면 출력이 반올림돼 있다.** `robot_utils.py:33` 이 `np.set_printoptions(… "{0:0.3f}")` 로 소수 셋째 자리만 찍는다.
    그릇을 집는 순간처럼 접촉이 있는 곳에서는 그 차이가 결과를 바꾼다.
    **정확한 재현은 `--data_collection True` 의 HDF5 로** — 전체 정밀도로 남고, 같은 실행에서 proprio 도 남아 자세 비교까지 된다
- [x] **번역 결과 — 도달 범위를 어디서 얼마나 넘나**
  → **10개 전부, 크게 넘친다 (10/1).** 변위를 1:1 로 옮기면 (Panda 시작 ↔ Mirobot 홈 파지점)

  | 태스크 | 스텝 | 수평 최대 | 경고선(280) 넘은 줄 | 각도 최대 | Z 최저(플랜지) |
  |---|---|---|---|---|---|
  | 0 | 76 | 504.6mm | 65 | 11.1° | −13.6mm |
  | 1 | 110 | 547.3mm | 92 | 16.4° | −42.8mm |
  | 2 | 99 | **566.8mm** | 86 | 16.2° | −36.4mm |
  | 3 | 79 | 535.0mm | 69 | 10.8° | −9.0mm |
  | 4 | 128 | 527.9mm | **118** | **40.0°** | 7.9mm |
  | 5 | 87 | 494.0mm | 48 | 38.1° | 5.1mm |
  | 6 | 108 | 561.9mm | 98 | 18.3° | −37.4mm |
  | 7 | 115 | 540.3mm | 42 | 9.6° | 13.1mm |
  | 8 | 109 | 533.1mm | 94 | 25.8° | −31.8mm |
  | 9 | 108 | 513.4mm | 97 | 12.2° | −13.6mm |

  - **수평 변위가 300~400mm** 다. Mirobot 홈이 이미 수평 199mm 라 경고선까지 남은 여유가 바깥쪽으로 약 80mm 뿐이다
  - 각도는 대부분 괜찮다 — 태스크 4·5(서랍·라메킨 위 그릇)만 30° 를 넘는다
  - **장면 탓이 아니다** — 장면을 KITCHEN_SCENE1 로 바꿔도 수평 510mm. **정책 동작의 크기 자체**다
  - **얼마나 줄이면 들어가나 (어림)** — 위치 변위에만 배율을 곱한다고 하면 **0.23~0.28**, 10개 모두면 **약 0.23 (≈ 1/4)**.
    그때 Z 최저는 162~175mm. 어림인 이유 — 플랜지 변위로 셈(파지점 오프셋의 회전 무시), 기준이 실제 한계(약 315mm)가 아니라 경고선 280mm,
    관절 한계·IK 해는 안 봤다
  - **흔히 말한 "2.7배"(855 vs 315mm)보다 훨씬 세다** — 도달 거리의 비가 아니라 **홈에서 바깥으로 남은 여유**가 정하기 때문이다.
    LIBERO 장면을 그대로 두고 동작만 1/4 로 줄이면 그릇·접시에 손이 안 닿으므로, **장면도 같이 줄여야** 한다 → ②③ 의 설계 조건
    (W4 8절 "궤적 축소 방법" 질문의 근거)
  - **→ 짝을 옮기면 배율을 키울 수 있다 — 4-4.** 이 0.23 은 짝을 홈에 둔 값이다
- [ ] **그리퍼 칸** — 지금 번역기는 그리퍼 action 을 시뮬 Panda 에만 넣고 G-code 에는 안 적는다 (`M4` 없음)
  → 

### 4-2. 열린 고리 — chunk 사이 다시 맞추기

- [ ] **지금 번역기는 열린 고리다** — 받은 action 을 넣고 나온 자세를 적을 뿐, 실물이 어디 있는지 안 본다.
  실제 운용에서는 **chunk 사이에 시뮬 Panda 를 Mirobot 의 실제 자세로 다시 데려다 놓아야** 한다 (CHECKLIST 2-4).
  다만 Mirobot 의 "실제 자세" 는 `?` 라 측정이 아니다 — 무엇으로 맞출지부터 정해야 한다
  → 

### 4-3. 실물

- [ ] **촘촘한 연속 명령을 받아 내는가** — 지금까지 실물에 보낸 가장 긴 파일이 61줄이다. 번역 결과는 20Hz 로 1157줄.
  `--stream` 으로 버퍼가 버티는지, 솎아(`--every`) 보내야 하는지. **이건 번역이 맞는지를 말해 주지 않는다** — 받아 내는지를 본다
  → **아직 안 보냈다 (10/5).** dry-run 만 — 1157줄, 수평 169.2~250.9mm, Z 173.0~248.3mm, 각도 최대 A 20.0 · B 21.5 · C 25.1°, 경고 0. 머리말 `; point grip`, `; pair` 없음 → 홈 짝·배율 1
- [ ] **같은 동작인가** — `?` 로는 못 잰다. 촬영해서 Panda 영상과 나란히
  → 

### 4-4. 크기 맞추기 — 짝과 배율 (10/1)

**왜 필요한가** — 4-1 대로 정책 동작을 1:1 로 옮기면 10개 전부 Mirobot 을 넘는다. 넘치는 양을 정하는 것은 두 로봇의
도달 거리 비(315 / 855 ≈ 0.37)가 아니라 **Mirobot 홈에서 바깥으로 남은 여유**다. 홈이 이미 수평 199mm 라
경고선(280mm)까지 앞쪽으로 **81mm** 뿐인데, 정책은 시작점에서 바깥으로 300~400mm 를 움직인다. 그래서 짝을 홈에 두면
배율을 **0.23** 까지 줄여야 하고, 0.37 로는 여전히 넘친다.

**손잡이는 둘이다** — `Mirobot 위치 = 짝(Mirobot) + (Panda 위치 − 짝(Panda)) × 배율` (`common/workspace.py`)

- **배율** — 변위에 곱한다. 세 축 같게, 고정값. 짝을 중심으로 늘고 준다
- **짝** — 지금까지는 "Panda 시작 ↔ Mirobot 홈". **Mirobot 쪽 짝을 베이스 쪽으로 당기면** 앞쪽 여유가 늘어 배율을 키울 수 있다

| Mirobot 쪽 짝 X (파지점) | 들어가는 배율 (10개 모두) | 가장 넉넉한 태스크 | 베이스에 가장 가까운 점 | Z 최저 (플랜지) |
|---|---|---|---|---|
| **199 (홈)** | **0.23** | 0.28 | 186mm | 167mm |
| 160 | 0.34 | 0.41 | 143mm | 137mm |
| **120** | **0.44** | 0.54 | **103mm** | 110mm |
| 80 | 0.54 | 0.67 | 71mm | 84mm |
| 60 | 0.58 | 0.73 | 61mm | 72mm |

LIBERO-Spatial 정책 10개 에피소드에서 계산한 어림이다 (플랜지 변위로 셈, 기준은 경고선 280mm). 당길수록 배율은 오르지만
**팔이 베이스 가까이 접혀 들어오고 더 낮게 내려간다** — 안쪽 한계는 아직 모른다.

**다른 연구는 어떻게 했나** — 우리 경우(큰 Panda 로 학습한 정책을 훨씬 작은 팔로)를 그대로 다룬 논문은 찾지 못했다. 세 갈래에서 한 조각씩 가져온다

| 선례 | 무엇을 했나 | 우리에게 |
|---|---|---|
| **Mirage** (RSS 2024) — 번역기 방식의 원조 | 두 좌표계를 고정 변환(이동·회전)으로만 맞춘다. **배율 없음.** *"common robot arms with similar workspaces"*, *"tasks … in both robots' workspace"* 를 가정 | **Mirobot 은 이 가정 밖이다** — 배율은 우리가 더하는 것이라 근거가 따로 필요하다 |
| **원격 조작** (teleoperation) | 크기가 다른 두 팔의 표준 짝짓기가 **기준점 맞추기 + 배율**. 배율은 따라가는 팔의 작업 공간을 덮고 경계에서 다시 잡는 일을 줄이도록 | **"짝 + 배율" 구조 자체는 정착된 방식** |
| **VLA fine-tuning** (OpenVLA · SmolVLA · Cosmos Policy) | 데이터셋마다 action 을 [−1, 1] 로 정규화. 학습과 실행이 같은 정규화를 쓴다. Cosmos Policy 도 데이터셋 최솟값·최댓값으로 맞춘다 (`cosmos_utils.py:623-645`, LIBERO 위치 action 범위 ±0.9375) | **학습과 실행이 같은 짝·배율을 써야 한다** |

**고르는 기준**

| | 기준 | 성격 | 근거 |
|---|---|---|---|
| 가 | 모든 점이 Mirobot 안전 범위 안 (수평 280mm) | 반드시 | 원격 조작 · 위 표 |
| 나 | 시작 자세와 베이스 근처 점이 실물에서 거부되지 않는다 | 반드시 | 역기구학·관절 한계는 실물만 안다 — **미확인** |
| 다 | 배율은 세 축 같게, 고정값 | 단순하게 | 원격 조작 · `workspace.py` "축마다 다르면 찌그러진다" |
| 라 | 학습과 실행이 같은 짝·배율 | 반드시 | OpenVLA · SmolVLA 의 정규화 일치 |
| 마 | 우리 과제를 Panda 공간으로 옮겼을 때 LIBERO 동작과 비슷한 크기 | **우리 판단** (논문 근거 아님) | 아래 |

**마** — action 번역에서는 학습 라벨이 "Mirobot 데모를 Panda 공간으로 키운 동작" 이다. 배율이 s 면 Mirobot 의 100mm 가
Panda 에서 100/s mm 가 된다. **s = 0.23 이면 435mm** 로 LIBERO 정책의 평소 동작(300~400mm)보다 커서 사전학습 분포 밖으로 나가고,
**s = 0.44 면 227mm** 로 그 안에 머문다. 배율이 너무 작으면 가를 지켜도 마를 잃는다 — 짝을 당겨 배율을 키우는 둘째 이유다.

**정한 것 — 짝 X 120, 배율 0.44 를 후보로 둔다** (`MAPPINGS["candidate"]`). **기본값은 아직 홈이다** — 나를 확인한 뒤 올린다

- [x] **코드** — Mirobot 쪽 짝을 바꿀 수 있게 하고(`ref_mirobot_mm`), 짝·배율을 **G-code 머리말** `; pair X120.00 Y0.00 Z175.72 scale 0.44` 에 적는다.
  쓰는 쪽(`action_to_gcode` · `libero_to_mirobot_gcode`)은 `--mapping {home,candidate}`, 읽는 쪽(`libero_follow` · `drift_check` · `roundtrip_check`)은
  머리말을 따른다. **표시가 없는 파일은 홈·배율 1** 로 읽는다 (파지점 전환 때와 같은 방식)
  - **원래 있던 구멍도 막았다** — `libero_follow` · `drift_check` 는 배율을 아예 안 읽어서, `--scale` 로 만든 파일을 배율 1 로 잘못 읽었다
  - 테스트 3개 추가 (`test_workspace` 14개), 전체 33개 통과
- [x] **검산**

  | 확인 | 결과 |
  |---|---|
  | 옛 파일 | `drift_check` 끝에서 끝 2.092 / 2.496mm · 0.346°, `roundtrip_check` 0.30mm — **그대로** |
  | 정책 10개를 후보값으로 | **수평 경고 0** — 최대 246.5~279.6mm (태스크 2 가 경계에 바짝 붙는다). Z 최저 109~135mm |
  | 후보값 파일을 만들어 시뮬이 따라가게 | 끝에서 끝 **1.895mm** = 홈일 때 1.898mm → **읽는 쪽이 머리말대로 되돌린다** |

- **각도는 그대로 넘는다** — 태스크 4·5 가 40.0° · 38.1° 로 배율 전과 같다. **배율은 위치에만 먹고 자세에는 안 먹는다.**
  J5 는 −200° ~ +30° 다 (W4 4절). 이 두 태스크의 손목 자세는 따로 다뤄야 한다
- **기존 LIBERO 장면의 물체도 후보값이면 들어온다 (10/5)** — Object·Spatial 장면의 물체를 옮기면 Mirobot 수평 105~256mm.
  그래서 도달 범위는 장면을 새로 만들지(②) 골라 쓸지(③)를 가르지 않는다 ([CHECKLIST.md](CHECKLIST.md) 5-2)
- **높이가 새 문제다 (10/5)** — 지금 짝 Z 는 홈 파지점 높이(175.72mm)를 그대로 쓴 값이라, Panda 의 탁상 면이 Mirobot Z 약 56~64mm 에 온다.
  실물 작업대 면이 그 높이가 아니면 손끝이 물체 위 허공에서 멈춘다. **짝 Z = 실물 작업대 Z + 0.44 × (Panda 시작 손끝의 탁상 위 높이 254~273mm)**
  로 다시 정한다 — 작업대 Z 는 로봇 노트북에서 잰다 (CHECKLIST 7절)
- [ ] **나 — 실물에서 두 줄** (로봇 노트북, `run_gcode` 기본 모드로 한 줄씩)
  - 시작 자세 — `G0 X123.15 Y0.01 Z230.63 A-0.01 B3.28 C0.02` (파지점이 짝 X 120 에 오는 자리)
  - 베이스에 가장 가까운 점 — `G0 X95.63 Y-42.30 Z135.06 A-1.79 B4.39 C0.27` (수평 104.6mm, 태스크 7)
  → **나 는 깨졌다 (10/5).** 시작 자세 `X123.15 Z230.63` → `Error,A102,Soft limit:Y`(J2) — 베이스 근처 점은 그 뒤라 안 보냈다. 테이블 정렬로 짝 Z 를 내린 배율별 시작 자세는 **0.30 · 0.35 · 0.40 통과, 0.44 거부**(`X123.07 Z176.04`). 내측 한계는 플랜지 X ≈ 128~139mm 이고 **Z 165~231 에서 높이와 거의 무관**하다 — 짝 Z 를 내려도 X 가 더 들어가지 않는다. 또 궤적의 가장 안쪽 점이 짝 X 보다 ~17mm 안쪽이라(옛 표) 0.40 도 궤적 중간에서 막힐 것으로 보였다 — 시작 자세만으로는 판정이 안 된다. → 서버가 **Mirobot 은 홈에서 시작하고 시뮬 Panda 시작 자세를 맞추는** 쪽으로 바꿨다. 세로 하한에 쓸 `Zt` 는 [CHECKLIST.md](CHECKLIST.md) 7절 "10/5 실물"
- [ ] **마 — 우리 과제의 동작 범위로 다시 본다** — 위 숫자는 pretrained LIBERO 정책 기준이다. fine-tuning 뒤에는 ②③ 장면의 데모가 정한다
  → 
- [ ] **교수님께** — 궤적 축소 방법(W4 8절, 아직 안 여쭘)을 이 기준표를 들고 여쭌다
  → 

출처 — [Mirage (arXiv 2402.19249)](https://arxiv.org/abs/2402.19249) ·
[OpenVLA](https://arxiv.org/html/2406.09246) ·
[SmolVLA (LeRobot)](https://learnopencv.com/smolvla-lerobot-vision-language-action-model/) ·
[Workspace mapping scaling factor in teleoperation](https://link.springer.com/article/10.1007/s12206-023-1036-y) ·
[Master-slave asymmetric teleoperation workspace mapping](https://www.researchgate.net/publication/323406740_Modular_Development_of_Master-Slave_Asymmetric_Teleoperation_Systems_With_a_Novel_Workspace_Mapping_Algorithm) ·
[Motion scaling in surgical teleoperation](https://arxiv.org/html/1902.03290)

---

## 5. 실물 운용 절차

> 4-3 을 한 뒤에 채운다.

---

## 관련 문서

- [ACTION_MEANING.md](ACTION_MEANING.md) — action 번역으로 정한 판단 (1-9: 번역기가 왜 시뮬 Panda 인가)
- [CHECKPOINT.md](CHECKPOINT.md) — 출발 가중치, HF 접근(6절)
- [CHECKLIST.md](CHECKLIST.md) — 작업 목록 (2-4, 7-1)
- [../W4/ANSWER.md](../W4/ANSWER.md) ④ 4절 — Mirobot `?` 가 측정이 아닌 이유
- `tools/action_to_gcode.py` — 번역기 · `tools/libero_follow.py` — 추종 루프 · `common/workspace.py` — 좌표 변환
