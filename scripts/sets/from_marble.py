"""A World Labs Marble world as a standing set, in a background Blender.

    Blender -b --factory-startup -P scripts/sets/from_marble.py -- <world folder> <set name> [--splats 500k] [--finer 1] [--turn degrees]
    (`just set-from-marble <world folder> <set name>`)

A Marble world is a place grown by a world model from one picture. What it
hands over (the folder, kept out of git) is

    world.json        the record: its name, the words it was grown from, and how
                      big it really is (assets.splats.semantics_metadata)
    collider.glb      a coarse mesh of every surface, for bumping into
    splats-*.spz      the place itself, as a cloud of soft colored blobs
                      (100k, 150k, 500k and full_res of them)

and what a set needs is a .glb in metres around an origin of its own. So:

    metres        raw numbers times `metric_scale_factor`
    floor at 0    the raw frame has y pointing down and the floor
                  `ground_plane_offset` metres below its origin; then the floor
                  the mesh really has is measured, and what is left is taken off
    our axes      y up, the ground x and z: a half turn about x (y and z flip),
                  the way World Labs' own viewer shows a world
    squared up    turned about y until the walls run along x and z, the long
                  side along x (`--turn` to say otherwise; a set that is already
                  there keeps the turn it has, so its marks stay where they are)
    origin        the middle of the room, on the floor
    colors        the collision mesh comes without any worth having. Each of its
                  corners takes the color of the blobs nearest to it; the mesh
                  is cut finer first (each triangle into four, `--finer` times),
                  so there are enough corners to hold a picture

It writes sets/<set>/set.glb, colors on the corners and no lighting of its own
(the blobs' colors already have the lamplight in them), and sets/<set>/set.json.
A set.json that is already there keeps its marks, paths, cameras and lights:
only `geometry`, `marble`, the footprint and the floor's measured area are
written again. A new one gets a mark in the middle and one camera, enough to
pass `just set-check` and be opened; the rest is for a person to place.

`marble` in set.json is how the same place is put down again from the raw
files, by the gallery (which shows the blobs themselves) and by fit_to_marble.py:

    point in the set = turn_y(turn_deg) * [x * scale, ground - y * scale, -z * scale] + move

Reading the files needs numpy, finding the nearest blobs Blender's own
mathutils: both come with Blender, neither with macOS's python3. Never
touches an open Blender.

The .spz format (github.com/nianticlabs/spz), version 2 or 3, gzip over one
stream: a 16-byte header (magic NGSP, version, count, sh degree, fractional
bits, flags), then for all blobs at once their positions (three 24-bit fixed
point numbers each), opacities (a byte), colors (three bytes), sizes (three
bytes, log) and turns (three bytes, or four in version 3).
"""

from __future__ import annotations

import gzip
import json
import math
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SPZ_MAGIC = 0x5053474E
COLOR_SCALE, SH_C0 = 0.15, 0.28209479177387814  # how .spz packs a color: the first spherical harmonic, squeezed into a byte
FLOOR_BAND = 0.25  # metres either side of the metadata's floor in which the mesh's own floor is looked for
NEAREST = 8  # blobs a corner's color is mixed from
SOLID = 0.35  # blobs fainter than this are haze, not a surface: they give no color


# ---- reading what Marble hands over -------------------------------------------------


def read_world(folder: str) -> dict:
    """The record of a world: what it is called, how big it is, and which of its files are in the folder."""
    with open(os.path.join(folder, "world.json")) as f:
        record = json.load(f)
    semantics = ((record.get("assets") or {}).get("splats") or {}).get("semantics_metadata") or {}
    if "metric_scale_factor" not in semantics or "ground_plane_offset" not in semantics:
        raise SystemExit("world.json has no assets.splats.semantics_metadata: without metric_scale_factor and ground_plane_offset there is no telling how big the place is")
    splats = {name[len("splats-"):-len(".spz")]: name for name in sorted(os.listdir(folder)) if name.startswith("splats-") and name.endswith(".spz")}
    return {"id": record.get("world_id"), "title": record.get("display_name") or os.path.basename(folder.rstrip("/")),
            "caption": (record.get("assets") or {}).get("caption") or (record.get("world_prompt") or {}).get("text_prompt"),
            "model": record.get("model"), "scale": float(semantics["metric_scale_factor"]), "ground": float(semantics["ground_plane_offset"]), "splats": splats}


