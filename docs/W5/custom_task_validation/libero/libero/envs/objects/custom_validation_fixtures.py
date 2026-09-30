"""Fixed fixtures used to validate a new physical support and its Region."""
from pathlib import Path

from robosuite.models.objects import MujocoXMLObject
from libero.libero.envs.base_object import register_object


@register_object
class RaisedSupport(MujocoXMLObject):
    """A 12 cm square, 4 cm high platform placed on the table."""

    def __init__(self, name="raised_support", joints=None):
        asset = (Path(__file__).resolve().parents[2] / "assets" /
                 "custom_validation_objects" / "raised_support.xml")
        super().__init__(str(asset), name=name, joints=joints,
                         obj_type="all", duplicate_collision_geoms=False)
        self.category_name = "raised_support"
        self.rotation = (0.0, 0.0)
        self.rotation_axis = "z"
        self.object_properties = {"vis_site_names": {}}
