"""Dioramas: one moment of the story, built from the real game assets and stood on a collector's base.

    python3 scripts/diorama/diorama.py check [name ...] [--runs runs]   # is the plan sound? (`just diorama-check`)
    python3 scripts/diorama/diorama.py list                             # every diorama, newest first
    python3 scripts/diorama/diorama.py load <name>                      # what the gallery's front page fetches for it

The portraits and the comics are the world as the toons imagine it. A diorama
is the other layer: the toys themselves, low-poly and a little clunky, posed
on a shelf in the basement. `dioramas/<name>/diorama.json` is the whole plan:

    title, caption, epoch, number   what the brass plate and the gallery say; the highest number is the one
                                    on the gallery's front page, the others go on the shelf under it
    set       {name, backdrop, keep {x [from, to], z [from, to], top_m}, dressing [prop, ...]}: a slice of a
              standing set (sets/<name>), cut like a cake, with one of its `backdrop_options` (by place) behind
    poses     {name: {about, bones}}: poses of this moment only, written like motion/comic_poses.json
    props     {id: {run, file, scale} or {built: "tripod" | "teacup" | "softbox", ...}}: what can be held or stood
    toons     [{toon, name, run, version (lowpoly | midpoly), pose (a name, or "clip@seconds"),
                mark (one of the set's) or at [x, z], on (a block to stand on), facing_deg or faces (a toon,
                a mark or [x, z]), looks_at (a toon, a prop or [x, y, z]),
                holds [{prop, hand, grip}], beside [{prop, offset [to its right, forward], turn_deg}]}]
    free_props [{prop, at [x, z] | under (another prop), facing_deg | faces}]
    lights    [{name, kind, at, aim, power, color, size_m}]: the shelf's light, for the pictures
    cameras   {name: {round_deg, above_deg, lens_mm, frames, fstop, focus}} (fitted to what it frames) or {at, aim, lens_mm}
    stills    [camera, ...]: the pictures to take; the first is the card
    plinth    {margin_m, height_m, wood, toy_scale, label}: the wooden base and its brass plate
    basement  {wall, shelf, air}: the plain warm wall and shelf behind, in the pictures only

Everything is in the set's own axes: metres, y up, z toward the front. A
heading of 0 faces the front, 90 faces +x.

Plain Python: no Blender. `scripts/diorama/build_diorama.py` is the builder.
"""

import glob
import json
import math
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
import standing  # noqa: E402

FORMAT = "forge-diorama/1"
DIORAMAS = os.path.join(REPO, "dioramas")
COMIC_POSES = os.path.join(REPO, "motion", "comic_poses.json")
EPOCHS = os.path.join(REPO, "world", "epochs")
CLIP_AT = re.compile(r"^([a-z][a-z0-9_-]*)@([0-9]+(?:\.[0-9]+)?)s?$")
VERSIONS = ("lowpoly", "midpoly")
BUILT = ("tripod", "teacup", "softbox")
HANDS = ("right", "left")
GRIPS = ("top", "bottom", "centre", "front")
APART_M = 0.35  # two toons planned closer than this are standing in each other
BUDGET = {"bytes": 2_000_000, "triangles": 60_000}  # what the combined .glb may cost a phone


def folder(name):
    return os.path.join(DIORAMAS, name)


def names():
    """Every diorama that has a plan, by name."""
    return sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(DIORAMAS, "*", "diorama.json")))


def load(name):
    path = name if name.endswith(".json") else os.path.join(folder(name), "diorama.json")
    with open(path) as f:
        spec = json.load(f)
    spec["dir"] = os.path.dirname(os.path.abspath(path))
    return spec


def comic_poses():
    with open(COMIC_POSES) as f:
        return json.load(f)["poses"]


def poses_of(spec):
    """Every pose this diorama can name: the comic library's, and its own on top."""
    return dict(comic_poses(), **(spec.get("poses") or {}))


def read_pose(ref, poses):
    """("pose", its turns) or ("clip", clip, seconds); None when `ref` is neither."""
    if ref in poses:
        return ("pose", poses[ref])
    at = CLIP_AT.match(ref or "")
    return ("clip", at.group(1), float(at.group(2))) if at else None


def epoch(name):
    path = os.path.join(EPOCHS, "%s.json" % name)
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return json.load(f)


