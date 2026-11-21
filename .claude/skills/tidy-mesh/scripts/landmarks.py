# Find a character's anatomy: where its chin, neck, shoulders, armpits, chest,
# waist, hips, crotch, elbows, wrists, knees and ankles are, how long its
# hands and feet are, and what shape its body is all the way along. Prints a
# ready-made "body" piece for build.py. Changes nothing but its own marks.
#
# The character stands as the pipeline leaves it: T-pose, z up, feet on the
# floor, facing -y (its left side is +x). It works on any mesh that stands
# like that: the detailed reference, a base body, or a low-poly block-out, so
# the same reading can be taken of each and compared.
#
# What it reads:
#   "landmarks"    one point [x, y, z] each, in world meters, on the +x side:
#                  "top", "chin", "neck" (the narrowest ring of the neck),
#                  "neck_base", "shoulder" (the top of the shoulder, where the
#                  arm starts), "armpit", "chest", "waist", "hips" (the widest
#                  ring of the pelvis), "crotch", "elbow", "wrist",
#                  "fingertip", "knee", "ankle", "heel", "toe"
#   "found"        how each was found: "shape" (it shows on the mesh) or
#                  "usual proportion" (nothing showed, so it sits where a body
#                  usually has it). Check those against the picture, and put
#                  one right with "landmarks": {"knee": [x, y, z]} on the piece.
#   "proportions"  heads tall, leg and arm length as shares of the height,
#                  shoulders against hips, hand and foot length
#   "girth"        half-width and half-depth at each named ring
#   "joints"       where the shoulder, elbow, wrist, hip, knee and ankle turn
#                  (middle of the limb), for a skeleton
#
# It also keeps the body's surface itself in the scene, under the piece's
# name: a ring of 24 distances every centimeter or two up the trunk and neck,
# out along one arm and hand, down one leg and along one foot (both sides are
# read and averaged). build.py's "body" piece lays its rings on that, so the
# built body has this character's own chest, belly, calves and shoulders,
# whether it is a wrestler, a troll or a cartoon. Whatever is on the mesh
# gets followed: clothes count as body. A character whose clothes hide its
# body (a long skirt, a robe) should be read off its base body instead:
# "object": "Body".
#
# The result's "body" is the piece: paste it into build.py's "parts" as it
# is, then change what you like (build.py's notes list every setting).
#
# "head": the head's box, when you have it (the one face.py took). Its floor
# is then the chin and its top the crown, which is surer than reading a chin
# off a beard or a collar. A head sunk between the shoulders needs it.
#
# With "show": True it draws a small cross at each landmark, as a wire
# object, "Look: landmarks". look(mode="angles") with the reference shows
# whether each sits on its joint. The marks never render or export; a run
# with "show": False removes them.
#
# Send this whole file through the blender MCP `execute_blender_code` tool
# after editing PARAMS. Prints RESULT {json}. About 2 s. Safe-mode compatible.

PARAMS = {
    "object": None,   # the mesh to read: a name, or a list of names read as one figure; None = the largest visible mesh
    "head": None,     # the head's box, {"min": [x, y, z], "max": [x, y, z]}; None = read the chin off the shape
    "name": "body",   # the piece's name, and the name its surface is kept under in the scene
    "show": True,     # draw a cross at each landmark
    "keep": True,     # keep the surface in the scene for build.py; False only measures
    "points": 30000,  # how many points the shape is read from
}

import bpy
import json
import math
import random
from mathutils import Vector
from mathutils.bvhtree import BVHTree

AROUND = 24  # distances in each ring of the kept surface
STATIONS = {"trunk": 56, "arm": 30, "hand": 12, "leg": 40, "foot": 14}  # rings kept along each stretch
NZ, NX = 150, 100  # how finely the first reading slices the figure, up and sideways


def face_count(obj):
    return len(obj.data.polygons)

def pick_objects(name):
    if isinstance(name, (list, tuple)):
        found = [bpy.data.objects.get(n) for n in name]
        if not found or any(o is None or o.type != "MESH" for o in found):
            raise ValueError("no mesh objects named %r" % (name,))
        return found
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise ValueError("no mesh object named %r" % name)
        return [obj]
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get() and not o.name.startswith("Look: ")]
    if not meshes:
        raise ValueError("the scene has no visible mesh objects")
    return [max(meshes, key=face_count)]

def mix(a, b, t):
    return a + (b - a) * t

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def r4(v):
    return round(v, 4)

