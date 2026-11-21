"""Tries the world with no Blender and no model.

    python3 scripts/world/test_world.py

What it shows:
  places   world.json puts every place down on one ground with no two footprints overlapping; every place is
           a sound set; a place slid onto another, or off the ground, is told
  epochs   the newest epoch is the world as it is now, and a world that has moved on since is told
  house    the dancer's kept design is a sound plan, builds into the very set that is kept, and a made-up
           design with other rooms builds into a sound set too
  toons    every toon stands on a mark of a place, with its small still file there; the artifacts are where
           the story says; the ninja's stage has its sitter, its group and its photographer, and a real
           place to hang behind them
  load     the first view of the world is small: few files, low-poly, nothing that needs a decoder

`cases()` hands the same checks to scripts/test_tools.py.
"""

import copy
import json
import os
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
import build_house  # noqa: E402
import places  # noqa: E402
import standing  # noqa: E402
import world as world_file  # noqa: E402

OVERVIEW_FILES, OVERVIEW_MB, OVERVIEW_TRIANGLES = 30, 2.5, 30000  # what the first view may cost a phone


def check(label, ok, detail=""):
    print("    %s  %s%s" % ("ok  " if ok else "FAIL", label, ("  (%s)" % (str(detail)[:600],)) if detail and not ok else ""))
    if not ok:
        raise AssertionError(label)


def glb(path):
    """A .glb's JSON, read straight from the file."""
    with open(path, "rb") as f:
        f.read(12)
        size, _ = struct.unpack("<II", f.read(8))
        return json.loads(f.read(size))


def triangles(doc):
    total = 0
    for mesh in doc.get("meshes") or []:
        for prim in mesh["primitives"]:
            total += doc["accessors"][prim["indices"] if "indices" in prim else prim["attributes"]["POSITION"]]["count"] // 3
    return total


def test_places():
    """world.json puts every place on one ground with no footprints overlapping, and every place is a sound set."""
    world = world_file.load()
    problems, seen = world_file.check(world)
    check("the world is sound: %d places, %d toons, %d artifacts" % (len(seen["places"]), len(seen["toons"]), len(seen["artifacts"])), not problems, problems[:4])
    for name in ("grass", "boxing-house", "settlement", "dancer-house", "spawn", "ninja-stage", "ring"):
        check("%s is in the world" % name, name in world["places"])
    for name, place in world["places"].items():
        wrong, _ = standing.check(world_file.place_set(place))
        check("%s (the %s set) passes set-check" % (name, place["set"]), not wrong, wrong[:3])
    outlines = {name: world_file.outline_of(place) for name, place in world["places"].items()}
    spots = world["places"]

    def stacked(a, b):  # two floors of one building, like the ring (1.4 m) and the roof (6 m) of the boxing house
        pa, pb = spots[a], spots[b]
        return pa.get("inside") and pa.get("inside") == pb.get("inside") and abs(pa.get("lift_m", 0.0) - pb.get("lift_m", 0.0)) >= 2.0

    apart = [(a, b) for a in outlines for b in outlines if a < b and spots[a].get("inside") != b and spots[b].get("inside") != a
             and not stacked(a, b) and world_file.crosses(outlines[a], outlines[b])]
    check("no two footprints overlap (the ring and the roof are inside the boxing house, by design)",
          not apart and spots["ring"]["inside"] == "boxing-house", apart)
    check("the ring stands wholly inside the boxing house", world_file.within(outlines["ring"], outlines["boxing-house"]))
    grass, garden = outlines["grass"], outlines["boxing-house"]
    check("the beer garden is beside the grass: under a metre between them", 0.0 <= min(p[1] for p in grass) - max(p[1] for p in garden) < 1.0)
    # A place slid onto another, and one pushed off the ground, are told.
    moved = copy.deepcopy(world)
    moved["places"]["spawn"]["at"] = [2.0, 12.0]
    moved["places"]["settlement"]["at"] = [60.0, -9.5]
    said = "\n".join(world_file.check(moved)[0])
    check("a place put down on top of another is told", "the footprints of \"grass\" and \"spawn\" overlap" in said, said[:300])
    check("a place off the edge of the ground is told", "place \"settlement\" runs off the ground" in said, said[:300])
    # Putting a place down is standing.placed and nothing else: a mark of the turned house lands where the arithmetic says.
    spot, facing = world_file.where(world, "dancer-house", "stage")
    st = world_file.place_set(world["places"]["dancer-house"])
    own = st["marks"]["stage"]["at"]
    at = world["places"]["dancer-house"]["at"]
    check("the dancer's house is turned to face the spawn spot: her stage mark lands at (%.2f, %.2f), facing %g" % (spot[0], spot[1], facing),
          abs(spot[0] - (at[0] - own[0])) < 1e-3 and abs(spot[1] - (at[1] - own[1])) < 1e-3 and abs(abs(facing) - 180.0) < 1e-6)
    made = {name: fn()[0] for name, fn in places.PLACES.items()}
    for name, card in made.items():
        kept = standing.load(name)
        kept.pop("dir")
        check("sets/%s/set.json is what places.py writes" % name, card == kept)


