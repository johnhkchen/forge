"""Try the comic code that needs no Blender, no model and no runs: the lettering, the checks on a comic's
panels, how a pose is read, and the adapter for a set.json.

    python3 scripts/comic/test_comic.py

Prints one line per check and "all passed" or how many failed. Part of `just check`.
"""

import json
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kit  # noqa: E402
import lettering  # noqa: E402

FAILED = []


def check(label, ok, detail=""):
    print("  %s  %s%s" % ("ok  " if ok else "FAIL", label, "  (%s)" % (detail,) if detail and not ok else ""))
    if not ok:
        FAILED.append(label)


def two_heads(size=900):
    """A two-shot as the renderer reports it: a head at left, a head at right, both in the lower half."""
    return {"size": [size, size],
            "heads": {"lincoln": {"center": [250.0, 430.0], "radius": 62.0, "mouth": [282.0, 452.0], "top": [250.0, 360.0]},
                      "roosevelt": {"center": [650.0, 520.0], "radius": 70.0, "mouth": [612.0, 545.0], "top": [650.0, 445.0]}},
            "bodies": {"lincoln": [150, 360, 360, 900], "roosevelt": [540, 445, 780, 900]}}


def lettering_rules(meta, panel, layout, label):
    """The rules every lettered panel keeps, whatever the picture."""
    wide, tall = meta["size"]
    heads = meta["heads"]
    balloons = layout["balloons"]
    check("%s: every line got a balloon" % label, len(balloons) == len(panel.get("lines") or []) and not layout["problems"], layout["problems"])
    boxes = [b["box"] for b in balloons] + ([layout["caption"]["box"]] if layout.get("caption") else [])
    check("%s: balloons and caption stay inside the panel" % label,
          all(b[0] >= 0 and b[1] >= 0 and b[0] + b[2] <= wide and b[1] + b[3] <= tall for b in boxes), boxes)
    check("%s: no balloon covers a face" % label,
          not any(lettering.box_hits_circle(b, f["center"], f["radius"]) for b in boxes for f in heads.values()))
    check("%s: no two balloons touch" % label,
          not any(lettering.overlap(a, b) for i, a in enumerate(boxes) for b in boxes[i + 1:]))
    for b in balloons:
        head = heads[b["who"]]
        tip = b["tail"][1]
        reach = math.hypot(tip[0] - head["center"][0], tip[1] - head["center"][1])
        check("%s: %s's tail ends at its own head, just off the face (%.2f head radii from its middle)" % (label, b["who"], reach / head["radius"]),
              head["radius"] <= reach <= head["radius"] * 1.6)
        others = [f for who, f in heads.items() if who != b["who"]]
        check("%s: %s's tail is nearer its speaker than anyone else" % (label, b["who"]),
              all(math.hypot(tip[0] - f["center"][0], tip[1] - f["center"][1]) > reach for f in others))
        root = [(b["tail"][0][0] + b["tail"][2][0]) / 2, (b["tail"][0][1] + b["tail"][2][1]) / 2]
        toward = (head["center"][0] - root[0]) * (tip[0] - root[0]) + (head["center"][1] - root[1]) * (tip[1] - root[1])
        check("%s: %s's tail points toward the head, not away" % (label, b["who"]), toward > 0)
        check("%s: %s's tail crosses nobody else's face" % (label, b["who"]),
              not any(lettering.segment_hits_circle(root, tip, f["center"], f["radius"]) for f in others))
    centers = [(b["box"][1] + b["box"][3] / 2, b["box"][0] + b["box"][2] / 2) for b in balloons]
    check("%s: balloons read in order (a later one is never above and left of an earlier one)" % label,
          all(not (later[0] < earlier[0] - 1 and later[1] < earlier[1]) for i, earlier in enumerate(centers) for later in centers[i + 1:]), centers)


