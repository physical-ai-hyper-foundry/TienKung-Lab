# 강화학습 파이프라인 페이크 페이지 — 홍보용 캡처 (2026-09-30)

와이어프레임(`docs/ideas/2026-09-18-rl-pipeline-wireframe-handoff.md`, 아티팩트 V77)의 화면 ⓪ · ⓪-b · ⓪-c · ① · ② · ③ · ③-c · ④ · ④-b 를
**실제 Data Library · Model Studio 프론트엔드 안에** 하드코딩된 데모 모드로 만들고, Playwright 로 스크린샷과 흐름 영상을 뽑는다.
아직 개발되지 않은 기능을 미리 보여 주는 자료이므로 API · 백엔드는 없다. 정해진 시나리오 한 줄만 동작하면 된다.

## 0. 결정 (2026-09-30, 사용자)

| 항목 | 결정 |
|---|---|
| 구현 위치 | **A. 실제 레포 데모 브랜치.** `data-library-frontend` · `model-studio/frontend` 각각 `demo/rl-fake-pages` 브랜치. `VITE_DEMO=1` 일 때 인증·API 를 픽스처로 대체 |
| 에이전트 | **2단계.** Main(Fable) 이 공통 계약·데모 골격·통합 검증. Opus 빌더 둘(DL / MS) + Opus 캡처 하나. 빌더는 필요할 때만 Sonnet 을 씀 |
| 캡처 | **Playwright 자동.** 스크린샷 9장 + 흐름 영상. 영상은 **커서 있는 판 · 없는 판** 둘 다 (Playwright 녹화에는 커서가 안 찍히므로 커서 판은 DOM 오버레이 커서를 주입) |
| 대상 | AgiBot X2 Ultra · 태스크 `평지 걷기`(`x2_walk`) 하나 |

## 1. 시나리오 (한 줄 스토리)

두 앱을 넘나드는 흐름이라 **이름·숫자·날짜가 두 앱에서 한 글자도 달라선 안 된다.** 값은 §3 픽스처 상수가 유일한 출처다.

```
[DL] ⓪   작업 목록(2개) → "새 작업" → Step 1 강화학습 카드 → Step 2 기본 정보(로봇 후보 2종으로 좁혀짐) → 작업 만들기
[DL] ⓪-b 작업 목록(3개) — 새 카드 "X2 평지 보행": 보행(파랑) · 강화학습(purple) 태그, "학습 0개"
[DL] ⓪-c 카드 클릭 → 사이드바에 원본·학습 데이터 그룹 없음, 기본 화면 = 학습 관리(빈 상태 카드 → 학습 요청)
[DL] ①   학습 요청: 태스크 드롭다운(평지 걷기 ✓ / 박스 들고 걷기 준비 중 / 스쿼트·들어올리기 준비 중), 오른쪽 요청 요약 + URDF 뷰어 → "학습 요청"
[MS] ②   새 탭 /rl?run_id=… : 배너 · 시뮬 환경 3택(PhysX 만 활성) · 런 이름 · 실행 파라미터 · 보상 함수(2개 값 변경) → "학습 요청"
[MS] ③   학습 실행 현황: x2_walk_20260915 학습 중, 스텝이 1초마다 오르는 티커, 펼친 행(파라미터·로그·Mean reward 차트)
[MS] ③-c "실시간 학습 화면" → 모달에 학습 영상(autoplay·loop·muted)
     ── 시간 건너뛰기: window.__demo.finishRun() 또는 ?demo=finished ──
[DL] ④   학습 관리 목록: x2_walk_20260915 학습 완료, 2026-09-15 13:06 - 2026-09-16 20:41
[DL] ④-b 학습 상세: 개요 4행 · 학습 결과 영상(단독 롤아웃) · 실행 파라미터 · 학습 파라미터(바꾼 2행 위) · 전체 학습 설정 · 학습 로그
```

- ③-b 중지 모달은 요청 범위 밖이라 만들지 않는다(버튼은 그려도 동작 없음).
- 데모 상태는 **메모리 안 스토어** 하나(페이지 새로고침 시 초기화). 작업 생성 → 목록 반영, 학습 요청 → 런 생성, 시간 건너뛰기 → 런 완료 세 가지 전이만 있다.
- 시간 건너뛰기는 캡처 스크립트가 부른다. DL 과 MS 는 다른 origin 이라 상태를 공유하지 않는다 — **DL 은 `?demo=finished` 를 받으면 처음부터 완료 상태로 뜬다.**

