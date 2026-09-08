먼저 Forward_Kinematics.py와 Inverse_Kinematics.py를 윈도우 환경에서 코드 실행을 해보는걸 권장드립니다.

1. pyserial 설치
python -m pip install pyserial

2. 연결된 COM 포트 확인
python -m serial.tools.list_ports -v

FK와 IK 코드에서 com포트 번호만 수정하면 실행가능할겁니다.