def test_lettering():
    print("lettering: balloons keep off faces, tails point at heads")
    meta = two_heads()
    panel = {"lines": [{"who": "roosevelt", "says": "Bully! Shall we wrestle, Abe?", "how": "shout"},
                       {"who": "lincoln", "says": "I reckon I'm already winning.", "how": "say"}],
             "caption": "Springfield, a slow afternoon.", "sfx": "THUD!"}
    layout = lettering.letter(meta, panel)
    lettering_rules(meta, panel, layout, "two-shot")
    check("two-shot: the type was not shrunk for two short lines", layout["shrunk"] == 0, layout["shrunk"])
    check("two-shot: the caption sits at the top, clear of both faces", layout["caption"]["box"][1] < 60, layout["caption"])
    check("two-shot: the sound effect found a corner clear of faces and balloons", layout["sfx"]["clear"], layout["sfx"])
    svg = lettering.to_svg(layout, meta["size"])
    check("the words stay text in the SVG, in the comic font's own element",
          svg.count("<text") >= 4 and "Bully! Shall we" in svg and "<svg" in svg and 'class="sfx"' in svg)
    check("a thought is drawn as bubbles, speech as a pointed tail",
          "<circle" in lettering.to_svg(lettering.letter(meta, {"lines": [{"who": "lincoln", "says": "Hm.", "how": "think"}]}), meta["size"])
          and "<polygon" in svg)

    close = {"size": [900, 900], "heads": {"ninja": {"center": [450.0, 560.0], "radius": 250.0, "mouth": [450.0, 680.0], "top": [450.0, 300.0]}},
             "bodies": {"ninja": [100, 300, 800, 900]}}
    line = {"lines": [{"who": "ninja", "says": "Nobody saw that.", "how": "think"}]}
    lettering_rules(close, line, lettering.letter(close, line), "close-up")

    wordy = {"lines": [{"who": "ninja", "says": "word " * 40, "how": "say"}, {"who": "ninja", "says": "more " * 40, "how": "say"},
                       {"who": "ninja", "says": "and more " * 30, "how": "say"}]}
    crowded = lettering.letter(close, wordy)
    check("a panel with far too many words is reported, not lettered over the face",
          crowded["problems"] and "too wordy" in crowded["problems"][0] and not crowded["balloons"], crowded["problems"])

    # Through someone's own eyes: their head is not in the picture, so their thought has nowhere to point.
    own = {"size": [900, 560], "heads": {}, "bodies": {}}
    seen = {"lines": [{"who": "ninja", "says": "Slow tracking shot along the ledge.", "how": "think"}, {"who": "ninja", "says": "Let it breathe.", "how": "think"}]}
    voiced = lettering.letter(own, seen)
    bars = voiced["balloons"]
    check("a thought with no head to point at becomes a voice: a bar along the bottom with no tail",
          len(bars) == 2 and all(b["how"] == "voice" and b["tail"] is None and b["box"][1] > 560 * 0.45 for b in bars) and not voiced["problems"], bars)
    check("two voice bars stack with the first one read on top, centered, inside the panel",
          bars[0]["box"][1] + bars[0]["box"][3] <= bars[1]["box"][1] and all(abs(b["box"][0] * 2 + b["box"][2] - 900) < 2 and b["box"][1] + b["box"][3] < 560 for b in bars), bars)
    drawn = lettering.to_svg(voiced, own["size"])
    check("the voice is still text, with no tail and no thought bubbles", 'class="voice"' in drawn and "<polygon" not in drawn and "<circle" not in drawn and "Let it breathe." in drawn)
    high = {"size": [900, 560], "heads": {"lincoln": {"center": [200.0, 70.0], "radius": 55.0, "mouth": [220.0, 90.0], "top": [200.0, 10.0]}}, "bodies": {}}
    low = lettering.letter(high, {"lines": [], "caption": "Meanwhile."})
    check("a caption moves to the bottom when a face is where it would go", low["caption"]["box"][1] > 400, low["caption"])
    check("text is measured from the font's own letter widths (an M is wider than an i)",
          lettering.text_width("MMMM", 30) > 2.5 * lettering.text_width("iiii", 30))
    check("long text wraps to lines that fit", all(lettering.text_width(l, 30) <= 300 for l in lettering.wrap("the quick brown fox jumps over the lazy dog", 30, 300)))


