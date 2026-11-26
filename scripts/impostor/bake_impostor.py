"""Cuts a rigged character into rigid parts, one per bone, and pictures each part from all around.

    Blender -b --factory-startup -P scripts/impostor/bake_impostor.py -- <run> <profile>
        [--look comic|pixel|joe] [--dress auto|off] [--head-px 2] [--creases head|none] [--head-colours 16] [--face auto|none|FILE] [--plays painted] [--title "Detailed model"] [--soften 128] [--views 26,62] [--px 192] [--lap 0.4] [--ball 0.9] [--smooth-cm 2] [--overlap 0.25] [--trunk-overlap 0.04] [--held 1.35] [--ink-cm 1.4] [--rest-pose] [--out DIR] [--name impostor-comic-joined] [--bent knee,elbow] [--bends 0,45,90,120,150] [--layers 2] [--round-the-back] [--eyes 20,40] [--eyes-round 6]

Reads <run>/profiles/<profile>-walk.glb (the file the page plays, so a bone's frame here is exactly
its frame there) and writes <run>/profiles/<profile>-impostor-<look>-joined/ (pages older than the mended
joints read <profile>-impostor/ and <profile>-impostor-<look>/, which this leaves alone; pixel art goes into
<profile>-impostor-pixel-clear/, and the -pixel-joined/ sheet from before faces were made clear is left alone too):

    impostor.json            the parts, their bones, the view sets, where each picture is on its sheet
                             ("cells": x, y, wide, tall on the sheet from its bottom left; where the bone's
                             head is in the picture; the lowest and highest its surface stands, in metres)
    views<N>-color.png       every part from every direction of set N: flat comic colour (no line: the page
                             paints the line's pixels itself)
    views<N>-data.png        the same pictures as numbers: which way the surface faces (red, green) and
                             how far it stands toward the eye (blue; 0 means nothing is there). A pixel of the
                             ink line round the part has 0 for both of its facing's numbers: that marks it

How a part is cut (cut_round). Every face goes to the part whose bones pull on it most (fingers fold into the
hand, toes into the foot, shoulders and neck into the chest; a bone the list does not know folds into the
nearest one above it that it does), the pull first evened out along the surface over --smooth-cm so the line
between two parts is a clean ring and not a fringe. Then two parts that meet at a joint each take everything
of the other's within reach of the ring where they meet (--lap times the ring's own radius), and the part
below the joint carries a ball in it: the faces round the ring pulled in onto a ball about the joint, --ball
of the room there is inside the body. A bend opens the outside of a joint; the ball is what shows through,
and it never pokes out, where a lap long enough to close a bent knee would stand out as a spur. A part also
takes the faces next door that its own bones still pull on by at least --overlap (--trunk-overlap for the hips,
spine, chest and head): that is how the skin under an arm goes up with the arm. At a shoulder neither card takes
anything of the other's further than --held rings from the joint (1.35: the shoulder's zone, where a piece of the
model is drawn and both cards step aside): an arm swung overhead carried what its card took from the chest round
with it, and the side of her top stood in the air above her shoulder (README: "Shoulders that hold"). --lap 0 cuts the old way
instead: only that last rule, with nothing evened out.

The line round a part. Every part is pictured with its own ink line all the way round it, and the line's
pixels are marked in the data sheet. Drawn at the surface's own depth such a line crosses the figure at every
joint, where one part's edge lies on the next part. So the page either stands the line a little behind the
surface, where the part next door covers it, or leaves it out and draws one line round the whole figure on the
finished picture (gallery/looks.js).

How a part is pictured. The part is laid in its bone's own frame and drawn with no perspective from
each direction of the set (impostor.py: views_of), by toon.py with the tones of light switched off:
the flat colours and the ink line, nothing else. Light and shade are not baked in. The page works them
out from the stored facing, so a forearm is lit from the same side whichever way it is turned.
Every part of one direction is drawn in one render, each in its own square; the squares are then
trimmed to what is in them and packed onto one sheet.

A dress (chains_of, cut_round). Every part belongs to one bone, and a long skirt does not: it spans the hips and
both legs, and cut into thigh and shin cards it tears apart between the legs whenever she side-steps or lunges,
while the bones it really moves with (the swing chains cloth.py gives a loose garment, "cloth_<gear>_<chain>_<n>")
are no part at all. So a garment whose chains hang from the hips or the spine (a skirt, a dress, a robe, a coat's
tails: anything that hangs over the legs) is a part of its own, "dress", that rides the bone its chains hang from:
the chains' pull on it, and on a garment that is a mesh of its own (rig_detailed.py: "gear: <name>") the hips' and
the legs' pull too, count for the dress and not for the hips or the legs. Its card is a picture of the dress as it
hangs at rest, for the looks and the crowd; what the pages draw near by is a piece of the model itself, swung by
the chains (bake_joints.py), which the dress's card steps aside for. --dress off cuts the old way, the dress among
the hips and the legs.

--plays names the rigged version whose clips the cards play, when the one pictured is not it: a detailed mesh
given another version's skeleton (rig_detailed.py) is pictured, and the cards then play that version's walk,
routine and fights. --title is what the page calls this choice. --soften is how many pixels wide toon.py
reads a texture at (smaller is flatter; a detailed mesh wants more than a painted one).

--look bakes a sheet for one of the page's other looks, into <version>-impostor-<look>-joined/:
    pixel   pixel art, into <version>-impostor-pixel-clear/: 48 pixels a metre, no smoothing, every colour snapped
            to the 32 this character is most made of, a line one pixel wide drawn round each picture; the page
            reads it without smoothing either. The head is pictured at 192 pixels a metre whatever the body's
            (--head-px says how many times finer), has its folds drawn in one pixel wide (--creases none leaves
            them out) and may have 16 colours of its own besides (--head-colours). When the character has a recipe
            for a face drawn on this model (pixel_face.py) its marks are drawn on top; --face none leaves them off.
    joe     bold ink: no line round the parts (the page draws the outside line itself, the same width on the
            screen however small the figure), and the lines inside a part drawn into its picture

--layers 2 pictures every part two surfaces deep, into <version>-impostor-<look>-layered/ (pixel art:
-impostor-pixel-clear-layered/). A picture holds the first surface its eye met, and no more: seen from a little to
one side, what was behind that surface is a hole (the crown of a hat behind its brim's edge, a wrist inside a
cuff). So each direction is pictured again with the first surface taken away wherever something behind it could
be seen from a little to one side (behind): something that faces the picture's own eye, can be seen from outside
the part from some direction up to 40 degrees off, and is on the outside of the whole model (a model is thin
shells, and most of what lies behind a surface is the inside of one). A layer's picture is cut down to what it
holds and goes on the same two sheets; a view set's "behind" lists them as "cells" lists the first, which is
pictured exactly as it is without --layers. --round-the-back also keeps what faces away from the picture's eye
(the strip of a limb just round its edge): it filled a few more pixels, made a tenth more stick out round the
figure and the sheet much bigger, and is not what the pages have. --eyes and --eyes-round say which eyes a place
behind may be seen by: rings of them, so many degrees off the direction pictured, so many round each ring (20 and 40
degrees, 6 round each: 12 eyes; 15,30,45,60 with 12 round each is 48 eyes out to 60 degrees). A third layer (--layers 3) found next to nothing on the three dancers.

--bent pictures knees or elbows bent as well: for each, a card of its own at each of --bends degrees (the skin
of its two parts round the joint, as the real model has it bent so far, in the frame of the bone above), listed
under "bent" in impostor.json. impostor.py draws the one nearest to how far the joint is bent now, turned about
the joint by half of what is left over. It was tried against a piece of the model in every joint (bake_joints.py)
and lost (README: "A knee that bends"): the sheets grow by half, a joint is seldom at one of the bends, and a
hip or a shoulder does not bend one way. The pages do not draw it; give it a --name of its own.

Prints IMPOSTOR lines and one RESULT {json}. Never touches an open Blender.
"""

import json
import math
import os
import sys
import time

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import impostor  # noqa: E402
import pixel_face  # noqa: E402

TOON = os.path.join(REPO, ".claude", "skills", "tidy-mesh", "scripts", "toon.py")
# The parts, and the bones each is made of. The first bone is the one the card rides on.
PARTS = [("hips", ["hips"]), ("spine", ["spine"]), ("chest", ["chest", "shoulder_l", "shoulder_r", "neck"]), ("head", ["head"])]
for side in ("l", "r"):
    PARTS += [("upper_arm_" + side, ["upper_arm_" + side]), ("forearm_" + side, ["forearm_" + side]), ("hand_" + side, ["hand_" + side]),
              ("thigh_" + side, ["thigh_" + side]), ("shin_" + side, ["shin_" + side]), ("foot_" + side, ["foot_" + side, "toe_" + side])]
