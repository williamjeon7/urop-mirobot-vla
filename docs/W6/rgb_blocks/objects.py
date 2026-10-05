"""Resizable cube objects for LIBERO; lengths are in metres."""

import math
from functools import partial
from pathlib import Path

from robosuite.models.objects import MujocoXMLObject
from libero.libero.envs.base_object import OBJECTS_DICT

ASSETS = Path(__file__).resolve().parent / "assets"
# 세 정육면체의 한 변 길이(mm). 크기를 바꾸려면 이 숫자를 수정하세요.
BLOCK_SIZE_MM = 40.0


def validate_edge_length(edge_length_m):
    edge_length_m = float(edge_length_m)
    if not math.isfinite(edge_length_m) or edge_length_m <= 0:
        raise ValueError("Cube edge length must be finite and greater than zero.")
    return edge_length_m


class CubeBlock(MujocoXMLObject):
    color = None

    def __init__(self, name, edge_length_m=None, joints="default"):
        if edge_length_m is None:
            edge_length_m = BLOCK_SIZE_MM / 1000
        edge_length_m = validate_edge_length(edge_length_m)
        super().__init__(
            str(ASSETS / (self.color + "_block.xml")),
            name=name,
            joints=joints,
            obj_type="all",
            duplicate_collision_geoms=False,
        )
        self.edge_length_m = edge_length_m
        half = edge_length_m / 2
        box_size = " ".join([str(half)] * 3)
        # robosuite keeps the XML template and a separate object subtree.
        # Scale both so render geometry, collision, and exported XML agree.
        for tree in (self.root, self.get_obj()):
            for geom in tree.iter("geom"):
                if geom.get("type") == "box":
                    geom.set("size", box_size)
                    if geom.get("group") == "0":
                        # Constant density: 50 g at the default 40 mm edge.
                        geom.set("mass", str(0.05 * (edge_length_m / 0.04) ** 3))
        offsets = {
            "bottom_site": (0, 0, -half),
            "top_site": (0, 0, half),
            "horizontal_radius_site": (math.sqrt(2) * half, 0, 0),
        }
        for site_name, offset in offsets.items():
            site = self.worldbody.find(
                "./body/site[@name='" + self.naming_prefix + site_name + "']"
            )
            site.set("pos", " ".join(str(value) for value in offset))
        self.category_name = self.color + "_block"
        self.rotation = (0, 0)
        self.rotation_axis = "z"
        self.object_properties = {"vis_site_names": {}}


class RedBlock(CubeBlock):
    color = "red"


class GreenBlock(CubeBlock):
    color = "green"


class BlueBlock(CubeBlock):
    color = "blue"


def register_blocks(edge_length_m=None):
    """Register the BDDL categories before constructing the environment."""
    if edge_length_m is None:
        edge_length_m = BLOCK_SIZE_MM / 1000
    edge_length_m = validate_edge_length(edge_length_m)
    for cls in (RedBlock, GreenBlock, BlueBlock):
        OBJECTS_DICT[cls.color + "_block"] = partial(cls, edge_length_m=edge_length_m)
