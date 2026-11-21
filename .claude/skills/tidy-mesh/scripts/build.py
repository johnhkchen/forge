# Block out a low-poly version from a list of simple pieces, join them into
# one object, and say how far it strays from the detailed mesh. A character's
# gear stays its own group, and it gets the points props attach to.
#
# Each piece has a "name", an optional "color" [r, g, b] (painted flat as
# vertex color), and ONE of these shapes:
#
#   "loft": "z" (or "x", "y")  a stack of rings along that axis, skinned.
#       "rings": [[position, middle, middle, half-width, half-width], ...]
#       exactly the rows measure.py prints. [position, middle, middle, radius]
#       makes a round ring, so a lathe (body, lid, knob) is a loft of those.
#   "tube": [[x, y, z, radius], ...]  a bar swept through those points
#       (spout, handle, arm, tail). [x, y, z, half-width across, half-width
#       along "up"] makes it oval. "up": [0, 0, 1] sets which way is up.
#   "lumps": [[x, y, z, radius], ...]  rough rocks, one per row
#       ([x, y, z, rx, ry, rz] squashes one). "jitter": 0.2, "seed": 1.
#   "box": {"min": [x, y, z], "max": [x, y, z]}
#   "head": "-y"  a head with a face, looking that way ("-y", "+y", "-x",
#       "+x"). Don't write this one by hand: face.py measures the
#       reference's head and prints the whole piece, ready to paste. What it
#       holds, so you can adjust it after looking:
#       "scan"   the name face.py stored the head's surface under, in this
#                scene. With it the head's points are laid on the reference
#                (outline, skull, cheeks, jaw) and the features are cut into
#                that. Without it you get a plain head from "rows" alone.
#       "box"    the head's box. "rows": [height, front of the face there,
#                half-width] for "chin", "mouth", "nose", "eyes", "brow",
#                "top": the heights place the features; front and half-width
#                only shape a head with no "scan"
#       "kind"   "creature" (heavy brow, scowl, broad nose and mouth) or "human"
#       "face"   sizes in meters, all optional: "eye_in" / "eye_out" (inner
#                and outer eye corner, from the center line), "eye_tall",
#                "eye_sunk", "nose_out", "nose_wide" and "mouth_wide" (half
#                widths), "mouth_tall", "underbite" (lower lip ahead of the
#                upper), "scowl" 0-1 (inner brow pulled down), "bold" 1.0
#                (how far brow, nose and sockets stand out; 1.3 reads from
#                farther away)
#       "eyes"   "sunk" (a dark socket, the eye set back in it) or "flat"
#                (one colored face per eye, 16 triangles fewer)
#       "tusks"  {"at": from the center line, "z": where it starts, "long": ,
#                "wide": , "front": how far forward the tip is, "from":
#                "below" or "above"} and "ears": {"long": , "tall": , "up":
#                0-1 (0 sticks out, 1 points up), "z": , "front": }; True
#                takes the defaults
#       "colors" {"skin", "socket", "eye", "mouth", "brow", "nose", "tusk",
#                "ear", "hair", "beard"}: a flat color per region ("hair"
#                covers the top and back, "beard" the jaw and upper lip).
#                Unset ones are shades of the piece's "color".
#       "back": False leaves the back open (a head sunk into the chest);
#       "round": True adds a column around the back (a head seen from
#       behind); "caps": False leaves the underside open. 150 to 240
#       triangles, already mirrored across the face's center line.
#   "body": "body"  a character's whole body with its anatomy, in one piece.
#       Don't write this one by hand either: landmarks.py finds the
#       reference's landmarks, keeps its surface under that name and prints
#       the piece. build.py makes it a trunk (pelvis, waist, ribcage, the
#       slope up to the neck), a neck, and mirrored arms (a shoulder cap,
#       upper arm, forearm, wrist), hands (one finger mass and a thumb), legs
#       (thigh, knee, calf, ankle) and feet (heel, arch, toes), as pieces
#       named "<name> trunk", "<name> arm"...: about 900 triangles, with
#       three rings set close at each elbow and knee, where they bend. What
#       it holds, so you can adjust it after looking:
#       "landmarks"  {"knee": [x, y, z], ...} puts a landmark right
#       "girth"      {"waist": [half-width, half-depth], ...} likewise, for
#                    "neck", "shoulders", "chest", "waist", "hips",
#                    "upper_arm", "elbow", "forearm", "wrist", "hand",
#                    "thigh", "knee", "calf", "ankle", "foot"
#       "follow"     1.0 lays every ring on the kept surface, so it is this
#                    character's own shape; 0 builds what a body usually
#                    has from the landmarks and girths alone; between the
#                    two is a cleaner, evener version of the character
#       "style"      {"chunky": 1.2} thickens trunk and limbs, {"limbs":
#                    0.9} the limbs alone, {"head": 1.15} grows the head
#                    and whatever sits wholly above the chin
#       "under"      {"trunk": 0.012, "leg": 0.012, "foot": 0.03}: draw a
#                    stretch in by that many meters where clothes cover it
#                    ("trunk", "neck", "arm", "hand", "leg", "foot"); or
#                    [[from, to, meters], ...] along it for a part of one
#       "detail"     "low", or "mid": twice the sides, five rings at each
#                    elbow and knee and about twice the rings elsewhere
#                    (the mid-poly rebuild sets this; leave it out)
#       "sides"      {"trunk": 8, "arm": 6, "leg": 6, ...} to spend more or
#                    fewer; "colors": {"trunk": [r, g, b], ...} per stretch;
#                    "thumb": False for a plain mitten
#       "body" may also be {"landmarks": {...}, "girth": {...}} written out,
#       for a body with no reference to read. Its result lists "body":
#       triangles, rings, and "check_these", the landmarks that were
#       guesses. Send the piece again to change it; "remove": ["body"]
#       drops all of it. The recipe keeps the landmarks and joints.
#
# For lofts and tubes:
#   "sides": 8            points around each ring (4 makes a square post)
#   "square": 2           2 = oval; higher is boxier (2.4 for limbs, 4 for a block)
#   "caps": [True, True]  close the first / last ring; False leaves an end
#                         open where it hides inside another piece
#   "closed": True        join the last ring back to the first (a belt or
#                         band: four rings, outer top, outer bottom, inner
#                         bottom, inner top)
#   a ring may end with extras: [z, x, y, rx, ry, {"square": 4, "back": 0.5,
#   "slope": 0.2}]. "back" is a different half-width on the + side of the
#   second across-axis (a belly in front, a flat back); "slope" tilts the
#   ring (a belt that sits lower in front).
#   Add a ring where something bends (elbow, knee) to give it an edge loop.
# Any piece: "mirror": True also builds its twin across x = 0.
#   "finer": 1 splits every face of the piece in four, rounding as it goes
#   (the mid-poly rebuild does this to heads; leave it out of a block-out).
#
# Gear comes off. On a character, a piece of clothing, armor or equipment
# says which gear item it is: "gear": "wool singlet" (a name from the brief's
# gear list; pass that list once as PARAMS["gear"]). Pieces without "gear"
# are the body, and the body is built whole underneath: take the coat away
# and there is a chest, not a hole. In the scene it is still one object to
# look at and check; export.py writes it as one mesh per group, named "body",
# "gear: wool singlet"..., each gear mesh tagged with its kind and slot.
#
# "sockets": True adds the points a game hangs props on, as empties named
# "socket: hand_right", "socket: hand_left" (the middle of each palm),
# "socket: head" (top of the head), "socket: back" (between the shoulder
# blades) and "socket: hip" (the left hip, where a sheath hangs). They are
# worked out from the body pieces of a T-pose facing -y, so the right hand
# is the one at -x. Read them in the result; move one that landed wrong
# with "sockets": {"head": [x, y, z]}.
#
# Pieces stay in the scene, hidden, so the next call only needs the pieces
# that change ("parts") or go ("remove"); everything is joined again each time.
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down
# (these comments can stay behind). Prints RESULT {json}. 1-3 s.
# Safe-mode compatible.

PARAMS = {
    "reference": None,  # the detailed mesh to build around; None = the largest visible mesh
    "name": None,       # the joined object's name; None = "<reference> (light)"
    "parts": [],        # pieces to add or replace, by name
    "remove": [],       # names of pieces to drop
    "shading": "flat",  # "flat" (faceted) or "smooth"
    "crease": None,     # with "smooth": edges bent more than this many degrees stay crisp
    "gear": None,       # the brief's gear list, [{"name": , "kind": , "slot": }]; None = as last time
    "sockets": None,    # True = add attachment points; {"head": [x, y, z]} moves one; False = none; None = as last time
    "check": 8000,      # points to sample for the shape check; 0 = skip it
}

