# Cut the clothes that hide a character's body out of its clothed mesh, so
# they can go back on a real body instead of a guessed one.
#
# It works from four files of one character: the clothed picture and the
# mesh made from it, and a second picture of the same character without the
# hiding clothes (edited from the first: same pose, same framing) and the
# mesh made from that, the "base body". Nothing under the clothes is guessed:
# the body is the base body, and each garment is the part of the clothed mesh
# that is that garment.
#
# In order:
#   1. The pictures. Where the two differ is the garment, seen from the
#      front. If the figure moved or changed size between them, or nothing
#      changed, it stops here ("pictures": "ok" false, and why).
#   2. The framing. TRELLIS.2 centers the figure and scales it to fill its
#      box, front toward -Y, so a face at (x, z) lands in the picture at a
#      column and row found from the two outlines' edges. "view" says how
#      well the mesh's outline then covers the figure in the picture.
#   3. The fit. The base body is laid on the clothed mesh using only the
#      parts the clothes don't cover (head, arms, feet...), by size and
#      position, never by bending. "fit" says how far apart those parts
#      still are, as a share of the height; over the limits it stops
#      ("fit": "ok" false) and cuts nothing.
#   4. The cut. Each face of the clothed mesh gets three votes, and is
#      garment when two agree:
#        picture   it lands where the pictures differ
#        color     its texture color is one the garment has in the picture,
#                  and the rest of the figure doesn't (this reaches the back,
#                  which the picture can't see)
#        distance  it stands off the base body by more than "gap"
#      Then the cut is carried up to where the colors change (so a skirt
#      comes whole to its waistband, through the blurred texels along it),
#      the edge is evened out, small scraps are dropped ("crumb") and small
#      holes are closed ("pinhole"). Where the real body is a little fuller
#      than the clothed mesh's guess, the garment is lifted onto it ("seat").
#   5. With several garments, each face goes to the one whose "slot" is at
#      its height (a hood above a robe).
# For each garment the result says how much of the clothed mesh it is, where
# its top and bottom are (shares of the height), how far round it is whole
# just under its top ("closed_round_its_top_pct": 100 is a whole waistband)
# and how much of it is in colors that belong to the rest of the figure
# ("other_colors_pct": scraps of tights or shoes would show here).
#
# It writes one .glb per garment into "out" (named for the garment, still
# where the clothed mesh has it) and the base body, moved to fit, as
# "body_out". "overlay" also renders the clothed mesh front, quarter and
# back with every face colored by which votes it got ("overlay_colors").
# With no meshes given it only checks the pictures.
#
# Run it in a background Blender (scripts/tidy_headless.py with "-" for the
# mesh). Prints RESULT {json}. About a minute on two 300k-triangle meshes.
# Safe-mode compatible.

PARAMS = {
    "picture": None,       # the clothed picture, .png (required)
    "base_picture": None,  # the same character without the hiding clothes, .png (required)
    "clothed": None,       # the clothed mesh, .glb; None = only check the pictures
    "base": None,          # the base body's mesh, .glb
    "garments": [],        # [{"name": "ruffled skirt", "slot": "hip", "kind": "worn"}]: the clothes that were taken off
    "out": None,           # folder for the garment .glb files; None = measure only
    "body_out": None,      # where to write the base body once it is laid on the clothed mesh, .glb
    "overlay": None,       # path stem for the vote renders: writes <stem>-front.png, -quarter.png, -back.png
    "gap": 0.015,          # "distance" vote: farther than this from the base body, as a share of the height
    "change": 0.14,        # "picture" vote: how different a pixel must be (0-1) to count as changed
    "grid": 384,           # the pictures are compared at this many pixels across
    "seat": 0.003,         # lift garment points inside the base body out onto it, this far off it (share of the height); None = leave them
    "crumb": 0.01,         # drop garment scraps smaller than this share of the garment
    "pinhole": 0.01,       # close holes in the garment smaller than this share of it
    "limits": {            # stop when the two don't line up (all in % of the figure's height)
        "edge": 2.0,       #   an edge of the figure (head top, hands, feet) moved more than this between the pictures
        "slivers": 6.0,    #   more than this share of the figure changed in thin slivers (it shifted or was redrawn)
        "median": 0.8,     #   uncovered parts of the base body sit this far off the clothed mesh, typically
        "p90": 2.5,        #   ...and nine in ten of them within this
        "view": 70.0,      #   seen from the front, a mesh's outline must cover this much of the figure in its picture (%)
    },
}

import bpy
import bmesh
import json
import math
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

LEVELS = 8  # color votes: red, green and blue each cut into this many steps
BANDS = {   # where on the body each slot sits, as shares of the height from the floor
    "head": [0.86, 1.0], "face": [0.86, 0.97], "neck": [0.8, 0.88], "torso": [0.45, 0.86],
    "arms": [0.6, 0.86], "hands": [0.6, 0.86], "back": [0.45, 0.86], "hip": [0.05, 0.58],
    "legs": [0.05, 0.55], "feet": [0.0, 0.08],
}
OVERLAY = {  # what each color in the vote renders means
    "picture + color + distance": [0.95, 0.95, 0.95],
    "picture + color": [0.2, 0.45, 0.9],
    "picture + distance": [0.95, 0.75, 0.1],
    "color + distance": [0.8, 0.25, 0.8],
    "grown to the color seam, closed hole or evened edge (added)": [0.1, 0.75, 0.3],
    "crumb or evened edge (dropped)": [0.9, 0.15, 0.1],
    "one vote only (not garment)": [0.5, 0.47, 0.44],
    "no vote (not garment)": [0.3, 0.28, 0.27],
}


