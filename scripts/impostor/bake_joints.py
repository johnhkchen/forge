"""Gives a character's flat cards real joints: a small piece of the model itself, with its skeleton's pull, for
every knee, elbow, hip and shoulder, and one for the neck, the collar and the tops of both shoulders.

    Blender -b --factory-startup -P scripts/impostor/bake_joints.py -- <run> <profile>
        [--from joe-joined,pixel-clear,pixel-joined,comic-joined] [--name necked] [--triangles 320] [--atlas 512]
        [--zone knee=1.6,elbow=1.7,hip=1.25,shoulder=1.35,neck=1] [--margin 0.2] [--kinds knee,elbow,hip,shoulder,neck,dress]
        [--torn 0.4] [--missed 0.5] [--leave forearm_l,...] [--dress-triangles 4000]
        [--even 0.03] [--cloth 0.5] [--pull worked|rig] [--neck-triangles 1] [--rim 0]

A card is a picture of a rigid piece of the model, taken as it stood. Bend a knee far and look at it end on, and
the two pictures that meet there show what they never should: the open end of the thigh and the open top of the
shin, the inside of a trouser leg. The cloth pulled over a bent knee is in no picture, because it only exists
when the model bends. So the knee is not drawn from pictures. Round every big joint the cards step aside (inside
a ball about the joint: the "zone") and a piece of the real model is drawn there instead, bending with the
skeleton as the whole model would.

For each of --from (the baked cards <profile>-impostor-<from>/, which are left alone) this writes
<profile>-impostor-<from>-<name>/, "-joined" left out of it (joe-joined makes joe-skinned; pixel-clear makes
pixel-clear-skinned), which the pages read first (gallery/looks.js: bakedFor):

    impostor.json     the same cards (their sheets are read where they are, in the folder they were baked into),
                      and "skin": the joints, each one's zone, the file below and its two pictures
    joints.glb        the pieces: the model's surface within the zone and a little more, some hundreds of
                      triangles a joint (--triangles: about how many, give or take a cut in four), with the
                      skeleton and its pull. One mesh, a material a joint ("joint shin_l": the bone whose head is
                      the joint)
    joints-color.png  the pieces' colour, looked up in this folder's own card sheets: every place on a piece takes
                      the colour the cards show there, from the picture that sees it most squarely. So a piece is
                      in the look its cards are in (the pixel sheet's few colours, bold ink's strong ones; not the
                      folds bold ink's sheet has drawn in, which the page draws on the finished picture) and
                      meets them without a change of colour
    joints-data.png   which way the surface faces at every place, from the same sheets (red, green: the facing
                      as the model has it at rest, folded as the card sheets fold theirs), so the light falls on
                      a piece's folds as it does on the cards'

A zone is a ball about the joint, --zone times the radius of the ring where the joint's two parts meet: wide
enough to hold what each part borrows from the other, and the ball the cards had in the joint.

What a piece is cut from. A rigged version that is tidy (a painted or low-poly mesh) gives its own faces there,
cut down if there are far too many. A detailed mesh does not: a third of a million triangles that fold through
each other, which no cutting down gets through. Its pieces are cut from the rigged version whose clips the cards
play (impostor.json: "plays"), each triangle cut in four until there are enough, unwrapped, and then every point
laid onto the detailed surface: the first of it met coming in from outside. The pull on a point is the tidy
mesh's, which is where the detailed mesh's own came from (rig_detailed.py).

The neck's piece (--kinds neck; yoke.py has its arithmetic and why there is one). The skeleton has a neck bone
and two collar bones, and no card rides any of them: their skin is in the chest's card, which rides the chest
bone alone, so a turned head and a raised arm leave the neck and the shoulder tops behind. The piece is that skin:
what the chest's card holds inside a ball about the foot of the neck, most of the way to the nearer arm's joint
(the shoulders' own pieces keep their zones), stopping where the head's own skin begins. In impostor.json it is
the joint "head" with "kind": "neck" and three things the others do not have: "about" (the bone its zone is a
ball about: "neck"), "aside" (the one card that steps aside there: the chest's; the head's stays whole) and
"core_cm" (what that card keeps in the zone: nothing). It is laid on the model with the head's own faces left
out, so that it does not climb a beard or a hat brim. Its pull is the rig's, worked over: evened out along the
surface over --even metres (a rig gives each point of a neck to one bone alone, and the skin folds where two
bones' points meet), and, where the tidy version has clothing as a mesh of its own, --cloth of what the neck and
head pull on the clothing given to the chest (a collar lies on the shoulders). --pull rig leaves the rig's own.
--rim eases a piece's pull over to the chest bone toward its rim; it scored worse and is off.

The dress's piece (--kinds dress; bake_impostor.py: chains_of). A skirt that spans the hips and both legs is a card
of its own in the sheets, "dress", riding the bone its swing chains hang from; but a card is rigid, and a skirt
swings up to 80 degrees in a dance. So the dress is drawn as one piece of the model, pulled by the chains and the
hips and the legs as the model is, and the dress's card steps aside for it wholly (a zone about the chains' root
as big as the dress, keeping nothing: "about", "aside" and "core_cm" as the neck's). Being one skin it cannot tear
between the legs, and the chains that move it are its own bones. It is cut from the pictured model itself, not
laid onto it: a garment is a mesh of its own (rig_detailed.py: "gear: <name>"), not a third of a million triangles
folding through a body, so it is cut down to --dress-triangles as it is, its three ruffled tiers and all, and keeps
the pull rig_detailed.py gave it. Its colour comes from the dress's own card, as every piece's does, so the polka
dots are the sheet's. In impostor.json it is the joint named after the top bone of its first chain, "kind": "dress",
and the same joint is added to the cards' "joints", so a page reads its zone the way it reads any other; a page
without the chains' bones draws neither the piece nor the zone, and the dress's card then rides the hips as it is.
Under a dress the knee and hip pieces are cut from the skin the dress hides ("body under: ..." in the tidy version)
and laid onto the body, not onto the skirt.

Bare shoulders, a top painted on (README: "Shoulders that hold"). A shoulder's zone is never smaller than
yoke.SHOULDER_SPAN of the way from its joint to the foot of the neck: the skin that stretches when an arm goes up is
as big as the shoulders are wide, not as the arm is thick. A pictured model that is a body with garments put back
on it has every other garment painted on its skin, and its pieces are cut from the skin those garments hide, not
from the tidy garments (yoke.cut_from): a sleeveless top is her skin's own black, and moves as skin. And the dress's
piece is worn over the body ("over_cm"): where it and a card of the body are that near, as at a waistband, the
dress is drawn.

A joint is left to its cards when too much of its piece would not lie down (--torn: the share of it in triangles
pulled out to shards, where the two meshes are too unlike: a rolled sleeve), or misses too much of the model
there (--missed), or is named in --leave or, for this character, in scripts/impostor/joints.json.
scripts/impostor/judge_joints.py says whether a joint does better with its piece; a picture says it better.

Prints JOINTS lines and one RESULT {json}. Never touches an open Blender.
"""

