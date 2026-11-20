"""Plays a shot's motion on one of our characters, in a background Blender.

    Blender -b --factory-startup -P scripts/motion/apply_shot.py -- <shot folder> <character run folder>
        [--prop <prop run folder>] [--versions lowpoly,midpoly] [--name hero]

The shot's motion.json (SOMA, from the motion worker) is turned into the plain
form by soma_to_plain.py and then goes through the same steps as the walk:
drape.py lays the clothes on the body, rig.py puts the skeleton in, cloth.py
gives the clothes the body's weights and loose cloth its bones, animate.py
fits the motion to this character, keeps planted feet planted, clamps every
joint to its limits, bakes it and measures it, swing.py makes the loose cloth
hang and swing with it, and export.py writes one .glb. Those steps are
apply_motion.py's, which a character's run goes through too. Nothing here is a
second way to animate a character: this file only feeds animate.py a different
motion, and adds the prop.

For each version it writes into the shot folder:
    <version>-<name>.glb    the character, rigged, with the action <name>
    <version>-<name>.json   what rig.py, animate.py and export.py reported

A prop (the katana) rides on the character's sockets as the shot list's
`props` cues say: on `back` until the draw, then in `hand_right`. It is bound
to a bone of its own, `prop`, keyed every frame to sit on whichever socket
holds it, so it is part of the same action and the same file.

The character's files are only read. Never touches an open Blender.
"""

import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import apply_motion  # noqa: E402
import soma_to_plain  # noqa: E402
from soma import Skeleton  # noqa: E402

# Where each version of a character is read from, inside its run folder. The
# low-poly one is the block-out itself: that file has the gear as separate
# meshes and the sockets.
VERSION_FILES = {"lowpoly": "lowpoly.glb", "midpoly": os.path.join("profiles", "midpoly.glb")}
# Which of a prop's versions goes with which version of the character.
PROP_FILES = {"lowpoly": os.path.join("profiles", "lowpoly.glb"), "midpoly": os.path.join("profiles", "game.glb")}


def sword_shape(obj):
    """Reads a sword off its mesh: which way the blade runs, where the guard is, where a hand holds it.

    A sword is longest along its blade and widest at its guard, and the guard
    sits nearer the grip end. So: the long axis, the widest slice along it,
    and a hand's width from there toward the nearer end."""
    points = [obj.matrix_world @ v.co for v in obj.data.vertices]
    spans = [max(p[a] for p in points) - min(p[a] for p in points) for a in range(3)]
    long = spans.index(max(spans))
    lo, hi = min(p[long] for p in points), max(p[long] for p in points)
    slices = 40
    widest, guard = 0.0, lo
    for i in range(slices):
        a = lo + (hi - lo) * i / slices
        near = [p for p in points if a <= p[long] <= a + (hi - lo) / slices]
        if not near:
            continue
        width = max(max(p[k] for p in near) - min(p[k] for p in near) for k in range(3) if k != long)
        if width > widest:
            widest, guard = width, a + (hi - lo) / (2 * slices)
    toward_tip = 1.0 if (hi - guard) > (guard - lo) else -1.0
    grip_at = guard - toward_tip * 0.09
    near = [p for p in points if abs(p[long] - grip_at) < 0.05] or points
    grip = Vector([sum(p[k] for p in near) / len(near) for k in range(3)])
    grip[long] = grip_at
    tip = Vector((0.0, 0.0, 0.0))
    tip[long] = toward_tip
    # The cutting edge is on the outside of the blade's curve: opposite the way the tip lifts away from the grip.
    far = [p for p in points if (p[long] - guard) * toward_tip > 0.8 * abs((hi if toward_tip > 0 else lo) - guard)]
    lift = Vector([sum(p[k] for p in far) / len(far) for k in range(3)]) - grip
    lift[long] = 0.0
    thin = [k for k in range(3) if k != long]
    edge = Vector((0.0, 0.0, 0.0))
    k = thin[0] if abs(lift[thin[0]]) > abs(lift[thin[1]]) else thin[1]
    edge[k] = -1.0 if lift[k] > 0 else 1.0
    return {"grip": grip, "tip": tip, "edge": edge, "length": hi - lo, "guard_at": guard}


def held_at(shape, grip_at, tip_toward, edge_toward):
    """The world matrix that puts a sword's grip at a point, its tip toward one direction and its edge as near another as it can be."""
    x = tip_toward.normalized()
    z = (edge_toward - x * edge_toward.dot(x)).normalized()
    want = Matrix((x, z.cross(x), z)).transposed()  # columns: tip, side, edge
    t, e = shape["tip"], shape["edge"]
    have = Matrix((t, e.cross(t), e)).transposed()
    turn = want @ have.inverted()
    out = turn.to_4x4()
    out.translation = grip_at - turn @ shape["grip"]
    return out