def find_run(runs, ending):
    """The newest run folder whose name ends with -<ending>, or None."""
    found = sorted(d for d in glob.glob(os.path.join(runs, "*-" + ending)) if os.path.isdir(d))
    return found[-1] if found else None


def toon_file(runs, toon, poses):
    """The rigged file a toon is posed from: <version>-walk.glb for a named pose, <version>-<clip>.glb for a clip moment."""
    run = find_run(runs, toon["run"])
    kind = read_pose(toon.get("pose"), poses)
    if not run or not kind:
        return None
    return os.path.join(run, "profiles", "%s-%s.glb" % (toon.get("version", "lowpoly"), "walk" if kind[0] == "pose" else kind[1]))


def prop_file(runs, prop):
    run = find_run(runs, prop["run"])
    return os.path.join(run, prop.get("file", "profiles/lowpoly.glb")) if run else None


def is_point(value, n):
    return isinstance(value, list) and len(value) == n and all(isinstance(v, (int, float)) for v in value)


def spot_of(spec, st, toon):
    """Where a toon stands: ([x, z], the floor's height there, the mark's own facing or None)."""
    facing = None
    if toon.get("mark"):
        m = standing.mark(st, toon["mark"])
        spot, facing = list(standing.stand_spot(m)), m.get("facing_deg")
        floor = float(m.get("floor_y", st.get("ground", {}).get("y", 0.0)))
    else:
        spot, floor = list(toon["at"]), float(st.get("ground", {}).get("y", 0.0))
    if toon.get("on"):
        floor = standing.top_of(standing.block_named(st, toon["on"]))
    return spot, floor, facing


def heading_to(a, b):
    """The heading that faces from [x, z] a to [x, z] b: 0 faces +z, 90 faces +x."""
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))


def facing_of(spec, st, toon):
    """The heading a toon's body faces, from its `facing_deg`, what it `faces`, or its mark."""
    spot, _, of_mark = spot_of(spec, st, toon)
    if "facing_deg" in toon:
        return float(toon["facing_deg"])
    target = toon.get("faces")
    if target is None:
        return float(of_mark or 0.0)
    if is_point(target, 2):
        return heading_to(spot, target)
    other = next((t for t in spec["toons"] if t["toon"] == target), None)
    if other is not None:
        return heading_to(spot, spot_of(spec, st, other)[0])
    return heading_to(spot, standing.stand_spot(standing.mark(st, target)))


