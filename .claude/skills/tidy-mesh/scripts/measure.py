# Measure a mesh region by region: how big each part is and, slice by slice,
# where its middle sits and how wide it is. Changes nothing.
#
# Each entry in "measure" picks vertices two ways, alone or together:
#   "part": a name from "parts" (the same boxes split.py and parts.json use;
#           a vertex belongs to the FIRST box holding it), or "body" for
#           everything in no box. This keeps neighbors out: the kettle's
#           body without its bracket feet, lid without the knob.
#   "box":  {"min": [x, y, z], "max": [x, y, z]} in world meters, to fence
#           off something that has no part box (one arm, the head).
# With "along": "x", "y" or "z" it also cuts the region into slices and
# prints one row per slice: [position, middle, middle, half-width, half-width]
# in the other two axes (the "columns" say which). These rows are the
# "rings" build.py takes, so a measured part can go straight into a loft.
#   "slices": 8             that many, evenly spaced, both ends included
#   "at": [0.42, 0.62, ..]  or exactly these positions
#
# Send this whole file through the blender MCP `execute_blender_code` tool
# after editing PARAMS. Prints RESULT {json}. A second or two.
# Safe-mode compatible.

PARAMS = {
    "object": None,  # None = the largest visible mesh
    "parts": [],     # [{"name": "knob", "min": [x, y, z], "max": [x, y, z]}, ...] (parts.json's list as it is)
    "measure": [],   # [{"name": "spout", "part": "spout", "along": "x", "slices": 7}, ...]; empty = every part and the body
}

import bpy
import json
import math
from mathutils import Euler, Vector

AXES = {"x": (0, 1, 2), "y": (1, 0, 2), "z": (2, 0, 1)}  # along -> (its axis, the two it is measured across)


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

def as_box(part):
    """(low, high, turn matrix or None, center) from a part or a plain box."""
    box = part.get("box", part)
    low, high = Vector(box["min"]), Vector(box["max"])
    turn = part.get("turn") or box.get("turn")
    back = Euler([math.radians(a) for a in turn]).to_matrix().inverted() if turn and any(turn) else None
    return low, high, back, (low + high) / 2

def inside(p, box):
    low, high, back, center = box
    if back:
        p = back @ (p - center) + center
    return low[0] <= p[0] <= high[0] and low[1] <= p[1] <= high[1] and low[2] <= p[2] <= high[2]

def extent(points, axis):
    values = [p[axis] for p in points]
    return min(values), max(values)

def rounded(values):
    return [round(v, 4) for v in values]


obj = pick_object(PARAMS["object"])
world = obj.matrix_world
points = [world @ v.co for v in obj.data.vertices]
names = [p["name"] for p in PARAMS["parts"]]
boxes = [as_box(p) for p in PARAMS["parts"]]

owner = []  # for each vertex: the first part box holding it, or len(boxes) for the body
for p in points:
    k = len(boxes)
    for i, box in enumerate(boxes):
        if inside(p, box):
            k = i
            break
    owner.append(k)

jobs = PARAMS["measure"] or [{"name": n, "part": n} for n in list(dict.fromkeys(names)) + ["body"]]
report = []
for job in jobs:
    chosen = points
    if job.get("part"):
        if job["part"] != "body" and job["part"] not in names:
            raise ValueError("measure %r: no part named %r in PARAMS['parts']" % (job.get("name"), job["part"]))
        keep = [len(boxes)] if job["part"] == "body" else [i for i, n in enumerate(names) if n == job["part"]]
        chosen = [p for p, k in zip(points, owner) if k in keep]
    if job.get("box"):
        fence = as_box(job["box"])
        chosen = [p for p in chosen if inside(p, fence)]
    entry = {"name": job.get("name") or job.get("part") or "region", "vertices": len(chosen)}
    report.append(entry)
    if not chosen:
        entry["note"] = "nothing there: check the box or the part name"
        continue
    spans = [extent(chosen, i) for i in range(3)]
    entry["min"] = rounded(s[0] for s in spans)
    entry["max"] = rounded(s[1] for s in spans)
    entry["size"] = rounded(s[1] - s[0] for s in spans)
    if not job.get("along"):
        continue
    a, u, v = AXES[job["along"]]
    start, end = spans[a]
    if job.get("at"):
        stations = sorted(job["at"])
        gaps = [q - p for p, q in zip(stations, stations[1:])]
        half = job.get("thick", min(gaps) if gaps else (end - start) * 0.05) / 2
    else:
        count = max(2, job.get("slices", 8))
        stations = [start + (end - start) * i / (count - 1) for i in range(count)]
        half = (end - start) / (count - 1) / 2
    buckets = [[] for _ in stations]
    for p in chosen:
        for i, t in enumerate(stations):
            if t - half <= p[a] <= t + half:
                buckets[i].append(p)
    rows = []
    for t, bucket in zip(stations, buckets):
        if not bucket:
            continue
        (u0, u1), (v0, v1) = extent(bucket, u), extent(bucket, v)
        rows.append(rounded([t, (u0 + u1) / 2, (v0 + v1) / 2, (u1 - u0) / 2, (v1 - v0) / 2]))
    entry["along"] = job["along"]
    entry["columns"] = ["xyz"[a], "middle " + "xyz"[u], "middle " + "xyz"[v], "half-width " + "xyz"[u], "half-width " + "xyz"[v]]
    entry["rows"] = rows
    entry["slice_thickness"] = round(half * 2, 4)

print("RESULT " + json.dumps({"object": obj.name, "regions": report}))
