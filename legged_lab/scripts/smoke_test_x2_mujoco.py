# Copyright (c) 2025-2026, The TienKung-Lab Project Developers.
# All rights reserved.
# Distributed under the BSD-3-Clause license.

"""MuJoCo smoke test for the AgiBot X2 port -- runs on CPU, no Isaac Lab needed.

Checks the parts of the port that do not depend on Isaac Sim: the model loads, the
20 actuated joints resolve, the PD gains hold the default pose, and a 750->20 policy
can be driven end to end. Isaac-only pieces (USD conversion, SceneEntityCfg regex
resolution, reward terms) are NOT covered.

    # does the robot stand up under the configured PD gains and default pose?
    python legged_lab/scripts/smoke_test_x2_mujoco.py --policy none

    # drive TienKung's pretrained walk policy on X2 (it is expected to fall)
    python legged_lab/scripts/smoke_test_x2_mujoco.py --policy Exported_policy/walk.pt --render
"""

import argparse
import math
import os

import mujoco
import numpy as np
import torch

from legged_lab.assets import ISAAC_ASSET_DIR

SCENE = os.path.join(ISAAC_ASSET_DIR, "agibot_x2", "mjcf", "scene.xml")

# The 20 actuated joints in the order Isaac Lab exposes them. The order depends on the physics
# backend (measured with `robot.joint_names`): PhysX walks the tree breadth-first, Newton
# depth-first (left leg, left arm, right leg, right arm). A policy's observation and action
# vectors follow the order of the backend it was trained on, so pass --joint-order accordingly.
JOINT_ORDERS = {
    "physx": [
        "left_hip_pitch_joint", "right_hip_pitch_joint",
        "left_shoulder_pitch_joint", "right_shoulder_pitch_joint",
        "left_hip_roll_joint", "right_hip_roll_joint",
        "left_shoulder_roll_joint", "right_shoulder_roll_joint",
        "left_hip_yaw_joint", "right_hip_yaw_joint",
        "left_shoulder_yaw_joint", "right_shoulder_yaw_joint",
        "left_knee_joint", "right_knee_joint",
        "left_elbow_joint", "right_elbow_joint",
        "left_ankle_pitch_joint", "right_ankle_pitch_joint",
        "left_ankle_roll_joint", "right_ankle_roll_joint",
    ],
    "newton": [
        "left_hip_pitch_joint", "left_hip_roll_joint", "left_hip_yaw_joint", "left_knee_joint",
        "left_ankle_pitch_joint", "left_ankle_roll_joint",
        "left_shoulder_pitch_joint", "left_shoulder_roll_joint", "left_shoulder_yaw_joint", "left_elbow_joint",
        "right_hip_pitch_joint", "right_hip_roll_joint", "right_hip_yaw_joint", "right_knee_joint",
        "right_ankle_pitch_joint", "right_ankle_roll_joint",
        "right_shoulder_pitch_joint", "right_shoulder_roll_joint", "right_shoulder_yaw_joint", "right_elbow_joint",
    ],
}  # fmt: skip
ISAAC_JOINT_ORDER = [
    "left_hip_pitch_joint", "right_hip_pitch_joint",
    "left_shoulder_pitch_joint", "right_shoulder_pitch_joint",
    "left_hip_roll_joint", "right_hip_roll_joint",
    "left_shoulder_roll_joint", "right_shoulder_roll_joint",
    "left_hip_yaw_joint", "right_hip_yaw_joint",
    "left_shoulder_yaw_joint", "right_shoulder_yaw_joint",
    "left_knee_joint", "right_knee_joint",
    "left_elbow_joint", "right_elbow_joint",
    "left_ankle_pitch_joint", "right_ankle_pitch_joint",
    "left_ankle_roll_joint", "right_ankle_roll_joint",
]  # fmt: skip

# Held at zero, mirroring the fixed joints in x2_ultra_locked20.urdf.
LOCKED_JOINTS = [
    "waist_yaw_joint", "waist_pitch_joint", "waist_roll_joint",
    "head_yaw_joint", "head_pitch_joint",
    "left_wrist_yaw_joint", "left_wrist_pitch_joint", "left_wrist_roll_joint",
    "right_wrist_yaw_joint", "right_wrist_pitch_joint", "right_wrist_roll_joint",
]  # fmt: skip

