# AgiBot X2 포팅 계획 및 진행 상황

TienKung-Lab 의 AMP 기반 보행 프레임워크를 AgiBot X2 Ultra 로 옮기는 작업.
브랜치 `feat/agibot-x2-port`, 태스크명 `x2_walk`. 2026-09-15 기준.

## 1. 전략

X2 Ultra(v1.4.0)는 31 DOF(다리 12 + 팔 14 + 허리 3 + 목 2)다. 허리 3 + 목 2 + 손목 6 = 11개를
URDF 에서 `fixed` 로 잠그면 **다리 12 + 팔 8 = 20 DOF** 로 TienKung2-lite 와 동형이 되어
`rsl_rl/utils/motion_loader.py`, `min_normalized_std`, `sim2sim.py` 의 20-DOF 가정을 그대로
재사용할 수 있다. 관절 축 규약도 20개 전부 TienKung 과 동일하고 병렬 링크가 없다.

로봇을 시뮬레이터에 맞추는 것이 아니라 설정이 로봇 이름을 부르게 한다. Isaac Lab API 는 전부
이름 기반이라 관절명을 바꾼 곳은 없다.

## 2. 학습 입력 구조 (레포 분석)

| 입력 | 위치 | 비고 |
|---|---|---|
| 로봇 에셋 3벌 (URDF / USD / MJCF) | `legged_lab/assets/<robot>/` | Isaac 은 USD 를 읽음. URDF 는 변환 원본, MJCF 는 sim2sim |
| 액추에이터 모델 + default pose | `<robot>.py` (`ArticulationCfg`) | URDF 에 없는 정보. PD 게인, effort/velocity limit, armature |
| AMP 모션 데이터 2종 (52열) | `envs/<robot>/datasets/` | visualization / amp_expert. GMR 리타게팅 산출물 |
| 보행 위상 클럭 (`GaitCfg`) | `walk_cfg.py` | 보상이자 관측. walk/run 차이는 이 5개 숫자와 AMP 데이터뿐 |
| 관측 75×10 = 750, 액션 20 | `tienkung_env.py` | ang_vel, gravity, cmd, q, q̇, action, sin/cos φ, ratio |
| 커맨드 / 지형 / DR / 종료 / 하이퍼파라미터 | `walk_cfg.py` | |
| 로봇 고유 이름·상수 | `RobotCfg` | 이번 작업으로 설정화 (관절명 24개, 보폭, hand offset) |

## 3. X2 vs TienKung 실측 (URDF 직접 파싱)

| | TienKung2-lite | X2 Ultra v1.4.0 |
|---|---|---|
| 구동 관절 | 20 | 31 → 20 (잠금) |
| 총 질량 | 61.76 kg | 44.80 kg |
| pelvis → ankle_roll | 0.932 m | 0.602 m |
| 좌우 발 y 간격 | 0.299 m (`feet_y_distance` 상수의 출처) | 0.274 m |
| default pose 골반 높이 | 0.828 m (AMP 실측 0.822 m 와 일치) | 0.601 m |
| 무릎 / 고관절 pitch 토크 | 300 N·m | 120 N·m (토크밀도 55%) |
| merge 후 강체 수 | 21 | 21 |
| merge 후 pelvis 질량 | — | 18.52 kg |

