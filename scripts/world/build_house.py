"""Builds a house from its design: the plan Opus drew becomes a standing set.

    python3 scripts/world/build_house.py <house> [--runs DIR] [--plan-only]

Reads sets/<house>/design.json (a HouseDesign: baml_src/11_world/house_prompt.baml)
and writes, in the same folder:

    set.json      the set: frame, footprint, floor, blocks, marks, cameras, lights
    build.json    the pieces that are only looked at, and what dressing to copy from a run
    sign.png      the house's own sign, lettered in its colours
    set.glb       built in a background Blender (scripts/sets/build_set.py)
    card.png      one picture of it through its front camera

How a plan becomes a place. The house is built like a film set: a back wall
and side walls, a tiled cap along their tops instead of a roof, and the front
left open so you can see in. Each area of the plan gets its floor in its own
colour and what belongs to its kind (a stage is a low platform with the
microphone on it; a bedroom has a bed; a patio has a table). Each feature
adds its pieces to the area it names. Every area gets a mark to stand on.
Paths and what each camera holds are tried against the set's own checks, and
only the ones that pass are kept: so any design that passes house_problems
builds into a sound set.

`--plan-only` stops after the first three files (no Blender): what the tests use.
Plain Python; Blender is only run as a separate, background program.
"""

import json
import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
import pieces as kit  # noqa: E402  (not `kit`: the comics have a kit.py of their own)
import signs  # noqa: E402
import standing  # noqa: E402
from pieces import block, box  # noqa: E402

BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
WALL_TALL, WALL_THICK = 3.2, 0.25
STAGE_TALL = 0.25
YARD = 3.6  # metres of paved yard out front, where the cameras stand
OPEN_AIR = ("Patio", "Garden", "Porch")
FACES = {"the grass": -90.0, "the spawn spot": 180.0, "the morning sun": 90.0, "the open ground": 0.0}  # the world's headings: 0 is south
MARK_NAMES = {"Stage": "stage", "PracticeFloor": "practice", "SittingRoom": "sitting_room", "Bedroom": "bedroom", "Kitchen": "kitchen",
              "DressingRoom": "dressing_room", "Patio": "patio", "Garden": "garden", "Porch": "porch"}


def rgb(colour):
    text = colour["hex"].lstrip("#")
    return [round(int(text[i:i + 2], 16) / 255.0, 3) for i in (0, 2, 4)]


def shade(color, by):
    return [round(max(0.0, min(1.0, c * by)), 3) for c in color]


def slug(name):
    return "_".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split())


