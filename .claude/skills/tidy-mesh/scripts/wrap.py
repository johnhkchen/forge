# Give a character the wardrobe's shared body: lay the template body over the
# character's own, from the collar down, and keep the character's own head.
#
# Every character built here has a body of its own making: different pieces,
# different points, a different texture layout. So clothes made for one fit
# nobody else. The template is one body (the MakeHuman base mesh, cut off at
# the collar and made lighter; see wardrobe/README.md) with one texture
# layout. Laid over each character, a spot of its texture is the same spot of
# the body on everyone: the left knee is the left knee. Skin-tight clothes can
# then be painted into that texture (paint.py) instead of worn as meshes, and
# an outfit painted for one character can be worn by another.
#
# What it does, in the open scene (a character's low-poly or mid-poly .glb,
# standing in its T-pose: z up, feet on z = 0, facing -y):
#   1. the character's body meshes ("body" and every "body under: ...") are
#      put together as one "base body", and a fine shell is drawn round it:
#      the surface to land on (a block-out is overlapping pieces; the shell is
#      their one outer skin);
#   2. the template is brought in and each of its bones is carried to where
#      that joint is on this character ("joints": rig.py's own, so run rig.py
#      first and pass them on), stretched along the bone and made as thick as
#      the body is around it. The hands keep the template's fingers, sized to
#      the hand ("keep_hands");
#   3. it is drawn onto the shell: each point goes to the nearest surface a
#      little at a time and slides along it to stay evenly spread. The points
#      on the open collar slide along the collar only, so it stays where it
#      was cut. Faces left spanning a hollow (across an armpit) are sunk in;
#   4. the character's own head is every piece of its body that stands above
#      the collar (the neck piece comes whole, so it reaches down inside the
#      collar and no gap shows when the head turns). It is joined on. Below
#      the collar the neck is tucked a little inside the template: the
#      template was drawn onto that very surface, and two skins in one place
#      flicker through each other (Lincoln's showed as a black slit down the
#      front of his throat).
#
# What is left: "body" is the template from the collar down plus the
# character's own head. The template's faces have a material of their own,
# marked "template" with the template's name: that mark is how rig.py knows
# to weight those faces from the template's own weights, and it travels in a
# .glb. The old body is kept, hidden, as "base body" (tagged "wardrobe":
# "base") for paint.py to copy the skin from; paint.py removes it.
#
# Read the result: "to_body_pct" is how far the template's points ended up
# from the character's own surface (share of its height: the middle one, 95
# in 100, the worst); "body_to_template_pct" the other way round, for the
# body's points that show; "folded_edges" should be few; "collar" says how
# far the head reaches down inside the collar ("head_below_ring_cm") and how
# far the ring stands from the neck ("ring_to_head_cm").
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down.
# Prints RESULT {json}. About ten seconds. Safe-mode compatible.

PARAMS = {
    "template": None,     # absolute path of the wardrobe template .glb (required): the skill's wardrobe/headless-1.0.glb
    "joints": None,       # where this character's joints are: rig.py's "joints" (required)
    "bodies": None,       # names of the body meshes; None = every mesh in the scene tagged as body
    "name": "body",       # what to call the new body
    "keep_hands": True,   # hands keep the template's fingers, sized and set at the wrist; False = drawn onto the body's own hand like everything else
    "rounds": 40,         # how many small steps onto the body
    "voxel": 0.004,       # how fine the shell round the body is, as a share of the height
}

import bpy
import bmesh
import json
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

BONES = [("hips", "hips", "spine"), ("spine", "spine", "chest"), ("chest", "chest", "neck"), ("neck", "neck", "head"), ("head", "head", "head_top")]
for side in "lr":
    BONES += [("shoulder_" + side, "shoulder_" + side, "upper_arm_" + side), ("upper_arm_" + side, "upper_arm_" + side, "forearm_" + side),
              ("forearm_" + side, "forearm_" + side, "hand_" + side), ("hand_" + side, "hand_" + side, "hand_tip_" + side),
              ("thigh_" + side, "thigh_" + side, "shin_" + side), ("shin_" + side, "shin_" + side, "foot_" + side),
              ("foot_" + side, "foot_" + side, "toe_" + side), ("toe_" + side, "toe_" + side, "toe_tip_" + side)]
