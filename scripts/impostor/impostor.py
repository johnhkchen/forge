"""A character drawn as flat cards, one per bone: the arithmetic, and a slow drawing of it.

The idea (Aubel, Boulic and Thalmann's cut-up impostors; Beacco and others at UPC, one per joint):
cut a rigged character into rigid parts, one per bone. Ahead of time, picture each part alone from a
fixed set of directions around it (bake_impostor.py: colour, which way the surface faces, how far it
stands toward the eye). To draw the character, each bone gets one flat card facing the eye, showing
the picture taken from nearest to where the eye now is *as that bone sees it*, turned and foreshortened
to how the bone now shows, each pixel slid by its stored depth to where the real surface would be. The
same depth lets the cards hide each other, and the set hide them, pixel by pixel. Any motion plays: no
new pictures are ever needed.

This file is the one place that arithmetic is written down in Python. gallery/impostor-math.js is the
same arithmetic for the page (test_impostor.py holds the two against each other), and draw() here is
the page's shader done slowly, a pixel at a time, so a picture can be judged without a browser.

Everything is in a .glb's own directions (y up, metres). A bone's own frame is its joint's frame in
the .glb, which is Blender's bone frame: y runs along the bone.

Needs numpy and nothing else (Blender's Python has it; `python3` here may not: see test_impostor.py).
"""

import json
import math
import os
import struct
import zlib

import numpy as np

# ---------- the directions a part is pictured from ----------

# name: (how many around the bone, the heights in degrees above and below its side-on ring). Straight
# along the bone, both ways, is always added.
VIEW_SETS = {
    "26": (8, [-45.0, 0.0, 45.0]),
    "62": (12, [-60.0, -30.0, 0.0, 30.0, 60.0]),
    "114": (16, [-67.5, -45.0, -22.5, 0.0, 22.5, 45.0, 67.5]),
}
MARCH_PX = 1.0       # sliding a pixel by its depth: the picture is searched in steps this many of its pixels long
MARCH_MAX = 32       # ... and never more steps than this (a longer search takes longer steps)
REFINE = 5           # ... then the place found is halved in on this many times
WALL_M = 0.04        # a pixel found this far below the surface it landed on is looking at nothing the picture saw
GO_ON = True         # ... and the search then goes on under it to the next surface (False: it gives up there, as the page did before the joints were mended)
FILL = {"ball", "joint", "screen"}  # what fills a bent joint, each of which judge_seams.py --fill can leave out: "ball" (a ball in every joint), "joint" (a see-through pixel near a joint), "screen" (cracks, on the finished picture)
FILL_BALL = 1.0      # a see-through pixel is filled inside a ball about a joint this many times the radius of the ring where its two parts meet
FILL_BACK_M = 0.02   # ... and stands this far behind where its line went in: anything truly there covers it
FILL_INNER = 0.8     # the ball in a joint is this share of the ball the bake found room for inside the body there (that one is as big as fits at the joint, and a thin forearm just past a thick elbow is thinner than it)
TINT_REACH = 0.6     # the colour a part gives a joint's ball is looked for this share of the ball's radius round a place ...
TINT_IN = 0.8        # ... this share of the joint's ring radius in from the joint, toward the middle of the part: its own skin, past what it borrows from next door
BALL_BACK_M = 0.01   # two parts both draw the ball of the joint between them, each in its own colour: the one whose body is not behind the ball, as the eye sees it, stands its ball back by up to this
BALLS_A_PART = 4     # a part meets at most this many others (a chest: the spine, the head and two arms)
BLEND_DEG = 7.0      # two views are mixed when the eye is within this of the line between them
HOLD_DEG = 2.5       # a view is kept until another is nearer by this much (stops flicker on the line)
INK = (0.11, 0.09, 0.13)  # the ink line's colour, as it looks on screen
LINE_BACK_M = 0.03   # the ink line round a part stands this far behind the part's surface, as a mesh's ink shell does: the part next door covers it
BREAK_M = 0.05       # lines drawn on the finished picture: within one figure, a line only where the surface steps back by more than this
SEAM_M = 0.09        # ... and bold ink's thin lines leave a step smaller than this alone where two cards of one figure meet
PARTS_A_FIGURE = 16  # a pixel's number in the finished picture: 1 + sixteen times which figure + which of its parts; 0 is not a card
CRACK_BEHIND_M = 0.02  # filling a crack on the finished picture: what shows through it is this much further off than the cards on both sides
CRACK_APART_M = 0.12   # ... which are no further than this from each other in depth
# The parts in the order a bake lists them (bake_impostor.py: PARTS), and which meet at a joint: a crack is only
# filled between two cards of one part, or of two parts that meet. gallery/looks.js has the same table.
PART_NAMES = ["hips", "spine", "chest", "head"] + [name + side for side in ("_l", "_r") for name in ("upper_arm", "forearm", "hand", "thigh", "shin", "foot")]
MEET = [("hips", "spine"), ("spine", "chest"), ("chest", "head")] + [pair for side in ("_l", "_r") for pair in (
    ("chest", "upper_arm" + side), ("upper_arm" + side, "forearm" + side), ("forearm" + side, "hand" + side), ("hips", "thigh" + side), ("thigh" + side, "shin" + side), ("shin" + side, "foot" + side))]
JOINED = np.eye(PARTS_A_FIGURE, dtype=bool)
for _a, _b in MEET:
    JOINED[PART_NAMES.index(_a), PART_NAMES.index(_b)] = JOINED[PART_NAMES.index(_b), PART_NAMES.index(_a)] = True
BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32) / 16.0 + 1.0 / 32.0
# The comic look (toon.py's numbers): where the light is as the eye sees it (right, up, toward the eye),
# what the middle and dark tones multiply a colour by, and how far a surface must face the light for each.
LIGHT = (-0.55, 0.5, 0.67)
SHADE = ((0.86, 0.85, 0.90), (0.62, 0.60, 0.74))
EDGES = (0.2, -0.2)
# The paint of each look (gallery/looks.js: LOOKS): the two darker tones, where each begins, how strong the colour
# is, how much light the rim gets, and how many steps a colour is cut to on the finished picture (0: left alone).
PAINTS = {
    "comic": {"shade": SHADE, "edges": EDGES, "punch": 1.0, "rim": 0.0, "levels": 0},
    "pixel": {"shade": ((0.8, 0.78, 0.88), (0.58, 0.55, 0.72)), "edges": EDGES, "punch": 1.1, "rim": 0.0, "levels": 12},
    "joe": {"shade": ((0.5, 0.46, 0.66), (0.5, 0.46, 0.66)), "edges": (0.08, -2.0), "punch": 1.45, "rim": 0.35, "levels": 0},
}
GRID_INK = (0x1c, 0x17, 0x21)   # the pixel looks' line on the finished picture
# A head on a finer grid ("Pixels, both"; gallery/looks.js has the same numbers):
FINE = 2             # a head's pixels are this many times smaller than the body's, each way
FINE_FROM = 40.0     # ... once a metre at the head is at least this many of the picture's big pixels (a face five or six wide); further off it is drawn with the body
KEEP_DARK = 0.12     # where a head's picture is shown smaller than it was taken, a pixel takes the darkest of what it covers when that is darker than its middle by this much (0 to 1, as the eye sees it)
KEEP_M = 0.02        # ... and stands within this of the same depth (it is the same surface, not something behind it)


def unit(v):
    v = np.asarray(v, dtype=np.float64)
    return v / max(np.linalg.norm(v), 1e-12)


def views_of(name):
    """The directions of a view set, each with its picture's own right and up.

    A direction d points from the part to the eye, in the bone's frame. The picture's up is the bone
    itself as seen from there (so a limb stands upright in its picture); looking straight along the
    bone, up is the bone's z. right x up = d."""
    around, heights = VIEW_SETS[name]
    dirs = []
    for el in heights:
        for k in range(around):
            az = 2.0 * math.pi * k / around
            c = math.cos(math.radians(el))
            dirs.append((c * math.sin(az), math.sin(math.radians(el)), c * math.cos(az)))
    dirs += [(0.0, 1.0, 0.0), (0.0, -1.0, 0.0)]
    out = []
    for d in dirs:
        d = unit(d)
        if abs(d[1]) > 0.999:
            u = np.array([0.0, 0.0, 1.0])
        else:
            u = unit(np.array([0.0, 1.0, 0.0]) - d[1] * d)
        r = np.cross(u, d)
        out.append({"d": [round(float(c), 6) for c in d], "r": [round(float(c), 6) for c in r], "u": [round(float(c), 6) for c in u]})
    return out


