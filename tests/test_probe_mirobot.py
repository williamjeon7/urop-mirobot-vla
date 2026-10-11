"""`tools/probe_mirobot.py` 의 자세 한 줄 출력과 Z 하한 검사 확인 테스트.

    python -m pytest tests/test_probe_mirobot.py
"""

from __future__ import annotations

from tools.probe_mirobot import Probe, pose_summary
from tools.run_gcode import Z_FLOOR_MM

STATUS = ("<Idle,Angle(ABCDXYZ):1.000,2.000,3.000,0.000,4.000,5.000,6.000,"
          "Cartesian coordinate(XYZ RxRyRz):198.670,0.000,230.450,0.000,3.200,-0.100,"
          "Pump PWM:30,Valve PWM:0,Motion_MODE:1>")


def test_pose_summary_reorders_joints():
    # Angle(ABCDXYZ) = [J4, J5, J6, D, J1, J2, J3] → J1~J6 로 바꿔 적는다
    line = pose_summary(STATUS)
    assert "Idle" in line
    assert "X 198.67 Y 0.00 Z 230.45" in line
    assert "A 0.00 B 3.20 C -0.10" in line
    assert "J1~J6 4.00 5.00 6.00 1.00 2.00 3.00" in line
    assert "집게 S30" in line


def make_probe(z_floor=None):
    probe = Probe.__new__(Probe)  # 포트·기록 파일 없이 검사 함수만 쓴다
    probe.z_floor = z_floor
    return probe


def test_below_floor_blocks_low_moves():
    probe = make_probe()
    assert probe.floor() == Z_FLOOR_MM
    assert probe.below_floor(f"G0 X200 Y0 Z{Z_FLOOR_MM - 0.01} A0 B0 C0")
    assert probe.below_floor("G0 Z50")  # 축이 다 없어도 Z 만 있으면 본다
    assert not probe.below_floor(f"G0 X200 Y0 Z{Z_FLOOR_MM} A0 B0 C0")
    assert not probe.below_floor("M4 S70")
    assert not probe.below_floor("$$")


def test_below_floor_uses_override():
    probe = make_probe(z_floor=40.0)
    assert not probe.below_floor("G0 X200 Y0 Z50 A0 B0 C0")
    assert probe.below_floor("G0 X200 Y0 Z39 A0 B0 C0")
