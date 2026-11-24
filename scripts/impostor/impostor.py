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
BLEND_DEG = 7.0      # two views are mixed when the eye is within this of the line between them
HOLD_DEG = 2.5       # a view is kept until another is nearer by this much (stops flicker on the line)
BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32) / 16.0 + 1.0 / 32.0
# The comic look (toon.py's numbers): where the light is as the eye sees it (right, up, toward the eye),
# what the middle and dark tones multiply a colour by, and how far a surface must face the light for each.
LIGHT = (-0.55, 0.5, 0.67)
SHADE = ((0.86, 0.85, 0.90), (0.62, 0.60, 0.74))
EDGES = (0.2, -0.2)


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

    def __init__(self, at, aim, fov_deg=30.0, size=(480, 540), near=0.1, far=100.0):
        self.at, self.aim = np.asarray(at, dtype=np.float64), np.asarray(aim, dtype=np.float64)
        self.fov_deg, self.size, self.near, self.far = float(fov_deg), tuple(size), near, far
        back = unit(self.at - self.aim)
        right = unit(np.cross([0.0, 1.0, 0.0], back))
        self.turn = np.stack([right, np.cross(back, right), back], axis=1)  # columns: right, up, back
        self.tan = math.tan(math.radians(self.fov_deg) / 2.0)

    def to_pixels(self, points):
        """World points to picture pixels (x from the left, y from the bottom) and their distance in front."""
        rel = (np.asarray(points) - self.at) @ self.turn
        wide, tall = self.size
        ahead = -rel[..., 2]
        x = (rel[..., 0] / (ahead * self.tan * wide / tall) * 0.5 + 0.5) * wide
        y = (rel[..., 1] / (ahead * self.tan) * 0.5 + 0.5) * tall
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


def card_pixels(character, part, view_index, card, eye, relief=True):
    """One card as the eye sees it: (x0, y0, colour HxWx3 as stored, cover HxW 0..1, normal HxWx3 in the bone's
    frame, distance in front HxW), or None when it is off the picture. The page's fragment shader, slowly.
    relief: slide each pixel by the picture's depth (False: the picture is laid flat on the card)."""
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
    ray_cam = np.stack([(xs / wide * 2 - 1) * eye.tan * wide / tall, (ys / tall * 2 - 1) * eye.tan, -np.ones_like(xs)], axis=-1)
    ray = ray_cam @ eye.turn.T
    toward, head = card["toward"], card["head"]
    along_ray = (toward @ (head - eye.at)) / (ray @ toward)
    world = eye.at + ray * along_ray[..., None]
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
        # that is under the surface, then halved in on.
        steps = march_steps(card, cell, ppm)
        top, bottom = high + 0.002, low - 0.002
        above, below = np.full(xs.shape, top), np.full(xs.shape, bottom)
        found = np.zeros(xs.shape, dtype=bool)
        for i in range(1, steps + 1):
            at = top + (bottom - top) * i / steps
            there, height, _ = read((sheet - at * lean) @ back.T)
            hit = ~found & there & (height >= at)
            below[hit] = at
            found |= hit
            above[~found] = at
        for _ in range(REFINE):
            mid = (above + below) / 2.0
            there, height, _ = read((sheet - mid[..., None] * lean) @ back.T)
            under = there & (height >= mid)
            below, above = np.where(under, mid, below), np.where(under, above, mid)
        xy = (sheet - below[..., None] * lean) @ back.T
        there, height, data = read(xy)
        inside = found & there & (height - below < WALL_M + (top - bottom) / steps / 2 ** REFINE)
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
    # facing and depth: the one pixel it falls in
    normal = unpack_normal(data[..., :2])
    out = (xy[..., 0] * card["deep"][0] + xy[..., 1] * card["deep"][1] + height * card["deep"][2]) * card["size"]
    to_eye = eye.at - world
    reach = np.linalg.norm(to_eye, axis=-1)
    point = world + to_eye / reach[..., None] * out[..., None]
    ahead = -((point - eye.at) @ eye.turn[:, 2])
    cover = np.where(inside, rgba[..., 3], 0.0)
    return int(lo[0]), int(lo[1]), rgba[..., :3], cover, normal, ahead


def tones(normal_bone, turn, eye, light=LIGHT, shade=SHADE, edges=EDGES):
    """What each pixel's colour is multiplied by: one of three flat tones, by how far the surface faces the light."""
    facing = (normal_bone @ turn.T) @ (eye.turn @ unit(light))
    out = np.ones(facing.shape + (3,), dtype=np.float32)
    out[facing <= edges[0]] = shade[0]
    out[facing <= edges[1]] = shade[1]
    return out


def draw(character, pose, eye, relief=True, blend=False, held=None, only=None, forced=None):
    """The character as cards, in one pose, through one eye.

    pose    {bone name: 4x4 matrix in the world}
    relief  slide each card's pixels by the picture's depth (False: every picture laid flat on its card)
    held    {part name: the view shown last time}: give the same dict back every frame and a view is
            kept until another is clearly nearer; None picks the nearest every time
    blend   mix each part's two nearest views near the line between them, by a fixed pattern of pixels
    only    part names to draw (None: all);  forced  {part name: view} to show whatever is nearest

    Returns (picture: rows from the bottom up, HxWx4 uint8; distance in front HxW, inf where empty;
    {part name: {"view", "next", "share", "off_deg"}})."""
    wide, tall = eye.size
    colour = np.zeros((tall, wide, 3), dtype=np.float32)
    depth = np.full((tall, wide), np.inf, dtype=np.float32)
    said = {}
    pattern = np.tile(BAYER, (tall // 4 + 1, wide // 4 + 1))[:tall, :wide]
    for part in character.parts:
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
        for n, (index, portion) in enumerate(showing):
            card = place(character.views[index], bone, part["center"], eye.at)
            got = card_pixels(character, part, index, card, eye, relief)
            if got is None:
                continue
            x0, y0, rgb, cover, normal, ahead = got
            h, w = cover.shape
            keep = cover >= 0.5
            if portion is not None:
                grid = pattern[y0:y0 + h, x0:x0 + w]
                keep &= (grid < portion) if n == 0 else (grid >= portion)
            keep &= ahead < depth[y0:y0 + h, x0:x0 + w]
            lit = to_linear(rgb) * tones(normal, card["turn"], eye)
            colour[y0:y0 + h, x0:x0 + w][keep] = lit[keep]
            depth[y0:y0 + h, x0:x0 + w][keep] = ahead[keep]
    out = np.zeros((tall, wide, 4), dtype=np.uint8)
    out[..., :3] = np.round(to_screen(colour) * 255.0)
    out[..., 3] = np.where(np.isfinite(depth), 255, 0)
    return out, depth, said
