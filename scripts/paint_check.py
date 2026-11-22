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

Nothing is written. scripts/test_tools.py reads these numbers.
"""
import json
import os
import sys

import bpy
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


if __name__ == "__main__":
    for path in sys.argv[sys.argv.index("--") + 1:]:
        print("PAINT " + json.dumps(check(os.path.abspath(path))))