class Plan:
    """A design, with its areas moved into the set's frame: the origin is the middle of the house, the front is +z."""

    def __init__(self, design):
        self.design = design
        self.wide, self.deep = float(design["wide_m"]), float(design["deep_m"])
        self.x0, self.z0 = -self.wide / 2.0, -self.deep / 2.0
        self.walls, self.roof, self.trim = rgb(design["walls"]), rgb(design["roof"]), rgb(design["trim"])
        self.areas = []
        for area in design["areas"]:
            lo = [self.x0 + area["x_m"], self.z0 + area["z_m"]]
            hi = [lo[0] + area["wide_m"], lo[1] + area["deep_m"]]
            self.areas.append(dict(area, lo=lo, hi=hi, mid=[(lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0]))
        # the walls run as far forward as the rooms do; open-air areas in front of that get a low wall
        indoor = [a for a in self.areas if a["kind"] not in OPEN_AIR]
        self.walled_to = max([a["hi"][1] for a in indoor] or [self.z0 + self.deep * 0.5])

    def area(self, name):
        return next(a for a in self.areas if a["name"] == name)


def furnish(area, plan, blocks, extras, marks, slots):
    """What belongs to an area because of its kind. Its mark is added by the caller."""
    kind, name = area["kind"], area["name"]
    (x0, z0), (x1, z1), (mx, mz) = area["lo"], area["hi"], area["mid"]
    floor = rgb(area["floor"])
    top = STAGE_TALL if kind == "Stage" else 0.03
    extras.append(box("%s floor" % name, [x0 + 0.02, 0.0, z0 + 0.02], [x1 - 0.02, top, z1 - 0.02], floor))
    if kind == "Stage":
        extras.append(box("%s edge" % name, [x0, 0.0, z1 - 0.06], [x1, STAGE_TALL + 0.03, z1], plan.trim))
        slots["microphone"] = {"at": [kit.r(mx + 0.55), STAGE_TALL, kit.r(mz + 0.2)], "heading": 0.0, "about": "on the stage, a step to one side of where she stands"}
    elif kind == "Bedroom":
        bx = x0 + 0.3
        blocks.append(block("bed", "bed", [bx, 0.0, z0 + 0.3], [bx + 1.4, 0.5, z0 + 2.3 if z1 - z0 >= 2.7 else z1 - 0.3], kit.CREAM))
        extras.append(box("pillow", [bx + 0.2, 0.5, z0 + 0.4], [bx + 1.2, 0.62, z0 + 0.8], shade(plan.roof, 1.1)))
        extras.append(box("blanket", [bx - 0.02, 0.3, z0 + 1.1], [bx + 1.42, 0.53, min(z0 + 2.32, z1 - 0.28)], plan.trim))
    elif kind == "DressingRoom":
        blocks.append(block("wardrobe", "wardrobe", [x0 + 0.3, 0.0, z0 + 0.3], [x0 + 1.5, 2.0, z0 + 0.85], plan.trim))
        rail_x = [min(x0 + 1.9, x1 - 0.9), x1 - 0.3]
        extras.append({"name": "costume rail", "sides": 5, "color": shade(plan.trim, 0.8),
                       "tube": [[rail_x[0], 0.0, z0 + 0.5, 0.025], [rail_x[0], 1.7, z0 + 0.5, 0.025], [rail_x[1], 1.7, z0 + 0.5, 0.025], [rail_x[1], 0.0, z0 + 0.5, 0.025]]})
        gowns = [plan.roof, [0.12, 0.11, 0.11], kit.CREAM, shade(plan.roof, 0.75)]
        count = max(1, int((rail_x[1] - rail_x[0]) / 0.3))
        for i in range(count):
            gx = rail_x[0] + 0.15 + i * (rail_x[1] - rail_x[0] - 0.3) / max(1, count - 1) if count > 1 else (rail_x[0] + rail_x[1]) / 2.0
            extras.append(box("gown %d" % (i + 1), [gx - 0.1, 0.45, z0 + 0.36], [gx + 0.1, 1.66, z0 + 0.64], gowns[i % len(gowns)]))
    elif kind == "Kitchen":
        blocks.append(block("kitchen counter", "counter", [x0 + 0.3, 0.0, z0 + 0.3], [min(x0 + 2.2, x1 - 0.3), 0.9, z0 + 0.9], plan.trim))
        extras.append(box("kitchen top", [x0 + 0.27, 0.9, z0 + 0.27], [min(x0 + 2.23, x1 - 0.27), 0.95, z0 + 0.93], kit.CREAM))
        extras.append({"name": "kitchen pots", "seed": 4, "jitter": 0.05, "color": [0.72, 0.45, 0.22], "lumps": [[x0 + 0.7, 1.05, z0 + 0.6, 0.12], [x0 + 1.2, 1.03, z0 + 0.6, 0.09]]})
    elif kind == "SittingRoom":
        cx = x0 + 0.45
        blocks.append(block("armchair seat", "seat", [cx, 0.0, z0 + 0.5], [cx + 0.6, 0.46, z0 + 0.92], plan.roof))
        blocks.append(block("armchair back", "seat", [cx, 0.0, z0 + 0.38], [cx + 0.6, 1.0, z0 + 0.5], plan.roof))
        extras.append(box("armchair seat front", [cx, 0.0, z0 + 0.92], [cx + 0.6, 0.46, z0 + 1.05], plan.roof))
        marks["seat"] = {"kind": "sit", "at": [kit.r(cx + 0.3), kit.r(z0 + 0.76)], "stand_at": [kit.r(cx + 0.3), kit.r(z0 + 1.24)], "facing_deg": 0.0, "seat_height_m": 0.46,
                         "seat": "armchair seat", "beside": ["armchair back"], "about": "the armchair in %s" % name}
        blocks.append(block("side table", "table", [cx + 0.85, 0.0, z0 + 0.45], [cx + 1.3, 0.55, z0 + 0.9], plan.trim))
    elif kind == "Patio":
        tx, tz = x1 - 0.9, z0 + 0.9
        blocks.append(block("patio table", "table", [tx - 0.45, 0.0, tz - 0.45], [tx + 0.45, 0.72, tz + 0.45], plan.trim))
        extras.append(kit.disc("patio table top", tx, 0.72, tz, 0.6, 0.04, kit.CREAM))
    elif kind == "Garden":
        extras.append({"name": "%s bushes" % name, "seed": 9, "jitter": 0.2, "color": kit.LEAF,
                       "lumps": [[x0 + 0.6, 0.4, z0 + 0.6, 0.5], [x1 - 0.6, 0.45, z0 + 0.6, 0.55], [x1 - 0.55, 0.35, z1 - 0.6, 0.42]]})
        extras.append({"name": "%s blooms" % name, "seed": 2, "jitter": 0.1, "color": plan.roof,
                       "lumps": [[x0 + 0.5, 0.85, z0 + 0.7, 0.12], [x0 + 0.85, 0.75, z0 + 0.5, 0.1], [x1 - 0.7, 0.95, z0 + 0.55, 0.12], [x1 - 0.5, 0.72, z1 - 0.7, 0.1]]})
    elif kind == "Porch":
        for i, px in enumerate((x0 + 0.12, x1 - 0.12)):
            blocks.append(block("%s post %d" % (name, i + 1), "post", [px - 0.08, 0.0, z1 - 0.2], [px + 0.08, 2.6, z1 - 0.04], plan.trim))
        extras.append(box("%s beam" % name, [x0, 2.6, z1 - 0.22], [x1, 2.8, z1 - 0.02], plan.trim))


def feature(item, area, plan, blocks, extras, n):
    """One of the touches that make the house hers, built into the area it names."""
    kind, tag = item["kind"], "%s %d" % (item["kind"].replace("_", " "), n)
    (x0, z0), (x1, z1), (mx, mz) = area["lo"], area["hi"], area["mid"]
    at_back = z0 - plan.z0 < 0.3
    if kind == "arches":
        count = max(2, int(round((x1 - x0) / 2.2)) + 1)
        xs = [x0 + 0.1 + i * (x1 - x0 - 0.2) / (count - 1) for i in range(count)]
        for i, px in enumerate(xs):
            blocks.append(block("%s post %d" % (tag, i + 1), "post", [px - 0.09, 0.0, z1 - 0.2], [px + 0.09, 2.5, z1 - 0.02], plan.walls))
        extras.append(box("%s beam" % tag, [x0, 2.75, z1 - 0.22], [x1, 3.0, z1], plan.walls))
        for i, (a, b) in enumerate(zip(xs, xs[1:])):  # the corners of each opening filled in, so it reads as an arch
            extras.append(box("%s arch %d left" % (tag, i + 1), [a + 0.09, 2.5, z1 - 0.2], [a + 0.34, 2.75, z1 - 0.02], plan.walls))
            extras.append(box("%s arch %d right" % (tag, i + 1), [b - 0.34, 2.5, z1 - 0.2], [b - 0.09, 2.75, z1 - 0.02], plan.walls))
    elif kind == "flower_pots":
        for i, (px, pz) in enumerate([(x0 + 0.3, z1 - 0.3), (x1 - 0.3, z1 - 0.3), (x0 + 0.3, z0 + 0.3)]):
            extras.extend(kit.flower_pot("%s %d" % (tag, i + 1), px, pz, bloom=plan.trim if i != 1 else [0.93, 0.6, 0.66], seed=i + 1))
    elif kind == "lanterns":
        extras.append(box("%s rail" % tag, [x0, 3.0, mz - 0.03], [x1, 3.06, mz + 0.03], plan.trim))
        for i in range(3):
            extras.extend(kit.lantern("%s %d" % (tag, i + 1), x0 + (i + 1) * (x1 - x0) / 4.0, 2.55, mz, cord=0.45))
    elif kind == "string_lights":
        posts = [(x0 + 0.12, z1 - 0.12), (x1 - 0.12, z1 - 0.12)] if at_back else [(x0 + 0.12, z0 + 0.12), (x1 - 0.12, z0 + 0.12), (x1 - 0.12, z1 - 0.12), (x0 + 0.12, z1 - 0.12)]
        b, e = kit.string_lights(tag, posts, tall=2.8, sag=0.3, every=0.6)
        blocks.extend(b)
        extras.extend(e)
    elif kind == "mirror_wall":
        glass = [0.72, 0.82, 0.88]
        if at_back:
            extras.append(box("%s glass" % tag, [x0 + 0.3, 0.3, z0 + 0.02], [x1 - 0.3, 2.4, z0 + 0.06], glass))
            extras.append({"name": "%s barre" % tag, "sides": 5, "tube": [[x0 + 0.3, 1.0, z0 + 0.22, 0.025], [x1 - 0.3, 1.0, z0 + 0.22, 0.025]], "color": plan.trim})
        else:
            blocks.append(block("%s frame" % tag, "wall", [x0, 0.0, z0 + 0.3], [x0 + 0.1, 2.4, z1 - 0.3], plan.trim))
            extras.append(box("%s glass" % tag, [x0 + 0.1, 0.3, z0 + 0.4], [x0 + 0.13, 2.3, z1 - 0.4], glass))
    elif kind == "awning":
        for i, px in enumerate((x0 + 0.12, x1 - 0.12)):
            blocks.append(block("%s post %d" % (tag, i + 1), "post", [px - 0.06, 0.0, z1 - 0.18], [px + 0.06, 2.6, z1 - 0.06], plan.trim))
        stripes = max(2, int((x1 - x0) / 0.6))
        for i in range(stripes):
            sx = x0 + i * (x1 - x0) / stripes
            extras.append(box("%s stripe %d" % (tag, i + 1), [sx, 2.6, max(z0, z1 - 2.2)], [sx + (x1 - x0) / stripes, 2.68, z1 + 0.1], plan.roof if i % 2 == 0 else kit.CREAM))
    elif kind == "fountain":
        fx, fz = x0 + 0.9, z0 + 0.9
        blocks.append(block("%s basin" % tag, "fountain", [fx - 0.6, 0.0, fz - 0.6], [fx + 0.6, 0.45, fz + 0.6], kit.STONE))
        extras.append(kit.disc("%s water" % tag, fx, 0.45, fz, 0.5, 0.02, [0.5, 0.7, 0.82]))
        extras.append({"name": "%s spout" % tag, "sides": 6, "tube": [[fx, 0.45, fz, 0.07], [fx, 0.95, fz, 0.05]], "color": kit.STONE})
    elif kind == "shutters" and at_back:
        extras.append(box("%s window" % tag, [mx - 0.45, 1.2, z0 + 0.01], [mx + 0.45, 2.3, z0 + 0.04], [0.5, 0.63, 0.78]))
        for side in (-1, 1):
            extras.append(box("%s shutter %s" % (tag, "left" if side < 0 else "right"), [mx + side * 0.47 - 0.2 * (side < 0), 1.2, z0 + 0.01], [mx + side * 0.47 + 0.2 * (side > 0), 2.3, z0 + 0.06], plan.trim))


def sound_without_geometry(card, folder):
    """A set's problems, leaving aside that its .glb has not been built yet."""
    card = dict(card, dir=folder)
    return [p for p in standing.check(card)[0] if "geometry" not in p and "dressing" not in p and "picture is missing" not in p]


def plan_set(name, design, folder):
    """(set.json, build.json) for a design."""
    plan = Plan(design)
    W, D, x0, z0 = plan.wide, plan.deep, plan.x0, plan.z0
    front = z0 + D
    blocks = [
        block("back wall", "wall", [x0 - WALL_THICK, 0.0, z0 - WALL_THICK], [x0 + W + WALL_THICK, WALL_TALL, z0], plan.walls),
        block("left wall", "wall", [x0 - WALL_THICK, 0.0, z0], [x0, WALL_TALL, plan.walled_to], plan.walls),
        block("right wall", "wall", [x0 + W, 0.0, z0], [x0 + W + WALL_THICK, WALL_TALL, plan.walled_to], plan.walls),
    ]
    if front - plan.walled_to > 0.5:  # a low wall round whatever is open to the sky out front
        blocks.append(block("low wall left", "wall", [x0 - WALL_THICK, 0.0, plan.walled_to], [x0, 0.6, front], plan.walls))
        blocks.append(block("low wall right", "wall", [x0 + W, 0.0, plan.walled_to], [x0 + W + WALL_THICK, 0.6, front], plan.walls))
    paving = shade(plan.walls, 0.92)
    extras = [
        kit.slab("yard", [x0 - 1.0, z0 - 1.0], [x0 + W + 1.0, front + YARD], paving, lip=0.3),
        box("house floor", [x0, 0.0, z0], [x0 + W, 0.02, front], shade(plan.walls, 0.8)),
        # a cap of roof tiles along the tops of the walls: the roof itself is left off, so you can see in
        box("roof cap back", [x0 - WALL_THICK - 0.25, WALL_TALL, z0 - WALL_THICK - 0.25], [x0 + W + WALL_THICK + 0.25, WALL_TALL + 0.22, z0 + 0.7], plan.roof),
        box("roof cap back ridge", [x0 - WALL_THICK - 0.1, WALL_TALL + 0.22, z0 - WALL_THICK], [x0 + W + WALL_THICK + 0.1, WALL_TALL + 0.42, z0 + 0.35], shade(plan.roof, 0.88)),
        box("roof cap left", [x0 - WALL_THICK - 0.2, WALL_TALL, z0 + 0.7], [x0 + 0.2, WALL_TALL + 0.2, plan.walled_to], plan.roof),
        box("roof cap right", [x0 + W - 0.2, WALL_TALL, z0 + 0.7], [x0 + W + WALL_THICK + 0.2, WALL_TALL + 0.2, plan.walled_to], plan.roof),
        box("sign post", [x0 - 0.6, 0.0, front + 1.16], [x0 - 0.52, 1.5, front + 1.24], plan.trim),
    ]
    marks, slots = {}, {}
    for area in plan.areas:
        furnish(area, plan, blocks, extras, marks, slots)
    for n, item in enumerate(design["features"]):
        feature(item, plan.area(item["area"]), plan, blocks, extras, n + 1)

    # a mark in every area: the stage's is on the platform, a step back from its middle. A few spots are offered
    # for each (the middle first), and the first one the set's own checks accept is kept further down.
    offered = {}
    for area in plan.areas:
        mark_name = MARK_NAMES[area["kind"]]
        while mark_name in offered or mark_name in marks:
            mark_name += "_2"
        (ax0, az0), (ax1, az1), (mx, mz) = area["lo"], area["hi"], area["mid"]
        spots = [[mx, mz - 0.15]] if area["kind"] == "Stage" else [[mx, mz], [mx, az1 - 0.7], [ax1 - 0.7, az1 - 0.7], [ax0 + 0.7, az1 - 0.7], [ax1 - 0.7, mz]]
        offered[mark_name] = []
        for x, z in spots:
            m = {"kind": "stand", "at": [kit.r(x), kit.r(z)], "facing_deg": 0.0, "about": "%s: %s" % (area["name"], area["about"])}
            if area["kind"] == "Stage":
                m["floor_y"] = STAGE_TALL
            offered[mark_name].append(m)
    offered.update({k: [v] for k, v in marks.items()})
    offered["gate"] = [{"kind": "stand", "at": [0.0, kit.r(front + 1.6)], "facing_deg": 180.0, "about": "out front, looking in"}]

    card = kit.set_card(
        name, design["name"], "%s %s" % (design["style"].rstrip(".") + ".", design["why"]),
        kit.rect(kit.r(x0 - 1.2), kit.r(z0 - 1.2), kit.r(x0 + W + 1.2), kit.r(front + YARD + 0.2)),
        [[[kit.r(x0 + 0.05), kit.r(z0 + 0.05)], [kit.r(x0 + W - 0.05), kit.r(front)]], [[kit.r(x0 - 0.9), kit.r(front)], [kit.r(x0 + W + 0.9), kit.r(front + YARD)]]],
        blocks, {}, [], {}, "baml run buy_house (the design), then python3 scripts/world/build_house.py %s" % name,
        ground_color=kit.GREYBOX, frame_about="the origin is the middle of the house; the front is its open side",
        extra={
            "faces": {"toward": design["faces"], "facing_deg": FACES[design["faces"]], "why": design["faces_why"]},
            "design": "design.json",
            "signs": [{"name": "house sign", "image": "sign.png", "center": [kit.r(x0 - 0.56), 1.72, kit.r(front + 1.25)], "width_m": 1.3, "height_m": 0.44, "heading": 0.0, "glow": 0.8,
                       "about": "her sign: %s" % design["sign"]}],
            "slots": slots,
            "dressing": [{"prop": "microphone", "slot": "microphone", "glb": "dressing/microphone.glb", "from_run": "2026-11-21T00-12-05-vintage-stage-microphone",
                          "about": "her microphone: the first thing we ever heard from this cast came through it"}] if "microphone" in slots else [],
        })
    # Marks first: a spot the set's own checks refuse is passed over (its area is still there to walk into).
    for mark_name, spots in offered.items():
        for m in spots:
            if not sound_without_geometry(dict(card, marks={mark_name: m}), folder):
                card["marks"][mark_name] = m
                break
    for needed in ("stage", "practice", "gate"):
        if needed not in card["marks"]:
            raise SystemExit("HOUSE PROBLEM the %s has no room for someone to stand: %s" % (needed, "; ".join(sound_without_geometry(dict(card, marks={needed: offered[needed][0]}), folder))))
    for target in card["marks"]:
        if target == "gate":
            continue
        end = standing.stand_spot(card["marks"][target])
        for via in ([], [[end[0], kit.r(front - 0.4)]], [[0.0, kit.r(front - 0.4)], [end[0], kit.r(front - 0.4)]]):
            path = {"from": "gate", "to": target, **({"via": via} if via else {})}
            if not sound_without_geometry(dict(card, paths=[path]), folder):
                card["paths"].append(path)
                break
    stage = card["marks"]["stage"]["at"]

    def holds(cam_name, cam):
        return [m for m in card["marks"] if not sound_without_geometry(dict(card, cameras={cam_name: dict(cam, sees=[m])}), folder)]

    # The front camera stands in the yard wherever it holds the most marks (a post right in front of it hides half the house).
    fronts = [{"at": [kit.r(x), 2.3, kit.r(front + YARD - 0.3)], "aim": [kit.r(x * 0.4), 1.0, kit.r(z0 + D * 0.4)], "lens_mm": 20, "about": "the whole house, from the yard"}
              for x in (0.0, -W * 0.15, W * 0.15, -W * 0.3, W * 0.3)]
    crowded = lambda cam: sum(1 for b in blocks if b["kind"] == "post" and abs(b["center"][0] - cam["at"][0]) < 1.0)
    front_cam = max(fronts, key=lambda cam: (len(holds("front", cam)), -crowded(cam)))
    cameras = {
        "front": front_cam,
        "stage": {"at": [kit.r(stage[0] + 0.6), 1.5, kit.r(min(stage[1] + 5.0, front + YARD - 0.4))], "aim": [stage[0], 1.25, stage[1]], "lens_mm": 35, "about": "the stage and the microphone"},
    }
    for cam_name, cam in cameras.items():
        held = holds(cam_name, cam)
        if held:
            card["cameras"][cam_name] = dict(cam, sees=held)
    recipe = {"about": "%s, besides its blocks: floors in each area's own colour, the tiled caps on the walls, and each feature's pieces. Built from design.json; do not edit by hand." % design["name"],
              "extras": extras, "dressing": {},
              "copies": {"microphone": {"run": "vintage-stage-microphone", "file": "profiles/lowpoly.glb"}} if "microphone" in slots else {}}
    return card, recipe


def letter_sign(design, out):
    walls, trim = design["walls"]["hex"], design["trim"]["hex"]
    words = design["sign"].replace("&", "&amp;").replace("<", "&lt;")
    signs.write(out, 650, 220, "background: %s; color: %s; font: italic 600 %dpx Georgia, 'Times New Roman', serif; border: 8px solid %s;" % (walls, trim, 86 if len(words) <= 14 else 58, trim), words)


def blender(script, args):
    done = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", os.path.join(REPO, "scripts", "sets", script), "--"] + args, capture_output=True, text=True)
    lines = [l for l in done.stdout.splitlines() if l.startswith(("SETBUILD", "STILL"))]
    if done.returncode or not lines:
        raise SystemExit("HOUSE PROBLEM %s stopped: %s" % (script, (done.stdout + done.stderr)[-800:]))
    return lines


def main():
    args = sys.argv[1:]
    name = args[0]
    folder = os.path.join(REPO, "sets", name)
    with open(os.path.join(folder, "design.json")) as f:
        design = json.load(f)
    card, recipe = plan_set(name, design, folder)
    for file, value in (("set.json", card), ("build.json", recipe)):
        with open(os.path.join(folder, file), "w") as f:
            json.dump(value, f, indent=1)
            f.write("\n")
    print("HOUSE %s: %s x %s m, %d areas, %d blocks, marks: %s; cameras: %s" % (name, design["wide_m"], design["deep_m"], len(design["areas"]), len(card["blocks"]),
                                                                           ", ".join(card["marks"]), ", ".join("%s holds %s" % (c, "/".join(v["sees"])) for c, v in card["cameras"].items())))
    if "--plan-only" in args:
        return
    letter_sign(design, os.path.join(folder, "sign.png"))
    if "--runs" in args:
        import world
        runs = os.path.abspath(args[args.index("--runs") + 1])
        for prop, copy in recipe["copies"].items():
            out = os.path.join(folder, "dressing", prop + ".glb")
            if os.path.isdir(runs):
                world.copy_glb(os.path.join(world.newest_run(runs, copy["run"]), copy["file"]), out, copy.get("move"))
                world.unpack([os.path.relpath(out, REPO)])
    for line in blender("build_set.py", [name]) + blender("set_still.py", [name, "--camera", "front"]):
        print("HOUSE " + line)
    problems, _ = standing.check(standing.load(name))
    for line in problems:
        print("HOUSE PROBLEM " + line)
    print("HOUSE %s: %s" % (name, "sound" if not problems else "%d problems" % len(problems)))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
