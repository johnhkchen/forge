"""Standing sets: a place of our own, built once and shot many times.

    python3 scripts/sets/standing.py check <set>        # is the set sound? (`just set-check <set>`)
    python3 scripts/sets/standing.py adopt <set> <file.glb> <x> <y> <z>   # use a .glb as the geometry, moved onto the set's origin
    python3 scripts/sets/standing.py blocks-glb <set>   # write set.glb as plain boxes, from the set's blocks
    python3 scripts/sets/standing.py list

A set is a folder, sets/<name>/, with a set.json:

    frame      the set's own frame: {origin [x, y, z], front_deg}. Everything
               else in the file is measured from that origin, so the whole
               set can be picked up and put down as one piece. `front_deg` is
               the heading its front faces (0: +z, where a stage's cameras are)
    footprint  the ground the set takes up, cameras and all, as an outline
               [[x, z], ...] in metres, going round once. `open_toward_deg`,
               if there, is a side kept clear for the set to grow on
    floor      where people can stand: rectangles on the ground, [[x0, z0], [x1, z1]]
    blocks     what is in the way, as boxes: {name, kind, center [x, y, z],
               size [across, tall, through], heading}. The same form a shot's
               plan.json carries as `set`, which apply_shot.py hands to the
               contact step in animate.py. A block counts as solid from the
               floor up to its top. `color` is what it is built in;
               `see_through` (ropes) stops a body but not a camera.
    ground     what is under and around the floor: {y, color, size_m}
    marks      named spots. Each has a kind:
                 stand   {at [x, z], facing_deg}
                 sit     {at (the hips, seated), stand_at (in front, standing),
                          facing_deg, seat_height_m, seat (the block sat on),
                          beside (blocks that belong to the seat: its back, an arm)}
                 touch   a stand mark with a spot for a hand:
                         {..., touch {hand, at [x, y, z]}}
                 lean    the same, for a hand resting on something
                 door    a stand mark just inside a way out, that says where it comes
                         out: {..., leads_to {set, mark}}, the door mark of another
                         set. The two name each other. `built: false` in leads_to
                         says the other side is not made yet
    paths      which marks people walk between, with turning points where a
               straight line would cross something: {from, to, via [[x, z]]}
    cameras    fixed, named: {at [x, y, z], aim [x, y, z], lens_mm, sees [marks]}
    lights     fixed: {name, kind (area, spot, sun), at, aim, power, color, size_m}
    backdrop   a painted picture standing behind the set: {image, center, width_m,
               height_m, heading, glow, cameras (the ones it must fill the view of; none: all)}
    backdrop_options  other pictures that can hang in the backdrop's place, by name:
               {options: [{place, title, image}]}. The ninja's stage has one per place in the
               world, so a portrait can be taken in front of any of them
    signs      painted flats that are part of the place (a shop sign, a wall
               painting): {name, image, center, width_m, height_m, heading, glow}.
               Unlike the backdrop, nothing is asked of them but that the picture is there
    slots      named spots dressing can stand on, like a character's sockets
    dressing   what stands on them now: {prop, slot, glb}; swap freely.
               `detail` is a heavier file of the same thing, for when you come close
    geometry   the set's own .glb and how to put it on the floor: {glb, move, turn_deg}

Everything is in metres, in the shot's own axes: y is up, the ground is x and
z, a heading of 0 faces +z and turns toward +x as it grows. A talk-show stage
faces +z: that is where the cameras are.

Placing a set in a world. A set.json never says where the set is: that is for
a world file to say (a future world.json: {"sets": {"studio": {"at": [x, z],
"facing_deg": 90}}}), one line per set, on one shared ground at true scale.
`placed` is the whole of the arithmetic: turn about the set's origin until its
front faces `facing_deg`, then slide the origin to `at`. Marks, cameras,
blocks, lights, the backdrop, the footprint and the .glb all move together,
because all of them are in the set's frame. A shot is planned and filmed in
that frame too, so moving a set never changes a shot made on it.

Blocking names marks, never coordinates. `stage_marks` turns a shot list
whose beats say `from`, `to` or `at` a mark into the path, distances, facings
and hand spots that plan_shot.py and timeline.py already know how to read. A
shot list that names no mark comes back untouched.

Plain Python: no Blender, no numpy.
"""

from __future__ import annotations

import copy
import json
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SETS = os.path.join(REPO, "sets")
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))

FORMAT = "forge-set/1"
BODY = 0.22  # metres of room a standing person needs around their middle
SEAT_MADE_FOR = 0.46  # the seat height our `sit` pose is written for
SEAT_SLACK = 0.06  # how far a seat may be from that and still be sat on
HEAD_STANDING, CHEST_STANDING = 1.62, 1.25  # where a standing person's head and chest are (the SOMA body)
HEAD_ABOVE_SEAT, CHEST_ABOVE_SEAT = 0.80, 0.45
PALM = 0.07  # from the wrist to the middle of the palm
SENSOR_MM, ASPECT = 36.0, 16.0 / 9.0
FRAME_MARGIN = 0.04  # a mark's head and feet stay this share of the frame inside its edge
MARK_KINDS = ("stand", "sit", "touch", "lean", "door")
BLOCK_KEYS = ("name", "kind", "center", "size", "heading")  # what a plan's `set` holds for each block


class SetProblem(ValueError):
    """Something a shot asked of a set that the set cannot give."""


# ---- reading a set ---------------------------------------------------------------


def folder(name: str) -> str:
    return name if os.path.isdir(name) and os.path.exists(os.path.join(name, "set.json")) else os.path.join(SETS, name)


def names() -> list:
    if not os.path.isdir(SETS):
        return []
    return sorted(n for n in os.listdir(SETS) if os.path.exists(os.path.join(SETS, n, "set.json")))


def load(name: str) -> dict:
    """A set by name (or by its folder). `dir` is added: where its files are."""
    where = folder(name)
    path = os.path.join(where, "set.json")
    if not os.path.exists(path):
        raise SetProblem(f"no set named {name!r}: there is no {os.path.relpath(path, REPO)} (sets: {', '.join(names()) or 'none'})")
    with open(path) as f:
        st = json.load(f)
    st["dir"] = where
    return st