def spot(values, share):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))]

def slug_of(name):
    words = "".join([c if (c.isascii() and c.isalnum()) else " " for c in name.lower()]).split()
    return "-".join(words)


# ---- pictures --------------------------------------------------------------

def load_picture(path, wide, tall):
    image = bpy.data.images.load(path)
    w, h = image.size[0], image.size[1]
    if not tall:
        tall = max(1, int(round(wide * h / w)))
    image.scale(wide, tall)
    px = image.pixels[:]
    bpy.data.images.remove(image)
    return px, wide, tall, [w, h]

def backdrop(px, wide, tall):
    """The plain background's color: the middle value around the border."""
    reds, greens, blues = [], [], []
    for v in range(tall):
        step = 1 if v in (0, tall - 1) else wide - 1
        for u in range(0, wide, step):
            at = (v * wide + u) * 4
            reds.append(px[at])
            greens.append(px[at + 1])
            blues.append(px[at + 2])
    return [spot(reds, 0.5), spot(greens, 0.5), spot(blues, 0.5)]

def figure_mask(px, wide, tall, back):
    """1 where the picture isn't background. Row 0 is the top."""
    mask = bytearray(wide * tall)
    for v in range(tall):
        row = (tall - 1 - v) * wide
        for u in range(wide):
            at = (row + u) * 4
            if abs(px[at] - back[0]) > 0.08 or abs(px[at + 1] - back[1]) > 0.08 or abs(px[at + 2] - back[2]) > 0.08:
                mask[v * wide + u] = 1
    return mask

def changed_mask(a, b, wide, tall, figure_a, figure_b, change):
    mask = bytearray(wide * tall)
    for v in range(tall):
        row = (tall - 1 - v) * wide
        for u in range(wide):
            i = v * wide + u
            if not (figure_a[i] or figure_b[i]):
                continue
            at = (row + u) * 4
            if abs(a[at] - b[at]) > change or abs(a[at + 1] - b[at + 1]) > change or abs(a[at + 2] - b[at + 2]) > change:
                mask[i] = 1
    return mask

def grown(mask, wide, tall, shrink=False):
    """One pixel wider all round (or narrower)."""
    out = bytearray(mask)
    want = 0 if shrink else 1
    for v in range(tall):
        for u in range(wide):
            i = v * wide + u
            if mask[i] == want:
                continue
            if ((u > 0 and mask[i - 1] == want) or (u < wide - 1 and mask[i + 1] == want)
                    or (v > 0 and mask[i - wide] == want) or (v < tall - 1 and mask[i + wide] == want)):
                out[i] = want
    return out

def patches(mask, wide, tall, of):
    """Connected patches of pixels equal to `of`: [[pixel, ...], ...]."""
    seen = bytearray(wide * tall)
    found = []
    for start in range(wide * tall):
        if mask[start] != of or seen[start]:
            continue
        seen[start] = 1
        stack, patch = [start], []
        while stack:
            i = stack.pop()
            patch.append(i)
            u = i % wide
            for j in (i - 1 if u > 0 else -1, i + 1 if u < wide - 1 else -1, i - wide, i + wide):
                if 0 <= j < wide * tall and mask[j] == of and not seen[j]:
                    seen[j] = 1
                    stack.append(j)
        found.append(patch)
    return found

def edges_of(mask, wide, tall):
    """[left, right, top, bottom] of a mask, in pixels."""
    left, right, top, bottom = wide, -1, tall, -1
    for v in range(tall):
        row = mask[v * wide:(v + 1) * wide]
        first = row.find(1)
        if first < 0:
            continue
        left = min(left, first)
        right = max(right, row.rfind(1))
        top = min(top, v)
        bottom = max(bottom, v)
    return [left, right, top, bottom]

