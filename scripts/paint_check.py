"""Measure a painted character in motion, in a background Blender.

    blender -b --factory-startup -P scripts/paint_check.py -- FILE.glb [FILE.glb ...]

FILE is a character on the wardrobe's template body with a skeleton and a clip
(profiles/painted-walk.glb, painted-rom.glb): its body is the template from
the collar down (the faces whose material is marked "template") and the
character's own head above it. For each file it prints one line,
`PAINT {json}`:

- "collar": the template's open edge round the neck, followed over every
  frame of the clip: how far its points stand from the head's surface, which
  reaches down inside it. "gap_cm" has the gap standing still, the worst over
  the clip and the frame it happens on. A collar that opens shows the inside
  of the body.
- "floor": how far below the floor the template's lowest point goes over the
  clip ("deepest_cm"), against where it is standing still. Weights that tie a
  foot to the wrong bone show up here first.
- "weights": how many of the template's points follow more than one bone, and
  how many bones the template's points follow in all: a body bound whole to
  one limb has one bone and no blends.
- "triangles": the template's, the head's, and the gear's.

    blender -b --factory-startup -P scripts/paint_check.py -- --edges TEMPLATE.glb GARMENT.png [GARMENT.png ...]

measures instead how clean a painted garment's edge is, from its picture (painted-outfit/<garment>.png) and
the template's texture layout. One line a picture, `EDGE {json}`:

- "ragged": the length of the garment's edge against the length of the same edge evened out (the picture
  blurred over about 2 cm and cut at half). A sewn edge is nearly its own evened-out self: about 1. An edge
  copied from a rough texture wanders in and out: 1.3 and up.
- "scraps": pieces of the garment off on their own, each under 2% of it. A garment drawn as one shape has none
  (the layout's own seams cut it into a few big pieces, which is not counted).
- "edge_cm", "evened_edge_cm": the two lengths, counting only edges inside the layout's islands (where an
  island ends is the layout's doing, not the garment's).

Nothing is written. scripts/test_tools.py reads these numbers.
"""
import json
import os
import sys

import bpy
import numpy as np
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


def template_faces(obj):
    marked = [k for k, m in enumerate(obj.data.materials) if m is not None and m.get("template")]
    return [p.index for p in obj.data.polygons if p.material_index in marked]


