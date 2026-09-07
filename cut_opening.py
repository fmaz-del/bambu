#!/usr/bin/env python3
"""Cut a rectangular through-opening in a model, preserving the 3MF project.

Used to replace the cover's vent grille with a single clean opening: the cut
spans the grille's outer bounds, so the ribs between the slots go and the
surrounding plate is untouched.
"""

import argparse

import numpy as np
import trimesh

import repair as repair_mod
from emboss import write_threemf


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("model", help="input STL or 3MF")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--rect", type=float, nargs=4, required=True,
                   metavar=("X0", "Y0", "X1", "Y1"), help="opening, in model X/Y mm")
    p.add_argument("--z", type=float, nargs=2, default=(-2.0, 5.0), metavar=("Z0", "Z1"),
                   help="cut through this Z span; keep it clear of other geometry")
    p.add_argument("--repair", action="store_true")
    args = p.parse_args()

    model = trimesh.load(args.model, force="mesh")
    print(f"model:  {len(model.faces)} triangles, volume={model.is_volume}")
    if args.repair or not model.is_volume:
        model = repair_mod.repair(model)

    x0, y0, x1, y1 = args.rect
    z0, z1 = args.z
    lo = np.array([min(x0, x1), min(y0, y1), min(z0, z1)])
    hi = np.array([max(x0, x1), max(y0, y1), max(z0, z1)])

    # refuse to cut where something other than the plate would be caught
    tris = model.vertices[model.faces]
    inside = ((tris[:, :, 0].max(1) > lo[0]) & (tris[:, :, 0].min(1) < hi[0]) &
              (tris[:, :, 1].max(1) > lo[1]) & (tris[:, :, 1].min(1) < hi[1]))
    zs = tris[inside][:, :, 2]
    print(f"cut:    {hi[0]-lo[0]:.2f} x {hi[1]-lo[1]:.2f} mm through Z {lo[2]} .. {hi[2]}")
    print(f"        geometry in that column spans Z {zs.min():.2f} .. {zs.max():.2f} mm")
    if zs.max() > hi[2]:
        print(f"        note: geometry above Z {hi[2]} in this column is left untouched")

    before = model.volume
    result = trimesh.boolean.difference([model, trimesh.creation.box(bounds=np.array([lo, hi]))])
    print(f"        removed {(before - result.volume) / 1000:.2f} cm3")

    if args.out.lower().endswith(".3mf"):
        write_threemf(args.model, args.out, result, len(result.faces))
    else:
        result.export(args.out)
    print(f"wrote:  {args.out} ({len(result.faces)} triangles)")


if __name__ == "__main__":
    main()