에셋 출처: [AgibotTech/agibot_x2_urdf](https://github.com/AgibotTech/agibot_x2_urdf) (Mulan PSL v2).
URDF, simple_collision URDF, MJCF, scene.xml 포함. 공식 RL 학습 코드는 없음 (X1 만 Isaac Gym 기반).

## 4. 재조정 상수

| 상수 | TienKung | X2 | 근거 |
|---|---|---|---|
| `feet_y_distance_target` | 0.299 | 0.274 | URDF 실측 |
| `gait_cycle` (walk) | 0.85 s | 0.68 s | √(0.602 / 0.932) 다리길이 스케일 |
| `feet_force` threshold / max | 500 / 400 N | 360 / 290 N | 질량비 0.73 |
| `add_base_mass` | ±5.0 kg | ±3.5 kg | merge 후 pelvis 18.52 kg |
| `init_state.pos` z | 1.0 m | 0.73 m | FK 0.601 m + TienKung 과 같은 비례 여유 |
| `hand_local_offset` | (0, 0, −0.3) | (−0.014, 0, −0.203) | elbow → wrist_roll 실측 |
| `shoulder_roll` 기본 | ±0.1 | ±0.15 | X2 소프트리밋 하한 0.092 rad |

## 5. PD 게인 산출

처음 쓴 effort-limit 비례 스케일은 틀렸다. X2 MJCF 의 `armature=0.03 kg·m²` 가 발목 roll 관성의
89 %, 어깨 yaw 의 95 % 를 차지하는데 TienKung 모델에는 armature 항이 없어, 원위 관절이 8~10배
언더게인이 됐다.

채택한 방법: TienKung 관절별 폐루프 고유진동수 ω_n 을 관성행렬 대각항에서 측정해 X2 관성에 이식.

```
kp = I_x2 · ω_n(TienKung)²
kd = 2 · min(ζ_TienKung, 1.0) · I_x2 · ω_n
0.15 rad 스텝에서 토크 한계 90 % 초과 시 kp 축소 (ankle_roll 해당)
```

ζ 상한을 둔 이유: TienKung 발목은 링크 관성이 거의 0 이라 ζ 가 2.6~3.7 로 비물리적.

| 관절 | 기존 kp/kd | 신규 kp/kd |
|---|---|---|
| hip_roll | 450 / 6.5 | 327 / 4.7 |
| hip_pitch | 280 / 4.0 | 468 / 6.7 |
| hip_yaw | 330 / 3.3 | 401 / 4.0 |
| knee | 280 / 4.0 | 536 / 7.7 |
| ankle_pitch | 30 / 2.5 | 172 / 5.5 |
| ankle_roll | 20 / 1.7 | 216 / 5.4 |
| shoulder_pitch | 70 / 3.4 | 98 / 4.9 |
| shoulder_roll | 23 / 1.7 | 33 / 2.5 |
| shoulder_yaw | 7 / 0.7 | 94 / 3.7 |
| elbow | 7 / 0.7 | 29 / 2.9 |

MuJoCo 검증: 기존 게인은 자세 유지만으로 1.52 초에 넘어짐, 신규 게인은 15 초 안정.

유보: armature 0.03 이 전 관절 균일이라 벤더 대략값일 가능성이 크다. 실기 스펙 확보 시 관절별로
넣고 발목 게인을 재산출한다.

## 6. 완료 커밋

| 커밋 | 내용 |
|---|---|
| `0dfdc14` feat | `prepare_agibot_x2.py`(fetch + 20DOF 잠금 URDF), `AGIBOT_X2_CFG`, `RobotCfg` 이름 설정화, `x2_walk` 태스크 |
| `10ddec3` test | `smoke_test_x2_mujoco.py` — 맥에서 MuJoCo 로 X2 구동, 렌더링 |
| `5e4ac0b` fix | PD 게인 관성 기준 재산출 |
| `a30014f` docs | 이 계획·상태 문서 |
| `60c7181` fix | `friction=0.3` 제거 — Isaac Lab `friction` 은 PhysX 무차원 계수라 MJCF `frictionloss`(N·m)와 불일치 |

`RobotCfg` 의 기본값은 기존 하드코딩과 바이트 단위로 동일해 TienKung 태스크 동작은 불변 (회귀 검증).

## 7. 검증 상태

**검증됨 (macOS, 정적 + MuJoCo)**
- 문법, 설정의 이름·정규식 40개가 X2 URDF 와 매칭, actuator 커버리지 20/20 중복 없음
- default pose 20개 전부 소프트리밋 내부 (hip_roll 여유 0.079, shoulder_roll 0.059 rad 로 빠듯)
- MJCF 로드, sensordata 레이아웃 (jointpos@16, jointvel@47, 총 78)
- 관측 구성 정확: 같은 코드로 TienKung + `walk.pt` 가 6 초에 3.15 m 보행 (명령 0.5 → 실측 0.53 m/s)
- 신규 PD 게인으로 기립 유지
- Isaac Lab 2.1.0 소스 대조: `ActuatorBaseCfg` 에 `armature`(관절 관성에 직접 가산, kg·m²) 와
  `friction` 필드 존재. 단 `friction` 은 PhysX 의 **무차원 관절 마찰 계수**(F_resist ≤ μ·F_spatial)
  라 MJCF `frictionloss=0.3` N·m 를 그대로 옮긴 것은 의미 불일치 → X2 cfg 에서 제거. X2 URDF 에
  `<dynamics>` 가 없어 USD 관절 마찰은 0 이며, TienKung URDF(`friction="0.0"`)와 같은 조건이 된다
- `convert_urdf.py` 플래그(`--merge-joints --joint-stiffness --joint-damping --joint-target-type none`)
  가 v2.1.0 스크립트와 일치
- `prepare_agibot_x2.py` 재실행 결과가 커밋된 `x2_ultra_locked20.urdf` 와 바이트 일치 (멱등)

**검증됨 (개발 PC, Isaac Lab 3.0.0-beta2.patch1 + Isaac Sim 6.0.1, 2026-09-15)**
- USD 변환: 강체 21, 관절 20. 6.0 임포터의 중첩 계층 문제와 `flatten_usd.py` 조치는
  `docs/plan/2026-09-15-isaaclab-3-migration.md` 5절 참조
- `robot.joint_names` 실측 = BFS 예측. TienKung 과 인덱스 `(0,1)↔(4,5)`(hip_roll↔hip_pitch) swap 만 다름.
  `merge_fixed_joints` 는 예측대로 11개 고정 관절을 pelvis 등에 병합
- `SceneEntityCfg` 정규식 해석, contact sensor(21 body), 보상 26항 모두 초기화·실행됨.
  `x2_walk` 64 env 3 iter 학습 루프 정상

관절 순서는 3단계 학습의 선결 조건이 아니다. 관측·액션이 같은 Isaac 순서로 일관되고 보상·AMP 관측은
`find_joints(preserve_order=True)` 로 이름 해석하므로 학습은 순서를 몰라도 된다. 순서는 sim2sim /
실기 배포 / Isaac Gym 코드 이식(DFS 순서) 때만 필요하다.

## 8. 다음 단계

```
[맥 가능]   B. X2 sim2sim 완성 — smoke test 재사용, 토크 모터 PD + 센서 인덱스 16/47   ← 다음
            C. AMP expert 데이터 생성에서 Isaac 의존 제거 (play_amp_animation 의 FK 를 MuJoCo 로)

[GPU 필요]  x2_walk 학습 (AMP off, amp_task_reward_lerp=1.0) → 평지 보행 확인이 실현 가능성 판정선   ← 다음
            dof_pos_limits 보상 모니터링
            (USD 변환·joint_names 기록은 2026-09-15 완료)

[사용자]    SMPL-X 바디모델 + AMASS 등록/다운로드
            GMR params.py 4곳 + ik_configs/smplx_to_x2.json 작성·튜닝
            X2 AMP 데이터 생성 → amp_motion_files 교체, amp_task_reward_lerp=0.7 로 AMP on

[후순위]    run 태스크 — 무릎 토크밀도 55 % 라 재튜닝 필수
            waist_yaw 해제 (LOCKED_JOINTS 에서 제거 + 20 하드코딩 3곳 수정)
            sim2real 스택 — Deploy_Tienkung 재사용 불가
```

## 9. 환경 제약

- 개발 머신은 macOS arm64. Isaac Lab 빌드가 없어 학습·USD 변환 불가. `mujoco==3.3.2` 설치됨.
- GMR 은 CPU 로 돌지만 SMPL-X / AMASS 가 계정 등록 필요.
- `walk.pt` 는 X2 에서 750→20 차원이 맞아 로드되지만 로봇 불일치로 1 초 내 넘어짐. 배관 점검
  용도로만 유효.