def check(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = 30  # what every motion here is baked at; the importer lays keys out by the scene's rate
    bpy.ops.import_scene.gltf(filepath=path)
    scene = bpy.context.scene
    body = [o for o in scene.objects if o.type == "MESH" and o.get("forge") == "body"]
    gear = [o for o in scene.objects if o.type == "MESH" and o.get("forge") == "gear"]
    of_template = {o.name: template_faces(o) for o in body}
    if not any(of_template.values()):
        return {"file": path, "skipped": "no body here is the wardrobe template"}
    rig = next((o for o in scene.objects if o.type == "ARMATURE"), None)
    action = rig.animation_data.action if rig and rig.animation_data else None
    frames = list(range(int(round(action.frame_range[0])), int(round(action.frame_range[1])))) if action else [0]

    # Standing still: the template's surface with the points a .glb split along seams (and where the skin under
    # gear was written apart) taken as one. Its one open edge is the collar.
    if rig:
        rig.data.pose_position = "REST"
    scene.frame_set(frames[0])
    bpy.context.view_layer.update()
    corners = []  # (object, point) for each of the template's corners
    for o in body:
        for fi in of_template[o.name]:
            corners += [(o.name, i) for i in o.data.polygons[fi].vertices]
    places = {key: bpy.data.objects[key[0]].matrix_world @ bpy.data.objects[key[0]].data.vertices[key[1]].co for key in set(corners)}
    keys = sorted(places)
    tree = KDTree(len(keys))
    for n, key in enumerate(keys):
        tree.insert(places[key], n)
    tree.balance()
    spot, count = {}, 0
    for n, key in enumerate(keys):
        if key in spot:
            continue
        for co, j, d in tree.find_range(places[key], 1e-4):
            spot.setdefault(keys[j], count)
        count += 1
    edges = {}
    for o in body:
        for fi in of_template[o.name]:
            ring = [spot[(o.name, i)] for i in o.data.polygons[fi].vertices]
            for a, b in zip(ring, ring[1:] + ring[:1]):
                edges[(min(a, b), max(a, b))] = edges.get((min(a, b), max(a, b)), 0) + 1
    open_spots = {s for edge, used in edges.items() if used == 1 for s in edge}
    collar = [key for key in keys if spot[key] in open_spots]
    floor = min(p.z for p in places.values())
    tall = max(max((o.matrix_world @ v.co).z for v in o.data.vertices) for o in body) - floor
    used_bones, blended, points = set(), 0, 0
    for o in body:
        names = {g.index: g.name for g in o.vertex_groups}
        for i in {i for fi in of_template[o.name] for i in o.data.polygons[fi].vertices}:
            mine = [names[g.group] for g in o.data.vertices[i].groups if g.weight > 0.02]
            used_bones.update(mine)
            blended += len(mine) > 1
            points += 1

    if rig:
        rig.data.pose_position = "POSE"
    still = worst = None
    worst_frame, deepest, deepest_frame = None, 0.0, None
    for f in frames:
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
        shown, head_points, head_faces, low = {}, [], [], 1e9
        for o in body:
            ev = o.evaluated_get(deps)
            me = ev.to_mesh()
            here = [ev.matrix_world @ v.co for v in me.vertices]
            shown[o.name] = here
            mine = set(of_template[o.name])
            start = len(head_points)
            head_points += here
            head_faces += [tuple(start + i for i in p.vertices) for p in me.polygons if p.index not in mine]
            for fi in mine:
                for i in me.polygons[fi].vertices:
                    low = min(low, here[i].z)
            ev.to_mesh_clear()
        head = BVHTree.FromPolygons(head_points, head_faces)
        gap = max(head.find_nearest(shown[name][i])[3] for name, i in collar)
        if still is None:
            still = gap
        if worst is None or gap > worst:
            worst, worst_frame = gap, f
        if floor - low > deepest:
            deepest, deepest_frame = floor - low, f
    return {
        "file": path, "height": round(tall, 3), "frames": len(frames), "clip": action.name if action else None,
        "body_meshes": sorted(o.name for o in body), "gear_meshes": sorted(o.name for o in gear),
        "collar": {"points": len(open_spots), "edges": sum(1 for used in edges.values() if used == 1),
                   "gap_cm": {"standing": round(100 * still, 2), "worst": round(100 * worst, 2), "worst_frame": worst_frame}},
        "floor": {"deepest_cm": round(100 * deepest, 2), "frame": deepest_frame},
        "weights": {"template_points": points, "following_more_than_one_bone": blended, "bones_followed": len(used_bones)},
        "triangles": {"template": sum(len(o.data.polygons[fi].vertices) - 2 for o in body for fi in of_template[o.name]),
                      "body": sum(len(p.vertices) - 2 for o in body for p in o.data.polygons),
                      "gear": sum(len(p.vertices) - 2 for o in gear for p in o.data.polygons)},
    }


def layout_of(template, size):
    """Which texels of a size x size picture the template's texture layout uses, and how many metres a texel is."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=template)
    obj = next(o for o in bpy.context.scene.objects if o.type == "MESH" and o.get("template"))
    me = obj.data
    me.calc_loop_triangles()
    uv = np.array([d.uv[:] for d in me.uv_layers.active.data]) * size
    used = np.zeros((size, size), bool)
    for lt in me.loop_triangles:
        t = uv[list(lt.loops)]
        x0, x1 = max(int(np.floor(t[:, 0].min())), 0), min(int(np.ceil(t[:, 0].max())), size - 1)
        y0, y1 = max(int(np.floor(t[:, 1].min())), 0), min(int(np.ceil(t[:, 1].max())), size - 1)
        d = (t[1, 1] - t[2, 1]) * (t[0, 0] - t[2, 0]) + (t[2, 0] - t[1, 0]) * (t[0, 1] - t[2, 1])
        if x1 < x0 or y1 < y0 or abs(d) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((t[1, 1] - t[2, 1]) * (gx - t[2, 0]) + (t[2, 0] - t[1, 0]) * (gy - t[2, 1])) / d
        w1 = ((t[2, 1] - t[0, 1]) * (gx - t[2, 0]) + (t[0, 0] - t[2, 0]) * (gy - t[2, 1])) / d
        used[y0:y1 + 1, x0:x1 + 1] |= (w0 >= -0.02) & (w1 >= -0.02) & (1 - w0 - w1 >= -0.02)
    area = sum(p.area for p in me.polygons)  # the template as it ships is 1.8 m tall: a person
    return used, (area / max(int(used.sum()), 1)) ** 0.5


def edge_length(mask, used):
    """How many texel sides lie between the garment and bare texels of the layout."""
    out = 0
    for axis in (0, 1):
        a, b = (mask[1:], mask[:-1]) if axis == 0 else (mask[:, 1:], mask[:, :-1])
        ua, ub = (used[1:], used[:-1]) if axis == 0 else (used[:, 1:], used[:, :-1])
        out += int(((a != b) & ua & ub).sum())
    return out


def box_sum(a, r):
    """Each cell's sum over the square of cells within r of it."""
    c = np.cumsum(np.cumsum(np.pad(a.astype(np.float64), ((r + 1, r), (r + 1, r))), 0), 1)
    n = 2 * r + 1
    return c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n]


def edges(template, paths):
    rows, layouts = [], {}
    for path in paths:
        image = bpy.data.images.load(path)
        size = image.size[0]
        px = np.empty(size * image.size[1] * 4, np.float32)
        image.pixels.foreach_get(px)
        alpha = px.reshape(image.size[1], size, 4)[..., 3]
        if size not in layouts:
            layouts[size] = layout_of(template, size)
        used, texel = layouts[size]
        mask = (alpha >= 0.5) & used
        r = max(2, int(round(0.01 * 1.8 / texel)))  # about 2 cm across on a person
        evened = (box_sum(mask, r) >= 0.5 * np.maximum(box_sum(used, r), 1)) & used
        # pieces: flood from each texel not yet seen
        seen, pieces = np.zeros_like(mask), []
        for y, x in zip(*np.nonzero(mask)):
            if seen[y, x]:
                continue
            stack, n = [(y, x)], 0
            seen[y, x] = True
            while stack:
                cy, cx = stack.pop()
                n += 1
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if 0 <= ny < mask.shape[0] and 0 <= nx < size and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            pieces.append(n)
        total = int(mask.sum())
        long, even = edge_length(mask, used), edge_length(evened, used)
        rows.append({"file": path, "texels": total, "edge_cm": round(100 * long * texel, 1), "evened_edge_cm": round(100 * even * texel, 1),
                     "ragged": round(long / max(even, 1), 3), "pieces": len(pieces), "scraps": sum(1 for n in pieces if n < 0.02 * total)})
    return rows


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    if args and args[0] == "--edges":
        for row in edges(os.path.abspath(args[1]), [os.path.abspath(a) for a in args[2:]]):
            print("EDGE " + json.dumps(row))
    else:
        for path in args:
            print("PAINT " + json.dumps(check(os.path.abspath(path))))