## 2. 화면별 완료 기준

각 화면은 와이어프레임 텍스트(스크래치 `wire_w-sNN.txt`)와 인수인계 문서 §2 규칙을 따른다. 아래는 빌더가 체크할 항목만.

| # | 앱 · 경로 | 반드시 보일 것 | 근거 |
|---|---|---|---|
| ⓪ | DL `/projects/{p}/tasks/new` | 2단계 마법사. Step 1 = 카드 2장(모방학습 / 강화학습, 카드마다 "다음 단계에서 받는 것" 한 문장). Step 2(강화) = 작업 이름·유형·설명·대표 이미지·적용 로봇 모델 **만**, 로봇 후보 `AgiBot / X2 Ultra`, `TienKung / TienKung 2 Lite` + 안내문. 왼쪽 세로 스테퍼(강화 2단계) · 우상단 가로 스테퍼 = 기존 `VerticalStepper`/`HorizontalStepper` 재사용 | s02, 인수인계 ⓪ |
| ⓪-b | DL `/projects/{p}/tasks` | 카드 3장. 작업 유형 태그(geekblue) 옆 **학습 유형 태그**(모방학습 cyan · 강화학습 purple). 강화학습 카드는 원본·에피소드·학습 데이터 개수 없이 "학습 N개" 만. 클릭 → 학습 관리 | s03 |
| ⓪-c | DL `/projects/{p}/tasks/{t}/trainings` | 서브메뉴 = 학습(학습 요청·학습 관리) + 설정(작업 설정) 만. 학습이 없으면 빈 카드("학습 요청" 버튼) | s05 |
| ① | DL `…/trainings/request` | 학습 유형 칸 **없음**. "강화학습 태스크" 드롭다운 3항목(2개 준비 중). 오른쪽 "요청 요약": URDF 뷰어 자리(정적 이미지 또는 간단 캔버스) · 로봇 모델 `AgiBot X2 Ultra` "작업 설정에서 지정됨" · 태스크 · 자유도 `20 · 다리 12 + 팔 8 (허리·목·손목 11 잠금)`. 버튼 "학습 요청" → MS 새 탭 | s06 |
| ② | MS `/rl?run_id=…` | 사이드바 "학습 파이프라인 생성" → **모방학습 / 강화학습** 두 항목. 상단 배너 한 줄. 왼쪽: 시뮬레이션 환경 3카드(PhysX 활성, Newton·MuJoCo 비활성 "지원 예정", 세 층 표기) · 런 이름 · 출력 디렉토리 · 강화학습 파라미터(Headless 토글 off, 병렬 환경 4096, 최대 스텝 50000, 체크포인트 간격 1000, Seed 42, Config 미리보기, 고급 설정 접힘). 오른쪽: 보상 함수 8 슬라이더 + 환경 난이도 3 + "기준값으로 되돌리기" + 바꾼 항목 파랗게 + "▷ 학습 요청" | s07 |
| ③ | MS `/runs` | 상단 요약 띠("1개 실행 중 …"). 필터 3 드롭다운(학습 유형 · 학습 기반 그룹 2개 · 상태) + 검색. 표 8열. RL 행 펼침: 로봇·태스크 / 출력 디렉토리 / 현재 진행 / 학습 파라미터 3그룹(바꾼 값 `(기본 …)` 표기) / 실시간 로그 / Mean reward · Mean episode length 차트(recharts, 영어 라벨) / 버튼 줄(중지·TensorBoard·실시간 학습 화면·체크포인트·Config·삭제). IL 행 1개 (ACT 완료) | s08 |
| ③-c | MS 모달 | 제목 `실시간 학습 화면 · x2_walk_20260915`, 우측 `1명 접속 중 · 스텝 N`. 16:9 영상(autoplay loop muted, `public/demo/x2_walk_training.mp4`), 좌상단 `● LIVE`, 좌하단 배지 `Isaac Sim · 4096 envs · 25 fps · 1920×1080`, 하단 안내문 + "새 탭에서 열기 ↗" | s10 |
| ④ | DL `…/trainings` | 필터 줄(학습 일시 전체기간/직접설정 · 학습 대상 · 학습 기반 · 학습 상태) + 정렬 + 초기화. 열: 학습 이름 · **학습 대상** · **학습 기반** · 상태 · 학습 일시. 학습 유형 열·필터 없음, 접두 없음. 하단 선택 바(모델 다운로드 · 삭제) | s11 |
| ④-b | DL `…/trainings/{r}` | 제목 줄 = 상태 점 + 런 이름 + "⤓ 모델 다운로드". **개요** 4행(학습 대상 · 학습 기반 · 학습 일시 · 학습 시간·스텝 ?툴팁). **학습 결과 영상**(남는 폭, HUD `등록된 모델 · 스텝 50,000 · Isaac Sim (PhysX)`, 재생 바에 ⛶ 전체 보기, 아래 회색 한 줄) + 오른쪽 **실행 파라미터** 264px 5행. **학습 파라미터** 표 3열(항목·설정 키·값), 바꾼 2행 위 + 값 아래 회색 `기준값 -200`, 배경색 없음. **전체 학습 설정**(접힘) · **학습 로그**(접힘, 마지막 100줄 안내 + 다운로드) | s14 |

