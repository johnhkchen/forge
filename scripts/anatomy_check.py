"""Measure a character's low-poly and mid-poly bodies against its detailed mesh: is the anatomy right?

    blender -b --factory-startup -P scripts/anatomy_check.py -- RUN_DIR OUT.png LABEL=FILE.glb [LABEL=FILE.glb ...]

RUN_DIR holds the detailed mesh (final.glb), the real body under hiding
clothes when the run has one (base/final.glb) and, for the head's box, the
block-out's recipe (lowpoly_build.json). Each FILE is a version to judge: a
low-poly or mid-poly .glb, standing or walking. Writes OUT.png (a sheet) and
OUT.json, and prints one line, ANATOMY {json}.

What it measures, each version against the detailed mesh:

- landmarks: the same finder (landmarks.py) is run on both, and each
  landmark's distance apart is given in % of the height. With a base body,
  the version's body alone (its gear hidden) is also read against that.
- proportions: heads tall, leg and arm share of the height, shoulders
  against hips, hand and foot length, side by side.
- silhouette: how much of the two outlines is shared, seen from the front
  and from the side (1.0 = the same outline).
- cross-sections: rings around the trunk, an arm, a leg and a foot, at the
  same spots on both; how far the version's ring is from the detailed one,
  in % of that ring's size, per region (pelvis, ribcage, shoulders, neck,
  upper arm, forearm, hand, thigh, shin, foot).
- triangles, and how many edge loops sit within a hand's width of each
  elbow and knee (what lets them bend).

The sheet shows, per version: the two outlines over each other, front and
side (grey shared, red where the version lacks, blue where it adds), with
both sets of landmarks (the detailed mesh's as black crosses, the version's
as red dots); then plain shaded pictures: the detailed mesh, the version
dressed, and the version's body alone with its gear off, where it has gear.
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", ".claude", "skills", "tidy-mesh", "scripts")
AROUND = 24
MARKS = ("chin", "neck_base", "shoulder", "armpit", "chest", "waist", "hips", "crotch", "elbow", "wrist", "fingertip", "knee", "ankle", "heel", "toe")


def run_script(name, params):
    with open(os.path.join(SCRIPTS, name)) as f:
        source = f.read()
    head, _, tail = source.partition("\nimport ")
    namespace = {"__name__": "__main__"}
    exec(head, namespace)
    namespace["PARAMS"].update(params)
    captured = []

    def capture(*args, **kwargs):
        text = " ".join(str(a) for a in args)
        if text.startswith("RESULT "):
            captured.append(json.loads(text[len("RESULT "):]))

    namespace["print"] = capture
    exec("import " + tail, namespace)
    return captured[-1]


def bring_in(path, tag):
    """A .glb's meshes, in their rest pose, each tagged with where it came from."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        if o.type == "ARMATURE":
            o.data.pose_position = "REST"
    bpy.context.view_layer.update()
    meshes = [o for o in new if o.type == "MESH" and not o.name.startswith("lines:")]
    for o in meshes:
        o["from"] = tag
    return meshes


def soup(meshes):
    """World-space points and triangles of some meshes, as evaluated (so a rig in rest pose counts)."""
    deps = bpy.context.evaluated_depsgraph_get()
    points, tris = [], []
    for o in meshes:
        ev = o.evaluated_get(deps)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        m = np.array(ev.matrix_world)
        co = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
        idx = np.empty(len(me.loop_triangles) * 3, dtype=np.int32)
        me.loop_triangles.foreach_get("vertices", idx)
        tris.append(idx.reshape(-1, 3) + sum(len(p) for p in points))
        points.append(co)
        ev.to_mesh_clear()
    return np.concatenate(points), np.concatenate(tris)


def tree_of(points, tris):
    return BVHTree.FromPolygons([tuple(p) for p in points], [tuple(int(i) for i in t) for t in tris])


