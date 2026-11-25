"""Do her legs stay under her skirt, and her hem off the floor? A take played through, every frame, and measured.

    Blender -b --factory-startup -P scripts/impostor/judge_legs.py -- [--take groove-flamenco] [--shots shots]
        [--glb <a take's .glb>,...] [--out evidence/unclip] [--tag after] [--every 1] [--fps 30] [--worst 6]

A skirt hangs on chains of swing bones (cloth.py names them cloth_<gear>_<chain>_<n>) and the legs move under it.
Where the chains do not keep clear of the legs, a thigh or a shin comes out through the front of the cloth; where
the hips drop low, the hem goes into the floor. This plays each of a take's films (the .glb the cast made, posed by
its own action: exactly what Blender films, and what the watch page and the cards' dress piece play) and on every
frame, with the skin as the bones bend it:

    into the skirt    how deep the skirt goes into a leg: for every point of the skirt (its corners and the middle
                      of each face), the nearest place on the skin of a thigh or a shin (the skin the skirt hides
                      among it: it is still leg); if the point is on the inside of the skin there, the leg has come
                      through the cloth by that much. A leg out under a hem that is flung up is not in the skirt
    floor             how far the lowest point of the skirt is below the floor (the rig's own floor)
    swing             how far the chains' top bones turn from how they hang at rest (so a fix that stiffens the
                      skirt shows), and how much the hem shakes: the mean, over its points and frames, of how far
                      each is from the middle of where it was the frame before and will be the frame after (mm)

A frame clips when the skirt is more than CLIP_CM into a leg. Writes <out>/legs[-tag].json (each frame's numbers,
and the sums) and prints a line for each film. Any garment whose chains hang from the hips or the spine is a skirt
here, whatever it is called (a tunic, a robe, a coat's tails); a character with none is said to have no skirt.
Never touches an open Blender.
"""

import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

CLIP_CM = 0.5        # a frame clips when the skirt is more than this far into a leg
DEEP_M = 0.12        # a point of the skirt further than this from a leg's skin is not in it (no thigh is that thick)
ANKLE = 0.85         # a shin counts down to here: below is the ankle, in a stiff shoe, and a hem lying on a shoe is not a leg through the skirt
LEGS = ("thigh_l", "thigh_r", "shin_l", "shin_r")
HUNG_FROM = ("hips", "spine")  # a skirt's chains hang from these (a hood's hang from the head)


def skirt_chains(rig):
    """[(parent, [bones top down])] of the chains that hang over the legs, from the rig's own note, or by name."""
    known = json.loads(rig.get("forge_cloth", "{}")).get("chains", [])
    if known:
        return [(c["parent"], c["bones"]) for c in known if c["parent"] in HUNG_FROM and all(b in rig.data.bones for b in c["bones"])]
    chains = []
    for bone in rig.data.bones:
        if bone.name.startswith("cloth_") and bone.parent is not None and bone.parent.name in HUNG_FROM:
            chain, at = [bone.name], bone
            while at.children:
                at = at.children[0]
                chain.append(at.name)
            chains.append((bone.parent.name, chain))
    return sorted(chains, key=lambda c: c[1][0])


def welded(points, within=1e-4):
    """Which place each point is: a .glb splits a point at every seam of the texture layout."""
    from mathutils.kdtree import KDTree
    tree = KDTree(len(points))
    for i, p in enumerate(points):
        tree.insert(p, i)
    tree.balance()
    place, count = [-1] * len(points), 0
    for i, p in enumerate(points):
        if place[i] >= 0:
            continue
        for _, j, _ in tree.find_range(p, within):
            if place[j] < 0:
                place[j] = count
        place[i] = count
        count += 1
    return place


def open_points(obj):
    """The skirt's points on an open edge (its hem and its waistband)."""
    place = welded([v.co.copy() for v in obj.data.vertices])
    count = {}
    for poly in obj.data.polygons:
        ring = list(poly.vertices)
        for i in range(len(ring)):
            key = tuple(sorted((place[ring[i - 1]], place[ring[i]])))
            count[key] = count.get(key, 0) + 1
    rim = {p for key, n in count.items() if n == 1 for p in key}
    return np.array([i for i in range(len(place)) if place[i] in rim], dtype=np.int64)


