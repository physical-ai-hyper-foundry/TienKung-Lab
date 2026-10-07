# Copyright (c) 2025-2026, The TienKung-Lab Project Developers.
# All rights reserved.
# Distributed under the BSD-3-Clause license.

"""Side-by-side video: the upstream TienKung walk policy vs our AgiBot X2 port.

Left  = TienKung robot + the project's pretrained ``Exported_policy/walk.pt``, simulated in MuJoCo.
        Same pipeline as sim2sim.py (sensor-based observations, position actuators, 0.85 s gait).
Right = AgiBot X2 + our x2_walk policy. By default this is an Isaac rollout recorded with
        ``play.py --record`` and replayed kinematically, because the X2 policy still falls when
        MuJoCo simulates it. Pass --x2-mujoco to simulate the X2 policy in MuJoCo instead.

Both sides get the same forward command and hold heading 0, as the training config does.

    python legged_lab/scripts/render_tienkung_vs_x2.py \
        --isaac outputs/isaac_vs_mujoco/isaac_39000.npz \
        --x2-policy logs/x2_walk/<run>/exported/policy_39000.pt
"""

import argparse
import os
import sys

import imageio.v2 as imageio
import mujoco
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from sim2sim_x2 import ANG_VEL_Z_RANGE, HEADING_STIFFNESS, heading, wrap_to_pi  # noqa: E402
from smoke_test_x2_mujoco import X2Runner  # noqa: E402

from legged_lab.assets import ISAAC_ASSET_DIR  # noqa: E402

try:
    import cv2
except ImportError:
    cv2 = None

W, H = 640, 480
TIENKUNG_XML = os.path.join(ISAAC_ASSET_DIR, "tienkung2_lite", "mjcf", "tienkung.xml")
X2_SCENE = os.path.join(ISAAC_ASSET_DIR, "agibot_x2", "mjcf", "scene.xml")


