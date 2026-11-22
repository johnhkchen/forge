# Paint skin-tight clothes into the body's texture, instead of wearing them as
# meshes. For a body that is the wardrobe template (run wrap.py first).
#
# A singlet, tights or an undershirt lies flat on the skin: it has no outline
# of its own, so a mesh for it buys nothing and costs a lot. Two surfaces a
# few millimeters apart have to bend exactly alike or skin comes through, and
# on a deep bend they never quite do. Painted into the body's own texture the
# cloth IS the skin's surface: it cannot be poked through, it costs no
# triangles, and because every template body shares one texture layout, the
# same painted outfit fits anyone who has the template body.
#
# This is an option beside drape.py, not instead of it. Loose clothes (a kilt,
# a coat), boots, hats, belts and anything whose outline matters keep their
# meshes and are draped as before; only what you name in "garments" is painted.
#
# What it does, texel by texel of the template's texture (a texel is one dot
# of it; each knows where on the body it is and which way it faces):
#   - it looks in at the character's old body (wrap.py kept it, hidden, as
#     "base body") for the color there, and in from outside at the gear named
#     in "garments" for the outermost one lying on this very spot (not on a
#     neighboring limb). A garment's mesh counts where it lies close ("reach")
#     or is worn round the limb, like a flared leg; a strap built standing off
#     the shoulder or a flap sticking out under an arm does not.
#   - "trim": what a texel is goes by its color, not by which mesh it came
#     from, because a block-out garment is cut rougher than the real one. Its
#     own texture shows skin round the neck and under the arms; it shows the
#     garment worn under it where it was built too long; it shows the boot
#     tops where it was built down into the boots. And the old body's own
#     texture shows the garment where the mesh fell short (a real strap,
#     drawn on the chest). So each color goes to whichever it is most typical
#     of: one of the painted garments, this body's bare skin, or the gear
#     that stays. The wearer's skin never rides along in an outfit.
#   - each garment's edge is then evened out: slivers narrower than twice
#     "smooth" go, notches that narrow are filled, scraps off on their own
#     are dropped, small windows of skin inside the cloth are shut, patches
#     the old bake missed (plain black) go to whatever surrounds them, and
#     the edge is softened by one texel.
#   - skin is trusted where the old body shows skin by its color and no gear
#     that stays was over it or close by ("margin"): under a boot top the old
#     texture has boot in it. The rest is filled in from the trusted skin
#     around it, fading to the body's average skin color further in.
#   - the painted gear and what is in "take_off" are removed, with the base
#     body; other gear stays as meshes.
#
# Each garment is also saved as a picture of its own when "save" names a
# folder: <garment>.png, clear where the garment is not, and skin.png, the
# bare skin. Another template body wears one with "wear": [{"name": "wool
# singlet", "image": ".../wool singlet.png"}], laid over its own skin.
#
# Read the result. "garments" has, for each: what the source gave
# ("texels_where_its_mesh_lies", and of those how many showed skin, other
# gear or another painted garment in its own texture; "cloth_in_the_body's_
# texture": cloth the mesh missed), what evening the edge did ("edge": ours),
# and "ends": how far along each limb it reaches (0 at the limb's top joint,
# 1 at the next joint down: a singlet's leg at 0.40 ends 40% of the way from
# hip to knee), which should land the same on every body. "skin" says how
# much skin was trusted and how much filled in.
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down.
# Prints RESULT {json}. About ten seconds at 1024. Safe-mode compatible.

PARAMS = {
    "body": None,          # the template body wrap.py made; None = the one in the scene
    "garments": [],        # gear to paint on and take off, by name: the skin-tight pieces ("wool singlet", "wool tights")
    "wear": [],            # outfits painted for another body: [{"name": "wool singlet", "image": "/path/wool singlet.png"}]
    "take_off": [],        # gear to remove without painting it (the clothes an outfit from "wear" replaces)
    "texture_size": 1024,  # the painted texture, square
    "save": None,          # a folder to write each garment's picture and skin.png into; None = keep them in the file only
    "trim": True,          # False = paint whatever the garment meshes show where they lie, skin and ragged edges and all
    "reach": 0.02,         # a garment's mesh counts where it lies this close to the body, as a share of the height; further off only where it is worn round the limb
    "smooth": 0.006,       # half the narrowest sliver or notch an edge keeps, as a share of the height (0.006: about 2 cm on a person)
    "margin": 0.012,       # skin this close to gear is not trusted either, as a share of the height
    "keep_base": False,    # True = leave the base body and the painted gear in the scene, hidden
}

import bpy
import array
import json
import math
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

REGIONS = ["head", "upper_torso", "lower_torso", "upper_arm_l", "lower_arm_l", "hand_l", "upper_arm_r", "lower_arm_r", "hand_r",
           "upper_leg_l", "lower_leg_l", "foot_l", "upper_leg_r", "lower_leg_r", "foot_r"]
LIMB = {"upper_torso": ("trunk", "hips", "neck"), "lower_torso": ("trunk", "hips", "neck")}  # region -> (what "ends" calls it, joint at 0, joint at 1)
for side in "lr":
    LIMB["upper_arm_" + side] = ("upper_arm_" + side, "upper_arm_" + side, "forearm_" + side)
    LIMB["lower_arm_" + side] = ("forearm_" + side, "forearm_" + side, "hand_" + side)
    LIMB["upper_leg_" + side] = ("thigh_" + side, "thigh_" + side, "shin_" + side)
    LIMB["lower_leg_" + side] = ("shin_" + side, "shin_" + side, "foot_" + side)