def nearest_views(dirs, v):
    """The views by how near they are to direction v (nearest first), and the angle to each in degrees."""
    dots = np.clip(np.asarray(dirs) @ np.asarray(v), -1.0, 1.0)
    order = np.argsort(-dots)
    return order, np.degrees(np.arccos(dots[order]))


def choose(dirs, v, held=None, hold_deg=HOLD_DEG):
    """Which view to show, which is next nearest, and how much of the first to show (1 = all of it).

    `held` is the view shown last time: it is kept until another is nearer by `hold_deg`. The share
    falls to a half as the eye reaches the line between the two views, across BLEND_DEG."""
    order, angles = nearest_views(dirs, v)
    first, second = int(order[0]), int(order[1])
    if held is not None and held != first:
        held_angle = math.degrees(math.acos(max(-1.0, min(1.0, float(np.asarray(dirs[held]) @ np.asarray(v))))))
        if held_angle - angles[0] < hold_deg:
            first, second = held, first
            gap = angles[0] - held_angle
            return first, second, float(min(1.0, max(0.0, 0.5 + 0.5 * gap / BLEND_DEG)))
    gap = angles[1] - angles[0]
    return first, second, float(min(1.0, 0.5 + 0.5 * gap / BLEND_DEG))


# ---------- where a card goes ----------

def place(view, bone, center, eye):
    """Where one part's card stands, and how its picture is read, for one view.

    bone    the bone's 4x4 matrix in the world (its joint, as the .glb has it)
    center  the middle of the part, in the bone's frame: the eye's direction is measured from there
    eye     where the eye is, in the world

    The card is a flat sheet through the bone's head, square on to the eye. A place on it is two numbers
    P (metres at the bone's own size): across, along `e2`, and up, along `e1`, both world directions on
    the sheet; e1 is the bone itself as it shows from here.

    The picture was taken from the view's direction d, not from where the eye now is. A point of it X
    right, Y up and h toward its own eye is the bone-frame point  X r + Y u + h d,  and seen from here
    that point shows on the sheet at

        P = turn_xy . (X, Y) + h * lean

    which is exact while the eye is far off compared with the part. `turn_xy` is the turn and the
    foreshortening; `lean` slides a point by how far it stands out, so a picture taken from a little to
    one side still lands where the real surface is. Read backwards, a pixel at P is looking along the
    line  (X, Y) = back . (P - h * lean)  for every h, and shows the first place on it where the
    picture's surface is at least h high: the page walks down that line (card_pixels). `deep` gives how
    far toward the eye a point stands: X, Y, h times its three numbers."""
    bone = np.asarray(bone, dtype=np.float64)
    turn = bone[:3, :3]
    size = float(np.cbrt(abs(np.linalg.det(turn))))
    turn = turn / size
    head = bone[:3, 3]
    middle = head + bone[:3, :3] @ np.asarray(center, dtype=np.float64)
    toward = unit(np.asarray(eye, dtype=np.float64) - middle)
    axis = turn[:, 1]
    flat = axis - (axis @ toward) * toward
    if np.linalg.norm(flat) < 1e-4:  # the bone points straight at the eye: its x will do
        axis = turn[:, 0]
        flat = axis - (axis @ toward) * toward
    e1 = unit(flat)
    e2 = np.cross(e1, toward)
    a1, a2, v = turn.T @ e1, turn.T @ e2, turn.T @ toward
    r, u, d = np.asarray(view["r"]), np.asarray(view["u"]), np.asarray(view["d"])
    turn_xy = np.array([[r @ a2, u @ a2], [r @ a1, u @ a1]])
    return {"head": head, "toward": toward, "size": size, "e1": e1, "e2": e2, "turn": turn,
            "back": np.linalg.inv(turn_xy), "turn_xy": turn_xy, "lean": np.array([d @ a2, d @ a1]), "deep": np.array([r @ v, u @ v, d @ v])}


def eye_in_bone(bone, center, eye):
    """The direction from the part's middle to the eye, in the bone's frame."""
    bone = np.asarray(bone, dtype=np.float64)
    middle = bone[:3, 3] + bone[:3, :3] @ np.asarray(center, dtype=np.float64)
    return unit(bone[:3, :3].T @ (np.asarray(eye, dtype=np.float64) - middle))


def box(card, cell, px_per_m, relief=True):
    """The part of the sheet a card must cover: (left, bottom, right, top) in the sheet's own metres. The
    picture's four corners as they now show, and (relief) room for its pixels to lean, by how low and
    high the picture's surface goes."""
    _, _, w, h, ax, ay, low, high = cell
    spots = np.array([[(cx - ax) / px_per_m, (cy - ay) / px_per_m] for cx, cy in ((0, 0), (w, 0), (w, h), (0, h))]) @ card["turn_xy"].T
    lean = card["lean"] if relief else np.zeros(2)
    return np.concatenate([spots.min(axis=0) + np.minimum(lean * low, lean * high), spots.max(axis=0) + np.maximum(lean * low, lean * high)])


def corners(card, cell, px_per_m, relief=True):
    """The four corners of a card in the world: left-bottom, right-bottom, right-top, left-top."""
    x0, y0, x1, y1 = box(card, cell, px_per_m, relief)
    return np.array([card["head"] + card["size"] * (x * card["e2"] + y * card["e1"]) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))])


def march_steps(card, cell, px_per_m):
    """How many steps the search down a pixel's line takes: enough that none is longer than MARCH_PX of the picture."""
    reach = float(np.linalg.norm(card["back"] @ card["lean"])) * (cell[7] - cell[6]) * px_per_m
    return int(min(MARCH_MAX, max(1, math.ceil(reach / MARCH_PX))))


# ---------- cutting a character into parts ----------

