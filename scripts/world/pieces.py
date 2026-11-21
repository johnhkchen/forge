"""Small things a place is built from, as data: a tree, a table, a stepped roof, a string of lights.

Every helper returns pieces in a set's own axes (x, y up, z toward the front),
in the two lists a set is built from (scripts/sets/build_set.py):

    blocks   boxes that are in the way: a body is kept out of them, and each
             is built as a box in its colour
    extras   pieces that are only looked at (build.py pieces: box, loft, tube, lumps)

Used by places.py (the reset's places) and build_house.py (a house from a
design). Plain Python: no Blender.
"""

import math

GRASS = [0.42, 0.6, 0.36]
GRASS_DARK = [0.34, 0.5, 0.31]
TIMBER = [0.45, 0.31, 0.2]
TIMBER_DARK = [0.3, 0.2, 0.14]
PLANK = [0.6, 0.45, 0.3]
CREAM = [0.949, 0.937, 0.914]
PLASTER = [0.88, 0.82, 0.7]
STEEL_BLUE = [0.267, 0.404, 0.608]
STONE = [0.56, 0.55, 0.52]
WARM_LIGHT = [1.0, 0.82, 0.45]
GREYBOX = [0.72, 0.71, 0.69]
RED = [0.72, 0.22, 0.2]
LEAF = [0.3, 0.5, 0.33]


def r(v):
    return round(float(v), 3)


def block(name, kind, lo, hi, color):
    """A box that is in the way, from its two corners."""
    return {"name": name, "kind": kind, "center": [r((lo[i] + hi[i]) / 2.0) for i in range(3)], "size": [r(hi[i] - lo[i]) for i in range(3)], "heading": 0.0, "color": color}


def box(name, lo, hi, color):
    """A box that is only looked at."""
    return {"name": name, "box": {"min": [r(v) for v in lo], "max": [r(v) for v in hi]}, "color": color}


def disc(name, x, y, z, radius, tall, color, sides=12):
    return {"name": name, "loft": "y", "sides": sides, "rings": [[r(y), r(x), r(z), r(radius)], [r(y + tall), r(x), r(z), r(radius)]], "color": color}