import json
import math
import os
import re
import sys
import time

import bpy
import bmesh
import numpy as np
from mathutils import Matrix
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import impostor  # noqa: E402
import bake_impostor  # noqa: E402
import yoke  # noqa: E402

KINDS = {"shin": "knee", "forearm": "elbow", "upper_arm": "shoulder", "thigh": "hip"}
SEEN_M = 0.012      # a place on a piece is in a card's picture when the picture's surface is this near it
WRAP_M = 0.06       # a piece cut from a tidy mesh is laid onto the pictured model's surface when that is within this of it
JOE_INK = np.array([0.07, 0.055, 0.086], dtype=np.float32)  # what bake_impostor.py draws a fold in
LAP_M = 0.015       # a piece is drawn this far past its zone, under the cards' edge, so no crack opens between them
DRESS_PULL = 0.5    # a face of the pictured model is the dress's when the dress pulls on it this much, on average over its corners
DRESS_ROOM_M = 0.05  # the dress's zone reaches this far past the furthest of it from the chains' root, as it hangs
DRESS_SWING = 1.5   # ... and its piece is drawn this many times as far out: swung, the hem goes further
DRESS_WRAP_M = 0.10  # the tidy version's dress is laid onto the pictured one where that is within this of it (a ruffle stands further off than a sleeve)
LEAST_M = {"elbow": 0.08, "knee": 0.10}  # a zone is never smaller than this: a ring found small (a rolled sleeve) is not a small joint
DRESS_OVER_M = 0.015  # the dress's piece is worn over the body: where it and a card of the body are this near, the dress is drawn
TORN_STRETCH = 2.5  # a triangle with an edge pulled out to this many times its length did not lie down on the model
MISSED_M = 0.015    # the model's surface this far from a piece is not covered by it
SCRAP = 0.03        # an island of a piece with less than this share of the piece's area is a scrap
PAD_PX = 6          # the colour round every patch of the atlas is carried this far outward
YOKE_FULL = 1       # the neck piece may have this many times a joint's triangles (three times as many, 1,300 to 1,700, scored the same: judge_joints.py)
HEADS = 0.5         # the neck piece leaves out a triangle the head pulls on more than this, on average over its corners
OVERLAP_M = 0.01    # the neck piece leaves out what lies this far inside a shoulder's zone: the shoulder's piece is there


def kind_of(bone):
    return "neck" if bone == "head" else KINDS.get(bone[:-2], "")


def hides_dress(obj, dress):
    """Whether a tidy version's mesh is skin a garment of the dress hides ("body under: ruffled skirt")."""
    return bool(dress and obj.get("under") and any(bake_impostor.worn_dress({"gear": g}, dress) for g in str(obj["under"]).split("|")))


def garment_of(obj):
    """The garment a mesh is ("gear: sleeveless top", or a "gear" of its own), as cloth.py writes a name; None for skin."""
    gear = obj.get("gear") or (obj.name[len("gear: "):].split(".")[0] if obj.name.startswith("gear: ") else None)
    return impostor.slug_of(gear) if gear else None


def cut_from(meshes, worn, dress):
    """Which of a tidy version's meshes the pieces are cut from (yoke.cut_from has the rule and why). worn: the
    garments the pictured model has as meshes of their own, or None when it is one skin (a clothed final.glb)."""
    told = [(garment_of(o), [impostor.slug_of(g) for g in str(o.get("under") or "").split("|") if g]) for o in meshes]
    return [o for o, keep in zip(meshes, yoke.cut_from(told, worn, (dress or {}).get("garments", ()))) if keep]



def rasterise(uv, size):
    """Which triangle each texel of a square atlas falls in, and where in it: (face index HxW, -1 where none;
    three weights HxWx3). uv: Tx3x2, 0 to 1, v upward; rows from the bottom."""
    face = np.full((size, size), -1, dtype=np.int32)
    weights = np.zeros((size, size, 3), dtype=np.float32)
    px = uv * size
    for t in range(len(px)):
        (x0, y0), (x1, y1), (x2, y2) = px[t]
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        lo_x, hi_x = max(0, int(math.floor(min(x0, x1, x2) - 1))), min(size, int(math.ceil(max(x0, x1, x2) + 1)))
        lo_y, hi_y = max(0, int(math.floor(min(y0, y1, y2) - 1))), min(size, int(math.ceil(max(y0, y1, y2) + 1)))
        if hi_x <= lo_x or hi_y <= lo_y:
            continue
        xs, ys = np.meshgrid(np.arange(lo_x, hi_x) + 0.5, np.arange(lo_y, hi_y) + 0.5)
        w0 = ((x1 - xs) * (y2 - ys) - (x2 - xs) * (y1 - ys)) / area
        w1 = ((x2 - xs) * (y0 - ys) - (x0 - xs) * (y2 - ys)) / area
        w2 = 1.0 - w0 - w1
        slack = 0.75 / max(1e-6, math.sqrt(abs(area)))  # a texel whose middle is just outside still takes the triangle
        inside = (w0 >= -slack) & (w1 >= -slack) & (w2 >= -slack) & (face[lo_y:hi_y, lo_x:hi_x] < 0)
        strict = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        take = inside | strict
        face[lo_y:hi_y, lo_x:hi_x][take] = t
        weights[lo_y:hi_y, lo_x:hi_x][take] = np.stack([w0, w1, w2], axis=-1)[take]
    return face, weights