def round_cut(points, pull, edges, corners, begin, sides, joints, lap, smooth_m, less=None, ball=0.9, ball_reach=1.0, pulled=None):
    """Which part owns each face of a mesh, and which faces each part also takes from next door, so that a
    joint can bend without opening. The arithmetic of bake_impostor.py's cut, with no Blender in it.

    points   Vx3, where every point of the mesh is (m)
    pull     VxP, how much each part's bones pull on each point
    edges    Ex2, the mesh's edges (two points each)
    corners, begin, sides   the faces: every face's points one after another, where each face starts in
             that list, and how many points it has
    joints   [(part, part, where the joint is)]: the pairs of parts that meet at a joint, as columns of `pull`,
             and the point the two turn about (None: no ball is worked out for it)
    lap      how far a part reaches into its neighbour, as a share of the radius of the ring where they meet
    smooth_m the pull is first evened out along the surface over about this far
    less     {(taker, giver): share} for a pair that should lap less than `lap`
    pulled   P numbers, or None: a part also takes a neighbour's face when its own bones pull on that face by at
             least its number (the skin under an arm goes up with the arm)
    ball     how big the ball in a joint is, as a share of the room there is for it
    ball_reach  the faces a ball is made of: the two parts' within this many ring radii of the ring

    A part owns the faces its bones pull on most. But the pull is first evened out along the surface, so the
    line between two parts is one clean ring round the limb. (A detailed mesh takes its weights from the nearest
    place on a coarse one, and the line between two parts then follows the coarse mesh's triangles: a fringe of
    splinters centimetres long, which comb apart as soon as the joint bends.) Then two parts that meet at a
    joint each take everything of the other's within reach of the ring where they meet: `lap` times the ring's
    own radius, so a thigh laps further than a wrist; and any face its own bones still pull on a good deal
    (`pulled`), which is how the skin under an arm goes up with the arm. A lap closes the outside of a bend only up to a point
    (two tubes of radius r that lap by L meet on the outside until the bend passes 2 atan(L / r)), and a long lap
    stands out as a spur when the joint bends only a little. So the lap is kept short and the joint gets a ball:
    the faces round the ring, pulled in onto a ball about the point the joint turns on, as big as fits inside
    the body there. However the joint turns, the ball is where it was; it shows only through the gap a bend
    opens, in the colours of the skin that was there, and it shuts the open end of the limb.

    Returns (owner: F, the part that owns each face; lapped: PxF, True where a part takes a face it does not
    own; rings: {(part, part): the ring's radius in metres} for every joint whose two parts do meet; balls:
    {(part, part): (the ball's radius in metres, F: True for the faces it is made of)})."""
    points, pull = np.asarray(points, dtype=np.float64), np.asarray(pull, dtype=np.float32)
    corners, begin, sides = np.asarray(corners, dtype=np.int64), np.asarray(begin, dtype=np.int64), np.asarray(sides, dtype=np.int64)
    parts = pull.shape[1]
    # points at the same place are one point: a mesh from a .glb is split along every seam of its texture
    _, first, weld = np.unique(np.round(points / 1e-4).astype(np.int64), axis=0, return_index=True, return_inverse=True)
    weld = weld.reshape(-1)
    spot = points[first]
    merged = np.zeros((len(first), parts), dtype=np.float32)
    np.add.at(merged, weld, pull)
    merged /= np.maximum(merged.sum(axis=1, keepdims=True), 1e-9)
    ends = weld[np.asarray(edges, dtype=np.int64).reshape(-1, 2)]
    ends = ends[ends[:, 0] != ends[:, 1]]
    if len(ends) and smooth_m > 0:
        both = np.concatenate([ends, ends[:, ::-1]])
        both = both[np.argsort(both[:, 0], kind="stable")]
        starts = np.concatenate([[0], np.nonzero(np.diff(both[:, 0]))[0] + 1])
        rows, many = both[starts, 0], np.diff(np.concatenate([starts, [len(both)]]))[:, None]
        edge = float(np.median(np.linalg.norm(spot[ends[:, 0]] - spot[ends[:, 1]], axis=1)))
        # one round spreads a point's pull about half an edge's length; rounds add up as squares do
        for _ in range(int(min(400, round(4.0 * (smooth_m / edge) ** 2)))):
            merged[rows] = 0.5 * merged[rows] + 0.5 * np.add.reduceat(merged[both[:, 1]], starts, axis=0) / many
    corners = weld[corners]
    share = np.add.reduceat(merged[corners], begin, axis=0) / sides[:, None]
    owner = share.argmax(axis=1)
    middle = np.add.reduceat(spot[corners], begin, axis=0) / sides[:, None]
    touched = np.zeros((len(first), parts), dtype=bool)  # which parts own a face at each point
    touched[corners, np.repeat(owner, sides)] = True
    lapped = np.zeros((parts, len(owner)), dtype=bool)
    rings, balls = {}, {}
    for a, b, centre in joints:
        ring = spot[touched[:, a] & touched[:, b]]
        if len(ring) < 3:
            continue
        radius = float(np.median(np.linalg.norm(ring - ring.mean(axis=0), axis=1)))
        rings[(a, b)] = radius
        some = ring[:: max(1, len(ring) // 96)]
        theirs = np.nonzero((owner == a) | (owner == b))[0]
        off = np.concatenate([np.linalg.norm(middle[theirs[i:i + 20000]][:, None, :] - some[None, :, :], axis=2).min(axis=1) for i in range(0, len(theirs), 20000)])
        for taker, giver in ((a, b), (b, a)):
            reach = off <= radius * (less or {}).get((taker, giver), lap)
            if pulled is not None and (taker, giver) not in (less or {}):
                reach = reach | (share[theirs, taker] >= pulled[taker])
            lapped[taker, theirs[(owner[theirs] == giver) & reach]] = True
        if centre is not None and ball > 0:
            # as big as fits: inside the nearest of the ring, and inside the nearest skin of all
            room = min(float(np.percentile(np.linalg.norm(ring - centre, axis=1), 10)), float(np.percentile(np.linalg.norm(spot - centre, axis=1), 0.5)))
            made = np.zeros(len(owner), dtype=bool)
            made[theirs[off <= radius * ball_reach]] = True
            balls[(a, b)] = (ball * room, made)
    return owner, lapped, rings, balls


# ---------- the folds of a part, found in its picture ----------

def folds(height, normal, known, step_m=0.02, turn=0.3):
    """Where a picture of a part shows a fold: True on the further pixel wherever the surface steps back by more
    than step_m from one pixel to the next (one fold of the body in front of another: a nostril, a lock of hair,
    the jaw over the neck), or turns by more than about 70 degrees (a crease) and is no nearer.

    height  HxW, how far each pixel's surface stands toward the eye (m);  normal  HxWx3, which way it faces
    known   HxW, True where the part is"""
    out = np.zeros_like(known)
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        near_h, near_n, near_k = np.roll(height, (dy, dx), axis=(0, 1)), np.roll(normal, (dy, dx), axis=(0, 1)), np.roll(known, (dy, dx), axis=(0, 1))
        out |= known & near_k & ((near_h - height > step_m) | (((normal * near_n).sum(axis=-1) < turn) & (near_h >= height)))
    return out


# ---------- colours, and the two ways a picture's numbers are packed ----------

def to_linear(c):
    c = np.asarray(c, dtype=np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_screen(c):
    c = np.clip(np.asarray(c, dtype=np.float32), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1.0 / 2.4) - 0.055)


def pack_normal(n):
    """A unit direction as two numbers 0..1 (folded onto an eight-sided shape, then flattened)."""
    n = np.asarray(n, dtype=np.float32)
    n = n / np.maximum(np.abs(n).sum(axis=-1, keepdims=True), 1e-9)
    x, y, z = n[..., 0], n[..., 1], n[..., 2]
    fold = z < 0
    fx = np.where(fold, (1.0 - np.abs(y)) * np.where(x >= 0, 1.0, -1.0), x)
    fy = np.where(fold, (1.0 - np.abs(x)) * np.where(y >= 0, 1.0, -1.0), y)
    return np.stack([fx * 0.5 + 0.5, fy * 0.5 + 0.5], axis=-1)


def unpack_normal(e):
    e = np.asarray(e, dtype=np.float32) * 2.0 - 1.0
    x, y = e[..., 0], e[..., 1]
    z = 1.0 - np.abs(x) - np.abs(y)
    t = np.clip(-z, 0.0, 1.0)
    x = x + np.where(x >= 0, -t, t)
    y = y + np.where(y >= 0, -t, t)
    n = np.stack([x, y, z], axis=-1)
    return n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-9)


# ---------- .png files, read and written without any package ----------

def write_png(path, pixels):
    """pixels: rows from the bottom up (as a texture has them), uint8, 3 or 4 numbers a pixel."""
    pixels = np.ascontiguousarray(pixels[::-1])
    tall, wide, deep = pixels.shape
    # Each row as it is, as its change from the pixel to the left, or from the row above: whichever packs smallest.
    best = None
    for kind in (0, 1, 2):
        rows = np.full((tall, wide * deep + 1), kind, dtype=np.uint8)
        if kind == 0:
            rows[:, 1:] = pixels.reshape(tall, wide * deep)
        elif kind == 1:
            rows[:, 1:] = (pixels - np.concatenate([np.zeros((tall, 1, deep), dtype=np.uint8), pixels[:, :-1]], axis=1)).reshape(tall, wide * deep)
        else:
            rows[:, 1:] = (pixels - np.concatenate([np.zeros((1, wide, deep), dtype=np.uint8), pixels[:-1]], axis=0)).reshape(tall, wide * deep)
        packed = zlib.compress(rows.tobytes(), 9)
        if best is None or len(packed) < len(best):
            best = packed

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", wide, tall, 8, 6 if deep == 4 else 2, 0, 0, 0))
                + chunk(b"IDAT", best) + chunk(b"IEND", b""))


def read_png(path):
    """An 8-bit RGB or RGBA .png as rows from the bottom up. Quick for files written here; any other is slower."""
    with open(path, "rb") as f:
        data = f.read()
    at, body, wide, tall, deep = 8, b"", 0, 0, 0
    while at < len(data):
        length, kind = struct.unpack(">I4s", data[at:at + 8])
        if kind == b"IHDR":
            wide, tall, bits, colour = struct.unpack(">IIBB", data[at + 8:at + 18])
            if bits != 8 or colour not in (2, 6):
                raise ValueError("%s: only 8-bit RGB and RGBA .png files are read here" % path)
            deep = 4 if colour == 6 else 3
        elif kind == b"IDAT":
            body += data[at + 8:at + 8 + length]
        at += 12 + length
    raw = np.frombuffer(zlib.decompress(body), dtype=np.uint8).reshape(tall, wide * deep + 1)
    kinds, rows = raw[:, 0], raw[:, 1:].astype(np.uint8).copy()
    if kinds.any():
        before = np.zeros(wide * deep, dtype=np.int32)
        for y in range(tall):
            row, kind = rows[y].astype(np.int32), int(kinds[y])
            if kind == 1:
                row = np.cumsum(row.reshape(wide, deep), axis=0).reshape(-1) & 255
            elif kind == 2:
                row = (row + before) & 255
            elif kind in (3, 4):
                for i in range(wide * deep):
                    left = row[i - deep] if i >= deep else 0
                    if kind == 3:
                        row[i] = (row[i] + ((left + before[i]) >> 1)) & 255
                    else:
                        corner = before[i - deep] if i >= deep else 0
                        guess = left + before[i] - corner
                        pa, pb, pc = abs(guess - left), abs(guess - before[i]), abs(guess - corner)
                        row[i] = (row[i] + (left if pa <= pb and pa <= pc else before[i] if pb <= pc else corner)) & 255
            rows[y] = row
            before = row
    return rows.reshape(tall, wide, deep)[::-1].copy()


