# Copyright (c) 2025-2026, The TienKung-Lab Project Developers.
# All rights reserved.
# Distributed under the BSD-3-Clause license.

"""Physics backend selection shared by every env class (``BaseEnv``, ``TienKungEnv``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import isaaclab.sim as sim_utils
from isaaclab_newton.physics import MJWarpSolverCfg, NewtonCfg, NewtonCollisionPipelineCfg, NewtonShapeCfg
from isaaclab_physx.physics import PhysxCfg

if TYPE_CHECKING:
    from legged_lab.envs.base.base_config import SimCfg


def make_physics_cfg(sim_cfg: "SimCfg"):
    """Return the Isaac Lab physics config selected by ``sim_cfg.physics_backend``."""
    if sim_cfg.physics_backend == "newton":
        # Same MuJoCo-Warp settings as Isaac Lab's rough-terrain locomotion preset
        # (isaaclab_tasks velocity_env_cfg.RoughPhysicsCfg.newton_mjwarp).
        mujoco_contacts = sim_cfg.newton_contacts == "mujoco"
        return NewtonCfg(
            solver_cfg=MJWarpSolverCfg(
                njmax=200,
                nconmax=100,
                cone="pyramidal",
                impratio=1.0,
                integrator="implicitfast",
                use_mujoco_contacts=mujoco_contacts,
            ),
            # Newton's collision pipeline must not be configured when MuJoCo does the collision detection.
            collision_cfg=None if mujoco_contacts else NewtonCollisionPipelineCfg(max_triangle_pairs=2_500_000),
            num_substeps=1,
            debug_mode=False,
            default_shape_cfg=NewtonShapeCfg(margin=0.01),
        )
    if sim_cfg.physics_backend == "physx":
        return PhysxCfg(gpu_max_rigid_patch_count=sim_cfg.physx.gpu_max_rigid_patch_count)
    raise ValueError(f"Unknown physics backend: {sim_cfg.physics_backend!r} (expected 'physx' or 'newton')")


def use_newton_actuators(sim_cfg: "SimCfg") -> bool:
    """``SimulationCfg.use_newton_actuators`` for the selected backend.

    On Newton this routes joint targets through the native actuator path (all-implicit articulations
    then run the decimation loop as one CUDA graph). It does not change the USD joint target mode, so
    the asset still needs a non-zero placeholder drive (see legged_lab/assets/agibot_x2/README.md).
    """
    return sim_cfg.physics_backend == "newton"


def make_ground_material_cfg(sim_cfg: "SimCfg") -> sim_utils.RigidBodyMaterialCfg:
    """Ground / default physics material for the selected backend.

    MuJoCo-Warp ignores ``friction_combine_mode`` and takes the max of the two colliders' friction, so a
    1.0 ground would override the robot's randomized 0.6-1.0 foot friction. Under Newton the ground gets the
    lower bound of that range, so the robot material is the effective contact friction for every sample while
    the ground never falls near MuJoCo's MJ_MINMU (1e-5): with ``newton_contacts="mujoco"`` a ~0 ground
    produced NaN states within 10 iterations (mujoco_warp warns "friction[0] < MJ_MINMU ... may cause NaN";
    ROBOTIS uses exactly 0 but with Newton's own collision pipeline).
    """
    mu = 0.6 if sim_cfg.physics_backend == "newton" else 1.0
    return sim_utils.RigidBodyMaterialCfg(
        friction_combine_mode="multiply",
        restitution_combine_mode="multiply",
        static_friction=mu,
        dynamic_friction=mu,
    )


def contact_force_threshold(sim_cfg: "SimCfg") -> float | None:
    """``ContactSensorCfg.force_threshold`` for the selected backend.

    PhysX picks its own default for ``None``; the Newton contact sensor resolves ``None`` to 0 N, which
    makes the air/contact-time transitions flicker on solver noise. 1 N matches the PhysX behaviour.
    """
    return 1.0 if sim_cfg.physics_backend == "newton" else None


def sanitize_newton_worlds(env_ids) -> list[str]:
    """Zero every non-finite solver buffer row of the given worlds (Newton backend only; no-op elsewhere).

    MuJoCo-Warp occasionally blows one world up to NaN. Isaac Lab's reset rewrites that world's joint and root
    state, but the solver keeps per-world scratch arrays (warm-start accelerations, constraint state, ...) that
    still hold NaN, so the world explodes again on the very next step and never leaves the batch. Returns the
    names of the arrays that were cleaned.
    """
    import torch
    import warp as wp
    from isaaclab_newton.physics import NewtonManager

    solver = getattr(NewtonManager, "_solver", None)
    data = getattr(solver, "mjw_data", None)
    if data is None:
        return []
    ids = torch.as_tensor(env_ids)
    nworld = int(data.nworld)
    cleaned: list[str] = []
    state = NewtonManager.get_state_0()
    for name in ("joint_q", "joint_qd", "joint_qdd", "body_q", "body_qd", "joint_f", "body_f"):
        arr = getattr(state, name, None)
        if arr is None:
            continue
        t = wp.to_torch(arr).reshape(nworld, -1)
        if not torch.isfinite(t[ids]).all():
            t[ids] = 0.0
            cleaned.append(f"state.{name}")
    skip = (wp.int32, wp.uint32, wp.int8, wp.uint8, wp.int64, wp.bool)
    for name in sorted(vars(data)):
        arr = getattr(data, name)
        if not isinstance(arr, wp.array) or arr.ndim < 1 or arr.shape[0] != nworld or arr.dtype in skip:
            continue
        try:
            t = wp.to_torch(arr).reshape(nworld, -1)
        except Exception:  # noqa: BLE001 -- exotic dtypes (vec/mat structs) that warp cannot alias
            continue
        if t.dtype.is_floating_point and not torch.isfinite(t[ids]).all():
            t[ids] = 0.0
            cleaned.append(f"data.{name}")
    return cleaned