def placed(st: dict, at=(0.0, 0.0), facing_deg=None):
    """How a set stands in a world: returns (point, heading), two functions that take a ground point [x, z] (or
    [x, y, z]) and a heading from the set's frame to the world's, with the set's origin at `at` and its front
    facing `facing_deg` (None: the way it already faces)."""
    frame = st.get("frame") or {}
    origin, front = frame.get("origin", [0.0, 0.0, 0.0]), float(frame.get("front_deg", 0.0))
    turn = 0.0 if facing_deg is None else float(facing_deg) - front
    c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))

    def point(p):
        x, z = p[0] - origin[0], p[-1] - origin[2]
        wx, wz = x * c + z * s + at[0], -x * s + z * c + at[1]
        return [round(wx, 4), round(wz, 4)] if len(p) == 2 else [round(wx, 4), round(p[1] - origin[1], 4), round(wz, 4)]

    def heading(h):
        return round(wrap(h + turn), 3)

    return point, heading


def inside(outline: list, x: float, z: float) -> bool:
    """Is a ground point inside an outline [[x, z], ...] (or on its edge)?"""
    hit = False
    for (x0, z0), (x1, z1) in zip(outline, outline[1:] + outline[:1]):
        if abs((x1 - x0) * (z - z0) - (z1 - z0) * (x - x0)) < 1e-9 and min(x0, x1) - 1e-9 <= x <= max(x0, x1) + 1e-9 and min(z0, z1) - 1e-9 <= z <= max(z0, z1) + 1e-9:
            return True
        if (z0 > z) != (z1 > z) and x < x0 + (x1 - x0) * (z - z0) / (z1 - z0):
            hit = not hit
    return hit


def plan_blocks(st: dict) -> list:
    """The set's blocks as a shot's plan.json carries them."""
    return [{key: copy.deepcopy(block[key]) for key in BLOCK_KEYS if key in block} for block in st.get("blocks") or []]


def block_named(st: dict, name: str):
    return next((b for b in st.get("blocks") or [] if b["name"] == name), None)


# ---- a little geometry -----------------------------------------------------------


def sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def unit(a):
    size = math.sqrt(dot(a, a))
    if size < 1e-9:
        raise SetProblem("two points that should differ are the same")
    return tuple(c / size for c in a)


def forward_of(heading: float) -> tuple:
    """The ground direction a heading faces, as (x, z)."""
    return math.sin(math.radians(heading)), math.cos(math.radians(heading))


def wrap(degrees: float) -> float:
    return (degrees + 180.0) % 360.0 - 180.0


def in_block(block: dict, x: float, z: float) -> tuple:
    """(across, through) of a ground point in a block's own axes, from its middle."""
    h = math.radians(block.get("heading", 0.0))
    dx, dz = x - block["center"][0], z - block["center"][2]
    return dx * math.cos(h) - dz * math.sin(h), dx * math.sin(h) + dz * math.cos(h)


def top_of(block: dict) -> float:
    return block["center"][1] + block["size"][1] / 2.0


def gap_to(block: dict, x: float, z: float) -> float:
    """How far a ground point is from a block's footprint; 0 inside it."""
    across, through = in_block(block, x, z)
    return math.hypot(max(0.0, abs(across) - block["size"][0] / 2.0), max(0.0, abs(through) - block["size"][2] / 2.0))


def in_the_way(st: dict) -> list:
    """Blocks that stand above the floor: the ones a body can bump into."""
    return [b for b in st.get("blocks") or [] if top_of(b) > 0.05]


def on_floor(st: dict, x: float, z: float) -> bool:
    for (x0, z0), (x1, z1) in (st.get("floor") or {}).get("areas") or []:
        if min(x0, x1) - 1e-6 <= x <= max(x0, x1) + 1e-6 and min(z0, z1) - 1e-6 <= z <= max(z0, z1) + 1e-6:
            return True
    return False


def sight_blocked(st: dict, eye, point, skip=()) -> str:
    """The name of a block standing between an eye and a point, or ''."""
    for block in st.get("blocks") or []:
        if block["name"] in skip or block.get("see_through"):
            continue  # ropes are in the way of a body, not of a camera
        h = math.radians(block.get("heading", 0.0))

        def local(p):
            dx, dy, dz = p[0] - block["center"][0], p[1] - block["center"][1], p[2] - block["center"][2]
            return (dx * math.cos(h) - dz * math.sin(h), dy, dx * math.sin(h) + dz * math.cos(h))

        a, b = local(eye), local(point)
        half = [s / 2.0 for s in block["size"]]
        lo, hi = 0.0, 1.0
        for axis in range(3):
            d = b[axis] - a[axis]
            if abs(d) < 1e-9:
                if abs(a[axis]) > half[axis]:
                    lo, hi = 1.0, 0.0
                    break
                continue
            t0, t1 = (-half[axis] - a[axis]) / d, (half[axis] - a[axis]) / d
            lo, hi = max(lo, min(t0, t1)), min(hi, max(t0, t1))
        if lo < hi - 1e-6 and hi > 0.0 and lo < 0.98:  # it may touch what the point rests on, right at the point
            return block["name"]
    return ""


def in_frame(camera: dict, point) -> tuple:
    """(is it in the picture, across -1..1, up -1..1, metres in front of the lens)."""
    eye, aim = camera["at"], camera["aim"]
    ahead = unit(sub(aim, eye))
    right = unit(cross(ahead, (0.0, 1.0, 0.0)))
    up = cross(right, ahead)
    d = sub(point, eye)
    depth = dot(d, ahead)
    if depth <= 0.05:
        return False, 0.0, 0.0, depth
    half_wide = (SENSOR_MM / 2.0) / float(camera["lens_mm"])
    across, rise = dot(d, right) / depth / half_wide, dot(d, up) / depth / (half_wide / ASPECT)
    return abs(across) <= 1.0 - FRAME_MARGIN and abs(rise) <= 1.0 - FRAME_MARGIN, across, rise, depth


