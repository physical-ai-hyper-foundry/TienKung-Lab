"""x2_ultra_locked20.urdf 를 0 자세로 조립해 감량한 GLB 로 내보낸다 (① 학습 요청의 URDF 뷰어용)."""
import sys, numpy as np, trimesh, yourdfpy, fast_simplification
urdf, out, ratio = sys.argv[1], sys.argv[2], float(sys.argv[3])
robot = yourdfpy.URDF.load(urdf, build_collision_scene_graph=False, load_collision_meshes=False)
scene = robot.scene  # zero configuration
slim = trimesh.Scene()
tri_in = tri_out = 0
for name, geom in scene.geometry.items():
    T = scene.graph.get(name)[0]
    m = geom.copy(); m.apply_transform(T)
    tri_in += len(m.faces)
    if len(m.faces) > 2000:
        v, f = fast_simplification.simplify(m.vertices.astype(np.float32), m.faces.astype(np.int64), target_reduction=1 - ratio)
        m = trimesh.Trimesh(v, f, process=True)
    tri_out += len(m.faces)
    m.fix_normals()
    m.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
        name="x2_body", baseColorFactor=[225, 228, 233, 255], metallicFactor=0.05, roughnessFactor=0.55))
    slim.add_geometry(m, node_name=name, geom_name=name)
# Z-up(URDF) → Y-up(glTF)
slim.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
slim.export(out, include_normals=True)
print(f"triangles {tri_in} -> {tri_out}, bounds {slim.bounds.round(3).tolist()}")
