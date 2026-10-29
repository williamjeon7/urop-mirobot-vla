# Calibrite ColorChecker Classic Mini로 D405 색 보정하기

색 보정부터 자동 번호 촬영·데이터 변환까지 한 번에 진행하려면 [통합 수집 가이드](MIROBOT_DATA_COLLECTION.md)를 따릅니다. 아래는 직접 출력 이름을 지정하는 상세 예시입니다. 정상 촬영 종료 시 MP4가 자동 생성되므로 `preview` 명령은 MP4가 없을 때만 실행합니다.

**사용할 순서: 색상표 촬영 → 네 모서리 선택 → 보정 확인 → 같은 설정으로 키보드 조작·학습 영상 수집.**
여기서 말하는 색상표는 가지고 계신 **Calibrite ColorChecker Classic Mini, 24패치**입니다. OpenCV `applyColorMap`이나 깊이 영상의 가짜 색상은 사용하지 않습니다.

## 1. 촬영 준비 — [로컬: Windows 노트북]

1. 학습 영상을 모을 때 쓸 조명·카메라 장착 위치·해상도를 먼저 정합니다.
2. 블록이 놓일 위치에 ColorChecker를 놓습니다. 조명은 고르게 비추고 반사광·그림자·집게 가림을 피합니다.
3. 표가 화면에서 충분히 크게 보이도록 합니다. 가능한 한 정면에서 찍고, 색 패치가 흐리거나 하얗게 날아가지 않게 합니다.
4. 표의 **갈색 피부 패치가 왼쪽 위, 흰색 패치가 왼쪽 아래, 검정 패치가 오른쪽 아래**로 보이게 놓습니다. 가로 6칸 × 세로 4칸입니다.
5. RealSense Viewer를 닫습니다. 수집 프로그램과 카메라를 동시에 열 수 없습니다.

Mini는 표준 Classic 24패치 배열의 소형 제품입니다. 기준값은 동봉한 `d405/classic_reference.json`에 있으며, X-Rite의 **2014년 11월 이후 Classic** Lab 기준값을 사용합니다. 오래된 X-Rite Mini를 재사용하는 경우 제조 시기·기준값이 같은지 확인하세요. 이 값은 개별 표의 실측값이 아니라 일반 기준값입니다.

