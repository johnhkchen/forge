"""Plays a fight on two of our characters, in a background Blender.

    Blender -b --factory-startup -P scripts/fight/apply_fight.py -- <fight.json> <out folder>
        --left <character run folder> --right <character run folder> [--versions lowpoly,midpoly]

Three steps, and none of them is a second way to animate a character:

  1. Each character is measured. Its clothes are laid on and rig.py fits its
     skeleton, as for a walk; what the moves need to know (where the joints
     are, how long the arms are, how far the face is in front of the head's
     middle, how thick the body is lying down) is saved as <side>.body.json.
  2. schedule.py lays the fight out for those two bodies and writes one plain
     motion each, and the timeline with its hits (fight.json).
  3. Each motion goes through apply_motion.py like any other: animate.py fits
     it, plants the feet, keeps shoes and shins out of the mat, clamps every
     joint to its limit, bakes and measures it; export.py writes the file.

Into the out folder, for each version:

    <version>-left.glb, <version>-right.glb     each fighter with the action "fight"
    <version>-left.json, <version>-right.json   what rig.py, animate.py and export.py reported

and fight.json gains "measured": for each version and each hit, where the
baked fist really is on the contact frame against the spot it was built for,
and against the other man's head or chest as he really stands; and for each
fighter, animate.py's "clamped" and its checks (through the floor, limits).

The characters' files are only read. Never touches an open Blender.
"""

import json
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
import apply_motion  # noqa: E402
import moves  # noqa: E402
import schedule  # noqa: E402

# Where each version of a character is read from, inside its run folder (as apply_shot.py has it).
VERSION_FILES = {"lowpoly": "lowpoly.glb", "midpoly": os.path.join("profiles", "midpoly.glb")}


