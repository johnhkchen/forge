"""Puts one of our characters on the skateboard and has it ride a run, in a background Blender.

    Blender -b --factory-startup -P scripts/skate/apply_ride.py -- <ride.json> <out folder>
        --character <character run folder> [--versions lowpoly,midpoly] [--shots <folder of shots>]

Four steps, and none of them is a second way to animate a character:

  1. The character is measured: rig.py fits its skeleton, as for a walk, and
     what the poses need (where the joints are, how long the arms are) is
     saved as rider.body.json.
  2. ride.py lays the run out for that body: where the board is on every
     frame (ride.json), and the rider's own motion in the board's frame
     (rider.motion.json).
  3. That motion goes through apply_motion.py like any other. The deck is
     the floor: animate.py plants both feet on it, keeps shoes out of it,
     clamps every joint to its limit, bakes and measures.
  4. The board and the ride are added. The skateboard (world/props/
     skateboard.glb) is bound to a bone of its own under the feet, the way a
     prop rides a socket, and one more bone, "ride", is put above the hips
     and the board and keyed to where ride.json says the board is. So the
     file holds the whole run in the set's own place: put it down at the
     set's origin and it rides the ramp.

In a handplant the board is carried by the hand: on each of its frames the
baked hand is found, and the board is put wherever keeps that hand on its
spot on the coping (eased on from the lip and back onto it).

Then he is kept out of the ramp. Off the surface (an air, a handplant) the
baked body is looked at where the ride puts it, and if any of it is in the
wood, board and rider are moved the short way out, the way the surface
faces there; the push is evened out over the frames round it. A borrowed
pose can hang a shoulder or a knee where our own poses never would.

Into the out folder:

    <version>-ride.glb     the character, the board, the action "ride"
    <version>-ride.json    what rig.py, animate.py and export.py reported
    ride.json              gains "measured_on": for each version, on the baked
                           file: how far the wheels are from the ramp while
                           riding, how far the feet are from the deck and
                           from where they were put, how deep anything is in
                           the ramp, turns outside a limit, the grabbing
                           hand against the board's edge, the planted hand
                           against the coping

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
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
sys.path.insert(0, os.path.join(REPO, "scripts", "fight"))
import apply_motion  # noqa: E402
import blockout_recipe  # noqa: E402
import board  # noqa: E402
import moves  # noqa: E402
import ride as ride_file  # noqa: E402
from pipe import Pipe  # noqa: E402

VERSION_FILES = {"lowpoly": "lowpoly.glb", "midpoly": os.path.join("profiles", "midpoly.glb"), "painted": os.path.join("profiles", "painted.glb")}
EVERY = 2  # the mesh is looked at on every this-many frames (and on every frame of a trick)
PUSH_CLEAR = 0.004   # metres: he is moved until nothing of him is deeper in the ramp than this
PUSH_ROUNDS = 6      # how many times a frame is moved and looked at again
PUSH_EASE = 5        # a push comes on and goes off over this many frames


def to_blender(p):
    return Vector((p[0], -p[2], p[1]))


def from_blender(v):
    return (v.x, v.z, -v.y)


def recipe_of(run):
    path = os.path.join(run, "lowpoly_build.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def body_card(source, recipe):
    """A character's card: rig.py's joints, measurements and limits (as the fight kit reads one)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=source)
    if any(o.type == "MESH" and o.get("forge") == "gear" for o in bpy.context.scene.objects):
        apply_motion.run_script("drape.py", {"pieces": recipe["pieces"] if recipe else None, "rings": False})
    record = apply_motion.run_script("rig.py", {"recipe": recipe["pieces"] if recipe else None, "template": blockout_recipe.wardrobe_template(bpy.data.materials)})
    rig = bpy.data.objects[record["rig"]]
    return moves.card_of(record, {"fist_m": round(0.5 * rig.data.bones["hand_l"].length, 4)})


def where(rig, bone, along=0.0):
    """A point on a bone of the rig as it is posed on this frame, in the scene: its head, or part of the way to its tail."""
    shown = rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
    b = shown.pose.bones[bone]
    return shown.matrix_world @ (b.head + (b.tail - b.head) * along)


