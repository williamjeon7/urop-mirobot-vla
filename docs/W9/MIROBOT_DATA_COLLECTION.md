# Mirobot 촬영부터 학습용 데이터 준비까지

> **절차** · 확인 2026-10-29 · 기준 W9 D405 수집 코드, Cosmos 로더 설계 `cosmos-policy@18a2acc`
> Windows에서 색 보정·키보드 촬영·0.05초 시간 정렬을 하고, OASYS에서 Cosmos Policy LIBERO용 데이터를 준비한다.

이번 작업은 **촬영 → 타임스텝 정렬 → 학습용 HDF5·통계·실제 T5 임베딩 준비와 검사**까지입니다. 모델 파인튜닝·정책 평가·실물 추론은 후속 작업입니다. 아래는 실행 방법이며, 이번 영상1~10의 로컬 후처리 결과는 5-3절에 기록했습니다. 서버 검증은 아직 완료하지 않았습니다.

## 1. 어디서 무엇을 실행하나

**로컬**은 D405와 Mirobot USB가 연결된 **Windows 노트북의 PowerShell**입니다. VS Code Remote로 OASYS에 접속한 터미널은 **서버의 Bash**입니다. 촬영 명령은 노트북에서 실행하세요.

| 순서 | 실행 위치 | 할 일 | Python |
| --- | --- | --- | --- |
| 2 | 로컬 Windows | 설치·카메라·로봇 포트 확인 | `docs/W9/.venv/Scripts/python.exe` |
| 3 | 로컬 Windows | 색상표 촬영·보정 프로필 준비 | 같은 W9 환경 |
| 4 | 로컬 Windows | 키보드로 조작하면서 영상·로봇 상태 기록 | 같은 W9 환경 |
| 5 | 로컬 Windows | 영상 검토·0.05초 타임스텝 정렬 | 같은 W9 환경 |
| 6 | 로컬 → 서버 | 원본·보정·정렬 결과 Git push → pull | Git + Git LFS |
| 7 | 서버 OASYS | Panda 시뮬 추종·HDF5 생성 | `cosmos-policy/.venv/bin/python` |
| 8~9 | 서버 OASYS | 구조·실제 로더 검사·통계·실제 T5 준비 | 같은 Cosmos/LIBERO 환경 |

모든 명령은 저장소 루트에서 실행합니다. 예시 경로는 로컬 `C:\mirobot-vla`, 서버 `~/UROP`입니다. 두 컴퓨터에 같은 최신 코드를 준비하고, `.venv`는 OS마다 별도로 사용합니다. 이 저장소의 `common/`, W6 장면과 에셋이 필요하므로 W9 폴더만 복사해서는 실행되지 않습니다.

## 2. 설치와 장치 확인 — 로컬 PowerShell

Python 3.10과 저장소가 준비된 노트북에서 최초 1회 실행합니다.

```powershell
cd C:\mirobot-vla
powershell -ExecutionPolicy Bypass -File docs/W9/d405/setup.ps1
```

