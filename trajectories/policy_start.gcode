; W10 policy initial pose. tools.run_gcode --home establishes homing first.
; Opens the gripper and returns to measured Mirobot home (flange mm, ABC deg).
G90
M20
M4 S40
G0 X198.670 Y0.000 Z230.720 A0.000 B0.000 C0.000