def read_spz(path: str) -> dict:
    """A .spz file's blobs. `at` is where each one is, in the file's own raw numbers; `rgb` its color as a screen
    shows it (0 to 1); `alpha` how solid it is; `size` its three radii. `raw` keeps the bytes as they were, so a
    few blobs can be written out again untouched (`write_spz`)."""
    with open(path, "rb") as f:
        data = gzip.decompress(f.read())
    magic, version, count, sh_degree, fractional_bits, flags, _ = struct.unpack("<IIIBBBB", data[:16])
    if magic != SPZ_MAGIC or version not in (2, 3):
        raise SystemExit("%s: not a version 2 or 3 .spz file (magic %#x, version %d)" % (path, magic, version))
    turn_bytes = 3 if version == 2 else 4
    raw, start = {}, 16
    for name, width in (("at", 9), ("alpha", 1), ("rgb", 3), ("size", 3), ("turn", turn_bytes)):
        raw[name] = np.frombuffer(data, np.uint8, count * width, start).reshape(count, width)
        start += count * width
    raw["rest"] = np.frombuffer(data, np.uint8, len(data) - start, start).reshape(count, -1) if len(data) > start else np.zeros((count, 0), np.uint8)
    b = raw["at"].reshape(count, 3, 3).astype(np.int32)
    fixed = b[:, :, 0] | (b[:, :, 1] << 8) | (b[:, :, 2] << 16)
    fixed = np.where(fixed & 0x800000, fixed - (1 << 24), fixed)
    return {"version": version, "count": count, "sh_degree": sh_degree, "fractional_bits": fractional_bits, "flags": flags,
            "at": (fixed / float(1 << fractional_bits)).astype(np.float32),
            "rgb": np.clip(0.5 + SH_C0 * (raw["rgb"].astype(np.float32) / 255.0 - 0.5) / COLOR_SCALE, 0.0, 1.0),
            "alpha": raw["alpha"][:, 0].astype(np.float32) / 255.0,
            "size": np.exp(raw["size"].astype(np.float32) / 16.0 - 10.0), "raw": raw}


def write_spz(path: str, spz: dict, keep=None) -> int:
    """Write blobs back out as they were read (the ones `keep` picks, or all). Returns how many."""
    raw = spz["raw"]
    keep = np.arange(spz["count"]) if keep is None else np.flatnonzero(keep) if np.asarray(keep).dtype == bool else np.asarray(keep)
    head = struct.pack("<IIIBBBB", SPZ_MAGIC, spz["version"], len(keep), spz["sh_degree"], spz["fractional_bits"], spz["flags"], 0)
    with open(path, "wb") as f:
        f.write(gzip.compress(head + b"".join(raw[name][keep].tobytes() for name in ("at", "alpha", "rgb", "size", "turn", "rest")), 6))
    return len(keep)