## 3. 픽스처 상수 (두 앱 공통 · 단일 출처)

빌더는 이 값을 **각 앱의 `src/demo/fixtures.ts`** 에 그대로 옮긴다. 값을 바꾸고 싶으면 이 표를 먼저 고친다.

### 3-1. 프로젝트 · 사용자 · 작업
| 키 | 값 |
|---|---|
| 사용자 | `jiwon` (아바타 `J`) |
| 프로젝트 | `휴머노이드 물류` · 적용 현장 `판교 물류센터` |
| 작업 1 (IL, 기존) | `X2 박스 운반` · 물류 · 운반 · 모방학습 · AgiBot・X2 Ultra · "물류 창고에서 테이블 위 박스를 양손으로 들어 선반까지 걸어가 내려놓는다." · 원본 4 · 에피소드 312 · 학습 데이터 2 · 학습 5 · 2026-09-16 업데이트 |
| 작업 2 (IL, 기존) | `X2 컵 옮기기` · 주방 · 모방학습 · AgiBot・X2 Ultra · "주방 시나리오. 테이블 위 컵을 오른손으로 쥐어 싱크대로 이동 및 배치." · 원본 2 · 에피소드 140 · 학습 데이터 1 · 학습 2 · 2026-09-10 업데이트 |
| 작업 3 (RL, ⓪ 에서 생성) | `X2 평지 보행` · 보행 · 강화학습 · AgiBot・X2 Ultra · "속도 명령을 따라 평지를 걷는 보행 정책. 시뮬레이션에서만 학습한다." · 학습 0 → 1 · 2026-09-15 업데이트 |
| 로봇 후보(강화) | `AgiBot / X2 Ultra`, `TienKung / TienKung 2 Lite` (모방일 때 추가: `UBTech / Walker S`, `Unitree / G1`) |
| 태스크 후보(X2) | `평지 걷기 — 속도 명령을 따라 걷는다` ✓ / `박스 들고 걷기` 준비 중 / `스쿼트 · 들어올리기` 준비 중 |
| 자유도 | `20` · `다리 12 + 팔 8 (허리·목·손목 11 잠금)` |
| 에셋 | `x2_ultra_locked20` · `v1.4.0` |

### 3-2. 런
| 키 | 값 |
|---|---|
| run_id | `0199a3f1-8c2d-7c2e` (화면 축약 `0199-…-7c2e`) |
| 런 이름 | `x2_walk_20260915` |
| 출력 디렉토리 | `~/outputs/model_studio/x2_walk_20260915` |
| 학습 기반 (`pipeline_type`) | `ISAAC_SIM_PHYSX` → 표시 `Isaac Sim (PhysX)` · 세 층 `Isaac Sim 6.0 · 물리 PhysX · 솔버 TGS` |
| 시작 | `2026-09-15 13:06` |
| 진행 중 스냅샷(③) | 스텝 `1,240 / 50,000` · reward `-4.10` · ep len `612.4` · `2.3 s/스텝` · 소요 `00:47:31` · 잔여 `31h 12m` · 마지막 ckpt `model_1000.pt` |
| 완료 상태(④·④-b) | 종료 `2026-09-16 20:41` · `31시간 35분 · 50,000 스텝` · 상태 `학습 완료` |
| IL 대조 행(③, MS 만) | `run_x2_pick_v1_20260912` · `0199-…-91af` · IL · ACT · 학습 완료 · `80,000 / 80,000` · loss `0.0412` · `06:12:08` · `2026-09-12 09:40` |

