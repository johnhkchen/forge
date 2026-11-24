"""The world: every place on one shared ground, at true scale, and the epochs it is kept in.

    python3 scripts/world/world.py check                 # is the world sound? (`just world-check`)
    python3 scripts/world/world.py map                   # where everything is, in words
    python3 scripts/world/world.py save-epoch epoch-0 --title "..." --caption "..."
    python3 scripts/world/world.py stock <runs folder>   # light copies of the runs' objects, where places use them
    python3 scripts/world/world.py load                  # what the gallery's overview fetches: files and MB
    python3 scripts/world/world.py backdrops             # the pictures that can hang behind the ninja's stage: one of each place

world.json is the world as it is now:

    ground     the developer's unfinished floor: {center [x, z], size_m [across, deep], color,
               cubes [{at [x, z], size_m}] (grey scale cubes), notes [{at [x, z], text}] ("TODO" labels)}
    places     {name: {set, at [x, z], facing_deg, label}}: a standing set (sets/<set>/set.json) put
               down with its origin at `at`, its front facing `facing_deg` (scripts/sets/standing.py,
               `placed`). `inside` names a place this one stands within (the ring, in the boxing
               house), with `lift_m` for how far its floor is above the ground
    artifacts  [{name, title, about, whose}] and where: `place` + `slot` (dressing on a set's slot), or
               `held_by` a toon with an `offset` [x, y, z] from their feet, and its own `glb`
    toons      [{toon, name, glb, place, mark, pose}]: who stands where, on a mark of a place
    planned    {name: {set, at, facing_deg, label, about}}: places that are built and put down but are not
               in the story yet (canon/CANON.md says what has happened). They are checked like places (a
               sound set, on the ground, not on top of anything) and shown on the world page with the
               world as it is now, marked as planned, but an epoch does not save them: when the story takes
               one in, it moves to `places` and a new epoch is saved
    epoch      the newest saved state, by name

An epoch (world/epochs/<name>.json) is that same state, saved whole, with a
title and a one-line caption. The world moves on by saving a new file; old
ones are never edited, so the gallery can step through them like a time-lapse.

Plain Python: no Blender.
"""

import copy
import glob
import json
import math
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import standing  # noqa: E402

FORMAT = "forge-world/1"
WORLD = os.path.join(REPO, "world.json")
EPOCHS = os.path.join(REPO, "world", "epochs")
STATE = ("ground", "places", "artifacts", "toons")  # what an epoch saves
SMALL_M = 0.7  # dressing smaller than this is left for when you come close


def load(path=WORLD):
    with open(path) as f:
        return json.load(f)


def epochs():
    """Every saved epoch, oldest first."""
    found = []
    for path in sorted(glob.glob(os.path.join(EPOCHS, "*.json"))):
        with open(path) as f:
            found.append(json.load(f))
    return sorted(found, key=lambda e: e.get("number", 0))


def place_set(place):
    return standing.load(place["set"])


def put(place, st=None):
    """(point, heading): from a place's own frame to the world's."""
    return standing.placed(st or place_set(place), place["at"], place.get("facing_deg"))


def outline_of(place, st=None):
    st = st or place_set(place)
    point, _ = put(place, st)
    return [point(p) for p in st["footprint"]["outline"]]


def crosses(a, b):
    """Do two outlines (convex, [[x, z], ...]) overlap? Touching edges do not count."""
    for shape in (a, b):
        for (x0, z0), (x1, z1) in zip(shape, shape[1:] + shape[:1]):
            nx, nz = z1 - z0, x0 - x1
            pa = [x * nx + z * nz for x, z in a]
            pb = [x * nx + z * nz for x, z in b]
            if max(pa) <= min(pb) + 1e-6 or max(pb) <= min(pa) + 1e-6:
                return False
    return True


def within(inner, outer):
    return all(standing.inside(outer, x, z) for x, z in inner)


