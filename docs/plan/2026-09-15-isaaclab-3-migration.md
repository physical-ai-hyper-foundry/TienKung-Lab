# Isaac Lab 3.0 마이그레이션 계획

ADR-001 에 따라 학습 스택을 Isaac Sim 6.0.1 + Isaac Lab 3.0.0-beta2.patch1 로 옮긴다.
브랜치 `feat/isaaclab-3-migration` (`feat/agibot-x2-port` 기반). 2026-09-15 기준.

목표: `x2_walk` 학습이 6.0.1 에서 돌고, 학습 중 화면을 브라우저(Docker Compose 웹 뷰어)로 볼 수 있으며,
결과 모델을 MuJoCo sim2sim 으로 조작한다. PhysX 백엔드만 쓴다(Newton 미지원 이벤트 사용).

## 1. 대조 근거

Isaac Lab `v3.0.0-beta2.patch1` 소스를 받아 이 레포가 import 하는 모든 심볼과 호출을 대조했다.
아래 표의 "3.0" 열은 소스에서 직접 확인한 것이다.

| 항목 | 2.1 (현재) | 3.0 | 조치 |
|---|---|---|---|
| `.data.*` 반환형 | `torch.Tensor` | `ProxyArray` (`.torch` 로 접근, 암묵 사용은 경고 후 동작) | 105곳 `.torch` 명시 |
| 쿼터니언 | WXYZ | XYZW | 하드코딩 1곳(`visualize_motion`) 수정. sim 값을 `quat_*` 에 그대로 넘기는 19곳은 무변경 |
| `root_state_w` | 정상 | 4.0 폐기 예고 | `root_link_pos_w` / `root_link_quat_w` 로 교체 |
| `body_state_w[..., :3]` / `[..., 3:7]` | 정상 | 정상 | `body_pos_w` / `body_quat_w` 로 교체 (슬라이스 의존 제거) |
| `write_joint_position_to_sim` / `write_joint_velocity_to_sim` | 있음 | **삭제** | `*_to_sim_index(position=…)` / `(velocity=…)` |
| `write_root_state_to_sim` | 있음 | 폐기 래퍼 | `write_root_link_pose_to_sim_index` + `write_root_com_velocity_to_sim_index` |
| `set_joint_position_target` | 있음 | 폐기 래퍼 | `set_joint_position_target_index(target=…)` |
| `SimulationCfg(physx=PhysxCfg)` | `isaaclab.sim.PhysxCfg` | `physics=isaaclab_physx.physics.PhysxCfg` | import 경로·필드명 변경 |
| `RayCasterCfg.attach_yaw_only` | 있음 | **삭제** | `ray_alignment="yaw"` |
| `isaacsim.core.utils.torch.set_seed` | 있음 | Isaac Sim 6.0 폐기 경로 | `isaaclab.utils.seed.configure_seed` |
| `--headless` | 기본 | 폐기(동작함). 기본이 headless, `--viz kit` 로 창 | 스크립트 유지, 렌더 게이트는 `sim.is_rendering` |
| `isaaclab_rl.rsl_rl.RslRlOnPolicyRunnerCfg` | `policy`/`algorithm` | `actor`/`critic`/`obs_groups` (rsl-rl-lib 5.x) | 2.1 cfg 클래스를 `legged_lab/utils/rsl_rl_cfg.py` 로 내장 |
| `isaaclab_rl.rsl_rl.export_policy_as_*` | 2.x policy 대상 | 5.x policy 대상 | 2.1 exporter 를 `legged_lab/utils/exporter.py` 로 내장 |
| URDF 임포터 | `convert_urdf.py in out.usd` | 재작성. 출력 `<dir>/<name>/<name>.usda`, `make_instanceable`/`root_link_name` 무시 | README·`usd_path`·`.gitignore` 갱신 |
| `RigidBodyPropertiesCfg` 등 스키마 cfg | `isaaclab.sim` | `isaaclab_physx.sim.schemas` (3.x 내내 별칭 유지) | 무변경 (3.0 레퍼런스 env 도 `sim_utils.RigidBodyMaterialCfg` 사용) |
| `ContactSensor` 데이터 (`net_forces_w_history`, `current_air_time`) | 정상 | 정상 (ProxyArray) | `.torch` |
| managers / commands / buffers / terrains / markers | 정상 | 시그니처 동일 | 무변경 |
| Python / numpy | 3.10, numpy<2 | **3.12**, numpy≥2 | `setup.py` distutils 제거, `np.int` 3곳 제거 |