# ---- marks -----------------------------------------------------------------------


def mark(st: dict, name: str) -> dict:
    found = (st.get("marks") or {}).get(name)
    if found is None:
        raise SetProblem(f"the set \"{st.get('name')}\" has no mark called \"{name}\" (it has: {', '.join(sorted(st.get('marks') or {}))})")
    return found


def own(m: dict) -> set:
    """The blocks a mark belongs with: its seat, and what stands `beside` it (a chair's back, a couch's arm)."""
    return {m.get("seat", "")} | set(m.get("beside") or [])


def stand_spot(m: dict) -> list:
    """Where a person stands at a mark: in front of a seat, or on the mark itself."""
    return list(m.get("stand_at") or m["at"])


def seat_spot(m: dict) -> list:
    return list(m["at"])


def head_and_feet(m: dict) -> list:
    """The points of a person at a mark that a camera must hold: the head, the chest, and the feet or the seat."""
    x, z = m["at"]
    if m["kind"] == "sit":
        seat = float(m["seat_height_m"])
        return [("head", (x, seat + HEAD_ABOVE_SEAT, z)), ("chest", (x, seat + CHEST_ABOVE_SEAT, z))]
    return [("head", (x, HEAD_STANDING, z)), ("chest", (x, CHEST_STANDING, z)), ("feet", (x, 0.05, z))]


def wrist_for(m: dict) -> list:
    """Where the wrist goes so the palm lands on a touch mark's spot: a palm's length back toward the body."""
    spot = m["touch"]["at"]
    x, z = stand_spot(m)
    away = math.hypot(spot[0] - x, spot[2] - z)
    if away < 1e-6:
        return list(spot)
    return [round(spot[0] - PALM * (spot[0] - x) / away, 4), spot[1], round(spot[2] - PALM * (spot[2] - z) / away, 4)]


def route(st: dict, a: str, b: str) -> list:
    """The turning points between two marks' standing spots, as the set's paths give them (none: a straight line)."""
    for path in st.get("paths") or []:
        if (path["from"], path["to"]) == (a, b):
            return [list(p) for p in path.get("via") or []]
        if (path["from"], path["to"]) == (b, a):
            return [list(p) for p in reversed(path.get("via") or [])]
    return []


def curve(points: list):
    """The smooth route plan_shot.py draws through ground points."""
    from plan_shot import Path

    return Path([{"x": p[0], "z": p[1]} for p in points])


# ---- is the set sound? -----------------------------------------------------------


def glb_bounds(path: str):
    """(lowest corner, highest corner) of everything in a .glb, read straight from the file."""
    with open(path, "rb") as f:
        f.read(12)
        size, _ = struct.unpack("<II", f.read(8))
        doc = json.loads(f.read(size))

    def matrix(node):
        if "matrix" in node:
            m = node["matrix"]
            return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
        t, s = node.get("translation", [0, 0, 0]), node.get("scale", [1, 1, 1])
        x, y, z, w = node.get("rotation", [0, 0, 0, 1])
        r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
        return [[r[i][0] * s[0], r[i][1] * s[1], r[i][2] * s[2], t[i]] for i in range(3)] + [[0, 0, 0, 1]]

    def times(a, b):
        return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]

    lo, hi = [1e9] * 3, [-1e9] * 3

    def visit(index, above):
        node = doc["nodes"][index]
        here = times(above, matrix(node))
        if "mesh" in node:
            for prim in doc["meshes"][node["mesh"]]["primitives"]:
                acc = doc["accessors"][prim["attributes"]["POSITION"]]
                for cx in (acc["min"][0], acc["max"][0]):
                    for cy in (acc["min"][1], acc["max"][1]):
                        for cz in (acc["min"][2], acc["max"][2]):
                            p = [here[i][0] * cx + here[i][1] * cy + here[i][2] * cz + here[i][3] for i in range(3)]
                            for i in range(3):
                                lo[i], hi[i] = min(lo[i], p[i]), max(hi[i], p[i])
        for child in node.get("children", []):
            visit(child, here)

    identity = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
    for scene in doc.get("scenes", [{"nodes": list(range(len(doc["nodes"])))}]):
        for index in scene["nodes"]:
            visit(index, identity)
    return lo, hi


def placed_bounds(st: dict):
    """The set's .glb as it stands on the floor: its box after the set's `geometry` move and turn."""
    geometry = st.get("geometry") or {}
    path = os.path.join(st["dir"], geometry.get("glb", "set.glb"))
    if not os.path.exists(path):
        return None
    lo, hi = glb_bounds(path)
    turn, move = math.radians(geometry.get("turn_deg", 0.0)), geometry.get("move", [0.0, 0.0, 0.0])
    xs, zs = [], []
    for x in (lo[0], hi[0]):
        for z in (lo[2], hi[2]):
            xs.append(x * math.cos(turn) + z * math.sin(turn) + move[0])
            zs.append(-x * math.sin(turn) + z * math.cos(turn) + move[2])
    return [min(xs), lo[1] + move[1], min(zs)], [max(xs), hi[1] + move[1], max(zs)]


def door_problem(st: dict, name: str, m: dict) -> str:
    """What is wrong with a door mark, or ''. A door names the set it leads into and the door mark it comes out at
    there; that mark leads back here. A side that is not made yet is said so (`built: false`), not left dangling."""
    to = m.get("leads_to") or {}
    if not to.get("set") or not to.get("mark"):
        return f"mark \"{name}\": a door needs leads_to {{set, mark}}: the set it leads into and the door it comes out at"
    if not os.path.exists(os.path.join(SETS, to["set"], "set.json")):
        return "" if to.get("built") is False else f"mark \"{name}\" leads to \"{to['set']}\", which is not a set (say \"built\": false in leads_to if it is still to come)"
    if to.get("built") is False:
        return f"mark \"{name}\": \"{to['set']}\" is a set now; take \"built\": false off the door"
    other = (load(to["set"]).get("marks") or {}).get(to["mark"])
    if not other or other.get("kind") != "door":
        return f"mark \"{name}\" leads to \"{to['mark']}\" in \"{to['set']}\", which is not a door there"
    back = other.get("leads_to") or {}
    if back.get("set") != st.get("name") or back.get("mark") != name:
        return f"mark \"{name}\" leads to \"{to['mark']}\" in \"{to['set']}\", but that door leads to \"{back.get('mark')}\" in \"{back.get('set')}\", not back here"
    return ""