설치 스크립트는 W9 가상환경을 준비하고 카메라만 조회합니다. 로봇 이동 명령은 보내지 않습니다. 장치를 다시 확인하려면:

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --list
docs/W9/.venv/Scripts/python.exe -m serial.tools.list_ports -v
```

- **D405**: RealSense USB 장치이며 COM 포트를 쓰지 않습니다. 노트북에서 D405가 조회돼야 합니다.
- **Mirobot**: 시리얼 포트입니다. 아래 명령의 `COM3`는 예시이므로 실제 조회 결과로 바꾸세요.
- **OASYS**: D405가 연결되지 않은 현재 구성에서 `RealSense devices: 0`은 정상입니다. SSH는 노트북 USB를 자동으로 전달하지 않습니다.

RealSense Viewer는 녹화 전에 닫습니다. Python과 동시에 카메라를 열 수 없습니다.

## 3. 색 보정 준비 — 로컬 PowerShell

### 현재 준비된 프로필 — 2026-10-29 실촬영 확인

**`docs/W9/data/calibration/classic_mini.json` 생성·재촬영 검증을 마쳤습니다.** 같은 카메라·조명·장착 상태라면 아래 보정 생성 과정을 반복하지 않고 **4절 촬영으로 진행**합니다. 4절 명령의 `--color-profile`이 개선된 설정을 자동 복원합니다.

기존 78개 설정 비교에 16개 설정을 추가하고, 선형·affine·root-polynomial 모델 및 지각 색 오차 최적화를 비교했습니다. 최종은 **선형광 RGB 3×3 행렬 + 채널별 offset의 affine 모델(`w9-color/2`)**입니다. 모델 비교 시 24회 leave-one-patch-out 교차검증을 사용했고, 표현 범위 밖의 색을 제외한 패치에는 밝기 여유를 두었습니다. 센서 시리얼은 `262422272124`, RGB 640×480·요청 30fps, 노출 33000·게인 16·화이트밸런스 5200·감마 340·채도 56·대비 45입니다. 현재 실측 저장 속도는 약 15fps입니다.

| 확인 | 평균 색 오차 | 최대 색 오차 |
| --- | ---: | ---: |
| 최초 프로필의 생성용 사진, 보정 후 | 7.88 | 26.17 |
| 개선 프로필의 생성용 사진, 보정 후 | 4.76 | 9.15 |
| 개선 프로필의 별도 재촬영 5프레임, 보정 후 | 4.64 | 9.56 |
| 최종 affine 프로필의 생성용 사진, 보정 후 | 3.60 | 7.43 |
| **현재 프로필: 별도 재촬영 8프레임, 보정 후** | **3.62** | **8.31** |

오차는 CIE76 ΔE입니다. 마지막 행은 8프레임 평균 오차의 평균과 전체 패치·프레임 중 최대 오차입니다. 설정 복원 후 15프레임을 버린 뒤 촬영했으며, 검사한 8프레임의 원본 클리핑 검사를 모두 통과했습니다. 보정 후에는 sRGB 범위 밖인 18번 청록 패치를 제외한 패치에서 채널 끝값 발생이 없었습니다. 18번의 기준 Lab을 현재 변환식으로 sRGB로 바꾸면 R이 음수이므로 출력 RGB의 경계 도달을 원본 센서 클리핑과 구분해 기록합니다.

최종 모델은 24패치 전체로 추정했고, 패치를 하나씩 제외하는 교차검증 평균 4.14·최대 7.71을 함께 기록했습니다. 교차검증은 카메라·모델 선택에도 사용했습니다. 재촬영은 같은 표·배치·조명에서의 반복 확인이며, 새로운 색이나 조명의 검증은 아닙니다. 최초 3×3 모델의 고정 6패치 holdout 검사와는 검증 방식이 다릅니다.

- 비교 이미지: `docs/W9/data/calibration/classic_mini.verify.png` (왼쪽 원본 / 오른쪽 보정).
- 재촬영 보고서: `docs/W9/data/calibration/classic_mini.validation.json`.
- 최초 프로필 보관: `docs/W9/data/calibration/initial_profile_backup/`.
- 직전 4.64 프로필 보관: `docs/W9/data/calibration/before_perceptual_20261029_160234/`.
- 최종 검증 촬영: `docs/W9/data/raw/chart_perceptual_verify_001/`.
- 선택 기록: `docs/W9/data/calibration/perceptual_selection.json`.

서버도 최신 `color_calibration.py`와 `color_refinement.py`를 사용해야 합니다. 기존 v1 프로필도 계속 읽을 수 있습니다. 비교한 root-polynomial 방식의 근거는 [Finlayson 등의 원 논문](https://research-portal.uea.ac.uk/en/publications/colour-correction-using-root-polynomial-regression/)이며, 현재 데이터에서는 교차검증 결과를 보고 affine을 채택했습니다.

이 파일들은 원본과 함께 Git에 커밋·push하고 서버에서 pull합니다(6절). PNG·MP4·NPZ·검토용 JPG는 Git LFS로 관리합니다. 다음은 조건이 바뀌어 **새 보정이 필요할 때**의 절차입니다.

### 3-1. 조명·배치 준비

실험실 커튼을 치고 작업 조명을 켠 뒤, 촬영에 사용할 카메라 장착 위치와 블록 배치를 고정합니다. 격자판의 한 칸은 10×10mm이며, 표시해 둔 로봇·블록 초기 위치를 사용합니다.

현재 예시는 **red / seed 2**입니다. 실물 블록 위치와 좌표 보정이 아래 reference·mapping G-code와 맞아야 합니다. 다른 색·seed를 수집하면 `--color`, `--seed`, `--reference`, `--mapping-gcode`를 함께 맞춥니다. 자유롭게 배치한 장면은 나중에 Panda 추종 변환을 통과하지 못할 수 있습니다.

이미 검증한 `docs/W9/data/calibration/classic_mini.json`이 있고 **같은 카메라·조명·장착·해상도·fps·설정**을 유지했다면 4절로 진행합니다. 조건을 바꿨다면 새 프로필을 만듭니다.

### 3-2. ColorChecker 3초 촬영

Calibrite ColorChecker Classic Mini 24패치를 블록이 놓일 위치에 두세요. **가로 6칸 × 세로 4칸**, 갈색 피부 패치는 왼쪽 위, 흰색은 왼쪽 아래, 검정은 오른쪽 아래입니다. 반사·그림자·가림 없이 충분히 크게 찍습니다.

색상표는 학습 에피소드와 구분하기 위해 이름을 직접 지정합니다.

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --out docs/W9/data/raw/chart_recal_001 --seconds 3 --preview --color-profile docs/W9/data/calibration/classic_mini.json
```

기존 폴더는 덮어쓰지 않습니다. 재촬영은 `chart_recal_002`처럼 새 이름으로 실행하고 아래 경로도 바꾸세요. 이 명령은 현재 프로필의 카메라 설정을 복원하고 **원본 PNG를 보정 없이 저장**합니다. 카메라·해상도가 달라 기존 프로필을 사용할 수 없다면 `--color-profile`을 빼고 새 설정부터 검증합니다. 기본 RGB는 640×480, 요청 30fps입니다. 정상 촬영 종료 후 `chart_recal_001/review.mp4`도 자동 생성됩니다.

### 3-3. 네 모서리 선택·보정 프로필 생성

흔들림·반사광이 없는 중간 PNG를 고릅니다. 예시는 10번 프레임입니다.

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.color_calibration fit --image docs/W9/data/raw/chart_recal_001/rgb/00000010.png --camera-metadata docs/W9/data/raw/chart_recal_001/metadata.json --out docs/W9/data/calibration/classic_mini_new.json --model affine --confirm-edition
```

새 출력은 `classic_mini_new.json`입니다. 아래 생성 파일 설명에서 `classic_mini`는 새 프로필 이름에 맞춰 읽으세요. 새 프로필은 별도 촬영 검증 후 채택하며 현재 `classic_mini.json`을 즉시 덮어쓰지 않습니다.

`--confirm-edition`은 사용한 표가 기준값과 맞는 **2014년 11월 이후 Classic 24패치**임을 확인했다는 뜻입니다.

창에서 **색 패치 격자 자체의 모서리**를 왼쪽 위 → 오른쪽 위 → 오른쪽 아래 → 왼쪽 아래 순서로 클릭한 뒤 `Enter`를 누릅니다. 검은 카드 바깥 테두리·로고는 포함하지 않습니다. 다시 선택은 `r`, 취소는 `Esc`입니다.

생성 결과:

```text
docs/W9/data/calibration/
  classic_mini.json             보정 행렬·카메라 설정·오차 보고서
  classic_mini.patches.png      6×4 패치 선택 확인
  classic_mini.comparison.png   왼쪽 원본 / 오른쪽 보정
  classic_mini.corners.json     선택한 네 모서리 (검사 실패 시에도 보관)
  classic_mini.sampling.json    패치별 RGB·암부/밝은 부분 클리핑 검사
