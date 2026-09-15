# AgiBot X2 asset

20-DoF locomotion variant of the AgiBot X2 Ultra, used by the `x2_walk` task.

## Attribution

The robot description (`urdf/`, `mjcf/`, `meshes/`) is downloaded from
[AgibotTech/agibot_x2_urdf](https://github.com/AgibotTech/agibot_x2_urdf) (`X2_URDF-v1.4.0`,
"X2 Ultra-N") and is licensed under **Mulan PSL v2**. It is not covered by this
repository's BSD-3-Clause license.

## Layout

| Path | Origin |
|---|---|
| `urdf/x2_ultra.urdf`, `urdf/x2_ultra_simple_collision.urdf` | upstream, unmodified |
| `mjcf/x2_ultra.xml` | upstream, unmodified (sim2sim) |
| `meshes/` | upstream, git-ignored (~90 MB) |
| `urdf/x2_ultra_locked20.urdf` | generated — waist/neck/wrist fixed, mesh paths repointed |
| `usd/x2_ultra_locked20/x2_ultra_locked20.usda` | generated — not committed, see below |
| `agibot_x2.py` | `AGIBOT_X2_CFG` articulation config |

## Regenerating

```bash
# 1. Fetch upstream files and write the 20-DoF URDF (needs network).
python legged_lab/scripts/prepare_agibot_x2.py

# 2. Convert to USD. Requires Isaac Lab 3.0 (Isaac Sim 6.0) -- run this on the training machine.
#    The 3.0 importer takes an output *directory* and writes <dir>/<urdf-stem>/<urdf-stem>.usda,
#    i.e. usd/x2_ultra_locked20/x2_ultra_locked20.usda, which is what AGIBOT_X2_CFG.usd_path expects.
cd <path-to-IsaacLab>
./isaaclab.sh -p scripts/tools/convert_urdf.py \
    <path-to-TienKung-Lab>/legged_lab/assets/agibot_x2/urdf/x2_ultra_locked20.urdf \
    <path-to-TienKung-Lab>/legged_lab/assets/agibot_x2/usd \
    --merge-joints --joint-stiffness 0.0 --joint-damping 0.0 --joint-target-type none

# 3. Record the resulting body/joint order on first use and compare it with the prediction in
#    docs/plan/2026-09-15-agibot-x2-port.md (the 3.0 importer was rewritten; merge_fixed_joints is
#    now a URDF pre-processing step).
```

## Joint budget

```
20 actuated = 12 legs (hip roll/pitch/yaw, knee, ankle pitch/roll)
            +  8 arms (shoulder pitch/roll/yaw, elbow)

11 fixed    =  3 waist (yaw/pitch/roll) + 2 neck (yaw/pitch) + 6 wrist (yaw/pitch/roll x2)
```

Locking those 11 keeps the same joint budget and topology as TienKung2-lite, so the
20-DoF assumptions in `rsl_rl/utils/motion_loader.py`, `min_normalized_std` and
`legged_lab/scripts/sim2sim.py` remain valid. To free the waist yaw later, drop it from
`LOCKED_JOINTS` in `legged_lab/scripts/prepare_agibot_x2.py` and update those three places.

## Measured against TienKung2-lite

| | TienKung2-lite | X2 Ultra (v1.4.0) |
|---|---|---|
| Actuated joints | 20 | 31 upstream → 20 locked |
| Total mass (URDF) | 61.76 kg | 44.80 kg |
| pelvis → ankle_roll | 0.932 m | 0.602 m |
| Foot y separation | 0.299 m | 0.274 m |
| Pelvis height at default pose | 0.828 m | 0.601 m |
| Knee / hip pitch torque | 300 N·m | 120 N·m |