def where(world, place_name, mark_name):
    """A mark of a place, in the world: ([x, z], facing)."""
    place = world["places"][place_name]
    st = place_set(place)
    point, heading = put(place, st)
    m = standing.mark(st, mark_name)
    spot = standing.stand_spot(m) if m.get("kind") != "sit" else m["at"]
    return point(spot), heading(m["facing_deg"])


def check(world):
    """(what is wrong with the world, in words; what was looked at)."""
    problems, seen = [], {}
    say = problems.append
    if world.get("format") != FORMAT:
        say("format is %r, not %r" % (world.get("format"), FORMAT))
    for key in STATE + ("epoch",):
        if key not in world:
            say('world.json has no "%s"' % key)
    if problems:
        return problems, seen
    sets, outlines = {}, {}
    for name, place in world["places"].items():
        try:
            st = place_set(place)
        except standing.SetProblem as e:
            say("place \"%s\": %s" % (name, e))
            continue
        wrong, _ = standing.check(st)
        for line in wrong:
            say("place \"%s\" (the %s set): %s" % (name, place["set"], line))
        sets[name], outlines[name] = st, outline_of(place, st)
    ground = world["ground"]
    gx, gz = ground["center"]
    half = [ground["size_m"][0] / 2.0, ground["size_m"][1] / 2.0]
    floor = [[gx - half[0], gz - half[1]], [gx + half[0], gz - half[1]], [gx + half[0], gz + half[1]], [gx - half[0], gz + half[1]]]
    names = list(outlines)
    for name in names:
        place = world["places"][name]
        if not within(outlines[name], floor):
            say("place \"%s\" runs off the ground" % name)
        parent = place.get("inside")
        if parent:
            if parent not in outlines:
                say("place \"%s\" is inside \"%s\", which is not a place" % (name, parent))
            elif not within(outlines[name], outlines[parent]):
                say("place \"%s\" is said to be inside \"%s\" but its footprint is not" % (name, parent))
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if world["places"][a].get("inside") == b or world["places"][b].get("inside") == a:
                continue
            pa, pb = world["places"][a], world["places"][b]
            if pa.get("inside") and pa.get("inside") == pb.get("inside") and abs(pa.get("lift_m", 0.0) - pb.get("lift_m", 0.0)) >= 2.0:
                continue  # two floors of one building (the ring at 1.4 m, the roof at 6 m) may share ground
            if crosses(outlines[a], outlines[b]):
                say("the footprints of \"%s\" and \"%s\" overlap" % (a, b))
    for cube in ground.get("cubes") or []:
        for name, outline in outlines.items():
            if standing.inside(outline, *cube["at"]):
                say("a scale cube at %s stands in \"%s\"" % (cube["at"], name))
    seen["places"] = {name: {"at": world["places"][name]["at"], "across_m": round(max(p[0] for p in o) - min(p[0] for p in o), 1), "deep_m": round(max(p[1] for p in o) - min(p[1] for p in o), 1)}
                      for name, o in outlines.items()}

    # Planned places: built and put down, not in the story yet. The same rules, against everything else.
    planned = {}
    for name, place in (world.get("planned") or {}).items():
        if name in world["places"]:
            say("\"%s\" is both a place and planned: a place that is in the story is no longer planned" % name)
            continue
        try:
            st = place_set(place)
        except standing.SetProblem as e:
            say("planned place \"%s\": %s" % (name, e))
            continue
        wrong, _ = standing.check(st)
        for line in wrong:
            say("planned place \"%s\" (the %s set): %s" % (name, place["set"], line))
        planned[name] = outline_of(place, st)
        if not within(planned[name], floor):
            say("planned place \"%s\" runs off the ground" % name)
        for other, outline in list(outlines.items()) + [(n, o) for n, o in planned.items() if n != name]:
            if crosses(planned[name], outline):
                say("the footprints of planned \"%s\" and \"%s\" overlap" % (name, other))
        for cube in ground.get("cubes") or []:
            if standing.inside(planned[name], *cube["at"]):
                say("a scale cube at %s stands in planned \"%s\"" % (cube["at"], name))
    seen["planned"] = {name: {"at": world["planned"][name]["at"], "across_m": round(max(p[0] for p in o) - min(p[0] for p in o), 1), "deep_m": round(max(p[1] for p in o) - min(p[1] for p in o), 1)}
                       for name, o in planned.items()}

    taken = {}
    toons = {t["toon"]: t for t in world["toons"]}
    for toon in world["toons"]:
        if toon.get("place") not in sets:
            say("toon \"%s\" is at \"%s\", which is not a place" % (toon["toon"], toon.get("place")))
            continue
        if toon.get("mark") not in sets[toon["place"]]["marks"]:
            say("toon \"%s\": the %s has no mark called \"%s\"" % (toon["toon"], toon["place"], toon.get("mark")))
            continue
        if not os.path.isfile(os.path.join(REPO, toon.get("glb", ""))):
            say("toon \"%s\": %s is missing (python3 scripts/world/world.py stock <runs>, then just world-toons)" % (toon["toon"], toon.get("glb")))
        spot = (toon["place"], toon["mark"])
        if spot in taken:
            say("toons \"%s\" and \"%s\" stand on the same mark" % (taken[spot], toon["toon"]))
        taken[spot] = toon["toon"]
    seen["toons"] = {t["toon"]: "%s, %s" % (t.get("place"), t.get("mark")) for t in world["toons"]}

    for thing in world["artifacts"]:
        if thing.get("held_by"):
            if thing["held_by"] not in toons:
                say("artifact \"%s\" is held by \"%s\", who is not in the world" % (thing["name"], thing["held_by"]))
            if not os.path.isfile(os.path.join(REPO, thing.get("glb", ""))):
                say("artifact \"%s\": %s is missing" % (thing["name"], thing.get("glb")))
            continue
        st = sets.get(thing.get("place"))
        if st is None:
            say("artifact \"%s\" is at \"%s\", which is not a place" % (thing["name"], thing.get("place")))
        elif not any(d.get("slot") == thing.get("slot") for d in st.get("dressing") or []):
            say("artifact \"%s\": nothing stands on the slot \"%s\" of the %s" % (thing["name"], thing.get("slot"), thing["place"]))
    seen["artifacts"] = [t["name"] for t in world["artifacts"]]

    saved = {e.get("name"): e for e in epochs()}
    now = saved.get(world["epoch"])
    if now is None:
        say("the epoch \"%s\" has not been saved (world/epochs/%s.json)" % (world["epoch"], world["epoch"]))
    elif any(now.get(key) != world[key] for key in STATE):
        say("the world has changed since \"%s\" was saved: save a new epoch, or save this one again if it has not been shown yet" % world["epoch"])
    for e in saved.values():
        if not e.get("title") or not e.get("caption"):
            say("epoch \"%s\" needs a title and a caption" % e.get("name"))
    seen["epochs"] = [e.get("name") for e in epochs()]
    return problems, seen