import bpy
import bmesh
import json
import math
import random
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ACROSS = {"x": (0, 1, 2), "y": (1, 0, 2), "z": (2, 0, 1)}


def face_count(obj):
    return len(obj.data.polygons)

def extras(row):
    return row[-1] if isinstance(row[-1], dict) else {}

def numbers(row):
    return [v for v in row if not isinstance(v, dict)]

def outline(sides, square, turn):
    """Unit ring: `sides` points of a rounded square, scaled to span -1..1 both ways."""
    pts = []
    for k in range(sides):
        t = math.pi / sides + math.radians(turn) + 2 * math.pi * k / sides
        c, s = math.cos(t), math.sin(t)
        pts.append((math.copysign(abs(c) ** (2 / square), c), math.copysign(abs(s) ** (2 / square), s)))
    wide = max(abs(p[0]) for p in pts)
    tall = max(abs(p[1]) for p in pts)
    return [(p[0] / wide, p[1] / tall) for p in pts]

def loft_rings(part):
    a, u, v = ACROSS[part["loft"]]
    rings = []
    for row in part["rings"]:
        n, more = numbers(row), extras(row)
        ru, rv = n[3], n[4] if len(n) > 4 else n[3]
        ring = []
        if more.get("points"):  # the ring's own outline, as offsets from its middle (a "body" piece writes these)
            for du, dv in more["points"]:
                p = [0.0, 0.0, 0.0]
                p[a], p[u], p[v] = n[0], n[1] + du, n[2] + dv
                ring.append(Vector(p))
            rings.append(ring)
            continue
        for pu, pv in outline(part.get("sides", 8), more.get("square", part.get("square", 2)), part.get("turn", 0)):
            reach = pv * (more.get("back", rv) if pv > 0 else rv)
            p = [0.0, 0.0, 0.0]
            p[a], p[u], p[v] = n[0] + more.get("slope", 0) * reach, n[1] + pu * ru, n[2] + reach
            ring.append(Vector(p))
        rings.append(ring)
    return rings

def tube_rings(part):
    rows = part["tube"]
    pts = [Vector(numbers(r)[:3]) for r in rows]
    last = len(pts) - 1
    side = None
    rings = []
    for i, row in enumerate(rows):
        n, more = numbers(row), extras(row)
        if part.get("closed"):
            ahead = pts[(i + 1) % len(pts)] - pts[i - 1]
        else:
            ahead = pts[min(i + 1, last)] - pts[max(i - 1, 0)]
        ahead.normalize()
        if side is None:
            side = Vector(part.get("up", (0, 0, 1))).cross(ahead)
            if side.length < 1e-6:
                side = Vector((1, 0, 0)).cross(ahead) if abs(ahead.x) < 0.9 else Vector((0, 1, 0)).cross(ahead)
        side = (side - ahead * side.dot(ahead)).normalized()  # carried along the path, so it never flips
        top = ahead.cross(side)
        ru, rv = n[3], n[4] if len(n) > 4 else n[3]
        shape = outline(part.get("sides", 6), more.get("square", part.get("square", 2)), part.get("turn", 0))
        rings.append([pts[i] + side * (pu * ru) + top * (pv * rv) for pu, pv in shape])
    return rings

def skin(rings, caps, closed):
    n = len(rings[0])
    verts = [p for ring in rings for p in ring]
    faces = []
    for i in range(len(rings) if closed else len(rings) - 1):
        a, b = i * n, ((i + 1) % len(rings)) * n
        faces += [(a + j, a + (j + 1) % n, b + (j + 1) % n, b + j) for j in range(n)]
    if not closed and caps[0]:
        faces.append(tuple(reversed(range(n))))
    if not closed and caps[1]:
        faces.append(tuple(range(len(verts) - n, len(verts))))
    # Face outward: on the first two rings, the sides should point away from the middle.
    middle = sum(verts[:2 * n], Vector()) / (2 * n)
    out = 0.0
    for f in faces[:n]:
        a, b, c, d = [verts[i] for i in f]
        out += (c - a).cross(d - b).dot((a + b + c + d) / 4 - middle)
    if out < 0:
        faces = [tuple(reversed(f)) for f in faces]
    return verts, faces

def lumps(part):
    rng = random.Random(part.get("seed", 1))
    jitter = part.get("jitter", 0.2)
    verts, faces = [], []
    for row in part["lumps"]:
        size = row[3:6] if len(row) > 5 else [row[3]] * 3
        ball = bmesh.new()
        bmesh.ops.create_icosphere(ball, subdivisions=part.get("detail", 1), radius=1.0)
        start = len(verts)
        verts += [Vector([row[i] + v.co[i] * size[i] * (1 + jitter * (2 * rng.random() - 1)) for i in range(3)]) for v in ball.verts]
        faces += [tuple(start + v.index for v in f.verts) for f in ball.faces]
        if part.get("mirror") and abs(row[0]) > size[0] * 0.1:  # one on the center line has no twin
            twin = len(verts)
            verts += [Vector((-p.x, p.y, p.z)) for p in verts[start:twin]]
            faces += [tuple(reversed([twin - start + i for i in f])) for f in faces[-len(ball.faces):]]
        ball.free()
    return verts, faces

def box(part):
    lo, hi = part["box"]["min"], part["box"]["max"]
    verts = [Vector((x, y, z)) for z in (lo[2], hi[2]) for y in (lo[1], hi[1]) for x in (lo[0], hi[0])]
    return verts, [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]

# ---- a body with anatomy: one "body" piece becomes a trunk, a neck, arms, hands, legs and feet ----

BODY_SIDES = {"low": {"trunk": 8, "neck": 6, "arm": 6, "hand": 6, "thumb": 4, "leg": 6, "foot": 6},
              "mid": {"trunk": 16, "neck": 10, "arm": 12, "hand": 8, "thumb": 6, "leg": 12, "foot": 10}}
BODY_FILL = {"trunk": 20, "neck": 4, "arm": 17, "hand": 7, "leg": 19, "foot": 9}  # mid poly: about this many rings along each stretch
BODY_TURN = {"hand": 30, "foot": 30}  # six-sided hands and feet lie flat: a face under the sole and the palm, not a ridge
BODY_AXIS = {"trunk": "z", "neck": "z", "arm": "x", "hand": "x", "leg": "z", "foot": "y"}
BODY_CAPS = {"trunk": [True, True], "neck": [False, False], "arm": [False, True], "hand": [False, True], "leg": [True, False], "foot": [True, True]}
BODY_MARKS = ("top", "chin", "neck", "neck_base", "shoulder", "armpit", "chest", "waist", "hips", "crotch", "elbow", "wrist", "fingertip", "knee", "ankle", "heel", "toe")
BODY_GIRTHS = ("neck", "shoulders", "chest", "waist", "hips", "upper_arm", "elbow", "forearm", "wrist", "hand", "thigh", "knee", "calf", "ankle", "foot")

def oval_reach(t, wide, low, high, square):
    """How far a rounded oval reaches at angle t: half-width `wide`, half-depth `low` toward -v and `high` toward +v."""
    c, s = math.cos(t), math.sin(t)
    deep = high if s > 0 else low
    return (abs(c / wide) ** square + abs(s / deep) ** square) ** (-1.0 / square)

def kept_reach(radii, t):
    """How far a kept ring (landmarks.py's distances, evenly around) reaches at angle t."""
    x = (t % (2 * math.pi)) / (2 * math.pi) * len(radii)
    i = int(x) % len(radii)
    return mix(radii[i], radii[(i + 1) % len(radii)], x - int(x))

def kept_row(rows, pos):
    """A kept surface's ring at a position along its stretch: [middle, middle, distances...], eased between the two nearest."""
    if pos <= rows[0][0]:
        return rows[0][1:]
    for a, b in zip(rows, rows[1:]):
        if pos <= b[0]:
            t = (pos - a[0]) / max(b[0] - a[0], 1e-9)
            return [mix(p, q, t) for p, q in zip(a[1:], b[1:])]
    return rows[-1][1:]

