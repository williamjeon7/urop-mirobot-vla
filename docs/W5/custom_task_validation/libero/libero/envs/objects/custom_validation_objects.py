"""Movable objects added for the custom-task extension experiment."""

from pathlib import Path

from robosuite.models.objects import MujocoXMLObject

from libero.libero.envs.base_object import register_object


@register_object
class CustomMarkerBox(MujocoXMLObject):
    """A 52 x 52 x 110 mm box with one collision shape and an orange marker."""

    def __init__(self, name="custom_marker_box", joints=None):
        asset = (Path(__file__).resolve().parents[2] / "assets" /
                 "custom_validation_objects" / "marker_box.xml")
        super().__init__(
            str(asset), name=name,
            joints=[dict(type="free", damping="0.0005")] if joints is None else joints,
            obj_type="all", duplicate_collision_geoms=False,
        )
        self.category_name = "custom_marker_box"
        self.rotation = (0.0, 0.0)
        self.rotation_axis = "z"
        self.object_properties = {"vis_site_names": {}}
