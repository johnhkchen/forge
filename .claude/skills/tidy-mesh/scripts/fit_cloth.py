# Ease tight clothes out wherever the body comes through them in motion.
#
# Tight cloth has far fewer points than the body under it, so where the body
# bends (a back bending forward, an armpit as the arm goes up, the seat in a
# squat) the skin bulges out between the cloth's points and shows through.
# This finds where, by playing a motion on a rigged copy of the character,
# and moves the cloth's points out there, on the character itself.
#
# Run it with a rigged copy in the scene: the body and each piece of gear as
# meshes of their own, tagged "fit_part" (and "forge" body or gear), each
# carrying a "fit_src" point attribute that says which point of the source
# object (PARAMS "source") it came from; drape.py's notes on the points
# ("forge_fit": 1 tight, 2 loose, 3 stiff, 4 band); the body's faces still
# carrying "forge_under" (0: drawn while dressed); and an action on the rig
# (rom.py's routine is the one meant: it pushes the body further than a walk
# or most shots do).
#
# How:
#   1. Standing still (the meshes as they rest), each body point that stays
#      drawn while dressed, and three spots along each of its edges, looks
#      straight out. If tight cloth is there (within 3% of the height, facing
#      the same way), the spot on the cloth it would come out through is kept:
#      which three cloth points, and how much of each.
#   2. Every few frames of the action, each kept body spot is compared with
#      its cloth spot, as both have moved: how far it is past the cloth, along
#      the cloth's facing there. Anything closer than the clearance counts.
#   3. Each cloth point gets the most any spot it carries needed, spread to
#      its neighbours on the same piece (halving each step), and no more than
#      a share of the height.
#   4. The source object's matching points move out by that much, along
#      their own facing. Loose cloth (it swings on bones of its own) and
#      stiff gear are never moved.
#
# Prints RESULT {json}: how many spots came through on how many frames, how
# many cloth points moved, and by how much. A few seconds.

PARAMS = {
    "source": None,      # the object to move the cloth of: the draped block-out the rigged copy was made from
    "rig": None,         # the copy's armature; None = the first one in the scene
    "every": 2,          # look at every this many frames of the action
    "clearance": 0.005,  # how far cloth should stay off the body at least, as a share of the height (drape.py's)
    "most": 0.025,       # the most any cloth point moves, as a share of the height
    "spread": 2,         # how many steps out from a point that needed it its neighbours follow (each step half as far)
    "smooth": 3,         # then this many rounds of evening each point's move out with its neighbours' (never below what it needed)
    "one_part": 0.8,     # a cloth point is only moved if this much of its weight is one part of the body (the trunk, an arm, a leg)
    "alike": 0.5,        # a skin spot is only held to the cloth over it if their weights share this much: the same bones move both
}

import bpy
import json
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.interpolate import poly_3d_calc

TIGHT = (1, 4)  # drape.py's forge_fit: tight, band

scene = bpy.context.scene
source = bpy.data.objects[PARAMS["source"]]
rig = bpy.data.objects.get(PARAMS["rig"]) if PARAMS["rig"] else next((o for o in scene.objects if o.type == "ARMATURE"), None)
if rig is None or not rig.animation_data or not rig.animation_data.action:
    raise ValueError("no rig with an action in the scene: rig a copy and play a motion on it first")
parts = [o for o in scene.objects if o.type == "MESH" and o.get("fit_part")]
body = next((o for o in parts if o.get("forge") == "body"), None)
gear = [o for o in parts if o.get("forge") == "gear"]
if body is None or not gear:
    raise ValueError("no body and gear parts tagged fit_part")


def values(obj, name, default=0):
    layer = obj.data.attributes.get(name)
    if layer is None:
        return [default] * len(obj.data.vertices)
    out = [default] * len(layer.data)
    layer.data.foreach_get("value", out)
    return out


world = {o.name: [o.matrix_world @ v.co for v in o.data.vertices] for o in parts}
flesh = world[body.name]
tall = max(p.z for p in flesh) - min(p.z for p in flesh)
reach = 0.03 * tall
clearance = PARAMS["clearance"] * tall

# ---- 1. standing still: which spot on the cloth each drawn body spot would come out through ----
trees, tris = {}, {}
for o in gear:
    fit = values(o, "forge_fit")
    o.data.calc_loop_triangles()
    keep = [tuple(t.vertices) for t in o.data.loop_triangles if all(fit[k] in TIGHT for k in t.vertices)]
    if keep:
        tris[o.name] = keep
        trees[o.name] = BVHTree.FromPolygons(world[o.name], keep)
