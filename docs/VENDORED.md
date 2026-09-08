# 외부 저장소 (vendored)

아래 두 저장소는 **버전관리에서 제외**되어 있다 (`.gitignore`). 각자 자체 `.git` 을
가진 순정 업스트림 클론이라 그대로 커밋하면 URL 도 없는 깨진 gitlink 가 되고,
`cosmos-policy/.venv` 는 13GB 다.

새로 clone 한 환경에서는 아래 절차로 직접 받는다. 위치는 **repo 최상위**여야 한다.

## cosmos-policy

NVIDIA VLA 정책 학습 코드. 서버(`server/`) 쪽에서 참조한다.

```bash
cd ~/UROP
git clone https://github.com/NVlabs/cosmos-policy.git
git -C cosmos-policy checkout 18a2acc
```

검증 시점(2026-09-08) 기준 로컬 수정 0개. 환경 구성은 해당 repo 의 `SETUP.md` 참조
(uv 로 `.venv` 생성, Python 3.10).

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
cd ~/UROP
git clone https://github.com/wlkata/RosForMirobot-master.git
git -C RosForMirobot-master checkout 8a60a4c
```

검증 시점 기준 로컬 수정 0개.
