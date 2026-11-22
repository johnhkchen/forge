# Make a character's clothes sit on its body: shape each worn piece to what is
# under it, and note which body faces the clothes hide.
#
# A block-out's gear is built as separate tubes and boxes roughly around the
# body. Run this after the last build.py (and before export.py) and each piece
# of clothing is laid on the body:
#   - "tight" pieces (trousers, sleeves, a shirt, wraps, a mask) are moved onto
#     the body under them, a small step off it ("clearance"), so they follow
#     its shape with no gap and nothing poking through. A piece worn over
#     another piece sits one more step out. Where a corner of the body would
#     still stand out through a flat face of cloth, that face is lifted over it.
#   - "loose" pieces (a kilt, a skirt, a coat's skirts, a hood, a cape) are
#     fitted only where they rest on the body: from their top down to where
#     the body starts to fall away under them. Below that they keep the hang
#     they were built with, and are pushed out only as far as cloth would
#     fall: straight down from the widest part of the body above it, never
#     in toward the legs. A belt or sash around it holds it to the body down
#     to where the belt sits; it hangs from there.
#   - "stiff" pieces (boots, a hat, a buckle, glasses) keep their shape; a
#     small one is carried along with the cloth it sits on. A belt or band
#     keeps its thickness and is set on what it goes around.
# Which is which is worked out from the piece (its name, the gear's slot and
# kind, how its lower edge stands off the body); say so yourself with
# "fit": "tight" | "loose" | "stiff" on a piece in build.py, or here with
# "fit": {"<gear or piece name>": "loose"}. "pieces" in the result lists what
# each was taken for and why: check it.
#
# It also finds the body faces that worn gear hides completely and marks them
# ("forge_under" on the faces; "masks" in the result). export.py then writes
# those faces as meshes of their own, "body under: wool trousers", tagged with
# the gear that hides them: a game (and the gallery) shows such a mesh only
# while that gear is off. The body stays whole, and worn gear can't let skin
# through, because the skin under it isn't drawn. "skin_showing_through" in
# the result counts what is left: spots on body faces that stay drawn, with
# cloth behind them instead of over them. It should be 0 or close to it.
#
# "rings": True (the default) first cuts a few new edge loops, without
# changing any shape: a tight piece gets one wherever the body under it has
# one and the piece has none near (at most three a piece), so cloth bends
# where the body bends; and the body gets one just inside each end of a piece
# that covers it (a cuff, a hem, a boot top), so the skin under the piece is
# faces of its own that can be hidden, with none half in and half out. Only
# on a block-out that is still one object.
#
# Works on a block-out in one object (build.py's "<reference> (light)", gear as
# face groups), or on the separate "body" / "gear: ..." meshes of an opened
# .glb, where it first joins a body that was written in several meshes. Run it
# again any time: a piece already on the body stays where it is, and meshes
# that were draped before they were written (their body says "draped") are
# only read, not moved. It leaves "forge_fit" (1 tight, 2 loose, 3 stiff, 4 a
# band), "forge_hang" (0 on the body to 1 at a loose piece's hem) and
# "forge_island" on the points, and "forge_hangs" on the mesh (for each loose
# piece, the height it hangs from and how far down), which cloth.py reads.
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down.
# Prints RESULT {json}. A second or two. Safe-mode compatible.

PARAMS = {
    "object": None,      # the block-out; None = the one in this scene, else the scene's "body" and "gear: ..." meshes
    "fit": {},           # {"<gear or piece name>": "tight" | "loose" | "stiff"}; anything not named is worked out
    "pieces": None,      # the recipe's pieces (for their names and "fit"); None = the block-out's own
    "clearance": 0.005,  # how far cloth sits off what is under it, as a share of the character's height
    "rings": True,       # cut edge loops: in tight pieces where the body under them has one, and in the body just inside each piece's ends
    "rings_budget": 0.12,  # ...for as long as they add no more than this share to the triangle count
    "mask": True,        # mark the body faces worn gear hides
    "move": None,        # False = change nothing: only work out what each piece is, the hang and the hidden faces. None = move, unless the meshes say they were draped before they were written
}

import bpy
import bmesh
import json
import math
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

LOOSE = ("kilt", "skirt", "coat", "cape", "cloak", "robe", "hood", "gown", "dress", "tabard", "loincloth", "poncho", "tunic", "apron", "shawl")
STIFF = ("boot", "shoe", "brogan", "sandal", "clog", "hat", "helmet", "crown", "spectacle", "glasses", "goggle", "buckle", "plate", "pauldron",
         "horn", "quiver", "pack", "bag", "pouch", "sheath", "button", "knot", "badge")
BELTS = ("belt", "sash", "girdle", "cord", "rope")
ACROSS = {"x": (0, 1, 2), "y": (1, 0, 2), "z": (2, 0, 1)}
FITS = {"tight": 1, "loose": 2, "stiff": 3, "band": 4}
BURIED = 0.03  # a point deeper in the body than this share of the height was built in there on purpose


def first(pair):
    return pair[0]

def has_word(text, words):
    low = (text or "").lower()
    for word in words:
        if word in low:
            return word
    return None

def middle_of(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2] if ordered else 0.0

def share_of(values, share):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))] if ordered else 0.0

