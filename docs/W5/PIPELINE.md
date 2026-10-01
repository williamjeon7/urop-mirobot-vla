# 파이프라인 — policy 에서 Mirobot 까지

> **절차** · 확인 2026-10-01 · 기준 `cosmos-policy@18a2acc`, `nvidia/Cosmos-Policy-LIBERO-Predict2-2B@cb689ec`, 서버(OASYS)
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
**좌표 변환이 파지점 기준으로 서버에서도 맞는다.** 남은 것은 **정책이 낸 action 을 번역기에 넣는 것**과 **실물**이다.

| 토막 | 상태 |
|---|---|
| policy | **돈다** (3-2) |
| 번역기 | **돈다** — 단, 지금까지 넣은 action 은 정책 출력이 아니다 (3-3) |
| 좌표 변환 | **맞는다** — 파지점 기준, 서버 확인 (3-1) |
| 정책 action → 번역기 | **아직** (4절) |
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
| 그 밖 | eval 의 화면 출력 — `t: … action: [ … ]` 줄을 긁는다. 재실행 없이 쓰려고 |

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
  → 
- [ ] **번역 결과 — 도달 범위를 어디서 얼마나 넘나**
  → 
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
  → 
- [ ] **같은 동작인가** — `?` 로는 못 잰다. 촬영해서 Panda 영상과 나란히
  → 

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
