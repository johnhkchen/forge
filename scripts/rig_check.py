"""Measure how well a character's skeleton fits its body, and how its skin holds up over a clip, in a background Blender.

    blender -b --factory-startup -P scripts/rig_check.py -- FILE.glb [FILE.glb ...]

FILE is a low-poly or mid-poly character with a skeleton and a clip
(profiles/lowpoly-walk.glb, midpoly-run.glb, lowpoly-hero.glb). For each file
it prints one line, `RIG {json}`:

- "joints": where each joint sits in the body around it. The body is cut
  straight across at the joint (level for the trunk, square to the bone for a
  limb) and the joint is measured from the middle of that cut, as a share of
  the cut's half size: 0 is dead center, 100 is on the skin. "@25" and "@60"
  are points a quarter and three fifths of the way along a bone, so a bone
  that leaves the middle of its limb shows too. "neck" is measured a quarter
  of the way up the neck bone, where the cut is the neck's own.
- "heights": the neck's base between the line of the shoulders (0) and the
  chin (1); the head's pivot between the chin (0) and the crown (1); how long
  the neck bone is, as a share of the height.
- "volume": per part of the body (trunk, neck, head, arm, leg...), how much
  its volume changes over the clip from standing in the T-pose: the least and
  most of the part as a whole, and the worst single piece. A trunk that loses
  a fifth of itself on every stride is what "something is squeezing it" looks
  like.
- "jitter": how much each part shakes: the part of its acceleration that
  changes from one frame to the next (its acceleration with a five-frame
  average taken off), in mm per frame squared, for skin points (the middle
  one and the 90th in a hundred) and for the head, hand, knee, ankle and ball
  of the foot. "knee_to_foot" is the knee's against the ball of the foot's: a
  knee is moved by its foot, so it should shake about as much, not twice.
- "knee_axis_swing_deg": the most a knee's hinge turns about the leg in one
  frame. A knee that points forward stays near 0 to 10; one flung out
  sideways for a frame reads 40 and more.

Nothing is written. scripts/test_tools.py reads these numbers.
"""
import json
import math
import os
import random
import sys

import bpy
from mathutils import Vector

REGIONS = {"hips": "trunk", "spine": "trunk", "chest": "trunk", "neck": "neck", "head": "head", "shoulder": "shoulder", "upper_arm": "arm", "forearm": "arm", "hand": "arm",
           "thigh": "leg", "shin": "leg", "foot": "leg", "toe": "leg"}
UP = Vector((0, 0, 1))


def region_of(bone):
    if bone.startswith("cloth"):
        return "cloth"
    if bone.startswith("tail"):
        return "tail"
    return REGIONS.get(bone[:-2] if bone.endswith(("_l", "_r")) else bone, "other")


def islands(faces):
    root = {}

    def find(a):
        while root.setdefault(a, a) != a:
            root[a] = root[root[a]]
            a = root[a]
        return a

    for f in faces:
        a = find(f[0])
        for v in f[1:]:
            b = find(v)
            if a != b:
                root[b] = a
    out = {}
    for f in faces:
        out.setdefault(find(f[0]), []).append(f)
    return list(out.values())


def volume(faces, points):
    ids = {i for f in faces for i in f}
    mid = sum((points[i] for i in ids), Vector()) / len(ids)
    total = 0.0
    for f in faces:
        a = points[f[0]] - mid
        for k in range(1, len(f) - 1):
            total += a.dot((points[f[k]] - mid).cross(points[f[k + 1]] - mid))
    return abs(total) / 6.0


def jitter(series, looped):
    """How much a point shakes: its acceleration less that acceleration's five-frame average, rms, in mm per frame squared."""
    n = len(series)
    if n < 8:
        return 0.0

    def at(i):
        return series[i % (n - 1)] if looped else series[min(max(i, 0), n - 1)]

    def acc(i):
        return at(i + 1) - 2 * at(i) + at(i - 1)

    total, count = 0.0, 0
    for i in (range(n - 1) if looped else range(3, n - 3)):
        mean = (acc(i - 2) + acc(i - 1) + acc(i) + acc(i + 1) + acc(i + 2)) / 5.0
        total += (acc(i) - mean).length_squared
        count += 1
    return 1000 * math.sqrt(total / max(count, 1))


