"""What a comic can be made from, read off the disk: who is in the cast, the poses and expressions each has,
the places a panel can be set, and the framings. The script step shows this to Opus and checks its script
against it; the panel renderer reads the same thing, so the two cannot disagree.

    python3 scripts/comic/kit.py [--runs runs] [--out comics/kit.json]

Plain Python, no Blender. Also the one place that knows about places:

  - a set, once sets land: sets/<name>/set.json, read by `from_set_json` (marks, named cameras, backdrop).
    That function is the adapter: when the set format settles, it is the only thing here to change.
  - until then, a stand-in from STAND_INS below: a finished run's .glb (the wrestling ring) or a shot's blocks
    (the rooftop) as a backdrop, three spots to stand on, and no cameras of its own. This is not a set format
    and should not grow into one; delete a stand-in when its set exists.
  - or a flat background for a talk panel.
"""

import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
COMICS = os.path.join(REPO, "comics")
CAST_FILE = os.path.join(COMICS, "cast.json")
CAST_DIR = os.path.join(COMICS, "cast")
BACKDROPS_DIR = os.path.join(COMICS, "backdrops")
POSES_FILE = os.path.join(REPO, "motion", "comic_poses.json")
SHOT_POSES_FILE = os.path.join(REPO, "motion", "poses.json")

EXPRESSIONS = ["neutral", "happy", "angry", "surprised", "sad", "smug", "talking", "shouting"]
SHEET_GRID = (4, 2)  # the expression sheet: columns, rows, read left to right, top to bottom
FRAMINGS = {
    "wide": "everyone head to toe with the place around them",
    "two-shot": "everyone in the panel from the hips up",
    "single": "one character from the chest up (the first one listed)",
    "close-up": "one character's face (the first one listed)",
}
SPOTS = ["left", "center", "right"]
FACINGS = ["left", "right", "camera", "away"]
HOWS = ["say", "think", "shout", "whisper"]
SHAPES = {"square": (1.0, 1.0), "wide": (1.0, 0.62), "tall": (1.0, 1.3)}
THERE = "there"  # a spot: where the clip itself has the character at that moment

# Stand-ins until sets/<name>/set.json exists. Colors are the page's (sRGB hex), top to bottom.
STAND_INS = {
    "ring": {
        "about": "inside the ropes of an 1890s wrestling ring: canvas mat, wooden corner posts",
        "backdrop": {"run": "1890s-wrestling-ring", "file": "profiles/lowpoly.glb"},
        "front_deg": 0.0, "center": [0.0, 0.55], "apart_m": 0.95, "camera_within_m": 2.4,
        "sky": ["#f3e3c3", "#e2c492"],
    },
    "rooftop": {
        "about": "a flat city rooftop at night with a low wall across it",
        "backdrop": {"shot": "hero-rooftop"},
        "front_deg": 140.0, "center": [3.4, 4.3], "apart_m": 1.1,
        "sky": ["#1b2a52", "#6a5a8c"],
    },
    "plain": {"about": "no place at all: a flat warm background, for a talk panel", "sky": ["#f2efe9", "#e9e2d4"]},
    "dusk": {"about": "no place at all: a flat evening-blue background, for a quiet or night panel", "sky": ["#2a3a66", "#7a6a96"]},
    "burst": {"about": "no place at all: a flat bright yellow background, for a punchline or a shock", "sky": ["#ffd95e", "#ffb347"]},
}


def read_json(path):
    with open(path) as f:
        return json.load(f)


def load_cast():
    return read_json(CAST_FILE)["cast"]


def find_run(runs, ending):
    """The newest run folder whose name ends with -<ending>, or None."""
    if not os.path.isdir(runs):
        return None
    found = sorted(f for f in os.listdir(runs) if f.endswith("-" + ending) and os.path.isdir(os.path.join(runs, f)))
    return os.path.join(runs, found[-1]) if found else None


def data_root(runs):
    """Where shots/ and sets/ sit: next to the runs folder."""
    return os.path.dirname(os.path.abspath(runs))


def clip_file(runs, entry, clip):
    """The rigged file that holds a clip ("walk" also serves the hand-written poses), or None."""
    run = find_run(runs, entry["run"])
    if not run:
        return None
    versions = [entry.get("version", "lowpoly"), "lowpoly"]
    for version in versions:
        path = os.path.join(run, "profiles", "%s-%s.glb" % (version, clip))
        if os.path.exists(path):
            return path
    return None


def shot_plan(runs, shot):
    path = os.path.join(data_root(runs), "shots", shot, "plan.json")
    return read_json(path) if os.path.exists(path) else None


def moments_of(runs, entry):
    """Named moments of a character's clips: each pose a shot was built from, at the second the shot reaches it."""
    about = read_json(SHOT_POSES_FILE)["poses"] if os.path.exists(SHOT_POSES_FILE) else {}
    found = []
    for clip, made in sorted((entry.get("clips") or {}).items()):
        if not made.get("shot") or not clip_file(runs, entry, clip):
            continue
        plan = shot_plan(runs, made["shot"])
        if not plan:
            continue
        seen = set()
        for move in plan.get("moves", []):
            pose = move.get("pose")
            if not pose or pose in seen:
                continue
            seen.add(pose)
            found.append({"name": "%s:%s" % (clip, pose), "clip": clip, "second": round(move["frame"] / float(plan.get("fps", 30)), 3),
                          "about": (about.get(pose) or {}).get("about", pose.replace("_", " ")), "shot": made["shot"]})
    return found


