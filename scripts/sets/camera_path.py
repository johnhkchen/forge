"""A camera that moves: a few keys in time, eased between, for a shot on a standing set.

A set's own cameras never move (set.json). A shot can add cameras of its own
that do, in its plan (motion/shots/<name>.json), under `moving_cameras`:

    "moving_cameras": {
      "push_in": {
        "about": "low and wide, pushing in slowly to a low medium shot",
        "keys": [
          {"at_s": 0.0,  "at": [0.0, 0.40, 8.4], "aim": [-0.7, 1.05, 2.75], "lens_mm": 24},
          {"at_s": 12.47, "at": [-0.3, 0.50, 5.6], "aim": [-0.4, 1.30, 2.75], "lens_mm": 32, "ease": "in_out"}
        ]
      }
    }

    at, aim   where the lens is and the point it looks at, in the set's metres
              (x across, y up, z toward the house), as a set's cameras say it
    lens_mm   on a 36 mm wide picture, as the set's cameras
    at_s      seconds into the shot. Before the first key the camera waits on
              it, after the last it stays on it
    ease      how the move into this key goes: "in_out" (the default: starts
              and stops gently), "in", "out", "linear", or "hold" (it waits
              on the key before, then cuts)

`from` and `to` (each with at, aim and lens_mm) and `ease` are a shorthand for
two keys: the whole shot long, or `seconds` long. Points and lenses are eased
in a straight line between keys, so the camera stays upright (no roll) and
its aim slides as the lens does.

plan_shot.py copies them, with the keys filled in, into plan.json; the films
(render_take.py --cameras <name>) and the watch page (gallery/camera-path.js,
the same arithmetic) both read them from there.

    python3 scripts/sets/camera_path.py <shot folder> [camera]   # what the camera sees of the figure, frame by frame

Plain Python.
"""

from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

EASES = ("in_out", "in", "out", "linear", "hold")


class PathProblem(ValueError):
    pass


def ease(kind: str, t: float) -> float:
    """How far along (0..1) a move is when t (0..1) of its time has gone."""
    t = min(1.0, max(0.0, t))
    if kind == "linear":
        return t
    if kind == "in":
        return 1.0 - math.cos(t * math.pi / 2.0)
    if kind == "out":
        return math.sin(t * math.pi / 2.0)
    if kind == "hold":
        return 1.0 if t >= 1.0 else 0.0
    return 0.5 - 0.5 * math.cos(t * math.pi)  # in_out


def _point(value, name: str, what: str) -> list:
    if not (isinstance(value, (list, tuple)) and len(value) == 3 and all(isinstance(v, (int, float)) for v in value)):
        raise PathProblem(f"moving camera \"{name}\": {what} is three numbers (x, y, z in metres)")
    return [float(v) for v in value]


def expand(name: str, card: dict, seconds: float = None) -> dict:
    """A moving camera as the plan keeps it: its keys, in order, every field filled in. Raises PathProblem."""
    if "keys" in card:
        keys = card["keys"]
    elif "from" in card and "to" in card:
        end = float(card.get("seconds", seconds if seconds is not None else 0.0))
        if end <= 0.0:
            raise PathProblem(f"moving camera \"{name}\": from/to needs the shot's length or `seconds`")
        keys = [dict(card["from"], at_s=0.0), dict(card["to"], at_s=end, ease=card.get("ease", "in_out"))]
    else:
        raise PathProblem(f"moving camera \"{name}\": give `keys`, or `from` and `to`")
    if not keys:
        raise PathProblem(f"moving camera \"{name}\": it has no keys")
    out = []
    for n, key in enumerate(keys):
        lens = float(key.get("lens_mm", out[-1]["lens_mm"] if out else 0.0))
        if lens <= 0.0:
            raise PathProblem(f"moving camera \"{name}\": key {n + 1} has no lens_mm")
        kind = key.get("ease", "in_out")
        if kind not in EASES:
            raise PathProblem(f"moving camera \"{name}\": key {n + 1} eases \"{kind}\"; it can be {', '.join(EASES)}")
        at_s = float(key.get("at_s", 0.0))
        if out and at_s < out[-1]["at_s"]:
            raise PathProblem(f"moving camera \"{name}\": key {n + 1} at {at_s} s comes before the key ahead of it")
        at, aim = _point(key.get("at"), name, f"key {n + 1}'s at"), _point(key.get("aim"), name, f"key {n + 1}'s aim")
        if math.dist(at, aim) < 0.05:
            raise PathProblem(f"moving camera \"{name}\": key {n + 1} looks at its own lens")
        out.append({"at_s": round(at_s, 4), "at": at, "aim": aim, "lens_mm": lens, "ease": kind})
    return {"about": card.get("about", ""), "keys": out}


def expand_all(cards: dict, seconds: float = None) -> dict:
    return {name: expand(name, card, seconds) for name, card in (cards or {}).items()}