# Must match AGIBOT_X2_CFG in legged_lab/assets/agibot_x2/agibot_x2.py.
DEFAULT_POSE = {
    "hip_roll": 0.0, "hip_pitch": -0.5, "hip_yaw": 0.0, "knee": 1.0,
    "ankle_pitch": -0.5, "ankle_roll": 0.0,
    "shoulder_pitch": 0.0, "shoulder_roll": 0.15, "shoulder_yaw": 0.0, "elbow": -0.3,
}  # fmt: skip
MIRRORED = {"hip_roll", "shoulder_roll"}  # negated on the right side
GAINS = {
    "hip_roll": (327, 4.7), "hip_pitch": (468, 6.7), "hip_yaw": (401, 4.0), "knee": (536, 7.7),
    "ankle_pitch": (172, 5.5), "ankle_roll": (216, 5.4),
    "shoulder_pitch": (98, 4.9), "shoulder_roll": (33, 2.5), "shoulder_yaw": (94, 3.7), "elbow": (29, 2.9),
}  # fmt: skip
LOCKED_GAIN = (200.0, 5.0)

DT = 0.005
DECIMATION = 4
ACTION_SCALE = 0.25
NUM_OBS_PER_STEP = 75
HISTORY = 10
CLIP_OBS = 100.0
CLIP_ACTIONS = 100.0
PHASE_RATIO = np.array([0.38, 0.38])
PHASE_OFFSET = np.array([0.38, 0.88])
HEADING_STIFFNESS = 0.5  # walk_cfg heading_control_stiffness
HEADING_WZ_MAX = 1.57  # walk_cfg ang_vel_z range


def joint_kind(name):
    return name.replace("left_", "").replace("right_", "").replace("_joint", "")


def default_angle(name):
    kind = joint_kind(name)
    sign = -1.0 if (name.startswith("right_") and kind in MIRRORED) else 1.0
    return sign * DEFAULT_POSE[kind]


