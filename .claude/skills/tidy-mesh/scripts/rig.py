# Give a low-poly or mid-poly T-pose character a skeleton, bind its meshes to
# it, and set how far each joint may turn.
#
# The character stands as the pipeline builds it: T-pose, z up, feet on z = 0,
# facing -y (so its left side is +x). Every visible mesh in the scene is bound
# (the body and each "gear: ..." mesh follow the same skeleton), and each
# "socket: ..." empty is hung on its bone (hands, head, chest, hips), so a prop
# put there follows.
#
# Where the joints go is read off the model, never typed in per character:
#   - with a block-out recipe ("recipe": build.py's pieces, or the
#     "forge_build" a mesh carries), from the pieces: the arm and leg lofts'
#     own rings say where the elbow, wrist and knee are (rings set close
#     together, or the narrowest ring), the torso's rings say how wide the
#     shoulders are, a tube behind the hips is a tail;
#   - without one, from the mesh: a block-out is separate pieces laid over each
#     other, so each connected piece is found and its points gathered back into
#     rings, then the same reading as above.
# Elbows and knees sit on the straight line from shoulder to wrist and hip to
# ankle, so they bend as true hinges.
#
# Bones (the same names on every character, so one animation fits all):
#   hips > spine > chest > neck > head
#   chest > shoulder_l > upper_arm_l > forearm_l > hand_l   (and _r)
#   hips > thigh_l > shin_l > foot_l > toe_l                 (and _r)
#   hips > tail_1 > tail_2 ...  only when the model has a tail
# bones.json in the skill folder says what each is called in SOMA and Mixamo.
#
# Binding: "weights": "auto" tries Blender's automatic weights first and keeps
# them only if every point got a weight and no limb pulls on the far side's
# bones. Block-outs are overlapping loose pieces, which usually defeats it, so
# the fallback ("pieces") weights each piece by its nearest bones: a small
# piece (a buckle, a tusk, a hand) follows one bone rigidly, a long one blends
# from bone to bone across each joint. "skin" in the result says which was used.
#
# Limits: each bone gets a Limit Rotation constraint (its own axes, XYZ order)
# with human ranges: knees and elbows are one-way hinges; hips, shoulders,
# spine, neck, wrists, ankles and toes have their usual reach. x is the bend
# (forward/back for the spine and legs, up/down for an arm held out), y the
# twist along the bone, z the sideways swing. A bulky build is made stiffer and
# a slim one looser ("flexibility": None works it out; 1.0 is an average
# person). The same numbers ride on each bone as "limit_deg" [x-, x+, y-, y+,
# z-, z+], which the animation tools clamp to.
#
# The result also measures the build (leg and arm length, widths, bulk), which
# walk.py turns into a gait.
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down.
# Prints RESULT {json}. About a second. Safe-mode compatible.

PARAMS = {
    "meshes": None,       # names of the meshes to bind; None = every visible mesh in the scene
    "recipe": None,       # the block-out's pieces (lowpoly_build.json "pieces"); None = the meshes' own "forge_build", else read the mesh
    "name": "rig",        # the armature's name
    "weights": "auto",    # "auto" = Blender's automatic weights if they hold up, else by piece; "pieces" = by piece straight away
    "flexibility": None,  # scales every joint's reach; None = from the build (bulky is stiffer)
    "tail": True,         # give a tail its own bones when the model has one
}

import bpy
import json
import math
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

ACROSS = {"x": (0, 1, 2), "y": (1, 0, 2), "z": (2, 0, 1)}
SOCKET_BONES = {"hand_right": "hand_r", "hand_left": "hand_l", "head": "head", "back": "chest", "hip": "hips"}
# Reach in degrees for a left-side bone: [x-, x+, y-, y+, z-, z+]. A right-side bone mirrors y and z.
LIMITS = {
    "spine": [-15, 30, -20, 20, -15, 15], "chest": [-12, 22, -25, 25, -15, 15],
    "neck": [-30, 35, -45, 45, -25, 25], "head": [-25, 30, -40, 40, -20, 20],
    "shoulder": [-12, 25, -10, 10, -20, 20], "upper_arm": [-100, 85, -90, 90, -130, 45],
    "forearm": [0, 0, -80, 80, -150, 0], "hand": [-80, 70, -10, 10, -25, 25],
    "thigh": [-120, 30, -40, 40, -40, 40], "shin": [0, 150, 0, 0, 0, 0],
    "foot": [-30, 50, -25, 25, -30, 30], "toe": [-70, 35, 0, 0, 0, 0],
    "tail": [-30, 30, -10, 10, -35, 35],
}
UP = {"spine": (0, -1, 0), "arm": (0, 0, 1), "leg": (0, 1, 0), "foot": (0, 0, -1), "tail": (0, 0, 1)}  # where each bone's z axis points


def first(pair):
    return pair[0]

def lerp(a, b, t):
    return a + (b - a) * t

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

def volume_of(points, faces):
    """A closed piece's volume; an open end costs a little accuracy, not much."""
    if not points:
        return 0.0
    mid = sum(points, Vector()) / len(points)
    total = 0.0
    for f in faces:
        a = points[f[0]] - mid
        for k in range(1, len(f) - 1):
            total += a.dot((points[f[k]] - mid).cross(points[f[k + 1]] - mid))
    return abs(total) / 6.0