KIT = {
    "cast": [
        {"id": "lincoln", "name": "Lincoln", "about": "", "poses": [{"name": "stand", "about": ""}, {"name": "flex", "about": ""}], "moments": [],
         "clips": ["run", "walk"], "expressions": ["neutral", "happy", "smug"]},
        {"id": "ninja", "name": "Ninja", "about": "", "poses": [{"name": "stand", "about": ""}],
         "moments": [{"name": "hero:draw", "about": "", "second": 11.3}], "clips": ["hero", "walk"], "expressions": [], "silent": True,
         "shot_clips": [{"clip": "hero", "seconds": 12.0, "beats": [], "places": ["rooftop"]}]},
    ],
    "places": [{"name": "ring", "about": "", "marks": [], "cameras": []}, {"name": "rooftop", "about": "", "marks": [], "cameras": []}, {"name": "studio", "about": "", "marks": ["host", "guest"], "cameras": ["wide", "desk"]}],
    "framings": [],
}


def panel(**changes):
    base = {"framing": "two-shot", "place": "ring", "camera": None, "shape": "square",
            "cast": [{"who": "lincoln", "at": "left", "facing": "right", "pose": "stand", "expression": "smug"}],
            "lines": [{"who": "lincoln", "says": "Well.", "how": "say"}], "caption": None, "sfx": None}
    base.update(changes)
    return base


def test_checks():
    print("checks: a comic's panels against the kit")
    check("a sound panel has no problems", kit.problems({"panels": [panel()]}, KIT) == [])
    cases = [
        ("a pose the character does not have", panel(cast=[{"who": "lincoln", "at": "left", "facing": "right", "pose": "moonwalk", "expression": "smug"}]), "no pose"),
        ("an expression it does not have", panel(cast=[{"who": "lincoln", "at": "left", "facing": "right", "pose": "stand", "expression": "furious"}]), "no expression"),
        ("somebody not in the cast", panel(cast=[{"who": "washington", "at": "left", "facing": "right", "pose": "stand", "expression": "neutral"}], lines=[]), "nobody called"),
        ("a place that is not there", panel(place="moon"), "no place"),
        ("a line from someone not in the panel", panel(lines=[{"who": "ninja", "says": "Hi.", "how": "say"}]), "not in the panel"),
        ("a camera the place does not have", panel(camera="crane"), "no camera"),
        ("a spot that is not a spot", panel(cast=[{"who": "lincoln", "at": "ceiling", "facing": "right", "pose": "stand", "expression": "smug"}]), "stands at"),
        ("a clip the character does not have", panel(cast=[{"who": "lincoln", "at": "left", "facing": "right", "pose": "hero@2.0", "expression": "smug"}]), "no clip"),
    ]
    for label, bad, says in cases:
        found = kit.problems({"panels": [bad]}, KIT)
        check("%s is caught" % label, any(says in f for f in found), found)
    member = KIT["cast"][1]
    check("a pose reads by name, a moment by name, a clip moment as clip@seconds",
          kit.read_pose("stand", member) == ("pose", "stand") and kit.read_pose("hero:draw", member) == ("moment", "hero:draw")
          and kit.read_pose("hero@7.25", member) == ("clip", "hero", 7.25) and kit.read_pose("walk@0.5s", member) == ("clip", "walk", 0.5))
    check("a character with no drawn faces may be asked for any expression (it keeps its own)",
          kit.problems({"panels": [panel(cast=[{"who": "ninja", "at": "center", "facing": "camera", "pose": "stand", "expression": "angry"}], lines=[])]}, KIT) == [])
    check("a set's mark and camera are accepted by name",
          kit.problems({"panels": [panel(place="studio", camera="desk", cast=[{"who": "lincoln", "at": "guest", "facing": "left", "pose": "stand", "expression": "happy"}])]}, KIT) == [])
    eyes = panel(framing="pov", look="hands", place="rooftop", lines=[{"who": "ninja", "says": "Hm.", "how": "think"}],
                 cast=[{"who": "ninja", "at": "there", "facing": "camera", "pose": "hero@7.9", "expression": "neutral"}])
    check("a pov panel of a shot's clip moment, kept \"there\", with a thought, is sound", kit.problems({"panels": [eyes]}, KIT) == [], kit.problems({"panels": [eyes]}, KIT))
    spoken = dict(eyes, lines=[{"who": "ninja", "says": "Hello!", "how": "say"}])
    check("a character who never speaks is caught speaking", any("never speaks aloud" in f for f in kit.problems({"panels": [spoken]}, KIT)))
    check("\"there\" is refused away from the clip's own place, and a look that is not a look is caught",
          any("stands at \"there\"" in f for f in kit.problems({"panels": [dict(eyes, place="ring")]}, KIT))
          and any("look" in f for f in kit.problems({"panels": [dict(eyes, look="sideways")]}, KIT)))
    poses = kit.poses()
    check("the pose library has the poses a talk needs, each with a sentence about it",
          {"stand", "talk", "point", "shrug", "flex"} <= set(poses) and all(p.get("about") and p.get("bones") is not None for p in poses.values()), sorted(poses))
    bones = {"hips", "spine", "chest", "neck", "head", "shoulder", "upper_arm", "forearm", "hand", "thigh", "shin", "foot", "toe"}
    strays = sorted({b for p in poses.values() for b in p["bones"] if (b[:-2] if b.endswith(("_l", "_r")) else b) not in bones})
    check("every pose turns only bones a character has", not strays, strays)