```

**오류가 나면 `classic_mini.json`과 `comparison.png`가 생성되지 않을 수 있습니다.** 픽셀 검사·행렬 검증을 통과한 경우에만 보정 프로필을 저장합니다. 모서리를 정상 선택했다면 실패해도 `corners.json`, `patches.png`, `sampling.json`은 남습니다. `sampling.json`의 `low_fraction`은 RGB 중 한 채널이라도 1 이하인 픽셀 비율, `high_fraction`은 254 이상인 비율입니다. 어느 패치든 합친 비율이 2%를 넘으면 중단합니다.

밝은 부분 클리핑은 반사광·과노출을 확인합니다. 암부 클리핑은 패치 선택·그림자·카메라 색 설정을 먼저 확인하며, 무조건 노출을 낮추지 않습니다. 실패한 프로필을 학습 촬영에 사용하지 않습니다. 저장된 모서리로 다시 검사하려면 위 `fit` 명령에 `--corners docs/W9/data/calibration/classic_mini.corners.json`을 추가할 수 있습니다. 다른 사진이나 위치가 바뀐 표에는 모서리를 새로 선택하세요.

먼저 `patches.png`의 패치 순서를 확인합니다. `comparison.png`에서 회색의 색 치우침이 줄고, RGB 패치가 과포화되거나 검게 뭉개지지 않는지 봅니다. affine 모드는 `cross_validation_mean`·`cross_validation_max`와 `all_mean_after`·`all_max_after`를 확인하고, 프로필을 고정한 뒤 새 촬영에서 개선이 유지되는지 검사합니다. 원본 클리핑 검사와 교차검증 개선 검사를 통과하지 못하면 프로필을 저장하지 않습니다. 기본 matrix 모드의 검사는 별도의 `heldout_mean_before`·`heldout_mean_after`를 사용합니다.

다른 프레임에 적용해 확인하려면:

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.color_calibration apply --image docs/W9/data/raw/chart_recal_001/rgb/00000020.png --profile docs/W9/data/calibration/classic_mini_new.json --out docs/W9/data/calibration/check_second_frame.png
```

프로필·확인 이미지가 이미 있으면 새 출력 이름을 사용합니다. 실제 블록의 명암·질감을 유지하며 색 치우침을 줄이는 보정입니다. 블록 RGB를 원색 값으로 강제 변환하지 않습니다.

## 4. 영상1부터 자동 번호로 촬영 — 로컬 PowerShell

### 4-1. 저장 방식

촬영 명령에서 **`--out`을 생략**하면 `docs/W9/data/raw/`의 기존 번호 중 최댓값 다음으로 저장합니다. 같은 명령을 다시 실행하면 다음 번호를 사용합니다.

```text
docs/W9/data/raw/
  chart_001/                 색상표, 번호 계산에서 제외
  영상1/
    영상1.mp4                정상 촬영 종료 후 자동 생성되는 확인 영상
    metadata.json            설정·색·seed·완료 여부
    frames.jsonl             프레임 번호·PNG 경로·시각
    rgb/00000000.png         원본 RGB PNG
    robot.jsonl              로봇 상태·명령·F8/F9 시각
    serial.jsonl             시리얼 기록
    reference.jsonl          시뮬 초기 자세·블록 배치 기준
    source.gcode             좌표 변환 기준
    color_profile.json       사용한 보정 프로필 복사본
  영상2/
    영상2.mp4
    ...
```

`영상1`과 `영상3`이 있으면 다음은 `영상4`입니다. 중단된 폴더도 보존하고 번호를 건너뜁니다. 다른 저장 위치를 쓰려면 `--out-root 다른/상위폴더`를 추가하세요. 직접 이름을 지정하는 `--out`과는 함께 쓰지 않습니다.

MP4는 검토용입니다. 학습 변환에는 **PNG·JSONL·metadata·reference·보정 파일을 포함한 폴더 전체**가 필요합니다. 원본 PNG에는 보정을 입히지 않고, 미리보기·MP4와 HDF5 변환에 보정을 적용합니다.

### 4-2. 키보드 조작·녹화 시작