def pack_spz(path: str, at, rgb, alpha=None, size=None, fractional_bits: int = 12) -> None:
    """A .spz from plain numbers (raw positions, colors 0 to 1): what a test needs to make a small world of its own."""
    at, rgb = np.asarray(at, np.float64), np.asarray(rgb, np.float64)
    n = len(at)
    fixed = np.round(at * (1 << fractional_bits)).astype(np.int32) & 0xFFFFFF
    where = np.stack([fixed & 0xFF, (fixed >> 8) & 0xFF, (fixed >> 16) & 0xFF], axis=2).astype(np.uint8).reshape(n, 9)
    color = np.clip(np.round(((rgb - 0.5) / SH_C0 * COLOR_SCALE + 0.5) * 255.0), 0, 255).astype(np.uint8)
    solid = np.clip(np.round((np.ones(n) if alpha is None else np.asarray(alpha)) * 255.0), 0, 255).astype(np.uint8).reshape(n, 1)
    big = np.clip(np.round((np.log(np.full((n, 3), 0.02) if size is None else np.asarray(size)) + 10.0) * 16.0), 0, 255).astype(np.uint8)
    turn = np.full((n, 3), 128, np.uint8)  # no turn at all
    head = struct.pack("<IIIBBBB", SPZ_MAGIC, 2, n, 0, fractional_bits, 0, 0)
    with open(path, "wb") as f:
        f.write(gzip.compress(head + where.tobytes() + solid.tobytes() + color.tobytes() + big.tobytes() + turn.tobytes(), 6))


def read_glb(path: str):
    """Every triangle of a .glb as (corners [n, 3], triangles [m, 3]), with each node's own move, turn and size applied."""
    with open(path, "rb") as f:
        f.read(12)
        size, _ = struct.unpack("<II", f.read(8))
        doc = json.loads(f.read(size))
        size, _ = struct.unpack("<II", f.read(8))
        blob = f.read(size)
    kinds = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
    widths = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

    def numbers(index):
        acc = doc["accessors"][index]
        view = doc["bufferViews"][acc["bufferView"]]
        kind, wide = np.dtype(kinds[acc["componentType"]]), widths[acc["type"]]
        start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = view.get("byteStride") or kind.itemsize * wide
        if stride == kind.itemsize * wide:
            return np.frombuffer(blob, kind, acc["count"] * wide, start).reshape(acc["count"], wide)
        rows = np.frombuffer(blob, np.uint8, (acc["count"] - 1) * stride + kind.itemsize * wide, start)
        return np.stack([np.frombuffer(rows[i * stride:i * stride + kind.itemsize * wide].tobytes(), kind) for i in range(acc["count"])])

    def matrix(node):
        if "matrix" in node:
            return np.array(node["matrix"], np.float64).reshape(4, 4).T
        m = np.eye(4)
        x, y, z, w = node.get("rotation", [0, 0, 0, 1])
        m[:3, :3] = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                              [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]) * np.array(node.get("scale", [1, 1, 1]))
        m[:3, 3] = node.get("translation", [0, 0, 0])
        return m

    corners, triangles, count = [], [], 0

    def visit(index, above):
        nonlocal count
        node = doc["nodes"][index]
        here = above @ matrix(node)
        if "mesh" in node:
            for prim in doc["meshes"][node["mesh"]]["primitives"]:
                if prim.get("mode", 4) != 4:
                    continue
                p = numbers(prim["attributes"]["POSITION"]).astype(np.float64)
                p = p @ here[:3, :3].T + here[:3, 3]
                t = numbers(prim["indices"]).astype(np.int64).reshape(-1, 3) if "indices" in prim else np.arange(len(p)).reshape(-1, 3)
                corners.append(p)
                triangles.append(t + count)
                count += len(p)
        for child in node.get("children", []):
            visit(child, here)

    for scene in doc.get("scenes") or [{"nodes": list(range(len(doc["nodes"])))}]:
        for index in scene["nodes"]:
            visit(index, np.eye(4))
    return np.concatenate(corners), np.concatenate(triangles)


# ---- from Marble's frame to a set's ---------------------------------------------------


def to_metres(raw, scale: float, ground: float):
    """Raw Marble points (x, y down, z forward) as metres in our axes (y up, floor at 0)."""
    raw = np.asarray(raw, np.float64)
    return np.stack([raw[:, 0] * scale, ground - raw[:, 1] * scale, -raw[:, 2] * scale], axis=1)