변경 없는 것: X2 포팅 전체(이름 기반 설정), 내장 `rsl_rl`(AMP, 순수 torch), MuJoCo sim2sim, 보상 항 정의.

## 2. 작업 순서와 검증

```
[0] 도구 준비                 setup.py setuptools, rsl_rl np.int → int
    → verify: py_compile

[1] isaaclab_rl 의존 제거      legged_lab/utils/rsl_rl_cfg.py, exporter.py 내장, cfg 파일 import 교체
    → verify: grep -r "isaaclab_rl" legged_lab == 0

[2] 시뮬레이션 설정            base_env.py: SimulationCfg(physics=PhysxCfg), configure_seed
                             scene.py: ray_alignment="yaw"
    → verify: grep attach_yaw_only / "from isaaclab.sim import PhysxCfg" == 0

[3] 데이터 접근·쓰기 API       base_env / tienkung_env / rewards: .torch, *_index, root_link_*, body_pos_w
    → verify: 스크립트로 .data.X 뒤에 .torch 없는 곳 0, 삭제된 API 호출 0

[4] 쿼터니언                   visualize_motion 의 WXYZ 재배열 제거
    → verify: find_quaternions.py --path legged_lab 에서 env/mdp 잔여 0
              (sensors/ 의 3건은 with_sensor 전용, 별도 처리)

[5] 렌더/스트리밍 게이트        step(): if self.sim.is_rendering: self.sim.render()
    → verify: 정적. 실동작은 GPU 머신

[6] 에셋·문서                  X2 README 변환 명령, AGIBOT_X2_CFG.usd_path, .gitignore, README 설치 절차
    → verify: 경로 문자열 일관성

[7] GPU 머신 (Ubuntu 22.04/24.04, 5070 Ti)
    uv 로 isaaclab[isaacsim,all]==3.0.0-beta2.patch1 (+ isaacsim 6.0.1.0, torch 2.10 cu128)
    pip install -e . && cd rsl_rl && pip install -e .   ← rsl-rl-lib 5.0.1 을 덮어쓰도록 마지막에
    convert_urdf.py 로 X2 USD 생성 → usd/x2_ultra_locked20/x2_ultra_locked20.usda
    WARN_ON_TORCH_QUATF_ACCESS=1 python legged_lab/scripts/train.py --task=x2_walk --num_envs=64
    → verify: DeprecationWarning 0, 쿼터니언 경고 0, robot.joint_names 기록
    python legged_lab/scripts/train.py --task=walk --num_envs=64   ← TienKung 회귀
    브라우저 스트리밍: --livestream 2 로 학습 실행 + Isaac Sim 6.0 웹 뷰어(포트 8210) 접속
    → verify: 브라우저에서 학습 장면 표시
```

## 3. 설계 결정 (되돌리기 쉬운 것들)

- **`.torch` 를 전부 명시한다.** 암묵 브리지(`__torch_function__`)는 4.0 에서 제거 예고라 지금 없앤다.
- **PhysX 전용.** `PresetCfg` 로 Newton 변형을 만들지 않는다. `randomize_rigid_body_material` 등이
  Newton 미지원이고 목표는 PhysX 학습이다.
