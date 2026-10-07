# Newton 백엔드 관절 드라이브 수정 검증 (개발 PC 에서 실행)

작성 2026-09-17. **2026-09-18 검증 완료** — 결과는 맨 아래 "진행 결과" 절. 아래 "실행 프롬프트" 는 실행 당시 계획이며, 4번(USD 재생성)은 변환기 0.3.0 이 Kit 안에서 안 돌아 방식이 바뀌었다(진행 결과 참고).

## 배경 (확정된 사실)

- `logs/x2_walk/2026-09-17_10-15-33_newton` 은 iteration 900→11,600 동안 mean_reward -6.2→-5.5, 에피소드 길이 ≈22 스텝(0.44 s)로 전혀 학습되지 않았다. 종료했고 폐기 대상이다.
- 정책 없이 0 행동으로 세워 두는 "서 있기 테스트" 에서 PhysX 는 골반 0.594 m 로 6 초 내내 서 있고, Newton 은 무릎이 접히며 0.46 s 만에 무릎이 바닥에 닿아 종료된다.
- 진단(`~/smoke/stand_diag.py`)으로 관절 순서·게인 배열·토크 한계·질량(47 kg)·접촉 센서 몸체 매핑은 두 백엔드 모두 정상임을 확인했다. 토크 한계를 5배로 올려도 궤적이 동일했다 → **PD 토크가 시뮬레이션에 전달되지 않는다.**
- 원인: `x2_ultra_locked20_flat.usd` 의 관절 DriveAPI 가 강성 0 · 감쇠 0 이다(변환 시 `--joint-stiffness 0 --joint-damping 0 --joint-target-type none`). Newton 은 USD 를 읽을 때 두 게인이 모두 0 이면 `JointTargetMode.EFFORT`(액추에이터 없음, 사용자가 토크를 직접 공급) 로 분류한다(`newton/_src/sim/enums.py` `JointTargetMode.from_gains`). 그래서 Isaac Lab 이 실행 시점에 써 넣는 강성 536 등을 받아 줄 MuJoCo 액추에이터가 없다. PhysX 는 실행 시점 게인 덮어쓰기가 드라이브 자체를 만들기 때문에 영향이 없었다.
- TienKung USD(`tienkung2_lite_physics.usd`)도 강성 0 이라 같은 문제가 있다.

## 이미 해 둔 것 (개발 PC)

- 백업: `legged_lab/assets/agibot_x2/usd/x2_ultra_locked20/x2_ultra_locked20_flat.usd.bak_nodrive`
- 패치: 같은 경로의 `x2_ultra_locked20_flat.usd` 의 RevoluteJoint 20개에 `DriveAPI(angular)` type=force, stiffness=1.0, damping=0.1, targetPosition=0 을 써 넣었다(자리표시자 — 실제 게인은 `AGIBOT_X2_CFG` 의 ImplicitActuator 가 실행 시점에 덮어쓴다).
- venv 의 pyglet 을 3.0.dev9 → 2.1.16 으로 내렸다(Newton GL 뷰어 `from pyglet import gl` 오류 해결).
- 스크립트: `legged_lab/scripts/record_play.py` 에 `--policy none`(0 행동), `--no_video`, 리셋 무작위화 비활성(pose/velocity 0, joint scale 1.0) 추가. 개발 PC 래퍼 `~/smoke/run_stand.sh <physx|newton> <out.mp4>`, `~/smoke/run_diag.sh <physx|newton> [--duration s] [--effort_scale k]`.
- 검증 실행은 시작만 하고 사용자 요청으로 중단했다. 결과 없음.
- 2026-09-18 (맥에서 수정, 개발 PC 에 동기화): Newton 백엔드일 때만 켜지는 설정 세 가지를 `legged_lab/utils/env_utils/physics.py` 의
  헬퍼(`use_newton_actuators`, `make_ground_material_cfg`, `contact_force_threshold`)로 넣고 `base_env.py`·`tienkung_env.py`·`scene.py` 가
  쓰게 했다. PhysX 일 때는 값이 이전과 동일(마찰 1.0, 임계 None, 플래그 False)이다. 근거는 아래 "Robotis cyclo_lab 대조".
- 2026-09-18: `legged_lab/assets/agibot_x2/check_usd_inertia.py` 추가. USD 의 주축이 URDF 관성을 복원하는지(`ok` / `inverted` / `composite`) 링크별로 찍는다.

## Robotis cyclo_lab 대조 (2026-09-18)

https://github.com/ROBOTIS-GIT/cyclo_lab 의 `k1/isaacsim-6-newton` 브랜치(Isaac Lab v3.0.0-beta2 고정, Newton 1.2.1, K1 휴머노이드를 Newton 으로 실제 학습)를 우리 설정과 대조했다.

**우리 진단이 맞았다는 확인.** `K1_rev1.py` 의 `UrdfConverterCfg.JointDriveCfg` 주석이 우리 원인과 글자 그대로 같다: "Newton 은 변환된 USD 를 읽을 때 관절 목표 모드를 추론한다. 게인 0 드라이브는 EFFORT 로 영구 분류되어 나중의 ImplicitActuator 게인 갱신으로는 위치 목표가 살아나지 않는다. 그래서 0 이 아닌 위치 드라이브(강성 1.0, 감쇠 1.0)를 심어 두고 실행 시점에 실제 게인으로 덮어쓴다." 그들은 URDF 를 매번 변환하므로 변환기 옵션으로 심고, 우리는 USD 파일에 직접 썼다(`flatten_usd.py` 단계로 옮기면 같은 효과).