def sample(camera: dict, t: float) -> dict:
    """Where the camera is at t seconds: {"at", "aim", "lens_mm"}."""
    keys = camera["keys"]
    if t <= keys[0]["at_s"] or len(keys) == 1:
        k = keys[0]
        return {"at": list(k["at"]), "aim": list(k["aim"]), "lens_mm": k["lens_mm"]}
    for a, b in zip(keys, keys[1:]):
        if t <= b["at_s"]:
            span = b["at_s"] - a["at_s"]
            u = ease(b["ease"], (t - a["at_s"]) / span if span > 0 else 1.0)
            mix = lambda p, q: [p[i] + (q[i] - p[i]) * u for i in range(3)]  # noqa: E731
            return {"at": mix(a["at"], b["at"]), "aim": mix(a["aim"], b["aim"]), "lens_mm": a["lens_mm"] + (b["lens_mm"] - a["lens_mm"]) * u}
    k = keys[-1]
    return {"at": list(k["at"]), "aim": list(k["aim"]), "lens_mm": k["lens_mm"]}


def tilt_deg(where: dict) -> float:
    """How far up (+) or down (-) the camera looks, in degrees."""
    d = [where["aim"][i] - where["at"][i] for i in range(3)]
    return math.degrees(math.atan2(d[1], math.hypot(d[0], d[2])))


def frames_at(seconds: float, fps: float) -> list:
    """The times of a film at fps that lasts `seconds`: 0, 1/fps, ..., one frame short of the end (a 14 s shot at 24
    frames a second is 336 pictures, 14.0 s of film; the shot's very last moment is the next film's first)."""
    count = max(1, int(math.floor(seconds * fps + 1e-6)))
    return [round(i / float(fps), 6) for i in range(count)]


def framing(camera: dict, motion: dict, sk, every: int = 1) -> dict:
    """What the camera sees of the figure over the shot (motion.json, on the SOMA body): how much of the time all of
    it is in the picture, how near an edge it comes, how tall it stands in the picture, and what is lowest in view."""
    import standing
    from soma import Skeleton  # noqa: F401  (the caller's)

    order = [motion["joints"].index(name) for name in sk.joints]
    fps = float(motion.get("fps", 30))
    inside, worst, rows = 0, None, []
    for f in range(0, len(motion["root"]), every):
        row = motion["rotations"][f]
        pos, _ = sk.fk(motion["root"][f], [tuple(row[4 * j: 4 * j + 4]) for j in order])
        where = sample(camera, f / fps)
        seen = [standing.in_frame(where, p) for p in pos]
        edge = max(max(abs(s[1]), abs(s[2])) for s in seen)
        ok = all(s[0] for s in seen) and all(s[3] > 0 for s in seen)
        inside += ok
        rises = [s[2] for s in seen]
        rows.append({"frame": f, "seconds": round(f / fps, 2), "edge": round(edge, 3), "tall": round((max(rises) - min(rises)) / 2.0, 3),
                     "lowest": round(min(rises), 3), "tilt_deg": round(tilt_deg(where), 1), "lens_mm": round(where["lens_mm"], 1),
                     "distance_m": round(math.dist(where["at"], pos[0]), 2)})
        if worst is None or edge > worst["edge"]:
            worst = rows[-1]
    return {"frames_looked_at": len(rows), "all_in_picture_share": round(inside / float(len(rows)), 3), "nearest_edge": worst, "first": rows[0], "last": rows[-1], "rows": rows}


def main() -> None:
    sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
    from soma import Skeleton

    shot = sys.argv[1]
    with open(os.path.join(shot, "plan.json")) as f:
        plan = json.load(f)
    cameras = plan.get("moving_cameras") or {}
    if not cameras:
        sys.exit(f"{shot}: its plan has no moving cameras (a `moving_cameras` block in its brief, then plan_shot.py)")
    name = sys.argv[2] if len(sys.argv) > 2 else next(iter(cameras))
    with open(os.path.join(shot, "motion.json")) as f:
        motion = json.load(f)
    seen = framing(cameras[name], motion, Skeleton.load(), every=3)
    for row in seen["rows"][:: max(1, len(seen["rows"]) // 12)] + [seen["last"]]:
        print("CAMERA %s %5.2f s: %4.1f m off, lens %4.1f mm, looking up %4.1f deg; the figure fills %3.0f%% of the height, its lowest point %+.2f, nearest an edge %.2f" % (
            name, row["seconds"], row["distance_m"], row["lens_mm"], row["tilt_deg"], 100 * row["tall"], row["lowest"], row["edge"]))
    w = seen["nearest_edge"]
    print("CAMERA %s: all of the figure in the picture %.0f%% of the time; nearest an edge %.2f at %.2f s (1 is the edge)" % (name, 100 * seen["all_in_picture_share"], w["edge"], w["seconds"]))


if __name__ == "__main__":
    main()
