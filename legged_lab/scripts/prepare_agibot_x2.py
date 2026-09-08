# Copyright (c) 2025-2026, The TienKung-Lab Project Developers.
# All rights reserved.
# Distributed under the BSD-3-Clause license.
#
# The AgiBot X2 robot description downloaded by this script comes from
# https://github.com/AgibotTech/agibot_x2_urdf and is licensed under Mulan PSL v2.

"""Prepare the AgiBot X2 asset for Isaac Lab.

Downloads the upstream X2 Ultra description and writes a locomotion variant in which
the waist (3), neck (2) and wrist (6) joints are fixed, leaving exactly 20 actuated
joints -- the same joint budget and topology as TienKung2-lite, so the 20-DoF
assumptions in the AMP motion loaders and sim2sim runner stay valid.

Usage:
    python legged_lab/scripts/prepare_agibot_x2.py
"""

import argparse
import os
import urllib.request
import xml.etree.ElementTree as ET

from legged_lab.assets import ISAAC_ASSET_DIR

REPO_RAW = "https://raw.githubusercontent.com/AgibotTech/agibot_x2_urdf"
REF = "main"
UPSTREAM_DIR = "X2_URDF-v1.4.0"

ASSET_DIR = os.path.join(ISAAC_ASSET_DIR, "agibot_x2")
SOURCE_URDF = os.path.join(ASSET_DIR, "urdf", "x2_ultra_simple_collision.urdf")
OUTPUT_URDF = os.path.join(ASSET_DIR, "urdf", "x2_ultra_locked20.urdf")

# Joints held fixed so the articulation exposes 20 actuated DoF (12 legs + 8 arms).
LOCKED_JOINTS = [
    "waist_yaw_joint",
    "waist_pitch_joint",
    "waist_roll_joint",
    "head_yaw_joint",
    "head_pitch_joint",
    "left_wrist_yaw_joint",
    "left_wrist_pitch_joint",
    "left_wrist_roll_joint",
    "right_wrist_yaw_joint",
    "right_wrist_pitch_joint",
    "right_wrist_roll_joint",
]

EXPECTED_ACTUATED = 20

# (remote path, local path) pairs for the text descriptions.
FILES = [
    (f"{UPSTREAM_DIR}/X2-Ultra_simple_collision.urdf", "urdf/x2_ultra_simple_collision.urdf"),
    (f"{UPSTREAM_DIR}/X2-Ultra.urdf", "urdf/x2_ultra.urdf"),
    (f"{UPSTREAM_DIR}/X2-Ultra.xml", "mjcf/x2_ultra.xml"),
    (f"{UPSTREAM_DIR}/scene.xml", "mjcf/scene.xml"),
]

# The MuJoCo files assume the upstream flat layout; repoint them at ours.
MJCF_PATCHES = [
    ("mjcf/x2_ultra.xml", 'meshdir="meshes/"', 'meshdir="../meshes/"'),
    ("mjcf/scene.xml", 'file="X2-Ultra.xml"', 'file="x2_ultra.xml"'),
]


def download(remote: str, local: str) -> None:
    path = os.path.join(ASSET_DIR, local)
    if os.path.exists(path):
        print(f"  skip (exists) {local}")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    url = f"{REPO_RAW}/{REF}/{remote}"
    urllib.request.urlretrieve(url, path)
    print(f"  fetched      {local}")


def download_meshes() -> None:
    """Fetch the STL meshes referenced by the URDF (~90 MB, git-ignored)."""
    mesh_dir = os.path.join(ASSET_DIR, "meshes")
    os.makedirs(mesh_dir, exist_ok=True)
    names = sorted(
        {
            os.path.basename(m.get("filename"))
            for m in ET.parse(SOURCE_URDF).getroot().findall(".//mesh")
            if m.get("filename")
        }
    )
    for i, name in enumerate(names, 1):
        path = os.path.join(mesh_dir, name)
        if os.path.exists(path):
            continue
        urllib.request.urlretrieve(f"{REPO_RAW}/{REF}/{UPSTREAM_DIR}/meshes/{name}", path)
        print(f"  [{i}/{len(names)}] {name}")
    print(f"  meshes ready ({len(names)} files)")


def patch_mjcf() -> None:
    """Repoint the MuJoCo files at this repository's directory layout (idempotent)."""
    for local, old, new in MJCF_PATCHES:
        path = os.path.join(ASSET_DIR, local)
        text = open(path).read()
        if old in text:
            open(path, "w").write(text.replace(old, new))
            print(f"  patched      {local}")


def write_locked_urdf() -> None:
    """Fix the locked joints and repoint mesh paths at the sibling meshes/ directory."""
    tree = ET.parse(SOURCE_URDF)
    root = tree.getroot()

    found = set()
    for joint in root.findall("joint"):
        if joint.get("name") in LOCKED_JOINTS:
            joint.set("type", "fixed")
            # A fixed joint carries no limit/axis/dynamics.
            for tag in ("limit", "axis", "dynamics"):
                for child in joint.findall(tag):
                    joint.remove(child)
            found.add(joint.get("name"))

    missing = set(LOCKED_JOINTS) - found
    if missing:
        raise RuntimeError(f"joints not present in {SOURCE_URDF}: {sorted(missing)}")

    for mesh in root.findall(".//mesh"):
        filename = mesh.get("filename")
        if filename:
            mesh.set("filename", "../meshes/" + os.path.basename(filename))

    actuated = [j.get("name") for j in root.findall("joint") if j.get("type") in ("revolute", "continuous")]
    if len(actuated) != EXPECTED_ACTUATED:
        raise RuntimeError(f"expected {EXPECTED_ACTUATED} actuated joints, got {len(actuated)}: {actuated}")

    os.makedirs(os.path.dirname(OUTPUT_URDF), exist_ok=True)
    tree.write(OUTPUT_URDF, encoding="utf-8", xml_declaration=True)
    print(f"  wrote        {os.path.relpath(OUTPUT_URDF, ISAAC_ASSET_DIR)}  ({len(actuated)} actuated joints)")
    for name in actuated:
        print(f"      {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-meshes", action="store_true", help="do not download the ~90 MB STL meshes")
    args = parser.parse_args()

    print("Downloading AgiBot X2 description...")
    for remote, local in FILES:
        download(remote, local)
    patch_mjcf()

    if not args.skip_meshes:
        print("Downloading meshes...")
        download_meshes()

    print("Generating 20-DoF locomotion URDF...")
    write_locked_urdf()


if __name__ == "__main__":
    main()
