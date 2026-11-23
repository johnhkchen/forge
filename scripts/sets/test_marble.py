"""Tries the Marble conversion on a small room made up here, in a background Blender. No World Labs, no GPU, no world folder.

    Blender -b --factory-startup -P scripts/sets/test_marble.py        (`just check` runs it)

The room is written the way Marble hands a world over: a world.json with a
scale and a ground offset, a collider.glb and a splats-500k.spz in Marble's raw
frame (y down, z forward, not in metres), standing at an angle. Red floor, blue
ceiling, green walls, one end wall yellow.

What it shows:
  spz          blobs written and read back come out where they were and the color they were; a few can be kept
  axes         raw points land in metres with y up and the floor at 0, by a turn and never a mirror
  conversion   the set's mesh is the room's true size, squared up, its floor at 0, its middle at the origin
  colors       every corner took the color of the splats beside it: floor red, ceiling blue
  set          the set.json written for it passes set-check; made again, it keeps its marks and its turn
  fit          a copy of the room at another size, turned and upside down, is laid back over it; a copy with
               no ceiling is too, and the report says the ceiling is the part that is missing
  the saloon   sets/niantic-saloon is as the conversion leaves a set: floor at 0, colors on, small enough to keep
"""

from __future__ import annotations

import json
import math
import os
import struct
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import fit_to_marble  # noqa: E402
import from_marble  # noqa: E402
import standing  # noqa: E402

SCALE, GROUND = 2.0, 1.5  # the made-up world's metric_scale_factor and ground_plane_offset
LONG, DEEP, TALL = 8.0, 5.0, 2.5  # the room, in metres
ASKEW = 30.0  # degrees it stands at in the raw files
RED, BLUE, GREEN, YELLOW = (0.8, 0.15, 0.1), (0.1, 0.2, 0.8), (0.15, 0.6, 0.2), (0.85, 0.75, 0.1)


def check(label, ok, detail=""):
    print("    %s  %s%s" % ("ok  " if ok else "FAIL", label, ("  (%s)" % (str(detail)[:600],)) if not ok and str(detail) else ""))
    if not ok:
        raise AssertionError(label)


def raw_room():
    """The room in Marble's raw frame: (corners, triangles facing inward, a color for each triangle)."""
    x, z, top, bottom = LONG / 2 / SCALE, DEEP / 2 / SCALE, (GROUND - TALL) / SCALE, GROUND / SCALE  # y is down: the ceiling is the smaller y
    c = np.array([[-x, bottom, -z], [x, bottom, -z], [x, bottom, z], [-x, bottom, z], [-x, top, -z], [x, top, -z], [x, top, z], [-x, top, z]])
    quads = [((0, 1, 2, 3), RED), ((4, 7, 6, 5), BLUE), ((0, 4, 5, 1), GREEN), ((3, 2, 6, 7), GREEN), ((0, 3, 7, 4), GREEN), ((1, 5, 6, 2), YELLOW)]
    triangles, colors = [], []
    middle = c.mean(axis=0)
    for (a, b, d, e), color in quads:
        for tri in ((a, b, d), (a, d, e)):
            n = np.cross(c[tri[1]] - c[tri[0]], c[tri[2]] - c[tri[0]])
            if n @ (middle - c[tri[0]]) < 0:
                tri = (tri[0], tri[2], tri[1])
            triangles.append(tri)
            colors.append(color)
    turn = math.radians(ASKEW)
    spin = np.array([[math.cos(turn), 0.0, math.sin(turn)], [0.0, 1.0, 0.0], [-math.sin(turn), 0.0, math.cos(turn)]])
    return c @ spin.T, np.array(triangles), np.array(colors)


def world_folder(where):
    """Write the made-up world as Marble would hand it over."""
    corners, triangles, colors = raw_room()
    os.makedirs(where, exist_ok=True)
    with open(os.path.join(where, "world.json"), "w") as f:
        json.dump({"world_id": "made-up", "display_name": "A made-up room", "model": "none",
                   "assets": {"caption": "A plain room for a test.", "splats": {"semantics_metadata": {"metric_scale_factor": SCALE, "ground_plane_offset": GROUND}}}}, f)
    fine_corners, fine_triangles = from_marble.finer(corners, triangles, 3)  # a collision mesh has many small triangles
    from_marble.write_glb(os.path.join(where, "collider.glb"), fine_corners, fine_triangles, np.full((len(fine_corners), 3), 0.5), "collider")
    rng = np.random.default_rng(3)
    at, rgb = [], []
    _, area = from_marble.normals_of(corners, triangles)
    for tri, color, size in zip(triangles, colors, area):
        n = int(9000 * size / area.sum()) + 50
        u, v = rng.random(n), rng.random(n)
        flip = u + v > 1
        u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
        at.append(corners[tri[0]] + (corners[tri[1]] - corners[tri[0]]) * u[:, None] + (corners[tri[2]] - corners[tri[0]]) * v[:, None])
        rgb.append(np.tile(color, (n, 1)))
    from_marble.pack_spz(os.path.join(where, "splats-500k.spz"), np.concatenate(at), np.concatenate(rgb))
    return where