BINS = 16     # colors are told apart on a 16 x 16 x 16 grid
BLACK = 0.02  # a texel darker than this in every channel is one the old bake missed, not a color
RUN = 0.15    # how far from where its mesh lies a garment may run in the old body's own texture, as a share of the height
NEAR = ((1, 0), (-1, 0), (0, 1), (0, -1))


def color_image(material):
    """The picture a material takes its color from, or None."""
    if material is None or not material.node_tree:
        return None
    for node in material.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image and any(link.to_socket.name == "Base Color" for link in node.outputs[0].links):
            return node.image
    return None

def pixels_of(image, held):
    """A picture's dots as one flat row of numbers (r, g, b, a, r, g, ...), read once."""
    if image.name not in held:
        dots = array.array("f", bytes(4 * 4 * image.size[0] * image.size[1]))
        image.pixels.foreach_get(dots)
        held[image.name] = (dots, image.size[0], image.size[1])
    return held[image.name]

def surface(objects, held, tag_of=None):
    """Meshes as one thing to look at: (tree, corners of each triangle, their layout spots, the picture, a tag)."""
    points, tris, spots, pictures, tags, facing = [], [], [], [], [], []
    for obj in objects:
        me = obj.data
        me.calc_loop_triangles()
        start = len(points)
        world = obj.matrix_world
        points += [world @ v.co for v in me.vertices]
        layout = me.uv_layers.active.data if me.uv_layers.active else None
        shown = [pixels_of(color_image(m), held) if color_image(m) else None for m in me.materials] or [None]
        for lt in me.loop_triangles:
            tris.append(tuple(start + i for i in lt.vertices))
            facing.append((world.to_3x3() @ lt.normal).normalized())
            spots.append([layout[l].uv.copy() for l in lt.loops] if layout else None)
            pictures.append(shown[min(lt.material_index, len(shown) - 1)])
            tags.append(tag_of[obj.name] if tag_of else 0)
    return {"tree": BVHTree.FromPolygons(points, tris) if tris else None, "points": points, "tris": tris, "spots": spots, "pictures": pictures, "tags": tags, "facing": facing}

def color_at(seen, index, place):
    """The color a surface shows at a point on one of its triangles, or None where it has no picture."""
    picture, spots = seen["pictures"][index], seen["spots"][index]
    if picture is None or spots is None:
        return None
    a, b, c = [seen["points"][k] for k in seen["tris"][index]]
    v0, v1, v2 = b - a, c - a, place - a
    d00, d01, d11, d20, d21 = v0.dot(v0), v0.dot(v1), v1.dot(v1), v2.dot(v0), v2.dot(v1)
    den = d00 * d11 - d01 * d01
    w1 = (d11 * d20 - d01 * d21) / den if den else 0.0
    w2 = (d00 * d21 - d01 * d20) / den if den else 0.0
    at = spots[0] * (1 - w1 - w2) + spots[1] * w1 + spots[2] * w2
    dots, wide, high = picture
    k = 4 * ((int((at.y % 1.0) * high) % high) * wide + int((at.x % 1.0) * wide) % wide)
    return dots[k], dots[k + 1], dots[k + 2], dots[k + 3]

def look_in(seen, own, p, n, out, deep, tall, near=None):
    """From `out` outside the body at p, straight in: the first of the surface that lies over this very spot of
    the body, not over a neighboring limb's (what it hits must be nearer to here than to anywhere else on the
    body, give or take). With `near`, a hit further off the body than that must also be cloth worn round the
    limb: facing the way the skin does, and there again on the limb's far side. (A flared trouser leg is; a
    flap built sticking out under an arm, or the side of a strap built standing off a shoulder, is not.)
    Returns (triangle, where), or None."""
    start, left = p + n * out, out + deep
    for _ in range(6):
        hit = seen["tree"].ray_cast(start, -n, left)
        if hit[0] is None:
            return None
        q = hit[0]
        if (own.find_nearest(q)[0] - p).length <= 0.6 * (q - p).length + 0.006 * tall:
            if near is None or (q - p).dot(n) <= near or worn_round(seen, own, p, n, hit[2], tall):
                return hit[2], q
        left -= hit[3] + 1e-4
        start = q - n * 1e-4
        if left <= 0:
            return None
    return None

def worn_round(seen, own, p, n, index, tall):
    if abs(seen["facing"][index].dot(n)) < 0.7:
        return False
    through = own.ray_cast(p - n * 1e-3, -n, 0.4 * tall)  # out the far side of the limb
    if through[0] is None:
        return False
    return seen["tree"].ray_cast(through[0] + n * (0.01 * tall), -n, 0.08 * tall)[0] is not None

def bin_of(r, g, b):
    top = BINS - 1e-3
    return (int(min(max(r, 0.0), 1.0) * top) * BINS + int(min(max(g, 0.0), 1.0) * top)) * BINS + int(min(max(b, 0.0), 1.0) * top)

def blurred(counts):
    """A color count spread a little to the colors next to it, so two shades of one skin are one skin."""
    out = [0.0] * len(counts)
    for k, n in enumerate(counts):
        if not n:
            continue
        r, g, b = k // (BINS * BINS), (k // BINS) % BINS, k % BINS
        for dr in (-1, 0, 1):
            for dg in (-1, 0, 1):
                for db in (-1, 0, 1):
                    if 0 <= r + dr < BINS and 0 <= g + dg < BINS and 0 <= b + db < BINS:
                        out[((r + dr) * BINS + g + dg) * BINS + b + db] += n * (0.4 if (dr, dg, db) == (0, 0, 0) else 0.6 / 26)
    total = sum(out) or 1.0
    return [v / total for v in out]

