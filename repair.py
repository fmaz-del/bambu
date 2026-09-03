#!/usr/bin/env python3
"""Turn the xBloom cover mesh into a single watertight solid.

The published 3MF is closed but not manifold: duplicate faces, ~95 zero-thickness
triangle pairs left over from the striped variant, and seven open boundary loops
in the panel face where the stripe recesses were modelled but never capped.
Nothing can be booleaned against it in that state.

The cleanup drops the junk, caps each boundary loop with a centroid fan, and
unions the surviving bodies -- which merges the six flush 0.2 mm "xbloom" letter
inlays into the panel, leaving it flat.
"""

import numpy as np
import trimesh

try:
    import networkx as nx
except ImportError:                                    # pragma: no cover
    nx = None


def cap_boundary_loops(mesh):
    """Close every open boundary loop with a fan from its centroid."""
    e, c = np.unique(mesh.edges_sorted, axis=0, return_counts=True)
    open_e = e[c == 1]
    if not len(open_e):
        return mesh, 0

    g = nx.Graph()
    g.add_edges_from(open_e.tolist())
    verts, faces = list(mesh.vertices), list(mesh.faces)
    capped = 0

    for comp in nx.connected_components(g):
        sub = g.subgraph(comp)
        if any(d != 2 for _, d in sub.degree()):       # not a simple closed loop
            continue
        loop = list(nx.cycle_basis(sub)[0])
        centre = len(verts)
        verts.append(mesh.vertices[loop].mean(0))
        for i in range(len(loop)):
            faces.append([loop[i], loop[(i + 1) % len(loop)], centre])
        capped += 1

    out = trimesh.Trimesh(np.array(verts), np.array(faces), process=False)
    out.merge_vertices()
    trimesh.repair.fix_normals(out)
    return out, capped


def repair(mesh, min_faces=9, verbose=True):
    """Clean, cap and union a messy mesh into one solid."""
    mesh = mesh.copy()
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()

    bodies = [b for b in mesh.split(only_watertight=False) if len(b.faces) >= min_faces]
    solids = []
    for b in bodies:
        if not b.is_volume:
            b, n = cap_boundary_loops(b)
            if verbose and n:
                print(f"  capped {n} boundary loop(s) on a {len(b.faces)}-face body")
        if b.is_volume:
            solids.append(b)
        elif verbose:
            print(f"  dropped a {len(b.faces)}-face body that would not close")

    if not solids:
        raise RuntimeError("nothing repairable in this mesh")

    solids.sort(key=lambda b: -abs(b.volume))
    out = solids[0]
    for b in solids[1:]:
        try:
            out = trimesh.boolean.union([out, b])
        except Exception:                              # noqa: BLE001
            if verbose:
                print(f"  skipped a {len(b.faces)}-face body the union rejected")
    if verbose:
        print(f"  repaired: {len(out.faces)} faces, {out.volume / 1000:.2f} cm3, "
              f"volume={out.is_volume}")
    return out


if __name__ == "__main__":
    import sys
    m = trimesh.load(sys.argv[1], force="mesh")
    print(f"input: {len(m.faces)} faces, volume={m.is_volume}")
    r = repair(m)
    r.export(sys.argv[2] if len(sys.argv) > 2 else "repaired.stl")
