# D405 — Windows에서 RealSense Viewer 설치와 실행

> **절차** · 확인 2026-10-12 · 기준 Windows 10/11, RealSense D405, Viewer v2.59.1
> Viewer를 다운로드하고 실행한 뒤, D405의 컬러 영상을 화면에서 확인하는 방법.

## 1. 준비

- RealSense D405와 데이터 전송이 가능한 USB 케이블
- Windows 노트북의 USB 3.x 포트
- [RealSense SDK 공식 다운로드 페이지](https://github.com/realsenseai/librealsense/releases/latest)

D405를 노트북에 연결한다. 다른 카메라 사용 프로그램이 실행 중이면 종료한다.

## 2. Viewer 다운로드

1. 공식 다운로드 페이지를 연다.
2. 페이지 아래 **Assets**를 펼친다. 목록이 접혀 있으면 **Show all assets**를 누른다.
3. **`RealSense.Viewer.exe`**를 다운로드한다. v2.59.1 릴리스의 파일명은 이것이며, 이전 릴리스에서는 **`Intel.RealSense.Viewer.exe`**라는 이름을 사용한다.
4. 다운로드한 파일은 찾기 쉬운 폴더에 둔다. 이 노트북에서는 `Downloads`에 `RealSense.Viewer-v2.59.1.exe`라는 이름으로 저장했다.

**Viewer 실행 파일을 받는 방식은 별도의 설치 마법사 없이 실행하는 방식이다.** 카메라 영상 확인만 할 때는 전체 SDK 설치나 Python 패키지 설치가 필요하지 않다.

SDK 개발 환경까지 필요하다면 릴리스의 **`RealSense.SDK.exe`** 설치 프로그램을 사용한다. SDK 설치에는 Viewer도 포함된다.

`latest` 링크가 가리키는 버전은 바뀔 수 있다. 다운로드할 때 릴리스 제목의 버전과 파일명을 확인한다.

[v2.59.1 공식 릴리스](https://github.com/realsenseai/librealsense/releases/tag/v2.59.1), [공식 Windows 배포 안내](https://github.com/realsenseai/librealsense/blob/master/doc/distribution_windows.md)

## 3. Viewer 실행

1. 파일 탐색기에서 다운로드한 Viewer 실행 파일을 찾는다.
2. 파일을 **더블클릭**한다.
3. Viewer 창이 열리면 왼쪽 장치 목록에서 **RealSense D405**를 확인한다.
4. 연결 표시가 **USB 3.x**인지 확인한다. 이 노트북의 실행 기록에서는 USB 3.2로 표시됐다.

다음 실행 때도 같은 파일을 더블클릭한다. 편하게 실행하려면 해당 파일의 바로가기를 만들어 사용한다.

## 4. D405 컬러 영상 켜기

이 노트북에서 확인한 설정 순서다. 다른 Viewer 버전에서는 버튼 위치와 이름이 조금 다를 수 있다.

1. 상단에서 **2D** 화면을 선택한다.
2. 왼쪽 **RealSense D405 → Stereo Module**을 펼친다.
3. 컬러 영상만 보려면 **Depth 체크를 해제**하고 **Color를 선택**한다.
4. 지원되는 설정에서 **RGB8 / 848×480 / 30 FPS**를 선택한다. 설정을 바꾸려면 스트리밍을 먼저 끈다.
5. **Stereo Module의 On/Off 스위치를 On**으로 켠다.
6. 오른쪽에 실제 장면의 컬러 영상이 표시되는지 확인한다.
7. 카메라 앞에서 물체를 움직여 영상이 실시간으로 갱신되는지 확인한다.

D405의 Color는 Stereo Module 안에서 선택한다. 별도의 RGB Camera 항목을 찾을 필요는 없다. 센서 구조와 LIBERO 영상 비교는 [D405_LIBERO_CAMERA.md](../W5/D405_LIBERO_CAMERA.md)를 참고한다.

확인이 끝나면 Stereo Module을 **Off**로 끄고 Viewer를 종료한다.

[공식 시작 안내](https://www.realsenseai.com/get-started-depth-camera/)

## 5. 실행이 안 되거나 영상이 안 보일 때

| 증상 | 확인 순서 |
|---|---|
| D405가 장치 목록에 없음 | 케이블 재연결 → 다른 USB 포트 사용 → 데이터 전송 지원 케이블 확인 → 다른 카메라 사용 프로그램 종료 → Viewer 다시 실행 |
| Depth 영상만 표시됨 | Stereo Module을 Off로 끄고 Depth를 해제한 뒤 Color를 선택해 다시 On으로 켠다. |
| 설정을 바꿀 수 없음 | 스트리밍을 Off로 끈 뒤 해상도·FPS·포맷을 변경한다. |
| 영상이 멈추거나 시작되지 않음 | 다른 카메라 사용 프로그램을 닫고, USB 연결을 확인한 다음 Viewer를 다시 실행한다. 오류 메시지가 나오면 내용을 기록한다. |

## 6. 선택 — MP4 시험 영상 저장

컬러 영상 확인 후 간단히 MP4가 필요하면 **Viewer 창을 화면 녹화**한다. Viewer 메뉴와 표시 요소도 함께 저장된다.

1. 컬러 영상이 나오는 Viewer 창을 클릭한다.
2. **`Windows + Alt + R`**을 눌러 녹화를 시작한다.
3. 약 10초 후 같은 단축키로 종료한다.
4. **동영상 → Captures**에서 MP4를 찾아 재생한다. 저장 위치를 변경했다면 **`Windows + G` → 갤러리**에서 파일을 확인한다.

단축키가 동작하지 않으면 `Windows + G`의 캡처 패널에서 녹화 버튼과 안내 메시지를 확인한다.

[Microsoft 공식 화면 녹화 안내](https://support.microsoft.com/en-gb/accessibility/windows/use-a-screen-reader-to-record-your-screen-with-xbox-game-bar)

Viewer의 **Record to File…**는 SDK 버전에 따라 `.bag` 또는 `.db3`로 카메라 데이터를 기록한다. 일반 MP4가 필요하면 위 화면 녹화 절차를 사용한다. [공식 SDK 녹화 안내](https://github.com/realsenseai/librealsense/blob/master/doc/record-and-playback.md)

## 7. 실행 확인 기록

이 노트북에서 Viewer v2.59.1.11053 실행, D405 인식, RGB8 / 848×480 / 30 FPS 설정의 컬러 스트리밍을 확인한 기록이 있다. 실행 결과와 다음 촬영 작업은 [CHECKLIST.md](CHECKLIST.md)에서 관리한다. MP4 저장·재생은 아직 미확인 상태다.