def body_ring(pos, shape, rows, follow, sides, turn, grow, inset):
    """One ring of a body stretch, as a loft row. `shape` is what a body usually has there: [middle, middle,
    half-width, half-depth toward -v, half-depth toward +v, squareness, where to read the kept surface (None =
    here; False = not at all)]. `rows` is the kept surface (or None), followed by `follow` (1 = all the way).
    The ring's corners are pushed out to the shape's true width and depth, so a six-sided limb is as wide
    from the front and as deep from the side as the round one it stands for."""
    cu, cv, wide, low, high, square, read_at = shape
    kept = None
    if rows and follow > 0 and read_at is not False:
        row = kept_row(rows, pos if read_at is None else read_at)
        cu, cv, kept = mix(cu, row[0], follow), mix(cv, row[1], follow), row[2:]
    fine, corners = [], []
    for i in range(48 + sides):
        t = 2 * math.pi * i / 48 if i < 48 else math.pi / sides + math.radians(turn) + 2 * math.pi * (i - 48) / sides
        reach = oval_reach(t, wide, low, high, square)
        if kept:
            reach = mix(reach, kept_reach(kept, t), follow)
        (fine if i < 48 else corners).append((reach * math.cos(t), reach * math.sin(t)))
    true = [max(p[0] for p in fine), -min(p[0] for p in fine), max(p[1] for p in fine), -min(p[1] for p in fine)]
    have = [max(p[0] for p in corners), -min(p[0] for p in corners), max(p[1] for p in corners), -min(p[1] for p in corners)]
    size = (true[0] + true[1] + true[2] + true[3]) / 4
    scale = max(0.4, grow - inset / max(size, 1e-6))
    points = []
    for du, dv in corners:
        du *= true[0] / max(have[0], 1e-9) if du > 0 else true[1] / max(have[1], 1e-9)
        dv *= true[2] / max(have[2], 1e-9) if dv > 0 else true[3] / max(have[3], 1e-9)
        points.append((du * scale, dv * scale))
    # Re-center on the ring's own box, so the middle and half-sizes written in the row are true (rig.py reads those).
    mu, mv = (true[0] - true[1]) / 2 * scale, (true[2] - true[3]) / 2 * scale
    return [round(pos, 4), round(cu + mu, 4), round(cv + mv, 4), round((true[0] + true[1]) / 2 * scale, 4), round((true[2] + true[3]) / 2 * scale, 4),
            {"points": [[round(du - mu, 4), round(dv - mv, 4)] for du, dv in points]}]

def drawn_in(told, pos):
    """How far a stretch is drawn in under clothes at a position: one number for all of it, or [[from, to, how far], ...]."""
    if isinstance(told, (int, float)):
        return told
    return max([span[2] for span in told if span[0] <= pos <= span[1]] or [0.0])

def filled(keys, count):
    """Key rings [[position, shape], ...] with more eased in between, evenly inside each gap, until there are about `count`."""
    step = (keys[-1][0] - keys[0][0]) / max(count - 1, 1)
    out = []
    for a, b in zip(keys, keys[1:]):
        out.append(a)
        extra = int((b[0] - a[0]) / step - 0.35)
        for i in range(1, extra + 1):
            t = i / (extra + 1)
            shape = [mix(p, q, t) for p, q in zip(a[1][:6], b[1][:6])]
            out.append([mix(a[0], b[0], t), shape + [a[1][6] if a[1][6] == b[1][6] else None]])
    out.append(keys[-1])
    return out

def climbing(keys, least):
    """Key rings in order along the stretch, dropping any that would sit on (or behind) the one before."""
    out = []
    for key in sorted(keys, key=first):
        if not out or key[0] - out[-1][0] >= least:
            out.append(key)
    return out

