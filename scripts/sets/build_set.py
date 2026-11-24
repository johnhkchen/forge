"""Builds a set's geometry from data, in a background Blender: a block-out, cheap to make and to change.

    Blender -b --factory-startup -P scripts/sets/build_set.py -- <set> [--only set|dressing]

Reads sets/<set>/set.json and sets/<set>/build.json and writes
    sets/<set>/set.glb               the set itself
    sets/<set>/dressing/<prop>.glb   each piece of dressing, on its own, standing at 0, 0, 0

The set is built with the skill's build.py, the tool the low-poly block-outs
are built with, from two lists:

    the set's blocks    every block in set.json becomes a box in its `color`.
                        These are the same boxes the contact step keeps a
                        body out of, so what you see is what is in the way.
                        (A block with "build": false is left out: it only
                        keeps people out of a piece of dressing, like the
                        ring in the boxing house.)
    build.json extras   pieces that are only looked at: the floor, a desk
                        top, cushions, a window frame.

Dressing is kept out of the set's file on purpose: a mug or a plant is a
small .glb of its own, stood on one of the set's slots when it is filmed, so
it can be moved, swapped or left out without building the set again.

Pieces are written in the set's own axes (x, y up, z toward the cameras) and
turned here for Blender (z up). Colors are flat, painted on the corners; there
are no textures. Never touches an open Blender.
"""

import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
import apply_motion  # noqa: E402  (for run_script: a skill script with its PARAMS filled in)
import standing  # noqa: E402

GRAY = [0.7, 0.68, 0.65]


def blender_point(p):
    """A point of the set (x, y up, z) in Blender's axes (x, y, z up)."""
    return [p[0], -p[2], p[1]]


def turned(piece):
    """A build.py piece written in the set's axes, as build.py wants it."""
    out = dict(piece)
    if "box" in piece:
        a, b = blender_point(piece["box"]["min"]), blender_point(piece["box"]["max"])
        out["box"] = {"min": [min(a[i], b[i]) for i in range(3)], "max": [max(a[i], b[i]) for i in range(3)]}
    if "tube" in piece:
        out["tube"] = [blender_point(row[:3]) + list(row[3:]) for row in piece["tube"]]
        if "up" in piece:  # which way the tube's "up" side faces (a sloping roof slab): a direction, turned the same way
            out["up"] = blender_point(piece["up"])
    if "lumps" in piece:
        out["lumps"] = [blender_point(row[:3]) + list(row[3:]) for row in piece["lumps"]]
    if "loft" in piece:
        if piece["loft"] != "y":
            raise ValueError("%s: a set's lofts stand up (\"loft\": \"y\")" % piece["name"])
        # [height, x, z, radius...] becomes build.py's [z, x, y, radius...]
        out["loft"] = "z"
        out["rings"] = [[row[0], row[1], -row[2]] + list(row[3:]) for row in piece["rings"]]
    return out


def block_piece(block):
    if abs(block.get("heading", 0.0)) > 0.01:
        raise ValueError("block %r is turned; build_set.py builds straight boxes only" % block["name"])
    c, s = block["center"], block["size"]
    lo = [c[i] - s[i] / 2.0 for i in range(3)]
    hi = [c[i] + s[i] / 2.0 for i in range(3)]
    return turned({"name": block["name"], "box": {"min": lo, "max": hi}, "color": block.get("color", GRAY)})


def build(pieces, out, name):
    """One .glb from build.py pieces: a fresh scene, the pieces joined, written with their flat colors."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # build.py measures against a detailed mesh; a set has none, so it gets a plain box to stand in for one.
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    stand_in = bpy.context.active_object
    stand_in.name = "stand-in"
    built = apply_motion.run_script("build.py", {"reference": "stand-in", "name": name, "parts": pieces, "shading": "flat", "sockets": False, "gear": [], "check": 0})
    bpy.data.objects.remove(stand_in, do_unlink=True)
    wrote = apply_motion.run_script("export.py", {"object": name, "path": out, "materials": False, "apart": False, "check": True})
    return {"triangles": built["triangles"], "pieces": len(built["pieces"]), "size": built["size"], "bytes": os.path.getsize(out), "only_this_object": (wrote or {}).get("only_this_object")}


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    st = standing.load(args[0])
    only = args[args.index("--only") + 1] if "--only" in args else None
    with open(os.path.join(st["dir"], "build.json")) as f:
        recipe = json.load(f)
    if only in (None, "set"):
        pieces = [block_piece(b) for b in st["blocks"] if b.get("build", True)] + [turned(p) for p in recipe.get("extras") or []]
        made = build(pieces, os.path.join(st["dir"], st["geometry"].get("glb", "set.glb")), st["name"])
        print("SETBUILD %s: %d pieces, %d triangles, %.1f x %.1f x %.1f m, %d kB -> %s" % (
            st["name"], made["pieces"], made["triangles"], made["size"][0], made["size"][1], made["size"][2], made["bytes"] // 1000, st["geometry"].get("glb", "set.glb")))
    if only in (None, "dressing"):
        os.makedirs(os.path.join(st["dir"], "dressing"), exist_ok=True)
        for prop, pieces in (recipe.get("dressing") or {}).items():
            made = build([turned(p) for p in pieces], os.path.join(st["dir"], "dressing", prop + ".glb"), prop)
            print("SETBUILD %s: dressing %s, %d triangles, %d kB" % (st["name"], prop, made["triangles"], made["bytes"] // 1000))


main()