출처: [Calibrite Classic Mini 제품 설명](https://calibrite.com/product/colorchecker-classic-mini/?noredirect=en-GB), [X-Rite 기준값·제조 시기 안내](https://www.xrite.com/service-support/new_color_specifications_for_colorchecker_sg_and_classic_charts), [원본 Lab 파일 미러](https://babelcolor.com/index_htm_files/ColorChecker24_After_Nov2014.txt).

## 2. 색상표를 3초 촬영 — [로컬: Windows PowerShell]

이 문서의 1~6절은 D405와 Mirobot이 연결된 **Windows 노트북에서 실행**합니다. 노트북의 시작 메뉴에서 PowerShell을 여세요. VS Code Remote의 OASYS 터미널은 서버 작업용입니다. 로컬 저장소가 `C:\mirobot-vla`라고 가정하며 실제 경로에 맞춰 바꿉니다.

최초 1회, Python 3.10과 저장소가 준비된 노트북에서 설치합니다.

```powershell
cd C:\mirobot-vla
powershell -ExecutionPolicy Bypass -File docs/W9/d405/setup.ps1
```

설치 스크립트가 D405를 조회합니다. 다시 확인하려면:

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --list
```

Windows에서 `RealSense devices: 0`이면 노트북의 USB 연결과 Viewer 종료 여부를 확인합니다. D405가 조회되면 3초 촬영합니다.

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --out docs/W9/data/raw/chart_001 --seconds 3 --preview
```

결과는 로컬 저장소의 `docs/W9/data/raw/chart_001/`에 저장됩니다. 기존 폴더는 덮어쓰지 않으므로 재촬영은 `chart_002`처럼 새 이름을 사용합니다. 이 단계에서는 서버에 접속할 필요가 없습니다.

프로그램은 자동 노출·화이트밸런스가 안정화될 시간을 주고, 지원하는 설정을 고정합니다. D405는 일반 웹캠과 센서 구성이 다르므로 센서 번호를 임의로 고르지 않고 지원 옵션을 조회합니다. 게인·감마 등 지원 설정도 기록하며 보정 프로필을 쓸 때 복원합니다.

색 보정에는 RGB PNG를 씁니다. 임의의 PNG가 필요하면 `rgb/00000010.png`처럼 녹화 중간 프레임을 고르세요. 흔들림·반사광이 있는 프레임은 제외합니다.

## 3. 색상표의 네 모서리 선택 — [로컬: Windows PowerShell]

같은 로컬 PowerShell에서 실행합니다:

```powershell
cd C:\mirobot-vla
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.color_calibration fit --image docs/W9/data/raw/chart_001/rgb/00000010.png --camera-metadata docs/W9/data/raw/chart_001/metadata.json --out docs/W9/data/calibration/classic_mini.json --confirm-edition
```

창이 뜨면 **색 패치 격자를 둘러싼 사각형**의 모서리를 순서대로 클릭합니다. 검은 카드 바깥 테두리나 로고 영역을 포함하지 마세요.

```text
① 왼쪽 위 ───────────────── ② 오른쪽 위
  갈색 피부 …                     …
  …                              …
  …                              …
  흰색       회색 …               검정
④ 왼쪽 아래 ───────────────── ③ 오른쪽 아래
```

클릭 순서는 **왼쪽 위 → 오른쪽 위 → 오른쪽 아래 → 왼쪽 아래**, 이후 `Enter`입니다. 잘못 선택하면 `r`, 취소는 `Esc`입니다. 표를 거꾸로 찍었다면 먼저 올바른 방향으로 다시 촬영하는 편이 쉽습니다.

코드는 원근을 보정한 뒤 각 패치 중앙 40% 영역의 RGB 중앙값을 읽습니다. 모서리의 검정 테두리·먼지 영향을 줄이기 위한 처리입니다. 패치가 과노출·암부 클리핑 상태면 프로필 생성을 거부합니다.

생성 파일:

```text
docs/W9/data/calibration/
  classic_mini.json             RGB 보정 행렬 + 카메라 설정 + 오차 보고서
  classic_mini.patches.png      패치 선택 영역 확인
  classic_mini.comparison.png   왼쪽 원본 / 오른쪽 보정 결과
```

`comparison.png`를 열어보세요. **먼저 `patches.png`가 6×4칸으로 정확히 잘렸는지** 확인해야 합니다. 패치 순서가 다르면 숫자만 좋아 보여도 잘못된 프로필입니다.

## 4. 보정 결과 판단 — [로컬: Windows 노트북]

보고서의 `heldout_mean_before`와 `heldout_mean_after`를 비교합니다. 계산에 쓰지 않은 6패치에서도 색 오차가 줄어야 프로필을 저장합니다. 오차는 **CIE76 ΔE**이며 CIEDE2000이 아닙니다.

보정 행렬은 나머지 18패치로 학습하는 선형광 RGB 3×3 행렬입니다. 기준 Lab(D50)을 Bradford로 D65에 맞춘 뒤 선형 sRGB에서 계산합니다. D405의 ISP RGB를 sRGB에 가까운 입력으로 해석하는 근사 방식이므로 센서 RAW 기반 정밀 프로파일과 같지는 않습니다. 관련 개념은 [OpenCV 색 보정 모델 안내](https://docs.opencv.org/4.8.0/d1/dc1/tutorial_ccm_color_correction_model.html)를 참고하세요.

실제로 확인할 것:

- 회색이 분홍·초록·파랑으로 치우치지 않는가.
- 빨강·초록·파랑 패치가 부자연스럽게 포화되거나 검게 뭉개지지 않는가.
- 흰색 패치의 질감이 남는가.
- 별도로 다시 촬영한 표와 실제 블록에서도 색이 안정적인가.

학습에 넣을 RGB 블록을 **[255,0,0] 같은 원색으로 강제 변환하지 않습니다.** 실제 색·명암·질감을 유지하며 카메라의 색 치우침을 줄이는 것이 목적입니다. 형광등/LED의 스펙트럼, 반사·그림자 차이는 한 행렬로 전부 해결할 수 없습니다.

다른 이미지에 직접 적용해 확인하려면:

```powershell
cd C:\mirobot-vla
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.color_calibration apply --image docs/W9/data/raw/chart_001/rgb/00000020.png --profile docs/W9/data/calibration/classic_mini.json --out docs/W9/data/calibration/check_second_frame.png
```

<a id="5-inverse_kinematicspy로-조작하면서-녹화"></a>

## 5. inverse_kinematics.py로 조작하면서 녹화 — [로컬: Windows PowerShell]

D405와 Mirobot USB 시리얼을 **둘 다 Windows 노트북에 연결**합니다. 실제 로봇 COM 포트를 확인하세요. D405는 RealSense SDK로 열며 COM 포트를 지정하지 않습니다.

```powershell
docs/W9/.venv/Scripts/python.exe -m serial.tools.list_ports -v
```

아래 `COM3`는 로봇 포트 예시입니다. 장치 관리자 또는 위 조회 결과에 맞춰 바꿉니다.

기존 조작 코드는 `robot/inverse_kinematics.py`입니다. **기존 동작 키를 사용하며, W9에서는 `--port`로 Windows 로봇 COM 포트를 지정**합니다. 녹화 시에만 W9 어댑터를 통해 같은 시리얼 연결에서 상태를 계속 받습니다. `inverse_kinematics.py`를 별도 터미널에서 동시에 실행하지 마세요.

아래 예는 **red / seed 2** 장면과 기존 좌표 변환을 사용합니다. 블록을 실제로 해당 보정·배치에 맞춰 놓아야 합니다. `mapping-gcode`는 좌표 변환 머리말만 사용하며 그 궤적은 실행하지 않습니다. reference는 시뮬 초기 자세·배치의 기준입니다.

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --teleop --out docs/W9/data/raw/red_s2_001 --color red --seed 2 --reference docs/W6/poses/pickup-red-s2.jsonl --mapping-gcode trajectories/2026_10_11-w6-pickup-red-s2-e5.gcode --color-profile docs/W9/data/calibration/classic_mini.json --initial-s 40 --open-s 40 --closed-s 60 --gripper-seconds 1.0 --port COM3 --execute --preview
```

이 명령은 **원래 조작 코드를 실행하므로 시작 시 호밍·초기 위치 이동이 일어납니다.** 먼저 작업 공간을 준비하세요. `--execute` 없이 실행하면 실제 조작을 시작하지 않습니다. teleop에서도 `--port COM3`처럼 실제 로봇 포트를 지정합니다. Windows에서는 기존 `keyboard` 입력을 사용하므로 F8/F9와 조작 키를 누릅니다. 자동 G-code 수집기의 Z 하한 검사는 이 키보드 조작 모드에 적용되지 않습니다. 기존 조작 코드의 이동 범위를 사용합니다.

순서:

1. 호밍·초기 이동이 완전히 끝날 때까지 기다립니다.
2. 기존 `←` 키로 집게를 열어 초기 상태 S40을 맞춥니다. 필요하면 자세를 준비합니다.
3. **F8**: 학습용 에피소드 시작.
4. 기존 키로 블록에 접근하고 **→** 키로 잡아 들어 올립니다. 실제 동작 키는 기존 코드 기준으로 `w/s`가 X, `a/d`가 Y입니다.
5. 들어 올린 상태를 약 1초 유지합니다.
6. **F9**: 학습용 에피소드 종료.
7. **q**: 기존 조작 코드 종료. **기존 코드의 종료 호밍도 그대로 수행**됩니다. F9 뒤의 이동은 학습 구간에서 제외됩니다.

한 번 실행에 F8/F9 구간 하나를 저장합니다. 다음 에피소드는 `red_s2_002`처럼 새로운 폴더로 다시 실행합니다. 미리보기 창의 `Esc`/터미널 `Ctrl+C`는 수집 중단이며 정상 완료로 표시되지 않습니다. 물리 비상정지를 대체하지 않습니다.

`--gripper-seconds 1.0`은 예시입니다. 실제 집게 닫힘 시간을 촬영으로 측정해 입력하세요. 로봇 상태는 목표 20Hz이며, 실제 수신 속도·공백은 후처리 보고서에서 확인합니다.

### 원본과 보정 영상은 어떻게 저장되나

- `rgb/*.png`: 원본 RGB를 그대로 저장합니다.
- `color_profile.json`: 이 에피소드에 적용할 보정과 카메라 고정 설정을 복사합니다.
- 녹화 미리보기와 `review.mp4`: 보정한 RGB를 보여줍니다.
- `export_hdf5`: 프로필을 읽어 손목 RGB를 **한 번만** 보정하고 학습 HDF5에 넣습니다.
- 정책 실행 때도 `color_calibration.apply_rgb()`를 같은 crop·회전 전에 호출합니다.

조명·노출·화이트밸런스·게인·카메라를 바꾸면 색상표를 다시 찍고 새 프로필을 만드세요. 프로필은 카메라 시리얼·해상도·fps를 검사하고 저장된 설정을 복원합니다. 다른 카메라나 다른 해상도에는 그대로 쓰지 않습니다.

## 6. 영상 검토·시간 정렬까지 완료 — [로컬: Windows PowerShell]

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.preview docs/W9/data/raw/red_s2_001
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.prepare docs/W9/data/raw/red_s2_001
```

`prepare`는 F8~F9 구간만 0.05초 간격으로 맞춥니다. 초기·종료 호밍은 제외합니다. 이후 서버에서 [D405_GUIDE.md의 6번](D405_GUIDE.md#6-서버에서-외부-영상action-생성--hdf5), [학습 안내](D405_TRAINING.md)를 따릅니다.

현재 프로젝트는 외부 영상을 시뮬 Panda로 생성하므로, 자유 조작이 시뮬 작업 공간 밖으로 나가거나 실물 블록 배치가 다르면 변환이 거부될 수 있습니다. reference의 초기 배치와 좌표 보정을 맞춘 집기 에피소드를 수집하세요. 시뮬이 따라가며 같은 블록을 잡아 들 수 있어야 성공 데이터로 저장합니다.

## 7. 서버로 전환 — [로컬 → OASYS]

**여기까지 로컬에서 끝낸 뒤 서버 작업으로 전환합니다.** `review.mp4`와 `alignment_report.json`을 확인한 후 원본 에피소드 폴더 전체와 `data/calibration/`을 OASYS로 보냅니다. `data/`는 Git으로 전송되지 않습니다.

[D405_GUIDE.md 6절](D405_GUIDE.md#6-서버에서-외부-영상action-생성--hdf5)의 **[서버] 폴더 준비 → [로컬] scp 전송 → [서버] HDF5 생성** 순서를 따릅니다. 이후 시뮬·T5·학습은 OASYS의 기존 Cosmos/LIBERO 환경에서 실행합니다.