def save_epoch(world, name, title, caption):
    """The world as it is now, saved whole. Refuses to write over an epoch whose state differs unless it is the newest one."""
    os.makedirs(EPOCHS, exist_ok=True)
    path = os.path.join(EPOCHS, name + ".json")
    before = epochs()
    known = next((e for e in before if e.get("name") == name), None)
    if known and before[-1].get("name") != name:
        raise SystemExit("%s is not the newest epoch: old epochs are never edited" % name)
    number = known["number"] if known else (before[-1]["number"] + 1 if before else 0)
    record = {"format": "forge-epoch/1", "name": name, "number": number, "title": title or (known or {}).get("title"), "caption": caption or (known or {}).get("caption")}
    for key in STATE:
        record[key] = copy.deepcopy(world[key])
    with open(path, "w") as f:
        json.dump(record, f, indent=1)
        f.write("\n")
    return path


# ---- light copies of the runs' objects ---------------------------------------------


def newest_run(runs, ending):
    found = sorted(d for d in glob.glob(os.path.join(runs, "*-" + ending)) if os.path.isdir(d))
    if not found:
        raise SystemExit("no run in %s is named for \"%s\"" % (runs, ending))
    return found[-1]


def copy_glb(source, out, move=None):
    """A run's .glb copied to where a place keeps it; `move` adds one node above everything, carrying the shift."""
    import blockout_recipe

    os.makedirs(os.path.dirname(out), exist_ok=True)
    if not move:
        shutil.copyfile(source, out)
        return
    doc, rest = blockout_recipe.read(source)
    for scene in doc.get("scenes") or []:
        if not scene.get("nodes"):
            continue
        doc["nodes"].append({"name": "moved", "children": list(scene["nodes"]), "translation": [float(v) for v in move]})
        scene["nodes"] = [len(doc["nodes"]) - 1]
    blockout_recipe.write(out, doc, rest)


