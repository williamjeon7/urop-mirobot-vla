# UROP — WLKATA Mirobot VLA 파이프라인

6축 Mirobot 을 대상으로 하는 VLA(Vision-Language-Action) 파이프라인. 코드가 두 환경에
나뉘어 실행되지만 **관측/액션 스키마와 통신 규약은 반드시 동일해야 해서** 한 repo 로
관리한다.

## 구조

```
common/   양쪽이 import 하는 공용 정의 — 여기서만 고친다
  schema.py     관측(9차원) / 액션(7차원) 벡터 레이아웃
  protocol.py   브리지 통신 토큰, 포트
  gcode.py      상태·액션 → G-code 변환
  demos.py      임베디드 데모 궤적 10개

robot/    로봇 노트북(Windows)에서만 실행 — 시리얼 직결
  serial_bridge.py       TCP ↔ 시리얼 브리지 (서버가 붙는 쪽)
  camera_bridge.py       USB 카메라 HTTP 스트림
  replay_serial.py       데모 재생 (시리얼 직결)
  replay_demo0.py        demo_0 만 재생, 첫 연결 확인용
  replay_hdf5.py         HDF5 데모 재생
  forward_kinematics.py  FK 수동 조작
  inverse_kinematics.py  IK 수동 조작

server/   GPU 서버(Linux)에서만 실행 — 브리지 경유
  bridge_client.py       노트북 브리지 클라이언트
  replay_network.py      데모 재생 (브리지 경유)
  replay_with_viewer.py  재생 + 시뮬 프레임 브라우저 뷰어
  replay_with_mujoco.py  재생 + 라이브 MuJoCo (※ 현재 미동작, docs/VENDORED.md 참조)
```

## 설치

`common/` 을 양쪽에서 import 하려고 editable install 을 쓴다. `sys.path` 는 건드리지 않는다.

**Python 3.10 이어야 한다.** 3.11 이상에서는 `pip install -e .` 이 거부된다.

```bash
# 서버 (Linux)
pip install -r requirements/server.txt
pip install -e .

# 로봇 노트북 (Windows)
pip install -r requirements/robot.txt
pip install -e .
```

`requirements/robot.txt` 와 `server.txt` 는 각각 `-r common.txt` 로 공통분을 상속한다.
`pyproject.toml` 의 `dependencies` 가 비어 있는 것은 의도된 것이다 — 양쪽 환경의
의존성이 다르고, 정작 `common/` 은 표준 라이브러리만 쓴다.

### 모델 가중치

**저장소에 모델 파일은 없다.** 20GB 가 넘어 git 으로 다룰 크기가 아니라 각자 받는다.
받는 법과 어느 환경에 무엇이 필요한지는 `docs/MODELS.md` 에 있다.

노트북은 **모델이 아예 필요 없다** — `robot/` 은 저장된 데모 궤적을 G-code 로 재생할
뿐 추론을 하지 않는다. 서버에서 학습/추론을 할 때만 필요하다.

실행은 파일 경로가 아니라 모듈로 부른다:

```bash
python -m robot.serial_bridge --serial-port COM3        # 노트북
python -m server.replay_network --demo 0 --max-steps 5  # 서버 (드라이런)
```

## 문서

- `docs/SETUP_LINUX.md` — 서버→터널→노트북→로봇 3창 실행 절차, 트러블슈팅
- `docs/VENDORED.md` — 외부 저장소(cosmos-policy, RosForMirobot) 받는 법
- `docs/MODELS.md` — 모델 가중치 받는 법, 캐시 위치
- `docs/plan/` — 프로젝트 계획, 주차별 가이드

## 제약

- **Python 3.10 고정** (3.11+ 에서 SDK dataclass 호환 문제). `pyproject.toml` 의
  `requires-python = ">=3.10,<3.11"` 로 강제된다.
- 모델 체크포인트, `data/`, `logs/`, `wandb/`, `outputs/` 는 버전관리 대상이 아니다.
- `cosmos-policy/` 와 `RosForMirobot-master/` 도 버전관리에서 빠져 있다.
  새 환경에서는 `docs/VENDORED.md` 절차대로 직접 clone 해야 한다.