def as_one(meshes, name):
    """One plain object holding the meshes as they stand: what landmarks.py is pointed at."""
    points, tris = soup(meshes)
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(p) for p in points], [], [tuple(int(i) for i in t) for t in tris])
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj, points, tris


def outline(tree, lo, hi, view, size):
    """A filled outline seen from the front (view 1: looking along y) or the side (view 0: along x)."""
    across = 0 if view == 1 else 1
    wide = hi[across] - lo[across]
    tall = hi[2] - lo[2]
    cols, rows = max(int(size * wide / tall), 8), size
    mask = np.zeros((rows, cols), dtype=bool)
    aim = Vector((0, 1, 0)) if view == 1 else Vector((1, 0, 0))
    for r in range(rows):
        z = lo[2] + (r + 0.5) * tall / rows
        for c in range(cols):
            p = [0.0, 0.0, z]
            p[across] = lo[across] + (c + 0.5) * wide / cols
            p[view] = lo[view] - 1.0
            mask[r, c] = tree.ray_cast(Vector(p), aim)[0] is not None
    return mask


def ring(tree, where, axis, clips, reach):
    u, v = [(1, 2), (0, 2), (0, 1)][axis]
    out = []
    ways = [Vector([1.0 if i == u else 0.0 for i in range(3)]), Vector([1.0 if i == v else 0.0 for i in range(3)])]
    within = all(tree.ray_cast(Vector(where), way * side, reach)[0] is not None for way in ways for side in (1, -1))
    for k in range(AROUND):
        t = 2 * math.pi * k / AROUND
        aim = [0.0, 0.0, 0.0]
        aim[u], aim[v] = math.cos(t), math.sin(t)
        far, walled = reach, False
        for a, sign, value in clips:
            if sign * aim[a] > 1e-6:
                room = sign * (value - where[a]) / (sign * aim[a])
                if room < far:
                    far, walled = max(room, 0.0), True
        aim = Vector(aim)
        hit = tree.ray_cast(Vector(where) + aim * far, -aim, far) if far > 1e-6 else (None,)
        if hit[0] is not None:
            out.append(far - hit[3])
        elif walled:  # nothing on the way in from the wall: the first surface on the way out to it, or the wall
            reached = tree.ray_cast(Vector(where), aim, far) if within and far > 1e-6 else (None,)
            out.append(reached[3] if reached[0] is not None else (far if within else None))
        else:
            out.append(None)
    return out


def regions(marks, tall, kept):
    """Where to cut rings, from the detailed mesh's landmarks: {region: [(where, axis, clips, reach), ...]}."""
    pit, top = marks["armpit"], marks["shoulder"]

    def middle(stretch, pos):
        rows = kept[stretch]
        best = min(rows, key=lambda r: abs(r[0] - pos))
        return best[1], best[2]

    def trunk(z):
        y = middle("trunk", z)[1]
        clips = [(0, 1, pit[0]), (0, -1, -pit[0])] if pit[2] - 0.01 * tall <= z <= top[2] + 0.01 * tall else []
        return ([0.0, y, z], 2, clips, 0.6 * tall)

    def arm(x):
        y, z = middle("arm" if x <= marks["wrist"][0] else "hand", x)
        return ([x, y, z], 0, [(2, -1, pit[2] - 0.005 * tall)] if x < pit[0] + 0.02 * tall else [], 0.3 * tall)

    def leg(z):
        x, y = middle("leg", z)
        return ([x, y, z], 2, [(0, -1, 0.0)], 0.35 * tall)

    def foot(y):
        x, z = middle("foot", y)
        return ([x, y, z], 1, [(0, -1, 0.0), (2, 1, marks["ankle"][2])], 0.3 * tall)

    def along(make, a, b):
        return [make(a + (b - a) * t) for t in (0.1, 0.3, 0.5, 0.7, 0.9)]

    return {
        "pelvis": along(trunk, marks["crotch"][2], marks["waist"][2]),
        "ribcage": along(trunk, marks["waist"][2], pit[2]),
        "shoulders": along(trunk, pit[2], marks["neck_base"][2]),
        "neck": along(trunk, marks["neck_base"][2], marks["chin"][2]),
        "upper arm": along(arm, pit[0], marks["elbow"][0]),
        "forearm": along(arm, marks["elbow"][0], marks["wrist"][0]),
        "hand": along(arm, marks["wrist"][0], marks["fingertip"][0]),
        "thigh": along(leg, marks["knee"][2], marks["crotch"][2]),
        "shin": along(leg, marks["ankle"][2], marks["knee"][2]),
        "foot": along(foot, marks["toe"][1], marks["heel"][1]),
    }


