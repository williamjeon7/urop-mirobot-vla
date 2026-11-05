# Mirobot_data — 실물 Mirobot 녹화 원본과 수집 방법

2026-11-04부터 새로 수집하는 실물 녹화를 주차 문서(`docs/W*`)와 분리해 여기에 모은다. 이전 녹화(`docs/W9/data/raw/layoutblue1–10` 등)는 옮기지 않는다.

모든 명령은 노트북 PowerShell의 `C:\mirobot-vla`에서 실행한다.

## 폴더 규칙

```text
Mirobot_data/
  W10/                 수집한 주차
    L01_red/           배치 L01에서 빨강을 집은 녹화
    L01_green/
    L01_blue/
    L02_red/
    ...
```

- **주차** — 녹화한 주. 정확한 시각은 각 폴더 `metadata.json`의 `recorded_at`(노트북 현지 시각)에 남는다.
- **배치 번호 `L01`–`L30`** — 블록 세 개를 놓은 장면 하나. 주차가 바뀌어도 번호는 이어서 매기고 다시 쓰지 않는다.
- **색** — 그 녹화에서 실제로 집은 블록(`--color`).
- 평가에 쓸 배치는 여기 녹화에 쓰지 않은 것으로 따로 정한다.
- **`trash/`** — 쓰지 않기로 한 녹화를 지우지 않고 옮겨 두는 곳 (노트북에만, git 제외). 11/04 오전 시험 녹화(L01, L02 일부)와, 정렬 기준을 통과하지 못해 다시 찍은 W10 녹화 5개의 처음 녹화가 여기 있다.

## 수집 방법

### 1. 장치 확인

D405와 Mirobot USB를 노트북에 연결하고, RealSense Viewer와 다른 로봇 조작 프로그램은 닫는다.

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.devices --robot-port COM3 --camera-serial 262422272124 --check
```

`robot_found`와 `camera_found`가 둘 다 `true`여야 한다. 로봇 COM 번호가 다르면 이후 명령의 `--port`를 바꾼다.

### 2. 호밍 — 기계를 처음 켰을 때 반드시

**Mirobot 전원을 켠 뒤에는 녹화 전에 반드시 한 번 호밍한다.** 관절 위치를 끝 스위치로 다시 맞추는 과정이다. 녹화 명령은 호밍하지 않고 초기 자세로만 움직이므로, 호밍을 건너뛰면 위치가 틀어진 채로 녹화된다.

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.home_robot --port COM3
```

- 팔이 크게 움직이므로 주변을 비운다. 녹화 프로그램이 켜져 있을 때는 실행하지 않는다 (같은 포트).
- 마지막에 `Homed; at the initial pose`가 나오면 끝. 팔은 녹화 시작 자세에 멈춘다.
- **다시 호밍할 때:** 어딘가 부딪혔을 때, 로봇이 Alarm 상태가 됐을 때, 시작 화면이 평소와 다르게 틀어져 보일 때.

### 3. 배치 준비 (배치마다)

1. 블록 세 개를 **반듯하게**(회전 없이) 놓는다. 시작 자세의 손목 화면에 셋 다 보여야 하고, 배치마다 위치를 바꾼다. 색마다 왼쪽·가운데·오른쪽, 가까운 쪽·먼 쪽을 고르게 돌린다 (색을 자리로 외우는 지름길을 막기 위해).
2. **L21부터(11/05) 블록 좌표 측정과 위에서 찍는 사진은 생략한다.** 배치 모습은 각 녹화의 D405 첫 프레임 `rgb/00000000.png`(녹화 시작 순간의 시작 자세 화면)으로 남는다. L01–L08은 좌표·사진, L09–L20은 좌표만 기록되어 있다. L21–L30은 미리 정한 좌표에 블록을 놓았으므로 그 좌표를 계획값으로 적었다.

### 4. 녹화 (빨강 → 초록 → 파랑)

색마다 아래 명령을 그대로 쓴다. **배치가 바뀔 때는 맨 끝 `--out Mirobot_data/W10/L01_<색>`에서 `L01`만 그 배치 번호로 바꾼다** (예: `W10/L02_red`). 주차가 바뀌면 `W10`도 바꾼다. 앞부분은 고치지 않는다.

red:

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --teleop --color red --seed 2 --reference docs/W6/poses/pickup-red-s2.jsonl --mapping-gcode trajectories/2026_10_11-w6-pickup-red-s2-e5.gcode --color-profile docs/W9/data/calibration/classic_mini.json --initial-s 40 --open-s 40 --closed-s 60 --gripper-seconds 1.0 --port COM3 --serial 262422272124 --execute --preview --out Mirobot_data/W10/L01_red
```

green:

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --teleop --color green --seed 2 --reference docs/W6/poses/pickup-green-s2.jsonl --mapping-gcode trajectories/2026_10_11-w6-pickup-green-s2-e5.gcode --color-profile docs/W9/data/calibration/classic_mini.json --initial-s 40 --open-s 40 --closed-s 60 --gripper-seconds 1.0 --port COM3 --serial 262422272124 --execute --preview --out Mirobot_data/W10/L01_green
```

