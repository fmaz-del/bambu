#!/usr/bin/env python3
"""Emboss (raise) or engrave (cut) a picture onto one face of an STL or 3MF model.

The image becomes a height map, which is turned into a closed solid and
booleaned onto the chosen face.  Background pixels get zero height, so they stay
buried inside the part -- only the ink shows up as relief, never a raised slab.

A 3MF in, 3MF out keeps the original Bambu Studio project intact (print
profiles, plate layout, thumbnails); only the object's mesh is replaced.

Example
-------
    python3 emboss.py cover.3mf logo.png -o cover_logo.3mf \
        --face bottom --region 51.8 16.6 135.0 232.3 --depth 0.6 --preview p.png
"""

import argparse
import shutil
import sys
import zipfile
from xml.etree import ElementTree as ET

import numpy as np
import trimesh
from PIL import Image, ImageOps

import repair as repair_mod

# Outward normal and image "up" vector for each named face, in model space.
# The horizontal image axis is u = cross(-normal, up): what you see standing
# outside the part and looking straight at that face.
FACES = {
    "front":  ((0, -1, 0), (0, 0, 1)),
    "back":   ((0, 1, 0), (0, 0, 1)),
    "left":   ((-1, 0, 0), (0, 0, 1)),
    "right":  ((1, 0, 0), (0, 0, 1)),
    "top":    ((0, 0, 1), (0, 1, 0)),
    "bottom": ((0, 0, -1), (0, -1, 0)),
}

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
PROD = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"


# --------------------------------------------------------------------------- #
# image -> height map
# --------------------------------------------------------------------------- #

def load_heightmap(path, max_px, invert, threshold, blur, crop, contrast=False):
    """Return (h, crop_frac) where h is in [0, 1]; 1 = full relief, 0 = background."""
    img = Image.open(path)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
        flat.alpha_composite(img)                     # transparent -> background
        img = flat
    img = ImageOps.exif_transpose(img).convert("L")

    if max(img.size) > max_px:
        s = max_px / max(img.size)
        img = img.resize((max(2, round(img.width * s)), max(2, round(img.height * s))),
                         Image.LANCZOS)
    if blur > 0:
        from PIL import ImageFilter
        img = img.filter(ImageFilter.GaussianBlur(blur))

    if contrast:
        img = ImageOps.autocontrast(img, cutoff=1)

    g = np.asarray(img, dtype=np.float64) / 255.0
    if contrast:                                      # spread the tones over the full depth
        lo, hi = np.percentile(g, [1, 99])
        g = np.clip((g - lo) / max(hi - lo, 1e-6), 0, 1)
    h = g if invert else 1.0 - g                      # default: dark ink is the feature
    if threshold is not None:
        h = (h >= threshold).astype(np.float64)
    h = np.clip(h, 0.0, 1.0)

    box = (0.0, 0.0, 1.0, 1.0)                        # u0, v0, u1, v1 as fractions
    if crop:
        ink = h > 0.02
        if ink.any():
            rows, cols = np.where(ink.any(1))[0], np.where(ink.any(0))[0]
            r0, r1 = max(0, rows[0] - 1), min(h.shape[0] - 1, rows[-1] + 1)
            c0, c1 = max(0, cols[0] - 1), min(h.shape[1] - 1, cols[-1] + 1)
            H, W = h.shape
            box = (c0 / W, r0 / H, (c1 + 1) / W, (r1 + 1) / H)
            h = h[r0:r1 + 1, c0:c1 + 1]
    return h, box


# --------------------------------------------------------------------------- #
# height map -> closed solid
# --------------------------------------------------------------------------- #

def build_relief(height, size_u, size_v, base):
    """Closed solid whose top surface follows `height`, with a flat bottom at -base."""
    ny, nx = height.shape
    us = np.linspace(-size_u / 2.0, size_u / 2.0, nx)
    vs = np.linspace(size_v / 2.0, -size_v / 2.0, ny)      # image row 0 at the top
    U, V = np.meshgrid(us, vs)

    n = nx * ny
    verts = np.vstack([
        np.stack([U, V, height], -1).reshape(-1, 3),
        np.stack([U, V, np.full(height.shape, -base)], -1).reshape(-1, 3),
    ])

    idx = np.arange(n).reshape(ny, nx)
    a, b, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
    top_f = np.concatenate([np.stack([c, d, a], -1).reshape(-1, 3),
                            np.stack([d, b, a], -1).reshape(-1, 3)])

    def skirt(border):
        p0, p1 = border[:-1], border[1:]
        return np.concatenate([np.stack([p0, p1, p1 + n], -1),
                               np.stack([p0, p1 + n, p0 + n], -1)])

    faces = np.concatenate([top_f, top_f[:, ::-1] + n,
                            skirt(idx[0, :]), skirt(idx[-1, :]),
                            skirt(idx[:, 0]), skirt(idx[:, -1])])

    mesh = trimesh.Trimesh(verts, faces, process=False)
    mesh.merge_vertices()
    trimesh.repair.fix_normals(mesh)          # consistent outward winding
    return mesh


