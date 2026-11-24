"""The ninja's casting office: a small building beside his photo stage, written as a set from a few numbers.

    python3 scripts/sets/casting_office.py          # writes sets/casting-office/set.json and build.json
    just set-build casting-office                   # then builds set.glb from them, in a background Blender

A back room off the photo stage, where the ninja holds auditions. Inside it is
one plain rectangular room, the room the concept pictures in
world/marble/casting-office/concepts/ all show:

    the far end    a cloth backdrop on a rod, two stand lamps, open wooden floor
                   and a taped X in front of it (room for three side by side)
    the near end   a folding table, three odd chairs behind it for the panel,
                   and the box camera on a tripod beside it
    side walls     a window in one, one plain door in the other
    ceiling        3 m

Outside it is the stage's own colors, off-white walls with steel-blue trim and a
steel-blue pitched roof, and a little porch over the door, which faces the stage.

The set's frame: the origin is the middle of the floor inside, at floor level.
The room runs along x, 6 m: the backdrop end is +x, the panel's end -x. It is
5 m across z: the door is in the +z wall (the set's front, front_deg 0), the
window in the -z wall. That is how from_marble.py squares up a Marble world
(the long side along x, the middle of the floor at the origin), so a Marble
world of this room drops in with a turn of a quarter and a little scaling:
`marble_seat` in set.json says how (`just marble-seat`).

Walls, the posts and the furniture are blocks (what is in the way, the same
boxes a walk in the world bumps into); the floor, ceiling, roof, the door's
head, the window's frame, and what is only looked at are build.json extras.
The door's head is not a block, or nobody could walk under it. Plain Python.
"""

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(REPO, "sets", "casting-office")

# The room inside the walls, in metres.
LONG, ACROSS, TALL = 6.0, 5.0, 3.0
WALL = 0.2
CEILING = 0.15                   # the ceiling's thickness: the walls stand TALL + CEILING
DOOR = (0.6, 1.6, 2.1)           # x from, x to, how high: in the +z wall, toward the backdrop end
WINDOW = (-0.2, 1.4, 0.8, 2.3)   # x from, x to, sill, head: in the -z wall
PORCH = (0.2, 2.0, 1.2)          # x from, x to, how deep out from the +z wall
RISE, EAVES = 1.1, 0.35          # the roof: how far the ridge stands above the walls, how far it hangs over

X, Z = LONG / 2.0, ACROSS / 2.0  # inside faces
XO, ZO = X + WALL, Z + WALL      # outside faces
WALL_TOP = TALL + CEILING

WHITE = [0.98, 0.973, 0.961]     # b28 off-white #faf8f5
CREAM = [0.949, 0.937, 0.914]    # b28 cream #f2efe9
BLUE = [0.267, 0.404, 0.608]     # b28 steel blue #44679b
DEEP_BLUE = [0.227, 0.345, 0.522]
WOOD = [0.80, 0.66, 0.48]
DARK_WOOD = [0.55, 0.40, 0.27]
BRASS = [0.78, 0.62, 0.32]
INK = [0.11, 0.098, 0.09]


def r(v):
    return round(v, 4)


def box(name, lo, hi, color):
    return {"name": name, "box": {"min": [r(v) for v in lo], "max": [r(v) for v in hi]}, "color": color}


def block(name, kind, lo, hi, color, build=True):
    """A box in the way, from its two corners."""
    b = {"name": name, "kind": kind, "center": [r((lo[i] + hi[i]) / 2.0) for i in range(3)], "size": [r(hi[i] - lo[i]) for i in range(3)], "heading": 0.0, "color": color}
    if not build:
        b["build"] = False
    return b