def add_board(rig, ground):
    """The skateboard under the feet, on a bone of its own, and the bone that carries rider and board along the ride.
    Returns the board's mesh."""
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=board.GLB)
    new = [o for o in bpy.context.scene.objects if o not in before]
    mesh = max((o for o in new if o.type == "MESH"), key=lambda o: len(o.data.polygons))
    for o in new:
        if o is not mesh:
            bpy.data.objects.remove(o)
    apply_motion_painted(mesh)
    roots = [b.name for b in rig.data.bones if b.parent is None]
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    carry = rig.data.edit_bones.new("ride")
    carry.head, carry.tail, carry.roll = ground, ground + Vector((0.0, 0.1, 0.0)), 0.0
    under = rig.data.edit_bones.new("board")
    under.head, under.tail, under.roll = ground, ground + Vector((0.0, 0.1, 0.0)), 0.0
    under.parent, under.use_connect = carry, False
    for name in roots:
        rig.data.edit_bones[name].parent = carry
        rig.data.edit_bones[name].use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    mesh.parent = rig
    mesh.matrix_world = rig.matrix_world @ Matrix.Translation(ground)
    group = mesh.vertex_groups.new(name="board")
    group.add(range(len(mesh.data.vertices)), 1.0, "REPLACE")
    mesh.modifiers.new("Armature", "ARMATURE").object = rig
    mesh.name = "prop: skateboard"
    mesh["forge"], mesh["prop"] = "prop", "skateboard"
    return mesh


