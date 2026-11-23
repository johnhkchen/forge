"""Tries the flat-card arithmetic. No Blender scene, no browser, no model needed.

    python3 scripts/impostor/test_impostor.py [RUNS_DIR]

The arithmetic needs numpy. When this Python has none, the file runs itself again in Blender's own Python
(which has it); with neither, it says so and stops without failing. What it shows:

  views     the three view sets have 26, 62 and 114 directions, each with a square, right-handed picture frame
  packing   a facing folded into two bytes comes back within a degree and a half; a .png comes back as written
  choosing  the nearest view is shown; one shown last time is kept until another is clearly nearer; on the line
            between two views each gets half
  placing   a point of a picture lands on the card exactly where the real point shows, for any bone, any eye
            and any view: turned, foreshortened and slid by its depth (exactly from far off; within 2 degrees
            from 4 m, for a point as much as 60 cm off the card)
  drawing   a ball baked as 26 pictures and drawn from between them is round and the right size, and lit from
            the eye's upper left; laid flat (no depth) it is still a ball
  page      gallery/impostor-math.js gives the same numbers as impostor.py (needs node; skipped without)
  baked     with RUNS_DIR holding a baked character (profiles/*-impostor): its sheets are the size its card
            says, every part has every picture, a bone's frame in the file is where its skin was bound, and
            a frame of its walk draws as one whole figure
"""

import glob
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

try:
    import numpy as np
except ImportError:
    found = sorted(glob.glob("/Applications/Blender.app/Contents/Resources/*/python/bin/python3*"))
    if not found or os.environ.get("IMPOSTOR_TEST_AGAIN"):
        print("skipped: the flat-card tests need numpy (Blender's Python has it; none was found)")
        sys.exit(0)
    sys.exit(subprocess.run([found[-1], os.path.abspath(__file__)] + sys.argv[1:], env=dict(os.environ, IMPOSTOR_TEST_AGAIN="1")).returncode)

sys.path.insert(0, HERE)
import impostor  # noqa: E402


def check(label, ok, detail=""):
    print("    %s  %s%s" % ("ok  " if ok else "FAIL", label, ("  (%s)" % (detail,)) if detail else ""))
    if not ok:
        raise AssertionError(label)


def some_bone(rng, size=1.0):
    q = rng.normal(size=4)
    q /= np.linalg.norm(q)
    m = np.eye(4)
    m[:3, :3] = impostor.quat_matrix(q) * size
    m[:3, 3] = rng.normal(size=3)
    return m


def test_views():
    for name, count in (("26", 26), ("62", 62), ("114", 114)):
        views = impostor.views_of(name)
        worst = 0.0
        for v in views:
            d, r, u = (np.array(v[k]) for k in "dru")
            worst = max(worst, abs(np.linalg.norm(d) - 1), abs(r @ u), abs(r @ d), abs(u @ d), np.linalg.norm(np.cross(r, u) - d))
        check("view set %s: %d directions, every picture frame square and right-handed" % (name, count), len(views) == count and worst < 1e-5, "worst %.2g" % worst)
    side = [v for v in impostor.views_of("26") if abs(v["d"][1]) < 1e-6]
    check("a side-on picture stands the bone upright", all(abs(v["u"][1] - 1) < 1e-6 for v in side) and len(side) == 8)


def test_packing():
    rng = np.random.default_rng(1)
    n = rng.normal(size=(4000, 3))
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    packed = np.round(impostor.pack_normal(n) * 255.0) / 255.0
    off = np.degrees(np.arccos(np.clip((impostor.unpack_normal(packed) * n).sum(axis=1), -1, 1)))
    check("a facing folded into two bytes comes back within 1.5 degrees", off.max() < 1.5, "worst %.2f" % off.max())
    folder = tempfile.mkdtemp(prefix="impostor-test-")
    try:
        for deep in (3, 4):
            picture = rng.integers(0, 256, size=(23, 31, deep), dtype=np.uint8)
            impostor.write_png(os.path.join(folder, "p.png"), picture)
            check("a .png of %d numbers a pixel comes back as written" % deep, np.array_equal(impostor.read_png(os.path.join(folder, "p.png")), picture))
    finally:
        shutil.rmtree(folder)


