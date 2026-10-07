# Copyright (c) 2025-2026, The TienKung-Lab Project Developers.
# All rights reserved.
# Distributed under the BSD-3-Clause license.

"""Side-by-side video of two Isaac rollouts, each recorded with ``play.py --record``.

Both sides are Isaac physics; MuJoCo is only the renderer. Each rollout is paired with the MJCF
of the robot it was recorded on, so robots with different models can be compared fairly.

    python legged_lab/scripts/play.py --task=walk --jit_policy Exported_policy/walk.pt \
        --num_envs 1 --lin_vel_x 0.5 --record outputs/isaac_tienkung_walk.npz
    python legged_lab/scripts/render_isaac_replays.py \
        --left  outputs/isaac_tienkung_walk.npz --left-model tienkung  --left-label "TienKung + walk.pt" \
        --right outputs/isaac_vs_mujoco/isaac_39000.npz --right-model x2 --right-label "AgiBot X2 + policy_39000"
"""

import argparse
import os

import imageio.v2 as imageio
import mujoco
import numpy as np

from legged_lab.assets import ISAAC_ASSET_DIR

try:
    import cv2
except ImportError:
    cv2 = None

W, H = 640, 480
MODELS = {
    "x2": (os.path.join(ISAAC_ASSET_DIR, "agibot_x2", "mjcf", "scene.xml"), "pelvis", 3.0, 0.35),
    "tienkung": (os.path.join(ISAAC_ASSET_DIR, "tienkung2_lite", "mjcf", "tienkung.xml"), "Base_link", 4.0, 0.50),
}


class Replay:
    """One recorded Isaac rollout, posed on its own MuJoCo model for rendering."""

    def __init__(self, npz_path, model_key, label):
        xml, root_body, self.cam_distance, self.fall_height = MODELS[model_key]
        self.label = label
        self.rec = np.load(npz_path, allow_pickle=False)
        self.model = mujoco.MjModel.from_xml_path(xml)
        self.data = mujoco.MjData(self.model)
        self.renderer = mujoco.Renderer(self.model, height=H, width=W)
        self.root_bid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, root_body)
        self.qadr = np.array([
            self.model.jnt_qposadr[mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, str(j))]
            for j in self.rec["joint_names"]
        ])  # fmt: skip
        if (self.qadr < 0).any():
            raise RuntimeError(f"{npz_path}: some Isaac joints are missing from {xml}")
        self.dt = float(self.rec["dt"])
        self.n_steps = len(self.rec["root_pos"])
        self.fell_at = None

    def pose(self, i):
        self.data.qpos[:] = 0.0
        self.data.qpos[0:3] = self.rec["root_pos"][i]
        x, y, z, w = self.rec["root_quat_xyzw"][i]
        self.data.qpos[3:7] = (w, x, y, z)
        self.data.qpos[self.qadr] = self.rec["joint_pos"][i]
        mujoco.mj_forward(self.model, self.data)
        height = float(self.data.xpos[self.root_bid][2])
        if self.fell_at is None and (bool(self.rec["done"][i]) or height < self.fall_height):
            self.fell_at = i * self.dt

    def render(self, cam, t, cmd_vx):
        cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        cam.lookat[:] = self.data.xpos[self.root_bid]
        cam.distance, cam.elevation, cam.azimuth = self.cam_distance, -15.0, 135.0
        self.renderer.update_scene(self.data, camera=cam)
        lines = [f"{self.label} (Isaac)", f"t={t:4.1f}s  cmd vx={cmd_vx:.1f}",
                 "FELL" if self.fell_at is not None else ""]  # fmt: skip
        return label_frame(self.renderer.render(), lines)


def label_frame(frame, lines):
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
    p.add_argument("--left", required=True)
    p.add_argument("--left-model", required=True, choices=sorted(MODELS))
    p.add_argument("--left-label", required=True)
    p.add_argument("--right", required=True)
    p.add_argument("--right-model", required=True, choices=sorted(MODELS))
    p.add_argument("--right-label", required=True)
    p.add_argument("--fps", type=int, default=25)
    p.add_argument("--out", default="outputs/isaac_compare/compare.mp4")
    args = p.parse_args()

    left = Replay(args.left, args.left_model, args.left_label)
    right = Replay(args.right, args.right_model, args.right_label)
    if abs(left.dt - right.dt) > 1e-9:
        raise RuntimeError(f"control dt differs: {left.dt} vs {right.dt}")

    dt = left.dt
    n_steps = min(left.n_steps, right.n_steps)
    cmd_vx = float(left.rec["lin_vel_x"])
    every = max(1, round(1.0 / (dt * args.fps)))
    cam = mujoco.MjvCamera()
    frames = []

    for i in range(n_steps):
        left.pose(i)
        right.pose(i)
        if i % every == 0:
            t = i * dt
            frames.append(np.hstack([
                left.render(cam, t, cmd_vx),
                np.full((H, 4, 3), 255, np.uint8),
                right.render(cam, t, float(right.rec["lin_vel_x"])),
            ]))  # fmt: skip

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    imageio.mimsave(args.out, frames, fps=args.fps)
    picks = np.linspace(0, len(frames) - 1, min(4, len(frames))).astype(int)
    strip = os.path.splitext(args.out)[0] + "_strip.png"
    imageio.imwrite(strip, np.vstack([frames[k] for k in picks]))

    print(f"steps={n_steps} dt={dt}s  video={args.out} ({len(frames)} frames)  strip={strip}")
    for side in (left, right):
        print(f"{side.label:34s} fell={'no' if side.fell_at is None else f'{side.fell_at:.2f}s'}  "
              f"final pos=({side.data.qpos[0]:+.2f}, {side.data.qpos[1]:+.2f})")  # fmt: skip


if __name__ == "__main__":
    main()
