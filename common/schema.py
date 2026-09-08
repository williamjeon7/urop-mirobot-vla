"""관측/액션 스키마.

노트북(robot/)과 서버(server/) **양쪽이 동일하게** 따라야 하는 정의다.
여기 인덱스가 어긋나면 로봇이 엉뚱한 축으로 움직이므로 한쪽만 고치지 말 것.
"""

from __future__ import annotations

TASK_INSTRUCTION = "pick up the red cube and place it on the green target"

# ── 액션 벡터 (길이 7) ────────────────────────────────────────
# [delta_eef_x, delta_eef_y, delta_eef_z,
#  delta_rot_x, delta_rot_y, delta_rot_z, gripper_command]
ACTION_DIM = 7

ACTION_DELTA_EEF_X = 0
ACTION_DELTA_EEF_Y = 1
ACTION_DELTA_EEF_Z = 2
ACTION_DELTA_ROT_X = 3
ACTION_DELTA_ROT_Y = 4
ACTION_DELTA_ROT_Z = 5
ACTION_GRIPPER = 6

# ── 상태 벡터 (길이 9) ────────────────────────────────────────
# [gripper_left_qpos, gripper_right_qpos,
#  eef_pos_x, eef_pos_y, eef_pos_z,
#  eef_quat_w, eef_quat_x, eef_quat_y, eef_quat_z]
#
# EEF 위치 단위는 **MuJoCo world frame 의 meter** 다. G-code 는 mm 를 쓰므로
# common.gcode.state_to_gcode() 가 1000 배 변환과 오프셋 보정을 담당한다.
STATE_DIM = 9

STATE_GRIPPER_LEFT_QPOS = 0
STATE_GRIPPER_RIGHT_QPOS = 1
STATE_EEF_POS_X = 2
STATE_EEF_POS_Y = 3
STATE_EEF_POS_Z = 4
STATE_EEF_QUAT_W = 5
STATE_EEF_QUAT_X = 6
STATE_EEF_QUAT_Y = 7
STATE_EEF_QUAT_Z = 8
