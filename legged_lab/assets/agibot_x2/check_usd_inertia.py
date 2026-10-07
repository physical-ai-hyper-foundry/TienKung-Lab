# Copyright (c) 2025-2026, The TienKung-Lab Project Developers.
# All rights reserved.
# Licensed under the BSD-3-Clause license.

"""Check that the principal axes authored in a converted USD reconstruct the URDF inertia tensors.

``urdf-usd-converter`` < 0.3.0 (bundled with Isaac Sim 6.0.x as 0.1.x) writes ``physics:principalAxes`` with the
inverse orientation for links whose products of inertia are non-zero: the eigenvalues are right, but
``R * diag * R^T`` gives the transposed rotation of the URDF tensor. This script prints, per link, which
reconstruction matches the URDF so a regenerated asset can be verified.

Usage (Isaac Lab venv, no Kit app needed)::

    python legged_lab/assets/agibot_x2/check_usd_inertia.py <robot.urdf> <robot.usd>

Links merged by ``--merge-joints`` (fixed-joint children folded into the parent) match neither form because the
URDF link alone is not the composite body; they are reported as ``composite``.
"""

import argparse
import xml.etree.ElementTree as ET

import numpy as np
from pxr import Usd, UsdPhysics


def urdf_inertias(path: str) -> dict[str, np.ndarray]:
    out = {}
    for link in ET.parse(path).getroot().iter("link"):
        inertia = link.find("inertial/inertia")
        if inertia is None:
            continue
        v = {k: float(inertia.get(k)) for k in ("ixx", "ixy", "ixz", "iyy", "iyz", "izz")}
        out[link.get("name")] = np.array(
            [[v["ixx"], v["ixy"], v["ixz"]], [v["ixy"], v["iyy"], v["iyz"]], [v["ixz"], v["iyz"], v["izz"]]]
        )
    return out


def quat_to_matrix(q) -> np.ndarray:
    w, (x, y, z) = q.GetReal(), q.GetImaginary()
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("urdf")
    parser.add_argument("usd")
    parser.add_argument("--rtol", type=float, default=1e-3, help="Match tolerance relative to max |I| of the link.")
    args = parser.parse_args()

    urdf = urdf_inertias(args.urdf)
    stage = Usd.Stage.Open(args.usd)
    counts = {"ok": 0, "inverted": 0, "composite": 0}
    for prim in stage.Traverse():
        if not prim.HasAPI(UsdPhysics.MassAPI) or prim.GetName() not in urdf:
            continue
        mass_api = UsdPhysics.MassAPI(prim)
        diag = mass_api.GetDiagonalInertiaAttr().Get()
        quat = mass_api.GetPrincipalAxesAttr().Get()
        if diag is None or quat is None:
            continue
        ref = urdf[prim.GetName()]
        tol = args.rtol * np.abs(ref).max()
        d = np.diag(diag)
        r = quat_to_matrix(quat)
        err_fwd = np.abs(r @ d @ r.T - ref).max()
        err_inv = np.abs(r.T @ d @ r - ref).max()
        if err_fwd <= tol:
            verdict = "ok"
        elif err_inv <= tol:
            verdict = "inverted"
        else:
            verdict = "composite"
        counts[verdict] += 1
        print(f"{verdict:9s} {prim.GetName():28s} R*D*R^T err={err_fwd:.2e}  R^T*D*R err={err_inv:.2e}")
    print(f"\nok={counts['ok']} inverted={counts['inverted']} composite(merged, not comparable)={counts['composite']}")
    if counts["inverted"]:
        raise SystemExit("USD principal axes are inverted: regenerate with urdf-usd-converter >= 0.3.0")


if __name__ == "__main__":
    main()
