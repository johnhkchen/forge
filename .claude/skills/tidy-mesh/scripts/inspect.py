# Measure what is wrong with a mesh, without changing anything.
#
# Send this whole file through the blender MCP `execute_blender_code` tool.
# Edit PARAMS first. It prints one line: RESULT {json}.
#
# Safe-mode compatible: bpy, bmesh, mathutils, math and json only.

PARAMS = {
    "object": None,  # name of the mesh object; None = the largest mesh in the scene
}

import bpy
import bmesh
import json
import math
from mathutils import Vector


def pick_object(name):
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise ValueError("no mesh object named %r" % name)
        return obj
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise ValueError("the scene has no mesh objects")
    return max(meshes, key=lambda o: len(o.data.polygons))


def islands(bm):
    """Connected pieces of the mesh, as lists of faces, largest first."""
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


def piece_summary(faces, total):
    """Share of all faces, and bounding-box size in local units."""
    verts = {v for f in faces for v in f.verts}
    lo = [min(v.co[i] for v in verts) for i in range(3)]
    hi = [max(v.co[i] for v in verts) for i in range(3)]
    return {"share": round(len(faces) / total, 4), "size": [round(hi[i] - lo[i], 3) for i in range(3)]}


def material_report(obj):
    report = []
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None:
            continue
        entry = {
            "name": mat.name,
            "blend": getattr(mat, "surface_render_method", None) or getattr(mat, "blend_method", None),
            "images": [],
            "principled": None,
        }
        if mat.use_nodes:
            for node in mat.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image:
                    entry["images"].append({"name": node.image.name, "size": list(node.image.size)})
                if node.type == "BSDF_PRINCIPLED":
                    def linked(sock):
                        return node.inputs[sock].is_linked
                    entry["principled"] = {
                        "base_color_textured": linked("Base Color"),
                        "metallic": "texture" if linked("Metallic") else round(node.inputs["Metallic"].default_value, 3),
                        "roughness": "texture" if linked("Roughness") else round(node.inputs["Roughness"].default_value, 3),
                        "alpha": "texture" if linked("Alpha") else round(node.inputs["Alpha"].default_value, 3),
                        "normal_map": linked("Normal"),
                    }
        report.append(entry)
    return report


obj = pick_object(PARAMS["object"])
me = obj.data
corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
low = Vector([min(c[i] for c in corners) for i in range(3)])
high = Vector([max(c[i] for c in corners) for i in range(3)])
size = high - low
tiny = max(size) * 1e-5

# glTF stores one UV per vertex, so an imported mesh is split along every
# texture seam into hundreds of "pieces" with open edges. Measure a welded
# copy (the object itself is untouched) to see the real topology.
bm = bmesh.new()
bm.from_mesh(me)
raw_vertices = len(bm.verts)
raw_triangles = sum(len(f.verts) - 2 for f in bm.faces)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=max(size) * 1e-6)
bm.faces.ensure_lookup_table()
bm.verts.index_update()
bm.faces.index_update()

pieces = islands(bm)
total_faces = max(len(bm.faces), 1)
longest_edge = max((e.calc_length() for e in bm.edges), default=0.0)

report = {
    "object": obj.name,
    "triangles": raw_triangles,
    "vertices": raw_vertices,
    "seam_split_vertices": raw_vertices - len(bm.verts),
    "size_m": [round(v, 4) for v in size],
    "bottom_z": round(low.z, 4),
    "origin": [round(v, 4) for v in obj.location],
    "unapplied_transform": (
        any(abs(v) > 1e-4 for v in obj.rotation_euler)
        or any(abs(v - 1.0) > 1e-4 for v in obj.scale)
    ),
    "pieces": len(pieces),
    "largest_piece_share": round(len(pieces[0]) / total_faces, 4) if pieces else 0,
    "small_pieces": sum(1 for p in pieces[1:] if len(p) / total_faces < 0.002),
    "largest_pieces": [piece_summary(p, total_faces) for p in pieces[:8]],
    "non_manifold_edges": sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary),
    "boundary_edges": sum(1 for e in bm.edges if e.is_boundary),
    "wire_edges": sum(1 for e in bm.edges if e.is_wire),
    "loose_vertices": sum(1 for v in bm.verts if not v.link_edges),
    "degenerate_faces": sum(1 for f in bm.faces if f.calc_area() < tiny * tiny),
    "longest_edge_m": round(longest_edge, 4),
    "uv_layers": [uv.name for uv in me.uv_layers],
    "smooth_shaded": any(p.use_smooth for p in me.polygons),
    "modifiers": [m.type for m in obj.modifiers],
    "materials": material_report(obj),
}
bm.free()
print("RESULT " + json.dumps(report))
