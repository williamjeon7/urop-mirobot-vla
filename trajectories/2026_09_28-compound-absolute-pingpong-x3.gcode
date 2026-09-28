; LIBERO → Mirobot  data/compound/2026_09_17-10_44_39.jsonl
; task KITCHEN_SCENE1_open_the_top_drawer_of_the_cabinet  segments ['forward + tilt back', 'left + ccw', 'down + tilt left']
; F = x축 180°, 플랜지 ↔ 플랜지, Panda 시작 ↔ Mirobot 홈 (198.67, 0.0, 230.72), scale 1.0, orientation absolute
; 9/28 반복 실행용 (W4 ④ 오차 누적) — 2026_09_17-compound-absolute.gcode 를 왕복 3회.
; 끝(seg3-end)에서 start 로 한 번에 돌아오면 큰 이동이 생겨, 갔던 waypoint 를 거꾸로 되짚어 돌아온다.
; 라벨 r1f = 1회차 가는 길, r1b = 1회차 돌아오는 길. absolute 파일의 첫 실물 실행이다.
G90
M20
; r1f start
G0 X198.67 Y0.00 Z230.72 A-0.01 B3.28 C0.02
; r1f seg1-move5
G0 X208.39 Y-0.13 Z220.83 A0.02 B7.29 C-0.02
; r1f seg1-end
G0 X258.48 Y0.43 Z222.31 A0.01 B18.22 C-0.04
; r1f seg2-move5
G0 X257.47 Y25.16 Z222.25 A0.12 B18.09 C7.06
; r1f seg2-end
G0 X255.51 Y60.26 Z222.47 A0.01 B18.07 C20.17
; r1f seg3-move5
G0 X257.63 Y55.03 Z207.28 A5.96 B16.14 C21.83
; r1f seg3-end
G0 X255.59 Y33.15 Z182.54 A16.75 B11.48 C24.44
; r1b seg3-move5
G0 X257.63 Y55.03 Z207.28 A5.96 B16.14 C21.83
; r1b seg2-end
G0 X255.51 Y60.26 Z222.47 A0.01 B18.07 C20.17
; r1b seg2-move5
G0 X257.47 Y25.16 Z222.25 A0.12 B18.09 C7.06
; r1b seg1-end
G0 X258.48 Y0.43 Z222.31 A0.01 B18.22 C-0.04
; r1b seg1-move5
G0 X208.39 Y-0.13 Z220.83 A0.02 B7.29 C-0.02
; r1b start
G0 X198.67 Y0.00 Z230.72 A-0.01 B3.28 C0.02
; r2f seg1-move5
G0 X208.39 Y-0.13 Z220.83 A0.02 B7.29 C-0.02
; r2f seg1-end
G0 X258.48 Y0.43 Z222.31 A0.01 B18.22 C-0.04
; r2f seg2-move5
G0 X257.47 Y25.16 Z222.25 A0.12 B18.09 C7.06
; r2f seg2-end
G0 X255.51 Y60.26 Z222.47 A0.01 B18.07 C20.17
; r2f seg3-move5
G0 X257.63 Y55.03 Z207.28 A5.96 B16.14 C21.83
; r2f seg3-end
G0 X255.59 Y33.15 Z182.54 A16.75 B11.48 C24.44
; r2b seg3-move5
G0 X257.63 Y55.03 Z207.28 A5.96 B16.14 C21.83
; r2b seg2-end
G0 X255.51 Y60.26 Z222.47 A0.01 B18.07 C20.17
; r2b seg2-move5
G0 X257.47 Y25.16 Z222.25 A0.12 B18.09 C7.06
; r2b seg1-end
G0 X258.48 Y0.43 Z222.31 A0.01 B18.22 C-0.04
; r2b seg1-move5
G0 X208.39 Y-0.13 Z220.83 A0.02 B7.29 C-0.02
; r2b start
G0 X198.67 Y0.00 Z230.72 A-0.01 B3.28 C0.02
; r3f seg1-move5
G0 X208.39 Y-0.13 Z220.83 A0.02 B7.29 C-0.02
; r3f seg1-end
G0 X258.48 Y0.43 Z222.31 A0.01 B18.22 C-0.04
; r3f seg2-move5
G0 X257.47 Y25.16 Z222.25 A0.12 B18.09 C7.06
; r3f seg2-end
G0 X255.51 Y60.26 Z222.47 A0.01 B18.07 C20.17
; r3f seg3-move5
G0 X257.63 Y55.03 Z207.28 A5.96 B16.14 C21.83
; r3f seg3-end
G0 X255.59 Y33.15 Z182.54 A16.75 B11.48 C24.44
; r3b seg3-move5
G0 X257.63 Y55.03 Z207.28 A5.96 B16.14 C21.83
; r3b seg2-end
G0 X255.51 Y60.26 Z222.47 A0.01 B18.07 C20.17
; r3b seg2-move5
G0 X257.47 Y25.16 Z222.25 A0.12 B18.09 C7.06
; r3b seg1-end
G0 X258.48 Y0.43 Z222.31 A0.01 B18.22 C-0.04
; r3b seg1-move5
G0 X208.39 Y-0.13 Z220.83 A0.02 B7.29 C-0.02
; r3b start
G0 X198.67 Y0.00 Z230.72 A-0.01 B3.28 C0.02