def body_parts(part, scene):
    """The pieces a "body" piece stands for: lofts named "<name> trunk", "<name> neck", "<name> arm"..., rings
    placed by the landmarks (three close together at each elbow and knee, so they bend), shaped like a body
    (ribcage, waist, pelvis, a shoulder cap, calf, heel and toes) and, where landmarks.py kept the surface,
    like this character's own. See the notes at the top."""
    name = part["name"]
    told = part["body"]
    if isinstance(told, str):
        stored = scene.get("body: " + told)
        if not stored:
            raise ValueError("body %r: this scene has no body named %r: run landmarks.py first (\"name\": %r), or give \"body\" the landmarks and girths yourself"
                             % (name, told, told))
        told = json.loads(stored)
    marks = dict(told.get("landmarks", {}), **part.get("landmarks", {}))
    girth = dict(told.get("girth", {}), **part.get("girth", {}))
    missing = [k for k in BODY_MARKS if k not in marks] + ["girth " + k for k in BODY_GIRTHS if k not in girth]
    if missing:
        raise ValueError("body %r needs %s (landmarks.py prints them all)" % (name, ", ".join(missing)))
    kept = told.get("scan") or {}
    center, floor = told.get("center", 0.0), told.get("floor", min(marks["heel"][2], marks["toe"][2]))
    tall = told.get("height") or marks["top"][2] - floor
    if abs(center) > 0.02 * tall:
        raise ValueError("body %r: the figure stands %.2f m off x = 0, and a body is built mirrored across it: center it first" % (name, center))
    detail = part.get("detail", "low")
    if detail not in BODY_SIDES:
        raise ValueError("body %r: \"detail\" is \"low\" or \"mid\", not %r" % (name, detail))
    follow = min(1.0, max(0.0, part.get("follow", 1.0))) if kept else 0.0
    style = part.get("style", {})
    chunky = style.get("chunky", 1.0)
    limbs = chunky * style.get("limbs", 1.0)
    under = part.get("under", {})
    sides = dict(BODY_SIDES[detail], **part.get("sides", {}))
    step = 0.008 * tall

    # What a body usually has at each ring: [position, [middle, middle, half-width, toward -v, toward +v, squareness, read at]].
    crotch, hips, waist, chest = marks["crotch"][2], marks["hips"][2], marks["waist"][2], marks["chest"][2]
    pit, top = marks["armpit"], marks["shoulder"]
    base, neck, chin, crown = marks["neck_base"][2], marks["neck"][2], marks["chin"][2], marks["top"][2]
    hips = max(hips, crotch + 2 * step)
    waist = max(waist, hips + 2 * step)
    chest = max(chest, waist + 2 * step)
    high = max(mix(pit[2], top[2], 0.8), chest + 4 * step)  # the shoulder line
    span = high - chest
    base = max(base, top[2] + 2 * step, high + 2 * step)
    neck = max(neck, base)
    back = [marks[k][1] for k in ("hips", "waist", "chest", "neck_base", "neck")]  # the trunk's middle, front to back, at each
    w_hip, d_hip = girth["hips"]
    w_waist, d_waist = girth["waist"]
    w_chest, d_chest = girth["chest"]
    w_sh, d_sh = girth["shoulders"]
    w_neck, d_neck = girth["neck"]
    trunk = [
        [crotch, [0, back[0], 0.55 * w_hip, 0.7 * d_hip, 0.75 * d_hip, 2.3, False]],  # between the legs
        [hips, [0, back[0], w_hip, 0.95 * d_hip, 1.1 * d_hip, 2.4, None]],  # the pelvis at its widest, glutes behind
        [mix(hips, waist, 0.55), [0, mix(back[0], back[1], 0.55), mix(w_hip, w_waist, 0.6), mix(d_hip, d_waist, 0.6), mix(d_hip, d_waist, 0.5), 2.3, None]],
        [waist, [0, back[1], w_waist, d_waist, d_waist, 2.2, None]],
        [mix(waist, chest, 0.5), [0, mix(back[1], back[2], 0.5), mix(w_waist, w_chest, 0.6), mix(d_waist, d_chest, 0.6), mix(d_waist, d_chest, 0.6), 2.4, None]],
        [chest, [0, back[2], w_chest, 1.06 * d_chest, d_chest, 2.6, None]],  # the ribcage at its deepest
        [chest + 0.33 * span, [0, mix(back[2], back[3], 0.2), w_sh, d_sh, d_sh, 2.8, None]],  # the upper chest, and the shoulder blades behind
        [chest + 0.67 * span, [0, mix(back[2], back[3], 0.4), w_sh, 0.95 * d_sh, d_sh, 2.7, None]],
        [high, [0, mix(back[2], back[3], 0.6), 0.98 * w_sh, 0.85 * d_sh, 0.95 * d_sh, 2.6, None]],  # the shoulder line
        [mix(high, base, 0.5), [0, mix(back[2], back[3], 0.85), mix(w_sh, 1.4 * w_neck, 0.65), 0.7 * d_sh, 0.85 * d_sh, 2.2, None]],  # the slope up to the neck
        [base, [0, back[3], 1.4 * w_neck, 1.2 * d_neck, 1.3 * d_neck, 2.0, None]],
    ]
    head_tall = max(crown - chin, 0.05 * tall)
    throat = [
        [base - 0.03 * tall, [0, back[3], 1.25 * w_neck, 1.15 * d_neck, 1.2 * d_neck, 2.0, mix(base, neck, 0.5)]],
        [mix(base, neck, 0.5), [0, mix(back[3], back[4], 0.5), 1.1 * w_neck, 1.05 * d_neck, 1.1 * d_neck, 2.0, None]],
        [max(neck, base + step), [0, back[4], w_neck, d_neck, d_neck, 2.0, neck]],
        [max(chin + 0.25 * head_tall, neck + 2 * step), [0, back[4], w_neck, d_neck, d_neck, 2.0, neck]],  # up inside the head
    ]
    elbow, wrist, tip = marks["elbow"], marks["wrist"], marks["fingertip"]
    d_up, h_up = girth["upper_arm"]
    d_el, h_el = girth["elbow"]
    d_fo, h_fo = girth["forearm"]
    d_wr, h_wr = girth["wrist"]
    d_ha, h_ha = girth["hand"]
    arm_y, arm_z = (pit[1] + top[1]) / 2, (pit[2] + top[2]) / 2
    # How far the elbow's outer loops sit from its middle. The rings next along stay four times as far off, so the
    # three read as one joint (rig.py takes rings set closer than the rest for where a limb bends).
    bend = min(0.5 * h_el, 0.09 * (elbow[0] - pit[0]), 0.09 * (wrist[0] - elbow[0]))
    arm = [
        [pit[0] - 0.8 * h_up, [arm_y, arm_z, 1.05 * d_up, 1.1 * h_up, 1.15 * h_up, 2.2, None]],  # inside the trunk
        [pit[0] + 0.02 * (elbow[0] - pit[0]), [arm_y, arm_z, 1.1 * d_up, 1.02 * h_up, 1.2 * h_up, 2.2, None]],  # the shoulder cap
        [min(mix(pit[0], elbow[0], 0.5), elbow[0] - 4 * bend), [mix(arm_y, elbow[1], 0.5), mix(arm_z, elbow[2], 0.5), d_up, h_up, 1.04 * h_up, 2.1, None]],  # the upper arm's belly
        [elbow[0] - bend, [elbow[1], elbow[2], 1.02 * d_el, 1.02 * h_el, 1.02 * h_el, 2.1, None]],
        [elbow[0], [elbow[1], elbow[2], d_el, h_el, h_el, 2.1, None]],
        [elbow[0] + bend, [elbow[1], elbow[2], mix(d_el, d_fo, 0.4), mix(h_el, h_fo, 0.4), mix(h_el, h_fo, 0.4), 2.1, None]],
        [max(mix(elbow[0], wrist[0], 0.33), elbow[0] + 4 * bend), [mix(elbow[1], wrist[1], 0.33), mix(elbow[2], wrist[2], 0.33), d_fo, h_fo, h_fo, 2.1, None]],  # the forearm's belly
        [mix(elbow[0], wrist[0], 0.7), [mix(elbow[1], wrist[1], 0.7), mix(elbow[2], wrist[2], 0.7), mix(d_fo, d_wr, 0.6), mix(h_fo, h_wr, 0.6), mix(h_fo, h_wr, 0.6), 2.2, None]],
        [wrist[0], [wrist[1], wrist[2], d_wr, h_wr, h_wr, 2.3, None]],
    ]
    long = tip[0] - wrist[0]
    hand = [
        [wrist[0], [wrist[1], wrist[2], d_wr, h_wr, h_wr, 2.3, None]],
        [wrist[0] + 0.2 * long, [mix(wrist[1], tip[1], 0.2), mix(wrist[2], tip[2], 0.2), 0.95 * d_ha, h_ha, h_ha, 3.0, None]],  # the heel of the hand
        [wrist[0] + 0.5 * long, [mix(wrist[1], tip[1], 0.5), mix(wrist[2], tip[2], 0.5), d_ha, 0.9 * h_ha, 0.9 * h_ha, 3.0, None]],  # the knuckles
        [wrist[0] + 0.8 * long, [mix(wrist[1], tip[1], 0.8), mix(wrist[2], tip[2], 0.8), 0.85 * d_ha, 0.6 * h_ha, 0.6 * h_ha, 3.0, None]],  # the fingers, as one mass
        [wrist[0] + 0.99 * long, [tip[1], tip[2], 0.5 * d_ha, 0.35 * h_ha, 0.35 * h_ha, 3.0, wrist[0] + 0.93 * long]],
    ]
    knee, ankle = marks["knee"], marks["ankle"]
    w_th, d_th = girth["thigh"]
    w_kn, d_kn = girth["knee"]
    w_ca, d_ca = girth["calf"]
    w_an, d_an = girth["ankle"]
    fold = min(0.5 * d_kn, 0.09 * (knee[2] - ankle[2]), 0.09 * (crotch - knee[2]))  # the same for the knee
    hip_x = mix(knee[0], 0.5 * w_hip, 0.8)
    leg = [
        [ankle[2], [ankle[0], ankle[1], w_an, d_an, d_an, 2.2, None]],
        [mix(ankle[2], knee[2], 0.32), [mix(ankle[0], knee[0], 0.32), mix(ankle[1], knee[1], 0.32), mix(w_an, w_ca, 0.6), mix(d_an, d_ca, 0.55), mix(d_an, d_ca, 0.7), 2.1, None]],
        [min(mix(ankle[2], knee[2], 0.67), knee[2] - 4 * fold), [mix(ankle[0], knee[0], 0.67), mix(ankle[1], knee[1], 0.67), w_ca, 0.92 * d_ca, 1.12 * d_ca, 2.1, None]],  # the calf, fullest behind
        [knee[2] - fold, [knee[0], knee[1], mix(w_kn, w_ca, 0.3), d_kn, 0.95 * d_kn, 2.2, None]],
        [knee[2], [knee[0], knee[1], w_kn, 1.06 * d_kn, 0.94 * d_kn, 2.3, None]],  # the knee, its cap in front
        [knee[2] + fold, [knee[0], knee[1], mix(w_kn, w_th, 0.3), mix(d_kn, d_th, 0.3), mix(d_kn, d_th, 0.3), 2.2, None]],
        [max(mix(knee[2], crotch, 0.55), knee[2] + 4 * fold), [mix(knee[0], hip_x, 0.55), knee[1], w_th, 1.02 * d_th, d_th, 2.1, None]],  # the thigh
        [crotch - 0.01 * tall, [hip_x, mix(knee[1], back[0], 0.7), 1.12 * w_th, 1.05 * d_th, 1.12 * d_th, 2.2, None]],
        [crotch + 0.07 * tall, [0.5 * w_hip, back[0], 0.5 * w_hip, 0.85 * d_hip, 0.95 * d_hip, 2.3, None]],  # up inside the pelvis
    ]
    heel, toe = marks["heel"], marks["toe"]
    span, w_ft, rise = heel[1] - toe[1], girth["foot"][0], ankle[2] - floor
    foot = []
    for share, wide, bottom, peak in ((0.01, 0.55, 0.0, 0.24), (0.15, 0.9, 0.0, 0.34), (0.33, 1.0, 0.0, 0.44),   # the toes, and the ball of the foot
                                      (0.58, 0.8, 0.06, 0.8), (0.8, 0.72, 0.0, 1.0), (0.99, 0.5, 0.05, 0.55)):  # the arch, under the ankle, the heel
        low, high = floor + bottom * rise, floor + peak * rise
        foot.append([toe[1] + share * span, [toe[0], (low + high) / 2, wide * w_ft, (high - low) / 2, (high - low) / 2, 3.0, None]])
    if detail == "mid":  # five loops at each elbow and knee, one more on the shoulder
        arm += [[elbow[0] - 0.5 * bend, list(arm[3][1])], [elbow[0] + 0.5 * bend, list(arm[5][1])],
                [pit[0] + 0.16 * (elbow[0] - pit[0]), [mix(arm_y, elbow[1], 0.16), mix(arm_z, elbow[2], 0.16), 1.05 * d_up, h_up, 1.18 * h_up, 2.2, None]]]
        leg += [[knee[2] - 0.5 * fold, list(leg[3][1])], [knee[2] + 0.5 * fold, list(leg[5][1])]]
    stretches = {"trunk": trunk, "neck": throat, "arm": arm, "hand": hand, "leg": leg, "foot": foot}

    color = list(part.get("color", (0.6, 0.6, 0.6)))[:3]
    colors = part.get("colors", {})
    made, rings = [], {}
    for key in ("trunk", "neck", "arm", "hand", "leg", "foot"):
        keys = climbing(stretches[key], 0.3 * step if key == "foot" else step)
        if detail == "mid":  # and rings eased in along every stretch
            keys = climbing(filled(keys, BODY_FILL[key]), 0.3 * step)
        rows = kept.get("trunk" if key == "neck" else key)
        grow = chunky if key in ("trunk", "neck") else limbs
        turn = BODY_TURN.get(key, 0) if sides[key] == 6 else 0
        loft = [body_ring(pos, shape, rows, follow, sides[key], turn, grow, drawn_in(under.get(key, 0.0), pos)) for pos, shape in keys]
        piece = {"name": "%s %s" % (name, key), "of": name, "stretch": key, "loft": BODY_AXIS[key], "sides": sides[key], "rings": loft,
                 "color": list(colors.get(key, color))[:3], "caps": BODY_CAPS[key]}
        if key not in ("trunk", "neck"):
            piece["mirror"] = True
        made.append(piece)
        rings[key] = len(loft)
    if part.get("thumb", True):  # a block for the thumb, forward of the palm
        y, z = hand[1][1][0], hand[1][1][1]
        thick = 0.3 * d_ha * limbs
        made.append({"name": name + " thumb", "of": name, "stretch": "thumb", "sides": sides["thumb"], "mirror": True, "color": list(colors.get("hand", color))[:3], "up": [0, 0, 1], "caps": [False, True],
                     "tube": [[round(wrist[0] + 0.2 * long, 4), round(y - 0.5 * d_ha, 4), round(z - 0.15 * h_ha, 4), round(1.1 * thick, 4), round(0.9 * h_ha, 4)],
                              [round(wrist[0] + 0.38 * long, 4), round(y - d_ha - 0.1 * long, 4), round(z - 0.3 * h_ha, 4), round(thick, 4), round(0.8 * h_ha, 4)],
                              [round(wrist[0] + 0.52 * long, 4), round(y - d_ha - 0.2 * long, 4), round(z - 0.4 * h_ha, 4), round(0.6 * thick, 4), round(0.5 * h_ha, 4)]]})
    # The first piece carries what the whole body was asked for and built from; the recipe keeps it (see the end of this file).
    made[0]["body"] = {"spec": part, "landmarks": marks, "joints": told.get("joints"), "found": told.get("found"), "rings": rings,
                       "loops": {"elbow": 5 if detail == "mid" else 3, "knee": 5 if detail == "mid" else 3},
                       "kept": {"name": part["body"], "data": told} if isinstance(part["body"], str) else None}
    return made