`COM3`는 실제 로봇 포트를 확인해 맞추세요. 집게는 현재 조작 코드의 열기 S40·닫기 S60을 사용합니다. 녹화 전에 `←`로 열어 둔 상태에서 `--initial-s 40 --open-s 40 --closed-s 60`을 사용하세요. 이 옵션 자체가 집게를 움직이지는 않습니다. **`--gripper-seconds 1.0`은 `gripper_openclose.mp4`에서 첫 번째 닫기·열기 한 쌍을 제외한 7회 동작의 측정 중앙값(1.0초)**입니다. 측정 구간과 한계는 [그리퍼 측정 기록](GRIPPER_CALIBRATION.md)에 정리했습니다.

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --teleop --color red --seed 2 --reference docs/W6/poses/pickup-red-s2.jsonl --mapping-gcode trajectories/2026_10_11-w6-pickup-red-s2-e5.gcode --color-profile docs/W9/data/calibration/classic_mini.json --initial-s 40 --open-s 40 --closed-s 60 --gripper-seconds 1.0 --port COM3 --execute --preview
```

터미널에 실제 저장 폴더가 출력됩니다. `--mapping-gcode`는 좌표 변환 머리말만 읽으며 해당 궤적을 자동 재생하지 않습니다. 이 명령은 기존 `robot/inverse_kinematics.py`를 실행하므로 **시작 시 호밍·초기 이동, q 종료 시 호밍이 일어납니다.** 작업 공간을 먼저 준비하세요. 기존 조작기를 별도 터미널에서 동시에 실행하지 않습니다.

**`--preview`를 포함한 위 명령을 그대로 실행하면 카메라 영상이 실시간으로 보입니다.** 미리보기 아래의 버튼으로 녹화를 제어합니다. 호밍 중에도 화면은 보이지만 PNG·MP4용 프레임을 저장하지 않습니다.

| 버튼·상태 | 의미 |
| --- | --- |
| `Homing / initial move...` | 시작 버튼 비활성화. 초기 위치 도착을 확인하는 중 |
| `START REC (F8)` | 녹화 시작. 초기 위치에서 새 상태 응답 3회가 연속 Idle이고 목표와 2mm·2° 이내일 때 활성화 |
| `STOP REC (F9)` | 녹화 종료. 카메라 실시간 화면은 계속 표시 |
| `STOPPED` | `q`를 눌러 조작기를 종료하면 MP4 생성·저장이 완료됨. 종료 호밍은 영상에 저장하지 않음 |

버튼·상태 글자는 미리보기에만 표시하며 원본 PNG나 확인용 MP4, 학습 영상에는 넣지 않습니다. 버튼은 마우스로 클릭하고, 키보드 F8/F9도 같은 기능으로 사용할 수 있습니다. `--preview`를 빼면 창 없이 F8/F9로 조작합니다.

| 키 | 동작 |
| --- | --- |
| `w` / `s` | X 증가 / 감소 |
| `a` / `d` | Y 증가 / 감소 |
| `↑` / `↓` | Z 증가 / 감소 |
| `←` / `→` | 집게 열기 / 닫기 |
| `1` / `2`, `4` / `5`, `7` / `8` | 각각 A, B, C 각도 증가 / 감소 |
| `F8` / `F9` | 녹화·학습 에피소드 시작 / 종료 (화면 버튼과 동일) |
| `q` | 조작기 종료·기존 종료 호밍 |

한 에피소드의 순서:

1. 실시간 카메라 화면을 보며 호밍·초기 이동이 끝나고 `READY`가 표시될 때까지 기다립니다.
2. `←`로 집게를 열어 초기 상태 S40을 맞추고 준비 자세를 잡습니다.
3. **`START REC (F8)` 버튼**을 클릭하거나 `F8`을 한 번 눌러 녹화·학습 구간을 시작합니다.
4. 블록에 접근하고 `→`로 집은 뒤 들어 올립니다.
5. 들어 올린 상태를 약 1초 유지하고 **`STOP REC (F9)` 버튼**을 클릭하거나 `F9`를 한 번 누릅니다.
6. 녹화가 멈춘 것을 확인하고 `q`로 종료합니다. 종료 호밍과 파일 저장·MP4 생성이 끝날 때까지 기다립니다. 종료 버튼만 누른 상태에서는 프로그램과 실시간 미리보기가 계속 실행 중입니다.
7. 다음 촬영은 블록 배치를 복원하고 같은 명령을 다시 실행합니다. 번호는 자동 증가합니다.

한 번 실행에 F8~F9 구간 하나입니다. `Esc`나 `Ctrl+C`는 수집 중단이며 정상 완료로 표시하지 않습니다. 이미 보낸 이동을 즉시 취소하는 비상정지가 아니므로 물리 비상정지에 접근할 수 있게 합니다. 자동 G-code 모드의 Z 하한 검사는 이 키보드 모드에 적용되지 않고 기존 조작기의 이동 범위를 사용합니다.

## 5. Alignment: 영상 확인·0.05초 타임스텝 정렬 — 로컬 PowerShell

### 5-1. 영상 검토와 alignment 실행

여기서 **alignment는 PNG 프레임·로봇 상태·집게 명령을 같은 20Hz 시간축에 맞추는 후처리**입니다. 프로젝트 루트 `C:\mirobot-vla`에서 실행합니다. MP4를 여는 명령과 alignment 명령은 별개입니다.

**이번 영상1~10은 5-3절의 70ms 기준으로 이미 정렬했습니다.** 기존 결과를 사용할 때는 이 절의 기본 40ms 명령을 다시 실행하지 않고 6절로 진행합니다. 아래 명령은 새 촬영분의 기본 품질 검사에 사용합니다.

아래 `영상1`은 **방금 터미널에 출력된 폴더명**으로 바꿉니다. PowerShell에서 영상을 열어 목표 블록을 실제로 잡아 들었는지, 손목 화면·색 보정·블록 배치가 정상인지 확인합니다.

```powershell
Start-Process "docs/W9/data/raw/영상1/영상1.mp4"
```

확인 후 아래 명령이 실제 alignment를 수행합니다.

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.prepare "docs/W9/data/raw/영상1"
```

영상1~10을 한꺼번에 정렬하고 실패한 번호를 확인하려면:

```powershell
cd C:\mirobot-vla
$failedEpisodes = @()
foreach ($episodeNumber in 1..10) {
    & docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.prepare "docs/W9/data/raw/영상$episodeNumber"
    if ($LASTEXITCODE -ne 0) { $failedEpisodes += $episodeNumber }
}
if ($failedEpisodes.Count -gt 0) {
    Write-Warning "Alignment 실패: 영상 $($failedEpisodes -join ', ')"
} else {
    Write-Host "영상1~10 alignment 완료"
}
```

성공하면 각 원본 폴더에 `aligned.npz`와 `alignment_report.json`이 생깁니다. 실패한 에피소드는 학습용 정렬이 완료된 것이 아닙니다. `Camera frame too far from grid`는 가장 가까운 PNG도 정렬 시각과 기본 허용값 40ms보다 멀다는 뜻입니다. 원본의 프레임 누락·실제 저장 속도를 확인하고, 통과만을 위해 허용값을 늘리지 않습니다.

### 5-2. 출력과 품질 검사