def coords(obj, graph):
    """An object's points as the bones bend it, in the world."""
    held = obj.evaluated_get(graph)
    mesh = held.to_mesh()
    out = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", out)
    held.to_mesh_clear()
    m = np.array(obj.matrix_world)
    return out.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]


def triangles(obj, keep=None):
    """An object's faces as triangles (only those whose corners all pass `keep`)."""
    out = []
    for poly in obj.data.polygons:
        ring = list(poly.vertices)
        if keep is None or all(keep[i] for i in ring):
            out += [(ring[0], ring[k], ring[k + 1]) for k in range(1, len(ring) - 1)]
    return np.array(out, dtype=np.int64).reshape(-1, 3)


def shake_of(tracks):
    """How much points shake: [frames, points, 3] -> the mean distance from the middle of the frames either side (m)."""
    if len(tracks) < 3:
        return 0.0
    return float(np.linalg.norm(tracks[1:-1] - 0.5 * (tracks[2:] + tracks[:-2]), axis=2).mean())


def nearest_on(segments, points):
    """For each point, the nearest of the segments [(a, b)]: (which, how far along it 0-1, the point on it, how far)."""
    best_k = np.zeros(len(points), dtype=np.int64)
    best_t, best_d = np.zeros(len(points)), np.full(len(points), np.inf)
    best_at = np.zeros_like(points)
    for k, (a, b) in enumerate(segments):
        ab = np.asarray(b, dtype=float) - np.asarray(a, dtype=float)
        t = np.clip((points - a) @ ab / max(float(ab @ ab), 1e-12), 0.0, 1.0)
        at = a + t[:, None] * ab
        d = np.linalg.norm(points - at, axis=1)
        better = d < best_d
        best_k[better], best_t[better], best_d[better], best_at[better] = k, t[better], d[better], at[better]
    return best_k, best_t, best_at, best_d


def depth_in_legs(points, segments, cast, reach=DEEP_M, cap=None, upto=None):
    """How deep each point is inside a leg: from the nearest place on the nearest leg's bone, a ray out through the
    point finds the leg's skin (`cast(origin, way, far, segment)` -> how far it is, or None: its own skin only); a point nearer the bone than
    the skin is inside by the difference. A ray from inside a limb meets its own skin first, so this holds where
    the skin has holes or is turned in places, as a nearest face's facing does not. Where a bent knee pinches the
    skin a ray can slip out through the fold: `cap(segment, along, way)`, if given, is the most the leg is thick
    there (from how it was made), and the skin is never further than that. -> (depth m, which segment)."""
    which, along, at, far = nearest_on(segments, points)
    deep = np.zeros(len(points))
    counted = far < reach if upto is None else (far < reach) & (along <= np.asarray(upto)[which])
    for i in np.nonzero(counted)[0]:
        if far[i] < 1e-6:
            continue
        way = (points[i] - at[i]) / far[i]
        most = cap(which[i], along[i], way) if cap else 2.0 * reach
        skin = cast(at[i], way, most, which[i])
        skin = most if (skin is None and cap) else skin
        if skin is not None and min(skin, most) > far[i]:
            deep[i] = min(skin, most) - far[i]
    return deep, which


def out_through(line, cast, step=1e-4):
    """How much of a leg's middle line has gone out through the cloth: walking the line (points, from the hip down),
    every time it crosses the cloth (`cast(origin, way, far)` -> how far the next crossing is, or None) it goes from
    inside to outside or back. A leg that goes out under the hem never crosses it. -> metres of the line outside."""
    out, outside = 0.0, False
    for a, b in zip(line[:-1], line[1:]):
        a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
        length = float(np.linalg.norm(b - a))
        if length < 1e-9:
            continue
        way, gone = (b - a) / length, 0.0
        while gone < length:
            hit = cast(a + way * gone, way, length - gone)
            upto = length if hit is None else min(length, gone + hit)
            if outside:
                out += upto - gone
            if hit is None:
                break
            outside = not outside
            gone = upto + step
    return out


