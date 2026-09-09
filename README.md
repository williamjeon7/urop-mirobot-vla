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

**Python 3.10 이어야 한다.** 3.11 이상에서는 `pip install -e .` 이 거부된다.

### 가상환경부터 만든다

`pip install` 을 시스템 파이썬에 그냥 하면 안 된다. 최근 배포판은 PEP 668 로 아예
막아서 `error: externally-managed-environment` 가 뜨고, 막히지 않는 환경이라도 다른
프로젝트와 패키지 버전이 얽힌다.

환경 이름은 **`urop`** 으로 통일한다. `urop/` 는 `.gitignore` 에 있으니 저장소 안에
만들어도 된다.

```powershell
# Windows (PowerShell) — 개인 노트북, 로봇 노트북
py -3.10 -m venv urop
urop\Scripts\Activate.ps1
```

```bash
# Linux / macOS
python3.10 -m venv urop
source urop/bin/activate
```

```bash
# 서버 OASYS — 이미 있는 conda 환경을 쓴다. 새로 만들지 말 것
conda activate urop
```

프롬프트 앞에 `(urop)` 이 붙으면 활성화된 것이고, 이후 모든 명령은 이 안에서 친다.

> **이름은 같지만 서버와 노트북은 서로 다른 도구다.** 아래를 헷갈리면 시간을 버린다.
>
> | 어디 | 무엇 | 켜는 법 |
> |---|---|---|
> | 노트북 (Windows) | venv `urop` | `urop\Scripts\Activate.ps1` |
> | 서버 OASYS (Linux) | conda 환경 `urop` | `conda activate urop` |
>
> 노트북에는 conda 가 설치되어 있지 않다. 거기서 `conda activate urop` 를 치면
> `'conda' 용어가 ... 인식되지 않습니다` 가 뜬다. venv 는 conda 가 모르는 물건이라
> conda 가 깔려 있어도 마찬가지다.

`py -3.10` / `python3.10` 이 없으면 먼저 Python 3.10 을 설치한다. 윈도우는
`py --list` 로 설치된 버전을 확인할 수 있고, 없으면 python.org 에서 3.10.11
(윈도우 설치 파일이 제공되는 마지막 3.10) 을 받는다.

> Windows PowerShell 에서 활성화가 `이 시스템에서 스크립트를 실행할 수 없으므로`
> 라며 막히면 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 를 한 번 실행한다.
> cmd 를 쓴다면 `urop\Scripts\activate.bat` 이다.

> venv 는 폴더 이름을 나중에 바꾸면 깨진다. 활성화 스크립트에 절대경로가 박히기
> 때문이다. 이름을 바꾸려면 폴더를 지우고 다시 만든다.

### 코드만 확인하려면 (개인 노트북)

코드를 읽고 어떻게 도는지만 보려는 경우, **로봇도 GPU도 모델도 필요 없다.**
clone 하면 `common/` `robot/` `server/` 세 디렉토리가 전부 따라온다.

```bash
git clone https://github.com/williamjeon7/urop-mirobot-vla.git
cd urop-mirobot-vla

python3.10 -m venv urop           # Windows: py -3.10 -m venv urop
source urop/bin/activate          # Windows: urop\Scripts\Activate.ps1

pip install -e .                  # 서드파티 의존성 0개. requirements 설치 안 해도 된다.
```

이 상태로 드라이런이 돌아간다. 실제 로봇에 나갈 G-code 를 그대로 출력하므로
파이프라인을 눈으로 따라가기 좋다.

```bash
python -m server.replay_network --demo 0 --max-steps 5   # 서버가 브리지로 보낼 G-code
python -m robot.replay_serial   --demo 0 --max-steps 5   # 노트북이 시리얼로 보낼 G-code
```

의존성 없이 되는 것과 안 되는 것:

| | 모듈 |
|---|---|
| 의존성 0개로 동작 | `common/*` 전부, `robot.replay_serial`, `robot.replay_demo0`, `robot.serial_bridge`, `server.bridge_client`, `server.replay_network` |
| 추가 설치 필요 | `robot.replay_hdf5`(h5py), `robot.camera_bridge`(opencv), `server.replay_with_viewer`(pillow), `server.replay_with_mujoco`(mujoco) |

### 실제로 돌리려면

`common/` 을 양쪽에서 import 하려고 editable install 을 쓴다. `sys.path` 는 건드리지 않는다.

```bash
# 서버 (Linux) — 기존 conda 환경 사용
conda activate urop
pip install -r requirements/server.txt
pip install -e .
```

```powershell
# 로봇 노트북 (Windows)
py -3.10 -m venv urop
urop\Scripts\Activate.ps1
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