def color_verdicts(cloth_shares, skin_share, other_share):
    """What each color is when it shows in a painted garment's texture. A block-out garment is cut rougher than
    the real one, so its texture shows more than its own cloth: this body's skin round its edges, the garment
    worn under it (a singlet's legs built too long show the tights), other gear (tights built down into the
    boots show the boot tops). A color goes to whichever it is most typical of: one of the painted garments'
    textures, this body's bare skin, or the gear that is not painted (which has to be twice as likely, and
    only counts near that gear).
    Returns two tables, near other gear and away from it: color -> 1, 2, ... a garment's cloth, -1 skin, 0 other gear."""
    near, away = {}, {}
    for k in range(len(skin_share)):
        best, which = 0.0, 0
        for number, share in enumerate(cloth_shares, 1):
            if share is not None and share[k] > best:
                best, which = share[k], number
        if not which:
            continue
        other = 0.5 * other_share[k] if other_share else 0.0
        away[k] = which if best >= skin_share[k] else -1
        near[k] = away[k] if max(best, skin_share[k]) >= other else 0
    return near, away

def kind_of(k, skin_share, cloth_shares, other_share):
    """What a color in the old body's texture is: -1 this body's skin, 1, 2, ... a garment's cloth (the one it
    is likeliest to be), 0 neither (other gear's color, or nobody's)."""
    least = 1.0 / len(skin_share)
    best, which = 0.0, 0
    for number, share in enumerate(cloth_shares, 1):
        if share is not None and share[k] > best:
            best, which = share[k], number
    other = other_share[k] if other_share else 0.0
    if max(skin_share[k], best) < least or other > max(skin_share[k], best):
        return 0
    return -1 if skin_share[k] >= best else which

def grown(mask, domain, steps, size):
    """A set of texels grown by `steps` texels inside the domain (round, near enough: straight and slanted steps take turns)."""
    out = set(mask)
    edge = [i for i in mask if any_outside(i, out, domain, size)]
    for step in range(steps):
        ways = NEAR if step % 2 == 0 else NEAR + ((1, 1), (1, -1), (-1, 1), (-1, -1))
        fresh = []
        for i in edge:
            x, y = i % size, i // size
            for dx, dy in ways:
                if 0 <= x + dx < size and 0 <= y + dy < size:
                    j = i + dx + dy * size
                    if domain[j] and j not in out:
                        out.add(j)
                        fresh.append(j)
        edge = fresh
    return out

def any_outside(i, mask, domain, size):
    x, y = i % size, i // size
    for dx, dy in NEAR:
        if 0 <= x + dx < size and 0 <= y + dy < size:
            j = i + dx + dy * size
            if domain[j] and j not in mask:
                return True
    return False

def any_outside_both(piece, mask, domain, size):
    """Does a patch of texels beside a set touch anything but the set and itself: the texture's island edge, or more of the outside?"""
    own = set(piece)
    for k in piece:
        x, y = k % size, k // size
        for dx, dy in NEAR:
            if not (0 <= x + dx < size and 0 <= y + dy < size):
                return True
            j = k + dx + dy * size
            if not domain[j] or (j not in mask and j not in own):
                return True
    return False

def shrunk(mask, domain, steps, size):
    """The set with `steps` texels taken off its edge. The edge of the texture's own islands is not an edge of the set."""
    rest = {i for i in grown_from_outside(mask, domain, size)}
    edge = list(rest)
    gone = set(rest)
    for step in range(steps):
        ways = NEAR if step % 2 == 0 else NEAR + ((1, 1), (1, -1), (-1, 1), (-1, -1))
        fresh = []
        for i in edge:
            x, y = i % size, i // size
            for dx, dy in ways:
                if 0 <= x + dx < size and 0 <= y + dy < size:
                    j = i + dx + dy * size
                    if j in mask and j not in gone:
                        gone.add(j)
                        fresh.append(j)
        edge = fresh
    return {i for i in mask if i not in gone}

def grown_from_outside(mask, domain, size):
    """The texels just outside the set, inside the domain."""
    out = set()
    for i in mask:
        x, y = i % size, i // size
        for dx, dy in NEAR:
            if 0 <= x + dx < size and 0 <= y + dy < size:
                j = i + dx + dy * size
                if domain[j] and j not in mask:
                    out.add(j)
    return out

def pieces_of(mask, size):
    """A set of texels as its connected pieces."""
    seen, out = set(), []
    for i in mask:
        if i in seen:
            continue
        piece, stack = [], [i]
        seen.add(i)
        while stack:
            k = stack.pop()
            piece.append(k)
            x, y = k % size, k // size
            for dx, dy in NEAR:
                if 0 <= x + dx < size and 0 <= y + dy < size:
                    j = k + dx + dy * size
                    if j in mask and j not in seen:
                        seen.add(j)
                        stack.append(j)
        out.append(piece)
    return out

def touches_island_edge(piece, domain, size):
    for k in piece:
        x, y = k % size, k // size
        for dx, dy in NEAR:
            if not (0 <= x + dx < size and 0 <= y + dy < size) or not domain[k + dx + dy * size]:
                return True
    return False