ORDER = [None]  # the face layer read_template sorts by


def by_order(face):
    return face[ORDER[0]]

def by_box(part):
    lo = Vector([min(v.co[k] for v in part) for k in range(3)])
    hi = Vector([max(v.co[k] for v in part) for k in range(3)])
    size = hi - lo
    return (size.x + 1e-6) * (size.y + 1e-6) * (size.z + 1e-6)

def tree_of(obj):
    me = obj.data
    return BVHTree.FromPolygons([obj.matrix_world @ v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])

def copy_of(obj, name):
    """A copy of a mesh object standing where it stands, with nothing between it and the world."""
    new = obj.copy()
    new.data = obj.data.copy()
    new.name = name
    bpy.context.scene.collection.objects.link(new)
    world = obj.matrix_world.copy()
    new.parent = None
    for mod in list(new.modifiers):
        new.modifiers.remove(mod)
    new.data.transform(world)
    new.matrix_world = Matrix.Identity(4)
    new.hide_set(False)
    new.hide_viewport = False
    return new

def join(objs, name):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    out = bpy.context.view_layer.objects.active
    out.name = out.data.name = name
    out.select_set(False)
    return out

def loose_parts(bm):
    """The connected pieces of a mesh, as lists of its points."""
    seen, parts = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        part, stack = [], [v]
        seen.add(v.index)
        while stack:
            a = stack.pop()
            part.append(a)
            for e in a.link_edges:
                b = e.other_vert(a)
                if b.index not in seen:
                    seen.add(b.index)
                    stack.append(b)
        parts.append(part)
    return parts

def read_template(path):
    """The template .glb as one welded mesh with its quads and regions back (the file holds triangles and says
    which pairs were quads). Returns the object; its notes ride on it."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path, merge_vertices=True)
    new = [o for o in bpy.data.objects if o not in before]
    found = [o for o in new if o.type == "MESH" and o.get("template")]
    if not found:
        raise ValueError("%s is not a wardrobe template: no mesh in it says \"template\"" % path)
    obj = found[0]
    world = obj.matrix_world.copy()
    obj.parent = None
    for mod in list(obj.modifiers):
        obj.modifiers.remove(mod)
    obj.data.transform(world)
    obj.matrix_world = Matrix.Identity(4)
    for o in new:
        if o is not obj:
            bpy.data.objects.remove(o, do_unlink=True)
    sizes = obj["template_faces"]
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    region = bm.faces.layers.int.new("region")
    ORDER[0] = bm.faces.layers.int.new("order")
    cuts, at = [], 0
    for number, (size, code) in enumerate(zip(sizes, obj["template_regions"])):
        mine = [bm.faces[at], bm.faces[at + 1]] if size == "4" else [bm.faces[at]]
        for f in mine:
            f[region], f[ORDER[0]] = int(code, 16), number
        if size == "4":  # two triangles in a row that were one quad: the edge they share goes
            cuts.append([e for e in mine[0].edges if mine[1] in e.link_faces][0])
        at += len(mine)
    bmesh.ops.dissolve_edges(bm, edges=cuts, use_verts=False)
    bm.faces.sort(key=by_order)  # the faces in the order the template has them
    bm.faces.layers.int.remove(ORDER[0])
    bm.to_mesh(obj.data)
    bm.free()
    return obj

def frame_of(along):
    """Two unit directions square to `along`, starting from the two world axes least like it."""
    axes = [Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))]
    most = 0
    for k in (1, 2):
        if abs(axes[k].dot(along)) > abs(axes[most].dot(along)):
            most = k
    del axes[most]
    if abs(axes[1].dot(along)) < abs(axes[0].dot(along)):
        axes.reverse()
    e1 = (axes[0] - along * axes[0].dot(along)).normalized()
    return e1, along.cross(e1).normalized()

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

def thickness(tree, a, b, e1, e2, cap):
    """How thick the body is round the bone a-b, each of two ways across it: the middle of what rays off the bone meet."""
    out = []
    for e in (e1, e2):
        hits = []
        for t in (0.2, 0.35, 0.5, 0.65, 0.8):
            p = a.lerp(b, t)
            for way in (1, -1):
                hit = tree.ray_cast(p, e * way, cap)
                if hit[0] is not None:
                    hits.append(hit[3])
        hits.sort()
        out.append(hits[len(hits) // 2] if len(hits) >= 3 else None)
    return out

def stats(values, tall):
    v = sorted(values)
    if not v:
        return None
    return {"median": round(100 * v[len(v) // 2] / tall, 3), "p95": round(100 * v[int(0.95 * (len(v) - 1))] / tall, 3), "worst": round(100 * v[-1] / tall, 3)}

def put(mesh, points):
    """The points onto the mesh; returns each point's own facing."""
    for v, p in zip(mesh.vertices, points):
        v.co = p
    mesh.update()
    return [v.normal.copy() for v in mesh.vertices]