**그들이 추가로 한 것 (우리 코드에는 없음).**

| 항목 | Robotis | 우리 | 판단 |
|---|---|---|---|
| `SimulationCfg.use_newton_actuators = True` | 켬. "위치 목표를 Newton 네이티브 액추에이터 경로로 보낸다" | 안 켬 | 목표 모드 자체는 안 바꾸므로 드라이브 자리표시자는 여전히 필요. 전부 ImplicitActuator 여도 fast path 가 켜져 decimation 루프가 CUDA 그래프로 잡힌다(속도). beta2.patch1 에도 있음. Newton 일 때만 켤 것 |
| `ContactSensorCfg.force_threshold = 1.0` | 명시 | `None` | Newton 은 `None` → 0 N 으로 해석(`isaaclab_newton/.../contact_sensor.py:279`). 접촉/공중 시간 전환이 노이즈로 튄다. PhysX 는 백엔드가 값을 고름 |
| 지면 마찰 0 | Newton 일 때 지면 정지·동마찰 0 | 지면 1.0, `friction_combine_mode="multiply"` | MuJoCo 는 두 지오메트리 마찰을 **max** 로 합친다(combine mode 무시). 지면이 1.0 이면 발 마찰 무작위화(0.6~1.0)가 전부 1.0 으로 덮인다. Newton 일 때만 지면 0 |
| CoM 무작위화 끔 | MJWarp 에서 NaN/질량행렬 미갱신 | 우리는 CoM 무작위화 없음 | 해당 없음 |
| critic `base_lin_vel` 를 ±10 으로 클립 | MJWarp 가 강한 접촉에서 한 env 의 루트 속도를 유한하지만 매우 크게 내는 경우가 있어 value loss 만 터짐 | 없음 | 학습 재개 후 value loss 스파이크가 보이면 적용 |
| Isaac Lab 패치 `body_com_acc` 경과 시간 | 여러 물리 스텝 뒤 lazy 갱신 시 가속도가 dt 로 나뉘어 과대 | 우리는 몸체 가속도를 보상에 안 씀 | 해당 없음 |
| MJWarp `njmax=95, nconmax=20`, `ls_iterations=50`, `ls_parallel=True` | 보행 태스크 | `njmax=200, nconmax=100`, `use_mujoco_contacts=False`, margin 0.01 | 우리 쪽이 여유가 많다. 문제 없음 |
| 관절 순서 PhysX=BFS / Newton=DFS | 기존 NPZ 를 위해 명시 매핑 | 이미 파악(`smoke_test_x2_mujoco.py --joint-order`) | 동일 |

**변환기 관성 버그 (백엔드 무관, 별건).** Robotis Dockerfile 은 Isaac Sim 6.0 이 번들한 `urdf-usd-converter` 0.1.x 를 v0.3.0 으로 교체한다. 0.3.0 변경 이력: "관성 곱(products of inertia)이 0 이 아닌 링크에서 `physics:principalAxes` 가 `R·diag·Rᵀ` 로 URDF 텐서를 복원하지 못했다(고유값은 맞고 방향이 틀림)." 개발 PC 의 isaacsim 6.0.1.0 번들은 0.1.3 이고, 우리 X2 USD 를 검산하면 `left_knee_link`, `left_hip_pitch_link` 모두 `Rᵀ·diag·R` 이 URDF 와 일치(오차 1e-10)하고 `R·diag·Rᵀ` 는 최대 성분의 14~35 % 어긋난다 → 우리 USD 는 링크 관성 주축이 뒤집혀 있다. PhysX·Newton 둘 다 `PhysicsMassAPI` 를 읽으므로 둘 다 영향을 받고, MuJoCo(MJCF 직접)는 정상이라 sim2sim 차이의 한 원인이 된다. 서 있기 실패의 원인은 아니고 크기도 작다(골반 병합체도 뒤집혀 있지만 차이는 비대각 성분 부호 수준, 다리 관절의 유효 관성 m·d²+armature 대비 약 2 %). 그래도 Newton 재학습을 처음부터 하는 김에 실행 프롬프트 4번에서 변환기 v0.3.0 으로 USD 를 재생성한다(변환기가 드라이브 자리표시자도 심으므로 수동 패치가 없어진다).

## 실행 프롬프트 (개발 PC 세션에 붙여 넣기)