def unpack(paths):
    """Write copies again without Draco (scripts/world/plain_glb.py, in a background Blender), so a browser needs no decoder for them."""
    import subprocess

    blender = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
    done = subprocess.run([blender, "-b", "--factory-startup", "-P", os.path.join(HERE, "plain_glb.py"), "--"] + [os.path.join(REPO, p) for p in paths], capture_output=True, text=True)
    lines = [l for l in done.stdout.splitlines() if l.startswith("PLAIN")]
    if done.returncode or len(lines) != len(paths):
        raise SystemExit("could not unpack the copies: %s" % (done.stdout + done.stderr)[-600:])


def stock(world, runs):
    """Bring in the light versions of the runs' objects: each set's build.json `copies`, and what toons hold."""
    made = []
    for name in standing.names():
        recipe_path = os.path.join(standing.SETS, name, "build.json")
        if not os.path.exists(recipe_path):
            continue
        with open(recipe_path) as f:
            copies = json.load(f).get("copies") or {}
        for prop, card in copies.items():
            out = os.path.join(standing.SETS, name, "dressing", prop + ".glb")
            copy_glb(os.path.join(newest_run(runs, card["run"]), card["file"]), out, card.get("move"))
            made.append(os.path.relpath(out, REPO))
    for thing in world["artifacts"]:
        if thing.get("held_by") and thing.get("from_run"):
            out = os.path.join(REPO, thing["glb"])
            copy_glb(os.path.join(newest_run(runs, thing["from_run"]), thing.get("from_file", "profiles/lowpoly.glb")), out)
            made.append(thing["glb"])
    unpack(made)
    return made


def backdrops(world, stage="studio"):
    """The pictures that can hang behind a stage (its set's `backdrop_options`): each a real place in the world, taken
    through that place's own camera in a background Blender, and kept small."""
    import subprocess

    blender = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
    st = standing.load(stage)
    made = []
    for option in st["backdrop_options"]["options"]:
        place = world["places"][option["place"]]
        out = os.path.join(st["dir"], option["image"])
        png = os.path.splitext(out)[0] + ".png"
        os.makedirs(os.path.dirname(out), exist_ok=True)
        done = subprocess.run([blender, "-b", "--factory-startup", "-P", os.path.join(REPO, "scripts", "sets", "set_still.py"), "--", place["set"], "--camera", option["camera"],
                               "--size", "1020x680", "--out", png], capture_output=True, text=True)
        if "STILL" not in done.stdout:
            raise SystemExit("no picture of %s: %s" % (option["place"], (done.stdout + done.stderr)[-500:]))
        if out != png:
            subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "82", png, "--out", out], capture_output=True, check=True)
            os.remove(png)
        made.append(os.path.relpath(out, REPO))
    return made


# ---- what the overview loads -------------------------------------------------------


