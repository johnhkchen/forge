"""Does loose cloth keep out of the body, off the floor, and still? Any clip of any character, every frame, measured.

    Blender -b --factory-startup -P scripts/fabric_judge.py -- --glb <a clip's .glb>,... [--out evidence/fabric]
        [--tag after] [--every 1] [--fps 30] [--worst 4] [--stills 0] [--stills-at 30,90]

judge_legs.py asks one question of one garment: do a skirt's chains keep clear of the thighs and shins. This asks
the same of every garment that swings on chains (cloth.py names them cloth_<gear>_<chain>_<n>: a skirt, a tunic's
hem, an apron, a coat's tails, a hood) against every part of the body, because a hand goes through a skirt in a
pick-up as surely as a knee does in a squat. It plays each .glb by its own action (exactly what Blender films, the
watch page plays and the cards' pieces are swung by) and on every frame, with the skin as the bones bend it:

    inside a limb     how deep the loose cloth (the points the chains pull on) goes into the body, part by part (legs: thighs and shins; arms: upper arms,
                      forearms and hands; trunk: hips, spine and chest; head: neck and head), past how deep it sat
                      there as it was made (cloth that rests on a hip is not through it). judge_legs.py's measure:
                      a ray from the part's bone out through the point finds the part's skin
                      Cloth that is pinched does not count: where two parts of the body press together (a thigh
                      against the belly in a squat, a calf against a thigh) no cloth between them can be clear of
                      both. It is counted apart ("pinched")
    through           how much of a limb's middle line is on the wrong side of the cloth: a leg starts inside a
                      skirt, so what counts is the leg outside it; an arm starts outside, so what counts is the arm
                      inside it (both less what was so as the cloth was made). A limb under a hem crosses nothing
    bare thighs       a leg can also leave a skirt without crossing it: round the hem, the skirt left hanging under
                      a raised thigh or flung out behind. So: of the places down the thighs that the cloth was all
                      round as it was made, the share it is no longer round (rays out from the thigh, eight ways;
                      "round" is five of them meeting cloth). Thighs only: a shin under a lifted knee shows below
                      any hem, and should
    floor             how far the lowest point of the cloth is below the floor
    swing             how far the chains' top bones turn from how they hang at rest (peak and mean)
    jitter            how much the cloth's open edges shake, frame to frame (mm): each point against the middle of
                      where it was the frame before and will be the frame after

A frame clips when the cloth is more than CLIP_CM into a part. Writes <out>/fabric[-tag].json: for each film its
sums, its garments (kind, where they hang from, chains) and, part by part, the deepest and the frames. --stills N
saves a plain picture of each film's N worst frames, --stills-at of the frames named. A film with no chains
says so. Never touches an open Blender.
"""

import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "impostor"))
import judge_legs  # noqa: E402

CLIP_CM = 0.5
DEEP_M = 0.12
PINCH_M = 0.015    # cloth in one part of the body and within this of another part's skin is pinched between them
ROUND = 5          # a place on a leg has cloth round it when this many of eight rays out from it meet cloth...
ROUND_M = 0.6      # ... within this far
SWUNG = 0.15       # a point of a garment is loose cloth when the chains pull on it this much
# The parts of the body cloth is tried against: {group: [(bone, how far along it counts)]}. A shin counts to just above
# the ankle (below is a stiff shoe, and a hem lying on a shoe is not a leg through a skirt).
PARTS = {
    "legs": [("thigh_l", 1.0), ("thigh_r", 1.0), ("shin_l", 0.85), ("shin_r", 0.85)],
    "arms": [("upper_arm_l", 1.0), ("upper_arm_r", 1.0), ("forearm_l", 1.0), ("forearm_r", 1.0), ("hand_l", 1.0), ("hand_r", 1.0)],
    "trunk": [("hips", 1.0), ("spine", 1.0), ("chest", 1.0)],
    "head": [("neck", 1.0), ("head", 1.0)],
}
FAMILY = {"thigh": "leg", "shin": "leg", "foot": "leg", "toe": "leg", "shoulder": "arm", "upper": "arm", "forearm": "arm", "hand": "arm"}
LINES = {"leg": ("thigh_%s", "shin_%s"), "arm": ("upper_arm_%s", "forearm_%s", "hand_%s")}


def family_of(bone):
    """Which limb a body bone is of: ("leg" | "arm" | "trunk", "l" | "r" | "")."""
    kind = FAMILY.get(bone.split("_")[0])
    if kind is None:
        return ("trunk", "")
    return (kind, bone[-1] if bone[-2:] in ("_l", "_r") else "")


