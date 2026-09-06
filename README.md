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

`xbloom_face_portrait.3mf` carries the portrait carved into the left panel:
**83.2 x 107.5 mm, 1.0 mm deep**, running the full width of the panel and
seated at its bottom edge. The subject is masked out of its background first,
so the carving is bounded by its own silhouette rather than a rectangular
plaque, and the edges where the photo's own crop cuts the figure are faded out
into the panel. `preview_panel.png` is a lit render of the finished face.

Reproduce it with:

```bash
python3 prepare.py portrait_source.jpg -o prepared.png \
    --clahe 1.8 --gamma 1.1 --floor 0.05 --feather 1 \
    --fade-bottom 0.14 --fade-left 0.07

python3 emboss.py xbloom_face_v1.5_.3mf prepared.png -o xbloom_face_portrait.3mf \
    --repair --flatten 0.6 --face bottom --region 51.76 16.57 135.0 232.26 \
    --margin 0 --valign bottom --mode engrave --depth 1.1 --blur 0.4 --resolution 480

python3 render_panel.py xbloom_face_portrait.3mf -o preview_panel.png \
    --region 50 14 136.5 234.5
```

### Checking the output

Verify the written file, not the mesh in memory -- that check cannot catch a
writer bug, and two of them hid behind it here. Reload the 3MF with
`process=False`, so trimesh does not merge vertices on the way in and mask
what is actually stored:

```python
m = trimesh.Trimesh(V, F, process=False)   # V, F parsed from the archive
assert m.is_watertight                      # every edge shared by exactly 2 faces
```

The shipped file passes: 231178 triangles, all 346767 edges at valence 2,
bounds matching the original to 1.5 um, and all 29 archive entries intact.
Loading it with trimesh's defaults reports it as non-watertight -- that is the
loader merging two vertex pairs that sit 10 femtometres apart, not a defect.

### Why it is carved in and not raised

That face lies **on the build plate**. Raised relief would protrude below Z = 0,
so the part would have to be lifted and printed on supports. Cutting inward
keeps it printable as-is — and it is what the original design already does: the
stripes and the "xbloom" lettering are 0.2 mm recesses in this same face.

`--flatten 0.6` fills the panel flush before carving, which clears the old
stripe recesses and lettering and gives the portrait a clean ground.

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