def compare_pictures(params):
    """The garment as the pictures show it, and whether the figure held still."""
    a, wide, tall, size_a = load_picture(params["picture"], params["grid"], None)
    b, _, _, size_b = load_picture(params["base_picture"], wide, tall)
    figure_a = figure_mask(a, wide, tall, backdrop(a, wide, tall))
    figure_b = figure_mask(b, wide, tall, backdrop(b, wide, tall))
    raw = changed_mask(a, b, wide, tall, figure_a, figure_b, params["change"])
    figure_px = max(1, sum(figure_a))
    # thin slivers go (a figure redrawn a pixel over), small specks go, small holes close
    mask = grown(grown(grown(grown(raw, wide, tall, True), wide, tall, True), wide, tall), wide, tall)
    for patch in patches(mask, wide, tall, 1):
        if len(patch) < 0.004 * figure_px:
            for i in patch:
                mask[i] = 0
    kept_px = max(1, sum(mask))
    for patch in patches(mask, wide, tall, 0):
        if len(patch) < 0.03 * kept_px:
            for i in patch:
                mask[i] = 1
    near = grown(grown(mask, wide, tall), wide, tall)
    slivers = sum(1 for i in range(wide * tall) if raw[i] and not near[i])
    box_a, box_b = edges_of(figure_a, wide, tall), edges_of(figure_b, wide, tall)
    height = max(1, box_a[3] - box_a[2] + 1)
    reach = edges_of(near, wide, tall) if sum(mask) else [wide, -1, tall, -1]
    names = ["left", "right", "top", "bottom"]
    shifted, why = {}, []
    for k in range(4):
        off = 100.0 * (box_b[k] - box_a[k]) / height
        # an edge the garment itself reaches may move: a hood is the top, a robe the bottom
        garment_edge = abs(reach[k] - box_a[k]) <= 2
        shifted[names[k]] = {"moved_pct": round(off, 2), "garment_reaches_it": garment_edge}
        if abs(off) > params["limits"]["edge"] and not garment_edge:
            why.append("the figure's %s edge moved %.1f%% of its height between the pictures (limit %s)" % (names[k], off, params["limits"]["edge"]))
    changed = 100.0 * sum(1 for i in range(wide * tall) if mask[i] and figure_a[i]) / figure_px
    sliver_share = 100.0 * slivers / figure_px
    if size_a[0] * size_b[1] != size_a[1] * size_b[0]:
        why.append("the pictures are different shapes: %s and %s" % (size_a, size_b))
    if changed < 2.0:
        why.append("almost nothing changed between the pictures (%.1f%% of the figure): the clothes are still on" % changed)
    if changed > 92.0:
        why.append("nearly the whole figure changed (%.0f%%): it was redrawn, not edited" % changed)
    if sliver_share > params["limits"]["slivers"]:
        why.append("%.1f%% of the figure changed in thin slivers (limit %s): it shifted or was redrawn" % (sliver_share, params["limits"]["slivers"]))
    report = {
        "ok": not why, "why": why, "compared_at": [wide, tall],
        "changed_pct": round(changed, 1), "slivers_pct": round(sliver_share, 2), "edges": shifted,
    }
    held = {"a": a, "b": b, "wide": wide, "tall": tall, "figure_a": figure_a, "figure_b": figure_b,
            "mask": mask, "near": near, "box_a": box_a, "box_b": box_b}
    return report, held


# ---- meshes ----------------------------------------------------------------