blue:

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --teleop --color blue --seed 2 --reference docs/W6/poses/pickup-blue-s2.jsonl --mapping-gcode trajectories/2026_10_11-w6-pickup-blue-s2-e5.gcode --color-profile docs/W9/data/calibration/classic_mini.json --initial-s 40 --open-s 40 --closed-s 60 --gripper-seconds 1.0 --port COM3 --serial 262422272124 --execute --preview --out Mirobot_data/W10/L01_blue
```

색 이름은 명령 안 네 곳(`--color`, `pickup-<색>-s2.jsonl`, `pickup-<색>-s2-e5.gcode`, 폴더 이름)이 같아야 하므로, 다른 색 명령을 고쳐 쓰지 말고 그 색의 명령을 복사한다.

조작 순서:

1. 미리보기 창에 `READY`가 뜰 때까지 기다린다.
2. `←`로 집게를 연다 → `F8`(또는 START REC 버튼)로 녹화 시작.
3. 키보드로 해당 색 블록에 접근해 `→`로 잡고 `↑`로 들어 올린다.
4. **집게를 닫은 뒤 첫 `↑` 명령부터 3초 후 녹화가 자동으로 끝난다.** 먼저 끝내려면 `F9`.
5. `q`로 종료 — 초기 자세로 돌아간 뒤 저장하고 확인용 MP4를 만든다.
6. 집은 블록을 잰 자리로 되돌려 놓고 다음 색을 찍는다.

| 키·버튼 | 동작 |
| --- | --- |
| `w` / `s` | 앞(로봇에서 멀어지는 쪽) / 뒤, 한 번에 5 mm |
| `a` / `d` | 로봇 기준 왼쪽 / 오른쪽 |
| `↑` / `↓` | 위 / 아래 |
| `←` / `→` | 집게 열기 S40 / 닫기 S60 |
| `1/2`, `4/5`, `7/8` | A, B, C 회전 5° |
| `F8` / `F9` | 녹화 시작 / 수동 종료 (미리보기 창 버튼도 같음) |
| `F10` / RESET 버튼 | 지금 시도를 지우고 위로 올린 뒤 초기 자세로 복귀. 같은 폴더에서 F8로 처음부터 다시 찍는다 |
| `v` / `g` / `f` | (선택) 결과 기록: 성공 / 잡았지만 못 듦 / 실패 |
| `q` | 종료·초기 자세 복귀·저장 |

주의:

- **키 입력은 어느 창이 앞에 있든 로봇으로 간다.** 녹화 중에는 다른 창(채팅 등)에 타이핑하지 않는다.
- 터미널에 출력되는 키 설명은 a·d / w·s가 바뀌어 있다. 위 표가 실제 동작이다.
- 미리보기의 `Esc`나 `Ctrl+C`는 녹화만 멈추고 이미 보낸 이동은 멈추지 않는다. 비상시에는 로봇 전원을 끈다.
- 조작 실수는 `F10`(RESET)으로 같은 폴더에서 다시 찍는다. 그때까지 찍힌 프레임은 지워지고, 다시 찍은 녹화가 0번 프레임부터 저장된다.
- **이미 저장된 녹화가 잘못됐으면**(집기 실패, 정렬 검사 미통과 등) `_1`·`_2` 같은 새 이름을 쓰지 않는다. 그 폴더를 `trash/<주차>/`로 옮긴 뒤 같은 명령·같은 이름으로 다시 찍는다. 폴더가 남아 있으면 녹화 명령이 시작 전에 멈추고 덮어쓰지 않는다. `trash`에 이미 같은 이름이 있으면 옮길 때 뒤에 `_old2`처럼 붙인다.
- 녹화가 끝난 뒤에는 팔을 더 움직이지 말고 바로 `q`를 누른다. 끝난 뒤의 오류도 녹화 전체를 실패로 만든다.

### 5. 녹화 뒤 기록

배치마다 **색별 집기 성공 여부**를 넘기면, 세 폴더에 `layout.json`을 넣고 0.05초 단위 정렬을 한다 (L21–L30은 정해 둔 좌표를 계획값으로, 아래 "블록 좌표와 `layout.json`"). 정렬은 70 ms 기준이다 (카메라 실제 저장이 초당 10–11장이라 기본 40 ms로는 실패한다).

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.prepare Mirobot_data/W10/L01_red --max-frame-ms 70
```

### 6. 서버로 전송

배치 5개(녹화 15개)마다 git으로 올린다. PNG·MP4·NPZ·JPG는 Git LFS로 올라간다 (`.gitattributes`).

```powershell
git add -- Mirobot_data
git diff --cached --stat
git commit -m "Mirobot_data W10 L01–L05"
git push
```

`git diff --cached --stat`에 이번 배치 폴더만 있는지 확인한 뒤 커밋한다.

## 블록 좌표와 `layout.json`

블록 좌표는 매트에 인쇄된 숫자로 읽는다.

