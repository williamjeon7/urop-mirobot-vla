# W9 설치·검증 기록

## 현재 작업 분담 (2026-10-29)

- **[로컬: Windows 노트북]**: D405가 실제 연결된 장비입니다. 수집·색 보정·로봇 조작·영상 검토·시간 정렬을 수행합니다. 로컬의 현재 연결 상태는 노트북에서 다시 조회해야 합니다.
- **[서버: OASYS Linux]**: 로컬에서 전송받은 원본으로 시뮬 추종·HDF5·T5·학습을 수행합니다. 서버에 D405를 연결할 필요가 없으며 `RealSense devices: 0`은 현재 구성에서 정상입니다.
- 로컬 녹화·검토 후 원본을 전송하는 지점에서 서버 터미널로 전환합니다. 자세한 순서는 [README.md](README.md)를 따릅니다.

## [서버: OASYS] 보조 검사 환경 확인 (2026-10-29)

- 저장소: `~/UROP` (`~/UROP`). 이 절의 검사 명령은 서버 저장소 루트에서 실행합니다.
- 보조 CPU 검사 환경: `docs/W9/.venv/bin/python`, Python 3.12.3.
- 시스템 `ensurepip`가 없어 `python3 -m venv`는 실패했습니다. 설치된 `uv`의 `--seed`로 `pip`를 포함해 복구했습니다.
- 재설치·검사: `bash docs/W9/d405/setup.sh`. 기존 Cosmos/LIBERO 환경과 별도로 구성합니다.
- requirements의 고정 버전 패키지 6개 설치 완료, `pip check` 통과.
- RealSense SDK import와 장치 조회는 성공했지만 **`RealSense devices: 0`**입니다. USB 카메라는 Windows 노트북에 연결돼 있으므로 서버에서 촬영하지 않습니다.
- Linux 로봇 포트는 `--port`로 지정합니다. W9 teleop는 전역 키 감지 대신 SSH 터미널 입력을 사용합니다.
- `docs/W9/.venv/bin/python -m docs.W9.d405.test_pipeline`: **18개 테스트 통과**. 가짜 시리얼의 Linux 포트 전달, 실제 조작 코드의 터미널 입력 연결, 분할 수신된 방향키·F8/F9 해석, 예외 시 터미널 복원, GUI/포트 누락 시 장치 접근 전 오류 처리를 포함합니다.
- Bash 설치 스크립트 실행·구문 검사와 `git diff --check` 통과. 로봇 동작 검증은 모의 장치로 수행했습니다.
- GPU 시뮬·학습 환경 및 모델 가중치 준비 여부는 이번 W9 설치 결과에 포함되지 않습니다.

실행 절차는 [README.md](README.md), [COLORCHECKER_MINI.md](COLORCHECKER_MINI.md), [D405_GUIDE.md](D405_GUIDE.md)를 따릅니다.

## 이전 Windows 로봇 PC 기록 (2026-10-29)

아래는 이전 Windows 환경에서 남긴 시험 기록입니다. 현재 OASYS에서 장치가 연결되거나 촬영에 성공했다는 뜻은 아닙니다. Windows용 `setup.ps1`은 현재 로컬 수집 환경을 준비할 때 사용합니다.

### 설치됨

- W9 전용 Python 3.10.11 환경: `docs/W9/.venv/`
- 공식 portable Viewer v2.59.1: `docs/W9/downloads/RealSense.Viewer.exe`
- Viewer SHA256: `622F853F56AFC7A396D575FDF7C02054617B535368F4BCBDC8591892EBE33C7D`
- Viewer 다운로드 정보: `docs/W9/downloads/viewer-install.json`
- 수집·색 보정·동기화·HDF5·서버 학습 도구: `docs/W9/d405/`

| Python 패키지 | 설치 버전 |
| --- | --- |
| pyrealsense2 | 2.59.1.11053 |
| numpy | 1.26.4 |
| opencv-python | 4.10.0.84 |
| h5py | 3.12.1 |
| pyserial | 3.5 |
| keyboard | 0.13.5 |

SDK는 카메라 장치 조회와 시험 수집으로 확인했습니다. Viewer 실행 화면은 확인하지 않았습니다. 기존 전역 Python 환경과 다른 가상환경은 변경하지 않았습니다.

### 실제 D405 시험

- D405 1대 조회 성공, RGB 640×480 지원 확인.
- 카메라만 약 3초 시험 수집 성공.
- 결과: `docs/W9/data/raw/camera_install_check/`
- 47프레임, 첫~마지막 수신 시각 차이 3.052초.
- 요청 fps=30, 실제 수신 간격 중앙값 기준 **약 15.00fps**.
- 최대 프레임 간격 67.42ms, 저장한 프레임 번호 사이 건너뜀 0.
- PNG와 프레임 시각·장치 시각·내부 파라미터 저장 확인.
- `review.mp4` 변환 성공. 실제 조명·노출에서 30fps가 나오는지는 별도로 조정·확인해야 합니다.

이 영상은 설치 확인용이며 로봇 상태가 없는 camera-only 자료입니다. 학습 HDF5로 변환하지 않습니다. ColorChecker 실물 기준으로 보정한 영상도 아닙니다.

### 코드 확인

`python -m docs.W9.d405.test_pipeline`: **12개 테스트 통과**.

검증 범위: 다음 타임스텝 action 목표, F8/F9 구간 잘라내기, 쿼터니언 회전 경계, 누락·중복 시각 거부, 그리퍼 전환·역전, 명령 사전 검사, RGB 채널·crop, HDF5 키·차원·쿼터니언, sRGB/D50-D65 변환, 합성 색 치우침의 미사용 패치 오차 감소, 가짜 시리얼 장치를 통한 명령·상태 분리, 학습 경로 override.

Python 구문 컴파일 및 `git diff --check` 통과.

### 기존 조작 코드 연결

`robot/inverse_kinematics.py`에는 W9 녹화에서만 사용하는 선택적 연결 지점 3곳을 추가했습니다. 원래 **COM3 설정과 키 조작·시작/종료 호밍을 유지**합니다. 일반 실행에서는 기존 방식으로 시리얼을 열며, W9 teleop로 실행할 때만 별도 기록기가 같은 연결을 관리합니다.

W9 teleop는 F8~F9 사이만 학습 구간으로 사용하고 원본 RGB·로봇 보고 자세·그리퍼 전송 명령·시각을 남깁니다. 실제 장비로 teleop 전체 흐름을 검증하지는 않았습니다.

### 남은 현장 작업

1. 가지고 계신 Classic Mini를 실제 작업 조명에서 촬영하고 보정 프로필 생성·검토.
2. 실제 로봇으로 키보드 수집 1회 수행, 상태 수신 속도·기록 공백 확인.
3. 집게 닫힘 시간 실측, 실물·시뮬 배치와 좌표 보정 확인.
4. Linux GPU 서버의 기존 Cosmos/LIBERO 환경에서 시뮬 추종·실제 로더 검증.
5. GPU 서버에서 T5·LIBERO 가중치·학습 환경 준비 후 파인튜닝.

ColorChecker의 실제 촬영 데이터와 로봇 에피소드가 아직 없어 실측 보정 프로필·학습 HDF5는 만들지 않았습니다. GPU 환경·대용량 모델은 이 Windows 수집 환경에 설치하지 않았습니다.
