"""Measure how a dressed character's clothes sit and move, in a background Blender.

    blender -b --factory-startup -P scripts/cloth_check.py -- FILE.glb [FILE.glb ...]

FILE is a low-poly or mid-poly character with its gear as separate meshes
("body", "gear: ..."), standing (profiles/lowpoly.glb) or with a skeleton
and a clip (profiles/lowpoly-walk.glb, lowpoly-hero.glb). For each file it
prints one line, `CLOTH {json}`:

- "poke_through": body points that worn gear covers while standing still
  (cloth straight out from the point, and the nearest cloth lying that way
  too: a knee just below a hem doesn't count),
  followed through every frame of the clip. One counts as poking through on
  a frame when the cloth that should be over it is behind it instead (within
  3% of the height, and facing the same way: it came out through that
  cloth). "through" says which gear. Given
  as how many point-frames, their share of all covered point-frames, and the
  deepest, in cm. Body meshes the file marks as hidden under gear ("body
  under: ...") are not drawn while the gear is on, so they can't poke
  through; "if_all_were_drawn" counts them anyway, to show what hiding them
  is worth.
- "gap_cm": per gear mesh, how far its points stand off the body while
  standing still: the middle one, the 95th in a hundred, and how many are
  inside the body.
- "cloth_bones": the loose-cloth bones in the file, how far they swing, and
  how deep any of their joints goes into a leg (a rod from hip to knee or
  knee to ankle, as thick as the leg is at rest).
- "triangles": drawn with everything on, and in the file altogether.

Nothing is written. scripts/test_tools.py reads these numbers.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


WELDS = {}  # object name -> (which spot each point is, how many spots)


def spots_of(obj):
    """A .glb splits a point wherever the texture layout has a seam (or the shading is flat), and the copies
    move together. They are one spot of the surface: each copy is mapped to the first point at its place, so a
    spot counts once and its normal comes from the faces on both sides of the seam. Otherwise the same mesh
    measured differently once it had been baked (Roosevelt's routine: 444 point-frames before the bake, 501
    after, with every point moving exactly the same)."""
    if obj.name not in WELDS:
        places = [obj.matrix_world @ v.co for v in obj.data.vertices]
        tree = KDTree(len(places))
        for i, p in enumerate(places):
            tree.insert(p, i)
        tree.balance()
        spot, count = [-1] * len(places), 0
        for i, p in enumerate(places):  # within 0.1 mm is one spot: the copies can come back a few hundredths of a mm apart
            if spot[i] >= 0:
                continue
            for co, j, d in tree.find_range(p, 1e-4):
                if spot[j] < 0:
                    spot[j] = count
            spot[i] = count
            count += 1
        WELDS[obj.name] = (spot, count)
    return WELDS[obj.name]


def posed(objects, deps):
    """Every spot and face of the objects as shown on this frame, split copies of a point taken as one spot
    (spots_of): (points, normals, faces, which object each point is of)."""
    points, normals, faces, owner = [], [], [], []
    for index, obj in enumerate(objects):
        spot, count = spots_of(obj)
        shown = obj.evaluated_get(deps)
        me = shown.to_mesh()
        start = len(points)
        world = shown.matrix_world
        here = [None] * count
        for i, v in enumerate(me.vertices):
            if here[spot[i]] is None:
                here[spot[i]] = world @ v.co
        lean = [Vector() for _ in range(count)]
        for p in me.polygons:
            corners = [spot[i] for i in p.vertices]
            a = here[corners[0]]
            n = Vector()
            for k in range(1, len(corners) - 1):  # the face's normal, as long as twice its area
                n += (here[corners[k]] - a).cross(here[corners[k + 1]] - a)
            for c in set(corners):
                lean[c] += n
            faces.append(tuple(start + c for c in corners))
        points += here
        normals += [n.normalized() if n.length > 1e-12 else Vector((0, 0, 1)) for n in lean]
        owner += [index] * count
        shown.to_mesh_clear()
    return points, normals, faces, owner


def poke_over(body, gear, rig, frames, every=1):
    """Skin through clothes over some frames of the rig's action, for meshes already in the scene: body meshes
    tagged "under" (hidden while dressed) count only toward "all". Standing still (the rig at rest) decides which
    body points the gear covers. Returns {"drawn": [point-frames, deepest m], "all": [...], "covered", "covered_drawn",
    "worst_frame", "through": {gear: point-frames}, "tall", "frames"}."""
    WELDS.clear()  # a new scene may reuse the names
    scene = bpy.context.scene
    if rig:
        rig.data.pose_position = "REST"
    scene.frame_set(frames[0] if frames else 0)
    deps = bpy.context.evaluated_depsgraph_get()
    points, normals, faces, owner = posed(body, deps)
    gpoints, gnormals, gfaces, gowner = posed(gear, deps)
    tall = max(p.z for p in points) - min(p.z for p in points)
    reach = 0.04 * tall
    cloth = BVHTree.FromPolygons(gpoints, gfaces)
    covered = [i for i, (p, n) in enumerate(zip(points, normals)) if under_cloth(cloth, p, n, reach)]
    drawn = [not body[owner[i]].get("under") for i in range(len(points))]
    if rig:
        rig.data.pose_position = "POSE"
    poke = {"drawn": [0, 0.0], "all": [0, 0.0]}
    worst_frame, most, through = None, 0, {}
    face_gear = []
    for obj in gear:
        face_gear += [obj.get("gear") or obj.name] * len(obj.data.polygons)
    looked = frames[::max(1, int(every))]
    for f in looked:
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
        points, normals, faces, owner = posed(body, deps)
        gpoints, gnormals, gfaces, gowner = posed(gear, deps)
        cloth = BVHTree.FromPolygons(gpoints, gfaces)
        here = 0
        for i in covered:
            p, n = points[i], normals[i]
            if cloth.ray_cast(p + n * 1e-4, n, reach)[0] is not None:
                continue
            behind = cloth.ray_cast(p - n * 1e-4, -n, 0.03 * tall)
            if behind[0] is None or behind[3] < 0.001 or behind[1].dot(n) < 0.2:  # the far wall of a sleeve faces the other way: not it
                continue
            for key in (("drawn", "all") if drawn[i] else ("all",)):
                poke[key][0] += 1
                poke[key][1] = max(poke[key][1], behind[3])
            here += drawn[i]
            if drawn[i]:
                through[face_gear[behind[2]]] = through.get(face_gear[behind[2]], 0) + 1
        if here > most:
            worst_frame, most = f, here
    return {"drawn": poke["drawn"], "all": poke["all"], "covered": len(covered), "covered_drawn": sum(1 for i in covered if drawn[i]),
            "worst_frame": worst_frame, "through": through, "tall": tall, "frames": len(looked)}


def check(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    WELDS.clear()
    bpy.context.scene.render.fps = 30  # what every motion here is baked at; the importer lays keys out by the scene's rate
    bpy.ops.import_scene.gltf(filepath=path)
    scene = bpy.context.scene
    meshes = [o for o in scene.objects if o.type == "MESH"]
    body = [o for o in meshes if o.get("forge") == "body"]
    gear = [o for o in meshes if o.get("forge") == "gear"]
    if not body or not gear:
        return {"file": path, "skipped": "no separate body and gear meshes"}
    rig = next((o for o in scene.objects if o.type == "ARMATURE"), None)
    action = rig.animation_data.action if rig and rig.animation_data else None
    frames = list(range(int(round(action.frame_range[0])), int(round(action.frame_range[1])))) if action else []

    # Standing still: what the gear covers, and how far off the body it sits.
    if rig:
        rig.data.pose_position = "REST"
    scene.frame_set(0)
    deps = bpy.context.evaluated_depsgraph_get()
    points, normals, faces, owner = posed(body, deps)
    gpoints, gnormals, gfaces, gowner = posed(gear, deps)
    tall = max(p.z for p in points) - min(p.z for p in points)
    reach = 0.04 * tall
    cloth = BVHTree.FromPolygons(gpoints, gfaces)
    skin = BVHTree.FromPolygons(points, faces)
    gaps = {}
    for index, obj in enumerate(gear):
        off, inside = [], 0
        for p, n, o in zip(gpoints, gnormals, gowner):
            if o != index:
                continue
            hit = skin.find_nearest(p)
            off.append(hit[3])
            out = skin.ray_cast(p, n, 0.03 * tall)
            inside += bool(out[0] is not None and out[1].dot(n) > 0)
        off.sort()
        gaps[obj.get("gear") or obj.name] = {"median": round(100 * off[len(off) // 2], 2), "p95": round(100 * off[int(0.95 * (len(off) - 1))], 2),
                                             "inside_the_body": inside, "points": len(off)}

    # Moving: is the cloth still over each covered point, or behind it?
    moving = poke_over(body, gear, rig, frames)
    poke, worst_frame, through = {"drawn": moving["drawn"], "all": moving["all"]}, moving["worst_frame"], moving["through"]
    total = max(moving["covered"] * len(frames), 1)
    seen = max(moving["covered_drawn"] * len(frames), 1)

    # Loose-cloth bones: how far they swing, and whether a joint goes into a leg.
    bones = [b.name for b in rig.data.bones if b.name.startswith("cloth_")] if rig else []
    swing = {"bones": len(bones), "chains": len({b.rsplit("_", 1)[0] for b in bones})}
    if bones and frames:
        rest = {b.name: (b.head_local.copy(), b.tail_local.copy()) for b in rig.data.bones}
        rods = [r for r in ("thigh_l", "thigh_r", "shin_l", "shin_r") if r in rest]
        room = {}
        for name in bones:
            for rod in rods:
                room[(name, rod)] = off_rod(rest[rod][0], rest[rod][1], rest[name][1])
        deepest, most_swing, lows, highs = 0.0, 0.0, {}, {}
        for f in frames:
            scene.frame_set(f)
            for name in bones:
                bone = rig.pose.bones[name]
                most_swing = max(most_swing, math.degrees(bone.matrix_basis.to_quaternion().angle))
                for rod in rods:
                    thick = min(room[(name, rod)], 0.06 * tall)  # at rest the joint was this far from the leg's middle line
                    now = off_rod(rig.pose.bones[rod].head, rig.pose.bones[rod].tail, bone.tail)
                    deepest = max(deepest, min(thick, 0.045 * tall) - now)
                at = rig.pose.bones["hips"].matrix.inverted() @ bone.tail
                lows[name] = at.copy() if name not in lows else Vector([min(lows[name][k], at[k]) for k in range(3)])
                highs[name] = at.copy() if name not in highs else Vector([max(highs[name][k], at[k]) for k in range(3)])
        swing.update({"most_swing_deg": round(most_swing, 1), "deepest_in_a_leg_cm": round(100 * max(deepest, 0.0), 2),
                      "most_travel_cm": round(100 * max((highs[n] - lows[n]).length for n in bones), 1)})

    def triangles(objects):
        return sum(len(p.vertices) - 2 for o in objects for p in o.data.polygons)

    return {
        "file": path, "height": round(tall, 3), "frames": len(frames), "clip": action.name if action else None,
        "body_meshes": sorted(o.name for o in body), "gear_meshes": sorted(o.name for o in gear),
        "covered_points": moving["covered"], "covered_points_drawn": moving["covered_drawn"],
        "poke_through": {"point_frames": poke["drawn"][0], "share_%": round(100 * poke["drawn"][0] / seen, 3), "deepest_cm": round(100 * poke["drawn"][1], 2),
                         "worst_frame": worst_frame, "through": through,
                         "if_all_were_drawn": {"point_frames": poke["all"][0], "share_%": round(100 * poke["all"][0] / total, 3), "deepest_cm": round(100 * poke["all"][1], 2)}},
        "gap_cm": gaps, "cloth_bones": swing,
        "triangles": {"drawn_dressed": triangles([o for o in meshes if not o.get("under")]), "in_the_file": triangles(meshes),
                      "body_hidden_when_dressed": triangles([o for o in body if o.get("under")])},
    }


def under_cloth(cloth, p, n, reach):
    """Is this body point properly under cloth: cloth straight out from it, and the nearest cloth is that way too
    (a knee just below a hem has cloth above it, not over it)."""
    if cloth.ray_cast(p + n * 1e-4, n, reach)[0] is None:
        return False
    near = cloth.find_nearest(p)
    return near[0] is not None and (near[3] < 1e-5 or (near[0] - p).normalized().dot(n) > 0.7)


def off_rod(a, b, p):
    """How far `p` is from the segment a-b."""
    ab = b - a
    t = min(1.0, max(0.0, (p - a).dot(ab) / max(ab.length_squared, 1e-12)))
    return (p - (a + ab * t)).length


if __name__ == "__main__":  # imported by tidy_profile.py for poke_over
    for path in sys.argv[sys.argv.index("--") + 1:]:
        print("CLOTH " + json.dumps(check(os.path.abspath(path))))
