# Copyright (c) 2025-2026, The TienKung-Lab Project Developers.
# All rights reserved.
# Distributed under the BSD-3-Clause license.

"""Side-by-side video: an Isaac rollout replayed kinematically vs the same policy simulated in MuJoCo.

Left  = Isaac physics. Root pose + joint angles recorded by `play.py --record`, only rendered here.
Right = MuJoCo physics. Same TorchScript policy, same forward command, heading hold to 0 as in training.

    python legged_lab/scripts/play.py --task=x2_walk --load_run <run> --checkpoint model_N.pt \
        --num_envs 1 --lin_vel_x 0.5 --record outputs/isaac_N.npz
    python legged_lab/scripts/render_isaac_vs_mujoco_x2.py --isaac outputs/isaac_N.npz \
        --policy logs/x2_walk/<run>/exported/policy_N.pt
"""

import argparse
import os
import sys

import imageio.v2 as imageio
import mujoco
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from sim2sim_x2 import ANG_VEL_Z_RANGE, HEADING_STIFFNESS, heading, wrap_to_pi  # noqa: E402
from smoke_test_x2_mujoco import X2Runner  # noqa: E402

try:
    import cv2
except ImportError:
    cv2 = None

W, H = 640, 480
FALL_HEIGHT = 0.35


def aim_camera(cam, data, body_id):
    # Free camera re-aimed every frame: the tracking camera smooths its lookat across update_scene
    # calls, so sharing one between two robots far apart drifts off both.
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat[:] = data.xpos[body_id]
    cam.distance, cam.elevation, cam.azimuth = 3.0, -15.0, 135.0
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
    p.add_argument("--isaac", required=True, help=".npz from play.py --record")
    p.add_argument("--policy", required=True, help="TorchScript policy for the MuJoCo side")
    p.add_argument("--gait-cycle", type=float, default=0.68)
    p.add_argument("--fps", type=int, default=25)
    p.add_argument("--out", default=None, help="output .mp4 (default: next to the .npz)")
    args = p.parse_args()

    rec = np.load(args.isaac, allow_pickle=False)
    dt = float(rec["dt"])
    vx = float(rec["lin_vel_x"])
    n_steps = len(rec["root_pos"])
    every = max(1, round(1.0 / (dt * args.fps)))
    name = os.path.splitext(os.path.basename(args.policy))[0]
    out = args.out or os.path.splitext(args.isaac)[0] + "_vs_mujoco.mp4"

    # MuJoCo physics side
    sim = X2Runner(args.policy, args.gait_cycle, [vx, 0.0, 0.0])
    target = heading(sim)
    model = sim.model

    # Isaac replay side: same model, separate data, no stepping
    replay = mujoco.MjData(model)
    qadr = []
    for jn in rec["joint_names"]:
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, str(jn))
        if jid < 0:
            raise RuntimeError(f"joint {jn} from Isaac not found in MJCF")
        qadr.append(model.jnt_qposadr[jid])
    qadr = np.array(qadr)

    renderer = mujoco.Renderer(model, height=H, width=W)
    cam = mujoco.MjvCamera()
    frames = []
    isaac_fell = mj_fell = None

    for i in range(n_steps):
        replay.qpos[:] = 0.0
        replay.qpos[0:3] = rec["root_pos"][i]
        x, y, z, w = rec["root_quat_xyzw"][i]
        replay.qpos[3:7] = (w, x, y, z)
        replay.qpos[qadr] = rec["joint_pos"][i]
        mujoco.mj_forward(model, replay)
        if isaac_fell is None and (rec["done"][i] or replay.xpos[sim.pelvis_bid][2] < FALL_HEIGHT):
            isaac_fell = i * dt

        err = wrap_to_pi(target - heading(sim))
        sim.command[2] = np.clip(HEADING_STIFFNESS * err, *ANG_VEL_Z_RANGE)
        sim.step()
        if mj_fell is None and sim.pelvis_height < FALL_HEIGHT:
            mj_fell = i * dt

        if i % every == 0:
            t = i * dt
            renderer.update_scene(replay, camera=aim_camera(cam, replay, sim.pelvis_bid))
            left = label(renderer.render(), [f"Isaac  {name}", f"t={t:4.1f}s  cmd vx={vx:.1f}",
                                             "FELL" if isaac_fell is not None else ""])
            renderer.update_scene(sim.data, camera=aim_camera(cam, sim.data, sim.pelvis_bid))
            right = label(renderer.render(), [f"MuJoCo  {name}", f"t={t:4.1f}s  cmd vx={vx:.1f}",
                                              "FELL" if mj_fell is not None else ""])
            frames.append(np.hstack([left, np.full((H, 4, 3), 255, np.uint8), right]))

    imageio.mimsave(out, frames, fps=args.fps)
    picks = np.linspace(0, len(frames) - 1, min(4, len(frames))).astype(int)
    strip = os.path.splitext(out)[0] + "_strip.png"
    imageio.imwrite(strip, np.vstack([frames[k] for k in picks]))

    def pos(d):
        return f"({d.qpos[0]:+.2f}, {d.qpos[1]:+.2f})"

    print(f"steps={n_steps} dt={dt}s  video={out} ({len(frames)} frames @ {args.fps} fps)  strip={strip}")
    print(f"Isaac : fell={'no' if isaac_fell is None else f'{isaac_fell:.2f}s'}  final pos={pos(replay)}")
    print(f"MuJoCo: fell={'no' if mj_fell is None else f'{mj_fell:.2f}s'}  final pos={pos(sim.data)}")


if __name__ == "__main__":
    main()