def test_epochs():
    """the newest epoch is the world as it is now; a world that has moved on is told; an old epoch is never written over."""
    world = world_file.load()
    saved = world_file.epochs()
    check("there is an epoch 0 with a title and a caption", saved and saved[0]["name"] == "epoch-0" and saved[0]["number"] == 0 and saved[0]["title"] and saved[0]["caption"])
    newest = saved[-1]
    check("the newest epoch (%s) is the world as it is now" % newest["name"], world["epoch"] == newest["name"] and all(newest[key] == world[key] for key in world_file.STATE))
    later = copy.deepcopy(world)
    later["toons"][0]["mark"] = "circle"
    said = "\n".join(world_file.check(later)[0])
    check("a world that has changed since its epoch was saved is told to save a new one", "has changed since" in said, said[:300])
    keep = world_file.EPOCHS
    try:
        world_file.EPOCHS = tempfile.mkdtemp(prefix="forge-epochs-")
        world_file.save_epoch(world, "epoch-0", "The reset", "one")
        world_file.save_epoch(later, "epoch-1", "Later", "two")
        check("a later epoch is a new file, numbered on", [e["number"] for e in world_file.epochs()] == [0, 1] and world_file.epochs()[1]["toons"][0]["mark"] == "circle")
        try:
            world_file.save_epoch(later, "epoch-0", "Changed", "afterwards")
            refused = False
        except SystemExit:
            refused = True
        check("an old epoch is never edited", refused and world_file.epochs()[0]["caption"] == "one")
    finally:
        world_file.EPOCHS = keep