def spread(colors, known, domain, size, steps, toward=None, fade=0):
    """Color carried out from the texels that have it to those that do not, a texel a step, each new one the
    average of its neighbors that already have it. With `toward`, the color fades to it over `fade` steps.
    `known` (a bytearray) is updated. Texels never reached are left as they were."""
    edge = [i for i in range(size * size) if known[i] and domain[i]]
    far = {}
    for step in range(steps):
        fresh = {}
        for i in edge:
            x, y = i % size, i // size
            for dx, dy in NEAR:
                if 0 <= x + dx < size and 0 <= y + dy < size:
                    j = i + dx + dy * size
                    if domain[j] and not known[j]:
                        got = fresh.get(j)
                        if got is None:
                            fresh[j] = [colors[3 * i], colors[3 * i + 1], colors[3 * i + 2], 1]
                        else:
                            got[0] += colors[3 * i]
                            got[1] += colors[3 * i + 1]
                            got[2] += colors[3 * i + 2]
                            got[3] += 1
        if not fresh:
            break
        mix = min(1.0, 1.0 / max(fade - step, 1)) if toward else 0.0
        for j, got in fresh.items():
            for c in range(3):
                value = got[c] / got[3]
                colors[3 * j + c] = value + (toward[c] - value) * mix if toward else value
            known[j] = 1
            far[j] = step + 1
        edge = list(fresh)
    return far

def new_image(name, size, dots):
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    image = bpy.data.images.new(name, size, size, alpha=True)
    image.pixels.foreach_set(dots)
    image.pack()
    return image

def write_png(image, path):
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()

def gear_name(obj):
    return obj.get("gear") or obj.name


scene = bpy.context.scene
bodies = [o for o in scene.objects if o.type == "MESH" and o.get("template") and (PARAMS["body"] is None or o.name == PARAMS["body"])]
if not bodies:
    raise ValueError("no template body here: run wrap.py first")
body = bodies[0]
mesh = body.data
slots = [k for k, m in enumerate(mesh.materials) if m is not None and m.get("template")]
if not slots:
    raise ValueError("%r has no material marked \"template\": it is not a wrapped template body" % body.name)
skin_material = mesh.materials[slots[0]]
region_of_face = mesh.attributes.get("region")
fit = json.loads(body.get("template_fit", "{}"))
joints = {k: Vector(v) for k, v in fit.get("joints", {}).items()}
base = [o for o in scene.objects if o.type == "MESH" and o.get("wardrobe") == "base"]
gear = [o for o in scene.objects if o.type == "MESH" and o.get("forge") == "gear"]
by_name = {}
for o in gear:
    by_name.setdefault(gear_name(o), []).append(o)
missing = [g for g in list(PARAMS["garments"]) + list(PARAMS["take_off"]) if g not in by_name]
if missing:
    raise ValueError("no gear called %s here (there is: %s)" % (", ".join(missing), ", ".join(sorted(by_name)) or "none"))
garments = [g for g in PARAMS["garments"]]
worn = [w for w in PARAMS["wear"]]
if len(garments) + len(worn) > 250:
    raise ValueError("too many garments at once")
size = int(PARAMS["texture_size"])
count = size * size

# ---- what there is to look at ----
held = {}
own_points = [body.matrix_world @ v.co for v in mesh.vertices]
mesh.calc_loop_triangles()
mine = [lt for lt in mesh.loop_triangles if lt.material_index in slots]
own = BVHTree.FromPolygons(own_points, [tuple(lt.vertices) for lt in mine])
tall = fit.get("height") or (max(p.z for p in own_points) - min(p.z for p in own_points)) / 0.86
old_skin = surface(base, held) if base else None
tag_of = {o.name: 1 + garments.index(gear_name(o)) for o in gear if gear_name(o) in garments}
cloth = surface([o for o in gear if gear_name(o) in garments], held, tag_of) if garments else None
other_gear = surface([o for o in gear if gear_name(o) not in garments], held)
normals = [(body.matrix_world.to_3x3() @ v.normal).normalized() for v in mesh.vertices]
layout = mesh.uv_layers.active.data
regions = [0] * len(mesh.polygons)
if region_of_face is not None:
    region_of_face.data.foreach_get("value", regions)
limb_of = {}
for index, name in enumerate(REGIONS):
    if name in LIMB and LIMB[name][1] in joints and LIMB[name][2] in joints:
        a, b = joints[LIMB[name][1]], joints[LIMB[name][2]]
        limb_of[index] = (LIMB[name][0], a, (b - a) / max((b - a).length_squared, 1e-12))