- **가로**: 매트 아래쪽 눈금. 0 = 로봇 정면 중심선, + = 로봇 기준 왼쪽
- **세로**: 매트 왼쪽 눈금. 로봇 베이스 중심에서 앞으로의 거리. 먼 쪽 경계선이 30

`layout.json`은 서버 좌표계(`paper_top_border_zero_Xup_Yleft_cm`: 먼 쪽 경계선과 0 중심선의 교점이 원점, +X 로봇에서 멀어지는 쪽, +Y 로봇 기준 왼쪽)로 적는다. 변환은 **X = 세로 − 30, Y = 가로**이고 로봇 베이스 중심은 (−30, 0)이다. 읽은 숫자도 `blocks_mat_cm`에 그대로 남긴다.

```json
{
  "layout_id": "L01", "target": "red", "unit": "cm",
  "blocks": {"red": [-6.0, 0.0], "green": [-7.0, -13.5], "blue": [-12.0, -10.5]},
  "blocks_mat_cm": {"red": [0.0, 24.0], "green": [-13.5, 23.0], "blue": [-10.5, 18.0]},
  "yaw_deg": {"red": 0, "green": 0, "blue": 0},
  "photo": "layout.jpg", "estimated": false, "source": "measured",
  "coordinate_frame": {"id": "paper_top_border_zero_Xup_Yleft_cm", "robot_base_center_cm": [-30, 0]},
  "real_success": true
}
```

위 숫자는 형식 예시다. 같은 배치의 세 녹화는 `layout_id`·`blocks`·사진이 같고 `target`·`real_success`만 다르다.

**L21부터(11/05)** 좌표를 재지 않고 위에서 찍는 사진도 없다. 배치 모습은 `photo`가 가리키는 D405 첫 프레임에서 확인한다. L21–L30은 미리 정한 좌표에 블록을 놓았으므로 그 좌표를 적고 `source`를 `"planned"`(재지 않은 계획값)로 둔다.

```json
{
  "layout_id": "L21", "target": "red", "unit": "cm",
  "blocks": {"red": [-5.0, 8.0], "green": [-12.0, 6.0], "blue": [-8.0, -7.0]},
  "blocks_mat_cm": {"red": [8.0, 25.0], "green": [6.0, 18.0], "blue": [-7.0, 22.0]},
  "yaw_deg": {"red": 0, "green": 0, "blue": 0},
  "photo": "rgb/00000000.png", "estimated": false, "source": "planned",
  "coordinate_frame": {"id": "paper_top_border_zero_Xup_Yleft_cm", "robot_base_center_cm": [-30, 0]},
  "real_success": true
}
```

좌표를 정하지 않고 놓은 배치라면 `blocks`·`blocks_mat_cm`·`yaw_deg`·`coordinate_frame`을 `null`, `source`를 `"not_measured"`로 둔다.

## 폴더 안 파일

| 파일 | 내용 |
| --- | --- |
| `rgb/*.png` | 손목 D405 원본 프레임 (색 보정 전) — 학습 데이터의 원천 |
| `frames.jsonl` | 프레임마다 받은 시각·카메라 프레임 번호 |
| `robot.jsonl` | 로봇 상태(위치·`?` 응답 원문)·명령·F8/자동 종료/RESET 표시 |
| `metadata.json` | 카메라 설정, 색, `recorded_at`, 호밍 여부, 버린 시도 수 |
| `capture_result.json` | 녹화 종료 이유 (자동 종료·F9·실패·시간 초과) |
| `reference.jsonl`, `source.gcode`, `color_profile.json` | 좌표 변환 기준과 색 보정 |
| `review.mp4` | 확인용 영상 (학습에 쓰지 않음). `q` 뒤 `...review.mp4: N frames` 줄과 프롬프트가 나올 때까지 기다려야 만들어진다 |
| `layout.json`, `layout.jpg` | 배치 번호·집기 성공 여부(녹화 뒤 추가). 블록 좌표는 L01–L20 실측, L21–L30 계획값. 위에서 찍은 사진(`layout.jpg`)은 L01–L08에만 있다 |
| `aligned.npz`, `alignment_report.json` | 0.05초 정렬 결과 (정렬 뒤 추가) |

녹화 설정(D405 팔뚝 장착, 640×480·30 fps 요청, `classic_mini.json`, 집게 S40/S60·1.0 s)은 영상1–10과 같다. 바꾸면 그 전 녹화와 섞어 학습할 수 없다.

## 문제가 생기면

| 증상 | 조치 |
| --- | --- |
| `Expected one D405, found 0` | D405 USB가 빠졌다. 다시 꽂고 1번 장치 확인. 팔이 움직이며 케이블이 당겨지지 않게 정리 |
| `robot_found: false` | 로봇 USB·전원 확인. COM 번호가 바뀌었으면 `--port` 변경 |
| 시작 화면이 평소와 다름 | 부딪혀 위치가 밀렸을 수 있다. 2번 호밍 후 다시 녹화 |