def test_house():
    """the dancer's kept design is a sound plan and builds into the very set that is kept; another design builds a sound set too."""
    world = world_file.load()
    name = world["places"]["dancer-house"]["set"]
    folder = os.path.join(REPO, "sets", name)
    with open(os.path.join(folder, "design.json")) as f:
        design = json.load(f)
    with open(os.path.join(folder, "design_cost.json")) as f:
        cost = json.load(f)
    check("the design is kept with what it cost: %d ask(s) of %s, %d tokens out, %s s" % (cost["asks"], cost["model"], cost["output_tokens"], cost["seconds"]), cost["asks"] >= 1 and cost["output_tokens"] > 0)
    kinds = [a["kind"] for a in design["areas"]]
    check("the plan has one stage, one practice floor, and a microphone on one of them", kinds.count("Stage") == 1 and kinds.count("PracticeFloor") == 1
          and next(a for a in design["areas"] if a["name"] == design["microphone_area"])["kind"] in ("Stage", "PracticeFloor"))
    inside = all(a["x_m"] >= 0 and a["z_m"] >= 0 and a["x_m"] + a["wide_m"] <= design["wide_m"] + 0.01 and a["z_m"] + a["deep_m"] <= design["deep_m"] + 0.01 for a in design["areas"])
    check("every area lies inside the house (%s x %s m)" % (design["wide_m"], design["deep_m"]), inside)
    card, recipe = build_house.plan_set(name, design, folder)
    kept = standing.load(name)
    kept.pop("dir")
    check("the kept set.json is what the design builds into: nothing was edited by hand", card == kept)
    wrong, seen = standing.check(standing.load(name))
    check("the house is a sound set: marks %s" % ", ".join(kept["marks"]), not wrong and {"stage", "practice", "gate"} <= set(kept["marks"]), wrong[:3])
    check("the microphone stands on her stage, and the stage mark is on the platform", kept["dressing"][0]["prop"] == "microphone" and kept["marks"]["stage"]["floor_y"] == build_house.STAGE_TALL
          and kept["slots"]["microphone"]["at"][1] == build_house.STAGE_TALL)
    check("the house faces what she asked for (%s), and the world puts it down that way" % design["faces"], kept["faces"]["facing_deg"] == world["places"]["dancer-house"]["facing_deg"])
    check("each camera holds what it says it sees: %s" % ", ".join("%s: %d marks" % (c, len(v["sees"])) for c, v in kept["cameras"].items()), len(kept["cameras"]) == 2)
    # Asking again makes a different house: another design, with other rooms and every feature, builds a sound plan too.
    other = {
        "name": "The Lookout", "style": "A plain timber cabin.", "why": "For the test.", "wide_m": 9.0, "deep_m": 8.0, "faces": "the grass", "faces_why": "To watch.",
        "walls": {"name": "pine", "hex": "#c8a878"}, "roof": {"name": "slate", "hex": "#55606a"}, "trim": {"name": "navy", "hex": "#223a5e"}, "materials": [],
        "areas": [
            {"name": "bunk", "kind": "Bedroom", "x_m": 0.0, "z_m": 0.0, "wide_m": 3.0, "deep_m": 3.0, "floor": {"name": "a", "hex": "#b08a5a"}, "about": "a bunk"},
            {"name": "galley", "kind": "Kitchen", "x_m": 3.0, "z_m": 0.0, "wide_m": 3.0, "deep_m": 3.0, "floor": {"name": "a", "hex": "#a07a4a"}, "about": "a galley"},
            {"name": "snug", "kind": "SittingRoom", "x_m": 6.0, "z_m": 0.0, "wide_m": 3.0, "deep_m": 3.0, "floor": {"name": "a", "hex": "#b89a6a"}, "about": "a snug"},
            {"name": "deck", "kind": "PracticeFloor", "x_m": 0.0, "z_m": 3.0, "wide_m": 4.5, "deep_m": 3.5, "floor": {"name": "a", "hex": "#c0a070"}, "about": "a deck"},
            {"name": "poop", "kind": "Stage", "x_m": 4.5, "z_m": 3.0, "wide_m": 4.5, "deep_m": 2.5, "floor": {"name": "a", "hex": "#403020"}, "about": "a stage"},
            {"name": "yard", "kind": "Garden", "x_m": 0.0, "z_m": 6.5, "wide_m": 9.0, "deep_m": 1.5 + 0.0, "floor": {"name": "a", "hex": "#6a9a5a"}, "about": "a garden"},
        ],
        "microphone_area": "poop",
        "features": [{"kind": k, "area": a, "about": "x"} for k, a in (("arches", "poop"), ("flower_pots", "yard"), ("lanterns", "deck"), ("string_lights", "yard"), ("mirror_wall", "deck"),
                                                                      ("awning", "poop"), ("fountain", "yard"), ("shutters", "galley"))],
        "sign": "Ahoy",
    }
    card, recipe = build_house.plan_set("the-lookout", other, tempfile.mkdtemp(prefix="forge-house-"))
    wrong = [p for p in standing.check(dict(card, dir=tempfile.gettempdir()))[0] if "missing" not in p]
    check("a different design builds a sound plan: %d blocks, %d pieces, marks %s" % (len(card["blocks"]), len(recipe["extras"]), ", ".join(card["marks"])),
          not wrong and {"stage", "practice", "gate", "seat"} <= set(card["marks"]) and card["faces"]["facing_deg"] == -90.0, wrong[:3])


