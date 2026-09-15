---
status: accepted
date: 2026-09-15
deciders: [Jiwon Choe]
---

# ADR-001: 학습 스택을 Isaac Sim 6.0 + Isaac Lab 3.0 으로 이전한다

## Context and Problem Statement

TienKung-Lab 은 Isaac Sim 4.5.0 + Isaac Lab 2.1.0 기준으로 작성돼 있다. 우리는 이 프레임워크로
AgiBot X2 보행 정책을 학습하고, 다음 두 가지를 제품 요구사항으로 갖는다.

1. 사용자가 클릭하면 **학습 진행 중인 Isaac Sim 화면을 브라우저로** 반드시 보여준다.
2. 학습된 모델은 **MuJoCo sim2sim** 으로 사용자가 직접 조작해 본다.

개발 PC 는 RTX 5070 Ti, 운영 PC 는 RTX 5090 (모두 Blackwell) 이다.

## Decision Drivers

- 브라우저 스트리밍은 필수. Isaac Sim 5.1 문서에는 데스크톱 앱(WebRTC Streaming Client)만 있고,
  브라우저용 "Web-Based Streaming Client (Docker Compose)" 는 **6.0.0 문서부터** 등장한다.
  6.1 은 그 뷰어를 React 기반 Web SDK 로 갱신한 수준이다.
- Blackwell GPU 는 CUDA 12.8 이상 PyTorch 가 필요하다. Isaac Lab 2.1 의 기본 torch(2.5.1, cu118)
  로는 돌지 않는다. 5.x 이상은 모두 cu128 계열이라 어느 쪽이든 해결된다.
- 릴리즈된 조합을 쓴다. 미출시 브랜치를 기반으로 하면 API 가 움직인다.
- 마이그레이션 비용. 6.x 에 대응하는 Isaac Lab 3.0 은 2.x 와 호환이 깨진다.

## Considered Options

1. **Isaac Sim 6.0.1 + Isaac Lab 3.0.0-beta2.patch1** — 브라우저 스트리밍 가능, 둘 다 릴리즈됨.
   Isaac Lab 2.1 → 3.0 마이그레이션 필요.
2. **Isaac Sim 6.1.0 + Isaac Lab develop** — 브라우저 스트리밍 가능. Isaac Lab 쪽 6.1 대응이
   아직 develop 브랜치에만 있음 (Python 3.12, torch 2.11, rsl-rl-lib 5.4.1 핀). 마이그레이션은
   1번과 같고, 표적이 움직인다.
3. **Isaac Sim 5.1 + Isaac Lab 2.3.2** — 마이그레이션 거의 없음. 스트리밍은 데스크톱 앱만 가능해
   요구사항 1 을 만족하지 못한다.

## Decision Outcome

**Chosen: 1. Isaac Sim 6.0.1 + Isaac Lab 3.0.0-beta2.patch1**, because 브라우저 스트리밍이 필수
요건이고, 그것을 제공하는 조합 중 유일하게 양쪽 다 릴리즈된 버전이기 때문이다. 6.1 은 Isaac Lab
정식 릴리즈가 따라오면 그때 별도 ADR 로 올린다.

## Consequences

- ✅ Good: 브라우저 스트리밍(Docker Compose 웹 뷰어, 포트 8210)을 학습 중 화면에 그대로 쓸 수 있다.
- ✅ Good: Blackwell 공식 지원 (torch 2.10 + cu128). 5070 Ti / 5090 모두 해당.
- ✅ Good: AgiBot X2 포팅(`feat/agibot-x2-port`)은 이름 기반 설정이라 그대로 유효하다. 내장 rsl_rl
  (AMP) 은 순수 torch 라 영향이 없다. MuJoCo sim2sim 은 Isaac 과 독립이다.
- ⚠️ Bad: Isaac Lab 2.1 → 3.0 마이그레이션. 쿼터니언 WXYZ→XYZW, `.data.*` 가 warp 배열 반환
  (`.torch` 접근자), `write_*_to_sim` 의 `_index`/`_mask` 분리, `--headless`→`--visualizer`,
  `PhysxCfg` 위치 이동, URDF 임포터 재작성. 핵심 3개 파일 약 1,200 줄이 대상이다.
- ⚠️ Bad: 쿼터니언 순서 오류는 에러 없이 조용히 틀린다. 관측(중력 투영)과 AMP 발/손 위치가 어긋나면
  학습이 되지 않으므로 별도 검증 절차가 필요하다.
- ⚠️ Bad: 3.0 은 beta 다. GA 전에 API 가 더 바뀔 수 있다. 버전을 핀하고 올릴 때만 의도적으로 올린다.
- ⚠️ Bad: 웹 뷰어는 Ubuntu 호스트 + Docker 전용이다. Windows/WSL 은 미지원. 운영 PC 는 Ubuntu 여야 한다.
- ⚠️ Bad: Python 3.12 / `uv` 기반 설치로 바뀐다. README 의 설치·USD 변환 절차를 다시 써야 한다.

## More Information

- Isaac Sim 6.0.0 livestream 문서: https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/manual_livestream_clients.html
- Isaac Sim 5.1.0 livestream 문서 (데스크톱 클라이언트만): https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/manual_livestream_clients.html
- Isaac Lab 3.0 마이그레이션 가이드: https://isaac-sim.github.io/IsaacLab/develop/source/migration/migrating_to_isaaclab_3-0.html
- Isaac Lab 릴리즈: https://github.com/isaac-sim/IsaacLab/releases (3.0.0-beta2.patch1 → Isaac Sim 6.0.1)
- 선행 작업: `docs/plan/2026-09-15-agibot-x2-port.md`
- 후속 계획: `docs/plan/2026-09-15-isaaclab-3-migration.md`
