#!/usr/bin/env python3
"""Set the layer height stored in a Bambu Studio 3MF project.

A relief only shows as many tones as it has layers. At the project's stock
0.2 mm a 1.4 mm relief has seven steps, so broad gradients land on a single
step and only the sharp edges cross a boundary -- which prints as contour
lines rather than a carving. 0.1 mm doubles the tonal steps to fourteen.

Everything else in the project is copied through untouched.
"""

import argparse
import json
import zipfile

SETTINGS = "Metadata/project_settings.config"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("model", help="input 3MF")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--layer-height", type=float, default=0.1)
    p.add_argument("--first-layer", type=float, default=None,
                   help="initial layer height (defaults to --layer-height)")
    args = p.parse_args()

    first = args.first_layer if args.first_layer is not None else args.layer_height
    with zipfile.ZipFile(args.model) as zf:
        cfg = json.loads(zf.read(SETTINGS).decode())
        was = (cfg.get("layer_height"), cfg.get("initial_layer_print_height"))
        cfg["layer_height"] = str(args.layer_height)
        cfg["initial_layer_print_height"] = str(first)
        blob = json.dumps(cfg, indent=4, ensure_ascii=False).encode()

        with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as out:
            for info in zf.infolist():
                out.writestr(info, blob if info.filename == SETTINGS
                             else zf.read(info.filename))

    print(f"layer height {was[0]} -> {args.layer_height} mm, "
          f"first layer {was[1]} -> {first} mm")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