def load_mesh(path, name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new_names = [o.name for o in bpy.data.objects if o not in before]
    meshes = [bpy.data.objects[n] for n in new_names if bpy.data.objects[n].type == "MESH"]
    if not meshes:
        raise ValueError("no mesh in %s" % path)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    world = obj.matrix_world.copy()
    obj.parent = None
    obj.data.transform(world)
    obj.matrix_world = Matrix.Identity(4)
    for n in new_names:
        o = bpy.data.objects.get(n)
        if o and o != obj:
            bpy.data.objects.remove(o, do_unlink=True)
    obj.name = name
    obj.select_set(False)
    return obj

def color_texture(obj):
    """The base-color texture's pixels, at most 1024 across: (pixels, width, height) or None."""
    for material in obj.data.materials:
        if not material or not material.node_tree:
            continue
        images = []
        for node in material.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image:
                to_color = any(link.to_socket.name == "Base Color" for link in node.outputs[0].links)
                images.append((0 if to_color else 1, node.image.name))
        if images:
            image = bpy.data.images[sorted(images)[0][1]].copy()
            if image.size[0] > 1024:
                image.scale(1024, max(1, int(1024 * image.size[1] / image.size[0])))
            px = image.pixels[:]
            size = (image.size[0], image.size[1])
            bpy.data.images.remove(image)
            return px, size[0], size[1]
    return None

def read_faces(bm, texture):
    """Per face: middle, area and texture color."""
    uv = bm.loops.layers.uv.active
    mids, areas, colors = [], [], []
    for f in bm.faces:
        mids.append(f.calc_center_median())
        areas.append(f.calc_area())
        if uv is None or texture is None:
            colors.append(None)
            continue
        px, w, h = texture
        s = t = 0.0
        for loop in f.loops:
            s += loop[uv].uv.x
            t += loop[uv].uv.y
        n = len(f.loops)
        at = ((int(t / n * h) % h) * w + (int(s / n * w) % w)) * 4
        colors.append((px[at], px[at + 1], px[at + 2]))
    return mids, areas, colors

def box_of(points):
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    return low, high

def view_of(low, high, edges):
    """How a point (x, z) of a mesh lands in the picture, from the two outlines' edges."""
    return {
        "left": edges[0], "right": edges[1] + 1, "top": edges[2],
        "per_x": (edges[1] + 1 - edges[0]) / max(1e-9, high[0] - low[0]),
        "per_z": (edges[3] + 1 - edges[2]) / max(1e-9, high[2] - low[2]),
        "x0": low[0], "z1": high[2], "mirrored": False,
    }

def pixel_of(view, p, wide, tall):
    """The picture pixel a point lands on, or -1 off the picture."""
    across = (p[0] - view["x0"]) * view["per_x"]
    u = int(view["right"] - across) if view["mirrored"] else int(view["left"] + across)
    v = int(view["top"] + (view["z1"] - p[2]) * view["per_z"])
    if u < 0 or v < 0 or u >= wide or v >= tall:
        return -1
    return v * wide + u

def check_view(view, mids, areas, colors, px, figure, wide, tall):
    """How well the mesh, seen from the front, covers the figure in the picture, and how far its colors are off."""
    depth = [1e9] * (wide * tall)
    front = [-1] * (wide * tall)
    for i in range(len(mids)):
        at = pixel_of(view, mids[i], wide, tall)
        if at >= 0 and mids[i][1] < depth[at]:
            depth[at] = mids[i][1]
            front[at] = i
    outline = bytearray(1 if f >= 0 else 0 for f in front)
    # a big face covers more than the one pixel its middle lands on
    for i in range(len(mids)):
        reach = min(8, int(0.6 * math.sqrt(areas[i]) * view["per_z"]))
        at = pixel_of(view, mids[i], wide, tall)
        if reach < 1 or at < 0:
            continue
        u0, v0 = at % wide, at // wide
        for v in range(max(0, v0 - reach), min(tall, v0 + reach + 1)):
            for u in range(max(0, u0 - reach), min(wide, u0 + reach + 1)):
                outline[v * wide + u] = 1
    outline = grown(grown(outline, wide, tall), wide, tall, True)
    both = either = 0
    off, counted = 0.0, 0
    for i in range(wide * tall):
        if outline[i] and figure[i]:
            both += 1
        if outline[i] or figure[i]:
            either += 1
        if front[i] >= 0 and figure[i] and colors[front[i]] is not None:
            at = ((tall - 1 - i // wide) * wide + i % wide) * 4
            c = colors[front[i]]
            off += abs(c[0] - px[at]) + abs(c[1] - px[at + 1]) + abs(c[2] - px[at + 2])
            counted += 1
    return {
        "overlap_pct": round(100.0 * both / max(1, either), 1),
        "color_off": round(off / max(1, 3 * counted), 3),
        "stretch": round(view["per_x"] / view["per_z"], 4),
        "mirrored": view["mirrored"],
    }

def best_view(mids, areas, colors, px, figure, edges, wide, tall):
    """The framing, facing whichever way matches the picture's colors better."""
    low, high = box_of(mids)
    view = view_of(low, high, edges)
    straight = check_view(view, mids, areas, colors, px, figure, wide, tall)
    flipped = dict(view)
    flipped["mirrored"] = True
    other = check_view(flipped, mids, areas, colors, px, figure, wide, tall)
    if other["color_off"] < straight["color_off"] - 0.01 and other["overlap_pct"] >= straight["overlap_pct"] - 1:
        return flipped, other
    return view, straight


# ---- laying the base body on the clothed mesh ------------------------------

def moved(p, fit):
    return Vector((p[0] * fit[0] + fit[1], p[1] * fit[0] + fit[2], p[2] * fit[0] + fit[3]))

def gaps(points, fit, tree):
    """Each point, moved, with the nearest spot on the clothed mesh and how far that is."""
    rows = []
    for p in points:
        q = moved(p, fit)
        hit = tree.find_nearest(q)
        if hit[0] is not None:
            rows.append((hit[3], q, hit[0]))
    return rows

def refit(points, fit, tree):
    """One step closer: the size and position that best carry the points onto their nearest spots."""
    rows = gaps(points, fit, tree)
    reach = max(3.0 * spot([r[0] for r in rows], 0.5), 0.004)
    pairs = [(points[i], rows[i][2]) for i in range(len(rows)) if rows[i][0] <= reach] if len(rows) == len(points) else []
    if len(pairs) < 50:
        return fit
    n = float(len(pairs))
    mid_p = Vector((0, 0, 0))
    mid_q = Vector((0, 0, 0))
    for p, q in pairs:
        mid_p += p
        mid_q += q
    mid_p /= n
    mid_q /= n
    top = bottom = 0.0
    for p, q in pairs:
        top += (p - mid_p).dot(q - mid_q)
        bottom += (p - mid_p).dot(p - mid_p)
    scale = top / bottom if bottom > 0 else 1.0
    return [scale, mid_q[0] - scale * mid_p[0], mid_q[1] - scale * mid_p[1], mid_q[2] - scale * mid_p[2]]

def lay_on(base_mids, base_view, held, clothed_box, clothed_view, tree, limits):
    """Fit the base body to the clothed mesh by its uncovered parts. Returns the fit and its report."""
    wide, tall = held["wide"], held["tall"]
    low, high = clothed_box
    height = high[2] - low[2]
    step = max(1, len(base_mids) // 6000)
    sample = [base_mids[i] for i in range(0, len(base_mids), step)]
    open_points = []
    for p in sample:
        at = pixel_of(base_view, p, wide, tall)
        if at >= 0 and not held["near"][at]:
            open_points.append(p)
    if len(open_points) < 200:
        open_points = sample  # the clothes cover nearly everything: use it all
    # two places to start: as the meshes came, and where the pictures put them
    b_low, b_high = box_of(base_mids)
    starts = {"as the meshes came": [1.0, 0.0, 0.0, 0.0]}
    for axis, name in ((0, "the pictures, by width"), (2, "the pictures, by height")):
        per_b = base_view["per_x"] if axis == 0 else base_view["per_z"]
        per_a = clothed_view["per_x"] if axis == 0 else clothed_view["per_z"]
        scale = per_b / per_a
        mid_u = (held["box_b"][0] + held["box_b"][1] + 1) / 2.0
        mid_v = (held["box_b"][2] + held["box_b"][3] + 1) / 2.0
        x = clothed_view["x0"] + (mid_u - clothed_view["left"]) / clothed_view["per_x"]
        z = clothed_view["z1"] - (mid_v - clothed_view["top"]) / clothed_view["per_z"]
        starts[name] = [scale, x - scale * (b_low[0] + b_high[0]) / 2.0, 0.0, z - scale * (b_low[2] + b_high[2]) / 2.0]
    scored = []
    for name in starts:
        scored.append((spot([r[0] for r in gaps(open_points, starts[name], tree)], 0.5), name))
    scored.sort()
    started = scored[0][1]
    best = starts[started]
    best_off = scored[0][0]
    fit = best
    for _ in range(8):
        fit = refit(open_points, fit, tree)
        off = spot([r[0] for r in gaps(open_points, fit, tree)], 0.5)
        if off < best_off:
            best, best_off = fit, off
    rows = gaps(open_points, best, tree)
    far = [100.0 * r[0] / height for r in rows]
    tenths = [[] for _ in range(10)]
    for r in rows:
        tenths[min(9, max(0, int((high[2] - r[1][2]) / height * 10)))].append(100.0 * r[0] / height)
    why = []
    median, p90 = spot(far, 0.5), spot(far, 0.9)
    if median > limits["median"]:
        why.append("the uncovered parts of the base body sit %.2f%% of the height off the clothed mesh, typically (limit %s)" % (median, limits["median"]))
    if p90 > limits["p90"]:
        why.append("one in ten uncovered points of the base body is more than %.2f%% of the height off the clothed mesh (limit %s)" % (p90, limits["p90"]))
    report = {
        "ok": not why, "why": why, "started_from": started, "points": len(open_points),
        "scale": round(best[0], 4),
        "shift_pct": [round(100.0 * best[k] / height, 2) for k in (1, 2, 3)],
        "off_pct": {"median": round(median, 2), "p90": round(p90, 2), "worst": round(max(far), 2) if far else 0.0},
        "off_pct_by_tenth_from_top": [round(spot(t, 0.5), 2) if t else None for t in tenths],
        "before_pct": round(100.0 * scored[[s[1] for s in scored].index("as the meshes came")][0] / height, 2),
    }
    return best, report


# ---- the cut ---------------------------------------------------------------

def color_votes(held):
    """For each color step: 1 a garment color, 2 clearly one of the rest of the figure, 0 can't tell.
    From the clothed picture, inside the change and outside it."""
    px, wide, tall = held["a"], held["wide"], held["tall"]
    inside = grown(held["mask"], wide, tall, True)
    n = LEVELS * LEVELS * LEVELS
    garment, rest = [0.0] * n, [0.0] * n
    for v in range(tall):
        for u in range(wide):
            i = v * wide + u
            if not held["figure_a"][i]:
                continue
            at = ((tall - 1 - v) * wide + u) * 4
            key = (int(px[at] * (LEVELS - 0.001)) * LEVELS + int(px[at + 1] * (LEVELS - 0.001))) * LEVELS + int(px[at + 2] * (LEVELS - 0.001))
            if inside[i]:
                garment[key] += 1.0
            elif not held["near"][i]:
                rest[key] += 1.0
    total_g, total_r = max(1.0, sum(garment)), max(1.0, sum(rest))
    votes = bytearray(n)
    for key in range(n):
        g, r = garment[key] / total_g, rest[key] / total_r
        # a neighboring step counts a little, so a slightly different shade still votes
        r0, g0, b0 = key // (LEVELS * LEVELS), (key // LEVELS) % LEVELS, key % LEVELS
        for dr, dg, db in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
            r1, g1, b1 = r0 + dr, g0 + dg, b0 + db
            if 0 <= r1 < LEVELS and 0 <= g1 < LEVELS and 0 <= b1 < LEVELS:
                other = (r1 * LEVELS + g1) * LEVELS + b1
                g += 0.3 * garment[other] / total_g
                r += 0.3 * rest[other] / total_r
        if g > 0.0005 and g > r:
            votes[key] = 1  # a garment color
        elif r > 0.0005 and r > 4.0 * g:
            votes[key] = 2  # clearly a color of the rest of the figure
    return votes

def islands(labels, neighbors, of):
    """Connected groups of faces whose label is `of`."""
    seen = bytearray(len(labels))
    found = []
    for start in range(len(labels)):
        if labels[start] != of or seen[start]:
            continue
        seen[start] = 1
        stack, group = [start], []
        while stack:
            i = stack.pop()
            group.append(i)
            for j in neighbors[i]:
                if labels[j] == of and not seen[j]:
                    seen[j] = 1
                    stack.append(j)
        found.append(group)
    return found

def to_the_seam(labels, votes, elsewhere, neighbors):
    """Grow the garment over its own blurred edge: a neighbor the picture votes for joins, unless
    its color is clearly the rest of the figure's. This carries the cut up to where the colors
    change (a waistband), through the half-and-half texels along it."""
    stack = [i for i in range(len(labels)) if labels[i]]
    grew = 0
    while stack:
        i = stack.pop()
        for j in neighbors[i]:
            if not labels[j] and (votes[j] & 1) and not elsewhere[j]:
                labels[j] = 1
                grew += 1
                stack.append(j)
    return grew

def walls_crossed(tree, start, way, nudge):
    """How many times a line from `start` going `way` passes through the body's surface."""
    count = 0
    at = start
    while count < 40:
        hit = tree.ray_cast(at, way)
        if hit[0] is None:
            break
        count += 1
        at = hit[0] + way * nudge
    return count

def walls_of(tree, low, high):
    """2 when the body is a thin shell with an outer and an inner wall (what TRELLIS.2 makes),
    1 when it is one closed skin. Lines shot straight through it cross four walls a pass, or two."""
    fours = twos = 0
    for k in range(1, 10):
        z = low[2] + (high[2] - low[2]) * k / 10.0
        start = Vector(((low[0] + high[0]) / 2.0, low[1] - 1.0, z))
        count = walls_crossed(tree, start, Vector((0.0, 1.0, 0.0)), 1e-6)
        if count and count % 4 == 0:
            fours += 1
        elif count:
            twos += 1
    return 2 if fours > twos else 1

def seat(obj, tree, walls, middle, clearance, reach):
    """Lift the garment's points that are under the base body's skin, or closer to it than
    `clearance`, out onto it. The clothed mesh hugged a guessed body; the real one can be a
    little fuller.

    A TRELLIS.2 mesh is a thin shell with an outer and an inner wall, so "which side of the
    nearest face" can't say what is inside. Counting walls can: a line from outside to far away
    crosses a multiple of four (in and out of the shell, twice per pass through the body), one
    from the hollow crosses two more, one from within the shell an odd number. A body that is
    one closed skin ("walls" 1) is simpler: an odd count is inside."""
    per_pass = 2 * walls
    lifted, most = 0, 0.0
    nudge = clearance * 0.01
    for v in obj.data.vertices:
        hit = tree.find_nearest(v.co)
        if hit[0] is None or hit[3] > reach:
            continue
        away = Vector((v.co[0] - middle[0], v.co[1] - middle[1], 0.0))
        if away.length < 1e-9:
            continue
        away.normalize()
        side = Vector((-away[1], away[0], 0.0))
        under = walls_crossed(tree, v.co, away, nudge) % per_pass != 0 and walls_crossed(tree, v.co, side, nudge) % per_pass != 0
        toward = hit[0] - v.co
        if toward.length < 1e-9:
            continue
        toward.normalize()
        if under:
            # out through the nearest wall, and the shell's other wall just past it
            skin = hit[0]
            past = tree.ray_cast(hit[0] + toward * nudge, toward, 4.0 * clearance) if walls == 2 else None
            if past is not None and past[0] is not None:
                skin = past[0]
            target = skin + toward * clearance
        elif hit[3] < clearance:
            target = hit[0] - toward * clearance
        else:
            continue
        most = max(most, (target - v.co).length)
        v.co = target
        lifted += 1
    obj.data.update()
    return lifted, most

def tidy(labels, neighbors, areas, crumb, pinhole):
    """Even the edge, drop scraps, close holes. Changes labels in place; says what it did."""
    evened = 0
    for _ in range(2):
        flips = []
        for i in range(len(labels)):
            near = neighbors[i]
            if len(near) < 2:
                continue
            against = sum(1 for j in near if labels[j] != labels[i])
            if 2 * against > len(near):
                flips.append(i)
        for i in flips:
            labels[i] = 1 - labels[i]
        evened += len(flips)
    total = sum(areas[i] for i in range(len(labels)) if labels[i])
    dropped = {"pieces": 0, "faces": 0}
    for group in islands(labels, neighbors, 1):
        if sum(areas[i] for i in group) < crumb * total:
            for i in group:
                labels[i] = 0
            dropped["pieces"] += 1
            dropped["faces"] += len(group)
    total = sum(areas[i] for i in range(len(labels)) if labels[i])
    closed = {"holes": 0, "faces": 0}
    for group in islands(labels, neighbors, 0):
        if sum(areas[i] for i in group) >= pinhole * total:
            continue
        inside = set(group)
        touches = any(labels[j] for i in group for j in neighbors[i] if j not in inside)
        if touches:
            for i in group:
                labels[i] = 1
            closed["holes"] += 1
            closed["faces"] += len(group)
    return {"edge_faces_evened": evened, "crumbs_dropped": dropped, "holes_closed": closed}

def share_out(garments, mids, labels, low_z, height):
    """Which garment each garment face belongs to: the one whose slot is at its height."""
    owner = [-1] * len(labels)
    bands = [BANDS.get(g.get("slot") or "", [0.0, 1.0]) for g in garments]
    for i in range(len(labels)):
        if not labels[i]:
            continue
        if len(garments) == 1:
            owner[i] = 0
            continue
        at = (mids[i][2] - low_z) / height
        best, best_off = 0, 9.0
        for k in range(len(garments)):
            off = max(bands[k][0] - at, at - bands[k][1], 0.0)
            if off < best_off:
                best, best_off = k, off
        owner[i] = best
    return owner

def round_the_top(keep, mids, top, height):
    """How much of the way round the garment is whole just under its top edge (a waistband, a
    collar): the share of 36 directions from its middle that have faces, 1-3% of the height down."""
    ring = [mids[i] for i in keep if top - 0.03 * height <= mids[i][2] <= top - 0.01 * height]
    if len(ring) < 36:
        return 0.0
    cx = sum(p[0] for p in ring) / len(ring)
    cy = sum(p[1] for p in ring) / len(ring)
    seen = set(int((math.atan2(p[1] - cy, p[0] - cx) + math.pi) / (2 * math.pi) * 36) % 36 for p in ring)
    return round(100.0 * len(seen) / 36.0, 1)

def write_glb(obj, path):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, use_active_scene=True, export_extras=True)
    obj.select_set(False)

def piece_of(source, keep, name):
    """A copy of the clothed mesh holding only the faces in `keep`."""
    me = source.data.copy()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj

def render_votes(obj, shades, stem, low, high):
    """The clothed mesh from the front, a quarter turn and the back, each face in its votes' color."""
    me = obj.data
    layer = me.color_attributes.new("votes", "BYTE_COLOR", "CORNER")
    flat = []
    for poly in me.polygons:
        c = shades[poly.index]
        for _ in range(poly.loop_total):
            flat.extend((c[0], c[1], c[2], 1.0))
    layer.data.foreach_set("color", flat)
    me.color_attributes.active_color = layer
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "VERTEX"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("votes")
    world.color = (0.955, 0.94, 0.915)
    scene.world = world
    camera = bpy.data.objects.new("votes camera", bpy.data.cameras.new("votes camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max(high[i] - low[i] for i in range(3)) * 1.06
    mid = Vector(((low[0] + high[0]) / 2, (low[1] + high[1]) / 2, (low[2] + high[2]) / 2))
    hidden = [o for o in scene.objects if o.type == "MESH" and o != obj and not o.hide_render]
    for o in hidden:
        o.hide_render = True
    written = []
    for name, turn in (("front", 0.0), ("quarter", 45.0), ("back", 180.0)):
        angle = math.radians(turn)
        camera.location = mid + Vector((5 * math.sin(angle), -5 * math.cos(angle), 0))
        camera.rotation_euler = (math.pi / 2, 0, angle)
        scene.render.filepath = "%s-%s.png" % (stem, name)
        bpy.ops.render.render(write_still=True)
        written.append(scene.render.filepath)
    for o in hidden:
        o.hide_render = False
    return written


def cut(params, held, result):
    wide, tall = held["wide"], held["tall"]
    clothed = load_mesh(params["clothed"], "clothed")
    base = load_mesh(params["base"], "base body")
    texture = color_texture(clothed)

    bm = bmesh.new()
    bm.from_mesh(clothed.data)
    low, high = box_of([v.co for v in bm.verts])
    height = high[2] - low[2]
    # glTF splits points along texture seams; weld them so neighbors are neighbors
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=height * 1e-6)
    bm.faces.ensure_lookup_table()
    bm.faces.index_update()
    mids, areas, colors = read_faces(bm, texture)
    neighbors = [[g.index for e in f.edges for g in e.link_faces if g != f] for f in bm.faces]
    clothed_tree = BVHTree.FromBMesh(bm)
    bm.to_mesh(clothed.data)
    bm.free()

    view, seen = best_view(mids, areas, colors, held["a"], held["figure_a"], held["box_a"], wide, tall)
    base_bm = bmesh.new()
    base_bm.from_mesh(base.data)
    base_mids, base_areas, base_colors = read_faces(base_bm, color_texture(base))
    base_bm.free()
    base_view, base_seen = best_view(base_mids, base_areas, base_colors, held["b"], held["figure_b"], held["box_b"], wide, tall)
    base_view["mirrored"] = view["mirrored"]
    result["view"] = {"clothed": seen, "base": base_seen}
    for name, got in (("clothed mesh", seen), ("base body", base_seen)):
        if got["overlap_pct"] < params["limits"]["view"]:
            result["why"].append("seen from the front, the %s covers only %.0f%% of the figure in its picture (limit %s): it isn't framed the way the picture is" % (name, got["overlap_pct"], params["limits"]["view"]))
    if result["why"]:
        return

    fit, report = lay_on(base_mids, base_view, held, (low, high), view, clothed_tree, params["limits"])
    result["fit"] = report
    if not report["ok"]:
        return
    base.data.transform(Matrix.Translation(Vector((fit[1], fit[2], fit[3]))) @ Matrix.Scale(fit[0], 4))
    base.data.update()
    if params["body_out"]:
        write_glb(base, params["body_out"])
        result["body"] = params["body_out"]
    base_bm = bmesh.new()
    base_bm.from_mesh(base.data)
    base_tree = BVHTree.FromBMesh(base_bm)
    b_low, b_high = box_of([v.co for v in base_bm.verts])
    base_middle = [(b_low[0] + b_high[0]) / 2.0, (b_low[1] + b_high[1]) / 2.0]
    base_walls = walls_of(base_tree, b_low, b_high)
    base_bm.free()

    # the three votes
    is_garment_color = color_votes(held)
    gap = params["gap"] * height
    votes = bytearray(len(mids))
    elsewhere = bytearray(len(mids))  # faces in a color that is clearly the rest of the figure's
    for i in range(len(mids)):
        at = pixel_of(view, mids[i], wide, tall)
        vote = 1 if (at >= 0 and held["near"][at]) else 0
        c = colors[i]
        if c is not None:
            key = (int(c[0] * (LEVELS - 0.001)) * LEVELS + int(c[1] * (LEVELS - 0.001))) * LEVELS + int(c[2] * (LEVELS - 0.001))
            if is_garment_color[key] == 1:
                vote += 2
            elif is_garment_color[key] == 2:
                elsewhere[i] = 1
        hit = base_tree.find_nearest(mids[i])
        if hit[0] is None or hit[3] > gap:
            vote += 4
        votes[i] = vote
    labels = bytearray(1 if v in (3, 5, 6, 7) else 0 for v in votes)
    voted = bytearray(labels)
    whole = sum(areas)
    names = {7: "picture + color + distance", 3: "picture + color", 5: "picture + distance", 6: "color + distance",
             1: "picture only", 2: "color only", 4: "distance only", 0: "none"}
    agreement = {}
    for code in names:
        chosen = [i for i in range(len(votes)) if votes[i] == code]
        agreement[names[code]] = {"faces": len(chosen), "area_pct": round(100.0 * sum(areas[i] for i in chosen) / whole, 2)}
    signals = {}
    for bit, name in ((1, "picture"), (2, "color"), (4, "distance")):
        chosen = [i for i in range(len(votes)) if votes[i] & bit]
        signals[name] = {"faces": len(chosen), "area_pct": round(100.0 * sum(areas[i] for i in chosen) / whole, 2)}
    result["votes"] = {"faces": len(votes), "said_garment": signals, "agreement": agreement,
                       "two_or_more": {"faces": sum(voted), "area_pct": round(100.0 * sum(areas[i] for i in range(len(voted)) if voted[i]) / whole, 2)}}
    reached = to_the_seam(labels, votes, elsewhere, neighbors)
    result["cleanup"] = tidy(labels, neighbors, areas, params["crumb"], params["pinhole"])
    result["cleanup"]["faces_grown_to_the_color_seam"] = reached

    garments = params["garments"] or [{"name": "garment", "slot": None}]
    owner = share_out(garments, mids, labels, low[2], height)
    result["garments"] = []
    for k in range(len(garments)):
        keep = set(i for i in range(len(owner)) if owner[i] == k)
        entry = {"name": garments[k]["name"], "slot": garments[k].get("slot"), "faces": len(keep), "file": None}
        if keep:
            heights = [mids[i][2] for i in keep]
            mask = bytearray(len(labels))
            for i in keep:
                mask[i] = 1
            entry["area_pct"] = round(100.0 * sum(areas[i] for i in keep) / whole, 2)
            entry["pieces"] = len(islands(mask, neighbors, 1))
            entry["top"] = round((max(heights) - low[2]) / height, 3)
            entry["bottom"] = round((min(heights) - low[2]) / height, 3)
            entry["closed_round_its_top_pct"] = round_the_top(keep, mids, max(heights), height)
            entry["other_colors_pct"] = round(100.0 * sum(areas[i] for i in keep if elsewhere[i]) / max(1e-12, sum(areas[i] for i in keep)), 2)
            if params["out"]:
                obj = piece_of(clothed, keep, "garment: %s" % garments[k]["name"])
                if params["seat"]:
                    lifted, most = seat(obj, base_tree, base_walls, base_middle, params["seat"] * height, 0.03 * height)
                    entry["points_lifted_onto_the_body"] = lifted
                    entry["lifted_at_most_pct"] = round(100.0 * most / height, 2)
                obj["gear"] = garments[k]["name"]
                obj["slot"] = garments[k].get("slot") or ""
                obj["kind"] = garments[k].get("kind") or "worn"
                entry["file"] = "%s/%s.glb" % (params["out"].rstrip("/"), slug_of(garments[k]["name"]))
                write_glb(obj, entry["file"])
                obj.hide_render = True
        result["garments"].append(entry)
    result["garment_area_pct"] = round(100.0 * sum(areas[i] for i in range(len(labels)) if labels[i]) / whole, 2)
    if not any(g["faces"] for g in result["garments"]):
        result["why"].append("no face of the clothed mesh got two votes: nothing to cut")

    if params["overlay"]:
        shades = []
        for i in range(len(votes)):
            if labels[i] and not voted[i]:
                shades.append(OVERLAY["grown to the color seam, closed hole or evened edge (added)"])
            elif voted[i] and not labels[i]:
                shades.append(OVERLAY["crumb or evened edge (dropped)"])
            elif labels[i]:
                shades.append(OVERLAY[names[votes[i]]])
            elif votes[i]:
                shades.append(OVERLAY["one vote only (not garment)"])
            else:
                shades.append(OVERLAY["no vote (not garment)"])
        base.hide_render = True
        result["overlay"] = render_votes(clothed, shades, params["overlay"], low, high)
        result["overlay_colors"] = OVERLAY


if not PARAMS["picture"] or not PARAMS["base_picture"]:
    raise ValueError("set PARAMS['picture'] and PARAMS['base_picture']")
result = {"ok": False, "why": []}
pictures, kept = compare_pictures(PARAMS)
result["pictures"] = pictures
if pictures["ok"] and PARAMS["clothed"] and PARAMS["base"]:
    cut(PARAMS, kept, result)
result["why"] = pictures["why"] + (result["fit"]["why"] if "fit" in result else []) + result["why"]
result["ok"] = not result["why"]
print("RESULT " + json.dumps(result))