under = [0] * len(body.data.polygons)
if body.data.attributes.get("forge_under") is not None:
    body.data.attributes["forge_under"].data.foreach_get("value", under)
drawn = set()
for poly in body.data.polygons:
    if under[poly.index] == 0:
        drawn.update(poly.vertices)
turn = body.matrix_world.to_3x3()
normals = [(turn @ v.normal).normalized() for v in body.data.vertices]
spots = []  # (body weights {point: share}, the way out)
for k in sorted(drawn):
    spots.append(({k: 1.0}, normals[k]))
for e in body.data.edges:
    a, b = e.vertices
    if a in drawn and b in drawn:
        facing = normals[a] + normals[b]
        if facing.length > 0.5:
            for t in (0.25, 0.5, 0.75):
                spots.append(({a: 1.0 - t, b: t}, facing.normalized()))
def bone_weights(obj):
    """Each point's skin weights, {bone: share}, from its vertex groups (rig.py and cloth.py name them after bones)."""
    names = {g.index: g.name for g in obj.vertex_groups}
    out = []
    for v in obj.data.vertices:
        row = {names[g.group]: g.weight for g in v.groups if g.group in names and g.weight > 1e-4}
        total = sum(row.values()) or 1.0
        out.append({b: w / total for b, w in row.items()})
    return out


def alike(a, b):
    """How much two points' weights agree, 0 to 1: the share of the same bones moving both."""
    return sum(min(w, b.get(bone, 0.0)) for bone, w in a.items())


def mixed(rows, shares):
    out = {}
    for row, share in zip(rows, shares):
        for bone, w in row.items():
            out[bone] = out.get(bone, 0.0) + w * share
    return out


def family(bone):
    """Which part of the body a bone moves: the trunk, an arm, a leg (a tail, or cloth bones, go with the trunk)."""
    for part in ("arm", "leg"):
        for side in ("_l", "_r"):
            if bone.endswith(side) and bone[:-2] in (("shoulder", "upper_arm", "forearm", "hand") if part == "arm" else ("thigh", "shin", "foot", "toe")):
                return part + side
    return "trunk"


def one_part(row):
    """Is this point moved mostly by one part of the body? Cloth where two meet (an armpit, the crotch) is pulled
    two ways at once, and easing it out doesn't keep skin in."""
    shares = {}
    for bone, w in row.items():
        shares[family(bone)] = shares.get(family(bone), 0.0) + w
    return max(shares.values(), default=0.0) >= PARAMS["one_part"]


skin_bones = bone_weights(body)
cloth_bones = {o.name: bone_weights(o) for o in gear}
settled = {name: [one_part(row) for row in rows] for name, rows in cloth_bones.items()}
kept = []  # (body weights, gear part, its three points, their shares)
passing = 0
for weights, n in spots:
    p = sum((flesh[k] * w for k, w in weights.items()), Vector())
    best = None
    for name, tree in trees.items():
        hit = tree.ray_cast(p + n * 1e-4, n, reach)
        if hit[0] is not None and hit[1].dot(n) > 0.2 and (best is None or hit[3] < best[3]):
            best = (name, hit[0], hit[2], hit[3])
    if best is None:
        continue
    name, at, tri, _ = best
    corners = tris[name][tri]
    shares = poly_3d_calc([world[name][k] for k in corners], at)
    # Only skin the cloth moves with. The underside of an arm held out in a T-pose is over a singlet's side, but
    # the arm swings down past the cloth, not through it: their weights hardly share a bone.
    if alike(mixed([skin_bones[k] for k in weights], list(weights.values())), mixed([cloth_bones[name][k] for k in corners], shares)) < PARAMS["alike"]:
        passing += 1
        continue
    kept.append((weights, name, corners, shares))