def ring_error(ours, theirs):
    """How far one ring is from another, in % of the other's size; None when the other saw nothing."""
    pairs = [(a if a is not None else 0.0, b) for a, b in zip(ours, theirs) if b is not None]
    if len(pairs) < AROUND // 2:
        return None
    size = sum(b for _, b in pairs) / len(pairs)
    return 100.0 * sum(abs(a - b) for a, b in pairs) / len(pairs) / max(size, 1e-6)


def loops_near(points, tris, spot, axis, reach):
    """How many separate rings of points cross a limb within `reach` of a joint: its edge loops there."""
    others = [i for i in range(3) if i != axis]
    near = points[(np.abs(points[:, axis] - spot[axis]) < reach) & (np.abs(points[:, others[0]] - spot[others[0]]) < 2.5 * reach)
                  & (np.abs(points[:, others[1]] - spot[others[1]]) < 2.5 * reach)]
    if not len(near):
        return 0
    at = np.sort(near[:, axis])
    return int(1 + np.sum(np.diff(at) > 0.06 * reach))


def shade(meshes, path, lo, hi, view):
    """A plain shaded picture of some meshes: front or three-quarter."""
    scene = bpy.context.scene
    hidden = {o: o.hide_render for o in bpy.data.objects}
    for o in bpy.data.objects:
        o.hide_render = o not in meshes
    cam = bpy.data.objects.get("check cam")
    if cam is None:
        cam = bpy.data.objects.new("check cam", bpy.data.cameras.new("check cam"))
        scene.collection.objects.link(cam)
        cam.data.type = "ORTHO"
    tall = hi[2] - lo[2]
    middle = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2))
    aim = Vector((0, -1, 0)) if view == "front" else Vector((0.75, -0.6, 0.25)).normalized()
    cam.location = middle + aim * 3 * tall
    cam.rotation_euler = (-aim).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = 1.08 * max(tall, hi[0] - lo[0])
    cam.data.clip_end = 10 * tall
    scene.camera = cam
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "SINGLE"
    scene.display.shading.single_color = (0.78, 0.74, 0.68)
    scene.display.shading.show_cavity = True
    scene.display.shading.show_object_outline = True
    scene.render.resolution_x = scene.render.resolution_y = 520
    scene.render.film_transparent = False
    scene.world = scene.world or bpy.data.worlds.new("check")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for o, was in hidden.items():
        o.hide_render = was
    img = bpy.data.images.load(path)
    px = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], 4)[:, :, :3]
    bpy.data.images.remove(img)
    os.remove(path)
    return px


def cross(img, col, row, color, size):
    rows, cols = img.shape[:2]
    r, c = int(np.clip(row, 0, rows - 1)), int(np.clip(col, 0, cols - 1))
    img[max(r - size, 0):r + size + 1, max(c - 1, 0):c + 2] = color
    img[max(r - 1, 0):r + 2, max(c - size, 0):c + size + 1] = color