### 3-3. 실행 파라미터
`sim_env: isaac_sim_physx` · `num_envs: 4096` · `max_iterations: 50000` · `headless: false` · `save_interval: 1000` · `seed: 42`

### 3-4. 보상 함수 · 환경 난이도 (항목 · 설정 키 · 기준값 · 설정값 · 슬라이더 범위)
| 항목 | 설정 키 | 기준값 | 설정값 | 범위 |
|---|---|---|---|---|
| 넘어짐 벌점 | `termination_penalty` | -200 | **-300** | -500 ~ -50 |
| 최대 전진 속도 | `lin_vel_x max` (m/s) | 1.0 | **0.8** | 0.3 ~ 1.5 |
| 속도 명령 추종 | `track_lin_vel_xy` | 1.0 | 1.0 | 0.5 ~ 3.0 |
| 회전 명령 추종 | `track_ang_vel_z` | 1.0 | 1.0 | 0.5 ~ 3.0 |
| 골반 수평 유지 | `body_orientation` | -2.0 | -2.0 | -5 ~ -0.5 |
| 동작 부드러움 | `action_rate` | -0.01 | -0.01 | -0.1 ~ -0.001 |
| 에너지 소모 | `energy` | -1e-3 | -1e-3 | -1e-2 ~ -1e-4 |
| 주기 보행 리듬 | `gait_feet_frc_perio` | 1.0 | 1.0 | 0 ~ 2.0 |
| 관절 한계 벌점 | `dof_pos_limits` | -2.0 | -2.0 | -10 ~ -0.5 |
| 외력 푸시 세기 | `push_robot` | 1× | 1× | 0 ~ 2× |
| 바닥 마찰 범위 | `static_friction_range` | 0.6–1.0 | 0.6–1.0 | 0.3 ~ 1.2 |

바꾼 항목은 위 두 줄뿐. ② 에서 파랗게, ③ 펼침에서 `(기본 -200)`, ④-b 에서 값 아래 회색 `기준값 -200`.

### 3-5. 로그 (③ 실시간 · ④-b 마지막 100줄의 앞부분)
```
[STEP] Learning iteration 1240/50000
[INFO] Mean reward: -4.10   Mean episode length: 612.4
[INFO] Episode_Reward/track_lin_vel_xy_exp: 0.41
[INFO] Episode_Reward/termination_penalty: -0.62
[INFO] Episode_Reward/dof_pos_limits: -0.03
[INFO] Iteration time: 2.31s   Total timesteps: 121,896,960
[CMD]  Saved checkpoint model_1000.pt
[STEP] Learning iteration 1241/50000
```
③ 티커는 1초마다 iteration +1, reward 는 -4.10 에서 완만 상승(±0.05 노이즈), 위 8줄 패턴으로 로그를 밀어 넣는다.
④-b 로그는 iteration 49,900 ~ 50,000 구간을 같은 패턴으로 생성(마지막 reward 60.7, ep len 1000.0 — 실제 PhysX 학습 최종값).

### 3-6. 차트 (③ Mean reward · Mean episode length)
iteration 0 → 1,240 구간, 25 포인트. reward −20 → −4.1 로 지수 수렴, ep len 80 → 612 로 상승. 라벨 영어, 오른쪽 축 `(÷50)` 표기는 뺀다(두 축을 쓴다).

