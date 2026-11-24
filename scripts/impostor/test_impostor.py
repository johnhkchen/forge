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
            holding a sheet baked with a face (profiles/*-impostor-pixel-joined, or the older *-pixel-faces): its head is pictured finer
            than its body, both eyes are in a good share of its pictures, and its head draws the size the
            plain pixel sheet's does
  joints    a limb whose two parts' weights meet in a fringe of splinters is cut along one clean ring, and
            each part laps the other by the same share of the limb's radius all the way round, and further where
            its own bones still pull; the joint gets a ball as big as fits; two parts drawn
            side by side, each with its own ink line all round it, show no line where they meet (the line is a
            shell behind the surface, and the part next door covers it) and keep it round the outside; with the
            line drawn on the finished picture instead, it is one pixel wide, wholly outside the figure, and
            never between two parts at the same depth; an arm in front of a chest still gets its line, and so
            does one figure in front of another; bold ink leaves a small step between two cards of one figure
            alone and still inks a real one; gallery/looks.js has the same numbers
  fill      a bent joint filled: a part with a tall flat top, seen from a little to one side, is see-through beside
            its top where the eye looks under the edge; with a joint there those pixels are filled, in the top's
            colour, behind the top and inside the joint's ball, and with the joint a metre off nothing changes;
            a part that is a rim round a hollow, seen from in front, gets the joint's ball in the hollow, round
            and at the right depth, and none where it has no surface; the part whose body is behind a ball
            stands it nearest; on the finished picture a crack a pixel wide between two parts that meet is
            filled from the nearer and gets no line, and one between parts that do not meet, a wide one, and a
            pixel that is in front are left alone; the page has the same numbers, the same table of parts that
            meet, and finds the same colour for a ball (needs node)
  skin      a piece of the real model in a big joint (bake_joints.py): inside the joint's zone a card keeps only what
            is near its own bone's line, stood 3 cm back, and outside the zone, or with the zone off, it is as it
            was; a piece (a tube pulled by two bones) is drawn only within its reach of the joint, from outside
            only (never its far wall), says it is the card below the joint,
            and bends where the bone bends it; the page has the same numbers, gives every part the same zones,
            turns a joint's number negative when its zone is on, and reads the "-skinned" folder first (needs
            node). With RUNS_DIR holding cards with pieces (profiles/*-impostor-joe-skinned): every joint named
            has a piece that lies within reach of its joint at rest, and a frame of the walk drawn with the
            pieces covers what it covered without them
  clear     a face kept clear in "Pixels, both": a head far off stays on the body's grid and a near one goes on a
            grid twice as fine, slid so the bone's head sits on a corner of a pixel; drawn that way a head is twice
            the pixels across, its line is still one big pixel wide and wholly outside it, and a body drawn
            beside it stays in whole big pixels; the line on a finer picture of big pixels falls where it fell on
            the small one; a dark line one sheet pixel wide, shown at half size, is kept wherever the grid sits
            (and read plainly is dropped somewhere); a fold is found where a surface steps back or turns, on the
            further pixel; the page has the same numbers. With RUNS_DIR holding a sheet baked for it
            (profiles/*-impostor-pixel-clear): its head is pictured at 192 pixels a metre, has folds drawn in,
            and the sheet has no more colours than it may
  layers    a brim in front of a plate, baked two layers deep and seen from one side: with the first layer alone
            the plate behind the brim's edge is a hole; with the layer behind it is filled, in the plate's colour,
            and nothing else changes. The page makes the same room for a lower layer, takes as many steps more,
            and reads layered cards first (needs node). With RUNS_DIR holding layered cards
            (profiles/*-impostor-joe-layered): every picture has a layer behind listed, inside the sheet, the first
            layer is the sheet that was there before, and a frame of the walk covers all it covered without
  baked     with RUNS_DIR holding a baked character (profiles/*-impostor-comic-joined, or the older
            *-impostor): its sheets are the size its card says, every part has every picture, a bone's frame in
            the file is where its skin was bound, and a frame of its walk draws as one whole figure; a sheet
            baked since the joints were mended marks its ink line, says how every joint was lapped, and its
            walk shows no ink where two parts meet
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


def tube(rng, radius=0.05, around=48, rings=61):
    """A limb: a tube along y, a ring of points every centimetre, two parts whose weights meet near the middle in
    a fringe of teeth 8 cm long and 2 cm wide, the way weights borrowed from a coarse mesh do. Every point is
    there twice, as a mesh from a .glb has its points along a seam."""
    ys = np.linspace(-0.3, 0.3, rings)
    angles = 2.0 * np.pi * np.arange(around) / around
    points = np.array([[radius * math.cos(a), y, radius * math.sin(a)] for y in ys for a in angles])
    line = np.where((np.arange(around) // 3) % 2 == 0, 0.04, -0.04) + rng.normal(size=around) * 0.004
    upper = (points[:, 1] > np.tile(line, rings)).astype(np.float32)
    pull = np.stack([1.0 - upper, upper], axis=1)
    faces = [(r * around + k, r * around + (k + 1) % around, (r + 1) * around + (k + 1) % around, (r + 1) * around + k) for r in range(rings - 1) for k in range(around)]
    edges = [(f[i], f[(i + 1) % 4]) for f in faces for i in range(4)]
    twice = len(points)  # the second copy of every point: odd faces use it, so the mesh is in pieces until its points are welded
    faces = [tuple(c + twice for c in f) if i % 2 else f for i, f in enumerate(faces)]
    return np.concatenate([points, points]), np.concatenate([pull, pull]), np.array(edges), np.array(faces).reshape(-1), np.arange(len(faces)) * 4, np.full(len(faces), 4), radius


def two_plates(folder, radius=0.1, ppm=192.0, line_px=3):
    """Two parts, each a round plate through its own bone's head and facing its picture's eye, baked with an ink
    line all round and the line marked: the cut end of a limb, as its neighbour's picture has it."""
    views = impostor.views_of("26")
    half = int(math.ceil(radius * ppm)) + line_px + 2
    side = 2 * half
    ys, xs = np.mgrid[0:side, 0:side]
    x, y = (xs + 0.5 - half) / ppm, (ys + 0.5 - half) / ppm
    there = x * x + y * y < radius * radius
    line = ~there & (x * x + y * y < (radius + line_px / ppm) ** 2)
    z = np.zeros_like(x)
    depth_m = radius + 0.02
    cols = 6
    rows = (len(views) + cols - 1) // cols
    colour = np.zeros((rows * (side + 2) + 2, cols * (side + 2) + 2, 4), dtype=np.uint8)
    data = np.zeros(colour.shape[:2] + (3,), dtype=np.uint8)
    cells = []
    for i, view in enumerate(views):
        x0, y0 = 2 + (i % cols) * (side + 2), 2 + (i // cols) * (side + 2)
        normal = np.broadcast_to(np.array(view["d"]), x.shape + (3,))
        packed = np.concatenate([impostor.pack_normal(normal), np.clip(z / depth_m * 0.5 + 0.5, 1 / 255.0, 1.0)[..., None]], axis=-1)
        packed[~there] = (0.5, 0.5, 0.0)
        packed[line] = (0.0, 0.0, 0.5)  # the line: marked, and as high as the surface beside it
        colour[y0:y0 + side, x0:x0 + side] = np.where((there | line)[..., None], (200, 200, 200, 255), (0, 0, 0, 0))
        data[y0:y0 + side, x0:x0 + side] = np.round(packed * 255.0)
        cells.append([x0, y0, side, side, half, half, 0.0, 0.01])
    impostor.write_png(os.path.join(folder, "c.png"), colour)
    impostor.write_png(os.path.join(folder, "d.png"), data)
    card = {"px_per_m": ppm, "default_views": "26", "line_marked": True, "parts": [{"name": n, "bone": n, "center": [0, 0, 0], "depth_m": depth_m} for n in "ab"],
            "sets": {"26": {"color": "c.png", "data": "d.png", "size": [colour.shape[1], colour.shape[0]], "views": views, "cells": {"a": cells, "b": cells}}}}
    with open(os.path.join(folder, "impostor.json"), "w") as f:
        json.dump(card, f)
    return radius


def test_joints():
    # the cut
    rng = np.random.default_rng(11)
    points, pull, edges, corners, begin, sides, radius = tube(rng)
    middle = np.add.reduceat(points[corners], begin, axis=0)[:, 1] / 4.0
    joint = [(0, 1, np.array([0.01, 0.0, 0.0]))]  # the joint a centimetre off the limb's middle
    raw, _, _, _ = impostor.round_cut(points, pull, edges, corners, begin, sides, joint, 0.85, 0.0)
    owner, lapped, rings, balls = impostor.round_cut(points, pull, edges, corners, begin, sides, joint, 0.85, 0.02)
    ragged = middle[raw == 0].max() - middle[raw == 1].min()
    clean = middle[owner == 0].max() - middle[owner == 1].min()
    check("a limb whose weights meet in a fringe of splinters is cut along one clean ring", ragged > 0.06 and clean < 0.012, "the two parts' faces run %.1f cm into each other as the weights have them, %.1f cm cut" % (ragged * 100, clean * 100))
    check("... and the ring's radius is the limb's", abs(rings[(0, 1)] - radius) < 0.004, "%.1f cm" % (rings[(0, 1)] * 100))
    line = 0.5 * (middle[owner == 0].max() + middle[owner == 1].min())
    column = (np.arange(len(owner)) % 48)
    reach = [(float((middle[lapped[0] & (column == k)]).max() - line), float(line - (middle[lapped[1] & (column == k)]).min())) for k in range(48)]
    check("each part laps the other by 0.85 of the radius, all the way round, and takes nothing of its own", not (lapped[0] & (owner == 0)).any() and not (lapped[1] & (owner == 1)).any()
          and all(0.03 < r < 0.055 for pair in reach for r in pair), "%.1f to %.1f cm" % (100 * min(min(p) for p in reach), 100 * max(max(p) for p in reach)))

    _, wider, _, _ = impostor.round_cut(points, pull, edges, corners, begin, sides, joint, 0.2, 0.02, pulled=[0.1, 2.0])
    _, short, _, _ = impostor.round_cut(points, pull, edges, corners, begin, sides, joint, 0.2, 0.02)
    reach = [float(middle[which[0]].max() - line) for which in (short, wider)]
    check("a part also takes the faces next door that its own bones still pull on, and the other part, told not to, takes no more", bool((wider[0] | ~short[0]).all()) and reach[1] > reach[0] + 0.008 and bool((wider[1] == short[1]).all()),
          "%.1f cm into its neighbour by the ring's rule, %.1f cm where its bones pull by a tenth" % (reach[0] * 100, reach[1] * 100))
    size, made = balls[(0, 1)]
    check("the joint's ball is as big as fits inside the limb there, and is made of the faces round the ring, both parts'", 0.03 < size < 0.04 and (owner[made] == 0).any() and (owner[made] == 1).any()
          and float(np.abs(middle[made] - line).max()) < 0.065, "%.1f cm across, faces within %.1f cm of the ring" % (200 * size, 100 * np.abs(middle[made] - line).max()))

    # the line round a part, where two parts meet
    folder = tempfile.mkdtemp(prefix="impostor-test-")
    try:
        radius = two_plates(folder)
        character = impostor.Character(folder)
        pose = {"a": np.eye(4), "b": np.eye(4)}
        pose["a"][:3, 3], pose["b"][:3, 3] = (-0.06, 1.0, 0.0), (0.06, 1.0, 0.0)
        eye = impostor.Eye([0.0, 1.0, 3.0], [0.0, 1.0, 0.0], 8.0, (240, 240))
        per_px = eye.m_per_px([0.0, 1.0, 0.0])
        ys, xs = np.mgrid[0:240, 0:240]
        disc = lambda cx, grow_px: (xs + 0.5 - 120 - cx / per_px) ** 2 + (ys + 0.5 - 120) ** 2 < (radius / per_px + grow_px) ** 2
        well_in, outside = disc(-0.06, -3) | disc(0.06, -3), ~(disc(-0.06, 1.5) | disc(0.06, 1.5))
        dark = lambda picture: (picture[..., 3] > 0) & (picture[..., :3].max(axis=-1) < 60)
        picture, _, _ = impostor.draw(character, pose, eye)
        check("two parts side by side, each with its own line all round: no line shows where they meet", int((dark(picture) & well_in).sum()) == 0, "%d dark pixels inside" % (dark(picture) & well_in).sum())
        check("... and the line is still there round the outside of the two", int((dark(picture) & outside).sum()) > 150, "%d pixels of line" % (dark(picture) & outside).sum())
        keep = impostor.LINE_BACK_M
        impostor.LINE_BACK_M = 0.0
        at_surface, _, _ = impostor.draw(character, pose, eye)
        impostor.LINE_BACK_M = keep
        check("(drawn at the surface's own depth, as it used to be, each part's line crosses the other)", int((dark(at_surface) & well_in).sum()) > 40, "%d dark pixels inside" % (dark(at_surface) & well_in).sum())
        # the same, with the line drawn on the finished picture
        small = impostor.Eye([0.0, 1.0, 3.0], [0.0, 1.0, 0.0], 8.0, (80, 80))
        who = np.zeros((80, 80), dtype=np.int32)
        picture, depth, _ = impostor.draw(character, pose, small, line="off", who=who)
        got = picture[..., 3] > 0
        lines = impostor.grid_line(depth, who, small)
        beside = np.zeros_like(got)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            beside |= np.roll(got, (dy, dx), axis=(0, 1))
        check("left out of the cards (the sheet's line is not drawn), the two parts are bare discs", int(dark(picture).sum()) == 0 and set(np.unique(who)) == {0, 1, 2})
        check("the line drawn on the finished picture is one pixel wide, just outside the figure, all the way round", bool((lines == (beside & ~got)).all()), "%d pixels of line" % lines.sum())
        # an arm in front of a chest, and one figure in front of another
        flat = np.full((40, 40), np.inf)
        flat[5:35, 5:35] = 4.0
        cards = np.where(np.isfinite(flat), 1, 0)
        step = flat.copy()
        step[5:35, 20:35] = 4.2
        chest_arm = cards.copy()
        chest_arm[5:35, 20:35] = 2
        inside = np.zeros_like(cards, dtype=bool)
        inside[8:32, 8:32] = True
        check("one part behind another of the same figure by 20 cm gets a line, on the further one", bool(impostor.grid_line(step, chest_arm, small)[8:32, 20].all()) and not impostor.grid_line(step, chest_arm, small)[8:32, 19].any())
        step[5:35, 20:35] = 4.03
        check("... by 3 cm, the cards not quite agreeing, none", not (impostor.grid_line(step, chest_arm, small) & inside).any())
        other = chest_arm.copy()
        other[5:35, 20:35] = 1 + impostor.PARTS_A_FIGURE
        check("... and another figure 3 cm behind does get one: it is somebody else", bool(impostor.grid_line(step, other, small)[8:32, 20].all()))
        slope = np.where(np.isfinite(flat), 4.0 + 0.08 * np.arange(40)[None, :], np.inf)
        check("a surface sloping steeply away is not a step", not (impostor.grid_line(slope, cards, small) & inside).any())
        # bold ink
        big = impostor.Eye([0.0, 1.0, 3.0], [0.0, 1.0, 0.0], 8.0, (40, 40))
        step[5:35, 20:35] = 4.06
        check("bold ink: a 6 cm step between two cards of one figure is left alone, and inked when nobody says who is who", not (impostor.bold_lines(step, chest_arm, big) & inside).any() and bool((impostor.bold_lines(step, None, big) & inside).any()))
        step[5:35, 20:35] = 4.2
        check("... a 20 cm step between them is inked", bool((impostor.bold_lines(step, chest_arm, big) & inside).any()))
    finally:
        shutil.rmtree(folder)
    with open(os.path.join(REPO, "gallery", "looks.js")) as f:
        page = f.read()
    with open(os.path.join(REPO, "gallery", "impostor.js")) as f:
        page += f.read()
    check("the page has the same numbers: how far a line must step, the seam bold ink forgives, sixteen parts a figure, the line's colour", all(text in page for text in (
        "breakM: { value: %g }" % impostor.BREAK_M, "seamM: { value: %g }" % impostor.SEAM_M, "1 + %d * (figure %% 15) + (part %% %d)" % (impostor.PARTS_A_FIGURE, impostor.PARTS_A_FIGURE),
        "lineInk: { value: new THREE.Color(0x%02x%02x%02x) }" % tuple(int(round(c * 255)) for c in impostor.INK))))


def test_baked(runs):
    folders = sorted(glob.glob(os.path.join(runs, "*", "profiles", "*-impostor-comic-joined", "impostor.json"))) or sorted(glob.glob(os.path.join(runs, "*", "profiles", "*-impostor", "impostor.json")))
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
    if card.get("line_marked"):
        joints = card.get("joints") or []
        check("every joint has a ring where its two parts meet, a lap and a ball", len(joints) == len(card["parts"]) - 1 and all(j["ring_cm"] > 1 and 0 < j["lap_cm"] < j["ring_cm"] and j["ball_cm"] > 1 for j in joints),
              "; ".join("%s %.0f/%.0f/%.0f" % (j["bone"], j["ring_cm"], j["lap_cm"], j["ball_cm"]) for j in joints[:4]) + " cm ...")
        sheet = card["sets"][card["default_views"]]
        data = impostor.read_png(os.path.join(folder, sheet["data"]))
        colour = impostor.read_png(os.path.join(folder, sheet["color"]))
        line = (data[..., 0] == 0) & (data[..., 1] == 0) & (data[..., 2] > 0)
        check("the ink line's pixels are marked in the data sheet, and the colour sheet holds no ink of its own there", 0.02 < line.sum() / float((data[..., 2] > 0).sum()) < 0.35 and bool((colour[line][:, 3] == 255).all())
              and float(colour[line][:, :3].max(axis=1).mean()) > 60, "%.0f%% of the sheet's pixels are line" % (100.0 * line.sum() / (data[..., 2] > 0).sum()))
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
    folders = sorted(glob.glob(os.path.join(runs, "*", "profiles", "*-impostor-pixel-joined", "impostor.json")) + glob.glob(os.path.join(runs, "*", "profiles", "*-impostor-pixel-faces", "impostor.json")))
    folders = [path for path in folders if "face" in json.load(open(path))]
    if not folders:
        print("    skipped  a sheet baked with a face (none in %s: just impostor-detailed <run> makes one for a character with a recipe)" % runs)
        return
    for path in folders:
        folder = os.path.dirname(path)
        who = os.path.basename(os.path.dirname(os.path.dirname(folder))).split("-", 5)[-1] + (", joints mended" if folder.endswith("-joined") else "")
        character = impostor.Character(folder)
        card = character.card
        head = next(p for p in card["parts"] if p["name"] == "head")
        times = head.get("px_per_m", card["px_per_m"]) / card["px_per_m"]
        check("%s: the head is pictured finer than the body, a whole number of times" % who, times > 1 and abs(times - round(times)) < 1e-9, "%g times" % times)
        eyes = {k: v for k, v in card["face"]["pictures_with"].items() if k.startswith("eye")}
        check("%s: every eye is in at least 8 of the head's %d pictures" % (who, len(character.views)), bool(eyes) and min(eyes.values()) >= 8, str(eyes))
        plain = folder[:-len("-joined" if folder.endswith("-joined") else "-faces")]  # the sheet with the head as coarse as the body
        glb = os.path.join(os.path.dirname(folder), card["plays"] + "-walk.glb")
        if not (os.path.isfile(os.path.join(plain, "impostor.json")) and os.path.isfile(glb)):
            continue
        # the head alone, drawn from the same eye off the finer sheet and off the plain one: the same size and place
        motion = impostor.Glb(glb)
        pose = motion.pose(None)
        at = pose["head"][:3, 3]
        eye = impostor.Eye([at[0] + 0.4, at[1] + 0.1, at[2] + 3.0], [at[0], at[1] + 0.05, at[2]], 12.0, (200, 200))
        boxes = []
        for which in (impostor.Character(plain), character):
            picture, _, _ = impostor.draw(which, pose, eye, only=["head"])
            ys, xs = np.where(picture[..., 3] > 0)
            if not boxes:
                floor = ys.max() - 0.6 * (ys.max() - ys.min())  # the head itself: how far down the neck a sheet's head part reaches is the cut's business
            boxes.append((xs[ys >= floor].min(), xs[ys >= floor].max(), ys.max()))
        off = max(abs(int(a) - int(b)) for a, b in zip(*boxes))
        wide = boxes[0][1] - boxes[0][0]
        check("%s: the finer head draws where and as big as the plain sheet's head does (within 4%% of its width)" % who, off <= max(2, 0.04 * wide), "%d pixels off on a head %d wide" % (off, wide))


def test_clear(runs):
    folder = tempfile.mkdtemp(prefix="impostor-test-")
    try:
        radius = ball(folder)
        with open(os.path.join(folder, "impostor.json")) as f:
            card = json.load(f)
        card["parts"][0]["name"] = "head"
        card["sets"]["26"]["cells"] = {"head": card["sets"]["26"]["cells"]["ball"]}
        card.update(nearest=True, line_marked=True)
        colour = impostor.read_png(os.path.join(folder, "c.png")).copy()
        for x0, y0, w, h, ax, ay, _, _ in card["sets"]["26"]["cells"]["head"]:
            colour[y0 + ay - 3:y0 + ay + 4, x0 + ax, :3] = (20, 20, 20)  # a line one pixel of the sheet wide, in the middle of every picture
        impostor.write_png(os.path.join(folder, "c.png"), colour)
        with open(os.path.join(folder, "impostor.json"), "w") as f:
            json.dump(card, f)
        head = impostor.Character(folder)
        bone = np.eye(4)
        bone[:3, 3] = (0.013, 1.6, 0.007)
        # the grid: a metre is 96 big pixels at 2 m with this eye, 24 at 8 m
        near = impostor.Eye(bone[:3, 3] + np.array([0.0, 0.0, 2.0]), bone[:3, 3] + np.array([0.011, 0.004, 0.0]), 2.0 * math.degrees(math.atan(0.5)), (192, 192))
        far = impostor.Eye(bone[:3, 3] + np.array([0.0, 0.0, 8.0]), bone[:3, 3], near.fov_deg, (192, 192))
        finer, fine_eye = impostor.head_grid(near, bone[:3, 3])
        at, _ = fine_eye.to_pixels(bone[:3, 3])
        check("a head 96 big pixels a metre goes on a grid twice as fine, and one 24 a metre stays with the body", finer and fine_eye.size == (384, 384) and not impostor.head_grid(far, bone[:3, 3])[0])
        check("... slid by less than a pixel, so the bone's head sits on a corner of one", float(np.abs(at - np.round(at)).max()) < 1e-6 and max(abs(c) for c in fine_eye.shift) <= 0.5 + 1e-9, "at %s, slid %s" % (np.round(at, 3), np.round(fine_eye.shift, 3)))
        picture, depth, who, lines = impostor.draw_fine_heads(head, {"b": bone}, near, paint=impostor.PAINTS["pixel"])
        plain, _, _ = impostor.draw(head, {"b": bone}, near, line="off")
        cover, small = (who > 0), plain[..., 3] > 0
        check("drawn that way a head is twice the pixels across", picture.shape[:2] == (384, 384) and abs(cover.sum() / 4.0 / small.sum() - 1.0) < 0.03, "%d fine pixels where the small picture has %d" % (cover.sum(), small.sum()))
        ys, xs = np.nonzero(cover)
        ring = math.pi * (xs.max() - xs.min() + 1)
        check("its line is one big pixel wide (two fine ones) and wholly outside it", not (lines & cover).any() and 1.7 < lines.sum() / ring < 2.6, "%d pixels of line round a head %d round" % (lines.sum(), ring))
        # the line on a picture of big pixels blown up is the line of the small picture blown up
        rng = np.random.default_rng(5)
        who_s, depth_s = np.zeros((40, 48), dtype=np.int32), np.full((40, 48), np.inf, dtype=np.float32)
        for n in range(14):
            y, x, h, w = rng.integers(2, 30), rng.integers(2, 36), rng.integers(3, 9), rng.integers(3, 9)
            who_s[y:y + h, x:x + w], depth_s[y:y + h, x:x + w] = 1 + 16 * (n % 3) + n % 5, 3.0 + 0.04 * n + 0.01 * np.arange(w)[None, :]
        eye_s = impostor.Eye([0, 1, 5], [0, 1, 0], 30.0, (48, 40))
        eye_f = impostor.Eye([0, 1, 5], [0, 1, 0], 30.0, (96, 80))
        big = lambda a: np.repeat(np.repeat(a, 2, axis=0), 2, axis=1)
        check("the line on a finer picture made of big pixels falls just where it fell on the small one", bool((impostor.grid_line(big(depth_s), big(who_s), eye_f, fine=2) == big(impostor.grid_line(depth_s, who_s, eye_s))).all()))
        # a mark one sheet pixel wide, the head shown at half the size it was pictured: 96 pixels a metre
        kept, plainly = [], []
        for sx in (0.0, 0.25, 0.5, 0.75):
            for sy in (0.0, 0.25, 0.5, 0.75):
                eye = impostor.Eye(near.at, near.aim, near.fov_deg, near.size, shift=(sx, sy))
                for keep, counts in ((True, kept), (False, plainly)):
                    got, _, _ = impostor.draw(head, {"b": bone}, eye, line="off", keep_dark=keep)
                    counts.append(int(((got[..., :3].max(axis=-1) < 60) & (got[..., 3] > 0)).sum()))
        check("a dark line one sheet pixel wide, shown at half size, is kept wherever the grid sits, and is never over two pixels wide", min(kept) >= 3 and max(kept) <= 8, "%d to %d pixels" % (min(kept), max(kept)))
        check("... where reading only the middle of each pixel drops it somewhere", min(plainly) == 0, "%d to %d pixels" % (min(plainly), max(plainly)))
        check("shown as big as it was pictured or bigger, nothing is added", int(((impostor.draw(head, {"b": bone}, fine_eye, line="off", keep_dark=True)[0][..., :3].max(axis=-1) < 60)).sum()) == int(((impostor.draw(head, {"b": bone}, fine_eye, line="off")[0][..., :3].max(axis=-1) < 60)).sum()))
    finally:
        shutil.rmtree(folder)
    # folds
    height = np.zeros((9, 12))
    height[:, 6:] = 0.03
    normal = np.zeros((9, 12, 3))
    normal[..., 2] = 1.0
    normal[4, :3] = (1.0, 0.0, 0.0)
    known = np.ones((9, 12), dtype=bool)
    known[:, [0, -1]] = False
    found = impostor.folds(height, normal, known)
    check("a fold is found where the surface steps back by more than 2 cm, on the further pixel only", bool(found[:, 5].all()) and not found[:, 6:].any())
    check("... and where it turns by more than about 70 degrees", bool(found[4, 1:3].all()) and not found[0, :5].any())
    with open(os.path.join(REPO, "gallery", "looks.js")) as f:
        page = f.read()
    with open(os.path.join(REPO, "gallery", "impostor.js")) as f:
        shader = f.read()
    check("the page has the same numbers: a grid twice as fine from 40 big pixels a metre, how much darker a kept pixel must be, how near in depth", all(text in page for text in ("heads: %d" % impostor.FINE, "FINE_FROM = %g" % impostor.FINE_FROM))
          and all(text in shader for text in ("middle - %g" % impostor.KEEP_DARK, "< %g &&" % impostor.KEEP_M)))
    # sheets baked for it
    folders = sorted(glob.glob(os.path.join(runs, "*", "profiles", "*-impostor-pixel-clear", "impostor.json")))
    if not folders:
        print("    skipped  a sheet baked for the clear look (none in %s: just impostor-detailed <run> makes one)" % runs)
        return
    for path in folders:
        folder = os.path.dirname(path)
        who = "%s, %s" % (os.path.basename(os.path.dirname(os.path.dirname(folder))).split("-", 5)[-1], os.path.basename(folder).split("-impostor")[0])
        with open(path) as f:
            card = json.load(f)
        head = next(p for p in card["parts"] if p["name"] == "head")
        check("%s: the head is pictured at 192 pixels a metre, a whole number of times the body's, with its folds drawn in" % who,
              head.get("px_per_m") == 192.0 and (192.0 / card["px_per_m"]) % 1 == 0 and card.get("creases") == "head", "the body at %g" % card["px_per_m"])
        check("%s: the sheet has no more colours than it may: 32, and 16 more for the head" % who, 8 <= len(card["palette"]) <= 48, "%d colours" % len(card["palette"]))
        glb = os.path.join(os.path.dirname(folder), card["plays"] + "-walk.glb")
        if os.path.isfile(glb):
            character = impostor.Character(folder)
            pose = impostor.Glb(glb).pose(0.2)
            at = pose["hips"][:3, 3]
            eye = impostor.Eye([at[0] + 1.0, 1.3, at[2] + 4.0], [at[0], 0.95, at[2]], 30.0, (160, 180))
            picture, depth, shows, lines = impostor.draw_fine_heads(character, pose, eye, paint=impostor.PAINTS["pixel"])
            part = (shows - 1) % impostor.PARTS_A_FIGURE
            body = (shows > 0) & (part != [p["name"] for p in card["parts"]].index("head"))
            blocks = body.reshape(180, 2, 160, 2)
            whole = blocks.all(axis=(1, 3)) | ~blocks.any(axis=(1, 3))
            face = (shows > 0) & ~body
            check("%s: a frame of his walk draws with the head on the finer grid and the body in whole big pixels, bar where the head covers part of one" % who,
                  face.sum() > 300 and (~whole).sum() < 0.6 * math.sqrt(face.sum()) * 4, "%d fine pixels of head; %d big pixels are part body" % (face.sum(), (~whole).sum()))


def post(folder, kind, radius=0.05, tall=0.10, ppm=192.0):
    """A part for the filling, baked as two_plates is (every picture the same, facing its own eye), with a joint at
    its bone's head. kind "post": a round flat top `tall` above the bone's head, with nothing round it (its sides
    are what no picture saw). kind "cup": a rim at the bone's head round a hollow `tall` deep."""
    views = impostor.views_of("26")
    half = int(math.ceil(2 * radius * ppm)) + 2
    side = 2 * half
    ys, xs = np.mgrid[0:side, 0:side]
    x, y = (xs + 0.5 - half) / ppm, (ys + 0.5 - half) / ppm
    inner = x * x + y * y < radius * radius
    there = inner if kind == "post" else x * x + y * y < (2 * radius) ** 2
    z = np.where(inner, tall if kind == "post" else -tall, 0.0)
    depth_m = tall + 0.05
    cols = 6
    rows = (len(views) + cols - 1) // cols
    colour = np.zeros((rows * (side + 2) + 2, cols * (side + 2) + 2, 4), dtype=np.uint8)
    data = np.zeros(colour.shape[:2] + (3,), dtype=np.uint8)
    cells = []
    for i, view in enumerate(views):
        x0, y0 = 2 + (i % cols) * (side + 2), 2 + (i // cols) * (side + 2)
        normal = np.broadcast_to(np.array(view["d"]), x.shape + (3,))
        packed = np.concatenate([impostor.pack_normal(normal), np.clip(z / depth_m * 0.5 + 0.5, 1 / 255.0, 1.0)[..., None]], axis=-1)
        packed[~there] = (0.5, 0.5, 0.0)
        colour[y0:y0 + side, x0:x0 + side] = np.where(there[..., None], np.where(inner[..., None], (200, 120, 40, 255), (90, 90, 200, 255)), (0, 0, 0, 0))
        data[y0:y0 + side, x0:x0 + side] = np.round(packed * 255.0)
        cells.append([x0, y0, side, side, half, half, float(z.min()), float(z.max())])
    impostor.write_png(os.path.join(folder, "c.png"), colour)
    impostor.write_png(os.path.join(folder, "d.png"), data)
    card = {"px_per_m": ppm, "default_views": "26", "line_marked": True, "parts": [{"name": "a", "bone": "a", "center": [0, 0, 0], "depth_m": depth_m}],
            "joints": [{"bone": "j", "between": ["a", "gone"], "ring_cm": 12.0, "ball_cm": 100.0 * radius * 0.75 / impostor.FILL_INNER}],
            "sets": {"26": {"color": "c.png", "data": "d.png", "size": [colour.shape[1], colour.shape[0]], "views": views, "cells": {"a": cells}}}}
    with open(os.path.join(folder, "impostor.json"), "w") as f:
        json.dump(card, f)


def test_fill():
    keep = set(impostor.FILL)
    bone = np.eye(4)
    bone[:3, 3] = (0.2, 1.0, -0.1)
    far = np.eye(4)
    far[:3, 3] = (1.2, 1.0, -0.1)
    views = impostor.views_of("26")
    d = np.array(views[8]["d"])  # a picture taken from the side
    folder = tempfile.mkdtemp(prefix="impostor-test-")
    try:
        # a see-through pixel near a joint: the eye 25 degrees off a picture of a tall flat top looks in under its edge
        post(folder, "post")
        character = impostor.Character(folder)
        off = impostor.unit(d + 0.47 * np.array(views[8]["r"]))
        eye = impostor.Eye(bone[:3, 3] + 3.0 * off, bone[:3, 3], 8.0, (200, 200))
        per_px = eye.m_per_px(bone[:3, 3])
        impostor.FILL = set()
        bare, bare_depth, _ = impostor.draw(character, {"a": bone, "j": bone}, eye, forced={"a": 8})
        impostor.FILL = {"joint"}
        filled, depth, _ = impostor.draw(character, {"a": bone, "j": bone}, eye, forced={"a": 8})
        away, _, _ = impostor.draw(character, {"a": bone, "j": far}, eye, forced={"a": 8})
        was, now = bare[..., 3] > 0, filled[..., 3] > 0
        new = now & ~was
        check("a see-through pixel beside a tall top is filled when a joint is there", new.sum() > 0.3 * was.sum() and not (was & ~now).any(), "%d pixels more on %d" % (new.sum(), was.sum()))
        ys, xs = np.nonzero(new)
        at, _ = eye.to_pixels(bone[:3, 3])
        check("... only inside the joint's ball, behind the top, in the top's colour", bool(len(ys)) and float(np.hypot(xs + 0.5 - at[0], ys + 0.5 - at[1]).max()) < 0.12 / per_px + 1.0
              and float(depth[new].min()) > float(bare_depth[was].min()) and bool((filled[new][:, 0] > filled[new][:, 2]).all()),
              "furthest %.1f cm from the joint" % (100.0 * per_px * float(np.hypot(xs + 0.5 - at[0], ys + 0.5 - at[1]).max()) if len(ys) else 0.0))
        check("... and with the joint a metre away nothing is filled", bool((away == bare).all()))
        # the ball in a joint: a rim round a hollow, seen from straight in front
        post(folder, "cup")
        character = impostor.Character(folder)
        eye = impostor.Eye(bone[:3, 3] + 3.0 * d, bone[:3, 3], 8.0, (200, 200))
        per_px = eye.m_per_px(bone[:3, 3])
        impostor.FILL = set()
        hollow, hollow_depth, _ = impostor.draw(character, {"a": bone, "j": bone}, eye, forced={"a": 8})
        impostor.FILL = {"ball"}
        stopped, depth, _ = impostor.draw(character, {"a": bone, "j": bone}, eye, forced={"a": 8})
        changed = depth < hollow_depth - 0.01
        ys, xs = np.mgrid[0:200, 0:200]
        ball_px = impostor.FILL_INNER * character.card["joints"][0]["ball_cm"] / 100.0 / per_px
        true = (xs + 0.5 - 100) ** 2 + (ys + 0.5 - 100) ** 2 < ball_px ** 2
        check("a hollow gets the joint's ball in it, round and the right size", (changed & true).sum() / float((changed | true).sum()) > 0.9, "shares %.3f of the true disc" % ((changed & true).sum() / float((changed | true).sum())))
        nearest = 3.0 - impostor.FILL_INNER * character.card["joints"][0]["ball_cm"] / 100.0 + impostor.BALL_BACK_M / 2.0
        check("... its nearest point a ball's radius in front of the joint (and stood back half way: the part's middle is the joint)", abs(float(depth[100, 100]) - nearest) < 0.003 and float(hollow_depth[100, 100]) > 3.05, "%.3f m, the hollow %.3f" % (depth[100, 100], hollow_depth[100, 100]))
        check("... and the picture's outline is as it was: no ball where the part has no surface", bool(((stopped[..., 3] > 0) == (hollow[..., 3] > 0)).all()))
        tint = impostor.own_tint(character.card, character.sheet, character.parts[0], [0.0, 0.0, 0.0], 0.02, character.pixel)
        check("the ball takes the colour the part has round the place looked at (its hollow, here)", np.abs(np.array(tint) * 255.0 - (200, 120, 40)).max() < 1.0, str(tint))
    finally:
        impostor.FILL = keep
        shutil.rmtree(folder)
    joint, eye_at = np.array([0.0, 1.0, 0.0]), np.array([0.0, 1.0, 3.0])
    check("the part whose body is behind a ball, as the eye sees it, stands it nearest", impostor.ball_back(joint, joint + [0, 0, -0.2], eye_at) < 1e-9
          and abs(impostor.ball_back(joint, joint + [0, 0, 0.2], eye_at) - impostor.BALL_BACK_M) < 1e-9 and abs(impostor.ball_back(joint, joint + [0.2, 0, 0], eye_at) - impostor.BALL_BACK_M / 2) < 1e-9)
    # cracks on the finished picture
    names = impostor.PART_NAMES
    number = lambda part, figure=0: 1 + impostor.PARTS_A_FIGURE * figure + names.index(part)
    picture = np.zeros((9, 12, 4), dtype=np.uint8)
    depth = np.full((9, 12), np.inf, dtype=np.float32)
    who = np.zeros((9, 12), dtype=np.int32)

    def lay(rows, cols, part, colour, away, figure=0):
        picture[rows, cols], depth[rows, cols], who[rows, cols] = colour + (255,), away, number(part, figure)

    lay(slice(0, 3), slice(0, 5), "thigh_l", (10, 0, 0), 4.00)
    lay(slice(0, 3), slice(6, 12), "shin_l", (20, 0, 0), 4.03)       # row 1: a crack one pixel wide at a knee
    lay(slice(3, 6), slice(0, 5), "thigh_l", (10, 0, 0), 4.00)
    lay(slice(3, 6), slice(6, 12), "thigh_r", (30, 0, 0), 4.03)      # row 4: one pixel between the legs
    lay(slice(6, 9), slice(0, 4), "thigh_l", (10, 0, 0), 4.00)
    lay(slice(6, 9), slice(7, 12), "shin_l", (20, 0, 0), 4.03)       # row 7: a gap three pixels wide
    got, got_depth, got_who, filled = impostor.crack_fill(picture, depth, who, [(0, 1), (1, 0)])
    check("a crack a pixel wide between two parts that meet is filled, from the nearer of the two", bool(filled[0:3, 5].all()) and tuple(got[1, 5]) == (10, 0, 0, 255) and got_who[1, 5] == number("thigh_l") and abs(float(got_depth[1, 5]) - 4.0) < 1e-6)
    check("... one between the legs is not, and nor is a gap three pixels wide", not filled[3:6, 5].any() and not filled[6:9, 4:7].any() and int(filled.sum()) == 3)
    front = depth.copy()
    front[0:3, 5] = 3.5
    check("... nor a pixel that shows something in front of the two", not impostor.crack_fill(picture, front, who, [(0, 1), (1, 0)])[3].any())
    other = who.copy()
    other[0:3, 6:12] = number("shin_l", 1)
    check("... nor one between two figures", not impostor.crack_fill(picture, depth, other, [(0, 1), (1, 0)])[3][0:3].any())
    check("bold ink looks for a crack's two sides as far off as its thick line reaches, four ways", impostor.bold_offsets() == [(0, 3), (2, 2), (3, 0), (2, -2)])
    joined = impostor.JOINED
    check("parts meet as the skeleton has them: each with itself, a thigh with its shin and the hips, not with the other thigh", bool((joined == joined.T).all() and joined.diagonal().all()) and bool(joined[names.index("thigh_l"), names.index("shin_l")])
          and bool(joined[names.index("thigh_l"), names.index("hips")]) and not joined[names.index("thigh_l"), names.index("thigh_r")] and not joined[names.index("forearm_l"), names.index("hips")] and int(joined.sum()) == 16 + 2 * 15)
    # the page
    with open(os.path.join(REPO, "gallery", "impostor-math.js")) as f:
        page = f.read()
    with open(os.path.join(REPO, "gallery", "looks.js")) as f:
        looks = f.read()
    check("the page has the same numbers for the filling", "export const FILL = { ball: %s, backM: %g, inner: %g, tintReach: %g, tintIn: %g, ballBackM: %g, aPart: %d, zoneCore:" % (
        ("%.1f" % impostor.FILL_BALL), impostor.FILL_BACK_M, impostor.FILL_INNER, impostor.TINT_REACH, impostor.TINT_IN, impostor.BALL_BACK_M, impostor.BALLS_A_PART) in page
        and "export const CRACK = { behindM: %g, apartM: %g };" % (impostor.CRACK_BEHIND_M, impostor.CRACK_APART_M) in looks)
    node = shutil.which("node")
    if not node:
        print("    skipped  the page's filling against impostor.py (no node here)")
        return
    rng = np.random.default_rng(11)
    cells = [[int(rng.integers(0, 40)), int(rng.integers(0, 40)), int(rng.integers(30, 70)), int(rng.integers(30, 70)), int(rng.integers(10, 30)), int(rng.integers(10, 30)), 0.0, 0.1] for _ in views]
    card = {"px_per_m": 96.0, "parts": [{"name": "a", "bone": "a", "center": [0.01, 0.2, -0.02]}, {"name": "b", "bone": "b", "px_per_m": 192.0, "center": [0.0, 0.1, 0.0]}],
            "joints": [{"bone": "b", "between": ["b", "a"], "ring_cm": 9.5, "ball_cm": 6.2}, {"bone": "c", "between": ["c", "b"], "ring_cm": 4.0, "ball_cm": 3.1}]}
    sheet = {"views": views, "cells": {"a": cells, "b": cells}}
    pixel = lambda x, y: [(x * 7 + y * 13) % 256, (x * 3 + y * 5) % 256, (x + y * 11) % 256, 255 if (x + y) % 5 else 0]
    cases = [{"bone": some_bone(rng, float(rng.uniform(0.6, 1.5))).T.reshape(-1).tolist(), "at": rng.normal(size=3).tolist(), "eye": (rng.normal(size=3) * 3).tolist(),
              "place": (rng.normal(size=3) * 0.05).tolist(), "reach": float(rng.uniform(0.01, 0.06)), "part": int(rng.integers(2))} for _ in range(24)]
    script = """
      import { FILL, ownTint, tintPlace, inBone, ballBack, partBalls } from %s;
      import { JOINED, PART_NAMES } from %s;
      const { card, sheet, cases } = JSON.parse(await new Promise((done) => { let s = ""; process.stdin.on("data", (d) => (s += d)).on("end", () => done(s)); }));
      const pixel = (x, y) => [(x * 7 + y * 13) %% 256, (x * 3 + y * 5) %% 256, (x + y * 11) %% 256, (x + y) %% 5 ? 255 : 0];
      console.log(JSON.stringify({ joined: JOINED, names: PART_NAMES, balls: partBalls(card), cases: cases.map((c) => {
        const part = card.parts[c.part], middle = [c.bone[12], c.bone[13], c.bone[14]];
        return { tint: ownTint(card, sheet, part, c.place, c.reach, pixel), place: tintPlace(c.place, part.center, 0.1), inBone: inBone(c.bone, c.at), back: ballBack(c.at, middle, c.eye) };
      }) }));
    """ % (json.dumps("file://" + os.path.join(REPO, "gallery", "impostor-math.js")), json.dumps("file://" + os.path.join(REPO, "gallery", "looks.js")))
    # looks.js draws with three.js, which node has not got here: its tables are read with that one line left out
    shim = tempfile.mkdtemp(prefix="impostor-test-")
    try:
        with open(os.path.join(shim, "looks.mjs"), "w") as f:
            f.write(looks.replace('import * as THREE from "three";', "const THREE = { Color: class {}, Vector2: class {}, Vector3: class {} };"))
        script = script.replace(json.dumps("file://" + os.path.join(REPO, "gallery", "looks.js")), json.dumps("file://" + os.path.join(shim, "looks.mjs")))
        out = subprocess.run([node, "--input-type=module", "-e", script], input=json.dumps({"card": card, "sheet": sheet, "cases": cases}), capture_output=True, text=True)
    finally:
        shutil.rmtree(shim)
    if out.returncode:
        raise AssertionError("node could not run the page's filling:\n" + out.stderr[-800:])
    js = json.loads(out.stdout)
    bits = [sum(1 << b for b in range(impostor.PARTS_A_FIGURE) if joined[a, b]) for a in range(impostor.PARTS_A_FIGURE)]
    check("the page has the same parts in the same order, and the same table of which meet", js["names"] == names and js["joined"] == bits)
    mine = impostor.part_balls(card)
    check("... gives every part the same joints, each with the same two radii", [[(b["bone"], round(b["radius"], 9), round(b["inner"], 9)) for b in balls] for balls in js["balls"]]
          == [[(bone, round(ring, 9), round(inner, 9)) for bone, ring, inner in mine.get(part["name"], [])] for part in card["parts"]])
    worst, same = 0.0, True
    for case, got in zip(cases, js["cases"]):
        part = card["parts"][case["part"]]
        bone = np.array(case["bone"]).reshape(4, 4).T
        size = float(np.cbrt(abs(np.linalg.det(bone[:3, :3]))))
        same &= impostor.own_tint(card, sheet, part, case["place"], case["reach"], pixel) == got["tint"]
        for a, b in ((impostor.tint_place(case["place"], part["center"], 0.1), got["place"]), ((bone[:3, :3] / size).T @ (np.array(case["at"]) - bone[:3, 3]) / size, got["inBone"]),
                     ([impostor.ball_back(case["at"], bone[:3, 3], case["eye"])], [got["back"]])):
            worst = max(worst, float(np.abs(np.asarray(a) - np.asarray(b)).max()))
    check("... finds the same colour for a ball in the same pixels (24 cases)", same)
    check("... and looks for it in the same place, with the joint where the bone has it and the ball stood back as far", worst < 1e-9, "worst %.2g" % worst)


def test_skin(runs):
    folder = tempfile.mkdtemp(prefix="impostor-test-")
    try:
        radius = ball(folder)
        character = impostor.Character(folder)
        bone, joint = np.eye(4), np.eye(4)
        eye = impostor.Eye([0.0, 0.0, 3.0], [0.0, 0.0, 0.0], 8.0, (240, 240))
        per_px = eye.m_per_px([0.0, 0.0, 0.0])
        ys, xs = np.mgrid[0:240, 0:240]
        x, y = (xs + 0.5 - 120) * per_px, (ys + 0.5 - 120) * per_px
        pose = {"b": bone, "j": joint}
        plain, plain_depth, _ = impostor.draw(character, pose, eye)
        # a joint at the ball's middle whose zone holds all of it: only what is near the bone's line (y) is kept
        character.balls, character.zones = {"ball": [("j", 0.05, 0.0)]}, {"ball": [(0.2, 0.03)]}
        zoned, zoned_depth, _ = impostor.draw(character, pose, eye)
        kept = zoned[..., 3] > 0
        # ... which on a ball is its two ends: the surface within 3 cm of the line is that near its poles
        ends = (plain[..., 3] > 0) & (np.abs(y) > math.sqrt(radius ** 2 - 0.03 ** 2) + 0.6 * per_px)
        check("inside a joint's zone a card keeps only what is near its own bone's line", ends.sum() > 20 and (kept & ends).sum() >= 0.9 * ends.sum() and (kept & (np.abs(y) < math.sqrt(radius ** 2 - 0.03 ** 2) - 2 * per_px)).sum() == 0,
              "%d pixels kept, the two ends are %d" % (kept.sum(), ends.sum()))
        back = (zoned_depth - plain_depth)[kept & ends]
        check("... stood %g cm further back" % (impostor.ZONE_BACK_M * 100), float(np.abs(back - impostor.ZONE_BACK_M).max()) < 0.004, "%.3f to %.3f m" % (back.min(), back.max()))
        character.zones = {"ball": [(0.0, 0.0)]}
        check("with the zone off the card is as it was", np.array_equal(impostor.draw(character, pose, eye)[0], plain))
        joint_far = np.eye(4)
        joint_far[:3, 3] = (0.0, 1.0, 0.0)
        character.zones = {"ball": [(0.2, 0.03)]}
        check("... and so is a card outside the zone", np.array_equal(impostor.draw(character, {"b": bone, "j": joint_far}, eye)[0], plain))
        character.balls, character.zones = {}, {}

        # a piece: a tube 5 cm thick along y, pulled by bone "lo" below y = 0 and bone "j" above it
        around, rings = 24, 41
        angle = np.arange(around) * 2 * math.pi / around
        points = np.array([[0.05 * math.cos(a), -0.2 + 0.4 * r / (rings - 1), 0.05 * math.sin(a)] for r in range(rings) for a in angle])
        tris = []
        for r in range(rings - 1):
            for a in range(around):
                p, q = r * around + a, r * around + (a + 1) % around
                tris += [[p, p + around, q], [q, p + around, q + around]]  # counted so each faces outward
        upper = np.clip(points[:, 1] / 0.04 * 0.5 + 0.5, 0.0, 1.0)
        skin = impostor.Skin.__new__(impostor.Skin)
        skin.bones, skin.inverse = ["lo", "j"], np.stack([np.eye(4), np.eye(4)])
        skin.pieces = {"j": (points, np.full((len(points), 2), 0.5), np.tile([0, 1, 0, 0], (len(points), 1)), np.stack([1.0 - upper, upper, 0 * upper, 0 * upper], axis=1), np.array(tris))}
        skin.colour = np.full((4, 4, 4), 0.8, dtype=np.float32)
        skin.facing = np.tile(np.array([0.0, 0.0, 1.0], dtype=np.float32), (4, 4, 1))
        skin.joints = [{"bone": "j", "between": ["ball", "ball"], "part": "ball", "reach_cm": 12.0}]
        character.skin = skin

        def piece(pose, flip=False):
            colour, depth, who = np.zeros((240, 240, 3), dtype=np.float32), np.full((240, 240), np.inf, dtype=np.float32), np.zeros((240, 240), dtype=np.int32)
            if flip:
                skin.pieces["j"] = skin.pieces["j"][:4] + (np.array(tris)[:, ::-1],)
            impostor.draw_skin(character, pose, eye, colour, depth, who)
            skin.pieces["j"] = skin.pieces["j"][:4] + (np.array(tris),)
            return depth, who

        rest = {"b": bone, "lo": np.eye(4), "j": np.eye(4)}
        depth, who = piece(rest)
        there = np.isfinite(depth)
        tall = (np.abs(y[there]).max() + per_px) if there.any() else 0.0
        check("a piece is drawn only within its reach of the joint", there.any() and abs(tall - math.sqrt(0.12 ** 2 - 0.05 ** 2)) < 0.012 and abs(np.abs(x[there]).max() - 0.05) < 0.004, "it reaches %.3f m up and down" % tall)
        check("... from outside only: its near wall, never its far one", float(depth[there].max()) < 3.0 and abs(float(depth[120, 120]) - 2.95) < 0.004, "%.3f to %.3f m off" % (depth[there].min(), depth[there].max()))
        inside_out = piece(rest, flip=True)[0]
        check("... and turned inside out, only the wall that then faces the eye, the far one", float(inside_out[np.isfinite(inside_out)].min()) > 3.0)
        check("it says it is the card below the joint", set(np.unique(who)) == {0, 1})
        bent = np.eye(4)
        bent[:3, :3] = impostor.about([0.0, 0.0, 1.0], math.radians(90.0))
        at, _ = skin.stood("j", {"lo": np.eye(4), "j": bent})
        top, low = points[:, 1] > 0.05, points[:, 1] < -0.05
        check("the bone above bends its end of the piece, and the other end stays", float(np.abs(at[top] - points[top] @ bent[:3, :3].T).max()) < 1e-9 and float(np.abs(at[low] - points[low]).max()) < 1e-9)
        character.skin = None
    finally:
        shutil.rmtree(folder)

    card = {"parts": [{"name": n} for n in ("thigh_l", "shin_l", "foot_l")], "joints": [{"bone": "shin_l", "between": ["shin_l", "thigh_l"], "ring_cm": 7.0, "ball_cm": 4.0}, {"bone": "foot_l", "between": ["foot_l", "shin_l"], "ring_cm": 5.0, "ball_cm": 3.0}],
            "skin": {"joints": [{"bone": "shin_l", "zone_cm": 11.2}]}}
    zones = impostor.part_zones(card)
    near = lambda got, want: len(got) == len(want) and all(abs(a - b) < 1e-9 for g, w in zip(got, want) for a, b in zip(g, w))
    check("a part's joints with a piece have a zone and a core, and the others none", near(zones["shin_l"], [(0.112, impostor.ZONE_CORE * 0.07), (0.0, 0.0)]) and near(zones["foot_l"], [(0.0, 0.0)]) and near(zones["thigh_l"], [(0.112, impostor.ZONE_CORE * 0.07)]))
    node = shutil.which("node")
    if not node:
        print("    skipped  the page's zones against impostor.py (no node here)")
    else:
        with open(os.path.join(REPO, "gallery", "looks.js")) as f:
            looks = f.read()
        shim = tempfile.mkdtemp(prefix="impostor-test-")
        try:
            with open(os.path.join(shim, "looks.mjs"), "w") as f:
                f.write(looks.replace('import * as THREE from "three";', "const THREE = { Color: class {}, Vector2: class {}, Vector3: class {} };"))
            script = """
              import { partBalls, jointNumber, FILL } from %s;
              import { bakedFor, lookOf } from %s;
              const card = JSON.parse(await new Promise((done) => { let s = ""; process.stdin.on("data", (d) => (s += d)).on("end", () => done(s)); }));
              const folders = (names) => ({ cards: names.map((n) => ({ profile: "detailed", plays: "lowpoly", folder: "profiles/detailed-impostor" + n })) });
              const all = folders(["", "-comic-joined", "-comic-skinned", "-joe-joined", "-joe-skinned", "-pixel-joined", "-pixel-skinned", "-pixel-clear", "-pixel-clear-skinned"]);
              const old = folders(["", "-comic-joined", "-joe-joined", "-pixel-joined", "-pixel-clear"]);
              console.log(JSON.stringify({ balls: partBalls(card), on: jointNumber(0.07, 0.004, true), off: jointNumber(0.07, 0.004, false), fill: FILL,
                picked: ["comic", "pixel-baked", "pixel-screen", "pixel-both", "joe"].map((id) => bakedFor(all, lookOf(id), "detailed").folder),
                before: ["comic", "pixel-baked", "pixel-both", "joe"].map((id) => bakedFor(old, lookOf(id), "detailed").folder) }));
            """ % (json.dumps("file://" + os.path.join(REPO, "gallery", "impostor-math.js")), json.dumps("file://" + os.path.join(shim, "looks.mjs")))
            out = subprocess.run([node, "--input-type=module", "-e", script], input=json.dumps(card), capture_output=True, text=True)
        finally:
            shutil.rmtree(shim)
        if out.returncode:
            raise AssertionError("node could not run the page's zones:\n" + out.stderr[-800:])
        js = json.loads(out.stdout)
        check("the page gives every part the same zones", [[(round(b["zone"], 9), round(b["core"], 9)) for b in balls] for balls in js["balls"]] == [[(round(z, 9), round(c, 9)) for z, c in zones.get(part["name"], [])] for part in card["parts"]])
        check("... has the same numbers for a zone's core and how far back it stands", js["fill"]["zoneCore"] == impostor.ZONE_CORE and js["fill"]["zoneBackM"] == impostor.ZONE_BACK_M)
        check("... turns a joint's number negative when its zone is on, and leaves the number itself alone", js["on"] == -js["off"] and js["off"] > 0 and math.floor(js["off"]) == 70)
        tail = lambda names: [n.split("-impostor")[1] for n in names]
        check("... reads the cards that have pieces first, each look its own", tail(js["picked"]) == ["-comic-skinned", "-pixel-skinned", "-comic-skinned", "-pixel-clear-skinned", "-joe-skinned"], str(tail(js["picked"])))
        check("... and the cards it read before when there are none with pieces", tail(js["before"]) == ["-comic-joined", "-pixel-joined", "-pixel-clear", "-joe-joined"], str(tail(js["before"])))

    found = sorted(glob.glob(os.path.join(runs, "*", "profiles", "*-impostor-joe-skinned", "impostor.json")))
    if not found:
        print("    skipped  baked pieces (no profiles/*-impostor-joe-skinned under %s)" % runs)
        return
    folder = os.path.dirname(found[0])
    character = impostor.Character(folder)
    skin, said = character.skin, character.card["skin"]
    check("cards with pieces: every joint named has a piece, a few hundred triangles each", all(j["bone"] in skin.pieces and 60 <= len(skin.pieces[j["bone"]][4]) <= 1400 for j in said["joints"]) and len(said["joints"]) >= 4,
          ", ".join("%s %d" % (j["bone"], len(skin.pieces.get(j["bone"], ((), (), (), (), ()))[4])) for j in said["joints"]))
    walk = impostor.Glb(os.path.join(os.path.dirname(folder), "%s-walk.glb" % character.card["plays"]))
    rest = impostor.Glb(os.path.join(os.path.dirname(folder), character.card["source"])).pose(None)
    worst = 0.0
    for j in said["joints"]:
        at, _ = skin.stood(j["bone"], rest)
        tris = skin.pieces[j["bone"]][4]
        middle = at[tris].mean(axis=1)
        worst = max(worst, float(np.linalg.norm(middle - rest[j["bone"]][:3, 3], axis=1).min()) - j["reach_cm"] / 100.0)
        check_ok = float((np.linalg.norm(at[tris] - rest[j["bone"]][:3, 3], axis=2).min(axis=1) < j["reach_cm"] / 100.0 + 0.011).mean())
        worst = max(worst, 1.0 - check_ok)
    check("... every one lying within reach of its joint as the model rests", worst < 0.02, "worst %.3f" % worst)
    pose = walk.pose(walk.seconds * 0.3)
    eye = impostor.Eye(pose["hips"][:3, 3] + np.array([1.6, 0.3, 3.2]), pose["hips"][:3, 3], 30.0, (300, 400))
    with_pieces = impostor.draw(character, pose, eye)[0][..., 3] > 0
    character.skin, zones = None, character.zones
    character.zones = {}
    without = impostor.draw(character, pose, eye)[0][..., 3] > 0
    character.skin, character.zones = skin, zones
    check("... and a frame of the walk drawn with them covers what it covered without", abs(with_pieces.sum() / float(without.sum()) - 1.0) < 0.03 and (without & ~with_pieces).sum() < 0.03 * without.sum(),
          "%d pixels with, %d without, %d lost" % (with_pieces.sum(), without.sum(), (without & ~with_pieces).sum()))


def brim_over_plate(folder, radius=0.1, brim=0.04, up=0.08, ppm=192.0):
    """A round plate through its bone's head with a smaller one (a brim) standing in front of its middle, baked two
    layers deep: the first layer is the brim where it covers the plate and the plate elsewhere; the layer behind is
    the plate under the brim, a picture of its own cut down to that."""
    views = impostor.views_of("26")
    half, small = int(math.ceil(radius * ppm)) + 2, int(math.ceil(brim * ppm)) + 1
    side = 2 * half
    ys, xs = np.mgrid[0:side, 0:side]
    x, y = (xs + 0.5 - half) / ppm, (ys + 0.5 - half) / ppm
    plate, over = x * x + y * y < radius * radius, x * x + y * y < brim * brim
    depth_m = radius + 0.02
    cols = 6
    rows = (len(views) + cols - 1) // cols
    colour = np.zeros((2 * rows * (side + 2) + 2, cols * (side + 2) + 2, 4), dtype=np.uint8)
    data = np.zeros(colour.shape[:2] + (3,), dtype=np.uint8)
    cells, behind = [], []
    high = lambda z: np.clip(z / depth_m * 0.5 + 0.5, 1 / 255.0, 1.0)
    for i, view in enumerate(views):
        x0, y0 = 2 + (i % cols) * (side + 2), 2 + (i // cols) * (side + 2)
        facing = impostor.pack_normal(np.broadcast_to(np.array(view["d"]), x.shape + (3,)))
        packed = np.concatenate([facing, high(np.where(over, up, 0.0))[..., None]], axis=-1)
        packed[~plate] = (0.5, 0.5, 0.0)
        colour[y0:y0 + side, x0:x0 + side] = np.where(over[..., None], (40, 60, 220, 255), np.where(plate[..., None], (200, 200, 200, 255), (0, 0, 0, 0)))
        data[y0:y0 + side, x0:x0 + side] = np.round(packed * 255.0)
        cells.append([x0, y0, side, side, half, half, 0.0, up])
        # the layer behind: the plate where the brim hid it
        y1 = y0 + rows * (side + 2)
        cut = slice(half - small, half + small)
        under = np.concatenate([facing, high(np.zeros_like(x))[..., None]], axis=-1)
        under[~over] = (0.5, 0.5, 0.0)
        colour[y1:y1 + 2 * small, x0:x0 + 2 * small] = np.where(over[..., None], (200, 200, 200, 255), (0, 0, 0, 0))[cut, cut]
        data[y1:y1 + 2 * small, x0:x0 + 2 * small] = np.round(under * 255.0)[cut, cut]
        behind.append([x0, y1, 2 * small, 2 * small, small, small, 0.0, 0.0])
    impostor.write_png(os.path.join(folder, "c.png"), colour)
    impostor.write_png(os.path.join(folder, "d.png"), data)
    card = {"px_per_m": ppm, "default_views": "26", "layers": 2, "parts": [{"name": "hat", "bone": "b", "center": [0, 0, 0], "depth_m": depth_m}],
            "sets": {"26": {"color": "c.png", "data": "d.png", "size": [colour.shape[1], colour.shape[0]], "views": views, "cells": {"hat": cells}, "behind": [{"hat": behind}]}}}
    with open(os.path.join(folder, "impostor.json"), "w") as f:
        json.dump(card, f)
    return radius, brim, up


def test_layers(runs):
    folder = tempfile.mkdtemp(prefix="impostor-test-")
    try:
        radius, brim, up = brim_over_plate(folder)
        bone = np.eye(4)
        bone[:3, 3] = (0.2, 1.0, -0.1)
        tilt = math.radians(20.0)
        eye = impostor.Eye(bone[:3, 3] + 3.0 * np.array([math.sin(tilt), 0.0, math.cos(tilt)]), bone[:3, 3], 6.0, (240, 240))
        # where the plate truly shows: every point of it, a little in from its edge, put through the eye
        rs, around = np.meshgrid(np.linspace(0.0, radius - 0.006, 120), np.linspace(0.0, 2.0 * math.pi, 720))
        spots, _ = eye.to_pixels(bone[:3, 3] + np.stack([rs * np.cos(around), rs * np.sin(around), np.zeros_like(rs)], axis=-1).reshape(-1, 3))
        true = np.zeros((240, 240), dtype=bool)
        true[np.floor(spots[:, 1]).astype(int), np.floor(spots[:, 0]).astype(int)] = True
        drawn = {}
        for label, on in (("first", False), ("both", True)):
            impostor.LAYERS = on
            picture, depth, _ = impostor.draw(impostor.Character(folder), {"b": bone}, eye, forced={"hat": 8})
            drawn[label] = picture
        impostor.LAYERS = True
        bare = {label: true & ~(picture[..., 3] > 0) for label, picture in drawn.items()}
        check("a brim in front of a plate, seen from 20 degrees to one side with one layer: the plate behind the brim's edge is a hole", bare["first"].sum() > 300, "%d pixels" % bare["first"].sum())
        check("... with the layer behind it is filled, bar a speck at each tip", bare["both"].sum() < 0.04 * bare["first"].sum(), "%d pixels left of %d" % (bare["both"].sum(), bare["first"].sum()))
        filled = bare["first"] & ~bare["both"]
        grey = drawn["both"][filled][:, :3].astype(int)
        check("... what fills it is the plate, in the plate's colour, not the brim's", bool(len(grey)) and float((np.abs(grey[:, 0] - grey[:, 2]) < 12).mean()) > 0.97, "%.0f%% grey" % (100.0 * (np.abs(grey[:, 0] - grey[:, 2]) < 12).mean()))
        same = (drawn["first"][..., 3] > 0) & ~filled
        check("... and nothing else of the picture changes", bool((drawn["first"][same] == drawn["both"][same]).all()) and not ((drawn["both"][..., 3] > 0) & ~(drawn["first"][..., 3] > 0) & ~filled).any())
        cell, low = [3, 4, 50, 60, 25, 30, -0.05, 0.12], [9, 9, 20, 20, 10, 10, -0.21, -0.1]
        check("a card's corners make room for a layer that stands lower than the first, and the search goes on down for it", impostor.deepest(cell, [low])[6] == -0.21 and impostor.deepest(cell, [low])[:6] == cell[:6]
              and impostor.deepest(cell, []) is cell and impostor.march_more(20, cell, [low]) == min(impostor.MARCH_MORE, math.ceil(0.16 * 20 / 0.174)) and impostor.march_more(20, cell, []) == 0)
        with open(os.path.join(REPO, "gallery", "impostor.js")) as f:
            page = f.read()
        check("the page's shader searches the layer behind too", all(text in page for text in ("uniform vec4 cellB;", "bool readB(", "MARCH_MORE_", "heightWas - heightNow > wallM")))
    finally:
        impostor.LAYERS = True
        shutil.rmtree(folder)
    node = shutil.which("node")
    if not node:
        print("    skipped  the page's layers against impostor.py (no node here)")
    else:
        with open(os.path.join(REPO, "gallery", "looks.js")) as f:
            looks = f.read()
        shim = tempfile.mkdtemp(prefix="impostor-test-")
        try:
            with open(os.path.join(shim, "looks.mjs"), "w") as f:
                f.write(looks.replace('import * as THREE from "three";', "const THREE = { Color: class {}, Vector2: class {}, Vector3: class {} };"))
            script = """
              import { behindOf, deepest, marchMore, MARCH_MORE } from %s;
              import { bakedFor, lookOf } from %s;
              const folders = (names) => ({ cards: names.map((n) => ({ profile: "detailed", plays: "lowpoly", folder: "profiles/detailed-impostor" + n })) });
              const old = ["", "-comic-joined", "-comic-skinned", "-joe-joined", "-joe-skinned", "-pixel-joined", "-pixel-skinned", "-pixel-clear", "-pixel-clear-skinned"];
              const all = folders([...old, "-comic-layered", "-comic-layered-skinned", "-joe-layered", "-joe-layered-skinned", "-pixel-layered", "-pixel-layered-skinned", "-pixel-clear-layered", "-pixel-clear-layered-skinned"]);
              const bare = folders([...old, "-joe-layered", "-pixel-clear-layered"]);
              const ids = ["comic", "pixel-baked", "pixel-screen", "pixel-both", "joe"];
              const cell = [3, 4, 50, 60, 25, 30, -0.05, 0.12], low = [9, 9, 20, 20, 10, 10, -0.21, -0.1];
              const sheet = { behind: [{ hat: [low, [0, 0, 0, 0, 0, 0, 0, 0]] }] };
              console.log(JSON.stringify({ most: MARCH_MORE, deep: deepest(cell, low), same: deepest(cell, null) === cell, more: [marchMore(20, cell, low), marchMore(20, cell, null), marchMore(400, cell, low)],
                behind: [behindOf(sheet, "hat", 0), behindOf(sheet, "hat", 1), behindOf(sheet, "head", 0), behindOf({}, "hat", 0)],
                picked: ids.map((id) => bakedFor(all, lookOf(id), "detailed").folder), off: ids.map((id) => bakedFor(all, lookOf(id), "detailed", false).folder),
                bare: ids.map((id) => bakedFor(bare, lookOf(id), "detailed").folder) }));
            """ % (json.dumps("file://" + os.path.join(REPO, "gallery", "impostor-math.js")), json.dumps("file://" + os.path.join(shim, "looks.mjs")))
            out = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True)
        finally:
            shutil.rmtree(shim)
        if out.returncode:
            raise AssertionError("node could not run the page's layers:\n" + out.stderr[-800:])
        js = json.loads(out.stdout)
        cell, low = [3, 4, 50, 60, 25, 30, -0.05, 0.12], [9, 9, 20, 20, 10, 10, -0.21, -0.1]
        check("the page makes the same room for a lower layer and takes as many steps more", js["most"] == impostor.MARCH_MORE and js["deep"] == impostor.deepest(cell, [low]) and js["same"]
              and js["more"] == [impostor.march_more(20, cell, [low]), 0, impostor.march_more(400, cell, [low])] and js["more"][2] == impostor.MARCH_MORE)
        check("... and finds a picture's layer behind only where it has one", js["behind"] == [low, None, None, None])
        tail = lambda names: [n.split("-impostor")[1] for n in names]
        check("the page reads layered cards first, with their pieces, each look its own", tail(js["picked"]) == ["-comic-layered-skinned", "-pixel-layered-skinned", "-comic-layered-skinned", "-pixel-clear-layered-skinned", "-joe-layered-skinned"], str(tail(js["picked"])))
        check("... layered cards without pieces before unlayered ones with, and only the looks that have them", tail(js["bare"]) == ["-comic-skinned", "-pixel-skinned", "-comic-skinned", "-pixel-clear-layered", "-joe-layered"], str(tail(js["bare"])))
        check("... and with the layers switched off, what it read before", tail(js["off"]) == ["-comic-skinned", "-pixel-skinned", "-comic-skinned", "-pixel-clear-skinned", "-joe-skinned"], str(tail(js["off"])))
    found = sorted(glob.glob(os.path.join(runs, "*", "profiles", "*-impostor-joe-layered", "impostor.json")))
    if not found:
        print("    skipped  baked layers (no profiles/*-impostor-joe-layered under %s)" % runs)
        return
    folder = os.path.dirname(found[0])
    character = impostor.Character(folder)
    sheet = character.sheet
    wide, tall = sheet["size"]
    behind = sheet["behind"][0]
    held = [c for row in behind.values() for c in row if c[2] > 0]
    check("baked layers: a layer behind for every part and picture, each inside the sheet, some of them holding something",
          set(behind) == set(sheet["cells"]) and all(len(behind[n]) == len(sheet["cells"][n]) for n in behind) and all(c[0] >= 0 and c[1] >= 0 and c[0] + c[2] <= wide and c[1] + c[3] <= tall for c in held) and len(held) > 20,
          "%d of %d pictures have one" % (len(held), sum(len(row) for row in behind.values())))
    under = sum(c[2] * c[3] for c in held) / float(sum(c[2] * c[3] for row in sheet["cells"].values() for c in row))
    check("... taking well under half the room the first layer takes", sheet["behind_share"] < 0.5 and under < 0.5, "%.0f%% as much" % (100.0 * under))
    lower = all(b[7] <= c[7] + 1e-6 for n in behind for b, c in zip(behind[n], sheet["cells"][n]) if b[2] > 0)
    check("... and never standing higher than the first layer's highest", lower)
    before = folder[:-len("-layered")] + "-joined"
    if os.path.isfile(os.path.join(before, "impostor.json")):
        with open(os.path.join(before, "impostor.json")) as f:
            was = json.load(f)
        check("... the first layer is the sheet that was there before, picture for picture", {n: [c[2:] for c in row] for n, row in was["sets"][character.set_name]["cells"].items()} == {n: [c[2:] for c in row] for n, row in sheet["cells"].items()})
    walk = impostor.Glb(os.path.join(os.path.dirname(folder), "%s-walk.glb" % character.card["plays"]))
    pose = walk.pose(walk.seconds * 0.3)
    eye = impostor.Eye(pose["hips"][:3, 3] + np.array([1.6, 0.9, 3.2]), pose["hips"][:3, 3], 30.0, (300, 400))
    both = impostor.draw(character, pose, eye)[0][..., 3] > 0
    impostor.LAYERS = False
    try:
        first = impostor.draw(impostor.Character(folder), pose, eye)[0][..., 3] > 0
    finally:
        impostor.LAYERS = True
    check("... a frame of the walk drawn with the layers covers all it covered without, and a little more", not (first & ~both).any() and both.sum() >= first.sum(), "%d pixels more" % (both.sum() - first.sum()))


def main():
    runs = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "runs")
    cases = [("views", test_views), ("packing", test_packing), ("choosing", test_choosing), ("placing", test_placing), ("drawing", test_drawing),
             ("page", test_page), ("joints", test_joints), ("fill", test_fill), ("layers", lambda: test_layers(runs)), ("skin", lambda: test_skin(runs)), ("faces", lambda: test_faces(runs)), ("clear", lambda: test_clear(runs)), ("baked", lambda: test_baked(runs))]
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