```
너는 ~/TienKung-Lab (브랜치 feat/isaaclab-3-migration) 에서 Isaac Lab 3.0 Newton 백엔드 수정을 검증하고 Newton 학습을 재시작한다.
문서 docs/plan/2026-09-17-newton-drive-fix-verification.md 를 먼저 읽어라. 환경: venv ~/venvs/isaaclab3 (SP=~/venvs/isaaclab3/lib/python3.12/site-packages),
Isaac Lab 스크립트 클론 ~/IsaacLab(v3.0.0-beta2.patch1), 래퍼 ~/smoke/run_stand.sh, ~/smoke/run_diag.sh, 로그 ~/logs/.
Newton 은 시작 시 1/3 확률로 "malloc(): unaligned tcache chunk detected" 로 죽거나 "Registered backend 'newton'" 에서 멈춘다
→ 같은 명령을 최대 3번 재시도한다(각 timeout 900 s). 어떤 경우에도 pkill 패턴은 "[r]ecord_play.py" 처럼 대괄호로 써서 자기 셸이 안 걸리게 해라.

0. 코드는 이미 동기화돼 있다. Newton 일 때만 use_newton_actuators=True, 지면 마찰 0, 접촉 센서 force_threshold=1.0 이 적용된다
   (legged_lab/utils/env_utils/physics.py). 코드 수정 없이 시작해라.

1. Newton 서 있기 테스트 (지금 패치된 USD):
   cd ~/TienKung-Lab && ~/smoke/run_stand.sh newton outputs/stand/newton_stand_drive.mp4 > ~/logs/stand_newton2.log 2>&1
   grep -E "RECORD|malloc|use_newton_actuators|Newton-native" ~/logs/stand_newton2.log
   통과 기준: "RECORD fell: no" 이고 pelvis z 가 0.73 → 약 0.59 로 내려앉은 뒤 6 초 동안 ±0.02 m 안에 머문다.
2. 관절 모드·마찰 진단:
   ~/smoke/run_diag.sh newton --duration 1 > ~/logs/diag_newton_mode.log 2>&1
   grep -E "^DIAG (model|t=|done)" ~/logs/diag_newton_mode.log
   기대: model.joint_target_mode 가 전부 1(POSITION), knee_tq 가 약 -25 N·m 로 수렴, done 없음.
   추가로 같은 진단 안에서(또는 짧은 스크립트로) NewtonManager.get_model() 의 shape 마찰 배열(shape_material_mu, 이름이 다르면
   dir(model) 에서 mu 를 찾아라)을 찍어 로봇 발 shape 이 0.6~1.0 사이이고 지면 shape 이 0 인지 확인해라. 발이 0 이면 재질 무작위화가
   Newton 에서 안 먹은 것이므로 학습을 시작하지 말고 보고해라.
3. PhysX 회귀:
   ~/smoke/run_stand.sh physx outputs/stand/physx_stand_drive.mp4 > ~/logs/stand_physx2.log 2>&1
   기대: 이전과 동일("fell: no", z 0.594).

4. 1~3 이 모두 통과하면 USD 를 관성이 맞는 변환기로 재생성한다(문서 "변환기 관성 버그" 참고).
   a. 검산 기준선: python legged_lab/assets/agibot_x2/check_usd_inertia.py legged_lab/assets/agibot_x2/urdf/x2_ultra_locked20.urdf \
        legged_lab/assets/agibot_x2/usd/x2_ultra_locked20/x2_ultra_locked20_flat.usd   ← 지금은 inverted 가 여러 개 나와야 정상.
   b. Isaac Sim 번들 변환기 교체(Robotis 방식). PRE=$SP/isaacsim/exts/isaacsim.asset.importer.urdf/pip_prebundle
        cp -r $PRE ~/backup_urdf_prebundle_0.1.3
        rm -rf $PRE/urdf_usd_converter $PRE/urdf_usd_converter-*.dist-info $PRE/newton_usd_schemas $PRE/newton_usd_schemas-*.dist-info
        ~/venvs/isaaclab3/bin/python -m pip install --no-deps --upgrade --target $PRE \
            "git+https://github.com/newton-physics/urdf-usd-converter.git@v0.3.0" "newton-usd-schemas==0.4.0"
   c. 이전 USD 보관: mv legged_lab/assets/agibot_x2/usd/x2_ultra_locked20 legged_lab/assets/agibot_x2/usd/x2_ultra_locked20_conv013
   d. 변환(드라이브 자리표시자를 변환기가 심는다 → 수동 USD 패치 불필요):
        OMNI_KIT_ACCEPT_EULA=YES python ~/IsaacLab/scripts/tools/convert_urdf.py legged_lab/assets/agibot_x2/urdf/x2_ultra_locked20.urdf \
            legged_lab/assets/agibot_x2/usd --merge-joints --joint-stiffness 1.0 --joint-damping 1.0 --joint-target-type position --headless
   e. 평탄화: python legged_lab/assets/agibot_x2/flatten_usd.py legged_lab/assets/agibot_x2/usd/x2_ultra_locked20/x2_ultra_locked20.usda \
        legged_lab/assets/agibot_x2/usd/x2_ultra_locked20/x2_ultra_locked20_flat.usd
   f. 검산: 4-a 의 명령을 새 flat.usd 로 다시 → inverted=0 이어야 한다. inverted 가 남으면 교체한 변환기를 Kit 이 안 쓴 것이다:
        변환 로그에서 urdf_usd_converter 경로/버전을 확인하고, 안 되면 보고하고 멈춰라(학습 시작 금지).
   g. pxr 로 RevoluteJoint 20개의 DriveAPI(angular) stiffness/damping 이 1.0/1.0, 대상 타입 position 인지 출력해라.
   h. 새 USD 로 1(Newton 서 있기)과 3(PhysX 서 있기)을 다시 돌려 둘 다 통과하는지 확인해라. 관성이 바뀌므로 z 값이 몇 mm 달라질 수 있다.

5. 4 까지 통과하면:
   a. legged_lab/assets/agibot_x2/README.md 의 Regenerating 절을 갱신해라: 변환기 교체 절차(4-b), 새 변환 옵션(4-d), 검산(4-f),
      그리고 왜 드라이브 게인이 0 이면 안 되는지(Newton EFFORT 모드) 한 단락.
   b. README.md 루트의 Physics backend 절과 docs/plan/2026-09-15-isaaclab-3-migration.md §7 에 이 사실(드라이브 자리표시자, Newton 전용 설정
      세 가지, 변환기 관성 버그)을 기록해라.
   c. 기존 Newton 런 두 개(2026-09-17_08-49-00_newton, 2026-09-17_10-15-33_newton)는 run 디렉토리 이름 뒤에 _nodrive 를 붙여
      폐기 표시해라(삭제 금지). x2_ultra_locked20_conv013 과 .bak_nodrive 도 삭제하지 말고 보관해라.
   d. Newton 학습을 처음부터 시작해라:
      ~/smoke/run_train.sh --physics newton --run_name newton  (로그 ~/logs/train_x2_walk_newton_v2.log, TensorBoard 6006)
      시작 직후 로그에서 백엔드가 NewtonMJWarpManager 인지, 액추에이터 fast path 가 켜졌는지(관련 INFO/WARN 줄) 확인해라.
      1,000 iteration 시점에 mean_reward 가 양수로 올라가고 에피소드 길이가 수백 스텝인지 확인하고 보고해라. PhysX 런은 같은 구간에서 양수였다.
      value loss 가 튀면(문서 표의 critic 클립 항목) 보고만 하고 멈추지 마라.

6. 하나라도 실패하면 학습을 시작하지 말고, 실패한 단계의 로그 전체 경로와 RECORD/DIAG 줄을 그대로 보고해라.
   되돌리기: USD 는 x2_ultra_locked20_conv013 을 다시 x2_ultra_locked20 으로, 변환기는 ~/backup_urdf_prebundle_0.1.3 을 $PRE 로.
```

