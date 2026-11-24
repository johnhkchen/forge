"""Counts how much of a face is left when a character is drawn as flat cards: eyes, brows, mouth, spectacles, a patch.

    Blender -b --factory-startup -P scripts/impostor/judge_faces.py -- --out <folder> [--tag before]
        [--runs runs] [--shots shots] [--take crew-candy-shop] [--model detailed] [--times 9,13.5,18,...]
        [--eyes crew,two,close] [--looks joe,pixel-both] [--pixel old|new] [--sheet NAME] [--why] [--only left,right]
        [--stills frontman@24:crew,...]

For every one of the take's cast, at each of --times seconds of it, through three eyes (the set's crew camera;
2 m from his head; 1 m from it, both on the crew camera's side), it draws him twice from the same eye: the real
model his cards were pictured from, posed by the same bones and drawn the comic way by toon.py, twice as fine as
the screen; and as cards, by impostor.py (the page's own arithmetic, paint and lines), in bold ink and in
"Pixels, both". Then, for each feature of his face (the "features" of his recipe in scripts/impostor/faces/: where
the model's own eyes, brows, nose, mouth, spectacles or patch are, stood on the head as the bake stands a mark), it measures

    kept      how well the light and dark of the feature and the skin just round it follows the real model's there,
              from 0 (nothing in common) to 1 (the same shape in the same place): an eye that has become a dot
              under a brow that is gone keeps little. The cards' picture may sit up to a centimetre off the
              model's and still count.
    shows     how much darker (or lighter) than the skin round it the feature is, as a share of how much it is
              in the real model's (no more than 1): whether there is anything there at all
    likeness  as `kept`, for the whole face at once (everything within 2 cm of a feature)

A feature turned away from the eye, or behind a hand or a hat's brim (by the cards' own depth), is not counted,
and neither is one the real model itself hardly shows (under 6 parts in 255 from its skin). `crawl` is how much
`kept` changes when the same picture is drawn with the grid of big pixels slid a part of a pixel, three ways: a
face whose features come and go as he moves has a high one.

--pixel old draws "Pixels, both" as the page did before the head had a grid of its own (one grid of big pixels
for all of him, the <model>-impostor-pixel-joined sheet); new (the default) reads <model>-impostor-pixel-clear
when it is there and draws the head on a grid twice as fine (impostor.py: draw_fine_heads).

--why (with --pixel old) also draws "Pixels, both" with one thing changed at a time, to say where a face is lost:
without the line on the finished picture; without cutting the colours to twelve steps; on a grid twice as fine;
from the comic sheet (192 pixels a metre, the model's own texture, no drawn face, no 32 colours) on the same grid.

Writes <out>/faces[-tag].json and, for --stills, <tag>-judged-<role>-<seconds>-<eye>.png: the real model, bold
ink and the pixel look side by side with every counted feature boxed. Never touches an open Blender.
"""

import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import impostor  # noqa: E402
import pixel_face  # noqa: E402

SIZE = (1080, 608)
FINER = 2            # the real model is drawn this many times finer than the screen
K = 2                # screen pixels to one of the pixel look's big ones, at this size (looks.js: 270 rows)
OFF_M = 0.01         # the cards' picture may sit this far from the model's
ROUND_M = 0.02       # the face, for likeness: everything within this of a feature
LEAST = 6.0          # a feature the real model shows less than this (of 255) is not counted
LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
PAPER = (250, 248, 245)
KINDS = (("eye", "eyes"), ("brow", "brows"), ("glass", "spectacles"), ("bridge", "spectacles"), ("patch", "patch"), ("mouth", "mouth"), ("moustache", "moustache"), ("nose", "nose"))


def kind_of(name):
    return next((kind for start, kind in KINDS if name.startswith(start)), "other")