def middle(values):
    values = sorted(values)
    return values[len(values) // 2]

def smooth(values):
    """Each value averaged with its neighbors; None stays None."""
    out = []
    for i, v in enumerate(values):
        near = [w for w in values[max(i - 1, 0):i + 2] if w is not None]
        out.append(sum(near) / len(near) if v is not None and near else None)
    return out

def run_near(values, seed, gap):
    """In sorted `values`, the unbroken run (no step wider than `gap`) holding the value nearest `seed`: (low, high)."""
    best = 0
    for i, v in enumerate(values):
        if abs(v - seed) < abs(values[best] - seed):
            best = i
    i = j = best
    while i > 0 and values[i] - values[i - 1] <= gap:
        i -= 1
    while j < len(values) - 1 and values[j + 1] - values[j] <= gap:
        j += 1
    return values[i], values[j]

def dip(values, first, last, depth):
    """The index in first..last where `values` dips most below what lies on both sides of it, or None
    when no dip reaches `depth` (0.93 = seven percent under the lower shoulder)."""
    best, best_score = None, depth
    for i in range(first + 1, last):
        if values[i] is None:
            continue
        left = [v for v in values[first:i] if v is not None]
        right = [v for v in values[i + 1:last + 1] if v is not None]
        if not left or not right:
            continue
        score = values[i] / max(min(max(left), max(right)), 1e-9)
        if score < best_score:
            best, best_score = i, score
    return best

def peak(values, first, last):
    """The index in first..last where `values` is highest, or None if that is at either end (no peak, only a slope)."""
    best = None
    for i in range(first, last + 1):
        if values[i] is not None and (best is None or values[i] > values[best]):
            best = i
    if best is None or best in (first, last):
        return None
    return best

def cast(tree, start, aim, reach):
    """How far along `aim` from `start` the surface is, or None within `reach`."""
    hit = tree.ray_cast(start, aim, reach)
    return hit[3] if hit[0] is not None else None

def ring(tree, where, axis, clips, reach, flip, own=False):
    """The surface around a point: AROUND distances, looking in from outside along the plane across
    `axis`. `clips` are walls the look must not start behind, as (axis index, sign, value): keep
    sign * p[axis] <= sign * value. A look that starts at a wall and meets nothing on the way in is
    tried again from the middle outward, if the middle is inside the figure: the first surface
    before the wall, or the wall itself (the shape runs on past it). Any other look that meets
    nothing is None.
    `flip` mirrors the look across x = the center, to read the other side with the same numbering.
    `own`: a limb's ring. Where the look in from outside lands much farther out than the first
    surface met from the middle, something else stands there (a tail behind a leg, a skirt over a
    thigh, the other leg) and the nearer surface is taken."""
    u, v = [(1, 2), (0, 2), (0, 1)][axis]
    out = []
    middle = Vector(where)
    if flip:
        middle.x = 2 * flip[0] - middle.x
    within = None  # is the middle inside the figure? worked out when first needed
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
        start = Vector(where) + aim * far
        if flip:
            start.x, aim.x = 2 * flip[0] - start.x, -aim.x
        gone = cast(tree, start, -aim, far) if far > 1e-6 else None
        if gone is not None:
            near = cast(tree, middle, aim, far - gone) if own else None
            out.append(near if near is not None and near > 0.01 * reach and far - gone > 3.0 * near + 0.03 * reach else far - gone)
        elif walled:
            if within is None:
                ways = [Vector([1.0 if i == u else 0.0 for i in range(3)]), Vector([1.0 if i == v else 0.0 for i in range(3)])]
                within = all(cast(tree, middle, way * side, reach) is not None for way in ways for side in (1, -1))
            reached = cast(tree, middle, aim, far) if within and far > 1e-6 else None
            out.append(reached if reached is not None else (far if within else None))
        else:
            out.append(None)
    return out

def both(a, b):
    """Two readings of one ring (the left and the mirrored right): their mean, or whichever saw something."""
    out = []
    for p, q in zip(a, b):
        if p is None or q is None:
            out.append(q if p is None else p)
        else:
            out.append((p + q) / 2)
    return out

def mended(rows):
    """Rings with their gaps filled from the neighbors around the ring, and spikes (a stray scrap, a
    hole) pulled back to what the rings on either side say."""
    for row in rows:
        seen = [r for r in row if r is not None]
        fill = middle(seen) if seen else 0.0
        for k in range(AROUND):
            if row[k] is None:
                near = [row[(k + d) % AROUND] for d in (-2, -1, 1, 2) if row[(k + d) % AROUND] is not None]
                row[k] = sum(near) / len(near) if near else fill
    out = []
    for i, row in enumerate(rows):
        new = []
        for k in range(AROUND):
            near = sorted(rows[j][k] for j in range(max(i - 2, 0), min(i + 3, len(rows))))
            mid = near[len(near) // 2]
            new.append(mid if abs(row[k] - mid) > 0.35 * max(mid, 1e-6) else row[k])
        out.append(new)
    return out

def spans(row, u_first):
    """A ring's half-sizes across its two directions: (toward -u, toward +u, toward -v, toward +v)."""
    us = [r * math.cos(2 * math.pi * k / AROUND) for k, r in enumerate(row)]
    vs = [r * math.sin(2 * math.pi * k / AROUND) for k, r in enumerate(row)]
    return -min(us), max(us), -min(vs), max(vs)

def at(rows, pos):
    """The kept ring nearest a position along its stretch."""
    best = rows[0]
    for row in rows:
        if abs(row[0] - pos) < abs(best[0] - pos):
            best = row
    return best

def half_sizes(rows, pos):
    row = at(rows, pos)
    a, b, c, d = spans(row[3:], True)
    return [r4((a + b) / 2), r4((c + d) / 2)]


objs = pick_objects(PARAMS["object"])
bpy.context.view_layer.update()
verts, tris, areas = [], [], []
for obj in objs:
    world = obj.matrix_world
    base = len(verts)
    verts += [world @ v.co for v in obj.data.vertices]
    obj.data.calc_loop_triangles()
    for t in obj.data.loop_triangles:
        tris.append((base + t.vertices[0], base + t.vertices[1], base + t.vertices[2]))
        areas.append(t.area)
if len(tris) < 20:
    raise ValueError("%s has too few faces to read a body from" % objs[0].name)
tree = BVHTree.FromPolygons([tuple(p) for p in verts], tris)
rng = random.Random(0)
points = []
for i in rng.choices(range(len(tris)), weights=areas, k=PARAMS["points"]):
    a, b, c = [verts[j] for j in tris[i]]
    s, t = rng.random(), rng.random()
    if s + t > 1:
        s, t = 1 - s, 1 - t
    points.append(a + (b - a) * s + (c - a) * t)

floor = min(p.z for p in verts)
crown = max(p.z for p in verts)
tall = crown - floor
left, right = max(p.x for p in verts), min(p.x for p in verts)
cx = (left + right) / 2
if abs(cx) < 0.02 * tall:
    cx = 0.0
far = (left - right) / 2
if far < 0.3 * tall:
    raise ValueError("the arms are not held out (the hands reach %.2f m from the middle of a %.2f m figure): this needs a T-pose" % (far, tall))
found = {}

# The first reading: every point by how high it is, and by how far out to the side (both sides folded onto one).
by_z = [[] for _ in range(NZ)]
by_x = [[] for _ in range(NX)]
for p in points:
    out = abs(p.x - cx)
    by_z[min(int((p.z - floor) / tall * NZ), NZ - 1)].append((out, p.y))
    by_x[min(int(out / far * NX), NX - 1)].append((p.z, p.y))

def z_of(i):
    return floor + (i + 0.5) * tall / NZ

def x_of(i):
    return (i + 0.5) * far / NX

def zi(z):
    return clamp(int((z - floor) / tall * NZ), 0, NZ - 1)

def xi(x):
    return clamp(int(x / far * NX), 0, NX - 1)

# ---- the arm: followed in from the fingertips until it meets the trunk ----
tips = sorted(z for z, y in [q for i in range(int(0.85 * NX), NX) for q in by_x[i]])
arm_z = tips[len(tips) // 2] if tips else floor + 0.75 * tall
arm = [None] * NX  # per slice: (lowest, highest, front, back) of the arm there
seed = arm_z
for i in range(NX - 1, -1, -1):
    zs = sorted(z for z, y in by_x[i])
    if not zs:
        continue
    lo, hi = run_near(zs, seed, 0.02 * tall)
    ys = [y for z, y in by_x[i] if lo <= z <= hi]
    arm[i] = (lo, hi, min(ys), max(ys))
    seed = (lo + hi) / 2
outer = [a for a in arm[int(0.45 * NX):int(0.85 * NX)] if a]
thick = middle([a[1] - a[0] for a in outer]) if outer else 0.08 * tall
under = middle([a[0] for a in outer]) if outer else arm_z - thick / 2
pit = None
for i in range(int(0.5 * NX), -1, -1):
    if arm[i] and (arm[i][0] < under - 1.0 * thick or arm[i][1] - arm[i][0] > 2.4 * thick):
        pit = i + 1
        break
if pit is None:
    pit = int(0.22 * NX)
    found["armpit"] = "usual proportion"
while pit < NX - 1 and arm[pit] is None:
    pit += 1
pit_x = x_of(pit) - 0.5 * far / NX
pit_lo, pit_hi, pit_front, pit_back = arm[pit]
arm_y = (pit_front + pit_back) / 2
girth = [None if a is None else (a[1] - a[0]) + (a[3] - a[2]) for a in arm]
girth = smooth(girth)
reach_arm = far - pit_x
w = dip(girth, xi(pit_x + 0.6 * reach_arm), xi(pit_x + 0.9 * reach_arm), 0.93)
if w is None:
    w = xi(pit_x + 0.76 * reach_arm)
    found["wrist"] = "usual proportion"
while arm[w] is None and w > pit:
    w -= 1
wrist_x = x_of(w)
e = dip(girth, xi(mix(pit_x, wrist_x, 0.4)), xi(mix(pit_x, wrist_x, 0.68)), 0.95)
if e is None:
    e = xi(mix(pit_x, wrist_x, 0.54))
    found["elbow"] = "usual proportion"
while arm[e] is None and e > pit:
    e -= 1
elbow_x = x_of(e)

def arm_middle(x):
    i = max(xi(x), pit)  # inside the armpit the slice is trunk: carry the arm's own middle in
    while arm[i] is None and i > 0:
        i -= 1
    return [x, (arm[i][2] + arm[i][3]) / 2, (arm[i][0] + arm[i][1]) / 2]

# ---- the legs: the gap between them closes at the crotch ----
shins = [q for i in range(zi(floor + 0.1 * tall), zi(floor + 0.3 * tall)) for q in by_z[i]]
if not shins:
    raise ValueError("nothing between 10% and 30% of the height: is the figure standing on z = %.2f?" % floor)
leg_x = middle([out for out, y in shins])
leg_y = middle([y for out, y in shins])
crotch = None
closed = 0
for i in range(zi(floor + 0.15 * tall), zi(arm_z)):
    near = [out for out, y in by_z[i] if abs(y - leg_y) < 0.04 * tall]
    if near and min(near) < 0.012 * tall:
        closed += 1
        if closed == 3:
            crotch = z_of(i - 2) - 0.5 * tall / NZ
            break
    else:
        closed = 0
arm_low = pit_lo - floor
usual = floor + 0.58 * arm_low  # where a crotch usually is, under an armpit this high
if crotch is None:
    crotch = usual
    found["crotch"] = "usual proportion"
elif not 0.8 * (usual - floor) <= crotch - floor <= 1.2 * (usual - floor):
    found["crotch"] = "usual proportion: the gap between the legs closes at %.2f m, which is no crotch (a skirt, a coat, a tail, baggy cloth). Read the body off a base body, or set it yourself" % crotch
    crotch = usual
leg = [None] * NZ  # per slice below the crotch: (inner, outer, front, back) of one leg
seed = leg_x
for i in range(zi(crotch), -1, -1):
    outs = sorted(out for out, y in by_z[i])
    if not outs:
        continue
    lo, hi = run_near(outs, seed, 0.03 * tall)
    ys = [y for out, y in by_z[i] if lo <= out <= hi]
    leg[i] = (lo, hi, min(ys), max(ys))
    seed = (lo + hi) / 2
wide = smooth([None if s is None else s[1] - s[0] for s in leg])
a = dip(wide, zi(floor + 0.02 * tall), zi(floor + 0.2 * (crotch - floor) + 0.04 * tall), 0.93)
if a is None:
    a = zi(floor + 0.1 * (crotch - floor))
    found["ankle"] = "usual proportion"
while leg[a] is None and a < NZ - 1:
    a += 1
ankle_z = z_of(a)
deep = smooth([None if s is None else s[3] - s[2] for s in leg])
k = dip(deep, zi(mix(ankle_z, crotch, 0.45)), zi(mix(ankle_z, crotch, 0.7)), 0.97)
if k is None:
    knee_z = mix(ankle_z, crotch, 0.565)
    found["knee"] = "usual proportion"
else:
    knee_z = z_of(k) + 0.012 * tall

def leg_middle(z):
    i = zi(min(z, crotch - 0.5 * tall / NZ))
    while leg[i] is None and i > 0:
        i -= 1
    return [(leg[i][0] + leg[i][1]) / 2, (leg[i][2] + leg[i][3]) / 2, z]

feet = [q for i in range(0, a + 1) for q in by_z[i]]
foot_out = sorted(out for out, y in feet)
foot_lo, foot_hi = run_near(foot_out, leg_middle(ankle_z)[0], 0.03 * tall)
foot_ys = [y for out, y in feet if foot_lo <= out <= foot_hi]
toe_y, heel_y = min(foot_ys), max(foot_ys)
foot_x = (foot_lo + foot_hi) / 2

# ---- the trunk: its half-width and depth at every height, arms cut off at the armpit ----
trunk = [None] * NZ  # per slice: (half-width, front, back)
for i in range(zi(crotch), NZ):
    outs = sorted(out for out, y in by_z[i])
    if not outs or outs[0] > 0.04 * tall:
        continue
    lo, hi = run_near(outs, 0.0, 0.03 * tall)
    hi = min(hi, pit_x)
    ys = [y for out, y in by_z[i] if out <= hi]
    trunk[i] = (hi, min(ys), max(ys))
half = smooth([None if s is None else s[0] for s in trunk])
depth = smooth([None if s is None else s[2] - s[1] for s in trunk])
h = peak(half, zi(crotch - 0.02 * tall), zi(mix(crotch, pit_lo, 0.3)))
if h is None:
    hips_z = mix(crotch, pit_lo, 0.12)
    found["hips"] = "usual proportion"
else:
    hips_z = z_of(h)
wi = dip(half, zi(mix(crotch, pit_lo, 0.3)), zi(mix(crotch, pit_lo, 0.8)), 0.985)
if wi is None:
    waist_z = mix(crotch, pit_lo, 0.5)
    found["waist"] = "usual proportion"
else:
    waist_z = z_of(wi)
c = peak(depth, zi(max(waist_z, pit_lo - 0.07 * tall)), zi(mix(pit_lo, pit_hi, 0.5)))
if c is None:
    chest_z = pit_lo
    found["chest"] = "usual proportion"
else:
    chest_z = z_of(c)
# The neck: the narrowest ring above the shoulders. Its base is where the slope from the shoulders has come most of the way in.
box = PARAMS["head"]
top_z = box["max"][2] if box else crown
n = dip(half, zi(pit_hi), zi(mix(pit_hi, top_z, 0.75)), 0.97)
if n is None:
    neck_z = min(pit_hi + 0.02 * tall, top_z - 0.08 * tall)
    neck_half = half[zi(neck_z)] or 0.06 * tall
    base_z = neck_z
    found["neck"] = "usual proportion: no neck shows between the shoulders and the head"
else:
    neck_z, neck_half = z_of(n), half[n]
    base_z = neck_z
    for i in range(n, zi(pit_hi) - 1, -1):
        if half[i] is not None and half[i] > neck_half + 0.35 * (pit_x - neck_half):
            break
        base_z = z_of(i)

def front_at(z):
    """The front of the figure on its center line at a height, or None."""
    return cast_front(z, 0.0)

def cast_front(z, x):
    gone = cast(tree, Vector((cx + x, leg_y - tall, z)), Vector((0, 1, 0)), 2 * tall)
    return None if gone is None else leg_y - tall + gone

if box:
    chin_z = box["min"][2]
    found["chin"] = "the head's box"
else:
    # Up the front of the neck, the chin is where the surface has come most of the way forward to the face.
    fronts = [front_at(z_of(i)) for i in range(NZ)]
    lo_i, hi_i = zi(neck_z), zi(mix(neck_z, top_z, 0.8))
    seen = [f for f in fronts[lo_i:hi_i + 1] if f is not None]
    chin_z = None
    if seen:
        recess, face_front = max(seen), min(seen)
        for i in range(lo_i, hi_i + 1):
            if fronts[i] is not None and fronts[i] == recess:
                lo_i = i
        for i in range(lo_i, hi_i + 1):
            if fronts[i] is not None and fronts[i] < recess - 0.5 * (recess - face_front) and recess - face_front > 0.02 * tall:
                chin_z = z_of(i) - 0.5 * tall / NZ
                break
    if chin_z is None:
        chin_z = top_z - 0.135 * tall
        found["chin"] = "usual proportion"
if box:  # the box's floor is the chin, whatever the neck looked like: a neck can't be above it
    neck_z = min(neck_z, chin_z)
    base_z = min(base_z, neck_z)
else:
    chin_z = clamp(chin_z, neck_z, top_z - 0.04 * tall)

def trunk_middle(z):
    i = zi(z)
    while trunk[i] is None and i > 0:
        i -= 1
    while trunk[i] is None and i < NZ - 1:
        i += 1
    return [cx, (trunk[i][1] + trunk[i][2]) / 2, z]

# ---- the surface itself: rings of distances along the trunk, one arm and hand, one leg and one foot ----
def stations(first, last, count):
    return [mix(first, last, i / (count - 1)) for i in range(count)]

def clips_for(stretch, where):
    """The walls a ring's look must not start behind: what keeps a neighbor out of it."""
    if stretch == "trunk":  # the arms, cut off at the armpit
        if pit_lo - 0.01 * tall <= where[2] <= pit_hi + 0.01 * tall:
            return [(0, 1, cx + pit_x), (0, -1, cx - pit_x)]
        return []
    if stretch == "arm":  # the flank under the armpit
        if where[0] - cx < pit_x + 0.02 * tall:
            return [(2, -1, pit_lo - 0.005 * tall)]
        return []
    if stretch == "leg":  # the other leg
        return [(0, -1, cx)]
    if stretch == "foot":  # the other foot, and the shin above
        return [(0, -1, cx), (2, 1, ankle_z)]
    return []

def settled(where, axis, stretch, reach, flip):
    """A limb is thin, its two sides are never quite alike, and a middle guessed from a few points of both can
    miss it: move the middle to the middle of what a ring there sees, on this side (`flip` for the other)."""
    u, v = [(1, 2), (0, 2), (0, 1)][axis]
    for _ in range(2):
        seen = ring(tree, where, axis, clips_for(stretch, where), reach, flip, True)
        us = [r * math.cos(2 * math.pi * k / AROUND) for k, r in enumerate(seen) if r is not None]
        vs = [r * math.sin(2 * math.pi * k / AROUND) for k, r in enumerate(seen) if r is not None]
        if len(us) < AROUND // 3:
            break
        where = list(where)
        where[u] += (min(us) + max(us)) / 2
        where[v] += (min(vs) + max(vs)) / 2
    return where

def read(places, axis, stretch, reach):
    """Rings at `places` ([x, y, z] each): the left side and the mirrored right, averaged, then mended.
    A ring that saw next to nothing (past the fingertips) is the last good one, drawn in."""
    rows, thin = [], []
    for i, where in enumerate(places):
        loose = stretch == "hand" or (stretch == "arm" and where[0] - cx > pit_x + 0.03 * tall) or (stretch == "leg" and where[2] < crotch - 0.03 * tall)
        other_side = where
        if loose:  # clear of the trunk: each side's ring is read around its own middle
            other_side = settled(where, axis, stretch, reach, (cx,))
            where = places[i] = settled(where, axis, stretch, reach, None)
        clips = clips_for(stretch, where)
        one = ring(tree, where, axis, clips, reach, None, stretch != "trunk")
        if len([r for r in one if r is not None]) < AROUND // 3 and rows:
            thin.append(i)
            rows.append(list(rows[-1]))
            continue
        if axis == 2 and abs(where[0] - cx) < 1e-9:
            other = [one[(AROUND // 2 - k) % AROUND] for k in range(AROUND)]  # the trunk: its own mirror image
        else:
            other = ring(tree, other_side, axis, clips_for(stretch, other_side), reach, (cx,), True)
        rows.append(both(one, other))
    rows = mended(rows)
    for i in thin:
        rows[i] = [0.6 * r for r in rows[i - 1]]
    return rows

trunk_top = mix(chin_z, top_z, 0.3)
places = [trunk_middle(z) for z in stations(crotch - 0.03 * tall, trunk_top, STATIONS["trunk"])]
ys = smooth(smooth([p[1] for p in places]))
places = [[p[0], y, p[2]] for p, y in zip(places, ys)]
trunk_rows = read(places, 2, "trunk", far)
arm_from = max(pit_x - 0.5 * (pit_hi - pit_lo), 0.3 * pit_x)
places = [[cx + m[0], m[1], m[2]] for m in [arm_middle(x) for x in stations(arm_from, wrist_x, STATIONS["arm"])]]
arm_rows = read(places, 0, "arm", 0.3 * tall)
arm_places = places
places = [[cx + m[0], m[1], m[2]] for m in [arm_middle(x) for x in stations(wrist_x, far - 0.002 * tall, STATIONS["hand"])]]
hand_rows = read(places, 0, "hand", 0.25 * tall)
hand_places = places
leg_top = crotch + 0.09 * tall
places = [[cx + m[0], m[1], m[2]] for m in [leg_middle(z) for z in stations(ankle_z - 0.3 * (ankle_z - floor), leg_top, STATIONS["leg"])]]
leg_rows = read(places, 2, "leg", 0.35 * tall)
leg_places = places
def foot_middle(y):
    """The middle of the foot at a spot along it: halfway between its sole and its top there (toes are low, a heel can be off the floor)."""
    top = cast(tree, Vector((cx + foot_x, y, ankle_z)), Vector((0, 0, -1)), ankle_z - floor + 0.01 * tall)
    sole = cast(tree, Vector((cx + foot_x, y, floor - 0.01 * tall)), Vector((0, 0, 1)), ankle_z - floor + 0.01 * tall)
    high = ankle_z - top if top is not None and top > 1e-5 else ankle_z
    low = floor - 0.01 * tall + sole if sole is not None else floor
    if high - low < 0.004 * tall:
        low, high = floor, floor + 0.5 * (ankle_z - floor)
    return [cx + foot_x, y, (low + high) / 2]

places = [foot_middle(y) for y in stations(toe_y + 0.004 * tall, heel_y - 0.004 * tall, STATIONS["foot"])]
foot_rows = read(places, 1, "foot", 0.3 * tall)
foot_places = places

def kept(places, rows, axis):
    u, v = [(1, 2), (0, 2), (0, 1)][axis]
    return [[r4(p[axis]), r4(p[u]), r4(p[v])] + [r4(r) for r in row] for p, row in zip(places, rows)]

scan = {
    "around": AROUND,
    "trunk": kept([trunk_middle(z)[:1] + [y, z] for z, y in zip(stations(crotch - 0.03 * tall, trunk_top, STATIONS["trunk"]), ys)], trunk_rows, 2),
    "arm": kept(arm_places, arm_rows, 0),
    "hand": kept(hand_places, hand_rows, 0),
    "leg": kept(leg_places, leg_rows, 2),
    "foot": kept(foot_places, foot_rows, 1),
}

# ---- the landmarks, as points on the +x side ----
def trunk_point(z):
    row = at(scan["trunk"], z)
    return [r4(cx), row[2], r4(z)]

elbow, wrist = arm_middle(elbow_x), arm_middle(wrist_x)
knee, ankle = leg_middle(knee_z), leg_middle(ankle_z)
tip = arm_middle(far - 0.5 * far / NX)
chin_front = cast_front(chin_z + 0.01 * tall, 0.0)
marks = {
    "top": [cx, trunk_middle(top_z - 0.02 * tall)[1], top_z],
    "chin": [cx, chin_front if chin_front is not None else trunk_middle(chin_z)[1], chin_z],
    "neck": trunk_point(neck_z),
    "neck_base": trunk_point(base_z),
    "shoulder": [cx + pit_x, arm_y, pit_hi],
    "armpit": [cx + pit_x, arm_y, pit_lo],
    "chest": trunk_point(chest_z),
    "waist": trunk_point(waist_z),
    "hips": trunk_point(hips_z),
    "crotch": [cx, leg_y, crotch],
    "elbow": [cx + elbow[0], elbow[1], elbow[2]],
    "wrist": [cx + wrist[0], wrist[1], wrist[2]],
    "fingertip": [cx + far, tip[1], tip[2]],
    "knee": [cx + knee[0], knee[1], knee[2]],
    "ankle": [cx + ankle[0], ankle[1], ankle[2]],
    "heel": [cx + foot_x, heel_y, floor],
    "toe": [cx + foot_x, toe_y, floor],
}
marks = {key: [r4(v) for v in spot] for key, spot in marks.items()}
for key in marks:
    found.setdefault(key, "shape")

sizes = {
    "neck": half_sizes(scan["trunk"], neck_z),
    "shoulders": [r4(pit_x), half_sizes(scan["trunk"], pit_lo)[1]],
    "chest": half_sizes(scan["trunk"], chest_z),
    "waist": half_sizes(scan["trunk"], waist_z),
    "hips": half_sizes(scan["trunk"], hips_z),
    "upper_arm": half_sizes(scan["arm"], mix(pit_x, elbow_x, 0.5) + cx),
    "elbow": half_sizes(scan["arm"], elbow_x + cx),
    "forearm": half_sizes(scan["arm"], mix(elbow_x, wrist_x, 0.3) + cx),
    "wrist": half_sizes(scan["arm"], wrist_x + cx),
    "hand": half_sizes(scan["hand"], mix(wrist_x, far, 0.45) + cx),
    "thigh": half_sizes(scan["leg"], mix(knee_z, crotch, 0.6)),
    "knee": half_sizes(scan["leg"], knee_z),
    "calf": half_sizes(scan["leg"], mix(knee_z, ankle_z, 0.33)),
    "ankle": half_sizes(scan["leg"], ankle_z),
    "foot": [r4((foot_hi - foot_lo) / 2), r4((ankle_z - floor) / 2)],
}
head_tall = top_z - chin_z
hip_half = sizes["hips"][0]
joints = {
    "shoulder": [r4(cx + pit_x - 0.25 * (pit_hi - pit_lo)), r4(arm_y), r4((pit_lo + pit_hi) / 2)],
    "elbow": marks["elbow"],
    "wrist": marks["wrist"],
    "hip": [r4(cx + leg_middle(crotch - 0.01 * tall)[0]), r4(leg_middle(crotch - 0.01 * tall)[1]), r4(crotch + 0.045 * tall)],
    "knee": marks["knee"],
    "ankle": marks["ankle"],
}
proportions = {
    "height_m": r4(tall),
    "heads_tall": round(tall / head_tall, 2),
    "leg_share": round((crotch - floor) / tall, 3),                 # floor to crotch, of the height
    "arm_share": round((far - pit_x) / tall, 3),                    # shoulder to fingertip, of the height
    "forearm_to_upper_arm": round((wrist_x - elbow_x) / max(elbow_x - pit_x, 1e-6), 2),
    "shin_to_thigh": round((knee_z - ankle_z) / max(crotch + 0.045 * tall - knee_z, 1e-6), 2),
    "shoulders_to_hips": round(pit_x / max(hip_half, 1e-6), 2),     # half-widths: over 1 is broad-shouldered
    "waist_to_hips": round(sizes["waist"][0] / max(hip_half, 1e-6), 2),
    "hand_share": round((far - wrist_x) / tall, 3),
    "foot_share": round((heel_y - toe_y) / tall, 3),
    "trunk_share": round((base_z - crotch) / tall, 3),              # crotch to the base of the neck
    "neck_share": round((chin_z - base_z) / tall, 3),
}

name = PARAMS["name"]
stored = {"object": objs[0].name, "height": r4(tall), "floor": r4(floor), "center": r4(cx), "landmarks": marks, "found": found,
          "girth": sizes, "joints": joints, "scan": scan}
if PARAMS["keep"]:
    bpy.context.scene["body: " + name] = json.dumps(stored)

guide = None
old = bpy.data.objects.get("Look: landmarks")
if old:
    bpy.data.objects.remove(old, do_unlink=True)
if PARAMS["show"]:
    guide = "Look: landmarks"
    arm_len = 0.02 * tall
    dots, edges = [], []
    for key, spot in marks.items():
        for flip in ((1,) if abs(spot[0] - cx) < 1e-6 else (1, -1)):
            x = cx + flip * (spot[0] - cx)
            for d in ((arm_len, 0, 0), (0, arm_len, 0), (0, 0, arm_len)):
                dots += [(x - d[0], spot[1] - d[1], spot[2] - d[2]), (x + d[0], spot[1] + d[1], spot[2] + d[2])]
                edges.append((len(dots) - 2, len(dots) - 1))
    me = bpy.data.meshes.new(guide)
    me.from_pydata(dots, edges, [])
    marker = bpy.data.objects.new(guide, me)
    bpy.context.scene.collection.objects.link(marker)
    marker.display_type = "WIRE"
    marker.show_in_front = True
    marker.hide_render = True
    marker.hide_select = True

print("RESULT " + json.dumps({
    "object": objs[0].name,
    "landmarks": marks,
    "found": found,
    "proportions": proportions,
    "girth": sizes,
    "joints": joints,
    "body": {"name": name, "body": name, "detail": "low", "follow": 1.0},
    "kept_as": "body: " + name if PARAMS["keep"] else None,
    "guide": guide,
    "next": "paste \"body\" into build.py's \"parts\" with the head and the gear; look at it next to the reference, and put right any landmark \"found\" by usual proportion",
}))
