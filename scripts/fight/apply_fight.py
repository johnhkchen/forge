"""Plays a fight on two of our characters, in a background Blender.

    Blender -b --factory-startup -P scripts/fight/apply_fight.py -- <fight.json> <out folder>
        --left <character run folder> --right <character run folder>
        [--left-version painted] [--right-version lowpoly] [--versions cast,midpoly] [--open-hands]

Which version of each character plays is the fight script's to say
("fighters": {"left": {"version": "painted"}}; lowpoly if it says nothing),
or the command line's. That pairing is the "cast". --versions adds other
passes with both fighters in one version (lowpoly, midpoly, painted).

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

Fists. Our hands are mittens with no finger bones, and an open mitten does
not read as a punch. So, for a fight only, each hand gets two more bones
("fingers_l" and "fingertips_l", and the same on the right), at the knuckles
and halfway down the fingers; the far half of the hand's mesh goes over to
them, and they are curled under and kept there for the whole action. No other profile gets it, and --open-hands leaves it out here.

Into the out folder, for the cast (and for each version asked for, under its own name):

    cast-left.glb, cast-right.glb     each fighter with the action "fight"
    cast-left.json, cast-right.json   what rig.py, animate.py and export.py reported

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
VERSION_FILES = {"lowpoly": "lowpoly.glb", "midpoly": os.path.join("profiles", "midpoly.glb"), "painted": os.path.join("profiles", "painted.glb")}
KNUCKLES = (0.5, 0.76)   # where a hand folds, as shares of the way from the wrist to the fingertips: the knuckles, and halfway down the fingers
CURL_DEG = (85.0, 90.0)  # how far it is curled under at each


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
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import blockout_recipe

    record = apply_motion.run_script("rig.py", {"recipe": recipe["pieces"] if recipe else None,
                                                "template": blockout_recipe.wardrobe_template(bpy.data.materials)})  # a painted version's body takes the template's own weights
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


def close_fists(rig):
    """Two more bones in each hand, at the knuckles and halfway down the fingers, with the far half of the hand's
    mesh on them, curled under and keyed that way in the rig's action: an open hand made into a fist.
    Where the knuckles are is read off the mesh (halfway from the wrist to the fingertips), so a short mitten
    and a hand with real fingers both fold in the right place. Returns what it did."""
    from mathutils import Quaternion

    to_rig = rig.matrix_world.inverted()
    skinned = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.find_armature() == rig]
    reach, lines = {}, {}
    for tag in ("l", "r"):
        hand = rig.data.bones["hand_" + tag]
        along = (hand.tail_local - hand.head_local).normalized()
        far = [hand.length]
        for obj in skinned:
            if "hand_" + tag not in obj.vertex_groups:
                continue
            index, here = obj.vertex_groups["hand_" + tag].index, to_rig @ obj.matrix_world
            far += [(here @ v.co - hand.head_local).dot(along) for v in obj.data.vertices if any(g.group == index and g.weight >= 0.5 for g in v.groups)]
        reach[tag] = max(far)
        lines[tag] = (KNUCKLES[0] * reach[tag], KNUCKLES[1] * reach[tag])
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for tag in ("l", "r"):
        hand = rig.data.edit_bones["hand_" + tag]
        along = (hand.tail - hand.head).normalized()
        spots = [hand.head + along * lines[tag][0], hand.head + along * lines[tag][1], hand.head + along * reach[tag]]
        above = hand
        for name, k in (("fingers_" + tag, 0), ("fingertips_" + tag, 1)):
            bone = rig.data.edit_bones.new(name)
            bone.head, bone.tail, bone.roll = spots[k], spots[k + 1], hand.roll
            bone.parent, bone.use_connect = above, False
            above = bone
    bpy.ops.object.mode_set(mode="OBJECT")
    made = {}
    scene = bpy.context.scene
    for tag, out in (("l", 1.0), ("r", -1.0)):
        hand = rig.data.bones["hand_" + tag]
        along = (hand.tail_local - hand.head_local).normalized()
        soft = 0.06 * reach[tag]  # a line is crossed over this much of the hand, so the fold is a bend and not a crease
        moved = 0
        for obj in skinned:
            if "hand_" + tag not in obj.vertex_groups:
                continue
            was = obj.vertex_groups["hand_" + tag]
            first = obj.vertex_groups.get("fingers_" + tag) or obj.vertex_groups.new(name="fingers_" + tag)
            second = obj.vertex_groups.get("fingertips_" + tag) or obj.vertex_groups.new(name="fingertips_" + tag)
            here = to_rig @ obj.matrix_world
            for v in obj.data.vertices:
                weight = next((g.weight for g in v.groups if g.group == was.index), 0.0)
                if weight <= 0.0:
                    continue
                far = (here @ v.co - hand.head_local).dot(along)
                over = [min(1.0, max(0.0, (far - line + soft) / (2.0 * soft))) for line in lines[tag]]
                if over[0] > 0.0:
                    was.add([v.index], weight * (1.0 - over[0]), "REPLACE")
                    first.add([v.index], weight * over[0] * (1.0 - over[1]), "REPLACE")
                    second.add([v.index], weight * over[0] * over[1], "REPLACE")
                    moved += 1
        # Curled under: in the T-pose the palm faces the floor, so the fingers turn down about the front-to-back axis.
        for name, degrees in (("fingers_" + tag, CURL_DEG[0]), ("fingertips_" + tag, CURL_DEG[1])):
            rest = rig.data.bones[name].matrix_local.to_3x3()
            curl = Quaternion((0.0, 1.0, 0.0), math.radians(out * degrees)).to_matrix()
            pose = rig.pose.bones[name]
            pose.rotation_mode = "QUATERNION"
            pose.rotation_quaternion = (rest.inverted() @ curl @ rest).to_quaternion()
            for frame in (scene.frame_start, scene.frame_end):
                pose.keyframe_insert("rotation_quaternion", frame=frame, group=name)
        made[tag] = {"points_moved": moved, "hand_long_cm": round(100 * reach[tag], 1)}
    return {"bones": ["fingers_l", "fingertips_l", "fingers_r", "fingertips_r"], "hands": made, "curl_deg": list(CURL_DEG)}


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
    versions = args[args.index("--versions") + 1].split(",") if "--versions" in args else ["cast"]
    os.makedirs(out, exist_ok=True)
    with open(fight_file) as f:
        fight = json.load(f)
    marks = schedule.marks_of(fight) if fight.get("set") else None
    if marks is None:
        marks = {"left": {"at": [-0.5, 0.0], "facing_deg": 90.0}, "right": {"at": [0.5, 0.0], "facing_deg": -90.0}}
    recipes = {side: recipe_of(run) for side, run in runs.items()}
    # Who plays in what: the fight script's choice for each side, unless the command line says otherwise.
    cast = {side: (fight.get("fighters") or {}).get(side, {}).get("version", "lowpoly") for side in runs}
    for side in runs:
        if "--%s-version" % side in args:
            cast[side] = args[args.index("--%s-version" % side) + 1]
        if cast[side] not in VERSION_FILES:
            sys.exit("no version called %r: choose from %s" % (cast[side], ", ".join(sorted(VERSION_FILES))))
        if not os.path.exists(os.path.join(runs[side], VERSION_FILES[cast[side]])):
            sys.exit("%s has no %s (%s)" % (runs[side], cast[side], VERSION_FILES[cast[side]]))
    fists = fight.get("fists", True) and "--open-hands" not in args

    # 1. The two bodies, each in the version it plays in: one move set, fitted to each by its measurements.
    cards = {}
    for side, run in runs.items():
        cards[side] = body_card(os.path.join(run, VERSION_FILES[cast[side]]), recipes[side])
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
    if fight.get("set"):  # a man knocked down must land on the mat, not through the ropes
        sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
        import standing

        st = standing.load(fight["set"])
        for hit in timeline["hits"]:
            for part, spot in sorted((hit.get("lies") or {}).items()):
                if not standing.on_floor(st, spot[0], spot[2]):
                    hit["off_the_floor"] = True
                    print("FIGHT warning: %s is knocked down at frame %d and his %s lands off the set's floor, at x %.2f, z %.2f: move the fight marks or let the other man fall" % (
                        hit["on"], hit["frame"], part, spot[0], spot[2]))

    # 3. Each fighter baked, and looked at on every contact frame.
    timeline["measured"], timeline["cast"], timeline["fists"] = {}, cast, fists
    for version in versions:
        seen = {"left": {}, "right": {}}
        report = {"fighters": {}, "hits": []}
        for side, run in runs.items():
            plays = cast[side] if version == "cast" else version
            source = os.path.join(run, VERSION_FILES[plays])
            if not os.path.exists(source):
                print("FIGHT %s %s: skipped, no %s" % (version, side, source))
                continue
            record = {"version": plays, "motion": "fight", "character": source, "side": side}
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
            if fists:
                record["fists"] = close_fists(rig)
            flat = False
            made_as = os.path.join(run, "profiles", plays + ".json")
            if os.path.exists(made_as):
                with open(made_as) as f:
                    flat = bool(json.load(f).get("flat_colors"))
            glb = os.path.join(out, "%s-%s.glb" % (version, side))
            apply_motion.write(record, glb, materials=not flat)
            with open(os.path.join(out, "%s-%s.json" % (version, side)), "w") as f:
                json.dump(record, f, indent=1)
            a, c = record["animation"], record["animation"]["check"]
            report["fighters"][side] = {"glb": os.path.basename(glb), "version": plays, "clamped": a["clamped"], "through_floor_cm": c["through_floor_cm"], "lowest_part": c["lowest_part"],
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