def test_choosing():
    dirs = np.array([v["d"] for v in impostor.views_of("26")])
    rng = np.random.default_rng(2)
    for _ in range(50):
        v = impostor.unit(rng.normal(size=3))
        first, second, share = impostor.choose(dirs, v)
        assert first == int(np.argmax(dirs @ v)) and 0.5 <= share <= 1.0
    check("the nearest view is the one shown", True)
    a, b = dirs[8], dirs[9]  # neighbours on the side-on ring
    just_past = impostor.unit(a * 0.49 + b * 0.51)
    check("a view shown last time is kept a little past the line", impostor.choose(dirs, just_past, held=8)[0] == 8 and impostor.choose(dirs, just_past)[0] == 9)
    well_past = impostor.unit(a * 0.3 + b * 0.7)
    check("... and let go once another is clearly nearer", impostor.choose(dirs, well_past, held=8)[0] == 9)
    check("on the line between two views each gets half", abs(impostor.choose(dirs, impostor.unit(a + b))[2] - 0.5) < 1e-4, "%.6f" % impostor.choose(dirs, impostor.unit(a + b))[2])
    check("square on to a view, it gets everything", impostor.choose(dirs, a)[2] == 1.0)


def test_placing():
    rng = np.random.default_rng(3)
    views = impostor.views_of("62")
    worst_far, worst_near = 0.0, 0.0
    for trial in range(200):
        size = float(rng.uniform(0.5, 2.0))
        bone = some_bone(rng, size)
        center = rng.normal(size=3) * 0.1
        view = views[int(rng.integers(len(views)))]
        d, r, u = (np.array(view[k]) for k in "dru")
        X, Y, h = rng.uniform(-0.3, 0.3, size=3)
        true = bone[:3, 3] + bone[:3, :3] @ (X * r + Y * u + h * d)
        for away, kind in ((1e6, "far"), (4.0, "near")):
            eye = bone[:3, 3] + impostor.unit(rng.normal(size=3)) * away
            card = impostor.place(view, bone, center, eye)
            sheet = card["turn_xy"] @ np.array([X, Y]) + h * card["lean"]
            on_card = card["head"] + card["size"] * (sheet[0] * card["e2"] + sheet[1] * card["e1"])
            # the real point and its place on the card must be in line with the eye: measure how far apart they look
            apart = float(np.linalg.norm(np.cross(impostor.unit(true - eye), on_card - true)))  # metres off the line of sight
            out = (np.array([X, Y, h]) @ card["deep"]) * card["size"]
            assert abs(out - (true - card["head"]) @ card["toward"]) < 1e-9
            if kind == "far":
                worst_far = max(worst_far, apart)
            else:
                worst_near = max(worst_near, math.degrees(apart / away))
            assert np.allclose(card["back"] @ card["turn_xy"], np.eye(2), atol=1e-9)
    check("from far off, a picture's point lands exactly where the real point shows", worst_far < 1e-6, "worst %.2g m" % worst_far)
    check("from 4 m it is within 2 degrees, for points up to 60 cm off the card (the eye is not endlessly far)", worst_near < 2.0, "worst %.2f degrees" % worst_near)
    bone = np.eye(4)
    card = impostor.place(views[24], bone, [0, 0, 0], np.array(views[24]["d"]) * 50.0)
    check("seen from exactly where it was pictured, a picture is not turned, squeezed or slid",
          np.allclose(card["turn_xy"], np.eye(2), atol=1e-9) and np.allclose(card["lean"], 0, atol=1e-9) and np.allclose(card["deep"], [0, 0, 1], atol=1e-9))


