# Copyright (c) 2025-2026, The TienKung-Lab Project Developers.
# All rights reserved.
# Distributed under the BSD-3-Clause license.

"""Roll out a checkpoint headless in Isaac Lab and save an mp4 of one robot.

Same environment setup as ``play.py`` (flat terrain, no noise, no pushes) but with a fixed
velocity command, a single robot and a chase camera. Frames come from Isaac Lab 3.0's
``VideoRecorder``: the Kit RTX camera on PhysX, the Newton GL viewer on Newton.

    python legged_lab/scripts/record_play.py --task=x2_walk --headless --enable_cameras \\
        --load_run=2026-09-16_15-17-02_newton --checkpoint=model_40000.pt --physics=newton \\
        --command 0.5 0 0 --duration 10 --out outputs/isaac_newton_40000.mp4
"""

import argparse

from isaaclab.app import AppLauncher

from legged_lab.utils import task_registry
from rsl_rl.runners import AmpOnPolicyRunner, OnPolicyRunner  # noqa: F401

import legged_lab.utils.cli_args as cli_args  # isort: skip

parser = argparse.ArgumentParser(description="Record a policy rollout to mp4.")
parser.add_argument("--task", type=str, required=True)
parser.add_argument("--physics", type=str, default=None, choices=["physx", "newton"])
parser.add_argument("--command", type=float, nargs=3, default=[0.5, 0.0, 0.0], help="lin_vel_x lin_vel_y ang_vel_z")
parser.add_argument(
    "--newton_contacts", type=str, default=None, choices=["newton", "mujoco"],
    help="Collision detection under the Newton backend (default: task config).",
)
parser.add_argument("--duration", type=float, default=10.0, help="seconds of simulated time")
parser.add_argument("--fps", type=int, default=25)
parser.add_argument("--size", type=int, nargs=2, default=[1280, 720])
parser.add_argument("--out", type=str, default="outputs/record.mp4", help="output .mp4 path")
parser.add_argument("--seed", type=int, default=None)
parser.add_argument("--no_video", action="store_true", help="skip frame capture (numbers only; no --enable_cameras needed)")
parser.add_argument("--policy", type=str, default="checkpoint", choices=["checkpoint", "none"],
                    help="'none' sends zero actions (hold the default pose) -- a standing test without a checkpoint")
parser.add_argument("--policy_joint_order", type=str, default=None, choices=["physx", "newton"],
                    help="joint order the checkpoint was trained with (PhysX = breadth-first, Newton = depth-first). "
                    "Set it when replaying a checkpoint on the other backend; observations and actions are permuted.")
cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)
args_cli, _ = parser.parse_known_args()
args_cli.headless = True
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import math  # noqa: E402
import os  # noqa: E402

import imageio.v2 as imageio  # noqa: E402
import torch  # noqa: E402
from isaaclab.envs.utils.video_recorder_cfg import VideoRecorderCfg  # noqa: E402
from isaaclab_tasks.utils import get_checkpoint_path  # noqa: E402

from legged_lab.envs import *  # noqa: E402,F401,F403
from legged_lab.utils.cli_args import update_rsl_rl_cfg  # noqa: E402