- **rsl_rl cfg 클래스를 내장한다.** 내장 AMP 러너는 `train_cfg["policy"]` / `["algorithm"]` 딕셔너리
  구조를 요구하는데 3.0 의 `RslRlOnPolicyRunnerCfg` 는 `actor`/`critic`/`obs_groups` 구조다.
  isaaclab_rl 을 어댑터로 끼우는 것보다 2.1 의 5개 configclass 를 그대로 가져오는 편이 작다.
- **`--headless` 플래그는 남긴다.** 3.0 에서 폐기됐지만 동작하고, 스크립트가 `args_cli.headless` 를 쓴다.
  README 에서는 `--viz kit` / 생략 을 안내한다. 단 스트리밍 시에는 `--headless` 를 넘기면 안 된다(5절 (b)).
- **with_sensor 변형(카메라·라이다·높이맵)은 이번 범위 밖.** `TiledCamera` 서브클래스와 커스텀
  `RayCaster.reset`(torch `drift` 가정)은 3.0 Warp 백엔드에서 검증하지 않았다. import 는 되게 유지한다.

## 4. 브라우저 스트리밍 메모

- Isaac Sim 6.0 웹 뷰어는 Docker Compose 로 뜨며 Ubuntu 호스트 전용, 포트 8210, Chromium 계열.
- 학습 프로세스 쪽은 `--livestream 2`(private WebRTC) 로 띄우면 AppLauncher 가
  `omni.kit.livestream.app` 확장을 켠다. headless 로 강제되지만 렌더는 유지된다.
- 학습 프로세스를 네이티브로 두고 뷰어 컨테이너만 붙일 수 있는지, 아니면 compose 의 Isaac Sim
  컨테이너 안에서 학습을 돌려야 하는지는 GPU 머신에서 확인한다. 후자가 문서 기준 경로다.
- 한 인스턴스에 한 클라이언트만 붙는다. "사용자가 클릭하면 보여준다"는 UX 는 뷰어 URL 을 여는 것으로
  구현하고, 스트림 자체는 학습 시작 시 항상 켜 둔다.
- (검증 후) 학습 프로세스는 네이티브로 두고 뷰어 컨테이너만 붙이면 된다. 5절 참조.

## 5. 진행 상태 (2026-09-15)

[0]~[6] macOS 정적 작업 완료. [7] 은 개발 PC(Ubuntu 24.04, RTX 5070 Ti 16 GB, driver 595.84)에서 실행했다.

- 환경: uv venv Python 3.12.3, isaacsim 6.0.1.0, isaaclab 3.0.0b2.post1, torch 2.10.0+cu128. isaaclab 휠 설치가
  torch 를 2.11 PyPI 빌드로 올려 `libtorch_cuda.so: undefined symbol: ncclDevCommDestroy` 가 났고, cu128 2.10.0 으로
  재고정해 해결. 내장 `rsl_rl`(2.3.1) 을 마지막에 설치해 rsl-rl-lib 5.0.1 을 대체.
- `pip install -e .` 는 gcc 가 없는 머신에서 `pynput → evdev` 소스 빌드에 실패한다. `--no-deps` 로 설치한 뒤
  mujoco / matplotlib / pynput(`--no-deps`) 을 따로 넣었다. README 에 기재.
- `legged_lab/terrains/ray_caster.py`: 3.0 의 `isaaclab.sensors.ray_caster.RayCaster` 는 백엔드 팩토리라 외부
  서브클래스가 import 시점에 `ImportError` → PhysX 구현체(`isaaclab_physx.sensors.ray_caster.ray_caster.RayCaster`)
  를 상속하도록 변경. 기본 `reset` 이 3축 drift 를 재샘플하므로 z 축 0.1 배만 덧씌운다.
