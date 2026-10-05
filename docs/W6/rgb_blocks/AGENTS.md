# W6 RGB 블록 작업 기준

- 이 폴더의 LIBERO/BDDL/시뮬레이터 작업은 먼저 `docs/W5/NewTaskBDDL.md`를 참고한다.
  실행·화면 표시는 6.3–6.5와 7.2, 새 Object 구현·등록은 9.2를 기준으로 삼는다.
- 기본 실행 방식은 W5처럼 일반 Python 스크립트의 `env.reset()` → `env.step(action)` →
  `agentview_image` → `cv2.imshow()` → `env.check_success()` 반복이다.
  다른 표시 방식은 사용자가 요청했을 때만 도입한다.
- 사용자가 localhost 표시를 요청한 현재 기본 뷰어는 `browser_viewer.py`다.
  Bash 실행 진입점은 `run_browser.sh`이며 Windows 실행기를 기본 안내로 제시하지 않는다.
  W5의 reset/step/관측/Goal 검사를 재사용하고 OpenCV JPEG를 메모리에서 MJPEG로 전송한다.
  `127.0.0.1`에만 바인딩하고 VS Code Remote 포트 전달로 로컬 브라우저에서 확인한다.
- 블록은 Red/Green/Blue 정육면체이며 크기는 `objects.py`의 `BLOCK_SIZE_MM`으로 조절한다.
- 사용자가 별도로 요청하지 않으면 이미지·GIF·영상·결과 JSON 파일을 저장하지 않는다.
- Windows는 W5에서 작동한 `libero` 환경과 WGL/DLL 설정을 사용한다.
  OASYS SSH에 `DISPLAY`가 없으면 OpenCV 창이 열리는 것처럼 설명하지 않는다.
- 환경 확인은 `test_rgb_blocks.py --headless --steps 60 --size 512 --seed 0`으로 수행한다.
  BDDL 초기 배치 확인과 실제 Panda 작업 수행은 구분한다. 현재 Goal은 배치 확인용이다.