def features_of(recipe, character):
    """The recipe's marks stood on the head, as the bake stands them: [{name, kind, p, n, size}] in the head bone's
    frame. How far forward the face is at each is read off the head's own picture from straight in front."""
    part = next(p for p in character.parts if p["name"] == "head")
    ppm = float(part.get("px_per_m") or character.px_per_m)
    vi = int(np.argmax(character.dirs[:, 2]))
    x0, y0, w, h, ax, ay, _, _ = character.cells["head"][vi]
    data = character.data[y0:y0 + h, x0:x0 + w]

    def front_at(x, y):
        cx, cy = int(math.floor(x * ppm + ax)), int(math.floor(y * ppm + ay))
        if not (0 <= cx < w and 0 <= cy < h) or data[cy, cx, 2] <= 0.5 / 255.0:
            return None
        return float((data[cy, cx, 2] * 2.0 - 1.0) * part["depth_m"])

    return [{"name": m["name"], "kind": kind_of(m["name"]), "p": np.array(m["p"]), "n": np.array(m["n"]), "size": m["size"]}
            for m in pixel_face.place(dict(recipe, marks=recipe.get("features") or recipe.get("marks", [])), front_at) if m["kind"] != "wash"]


def eye_for(name, crew, crew_fov, pose, size):
    """The judge's three eyes (scripts/impostor/clear_shots.py stands the watch page's the same way)."""
    head = pose["head"][:3, 3] + np.array([0.0, 0.1, 0.0])
    if name == "crew":
        return impostor.Eye(np.array(crew["at"], dtype=float), np.array(crew["aim"], dtype=float), crew_fov, size)
    toward = np.array([crew["at"][0] - head[0], 0.0, crew["at"][2] - head[2]])
    toward /= np.linalg.norm(toward)
    if name == "two":
        return impostor.Eye(head + 2.0 * toward + np.array([0.0, 0.05, 0.0]), head - np.array([0.0, 0.25, 0.0]), 36.0, size)
    return impostor.Eye(head + 1.0 * toward + np.array([0.0, 0.05, 0.0]), head, 36.0, size)


def luma(picture):
    """How light each pixel is, 0 to 255 as the eye sees it, a picture with nothing there counted as paper."""
    cover = picture[..., 3:4].astype(np.float32) / 255.0
    return (picture[..., :3].astype(np.float32) * cover + np.array(PAPER, dtype=np.float32) * (1.0 - cover)) @ LUMA


def blown(picture, times):
    return picture if times == 1 else np.repeat(np.repeat(picture, times, axis=0), times, axis=1)


def boxes_of(features, head, eye, depth, scale):
    """Where each feature is in the fine picture: [(feature, x0, x1, y0, y1)] for the ones that face the eye and that
    nothing stands in front of. `depth` is the cards' own (bold ink, at the screen's size)."""
    out, hidden, turned = [], 0, 0
    for f in features:
        p, n = head[:3, :3] @ f["p"] + head[:3, 3], impostor.unit(head[:3, :3] @ f["n"])
        if n @ impostor.unit(eye.at - p) < 0.3:
            turned += 1
            continue
        across = impostor.unit(np.cross([0.0, 1.0, 0.0], f["n"]))
        ends = np.array([head[:3, :3] @ (f["p"] + across * sx * f["size"][0] / 2.0 + np.array([0.0, 1.0, 0.0]) * sy * f["size"][1] / 2.0) + head[:3, 3] for sx in (-1, 1) for sy in (-1, 1)])
        spots, ahead = eye.to_pixels(ends)
        centre, away = eye.to_pixels(p)
        cx, cy = int(centre[0]), int(centre[1])
        if not (2 <= cx < eye.size[0] - 2 and 2 <= cy < eye.size[1] - 2):
            turned += 1
            continue
        if depth[cy, cx] < away - 0.045:  # a hand, a brim: something of him stands in front of it
            hidden += 1
            continue
        x0, x1, y0, y1 = spots[:, 0].min() * scale, spots[:, 0].max() * scale, spots[:, 1].min() * scale, spots[:, 1].max() * scale
        grow = lambda a, b: (a, b) if b - a >= 3.0 else ((a + b) / 2.0 - 1.5, (a + b) / 2.0 + 1.5)
        (x0, x1), (y0, y1) = grow(x0, x1), grow(y0, y1)
        out.append((f, int(round(x0)), int(round(x1)), int(round(y0)), int(round(y1))))
    return out, hidden, turned


