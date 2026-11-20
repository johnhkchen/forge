# Block out a low-poly version from a list of simple pieces, join them into
# one object, and say how far it strays from the detailed mesh.
#
# Each piece has a "name", an optional "color" [r, g, b] (painted flat as
# vertex color), and ONE of these shapes:
#
#   "loft": "z" (or "x", "y")  a stack of rings along that axis, skinned.
#       "rings": [[position, middle, middle, half-width, half-width], ...]
#       exactly the rows measure.py prints. [position, middle, middle, radius]
#       makes a round ring, so a lathe (body, lid, knob) is a loft of those.
#   "tube": [[x, y, z, radius], ...]  a bar swept through those points
#       (spout, handle, arm, tail). [x, y, z, half-width across, half-width
#       along "up"] makes it oval. "up": [0, 0, 1] sets which way is up.
#   "lumps": [[x, y, z, radius], ...]  rough rocks, one per row
#       ([x, y, z, rx, ry, rz] squashes one). "jitter": 0.2, "seed": 1.
#   "box": {"min": [x, y, z], "max": [x, y, z]}
#
# For lofts and tubes:
#   "sides": 8            points around each ring (4 makes a square post)
#   "square": 2           2 = oval; higher is boxier (2.4 for limbs, 4 for a block)
#   "caps": [True, True]  close the first / last ring; False leaves an end
#                         open where it hides inside another piece
#   "closed": True        join the last ring back to the first (a belt or
#                         band: four rings, outer top, outer bottom, inner
#                         bottom, inner top)
#   a ring may end with extras: [z, x, y, rx, ry, {"square": 4, "back": 0.5,
#   "slope": 0.2}]. "back" is a different half-width on the + side of the
#   second across-axis (a belly in front, a flat back); "slope" tilts the
#   ring (a belt that sits lower in front).
#   Add a ring where something bends (elbow, knee) to give it an edge loop.
# Any piece: "mirror": True also builds its twin across x = 0.
#
# Pieces stay in the scene, hidden, so the next call only needs the pieces
# that change ("parts") or go ("remove"); everything is joined again each time.
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down
# (these comments can stay behind). Prints RESULT {json}. 1-3 s.
# Safe-mode compatible.

PARAMS = {
    "reference": None,  # the detailed mesh to build around; None = the largest visible mesh
    "name": None,       # the joined object's name; None = "<reference> (light)"
    "parts": [],        # pieces to add or replace, by name
    "remove": [],       # names of pieces to drop
    "shading": "flat",  # "flat" (faceted) or "smooth"
    "check": 8000,      # points to sample for the shape check; 0 = skip it
}

import bpy
import bmesh
import json
import math
import random
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ACROSS = {"x": (0, 1, 2), "y": (1, 0, 2), "z": (2, 0, 1)}


def face_count(obj):
    return len(obj.data.polygons)

def extras(row):
    return row[-1] if isinstance(row[-1], dict) else {}

def numbers(row):
    return [v for v in row if not isinstance(v, dict)]

def outline(sides, square, turn):
    """Unit ring: `sides` points of a rounded square, scaled to span -1..1 both ways."""
    pts = []
    for k in range(sides):
        t = math.pi / sides + math.radians(turn) + 2 * math.pi * k / sides
        c, s = math.cos(t), math.sin(t)
        pts.append((math.copysign(abs(c) ** (2 / square), c), math.copysign(abs(s) ** (2 / square), s)))
    wide = max(abs(p[0]) for p in pts)
    tall = max(abs(p[1]) for p in pts)
    return [(p[0] / wide, p[1] / tall) for p in pts]

def loft_rings(part):
    a, u, v = ACROSS[part["loft"]]
    rings = []
    for row in part["rings"]:
        n, more = numbers(row), extras(row)
        ru, rv = n[3], n[4] if len(n) > 4 else n[3]
        ring = []
        for pu, pv in outline(part.get("sides", 8), more.get("square", part.get("square", 2)), part.get("turn", 0)):
            reach = pv * (more.get("back", rv) if pv > 0 else rv)
            p = [0.0, 0.0, 0.0]
            p[a], p[u], p[v] = n[0] + more.get("slope", 0) * reach, n[1] + pu * ru, n[2] + reach
            ring.append(Vector(p))
        rings.append(ring)
    return rings

