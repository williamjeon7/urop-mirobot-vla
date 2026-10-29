# W9 실행 안내

지금 하려는 작업은 **Calibrite ColorChecker Classic Mini 색 보정 → 기존 inverse_kinematics.py 키보드 조작으로 학습 데이터 수집**입니다.

1. **[COLORCHECKER_MINI.md](COLORCHECKER_MINI.md)** — 먼저 읽을 문서. 표 촬영, 네 모서리 선택, 보정 확인, F8/F9 녹화 순서.
2. [D405_GUIDE.md](D405_GUIDE.md) — 설치, 파일 구조, 20Hz 타임스텝 정렬, 서버 HDF5 변환.
3. [D405_TRAINING.md](D405_TRAINING.md) — GPU 서버에서 실제 지시문 임베딩과 Cosmos Policy 파인튜닝.
4. [D405_INSTALLATION.md](D405_INSTALLATION.md) — 이 PC에 설치한 프로그램과 실제 검증 결과.

지금 시작할 명령(카메라만 사용):

```powershell
cd C:\mirobot-vla
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --out docs/W9/data/raw/chart_001 --seconds 3 --preview
```

먼저 실제 색상표를 작업 조명 아래에 놓으세요. `chart_001` 폴더가 이미 있으면 새 이름을 쓰세요. 보정 프로필은 실제 표 촬영 후 만듭니다.

기존 설계: [DATASET_HDF5.md](DATASET_HDF5.md), [FOLLOW.md](FOLLOW.md), [CHECKLIST.md](CHECKLIST.md).
