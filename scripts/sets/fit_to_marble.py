"""How well does a mesh made from a picture of a Marble place still match the place? In a background Blender.

    Blender -b --factory-startup -P scripts/sets/fit_to_marble.py -- <set> <mesh.glb> [--out report.json] [--fitted fitted.glb]
    (`just marble-fit <set> <mesh.glb>`)

The round trip this is for: a Marble place, a picture of it, Codex tidying the
picture, TRELLIS making a mesh from that, and then the question: is it still
the same room? TRELLIS hands back a mesh of no particular size, facing no
particular way. So:

    fit       find the size, turn and move that lays the mesh over the set's own
              (sets/<set>/set.glb: the collision mesh, in metres). Sixteen starts
              (squared up by which way its walls face, then four quarter turns,
              upright or upside down, as it is or mirrored), each sized so the
              two take up the same ground, each then walked in
              by closest points (ICP: pair every point with the nearest surface,
              solve for the best size, turn and move, repeat), leaving the worst
              fifth of the pairs out of each solve so that a missing ceiling does
              not drag the rest. The start that ends closest wins.
    measure   with the mesh laid over the room, how far apart the surfaces are,
              both ways, by part of the room:
                made -> room   from points on the new mesh to the room's surface:
                               is what TRELLIS made where the room has it?
                room -> made   from points on the room to the new mesh: how much
                               of the room did TRELLIS make at all? (A diorama
                               picture has no ceiling, so expect that part far.)
              Each as a median and a 90th percentile, in centimetres.

The parts: the floor (level, facing up, at the bottom), the ceiling (facing
down, in the top third), the walls (upright, within a stride of the room's
edge) and things (the rest: the bar, tables, coils of rope).

`--fitted` writes the mesh again, laid over the set, to open beside set.glb.
Needs numpy and Blender's mathutils. Never touches an open Blender.
"""

from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import from_marble  # noqa: E402

PARTS = ("floor", "walls", "ceiling", "things")
POINTS = 20000  # points taken on each surface
ROUNDS = 15  # how many times each start is walked in
FINISH = 300  # how many more the best start may take to settle
SETTLED = 2e-5  # ...or until a round changes its size by less than this share
KEEP = 0.8  # the share of pairs, closest first, each solve is made from
EDGE = 0.9  # metres from the room's edge within which an upright surface is a wall


def parts_of(corners, triangles):
    """Which part of the room each triangle is: an index into PARTS."""
    normal, _ = from_marble.normals_of(corners, triangles)
    middle = corners[triangles].mean(axis=1)
    lo, hi = np.percentile(corners, 0.2, axis=0), np.percentile(corners, 99.8, axis=0)
    tall = hi[1] - lo[1]
    from_edge = np.minimum(np.minimum(middle[:, 0] - lo[0], hi[0] - middle[:, 0]), np.minimum(middle[:, 2] - lo[2], hi[2] - middle[:, 2]))
    part = np.full(len(triangles), PARTS.index("things"))
    part[(np.abs(normal[:, 1]) < 0.5) & (from_edge < EDGE)] = PARTS.index("walls")
    part[(normal[:, 1] < -0.5) & (middle[:, 1] > lo[1] + 0.62 * tall)] = PARTS.index("ceiling")
    part[(normal[:, 1] > 0.7) & (middle[:, 1] < lo[1] + 0.05 * tall + 0.05)] = PARTS.index("floor")
    return part


def points_on(corners, triangles, count, seed=0):
    """`count` points spread evenly over a mesh's surface: (points, the triangle each is on)."""
    rng = np.random.default_rng(seed)
    _, area = from_marble.normals_of(corners, triangles)
    which = rng.choice(len(triangles), size=count, p=area / area.sum())
    u, v = rng.random(count), rng.random(count)
    flip = u + v > 1.0
    u[flip], v[flip] = 1.0 - u[flip], 1.0 - v[flip]
    a, b, c = corners[triangles[which, 0]], corners[triangles[which, 1]], corners[triangles[which, 2]]
    return a + (b - a) * u[:, None] + (c - a) * v[:, None], which


