# Mirobot 실행 명령어

서버에서 로봇을 돌리려면 **창 세 개**가 필요하다. 창을 헷갈리는 게 제일 흔한 실수다.

| 창 | 프롬프트 | 어디 |
|---|---|---|
| 1. 브리지 | `PS C:\mirobot>` | 로봇 노트북 |
| 2. 터널 | `PS C:\...>` → 붙으면 `<USER>@OASYS:~$` | 로봇 노트북에서 실행 |
| 3. 작업 | `(urop) <USER>@OASYS:~$` | 서버 |

`<USER>@OASYS:~$`로 보이는 창은 **서버**다. 거기서 `findstr`, `netstat -ano` 같은
윈도우 명령이나 브리지를 띄우면 안 된다.

---

## 창 1 — 로봇 노트북 (윈도우), 브리지

```powershell
cd C:\mirobot
python mirobot_serial_bridge.py --serial-port COM3
```

`bridge listening on 0.0.0.0:8765` 뜨면 성공. **창 유지.**

포트 번호가 바뀌었으면 `python -m serial.tools.list_ports -v`로 확인.
pyserial이 없으면 `python -m pip install pyserial`.

## 창 2 — 로봇 노트북 (윈도우), 역터널

**노트북과 서버가 다른 망이라서 필요하다.** 창 1은 COM3를 노트북 안에서만 열어 줄 뿐,
서버(192.168.50.x)에서 노트북(192.168.0.x)으로 갈 경로가 없다. 그래서 닿을 수 있는
노트북 쪽에서 먼저 연결을 건다. 이걸 빼면 `--execute`가 접속 단계에서 죽고 로봇은
아무것도 하지 않는다.

```powershell
ssh -p <SSH_PORT> -R 8765:127.0.0.1:8765 <USER>@<SERVER_IP>
```

Ubuntu 인사말 뜨면 성공. **창 유지.**

- 포트는 **<SSH_PORT>**이다 (22 아님).
- 목적지는 **`127.0.0.1`**이다. `localhost`로 쓰면 안 된다.

> **노트북을 서버와 같은 랜(192.168.50.x)에 붙이면 이 창은 통째로 생략된다.**
> 창 1만 띄우고 서버에서 `--bridge-host <노트북IP>`로 바로 가면 된다.
> 창이 하나 줄고 터널이 끊길 걱정도 없으니, 가능하면 이쪽이 낫다.

## 창 3 — 서버 (OASYS)

```bash
conda activate urop
cd ~/UROP/mirobot_control
```

연결 확인:

```bash
python -c "
import socket
s=socket.create_connection(('127.0.0.1',8765),timeout=8); f=s.makefile('rwb',buffering=0)
f.write(b'__PING__\n');   print(f.readline())
f.write(b'__STATUS__\n'); print(f.readline())
f.write(b'__QUIT__\n');   s.close()"
```

`__OK__ bridge-ready`와 로봇 좌표 JSON이 나오면 전 구간 정상.

실행:

```bash
# 드라이런 (네트워크 안 씀, G-code만 출력)
python replay_all_demos_network.py --bridge-host 127.0.0.1 --demo 0 --max-steps 5

# 실제 동작
python replay_all_demos_network.py --bridge-host 127.0.0.1 --demo 0 --max-steps 5 --execute

# 전체 데모
python replay_all_demos_network.py --bridge-host 127.0.0.1 --demo all --home-each-demo --execute
```

`--execute`가 붙으면 첫 명령이 `$H` **호밍**이라 로봇이 크게 움직인다.
주변을 치우고 비상정지에 손이 닿는 위치에서 시작할 것. 멈춤은 `Ctrl+C`.

터널·브리지가 계속 떠 있어야 하므로 서버 작업은 tmux 안에서.

---

## 막히면

| 증상 | 원인 | 조치 |
|---|---|---|
| `RuntimeError: Bridge connection closed`, PING이 빈 응답 | `-R`을 `localhost`로 씀 → 윈도우에서 `::1`로 풀림. 브리지는 IPv4에만 바인딩 | 창 2에서 `exit` 후 `127.0.0.1`로 다시 |
| 새 터널이 즉시 죽음 | 기존 터널이 서버 8765를 잡고 있음 (`ExitOnForwardFailure yes`) | 기존 창 2에서 먼저 `exit` |
| `ssh: connect ... timed out` | 포트 22로 시도 | `-p <SSH_PORT>` |
| `could not open port COM3` | Mirobot Studio·시리얼 모니터가 포트 점유 | 다 닫고 재실행 |
| 서버에서 `ModuleNotFoundError` | env 미적용 | `conda activate urop`, `which python`이 `envs/urop/bin/python`인지 확인 |
| `nc`는 되는데 실행이 안 됨 | `nc`는 터널만 확인함. 브리지 생사는 모름 | 위 PING 스크립트로 확인 |

드라이런은 소켓을 아예 열지 않으므로 **연결 테스트로 쓸 수 없다.**

---

## 참고

- 서버 env: conda `urop` (Python 3.10, pyserial/numpy/h5py/pillow).
  다시 만들 일이 있으면
  `mamba create -n urop -y -c conda-forge python=3.10 pyserial pillow h5py numpy`.
  activate는 `conda activate urop` (`mamba activate`는 이 셸에서 안 됨).
- `mujoco`, `cosmos_policy`는 안 넣었다. `cosmos-policy_tj/`가 저장소에 없어서
  `replay_demo_network_with_mujoco.py`는 아직 못 돌린다.
- `mirobot_camera_bridge.py`는 노트북에서 돌린다:
  `python mirobot_camera_bridge.py --camera-index 0 --listen-host 0.0.0.0 --port 8890`
- `Forward_Kinematics.py` / `Inverse_Kinematics.py`는 시리얼을 직접 열어서
  **서버에서 못 돌린다.** 게다가 현재 `import keyboard` + `COM7` 상태라
  리눅스에서 그대로는 실행되지 않는다 (9/6에 했던 `keyinput.py` 이식이 파일에서 사라짐).
- 접속 정보는 노트북 `~/.ssh/config`의 `Host OASYS`:
  `HostName <SERVER_IP>` / `Port <SSH_PORT>` / `User <USER>`.

*2026-09-07 기준. 서버→터널→노트북→COM3→로봇 상태 조회까지 검증됨.*
