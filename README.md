# xBloom face cover — picture embossing

Tooling to put a picture on the front of the xBloom Studio cover
(`xbloom_face_v1.5_.3mf`), or on any other STL/3MF model.

## The model

`xbloom_face_v1.5_.3mf` is a Bambu Studio project holding one object,
`xbloom face with straps v1.stl` (4552 triangles), laid on the plate so that
**the visible outer face of the cover points down, at Z = 0**.

Measured from the mesh:

| | |
|---|---|
| overall | 172.4 × 215.7 × 79.9 mm |
| panel wall thickness | 2.9 mm |
| **front panel (flat, usable)** | **X 51.8 … 135.0, Y 16.6 … 232.3 → 83.2 × 215.7 mm** |
| right wing | X 138 … 220 — carries 3 × Ø10 mm holes and a vent slot array |

So the picture goes on the `bottom` face (outward normal −Z), restricted to the
left-hand region — the right-hand part of that face is the side wing and must
stay clear.

The mesh is closed but **not manifold**: 8 bodies, 135 edges shared by 4 faces,
18 duplicate faces, and ~95 zero-thickness triangle pairs left over from the
striped variant. A true CSG boolean therefore fails, and the tool falls back to
merging the shells — slicers union overlapping solids, so an emboss still
prints correctly. An *engrave* would need a repaired mesh first.

## Usage

```bash
python3 emboss.py xbloom_face_v1.5_.3mf picture.png -o xbloom_face_picture.3mf \
    --face bottom --region 51.8 16.6 135.0 232.3 --margin 10 \
    --mode emboss --depth 0.6 --preview preview.png
```

`--region` takes the rectangle in the two model axes that lie in the face
(X and Y here); the picture is scaled to fit inside it with `--margin` mm clear.
3MF in and 3MF out preserves the whole Bambu Studio project — print profiles,
plate layout, thumbnails — replacing only the object mesh.

Useful options:

| flag | effect |
|---|---|
| `--depth` | relief height in mm (0.4–0.8 suits a 0.2 mm layer height) |
| `--mode engrave` | cut the picture in instead of raising it |
| `--invert` | raise the light pixels rather than the dark ones |
| `--threshold 0.5` | binarise, for a crisp flat-topped logo |
| `--rotate 180` | turn the picture on the face |
| `--offset-x/--offset-y` | nudge in mm along the face axes |
| `--resolution` | pixels along the longest side; drives the triangle count |
| `--keep-framing` | honour an off-centre subject instead of centring it |

## Dependencies

```bash
pip3 install numpy pillow trimesh manifold3d networkx matplotlib
```
