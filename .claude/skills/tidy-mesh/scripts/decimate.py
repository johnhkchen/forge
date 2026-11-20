# Reduce a mesh to a triangle budget, keeping its UVs and textures.
#
# Run clean.py first. Send this whole file through the blender MCP
# `execute_blender_code` tool after editing PARAMS. Prints RESULT {json}.
#
# Collapse decimation is shape-aware: it keeps faces where the shape changes
# (tips, rims, knobs) and spends few on flat areas, so it holds a silhouette
# far better than evenly sized quads at the same budget (on the kettle at 8k
# triangles: 0.3% worst error vs 2.5% for 4k QuadriFlow quads). It keeps UV
# seams, so the existing texture still fits.
#
# For light versions (web, game, mobile) use as_copy + quadify, then bake.py
# (mode "onto") to bake the full mesh's look and detail onto the copy.
#
# Safe-mode compatible: bpy, bmesh, mathutils, math and json only.

PARAMS = {
    "object": None,           # mesh object name; None = the largest mesh in the scene
    "target_triangles": 100000,
    "keep_original": True,    # keep an untouched hidden copy named "<name> (full)"
    "as_copy": False,         # leave the object alone; reduce a copy named "<name> (light)"
    "quadify": False,         # pair triangles back into quads where they line up
}

import bpy
import json
import math


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
if PARAMS["as_copy"]:
    light = obj.copy()
    light.data = obj.data.copy()
    light.name = obj.name + " (light)"
    for c in obj.users_collection:
        c.objects.link(light)
    obj.hide_set(True)
    obj.hide_render = True
    obj = light
    PARAMS["keep_original"] = False
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
    if PARAMS["quadify"]:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.tris_convert_to_quads(face_threshold=math.radians(40), shape_threshold=math.radians(40), uvs=True)
        bpy.ops.object.mode_set(mode="OBJECT")
        done.append("paired into %d quads + %d triangles" % (
            sum(1 for p in obj.data.polygons if len(p.vertices) == 4),
            sum(1 for p in obj.data.polygons if len(p.vertices) == 3)))
    print("RESULT " + json.dumps({"object": obj.name, "before": before, "after": after, "done": done}))
