# Copyright (c) 2025-2026, The TienKung-Lab Project Developers.
# All rights reserved.
# Distributed under the BSD-3-Clause license.

"""Interactive MuJoCo sim2sim for AgiBot X2 -- live viewer, tracking camera, keyboard commands.

Reuses the observation / PD pipeline of smoke_test_x2_mujoco.py.

    python legged_lab/scripts/sim2sim_x2.py --policy logs/x2_walk/<run>/exported/policy_15100.pt

Heading hold (default, matches training's heading_command=True): the yaw-rate command is
clip(0.5 * wrap(heading_target - heading), +-1.57), as in Isaac Lab's UniformVelocityCommand.

Numpad: 8/2 vx +-0.2, 4/6 vy +-0.2, 7/9 turn target heading +-15 deg (yaw rate +-0.2 with
--no-heading), 5 zero command and hold current heading, 0 reset robot.
"""

import argparse
import os
import sys
import time

import mujoco
import mujoco.viewer
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from smoke_test_x2_mujoco import DECIMATION, DT, X2Runner  # noqa: E402

# GLFW key codes for the numpad
KP_0, KP_2, KP_4, KP_5, KP_6, KP_7, KP_8, KP_9 = 320, 322, 324, 325, 326, 327, 328, 329
STEP = 0.2
HEADING_STEP = np.radians(15.0)
# Must match commands in the x2_walk env config.
HEADING_STIFFNESS = 0.5
ANG_VEL_Z_RANGE = (-1.57, 1.57)


def wrap_to_pi(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def heading(runner):
    """World yaw of the pelvis x-axis, as Isaac Lab's heading_w."""
    fwd = runner.data.xmat[runner.pelvis_bid].reshape(3, 3)[:, 0]
    return float(np.arctan2(fwd[1], fwd[0]))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--policy", type=str, required=True, help="TorchScript policy")
    p.add_argument("--command", type=float, nargs=3, default=[0.0, 0.0, 0.0], help="initial lin_vel_x lin_vel_y ang_vel_z")
    p.add_argument("--gait-cycle", type=float, default=0.68, help="X2 walk_cfg uses 0.68 s")
    p.add_argument("--no-heading", action="store_true", help="drive yaw rate directly instead of holding a heading")
    args = p.parse_args()

    runner = X2Runner(args.policy, args.gait_cycle, args.command)
    hold = not args.no_heading
    state = {"reset": False, "target": heading(runner)}

    def report():
        c = runner.command
        if hold:
            print(f"command vx={c[0]:+.1f} vy={c[1]:+.1f} heading_target={np.degrees(state['target']):+.0f} deg", flush=True)
        else:
            print(f"command vx={c[0]:+.1f} vy={c[1]:+.1f} yaw={c[2]:+.1f}", flush=True)

    def on_key(key):
        c = runner.command
        if key == KP_8:
            c[0] += STEP
        elif key == KP_2:
            c[0] -= STEP
        elif key == KP_4:
            c[1] += STEP
        elif key == KP_6:
            c[1] -= STEP
        elif key in (KP_7, KP_9):
            sign = 1.0 if key == KP_7 else -1.0
            if hold:
                state["target"] = wrap_to_pi(state["target"] + sign * HEADING_STEP)
            else:
                c[2] += sign * STEP
        elif key == KP_5:
            c[:] = 0.0
            state["target"] = heading(runner)
        elif key == KP_0:
            state["reset"] = True
            return
        else:
            return
        np.clip(c, -1.0, 1.0, out=c)
        report()

    control_dt = DT * DECIMATION
    with mujoco.viewer.launch_passive(runner.model, runner.data, key_callback=on_key) as viewer:
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_TRACKING
        viewer.cam.trackbodyid = runner.pelvis_bid
        viewer.cam.distance = 3.0
        viewer.cam.elevation = -15.0
        viewer.cam.azimuth = 135.0
        print(f"policy={args.policy}  gait_cycle={args.gait_cycle}s  heading_hold={hold}", flush=True)
        report()

        last_status = time.time()
        while viewer.is_running():
            start = time.time()
            if state["reset"]:
                state["reset"] = False
                runner._reset()
                state["target"] = heading(runner)
                print("reset", flush=True)
            with viewer.lock():
                if hold:
                    err = wrap_to_pi(state["target"] - heading(runner))
                    runner.command[2] = np.clip(HEADING_STIFFNESS * err, *ANG_VEL_Z_RANGE)
                runner.step()
            viewer.sync()
            if hold and start - last_status > 2.0:
                last_status = start
                print(
                    f"  heading={np.degrees(heading(runner)):+6.1f} deg  error={np.degrees(err):+5.1f} deg"
                    f"  yaw_cmd={runner.command[2]:+.2f}  pos=({runner.data.qpos[0]:+.2f}, {runner.data.qpos[1]:+.2f})",
                    flush=True,
                )
            sleep = control_dt - (time.time() - start)
            if sleep > 0:
                time.sleep(sleep)


if __name__ == "__main__":
    main()