def islands_of(obj):
    """The connected pieces of a mesh, with texture-seam and flat-shading splits welded by position."""
    me = obj.data
    world = [obj.matrix_world @ v.co for v in me.vertices]
    weld, slot = {}, []
    for p in world:
        key = (round(p.x, 4), round(p.y, 4), round(p.z, 4))
        if key not in weld:
            weld[key] = len(weld)
        slot.append(weld[key])
    root = list(range(len(weld)))
    for poly in me.polygons:
        a = slot[poly.vertices[0]]
        while root[a] != a:
            root[a] = root[root[a]]
            a = root[a]
        for v in poly.vertices[1:]:
            b = slot[v]
            while root[b] != b:
                root[b] = root[root[b]]
                b = root[b]
            if a != b:
                root[b] = a
    found = {}
    for i in range(len(slot)):
        a = slot[i]
        while root[a] != a:
            a = root[a]
        found.setdefault(a, []).append(i)
    faces = {}
    for poly in me.polygons:
        a = slot[poly.vertices[0]]
        while root[a] != a:
            a = root[a]
        faces.setdefault(a, []).append(tuple(poly.vertices))
    out = []
    for key, verts in found.items():
        for part, part_faces in halves(world, verts, faces.get(key, [])):
            pts = [world[i] for i in part]
            lo = Vector([min(p[k] for p in pts) for k in range(3)])
            hi = Vector([max(p[k] for p in pts) for k in range(3)])
            out.append({"obj": obj, "verts": part, "lo": lo, "hi": hi, "gear": obj.get("forge") == "gear",
                        "volume": volume_of(world, part_faces)})
    return out, world

def halves(world, verts, faces):
    """A mirrored pair that only touches along the center line (two thighs meeting) comes apart again:
    no face crosses x = 0, and the points on it make one thin line, not the front and back of one ring."""
    sides = [1 if sum(world[i].x for i in f) > 0 else -1 for f in faces]
    crossing = [f for f in faces if min(world[i].x for i in f) < -1e-4 and max(world[i].x for i in f) > 1e-4]
    on = [world[i] for i in verts if abs(world[i].x) < 1e-4]
    if crossing or not on or 1 not in sides or -1 not in sides:
        return [(verts, faces)]
    thin = 1.0
    for k in (1, 2):
        size = max(world[i][k] for i in verts) - min(world[i][k] for i in verts)
        thin = min(thin, (max(p[k] for p in on) - min(p[k] for p in on)) / max(size, 1e-9))
    if thin > 0.5:
        return [(verts, faces)]
    out = []
    for want in (1, -1):
        mine = [f for f, s in zip(faces, sides) if s == want]
        out.append((sorted({i for f in mine for i in f}), mine))
    return out

def box_size(seg):
    size = seg["hi"] - seg["lo"]
    return size.x * size.y * size.z

def back_end(seg):
    return seg["hi"].y

def side_of(lo, hi):
    wide = hi.x - lo.x
    if lo.x < -0.25 * wide and hi.x > 0.25 * wide:
        return 0
    return 1 if lo.x + hi.x > 0 else -1

def segment(name, axis, rows, lo, hi, gear, kind):
    return {"name": name, "axis": axis, "rows": sorted(rows, key=first), "lo": lo, "hi": hi, "gear": gear, "kind": kind, "side": side_of(lo, hi)}

def island_segment(piece, world, tall):
    """A mesh piece as a stack of rings along its longest side: its points gathered by where they sit along it."""
    size = piece["hi"] - piece["lo"]
    axis = 0 if size.x >= size.y and size.x >= size.z else (1 if size.y >= size.z else 2)
    pts = sorted([world[i] for i in piece["verts"]], key=[at_x, at_y, at_z][axis])
    rows, group = [], [pts[0]]
    for p in pts[1:] + [None]:
        if p is not None and p[axis] - group[-1][axis] < 0.004 * tall:
            group.append(p)
            continue
        low = Vector([min(q[k] for q in group) for k in range(3)])
        high = Vector([max(q[k] for q in group) for k in range(3)])
        rows.append([(low[axis] + high[axis]) / 2, (low + high) / 2, (high - low) / 2])
        group = [p]
    return segment("", axis, rows, piece["lo"], piece["hi"], piece["gear"], "loft")

def at_x(p):
    return p.x

def at_y(p):
    return p.y

def at_z(p):
    return p.z

def recipe_segments(pieces):
    """build.py's pieces as the same stacks of rings, read straight from the recipe."""
    out = []
    for part in pieces:
        gear, name, flips = bool(part.get("gear")), part.get("name", ""), [1.0]
        rows, axis, kind = [], None, "blob"
        if "loft" in part:
            axis, u, v = ACROSS[part["loft"]]
            kind = "band" if part.get("closed") else "loft"
            for row in part["rings"]:
                n = [x for x in row if not isinstance(x, dict)]
                more = row[-1] if isinstance(row[-1], dict) else {}
                rv = n[4] if len(n) > 4 else n[3]
                back = more.get("back", rv)
                mid, half = Vector((0, 0, 0)), Vector((0, 0, 0))
                mid[axis], mid[u], mid[v] = n[0], n[1], n[2] + (back - rv) / 2
                half[u], half[v] = n[3], (rv + back) / 2
                rows.append([n[0], mid, half])
        elif "tube" in part:
            kind = "tube"
            pts = [[x for x in row if not isinstance(x, dict)] for row in part["tube"]]
            span = [abs(pts[-1][k] - pts[0][k]) for k in range(3)]
            axis = span.index(max(span))
            for n in pts:
                r = max(n[3], n[4] if len(n) > 4 else n[3])
                half = Vector((r, r, r))
                half[axis] = 0
                rows.append([n[axis], Vector(n[:3]), half])
        elif "lumps" in part:
            lows = [Vector(r[:3]) - Vector(r[3:6] if len(r) > 5 else [r[3]] * 3) for r in part["lumps"]]
            highs = [Vector(r[:3]) + Vector(r[3:6] if len(r) > 5 else [r[3]] * 3) for r in part["lumps"]]
            lo = Vector([min(p[k] for p in lows) for k in range(3)])
            hi = Vector([max(p[k] for p in highs) for k in range(3)])
        elif "box" in part:
            lo, hi = Vector(part["box"]["min"]), Vector(part["box"]["max"])
            kind = "head" if "head" in part else "blob"
        else:
            continue
        if rows:
            lo = Vector([min(r[1][k] - r[2][k] for r in rows) for k in range(3)])
            hi = Vector([max(r[1][k] + r[2][k] for r in rows) for k in range(3)])
        if "head" in name.lower() and kind != "head" and not gear:
            kind = "head"
        if part.get("mirror") and "head" not in part:
            flips = [1.0, -1.0]
        for flip in flips:
            turn = Vector((flip, 1, 1))
            a, b = lo * turn, hi * turn
            out.append(segment(name, axis, [[r[0] * (flip if axis == 0 else 1), r[1] * turn, r[2]] for r in rows],
                               Vector((min(a.x, b.x), a.y, a.z)), Vector((max(a.x, b.x), b.y, b.z)), gear, kind))
    return out