def blocks():
    door0, door1, _ = DOOR
    win0, win1, sill, _ = WINDOW
    out = [
        # Walls. The two end walls run the whole way across, corners and all.
        block("wall, backdrop end", "wall", [X, 0, -ZO], [XO, WALL_TOP, ZO], WHITE),
        block("wall, panel end", "wall", [-XO, 0, -ZO], [-X, WALL_TOP, ZO], WHITE),
        block("wall, door side, panel end", "wall", [-X, 0, Z], [door0, WALL_TOP, ZO], WHITE),
        block("wall, door side, backdrop end", "wall", [door1, 0, Z], [X, WALL_TOP, ZO], WHITE),
        block("wall, window side, panel end", "wall", [-X, 0, -ZO], [win0, WALL_TOP, -Z], WHITE),
        block("wall, window side, backdrop end", "wall", [win1, 0, -ZO], [X, WALL_TOP, -Z], WHITE),
        block("wall under the window", "wall", [win0, 0, -ZO], [win1, sill, -Z], WHITE),
        # The porch's two posts.
        block("porch post, panel end", "post", [PORCH[0], 0, ZO + PORCH[2] - 0.15], [PORCH[0] + 0.1, 2.35, ZO + PORCH[2] - 0.05], BLUE),
        block("porch post, backdrop end", "post", [PORCH[1] - 0.1, 0, ZO + PORCH[2] - 0.15], [PORCH[1], 2.35, ZO + PORCH[2] - 0.05], BLUE),
        # The far end: the backdrop, and the two lamps on stands (built as extras: a box would not look like a lamp).
        block("backdrop", "flat", [X - 0.17, 0.05, -1.6], [X - 0.12, 2.6, 1.6], BLUE),
        block("lamp, window side", "lamp", [2.05, 0, -2.1], [2.45, 1.75, -1.7], WHITE, build=False),
        block("lamp, door side", "lamp", [2.05, 0, 1.7], [2.45, 1.75, 2.1], WHITE, build=False),
        # The near end: the panel's folding table and three odd chairs, and the box camera on its tripod.
        block("panel table", "table", [-1.9, 0, -1.1], [-1.2, 0.75, 1.1], CREAM, build=False),
        block("box camera", "camera", [-1.4, 0, -1.85], [-1.0, 1.4, -1.45], DARK_WOOD, build=False),
    ]
    for i, (z, color) in enumerate(((-0.8, BLUE), (0.0, DARK_WOOD), (0.8, DEEP_BLUE)), start=1):
        out.append(block("panel seat %d" % i, "seat", [-2.82, 0, z - 0.22], [-2.38, 0.46, z + 0.22], color))
        out.append(block("panel back %d" % i, "seat", [-2.88, 0, z - 0.2], [-2.82, 1.0, z + 0.2], color))
    return out