def check(st: dict) -> tuple:
    """(what is wrong with a set, in words; what was looked at). Nothing wrong: the first is empty."""
    problems, seen = [], {}
    say = problems.append
    if st.get("format") != FORMAT:
        say(f"format is {st.get('format')!r}, not {FORMAT!r}")
    for key in ("name", "frame", "footprint", "floor", "blocks", "marks", "cameras", "lights", "geometry"):
        if key not in st:
            say(f"set.json has no \"{key}\"")
    if problems:
        return problems, seen
    blocks, marks, cameras = st["blocks"], st["marks"], st["cameras"]
    tall = in_the_way(st)
    doubled = {b["name"] for b in blocks if sum(1 for o in blocks if o["name"] == b["name"]) > 1}
    if doubled:
        say(f"two blocks share a name: {', '.join(sorted(doubled))}")
    for block in blocks:
        if any(k not in block for k in BLOCK_KEYS) or len(block["center"]) != 3 or len(block["size"]) != 3 or min(block["size"]) <= 0:
            say(f"block \"{block.get('name')}\" needs name, kind, center [x, y, z], size [across, tall, through] and heading")
    if not (st["floor"].get("areas") or []):
        say("the floor has no areas to stand on")
    seen["blocks"], seen["in_the_way"] = len(blocks), len(tall)

    # The set's own frame and footprint: what lets it be put down in a world as one piece.
    frame, outline = st["frame"], (st["footprint"] or {}).get("outline") or []
    if len(frame.get("origin") or []) != 3 or "front_deg" not in frame:
        say("frame needs origin [x, y, z] and front_deg")
    if len(outline) < 3:
        say("the footprint needs an outline of at least 3 ground points")
    else:
        if not inside(outline, frame.get("origin", [0, 0, 0])[0], frame.get("origin", [0, 0, 0])[-1]):
            say("the set's origin is outside its own footprint")
        out = [f"mark \"{n}\"" for n, m in marks.items() if "at" in m and not inside(outline, *m["at"])]
        out += [f"block \"{b['name']}\"" for b in tall if not inside(outline, b["center"][0], b["center"][2])]
        out += [f"camera \"{n}\"" for n, c in cameras.items() if "at" in c and not inside(outline, c["at"][0], c["at"][2])]
        for (x0, z0), (x1, z1) in st["floor"].get("areas") or []:
            if not all(inside(outline, x, z) for x in (x0, x1) for z in (z0, z1)):
                out.append("part of the floor")
        if out:
            say(f"outside the set's footprint: {', '.join(out)}")
        xs, zs = [p[0] for p in outline], [p[1] for p in outline]
        seen["footprint"] = {"across_m": round(max(xs) - min(xs), 2), "deep_m": round(max(zs) - min(zs), 2), "open_toward_deg": st["footprint"].get("open_toward_deg")}
    if any(abs(v) > 1e-9 for v in (st["geometry"].get("move") or [0, 0, 0])) or abs(st["geometry"].get("turn_deg", 0.0)) > 1e-9:
        say("the geometry is not built around the set's origin: its move and turn should be 0 (`standing.py adopt` bakes them into the .glb)")

    # Marks: on the floor, clear of what is in the way, seats the right height, hands in reach.
    for name, m in marks.items():
        if m.get("kind") not in MARK_KINDS:
            say(f"mark \"{name}\": kind is {m.get('kind')!r}, not one of {', '.join(MARK_KINDS)}")
            continue
        if "at" not in m or "facing_deg" not in m:
            say(f"mark \"{name}\" needs at [x, z] and facing_deg")
            continue
        seat = block_named(st, m.get("seat", "")) if m["kind"] == "sit" else None
        for label, (x, z) in (("stands", stand_spot(m)),) + ((("sits", seat_spot(m)),) if m["kind"] == "sit" else ()):
            if not on_floor(st, x, z):
                say(f"mark \"{name}\" {label} off the floor, at ({x}, {z})")
            for block in tall:
                if block["name"] in own(m):
                    continue
                room = gap_to(block, x, z)
                if room < BODY:
                    say(f"mark \"{name}\" {label} {100 * room:.0f} cm from \"{block['name']}\": a body needs {100 * BODY:.0f} cm")
        if m["kind"] == "sit":
            height = m.get("seat_height_m")
            if height is None or "stand_at" not in m:
                say(f"mark \"{name}\": a seat needs seat_height_m and stand_at (where you stand in front of it)")
                continue
            if abs(height - SEAT_MADE_FOR) > SEAT_SLACK:
                say(f"mark \"{name}\": a seat {height} m high is not one our sit pose fits ({SEAT_MADE_FOR - SEAT_SLACK:.2f} to {SEAT_MADE_FOR + SEAT_SLACK:.2f} m)")
            if seat is None:
                say(f"mark \"{name}\": its seat \"{m.get('seat')}\" is not one of the blocks")
            else:
                if abs(top_of(seat) - height) > 0.011:
                    say(f"mark \"{name}\": the seat is {height} m high but \"{seat['name']}\" tops out at {top_of(seat):.3f} m")
                if gap_to(seat, *seat_spot(m)) > 0.0:
                    say(f"mark \"{name}\": the hips are not over \"{seat['name']}\"")
            rise = math.dist(stand_spot(m), seat_spot(m))
            if not 0.25 <= rise <= 0.7:
                say(f"mark \"{name}\": standing {rise:.2f} m from the seat; 0.25 to 0.7 m is a step back onto a chair")
            fx, fz = forward_of(m["facing_deg"])
            if (stand_spot(m)[0] - m["at"][0]) * fx + (stand_spot(m)[1] - m["at"][1]) * fz < 0.2:
                say(f"mark \"{name}\": stand_at is not in front of the seat, the way it faces")
        if m["kind"] in ("touch", "lean"):
            touch = m.get("touch") or {}
            if touch.get("hand") not in ("left", "right") or len(touch.get("at") or []) != 3:
                say(f"mark \"{name}\": a {m['kind']} mark needs touch {{hand: left or right, at: [x, y, z]}}")
                continue
            tx, ty, tz = touch["at"]
            reach = math.hypot(tx - m["at"][0], tz - m["at"][1])
            if not 0.5 <= ty <= 1.45 or reach > 0.7:
                say(f"mark \"{name}\": the hand's spot is {ty} m up and {reach:.2f} m out; an arm reaches 0.5 to 1.45 m up, 0.7 m out")
            if any(gap_to(b, tx, tz) == 0.0 and ty < top_of(b) - 0.005 for b in tall):
                say(f"mark \"{name}\": the hand's spot is inside a block")
        if m["kind"] == "door":
            problem = door_problem(st, name, m)
            if problem:
                say(problem)
    # Two people at marks that share a hand's spot (a handshake) face each other across it.
    shared = {}
    for name, m in marks.items():
        if m.get("kind") == "touch" and m.get("touch") and "at" in m:
            shared.setdefault(tuple(m["touch"]["at"]), []).append(name)
    for spot, pair in shared.items():
        if len(pair) != 2:
            continue
        a, b = marks[pair[0]], marks[pair[1]]
        apart = math.dist(a["at"], b["at"])
        want = math.degrees(math.atan2(b["at"][0] - a["at"][0], b["at"][1] - a["at"][1]))
        off = max(abs(wrap(a["facing_deg"] - want)), abs(wrap(b["facing_deg"] - want - 180.0)))
        if not 0.6 <= apart <= 1.05 or off > 30.0:
            say(f"marks \"{pair[0]}\" and \"{pair[1]}\" share a hand's spot but stand {apart:.2f} m apart, {off:.0f} degrees off facing each other")
        seen.setdefault("meet", []).append({"marks": pair, "apart_m": round(apart, 3)})
    seen["marks"] = {kind: sorted(n for n, m in marks.items() if m.get("kind") == kind) for kind in MARK_KINDS}

    # Paths: between marks that exist, on the floor, clear of what is in the way.
    walked = []
    for path in st.get("paths") or []:
        if path.get("from") not in marks or path.get("to") not in marks:
            say(f"path {path.get('from')} to {path.get('to')}: both ends must be marks")
            continue
        a, b = marks[path["from"]], marks[path["to"]]
        points = [stand_spot(a)] + [list(p) for p in path.get("via") or []] + [stand_spot(b)]
        line = curve(points)
        worst, where = 9.0, None
        for i in range(0, len(line.points), 3):
            x, z = line.points[i]
            if not on_floor(st, x, z):
                say(f"path {path['from']} to {path['to']} leaves the floor at ({x:.2f}, {z:.2f})")
                break
            for block in tall:
                if block["name"] in own(a) | own(b):
                    continue
                room = gap_to(block, x, z)
                if room < worst:
                    worst, where = room, block["name"]
        if worst < BODY * 0.8:
            say(f"path {path['from']} to {path['to']} passes {100 * worst:.0f} cm from \"{where}\"; give it a turning point (via)")
        walked.append({"from": path["from"], "to": path["to"], "metres": round(line.length, 2), "nearest_cm": round(100 * worst) if where else None})
    seen["paths"] = walked

    # Cameras: each one holds the marks it says it sees, head to foot, with nothing in the way.
    shallow = st.get("stage") == "shallow"
    if shallow and not cameras:
        say("a stage needs cameras")
    views = {}
    for name, cam in cameras.items():
        if any(k not in cam for k in ("at", "aim", "lens_mm")):
            say(f"camera \"{name}\" needs at, aim and lens_mm")
            continue
        if not 14 <= cam["lens_mm"] <= 200:
            say(f"camera \"{name}\": a {cam['lens_mm']} mm lens is outside 14 to 200")
        if any(gap_to(b, cam["at"][0], cam["at"][2]) == 0.0 and cam["at"][1] < top_of(b) for b in tall):
            say(f"camera \"{name}\" is inside a block")
        if not cam.get("sees"):
            say(f"camera \"{name}\" sees no marks: list the ones it is there for")
        held = []
        for seen_mark in cam.get("sees") or []:
            if seen_mark not in marks:
                say(f"camera \"{name}\" sees \"{seen_mark}\", which is not a mark")
                continue
            m = marks[seen_mark]
            for part, point in head_and_feet(m):
                ok, across, rise, depth = in_frame(cam, point)
                if not ok:
                    say(f"camera \"{name}\" does not hold the {part} at \"{seen_mark}\" (it lands {across:+.2f} across, {rise:+.2f} up; the picture runs -1 to 1)")
                if part in ("head", "chest"):
                    behind = sight_blocked(st, cam["at"], point, skip=own(m))
                    if behind:
                        say(f"camera \"{name}\" cannot see the {part} at \"{seen_mark}\": \"{behind}\" is in the way")
            if shallow and cam["at"][2] < m["at"][1] + 1.0:
                say(f"camera \"{name}\" is not out front of \"{seen_mark}\": a stage faces its cameras")
            held.append(seen_mark)
        views[name] = held
    seen["cameras"] = views
    if shallow:
        depth = max(max(z0, z1) for (_, z0), (_, z1) in st["floor"]["areas"]) - min(min(z0, z1) for (_, z0), (_, z1) in st["floor"]["areas"])
        if depth > 5.0:
            say(f"the stage is {depth:.1f} m deep; a stage that faces its cameras is shallow (5 m at most)")
        unseen = sorted(n for n, m in marks.items() if not m.get("offstage") and not any(n in v for v in views.values()))
        if unseen:
            say(f"no camera sees: {', '.join(unseen)}")

    # Lights: fixed, above the floor, and on.
    if not st["lights"]:
        say("the set has no lights")
    for light in st["lights"]:
        if light.get("kind") not in ("area", "spot", "sun") or "at" not in light or float(light.get("power", 0)) <= 0:
            say(f"light \"{light.get('name')}\" needs kind (area, spot or sun), at and a power above 0")
        elif light["at"][1] < 1.0:
            say(f"light \"{light.get('name')}\" is {light['at'][1]} m up: lights hang above the set")
    seen["lights"] = [light.get("name") for light in st["lights"]]

    # The backdrop: its picture is there, it stands behind everyone, and it fills the widest camera's view.
    backdrop = st.get("backdrop")
    if backdrop:
        picture = os.path.join(st["dir"], backdrop.get("image", ""))
        if not os.path.isfile(picture):
            say(f"the backdrop's picture is missing: {backdrop.get('image')}")
        fx, fz = forward_of(backdrop.get("heading", 0.0))
        cx, cy, cz = backdrop["center"]
        for name, m in marks.items():
            if (m["at"][0] - cx) * fx + (m["at"][1] - cz) * fz < 0.3:
                say(f"mark \"{name}\" is not in front of the backdrop")
        for name, cam in cameras.items():
            if "at" not in cam or "aim" not in cam or name not in (backdrop.get("cameras") or cameras):
                continue  # a backdrop can be painted for some cameras only; the others see past it
            ahead = unit(sub(cam["aim"], cam["at"]))
            right = unit(cross(ahead, (0.0, 1.0, 0.0)))
            up = cross(right, ahead)
            half_wide = (SENSOR_MM / 2.0) / float(cam["lens_mm"])
            for sx in (-1.0, 1.0):
                for sy in (-1.0, 1.0):
                    ray = tuple(ahead[i] + right[i] * sx * half_wide + up[i] * sy * half_wide / ASPECT for i in range(3))
                    toward = ray[0] * fx + ray[2] * fz
                    if toward >= -1e-6:
                        continue  # looking along the backdrop, or away
                    t = ((cx - cam["at"][0]) * fx + (cz - cam["at"][2]) * fz) / toward
                    hit = tuple(cam["at"][i] + ray[i] * t for i in range(3))
                    if hit[1] < (st.get("ground") or {}).get("y", 0.0):
                        continue  # that corner of the picture is floor
                    if sight_blocked(st, cam["at"], hit):
                        continue  # a wall or a flat stands in front of it there
                    across = (hit[0] - cx) * fz - (hit[2] - cz) * fx
                    if abs(across) > backdrop["width_m"] / 2.0 + 0.01 or hit[1] > cy + backdrop["height_m"] / 2.0 + 0.01:
                        say(f"camera \"{name}\" sees past the edge of the backdrop ({across:+.1f} m across, {hit[1]:.1f} m up)")
        seen["backdrop"] = backdrop.get("image")

    for option in (st.get("backdrop_options") or {}).get("options") or []:
        if not backdrop:
            say("backdrop_options need a backdrop to hang in the place of")
            break
        if not os.path.isfile(os.path.join(st["dir"], option.get("image", ""))):
            say(f"backdrop option \"{option.get('place')}\": its picture is missing: {option.get('image')}")
    seen["backdrop_options"] = [o.get("place") for o in (st.get("backdrop_options") or {}).get("options") or []]
    for sign in st.get("signs") or []:
        if not os.path.isfile(os.path.join(st["dir"], sign.get("image", ""))):
            say(f"sign \"{sign.get('name')}\": its picture is missing: {sign.get('image')}")
        if len(sign.get("center") or []) != 3 or float(sign.get("width_m", 0)) <= 0 or float(sign.get("height_m", 0)) <= 0:
            say(f"sign \"{sign.get('name')}\" needs center [x, y, z], width_m and height_m")
    seen["signs"] = [sign.get("name") for sign in st.get("signs") or []]

    # Dressing stands on slots the set has.
    slots = st.get("slots") or {}
    for item in st.get("dressing") or []:
        if item.get("detail") and not os.path.isfile(os.path.join(st["dir"], item["detail"])):
            say(f"dressing \"{item.get('prop')}\": its detailed file {item['detail']} is missing")
        if item.get("slot") not in slots:
            say(f"dressing \"{item.get('prop')}\" stands on \"{item.get('slot')}\", which is not a slot")
        if not os.path.isfile(os.path.join(st["dir"], item.get("glb", ""))):
            say(f"dressing \"{item.get('prop')}\": {item.get('glb')} is missing")
    seen["dressing"] = [item.get("prop") for item in st.get("dressing") or []]

    # The .glb is there, and what is in the way is somewhere inside it.
    box = placed_bounds(st)
    if box is None:
        say(f"the set's geometry is missing: {st['geometry'].get('glb', 'set.glb')}")
    else:
        lo, hi = box
        for block in tall:
            c, top = block["center"], top_of(block)
            if not (lo[0] - 0.2 <= c[0] <= hi[0] + 0.2 and lo[2] - 0.2 <= c[2] <= hi[2] + 0.2 and top <= hi[1] + 0.2):
                say(f"block \"{block['name']}\" is outside the set's geometry (which spans {[round(v, 2) for v in lo]} to {[round(v, 2) for v in hi]})")
        seen["geometry"] = {"glb": st["geometry"].get("glb", "set.glb"), "from": [round(v, 2) for v in lo], "to": [round(v, 2) for v in hi]}
    return problems, seen