def piece_boxes(pieces):
    """Each recipe piece's box (and its mirror twin's), to tell which piece a part of the mesh is."""
    out = []
    for part in pieces or []:
        pts = []
        if "loft" in part:
            a, u, v = ACROSS[part["loft"]]
            for row in part["rings"]:
                n = [x for x in row if not isinstance(x, dict)]
                more = row[-1] if isinstance(row[-1], dict) else {}
                rv = n[4] if len(n) > 4 else n[3]
                for su, sv in ((-n[3], -rv), (n[3], more.get("back", rv))):
                    p = [0.0, 0.0, 0.0]
                    p[a], p[u], p[v] = n[0] + more.get("slope", 0) * sv, n[1] + su, n[2] + sv
                    pts.append(p)
        elif "tube" in part:
            for row in part["tube"]:
                n = [x for x in row if not isinstance(x, dict)]
                r = max(n[3], n[4] if len(n) > 4 else n[3])
                pts += [[n[0] - r, n[1] - r, n[2] - r], [n[0] + r, n[1] + r, n[2] + r]]
        elif "lumps" in part:
            for row in part["lumps"]:
                size = row[3:6] if len(row) > 5 else [row[3]] * 3
                pts += [[row[i] - size[i] for i in range(3)], [row[i] + size[i] for i in range(3)]]
        elif "box" in part:
            pts = [part["box"]["min"], part["box"]["max"]]
        if not pts:
            continue
        lo, hi = [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]
        out.append((part, lo, hi))
        if part.get("mirror") and "head" not in part:  # its twin, and the pair as one (two legs that meet in the middle)
            out.append((part, [-hi[0], lo[1], lo[2]], [-lo[0], hi[1], hi[2]]))
            out.append((part, [min(lo[0], -hi[0]), lo[1], lo[2]], [max(hi[0], -lo[0]), hi[1], hi[2]]))
    return out

def exit_of(tree, start, aim, reach):
    """If `start` is inside the body, where a ray along `aim` leaves it (the last wall met from within), else None."""
    out, at, left = None, start, reach
    for _ in range(6):
        hit = tree.ray_cast(at, aim, left)
        if hit[0] is None or hit[1].dot(aim) <= 0:
            break
        out = hit[0]
        left -= hit[3] + 1e-5
        at = hit[0] + aim * 1e-5
        if left <= 0:
            break
    return out

def farthest(tree, start, aim, reach):
    """How far along `aim` the last surface of `tree` within `reach` is; 0 if none."""
    far, at, gone = 0.0, start + aim * 1e-5, 1e-5
    for _ in range(8):
        if gone >= reach:
            break
        hit = tree.ray_cast(at, aim, reach - gone)
        if hit[0] is None:
            break
        gone += hit[3] + 1e-5
        far = gone
        at = hit[0] + aim * 1e-5
    return far

def tree_of(pos, faces):
    """A search tree over faces given as tuples of point numbers into `pos`."""
    index, pts, polys = {}, [], []
    for f in faces:
        poly = []
        for k in f:
            if k not in index:
                index[k] = len(pts)
                pts.append(pos[k])
            poly.append(index[k])
        polys.append(poly)
    return BVHTree.FromPolygons(pts, polys) if polys else None

def gather(light):
    """What is body and what is gear: [{"obj", "faces": [face numbers], "tag"}], the body first."""
    layers = []
    if light is not None:
        marks = [0] * len(light.data.polygons)
        light.data.attributes["forge_group"].data.foreach_get("value", marks)
        for index, tag in enumerate(json.loads(light["forge_groups"])):
            layers.append({"obj": light, "faces": [i for i, m in enumerate(marks) if m == index], "tag": tag})
    else:
        for o in scene.objects:
            if o.type != "MESH" or o.get("forge") not in ("body", "gear") or o.name.startswith("lines:"):
                continue
            tag = {"forge": o["forge"], "name": "body" if o["forge"] == "body" else "gear: " + str(o.get("gear", o.name))}
            for key in ("gear", "kind", "slot"):
                if o.get(key):
                    tag[key] = o[key]
            layers.append({"obj": o, "faces": list(range(len(o.data.polygons))), "tag": tag})
    return [l for l in layers if l["tag"].get("forge") == "body"] + [l for l in layers if l["tag"].get("forge") != "body"]

def same_place(points, within=1e-4):
    """Which place each point is, and how many places: points closer than `within` (m) are one place. A .glb
    splits a point wherever the texture layout has a seam, and the copies can come back a few hundredths of a
    millimetre apart. Rounded to a grid, a pair either side of a grid line would be two places, and a garment
    could come apart into scraps along a seam (Roosevelt's singlet did: two of them were then taken for stiff
    little pieces, and tore away from the rest in motion)."""
    tree = KDTree(len(points))
    for i, p in enumerate(points):
        tree.insert(p, i)
    tree.balance()
    place, count = [-1] * len(points), 0
    for i, p in enumerate(points):
        if place[i] >= 0:
            continue
        for co, j, d in tree.find_range(p, within):
            if place[j] < 0:
                place[j] = count
        place[i] = count
        count += 1
    return place, count

def survey(layers):
    """The meshes as they are now, with points that share a place within a layer counted once."""
    pos, members, normal, of_layer, faces, links = [], [], [], [], [], []
    for li, layer in enumerate(layers):
        obj = layer["obj"]
        me = obj.data
        turn = obj.matrix_world.to_3x3()
        world = [obj.matrix_world @ v.co for v in me.vertices]
        at, seen = {}, {}
        used = sorted({vi for fi in layer["faces"] for vi in me.polygons[fi].vertices})
        place = dict(zip(used, same_place([world[vi] for vi in used])[0]))
        for fi in layer["faces"]:
            poly = me.polygons[fi]
            ring = []
            for vi in poly.vertices:
                if vi not in seen:
                    p = world[vi]
                    spot = place[vi]
                    if spot not in at:
                        at[spot] = len(pos)
                        pos.append(p.copy())
                        members.append([])
                        normal.append(Vector())
                        of_layer.append(li)
                        links.append(set())
                    seen[vi] = at[spot]
                    members[at[spot]].append((obj, vi))
                ring.append(seen[vi])
            push = (turn @ poly.normal) * poly.area
            for i, k in enumerate(ring):
                normal[k] += push
                links[k].add(ring[i - 1])
                links[ring[i - 1]].add(k)
            faces.append((li, fi, tuple(ring)))
    for n in normal:
        if n.length > 1e-12:
            n.normalize()
    return {"pos": pos, "members": members, "normal": normal, "layer": of_layer, "faces": faces, "links": links}

