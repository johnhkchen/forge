# Split an object into named parts using boxes, or just color the parts.
#
# TRELLIS.2 fuses touching parts (a kettle's lid, knob and spout are one
# surface with the body), so the parts can't be found from the mesh alone.
# Instead someone who knows what the object is (Claude, from the brief and a
# look at it) places one axis-aligned box per part, in world coordinates.
# Each face goes to the FIRST part whose box contains its center, so list
# small parts inside bigger ones first (knob before lid). Faces in no box
# belong to the body.
#
# mode "color": paints each part a distinct color, changes nothing else. Use
#               it with `look` to check the boxes.
# mode "split": separates each part into its own object named
#               "<object> · <part>" and closes the opening where it was cut
#               (the cap sits inside the joint, as on a modeled prop).
#
# Prints RESULT {json} with each part's face count and share of the area.
# Safe-mode compatible: bpy, bmesh, mathutils, math and json only.

PARAMS = {
    "object": None,   # None = the largest visible mesh
    "parts": [],      # [{"name": "knob", "box": {"min": [x, y, z], "max": [x, y, z]}}, ...]
    "mode": "color",  # "color" or "split"
    "body": "body",   # name for faces in no box
}

import bpy
import bmesh
import colorsys
import json
from mathutils import Vector



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


def inside(p, box):
    lo, hi = box["min"], box["max"]
    return all(lo[i] <= p[i] <= hi[i] for i in range(3))


def assign(obj, parts, body):
    """Part index per face (len(parts) = body), by face center in world space."""
    m = obj.matrix_world
    out = []
    for poly in obj.data.polygons:
        c = m @ poly.center
        out.append(next((i for i, p in enumerate(parts) if inside(c, p["box"])), len(parts)))
    return out


def neighbors(obj):
    """Faces that share an edge, matched by vertex position so texture seams
    (where glTF duplicates vertices) don't break the surface apart."""
    size = max(obj.dimensions) or 1.0
    grid = size * 1e-6
    me = obj.data
    keys = [tuple(round(c / grid) for c in v.co) for v in me.vertices]
    edge_faces = {}
    for poly in me.polygons:
        vs = poly.vertices
        for i in range(len(vs)):
            a, b = keys[vs[i]], keys[vs[(i + 1) % len(vs)]]
            edge = (a, b) if a < b else (b, a)
            edge_faces.setdefault(edge, []).append(poly.index)
    near = [[] for _ in me.polygons]
    for faces in edge_faces.values():
        for f in faces:
            near[f].extend(g for g in faces if g != f)
    return near


def tidy_owners(owner, near, body):
    """Box cuts through a fused surface leave scraps: a bit of body caught in
    a bracket's box, a ring of body inside the lid's box. Keep each part's
    largest connected region; give every other region of it to the
    neighboring part it shares the most border with. Regions that touch
    nothing (a separate pin) stay where they are."""
    for _ in range(3):
        seen = [False] * len(owner)
        regions = []
        for start in range(len(owner)):
            if seen[start]:
                continue
            k = owner[start]
            stack, region = [start], []
            seen[start] = True
            while stack:
                f = stack.pop()
                region.append(f)
                for g in near[f]:
                    if not seen[g] and owner[g] == k:
                        seen[g] = True
                        stack.append(g)
            regions.append((k, region))
        largest = {}
        for k, region in regions:
            if len(region) > len(largest.get(k, [])):
                largest[k] = region
        moved = 0
        for k, region in regions:
            if region is largest[k]:
                continue
            border = {}
            members = set(region)
            for f in region:
                for g in near[f]:
                    if g not in members and owner[g] != k:
                        border[owner[g]] = border.get(owner[g], 0) + 1
            if not border:
                continue
            into = max(border.items(), key=second)[0]
            for f in region:
                owner[f] = into
            moved += 1
        if not moved:
            break
    return owner


def second(pair):
    return pair[1]


obj = pick_object(PARAMS["object"])
parts = PARAMS["parts"]
for p in parts:
    if not p.get("name") or "box" not in p or len(p["box"]["min"]) != 3 or len(p["box"]["max"]) != 3:
        raise ValueError("each part needs a name and a box with 3-number min and max: %r" % p)
names = [p["name"] for p in parts] + [PARAMS["body"]]
owner = tidy_owners(assign(obj, parts, PARAMS["body"]), neighbors(obj), len(parts))

areas = [0.0] * len(names)
counts = [0] * len(names)
for poly, k in zip(obj.data.polygons, owner):
    areas[k] += poly.area
    counts[k] += 1
total = sum(areas) or 1.0
report = [{"part": n, "faces": counts[i], "share": round(areas[i] / total, 4)} for i, n in enumerate(names)]

if PARAMS["mode"] == "color":
    attr = obj.data.color_attributes.get("part color") or obj.data.color_attributes.new("part color", "BYTE_COLOR", "CORNER")
    palette = [colorsys.hsv_to_rgb((i * 0.618034) % 1.0, 0.6, 0.95) for i in range(len(names))]
    palette[-1] = (0.82, 0.8, 0.77)  # the body stays a quiet clay gray
    for poly, k in zip(obj.data.polygons, owner):
        for li in poly.loop_indices:
            attr.data[li].color = (*palette[k], 1.0)
    mat = bpy.data.materials.get("parts preview") or bpy.data.materials.new("parts preview")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    color = nodes.get("part color") or nodes.new("ShaderNodeAttribute")
    color.name = "part color"
    color.attribute_name = "part color"
    mat.node_tree.links.new(color.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    report_mode = "colored"
elif PARAMS["mode"] == "split":
    made = []
    for k, name in enumerate(names):
        if not counts[k]:
            continue
        piece = obj.copy()
        piece.data = obj.data.copy()
        piece.name = "%s · %s" % (obj.name, name)
        for c in obj.users_collection:
            c.objects.link(piece)
        bm = bmesh.new()
        bm.from_mesh(piece.data)
        bm.faces.ensure_lookup_table()
        drop = [f for f in bm.faces if owner[f.index] != k]
        bmesh.ops.delete(bm, geom=drop, context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=max(obj.dimensions) * 1e-6)
        rim = [e for e in bm.edges if e.is_boundary]
        if rim:
            bmesh.ops.holes_fill(bm, edges=rim, sides=0)
            bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(piece.data)
        bm.free()
        piece["part"] = name
        made.append(piece.name)
    obj.hide_set(True)
    obj.hide_render = True
    report_mode = "split into %s" % ", ".join(made)
else:
    raise ValueError("mode must be 'color' or 'split'")

print("RESULT " + json.dumps({"object": obj.name, "mode": report_mode, "parts": report}))
