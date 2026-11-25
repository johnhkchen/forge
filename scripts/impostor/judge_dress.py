"""Does a dress hold together as cards? A take's dancer drawn as cards, ways of doing her skirt side by side,
against the real model posed the same, in the moments that ask most of a skirt.

    Blender -b --factory-startup -P scripts/impostor/judge_dress.py -- --out <folder> [--tag after]
        [--runs runs] [--shots shots] [--take groove-flamenco] [--only figure] [--model detailed]
        [--ways before=<profiles>:necked,after=<profiles>:necked,...] [--looks joe,pixel-both]
        [--eyes push,crew,2] [--deep 2] [--moves lunge,side,deep,swirl] [--at 3.5,9] [--stills all|<move>@<seconds>:<eye>,...]

A skirt is the one shape a card per bone cannot hold: it spans the hips and both legs, so cut into thigh and shin
cards it tears apart between the legs, and the bones it swings on are no card's (bake_impostor.py: chains_of). This
looks at the moments of the take that ask most of it (--deep of each, at least a second apart; --at adds more):

    lunge   the feet furthest apart front to back, in the hips' own frame
    side    the feet furthest apart side to side (a side-step, a wide stance)
    deep    the hips lowest
    swirl   a swing chain turned furthest from how it hangs at rest (the hem flung out)

through --eyes: "push" (the take's own moving camera, push_in or the first it has, where it is at that moment),
"crew" (the set's crew camera) and "2" (a square 1.3 m across round the skirt as the screen would show it from 2 m,
on the crew camera's side). Each moment is drawn once as the real model (the model the cards were pictured from,
posed by the take's own bones, its swing chains among them, drawn the comic way twice as fine) and once for each of
--ways: a name, and the profiles folder whose cards it reads (with ":necked", ":layered-necked", ":joined" for which
of its sheets: what the pages read is "necked"). Within the skirt (where the real model's dress shows, and 4 cm
round it), over the real model's body:

    likeness   how well the cards' light and dark follows the model's (judge_joints.py: judge): the polka dots,
               the tiers' shadows, the hem
    blots      the share of it where the cards are a good deal darker than the model
    bare       pixels of the model's body there the cards leave uncovered, in pixels of the screen
    torn       ... of those, the ones shut in by the cards on every side: a hole in the figure, the stage seen
               through the skirt between the legs
    out        pixels the cards cover there and the model does not (a rigid hem that did not swing, a leg through)

Writes <out>/dress[-tag].json and, for --stills, <tag>-<move>-<seconds>-<eye>-<look>.png: the real model, then each
way. Never touches an open Blender.
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
sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
import impostor  # noqa: E402

SIZE = (1080, 608)
FINER = 2             # the real model is drawn this many times finer than the screen
ROUND_M = 0.04        # the skirt's ground reaches this far round where the real model's dress shows
SQUARE_M = 1.3        # the square round the skirt, from close by
SCREEN_FOV = 36.0     # the free eye's view on the watch page
MOVES = ("lunge", "side", "deep", "swirl")
SHEETS = {"necked": {"joe": ["joe-necked", "joe-skinned", "joe-joined"], "pixel-both": ["pixel-clear-necked", "pixel-clear-skinned", "pixel-clear"], "comic": ["comic-necked", "comic-joined"]},
          "layered-necked": {"joe": ["joe-layered-necked", "joe-necked"], "pixel-both": ["pixel-clear-layered-necked", "pixel-clear-necked"], "comic": ["comic-layered-necked", "comic-necked"]},
          "joined": {"joe": ["joe-joined"], "pixel-both": ["pixel-clear"], "comic": ["comic-joined"]}}


def fov_of(lens_mm):
    """How tall a view is, in degrees, for a lens on the set's cameras (36 mm wide, 16:9)."""
    return math.degrees(2.0 * math.atan(36.0 / (16.0 / 9.0) / 2.0 / lens_mm))


def in_hips(pose, bone):
    """Where a bone's head is in the hips' own frame (metres, the hips' size taken out)."""
    hips = np.asarray(pose["hips"], dtype=np.float64)
    turn = hips[:3, :3] / np.cbrt(abs(np.linalg.det(hips[:3, :3])))
    return turn.T @ (np.asarray(pose[bone])[:3, 3] - hips[:3, 3])


def moves_of(rest, pose, chains, root="hips"):
    """What a pose asks of a skirt: {"lunge", "side": how far apart the feet are front to back and side to side, in
    the hips' frame, past how they stand at rest (m); "deep": how far the hips are below where they rest (m); "swirl":
    the most any chain's top bone is turned from how it hangs at rest, in its root's frame (degrees)}."""
    apart = in_hips(pose, "foot_l") - in_hips(pose, "foot_r")
    still = in_hips(rest, "foot_l") - in_hips(rest, "foot_r")
    out = {"lunge": abs(float(apart[2])) - abs(float(still[2])), "side": abs(float(apart[0])) - abs(float(still[0])),
           "deep": float(rest["hips"][1, 3] - pose["hips"][1, 3])}
    r = lambda m: np.asarray(m)[:3, :3] / np.cbrt(abs(np.linalg.det(np.asarray(m)[:3, :3])))
    swing = 0.0
    for chain in chains:
        top = chain[0]
        if top not in pose:
            continue
        now, then = r(pose[root]).T @ r(pose[top]), r(rest[root]).T @ r(rest[top])
        swing = max(swing, math.degrees(impostor.angle_of(then.T @ now)))
    out["swirl"] = swing
    return out