def top_of(root, a):
    while root[a] != a:
        root[a] = root[root[a]]
        a = root[a]
    return a

def islands_of(data, layers, boxes):
    """Each gear layer's connected pieces, matched to a recipe piece by its box where there is a recipe."""
    root = list(range(len(data["pos"])))
    for li, fi, ring in data["faces"]:
        a = top_of(root, ring[0])
        for k in ring[1:]:
            root[top_of(root, k)] = a
    found = {}
    for li, fi, ring in data["faces"]:
        if layers[li]["tag"].get("forge") == "body":
            continue
        a = top_of(root, ring[0])
        if a not in found:
            found[a] = {"layer": li, "faces": [], "points": set()}
        found[a]["faces"].append((fi, ring))
        found[a]["points"].update(ring)
    out = []
    for isl in found.values():
        isl["points"] = sorted(isl["points"])
        pts = [data["pos"][k] for k in isl["points"]]
        isl["lo"] = Vector([min(p[i] for p in pts) for i in range(3)])
        isl["hi"] = Vector([max(p[i] for p in pts) for i in range(3)])
        tag = layers[isl["layer"]]["tag"]
        isl["gear"] = tag.get("gear", "")
        isl["piece"], best = None, 0.08 * tall
        for part, lo, hi in boxes:
            if part.get("gear") == isl["gear"]:
                off = sum(abs(lo[i] - isl["lo"][i]) + abs(hi[i] - isl["hi"][i]) for i in range(3))
                if off < best:
                    isl["piece"], best = part, off
        edges = {}
        for fi, ring in isl["faces"]:
            for i, k in enumerate(ring):
                pair = (min(k, ring[i - 1]), max(k, ring[i - 1]))
                edges[pair] = edges.get(pair, 0) + 1
        isl["open_edges"] = sum(1 for n in edges.values() if n == 1)
        isl["band"] = isl["open_edges"] == 0 and len(isl["points"]) - len(edges) + len(isl["faces"]) == 0
        wide = isl["hi"].x - isl["lo"].x
        isl["centered"] = isl["lo"].x < -0.25 * wide and isl["hi"].x > 0.25 * wide
        isl["name"] = isl["piece"]["name"] if isl["piece"] else isl["gear"]
        out.append(isl)
    return out

def gap_of(k):
    """How far a gear point is off the body: (distance, the body point it measures from, the way out from there).
    Inside the body the distance is negative and the way out is the cloth's own facing."""
    p, n = data["pos"][k], data["normal"][k]
    leaves = exit_of(body_tree, p, n, 0.08 * tall) if n.length > 0.5 else None
    if leaves is not None:
        return -(leaves - p).length, leaves, n
    hit = body_tree.find_nearest(p)
    if hit[0] is None:
        return 1e9, p, n
    return hit[3], hit[0], ((p - hit[0]) / hit[3] if hit[3] > 1e-6 else n)

def body_out(p, aim, z):
    """Seen from outside along `aim` at height `z`: how far out from `p` the body reaches that way. None if it
    isn't there (within a tenth of the height in from `p`); "in" if the look starts inside the body (an arm held out)."""
    start = Vector((p.x, p.y, z)) + aim * (0.12 * tall)
    hit = body_tree.ray_cast(start, -aim, 0.22 * tall)
    if hit[0] is None:
        return None
    if hit[1].dot(aim) <= 0:
        return "in"
    return 0.12 * tall - hit[3]

def bins_of(points, axis):
    """Points gathered into rings by where they sit along an axis: [[position, [points]]], highest first."""
    rows = sorted([(data["pos"][k][axis], k) for k in points], reverse=True)
    out = []
    for at, k in rows:
        if out and out[-1][0] - at < 0.01 * tall:
            out[-1][1].append(k)
        else:
            out.append([at, [k]])
    return out

def judge(isl):
    """What a piece is taken for, and why."""
    part, tag = isl["piece"] or {}, layers[isl["layer"]]["tag"]
    for was in stored.get(isl["gear"], []):  # a mesh draped before it was written says what each of its parts was
        if sum(abs(was["lo"][i] - isl["lo"][i]) + abs(was["hi"][i] - isl["hi"][i]) for i in range(3)) < 0.02 * tall:
            isl["name"], isl["was"] = was["name"], was
            return was["fit"], "as when it was draped"
    for name in (part.get("name"), isl["gear"]):
        if name and PARAMS["fit"].get(name) in FITS:
            return PARAMS["fit"][name], "you said so"
    if part.get("fit") in FITS:
        return part["fit"], "its piece says so"
    named = part.get("name") or isl["gear"]
    if tag.get("kind") == "attached":
        return "stiff", "it is attached, not worn"
    if has_word(tag.get("slot"), ("feet", "foot")):
        return "stiff", "footwear keeps its shape"
    if has_word(named, STIFF):
        return "stiff", "a %s keeps its shape" % has_word(named, STIFF)
    if (isl["hi"] - isl["lo"]).length < 0.12 * tall or len(isl["points"]) <= 8:
        return "stiff", "small"
    if isl["band"]:
        return "band", "a band with an inside and an outside"
    word = has_word(named, LOOSE)  # a piece's own name where there is a recipe ("hood", not the "mask" of "hood and mask")
    if word and (isl["centered"] or part.get("name")):
        return "loose", "a %s hangs" % word
    low = bins_of(isl["points"], 2)[-1][1]
    if isl["centered"] and isl["hi"].z - isl["lo"].z > 0.08 * tall and max(gaps[k][0] for k in low) > 0.04 * tall:
        return "loose", "its lower edge stands well off the body"
    return "tight", "it lies on the body"

