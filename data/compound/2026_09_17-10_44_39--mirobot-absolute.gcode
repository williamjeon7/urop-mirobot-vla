; LIBERO → Mirobot  data/compound/2026_09_17-10_44_39.jsonl
; task KITCHEN_SCENE1_open_the_top_drawer_of_the_cabinet  segments ['forward + tilt back', 'left + ccw', 'down + tilt left']
; F = x축 180°, 파지점 ↔ 파지점, Panda 시작 ↔ Mirobot (120.0, 0.0, 175.72) (짝 candidate), scale 0.44, orientation absolute
; point grip
; pair X120.00 Y0.00 Z175.72 scale 0.44
G90
M20
; start  (step 30, settle)
G0 X123.15 Y0.01 Z230.63 A-0.01 B3.28 C0.02
; seg1-move5  (step 35, move)
G0 X128.28 Y-0.06 Z226.20 A0.02 B7.29 C-0.02
; seg1-end  (step 55, hold)
G0 X152.61 Y0.19 Z226.33 A0.01 B18.22 C-0.04
; seg2-move5  (step 60, move)
G0 X152.11 Y11.52 Z226.32 A0.12 B18.09 C7.06
; seg2-end  (step 80, hold)
G0 X151.04 Y27.84 Z226.41 A0.01 B18.07 C20.17
; seg3-move5  (step 85, move)
G0 X152.02 Y24.30 Z219.79 A5.96 B16.14 C21.83
; seg3-end  (step 105, hold)
G0 X151.09 Y12.33 Z208.69 A16.75 B11.48 C24.44