def measure(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = 30
    bpy.ops.import_scene.gltf(filepath=path)
    scene = bpy.context.scene
    rig = next((o for o in scene.objects if o.type == "ARMATURE"), None)
    if rig is None:
        return {"file": path, "error": "no skeleton in the file"}
    action = rig.animation_data.action if rig.animation_data and rig.animation_data.action else None
    meshes = [o for o in scene.objects if o.type == "MESH" and o.find_armature() == rig]
    bones = rig.data.bones
    head = {b.name: rig.matrix_world @ b.head_local for b in bones}
    tail = {b.name: rig.matrix_world @ b.tail_local for b in bones}

    # ---- the body at rest, its points welded across the meshes it was split into ----
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    weld, where, owner, first_of, slot = {}, [], [], [], {}
    body_faces = []
    for o in meshes:
        is_body = (o.get("forge") or "body") not in ("gear", "prop") and not o.name.startswith("prop")
        names = [g.name for g in o.vertex_groups]
        for v in o.data.vertices:
            p = o.matrix_world @ v.co
            key = ("body" if is_body else o.name, round(p.x, 4), round(p.y, 4), round(p.z, 4))
            if key not in weld:
                weld[key] = len(where)
                where.append(p)
                owner.append(max([(g.weight, names[g.group]) for g in v.groups] or [(0.0, "")])[1])
                first_of.append((o.name, v.index))
            slot[(o.name, v.index)] = weld[key]
        if is_body:
            for poly in o.data.polygons:
                ids = [slot[(o.name, i)] for i in poly.vertices]
                if len(set(ids)) >= 3:
                    body_faces.append(ids)
    low, high = min(p.z for p in where), max(p.z for p in where)
    tall = high - low
    pieces = []
    for faces in islands(body_faces):
        ids = sorted({i for f in faces for i in f})
        votes = {}
        for i in ids:
            votes[region_of(owner[i])] = votes.get(region_of(owner[i]), 0) + 1
        pieces.append({"faces": faces, "ids": ids, "v0": volume(faces, where), "region": max(votes.items(), key=lambda kv: kv[1])[0],
                       "lo": [min(where[i][k] for i in ids) for k in range(3)], "hi": [max(where[i][k] for i in ids) for k in range(3)]})
    whole = sum(p["v0"] for p in pieces) or 1.0

    # ---- joints against the body's cross-sections ----
    def cuts(point, normal):
        n = normal.normalized()
        u = n.cross(Vector((0, 1, 0)))
        if u.length < 0.3:
            u = n.cross(Vector((1, 0, 0)))
        u.normalize()
        v = n.cross(u)
        out = []
        for piece in pieces:
            d = {i: (where[i] - point).dot(n) for i in piece["ids"]}
            root, hit = {}, {}

            def find(a):
                while root.setdefault(a, a) != a:
                    root[a] = root[root[a]]
                    a = root[a]
                return a

            for f in piece["faces"]:
                crossing = []
                for a, b in zip(f, f[1:] + f[:1]):
                    if (d[a] > 0) != (d[b] > 0):
                        k = (min(a, b), max(a, b))
                        if k not in hit:
                            hit[k] = where[a].lerp(where[b], d[a] / (d[a] - d[b]))
                        crossing.append(k)
                for a, b in zip(crossing, crossing[1:]):
                    ra, rb = find(a), find(b)
                    if ra != rb:
                        root[rb] = ra
            loops = {}
            for k in hit:
                loops.setdefault(find(k), []).append(hit[k])
            groups = [list(g) for g in loops.values()]
            merged = True
            while merged:  # a loop broken where two body meshes meet is one loop
                merged = False
                for i in range(len(groups)):
                    for j in range(i + 1, len(groups)):
                        if any((p - q).length < 0.006 for p in groups[i] for q in groups[j]):
                            groups[i] += groups.pop(j)
                            merged = True
                            break
                    if merged:
                        break
            for pts in groups:
                if len(pts) < 3:
                    continue
                us, vs = [(p - point).dot(u) for p in pts], [(p - point).dot(v) for p in pts]
                out.append({"cu": (min(us) + max(us)) / 2, "cv": (min(vs) + max(vs)) / 2, "hu": (max(us) - min(us)) / 2, "hv": (max(vs) - min(vs)) / 2})
        for loop in out:
            loop["area"] = loop["hu"] * loop["hv"]
        return out

    def off_center(point, normal, pick):
        loops = cuts(point, normal)
        if not loops:
            return None
        holds = [c for c in loops if abs(c["cu"]) <= 1.02 * c["hu"] and abs(c["cv"]) <= 1.02 * c["hv"]]
        if not holds:
            cut = min(loops, key=lambda c: math.hypot(c["cu"], c["cv"]))
        elif pick == "largest":
            cut = max(holds, key=lambda c: c["area"])
        else:
            big = max(c["area"] for c in holds)
            cut = min([c for c in holds if c["area"] >= 0.08 * big], key=lambda c: c["area"])
        return {"off_%": round(100 * max(abs(cut["cu"]) / max(cut["hu"], 1e-6), abs(cut["cv"]) / max(cut["hv"], 1e-6)), 1), "inside": bool(holds),
                "half_cm": [round(100 * cut["hu"], 1), round(100 * cut["hv"], 1)]}

    joints = {}
    if all(n in head for n in ("hips", "spine", "chest", "neck", "head")):
        for name in ("hips", "spine", "chest"):
            joints[name] = off_center(head[name], UP, "largest")
        joints["neck"] = off_center(head["neck"].lerp(head["head"], 0.25), UP, "smallest")
        joints["head"] = off_center(head["head"], UP, "largest")
    for name in ("upper_arm_l", "forearm_l", "hand_l", "thigh_l", "shin_l", "foot_l"):
        if name not in head:
            continue
        along = tail[name] - head[name]
        for share, tag in ((0.0, ""), (0.25, "@25"), (0.6, "@60")):
            if share == 0.0 and name in ("upper_arm_l", "thigh_l", "foot_l"):
                continue  # the shoulder and hip joints sit inside the trunk: the limb's own cut starts a little way along
            joints[name + tag] = off_center(head[name] + along * share, along, "smallest")
    heights = {}
    body_names = {o.name for o in meshes if (o.get("forge") or "body") not in ("gear", "prop")}
    of_head = [where[i] for i in range(len(where)) if owner[i] == "head" and first_of[i][0] in body_names]
    if of_head and "upper_arm_l" in head and "neck" in head:
        chin, crown, shoulders = min(p.z for p in of_head), max(p.z for p in of_head), head["upper_arm_l"].z
        heights = {"neck_base_between_shoulders_and_chin": round((head["neck"].z - shoulders) / (chin - shoulders), 2) if chin - shoulders > 0.01 * tall else None,
                   "head_pivot_between_chin_and_crown": round((head["head"].z - chin) / max(crown - chin, 1e-6), 2),
                   "neck_long_%": round(100 * (head["head"] - head["neck"]).length / tall, 1),
                   "shoulder_line_%": round(100 * (shoulders - low) / tall, 1), "neck_base_%": round(100 * (head["neck"].z - low) / tall, 1),
                   "head_pivot_%": round(100 * (head["head"].z - low) / tall, 1), "chin_%": round(100 * (chin - low) / tall, 1)}
    out = {"file": path, "height": round(tall, 3), "joints": joints, "heights": heights}
    rig.data.pose_position = "POSE"
    if action is None:
        return out

    # ---- over the clip: volume, and how much things shake ----
    first, last = [int(round(f)) for f in action.frame_range]
    frames = list(range(first, last + 1))
    random.seed(1)
    by_region = {}
    for i in range(len(where)):
        by_region.setdefault(region_of(owner[i]), []).append(i)
    samples = {r: random.sample(ids, min(len(ids), 120)) for r, ids in by_region.items() if r != "other"}
    tracks = {r: [] for r in samples}
    watch = {"head": ("head", True), "hand": ("hand_l", False), "knee": ("shin_l", False), "ankle": ("foot_l", False), "ball_of_foot": ("toe_l", False),
             "knee_r": ("shin_r", False), "ball_of_foot_r": ("toe_r", False)}
    watch = {k: v for k, v in watch.items() if v[0] in head}
    spots = {k: [] for k in watch}
    volumes = [[] for _ in pieces]
    hinge = {"l": [], "r": []}
    pose_first, seam = {}, 0.0
    for f in frames:
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
        shown = rig.evaluated_get(deps)
        for k, (bone, at_tail) in watch.items():
            spots[k].append(shown.matrix_world @ (shown.pose.bones[bone].tail if at_tail else shown.pose.bones[bone].head))
        for tag in ("l", "r"):
            if "thigh_" + tag in head:
                turned = (shown.matrix_world @ shown.pose.bones["thigh_" + tag].matrix).to_3x3()
                hips = (shown.matrix_world @ shown.pose.bones["hips"].matrix).to_3x3().inverted()
                hinge[tag].append((hips @ turned.col[0], hips @ turned.col[1]))  # the knee's axis and the thigh's line, as the hips see them
        now = [None] * len(where)
        for o in meshes:
            me = o.evaluated_get(deps).to_mesh()
            for v in me.vertices:
                s = slot.get((o.name, v.index))
                if s is not None and first_of[s] == (o.name, v.index):
                    now[s] = o.matrix_world @ v.co
            o.evaluated_get(deps).to_mesh_clear()
        for r, ids in samples.items():
            tracks[r].append([now[i] for i in ids])
        for k, piece in enumerate(pieces):
            if piece["v0"] > 0.002 * whole:
                volumes[k].append(volume(piece["faces"], now))
        pose = {b.name: list(b.rotation_quaternion) + list(b.location) for b in rig.pose.bones}
        if f == first:
            pose_first = pose
        elif f == last:
            seam = max(abs(a - b) for name in pose for a, b in zip(pose[name], pose_first[name]))
    scene.frame_set(first)
    looped = seam < 1e-4
    vol = {}
    for k, piece in enumerate(pieces):
        if not volumes[k]:
            continue
        part = vol.setdefault(piece["region"], {"v0": 0.0, "sum": [0.0] * len(frames), "worst_piece_%": 0.0})
        part["v0"] += piece["v0"]
        part["sum"] = [a + b for a, b in zip(part["sum"], volumes[k])]
        part["worst_piece_%"] = min(part["worst_piece_%"], round(100 * (min(volumes[k]) / piece["v0"] - 1), 1))
    for part in vol.values():
        total = part.pop("sum")
        part["least_%"], part["most_%"] = round(100 * (min(total) / part["v0"] - 1), 1), round(100 * (max(total) / part["v0"] - 1), 1)
        part["v0"] = round(part["v0"], 4)
    shake = {"skin": {}, "points": {k: round(jitter(v, looped), 2) for k, v in spots.items()}}
    for r, rows in tracks.items():
        each = sorted(jitter([row[j] for row in rows], looped) for j in range(len(rows[0])))
        shake["skin"][r] = {"middle": round(each[len(each) // 2], 2), "p90": round(each[int(0.9 * (len(each) - 1))], 2)}
    ratios = [shake["points"][a] / max(shake["points"][b], 1e-6) for a, b in (("knee", "ball_of_foot"), ("knee_r", "ball_of_foot_r")) if a in shake["points"]]
    if ratios:
        shake["knee_to_foot"] = round(max(ratios), 2)
    swing = 0.0
    for tag in ("l", "r"):
        rows = hinge[tag]
        for (a, along), (b, _) in zip(rows, rows[1:] + (rows[:1] if looped else [])):
            # how far the hinge turned about the thigh's own line between two frames (the thigh swinging fore and aft doesn't count)
            a2, b2 = a - along * a.dot(along), b - along * b.dot(along)
            if a2.length > 1e-6 and b2.length > 1e-6:
                swing = max(swing, math.degrees(a2.angle(b2)))
    out.update({"clip": action.name, "frames": len(frames) - 1, "looped": looped, "volume": vol, "jitter": shake, "knee_axis_swing_deg": round(swing, 1)})
    return out


for path in sys.argv[sys.argv.index("--") + 1:]:
    got = measure(os.path.abspath(path))
    print("RIG " + json.dumps(got))
