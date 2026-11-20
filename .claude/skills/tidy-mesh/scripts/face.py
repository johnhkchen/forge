# Find the face on a character's detailed head, and print it as a ready-made
# "head" piece for build.py. Changes nothing but its own guide lines.
#
# Give it the head's box (from measure.py or by eye) and which way the face
# looks. The box runs from under the chin (or beard) to the top of the
# skull, or to the brim if there is a hat or helmet, which is its own
# piece; ears in, neck and shoulders out; its back wall where the skull
# ends or sinks into the body. It looks at the head front-on, a few hundred
# points, and reads two things: how far forward the surface is (brow, nose,
# lips and chin stick out; eye sockets and the mouth sink in) and how dark
# the texture is (eyes and mouth are dark bands). From those it works out
# how high the chin, mouth, nose, eyes and brow sit, how wide the head is at
# each, eye and mouth widths, the underbite, tusks, ears, and the skin,
# socket and mouth colors.
#
# It also keeps the head's surface itself (front, back and width, row by
# row) in the scene, under the piece's name; the piece's "scan" points at
# it, and build.py lays the head's points on it, so the built head has the
# reference's outline, skull, cheeks and jaw, not a box's. Whatever is in
# the box gets followed: keep a collar, shoulders or a hat out of it.
#
# The result's "head" is the piece: paste it into build.py's "parts" as it
# is, then change what you like (build.py's notes list every setting).
# "found" says how each feature was found: "texture", "shape", or "guess"
# when neither showed it; check guesses against the picture. "profile" has
# the numbers it read, row by row, top to bottom.
#
# With "show": True it draws the box and a line at each feature's height as
# a wire object, "Look: face". look(mode="angles", target=["Look: face"])
# frames the head; the lines should sit on the brow, eyes, nose, mouth and
# chin. If one is off, set that row's height in "head" yourself. The lines
# never render or export; a run with "show": False removes them.
#
# Send this whole file through the blender MCP `execute_blender_code` tool
# after editing PARAMS. Prints RESULT {json}. About 2 s. Safe-mode compatible.

PARAMS = {
    "object": None,      # the detailed mesh; None = the largest visible mesh
    "box": None,         # the head: {"min": [x, y, z], "max": [x, y, z]} in world meters (required)
    "facing": "-y",      # which way the face looks: "-y", "+y", "-x" or "+x"
    "kind": "creature",  # "creature" (troll, orc, goblin) or "human"; passed on to build.py
    "name": "head",      # the piece's name
    "show": True,        # draw the guide lines
}

import bpy
import json
from mathutils import Vector

FACING = {"-y": (1, -1.0), "+y": (1, 1.0), "-x": (0, -1.0), "+x": (0, 1.0)}
ROWS, LANES = 44, 12  # how finely it looks: rows up the head, lanes from the center line to each side


def face_count(obj):
    return len(obj.data.polygons)

def pick_object(name):
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise ValueError("no mesh object named %r" % name)
        return obj
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get() and not o.name.endswith(" (light)")]
    if not meshes:
        raise ValueError("the scene has no visible mesh objects")
    return max(meshes, key=face_count)

def color_image(obj):
    """The picture that colors the surface, or None if it is one flat color."""
    mats = [m for m in obj.data.materials if m and m.use_nodes]
    if not mats or not obj.data.uv_layers.active:
        return None
    queue = [link.from_node for n in mats[0].node_tree.nodes if n.type == "BSDF_PRINCIPLED" for link in n.inputs["Base Color"].links]
    for _ in range(60):
        if not queue:
            break
        node = queue.pop(0)
        if node.type == "TEX_IMAGE" and node.image:
            return node.image
        for socket in node.inputs:
            queue += [link.from_node for link in socket.links]
    return None

def linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None

