"""Translate W10 ``follow`` actions through the same virtual Panda as labels.

The action describes a controller target relative to the *virtual* Panda's
current pose.  ``target`` computes that target before advancing the simulator;
the simulator's subsequently reached pose is not the physical robot's target.
Call ``advance`` once after accepting each physical command, and use measured
Mirobot state separately for policy proprioception and tracking checks.

Imports remain lightweight until ``initialize`` creates the headless simulator.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

from common.policy_io import apply_action, gripper_s
from common.rotation import quat_xyzw_to_wxyz
from common.servo import pose_gap, servo_action
from common.workspace import flange_to_grip


def _finite_values(values, count: int, label: str) -> tuple[float, ...]:
    result = tuple(float(v) for v in values)
    if len(result) != count or not all(math.isfinite(v) for v in result):
        raise ValueError(f"{label} needs {count} finite values.")
    return result


def checked_action(action) -> tuple[float, ...]:
    """Reject malformed/out-of-range actions; match the controller's clipping."""
    values = _finite_values(action, 7, "OSC_POSE action")
    if any(abs(v) > 1.000001 for v in values):
        raise ValueError("OSC_POSE action outside [-1, 1].")
    return tuple(max(-1.0, min(1.0, v)) for v in values)


@dataclass(frozen=True)
class FollowTarget:
    cart6: tuple[float, ...]
    gripper_s: float
    virtual_cart6: tuple[float, ...]
    action: tuple[float, ...]


class FollowTranslator:
    """Stateful inverse of ``docs.W9.d405.action_labels.follow_actions``.

    ``frame`` is a ``tools.policy_obs.MirobotFrame``.  A factory can be injected
    for tests; otherwise the exact label-generation environment is created.
    Warmup only moves the virtual Panda and never sends hardware commands.
    """

    def __init__(self, frame, reference_meta: dict | None = None, *,
                 env_factory: Callable | None = None, open_s: float = 40.0,
                 closed_s: float = 60.0):
        self.frame = frame
        self.reference_meta = reference_meta
        self.env_factory = env_factory
        self.open_s = float(open_s)
        self.closed_s = float(closed_s)
        if not all(math.isfinite(v) for v in (self.open_s, self.closed_s)):
            raise ValueError("Gripper settings must be finite.")
        self.env = None
        self.obs = None
        self.steps = 0
        self.initialization = None

    def _pose(self):
        if self.obs is None:
            raise RuntimeError("Initialize the follow translator before using it.")
        pos = _finite_values(self.obs["robot0_eef_pos"], 3, "Virtual position")
        q = quat_xyzw_to_wxyz(_finite_values(self.obs["robot0_eef_quat"], 4,
                                            "Virtual quaternion"))
        return pos, q

    def _cart6(self, pos, q) -> tuple[float, ...]:
        xyz, abc = self.frame.to_mirobot(pos, q)
        return _finite_values((*xyz, *abc), 6, "Mirobot pose")

    def initialize(self, cart6, closure: float = 0.0, *,
                   max_warmup_steps: int = 100) -> dict:
        """Match label warmup (2 mm LIBERO / 0.1 degree), or fail closed.

        Reset must agree with the original coordinate reference to 1 mm and
        0.1 degree.  Initial warmup residual is returned in physical Mirobot mm.
        Reinitialization closes the previous virtual environment.
        """
        cart6 = _finite_values(cart6, 6, "Measured Cartesian state")
        closure = float(closure)
        if not math.isfinite(closure) or not 0.0 <= closure <= 1.0:
            raise ValueError("Gripper closure must be between 0 and 1.")
        if not isinstance(max_warmup_steps, int) or max_warmup_steps < 0:
            raise ValueError("max_warmup_steps must be a nonnegative integer.")
        target_pos, target_q = self.frame.to_libero(cart6)
        self.close()
        factory = self.env_factory
        if factory is None:
            from docs.W9.d405.action_labels import create_translator
            factory = create_translator
        self.env = factory()
        try:
            self.obs = self.env.reset()
            pos, q = self._pose()
            if self.reference_meta is None:
                ref_pos = flange_to_grip(self.frame.ref_flange, self.frame.ref_q)
                ref_q = self.frame.ref_q
            else:
                ref_pos = self.reference_meta["start_eef_pos"]
                ref_q = quat_xyzw_to_wxyz(self.reference_meta["start_eef_quat_xyzw"])
            reset_m, reset_deg = pose_gap(pos, q, ref_pos, ref_q)
            if reset_m > 0.001 or reset_deg > 0.1:
                raise ValueError("Translator reset differs from the recorded mapping reference "
                                 f"({reset_m * 1000:.3f} mm LIBERO, {reset_deg:.3f} deg).")
            grip = -1.0 if closure < 0.5 else 1.0
            for warmup in range(max_warmup_steps + 1):
                pos, q = self._pose()
                dp, dq = pose_gap(pos, q, target_pos, target_q)
                if dp <= 0.002 and dq <= 0.1:
                    break
                if warmup == max_warmup_steps:
                    raise ValueError("Translator warmup failed: "
                                     f"{dp * 1000:.3f} mm LIBERO, {dq:.3f} deg.")
                action = servo_action(pos, q, target_pos, target_q, grip)
                self.obs, _, _, _ = self.env.step(action)
            self.steps = 0
            self.initialization = dict(warmup_steps=warmup,
                reset_position_libero_mm=reset_m * 1000.0,
                reset_rotation_deg=reset_deg,
                position_mm=dp * 1000.0 * self.frame.settings["scale"],
                rotation_deg=dq, virtual_cart6=list(self._cart6(pos, q)))
            return dict(self.initialization)
        except BaseException:
            self.close()
            raise

    def target(self, action) -> FollowTarget:
        """Preview controller goal without stepping the simulator."""
        action = checked_action(action)
        pos, q = self._pose()
        goal_pos, goal_q = apply_action(pos, q, action)
        return FollowTarget(cart6=self._cart6(goal_pos, goal_q),
                            gripper_s=gripper_s(action, self.open_s, self.closed_s),
                            virtual_cart6=self._cart6(pos, q), action=action)

    def advance(self, action) -> dict:
        """Advance exactly one 20 Hz virtual control step after acceptance."""
        action = checked_action(action)
        self._pose()  # require successful initialization before env.step
        self.obs, _, _, _ = self.env.step(action)
        self.steps += 1
        pos, q = self._pose()
        return dict(steps=self.steps, virtual_cart6=list(self._cart6(pos, q)))

    def gap(self, cart6) -> dict:
        """Difference between measured and virtual poses in physical mm/degrees."""
        cart6 = _finite_values(cart6, 6, "Measured Cartesian state")
        measured_pos, measured_q = self.frame.to_libero(cart6)
        pos, q = self._pose()
        dp, dq = pose_gap(pos, q, measured_pos, measured_q)
        return dict(position_mm=dp * 1000.0 * self.frame.settings["scale"],
                    rotation_deg=dq)

    def close(self):
        env, self.env = self.env, None
        self.obs = None
        self.initialization = None
        if env is not None:
            env.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