FACING ={"-y": (1, -1.0), "+y": (1, 1.0), "-x": (0, -1.0), "+x": (0, 1.0)}
# What a face needs to read at this size, as shares of the head's height or of a row's half-width.
KINDS = {
    "creature": {"brow": 0.08, "scowl": 0.5, "nose_wide": 0.3, "mouth_wide": 0.62, "ear_long": 0.24, "ear_up": 0.6},
    "human": {"brow": 0.03, "scowl": 0.0, "nose_wide": 0.16, "mouth_wide": 0.42, "ear_long": 0.1, "ear_up": 0.15},
}

def mix(a, b, t):
    return a + (b - a) * t

def tone(color, by):
    return [min(1.0, c * by) for c in color[:3]]

def facing_out(verts, faces):
    """The faces, wound so they point away from the middle of the shape."""
    middle = sum(verts, Vector()) / len(verts)
    out = 0.0
    for f in faces:
        pts = [verts[i] for i in f]
        normal = (pts[1] - pts[0]).cross(pts[2] - pts[0]) if len(pts) == 3 else (pts[2] - pts[0]).cross(pts[3] - pts[1])
        out += normal.dot(sum(pts, Vector()) / len(pts) - middle)
    return faces if out >= 0 else [tuple(reversed(f)) for f in faces]

def spike(base, tip):
    """An open cone from a ring of base points to a tip: an ear or a tusk."""
    verts = list(base) + [tip]
    return verts, [(i, (i + 1) % len(base), len(base)) for i in range(len(base))]

def scan_row(zs, z):
    """Which two stored rows `z` lies between, and how far along."""
    r = 0
    while r < len(zs) - 2 and zs[r + 1] < z:
        r += 1
    return r, min(1.0, max(0.0, (z - zs[r]) / (zs[r + 1] - zs[r])))

def scan_at(scan, side, s, z):
    """The measured surface ("front" or "back") at `s` from the center line and height `z`: how far
    forward it is, or None where face.py saw nothing. Past the head's edge it gives the edge."""
    r, t = scan_row(scan["zs"], z)
    lanes = len(scan[side][0])
    x = min(max(s / scan["half"] * lanes - 0.5, 0.0), lanes - 1.0)
    found = []
    for row in (scan[side][r], scan[side][r + 1]):
        i = int(x)
        while i > 0 and row[i] is None:
            i -= 1
        j = min(i + 1, lanes - 1)
        found.append(row[i] if i < int(x) or row[i] is None or row[j] is None else mix(row[i], row[j], x - i))
    if None in found:
        return found[0] if found[1] is None else found[1]
    return mix(found[0], found[1], t)

