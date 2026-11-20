# Fix the mess TRELLIS.2 leaves in a mesh, keeping its UVs and textures.
#
# Send this whole file through the blender MCP `execute_blender_code` tool.
# Edit PARAMS first. It prints one line: RESULT {json} with before/after counts.
#
# Safe-mode compatible: bpy, bmesh, mathutils, math and json only.

PARAMS = {
    "object": None,            # mesh object name; None = the largest mesh in the scene
    # A separate piece is a speck (and deleted) only if it is BOTH this small a
    # share of all faces AND this small next to the whole object. Real parts
    # like a handle or a lid knob fail the second test and are kept.
    "speck_face_share": 0.002,
    "speck_size_share": 0.05,
    "fill_holes_up_to": 12,    # close open holes with at most this many edges; 0 = never
    "smooth_iterations": 0,    # light Laplacian smoothing against voxel ripples; 0 = off
    "sharp_angle": 30.0,       # shade smooth, but keep edges sharper than this crisp
}

import bpy
import bmesh
import json
import math
from mathutils import Vector



def face_count(obj):
    return len(obj.data.polygons)

def pick_object(name):
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise ValueError("no mesh object named %r" % name)
        return obj
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise ValueError("the scene has no mesh objects")
    return max(meshes, key=face_count)


def islands(bm):
    seen = set()
    pieces = []
    for start in bm.faces:
        if start.index in seen:
            continue
        stack = [start]
        seen.add(start.index)
        piece = []
        while stack:
            f = stack.pop()
            piece.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
        pieces.append(piece)
    pieces.sort(key=len, reverse=True)
    return pieces


def extent(verts):
    lo = Vector([min(v.co[i] for v in verts) for i in range(3)])
    hi = Vector([max(v.co[i] for v in verts) for i in range(3)])
    return (hi - lo).length


def counts(bm):
    return {
        "triangles": sum(len(f.verts) - 2 for f in bm.faces),
        "vertices": len(bm.verts),
        "non_manifold_edges": sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary),
        "boundary_edges": sum(1 for e in bm.edges if e.is_boundary),
    }


obj = pick_object(PARAMS["object"])
me = obj.data
bm = bmesh.new()
bm.from_mesh(me)
before = counts(bm)
size = extent(bm.verts)
done = []

# 1. Weld. glTF splits vertices along every UV seam; Blender keeps UVs per
#    face corner, so welding joins the surface without touching the texture.
n = len(bm.verts)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=size * 1e-6)
done.append("welded %d seam-split vertices" % (n - len(bm.verts)))

# 2. Remove degenerate faces and loose bits.
bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=size * 1e-6)
loose = [v for v in bm.verts if not v.link_faces]
bmesh.ops.delete(bm, geom=loose, context="VERTS")
wires = [e for e in bm.edges if not e.link_faces]
bmesh.ops.delete(bm, geom=wires, context="EDGES")
if loose or wires:
    done.append("deleted %d loose vertices and %d wire edges" % (len(loose), len(wires)))

# 3. Delete specks: tiny floating pieces, never real parts.
bm.faces.ensure_lookup_table()
bm.faces.index_update()
pieces = islands(bm)
total = max(len(bm.faces), 1)
specks = [
    p for p in pieces[1:]
    if len(p) / total < PARAMS["speck_face_share"]
    and extent({v for f in p for v in f.verts}) < size * PARAMS["speck_size_share"]
]
if specks:
    bmesh.ops.delete(bm, geom=[f for p in specks for f in p], context="FACES")
    stray = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=stray, context="VERTS")
    done.append("deleted %d floating specks, kept %d pieces" % (len(specks), len(pieces) - len(specks)))

# 4. Close small holes. The new faces get no texture of their own, so only
#    small ones; big openings are usually real (a mug's mouth).
if PARAMS["fill_holes_up_to"] > 0:
    boundary = [e for e in bm.edges if e.is_boundary]
    filled = bmesh.ops.holes_fill(bm, edges=boundary, sides=PARAMS["fill_holes_up_to"])
    if filled["faces"]:
        bmesh.ops.triangulate(bm, faces=filled["faces"])
        done.append("closed small holes with %d faces" % len(filled["faces"]))

# 5. Optional smoothing of voxel ripples, holding volume and open borders.
if PARAMS["smooth_iterations"] > 0:
    inner = [v for v in bm.verts if not v.is_boundary]
    for _ in range(PARAMS["smooth_iterations"]):
        bmesh.ops.smooth_laplacian_vert(
            bm, verts=inner, lambda_factor=0.3, lambda_border=0.0,
            use_x=True, use_y=True, use_z=True, preserve_volume=True,
        )
    done.append("smoothed %d passes" % PARAMS["smooth_iterations"])

# 6. Tidy what the steps above left behind, then point all normals out.
bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=size * 1e-6)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
after = counts(bm)
bm.to_mesh(me)
bm.free()
me.update()

# 7. Shading: smooth, with crisp edges beyond the sharp angle. This writes
#    sharp edges into the mesh itself (no modifier), so glTF export keeps it.
for o in bpy.context.selected_objects:
    o.select_set(False)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(PARAMS["sharp_angle"]))
done.append("shaded smooth, sharp above %g degrees" % PARAMS["sharp_angle"])

print("RESULT " + json.dumps({"object": obj.name, "before": before, "after": after, "done": done}))
