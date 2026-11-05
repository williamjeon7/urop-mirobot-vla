# 외부 저장소 (vendored)

> **절차** · 확인 2026-09-09 · 기준 `cosmos-policy@18a2acc`, `RosForMirobot@8a60a4c`
> `.gitignore` 로 빠져 있어 clone 에 따라오지 않는 외부 저장소를 받는 법.

아래 두 저장소는 **버전관리에서 제외**되어 있다 (`.gitignore`). 각자 자체 `.git` 을
가진 외부 클론이라 그대로 커밋하면 URL 도 없는 깨진 gitlink 가 된다.

**즉 `mirobot-vla` 를 clone 해도 이 폴더들은 따라오지 않는다.** 필요하면 아래 절차로
직접 받는다. 위치는 **repo 최상위**다 (서버면 `~/UROP`, 노트북이면 `C:\mirobot-vla`).

## cosmos-policy

NVIDIA VLA 정책 학습 코드.

2026-11-05 이 서버에서는 문서를 `cosmos-policy/docs/upstream/`, 공용 가중치를
`cosmos-policy/models/`, 주차별 작업을 `cosmos-policy/W10/`으로 정리했다.
아래 clone 명령은 원래 업스트림 구조를 받는다. 서버의 현재 구조와 학습 안내는 로컬
`cosmos-policy/README.md`, `cosmos-policy/W10/TRAINING.md`를 본다.

```bash
git clone https://github.com/NVlabs/cosmos-policy.git
git -C cosmos-policy checkout 18a2acc
```

### 받아지는 크기는 약 20MB 다

`cosmos-policy` 하면 13GB 를 떠올리기 쉬운데, 그건 **서버에서 uv 로 만든 `.venv`** 이고
clone 에는 포함되지 않는다.

| | 크기 | clone 에 포함 |
|---|---|---|
| 소스 | 17MB | ✅ |
| `.git` | 3MB | ✅ |
| `.venv` | 13GB | ❌ 각 환경에서 직접 생성 |
| 모델 가중치 | 24GB | ❌ HF 캐시. `docs/MODELS.md` 참조 |

### 개인 노트북에서도 받을 만하다

코드를 **읽는** 목적이라면 노트북에 받아도 부담이 없고, 모델도 필요 없다.
LIBERO 쪽에는 설치 없이 바로 열리는 자료가 들어 있다:

| 파일 | 크기 | 내용 |
|---|---|---|
| `.../libero/sample_libero_10_observation.pkl` | 384KB | 관측 1개 통째로 — `primary_image` (256,256,3) uint8, `wrist_image` (256,256,3), `proprio` (9,) |
| `.../libero/libero_*_metainfo.json` | 5.2MB | 태스크별 demo 목록, 성공/실패 라벨, `initial_state` |

`pickle` + `numpy` + `json` 만 있으면 되고 LIBERO 나 mujoco 설치도 필요 없다.

시뮬레이션을 **실행**까지 하려면 그때 `libero_requirements.txt` (robosuite 1.4.1,
mujoco 3.3.2, bddl 등) 가 필요하다. 리눅스 기준으로 만들어진 스택이라 윈도우에서는
마찰이 있을 수 있으니, 실행은 서버에서 하는 편이 빠르다.

환경 구성은 해당 repo 의 `SETUP.md` 참조 (uv 로 `.venv` 생성, Python 3.10).
검증 시점(2026-09-08) 기준 로컬 수정 0개.

이 코드가 쓰는 **모델 가중치는 또 별개**다. `docs/MODELS.md` 참조.

> **주의** — `server/replay_with_mujoco.py` 는 `cosmos_policy.experiments.robot.mirobot`
> 을 import 하지만 이 모듈은 **업스트림에 없다** (`experiments/robot/` 에는 `aloha`,
> `libero`, `robocasa` 뿐). 재배치 전 이 파일들이 참조하던 `cosmos-policy_tj/` 경로도
> 존재하지 않는다. 즉 이 스크립트를 살리려면 위 clone 만으로는 부족하고 Mirobot 용
> 포크 코드가 따로 필요하다. `docs/SETUP_LINUX.md` 참고.
>
> 재배치 때 이 파일의 `sys.path.insert` 는 제거했다. `cosmos_policy` 는 설치된 패키지로
> 가져온다.

## RosForMirobot-master

WLKATA 공식 ROS 패키지 (URDF, MoveIt, Gazebo). 참고용이며 실행 경로에는 들어가지 않는다.

```bash
git clone https://github.com/wlkata/RosForMirobot-master.git
git -C RosForMirobot-master checkout 8a60a4c
```

검증 시점 기준 로컬 수정 0개.