def stands_out(light, inside, around, dx=0, dy=0):
    """How much lighter the skin round a feature is than the feature, in a picture slid (dx, dy)."""
    tall, wide = light.shape
    ys, xs = np.nonzero(inside)
    ya, xa = np.nonzero(around)
    return float(light[np.clip(ya + dy, 0, tall - 1), np.clip(xa + dx, 0, wide - 1)].mean() - light[np.clip(ys + dy, 0, tall - 1), np.clip(xs + dx, 0, wide - 1)].mean())


def soft(a, r):
    """Each pixel the mean of the square of pixels r either side of it."""
    if r < 1:
        return a
    pad = np.pad(a, r, mode="edge")
    total = np.cumsum(np.cumsum(pad, axis=0), axis=1)
    total = np.pad(total, ((1, 0), (1, 0)))
    n = 2 * r + 1
    return (total[n:, n:] - total[:-n, n:] - total[n:, :-n] + total[:-n, :-n]) / float(n * n)


def judge(real, picture, boxes, per_px):
    """One cards' picture against the real model's (both the fine size): {feature name: kept}, the likeness of the
    whole face, and {feature name: shows}."""
    truth, mine = luma(real), luma(picture)
    there = real[..., 3] > 127
    tall, wide = truth.shape
    taken = np.zeros_like(there)
    for _, x0, x1, y0, y1 in boxes:
        taken[max(0, y0):y1, max(0, x0):x1] = True
    reach = max(1, int(round(OFF_M / per_px)))
    slides = [(dx, dy) for dx in range(-reach, reach + 1, max(1, reach // 2)) for dy in range(-reach, reach + 1, max(1, reach // 2))]
    kept, shows = {}, {}
    blur = max(1, int(round(0.004 / per_px)))
    soft_truth, soft_mine = soft(truth, blur), soft(mine, blur)

    def alike(region):
        ys, xs = np.nonzero(region)
        av = soft_truth[ys, xs] - soft_truth[ys, xs].mean()
        best = -1.0
        for dx, dy in slides:
            bv = soft_mine[np.clip(ys + dy, 0, tall - 1), np.clip(xs + dx, 0, wide - 1)]
            bv = bv - bv.mean()
            best = max(best, float((av * bv).sum() / max(1e-6, math.sqrt(float((av * av).sum() * (bv * bv).sum())))))
        return max(0.0, best)

    for f, x0, x1, y0, y1 in boxes:
        inside = np.zeros_like(there)
        inside[max(0, y0):y1, max(0, x0):x1] = True
        pad = max(2, int(round(0.6 * max(x1 - x0, y1 - y0))))
        around = np.zeros_like(there)
        around[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad] = True
        around &= ~taken & there
        inside &= there
        if inside.sum() < 4 or around.sum() < 6:
            continue
        true = stands_out(truth, inside, around)
        if abs(true) < LEAST:
            continue
        best = max(stands_out(mine, inside, around, dx, dy) / true for dx, dy in slides)
        shows[f["name"]] = float(min(1.0, max(0.0, best)))
        kept[f["name"]] = alike(inside | around)
    like = None
    if boxes:
        r = max(1, int(round(ROUND_M / per_px)))
        x0, x1 = max(0, min(b[1] for b in boxes) - r), min(wide, max(b[2] for b in boxes) + r)
        y0, y1 = max(0, min(b[3] for b in boxes) - r), min(tall, max(b[4] for b in boxes) + r)
        face = np.zeros_like(there)
        face[y0:y1, x0:x1] = True
        face &= there
        if face.sum() > 30:
            like = alike(face)
    return kept, like, shows


def still(path, pictures, boxes, tall=420):
    """Pictures side by side (each the fine size), cut to the head, every counted feature boxed."""
    if not boxes:
        return
    x0, x1 = min(b[1] for b in boxes), max(b[2] for b in boxes)
    y0, y1 = min(b[3] for b in boxes), max(b[4] for b in boxes)
    pad = int(0.9 * max(x1 - x0, y1 - y0)) + 8
    h, w = pictures[0].shape[:2]
    cx0, cx1, cy0, cy1 = max(0, x0 - pad), min(w, x1 + pad), max(0, y0 - pad), min(h, y1 + pad)
    times = max(1, tall // max(1, cy1 - cy0))
    cuts = []
    for n, picture in enumerate(pictures):
        cover = picture[..., 3:4].astype(np.float32) / 255.0
        shown = np.round(picture[..., :3] * cover + np.array(PAPER, dtype=np.float32) * (1.0 - cover)).astype(np.uint8)
        if n == len(pictures) - 1:
            shown = shown.copy()
            for _, bx0, bx1, by0, by1 in boxes:
                shown[by0:by1, [max(0, bx0 - 1), min(w - 1, bx1)]] = (40, 200, 90)
                shown[[max(0, by0 - 1), min(h - 1, by1)], bx0:bx1] = (40, 200, 90)
        cuts.append(np.repeat(np.repeat(shown[cy0:cy1, cx0:cx1], times, axis=0), times, axis=1))
        cuts.append(np.full((cuts[-1].shape[0], 10, 3), 255, dtype=np.uint8))
    impostor.write_png(path, np.concatenate(cuts[:-1], axis=1))


def main():
    import judge_seams  # the real model in a background Blender (needs bpy)
    args = sys.argv[sys.argv.index("--") + 1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    out = os.path.abspath(flag("--out", "evidence/clear"))
    os.makedirs(out, exist_ok=True)
    tag, model, way = flag("--tag", ""), flag("--model", "detailed"), flag("--pixel", "new")
    runs, shots = os.path.abspath(flag("--runs", os.path.join(REPO, "runs"))), os.path.abspath(flag("--shots", os.path.join(REPO, "shots")))
    take = os.path.join(shots, flag("--take", "crew-candy-shop"))
    times = [float(t) for t in flag("--times", "9,13.5,18,24,36,45").split(",") if t]
    eyes, looks = flag("--eyes", "crew,two,close").split(","), flag("--looks", "joe,pixel-both").split(",")
    only = flag("--only", "").split(",") if flag("--only", "") else None
    why = "--why" in args
    stills = set(flag("--stills", "").split(",")) - {""}
    with open(os.path.join(take, next(f for f in sorted(os.listdir(take)) if f.startswith("cast-") and f.endswith(".json")))) as f:
        cast = json.load(f)
    with open(os.path.join(REPO, "sets", cast["set"], "set.json")) as f:
        crew = json.load(f)["cameras"]["crew"]
    crew_fov = math.degrees(2.0 * math.atan(36.0 / (16.0 / 9.0) / 2.0 / crew["lens_mm"]))
    fine_size = (SIZE[0] * FINER, SIZE[1] * FINER)
    report = {"take": os.path.basename(take), "model": model, "pixel": way, "size": list(SIZE), "rows": []}
    began = time.time()

    for role, part in cast["roles"].items():
        if only and role not in only:
            continue
        run = part["character"].split("/runs/")[1].split("/")[0]
        profiles = os.path.join(runs, run, "profiles")
        recipe = pixel_face.recipe_for(run)
        if not recipe:
            print("FACES %s has no recipe to say where his features are: left out" % role, flush=True)
            continue
        folder = lambda name: os.path.join(profiles, "%s-%s" % (model, name))
        if "--joints" not in args or flag("--joints", "") != "cards":  # the cards with a piece of the model in each big joint, when there are some
            plain = folder
            stem = lambda name: plain(name)[:-len("-joined")] if name.endswith("-joined") else plain(name)
            tails = ([] if flag("--joints", "") == "knees" else ["-necked"]) + ["-skinned"]  # (the ones with a piece for the neck too, first; --joints knees: without)
            pieces = lambda name: next((stem(name) + t for t in tails if os.path.isfile(os.path.join(stem(name) + t, "impostor.json"))), stem(name) + "-skinned")
            folder = lambda name: pieces(name) if os.path.isfile(os.path.join(pieces(name), "impostor.json")) else plain(name)
        joe = impostor.Character(folder("impostor-joe-joined"))
        comic = impostor.Character(folder("impostor-comic-joined")) if why else None
        named = flag("--sheet", "")
        pixel_folder = folder(named) if named else next(folder(n) for n in (["impostor-pixel-clear"] if way == "new" else []) + ["impostor-pixel-joined"] if os.path.isfile(os.path.join(folder(n), "impostor.json")))
        pixel = impostor.Character(pixel_folder)
        report.setdefault("sheets", {})[role] = os.path.basename(pixel_folder)
        features = features_of(recipe, joe)
        real = judge_seams.Real(os.path.join(profiles, joe.card["source"]), joe.card, pieces=False)
        motion = impostor.Glb(os.path.join(take, part["glb"]))
        paint = impostor.PAINTS["pixel"]

        def pixel_both(pose, eye, sheet=None, line=True, levels=True, k=K, shift=(0.0, 0.0), new=None):
            """ "Pixels, both" at the screen's size, blown up to the fine one."""
            character = sheet or pixel
            small = impostor.Eye(eye.at, eye.aim, eye.fov_deg, (SIZE[0] // k, SIZE[1] // k), shift=shift)
            if way == "new" if new is None else new:
                picture, _, _, _ = impostor.draw_fine_heads(character, pose, small, paint=paint, line=line)
                times_ = k * FINER // impostor.FINE
            else:
                who = np.zeros((small.size[1], small.size[0]), dtype=np.int32)
                picture, depth, _ = impostor.draw(character, pose, small, line="off", who=who, paint=paint)
                if line:
                    picture = impostor.with_lines(picture, impostor.grid_line(depth, who, small), impostor.GRID_INK)
                times_ = k * FINER
            if levels:
                picture = impostor.cut_levels(picture, paint["levels"])
            picture = blown(picture, times_)
            if shift != (0.0, 0.0):  # slid with its grid: bring it back over the model's
                picture = np.roll(picture, (-int(round(shift[1] * k * FINER)), -int(round(shift[0] * k * FINER))), axis=(0, 1))
            return picture

        for t in times:
            pose = motion.pose(t)
            real.pose(pose)
            for eye_name in eyes:
                eye = eye_for(eye_name, crew, crew_fov, pose, SIZE)
                fine = impostor.Eye(eye.at, eye.aim, eye.fov_deg, fine_size)
                per_px = fine.m_per_px(pose["head"][:3, 3])
                truth = real.draw(fine, 0.0)
                who = np.zeros((SIZE[1], SIZE[0]), dtype=np.int32)
                bold, depth, _ = impostor.draw(joe, pose, eye, line="off", who=who, paint=impostor.PAINTS["joe"])
                bold = blown(impostor.with_lines(bold, impostor.bold_lines(depth, who, eye) & (who > 0)), FINER)
                boxes, hidden, turned = boxes_of(features, pose["head"], eye, depth, FINER)
                base = {"role": role, "seconds": t, "eye": eye_name, "features": len(features), "counted": len(boxes), "hidden": hidden, "turned": turned,
                        "big_px_m": round(per_px * FINER * K, 4), "face_big_px": round(0.15 / (per_px * FINER * K), 1)}
                drawn = {}
                if "joe" in looks:
                    drawn["joe"] = bold
                if "pixel-both" in looks:
                    drawn["pixel-both"] = pixel_both(pose, eye)
                if why:
                    drawn["why: no line"] = pixel_both(pose, eye, line=False)
                    drawn["why: colours not cut to steps"] = pixel_both(pose, eye, levels=False)
                    drawn["why: grid twice as fine"] = pixel_both(pose, eye, k=1)
                    drawn["why: comic sheet on the grid"] = pixel_both(pose, eye, sheet=comic)
                for look, picture in drawn.items():
                    kept, like, shows = judge(truth, picture, boxes, per_px)
                    row = dict(base, look=look, kept=kept, likeness=like, shows=shows)
                    if look == "pixel-both":  # the same picture with its grid slid three ways
                        tries = [kept] + [judge(truth, pixel_both(pose, eye, shift=s), boxes, per_px)[0] for s in ((0.5, 0.0), (0.0, 0.5), (0.5, 0.5))]
                        row["crawl"] = {name: round(max(g.get(name, 0.0) for g in tries) - min(g.get(name, 0.0) for g in tries), 3) for name in kept}
                        row["kept_worst"] = {name: round(min(g.get(name, 0.0) for g in tries), 3) for name in kept}
                    report["rows"].append(row)
                if "%s@%g:%s" % (role, t, eye_name) in stills:
                    still(os.path.join(out, "%s-judged-%s-%g-%s.png" % (tag or way, role, t, eye_name)), [truth] + [drawn[k] for k in ("joe", "pixel-both") if k in drawn], boxes)
            print("FACES %s %.1f s" % (role, t), flush=True)

    # the sums: for every eye and look, each dancer and all of them
    table = {}
    mean = lambda xs: round(float(np.mean(xs)), 3) if len(xs) else None
    for row in report["rows"]:
        for who_ in (row["role"], "all"):
            e = table.setdefault("%s|%s|%s" % (row["eye"], row["look"], who_), {"pictures": 0, "kept": [], "shows": [], "likeness": [], "crawl": [], "worst": [], "kinds": {}, "counted": 0, "hidden": 0, "turned": 0, "face_big_px": []})
            e["pictures"] += 1
            e["kept"] += list(row["kept"].values())
            e["shows"] += list(row["shows"].values())
            e["crawl"] += list(row.get("crawl", {}).values())
            e["worst"] += list(row.get("kept_worst", {}).values())
            e["face_big_px"].append(row["face_big_px"])
            for key in ("counted", "hidden", "turned"):
                e[key] += row[key]
            if row["likeness"] is not None:
                e["likeness"].append(row["likeness"])
            for name, value in row["kept"].items():
                e["kinds"].setdefault(kind_of(name), []).append(value)
    for key, e in table.items():
        e.update(kept=mean(e["kept"]), shows=mean(e["shows"]), lost=round(float(np.mean(np.array(e["kept"]) < 0.25)), 3) if e["kept"] else None, likeness=mean(e["likeness"]), crawl=mean(e["crawl"]), worst=mean(e["worst"]),
                 kinds={k: mean(v) for k, v in e["kinds"].items()}, face_big_px=mean(e["face_big_px"]))
        print("FACES %-46s %2d pictures: kept %s (under a quarter: %s of the features; shows %s), likeness %s%s; %s; a face %s big pixels wide; %d counted, %d hidden, %d turned away" % (
            key, e["pictures"], e["kept"], e["lost"], e["shows"], e["likeness"], "" if e["crawl"] is None else ", crawl %s, kept at worst %s" % (e["crawl"], e["worst"]),
            ", ".join("%s %s" % kv for kv in e["kinds"].items()), e["face_big_px"], e["counted"], e["hidden"], e["turned"]), flush=True)
    report["table"] = table
    report["seconds"] = round(time.time() - began, 1)
    with open(os.path.join(out, "faces%s.json" % (tag and "-" + tag)), "w") as f:
        json.dump(report, f, indent=1)
    print("RESULT " + json.dumps({"out": out, "seconds": report["seconds"]}))


if __name__ == "__main__":
    main()