def test_toons():
    """every toon stands on a mark with its still file there; the artifacts are where the story says; the ninja's stage is ready for portraits."""
    world = world_file.load()
    homes = {t["toon"]: (t["place"], t["mark"]) for t in world["toons"]}
    check("the seven toons are at home", homes == {"roosevelt": ("grass", "stride"), "lincoln": ("boxing-house", "ringside"), "pirate": ("boxing-house", "brew_door"), "ninja": ("ninja-stage", "photographer"),
                                                    "dancer": ("dancer-house", "stage"), "troll": ("settlement", "stall_troll"), "lizardkin": ("settlement", "stall_lizardkin")}, homes)
    for toon in world["toons"]:
        doc = glb(os.path.join(REPO, toon["glb"]))
        spot, _ = world_file.where(world, toon["place"], toon["mark"])
        check("%s stands at (%.1f, %.1f): a still file, %d triangles, no skeleton" % (toon["toon"], spot[0], spot[1], triangles(doc)),
              200 < triangles(doc) < 4000 and not doc.get("skins") and not doc.get("animations") and "KHR_draco_mesh_compression" not in (doc.get("extensionsUsed") or []))
    where = {a["name"]: (a.get("place") or "held by " + a["held_by"], a.get("slot")) for a in world["artifacts"]}
    check("the gachapon and the BUY HOUSE pedestal stand at the spawn spot", where["gachapon"] == ("spawn", "machine") and where["buy-house"] == ("spawn", "pedestal"))
    check("the kettle and the bread are on the settlement's stall, the microphone in the dancer's house, the camera with the ninja",
          where["kettle"] == ("settlement", "stall_kettle") and where["bread"] == ("settlement", "stall_bread") and where["microphone"] == ("dancer-house", "microphone") and where["pinhole-camera"][0] == "held by ninja")
    spawn = standing.load("spawn")
    pedestal, machine = spawn["slots"]["pedestal"]["at"], spawn["slots"]["machine"]["at"]
    check("the pedestal is near the gachapon (%.1f m) and its button can be pressed from the `button` mark" % ((pedestal[0] - machine[0]) ** 2 + (pedestal[2] - machine[2]) ** 2) ** 0.5,
          ((pedestal[0] - machine[0]) ** 2 + (pedestal[2] - machine[2]) ** 2) ** 0.5 < 6.0 and spawn["marks"]["button"]["kind"] == "touch" and len(spawn["signs"]) == 2)
    # The ninja's stage: a sitter, a row for a group, a photographer, and only real places behind them.
    stage = standing.load(world["places"]["ninja-stage"]["set"])
    check("the ninja's stage has a sitter, a group and a photographer", stage["groups"]["portrait"] == ["sitter", "group_1", "group_2", "group_3"] and all(m in stage["marks"] for m in stage["groups"]["portrait"] + ["photographer"]))
    sitter, photographer = stage["marks"]["sitter"], stage["marks"]["photographer"]
    check("the photographer faces the sitter from %.1f m" % (photographer["at"][1] - sitter["at"][1]), photographer["at"][0] == sitter["at"][0] and 2.0 < photographer["at"][1] - sitter["at"][1] < 4.0 and photographer["facing_deg"] == 180.0)
    options = stage["backdrop_options"]["options"]
    check("what hangs behind them is always a place in the world: %s" % ", ".join(o["place"] for o in options),
          len(options) >= 4 and all(o["place"] in world["places"] and os.path.isfile(os.path.join(stage["dir"], o["image"])) for o in options)
          and stage["backdrop"]["place"] in world["places"] and stage["backdrop"]["image"] in [o["image"] for o in options])
    wide = stage["cameras"]["wide"]["sees"]
    check("the wide camera holds the sitter and the whole group", all(m in wide for m in stage["groups"]["portrait"]))


def test_load():
    """the first view of the world is small: few files, low-poly, nothing that needs a decoder."""
    world = world_file.load()
    files = world_file.overview_files(world)
    first = files["overview"]
    check("the overview is %d files, %.2f MB (at most %d files, %.1f MB)" % (first["files"], first["bytes"] / 1e6, OVERVIEW_FILES, OVERVIEW_MB), first["files"] <= OVERVIEW_FILES and first["bytes"] <= OVERVIEW_MB * 1e6)
    docs = {path: glb(os.path.join(REPO, path)) for path in first["list"] if path.endswith(".glb")}
    total = sum(triangles(doc) for doc in docs.values())
    check("it is low-poly everywhere: %d triangles in all" % total, total <= OVERVIEW_TRIANGLES)
    packed = [path for path, doc in docs.items() if "KHR_draco_mesh_compression" in (doc.get("extensionsUsed") or [])]
    check("nothing in it needs a decoder fetched first", not packed, packed)
    later = files["on_coming_close"]
    check("what is small or heavy waits until you come close: %d more files, %.2f MB" % (later["files"], later["bytes"] / 1e6),
          any("ring/set.glb" in p for p in later["list"]) and any("kettle" in p for p in later["list"]) and not any("kettle" in p for p in first["list"]))


TESTS = [test_places, test_epochs, test_house, test_toons, test_load]


def cases():
    """The tests, for scripts/test_tools.py: [(name, what it shows, the function)]."""
    return [(t.__name__[5:], t.__doc__, t) for t in TESTS]


def main():
    failed = 0
    for test in TESTS:
        print("%s: %s" % (test.__name__[5:], test.__doc__))
        try:
            test()
        except Exception as e:  # a failed check, or something a check reads that is missing
            failed += 1
            print("    FAILED: %s: %s" % (type(e).__name__, str(e)[:800]))
    print("%d world case(s) failed" % failed if failed else "all %d world cases passed" % len(TESTS))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