def head(part):
    """A head with a face, from where the features sit (see the notes at the top).
    Built as a grid, rows going up and columns going from the middle of the face
    around to the back of the skull; a feature is a few grid points pushed in or
    out and a few cells painted. Returns points, faces and a color per face."""
    a, sign = FACING[part["head"]]
    u = 1 - a
    lo, hi = part["box"]["min"], part["box"]["max"]
    back = min(sign * lo[a], sign * hi[a])
    given = part.get("rows", {})
    order = ("chin", "mouth", "nose", "eyes", "brow", "top")
    missing = [k for k in order if k not in given]
    if missing:
        raise ValueError("head %r: rows needs %s (face.py prints them all)" % (part.get("name"), ", ".join(missing)))
    chin, mouth, nose, eyes, brow, top = [(given[k][0], sign * given[k][1], given[k][2]) for k in order]
    if not chin[0] < mouth[0] < nose[0] < eyes[0] < brow[0] < top[0]:
        raise ValueError("head %r: rows must climb: chin < mouth < nose < eyes < brow < top" % part.get("name"))
    if min(r[1] for r in (chin, mouth, nose, eyes, brow, top)) <= back:
        raise ValueError("head %r: the box must reach behind the face (its back is in front of a row)" % part.get("name"))
    scan = None
    if part.get("scan"):
        stored = bpy.context.scene.get("face: " + part["scan"])
        if not stored:
            raise ValueError("head %r: this scene has no measured surface named %r: run face.py first, or drop \"scan\" for a plain head"
                             % (part.get("name"), part["scan"]))
        scan = json.loads(stored)
    kind = KINDS[part.get("kind", "creature")]
    face = part.get("face", {})
    tall = max(hi[2], top[0]) - chin[0]
    bold = face.get("bold", 1.0)
    step = 0.015 * tall

    # Sizes: the measured ones, but never so small the feature disappears.
    eye_out = min(face.get("eye_out", 0.72 * eyes[2]), 0.8 * eyes[2])
    eye_in = min(max(face.get("eye_in", 0.22 * eyes[2]), 0.12 * eyes[2]), eye_out - 0.3 * eyes[2])
    eye_tall = min(max(face.get("eye_tall", 0), 0.14 * tall), 0.8 * (brow[0] - nose[0]))
    eye_sunk = max(face.get("eye_sunk", 0), 0.035 * tall) * bold
    nose_out = max(face.get("nose_out", 0), 0.07 * tall) * bold
    nose_wide = min(max(face.get("nose_wide", kind["nose_wide"] * nose[2]), 0.1 * nose[2]), 0.45 * nose[2])
    mouth_wide = min(max(face.get("mouth_wide", kind["mouth_wide"] * mouth[2]), 0.3 * mouth[2]), 0.75 * mouth[2])
    mouth_tall = max(face.get("mouth_tall", 0), 0.045 * tall)
    under = face.get("underbite", 0.0)
    scowl = face.get("scowl", kind["scowl"])

    # Rows, bottom to top: [height, front, half-width, first column, second column].
    z_low, z_high = mouth[0] - mouth_tall / 2, mouth[0] + mouth_tall / 2
    z_under = mix(z_high, nose[0], 0.55)
    z_lid = eyes[0] - eye_tall / 2
    z_edge = min(eyes[0] + eye_tall / 2, max(brow[0], eyes[0] + step))
    z_ridge = mix(max(brow[0], z_edge), top[0], 0.4)
    cheek = mix(nose[1], brow[1], min(1.0, max(0.0, (z_lid - nose[0]) / (brow[0] - nose[0]))))
    ledge = max(brow[1], cheek + kind["brow"] * tall * bold)
    k = 1 / eyes[2]
    rings = [
        [min(lo[2], chin[0] - 0.08 * tall), mix(back, chin[1], 0.55), 0.7 * chin[2], 0.3 * chin[2], 0.5 * chin[2]],
        [chin[0], chin[1], chin[2], 0.45 * mouth_wide, 0.9 * mouth_wide],
        [z_low, mouth[1] + under, mouth[2], 0.5 * mouth_wide, mouth_wide],
        [z_high, mouth[1], mouth[2], 0.5 * mouth_wide, mouth_wide],
        [z_under, nose[1], nose[2], nose_wide, max(eye_out * k * nose[2], nose_wide + 0.15 * nose[2])],
        [z_lid, cheek, eyes[2], eye_in, eye_out],
        [z_edge, ledge, mix(eyes[2], brow[2], 0.5), eye_in, eye_out],
        [z_ridge, mix(ledge, top[1], 0.35), brow[2], eye_in * k * brow[2], eye_out * k * brow[2]],
        [top[0], top[1], top[2], eye_in * k * top[2], eye_out * k * top[2]],
    ]
    for i in range(1, len(rings)):
        rings[i][0] = max(rings[i][0], rings[i - 1][0] + step)
        if scan:  # as wide as the reference is at that height
            r, t = scan_row(scan["zs"], rings[i][0])
            rings[i][2] = max(mix(scan["wide"][r], scan["wide"][r + 1], t), 0.25 * eyes[2])
    grid = []  # grid[row][column] = Vector((sideways, forward, up))
    for z, front, wide, s1, s2 in rings:
        deep = front - back
        s2 = min(max(s2, 0.3 * wide), 0.78 * wide)
        s1 = min(s1, s2 - 0.12 * wide)
        row = [Vector((0, front, z)), Vector((s1, front - 0.08 * deep * (s1 / wide) ** 2, z)),
               Vector((s2, front - 0.08 * deep * (s2 / wide) ** 2, z)),
               Vector((max(0.86 * wide, s2 + 0.06 * wide), front - 0.2 * deep, z)), Vector((wide, back + 0.45 * deep, z))]
        if part.get("round"):
            row.append(Vector((0.72 * wide, back + 0.1 * deep, z)))
        if part.get("back", True):
            row.append(Vector((0, back, z)))
        if scan and grid:  # lay the ring on the reference: the face as seen from the front, the rest from behind
            for c in range(4):
                row[c].y = scan_at(scan, "front", row[c].x, z) or row[c].y
            edge, behind = scan_at(scan, "front", wide, z), scan_at(scan, "back", wide, z)
            if edge is not None:
                row[4].y = edge if behind is None else (edge + behind) / 2
            for c in range(5, len(row)):
                if behind is None:  # sunk into the body here: the side runs straight back into it
                    row[c].x = 0.95 * wide
                row[c].y = scan_at(scan, "back", row[c].x, z) or row[c].y
        grid.append(row)
    if scan:  # under the jaw: the chin's ring, drawn in
        inside = sum((p.y for p in grid[1]), 0.0) / len(grid[1])
        grid[0] = [Vector((0.75 * p.x, mix(inside, p.y, 0.6), rings[0][0])) for p in grid[1]]
    peak = max(hi[2], rings[-1][0] + 0.06 * tall)
    if scan:
        peak = max(min(peak, scan["zs"][-1]), rings[-1][0] + step)
    crown = Vector((0, (grid[-1][0].y + (grid[-1][-1].y if part.get("back", True) else back)) / 2, peak))
    grid.append([crown.copy() for _ in grid[0]])
    tip = nose[1] + nose_out
    if scan:  # the reference's own nose, or what reads, whichever sticks out more
        tip = max(scan_at(scan, "front", 0, nose[0]) or tip, grid[5][1].y + nose_out)
        for c in range(4):  # and its own brow, nudged out where it would not overhang the eyes at all
            grid[6][c].y = max(grid[6][c].y, grid[5][max(c, 1)].y + 0.2 * kind["brow"] * tall * bold)
    else:
        grid[4][1].y += 0.3 * nose_out  # the nose's wings
    grid[5][0] = Vector((0, tip, min(max(nose[0], rings[4][0] + step), rings[6][0] - step)))  # the tip of the nose
    grid[6][0].z -= 0.45 * scowl * eye_tall
    grid[6][1].z -= 0.3 * scowl * eye_tall
    grid[6][2].z = min(grid[6][2].z + 0.15 * scowl * eye_tall, mix(rings[6][0], rings[7][0], 0.5))
    for c in range(2, len(grid[0])):  # past its corner the mouth is one line
        grid[2][c] = grid[3][c] = (grid[2][c] + grid[3][c]) / 2

    paint = part.get("colors", {})
    skin = list(paint.get("skin", part.get("color", (0.6, 0.6, 0.6))))[:3]
    hair = paint.get("hair")
    socket, pupil = paint.get("socket", tone(skin, 0.4)), paint.get("eye", (0.04, 0.03, 0.03))
    verts, faces, shades = [], [], []
    width = len(grid[0])
    for r in range(len(grid) - 1):
        for c in range(width - 1):
            cell = [grid[r][c], grid[r][c + 1], grid[r + 1][c + 1], grid[r + 1][c]]
            color = hair if hair and (r >= 7 or (r >= 5 and c >= 4)) else skin
            if "beard" in paint and (r < 2 or (r == 3 and c < 2)) and c < 4:  # jaw, chin and upper lip
                color = paint["beard"]
            n = len(verts)
            if c == 0 and r in (4, 5):  # the nose: under and side below the tip, bridge above it
                verts += cell
                faces += [(n, n + 1, n + 3), (n + 1, n + 2, n + 3)] if r == 4 else [(n, n + 1, n + 2), (n, n + 2, n + 3)]
                shades += [paint.get("nose", tone(skin, 0.72)) if r == 4 else skin, skin]
            elif c == 1 and r == 5 and part.get("eyes", "sunk") == "sunk":  # a socket: four dark sides down to the eye
                middle = sum(cell, Vector()) / 4
                deep = max(eye_sunk, min(middle.y - eyes[1], 0.12 * tall))
                inner = [middle + (p - middle) * 0.6 - Vector((0, deep, 0)) for p in cell]
                verts += cell + inner
                faces += [(n + i, n + (i + 1) % 4, n + 4 + (i + 1) % 4, n + 4 + i) for i in range(4)] + [(n + 4, n + 5, n + 6, n + 7)]
                shades += [socket] * 4 + [pupil]
            else:
                if c == 1 and r == 5:
                    color = paint.get("eye", (0.04, 0.03, 0.03))
                elif r == 2 and c < 2:
                    color = paint.get("mouth", tone(skin, 0.35))
                elif r == 6 and c < 3:
                    color = paint.get("brow", tone(skin, 0.8))
                verts += cell
                faces.append((n, n + 1, n + 2, n + 3))
                shades.append(color)
    if part.get("caps", True):  # under the jaw
        n = len(verts)
        verts += list(reversed(grid[0]))
        faces.append(tuple(range(n, n + width)))
        shades.append(skin)
    twin = len(verts)  # the other half of the face
    verts += [Vector((-p.x, p.y, p.z)) for p in verts]
    faces += [tuple(reversed([twin + i for i in f])) for f in faces]
    shades += shades
    faces = facing_out(verts, faces)

    extra = []  # ears and tusks: [(base points, tip, color)]
    ears = part.get("ears")
    if ears:
        ears = ears if isinstance(ears, dict) else {}
        size, up = ears.get("long", kind["ear_long"] * tall), ears.get("up", kind["ear_up"])
        at = Vector((0.9 * rings[5][2], cheek - min(0.6 * (cheek - back), 0.65 * eyes[2]), ears.get("z", eyes[0])))
        if "front" in ears:
            at.y = sign * ears["front"]
        half = ears.get("tall", 0.18 * tall) / 2
        base = [at + Vector((0, half, 0)), at + Vector((0, 0, half)), at + Vector((0, -half, 0)), at + Vector((0, 0, -half))]
        tip = at + Vector((0.1 * eyes[2] + size * (1 - 0.6 * up), -0.35 * size, 0.9 * size * up))
        extra.append((base, tip, paint.get("ear", tone(skin, 0.9))))
    tusks = part.get("tusks")
    if tusks:
        tusks = tusks if isinstance(tusks, dict) else {}
        size, r = tusks.get("long", 0.2 * tall), tusks.get("wide", 0.035 * tall)
        below = tusks.get("from", "below") == "below"
        at = Vector((min(tusks.get("at", 0.8 * mouth_wide), mouth[2] - r), mouth[1] + (under if below else 0.0) - 0.5 * r,
                     tusks.get("z", mouth[0] - (0.25 * size if below else -0.25 * size))))
        base = [at + Vector((r, 0, 0)), at + Vector((0, r, 0)), at + Vector((-r, 0, 0)), at + Vector((0, -r, 0))]
        tip = at + Vector((0.3 * r, 0.25 * size, size if below else -size))
        if "front" in tusks:  # as far forward as the reference's
            tip.y = sign * tusks["front"]
            at.y = max(at.y, tip.y - 0.5 * size)
            base = [at + Vector((r, 0, 0)), at + Vector((0, r, 0)), at + Vector((-r, 0, 0)), at + Vector((0, -r, 0))]
        extra.append((base, tip, paint.get("tusk", (0.88, 0.84, 0.68))))
    for base, tip, color in extra:
        for flip in (1, -1):
            points, sides = spike([Vector((flip * p.x, p.y, p.z)) for p in base], Vector((flip * tip.x, tip.y, tip.z)))
            n = len(verts)
            verts += points
            faces += [tuple(n + i for i in f) for f in facing_out(points, sides)]
            shades += [color] * len(sides)

    # Weld the grid's shared points, drop cells that closed up, and stand it in the world.
    middle = (lo[u] + hi[u]) / 2
    index, placed, kept, colors = {}, [], [], []
    for f, color in zip(faces, shades):
        ring = []
        for i in f:
            key = tuple(round(v, 6) for v in verts[i])
            if key not in index:
                index[key] = len(placed)
                p = [0.0, 0.0, verts[i].z]
                p[u], p[a] = middle + verts[i].x, sign * verts[i].y
                placed.append(Vector(p))
            if index[key] not in ring:
                ring.append(index[key])
        if len(ring) > 2:
            kept.append(tuple(ring))
            colors.append(color)
    if (u, sign) in ((0, -1.0), (1, 1.0)):  # these two ways of facing mirror the shape, which turns every face inside out
        kept = [tuple(reversed(f)) for f in kept]
    return placed, kept, colors

