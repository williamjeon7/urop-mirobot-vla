# LIBERO — 관측 · 액션 구조

> **참조** · 확인 2026-09-09 · 기준 `cosmos-policy@18a2acc`
> LIBERO 의 관측/액션 구조와 우리 스키마(`common/schema.py`)의 대응 관계.

우리 Mirobot 스키마가 LIBERO 규약을 이식한 것이라, 둘의 대응 관계를 확인해 둔 문서다.

경로는 모두 `cosmos-policy/cosmos_policy/experiments/robot/libero/` 아래다.
`cosmos-policy` 는 별도 clone 이 필요하다 (약 20MB) — `VENDORED.md` 참조.

---

## 설치 없이 열 수 있는 자료

모델도 LIBERO 도 필요 없다. `pickle` + `numpy` + `json` 이면 된다.

| 파일 | 크기 | 내용 |
|---|---|---|
| `sample_libero_10_observation.pkl` | 384KB | 관측 하나가 통째로 |
| `libero_10_metainfo.json` | 1.1MB | 태스크 10개 |
| `libero_goal_metainfo.json` | 1.1MB | |
| `libero_object_metainfo.json` | 1.7MB | |
| `libero_spatial_metainfo.json` | 1.3MB | |

```python
import pickle
d = pickle.load(open(".../libero/sample_libero_10_observation.pkl", "rb"))
```

---

## 관측 (observation)

| 키 | 형태 | 출처 |
|---|---|---|
| `primary_image` | (256, 256, 3) uint8 | `obs["agentview_image"]` |
| `wrist_image` | (256, 256, 3) uint8 | `obs["robot0_eye_in_hand_image"]` |
| `proprio` | (9,) float64 | 아래 |

해상도는 `get_libero_env(..., resolution=256)` 에서 `camera_heights` /
`camera_widths` 로 정해진다 (`libero_utils.py:30`).

### proprio 9차원 — 우리 STATE 와 정확히 같다

```python
# LIBERO   run_libero_eval.py:334
np.concatenate((obs["robot0_gripper_qpos"],  # 2
                obs["robot0_eef_pos"],       # 3
                obs["robot0_eef_quat"]))     # 4  = 9

# 우리     common/schema.py
[gripper_left_qpos, gripper_right_qpos,           # 2
 eef_pos_x, eef_pos_y, eef_pos_z,                 # 3
 eef_quat_w, eef_quat_x, eef_quat_y, eef_quat_z]  # 4  = 9
```

순서까지 동일하다. `common/schema.py` 의 인덱스 상수를 LIBERO 데이터에 그대로
쓸 수 있다.

---

## 액션 (action) — 7차원 Cartesian 델타

```python
# libero_utils.py:42
def get_libero_dummy_action(model_family):
    return [0, 0, 0, 0, 0, 0, -1]
```

`delta EEF pos(3) + delta rot(3) + gripper(1)`. 우리 ACTION 7차원과 동일하다.

**관절 제어가 아니다.** Panda 관절 제어였다면 7축 + 그리퍼로 8차원이 나온다.
즉 정책은 Cartesian 델타를 내보내고 **IK 는 robosuite 컨트롤러가 내부에서 푼다**
(OSC 계열).

### FK / IK 판단에 관한 메모

우리 쪽도 이미 같은 계열이다. `common/gcode.py` 의 `state_to_gcode()` 가 EEF 좌표를
`G0 X.. Y.. Z..` 로 내보내고 Mirobot 펌웨어가 IK 를 푼다.

따라서 쟁점은 "FK 냐 IK 냐" 가 아니라 **"Cartesian 공간을 유지할 것이냐, 관절 공간으로
내려갈 것이냐"** 에 가깝다. 정리되면 `plan/운영기준.md` §7 의 `액션 표현` 항목에
결정을 남긴다.

---

## metainfo — demo 목록과 성공/실패 라벨

```python
{
  "put_both_the_alphabet_soup_and_the_tomato_sauce_in_the_basket": {
      "demo_0":  {"success": True,  "initial_state": [...]},
      "demo_3":  {"success": False, "initial_state": [...]},
      ...
  },
  ...   # 태스크 10개
}
```

**실패한 demo 도 라벨이 붙어 있다.** Failure Detection 쪽에서 참고할 만하다.

`initial_state` 는 재현용 초기 상태 벡터다. `run_libero_eval.py:308
load_initial_states()` 가 이걸 읽는다. 시드가 고정 초기 상태를 써도 물체 위치에
영향을 준다는 주석이 `libero_utils.py:36` 에 있다.

---

## 롤아웃 저장

- 프레임 누적: `run_libero_eval.py` 의 `replay_images` / `replay_wrist_images`
  (`run_episode()` 안, 376행 부근)
- 영상 저장: `libero_utils.py:61 save_rollout_video()`,
  `libero_utils.py:77 save_rollout_video_with_future_image_predictions()`
- `data_collection=True` 로 두면 에피소드 데이터를 오프라인용으로 남긴다
  (`run_libero_eval.py:264`)

---

## 시뮬을 실행까지 하려면

`libero_requirements.txt`:

```
imageio[ffmpeg]
robosuite==1.4.1
bddl
easydict
cloudpickle
gym
draccus
mujoco==3.3.2
```

**모델은 여기서도 필요 없다.** 다만 리눅스 기준으로 만들어진 스택이라 윈도우에서는
렌더링·bddl 쪽 마찰이 있을 수 있다. 서버 `cosmos-policy/.venv` 에는 이미 mujoco 가
들어 있다.

체크포인트를 써서 실제 정책 롤아웃을 돌리는 단계가 되면 그때 모델이 필요하다.
`MODELS.md` 참조 — `--ckpt_path` 에 HF repo ID 를 넘기면 자동으로 받는다.