def slab(name, lo, hi, color, lip=0.25):
    """Ground with gentle edges: a flat top with a soft slope down all round (the corners rounded off)."""
    cx, cz = (lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0
    hx, hz = (hi[0] - lo[0]) / 2.0, (hi[1] - lo[1]) / 2.0
    return {"name": name, "loft": "y", "sides": 24, "square": 6,
            "rings": [[-0.3, r(cx), r(cz), r(hx), r(hz)], [-0.06, r(cx), r(cz), r(hx - lip * 0.3), r(hz - lip * 0.3)], [0.0, r(cx), r(cz), r(hx - lip), r(hz - lip)]], "color": color}


def tree(name, x, z, tall=5.0, spread=1.6, seed=1, leaf=LEAF):
    trunk = block(name + " trunk", "tree", [x - 0.2, 0.0, z - 0.2], [x + 0.2, tall * 0.45, z + 0.2], TIMBER_DARK)
    top = tall * 0.45
    leaves = {"name": name + " leaves", "seed": seed, "jitter": 0.16, "color": leaf,
              "lumps": [[r(x), r(top + spread * 0.5), r(z), r(spread)], [r(x + spread * 0.6), r(top + spread * 0.9), r(z + 0.3), r(spread * 0.75)],
                        [r(x - spread * 0.55), r(top + spread), r(z - 0.25), r(spread * 0.75)], [r(x + 0.1), r(top + spread * 1.55), r(z), r(spread * 0.7)]]}
    return [trunk], [leaves]


def rocks(name, spots, seed=2, color=STONE):
    """spots: [[x, z, radius], ...], each a rock half sunk in the ground."""
    return {"name": name, "seed": seed, "jitter": 0.22, "color": color, "lumps": [[r(x), r(rad * 0.35), r(z), r(rad), r(rad * 0.7), r(rad * 0.85)] for x, z, rad in spots]}


def stepped_roof(name, lo, hi, y, color, steps=3, rise=0.45, along="x", overhang=0.3):
    """A roof as a short stack of boxes, each narrower than the one under it: a block-out's gable.
    lo and hi are [x, z] corners of what it covers; the ridge runs along x or z."""
    out = []
    for i in range(steps):
        pull = i * ((hi[1] - lo[1]) if along == "x" else (hi[0] - lo[0]) + 2 * overhang) / (2.0 * steps)
        a = [lo[0] - overhang, y + i * rise, lo[1] - overhang]
        b = [hi[0] + overhang, y + (i + 1) * rise, hi[1] + overhang]
        if along == "x":
            a[2] += pull
            b[2] -= pull
        else:
            a[0] += pull
            b[0] -= pull
        out.append(box("%s %d" % (name, i + 1), a, b, color))
    return out


def table(name, x, z, wide=1.8, color=PLANK):
    """A garden table (in the way) with a bench either side. The benches are 0.46 m high: seats our sit pose fits."""
    return [
        block(name, "table", [x - wide / 2, 0.0, z - 0.4], [x + wide / 2, 0.74, z + 0.4], color),
        block(name + " bench front", "seat", [x - wide / 2, 0.0, z + 0.62], [x + wide / 2, 0.46, z + 0.97], color),
        block(name + " bench back", "seat", [x - wide / 2, 0.0, z - 0.97], [x + wide / 2, 0.46, z - 0.62], color),
    ]


def bench_seat(table_name, x, z, about):
    """A sit mark on a table's front bench, facing out over the garden."""
    return {"kind": "sit", "at": [r(x), r(z + 0.795)], "stand_at": [r(x), r(z + 1.25)], "facing_deg": 0.0, "seat_height_m": 0.46,
            "seat": table_name + " bench front", "beside": [], "about": about}


def string_lights(name, posts, tall=3.0, sag=0.35, every=0.9, color=WARM_LIGHT):
    """Posts with a string of warm bulbs hung between them, in the order given."""
    blocks, extras = [], []
    for i, (x, z) in enumerate(posts):
        blocks.append(block("%s post %d" % (name, i + 1), "post", [x - 0.06, 0.0, z - 0.06], [x + 0.06, tall, z + 0.06], TIMBER_DARK))
    bulbs = []
    for i, ((x0, z0), (x1, z1)) in enumerate(zip(posts, posts[1:])):
        mid = [(x0 + x1) / 2.0, tall - sag, (z0 + z1) / 2.0]
        extras.append({"name": "%s string %d" % (name, i + 1), "sides": 4, "color": TIMBER_DARK,
                       "tube": [[r(x0), r(tall - 0.05), r(z0), 0.012], [r(mid[0]), r(mid[1]), r(mid[2]), 0.012], [r(x1), r(tall - 0.05), r(z1), 0.012]]})
        count = max(2, int(math.hypot(x1 - x0, z1 - z0) / every))
        for k in range(1, count):
            t = k / float(count)
            drop = sag * 4.0 * t * (1.0 - t)
            bulbs.append([r(x0 + (x1 - x0) * t), r(tall - 0.05 - drop - 0.08), r(z0 + (z1 - z0) * t), 0.07])
    extras.append({"name": name + " bulbs", "lumps": bulbs, "seed": 5, "jitter": 0.0, "color": color})
    return blocks, extras


def bunting(name, a, b, y, colors, every=0.6):
    """Little flags hung in a row under a beam from a to b ([x, z] each), in turn from `colors`."""
    out = []
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    count = max(1, int(length / every))
    along_x = abs(b[0] - a[0]) >= abs(b[1] - a[1])
    for i in range(count):
        t = (i + 0.5) / count
        x, z = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        half = [0.17, 0.015] if along_x else [0.015, 0.17]
        out.append(box("%s flag %d" % (name, i + 1), [x - half[0], y - 0.32, z - half[1]], [x + half[0], y, z + half[1]], colors[i % len(colors)]))
    return out


def flower_pot(name, x, z, y=0.0, bloom=RED, seed=3):
    pot = {"name": name + " pot", "loft": "y", "sides": 8, "rings": [[r(y), r(x), r(z), 0.16], [r(y + 0.34), r(x), r(z), 0.22]], "color": [0.74, 0.44, 0.3]}
    flowers = {"name": name + " flowers", "seed": seed, "jitter": 0.2, "color": bloom,
               "lumps": [[r(x), r(y + 0.5), r(z), 0.2], [r(x + 0.12), r(y + 0.62), r(z + 0.05), 0.13], [r(x - 0.1), r(y + 0.6), r(z - 0.06), 0.13]]}
    return [pot, flowers]


def lantern(name, x, y, z, color=WARM_LIGHT, cord=0.5):
    return [{"name": name + " cord", "sides": 4, "tube": [[r(x), r(y + cord), r(z), 0.012], [r(x), r(y), r(z), 0.012]], "color": TIMBER_DARK},
            {"name": name, "lumps": [[r(x), r(y - 0.12), r(z), 0.16]], "seed": 1, "jitter": 0.0, "color": color}]


def set_card(name, title, about, outline, floor_areas, blocks, marks, paths, cameras, built_by, lights=None, air=None, ground_color=None, frame_about="", extra=None):
    """A set.json in the standing-set format (scripts/sets/standing.py), with nothing left out."""
    card = {
        "format": "forge-set/1", "name": name, "title": title, "about": about, "stage": "open",
        "frame": {"origin": [0.0, 0.0, 0.0], "front_deg": 0.0, "about": frame_about},
        "footprint": {"outline": outline, "about": "all of it, its cameras included"},
        "units": "metres. y is up, the ground is 0. The front is +z: a heading of 0 faces it, 90 faces +x.",
        "floor": {"areas": floor_areas},
        "ground": {"y": -0.02, "color": ground_color or GREYBOX, "size_m": 70.0},
        "blocks": blocks, "marks": marks, "paths": paths, "cameras": cameras, "lights": lights or DAYLIGHT,
        "world": air or OPEN_AIR, "backdrop": None, "signs": [], "slots": {}, "dressing": [],
        "geometry": {"glb": "set.glb", "move": [0.0, 0.0, 0.0], "turn_deg": 0.0, "built_by": built_by},
    }
    card.update(extra or {})
    return card


def rect(x0, z0, x1, z1):
    return [[x0, z0], [x1, z0], [x1, z1], [x0, z1]]


DAYLIGHT = [
    {"name": "sun", "kind": "sun", "at": [-8.0, 16.0, 10.0], "aim": [0.0, 0.0, 0.0], "power": 2.6, "color": [1.0, 0.96, 0.88]},
    {"name": "sky", "kind": "area", "at": [6.0, 12.0, 8.0], "aim": [0.0, 0.0, 0.0], "power": 900.0, "color": [0.88, 0.93, 1.0], "size_m": 12.0},
]
OPEN_AIR = {"color": [0.8, 0.86, 0.9], "strength": 0.7}
