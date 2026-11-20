# Rebuild a mesh as clean quads, the way a modeler would lay it out.
#
# TRELLIS.2 builds its surface from voxels: an even soup of ~300k triangles
# with no edge loops. This makes a "<name> (quads)" copy instead: each
# separate part (body, handle, lid...) is rebuilt with QuadriFlow, whose quads
# follow the surface's curvature and sharp edges. Parts get quads in
# proportion to their area.
#
# QuadriFlow needs a watertight part. Each part is repaired in place first
# (keeps the true shape, e.g. a spout's open mouth); only if QuadriFlow still
# refuses does it fall back to a voxel remesh (watertight but softens thin
# tips), and last to plain reduction. `routes` in the result says which.
#
# Quads are evenly sized, so a thin tip ends up about one quad short. Below
# ~8k quads that shows; use decimate.py (shape-aware) for light versions and
# check either with match.py.
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
    # A part is a speck (and dropped) only if it is BOTH this small a share of
    # the area AND this small next to the whole object, the same rule as
    # clean.py. Small but real parts, like a handle's hinge pivots, are kept.
    "speck_share": 0.002,
    "speck_size_share": 0.05,
    "detail": 450,           # voxel fallback: resolution across the whole object;
                             # higher keeps thin walls (spout lips, rims) intact
    "preserve_sharp": True,
}

import bpy
import bmesh
import json
import math



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


def repair(obj):
    """Make a part watertight without remeshing it: cut out the faces around
    bad edges and bad vertices, fill the holes, point normals outward."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    size = max(obj.dimensions)
    for _ in range(4):
        # QuadriFlow's own test is stricter than "every edge has two faces":
        # the two must also run in opposite directions, which zero-area and
        # duplicate faces break. Remove those first.
        bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=size * 1e-6)
        bm.verts.index_update()
        seen = {}
        twins = []
        for f in bm.faces:
            key = frozenset(v.index for v in f.verts)
            if key in seen:
                twins.extend((f, seen[key]))
            else:
                seen[key] = f
        if twins:
            bmesh.ops.delete(bm, geom=list(set(twins)), context="FACES")
        bad_edges = [e for e in bm.edges if not e.is_manifold]
        bad_verts = [v for v in bm.verts if not v.is_manifold]
        if not bad_edges and not bad_verts:
            break
        faces = {f for e in bad_edges for f in e.link_faces} | {f for v in bad_verts for f in v.link_faces}
        bmesh.ops.delete(bm, geom=list(faces), context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()


def quadriflow(part, budget):
    try:
        outcome = bpy.ops.object.quadriflow_remesh(
            mode="FACES", target_faces=budget, use_preserve_sharp=PARAMS["preserve_sharp"],
            use_preserve_boundary=True, use_mesh_symmetry=False, seed=0,
        )
    except RuntimeError:
        return False
    return "FINISHED" in outcome


def reduce(part, triangles):
    if len(part.data.polygons) <= triangles:
        return
    mod = part.modifiers.new("Decimate", "DECIMATE")
    mod.ratio = triangles / len(part.data.polygons)
    mod.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=mod.name)


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
whole = max(work.dimensions)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.remove_doubles(threshold=max(work.dimensions) * 1e-6)
bpy.ops.mesh.separate(type="LOOSE")
bpy.ops.object.mode_set(mode="OBJECT")
parts = list(bpy.context.selected_objects)

areas = {p.name: area(p) for p in parts}
total_area = sum(areas.values()) or 1.0
kept, dropped = [], []
tears = {}
routes = {}
for part in parts:
    share = areas[part.name] / total_area
    if share < PARAMS["speck_share"] and max(part.dimensions) < whole * PARAMS["speck_size_share"]:
        dropped.append(part.name)
        bpy.data.objects.remove(part, do_unlink=True)
        continue
    budget = max(PARAMS["min_part_quads"], int(PARAMS["target_quads"] * share))
    select_only([part], part)
    original = part.data.copy()
    # 1. The part's own surface, repaired. QuadriFlow is slow on dense
    #    input, so very dense parts are reduced (shape-aware) first.
    repair(part)
    reduce(part, 60000)
    repair(part)
    big = share >= 0.05
    if quadriflow(part, budget):
        routes[part.name] = "surface"
    else:
        # 2. A voxel remesh is always watertight, but softens thin tips and
        #    turns small parts (a hinge pin) into blobs, so big parts only.
        voxel_ok = False
        if big:
            part.data = original.copy()
            part.data.remesh_voxel_size = whole / PARAMS["detail"]
            part.data.use_remesh_fix_poles = True
            bpy.ops.object.voxel_remesh()
            voxel_ok = quadriflow(part, budget)
        if voxel_ok:
            routes[part.name] = "voxel"
        else:
            # 3. Plain reduction, paired into quads where they line up.
            part.data = original.copy()
            reduce(part, budget * 2)
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.mesh.tris_convert_to_quads()
            bpy.ops.object.mode_set(mode="OBJECT")
            routes[part.name] = "reduced"
    tears[part.name] = close_tears(part)
    kept.append(part)

if not kept:
    raise ValueError("no parts left to retopologize")
select_only(kept, kept[0])
bpy.ops.object.join()
result = bpy.context.view_layer.objects.active
result.name = source.name + " (quads)"
# Snap the new surface back onto the original, as in hand retopology:
# QuadriFlow (and the voxel route) drift a little from the true shape.
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
    "routes": sorted(routes.values()),
    "tears_closed": sum(tears.values()),
}))