def extras():
    door0, door1, door_top = DOOR
    win0, win1, sill, head = WINDOW
    p0, p1, deep = PORCH
    ex = [
        box("floor", [-XO, -0.12, -ZO], [XO, 0.0, ZO], WOOD),
        box("ceiling", [-XO, TALL, -ZO], [XO, WALL_TOP, ZO], WHITE),
        box("over the door", [door0, door_top, Z], [door1, WALL_TOP, ZO], WHITE),
        box("over the window", [win0, head, -ZO], [win1, WALL_TOP, -Z], WHITE),
        # A steel-blue skirting all round the outside, as on the stage, with the doorway left open.
        box("skirting, backdrop end", [XO, 0, -ZO - 0.03], [XO + 0.03, 0.3, ZO + 0.03], BLUE),
        box("skirting, panel end", [-XO - 0.03, 0, -ZO - 0.03], [-XO, 0.3, ZO + 0.03], BLUE),
        box("skirting, window side", [-XO, 0, -ZO - 0.03], [XO, 0.3, -ZO], BLUE),
        box("skirting, door side, panel end", [-XO, 0, ZO], [door0 - 0.08, 0.3, ZO + 0.03], BLUE),
        box("skirting, door side, backdrop end", [door1 + 0.08, 0, ZO], [XO, 0.3, ZO + 0.03], BLUE),
        # The door: a steel-blue frame outside, the leaf standing open against the wall outside.
        box("door frame, panel side", [door0 - 0.08, 0, ZO], [door0, door_top + 0.08, ZO + 0.05], BLUE),
        box("door frame, backdrop side", [door1, 0, ZO], [door1 + 0.08, door_top + 0.08, ZO + 0.05], BLUE),
        box("door frame, head", [door0 - 0.08, door_top, ZO], [door1 + 0.08, door_top + 0.08, ZO + 0.05], BLUE),
        box("door, open", [door1 + 0.1, 0.02, ZO + 0.06], [door1 + 0.1 + (door1 - door0) - 0.04, door_top - 0.02, ZO + 0.1], BLUE),
        box("door knob", [door1 + (door1 - door0) - 0.06, 0.98, ZO + 0.1], [door1 + (door1 - door0) - 0.02, 1.02, ZO + 0.14], BRASS),
        # The window: a frame outside and a cross in the middle of the opening. No glass.
        box("window frame, sill", [win0 - 0.08, sill - 0.06, -ZO - 0.08], [win1 + 0.08, sill, -ZO + 0.02], BLUE),
        box("window frame, head", [win0 - 0.08, head, -ZO - 0.05], [win1 + 0.08, head + 0.08, -ZO], BLUE),
        box("window frame, panel side", [win0 - 0.08, sill, -ZO - 0.05], [win0, head, -ZO], BLUE),
        box("window frame, backdrop side", [win1, sill, -ZO - 0.05], [win1 + 0.08, head, -ZO], BLUE),
        box("window bar, up", [(win0 + win1) / 2 - 0.03, sill, -Z - 0.12], [(win0 + win1) / 2 + 0.03, head, -Z - 0.08], BLUE),
        box("window bar, across", [win0, (sill + head) / 2 - 0.03, -Z - 0.12], [win1, (sill + head) / 2 + 0.03, -Z - 0.08], BLUE),
        box("window ledge, inside", [win0 - 0.05, sill - 0.04, -Z], [win1 + 0.05, sill, -Z + 0.1], CREAM),
        # Steel-blue corner boards, so the box reads as a building from far off.
        box("corner, backdrop end, door side", [XO - 0.06, 0, ZO - 0.06], [XO + 0.04, WALL_TOP, ZO + 0.04], BLUE),
        box("corner, backdrop end, window side", [XO - 0.06, 0, -ZO - 0.04], [XO + 0.04, WALL_TOP, -ZO + 0.06], BLUE),
        box("corner, panel end, door side", [-XO - 0.04, 0, ZO - 0.06], [-XO + 0.06, WALL_TOP, ZO + 0.04], BLUE),
        box("corner, panel end, window side", [-XO - 0.04, 0, -ZO - 0.04], [-XO + 0.06, WALL_TOP, -ZO + 0.06], BLUE),
        # The porch: a deck, a little roof on two posts (the posts are blocks), a mat at the door.
        box("porch deck", [p0, -0.12, ZO], [p1, 0.0, ZO + deep], DARK_WOOD),
        box("porch roof", [p0 - 0.1, 2.35, ZO], [p1 + 0.1, 2.45, ZO + deep + 0.05], DEEP_BLUE),
        box("door mat", [door0 + 0.1, 0.0, ZO + 0.08], [door1 - 0.1, 0.015, ZO + 0.6], CREAM),
        # Inside, at the far end: the rod the backdrop hangs from, and the taped X.
        {"name": "backdrop rod", "tube": [[X - 0.15, 2.62, -1.75, 0.025], [X - 0.15, 2.62, 1.75, 0.025]], "sides": 6, "color": BRASS},
        {"name": "taped X, one way", "tube": [[1.05, 0.004, -0.15, 0.025, 0.004], [1.35, 0.004, 0.15, 0.025, 0.004]], "sides": 4, "color": WHITE},
        {"name": "taped X, other way", "tube": [[1.05, 0.004, 0.15, 0.025, 0.004], [1.35, 0.004, -0.15, 0.025, 0.004]], "sides": 4, "color": WHITE},
    ]
    # The roof: a white gable (a three-sided bar along x) under two steel-blue slabs.
    slope = math.atan2(RISE, ZO)
    ex.append({"name": "gable", "tube": [[-XO, WALL_TOP + RISE / 3.0, 0.0, ZO, RISE * 2.0 / 3.0], [XO, WALL_TOP + RISE / 3.0, 0.0, ZO, RISE * 2.0 / 3.0]],
               "sides": 3, "turn": 30, "color": WHITE})
    length = math.hypot(ZO, RISE)
    start, end = -0.05, length + EAVES
    middle, half = (start + end) / 2.0, (end - start) / 2.0
    for side, sign in (("door side", 1.0), ("window side", -1.0)):
        down = (sign * math.cos(slope), -math.sin(slope))  # (z, y) down the slope from the ridge
        normal = (sign * math.sin(slope), math.cos(slope))
        z = down[0] * middle + normal[0] * 0.06
        y = WALL_TOP + RISE + down[1] * middle + normal[1] * 0.06
        ex.append({"name": "roof, %s" % side, "tube": [[-XO - EAVES, r(y), r(z), r(half), 0.06], [XO + EAVES, r(y), r(z), r(half), 0.06]],
                   "sides": 4, "up": [0.0, r(normal[1]), r(normal[0])], "color": DEEP_BLUE})
    ex.append({"name": "ridge", "tube": [[-XO - EAVES, WALL_TOP + RISE + 0.1, 0.0, 0.09], [XO + EAVES, WALL_TOP + RISE + 0.1, 0.0, 0.09]], "sides": 6, "color": BLUE})
    # The lamps: three legs, a pole and a head turned toward the backdrop.
    for name, z in (("window side", -1.9), ("door side", 1.9)):
        for k in range(3):
            a = math.radians(90 + 120 * k)
            ex.append({"name": "lamp leg %d, %s" % (k + 1, name), "tube": [[r(2.25 + 0.2 * math.cos(a)), 0.0, r(z + 0.2 * math.sin(a)), 0.015], [2.25, 0.55, z, 0.015]], "sides": 5, "color": DARK_WOOD})
        ex.append({"name": "lamp pole, %s" % name, "tube": [[2.25, 0.5, z, 0.02], [2.25, 1.6, z, 0.02]], "sides": 6, "color": DARK_WOOD})
        aim = (X - 0.15 - 2.25, -0.6 * z)  # toward the middle of the backdrop
        n = math.hypot(*aim)
        ex.append({"name": "lamp head, %s" % name, "tube": [[2.25, 1.62, z, 0.07], [r(2.25 + 0.22 * aim[0] / n), 1.58, r(z + 0.22 * aim[1] / n), 0.13]], "sides": 10, "color": BRASS})
    # The folding table: a top on four thin legs.
    ex.append(box("table top", [-1.9, 0.72, -1.1], [-1.2, 0.76, 1.1], CREAM))
    for x in (-1.85, -1.27):
        for z in (-1.05, 1.03):
            ex.append(box("table leg %.2f %.2f" % (x, z), [x, 0, z], [x + 0.03, 0.72, z + 0.03], DEEP_BLUE))
    ex.append(box("cue cards on the table", [-1.75, 0.76, -0.55], [-1.5, 0.79, -0.2], WHITE))
    ex.append({"name": "mug on the table", "loft": "y", "sides": 10, "rings": [[0.76, -1.55, 0.45, 0.045], [0.86, -1.55, 0.45, 0.048]], "color": WHITE})
    # The box camera: three broom-handle legs, a wooden box, a brass lens toward the X.
    for k in range(3):
        a = math.radians(30 + 120 * k)
        ex.append({"name": "tripod leg %d" % (k + 1), "tube": [[r(-1.2 + 0.25 * math.cos(a)), 0.0, r(-1.65 + 0.25 * math.sin(a)), 0.018], [-1.2, 1.12, -1.65, 0.018]], "sides": 5, "color": WOOD})
    ex.append(box("box camera body", [-1.36, 1.12, -1.8], [-1.06, 1.38, -1.5], DARK_WOOD))
    ex.append({"name": "box camera lens", "tube": [[-1.06, 1.25, -1.65, 0.06], [-0.96, 1.25, -1.65, 0.05]], "sides": 10, "color": BRASS})
    # A corkboard and two framed portraits on the door-side wall, a shelf with a kettle at the panel end.
    ex.append(box("corkboard", [-2.6, 1.2, Z - 0.03], [-1.2, 2.1, Z], [0.72, 0.56, 0.38]))
    for i, x in enumerate((-2.45, -2.15, -1.85, -1.55)):
        ex.append(box("print %d" % (i + 1), [x, 1.5 + 0.12 * (i % 2), Z - 0.04], [x + 0.18, 1.72 + 0.12 * (i % 2), Z - 0.03], WHITE))
    for i, x in enumerate((-0.6, -0.05)):
        ex.append(box("portrait frame %d" % (i + 1), [x, 1.35, Z - 0.04], [x + 0.4, 1.9, Z], BLUE))
        ex.append(box("portrait %d" % (i + 1), [x + 0.05, 1.4, Z - 0.05], [x + 0.35, 1.85, Z - 0.04], CREAM))
    ex.append(box("shelf", [-X, 1.55, -2.3], [-X + 0.25, 1.59, -1.3], DARK_WOOD))
    ex.append({"name": "kettle", "loft": "y", "sides": 10, "rings": [[1.59, -X + 0.12, -1.55, 0.08], [1.7, -X + 0.12, -1.55, 0.09], [1.78, -X + 0.12, -1.55, 0.04]], "color": BLUE})
    ex.append({"name": "rope coil", "loft": "y", "sides": 12, "rings": [[0.0, 2.7, -2.25, 0.2], [0.12, 2.7, -2.25, 0.2]], "color": [0.78, 0.68, 0.5]})
    return ex


