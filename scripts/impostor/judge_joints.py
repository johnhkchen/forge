"""Does a bent joint read as the joint it is? A take's cast drawn as cards, joint by joint, against the real
models posed the same.

    Blender -b --factory-startup -P scripts/impostor/judge_joints.py -- --out <folder> [--tag before]
        [--runs runs] [--shots shots] [--take crew-candy-shop] [--model detailed] [--sheets joined|skinned|bent]
        [--at 38] [--deep 2] [--kinds knee,elbow,hip,shoulder] [--eyes crew,2,1] [--looks joe,pixel-both]
        [--only left] [--core 0.6] [--stills left@38:shin_l:1,...|asked] [--parts left@38:shin_l:1]

judge_seams.py counts pixels the cards leave bare. A knee can have none bare and still not be a knee: a hollow
plugged with one flat colour, with the rim of the part drawn round it, is a socket. So this one compares what
is drawn. For every one of the cast, at each of --at seconds of the take (both knees) and at the --deep moments
where each of --kinds is bent furthest (that joint), it draws the character from the same eye twice: as cards,
by impostor.py, in each look; and the real model those cards were pictured from, posed by the same bones and
drawn the comic way, twice as fine. The eyes: the set's crew camera, and a square 55 cm across round the joint
as the screen would show it from 2 m and from 1 m off, on the crew camera's side. In a disc about the joint (the
ring where its two parts meet and 6 cm more), over the real model's own body:

    likeness   how well the cards' light and dark follows the real model's: 1 is the same shapes in the same
               places, 0 is nothing in common (the two blurred over 4 mm, the cards slid up to a centimetre)
    blots      the share of the disc where the cards are a good deal darker than the model (50 of 255, both
               blurred over 6 mm): a dark ring, a hollow, a black scratch
    colour     how far the cards' colour is from the model's, of 255, a typical pixel. The looks paint
               differently from the comic way the model is drawn, so this is for one look before and after
    bare       pixels of the model's body the cards do not cover, in pixels of the screen

"shaft" rows are the same disc laid on the middle of a thigh or an upper arm, where nothing bends: what the
cards score when nothing is wrong. --sheets says which baked cards to read: joined (as they were: rigid parts,
a ball in each joint), skinned (those, with a piece of the real model bending in each big joint: bake_joints.py)
or bent (joint cards pictured bent: bake_impostor.py --bent).

Writes <out>/joints[-tag].json and, for --stills (role@seconds:bone:eye), <tag>-<role>-<seconds>-<bone>-<eye>.png:
the real model, then the cards in each look. --parts writes the same square with the upper part's card alone and
the lower part's alone: what each picture holds at the joint. Never touches an open Blender.
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
FINER = 2            # the real model is drawn this many times finer than the screen
K = 2                # screen pixels to one of the pixel looks' big ones, at this size (looks.js: 270 rows)
SQUARE_M = 0.55      # the square round a joint, from close by
SCREEN_FOV = 36.0    # the free eye's view on the watch page: how big a pixel is from 1 m and 2 m follows from it
REACH_M = 0.06       # a joint's disc reaches this far past the ring where its two parts meet
OFF_M = 0.01         # the cards' picture may sit this far from the model's
BLOT = 50.0          # darker than the model by this much (of 255) is a blot
LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
PAPER = (250, 248, 245)
KINDS = {"shin": "knee", "forearm": "elbow", "upper_arm": "shoulder", "thigh": "hip"}
SHAFT = {"knee": "thigh", "elbow": "upper_arm"}  # where nothing bends: the middle of the part above
STEPS = (30, 60, 90)
SHEETS = {"joined": {"joe": ["joe-joined"], "pixel-both": ["pixel-clear", "pixel-joined"], "comic": ["comic-joined"], "pixel-baked": ["pixel-joined"]},
          "skinned": {"joe": ["joe-skinned"], "pixel-both": ["pixel-clear-skinned"], "comic": ["comic-skinned"], "pixel-baked": ["pixel-skinned"]},
          "bent": {"joe": ["joe-bent"], "pixel-both": ["pixel-bent"], "comic": ["comic-bent"], "pixel-baked": ["pixel-bent"]}}


def kind_of(bone):
    return KINDS.get(bone[:-2], "")


def luma(picture):
    cover = picture[..., 3:4].astype(np.float32) / 255.0
    return (picture[..., :3].astype(np.float32) * cover + np.array(PAPER, dtype=np.float32) * (1.0 - cover)) @ LUMA


def soft(a, r):
    """Each pixel the mean of the square of pixels r either side of it."""
    if r < 1:
        return a
    pad = np.pad(a, r, mode="edge")
    total = np.pad(np.cumsum(np.cumsum(pad, axis=0), axis=1), ((1, 0), (1, 0)))
    n = 2 * r + 1
    return (total[n:, n:] - total[:-n, n:] - total[n:, :-n] + total[:-n, :-n]) / float(n * n)


def blown(picture, times):
    return picture if times == 1 else np.repeat(np.repeat(picture, times, axis=0), times, axis=1)


def judge(real, cards, disc, per_px):
    """The cards' picture against the real model's inside a disc, both the fine size (per_px: metres a pixel):
    {"likeness", "blots", "colour", "bare" (fine pixels), "ground" (fine pixels of the model in the disc)}."""
    there = real[..., 3] > 127
    region = disc & there
    ground = int(region.sum())
    if ground < 12:
        return None
    tall, wide = there.shape
    ys, xs = np.nonzero(region)
    truth, mine = luma(real), luma(cards)
    blur = max(1, int(round(0.004 / per_px)))
    a, b = soft(truth, blur), soft(mine, blur)
    reach = max(1, int(round(OFF_M / per_px)))
    av = a[ys, xs] - a[ys, xs].mean()
    best = -1.0
    for dx in range(-reach, reach + 1, max(1, reach // 2)):
        for dy in range(-reach, reach + 1, max(1, reach // 2)):
            bv = b[np.clip(ys + dy, 0, tall - 1), np.clip(xs + dx, 0, wide - 1)]
            bv = bv - bv.mean()
            best = max(best, float((av * bv).sum() / max(1e-6, math.sqrt(float((av * av).sum() * (bv * bv).sum())))))
    wider = max(1, int(round(0.006 / per_px)))
    a, b = soft(truth, wider), soft(mine, wider)
    both = region & (cards[..., 3] > 127)
    off = np.abs(real[..., :3].astype(np.float32) - cards[..., :3].astype(np.float32)).mean(axis=-1)
    return {"likeness": max(0.0, best), "blots": float((a[ys, xs] - b[ys, xs] > BLOT).mean()), "colour": float(off[both].mean()) if both.any() else None,
            "bare": int((region & ~(cards[..., 3] > 127)).sum()), "ground": ground}


def over_paper(picture):
    cover = picture[..., 3:4].astype(np.float32) / 255.0
    return np.round(picture[..., :3] * cover + np.array(PAPER, dtype=np.float32) * (1.0 - cover)).astype(np.uint8)


def still(path, pictures, disc=None, tall=420):
    """Pictures side by side, blown up whole to about `tall` pixels; the disc that was judged ringed on the first."""
    times = max(1, tall // pictures[0].shape[0])
    cuts = []
    for n, picture in enumerate(pictures):
        shown = over_paper(picture)
        if n == 0 and disc is not None:
            edge = disc & ~(np.roll(disc, 1, 0) & np.roll(disc, -1, 0) & np.roll(disc, 1, 1) & np.roll(disc, -1, 1))
            shown[edge] = (40, 200, 90)
        cuts += [blown(shown, times), np.full((shown.shape[0] * times, 10, 3), 255, dtype=np.uint8)]
    impostor.write_png(path, np.concatenate(cuts[:-1], axis=1))


def draw_look(character, pose, eye, look, only=None):
    """The cards as the page draws them in a look, through an eye the size of the screen's picture, blown up to
    FINER times that."""
    who = np.zeros((eye.size[1], eye.size[0]), dtype=np.int32)
    marked = bool(character.card.get("line_marked"))
    if look == "pixel-both":
        small = impostor.Eye(eye.at, eye.aim, eye.fov_deg, (eye.size[0] // K, eye.size[1] // K))
        if only is None:
            picture = impostor.draw_fine_heads(character, pose, small, paint=impostor.PAINTS["pixel"])[0]
            return blown(impostor.cut_levels(picture, impostor.PAINTS["pixel"]["levels"]), K * FINER // impostor.FINE)
        picture = impostor.draw(character, pose, small, line="off", paint=impostor.PAINTS["pixel"], only=only)[0]
        return blown(impostor.cut_levels(picture, impostor.PAINTS["pixel"]["levels"]), K * FINER)
    if look == "joe":
        picture, depth, _ = impostor.draw(character, pose, eye, line="off" if marked else "shell", who=who, paint=impostor.PAINTS["joe"], only=only)
        lines = impostor.bold_lines(depth, who if marked else None, eye) & (who > 0)
        if marked and "screen" in impostor.FILL:
            picture, depth, who, filled = impostor.crack_fill(picture, depth, who, impostor.bold_offsets())
            lines &= ~filled
        return blown(impostor.with_lines(picture, lines), FINER)
    paint = impostor.PAINTS["pixel" if look == "pixel-baked" else "comic"]
    return blown(impostor.draw(character, pose, eye, line="shell", paint=paint, only=only)[0], FINER)


def main():
    import judge_seams  # the real model in a background Blender (needs bpy)
    args = sys.argv[sys.argv.index("--") + 1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    out = os.path.abspath(flag("--out", "evidence/knees"))
    os.makedirs(out, exist_ok=True)
    tag, model, which = flag("--tag", ""), flag("--model", "detailed"), flag("--sheets", "skinned")
    runs, shots = os.path.abspath(flag("--runs", os.path.join(REPO, "runs"))), os.path.abspath(flag("--shots", os.path.join(REPO, "shots")))
    take = os.path.join(shots, flag("--take", "crew-candy-shop"))
    at = [float(t) for t in flag("--at", "38").split(",") if t]
    deep = int(flag("--deep", "2"))
    kinds = flag("--kinds", "knee,elbow,hip,shoulder").split(",")
    eyes, looks = flag("--eyes", "crew,2,1").split(","), flag("--looks", "joe,pixel-both").split(",")
    only = flag("--only", "").split(",") if flag("--only", "") else None
    impostor.ZONE_CORE = float(flag("--core", str(impostor.ZONE_CORE)))  # to try: how much of a card is kept inside a joint's zone (0: nothing)
    stills, parts_of = set(flag("--stills", "").split(",")) - {""}, set(flag("--parts", "").split(",")) - {""}
    with open(os.path.join(take, next(f for f in sorted(os.listdir(take)) if f.startswith("cast-") and f.endswith(".json")))) as f:
        cast = json.load(f)
    with open(os.path.join(REPO, "sets", cast["set"], "set.json")) as f:
        crew = json.load(f)["cameras"]["crew"]
    crew_fov = math.degrees(2.0 * math.atan(36.0 / (16.0 / 9.0) / 2.0 / crew["lens_mm"]))
    report = {"take": os.path.basename(take), "model": model, "sheets": which, "size": list(SIZE), "rows": [], "folders": {}}
    began = time.time()

    # (any other name: cards with pieces baked under that name, bake_joints.py --name)
    sheets = SHEETS.get(which) or {look: [n.replace("skinned", which) for n in names] for look, names in SHEETS["skinned"].items()}
    for role, part in cast["roles"].items():
        if only and role not in only:
            continue
        run = part["character"].split("/runs/")[1].split("/")[0]
        profiles = os.path.join(runs, run, "profiles")
        characters = {}
        for look in looks:
            folder = next(os.path.join(profiles, "%s-impostor-%s" % (model, n)) for n in sheets[look] if os.path.isfile(os.path.join(profiles, "%s-impostor-%s" % (model, n), "impostor.json")))
            characters[look] = characters.get(folder) or impostor.Character(folder)
            characters[folder] = characters[look]
            report["folders"].setdefault(role, {})[look] = os.path.basename(folder)
        first = characters[looks[0]].card
        real = judge_seams.Real(os.path.join(profiles, first["source"]), first, pieces=False)
        motion = impostor.Glb(os.path.join(take, part["glb"]))
        rings = {j["bone"]: j["ring_cm"] / 100.0 for j in first.get("joints") or []}
        above = {j["bone"]: next(p["bone"] for p in first["parts"] if p["name"] == j["between"][1]) for j in first.get("joints") or []}
        # the moments, and the joints looked at in each: (seconds, [bones])
        moments = [(t, [b for b in rings if kind_of(b) == "knee"]) for t in at]
        if deep:
            looked = [(t, real.bends(motion.pose(t))) for t in np.arange(0.0, motion.seconds, 0.25)]
            for kind in kinds:
                picked = []
                for _, bone, t in sorted(((max((v, b) for b, v in bends.items() if kind_of(b) == kind) + (t,)) for t, bends in looked), reverse=True):
                    if len(picked) < deep and all(abs(t - u) >= 1.0 for u, _ in picked):
                        picked.append((float(t), [bone]))
                moments += picked
        for t, bones in sorted(moments):
            pose = motion.pose(t)
            real.pose(pose)
            bends = real.bends(pose)
            # every big joint is judged through the crew camera; the ones this moment is for from close by too
            spots = [(b, kind_of(b), pose[b][:3, 3], rings[b] + REACH_M) for b in rings if kind_of(b) in kinds]
            spots += [(above[b], "shaft", (pose[above[b]][:3, 3] + pose[b][:3, 3]) / 2.0, rings[b] + REACH_M) for b in rings if kind_of(b) in SHAFT and kind_of(b) in kinds]
            for eye_name in eyes:
                if eye_name == "crew":
                    views = [(impostor.Eye(np.array(crew["at"], dtype=float), np.array(crew["aim"], dtype=float), crew_fov, SIZE), spots, "")]
                else:  # a square round the joint, as the screen shows it from that many metres
                    away = float(eye_name)
                    side = int(round(SQUARE_M * SIZE[1] / (2.0 * away * math.tan(math.radians(SCREEN_FOV) / 2.0)) / 4.0)) * 4
                    views = []
                    for bone in bones:
                        joint = pose[bone][:3, 3]
                        toward = impostor.unit(np.array([crew["at"][0] - joint[0], 0.0, crew["at"][2] - joint[2]]))
                        eye = impostor.Eye(joint + away * toward + np.array([0.0, 0.12 * away, 0.0]), joint, math.degrees(2.0 * math.atan(SQUARE_M / 2.0 / away)), (side, side))
                        views.append((eye, [s for s in spots if s[0] in (bone, above[bone])], bone))
                for eye, judged, focus in views:
                    fine = impostor.Eye(eye.at, eye.aim, eye.fov_deg, (eye.size[0] * FINER, eye.size[1] * FINER))
                    truth = real.draw(fine, 0.0)
                    ys, xs = np.mgrid[0:fine.size[1], 0:fine.size[0]]
                    drawn = {look: draw_look(characters[look], pose, eye, look) for look in looks}
                    discs = {}
                    for bone, kind, where, radius in judged:
                        centre, ahead = fine.to_pixels(where)
                        per_px = 2.0 * float(ahead) * fine.tan / fine.size[1]
                        disc = (xs + 0.5 - centre[0]) ** 2 + (ys + 0.5 - centre[1]) ** 2 < (radius / per_px) ** 2
                        discs[(bone, kind)] = disc
                        for look in looks:
                            got = judge(truth, drawn[look], disc, per_px)
                            if got is None:
                                continue
                            got["bare"] = round(got["bare"] / float(FINER * FINER), 1)
                            report["rows"].append(dict(got, role=role, seconds=round(t, 2), eye=eye_name, look=look, bone=bone, kind=kind, bend=round(bends.get(bone, 0.0), 1) if kind != "shaft" else 0.0,
                                                       focus=bool(focus == bone or (eye_name == "crew" and bone in bones))))
                    name = "%s@%g:%s:%s" % (role, t, focus or "all", eye_name)
                    if name in stills or ("asked" in stills and focus and eye_name == eyes[-1]):
                        still(os.path.join(out, "%s-%s-%g-%s-%s.png" % (tag or which, role, t, focus or "all", eye_name)), [truth] + [drawn[look] for look in looks], discs.get((focus, kind_of(focus))) if focus else None)
                    if name in parts_of and focus:
                        lower = next(p["name"] for p in first["parts"] if p["bone"] == focus)
                        upper = next(p["name"] for p in first["parts"] if p["bone"] == above[focus])
                        for look in looks:
                            still(os.path.join(out, "%s-%s-%g-%s-%s-%s-parts.png" % (tag or which, role, t, focus, eye_name, look)),
                                  [truth, drawn[look], draw_look(characters[look], pose, eye, look, [upper]), draw_look(characters[look], pose, eye, look, [lower])])
            print("JOINTS %s %.2f s (%s)" % (role, t, ", ".join(bones)), flush=True)

    # the sums: for every eye, look and kind of joint, by how far it is bent; and the joints each moment was for
    table = {}
    mean = lambda xs: round(float(np.mean(xs)), 3) if len(xs) else None
    for row in report["rows"]:
        step = "shaft" if row["kind"] == "shaft" else ["under 30", "30 to 60", "60 to 90", "90 and over"][sum(row["bend"] >= s for s in STEPS)]
        keys = ["%s|%s|%s|%s" % (row["eye"], row["look"], row["kind"], step)]
        if row["kind"] != "shaft":
            keys.append("%s|%s|%s|all" % (row["eye"], row["look"], row["kind"]))
            if row["bend"] >= 60:
                keys.append("%s|%s|any|60 and over" % (row["eye"], row["look"]))
        if row["focus"] and row["kind"] != "shaft":
            keys.append("%s|%s|%s|asked" % (row["eye"], row["look"], row["kind"]))
        for key in keys:
            e = table.setdefault(key, {"joints": 0, "likeness": [], "blots": [], "colour": [], "bare": []})
            e["joints"] += 1
            for k in ("likeness", "blots", "colour", "bare"):
                if row[k] is not None:
                    e[k].append(row[k])
    for key in sorted(table):
        e = table[key]
        e.update(worst=round(float(min(e["likeness"])), 3), likeness=mean(e["likeness"]), blots=mean(e["blots"]), colour=mean(e["colour"]), bare=mean(e["bare"]))
        print("JOINTS %-44s %3d joints: likeness %.3f (worst %.3f), blots %4.1f%%, colour off %4.1f, bare %5.1f px" % (key, e["joints"], e["likeness"], e["worst"], 100.0 * e["blots"], e["colour"] or 0.0, e["bare"]), flush=True)
    report["table"] = table
    report["seconds"] = round(time.time() - began, 1)
    with open(os.path.join(out, "joints%s.json" % (tag and "-" + tag)), "w") as f:
        json.dump(report, f, indent=1)
    print("RESULT " + json.dumps({"out": out, "seconds": report["seconds"]}))


if __name__ == "__main__":
    main()
