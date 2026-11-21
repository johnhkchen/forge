# Move other meshes of the same object to where its finished mesh now stands.
#
# Finishing turns, sizes and stands the raw mesh (stand.py). A character's
# base body and the clothes cut for it (garment.py) were made beside the raw
# mesh, so they must make exactly the same move, or they no longer fit. This
# finds that move and applies it to each file in "follow".
#
# The move comes from, in this order:
#   - "placed": 16 numbers, a 4x4 matrix row by row, if you give it;
#   - what stand.py wrote on the finished object ("forge_placed": every turn,
#     scale and shift it made, multiplied up);
#   - failing both (a scene from before stand.py kept it, or work done by
#     hand), a fit: the raw mesh is tried in each of the 24 upright and
#     sideways turns, sized and centered to the finished one, and the turn
#     that lands closest wins. A turn that isn't a quarter turn can't be
#     found this way.
# Whichever it was, the raw mesh ("raw") is then moved and measured against
# the finished object: "check" says how far apart they are, as a share of the
# height. Over "limit" nothing is written and "ok" is false.
#
# Open the run's scene.blend (or final.glb) first; run it in a background
# Blender (scripts/tidy_headless.py). Prints RESULT {json}. A few seconds.
# Safe-mode compatible.

PARAMS = {
    "object": None,  # the finished object; None = the largest visible mesh
    "raw": None,     # the raw mesh it was made from, .glb (required): the move is checked on it
    "follow": [],    # [{"from": "/abs/base/body.glb", "to": "/abs/base/final.glb"}, ...]
    "placed": None,  # the move, as 16 numbers; None = read it from the object, else fit it
    "image_format": "AUTO",  # "AUTO" keeps each file's pictures as they came; "WEBP" makes them smaller
    "limit": 0.5,    # stop if the moved raw mesh is typically farther than this from the finished one (% of height)
}

import bpy
import bmesh
import json
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


def face_count(obj):
    return len(obj.data.polygons)

def pick_object(name):
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise ValueError("no mesh object named %r" % name)
        return obj
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get()]
    if not meshes:
        raise ValueError("the scene has no visible mesh objects")
    return max(meshes, key=face_count)