def profile_of(cast, head, tail, x_axis, z_axis, steps=11, around=16, far=0.2):
    """How thick a leg is round its bone, as it was made: rays out from the bone at `steps` places along it and
    `around` ways round it (in the bone's own x and z) -> [steps, around] (m; 0 where a ray found nothing)."""
    out = np.zeros((steps, around))
    for s in range(steps):
        origin = head + (tail - head) * (s / (steps - 1.0))
        for k in range(around):
            angle = 2.0 * math.pi * k / around
            hit = cast(origin, math.cos(angle) * x_axis + math.sin(angle) * z_axis, far)
            out[s, k] = hit or 0.0
    return out


def thickness(profile, along, x, z, slack=1.2, plus=0.01):
    """The most a leg is thick at `along` (0-1) the way (x, z) in its bone's frame, from its profile, with slack."""
    steps, around = profile.shape
    s = min(max(along, 0.0), 1.0) * (steps - 1)
    a = (math.atan2(z, x) % (2.0 * math.pi)) / (2.0 * math.pi) * around
    s0, a0 = int(min(s, steps - 2)), int(a) % around
    fs, fa = s - s0, a - int(a)
    near = [profile[s0, a0], profile[s0, (a0 + 1) % around], profile[s0 + 1, a0], profile[s0 + 1, (a0 + 1) % around]]
    value = (near[0] * (1 - fa) + near[1] * fa) * (1 - fs) + (near[2] * (1 - fa) + near[3] * fa) * fs
    return slack * value + plus


