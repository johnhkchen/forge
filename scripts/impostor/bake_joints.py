"""Gives a character's flat cards real joints: a small piece of the model itself, with its skeleton's pull, for
every knee, elbow, hip and shoulder.

    Blender -b --factory-startup -P scripts/impostor/bake_joints.py -- <run> <profile>
        [--from joe-joined,pixel-clear,pixel-joined,comic-joined] [--name skinned] [--triangles 320] [--atlas 512]
        [--zone knee=1.6,elbow=1.7,hip=1.25,shoulder=1.35] [--margin 0.2] [--kinds knee,elbow,hip,shoulder] [--torn 0.4] [--missed 0.5] [--leave forearm_l,...]

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

KINDS = {"shin": "knee", "forearm": "elbow", "upper_arm": "shoulder", "thigh": "hip"}
SEEN_M = 0.012      # a place on a piece is in a card's picture when the picture's surface is this near it
WRAP_M = 0.06       # a piece cut from a tidy mesh is laid onto the pictured model's surface when that is within this of it
JOE_INK = np.array([0.07, 0.055, 0.086], dtype=np.float32)  # what bake_impostor.py draws a fold in
LAP_M = 0.015       # a piece is drawn this far past its zone, under the cards' edge, so no crack opens between them
LEAST_M = {"elbow": 0.08, "knee": 0.10}  # a zone is never smaller than this: a ring found small (a rolled sleeve) is not a small joint
TORN_STRETCH = 2.5  # a triangle with an edge pulled out to this many times its length did not lie down on the model
MISSED_M = 0.015    # the model's surface this far from a piece is not covered by it
SCRAP = 0.03        # an island of a piece with less than this share of the piece's area is a scrap
PAD_PX = 6          # the colour round every patch of the atlas is carried this far outward


def kind_of(bone):
    return KINDS.get(bone[:-2], "")


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
    name, target, size = flag("--name", "skinned"), int(flag("--triangles", "320")), int(flag("--atlas", "512"))
    zones = dict((k, float(v)) for k, v in (pair.split("=") for pair in flag("--zone", "knee=1.6,elbow=1.7,hip=1.25,shoulder=1.35").split(",")))
    leave = set(flag("--leave", "").split(","))  # joints to leave to their cards whatever the bake finds (judge_joints.py says which do better so)
    with open(os.path.join(HERE, "joints.json")) as f:  # ... and the ones written down for this character
        leave |= set(json.load(f).get(re.sub(r"^\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d-", "", os.path.basename(run)), {}).get("leave", []))
    max_torn, max_missed = float(flag("--torn", "0.4")), float(flag("--missed", "0.5"))
    margin, kinds = float(flag("--margin", "0.2")), flag("--kinds", "knee,elbow,hip,shoulder").split(",")
    profiles = os.path.join(run, "profiles")
    sources = [s for s in sources if os.path.isfile(os.path.join(profiles, "%s-impostor-%s" % (profile, s), "impostor.json"))]  # the cards there are
    folders = [os.path.join(profiles, "%s-impostor-%s" % (profile, s)) for s in sources]
    with open(os.path.join(folders[0], "impostor.json")) as f:
        card = json.load(f)
    source = os.path.join(profiles, card["source"])
    began = time.time()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.import_scene.gltf(filepath=source)
    rig = next(o for o in scene.objects if o.type == "ARMATURE")
    bodies = [o for o in scene.objects if o.type == "MESH" and o.find_armature() and not o.get("under")]
    rest = impostor.Glb(source).pose(None)
    folds = bake_impostor.part_of_bone(rig)
    bone_of = {n: bones[0] for n, bones in bake_impostor.PARTS}
    # The pictured model as it rests, to lay the pieces on.
    points, faces = [], []
    for obj in bodies:
        first = len(points)
        points += [obj.matrix_world @ v.co for v in obj.data.vertices]
        faces += [[first + i for i in poly.vertices] for poly in obj.data.polygons]
    skin = BVHTree.FromPolygons(points, faces)
    # What the pieces are cut from: a tidy mesh with this skeleton. A detailed mesh is not one (a third of a million
    # triangles that fold through each other: cutting it down stalls), so its pieces are cut from the rigged version
    # whose clips the cards play, each face cut in four until there are enough, and laid onto the detailed surface.
    wrap = card.get("plays", profile) != profile and os.path.isfile(os.path.join(profiles, "%s-walk.glb" % card["plays"]))
    if wrap:
        known = set(scene.objects)
        bpy.ops.import_scene.gltf(filepath=os.path.join(profiles, "%s-walk.glb" % card["plays"]))
        extra = [o for o in scene.objects if o not in known]
        tidy = [o for o in extra if o.type == "MESH" and o.find_armature() and not o.get("under")]
    else:
        extra, tidy = [], bodies

    joints, made = [], []
    for j in card["joints"]:
        kind = kind_of(j["bone"])
        if kind not in kinds or kind not in zones or j["bone"] in leave:
            continue
        ring = j["ring_cm"] / 100.0
        zone = max(zones[kind] * ring, LEAST_M.get(kind, 0.0))
        centre = rig.matrix_world @ rig.data.bones[j["bone"]].head_local
        pieces = []
        for obj in tidy:
            groups = [folds.get(g.name) for g in obj.vertex_groups]
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
            for f in bm.faces:
                f[tell] = 1 if f.index in keep and keep[f.index][0] >= keep[f.index][1] else 0
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)  # a .glb's mesh is split along every seam of its texture
            bmesh.ops.triangulate(bm, faces=bm.faces)
            pieces.append((obj, data, bm))
        if not pieces:
            continue
        before = sum(len(bm.faces) for _, _, bm in pieces)
        cuts = 0
        while wrap and before * 4 ** (cuts + 1) <= target * 4:
            cuts += 1
        objects = []
        for obj, data, bm in pieces:
            for _ in range(cuts):
                bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=1, use_grid_fill=True)
                bmesh.ops.triangulate(bm, faces=bm.faces)
            # what lies wholly outside the zone and the little more the piece is drawn in is not needed
            reach = zone + LAP_M + 0.01
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if all((obj.matrix_world @ v.co - centre).length > reach for v in f.verts)], context="FACES")
            bm.to_mesh(data)
            bm.free()
            new = bpy.data.objects.new("joint %s" % j["bone"], data)
            scene.collection.objects.link(new)
            new.matrix_world = obj.matrix_world
            for g in obj.vertex_groups:
                new.vertex_groups.new(name=g.name)
            objects.append(new)
        count = sum(len(o.data.polygons) for o in objects)
        if count > target * 4:  # a tidy mesh with more than enough there: cut down, the pull carried along
            for o in objects:
                o.modifiers.new("fewer", "DECIMATE").ratio = target / float(count)
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
        made += objects
        print("JOINTS %s (%s): a zone of %.1f cm; %d triangles of the tidy mesh there, made %d" % (j["bone"], kind, zone * 100, before, joints[-1]["triangles"]), flush=True)
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
        for v in bm.verts:
            at, out = whole.matrix_world @ v.co, (turn @ v.normal).normalized()
            hit, facing, _, far = skin.ray_cast(at + out * WRAP_M, -out, 2.0 * WRAP_M)
            if hit is None or facing.dot(out) <= 0.0:
                hit, facing, _, far = skin.find_nearest(at, WRAP_M)
            if hit is None:  # the tidy mesh has something here the pictured model has not: the nearest of it, however far
                lost.append(v)
                hit, facing, _, far = skin.find_nearest(at)
            if hit is not None:
                v.co = back @ hit
        print("JOINTS laid onto the pictured model: %d of %d points found no surface within %g cm and went to the nearest there is" % (len(lost), len(bm.verts), WRAP_M * 100), flush=True)
        # Did a piece lie down? Where the model is one skin (a knee in trousers, a bare shoulder) every triangle keeps
        # its shape and its facing. Where it is one thing inside another (a forearm in a wide cuff), points of one
        # triangle land on different layers and the triangle is pulled out into a shard, or turned over. A joint with
        # too much of its piece torn like that is better left to its cards.
        bm.normal_update()
        torn, whole_area = {}, {}
        for f in bm.faces:
            slot = me.materials[f.material_index].name
            stretch = max((e.calc_length() + 1e-9) / ((was[e.verts[0].index] - was[e.verts[1].index]).length + 1e-9) for e in f.edges)
            area = f.calc_area()
            whole_area[slot] = whole_area.get(slot, 0.0) + area
            if stretch > TORN_STRETCH or f.normal.dot(faced[f.index]) < 0.2:
                torn[slot] = torn.get(slot, 0.0) + area
        for j in joints:
            j["torn"] = round(torn.get("joint %s" % j["bone"], 0.0) / max(1e-9, whole_area.get("joint %s" % j["bone"], 0.0)), 3)
        # And does it cover what is there? A piece is one skin. Where the model is one thing inside another with air
        # between (a forearm in a wide cuff), one skin cannot be both: how much of the model's own surface in the
        # zone, of the joint's two parts, lies further than MISSED_M from the piece.
        laid = BVHTree.FromBMesh(bm)
        for j in joints:
            centre, zone = rig.matrix_world @ rig.data.bones[j["bone"]].head_local, j["zone_cm"] / 100.0
            total = missed = 0.0
            for obj in bodies:
                groups = [folds.get(g.name) in j["between"] for g in obj.vertex_groups]
                near = {}
                for poly in obj.data.polygons:
                    at = obj.matrix_world @ poly.center
                    if (at - centre).length >= zone:
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
        dropped = [j for j in joints if j["torn"] > max_torn or j["missed"] > max_missed]
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
        j["part"] = j["between"][0]
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