# ---- texel by texel: what the old body shows there, what gear was over it, what the garments show there ----
inside = bytearray(count)        # 1 where the template's layout uses the texel
skin = array.array("f", bytes(4 * 3 * count))   # the old body's color
has_skin = bytearray(count)
under_gear = bytearray(count)    # gear that is not being painted was over this spot
near_cloth = bytearray(count)    # a garment being painted has its mesh over this spot, however far off
paint = array.array("f", bytes(4 * 3 * count))  # the color of the garment lying on this spot
has_paint = bytearray(count)
lies = bytearray(count)          # which garment's mesh lies on this spot: 1, 2, ... in the order given; 0 = none
part = bytearray(count)          # which region of the body + 1
along = array.array("f", bytes(4 * count))      # how far along its limb's bone the texel is
place = array.array("f", bytes(4 * 3 * count))  # where on the body the texel is
gear_counts = [0] * (BINS ** 3)  # the colors of the gear that is not being painted, where it lies over the body
reach = PARAMS["reach"] * tall
for lt in mine:
    uv = [layout[l].uv for l in lt.loops]
    ax, ay, bx, by, cx, cy = uv[0].x * size, uv[0].y * size, uv[1].x * size, uv[1].y * size, uv[2].x * size, uv[2].y * size
    den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if abs(den) < 1e-12:
        continue
    x0, x1 = max(int(math.floor(min(ax, bx, cx))), 0), min(int(math.ceil(max(ax, bx, cx))), size - 1)
    y0, y1 = max(int(math.floor(min(ay, by, cy))), 0), min(int(math.ceil(max(ay, by, cy))), size - 1)
    pa, pb, pc = [own_points[k] for k in lt.vertices]
    na, nb, nc = [normals[k] for k in lt.vertices]
    region = regions[lt.polygon_index]
    limb = limb_of.get(region)
    for y in range(y0, y1 + 1):
        gy = y + 0.5
        for x in range(x0, x1 + 1):
            i = y * size + x
            if inside[i]:
                continue
            gx = x + 0.5
            w0 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / den
            w1 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / den
            w2 = 1.0 - w0 - w1
            if w0 < -0.02 or w1 < -0.02 or w2 < -0.02:
                continue
            inside[i] = 1
            part[i] = region + 1
            p = pa * w0 + pb * w1 + pc * w2
            n = (na * w0 + nb * w1 + nc * w2).normalized()
            place[3 * i], place[3 * i + 1], place[3 * i + 2] = p
            if limb:
                along[i] = (p - limb[1]).dot(limb[2])
            if old_skin and old_skin["tree"]:
                hit = look_in(old_skin, own, p, n, 0.02 * tall, 0.03 * tall, tall)
                seen = color_at(old_skin, hit[0], hit[1]) if hit else None
                if seen and max(seen[0], seen[1], seen[2]) >= BLACK:
                    skin[3 * i], skin[3 * i + 1], skin[3 * i + 2] = seen[0], seen[1], seen[2]
                    has_skin[i] = 1
            if other_gear["tree"]:
                hit = other_gear["tree"].ray_cast(p - n * (0.01 * tall), n, 0.06 * tall)
                if hit[0] is not None:
                    under_gear[i] = 1
                    seen = color_at(other_gear, hit[2], hit[0])
                    if seen and max(seen[0], seen[1], seen[2]) >= BLACK:
                        gear_counts[bin_of(seen[0], seen[1], seen[2])] += 1
            if cloth and cloth["tree"]:
                if cloth["tree"].ray_cast(p - n * (0.01 * tall), n, 0.08 * tall)[0] is not None:
                    near_cloth[i] = 1
                hit = look_in(cloth, own, p, n, 0.07 * tall, 0.02 * tall, tall, reach)
                if hit:
                    lies[i] = cloth["tags"][hit[0]]
                    seen = color_at(cloth, hit[0], hit[1])
                    if seen and max(seen[0], seen[1], seen[2]) >= BLACK:
                        paint[3 * i], paint[3 * i + 1], paint[3 * i + 2] = seen[0], seen[1], seen[2]
                        has_paint[i] = 1
used = [i for i in range(count) if inside[i]]
if not used:
    raise ValueError("the template's faces have no texture layout")
texel = math.sqrt(sum(p.area for p in mesh.polygons if p.material_index in slots) / len(used))  # meters a texel, about
steps = max(1, int(round(PARAMS["smooth"] * tall / texel)))
speck = int((0.012 * tall / texel) ** 2)  # a loose piece smaller than about 2 cm across is a speck
near_hard = {i for i in used if under_gear[i]}
if PARAMS["margin"] > 0:
    near_hard = grown(near_hard, inside, max(1, int(round(PARAMS["margin"] * tall / texel))), size)

# ---- this body's skin colors: what the old body shows well away from any gear ----
any_gear = {i for i in used if under_gear[i] or near_cloth[i] or lies[i]}
away = grown(any_gear, inside, int(round(0.04 * tall / texel)), size)
skin_counts = [0] * (BINS ** 3)
total, bare = [0.0, 0.0, 0.0], 0
for trial in (away, any_gear, set()):
    for i in used:
        if has_skin[i] and i not in trial:
            skin_counts[bin_of(skin[3 * i], skin[3 * i + 1], skin[3 * i + 2])] += 1
            bare += 1
            for c in range(3):
                total[c] += skin[3 * i + c]
    if bare >= 0.01 * len(used):  # enough bare skin to go by; else nearer the gear, else (dressed head to toe) anything the old body shows
        break
    skin_counts, total, bare = [0] * (BINS ** 3), [0.0, 0.0, 0.0], 0
skin_mean = [v / bare for v in total] if bare else [0.6, 0.45, 0.4]
skin_share = blurred(skin_counts)

# ---- each garment: which texels are really its cloth ----
report, masks = {}, {name: set() for name in garments}
colored = bytearray(count)   # the texel has a cloth color of its own (the rest of a garment is filled in from these)
shows_skin = set()           # a garment's mesh lies here but its texture shows this body's skin: real skin, the wearer's own
skin_ok = bytearray(count)   # the old body shows skin here, by its color
if not PARAMS["trim"]:  # as the meshes have it: whatever a garment's mesh shows where it lies is the garment
    for i in used:
        skin_ok[i] = has_skin[i]
        if lies[i] and has_paint[i]:
            masks[garments[lies[i] - 1]].add(i)
            colored[i] = 1
    for name in garments:
        report[name] = {"texels": len(masks[name]), "trimmed": False, "texels_kept": len(masks[name])}