def into_set(raw, marble: dict):
    """Raw Marble points in a set's own frame, by the `marble` block of its set.json."""
    p = to_metres(raw, marble["scale"], marble["ground"])
    turn = math.radians(marble.get("turn_deg", 0.0))
    c, s = math.cos(turn), math.sin(turn)
    x, z = p[:, 0] * c + p[:, 2] * s, -p[:, 0] * s + p[:, 2] * c
    return np.stack([x + marble["move"][0], p[:, 1] + marble["move"][1], z + marble["move"][2]], axis=1)


def normals_of(corners, triangles):
    """(each triangle's unit normal, its area)."""
    a, b, c = corners[triangles[:, 0]], corners[triangles[:, 1]], corners[triangles[:, 2]]
    n = np.cross(b - a, c - a)
    size = np.linalg.norm(n, axis=1)
    return n / np.maximum(size, 1e-12)[:, None], size / 2.0


def floor_of(corners, triangles):
    """The floor the mesh really has, near y = 0: (its height, [x0, z0, x1, z1] of the room, clear floor in m2).
    Triangles facing up within a hand of the metadata's floor are floor or something lying on it; the floor is
    the centimetre of height most of their area is at (tables and chairs make lumps above it, never below).
    The room is everything the mesh covers, seen from above."""
    normal, area = normals_of(corners, triangles)
    middle = corners[triangles].mean(axis=1)
    level = (normal[:, 1] > 0.7) & (np.abs(middle[:, 1]) < FLOOR_BAND)
    if not level.any():
        return 0.0, None, 0.0
    steps = np.round(middle[level, 1] / 0.01).astype(int)
    share = np.bincount(steps - steps.min(), weights=area[level])
    share = np.convolve(share, [1.0, 1.0, 1.0], "same")  # a floor is a few centimetres of lumps, not one
    height = float((int(np.argmax(share)) + steps.min()) * 0.01)
    flat = level & (np.abs(middle[:, 1] - height) < 0.04)
    height = float(np.average(middle[flat, 1], weights=area[flat]))
    lo, hi = np.percentile(corners[:, [0, 2]], 0.2, axis=0), np.percentile(corners[:, [0, 2]], 99.8, axis=0)
    return height, [float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])], float(area[flat].sum())


def square_turn(corners, triangles) -> float:
    """The turn about y (degrees, our headings) that squares a room up with x and z, its long side along x:
    walls face four ways a quarter turn apart, so the way most wall faces, counted in quarter turns, is the room's own."""
    normal, area = normals_of(corners, triangles)
    wall = np.abs(normal[:, 1]) < 0.3
    if not wall.any():
        return 0.0
    angle = np.arctan2(normal[wall, 0], normal[wall, 2])  # a heading: 0 faces +z
    quarter = math.atan2(float((np.sin(4 * angle) * area[wall]).sum()), float((np.cos(4 * angle) * area[wall]).sum())) / 4.0
    best = None
    for k in range(4):
        turn = -math.degrees(quarter) + 90.0 * k
        turn = (turn + 180.0) % 360.0 - 180.0
        c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
        x, z = corners[:, 0] * c + corners[:, 2] * s, -corners[:, 0] * s + corners[:, 2] * c
        long_way = float(np.ptp(x)) >= float(np.ptp(z))
        if long_way and (best is None or abs(turn) < abs(best)):
            best = turn
    return round(best if best is not None else 0.0, 2)


def finer(corners, triangles, times: int = 1):
    """Each triangle cut into four, `times` over, sharing the new corners along every edge."""
    for _ in range(times):
        edges = np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
        edges.sort(axis=1)
        unique, where = np.unique(edges, axis=0, return_inverse=True)
        where = where.reshape(-1)
        middles = (corners[unique[:, 0]] + corners[unique[:, 1]]) / 2.0
        n, m = len(corners), len(triangles)
        ab, bc, ca = where[:m] + n, where[m:2 * m] + n, where[2 * m:] + n
        a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
        triangles = np.concatenate([np.stack([a, ab, ca], 1), np.stack([ab, b, bc], 1), np.stack([ca, bc, c], 1), np.stack([ab, bc, ca], 1)])
        corners = np.concatenate([corners, middles])
    return corners, triangles