def bring(path, name):
    """A .glb as one object, its points where the file put them."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new_names = [o.name for o in bpy.data.objects if o not in before]
    meshes = [bpy.data.objects[n] for n in new_names if bpy.data.objects[n].type == "MESH"]
    if not meshes:
        raise ValueError("no mesh in %s" % path)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    world = obj.matrix_world.copy()
    obj.parent = None
    obj.data.transform(world)
    obj.matrix_world = Matrix.Identity(4)
    for n in new_names:
        o = bpy.data.objects.get(n)
        if o and o != obj:
            bpy.data.objects.remove(o, do_unlink=True)
    obj.name = name
    obj.select_set(False)
    return obj

def box_of(points):
    low = Vector([min(p[i] for p in points) for i in range(3)])
    high = Vector([max(p[i] for p in points) for i in range(3)])
    return low, high

def spot(values, share):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))] if ordered else 0.0

def apart(points, move, tree):
    """How far the moved points land from the finished surface: middle and nine-in-ten."""
    far = []
    for p in points:
        hit = tree.find_nearest(move @ p)
        if hit[0] is not None:
            far.append(hit[3])
    return spot(far, 0.5), spot(far, 0.9)

def mean_apart(points, move, tree):
    """The average distance instead: a nose or a pair of feet on the wrong side counts, where a middle value would miss them."""
    total, count = 0.0, 0
    for p in points:
        hit = tree.find_nearest(move @ p)
        if hit[0] is not None:
            total += hit[3]
            count += 1
    return total / max(1, count)

def quarter_turns():
    """The 24 ways to turn a box onto itself."""
    axes = [Vector((1, 0, 0)), Vector((-1, 0, 0)), Vector((0, 1, 0)), Vector((0, -1, 0)), Vector((0, 0, 1)), Vector((0, 0, -1))]
    turns = []
    for x in axes:
        for y in axes:
            if abs(x.dot(y)) > 0.5:
                continue
            z = x.cross(y)
            turns.append(Matrix(((x[0], y[0], z[0], 0), (x[1], y[1], z[1], 0), (x[2], y[2], z[2], 0), (0, 0, 0, 1))))
    return turns

def fit_move(points, final_low, final_high, tree):
    """The quarter turn, size and shift that best carry the raw points onto the finished mesh."""
    best, best_off = None, 1e9
    final_size = final_high - final_low
    for turn in quarter_turns():
        low, high = box_of([turn @ p for p in points])
        size = high - low
        scale = max(final_size) / max(max(size), 1e-9)
        shift = (final_low + final_high) / 2 - scale * (low + high) / 2
        move = Matrix.Translation(shift) @ Matrix.Scale(scale, 4) @ turn
        off = mean_apart(points[::7], move, tree)
        if off < best_off:
            best, best_off = move, off
    return best


final = pick_object(PARAMS["object"])
if not PARAMS["raw"]:
    raise ValueError("set PARAMS['raw'] to the raw mesh's .glb")
bm = bmesh.new()
bm.from_mesh(final.data)
bm.transform(final.matrix_world)
tree = BVHTree.FromBMesh(bm)
final_low, final_high = box_of([v.co for v in bm.verts])
bm.free()
height = final_high[2] - final_low[2]

raw = bring(PARAMS["raw"], "follow: raw")
stride = max(1, len(raw.data.vertices) // 4000)
points = [raw.data.vertices[i].co.copy() for i in range(0, len(raw.data.vertices), stride)]
bpy.data.objects.remove(raw, do_unlink=True)

kept = final.get("forge_placed")
if PARAMS["placed"]:
    source = "given"
    flat = list(PARAMS["placed"])
elif kept is not None and len(kept) == 16:
    source = "kept by stand.py"
    flat = list(kept)
else:
    source = "fitted"
    flat = None
if flat is None:
    move = fit_move(points, final_low, final_high, tree)
else:
    move = Matrix([flat[0:4], flat[4:8], flat[8:12], flat[12:16]])
typical, most = apart(points, move, tree)
check = {"typical_pct": round(100.0 * typical / height, 3), "nine_in_ten_within_pct": round(100.0 * most / height, 3)}
ok = check["typical_pct"] <= PARAMS["limit"]
if not ok and source == "kept by stand.py":
    # the object was moved again after stand.py, by hand: fall back to the fit
    refit = fit_move(points, final_low, final_high, tree)
    typical, most = apart(points, refit, tree)
    if 100.0 * typical / height <= PARAMS["limit"]:
        move, source, ok = refit, "fitted (what stand.py kept no longer matched)", True
        check = {"typical_pct": round(100.0 * typical / height, 3), "nine_in_ten_within_pct": round(100.0 * most / height, 3)}

written = []
if ok:
    for job in PARAMS["follow"]:
        obj = bring(job["from"], "follow: piece")
        obj.data.transform(move)
        obj.data.update()
        low, high = box_of([v.co for v in obj.data.vertices])
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.export_scene.gltf(filepath=job["to"], export_format="GLB", use_selection=True, use_active_scene=True, export_extras=True,
                                  export_image_format=PARAMS["image_format"])
        written.append({"from": job["from"], "to": job["to"], "min": [round(c, 4) for c in low], "max": [round(c, 4) for c in high]})
        bpy.data.objects.remove(obj, do_unlink=True)

print("RESULT " + json.dumps({
    "ok": ok,
    "why": [] if ok else ["moved by %s, the raw mesh still sits %.2f%% of the height off the finished one (limit %s)" % (source, check["typical_pct"], PARAMS["limit"])],
    "object": final.name,
    "move_from": source,
    "placed": [round(move[r][c], 6) for r in range(4) for c in range(4)],
    "scale": round(move.to_scale()[0], 5),
    "check": check,
    "height": round(height, 4),
    "written": written,
}))
