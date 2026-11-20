"""Picture a character's face in every version of a run, next to the source picture.

    blender -b --factory-startup -P scripts/face_sheet.py -- RUN_DIR OUT.png [--size 256] [--box x0,y0,z0,x1,y1,z1] [--also label=FILE.glb ...] [--only label,label]

One row per version that is there (the detailed final.glb, or the raw mesh.glb
when the run has not been through Blender; profiles/web, game, lowpoly,
midpoly; the two walk clips at two moments of the loop), three close-ups of
the head each: front, three-quarter, side. The first row is the head cut out
of the run's image.png. Next to OUT.png it writes OUT.json: the head's box,
and for each version the tiles' paths and, for a walk clip, how far the
head's points move against the head bone (a face that bends shows here).

The head's box is the block-out's own head piece when the run has a recipe
(lowpoly_build.json), else it is found on the detailed mesh: the column above
the arms of a T-pose, down to where it narrows into the neck or widens into
the shoulders. --box sets it by hand. Every version is framed with that one
box, so the tiles can be laid over each other.
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

args = sys.argv[sys.argv.index("--") + 1:]


def option(name, default, many=False):
    found = []
    while name in args:
        i = args.index(name)
        found.append(args[i + 1])
        del args[i:i + 2]
    if many:
        return found
    return found[-1] if found else default


size = int(option("--size", "256"))
box_arg = option("--box", "")
also = option("--also", None, many=True)
only = [s for s in option("--only", "").split(",") if s]
run, out = os.path.abspath(args[0]), os.path.abspath(args[1])
tiles_dir = os.path.splitext(out)[0] + "-tiles"
os.makedirs(tiles_dir, exist_ok=True)

VIEWS = {"front": Vector((0, -1, 0)), "three-quarter": Vector((0.7, -0.7, 0.12)).normalized(), "side": Vector((1, 0, 0))}


def load(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = 30
    bpy.ops.import_scene.gltf(filepath=path)
    scene = bpy.context.scene
    meshes = [o for o in scene.objects if o.type == "MESH" and not o.get("under")]
    for o in scene.objects:
        if o.type == "MESH" and o.get("under"):
            o.hide_render = True
    for o in meshes:
        me = o.data
        if not (me.materials and me.materials[0]):  # painted colors and no material: show the paint
            mat = bpy.data.materials.new("sheet")
            mat.use_nodes = True
            shader = mat.node_tree.nodes["Principled BSDF"]
            shader.inputs["Roughness"].default_value = 0.9
            if me.color_attributes:
                color = mat.node_tree.nodes.new("ShaderNodeVertexColor")
                mat.node_tree.links.new(color.outputs["Color"], shader.inputs["Base Color"])
            me.materials.clear()
            me.materials.append(mat)
    return scene, meshes


def world_points(meshes, deps=None):
    chunks = []
    for o in meshes:
        me = o.evaluated_get(deps).to_mesh() if deps else o.data
        co = np.empty(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        m = np.array(o.matrix_world, dtype=np.float32)
        chunks.append(co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3])
        if deps:
            o.evaluated_get(deps).to_mesh_clear()
    return np.concatenate(chunks)


def find_head(pts):
    """The head of a T-pose facing -y: [[x0, y0, z0], [x1, y1, z1]]."""
    z0, z1 = float(pts[:, 2].min()), float(pts[:, 2].max())
    tall = z1 - z0
    cx = float(pts[:, 0].min() + pts[:, 0].max()) / 2  # between the hands: a flower over one ear doesn't move it
    column = pts[np.abs(pts[:, 0] - cx) < 0.2 * tall]
    step = tall / 200
    widths = []
    for i in range(70):
        row = column[(column[:, 2] <= z1 - i * step) & (column[:, 2] > z1 - (i + 1) * step)]
        widths.append(float(np.abs(row[:, 0] - cx).max()) if len(row) else 0.0)
    head_w, neck = 0.0, None
    for i, w in enumerate(widths):
        if i * step < 0.07 * tall:
            head_w = max(head_w, w)
            continue
        if w < 0.72 * head_w:  # narrowing into a neck: follow it down to its narrowest
            neck = i
            while neck + 1 < len(widths) and widths[neck + 1] <= widths[neck] and (neck - i) * step < 0.03 * tall:
                neck += 1
            break
        if w > 1.45 * head_w:  # widening into shoulders with no neck between
            neck = i
            break
        head_w = max(head_w, w)
    if neck is None:
        neck = int(0.15 * tall / step)
    bottom = z1 - neck * step
    inside = column[(column[:, 2] >= bottom) & (np.abs(column[:, 0] - cx) <= head_w * 1.05)]
    return [[cx - head_w, float(inside[:, 1].min()), bottom], [cx + head_w, float(inside[:, 1].max()), z1]]


def front_depth(meshes, box, cells=48):
    """How far forward the surface is, seen from the front, on a grid over the box (rows from the top): NaN where nothing is hit."""
    verts, polys, base = [], [], 0
    for o in meshes:
        me, m = o.data, o.matrix_world
        verts += [tuple(m @ v.co) for v in me.vertices]
        polys += [tuple(base + i for i in p.vertices) for p in me.polygons]
        base += len(me.vertices)
    tree = BVHTree.FromPolygons(verts, polys)
    (x0, y0, z0), (x1, y1, z1) = box
    reach = (y1 - y0) * 1.5
    grid = np.full((cells, cells), np.nan, dtype=np.float32)
    for r in range(cells):
        z = z1 - (r + 0.5) / cells * (z1 - z0)
        for c in range(cells):
            x = x0 + (c + 0.5) / cells * (x1 - x0)
            hit = tree.ray_cast(Vector((x, y0 - reach, z)), Vector((0, 1, 0)), reach + (y1 - y0))
            if hit[0] is not None:
                grid[r, c] = hit[0].y
    return grid


def against(reference, depth, box):
    """A version's head against the detailed one, seen from the front: the share of the head that is missing (a hole, or
    the surface more than 8% of the head's height behind), and how far the rest sits off, as % of the head's height."""
    tall = box[1][2] - box[0][2]
    there = ~np.isnan(reference)
    gap = np.abs(depth - reference) / tall * 100
    missing = there & (np.isnan(depth) | ((depth - reference) / tall > 0.08))
    kept = there & ~missing
    return {"missing_pct": round(100 * float(missing.sum()) / max(int(there.sum()), 1), 1),
            "off_typical_pct": round(float(np.median(gap[kept])), 2) if kept.any() else None,
            "off_p95_pct": round(float(np.percentile(gap[kept], 95)), 2) if kept.any() else None}


def render_views(scene, box, tag, shift=None):
    """Three close-ups of the box; returns {view: path}."""
    low, high = Vector(box[0]), Vector(box[1])
    if shift:
        low, high = low + shift, high + shift
    center, span = (low + high) / 2, max(high.x - low.x, high.z - low.z, high.y - low.y) * 1.3
    cam = bpy.data.objects.new("sheet camera", bpy.data.cameras.new("sheet camera"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = span
    cam.data.clip_end = 100
    sun = bpy.data.objects.new("sheet light", bpy.data.lights.new("sheet light", "SUN"))
    sun.data.energy, sun.data.angle = 2.5, 0.5
    for o in (cam, sun):
        scene.collection.objects.link(o)
    sky = bpy.data.worlds.new("sheet sky")
    sky.use_nodes = True
    sky.node_tree.nodes["Background"].inputs["Color"].default_value = (0.75, 0.75, 0.78, 1.0)
    sky.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.7
    scene.world, scene.camera = sky, cam
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.view_settings.view_transform = "Standard"
    paths = {}
    for view, away in VIEWS.items():
        cam.location = center + away * 10
        cam.rotation_euler = (-away).to_track_quat("-Z", "Y").to_euler()
        sun.rotation_euler = (-(away + Vector((0, 0, 0.7)) + away.cross(Vector((0, 0, 1))) * 0.5)).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(tiles_dir, "%s-%s.png" % (tag, view))
        bpy.ops.render.render(write_still=True)
        paths[view] = scene.render.filepath
    return paths


def head_drift(scene, rig, meshes, box):
    """Over the clip: how far the head's points move against the head bone, as % of the head's height (worst point, any frame),
    and the share of the head's points that are not carried by the head bone alone."""
    if "head" not in rig.pose.bones:
        return None
    low, high = np.array(box[0]), np.array(box[1])
    action = rig.animation_data.action
    first, last = [int(round(f)) for f in action.frame_range]
    rest = np.array(rig.matrix_world @ rig.data.bones["head"].matrix_local)
    rest_inv = np.linalg.inv(rest)
    scene.frame_set(first)
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    base = world_points(meshes, bpy.context.evaluated_depsgraph_get())
    rig.data.pose_position = "POSE"
    pick = np.all((base >= low) & (base <= high), axis=1)
    pick &= base[:, 2] >= low[2] + 0.4 * (high[2] - low[2])  # from the nose up: the top of the neck piece reaches inside the jaw
    local = np.c_[base[pick], np.ones(pick.sum())] @ rest_inv.T
    worst = 0.0
    for frame in range(first, last + 1, max(1, (last - first) // 12)):
        scene.frame_set(frame)
        deps = bpy.context.evaluated_depsgraph_get()
        now = world_points(meshes, deps)[pick]
        bone = np.array(rig.matrix_world @ rig.pose.bones["head"].matrix)
        moved = np.c_[now, np.ones(len(now))] @ np.linalg.inv(bone).T
        worst = max(worst, float(np.linalg.norm(moved[:, :3] - local[:, :3], axis=1).max()))
    return {"face_bends_pct_of_head": round(100 * worst / (high[2] - low[2]), 2), "points": int(pick.sum())}


def read_png(path):
    image = bpy.data.images.load(path)
    w, h = image.size
    px = np.empty(w * h * 4, dtype=np.float32)
    image.pixels.foreach_get(px)
    bpy.data.images.remove(image)
    return px.reshape(h, w, 4)[::-1]  # top row first


def write_png(pixels, path):
    h, w = pixels.shape[:2]
    image = bpy.data.images.new("sheet", w, h, alpha=True)
    image.pixels.foreach_set(np.ascontiguousarray(pixels[::-1], dtype=np.float32).ravel())
    image.filepath_raw, image.file_format = path, "PNG"
    image.save()
    bpy.data.images.remove(image)


def resize(pixels, to):
    h, w = pixels.shape[:2]
    ys = np.clip(((np.arange(to) + 0.5) * h / to).astype(int), 0, h - 1)
    xs = np.clip(((np.arange(to) + 0.5) * w / to).astype(int), 0, w - 1)
    return pixels[ys][:, xs]


def picture_head(path, body, box):
    """Cut the head out of the source picture: the picture shows the whole figure front-on, so the head's
    box, as a share of the figure's box, says where to cut. Framed like the front tiles."""
    px = read_png(path)
    h, w = px.shape[:2]
    back = px[:8, :8, :3].reshape(-1, 3).mean(axis=0)
    mask = np.abs(px[:, :, :3] - back).sum(axis=2) > 0.12
    rows, cols = np.where(mask.any(axis=1))[0], np.where(mask.any(axis=0))[0]
    top, bottom, left, right = rows[0], rows[-1], cols[0], cols[-1]
    per_m = (bottom - top) / (body[1][2] - body[0][2])
    mid_m = (box[0][0] + box[1][0]) / 2
    # the figure's middle, read off the picture's own head rows: the arms may not be the same length in the picture
    head_rows = mask[top:top + max(2, int((box[1][2] - box[0][2]) * per_m))]
    head_cols = np.where(head_rows.any(axis=0))[0]
    cx = (head_cols[0] + head_cols[-1]) / 2 if len(head_cols) else (left + right) / 2
    cz = top + (body[1][2] - (box[0][2] + box[1][2]) / 2) * per_m
    span = max(box[1][0] - box[0][0], box[1][2] - box[0][2], box[1][1] - box[0][1]) * 1.3 * per_m
    x0, y0 = int(round(cx - span / 2)), int(round(cz - span / 2))
    n = int(round(span))
    cut = np.ones((n, n, 4), dtype=np.float32) * np.array([back[0], back[1], back[2], 1.0], dtype=np.float32)
    ys, xs = np.arange(n) + y0, np.arange(n) + x0
    ok_y, ok_x = (ys >= 0) & (ys < h), (xs >= 0) & (xs < w)
    cut[np.ix_(ok_y, ok_x)] = px[np.ix_(ys[ok_y], xs[ok_x])]
    cut[:, :, 3] = 1.0
    return resize(cut, size), {"x0": x0, "y0": y0, "span_px": n, "per_m": float(per_m), "mid_m": mid_m}


# Which files to draw, top to bottom.
versions = []
detailed = next((os.path.join(run, n) for n in ("final.glb", "mesh.glb") if os.path.exists(os.path.join(run, n))), None)
if detailed:
    versions.append(("detailed" if detailed.endswith("final.glb") else "raw mesh", detailed))
for name in ("web", "game", "midpoly", "lowpoly", "midpoly-walk", "lowpoly-walk"):
    path = os.path.join(run, "profiles", name + ".glb")
    if os.path.exists(path):
        versions.append((name, path))
if only:
    versions = [v for v in versions if v[0] in only]
for item in also:
    label, _, path = item.partition("=")
    versions.append((label, os.path.abspath(path)))

box = None
if box_arg:
    v = [float(x) for x in box_arg.split(",")]
    box = [v[:3], v[3:]]
recipe = os.path.join(run, "lowpoly_build.json")
if box is None and os.path.exists(recipe):
    with open(recipe) as f:
        heads = [p for p in json.load(f).get("pieces", []) if "head" in p]
    if heads:
        box = [heads[0]["box"]["min"], heads[0]["box"]["max"]]

report = {"run": run, "versions": [], "views": list(VIEWS)}
rows, body, reference = [], None, None
for label, path in versions:
    scene, meshes = load(path)
    tag = label.replace(" ", "-")
    rig = next((o for o in scene.objects if o.type == "ARMATURE"), None)
    if body is None:
        pts = world_points(meshes)
        body = [pts.min(axis=0).tolist(), pts.max(axis=0).tolist()]
        if box is None:
            box = find_head(pts)
        report["box"], report["body"] = box, body
    entry = {"label": label, "file": path, "tiles": []}
    if rig and rig.animation_data and rig.animation_data.action:
        entry["walk"] = head_drift(scene, rig, meshes, box)
        first, last = [int(round(f)) for f in rig.animation_data.action.frame_range]
        for share in (0.25, 0.75):
            frame = int(first + (last - first) * share)
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            shift = None
            if "head" in rig.pose.bones:
                shift = rig.matrix_world @ rig.pose.bones["head"].head - rig.matrix_world @ rig.data.bones["head"].head_local
            paths = render_views(scene, box, "%s-f%d" % (tag, frame), shift)
            entry["tiles"].append(paths)
            rows.append(("%s @%d" % (label, frame), paths))
    else:
        depth = front_depth(meshes, box)
        if reference is None:
            reference = depth
        else:
            entry["shape"] = against(reference, depth, box)
        paths = render_views(scene, box, tag)
        entry["tiles"].append(paths)
        rows.append((label, paths))
    report["versions"].append(entry)

# The sheet: the picture's head, then a row per version.
picture = os.path.join(run, "image.png")
gap = 4
grid = np.ones(((len(rows) + 1) * (size + gap) + gap, 3 * (size + gap) + gap, 4), dtype=np.float32)
grid[:, :, :3] = 0.15
if os.path.exists(picture) and body:
    cut, where = picture_head(picture, body, box)
    write_png(cut, os.path.join(tiles_dir, "picture-front.png"))
    report["picture"] = dict(where, tile=os.path.join(tiles_dir, "picture-front.png"))
    grid[gap:gap + size, gap:gap + size] = cut
for r, (label, paths) in enumerate(rows):
    for c, view in enumerate(VIEWS):
        tile = read_png(paths[view])
        y, x = gap + (r + 1) * (size + gap), gap + c * (size + gap)
        grid[y:y + size, x:x + size] = tile[:size, :size]
write_png(grid, out)
report["rows"] = ["picture"] + [label for label, _ in rows]
with open(os.path.splitext(out)[0] + ".json", "w") as f:
    json.dump(report, f, indent=1)
print("FACES %s: %d rows (%s)" % (out, len(rows) + 1, ", ".join(report["rows"])))
