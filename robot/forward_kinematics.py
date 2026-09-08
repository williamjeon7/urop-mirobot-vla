import serial
import time
import keyboard

# 시리얼 포트 초기화
ser = serial.Serial(port="COM4", baudrate=115200, timeout=1)
# Linux의 경우: ser = serial.Serial(port="/dev/ttyUSB0", baudrate=115200, timeout=1)

time.sleep(2)  # 연결 안정화 대기


def send_gcode(command):
    ser.write((command + "\n").encode())
    print(f"📤 명령 전송: {command}")
    response = []
    while True:
        line = ser.readline().decode("utf-8").strip()
        if line:
            response.append(line)
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
send_gcode("G91")  # 상대 좌표계 모드
send_gcode("G0 X0 Y0 Z0 A0 B0 C0")  # 모든 관절 초기 위치(0도)

# 현재 관절 각도 변수 (도 단위)
current_j1 = 0  # J1 (도)
current_j2 = 0  # J2 (도)
current_j3 = 0  # J3 (도)
current_j4 = 0  # J4 (도)
current_j5 = 0  # J5 (도)
current_j6 = 0  # J6 (도)
step_angular = 3  # 관절 이동 단위 (도)

# 키보드 제어 시작
print("\n=== 실시간 키보드로 로봇 제어 시작 (조인트 모드) ===")
print("명령어:")
print("  1: J1 증가 (+5도)")
print("  2: J1 감소 (-5도)")
print("  3: J2 증가 (+5도)")
print("  4: J2 감소 (-5도)")
print("  5: J3 증가 (+5도)")
print("  6: J3 감소 (-5도)")
print("  7: J4 증가 (+5도)")
print("  8: J4 감소 (-5도)")
print("  9: J5 증가 (+5도)")
print("  0: J5 감소 (-5도)")
print("  -: J6 증가 (+5도)")
print("  =: J6 감소 (-5도)")
print("  ,: 그리퍼 열기 (M4 S40)")
print("  .: 그리퍼 닫기 (M4 S60)")
print("  q: 종료")
print("키를 누르고 있으면 계속 움직입니다!")

while True:
    if keyboard.is_pressed("1"):  # J1 증가
        current_j1 += step_angular
        send_gcode(f"G0 X{current_j1} Y{current_j2} Z{current_j3} A{current_j4} B{current_j5} C{current_j6}")
    elif keyboard.is_pressed("2"):  # J1 감소
        current_j1 -= step_angular
        send_gcode(f"G0 X{current_j1} Y{current_j2} Z{current_j3} A{current_j4} B{current_j5} C{current_j6}")
    elif keyboard.is_pressed("3"):  # J2 증가
        current_j2 += step_angular
        send_gcode(f"G0 X{current_j1} Y{current_j2} Z{current_j3} A{current_j4} B{current_j5} C{current_j6}")
    elif keyboard.is_pressed("4"):  # J2 감소
        current_j2 -= step_angular
        send_gcode(f"G0 X{current_j1} Y{current_j2} Z{current_j3} A{current_j4} B{current_j5} C{current_j6}")
    elif keyboard.is_pressed("5"):  # J3 증가
        current_j3 += step_angular
        send_gcode(f"G0 X{current_j1} Y{current_j2} Z{current_j3} A{current_j4} B{current_j5} C{current_j6}")
    elif keyboard.is_pressed("6"):  # J3 감소
        current_j3 -= step_angular
        send_gcode(f"G0 X{current_j1} Y{current_j2} Z{current_j3} A{current_j4} B{current_j5} C{current_j6}")
    elif keyboard.is_pressed("7"):  # J4 증가
        current_j4 += step_angular
        send_gcode(f"G0 X{current_j1} Y{current_j2} Z{current_j3} A{current_j4} B{current_j5} C{current_j6}")
    elif keyboard.is_pressed("8"):  # J4 감소
        current_j4 -= step_angular
        send_gcode(f"G0 X{current_j1} Y{current_j2} Z{current_j3} A{current_j4} B{current_j5} C{current_j6}")
    elif keyboard.is_pressed("9"):  # J5 증가
        current_j5 += step_angular
        send_gcode(f"G0 X{current_j1} Y{current_j2} Z{current_j3} A{current_j4} B{current_j5} C{current_j6}")
    elif keyboard.is_pressed("0"):  # J5 감소
        current_j5 -= step_angular
        send_gcode(f"G0 X{current_j1} Y{current_j2} Z{current_j3} A{current_j4} B{current_j5} C{current_j6}")
    elif keyboard.is_pressed("-"):  # J6 증가
        current_j6 += step_angular
        send_gcode(f"G0 X{current_j1} Y{current_j2} Z{current_j3} A{current_j4} B{current_j5} C{current_j6}")
    elif keyboard.is_pressed("="):  # J6 감소
        current_j6 -= step_angular
        send_gcode(f"G0 X{current_j1} Y{current_j2} Z{current_j3} A{current_j4} B{current_j5} C{current_j6}")
    elif keyboard.is_pressed(","):  # 그리퍼 열기
        send_gcode("M4 S40")
        time.sleep(0.5)  # 연속 실행 방지
    elif keyboard.is_pressed("."):  # 그리퍼 닫기
        send_gcode("M4 S60")
        time.sleep(0.5)  # 연속 실행 방지
    elif keyboard.is_pressed("q"):  # 종료
        print("프로그램 종료")
        send_gcode("$H")  # 홈으로 이동
        send_gcode("M30")  # 프로그램 종료 및 포트 닫기
        break
    current_j1 = current_j2 = current_j3 = current_j4 = current_j5 =current_j6 = 0  
    time.sleep(0.1)  # CPU 부하 감소