TO_GLB = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))  # Blender's z-up to a .glb's y-up
EYE_AWAY = 10.0   # how far off the eye stands while picturing (m); nothing depends on it
GUTTER = 2        # empty pixels between pictures on a sheet
ROW_PX = 1400     # how wide one render of all the parts may be
HEAD_PPM = 192.0  # pixel art pictures a head this fine
CREASE = 0.42     # a fold drawn into a pixel-art head is the colour under it times this
TRUNK = ("hips", "spine", "chest", "head")  # thick parts that hardly bend against each other: they lap over each other much further
HANG = ("shoulder", "upper_arm", "forearm", "hand")  # the bones that are pictured as they hang in the clip, not as they rest


def hang_arms(scene, rig):
    """Stand the skeleton as it is pictured: at rest, but with the arms where they are on average through the
    file's own clip. A rig rests with its arms straight out; nobody walks or fights like that, and a part is only
    exact near the pose it was cut in, so the arms are cut hanging. Returns how far each upper arm was lowered (deg)."""
    action = rig.animation_data.action if rig.animation_data else None
    first, last = (int(action.frame_range[0]), int(action.frame_range[1])) if action else (0, 0)
    arms = [b for b in rig.pose.bones if b.name.startswith(HANG)]
    total = {b.name: np.zeros(4) for b in arms}
    for f in range(first, last + 1):
        scene.frame_set(f)
        for b in arms:
            q = np.array(b.rotation_quaternion[:]) if b.rotation_mode == "QUATERNION" else np.array(b.rotation_euler.to_quaternion()[:])
            total[b.name] += q if q @ (total[b.name] if total[b.name].any() else q) >= 0 else -q
    if rig.animation_data:
        rig.animation_data_clear()
    lowered = {}
    for b in rig.pose.bones:
        b.location, b.scale = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
        b.rotation_mode = "QUATERNION"
        q = total.get(b.name)
        b.rotation_quaternion = tuple(q / np.linalg.norm(q)) if q is not None and q.any() else (1.0, 0.0, 0.0, 0.0)
        if b.name.startswith("upper_arm"):
            lowered[b.name] = round(math.degrees(2.0 * math.acos(min(1.0, abs(b.rotation_quaternion[0])))), 1)
    bpy.context.view_layer.update()
    return lowered


BENT_KINDS = {"shin": "knee", "forearm": "elbow"}  # the joints that can be pictured bent: the ones that bend one way
BENT_ZONE = {"knee": 1.6, "elbow": 1.7}            # a joint's zone, as bake_joints.py has it: this many times the ring where its two parts meet
BENT_LAP_M = 0.015


def hinges(scene, rig, bones):
    """Which way each of some bones bends, found in the file's own clip: {bone: the axis it turns about, in its own
    frame, turning the way it bends}. The moment of the clip where the bone is turned furthest from where it is on
    average says so. Call before hang_arms, which puts the clip away."""
    action = rig.animation_data.action if rig.animation_data else None
    first, last = (int(action.frame_range[0]), int(action.frame_range[1])) if action else (0, 0)
    seen = {b: [] for b in bones if b in rig.pose.bones}
    for f in range(first, last + 1):
        scene.frame_set(f)
        for b in seen:
            pb = rig.pose.bones[b]
            seen[b].append(pb.rotation_quaternion.copy() if pb.rotation_mode == "QUATERNION" else pb.rotation_euler.to_quaternion())
    out = {}
    for b, turns in seen.items():
        total = np.zeros(4)
        for q in turns:
            total += np.array(q[:]) if np.array(q[:]) @ (total if total.any() else np.array(q[:])) >= 0 else -np.array(q[:])
        mean = Quaternion(tuple(total / max(np.linalg.norm(total), 1e-9)))
        # a knee and an elbow are straightest at one end of what the clip does and bent at the other: the axis is
        # that of the turn from the straightest moment to the most bent
        along = lambda q: abs((rig.pose.bones[b].parent.bone.matrix_local.to_3x3().inverted() @ rig.pose.bones[b].bone.matrix_local.to_3x3() @ q.to_matrix() @ Vector((0, 1, 0))).normalized().y)
        straight, bent = max(turns, key=along), min(turns, key=along)
        delta = straight.inverted() @ bent
        axis, angle = delta.to_axis_angle()
        out[b] = (tuple(axis) if angle >= 0 else tuple(-axis), tuple(straight), math.degrees(abs(angle)))
    return out


def run_toon(**params):
    with open(TOON) as f:
        source = f.read()
    space = {"__name__": "__main__"}
    head, _, tail = source.partition("\nimport ")
    exec(head, space)
    space["PARAMS"].update(params)
    exec("import " + tail, space)


def part_of_bone(rig, dress=None):
    """{bone name: part name}: a bone no part names folds into the nearest bone above it that one does. With a
    dress (chains_of), its chains' bones are the dress's."""
    known = {bone: name for name, bones in PARTS for bone in bones}
    out = {}
    for bone in rig.data.bones:
        up = bone
        while up is not None and up.name not in known:
            up = up.parent
        out[bone.name] = known[up.name] if up is not None else "hips"
    for bone in (dress or {}).get("bones", []):
        out[bone] = "dress"
    return out


# a swing chain's bone, the parts its chains may hang from, a garment's name as its chains carry it, and the dress
# a skeleton has (impostor.py: chains_of, with no Blender in it)
CHAIN, DRESS_ROOTS, slug_of, chains_of = impostor.CHAIN, impostor.DRESS_ROOTS, impostor.slug_of, impostor.chains_of
DRESS_LEGS = ("thigh_l", "thigh_r", "shin_l", "shin_r")  # ... and on a garment that is a mesh of its own, the legs' pull on it is the dress's too


def note_of(rig):
    """A Blender skeleton's own description of what it wears loose (cloth.py's "forge_cloth"), or None."""
    try:
        return json.loads(rig.get("forge_cloth") or "null")
    except (TypeError, ValueError):
        return None


def garments_of(rig, note=None):
    """impostor.garments_of for a Blender skeleton. note: the description to read it by, when the skeleton carries
    none of its own (a detailed model given a tidy version's skeleton: that version's, impostor.note_in)."""
    folds = part_of_bone(rig)
    return impostor.garments_of([b.name for b in rig.data.bones], lambda n: rig.data.bones[n].parent.name if rig.data.bones[n].parent else None, lambda n: folds.get(n), note_of(rig) or note)


def dress_of(rig, note=None):
    """chains_of for a Blender skeleton (note: as garments_of)."""
    folds = part_of_bone(rig)
    return chains_of([b.name for b in rig.data.bones], lambda n: rig.data.bones[n].parent.name if rig.data.bones[n].parent else None, lambda n: folds.get(n), note_of(rig) or note)


def worn_dress(obj, dress):
    """Whether an object is a garment the dress's chains swing (a mesh of its own: "gear: ruffled skirt")."""
    gear = obj.get("gear") or (obj.name[len("gear: "):].split(".")[0] if obj.name.startswith("gear: ") else None)
    return bool(dress and gear and any(s == slug_of(gear) or s.startswith(slug_of(gear) + "_") for s in dress["garments"]))


def groups_of(obj, folds, dress=None):
    """The part each of an object's vertex groups pulls for. On a garment the dress swings, the hips' and the legs'
    pull counts for the dress: the skirt rides them only as the dress does."""
    worn = worn_dress(obj, dress)
    root = folds.get(dress["root"]) if dress else None
    return [("dress" if worn and folds.get(g.name) in (root, "dress") + DRESS_LEGS else folds.get(g.name)) for g in obj.vertex_groups]


def parts_with(dress):
    """The parts, and the dress's if there is one: it rides the bone its chains hang from."""
    return PARTS + ([("dress", [dress["root"]] + dress["bones"])] if dress else [])


def cut(objects, rig, overlap, trunk_overlap, dress=None):
    """{part name: [(object, [face indices], lapped over from next door?)]} and how many triangles each part owns outright."""
    folds = part_of_bone(rig, dress)
    names = [name for name, _ in parts_with(dress)]
    column = {name: i for i, name in enumerate(names)}
    out, own = {name: [] for name in names}, {name: 0 for name in names}
    for obj in objects:
        me = obj.data
        pull = np.zeros((len(me.vertices), len(names)), dtype=np.float32)
        groups = groups_of(obj, folds, dress)
        for v in me.vertices:
            for g in v.groups:
                part = groups[g.group]
                if part is not None:
                    pull[v.index, column[part]] += g.weight
        pull /= np.maximum(pull.sum(axis=1, keepdims=True), 1e-9)
        chosen, lapped = {name: [] for name in names}, {name: [] for name in names}
        for poly in me.polygons:
            share = pull[list(poly.vertices)].mean(axis=0)
            best = int(share.argmax())
            own[names[best]] += len(poly.vertices) - 2
            chosen[names[best]].append(poly.index)
            for i, name in enumerate(names):
                if i != best and share[i] >= (trunk_overlap if name in TRUNK else overlap):
                    lapped[name].append(poly.index)
        for name in names:
            if chosen[name]:
                out[name].append((obj, chosen[name], False))
            if lapped[name]:
                out[name].append((obj, lapped[name], True))
    return out, own