- X2 USD 변환 성공: 강체 21, 관절 20, 순서는 BFS 예측대로(TienKung 과 `(0,1)↔(4,5)` swap). **단** 6.0 임포터는
  링크를 부모 링크 아래 중첩(`Geometry/pelvis/left_hip_pitch_link/...`)해 저장하고, beta2.patch1 의
  `activate_contact_sensors` 는 첫 강체에서 탐색을 멈춰 pelvis 에만 contact reporter 가 붙는다 →
  `undesired_contacts` 의 body 정규식 해석 실패. 업스트림 isaac-sim/IsaacLab#5126, develop 에 2026-07-16 수정
  (#6378) 됐으나 릴리스에는 미포함. 조치: `legged_lab/assets/agibot_x2/flatten_usd.py` 로 계층을 평탄화(월드
  포즈 베이크, 관계 36건 재매핑, 출력 `x2_ultra_locked20_flat.usd`) → 21개 전부 reporter 확인.
- `x2_walk` 64 env 3 iter: 정상(obs 750, 레포 코드발 DeprecationWarning 0). `WARN_ON_TORCH_QUATF_ACCESS=1`
  경고 8곳은 모두 sim 쿼터니언을 3.0 `quat_*` 함수에 그대로 넘기는 곳으로, 순서 가정이 없다.
- TienKung `walk` 64 env 3 iter: 정상. 회귀: 2.1 에서 학습한 `Exported_policy/walk.pt` 를 3.0 env 에서
  400 step 실행 → 낙상 0/64 (무작위 정책은 3~46 step 에 종료). 관측 파이프라인·쿼터니언 순서 일치로 판정.
- 브라우저 스트리밍: 웹 뷰어는 IsaacSim 레포 `tools/docker/web-viewer/Dockerfile` 로 로컬 빌드된다(공개
  base 이미지, NGC 로그인 불필요). 개발 PC 에서 `ISAACSIM_HOST=192.168.0.6` 으로 빌드해 host network 로
  8210 에 띄웠고, 학습은 `PUBLIC_IP=192.168.0.6 --livestream 1 --viz kit` 로 실행. 두 가지 함정:
  (a) 뷰어가 `crypto.randomUUID` 를 써서 `http://<ip>` 접속(비보안 컨텍스트)에서는 TypeError → `tools/web-viewer/`
  의 폴리필 이미지로 해결. (b) `--headless` 를 넘기면 3.0 이 visualizer 를 전부 끄고, 3.0 의 `render()` 는
  visualizer 가 없으면 Kit 앱 루프를 돌리지 않아 프레임 0 → 인코더 세션 fps 0, 50 초 뒤 SERVER_DISCONNECTED.
  `--viz kit` 필수. 4096 env: 3.0 s/iter(렌더 없음) → 4.3 s/iter(렌더).

## 6. 남는 위험

- 3.0 은 beta. `isaaclab==3.0.0b2.post1` 로 핀하고 올릴 때만 의도적으로 올린다.
- `flatten_usd.py` 는 임시 조치다. #6378 이 포함된 릴리스로 올리면 스크립트와 `_flat.usd` 를 제거하고
  `AGIBOT_X2_CFG.usd_path` 를 임포터 원본(`x2_ultra_locked20.usda`)으로 되돌린다.
- "학습 프로세스 네이티브 + 뷰어 컨테이너만" 구성은 성립한다(compose 의 isaac-sim 서비스 없이 web-viewer 만).
  뷰어는 빌드 시점에 호스트 IP 를 굽기 때문에 IP 가 바뀌면 재빌드해야 한다.
- with_sensor 변형(카메라·라이다·높이맵)은 미검증.

## 7. Newton(MuJoCo-Warp) 백엔드 (2026-09-16 ~ 17)

목적: "MuJoCo 로 학습" 요청. 순수 MuJoCo(CPU, 단일 env) 학습은 비현실적이고 MJX/MuJoCo Playground 는 태스크 전체를
다시 써야 한다. Isaac Lab 3.0 의 Newton 백엔드가 MuJoCo-Warp 솔버(`MJWarpSolverCfg`)를 GPU 병렬로 돌리므로 이쪽을
택했다. 환경·보상·러너 코드는 그대로다.