else:
    kinds, counts_of = {}, []
    for number, name in enumerate(garments, 1):
        counts = [0] * (BINS ** 3)
        for i in used:
            if lies[i] == number and has_paint[i]:
                counts[bin_of(paint[3 * i], paint[3 * i + 1], paint[3 * i + 2])] += 1
        counts_of.append(counts)
    gear_share = blurred(gear_counts) if sum(gear_counts) else None
    cloth_shares = [blurred(counts) if sum(counts) else None for counts in counts_of]  # the share of each garment's texture each color has
    verdicts = color_verdicts(cloth_shares, skin_share, gear_share)
    for name in garments:
        report[name] = {"trimmed": True}
    by_gear = grown({i for i in used if under_gear[i]}, inside, int(round(0.04 * tall / texel)), size)  # another piece of gear can only show in a garment's texture near where that gear is
    shows_gear = {name: 0 for name in garments}
    shows_other = {name: 0 for name in garments}
    # 1. where a garment's mesh lies and its own texture shows cloth
    from_mesh = {name: set() for name in garments}
    for i in used:
        if lies[i] and has_paint[i]:
            what = verdicts[0 if i in by_gear else 1][bin_of(paint[3 * i], paint[3 * i + 1], paint[3 * i + 2])]  # whose cloth, this body's skin, or other gear?
            if what == 0:
                shows_gear[garments[lies[i] - 1]] += 1
            elif what == -1:
                shows_skin.add(i)
            else:  # cloth: this garment's own, or the one worn under it showing where this one was built too long
                from_mesh[garments[what - 1]].add(i)
                colored[i] = 1
                if what != lies[i]:
                    shows_other[garments[lies[i] - 1]] += 1
    # 2. where the old body's own texture shows the garment (the real strap, drawn on the chest), near where the mesh lies
    from_body = {name: set() for name in garments}
    taken = set()
    for name in garments:
        taken |= from_mesh[name]
    for i in used:
        if has_skin[i] and i not in taken and i not in shows_skin:
            k = bin_of(skin[3 * i], skin[3 * i + 1], skin[3 * i + 2])
            if k not in kinds:
                kinds[k] = kind_of(k, skin_share, cloth_shares, gear_share)
            if kinds[k] > 0:
                from_body[garments[kinds[k] - 1]].add(i)
            elif kinds[k] == -1:
                skin_ok[i] = 1
    run = int(round(RUN * tall / texel))
    for name in garments:
        from_body[name] &= grown(from_mesh[name], inside, run, size) if from_mesh[name] else set()
        for i in from_body[name]:
            paint[3 * i], paint[3 * i + 1], paint[3 * i + 2] = skin[3 * i], skin[3 * i + 1], skin[3 * i + 2]
            colored[i] = 1
        masks[name] = from_mesh[name] | from_body[name]
    # 3. texels that show neither (a patch the old bake missed is plain black; a blend at an edge): each patch
    #    of them goes to the garment that mostly surrounds it, or stays with the skin
    taken = set(shows_skin)
    for name in garments:
        taken |= masks[name]
    blank = {i for i in used if i not in taken and not skin_ok[i]}
    holes = {name: 0 for name in garments}
    for piece in pieces_of(blank, size):
        if len(piece) > 40 * speck:
            continue
        around, rim = {}, 0
        for k in piece:
            x, y = k % size, k // size
            for dx, dy in NEAR:
                if 0 <= x + dx < size and 0 <= y + dy < size:
                    j = k + dx + dy * size
                    if inside[j] and j not in blank:
                        rim += 1
                        for name in garments:
                            if j in masks[name]:
                                around[name] = around.get(name, 0) + 1
        for name, n in around.items():
            if n > 0.5 * rim:
                masks[name].update(piece)
                holes[name] += len(piece)
    # 4. only what hangs together with where the mesh lies is the garment; then the edge is evened out
    for number, name in enumerate(garments, 1):
        mask = masks[name]
        note = report[name]
        note.update({"texels_where_its_mesh_lies": sum(1 for i in used if lies[i] == number), "cloth_in_the_garments'_textures": len(from_mesh[name]),
                     "skin_in_its_texture": sum(1 for i in shows_skin if lies[i] == number), "other_gear_in_its_texture": shows_gear[name], "another_painted_garment_in_its_texture": shows_other[name],
                     "no_color_in_its_texture": sum(1 for i in used if lies[i] == number and not has_paint[i]),
                     "cloth_in_the_body's_texture": len(from_body[name]), "patches_of_no_color_filled": holes[name]})
        if note["skin_in_its_texture"] > 0.6 * max(note["texels_where_its_mesh_lies"], 1):
            note["warning"] = "most of this garment's texture is the color of the skin: color cannot tell them apart, check the picture"
        loose = 0
        for piece in pieces_of(mask, size):
            if not any(k in from_mesh[name] for k in piece) and not touches_island_edge(piece, inside, size):
                mask.difference_update(piece)
                loose += len(piece)
        before = set(mask)
        mask = grown(shrunk(mask, inside, steps, size), inside, steps, size) & before         # slivers and spikes go
        opened = len(before) - len(mask)
        others = set()
        for other in garments:
            if other != name:
                others |= masks[other]
        closed = shrunk(grown(mask, inside, steps, size), inside, steps, size)                # notches and pinholes fill,
        mask.update(i for i in closed if i not in others)                                     # but never over another garment
        # a scrap on its own, small beside the garment (what is left of a flap built sticking out under an arm).
        # In the texture a strap that carries on across a seam of the layout looks like a scrap too: on the body
        # it is right next to the rest, and stays.
        dropped = 0
        parts = sorted(pieces_of(mask, size), key=len, reverse=True)
        small = [piece for piece in parts if len(piece) < max(speck, 0.03 * len(mask))]
        if small and len(small) < len(parts):
            large = [k for piece in parts if len(piece) >= max(speck, 0.03 * len(mask)) for k in piece[::7]]
            rest = KDTree(len(large))
            for k in large:
                rest.insert((place[3 * k], place[3 * k + 1], place[3 * k + 2]), k)
            rest.balance()
            for piece in small:
                if not any(rest.find((place[3 * k], place[3 * k + 1], place[3 * k + 2]))[2] < 0.012 * tall for k in piece[::5]):
                    mask.difference_update(piece)
                    dropped += len(piece)
        holes_shut = 0
        for piece in pieces_of({i for i in grown(mask, inside, 12 * steps, size) if i not in mask}, size):  # a small window of skin with cloth all round it: cloth has no such holes
            if len(piece) < 12 * speck and not any(k in others for k in piece) and not any_outside_both(piece, mask, inside, size):
                mask.update(piece)
                holes_shut += len(piece)
        note["edge"] = {"loose_from_the_garment": loose, "taken_off_as_slivers": opened, "filled_in": len(mask - before) - holes_shut, "dropped_as_scraps": dropped,
                        "small_holes_shut": holes_shut, "narrowest_kept_cm": round(100 * 2 * steps * texel, 1)}
        note["texels"] = len(before) + loose
        masks[name] = mask
    # a thin line of skin left between two garments where they meet (each had its own edge evened out) is cloth:
    # every texel of it goes to the garment next to it
    cloth_all = set()
    for name in garments:
        cloth_all |= masks[name]
    for piece in pieces_of({i for i in grown(cloth_all, inside, 12 * steps, size) if i not in cloth_all}, size):
        if len(piece) < 12 * speck and not any_outside_both(piece, cloth_all, inside, size):
            left = set(piece)
            while left:
                took = {}
                for k in left:
                    x, y = k % size, k // size
                    for dx, dy in NEAR:
                        if 0 <= x + dx < size and 0 <= y + dy < size:
                            for name in garments:
                                if k + dx + dy * size in masks[name]:
                                    took[k] = name
                if not took:
                    break
                for k, name in took.items():
                    masks[name].add(k)
                    report[name]["edge"]["filled_in"] += 1
                left -= set(took)
    for name in garments:
        report[name]["texels_kept"] = len(masks[name])
