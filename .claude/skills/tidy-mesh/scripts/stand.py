# Stand an imported mesh up the way a finished asset sits: turned to face
# front, at its real size, resting on the floor at the world origin, welded
# and smooth-shaded. Turn, size and origin are applied to the mesh itself, so
# the object ends with no rotation, scale 1 and location 0.
#
# Run it once to fix everything, or again with only "turn" to correct the
# facing after a look (the other steps are safe to repeat).
#
# It keeps the whole move it made on the object ("forge_placed", and "placed"
# in the result: a 4x4 matrix, row by row, multiplied up over every run), so
# anything made beside the raw mesh, like a character's base body, can be
# moved the same way afterwards (follow.py).
#
# Send this whole file through the blender MCP `execute_blender_code` tool
# after editing PARAMS. Prints RESULT {json}. About 3 s on 300k triangles.
# Safe-mode compatible.

PARAMS = {
    "object": None,           # None = the largest visible mesh
    "turn": [0, 0, 0],        # degrees about X, Y, Z; [0, 0, 180] faces it the other way. Front is -Y
    "size": None,             # meters; None = leave the size alone
    "size_of": "largest",     # "largest" side, or "height" (z, for a standing character)
    "on_floor": True,         # origin at the bottom center, object at the world origin, resting on z = 0
    "weld": 0.0001,           # merge vertices closer than this (meters), drop loose bits, normals outward; None = skip
    "smooth_angle": 30,       # smooth shading, edges sharper than this stay sharp; None = skip
    "max_triangles": 400000,  # above this, add a Decimate modifier...
    "decimate_to": 300000,    # ...down to about this many
}

import bpy
import bmesh
import json
import math
from mathutils import Euler, Matrix, Vector


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

def bounds(me):
    low = [min(v.co[i] for v in me.vertices) for i in range(3)]
    high = [max(v.co[i] for v in me.vertices) for i in range(3)]
    return low, high


obj = pick_object(PARAMS["object"])
me = obj.data
did = []
before = obj.get("forge_placed")
placed = Matrix([before[0:4], before[4:8], before[8:12], before[12:16]]) if before is not None and len(before) == 16 else Matrix.Identity(4)

turn = Euler([math.radians(a) for a in PARAMS["turn"]]).to_matrix().to_4x4()
me.transform(turn @ obj.matrix_world)  # bakes in whatever the object carried, plus the turn
placed = turn @ obj.matrix_world @ placed
obj.matrix_world = Matrix.Identity(4)
if any(PARAMS["turn"]):
    did.append("turned %s degrees" % PARAMS["turn"])

low, high = bounds(me)
if PARAMS["size"]:
    now = (high[2] - low[2]) if PARAMS["size_of"] == "height" else max(high[i] - low[i] for i in range(3))
    me.transform(Matrix.Scale(PARAMS["size"] / now, 4))
    placed = Matrix.Scale(PARAMS["size"] / now, 4) @ placed
    did.append("scaled x%.4f so the %s is %s m" % (PARAMS["size"] / now, PARAMS["size_of"], PARAMS["size"]))
    low, high = bounds(me)
if PARAMS["on_floor"]:
    shift = Matrix.Translation(-Vector(((low[0] + high[0]) / 2, (low[1] + high[1]) / 2, low[2])))
    me.transform(shift)
    placed = shift @ placed
    did.append("origin at the bottom center, resting on z = 0")

if PARAMS["weld"]:
    bm = bmesh.new()
    bm.from_mesh(me)
    start = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=PARAMS["weld"])
    welded = start - len(bm.verts)
    loose_edges = [e for e in bm.edges if not e.link_faces]
    bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")
    loose_verts = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    did.append("welded %d vertices, removed %d loose edges and %d loose vertices, normals outward"
               % (welded, len(loose_edges), len(loose_verts)))
me.update()
obj["forge_placed"] = [placed[r][c] for r in range(4) for c in range(4)]

for o in bpy.context.selected_objects:
    o.select_set(False)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
triangles = sum(len(p.vertices) - 2 for p in me.polygons)
if PARAMS["max_triangles"] and triangles > PARAMS["max_triangles"] and not obj.modifiers.get("Decimate"):
    dec = obj.modifiers.new("Decimate", "DECIMATE")
    dec.ratio = PARAMS["decimate_to"] / triangles
    did.append("Decimate modifier to about %d triangles" % PARAMS["decimate_to"])
if PARAMS["smooth_angle"] is not None:
    for old in [m for m in obj.modifiers if m.type == "NODES" and m.name.startswith("Smooth by Angle")]:
        obj.modifiers.remove(old)
    try:
        bpy.ops.object.shade_auto_smooth(use_auto_smooth=True, angle=math.radians(PARAMS["smooth_angle"]))
        did.append("smooth shading with a Smooth by Angle modifier at %s degrees" % PARAMS["smooth_angle"])
    except (RuntimeError, AttributeError, TypeError) as e:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
        did.append("smooth shading only (Smooth by Angle not available: %s)" % e)
obj.select_set(False)

deps = bpy.context.evaluated_depsgraph_get()
shown = obj.evaluated_get(deps)
final_triangles = sum(len(p.vertices) - 2 for p in shown.to_mesh().polygons)
shown.to_mesh_clear()
low, high = bounds(me)
print("RESULT " + json.dumps({
    "object": obj.name,
    "did": did,
    "triangles": final_triangles,
    "vertices": len(me.vertices),
    "min": [round(c, 4) for c in low],
    "max": [round(c, 4) for c in high],
    "size": [round(high[i] - low[i], 4) for i in range(3)],
    "modifiers": [m.name for m in obj.modifiers],
    "uv_layers": len(me.uv_layers),
    "placed": [round(placed[r][c], 6) for r in range(4) for c in range(4)],
}))