class Surface:
    """A mesh that can be asked for the nearest point on it."""

    def __init__(self, corners, triangles):
        from mathutils.bvhtree import BVHTree

        self.tree = BVHTree.FromPolygons(corners.tolist(), triangles.tolist())

    def nearest(self, points):
        """(the nearest point on the surface, the triangle it is on, how far) for each point."""
        at, which, far = np.zeros((len(points), 3)), np.zeros(len(points), np.int64), np.zeros(len(points))
        for i, p in enumerate(points.tolist()):
            spot, _, index, distance = self.tree.find_nearest(p)
            at[i], which[i], far[i] = spot, index, distance
        return at, which, far


def best_similarity(a, b, mirrored=False):
    """The size, turn and move that bring points `a` closest to their partners `b` (Umeyama): b ~ s * R @ a + t.
    A turn, never a mirror, unless the fit was started mirrored: then exactly one mirror."""
    ma, mb = a.mean(axis=0), b.mean(axis=0)
    da, db = a - ma, b - mb
    u, d, vt = np.linalg.svd(db.T @ da / len(a))
    sign = np.ones(3)
    if (np.linalg.det(u) * np.linalg.det(vt) < 0) != mirrored:
        sign[-1] = -1.0
    r = u @ np.diag(sign) @ vt
    s = float((d * sign).sum() / (da ** 2).sum() * len(a))
    return s, r, mb - s * r @ ma


def fit(made, room: Surface, room_box, rounds=ROUNDS, squared=None):
    """Lay points `made` over the room. Returns {scale, turn (3x3), move, typical_m, start, mirrored}: the best of the starts.
    `squared(flip)` says how many degrees square a mesh up once it has been flipped by the 3x3 `flip` (none: 0)."""
    lo, hi = room_box
    best = None
    for mirrored in (False, True):
        for upside_down in (False, True):
            flip = (np.diag([1.0, -1.0, -1.0]) if upside_down else np.eye(3)) @ (np.diag([-1.0, 1.0, 1.0]) if mirrored else np.eye(3))
            square = squared(flip) if squared else 0.0
            for quarter in range(4):
                yaw = math.radians(90.0 * quarter + square)
                c, s = math.cos(yaw), math.sin(yaw)
                r = np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]) @ flip
                p = made @ r.T
                plo, phi = np.percentile(p, 1, axis=0), np.percentile(p, 99, axis=0)
                size = float(np.sqrt(((hi[0] - lo[0]) * (hi[2] - lo[2])) / max((phi[0] - plo[0]) * (phi[2] - plo[2]), 1e-12)))  # the same ground covered
                t = np.array([(lo[0] + hi[0]) / 2.0, lo[1], (lo[2] + hi[2]) / 2.0]) - size * np.array([(plo[0] + phi[0]) / 2.0, plo[1], (plo[2] + phi[2]) / 2.0])
                scale, turn, move = size, r, t
                for _ in range(rounds):
                    now = scale * made @ turn.T + move
                    at, _, far = room.nearest(now)
                    kept = far <= np.quantile(far, KEEP)
                    scale, turn, move = best_similarity(made[kept], at[kept], mirrored)
                _, _, far = room.nearest(scale * made @ turn.T + move)
                typical = float(np.median(far))
                if best is None or typical < best["typical_m"]:
                    best = {"scale": scale, "turn": turn, "move": move, "typical_m": typical, "mirrored": mirrored,
                            "start": {"quarter_turns": quarter, "upside_down": upside_down, "mirrored": mirrored}}
    # The best start is walked the rest of the way in: closest points pull a surface along itself only slowly.
    scale, turn, move = best["scale"], best["turn"], best["move"]
    for _ in range(FINISH):
        at, _, far = room.nearest(scale * made @ turn.T + move)
        kept = far <= np.quantile(far, KEEP)
        was = scale
        scale, turn, move = best_similarity(made[kept], at[kept], best["mirrored"])
        if abs(scale - was) < SETTLED * was:
            break
    _, _, far = room.nearest(scale * made @ turn.T + move)
    best.update(scale=scale, turn=turn, move=move, typical_m=float(np.median(far)))
    return best


def spread(far):
    if not len(far):
        return None
    return {"median_cm": round(100 * float(np.median(far)), 1), "p90_cm": round(100 * float(np.percentile(far, 90)), 1), "points": int(len(far))}


