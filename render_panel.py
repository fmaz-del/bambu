#!/usr/bin/env python3
"""Lit close-up of a decorated face, roughly as the printed part will look.

Rasterises the outer surface, then shades it with a raking light so a shallow
relief actually reads. The view is oriented the way the part is worn: for the
xBloom cover the panel's "up" is -Y, because the wing's holes sit at the
machine's bottom.
"""

import argparse

import matplotlib
import numpy as np
import trimesh

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def surface(mesh, x0, x1, y0, y1, nx, zmax):
    ny = max(2, int(nx * (y1 - y0) / (x1 - x0)))
    xs, ys = np.linspace(x0, x1, nx), np.linspace(y0, y1, ny)
    dx, dy = xs[1] - xs[0], ys[1] - ys[0]
    z = np.full((ny, nx), np.inf)
    for t in mesh.vertices[mesh.faces]:
        if (t[:, 0].max() < x0 or t[:, 0].min() > x1 or t[:, 1].max() < y0
                or t[:, 1].min() > y1 or t[:, 2].min() > zmax):
            continue
        j0 = max(0, int((t[:, 0].min() - x0) // dx)); j1 = min(nx - 1, int((t[:, 0].max() - x0) // dx) + 1)
        i0 = max(0, int((t[:, 1].min() - y0) // dy)); i1 = min(ny - 1, int((t[:, 1].max() - y0) // dy) + 1)
        if j1 < j0 or i1 < i0:
            continue
        gx, gy = np.meshgrid(xs[j0:j1 + 1], ys[i0:i1 + 1])
        (ax_, ay_), (bx_, by_), (cx_, cy_) = t[0, :2], t[1, :2], t[2, :2]
        den = (by_ - cy_) * (ax_ - cx_) + (cx_ - bx_) * (ay_ - cy_)
        if abs(den) < 1e-12:
            continue
        w0 = ((by_ - cy_) * (gx - cx_) + (cx_ - bx_) * (gy - cy_)) / den
        w1 = ((cy_ - ay_) * (gx - cx_) + (ax_ - cx_) * (gy - cy_)) / den
        ins = (w0 >= -1e-9) & (w1 >= -1e-9) & ((1 - w0 - w1) >= -1e-9)
        if not ins.any():
            continue
        zz = w0 * t[0, 2] + w1 * t[1, 2] + (1 - w0 - w1) * t[2, 2]
        blk = z[i0:i1 + 1, j0:j1 + 1]
        np.minimum(blk, np.where(ins, zz, np.inf), out=blk)
    return np.where(np.isinf(z), np.nan, z), dx, dy


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("model")
    p.add_argument("-o", "--out", default="panel.png")
    p.add_argument("--region", type=float, nargs=4, required=True,
                   metavar=("X0", "Y0", "X1", "Y1"))
    p.add_argument("--px", type=int, default=900, help="render width in pixels")
    p.add_argument("--zmax", type=float, default=3.5,
                   help="ignore geometry deeper than this, so the far wall is not drawn")
    args = p.parse_args()

    mesh = trimesh.load(args.model, force="mesh")
    x0, y0, x1, y1 = args.region
    z, dx, dy = surface(mesh, x0, x1, y0, y1, args.px, args.zmax)

    h = (-z)[::-1, :]                      # height above the face; flip so -Y is up
    f = np.nan_to_num(h)
    gy, gx = np.gradient(f, dy, dx)
    lx, ly, lz = -0.5, 0.55, 0.67          # raking light from the upper left
    sh = np.clip(((lz - gx * lx - gy * ly) / np.sqrt(1 + gx ** 2 + gy ** 2) - 0.55) / 0.42, 0, 1)
    amb = np.clip(1 + f / 2.2, 0.55, 1.0)  # deeper cuts sit in shadow
    rgb = plt.cm.pink(np.clip(0.26 + 0.70 * sh * amb, 0, 1))
    rgb[np.isnan(h)] = [1, 1, 1, 1]

    fig, ax = plt.subplots(figsize=(rgb.shape[1] / 150, rgb.shape[0] / 150))
    ax.imshow(rgb, origin="lower", extent=[x0, x1, y0, y1])
    ax.set_aspect("equal"); ax.axis("off")
    plt.tight_layout(pad=0.2)
    plt.savefig(args.out, dpi=150, facecolor="white")
    print(f"wrote {args.out}  ({rgb.shape[1]}x{rgb.shape[0]} px, "
          f"relief {np.nanmin(h):.2f}..{np.nanmax(h):.2f} mm)")


if __name__ == "__main__":
    main()
