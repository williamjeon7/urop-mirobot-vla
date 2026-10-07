"""Special start layouts for pick up tests: neighbours close to the target along y.

The top-down fingers open along world y, so a neighbour within reach of the open
fingers blocks a straight descent. After `env.reset()` these scenarios move neighbour
blocks once, like the direct state test in W5 NewTaskBDDL 8.5. The Panda still acts
only through `env.step(action)`; nothing is moved during the action.
(LIBERO's BDDL sampler keeps cube centres >= sqrt(2) * edge apart, so gaps below
~17 mm for 40 mm cubes cannot be written as BDDL regions.)
"""

import numpy as np

SCENARIOS = ("none", "adjacent", "sandwich")
DEFAULT_GAP_MM = 20.0   # face-to-face gap; the open fingers reach past it
# Neighbours are placed along world y, the axis the top-down fingers open along (pickup.TOP_DOWN).
ADJACENT_NEIGHBOUR = {"red_block_1": ("green_block_1", +1),
                      "green_block_1": ("red_block_1", -1),
                      "blue_block_1": ("green_block_1", -1)}


def _place(env, name, xy):
    joint = env.env.objects_dict[name].joints[0]
    qpos = env.sim.data.get_joint_qpos(joint).copy()
    qpos[:2] = xy
    qpos[3:] = (1.0, 0.0, 0.0, 0.0)   # upright, yaw 0 like the BDDL placement
    env.sim.data.set_joint_qpos(joint, qpos)
    env.sim.data.set_joint_qvel(joint, np.zeros(6))


def apply_scenario(env, scenario, target, gap_mm=DEFAULT_GAP_MM):
    """Move neighbours next to `target` along y. Returns {name: (x, y)} of moved blocks."""
    if scenario not in SCENARIOS:
        raise ValueError("Unknown scenario {!r}; choose from {}.".format(scenario, SCENARIOS))
    if scenario == "none":
        return {}
    edge = env.rgb_size_mm / 1000
    pitch = edge + gap_mm / 1000
    centre = env.env.object_states_dict[target].get_geom_state()["pos"][:2].copy()
    if scenario == "adjacent":
        name, side = ADJACENT_NEIGHBOUR[target]
        layout = {name: centre + [0.0, side * pitch]}
    else:
        # Keep the neighbours' left/right order (lower y goes to the -y side).
        others = sorted((n for n in env.env.objects_dict if n != target),
                        key=lambda n: env.env.object_states_dict[n].get_geom_state()["pos"][1])
        layout = {others[0]: centre + [0.0, -pitch], others[1]: centre + [0.0, +pitch]}
    for name, xy in layout.items():
        _place(env, name, xy)
    env.sim.forward()
    return {name: [round(float(v), 4) for v in xy] for name, xy in layout.items()}