def tube_rings(part):
    rows = part["tube"]
    pts = [Vector(numbers(r)[:3]) for r in rows]
    last = len(pts) - 1
    side = None
    rings = []
    for i, row in enumerate(rows):
        n, more = numbers(row), extras(row)
        if part.get("closed"):
            ahead = pts[(i + 1) % len(pts)] - pts[i - 1]
        else:
            ahead = pts[min(i + 1, last)] - pts[max(i - 1, 0)]
        ahead.normalize()
        if side is None:
            side = Vector(part.get("up", (0, 0, 1))).cross(ahead)
            if side.length < 1e-6:
                side = Vector((1, 0, 0)).cross(ahead) if abs(ahead.x) < 0.9 else Vector((0, 1, 0)).cross(ahead)
        side = (side - ahead * side.dot(ahead)).normalized()  # carried along the path, so it never flips
        top = ahead.cross(side)
        ru, rv = n[3], n[4] if len(n) > 4 else n[3]
        shape = outline(part.get("sides", 6), more.get("square", part.get("square", 2)), part.get("turn", 0))
        rings.append([pts[i] + side * (pu * ru) + top * (pv * rv) for pu, pv in shape])
    return rings

def skin(rings, caps, closed):
    n = len(rings[0])
    verts = [p for ring in rings for p in ring]
    faces = []
    for i in range(len(rings) if closed else len(rings) - 1):
        a, b = i * n, ((i + 1) % len(rings)) * n
        faces += [(a + j, a + (j + 1) % n, b + (j + 1) % n, b + j) for j in range(n)]
    if not closed and caps[0]:
        faces.append(tuple(reversed(range(n))))
    if not closed and caps[1]:
        faces.append(tuple(range(len(verts) - n, len(verts))))
    # Face outward: on the first two rings, the sides should point away from the middle.
    middle = sum(verts[:2 * n], Vector()) / (2 * n)
    out = 0.0
    for f in faces[:n]:
        a, b, c, d = [verts[i] for i in f]
        out += (c - a).cross(d - b).dot((a + b + c + d) / 4 - middle)
    if out < 0:
        faces = [tuple(reversed(f)) for f in faces]
    return verts, faces

def lumps(part):
    rng = random.Random(part.get("seed", 1))
    jitter = part.get("jitter", 0.2)
    verts, faces = [], []
    for row in part["lumps"]:
        size = row[3:6] if len(row) > 5 else [row[3]] * 3
        ball = bmesh.new()
        bmesh.ops.create_icosphere(ball, subdivisions=part.get("detail", 1), radius=1.0)
        start = len(verts)
        verts += [Vector([row[i] + v.co[i] * size[i] * (1 + jitter * (2 * rng.random() - 1)) for i in range(3)]) for v in ball.verts]
        faces += [tuple(start + v.index for v in f.verts) for f in ball.faces]
        if part.get("mirror") and abs(row[0]) > size[0] * 0.1:  # one on the center line has no twin
            twin = len(verts)
            verts += [Vector((-p.x, p.y, p.z)) for p in verts[start:twin]]
            faces += [tuple(reversed([twin - start + i for i in f])) for f in faces[-len(ball.faces):]]
        ball.free()
    return verts, faces

def box(part):
    lo, hi = part["box"]["min"], part["box"]["max"]
    verts = [Vector((x, y, z)) for z in (lo[2], hi[2]) for y in (lo[1], hi[1]) for x in (lo[0], hi[0])]
    return verts, [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]

def make_piece(part, owner, scene):
    if "loft" in part:
        verts, faces = skin(loft_rings(part), part.get("caps", [True, True]), part.get("closed", False))
    elif "tube" in part:
        verts, faces = skin(tube_rings(part), part.get("caps", [True, True]), part.get("closed", False))
    elif "lumps" in part:
        verts, faces = lumps(part)
    elif "box" in part:
        verts, faces = box(part)
    else:
        raise ValueError("piece %r needs a loft, tube, lumps or box" % part.get("name"))
    if part.get("mirror") and "lumps" not in part:
        count = len(verts)
        verts = verts + [Vector((-p.x, p.y, p.z)) for p in verts]
        faces = faces + [tuple(reversed([count + i for i in f])) for f in faces]
    me = bpy.data.meshes.new("piece: " + part["name"])
    me.from_pydata([tuple(p) for p in verts], [], faces)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)  # a ring of radius 0 becomes a point
    if "lumps" in part or "box" in part:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    paint = me.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
    shade = tuple(part.get("color", (0.6, 0.6, 0.6)))[:3] + (1.0,)
    for d in paint.data:
        d.color = shade
    piece = bpy.data.objects.new("piece: " + part["name"], me)
    piece["piece_of"] = owner
    piece["piece"] = part["name"]
    scene.collection.objects.link(piece)
    piece.hide_set(True)
    piece.hide_render = True
    return piece

def triangles(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)

