# How closely a light mesh keeps the shape of the full one, and where it
# drifts. Changes nothing. Prints RESULT {json}.
#
# Measures both ways, since each misses different failures:
#   full -> light  catches lost shape (a spout tip that got shorter)
#   light -> full  catches bulges and webbing that aren't in the original
# Distances are given as a percentage of the object's largest dimension.
# Under ~0.5% is invisible at normal viewing distance; over ~1.5% shows in
# the silhouette.
#
# Safe-mode compatible: bpy, bmesh, mathutils, math and json only.

PARAMS = {
    "full": None,    # the original mesh; None = the hidden source of the light mesh
    "light": None,   # the reduced mesh; None = the "(quads)" or "(light)" mesh in the scene
    "samples": 20000,
    "worst": 5,      # how many worst spots to describe
}

import bpy
import json
import random
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def find(name, suffix_match):
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise ValueError("no mesh object named %r" % name)
        return obj
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name.endswith((" (quads)", " (light)")):
            return o if suffix_match else bpy.data.objects.get(o.name.rsplit(" (", 1)[0])
    raise ValueError("name the meshes: no '(quads)' or '(light)' mesh found")


def world_tree(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    return BVHTree.FromObject(obj, deps), obj.evaluated_get(deps)


def surface_points(obj, count):
    """Points spread over the surface by area, in world space."""
    me = obj.data
    me.calc_loop_triangles()
    tris = me.loop_triangles
    areas = [t.area for t in tris]
    total = sum(areas)
    rng = random.Random(0)
    m = obj.matrix_world
    picks = rng.choices(range(len(tris)), weights=areas, k=count)
    out = []
    for i in picks:
        a, b, c = (me.vertices[v].co for v in tris[i].vertices)
        r1, r2 = rng.random(), rng.random()
        if r1 + r2 > 1:
            r1, r2 = 1 - r1, 1 - r2
        out.append(m @ (a + (b - a) * r1 + (c - a) * r2))
    return out, total


def distances(points, tree, matrix_inv, matrix):
    out = []
    for p in points:
        hit = tree.find_nearest(matrix_inv @ p)
        out.append((((matrix @ hit[0]) - p).length if hit[0] else 0.0, p))
    return out


def where(p, lo, hi):
    """Describe a point by where it sits in the bounding box."""
    rel = [(p[i] - lo[i]) / max(hi[i] - lo[i], 1e-9) for i in range(3)]
    words = []
    for value, low_word, high_word in ((rel[2], "bottom", "top"), (rel[0], "left (-X)", "right (+X)"), (rel[1], "front (-Y)", "back (+Y)")):
        if value < 0.2:
            words.append(low_word)
        elif value > 0.8:
            words.append(high_word)
    return " ".join(words) or "middle"


def summarize(pairs, size):
    d = sorted(x for x, _ in pairs)
    def pct(q):
        return round(100 * d[min(len(d) - 1, int(q * len(d)))] / size, 2)
    return {"mean_%": round(100 * sum(d) / len(d) / size, 3), "p95_%": pct(0.95), "max_%": pct(1.0)}


full = find(PARAMS["full"], False)
light = find(PARAMS["light"], True)
size = max(full.dimensions)
corners = [full.matrix_world @ Vector(c) for c in full.bound_box]
lo = Vector([min(c[i] for c in corners) for i in range(3)])
hi = Vector([max(c[i] for c in corners) for i in range(3)])

full_tree, _ = world_tree(full)
light_tree, _ = world_tree(light)
n = PARAMS["samples"]
full_pts, _ = surface_points(full, n)
light_pts, _ = surface_points(light, n)
lost = distances(full_pts, light_tree, light.matrix_world.inverted(), light.matrix_world)
added = distances(light_pts, full_tree, full.matrix_world.inverted(), full.matrix_world)

worst = []
def farthest_first(pair):
    return -pair[0]


for dist, p in sorted(lost + added, key=farthest_first):
    spot = where(p, lo, hi)
    if any(w["where"] == spot for w in worst):
        continue
    worst.append({"where": spot, "off_%": round(100 * dist / size, 2)})
    if len(worst) == PARAMS["worst"]:
        break

print("RESULT " + json.dumps({
    "full": full.name,
    "light": light.name,
    "shape_lost": summarize(lost, size),
    "shape_added": summarize(added, size),
    "worst_spots": worst,
}))