def corner_colors(path):
    """The colors on a .glb's corners, as the light they stand for (0 to 1)."""
    with open(path, "rb") as f:
        f.read(12)
        size, _ = struct.unpack("<II", f.read(8))
        doc = json.loads(f.read(size))
        size, _ = struct.unpack("<II", f.read(8))
        blob = f.read(size)
    acc = doc["accessors"][doc["meshes"][0]["primitives"][0]["attributes"]["COLOR_0"]]
    view = doc["bufferViews"][acc["bufferView"]]
    return np.frombuffer(blob, np.uint16, acc["count"] * 4, view.get("byteOffset", 0)).reshape(-1, 4)[:, :3] / 65535.0, doc


def test_spz():
    """blobs written and read back come out where they were and the color they were; a few can be kept."""
    with tempfile.TemporaryDirectory() as tmp:
        rng = np.random.default_rng(1)
        at, rgb = rng.uniform(-3, 3, (500, 3)), rng.uniform(0.05, 0.95, (500, 3))
        path = os.path.join(tmp, "a.spz")
        from_marble.pack_spz(path, at, rgb, alpha=np.linspace(0.1, 1.0, 500), size=np.full((500, 3), 0.03))
        got = from_marble.read_spz(path)
        check("500 blobs come back", got["count"] == 500 and got["version"] == 2)
        check("where they were, to a quarter of a millimetre", float(np.abs(got["at"] - at).max()) < 2.5e-4, np.abs(got["at"] - at).max())
        check("the color they were, to a hundredth", float(np.abs(got["rgb"] - rgb).max()) < 0.012, np.abs(got["rgb"] - rgb).max())
        check("as solid and as big as they were", float(np.abs(got["alpha"] - np.linspace(0.1, 1.0, 500)).max()) < 0.003 and float(np.abs(got["size"] - 0.03).max()) < 0.002)
        kept = from_marble.write_spz(os.path.join(tmp, "b.spz"), got, got["at"][:, 0] > 0)
        again = from_marble.read_spz(os.path.join(tmp, "b.spz"))
        check("a few can be written out again untouched", kept == int((got["at"][:, 0] > 0).sum()) == again["count"] and np.array_equal(again["at"], got["at"][got["at"][:, 0] > 0]))