def apply_motion_painted(mesh):
    """The board carries its colors on its corners: give it a material that shows them (as a set's block-out gets one when it is filmed)."""
    if not mesh.data.color_attributes or any(slot.material for slot in mesh.material_slots):
        return
    mat = bpy.data.materials.new("skateboard")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    paint = nodes.new("ShaderNodeAttribute")
    paint.attribute_name = mesh.data.color_attributes[0].name
    links.new(paint.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
    nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
    mesh.data.materials.append(mat)


def carried(row):
    """Where a frame of the ride puts the board's frame, in the scene: a 4x4 from the board's axes (x nose, y heel side, z up off the deck)."""
    nose, up = to_blender(row["nose"]), to_blender(row["up"])
    side = up.cross(nose)
    out = Matrix((nose, side, up)).transposed().to_4x4()
    out.translation = to_blender(row["at"])
    return out


def key_ride(rig, rows, ground):
    """Keys the "ride" bone on every frame so that the board's frame (at `ground` in the rig) is where the ride says."""
    rest = rig.data.bones["ride"].matrix_local.copy()
    pose = rig.pose.bones["ride"]
    pose.rotation_mode = "QUATERNION"
    last = None
    for f, row in enumerate(rows):
        want = rig.matrix_world.inverted() @ carried(row) @ Matrix.Translation(-ground) @ rest  # where the bone is, with everything it carries
        basis = rest.inverted() @ want
        loc, rot, _ = basis.decompose()
        if last is not None and rot.dot(last) < 0:
            rot.negate()
        last = rot.copy()
        pose.location, pose.rotation_quaternion = loc, rot
        pose.keyframe_insert("location", frame=f, group="ride")
        pose.keyframe_insert("rotation_quaternion", frame=f, group="ride")
    for curve in fcurves_of(rig.animation_data.action):
        if 'pose.bones["ride"]' in curve.data_path:
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"


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


def hand_carries(rig, ride, ground):
    """A handplant: on each of its frames the board goes wherever keeps the baked hand on its spot on the coping.
    Changes the ride's frames; returns, per handplant, how far the board was moved to do it."""
    scene, out = bpy.context.scene, []
    rows = ride["frames_list"]
    for event in ride["events"]:
        if event["did"] != "handplant":
            continue
        a, b = event["from_frame"], event["to_frame"]
        hand = Vector(event["hand_on_the_coping"])
        most = 0.0
        for f in range(a, b + 1):
            scene.frame_set(f)
            palm = rig.matrix_world.inverted() @ where(rig, "hand_" + event["hand"], 0.5) - ground  # in the board's frame
            row = rows[f]
            there = Vector(ride_file.to_set((0.0, 0.0, 0.0), row["nose"], row["up"], tuple(palm)))
            want = hand - there
            u = (f - a) / float(b - a)
            w = ride_file.ease((u - 0.15) / 0.12) * ride_file.ease((0.85 - u) / 0.12)  # at the lip the board is on the wall, whatever the hand does
            at = Vector(row["at"]).lerp(want, w)
            most = max(most, (at - Vector(row["at"])).length)
            row["at"] = [round(c, 5) for c in at]
        out.append({"pass": event["pass"], "board_moved_to_keep_the_hand_on_cm": round(100 * most, 1)})
    scene.frame_set(0)
    return out


def kept_out(rig, mesh_board, ride, pipe, ground):
    """Off the ramp, where a trick's pose would put part of him in it. On every frame he is not riding (an air, a
    handplant, and the few frames each side) the baked body is looked at where the ride puts it; if any of it is
    in the wood, the board and he with it are moved the short way out: along the way the surface faces there.
    What is asked of each frame is evened out over the frames round it, so the push comes on and goes off.
    While a hand is planted, that hand and forearm are left out: they are on the coping. Riding, nothing is
    moved: the wheels belong on the surface. Changes the ride's frames; returns what it did.
    Run before the ride is keyed (the rig's own space is then the board's frame)."""
    scene = bpy.context.scene
    rows, events = ride["frames_list"], ride["events"]
    skinned = [o for o in scene.objects if o.type == "MESH" and o.find_armature() == rig and not o.hide_render]
    carried_by = {}
    for obj in skinned:  # which bone mostly carries each point
        names = [g.name for g in obj.vertex_groups]
        carried_by[obj.name] = [max(((g.weight, names[g.group]) for g in v.groups), default=(0.0, ""))[1] for v in obj.data.vertices]
    free = [f for f, row in enumerate(rows) if row["kind"] in ("air", "plant")]
    wanted = sorted({g for f in free for g in range(f - PUSH_EASE, f + PUSH_EASE + 1) if 0 <= g < len(rows)})
    planted = {}
    for e in events:
        if e["did"] == "handplant":
            for f in range(e["hand_on_from_frame"] - 3, e["hand_off_at_frame"] + 4):
                planted[f] = {"hand_" + e["hand"], "forearm_" + e["hand"]}
    need = {}
    for f in wanted:
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
        points = []
        for obj in skinned:
            shown = obj.evaluated_get(deps)
            me = shown.to_mesh()
            here = rig.matrix_world.inverted() @ shown.matrix_world
            skip = planted.get(f, ())
            owners = carried_by[obj.name]
            for v in me.vertices:
                if v.index < len(owners) and owners[v.index] in skip:
                    continue
                points.append(tuple(here @ v.co - ground))
            shown.to_mesh_clear()
        row, push = rows[f], Vector((0.0, 0.0, 0.0))
        for again in range(PUSH_ROUNDS):
            at = [row["at"][i] + push[i] for i in range(3)]
            deepest, way = 0.0, None
            for p in points:
                x, y, z = ride_file.to_set(at, row["nose"], row["up"], p)
                deep, out = pipe.way_out(x, y, z)
                if deep > deepest:
                    deepest, way = deep, out
            if deepest <= PUSH_CLEAR:
                break
            push += Vector((way[0], way[1], 0.0)) * (deepest + PUSH_CLEAR)
        need[f] = push
    moved, most, most_at = {}, 0.0, None
    for f in wanted:
        if rows[f]["kind"] not in ("air", "plant"):
            continue  # riding, the board stays on the surface
        best = need[f]
        for k in range(1, PUSH_EASE + 1):
            share = 1.0 - k / (PUSH_EASE + 1.0)
            share = share * share * (3.0 - 2.0 * share)
            for g in (f - k, f + k):
                if g in need and (need[g] * share).length > best.length:
                    best = need[g] * share
        if best.length > 1e-4:
            moved[f] = best
            if best.length > most:
                most, most_at = best.length, f
    for f, push in moved.items():
        rows[f]["at"] = [round(rows[f]["at"][i] + push[i], 5) for i in range(3)]
    scene.frame_set(0)
    return {"frames_looked_at": len(wanted), "frames_moved": len(moved), "most_cm": round(100 * most, 1), "most_frame": most_at,
            "deepest_before_cm": round(100 * max([n.length for n in need.values()] + [0.0]), 1)}


def measure(rig, mesh_board, ride, pipe, ground, animation):
    """The baked file, looked at in the set: the wheels against the ramp, the feet against the deck, everything against the ramp's solid, the hands in the tricks."""
    scene = bpy.context.scene
    rows, events = ride["frames_list"], ride["events"]
    skinned = [o for o in scene.objects if o.type == "MESH" and o.find_armature() == rig and not o.hide_render]
    wheels = [Vector(w) for w in board.wheels()]
    spots = {tag: None for tag in ("l", "r")}
    in_trick = set()
    for e in events:
        in_trick |= set(range(e["from_frame"], e["to_frame"] + 1))
    kick = set()
    for e in events:
        if e["did"] == "kickturn":
            kick |= set(range(e["from_frame"], e["to_frame"] + 1))
    out = {"wheels_off_the_surface_cm": 0.0, "back_wheels_off_the_surface_cm": 0.0, "wheels_frame": None, "feet": {}, "in_the_ramp": {}, "grabs": [], "handplants": []}
    foot = {tag: {"off_the_deck_cm": 0.0, "from_its_spot_cm": 0.0} for tag in ("l", "r")}
    deepest = {}
    toe_rest = {tag: rig.data.bones["toe_" + tag].head_local.z - ground.z for tag in ("l", "r")}
    grab_frames = {}
    for e in events:
        if e["did"] == "air grab" and e.get("held_frames"):
            for f in range(e["held_frames"][0], e["held_frames"][1] + 1):
                grab_frames[f] = e
    grab_seen, plant_seen = {}, {}
    to_rig = None
    for f, row in enumerate(rows):
        look = f % EVERY == 0 or f in in_trick
        if not look:
            continue
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
        shown = rig.evaluated_get(deps)
        carry = shown.matrix_world @ shown.pose.bones["board"].matrix @ rig.data.bones["board"].matrix_local.inverted() @ Matrix.Translation(ground)  # the board's frame, in the scene
        back = carry.inverted()
        # The wheels against the ramp, while he is riding it.
        if row["kind"] in ("ride", "stop"):
            for k, wheel in enumerate(wheels):
                x, y, z = from_blender(carry @ wheel)
                off = abs(pipe.where(x, y, carry_on=True)[1])
                if k >= 2 and off > out["back_wheels_off_the_surface_cm"] / 100.0:
                    out["back_wheels_off_the_surface_cm"] = round(100 * off, 2)
                if f not in kick and off > out["wheels_off_the_surface_cm"] / 100.0:
                    out["wheels_off_the_surface_cm"], out["wheels_frame"] = round(100 * off, 2), f
        # The feet against the deck: the ball of each foot, in the board's frame.
        for tag in ("l", "r"):
            ball = back @ where(rig, "toe_" + tag)
            if spots[tag] is None:
                spots[tag] = ball.copy()
            foot[tag]["off_the_deck_cm"] = max(foot[tag]["off_the_deck_cm"], round(100 * abs(ball.z - toe_rest[tag]), 2))
            foot[tag]["from_its_spot_cm"] = max(foot[tag]["from_its_spot_cm"], round(100 * math.hypot(ball.x - spots[tag].x, ball.y - spots[tag].y), 2))
        # Everything against the ramp's solid.
        for obj in skinned:
            evaluated = obj.evaluated_get(deps)
            me = evaluated.to_mesh()
            world = evaluated.matrix_world
            worst = 0.0
            for v in me.vertices:
                x, y, z = from_blender(world @ v.co)
                deep = pipe.inside(x, y, z)
                if deep > worst:
                    worst = deep
            evaluated.to_mesh_clear()
            name = "the board" if obj is mesh_board else obj.name
            if worst > deepest.get(name, (0.0, None))[0]:
                deepest[name] = (worst, f)
        # A grabbing hand against the board's edge; the planted hand against the coping.
        if f in grab_frames:
            e = grab_frames[f]
            palm = back @ where(rig, "hand_r", 0.5)
            grab_seen.setdefault(e["pass"], []).append(100 * (palm - Vector(e["grab"]["spot"])).length)
        if row["kind"] == "plant":
            e = next(e for e in events if e["did"] == "handplant" and e["from_frame"] <= f <= e["to_frame"])
            if e["hand_on_from_frame"] <= f <= e["hand_off_at_frame"]:
                palm = Vector(from_blender(where(rig, "hand_" + e["hand"], 0.5)))
                plant_seen.setdefault(e["pass"], []).append((f, 100 * (palm - Vector(e["hand_on_the_coping"])).length))
    scene.frame_set(0)
    out["feet"] = foot
    out["in_the_ramp"] = {name: {"deepest_cm": round(100 * deep, 2), "frame": f} for name, (deep, f) in sorted(deepest.items())}
    out["deepest_in_the_ramp_cm"] = round(100 * max([d for d, _ in deepest.values()] or [0.0]), 2)
    for number, seen in sorted(grab_seen.items()):
        seen = sorted(seen)
        out["grabs"].append({"pass": number, "hand_from_the_edge_cm": {"least": round(seen[0], 1), "typical": round(seen[len(seen) // 2], 1), "most": round(seen[-1], 1)}})
    for number, seen in sorted(plant_seen.items()):
        every = sorted(d for f, d in seen)
        out["handplants"].append({"pass": number, "frames": [seen[0][0], seen[-1][0]], "hand_from_the_coping_cm": {"typical": round(every[len(every) // 2], 1), "most": round(every[-1], 1)}})
    c = animation["check"]
    out["on_the_deck"] = {"through_the_deck_cm": c["through_floor_cm"], "lowest_part": c["lowest_part"], "a_planted_foot_strays_cm": c["planted_foot_strays_cm"]}
    out["limits"] = {"turns_outside_a_limit": c["limit_violations"], "clamped": animation["clamped"]}
    return out


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    script_file, out = os.path.abspath(args[0]), os.path.abspath(args[1])
    run = os.path.abspath(args[args.index("--character") + 1])
    shots = os.path.abspath(args[args.index("--shots") + 1]) if "--shots" in args else None
    os.makedirs(out, exist_ok=True)
    with open(script_file) as f:
        script = json.load(f)
    versions = args[args.index("--versions") + 1].split(",") if "--versions" in args else [(script.get("rider") or {}).get("version", "lowpoly")]
    recipe = recipe_of(run)
    pipe = Pipe.of_set(script.get("set", "halfpipe"))
    if not os.path.exists(board.GLB):
        sys.exit("there is no skateboard yet (%s): just skate-board builds it" % os.path.relpath(board.GLB, REPO))

    measured_on, kept = {}, None
    for version in versions:
        source = os.path.join(run, VERSION_FILES[version])
        if not os.path.exists(source):
            print("RIDE %s: skipped, no %s" % (version, source))
            continue
        # 1. The body, in the version that rides.
        card = body_card(source, recipe)
        with open(os.path.join(out, "rider.body.json"), "w") as f:
            json.dump(card, f, indent=1)
        body = moves.Body(card)
        print("RIDE body %s: %.2f m tall, hips at %.2f m, arm %.2f m" % (version, body.tall, body.leg, body.arm))
        # 2. The run, laid out for this body.
        made = ride_file.build(script, body, pipe, shots=shots, log=lambda line: print("RIDE " + line))
        ride, motion = made["ride"], made["motion"]
        with open(os.path.join(out, "rider.motion.json"), "w") as f:
            json.dump(motion, f)
        for line in ride_file.said(ride):
            print("RIDE " + line)
        # 3. The rider, baked on his board.
        record = {"version": version, "motion": "ride", "character": source, "ride": os.path.basename(script_file)}
        record.update(apply_motion.fit(source, motion, "ride", recipe))
        rig = bpy.data.objects[record["rig"]["rig"]]
        hips = rig.data.bones["hips"].head_local
        ground = Vector((hips.x, hips.y, record["rig"]["measure"].get("floor", 0.0)))  # the middle of the top of the deck, in the rig
        # 4. The board, and the ride.
        scene = bpy.context.scene
        scene.frame_set(0)
        before = where(rig, "hand_l").copy()
        mesh_board = add_board(rig, ground)
        scene.frame_set(1)
        scene.frame_set(0)
        moved = (where(rig, "hand_l") - before).length
        if moved > 1e-4:
            sys.exit("putting the ride bone above the hips moved the character by %.4f m: the bake no longer holds" % moved)
        record["handplants"] = hand_carries(rig, ride, ground)
        record["kept_out_of_the_ramp"] = kept_out(rig, mesh_board, ride, pipe, ground)
        key_ride(rig, ride["frames_list"], ground)
        ride["measured"] = ride_file.measure(ride, pipe)
        record["measured"] = measure(rig, mesh_board, ride, pipe, ground, record["animation"])
        record["measured"]["handplant_board_moved"] = record["handplants"]
        record["measured"]["moved_out_of_the_ramp"] = record["kept_out_of_the_ramp"]
        record["measured"]["pose_from"] = [dict({k: v for k, v in e["pose_from_result"].items() if k != "said"}, **{"pass": e["pass"]}) for e in ride["events"] if e.get("pose_from_result")]
        measured_on[version] = record["measured"]
        flat = False
        made_as = os.path.join(run, "profiles", version + ".json")
        if os.path.exists(made_as):
            with open(made_as) as f:
                flat = bool(json.load(f).get("flat_colors"))
        glb = os.path.join(out, "%s-ride.glb" % version)
        apply_motion.write(record, glb, materials=not flat)
        with open(os.path.join(out, "%s-ride.json" % version), "w") as f:
            json.dump(record, f, indent=1)
        m, a = record["measured"], record["animation"]
        print("RIDE %s: %d frames, clamped %s, %d turns outside a limit, %.2f MB -> %s" % (version, a["frames"] + 1, json.dumps(a["clamped"]), m["limits"]["turns_outside_a_limit"], record["bytes"] / 1e6, glb))
        print("RIDE %s: wheels off the surface %.2f cm at most while riding (back wheels %.2f cm, kickturns included)" % (version, m["wheels_off_the_surface_cm"], m["back_wheels_off_the_surface_cm"]))
        print("RIDE %s: feet: %s; through the deck %.2f cm (%s)" % (version, json.dumps(m["feet"]), m["on_the_deck"]["through_the_deck_cm"], m["on_the_deck"]["lowest_part"]))
        print("RIDE %s: deepest in the ramp %.2f cm: %s" % (version, m["deepest_in_the_ramp_cm"], json.dumps(m["in_the_ramp"])))
        k = m["moved_out_of_the_ramp"]
        print("RIDE %s: moved out of the ramp on %d frames, %.1f cm at most (frame %s)" % (version, k["frames_moved"], k["most_cm"], k["most_frame"]))
        for row in m["grabs"]:
            print("RIDE %s: pass %d, the grabbing hand is %s cm from the board's edge" % (version, row["pass"], json.dumps(row["hand_from_the_edge_cm"])))
        for row in m["handplants"]:
            print("RIDE %s: pass %d, the planted hand is %s cm from its spot on the coping" % (version, row["pass"], json.dumps(row["hand_from_the_coping_cm"])))
        if kept is None:  # ride.json is the run as the first version rides it; the others add what was measured on them
            kept = ride
            kept["rider"] = {"character": "runs/%s/%s" % (os.path.basename(run), VERSION_FILES[version]), "version": version}
            kept["title"], kept["about_the_run"] = script.get("title"), script.get("about")
        kept["measured_on"] = measured_on
        with open(os.path.join(out, "ride.json"), "w") as f:
            json.dump(kept, f)
    print("RIDE wrote", os.path.join(out, "ride.json"))


main()