def recipe_of(run):
    path = os.path.join(run, "lowpoly_build.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def body_card(source, recipe):
    """A character's card: rig.py's joints, measurements and limits, and a few things read off the mesh as it stands at rest."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=source)
    if any(o.type == "MESH" and o.get("forge") == "gear" for o in bpy.context.scene.objects):
        apply_motion.run_script("drape.py", {"pieces": recipe["pieces"] if recipe else None, "rings": False})
    record = apply_motion.run_script("rig.py", {"recipe": recipe["pieces"] if recipe else None})
    rig = bpy.data.objects[record["rig"]]
    j = record["joints"]
    to_rig = rig.matrix_world.inverted()
    points = []
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj.find_armature() == rig:
            here = to_rig @ obj.matrix_world
            points += [here @ v.co for v in obj.data.vertices]
    tall = record["measure"]["height"]
    crown = max(0.12, tall - j["head"][2])
    face = [p.y for p in points if abs(p.x) < 0.05 and j["head"][2] + 0.25 * crown < p.z < j["head"][2] + 0.75 * crown]
    middle_z = j["spine"][2] + 0.55 * (j["chest"][2] - j["spine"][2])
    middle_y = j["spine"][1] + 0.55 * (j["chest"][1] - j["spine"][1])
    chest = [p.y for p in points if abs(p.x) < 0.6 * record["measure"]["shoulder_half_width"] and abs(p.z - middle_z) < 0.05]
    behind = [p.y for p in points if p.z > j["hips"][2] - 0.15]
    hand = rig.data.bones["hand_l"]
    extras = {
        "fist_m": round(0.5 * hand.length, 4),                                                   # the wrist to the middle of the fist
        "head_front_m": round(j["head"][1] - min(face), 4) if face else None,                    # the head's middle to the face
        "chest_front_m": round(middle_y - min(chest), 4) if chest else None,                     # the spine to the front of the chest
        "back_depth_m": round(max(behind) - j["hips"][1], 4) if behind else None,                # the hips to the furthest thing behind them
    }
    return moves.card_of(record, {k: v for k, v in extras.items() if v})


def where(rig, bone, along=0.0):
    """A point on a bone of the baked rig, on the frame the scene is at: its head, or part of the way to its tail."""
    shown = rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
    b = shown.pose.bones[bone]
    return shown.matrix_world @ (b.head + (b.tail - b.head) * along)


def from_mark(rig, point):
    """A point of the scene in the fighter's own axes: from the floor under his resting hips."""
    hips = rig.data.bones["hips"].head_local
    return (point.x - hips.x, point.y - hips.y, point.z)


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    fight_file, out = os.path.abspath(args[0]), os.path.abspath(args[1])
    runs = {side: os.path.abspath(args[args.index("--" + side) + 1]) for side in ("left", "right")}
    versions = args[args.index("--versions") + 1].split(",") if "--versions" in args else ["lowpoly"]
    os.makedirs(out, exist_ok=True)
    with open(fight_file) as f:
        fight = json.load(f)
    marks = schedule.marks_of(fight) if fight.get("set") else None
    if marks is None:
        marks = {"left": {"at": [-0.5, 0.0], "facing_deg": 90.0}, "right": {"at": [0.5, 0.0], "facing_deg": -90.0}}
    recipes = {side: recipe_of(run) for side, run in runs.items()}

    # 1. The two bodies, from the low-poly version: one move set, fitted to each by its measurements.
    cards = {}
    for side, run in runs.items():
        cards[side] = body_card(os.path.join(run, VERSION_FILES["lowpoly"]), recipes[side])
        with open(os.path.join(out, side + ".body.json"), "w") as f:
            json.dump(cards[side], f, indent=1)
        b = moves.Body(cards[side])
        print("FIGHT body %s: %.2f m tall, hips at %.2f m, arm %.2f m and a fist of %.2f, face %.1f cm in front, %.1f cm thick lying down" % (
            side, b.tall, b.leg, b.arm, b.fist, 100 * b.head_front, 100 * b.back))
    bodies = {side: moves.Body(card) for side, card in cards.items()}

    # 2. The fight, laid out for these two.
    made = schedule.schedule(fight, bodies, marks)
    timeline = made["timeline"]
    timeline["name"] = fight.get("name", "fight")
    timeline["set"], timeline["marks"] = fight.get("set"), {side: dict(marks[side], mark=(fight.get("marks") or {}).get(side)) for side in marks}
    for side, motion in made["motions"].items():
        with open(os.path.join(out, side + ".motion.json"), "w") as f:
            json.dump(motion, f)
    print("FIGHT timeline: %d frames (%.1f s), %d hits" % (timeline["frames"], timeline["seconds"], len(timeline["hits"])))

    # 3. Each fighter baked, and looked at on every contact frame.
    timeline["measured"] = {}
    for version in versions:
        seen = {"left": {}, "right": {}}
        report = {"fighters": {}, "hits": []}
        for side, run in runs.items():
            source = os.path.join(run, VERSION_FILES[version])
            if not os.path.exists(source):
                print("FIGHT %s %s: skipped, no %s" % (version, side, source))
                continue
            record = {"version": version, "motion": "fight", "character": source, "side": side}
            record.update(apply_motion.fit(source, made["motions"][side], "fight", recipes[side]))
            rig = bpy.data.objects[record["rig"]["rig"]]
            scene = bpy.context.scene
            for n, hit in enumerate(timeline["hits"]):
                if hit["by"] == side:
                    scene.frame_set(hit["frame"])
                    seen[side][n] = {"fist": schedule.set_point(marks[side], from_mark(rig, where(rig, "hand_" + hit["hand"], 0.5)))}
                else:  # the man hit, on the frame before: where the blow was aimed
                    scene.frame_set(hit["frame"] - 1)
                    seen[side][n] = {"head": schedule.set_point(marks[side], from_mark(rig, where(rig, "head", 0.5 * bodies[side].head_tall / max(rig.data.bones["head"].length, 1e-6)))),
                                     "chest": schedule.set_point(marks[side], from_mark(rig, where(rig, "spine", 0.55)))}
            scene.frame_set(0)
            flat = False
            made_as = os.path.join(run, "profiles", version + ".json")
            if os.path.exists(made_as):
                with open(made_as) as f:
                    flat = bool(json.load(f).get("flat_colors"))
            glb = os.path.join(out, "%s-%s.glb" % (version, side))
            apply_motion.write(record, glb, materials=not flat)
            with open(os.path.join(out, "%s-%s.json" % (version, side)), "w") as f:
                json.dump(record, f, indent=1)
            a, c = record["animation"], record["animation"]["check"]
            report["fighters"][side] = {"glb": os.path.basename(glb), "clamped": a["clamped"], "through_floor_cm": c["through_floor_cm"], "lowest_part": c["lowest_part"],
                                        "lowest_frame": c["lowest_frame"], "limit_violations": c["limit_violations"], "planted_foot_strays_cm": c["planted_foot_strays_cm"],
                                        "hips_lowered_cm": a["hips_lowered_cm"], "off_the_motion": c["off_the_motion"], "ground": [round(v, 4) for v in rig.data.bones["hips"].head_local[:2]]}
            print("FIGHT %s %s: %d frames, clamped %s, through the mat %.2f cm (%s, frame %d), %d turns outside a limit, a planted foot strays %.2f cm, %.2f MB -> %s" % (
                version, side, a["frames"] + 1, json.dumps(a["clamped"]), c["through_floor_cm"], c["lowest_part"], c["lowest_frame"], c["limit_violations"],
                c["planted_foot_strays_cm"], record["bytes"] / 1e6, glb))
        for n, hit in enumerate(timeline["hits"]):
            mine, his = seen[hit["by"]].get(n), seen[hit["on"]].get(n)
            if not mine or not his:
                continue
            fist = mine["fist"]
            low = moves.STRIKES[hit["move"]]["aims"] == "low"
            aimed = his["chest"] if low else his["head"]
            row = {"frame": hit["frame"], "move": hit["move"], "by": hit["by"], "blocked": hit["blocked"], "fist": fist,
                   "fist_from_its_spot_cm": round(100 * math.dist(fist, hit["at"]), 1),
                   "fist_from_his_%s_cm" % ("chest" if low else "head"): round(100 * math.dist(fist, aimed), 1)}
            report["hits"].append(row)
            print("FIGHT %s hit at %d, %s %s%s: fist %.1f cm from its spot, %.1f cm from the middle of his %s" % (
                version, hit["frame"], hit["by"], hit["move"], " (blocked)" if hit["blocked"] else "", row["fist_from_its_spot_cm"],
                round(100 * math.dist(fist, aimed), 1), "chest" if low else "head"))
        timeline["measured"][version] = report
    with open(os.path.join(out, "fight.json"), "w") as f:
        json.dump(timeline, f, indent=1)
    print("FIGHT wrote", os.path.join(out, "fight.json"))


main()