MP4 생성에 실패했거나 중단된 기록을 검토해야 한다면 PNG를 보존한 상태에서 다시 만들 수 있습니다. 기존 MP4는 덮어쓰지 않습니다.

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.preview "docs/W9/data/raw/영상1"
```

`prepare`는 F8~F9 범위만 0.05초(20Hz)로 정렬하며 시작·종료 호밍을 제외합니다. 같은 폴더에 `aligned.npz`와 `alignment_report.json`을 만듭니다. MP4를 0.05초 길이의 여러 파일로 자르는 방식이 아닙니다.

| 칸 | 관측: 손목 RGB·로봇 상태 | 다음 action의 목표 |
| --- | --- | --- |
| 0 | 시작 시각 t | t+0.05초 자세 |
| 1 | t+0.05초 | t+0.10초 자세 |
| 2 | t+0.10초 | t+0.15초 자세 |

현재 관측을 먼저 저장하고 다음 자세를 action 목표로 붙입니다. 최종 자세는 앞선 action의 목표로만 사용합니다. 로봇 위치는 선형 보간, 회전은 쿼터니언 SLERP, 집게는 명령·측정한 이동 시간으로 추정합니다.

`alignment_report.json`에서 다음을 확인합니다.

| 항목 | 의미·기본 검사 |
| --- | --- |
| `steps` / `dt` | 최소 16 action, 간격 0.05초 |
| `robot_hz_median` | 실제 상태 수신 속도, 목표 20Hz |
| `max_robot_gap_ms` | 기본 150ms 초과 공백은 거부 |
| `max_frame_error_ms` | 관측 시각과 가장 가까운 실제 프레임의 차이, 기본 40ms 초과는 거부 |
| `repeated_frames` | 여러 타임스텝에 같은 PNG가 선택된 횟수 |
| `skipped_camera_frame_numbers` | 카메라 프레임 번호 누락 수 |

시각은 PC 수신 기준이며 정확한 센서 노출 시각을 보장하지 않습니다. 낮은 수신 속도를 보간해도 새 측정 정보가 생기지 않습니다. 더 엄격히 확인하려면 `--max-state-gap-ms 75`를 추가합니다. `--camera-latency-ms`는 별도로 측정한 지연이 있을 때만 사용합니다. 검사 실패 시 먼저 원본·수신 속도·공백을 확인하세요.

**`aligned.npz`는 아직 학습용 HDF5가 아닙니다.** 다음 서버 작업에서 외부 영상과 Panda action을 생성합니다.

### 5-3. 이번 영상1~10의 후처리 결과와 재현 방법

2026-10-29 수집한 영상1~10은 사용자가 실물 집기 성공을 확인했습니다. 각 `metadata.json`에 `real_success: true`와 확인 출처를 기록했습니다. 원본 PNG·MP4·로봇 로그는 유지했습니다.

실제 PNG 저장 속도는 약 10~11fps여서 기본 40ms 프레임 차이 검사는 10개 모두 실패했습니다. 이번 배치는 저장 프레임 간격(최대 약 139ms)에 맞춰 **프레임 허용 차이만 명시적으로 70ms**로 선택해 정렬했습니다. 로봇 공백 기준은 기존 150ms를 유지했습니다. 이것은 기본 품질 기준을 통과한 결과와 구별해야 합니다. 실제 가장 가까운 프레임 차이는 약 55~67ms이며, 원본의 시간 해상도가 향상된 것은 아닙니다. 다음 촬영에서는 실제 저장 속도를 높이고 기본 40ms 기준을 다시 확인합니다.

다음 명령으로 PNG 전체 디코딩·MP4 프레임 수·보정 프로필·정렬 배열·입력 해시를 검사하고 동일한 결과를 재현할 수 있습니다. 기존 파생 결과를 재생성하므로 현재 결과를 유지하려면 재실행하지 않아도 됩니다.

```powershell
docs/W9/.venv/Scripts/python.exe docs/W9/data/postprocess/finish_local.py --max-frame-ms 70 --real-success-reviewed
```

`--real-success-reviewed`는 검토 완료 사실을 기록하는 옵션입니다. 새 촬영분에 성공 확인 없이 사용하지 않습니다. 각 에피소드에 `aligned.npz`, `alignment_report.json`, `postprocess_report.json`을 만들고, 전체 결과는 `docs/W9/data/postprocess/summary.json`에 저장합니다. 보고서의 `accepted_max_frame_ms`, `default_frame_limit_passed`, `steps_exceeding_default_frame_limit`, `repeated_frames`를 서버에서도 함께 확인합니다.

로컬에서 PNG 전체 디코딩, MP4 전체 디코딩과 PNG 개수 일치, 보정 프로필 로드를 검사했습니다. 정렬 결과의 배열 길이·형상·유한값·쿼터니언 정규화·입력 SHA256도 확인했습니다. 보정된 검토용 스냅샷은 `docs/W9/data/postprocess/videoN_review.jpg`에 있습니다.

| 영상 | action 수 | 최대 프레임 차이(ms) | 기본 40ms 초과 step 수 |
| --- | ---: | ---: | ---: |
| 1 | 322 | 63.6 | 59 |
| 2 | 399 | 57.9 | 51 |
| 3 | 366 | 57.8 | 34 |
| 4 | 341 | 57.7 | 41 |
| 5 | 383 | 56.8 | 41 |
| 6 | 529 | 67.1 | 85 |
| 7 | 584 | 57.5 | 65 |
| 8 | 461 | 54.6 | 53 |
| 9 | 480 | 55.5 | 60 |
| 10 | 518 | 61.9 | 54 |

합계 **4,383 actions**입니다. 로컬 후처리는 완료했으며 **Panda 추종·HDF5 생성·Cosmos 로더 검사·T5 생성은 아직 실행하지 않았습니다.** 서버에서는 아래 6절부터 이어 갑니다.

## 6. 원본과 보정 파일 공유 — Git push → pull

**Windows에서 촬영·정렬 → Git commit·push → OASYS에서 Git pull** 순서입니다. `docs/W9/data/`는 Git 추적 대상으로 설정돼 있고, PNG·MP4·NPZ·검토용 JPG는 `.gitattributes`에 따라 Git LFS로 관리합니다. 별도 파일 전송이나 `git add -f`는 필요하지 않습니다.

**실행 위치 확인:** `PS C:\...>`는 로컬 Windows PowerShell, `<USER>@OASYS:~/UROP$`는 서버 Bash입니다. 서버에서는 아래 6-2절을 실행합니다. 로컬 촬영·업로드는 Windows 시작 메뉴에서 PowerShell을 열어 실행하세요. Windows 경로 `C:\mirobot-vla`는 노트북의 실제 저장소 경로로 바꿉니다.

### 6-1. 로컬 Windows PowerShell: 커밋·push

촬영과 5절 정렬을 마친 뒤 실행합니다. `영상1`은 방금 촬영한 폴더명으로 바꾸세요. MP4뿐 아니라 **PNG·JSONL·metadata·reference·보정·정렬 결과를 포함한 에피소드 폴더 전체**를 추가합니다.

Git LFS가 설치돼 있어야 하며, 각 컴퓨터에서 최초 1회 `git lfs install`을 실행합니다.

```powershell
cd "C:\mirobot-vla"
git lfs install
git branch --show-current
git add -- "docs/W9/data/raw/영상1" docs/W9/data/calibration
git add -- docs/W9/data/postprocess
git diff --cached --stat
git status --short
```

추가할 파일이 맞는지 확인한 뒤 커밋·push합니다. `.venv`는 각 컴퓨터에서 별도로 사용합니다.

```powershell
git commit -m "Add Mirobot episode 1 and calibration"
git push
```

push 과정에서 PNG·MP4·NPZ·검토용 JPG의 LFS 데이터도 업로드됩니다. 오류 없이 완료됐는지 확인합니다. 영상1~10 전체를 올릴 때는 `git add -- docs/W9/data/raw docs/W9/data/calibration docs/W9/data/postprocess`로 원본과 후처리 결과를 함께 추가합니다. 추가 촬영분도 새 에피소드 폴더를 같은 방식으로 커밋합니다. 다른 노트북에서 같은 영상 번호를 만들었다면 먼저 폴더명을 구분합니다.

### 6-2. 서버 OASYS Bash: pull·파일 확인

로컬에서 push한 **같은 브랜치**에서 실행합니다. 서버에도 Git LFS를 설치하고 최초 1회 `git lfs install`을 실행합니다.

```bash
cd ~/UROP
git lfs install
git branch --show-current
git status --short
git pull --ff-only
git lfs pull
ls -lh "docs/W9/data/raw/영상1/"
ls -lh docs/W9/data/calibration/classic_mini.json
```

`git pull`이 로컬 변경이나 브랜치 분기로 중단되면 해당 변경부터 정리합니다. `git lfs pull`은 PNG·MP4·NPZ·검토용 JPG의 실제 내용을 내려받습니다.

`영상1`은 업로드한 에피소드 이름으로 바꾸세요. 폴더에 `rgb/`, `metadata.json`, `frames.jsonl`, `robot.jsonl`, `reference.jsonl`, `source.gcode`, `color_profile.json`이 있어야 합니다. 5절 정렬을 마쳤다면 `aligned.npz`와 `alignment_report.json`도 확인합니다. 파일이 준비되면 7절로 진행합니다.

이번 영상1~10은 이미 계산된 `aligned.npz`를 사용합니다. 각 에피소드의 `postprocess_report.json`과 전체 `docs/W9/data/postprocess/summary.json`도 함께 확인합니다. 서버에서 `prepare`를 옵션 없이 다시 실행하면 이번 배치는 기본 40ms 검사에서 실패합니다.

입력 해시 검사는 Windows의 CRLF와 Linux의 LF 줄바꿈 차이를 허용하므로 Git으로 옮겼다는 이유만으로 다시 정렬할 필요는 없습니다. 원본 로그·metadata·reference·보정의 실제 내용이 바뀌었다면 정렬을 다시 해야 합니다.

### 6-3. 원본만 올라온 경우: 서버에서 정렬

`export_hdf5`에서 `FileNotFoundError: .../aligned.npz`가 발생하면 정렬 결과가 준비되지 않은 상태입니다. 로컬에서 생성한 두 정렬 파일을 커밋·push하고 서버에서 pull하거나, 원본이 모두 있는 서버에서 직접 정렬할 수 있습니다. 이 작업에는 카메라·로봇 연결이나 시뮬레이터가 필요하지 않습니다.

**이번 영상1~10을 재현할 때만** 다음 명령을 실행합니다. 기존 파생 결과를 재생성하며, 5-3절에 기록한 70ms 허용 차이를 명시합니다. 이미 기록된 성공 확인은 유지하므로 `--real-success-reviewed`를 다시 지정할 필요는 없습니다.

```bash
cd ~/UROP
cosmos-policy/.venv/bin/python docs/W9/data/postprocess/finish_local.py \
  --max-frame-ms 70
