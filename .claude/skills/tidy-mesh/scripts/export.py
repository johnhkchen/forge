# Export one object as a GLB, with modifiers applied.
#
# Send this whole file through the blender MCP `execute_blender_code` tool
# after editing PARAMS. Prints RESULT {json}.
#
# glTF carries plain textures and plain values only. If the material uses
# color ramps, mixes or other nodes, run bake.py (mode "materials") first,
# or the GLB silently loses those changes.
#
# Safe-mode compatible: bpy, bmesh, mathutils, math and json only.

PARAMS = {
    "object": None,         # object to export; None = the largest visible mesh
    "path": None,           # absolute path of the .glb to write (required)
    "image_format": "AUTO", # "AUTO" (PNG/JPEG as given), "JPEG" or "WEBP" (smallest)
    "draco": False,         # Draco-compress the mesh (web viewers need a Draco decoder)
}

import bpy
import json


def pick_object(name):
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise ValueError("no object named %r" % name)
        return obj
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get()]
    if not meshes:
        raise ValueError("the scene has no visible mesh objects")
    return max(meshes, key=lambda o: len(o.data.polygons))


if not PARAMS["path"]:
    raise ValueError("set PARAMS['path'] to where the .glb should go")
obj = pick_object(PARAMS["object"])
for o in bpy.context.selected_objects:
    o.select_set(False)
obj.hide_set(False)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.export_scene.gltf(
    filepath=PARAMS["path"],
    export_format="GLB",
    use_selection=True,
    export_apply=True,
    export_image_format=PARAMS["image_format"],
    export_draco_mesh_compression_enable=PARAMS["draco"],
)
print("RESULT " + json.dumps({
    "object": obj.name,
    "path": PARAMS["path"],
    "faces": len(obj.data.polygons),
    "triangles": sum(len(p.vertices) - 2 for p in obj.data.polygons),
}))
