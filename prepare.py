#!/usr/bin/env python3
"""Turn a photograph into a height map ready to carve.

Cuts the subject out of its background, so the carving is bounded by the
subject's own silhouette instead of a rectangular plaque, then stretches the
local contrast so faces, cloth and feathers read as depth rather than mush.
Output is greyscale on pure white: white is background and gets no cut at all.
"""

import argparse

import cv2
import numpy as np
from PIL import Image


def cutout(path, feather):
    """Alpha mask of the main subject, 0..1."""
    from rembg import new_session, remove
    img = Image.open(path).convert("RGB")
    res = remove(img, session=new_session("u2net"), post_process_mask=True)
    a = np.asarray(res.split()[-1], dtype=np.float32) / 255.0
    if feather > 0:
        k = int(feather) * 2 + 1
        a = cv2.GaussianBlur(a, (k, k), 0)
    return np.asarray(img), np.clip(a, 0, 1)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image")
    p.add_argument("-o", "--out", default="prepared.png")
    p.add_argument("--no-cutout", action="store_true", help="keep the background")
    p.add_argument("--feather", type=int, default=2, help="soften the silhouette, px")
    p.add_argument("--clahe", type=float, default=2.5,
                   help="local contrast strength (0 disables)")
    p.add_argument("--gamma", type=float, default=1.0,
                   help=">1 deepens the shadows, <1 lifts them")
    p.add_argument("--fade-bottom", type=float, default=0.0, metavar="FRAC",
                   help="dissolve this fraction of the subject's height into the "
                        "surface at the bottom, so a cropped bust has no hard edge")
    p.add_argument("--fade-top", type=float, default=0.0, metavar="FRAC")
    p.add_argument("--fade-left", type=float, default=0.0, metavar="FRAC")
    p.add_argument("--fade-right", type=float, default=0.0, metavar="FRAC")
    p.add_argument("--floor", type=float, default=0.06,
                   help="tone the subject never goes below, keeping it clear of the surface")
    args = p.parse_args()

    if args.no_cutout:
        rgb = np.asarray(Image.open(args.image).convert("RGB"))
        alpha = np.ones(rgb.shape[:2], np.float32)
    else:
        rgb, alpha = cutout(args.image, args.feather)

    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if args.clahe > 0:
        g = cv2.createCLAHE(clipLimit=args.clahe, tileGridSize=(8, 8)).apply(g)
    g = g.astype(np.float32) / 255.0

    # stretch using only the subject's own tones, so the background can't skew it
    sel = alpha > 0.5
    if sel.any():
        lo, hi = np.percentile(g[sel], [2, 98])
        g = np.clip((g - lo) / max(hi - lo, 1e-6), 0, 1)
    if args.gamma != 1.0:
        g = g ** args.gamma

    depth = (1.0 - g)                                  # how deep to cut
    depth = args.floor + (1.0 - args.floor) * depth    # keep the subject off the surface
    depth *= alpha                                     # background cuts nothing

    # Dissolve the subject into the surface wherever the photo's own crop cuts it,
    # so a straight frame edge does not read as a wall in the relief.
    sides = (("fade_top", 0, False), ("fade_bottom", 0, True),
             ("fade_left", 1, False), ("fade_right", 1, True))
    for name, axis, from_end in sides:
        frac = getattr(args, name)
        if frac <= 0:
            continue
        idx = np.where(alpha.max(1 - axis) > 0.5)[0]
        if not len(idx):
            continue
        i0, i1 = idx[0], idx[-1]
        n = max(int(frac * max(i1 - i0, 1)), 1)
        ramp = np.ones(depth.shape[axis], np.float32)
        f = np.linspace(0, 1, n, dtype=np.float32)
        if from_end:
            ramp[i1 - n + 1:i1 + 1] = np.minimum(ramp[i1 - n + 1:i1 + 1], f[::-1])
        else:
            ramp[i0:i0 + n] = np.minimum(ramp[i0:i0 + n], f)
        depth *= ramp[:, None] if axis == 0 else ramp[None, :]

    Image.fromarray(((1.0 - depth) * 255).astype(np.uint8), "L").save(args.out)
    print(f"wrote {args.out}  subject covers {100 * (alpha > 0.5).mean():.1f}% of the frame, "
          f"depth range {depth.min():.2f}..{depth.max():.2f}")


if __name__ == "__main__":
    main()
