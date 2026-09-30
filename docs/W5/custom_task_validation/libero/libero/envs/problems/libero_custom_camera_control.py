"""Tabletop domain with a second camera and a tuned OSC_POSE controller."""

from copy import deepcopy

from libero.libero.envs.bddl_base_domain import TASK_MAPPING, register_problem
from libero.libero.envs.problems import libero_tabletop_manipulation  # noqa: F401
from libero.libero.envs.regions import REGION_SAMPLERS


REGION_SAMPLERS["libero_custom_camera_control"] = dict(
    REGION_SAMPLERS["libero_tabletop_manipulation"]
)


@register_problem
class Libero_Custom_Camera_Control(TASK_MAPPING["libero_tabletop_manipulation"]):
    """Preserve the tabletop scene while extending its control and observation."""

    def __init__(self, bddl_file_name, *args, **kwargs):
        controller = deepcopy(kwargs.get("controller_configs") or {})
        controller["kp"] = 180
        controller["damping_ratio"] = 1.0
        kwargs["controller_configs"] = controller
        super().__init__(bddl_file_name, *args, **kwargs)

    def _setup_camera(self, mujoco_arena):
        super()._setup_camera(mujoco_arena)
        mujoco_arena.set_camera(
            camera_name="custom_overview",
            pos=[0.9, 0.0, 1.8],
            quat=[
                0.6380177736282349,
                0.3048497438430786,
                0.30484986305236816,
                0.6380177736282349,
            ],
        )
