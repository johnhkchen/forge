"""Tries the screen test (screen.py) on robots drawn here, with no model and no Blender: a good one, and one each
with a fault the screen must catch.

    python3 scripts/casting/test_screen.py      (runs itself again with Pillow, numpy and scipy through uv if this
                                                 Python has not got them)

What it shows:
  outline      the figure is found on a shaded grey background, a gap under a band over the head stays background
  builds       a T-pose scores high; arms down, or a figure touching the frame's edge, score lower
  face         two lamp eyes on a dark plate are found at the crew camera's size; a face with no plate is not
  colours      a robot in the breakdown's colours matches them; one in other colours does not
  flags        an antenna, a shadow round the feet, and something held each get a flag
  ranking      the good robot comes first, and every file the page reads is written
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

try:
    import numpy as np
    from PIL import Image, ImageDraw
    import scipy  # noqa: F401
except ImportError:
    if os.environ.get("FORGE_SCREEN_TEST_AGAIN"):
        raise
    sys.exit(subprocess.call(["uv", "run", "--no-project", "--python", "3.12", "--with", "pillow", "--with", "numpy", "--with", "scipy",
                              "python", os.path.abspath(__file__)], env=dict(os.environ, FORGE_SCREEN_TEST_AGAIN="1")))

sys.path.insert(0, HERE)
import screen  # noqa: E402

MUSTARD, BLUE, CHARCOAL, CREAM, RED = (224, 165, 38), (68, 103, 155), (43, 42, 46), (242, 230, 200), (200, 68, 47)


def check(what, ok, said=""):
    print("    %s  %s%s" % ("ok    " if ok else "FAILED", what, " (%s)" % said if said else ""))
    if not ok:
        raise AssertionError(what)


def robot(path, arms="out", eyes=True, colours=True, antenna=False, shadow=False, held=False, band=False, edge=False, paint=None):
    """A toy robot 1024 pixels square on a softly shaded grey: box head, dark face plate, two lamp eyes, a grille, a
    barrel chest with a red dial, posts for limbs, a ball at each joint."""
    size = 1024
    ys, xs = np.mgrid[0:size, 0:size]
    grey = (205 - 18 * ys / size - 6 * xs / size).astype(np.uint8)
    img = Image.fromarray(np.stack([grey, grey, grey + 2], -1))
    d = ImageDraw.Draw(img)
    body, limb = paint or ((MUSTARD, BLUE) if colours else ((120, 160, 90), (150, 90, 160)))
    cx = size // 2
    if shadow:
        d.ellipse((cx - 300, 860, cx + 300, 960), fill=(176, 176, 178))
    d.rectangle((cx - 150, 150, cx + 150, 400), fill=body)                       # head
    if eyes:
        d.rectangle((cx - 120, 190, cx + 120, 370), fill=CHARCOAL)                # face plate
        for ex in (cx - 65, cx + 65):
            d.ellipse((ex - 38, 220, ex + 38, 296), fill=CREAM)                    # lamp eyes
        for gy in (318, 336, 354):
            d.rectangle((cx - 50, gy, cx + 50, gy + 8), fill=CREAM)               # grille
    if antenna:
        d.rectangle((cx - 6, 60, cx + 6, 150), fill=body)
        d.ellipse((cx - 22, 40, cx + 22, 84), fill=RED)
    if band:
        d.arc((cx - 180, 100, cx + 180, 420), 180, 360, fill=CHARCOAL, width=22)
    d.rectangle((cx - 50, 390, cx + 50, 430), fill=limb)                          # neck
    d.ellipse((cx - 170, 410, cx + 170, 700), fill=body)                         # barrel chest
    d.ellipse((cx - 30, 520, cx + 30, 580), fill=RED)                            # dial
    reach = 500 if edge else 420
    if arms == "out":
        d.rectangle((cx - reach, 450, cx + reach, 495), fill=limb)
        for side in (-1, 1):
            d.ellipse((cx + side * 190 - 30, 442, cx + side * 190 + 30, 502), fill=limb)
            hx = cx + side * reach
            d.rectangle((hx - 30 if side > 0 else hx - 10, 430, hx + 10 if side > 0 else hx + 30, 515), fill=CHARCOAL)
        if held:
            d.rectangle((cx + reach - 40, 300, cx + reach + 20, 640), fill=(230, 230, 230))
            d.rectangle((cx + reach - 35, 305, cx + reach + 15, 635), fill=(30, 30, 30))
    else:
        for side in (-1, 1):
            d.rectangle((cx + side * 200 - 22, 440, cx + side * 200 + 22, 760), fill=limb)
    for side in (-1, 1):
        d.rectangle((cx + side * 80 - 28, 640, cx + side * 80 + 28, 900), fill=limb)  # legs
        d.ellipse((cx + side * 80 - 34, 760, cx + side * 80 + 34, 828), fill=limb)
        d.rectangle((cx + side * 80 - 60, 900, cx + side * 80 + 60, 940), fill=CHARCOAL)  # feet
    img.save(path)


def world():
    top = tempfile.mkdtemp(prefix="screen-test-")
    role_dir = os.path.join(top, "casting", "robot")
    os.makedirs(os.path.join(role_dir, "headshots"))
    with open(os.path.join(REPO, "casting", "robot", "role.json")) as f:
        role = json.load(f)
    lilac = [{"name": "lilac", "hex": "#A88BD1", "where": "body"}, {"name": "slate violet", "hex": "#4E4860", "where": "joints"},
             {"name": "charcoal", "hex": "#2B2A2E", "where": "face"}, {"name": "lamp cream", "hex": "#F2E6C8", "where": "eyes"}, {"name": "red", "hex": "#C8442F", "where": "dial"}]
    role["looks"] = [dict(role["looks"][0], id="toy", name="Toy", colourways=[{"id": "lilac", "name": "Lilac", "why": "test", "of": "toy", "headshot": "toy.1-lilac", "swatches": lilac}]),
                     dict(role["looks"][0], id="other", name="Other")]
    role["looks"][0]["brief"] = dict(role["looks"][0]["brief"], gear=[])
    role["looks"][1]["brief"] = dict(role["looks"][1]["brief"], gear=[{"name": "short apron", "kind": "worn", "slot": "torso", "look": "a short cotton apron"}])
    with open(os.path.join(role_dir, "role.json"), "w") as f:
        json.dump(role, f)
    runs = os.path.join(top, "runs")
    os.makedirs(os.path.join(runs, "someone"))
    pic = os.path.join(runs, "someone", "image.png")
    robot(pic, colours=False)
    with open(os.path.join(runs, "someone", "brief.json"), "w") as f:
        json.dump({"name": "Someone", "character": True, "size_m": 1.8}, f)
    return top, role_dir, runs, role["breakdown"]["palette"]


def measure(top, name, **how):
    path = os.path.join(top, name + ".png")
    robot(path, **how)
    return path


def test_all():
    top, role_dir, runs, palette = world()
    cast = screen.the_cast(runs, os.path.join(top, "cache"))
    good, f, face_small = screen.screen_one(measure(top, "good"), palette, cast, 1.45)
    check("the figure is found: as tall as drawn, on a shaded background", abs(f.tall - (940 - 150) * screen.WORK_PX / 1024) <= 3, str(f.tall))
    check("a T-pose in front of a plain background builds", good["scores"]["builds"] > 0.9, str(good["numbers"]["builds"]))
    check("two eyes are found on the plate at the crew camera's size, level and apart", good["numbers"]["face"]["eyes"] == 2 and good["numbers"]["face"]["level"] and good["scores"]["face"] > 0.8, str(good["numbers"]["face"]))
    check("its colours are the breakdown's, mustard leading", good["scores"]["colours"] > 0.7 and good["numbers"]["colours"]["lead"] == 1.0, str(good["numbers"]["colours"]))
    check("nothing is flagged on it", good["flags"] == [], "; ".join(good["flags"]))
    down, _, _ = screen.screen_one(measure(top, "down", arms="down"), palette, cast, 1.45)
    check("arms down is not a T-pose", down["numbers"]["builds"]["t_pose"] < 0.6 and down["scores"]["builds"] < good["scores"]["builds"], str(down["numbers"]["builds"]))
    edge, _, _ = screen.screen_one(measure(top, "edge", edge=True), palette, cast, 1.45)
    check("hands at the frame's edge are not whole in frame", edge["numbers"]["builds"]["in_frame"] < 1.0)
    blank, _, _ = screen.screen_one(measure(top, "blank", eyes=False), palette, cast, 1.45)
    check("a head with no face plate has no face", blank["scores"]["face"] < 0.3, str(blank["numbers"]["face"]))
    off, _, _ = screen.screen_one(measure(top, "off", colours=False), palette, cast, 1.45)
    check("a robot in other colours does not match the breakdown's", off["scores"]["colours"] < good["scores"]["colours"] - 0.2, "%.2f against %.2f" % (off["scores"]["colours"], good["scores"]["colours"]))
    check("and it shares more of its outline with a cast member drawn the same way", off["numbers"]["stands_apart"]["shared"] >= good["numbers"]["stands_apart"]["shared"] - 0.01)
    ant, _, _ = screen.screen_one(measure(top, "antenna", antenna=True), palette, cast, 1.45)
    check("an antenna is flagged and costs the cards score", any("above its head" in x for x in ant["flags"]) and ant["scores"]["cards"] < good["scores"]["cards"], "; ".join(ant["flags"]))
    shade, _, _ = screen.screen_one(measure(top, "shadow", shadow=True), palette, cast, 1.45)
    check("a shadow under the feet is flagged", any("shadow" in x for x in shade["flags"]), "; ".join(shade["flags"]))
    held, _, _ = screen.screen_one(measure(top, "held", held=True), palette, cast, 1.45)
    check("a board held at the end of an arm is flagged", any("held" in x for x in held["flags"]), str(held["numbers"]["hands"]))
    banded = screen.Figure(measure(top, "band", band=True), 1.45)
    inside = banded.mask[int(136 * screen.WORK_PX / 1024), screen.WORK_PX // 2]
    check("the gap under a band over the head stays background", not inside)
    check("a brief with an apron hangs; a snug belt does not", screen.hangs({"gear": [{"name": "short apron", "kind": "worn", "look": "cotton"}]}) == ["short apron"]
          and not screen.hangs({"gear": [{"name": "belt", "kind": "worn", "look": "snug charcoal belt"}]}))
    shutil.copy(measure(top, "a"), os.path.join(role_dir, "headshots", "toy.png"))
    shutil.copy(measure(top, "b", antenna=True), os.path.join(role_dir, "headshots", "toy.2.png"))
    shutil.copy(measure(top, "c"), os.path.join(role_dir, "headshots", "other.png"))
    shutil.copy(measure(top, "d"), os.path.join(role_dir, "headshots", "nobody.png"))
    out = screen.screen_role("robot", os.path.join(top, "casting"), runs)
    ids = [r["id"] for r in out["shots"]]
    check("every headshot of a look in the role is ranked, a stranger's is not", sorted(ids) == ["other", "toy", "toy.2"], ",".join(ids))
    check("the plain one is first; the antenna and the apron in a brief come after it, flagged", ids[0] == "toy" and all(r["flags"] for r in out["shots"][1:]), ",".join(ids))
    check("each row has its picture, the crew camera's view, its face and a small copy, all written",
          all(os.path.isfile(os.path.join(screen.ROOT, r[k])) for r in out["shots"] for k in ("picture", "small", "face", "look_small")))
    check("the contact sheet is written", os.path.isfile(os.path.join(role_dir, "screen-contact-sheet.png")))
    shutil.rmtree(top)


def test_colourways():
    """headshots kept small for git, and a colourway screened against its own colours"""
    top, role_dir, runs, palette = world()
    heads = os.path.join(role_dir, "headshots")
    robot(os.path.join(heads, "toy.png"))
    robot(os.path.join(heads, "toy.1-lilac.png"), paint=((168, 139, 209), (78, 72, 96)))
    robot(os.path.join(heads, "toy.1-teal.png"), paint=((40, 150, 140), (78, 72, 96)))  # not written in role.json
    made = screen.keep("robot", os.path.join(top, "casting"))
    check("Codex's PNGs go to full/, and a 1024-pixel JPEG of each stays beside them",
          sorted(made) == ["toy", "toy.1-lilac", "toy.1-teal"] and not any(n.endswith(".png") for n in os.listdir(heads))
          and Image.open(os.path.join(heads, "toy.jpg")).size == (screen.KEEP_PX, screen.KEEP_PX) and os.path.isfile(os.path.join(heads, "full", "toy.png")))
    check("the kept JPEG is small (under 150 KB)", os.path.getsize(os.path.join(heads, "toy.jpg")) < 150000, "%d bytes" % os.path.getsize(os.path.join(heads, "toy.jpg")))
    check("keeping again makes nothing new", screen.keep("robot", os.path.join(top, "casting")) == [])
    check("names: a picture, a numbered picture, a colourway", screen.parse_shot("toy") == ("toy", 1, None) and screen.parse_shot("toy.2") == ("toy", 2, None)
          and screen.parse_shot("toy.1-lilac") == ("toy", 1, "lilac") and screen.parse_shot("toy.x") is None)
    out = screen.screen_role("robot", os.path.join(top, "casting"), runs)
    rows = {r["id"]: r for r in out["shots"]}
    check("the colourway is screened, one not in role.json is not", "toy.1-lilac" in rows and "toy.1-teal" not in rows, ",".join(rows))
    lilac = rows["toy.1-lilac"]
    check("it knows its headshot and its swatches", lilac["colourway"]["of"] == "toy" and lilac["colourway"]["swatches"][0] == "#A88BD1")
    check("its colours are measured against its own swatches, lilac leading", lilac["scores"]["colours"] > 0.7 and lilac["numbers"]["colours"]["lead"] == 1.0,
          str(lilac["numbers"]["colours"]))
    check("its shape scores are the headshot's own", abs(lilac["scores"]["builds"] - rows["toy"]["scores"]["builds"]) < 0.02 and abs(lilac["scores"]["face"] - rows["toy"]["scores"]["face"]) < 0.11)
    check("the colourways' contact sheet is written", out.get("colourway_sheet") and os.path.isfile(os.path.join(screen.ROOT, out["colourway_sheet"])))
    shutil.rmtree(top)


TESTS = [test_all, test_colourways]


def main():
    failed = 0
    for test in TESTS:
        print("%s:" % test.__name__[5:])
        try:
            test()
        except Exception as e:
            failed += 1
            print("    FAILED: %s: %s" % (type(e).__name__, str(e)[:800]))
    print("%d screen case(s) failed" % failed if failed else "all %d screen cases passed" % len(TESTS))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
