# W6 RGB 블록 작업 기준

- 이 폴더의 LIBERO/BDDL/시뮬레이터 작업은 먼저 `docs/W5/NewTaskBDDL.md`를 참고한다.
  실행·화면 표시는 6.3–6.5와 7.2, 새 Object 구현·등록은 9.2를 기준으로 삼는다.
- 기본 실행 방식은 W5처럼 일반 Python 스크립트의 `env.reset()` → `env.step(action)` →
  `agentview_image` → `cv2.imshow()` → `env.check_success()` 반복이다.
  다른 표시 방식은 사용자가 요청했을 때만 도입한다.
- 사용자가 localhost 표시를 요청한 현재 기본 뷰어는 `browser_viewer.py`다.
  OASYS의 Bash 실행 진입점은 `run_browser.sh`다. 사용자가 요청한 Windows 노트북 실행은
  `run_local.cmd -Setup`으로 경로를 한 번 저장하고 이후 `run_local.cmd`로 실행한다.
  W5의 reset/step/관측/Goal 검사를 재사용하고 OpenCV JPEG를 메모리에서 MJPEG로 전송한다.
  `127.0.0.1`에만 바인딩하고 VS Code Remote 포트 전달로 로컬 브라우저에서 확인한다.
- 블록은 Red/Green/Blue 정육면체이며 크기는 `objects.py`의 `BLOCK_SIZE_MM`으로 조절한다.
- 기본 모드는 `--task scene`이다. `--task red|green|blue`는 RGB 세 블록을 유지하며
  해당 블록을 관심 대상으로 지정한다. 색상별 BDDL과 선택 정보는 `tasks/`와 `tasks.py`에 둔다.
- `scene` Goal은 배치 확인용이다. 색상 Task Goal은 LIBERO `Up`(z ≥ 1.0 m)이다.
  배치는 BDDL `:init` 조건으로 판정하고 Goal로 판정하지 않는다.
- Pick up은 `pickup.py`의 `run_pickup`이 수행한다. OSC_POSE `env.step(action)`만 사용하고
  물체 상태를 직접 바꾸지 않는다. 성공 조건은 `Up` Goal, `_check_grasp`, 다른 블록이 1 cm 넘게 움직이지 않음,
  그리고 `--scenario none`이면 다른 블록 `On` 유지다.
  `scenarios.py`는 reset 직후 한 번만 이웃 블록 위치를 바꾸는 장면 준비다. 동작 중에는 물체를 옮기지 않는다.
  뷰어는 설정 하나(task·mode view|pickup|reach·scenario·seed)를 episode 하나로 돌린다. 설정은 브라우저에서
  `/control` `load`로 바꾸고(per-instance 토큰, localhost Host, same-origin), task가 바뀔 때만 환경을 새로 만든다.
  지금 episode의 장면을 메모리에 두고 일시정지·되돌리기·다음 seed를 받는다. 명령어 옵션은 처음 설정이다.
  결정과 검증 기록은 `PICKUP.md`에 남긴다.
- 사용자가 별도로 요청하지 않으면 이미지·GIF·영상·결과 JSON 파일을 저장하지 않는다.
  예외(10/7 허락): `pickup.py --log`는 번역기 입력용 JSONL을 `data/pickup/`(git 제외)에 남긴다.
  `--log`는 손 좌표 JSONL(`panda-poses/1`, `docs/W6/DIVISION.md` 3장)이다. 이 폴더는 Panda 쪽이고,
  Mirobot 변환(`tools/poses_to_gcode.py`, `common/`)은 Mirobot 쪽이 맡는다. 만든 G-code는 `trajectories/`에 둔다.
- Windows는 W5에서 작동한 `libero` 환경과 WGL/DLL 설정을 사용한다.
  OASYS SSH에 `DISPLAY`가 없으면 OpenCV 창이 열리는 것처럼 설명하지 않는다.
- 환경 확인은 `test_rgb_blocks.py --headless --steps 60 --size 512 --seed 0`으로 수행한다.
  색상별 확인에는 `--task red`, `--task green`, `--task blue`를 추가한다.
  BDDL 초기 배치 확인과 실제 Panda 작업 수행은 구분한다. `scene`의 초기 Goal은 `True`가 정상이고,
  색상 Task의 초기 Goal은 `False`가 정상이다. Panda 작업은 `pickup.py --task <color> --seed <n>`으로 확인한다.
