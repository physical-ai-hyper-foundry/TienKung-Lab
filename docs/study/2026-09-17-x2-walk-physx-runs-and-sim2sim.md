# AgiBot X2 보행 학습 결과 정리: PhysX 두 런과 MuJoCo sim2sim (2026-09-17)

브랜치 `feat/isaaclab-3-migration`, Isaac Sim 6.0.1 + Isaac Lab 3.0.0b2.post1, 개발 PC RTX 5070 Ti 16 GB.
태스크 `x2_walk`(AMP 꺼짐, 20 DoF, GRAVEL 지형 생성, 4096 env, PPO). 평가 스크립트는 레포의
`smoke_test_x2_mujoco.py`(순수 MuJoCo 3.8.1, CPU, 스크립트 안에서 PD 폐루프, 10 s, gait 0.68 s).

## 1. 학습 런

| 런 | 물리 | 기간 | iteration | 마지막 mean reward / ep len | 비고 |
|---|---|---|---|---|---|
| `2026-09-15_13-06-27` (run 1) | PhysX | 09-15 13:06 → 09-16 11:45 | 50,000 완주 | 60.7 / 1000 | 1.6~2.3 s/iter |
| `2026-09-16_15-17-02_physx-run2` (run 2) | PhysX | 09-16 15:17 → 09-17 07:30 중단 | 40,042 | 63.0 / 1000 | `--physics newton` 으로 시작했으나 분기 미적용(§4) |
| `2026-09-17_08-49-00_newton` | Newton (MuJoCo Warp) | 09-17 08:50 → | 진행 중 | | 1.94 s/iter, VRAM 5.4 GB |

두 PhysX 런은 seed 42 로 같지만 GPU 비결정성 때문에 서로 다른 정책이다. reward 곡선은 둘 다 약 6,000 iteration
에서 50 을 넘고 15,000 이후 평탄하다.

## 2. TensorBoard 의 한 칸짜리 reward 급락

`Train/mean_reward` 가 60 근처에서 -100 ~ -1,400 으로 한 iteration 만 떨어졌다가 바로 복귀하는 스파이크가 run 2
에서 40,000 iteration 동안 약 60번 있었다. 로그를 항목별로 뜯으면

- 급락 iteration 에서 `Episode_Reward/lin_vel_z_l2` 만 평소 -0.03 → -68 ~ -76 으로 폭발, 다른 항목은 정상.
- 평균 에피소드 길이는 990~1000 그대로, 행동 노이즈 std 도 불변.
- rsl_rl 의 mean_reward 는 최근 100개 종료 에피소드의 누적 보상 평균(deque)이라 -50,000 짜리 에피소드 하나가
  평균을 -500 으로 끌어내린 뒤 다음 iteration 에 밀려난다.

즉 정책 붕괴가 아니라 몇 env 의 몸통이 한 스텝 수직으로 튕기는 접촉 솔버 "팝" 이다(지형 메시 모서리). run 1
(PhysX) 에도 같은 스파이크가 있어 엔진 공통 현상이며 학습에는 영향이 없다.

## 3. MuJoCo sim2sim 평가

### run 1 최종(iteration 49,999), 명령 vx 별

| vx | 낙상 | 이동 x / y | 평균 vx |
|---|---|---|---|
| 0.0 | 없음 | -0.10 / -1.00 m | -0.01 |
| 0.3 | 2.8 s | +1.68 / +0.59 m | 0.17 |
| 0.5 | 5.2 s | +2.67 / -1.16 m | 0.27 |
| 1.0 | 없음 | +7.09 / -7.48 m | 0.71 |

### run 2 체크포인트별, 명령 vx 0 / 0.5

| iteration | vx 0: 낙상 | vx 0.5: 낙상 | vx 0.5: 이동 x / y | 평균 vx |
|---|---|---|---|---|
| 2,100 | - | 없음 | +3.85 / +0.10 m | 0.39 |
| 5,000 | 없음 | 없음 | +4.31 / +0.17 m | 0.43 |
| 10,000 | 없음 | 1.8 s | +1.42 / +1.15 m | 0.14 |
| 20,000 | 3.8 s | 4.9 s | +4.24 / +1.48 m | 0.42 |
| 30,000 | 3.3 s | 6.5 s | +0.38 / -0.98 m | 0.04 |
| 40,000 | 8.5 s | 1.9 s | -0.00 / +0.97 m | 0.00 |

