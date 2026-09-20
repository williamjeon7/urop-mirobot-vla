; LIBERO → Mirobot  data/compound/2026_09_17-10_44_39.jsonl
; task KITCHEN_SCENE1_open_the_top_drawer_of_the_cabinet  segments ['forward + tilt back', 'left + ccw', 'down + tilt left']
; F = x축 180°, 플랜지 ↔ 플랜지, Panda 시작 ↔ Mirobot 홈 (198.67, 0.0, 230.72), scale 1.0, orientation relative
G90
M20
; start  (step 30, settle)
G0 X198.67 Y0.00 Z230.72 A0.00 B-0.00 C0.00
; seg1-move5  (step 35, move)
G0 X208.39 Y-0.13 Z220.83 A0.03 B4.01 C-0.04
; seg1-end  (step 55, hold)
G0 X258.48 Y0.43 Z222.31 A0.01 B14.94 C-0.06
; seg2-move5  (step 60, move)
G0 X257.47 Y25.16 Z222.25 A0.12 B14.81 C7.03
; seg2-end  (step 80, hold)
G0 X255.51 Y60.26 Z222.47 A0.01 B14.79 C20.15
; seg3-move5  (step 85, move)
G0 X257.63 Y55.03 Z207.28 A5.88 B12.88 C21.46
; seg3-end  (step 105, hold)
G0 X255.59 Y33.15 Z182.54 A16.59 B8.34 C23.47