```

**새 촬영분**을 서버에서 정렬할 때는 다음 기본 40ms 명령을 사용합니다. `영상1`은 새 에피소드 폴더명으로 바꿉니다.

```bash
cd ~/UROP
cosmos-policy/.venv/bin/python -m docs.W9.d405.prepare "docs/W9/data/raw/영상1"
ls -lh "docs/W9/data/raw/영상1/aligned.npz" "docs/W9/data/raw/영상1/alignment_report.json"
```

`prepare`가 정상 종료해 두 파일이 생성된 경우에만 7절을 실행합니다. `Camera frame too far from grid`는 실제 카메라 프레임과 20Hz 관측 시각의 차이가 기본 40ms를 초과했다는 뜻입니다. 이 경우 정렬 파일을 생성하지 않습니다. 원본 수신 속도·프레임 공백을 확인하고 촬영 조건을 개선한 뒤 다시 수집합니다. 누락 파일을 임의로 만들거나, 검사 통과만을 위해 오차 한계를 높이지 않습니다.

### 6-4. 선택 사항 — 로컬 PowerShell: scp로 직접 전송

Git LFS 대신 직접 복사할 때만 사용합니다. 먼저 서버에서 `mkdir -p ~/UROP/docs/W9/data`로 받을 폴더를 만들고, 아래 `OASYS_HOST`를 평소 쓰는 실제 SSH 주소·별칭으로 바꿉니다.

```powershell
cd C:\mirobot-vla
scp -r docs/W9/data/raw docs/W9/data/calibration docs/W9/data/postprocess <USER>@OASYS_HOST:~/UROP/docs/W9/data/
```

`.venv`는 보내지 않습니다. 이 명령은 raw 전체를 복사하므로 이후 추가 촬영분은 해당 에피소드 폴더만 서버의 `docs/W9/data/raw/`로 보내도 됩니다. 서로 다른 노트북·저장 위치에서 같은 번호를 만들었다면 서버의 기존 폴더와 충돌하지 않도록 구분해서 보관합니다.

**이후 명령은 서버 Bash에서 실행합니다.**

## 7. Panda 추종·HDF5 변환 — 서버 Bash

이미 설치된 **Cosmos/LIBERO 환경과 에셋**을 사용합니다. 아래는 `~/UROP/cosmos-policy/.venv`가 준비된 경우입니다. 실제 설치 위치가 다르면 Python 경로를 바꾸세요. Windows 수집용 가상환경과 다르며, 수집용 requirements로 서버 환경을 덮어쓰지 않습니다.

```bash
cd ~/UROP
ls "docs/W9/data/raw/영상1/"
cosmos-policy/.venv/bin/python -m docs.W9.d405.export_hdf5 \
  "docs/W9/data/raw/영상1" \
  --out docs/W9/data/hdf5/mirobot_real \
  --real-success --layout-confirmed