def test_set_adapter():
    print("sets: a set.json comes through the adapter as marks, cameras and a backdrop")
    with tempfile.TemporaryDirectory() as root:
        folder = os.path.join(root, "studio")
        os.makedirs(folder)
        with open(os.path.join(folder, "set.glb"), "w") as f:
            f.write("")
        with open(os.path.join(folder, "set.json"), "w") as f:
            json.dump({"name": "studio", "about": "a talk-show studio",
                       "marks": [{"name": "host", "kind": "sit", "at": [0.6, 0.0, 0.45], "facing_deg": -30}, {"name": "guest", "at": [-0.6, 0.0, 0.0]}],
                       "cameras": {"wide": {"position": [0, -5, 1.6], "look_at": [0, 0, 1.1], "lens": 35}},
                       "backdrops": ["set.glb"], "lights": [{"name": "key"}]}, f)
        place = kit.from_set_json(folder)
        check("marks keep their spot, facing and kind", place["marks"]["host"] == {"at": [0.6, 0.0, 0.45], "facing_deg": -30.0, "kind": "sit"}
              and place["marks"]["guest"]["kind"] == "stand", place["marks"])
        check("a named camera keeps where it is, what it looks at and its lens",
              place["cameras"]["wide"]["at"] == [0, -5, 1.6] and place["cameras"]["wide"]["lens"] == 35.0, place["cameras"])
        check("the backdrop is the set's own .glb", place["backdrop"] == [os.path.join(folder, "set.glb")], place["backdrop"])
    check("a stand-in names no marks or cameras of its own: it is not a set format",
          all("marks" not in s and "cameras" not in s for s in kit.STAND_INS.values()))


def main():
    test_lettering()
    test_checks()
    test_set_adapter()
    print("comic: %s" % ("%d check(s) failed: %s" % (len(FAILED), "; ".join(FAILED)) if FAILED else "all passed"))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
