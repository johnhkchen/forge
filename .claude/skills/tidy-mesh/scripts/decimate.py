# Reduce a mesh to a triangle budget, keeping its UVs and textures.
#
# Run clean.py first. Send this whole file through the blender MCP
# `execute_blender_code` tool after editing PARAMS. Prints RESULT {json}.
#
# Collapse decimation in Blender keeps UV seams, so the existing texture still
# fits. It is the right tool down to ~50k triangles for an object like this.
# Much lower than that, details start to melt; use bake.py with a low target
# instead, which also bakes a normal map to bring the detail back.
#
# Safe-mode compatible: bpy, bmesh, mathutils, math and json only.

PARAMS = {
    "object": None,           # mesh object name; None = the largest mesh in the scene
    "target_triangles": 100000,
    "keep_original": True,    # keep an untouched hidden copy named "<name> (full)"
}

import bpy
import json


def pick_object(name):
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise ValueError("no mesh object named %r" % name)
        return obj
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get()]
    if not meshes:
        raise ValueError("the scene has no visible mesh objects")
    return max(meshes, key=lambda o: len(o.data.polygons))


def triangles(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


obj = pick_object(PARAMS["object"])
before = triangles(obj)
target = PARAMS["target_triangles"]
if before <= target:
    print("RESULT " + json.dumps({"object": obj.name, "before": before, "after": before, "done": ["already under budget"]}))
else:
    done = []
    if PARAMS["keep_original"]:
        full = obj.copy()
        full.data = obj.data.copy()
        full.name = obj.name + " (full)"
        for c in obj.users_collection:
            c.objects.link(full)
        full.hide_set(True)
        full.hide_render = True
        done.append("kept the original as %r (hidden)" % full.name)

    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    mod = obj.modifiers.new("Decimate", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = target / before
    mod.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=mod.name)
    after = triangles(obj)
    done.append("decimated %d -> %d triangles" % (before, after))
    print("RESULT " + json.dumps({"object": obj.name, "before": before, "after": after, "done": done}))