def axis_of(isl):
    """The way a piece runs: its loft's axis where the recipe says, else its longest side."""
    if isl["piece"] and "loft" in isl["piece"]:
        return ACROSS[isl["piece"]["loft"]][0]
    size = isl["hi"] - isl["lo"]
    return 0 if size.x >= size.y and size.x >= size.z else (1 if size.y >= size.z else 2)

def by_size(cut):
    return len(islands[cut[0]]["points"])

def add_rings(light, islands):
    """New edge loops, cut across faces without changing the shape. Returns (how many in the gear, how many in the body).
    - a tight piece gets one where the body under it has a ring and it has none near, so cloth bends where the body bends;
    - the body gets one just inside each end of a piece that covers it (a cuff, a hem, a boot top), so the skin
      under the piece is faces of its own that can be hidden, and none of it is half in, half out."""
    body_points = [k for k in range(len(data["pos"])) if layers[data["layer"][k]]["tag"].get("forge") == "body"]
    cuts, body_cuts = [], []
    for number, isl in enumerate(islands):
        big = (isl["hi"] - isl["lo"]).length >= 0.12 * tall
        if isl["fit"] not in ("tight", "band") and not (isl["fit"] == "stiff" and big):
            continue
        axis = axis_of(isl)
        own = [row[0] for row in bins_of(isl["points"], axis)]
        if len(own) < 2:
            continue
        near = []
        for k in body_points:
            p = data["pos"][k]
            if all(isl["lo"][i] - 0.015 * tall < p[i] < isl["hi"][i] + 0.015 * tall for i in range(3)):
                near.append(k)
        rows = bins_of(near, axis)
        if isl["fit"] == "tight":
            wanted = []
            for at, ring in rows:
                away = min(abs(at - o) for o in own)
                if isl["lo"][axis] + 0.02 * tall < at < isl["hi"][axis] - 0.02 * tall and len(ring) >= 4 and away > 0.025 * tall and all(abs(at - w[1]) > 0.025 * tall for w in wanted):
                    wanted.append((away, at))
            for away, at in sorted(wanted, reverse=True)[:3]:
                cuts.append((number, axis, at))
        if near and isl["hi"][axis] - isl["lo"][axis] > 8 * step:
            for at in (isl["lo"][axis] + 1.5 * step, isl["hi"][axis] - 1.5 * step):
                if all(abs(at - row[0]) > 1.5 * step for row in rows):
                    body_cuts.append((number, axis, at))
    if not cuts and not body_cuts:
        return 0, 0
    bm = bmesh.new()
    bm.from_mesh(light.data)
    bm.faces.ensure_lookup_table()
    mark = bm.faces.layers.int.new("drape_island")
    group = bm.faces.layers.int.get("forge_group")
    for number, isl in enumerate(islands):
        for fi, ring in isl["faces"]:
            bm.faces[fi][mark] = number + 1
    back = light.matrix_world.inverted()
    start = sum(len(f.verts) - 2 for f in bm.faces)
    body_cuts.sort(key=by_size, reverse=True)  # the biggest pieces first: they hide the most skin
    made = [0, 0]
    for number, axis, at in cuts + body_cuts:
        isl = islands[number]
        if sum(len(f.verts) - 2 for f in bm.faces) > start * (1.0 + PARAMS["rings_budget"]):
            break  # the low-poly budget comes first
        made[0 if (number, axis, at) in cuts else 1] += 1
        if (number, axis, at) in cuts:
            mine = [f for f in bm.faces if f[mark] == number + 1]
        else:  # the body's faces under this piece, and a little past its ends
            long = isl["hi"][axis] - isl["lo"][axis]
            mine = []
            for f in bm.faces:
                if f[mark] != 0 or f[group] != 0:
                    continue
                mid = light.matrix_world @ f.calc_center_median()
                if all((isl["lo"][i] - 0.15 * long < mid[i] < isl["hi"][i] + 0.15 * long) if i == axis else (isl["lo"][i] - 2 * step < mid[i] < isl["hi"][i] + 2 * step) for i in range(3)):
                    mine.append(f)
        if not mine:
            continue
        geom = set(mine)
        for f in mine:
            geom.update(f.edges)
            geom.update(f.verts)
        spot, facing = Vector(), Vector()
        spot[axis], facing[axis] = at, 1.0
        bmesh.ops.bisect_plane(bm, geom=list(geom), dist=1e-5, plane_co=back @ spot, plane_no=(light.matrix_world.to_3x3().transposed() @ facing).normalized())
    bm.faces.layers.int.remove(mark)
    bm.to_mesh(light.data)
    bm.free()
    light.data.update()
    return made[0], made[1]

def by_gear(entry):
    return (entry["gear"], entry["piece"])

def inner_first(isl):
    """What is worn nearest the body goes on first; a belt or band goes over everything it is around."""
    off = [min(abs(gaps[k][0]), 4 * step) for k in isl["points"]]
    return (isl["girds"], sum(off) / len(off))

