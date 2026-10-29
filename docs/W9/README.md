# W9 실행 안내

**로컬 = D405가 연결된 Windows 노트북의 PowerShell**, **서버 = SSH/VS Code Remote로 접속한 OASYS의 Bash**입니다. 노트북의 시작 메뉴에서 PowerShell을 열면 로컬입니다. `<USER>@OASYS:~/UROP$`가 보이면 서버입니다.

| 순서 | 실행 위치 | 할 일 | Python 환경 |
| --- | --- | --- | --- |
| 1 | 로컬 Windows | 설치, D405·로봇 포트 확인 | `docs/W9/.venv/Scripts/python.exe` |
| 2 | 로컬 Windows | 색상표 촬영 → 네 모서리 선택 → 보정 확인 | 같은 W9 환경 |
| 3 | 로컬 Windows | Mirobot 키보드 조작·F8/F9 녹화 → MP4 검토·시간 정렬 | 같은 W9 환경 |
| 4 | 로컬 → 서버 | 원본 녹화 폴더와 보정 프로필 전송 | PowerShell의 `scp` |
| 5 | 서버 OASYS | Panda 시뮬 추종 → HDF5 생성·검사 | `cosmos-policy/.venv/bin/python` |
| 6 | 서버 OASYS | 실제 T5 임베딩 → 파인튜닝 | 같은 Cosmos/LIBERO 환경 |

**3번까지 로컬에서 마친 뒤, 4번에서 데이터를 보내고 5번부터 서버 터미널로 전환합니다.** SSH 연결은 파일 전송 때부터 필요합니다. D405·Mirobot은 수집하는 Windows 노트북에 연결합니다. OASYS의 `RealSense devices: 0`은 현재 연결 구성에서 정상이며, 서버에서 카메라 촬영 명령을 실행하지 않습니다.

두 컴퓨터에 같은 최신 저장소 코드를 준비합니다. 로컬 경로는 아래에서 `C:\mirobot-vla`로 가정하므로 실제 저장소 경로가 다르면 바꾸세요. `.venv`는 각 OS에서 따로 만들며 복사하지 않습니다.

## [로컬: Windows PowerShell] 지금 시작할 명령

Python 3.10과 저장소가 준비된 노트북에서 실행합니다. VS Code Remote 창을 사용 중이면 노트북 시작 메뉴에서 PowerShell을 별도로 여세요.

```powershell
cd C:\mirobot-vla
powershell -ExecutionPolicy Bypass -File docs/W9/d405/setup.ps1
```

장치 조회에서 D405가 보이면 색상표를 3초 촬영합니다.

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --out docs/W9/data/raw/chart_001 --seconds 3 --preview
```

실제 색상표를 작업 조명 아래에 놓으세요. `chart_001`이 이미 있으면 새 이름을 씁니다. 이어서 [COLORCHECKER_MINI.md](COLORCHECKER_MINI.md)의 **[로컬] 3~6절**까지 진행합니다.

## [로컬 → 서버] 전송하고 서버 작업으로 전환

서버 폴더 준비, 로컬 PowerShell의 `scp`, 서버 HDF5 실행 순서는 [D405_GUIDE.md의 6번](D405_GUIDE.md#6-서버에서-외부-영상action-생성--hdf5)을 따릅니다. `data/`는 Git 제외 대상이므로 코드 push/pull만으로 녹화가 옮겨지지 않습니다. MP4만 보내지 말고 PNG·JSONL·metadata·보정 파일을 포함한 폴더 전체를 보냅니다.

## 상세 문서

1. **[COLORCHECKER_MINI.md](COLORCHECKER_MINI.md)** — [로컬] 색 보정·키보드 녹화, [전환] 서버로 보낼 자료.
2. [D405_GUIDE.md](D405_GUIDE.md) — [로컬] 설치·녹화·시간 정렬, [전환] 전송, [서버] HDF5 변환.
3. [D405_TRAINING.md](D405_TRAINING.md) — [서버] 임베딩·Cosmos Policy 파인튜닝.
4. [D405_INSTALLATION.md](D405_INSTALLATION.md) — 컴퓨터별 설치·검증 기록.

기존 설계: [DATASET_HDF5.md](DATASET_HDF5.md), [FOLLOW.md](FOLLOW.md), [CHECKLIST.md](CHECKLIST.md).