def overlay(ref_mask, mask, lo, hi, view, ref_marks, marks):
    """Two outlines over each other: the detailed mesh grey, the version blue where it adds and red where it lacks."""
    rows, cols = ref_mask.shape
    img = np.ones((rows, cols, 3), dtype=np.float32)
    img[ref_mask & mask] = (0.72, 0.72, 0.72)
    img[ref_mask & ~mask] = (0.95, 0.45, 0.4)
    img[~ref_mask & mask] = (0.4, 0.55, 0.95)
    across = 0 if view == 1 else 1
    for spots, color, size in ((ref_marks, (0, 0, 0), 5), (marks, (0.85, 0.0, 0.0), 2)):
        for key in MARKS:
            p = spots[key]
            cross(img, (p[across] - lo[across]) / (hi[across] - lo[across]) * cols, (p[2] - lo[2]) / (hi[2] - lo[2]) * rows, color, size)
    return img


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    run, out, files = os.path.abspath(args[0]), os.path.abspath(args[1]), [a.split("=", 1) for a in args[2:]]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    box = None
    recipe_path = os.path.join(run, "lowpoly_build.json")
    if os.path.exists(recipe_path):
        with open(recipe_path) as f:
            heads = [p for p in json.load(f)["pieces"] if "head" in p and p.get("box")]
        box = heads[0]["box"] if heads else None

    ref_meshes = bring_in(os.path.join(run, "final.glb"), "ref")
    ref, ref_points, ref_tris = as_one(ref_meshes, "check: detailed")
    ref_tree = tree_of(ref_points, ref_tris)
    found = run_script("landmarks.py", {"object": ref.name, "head": box, "name": "check: detailed", "show": False})
    kept = json.loads(bpy.context.scene["body: check: detailed"])["scan"]
    marks, tall = found["landmarks"], found["proportions"]["height_m"]
    lo, hi = ref_points.min(axis=0) - 0.03 * tall, ref_points.max(axis=0) + 0.03 * tall
    base = None
    if os.path.exists(os.path.join(run, "base", "final.glb")):
        base_obj, _, _ = as_one(bring_in(os.path.join(run, "base", "final.glb"), "base"), "check: base body")
        base = run_script("landmarks.py", {"object": base_obj.name, "head": box, "name": "check: base body", "show": False, "keep": False})
    cuts = regions(marks, tall, kept)
    ref_rings = {name: [ring(ref_tree, *cut) for cut in spots] for name, spots in cuts.items()}
    ref_masks = {view: outline(ref_tree, lo, hi, view, 300) for view in (1, 0)}
    ref_shade = shade(ref_meshes, out + ".tmp.png", lo, hi, "quarter")

    report = {"run": run, "height_m": tall, "detailed": {"landmarks": marks, "proportions": found["proportions"], "found": found["found"]},
              "base_body": base and {"landmarks": base["landmarks"], "proportions": base["proportions"]}, "versions": {}}
    strips = []
    for label, path in files:
        every = bring_in(os.path.abspath(path), label)
        meshes = [o for o in every if not o.get("under")]  # dressed: the skin a piece of gear hides isn't drawn
        bare = [o for o in every if o.get("forge") == "body"] if any(o.get("forge") == "gear" for o in every) else []
        obj, points, tris = as_one(meshes, "check: " + label)
        tree = tree_of(points, tris)
        try:
            mine = run_script("landmarks.py", {"object": obj.name, "head": box, "name": "check: " + label, "show": False, "keep": False})
        except ValueError as why:
            report["versions"][label] = {"file": path, "error": str(why)}
            continue
        off = {k: round(100 * (Vector(mine["landmarks"][k]) - Vector(marks[k])).length / tall, 2) for k in MARKS}
        entry = {"file": path, "triangles": int(len(tris)), "landmark_off_pct": off,
                 "landmark_off_mean_pct": round(sum(off.values()) / len(off), 2), "landmark_off_worst": max(off, key=off.get),
                 "proportions": mine["proportions"], "found": {k: v for k, v in mine["found"].items() if v != "shape"}}
        if base:  # its body alone, against the real body
            if bare:
                bare_obj, _, _ = as_one(bare, "check: %s body" % label)
                try:
                    alone = run_script("landmarks.py", {"object": bare_obj.name, "head": box, "name": "x", "show": False, "keep": False})
                    gap = {k: round(100 * (Vector(alone["landmarks"][k]) - Vector(base["landmarks"][k])).length / tall, 2) for k in MARKS}
                    entry["body_vs_base_body"] = {"landmark_off_pct": gap, "landmark_off_mean_pct": round(sum(gap.values()) / len(gap), 2),
                                                  "proportions": alone["proportions"]}
                except ValueError as why:
                    entry["body_vs_base_body"] = {"error": str(why)}
                bpy.data.objects.remove(bare_obj, do_unlink=True)
        masks = {view: outline(tree, lo, hi, view, 300) for view in (1, 0)}
        entry["silhouette_shared"] = {name: round(float((masks[v] & ref_masks[v]).sum()) / max(float((masks[v] | ref_masks[v]).sum()), 1.0), 3)
                                      for name, v in (("front", 1), ("side", 0))}
        sections = {}
        for name, spots in cuts.items():
            errors = [ring_error(ring(tree, *cut), theirs) for cut, theirs in zip(spots, ref_rings[name])]
            errors = [e for e in errors if e is not None]
            sections[name] = round(sum(errors) / len(errors), 1) if errors else None
        entry["cross_section_off_pct"] = sections
        seen = [v for v in sections.values() if v is not None]
        entry["cross_section_off_mean_pct"] = round(sum(seen) / len(seen), 1) if seen else None
        hand = marks["fingertip"][0] - marks["wrist"][0]
        entry["loops"] = {"elbow": loops_near(points, tris, mine["landmarks"]["elbow"], 0, 0.5 * hand),
                          "knee": loops_near(points, tris, mine["landmarks"]["knee"], 2, 0.5 * hand)}
        report["versions"][label] = entry
        panels = [overlay(ref_masks[1], masks[1], lo, hi, 1, marks, mine["landmarks"]), overlay(ref_masks[0], masks[0], lo, hi, 0, marks, mine["landmarks"])]
        panels += [np.flipud(ref_shade), np.flipud(shade(meshes, out + ".tmp.png", lo, hi, "quarter")),
                   np.flipud(shade(bare or meshes, out + ".tmp.png", lo, hi, "quarter" if bare else "front"))]
        if bare:
            panels.append(np.flipud(shade(bare, out + ".tmp.png", lo, hi, "front")))
        rows = max(p.shape[0] for p in panels)
        padded = [np.concatenate([np.ones((rows - p.shape[0], p.shape[1], 3), dtype=np.float32), p[::-1] if i < 2 else p]) for i, p in enumerate(panels)]
        strips.append(np.concatenate([np.concatenate([p, np.ones((rows, 12, 3), dtype=np.float32)], axis=1) for p in padded], axis=1))
        for o in every + [obj]:
            o.hide_render = True
    if strips:
        wide = max(s.shape[1] for s in strips)
        sheet = np.concatenate([np.concatenate([s, np.ones((s.shape[0], wide - s.shape[1], 3), dtype=np.float32)], axis=1) for s in strips])
        sheet = np.flipud(sheet)
        img = bpy.data.images.new("sheet", sheet.shape[1], sheet.shape[0], alpha=False)
        img.pixels.foreach_set(np.concatenate([sheet, np.ones(sheet.shape[:2] + (1,), dtype=np.float32)], axis=2).ravel())
        img.filepath_raw, img.file_format = out, "PNG"
        img.save()
    report["sheet"] = out
    report["rows"] = [label for label, _ in files]
    with open(os.path.splitext(out)[0] + ".json", "w") as f:
        json.dump(report, f, indent=1)
    print("ANATOMY " + json.dumps({label: {k: v[k] for k in ("triangles", "landmark_off_mean_pct", "landmark_off_worst", "silhouette_shared",
                                                             "cross_section_off_mean_pct", "loops") if k in v} for label, v in report["versions"].items()}))


main()