class TienKungRunner:
    """Headless version of sim2sim.py's MujocoRunner (no viewer, no keyboard)."""

    DT, DECIMATION, ACTION_SCALE = 0.005, 4, 0.25
    NUM_ACTION, NUM_OBS, HISTORY = 20, 75, 10
    CLIP_OBS, CLIP_ACTIONS = 100.0, 100.0
    GAIT_CYCLE = 0.85
    PHASE_RATIO = np.array([0.38, 0.38])
    PHASE_OFFSET = np.array([0.38, 0.88])
    DEFAULT_POSE = np.array(
        [0, -0.5, 0, 1.0, -0.5, 0, 0, -0.5, 0, 1.0, -0.5, 0, 0, 0.1, 0.0, -0.3, 0, -0.1, 0.0, -0.3]
    )
    # sim2sim.py's index maps between MuJoCo sensor order and Isaac joint order.
    MUJOCO_TO_ISAAC = [0, 6, 12, 16, 1, 7, 13, 17, 2, 8, 14, 18, 3, 9, 15, 19, 4, 10, 5, 11]
    ISAAC_TO_MUJOCO = [0, 4, 8, 12, 16, 18, 1, 5, 9, 13, 17, 19, 2, 6, 10, 14, 3, 7, 11, 15]

    def __init__(self, policy_path, command):
        self.model = mujoco.MjModel.from_xml_path(TIENKUNG_XML)
        self.model.opt.timestep = self.DT
        self.data = mujoco.MjData(self.model)
        self.policy = torch.jit.load(policy_path, map_location="cpu")
        self.policy.eval()
        self.command = np.array(command, dtype=np.double)
        self.root_bid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "Base_link")
        self.action = np.zeros(self.NUM_ACTION)
        self.obs_history = np.zeros(self.NUM_OBS * self.HISTORY, dtype=np.float32)
        self.gait_phase = np.zeros(2)
        self.episode_length_buf = 0
        mujoco.mj_forward(self.model, self.data)

    @property
    def pelvis_height(self):
        return float(self.data.xpos[self.root_bid][2])

    def heading(self):
        fwd = self.data.xmat[self.root_bid].reshape(3, 3)[:, 0]
        return float(np.arctan2(fwd[1], fwd[0]))

    @staticmethod
    def _quat_rotate_inverse(q, v):
        """q is (x, y, z, w), as in sim2sim.py."""
        q_w, q_vec = q[-1], q[:3]
        return v * (2.0 * q_w**2 - 1.0) - np.cross(q_vec, v) * q_w * 2.0 + q_vec * np.dot(q_vec, v) * 2.0

    def get_obs(self):
        dof_pos = self.data.sensordata[0:20]
        dof_vel = self.data.sensordata[20:40]
        quat_xyzw = self.data.sensor("orientation").data[[1, 2, 3, 0]].astype(np.double)
        obs = np.concatenate([
            self.data.sensor("angular-velocity").data.astype(np.double),
            self._quat_rotate_inverse(quat_xyzw, np.array([0.0, 0.0, -1.0])),
            self.command,
            (dof_pos - self.DEFAULT_POSE)[self.MUJOCO_TO_ISAAC],
            dof_vel[self.MUJOCO_TO_ISAAC],
            np.clip(self.action, -self.CLIP_ACTIONS, self.CLIP_ACTIONS),
            np.sin(2 * np.pi * self.gait_phase),
            np.cos(2 * np.pi * self.gait_phase),
            self.PHASE_RATIO,
        ]).astype(np.float32)  # fmt: skip
        self.obs_history = np.roll(self.obs_history, -self.NUM_OBS)
        self.obs_history[-self.NUM_OBS :] = obs
        return np.clip(self.obs_history, -self.CLIP_OBS, self.CLIP_OBS)

    def step(self):
        obs = self.get_obs()
        with torch.no_grad():
            self.action = self.policy(torch.from_numpy(obs)).numpy()[: self.NUM_ACTION]
        self.action = np.clip(self.action, -self.CLIP_ACTIONS, self.CLIP_ACTIONS)
        target = (self.action * self.ACTION_SCALE)[self.ISAAC_TO_MUJOCO] + self.DEFAULT_POSE
        for _ in range(self.DECIMATION):
            self.data.ctrl = target
            mujoco.mj_step(self.model, self.data)
        self.episode_length_buf += 1
        t = self.episode_length_buf * self.DT * self.DECIMATION / self.GAIT_CYCLE
        self.gait_phase = (t + self.PHASE_OFFSET) % 1.0


def aim_camera(cam, data, body_id, distance):
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat[:] = data.xpos[body_id]
    cam.distance, cam.elevation, cam.azimuth = distance, -15.0, 135.0
    return cam