```

`--real-success`는 검토 영상에서 **실물 목표 블록 집기 성공**을 확인했다는 뜻입니다. `--layout-confirmed`는 **실물 배치와 좌표 보정이 reference와 일치**함을 확인했다는 뜻입니다. 확인한 에피소드에만 지정합니다.

이번 영상1~10은 모두 같은 seed 2/reference를 사용합니다. 실물 집기 성공은 확인됐지만 실물 배치와 reference 배치·좌표 매핑의 일치는 별도로 검증하지 않았습니다. 위치를 옮긴 에피소드는 해당 실물 배치와 맞는 reference/매핑이 필요한지 먼저 확인합니다. reference를 수정하면 입력 해시가 바뀌므로 alignment도 다시 계산해야 합니다. `--layout-confirmed`를 일괄로 가정하지 않습니다.

변환 시 Panda가 실물 궤적을 따라가며 외부 RGB와 OSC_POSE action을 생성합니다. 손목 RGB는 실물 D405 영상입니다. 실물 관절각이나 XYZ(mm)를 그대로 action으로 넣지 않습니다.

검사 조건:

- 시뮬 초기 손 자세·블록 배치가 reference와 일치해야 합니다.
- 현재 시뮬 관측을 저장한 뒤 다음 칸의 실물 자세를 목표로 이동합니다.
- 마지막 0.5초 동안 시뮬도 목표 블록을 잡고 들어 올린 상태여야 합니다.
- 기본 추종 오차 한계는 실물 환산 위치 5mm·자세 2°입니다. 실패하면 `export_report.json`을 확인하고 배치·보정·동작을 검토합니다. 통과를 위해 한계를 임의로 올리지 않습니다.

D405 RGB는 색 보정 후 중앙 정사각 crop → 256×256으로 변환합니다. 장착 방향에 따라 `--rotate 90`, `180`, `270`(반시계 방향)을 추가할 수 있습니다. 실물 영상에 시뮬용 상하 flip을 일괄 적용하지 않습니다. 후속 추론에서도 같은 보정·crop·회전을 사용해야 합니다.

출력 예시:

```text
docs/W9/data/hdf5/mirobot_real/
  MIROBOT_video1_SCENE1_pick_up_the_red_block_on_the_table_demo.hdf5

data/demo_0/obs/agentview_rgb      (T,256,256,3) uint8    시뮬 외부 RGB
data/demo_0/obs/eye_in_hand_rgb    (T,256,256,3) uint8    실물 D405 손목 RGB
data/demo_0/actions               (T,7) float32         Panda OSC_POSE
data/demo_0/robot_states          (T,9) float32         손가락2+위치3+xyzw4
```

한글 원본 폴더 `영상1`은 HDF5 이름에서 `video1`로 바꾸며 원본 이름은 속성에 보존합니다. 파일 이름의 `SCENE1` 뒤가 지시문이므로 임의로 바꾸지 않습니다. 여러 에피소드를 `mirobot_real/` 아래에 두고 7절을 각 에피소드에 반복합니다. 기존 HDF5는 덮어쓰지 않습니다.

## 8. 구조·실제 Cosmos 로더·통계 검사 — 서버 Bash

최종으로 사용할 에피소드를 모은 뒤 실행합니다.

```bash
cosmos-policy/.venv/bin/python -m docs.W9.d405.check_dataset docs/W9/data/hdf5
cosmos-policy/.venv/bin/python -m tools.check_cosmos_dataset \
  --data-dir docs/W9/data/hdf5 --recompute-stats