def middle(values):
    values = sorted(v for v in values if v is not None)
    return values[len(values) // 2] if values else None

def mix(a, b, t):
    return a + (b - a) * t

def best(rows, values):
    """The row (an index) where `values` is highest."""
    top = rows[0]
    for i in rows:
        if values[i] > values[top]:
            top = i
    return top

def smooth(values):
    return [mean(values[max(i - 1, 0):i + 2]) for i in range(len(values))]

def r3(v):
    return round(v, 3)


if not PARAMS["box"]:
    raise ValueError("set PARAMS['box'] to the head's box")
obj = pick_object(PARAMS["object"])
a, sign = FACING[PARAMS["facing"]]
u = 1 - a
lo, hi = PARAMS["box"]["min"], PARAMS["box"]["max"]
center, half = (lo[u] + hi[u]) / 2, (hi[u] - lo[u]) / 2
back, wall = min(sign * lo[a], sign * hi[a]), max(sign * lo[a], sign * hi[a])
row_step = (hi[2] - lo[2]) / ROWS

# Look at the head front-on: one ray per row, lane and side.
bpy.context.view_layer.update()
world = obj.matrix_world
inverse = world.inverted()
aim = [0.0, 0.0, 0.0]
aim[a] = -sign
aim = (inverse.to_3x3() @ Vector(aim)).normalized()
image = color_image(obj)
if image:
    wide_px, tall_px = image.size
    pixels = image.pixels[:]
    # A color picture is stored sRGB even when its tag says otherwise (one image shared with the normal map gets tagged Non-Color).
    srgb = not image.colorspace_settings.name.startswith("Linear")
    uvs = obj.data.uv_layers.active.data
polygons, vertices, loops = obj.data.polygons, obj.data.vertices, obj.data.loops
depth, light, tint, facing = [], [], [], []  # per row and lane: how far forward, how light (0-1), color, how squarely it faces front
for j in range(ROWS):
    z = lo[2] + (j + 0.5) * row_step
    d_row, l_row, t_row, f_row = [], [], [], []
    for i in range(LANES):
        ds, ls, ts, fs = [], [], [], []
        for side in (1, -1):
            start = [0.0, 0.0, z]
            start[u], start[a] = center + side * (i + 0.5) / LANES * half, sign * (wall + (wall - back))
            hit, where, normal, index = obj.ray_cast(inverse @ Vector(start), aim)
            if not hit or sign * (world @ where)[a] < back:
                continue
            ds.append(sign * (world @ where)[a])
            fs.append(-normal.dot(aim))
            if image:
                near, gap = None, None
                for corner in polygons[index].loop_indices:  # the nearest corner's spot in the picture
                    away = (vertices[loops[corner].vertex_index].co - where).length
                    if gap is None or away < gap:
                        near, gap = corner, away
                x, y = uvs[near].uv
                at = 4 * (int(y % 1 * tall_px) % tall_px * wide_px + int(x % 1 * wide_px) % wide_px)
                rgb = pixels[at:at + 3]
                ls.append(0.3 * rgb[0] + 0.6 * rgb[1] + 0.1 * rgb[2])
                ts.append([linear(c) if srgb else c for c in rgb])
        d_row.append(mean(ds))
        f_row.append(mean(fs))
        l_row.append(mean(ls))
        t_row.append([mean([t[k] for t in ts]) for k in range(3)] if ts else None)
    depth.append(d_row)
    light.append(l_row)
    tint.append(t_row)
    facing.append(f_row)
# Going outward along a row, the head ends where its side has turned away and the surface then faces
# front again well behind the face (the chest around a sunk head), or drops far behind it.
face_front = middle([row[0] for row in depth])
if face_front is None:
    raise ValueError("nothing inside the box faces %s: check the box and 'facing'" % PARAMS["facing"])
flaps = []  # per row: the cells cut off because they face front again behind the head's side: an ear, or the chest
for j in range(ROWS):
    turned, ended, flap = False, False, []
    for i in range(LANES):
        if None in (depth[j][0], depth[j][i]):
            continue
        behind = min(depth[j][0], face_front) - depth[j][i]
        turned = turned or (facing[j][i] < 0.45 and i >= 0.4 * LANES)  # nearer the middle it is the side of a nose
        far = behind > 0.6 * max(hi[2] - lo[2], wall - back)
        ended = ended or far or (turned and facing[j][i] > 0.7 and behind > 0.12 * (hi[2] - lo[2]))
        if ended:
            if not far:
                flap.append((i, depth[j][i]))
            depth[j][i] = light[j][i] = tint[j][i] = None
    flaps.append(flap)

# The same rows and lanes seen from behind, for the back of a head that stands free of the body.
# Where the head is sunk into the body there is nothing to see, and the box's back wall stands in.
rear = []
far_off = max(obj.dimensions) * 2
for j in range(ROWS):
    row = []
    for i in range(LANES):
        seen = []
        for side in (1, -1):
            if depth[j][i] is None:
                continue
            start = [0.0, 0.0, lo[2] + (j + 0.5) * row_step]
            start[u], start[a] = center + side * (i + 0.5) / LANES * half, sign * (back - far_off)
            hit, where, _, _ = obj.ray_cast(inverse @ Vector(start), -aim)
            if hit and back <= sign * (world @ where)[a] <= depth[j][i]:
                seen.append(sign * (world @ where)[a])
        row.append(mean(seen))
    rear.append(row)

# One line per row: where it is, how wide the head is there, how far forward
# the middle of the face and the eye lanes are, and how dark each is.
reach = [max([i + 1 for i in range(LANES) if depth[j][i] is not None] or [0]) for j in range(ROWS)]
usual = middle([r for r in reach if r]) or 1
mid_lanes = [i for i in range(LANES) if i + 0.5 <= max(1.0, 0.18 * usual)]
eye_lanes = [i for i in range(LANES) if 0.3 * usual <= i + 0.5 <= 0.7 * usual] or mid_lanes
kept = [j for j in range(ROWS) if mean([depth[j][i] for i in mid_lanes]) is not None]
if len(kept) < 8:
    raise ValueError("almost nothing inside the box faces %s: check the box and 'facing'" % PARAMS["facing"])
zs = [lo[2] + (j + 0.5) * row_step for j in kept]
wide = smooth([reach[j] / LANES * half for j in kept])
mid = smooth([mean([depth[j][i] for i in mid_lanes]) for j in kept])
lane = smooth([mean([depth[j][i] for i in eye_lanes]) or mean([depth[j][i] for i in mid_lanes]) for j in kept])
dark_mid = smooth([1 - (mean([light[j][i] for i in mid_lanes]) or 0) for j in kept]) if image else None
dark_lane = smooth([1 - (mean([light[j][i] for i in eye_lanes]) or 0) for j in kept]) if image else None
n = len(kept)
found = {}

def rows_between(low, high):
    return [i for i in range(n) if low <= zs[i] <= high]

def row_at(z):
    near = 0
    for i in range(n):
        if abs(zs[i] - z) < abs(zs[near] - z):
            near = i
    return near

def dark_lanes(rows, limit):
    """Across these rows, the run of lanes darker than `limit` around the darkest one: the first and one past the last."""
    dark = [1 - (mean([light[kept[r]][i] for r in rows]) or 1) for i in range(LANES)]
    reach_in = max(1, int(0.8 * usual))  # past that is the side of the head: hair, ears
    low = high = best(range(reach_in), dark)
    while low and dark[low - 1] >= limit:
        low -= 1
    while high + 1 < reach_in and dark[high + 1] >= limit:
        high += 1
    return low, high + 1

def usual_color(rows, lanes):
    """The usual color and lightness of these cells, or None."""
    cells = [(light[kept[r]][i], tint[kept[r]][i]) for r in rows for i in lanes if light[kept[r]][i] is not None]
    if not cells:
        return None
    return [r3(middle([c[1][k] for c in cells])) for k in range(3)], middle([c[0] for c in cells])

def darkest(rows, lanes):
    """The color of the darkest third of these cells."""
    cells = sorted([(light[kept[r]][i], tint[kept[r]][i]) for r in rows for i in lanes if light[kept[r]][i] is not None], key=first)
    cells = cells[:max(1, len(cells) // 3)]
    return [r3(mean([c[1][k] for c in cells])) for k in range(3)] if cells else None

def first(pair):
    return pair[0]


# Chin: below the most forward point of the jaw, where the profile falls back toward the neck.
top_z = hi[2]
jaw = best(rows_between(lo[2], mix(lo[2], top_z, 0.5)) or [0], mid)
chin = jaw
while chin > 0 and mid[chin - 1] >= mid[jaw] - 0.15 * (hi[2] - lo[2]):
    chin -= 1
chin_z = zs[chin] - row_step / 2 if chin else lo[2]
tall = top_z - chin_z
found["chin"] = {"z": r3(chin_z), "by": "shape" if chin else "the bottom of the box"}

# Eyes: the darkest band across the eye lanes, or else the deepest hollow in them.
span = rows_between(chin_z + 0.35 * tall, chin_z + 0.9 * tall) or [n - 1]
gap = max(1, round(0.1 * tall / row_step))
hollow = [(lane[max(i - gap, 0)] + lane[min(i + gap, n - 1)]) / 2 - lane[i] for i in range(n)]
proud = [mid[i] - lane[i] for i in range(n)]  # how far the middle stands out from the cheeks beside it
eye, eye_tall, eye_span, by = None, None, None, "guess"
for _ in range(3 if image else 0):
    if not span:
        break
    pick = best(span, dark_lane)
    usual_dark = middle([dark_lane[i] for i in span])
    if dark_lane[pick] - usual_dark < 0.08:
        break
    limit = mix(usual_dark, dark_lane[pick], 0.5)
    low = high = pick
    while low - 1 in span and dark_lane[low - 1] >= limit:
        low -= 1
    while high + 1 < n and dark_lane[high + 1] >= limit:
        high += 1
    if high == n - 1 and low > span[0] + 2:  # dark all the way to the top is hair or a hat: look below it
        span = [i for i in span if i < low]
        continue
    eye, eye_tall, by = row_at((zs[low] + zs[high]) / 2), (high - low + 1) * row_step, "texture"
    eye_z = (zs[low] + zs[high]) / 2
    eye_span = dark_lanes(range(low, high + 1), limit)
    break
if eye is None:
    # With no dark band to go by: a hollow a little above the tip of the nose, or else a third of
    # the way from there to the top of the head, where eyes usually are.
    span = rows_between(chin_z + 0.35 * tall, chin_z + 0.9 * tall) or [n - 1]
    usually = chin_z + 0.62 * tall
    tip = best(rows_between(chin_z + 0.25 * tall, chin_z + 0.75 * tall) or [0], proud)
    if proud[tip] >= 0.01 * tall:
        span = rows_between(mix(zs[tip], top_z, 0.15), mix(zs[tip], top_z, 0.55)) or span
        usually = mix(zs[tip], top_z, 0.3)
    pick = best(span, hollow)
    if hollow[pick] > 0.01 * tall:
        eye, by = pick, "shape"
    else:
        eye = row_at(usually)
    eye_z = zs[eye]
found["eyes"] = {"z": r3(eye_z), "by": by}
eye_top = eye_z + max(eye_tall or 0, 0.12 * tall) / 2

# Brow: the most forward row of the eye lanes just above the eyes.
span = rows_between(eye_top, eye_z + 0.3 * tall)
if span:
    brow = best(span, lane)
    brow_z, by = zs[brow], "shape"
else:
    brow_z, by = min(eye_top + 0.04 * tall, mix(eye_z, top_z, 0.6)), "guess"
    brow = row_at(brow_z)
found["brow"] = {"z": r3(brow_z), "by": by}

# Nose: in the upper half between chin and eyes, where the middle stands out most from the cheeks beside it.
span = rows_between(chin_z + 0.45 * (eye_z - chin_z), eye_z - max(eye_tall or 0, 0.12 * tall) / 2 - row_step)
nose = best(span, proud) if span else None
if nose is not None and proud[nose] >= 0.01 * tall:
    nose_z, nose_out, by = zs[nose], proud[nose], "shape"
    lanes = [i for i in range(LANES) if depth[kept[nose]][i] is not None and depth[kept[nose]][i] >= mid[nose] - 0.5 * nose_out]
    nose_wide = max(1, len(lanes)) / LANES * half
else:
    nose_z, nose_out, nose_wide, by = mix(chin_z, eye_z, 0.62), None, None, "guess"
    nose = row_at(nose_z)
found["nose"] = {"z": r3(nose_z), "by": by}

# Mouth: between chin and nose, the darkest row down the middle, or else a crease in the profile.
span = rows_between(chin_z + 0.12 * (nose_z - chin_z), nose_z - 0.2 * (nose_z - chin_z))
mouth, mouth_wide, mouth_tall, by = None, None, None, "guess"
if image and span:
    pick = best(span, dark_mid)
    usual_dark = middle([dark_mid[i] for i in span])
    if dark_mid[pick] - usual_dark >= 0.05:
        mouth, by = pick, "texture"
        limit = mix(usual_dark, dark_mid[pick], 0.5)
        run = dark_lanes([pick], limit)
        mouth_wide = run[1] / LANES * half if run[0] <= 1 else None
        mouth_tall = len([i for i in span if dark_mid[i] >= limit]) * row_step
if mouth is None and span:
    crease = [0.0] + [(mid[i - 1] + mid[i + 1]) / 2 - mid[i] for i in range(1, n - 1)] + [0.0]
    pick = best(span, crease)
    if crease[pick] > 0.004 * tall:
        mouth, by = pick, "shape"
if mouth is None:
    mouth = row_at(mix(chin_z, nose_z, 0.45))
mouth_z = min(max(zs[mouth], chin_z + 0.06 * tall), nose_z - 0.06 * tall)
found["mouth"] = {"z": r3(mouth_z), "by": by}
upper = min([mid[i] for i in range(mouth + 1, nose)] or [mid[mouth]])
lower = max([mid[i] for i in range(chin, mouth + 1)] or [mid[mouth]])
underbite = max(0.0, lower - upper)

# Tusks: a lane off the center line that juts out from the lanes beside it, between chin and eyes.
tusks = None
spikes = []
for r in rows_between(chin_z, eye_z - 0.1 * tall):
    across = depth[kept[r]]
    spikes += [(i, r) for i in range(2, LANES - 2) if None not in (across[i - 2], across[i], across[i + 2])
               and across[i] - max(across[i - 2], across[i + 2]) >= 0.06 * tall]
at = middle([i for i, _ in spikes])
high, low = max([r for i, r in spikes if abs(i - at) <= 1] or [0]), min([r for i, r in spikes if abs(i - at) <= 1] or [0])
if len(spikes) >= 2 and zs[low] - 0.12 * tall <= mouth_z <= zs[high] + 0.12 * tall:  # it has to start at the mouth
    drop_up = depth[kept[high]][at] - ((depth[kept[high + 1]][at] if high + 1 < n else None) or back)
    drop_down = depth[kept[low]][at] - ((depth[kept[low - 1]][at] if low else None) or back)
    rising = drop_up >= drop_down  # the free end is the one with nothing beyond it
    tusks = {"at": r3((at + 0.5) / LANES * half), "from": "below" if rising else "above", "long": r3(zs[high] - zs[low] + row_step),
             "front": r3(sign * max(depth[kept[r]][i] for i, r in spikes if abs(i - at) <= 1)),
             "z": r3(zs[low] - row_step / 2 if rising else zs[high] + row_step / 2)}

# Ears: a short band of rows, around eye height, with a flap out beyond the side of the head.
# Flaps on most rows are the chest and shoulders around a sunk head instead.
ears = None
flapped = [r for r in range(n) if flaps[kept[r]]]
band = [r for r in flapped if nose_z <= zs[r] <= eye_z + 0.3 * tall]
if len(band) >= 2 and len(flapped) <= 0.6 * n:
    cells = [cell for r in band for cell in flaps[kept[r]]]
    root = min(i for i, _ in cells) / LANES * half
    ears = {"z": r3(mean([zs[r] for r in band])), "front": r3(sign * mean([d for _, d in cells])),
            "long": r3(max((max(i for i, _ in cells) + 1) / LANES * half - root, 0.08 * tall)),
            "tall": r3((len(band) + 1) * row_step)}

# The surface itself, for build.py to lay the head's points on: the front as seen (tusks smoothed
# away, since they are built on their own), the back, and the half-width, row by row.
surface = [list(depth[j]) for j in kept]
if tusks:
    for r in range(max(low - 1, 0), min(high + 2, n)):
        a0, a1 = max(at - 2, 0), min(at + 2, LANES - 1)
        if None not in (surface[r][a0], surface[r][a1]):
            for i in range(a0 + 1, a1):
                surface[r][i] = mix(surface[r][a0], surface[r][a1], (i - a0) / (a1 - a0))

def settled(grid):
    """Each cell averaged with the ones above and below it, rounded."""
    return [[None if grid[r][i] is None else round(mean([grid[q][i] for q in range(max(r - 1, 0), min(r + 2, len(grid)))]), 4)
             for i in range(LANES)] for r in range(len(grid))]

bpy.context.scene["face: " + PARAMS["name"]] = json.dumps({
    "zs": [round(z, 4) for z in zs], "half": half, "wide": [round(w, 4) for w in wide],
    "front": settled(surface), "back": settled([rear[j] for j in kept]),
})

top = row_at(mix(brow_z, top_z, 0.55))
rows = {
    "chin": [chin_z, (mid[chin] + mid[jaw]) / 2, wide[jaw]],
    "mouth": [mouth_z, upper, wide[mouth]],
    "nose": [nose_z, lane[nose], wide[nose]],
    "eyes": [eye_z, lane[eye], wide[eye]],
    "brow": [brow_z, min(lane[brow], lane[eye] + 0.12 * tall), wide[brow]],  # farther out than that is a hat's brim
    "top": [zs[top], min(mid[top], lane[brow], lane[eye] + 0.12 * tall), wide[top]],
}
order = ("chin", "mouth", "nose", "eyes", "brow", "top")
for below, above in zip(order, order[1:]):  # build.py needs them to climb
    if rows[above][0] < rows[below][0] + 0.04 * tall:
        rows[above][0] = rows[below][0] + 0.04 * tall
        if above in found:
            found[above] = {"z": r3(rows[above][0]), "by": "guess"}

face = {"underbite": r3(underbite)}
if eye_tall:
    face["eye_tall"] = r3(eye_tall)
if eye_span:
    face["eye_in"], face["eye_out"] = r3(eye_span[0] / LANES * half), r3(eye_span[1] / LANES * half)
if nose_out:
    face["nose_out"], face["nose_wide"] = r3(nose_out), r3(nose_wide)
if mouth_wide:
    face["mouth_wide"] = r3(max(mouth_wide, tusks["at"] + half / LANES) if tusks else mouth_wide)
if mouth_tall:
    face["mouth_tall"] = r3(mouth_tall)
piece = {
    "name": PARAMS["name"],
    "head": PARAMS["facing"],
    "kind": PARAMS["kind"],
    "box": {"min": [r3(v) for v in lo], "max": [r3(v) for v in hi]},
    "rows": {k: [r3(v[0]), r3(sign * v[1]), r3(v[2])] for k, v in rows.items()},
    "scan": PARAMS["name"],
    "face": face,
}
if tusks:
    piece["tusks"] = tusks
if ears:
    piece["ears"] = ears
if image:
    # Skin is the cheeks' usual color; a region gets its own color only where it clearly differs.
    face_lanes = range(max(1, int(0.8 * usual)))
    skin, skin_light = usual_color(rows_between(mix(mouth_z, nose_z, 0.5), eye_z - (eye_tall or 0.12 * tall) / 2) or [nose], face_lanes)
    piece["color"] = skin
    piece["colors"] = {}
    eye_rows = rows_between(eye_z - (eye_tall or 0.12 * tall) / 2, eye_z + (eye_tall or 0.12 * tall) / 2) or [eye]
    for key, color in (("socket", darkest(eye_rows, eye_lanes)), ("mouth", darkest([mouth], mid_lanes))):
        if color and sum(color) < 0.5 * sum(skin):
            piece["colors"][key] = color
    for key, where in (("beard", rows_between(chin_z, mouth_z - 0.05 * tall)), ("hair", rows_between(rows["top"][0], top_z))):
        usual_there = usual_color(where, face_lanes) if where else None
        if usual_there and usual_there[1] < 0.65 * skin_light:
            piece["colors"][key] = usual_there[0]
            found[key] = {"by": "texture", "why": "darker than the cheeks there; drop it from \"colors\" if that is a hat, a collar or shadow"}

guide = None
old = bpy.data.objects.get("Look: face")
if old:
    bpy.data.objects.remove(old, do_unlink=True)
if PARAMS["show"]:
    guide = "Look: face"
    points = [(x, y, z) for z in (lo[2], hi[2]) for y in (lo[1], hi[1]) for x in (lo[0], hi[0])]
    edges = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
    for key in order:
        z, front, reach_out = rows[key]
        for side in (-1, 1):
            p = [0.0, 0.0, z]
            p[u], p[a] = center + side * reach_out, sign * (front + 0.02 * tall)
            points.append(tuple(p))
        edges.append((len(points) - 2, len(points) - 1))
    me = bpy.data.meshes.new(guide)
    me.from_pydata(points, edges, [])
    marker = bpy.data.objects.new(guide, me)
    bpy.context.scene.collection.objects.link(marker)
    marker.display_type = "WIRE"
    marker.hide_render = True
    marker.hide_select = True

print("RESULT " + json.dumps({
    "object": obj.name,
    "textured": bool(image),
    "head": piece,
    "found": found,
    "profile": {
        "columns": ["height", "middle of the face, front", "eye lanes, front", "half-width", "darkness of the middle", "darkness of the eye lanes"],
        "rows": [[r3(zs[i]), r3(sign * mid[i]), r3(sign * lane[i]), r3(wide[i])] + ([r3(dark_mid[i]), r3(dark_lane[i])] if image else [])
                 for i in range(n - 1, -1, -2)],
    },
    "guide": guide,
    "next": "paste \"head\" into build.py's \"parts\"; look at it front-on and from the side next to the reference",
}))
