"""Counts what the layers behind a card's first surface fill: the same moments drawn from sheets with and without them.

    Blender -b --factory-startup -P scripts/impostor/judge_layers.py -- --out <folder> [--tag after]
        [--runs runs] [--shots shots] [--take crew-candy-shop] [--model detailed] [--times 9,13.5,18,24,36,45]
        [--eyes crew,two,close] [--looks joe,pixel-both,comic] [--only right] [--stills right@18:two,...]
        [--before joe=FOLDER,...] [--after joe=FOLDER,...] [--round 0.32] [--first-only]

For every one of the take's cast, at each of --times seconds of it, through three eyes (the set's crew camera;
2 m from his head; 1 m from it), it draws the real model his cards were pictured from, and his cards twice: from
the sheets with one layer (<model>-impostor-<look>-skinned and the like, as the pages read them before) and from
the layered ones (bake_impostor.py --layers: <model>-impostor-<look>-layered-skinned, or without -skinned when
there are no pieces). Then it counts, in pixels of the picture, over the whole figure and within --round metres of
the middle of his head (a hat is there):

    bare       body the real model has (a pixel in from its edge) and the cards do not
    holes      ... of that, shut in by the cards on every side
    out        cards where the real model has nothing, a pixel out from its edge
    filled     bare before, covered now
    opened     covered before, bare now
    off        (the comic look, which is drawn in the model's own colours and light) pixels both have whose colour
               is further from the model's than 64 in 255

--before and --after name a look's folder outright (a path, or a name under the run's profiles).

Writes <out>/layers[-tag].json and, for --stills, <tag>-<role>-<seconds>-<eye>-<look>.png: the real model, the
cards before, the cards after, and the cards after again with what the layers filled marked green, what is still
bare blue and what opened red. Never touches an open Blender.
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

SIZE = (1080, 608)
# name: (which sheets, before and after; how many screen pixels one of the picture's is; the lines drawn on the finished picture)
LOOKS = {"joe": ("joe-joined", "joe-layered", 1, "bold"), "comic": ("comic-joined", "comic-layered", 1, None),
         "pixel-both": ("pixel-clear", "pixel-clear-layered", 2, "grid"), "pixel-baked": ("pixel-joined", "pixel-layered", 1, None)}


def with_pieces(folder):
    """A set of cards with a piece of the model in each big joint, when it has one (bake_joints.py)."""
    pieces = "%s-skinned" % (folder[:-len("-joined")] if folder.endswith("-joined") else folder)
    return pieces if os.path.isfile(os.path.join(pieces, "impostor.json")) else folder


def cards(character, pose, eye, lines):
    """A character's cards as a page draws them in a look: the picture, with the look's lines on it."""
    fine = impostor.FINE if lines == "grid" and "-pixel-clear" in os.path.basename(character.folder) else 1
    if fine > 1:  # "Pixels, both": the head on a grid twice as fine, brought back to big pixels to count
        picture, _, _, _ = impostor.draw_fine_heads(character, pose, eye, fine=fine)
        cover = (picture[..., 3].reshape(eye.size[1], fine, eye.size[0], fine) > 127).sum(axis=(1, 3)) * 2 >= fine * fine
        small = picture[::fine, ::fine].copy()
        small[..., 3] = np.where(cover, 255, 0)
        return small
    who = np.zeros((eye.size[1], eye.size[0]), dtype=np.int32)
    picture, depth, _ = impostor.draw(character, pose, eye, line="off" if lines else "shell", who=who)
    drawn = impostor.grid_line(depth, who, eye) if lines == "grid" else impostor.bold_lines(depth, who, eye) & (who > 0) if lines == "bold" else None
    if drawn is not None:
        picture, depth, who, filled = impostor.crack_fill(picture, depth, who, [(0, 1), (1, 0)] if lines == "grid" else impostor.bold_offsets())
        picture = impostor.with_lines(picture, drawn & ~filled)
    return picture


def main():
    import judge_seams as seams  # the real model in a background Blender (needs bpy)
    from judge_faces import eye_for
    args = sys.argv[sys.argv.index("--") + 1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    out = os.path.abspath(flag("--out", "evidence/layers"))
    os.makedirs(out, exist_ok=True)
    tag, model = flag("--tag", ""), flag("--model", "detailed")
    runs, shots = os.path.abspath(flag("--runs", os.path.join(REPO, "runs"))), os.path.abspath(flag("--shots", os.path.join(REPO, "shots")))
    take = os.path.join(shots, flag("--take", "crew-candy-shop"))
    times = [float(t) for t in flag("--times", "9,13.5,18,24,36,45").split(",") if t]
    eyes, looks = flag("--eyes", "crew,two,close").split(","), flag("--looks", "joe,pixel-both,comic").split(",")
    only = flag("--only", "").split(",") if flag("--only", "") else None
    stills = set(flag("--stills", "").split(",")) - {""}
    named = {way: dict(pair.split("=") for pair in flag("--" + way, "").split(",") if pair) for way in ("before", "after")}
    round_m = float(flag("--round", "0.32"))
    impostor.LAYERS = "--first-only" not in args  # the layered sheets read as if they had one layer: what the bake alone changed
    with open(os.path.join(take, next(f for f in sorted(os.listdir(take)) if f.startswith("cast-") and f.endswith(".json")))) as f:
        cast = json.load(f)
    with open(os.path.join(REPO, "sets", cast["set"], "set.json")) as f:
        crew = json.load(f)["cameras"]["crew"]
    crew_fov = math.degrees(2.0 * math.atan(36.0 / (16.0 / 9.0) / 2.0 / crew["lens_mm"]))
    report = {"take": os.path.basename(take), "model": model, "size": list(SIZE), "round_m": round_m, "sheets": {}, "rows": []}
    began = time.time()
    for role, part in cast["roles"].items():
        if only and role not in only:
            continue
        run = part["character"].split("/runs/")[1].split("/")[0]
        profiles = os.path.join(runs, run, "profiles")
        characters = {}
        for look in looks:
            for way, name in zip(("before", "after"), LOOKS[look][:2]):
                folder = named[way].get(look)
                folder = (folder if os.path.isabs(folder) else os.path.join(profiles, folder)) if folder else with_pieces(os.path.join(profiles, "%s-impostor-%s" % (model, name)))
                characters[look, way] = impostor.Character(folder)
                report["sheets"]["%s|%s|%s" % (role, look, way)] = os.path.basename(folder)
        first = characters[looks[0], "before"].card
        real = seams.Real(os.path.join(profiles, first["source"]), first, pieces=False)
        motion = impostor.Glb(os.path.join(take, part["glb"]))
        for t in times:
            pose = motion.pose(t)
            real.pose(pose)
            head = pose["head"][:3, 3] + pose["head"][:3, 1] * 0.12  # the middle of a head, and of a hat on it
            for eye_name in eyes:
                bodies, truths = {}, {}
                for look in looks:
                    k, lines = LOOKS[look][2:]
                    eye = eye_for(eye_name, crew, crew_fov, pose, (SIZE[0] // k, SIZE[1] // k))
                    if k not in bodies:
                        truths[k] = real.draw(eye, 0.0)
                        bodies[k] = truths[k][..., 3] > 127
                    body, truth = bodies[k], truths[k]
                    (hx, hy), _ = eye.to_pixels(head)
                    ys, xs = np.mgrid[0:eye.size[1], 0:eye.size[0]]
                    near = (xs + 0.5 - hx) ** 2 + (ys + 0.5 - hy) ** 2 < (round_m / eye.m_per_px(head)) ** 2
                    drawn = {way: cards(characters[look, way], pose, eye, lines) for way in ("before", "after")}
                    row = {"role": role, "seconds": t, "eye": eye_name, "look": look, "body": int(body.sum()), "body_head": int((body & near).sum())}
                    masks = {}
                    for way, picture in drawn.items():
                        got = picture[..., 3] > 127
                        bare = seams.shrink(body, 1) & ~got
                        hole = bare & ~seams.outside(got)
                        stuck = got & ~seams.grow(body, 1)
                        masks[way] = (got, bare)
                        both = got & body
                        off = both & (np.abs(picture[..., :3].astype(int) - truth[..., :3].astype(int)).max(axis=-1) > 64) if look == "comic" else np.zeros_like(got)
                        for name, mask in (("bare", bare), ("holes", hole), ("out", stuck), ("off", off)):
                            row["%s_%s" % (name, way)], row["%s_%s_head" % (name, way)] = int(mask.sum()), int((mask & near).sum())
                    filled, opened = masks["before"][1] & masks["after"][0], masks["after"][1] & masks["before"][0]
                    row.update(filled=int(filled.sum()), filled_head=int((filled & near).sum()), opened=int(opened.sum()), opened_head=int((opened & near).sum()))
                    report["rows"].append(row)
                    if "%s@%g:%s" % (role, t, eye_name) in stills:
                        marked = (seams.over_paper(drawn["after"]) * 0.45 + np.array(seams.PAPER) * 0.55).astype(np.uint8)
                        marked[masks["after"][1]], marked[filled], marked[opened] = (40, 90, 220), (30, 170, 70), (220, 40, 30)
                        ys_, xs_ = np.where(near)
                        y0, y1, x0, x1 = ys_.min(), ys_.max() + 1, xs_.min(), xs_.max() + 1
                        times_ = max(1, 420 // (y1 - y0))
                        cuts = [np.repeat(np.repeat(p[y0:y1, x0:x1], times_, axis=0), times_, axis=1)
                                for p in (seams.over_paper(truth), seams.over_paper(drawn["before"]), seams.over_paper(drawn["after"]), marked)]
                        gap = np.full((cuts[0].shape[0], 8, 3), 255, dtype=np.uint8)
                        impostor.write_png(os.path.join(out, "%s-%s-%g-%s-%s.png" % (tag or "layers", role, t, eye_name, look)), np.concatenate([c for cut in cuts for c in (cut, gap)][:-1], axis=1))
            print("LAYERS %s %.1f s" % (role, t), flush=True)
    table = {}
    for row in report["rows"]:
        for who in (row["role"], "all"):
            e = table.setdefault("%s|%s|%s" % (row["eye"], row["look"], who), {"pictures": 0})
            e["pictures"] += 1
            for key, value in row.items():
                if isinstance(value, int) and key != "seconds":
                    e[key] = e.get(key, 0) + value
    for key, e in sorted(table.items()):
        n = float(e["pictures"])
        for name in list(e):
            if name != "pictures":
                e[name] = round(e[name] / n, 1)
        print("LAYERS %-28s| %2d pictures | whole figure: bare %6.1f to %6.1f, holes %5.1f to %5.1f, out %6.1f to %6.1f, filled %5.1f, opened %5.1f | round the head: bare %5.1f to %5.1f, holes %5.1f to %5.1f, out %5.1f to %5.1f, filled %5.1f, opened %4.1f%s" % (
            key, e["pictures"], e["bare_before"], e["bare_after"], e["holes_before"], e["holes_after"], e["out_before"], e["out_after"], e["filled"], e["opened"],
            e["bare_before_head"], e["bare_after_head"], e["holes_before_head"], e["holes_after_head"], e["out_before_head"], e["out_after_head"], e["filled_head"], e["opened_head"],
            " | colour off %.1f to %.1f (head %.1f to %.1f)" % (e["off_before"], e["off_after"], e["off_before_head"], e["off_after_head"]) if "|comic|" in key else ""), flush=True)
    report["table"] = table
    report["seconds"] = round(time.time() - began, 1)
    with open(os.path.join(out, "layers%s.json" % (tag and "-" + tag)), "w") as f:
        json.dump(report, f, indent=1)
    print("RESULT " + json.dumps({"out": out, "seconds": report["seconds"]}))


if __name__ == "__main__":
    main()