def nearest(points, to, k: int = 1):
    """For each of `to`, the k nearest of `points`: (which [n, k], how far [n, k]). Blender's own kd-tree."""
    from mathutils import kdtree

    tree = kdtree.KDTree(len(points))
    for i, p in enumerate(points.tolist()):
        tree.insert(p, i)
    tree.balance()
    which, far = np.zeros((len(to), k), np.int64), np.full((len(to), k), 1e9)
    for i, p in enumerate(to.tolist()):
        found = tree.find_n(p, k)
        for j, (_, index, distance) in enumerate(found):
            which[i, j], far[i, j] = index, distance
    return which, far


def colors_from(corners, splat_at, splat_rgb, splat_alpha):
    """A color for every corner, from the blobs nearest to it: the solid ones, the near ones counting most.
    Returns (rgb 0 to 1 as a screen shows it, how far the nearest blob was)."""
    solid = splat_alpha >= SOLID
    if solid.sum() < NEAREST:
        solid = np.ones(len(splat_at), bool)
    at, rgb, alpha = splat_at[solid], splat_rgb[solid], splat_alpha[solid]
    k = min(NEAREST, len(at))
    which, far = nearest(at, corners, k)
    reach = np.maximum(far[:, :1] * 1.5, 0.02)  # a blob half again as far as the nearest counts for little
    weight = np.exp(-0.5 * (far / reach) ** 2) * alpha[which]
    weight /= np.maximum(weight.sum(axis=1, keepdims=True), 1e-12)
    return (rgb[which] * weight[:, :, None]).sum(axis=1), far[:, 0]


def to_linear(rgb):
    """Screen colors as the light they stand for: what a .glb's corner colors are written in."""
    rgb = np.asarray(rgb, np.float64)
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def write_glb(path: str, corners, triangles, rgb, name: str = "set") -> int:
    """One mesh with a color on every corner (rgb as a screen shows it) and no lighting of its own. Returns its size in bytes."""
    where = np.asarray(corners, np.float32)
    color = np.concatenate([np.round(to_linear(rgb) * 65535.0), np.full((len(where), 1), 65535.0)], axis=1).astype(np.uint16)
    index = np.asarray(triangles, np.uint32).reshape(-1)
    parts = [where.tobytes(), color.tobytes(), index.tobytes()]
    views, start = [], 0
    for part, target in zip(parts, (34962, 34962, 34963)):
        views.append({"buffer": 0, "byteOffset": start, "byteLength": len(part), "target": target})
        start += len(part) + (-len(part)) % 4
    blob = b"".join(part + b"\0" * ((-len(part)) % 4) for part in parts)
    doc = {
        "asset": {"version": "2.0", "generator": "forge from_marble.py"}, "scene": 0, "scenes": [{"name": name, "nodes": [0]}],
        "nodes": [{"name": "set: " + name, "mesh": 0}],
        "meshes": [{"name": name, "primitives": [{"attributes": {"POSITION": 0, "COLOR_0": 1}, "indices": 2, "material": 0}]}],
        # The blobs' colors already have the lamplight in them, so the mesh shows them as they are: lit by nothing.
        "materials": [{"name": "baked from the splats", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 1.0},
                       "extensions": {"KHR_materials_unlit": {}}}],
        "extensionsUsed": ["KHR_materials_unlit"],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(where), "type": "VEC3", "min": where.min(axis=0).tolist(), "max": where.max(axis=0).tolist()},
            {"bufferView": 1, "componentType": 5123, "normalized": True, "count": len(where), "type": "VEC4"},
            {"bufferView": 2, "componentType": 5125, "count": len(index), "type": "SCALAR"},
        ],
        "bufferViews": views, "buffers": [{"byteLength": len(blob)}],
    }
    text = json.dumps(doc, separators=(",", ":")).encode()
    text += b" " * ((-len(text)) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(text) + 8 + len(blob)))
        f.write(struct.pack("<II", len(text), 0x4E4F534A) + text)
        f.write(struct.pack("<II", len(blob), 0x004E4942) + blob)
    return os.path.getsize(path)