def look_up(character, part, points, normals, seen_m=SEEN_M):
    """What a part's own card pictures show at places on it. points, normals: Nx3 in the part's bone's frame.
    Returns (colour Nx3 as the sheet stores it, facing Nx3 in the bone's frame, found N)."""
    ppm = float(part.get("px_per_m") or character.px_per_m)
    tall, wide = character.colour.shape[:2]
    best = np.full(len(points), -9.0)
    colour, facing = np.zeros((len(points), 3), dtype=np.float32), np.zeros((len(points), 3), dtype=np.float32)
    for view, cell in zip(character.views, character.cells[part["name"]]):
        x0, y0, w, h, ax, ay = cell[:6]
        if w <= 0 or h <= 0:
            continue
        r, u, d = (np.asarray(view[k], dtype=np.float64) for k in ("r", "u", "d"))
        cx, cy = ax + ppm * (points @ r), ay + ppm * (points @ u)
        inside = (cx >= 0) & (cx < w) & (cy >= 0) & (cy < h)
        iy, ix = np.clip(np.floor(y0 + cy).astype(int), 0, tall - 1), np.clip(np.floor(x0 + cx).astype(int), 0, wide - 1)
        data = character.data[iy, ix]
        height = (data[:, 2] * 2.0 - 1.0) * part["depth_m"]
        surface = inside & (data[:, 2] > 0.5 / 255.0) & ((data[:, 0] > 0.5 / 255.0) | (data[:, 1] > 0.5 / 255.0)) & (character.colour[iy, ix, 3] > 0.5)
        if character.card.get("look") == "joe":  # bold ink's sheet has its folds drawn in, in ink: a line is not the surface's colour
            surface &= np.abs(character.colour[iy, ix, :3] - JOE_INK).max(axis=1) > 1.5 / 255.0
        off = np.abs(height - points @ d)
        # the picture that sees the place most squarely, of those whose surface is there; a little is taken off for
        # a surface that is not quite at the place, so of two pictures as square the nearer wins
        score = np.where(surface & (off < seen_m), normals @ d - off / seen_m * 0.1, -9.0)
        take = score > best
        best[take] = score[take]
        colour[take] = character.colour[iy, ix, :3][take]
        facing[take] = impostor.unpack_normal(data[:, :2])[take]
    return colour, facing, best > 0.1


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    run, profile = os.path.abspath(args[0]), args[1]
    sources = flag("--from", "joe-joined,pixel-clear,pixel-joined,comic-joined").split(",")
    name, target = flag("--name", "necked"), int(flag("--triangles", "320"))
    zones = dict((k, float(v)) for k, v in (pair.split("=") for pair in flag("--zone", "knee=1.6,elbow=1.7,hip=1.25,shoulder=1.35,neck=1").split(",")))
    even_m, cloth, rim = float(flag("--even", str(yoke.EVEN_M))), float(flag("--cloth", str(yoke.CLOTH))), float(flag("--rim", "0"))
    rework = flag("--pull", "worked") != "rig"  # --pull rig: every piece keeps the rig's own pull, as the knees do
    leave = set(flag("--leave", "").split(","))  # joints to leave to their cards whatever the bake finds (judge_joints.py says which do better so)
    with open(os.path.join(HERE, "joints.json")) as f:  # ... and the ones written down for this character
        leave |= set(json.load(f).get(re.sub(r"^\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d-", "", os.path.basename(run)), {}).get("leave", []))
    max_torn, max_missed = float(flag("--torn", "0.4")), float(flag("--missed", "0.5"))
    margin, kinds = float(flag("--margin", "0.2")), flag("--kinds", "knee,elbow,hip,shoulder,neck,dress").split(",")
    profiles = os.path.join(run, "profiles")
    sources = [s for s in sources if os.path.isfile(os.path.join(profiles, "%s-impostor-%s" % (profile, s), "impostor.json"))]  # the cards there are
    folders = [os.path.join(profiles, "%s-impostor-%s" % (profile, s)) for s in sources]
    with open(os.path.join(folders[0], "impostor.json")) as f:
        card = json.load(f)
    source = os.path.join(profiles, card["source"])
    # a dress the cards were cut with (bake_impostor.py: chains_of), and its piece's size
    dressed = next((p for p in card["parts"] if p.get("dress")), None) if "dress" in kinds else None
    dress = dict(dressed["dress"], bones=[b for chain in dressed["dress"]["chains"] for b in chain]) if dressed else None
    size = int(flag("--atlas", "1024" if dress else "512"))  # (a skirt is as much surface as every other piece together)
    dress_triangles = int(flag("--dress-triangles", "4000"))
    dress_from_model, dress_skin = flag("--dress-from", "tidy") == "model", None
    began = time.time()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.import_scene.gltf(filepath=source)
    rig = next(o for o in scene.objects if o.type == "ARMATURE")
    bodies = [o for o in scene.objects if o.type == "MESH" and o.find_armature() and not o.get("under")]
    rest = impostor.Glb(source).pose(None)
    folds = bake_impostor.part_of_bone(rig, dress)
    bone_of = {n: bones[0] for n, bones in bake_impostor.parts_with(dress)}
    # The pictured model as it rests, to lay the pieces on (not the dress: a knee under a skirt lies on the leg).
    points, faces, below, body_pulls = [], [], [], []
    for obj in [o for o in bodies if not bake_impostor.worn_dress(o, dress)]:
        first = len(points)
        points += [obj.matrix_world @ v.co for v in obj.data.vertices]
        group_names = [g.name for g in obj.vertex_groups]
        body_pulls += [{group_names[g.group]: g.weight for g in v.groups if g.weight > 0} for v in obj.data.vertices]
        faces += [[first + i for i in poly.vertices] for poly in obj.data.polygons]
        # (the same without the head's own faces, for the neck's piece to be laid on: a beard, a jaw or a hat brim
        # hangs over a collar, and is the head's card's to show)
        heads = [folds.get(g.name) == "head" for g in obj.vertex_groups]
        headed = np.array([sum(g.weight for g in v.groups if heads[g.group]) > 0.5 * (sum(g.weight for g in v.groups) or 1.0) for v in obj.data.vertices])
        below += [[first + i for i in poly.vertices] for poly in obj.data.polygons if not headed[list(poly.vertices)].all()]
    skin = BVHTree.FromPolygons(points, faces)
    skin_below = BVHTree.FromPolygons(points, below) if below else skin
    # What the pieces are cut from: a tidy mesh with this skeleton. A detailed mesh is not one (a third of a million
    # triangles that fold through each other: cutting it down stalls), so its pieces are cut from the rigged version
    # whose clips the cards play, each face cut in four until there are enough, and laid onto the detailed surface.
    wrap = card.get("plays", profile) != profile and os.path.isfile(os.path.join(profiles, "%s-walk.glb" % card["plays"]))
    dress_from_model = dress_from_model or not wrap  # (a tidy model pictured as it is: its own dress is the piece)
    if wrap:
        known = set(scene.objects)
        bpy.ops.import_scene.gltf(filepath=os.path.join(profiles, "%s-walk.glb" % card["plays"]))
        extra = [o for o in scene.objects if o not in known]
        # a pictured model that is a body with garments put back on it has the others painted on: cut from the skin under those
        worn = {garment_of(o) for o in bodies if garment_of(o)} or None
        if flag("--painted", "skin") == "garment":  # (tried: a garment painted on cut as the tidy garment, as before "Shoulders that hold")
            worn = None
        tidy = cut_from([o for o in extra if o.type == "MESH" and o.find_armature()], worn, dress)
        print("JOINTS cut from the tidy version's %s" % ", ".join(sorted(o.name for o in tidy)), flush=True)
    else:
        extra, tidy = [], [o for o in bodies if not bake_impostor.worn_dress(o, dress)]  # the dress is its own piece

    joints, made = [], []
    head_of = lambda bone: rig.matrix_world @ rig.data.bones[bone].head_local
    wanted = []
    for j in card["joints"]:
        kind = kind_of(j["bone"])
        if kind not in kinds or kind not in zones or j["bone"] in leave:
            continue
        ring = j["ring_cm"] / 100.0
        if kind == "neck":
            # The neck's piece is the whole yoke: the neck, the collar and the top of both shoulders, in a ball about the
            # foot of the neck. That is what the neck's and the collar bones pull on, and the chest's card held still.
            if any(b not in rig.data.bones for b in ("neck", "chest", "upper_arm_l", "upper_arm_r")):
                continue
            centre = head_of("neck")
            zone = yoke.zone(centre, [head_of(b) for b in ("upper_arm_l", "upper_arm_r")], head_of("chest"), zones[kind])
        else:
            zone, centre = max(zones[kind] * ring, LEAST_M.get(kind, 0.0)), head_of(j["bone"])
            if kind == "shoulder" and "neck" in rig.data.bones:  # as big as the shoulders are wide, not as the arm is thick
                zone = yoke.shoulder_zone(zone, centre, head_of("neck"))
        wanted.append((j, kind, ring, zone, centre))
    wanted.sort(key=lambda w: w[1] == "neck")  # the neck's last: it leaves the shoulders' zones to their own pieces
    shoulders = [(centre, zone) for _, kind, _, zone, centre in wanted if kind == "shoulder"]
    for j, kind, ring, zone, centre in wanted:
        full = int(target * (float(flag("--neck-triangles", str(YOKE_FULL))) if kind == "neck" else 1))  # (--neck-triangles: how many times a joint's the neck piece may have)
        taken = lambda at: any((at - c).length < z - OVERLAP_M for c, z in shoulders)  # inside a shoulder's zone: its piece is there
        pieces = []
        for obj in tidy:
            groups = bake_impostor.groups_of(obj, folds, dress)
            pull = np.zeros((len(obj.data.vertices), 2))
            # (a hip's and a shoulder's zone reaches up the trunk past where the hips' or the chest's own bones pull
            # most: what the spine pulls there counts as the trunk's)
            trunk = {"spine"} if j["between"][1] in ("hips", "chest") else set()
            for v in obj.data.vertices:
                total = sum(g.weight for g in v.groups) or 1.0
                for g in v.groups:
                    for n in (0, 1):
                        if groups[g.group] == j["between"][n] or (n == 1 and groups[g.group] in trunk):
                            pull[v.index, n] += g.weight / total
            near = np.array([(obj.matrix_world @ v.co - centre).length < zone + margin * ring for v in obj.data.vertices])
            if kind == "neck":  # the trunk's side only (the head is its card's, whole), and not what a shoulder's piece has
                free = np.array([not taken(obj.matrix_world @ v.co) for v in obj.data.vertices])
                keep = {p.index: pull[list(p.vertices)].mean(axis=0) for p in obj.data.polygons if near[list(p.vertices)].any() and pull[list(p.vertices), 1].mean() >= 0.2 and free[list(p.vertices)].any()}
            else:
                keep = {p.index: pull[list(p.vertices)].mean(axis=0) for p in obj.data.polygons if near[list(p.vertices)].any() and pull[list(p.vertices)].sum(axis=1).mean() >= 0.2}
            if not keep:
                continue
            data = obj.data.copy()
            for layer in list(data.uv_layers):
                data.uv_layers.remove(layer)
            bm = bmesh.new()
            bm.from_mesh(data)
            bm.faces.ensure_lookup_table()
            tell = bm.faces.layers.int.new("lower")  # which of the joint's two parts a face is more of: the one below it, or the one above
            worn = bm.faces.layers.int.new("gear")   # whether it is clothing that comes off (a mesh of its own in the tidy version), not the body
            for f in bm.faces:
                f[tell] = 1 if f.index in keep and keep[f.index][0] >= keep[f.index][1] else 0
                f[worn] = 1 if obj.name.lower().startswith("gear") else 0
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)  # a .glb's mesh is split along every seam of its texture
            bmesh.ops.triangulate(bm, faces=bm.faces)
            pieces.append((obj, data, bm))
        if not pieces:
            continue
        before = sum(len(bm.faces) for _, _, bm in pieces)
        cuts = 0
        while wrap and before * 4 ** (cuts + 1) <= full * 4:
            cuts += 1
        objects = []
        for obj, data, bm in pieces:
            for _ in range(cuts):
                bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=1, use_grid_fill=True)
                bmesh.ops.triangulate(bm, faces=bm.faces)
            # what lies wholly outside the zone and the little more the piece is drawn in is not needed
            reach = zone + LAP_M + 0.01
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if all((obj.matrix_world @ v.co - centre).length > reach for v in f.verts)], context="FACES")
            if kind == "neck":
                bmesh.ops.delete(bm, geom=[f for f in bm.faces if all(taken(obj.matrix_world @ v.co) for v in f.verts)], context="FACES")
                # and what is more the head's than the neck's is the head's card's: a tidy mesh's long triangles reach from
                # the neck well up behind the jaw, and what is left there swings out from under the hair when the head nods
                pulls = bm.verts.layers.deform.verify()
                heads = {i for i, g in enumerate(obj.vertex_groups) if folds.get(g.name) == "head"}
                share = lambda v: sum(w for g, w in v[pulls].items() if g in heads) / (sum(v[pulls].values()) or 1.0)
                bmesh.ops.delete(bm, geom=[f for f in bm.faces if sum(share(v) for v in f.verts) / len(f.verts) > HEADS], context="FACES")
            bm.to_mesh(data)
            bm.free()
            new = bpy.data.objects.new("joint %s" % j["bone"], data)
            scene.collection.objects.link(new)
            new.matrix_world = obj.matrix_world
            for g in obj.vertex_groups:
                new.vertex_groups.new(name=g.name)
            objects.append(new)
        count = sum(len(o.data.polygons) for o in objects)
        if count > full * 4:  # a tidy mesh with more than enough there: cut down, the pull carried along
            for o in objects:
                o.modifiers.new("fewer", "DECIMATE").ratio = full / float(count)
            graph = bpy.context.evaluated_depsgraph_get()
            for o in objects:
                fewer = bpy.data.meshes.new_from_object(o.evaluated_get(graph), preserve_all_data_layers=True, depsgraph=graph)
                o.modifiers.clear()
                o.data = fewer
        tagged = bpy.data.materials.new("joint %s" % j["bone"])
        for o in objects:
            o.data.materials.clear()
            o.data.materials.append(tagged)
            for poly in o.data.polygons:
                poly.use_smooth = True
        joints.append({"bone": j["bone"], "kind": kind, "between": j["between"], "ring_cm": j["ring_cm"], "zone_cm": round(zone * 100, 1), "reach_cm": round((zone + LAP_M) * 100, 1), "triangles": sum(len(o.data.polygons) for o in objects), "cut_from": before})
        if kind == "neck":
            # about: the bone whose head the zone and the piece are a ball about (not the joint's own, the head's);
            # aside: the one card that steps aside there (the head's stays whole); core_cm: and keeps nothing in it
            joints[-1].update(about="neck", aside=[j["between"][1]], core_cm=0.0)
        made += objects
        print("JOINTS %s (%s): a zone of %.1f cm; %d triangles of the tidy mesh there, made %d" % (j["bone"], kind, zone * 100, before, joints[-1]["triangles"]), flush=True)
    if dress and dress["root"] in rig.data.bones:
        # The dress. Which faces are the dress's: those the dress pulls on most, on average over their corners.
        key, root = dress["chains"][0][0], dress["root"]
        centre = head_of(root)

        def dress_faces(obj):
            groups = bake_impostor.groups_of(obj, folds, dress)
            share = np.zeros(len(obj.data.vertices))
            for v in obj.data.vertices:
                total = sum(g.weight for g in v.groups) or 1.0
                share[v.index] = sum(g.weight for g in v.groups if groups[g.group] == "dress") / total
            return [poly.index for poly in obj.data.polygons if share[list(poly.vertices)].mean() >= DRESS_PULL]

        # the pictured model's dress, as it rests: what the piece is laid onto, and how far it reaches
        laid_points, laid_faces, furthest = [], [], 0.0
        for obj in bodies:
            for i in dress_faces(obj):
                poly = obj.data.polygons[i]
                laid_faces.append([len(laid_points) + k for k in range(len(poly.vertices))])
                laid_points += [obj.matrix_world @ obj.data.vertices[v].co for v in poly.vertices]
        furthest = max([0.0] + [(p - centre).length for p in laid_points])
        dress_skin = BVHTree.FromPolygons(laid_points, laid_faces) if laid_faces else None
        # what it is cut from: the tidy version's dress (a clean skin, each triangle cut in four once or twice and laid
        # onto the pictured dress, as the knees are), or with --dress-from model the pictured dress cut down as it is
        from_model = dress_from_model
        objects, before = [], 0
        for obj in (bodies if from_model else [o for o in extra if o.type == "MESH" and o.find_armature() and not o.get("under")]):
            keep = dress_faces(obj)
            if not keep:
                continue
            data = obj.data.copy()
            for layer in list(data.uv_layers):
                data.uv_layers.remove(layer)
            bm = bmesh.new()
            bm.from_mesh(data)
            bm.faces.ensure_lookup_table()
            kept = set(keep)
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in kept], context="FACES")
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
            bmesh.ops.triangulate(bm, faces=bm.faces)
            before += len(bm.faces)
            lower, worn = bm.faces.layers.int.new("lower"), bm.faces.layers.int.new("gear")
            for f in bm.faces:
                f[lower], f[worn] = 1, 1
            bm.to_mesh(data)
            bm.free()
            new = bpy.data.objects.new("joint %s" % key, data)
            scene.collection.objects.link(new)
            new.matrix_world = obj.matrix_world
            for g in obj.vertex_groups:
                new.vertex_groups.new(name=g.name)
            objects.append(new)
        if objects and dress_skin is not None:
            cuts = 0
            while not from_model and before * 4 ** (cuts + 1) <= dress_triangles * 2:
                cuts += 1
            for o in objects:
                bm = bmesh.new()
                bm.from_mesh(o.data)
                for _ in range(cuts):
                    bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=1, use_grid_fill=True)
                bmesh.ops.triangulate(bm, faces=bm.faces)
                bm.to_mesh(o.data)
                bm.free()
            count = sum(len(o.data.polygons) for o in objects)
            if count > dress_triangles * 2:  # cut down as it is, the pull carried along
                for o in objects:
                    o.modifiers.new("fewer", "DECIMATE").ratio = dress_triangles / float(count)
                graph = bpy.context.evaluated_depsgraph_get()
                for o in objects:
                    fewer = bpy.data.meshes.new_from_object(o.evaluated_get(graph), preserve_all_data_layers=True, depsgraph=graph)
                    o.modifiers.clear()
                    o.data = fewer
            tagged = bpy.data.materials.new("joint %s" % key)
            for o in objects:
                bm = bmesh.new()  # (a cut-down mesh may have quads again)
                bm.from_mesh(o.data)
                bmesh.ops.triangulate(bm, faces=bm.faces)
                bm.to_mesh(o.data)
                bm.free()
                o.data.materials.clear()
                o.data.materials.append(tagged)
                for poly in o.data.polygons:
                    poly.use_smooth = True
            zone = furthest + DRESS_ROOM_M
            joints.append({"bone": key, "kind": "dress", "between": ["dress", folds.get(root, "hips")], "ring_cm": 0.1, "zone_cm": round(zone * 100, 1), "reach_cm": round(zone * DRESS_SWING * 100, 1),
                           "triangles": sum(len(o.data.polygons) for o in objects), "cut_from": before, "from": "model" if from_model else "tidy", "about": root, "aside": ["dress"], "core_cm": 0.0, "over_cm": round(DRESS_OVER_M * 100, 2),
                           "chains": len(dress["chains"]), "garments": dress["garments"]})
            made += objects
            print("JOINTS the dress (%s): %d chains from %s, a zone of %.1f cm; %d triangles of the %s there, made %d" % (", ".join(dress["garments"]), len(dress["chains"]), root, zone * 100, before,
                  "pictured model" if from_model else "tidy mesh", joints[-1]["triangles"]), flush=True)
    for obj in extra:
        bpy.data.objects.remove(obj)
    for obj in bodies:
        obj.hide_render = True
    bake_impostor.hang_arms(scene, rig)  # the pose the cards were pictured in
    into = {}
    for part, bone in bone_of.items():
        if bone in rest and bone in rig.pose.bones:
            moved = rig.pose.bones[bone].matrix @ rig.data.bones[bone].matrix_local.inverted()
            into[part] = np.array(Matrix(np.linalg.inv(rest[bone]).tolist()) @ bake_impostor.TO_GLB @ moved.inverted())

    # One mesh, one atlas: unwrapped afresh (the model's own unwrapping is in thousands of scraps).
    for obj in scene.objects:
        obj.select_set(False)
    for p in made:
        p.select_set(True)
    bpy.context.view_layer.objects.active = made[0]
    bpy.ops.object.join()
    whole = made[0]
    whole.name = "joints"
    whole.data.uv_layers.new(name="atlas")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(72.0), island_margin=0.012)
    bpy.ops.object.mode_set(mode="OBJECT")
    me = whole.data
    if wrap:
        # Onto the pictured model, once the pieces are unwrapped (a tidy surface unwraps into a few big patches; laid
        # onto every fold of the detailed one first, it unwraps into scraps): each point goes to the first of the
        # model's surface met coming in from outside, along the piece's own facing.
        back, turn = whole.matrix_world.inverted(), whole.matrix_world.to_3x3()
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.normal_update()
        lost = []
        was = {v.index: v.co.copy() for v in bm.verts}
        faced = {f.index: f.normal.copy() for f in bm.faces}
        necks = {s for s, m in enumerate(me.materials) if any(j["kind"] == "neck" and m.name == "joint %s" % j["bone"] for j in joints)}
        dresses = {s for s, m in enumerate(me.materials) if any(j["kind"] == "dress" and m.name == "joint %s" % j["bone"] for j in joints)}
        every = skin
        # Tried and left off (--pull pictured): on a body with garments put back on it, a piece cut from the skin under
        # a painted-on garment pulled as the pictured body is where it lies, not as the tidy skin was (the pictured body
        # took its pull from the tidy version's nearest surface, the painted garment's among them). It was thought to
        # be why her armpit came apart overhead; judge_joints.py found the skin drawn further off (0.6 to 0.9 cm) and
        # no fewer bare pixels.
        pulled_as = {} if wrap and worn is not None and flag("--pull", "worked") == "pictured" else None
        corners_of = {id(every): faces, id(skin_below): below}
        for v in bm.verts:
            if v.link_faces and v.link_faces[0].material_index in dresses:
                if dress_from_model:
                    continue  # cut from the pictured model: it lies there already
                at, out = whole.matrix_world @ v.co, (turn @ v.normal).normalized()
                hit, facing, _, far = dress_skin.ray_cast(at + out * DRESS_WRAP_M, -out, 2.0 * DRESS_WRAP_M)
                if hit is None or facing.dot(out) <= 0.0:
                    hit, facing, _, far = dress_skin.find_nearest(at)
                if hit is not None:
                    v.co = back @ hit
                continue
            at, out = whole.matrix_world @ v.co, (turn @ v.normal).normalized()
            skin = skin_below if v.link_faces and v.link_faces[0].material_index in necks else every
            hit, facing, index, far = skin.ray_cast(at + out * WRAP_M, -out, 2.0 * WRAP_M)
            if hit is None or facing.dot(out) <= 0.0:
                hit, facing, index, far = skin.find_nearest(at, WRAP_M)
            if hit is None:  # the tidy mesh has something here the pictured model has not: the nearest of it, however far
                lost.append(v)
                hit, facing, index, far = skin.find_nearest(at)
            if hit is not None:
                v.co = back @ hit
                if pulled_as is not None:  # the pictured body's pull there: its face's corners', the nearer counting more
                    total = {}
                    for corner in corners_of[id(skin)][index]:
                        share = 1.0 / max((points[corner] - hit).length, 1e-5)
                        for bone, w in body_pulls[corner].items():
                            total[bone] = total.get(bone, 0.0) + w * share
                    pulled_as[v.index] = total
        print("JOINTS laid onto the pictured model: %d of %d points found no surface within %g cm and went to the nearest there is" % (len(lost), len(bm.verts), WRAP_M * 100), flush=True)
        if pulled_as:
            layer = bm.verts.layers.deform.verify()
            slot = {g.name: g.index for g in whole.vertex_groups}
            bm.verts.ensure_lookup_table()
            for i, total in pulled_as.items():
                best = sorted(total.items(), key=lambda pair: -pair[1])[:4]
                whole_w = sum(w for _, w in best) or 1.0
                for bone, _ in best:
                    if bone not in slot:
                        slot[bone] = whole.vertex_groups.new(name=bone).index
                v = bm.verts[i]
                v[layer].clear()
                for bone, w in best:
                    v[layer][slot[bone]] = w / whole_w
            print("JOINTS %d points pulled as the pictured body is where they lie (its garments painted on)" % len(pulled_as), flush=True)
        # Did a piece lie down? Where the model is one skin (a knee in trousers, a bare shoulder) every triangle keeps
        # its shape and its facing. Where it is one thing inside another (a forearm in a wide cuff), points of one
        # triangle land on different layers and the triangle is pulled out into a shard, or turned over. A joint with
        # too much of its piece torn like that is better left to its cards.
        bm.normal_update()
        torn, whole_area, shards = {}, {}, set()
        for f in bm.faces:
            slot = me.materials[f.material_index].name
            stretch = max((e.calc_length() + 1e-9) / ((was[e.verts[0].index] - was[e.verts[1].index]).length + 1e-9) for e in f.edges)
            area = f.calc_area()
            whole_area[slot] = whole_area.get(slot, 0.0) + area
            if stretch > TORN_STRETCH or f.normal.dot(faced[f.index]) < 0.2:
                torn[slot] = torn.get(slot, 0.0) + area
                if f.material_index in necks:  # a collar's edge, a strap: left where the tidy mesh has it, not pulled to a shard
                    shards.update(f.verts)
        for v in shards:
            v.co = was[v.index]
        for j in joints:
            j["torn"] = round(torn.get("joint %s" % j["bone"], 0.0) / max(1e-9, whole_area.get("joint %s" % j["bone"], 0.0)), 3)
        # And does it cover what is there? A piece is one skin. Where the model is one thing inside another with air
        # between (a forearm in a wide cuff), one skin cannot be both: how much of the model's own surface in the
        # zone, of the joint's two parts, lies further than MISSED_M from the piece.
        laid = BVHTree.FromBMesh(bm)
        for j in joints:
            centre, zone = head_of(j.get("about", j["bone"])), j["zone_cm"] / 100.0
            total = missed = 0.0
            for obj in bodies:
                groups = [n in j.get("aside", j["between"]) for n in bake_impostor.groups_of(obj, folds, dress)]
                near = {}
                for poly in obj.data.polygons:
                    at = obj.matrix_world @ poly.center
                    if (at - centre).length >= zone or (j["kind"] == "neck" and any((at - c).length < z for c, z in shoulders)):
                        continue
                    for v in poly.vertices:
                        if v not in near:
                            pulls = obj.data.vertices[v].groups
                            near[v] = sum(g.weight for g in pulls if groups[g.group]) / (sum(g.weight for g in pulls) or 1.0)
                    if sum(near[v] for v in poly.vertices) / len(poly.vertices) < 0.5:
                        continue
                    total += poly.area
                    found = laid.find_nearest(whole.matrix_world.inverted() @ at, MISSED_M)
                    if found[0] is None:
                        missed += poly.area
            j["missed"] = round(missed / max(total, 1e-9), 3)
        dropped = [j for j in joints if (j["torn"] > max_torn or j["missed"] > max_missed) and j["kind"] != "dress"]  # (a dress is one skin over ruffles: what it misses is the ruffles' undersides)
        print("JOINTS torn, and missed: %s" % ", ".join("%s %.0f%% %.0f%%" % (j["bone"], 100 * j["torn"], 100 * j["missed"]) for j in joints), flush=True)
        if dropped:
            print("JOINTS left to their cards (too much of the piece would not lie down): %s" % ", ".join(j["bone"] for j in dropped), flush=True)
            gone = {"joint %s" % j["bone"] for j in dropped}
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if me.materials[f.material_index].name in gone], context="FACES")
            joints[:] = [j for j in joints if j not in dropped]
        # A scrap that came away from its piece (a few triangles on their own, where the trimming to the zone or a
        # point laid on the wrong layer cut them off) would hang in the air beside a bent joint: left out.
        seen, scraps = set(), []
        for start in bm.faces:
            if start in seen:
                continue
            island, todo = [], [start]
            seen.add(start)
            while todo:
                f = todo.pop()
                island.append(f)
                for e in f.edges:
                    for g in e.link_faces:
                        if g not in seen and g.material_index == f.material_index:
                            seen.add(g)
                            todo.append(g)
            if sum(f.calc_area() for f in island) < SCRAP * whole_area.get(me.materials[start.material_index].name, 0.0):
                scraps += island
        if scraps:
            print("JOINTS %d triangles in scraps that had come away from their pieces were left out" % len(scraps), flush=True)
            bmesh.ops.delete(bm, geom=scraps, context="FACES")
        bm.to_mesh(me)
        bm.free()
        me.update()
    print("JOINTS one mesh: %d points, %d triangles" % (len(me.vertices), len(me.polygons)), flush=True)

    # The pull on the neck's piece, worked over (the other joints keep the rig's own; yoke.py has the arithmetic).
    #   - A neck is not a hinge. The rig gives each point of it to one bone alone (a collar bone, the neck, the
    #     head), so the skin folds where two bones' points meet. The piece's pull is evened out along its surface
    #     (--even metres), the head's own points kept, so a turn or a nod is shared all the way down.
    #   - Cloth is not skin. A collar lies on the shoulders and the neck turns inside it. Where the tidy version
    #     has clothing as a mesh of its own, its points give --cloth of what the neck and head pull on them to
    #     the chest.
    #   - Tried and left off (--rim 0.3 turns it on, for the shoulders' pieces too): easing a piece's pull over to
    #     the chest bone toward its rim, so that it meets the chest's card without a step. It took the collar
    #     bone's lift out of the skin round a shoulder, and judge_joints.py scored a raised arm and a shrug worse.
    reworked = [j for j in joints if j["kind"] == "neck" or (rim > 0 and j["kind"] == "shoulder")] if rework else []
    if reworked:
        bones_of = [g.name for g in whole.vertex_groups]
        column = {name: i for i, name in enumerate(bones_of)}
        pull = np.zeros((len(me.vertices), len(bones_of)))
        for v in me.vertices:
            for g in v.groups:
                pull[v.index, g.group] = g.weight
        pull[:, [i for i, b in enumerate(bones_of) if b not in rig.pose.bones]] = 0.0  # (a group that is no bone of this skeleton pulls nothing)
        pull /= np.maximum(pull.sum(axis=1, keepdims=True), 1e-9)
        was_pull = pull.copy()
        slot_of, worn_at = np.full(len(me.vertices), -1), np.zeros(len(me.vertices), dtype=bool)
        worn = np.zeros(len(me.polygons), dtype=np.int32)
        me.attributes["gear"].data.foreach_get("value", worn)
        for p in me.polygons:
            slot_of[list(p.vertices)] = p.material_index
            if worn[p.index]:
                worn_at[list(p.vertices)] = True
        spot = np.array([whole.matrix_world @ v.co for v in me.vertices])
        edges = np.array([list(e.vertices) for e in me.edges], dtype=np.int64).reshape(-1, 2)
        slots = {m.name[len("joint "):]: s for s, m in enumerate(me.materials)}
        mine_of = [column[b] for b in ("chest", "shoulder_l", "shoulder_r", "neck") if b in column]  # the bones the chest's card stands for
        neck = next((j for j in joints if j["kind"] == "neck"), None)
        for j in reworked:
            mine = slot_of == slots[j["bone"]]
            if not mine.any():
                continue
            centre, zone = np.array(head_of(j.get("about", j["bone"]))), j["zone_cm"] / 100.0
            if j["kind"] == "neck":
                pull = yoke.lay_cloth(pull, mine & worn_at, column["neck"], column["head"], column["chest"], cloth)
                own = edges[mine[edges[:, 0]] & mine[edges[:, 1]]]
                length = float(np.linalg.norm(spot[own[:, 0]] - spot[own[:, 1]], axis=1).mean()) if len(own) else 1.0
                rounds = yoke.rounds_for(even_m, length)
                pull[mine] = yoke.spread_pull(pull, own, ~mine | (was_pull[:, column["head"]] > 0.99), rounds)[mine]
                j.update(even_cm=round(even_m * 100, 1), even_rounds=rounds, cloth=cloth, cloth_points=int((mine & worn_at).sum()))
                others, up = shoulders, np.array(head_of(j["bone"])) - centre
            else:
                others, up = [(np.array(head_of(neck["about"])), neck["zone_cm"] / 100.0)] if neck else [], None
            if rim > 0:
                eased = yoke.rim(pull, spot, centre, zone, mine_of, column["chest"], [(np.array(c), z) for c, z in others], up, rim)[0]
                pull[mine] = eased[mine]
                j["rim"] = rim
        changed = np.nonzero(np.abs(pull - was_pull).max(axis=1) > 1e-6)[0]
        pull = yoke.most(pull)
        # The cards were pictured with the arms hanging, the collar bones with them, and the skeleton stands so now. A
        # point whose pull has changed is moved, as it rests, to where the new pull puts it exactly where the old
        # one did in that pose: so the piece is the pictured surface there, and only differs as the bones leave it.
        held = np.array([np.array(rig.pose.bones[b].matrix @ rig.data.bones[b].matrix_local.inverted()) if b in rig.pose.bones else np.eye(4) for b in bones_of])
        to_rig = np.array(rig.matrix_world.inverted() @ whole.matrix_world)
        back = np.linalg.inv(to_rig)
        if len(changed):
            at_rest = np.array([list(me.vertices[i].co) for i in changed])
            again = yoke.rest_again(at_rest @ to_rig[:3, :3].T + to_rig[:3, 3], was_pull[changed], pull[changed], held)
            again = again @ back[:3, :3].T + back[:3, 3]
        for n, i in enumerate(changed):
            me.vertices[i].co = again[n].tolist()
            for g in whole.vertex_groups:
                g.remove([int(i)])
            for b in np.nonzero(pull[i] > 1e-4)[0]:
                whole.vertex_groups[int(b)].add([int(i)], float(pull[i, b]), "REPLACE")
        me.update()
        print("JOINTS the pull on %s worked over: %d points changed" % (", ".join(j["bone"] for j in reworked), len(changed)), flush=True)
    arm = whole.modifiers.new("skeleton", "ARMATURE")
    arm.object = rig
    whole.parent = rig

    # Where every texel of the atlas is on the model, in the pose the cards were pictured in.
    graph = bpy.context.evaluated_depsgraph_get()
    stood = bpy.data.meshes.new_from_object(whole.evaluated_get(graph), preserve_all_data_layers=True, depsgraph=graph)
    count = len(stood.vertices)
    at, facing = np.empty(count * 3, dtype=np.float32), np.empty(count * 3, dtype=np.float32)
    stood.vertices.foreach_get("co", at)
    stood.vertices.foreach_get("normal", facing)
    at, facing = at.reshape(-1, 3).astype(np.float64), facing.reshape(-1, 3).astype(np.float64)
    tris = np.array([list(p.vertices) for p in me.polygons], dtype=np.int64)
    assert tris.shape[1] == 3, "the pieces are triangles"
    loops = np.array([list(p.loop_indices) for p in me.polygons], dtype=np.int64)
    uv = np.empty(len(me.loops) * 2, dtype=np.float32)
    me.uv_layers["atlas"].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)[loops]
    lower = np.zeros(len(me.polygons), dtype=np.int32)
    me.attributes["lower"].data.foreach_get("value", lower)
    slot = np.array([p.material_index for p in me.polygons])
    names = [m.name[len("joint "):] for m in me.materials]
    face, weights = rasterise(uv, size)
    ys, xs = np.nonzero(face >= 0)
    hit = face[ys, xs]
    w = weights[ys, xs].astype(np.float64)
    where = (at[tris[hit]] * w[..., None]).sum(axis=1)
    turned = (facing[tris[hit]] * w[..., None]).sum(axis=1)
    turned /= np.maximum(np.linalg.norm(turned, axis=1, keepdims=True), 1e-9)
    by_bone = {j["bone"]: j for j in joints}
    part_of = np.array([by_bone[names[slot[t]]]["between"][0 if lower[t] else 1] for t in range(len(tris))])
    rest_turn = {part: rest[bone][:3, :3] / np.cbrt(abs(np.linalg.det(rest[bone][:3, :3]))) for part, bone in bone_of.items() if bone in rest}

    for j in joints:
        j["part"] = j.get("aside", j["between"])[0]
    dress_joints = [{"bone": j["bone"], "between": j["between"], "ring_cm": j["ring_cm"], "lap_cm": 0.0, "ball_cm": 0.0, "dress": True} for j in joints if j["kind"] == "dress"]
    triangles = int(len(tris))
    out_folders = []
    for folder, source_name in zip(folders, sources):
        with open(os.path.join(folder, "impostor.json")) as f:
            this = json.load(f)
        character = impostor.Character(folder)
        colour = np.zeros((size, size, 3), dtype=np.float32)
        normal = np.zeros((size, size, 3), dtype=np.float32)
        known = np.zeros((size, size), dtype=bool)
        missed = 0
        for j in joints:
            for n, part_name in enumerate(j["between"]):
                other = j["between"][1 - n]
                mine = (part_of[hit] == part_name) & (np.array(names)[slot[hit]] == j["bone"])
                if not mine.any():
                    continue
                got = None
                # its own part's pictures first, then those with a surface a little further from the place; what they do not
                # show, the other part's may
                for asked, seen_m in ((part_name, SEEN_M), (part_name, 2.5 * SEEN_M), (other, SEEN_M), (other, 2.5 * SEEN_M)):
                    part = next(p for p in this["parts"] if p["name"] == asked)
                    m = into[asked]
                    c, f, found = look_up(character, part, where[mine] @ m[:3, :3].T + m[:3, 3], turned[mine] @ m[:3, :3].T, seen_m)
                    f = f @ rest_turn[asked].T  # as the model has it at rest, in a .glb's directions
                    if got is None:
                        got = [c, f, found]
                    else:
                        more = found & ~got[2]
                        got[0][more], got[1][more], got[2][more] = c[more], f[more], True
                colour[ys[mine], xs[mine]], normal[ys[mine], xs[mine]], known[ys[mine], xs[mine]] = got[0], got[1], got[2]
                missed += int((~got[2]).sum())
        colour = bake_impostor.spread(colour, known, 64)   # what no picture saw takes its neighbour's
        normal = bake_impostor.spread(normal, known, 64)
        filled = bake_impostor.spread(known, known, PAD_PX)
        normal = np.where(np.linalg.norm(normal, axis=-1, keepdims=True) > 0.1, normal, (0.0, 1.0, 0.0))
        sheet = np.zeros((size, size, 4), dtype=np.uint8)
        sheet[..., :3] = np.round(np.clip(colour, 0.0, 1.0) * 255.0)
        sheet[..., 3] = np.where(filled | (face >= 0), 255, 0)
        data = np.zeros((size, size, 3), dtype=np.uint8)
        data[..., :2] = np.round(np.clip(impostor.pack_normal(normal), 0.0, 1.0) * 255.0)
        data[..., 2] = 255
        out = "%s-%s" % (re.sub("-joined$", "", folder), name)
        os.makedirs(out, exist_ok=True)
        impostor.write_png(os.path.join(out, "joints-color.png"), sheet)
        impostor.write_png(os.path.join(out, "joints-data.png"), data)
        # the dress's zone is read as any joint's is: its card steps aside wherever its piece is drawn
        this["joints"] = [j for j in this.get("joints") or [] if not j.get("dress")] + dress_joints
        for sheet_set in this["sets"].values():  # the cards' own sheets are read where they are
            sheet_set["color"], sheet_set["data"] = "../%s/%s" % (os.path.basename(folder), sheet_set["color"]), "../%s/%s" % (os.path.basename(folder), sheet_set["data"])
        this["skin"] = {"file": "joints.glb", "color": "joints-color.png", "data": "joints-data.png", "size": [size, size], "triangles": triangles, "joints": joints,
                        "cards_from": os.path.basename(folder), "unseen_texels": round(missed / float(max(1, len(hit))), 4), "memory_mb": round(size * size * 8 / 1e6, 2)}
        with open(os.path.join(out, "impostor.json"), "w") as f:
            json.dump(this, f, indent=1)
        out_folders.append(out)
        print("JOINTS %s: %d triangles in %d joints; %.1f%% of the atlas had no picture to take its colour from" % (os.path.basename(out), triangles, len(joints), 100.0 * missed / max(1, len(hit))), flush=True)

    # The file: the pieces at rest, with the skeleton.
    for b in rig.pose.bones:
        b.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    for obj in list(scene.objects):
        if obj not in (whole, rig):
            bpy.data.objects.remove(obj)
    whole.select_set(True)
    rig.select_set(True)
    first = os.path.join(out_folders[0], "joints.glb")
    bpy.ops.export_scene.gltf(filepath=first, export_format="GLB", use_selection=True, export_animations=False, export_materials="EXPORT", export_yup=True, export_skins=True, export_normals=True, export_texcoords=True)
    with open(first, "rb") as f:
        blob = f.read()
    for out in out_folders:
        if out != out_folders[0]:
            with open(os.path.join(out, "joints.glb"), "wb") as f:
                f.write(blob)
        with open(os.path.join(out, "impostor.json")) as f:
            this = json.load(f)
        this["skin"]["bytes"] = {"file": len(blob), "color": os.path.getsize(os.path.join(out, "joints-color.png")), "data": os.path.getsize(os.path.join(out, "joints-data.png"))}
        with open(os.path.join(out, "impostor.json"), "w") as f:
            json.dump(this, f, indent=1)
    print("RESULT " + json.dumps({"folders": out_folders, "triangles": triangles, "joints": len(joints), "file_bytes": len(blob), "seconds": round(time.time() - began, 1)}))


if __name__ == "__main__":
    main()