def seat(k, under):
    """For a point: (the spot under it, the way out, how far off it must sit, how far off it is)."""
    dist, base, out = gap_of(k)
    now = (data["pos"][k] - base).dot(out)
    need = step
    if under is not None:
        far = farthest(under, base, out, 4 * step)  # other gear within four steps of the body here is worn under this
        if far > 0:
            need = far + step
    return base, out, need, now

def lay(k, under):
    """Put a point on what is under it. Not one too far off to be meant to touch, and not one sunk deep
    in the body: that is where two pieces were built into each other (a trouser leg's top inside the hips)."""
    for _ in range(6):
        base, out, need, now = seat(k, under)
        if now > 0.05 * tall or now < -BURIED * tall or abs(now - need) < 1e-5:
            break
        data["pos"][k] = base + out * need

def keep_off(k, under):
    """Push a point out if it is in, or nearer than a step to, what is under it."""
    for _ in range(3):
        base, out, need, now = seat(k, under)
        if now >= need - 1e-5 or now < -BURIED * tall:
            break
        data["pos"][k] = base + out * need

def follow(points, leaders):
    """Points with no say of their own (the inside wall of a kilt, the outside of a belt) move as the nearest leader did."""
    for k in points:
        best, best_d = None, 1e9
        for j in leaders:
            d = (before[j] - before[k]).length_squared
            if d < best_d:
                best, best_d = j, d
        if best is not None:
            data["pos"][k] = before[k] + (data["pos"][best] - before[best])

def cinch_over(isl):
    """The height of a belt or band worn around a loose piece, which holds it to the body there; None without one."""
    best = None
    for other in islands:
        if other is not isl and other["girds"] and isl["lo"].z < other["lo"].z < isl["hi"].z:
            if other["lo"].x < isl["hi"].x and other["hi"].x > isl["lo"].x:
                best = other["lo"].z if best is None else min(best, other["lo"].z)
    return best

def lay_loose(isl, under):
    """A loose piece: on the body from its top down to where the body falls away, hanging below."""
    points = isl["points"]
    mid = sum((data["pos"][k] for k in points), Vector()) / len(points)
    liners = []
    for k in points:
        radial = Vector((data["pos"][k].x - mid.x, data["pos"][k].y - mid.y, 0.0))
        if radial.length > 1e-4 and data["normal"][k].dot(radial.normalized()) < -0.2:
            liners.append(k)
    lining = set(liners)
    outer = [k for k in points if k not in lining] or points
    belt = cinch_over(isl)
    free, fall, aims = {}, {}, {}
    for k in outer:
        p, n = data["pos"][k], data["normal"][k]
        flat = Vector((n.x, n.y, 0.0))
        free[k] = False
        if flat.length < 0.35:  # it faces up or down: it lies on a shoulder or a crown
            continue
        aims[k] = flat.normalized()
        own = body_out(p, aims[k], p.z)
        above, z = None, p.z + 0.015 * tall
        stop = belt if belt is not None and belt > p.z else isl["hi"].z
        while z <= stop + 1e-6:
            s = body_out(p, aims[k], z)
            if s is not None and s != "in" and (above is None or s > above):
                above = s
            z += 0.015 * tall
        if own == "in":  # under an arm: no telling
            continue
        fall[k] = above if own is None else (own if above is None else max(own, above))
        free[k] = above is not None and (own is None or own < above - 0.01 * tall)
    rows = bins_of(outer, 2)
    line = isl["lo"].z
    for i, row in enumerate(rows):
        if sum(1 for k in row[1] if free[k]) >= 0.25 * len(row[1]):
            line = rows[max(i - 1, 0)][0]
            break
    if belt is not None:  # a belt holds the cloth to the body down to where it sits, and lets it go below
        line = belt
    if isl.get("was") and isl["was"].get("line") is not None:
        line = isl["was"]["line"]
    drop = line - isl["lo"].z
    for k in points:
        hang[k] = min(1.0, max(0.0, (line - 0.005 * tall - data["pos"][k].z) / drop)) if drop >= 0.03 * tall else 0.0
    on_body = [k for k in outer if hang[k] == 0.0]
    hanging = [k for k in outer if hang[k] > 0.0]
    if PARAMS["move"]:
        for k in on_body:
            lay(k, under)
        if hanging and on_body:  # the hanging part comes along with the edge it hangs from, less and less toward the hem
            shift = {k: (data["pos"][k] - before[k]) if hang[k] == 0.0 else Vector() for k in outer}
            mine = set(outer)
            for _ in range(60):
                for k in hanging:
                    near = [shift[j] for j in data["links"][k] if j in mine]
                    if near:
                        shift[k] = sum(near, Vector()) / len(near)
            for k in hanging:
                data["pos"][k] = before[k] + shift[k] * (1.0 - 0.8 * hang[k])
        for k in hanging:
            if k in aims and fall.get(k) is not None:  # cloth falls straight down from the widest part above it
                lack = fall[k] + step - (data["pos"][k] - before[k]).dot(aims[k])
                if lack > 0:
                    data["pos"][k] = data["pos"][k] + aims[k] * lack
            keep_off(k, under)
        follow(liners, outer)
    return {"hangs_from_z": round(line, 3), "hangs_m": round(drop if drop >= 0.03 * tall else 0.0, 3), "belted_at_z": round(belt, 3) if belt is not None else None}

def lay_band(isl, under):
    """A belt or band: its inside wall goes onto what it is around, its outside keeps the thickness."""
    inside = [k for k in isl["points"] if gaps[k][0] > 0 and data["normal"][k].dot(gaps[k][2]) < -0.2]
    for k in inside:
        lay(k, under)
    held = set(inside)
    if inside:
        follow([k for k in isl["points"] if k not in held], inside)

