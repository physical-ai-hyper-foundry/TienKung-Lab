# TienKung-Lab: RL-based Locomotion Control System

**[简体中文](./README_zh.md)｜English**


## Overview

This framework is an RL-based locomotion control system suitable for full-sized humanoid robots, Walker TienKung. It integrates AMP-style rewards with periodic gait rewards, facilitating natural, stable, and efficient walking and running behaviors.

The codebase is built on IsaacLab, supports Sim2Sim transfer to MuJoCo, and features a modular architecture for seamless customization and extension. Additionally, it incorporates ray-casting-based sensors for enhanced perception, enabling precise environmental interaction and obstacle avoidance. The framework has also been successfully validated on the real Walker TienKung robot.



## Project Structure

```
	TienKung-Lab/
	├── legged_lab/              # Core motion control framework
	│   ├── scripts/             # Executable scripts
	│   ├── envs/                # Environment definitions
	│   ├── mdp/                 # Reward functions
	│   ├── sensors/             # Sensor modules
	│   ├── terrains/            # Terrain generation
	│   ├── assets/              # Robot models
	│   └── utils/               # Utility functions
	│
	├── rsl_rl/                  # Reinforcement learning library
	│   ├── algorithms/          # PPO/AMP-PPO algorithms
	│   ├── modules/             # Neural network modules
	│   ├── runners/             # Training runners
	│   ├── storage/             # Data storage
	│   └── utils/               # Utility functions
	│
	├── Exported_policy/         # Pre-trained policies
	├── docs/                    # Documentation
	└── setup.py                 # Installation setup
```



## Installation

TienKung-Lab targets **Isaac Sim 6.0.1 + Isaac Lab 3.0.0-beta2.patch1** (Python 3.12, PyTorch 2.10 / CUDA 12.8,
Blackwell GPUs supported). The 4.5.0 / 2.1.0 combination the project started on no longer works with this code;
see `docs/decisions/2026-09-15-adr-001-move-to-isaac-sim-6-isaac-lab-3.md` for why.

