# Line up a run's raw mesh and its profiles side by side in the live Blender,
# in a new scene called "Profiles" (the scene already open is left alone).
# Each gets a label with its quad or triangle count; the viewport switches to
# material preview with the wireframe on, framed on the row.
#
# Send this whole file through the blender MCP `execute_blender_code` tool
# after editing PARAMS. A second or two. Safe-mode compatible.

PARAMS = {
    "run": None,  # absolute path of the run folder (required)
    "profiles": ["hero", "quads", "web", "game", "mobile"],
    "include_raw": True,  # put the raw TRELLIS.2 mesh first, for comparison
}

import bpy
import json
import math
from mathutils import Euler, Vector

def face_count(obj):
    return len(obj.data.polygons)

if not PARAMS["run"]:
    raise ValueError("set PARAMS['run'] to the run folder's absolute path")
run = PARAMS["run"]
entries = [("raw TRELLIS.2", run + "/mesh.glb")] if PARAMS["include_raw"] else []
entries += [(p, "%s/profiles/%s.glb" % (run, p)) for p in PARAMS["profiles"]]

scene = bpy.data.scenes.get("Profiles") or bpy.data.scenes.new("Profiles")
for o in list(scene.objects):
    bpy.data.objects.remove(o, do_unlink=True)
window = bpy.context.window
if window:
    window.scene = scene

label_mat = bpy.data.materials.get("label white") or bpy.data.materials.new("label white")
label_mat.use_nodes = True
bsdf = label_mat.node_tree.nodes.get("Principled BSDF")
bsdf.inputs["Base Color"].default_value = (0.95, 0.95, 0.95, 1)
bsdf.inputs["Emission Color"].default_value = (1, 1, 1, 1)
bsdf.inputs["Emission Strength"].default_value = 0.6

lined = []
for label, path in entries:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    obj = max((o for o in new if o.type == "MESH"), key=face_count)
    for o in new:
        if o is not obj:
            bpy.data.objects.remove(o, do_unlink=True)
    obj.name = label
    obj.parent = None
    if label != "raw TRELLIS.2" and label != "hero":
        # glTF stores only triangles; pair them back into the quads they were.
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.tris_convert_to_quads(face_threshold=math.radians(40), shape_threshold=math.radians(40), uvs=True)
        bpy.ops.object.mode_set(mode="OBJECT")
    lined.append(obj)

bpy.context.view_layer.update()
sized = [o for o in lined if o.name != "raw TRELLIS.2"] or lined
size = max(sized[0].dimensions)
x = 0.0
counts = []
for obj in lined:
    obj.scale = obj.scale * (size / max(obj.dimensions))
    bpy.context.view_layer.update()
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector([min(c[i] for c in corners) for i in range(3)])
    hi = Vector([max(c[i] for c in corners) for i in range(3)])
    obj.location += Vector((x - lo.x, -(lo.y + hi.y) / 2, -lo.z))
    faces = len(obj.data.polygons)
    quads = sum(1 for p in obj.data.polygons if len(p.vertices) == 4)
    count = "%s quads" % format(quads, ",") if quads > faces * 0.8 else "%s triangles" % format(
        sum(len(p.vertices) - 2 for p in obj.data.polygons), ",")
    counts.append([obj.name, count])
    text = bpy.data.objects.new(obj.name + " label", bpy.data.curves.new(obj.name + " label", "FONT"))
    text.data.body = "%s\n%s" % (obj.name, count)
    text.data.size = size * 0.17
    text.data.align_x = "CENTER"
    text.data.materials.append(label_mat)
    scene.collection.objects.link(text)
    text.location = (x + (hi.x - lo.x) / 2, -size * 0.7, -size * 0.3)
    text.rotation_euler = (math.radians(75), 0, 0)
    x += (hi.x - lo.x) + size * 0.5

for o in bpy.context.view_layer.objects:
    o.select_set(False)
bpy.context.view_layer.objects.active = None
width = x - size * 0.5
for area in (window.screen.areas if window else []):
    if area.type == "VIEW_3D":
        space = area.spaces.active
        space.shading.type = "MATERIAL"
        space.overlay.show_wireframes = True
        space.overlay.wireframe_threshold = 1.0
        view = space.region_3d
        view.view_perspective = "PERSP"
        view.view_location = (width / 2, 0, size / 2)
        view.view_rotation = Euler((math.radians(75), 0, 0)).to_quaternion()
        view.view_distance = width * 0.95

print("RESULT " + json.dumps({"scene": scene.name, "lined_up": counts}))