def check(spec, runs=None):
    """(what is wrong with a diorama's plan, in words; what was looked at). With `runs`, also that every file it needs is there."""
    problems, seen = [], {}
    say = problems.append
    if spec.get("format") != FORMAT:
        say("format is %r, not %r" % (spec.get("format"), FORMAT))
        return problems, seen
    for key in ("name", "title", "caption", "epoch", "number", "set", "toons", "cameras", "stills", "plinth"):
        if key not in spec:
            say('diorama.json has no "%s"' % key)
    if problems:
        return problems, seen
    if os.path.basename(spec.get("dir", spec["name"])) != spec["name"]:
        say("it is named \"%s\" but kept in %s/" % (spec["name"], os.path.basename(spec["dir"])))
    if not isinstance(spec["number"], int):
        say("its number must be a whole number: the highest is the one on the front page")
    if len(spec["caption"]) > 160 or "\n" in spec["caption"]:
        say("the caption is one line, at most 160 letters")
    when = epoch(spec["epoch"])
    if when is None:
        say("the epoch \"%s\" has not been saved (world/epochs/)" % spec["epoch"])
    seen["epoch"] = when and "Epoch %s: %s" % (when.get("number"), when.get("title"))

    card = spec["set"]
    try:
        st = standing.load(card["name"])
    except (standing.SetProblem, OSError, KeyError) as e:
        say("the set: %s" % e)
        return problems, seen
    keep = card.get("keep") or {}
    if not (is_point(keep.get("x"), 2) and is_point(keep.get("z"), 2) and keep["x"][0] < keep["x"][1] and keep["z"][0] < keep["z"][1]):
        say("set.keep needs x [from, to] and z [from, to]: the slice of the set that stands on the base")
        return problems, seen
    options = [o["place"] for o in (st.get("backdrop_options") or {}).get("options") or []]
    if card.get("backdrop") and card["backdrop"] not in options:
        say("the %s has no backdrop of \"%s\" (it has: %s)" % (card["name"], card["backdrop"], ", ".join(options) or "none"))
    dressing = [d["prop"] for d in st.get("dressing") or []]
    for prop in card.get("dressing") or []:
        if prop not in dressing:
            say("the %s has no dressing called \"%s\"" % (card["name"], prop))
    seen["set"] = "%s, %.1f x %.1f m of it, in front of %s" % (card["name"], keep["x"][1] - keep["x"][0], keep["z"][1] - keep["z"][0], card.get("backdrop") or "no backdrop")

    poses = poses_of(spec)
    for name, pose in (spec.get("poses") or {}).items():
        if not isinstance(pose.get("bones"), dict) or not all(is_point(turn, 3) for turn in pose["bones"].values()):
            say("pose \"%s\": bones is {bone: [x, y, z] in degrees}" % name)

    props = spec.get("props") or {}
    for name, prop in props.items():
        if prop.get("built"):
            if prop["built"] not in BUILT:
                say("prop \"%s\": nothing builds a \"%s\" (it can be: %s)" % (name, prop["built"], ", ".join(BUILT)))
        elif not prop.get("run"):
            say("prop \"%s\" needs a run to come from, or something built" % name)
        elif runs and not os.path.isfile(prop_file(runs, prop) or ""):
            say("prop \"%s\": no %s in a run named for \"%s\" under %s" % (name, prop.get("file", "profiles/lowpoly.glb"), prop["run"], runs))

    inside = lambda x, z: keep["x"][0] <= x <= keep["x"][1] and keep["z"][0] <= z <= keep["z"][1]
    ids, spots, used = set(), {}, {}

    def use(prop, by):
        if prop not in props:
            say("%s: there is no prop called \"%s\"" % (by, prop))
        elif prop in used:
            say("prop \"%s\" is used twice: by %s and by %s" % (prop, used[prop], by))
        used[prop] = by

    for toon in spec["toons"]:
        who = toon.get("toon")
        if not who or who in ids or who in props:
            say("every toon needs a name of its own, not shared with a prop (%r)" % who)
            continue
        ids.add(who)
        if toon.get("version", "lowpoly") not in VERSIONS:
            say("toon \"%s\": version is lowpoly or midpoly, not \"%s\"" % (who, toon.get("version")))
        if read_pose(toon.get("pose"), poses) is None:
            say("toon \"%s\" has no pose \"%s\" (a name from motion/comic_poses.json or this diorama's own, or clip@seconds)" % (who, toon.get("pose")))
        elif runs and not os.path.isfile(toon_file(runs, toon, poses) or ""):
            say("toon \"%s\": no %s file for that pose in a run named for \"%s\" under %s" % (who, toon.get("version", "lowpoly"), toon.get("run"), runs))
        if toon.get("mark") and toon["mark"] not in st["marks"]:
            say("toon \"%s\": the %s has no mark called \"%s\"" % (who, card["name"], toon["mark"]))
            continue
        if not toon.get("mark") and not is_point(toon.get("at"), 2):
            say("toon \"%s\" needs a mark or a place to stand (at [x, z])" % who)
            continue
        if toon.get("on") and standing.block_named(st, toon["on"]) is None:
            say("toon \"%s\" stands on \"%s\", which is not a block of the %s" % (who, toon["on"], card["name"]))
            continue
        spot, floor, _ = spot_of(spec, st, toon)
        if not inside(*spot):
            say("toon \"%s\" stands at (%g, %g), off the slice of the set that is kept" % (who, spot[0], spot[1]))
        if toon.get("on") and standing.gap_to(standing.block_named(st, toon["on"]), *spot) > 0.0:
            say("toon \"%s\" is said to stand on the %s but is not over it" % (who, toon["on"]))
        spots[who] = spot
        for held in toon.get("holds") or []:
            use(held.get("prop"), "toon \"%s\"" % who)
            if held.get("hand") not in HANDS:
                say("toon \"%s\" holds \"%s\" in which hand? (right or left)" % (who, held.get("prop")))
            if not (held.get("grip", "top") in GRIPS or is_point(held.get("grip"), 3)):
                say("toon \"%s\": a grip is one of %s, or a point of the prop [x, y, z]" % (who, ", ".join(GRIPS)))
        for near in toon.get("beside") or []:
            use(near.get("prop"), "toon \"%s\"" % who)
            if not is_point(near.get("offset"), 2):
                say("toon \"%s\": what stands beside needs an offset [to its right, forward] in metres" % who)
    for toon in spec["toons"]:
        who = toon.get("toon")
        target = toon.get("faces")
        if target is not None and not (is_point(target, 2) or target in ids or target in st["marks"]):
            say("toon \"%s\" faces \"%s\", which is not a toon, a mark or a point [x, z]" % (who, target))
        target = toon.get("looks_at")
        if target is not None and not (is_point(target, 3) or (target in ids and target != who) or target in props):
            say("toon \"%s\" looks at \"%s\", which is not another toon, a prop or a point [x, y, z]" % (who, target))
    for i, a in enumerate(sorted(spots)):
        for b in sorted(spots)[i + 1:]:
            apart = math.dist(spots[a], spots[b])
            if apart < APART_M:
                say("toons \"%s\" and \"%s\" are planned %.2f m apart: standing in each other" % (a, b, apart))
    seen["toons"] = {t["toon"]: "%s, %s" % (t.get("version", "lowpoly"), t.get("pose")) for t in spec["toons"] if t.get("toon")}

    for free in spec.get("free_props") or []:
        use(free.get("prop"), "the free props")
        if free.get("under"):
            if free["under"] not in props:
                say("free prop \"%s\" stands under \"%s\", which is not a prop" % (free.get("prop"), free["under"]))
        elif not is_point(free.get("at"), 2):
            say("free prop \"%s\" needs a place (at [x, z]) or something to stand under" % free.get("prop"))
        elif not inside(*free["at"]):
            say("free prop \"%s\" stands off the slice of the set that is kept" % free.get("prop"))
    for name in props:
        if name not in used:
            say("prop \"%s\" is never held or stood anywhere" % name)
    seen["props"] = sorted(used)

    cameras = spec["cameras"]
    for name, cam in cameras.items():
        fitted = all(isinstance(cam.get(k), (int, float)) for k in ("round_deg", "above_deg"))
        if not fitted and not (is_point(cam.get("at"), 3) and is_point(cam.get("aim"), 3)):
            say("camera \"%s\" needs round_deg and above_deg (it is then fitted to what it frames), or at and aim" % name)
        for who in cam.get("frames") or []:
            if who not in ids and who not in props:
                say("camera \"%s\" frames \"%s\", which is not a toon or a prop" % (name, who))
        focus = cam.get("focus")
        if focus is not None and not (is_point(focus, 3) or focus in ids or focus in props):
            say("camera \"%s\" focuses on \"%s\", which is not a toon, a prop or a point" % (name, focus))
    if not spec["stills"] or any(name not in cameras for name in spec["stills"]):
        say("stills names the cameras to take pictures through (%s); the first is the card" % ", ".join(cameras))
    for light in spec.get("lights") or []:
        if not (light.get("name") and light.get("kind") in ("area", "spot", "sun", "point") and is_point(light.get("at"), 3) and isinstance(light.get("power"), (int, float))):
            say("light %r needs a name, a kind (area, spot, sun, point), at [x, y, z] and a power" % light.get("name"))
    plinth = spec["plinth"]
    if not all(isinstance(plinth.get(k), (int, float)) and plinth[k] > 0 for k in ("margin_m", "height_m")):
        say("the plinth needs a margin_m and a height_m")
    seen["cameras"] = list(cameras)
    return problems, seen