def make_piece(part, owner, scene):
    shades = None
    if "head" in part:
        verts, faces, shades = head(part)
    elif "loft" in part:
        verts, faces = skin(loft_rings(part), part.get("caps", [True, True]), part.get("closed", False))
    elif "tube" in part:
        verts, faces = skin(tube_rings(part), part.get("caps", [True, True]), part.get("closed", False))
    elif "lumps" in part:
        verts, faces = lumps(part)
    elif "box" in part:
        verts, faces = box(part)
    else:
        raise ValueError("piece %r needs a loft, tube, lumps, box or head" % part.get("name"))
    if part.get("mirror") and "lumps" not in part and "head" not in part:
        count = len(verts)
        verts = verts + [Vector((-p.x, p.y, p.z)) for p in verts]
        faces = faces + [tuple(reversed([count + i for i in f])) for f in faces]
    me = bpy.data.meshes.new("piece: " + part["name"])
    me.from_pydata([tuple(p) for p in verts], [], faces)
    paint = me.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
    flat = tuple(part.get("color", (0.6, 0.6, 0.6)))[:3] + (1.0,)
    for i, poly in enumerate(me.polygons):
        shade = tuple(shades[i])[:3] + (1.0,) if shades else flat
        for corner in poly.loop_indices:
            paint.data[corner].color = shade
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)  # a ring of radius 0 becomes a point
    if "lumps" in part or "box" in part:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for _ in range(int(part.get("finer", 0))):
        bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=1, smooth=1.0, use_grid_fill=True)
    bm.to_mesh(me)
    bm.free()
    piece = bpy.data.objects.new("piece: " + part["name"], me)
    piece["piece_of"] = owner
    piece["piece"] = part["name"]
    piece["gear"] = part.get("gear") or ""
    piece["of"] = part.get("of") or ""  # the "body" piece this one was made for
    piece["spec"] = json.dumps(part)  # the recipe, so the same piece can be built again, denser
    scene.collection.objects.link(piece)
    piece.hide_set(True)
    piece.hide_render = True
    return piece

def triangles(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)

def spread(me, count, rng):
    """Points spread evenly over a mesh's surface."""
    me.calc_loop_triangles()
    tris = me.loop_triangles
    out = []
    for i in rng.choices(range(len(tris)), weights=[t.area for t in tris], k=count):
        a, b, c = [me.vertices[v].co for v in tris[i].vertices]
        r1, r2 = rng.random(), rng.random()
        if r1 + r2 > 1:
            r1, r2 = 1 - r1, 1 - r2
        out.append(a + (b - a) * r1 + (c - a) * r2)
    return out

def off(points, tree, size):
    """How far each point is from a surface, in % of the object's size, farthest first."""
    found = [(tree.find_nearest(p), p) for p in points]
    return sorted([(100 * hit[3] / size, p) for hit, p in found if hit[0] is not None], key=first, reverse=True)

def first(pair):
    return pair[0]

def group_name(piece):
    return "gear: " + piece["gear"] if piece.get("gear") else "body"

def group_tag(group, listed):
    """What export.py writes on a group's mesh: for gear, its kind and slot from the brief."""
    if group == "body":
        return {"name": group, "forge": "body"}
    item = listed.get(group[6:], {})
    return {"name": group, "forge": "gear", "gear": group[6:], "kind": item.get("kind") or "worn", "slot": item.get("slot") or ""}

def ray(tree, start, aim):
    """Where a ray first meets the body, or None."""
    return tree.ray_cast(Vector(start), Vector(aim))[0]

def find_sockets(points, faces, head_top, moved):
    """Where props attach on a T-pose body facing -y: palms, top of the head, upper back, left hip."""
    lows = [min(p[i] for p in points) for i in range(3)]
    highs = [max(p[i] for p in points) for i in range(3)]
    tall = highs[2] - lows[2]
    middle = (lows[0] + highs[0]) / 2
    tree = BVHTree.FromPolygons([tuple(p) for p in points], faces)
    found = {}
    for key, tip, inward in (("hand_right", lows[0], 1.0), ("hand_left", highs[0], -1.0)):
        hand = [p for p in points if abs(p.x - tip) < 0.1 * tall]
        found[key] = [tip + inward * 0.055 * tall] + [(min(p[i] for p in hand) + max(p[i] for p in hand)) / 2 for i in (1, 2)]
    arms = (found["hand_right"][2] + found["hand_left"][2]) / 2
    if head_top:
        found["head"] = list(head_top)
    else:
        crown = [p for p in points if abs(p.x - middle) < 0.12 * tall]
        peak = max(p.z for p in crown)
        near = [p.y for p in crown if p.z > peak - 0.03 * tall]
        found["head"] = [middle, sum(near) / len(near), peak]
    up = arms - 0.04 * tall
    spine = ray(tree, (middle, highs[1] + 1, up), (0, -1, 0))
    found["back"] = [middle, spine.y if spine else highs[1], up]
    waist = lows[2] + 0.62 * (arms - lows[2])
    front, behind = ray(tree, (middle, lows[1] - 1, waist), (0, 1, 0)), ray(tree, (middle, highs[1] + 1, waist), (0, -1, 0))
    depth = (front.y + behind.y) / 2 if front and behind else (lows[1] + highs[1]) / 2
    side = ray(tree, (highs[0] + 1, depth, waist), (-1, 0, 0))
    found["hip"] = [side.x if side else middle + 0.1 * tall, depth, waist]
    for key, spot in moved.items():
        if key not in found:
            raise ValueError("no socket named %r: sockets are %s" % (key, ", ".join(found)))
        found[key] = list(spot)
    return {key: [round(c, 4) for c in spot] for key, spot in found.items()}, tall