def test_axes():
    """raw points land in metres with y up and the floor at 0, by a turn and never a mirror."""
    p = from_marble.to_metres(np.array([[0.0, GROUND / SCALE, 0.0], [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]), SCALE, GROUND)
    check("the raw floor (y = ground / scale, below the origin: y is down) is at 0", abs(p[0, 1]) < 1e-9, p[0])
    check("the raw origin, where the camera was, is %.1f m above it" % GROUND, abs(p[1, 1] - GROUND) < 1e-9, p[1])
    check("one raw unit is %.1f m" % SCALE, abs(np.linalg.norm(p[2] - p[1]) - SCALE) < 1e-9)
    check("raw forward (+z) is our -z, and x stays x", p[3, 2] - p[1, 2] == -SCALE and p[2, 0] - p[1, 0] == SCALE)
    marble = {"scale": SCALE, "ground": GROUND, "turn_deg": 40.0, "move": [1.0, 0.0, -2.0]}
    basis = from_marble.into_set(np.eye(3), marble) - from_marble.into_set(np.zeros((1, 3)), marble)
    check("into a set's frame is a turn and a size, never a mirror", abs(np.linalg.det(basis.T) - SCALE ** 3) < 1e-6, np.linalg.det(basis.T))


def converted(tmp):
    folder = world_folder(os.path.join(tmp, "world"))
    set_dir = os.path.join(tmp, "sets", "made-up")
    return folder, set_dir, from_marble.convert(folder, set_dir, "made-up", times=0)


def test_conversion():
    """the set's mesh is the room's true size, squared up, its floor at 0, its middle at the origin."""
    with tempfile.TemporaryDirectory() as tmp:
        _, set_dir, done = converted(tmp)
        lo, hi = standing.glb_bounds(os.path.join(set_dir, "set.glb"))
        size = [hi[i] - lo[i] for i in range(3)]
        check("%.0f m long, %.1f m high, %.0f m deep: the raw numbers times the scale, the long side along x" % (LONG, TALL, DEEP),
              abs(size[0] - LONG) < 0.02 and abs(size[1] - TALL) < 0.01 and abs(size[2] - DEEP) < 0.02, size)
        check("the floor is at 0 and the ceiling above it", abs(lo[1]) < 0.002 and abs(hi[1] - TALL) < 0.002, (lo[1], hi[1]))
        check("the middle of the room is the origin", abs(lo[0] + hi[0]) < 0.02 and abs(lo[2] + hi[2]) < 0.02, (lo, hi))
        check("it stood at %.0f degrees and was turned square" % ASKEW, min(abs((done["turn_deg"] + sign * ASKEW + 45.0) % 90.0 - 45.0) for sign in (1.0, -1.0)) < 0.5, done["turn_deg"])


def test_colors():
    """every corner took the color of the splats beside it: floor red, ceiling blue."""
    with tempfile.TemporaryDirectory() as tmp:
        folder, set_dir = world_folder(os.path.join(tmp, "world")), os.path.join(tmp, "sets", "made-up")
        from_marble.convert(folder, set_dir, "made-up", times=1)
        colors, doc = corner_colors(os.path.join(set_dir, "set.glb"))
        corners, _ = from_marble.read_glb(os.path.join(set_dir, "set.glb"))
        inside = (np.abs(corners[:, 0]) < LONG / 2 - 0.4) & (np.abs(corners[:, 2]) < DEEP / 2 - 0.4)
        floor, ceiling = inside & (corners[:, 1] < 0.01), inside & (corners[:, 1] > TALL - 0.01)
        check("there are corners on the floor and the ceiling to look at", floor.sum() > 20 and ceiling.sum() > 20, (floor.sum(), ceiling.sum()))
        check("the floor is red", float(np.abs(colors[floor] - from_marble.to_linear(RED)).max()) < 0.03, colors[floor][:3])
        check("the ceiling is blue", float(np.abs(colors[ceiling] - from_marble.to_linear(BLUE)).max()) < 0.03, colors[ceiling][:3])
        end = (np.abs(np.abs(corners[:, 0]) - LONG / 2) < 0.01) & (np.abs(corners[:, 2]) < DEEP / 2 - 0.4) & (corners[:, 1] > 0.4) & (corners[:, 1] < TALL - 0.4)
        yellow = np.abs(colors[end] - from_marble.to_linear(YELLOW)).max(axis=1) < 0.03
        check("one end wall is yellow and the other is not", 0.3 < yellow.mean() < 0.7 and len({bool(v) for v in yellow[corners[end][:, 0] > 0]}) == 1, yellow.mean())
        check("the mesh shows its colors as they are, lit by nothing", "KHR_materials_unlit" in doc["materials"][0].get("extensions", {}))


def test_set():
    """the set.json written for it passes set-check; made again, it keeps its marks and its turn."""
    with tempfile.TemporaryDirectory() as tmp:
        folder, set_dir, done = converted(tmp)
        st = standing.load(set_dir)
        problems, _ = standing.check(st)
        check("a new set from a Marble world is sound as written", not problems, problems)
        check("it says how the raw files stand in it", st["marble"]["scale"] == SCALE and abs(st["marble"]["ground"] - GROUND) < 0.01 and st["marble"]["world"] == "world" and st["marble"]["splats"] == {"500k": "splats-500k.spz"}, st["marble"])
        st.pop("dir")
        st["marks"]["by_the_wall"] = {"kind": "stand", "at": [2.0, 0.5], "facing_deg": 90.0}
        with open(os.path.join(set_dir, "set.json"), "w") as f:
            json.dump(st, f)
        again = from_marble.convert(folder, set_dir, "made-up", times=0)
        kept = standing.load(set_dir)
        check("made again, the mark someone placed is still there", "by_the_wall" in kept["marks"])
        check("and the room is turned the way it was", again["turn_deg"] == done["turn_deg"] and kept["marble"]["move"] == st["marble"]["move"])


def test_fit():
    """a copy of the room at another size, turned and upside down, is laid back over it; one with no ceiling too."""
    with tempfile.TemporaryDirectory() as tmp:
        _, set_dir, _ = converted(tmp)
        corners, triangles = from_marble.read_glb(os.path.join(set_dir, "set.glb"))
        turn = math.radians(40.0)
        spin = np.array([[math.cos(turn), 0.0, math.sin(turn)], [0.0, 1.0, 0.0], [-math.sin(turn), 0.0, math.cos(turn)]]) @ np.diag([1.0, -1.0, -1.0])
        made = (corners @ spin.T) * 0.37 + np.array([5.0, -2.0, 1.0])
        report, laid = fit_to_marble.measure(corners, triangles, made, triangles, count=4000)
        check("the size it was made at is found (x %.3f)" % (1 / 0.37), abs(report["fit"]["scale"] * 0.37 - 1.0) < 0.01, report["fit"])
        check("laid back over the room, the surfaces are within a centimetre", report["made_to_room"]["all"]["p90_cm"] < 1.0 and report["room_to_made"]["all"]["p90_cm"] < 1.0, (report["made_to_room"]["all"], report["room_to_made"]["all"]))
        part = fit_to_marble.parts_of(corners, triangles)
        counts = {name: int((part == i).sum()) for i, name in enumerate(fit_to_marble.PARTS)}
        check("the room has a floor, walls and a ceiling to measure by", counts["floor"] > 0 and counts["walls"] > 0 and counts["ceiling"] > 0, counts)
        open_top = triangles[part != fit_to_marble.PARTS.index("ceiling")]
        report, _ = fit_to_marble.measure(corners, triangles, made, open_top, count=4000)
        check("with its ceiling taken off it still fits: what was made is where the room has it", report["made_to_room"]["all"]["p90_cm"] < 3.0, report["made_to_room"])
        check("and the report says which part is missing: the ceiling is far, the floor is not",
              report["room_to_made"]["ceiling"]["median_cm"] > 50.0 and report["room_to_made"]["floor"]["median_cm"] < 3.0, report["room_to_made"])


def test_the_saloon():
    """sets/niantic-saloon is as the conversion leaves a set: floor at 0, colors on, small enough to keep."""
    st = standing.load("niantic-saloon")
    path = os.path.join(st["dir"], "set.glb")
    corners, triangles = from_marble.read_glb(path)
    height, _, clear = from_marble.floor_of(corners, triangles)
    check("its floor is at 0, to a centimetre", abs(height) < 0.01 and clear > 10.0, (height, clear))
    lo, hi = standing.glb_bounds(path)
    check("it is a room people fit in: 2.5 to 3.5 m high, the long side along x", 2.5 < hi[1] - lo[1] < 3.5 and hi[0] - lo[0] > hi[2] - lo[2], (lo, hi))
    colors, _ = corner_colors(path)
    check("its corners carry colors, and not one flat one", len(colors) == len(corners) and float(colors.std(axis=0).min()) > 0.02, colors.std(axis=0))
    check("it is small enough to keep in git (under 10 MB)", os.path.getsize(path) < 10e6, os.path.getsize(path))
    check("it says which Marble world it is and how that stands in it", st["marble"]["world"] == "niantic-saloon" and st["marble"]["scale"] > 0 and len(st["marble"]["move"]) == 3)
    check("it has a door that says where it leads", any(m.get("kind") == "door" and m.get("leads_to") for m in st["marks"].values()))


TESTS = [test_spz, test_axes, test_conversion, test_colors, test_set, test_fit, test_the_saloon]


def cases():
    """The tests, for scripts/test_tools.py: [(name, what it shows, the function)]."""
    return [(t.__name__[5:], t.__doc__, t) for t in TESTS]


def main() -> int:
    failed = 0
    for test in TESTS:
        print("%s: %s" % (test.__name__[5:], test.__doc__))
        try:
            test()
        except Exception as e:  # a failed check, or something a check reads that is missing
            failed += 1
            print("    FAILED: %s: %s" % (type(e).__name__, str(e)[:800]))
    print("MARBLE %d marble case(s) failed" % failed if failed else "MARBLE all %d marble cases passed" % len(TESTS))
    return 1 if failed else 0


if __name__ == "__main__":
    code = main()
    if code:
        sys.exit(code)
