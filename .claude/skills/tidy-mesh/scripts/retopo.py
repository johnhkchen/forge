# Rebuild a mesh as clean quads, the way a modeler would lay it out.
#
# TRELLIS.2 builds its surface from voxels: an even soup of ~300k triangles
# with no edge loops. This makes a "<name> (quads)" copy instead: each
# separate part (body, handle, lid...) is made watertight with a voxel
# remesh, then rebuilt with QuadriFlow, whose quads follow the surface's
# curvature and sharp edges. Parts get quads in proportion to their area.
#
# The new mesh has no UVs or texture yet. Follow with bake.py (mode "onto")
# to bake the original's color, materials and fine detail onto it.
#
# Heavy: a few seconds to a minute or so per part. Prefer running it in a
# background Blender (see SKILL.md) over the live session, which it freezes.
#
# Safe-mode compatible: bpy, bmesh, mathutils, math and json only.

PARAMS = {
    "object": None,          # mesh object name; None = the largest visible mesh
    "target_quads": 8000,    # total quads across all parts
    "min_part_quads": 150,   # no part gets fewer than this
    "speck_share": 0.002,    # parts under this share of the area are dropped
    "detail": 220,           # voxel resolution across each part's longest side;
                             # higher keeps thin walls (spout lips, rims) intact
    "preserve_sharp": True,
}

import bpy
import bmesh
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


def select_only(objs, active):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def area(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    a = sum(f.calc_area() for f in bm.faces)
    bm.free()
    return a


def close_tears(obj):
    """QuadriFlow can tear thin spots. Fill what it opened (its input was
    watertight, so every open edge is a tear) and report how many there were."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    edges = [e for e in bm.edges if e.is_boundary]
    if edges:
        bmesh.ops.holes_fill(bm, edges=edges, sides=0)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
    bm.free()
    return len(edges)


def quads(obj):
    return sum(1 for p in obj.data.polygons if len(p.vertices) == 4)


source = pick_object(PARAMS["object"])

# Work on a copy; the original stays as the bake source.
work = source.copy()
work.data = source.data.copy()
work.name = source.name + " (quads)"
for c in source.users_collection:
    c.objects.link(work)
work.modifiers.clear()
work.data.materials.clear()
select_only([work], work)
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

# One object per separate part.
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.remove_doubles(threshold=max(work.dimensions) * 1e-6)
bpy.ops.mesh.separate(type="LOOSE")
bpy.ops.object.mode_set(mode="OBJECT")
parts = list(bpy.context.selected_objects)

areas = {p.name: area(p) for p in parts}
total_area = sum(areas.values()) or 1.0
kept, dropped, failed = [], [], []
tears = {}
for part in parts:
    share = areas[part.name] / total_area
    if share < PARAMS["speck_share"]:
        dropped.append(part.name)
        bpy.data.objects.remove(part, do_unlink=True)
        continue
    budget = max(PARAMS["min_part_quads"], int(PARAMS["target_quads"] * share))
    select_only([part], part)
    # Watertight first: QuadriFlow refuses non-manifold input.
    part.data.remesh_voxel_size = max(part.dimensions) / PARAMS["detail"]
    part.data.use_remesh_fix_poles = True
    bpy.ops.object.voxel_remesh()
    try:
        bpy.ops.object.quadriflow_remesh(
            mode="FACES", target_faces=budget, use_preserve_sharp=PARAMS.get("preserve_sharp", True),
            use_preserve_boundary=True, use_mesh_symmetry=False, seed=0,
        )
    except RuntimeError as err:
        failed.append({"part": part.name, "error": str(err)[:200]})
    tears[part.name] = close_tears(part)
    kept.append(part)

if not kept:
    raise ValueError("no parts left to retopologize")
select_only(kept, kept[0])
bpy.ops.object.join()
result = bpy.context.view_layer.objects.active
result.name = source.name + " (quads)"
# Snap the new surface back onto the original, as in hand retopology: the
# voxel and QuadriFlow passes both drift a little from the true shape.
wrap = result.modifiers.new("Shrinkwrap", "SHRINKWRAP")
wrap.target = source
wrap.wrap_method = "NEAREST_SURFACEPOINT"
bpy.ops.object.modifier_apply(modifier=wrap.name)
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))
source.hide_set(True)
source.hide_render = True

print("RESULT " + json.dumps({
    "object": result.name,
    "faces": len(result.data.polygons),
    "quads": quads(result),
    "triangles": sum(len(p.vertices) - 2 for p in result.data.polygons),
    "parts": len(kept),
    "dropped_specks": len(dropped),
    "failed": failed,
    "tears_closed": sum(tears.values()),
}))
