# Bring a .glb in as one named object and say what arrived.
#
# With "scene" set it works in a scene of its own, so nothing else in the
# file is touched: a new one, or the one an earlier open.py made by that
# name (emptied first). If someone else's scene already has the name, Blender
# adds ".001": read "scene" in the result. It never empties a scene it didn't
# make: "empty_first" on someone else's scene opens a fresh "Forge" scene
# instead (see "kept_scene" in the result). Joins the file's meshes into one
# object, drops the empties glTF adds, and keeps it where the file put it.
# "add": True brings a second mesh into a scene that already holds one (a
# character's base body beside its clothed mesh) and removes nothing.
#
# Send this whole file through the blender MCP `execute_blender_code` tool
# after editing PARAMS. Prints RESULT {json}: the object's name, triangles,
# bounds ("min", "max", "size" in meters), materials and textures.
# Under a second. Safe-mode compatible.

PARAMS = {
    "mesh": None,          # absolute path of the .glb (required)
    "scene": None,         # a scene to put it in, like "Parts"; None = the open scene
    "name": "Reference",   # what to call the object
    "empty_first": False,  # with no "scene": empty the open scene first, if open.py made it
    "add": False,          # True = keep what the scene holds and put this beside it
}

import bpy
import json
from mathutils import Vector

if not PARAMS["mesh"]:
    raise ValueError("set PARAMS['mesh'] to the .glb's absolute path")
scene = bpy.context.scene
if PARAMS["scene"]:
    ours = [s for s in bpy.data.scenes if s.get("opened_as") == PARAMS["scene"]]
    scene = ours[0] if ours else bpy.data.scenes.new(PARAMS["scene"])
    scene["opened_as"] = PARAMS["scene"]
    if bpy.context.window:
        bpy.context.window.scene = scene
kept = None
if PARAMS["add"]:
    PARAMS["empty_first"] = False
if PARAMS["empty_first"] and not PARAMS["scene"] and not scene.get("opened_as"):
    # Not ours (the person's own scene, or one this tool didn't make):
    # leave it whole and work in a fresh scene instead.
    kept = scene.name
    scene = bpy.data.scenes.new("Forge")
    scene["opened_as"] = "Forge"
    if bpy.context.window:
        bpy.context.window.scene = scene
removed = 0
if (PARAMS["scene"] or PARAMS["empty_first"]) and not PARAMS["add"]:
    for o in list(scene.objects):
        bpy.data.objects.remove(o, do_unlink=True)
        removed += 1

before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=PARAMS["mesh"])
new = [o for o in bpy.data.objects if o not in before]
new_names = [o.name for o in new]
meshes = [o for o in new if o.type == "MESH"]
if not meshes:
    raise ValueError("no mesh in %s" % PARAMS["mesh"])
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
obj.matrix_world = world
for n in new_names:  # the joined-away meshes are already gone; this drops the empties
    o = bpy.data.objects.get(n)
    if o and o != obj:
        bpy.data.objects.remove(o, do_unlink=True)
obj.name = PARAMS["name"]
obj.select_set(False)

corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
low = [round(min(c[i] for c in corners), 4) for i in range(3)]
high = [round(max(c[i] for c in corners), 4) for i in range(3)]
materials = []
for m in obj.data.materials:
    images = []
    if m and m.node_tree:
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image and n.image.name not in images:
                images.append(n.image.name)
    materials.append({"name": m.name if m else None, "textures": images})

print("RESULT " + json.dumps({
    "object": obj.name,  # may get a .001 suffix if the name is taken in another scene
    "scene": scene.name,
    "removed_first": removed,
    "kept_scene": kept,  # set when the open scene wasn't ours and was left alone
    "joined": len(meshes),
    "triangles": sum(len(p.vertices) - 2 for p in obj.data.polygons),
    "vertices": len(obj.data.vertices),
    "min": low, "max": high,
    "size": [round(high[i] - low[i], 4) for i in range(3)],
    "materials": materials,
    "other_scenes": [s.name for s in bpy.data.scenes if s != scene],
}))