### 3-7. 영상 · 이미지
| 용도 | 원본(TienKung-Lab `outputs/`) | 배치 |
|---|---|---|
| ③-c 실시간 학습 화면 | `train_view/x2_walk_training_4096_final_web.mp4` (30 s · 1920×1080 · 17 MB) | MS `public/demo/x2_walk_training.mp4` |
| ④-b 학습 결과 영상 | `compare/isaac_physx_49999_vx0.5.mp4` (10 s · 1280×720 · 1.9 MB) | DL `public/demo/x2_walk_rollout.mp4` |
| ④-b 포스터 · 카드 썸네일 | `train_view/x2_walk_training_4096_final_still.jpg` / 롤아웃 첫 프레임 | 각 `public/demo/` |
| ① URDF 뷰어 | **회전하는 3D(사용자 결정 2026-09-30).** `x2_ultra_locked20.urdf` 를 0 자세로 조립·감량한 GLB(3.8 MB, `tools/demo/urdf_to_glb.py`, 원본 `outputs/fake-pages/assets/`) 를 `@google/model-viewer` 로 자동 회전 + 드래그 회전 + 휠 확대. 포스터는 롤아웃 정지 프레임 | DL `public/demo/x2_ultra_locked20.glb`, `x2_urdf_preview.jpg` |

mp4 는 git 에 넣지 않는다 — 두 브랜치의 `.gitignore` 에 `public/demo/*.mp4` 추가, 복사 스크립트 `tools/demo/copy-assets.sh`(TienKung-Lab 쪽)로 채운다.

## 4. 데모 모드 골격 (코드 인벤토리 반영, 2026-09-30)

두 앱의 봉합 지점이 달라 골격은 **빌더가 각자 1단계로 만든다.** 공통인 것은 규약뿐이다.

공통 규약
- `VITE_DEMO=1` → `import.meta.env.VITE_DEMO === '1'`. 스크립트 `dev:demo` = `VITE_DEMO=1 vite`.
- `src/demo/` 폴더: `fixtures.ts`(§3 상수) · `store.ts`(메모리 상태 + 전이 + `window.__demo = { finishRun(), reset() }`) · `handlers.ts`(가짜 응답) · `install.ts`(`main.tsx` 맨 위에서 데모일 때만 호출).
- `?demo=finished` 를 받으면 스토어를 완료 상태로 초기화. 새 의존성(MSW 등) 금지.
- 기존 페이지는 가짜 응답만으로 뜨게 한다. 새 화면·바뀐 열은 진짜 컴포넌트를 고친다(`isDemo` 분기로 감싸지 않는다 — 데모 브랜치다).

Data Library (`data-library-frontend`, pnpm, Vite **5173**, base **`/library/`** → `http://localhost:5173/library/projects/…`)
- 봉합: axios 인스턴스 3개(`src/api/client.ts` `/library-api/v1`, `authClient.ts` `/authentication`, `storage.ts` `/library-storage`)에 **커스텀 adapter** 를 꽂는다(`instance.defaults.adapter`). 네이티브 `fetch` 2곳(`useAuthImageSrc.ts` 대표 이미지, `client.ts:66` 로그아웃)과 기본 `axios`(로그 다운로드)는 데모에서 `window.fetch` 를 감싸 `/library-api|/library-storage|/authentication` 만 가로챈다.
- 인증: `install.ts` 에서 `useAuthStore.setState({ user: 픽스처, isAuthInitialized: true })` — `initializeSession` 은 이미 초기화돼 있으면 바로 반환한다(`authStore.ts:19`).
- 응답 봉투 `{ success, data }`, 목록은 `ApiPage { content, page, size, totalElements, totalPages }`. `GET /projects`, `/projects/{id}`, `/tasks?projectId=`, `/tasks/{id}`, `/task-categories`, `/robots`, `/source-types`, `POST /tasks`, `/tasks/{id}/training-runs(+/filter-options)`, `/training-runs/{id}`, `/tasks/{id}/training-data`, `/raw-datasets?taskId=`, `/authentication/me` 가 필요한 전부다.
- 타입 확장: `ApiTaskSummary`/`ApiTask` 에 `trainingType: 'IMITATION' | 'REINFORCEMENT'`, `ApiTrainingRunListItem`/`Detail` 에 `pipelineType`, `targetName`(학습 대상), 결과 영상·실행 파라미터·학습 파라미터 필드. 표시 이름 매핑은 `src/utils/` 에 새로.
- Model Studio 링크: `src/config/externalLinks.ts` 의 `MODEL_STUDIO_URL` 이 `/model-studio` 로 하드코딩 → 데모에서 `http://localhost:5174`, 강화학습은 `/rl?run_id=…` 로 여는 함수 추가.
- 폰트 Pretendard 는 npm 패키지로 번들됨(CDN 링크 실패는 무해). Node 24 로 `pnpm dev` 가능.