def summary(d):
    if not d:
        return None
    return {"mean_%": round(sum(x for x, _ in d) / len(d), 2), "p95_%": round(d[len(d) // 20][0], 2), "max_%": round(d[0][0], 2)}


scene = bpy.context.scene
ref = bpy.data.objects.get(PARAMS["reference"]) if PARAMS["reference"] else None
if ref is None:
    candidates = [o for o in scene.objects if o.type == "MESH" and o.visible_get() and not o.name.endswith(" (light)")]
    if not candidates:
        raise ValueError("no reference mesh: open the detailed mesh first, or set PARAMS['reference']")
    ref = max(candidates, key=face_count)
name = PARAMS["name"] or ref.name + " (light)"

pieces = {o["piece"]: o for o in scene.objects if o.get("piece_of") == name}
asked = []
for part in PARAMS["parts"]:
    if "body" in part and "loft" not in part:  # a body: the trunk, neck, arms, hands, legs and feet it stands for
        asked += body_parts(part, scene)
    else:
        asked.append(part)
going = PARAMS["remove"] + [p["name"] for p in PARAMS["parts"]]
for gone in going + [n for n, o in pieces.items() if o.get("of") in going]:
    if gone in pieces:
        bpy.data.objects.remove(pieces.pop(gone), do_unlink=True)
for part in asked:
    pieces[part["name"]] = make_piece(part, name, scene)
if not pieces:
    raise ValueError("nothing to build: PARAMS['parts'] is empty")

light = bpy.data.objects.get(name)
if light is None:
    light = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    scene.collection.objects.link(light)

# Which gear item each gear piece is: the brief's list, kept on the object between calls.
if PARAMS["gear"] is not None:
    light["forge_gear"] = json.dumps([{"name": g["name"], "kind": g.get("kind"), "slot": g.get("slot")} for g in PARAMS["gear"]])
listed = {g["name"]: g for g in json.loads(light.get("forge_gear", "[]"))}
for piece in pieces.values():
    if piece.get("gear") and listed and piece["gear"] not in listed:
        raise ValueError("piece %r is gear %r, which the gear list doesn't have: %s" % (piece["piece"], piece["gear"], ", ".join(listed)))
groups = ["body"] if any(not p.get("gear") for p in pieces.values()) else []
for piece in pieces.values():
    if group_name(piece) not in groups:
        groups.append(group_name(piece))

# A body piece's own notes: what it was asked for, its landmarks, and the "head" size its style asks for.
bodies = [json.loads(p["spec"]).get("body") for p in pieces.values() if p.get("of")]
bodies = [b for b in bodies if isinstance(b, dict) and b.get("spec")]
big_head = bodies[0]["spec"].get("style", {}).get("head", 1.0) if bodies else 1.0
chin = Vector((0.0, bodies[0]["landmarks"]["neck"][1], bodies[0]["landmarks"]["chin"][2])) if bodies else None

joined = bmesh.new()
marks = []  # for each face, which group it belongs to
for piece in pieces.values():
    before = len(joined.verts)
    joined.from_mesh(piece.data)
    marks += [groups.index(group_name(piece))] * len(piece.data.polygons)
    if big_head != 1.0 and not piece.get("of") and min(v.co.z for v in piece.data.vertices) > chin.z - 0.02 * (ref.dimensions.z or 1.0):
        joined.verts.ensure_lookup_table()  # the head and all that sits on it (hair, a hat, glasses) grow from the chin
        for i in range(before, len(joined.verts)):
            joined.verts[i].co = chin + (joined.verts[i].co - chin) * big_head
joined.to_mesh(light.data)
joined.free()
smooth = PARAMS["shading"] == "smooth"
light.data.polygons.foreach_set("use_smooth", [smooth] * len(light.data.polygons))
if smooth and PARAMS["crease"]:
    light.data.set_sharp_from_angle(angle=math.radians(PARAMS["crease"]))
tag = light.data.attributes.get("forge_group") or light.data.attributes.new("forge_group", "INT", "FACE")
tag.data.foreach_set("value", marks)
light.data.update()
bpy.context.view_layer.update()
mat = bpy.data.materials.get("piece colors") or bpy.data.materials.new("piece colors")
mat.use_nodes = True
nodes = mat.node_tree.nodes
paint = nodes.get("Col") or nodes.new("ShaderNodeAttribute")
paint.name = paint.attribute_name = "Col"
mat.node_tree.links.new(paint.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
light.data.materials.clear()
light.data.materials.append(mat)
light["forge_groups"] = json.dumps([group_tag(g, listed) for g in groups])  # export.py writes one mesh per group from this
for key in ("draped", "forge_masks"):  # the pieces were joined afresh: whatever drape.py did to the old mesh is gone
    if key in light:
        del light[key]

# Attachment points: empties that export.py sends along.
wanted = PARAMS["sockets"]
before = json.loads(light.get("forge_sockets", "null"))
if wanted is None:
    wanted = before["moved"] if before else False
sockets = {}
for old in [o for o in scene.objects if o.get("socket_of") == name]:
    bpy.data.objects.remove(old, do_unlink=True)
if wanted is not False:
    moved = wanted if isinstance(wanted, dict) else {}
    flesh = [p for p in pieces.values() if not p.get("gear")] or list(pieces.values())
    points, faces = [], []
    for piece in flesh:
        start = len(points)
        points += [v.co.copy() for v in piece.data.vertices]
        faces += [tuple(start + i for i in poly.vertices) for poly in piece.data.polygons]
    heads = [[v.co for v in p.data.vertices] for p in flesh if "head" in json.loads(p.get("spec", "{}"))]
    top = [sum(p.x for p in heads[0]) / len(heads[0]), sum(p.y for p in heads[0]) / len(heads[0]), max(p.z for p in heads[0])] if heads else None
    if top and big_head != 1.0:
        top = list(chin + (Vector(top) - chin) * big_head)
    sockets, tall = find_sockets(points, faces, top, moved)
    for key, spot in sockets.items():
        marker = bpy.data.objects.new("socket: " + key, None)
        marker.empty_display_type = "SPHERE"
        marker.empty_display_size = 0.02 * tall
        marker.location = spot
        marker["socket_of"] = name
        marker["forge"] = "socket"
        marker["socket"] = key
        scene.collection.objects.link(marker)
    light["forge_sockets"] = json.dumps({"moved": moved if moved else True, "at": sockets})
elif "forge_sockets" in light:
    del light["forge_sockets"]

# The recipe: every piece as it was asked for, so the mid-poly profile can build the same thing denser.
recipe = [json.loads(p["spec"]) for p in pieces.values() if p.get("spec")]
if len(recipe) == len(pieces):
    scans = {}
    for part in recipe:
        if part.get("scan") and scene.get("face: " + part["scan"]):
            scans[part["scan"]] = json.loads(scene["face: " + part["scan"]])
    build = {"version": 1, "object": name, "shading": PARAMS["shading"], "gear": list(listed.values()),
             "sockets": sockets, "pieces": recipe, "scans": scans}
    if bodies:  # where this character's joints and landmarks are, for whatever reads the recipe next (a skeleton, say)
        build["landmarks"], build["joints"] = bodies[0]["landmarks"], bodies[0]["joints"]
    light["forge_build"] = json.dumps(build)
elif "forge_build" in light:
    del light["forge_build"]

result = {
    "object": light.name,
    "reference": ref.name,
    "triangles": triangles(light.data),
    "size": [round(d, 3) for d in light.dimensions],
    "reference_size": [round(d, 3) for d in ref.dimensions],
    "pieces": [{"name": n, "triangles": triangles(o.data)} for n, o in pieces.items()],
    "recipe_kept": "forge_build" in light,
}
if len(groups) > 1:
    result["groups"] = [dict(group_tag(g, listed), triangles=sum(triangles(p.data) for p in pieces.values() if group_name(p) == g)) for g in groups]
    result["gear_not_built"] = [g["name"] for g in listed.values() if g.get("kind") != "held" and "gear: " + g["name"] not in groups]
if sockets:
    result["sockets"] = sockets
if bodies:
    mine = [o for o in pieces.values() if o.get("of") == bodies[0]["spec"]["name"]]
    result["body"] = {"triangles": sum(triangles(o.data) for o in mine), "rings": bodies[0]["rings"], "loops": bodies[0]["loops"],
                      "landmarks": bodies[0]["landmarks"],
                      "check_these": {k: v for k, v in (bodies[0].get("found") or {}).items() if v != "shape"}}
if PARAMS["check"]:
    rng = random.Random(0)
    size = max(ref.dimensions)
    to_ref = ref.matrix_world.inverted()
    ref_tree = BVHTree.FromObject(ref, bpy.context.evaluated_depsgraph_get())
    light_tree = BVHTree.FromPolygons([tuple(v.co) for v in light.data.vertices], [tuple(p.vertices) for p in light.data.polygons])
    lost = off([ref.matrix_world @ p for p in spread(ref.data, PARAMS["check"], rng)], light_tree, size)
    added = []
    for entry, piece in zip(result["pieces"], pieces.values()):
        share = max(50, PARAMS["check"] * entry["triangles"] // max(result["triangles"], 1))
        d = off([to_ref @ p for p in spread(piece.data, share, rng)], ref_tree, size)
        added += d
        if d:
            entry["sticks_out_%"] = round(d[0][0], 2)
            entry["worst_at"] = [round(c, 3) for c in ref.matrix_world @ d[0][1]]
    spots = []
    for dist, p in lost:
        if all((p - q).length > size * 0.12 for _, q in spots):
            spots.append((dist, p))
        if len(spots) == 5:
            break
    result["shape_lost"] = summary(lost)
    result["shape_added"] = summary(sorted(added, key=first, reverse=True))
    result["most_missing_at"] = [{"at": [round(c, 3) for c in p], "off_%": round(dist, 2)} for dist, p in spots]

print("RESULT " + json.dumps(result))