# ---- what was built ---------------------------------------------------------------


def glb_doc(path):
    """A .glb's JSON, read straight from the file."""
    with open(path, "rb") as f:
        f.read(12)
        size, _ = struct.unpack("<II", f.read(8))
        return json.loads(f.read(size))


def glb_facts(path):
    """What a built diorama's .glb holds: triangles, how it is packed, how its pictures are kept."""
    doc = glb_doc(path)
    prims = [p for m in doc.get("meshes") or [] for p in m["primitives"]]
    count = lambda p: doc["accessors"][p["indices"] if "indices" in p else p["attributes"]["POSITION"]]["count"] // 3
    return {
        "bytes": os.path.getsize(path),
        "meshes": len(doc.get("meshes") or []),
        "triangles": sum(count(p) for p in prims),
        "draco": bool(prims) and all("KHR_draco_mesh_compression" in (p.get("extensions") or {}) for p in prims),
        "pictures": sorted({i.get("mimeType", "?") for i in doc.get("images") or []}),
        "nodes": [n.get("name") for n in doc.get("nodes") or [] if (n.get("name") or "").split(":")[0] in ("toon", "prop", "set", "plinth")],
    }


def built(name):
    """A diorama's build record (dioramas/<name>/build.json), or None before `just diorama <name>`."""
    path = os.path.join(folder(name), "build.json")
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return json.load(f)