- 변경: `SimCfg.physics_backend: Literal["physx","newton"]`(기본 physx), `legged_lab/utils/env_utils/physics.py`
  의 `make_physics_cfg()` 가 `PhysxCfg` 또는 `NewtonCfg(MJWarpSolverCfg(njmax=200, nconmax=100, cone=pyramidal,
  integrator=implicitfast, use_mujoco_contacts=False), collision max_triangle_pairs=2.5M, default_shape margin=0.01)`
  을 돌려준다(isaaclab_tasks `velocity_env_cfg.RoughPhysicsCfg.newton_mjwarp` 와 동일 값). `BaseEnv` 와
  `TienKungEnv` 둘 다 이 함수를 쓴다. `train.py` / `play.py` / `record_play.py` / `export_policy.py` 에 `--physics`.
- **사고(2026-09-17 발견).** 처음에는 분기를 `BaseEnv.__init__` 에만 넣었는데 `x2_walk` 를 포함한 모든 태스크는
  `TienKungEnv` 로 등록돼 있고 그 클래스가 `SimulationCfg(physics=PhysxCfg(...))` 를 따로 만든다. 그래서 09-16
  15:17 에 `--physics newton` 으로 시작한 런은 PhysX 로 돌았다. 스모크가 통과해도 백엔드가 바뀌었다는 증거는
  아니었다. `env.sim.physics_manager.__name__` 을 찍어 확인하는 스크립트(`~/smoke/check_backend.py`)로 잡았고,
  런 디렉토리는 `2026-09-16_15-17-02_physx-run2` 로 이름을 바꿨다. 교훈: 백엔드 전환은 로그가 아니라 매니저
  클래스 이름으로 검증한다.
- 왜 그대로 도는가: 3.0 의 `isaaclab.sensors.ContactSensorCfg` 는 백엔드 팩토리라 Newton 접촉 센서로 자동 분기하고,
  레포가 쓰는 데이터 속성(`net_forces_w_history`, `current_air_time`, `applied_torque`, `joint_acc`, `body_*_w`,
  `root_link_*`)은 Newton `ArticulationData` 에 모두 있다. `randomize_rigid_body_mass`(set_masses) / material /
  `push_by_setting_velocity` 도 지원. 미지원은 tendon 계열과 gravity compensation 뿐.
- 의존성: `newton[sim] 1.2.1` 은 `mujoco~=3.8.0` 을 요구한다. 3.3.2 에서는 `mjtDisableBit.mjDSBL_SPRING` 없음으로
  Newton 매니저 초기화가 실패. venv 를 3.8.1 로 올렸고 `smoke_test_x2_mujoco.py` / `mujoco_viewer` 는 그대로 동작.
- **관절 순서가 다르다.** PhysX 는 BFS(`left_hip_pitch, right_hip_pitch, left_shoulder_pitch, ...`), Newton 은 DFS
  (`left_hip_pitch, left_hip_roll, ..., left_elbow, right_hip_pitch, ...`; 왼다리 6·왼팔 4·오른다리 6·오른팔 4).
  env 는 이름으로 관절 그룹을 찾으므로 학습에는 영향이 없지만, 정책의 obs/action 배열 순서가 달라져 MuJoCo 평가
  스크립트에 `--joint-order newton` 이 필요하다.
- 검증(진짜 Newton): `check_backend` → `NewtonMJWarpManager`, `isaaclab_newton` Articulation/ContactSensor, 비디오
  백엔드 `newton_gl`. 64 env × 3 iter 평지·지형생성 모두 통과. 지형생성 64 env 에서 한 번 `malloc(): unaligned
  tcache chunk detected` 로 코어 덤프가 났으나 재현되지 않음(Newton 1.2.1 beta 로 추정, 장시간 런에서 주시).
  4096 env 본 학습 `logs/x2_walk/2026-09-17_08-49-00_newton`(1.94 s/iter, VRAM 5.4 GB) 진행 중.