class X2Runner:
    def __init__(self, policy_path, gait_cycle, command, seed=None, substeps=1, actuator="torque", frictionloss=None, heading=False):
        self.seed = seed
        self.substeps = substeps
        self.actuator = actuator
        self.model = mujoco.MjModel.from_xml_path(SCENE)
        self.model.opt.timestep = DT / substeps
        if frictionloss is not None:
            # Asset-gap probe: the USD used by both Isaac backends has no joint friction, the vendor MJCF has 0.3 N*m.
            self.model.dof_frictionloss[:] = frictionloss
        self.data = mujoco.MjData(self.model)
        self.gait_cycle = gait_cycle
        self.command = np.array(command, dtype=np.double)
        # Training uses heading_command=True: the env recomputes the yaw-rate command every step as
        # 0.5 * wrap(heading_target - yaw), so the policy never learned to hold a heading by itself.
        self.heading = heading
        self.heading_target = None  # locked to the yaw after reset on the first step

        self.policy = None
        if policy_path and policy_path != "none":
            self.policy = torch.jit.load(policy_path, map_location="cpu")
            self.policy.eval()

        self._resolve_indices()
        self._reset()

    def _resolve_indices(self):
        m = self.model
        self.qpos_adr, self.qvel_adr, self.act_adr, self.ctrl_range = [], [], [], []
        for name in ISAAC_JOINT_ORDER + LOCKED_JOINTS:
            jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, name)
            aid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, f"motor_{name}")
            if jid < 0 or aid < 0:
                raise RuntimeError(f"{name}: joint id {jid}, actuator id {aid}")
            self.qpos_adr.append(m.jnt_qposadr[jid])
            self.qvel_adr.append(m.jnt_dofadr[jid])
            self.act_adr.append(aid)
            self.ctrl_range.append(m.actuator_ctrlrange[aid])
        self.qpos_adr = np.array(self.qpos_adr)
        self.qvel_adr = np.array(self.qvel_adr)
        self.act_adr = np.array(self.act_adr)
        self.ctrl_range = np.array(self.ctrl_range)

        self.default_pos = np.array(
            [default_angle(j) for j in ISAAC_JOINT_ORDER] + [0.0] * len(LOCKED_JOINTS)
        )
        self.kp = np.array([GAINS[joint_kind(j)][0] for j in ISAAC_JOINT_ORDER] + [LOCKED_GAIN[0]] * len(LOCKED_JOINTS))
        self.kd = np.array([GAINS[joint_kind(j)][1] for j in ISAAC_JOINT_ORDER] + [LOCKED_GAIN[1]] * len(LOCKED_JOINTS))
        self.pelvis_bid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "pelvis")
        if self.actuator == "position":
            # Turn the MJCF torque motors into MuJoCo position servos (force = kp*(ctrl - q) - kd*qd) and let the
            # implicitfast integrator treat the PD implicitly -- the same model as Isaac's ImplicitActuator and
            # TienKung's MJCF (<position kp=...> + implicitfast), instead of an explicit PD closed by this script.
            m = self.model
            m.opt.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
            for i, aid in enumerate(self.act_adr):
                m.actuator_gaintype[aid] = mujoco.mjtGain.mjGAIN_FIXED
                m.actuator_biastype[aid] = mujoco.mjtBias.mjBIAS_AFFINE
                m.actuator_gainprm[aid, :] = 0.0
                m.actuator_biasprm[aid, :] = 0.0
                m.actuator_gainprm[aid, 0] = self.kp[i]
                m.actuator_biasprm[aid, 1] = -self.kp[i]
                m.actuator_biasprm[aid, 2] = -self.kd[i]
                m.actuator_forcelimited[aid] = 1
                m.actuator_forcerange[aid] = m.actuator_ctrlrange[aid]  # the motor's torque limit
                m.actuator_ctrllimited[aid] = 0

    def _reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qpos_adr] = self.default_pos
        self.data.qpos[2] = 0.73  # spawn height from AGIBOT_X2_CFG
        if self.seed is not None:
            # Seeded reset perturbation for fall-rate sweeps: joint offsets +-0.05 rad, root yaw, root velocity
            # +-0.2 m/s (milder than training's reset randomisation, which scales joints by 0.5..1.5).
            rng = np.random.default_rng(self.seed)
            n = len(ISAAC_JOINT_ORDER)
            self.data.qpos[self.qpos_adr[:n]] += rng.uniform(-0.05, 0.05, n)
            yaw = rng.uniform(-np.pi, np.pi)
            self.data.qpos[3:7] = [np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)]
            self.data.qvel[0:2] = rng.uniform(-0.2, 0.2, 2)
        mujoco.mj_forward(self.model, self.data)
        self.action = np.zeros(len(ISAAC_JOINT_ORDER))
        self.obs_history = np.zeros(NUM_OBS_PER_STEP * HISTORY, dtype=np.float32)
        self.step_count = 0

    @staticmethod
    def _quat_rotate_inverse(q, v):
        w, xyz = q[0], q[1:]
        a = v * (2.0 * w**2 - 1.0)
        b = np.cross(xyz, v) * w * 2.0
        c = xyz * np.dot(xyz, v) * 2.0
        return a - b + c

    def _gait_phase(self):
        t = self.step_count * DT * DECIMATION / self.gait_cycle
        return (t + PHASE_OFFSET) % 1.0

    def get_obs(self):
        n = len(ISAAC_JOINT_ORDER)
        dof_pos = self.data.qpos[self.qpos_adr[:n]]
        dof_vel = self.data.qvel[self.qvel_adr[:n]]
        quat = self.data.sensor("body-orientation").data  # wxyz
        phase = self._gait_phase()
        obs = np.concatenate([
            self.data.sensor("body-angular-velocity").data,                 # 3
            self._quat_rotate_inverse(quat, np.array([0.0, 0.0, -1.0])),    # 3
            self.command,                                                   # 3
            dof_pos - self.default_pos[:n],                                 # 20
            dof_vel,                                                        # 20
            np.clip(self.action, -CLIP_ACTIONS, CLIP_ACTIONS),              # 20
            np.sin(2 * np.pi * phase), np.cos(2 * np.pi * phase),           # 4
            PHASE_RATIO,                                                    # 2
        ]).astype(np.float32)  # fmt: skip
        self.obs_history = np.roll(self.obs_history, -NUM_OBS_PER_STEP)
        self.obs_history[-NUM_OBS_PER_STEP:] = obs
        return np.clip(self.obs_history, -CLIP_OBS, CLIP_OBS)

    def apply_control(self):
        target = self.default_pos.copy()
        target[: len(self.action)] += self.action * ACTION_SCALE
        if self.actuator == "position":
            self.data.ctrl[self.act_adr] = target
            return
        q = self.data.qpos[self.qpos_adr]
        qd = self.data.qvel[self.qvel_adr]
        tau = self.kp * (target - q) - self.kd * qd
        self.data.ctrl[self.act_adr] = np.clip(tau, self.ctrl_range[:, 0], self.ctrl_range[:, 1])

    def _yaw(self):
        w, x, y, z = self.data.sensor("body-orientation").data
        return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))

    def step(self):
        if self.heading:  # same law as isaaclab UniformVelocityCommand (stiffness 0.5, clipped to the ang_vel_z range)
            if self.heading_target is None:
                self.heading_target = self._yaw()
            err = (self.heading_target - self._yaw() + math.pi) % (2 * math.pi) - math.pi
            self.command[2] = float(np.clip(HEADING_STIFFNESS * err, -HEADING_WZ_MAX, HEADING_WZ_MAX))
        obs = self.get_obs()
        if self.policy is not None:
            with torch.no_grad():
                out = self.policy(torch.from_numpy(obs).unsqueeze(0)).numpy()[0]
            self.action = np.clip(out[: len(ISAAC_JOINT_ORDER)], -CLIP_ACTIONS, CLIP_ACTIONS)
        for _ in range(DECIMATION * self.substeps):
            self.apply_control()
            mujoco.mj_step(self.model, self.data)
        self.step_count += 1

    @property
    def pelvis_height(self):
        return float(self.data.xpos[self.pelvis_bid][2])