def card(spec):
    """A diorama as the gallery needs it: what the plate says, and the files that are there."""
    record = built(spec["name"]) or {}
    has = lambda rel: os.path.isfile(os.path.join(spec["dir"], rel))
    when = epoch(spec["epoch"]) or {}
    stills = [{"camera": s["camera"], "about": s.get("about"), "picture": s["picture"], "small": s["small"]}
              for s in record.get("stills") or [] if has(s["picture"]) and has(s["small"])]
    return {
        "name": spec["name"], "number": spec["number"], "title": spec["title"], "caption": spec["caption"],
        "epoch": {"name": spec["epoch"], "number": when.get("number"), "title": when.get("title")},
        "glb": "diorama.glb" if has("diorama.glb") else None,
        "bytes": os.path.getsize(os.path.join(spec["dir"], "diorama.glb")) if has("diorama.glb") else None,
        "triangles": (record.get("glb") or {}).get("triangles"),
        "card": "card.png" if has("card.png") else None,
        "stills": stills,
        "views": record.get("cameras") or {},
        "cast": [{"toon": t["toon"], "name": t.get("name") or t["toon"], "version": t.get("version", "lowpoly")} for t in spec["toons"]],
    }


def shelf():
    """Every diorama, newest first: the first is the one on the front page."""
    found = []
    for name in names():
        try:
            spec = load(name)
            found.append(card(spec))
        except (OSError, ValueError, KeyError):
            continue
    return sorted(found, key=lambda c: c["number"], reverse=True)


def front_page_files(name):
    """What the gallery fetches of a diorama when the front page opens, and what waits for a tap."""
    spec = load(name)
    it = card(spec)
    first = ([it["glb"]] if it["glb"] else []) + [s["small"] for s in it["stills"]]
    later = [s["picture"] for s in it["stills"]]
    size = lambda paths: sum(os.path.getsize(os.path.join(spec["dir"], p)) for p in paths)
    return {"first": {"files": len(first), "bytes": size(first), "list": first}, "on_a_tap": {"files": len(later), "bytes": size(later), "list": later}}


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("check", "list", "load"):
        sys.exit(__doc__.split("\n\n")[1])
    if args[0] == "list":
        for it in shelf():
            print("DIORAMA %d %s: \"%s\", %s%s" % (it["number"], it["name"], it["title"], "Epoch %s" % it["epoch"]["number"], "" if it["glb"] else " (not built yet: just diorama %s)" % it["name"]))
        return
    if args[0] == "load":
        files = front_page_files(args[1])
        for key, part in files.items():
            print("DIORAMA %s: %d files, %.2f MB" % (key.replace("_", " "), part["files"], part["bytes"] / 1e6))
            for path in part["list"]:
                print("DIORAMA   %7.1f kB  %s" % (os.path.getsize(os.path.join(folder(args[1]), path)) / 1e3, path))
        return
    runs = os.path.abspath(args[args.index("--runs") + 1]) if "--runs" in args else None
    wanted = [a for i, a in enumerate(args[1:], 1) if not a.startswith("--") and args[i - 1] != "--runs"] or names()
    failed = 0
    for name in wanted:
        try:
            spec = load(name)
        except (OSError, ValueError) as e:
            print("DIORAMA PROBLEM %s: %s" % (name, e))
            failed += 1
            continue
        problems, seen = check(spec, runs if runs and os.path.isdir(runs) else None)
        for key in ("epoch", "set"):
            if seen.get(key):
                print("DIORAMA %s %s: %s" % (name, key, seen[key]))
        for who, how in (seen.get("toons") or {}).items():
            print("DIORAMA %s toon %s: %s" % (name, who, how))
        for line in problems:
            print("DIORAMA PROBLEM %s: %s" % (name, line))
        print("DIORAMA %s: %s" % (name, "sound" if not problems else "%d problems" % len(problems)))
        failed += bool(problems)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
