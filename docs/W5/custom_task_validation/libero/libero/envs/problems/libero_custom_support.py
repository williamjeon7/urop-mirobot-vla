"""Tabletop environment extension for a platform with its own top Region."""
from libero.libero.envs.bddl_base_domain import TASK_MAPPING, register_problem
from libero.libero.envs.objects.custom_validation_fixtures import RaisedSupport
from libero.libero.envs.regions import REGION_SAMPLERS, TableRegionSampler


# register_problem stores the class in TASK_MAPPING; its decorator return is None.
_TabletopBase = TASK_MAPPING["libero_tabletop_manipulation"]
REGION_SAMPLERS["libero_custom_support"] = {"table": TableRegionSampler}


@register_problem
class Libero_Custom_Support(_TabletopBase):
    """Reuse the tabletop scene and place the new support at the table surface."""

    def _add_placement_initializer(self):
        super()._add_placement_initializer()
        # This platform's bottom_site matches its true collision bottom.
        # Tabletop's legacy fixture z_offset (-0.04 m) would sink the platform.
        for name, fixture in self.fixtures_dict.items():
            if isinstance(fixture, RaisedSupport):
                self.placement_initializer.samplers[name + "_sampler"].z_offset = 0.0