# --------------------------------------------------------------------------- #
# face geometry
# --------------------------------------------------------------------------- #

def face_frame(bounds, face):
    """Centre of that bbox face plus the u / v / normal axes, in model space."""
    normal, up = (np.array(v, float) for v in FACES[face])
    u = np.cross(-normal, up)
    axis = int(np.argmax(np.abs(normal)))
    lo, hi = bounds
    origin = (lo + hi) / 2.0
    origin[axis] = hi[axis] if normal[axis] > 0 else lo[axis]
    return origin, u, up, normal


def inplane_axes(u, v):
    """Which model axes the face's u and v run along, and with which sign."""
    return (int(np.argmax(np.abs(u))), float(np.sign(u[np.argmax(np.abs(u))])),
            int(np.argmax(np.abs(v))), float(np.sign(v[np.argmax(np.abs(v))])))


# --------------------------------------------------------------------------- #
# 3MF round-trip
# --------------------------------------------------------------------------- #

def parse_transform(text):
    """3MF stores a row-major 4x3; points transform as p' = p . M + t."""
    n = [float(x) for x in text.split()]
    M = np.array(n[:9], float).reshape(3, 3)
    t = np.array(n[9:12], float)
    return M, t


def threemf_object_transform(zf):
    """Local object coords -> plate coords, following build item -> component."""
    root = ET.fromstring(zf.read("3D/3dmodel.model"))
    item = root.find(f"{CORE}build/{CORE}item")
    M, t = (np.eye(3), np.zeros(3))
    if item is not None and item.get("transform"):
        M, t = parse_transform(item.get("transform"))
    target = item.get("objectid") if item is not None else None

    path, obj_id = None, target
    for obj in root.findall(f"{CORE}resources/{CORE}object"):
        if obj.get("id") != target:
            continue
        comp = obj.find(f"{CORE}components/{CORE}component")
        if comp is not None:
            path, obj_id = comp.get(f"{PROD}path"), comp.get("objectid")
            if comp.get("transform"):
                Mc, tc = parse_transform(comp.get("transform"))
                t = tc @ M + t              # compose: (p.Mc + tc).M + t
                M = Mc @ M
    return M, t, (path.lstrip("/") if path else None), obj_id


def write_threemf(src, dst, mesh, face_count):
    """Copy the project verbatim, swapping in the new mesh (in local coords)."""
    with zipfile.ZipFile(src) as zf:
        M, t, path, obj_id = threemf_object_transform(zf)
        if path is None:
            raise RuntimeError("no component object found in 3dmodel.model")
        local = (mesh.vertices - t) @ np.linalg.inv(M)

        rows = ['<?xml version="1.0" encoding="UTF-8"?>']
        old = ET.fromstring(zf.read(path))
        obj = next(o for o in old.findall(f"{CORE}resources/{CORE}object")
                   if o.get("id") == obj_id)
        # ElementTree hands back namespaced attributes in Clark notation
        # ("{uri}UUID"), which is not valid XML to write straight out again.
        def qname(k):
            return f"p:{k[len(PROD):]}" if k.startswith(PROD) else (
                f"BambuStudio:{k.split('}')[-1]}" if k.startswith("{http://schemas.bambulab.com")
                else k.split("}")[-1] if k.startswith("{") else k)
        attrs = " ".join(f'{qname(k)}="{v}"' for k, v in obj.attrib.items())
        rows.append(
            '<model unit="millimeter" xml:lang="en-US" '
            'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
            'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
            'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
            'requiredextensions="p">')
        rows.append(' <metadata name="BambuStudio:3mfVersion">1</metadata>')
        rows.append(f' <resources>\n  <object {attrs}>\n   <mesh>\n    <vertices>')
        rows += [f'     <vertex x="{x:.7f}" y="{y:.7f}" z="{z:.7f}"/>' for x, y, z in local]
        rows.append('    </vertices>\n    <triangles>')
        rows += [f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mesh.faces]
        rows.append('    </triangles>\n   </mesh>\n  </object>\n </resources>\n <build/>\n</model>')
        obj_xml = "\n".join(rows).encode()

        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as out:
            for info in zf.infolist():
                data = zf.read(info.filename)
                if info.filename == path:
                    data = obj_xml
                elif info.filename == "Metadata/model_settings.config":
                    text = data.decode()
                    for old_n in set(__import__("re").findall(r'face_count="(\d+)"', text)):
                        text = text.replace(f'face_count="{old_n}"', f'face_count="{face_count}"')
                    data = text.encode()
                out.writestr(info, data)