def mean_of(points, which):
    total = Vector()
    for k in which:
        total += points[k]
    return total / len(which)

def settle(points, idle, nbrs, sweeps):
    """Points that are never drawn to the body (inside a fold of the template's own) ride with the points round them."""
    for _ in range(sweeps):
        for i in idle:
            points[i] = mean_of(points, nbrs[i])


scene = bpy.context.scene
if not PARAMS["template"]:
    raise ValueError("set PARAMS['template'] to the wardrobe template's .glb (the skill's wardrobe/headless-1.0.glb)")
if not PARAMS["joints"]:
    raise ValueError("set PARAMS['joints'] to rig.py's \"joints\" for this character: run rig.py first")
if PARAMS["bodies"]:
    bodies = [bpy.data.objects[n] for n in PARAMS["bodies"]]
else:
    bodies = [o for o in scene.objects if o.type == "MESH" and o.get("forge") == "body" and not o.name.startswith("lines:")]
if not bodies:
    raise ValueError("no body here: this needs a character's .glb with its \"body\" mesh (and gear as meshes of its own)")
if any(o.data.materials and o.data.materials[0] is not None and o.data.materials[0].get("template") for o in bodies):
    raise ValueError("this body is already the template: wrap.py is for a character's own body")

# ---- 1. the base body, and a shell round it to land on ----
keep_tags = {k: bodies[0][k] for k in ("forge",) if k in bodies[0]}
base = join([copy_of(o, "base body") for o in bodies], "base body")
for key in list(base.keys()):
    del base[key]
base["wardrobe"] = "base"
bm = bmesh.new()
bm.from_mesh(base.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)  # a .glb splits points along texture seams: one piece is one piece again
bm.to_mesh(base.data)
bm.free()
floor = min(v.co.z for v in base.data.vertices)
top = max(v.co.z for v in base.data.vertices)
tall = top - floor
reach_x = max(abs(v.co.x) for v in base.data.vertices)
base_tree = tree_of(base)

shell = copy_of(base, "shell")
for o in bpy.context.selected_objects:
    o.select_set(False)
shell.select_set(True)
bpy.context.view_layer.objects.active = shell
shell.data.remesh_voxel_size = PARAMS["voxel"] * tall
shell.data.remesh_voxel_adaptivity = 0.0
bpy.ops.object.voxel_remesh()
bm = bmesh.new()
bm.from_mesh(shell.data)
parts = sorted(loose_parts(bm), key=by_box, reverse=True)
for part in parts[1:]:  # the outer skin only: walls inside it (where pieces overlapped) go
    bmesh.ops.delete(bm, geom=part, context="VERTS")
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(shell.data)
bm.free()
target = tree_of(shell)

# ---- 2. the template, each bone carried to this character's joint ----
J = {k: Vector(v) for k, v in PARAMS["joints"].items()}
J["head_top"] = Vector((J["head"].x, J["head"].y, top))
for tag, flip in (("_l", 1.0), ("_r", -1.0)):
    J["hand_tip" + tag] = Vector((flip * reach_x, J["hand" + tag].y, J["hand" + tag].z))
    foot = [v.co for v in base.data.vertices if v.co.z - floor < 1.5 * (J["foot" + tag].z - floor) and v.co.x * flip > 0]
    J["toe_tip" + tag] = Vector((J["toe" + tag].x, min([p.y for p in foot] or [J["toe" + tag].y - 0.05 * tall]), J["toe" + tag].z))
