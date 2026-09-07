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

## Result

`xbloom_face_raised_0.1mm.3mf` — **print this one.** The portrait stands out of
the panel: the whole panel is lowered 1.4 mm and the figure rises back to the
original surface, 83.2 x 108 mm, seated at the bottom and running the full
panel width. The project's layer height is set to 0.1 mm.

`xbloom_face_raised_0.2mm.3mf` is the same mesh on the original 0.2 mm profile.

Reproduce with:

```bash
python3 prepare.py portrait_source.jpg -o prepared.png --raised \
    --clahe 0.6 --gamma 0.95 --floor 0.30 --feather 1 \
    --fade-bottom 0.14 --fade-left 0.07

python3 emboss.py xbloom_face_v1.5_.3mf prepared.png -o raised.3mf \
    --repair --raised 1.4 --invert --face bottom \
    --region 51.76 16.57 135.0 232.26 --margin 0 --valign bottom \
    --blur 0.4 --resolution 480

python3 set_layer_height.py raised.3mf -o raised_0.1mm.3mf --layer-height 0.1
```

### Raised relief on a face that lies on the build plate

The decorated face sits at Z = 0, on the plate, so relief cannot protrude
outward — there is nothing below Z = 0 to print into. `--raised MM` gets the
raised look while only ever *removing* material: it lowers the whole of
`--region` by MM, then stands the picture back out of that recess so its peaks
finish flush with the original surface. The part still prints face-down with no
supports, and the figure's highest points line up with the wing's face.

### Layer height decides whether it reads as a relief at all

A relief shows only as many tones as it has layers. The first print of this
model, at the project's stock 0.2 mm over a 1.1 mm relief, had five steps:
broad areas of the robe and face all landed on one step and only sharp edges
crossed a layer boundary, so it printed as contour lines rather than a
carving. At 1.4 mm and 0.1 mm layers there are fourteen steps.

That doubles print time over the whole 80 mm part. Bambu Studio's variable
layer height tool can instead hold 0.1 mm for just the bottom 2 mm, where the
relief is, and run 0.2 mm above it.

### Do not lean on CLAHE for a relief

Local contrast equalisation sharpens edges but flattens the broad tonal
gradient that gives a relief its volume — it pushes the result toward
outlines, which is the other half of what went wrong on that first print.
`--clahe 0.6` or lower, and let the global contrast stretch do the work.

### Printing notes

- Print in the orientation the project already has: decorated face down, no supports.
- 0.2 mm layers give the 1.0 mm carve five tonal steps; **0.1 mm layers give ten**
  and look markedly smoother.
- Use a smooth plate. A textured plate stamps its own pattern over the relief.
- Panel wall is 2.9 mm, so a 1.0 mm carve leaves 1.9 mm behind it.

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
| `--valign/--halign` | sit against an edge of `--region` instead of its middle |
| `--offset-x/--offset-y` | nudge in mm along the face axes |
| `--resolution` | pixels along the longest side; drives the triangle count |
| `--keep-framing` | honour an off-centre subject instead of centring it |

## Dependencies

```bash
pip3 install numpy pillow trimesh manifold3d networkx matplotlib
```