# --------------------------------------------------------------------------- #
# preview
# --------------------------------------------------------------------------- #

def render_face(mesh, face, path, px=700):
    """Rasterise the decorated face to a PNG so placement can be eyeballed."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _, u, v, normal = face_frame(mesh.bounds, face)
    R = np.column_stack([u, v, normal])
    P = mesh.vertices @ R                       # x=u, y=v, z=height above the face
    tris = P[mesh.faces]
    lo, hi = P.min(0), P.max(0)
    nx = px
    ny = max(2, int(px * (hi[1] - lo[1]) / max(hi[0] - lo[0], 1e-9)))
    xs = np.linspace(lo[0], hi[0], nx); ys = np.linspace(lo[1], hi[1], ny)
    dx, dy = xs[1] - xs[0], ys[1] - ys[0]
    Z = np.full((ny, nx), np.inf)

    for t in tris:
        j0 = max(0, int((t[:, 0].min() - xs[0]) // dx)); j1 = min(nx - 1, int((t[:, 0].max() - xs[0]) // dx) + 1)
        i0 = max(0, int((t[:, 1].min() - ys[0]) // dy)); i1 = min(ny - 1, int((t[:, 1].max() - ys[0]) // dy) + 1)
        if j1 < j0 or i1 < i0:
            continue
        gx, gy = np.meshgrid(xs[j0:j1 + 1], ys[i0:i1 + 1])
        (ax_, ay_), (bx_, by_), (cx_, cy_) = t[0, :2], t[1, :2], t[2, :2]
        den = (by_ - cy_) * (ax_ - cx_) + (cx_ - bx_) * (ay_ - cy_)
        if abs(den) < 1e-12:
            continue
        w0 = ((by_ - cy_) * (gx - cx_) + (cx_ - bx_) * (gy - cy_)) / den
        w1 = ((cy_ - ay_) * (gx - cx_) + (ax_ - cx_) * (gy - cy_)) / den
        w2 = 1 - w0 - w1
        ins = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if not ins.any():
            continue
        z = -(w0 * t[0, 2] + w1 * t[1, 2] + w2 * t[2, 2])   # distance toward the viewer
        blk = Z[i0:i1 + 1, j0:j1 + 1]
        np.minimum(blk, np.where(ins, z, np.inf), out=blk)

    H = np.where(np.isinf(Z), np.nan, -Z)          # height above the face, mm
    H -= np.nanmedian(H)
    F = np.nan_to_num(H)
    gy, gx = np.gradient(F, dy, dx)                 # surface slope
    lx, ly, lz = -0.55, 0.55, 0.63                  # light from the upper left
    shade = (lz - gx * lx - gy * ly) / np.sqrt(1 + gx ** 2 + gy ** 2)
    shade = np.clip((shade - 0.55) / 0.5, 0, 1) * 0.75 + 0.22
    shade[np.isnan(H)] = 1.0                        # holes read as background

    fig, ax = plt.subplots(1, 2, figsize=(2 * nx / 105, ny / 105))
    ax[0].imshow(shade, origin="lower", extent=[xs[0], xs[-1], ys[0], ys[-1]],
                 cmap="gray", vmin=0, vmax=1)
    ax[0].set_title(f"{face} face, lit from the upper left")
    lo_h, hi_h = np.nanpercentile(H, 0.5), np.nanpercentile(H, 99.5)
    im = ax[1].imshow(H, origin="lower", extent=[xs[0], xs[-1], ys[0], ys[-1]],
                      cmap="magma", vmin=lo_h, vmax=hi_h if hi_h > lo_h else lo_h + 0.01)
    ax[1].set_title("relief height, mm"); plt.colorbar(im, ax=ax[1], shrink=.6)
    for a in ax:
        a.set_aspect("equal"); a.set_xlabel("u, mm"); a.set_ylabel("v, mm")
    plt.tight_layout(); plt.savefig(path, dpi=100); plt.close(fig)


# --------------------------------------------------------------------------- #

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("model", help="input STL or 3MF")
    p.add_argument("image", help="picture to apply")
    p.add_argument("-o", "--out", default=None, help="output STL or 3MF")
    p.add_argument("--face", default="front", choices=sorted(FACES))
    p.add_argument("--mode", default="emboss", choices=["emboss", "engrave"])
    p.add_argument("--depth", type=float, default=0.8, help="relief height / cut depth, mm")
    p.add_argument("--region", type=float, nargs=4, metavar=("A0", "B0", "A1", "B1"),
                   default=None, help="fit inside this rectangle, in the two model axes "
                                      "that lie in the face (e.g. X and Y for top/bottom)")
    p.add_argument("--margin", type=float, default=8.0, help="mm kept clear inside --region")
    p.add_argument("--width", type=float, default=None, help="image width in mm (overrides fit)")
    p.add_argument("--height", type=float, default=None, help="image height in mm")
    p.add_argument("--offset-x", type=float, default=0.0, help="shift along +u, mm")
    p.add_argument("--offset-y", type=float, default=0.0, help="shift along +v, mm")
    p.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270],
                   help="rotate the picture on the face, degrees CCW")
    p.add_argument("--invert", action="store_true", help="raise light pixels, not dark ones")
    p.add_argument("--threshold", type=float, default=None, metavar="0..1",
                   help="binarise for a crisp flat-top logo")
    p.add_argument("--blur", type=float, default=0.0, help="Gaussian blur, pixels")
    p.add_argument("--no-crop", action="store_true", help="keep the image's blank margins")
    p.add_argument("--keep-framing", action="store_true",
                   help="honour the subject's off-centre position in the source picture")
    p.add_argument("--resolution", type=int, default=220,
                   help="pixels along the picture's longest side (mesh density)")
    p.add_argument("--embed", type=float, default=0.6,
                   help="mm the relief base is sunk into the part for a clean join")
    p.add_argument("--flatten", type=float, default=0.0, metavar="MM",
                   help="fill --region flush to the face plane to this depth before "
                        "applying the picture, clearing any old surface decoration")
    p.add_argument("--repair", action="store_true",
                   help="clean the mesh into one watertight solid first (needed to engrave)")
    p.add_argument("--contrast", action="store_true",
                   help="stretch the picture's tones to use the full depth (for photos)")
    p.add_argument("--preview", default=None, help="write a PNG preview of the face")
    p.add_argument("--no-boolean", action="store_true",
                   help="merge shells instead of a boolean (emboss only)")
    args = p.parse_args()

    model = trimesh.load(args.model, force="mesh")
    print(f"model:  {len(model.faces)} triangles, bounds "
          f"{np.round(model.bounds[0], 2).tolist()} .. {np.round(model.bounds[1], 2).tolist()}")
    if args.repair:
        print("  repairing into a single solid")
        model = repair_mod.repair(model)
    elif not model.is_volume:
        print("  note: mesh is not a closed volume; pass --repair to fix it")

    origin, u, v, normal = face_frame(model.bounds, args.face)
    ua, us_, va, vs_ = inplane_axes(u, v)
    span = model.bounds[1] - model.bounds[0]
    print(f"face:   {args.face}: u=+-{'XYZ'[ua]}, v=+-{'XYZ'[va]}, "
          f"{span[ua]:.1f} x {span[va]:.1f} mm, plane at {'XYZ'[int(np.argmax(abs(normal)))]}"
          f"={origin[int(np.argmax(abs(normal)))]:.2f}")

    hm, box = load_heightmap(args.image, args.resolution, args.invert,
                             args.threshold, args.blur,
                             not args.no_crop, args.contrast)
    if args.rotate:
        hm = np.rot90(hm, args.rotate // 90)
        if args.rotate in (90, 270):
            box = (box[1], box[0], box[3], box[2])
    ny, nx = hm.shape

    # available rectangle on the face, in face (u, v) coordinates
    if args.region:
        a0, b0, a1, b1 = args.region
        ac, bc = (a0 + a1) / 2, (b0 + b1) / 2
        avail_u, avail_v = abs(a1 - a0) - 2 * args.margin, abs(b1 - b0) - 2 * args.margin
        cu = us_ * (ac - origin[ua]); cv = vs_ * (bc - origin[va])
    else:
        avail_u, avail_v = span[ua] * 0.6, span[va] * 0.6
        cu = cv = 0.0
    if avail_u <= 0 or avail_v <= 0:
        sys.exit("--margin leaves no room inside --region")

    # size the *cropped* picture so the full (uncropped) picture would fit the region
    full_u, full_v = box[2] - box[0], box[3] - box[1]
    if args.width or args.height:
        size_u = args.width if args.width else args.height * (nx / ny)
        size_v = args.height if args.height else size_u * (ny / nx)
    else:
        scale = min(avail_u / (nx / full_u), avail_v / (ny / full_v))
        size_u, size_v = nx * scale, ny * scale
    if args.keep_framing:
        # leave the subject where it sat inside the original picture
        cu += ((box[0] + box[2]) / 2 - 0.5) * size_u / full_u
        cv -= ((box[1] + box[3]) / 2 - 0.5) * size_v / full_v
    cu += args.offset_x; cv += args.offset_y

    print(f"image:  {nx} x {ny} px -> {size_u:.2f} x {size_v:.2f} mm, "
          f"centre offset ({cu:+.2f}, {cv:+.2f}) mm, {args.mode} {args.depth} mm")
    if args.region and (size_u > avail_u + 1e-6 or size_v > avail_v + 1e-6):
        print("  warning: picture overflows the region")

    if args.flatten:
        if not args.region:
            sys.exit("--flatten needs --region")
        naxis = int(np.argmax(np.abs(normal)))
        a0, b0, a1, b1 = args.region
        lo = np.empty(3); hi = np.empty(3)
        lo[ua], hi[ua] = min(a0, a1), max(a0, a1)
        lo[va], hi[va] = min(b0, b1), max(b0, b1)
        plane = origin[naxis]
        inward = plane - normal[naxis] * args.flatten
        lo[naxis], hi[naxis] = min(plane, inward), max(plane, inward)
        slab = trimesh.creation.box(bounds=np.array([lo, hi]))
        print(f"flatten: filling {hi[ua] - lo[ua]:.1f} x {hi[va] - lo[va]:.1f} mm "
              f"to {args.flatten} mm deep")
        model = trimesh.boolean.union([model, slab])

    if args.mode == "emboss":
        relief = build_relief(hm * args.depth, size_u, size_v, args.embed)
    else:
        # mirrored through the face plane: the cut runs inward, the flat part of
        # the tool sticks out of the model and removes nothing.
        relief = build_relief(-hm * args.depth, size_u, size_v, -args.embed)

    frame = np.eye(4)
    frame[:3, 0], frame[:3, 1], frame[:3, 2] = u, v, normal
    frame[:3, 3] = origin + u * cu + v * cv
    relief.apply_transform(frame)

    if args.no_boolean:
        if args.mode == "engrave":
            sys.exit("--no-boolean cannot engrave")
        result = trimesh.util.concatenate([model, relief])
    else:
        try:
            result = (trimesh.boolean.union([model, relief]) if args.mode == "emboss"
                      else trimesh.boolean.difference([model, relief]))
        except Exception as exc:                              # noqa: BLE001
            if args.mode == "engrave":
                raise
            print(f"  boolean failed ({exc}); merging shells instead")
            result = trimesh.util.concatenate([model, relief])

    out = args.out or args.model.rsplit(".", 1)[0] + "_image.stl"
    if out.lower().endswith(".3mf"):
        if not args.model.lower().endswith(".3mf"):
            sys.exit("3MF output needs a 3MF input to copy the project from")
        write_threemf(args.model, out, result, len(result.faces))
    else:
        result.export(out)
    print(f"wrote:  {out} ({len(result.faces)} triangles, watertight={result.is_watertight})")

    if args.preview:
        render_face(result, args.face, args.preview)
        print(f"wrote:  {args.preview}")


if __name__ == "__main__":
    main()
