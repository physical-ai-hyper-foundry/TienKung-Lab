# Copyright (c) 2022-2025, The Isaac Lab Project Developers.
# All rights reserved.
#
# Copyright (c) 2025-2026, The TienKung-Lab Project Developers.
# All rights reserved.
# Modifications are licensed under the BSD-3-Clause license.
#
# This file contains code derived from the Isaac Lab and Legged Lab Projects,
# with additional modifications by the TienKung-Lab Project,
# and is distributed under the BSD-3-Clause license.

"""Configuration for the AgiBot X2 Ultra humanoid robot.

The articulation is the 20-DoF locomotion variant produced by
``legged_lab/scripts/prepare_agibot_x2.py`` (waist, neck and wrist joints held
fixed), which matches TienKung2-lite's 12-leg + 8-arm joint budget.

Robot description: https://github.com/AgibotTech/agibot_x2_urdf (Mulan PSL v2)
"""

import isaaclab.sim as sim_utils
from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.assets.articulation import ArticulationCfg

from legged_lab.assets import ISAAC_ASSET_DIR

AGIBOT_X2_CFG = ArticulationCfg(
    spawn=sim_utils.UsdFileCfg(
        usd_path=f"{ISAAC_ASSET_DIR}/agibot_x2/usd/x2_ultra_locked20/x2_ultra_locked20_flat.usd",
        activate_contact_sensors=True,
        rigid_props=sim_utils.RigidBodyPropertiesCfg(
            disable_gravity=False,
            retain_accelerations=False,
            linear_damping=0.0,
            angular_damping=0.0,
            max_linear_velocity=1000.0,
            max_angular_velocity=1000.0,
            max_depenetration_velocity=1.0,
        ),
        articulation_props=sim_utils.ArticulationRootPropertiesCfg(
            enabled_self_collisions=False, solver_position_iteration_count=8, solver_velocity_iteration_count=4
        ),
    ),
    init_state=ArticulationCfg.InitialStateCfg(
        # Forward kinematics puts the pelvis at 0.601 m in this pose; the extra
        # margin mirrors TienKung's 1.0 m spawn over its own 0.828 m pose height.
        pos=(0.0, 0.0, 0.73),
        joint_pos={
            # Hip roll is asymmetric too ([-0.24, 2.91] rad on the left), leaving only
            # 0.079 rad of adduction inside the soft limit at this neutral pose.
            "left_hip_roll_joint": 0.0,
            "left_hip_pitch_joint": -0.5,
            "left_hip_yaw_joint": 0.0,
            "left_knee_joint": 1.0,
            "left_ankle_pitch_joint": -0.5,
            "left_ankle_roll_joint": 0.0,
            "right_hip_roll_joint": 0.0,
            "right_hip_pitch_joint": -0.5,
            "right_hip_yaw_joint": 0.0,
            "right_knee_joint": 1.0,
            "right_ankle_pitch_joint": -0.5,
            "right_ankle_roll_joint": 0.0,
            "left_shoulder_pitch_joint": 0.0,
            # X2's shoulder roll range is asymmetric ([-0.06, 2.98] rad on the left),
            # so the soft limit starts at 0.092 rad -- the arms cannot hang fully adducted.
            "left_shoulder_roll_joint": 0.15,
            "left_shoulder_yaw_joint": 0.0,
            "left_elbow_joint": -0.3,
            "right_shoulder_pitch_joint": 0.0,
            "right_shoulder_roll_joint": -0.15,
            "right_shoulder_yaw_joint": 0.0,
            "right_elbow_joint": -0.3,
        },
        joint_vel={".*": 0.0},
    ),
    soft_joint_pos_limit_factor=0.9,
    actuators={
        # Gains reproduce TienKung's closed-loop joint dynamics on X2's inertia rather than
        # scaling by torque: omega_n is carried over per joint (kp = I_x2 * omega_n^2), damping
        # matches TienKung's ratio capped at zeta = 1.0, and kp is reduced where a 0.15 rad
        # step would saturate the motor. Effort/velocity limits and armature come from the
        # upstream URDF / MuJoCo description. The MuJoCo file's frictionloss (0.3 N*m) is
        # deliberately not carried over: Isaac Lab's ``friction`` is PhysX's unitless joint
        # friction coefficient, not a Coulomb torque, and the URDF declares no joint
        # friction -- so the joints stay frictionless like TienKung's.
        #
        # This matters most at the ankles and wrists: the vendor's uniform armature of
        # 0.03 kg*m^2 is 69-95% of their total inertia, and TienKung's model has no armature
        # at all. Torque-ratio scaling missed that and left the ankles ~8x too soft -- with
        # those gains the robot tips over in 1.5 s in MuJoCo, and with these it stands
        # indefinitely (legged_lab/scripts/smoke_test_x2_mujoco.py --policy none).
        "legs": ImplicitActuatorCfg(
            joint_names_expr=[
                ".*_hip_roll_joint",
                ".*_hip_pitch_joint",
                ".*_hip_yaw_joint",
                ".*_knee_joint",
            ],
            effort_limit_sim={
                ".*_hip_roll_joint": 120,
                ".*_hip_pitch_joint": 120,
                ".*_hip_yaw_joint": 120,
                ".*_knee_joint": 120,
            },
            velocity_limit_sim={
                ".*_hip_roll_joint": 11.94,
                ".*_hip_pitch_joint": 11.94,
                ".*_hip_yaw_joint": 11.94,
                ".*_knee_joint": 11.94,
            },
            stiffness={
                ".*_hip_roll_joint": 327,
                ".*_hip_pitch_joint": 468,
                ".*_hip_yaw_joint": 401,
                ".*_knee_joint": 536,
            },
            damping={
                ".*_hip_roll_joint": 4.7,
                ".*_hip_pitch_joint": 6.7,
                ".*_hip_yaw_joint": 4.0,
                ".*_knee_joint": 7.7,
            },
            armature=0.03,
        ),
        "feet": ImplicitActuatorCfg(
            joint_names_expr=[
                ".*_ankle_pitch_joint",
                ".*_ankle_roll_joint",
            ],
            effort_limit_sim={
                ".*_ankle_pitch_joint": 60,
                ".*_ankle_roll_joint": 36,
            },
            velocity_limit_sim={
                ".*_ankle_pitch_joint": 13.61,
                ".*_ankle_roll_joint": 14.66,
            },
            stiffness={
                ".*_ankle_pitch_joint": 172,
                ".*_ankle_roll_joint": 216,
            },
            damping={
                ".*_ankle_pitch_joint": 5.5,
                ".*_ankle_roll_joint": 5.4,
            },
            armature=0.03,
        ),
        "arms": ImplicitActuatorCfg(
            joint_names_expr=[
                ".*_shoulder_pitch_joint",
                ".*_shoulder_roll_joint",
                ".*_shoulder_yaw_joint",
                ".*_elbow_joint",
            ],
            effort_limit_sim={
                ".*_shoulder_pitch_joint": 60,
                ".*_shoulder_roll_joint": 60,
                ".*_shoulder_yaw_joint": 36,
                ".*_elbow_joint": 36,
            },
            velocity_limit_sim={
                ".*_shoulder_pitch_joint": 13.61,
                ".*_shoulder_roll_joint": 13.61,
                ".*_shoulder_yaw_joint": 14.66,
                ".*_elbow_joint": 14.66,
            },
            stiffness={
                ".*_shoulder_pitch_joint": 98,
                ".*_shoulder_roll_joint": 33,
                ".*_shoulder_yaw_joint": 94,
                ".*_elbow_joint": 29,
            },
            damping={
                ".*_shoulder_pitch_joint": 4.9,
                ".*_shoulder_roll_joint": 2.5,
                ".*_shoulder_yaw_joint": 3.7,
                ".*_elbow_joint": 2.9,
            },
            armature=0.03,
        ),
    },
)
