#!/usr/bin/env python3
"""Drop the embedded print/printer profile from a 3MF, keeping the geometry.

The xBloom project ships an X1 Carbon profile: X1-specific start G-code and X1
acceleration limits. Loading that on another printer is not a matter of
renaming a field, so this removes the profile instead and lets the slicer apply
the settings for whichever printer is actually selected. The model, its
position on the plate and the rest of the archive are untouched.
"""

import argparse
import zipfile

DROP = {"Metadata/project_settings.config"}


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("model")
    p.add_argument("-o", "--out", required=True)
    args = p.parse_args()

    with zipfile.ZipFile(args.model) as zf:
        kept = [i for i in zf.infolist() if i.filename not in DROP]
        dropped = [i.filename for i in zf.infolist() if i.filename in DROP]
        with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as out:
            for info in kept:
                out.writestr(info, zf.read(info.filename))

    print(f"dropped: {', '.join(dropped) or 'nothing'}")
    print(f"wrote:   {args.out} ({len(kept)} entries kept)")


if __name__ == "__main__":
    main()