# ---- blocking: a shot list that names marks ---------------------------------------


def names_marks(shot: dict) -> bool:
    return bool(shot.get("start_mark")) or any(beat.get(key) for beat in shot.get("beats") or [] for key in ("from", "to", "at"))


def stage_marks(shot: dict, st: dict, library: dict) -> dict:
    """A shot list whose beats name marks, with the set's numbers filled in.

    Start at `start_mark`. A beat that says `to` a mark walks there, along the
    set's path between the two; `at` a mark stays (or, at a seat, sits down or
    gets up); `from` only says where the beat must already be. The result has
    what a shot list without marks has: the path as ground points, each move's
    and key's distance along it and which way it faces, and a text beat's
    start and end. A pose that is `seated` in the library takes the seat's
    spot, any other the spot in front of it. It also notes, under `stage`,
    what plan.json should carry for the cast: which hand is put where (a
    handshake), and which seat is sat on.

    A shot list that names no mark is returned as it came."""
    if not names_marks(shot):
        return shot
    out = copy.deepcopy(shot)
    poses = library["poses"]
    if not out.get("start_mark"):
        raise SetProblem("a shot list that names marks says where it starts: start_mark")

    def spot_of(mark_name: str, pose) -> tuple:
        m = mark(st, mark_name)
        seated = bool(pose and poses[pose].get("seated"))
        if seated and m["kind"] != "sit":
            raise SetProblem(f"the pose \"{pose}\" sits, and \"{mark_name}\" is not a seat")
        return (mark_name, "seat" if seated else "stand"), (seat_spot(m) if seated else stand_spot(m))

    # 1. Every place the shot stops, in order, and the ground points between them.
    here, at = spot_of(out["start_mark"], out.get("start_pose"))
    points, stops = [at], {}  # stops: id of a move, key or beat end -> index into points

    def go(to, to_at):
        nonlocal here, at
        if to == here:
            return
        if to[0] != here[0]:
            if here[1] == "seat":
                points.append(stand_spot(mark(st, here[0])))
            points.extend(route(st, here[0], to[0]))
            stand = stand_spot(mark(st, to[0]))
            if to[1] == "seat":
                points.append(stand)
        if math.dist(points[-1], to_at) > 1e-6:
            points.append(to_at)
        here, at = to, to_at

    for b, beat in enumerate(out["beats"]):
        source = beat.get("source", "poses")
        if beat.get("from") and beat["from"] != here[0]:
            raise SetProblem(f"beat \"{beat['name']}\" starts from \"{beat['from']}\", but the character is at \"{here[0]}\"")
        dest = beat.get("to") or beat.get("at") or here[0]
        if beat.get("at") and beat["at"] != here[0] and not beat.get("to"):
            raise SetProblem(f"beat \"{beat['name']}\" is at \"{beat['at']}\", but the character is at \"{here[0]}\": walk it there with a beat that says \"to\"")
        if source == "poses":
            for n, move in enumerate(beat.get("moves") or []):
                go(*spot_of(move.get("at") or dest, move["pose"]))
                stops[("move", b, n)] = len(points) - 1
        else:
            stops[("from", b)] = len(points) - 1
            go(*spot_of(dest, None))
            stops[("to", b)] = len(points) - 1
    if len(points) < 2:  # nobody went anywhere: a path still needs a direction
        fx, fz = forward_of(mark(st, out["start_mark"])["facing_deg"])
        points.append([round(points[0][0] + 0.5 * fx, 4), round(points[0][1] + 0.5 * fz, 4)])
    line = curve(points)
    along = []
    for p in points:  # the curve passes through every point, in order (twice, where a route doubles back)
        later = [k for k in range(len(line.points)) if not along or line.along[k] >= along[-1] - 1e-6]
        best = min(later, key=lambda k, p=p: (round(math.dist(line.points[k], p), 4), k))
        along.append(round(line.along[best], 4))

    def facing_at(metres: float, heading: float) -> float:
        """facing_deg for something at `metres` along the path that must face `heading` on the set."""
        return round(wrap(heading - line.at(metres)[2]), 2)

    out["path"] = [{"x": round(p[0], 4), "z": round(p[1], 4)} for p in points]
    out["start_facing_deg"] = facing_at(along[0], mark(st, out["start_mark"])["facing_deg"])

    # 2. Fill the numbers in.
    touches, seats, used = [], [], [out["start_mark"]]
    here_mark = out["start_mark"]
    for b, beat in enumerate(out["beats"]):
        source = beat.get("source", "poses")
        dest = beat.get("to") or beat.get("at") or here_mark
        if source == "poses":
            for n, move in enumerate(beat.get("moves") or []):
                where = move.get("at") or dest
                m = mark(st, where)
                move["at_m"], move["side_m"] = along[stops[("move", b, n)]], 0.0
                move["facing_deg"] = facing_at(move["at_m"], m["facing_deg"])
                move.pop("at", None)
                hand = (m.get("touch") or {}).get("hand")
                if hand and f"{hand}_hand" in (move.get("pins") or []) and not any(t["beat"] == beat["name"] for t in touches):
                    touches.append({"beat": beat["name"], "pin": f"{hand}_hand", "mark": where, "palm": list(m["touch"]["at"]), "wrist": wrist_for(m)})
                if poses[move["pose"]].get("seated") and not any(t["beat"] == beat["name"] for t in seats):
                    seats.append({"beat": beat["name"], "mark": where, "seat": m.get("seat"), "seat_height_m": m["seat_height_m"], "at": seat_spot(m)})
                here_mark = where
        else:
            beat["from_m"], beat["to_m"] = along[stops[("from", b)]], along[stops[("to", b)]]
            if source == "video":
                # A stretch of a clip stands on the mark facing the way the mark faces, whichever way the camera saw it.
                beat["facing_deg"] = facing_at(beat["from_m"], mark(st, here_mark)["facing_deg"])
            for key in beat.get("keys") or []:
                where = key.pop("where", None)
                if where == "start":
                    key["at_seconds"], key["at_m"] = 0.0, beat["from_m"]
                    key["facing_deg"] = facing_at(key["at_m"], mark(st, here_mark)["facing_deg"])
                elif where == "end":
                    count = int(beat["frames"]) if beat.get("frames") else int(round(float(beat["seconds"]) * 30))
                    key["at_seconds"], key["at_m"] = round(count / 30.0, 4), beat["to_m"]
                    key["facing_deg"] = facing_at(key["at_m"], mark(st, dest)["facing_deg"])
                elif where is not None:
                    raise SetProblem(f"beat \"{beat['name']}\": a key is at the beat's \"start\" or \"end\", not \"{where}\"")
                key.setdefault("side_m", 0.0)
                key.setdefault("only", [])
            here_mark = dest
        if dest not in used:
            used.append(dest)
        for key in ("from", "to", "at"):
            beat.pop(key, None)
    out.pop("start_mark", None)
    out["stage"] = {"set": st["name"], "marks": used, "touches": touches, "seats": seats,
                    "seated_poses": sorted(name for name, pose in poses.items() if pose.get("seated")),
                    "starts_seated": bool(poses[out["start_pose"]].get("seated"))}
    return out