# ---- 2. through the action: how far past its cloth spot each body spot goes ----
need = {o.name: {} for o in gear}  # gear part -> {point: how far it must move out}
through, deepest = 0, 0.0
first, last = [int(round(f)) for f in rig.animation_data.action.frame_range]
for frame in range(first, last + 1, max(1, int(PARAMS["every"]))):
    scene.frame_set(frame)
    deps = bpy.context.evaluated_depsgraph_get()
    moved = {}
    for o in parts:
        shown = o.evaluated_get(deps)
        me = shown.to_mesh()
        moved[o.name] = [o.matrix_world @ v.co for v in me.vertices]
        shown.to_mesh_clear()
    skin = moved[body.name]
    for weights, name, corners, shares in kept:
        p = sum((skin[k] * w for k, w in weights.items()), Vector())
        c = [moved[name][k] for k in corners]
        spot = c[0] * shares[0] + c[1] * shares[1] + c[2] * shares[2]
        facing = (c[1] - c[0]).cross(c[2] - c[0])
        if facing.length < 1e-12:
            continue
        facing.normalize()  # a triangle keeps its face's winding, so this points out of the cloth
        past = (p - spot).dot(facing)
        if past > -clearance:
            want = past + clearance
            if past > 0:
                through += 1
                deepest = max(deepest, past)
            for k in corners:
                if not settled[name][k]:
                    continue
                if want > need[name].get(k, 0.0):
                    need[name][k] = want
scene.frame_set(first)

# ---- 3. spread to neighbours on the same piece, and cap ----
most = PARAMS["most"] * tall
for o in gear:
    links = {}
    for e in o.data.edges:
        a, b = e.vertices
        links.setdefault(a, []).append(b)
        links.setdefault(b, []).append(a)
    fit = values(o, "forge_fit")
    grown = dict(need[o.name])
    for _ in range(int(PARAMS["spread"])):
        step = dict(grown)
        for k, d in grown.items():
            for j in links.get(k, []):
                if fit[j] in TIGHT and settled[o.name][j] and d / 2 > step.get(j, 0.0):
                    step[j] = d / 2
        grown = step
    for _ in range(int(PARAMS["smooth"])):  # even it out, so the cloth swells instead of growing spikes
        even = {}
        for k in set(grown) | {j for k in grown for j in links.get(k, [])}:
            if fit[k] not in TIGHT or not settled[o.name][k]:
                continue
            around = [grown.get(j, 0.0) for j in links.get(k, [])]
            even[k] = max(need[o.name].get(k, 0.0) * 0.75, (grown.get(k, 0.0) + sum(around)) / (1 + len(around)))
        grown = even
    # A hem stays where drape.py laid it: a point on the edge of a piece (an armhole, a cuff) doesn't move, so the
    # cloth swells between its edges instead of an edge standing off as a flap.
    faces_of = {}
    for poly in o.data.polygons:
        for i, k in enumerate(poly.vertices):
            pair = (min(k, poly.vertices[i - 1]), max(k, poly.vertices[i - 1]))
            faces_of[pair] = faces_of.get(pair, 0) + 1
    edge = {k for pair, n in faces_of.items() if n == 1 for k in pair}
    for k in list(grown):
        if k in edge:
            grown[k] = 0.0
    need[o.name] = {k: min(d, most) for k, d in grown.items() if d > 1e-5}

# ---- 4. move the source's matching cloth points out ----
# Straight away from the nearest point of the body, not along the cloth's own facing: cloth.py gives each cloth
# point the weights of the body nearest it, and moving along that line keeps the same body point nearest (a point
# by an armpit pushed along its facing could end up nearer the arm, and take the arm's weights).
back = source.matrix_world.inverted()
src_turn = source.matrix_world.to_3x3()
skin_tree = BVHTree.FromPolygons(flesh, [tuple(p.vertices) for p in body.data.polygons])
pushed = []
for o in gear:
    origin = values(o, "fit_src", -1)
    for k, d in need[o.name].items():
        s = origin[k]
        if s < 0:
            continue
        v = source.data.vertices[s]
        at = source.matrix_world @ v.co
        out = (src_turn @ v.normal).normalized()
        near = skin_tree.find_nearest(at)
        if near[0] is not None and near[3] > 1e-4 and (at - near[0]).normalized().dot(out) > 0.2:
            out = (at - near[0]).normalized()
        v.co = back @ (source.matrix_world @ v.co + out * d)
        pushed.append(d)
source.data.update()
pushed.sort()
result = {
    "source": source.name, "spots_watched": len(kept), "spots_moving_apart": passing, "frames_looked_at": len(range(first, last + 1, max(1, int(PARAMS["every"])))),
    "spot_frames_through": through, "deepest_cm": round(100 * deepest, 2),
    "cloth_points_moved": len(pushed), "moved_cm": {"middle": round(100 * pushed[len(pushed) // 2], 2) if pushed else 0.0, "most": round(100 * pushed[-1], 2) if pushed else 0.0},
}
print("RESULT " + json.dumps(result))
