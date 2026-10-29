import serial
import time
import keyboard

# 시리얼 포트 초기화
# ser = serial.Serial(port="/dev/ttyUSB0", baudrate=115200, timeout=1)
ser = (_w9_session.open_serial(port="COM3", baudrate=115200, timeout=1)
       if "_w9_session" in globals() else serial.Serial(port="COM3", baudrate=115200, timeout=1))

time.sleep(2)  # 연결 안정화 대기

def send_gcode(command):
    if "_w9_session" in globals():
        return _w9_session.send_gcode(command)
    ser.write((command + "\n").encode())
    print(f"📤 명령 전송: {command}")
    response = []
    while True:
        line = ser.readline().decode("utf-8").strip()
        if line:
            response.append(line)
            # print(f"응답: {line}")
            if line[:5].lower() == "error":
                print("⚠️ 에러 발생!!!")
                return False
            elif "[Reset to continue]" in line.lower():
                print("⚠️ 리셋 대기 상태 감지, Enter 전송 후 종료")
                ser.write(b"\n")
                time.sleep(1)
                return False
        if "ok" in line.lower():
            print("✅ 명령 실행 완료")
            if command == "M30":
                ser.close()
                print("🔒 시리얼 포트 닫힘")
            return True


# 초기 설정
send_gcode("$22=1")  # 홈 정렬 활성화
send_gcode("$H")  # 홈으로 이동
send_gcode("M20")  # 홈으로 이동
send_gcode("G90")  # 절대 좌표계 (카르테시안 모드)
send_gcode("G0 X198.67 Y0 Z230.72 A0 B0 C0")  # 초기 위치 (6축 모두 0)

# 현재 위치 변수 (카르테시안 좌표계 + 3개의 회전축)
current_x = 198.67  # X축 (mm)
current_y = 0  # Y축 (mm)
current_z = 230.72  # Z축 (mm)
current_a = 0  # J4 (도)
current_b = 0  # J5 (도)
current_c = 0  # J6 (도)
step_linear = 5  # 선형 이동 단위 (mm)
step_angular = 5  # 회전 이동 단위 (도)

# 키보드 제어 시작
print("\n=== 실시간 키보드로 로봇 제어 시작 (카르테시안 모드) ===")
print("명령어:")
print("  a: X축 증가 (+5mm)")
print("  d: X축 감소 (-5mm)")
print("  w: Y축 증가 (+5mm)")
print("  s: Y축 감소 (-5mm)")
print("  ↑: Z축 증가 (+5mm)")
print("  ↓: Z축 감소 (-5mm)")
print("  ←: 그리퍼 열기 (M4 S40)")
print("  →: 그리퍼 닫기 (M4 S60)")
print("  1: A축 증가 (+5도)")
print("  2: A축 감소 (-5도)")
print("  3: A축 상태 확인")
print("  4: B축 증가 (+5도)")
print("  5: B축 감소 (-5도)")
print("  6: B축 상태 확인")
print("  7: C축 증가 (+5도)")
print("  8: C축 감소 (-5도)")
print("  9: C축 상태 확인")
print("  q: 종료")
print("키를 누르고 있으면 계속 움직입니다!")

while True:
    if "_w9_session" in globals():
        _w9_session.tick()  # W9 녹화에서만 F8 시작 / F9 종료, 기존 키 조작 유지
    if keyboard.is_pressed("w"):  # X 증가
        current_x += step_linear
        send_gcode(f"G0 X{current_x} Y{current_y} Z{current_z} A{current_a} B{current_b} C{current_c}")
    elif keyboard.is_pressed("s"):  # X 감소
        current_x -= step_linear
        send_gcode(f"G0 X{current_x} Y{current_y} Z{current_z} A{current_a} B{current_b} C{current_c}")
    elif keyboard.is_pressed("a"):  # Y 증가
        current_y += step_linear
        send_gcode(f"G0 X{current_x} Y{current_y} Z{current_z} A{current_a} B{current_b} C{current_c}")
    elif keyboard.is_pressed("d"):  # Y 감소
        current_y -= step_linear
        send_gcode(f"G0 X{current_x} Y{current_y} Z{current_z} A{current_a} B{current_b} C{current_c}")
    elif keyboard.is_pressed("up"):  # Z 증가
        current_z += step_linear
        send_gcode(f"G0 X{current_x} Y{current_y} Z{current_z} A{current_a} B{current_b} C{current_c}")
    elif keyboard.is_pressed("down"):  # Z 감소
        current_z -= step_linear
        send_gcode(f"G0 X{current_x} Y{current_y} Z{current_z} A{current_a} B{current_b} C{current_c}")
    elif keyboard.is_pressed("left"):  # 그리퍼 열기
        send_gcode("M4 S40")
        time.sleep(0.5)  # 연속 실행 방지
    elif keyboard.is_pressed("right"):  # 그리퍼 닫기
        send_gcode("M4 S60")
        time.sleep(0.5)  # 연속 실행 방지
    # A축 (J4) 제어
    elif keyboard.is_pressed("1"):  # A 증가
        current_a += step_angular
        send_gcode(f"G0 X{current_x} Y{current_y} Z{current_z} A{current_a} B{current_b} C{current_c}")
    elif keyboard.is_pressed("2"):  # A 감소
        current_a -= step_angular
        send_gcode(f"G0 X{current_x} Y{current_y} Z{current_z} A{current_a} B{current_b} C{current_c}")
    elif keyboard.is_pressed("3"):  # A 상태 확인
        send_gcode("?")
        time.sleep(0.5)
    # B축 (J5) 제어
    elif keyboard.is_pressed("4"):  # B 증가
        current_b += step_angular
        send_gcode(f"G0 X{current_x} Y{current_y} Z{current_z} A{current_a} B{current_b} C{current_c}")
    elif keyboard.is_pressed("5"):  # B 감소
        current_b -= step_angular
        send_gcode(f"G0 X{current_x} Y{current_y} Z{current_z} A{current_a} B{current_b} C{current_c}")
    elif keyboard.is_pressed("6"):  # B 상태 확인
        send_gcode("?")
        time.sleep(0.5)
    # C축 (J6) 제어
    elif keyboard.is_pressed("7"):  # C 증가
        current_c += step_angular
        send_gcode(f"G0 X{current_x} Y{current_y} Z{current_z} A{current_a} B{current_b} C{current_c}")
    elif keyboard.is_pressed("8"):  # C 감소
        current_c -= step_angular
        send_gcode(f"G0 X{current_x} Y{current_y} Z{current_z} A{current_a} B{current_b} C{current_c}")
    elif keyboard.is_pressed("9"):  # C 상태 확인
        send_gcode("?")
        time.sleep(0.5)
    elif keyboard.is_pressed("q"):  # 종료
        print("프로그램 종료")
        send_gcode("$H")  # 홈으로 이동
        # send_gcode("G4 P5")
        # send_gcode("G0 X198.67 Y0 Z230.72 A0 B0 C0")
        send_gcode("M30")
        break

    time.sleep(0.1)  # CPU 부하 감소

    #   sudo python3 /media/tj/kodak_64G/ros2/3M5D/cartesian_mode.py