def label(frame, lines):
    if cv2 is None:
        return frame
    frame = np.ascontiguousarray(frame)
    for i, text in enumerate(lines):
        y = 28 + 26 * i
        cv2.putText(frame, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)
    return frame


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--isaac", default=None, help=".npz from play.py --record (X2 side, default mode)")
    p.add_argument("--x2-policy", required=True, help="TorchScript x2_walk policy")
    p.add_argument("--tienkung-policy", default="Exported_policy/walk.pt")
    p.add_argument("--x2-mujoco", action="store_true", help="simulate the X2 policy in MuJoCo instead of replaying Isaac")
    p.add_argument("--lin_vel_x", type=float, default=0.5)
    p.add_argument("--seconds", type=float, default=20.0)
    p.add_argument("--fps", type=int, default=25)
    p.add_argument("--out", default="outputs/tienkung_vs_x2/tienkung_vs_x2.mp4")
    args = p.parse_args()

    if not args.x2_mujoco and not args.isaac:
        p.error("--isaac is required unless --x2-mujoco is given")

    control_dt = 0.02
    x2_name = os.path.splitext(os.path.basename(args.x2_policy))[0]

    tk = TienKungRunner(args.tienkung_policy, [args.lin_vel_x, 0.0, 0.0])
    tk_target = tk.heading()

    x2_sim = X2Runner(args.x2_policy, 0.68, [args.lin_vel_x, 0.0, 0.0])
    x2_target = heading(x2_sim)
    x2_model = x2_sim.model

    if args.x2_mujoco:
        x2_side, x2_data, n_steps = "MuJoCo", x2_sim.data, round(args.seconds / control_dt)
    else:
        rec = np.load(args.isaac, allow_pickle=False)
        control_dt = float(rec["dt"])
        n_steps = min(len(rec["root_pos"]), round(args.seconds / control_dt))
        replay = mujoco.MjData(x2_model)
        qadr = np.array([
            x2_model.jnt_qposadr[mujoco.mj_name2id(x2_model, mujoco.mjtObj.mjOBJ_JOINT, str(j))]
            for j in rec["joint_names"]
        ])  # fmt: skip
        x2_side, x2_data = "Isaac (replay)", replay

    tk_render = mujoco.Renderer(tk.model, height=H, width=W)
    x2_render = mujoco.Renderer(x2_model, height=H, width=W)
    cam = mujoco.MjvCamera()
    every = max(1, round(1.0 / (control_dt * args.fps)))
    frames, tk_fell, x2_fell = [], None, None

    for i in range(n_steps):
        tk.command[2] = np.clip(HEADING_STIFFNESS * wrap_to_pi(tk_target - tk.heading()), *ANG_VEL_Z_RANGE)
        tk.step()
        if tk_fell is None and tk.pelvis_height < 0.5:  # TienKung pelvis stands at ~0.83 m
            tk_fell = i * control_dt

        if args.x2_mujoco:
            x2_sim.command[2] = np.clip(HEADING_STIFFNESS * wrap_to_pi(x2_target - heading(x2_sim)), *ANG_VEL_Z_RANGE)
            x2_sim.step()
        else:
            replay.qpos[:] = 0.0
            replay.qpos[0:3] = rec["root_pos"][i]
            x, y, z, w = rec["root_quat_xyzw"][i]
            replay.qpos[3:7] = (w, x, y, z)
            replay.qpos[qadr] = rec["joint_pos"][i]
            mujoco.mj_forward(x2_model, replay)
        if x2_fell is None and x2_data.xpos[x2_sim.pelvis_bid][2] < 0.35:  # X2 pelvis stands at ~0.73 m
            x2_fell = i * control_dt

        if i % every == 0:
            t = i * control_dt
            tk_render.update_scene(tk.data, camera=aim_camera(cam, tk.data, tk.root_bid, 4.0))
            left = label(tk_render.render(), ["TienKung + walk.pt (MuJoCo)", f"t={t:4.1f}s  cmd vx={args.lin_vel_x:.1f}",
                                              "FELL" if tk_fell is not None else ""])
            x2_render.update_scene(x2_data, camera=aim_camera(cam, x2_data, x2_sim.pelvis_bid, 3.0))
            right = label(x2_render.render(), [f"AgiBot X2 + {x2_name} ({x2_side})",
                                               f"t={t:4.1f}s  cmd vx={args.lin_vel_x:.1f}",
                                               "FELL" if x2_fell is not None else ""])
            frames.append(np.hstack([left, np.full((H, 4, 3), 255, np.uint8), right]))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    imageio.mimsave(args.out, frames, fps=args.fps)
    picks = np.linspace(0, len(frames) - 1, min(4, len(frames))).astype(int)
    strip = os.path.splitext(args.out)[0] + "_strip.png"
    imageio.imwrite(strip, np.vstack([frames[k] for k in picks]))

    print(f"steps={n_steps}  video={args.out} ({len(frames)} frames @ {args.fps} fps)  strip={strip}")
    print(f"TienKung walk.pt : fell={'no' if tk_fell is None else f'{tk_fell:.2f}s'}  "
          f"pos=({tk.data.qpos[0]:+.2f}, {tk.data.qpos[1]:+.2f})")
    print(f"X2 {x2_name} ({x2_side}): fell={'no' if x2_fell is None else f'{x2_fell:.2f}s'}  "
          f"pos=({x2_data.qpos[0]:+.2f}, {x2_data.qpos[1]:+.2f})")


if __name__ == "__main__":
    main()