## 통과 후 남는 일

- `docs/study/2026-09-17-x2-walk-physx-runs-and-sim2sim.md` 에 이 원인 분석과 서 있기 테스트 수치를 추가.
- 진짜 PhysX vs Newton 4분할 비교 영상(Isaac Sim PhysX | Isaac Sim Newton / MuJoCo PhysX 정책 | MuJoCo Newton 정책)은 새 Newton 런이 걷기 시작한 뒤에.
- TienKung USD 에도 같은 드라이브 자리표시자가 필요하다(Newton 으로 돌릴 계획이 있을 때).
- 기존 PhysX 정책(`logs/x2_walk/2026-09-15_13-06-27`)은 관성 주축이 뒤집힌 USD 로 학습된 것이다. 재학습은 하지 않고 기준선으로 둔다.
  Newton 정책이 MuJoCo 에서 걷는지가 먼저다.
- Newton 학습에서 value loss 가 튀면 critic 의 base_lin_vel 을 ±10 으로 클립(Robotis 가 MJWarp 이상치 때문에 넣은 것).

## 진행 결과 (2026-09-18, 맥에서 ssh 로 실행)

| 단계 | 결과 |
|---|---|
| 1. Newton 서 있기 (수동 패치 USD + Newton 전용 설정) | 통과, 1회차. pelvis z 0.73 → 0.613, 6 s 동안 ±0.001 m |
| 2. 관절 모드·마찰 진단 | 통과, 3회차(1·2회차는 `Registered backend 'newton'` 직후 100 % CPU 멈춤 → SIGKILL). `joint_target_mode` 액추에이터 관절 전부 1(POSITION), ke 468/327/401/536/172/216/98/33/94/29, knee_tq −28 N·m, 발 마찰 0.603~0.997, 충돌 지면 마찰 0. 정적 구 `ft_0`(1 cm, 원점, flags 8)는 FrameView 보조 shape, 비충돌 |
| 3. PhysX 회귀 | 통과, z 0.594 (이전과 동일) |
| 4. USD 재생성 | 변환기 v0.3.0 은 `NewtonMassAPI` 스키마가 Kit 6.0.1 의 `omni.usd.schema.newton`(플러그인 이름 `newton`) 과 충돌해 `ApplyAPI: Cannot find a valid schema` → prebundle 교체·PYTHONPATH 모두 실패, 0.1.3 으로 복원. 대신 0.1.3 으로 `--joint-stiffness 1.0 --joint-damping 1.0 --joint-target-type position` 변환(드라이브 20개 = 0.01745 = 1.0 의 도 단위) + `flatten_usd.py --conjugate-principal-axes` → `check_usd_inertia.py` ok 18 / inverted 0 / composite 3 |
| 4-h. 새 USD 서 있기 | Newton z 0.613, PhysX z 0.594. 둘 다 이전과 동일 |
| 5. 문서·개명·학습 | 에셋 README·루트 README·migration plan §7 갱신. `2026-09-17_08-49-00_newton`, `2026-09-17_10-15-33_newton` → `_nodrive`. Newton 학습 재시작(로그 `~/logs/train_x2_walk_newton_v2.log`) |