def body_spots(points):
    """Where to look for skin coming through: the body's points and three spots along each of its edges (an edge
    down a limb's corner can stand out through flat cloth all along), as (place, facing). Only the body's own
    outside counts: a leg's top sunk in the hips is "through" nothing."""
    out = []
    chosen = set(points)
    for k in points:
        n = data["normal"][k]
        if n.length < 0.5 or exit_of(body_tree, data["pos"][k] + n * 1e-4, n, 0.08 * tall) is not None:
            continue
        out.append((data["pos"][k], n))
        for j in data["links"][k]:
            if j > k and j in chosen and data["normal"][j].length > 0.5:
                facing = data["normal"][k] + data["normal"][j]
                if facing.length > 0.5:
                    for t in (0.25, 0.5, 0.75):
                        out.append((data["pos"][k].lerp(data["pos"][j], t), facing.normalized()))
    return out

def lift_over_body(isl, spots):
    """Where a corner or an edge of the body still stands out through a face of this piece (the cloth has fewer
    points than the body has there), lift that face's points until it clears. Done piece by piece as each is
    laid, so whatever is worn over it is laid over the lifted cloth. Returns how many spots were covered this way."""
    lo, hi = isl_box(isl)
    near = [(p, n) for p, n in spots if all(lo[i] - 2 * step < p[i] < hi[i] + 2 * step for i in range(3))]
    rings = [ring for fi, ring in isl["faces"]]
    cleared = 0
    for _ in range(3):
        cloth = tree_of(data["pos"], rings)
        lift = {}
        for p, n in near:
            hit = cloth.ray_cast(p - n * 1e-4, -n, 2 * step)  # a corner stands out a little; anything deeper is not a corner
            if hit[0] is None or hit[1].dot(n) < 0.2 or hit[3] < 1e-4:
                continue
            cleared += 1
            for j in rings[hit[2]]:
                lift[j] = max(lift.get(j, 0.0), hit[3] + 0.3 * step)
        if not lift:
            break
        for j, by in lift.items():
            data["pos"][j] = data["pos"][j] + data["normal"][j] * by
    return cleared

def isl_box(isl):
    """A piece's box where its points are now."""
    pts = [data["pos"][k] for k in isl["points"]]
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]

def stats(values):
    return {"median": round(100 * middle_of(values), 2), "p95": round(100 * share_of(values, 0.95), 2), "max": round(100 * max(values), 2)} if values else None


scene = bpy.context.scene
light = bpy.data.objects.get(PARAMS["object"]) if PARAMS["object"] else None
if light is None:
    held = [o for o in scene.objects if o.type == "MESH" and o.get("forge_groups") and o.data.attributes.get("forge_group")]
    light = held[0] if held else None
joined_body = 0
if light is None:
    bodies = [o for o in scene.objects if o.type == "MESH" and o.get("forge") == "body" and not o.name.startswith("lines:")]
    if len(bodies) > 1:  # a body written as "body" and "body under: ..." meshes is one mesh again
        whole = [o for o in bodies if not o.get("under")] or bodies
        for o in bpy.context.selected_objects:
            o.select_set(False)
        for o in bodies:
            o.hide_set(False)
            o.select_set(True)
        bpy.context.view_layer.objects.active = whole[0]
        bpy.ops.object.join()
        joined_body = len(bodies)
        body = bpy.context.view_layer.objects.active
        if "under" in body:
            del body["under"]
        body.name = body.data.name = "body"
layers = gather(light)
if PARAMS["move"] is None:  # a .glb written after draping carries "draped" on its body: its clothes are already where they belong
    PARAMS["move"] = not any(layer["obj"].get("draped") for layer in layers)
if not layers or layers[0]["tag"].get("forge") != "body":
    raise ValueError("no body to drape over: this needs a block-out with gear (build.py pieces with \"gear\"), or a .glb's \"body\" and \"gear: ...\" meshes")
if len(layers) < 2:
    raise ValueError("no gear to drape: every piece is body")
data = survey(layers)
flesh = [p for p, li in zip(data["pos"], data["layer"]) if layers[li]["tag"].get("forge") == "body"]
tall = max(p.z for p in flesh) - min(p.z for p in flesh)  # the body's own height: gear moves, and nothing here may depend on where it went
step = PARAMS["clearance"] * tall
pieces = PARAMS["pieces"]
if pieces is None and light is not None and light.get("forge_build"):
    pieces = json.loads(light["forge_build"]).get("pieces")
boxes = piece_boxes(pieces)
triangles_before = sum(len(ring) - 2 for li, fi, ring in data["faces"])

body_tree = tree_of(data["pos"], [ring for li, fi, ring in data["faces"] if layers[li]["tag"].get("forge") == "body"])
islands = islands_of(data, layers, boxes)
gaps = {k: gap_of(k) for isl in islands for k in isl["points"]}
stored = {}
for layer in layers:
    if layer["obj"].get("drape"):
        stored.update(json.loads(layer["obj"]["drape"]))
for isl in islands:
    isl["fit"], isl["why"] = judge(isl)
rings_added, body_rings = 0, 0
if PARAMS["rings"] and PARAMS["move"] and light is not None:
    rings_added, body_rings = add_rings(light, islands)
    if rings_added or body_rings:
        layers = gather(light)
        data = survey(layers)
        islands = islands_of(data, layers, boxes)
        gaps = {k: gap_of(k) for isl in islands for k in isl["points"]}
        for isl in islands:
            isl["fit"], isl["why"] = judge(isl)

for isl in islands:  # a belt, sash or band worn around the middle: it goes on last, and loose cloth hangs from under it
    isl["girds"] = isl["fit"] == "band" or (isl["fit"] != "stiff" and isl["centered"] and bool(has_word(isl["name"], BELTS)))