def report_layout(runner):
    m = runner.model
    print(f"model      : {m.nbody} bodies, {m.njnt} joints, {m.nu} actuators, {m.nsensor} sensors")
    print(f"controlled : {len(ISAAC_JOINT_ORDER)} actuated + {len(LOCKED_JOINTS)} locked = {m.nu}")
    adr = {}
    for kind in ("jointpos", "jointvel"):
        first = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SENSOR, f"{kind}_{ISAAC_JOINT_ORDER[0]}")
        adr[kind] = m.sensor_adr[first]
    print(f"sensordata : jointpos starts at {adr['jointpos']}, jointvel at {adr['jointvel']} (total {m.nsensordata})")
    torque = m.actuator_ctrlrange[runner.act_adr[0]]
    print(f"actuators  : torque motors, ctrlrange e.g. {torque} -- PD is closed in this script")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--policy", type=str, default="none", help="TorchScript policy, or 'none' to hold the default pose")
    p.add_argument("--duration", type=float, default=5.0, help="seconds of simulated time")
    p.add_argument("--command", type=float, nargs=3, default=[0.5, 0.0, 0.0], help="lin_vel_x lin_vel_y ang_vel_z")
    # walk.pt was trained at TienKung's 0.85 s cycle; X2's config uses 0.68 s.
    p.add_argument("--gait-cycle", type=float, default=0.85)
    p.add_argument("--joint-order", choices=sorted(JOINT_ORDERS), default="physx",
                   help="physics backend the policy was trained on (sets the joint order)")
    p.add_argument("--render", action="store_true", help="save frames to a video directory")
    p.add_argument("--out", type=str, default="outputs/x2_smoke")
    p.add_argument("--fps", type=int, default=25, help="video frame rate (control runs at 50 Hz)")
    p.add_argument("--size", type=int, nargs=2, default=[1280, 720], help="video width height")
    p.add_argument("--seed", type=int, default=None, help="perturb the reset (joint offsets, yaw, root velocity)")
    p.add_argument("--quiet", action="store_true", help="skip the per-0.2 s trace")
    p.add_argument("--actuator", choices=["torque", "position"], default="torque",
                   help="torque: explicit PD closed here on the MJCF motors; position: MuJoCo position servos + implicitfast")
    p.add_argument("--heading", action="store_true",
                   help="close the heading loop like training (heading_command=True): wz = 0.5 * wrap(target - yaw)")
    p.add_argument("--frictionloss", type=float, default=None,
                   help="override joint frictionloss for every DoF (0 = match the USD asset, which has none)")
    p.add_argument("--substeps", type=int, default=1,
                   help="physics/PD substeps per 5 ms control tick (5 = 1 kHz explicit PD; Isaac uses implicit PD at 5 ms)")
    args = p.parse_args()

    ISAAC_JOINT_ORDER[:] = JOINT_ORDERS[args.joint_order]
    runner = X2Runner(args.policy, args.gait_cycle, args.command, seed=args.seed, substeps=args.substeps,
                      actuator=args.actuator, frictionloss=args.frictionloss, heading=args.heading)
    if not args.quiet:
        report_layout(runner)
    print(f"policy     : {args.policy}   command={args.command}   gait_cycle={args.gait_cycle}s")
    print(f"pelvis at reset: {runner.pelvis_height:.3f} m\n")

    renderer = frames = camera = None
    frame_every = max(1, round(1.0 / (DT * DECIMATION) / args.fps))
    if args.render:
        os.makedirs(args.out, exist_ok=True)
        runner.model.vis.global_.offwidth = max(runner.model.vis.global_.offwidth, args.size[0])
        runner.model.vis.global_.offheight = max(runner.model.vis.global_.offheight, args.size[1])
        renderer = mujoco.Renderer(runner.model, height=args.size[1], width=args.size[0])
        camera = mujoco.MjvCamera()
        camera.type = mujoco.mjtCamera.mjCAMERA_TRACKING
        camera.trackbodyid = runner.pelvis_bid
        camera.distance, camera.azimuth, camera.elevation = 3.0, 135.0, -20.0
        frames = []

    n_steps = int(args.duration / (DT * DECIMATION))
    fallen_at = None
    start_xy = runner.data.xpos[runner.pelvis_bid][:2].copy()
    for i in range(n_steps):
        runner.step()
        h = runner.pelvis_height
        if fallen_at is None and h < 0.35:
            fallen_at = runner.step_count * DT * DECIMATION
        if i % 10 == 0 and not args.quiet:
            t = runner.step_count * DT * DECIMATION
            print(f"  t={t:5.2f}s  pelvis={h:.3f} m  |action|={np.abs(runner.action).mean():.3f}")
        if renderer is not None and i % frame_every == 0:
            renderer.update_scene(runner.data, camera=camera)
            frames.append(renderer.render())

    moved = runner.data.xpos[runner.pelvis_bid][:2] - start_xy
    print(f"\nfinal pelvis height: {runner.pelvis_height:.3f} m")
    print(f"pelvis moved       : x={moved[0]:+.2f} m  y={moved[1]:+.2f} m  (mean vx={moved[0] / args.duration:.2f} m/s)")
    print(f"fell (< 0.35 m)    : {'no' if fallen_at is None else f'yes, at t={fallen_at:.2f}s'}")
    print(f"RESULT policy={os.path.basename(args.policy)} cmd={args.command[0]:.1f} seed={args.seed} substeps={args.substeps} act={args.actuator} fl={args.frictionloss} hd={int(args.heading)} "
          f"fell={'yes' if fallen_at is not None else 'no'} t_fall={fallen_at if fallen_at is not None else -1:.2f} "
          f"dx={moved[0]:+.2f} dy={moved[1]:+.2f}")

    if frames:
        import imageio.v2 as imageio

        video = os.path.join(args.out, "rollout.mp4")
        imageio.mimsave(video, frames, fps=args.fps)
        # A strip of evenly spaced frames, for machines without a viewer window.
        picks = np.linspace(0, len(frames) - 1, min(6, len(frames))).astype(int)
        strip = os.path.join(args.out, "strip.png")
        imageio.imwrite(strip, np.hstack([frames[i] for i in picks]))
        print(f"video              : {video} ({len(frames)} frames)")
        print(f"strip              : {strip}")


if __name__ == "__main__":
    main()
