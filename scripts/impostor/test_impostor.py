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
  faces     a face drawn for pixel art (pixel_face.py): the sheet's few colours keep the face's own and are well
            apart; on a ball of a head both eyes are drawn from the front in whole pixels, level and either side of
            the middle, never smaller than the least size; from the side the near one is narrower and the far one
            is not drawn, from behind neither is; a turned face keeps its far eye; a hat's brim well in front
            hides the eyes, and one close over them hides only marks told to keep within 3 cm; a wash paints the front and leaves the back; every recipe in faces/ reads. With RUNS_DIR
            holding a sheet baked with a face (profiles/*-impostor-pixel-faces): its head is pictured finer
            than its body, both eyes are in a good share of its pictures, and its head draws the size the
            plain pixel sheet's does
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
import pixel_face  # noqa: E402


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


def ball_head(view, ppm=192.0, radius=0.09, brim=None):
    """One picture of a ball of a head, as the bake hands it to pixel_face: flat skin, how far each pixel stands
    toward the eye, where the head is, and where the bone's head (the ball's middle) is in the picture. brim: a
    disc this far above the middle and this wide, like a hat's (height, radius): it hides what is under it."""
    d, r, u = (np.array(view[k]) for k in "dru")
    half = int(math.ceil(radius * 1.8 * ppm)) + 2
    xs, ys = np.meshgrid((np.arange(2 * half) + 0.5 - half) / ppm, (np.arange(2 * half) + 0.5 - half) / ppm)
    inside = xs * xs + ys * ys < radius * radius
    height = np.where(inside, np.sqrt(np.clip(radius * radius - xs * xs - ys * ys, 0.0, None)), 0.0)
    there = inside.copy()
    if brim:
        up, wide = brim
        # where the eye's line through each pixel crosses the brim's plane (y = up), if it does inside the disc
        if abs(d[1]) > 1e-6:
            t = (up - (xs * r[1] + ys * u[1])) / d[1]
            hit = xs[..., None] * r + ys[..., None] * u + t[..., None] * d
            on = (hit[..., 0] ** 2 + hit[..., 2] ** 2 < wide * wide) & (t > height)
            height, there = np.where(on, t, height), there | on
    colour = np.zeros((2 * half, 2 * half, 4), dtype=np.float32)
    colour[there] = (0.8, 0.6, 0.5, 1.0)
    return colour, height.astype(np.float64), there, (half, half)


def test_faces(runs):
    # the sheet's few colours
    rng = np.random.default_rng(3)
    skin, hair, ink = np.array([0.67, 0.42, 0.33]), np.array([0.33, 0.25, 0.19]), np.array([0.11, 0.09, 0.13])
    pixels = np.concatenate([np.tile(skin, (9000, 1)), np.tile(hair, (600, 1)), np.tile([0.1, 0.2, 0.5], (300, 1)), np.tile([0.9, 0.85, 0.8], (100, 1))]).astype(np.float32)
    pixels += rng.uniform(-0.01, 0.01, size=pixels.shape).astype(np.float32)   # a render's faint mottling
    palette = pixel_face.few_colours(pixels, 32, keep=[ink, ink])
    near = lambda c: float(np.abs(palette - np.asarray(c, dtype=np.float32)).max(axis=1).min())
    gaps = [float(np.abs(a - b).max()) for i, a in enumerate(palette) for b in palette[i + 1:]]
    check("the few colours keep the face's own, once", float(np.abs(palette[0] - ink).max()) < 1e-6 and sum(np.abs(c - ink).max() < 1e-3 for c in palette) == 1)
    check("... find every colour the pixels have, however much of them is one flat colour", all(near(c) < 0.03 for c in (skin, hair, [0.1, 0.2, 0.5], [0.9, 0.85, 0.8])), "%d colours" % len(palette))
    check("... and spend none on a colour a hair off another", len(palette) <= 32 and min(gaps) >= 16.0 / 255.0 - 1e-6, "%d colours, the nearest two %.3f apart" % (len(palette), min(gaps)))
    same = [{"colours": [[int(round(c * 255)) for c in hair]], "as": [10, 200, 10]}]
    drawn_as = pixel_face.folded(palette, same)
    snapped = pixel_face.snap(np.array([[hair, skin]], dtype=np.float32), palette, drawn_as)
    check("a colour the recipe says is another thing's is drawn as that, and the rest as they are", np.abs(snapped[0, 0] * 255 - [10, 200, 10]).max() < 1 and np.abs(snapped[0, 1] - skin).max() < 0.03)
    check("the least a mark may measure is a size on the head: 3 pixels at 192 a metre, 2 at 96", pixel_face.least_for(192.0) == 3 and pixel_face.least_for(96.0) == 2)

    # a face on a ball of a head
    recipe = {"half_wide": 0.075, "colours": {"ink": [28, 23, 33], "rim": [52, 54, 68], "lens": [208, 220, 230]}, "marks": [
        {"name": "face", "kind": "wash", "x": [-0.05, 0.05], "y": [-0.05, 0.03], "colour": "found"},
        {"name": "glass", "kind": "ring", "at": [0.0, -0.04], "size": [0.047, 0.047], "rim_m": 0.0104, "colour": "rim", "lens": "lens"},
        {"name": "eye_r", "kind": "block", "at": [-0.03, 0.01], "size": [0.016, 0.016], "colour": "ink"},
        {"name": "eye_l", "kind": "block", "at": [0.03, 0.01], "size": [0.016, 0.016], "colour": "ink"}]}
    radius, ppm = 0.09, 192.0
    front_at = lambda x, y: math.sqrt(radius * radius - x * x - y * y) if x * x + y * y < radius * radius else None
    marks = pixel_face.place(recipe, front_at)
    views = impostor.views_of("26")
    least = pixel_face.least_for(ppm)
    is_ink = lambda colour: np.abs(colour[..., :3] - np.array([28, 23, 33]) / 255.0).max(axis=-1) < 1e-3

    def drawn(view, brim=None):
        colour, height, there, anchor = ball_head(views[view], ppm, radius, brim)
        found = pixel_face.find_colours(marks, *ball_head(views[8], ppm, radius)[:3], views[8], ppm, anchor)
        counts = pixel_face.draw(colour, height, there, views[view], ppm, anchor, marks, recipe["colours"], found, least)
        return colour, there, anchor, counts

    colour, there, anchor, counts = drawn(8)
    ys, xs = np.where(is_ink(colour))
    left, right = xs < anchor[0], xs >= anchor[0]
    box = lambda pick: (xs[pick].min(), xs[pick].max(), ys[pick].min(), ys[pick].max())
    a, b = box(left), box(right)
    check("from the front both eyes are drawn, in whole blocks no smaller than the least size",
          counts["eye_r"] == counts["eye_l"] >= least * least and a[1] - a[0] + 1 >= least and a[3] - a[2] + 1 >= least and left.sum() == (a[1] - a[0] + 1) * (a[3] - a[2] + 1), "%d and %d pixels" % (counts["eye_r"], counts["eye_l"]))
    check("... level with each other and the same way either side of the middle", a[2:] == b[2:] and abs((anchor[0] - a[1]) - (b[0] - anchor[0] + 1)) <= 1, "%s and %s about column %d" % (a, b, anchor[0]))
    check("... and nothing of the face is drawn off the head", not (is_ink(colour) & ~there).any())
    rim = np.abs(colour[..., :3] - np.array([52, 54, 68]) / 255.0).max(axis=-1) < 1e-3
    lens = np.abs(colour[..., :3] - np.array([208, 220, 230]) / 255.0).max(axis=-1) < 1e-3
    ly, lx = np.where(lens)
    ringed = all(rim[y, :x].any() and rim[y, x + 1:].any() and rim[:y, x].any() and rim[y + 1:, x].any() for y, x in zip(ly, lx))
    check("a ring is a rim all the way round what is inside it", lens.sum() >= 4 and ringed, "%d pixels of rim round %d of lens" % (rim.sum(), lens.sum()))
    _, _, _, side = drawn(10)      # from the character's left
    _, _, _, behind = drawn(12)
    check("from the side the near eye is drawn, narrower, and the far one is not", 0 < side["eye_l"] < counts["eye_l"] and side["eye_r"] == 0, "%d of %d, and %d" % (side["eye_l"], counts["eye_l"], side["eye_r"]))
    check("from behind neither is", behind["eye_l"] == 0 and behind["eye_r"] == 0)
    _, _, _, turned = drawn(9)     # 45 degrees round
    check("a turned face keeps its far eye, narrower than the near one", 0 < turned["eye_r"] <= turned["eye_l"], "%d and %d" % (turned["eye_r"], turned["eye_l"]))
    _, _, _, high = drawn(16)                              # from 45 degrees up, bare-headed
    _, _, _, hatted = drawn(16, brim=(0.2, 0.5))           # the same under a brim 19 cm above the eyes: 27 cm in front of them from here
    check("from above both eyes show on a bare head, and neither under a hat's brim well in front of them", high["eye_l"] > 0 and high["eye_r"] > 0 and hatted["eye_l"] == 0 and hatted["eye_r"] == 0, "%s then %s" % (high, hatted))
    marks[2]["reach"] = 0.03                               # the right eye told to keep within 3 cm of the surface
    _, _, _, close = drawn(16, brim=(0.06, 0.3))           # a brim 5 cm above the eyes: 7 cm in front of them from here
    del marks[2]["reach"]
    check("a brim close over the eyes hides the mark that keeps within 3 cm, and not the one left at 8", close["eye_r"] == 0 and close["eye_l"] > 0, str(close))
    back, _, _, washed = drawn(12)
    check("a wash paints the front of the face and leaves the back of the head alone", counts["face"] > 100 and washed["face"] == 0, "%d pixels from the front, %d from behind" % (counts["face"], washed["face"]))
    page = pixel_face.for_page(marks, recipe["colours"], {})
    check("the page is handed every mark but the wash, with its place, its facing and its colours", [m["name"] for m in page] == ["glass", "eye_r", "eye_l"] and all(len(m["p"]) == 3 and len(m["n"]) == 3 and len(m["colour"]) == 3 for m in page))

    # the recipes kept in the repo
    names = sorted(glob.glob(os.path.join(HERE, "faces", "*.json")))
    ok, said = bool(names), ""
    for path in names:
        with open(path) as f:
            face = json.load(f)
        found = {m["name"]: np.array([0.7, 0.5, 0.4], dtype=np.float32) for m in face["marks"] if m["kind"] == "wash"}
        for m in face["marks"]:
            good = m["kind"] in ("wash", "block", "disc", "ring") and (("x" in m and "y" in m) if m["kind"] == "wash" else (len(m["at"]) == 2 and len(m["size"]) == 2 and min(m["size"]) >= pixel_face.LEAST_M * 0.75))
            good = good and pixel_face.paint_of(m, "colour", face.get("colours", {}), found) is not None
            if not good:
                ok, said = False, "%s: %s" % (os.path.basename(path), m["name"])
        ok = ok and bool(face.get("drawn_on"))
    check("every recipe in faces/ reads: each mark a kind there is, a colour that is named, no smaller than shows, and the model it was drawn on", ok, said or "%d recipes" % len(names))
    check("a run's recipe is found by the run's name without its date", pixel_face.recipe_for("/somewhere/runs/2026-11-20T14-02-45-roosevelt-wrestler-1890s") is not None and pixel_face.recipe_for("/somewhere/runs/2026-01-01T00-00-00-nobody") is None)

    # a sheet baked with a face
    folders = sorted(glob.glob(os.path.join(runs, "*", "profiles", "*-impostor-pixel-faces", "impostor.json")))
    if not folders:
        print("    skipped  a sheet baked with a face (none in %s: just impostor-detailed <run> makes one for a character with a recipe)" % runs)
        return
    for path in folders:
        folder = os.path.dirname(path)
        who = os.path.basename(os.path.dirname(os.path.dirname(folder))).split("-", 5)[-1]
        character = impostor.Character(folder)
        card = character.card
        head = next(p for p in card["parts"] if p["name"] == "head")
        times = head.get("px_per_m", card["px_per_m"]) / card["px_per_m"]
        check("%s: the head is pictured finer than the body, a whole number of times" % who, times > 1 and abs(times - round(times)) < 1e-9, "%g times" % times)
        eyes = {k: v for k, v in card["face"]["pictures_with"].items() if k.startswith("eye")}
        check("%s: every eye is in at least 8 of the head's %d pictures" % (who, len(character.views)), bool(eyes) and min(eyes.values()) >= 8, str(eyes))
        plain = folder[:-len("-faces")]
        glb = os.path.join(os.path.dirname(folder), card["plays"] + "-walk.glb")
        if not (os.path.isfile(os.path.join(plain, "impostor.json")) and os.path.isfile(glb)):
            continue
        # the head alone, drawn from the same eye off the finer sheet and off the plain one: the same size and place
        motion = impostor.Glb(glb)
        pose = motion.pose(None)
        at = pose["head"][:3, 3]
        eye = impostor.Eye([at[0] + 0.4, at[1] + 0.1, at[2] + 3.0], [at[0], at[1] + 0.05, at[2]], 12.0, (200, 200))
        boxes = []
        for which in (character, impostor.Character(plain)):
            picture, _, _ = impostor.draw(which, pose, eye, only=["head"])
            ys, xs = np.where(picture[..., 3] > 0)
            boxes.append((xs.min(), xs.max(), ys.min(), ys.max()))
        off = max(abs(int(a) - int(b)) for a, b in zip(*boxes))
        wide = boxes[1][1] - boxes[1][0]
        check("%s: the finer head draws where and as big as the plain sheet's head does (within 4%% of its width)" % who, off <= max(2, 0.04 * wide), "%d pixels off on a head %d wide" % (off, wide))


def main():
    runs = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "runs")
    cases = [("views", test_views), ("packing", test_packing), ("choosing", test_choosing), ("placing", test_placing), ("drawing", test_drawing),
             ("page", test_page), ("faces", lambda: test_faces(runs)), ("baked", lambda: test_baked(runs))]
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