def attach_prop(rig, prop_file, cues, frames, record):
    """Binds a prop to a bone of its own and keys that bone to ride the sockets the cues name."""
    sockets = {o["socket"]: o for o in bpy.context.scene.objects if o.type == "EMPTY" and o.get("forge") == "socket" and o.parent == rig}
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=prop_file)
    meshes = [o for o in bpy.context.scene.objects if o not in before and o.type == "MESH"]
    for o in [o for o in bpy.context.scene.objects if o not in before and o.type != "MESH"]:
        bpy.data.objects.remove(o)
    prop = max(meshes, key=lambda o: len(o.data.polygons))
    shape = sword_shape(prop)

    # Where it sits on each socket, worked out once in the T-pose (the rig is at rest: frame -1 has no keys yet).
    action = rig.animation_data.action
    rig.animation_data.action = None
    for bone in rig.pose.bones:
        bone.matrix_basis = Matrix()
    bpy.context.view_layer.update()
    rest = {name: o.matrix_world.copy() for name, o in sockets.items()}
    seat = {}
    if "back" in rest:
        # Across the back: grip up over the right shoulder, tip down toward the left hip, flat against the body.
        at = rest["back"].translation + Vector((-0.17, 0.05, 0.20))
        seat["back"] = rest["back"].inverted() @ held_at(shape, at, Vector((0.50, 0.0, -0.86)), Vector((-0.86, 0.0, -0.50)))
    for hand, side in (("hand_right", -1.0), ("hand_left", 1.0)):
        if hand in rest:
            # In a fist on an arm held out: blade pointing forward (-y), cutting edge down.
            seat[hand] = rest[hand].inverted() @ held_at(shape, rest[hand].translation, Vector((0.0, -1.0, 0.0)), Vector((0.0, 0.0, -1.0)))

    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    bone = rig.data.edit_bones.new("prop")
    bone.head, bone.tail = (0.0, 0.0, 0.0), (0.0, 0.1, 0.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    group = prop.vertex_groups.new(name="prop")
    group.add(range(len(prop.data.vertices)), 1.0, "REPLACE")
    world = prop.matrix_world.copy()
    prop.parent = rig
    prop.matrix_world = world
    prop.modifiers.new("Armature", "ARMATURE").object = rig
    prop.name = "prop: " + record["prop"]
    prop["forge"], prop["prop"] = "prop", record["prop"]

    rig.animation_data.action = action
    bone_rest = rig.data.bones["prop"].matrix_local.copy()
    pose = rig.pose.bones["prop"]
    pose.rotation_mode = "QUATERNION"
    plan = sorted(((round(c["from_seconds"] * bpy.context.scene.render.fps), c["socket"]) for c in cues), key=lambda c: c[0])
    last, held = None, []
    for f in range(frames + 1):
        bpy.context.scene.frame_set(f)
        socket = [s for at, s in plan if at <= f][-1] if plan and plan[0][0] <= f else plan[0][1]
        if socket not in seat:
            continue
        # Every point of the prop goes where the socket, with the prop seated on it, puts it.
        pose.matrix = rig.matrix_world.inverted() @ sockets[socket].matrix_world @ seat[socket] @ rig.matrix_world @ bone_rest
        pose.scale = (1.0, 1.0, 1.0)
        if last is not None and pose.rotation_quaternion.dot(last) < 0:
            pose.rotation_quaternion.negate()
        last = pose.rotation_quaternion.copy()
        pose.keyframe_insert("location", frame=f, group="prop")
        pose.keyframe_insert("rotation_quaternion", frame=f, group="prop")
        if not held or held[-1][1] != socket:
            held.append((f, socket))
    for curve in fcurves_of(action):
        if 'pose.bones["prop"]' in curve.data_path:
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"
    bpy.context.scene.frame_set(0)
    record.update({"length_m": round(shape["length"], 3), "sockets": [s for _, s in held], "changes_hands_at_frames": [f for f, _ in held[1:]], "triangles": sum(len(p.vertices) - 2 for p in prop.data.polygons)})
    return prop


def fcurves_of(action):
    curves = []
    if getattr(action, "layers", None):
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    curves += list(bag.fcurves)
    else:
        curves = list(getattr(action, "fcurves", []))
    return curves


def measure(rig, plan, scale, prop):
    """What the baked action does on this character, against the shot's plan scaled to its size."""
    scene = bpy.context.scene
    out = {"hands": [], "beats": []}
    hand_bone = {"left_hand": "hand_l", "right_hand": "hand_r", "left_foot": "toe_l", "right_foot": "toe_r"}
    for move in plan["moves"]:
        scene.frame_set(move["frame"])
        deps = bpy.context.evaluated_depsgraph_get()
        shown = rig.evaluated_get(deps)
        for pin, want in (move.get("pin_points") or {}).items():
            if not pin.endswith("hand"):
                continue
            got = shown.matrix_world @ shown.pose.bones[hand_bone[pin]].head
            target = Vector((want[0], -want[2], want[1])) * scale
            out["hands"].append({"move": move["name"], "pin": pin, "wrist_from_planned_spot_cm": round(100 * (got - target).length, 1)})
    for beat in plan["beats"]:
        move = [m for m in plan["moves"] if m["beat"] == beat["name"]][-1]
        scene.frame_set(move["frame"])
        shown = rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
        hips = shown.matrix_world @ shown.pose.bones["hips"].head
        out["beats"].append({"beat": beat["name"], "frame": move["frame"], "hips_from_planned_point_cm": round(100 * math.hypot(hips.x - move["x"] * scale, hips.y + move["z"] * scale), 1)})
    scene.frame_set(0)
    return out


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    shot, character = os.path.abspath(args[0]), os.path.abspath(args[1])
    prop_run = os.path.abspath(args[args.index("--prop") + 1]) if "--prop" in args else None
    versions = args[args.index("--versions") + 1].split(",") if "--versions" in args else list(VERSION_FILES)
    name = args[args.index("--name") + 1] if "--name" in args else "hero"

    with open(os.path.join(shot, "motion.json")) as f:
        motion = json.load(f)
    with open(os.path.join(shot, "plan.json")) as f:
        plan = json.load(f)
    with open(os.path.join(shot, "shotlist.json")) as f:
        cues = json.load(f).get("props") or []
    sk = Skeleton.load()
    plain, converted = soma_to_plain.convert(motion, sk, name)
    recipe = None
    if os.path.exists(os.path.join(character, "lowpoly_build.json")):
        with open(os.path.join(character, "lowpoly_build.json")) as f:
            recipe = json.load(f)

    for version in versions:
        source = os.path.join(character, VERSION_FILES[version])
        if not os.path.exists(source):
            print("APPLY %s: skipped, no %s" % (version, source))
            continue
        # The shared steps: clothes, skeleton, the motion fitted and baked, loose cloth swung (apply_motion.py).
        record = {"version": version, "motion": name, "character": source, "shot": shot, "from_soma": converted}
        record.update(apply_motion.fit(source, plain, name, recipe))
        rig = bpy.data.objects[record["rig"]["rig"]]
        scale = record["rig"]["measure"]["hip_height"] / converted["soma_hip_height_m"]
        record["size_against_soma"] = round(scale, 4)
        if prop_run and cues:
            with open(os.path.join(prop_run, "prop_of.json")) as f:
                link = json.load(f)
            record["prop"] = {"prop": link.get("gear", "prop"), "from": os.path.join(prop_run, PROP_FILES[version]), "grip": link.get("grip")}
            attach_prop(rig, record["prop"]["from"], [c for c in cues if c["prop"] == record["prop"]["prop"]] or cues, plain["frames"], record["prop"])
        record["against_the_plan"] = measure(rig, plan, scale, None)
        glb = os.path.join(shot, "%s-%s.glb" % (version, name))
        flat = False
        made = os.path.join(character, "profiles", version + ".json")
        if os.path.exists(made):
            with open(made) as f:
                flat = bool(json.load(f).get("flat_colors"))
        apply_motion.write(record, glb, materials=not flat)
        with open(os.path.join(shot, "%s-%s.json" % (version, name)), "w") as f:
            json.dump(record, f, indent=2)
        a, c = record["animation"], record["animation"]["check"]
        print("APPLY %s: %d bones, %d frames, hips lowered %.1f cm, clamped %s, planted feet slide %.2f cm, through the floor %.2f cm, %d turns outside a limit, %.2f MB -> %s" % (
            version, len(record["rig"]["bones"]), a["frames"] + 1, a["hips_lowered_cm"], json.dumps(a["clamped"]), c["foot_slide_cm_per_step"],
            c["through_floor_cm"], c["limit_violations"], record["bytes"] / 1e6, glb))
        for hand in record["against_the_plan"]["hands"]:
            print("APPLY %s: %s at '%s' is %.1f cm from its planned spot" % (version, hand["pin"], hand["move"], hand["wrist_from_planned_spot_cm"]))


main()