# ---- the whole conversion ---------------------------------------------------------------


def starter(name: str, world: dict, floor, tall: float) -> dict:
    """A set.json for a place nobody has placed anything in yet: one mark in the middle, one camera, one lamp."""
    x0, z0, x1, z1 = floor
    reach = min(x1 - x0, z1 - z0)
    return {
        "format": "forge-set/1", "name": name, "title": world["title"], "about": world["caption"], "stage": "open",
        "frame": {"origin": [0.0, 0.0, 0.0], "front_deg": 0.0, "about": "the origin is the middle of the floor, on the floor"},
        "footprint": {}, "units": "metres. y is up and 0 is the floor.",
        "floor": {"areas": [], "note": "the floor the collision mesh has, as one rectangle; furniture stands on it and is in `blocks`"},
        "ground": {"y": -0.02, "color": [0.12, 0.09, 0.07], "size_m": 60.0},
        "blocks": [],
        "marks": {"centre": {"kind": "stand", "at": [0.0, 0.0], "facing_deg": 0.0, "about": "the middle of the floor"}},
        "paths": [],
        "cameras": {"wide": {"at": [0.0, 1.3, round(min(reach / 2.0 - 0.3, 3.0), 2)], "aim": [0.0, 0.85, 0.0], "lens_mm": 18, "sees": ["centre"], "about": "from inside, looking at the middle"}},
        "lights": [{"name": "lamplight", "kind": "area", "at": [0.0, round(max(1.2, tall - 0.4), 2), 0.0], "aim": [0.0, 0.0, 0.0], "power": 300.0, "color": [1.0, 0.82, 0.6], "size_m": 3.0}],
        "world": {"color": [0.2, 0.15, 0.1], "strength": 0.5},
        "slots": {}, "dressing": [],
    }