```

첫 검사는 영상·action·상태의 차원, 자료형, 유한값, 쿼터니언, 타임스텝과 지시문을 확인합니다. 두 번째는 실제 `LIBERODataset`으로 에피소드·step 수·지시문·샘플 모양을 확인하고 정규화 통계를 만듭니다.

두 번째 검사기는 **임시 가짜 T5**로 샘플 모양만 확인합니다. 이것만 통과한 상태는 학습 준비 완료가 아닙니다. 데이터가 바뀌면 통계를 다시 계산하세요. `dataset_statistics.json`과 생성되는 `dataset_statistics_post_norm.json`을 보관합니다. 새 데이터 통계와 기존 LIBERO 통계 중 무엇을 학습에 적용할지는 데이터 범위와 함께 기록합니다.

Panda 시뮬 HDF5도 섞는다면 같은 data root의 `panda_sim/` 아래에 둡니다. 로더는 step 단위로 샘플링하므로 에피소드 90개/10개가 step 비율 90/10을 보장하지 않습니다. 출력의 suite별 step 수를 확인합니다.

검증용 데이터를 분리할 때는 프레임이 아닌 **에피소드·배치(seed) 단위**로 나누고, 검증 에피소드는 학습 data root 밖에 둡니다. 같은 배치의 색만 바꾼 에피소드도 같은 분할에 둡니다.

## 9. 실제 지시문 T5 임베딩 준비·검사 — 서버 Bash

HDF5를 최종 구성한 뒤 실행합니다. 지시문은 소문자·마침표 없이 `pick up the red block on the table`처럼 파일 이름에서 추출됩니다. 글자·대소문자·마침표까지 임베딩 키와 정확히 같아야 합니다.

서버에 T5-11B 캐시와 GPU 메모리가 준비된 경우:

```bash
cosmos-policy/.venv/bin/python -m docs.W9.d405.make_t5 docs/W9/data/hdf5
```

캐시가 없다면 대용량 T5-11B 다운로드와 GPU 메모리를 준비한 뒤 아래 명령을 사용합니다. 정책 체크포인트 다운로드는 이번 단계에 필요하지 않습니다.

```bash
cosmos-policy/.venv/bin/python -m docs.W9.d405.make_t5 docs/W9/data/hdf5 --allow-download
```

둘 중 환경에 맞는 명령 하나를 실행합니다. 서버 Cosmos 환경에 `torch`, `transformers`, `sentencepiece`가 필요합니다. 출력은 `docs/W9/data/hdf5/t5_embeddings.pkl`입니다. 이미 있으면 덮어쓰지 않으므로 기존 지시문을 모두 포함하는지 검사하고, 새 지시문이 추가됐다면 기존 파일을 별도 보관한 뒤 다시 생성합니다.

```bash
cosmos-policy/.venv/bin/python -m docs.W9.d405.check_dataset docs/W9/data/hdf5 \
  --t5 docs/W9/data/hdf5/t5_embeddings.pkl
```

지시문 누락·잘못된 차원·0으로 채운 가짜 임베딩이 없어야 합니다. T5 생성·이 검사는 학습 실행이 아닙니다.

## 10. 이번 작업 완료 기준

- [ ] 각 에피소드 원본 PNG·시각·로봇 상태·명령·reference·보정 프로필을 보관했다.
- [ ] MP4로 실물 목표 블록 집기 성공·초기 배치를 확인했다.
- [ ] `aligned.npz`와 `alignment_report.json`으로 F8~F9 구간의 0.05초 정렬·공백·지연을 확인했다.
- [ ] Panda 추종·시뮬 집기·추종 오차를 통과한 HDF5를 생성했다.
- [ ] 최종 데이터에 대해 구조 검사·실제 Cosmos 로더 샘플 검사를 통과하고 통계를 보관했다.
- [ ] 실제 지시문 T5 임베딩을 만들고 검사를 통과했다.
- [ ] 사용한 색·seed·집게 시간·카메라 설정·보정·회전·데이터 분할·코드 버전을 함께 기록했다.

여기까지가 **Cosmos Policy LIBERO에 학습 가능한 데이터를 준비하는 범위**입니다. 실제 학습 성능이나 실물 성공률은 후속 학습·평가에서 확인합니다.

## 11. 막혔을 때

| 증상 | 확인할 것 |
| --- | --- |
| 로컬에서 D405 0대 | USB 연결, Viewer 종료, `capture --list` |
| 로봇 포트 연결 실패 | `serial.tools.list_ports -v`, 실제 COM 번호, 다른 조작기 종료 |
| 보정 프로필 설정 불일치 | 같은 카메라·해상도·fps인지 확인, 조명을 바꿨다면 재보정 |
| F8/F9 구간 오류 | 한 번 실행에 시작 1회·종료 1회, 이후 q로 정상 종료했는지 확인 |
| PNG는 있고 MP4가 없음 | 촬영 완료 여부·오류 확인 후 `preview`로 재생성, 원본 보존 |
| 시간 정렬 실패 | 상태 수신 공백·프레임 지연·완료 여부·reference 일치 확인 |
| HDF5 변환 실패 | 실물 배치·좌표 보정·시뮬 작업 공간·추종 오차·시뮬 집기 확인 |
| T5 캐시 없음 | 서버의 로컬 모델 경로를 `--model`로 지정하거나 다운로드 준비 후 `--allow-download` |
| 출력이 이미 존재함 | 원본·기존 결과를 보관하고 새 출력 이름 사용, 번호 폴더 수동 재사용 금지 |

서버 환경이 아직 없다면 기존 설치 기록 [D405_INSTALLATION.md](D405_INSTALLATION.md)와 [D405_TRAINING.md](D405_TRAINING.md) 1절을 참고합니다. 세부 설계 근거는 [DATASET_HDF5.md](DATASET_HDF5.md), [FOLLOW.md](FOLLOW.md)에, 후속 학습 절차는 [D405_TRAINING.md](D405_TRAINING.md) 4절 이후에 남겨 둡니다.