def into_plan(record: dict, st: dict, shot: dict) -> dict:
    """Put the set into a shot's plan.json: its blocks (what the contact step keeps a body out of),
    its wall if the checks should measure one, and what blocking by marks asked for."""
    record["set"] = plan_blocks(st)
    if st.get("wall"):
        record["wall"] = next(b for b in record["set"] if b["name"] == st["wall"])
    record["standing_set"] = st["name"]
    stage = shot.get("stage")
    if not stage:
        return record
    moves = record["moves"]
    # A hand put on a spot of the set: every pinned move of that beat holds the wrist where the set says, not
    # where the pose happened to have it. Two people given the same spot then meet on it.
    for touch in stage["touches"]:
        frames = []
        for move in moves:
            if move["beat"] == touch["beat"] and touch["pin"] in (move.get("pin_points") or {}):
                move["pose_put_it_cm_away"] = round(100 * math.dist(move["pin_points"][touch["pin"]], touch["wrist"]), 1)
                move["pin_points"][touch["pin"]] = list(touch["wrist"])
                frames.append(move["frame"])
        touch["from_frame"], touch["to_frame"] = (min(frames), max(frames)) if frames else (None, None)
    # Seated: from the frame a sitting pose is reached to the last frame one is held, a stretch per sitting.
    # (A shot that starts in a sitting pose is seated from its first frame.)
    by_beat = {seat["beat"]: seat for seat in stage["seats"]}
    spans, open_span = [], None
    for n, move in enumerate(moves):
        if move.get("pose") in stage["seated_poses"] and move["beat"] in by_beat:
            if open_span is None:
                seat = by_beat[move["beat"]]
                open_span = {k: seat[k] for k in ("mark", "seat", "seat_height_m", "at")}
                open_span["from_frame"] = 0 if n == 0 and stage["starts_seated"] else move["frame"]
                spans.append(open_span)
            open_span["to_frame"] = move["frame"]
        else:
            open_span = None
    record["stage"] = {"set": st["name"], "marks": stage["marks"], "touches": stage["touches"], "seats": spans}
    return record