학습 진행(런 `logs/x2_walk/2026-09-18_12-42-14_newton`, 2.0 s/iter, VRAM 5.6 GB): iter 11 ep len 51(옛 런 22) → 159 reward −4.7 → 287 −3.8/158 → 403 **+7.4**/775 → 627 21.7/921 → **1043 reward 36.8, ep len 983/1000**. 드라이브 없던 옛 런은 11,600 iter 까지 −6 대였다. Newton 백엔드에서 학습이 된다. 이후 2000 45.2 → 3000 50.2 → 4000 52.1 → 5000 53.4 → 5500 54.2 (ep len 1000 고정). **사용자 결정으로 16:55 에 iter 5,573 에서 종료**(마지막 체크포인트 `model_5500.pt`, 보상은 1000 iter 당 +1.5 정도로 아직 완만히 상승 중이었음; PhysX 최종 60.7). 17:08 사용자 요청으로 재개: `run_train.sh --physics newton --run_name newton_resume5500 --resume True --load_run 2026-09-18_12-42-14_newton --checkpoint model_5500.pt` (`--resume` 는 type=bool 이라 값 True 필수). 새 런 디렉토리 `*_newton_resume5500`, iteration 은 5500 부터 이어짐(목표 55,500), 로그 `~/logs/train_x2_walk_newton_v2_resume.log`. 지면 마찰 1e-4 변경이 이 런부터 적용.

보관: `usd/x2_ultra_locked20_conv013/`(옛 변환 + 수동 드라이브 패치, `.bak_nodrive` 포함), `~/backup_urdf_prebundle_0.1.3/`(prebundle 원본). 변환기 0.3.0 은 Kit 이 새 Newton 스키마를 싣는 버전이 나오면 다시 시도한다.

## sim2sim 6조합 중간 점검 (2026-09-18 16:30~16:55, 명령 0.5 m/s 전진, 10 s)

Newton 정책 = `2026-09-18_12-42-14_newton/model_4900.pt`(학습 10 % 시점), PhysX 정책 = `2026-09-15_13-06-27/model_49999.pt`(최종).
교차 실행은 `record_play.py --policy_joint_order` 로 관측 프레임(75 = 9 + 20·3 + 6)의 관절 슬라이스와 행동을 재배열.

| 학습 \ 실행 | MuJoCo (맥, CPU) | Newton | PhysX |
|---|---|---|---|
| Newton (4,900) | 안 넘어짐, x +3.74 / y +5.02 m, 0.37 m/s, 골반 0.55~0.66 출렁임 | 안 넘어짐, x +4.21 / y −0.38, 0.42 m/s | 안 넘어짐, x +4.05 / y −0.56, 0.40 m/s |
| PhysX (49,999) | **5.2 s 에 넘어짐**, x +2.83 / y −1.14 | 안 넘어짐, x +5.02 / y −0.25, 0.50 m/s | 안 넘어짐, x +4.51 / y +0.09, 0.45 m/s |

- 정책 파일: 맥 `outputs/policies/{physx_50000,newton_4900}.pt`. 영상: 맥 `outputs/matrix/`(개별 6편 + `sim2sim_matrix_2x3.mp4`, `make_grid.sh` 로 재생성).
- 관찰: Isaac 두 백엔드 사이(Newton↔PhysX)는 양방향 모두 전이가 잘 된다. 순수 MuJoCo 로 가면 PhysX 정책은 넘어지고 Newton 정책은 서서 걷지만 옆으로 크게 흐른다.
  MuJoCo 평가 스크립트는 PD 를 스크립트에서 닫고(`smoke_test_x2_mujoco.py`) 게이트 주기 0.68 을 쓰므로 Isaac 쪽과 조건이 완전히 같지는 않다. Newton 정책은 아직 학습 초반이라 최종 체크포인트로 재평가 필요.
- 종료 후 최종 `model_5500.pt` 를 MuJoCo 에서 같은 조건으로 돌리니 **4.58 s 에 넘어짐**(x +4.65 / y +2.82 m). 4900 은 안 넘어졌고 5500 은 넘어졌으므로 한 번의 롤아웃으로
  "MuJoCo 전이 성공" 을 말할 수 없다. 체크포인트·시드·명령을 바꿔 여러 번 돌려 낙상률로 비교해야 한다(영상 `outputs/matrix/newton5500_on_mujoco/`).

## 2026-09-19 재개 런 결과와 MuJoCo 낙상률 스윕

- 재개 런 `2026-09-18_17-08-33_newton_resume5500` 은 09-19 04:44, iter 20,607 에서 `RuntimeError: normal expects all elements of std >= 0.0` 로 죽었다
  (정책 std 가 NaN — 한 업데이트에서 손실이 발산). Robotis 가 critic `base_lin_vel` 을 ±10 클립한 이유(MJWarp 이상치)와 같은 부류. 보상은 16k 부터 58 고원
  (10k 56.6 / 16k 58.2 / 18k 58.2 / 20k 57.4; PhysX 최종 60.7). 마지막 체크포인트 `model_20600.pt`. 사용자가 원격으로 꺼내 준 원본 체크포인트를 맥에서
  bundled rsl_rl `ActorCritic(750, 800, 20, [512,256,128], elu)` 로 복원해 `outputs/policies/newton_20600.pt` 로 내보냈다(Isaac 불필요, 출력 오차 0).
- `smoke_test_x2_mujoco.py` 에 `--seed`(관절 ±0.05 rad, 임의 yaw, 루트 속도 ±0.2 m/s), `--quiet`, `RESULT` 요약 줄 추가. 4 정책 × 명령 {0, 0.3, 0.5} × 시드 5, 10 s.

| 정책 | cmd 0.0 | cmd 0.3 | cmd 0.5 |
|---|---|---|---|
| PhysX 50,000 | 0/5 낙상 | 2/5 | 1/5 |
| Newton 4,900 | 3/5 | 4/5 | 4/5 |
| Newton 5,500 | 5/5 | 5/5 | 5/5 |
| Newton 20,600 | 5/5 | 5/5 | 5/5 |

