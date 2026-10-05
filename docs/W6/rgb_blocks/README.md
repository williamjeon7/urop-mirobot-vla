# RGB 정육면체 시뮬레이터

## 1. 실행

OASYS의 Bash 터미널에서 실행한다:

```bash
bash ~/UROP/docs/W6/rgb_blocks/run_browser.sh
```

## 2. 브라우저

VS Code 하단 PORTS에서 포트 전달을 눌러 `8766`을 추가한다.
로컬 PC 브라우저에서 http://localhost:8766을 연다.
이미 연결된 SSH를 사용하므로 추가 비밀번호는 없다.

## 3. 종료

실행한 터미널에서 `Ctrl+C`를 누른다. 다른 터미널에서 종료하려면:

```bash
bash ~/UROP/docs/W6/rgb_blocks/run_browser.sh --stop
```

## 4. 블록 크기

[objects.py](./objects.py)의 `BLOCK_SIZE_MM = 40.0` 값을 수정한다(mm).
서버를 종료하고 다시 실행해야 적용된다.