def all_chains(rig):
    """Every swing chain a skeleton has: [{"gear", "kind", "parent", "bones"}], from the rig's own note or by name."""
    known = json.loads(rig.get("forge_cloth", "{}")).get("chains", [])
    if known:
        return [dict(c) for c in known if all(b in rig.data.bones for b in c["bones"])]
    chains = []
    for bone in rig.data.bones:
        if bone.name.startswith("cloth_") and bone.parent is not None and not bone.parent.name.startswith("cloth_"):
            chain, at = [bone.name], bone
            while at.children:
                at = at.children[0]
                chain.append(at.name)
            chains.append({"gear": bone.name[len("cloth_"):].rsplit("_", 2)[0], "parent": bone.parent.name, "bones": chain})
    return sorted(chains, key=lambda c: c["bones"][0])


def judge_film(glb, fps=30, every=1, worst=4, stills=0, out=None, tag="", at=None):
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = fps
    bpy.ops.import_scene.gltf(filepath=glb)
    rig = next((o for o in scene.objects if o.type == "ARMATURE"), None)
    report = {"glb": glb, "chains": 0}
    if rig is None or rig.animation_data is None or rig.animation_data.action is None:
        report["cloth"] = None
        return report
    chains = all_chains(rig)
    report["chains"] = len(chains)
    if not chains:
        report["cloth"] = None
        return report
    note = json.loads(rig.get("forge_cloth", "{}"))
    report["garments"] = note.get("garments") or sorted({(c.get("gear"), c["parent"]) for c in chains})
    chain_bones = {b for c in chains for b in c["bones"]}
    meshes = [o for o in scene.objects if o.type == "MESH" and o.find_armature() == rig]

    def swung(obj):
        ids = {g.index for g in obj.vertex_groups if g.name in chain_bones}
        return any(g.group in ids and g.weight > 0.05 for v in obj.data.vertices for g in v.groups)
    cloths = [o for o in meshes if o.get("forge") == "gear" and swung(o)]
    bodies = [o for o in meshes if o.get("forge") != "gear"]
    report["cloth"] = [o.name for o in cloths]
    if not cloths or not bodies:
        return report
    floor = float(json.loads(rig.get("forge_rig", "{}")).get("measure", {}).get("floor", 0.0))
    parts = [(group, bone, upto) for group, bones in PARTS.items() for bone, upto in bones if bone in rig.pose.bones]
    families = [family_of(bone) for _, bone, _ in parts]
    body_faces, face_family = [], []
    for obj in bodies:  # which limb each face of the body is: a part's own thickness is taken from its own skin
        tris = judge_legs.triangles(obj)
        names = {g.index: g.name for g in obj.vertex_groups}
        votes = {}
        lean = [dict() for _ in obj.data.vertices]
        for v in obj.data.vertices:
            for g in v.groups:
                fam = family_of(names.get(g.group, ""))
                lean[v.index][fam] = lean[v.index].get(fam, 0.0) + g.weight
        for tri in tris:
            votes = {}
            for i in tri:
                for fam, w in lean[i].items():
                    votes[fam] = votes.get(fam, 0.0) + w
            face_family.append(max(votes, key=votes.get) if votes else ("trunk", ""))
        body_faces.append((obj, tris))
    def pulled(obj):
        """Which of a garment's points the chains pull on (SWUNG of their weight or more): the loose cloth. The rest
        of a tunic is a shirt, and goes where the body's own weights take it; that is not the swing's to mend."""
        ids = {g.index for g in obj.vertex_groups if g.name in chain_bones}
        return np.array([sum(g.weight for g in v.groups if g.group in ids) >= SWUNG * max(sum(g.weight for g in v.groups), 1e-9) for v in obj.data.vertices], dtype=bool)
    shape = []
    for obj in cloths:
        tris, loose = judge_legs.triangles(obj), pulled(obj)
        shape.append((obj, tris, judge_legs.open_points(obj), loose, loose[tris].all(axis=1) if len(tris) else np.zeros(0, dtype=bool)))
    action = rig.animation_data.action
    first, last = (int(round(x)) for x in action.frame_range)
    frames = list(range(first, last + 1, max(1, int(every))))
    rest_tops = {c["bones"][0]: (rig.data.bones[c["parent"]].matrix_local.inverted() @ rig.data.bones[c["bones"][0]].matrix_local).to_quaternion() for c in chains}
    profiles = {}
    upto = [u for _, _, u in parts]

    def stood():
        graph = bpy.context.evaluated_depsgraph_get()
        samples, rims, cloth, cloth_faces, start = [], [], [], [], 0
        for obj, tris, rim, loose, loose_faces in shape:
            p = judge_legs.coords(obj, graph)
            samples += [p[loose], p[tris[loose_faces]].mean(axis=1)]
            rims.append(p[rim[loose[rim]]])
            cloth.append(p)
            cloth_faces.append(tris + start)
            start += len(p)
        samples = np.concatenate(samples)
        sheet = BVHTree.FromPolygons([Vector(p) for p in np.concatenate(cloth)], np.concatenate(cloth_faces).tolist())
        world = rig.matrix_world
        through = {}
        for kind, names in LINES.items():
            for side in ("l", "r"):
                bones = [rig.pose.bones.get(n % side) for n in names]
                if any(b is None for b in bones):
                    continue
                line = [np.array(world @ bones[0].head)] + [np.array(world @ b.tail) for b in bones]
                if kind == "leg":  # to just above the ankle
                    line[-1] = np.array(world @ (bones[-1].head + (bones[-1].tail - bones[-1].head) * 0.85))
                through[(kind, side)] = judge_legs.out_through(line, lambda o, w, d: sheet.ray_cast(Vector(o), Vector(w), d)[3])
        around = []  # for each place down the legs: how many of eight rays out from it meet the cloth
        for side in ("l", "r"):
            for name, upto_here in (("thigh_%s" % side, 1.0),):
                bone = rig.pose.bones.get(name)
                if bone is None:
                    continue
                m = world @ bone.matrix
                x_axis, z_axis = np.array(m.to_3x3().normalized().col[0]), np.array(m.to_3x3().normalized().col[2])
                head, tail = np.array(world @ bone.head), np.array(world @ bone.tail)
                for t in (0.15, 0.35, 0.55, 0.75, 0.95):
                    if t > upto_here:
                        continue
                    at = head + (tail - head) * t
                    around.append(sum(sheet.ray_cast(Vector(at), Vector(math.cos(a) * x_axis + math.sin(a) * z_axis), ROUND_M)[3] is not None for a in [k * math.pi / 4 for k in range(8)]))
        points, faces, start = [], [], 0
        for obj, tris in body_faces:
            p = judge_legs.coords(obj, graph)
            points.append(p)
            faces.append(tris + start)
            start += len(p)
        tree = BVHTree.FromPolygons([Vector(p) for p in np.concatenate(points)], np.concatenate(faces).tolist())

        def cast(origin, way, far, k, own=False):
            hit = tree.ray_cast(Vector(origin), Vector(way), far)
            if hit[3] is None or (own and face_family[hit[2]] not in (families[k], ("trunk", ""))):
                return None
            return hit[3]
        mats = [world @ rig.pose.bones[n].matrix for _, n, _ in parts]
        segments = [(np.array(world @ rig.pose.bones[n].head), np.array(world @ rig.pose.bones[n].tail)) for _, n, _ in parts]
        axes = [(np.array(m.to_3x3().normalized().col[0]), np.array(m.to_3x3().normalized().col[2])) for m in mats]
        if not profiles:
            for k in range(len(parts)):
                profiles[k] = judge_legs.profile_of(lambda o, w, d: cast(o, w, d, k, own=True), segments[k][0], segments[k][1], axes[k][0], axes[k][1])

        def cap(k, along, way):
            return judge_legs.thickness(profiles[k], along, float(way @ axes[k][0]), float(way @ axes[k][1]))
        deep, which = judge_legs.depth_in_legs(samples, segments, cast, reach=DEEP_M, cap=cap, upto=upto)

        def pinched(i):
            """Whether a point of cloth in one part is in, or hard against, another part too: pinched between them."""
            k = which[i]
            for j, (a, b) in enumerate(segments):
                if j == k:
                    continue
                ab = b - a
                t = float(np.clip((samples[i] - a) @ ab / max(float(ab @ ab), 1e-12), 0.0, 1.0))
                if families[j] == families[k] and (min(t, 1.0 - t) < 0.25):
                    continue  # (the next bone of the same limb, at the joint they share: a knee is not a pinch)
                at = a + t * ab
                far = float(np.linalg.norm(samples[i] - at))
                if far < 1e-6 or far > DEEP_M + PINCH_M:
                    continue
                way = (samples[i] - at) / far
                most = cap(j, t, way)
                skin = cast(at, way, most, j)
                if (most if skin is None else min(skin, most)) > far - PINCH_M:
                    return True
            return False
        return samples, np.concatenate(rims), deep, which, through, np.array(around), pinched

    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    _, _, at_rest, _, through_rest, round_rest, _ = stood()
    was_round = round_rest >= ROUND  # the places down the legs the cloth was all round as it was made
    rest_all = {c["bones"][i]: (rig.data.bones[c["parent"]].matrix_local.inverted() @ rig.data.bones[c["bones"][i]].matrix_local).to_quaternion() for c in chains for i in range(len(c["bones"]))}
    rig.data.pose_position = "POSE"
    group_of = np.array([list(PARTS).index(g) for g, _, _ in parts])
    rows, hems = [], []
    began = time.time()
    for f in frames:
        scene.frame_set(f)
        samples, rim, deep, which, through, around, pinched = stood()
        hems.append(rim)
        past = np.maximum(deep - at_rest, 0.0)  # (as judge_legs.py: past how deep the point sat in the body as it was made)
        squeezed = 0.0
        for i in np.nonzero(past > CLIP_CM / 100.0)[0]:
            if pinched(i):
                squeezed, past[i] = max(squeezed, float(past[i])), 0.0
        bare = float((around[was_round] < ROUND).mean()) if was_round.any() else 0.0
        by = {}
        for g, name in enumerate(PARTS):
            mine = group_of[which] == g
            by[name] = round(100.0 * float(past[mine].max()), 2) if mine.any() else 0.0
        k = int(np.argmax(past))
        wrong = {"%s_%s" % key: round(100.0 * max(0.0, through[key] - through_rest.get(key, 0.0)), 2) for key in through}
        swing = 0.0
        for c in chains:  # (any bone of a chain: one whose top bone holds no cloth of its own swings by the ones below)
            for name in c["bones"]:
                now = (rig.pose.bones[c["parent"]].matrix.inverted() @ rig.pose.bones[name].matrix).to_quaternion()
                angle = rest_all[name].rotation_difference(now).angle
                swing = max(swing, math.degrees(min(angle, 2 * math.pi - angle)))
        rows.append({"frame": f, "seconds": round((f - first) / float(fps), 3), "into_cm": round(100.0 * float(past[k]), 2), "part": parts[which[k]][1] if past[k] > 0 else None,
                     "by": by, "pinched_cm": round(100.0 * squeezed, 2), "bare_legs": round(bare, 3), "legs_out_cm": max([v for key, v in wrong.items() if key.startswith("leg")] or [0.0]),
                     "arms_in_cm": max([v for key, v in wrong.items() if key.startswith("arm")] or [0.0]),
                     "floor_dip_cm": round(max(0.0, 100.0 * (floor - float(samples[:, 2].min()))), 2), "swing_deg": round(swing, 1)})
    into = np.array([r["into_cm"] for r in rows])
    dip = np.array([r["floor_dip_cm"] for r in rows])
    order = np.argsort(-into, kind="stable")[:worst]
    parts_sum = {}
    for name in PARTS:
        col = np.array([r["by"][name] for r in rows])
        parts_sum[name] = {"deepest_cm": round(float(col.max()), 2), "frames_clipping": int((col > CLIP_CM).sum()), "frames_over_2cm": int((col > 2.0).sum())}
    report.update({
        "frames": len(rows), "fps": fps, "every": every, "clip_cm": CLIP_CM, "judge_seconds": round(time.time() - began, 2),
        "deepest_cm": round(float(into.max()), 2), "frames_clipping": int((into > CLIP_CM).sum()), "frames_over_2cm": int((into > 2.0).sum()),
        "parts": parts_sum,
        "legs_out_cm": round(max(r["legs_out_cm"] for r in rows), 2), "frames_legs_out": int(sum(r["legs_out_cm"] > CLIP_CM for r in rows)),
        "arms_in_cm": round(max(r["arms_in_cm"] for r in rows), 2), "frames_arms_in": int(sum(r["arms_in_cm"] > CLIP_CM for r in rows)),
        "frames_pinched": int(sum(r["pinched_cm"] > CLIP_CM for r in rows)), "pinched_cm": round(max(r["pinched_cm"] for r in rows), 2),
        "legs_covered_as_made": int(was_round.sum()), "bare_legs_mean": round(float(np.mean([r["bare_legs"] for r in rows])), 3), "bare_legs_peak": round(max(r["bare_legs"] for r in rows), 3),
        "frames_legs_bare": int(sum(r["bare_legs"] >= 0.25 for r in rows)),
        "floor_dip_cm": round(float(dip.max()), 2), "frames_in_floor": int((dip > 0.05).sum()),
        "peak_swing_deg": round(max(r["swing_deg"] for r in rows), 1), "mean_swing_deg": round(float(np.mean([r["swing_deg"] for r in rows])), 1),
        "jitter_mm": round(1000.0 * judge_legs.shake_of(np.stack(hems)), 3) if len(hems[0]) else 0.0,
        "worst": [rows[i] for i in order if rows[i]["into_cm"] > CLIP_CM], "rows": rows,
    })
    if (stills or at) and out:
        bad = sorted(rows, key=lambda r: -(r["into_cm"] + r["legs_out_cm"] + r["arms_in_cm"] + r["floor_dip_cm"]))[:stills]
        shown = [r["frame"] for r in bad] + [f for f in (at or []) if first <= f <= last]
        report["stills"] = [still(scene, rig, f, os.path.join(out, "%s%s-f%03d.png" % (os.path.splitext(os.path.basename(glb))[0], tag and "-" + tag, f))) for f in shown]
    return report