template = read_template(PARAMS["template"])
template_name = template["template"]
C = {k: Vector(v) for k, v in json.loads(template["template_canon"]).items()}
missing = [name for name, a, b in BONES if a not in J or b not in J]
if missing:
    raise ValueError("no joint for %s: \"joints\" should be rig.py's own" % ", ".join(missing))
tmesh = template.data
rest = [v.co.copy() for v in tmesh.vertices]
count = len(rest)
template_tree = tree_of(template)

carry, fit = {}, {}
for name, a, b in BONES:
    a0, b0, a1, b1 = C[a], C[b], J[a], J[b]
    d0, d1 = (b0 - a0).normalized(), (b1 - a1).normalized()
    e1, e2 = frame_of(d0)
    turn = d0.rotation_difference(d1).to_matrix()
    r0 = thickness(template_tree, a0, b0, e1, e2, 0.3)
    r1 = thickness(target, a1, b1, turn @ e1, turn @ e2, 0.3 * tall / 1.8)
    wide = [clamp(r1[k] / r0[k], 0.4, 3.0) if (r0[k] and r1[k]) else None for k in (0, 1)]
    s1, s2 = (wide[0] or wide[1] or tall / 1.8), (wide[1] or wide[0] or tall / 1.8)
    long = (b1 - a1).length / (b0 - a0).length
    if name.startswith("hand_") and PARAMS["keep_hands"]:
        s1 = s2 = long  # the hand keeps its own shape, sized as one
    basis = Matrix((d0, e1, e2)).transposed()  # columns: along the bone, and two ways across it
    carry[name] = (turn @ basis @ Matrix.Diagonal((long, s1, s2)) @ basis.transposed(), a0, a1)
    fit[name] = {"along": round(long, 2), "thick": [round(s1, 2), round(s2, 2)]}

# the template's own weights say how much of each bone's move a point takes
names = [b[0] for b in BONES]
group_bone = {g.index: g.name for g in template.vertex_groups if g.name in names}
weights = []
for v in tmesh.vertices:
    mine = [(group_bone[g.group], g.weight) for g in v.groups if g.group in group_bone and g.weight > 0]
    total = sum(w for _, w in mine) or 1.0
    weights.append([(n, w / total) for n, w in mine])
P = []
for i in range(count):
    at = Vector()
    for name, w in weights[i]:
        move, a0, a1 = carry[name]
        at += w * (move @ (rest[i] - a0) + a1)
    P.append(at if weights[i] else rest[i].copy())
hold = [sum(w for n, w in weights[i] if n in ("hand_l", "hand_r")) if PARAMS["keep_hands"] else 0.0 for i in range(count)]

# ---- 3. onto the shell ----
bm = bmesh.new()
bm.from_mesh(tmesh)
bm.verts.ensure_lookup_table()
# a point on the open collar slides along the collar only, so the collar does not creep down the neck
nbrs = [[e.other_vert(v).index for e in v.link_edges if (not v.is_boundary) or e.is_boundary] for v in bm.verts]
ring = [v.index for v in bm.verts if v.is_boundary]
bm.free()
faces = [list(p.vertices) for p in tmesh.polygons]
# Parts of the template that face its own surface close by (between fingers and toes) are never drawn to the
# body: they ride along with the points around them.
facing = [v.normal.copy() for v in tmesh.vertices]
passive = [template_tree.ray_cast(rest[i] + facing[i] * 1e-3, facing[i], 0.02)[0] is not None for i in range(count)]
idle = [i for i in range(count) if passive[i] and hold[i] < 0.5]
live = [i for i in range(count) if not passive[i] and hold[i] < 0.5]
rounds = max(8, int(PARAMS["rounds"]))
for it in range(rounds):
    normals = put(tmesh, P)
    answered = [False] * count
    step = 0.5 if it < rounds - 4 else 1.0
    for i in range(count):
        if passive[i]:
            continue
        near = target.find_nearest(P[i])
        # the nearest surface, if it faces the way the point does (the far wall of an armpit does not); any, at the end
        if near[0] is not None and near[1].dot(normals[i]) > (0.0 if it < rounds - 6 else -1.0):
            answered[i] = True
            P[i] = P[i] + (near[0] - P[i]) * (step * (1.0 - hold[i]))
    if it < rounds - 4:  # slide along the surface to stay evenly spread
        avg = [mean_of(P, nbrs[i]) for i in range(count)]
        normals = put(tmesh, P)
        ease = 0.5 if it < rounds - 12 else 0.2
        for i in range(count):
            slide = avg[i] - P[i]
            slide -= normals[i] * slide.dot(normals[i])
            P[i] = P[i] + slide * (ease * (1.0 - hold[i]))
        for i in live:  # a point the body did not answer for follows its neighbours
            if not answered[i]:
                P[i] = avg[i]
    settle(P, idle, nbrs, 400 if it in (0, rounds - 1) else 25)