Model Studio (`model-studio/frontend`, npm, Vite **5174**, base `/`)
- 봉합: `src/api/client.ts:11-36` 의 `request<T>()` 첫 줄에서 데모면 `handlers.ts` 로 분기. `src/api/auth.ts` 의 `fetchSession()` 은 데모면 픽스처 사용자로 `authenticated` 반환. `src/hooks/useWebSocket.ts` 의 `useRunLogsWS` 는 데모면 가짜 에미터(`init` → 로그 8줄 패턴 1초 간격 + `metric`)를 쓴다.
- `PipelineType` 에 `'ISAAC_SIM_PHYSX' | 'ISAAC_SIM_NEWTON' | 'MUJOCO'` 추가, `TrainingRun` 에 `trainingType`, RL 파라미터(실행·보상·난이도), `meanReward`, `meanEpisodeLength`, `metrics` 에 reward·epLen 포인트. `PipelineBadge` 두 벌(`TrainingRuns.tsx:20`, `Dashboard.tsx:11`)에 새 값 라벨.
- `/api` 프록시는 데모에서 안 쓴다(모두 `request()` 에서 끝남). `../VERSION` 은 있어야 한다(있음).

## 5. 역할 분담

| 에이전트 | 범위 | 산출 | 완료 판정 |
|---|---|---|---|
| Main (Fable) | §3 픽스처 · 브랜치 생성 · 에셋 복사 · 통합 검증 · 문서 | 두 레포 데모 브랜치, `public/demo/` 에셋, 이 문서 | 두 빌더 결과를 같이 띄워 §1 흐름이 끝까지 이어짐 |
| Opus · DL 빌더 | 1단계 §4 골격(백엔드 없이 부팅) → 2단계 ⓪ ⓪-b ⓪-c ① ④ ④-b | `data-library-frontend` 커밋 | 6화면이 §2 기준을 충족하고 시나리오 순서로 클릭 이동 가능. 화면마다 스크린샷 1장 첨부 보고 |
| Opus · MS 빌더 | 1단계 §4 골격 → 2단계 ② ③ ③-c + 사이드바 항목 | `model-studio/frontend` 커밋 | 3화면 §2 충족, `?run_id` 로 진입 → 학습 요청 → /runs 에 런 생성 → 모달 재생. 스크린샷 첨부 보고 |
| Opus · 캡처 | Playwright 스크립트 | `tools/demo/capture/` (TienKung-Lab) + `outputs/fake-pages/` | 스크린샷 9장(1440×900, 2x) · 흐름 영상 커서 O/X 2편(mp4) |

빌더 프롬프트에 반드시 넣을 것: 이 문서 경로, 해당 `wire_w-sNN.txt` 원문, 인수인계 §2 해당 절, 픽스처 파일 경로, "기존 컴포넌트·토큰·i18n 을 재사용하고 새 UI 라이브러리를 들이지 말 것", "픽스처 값은 고치지 말고 Main 에 요청할 것".

## 6. 캡처 사양

- 뷰포트 1440×900, `deviceScaleFactor: 2`, 언어 KO, 라이트 테마.
- 스크린샷: 화면마다 1장, 파일명 `NN-<screen>.png` (`00-create-task-step1.png` … `08-training-detail.png`). ③-c · ①-드롭다운 열림 같은 상태는 별도 파일.
- 흐름 영상: 시나리오 §1 을 한 번에. 클릭 사이 700 ms 정지, 스크롤은 부드럽게. Playwright `recordVideo` → webm → ffmpeg 로 mp4(H.264, 30 fps).
  - **커서 없는 판**: 그대로.
  - **커서 있는 판**: `page.addInitScript` 로 흰 테두리 검은 화살표 SVG 커서(`position:fixed; pointer-events:none; z-index:2147483647`)를 주입, `page.mouse.move` 경로를 따라 움직이고 클릭 시 살짝 축소. 두 판은 같은 스크립트를 `--cursor` 플래그로 두 번 돌린다.