def ball(folder, radius=0.1, ppm=192.0):
    """A ball round its bone's head, baked the way bake_impostor.py bakes: 26 pictures, every one the same disc."""
    views = impostor.views_of("26")
    half = int(math.ceil(radius * ppm)) + 2
    side = 2 * half
    ys, xs = np.mgrid[0:side, 0:side]
    x, y = (xs + 0.5 - half) / ppm, (ys + 0.5 - half) / ppm
    there = x * x + y * y < radius * radius
    z = np.sqrt(np.clip(radius * radius - x * x - y * y, 0, None))
    depth_m = radius + 0.02
    cols = 6
    rows = (len(views) + cols - 1) // cols
    colour = np.zeros((rows * (side + 2) + 2, cols * (side + 2) + 2, 4), dtype=np.uint8)
    data = np.zeros(colour.shape[:2] + (3,), dtype=np.uint8)
    cells = []
    for i, view in enumerate(views):
        x0, y0 = 2 + (i % cols) * (side + 2), 2 + (i // cols) * (side + 2)
        normal = (x[..., None] * np.array(view["r"]) + y[..., None] * np.array(view["u"]) + z[..., None] * np.array(view["d"])) / radius
        packed = np.concatenate([impostor.pack_normal(normal), np.clip(z / depth_m * 0.5 + 0.5, 1 / 255.0, 1.0)[..., None]], axis=-1)
        packed[~there] = (0.5, 0.5, 0.0)
        colour[y0:y0 + side, x0:x0 + side] = np.where(there[..., None], (200, 200, 200, 255), (0, 0, 0, 0))
        data[y0:y0 + side, x0:x0 + side] = np.round(packed * 255.0)
        cells.append([x0, y0, side, side, half, half, 0.0, radius])
    impostor.write_png(os.path.join(folder, "c.png"), colour)
    impostor.write_png(os.path.join(folder, "d.png"), data)
    card = {"px_per_m": ppm, "default_views": "26", "parts": [{"name": "ball", "bone": "b", "center": [0, 0, 0], "depth_m": depth_m}],
            "sets": {"26": {"color": "c.png", "data": "d.png", "size": [colour.shape[1], colour.shape[0]], "views": views, "cells": {"ball": cells}}}}
    with open(os.path.join(folder, "impostor.json"), "w") as f:
        json.dump(card, f)
    return radius


def test_drawing():
    folder = tempfile.mkdtemp(prefix="impostor-test-")
    try:
        radius = ball(folder)
        character = impostor.Character(folder)
        bone = some_bone(np.random.default_rng(4))
        bone[:3, 3] = (0.2, 1.0, -0.1)
        # an eye between the pictures: 20 degrees round and 20 up from the nearest
        eye = impostor.Eye(bone[:3, 3] + 3.0 * impostor.unit([0.5, 0.4, 0.8]), bone[:3, 3], 8.0, (240, 240))
        ys, xs = np.mgrid[0:240, 0:240]
        per_px = eye.m_per_px(bone[:3, 3])
        true = (xs + 0.5 - 120) ** 2 + (ys + 0.5 - 120) ** 2 < (radius / per_px / math.cos(math.asin(radius / 3.0))) ** 2
        for relief, label in ((True, "slid by its depth"), (False, "laid flat")):
            picture, depth, said = impostor.draw(character, {"b": bone}, eye, relief=relief)
            got = picture[..., 3] > 0
            shared = (got & true).sum() / float((got | true).sum())
            check("a ball drawn from between its pictures, %s, is round and the right size" % label, shared > 0.955, "shares %.3f of the true disc, %.1f degrees off its picture" % (shared, said["ball"]["off_deg"]))
            if relief:
                near = float(depth[120, 120])
                check("its nearest point is a ball's radius nearer than its middle", abs(near - (3.0 - radius)) < 0.006, "%.3f m" % near)
                well_in = (xs + 0.5 - 120) ** 2 + (ys + 0.5 - 120) ** 2 < (0.85 * radius / per_px) ** 2
                values, counts = np.unique(picture[well_in][:, 0], return_counts=True)
                main = values[counts > 0.02 * counts.sum()]
                bright = picture[..., :3].astype(float).sum(axis=-1)
                upper_left, lower_right = bright[130:170, 70:110][got[130:170, 70:110]].mean(), bright[70:110, 130:170][got[70:110, 130:170]].mean()
                check("it is lit from the eye's upper left, in flat tones", upper_left > lower_right * 1.1 and 2 <= len(main) <= 3 and counts[counts > 0.02 * counts.sum()].sum() > 0.95 * counts.sum(),
                      "%d tones cover %.0f%% of it" % (len(main), 100.0 * counts[counts > 0.02 * counts.sum()].sum() / counts.sum()))
        mixed, _, _ = impostor.draw(character, {"b": bone}, eye, blend=True)
        check("mixing its two nearest pictures leaves no holes", ((mixed[..., 3] > 0) & true).sum() / float(true.sum()) > 0.97)
    finally:
        shutil.rmtree(folder)


def test_page():
    node = shutil.which("node")
    if not node:
        print("    skipped  the page's arithmetic against impostor.py (no node here)")
        return
    rng = np.random.default_rng(5)
    views = impostor.views_of("62")
    dirs = [v["d"] for v in views]
    cases = []
    for _ in range(60):
        bone = some_bone(rng, float(rng.uniform(0.6, 1.5)))
        cases.append({"bone": bone.T.reshape(-1).tolist(), "center": (rng.normal(size=3) * 0.1).tolist(), "eye": (bone[:3, 3] + impostor.unit(rng.normal(size=3)) * 4.0).tolist(),
                      "cell": [10, 20, int(rng.integers(20, 90)), int(rng.integers(20, 90)), int(rng.integers(5, 40)), int(rng.integers(5, 40)), -0.05, float(rng.uniform(0.0, 0.2))],
                      "held": int(rng.integers(len(views)))})
    script = """
      import { eyeInBone, choose, place, corners, marchSteps } from %s;
      const { views, cases } = JSON.parse(await new Promise((done) => { let s = ""; process.stdin.on("data", (d) => (s += d)).on("end", () => done(s)); }));
      const dirs = views.map((v) => v.d);
      console.log(JSON.stringify(cases.map((c) => {
        const v = eyeInBone(c.bone, c.center, c.eye);
        const pick = choose(dirs, v, null, %r, %r), kept = choose(dirs, v, c.held, %r, %r);
        const card = place(views[pick.first], c.bone, c.center, c.eye);
        return { v, pick: [pick.first, pick.second, pick.share], kept: [kept.first, kept.second, kept.share], back: card.back, lean: card.lean, deep: card.deep,
                 corners: corners(card, c.cell, 192).world, flat: corners(card, c.cell, 192, false).world, steps: marchSteps(card, c.cell, 192, { px: %r, max: %r }) };
      })));
    """ % (json.dumps("file://" + os.path.join(REPO, "gallery", "impostor-math.js")), impostor.HOLD_DEG, impostor.BLEND_DEG, impostor.HOLD_DEG, impostor.BLEND_DEG, impostor.MARCH_PX, impostor.MARCH_MAX)
    out = subprocess.run([node, "--input-type=module", "-e", script], input=json.dumps({"views": views, "cases": cases}), capture_output=True, text=True)
    if out.returncode:
        raise AssertionError("node could not run gallery/impostor-math.js:\n" + out.stderr[-800:])
    worst, same = 0.0, True
    for case, js in zip(cases, json.loads(out.stdout)):
        bone = np.array(case["bone"]).reshape(4, 4).T
        v = impostor.eye_in_bone(bone, case["center"], case["eye"])
        pick, kept = impostor.choose(np.array(dirs), v), impostor.choose(np.array(dirs), v, held=case["held"])
        card = impostor.place(views[pick[0]], bone, case["center"], case["eye"])
        same &= list(pick[:2]) == js["pick"][:2] and list(kept[:2]) == js["kept"][:2] and impostor.march_steps(card, case["cell"], 192.0) == js["steps"]
        for mine, theirs in ((v, js["v"]), (card["back"].reshape(-1), js["back"]), (card["lean"], js["lean"]), (card["deep"], js["deep"]), ([pick[2], kept[2]], [js["pick"][2], js["kept"][2]]),
                             (impostor.corners(card, case["cell"], 192.0), js["corners"]), (impostor.corners(card, case["cell"], 192.0, False), js["flat"])):
            worst = max(worst, float(np.abs(np.asarray(mine) - np.asarray(theirs)).max()))
    check("the page picks the same views and takes the same number of steps as impostor.py (60 cases)", same)
    check("... and puts every card's corners in the same place, and reads its picture the same way", worst < 1e-9, "worst %.2g" % worst)


def test_baked(runs):
    folders = sorted(glob.glob(os.path.join(runs, "*", "profiles", "*-impostor", "impostor.json")))
    if not folders:
        print("    skipped  a baked character (none in %s: just impostor <run> <version> makes one)" % runs)
        return
    folder = os.path.dirname(folders[0])
    character = impostor.Character(folder)
    card = character.card
    for name, sheet in card["sets"].items():
        colour = impostor.read_png(os.path.join(folder, sheet["color"]))
        complete = all(len(sheet["cells"][p["name"]]) == len(sheet["views"]) and all(c[2] > 0 and c[0] + c[2] <= sheet["size"][0] and c[1] + c[3] <= sheet["size"][1] for c in sheet["cells"][p["name"]]) for p in card["parts"])
        check("view set %s: the sheet is the size the card says, and every part has every picture on it" % name, list(colour.shape[1::-1]) == sheet["size"] and complete)
    check("it is cut into about fifteen parts, each with triangles of its own", 12 <= len(card["parts"]) <= 20 and all(p["own_triangles"] > 0 for p in card["parts"]), "%d parts" % len(card["parts"]))
    glb = os.path.join(os.path.dirname(folder), card["source"])
    if not os.path.isfile(glb):
        return
    motion = impostor.Glb(glb)
    rest = motion.pose(None)
    skin = motion.doc["skins"][0]
    bound = motion.numbers(skin["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
    worst = max(float(np.abs(np.linalg.inv(bound[i]) - rest[motion.names[j]]).max()) for i, j in enumerate(skin["joints"]))
    check("every bone's frame in the file is where its skin was bound (so a part cut there rides the bone exactly)", worst < 1e-4, "worst %.2g" % worst)
    pose = motion.pose(motion.seconds * 0.3)
    hips = pose["hips"][:3, 3]
    eye = impostor.Eye([hips[0] + 2.5, 1.4, hips[2] + 3.6], [hips[0], 0.95, hips[2]], 30.0, (240, 270))
    picture, _, said = impostor.draw(character, pose, eye)
    got = picture[..., 3] > 0
    ys, xs = np.where(got)
    tall_m = (ys.max() - ys.min()) * eye.m_per_px(eye.aim)
    # one whole figure: flood from one pixel reaches (nearly) all of it
    seen = np.zeros_like(got)
    todo = [(int(ys[0]), int(xs[0]))]
    seen[todo[0]] = True
    while todo:
        y, x = todo.pop()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < got.shape[0] and 0 <= nx < got.shape[1] and got[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                todo.append((ny, nx))
    check("a frame of its walk draws as one whole figure of a man's height, every part with a picture",
          seen.sum() > 0.985 * got.sum() and 1.5 < tall_m < 2.1 and len(said) == len(card["parts"]), "%.2f m tall, %.1f%% in one piece" % (tall_m, 100.0 * seen.sum() / got.sum()))


def main():
    runs = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "runs")
    cases = [("views", test_views), ("packing", test_packing), ("choosing", test_choosing), ("placing", test_placing), ("drawing", test_drawing),
             ("page", test_page), ("baked", lambda: test_baked(runs))]
    failed = 0
    for name, case in cases:
        print(name)
        try:
            case()
        except AssertionError as err:
            failed += 1
            print("    FAILED: %s" % err)
    print("%d of %d flat-card cases passed" % (len(cases) - failed, len(cases)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