같은 체크포인트를 Isaac Sim(PhysX) 에서 돌리면 40,000 도 넘어지지 않고 직진한다(10 s, x +3.8 m).

읽는 법:

- sim2sim 갭은 실재한다. Isaac 에서 완벽한 정책이 MuJoCo 에서는 저속에서 넘어지고 옆으로 흐른다(헤딩 명령을
  끄고 평가하므로 yaw 보정도 없다).
- **학습이 진행될수록 MuJoCo 전이가 나빠진다.** 5,000 iteration 까지는 두 명령 모두 안 넘어지지만 10,000 부터
  무너진다. 보상이 평탄해진 뒤의 학습은 PhysX 접촉 특성에 맞춘 미세 조정이라 다른 엔진에서는 손해다.
- 따라서 "마지막 체크포인트 = 최선" 이 아니다. 배포용 체크포인트는 목표 시뮬레이터(또는 실기)에서 평가해 골라야
  하고, 제품의 모델 테스터(MuJoCo)가 이 선택을 맡는 자리다.

## 4. `--physics newton` 이 적용되지 않았던 이유

`SimCfg.physics_backend` 분기를 `BaseEnv.__init__` 에 넣었지만 `x2_walk` 를 포함한 모든 태스크는 `TienKungEnv`
로 등록돼 있고, 그 클래스는 `SimulationCfg(physics=PhysxCfg(...))` 를 자체적으로 만든다. 64 env 스모크가
통과해서 바뀐 줄 알았으나 PhysX 로도 통과하는 테스트였다. `env.sim.physics_manager.__name__` 을 찍는 확인
스크립트로 잡았고, 선택 로직을 `legged_lab/utils/env_utils/physics.py:make_physics_cfg()` 로 옮겨 두 클래스가
공유하게 했다. 확인 결과 `NewtonMJWarpManager` / `isaaclab_newton` Articulation·ContactSensor 로 바뀐다.

추가로 드러난 것: Newton 은 `mujoco~=3.8.0` 을 요구하고(3.3.2 에서 import 실패), 관절 순서가 PhysX(BFS) 와
Newton(DFS) 에서 다르다. 자세한 내용은 `docs/plan/2026-09-15-isaaclab-3-migration.md` §7.

## 5. 영상

`outputs/compare/`(git 무시). 모두 명령 vx 0.5 m/s, 10 s, 1280×720, 25 fps, 추적 카메라.

| 파일 | 내용 |
|---|---|
| `x2_walk_physx_run1_vs_run2_2x2.mp4` | 2×2: 위 Isaac Sim(PhysX) run 1 / run 2, 아래 MuJoCo run 1 / run 2 |
| `isaac_physx_49999_vx0.5.mp4`, `mujoco_physx_49999_vx0.5.mp4` | run 1 최종 |
| `isaac_physx-run2_40000_vx0.5.mp4`, `mujoco_physx-run2_40000_vx0.5.mp4` | run 2 40,000 |
| `isaac_physx-run2_5000_vx0.5.mp4`, `mujoco_physx-run2_5000_vx0.5.mp4` | run 2 5,000 (MuJoCo 에서 잘 걷는 체크포인트) |

만드는 법(개발 PC): `export_policy.py` 로 체크포인트 내보내기 → `record_play.py`(Isaac) 와
`smoke_test_x2_mujoco.py --render`(MuJoCo) → 맥에서 ffmpeg `xstack` 으로 합성. 명령은 README "Physics backend" 와
"Sim2Sim" 절 참고.

## 6. 남은 일

- 진짜 Newton 런이 끝나면(또는 10,000 iteration 쯤 중단) §3 표와 §5 영상을 Newton 정책으로 다시 채워 PhysX 와
  비교한다. MuJoCo 평가 시 `--joint-order newton`.
- MuJoCo 평가에 헤딩 보정(ang_vel_z 명령)을 넣어 y 드리프트를 분리한다.
- `lin_vel_z_l2` 스파이크는 학습에 무해하지만 로그를 깨끗이 하려면 항 클리핑을 고려한다.