- 무교란 cmd 0 에서도 Newton 20,600 은 4.2 s 에 넘어진다(|action| 이 2 이상으로 커짐). PhysX 정책은 교란을 줘도 선다. Newton 체크포인트가 늦을수록 MuJoCo 전이가
  나빠진다. **"Newton 으로 학습하면 MuJoCo 전이가 좋아진다" 는 전제가 이 하네스에서는 뒷받침되지 않는다.**
- 하네스 쪽 의심 지점: MuJoCo 평가는 토크 모터 + 스크립트 PD(명시적, 5 ms)이고 Isaac 두 백엔드는 implicit PD(implicitfast)다. kp 536 / armature 0.03 이면
  ω·dt ≈ 0.67 로 명시적 PD 안정 한계 근처라 큰 행동을 내는 정책일수록 불리하다. 관절 순서 매핑은 어제 Newton 정책→PhysX 교차 실행이 걸었으므로 검증됨.
- 1 kHz 명시적 PD(`--substeps 5`, 시드 3 × cmd {0, 0.5}) 재평가: PhysX 0/6, Newton 4,900 0/6(단 cmd 0 에서도 3~4 m 움직여 명령을 안 따름), **Newton 20,600 6/6 낙상**.
  PD 주기는 결과를 크게 바꾸므로(PhysX 3/15 → 0/6) 이후 MuJoCo 평가는 `--substeps 5` 를 기본으로 볼 것. 그래도 20,600 은 넘어진다 → 하네스가 아니라 정책이
  Newton 역학에 과적합된 것으로 본다(가설: 학습이 길어질수록 행동 크기가 커지며 Newton 접촉/PD 특성에 맞춘 고게인 보행이 됨).
- 다음 확인: (1) 개발 PC 에서 20,600 을 Isaac Newton cmd 0 으로 세워 보기(거기서 서면 갭은 Newton→MuJoCo 역학 차이), (2) MuJoCo 하네스를 1 kHz 서브스텝 PD 또는
  position 액추에이터(implicit)로 바꿔 재평가, (3) 재개하려면 critic 속도 클립 + NaN 가드 먼저.

## 2026-09-21 MuJoCo 하네스를 TienKung 방식(implicit position 서보)으로

`smoke_test_x2_mujoco.py` 에 `--actuator position`(MJCF motor 를 런타임에 kp/kd affine bias 의 position 서보로 바꾸고 `implicitfast` 적분, ctrl = 목표 각도 — TienKung
MJCF·Isaac ImplicitActuator 와 같은 모델)과 `--frictionloss <v>`(관절 frictionloss 덮어쓰기; USD 에는 관절 마찰이 없고 벤더 MJCF 는 0.3 N·m) 추가.
무정책 서 있기: 골반 0.594 m (PhysX 와 동일). 시드 3 × cmd {0, 0.5}, 10 s, 리셋 교란:

| 정책 | 명시 PD 5 ms | 명시 PD 1 kHz | position 서보 | position 서보 + frictionloss 0 |
|---|---|---|---|---|
| PhysX 50,000 | 3/15 | 0/6 | 2/6 | **0/6** |
| Newton 4,900 | 11/15 | 0/6 | 3/6 | 2/6 |
| Newton 20,600 | 15/15 | 6/6 | 5/6 | 6/6 |

- 하네스 정합(implicit PD) + 에셋 정합(관절 마찰 0 = USD 와 동일)으로 **PhysX 정책은 MuJoCo 에서 0/6** 이 된다. TienKung 이 잘 됐던 이유(같은 액추에이터 모델, 같은 에셋)가
  X2 에서도 그대로 재현된다. 앞으로 MuJoCo 평가 기본은 `--actuator position --frictionloss 0`(또는 USD 에 0.3 을 넣고 양쪽 다 켜기).
- Newton 20,600 은 어떤 하네스에서도 넘어진다 → 남은 갭은 Newton 백엔드 고유: 자체 충돌 파이프라인(`use_mujoco_contacts=False`, margin 0.01, gap), 접촉 강성,
  지면 마찰 max 규칙(로봇 0.6~1.0 vs MuJoCo 1.0). 4,900 이 더 잘 서는 것은 학습이 길어질수록 그 특성에 맞춰지기 때문으로 본다.
- 교란에 임의 yaw 가 들어가므로 표의 dx 는 전진량이 아니다(월드 x). 낙상 여부만 비교할 것.
- 다음(개발 PC 필요): (1) 20,600 을 Isaac Newton cmd 0 에서 세워 확인, (2) `use_mujoco_contacts=True` + 지면 마찰 1.0/로봇 1.0 고정으로 Newton 재학습 후 같은 스윕,
  (3) 재학습 전 critic 속도 클립 + NaN 가드.

## 2026-09-21 개발 PC: 20,600 Isaac 재생, MuJoCo 접촉 모드, 재학습

- 20,600 을 Isaac 에서 재생: Newton cmd 0 → 서 있음(z 0.639), Newton cmd 0.5 → 0.41 m/s 보행, PhysX cmd 0.5 → 0.41 m/s. **Isaac 안에서는 정상, 순수 MuJoCo 에서만 낙상** 확정.
- 코드: `SimCfg.newton_contacts: "newton" | "mujoco"`(+ 네 스크립트의 `--newton_contacts`) → `MJWarpSolverCfg.use_mujoco_contacts`, mujoco 일 때 `collision_cfg=None`(필수).
  critic 의 `root_lin_vel` ±10 클립(tienkung_env). `amp_ppo.update` 에 비유한 grad norm 이면 optimizer step 을 건너뛰는 가드(std NaN 재발 방지).