put(tmesh, P)

# faces left spanning a hollow (chin to chest, across an armpit): sink them in
def spanning():
    out = []
    for fi, ring_of in enumerate(faces):
        if any(passive[k] or hold[k] >= 0.5 for k in ring_of):
            continue
        mid = mean_of(P, ring_of)
        hit = target.find_nearest(mid)
        if hit[3] > 0.005 * tall:
            out.append((fi, hit[0] - mid))
    return out

bridges_before = len(spanning())
for _ in range(25):
    bad = spanning()
    if not bad:
        break
    move, hits = {}, {}
    for fi, d in bad:
        for k in faces[fi]:
            move[k] = move.get(k, Vector()) + d
            hits[k] = hits.get(k, 0) + 1
    for k in move:
        P[k] = P[k] + 0.8 * move[k] / hits[k]
    avg = [mean_of(P, nbrs[i]) for i in range(count)]
    normals = put(tmesh, P)
    for i in range(count):
        slide = avg[i] - P[i]
        slide -= normals[i] * slide.dot(normals[i])
        P[i] = P[i] + slide * (0.3 * (1.0 - hold[i]))
    for i in live:
        if i not in move:
            hit = target.find_nearest(P[i])
            if hit[3] < 0.01 * tall:
                P[i] = hit[0].copy()
    settle(P, idle, nbrs, 10)
for i in live:  # everything back onto the surface it is now nearest to
    hit = target.find_nearest(P[i])
    if hit[0] is not None:
        P[i] = hit[0].copy()
settle(P, idle, nbrs, 100)
bridges_after = len(spanning())
put(tmesh, P)
for p in tmesh.polygons:
    p.use_smooth = True

# ---- 4. the character's own head: every piece of its body that stands above the collar ----
ring_low = min(P[i].z for i in ring)
ring_high = max(P[i].z for i in ring)
head = copy_of(base, "own head")
bm = bmesh.new()
bm.from_mesh(head.data)
bm.verts.ensure_lookup_table()
neck_floor = (J["chest"].z + J["neck"].z) / 2
kept, head_points = [], set()
for part in loose_parts(bm):
    zs = [v.co.z for v in part]
    if max(zs) > ring_high + 0.01 * tall and min(zs) > neck_floor and max(abs(v.co.x) for v in part) < 0.14 * tall:
        kept.append({"points": len(part), "from": round((min(zs) - floor) / tall, 3), "to": round((max(zs) - floor) / tall, 3)})
        head_points.update(v.index for v in part)
if not head_points:
    bm.free()
    raise ValueError("no piece of the body stands above the collar (at %.0f%% of the height): is there a head?" % (100 * (ring_high - floor) / tall))
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in head_points], context="VERTS")
head_low = min(v.co.z for v in bm.verts)
# Below the collar the neck piece and the template are the same surface (the template was drawn onto it), and two
# skins in one place flicker through each other. The neck is tucked inside: not at all just under the collar, so no gap
# opens there when the head bends away, and by `tuck` from a little way further down.
wrapped = tree_of(template)
tuck, tucked = 0.004 * tall, 0
for v in bm.verts:
    if v.co.z < ring_low:
        hit = wrapped.find_nearest(v.co)
        deep = tuck * min(1.0, max(0.0, (ring_low - v.co.z) / (0.01 * tall) - 0.5))
        if hit[0] is not None and (v.co - hit[0]).dot(hit[1]) > -deep and hit[3] < 3 * tuck:
            v.co = hit[0] - hit[1] * deep
            tucked += 1
