#!/bin/bash
# 페이크 페이지용 영상·이미지를 두 프론트엔드의 public/demo/ 로 복사한다 (mp4 는 git 에 넣지 않는다).
# 출처: docs/plan/2026-09-30-rl-fake-pages.md §3-7
set -e
T="$(cd "$(dirname "$0")/../.." && pwd)"
F="$T/../00_physical_ai_hyper_foundry"
DL="$F/data-library-frontend/public/demo"; MS="$F/model-studio/frontend/public/demo"
mkdir -p "$DL" "$MS"
cp "$T/outputs/train_view/x2_walk_training_4096_final_web.mp4"  "$MS/x2_walk_training.mp4"
cp "$T/outputs/train_view/x2_walk_training_4096_final_still.jpg" "$MS/x2_walk_training_poster.jpg"
cp "$T/outputs/compare/isaac_physx_49999_vx0.5.mp4"               "$DL/x2_walk_rollout.mp4"
ffmpeg -v error -y -ss 4 -i "$T/outputs/compare/isaac_physx_49999_vx0.5.mp4" -frames:v 1 -q:v 3 "$DL/x2_walk_rollout_poster.jpg"
ffmpeg -v error -y -ss 0.2 -i "$T/outputs/compare/isaac_physx_49999_vx0.5.mp4" -frames:v 1 -vf "scale=960:-1" -q:v 3 "$DL/x2_urdf_preview.jpg"
cp "$T/outputs/train_view/x2_walk_training_4096_final_still.jpg" "$DL/x2_walk_task_thumb.jpg"
# ① URDF 뷰어용 GLB: tools/demo/urdf_to_glb.py 로 만든다 (uv run --with trimesh --with yourdfpy --with fast_simplification --with numpy --with lxml --with pillow python tools/demo/urdf_to_glb.py <urdf> <out.glb> 0.4)  # 0.12 는 각진 면·찌꺼기가 보여 0.4 로 확정 (outputs/fake-pages/assets/glb_compare_*.png)
cp "$T/outputs/fake-pages/assets/x2_ultra_locked20.glb" "$DL/x2_ultra_locked20.glb"
ls -la "$DL" "$MS"
