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

1. 블록 세 개를 **반듯하게**(회전 없이) 놓는다. 시작 자세의 손목 화면에 셋 다 보여야 하고, 배치마다 위치를 바꾼다.
2. 세 블록 중심 좌표를 매트에 인쇄된 숫자로 **(가로, 세로)** cm, 0.5 cm 단위로 읽어 둔다 (아래 "블록 좌표").
3. 블록과 눈금이 보이게 **위에서 사진을 한 장** 찍는다.

### 4. 녹화 (빨강 → 초록 → 파랑)

`<c>` 네 곳을 같은 색(`red` / `green` / `blue`)으로, `L01`을 그 배치 번호로 바꾼다.

```powershell
docs/W9/.venv/Scripts/python.exe -m docs.W9.d405.capture --teleop --color <c> --seed 2 --reference docs/W6/poses/pickup-<c>-s2.jsonl --mapping-gcode trajectories/2026_10_11-w6-pickup-<c>-s2-e5.gcode --color-profile docs/W9/data/calibration/classic_mini.json --initial-s 40 --open-s 40 --closed-s 60 --gripper-seconds 1.0 --port COM3 --serial 262422272124 --execute --preview --out Mirobot_data/W10/L01_<c>
```

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
| RESET 버튼 | 지금 시도를 버리고 위로 올린 뒤 초기 자세로 복귀. 같은 폴더에서 F8로 다시 찍는다 |
| `v` / `g` / `f` | (선택) 결과 기록: 성공 / 잡았지만 못 듦 / 실패 |
| `q` | 종료·초기 자세 복귀·저장 |

주의:

- **키 입력은 어느 창이 앞에 있든 로봇으로 간다.** 녹화 중에는 다른 창(채팅 등)에 타이핑하지 않는다.
- 터미널에 출력되는 키 설명은 a·d / w·s가 바뀌어 있다. 위 표가 실제 동작이다.
- 미리보기의 `Esc`나 `Ctrl+C`는 녹화만 멈추고 이미 보낸 이동은 멈추지 않는다. 비상시에는 로봇 전원을 끈다.
- 조작 실수는 RESET으로 같은 폴더에서 다시 찍는다. 실행을 처음부터 다시 해야 하면 `L01_red_2`처럼 새 이름을 쓴다 (같은 이름이면 시작 전에 멈추고 덮어쓰지 않는다).
- 실패한 녹화는 지우지 않고 `layout.json`의 `real_success: false`로 남긴다.
- 녹화가 끝난 뒤에는 팔을 더 움직이지 말고 바로 `q`를 누른다. 끝난 뒤의 오류도 녹화 전체를 실패로 만든다.

### 5. 녹화 뒤 기록

배치마다 세 블록 좌표와 위에서 찍은 사진을 넘기면, 세 폴더에 `layout.json`과 `layout.jpg`를 넣고 0.05초 단위 정렬을 한다. 정렬은 70 ms 기준이다 (카메라 실제 저장이 초당 10–11장이라 기본 40 ms로는 실패한다).

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

## 폴더 안 파일

| 파일 | 내용 |
| --- | --- |
| `rgb/*.png` | 손목 D405 원본 프레임 (색 보정 전) — 학습 데이터의 원천 |
| `frames.jsonl` | 프레임마다 받은 시각·카메라 프레임 번호 |
| `robot.jsonl` | 로봇 상태(위치·`?` 응답 원문)·명령·F8/자동 종료/RESET 표시 |
| `metadata.json` | 카메라 설정, 색, `recorded_at`, 호밍 여부, 버린 시도 수 |
| `capture_result.json` | 녹화 종료 이유 (자동 종료·F9·실패·시간 초과) |
| `reference.jsonl`, `source.gcode`, `color_profile.json` | 좌표 변환 기준과 색 보정 |
| `<폴더명>.mp4` | 확인용 영상 (학습에 쓰지 않음) |
| `layout.json`, `layout.jpg` | 블록 좌표·사진 (녹화 뒤 추가) |
| `aligned.npz`, `alignment_report.json` | 0.05초 정렬 결과 (정렬 뒤 추가) |

녹화 설정(D405 팔뚝 장착, 640×480·30 fps 요청, `classic_mini.json`, 집게 S40/S60·1.0 s)은 영상1–10과 같다. 바꾸면 그 전 녹화와 섞어 학습할 수 없다.

## 문제가 생기면

| 증상 | 조치 |
| --- | --- |
| `Expected one D405, found 0` | D405 USB가 빠졌다. 다시 꽂고 1번 장치 확인. 팔이 움직이며 케이블이 당겨지지 않게 정리 |
| `robot_found: false` | 로봇 USB·전원 확인. COM 번호가 바뀌었으면 `--port` 변경 |
| 시작 화면이 평소와 다름 | 부딪혀 위치가 밀렸을 수 있다. 2번 호밍 후 다시 녹화 |
