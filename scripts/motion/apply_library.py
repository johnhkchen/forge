"""Plays the screen-test motions on one character, in a background Blender.

    Blender -b --factory-startup -P scripts/motion/apply_library.py -- <character run folder>
        [--motions deep-squat,kick] [--versions lowpoly,midpoly] [--library motion/library]

Each motion in the library (motion/library/<id>/motion.json, SOMA, made by
Kimodo: screen_motions.py) goes onto the character the way its run and its
shots do (apply_motion.py): its clothes laid on, its own skeleton fitted with
its joint limits, the motion fitted to it with planted feet kept planted, every
joint clamped inside its limits, loose cloth swung, a tail made to follow the
hips. The motion is played in the character's own strides (lengths in hip
heights), as a run is: nothing here is tuned per character, so every rig is
asked the same thing and animate.py's "clamped" report says which joints a
motion asked too much of.

For each version it writes into the run's profiles/ folder, beside its walk and
its run:

    <version>-screen-<id>.glb    the character, rigged, with the action screen-<id>
    <version>-screen-<id>.json   what rig.py, animate.py and export.py reported,
                                 and `screen`: which motion, from which sentence

The cards play these as they play the walk: a card baked from the detailed
mesh on the low-poly skeleton plays the low-poly files. The character's own
files are only read. Never touches an open Blender.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import apply_motion  # noqa: E402
import soma_to_plain  # noqa: E402
from soma import Skeleton  # noqa: E402

# Where each version of a character is read from, inside its run folder (as apply_shot.py reads them): the low-poly
# one is the block-out itself, with its gear as separate meshes and its sockets.
VERSION_FILES = {"lowpoly": "lowpoly.glb", "midpoly": os.path.join("profiles", "midpoly.glb"), "painted": os.path.join("profiles", "painted.glb")}


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default  # noqa: E731
    run = os.path.abspath(args[0])
    library = os.path.abspath(flag("--library", os.path.join(REPO, "motion", "library")))
    versions = flag("--versions", "lowpoly,midpoly").split(",")
    listed = [m["id"] for m in json.load(open(os.path.join(library, "library.json")))["motions"]]
    wanted = [m for m in flag("--motions", ",".join(listed)).split(",") if m]
    sk = Skeleton.load()
    recipe = None  # what the block-out was built from: lowpoly_build.json, or the copy riding in lowpoly.glb (as tidy_profile.py reads it)
    if os.path.exists(os.path.join(run, "lowpoly_build.json")):
        with open(os.path.join(run, "lowpoly_build.json")) as f:
            recipe = json.load(f)
    elif os.path.exists(os.path.join(run, "lowpoly.glb")):
        try:
            recipe = apply_motion.blockout_recipe.contents(apply_motion.blockout_recipe.read(os.path.join(run, "lowpoly.glb"))[0])["recipe"]
        except (KeyError, ValueError, TypeError):
            recipe = None
    profiles = os.path.join(run, "profiles")
    for mid in wanted:
        path = os.path.join(library, mid, "motion.json")
        if not os.path.exists(path):
            print("SCREEN %s: skipped, not made yet (just screen-motions go)" % mid)
            continue
        with open(path) as f:
            motion = json.load(f)
        name = "screen-" + mid
        plain, converted = soma_to_plain.convert(motion, sk, name)
        for version in versions:
            source = os.path.join(run, VERSION_FILES[version])
            if not os.path.exists(source):
                print("SCREEN %s %s: skipped, no %s" % (mid, version, source))
                continue
            started = time.time()
            made = {}
            if os.path.exists(os.path.join(profiles, version + ".json")):
                with open(os.path.join(profiles, version + ".json")) as f:
                    made = json.load(f)
            record = {"profile": "%s-%s" % (version, name), "of": version, "character": source, "from_soma": converted,
                      "screen": {"id": mid, "name": motion.get("name"), "prompt": motion.get("prompt"), "ask": motion.get("ask"),
                                 "take": motion.get("take"), "seed": motion.get("seed"), "seconds": motion.get("seconds"), "made_by": motion.get("made_by")}}
            try:
                record.update(apply_motion.fit(source, plain, name, recipe, {}, tail=True))
            except ValueError as why:  # not a character a skeleton fits (not in a T-pose)
                print("SCREEN %s %s: skipped, %s" % (mid, version, why))
                continue
            record["size_against_soma"] = round(record["rig"]["measure"]["hip_height"] / converted["soma_hip_height_m"], 4)
            glb = os.path.join(profiles, "%s-%s.glb" % (version, name))
            apply_motion.write(record, glb, materials=not made.get("flat_colors"))
            record["gear"], record["sockets"] = made.get("gear") or [], made.get("sockets") or []
            record["seconds"] = round(time.time() - started, 1)
            with open(os.path.join(profiles, "%s-%s.json" % (version, name)), "w") as f:
                json.dump(record, f, indent=2)
            a, c = record["animation"], record["animation"]["check"]
            print("SCREEN %s %s: %d frames, clamped %s, a planted foot strays %.2f cm at most, through the floor %.2f cm (%s), %d turns outside a limit, %.2f MB, %.0fs -> %s" % (
                mid, version, a["frames"] + 1, json.dumps(a.get("clamped") or {}), c["planted_foot_strays_cm"], c["through_floor_cm"], c["lowest_part"],
                c["limit_violations"], record["bytes"] / 1e6, record["seconds"], glb), flush=True)


main()