- MuJoCo 접촉 모드 서 있기: 통과, **골반 z 0.593** — Newton 자체 파이프라인의 0.613 이 아니라 PhysX/순수 MuJoCo 의 0.594 와 같다. 2 cm 높이 차이가 접촉 파이프라인
  (마진 1 cm 등)에서 온 것이었음. sim2sim 갭의 주요 후보가 맞았다는 신호.
- 재학습 시작 10:5x: `run_train.sh --physics newton --newton_contacts mujoco --run_name newton_mjc`, 로그 `~/logs/train_x2_walk_newton_mjc.log`, 처음부터.
  평가는 `smoke_test_x2_mujoco.py --actuator position --frictionloss 0 --joint-order newton` 스윕으로.

## 2026-09-21 오후: `newton_mjc` 첫 런 NaN 원인 진단과 가드

- 첫 `newton_mjc` 런은 반복 2부터 Mean reward NaN, PPO 가드가 440 회 update 를 건너뜀 → 종료. 원인 두 겹:
  1. **지면 마찰 1e-4.** MuJoCo 접촉 파이프라인에서 대량 NaN 을 냈다. 로봇 무작위화 하한인 **0.6** 으로 올리자 대량 NaN 은 사라짐(`physics.py`).
  2. **MuJoCo-Warp 산발 NaN.** `~/smoke/nan_diag.py`(무작위 행동, 512 env, 300 step): mujoco+rand 0/512, mujoco no-rand 1/512, newton 0/512.
     2048 env × 1000 step(no-rand)에서는 32 회, env-step 당 ≈1.6e-5 → 4096 env 학습이면 반복당 ≈1.5 회. 한 env 가 NaN 이 되면 접촉 종료가 절대 안 걸리고
     PPO 미니배치 전체가 오염되며, **Isaac reset 으로도 안 풀린다**(reset 은 joint/root 만 다시 쓰고 `mjw_data` 의 qacc_warmstart·qM·qLD·cvel 등 월드 스크래치는 NaN 그대로 →
     다음 step 에 다시 폭발; 가드가 같은 env 84 에 대해 매 step 반복 발동으로 확인).
- 가드(두 env 공통): `check_reset` 에서 root pos/quat/lin vel/ang vel·joint pos/vel 중 하나라도 비유한 env 를 `nonfinite_buf` 로 잡아 reset 대상에 넣고 보상을 0 으로. Newton 이면 reset **전에**
  `sanitize_newton_worlds(env_ids)`(`physics.py`)가 `NewtonManager._solver.mjw_data` 의 nworld 축 float 배열과 `get_state_0()` 의 joint_q/qd/qdd·body_q/qd·joint_f·body_f 에서
  해당 월드 행을 0 으로 지운 뒤 reset + forward 로 재구성. 진단(사후 sanitize 버전)에서는 이벤트마다 경고가 한 번만 나고 env 가 복구됨(1621 만 두 번 재발).
- 첫 가드 버전으로 띄운 `newton_mjc2` 는 반복 6까지 grad 스킵 65회 → 종료. 원인: sanitize + reset + forward 뒤에도 그 step 의 `robot.data` 읽기(root_lin_vel_b 등)는 여전히 NaN 이라
  policy obs / AMP obs 에 NaN 이 실려 나감(→ NaN action → 다음 step 재오염). 대책: `compute_observations` 와 `get_amp_obs_for_expert_trans` 에서 `nonfinite_buf` 행을 0 프레임으로
  치환(그 env 는 어차피 reset 된 상태). 2048 env 검증에서 반환 obs NaN 0 을 확인한 뒤 재학습 재시작(`~/logs/nan_guard_prod2.log`).
- obs 0 치환 버전도 반복 49까지 grad **inf** 스킵 244/980(가드가 안 뜬 반복에서도 발생). NaN 이 되기 전 단계의 거대한 유한값(|v| 5e5, |qd| 7e6 등)이
  보상·AMP obs(비클립)로 새는 것이 원인 → `check_reset` 에 크기 가드 추가(|v|>50 m/s, |ω|>200 rad/s, |qd|>1000 rad/s, |pos|>1e4 → 비유한과 동일 처리) + 비유한 보상 0 치환.
  결과(`logs/x2_walk/2026-09-21_13-19-59_newton_mjc2`): 반복 31 동안 폭주 포착 18회, **grad 스킵 0**, reward -13→-11.6(초기 구간 정상), 2.1 s/iter.
- 지워지는 배열: actuator_force/length/velocity, cacc, cdof(_dot), cfrc_int, cinert, crb, cvel, geom_xpos, qLD, qM, qacc(_smooth/_warmstart), qfrc_bias/smooth, qpos, qvel, subtree_com,
  xanchor, xipos, xpos. PhysX 경로에서는 함수가 no-op.
