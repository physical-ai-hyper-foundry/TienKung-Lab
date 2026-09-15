# Copyright (c) 2022-2025, The Isaac Lab Project Developers.
# All rights reserved.
#
# Copyright (c) 2025-2026, The TienKung-Lab Project Developers.
# All rights reserved.
# Modifications are licensed under the BSD-3-Clause license.
#
# This file contains code derived from the Isaac Lab Project (isaaclab_rl.rsl_rl, v2.1.0),
# with additional modifications by the TienKung-Lab Project,
# and is distributed under the BSD-3-Clause license.

"""RSL-RL runner configuration classes, vendored from Isaac Lab 2.1.0.

Isaac Lab 3.0 restructured ``isaaclab_rl.rsl_rl.RslRlOnPolicyRunnerCfg`` around rsl-rl-lib 5.x
(``actor`` / ``critic`` / ``obs_groups``), but the bundled ``rsl_rl`` package in this repository
(the AMP runner) still consumes the 2.x layout: ``train_cfg["policy"]`` and
``train_cfg["algorithm"]``. Keeping the 2.1 config classes here decouples the task configs
from the installed Isaac Lab version.
"""

from __future__ import annotations

from dataclasses import MISSING
from typing import Literal

from isaaclab.utils import configclass


@configclass
class RslRlRndCfg:
    """Configuration for the Random Network Distillation (RND) module."""

    @configclass
    class WeightScheduleCfg:
        """Configuration for the weight schedule."""

        mode: str = "constant"

    @configclass
    class LinearWeightScheduleCfg(WeightScheduleCfg):
        """Linear decay from :attr:`RslRlRndCfg.weight` to :attr:`final_value`."""

        mode: str = "linear"
        final_value: float = MISSING
        initial_step: int = MISSING
        final_step: int = MISSING

    @configclass
    class StepWeightScheduleCfg(WeightScheduleCfg):
        """Switch to :attr:`final_value` at :attr:`final_step`."""

        mode: str = "step"
        final_step: int = MISSING
        final_value: float = MISSING

    weight: float = 0.0
    weight_schedule: WeightScheduleCfg | None = None
    reward_normalization: bool = False
    state_normalization: bool = False
    learning_rate: float = 1e-3
    num_outputs: int = 1
    predictor_hidden_dims: list[int] = [-1]
    target_hidden_dims: list[int] = [-1]


@configclass
class RslRlSymmetryCfg:
    """Configuration for the symmetry-augmentation in the training."""

    use_data_augmentation: bool = False
    use_mirror_loss: bool = False
    data_augmentation_func: callable = MISSING
    mirror_loss_coeff: float = 0.0


@configclass
class RslRlPpoActorCriticCfg:
    """Configuration for the PPO actor-critic networks."""

    class_name: str = "ActorCritic"
    init_noise_std: float = MISSING
    noise_std_type: Literal["scalar", "log"] = "scalar"
    actor_hidden_dims: list[int] = MISSING
    critic_hidden_dims: list[int] = MISSING
    activation: str = MISSING


@configclass
class RslRlPpoActorCriticRecurrentCfg(RslRlPpoActorCriticCfg):
    """Configuration for the PPO actor-critic networks with recurrent layers."""

    class_name: str = "ActorCriticRecurrent"
    rnn_type: str = MISSING
    rnn_hidden_dim: int = MISSING
    rnn_num_layers: int = MISSING


@configclass
class RslRlPpoAlgorithmCfg:
    """Configuration for the PPO algorithm."""

    class_name: str = "PPO"
    num_learning_epochs: int = MISSING
    num_mini_batches: int = MISSING
    learning_rate: float = MISSING
    schedule: str = MISSING
    gamma: float = MISSING
    lam: float = MISSING
    entropy_coef: float = MISSING
    desired_kl: float = MISSING
    max_grad_norm: float = MISSING
    value_loss_coef: float = MISSING
    use_clipped_value_loss: bool = MISSING
    clip_param: float = MISSING
    normalize_advantage_per_mini_batch: bool = False
    symmetry_cfg: RslRlSymmetryCfg | None = None
    rnd_cfg: RslRlRndCfg | None = None


@configclass
class RslRlOnPolicyRunnerCfg:
    """Configuration of the runner for on-policy algorithms."""

    seed: int = 42
    device: str = "cuda:0"
    num_steps_per_env: int = MISSING
    max_iterations: int = MISSING
    empirical_normalization: bool = MISSING
    policy: RslRlPpoActorCriticCfg = MISSING
    algorithm: RslRlPpoAlgorithmCfg = MISSING
    clip_actions: float | None = None
    save_interval: int = MISSING
    experiment_name: str = MISSING
    run_name: str = ""
    logger: Literal["tensorboard", "neptune", "wandb"] = "tensorboard"
    neptune_project: str = "isaaclab"
    wandb_project: str = "isaaclab"
    resume: bool = False
    load_run: str = ".*"
    load_checkpoint: str = "model_.*.pt"