def pick(moments, deep, apart=1.0):
    """The `deep` moments with the most of a move, at least `apart` seconds from each other: [(seconds, how much)]."""
    picked = []
    for value, t in sorted(((v, t) for t, v in moments), reverse=True):
        if len(picked) < deep and all(abs(t - u) >= apart for u, _ in picked):
            picked.append((t, value))
    return picked


def ground_of(dress, per_px):
    """The skirt's ground: where the real model's dress shows, and ROUND_M round it."""
    import judge_seams as seams
    return seams.grow(dress, max(1, int(round(ROUND_M / per_px))))


def judge_way(truth, body, cards, ground, per_px):
    """One way's cards against the real model over the skirt's ground, both at the fine size."""
    import judge_joints as jj
    import judge_seams as seams
    got = jj.judge(truth, cards, ground, per_px) or {"likeness": None, "blots": None, "colour": None}
    covered = cards[..., 3] > 127
    bare = seams.shrink(body, 1) & ~covered & ground
    torn = bare & ~seams.outside(covered)
    out = covered & ~seams.grow(body, 1) & ground
    k = float(FINER * FINER)
    return {"likeness": got["likeness"], "blots": got["blots"], "bare": round(bare.sum() / k, 1), "torn": round(torn.sum() / k, 1), "out": round(out.sum() / k, 1), "ground": round((ground & body).sum() / k, 1)}


