"""Measure whether a block-out version's colors are the right ones: does each
piece of gear show its own cloth, and the body its own skin?

    blender -b --factory-startup -P scripts/bake_check.py -- SCENE.blend FILE.glb [FILE.glb ...] [--sheet OUT.png] [--px 220]

SCENE.blend is the run's scene (the detailed mesh, as the picture showed
the character: dressed). FILE is a low-poly or mid-poly version of it
(profiles/lowpoly.glb, midpoly.glb), with its gear as separate meshes.

Both are looked at straight on from the front, the back and both sides, with
no light: only the color each surface carries. Wherever the same spot shows
both, the two colors are compared (their distance in CIELAB, "dE": under 5
is hard to see, 10 is a clear shift, over 25 is a different color). For each
file it prints one line, `BAKE {json}`:

- "gear": for each piece, how many spots were compared; the mean dE and the
  share over 25 ("wrong_%") among the spots where the detailed mesh shows
  that piece (a block-out's kilt is a little bigger than the real one, so
  some of its spots lie over the leg: copying the leg there is no virtue);
  and "takes_skin_%": the share of all its spots that are nearer the body's
  skin color than the piece's own. That is a kilt painted with the leg
  under it. It only means something when the two colors are well apart
  ("color_apart_from_skin_dE").
- "body": the same for the head, the arms, the trunk and the legs, where
  they show with the gear on.
- "under": with the gear off, the skin each piece hid: how far it is from
  the color of the skin that shows (dE), and "takes_cloth_%", the share
  nearer the piece's color than the skin's. That is a thigh painted kilt.
- "all": every spot together.

A block-out sits a little off the detailed mesh, so edges never line up
exactly: 6 to 10 dE is what a good bake scores here. Compare a file with
another made from the same block-out.

--sheet writes a picture: one row per view; the detailed mesh, then each
file, then each file with its gear off. Nothing else is written.
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

VIEWS = (("front", (0, 1, 0), (1, 0, 0)), ("back", (0, -1, 0), (-1, 0, 0)),
         ("left", (-1, 0, 0), (0, 1, 0)), ("right", (1, 0, 0), (0, -1, 0)))  # name, the way the eye looks, the picture's right
WRONG = 25.0   # dE past which a spot is a different color
LAYER = 0.08   # the two surfaces must be within this share of the height to be the same spot


def srgb(linear):
    linear = np.clip(linear, 0.0, 1.0)
    return np.where(linear <= 0.0031308, linear * 12.92, 1.055 * np.power(linear, 1 / 2.4) - 0.055)


def lab(rgb):
    """sRGB (0-1) to CIELAB."""
    rgb = np.clip(np.asarray(rgb, dtype=np.float64), 0.0, 1.0)
    lin = np.where(rgb <= 0.04045, rgb / 12.92, np.power((rgb + 0.055) / 1.055, 2.4))
    xyz = lin @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]])
    xyz = xyz / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def pixels_of(img):
    w, h = img.size
    flat = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(flat)
    return flat.reshape(h, w, 4)[:, :, :3]


def base_color(mat):
    """A material's color as (texture pixels or None, flat sRGB color)."""
    if mat is None or not mat.use_nodes:
        return None, np.array([0.6, 0.6, 0.6])
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return None, np.array([0.6, 0.6, 0.6])
    sock = bsdf.inputs["Base Color"]
    node = sock.links[0].from_node if sock.is_linked else None
    while node is not None and node.type == "MIX" and node.inputs[6].is_linked:  # the importer multiplies vertex color in
        node = node.inputs[6].links[0].from_node
    if node is not None and node.type == "TEX_IMAGE" and node.image:
        return node.image, None
    if node is not None and node.type in ("VERTEX_COLOR", "ATTRIBUTE"):
        return "paint", None
    return None, srgb(np.array(sock.default_value[:3]))