def still(scene, rig, frame, path, size=720):
    """A plain picture of one frame, three-quarter front, the whole figure (workbench: no lights to set up)."""
    import bpy
    from mathutils import Vector
    scene.frame_set(frame)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new("w")
    scene.world.color = (0.78, 0.8, 0.82)
    cam = bpy.data.objects.get("judge eye")
    if cam is None:
        cam = bpy.data.objects.new("judge eye", bpy.data.cameras.new("judge eye"))
        scene.collection.objects.link(cam)
    scene.camera = cam
    hips = rig.matrix_world @ rig.pose.bones["hips"].head
    tall = float(json.loads(rig.get("forge_rig", "{}")).get("measure", {}).get("height", 1.7))
    look = Vector((hips.x, hips.y, 0.45 * tall))
    cam.location = look + Vector((0.55, -1.0, 0.3)).normalized() * 2.1 * tall
    cam.rotation_euler = (look - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 60
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def line_of(r):
    if r.get("cloth") is None:
        return "no cloth on chains"
    p = r["parts"]
    return ("into the body up to %.1f cm, %d of %d frames clip (%d over 2 cm; pinched on %d more) [legs %.1f/%d, arms %.1f/%d, trunk %.1f/%d, head %.1f/%d]; a leg out through the cloth %.1f cm, %d frames; "
            "thighs bare %.0f%% on average, a quarter bare or more on %d frames; an arm in through it %.1f cm, %d frames; floor %.1f cm, %d frames; swing peak %.0f (mean %.0f) deg; jitter %.2f mm" % (
                r["deepest_cm"], r["frames_clipping"], r["frames"], r["frames_over_2cm"], r["frames_pinched"], p["legs"]["deepest_cm"], p["legs"]["frames_clipping"], p["arms"]["deepest_cm"], p["arms"]["frames_clipping"],
                p["trunk"]["deepest_cm"], p["trunk"]["frames_clipping"], p["head"]["deepest_cm"], p["head"]["frames_clipping"], r["legs_out_cm"], r["frames_legs_out"],
                100 * r["bare_legs_mean"], r["frames_legs_bare"], r["arms_in_cm"], r["frames_arms_in"],
                r["floor_dip_cm"], r["frames_in_floor"], r["peak_swing_deg"], r["mean_swing_deg"], r["jitter_mm"]))


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default  # noqa: E731
    out = os.path.abspath(flag("--out", "evidence/fabric"))
    tag = flag("--tag", "")
    fps, every, worst, stills = int(flag("--fps", "30")), int(flag("--every", "1")), int(flag("--worst", "4")), int(flag("--stills", "0"))
    films = [g for g in flag("--glb", "").split(",") if g]
    at = [int(f) for f in flag("--stills-at", "").split(",") if f]
    os.makedirs(out, exist_ok=True)
    began, reports = time.time(), []
    for glb in films:
        r = judge_film(os.path.abspath(glb), fps, every, worst, stills, out, tag, at)
        reports.append(r)
        print("FABRIC %s: %s" % (os.path.basename(glb), line_of(r)), flush=True)
    path = os.path.join(out, "fabric%s.json" % (tag and "-" + tag))
    with open(path, "w") as f:
        json.dump({"films": reports, "seconds": round(time.time() - began, 1)}, f, indent=1)
    print("RESULT " + json.dumps({"out": path, "seconds": round(time.time() - began, 1)}))


if __name__ == "__main__":
    main()
