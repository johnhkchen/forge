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

FACING = {"-y": (1, -1.0), "+y": (1, 1.0), "-x": (0, -1.0), "+x": (0, 1.0)}
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
for gone in PARAMS["remove"] + [p["name"] for p in PARAMS["parts"]]:
    if gone in pieces:
        bpy.data.objects.remove(pieces.pop(gone), do_unlink=True)
for part in PARAMS["parts"]:
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

joined = bmesh.new()
marks = []  # for each face, which group it belongs to
for piece in pieces.values():
    joined.from_mesh(piece.data)
    marks += [groups.index(group_name(piece))] * len(piece.data.polygons)
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
    light["forge_build"] = json.dumps({"version": 1, "object": name, "shading": PARAMS["shading"], "gear": list(listed.values()),
                                       "sockets": sockets, "pieces": recipe, "scans": scans})
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
