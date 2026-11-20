# Block out a low-poly version from a list of simple pieces, join them into
# one object, and say how far it strays from the detailed mesh.
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
#       "box"    the head's box. "rows": [height, front of the face there,
#                half-width] for "chin", "mouth", "nose", "eyes", "brow", "top"
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
#                "wide": , "from": "below" or "above"} and "ears": {"long": , "up": 0-1 (0
#                sticks out, 1 points up), "z": }; True takes the defaults
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
        grid.append(row)
    crown = Vector((0, mix(back, top[1], 0.5), max(hi[2], rings[-1][0] + 0.06 * tall)))
    grid.append([crown.copy() for _ in grid[0]])
    grid[5][0] = Vector((0, nose[1] + nose_out, min(max(nose[0], rings[4][0] + step), rings[6][0] - step)))  # the tip of the nose
    grid[4][1].y += 0.3 * nose_out  # its wings
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
        at = Vector((0.9 * eyes[2], cheek - min(0.6 * (cheek - back), 0.65 * eyes[2]), ears.get("z", eyes[0])))
        half = 0.09 * tall
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
    bm.to_mesh(me)
    bm.free()
    piece = bpy.data.objects.new("piece: " + part["name"], me)
    piece["piece_of"] = owner
    piece["piece"] = part["name"]
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

joined = bmesh.new()
for piece in pieces.values():
    joined.from_mesh(piece.data)
light = bpy.data.objects.get(name)
if light is None:
    light = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    scene.collection.objects.link(light)
joined.to_mesh(light.data)
joined.free()
light.data.polygons.foreach_set("use_smooth", [PARAMS["shading"] == "smooth"] * len(light.data.polygons))
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

result = {
    "object": light.name,
    "reference": ref.name,
    "triangles": triangles(light.data),
    "size": [round(d, 3) for d in light.dimensions],
    "reference_size": [round(d, 3) for d in ref.dimensions],
    "pieces": [{"name": n, "triangles": triangles(o.data)} for n, o in pieces.items()],
}
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
