# Mirobot Tabletop 환경 세팅

10/29
현재 연결 구성은 **D405·Mirobot USB → Windows 노트북(로컬)**, **데이터 변환용 시뮬·검사 → OASYS 서버**입니다. 이번 작업은 촬영·0.05초 타임스텝 정렬 후 Cosmos Policy LIBERO 학습용 HDF5·통계·실제 T5 임베딩을 준비하는 데까지이며, 모델 학습은 후속 작업입니다.

- **[로컬: Windows PowerShell] Mirobot**: 저장소 루트에서 `docs/W9/.venv/Scripts/python.exe -m serial.tools.list_ports -v`로 실제 포트를 확인하고 `--port COM3`처럼 지정합니다. COM3는 예시이며 장치 관리자와 조회 결과를 따릅니다.
- **[로컬: Windows PowerShell] D405**: RealSense SDK의 USB 장치입니다. COM 포트를 쓰지 않으며 `docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --list`로 확인합니다. 이전 메모의 D405 COM4 표기는 사용하지 않습니다.
- **[로컬 → 서버]**: 촬영·색 보정·로봇 녹화·영상 검토까지 노트북에서 끝내고 원본 폴더를 OASYS로 전송합니다.
- **[서버: OASYS Bash]**: 전송받은 기록으로 시뮬 추종·HDF5 변환·로더 검사·실제 T5 임베딩 준비까지 수행합니다. 서버의 카메라 0대 조회는 현재 구성에서 정상입니다.

설치·촬영·색 보정·조작·자동 번호 저장과 데이터 변환은 [통합 수집 가이드](MIROBOT_DATA_COLLECTION.md)를 따릅니다.

격자판 기준 0도에 Homing에서 고정, 청테이프로 mirobot 밑에 표시 완료

RGB 블록 초기 위치 설정 완료, 샤프로 초기 위치 표시 완료
-> LIBERO TABLETOP으로 XML 작성할 때 초기 환경 수정 필요

그리고 LIBERO D405 기준으로 색상 보정 행렬 써서 맞춰야 합니다.

실험실을 커튼 치고, 불 다 켜고 하시면 됩니다. d405 색상 보정은 제가 했어요!

격자 무늬 1칸당 가로 10mm, 세로 10mm

## 환경 세팅 사진

격자판과 초기 위치 표시:

![격자판과 초기 위치 표시](./images/mirobot_tabletop_grid.png)

Mirobot과 RGB 블록 초기 배치:

![Mirobot과 RGB 블록 초기 배치](./images/mirobot_tabletop_setup.png)