- 재학습: `run_train.sh --physics newton --newton_contacts mujoco --run_name newton_mjc2`, 로그 `~/logs/train_x2_walk_newton_mjc2.log`(가드 검증 `~/logs/nan_guard_prod.log` 통과 후 자동 시작).
  초반 반복에서 `[WARN] non-finite` 빈도와 Mean reward 유한 여부를 볼 것. 첫 시도는 Newton 시작 멈춤(13분간 `factory ContactSensor`)에 걸려
  `~/smoke/train_retry.sh <log> <run_train.sh 인자>`(5분 뒤에도 그 줄이면 SIGKILL 후 재시도, 최대 4회; 진행 로그 `~/logs/train_retry_newton_mjc2.out`)로 재기동.

## 2026-09-22 `newton_mjc2` 결과: MuJoCo 접촉 모드 학습의 sim2sim

학습 상태(09-22 08:00): 반복 31,594, Mean reward 64.0(PhysX 최종 60.7, 옛 Newton 고원 58 보다 높음), ep len 995, grad 스킵 0, 폭주 포착 2,445회(반복당 0.08),
비유한 보상 12회(모두 0 치환). 계속 진행 중(`logs/x2_walk/2026-09-21_13-19-59_newton_mjc2`).

순수 MuJoCo 낙상률(맥, `--actuator position --frictionloss 0 --gait-cycle 0.68`, 10 s, 시드 1~6 리셋 교란, 원본 ckpt → `scratchpad/ckpt_to_jit.py` 로 TorchScript, Isaac 불필요):

| 정책 | cmd 0 | cmd 0.5 m/s |
|---|---|---|
| PhysX 50,000 (기준) | 0/6 | 3/6 |
| Newton(자체 접촉) 20,600 | 3/3 | 3/3 |
| newton_mjc2 5,000 | 2/6 | 5/6 |
| newton_mjc2 **10,000** | **0/6** | **0/6** |
| newton_mjc2 15,000 | 0/6 | 2/6 |
| newton_mjc2 20,000 | 0/6 | 4/6 |
| newton_mjc2 25,000 | 0/6 | 3/6 |
| newton_mjc2 31,500 | 2/6 | 6/6 |

- **MuJoCo 접촉 모드로 바꾸자 Newton 백엔드 고유 갭이 사라졌다.** 옛 Newton 정책은 전부 낙상이었는데, 같은 하네스에서 newton_mjc2 10,000 은 PhysX 기준선보다 낫다(0/12 vs 3/12).
- PhysX 도 시드를 늘리니 cmd 0.5 에서 3/6 넘어진다(09-21 의 0/6 은 시드 1~3 만). 기준선이 완벽하지 않으니 6 시드 이상으로 비교할 것.
- 체크포인트가 늦을수록 전이가 나빠지는 추세는 여기서도 같다(PhysX 런에서도 관찰된 현상). Isaac 안에서는 보상이 계속 오르므로 시뮬레이터 특성에 과적합하는 것으로 본다.
  sim2sim 후보는 10,000~15,000 구간. 이후 학습을 더 돌려도 전이 목적에는 이득이 없을 가능성이 크다(조기 종료 or 무작위화 강화가 다음 실험).
- 로그: `outputs/matrix/mujoco_sweep_mjc2*.txt`, 정책 `outputs/policies/newton_mjc2_*.pt`(git 무시).

### 09-22 "왜 MuJoCo 에서 직진을 못 하나" (학습은 32,829 에서 사용자 지시로 종료, 최종 `model_32800.pt`)

- 학습 설정이 `heading_command=True`(stiffness 0.5, `rel_heading_envs=1.0`): Isaac 에서는 **명령 생성기가 매 step ωz = 0.5·wrap(목표 heading − yaw) 를 다시 계산**한다.
  즉 heading 유지는 정책이 아니라 환경이 닫는 루프. 하네스는 ωz=0 고정이라 yaw 편향이 그대로 누적됐다. `smoke_test_x2_mujoco.py --heading` 으로 같은 법칙을 재현.
- 원인 두 겹(측정: scratchpad `heading_probe.py`, `wz_probe.py`, cmd vx 0.5):
  1. **환경 heading 루프 부재**(위). PhysX 정책은 `--heading` 을 켜면 ±30° 안에서 방향을 유지한다.
  2. **mjc2 정책의 MuJoCo 고유 yaw 편향**: ωz 명령 0 인데 +0.42 rad/s 로 돈다. 명령 +0.5 → +0.76, −0.5 → **+0.30**(부호도 못 따라감). Isaac 재생(Newton·PhysX 모두)은
     10 s 에 y 0.1 m 이내로 직진(0.42 m/s) → 순수 MuJoCo 에서만 나는 편향. `--heading` 을 켜도 10 s 에 +94° 까지 돈다(stiffness 0.5 로는 0.4 rad/s 편향을 못 이김).
     Newton(MJWarp, USD 에서 생성한 모델)과 순수 MuJoCo(벤더 MJCF)는 **에셋 자체가 다르다**(충돌 형상·관성·armature) → 다음 조사 대상.
- `--heading` 6시드 낙상(cmd 0 / 0.5): mjc2 10k **0/6·0/6**, 15k **0/6·0/6**, PhysX 50k 0/6·3/6. 이후 MuJoCo 평가 기본 옵션에 `--heading` 추가.
- 6분할 영상 v2: `outputs/matrix/sim2sim_matrix_mjc2_2x3.mp4`(행 1 = newton_mjc2 10,000, 행 2 = PhysX 50,000; 열 = 순수 MuJoCo(heading on) | Isaac Newton(MuJoCo 접촉) | Isaac PhysX).