- 주의: `legged_lab/terrains/ray_caster.py` 는 PhysX RayCaster 를 상속하므로 height scan 을 켜는 태스크는 Newton
  에서 미검증.
- 부수 수정: torch 2.10 에서 `torch.onnx.export` 기본이 dynamo 경로라 opset 11 다운컨버트가 `CastLike` 에서
  실패 → `legged_lab/utils/exporter.py` 에 `dynamo=False`(검증 완료, 단일 `policy.onnx` 생성).

- **Newton 이 학습되지 않던 원인(2026-09-17 확정, 09-18 검증).** X2 USD 의 관절 DriveAPI 가 강성 0·감쇠 0 이면 Newton 은
  임포트 시 그 관절을 EFFORT 모드(액추에이터 없음)로 분류해 실행 시점 ImplicitActuator 게인이 무시된다 → 0 행동 서 있기에서
  0.46 s 만에 무릎이 접힘. PhysX 는 실행 시점 게인이 드라이브를 만들어 무관. 변환 시 `--joint-stiffness 1.0 --joint-damping 1.0
  --joint-target-type position` 자리표시자를 심는 것으로 해결(에셋 README). Robotis cyclo_lab K1 도 같은 처방.
  09-17 의 Newton 런 두 개는 이 상태로 돈 것이라 `_nodrive` 로 개명·폐기.
- **Newton 전용 설정(09-18, `legged_lab/utils/env_utils/physics.py`).** `use_newton_actuators=True`, 지면 마찰 0.6(MuJoCo 는
  두 콜라이더 마찰을 max 로 합치므로 지면 1.0 이면 로봇 마찰 무작위화가 묻힘; 첫 런은 0.0 으로 돌렸고 mujoco_warp 가
  `friction < MJ_MINMU(1e-5) may cause NaN` 경고를 내서 09-18 오후 1e-4 로 올림; 09-21 `newton_contacts=mujoco` 재학습에서 1e-4 가 첫 반복부터
  전 env NaN 을 내서 로봇 무작위화 하한인 0.6 으로 확정), 접촉 센서 `force_threshold=1.0`(Newton 은
  None→0 N). PhysX 경로 값은 그대로. 진단으로 관절 모드 POSITION·발 마찰 0.60~0.997·지면 0 확인. Newton 모델의 정적
  구 `ft_0`(1 cm, 원점, flags 8)는 FrameView 보조 shape 이며 충돌하지 않는다.
- **변환기 관성 버그(09-18).** Isaac Sim 6.0.1 번들 `urdf-usd-converter` 0.1.3 은 `physics:principalAxes` 를 뒤집어 쓴다
  (0.3.0 에서 수정). 0.3.0 은 `NewtonMassAPI` 스키마가 Kit 6.0.1 의 `omni.usd.schema.newton`(플러그인 이름 `newton`,
  구버전) 과 충돌해 Kit 안에서 못 쓴다(prebundle 교체·PYTHONPATH 로도 불가). 대신 `flatten_usd.py --conjugate-principal-axes`
  로 쿼터니언 켤레를 써 넣고 `check_usd_inertia.py` 로 검산(ok 18 / inverted 0 / composite 3). 크기는 작아(비대각 부호,
  다리 관절 유효 관성 대비 ~2 %) sim2sim 갭의 주원인은 아니다. 기존 PhysX 정책은 재학습하지 않고 기준선으로 둔다.
- Newton 은 시작 시 1/3 가량 `Registered backend 'newton'` 직후 100 % CPU 로 멈춘다(SIGKILL 필요). `~/smoke/retry.sh` 로
  최대 3회 재시도.

PhysX 두 런의 MuJoCo 평가와 영상은 `docs/study/2026-09-17-x2-walk-physx-runs-and-sim2sim.md` 에 있다.