def measure(room_corners, room_triangles, made_corners, made_triangles, count=POINTS, rounds=ROUNDS):
    """Fit a mesh to a room and say how far apart they are. Everything in the room's own metres."""
    part = parts_of(room_corners, room_triangles)
    room = Surface(room_corners, room_triangles)
    lo, hi = np.percentile(room_corners, 0.2, axis=0), np.percentile(room_corners, 99.8, axis=0)
    made_points, _ = points_on(made_corners, made_triangles, count)
    # A mesh that stands at an angle is squared up first, the way a Marble room is: by which way its walls face.
    found = fit(made_points[: count // 4], room, (lo, hi), rounds, lambda flip: from_marble.square_turn(made_corners @ flip.T, made_triangles))
    scale, turn, move = found["scale"], found["turn"], found["move"]
    laid = scale * made_corners @ turn.T + move

    _, on, far = room.nearest(scale * made_points @ turn.T + move)
    made_to_room = {"all": spread(far)}
    for i, name in enumerate(PARTS):
        made_to_room[name] = spread(far[part[on] == i])
    room_points, on_room = points_on(room_corners, room_triangles, count, seed=1)
    _, _, back = Surface(laid, made_triangles).nearest(room_points)
    room_to_made = {"all": spread(back)}
    for i, name in enumerate(PARTS):
        room_to_made[name] = spread(back[part[on_room] == i])

    # The turn, said the way a set says it: the mesh stood the right way up and unmirrored first, then turned about y.
    upright = turn @ (np.diag([-1.0, 1.0, 1.0]) if found["mirrored"] else np.eye(3)) @ (np.diag([1.0, -1.0, -1.0]) if found["start"]["upside_down"] else np.eye(3))
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, float(upright[1, 1])))))
    yaw = math.degrees(math.atan2(float(upright[0, 2]), float(upright[2, 2])))
    return {
        "fit": {"scale": round(scale, 5), "yaw_deg": round(yaw, 2), "tilt_deg": round(tilt, 2), "upside_down": found["start"]["upside_down"], "mirrored": found["mirrored"],
                "move_m": [round(float(v), 3) for v in move], "turn": [[round(float(v), 5) for v in row] for row in turn], "started_from": found["start"],
                "about": "point in the room = scale * turn @ point in the mesh + move. yaw_deg is the turn about y once the mesh is the right way up (upside_down: y and z flipped first) and unmirrored"},
        "made_to_room": made_to_room, "room_to_made": room_to_made,
        "about": {"made_to_room": "from points on the new mesh to the room's surface, by the part of the room they land on: is what was made where the room has it?",
                  "room_to_made": "from points on each part of the room to the new mesh: how much of the room was made at all?"},
    }, laid


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    opt = lambda flag, default: args[args.index(flag) + 1] if flag in args else default
    named = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or not args[i - 1].startswith("--"))]
    if len(named) != 2:
        sys.exit(__doc__.split("\n\n")[1])
    sys.path.insert(0, HERE)
    set_dir = named[0] if os.path.exists(os.path.join(named[0], "set.json")) else os.path.join(REPO, "sets", named[0])
    with open(os.path.join(set_dir, "set.json")) as f:
        st = json.load(f)
    room_corners, room_triangles = from_marble.read_glb(os.path.join(set_dir, (st.get("geometry") or {}).get("glb", "set.glb")))
    made_corners, made_triangles = from_marble.read_glb(named[1])
    report, laid = measure(room_corners, room_triangles, made_corners, made_triangles)
    report = dict({"set": st["name"], "mesh": os.path.abspath(named[1]), "mesh_triangles": int(len(made_triangles))}, **report)
    out = opt("--out", None)
    if out:
        with open(out, "w") as f:
            json.dump(report, f, indent=1)
            f.write("\n")
    if "--fitted" in args:
        from_marble.write_glb(opt("--fitted", None), laid, made_triangles, np.full((len(laid), 3), 0.7), "fitted")
    f = report["fit"]
    print("FIT %s onto %s: size x %.4f, turned %.1f degrees, tilted %.1f%s%s, moved %s" % (os.path.basename(named[1]), st["name"], f["scale"], f["yaw_deg"], f["tilt_deg"],
          ", upside down" if f["upside_down"] else "", ", mirrored" if f["mirrored"] else "", f["move_m"]))
    for way, words in (("made_to_room", "new mesh -> room"), ("room_to_made", "room -> new mesh")):
        for name in ("all",) + PARTS:
            got = report[way][name]
            print("FIT %s, %-7s: %s" % (words, name, "median %.1f cm, 90th percentile %.1f cm (%d points)" % (got["median_cm"], got["p90_cm"], got["points"]) if got else "nothing there"))


if __name__ == "__main__":
    main()