# ---- the set as plain boxes --------------------------------------------------------


def blocks_glb(st: dict, out: str) -> str:
    """The set's blocks as a .glb of plain boxes: the simplest geometry a set can have."""
    import to_gltf

    glb = to_gltf.Glb()
    nodes = to_gltf.set_blocks(glb, plan_blocks(st))
    glb.doc["scenes"], glb.doc["scene"] = [{"name": st["name"], "nodes": nodes}], 0
    glb.write(out)
    return out


def adopt(st: dict, source: str, move, turn_deg: float = 0.0) -> str:
    """Take a .glb made somewhere else (a finished run's object) as the set's geometry, around the set's origin:
    the file is copied with one node added above everything in it, carrying the move and the turn."""
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import blockout_recipe

    doc, rest = blockout_recipe.read(source)
    half = math.radians(turn_deg) / 2.0
    for scene in doc.get("scenes") or []:
        doc["nodes"].append({"name": "set: " + st["name"], "children": list(scene["nodes"]), "translation": [float(v) for v in move],
                             "rotation": [0.0, math.sin(half), 0.0, math.cos(half)]})
        scene["nodes"] = [len(doc["nodes"]) - 1]
    out = os.path.join(st["dir"], (st.get("geometry") or {}).get("glb", "set.glb"))
    blockout_recipe.write(out, doc, rest)
    return out


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "adopt":  # adopt <set> <file.glb> <x> <y> <z> [turn]: see `adopt`
        st = load(args[1])
        print("SET wrote", os.path.relpath(adopt(st, args[2], [float(v) for v in args[3:6]], float(args[6]) if len(args) > 6 else 0.0), REPO))
        return
    if not args or args[0] not in ("check", "blocks-glb", "list"):
        sys.exit(__doc__.split("\n\n")[1])
    if args[0] == "list":
        for name in names():
            print("SET", name)
        return
    failed = 0
    for name in args[1:] or names():
        st = load(name)
        if args[0] == "blocks-glb":
            print("SET wrote", os.path.relpath(blocks_glb(st, os.path.join(st["dir"], "set.glb")), REPO))
            continue
        problems, seen = check(st)
        marks = seen.get("marks") or {}
        print(f"SET {st.get('name')}: {seen.get('blocks', 0)} blocks ({seen.get('in_the_way', 0)} in the way), marks: "
              + "; ".join(f"{kind} {', '.join(found)}" for kind, found in marks.items() if found))
        for path in seen.get("paths") or []:
            print(f"SET {st.get('name')}: path {path['from']} to {path['to']}: {path['metres']} m" + (f", {path['nearest_cm']} cm from the nearest thing" if path["nearest_cm"] is not None else ""))
        for camera, held in (seen.get("cameras") or {}).items():
            print(f"SET {st.get('name')}: camera {camera} holds {', '.join(held) or 'nothing'}")
        for line in problems:
            print(f"SET {st.get('name')}: PROBLEM {line}")
        if seen.get("footprint"):
            print(f"SET {st.get('name')}: footprint {seen['footprint']['across_m']} m across, {seen['footprint']['deep_m']} m deep" + (f", open toward {seen['footprint']['open_toward_deg']} degrees" if seen["footprint"]["open_toward_deg"] is not None else ""))
        print(f"SET {st.get('name')}: " + ("sound" if not problems else f"{len(problems)} problems"))
        failed += bool(problems)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