def expressions_of(who):
    folder = os.path.join(CAST_DIR, who, "faces")
    if not os.path.isdir(folder):
        return []
    return [e for e in EXPRESSIONS if os.path.exists(os.path.join(folder, e + ".png"))]


def poses():
    return read_json(POSES_FILE)["poses"]


def first(record, names, default=None):
    for name in names:
        if isinstance(record, dict) and record.get(name) is not None:
            return record[name]
    return default


def named(things):
    """A set's marks or cameras, written as {"name": {...}} or as [{"name": ..., ...}]: always [(name, record)]."""
    if isinstance(things, dict):
        return [(name, record if isinstance(record, dict) else {"at": record}) for name, record in things.items()]
    return [(first(t, ["name", "id"], "mark %d" % (i + 1)), t) for i, t in enumerate(things or []) if isinstance(t, dict)]


def from_set_json(folder):
    """THE ADAPTER POINT for standing sets. Turns sets/<name>/set.json into what a panel needs:

        {"about", "marks": {name: {"at": [x, y, z], "facing_deg", "kind"}}, "cameras": {name: {"at", "look_at", "lens"}},
         "backdrop": [paths of .glb files], "sky": [top, bottom]}

    The set format is the sets branch's to define. This reads the fields it was described with (marks to stand,
    sit or lean at, named cameras, lights, backdrops) under the names they are most likely to have, and nothing
    else in the comics code looks inside set.json."""
    doc = read_json(os.path.join(folder, "set.json"))
    marks = {}
    for name, record in named(first(doc, ["marks"], [])):
        marks[name] = {"at": list(first(record, ["at", "position", "location", "xyz"], [0.0, 0.0, 0.0])),
                       "facing_deg": float(first(record, ["facing_deg", "facing", "heading_deg", "heading", "yaw_deg"], 0.0) or 0.0),
                       "kind": first(record, ["kind", "type", "pose"], "stand")}
    cameras = {}
    for name, record in named(first(doc, ["cameras"], [])):
        cameras[name] = {"at": list(first(record, ["at", "position", "location", "eye"], [0.0, -4.0, 1.5])),
                         "look_at": list(first(record, ["look_at", "target", "aim"], [0.0, 0.0, 1.2])),
                         "lens": float(first(record, ["lens", "lens_mm", "focal_mm"], 50.0)),
                         "about": first(record, ["about", "framing", "note"], "")}
    files = []
    for piece in first(doc, ["backdrops", "backdrop", "pieces", "files"], []) or []:
        path = piece if isinstance(piece, str) else first(piece, ["glb", "file", "path"])
        if path and path.endswith(".glb"):
            files.append(path if os.path.isabs(path) else os.path.join(folder, path))
    for name in ("set.glb", "backdrop.glb"):
        if not files and os.path.exists(os.path.join(folder, name)):
            files.append(os.path.join(folder, name))
    sky = first(doc, ["sky", "background"], None)
    return {"about": first(doc, ["about", "description"], os.path.basename(folder)), "marks": marks, "cameras": cameras,
            "backdrop": files, "sky": sky if isinstance(sky, list) else ["#f2efe9", "#e9e2d4"], "set": folder}


def places(runs):
    """Every place a panel can name: {name: record}. A set wins over a stand-in of the same name."""
    found = {}
    for root in (os.path.join(REPO, "sets"), os.path.join(data_root(runs), "sets")):
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            if os.path.exists(os.path.join(root, name, "set.json")):
                found[name] = from_set_json(os.path.join(root, name))
    for name, stand_in in STAND_INS.items():
        if name in found:
            continue
        backdrop = stand_in.get("backdrop") or {}
        if backdrop.get("run"):
            run = find_run(runs, backdrop["run"])
            path = os.path.join(run, backdrop["file"]) if run else None
            if not path or not os.path.exists(path):
                continue
        if backdrop.get("shot") and not os.path.exists(os.path.join(data_root(runs), "shots", backdrop["shot"], "motion.glb")):
            continue
        found[name] = dict(stand_in, stand_in=True, marks={}, cameras={})
    for name, place in found.items():  # a painted backdrop, if one was made for the place (baml run backdrop)
        if os.path.exists(os.path.join(BACKDROPS_DIR, name + ".png")):
            place["sky_image"] = "backdrops/%s.png" % name
    return found


