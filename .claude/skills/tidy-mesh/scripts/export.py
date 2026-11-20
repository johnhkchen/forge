# Export one object as a GLB, with modifiers applied, and nothing else.
#
# Blender's glTF exporter writes every scene in the file unless told
# otherwise, so "selected only" still drags in meshes from other scenes.
# This exports the open scene only, then reads the file back and counts what
# is in it ("file" in the result; "only_this_object" should be true).
#
# glTF carries plain textures and plain values only. If the material uses
# color ramps, mixes or other nodes, run bake.py (mode "materials") first,
# or the GLB silently loses those changes.
#
# Send this whole file through the blender MCP `execute_blender_code` tool
# after editing PARAMS. Prints RESULT {json}. About a second.
# Safe-mode compatible.

PARAMS = {
    "object": None,          # object to export; None = the largest visible mesh
    "path": None,            # absolute path of the .glb to write (required)
    "materials": True,       # False = shape and vertex colors only (a low-poly block-out)
    "image_format": "AUTO",  # "AUTO" (PNG/JPEG as given), "JPEG" or "WEBP" (smallest)
    "draco": False,          # Draco-compress the mesh (web viewers need a Draco decoder)
    "check": True,           # read the file back to confirm it holds just this object
}

import bpy
import json


def face_count(obj):
    return len(obj.data.polygons)

def pick_object(name):
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise ValueError("no object named %r" % name)
        return obj
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get()]
    if not meshes:
        raise ValueError("the scene has no visible mesh objects")
    return max(meshes, key=face_count)

def read_back(path):
    """What the written file holds, by importing it into a throwaway scene."""
    window = bpy.context.window
    if not window:
        return None
    kinds = (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.collections)
    before = [set(kind) for kind in kinds]
    home = window.scene
    scratch = bpy.data.scenes.new("export check")
    window.scene = scratch
    try:
        bpy.ops.import_scene.gltf(filepath=path)
        found = [o for o in scratch.objects if o.type == "MESH"]
        held = {"meshes": len(found), "names": [o.name for o in found][:8],
                "triangles": sum(len(p.vertices) - 2 for o in found for p in o.data.polygons),
                "vertex_colors": any(len(o.data.color_attributes) for o in found)}
    finally:
        window.scene = home
        for kind, old in zip(kinds, before):
            for item in [i for i in kind if i not in old]:
                kind.remove(item)
        bpy.data.scenes.remove(scratch)
    return held


if not PARAMS["path"]:
    raise ValueError("set PARAMS['path'] to where the .glb should go")
obj = pick_object(PARAMS["object"])
scene = bpy.context.scene
if obj.name not in scene.objects:
    raise ValueError("%r is not in the open scene %r; switch to its scene first "
                     "(bpy.context.window.scene = ...)" % (obj.name, scene.name))
for o in bpy.context.selected_objects:
    o.select_set(False)
obj.hide_set(False)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
options = {
    "filepath": PARAMS["path"],
    "export_format": "GLB",
    "use_selection": True,
    "use_active_scene": True,  # without this, every scene in the file is written
    "export_apply": True,
    "export_draco_mesh_compression_enable": PARAMS["draco"],
}
if PARAMS["materials"]:
    options["export_image_format"] = PARAMS["image_format"]
else:
    options["export_materials"] = "NONE"
    if "export_vertex_color" in bpy.ops.export_scene.gltf.get_rna_type().properties.keys():
        options["export_vertex_color"] = "ACTIVE"
bpy.ops.export_scene.gltf(**options)
obj.select_set(False)

deps = bpy.context.evaluated_depsgraph_get()
shown = obj.evaluated_get(deps)
triangles = sum(len(p.vertices) - 2 for p in shown.to_mesh().polygons)
shown.to_mesh_clear()
result = {
    "object": obj.name,
    "path": PARAMS["path"],
    "faces": len(obj.data.polygons),
    "triangles": triangles,
}
if PARAMS["check"]:
    held = read_back(PARAMS["path"])
    if held:
        result["file"] = held
        result["only_this_object"] = held["meshes"] == 1 and held["triangles"] == triangles
print("RESULT " + json.dumps(result))