def set_card():
    door0, door1, door_top = DOOR
    win0, win1, sill, head = WINDOW
    p0, p1, deep = PORCH
    door_x = (door0 + door1) / 2.0
    return {
        "format": "forge-set/1",
        "name": "casting-office",
        "title": "The casting office",
        "about": "The ninja's back room, a short walk from his photo stage: a backdrop and two lamps at the far end with a taped X on open floor, a table and three chairs for whoever is watching, and his box camera on a tripod. One window, one door, a porch that faces the stage. A world grown by Marble will fill the inside later.",
        "stage": "open",
        "frame": {"origin": [0.0, 0.0, 0.0], "front_deg": 0.0,
                  "about": "the origin is the middle of the floor inside, at floor level. The room runs along x: the backdrop end is +x, the panel's end -x. The front (+z) is the door's wall"},
        "footprint": {"outline": [[-XO - 0.4, -ZO - 0.4], [XO + 0.4, -ZO - 0.4], [XO + 0.4, r(ZO + deep + 0.2)], [-XO - 0.4, r(ZO + deep + 0.2)]],
                      "about": "the building and its roof's overhang, and the porch out front"},
        "units": "metres. y is up and 0 is the floor inside. The room is %g m long (x), %g m across (z) and %g m to the ceiling." % (LONG, ACROSS, TALL),
        "floor": {"areas": [[[-X, -Z], [X, Z]], [[door0, Z], [door1, ZO]], [[p0, ZO], [p1, r(ZO + deep)]]],
                  "note": "the room inside the walls, the doorway, and the porch"},
        "ground": {"y": 0.0, "color": [0.87, 0.83, 0.76], "size_m": 30.0},
        "room": {
            "about": "the room inside the walls: what a Marble world of it fills. Measured from the set's origin, which is the middle of this floor",
            "inside": {"min": [-X, 0.0, -Z], "max": [X, TALL, Z]},
            "long_m": LONG, "across_m": ACROSS, "tall_m": TALL, "walls_m": WALL,
            "floor_origin": [0.0, 0.0, 0.0],
            "backdrop_end": "+x", "panel_end": "-x",
            "door": {"wall": "+z", "x": [door0, door1], "tall_m": door_top},
            "window": {"wall": "-z", "x": [win0, win1], "y": [sill, head]},
        },
        "marble_seat": {
            "about": "How a Marble world of this room goes into the shell (just marble-seat <world folder>, scripts/sets/from_marble.py --seat). Marble's own origin is the picture's eye, looking along its +z. "
                     "Turn: the eye looks toward looks_toward_deg (the backdrop end), then the nearest quarter turn that squares its walls with x and z. "
                     "Size: Marble's metres, then scaled so the floor it measures is the size of `room.inside` (the mean of the two ways; the report says how far each was off). "
                     "Move: the middle of that floor onto this set's origin. Then the eye should land on the camera `eye`, within eye_within_m; the report says where it landed. "
                     "The shell's own set.glb is kept; the Marble mesh is written beside it as marble.glb",
            "eye": "panel_eye",
            "looks_toward_deg": 90.0,
            "scale_to_inside": True,
            "eye_within_m": 0.6,
            "mesh": "marble.glb",
        },
        "blocks": blocks(),
        "marks": {
            "audition": {"kind": "stand", "at": [1.2, 0.0], "facing_deg": -90.0, "about": "the taped X: where whoever is auditioning stands, facing the table, the backdrop behind them"},
            "lineup_left": {"kind": "stand", "at": [1.2, -0.8], "facing_deg": -90.0, "about": "a chemistry read: beside the X, on the window side (the panel's left)"},
            "lineup_right": {"kind": "stand", "at": [1.2, 0.8], "facing_deg": -90.0, "about": "a chemistry read: beside the X, on the door side (the panel's right)"},
            "panel_1": {"kind": "sit", "at": [-2.6, -0.8], "stand_at": [-2.15, -0.8], "facing_deg": 90.0, "seat_height_m": 0.46, "seat": "panel seat 1", "beside": ["panel back 1"],
                        "about": "the panel's seat on the window side"},
            "panel_2": {"kind": "sit", "at": [-2.6, 0.0], "stand_at": [-2.15, 0.0], "facing_deg": 90.0, "seat_height_m": 0.46, "seat": "panel seat 2", "beside": ["panel back 2"],
                        "about": "the middle seat at the table: the eye the concept pictures were drawn from (camera panel_eye)"},
            "panel_3": {"kind": "sit", "at": [-2.6, 0.8], "stand_at": [-2.15, 0.8], "facing_deg": 90.0, "seat_height_m": 0.46, "seat": "panel seat 3", "beside": ["panel back 3"],
                        "about": "the panel's seat on the door side"},
            "box_camera": {"kind": "stand", "at": [-1.75, -1.65], "facing_deg": 90.0, "about": "behind the box camera on its tripod: where the ninja stands to take a test picture of whoever is on the X"},
            "door": {"kind": "door", "at": [door_x, 1.9], "facing_deg": 180.0, "leads_to": {"set": "studio", "mark": "office_door"},
                     "about": "just inside the door, facing into the room: the way in from the photo stage"},
            "porch": {"kind": "stand", "at": [door_x, r(ZO + 0.6)], "facing_deg": 0.0, "about": "on the porch outside the door, looking out toward the stage"},
        },
        "paths": [
            {"from": "porch", "to": "door"},
            {"from": "door", "to": "audition"},
            {"from": "door", "to": "lineup_right"},
            {"from": "door", "to": "lineup_left"},
            {"from": "door", "to": "panel_3", "via": [[-0.6, 1.6], [-2.15, 1.55]]},
            {"from": "panel_3", "to": "panel_2"},
            {"from": "panel_2", "to": "panel_1"},
            {"from": "door", "to": "box_camera", "via": [[0.2, -0.9], [-0.7, -2.05], [-1.75, -2.1]]},
            {"from": "audition", "to": "lineup_left"},
            {"from": "audition", "to": "lineup_right"},
        ],
        "cameras": {
            "panel_eye": {"at": [-2.45, 1.2, 0.0], "aim": [3.0, 1.0, 0.0], "lens_mm": 20, "sees": ["audition", "lineup_left", "lineup_right"],
                          "about": "seated at the middle of the table, 1.2 m up, looking at the X and the backdrop: the eye the concept pictures were drawn from, and where a Marble world's own eye is lined up"},
            "lens": {"at": [-0.9, 1.25, -1.65], "aim": [1.2, 0.8, 0.0], "lens_mm": 24, "sees": ["audition", "lineup_left", "lineup_right"],
                     "about": "through the box camera's lens: what the ninja's test picture sees"},
            "back": {"at": [2.6, 2.2, -1.2], "aim": [-2.6, 0.7, 0.3], "lens_mm": 18, "sees": ["panel_1", "panel_2", "panel_3"],
                     "about": "from up by the backdrop, looking back at the table: who is watching"},
        },
        "lights": [
            {"name": "afternoon sun", "kind": "sun", "at": [-8.0, 14.0, 10.0], "aim": [0.0, 0.0, 0.0], "power": 2.4, "color": [1.0, 0.96, 0.88]},
            {"name": "ceiling lamp", "kind": "area", "at": [0.0, 2.9, 0.0], "aim": [0.0, 0.0, 0.0], "power": 70.0, "color": [1.0, 0.95, 0.88], "size_m": 2.0},
            {"name": "daylight from the window", "kind": "area", "at": [0.6, 1.7, -2.3], "aim": [0.2, 0.6, 0.8], "power": 45.0, "color": [0.9, 0.94, 1.0], "size_m": 1.2},
            {"name": "lamps on the backdrop", "kind": "area", "at": [1.6, 1.8, 0.0], "aim": [2.9, 1.3, 0.0], "power": 12.0, "color": [1.0, 0.9, 0.75], "size_m": 1.5},
            {"name": "on the X", "kind": "area", "at": [-0.4, 2.7, 0.0], "aim": [1.2, 1.0, 0.0], "power": 35.0, "color": [1.0, 0.96, 0.9], "size_m": 1.5},
        ],
        "world": {"color": [0.98, 0.973, 0.961], "strength": 0.2},
        "slots": {},
        "dressing": [],
        "groups": {
            "about": "Marks used together. An audition stands one person on the X; a chemistry read stands two or three along the row, the X in the middle. The panel sits along the table; the ninja is at his box camera",
            "lineup": ["audition", "lineup_left", "lineup_right"],
            "panel": ["panel_1", "panel_2", "panel_3"],
            "photographer": ["box_camera"],
        },
        "geometry": {"glb": "set.glb", "move": [0.0, 0.0, 0.0], "turn_deg": 0.0,
                     "built_by": "just set-build casting-office (scripts/sets/build_set.py, from the blocks here and the extra pieces in build.json; both written by scripts/sets/casting_office.py)"},
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    recipe = {"about": "What the casting office is built from, besides its blocks (each block that is built is a box in its own color): the floor, ceiling and roof, the door's head and the window's frame, "
                       "the porch, the lamps, the table and the box camera as they look (their blocks are only what is in the way), and the small things on the walls. Written by scripts/sets/casting_office.py.",
              "extras": extras()}
    path = os.path.join(OUT, "set.json")
    old = {}
    if os.path.exists(path):
        with open(path) as f:
            old = json.load(f)
    card = set_card()
    if old.get("marble"):  # a Marble world already seated in it stays seated
        card["marble"] = old["marble"]
    for name, data in (("set.json", card), ("build.json", recipe)):
        with open(os.path.join(OUT, name), "w") as f:
            json.dump(data, f, indent=1)
            f.write("\n")
    print("CASTING wrote sets/casting-office/set.json (%d blocks, %d marks, %d cameras) and build.json (%d extras)" % (len(card["blocks"]), len(card["marks"]), len(card["cameras"]), len(recipe["extras"])))


if __name__ == "__main__":
    main()
