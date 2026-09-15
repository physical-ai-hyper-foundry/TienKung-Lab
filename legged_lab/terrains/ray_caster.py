# Copyright (c) 2021-2024, The RSL-RL Project Developers.
# All rights reserved.
# Original code is licensed under the BSD-3-Clause license.
#
# Copyright (c) 2022-2025, The Isaac Lab Project Developers.
# All rights reserved.
#
# Copyright (c) 2025-2026, The Legged Lab Project Developers.
# All rights reserved.
#
# Copyright (c) 2025-2026, The TienKung-Lab Project Developers.
# All rights reserved.
# Modifications are licensed under the BSD-3-Clause license.
#
# This file contains code derived from the RSL-RL, Isaac Lab, and Legged Lab Projects,
# with additional modifications by the TienKung-Lab Project,
# and is distributed under the BSD-3-Clause license.
from collections.abc import Sequence

import warp as wp

# Isaac Lab 3.0 turned ``isaaclab.sensors.ray_caster.RayCaster`` into a backend factory that refuses
# subclasses outside the ``isaaclab`` package, so we derive from the PhysX implementation directly
# (this project is PhysX-only, see ADR-001).
from isaaclab_physx.sensors.ray_caster.ray_caster import RayCaster as BaseRayCaster


class RayCaster(BaseRayCaster):
    def reset(self, env_ids: Sequence[int] | None = None, env_mask: wp.array | None = None):
        # reset the timers and counters, and resample ``drift`` in all axes from ``cfg.drift_range``
        super().reset(env_ids, env_mask)
        # resolve None / mask
        if env_ids is None and env_mask is not None:
            env_ids = wp.to_torch(env_mask).nonzero(as_tuple=False).squeeze(-1)
        elif env_ids is None:
            env_ids = slice(None)
        # keep the vertical drift ten times smaller than the horizontal one
        drift = self.drift.torch
        drift[env_ids, 2] = drift[env_ids, 2].uniform_(*(self.cfg.drift_range[0] * 0.1, self.cfg.drift_range[1] * 0.1))
