"""Writes the halfpipe as a standing set: sets/halfpipe/set.json, from the few numbers below.

    python3 scripts/skate/halfpipe_set.py          # then `just halfpipe-build` makes set.glb from it

The ramp's shape is said once, in RAMP. Everything else in the set (where
the decks' boxes are, where the marks, cameras and lights go, the ground it
takes up) is worked out from that, so a ramp of another size is a change to
RAMP and nothing else. scripts/skate/pipe.py turns the same numbers into
"where is the surface, and which way does it face".

Plain Python: no Blender.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from pipe import Pipe  # noqa: E402

# A vert ramp in the X Games style, sized for this world: a little smaller than the real thing (theirs has
# transitions of about 3.4 m too, but well over half a metre of vert, and is twice as long).
RAMP = {"flat_m": 5.0, "radius_m": 3.4, "vert_m": 0.3, "deck_m": 1.6, "width_m": 12.0, "coping_radius_m": 0.03, "coping_proud_m": 0.012}
RIDE_LINE_Z = 2.0      # where along the ramp a run is ridden: nearer the open end the cameras look in from
RAIL_M = 1.1           # the railing at the back of each deck
PLY = [0.62, 0.43, 0.25]
PLY_DARK = [0.47, 0.32, 0.19]
STEEL = [0.72, 0.74, 0.76]


def build() -> dict:
    pipe = Pipe(RAMP)
    w, e, h, half = pipe.wall_x, pipe.end_x, pipe.height, pipe.width / 2.0
    deck_x = round((w + e) / 2.0, 3)
    front = half + 0.5
    blocks, marks = [], {}
    for side, name in ((-1.0, "left"), (1.0, "right")):
        blocks.append({"name": "deck " + name, "kind": "deck", "center": [side * deck_x, round(h / 2.0, 3), 0.0], "size": [round(pipe.deck, 3), round(h, 3), pipe.width], "heading": 0.0,
                       "color": PLY_DARK, "build": False})
        blocks.append({"name": "rail " + name, "kind": "rail", "center": [round(side * (e - 0.04), 3), round(h + RAIL_M / 2.0, 3), 0.0], "size": [0.08, RAIL_M, pipe.width], "heading": 0.0,
                       "color": STEEL, "see_through": True, "build": False})
        marks["deck_" + name] = {"kind": "stand", "at": [side * deck_x, RIDE_LINE_Z], "facing_deg": -90.0 * side, "floor_y": round(h, 3),
                                 "about": "on the %s platform, %.1f m up, looking into the pipe: where a run starts and ends" % (name, h)}
    marks["flat"] = {"kind": "stand", "at": [0.0, RIDE_LINE_Z], "facing_deg": 0.0, "about": "the middle of the flat bottom"}
    return {
        "format": "forge-set/1",
        "name": "halfpipe",
        "title": "The halfpipe",
        "about": "A plywood vert ramp out past the settlement: a flat bottom, a curved wall up each side, a steel tube along each top edge and a platform behind it. Somewhere to roll back and forth and, with enough speed, leave the top.",
        "stage": "open",
        "frame": {"origin": [0.0, 0.0, 0.0], "front_deg": 0.0, "about": "the origin is the middle of the flat bottom, on the wood; the front is the open end the cameras look in from"},
        "footprint": {"outline": [[-(e + 0.5), -front], [e + 0.5, -front], [e + 0.5, front], [1.6, front + 6.7], [-1.6, front + 6.7], [-(e + 0.5), front]],
                      "about": "the ramp and a little ground round it, and a point out front where the side camera stands"},
        "units": "metres. y is up and 0 is the flat bottom. x is across the pipe (the walls are at -x and +x), z is along it; the front is +z.",
        "ramp": dict(RAMP, height_m=round(h, 3), wall_x_m=round(w, 3), lip_s_m=round(pipe.lip, 4), ride_line_z=RIDE_LINE_Z,
                     about="The ramp cut across: it is this shape all the way along z. `s` is metres along the riding surface from the middle of the flat (minus to the left, plus to the right). scripts/skate/pipe.py reads the numbers here and answers where the surface is and which way it faces at any point across; `cross_section` says the same thing piece by piece.",
                     coping=[{"side": name, "centre": [round(v, 4) for v in pipe.coping(side)], "radius_m": pipe.coping_r} for side, name in ((-1.0, "left"), (1.0, "right"))],
                     cross_section=pipe.sections()),
        "floor": {"areas": [[[-pipe.half_flat, -half], [pipe.half_flat, half]], [[-e, -half], [-w, half]], [[w, -half], [e, half]]],
                  "note": "the flat bottom and the two platforms. The curved walls are ridden, not stood on."},
        "ground": {"y": -0.02, "color": [0.72, 0.71, 0.69], "size_m": 60.0},
        "blocks": blocks,
        "marks": marks,
        "paths": [],
        "cameras": {
            "side": {"at": [0.0, 2.6, front + 6.2], "aim": [0.0, 3.2, RIDE_LINE_Z], "lens_mm": 22, "sees": ["flat", "deck_left", "deck_right"],
                     "about": "side-on from out front, level with the middle of the flat: the whole ramp and the air above both lips"},
            "low": {"at": [-1.2, 0.45, half - 0.5], "aim": [w, h + 0.9, RIDE_LINE_Z - 0.4], "lens_mm": 20, "sees": ["deck_right"],
                    "about": "low on the flat bottom, looking up the right wall"},
            "deck": {"at": [-(deck_x + 0.2), h + 1.75, half - 0.6], "aim": [1.2, 1.9, RIDE_LINE_Z - 0.6], "lens_mm": 18, "sees": ["flat", "deck_right"],
                     "about": "from the left platform, looking down into the pipe and across to the other lip"},
        },
        "lights": [
            {"name": "sun", "kind": "sun", "at": [-6.0, 16.0, 12.0], "aim": [0.0, 1.5, 0.0], "power": 2.2, "color": [1.0, 0.96, 0.88]},
            {"name": "sky", "kind": "area", "at": [4.0, 12.0, 9.0], "aim": [0.0, 1.5, 0.0], "power": 500.0, "color": [0.88, 0.93, 1.0], "size_m": 12.0},
        ],
        "world": {"color": [0.8, 0.86, 0.9], "strength": 0.7},
        "backdrop": None,
        "signs": [],
        "slots": {},
        "dressing": [],
        "geometry": {"glb": "set.glb", "move": [0.0, 0.0, 0.0], "turn_deg": 0.0,
                     "built_by": "python3 scripts/skate/halfpipe_set.py, then just halfpipe-build (scripts/skate/build_halfpipe.py)"},
    }


def main() -> None:
    out = os.path.join(REPO, "sets", "halfpipe", "set.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(build(), f, indent=1)
        f.write("\n")
    print("HALFPIPE wrote", os.path.relpath(out, REPO))


if __name__ == "__main__":
    main()
