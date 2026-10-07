# Copyright (c) 2025-2026, The TienKung-Lab Project Developers.
# All rights reserved.
# Distributed under the BSD-3-Clause license.

"""Export one checkpoint to TorchScript / ONNX and exit (``play.py`` keeps simulating after export).

    python legged_lab/scripts/export_policy.py --task=x2_walk --headless \\
        --load_run=2026-09-16_15-17-02_newton --checkpoint=model_40000.pt --physics=newton --name=policy_40000
"""

import argparse

from isaaclab.app import AppLauncher

from legged_lab.utils import task_registry
from rsl_rl.runners import AmpOnPolicyRunner, OnPolicyRunner  # noqa: F401

import legged_lab.utils.cli_args as cli_args  # isort: skip

parser = argparse.ArgumentParser(description="Export a checkpoint and exit.")
parser.add_argument("--task", type=str, required=True)
parser.add_argument("--physics", type=str, default=None, choices=["physx", "newton"])
parser.add_argument("--name", type=str, default="policy", help="output file stem inside <run>/exported/")
parser.add_argument(
    "--newton_contacts", type=str, default=None, choices=["newton", "mujoco"],
    help="Collision detection under the Newton backend (default: task config).",
)
parser.add_argument("--seed", type=int, default=None)
cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)
args_cli, _ = parser.parse_known_args()
args_cli.headless = True
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import os  # noqa: E402

from isaaclab_tasks.utils import get_checkpoint_path  # noqa: E402

from legged_lab.envs import *  # noqa: E402,F401,F403
from legged_lab.utils.cli_args import update_rsl_rl_cfg  # noqa: E402
from legged_lab.utils.exporter import export_policy_as_jit, export_policy_as_onnx  # noqa: E402


def export():
    env_cfg, agent_cfg = task_registry.get_cfgs(args_cli.task)
    env_class = task_registry.get_task_class(args_cli.task)
    env_cfg.scene.num_envs = 1
    env_cfg.scene.terrain_generator = None
    env_cfg.scene.terrain_type = "plane"
    if args_cli.physics is not None:
        env_cfg.sim.physics_backend = args_cli.physics
    if args_cli.newton_contacts is not None:
        env_cfg.sim.newton_contacts = args_cli.newton_contacts
    agent_cfg = update_rsl_rl_cfg(agent_cfg, args_cli)
    env_cfg.scene.seed = agent_cfg.seed
    env = env_class(env_cfg, True)

    log_root_path = os.path.abspath(os.path.join("logs", agent_cfg.experiment_name))
    resume_path = get_checkpoint_path(log_root_path, agent_cfg.load_run, agent_cfg.load_checkpoint)
    runner = eval(agent_cfg.runner_class_name)(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    runner.load(resume_path, load_optimizer=False)

    out_dir = os.path.join(os.path.dirname(resume_path), "exported")
    export_policy_as_jit(runner.alg.policy, runner.obs_normalizer, path=out_dir, filename=f"{args_cli.name}.pt")
    export_policy_as_onnx(runner.alg.policy, normalizer=runner.obs_normalizer, path=out_dir, filename=f"{args_cli.name}.onnx")
    print(f"EXPORT {resume_path} -> {out_dir}/{args_cli.name}.pt")


if __name__ == "__main__":
    export()
    simulation_app.close()