def main():
    import bpy
    import camera_path
    import judge_joints as jj
    import judge_seams as seams  # the real model in a background Blender
    args = sys.argv[sys.argv.index("--") + 1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    out = os.path.abspath(flag("--out", "evidence/dress"))
    os.makedirs(out, exist_ok=True)
    tag, model = flag("--tag", ""), flag("--model", "detailed")
    runs, shots = os.path.abspath(flag("--runs", os.path.join(REPO, "runs"))), os.path.abspath(flag("--shots", os.path.join(REPO, "shots")))
    take = os.path.join(shots, flag("--take", "groove-flamenco"))
    looks, eyes = flag("--looks", "joe,pixel-both").split(","), flag("--eyes", "push,crew,2").split(",")
    deep, moves = int(flag("--deep", "2")), [m for m in flag("--moves", ",".join(MOVES)).split(",") if m]
    at = [float(t) for t in flag("--at", "").split(",") if t]
    only = flag("--only", "").split(",") if flag("--only", "") else None
    stills = set(flag("--stills", "").split(",")) - {""}
    ways = [pair.split("=", 1) for pair in flag("--ways", "after=:necked").split(",") if pair]
    with open(os.path.join(take, next(f for f in sorted(os.listdir(take)) if f.startswith("cast-") and f.endswith(".json")))) as f:
        cast = json.load(f)
    with open(os.path.join(REPO, "sets", cast["set"], "set.json")) as f:
        crew = json.load(f)["cameras"]["crew"]
    plan = {}
    if os.path.isfile(os.path.join(take, "plan.json")):
        with open(os.path.join(take, "plan.json")) as f:
            plan = json.load(f)
    moving = camera_path.expand_all(plan.get("moving_cameras") or {})
    push = moving.get("push_in") or next(iter(moving.values()), None)
    report = {"take": os.path.basename(take), "model": model, "size": list(SIZE), "ways": {}, "rows": [], "moments": []}
    began = time.time()
    for role, part in cast["roles"].items():
        if only and role not in only:
            continue
        run = part["character"].split("/runs/")[1].split("/")[0]
        profiles = os.path.join(runs, run, "profiles")
        characters = {}
        for name, where in ways:
            folder, _, which = where.partition(":")
            folder = os.path.abspath(folder) if folder else profiles
            folder = os.path.join(folder, "profiles") if os.path.isdir(os.path.join(folder, "profiles")) else folder
            for look in looks:
                got = next((os.path.join(folder, "%s-impostor-%s" % (model, n)) for n in SHEETS[which or "necked"][look] if os.path.isfile(os.path.join(folder, "%s-impostor-%s" % (model, n), "impostor.json"))), None)
                if got is None:
                    sys.exit("no %s cards for %s in %s" % (look, name, folder))
                characters[name, look] = impostor.Character(got)
                report["ways"]["%s|%s" % (name, look)] = got
        first = characters[ways[0][0], looks[0]].card
        real = seams.Real(os.path.join(profiles, first["source"]), first, pieces=False)
        worn = [o for o in real.bodies if o.name.startswith("gear: ") or o.get("gear")]
        dressed = next((p for c in characters.values() for p in c.card["parts"] if p.get("dress")), None)
        chains = dressed["dress"]["chains"] if dressed else []
        motion = impostor.Glb(os.path.join(take, part["glb"]))
        rest = motion.pose(None)
        looked = [(t, moves_of(rest, motion.pose(t), chains, dressed["dress"]["root"] if dressed else "hips")) for t in np.arange(0.0, motion.seconds, 0.25)]
        moments = [(t, why, value) for why in moves for t, value in pick([(t, m[why]) for t, m in looked], deep)] + [(t, "at", 0.0) for t in at]
        for t, why, value in sorted(moments):
            report["moments"].append({"role": role, "seconds": round(float(t), 2), "why": why, "how_much": round(float(value), 3)})
            pose = motion.pose(t)
            real.pose(pose)
            middle = (pose["hips"][:3, 3] + 0.5 * (pose["shin_l"][:3, 3] + pose["shin_r"][:3, 3])) / 2.0  # the middle of the skirt, near enough
            for eye_name in eyes:
                if eye_name == "push":
                    if push is None:
                        continue
                    where = camera_path.sample(push, t)
                    eye = impostor.Eye(np.array(where["at"], dtype=float), np.array(where["aim"], dtype=float), fov_of(where["lens_mm"]), SIZE)
                elif eye_name == "crew":
                    eye = impostor.Eye(np.array(crew["at"], dtype=float), np.array(crew["aim"], dtype=float), fov_of(crew["lens_mm"]), SIZE)
                else:
                    away = float(eye_name)
                    side = int(round(SQUARE_M * SIZE[1] / (2.0 * away * math.tan(math.radians(SCREEN_FOV) / 2.0)) / 4.0)) * 4
                    toward = impostor.unit(np.array([crew["at"][0] - middle[0], 0.0, crew["at"][2] - middle[2]]))
                    eye = impostor.Eye(middle + away * toward + np.array([0.0, 0.15 * away, 0.0]), middle, math.degrees(2.0 * math.atan(SQUARE_M / 2.0 / away)), (side, side))
                fine = impostor.Eye(eye.at, eye.aim, eye.fov_deg, (eye.size[0] * FINER, eye.size[1] * FINER))
                truth = real.draw(fine, 0.0)
                body = truth[..., 3] > 127
                for o in real.bodies:  # where the dress shows, alone
                    o.hide_render = o not in worn
                dress = real.shoot(fine)[..., 3] > 127 if worn else body
                for o in real.bodies:
                    o.hide_render = False
                per_px = fine.m_per_px(middle)
                ground = ground_of(dress, per_px)
                drawn = {}
                for look in looks:
                    for name, _ in ways:
                        drawn[name, look] = jj.draw_look(characters[name, look], pose, eye, look)
                        row = judge_way(truth, body, drawn[name, look], ground, per_px)
                        row.update(role=role, seconds=round(float(t), 2), why=why, eye=eye_name, look=look, way=name)
                        report["rows"].append(row)
                    label = "%s@%g:%s" % (why, t, eye_name)
                    if "all" in stills or label in stills:
                        ys, xs = np.nonzero(ground)
                        if len(ys):
                            pad = int(0.1 / per_px)
                            crop = (max(0, xs.min() - pad), max(0, ys.min() - pad), min(fine.size[0], xs.max() + pad), min(fine.size[1], ys.max() + pad))
                            jj.still(os.path.join(out, "%s-%s-%g-%s-%s.png" % (tag or "dress", why, t, eye_name, look)), [truth] + [drawn[name, look] for name, _ in ways], tall=520, crop=crop)
            print("DRESS %s %.2f s (%s)" % (role, t, why), flush=True)

    # the sums: for every eye, look and way, by what the moment asked, and over all of them
    table = {}
    for row in report["rows"]:
        for key in ("%s|%s|%s|%s" % (row["eye"], row["look"], row["why"], row["way"]), "%s|%s|all|%s" % (row["eye"], row["look"], row["way"]), "all|%s|all|%s" % (row["look"], row["way"])):
            e = table.setdefault(key, {"pictures": 0, "likeness": [], "blots": [], "bare": [], "torn": [], "out": []})
            e["pictures"] += 1
            for k in ("likeness", "blots", "bare", "torn", "out"):
                if row[k] is not None:
                    e[k].append(row[k])
    for key in sorted(table):
        e = table[key]
        e.update(worst=round(float(min(e["likeness"])), 3) if e["likeness"] else None, **{k: round(float(np.mean(e[k])), 3) if e[k] else None for k in ("likeness", "blots", "bare", "torn", "out")})
        print("DRESS %-36s %3d pictures: likeness %.3f (worst %.3f), blots %4.1f%%, bare %6.1f px, torn %6.1f px, out %6.1f px" % (
            key, e["pictures"], e["likeness"] or 0.0, e["worst"] or 0.0, 100.0 * (e["blots"] or 0.0), e["bare"] or 0.0, e["torn"] or 0.0, e["out"] or 0.0), flush=True)
    report["table"] = table
    report["seconds"] = round(time.time() - began, 1)
    with open(os.path.join(out, "dress%s.json" % (tag and "-" + tag)), "w") as f:
        json.dump(report, f, indent=1)
    print("RESULT " + json.dumps({"out": out, "seconds": report["seconds"]}))


if __name__ == "__main__":
    main()