def record():
    env_cfg, agent_cfg = task_registry.get_cfgs(args_cli.task)
    env_class = task_registry.get_task_class(args_cli.task)

    vx, vy, wz = args_cli.command
    env_cfg.noise.add_noise = False
    env_cfg.domain_rand.events.push_robot = None
    # Deterministic start: no reset randomisation of the root pose/velocity or the joint scale
    # (training uses pose +-0.5 m, random yaw, +-0.5 m/s and joint scale 0.5..1.5).
    ev = env_cfg.domain_rand.events
    ev.reset_base.params["pose_range"] = {"x": (0.0, 0.0), "y": (0.0, 0.0), "yaw": (0.0, 0.0)}
    ev.reset_base.params["velocity_range"] = {k: (0.0, 0.0) for k in ("x", "y", "z", "roll", "pitch", "yaw")}
    ev.reset_robot_joints.params["position_range"] = (1.0, 1.0)
    env_cfg.scene.max_episode_length_s = args_cli.duration + 5.0
    env_cfg.scene.num_envs = 1
    env_cfg.scene.terrain_generator = None
    env_cfg.scene.terrain_type = "plane"
    env_cfg.scene.height_scanner.drift_range = (0.0, 0.0)
    env_cfg.commands.rel_standing_envs = 0.0
    env_cfg.commands.heading_command = False
    env_cfg.commands.ranges.lin_vel_x = (vx, vx)
    env_cfg.commands.ranges.lin_vel_y = (vy, vy)
    env_cfg.commands.ranges.ang_vel_z = (wz, wz)
    if args_cli.physics is not None:
        env_cfg.sim.physics_backend = args_cli.physics
    if args_cli.newton_contacts is not None:
        env_cfg.sim.newton_contacts = args_cli.newton_contacts

    agent_cfg = update_rsl_rl_cfg(agent_cfg, args_cli)
    env_cfg.scene.seed = agent_cfg.seed
    env = env_class(env_cfg, True)

    if args_cli.policy == "none":
        print("[INFO] policy: none (zero actions, default pose held by the PD controller)")

        def policy(obs):
            return torch.zeros(env.num_envs, env.num_actions, device=env.device)

    else:
        log_root_path = os.path.abspath(os.path.join("logs", agent_cfg.experiment_name))
        resume_path = get_checkpoint_path(log_root_path, agent_cfg.load_run, agent_cfg.load_checkpoint)
        print(f"[INFO] checkpoint: {resume_path}")
        runner = eval(agent_cfg.runner_class_name)(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
        runner.load(resume_path, load_optimizer=False)
        policy = runner.get_inference_policy(device=env.device)
        if args_cli.policy_joint_order and args_cli.policy_joint_order != env_cfg.sim.physics_backend:
            # The two backends enumerate joints differently, so a checkpoint's obs/action layout only matches the
            # backend it was trained on. Permute the joint slices of every stacked observation frame into the
            # policy's order and the policy's actions back into the env's order.
            from legged_lab.scripts.smoke_test_x2_mujoco import JOINT_ORDERS

            env_names = list(env.robot.joint_names)
            pol_names = JOINT_ORDERS[args_cli.policy_joint_order]
            assert sorted(env_names) == sorted(pol_names), "joint name sets differ"
            to_pol = torch.tensor([env_names.index(n) for n in pol_names], device=env.device)
            to_env = torch.tensor([pol_names.index(n) for n in env_names], device=env.device)
            n_act = int(env.num_actions)
            # not `frame`: record() rebinds that name to the captured uint8 image, and the closure would read it
            obs_frame = 9 + 3 * n_act + 6  # ang_vel, gravity, command | joint_pos, joint_vel, action | gait sin/cos/ratio
            print(f"[INFO] policy joint order: {args_cli.policy_joint_order} (env: {env_cfg.sim.physics_backend}); "
                  f"permuting obs frames of {obs_frame} and actions")

            def make_permuted(inner):
                def permuted(obs):
                    assert obs.shape[1] % obs_frame == 0, f"obs dim {obs.shape[1]} is not a multiple of {obs_frame}"
                    o = obs.view(obs.shape[0], -1, obs_frame).clone()
                    for start in (9, 9 + n_act, 9 + 2 * n_act):
                        o[:, :, start : start + n_act] = o[:, :, start : start + n_act][:, :, to_pol]
                    return inner(o.view(obs.shape[0], -1))[:, to_env]

                return permuted

            policy = make_permuted(policy)

    recorder = capture = None
    if not args_cli.no_video:
        vr_cfg = VideoRecorderCfg(
            env_render_mode="rgb_array",
            backend_source="renderer",
            window_width=args_cli.size[0],
            window_height=args_cli.size[1],
        )
        recorder = vr_cfg.class_type(vr_cfg, env.scene)
        capture = recorder._capture
    cam_offset = (-1.6, -2.6, 1.1)  # behind-left of the robot, slightly above

    def aim_camera():
        root = env.robot.data.root_link_pos_w.torch[0].tolist()
        eye = tuple(root[i] + cam_offset[i] for i in range(3))
        lookat = (root[0] + 0.3, root[1], root[2] - 0.2)
        if hasattr(capture, "update_camera"):  # Newton GL viewer
            capture.update_camera(eye, lookat)
        else:  # Kit RTX perspective camera (PhysX)
            from isaacsim.core.rendering_manager import ViewportManager

            capture.cfg.eye, capture.cfg.lookat = eye, lookat
            ViewportManager.set_camera_view(capture.cfg.camera_prim_path, eye=list(eye), target=list(lookat))

    frame_every = max(1, round(1.0 / env.step_dt / args_cli.fps))
    n_steps = int(math.ceil(args_cli.duration / env.step_dt))
    frames = []
    obs, _ = env.get_observations()
    start = env.robot.data.root_link_pos_w.torch[0].clone()
    fallen_at = None
    z_min = float(start[2])
    z_trace = []
    for i in range(n_steps):
        with torch.inference_mode():
            actions = policy(obs)
            obs, _, dones, _ = env.step(actions)
        t = (i + 1) * env.step_dt
        z = float(env.robot.data.root_link_pos_w.torch[0, 2])
        z_min = min(z_min, z)
        if i % max(1, round(0.5 / env.step_dt)) == 0:
            z_trace.append(f"{t:.1f}s:{z:.3f}")
        if fallen_at is None and bool(dones[0]):
            fallen_at = t
        if recorder is not None and i % frame_every == 0:
            aim_camera()
            frame = recorder.render_rgb_array()
            if frame is not None:
                frames.append(frame[..., :3].copy())
    moved = (env.robot.data.root_link_pos_w.torch[0] - start).tolist()

    if recorder is not None:
        os.makedirs(os.path.dirname(os.path.abspath(args_cli.out)), exist_ok=True)
        imageio.mimsave(args_cli.out, frames, fps=args_cli.fps)
        print(f"RECORD frames={len(frames)} fps={args_cli.fps} out={args_cli.out}")
    print(f"RECORD moved x={moved[0]:+.2f} y={moved[1]:+.2f} (mean vx={moved[0] / args_cli.duration:.2f} m/s)")
    print(f"RECORD fell: {'no' if fallen_at is None else f'yes, at t={fallen_at:.2f}s'}")
    print(f"RECORD pelvis z: start={float(start[2]):.3f} min={z_min:.3f} end={float(env.robot.data.root_link_pos_w.torch[0, 2]):.3f}")
    print("RECORD pelvis z trace: " + " ".join(z_trace))


if __name__ == "__main__":
    record()
    simulation_app.close()
