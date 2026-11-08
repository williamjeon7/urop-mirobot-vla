"""Move to the policy start pose through the bridge's /command, without homing.

Uses only commands every bridge version accepts (G90, M20, M4 S, absolute G0 within the
25 mm / 20 deg per-move limit), so pickup runs from OASYS work with the installed Windows bridge.
The bridge waits for Idle after each move and reports the pose; we verify each arrival.
"""
from __future__ import annotations

import math
import time

INITIAL_POSE = (198.67, 0.0, 230.72, 0.0, 0.0, 0.0)  # trajectories/policy_start.gcode
OPEN_S = 40
MAX_SEGMENT_MM = 20.0  # below the bridge's 25 mm hard limit
# Bridges installed before 11/08 check "Idle pose = target" using a status read before the arm
# starts moving, so any single move longer than 2 mm can be refused (bridge fault). Keep each
# move to such a bridge under 2 mm and wait on the server until the arm has really stopped.
LEGACY_SEGMENT_MM = 1.8
# Start/return moves go as directly as the bridge allows: one move per 24 mm (the bridge refuses
# more than 25 mm). The bridge itself waits for Idle after each move, so no extra waiting here.
DIRECT_SEGMENT_MM = 24.0
SETTLE = dict(polls=3, tolerance_mm=0.05, timeout_s=15.0, interval_s=0.05)
MAX_SEGMENT_DEG = 10.0  # below the bridge's 20 deg limit
ARRIVAL = (2.0, 1.0)  # mm, deg


def _angle(a, b):
    return abs((a - b + 180) % 360 - 180)


def _gap(a, b):
    return math.dist(a[:3], b[:3]), max(_angle(x, y) for x, y in zip(a[3:], b[3:]))


def legacy_bridge(client):
    """True for a bridge without the after-motion settle check (needs < 2 mm moves)."""
    health = getattr(client, "health", None)
    return callable(health) and health().get("move_settle_check") != "after_motion"


def segment_mm(client):
    return LEGACY_SEGMENT_MM if legacy_bridge(client) else MAX_SEGMENT_MM


def wait_settled(client, sleep=time.sleep, clock=time.monotonic):
    """Poll until the arm reports Idle at the same pose several times in a row."""
    deadline = clock() + SETTLE["timeout_s"]
    recent = []
    while clock() < deadline:
        observation = client.observation()
        recent = (recent + [observation])[-SETTLE["polls"]:]
        if (len(recent) == SETTLE["polls"] and
                all(str(o.get("state", "")).lower() == "idle" for o in recent) and
                all(math.dist(o["cart6"][:3], recent[-1]["cart6"][:3]) <= SETTLE["tolerance_mm"] for o in recent)):
            return observation
        sleep(SETTLE["interval_s"])
    raise RuntimeError("로봇이 멈춘 것을 확인하지 못했습니다 (15초)")


def move(client, current, goal, max_segment_mm, *, log=None, on_command=None, sleep=time.sleep, settle=True):
    """Send current -> goal as segments of at most max_segment_mm.

    settle=True waits on this side until the arm has stopped after every segment (policy moves on
    old bridges); settle=False trusts the bridge's own Idle wait and uses the pose it reports.
    """
    observation = None
    for target in waypoints(current, goal, max_segment_mm):
        command = command_text(target)
        if log:
            log(command)
        result = client.command(command)
        if on_command:
            on_command(command, result)
        if settle:
            observation = wait_settled(client, sleep=sleep)
        else:
            observation = result if result.get("cart6") else client.observation()
    return observation


def waypoints(start, goal=INITIAL_POSE, max_segment_mm=MAX_SEGMENT_MM):
    """Straight segments from start to goal, each within the per-move limits."""
    distance, rotation = _gap(start, goal)
    count = max(1, math.ceil(distance / max_segment_mm), math.ceil(rotation / MAX_SEGMENT_DEG))
    deltas = [((g - s + 180) % 360 - 180) if i >= 3 else g - s for i, (s, g) in enumerate(zip(start, goal))]
    return [tuple(s + d * k / count for s, d in zip(start, deltas)) for k in range(1, count + 1)]


def command_text(cart6):
    return "G0 " + " ".join(f"{axis}{value:.3f}" for axis, value in zip("XYZABC", cart6))


def _check_arrival(reached, goal, what):
    mm, deg = _gap(reached, goal)
    if mm > ARRIVAL[0] or deg > ARRIVAL[1]:
        raise RuntimeError(f"{what} 도착 실패: {mm:.2f} mm / {deg:.2f} deg")


def prepare_without_homing(client, log=print, sleep=time.sleep):
    """Open the gripper and go to INITIAL_POSE. Returns event rows for initialization.jsonl."""
    events = []
    observation = client.observation()
    state = str(observation.get("state", ""))
    events.append(dict(kind="state_before", state=state, cart6=observation.get("cart6")))
    if state.lower() != "idle":
        raise RuntimeError(f"로봇이 Idle 이 아닙니다 ({state}). 전원을 켠 직후나 Locked/A106 이면 "
                           "DEPLOY 2-3 으로 호밍한 뒤 다시 실행하세요.")
    for setup in ("G90", "M20", f"M4 S{OPEN_S}"):
        log(f"초기화: {setup}")
        events.append(dict(kind="command", command=setup, result=client.command(setup)))
    sleep(1.0)  # gripper opening time, as in policy_start.gcode
    settled = move(client, observation["cart6"], INITIAL_POSE, DIRECT_SEGMENT_MM, settle=False,
                   log=lambda c: log(f"초기화: {c}"), sleep=sleep,
                   on_command=lambda c, r: events.append(dict(kind="command", command=c, result=r)))
    _check_arrival(settled["cart6"], INITIAL_POSE, "초기 위치")
    events.append(dict(kind="initial_pose_ready", cart6=list(settled["cart6"]), gripper_s=OPEN_S, homed=False))
    log("초기 위치 도착 (호밍 없음, 그리퍼 열림)")
    return events


def return_to_initial(client, log=print, sleep=time.sleep):
    """After a pickup run: lift straight up to the start height, then move to INITIAL_POSE.

    The gripper is left as it is (a held block stays held). Nothing moves unless the robot is
    Idle. Returns event rows; raises RuntimeError if a move is refused or not reached.
    """
    events = []
    observation = client.observation()
    state = str(observation.get("state", ""))
    events.append(dict(kind="return_state_before", state=state, cart6=observation.get("cart6")))
    if state.lower() != "idle":
        raise RuntimeError(f"로봇이 Idle 이 아니라 초기 위치로 보내지 않았습니다 ({state}).")
    current = list(observation["cart6"])
    lifted = tuple(current[:2]) + (max(current[2], INITIAL_POSE[2]),) + tuple(current[3:])
    for goal in (lifted, INITIAL_POSE):  # up first, so the gripper never sweeps low over the blocks
        settled = move(client, current, goal, DIRECT_SEGMENT_MM, settle=False,
                       log=lambda c: log(f"복귀: {c}"), sleep=sleep,
                       on_command=lambda c, r: events.append(dict(kind="return_command", command=c, result=r)))
        _check_arrival(settled["cart6"], goal, "복귀 중")
        current = list(settled["cart6"])
    events.append(dict(kind="returned_to_initial_pose", cart6=current))
    log("초기 위치로 복귀 완료 (그리퍼는 그대로)")
    return events