before = {k: data["pos"][k].copy() for isl in islands for k in isl["points"]}
gap_before = {k: gaps[k][0] for k in gaps}
hang, moved, laid = {}, {}, []  # laid: the faces of pieces already on the body, which later pieces sit over

for isl in islands:
    if isl["fit"] == "stiff" and (isl["hi"] - isl["lo"]).length >= 0.15 * tall:
        laid += [(isl["gear"], ring) for fi, ring in isl["faces"]]
lifted = 0
skin_spots = body_spots([k for k in range(len(data["pos"])) if layers[data["layer"][k]]["tag"].get("forge") == "body"])
for isl in sorted([i for i in islands if i["fit"] != "stiff"], key=inner_first):
    under = tree_of(data["pos"], [ring for gear, ring in laid if gear != isl["gear"]])  # its own gear's other pieces are beside it, not under it
    if isl["fit"] == "loose":
        isl["hang"] = lay_loose(isl, under)
    elif PARAMS["move"] and isl["fit"] == "tight":
        for k in isl["points"]:
            lay(k, under)
    elif PARAMS["move"]:
        lay_band(isl, under)
    if PARAMS["move"]:
        lifted += lift_over_body(isl, skin_spots)
    laid += [(isl["gear"], ring) for fi, ring in isl["faces"]]
if PARAMS["move"]:
    shifted = [k for k in before if (data["pos"][k] - before[k]).length > 1e-6]
    for isl in islands:  # a buckle, a button, a knot: carried along with the cloth it sits on
        if isl["fit"] != "stiff" or (isl["hi"] - isl["lo"]).length >= 0.15 * tall or not shifted:
            continue
        mine = set(isl["points"])
        near = [j for j in shifted if j not in mine and all(isl["lo"][i] - 0.02 * tall < before[j][i] < isl["hi"][i] + 0.02 * tall for i in range(3))]
        if near:
            carry = sum((data["pos"][j] - before[j] for j in near), Vector()) / len(near)
            for k in isl["points"]:
                data["pos"][k] = before[k] + carry
    for k in before:
        moved[k] = (data["pos"][k] - before[k]).length
        if moved[k] > 1e-7:
            for obj, vi in data["members"][k]:
                obj.data.vertices[vi].co = obj.matrix_world.inverted() @ data["pos"][k]
    for layer in layers:
        layer["obj"].data.update()
gaps = {k: gap_of(k) for k in before}

# ---- which body faces does worn gear hide completely? ----
masks, under_of = [[]], {}
if PARAMS["mask"]:
    soft, hard = {}, {}
    for isl in islands:
        if isl["fit"] == "stiff":
            hard.setdefault(isl["gear"], []).extend([ring for fi, ring in isl["faces"]])
        else:
            soft.setdefault(isl["gear"], []).extend([(isl, ring) for fi, ring in isl["faces"]])
    hangs = {isl["gear"] for isl in islands if isl["fit"] == "loose"}
    cloth_of = soft
    soft = {g: tree_of(data["pos"], [ring for isl, ring in f]) for g, f in soft.items() if f}
    hard = {g: tree_of(data["pos"], f) for g, f in hard.items() if f}
    for li, fi, ring in data["faces"]:
        if layers[li]["tag"].get("forge") != "body":
            continue
        corners = [data["pos"][k] for k in ring]
        mid = sum(corners, Vector()) / len(corners)
        facing = (layers[li]["obj"].matrix_world.to_3x3() @ layers[li]["obj"].data.polygons[fi].normal).normalized()
        spots = [mid] + [mid + (p - mid) * 0.85 for p in corners]
        # Hidden means hidden from every side: straight out and at a slant four ways, the gear is there. A face
        # under a hat's brim or just inside a collar is covered straight out but seen from below, and stays.
        side = facing.orthogonal().normalized()
        ways = [facing] + [(facing * 0.766 + lean * 0.643).normalized() for lean in (side, -side, facing.cross(side), -facing.cross(side))]
        over = []
        for g in sorted(set(soft) | set(hard)):
            hidden = True
            for p in spots:
                for way in ways:
                    ok = False
                    if g in soft:
                        hit = soft[g].ray_cast(p + facing * 1e-4, way, 0.08 * tall if g in hangs else 0.03 * tall)  # loose cloth stands further off
                        ok = hit[0] is not None and hit[1].dot(way) > 0
                        if ok and cloth_of[g][hit[2]][0].get("hang"):  # not under the last quarter of a hanging piece: a hem can swing clear of the leg
                            hung = cloth_of[g][hit[2]][0]["hang"]
                            ok = hung["hangs_m"] <= 0 or hit[0].z > hung["hangs_from_z"] - 0.75 * hung["hangs_m"]
                    if not ok and g in hard:  # inside a boot or a hat: its wall is that way, or right here (a sole on a sole)
                        ok = hard[g].ray_cast(p + facing * 1e-4, way, 0.08 * tall)[0] is not None or hard[g].find_nearest(p)[3] < 1.5 * step
                    if not ok:
                        hidden = False
                        break
                if not hidden:
                    break
            if hidden:
                over.append(g)
        if over:
            if over not in masks:
                masks.append(over)
            under_of[(li, fi)] = masks.index(over)
for layer in layers:
    obj = layer["obj"]
    if layer["tag"].get("forge") == "body":
        mark = obj.data.attributes.get("forge_under") or obj.data.attributes.new("forge_under", "INT", "FACE")
        mark.data.foreach_set("value", [0] * len(obj.data.polygons))
        obj["forge_masks"] = json.dumps(masks)
        obj["draped"] = 1
