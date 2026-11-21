"""The places the reset spawned, written out as standing sets, from data.

    python3 scripts/world/places.py            # writes sets/<place>/set.json and build.json for all four
    python3 scripts/world/places.py grass      # or only the ones named

    grass          Theodore's grass: open ground, a few trees and rocks
    boxing-house   the timber hall around the ring, the brew house, the beer garden
    settlement     the troll's den and the lizardkin's sun house, and their stall
    spawn          where new toons land: the gachapon and the BUY HOUSE pedestal

Each is an ordinary set (scripts/sets/standing.py): a frame, a footprint,
marks, cameras, blocks that are in the way, and a build.json of pieces that
are only looked at. `just set-build <place>` then builds its set.glb in a
background Blender, and `just set-check <place>` says whether it is sound.

Nothing here says where a place stands: that is world.json's job.
Plain Python: no Blender.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import pieces as kit  # noqa: E402  (not `kit`: the comics have a kit.py of their own)
from pieces import block, box, disc, rect  # noqa: E402

BUILT_BY = "python3 scripts/world/places.py, then just set-build %s"


def stand(at, facing, about):
    return {"kind": "stand", "at": at, "facing_deg": float(facing), "about": about}


def grass():
    blocks, extras = [], [kit.slab("grass", [-21.8, -12.8], [21.8, 12.8], kit.GRASS, lip=0.7)]
    extras.append(disc("boxing circle", -6.0, 0.0, 2.0, 3.2, 0.015, [0.5, 0.66, 0.42], sides=20))
    for i, (x, z, tall, spread) in enumerate([(-17.0, -8.0, 6.5, 2.1), (15.0, -9.0, 5.5, 1.7), (18.0, 6.0, 5.0, 1.6), (-14.0, 8.5, 4.5, 1.4), (6.0, -10.5, 4.2, 1.3)]):
        b, e = kit.tree("tree %d" % (i + 1), x, z, tall, spread, seed=i + 1, leaf=kit.LEAF if i % 2 == 0 else [0.36, 0.55, 0.3])
        blocks += b
        extras += e
    extras.append(kit.rocks("rocks", [[-10.0, -9.0, 0.9], [-9.0, -8.1, 0.5], [12.0, 8.0, 0.7], [19.0, -2.0, 0.6], [-19.5, 3.0, 0.5]]))
    extras.append({"name": "buttercups", "seed": 4, "jitter": 0.1, "color": [0.95, 0.82, 0.35],
                   "lumps": [[x, 0.08, z, 0.11] for x, z in [(-3, 7), (-2.4, 7.5), (4, 5), (4.6, 5.3), (9, -4), (-12, -1), (-11.4, -1.5), (14, 1), (1, -8), (1.6, -8.3)]]})
    extras.append({"name": "daisies", "seed": 6, "jitter": 0.1, "color": kit.CREAM,
                   "lumps": [[x, 0.08, z, 0.1] for x, z in [(-2.8, 7.9), (5, 4.6), (8.5, -4.6), (-12.5, -1.6), (13.4, 1.5), (0.7, -8.6), (-18, 10), (10, 10.5)]]})
    blocks.append(block("bench seat", "seat", [-16.2, 0.0, -6.2], [-14.4, 0.46, -5.85], kit.PLANK))
    blocks.append(block("bench back", "seat", [-16.2, 0.0, -6.3], [-14.4, 0.95, -6.2], kit.PLANK))
    marks = {
        "stride": stand([2.0, 1.0], 20, "the middle of the grass: room to stride, to box, to breathe"),
        "circle": stand([-6.0, 2.0], 90, "the paler ring in the grass, for boxing outdoors"),
        "oak": stand([-15.0, -3.5], 150, "in the shade of the big tree"),
        "bench": {"kind": "sit", "at": [-15.3, -6.02], "stand_at": [-15.3, -5.55], "facing_deg": 0.0, "seat_height_m": 0.46, "seat": "bench seat",
                  "beside": ["bench back"], "about": "the bench under the big tree, looking out over the grass"},
        "north_gate": stand([-4.0, -11.5], 180, "the edge nearest the boxing house and its beer garden"),
        "east_gate": stand([20.0, 4.0], 90, "the edge nearest the spawn spot"),
    }
    paths = [{"from": "stride", "to": "circle"}, {"from": "stride", "to": "north_gate"}, {"from": "stride", "to": "east_gate"}, {"from": "circle", "to": "oak"}, {"from": "oak", "to": "bench"}]
    cameras = {
        "wide": {"at": [0.0, 7.0, 12.6], "aim": [-1.0, 0.4, -1.0], "lens_mm": 20, "sees": ["stride", "circle"], "about": "the whole plot, from the south edge"},
        "oak": {"at": [-10.5, 1.7, -0.5], "aim": [-15.2, 1.0, -5.2], "lens_mm": 32, "sees": ["bench", "oak"], "about": "the bench and the big tree"},
    }
    card = kit.set_card("grass", "Theodore's grass", "A large plot of open grass that Roosevelt asked for: room to stride, to box, to breathe. A few trees, a few rocks, one bench.",
                        rect(-22.0, -13.0, 22.0, 13.0), [[[-21.0, -12.0], [21.0, 12.0]]], blocks, marks, paths, cameras, BUILT_BY % "grass",
                        ground_color=kit.GREYBOX, frame_about="the origin is the middle of the grass; the front is its south edge")
    return card, {"about": "Theodore's grass, besides its blocks: the ground, the leaves, the rocks and the flowers.", "extras": extras, "dressing": {}}


def boxing_house():
    floor = [0.5, 0.38, 0.27]
    blocks = [
        block("back wall", "wall", [-7.0, 0.0, -7.0], [7.0, 7.4, -6.7], kit.TIMBER),
        block("left wall", "wall", [-7.0, 0.0, -6.7], [-6.7, 6.0, 9.0], kit.TIMBER),
        block("right wall", "wall", [6.7, 0.0, -6.7], [7.0, 6.0, -3.0], kit.TIMBER),
        block("post right", "post", [6.7, 0.0, 0.85], [7.0, 6.0, 1.15], kit.TIMBER_DARK),
        block("post front right", "post", [6.7, 0.0, 8.7], [7.0, 6.0, 9.0], kit.TIMBER_DARK),
        block("ring", "ring", [-2.3, 0.0, -2.2], [2.3, 2.9, 3.2], [0.8, 0.76, 0.68]),
        block("bar", "counter", [-5.7, 0.0, -4.0], [-5.0, 1.1, 1.0], kit.TIMBER_DARK),
        block("ringside bench", "seat", [4.55, 0.0, -1.5], [4.9, 0.46, 1.5], kit.PLANK),
        block("ringside bench back", "seat", [4.9, 0.0, -1.5], [5.0, 0.95, 1.5], kit.PLANK),
        block("brew house", "wall", [10.0, 0.0, -7.0], [16.0, 3.2, -2.0], kit.PLASTER),
        block("barrels", "barrel", [10.3, 0.0, -1.9], [11.9, 0.9, -1.0], kit.PLANK),
        block("copper", "tank", [16.5, 0.0, -5.6], [18.7, 2.5, -3.4], [0.72, 0.45, 0.22]),
    ]
    tables = [("table 1", 12.0, 3.0), ("table 2", 17.5, 3.5), ("table 3", 14.5, 8.5)]
    for name, x, z in tables:
        blocks += kit.table(name, x, z)
    lights_blocks, lights_extras = kit.string_lights("garden lights", [(8.2, -1.6), (21.8, -1.6), (21.8, 12.0), (8.2, 12.0)], sag=0.7)
    blocks += lights_blocks
    # The ring is its own set; here it is one block (so nobody walks through it) and a piece of dressing.
    blocks[5]["build"] = False

    extras = [
        box("hall floor", [-7.3, -0.12, -7.3], [7.3, 0.0, 9.3], floor),
        kit.slab("garden lawn", [7.3, -7.5], [22.7, 12.7], kit.GRASS, lip=0.4),
        box("front beam", [-7.0, 5.8, 8.7], [7.0, 6.1, 9.0], kit.TIMBER_DARK),
        box("right beam", [6.7, 5.8, -3.0], [7.0, 6.1, 8.7], kit.TIMBER_DARK),
        box("truss 1", [-6.7, 5.8, -2.62], [6.7, 6.05, -2.38], kit.TIMBER_DARK),
        box("truss 2", [-6.7, 5.8, 3.38], [6.7, 6.05, 3.62], kit.TIMBER_DARK),
        box("bar top", [-5.76, 1.1, -4.06], [-4.92, 1.16, 1.06], [0.24, 0.16, 0.11]),
        box("bar shelf", [-6.7, 1.7, -3.6], [-6.42, 1.76, 0.6], kit.TIMBER_DARK),
        {"name": "bottles", "seed": 8, "jitter": 0.0, "color": [0.3, 0.45, 0.35], "lumps": [[-6.55, 1.9, z, 0.07, 0.14, 0.07] for z in (-3.2, -2.6, -2.1, -1.3, -0.6, 0.1)]},
        box("storeroom door", [-6.5, 0.0, -6.7], [-5.5, 2.2, -6.64], [0.17, 0.13, 0.11]),
        # the brew house: plaster with timber framing, a stepped roof, a chimney, a door
        box("brew door", [12.4, 0.0, -2.0], [13.6, 2.2, -1.94], kit.TIMBER_DARK),
        box("brew frame low", [9.97, 0.0, -2.0], [16.03, 0.2, -1.95], kit.TIMBER),
        box("brew frame top", [9.97, 3.0, -2.0], [16.03, 3.2, -1.95], kit.TIMBER),
        box("brew frame left", [9.97, 0.0, -2.0], [10.17, 3.2, -1.95], kit.TIMBER),
        box("brew frame right", [15.83, 0.0, -2.0], [16.03, 3.2, -1.95], kit.TIMBER),
        box("brew window", [14.2, 1.3, -2.0], [15.3, 2.2, -1.95], [0.5, 0.63, 0.78]),
        box("brew chimney", [14.6, 3.2, -6.2], [15.3, 5.6, -5.5], kit.STONE),
        {"name": "copper dome", "loft": "y", "sides": 12, "rings": [[2.5, 17.6, -4.5, 1.1], [2.9, 17.6, -4.5, 0.8], [3.15, 17.6, -4.5, 0.3]], "color": [0.72, 0.45, 0.22]},
        {"name": "copper pipe", "sides": 6, "tube": [[17.6, 3.1, -4.5, 0.09], [17.6, 3.6, -4.5, 0.09], [16.0, 3.6, -4.5, 0.09]], "color": [0.72, 0.45, 0.22]},
    ]
    extras += kit.stepped_roof("brew roof", [10.0, -7.0], [16.0, -2.0], 3.2, [0.56, 0.27, 0.2], steps=3, rise=0.5)
    for i, x in enumerate((10.7, 11.5)):
        extras.append({"name": "barrel %d" % (i + 1), "loft": "y", "sides": 10, "rings": [[0.0, x, -1.45, 0.3], [0.45, x, -1.45, 0.38], [0.9, x, -1.45, 0.3]], "color": [0.5, 0.34, 0.2]})
    for i, z in enumerate((-5.0, -1.5, 4.5, 7.2)):
        extras.append(box("window %d" % (i + 1), [-6.7, 2.0, z - 0.6], [-6.66, 4.3, z + 0.6], [0.5, 0.63, 0.78]))
        extras.append(box("window %d arch" % (i + 1), [-6.7, 4.3, z - 0.4], [-6.66, 4.65, z + 0.4], [0.5, 0.63, 0.78]))
    flags = [[0.72, 0.22, 0.2], kit.CREAM, kit.STEEL_BLUE]
    extras += kit.bunting("front bunting", [-6.7, 8.85], [6.7, 8.85], 5.8, flags)
    extras += kit.bunting("truss bunting 1", [-6.7, -2.5], [6.7, -2.5], 5.8, flags)
    extras += kit.bunting("truss bunting 2", [-6.7, 3.5], [6.7, 3.5], 5.8, flags)
    for i, (x, z) in enumerate([(-3.4, -2.5), (3.4, -2.5), (-3.4, 3.5), (3.4, 3.5)]):
        extras += kit.lantern("lamp %d" % (i + 1), x, 4.9, z, cord=0.9)
    for i, (name, x, z) in enumerate(tables):
        extras.append({"name": name + " mugs", "seed": i, "jitter": 0.0, "color": kit.CREAM, "lumps": [[x - 0.4, 0.82, z + 0.1, 0.07, 0.09, 0.07], [x + 0.35, 0.82, z - 0.12, 0.07, 0.09, 0.07]]})
    extras += lights_extras

    marks = {
        "door": stand([0.0, 6.6], 180, "just inside the open front of the hall, looking at the ring"),
        "ringside": stand([3.6, 1.0], -90, "standing at the ropes, on the bench side"),
        "bar": stand([-4.3, -1.5], -90, "at the bar"),
        "storeroom": stand([-6.0, -5.7], 180, "the dark storeroom door behind the bar, where the ninja develops his prints"),
        "ringside_bench": {"kind": "sit", "at": [4.72, 0.0], "stand_at": [4.25, 0.0], "facing_deg": -90.0, "seat_height_m": 0.46, "seat": "ringside bench",
                           "beside": ["ringside bench back"], "about": "a front-row seat"},
        "garden": stand([9.5, 6.5], 90, "the edge of the beer garden, between the hall and the tables"),
        "garden_table_1": kit.bench_seat("table 1", 12.0, 3.0, "the near table, facing out over the garden"),
        "garden_table_3": kit.bench_seat("table 3", 14.5, 8.5, "the table nearest the grass"),
        "brew_door": stand([13.0, -1.1], 0, "the brew house door"),
        "copper": stand([17.6, -1.5], 0, "by the big copper, where the beer is made"),
    }
    paths = [
        {"from": "door", "to": "ringside", "via": [[3.4, 5.4]]}, {"from": "door", "to": "bar", "via": [[-3.6, 4.6]]}, {"from": "bar", "to": "storeroom", "via": [[-4.3, -5.2]]},
        {"from": "ringside", "to": "ringside_bench"}, {"from": "ringside", "to": "garden", "via": [[5.8, 3.4], [7.6, 5.0]]},
        {"from": "garden", "to": "garden_table_1"}, {"from": "garden", "to": "garden_table_3"},
        {"from": "garden", "to": "brew_door", "via": [[9.6, 0.4], [12.6, -0.4]]}, {"from": "brew_door", "to": "copper"},
    ]
    cameras = {
        "hall": {"at": [1.5, 1.8, 12.6], "aim": [0.6, 1.2, 0.0], "lens_mm": 30, "sees": ["door", "ringside"], "about": "the whole hall, through its open front"},
        "ringside": {"at": [6.2, 1.3, 5.6], "aim": [3.4, 1.1, 0.4], "lens_mm": 32, "sees": ["ringside", "ringside_bench"], "about": "low, along the bench"},
        "garden": {"at": [21.5, 2.6, 12.3], "aim": [13.0, 0.7, 4.5], "lens_mm": 26, "sees": ["garden_table_1", "garden_table_3", "garden"], "about": "the beer garden, with the brew house behind"},
    }
    lights = kit.DAYLIGHT + [{"name": "ring light", "kind": "area", "at": [0.0, 5.6, 0.5], "aim": [0.0, 1.4, 0.5], "power": 500.0, "color": [1.0, 0.9, 0.72], "size_m": 4.0}]
    extra = {
        "footprint": {"outline": rect(-8.0, -8.0, 23.0, 13.0), "open_toward_deg": 0.0,
                      "about": "the hall, the brew house and the beer garden, cameras and all. The front (toward the grass) is kept open"},
        "signs": [{"name": "hall painting", "image": "../ring/backdrop.png", "center": [0.0, 3.62, -6.68], "width_m": 10.8, "height_m": 7.2, "heading": 0.0, "glow": 0.9, "detail": True,
                   "about": "the far wall of the hall and its crowd, painted by Codex: the same picture behind the ring in \"Long Reach\""}],
        "slots": {"ring": {"at": [0.0, 1.36, 0.0], "heading": 0.0, "about": "the middle of the hall: the ring's mat is 1.36 m above the floor"}},
        "dressing": [{"prop": "ring", "slot": "ring", "glb": "dressing/ring.glb", "detail": "../ring/set.glb", "set": "ring",
                      "about": "the 1890s ring, its own set (sets/ring): the light version here, the full one when you come close"}],
        "parts": {"ring": {"set": "ring", "at": [0.0, 0.0], "lift_m": 1.36, "about": "the ring set stands inside the hall, its mat 1.36 m above the hall floor"}},
    }
    card = kit.set_card("boxing-house", "The boxing house",
                        "A timber hall around the 1890s ring, with arched windows, bunting and lamps, a bar along one wall, and a brew house and a beer garden beside it on the grass. Its roof is left off, like a film set, so you can see in.",
                        rect(-8.0, -8.0, 23.0, 13.0), [[[-6.6, -6.5], [7.3, 8.9]], [[7.3, -1.95], [22.4, 12.4]]], blocks, marks, paths, cameras, BUILT_BY % "boxing-house",
                        lights=lights, frame_about="the origin is on the hall floor under the middle of the ring; the front is the open side the ring's steps face", extra=extra)
    return card, {"about": "The boxing house, besides its blocks: floors, beams, windows, bunting, lamps, the brew house's trim and the garden's lights. The ring is dressing, from the ring set.",
                  "extras": extras, "dressing": {},
                  "copies": {"ring": {"run": "1890s-wrestling-ring", "file": "profiles/lowpoly.glb", "move": [0.0, -1.36, 0.485]}}}


def settlement():
    earth = [0.55, 0.54, 0.4]
    stone, sand = [0.55, 0.55, 0.52], [0.84, 0.69, 0.46]
    blocks = [
        block("troll den", "wall", [-7.5, 0.0, -6.0], [-1.5, 4.0, -1.0], stone),
        block("sun house", "wall", [1.5, 0.0, -6.0], [6.5, 3.0, -1.5], sand),
        block("troll stool", "seat", [-1.25, 0.0, -2.7], [-0.25, 0.8, -1.7], stone),
        block("small stool", "seat", [0.35, 0.0, -2.4], [0.95, 0.46, -1.98], kit.PLANK),
        block("hearth", "hearth", [-5.1, 0.0, 2.4], [-3.9, 0.35, 3.6], kit.STONE),
        block("stall counter", "counter", [2.0, 0.0, 4.1], [5.0, 1.0, 4.9], kit.PLANK),
        block("sign post", "post", [5.96, 0.0, 5.3], [6.04, 1.3, 5.38], kit.TIMBER_DARK),
    ]
    for i, (x, z) in enumerate([(1.9, 3.1), (5.1, 3.1), (1.9, 5.1), (5.1, 5.1)]):
        blocks.append(block("awning post %d" % (i + 1), "post", [x - 0.06, 0.0, z - 0.06], [x + 0.06, 3.1, z + 0.06], kit.TIMBER_DARK))
    extras = [
        kit.slab("settlement ground", [-8.7, -6.8], [8.7, 7.7], earth, lip=0.5),
        box("troll door", [-5.6, 0.0, -1.0], [-3.4, 3.2, -0.94], [0.16, 0.14, 0.13]),
        box("troll lintel", [-5.9, 3.2, -1.0], [-3.1, 3.55, -0.9], [0.45, 0.45, 0.43]),
        kit.rocks("den boulders", [[-7.6, -0.9, 0.9], [-1.5, -0.8, 0.7], [-8.0, -3.5, 0.8], [-6.8, -0.4, 0.45]], seed=3, color=[0.5, 0.5, 0.48]),
        box("den chimney", [-6.8, 4.0, -5.2], [-5.9, 5.6, -4.3], [0.45, 0.45, 0.43]),
        box("sun door", [3.3, 0.0, -1.5], [4.7, 2.3, -1.44], [0.2, 0.4, 0.38]),
        box("sun window", [5.3, 1.2, -1.5], [6.0, 2.0, -1.44], [0.5, 0.63, 0.78]),
        box("sun roof rim", [1.3, 3.0, -6.2], [6.7, 3.2, -1.3], [0.76, 0.6, 0.4]),
        {"name": "sunning rock", "seed": 2, "jitter": 0.15, "color": [0.72, 0.62, 0.5], "lumps": [[5.2, 3.35, -4.4, 0.9, 0.3, 0.7]]},
        {"name": "pennant pole", "sides": 5, "tube": [[2.0, 3.2, -2.0, 0.04], [2.0, 5.4, -2.0, 0.03]], "color": kit.TIMBER_DARK},
        box("pennant", [2.03, 4.75, -2.01], [2.95, 5.3, -1.99], [0.3, 0.55, 0.36]),
        box("porch beam", [-1.5, 2.85, -3.5], [1.5, 3.05, -3.25], kit.TIMBER),
        box("porch table", [-0.2, 0.0, -2.75], [0.3, 0.62, -1.7], kit.PLANK),
        kit.rocks("hearth stones", [[-5.0, 2.5, 0.28], [-4.5, 2.4, 0.26], [-4.0, 2.5, 0.28], [-3.9, 3.0, 0.27], [-4.0, 3.5, 0.28], [-4.5, 3.6, 0.26], [-5.0, 3.5, 0.28], [-5.1, 3.0, 0.27]], seed=7),
        {"name": "fire", "seed": 1, "jitter": 0.25, "color": [0.95, 0.55, 0.2], "lumps": [[-4.5, 0.3, 3.0, 0.25, 0.35, 0.25]]},
        box("stall shelf", [2.0, 1.0, 4.06], [5.0, 1.04, 4.94], [0.68, 0.52, 0.36]),
        box("sign board back", [5.5, 1.25, 5.3], [6.5, 1.95, 5.33], kit.TIMBER_DARK),
    ]
    extras += kit.stepped_roof("den roof", [-7.5, -6.0], [-1.5, -1.0], 4.0, [0.38, 0.5, 0.32], steps=2, rise=0.45)
    for i in range(6):
        x0 = 1.7 + i * 0.6
        extras.append(box("awning %d" % (i + 1), [x0, 3.1, 2.85], [x0 + 0.6, 3.18, 5.35], kit.CREAM if i % 2 == 0 else kit.STEEL_BLUE))
    extras += kit.flower_pot("stall flowers", 1.5, 5.6, bloom=[0.9, 0.75, 0.3])
    marks = {
        "stall_troll": stand([2.7, 3.5], 0, "behind the stall, the troll's side: the kettle and the teapots"),
        "stall_lizardkin": stand([4.3, 3.5], 0, "behind the stall, the lizardkin's side: the bread"),
        "customer": stand([3.5, 6.2], 180, "in front of the stall, deciding"),
        "hearth_side": stand([-4.5, 4.5], 180, "by the fire they share"),
        "porch_seat": {"kind": "sit", "at": [0.65, -2.19], "stand_at": [0.65, -1.72], "facing_deg": 0.0, "seat_height_m": 0.46, "seat": "small stool", "beside": [],
                       "about": "the small stool on the porch between the two homes (the big stone one is the troll's)"},
        "troll_door": stand([-4.5, 0.2], 0, "the den's doorway, tall enough for a troll"),
        "sun_door": stand([4.0, -0.5], 0, "the lizardkin's door"),
    }
    paths = [{"from": "troll_door", "to": "hearth_side", "via": [[-3.2, 2.0], [-3.2, 4.2]]}, {"from": "troll_door", "to": "stall_troll", "via": [[1.0, 2.2]]},
             {"from": "sun_door", "to": "stall_lizardkin", "via": [[4.3, 1.5]]}, {"from": "customer", "to": "hearth_side", "via": [[0.0, 6.0]]}, {"from": "sun_door", "to": "porch_seat", "via": [[1.4, -0.9]]}]
    cameras = {
        "stall": {"at": [3.5, 1.9, 7.8], "aim": [3.5, 1.15, 3.5], "lens_mm": 28, "sees": ["stall_troll", "stall_lizardkin"], "about": "the stall from where a customer stands"},
        "wide": {"at": [8.6, 4.6, 7.6], "aim": [0.0, 1.2, -0.5], "lens_mm": 24, "sees": ["hearth_side", "troll_door", "sun_door"], "about": "both homes, the fire and the stall"},
    }
    extra = {
        "signs": [{"name": "which is which", "image": "sign.png", "center": [6.0, 1.6, 5.34], "width_m": 0.94, "height_m": 0.63, "heading": 0.0, "glow": 0.8,
                   "about": "the stall's sign, explaining which is the tea and which is the bread"}],
        "slots": {
            "stall_kettle": {"at": [2.6, 1.04, 4.5], "heading": 20.0, "about": "the counter, the troll's end"},
            "stall_teapots": {"at": [3.5, 1.04, 4.5], "heading": 0.0, "about": "the middle of the counter"},
            "stall_bread": {"at": [4.4, 1.04, 4.5], "heading": 75.0, "about": "the counter, the lizardkin's end"},
        },
        "dressing": [
            {"prop": "kettle", "slot": "stall_kettle", "glb": "dressing/kettle.glb", "small": True, "from_run": "2026-11-20T03-22-22-iron-kettle", "about": "the kettle of tea: always pours, never quite empty"},
            {"prop": "teapots", "slot": "stall_teapots", "glb": "dressing/teapots.glb", "small": True, "about": "three little teapots for sale"},
            {"prop": "bread", "slot": "stall_bread", "glb": "dressing/bread.glb", "small": True, "from_run": "2026-11-20T05-41-37-sliced-baguette-loaf", "about": "the bread: a slice meets a toon's need for a good meal"},
        ],
    }
    card = kit.set_card("settlement", "The settlement",
                        "Land that suits the cave troll and the lizardkin for the long haul: a tall stone den and a small sun house with a porch between them, a fire they share, and their first little stall, selling teapots and bread.",
                        rect(-9.0, -7.0, 9.0, 8.0), [[[-8.4, -0.9], [8.4, 7.4]], [[-1.4, -3.2], [1.4, -0.9]]], blocks, marks, paths, cameras, BUILT_BY % "settlement",
                        frame_about="the origin is the middle of the yard; the front is the side the stall faces", extra=extra)
    pots = []
    for i, (x, color) in enumerate([(-0.24, [0.78, 0.58, 0.25]), (0.0, [0.35, 0.5, 0.62]), (0.24, [0.75, 0.4, 0.33])]):
        pots += [
            {"name": "teapot %d" % (i + 1), "loft": "y", "sides": 8, "rings": [[0.0, x, 0.0, 0.05], [0.05, x, 0.0, 0.085], [0.11, x, 0.0, 0.07], [0.13, x, 0.0, 0.03]], "color": color},
            {"name": "teapot %d spout" % (i + 1), "sides": 5, "tube": [[x, 0.05, 0.07, 0.016], [x, 0.11, 0.13, 0.012]], "color": color},
            {"name": "teapot %d knob" % (i + 1), "lumps": [[x, 0.145, 0.0, 0.018]], "seed": 1, "jitter": 0.0, "color": color},
        ]
    return card, {"about": "The settlement, besides its blocks: the ground, doors, roofs, the fire, the awning. The teapots are built here; the kettle and the bread are light copies of their runs.",
                  "extras": extras, "dressing": {"teapots": pots},
                  "copies": {"kettle": {"run": "iron-kettle", "file": "profiles/lowpoly.glb"}, "bread": {"run": "sliced-baguette-loaf", "file": "profiles/mobile.glb"}}}


def spawn():
    pad = [0.8, 0.79, 0.77]
    coral, cream = [0.86, 0.38, 0.32], kit.CREAM
    blocks = [
        block("gachapon", "machine", [-3.0, 0.0, -2.3], [-1.4, 1.8, -0.9], coral),
        block("pedestal", "pedestal", [2.3, 0.0, -1.7], [2.9, 1.08, -1.1], kit.GREYBOX),
        block("label pole", "post", [2.58, 0.0, -1.8], [2.62, 1.6, -1.76], kit.GREYBOX),
    ]
    for b in blocks[:2]:
        b["build"] = False  # each is a piece of dressing: the block only keeps people out of it
    extras = [
        kit.slab("spawn pad", [-4.7, -3.7], [4.7, 4.7], pad, lip=0.2),
        disc("landing ring", 1.2, 0.0, 0.6, 1.15, 0.02, kit.STEEL_BLUE, sides=20),
        disc("landing middle", 1.2, 0.0, 0.6, 0.85, 0.03, cream, sides=20),
        box("scale cube", [3.3, 0.0, -3.5], [4.3, 1.0, -2.5], kit.GREYBOX),
        {"name": "capsule pink", "lumps": [[-1.6, 0.16, -0.3, 0.16]], "seed": 1, "jitter": 0.0, "color": [0.93, 0.6, 0.66]},
        {"name": "capsule yellow", "lumps": [[-0.9, 0.16, 0.3, 0.16]], "seed": 1, "jitter": 0.0, "color": [0.95, 0.8, 0.4]},
    ]
    marks = {
        "pad": stand([1.2, 0.6], 0, "the landing ring: where a new toon stands when their capsule opens"),
        "machine": stand([-2.2, 0.3], 180, "in front of the gachapon"),
        "button": {"kind": "touch", "at": [2.6, -0.52], "facing_deg": 180.0, "touch": {"hand": "right", "at": [2.6, 1.08, -1.17]},
                   "about": "at the BUY HOUSE pedestal, a hand on the big round button"},
    }
    paths = [{"from": "pad", "to": "machine"}, {"from": "pad", "to": "button"}]
    cameras = {"wide": {"at": [0.4, 1.9, 4.8], "aim": [0.2, 1.0, -1.2], "lens_mm": 22, "sees": ["pad", "machine", "button"], "about": "the pad, the gachapon and the pedestal"}}
    extra = {
        "signs": [
            {"name": "button plate", "image": "sign.png", "center": [2.6, 0.55, -1.085], "width_m": 0.5, "height_m": 0.17, "heading": 0.0, "glow": 0.8, "about": "BUY HOUSE, in the developer's default lettering"},
            {"name": "floating label", "image": "sign.png", "center": [2.6, 1.82, -1.75], "width_m": 1.3, "height_m": 0.44, "heading": 0.0, "glow": 0.8, "about": "the same words again on a plain label above it, the way a developer marks something unfinished"},
        ],
        "slots": {"machine": {"at": [-2.2, 0.0, -1.6], "heading": 0.0, "about": "the back of the pad"}, "pedestal": {"at": [2.6, 0.0, -1.4], "heading": 0.0, "about": "beside the landing ring"}},
        "dressing": [{"prop": "gachapon", "slot": "machine", "glb": "dressing/gachapon.glb", "about": "the gachapon machine: brings new toons into the world, one capsule at a time"},
                     {"prop": "buy-house", "slot": "pedestal", "glb": "dressing/buy-house.glb", "about": "the BUY HOUSE pedestal: a plain plinth with a big round button"}],
    }
    card = kit.set_card("spawn", "The spawn spot", "Where new toons arrive. The gachapon machine drops a capsule, the capsule opens on the landing ring, and beside it stands the developer's plain pedestal with its big round button: BUY HOUSE.",
                        rect(-5.0, -4.0, 5.0, 5.0), [[[-4.5, -3.5], [4.5, 4.5]]], blocks, marks, paths, cameras, BUILT_BY % "spawn",
                        frame_about="the origin is the middle of the pad; the front is the side you walk up from", extra=extra)
    gachapon = [
        box("base", [-0.7, 0.0, -0.6], [0.7, 1.1, 0.6], coral),
        box("band", [-0.74, 1.1, -0.64], [0.74, 1.2, 0.64], cream),
        {"name": "globe", "loft": "y", "sides": 12, "rings": [[1.2, 0.0, 0.0, 0.55], [1.42, 0.0, 0.0, 0.78], [1.78, 0.0, 0.0, 0.85], [2.12, 0.0, 0.0, 0.72], [2.32, 0.0, 0.0, 0.45]], "color": [0.8, 0.89, 0.95]},
        {"name": "cap", "loft": "y", "sides": 12, "rings": [[2.32, 0.0, 0.0, 0.47], [2.46, 0.0, 0.0, 0.3]], "color": coral},
        {"name": "cap knob", "lumps": [[0.0, 2.52, 0.0, 0.1]], "seed": 1, "jitter": 0.0, "color": cream},
        box("chute", [-0.32, 0.14, 0.6], [0.32, 0.5, 0.66], [0.2, 0.18, 0.17]),
        {"name": "crank", "sides": 10, "tube": [[0.38, 0.8, 0.6, 0.14], [0.38, 0.8, 0.7, 0.14]], "color": cream},
        box("crank grip", [0.34, 0.76, 0.7], [0.42, 0.84, 0.82], [0.2, 0.18, 0.17]),
        box("coin slot", [-0.42, 0.74, 0.6], [-0.18, 0.9, 0.63], [0.2, 0.18, 0.17]),
        # capsules you can see through the globe's window, painted on as dots
        {"name": "capsules in globe", "seed": 3, "jitter": 0.0, "color": [0.93, 0.6, 0.66], "lumps": [[-0.3, 1.6, 0.74, 0.12], [0.34, 1.9, 0.66, 0.12]]},
        {"name": "capsules in globe 2", "seed": 3, "jitter": 0.0, "color": [0.95, 0.8, 0.4], "lumps": [[0.1, 1.55, 0.8, 0.12], [-0.2, 1.95, 0.66, 0.12]]},
        {"name": "capsules in globe 3", "seed": 3, "jitter": 0.0, "color": kit.STEEL_BLUE, "lumps": [[0.42, 1.55, 0.66, 0.12], [-0.02, 1.8, 0.82, 0.12]]},
        {"name": "capsule in chute", "lumps": [[0.0, 0.3, 0.62, 0.14]], "seed": 1, "jitter": 0.0, "color": [0.95, 0.8, 0.4]},
    ]
    pedestal = [
        box("plinth", [-0.3, 0.0, -0.3], [0.3, 0.9, 0.3], [0.74, 0.73, 0.71]),
        box("plate", [-0.34, 0.9, -0.34], [0.34, 0.95, 0.34], [0.82, 0.81, 0.79]),
        disc("button ring", 0.0, 0.95, 0.0, 0.21, 0.03, [0.2, 0.2, 0.2], sides=16),
        {"name": "button", "loft": "y", "sides": 16, "rings": [[0.98, 0.0, 0.0, 0.17], [1.05, 0.0, 0.0, 0.17], [1.08, 0.0, 0.0, 0.12]], "color": [0.85, 0.16, 0.14]},
        box("label pole", [-0.02, 0.0, -0.4], [0.02, 1.6, -0.36], [0.74, 0.73, 0.71]),
        box("label board", [-0.68, 1.58, -0.39], [0.68, 2.06, -0.36], [0.82, 0.81, 0.79]),
    ]
    return card, {"about": "The spawn spot, besides its blocks: the pad and the landing ring. The gachapon and the pedestal are dressing, each built from simple pieces around its own foot.",
                  "extras": extras, "dressing": {"gachapon": gachapon, "buy-house": pedestal}}


PLACES = {"grass": grass, "boxing-house": boxing_house, "settlement": settlement, "spawn": spawn}


def main():
    for name in sys.argv[1:] or list(PLACES):
        card, recipe = PLACES[name]()
        folder = os.path.join(REPO, "sets", name)
        os.makedirs(folder, exist_ok=True)
        for file, value in (("set.json", card), ("build.json", recipe)):
            with open(os.path.join(folder, file), "w") as f:
                json.dump(value, f, indent=1)
                f.write("\n")
        print("PLACE %s: %d blocks, %d marks, %d cameras, %d extra pieces" % (name, len(card["blocks"]), len(card["marks"]), len(card["cameras"]), len(recipe["extras"])))


if __name__ == "__main__":
    main()
