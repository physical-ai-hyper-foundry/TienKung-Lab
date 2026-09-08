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
import os

import mujoco
import numpy as np
import torch

from legged_lab.assets import ISAAC_ASSET_DIR

SCENE = os.path.join(ISAAC_ASSET_DIR, "agibot_x2", "mjcf", "scene.xml")

# The 20 actuated joints in the order Isaac Lab is predicted to expose them (breadth-first
# from the root, siblings in URDF declaration order, fixed joints collapsed). Confirm this
# against `robot.joint_names` the first time the task runs under Isaac Lab.
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


def joint_kind(name):
    return name.replace("left_", "").replace("right_", "").replace("_joint", "")


def default_angle(name):
    kind = joint_kind(name)
    sign = -1.0 if (name.startswith("right_") and kind in MIRRORED) else 1.0
    return sign * DEFAULT_POSE[kind]


class X2Runner:
    def __init__(self, policy_path, gait_cycle, command):
        self.model = mujoco.MjModel.from_xml_path(SCENE)
        self.model.opt.timestep = DT
        self.data = mujoco.MjData(self.model)
        self.gait_cycle = gait_cycle
        self.command = np.array(command, dtype=np.double)

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

    def _reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qpos_adr] = self.default_pos
        self.data.qpos[2] = 0.73  # spawn height from AGIBOT_X2_CFG
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
        q = self.data.qpos[self.qpos_adr]
        qd = self.data.qvel[self.qvel_adr]
        tau = self.kp * (target - q) - self.kd * qd
        self.data.ctrl[self.act_adr] = np.clip(tau, self.ctrl_range[:, 0], self.ctrl_range[:, 1])

    def step(self):
        obs = self.get_obs()
        if self.policy is not None:
            with torch.no_grad():
                out = self.policy(torch.from_numpy(obs).unsqueeze(0)).numpy()[0]
            self.action = np.clip(out[: len(ISAAC_JOINT_ORDER)], -CLIP_ACTIONS, CLIP_ACTIONS)
        for _ in range(DECIMATION):
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
    p.add_argument("--render", action="store_true", help="save frames to a video directory")
    p.add_argument("--out", type=str, default="outputs/x2_smoke")
    args = p.parse_args()

    runner = X2Runner(args.policy, args.gait_cycle, args.command)
    report_layout(runner)
    print(f"policy     : {args.policy}   command={args.command}   gait_cycle={args.gait_cycle}s")
    print(f"pelvis at reset: {runner.pelvis_height:.3f} m\n")

    renderer = frames = None
    if args.render:
        os.makedirs(args.out, exist_ok=True)
        renderer = mujoco.Renderer(runner.model, height=480, width=640)
        frames = []

    n_steps = int(args.duration / (DT * DECIMATION))
    fallen_at = None
    for i in range(n_steps):
        runner.step()
        h = runner.pelvis_height
        if fallen_at is None and h < 0.35:
            fallen_at = runner.step_count * DT * DECIMATION
        if i % 10 == 0:
            t = runner.step_count * DT * DECIMATION
            print(f"  t={t:5.2f}s  pelvis={h:.3f} m  |action|={np.abs(runner.action).mean():.3f}")
        if renderer is not None and i % 5 == 0:
            renderer.update_scene(runner.data, camera=-1)
            frames.append(renderer.render())

    print(f"\nfinal pelvis height: {runner.pelvis_height:.3f} m")
    print(f"fell (< 0.35 m)    : {'no' if fallen_at is None else f'yes, at t={fallen_at:.2f}s'}")

    if frames:
        import imageio.v2 as imageio

        video = os.path.join(args.out, "rollout.mp4")
        imageio.mimsave(video, frames, fps=10)
        # A strip of evenly spaced frames, for machines without a viewer window.
        picks = np.linspace(0, len(frames) - 1, min(6, len(frames))).astype(int)
        strip = os.path.join(args.out, "strip.png")
        imageio.imwrite(strip, np.hstack([frames[i] for i in picks]))
        print(f"video              : {video} ({len(frames)} frames)")
        print(f"strip              : {strip}")


if __name__ == "__main__":
    main()