def surface(objects, labels):
    """Triangles of the objects in world space, ready to look at: a BVH tree and, per triangle, its
    label, its corners' UVs or colors, and what colors it."""
    points, tris, label, uv, paint, source = [], [], [], [], [], []
    sources = []
    for obj, name in zip(objects, labels):
        me = obj.data
        me.calc_loop_triangles()
        start = len(points)
        points += [obj.matrix_world @ v.co for v in me.vertices]
        uvs = me.uv_layers.active
        colors = me.color_attributes[0] if me.color_attributes else None
        kinds = []
        for slot in obj.material_slots or [None]:
            image, flat = base_color(slot.material if slot else None)
            if isinstance(image, str) or (image is None and flat is None):
                kinds.append(("paint", None))
            elif image is not None:
                kinds.append(("image", pixels_of(image)))
            else:
                kinds.append(("flat", flat))
        if not obj.material_slots and colors is not None:
            kinds = [("paint", None)]
        for t in me.loop_triangles:
            tris.append(tuple(start + i for i in t.vertices))
            label.append(name)
            kind = kinds[min(t.material_index, len(kinds) - 1)]
            if kind[0] == "paint" and colors is None:
                kind = ("flat", np.array([0.6, 0.6, 0.6]))
            source.append(len(sources))
            sources.append(kind)
            uv.append([tuple(uvs.data[i].uv) for i in t.loops] if uvs else [(0, 0)] * 3)
            if colors is not None:
                at = t.loops if colors.domain == "CORNER" else t.vertices
                paint.append([tuple(colors.data[i].color[:3]) for i in at])
            else:
                paint.append([(0, 0, 0)] * 3)
    # one entry per material kind, not per triangle
    seen, compact, remap = {}, [], []
    for kind in sources:
        key = (kind[0], id(kind[1]) if kind[0] == "image" else (tuple(kind[1]) if kind[1] is not None else None))
        if key not in seen:
            seen[key] = len(compact)
            compact.append(kind)
        remap.append(seen[key])
    return {"tree": BVHTree.FromPolygons([tuple(p) for p in points], tris) if tris else None,
            "points": np.array([tuple(p) for p in points], dtype=np.float64).reshape(-1, 3),
            "tris": np.array(tris, dtype=np.int64).reshape(-1, 3), "label": label,
            "uv": np.array(uv, dtype=np.float64).reshape(-1, 3, 2), "paint": np.array(paint, dtype=np.float64).reshape(-1, 3, 3),
            "source": np.array(remap, dtype=np.int64), "sources": compact}


def look(surf, origins, way, far):
    """What each ray sees: (hit or not, sRGB color, depth, triangle index)."""
    n = len(origins)
    hit = np.zeros(n, dtype=bool)
    tri = np.zeros(n, dtype=np.int64)
    depth = np.zeros(n)
    where = np.zeros((n, 3))
    if surf["tree"] is None:
        return hit, np.zeros((n, 3)), depth, tri
    cast, toward = surf["tree"].ray_cast, Vector(way)
    for i, o in enumerate(origins):
        loc, _, index, dist = cast(Vector(o), toward, far)
        if loc is not None:
            hit[i], tri[i], depth[i], where[i] = True, index, dist, loc
    color = np.zeros((n, 3))
    if not hit.any():
        return hit, color, depth, tri
    ids = tri[hit]
    a, b, c = (surf["points"][surf["tris"][ids, k]] for k in range(3))
    p = where[hit]
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
    den = np.where(np.abs(d00 * d11 - d01 * d01) < 1e-20, 1.0, d00 * d11 - d01 * d01)
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    bary = np.stack([1 - v - w, v, w], axis=1)
    got = np.zeros((len(ids), 3))
    which = surf["source"][ids]
    for s, (kind, data) in enumerate(surf["sources"]):
        m = which == s
        if not m.any():
            continue
        if kind == "flat":
            got[m] = data
        elif kind == "paint":
            got[m] = srgb((surf["paint"][ids[m]] * bary[m][:, :, None]).sum(1))
        else:
            at = (surf["uv"][ids[m]] * bary[m][:, :, None]).sum(1)
            h, wd = data.shape[:2]
            x = np.clip((at[:, 0] % 1.0) * wd, 0, wd - 1).astype(np.int64)
            y = np.clip((at[:, 1] % 1.0) * h, 0, h - 1).astype(np.int64)
            got[m] = data[y, x]
    color[hit] = got
    return hit, color, depth, tri