bm.to_mesh(head.data)
bm.free()
head_tree = tree_of(head)
ring_to_head = sorted(head_tree.find_nearest(P[i])[3] for i in ring)
collar = {"ring_points": len(ring), "ring_at": [round((ring_low - floor) / tall, 3), round((ring_high - floor) / tall, 3)],
          "head_reaches_down_to": round((head_low - floor) / tall, 3), "head_below_ring_cm": round(100 * (ring_low - head_low), 1),
          "ring_to_head_cm": {"median": round(100 * ring_to_head[len(ring_to_head) // 2], 2), "worst": round(100 * ring_to_head[-1], 2)},
          "ring_to_body_cm_worst": round(100 * max(target.find_nearest(P[i])[3] for i in ring), 2),
          "head_pieces": len(kept), "head_triangles": sum(len(p.vertices) - 2 for p in head.data.polygons),
          "neck_points_tucked_inside": tucked}

# ---- how close is it? ----
to_body = [base_tree.find_nearest(P[i])[3] for i in range(count) if hold[i] < 0.5]
back = []
for v in base.data.vertices:  # the base body's own points that show from outside, below the head
    if v.index in head_points:
        continue
    n = v.normal
    if base_tree.ray_cast(v.co + n * 2e-3, n, 2.0)[0] is not None and base_tree.ray_cast(v.co - n * 2e-3, -n, 2.0)[0] is not None:
        continue
    back.append(wrapped.find_nearest(v.co)[3])
bm = bmesh.new()
bm.from_mesh(tmesh)
folded = sum(1 for e in bm.edges if len(e.link_faces) == 2 and e.link_faces[0].normal.dot(e.link_faces[1].normal) < -0.2)
surface = sum(f.calc_area() for f in bm.faces)
bm.free()

# ---- one body: the template from the collar down, the character's own head ----
skin = bpy.data.materials.new("painted: " + template_name)
skin.use_nodes = True
skin["template"] = template_name  # the mark rig.py and paint.py know the template's faces by; it travels in a .glb
tmesh.materials.clear()
tmesh.materials.append(skin)
for key in ("template_faces", "template_regions", "template_canon", "template_cut", "template_region_names", "license"):
    if key in template:
        del template[key]
for group in list(template.vertex_groups):  # rig.py reads the weights from the template's own file, by where each point is in the layout
    template.vertex_groups.remove(group)
template_points, template_faces = len(tmesh.vertices), len(tmesh.polygons)
template_triangles = sum(len(p.vertices) - 2 for p in tmesh.polygons)
body = join([template, head], PARAMS["name"])
for key, value in keep_tags.items():
    body[key] = value
body["template"] = template_name
body["template_fit"] = json.dumps({"height": round(tall, 4), "floor": round(floor, 4), "collar": collar["ring_at"],
                                   "joints": {k: [round(c, 4) for c in v] for k, v in J.items()}})
old = [o.name for o in bodies]
for o in bodies:
    spare = o.data
    bpy.data.objects.remove(o, do_unlink=True)
    if spare.users == 0:
        bpy.data.meshes.remove(spare)
spare = shell.data
bpy.data.objects.remove(shell, do_unlink=True)
bpy.data.meshes.remove(spare)
body.name = body.data.name = PARAMS["name"]
base.hide_set(True)
base.hide_render = True

print("RESULT " + json.dumps({
    "object": body.name, "template": template_name, "base_body": base.name, "replaced": old,
    "height": round(tall, 3), "points": template_points, "faces": template_faces,
    "triangles": {"template": template_triangles, "own_head": collar["head_triangles"], "body": sum(len(p.vertices) - 2 for p in body.data.polygons)},
    "to_body_pct": stats(to_body, tall), "body_to_template_pct": stats(back, tall), "body_points_that_show": len(back),
    "folded_edges": folded, "faces_spanning_a_hollow": [bridges_before, bridges_after], "points_that_ride_along": sum(1 for x in passive if x),
    "hands_kept": bool(PARAMS["keep_hands"]), "surface_m2": round(surface, 3), "collar": collar, "head_pieces": kept, "fit": fit,
}))
