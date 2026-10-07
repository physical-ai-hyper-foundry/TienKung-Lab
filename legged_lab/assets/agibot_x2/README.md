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
| `usd/x2_ultra_locked20/x2_ultra_locked20.usda` | 3.0 importer output (layered, nested links), not committed |
| `usd/x2_ultra_locked20/x2_ultra_locked20_flat.usd` | `flatten_usd.py` output, loaded by `AGIBOT_X2_CFG` |
| `flatten_usd.py` | flattens the importer's nested link hierarchy (see below) |
| `agibot_x2.py` | `AGIBOT_X2_CFG` articulation config |

## Regenerating

```bash
# 1. Fetch upstream files and write the 20-DoF URDF (needs network).
python legged_lab/scripts/prepare_agibot_x2.py

# 2. Convert to USD. Requires Isaac Lab 3.0 (Isaac Sim 6.0) -- run this on the training machine.
#    The 3.0 importer takes an output *directory* and writes <dir>/<urdf-stem>/<urdf-stem>.usda
#    (a layered asset with a payloads/ folder next to it). convert_urdf.py is not part of the wheel:
#    clone https://github.com/isaac-sim/IsaacLab at tag v3.0.0-beta2.patch1 for the script.
#    The joint drive must NOT be zero-gain: Newton classifies a DriveAPI with stiffness 0 and damping 0
#    as EFFORT mode (no actuator), and the ImplicitActuator gains written at runtime are then ignored,
#    so the robot collapses. The 1.0/1.0 position drive is a placeholder that AGIBOT_X2_CFG overwrites.
python <path-to-IsaacLab>/scripts/tools/convert_urdf.py \
    legged_lab/assets/agibot_x2/urdf/x2_ultra_locked20.urdf \
    legged_lab/assets/agibot_x2/usd \
    --merge-joints --joint-stiffness 1.0 --joint-damping 1.0 --joint-target-type position --headless

# 3. Flatten the link hierarchy and fix the inertia axes. The 6.0 importer nests each child link under
#    its parent (Geometry/pelvis/left_hip_pitch_link/...), and Isaac Lab 3.0.0-beta2.patch1 only puts a
#    contact reporter on the root body of such assets (isaac-sim/IsaacLab#5126, fixed upstream after the
#    tag). The script moves all 21 bodies directly under Geometry/, bakes world poses and remaps joint
#    targets. --conjugate-principal-axes corrects physics:principalAxes, which the bundled
#    urdf-usd-converter 0.1.3 writes inverted (fixed in 0.3.0, whose NewtonMassAPI schema Kit 6.0.1
#    cannot load, so the conversion stays on 0.1.3 and the flatten step fixes the axes instead).
python legged_lab/assets/agibot_x2/flatten_usd.py \
    legged_lab/assets/agibot_x2/usd/x2_ultra_locked20/x2_ultra_locked20.usda \
    legged_lab/assets/agibot_x2/usd/x2_ultra_locked20/x2_ultra_locked20_flat.usd \
    --conjugate-principal-axes

# 4. Verify: every non-merged link must report "ok" (R*D*R^T reproduces the URDF tensor); merged
#    bodies (pelvis, elbows) report "composite" because the URDF link alone is not the merged body.
python legged_lab/assets/agibot_x2/check_usd_inertia.py \
    legged_lab/assets/agibot_x2/urdf/x2_ultra_locked20.urdf \
    legged_lab/assets/agibot_x2/usd/x2_ultra_locked20/x2_ultra_locked20_flat.usd
```

Measured on the first 3.0 run (2026-09-15): 21 bodies, 20 joints, and `robot.joint_names` is

```
hip_pitch(L,R) shoulder_pitch(L,R) hip_roll(L,R) shoulder_roll(L,R) hip_yaw(L,R) shoulder_yaw(L,R)
knee(L,R) elbow(L,R) ankle_pitch(L,R) ankle_roll(L,R)
```

i.e. the BFS prediction in `docs/plan/2026-09-15-agibot-x2-port.md`: identical to TienKung except that
indices `(0,1)` and `(4,5)` (hip_roll / hip_pitch) are swapped.

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
