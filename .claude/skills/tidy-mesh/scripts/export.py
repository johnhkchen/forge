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
# A block-out with gear or sockets (build.py) goes out in pieces, so a game
# can take gear off or swap it: one mesh per group, named "body", "gear: wool
# singlet"..., each gear mesh tagged (glTF extras) with its "gear" name,
# "kind" and "slot", plus one empty per attachment point, "socket:
# hand_right"... The first mesh also carries build.py's recipe
# ("forge_build"), which the mid-poly profile rebuilds from. "file" in the
# result lists what was written; "only_this_object" is still the check.
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
    "apart": True,           # a block-out with gear or sockets: one mesh per group and the socket empties
    "check": True,           # read the file back to confirm it holds just this object
}

import bpy
import bmesh
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
        held = {"meshes": len(found), "names": [o.name for o in found][:24],
                "empties": sum(1 for o in scratch.objects if o.type == "EMPTY"),
                "triangles": sum(len(p.vertices) - 2 for o in found for p in o.data.polygons),
                "vertex_colors": any(len(o.data.color_attributes) for o in found)}
    finally:
        window.scene = home
        for kind, old in zip(kinds, before):
            for item in [i for i in kind if i not in old]:
                kind.remove(item)
        bpy.data.scenes.remove(scratch)
    return held


def split_groups(obj, scene):
    """A block-out's groups as objects of their own for the length of the export, named and tagged for the file."""
    made = []
    for index, tag in enumerate(json.loads(obj["forge_groups"])):
        me = obj.data.copy()
        bm = bmesh.new()
        bm.from_mesh(me)
        mark = bm.faces.layers.int.get("forge_group")
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f[mark] != index], context="FACES")
        bm.faces.layers.int.remove(mark)
        bm.to_mesh(me)
        bm.free()
        me.name = tag["name"]
        part = bpy.data.objects.new(tag["name"], me)
        part.matrix_world = obj.matrix_world.copy()
        for key, value in tag.items():
            if key != "name":
                part[key] = value
        scene.collection.objects.link(part)
        made.append(part)
    if made and "forge_build" in obj:
        made[0]["forge_build"] = obj["forge_build"]
    return made


if not PARAMS["path"]:
    raise ValueError("set PARAMS['path'] to where the .glb should go")
obj = pick_object(PARAMS["object"])
scene = bpy.context.scene
if obj.name not in scene.objects:
    raise ValueError("%r is not in the open scene %r; switch to its scene first "
                     "(bpy.context.window.scene = ...)" % (obj.name, scene.name))
sockets = [o for o in scene.objects if o.get("socket_of") == obj.name]
groups = json.loads(obj.get("forge_groups", "[]")) if obj.type == "MESH" else []
parts = split_groups(obj, scene) if PARAMS["apart"] and groups and (len(groups) > 1 or sockets) else []
for o in bpy.context.selected_objects:
    o.select_set(False)
for o in (parts + sockets) if parts else [obj]:
    o.hide_set(False)
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0] if parts else obj
options = {
    "filepath": PARAMS["path"],
    "export_format": "GLB",
    "use_selection": True,
    "use_active_scene": True,  # without this, every scene in the file is written
    "export_apply": True,
    "export_draco_mesh_compression_enable": PARAMS["draco"],
    "export_extras": bool(groups),  # the tags and the recipe travel as custom properties
}
if PARAMS["materials"]:
    options["export_image_format"] = PARAMS["image_format"]
else:
    options["export_materials"] = "NONE"
    if "export_vertex_color" in bpy.ops.export_scene.gltf.get_rna_type().properties.keys():
        options["export_vertex_color"] = "ACTIVE"
try:
    bpy.ops.export_scene.gltf(**options)
finally:
    for o in parts:
        spare = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.meshes.remove(spare)
    for o in sockets + [obj]:
        o.select_set(False)

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
        result["only_this_object"] = (held["meshes"] == max(len(parts), 1) and held["triangles"] == triangles
                                      and held["empties"] == (len(sockets) if parts else 0))
if parts:
    result["groups"] = [g["name"] for g in groups]
    result["sockets"] = [o["socket"] for o in sockets]
print("RESULT " + json.dumps(result))