for (li, fi), index in under_of.items():
    layers[li]["obj"].data.attributes["forge_under"].data[fi].value = index

# ---- notes on the points, for cloth.py ----
fit_of, island_of = {}, {}
for number, isl in enumerate(islands):
    for k in isl["points"]:
        fit_of[k], island_of[k] = FITS.get(isl["fit"], 3), number + 1
for obj in {layer["obj"].name: layer["obj"] for layer in layers}.values():
    count = len(obj.data.vertices)
    notes = {"forge_fit": [0] * count, "forge_island": [0] * count, "forge_hang": [0.0] * count}
    for k in fit_of:
        for owner, vi in data["members"][k]:
            if owner == obj:
                notes["forge_fit"][vi], notes["forge_island"][vi], notes["forge_hang"][vi] = fit_of[k], island_of[k], hang.get(k, 0.0)
    kept = {}
    for isl in islands:
        if layers[isl["layer"]]["obj"] == obj:
            kept.setdefault(isl["gear"], []).append({"name": isl["name"], "fit": isl["fit"], "lo": [round(v, 4) for v in isl_box(isl)[0]], "hi": [round(v, 4) for v in isl_box(isl)[1]],
                                                     "line": isl["hang"]["hangs_from_z"] if isl.get("hang") else None})
    obj["drape"] = json.dumps(kept)  # what each part was taken for, which export.py writes into the file with the gear
    obj["forge_hangs"] = json.dumps({str(number + 1): [isl["hang"]["hangs_from_z"], isl["hang"]["hangs_m"]] for number, isl in enumerate(islands) if isl.get("hang")})
    for name, values in notes.items():
        old = obj.data.attributes.get(name)
        if old is not None:
            obj.data.attributes.remove(old)
        obj.data.attributes.new(name, "FLOAT" if name == "forge_hang" else "INT", "POINT").data.foreach_set("value", values)

# ---- is any skin still showing through, standing still? Spots on body faces that stay drawn, with cloth behind them. ----
showing = {}
worn = [isl for isl in islands if isl["fit"] != "stiff"]  # through cloth, that is: a boot or a pair of glasses is as it was built
cloth = tree_of(data["pos"], [ring for isl in worn for fi, ring in isl["faces"]])
owner = [isl["gear"] for isl in worn for fi, ring in isl["faces"]]
drawn_points = set()
for li, fi, ring in data["faces"]:
    if layers[li]["tag"].get("forge") == "body" and (li, fi) not in under_of:
        drawn_points.update(ring)
for p, n in body_spots(sorted(drawn_points)) if cloth is not None else []:
    hit = cloth.ray_cast(p - n * 1e-4, -n, 0.03 * tall)
    if hit[0] is not None and hit[1].dot(n) > 0.2 and hit[3] > 0.001:
        showing[owner[hit[2]]] = showing.get(owner[hit[2]], 0) + 1

# ---- what happened ----
soft_points = [k for isl in islands if isl["fit"] != "stiff" for k in isl["points"]]
touching = [k for isl in islands if isl["fit"] in ("tight", "loose") for k in isl["points"] if hang.get(k, 0.0) == 0.0 and -BURIED * tall < gap_before[k] < 0.08 * tall]
listed = {}
for isl in islands:
    key = (isl["name"], isl["gear"], isl["fit"])
    if key not in listed:
        listed[key] = {"piece": isl["name"], "gear": isl["gear"], "fit": isl["fit"], "why": isl["why"], "parts": 0, "points": []}
        if isl.get("hang"):
            listed[key].update(isl["hang"])
    listed[key]["parts"] += 1
    listed[key]["points"] += isl["points"]
for entry in listed.values():
    points = entry.pop("points")
    entry["moved_cm"] = [round(100 * middle_of([moved.get(k, 0.0) for k in points]), 2), round(100 * max(moved.get(k, 0.0) for k in points), 2)]
    entry["off_body_cm"] = [round(100 * middle_of([gap_before[k] for k in points]), 2), round(100 * middle_of([gaps[k][0] for k in points]), 2)]
faces_hidden = {}
for (li, fi), index in under_of.items():
    faces_hidden[index] = faces_hidden.get(index, 0) + len(layers[li]["obj"].data.polygons[fi].vertices) - 2
result = {
    "object": light.name if light is not None else None, "meshes": sorted({layer["obj"].name for layer in layers}),
    "height": round(tall, 3), "clearance_cm": round(100 * step, 2), "moved": bool(PARAMS["move"]), "body_meshes_joined": joined_body,
    "pieces": sorted(listed.values(), key=by_gear),
    "gap_where_it_touches_cm": {"before": stats([max(gap_before[k], 0.0) for k in touching]), "after": stats([max(gaps[k][0], 0.0) for k in touching])},
    "points_inside_the_body": {"before": sum(1 for k in soft_points if -BURIED * tall < gap_before[k] < -1e-4), "after": sum(1 for k in soft_points if -BURIED * tall < gaps[k][0] < -1e-4),
                               "built_in_deep": sum(1 for k in soft_points if gaps[k][0] <= -BURIED * tall)},
    "skin_showing_through": {"points": sum(showing.values()), "through": showing},
    "rings_added": rings_added, "body_rings_added": body_rings, "lifted_over_body_corners": lifted,
    "triangles": {"before": triangles_before, "after": sum(len(ring) - 2 for li, fi, ring in data["faces"])},
    "masks": [{"under": masks[i], "body_triangles": faces_hidden.get(i, 0)} for i in range(1, len(masks))],
    "body_triangles_hidden_when_dressed": sum(faces_hidden.values()),
}
print("RESULT " + json.dumps(result))