wears = bytearray(count)  # which garment is painted here: 1, 2, ... in the order given; 0 = none
for number, name in enumerate(garments, 1):
    for i in masks[name]:
        wears[i] = number

# ---- the skin layer: skin that can be trusted, and the rest filled in from it ----
# Trusted: the old body's own color where it is skin by its color and no gear that stays (or is taken off
# unpainted) was over it or close by; and skin seen through a painted garment's own texture.
trusted = bytearray(count)
seen_through = 0
doubtful = set(near_hard)
if PARAMS["trim"]:  # and not right at a cloth edge or a patch of no color, where the old bake blended the two
    edges = {i for i in used if wears[i] or (not skin_ok[i] and i not in shows_skin and not lies[i])}
    doubtful |= grown(edges, inside, 3, size)
for i in used:
    if wears[i] or i in doubtful:
        continue
    if i in shows_skin:
        skin[3 * i], skin[3 * i + 1], skin[3 * i + 2] = paint[3 * i], paint[3 * i + 1], paint[3 * i + 2]
        trusted[i] = 1
        seen_through += 1
    elif skin_ok[i] and not lies[i]:
        trusted[i] = 1
for i in used:
    if not wears[i]:
        colored[i] = 0
spread(paint, colored, inside, size, 4 * steps + 8)  # a texel a garment gained takes the cloth's color from next to it; and a little past its edge, for the soft edge
copied = sum(trusted) - seen_through
known = bytearray(trusted)
fade = max(2, int(round(0.03 * tall / texel)))
reached = spread(skin, known, inside, size, 4 * size, skin_mean, fade)
unreached = 0
for i in used:
    if not known[i]:  # an island with no trusted skin on it at all (a foot inside a boot)
        skin[3 * i], skin[3 * i + 1], skin[3 * i + 2] = skin_mean
        known[i] = 1
        unreached += 1
soften = [i for i, far in reached.items() if far <= 2 * fade]
for _ in range(4):  # the filled-in skin next to real skin, evened out: filling a texel a step leaves streaks
    fresh = []
    for i in soften:
        x, y = i % size, i // size
        r = g = b = n = 0
        for dx, dy in NEAR:
            if 0 <= x + dx < size and 0 <= y + dy < size and inside[i + dx + dy * size]:
                j = 3 * (i + dx + dy * size)
                r, g, b, n = r + skin[j], g + skin[j + 1], b + skin[j + 2], n + 1
        fresh.append((r / n, g / n, b / n) if n else (skin[3 * i], skin[3 * i + 1], skin[3 * i + 2]))
    for i, value in zip(soften, fresh):
        skin[3 * i], skin[3 * i + 1], skin[3 * i + 2] = value

# ---- outfits painted for another body, laid over this skin ----
layers = []   # (name, color row, how much of the texel it covers 0..1, texels) in the order they go on
for number, name in enumerate(garments, 1):
    cover = array.array("f", bytes(4 * count))
    for i in masks[name]:
        cover[i] = 1.0
    layers.append((name, paint, cover, masks[name]))
for entry in worn:
    image = bpy.data.images.load(entry["image"])
    dots, wide, high = pixels_of(image, held)
    color = array.array("f", bytes(4 * 3 * count))
    cover = array.array("f", bytes(4 * count))
    mask = set()
    for i in used:
        x, y = i % size, i // size
        k = 4 * (min(int((y + 0.5) / size * high), high - 1) * wide + min(int((x + 0.5) / size * wide), wide - 1))
        if dots[k + 3] > 0.004:
            color[3 * i], color[3 * i + 1], color[3 * i + 2], cover[i] = dots[k], dots[k + 1], dots[k + 2], dots[k + 3]
            if dots[k + 3] > 0.5:
                mask.add(i)
    layers.append((entry.get("name") or image.name, color, cover, mask))
    report[entry.get("name") or image.name] = {"texels": len(mask), "texels_kept": len(mask), "worn_from": entry["image"]}