def overview_files(world):
    """The files the gallery fetches to show the whole world, before anyone comes close, and what waits for that."""
    first, later = [], []
    for name, place in list(world["places"].items()) + list((world.get("planned") or {}).items()):
        st = place_set(place)
        if place.get("inside"):
            continue  # drawn by the place it stands in, as dressing
        rel = os.path.relpath(st["dir"], REPO)
        first.append(os.path.join(rel, st["geometry"].get("glb", "set.glb")))
        for item in st.get("dressing") or []:
            (later if item.get("small") else first).append(os.path.normpath(os.path.join(rel, item["glb"])))
            if item.get("detail"):
                later.append(os.path.normpath(os.path.join(rel, item["detail"])))
        for sign in st.get("signs") or []:
            (later if sign.get("detail") else first).append(os.path.normpath(os.path.join(rel, sign["image"])))
        if st.get("backdrop"):
            later.append(os.path.normpath(os.path.join(rel, st["backdrop"]["image"])))
    first += [t["glb"] for t in world["toons"]]
    later += [t["glb"] for t in world["artifacts"] if t.get("glb")]
    size = lambda paths: sum(os.path.getsize(os.path.join(REPO, p)) for p in set(paths) if os.path.isfile(os.path.join(REPO, p)))
    return {"overview": {"files": len(set(first)), "bytes": size(first), "list": sorted(set(first))},
            "on_coming_close": {"files": len(set(later) - set(first)), "bytes": size(set(later) - set(first)), "list": sorted(set(later) - set(first))}}


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("check", "map", "save-epoch", "stock", "load", "backdrops"):
        sys.exit(__doc__.split("\n\n")[1])
    world = load()
    if args[0] == "save-epoch":
        opt = lambda flag: args[args.index(flag) + 1] if flag in args else None
        print("WORLD saved", os.path.relpath(save_epoch(world, args[1], opt("--title"), opt("--caption")), REPO))
        return
    if args[0] == "stock":
        for path in stock(world, os.path.abspath(args[1])):
            print("WORLD stocked", path)
        return
    if args[0] == "backdrops":
        for path in backdrops(world):
            print("WORLD backdrop", path)
        return
    if args[0] == "load":
        files = overview_files(world)
        for key, part in files.items():
            print("WORLD %s: %d files, %.2f MB" % (key.replace("_", " "), part["files"], part["bytes"] / 1e6))
            for path in part["list"]:
                print("WORLD   %7.1f kB  %s" % (os.path.getsize(os.path.join(REPO, path)) / 1e3 if os.path.isfile(os.path.join(REPO, path)) else 0, path))
        return
    problems, seen = check(world)
    for name, card in (seen.get("places") or {}).items():
        place = world["places"][name]
        print("WORLD %s: the %s set at (%g, %g), facing %g, %s x %s m%s" % (name, place["set"], place["at"][0], place["at"][1], place.get("facing_deg", 0), card["across_m"], card["deep_m"],
                                                                         ", inside the " + place["inside"] if place.get("inside") else ""))
    for name, card in (seen.get("planned") or {}).items():
        place = world["planned"][name]
        print("WORLD %s (planned, not in the story yet): the %s set at (%g, %g), facing %g, %s x %s m" % (name, place["set"], place["at"][0], place["at"][1], place.get("facing_deg", 0), card["across_m"], card["deep_m"]))
    for toon, spot in (seen.get("toons") or {}).items():
        print("WORLD toon %s: %s" % (toon, spot))
    if args[0] == "map":
        return
    print("WORLD artifacts: %s" % ", ".join(seen.get("artifacts") or []))
    print("WORLD epochs: %s (now: %s)" % (", ".join(seen.get("epochs") or []) or "none", world.get("epoch")))
    for line in problems:
        print("WORLD PROBLEM %s" % line)
    print("WORLD " + ("sound" if not problems else "%d problems" % len(problems)))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
