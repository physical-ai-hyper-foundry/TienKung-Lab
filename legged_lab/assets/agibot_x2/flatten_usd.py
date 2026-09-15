# Copyright (c) 2025-2026, The TienKung-Lab Project Developers.
# All rights reserved.
# Licensed under the BSD-3-Clause license.

"""Flatten the link hierarchy of a USD produced by the Isaac Lab 3.0 / Isaac Sim 6.0 URDF importer.

The 6.0 importer authors every child link *under* its parent link (``Geometry/pelvis/left_hip_pitch_link/...``).
Isaac Lab 3.0.0-beta2.patch1 assumes the 2.x layout where all links are siblings of the root
(``activate_contact_sensors`` stops at the first rigid body and ``ContactSensor`` builds a single-level
PhysX pattern), so only the root body gets a contact reporter. See isaac-sim/IsaacLab#5126 (fixed on
``develop`` after beta2.patch1). Until that fix ships, this script moves every rigid body directly under the
``Geometry`` scope, bakes its world pose into its xform, and remaps joint/robot-schema relationships.

Usage (run with the Isaac Lab venv, no Kit app needed)::

    python legged_lab/assets/agibot_x2/flatten_usd.py <in.usda> <out.usd>

Write the output as binary ``.usd``: flattening inlines the mesh payloads, and the ASCII form is ~150 MB.
"""

import argparse

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics


def _remap_path(path: Sdf.Path, mapping: dict[Sdf.Path, Sdf.Path]) -> Sdf.Path:
    prim_path = path.GetPrimPath()
    return path.ReplacePrefix(prim_path, mapping[prim_path]) if prim_path in mapping else path


def _remap_targets(stage: Usd.Stage, mapping: dict[Sdf.Path, Sdf.Path]) -> int:
    """Rewrite relationship targets and attribute connections whose prim path was moved."""
    count = 0
    for prim in stage.Traverse():
        for rel in prim.GetRelationships():
            targets = rel.GetTargets()
            new_targets = [_remap_path(t, mapping) for t in targets]
            if new_targets != targets:
                rel.SetTargets(new_targets)
                count += 1
        for attr in prim.GetAttributes():
            conns = attr.GetConnections()
            new_conns = [_remap_path(c, mapping) for c in conns]
            if new_conns != conns:
                attr.SetConnections(new_conns)
                count += 1
    return count


def flatten(src: str, dst: str) -> list[str]:
    stage = Usd.Stage.Open(src)
    flat_layer = stage.Flatten()
    fstage = Usd.Stage.Open(flat_layer)
    geom = fstage.GetDefaultPrim().GetChild("Geometry")
    if not geom.IsValid():
        raise RuntimeError("Expected a 'Geometry' scope under the default prim (6.0 importer layout).")

    bodies = [p for p in Usd.PrimRange(geom) if p.HasAPI(UsdPhysics.RigidBodyAPI)]
    nested = [p for p in bodies if p.GetParent() != geom]
    xf_cache = UsdGeom.XformCache()
    geom_world_inv = xf_cache.GetLocalToWorldTransform(geom).GetInverse()
    local_to_geom = {p.GetPath(): xf_cache.GetLocalToWorldTransform(p) * geom_world_inv for p in nested}

    # full old->new path mapping (a prim's new prefix is that of its nearest rigid-body ancestor)
    body_new_path = {p.GetPath(): geom.GetPath().AppendChild(p.GetName()) for p in bodies}
    mapping: dict[Sdf.Path, Sdf.Path] = {}
    for prim in Usd.PrimRange(geom):
        path = prim.GetPath()
        for ancestor in [path] + list(path.GetAncestorsRange())[1:]:
            if ancestor in body_new_path:
                new = path.ReplacePrefix(ancestor, body_new_path[ancestor])
                if new != path:
                    mapping[path] = new
                break

    # move deepest first so descendants are already relocated when their parent moves
    for prim in sorted(nested, key=lambda p: -p.GetPath().pathElementCount):
        old, new = prim.GetPath(), body_new_path[prim.GetPath()]
        if fstage.GetPrimAtPath(new).IsValid():
            raise RuntimeError(f"Name collision while moving {old} -> {new}")
        edit = Sdf.BatchNamespaceEdit()
        edit.Add(old, new)
        if not flat_layer.Apply(edit):
            raise RuntimeError(f"Namespace edit failed: {old} -> {new}")
        moved = fstage.GetPrimAtPath(new)
        mat = local_to_geom[old]
        translate = mat.ExtractTranslation()
        orient = mat.ExtractRotationQuat()
        moved.GetAttribute("xformOp:translate").Set(Gf.Vec3d(translate))
        orient_attr = moved.GetAttribute("xformOp:orient")
        orient_attr.Set(Gf.Quatf(orient) if orient_attr.GetTypeName() == Sdf.ValueTypeNames.Quatf else orient)
        scale = moved.GetAttribute("xformOp:scale")
        if scale and not Gf.IsClose(Gf.Vec3d(scale.Get()), Gf.Vec3d(1.0), 1e-6):
            raise RuntimeError(f"Non-unit scale on {old} is not supported")

    n_remap = _remap_targets(fstage, mapping)
    flat_layer.Export(dst)
    return [
        f"moved {len(nested)} of {len(bodies)} rigid bodies under {geom.GetPath()}",
        f"remapped {n_remap} relationships/connections",
        f"wrote {dst}",
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("src", help="Interface .usda written by convert_urdf.py")
    parser.add_argument("dst", help="Output single-layer .usd (binary)")
    args = parser.parse_args()
    for line in flatten(args.src, args.dst):
        print(line)