def at_row(seg, pos):
    """A segment's middle and half-size where its axis reads `pos`, or None outside it."""
    rows = seg["rows"]
    if not rows or pos < rows[0][0] - 1e-6 or pos > rows[-1][0] + 1e-6:
        return None
    for a, b in zip(rows, rows[1:]):
        if pos <= b[0]:
            t = 0.0 if b[0] - a[0] < 1e-9 else clamp((pos - a[0]) / (b[0] - a[0]), 0.0, 1.0)
            return a[1].lerp(b[1], t), a[2].lerp(b[2], t)
    return rows[-1][1], rows[-1][2]

def envelope(segs, axis, pos):
    """The box around every listed segment where the axis reads `pos`: (middle, half-size), or None."""
    lo = hi = None
    for seg in segs:
        if seg["axis"] == axis:
            hit = at_row(seg, pos)
            if hit is None:
                continue
            a, b = hit[0] - hit[1], hit[0] + hit[1]
        elif seg["lo"][axis] <= pos <= seg["hi"][axis]:
            a, b = seg["lo"], seg["hi"]
        else:
            continue
        lo = a.copy() if lo is None else Vector([min(lo[k], a[k]) for k in range(3)])
        hi = b.copy() if hi is None else Vector([max(hi[k], b[k]) for k in range(3)])
    if lo is None:
        return None
    mid, half = (lo + hi) / 2, (hi - lo) / 2
    mid[axis], half[axis] = pos, 0.0
    return mid, half