def kit(runs):
    """What the script step is told and checks against."""
    library = poses()
    cast = []
    for who, entry in load_cast().items():
        if not clip_file(runs, entry, "walk"):
            continue
        clips = sorted(c for c in (entry.get("clips") or {}) if clip_file(runs, entry, c))
        cast.append({
            "id": who, "name": entry["name"], "about": entry["about"],
            "poses": [{"name": name, "about": pose["about"]} for name, pose in library.items()],
            "moments": [{"name": m["name"], "about": m["about"], "place": STAND_IN_OF_SHOT.get(m["shot"], "")} for m in moments_of(runs, entry)],
            "clips": clips,
            "expressions": expressions_of(who),
        })
    spots = []
    for name, place in places(runs).items():
        spots.append({"name": name, "about": place["about"], "marks": sorted(place.get("marks") or {}),
                      "cameras": sorted(place.get("cameras") or {})})
    return {"cast": cast, "places": spots, "framings": [{"name": n, "about": a} for n, a in FRAMINGS.items()]}


STAND_IN_OF_SHOT = {s["backdrop"]["shot"]: name for name, s in STAND_INS.items() if (s.get("backdrop") or {}).get("shot")}

# "hero@7.25": 7.25 seconds into the clip "hero".
CLIP_AT = re.compile(r"^([a-z][a-z0-9_-]*)@([0-9]+(?:\.[0-9]+)?)s?$")


def read_pose(ref, member):
    """What a panel's pose means for one cast member (an entry of kit()["cast"]):
    ("pose", name), ("clip", clip, second) or raises ValueError saying what is wrong."""
    if any(p["name"] == ref for p in member["poses"]):
        return ("pose", ref)
    if any(m["name"] == ref for m in member["moments"]):
        return ("moment", ref)
    at = CLIP_AT.match(ref or "")
    if at:
        if at.group(1) not in member["clips"]:
            raise ValueError("%s has no clip \"%s\" (it has: %s)" % (member["id"], at.group(1), ", ".join(member["clips"]) or "none"))
        return ("clip", at.group(1), float(at.group(2)))
    raise ValueError("%s has no pose \"%s\"" % (member["id"], ref))


def problems(comic, have):
    """What is wrong with a comic's panels, in plain words; empty when it can be drawn. `have` is kit()."""
    wrong = []
    cast = {m["id"]: m for m in have["cast"]}
    spots = {p["name"]: p for p in have["places"]}
    panels = comic.get("panels") or []
    if not panels:
        wrong.append("there are no panels")
    for n, panel in enumerate(panels, 1):
        tag = "panel %d" % n
        if panel.get("framing") not in FRAMINGS:
            wrong.append("%s: framing \"%s\" is not one of %s" % (tag, panel.get("framing"), ", ".join(FRAMINGS)))
        place = spots.get(panel.get("place"))
        if place is None:
            wrong.append("%s: no place \"%s\" (there is: %s)" % (tag, panel.get("place"), ", ".join(sorted(spots))))
        if panel.get("camera") and place is not None and panel["camera"] not in place["cameras"]:
            wrong.append("%s: %s has no camera \"%s\"" % (tag, panel["place"], panel["camera"]))
        members = panel.get("cast") or []
        if not members:
            wrong.append("%s: nobody is in it" % tag)
        here = set()
        for member in members:
            who = member.get("who")
            if who not in cast:
                wrong.append("%s: nobody called \"%s\" (there is: %s)" % (tag, who, ", ".join(sorted(cast))))
                continue
            if who in here:
                wrong.append("%s: %s is in it twice" % (tag, who))
            here.add(who)
            try:
                read_pose(member.get("pose"), cast[who])
            except ValueError as error:
                wrong.append("%s: %s" % (tag, error))
            expression = member.get("expression") or "neutral"
            if cast[who]["expressions"] and expression not in cast[who]["expressions"]:
                wrong.append("%s: %s has no expression \"%s\" (it has: %s)" % (tag, who, expression, ", ".join(cast[who]["expressions"])))
            at = member.get("at", "center")
            marks = (place or {}).get("marks") or []
            if isinstance(at, str) and at not in SPOTS and at != THERE and at not in marks:
                wrong.append("%s: %s stands at \"%s\", which is not left, center, right%s" % (tag, who, at, "".join(", " + m for m in marks)))
            if member.get("facing", "camera") not in FACINGS:
                wrong.append("%s: %s faces \"%s\", which is not one of %s" % (tag, who, member.get("facing"), ", ".join(FACINGS)))
        for line in panel.get("lines") or []:
            if line.get("who") not in here:
                wrong.append("%s: %s has a line but is not in the panel" % (tag, line.get("who")))
            if line.get("how", "say") not in HOWS:
                wrong.append("%s: a line is spoken \"%s\", which is not one of %s" % (tag, line.get("how"), ", ".join(HOWS)))
        if panel.get("shape", "square") not in SHAPES:
            wrong.append("%s: shape \"%s\" is not one of %s" % (tag, panel.get("shape"), ", ".join(SHAPES)))
    return wrong


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", default=os.path.join(REPO, "runs"))
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    made = kit(os.path.abspath(args.runs))
    text = json.dumps(made, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w") as f:
            f.write(text + "\n")
        print("KIT %s: %d in the cast, %d places" % (args.out, len(made["cast"]), len(made["places"])))
    else:
        print(text)