def spread(me, count, rng):
    """Points spread evenly over a mesh's surface."""
    me.calc_loop_triangles()
    tris = me.loop_triangles
    out = []
    for i in rng.choices(range(len(tris)), weights=[t.area for t in tris], k=count):
        a, b, c = [me.vertices[v].co for v in tris[i].vertices]
        r1, r2 = rng.random(), rng.random()
        if r1 + r2 > 1:
            r1, r2 = 1 - r1, 1 - r2
        out.append(a + (b - a) * r1 + (c - a) * r2)
    return out

def off(points, tree, size):
    """How far each point is from a surface, in % of the object's size, farthest first."""
    found = [(tree.find_nearest(p), p) for p in points]
    return sorted([(100 * hit[3] / size, p) for hit, p in found if hit[0] is not None], key=first, reverse=True)

def first(pair):
    return pair[0]

def summary(d):
    if not d:
        return None
    return {"mean_%": round(sum(x for x, _ in d) / len(d), 2), "p95_%": round(d[len(d) // 20][0], 2), "max_%": round(d[0][0], 2)}


scene = bpy.context.scene
ref = bpy.data.objects.get(PARAMS["reference"]) if PARAMS["reference"] else None
if ref is None:
    candidates = [o for o in scene.objects if o.type == "MESH" and o.visible_get() and not o.name.endswith(" (light)")]
    if not candidates:
        raise ValueError("no reference mesh: open the detailed mesh first, or set PARAMS['reference']")
    ref = max(candidates, key=face_count)
name = PARAMS["name"] or ref.name + " (light)"

pieces = {o["piece"]: o for o in scene.objects if o.get("piece_of") == name}
for gone in PARAMS["remove"] + [p["name"] for p in PARAMS["parts"]]:
    if gone in pieces:
        bpy.data.objects.remove(pieces.pop(gone), do_unlink=True)
for part in PARAMS["parts"]:
    pieces[part["name"]] = make_piece(part, name, scene)
if not pieces:
    raise ValueError("nothing to build: PARAMS['parts'] is empty")

joined = bmesh.new()
for piece in pieces.values():
    joined.from_mesh(piece.data)
light = bpy.data.objects.get(name)
if light is None:
    light = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    scene.collection.objects.link(light)
joined.to_mesh(light.data)
joined.free()
light.data.polygons.foreach_set("use_smooth", [PARAMS["shading"] == "smooth"] * len(light.data.polygons))
light.data.update()
bpy.context.view_layer.update()
mat = bpy.data.materials.get("piece colors") or bpy.data.materials.new("piece colors")
mat.use_nodes = True
nodes = mat.node_tree.nodes
paint = nodes.get("Col") or nodes.new("ShaderNodeAttribute")
paint.name = paint.attribute_name = "Col"
mat.node_tree.links.new(paint.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
light.data.materials.clear()
light.data.materials.append(mat)

result = {
    "object": light.name,
    "reference": ref.name,
    "triangles": triangles(light.data),
    "size": [round(d, 3) for d in light.dimensions],
    "reference_size": [round(d, 3) for d in ref.dimensions],
    "pieces": [{"name": n, "triangles": triangles(o.data)} for n, o in pieces.items()],
}
if PARAMS["check"]:
    rng = random.Random(0)
    size = max(ref.dimensions)
    to_ref = ref.matrix_world.inverted()
    ref_tree = BVHTree.FromObject(ref, bpy.context.evaluated_depsgraph_get())
    light_tree = BVHTree.FromPolygons([tuple(v.co) for v in light.data.vertices], [tuple(p.vertices) for p in light.data.polygons])
    lost = off([ref.matrix_world @ p for p in spread(ref.data, PARAMS["check"], rng)], light_tree, size)
    added = []
    for entry, piece in zip(result["pieces"], pieces.values()):
        share = max(50, PARAMS["check"] * entry["triangles"] // max(result["triangles"], 1))
        d = off([to_ref @ p for p in spread(piece.data, share, rng)], ref_tree, size)
        added += d
        if d:
            entry["sticks_out_%"] = round(d[0][0], 2)
            entry["worst_at"] = [round(c, 3) for c in ref.matrix_world @ d[0][1]]
    spots = []
    for dist, p in lost:
        if all((p - q).length > size * 0.12 for _, q in spots):
            spots.append((dist, p))
        if len(spots) == 5:
            break
    result["shape_lost"] = summary(lost)
    result["shape_added"] = summary(sorted(added, key=first, reverse=True))
    result["most_missing_at"] = [{"at": [round(c, 3) for c in p], "off_%": round(dist, 2)} for dist, p in spots]

print("RESULT " + json.dumps(result))