# ---------- a .glb's skeleton and how it moves, read straight from the file ----------

def quat_matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


class Glb:
    """The nodes of a .glb and its first animation. pose(t) gives every node's matrix in the world at t seconds."""

    KINDS = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
    WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

    def __init__(self, path):
        with open(path, "rb") as f:
            f.read(12)
            size, _ = struct.unpack("<I4s", f.read(8))
            self.doc = json.loads(f.read(size))
            size, _ = struct.unpack("<I4s", f.read(8))
            self.bin = f.read(size)
        doc = self.doc
        self.names = [n.get("name", "") for n in doc["nodes"]]
        self.parent = [-1] * len(doc["nodes"])
        for i, n in enumerate(doc["nodes"]):
            for kid in n.get("children", []):
                self.parent[kid] = i
        self.order = []
        todo = [i for i, p in enumerate(self.parent) if p < 0]
        while todo:
            i = todo.pop()
            self.order.append(i)
            todo += doc["nodes"][i].get("children", [])
        self.rest = [(np.array(n.get("translation", [0, 0, 0]), dtype=np.float64), np.array(n.get("rotation", [0, 0, 0, 1]), dtype=np.float64),
                      np.array(n.get("scale", [1, 1, 1]), dtype=np.float64)) for n in doc["nodes"]]
        self.tracks, self.seconds, self.clip = [], 0.0, None
        if doc.get("animations"):
            clip = doc["animations"][0]
            self.clip = clip.get("name")
            for ch in clip["channels"]:
                sampler = clip["samplers"][ch["sampler"]]
                times = self.numbers(sampler["input"]).astype(np.float64)
                self.tracks.append((ch["target"]["node"], ch["target"]["path"], times, self.numbers(sampler["output"]).astype(np.float64), sampler.get("interpolation", "LINEAR")))
                self.seconds = max(self.seconds, float(times[-1]))

    def numbers(self, index):
        acc = self.doc["accessors"][index]
        view = self.doc["bufferViews"][acc["bufferView"]]
        wide = self.WIDTH[acc["type"]]
        start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        got = np.frombuffer(self.bin, dtype=self.KINDS[acc["componentType"]], count=acc["count"] * wide, offset=start)
        return got.reshape(acc["count"], wide) if wide > 1 else got

    def pose(self, t=None):
        """{node name: 4x4 matrix in the world}. t in seconds (the clip is held at its ends); None is the rest pose."""
        now = [list(r) for r in self.rest]
        if t is not None:
            for node, path, times, values, how in self.tracks:
                if t <= times[0]:
                    v = values[0]
                elif t >= times[-1]:
                    v = values[-1]
                else:
                    k = int(np.searchsorted(times, t, side="right")) - 1
                    f = 0.0 if how == "STEP" else (t - times[k]) / (times[k + 1] - times[k])
                    a, b = values[k], values[k + 1]
                    if path == "rotation":
                        dot = float(a @ b)
                        if dot < 0:
                            b, dot = -b, -dot
                        if dot > 0.9995:
                            v = a + (b - a) * f
                        else:
                            angle = math.acos(dot)
                            v = (math.sin((1 - f) * angle) * a + math.sin(f * angle) * b) / math.sin(angle)
                        v = v / np.linalg.norm(v)
                    else:
                        v = a + (b - a) * f
                now[node][{"translation": 0, "rotation": 1, "scale": 2}[path]] = v
        world = [None] * len(now)
        for i in self.order:
            m = np.eye(4)
            m[:3, :3] = quat_matrix(now[i][1]) * now[i][2]
            m[:3, 3] = now[i][0]
            world[i] = m if self.parent[i] < 0 else world[self.parent[i]] @ m
        return {name: world[i] for i, name in enumerate(self.names)}

    def triangles(self):
        prims = [p for m in self.doc.get("meshes", []) for p in m["primitives"]]
        return sum(self.doc["accessors"][p["indices"]]["count"] // 3 for p in prims)


# ---------- the eye ----------

class Eye:
    """A camera: where it is, what it looks at, how tall its view is in degrees, and the picture's size."""

    def __init__(self, at, aim, fov_deg=30.0, size=(480, 540), near=0.1, far=100.0, shift=(0.0, 0.0)):
        self.at, self.aim = np.asarray(at, dtype=np.float64), np.asarray(aim, dtype=np.float64)
        self.fov_deg, self.size, self.near, self.far = float(fov_deg), tuple(size), near, far
        self.shift = (float(shift[0]), float(shift[1]))  # the whole picture slid this many pixels right and up: the same view on a grid that sits elsewhere
        back = unit(self.at - self.aim)
        right = unit(np.cross([0.0, 1.0, 0.0], back))
        self.turn = np.stack([right, np.cross(back, right), back], axis=1)  # columns: right, up, back
        self.tan = math.tan(math.radians(self.fov_deg) / 2.0)

    def to_pixels(self, points):
        """World points to picture pixels (x from the left, y from the bottom) and their distance in front."""
        rel = (np.asarray(points) - self.at) @ self.turn
        wide, tall = self.size
        ahead = -rel[..., 2]
        x = (rel[..., 0] / (ahead * self.tan * wide / tall) * 0.5 + 0.5) * wide + self.shift[0]
        y = (rel[..., 1] / (ahead * self.tan) * 0.5 + 0.5) * tall + self.shift[1]
        return np.stack([x, y], axis=-1), ahead

    def m_per_px(self, point):
        """How big one pixel is at a point, in metres."""
        ahead = -float((np.asarray(point) - self.at) @ self.turn[:, 2])
        return 2.0 * ahead * self.tan / self.size[1]


# ---------- a baked character, and drawing it ----------

class Character:
    """What bake_impostor.py wrote: impostor.json and one view set's two picture sheets."""

    def __init__(self, folder, views=None):
        with open(os.path.join(folder, "impostor.json")) as f:
            self.card = json.load(f)
        self.folder = folder
        self.px_per_m = float(self.card["px_per_m"])
        self.parts = self.card["parts"]
        self.use(views or self.card["default_views"])

    def use(self, name):
        sheet = self.card["sets"][name]
        self.set_name, self.sheet = name, sheet
        self.views = sheet["views"]
        self.dirs = np.array([v["d"] for v in self.views])
        self.colour = read_png(os.path.join(self.folder, sheet["color"])).astype(np.float32) / 255.0
        self.data = read_png(os.path.join(self.folder, sheet["data"])).astype(np.float32) / 255.0
        self.cells = sheet["cells"]
        lit = np.round(self.colour * 255.0)
        self.balls, self.tints, self.pixel = part_balls(self.card), getattr(self, "tints", {}), lambda x, y: lit[y, x]


def card_pixels(character, part, view_index, card, eye, relief=True, line="shell", keep_dark=False, balls=None):
    """One card as the eye sees it: (x0, y0, colour HxWx3 as stored, cover HxW 0..1, normal HxWx3 in the bone's
    frame, distance in front HxW, HxW True where the pixel is the part's ink line), or None when it is off the
    picture. The page's fragment shader, slowly.
    relief: slide each pixel by the picture's depth (False: the picture is laid flat on the card).
    line: what becomes of the ink line round the part, on a sheet that marks it (line_marked): "shell" stands it
    LINE_BACK_M behind the surface, "off" leaves it out (the line is then drawn on the finished picture).
    keep_dark: where the picture is shown smaller than it was taken (one pixel of the eye's covers more than one of
    the sheet's), a pixel takes the darkest of what it covers when that is a good deal darker than its middle: an
    eye or a brow one sheet pixel wide is kept, where reading only the middle would drop it on every other frame.
    balls: this part's joints where they are now (joint_balls): a see-through pixel near one is filled, and each
    has a ball in it."""
    cell = character.cells[part["name"]][view_index]
    x0, y0, w, h, ax, ay, low, high = cell
    if w <= 0 or h <= 0:
        return None
    ppm = float(part.get("px_per_m") or character.px_per_m)  # a part pictured finer than the rest (a head) says so
    quad = corners(card, cell, ppm, relief)
    spots, ahead = eye.to_pixels(quad)
    if (ahead <= eye.near).any():
        return None
    wide, tall = eye.size
    lo = np.maximum(np.floor(spots.min(axis=0)).astype(int), 0)
    hi = np.minimum(np.ceil(spots.max(axis=0)).astype(int), [wide, tall])
    if (hi <= lo).any():
        return None
    xs, ys = np.meshgrid(np.arange(lo[0], hi[0]) + 0.5, np.arange(lo[1], hi[1]) + 0.5)
    ray_cam = np.stack([((xs - eye.shift[0]) / wide * 2 - 1) * eye.tan * wide / tall, ((ys - eye.shift[1]) / tall * 2 - 1) * eye.tan, -np.ones_like(xs)], axis=-1)
    ray = ray_cam @ eye.turn.T
    toward, head = card["toward"], card["head"]
    along_ray = (toward @ (head - eye.at)) / (ray @ toward)
    world = eye.at + ray * along_ray[..., None]
    reach = np.linalg.norm(eye.at - world, axis=-1)
    toward_eye = (eye.at - world) / reach[..., None]
    balls = balls or []
    rel = (world - head) / card["size"]
    sheet = np.stack([rel @ card["e2"], rel @ card["e1"]], axis=-1)  # P: across and up on the card
    sheet_tall, sheet_wide = character.colour.shape[:2]
    back, lean = card["back"], card["lean"]

    def read(xy):
        """The data sheet at a place of the picture: (is there surface here, how high, the pixel's numbers)."""
        cx, cy = xy[..., 0] * ppm + ax, xy[..., 1] * ppm + ay
        inside = (cx >= 0) & (cx < w) & (cy >= 0) & (cy < h)
        data = character.data[np.clip(np.floor(y0 + cy).astype(int), 0, sheet_tall - 1), np.clip(np.floor(x0 + cx).astype(int), 0, sheet_wide - 1)]
        return inside & (data[..., 2] > 0.5 / 255.0), (data[..., 2] * 2.0 - 1.0) * part["depth_m"], data

    if relief:
        # Down each pixel's line from above the picture's highest point to below its lowest: the first step
        # that is under the surface, then halved in on. A place found far under the surface is the side of
        # something the picture never saw the back of: the search goes on from there, under it, to the next
        # place the line comes down onto the surface.
        steps = march_steps(card, cell, ppm)
        top, bottom = high + 0.002, low - 0.002
        above, below = np.full(xs.shape, top), np.full(xs.shape, bottom)
        found, was, over = np.zeros(xs.shape, dtype=bool), np.zeros(xs.shape, dtype=bool), np.zeros(xs.shape, dtype=bool)
        walled, wall_at = np.zeros(xs.shape, dtype=bool), np.full(xs.shape, bottom)
        round_ = balls if "joint" in FILL else []
        for i in range(1, steps + 1):
            at = top + (bottom - top) * i / steps
            spot = (sheet - at * lean) @ back.T
            there, height, _ = read(spot)
            under = there & (height >= at)
            if round_ and (under & ~found & ~walled).any():
                # under the surface, and inside a joint's ball: the first such place on the line is kept for the filling
                here = world + toward_eye * ((spot[..., 0] * card["deep"][0] + spot[..., 1] * card["deep"][1] + at * card["deep"][2]) * card["size"])[..., None]
                inside_ball = np.zeros(xs.shape, dtype=bool)
                for centre, ring, _, _, _ in round_:
                    inside_ball |= ((here - centre) ** 2).sum(axis=-1) < ring * ring
                first = under & ~found & ~walled & inside_ball
                wall_at[first] = at
                walled |= first
            new = under & ~was & ~found & ~over
            if new.any():  # only the pixels whose line has just gone under
                rows, cols = np.nonzero(new)
                mine, a, b = sheet[rows, cols], above[rows, cols], np.full(len(rows), at)
                for _ in range(REFINE):
                    mid = (a + b) / 2.0
                    there, height, _ = read((mine - mid[:, None] * lean) @ back.T)
                    deep = there & (height >= mid)
                    b, a = np.where(deep, mid, b), np.where(deep, a, mid)
                there, height, _ = read((mine - b[:, None] * lean) @ back.T)
                hit = there & (height - b < WALL_M + (top - bottom) / steps / 2 ** REFINE)
                below[rows[hit], cols[hit]] = b[hit]
                found[rows[hit], cols[hit]] = True
                if not GO_ON:
                    over[rows[~hit], cols[~hit]] = True
            above[~under & ~found] = at
            was = under
        # Filling a joint. A line that went in only by the side of something, and came down on no surface after,
        # shows nothing: a see-through pixel, and at a bent joint that is the tear in the figure. The picture
        # never saw what is there. But inside a joint's ball, under the part's own surface, there is body: the
        # limb goes on into the next part. So such a pixel is filled where its line first runs under the surface
        # inside a joint's ball, in the colour of the surface over that place, standing a little behind it so
        # that anything truly there covers it. Along the side of a limb, away from any joint, nothing is filled.
        skirt = walled & ~found
        below[skirt] = wall_at[skirt]
        found = found | skirt
        xy = (sheet - below[..., None] * lean) @ back.T
        there, height, data = read(xy)
        if skirt.any() and character.card.get("line_marked"):
            # the edge of a picture is its ink line: the colour is taken from a little further in along the line
            run = float(np.linalg.norm(back @ lean)) * ppm  # pixels of the picture the line crosses for a metre it drops
            for _ in range(3):
                edge = skirt & (data[..., 0] < 0.5 / 255.0) & (data[..., 1] < 0.5 / 255.0)
                if not edge.any() or run < 1e-6:
                    break
                further = below - np.where(edge, 2.0 / run, 0.0)
                there2, height2, data2 = read((sheet - further[..., None] * lean) @ back.T)
                take = edge & there2 & (height2 >= further)
                below, xy = np.where(take, further, below), np.where(take[..., None], (sheet - further[..., None] * lean) @ back.T, xy)
                height, data = np.where(take, height2, height), np.where(take[..., None], data2, data)
        height = np.where(skirt, below - FILL_BACK_M, height)
        inside = found & there
    else:
        xy = sheet @ back.T
        inside, height, data = read(xy)
    if not inside.any():
        return None
    cx, cy = xy[..., 0] * ppm + ax, xy[..., 1] * ppm + ay
    u, v = x0 + cx, y0 + cy
    # colour: smoothed between the four pixels around, as a texture is
    fu, fv = u - 0.5, v - 0.5
    iu, iv = np.floor(fu).astype(int), np.floor(fv).astype(int)
    tu, tv = (fu - iu)[..., None], (fv - iv)[..., None]
    grab = lambda a, b: character.colour[np.clip(b, 0, sheet_tall - 1), np.clip(a, 0, sheet_wide - 1)]
    rgba = (grab(iu, iv) * (1 - tu) + grab(iu + 1, iv) * tu) * (1 - tv) + (grab(iu, iv + 1) * (1 - tu) + grab(iu + 1, iv + 1) * tu) * tv
    if character.card.get("nearest"):  # pixel art is read without smoothing: the one pixel it falls in
        rgba = grab(np.floor(u).astype(int), np.floor(v).astype(int))
        covers = ppm * eye.m_per_px(head) / card["size"]  # how many of the sheet's pixels one of the eye's is across
        if keep_dark and covers > 1.0:
            rgba = rgba.copy()
            grey = lambda c: c[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
            best = grey(rgba)
            middle = best.copy()
            reach = min(covers, 3.0) / 3.0
            for du, dv in ((reach, 0.0), (-reach, 0.0), (0.0, reach), (0.0, -reach)):
                iu, iv = np.clip(np.floor(u + du).astype(int), 0, sheet_wide - 1), np.clip(np.floor(v + dv).astype(int), 0, sheet_tall - 1)
                near, near_d = character.colour[iv, iu], character.data[iv, iu]
                same = (near[..., 3] > 0.5) & (near_d[..., 2] > 0.5 / 255.0) & (np.abs((near_d[..., 2] * 2.0 - 1.0) * part["depth_m"] - height) < KEEP_M) & ((near_d[..., 0] + near_d[..., 1]) > 0.5 / 255.0)
                take = same & (grey(near) < best) & (grey(near) < middle - KEEP_DARK)
                rgba[take] = near[take]
                best = np.where(take, grey(near), best)
    # facing and depth: the one pixel it falls in
    normal = unpack_normal(data[..., :2])
    # (a sheet from before the line was marked gave its line the picture's own direction for a facing, to the last digit)
    inked = (normal @ np.asarray(character.views[view_index]["d"], dtype=np.float32)) > 0.99995
    if character.card.get("line_marked"):
        # The ink line is marked in the data sheet (both of its facing's numbers are 0). It faces the eye, and it
        # is a shell behind the surface: whatever of the figure is beside it, a hair nearer, covers it.
        inked = (data[..., 0] < 0.5 / 255.0) & (data[..., 1] < 0.5 / 255.0)
        normal = np.where(inked[..., None], np.asarray(card["turn"].T @ card["toward"], dtype=np.float32), normal)
        if line == "off":
            inside = inside & ~inked
        rgba = rgba.copy()
        rgba[..., :3] = np.where(inked[..., None], np.array(INK, dtype=np.float32), rgba[..., :3])  # the sheet holds no ink: the line is painted here
        height = height - np.where(inked, LINE_BACK_M, 0.0)
    out = (xy[..., 0] * card["deep"][0] + xy[..., 1] * card["deep"][1] + height * card["deep"][2]) * card["size"]
    point = world + toward_eye * out[..., None]
    ahead = -((point - eye.at) @ eye.turn[:, 2])
    cover = np.where(inside, rgba[..., 3], 0.0)
    inked = inked & inside
    rgb = rgba[..., :3]
    if balls and "ball" in FILL:
        # The ball in a joint. A ball about each of this part's joints, small enough to lie inside the body, in
        # this part's own colour near the joint (the part next door draws the same ball in its colour, and the one
        # whose body is behind the ball, as the eye sees it, is the one that shows). Wherever the eye's own line
        # through a pixel meets one before it meets the picture's surface, the ball is what shows: the eye is
        # looking in at the open end of the part, at the inside of its far wall, and the ball stops the hollow.
        # Skin is nearer than the ball everywhere else, and covers it. Where the picture has no surface at all
        # the ball is not drawn: beside a thin arm in a wide sleeve there is nothing, and a ball would be a knob.
        surface = np.where(cover >= 0.5, reach - out, np.inf)  # how far along the eye's line the picture's surface is
        nearest, colour, facing = surface.copy(), np.zeros(rgb.shape, dtype=np.float32), np.zeros(rgb.shape, dtype=np.float64)
        for centre, _, inner, tint, back in balls:
            off = centre - eye.at
            along = -(toward_eye @ off)                       # the eye's line runs from the eye away through the pixel
            under_root = along * along - off @ off + inner * inner
            hit = (under_root >= 0.0) & (inner > 0.0)
            far = along - np.sqrt(np.where(hit, under_root, 0.0)) + back
            take = hit & (far > back) & (far < nearest) & (cover >= 0.5)
            nearest = np.where(take, far, nearest)
            colour[take] = tint
            facing[take] = ((eye.at - toward_eye * (far - back)[..., None] - centre) / max(inner, 1e-9))[take]
        ball = nearest < surface
        if ball.any():
            rgb, normal = np.where(ball[..., None], colour, rgb), np.where(ball[..., None], facing @ card["turn"], normal)
            ahead = np.where(ball, -((-toward_eye * nearest[..., None]) @ eye.turn[:, 2]), ahead)
            cover, inked = np.where(ball, 1.0, cover), inked & ~ball
    return int(lo[0]), int(lo[1]), rgb, cover, normal, ahead, inked


def own_tint(card, sheet, part, at, reach_m, pixel):
    """The colour a part gives the ball of one of its joints: the middle colour (each of red, green and blue by
    itself) of what the part's own pictures show round a place on it, seen from the side.
    part: one of the card's parts;  at: the place, in the bone's frame (m);  reach_m: how far round it to look;
    sheet: one view set of the card ("views", "cells");  pixel(x, y): the colour sheet's pixel x from the left and
    y from the bottom, four numbers 0 to 255. gallery/impostor-math.js has the same (ownTint).
    Returns three numbers 0 to 1, as the sheet stores colour."""
    ppm = float(part.get("px_per_m") or card["px_per_m"])
    reach = max(2.0, reach_m * ppm)
    seen = [[], [], []]
    for view, cell in zip(sheet["views"], sheet["cells"][part["name"]]):
        x0, y0, wide, tall, ax, ay = cell[:6]
        if abs(view["d"][1]) >= 0.5 or wide <= 0 or tall <= 0:
            continue
        mx = ax + ppm * (at[0] * view["r"][0] + at[1] * view["r"][1] + at[2] * view["r"][2])
        my = ay + ppm * (at[0] * view["u"][0] + at[1] * view["u"][1] + at[2] * view["u"][2])
        for cy in range(max(0, int(math.floor(my - reach))), min(tall, int(math.ceil(my + reach)) + 1)):
            for cx in range(max(0, int(math.floor(mx - reach))), min(wide, int(math.ceil(mx + reach)) + 1)):
                if (cx + 0.5 - mx) ** 2 + (cy + 0.5 - my) ** 2 > reach * reach:
                    continue
                got = pixel(x0 + cx, y0 + cy)
                if got[3] >= 128:
                    for k in range(3):
                        seen[k].append(int(got[k]))
    if not seen[0]:
        return [0.5, 0.5, 0.5]
    return [sorted(channel)[len(channel) // 2] / 255.0 for channel in seen]


def tint_place(joint_at, center, ring):
    """Where on a part to look for the colour it gives a joint's ball: TINT_IN of the joint's ring radius in from
    the joint toward the middle of the part. All in the bone's frame."""
    joint_at, center = np.asarray(joint_at, dtype=np.float64), np.asarray(center, dtype=np.float64)
    return joint_at + unit(center - joint_at) * (TINT_IN * ring)


def part_balls(card):
    """{part name: [(the bone whose head is a joint of that part, the radius the joint is filled within, the
    radius of the ball in it)]}, in metres at the bone's own size, from what a bake says of its joints (the ring
    where the two parts meet, and the ball it found room for inside the body there). A sheet baked before the
    joints were mended says nothing of them and gets none."""
    out = {}
    for joint in card.get("joints") or []:
        for name in joint["between"]:
            out.setdefault(name, []).append((joint["bone"], FILL_BALL * joint["ring_cm"] / 100.0, FILL_INNER * joint["ball_cm"] / 100.0))
    return {name: balls[:BALLS_A_PART] for name, balls in out.items()}


def ball_back(joint_at, middle, eye_at):
    """How far back a part stands the ball of one of its joints (m): nothing when the part's own body is straight
    behind the ball as the eye sees it (the eye is looking in at that part's open end, and the ball is that part's
    to colour), BALL_BACK_M when it is straight in front. joint_at, middle (of the part), eye_at: in the world."""
    joint_at = np.asarray(joint_at, dtype=np.float64)
    return BALL_BACK_M * (1.0 - float(unit(np.asarray(middle) - joint_at) @ unit(joint_at - np.asarray(eye_at)))) / 2.0


def joint_balls(character, part, bone, pose, eye_at):
    """A part's joints where they are now: [(the joint in the world, the radius it is filled within, the radius
    of the ball in it, the colour this part gives the ball, how far back it stands it)], in metres as the world has
    them. bone: the part's bone in the world; pose: every bone in the world. The colour is looked up the first time
    (where the joint is on the part hardly changes) and kept."""
    bone = np.asarray(bone, dtype=np.float64)
    turn = bone[:3, :3]
    size = float(np.cbrt(abs(np.linalg.det(turn))))
    middle = bone[:3, 3] + turn @ np.asarray(part["center"], dtype=np.float64)
    out = []
    for name, ring, inner in character.balls.get(part["name"], []):
        if name not in pose:
            continue
        at = np.asarray(pose[name], dtype=np.float64)[:3, 3]
        key = (character.set_name, part["name"], name)
        if key not in character.tints:
            character.tints[key] = np.asarray(own_tint(character.card, character.sheet, part, tint_place((turn / size).T @ (at - bone[:3, 3]) / size, part["center"], ring), TINT_REACH * inner, character.pixel), dtype=np.float32)
        out.append((at, ring * size, inner * size, character.tints[key], ball_back(at, middle, eye_at)))
    return out


def tones(normal_bone, turn, eye, light=LIGHT, shade=SHADE, edges=EDGES):
    """What each pixel's colour is multiplied by: one of three flat tones, by how far the surface faces the light."""
    facing = (normal_bone @ turn.T) @ (eye.turn @ unit(light))
    out = np.ones(facing.shape + (3,), dtype=np.float32)
    out[facing <= edges[0]] = shade[0]
    out[facing <= edges[1]] = shade[1]
    return out


def painted(rgb, normal_bone, turn, eye, paint):
    """A card's pixels in a look's paint (the page's shader: CARD_FRAGMENT): the stored colour made stronger or
    weaker (punch), one of the look's flat tones by how far the surface faces the light, and a little light on
    the rim. rgb as stored (0 to 1, as the screen has it); returns light as it adds up (to_screen for the screen)."""
    world = normal_bone @ turn.T
    facing = world @ (eye.turn @ unit(LIGHT))
    tone = np.ones(facing.shape + (3,), dtype=np.float32)
    tone[facing <= paint["edges"][0]] = paint["shade"][0]
    tone[facing <= paint["edges"][1]] = paint["shade"][1]
    lit = to_linear(rgb)
    grey = lit @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    lit = grey[..., None] + (lit - grey[..., None]) * paint["punch"]
    rim = paint["rim"] * (1.0 - np.clip(world @ eye.turn[:, 2], 0.0, 1.0)) ** 3 * (facing >= paint["edges"][0])
    return lit * tone + rim[..., None]


def cut_levels(picture, levels):
    """A finished picture's colours cut to a few steps a channel, as the eye sees them (looks.js: levels)."""
    if not levels:
        return picture
    out = picture.copy()
    lit = to_linear(picture[..., :3].astype(np.float32) / 255.0)
    out[..., :3] = np.round(to_screen((np.floor(lit ** (1.0 / 2.2) * levels + 0.5) / levels) ** 2.2) * 255.0)
    return out


def draw(character, pose, eye, relief=True, blend=False, held=None, only=None, forced=None, line="shell", who=None, figure=0, lines=None, paint=None, keep_dark=False):
    """The character as cards, in one pose, through one eye.

    pose    {bone name: 4x4 matrix in the world}
    relief  slide each card's pixels by the picture's depth (False: every picture laid flat on its card)
    held    {part name: the view shown last time}: give the same dict back every frame and a view is
            kept until another is clearly nearer; None picks the nearest every time
    blend   mix each part's two nearest views near the line between them, by a fixed pattern of pixels
    only    part names to draw (None: all);  forced  {part name: view} to show whatever is nearest
    line    the ink line round each part: "shell" (behind the surface) or "off" (card_pixels)
    who     an HxW array of whole numbers to fill in: which card each pixel shows (1 + PARTS_A_FIGURE * figure +
            the part's place in the list; 0 where there is none), for the lines drawn on the finished picture
    lines   an HxW array of True and False to fill in: where the picture shows a part's own ink line
    paint   one of PAINTS, for a look's own tones, strength of colour and rim light (None: the comic look's tones)
    keep_dark  the head's card keeps the darkest of what a pixel covers when it is shown small (card_pixels)

    Returns (picture: rows from the bottom up, HxWx4 uint8; distance in front HxW, inf where empty;
    {part name: {"view", "next", "share", "off_deg"}})."""
    wide, tall = eye.size
    colour = np.zeros((tall, wide, 3), dtype=np.float32)
    depth = np.full((tall, wide), np.inf, dtype=np.float32)
    said = {}
    pattern = np.tile(BAYER, (tall // 4 + 1, wide // 4 + 1))[:tall, :wide]
    for index, part in enumerate(character.parts):
        name = part["name"]
        if only is not None and name not in only:
            continue
        bone = pose[part["bone"]]
        v = eye_in_bone(bone, part["center"], eye.at)
        first, second, share = choose(character.dirs, v, None if held is None else held.get(name))
        if forced and name in forced:
            first, share = forced[name], 1.0
        if held is not None:
            held[name] = first
        off = math.degrees(math.acos(max(-1.0, min(1.0, float(character.dirs[first] @ v)))))
        said[name] = {"view": first, "next": second, "share": share, "off_deg": off}
        showing = [(first, None)] if not blend or share >= 1.0 else [(first, share), (second, share)]
        for n, (view, portion) in enumerate(showing):
            card = place(character.views[view], bone, part["center"], eye.at)
            got = card_pixels(character, part, view, card, eye, relief, line, keep_dark and name == "head", joint_balls(character, part, bone, pose, eye.at))
            if got is None:
                continue
            x0, y0, rgb, cover, normal, ahead, inked = got
            h, w = cover.shape
            keep = cover >= 0.5
            if portion is not None:
                grid = pattern[y0:y0 + h, x0:x0 + w]
                keep &= (grid < portion) if n == 0 else (grid >= portion)
            keep &= ahead < depth[y0:y0 + h, x0:x0 + w]
            lit = to_linear(rgb) * tones(normal, card["turn"], eye) if paint is None else painted(rgb, normal, card["turn"], eye, paint)
            if paint is not None:  # the ink line is its own colour whatever the paint
                lit = np.where(inked[..., None], to_linear(np.array(INK, dtype=np.float32)), lit)
            colour[y0:y0 + h, x0:x0 + w][keep] = lit[keep]
            depth[y0:y0 + h, x0:x0 + w][keep] = ahead[keep]
            if who is not None:
                who[y0:y0 + h, x0:x0 + w][keep] = 1 + PARTS_A_FIGURE * (figure % 15) + index % PARTS_A_FIGURE
            if lines is not None:
                lines[y0:y0 + h, x0:x0 + w][keep] = inked[keep]
    out = np.zeros((tall, wide, 4), dtype=np.uint8)
    out[..., :3] = np.round(to_screen(colour) * 255.0)
    out[..., 3] = np.where(np.isfinite(depth), 255, 0)
    return out, depth, said


# ---------- lines drawn on the finished picture (gallery/looks.js does the same on the graphics card) ----------

def _beside(a, dy, dx):
    """Every pixel's neighbour dy up and dx to the right (the picture's own edge pixel past the edge)."""
    tall, wide = a.shape[:2]
    ys = np.clip(np.arange(tall) + dy, 0, tall - 1)
    xs = np.clip(np.arange(wide) + dx, 0, wide - 1)
    return a[ys][:, xs]


def grid_line(depth, who, eye, break_m=BREAK_M, fine=1):
    """The pixel looks' line: True where a pixel of the finished picture is inked. One big pixel wide, just outside
    whatever a card shows, on the picture's own grid.

    depth  how far in front each pixel is (m; inf where nothing is);  who  which card each pixel shows (draw)
    fine   how many of this picture's pixels one big pixel is across (1; FINE when heads are on a finer grid: the
           body's pixels are then blocks of that many, and the line stays one big pixel wide round a head too)

    A pixel is inked when a pixel beside it (left, right, above or below, up to one big pixel off) shows a card and
      - this one shows something else, or another figure, and is the further of the two: the outside line; or
      - (one big pixel off) this one shows the same figure and is further by more than break_m (and by more than
        a big pixel and a half is across out there), and not just because the surface is sloping away: an arm in
        front of a chest.
    Two cards of one figure that meet at a joint are at the same depth, so no line falls between them."""
    figure = np.where(who > 0, (who - 1) // PARTS_A_FIGURE, -1)
    per_px = 2.0 * eye.tan / (eye.size[1] / fine)  # how big a big pixel is a metre away
    d = np.where(np.isfinite(depth), depth, eye.far)
    inked = np.zeros(depth.shape, dtype=bool)
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        for s in range(1, fine + 1):
            it, there = _beside(who, dy * s, dx * s), _beside(d, dy * s, dx * s)
            drop = d - there
            same = (who > 0) & (_beside(figure, dy * s, dx * s) == figure)
            inked |= (it > 0) & ~same & (drop > 0.0)
            if s == fine:
                slope = np.where(_beside(figure, -dy * s, -dx * s) == figure, np.abs(_beside(d, -dy * s, -dx * s) - d), 0.0)
                inked |= (it > 0) & same & (drop > np.maximum(break_m, 1.5 * per_px * there)) & (drop > 2.5 * slope)
    return inked


def head_grid(eye, head_at, fine=FINE, fine_from=FINE_FROM):
    """Whether a head this far off goes on the finer grid, and the eye that draws it there: the same view with
    `fine` times the pixels each way, slid by part of a pixel so that the bone's head (where the head's picture has
    a corner of one of its own pixels) lands on a corner of one of the grid's. As he moves, his head's picture then
    moves a whole pixel at a time, as a sprite does, and is not read at a new place between pixels every frame.
    Returns (finer?, the eye)."""
    wide, tall = eye.size
    if tall / (2.0 * eye.tan * max(1e-6, -float((np.asarray(head_at) - eye.at) @ eye.turn[:, 2]))) < fine_from:
        return False, eye
    plain = Eye(eye.at, eye.aim, eye.fov_deg, (wide * fine, tall * fine), eye.near, eye.far, (eye.shift[0] * fine, eye.shift[1] * fine))
    at, _ = plain.to_pixels(np.asarray(head_at, dtype=np.float64))
    plain.shift = (plain.shift[0] + float(np.round(at[0]) - at[0]), plain.shift[1] + float(np.round(at[1]) - at[1]))
    return True, plain


def draw_fine_heads(character, pose, eye, paint=None, fine=FINE, fine_from=FINE_FROM, snap=True, keep_dark=True, figure=0, line=True):
    """The character as "Pixels, both" draws him (gallery/looks.js: Screen): the body on the picture's big pixels,
    the head on a grid `fine` times finer, and one line a big pixel wide round the lot.

    eye is the eye of the small picture (its pixels are the big ones). The body (every card but the head's) is
    drawn through it. The head's card is drawn through the same eye with `fine` times the pixels (head_grid), in
    front of or behind the body pixel by pixel. Returns (picture: `fine` times the eye's size, rows from the
    bottom up, HxWx4; distance in front; which card each pixel shows; True where the line is)."""
    wide, tall = eye.size
    names = [p["name"] for p in character.parts]
    finer, head_eye = head_grid(eye, pose[next(p["bone"] for p in character.parts if p["name"] == "head")][:3, 3], fine, fine_from) if "head" in names else (False, eye)
    if not snap and finer:
        head_eye = Eye(eye.at, eye.aim, eye.fov_deg, (wide * fine, tall * fine), eye.near, eye.far, (eye.shift[0] * fine, eye.shift[1] * fine))
    who = np.zeros((tall, wide), dtype=np.int32)
    picture, depth, _ = draw(character, pose, eye, line="off", who=who, figure=figure, paint=paint, only=[n for n in names if n != "head"] if finer else None)
    big = lambda a: np.repeat(np.repeat(a, fine, axis=0), fine, axis=1)
    picture, depth, who = big(picture), big(depth), big(who)
    if finer:
        head_who = np.zeros((tall * fine, wide * fine), dtype=np.int32)
        head, head_depth, _ = draw(character, pose, head_eye, line="off", who=head_who, figure=figure, paint=paint, only=["head"], keep_dark=keep_dark)
        front = head_depth < depth
        picture[front], depth[front], who[front] = head[front], head_depth[front], head_who[front]
    lines = grid_line(depth, who, Eye(eye.at, eye.aim, eye.fov_deg, (wide * fine, tall * fine), eye.near, eye.far), fine=fine) if line else np.zeros(who.shape, dtype=bool)
    if "screen" in FILL:  # a crack one big pixel wide between two cards that meet is filled, and gets no line
        picture, depth, who, filled = crack_fill(picture, depth, who, [(0, fine), (fine, 0)])
        lines &= ~filled
    return with_lines(picture, lines, GRID_INK), depth, who, lines


def bold_lines(depth, who, eye, outer=3.2, inner=1.2, seam_m=SEAM_M):
    """Bold ink's lines on the finished picture: True where a pixel is inked. A thick line just outside anything
    that stands well in front of what is behind it, a thin one where one thing passes just in front of another,
    and a thin one where the surface folds. `who` (which card each pixel shows; None: nobody says) keeps the thin
    lines off the joints: where two cards of one figure meet, a step under seam_m is the cards not quite agreeing,
    not one thing in front of another, and a bend in the depth there is not a fold."""
    near, far = eye.near, eye.far
    d = np.where(np.isfinite(depth), depth, far)
    raw = (far + near - 2.0 * near * far / d) / (far - near) * 0.5 + 0.5  # what the depth buffer holds
    figure = None if who is None else np.where(who > 0, (who - 1) // PARTS_A_FIGURE, -1)
    inked = np.zeros(depth.shape, dtype=bool)
    steps = [(math.cos(i * 0.7853982), math.sin(i * 0.7853982)) for i in range(8)]
    at = lambda a, i, r: _beside(a, int(round(steps[i][1] * r)), int(round(steps[i][0] * r)))
    for i in range(8):
        wide, wide_past = at(d, i, outer), at(d, (i + 4) % 8, outer)
        drop, slope = d - wide, np.abs(wide_past - d)
        inked |= (drop > 0.3 + 0.03 * wide) & (drop > 2.5 * slope)
        close, close_past = at(d, i, inner), at(d, (i + 4) % 8, inner)
        drop, slope = d - close, np.abs(close_past - d)
        thin = (drop > 0.04 + 0.004 * close) & (drop > 2.5 * slope)
        if who is not None:
            it = at(who, i, inner)
            thin &= ~((who > 0) & (it > 0) & (at(figure, i, inner) == figure) & (it != who) & (drop < seam_m))
        inked |= thin
    r = max(1, int(round(inner)))
    bend = np.abs(_beside(raw, 0, r) + _beside(raw, 0, -r) - 2.0 * raw) + np.abs(_beside(raw, r, 0) + _beside(raw, -r, 0) - 2.0 * raw)
    fold = (d < 40.0) & (bend * d * d * (far - near) / (near * far) > 0.02 + 0.004 * d)
    if who is not None:
        for dy, dx in ((0, r), (0, -r), (r, 0), (-r, 0)):
            fold &= ~((who > 0) & (_beside(figure, dy, dx) == figure) & (_beside(who, dy, dx) != who))
    return inked | fold


def crack_fill(picture, depth, who, offsets):
    """Cracks filled on the finished picture (gallery/looks.js does the same on the graphics card). A pixel that
    shows no card, or another figure, with two cards of one figure on opposite sides of it (at each of
    `offsets`, (up, right) in pixels, and the same the other way), is a crack between them when the two are one
    part or two parts that meet at a joint, stand within CRACK_APART_M of each other, and what the pixel shows
    is further off than both by CRACK_BEHIND_M. It takes the colour, depth and number of the nearer of the two.
    A real gap (between the legs, between an arm and the hips, the stage seen through a bent arm) is wider than
    the offsets reach, or lies between parts that do not meet, and is left alone.
    Returns (picture, depth, who, True where a pixel was filled); what was given is not changed."""
    d = np.where(np.isfinite(depth), depth, 1e9)
    figure = np.where(who > 0, (who - 1) // PARTS_A_FIGURE, -1)
    part = np.where(who > 0, (who - 1) % PARTS_A_FIGURE, 0)
    picture, new_depth, new_who = picture.copy(), depth.copy(), who.copy()
    filled = np.zeros(depth.shape, dtype=bool)
    for dy, dx in offsets:
        a_who, b_who, a_d, b_d = _beside(who, dy, dx), _beside(who, -dy, -dx), _beside(d, dy, dx), _beside(d, -dy, -dx)
        a_fig, b_fig = _beside(figure, dy, dx), _beside(figure, -dy, -dx)
        crack = (a_who > 0) & (b_who > 0) & (a_fig == b_fig) & (figure != a_fig) & JOINED[_beside(part, dy, dx), _beside(part, -dy, -dx)]
        crack &= (np.abs(a_d - b_d) < CRACK_APART_M) & (d - np.maximum(a_d, b_d) > CRACK_BEHIND_M) & ~filled
        from_a = crack & (a_d <= b_d)
        from_b = crack & ~from_a
        for take, oy, ox in ((from_a, dy, dx), (from_b, -dy, -dx)):
            picture[take], new_depth[take], new_who[take] = _beside(picture, oy, ox)[take], _beside(depth, oy, ox)[take], _beside(who, oy, ox)[take]
        filled |= crack
    return picture, new_depth, new_who, filled


def bold_offsets(outer=3.2):
    """Where bold ink looks for the two sides of a crack: as far off as its thick line reaches, four ways."""
    return [(int(round(math.sin(i * 0.7853982) * outer)), int(round(math.cos(i * 0.7853982) * outer))) for i in range(4)]


def with_lines(picture, lines, ink=(0x12, 0x0e, 0x16)):
    """A drawn picture (draw) with lines put on it."""
    out = picture.copy()
    out[lines] = tuple(ink) + (255,)
    return out