def joints_of(rig):
    """[(a part, the part it hangs from, the bone whose head is the joint between them)], as the skeleton has them."""
    folds = part_of_bone(rig)
    out = []
    for name, bones in PARTS:
        for b in bones:
            bone = rig.data.bones.get(b)
            if bone is not None and bone.parent is not None and folds[bone.parent.name] != name:
                out.append((name, folds[bone.parent.name], b))
    return out


HELD = 1.35     # at a shoulder, what the arm's card takes from the chest stays within this many rings of the joint: the shoulder's zone (bake_joints.py), where a piece of the model is drawn
HELD_JOINTS = ("upper_arm_l", "upper_arm_r", "head")  # the joints it holds at: the ball joints an arm swings overhead about, and the head's on its neck
HELD_ABOVE = 1.0  # ... and what the card above the joint (the chest) takes from the one below stays within this many: less, because the
                  # joint itself moves off it. An arm going up lifts its collar bone and its joint a few centimetres with it, and the
                  # arm's skin the chest's card kept was left behind, outside the zone that had moved on, as a flap under the arm. A head
                  # tipped back leaves the neck skin its card took from the chest standing out from her throat as a jagged collar.


def cut_round(objects, rig, posed, lap, smooth_m, ball=0.9, overlap=0.25, trunk_overlap=0.04, head_lap=0.3, dress=None, held=0.0):
    """The cut made fit for a joint to bend (impostor.py: round_cut has the account of it): {part name: [(object,
    [face indices], lapped over from next door?, the ball these faces are pulled onto or None)]}, how many
    triangles each part owns outright, and what each joint was given. The pull is evened out along the surface
    over smooth_m; two parts that meet at a joint each reach `lap` times the ring's radius into the other; and the
    part below the joint carries a ball in it, `ball` of the room there is. The chest takes less of the head than
    `lap` (head_lap): a jaw that stayed behind when the head turned would show. At a shoulder what either card
    takes by pull alone stays within `held` rings of the joint (0: as far as the pull goes, the cut as it was): an
    arm swung overhead carries what its card took from the chest round with it, and skin from down her side stood
    up in the air above the shoulder (README: "Shoulders that hold"). Points are where they stand in
    the baking pose. A dress (chains_of) is one part more, met at no joint: it neither laps nor takes a ball."""
    folds = part_of_bone(rig, dress)
    names = [name for name, _ in parts_with(dress)]
    column = {name: i for i, name in enumerate(names)}
    joints = [(a, b, bone, np.array((rig.matrix_world @ rig.pose.bones[bone].head)[:])) for a, b, bone in joints_of(rig)]
    points, pulls, edges, corners, begin, sides, spans = [], [], [], [], [], [], []
    for obj in objects:  # every object's faces, gathered into one mesh
        me = obj.data
        count, first_point, first_corner = len(me.vertices), sum(len(p) for p in points), sum(len(c) for c in corners)
        pull = np.zeros((count, len(names)), dtype=np.float32)
        groups = groups_of(obj, folds, dress)
        for v in me.vertices:
            for g in v.groups:
                part = groups[g.group]
                if part is not None:
                    pull[v.index, column[part]] += g.weight
        at = np.empty(count * 3, dtype=np.float32)
        posed[obj.name].vertices.foreach_get("co", at)
        points.append(at.reshape(count, 3) @ np.array(obj.matrix_world.to_3x3()).T + np.array(obj.matrix_world.translation[:]))
        pulls.append(pull)
        got = np.empty(len(me.edges) * 2, dtype=np.int64)
        me.edges.foreach_get("vertices", got)
        edges.append(got.reshape(-1, 2) + first_point)
        got = np.empty(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", got)
        corners.append(got + first_point)
        start, many = np.empty(len(me.polygons), dtype=np.int64), np.empty(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get("loop_start", start)
        me.polygons.foreach_get("loop_total", many)
        spans.append((obj, sum(len(x) for x in sides), len(many)))
        begin.append(start + first_corner)
        sides.append(many)
    sides = np.concatenate(sides)
    owner, lapped, rings, balls = impostor.round_cut(np.concatenate(points), np.concatenate(pulls), np.concatenate(edges), np.concatenate(corners), np.concatenate(begin), sides,
                                                     [(column[a], column[b], centre) for a, b, _, centre in joints], lap, smooth_m, {(column["chest"], column["head"]): head_lap}, ball,
                                                     pulled=[trunk_overlap if name in TRUNK else overlap for name in names],
                                                     held=dict(pair for a, b, bone, _ in joints if bone in HELD_JOINTS for pair in (((column[a], column[b]), held), ((column[b], column[a]), held * HELD_ABOVE / HELD))) if held > 0 else None)
    out, own = {name: [] for name in names}, {name: 0 for name in names}
    for obj, start, many in spans:
        mine = owner[start:start + many]
        for i, name in enumerate(names):
            own[name] += int((sides[start:start + many][mine == i] - 2).sum())
            if (mine == i).any():
                out[name].append((obj, np.nonzero(mine == i)[0].tolist(), False, None))
            if lapped[i, start:start + many].any():
                out[name].append((obj, np.nonzero(lapped[i, start:start + many])[0].tolist(), True, None))
        for a, b, _, centre in joints:  # the ball rides the part below the joint: that part turns about the ball's own middle
            size, made = balls.get((column[a], column[b]), (0.0, None))
            if made is not None and size > 0.005 and made[start:start + many].any():
                out[a].append((obj, np.nonzero(made[start:start + many])[0].tolist(), True, (centre, size)))
    said = [{"bone": bone, "between": [a, b], "ring_cm": round(rings[(column[a], column[b])] * 100, 1), "lap_cm": round(rings[(column[a], column[b])] * lap * 100, 1),
             "ball_cm": round(balls.get((column[a], column[b]), (0.0, None))[0] * 100, 1)}
            for a, b, bone, _ in joints if (column[a], column[b]) in rings]
    return out, own, said


def piece(obj, posed, faces, into, ball=None):
    """A copy of some of an object's faces, as they stand in the baking pose (`posed`: the mesh with the
    skeleton's pull already in its points), moved by the matrix `into`. ball (a middle and a radius, in the
    scene): the faces' points are first pulled in onto that ball, the ones that were further out landing a hair
    further out, so of two layers (a coat over a shirt) the outer one still shows."""
    data = posed.copy()
    bm = bmesh.new()
    bm.from_mesh(data)
    bm.faces.ensure_lookup_table()
    keep = set(faces)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
    bm.to_mesh(data)
    bm.free()
    if ball is not None:
        middle, radius = Vector(ball[0]), ball[1]
        back = obj.matrix_world.inverted()
        for v in data.vertices:
            out = obj.matrix_world @ v.co - middle
            far = max(out.length, 1e-6)
            v.co = back @ (middle + out * (radius * (1.0 + 0.03 * min(1.0, far / (4.0 * radius))) / far))
    data.transform(into)
    data.update()
    new = bpy.data.objects.new("part: " + obj.name, data)
    bpy.context.scene.collection.objects.link(new)
    return new


def data_material(name, ink):
    """Paints which way a surface faces, as the eye sees it (red: right, green: up), and how far it stands
    toward the eye from the bone's head (blue), all as plain numbers around a half. The ink line's own
    version paints nothing (black): that is how its pixels are told from the surface's afterwards."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.use_backface_culling = ink
    tree = mat.node_tree
    tree.nodes.clear()
    if ink:
        glow, out = tree.nodes.new("ShaderNodeEmission"), tree.nodes.new("ShaderNodeOutputMaterial")
        glow.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        tree.links.new(glow.outputs[0], out.inputs["Surface"])
        return mat
    shape = tree.nodes.new("ShaderNodeNewGeometry")
    seen = tree.nodes.new("ShaderNodeVectorTransform")
    seen.vector_type, seen.convert_from, seen.convert_to = "NORMAL", "WORLD", "CAMERA"
    tree.links.new(shape.outputs["Normal"], seen.inputs[0])
    split = tree.nodes.new("ShaderNodeSeparateXYZ")
    tree.links.new(seen.outputs[0], split.inputs[0])
    eye = tree.nodes.new("ShaderNodeCameraData")

    def half(socket, scale, add):
        node = tree.nodes.new("ShaderNodeMath")
        node.operation = "MULTIPLY_ADD"
        tree.links.new(socket, node.inputs[0])
        node.inputs[1].default_value, node.inputs[2].default_value = scale, add
        return node.outputs[0]

    join = tree.nodes.new("ShaderNodeCombineXYZ")
    tree.links.new(half(split.outputs[0], 0.5, 0.5), join.inputs[0])
    tree.links.new(half(split.outputs[1], 0.5, 0.5), join.inputs[1])
    tree.links.new(half(eye.outputs["View Z Depth"], -0.5, 0.5 + 0.5 * EYE_AWAY), join.inputs[2])
    glow = tree.nodes.new("ShaderNodeEmission")
    tree.links.new(join.outputs[0], glow.inputs["Color"])
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(glow.outputs[0], out.inputs["Surface"])
    return mat


def retag(group, objects):
    """Say out loud that the ink's material changed: without this the next render still draws the last one."""
    group.update_tag()
    for obj in objects:
        obj.update_tag()
    bpy.context.view_layer.update()


def pixels_of(path, plain=False):
    image = bpy.data.images.load(path)
    if plain:
        image.colorspace_settings.name = "Non-Color"
    wide, tall = image.size
    got = np.empty(wide * tall * 4, dtype=np.float32)
    image.pixels.foreach_get(got)
    bpy.data.images.remove(image)
    return got.reshape(tall, wide, 4)


def spread(values, known, rounds):
    """Fill pixels that have no value from a neighbour that has, a ring at a time."""
    values, known = values.copy(), known.copy()
    for _ in range(rounds):
        if known.all():
            break
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            near_v = np.roll(values, (dy, dx), axis=(0, 1))
            near_k = np.roll(known, (dy, dx), axis=(0, 1))
            take = near_k & ~known
            values[take] = near_v[take]
            known = known | take
    return values


BEHIND_START_M = 0.004   # what is behind a surface is looked for from this far behind it ...
BEHIND_APART_M = 0.006   # ... and one layer of it is at least this far behind the last
BEHIND_HITS = 10         # ... among this many surfaces down a pixel's line at most
BEHIND_TILTS = (20.0, 40.0)  # a surface behind another is kept only if it can be seen from outside the part from somewhere this far (degrees) round the direction pictured ...
BEHIND_AROUND = 6        # ... this many ways round, for each
BEHIND_OFF_M = 0.0015    # ... looking from this far off the surface
BEHIND_OUT = 24          # ... and only if it is on the outside of the whole model: one of this many ways from it, all round, meets nothing
BEHIND_LEAST_CM2 = 3.3   # a patch of a layer behind is kept only if, with its thin edges and specks taken off, this much of it is left (and never under 4 pixels): a layer's picture is cut down to what it holds, and one speck far off makes it big
PEEL_MORE_M = 0.002      # picturing a layer, everything nearer than this in front of it is left out


def tree_of(objects):
    """Something to send lines through: a part's faces, as they lie in its bone's frame."""
    points, faces = [], []
    for obj in objects:
        first = len(points)
        points += [v.co.copy() for v in obj.data.vertices]
        faces += [[first + i for i in poly.vertices] for poly in obj.data.polygons]
    return BVHTree.FromPolygons(points, faces)


def whole_tree(objects, posed):
    """Every face of the model as it stands when it is cut, in the scene's own frame."""
    points, faces = [], []
    for obj in objects:
        first = len(points)
        points += [obj.matrix_world @ v.co for v in posed[obj.name].vertices]
        faces += [[first + i for i in poly.vertices] for poly in posed[obj.name].polygons]
    return BVHTree.FromPolygons(points, faces)


def behind(tree, view, height, known, half, per_m, whole=None, out_to=None, backs=False):
    """What lies behind a picture's surface that an eye a little to one side could see. A picture holds, for every
    pixel, the first surface the line through it meets. A model is thin shells one inside another (a hat's brim in
    front of its crown, a cuff round a wrist, a coat's skirt over a leg), and most of what a line meets after the
    first is the inside of something, which nobody ever sees. So for each pixel the line is followed on through
    the part (tree_of), and the first surface on it that can be seen from outside the part, from some direction
    within BEHIND_TILTS of the one pictured, is the next layer. A part is cut open at its joints, and through the
    cut its own inside can be seen: so the place must also be on the outside of the whole model (whole: whole_tree;
    out_to: the matrix from the part's bone's frame to the model as it stood). And it must face the eye that
    would see it. backs: surfaces that face away from the direction pictured count too (the strip of a limb just
    round its edge, which an eye a little to one side sees); without, only what faces the picture's own eye and
    is hidden from it by something in front. height: how high each pixel's surface stands
    toward the eye (m, from the bone's head); known: where there is one; half: the picture is 2 * half pixels
    square with the bone's head at its middle; per_m: its pixels a metre. Returns how high the next layer stands
    at each pixel, and where there is one."""
    d, r, u = Vector(view["d"]), Vector(view["r"]), Vector(view["u"])
    cone = []
    for tilt in BEHIND_TILTS:
        for k in range(BEHIND_AROUND):
            a = 2.0 * math.pi * (k + 0.5 * (tilt == BEHIND_TILTS[0])) / BEHIND_AROUND
            cone.append((d * math.cos(math.radians(tilt)) + (r * math.cos(a) + u * math.sin(a)) * math.sin(math.radians(tilt))).normalized())
    down = -d
    turn = out_to.to_3x3() if out_to is not None else None
    golden = math.pi * (3.0 - math.sqrt(5.0))
    around = [Vector((math.cos(golden * k) * math.sqrt(1.0 - z * z), z, math.sin(golden * k) * math.sqrt(1.0 - z * z))) for k, z in ((k, 1.0 - 2.0 * (k + 0.5) / BEHIND_OUT) for k in range(BEHIND_OUT))]
    out, found = np.zeros(height.shape, dtype=np.float32), np.zeros(height.shape, dtype=bool)
    cast = tree.ray_cast
    for j, i in zip(*np.nonzero(known)):
        at = float(height[j, i]) - BEHIND_START_M
        foot = r * ((i + 0.5 - half) / per_m) + u * ((j + 0.5 - half) / per_m)
        for _ in range(BEHIND_HITS):
            hit = cast(foot + d * at, down)
            if hit[0] is None:
                break
            at -= hit[3]
            if float(height[j, i]) - at >= BEHIND_APART_M:
                spot = hit[0]
                faces = hit[1]
                if (backs or faces.dot(d) > 0.02) and any(faces.dot(way) > 0.02 and cast(spot + way * BEHIND_OFF_M, way)[0] is None for way in cone):
                    stood = out_to @ spot if whole is not None else None
                    if whole is None or any(whole.ray_cast(stood + way * BEHIND_OFF_M, way)[0] is None for way in around):
                        out[j, i], found[j, i] = at, True
                        break
            at -= 1e-4
    return out, found


def patches(found, least):
    """A layer's pixels without its specks and hairs: what is left of `found` when everything one pixel thin is
    taken off (and put back round what stays), in patches of at least `least` pixels."""
    core = found.copy()
    core[1:] &= found[:-1]
    core[:-1] &= found[1:]
    core[:, 1:] &= found[:, :-1]
    core[:, :-1] &= found[:, 1:]
    core[0], core[-1], core[:, 0], core[:, -1] = False, False, False, False
    keep, seen = np.zeros_like(found), np.zeros_like(found)
    tall, wide = found.shape
    for j, i in zip(*np.nonzero(core)):
        if seen[j, i]:
            continue
        todo, patch = [(j, i)], []
        seen[j, i] = True
        while todo:
            y, x = todo.pop()
            patch.append((y, x))
            for b, a in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= b < tall and 0 <= a < wide and core[b, a] and not seen[b, a]:
                    seen[b, a] = True
                    todo.append((b, a))
        if len(patch) >= least:
            ys, xs = zip(*patch)
            keep[ys, xs] = True
    grown = keep.copy()
    grown[1:] |= keep[:-1]
    grown[:-1] |= keep[1:]
    grown[:, 1:] |= keep[:, :-1]
    grown[:, :-1] |= keep[:, 1:]
    return grown & found


def peel_group(image):
    """A node group every material is passed through while a layer behind the first is pictured: a place nearer
    the eye than the picture `image` says (how high the layer stands there, in the render's own pixels) is not
    drawn at all, so the nearest thing that is drawn is the layer. "On" 0 switches it off."""
    group = bpy.data.node_groups.new("impostor peel", "ShaderNodeTree")
    group.interface.new_socket(name="Shader", in_out="INPUT", socket_type="NodeSocketShader")
    group.interface.new_socket(name="Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    nodes, links = group.nodes, group.links
    enter, leave = nodes.new("NodeGroupInput"), nodes.new("NodeGroupOutput")
    where = nodes.new("ShaderNodeTexCoord")
    read = nodes.new("ShaderNodeTexImage")
    read.image, read.interpolation, read.extension = image, "Closest", "EXTEND"
    links.new(where.outputs["Window"], read.inputs["Vector"])
    eye = nodes.new("ShaderNodeCameraData")
    high = nodes.new("ShaderNodeMath")
    high.operation = "SUBTRACT"
    high.inputs[0].default_value = EYE_AWAY
    links.new(eye.outputs["View Z Depth"], high.inputs[1])
    keep = nodes.new("ShaderNodeMath")
    keep.operation = "LESS_THAN"
    links.new(high.outputs[0], keep.inputs[0])
    far = nodes.new("ShaderNodeMath")  # (a picture holds 0 to 1: a height is kept in it as a half and a quarter of itself)
    far.operation = "MULTIPLY_ADD"
    far.inputs[1].default_value, far.inputs[2].default_value = 4.0, -2.0
    links.new(read.outputs["Color"], far.inputs[0])
    links.new(far.outputs[0], keep.inputs[1])
    on = nodes.new("ShaderNodeValue")
    on.name = "On"
    off = nodes.new("ShaderNodeMath")
    off.operation = "SUBTRACT"
    off.inputs[0].default_value = 1.0
    links.new(on.outputs[0], off.inputs[1])
    either = nodes.new("ShaderNodeMath")
    either.operation = "MAXIMUM"
    links.new(keep.outputs[0], either.inputs[0])
    links.new(off.outputs[0], either.inputs[1])
    clear, mix = nodes.new("ShaderNodeBsdfTransparent"), nodes.new("ShaderNodeMixShader")
    links.new(either.outputs[0], mix.inputs[0])
    links.new(clear.outputs[0], mix.inputs[1])
    links.new(enter.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], leave.inputs[0])
    return group


def peeled(mat, group):
    """Pass a material through the peel group, just before its output."""
    tree = mat.node_tree
    out = next((n for n in tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)
    if out is None or not out.inputs["Surface"].links or any(n.type == "GROUP" and n.node_tree == group for n in tree.nodes):
        return
    was = out.inputs["Surface"].links[0].from_socket
    node = tree.nodes.new("ShaderNodeGroup")
    node.node_tree = group
    tree.links.new(was, node.inputs[0])
    tree.links.new(node.outputs[0], out.inputs["Surface"])


def pack(sizes):
    """Shelves: [(w, h)] to ([(x, y)], sheet width, sheet height). The width is picked to leave the sheet near square."""
    area = sum((w + GUTTER) * (h + GUTTER) for w, h in sizes)
    best = None
    for wide in (256, 512, 1024, 2048, 4096):
        if wide < max(w for w, _ in sizes) + GUTTER:
            continue
        spots, x, y, shelf = [None] * len(sizes), GUTTER, GUTTER, 0
        for i in sorted(range(len(sizes)), key=lambda i: -sizes[i][1]):
            w, h = sizes[i]
            if x + w + GUTTER > wide:
                x, y, shelf = GUTTER, y + shelf + GUTTER, 0
            spots[i] = (x, y)
            x, shelf = x + w + GUTTER, max(shelf, h)
        tall = (y + shelf + GUTTER + 3) // 4 * 4
        if best is None or max(wide, tall) < max(best[1], best[2]) or (max(wide, tall) == max(best[1], best[2]) and wide * tall < best[1] * best[2]):
            best = (spots, wide, tall)
    return best + (area,)


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    run, profile = os.path.abspath(args[0]), args[1]
    look = flag("--look", "comic")
    lap, smooth_m, ball = float(flag("--lap", "0.4")), float(flag("--smooth-cm", "2")) / 100.0, float(flag("--ball", "0.9"))
    sets = flag("--views", "26,62" if look == "comic" else "26").split(",")
    ppm = float(flag("--px", "48" if look == "pixel" else "192"))
    overlap = float(flag("--overlap", "0.25"))
    trunk_overlap = float(flag("--trunk-overlap", "0.04"))
    held = float(flag("--held", str(HELD)))  # at a shoulder, how far (in rings of the joint) a card may take the other's skin by pull alone; 0: as far as the pull goes, as cards were cut before
    # pixel art: the line is one pixel of the sheet. bold ink: no line round the part at all (the page draws it)
    ink_m = float(flag("--ink-cm", str(100.0 / ppm) if look == "pixel" else "0" if look == "joe" else "1.4")) / 100.0
    colours = int(flag("--colours", "32" if look == "pixel" else "0"))
    global BEHIND_TILTS, BEHIND_AROUND
    BEHIND_TILTS, BEHIND_AROUND = tuple(float(t) for t in flag("--eyes", ",".join("%g" % t for t in BEHIND_TILTS)).split(",")), int(flag("--eyes-round", str(BEHIND_AROUND)))
    layers = max(1, int(flag("--layers", "1")))  # how many surfaces deep every picture goes: 1 is the first the eye meets and no more
    source = flag("--source", os.path.join(run, "profiles", profile + "-walk.glb"))
    # Pixel art: the head finer than the body, and a face drawn on purpose from the character's recipe.
    face = flag("--face", "auto" if look == "pixel" else "none")
    if face == "auto":
        # A recipe was drawn on one model's head and fits no other: the painted head's eyes are not where the
        # detailed head's are. Left to itself the bake uses it only for the model it says it was drawn on.
        recipe = pixel_face.recipe_for(run)
        if recipe and recipe.get("drawn_on", profile) != profile:
            print("IMPOSTOR face: the recipe was drawn on the %s model, not %s: left off (--face FILE to use one anyway)" % (recipe["drawn_on"], profile), flush=True)
            recipe = None
    elif face == "none":
        recipe = None
    else:
        with open(face) as f:
            recipe = json.load(f)
    # Pixel art pictures the head at 192 pixels a metre whatever the body's (a face needs them: "Pixels, both" draws
    # the head on a grid twice as fine as the body's), and draws the folds of the face into it, as bold ink does.
    head_px = float(flag("--head-px", str(max(1.0, round(HEAD_PPM / ppm))) if look == "pixel" else "1"))
    finer = {"head": head_px} if head_px != 1.0 else {}
    creases = flag("--creases", "head" if look == "pixel" else "none")       # which parts get their folds drawn in: head, none
    head_colours = int(flag("--head-colours", "16" if look == "pixel" else "0"))  # colours the head may have besides the sheet's own
    out = os.path.abspath(flag("--out", os.path.join(run, "profiles", "%s-%s" % (profile, flag("--name", (("impostor-pixel-clear" if look == "pixel" else "impostor-%s-joined" % look) + ("-layered" if layers > 1 else "")).replace("-joined-layered", "-layered"))))))
    os.makedirs(out, exist_ok=True)
    began = time.time()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.import_scene.gltf(filepath=source)
    rig = next(o for o in scene.objects if o.type == "ARMATURE")
    bodies = [o for o in scene.objects if o.type == "MESH" and o.find_armature() and not o.get("under")]
    rest = impostor.Glb(source).pose(None)
    bent_kinds = [k for k in flag("--bent", "").split(",") if k]  # joints pictured bent as well: knee, elbow
    bends = [float(b) for b in flag("--bends", "0,45,90,120,150").split(",")]
    hinge = hinges(scene, rig, [bones[0] for name, bones in PARTS if BENT_KINDS.get(name[:-2]) in bent_kinds]) if bent_kinds else {}
    # a garment swung by chains that hang over the legs is a part of its own (--dress off: cut among the hips and legs)
    # (what it wears is read from the skeleton's own description of it, or from that of the version whose clips these cards play)
    told = impostor.note_in(os.path.join(os.path.dirname(source), "%s-walk.glb" % flag("--plays", profile)))
    dress = dress_of(rig, told) if flag("--dress", "auto") != "off" else None
    if dress:
        print("IMPOSTOR dress: %s (%s), %d chains of %d bones hanging from %s" % (", ".join(dress["garments"]), ", ".join(str(k) for k in dress.get("kinds") or []), len(dress["chains"]), len(dress["bones"]), dress["root"]), flush=True)
    lowered = hang_arms(scene, rig) if "--rest-pose" not in args else {}
    graph = bpy.context.evaluated_depsgraph_get()
    posed = {o.name: bpy.data.meshes.new_from_object(o.evaluated_get(graph)) for o in bodies}
    model_tree = whole_tree(bodies, posed) if layers > 1 else None
    out_to = {}  # for each part, the matrix from its bone's frame back to the model as it stands here
    whole_triangles = sum(len(p.vertices) - 2 for o in bodies for p in o.data.polygons)

    # The parts, each in its bone's own frame.
    if lap > 0:
        chosen, own, joints = cut_round(bodies, rig, posed, lap, smooth_m, ball, overlap, trunk_overlap, dress=dress, held=held)
    else:
        (chosen, own), joints = cut(bodies, rig, overlap, trunk_overlap, dress), None
    parts, made = [], {}
    for name, bones in parts_with(dress):
        if not chosen[name] or bones[0] not in rest:
            continue
        # where the bone's frame is in the baking pose: the bone's own move from rest, then its rest frame
        moved = rig.pose.bones[bones[0]].matrix @ rig.data.bones[bones[0]].matrix_local.inverted()
        into = Matrix(np.linalg.inv(rest[bones[0]]).tolist()) @ TO_GLB @ moved.inverted()
        objects = []
        for obj, faces, borrowed, *onto in chosen[name]:
            objects.append(piece(obj, posed[obj.name], faces, into, onto[0] if onto else None))
            objects[-1]["lap"] = borrowed
        points = np.array([v.co[:] for o in objects for v in o.data.vertices])
        reach = float(np.linalg.norm(points, axis=1).max()) + ink_m
        lo, hi = points.min(axis=0), points.max(axis=0)
        made[name] = objects
        out_to[name] = into.inverted()
        parts.append({"name": name, "bone": bones[0], "bones": bones, **({"px_per_m": ppm * finer[name]} if name in finer else {}), "center": [round(float(c), 4) for c in (lo + hi) / 2.0],
                      "depth_m": round(reach + 0.01, 4), "reach_m": round(reach, 4),
                      "triangles": sum(len(p.vertices) - 2 for o in objects for p in o.data.polygons), "own_triangles": own[name]})
        if name == "dress":  # what swings it, for the piece of the model that is drawn in its place (bake_joints.py)
            parts[-1].update(bones=[bones[0]], dress={"root": dress["root"], "chains": dress["chains"], "garments": dress["garments"]})
    # Joints pictured bent (--bent). A joint's own card: the skin of its two parts round the joint, as the real model
    # has it with the joint bent so far, pictured as any part is, in the frame of the bone above. One card for
    # each of --bends degrees. The page shows the one nearest to how far the joint is bent now, and the two parts'
    # own cards show nothing within the joint's zone.
    bent = []
    if hinge and joints:
        first = dict(PARTS)
        owned = {name: {obj.name: set(faces) for obj, faces, borrowed, *onto in chosen[name] if not borrowed} for name in chosen}
        held = {b: rig.pose.bones[b].rotation_quaternion.copy() for b in hinge}
        turn = lambda bone: np.array(rig.pose.bones[bone].matrix.to_3x3().normalized())
        cut_turns = {b: turn(rig.pose.bones[b].parent.name).T @ turn(b) for b in hinge}  # the part below in the frame of the part above, as the parts were cut
        for degrees in bends:
            for b, (axis, _, _) in hinge.items():
                rig.pose.bones[b].rotation_quaternion = held[b] @ Quaternion(axis, math.radians(degrees))
            bpy.context.view_layer.update()
            graph = bpy.context.evaluated_depsgraph_get()
            now = {o.name: bpy.data.meshes.new_from_object(o.evaluated_get(graph)) for o in bodies}
            for j in joints:
                if j["bone"] not in hinge or first[j["between"][1]][0] not in rest:
                    continue
                kind = BENT_KINDS[j["bone"][:-2]]
                upper = first[j["between"][1]][0]
                zone = BENT_ZONE[kind] * j["ring_cm"] / 100.0
                centre = np.array((rig.matrix_world @ rig.pose.bones[j["bone"]].head)[:])
                moved = rig.pose.bones[upper].matrix @ rig.data.bones[upper].matrix_local.inverted()
                into = Matrix(np.linalg.inv(rest[upper]).tolist()) @ TO_GLB @ moved.inverted()
                objects = []
                for obj in bodies:
                    mine = owned[j["between"][0]].get(obj.name, set()) | owned[j["between"][1]].get(obj.name, set())
                    at = np.empty(len(now[obj.name].vertices) * 3, dtype=np.float32)
                    now[obj.name].vertices.foreach_get("co", at)
                    near = np.linalg.norm(at.reshape(-1, 3) @ np.array(obj.matrix_world.to_3x3()).T + np.array(obj.matrix_world.translation[:]) - centre, axis=1) < zone + BENT_LAP_M + 0.02
                    faces = [p.index for p in obj.data.polygons if p.index in mine and any(near[v] for v in p.vertices)]
                    if faces:
                        objects.append(piece(obj, now[obj.name], faces, into))
                        objects[-1]["lap"] = True  # no line round a joint's card: its edge is inside the figure
                if not objects:
                    continue
                name = "%s@%g" % (j["bone"], degrees)
                points = np.array([v.co[:] for o in objects for v in o.data.vertices])
                reach = float(np.linalg.norm(points, axis=1).max())
                lo, hi = points.min(axis=0), points.max(axis=0)
                made[name] = objects
                parts.append({"name": name, "bone": upper, "bones": [upper], "joint": j["bone"], "bend": degrees, "center": [round(float(c), 4) for c in (lo + hi) / 2.0],
                              "depth_m": round(reach + 0.01, 4), "reach_m": round(reach, 4), "triangles": sum(len(p.vertices) - 2 for o in objects for p in o.data.polygons), "own_triangles": 0})
                if degrees == bends[0]:
                    bent.append({"bone": j["bone"], "upper": upper, "kind": kind, "between": j["between"], "axis": [round(a, 5) for a in hinge[j["bone"]][0]], "bends": bends, "part": j["between"][0],
                                 "cut_turn": [[round(float(c), 6) for c in row] for row in cut_turns[j["bone"]]], "zone_cm": round(zone * 100, 1), "reach_cm": round((zone + BENT_LAP_M) * 100, 1)})
        for b in hinge:
            rig.pose.bones[b].rotation_quaternion = held[b]
        print("IMPOSTOR bent: %s, each at %s degrees" % (", ".join(j["bone"] for j in bent), ", ".join("%g" % b for b in bends)), flush=True)
    for obj in list(scene.objects):
        if obj.type in ("MESH", "ARMATURE", "EMPTY") and not obj.name.startswith("part: "):
            bpy.data.objects.remove(obj)

    # The face: each of the recipe's marks found on the head's own surface, from straight in front.
    marks = []
    if recipe and "head" in made:
        points, faces = [], []
        for obj in made["head"]:
            first = len(points)
            points += [v.co.copy() for v in obj.data.vertices]
            faces += [[first + i for i in poly.vertices] for poly in obj.data.polygons]
        tree = BVHTree.FromPolygons(points, faces)

        def front_at(x, y):
            hit = tree.ray_cast(Vector((x, y, 2.0)), Vector((0.0, 0.0, -1.0)))
            return None if hit[0] is None else hit[0].z

        marks = pixel_face.place(recipe, front_at)
        print("IMPOSTOR face: %d of the recipe's %d marks found on the head" % (len(marks), len(recipe.get("marks", []))), flush=True)

    # One square each, in rows: where every part's bone head sits in the render.
    half = {p["name"]: int(math.ceil((p["reach_m"] * ppm + 3) * finer.get(p["name"], 1.0))) for p in parts}
    spots, x, y, shelf = {}, 0, 0, 0
    for p in sorted(parts, key=lambda p: -half[p["name"]]):
        side = 2 * half[p["name"]]
        if x + side > ROW_PX and x > 0:
            x, y, shelf = 0, y + shelf, 0
        spots[p["name"]] = (x + side // 2, y + side // 2)
        x, shelf = x + side, max(shelf, side)
    wide, tall = max(sx + half[n] for n, (sx, sy) in spots.items()), y + shelf
    wide, tall = wide + wide % 2, tall + tall % 2

    cam_data = bpy.data.cameras.new("eye")
    cam_data.type, cam_data.ortho_scale, cam_data.clip_start, cam_data.clip_end = "ORTHO", max(wide, tall) / ppm, 0.1, 2.0 * EYE_AWAY
    cam = bpy.data.objects.new("eye", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = wide, tall, 100
    # Pixel art gets its line afterwards, one pixel all round each picture: a shell on so coarse a grid speckles
    # every fold of a detailed mesh with ink.
    run_toon(shade=[[1.0, 1.0, 1.0], [1.0, 1.0, 1.0]], line_px=0 if look == "pixel" else ink_m * ppm, background=None, samples=16, **({"levels": 6} if look == "pixel" else {}), **({"soften": int(flag("--soften", "64"))} if look == "pixel" or "--soften" in args else {}))
    # The faces a part borrows from next door get no ink line of their own: the line there is the neighbour's
    # to draw. Left on, a limb's line ran on up into the shoulder and showed as scratches over the chest.
    for objects in made.values():
        for obj in objects:
            if obj.get("lap"):
                for mod in [m for m in obj.modifiers if m.name == "comic ink"]:
                    obj.modifiers.remove(mod)
    shells = [m for obj in (o for objects in made.values() for o in objects) for m in obj.modifiers if m.name == "comic ink"]
    data_mat, data_ink = data_material("impostor data", False), data_material("impostor data ink", True)
    ink_group = bpy.data.node_groups.get("comic ink")
    ink_mat = bpy.data.materials.get("comic ink")
    part_objects = [o for objects in made.values() for o in objects]
    painted = {o.name: list(o.data.materials) for o in part_objects}
    tmp_colour, tmp_data = os.path.join(out, ".bake-colour.png"), os.path.join(out, ".bake-data.exr")
    # Layers behind the first (--layers): what each needs to be pictured (behind, peel_group).
    trees = {name: tree_of(objects) for name, objects in made.items()} if layers > 1 else {}
    peel_at = bpy.data.images.new("impostor peel", wide, tall, float_buffer=True, is_data=True) if layers > 1 else None
    if peel_at:
        peel_at.use_half_precision = False  # (a half-size number is good to two millimetres here, and a layer is told from the one in front by that much)
    peel = peel_group(peel_at) if layers > 1 else None
    for mat in ([data_mat] + [m for mats in painted.values() for m in mats if m is not None]) if layers > 1 else []:
        peeled(mat, peel)
    last = {}  # the layer just pictured, for the one behind it: {part: (how high each pixel stands, where there is one)}

    card = {"format": "forge-impostor/1", "source": os.path.basename(source), "profile": profile, "look": look, "nearest": look == "pixel", "plays": flag("--plays", profile), "title": flag("--title", ""), "px_per_m": ppm, "ink_m": ink_m, "overlap": overlap, "trunk_overlap": trunk_overlap, "arms_lowered_deg": lowered,
            "cut": dict({"lap": lap, "smooth_m": smooth_m, "ball": ball}, **({"held": held} if held > 0 else {})) if lap > 0 else None, "joints": joints, **({"bent": {"joints": bent}} if bent else {}), "line_marked": True, "layers": layers, **({"eyes": {"deg": list(BEHIND_TILTS), "round": BEHIND_AROUND}} if layers > 1 else {}), "line_back_m": impostor.LINE_BACK_M, "creases": creases if look == "pixel" else None, "head_colours": head_colours,
            "light": list(impostor.LIGHT), "shade": [list(s) for s in impostor.SHADE], "edges": list(impostor.EDGES),
            "march": {"px": impostor.MARCH_PX, "max": impostor.MARCH_MAX, "refine": impostor.REFINE, "wall_m": impostor.WALL_M}, "blend_deg": impostor.BLEND_DEG, "hold_deg": impostor.HOLD_DEG,
            "parts": parts, "triangles": whole_triangles, "default_views": sets[0], "sets": {}}
    for set_name in sets:
        views = impostor.views_of(set_name)
        pictures = []  # (part, view, colour, data)
        heads = []     # the head's pictures, kept as they stand to have the face drawn on: (view, colour, height, where the head is, where the bone's head is)
        for vi, layer in ((vi, layer) for vi in range(len(views)) for layer in range(layers)):
            view = views[vi]
            d, r, u = Vector(view["d"]), Vector(view["r"]), Vector(view["u"])
            if peel:
                # a layer behind the first: for every part, how high it stands at each pixel; nothing nearer is drawn
                peel.nodes["On"].outputs[0].default_value = 1.0 if layer else 0.0
                if layer:
                    high = np.zeros((tall, wide, 4), dtype=np.float32)
                    for p in parts:
                        (sx, sy), hs, fine = spots[p["name"]], half[p["name"]], finer.get(p["name"], 1.0)
                        at, found = behind(trees[p["name"]], view, *last[p["name"]], hs, ppm * fine, model_tree, out_to[p["name"]], "--round-the-back" in args)
                        found = patches(found, max(4, int(round(BEHIND_LEAST_CM2 * 1e-4 * (ppm * fine) ** 2))))
                        high[sy - hs:sy + hs, sx - hs:sx + hs, :3] = np.where(found, np.clip(0.5 + 0.25 * (at + PEEL_MORE_M) * fine, 0.0, 1.0), 0.0)[..., None]  # (all three colours: a node reads a picture's brightness)
                    peel_at.pixels.foreach_set(high.ravel())
                    peel_at.update()
            cam.matrix_world = Matrix(((r.x, u.x, d.x, d.x * EYE_AWAY), (r.y, u.y, d.y, d.y * EYE_AWAY), (r.z, u.z, d.z, d.z * EYE_AWAY), (0, 0, 0, 1)))
            for p in parts:
                sx, sy = spots[p["name"]]
                at = r * ((sx - wide / 2.0) / ppm) + u * ((sy - tall / 2.0) / ppm)
                for obj in made[p["name"]]:
                    obj.matrix_world = Matrix.Translation(at) @ Matrix.Diagonal((finer.get(p["name"], 1.0),) * 3 + (1.0,))  # a finer part is pictured larger
            # colour, without the line's shell: the line's pixels are marked in the numbers and painted by the page
            for obj in part_objects:
                for i, mat in enumerate(painted[obj.name]):
                    obj.data.materials[i] = mat
            for shell in shells:
                shell.show_render = False
            if ink_group:
                retag(ink_group, part_objects)
            # pixel art is not smoothed: a pixel is one colour of the surface under its middle
            scene.eevee.taa_render_samples, scene.render.filter_size = (1, 0.01) if look == "pixel" else (16, 0.8)
            scene.render.image_settings.file_format, scene.render.image_settings.color_mode = "PNG", "RGBA"
            scene.render.image_settings.color_depth = "8"
            scene.render.filepath = tmp_colour
            bpy.ops.render.render(write_still=True)
            colour = pixels_of(tmp_colour)
            # facing and depth
            for obj in part_objects:
                for i in range(len(obj.data.materials)):
                    obj.data.materials[i] = data_mat
            for shell in shells:
                shell.show_render = layer == 0  # a layer behind the first has no line round it
            if ink_group:
                ink_group.nodes["Ink"].inputs["Material"].default_value = data_ink
                retag(ink_group, part_objects)
            scene.eevee.taa_render_samples, scene.render.filter_size = 1, 0.01
            scene.render.image_settings.file_format, scene.render.image_settings.color_mode = "OPEN_EXR", "RGBA"
            scene.render.image_settings.color_depth = "32"
            scene.render.filepath = tmp_data
            bpy.ops.render.render(write_still=True)
            data = pixels_of(tmp_data, plain=True)
            for p in parts:
                sx, sy = spots[p["name"]]
                hs = half[p["name"]]
                fine = finer.get(p["name"], 1.0)
                col = colour[sy - hs:sy + hs, sx - hs:sx + hs].copy()
                dat = data[sy - hs:sy + hs, sx - hs:sx + hs]
                if fine != 1.0:  # pictured larger, so everything stood further forward too
                    dat = dat.copy()
                    dat[..., 2] = (dat[..., 2] - 0.5) / fine + 0.5
                # The outline is the unsmoothed one: a pixel is the part or it is not. A soft edge would lose the
                # thin ink line when the card is drawn (it is kept where the cover is over a half). The colour
                # under it is the smoothed render's, carried a pixel outward where that one had not reached.
                there = dat[..., 3] > 0.5
                if look == "pixel" and layer == 0:
                    grown = there
                    for _ in range(max(1, int(round(fine)))):  # the line is as wide on a finer part as on the rest
                        grown = grown | np.roll(grown, 1, 0) | np.roll(grown, -1, 0) | np.roll(grown, 1, 1) | np.roll(grown, -1, 1)
                    ring = grown & ~there
                    dat = dat.copy()
                    dat[ring] = (0.0, 0.0, 0.0, 1.0)  # marked as line, as the shell's pixels are: it takes its depth from the surface beside it
                    there = there | ring
                col[..., :3] = spread(col[..., :3], col[..., 3] > 0.5, 3)
                col[..., 3] = there
                last[p["name"]] = ((dat[..., 2] * 2.0 - 1.0).copy(), (dat[..., 3] > 0.5) & ~((dat[..., 0] < 0.02) & (dat[..., 1] < 0.02) & (dat[..., 2] < 0.02)))  # (not the line's pixels)
                if not there.any():
                    pictures.append((p, vi, None, None, (0, 0), (0.0, 0.0), layer))
                    continue
                ys, xs = np.where(there)
                x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
                # the facing as the bone has it, and the depth as a share of the part's reach
                known = dat[..., 3] > 0.5
                # The ink line is a shell behind the part, centimetres further back than the surface it outlines.
                # Left there it would be slid apart from its own outline when the card is drawn from a little to one
                # side. So the line takes the depth of the surface next to it, and faces the eye.
                line = known & (dat[..., 0] < 0.02) & (dat[..., 1] < 0.02) & (dat[..., 2] < 0.02)
                dat = dat.copy()
                dat[..., :3] = np.where(line[..., None], (0.5, 0.5, 0.5), dat[..., :3])
                dat[..., 2] = spread(dat[..., 2], known & ~line, 8)
                nx, ny = dat[..., 0] * 2.0 - 1.0, dat[..., 1] * 2.0 - 1.0
                nz = np.sqrt(np.clip(1.0 - nx * nx - ny * ny, 0.0, 1.0))
                normal = nx[..., None] * np.array(view["r"]) + ny[..., None] * np.array(view["u"]) + nz[..., None] * np.array(view["d"])
                height = (dat[..., 2] * 2.0 - 1.0) / p["depth_m"]
                # blue 0 is kept to mean "nothing here": the page's search down a pixel's line must know air from surface
                packed = np.concatenate([impostor.pack_normal(normal), np.clip(height * 0.5 + 0.5, 1.0 / 255.0, 1.0)[..., None]], axis=-1)
                packed[~known] = (0.5, 0.5, 0.0)
                # the line is marked: both of its facing's numbers are 0, and no pixel of the surface has that
                packed[..., 0] = np.where(known & ~line & (packed[..., 0] < 0.5 / 255.0) & (packed[..., 1] < 0.5 / 255.0), 1.0 / 255.0, packed[..., 0])
                packed[line, :2] = 0.0
                if look == "joe":
                    # Bold ink: the lines inside a part are drawn here, into its picture: where the surface steps
                    # back by more than 2 cm from one pixel to the next (one fold of the body in front of another)
                    # or turns by more than about 70 degrees (a crease). The line goes on the further pixel.
                    metres_all = (dat[..., 2] * 2.0 - 1.0)
                    inked = np.zeros_like(known)
                    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                        near_h, near_n, near_k = np.roll(metres_all, (dy, dx), axis=(0, 1)), np.roll(normal, (dy, dx), axis=(0, 1)), np.roll(known, (dy, dx), axis=(0, 1))
                        inked |= known & near_k & ((near_h - metres_all > 0.02) | (((normal * near_n).sum(axis=-1) < 0.3) & (near_h >= metres_all)))
                    inked |= np.roll(inked, 1, axis=0) & known  # two pixels wide: about a centimetre
                    col[..., :3] = np.where(inked[..., None], (0.07, 0.055, 0.086), col[..., :3])
                if look == "pixel" and creases == "head" and p["name"] == "head":
                    # Pixel art: the folds of the head, one pixel wide, in the colour that is there made dark (a
                    # nostril, the line of the jaw, a lock of hair), on the further pixel. Without them a face read
                    # small is a patch of skin; bold ink has always had them.
                    col[..., :3] = np.where(impostor.folds(dat[..., 2] * 2.0 - 1.0, normal, known & ~line)[..., None], col[..., :3] * CREASE, col[..., :3])
                metres = (np.round(packed[..., 2][known] * 255.0) / 255.0 * 2.0 - 1.0) * p["depth_m"]
                if marks and p["name"] == "head" and layer == 0:
                    heads.append((vi, col[y0:y1, x0:x1], (dat[..., 2] * 2.0 - 1.0)[y0:y1, x0:x1], (known & ~line)[y0:y1, x0:x1], (hs - x0, hs - y0)))
                pictures.append((p, vi, col[y0:y1, x0:x1], packed[y0:y1, x0:x1], (hs - x0, hs - y0), (float(metres.min()), float(metres.max())), layer))
            if vi % 8 == 0 and layer == 0:
                print("IMPOSTOR views %s: %d of %d pictured" % (set_name, vi + 1, len(views)), flush=True)
        palette, keep = None, []
        if heads:
            # The face, drawn into every picture of the head. What a wash finds is found once, from the front.
            head_ppm = ppm * finer.get("head", 1.0)
            least = pixel_face.least_for(head_ppm)
            vi, col, height, there, anchor = max(heads, key=lambda h: views[h[0]]["d"][2])
            found = pixel_face.find_colours(marks, col, height, there, views[vi], head_ppm, anchor)
            drawn = {}
            for vi, col, height, there, anchor in heads:
                for name, count in pixel_face.draw(col, height, there, views[vi], head_ppm, anchor, marks, recipe.get("colours", {}), found, least).items():
                    drawn[name] = drawn.get(name, 0) + (1 if count else 0)
            keep = pixel_face.kept_colours(marks, recipe.get("colours", {}), found)
            card["face"] = {"least_px": least, "marks": pixel_face.for_page(marks, recipe.get("colours", {}), found), "pictures_with": drawn}
            print("IMPOSTOR face: drawn in %s" % ", ".join("%s %d" % (k, v) for k, v in drawn.items()), flush=True)
        if colours:
            # Pixel art keeps to a few colours: the ones this character is most made of. Every pixel takes the nearest.
            # (from the first layer's pictures alone: a sheet baked with layers behind has the colours it has without)
            seen = np.concatenate([pic[2][pic[2][..., 3] > 0.5][:, :3] for pic in pictures if pic[2] is not None and pic[6] == 0])
            palette = pixel_face.few_colours(seen[:: max(1, len(seen) // 200000)], colours, keep)
            if head_colours:
                # ... and the head some more of its own, picked from its pictures alone and closer together: a face is
                # a tenth of the figure, and left to the whole sheet's count it gets one skin and one shadow.
                of_head = np.concatenate([pic[2][pic[2][..., 3] > 0.5][:, :3] for pic in pictures if pic[2] is not None and pic[6] == 0 and pic[0]["name"] == "head"] or [seen[:0]])
                if len(of_head):
                    palette = pixel_face.few_colours(of_head[:: max(1, len(of_head) // 200000)], len(palette) + head_colours, list(palette), apart=10.0 / 255.0)
            drawn_as = pixel_face.folded(palette, (recipe or {}).get("same"))  # colours the recipe says are one thing
            for pic in pictures:
                if pic[2] is not None:
                    pic[2][..., :3] = pixel_face.snap(pic[2][..., :3], palette, drawn_as)
            palette = np.unique(np.round(drawn_as * 255.0), axis=0).astype(np.float32) / 255.0
            card["palette"] = [[int(round(c * 255)) for c in colour] for colour in palette]
        sizes = [(pic[2].shape[1], pic[2].shape[0]) if pic[2] is not None else (1, 1) for pic in pictures]
        where, sheet_w, sheet_h, used = pack(sizes)
        colour_sheet = np.zeros((sheet_h, sheet_w, 4), dtype=np.uint8)
        data_sheet = np.zeros((sheet_h, sheet_w, 3), dtype=np.uint8)
        first = {p["name"]: [None] * len(views) for p in parts}
        # the layers behind the first: the same list for each, a picture cut down to what it holds
        further = [{p["name"]: [None] * len(views) for p in parts} for _ in range(layers - 1)]
        for (p, vi, col, dat, anchor, heights, layer), (x, y), (w, h) in zip(pictures, where, sizes):
            cells = further[layer - 1] if layer else first
            if col is None:
                cells[p["name"]][vi] = [0, 0, 0, 0, 0, 0, 0.0, 0.0]
                continue
            colour_sheet[y:y + h, x:x + w] = np.round(np.clip(col, 0.0, 1.0) * 255.0)
            data_sheet[y:y + h, x:x + w] = np.round(np.clip(dat, 0.0, 1.0) * 255.0)
            cells[p["name"]][vi] = [int(x), int(y), int(w), int(h), int(anchor[0]), int(anchor[1]), round(heights[0], 4), round(heights[1], 4)]
        cells = first
        names = ("views%s-color.png" % set_name, "views%s-data.png" % set_name)
        impostor.write_png(os.path.join(out, names[0]), colour_sheet)
        impostor.write_png(os.path.join(out, names[1]), data_sheet)
        card["sets"][set_name] = {
            "color": names[0], "data": names[1], "size": [sheet_w, sheet_h], "views": views, "cells": cells,
            **({"behind": further, "behind_share": round(sum(w * h for pic, (w, h) in zip(pictures, sizes) if pic[6] and pic[2] is not None) / float(max(1, sum(w * h for pic, (w, h) in zip(pictures, sizes) if pic[2] is not None))), 3)} if further else {}),
            "pictures": len(pictures), "filled": round(used / float(sheet_w * sheet_h), 3),
            "bytes": {"color": os.path.getsize(os.path.join(out, names[0])), "data": os.path.getsize(os.path.join(out, names[1]))},
            # two sheets, four bytes a pixel each once a graphics card holds them
            "memory_mb": round(sheet_w * sheet_h * 8 / 1e6, 2),
        }
        print("IMPOSTOR views %s: %d pictures on a %dx%d sheet, %.1f MB in memory" % (set_name, len(pictures), sheet_w, sheet_h, sheet_w * sheet_h * 8 / 1e6), flush=True)
    for path in (tmp_colour, tmp_data):
        if os.path.exists(path):
            os.remove(path)
    card["seconds"] = round(time.time() - began, 1)
    with open(os.path.join(out, "impostor.json"), "w") as f:
        json.dump(card, f, indent=1)
    print("RESULT " + json.dumps({"folder": out, "parts": len(parts), "triangles": whole_triangles, "seconds": card["seconds"],
                                   "sets": {k: {"size": v["size"], "memory_mb": v["memory_mb"], "pictures": v["pictures"]} for k, v in card["sets"].items()}}))


if __name__ == "__main__":
    main()