- 두 앱은 다른 origin 이므로 하나의 `BrowserContext` 에서 탭 두 개로 진행하고, 새 탭 전환 시 짧은 정지를 둔다.

## 7. 진행 기록

- 2026-09-30: 결정(§0) · 시나리오 · 픽스처 확정. 코드 인벤토리 반영해 §4 봉합 지점·포트·URL 확정. 두 레포에 `demo/rl-fake-pages` 브랜치 생성, `public/demo/` 에셋 복사(`tools/demo/copy-assets.sh`).
- 2026-09-30~10-01: **완료.** 빌더 둘(DL 6화면 · MS 3화면)과 캡처 하네스가 작업 트리에 산출(커밋 없음). 산출물:
  - 스크린샷 15장 `outputs/fake-pages/screens/`(00~08 + 드롭다운·전체 길이 변형), 흐름 영상 `outputs/fake-pages/video/rl-flow.mp4`(73.7 s) · `rl-flow-cursor.mp4`(76.8 s), 시나리오 `tools/demo/capture/scenarios/rl-flow.json`.
  - 3D 뷰어: `@google/model-viewer` + GLB. **감량률 비교 후 40%(63만 삼각형 · 15 MB) 채택** — 12% 는 각진 면·찌꺼기, 원본 37 MB 는 로딩 2배(`outputs/fake-pages/assets/glb_compare_*.png`). 세 버전 모두 `outputs/fake-pages/assets/`.
  - 빌더가 계획과 다르게 한 것: DL 날짜 표기를 앱 전체 `YYYY-MM-DD HH:mm` 로, 상태 `학습 성공`→`학습 완료` 전역 변경, MS 상태 라벨은 제품 사전 그대로 `학습 진행중`(와이어프레임 "학습 중" 아님), DL 에 `?demo=created|running` 추가, "학습 조기 종료" 상태는 enum 에 없어 CANCELED 로 대체.
  - 하네스: headless-shell 은 소프트웨어 GL 이라 3D 가 2 fps → `channel: 'chromium'` 으로 바꿔 GPU 사용. 탭 전환 시 뷰포트 재적용, `window.open` 새 탭은 context `page` 이벤트로 감지.
  - 실행: DL `pnpm dev:demo`(5173) · MS `npm run dev:demo`(5174), 캡처 `cd tools/demo/capture && node flow.mjs --scenario rl-flow.json --out video [--cursor]`.
- 2026-10-01 사용자 검수 반영: **캡처 해상도 1920×1080** 으로 변경(§6 의 1440×900 은 폐기, 이전 결과물은 `outputs/fake-pages/_1440x900/`). ① 뷰어 카드는 URDF/USD 토글을 빼고(토글은 라벨 글자만 바꾸던 장식이었음) **에셋 이름 · 버전만 표기**(`x2_ultra_locked20 · v1.4.0`, ② 배너와 같은 표기). 형식 글자를 남기면 "그럼 GLB 는 뭐냐" 가 되므로 뺌 — 뷰어의 GLB 는 URDF 가 가리키는 STL 40개를 조립·포장한 것이라 새 형상이 아니다. MS `/runs` 표 열 이름 `유형` → **`학습 유형`**, 배지 `RL/IL` → **`강화학습/모방학습`**(열 폭 5%→8%).
- 2026-10-01 2차 검수: ① 3D 뷰어는 한때 자동 회전을 껐다가 **다시 켬**(20°/s, 드래그하면 멈췄다 1.5 s 뒤 재개 — 홍보용엔 도는 쪽이 낫다는 사용자 판단). 영상에서는 하네스가 **드래그 회전·휠 줌을 직접 수행**(`flow.mjs` 에 `drag`·`wheel` 단계 추가, 단독 클립 `video/viewer-only[-cursor].mp4` 로 연출 승인 후 `rl-flow` 에 반영). ④-b **학습 결과 영상 : 실행 파라미터 = 7 : 3**(flex 7/3, 고정 264px 폐기). 스크린샷 `03/03b/08/08b` 재촬영 완료, 영상은 스크린샷 확정 후 재녹화. 하네스 주의: `shot.mjs` 출력 경로는 상대이면 `outputs/fake-pages/` 기준이므로 절대 경로를 쓸 것.