- Install Isaac Lab 3.0 by following the [installation guide](https://isaac-sim.github.io/IsaacLab/main/source/setup/installation/index.html).
  This repository was migrated against the `v3.0.0-beta2.patch1` release, published on the index as `3.0.0b2.post1`:

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install "isaacsim[all,extscache]==6.0.1.0" --extra-index-url https://pypi.nvidia.com --index-strategy unsafe-best-match --prerelease=allow
uv pip install -U torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install "isaaclab[isaacsim,all]==3.0.0b2.post1" --extra-index-url https://pypi.nvidia.com --index-strategy unsafe-best-match --prerelease=allow
```

- Clone this repository separately from the Isaac Lab installation (i.e. outside the `IsaacLab` directory)

- Using the python interpreter that has Isaac Lab installed, install the library

```bash
cd TienKung-Lab
pip install -e .
```

  On Linux, `pynput` (used by `sim2sim.py`) pulls in `evdev`, which is built from source and needs a C compiler.
  Either install `build-essential` first, or install without dependencies and add the rest by hand:

```bash
pip install -e . --no-deps
pip install "mujoco==3.3.2" mujoco-python-viewer matplotlib
pip install --no-deps pynput python-xlib six
```

- Install the bundled rsl-rl library **last**. Isaac Lab's `rsl-rl` extra pulls in `rsl-rl-lib` 5.x, which this
  repository's AMP runner is not written against; the editable install below must shadow it.

```bash
cd TienKung-Lab/rsl_rl
pip install -e .
```

- Verify that the extension is correctly installed by running the following command (`--headless` is deprecated
  in Isaac Lab 3.0; omit `--viz` for headless or pass `--viz kit` for a viewport):

```bash
python legged_lab/scripts/train.py --task=walk  --logger=tensorboard --num_envs=64
```

### Browser streaming of a training run

Isaac Sim 6.0 streams over WebRTC to a browser viewer that is built from the
[Isaac Sim repository](https://github.com/isaac-sim/IsaacSim) (`tools/docker/web-viewer/Dockerfile`, Ubuntu hosts
only, no NGC login needed). Build it once on the training machine with that machine's LAN IP baked in, and run it
on port 8210:

```bash
docker build --network host \
    --build-arg ISAACSIM_HOST=<training-machine-ip> \
    --build-arg ISAACSIM_SIGNAL_PORT=49100 --build-arg ISAACSIM_STREAM_PORT=47998 \
    -t isaacsim-web-viewer:6.0 <path-to-IsaacSim>/tools/docker/web-viewer
# The stock viewer calls crypto.randomUUID, which browsers only expose on HTTPS/localhost origins; when the
# page is opened as http://<ip>:8210 the stream dies with "crypto.randomUUID is not a function". This derived
# image injects a polyfill (tools/web-viewer/).
docker build -f tools/web-viewer/Dockerfile.polyfill -t isaacsim-web-viewer:6.0-lan tools/web-viewer
docker run -d --name isaacsim-web-viewer --network host --restart unless-stopped isaacsim-web-viewer:6.0-lan
```

Launch training with livestreaming bound to the same IP, then open `http://<training-machine-ip>:8210` in a
Chromium browser:

```bash
PUBLIC_IP=<training-machine-ip> python legged_lab/scripts/train.py --task=x2_walk --livestream 1
```

`--livestream 1` forces headless mode, enables `omni.kit.livestream.app` and listens on TCP 49100 (signalling) and
UDP 47998 (media); training keeps running whether or not a viewer is attached. `--livestream 2` binds to
127.0.0.1 only, for a viewer on the same machine. One client can attach to an Isaac Sim instance at a time.

## Usage

### Motion Retargeting

This section uses [GMR](https://github.com/YanjieZe/GMR) for motion retargeting, Walker Tienkung currently supports motion retargeting only for SMPLX types (AMASS, OMOMO).

**1. Prepare the dataset and Motion retargeting with [GMR](https://github.com/YanjieZe/GMR).**

```bash
python scripts/smplx_to_robot.py --smplx_file <path_to_smplx_data> --robot tienkung  --save_path <path_to_save_robot_data.pkl>
```

**2. Data Processing and Data Saving.**

The dataset consists of two parts with distinct functions and formats, requiring conversion in two steps.

- **`motion_visualization/`**  
  Used for motion playback with `play_amp_animation.py` to check motion correctness and quality.  
  Data fields:  [root_pos, root_rot, dof_pos, root_lin_vel, root_ang_vel, dof_vel]

- **`motion_amp_expert/`**  
  Used during training as expert reference data for AMP.  
  Data fields:  [dof_pos, dof_vel, end-effector pos]

- **Step 1: Data Processing and Visualization Data Saving.**

```bash
python legged_lab/scripts/gmr_data_conversion.py --input_pkl <path_to_save_robot_data.pkl> --output_txt legged_lab/envs/tienkung/datasets/motion_visualization/motion.txt
```

**Note**: Before starting step 2, set the `amp_motion_files_display` path in the config to the file generated in step 1.

- **Step 2: Motion Visualization and Expert Data Saving.**

```bash
python legged_lab/scripts/play_amp_animation.py --task=walk --num_envs=1 --save_path legged_lab/envs/tienkung/datasets/motion_amp_expert/motion.txt --fps 30.0
```

**Note**: After step 2, set the `amp_motion_files` path in the config to the file generated in step 2.

### Visualize motion

Visualize the motion by updating the simulation with data from tienkung/datasets/motion_visualization.

```bash
python legged_lab/scripts/play_amp_animation.py --task=walk --num_envs=1
python legged_lab/scripts/play_amp_animation.py --task=run --num_envs=1
```

### Visualize motion with sensors

Visualize the motion with sensors by updating the simulation with data from tienkung/datasets/motion_visualization.

```bash
python legged_lab/scripts/play_amp_animation.py --task=walk_with_sensor --num_envs=1
python legged_lab/scripts/play_amp_animation.py --task=run_with_sensor --num_envs=1
```

### Train

Train the policy using AMP expert data from tienkung/datasets/motion_amp_expert.

```bash
python legged_lab/scripts/train.py --task=walk --headless --logger=tensorboard --num_envs=4096
python legged_lab/scripts/train.py --task=run --headless --logger=tensorboard --num_envs=4096
```

### Play

Run the trained policy.

```bash
python legged_lab/scripts/play.py --task=walk --num_envs=1
python legged_lab/scripts/play.py --task=run --num_envs=1
```

### Sim2Sim(MuJoCo)

Evaluate the trained policy in MuJoCo to perform cross-simulation validation.

Exported_policy/ contains pretrained policies provided by the project. When using the play script, trained policy is exported automatically and saved to path like logs/run/[timestamp]/exported/policy.pt.

```bash
python legged_lab/scripts/sim2sim.py --task walk --policy Exported_policy/walk.pt --duration 100
```

### Sim2Real

The results of the TienKung-Lab have been successfully verified on the real **TienKung** robot.

For deployment details, refer to the repository [here](https://github.com/UBTECH-Robot/Deploy_Tienkung).

**Safety Notice:** Testing on real robot is risky. RL policy may cause unexpected or violent motions, so ensure accident insurance is in place and the emergency stop works.




## Code Formatting

We have a pre-commit template to automatically format your code.
To install pre-commit:

```bash
pip install pre-commit
```

Then you can run pre-commit with:

```bash
pre-commit run --all-files
```



## Troubleshooting

### Pylance Missing Indexing of Extensions

In some VsCode versions, the indexing of part of the extensions is missing. In this case, add the path to your extension in `.vscode/settings.json` under the key `"python.analysis.extraPaths"`.

```json
{
    "python.analysis.extraPaths": [
        "${workspaceFolder}/legged_lab",
        "<path-to-IsaacLab>/source/isaaclab_tasks",
        "<path-to-IsaacLab>/source/isaaclab_mimic",
        "<path-to-IsaacLab>/source/extensions",
        "<path-to-IsaacLab>/source/isaaclab_assets",
        "<path-to-IsaacLab>/source/isaaclab_rl",
        "<path-to-IsaacLab>/source/isaaclab",
    ]
}
```

## Acknowledgement

**Special thanks to the Beijing Humanoid Robot Innovation Center for their invaluable support and guidance.**

**Project Link:** [TienKung-Lab](https://github.com/Open-X-Humanoid/TienKung-Lab)