def plain_texture(obj, size=2048):
    """The detailed mesh's color as one plain texture on its own UVs, whatever its shader does on the way."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 1
    img = bpy.data.images.new("check: detailed color", size, size, alpha=False)
    undo = []
    for slot in obj.material_slots:
        mat = slot.material
        tree = mat.node_tree
        bsdf = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
        out = next(n for n in tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output)
        emit = tree.nodes.new("ShaderNodeEmission")
        sock = bsdf.inputs["Base Color"]
        if sock.is_linked:
            tree.links.new(sock.links[0].from_socket, emit.inputs["Color"])
        else:
            emit.inputs["Color"].default_value = sock.default_value
        old = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].is_linked else None
        tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = img
        tree.nodes.active = node
        undo.append((tree, emit, node, out, old))
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.bake(type="EMIT", margin=4, use_clear=True)
    for tree, emit, node, out, old in undo:
        if old is not None:
            tree.links.new(old, out.inputs["Surface"])
        tree.nodes.remove(emit)
        tree.nodes.remove(node)
    return pixels_of(img)


def region(point, marks):
    """Which part of the body a spot is on, roughly: head, arms, trunk or legs."""
    x, _, z = point
    if z < marks["hip"]:
        return "legs"
    if z > marks["chin"]:
        return "head"
    if abs(x - marks["mid"]) > marks["shoulder"]:
        return "arms"
    return "trunk"


def stats(d):
    return {"spots": int(len(d)), "dE": round(float(d.mean()), 1), "wrong_%": round(float((d > WRONG).mean() * 100), 1)} if len(d) else {"spots": 0}


def measure(path, full, low, high, px, sheet):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    if len(meshes) == 1 and not meshes[0].get("forge"):
        meshes[0]["forge"] = "body"
    worn = [o for o in meshes if o.get("forge") == "gear"]
    shown = [o for o in meshes if o.get("forge") == "body" and not o.get("under")]
    hidden = [o for o in meshes if o.get("forge") == "body" and o.get("under")]
    dressed = surface(worn + shown, [o["gear"] for o in worn] + ["body"] * len(shown))
    bare = surface(shown + hidden, ["body"] * len(shown) + [o["under"] for o in hidden])
    sockets = {o["socket"]: o.matrix_world.translation for o in new if o.get("socket")}
    size = high - low
    top = sockets["head"].z if "head" in sockets else high.z
    hip = sockets["hip"].z if "hip" in sockets else low.z + 0.5 * size.z
    reach = max(abs(sockets[k].x) for k in ("hand_left", "hand_right")) if "hand_left" in sockets else size.x / 2
    marks = {"hip": hip, "chin": hip + 0.7 * (top - hip), "mid": (low.x + high.x) / 2, "shoulder": 0.32 * reach}
    step = size.z / px
    far = size.length * 3
    rows = {"gear": {}, "body": {}, "under": {}, "all": []}
    cells = []
    for name, way, right in VIEWS:
        way, right, up = np.array(way, dtype=float), np.array(right, dtype=float), np.array([0.0, 0.0, 1.0])
        middle = np.array((low + high) / 2)
        wide = abs(right @ np.array(size)) + 4 * step
        nx, nz = int(wide / step), int(size.z / step) + 4
        us = (np.arange(nx) - (nx - 1) / 2) * step
        vs = ((nz - 1) / 2 - np.arange(nz)) * step
        origins = (middle - way * size.length)[None, None, :] + us[None, :, None] * right[None, None, :] + vs[:, None, None] * up[None, None, :]
        origins = origins.reshape(-1, 3)
        f_hit, f_col, f_depth, _ = look(full, origins, way, far)
        d_hit, d_col, d_depth, d_tri = look(dressed, origins, way, far)
        b_hit, b_col, b_depth, b_tri = look(bare, origins, way, far)
        same = f_hit & d_hit & (np.abs(f_depth - d_depth) < LAYER * size.z)
        de = np.linalg.norm(lab(f_col) - lab(d_col), axis=1)
        labels = np.array([dressed["label"][t] if h else "" for t, h in zip(d_tri, d_hit)])
        spots = origins + way[None, :] * d_depth[:, None]
        for i in np.nonzero(same)[0]:
            if labels[i] == "body":
                rows["body"].setdefault(region(spots[i], marks), []).append((de[i], f_col[i], d_col[i]))
            else:
                rows["gear"].setdefault(labels[i], []).append((de[i], f_col[i], d_col[i]))
            rows["all"].append(de[i])
        under = np.array([bare["label"][t] if h else "" for t, h in zip(b_tri, b_hit)])
        for i in np.nonzero(b_hit & d_hit & (labels != "body") & (labels != ""))[0]:  # skin a piece covers, seen with the gear off
            rows["under"].setdefault(labels[i], []).append(b_col[i])
        if sheet is not None:
            heat = np.zeros_like(d_col)
            heat[same] = np.stack([np.clip(de[same] / 50, 0, 1), np.clip(1 - de[same] / 50, 0, 1) * 0.6, np.zeros(same.sum())], axis=1)
            bg = np.array([0.42, 0.42, 0.42])
            cells.append((name, nz, nx, [np.where(h[:, None], c, bg).reshape(nz, nx, 3) for h, c in
                                         ((f_hit, f_col), (d_hit, d_col), (b_hit, b_col), (d_hit, np.where(same[:, None], heat, bg)))]))
    skin_seen = [r for part in rows["body"].values() for r in part]
    skin_full = np.median(lab(np.array([r[1] for r in skin_seen])), axis=0) if skin_seen else None
    skin_low = np.median(lab(np.array([r[2] for r in skin_seen])), axis=0) if skin_seen else None
    result = {"file": path, "gear": {}, "body": {}, "under": {}, "all": stats(np.array(rows["all"]))}
    for part, got in sorted(rows["body"].items()):
        result["body"][part] = stats(np.array([r[0] for r in got]))
    for gear, got in sorted(rows["gear"].items()):
        de = np.array([r[0] for r in got])
        ref, now = lab(np.array([r[1] for r in got])), lab(np.array([r[2] for r in got]))
        own = np.median(ref, axis=0)
        row = stats(de)
        if skin_full is not None:
            # where the detailed mesh itself shows the piece there, not the skin beside or under it
            truly = np.linalg.norm(ref - own, axis=1) <= np.linalg.norm(ref - skin_full, axis=1)
            row = stats(de[truly]) if truly.any() else row
            row["spots"] = int(len(de))
            row["color_apart_from_skin_dE"] = round(float(np.linalg.norm(own - skin_full)), 1)
            row["takes_skin_%"] = round(float((np.linalg.norm(now - skin_full, axis=1) < np.linalg.norm(now - own, axis=1)).mean() * 100), 1)
        result["gear"][gear] = row
        if gear in rows["under"] and skin_low is not None:
            skin = lab(np.array(rows["under"][gear]))
            cloth = np.median(now, axis=0)
            off = np.linalg.norm(skin - skin_low, axis=1)
            result["under"][gear] = {"spots": int(len(skin)), "dE_from_the_skin_that_shows": round(float(off.mean()), 1),
                                     "takes_cloth_%": round(float((np.linalg.norm(skin - cloth, axis=1) < off).mean() * 100), 1)}
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    return result, cells


def save_sheet(path, columns):
    """columns: one list of (view name, rows, cols, picture) per column; the same views down each."""
    gap = 6
    heights = [c[1] for c in columns[0]]
    widths = [[c[2] for c in col] for col in columns]
    width = sum(max(w) + gap for w in widths) + gap
    height = sum(h + gap for h in heights) + gap
    canvas = np.full((height, width, 4), 0.42, dtype=np.float32)
    canvas[:, :, 3] = 1.0
    x = gap
    for col, ws in zip(columns, widths):
        y = gap
        for (_, nz, nx, picture) in col:
            canvas[y:y + nz, x:x + nx, :3] = picture
            y += nz + gap
        x += max(ws) + gap
    img = bpy.data.images.new("check sheet", width, height, alpha=False)
    img.pixels.foreach_set(canvas[::-1].reshape(-1))
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()


def main(argv):
    sheet, px = None, 220
    if "--sheet" in argv:
        i = argv.index("--sheet")
        sheet = os.path.abspath(argv[i + 1])
        del argv[i:i + 2]
    if "--px" in argv:
        i = argv.index("--px")
        px = int(argv[i + 1])
        del argv[i:i + 2]
    if len(argv) < 2:
        sys.exit("usage: bake_check.py -- SCENE.blend FILE.glb [FILE.glb ...] [--sheet OUT.png] [--px 220]")
    if argv[0].endswith(".blend"):
        bpy.ops.wm.open_mainfile(filepath=os.path.abspath(argv[0]))
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=os.path.abspath(argv[0]))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get()]
    detailed = max(meshes, key=lambda o: len(o.data.polygons))
    texture = plain_texture(detailed)
    full = surface([detailed], ["detailed"])
    full["sources"] = [("image", texture)]
    full["source"][:] = 0
    corners = [detailed.matrix_world @ Vector(c) for c in detailed.bound_box]
    low = Vector([min(c[i] for c in corners) for i in range(3)])
    high = Vector([max(c[i] for c in corners) for i in range(3)])
    columns = []
    for path in argv[1:]:
        result, cells = measure(os.path.abspath(path), full, low, high, px, sheet)
        print("BAKE " + json.dumps(result))
        if sheet:
            if not columns:
                columns.append([(c[0], c[1], c[2], c[3][0]) for c in cells])
            columns.append([(c[0], c[1], c[2], c[3][1]) for c in cells])
            columns.append([(c[0], c[1], c[2], c[3][2]) for c in cells])
            columns.append([(c[0], c[1], c[2], c[3][3]) for c in cells])
    if sheet:
        save_sheet(sheet, columns)
        print("SHEET " + sheet)


main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