def judge_film(glb, fps=30, every=1, worst=6):
    """One take's .glb played through: the numbers for every frame, and the sums."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = fps
    bpy.ops.import_scene.gltf(filepath=glb)
    rig = next(o for o in scene.objects if o.type == "ARMATURE")
    chains = skirt_chains(rig)
    report = {"glb": glb, "chains": len(chains)}
    if not chains:
        report["skirt"] = None
        return report
    chain_bones = {b for _, bones in chains for b in bones}
    meshes = [o for o in scene.objects if o.type == "MESH" and o.find_armature() == rig]
    def swung(obj):  # a garment the chains really pull on (a .glb gives every mesh a group for every bone, most of them empty)
        ids = {g.index for g in obj.vertex_groups if g.name in chain_bones}
        return any(g.group in ids and g.weight > 0.05 for v in obj.data.vertices for g in v.groups)
    skirts = [o for o in meshes if o.get("forge") == "gear" and swung(o)]
    bodies = [o for o in meshes if o.get("forge") != "gear"]
    report["skirt"] = [o.name for o in skirts]
    floor = float(json.loads(rig.get("forge_rig", "{}")).get("measure", {}).get("floor", 0.0))
    legs = [name for name in LEGS if name in rig.pose.bones]
    body_faces, face_side = [], []
    for obj in bodies:  # which leg each face of the body is (the thigh, shin and foot a side's): a ray from a leg counts only its own skin
        tris = triangles(obj)
        names = {g.index: g.name for g in obj.vertex_groups}
        lean = np.zeros(len(obj.data.vertices))
        for v in obj.data.vertices:
            for g in v.groups:
                name = names.get(g.group, "")
                if name.split("_")[0] in ("thigh", "shin", "foot", "toe"):
                    lean[v.index] += g.weight if name.endswith("_l") else -g.weight if name.endswith("_r") else 0.0
        side = lean[tris].sum(axis=1) if len(tris) else np.zeros(0)
        face_side += ["l" if s > 0.5 else "r" if s < -0.5 else "" for s in side]
        body_faces.append((obj, tris))
    shape = [(obj, triangles(obj), open_points(obj)) for obj in skirts]
    action = rig.animation_data.action
    first, last = (int(round(x)) for x in action.frame_range)
    frames = list(range(first, last + 1, max(1, int(every))))
    rest_tops = {bones[0]: (rig.data.bones[parent].matrix_local.inverted() @ rig.data.bones[bones[0]].matrix_local).to_quaternion() for parent, bones in chains}

    profiles = {}

    def stood():
        """The skirt's points (its corners and the middle of each face), its open edges' points, and how deep each
        point is in a leg, as the scene stands now. The first call (at rest) also takes each leg's profile."""
        graph = bpy.context.evaluated_depsgraph_get()
        samples, rims, cloth, cloth_faces, start = [], [], [], [], 0
        for obj, tris, rim in shape:
            p = coords(obj, graph)
            samples += [p, p[tris].mean(axis=1)]
            rims.append(p[rim])
            cloth.append(p)
            cloth_faces.append(tris + start)
            start += len(p)
        samples = np.concatenate(samples)
        sheet = BVHTree.FromPolygons([Vector(p) for p in np.concatenate(cloth)], np.concatenate(cloth_faces).tolist())
        world = rig.matrix_world
        through = {}
        for side in ("l", "r"):  # each leg's middle line, hip to knee to just above the ankle: does it go out through the cloth?
            thigh, shin = rig.pose.bones.get("thigh_" + side), rig.pose.bones.get("shin_" + side)
            if thigh is None or shin is None:
                continue
            line = [np.array(world @ thigh.head), np.array(world @ thigh.tail), np.array(world @ (shin.head + (shin.tail - shin.head) * ANKLE))]
            through[side] = out_through(line, lambda o, w, d: sheet.ray_cast(Vector(o), Vector(w), d)[3])
        points, faces, start = [], [], 0
        for obj, tris in body_faces:
            p = coords(obj, graph)
            points.append(p)
            faces.append(tris + start)
            start += len(p)
        tree = BVHTree.FromPolygons([Vector(p) for p in np.concatenate(points)], np.concatenate(faces).tolist())

        def cast(origin, way, far, k, own=False):
            hit = tree.ray_cast(Vector(origin), Vector(way), far)
            if hit[3] is None or (own and face_side[hit[2]] not in (legs[k][-1], "")):
                return None  # (a leg's profile is taken from its own skin, never the other leg's)
            return hit[3]
        frames = [world @ rig.pose.bones[n].matrix for n in legs]
        segments = [(np.array(world @ rig.pose.bones[n].head), np.array(world @ rig.pose.bones[n].tail)) for n in legs]
        axes = [(np.array(m.to_3x3().normalized().col[0]), np.array(m.to_3x3().normalized().col[2])) for m in frames]
        if not profiles:
            for k, n in enumerate(legs):
                profiles[k] = profile_of(lambda o, w, d: cast(o, w, d, k, own=True), segments[k][0], segments[k][1], axes[k][0], axes[k][1])

        def cap(k, along, way):
            return thickness(profiles[k], along, float(way @ axes[k][0]), float(way @ axes[k][1]))
        deep, which = depth_in_legs(samples, segments, cast, cap=cap, upto=[ANKLE if n.startswith("shin") else 1.0 for n in legs])
        return samples, np.concatenate(rims), deep, which, through

    # how deep each point of the skirt is in a leg as it was made (cloth that rests on a thigh is not through it)
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    _, _, at_rest, _, out_at_rest = stood()
    rig.data.pose_position = "POSE"
    rows, hems = [], []
    for f in frames:
        scene.frame_set(f)
        samples, rim, deep, which, through = stood()
        out_cm = {side: round(100.0 * max(0.0, through[side] - out_at_rest.get(side, 0.0)), 2) for side in through}
        hems.append(rim)
        low = float(samples[:, 2].min())
        past = deep - at_rest
        k = int(np.argmax(past))
        deepest, where = max(0.0, float(past[k])), (legs[which[k]] if past[k] > 0 else None)
        swing = 0.0
        for parent, bones in chains:
            now = (rig.pose.bones[parent].matrix.inverted() @ rig.pose.bones[bones[0]].matrix).to_quaternion()
            angle = rest_tops[bones[0]].rotation_difference(now).angle
            swing = max(swing, math.degrees(min(angle, 2 * math.pi - angle)))
        rows.append({"frame": f, "seconds": round((f - first) / float(fps), 3), "into_cm": round(100.0 * deepest, 2), "leg": where, "at": [round(float(x), 3) for x in samples[k]],
                     "out_cm": max(out_cm.values() or [0.0]), "out_leg": max(out_cm, key=out_cm.get) if out_cm and max(out_cm.values()) > 0 else None,
                     "floor_dip_cm": round(max(0.0, 100.0 * (floor - low)), 2), "swing_deg": round(swing, 1)})
    into = np.array([r["into_cm"] for r in rows])
    dip = np.array([r["floor_dip_cm"] for r in rows])
    order = np.argsort(-into, kind="stable")[:worst]
    report.update({
        "frames": len(rows), "fps": fps, "every": every, "clip_cm": CLIP_CM,
        "deepest_into_legs_cm": round(float(into.max()), 2), "frames_clipping": int((into > CLIP_CM).sum()),
        "frames_clipping_over_2cm": int((into > 2.0).sum()),
        "most_leg_out_through_cm": round(max(r["out_cm"] for r in rows), 2), "frames_leg_out_through": int(sum(r["out_cm"] > CLIP_CM for r in rows)),
        "deepest_floor_dip_cm": round(float(dip.max()), 2), "frames_in_floor": int((dip > 0.0).sum()),
        "most_swing_deg": round(max(r["swing_deg"] for r in rows), 1), "mean_swing_deg": round(float(np.mean([r["swing_deg"] for r in rows])), 1),
        "hem_shake_mm": round(1000.0 * shake_of(np.stack(hems)), 3),
        "worst": [rows[i] for i in order if rows[i]["into_cm"] > CLIP_CM], "rows": rows,
    })
    return report


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    out = os.path.abspath(flag("--out", "evidence/unclip"))
    tag = flag("--tag", "")
    fps, every, worst = int(flag("--fps", "30")), int(flag("--every", "1")), int(flag("--worst", "6"))
    films = [g for g in flag("--glb", "").split(",") if g]
    if not films:
        take = os.path.join(os.path.abspath(flag("--shots", os.path.join(REPO, "shots"))), flag("--take", "groove-flamenco"))
        with open(os.path.join(take, next(f for f in sorted(os.listdir(take)) if f.startswith("cast-") and f.endswith(".json")))) as f:
            cast = json.load(f)
        films = [os.path.join(take, part["glb"]) for part in cast["roles"].values()]
    os.makedirs(out, exist_ok=True)
    began, reports = time.time(), []
    for glb in films:
        r = judge_film(os.path.abspath(glb), fps, every, worst)
        reports.append(r)
        if r.get("skirt") is None:
            print("LEGS %s: no skirt (no chains hang from the hips or the spine)" % os.path.basename(glb), flush=True)
            continue
        print("LEGS %s: the skirt up to %.2f cm into her legs, %d of %d frames clip (%d over 2 cm); a leg out through the cloth on %d frames (up to %.1f cm of it); the hem up to %.2f cm into the floor on %d frames; swings up to %.1f degrees (%.1f on average), the hem shakes %.2f mm" % (
            os.path.basename(glb), r["deepest_into_legs_cm"], r["frames_clipping"], r["frames"], r["frames_clipping_over_2cm"], r["frames_leg_out_through"], r["most_leg_out_through_cm"],
            r["deepest_floor_dip_cm"], r["frames_in_floor"], r["most_swing_deg"], r["mean_swing_deg"], r["hem_shake_mm"]), flush=True)
        for w in r["worst"]:
            print("LEGS   worst: %.2f s, %.2f cm into the %s" % (w["seconds"], w["into_cm"], w["leg"]), flush=True)
    path = os.path.join(out, "legs%s.json" % (tag and "-" + tag))
    with open(path, "w") as f:
        json.dump({"films": reports, "seconds": round(time.time() - began, 1)}, f, indent=1)
    print("RESULT " + json.dumps({"out": path, "seconds": round(time.time() - began, 1)}))


if __name__ == "__main__":
    main()