def rings_of(segs, axis, flip):
    """[position along the limb, cross-section area] for every ring of the segments, nearest the body first."""
    out, groups = [], []
    for seg in segs:
        if seg["axis"] != axis or seg["kind"] == "band":
            continue
        mine = []
        for pos, mid, half in seg["rows"]:
            sizes = [half[k] for k in range(3) if k != axis]
            mine.append([pos * flip, sizes[0] * sizes[1]])
        mine.sort(key=first)
        out += mine
        gaps = sorted(b[0] - a[0] for a, b in zip(mine, mine[1:]))
        if len(gaps) >= 3:  # rings set closer than this piece's usual spacing mark a joint
            group = [mine[0][0]]
            for a, b in zip(mine, mine[1:]):
                if b[0] - a[0] < 0.75 * gaps[len(gaps) // 2]:
                    group.append(b[0])
                else:
                    if len(group) > 1:
                        groups.append((group[0] + group[-1]) / 2)
                    group = [b[0]]
            if len(group) > 1:
                groups.append((group[0] + group[-1]) / 2)
    out.sort(key=first)
    merged = []
    for ring in out:
        if merged and ring[0] - merged[-1][0] < 1e-4:
            merged[-1][1] = max(merged[-1][1], ring[1])
        else:
            merged.append(ring)
    return merged, groups

def find_joint(found, lo, hi, prior, order):
    """Where a limb bends between `lo` and `hi`: rings set close together, the narrowest ring, or the
    ring nearest where the joint usually is; failing all, where it usually is. Returns (position, how)."""
    rings, groups = found
    inside = [i for i, r in enumerate(rings) if lo <= r[0] <= hi]
    for how in order:
        best = None
        if how == "close rings":
            for spot in groups:
                if lo <= spot <= hi and (best is None or abs(spot - prior) < abs(best - prior)):
                    best = spot
        elif how == "narrowest ring":
            for i in inside:
                if 0 < i < len(rings) - 1 and rings[i][1] < 0.93 * rings[i - 1][1] and rings[i][1] < 0.93 * rings[i + 1][1]:
                    if best is None or abs(rings[i][0] - prior) < abs(best - prior):
                        best = rings[i][0]
        elif how == "nearest ring":
            for i in inside:
                if best is None or abs(rings[i][0] - prior) < abs(best - prior):
                    best = rings[i][0]
        if best is not None:
            return best, how
    return prior, "usual proportion"

def nearest_on(a, b, p):
    """How far `p` is from the bone a-b."""
    ab = b - a
    t = clamp((p - a).dot(ab) / max(ab.length_squared, 1e-12), 0.0, 1.0)
    return (p - (a + ab * t)).length

def chain_of(name):
    if name.startswith("tail"):
        return "tail"
    for key, chain in (("arm", "arm"), ("hand", "arm"), ("shoulder", "arm"), ("thigh", "leg"), ("shin", "leg"), ("foot", "leg"), ("toe", "leg")):
        if key in name:
            return chain + name[-2:]
    return "trunk"

def limit_of(name, flex):
    """A bone's reach, mirrored for the right side and scaled by how flexible the build is."""
    base = name[:-2] if name.endswith(("_l", "_r")) else ("tail" if name.startswith("tail") else name)
    if base not in LIMITS:
        return None
    lim = [clamp(v * flex, -175.0, 175.0) for v in LIMITS[base]]
    if base in ("shin", "forearm"):  # a hinge keeps its full fold
        lim = [float(v) for v in LIMITS[base]]
    if name.endswith("_r"):
        lim = lim[:2] + [-lim[3], -lim[2], -lim[5], -lim[4]]
    return [round(v, 1) for v in lim]


scene = bpy.context.scene
if PARAMS["meshes"]:
    meshes = [bpy.data.objects[n] for n in PARAMS["meshes"]]
else:
    meshes = [o for o in scene.objects if o.type == "MESH" and o.visible_get() and not o.name.startswith("lines:")]
if not meshes:
    raise ValueError("no mesh to rig: open the character's low-poly or mid-poly .glb first")
old = bpy.data.objects.get(PARAMS["name"])
if old is not None and old.type == "ARMATURE":
    for o in list(old.children):
        world_was = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = world_was
    bpy.data.objects.remove(old, do_unlink=True)
pieces, worlds = [], {}
for obj in meshes:
    found, worlds[obj.name] = islands_of(obj)
    pieces += found
low = Vector([min(p["lo"][k] for p in pieces) for k in range(3)])
high = Vector([max(p["hi"][k] for p in pieces) for k in range(3)])
tall = high.z - low.z
floor = low.z

recipe = PARAMS["recipe"]
if recipe is None:
    for obj in meshes:
        if obj.get("forge_build"):
            recipe = json.loads(obj["forge_build"]).get("pieces")
if isinstance(recipe, dict):
    recipe = recipe.get("pieces")
if recipe:
    segs, placed_from = recipe_segments(recipe), "recipe"
else:
    segs, placed_from = [island_segment(p, worlds[p["obj"].name], tall) for p in pieces], "mesh"
flesh = [s for s in segs if not s["gear"]] or segs

# ---- read the build: arms, trunk, legs, feet, head, tail ----
notes = {}
left = [s for s in flesh if s["side"] > 0]
if not left:
    raise ValueError("nothing on the character's left (+x): is it standing in a T-pose facing -y?")
far = max(s["hi"].x for s in left)
tip_seg = [s for s in left if s["hi"].x == far][0]
if far < 0.3 * tall:
    raise ValueError("the arms are not held out (the hands reach x = %.2f on a %.2f m figure): this needs a T-pose" % (far, tall))
arm_z = (tip_seg["lo"].z + tip_seg["hi"].z) / 2
arm_segs = [s for s in left if s["lo"].z <= arm_z <= s["hi"].z and s["hi"].x > 0.25 * far and s["hi"].z - s["lo"].z < 0.5 * tall]
if not arm_segs:
    arm_segs = [tip_seg]
trunk = [s for s in flesh if s["side"] == 0]
if not trunk:
    raise ValueError("no piece sits on the center line: is the character centered on x = 0?")
uprights = [s for s in trunk if s["axis"] == 2 and s["kind"] not in ("band", "tube") and s["hi"].z > 0.5 * arm_z] or trunk
torso = sorted(uprights, key=box_size)[-1]
# a tail: a long piece on the center line that runs out behind the torso, below the hips
tails = [s for s in trunk if s is not torso and s["kind"] not in ("head", "band") and s["hi"].y > torso["hi"].y + 0.06 * tall
         and s["hi"].y - s["lo"].y > 0.1 * tall and s["lo"].z < 0.5 * arm_z and len(s["rows"]) >= 3]
tail = sorted(tails, key=back_end)[-1] if tails else None
trunk = [s for s in trunk if s is not tail]
uprights = [s for s in uprights if s is not tail and (s["hi"] - s["lo"]).x > 0.4 * (torso["hi"] - torso["lo"]).x]

def trunk_at(z):
    """The trunk's middle and half-size at a height, from the pieces on the center line."""
    hit = envelope(uprights, 2, z) or envelope([s for s in trunk if box_size(s) > 0.05 * box_size(torso)], 2, z)
    if hit is None:
        hit = envelope([torso], 2, clamp(z, torso["lo"].z + 1e-4, torso["hi"].z - 1e-4))
    return hit

chest_wide = trunk_at(clamp(arm_z, torso["lo"].z, torso["hi"].z))[1].x
arm_in = min(s["lo"].x for s in arm_segs)
shoulder_x = clamp(0.85 * chest_wide, max(arm_in, 0.04 * tall), 0.45 * far)
arm_long = far - shoulder_x
rings = rings_of(arm_segs, 0, 1.0)
wrist_x, notes["wrist"] = find_joint(rings, shoulder_x + 0.6 * arm_long, shoulder_x + 0.9 * arm_long, shoulder_x + 0.8 * arm_long, ["narrowest ring"])
elbow_x, notes["elbow"] = find_joint(rings, lerp(shoulder_x, wrist_x, 0.38), lerp(shoulder_x, wrist_x, 0.68),
                                     lerp(shoulder_x, wrist_x, 0.54), ["close rings", "narrowest ring", "nearest ring"])
arm_mid = envelope(arm_segs, 0, clamp(shoulder_x + 0.15 * arm_long, arm_in + 1e-4, far))
wrist_mid = envelope(arm_segs, 0, wrist_x)
shoulder = Vector((shoulder_x, arm_mid[0].y, arm_mid[0].z))
wrist = Vector((wrist_x, wrist_mid[0].y, wrist_mid[0].z))
elbow = shoulder.lerp(wrist, (elbow_x - shoulder_x) / (wrist_x - shoulder_x))
tip_mid = envelope(arm_segs, 0, far - 1e-4) or wrist_mid
hand_tip = wrist.lerp(Vector((far, tip_mid[0].y, tip_mid[0].z)), 0.9)
arm_thick = wrist_mid[1].z

leg_segs = [s for s in left if s["axis"] == 2 and s["hi"].z < arm_z and (s["lo"].z + s["hi"].z) / 2 < 0.6 * arm_z and s["kind"] != "band"]
if not leg_segs:
    raise ValueError("no leg found on the left (+x) side: the legs should be upright pieces beside the center line")
foot_segs = [s for s in left if s["lo"].z < floor + 0.04 * tall and s["hi"].z < floor + 0.2 * tall and s not in leg_segs]
leg_top = max(s["hi"].z for s in leg_segs)
leg_low = min(s["lo"].z for s in leg_segs)
top = envelope(leg_segs, 2, leg_top - 1e-4)
foot_top = max([s["hi"].z for s in foot_segs] or [floor + 0.075 * tall]) - floor
ankle_z = floor + clamp(0.6 * foot_top, 0.03 * tall, 0.09 * tall)
hip_z = max(leg_top - 0.25 * top[1].x, ankle_z + 0.55 * (leg_top - ankle_z))
hip_mid = envelope(leg_segs, 2, hip_z)
ankle_mid = envelope(leg_segs, 2, max(ankle_z, leg_low + 1e-4))
hip = Vector((hip_mid[0].x, hip_mid[0].y, hip_z))
ankle = Vector((ankle_mid[0].x, ankle_mid[0].y, ankle_z))
rings = rings_of(leg_segs, 2, -1.0)
leg_long = hip_z - ankle_z
knee_at, notes["knee"] = find_joint(rings, -(hip_z - 0.38 * leg_long), -(hip_z - 0.68 * leg_long), -(hip_z - 0.5 * leg_long), ["close rings", "nearest ring"])
knee = hip.lerp(ankle, clamp((hip_z + knee_at) / leg_long, 0.44, 0.56))  # never so lopsided that the leg can't stride
leg_thick = envelope(leg_segs, 2, (hip_z + knee.z) / 2)[1].x
toe_y = min([s["lo"].y for s in foot_segs] or [ankle.y - 0.12 * tall])
foot_x = (min(s["lo"].x for s in foot_segs) + max(s["hi"].x for s in foot_segs)) / 2 if foot_segs else ankle.x
ball = Vector((ankle.x, lerp(ankle.y, toe_y, 0.62), floor + 0.4 * (ankle_z - floor)))  # straight ahead of the ankle, so ankle and toes hinge on one axis
toe_tip = Vector((ball.x, lerp(ankle.y, toe_y, 0.95), ball.z))
toe_mid = envelope(foot_segs, 1, (ball.y + toe_tip.y) / 2) if foot_segs else None
if toe_mid is not None:  # a thin or pointed toe (a heeled shoe's): the toe bone moves by the little it takes to stay inside the foot
    aside = clamp(ball.x, toe_mid[0].x - 0.8 * toe_mid[1].x, toe_mid[0].x + 0.8 * toe_mid[1].x) - ball.x
    ball.x, toe_tip.x = ball.x + aside, toe_tip.x + aside  # sideways whole, so it still hinges square to the foot
    middle = clamp(ball.z, toe_mid[0].z - 0.8 * toe_mid[1].z, toe_mid[0].z + 0.8 * toe_mid[1].z)
    if abs(middle - ball.z) > 1e-5:
        toe_tip.z = max(2 * middle - ball.z, floor + 0.002)  # and its tip dips

heads = [s for s in trunk if s["kind"] == "head"]
if not heads:
    above = [s for s in trunk if s is not torso and (s["lo"].z + s["hi"].z) / 2 > arm_z - 0.05 * tall and s["lo"].z > arm_z - 0.1 * tall and s["kind"] != "tube" and s["kind"] != "band"]
    size = [(s["hi"] - s["lo"]).x * (s["hi"] - s["lo"]).y * (s["hi"] - s["lo"]).z for s in above]
    heads = [s for s, v in zip(above, size) if v >= 0.3 * max(size)]
if heads:
    head_lo = min(s["lo"].z for s in heads)
    head_hi = max(s["hi"].z for s in heads)
    head_y = sum((s["lo"].y + s["hi"].y) / 2 for s in heads) / len(heads)
else:  # no piece to call a head: the top of the trunk stands in
    head_lo, head_hi, head_y = lerp(arm_z, high.z, 0.35), high.z, trunk_at(high.z - 1e-3)[0].y
notes["head"] = "a head piece" if heads else "the top of the trunk"
hips_z = hip_z + 0.02 * tall
skull_z = max(head_lo + 0.2 * (head_hi - head_lo), hips_z + 0.2 * tall)
neck_z = max(skull_z - 0.05 * tall, lerp(hips_z, skull_z, 0.75))
spine_z, chest_z = lerp(hips_z, neck_z, 0.3), lerp(hips_z, neck_z, 0.62)

def spine_point(z, toward_head):
    return Vector((0.0, lerp(trunk_at(z)[0].y, head_y, toward_head), z))

joints = {"hips": spine_point(hips_z, 0), "spine": spine_point(spine_z, 0), "chest": spine_point(chest_z, 0),
          "neck": spine_point(neck_z, 0.25), "head": spine_point(skull_z, 0.6),
          "head_top": Vector((0.0, lerp(trunk_at(skull_z)[0].y, head_y, 0.8), lerp(skull_z, head_hi, 0.85)))}
collar = Vector((0.3 * shoulder_x, lerp(joints["chest"].y, shoulder.y, 0.7), lerp(joints["neck"].z, shoulder.z, 0.7)))

tail_points = []
if PARAMS["tail"]:
    if tail is not None:
        path = [r[1].copy() for r in tail["rows"]]
        if path[0].y > path[-1].y:
            path.reverse()
        if placed_from == "mesh" and len(path) > 6:  # a slanted tube's rings come back in bits: even them out
            path = [path[0]] + [(a + b + c) / 3 for a, b, c in zip(path, path[1:], path[2:])] + [path[-1]]
        path = [p for p in path if p.y > joints["hips"].y] or path
        path[0] = path[0].lerp(path[1], 0.2)  # the first point is on the tail's end cap: start a little inside
        long = sum((b - a).length for a, b in zip(path, path[1:]))
        count = int(clamp(round(long / (0.09 * tall)), 2, 5))
        for i in range(count + 1):
            want, walked = long * i / count, 0.0
            spot = path[-1]
            for a, b in zip(path, path[1:]):
                step = (b - a).length
                if walked + step >= want - 1e-9:
                    spot = a.lerp(b, (want - walked) / max(step, 1e-9))
                    break
                walked += step
            tail_points.append(Vector((0.0, spot.y, spot.z)))
        end_half = tail["rows"][-1][2] if tail["rows"][-1][1].y > tail["rows"][0][1].y else tail["rows"][0][2]
        tail_points[-1] = tail_points[-2].lerp(tail_points[-1], 0.9) + Vector((0, 0, 0.5 * max(end_half.z, end_half.x)))

# ---- the bones: name, head, tail, parent, which way its z axis points ----
plan = [("hips", joints["hips"], joints["spine"], None, "spine"), ("spine", joints["spine"], joints["chest"], "hips", "spine"),
        ("chest", joints["chest"], joints["neck"], "spine", "spine"), ("neck", joints["neck"], joints["head"], "chest", "spine"),
        ("head", joints["head"], joints["head_top"], "neck", "spine")]
for tag, flip in (("_l", 1.0), ("_r", -1.0)):
    turn = Vector((flip, 1, 1))
    plan += [("shoulder" + tag, collar * turn, shoulder * turn, "chest", "arm"), ("upper_arm" + tag, shoulder * turn, elbow * turn, "shoulder" + tag, "arm"),
             ("forearm" + tag, elbow * turn, wrist * turn, "upper_arm" + tag, "arm"), ("hand" + tag, wrist * turn, hand_tip * turn, "forearm" + tag, "arm"),
             ("thigh" + tag, hip * turn, knee * turn, "hips", "leg"), ("shin" + tag, knee * turn, ankle * turn, "thigh" + tag, "leg"),
             ("foot" + tag, ankle * turn, ball * turn, "shin" + tag, "foot"), ("toe" + tag, ball * turn, toe_tip * turn, "foot" + tag, "foot")]
for i in range(len(tail_points) - 1):
    plan.append(("tail_%d" % (i + 1), tail_points[i], tail_points[i + 1], "tail_%d" % i if i else "hips", "tail"))

data = bpy.data.armatures.new(PARAMS["name"])
rig = bpy.data.objects.new(PARAMS["name"], data)
scene.collection.objects.link(rig)
for o in bpy.context.selected_objects:
    o.select_set(False)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
for name, start, end, parent, kind in plan:
    bone = data.edit_bones.new(name)
    bone.head, bone.tail = start, end
    if parent:
        bone.parent = data.edit_bones[parent]
        bone.use_connect = (bone.parent.tail - bone.head).length < 1e-5
    bone.align_roll(Vector(UP[kind]))
bpy.ops.object.mode_set(mode="OBJECT")
data.display_type = "STICK"
rig.show_in_front = True
bones = [(name, start, end, chain_of(name)) for name, start, end, parent, kind in plan]
parents = {name: parent for name, start, end, parent, kind in plan}

# ---- how bulky: what makes the joints stiffer and, later, the gait heavier ----
body_volume = sum(p["volume"] for p in pieces if not p["gear"]) or sum(p["volume"] for p in pieces)
weighted = sum(p["volume"] * (p["lo"].z + p["hi"].z) / 2 for p in pieces if not p["gear"] or body_volume == 0)
bulk = body_volume / tall ** 3
flex = PARAMS["flexibility"] or round(clamp(1.15 - 2.2 * (bulk - 0.015), 0.8, 1.15), 2)

# ---- bind every mesh ----
def nearest_bone(p, allowed):
    best, best_d = None, 1e9
    for name, a, b, chain in bones:
        if allowed is None or chain in allowed:
            d = nearest_on(a, b, p)
            if d < best_d:
                best, best_d = name, d
    return best

def piece_weights(obj):
    """Weights by piece: each connected piece goes to the limb most of its points are nearest, a small
    piece rigidly to one bone, a larger one blended across the joints of that limb and the trunk."""
    world, done = worlds[obj.name], {}
    for piece in [p for p in pieces if p["obj"] == obj]:
        votes = {}
        for i in piece["verts"][::max(1, len(piece["verts"]) // 60)]:
            chain = chain_of(nearest_bone(world[i], None))
            votes[chain] = votes.get(chain, 0) + 1
        home = sorted(votes.items(), key=second)[-1][0]
        piece["limb"] = home
        allowed = None
        if home != "trunk":
            allowed = {home, "trunk"}
            if home.startswith("leg") and side_of(piece["lo"], piece["hi"]) == 0:
                allowed = {"leg_l", "leg_r", "trunk"}
        size = piece["hi"] - piece["lo"]
        # A face must not bend: the head piece, and whatever sits wholly on it (hair, a hat, glasses, a
        # mustache), goes with the head bone alone. Blended with the neck, a nod squashed the jaw
        # (the head's points moved up to 11% of its height against the bone on the low-poly ninja).
        if home == "trunk" and heads and piece["lo"].z >= head_lo - 0.25 * (head_hi - head_lo) and (piece["lo"].z + piece["hi"].z) / 2 > head_lo:
            for i in piece["verts"]:
                done[i] = [("head", 1.0)]
            continue
        if size.length < 0.12 * tall:
            one = nearest_bone((piece["lo"] + piece["hi"]) / 2, allowed)
            for i in piece["verts"]:
                done[i] = [(one, 1.0)]
            continue
        for i in piece["verts"]:
            near = [(nearest_on(a, b, world[i]), name) for name, a, b, chain in bones if allowed is None or chain in allowed]
            near.sort(key=first)
            fall = max(0.35 * near[0][0], 0.012 * tall)
            got = [(name, (1 - (d - near[0][0]) / fall) ** 2) for d, name in near[:4] if d - near[0][0] < fall]
            total = sum(w for _, w in got)
            done[i] = [(name, w / total) for name, w in got]
            if allowed and len(allowed) == 3:  # a skirt, kilt or belt around both legs: half of it stays with the hips, so a stride doesn't tear it
                done[i] = [(name, 0.5 * w) for name, w in done[i] if name != "hips"] + [("hips", 0.5 + 0.5 * sum(w for name, w in done[i] if name == "hips"))]
    # The ball of the foot is a hinge resting on the floor: ahead of it is all toe, behind it all foot,
    # so a lifting heel can't drag the toes down through the ground.
    for i, pairs in done.items():
        for tag, flip in (("_l", 1.0), ("_r", -1.0)):
            if any(name in ("foot" + tag, "toe" + tag) for name, w in pairs):
                front = "toe" + tag if world[i].y < ball.y else "foot" + tag
                low = world[i].z < ankle.z  # below the ankle it is foot, not shin: a leaning shin must not push the sole into the floor
                kept = [(name, w) for name, w in pairs if name not in ("foot" + tag, "toe" + tag) and not (low and name == "shin" + tag)]
                done[i] = kept + [(front, 1.0 - sum(w for _, w in kept))]
    for group in list(obj.vertex_groups):
        obj.vertex_groups.remove(group)
    groups = {name: obj.vertex_groups.new(name=name) for name, a, b, chain in bones}
    for i, pairs in done.items():
        for name, w in pairs:
            if w > 1e-4:
                groups[name].add([i], w, "REPLACE")

def second(pair):
    return pair[1]

def auto_weights(obj):
    """Blender's automatic weights, kept only if they hold up. Returns why not, or None."""
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    except RuntimeError as err:
        return "it failed: %s" % str(err).strip()[:80]
    names = {g.index: g.name for g in obj.vertex_groups}
    world, bare, leak = worlds[obj.name], 0, 0
    for v in obj.data.vertices:
        total = sum(g.weight for g in v.groups)
        if total < 1e-4:
            bare += 1
        elif abs(world[v.index].x) > 0.05 * tall:
            wrong = "_r" if world[v.index].x > 0 else "_l"
            if sum(g.weight for g in v.groups if names[g.group].endswith(wrong)) > 0.3 * total:
                leak += 1
    if bare:
        return "it left %d of %d points with no weight" % (bare, len(obj.data.vertices))
    if leak > 0.01 * len(obj.data.vertices):
        return "it tied %d points to the far side's bones" % leak
    return None

# One way of binding for the whole character: a shirt bound one way over a chest bound another lets the chest poke through.
skin, why = {}, "asked for by-piece weights"
if PARAMS["weights"] == "auto":
    failed = [(obj.name, auto_weights(obj)) for obj in meshes]
    failed = [(name, said) for name, said in failed if said]
    why = "automatic weights did not hold on %s: %s" % failed[0] if failed else None
for obj in meshes:
    for mod in [m for m in obj.modifiers if m.type == "ARMATURE"]:
        obj.modifiers.remove(mod)
    if why is None:
        skin[obj.name] = {"used": "automatic"}
        for piece in [p for p in pieces if p["obj"] == obj]:
            piece["limb"] = chain_of(nearest_bone((piece["lo"] + piece["hi"]) / 2, None))
    else:
        piece_weights(obj)
        skin[obj.name] = {"used": "pieces"}
    world_was = obj.matrix_world.copy()
    obj.parent = rig
    obj.matrix_parent_inverse = rig.matrix_world.inverted()
    obj.matrix_world = world_was
    for mod in [m for m in obj.modifiers if m.type == "ARMATURE"]:
        obj.modifiers.remove(mod)
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    # at most four bones a point (what a .glb carries), adding up to 1
    bare = 0
    for v in obj.data.vertices:
        pairs = sorted([(g.weight, g.group) for g in v.groups], reverse=True)
        for w, index in pairs[4:]:
            obj.vertex_groups[index].remove([v.index])
        total = sum(w for w, _ in pairs[:4])
        if total < 1e-6:
            bare += 1
            continue
        for w, index in pairs[:4]:
            obj.vertex_groups[index].add([v.index], w / total, "REPLACE")
    skin[obj.name]["points"] = len(obj.data.vertices)
    skin[obj.name]["unweighted"] = bare

# ---- limits ----
limits = {}
for bone in rig.pose.bones:
    bone.rotation_mode = "QUATERNION"
    lim = limit_of(bone.name, flex)
    if lim is None:
        continue
    limits[bone.name] = lim
    rule = bone.constraints.new("LIMIT_ROTATION")
    rule.name = "Joint limit"
    rule.owner_space = "LOCAL"
    rule.euler_order = "XYZ"
    rule.use_limit_x = rule.use_limit_y = rule.use_limit_z = True
    rule.min_x, rule.max_x, rule.min_y, rule.max_y, rule.min_z, rule.max_z = [math.radians(v) for v in lim]
    data.bones[bone.name]["limit_deg"] = lim

# ---- sockets follow their bones ----
hung = {}
for o in scene.objects:
    if o.type == "EMPTY" and o.get("forge") == "socket" and SOCKET_BONES.get(o.get("socket")) in data.bones:
        bone = data.bones[SOCKET_BONES[o["socket"]]]
        world_was = o.matrix_world.copy()
        o.parent, o.parent_type, o.parent_bone = rig, "BONE", bone.name
        o.matrix_parent_inverse = (rig.matrix_world @ bone.matrix_local @ Matrix.Translation((0, bone.length, 0))).inverted()
        o.matrix_basis = world_was
        hung[o["socket"]] = bone.name

# ---- is every bone inside the mesh? ----
points, faces, trees = [], [], []
for obj in meshes:
    start = len(points)
    points += worlds[obj.name]
    faces += [tuple(start + i for i in poly.vertices) for poly in obj.data.polygons]
    for piece in [p for p in pieces if p["obj"] == obj]:
        mine = set(piece["verts"])
        trees.append((piece, BVHTree.FromPolygons([tuple(p) for p in worlds[obj.name]], [tuple(poly.vertices) for poly in obj.data.polygons if poly.vertices[0] in mine])))
tree = BVHTree.FromPolygons([tuple(p) for p in points], faces)

def inside(p):
    """Inside the mesh if it is inside any one piece: rays out of it, most ways, first meet that piece's wall from within."""
    for piece, walls in trees:
        if all(piece["lo"][k] - 1e-6 <= p[k] <= piece["hi"][k] + 1e-6 for k in range(3)):
            shut = 0
            for aim in ((1, 0.13, 0.07), (-1, 0.11, 0.05), (0.09, 1, 0.12), (0.06, -1, 0.1), (0.1, 0.07, 1), (0.05, 0.12, -1)):
                hit = walls.ray_cast(p, Vector(aim).normalized())
                if hit[0] is not None and hit[1].dot(Vector(aim)) > 0:
                    shut += 1
            if shut >= 4:
                return True
    return False

outside = []
for name, start, end, chain in bones:
    for label, p in (("head", start), ("middle", (start + end) / 2)):
        if not inside(p):
            outside.append({"bone": name, "at": label, "off_cm": round(100 * tree.find_nearest(p)[3], 1)})

# ---- the build, measured: what walk.py makes a gait from ----
others = [p for p in pieces if not str(p.get("limb", "")).startswith("arm")]
widths = []
for i in range(24):
    z0, z1 = floor + tall * i / 24, floor + tall * (i + 1) / 24
    widths.append(round(max([max(abs(p["lo"].x), abs(p["hi"].x)) for p in others if p["lo"].z < z1 and p["hi"].z > z0 and p["hi"].z - p["lo"].z < 0.9 * tall] or [0.0]), 3))
measure = {
    "height": round(tall, 3), "floor": round(floor, 4),
    "hip_height": round(hip.z - floor, 3), "thigh": round((knee - hip).length, 3), "shin": round((ankle - knee).length, 3),
    "ankle_height": round(ankle.z - floor, 3), "foot_long": round(ankle.y - toe_y, 3), "leg_thick": round(leg_thick, 3),
    "hip_half_width": round(hip.x, 3), "foot_x": round(ball.x, 3), "shoulder_half_width": round(shoulder.x, 3), "shoulder_height": round(shoulder.z - floor, 3),
    "arm_long": round((elbow - shoulder).length + (wrist - elbow).length + (hand_tip - wrist).length, 3), "arm_thick": round(arm_thick, 3),
    "body_half_widths": widths, "volume_m3": round(body_volume, 4), "bulk": round(bulk, 4),
    "mass_center_height": round((weighted / body_volume - floor) / tall, 3) if body_volume else 0.5,
    "tail_long": round(sum((b - a).length for a, b in zip(tail_points, tail_points[1:])), 3),
    "tail_tip_height": round(tail_points[-1].z - floor, 3) if tail_points else 0.0, "tail_bones": max(len(tail_points) - 1, 0),
    "flexibility": flex,
}
rig["forge_rig"] = json.dumps({"measure": measure, "limits": limits, "placed_from": placed_from})
result = {
    "rig": rig.name, "bones": [b[0] for b in bones], "placed_from": placed_from, "found_by": notes,
    "joints": {name: [round(c, 3) for c in start] for name, start, end, chain in bones},
    "skin": skin, "meshes": [o.name for o in meshes], "sockets": hung,
    "weights": "automatic" if why is None else "pieces", "why_not_automatic": why,
    "limits": limits, "measure": measure, "bones_outside": outside,
}
print("RESULT " + json.dumps(result))