# a soft edge, one texel wide, for the garments painted here (a worn outfit brings its own)
for name, color, cover, mask in layers[:len(garments)]:
    rim = grown_from_outside(mask, inside, size) | {i for i in mask if any_outside(i, mask, inside, size)}
    for i in rim:
        x, y = i % size, i // size
        on = seen = 0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if 0 <= x + dx < size and 0 <= y + dy < size and inside[i + dx + dy * size]:
                    seen += 1
                    on += (i + dx + dy * size) in mask
        cover[i] = on / seen if seen else cover[i]

# ---- where each garment ends on each limb ----
for name, color, cover, mask in layers:
    spans, ends = {}, {}
    for i in mask:
        limb = limb_of.get(part[i] - 1)
        if limb:
            spans.setdefault(limb[0], []).append(along[i])
    whole = {}
    for i in used:
        limb = limb_of.get(part[i] - 1)
        if limb:
            whole[limb[0]] = whole.get(limb[0], 0) + 1
    for limb, values in spans.items():
        if len(values) < 0.02 * whole[limb]:
            continue
        values.sort()
        ends[limb] = [round(values[int(0.01 * (len(values) - 1))], 3), round(values[int(0.99 * (len(values) - 1))], 3)]
    report[name]["ends"] = ends
    report[name]["share_of_the_texture"] = round(len(mask) / len(used), 3)

# ---- put it together and bleed past the island edges, so filtering never pulls in background ----
final = array.array("f", skin)
for name, color, cover, mask in layers:
    for i in used:
        a = cover[i]
        if a > 0:
            for c in range(3):
                final[3 * i + c] += (color[3 * i + c] - final[3 * i + c]) * a
everywhere = bytearray(b"\x01") * count
filled = bytearray(inside)
spread(final, filled, everywhere, size, 16)

def as_dots(color, cover):
    """Colors and how much each texel is covered as a picture's row of r, g, b, a."""
    dots = array.array("f", bytes(4 * 4 * count))
    for i in range(count):
        dots[4 * i], dots[4 * i + 1], dots[4 * i + 2] = color[3 * i], color[3 * i + 1], color[3 * i + 2]
        dots[4 * i + 3] = 1.0 if cover is None else cover[i]
    return dots

picture = new_image(body.name + " painted", size, as_dots(final, None))
tree = skin_material.node_tree
shader = [node for node in tree.nodes if node.type == "BSDF_PRINCIPLED"][0]
for node in [node for node in tree.nodes if node.type == "TEX_IMAGE"]:
    tree.nodes.remove(node)
node = tree.nodes.new("ShaderNodeTexImage")
node.image = picture
tree.links.new(node.outputs["Color"], shader.inputs["Base Color"])
shader.inputs["Roughness"].default_value = 0.8
shader.inputs["Metallic"].default_value = 0.0
written = {}
if PARAMS["save"]:
    folder = PARAMS["save"].rstrip("/")
    skin_filled = bytearray(inside)
    bare_skin = array.array("f", skin)
    spread(bare_skin, skin_filled, everywhere, size, 16)
    write_png(new_image(body.name + " skin", size, as_dots(bare_skin, None)), folder + "/skin.png")
    written["skin"] = folder + "/skin.png"
    for name, color, cover, mask in layers[:len(garments)]:
        write_png(new_image(body.name + " " + name, size, as_dots(color, cover)), folder + "/" + name + ".png")
        written[name] = folder + "/" + name + ".png"

# ---- the painted gear and the old body go ----
removed = []
for name in list(garments) + list(PARAMS["take_off"]):
    for o in by_name.get(name, []):
        if PARAMS["keep_base"]:
            o.hide_set(True)
            o.hide_render = True
            continue
        removed.append(o.name)
        spare = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if spare.users == 0:
            bpy.data.meshes.remove(spare)
if not PARAMS["keep_base"]:
    for o in base:
        spare = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if spare.users == 0:
            bpy.data.meshes.remove(spare)
body["painted"] = json.dumps([name for name, color, cover, mask in layers])
kept = sorted({gear_name(o) for o in scene.objects if o.type == "MESH" and o.get("forge") == "gear" and not o.hide_get()})

print("RESULT " + json.dumps({
    "object": body.name, "texture": [size, size], "picture": picture.name, "texels_used": len(used), "texel_mm": round(1000 * texel, 2),
    "painted": [name for name, color, cover, mask in layers], "garments": report, "kept_as_meshes": kept, "removed": removed,
    "skin": {"copied_from_the_old_body": copied, "seen_through_a_garment's_texture": seen_through,
             "filled_in": len(reached) + unreached, "on_islands_with_no_skin_to_go_by": unreached,
             "had_gear_that_stays_over_or_near": len(near_hard), "not_trusted_at_a_cloth_edge": len(doubtful) - len(near_hard), "bare_skin_to_go_by": bare, "average_color": [round(v, 3) for v in skin_mean]},
    "saved": written,
    "triangles": {"body": sum(len(p.vertices) - 2 for p in mesh.polygons),
                  "gear_kept": sum(len(p.vertices) - 2 for o in scene.objects if o.type == "MESH" and o.get("forge") == "gear" and not o.hide_get() for p in o.data.polygons)},
}))