def convert(folder: str, set_dir: str, name: str, splats: str = "500k", times: int = 1, turn=None) -> dict:
    """Make set.glb and set.json in `set_dir` from a Marble world's folder. Returns what was done, in numbers.
    `turn` is degrees about y, or None: the turn the set already has, or for a new set the one that squares the room up."""
    world = read_world(folder)
    if splats not in world["splats"]:
        raise SystemExit("no splats-%s.spz in %s (there: %s)" % (splats, folder, ", ".join(world["splats"]) or "none"))
    path = os.path.join(set_dir, "set.json")
    st = None
    if os.path.exists(path):
        with open(path) as f:
            st = json.load(f)
    raw_corners, triangles = read_glb(os.path.join(folder, "collider.glb"))
    marble = {"scale": world["scale"], "ground": world["ground"], "turn_deg": 0.0, "move": [0.0, 0.0, 0.0]}
    corners = into_set(raw_corners, marble)
    height, floor, floor_area = floor_of(corners, triangles)
    if floor is None:
        raise SystemExit("the collision mesh has no level floor within %.2f m of where world.json says the ground is" % FLOOR_BAND)
    # What is left of the floor's height comes off (the metadata's ground is a fitted plane; the mesh is what feet
    # stand on), the room is squared up with x and z, and the middle of it becomes the origin.
    if turn is None:
        turn = ((st or {}).get("marble") or {}).get("turn_deg")
    marble["turn_deg"] = float(square_turn(corners, triangles) if turn is None else turn)
    marble["ground"] = world["ground"] - height
    corners = into_set(raw_corners, marble)
    _, floor, _ = floor_of(corners, triangles)
    marble["move"] = [-(floor[0] + floor[2]) / 2.0, 0.0, -(floor[1] + floor[3]) / 2.0]
    corners = into_set(raw_corners, marble)
    height, floor, floor_area = floor_of(corners, triangles)
    coarse = len(triangles)
    corners, triangles = finer(corners, triangles, times)
    spz = read_spz(os.path.join(folder, world["splats"][splats]))
    rgb, far = colors_from(corners, into_set(spz["at"], marble), spz["rgb"], spz["alpha"])
    os.makedirs(set_dir, exist_ok=True)
    size = write_glb(os.path.join(set_dir, "set.glb"), corners, triangles, rgb, name)

    lo, hi = corners.min(axis=0), corners.max(axis=0)
    if st is None:
        st = starter(name, world, floor, float(hi[1]))
    pad = 0.3
    st["footprint"] = dict(st.get("footprint") or {}, outline=[[round(float(lo[0]) - pad, 2), round(float(lo[2]) - pad, 2)], [round(float(hi[0]) + pad, 2), round(float(lo[2]) - pad, 2)],
                                                               [round(float(hi[0]) + pad, 2), round(float(hi[2]) + pad, 2)], [round(float(lo[0]) - pad, 2), round(float(hi[2]) + pad, 2)]])
    st["footprint"].setdefault("about", "everything the collision mesh covers, walls and all")
    st["floor"]["measured"] = {"area_m2": round(floor_area, 1), "box": [[round(floor[0], 2), round(floor[1], 2)], [round(floor[2], 2), round(floor[3], 2)]], "height_m": round(height, 4)}
    if not st["floor"].get("areas"):
        st["floor"]["areas"] = [st["floor"]["measured"]["box"]]
    st["geometry"] = {"glb": "set.glb", "move": [0.0, 0.0, 0.0], "turn_deg": 0.0,
                      "built_by": "the Marble world's collision mesh in metres, floor at 0, colors from its %s splats (just set-from-marble <world folder> %s)" % (splats, name)}
    st["marble"] = {
        "world": os.path.basename(os.path.abspath(folder)), "id": world["id"], "model": world["model"],
        "scale": marble["scale"], "ground": round(marble["ground"], 5), "ground_as_given": world["ground"], "turn_deg": marble["turn_deg"],
        "move": [round(v, 4) for v in marble["move"]], "splats": world["splats"],
        "about": "how the raw files stand in this set: point = turn_y(turn_deg) * [x * scale, ground - y * scale, -z * scale] + move. The folder is world/marble/<world>/, kept out of git",
    }
    with open(path, "w") as f:
        json.dump(st, f, indent=1)
        f.write("\n")
    return {"set": name, "glb_bytes": size, "triangles": int(len(triangles)), "corners": int(len(corners)), "collider_triangles": int(coarse),
            "splats": int(spz["count"]), "from": [round(float(v), 2) for v in lo], "to": [round(float(v), 2) for v in hi],
            "turn_deg": marble["turn_deg"], "clear_floor_m2": round(floor_area, 1), "floor_height_left_m": round(height, 4), "floor_was_off_by_m": round(world["ground"] - marble["ground"], 4),
            "nearest_splat_cm": {"typical": round(100 * float(np.median(far)), 1), "p90": round(100 * float(np.percentile(far, 90)), 1)}}


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    opt = lambda flag, default: args[args.index(flag) + 1] if flag in args else default
    named = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or not args[i - 1].startswith("--"))]
    if len(named) != 2:
        sys.exit(__doc__.split("\n\n")[1])
    folder, name = os.path.abspath(named[0]), named[1]
    set_dir = name if os.path.isabs(name) else os.path.join(REPO, "sets", name)
    done = convert(folder, set_dir, os.path.basename(set_dir), opt("--splats", "500k"), int(opt("--finer", "1")), float(opt("--turn", "0")) if "--turn" in args else None)
    print("MARBLE %s" % json.dumps(done))
    print("MARBLE wrote %s (%.1f MB, %d triangles) and set.json" % (os.path.relpath(os.path.join(set_dir, "set.glb"), REPO), done["glb_bytes"] / 1e6, done["triangles"]))


if __name__ == "__main__":
    main()
