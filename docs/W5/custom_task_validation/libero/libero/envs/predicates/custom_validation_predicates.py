"""A stricter placement condition for the section 9 milk experiment."""

import numpy as np

from .base_predicates import BinaryAtomic, On


class CenteredUprightOn(BinaryAtomic):
    """Milk contacts the plate, is centered within 1 cm, and stands upright.

    The milk asset's local positive Y axis points toward the carton top.
    """

    def __call__(self, milk, plate):
        if not On()(milk, plate):
            return False
        milk_pos = milk.get_geom_state()["pos"]
        plate_pos = plate.get_geom_state()["pos"]
        xy_distance = np.linalg.norm(milk_pos[:2] - plate_pos[:2])
        body_id = milk.env.obj_body_id[milk.object_name]
        rotation = milk.env.sim.data.body_xmat[body_id].reshape(3, 3)
        local_y_world_z = float(rotation[2, 1])
        return bool(xy_distance <= 0.01 and local_y_world_z >= 0.95)
