"""Where several dancers in one clip stand relative to each other, so a crew keeps its formation on our stage.

    python3 scripts/video/formation.py <clip> --people 1,2,3 --from 5.4 --to 53.0 [--origin x,z] [--heading 0]

Each person's motion comes back from GEM-X in a world of their own: everyone
starts at its middle, and over half a minute each drifts a different way. So
the motions alone do not say who stood where. The picture does. All of them
were filmed by one camera at the same moments, and a person's box in the
picture says where they are: how far (a body this tall, in this pose, that
looks this big, is this far off) and how far to the side.

    how far      from the box's height against the height of the pose GEM-X
                 found (crouched people are not "further away"). Someone whose
                 feet are cut off by the bottom of the picture would look
                 further than they are; for them the top of the box is used,
                 with the camera's height and tilt worked out from the people
                 whose feet do show.
    to the side  from the box's middle, at that distance.

A camera that pans, creeps or zooms moves everyone in the picture together, so
only what is NOT shared is kept from the picture: each person's place relative
to the middle of the group, smoothed over a few seconds. The quick part of
how each person moves (a step, a hop, a slide) is taken from their own motion,
where it is measured far better. What is lost is the whole group travelling
slowly together: the middle of the group stays on its spot.

    place of person i = the spot + their smoothed place in the group (picture)
                                 + their own quick movement (their motion)

`spread` (1 is as filmed) stretches the places in the group, for characters
broader than the dancers were.

A worker answer that carries `camera_root` (where the hips are in the camera's
own space; newer workers send it) is used in place of the boxes for "how far"
and "to the side".

The command prints where each person starts and ends and the closest any two
come, for writing a set's marks from. Plain Python.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
import clip as clip_file  # noqa: E402

FPS = 30
HEAD_ABOVE_M, SOLE_BELOW_M = 0.14, 0.04  # a box reaches this far past the head joint and the toe joint
SMOOTH_FRAMES = 60  # either side: places in the group are averaged over about four seconds (shorter follows the picture closer, and slides the feet more)
QUICK_FRAMES = 60  # either side: movement slower than that is not taken from a person's own motion
LOW_FOOT_M = 0.06  # a toe within this of where it rests is on the floor, near enough
GROUP_DRIFT_M_PER_S = 0.05  # everyone's standing foot sliding the same way faster than this is a group that drifts
GROUP_LEASH_FRAMES = 240  # either side: the group's own travel is kept, but not a creep slower than about sixteen seconds
CAMERA_HEIGHT_M = 1.3  # used only if the clip never shows two people at clearly different distances


def middle(values: list) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def smoothed(values: list, reach: int) -> list:
    """A moving average, `reach` frames either side; gaps (None) are filled from what is around them."""
    known = [i for i, v in enumerate(values) if v is not None]
    if not known:
        raise clip_file.Stop("someone in the formation is never seen in these seconds")
    filled = list(values)
    for i, v in enumerate(values):
        if v is None:
            before, after = [k for k in known if k < i], [k for k in known if k > i]
            if before and after:
                a, b = before[-1], after[0]
                filled[i] = values[a] + (values[b] - values[a]) * (i - a) / float(b - a)
            else:
                filled[i] = values[(before or after)[-1 if before else 0]]
    # A median over a few frames first, so one wild box does not pull the average.
    calm = [middle(filled[max(0, i - 4) : i + 5]) for i in range(len(filled))]
    total, sums = [0.0], 0.0
    for v in calm:
        sums += v
        total.append(sums)
    return [(total[min(len(calm), i + reach + 1)] - total[max(0, i - reach)]) / (min(len(calm), i + reach + 1) - max(0, i - reach)) for i in range(len(calm))]


def seen_from_boxes(people: dict, width: int, height: int) -> dict:
    """{person: [(left, far) or None per frame]} in the dancers' own metres, from boxes and pose heights.

    `people` is {person: {"boxes": [box or None], "top": [m above the floor], "tall": [m]}} over the same frames."""
    focal = math.hypot(width, height)  # the focal length GEM-X itself assumes
    count = len(next(iter(people.values()))["boxes"])
    whole, cut = {p: [None] * count for p in people}, {p: [False] * count for p in people}
    for p, card in people.items():
        for f, box in enumerate(card["boxes"]):
            if not box or box[3] - box[1] < 8:
                continue
            cut[p][f] = box[3] >= height - 3
            if not cut[p][f]:
                whole[p][f] = focal * card["tall"][f] / (box[3] - box[1])
    # The camera's height above the floor: two people at different distances have their feet on different rows.
    heights = []
    names = list(people)
    for f in range(count):
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                za, zb = whole[a][f], whole[b][f]
                if za and zb and abs(za - zb) > 0.5:
                    heights.append((people[a]["boxes"][f][3] - people[b]["boxes"][f][3]) / (focal * (1.0 / za - 1.0 / zb)))
    camera = middle(heights) if len(heights) >= 30 else CAMERA_HEIGHT_M
    if not 0.3 < camera < 3.0:
        camera = CAMERA_HEIGHT_M
    out = {p: [None] * count for p in people}
    for f in range(count):
        level = [people[p]["boxes"][f][3] - focal * camera / whole[p][f] for p in names if whole[p][f]]  # the row the floor's far edge would be on
        for p in names:
            box = people[p]["boxes"][f]
            if not box:
                continue
            far = whole[p][f]
            if far is None and box[3] - box[1] >= 8:
                over = camera - people[p]["top"][f]  # how far the top of them is below the camera (negative: above it)
                rows = box[1] - (sum(level) / len(level)) if level else 0.0
                guess = focal * people[p]["tall"][f] / (box[3] - box[1])  # too far, by however much of them is cut off
                far = focal * over / rows if level and abs(over) > 0.15 and abs(rows) > 8 else guess
                if not 0.5 * guess < far <= guess:
                    far = guess
            if far:
                out[p][f] = (-((box[0] + box[2]) / 2.0 - width / 2.0) * far / focal, far)
    return out, {"camera_height_m": round(camera, 2), "from": "boxes", "feet_cut_off_share": {str(p): round(sum(cut[p]) / float(count), 2) for p in names}}


def places(seen: dict, reach: int = None) -> dict:
    """{person: [(left, back) per frame]}: each one's smoothed place relative to the middle of the group.
    Left is the camera's left (the left of the screen); back is away from the camera."""
    reach = SMOOTH_FRAMES if reach is None else reach
    names = list(seen)
    smooth = {p: (smoothed([s[0] if s else None for s in seen[p]], reach), smoothed([s[1] if s else None for s in seen[p]], reach)) for p in names}
    count = len(smooth[names[0]][0])
    out = {p: [] for p in names}
    for f in range(count):
        mx = sum(smooth[p][0][f] for p in names) / len(names)
        mz = sum(smooth[p][1][f] for p in names) / len(names)
        for p in names:
            out[p].append((smooth[p][0][f] - mx, smooth[p][1][f] - mz))
    return out


def measure(folder: str, people: list, first: int, last: int, motions: dict, sizes: dict, sk, camera: dict = None) -> tuple:
    """The group's places over clip frames first..last. `motions` is {person: our motion over those frames, in
    GEM-X's own world}; `sizes` is {person: our legs over theirs}. Returns ({person: [(left, back)]}, notes).
    `camera`, if the worker gave it, is {person: [hips in the camera's space per frame]} and is used as it is."""
    if camera:
        return places({p: [(-c[0], c[2]) for c in camera[p]] for p in people}), {"from": "where GEM-X put each person's hips in the camera's space"}
    raw = clip_file.read(os.path.join(folder, "people-raw.json"))
    if not raw:
        raise clip_file.Stop("the clip's people have not been found")
    width, height = raw["shots"][0]["width"], raw["shots"][0]["height"]
    cards = {}
    for p in people:
        boxes = []
        for shot in raw["shots"]:
            found = next((q for q in shot["people"] if q["id"] == p), None)
            for f in range(max(first, shot["first_frame"]), min(last, shot["last_frame"]) + 1):
                boxes.append(found["boxes"][f - shot["first_frame"]] if found else None)
        if len(boxes) != last - first + 1:
            raise clip_file.Stop("the formation's seconds are not all inside the clip's shots")
        top, tall = [], []
        for f in range(len(boxes)):
            pos, _ = sk.fk(motions[p]["root"][f], [tuple(motions[p]["rotations"][f][4 * j : 4 * j + 4]) for j in range(len(sk.joints))])
            ys = [q[1] for q in pos]
            low = min(ys) - SOLE_BELOW_M
            tall.append((max(ys) + HEAD_ABOVE_M - low) / sizes[p])
            top.append(tall[-1])  # above the floor they stand on (a jump is not known to the picture)
        cards[p] = {"boxes": boxes, "top": top, "tall": tall}
    seen, notes = seen_from_boxes(cards, width, height)
    return places(seen), notes


def quick(motion: dict, reach: int = None) -> list:
    """[(x, z) per frame]: a motion's own movement over the ground with everything slow taken out."""
    reach = QUICK_FRAMES if reach is None else reach
    xs, zs = smoothed([r[0] for r in motion["root"]], reach), smoothed([r[2] for r in motion["root"]], reach)
    return [(r[0] - xs[f], r[2] - zs[f]) for f, r in enumerate(motion["root"])]


def standing_feet(sk, motion: dict) -> list:
    """Per frame, (the lower toe's place over the floor, how high it is over where it rests): the foot a body is most
    likely standing on, whatever the model says about contact."""
    toes = (sk.index["LeftToeBase"], sk.index["RightToeBase"])
    rest = [sk.rest_world_pos[t][1] for t in toes]
    out = []
    for f in range(len(motion["root"])):
        pos, _ = sk.fk(motion["root"][f], [tuple(motion["rotations"][f][4 * j : 4 * j + 4]) for j in range(len(sk.joints))])
        high = [pos[t][1] - rest[k] for k, t in enumerate(toes)]
        k = 0 if high[0] <= high[1] else 1
        out.append((k, (pos[toes[0]][0], pos[toes[0]][2]), (pos[toes[1]][0], pos[toes[1]][2]), high[k]))
    return out


def moved_together(feet: dict) -> list:
    """[(x, z) per frame step]: how far everyone's standing foot moved over the floor in the same direction at
    once, from each frame to the next. A foot someone stands on does not move. If all of theirs move the same
    way together, it is not them: it is the camera (or the model) carrying the whole picture along."""
    names = list(feet)
    count = len(feet[names[0]])
    out = []
    for f in range(count - 1):
        steps = []
        for p in names:
            k, left, right, high = feet[p][f]
            if high > LOW_FOOT_M or feet[p][f + 1][3] > LOW_FOOT_M:
                continue  # in the air: this one says nothing about the floor
            now, then = (left, right)[k], (feet[p][f + 1][1], feet[p][f + 1][2])[k]
            steps.append((then[0] - now[0], then[1] - now[1]))
        if len(steps) < len(names):
            out.append((0.0, 0.0))  # only what ALL of them share is the picture's doing
            continue
        mx, mz = sum(s[0] for s in steps) / len(steps), sum(s[1] for s in steps) / len(steps)
        size = math.hypot(mx, mz)
        if size < 1e-9:
            out.append((0.0, 0.0))
            continue
        shared = max(0.0, min((s[0] * mx + s[1] * mz) / size for s in steps))  # as far as the one who moved least that way
        shared = min(shared, size)
        out.append((mx / size * shared, mz / size * shared))
    return out


def group_drift(sk, placed: dict) -> dict:
    """How much a group set down on a stage slides as one: everyone's standing foot moving the same way at once."""
    steps = moved_together({p: standing_feet(sk, motion) for p, motion in placed.items()})
    count = len(steps)
    total = sum(math.hypot(*s) for s in steps)
    # Over a third of a second, so one frame's jitter is not a "moment".
    reach = 5
    speeds = []
    for f in range(count):
        near = steps[max(0, f - reach) : f + reach + 1]
        speeds.append(math.hypot(sum(s[0] for s in near), sum(s[1] for s in near)) / (len(near) / float(FPS)))
    moments, start = [], None
    for f in range(count + 1):
        on = f < count and speeds[f] > GROUP_DRIFT_M_PER_S
        if on and start is None:
            start = f
        if not on and start is not None:
            if f - start >= 8:
                moments.append((start, f - 1, round(100.0 * math.hypot(sum(s[0] for s in steps[start:f]), sum(s[1] for s in steps[start:f])), 1)))
            start = None
    return {
        "slides_together_cm_in_all": round(100.0 * total, 1),
        "slides_together_cm_per_s": round(100.0 * total / (count / float(FPS)), 2),
        "frames_over_5_cm_per_s": sum(1 for v in speeds if v > GROUP_DRIFT_M_PER_S),
        "share_of_frames_over_5_cm_per_s": round(sum(1 for v in speeds if v > GROUP_DRIFT_M_PER_S) / float(max(1, count)), 3),
        "fastest_cm_per_s": round(100.0 * max(speeds), 1) if speeds else 0.0,
        "moments": moments,
    }


def holding_the_group() -> bool:
    """FORGE_GROUP_HOLD=0 sets a crew down the way it was before the group's own drift was taken out, to compare."""
    return os.environ.get("FORGE_GROUP_HOLD", "").strip().lower() not in ("0", "no", "off", "false")


def stand(sk, motions: dict, where: dict, sizes: dict, origin=(0.0, 0.0), heading: float = 0.0, spread: float = 1.0, travel: float = 1.0) -> dict:
    """The motions set down together on a stage. In GEM-X's world the camera looks along +Z and the dancers face
    it (heading 180); on the stage they face `heading`, the group's middle on `origin`. Returns {person: motion}.

    What moves a dancer over the floor is three things, kept apart:

      their place in the group   from the picture, smoothed (`where`)
      their own quick movement   their motion's, with the slow part taken out, AND with what everyone did
                                 alike taken out: that part is not theirs
      the group's travel         what everyone did alike, less what the camera did. The camera's part is
                                 read off the feet: when everyone's standing foot slides the same way at once,
                                 nobody stepped; the picture moved (`moved_together`). What is left is the group
                                 really going somewhere, on its feet, and it is kept, on a long leash
                                 (GROUP_LEASH_FRAMES) so that a slow creep cannot walk the crew off the stage."""
    import timeline

    names = list(motions)
    size = sum(sizes.values()) / len(sizes)
    turn = heading - 180.0
    count = len(motions[names[0]]["root"])
    if holding_the_group() and len(names) > 1:
        carried, at = [(0.0, 0.0)], [0.0, 0.0]
        for step in moved_together({p: standing_feet(sk, motions[p]) for p in names}):
            at = [at[0] + step[0], at[1] + step[1]]
            carried.append((at[0], at[1]))
        # Everyone's path with the camera's part out; then what they share, from where it starts.
        own = {p: [(r[0] - carried[f][0], r[2] - carried[f][1]) for f, r in enumerate(motions[p]["root"])] for p in names}
        shared = [(sum(own[p][f][0] for p in names) / len(names), sum(own[p][f][1] for p in names) / len(names)) for f in range(count)]
        slow_x, slow_z = smoothed([c[0] for c in shared], GROUP_LEASH_FRAMES), smoothed([c[1] for c in shared], GROUP_LEASH_FRAMES)
        group = [((shared[f][0] - slow_x[f]) * travel, (shared[f][1] - slow_z[f]) * travel) for f in range(count)]
        mine = {}
        for p in names:
            apart = {"root": [[own[p][f][0] - shared[f][0], 0.0, own[p][f][1] - shared[f][1]] for f in range(count)]}
            mine[p] = [(q[0] + group[f][0], q[1] + group[f][1]) for f, q in enumerate(quick(apart))]
    else:
        mine = {p: quick(motions[p]) for p in names}
    out = {}
    for p, motion in motions.items():
        turned = timeline.moved(motion, turn, 0.0, 0.0)
        roots = []
        for f, root in enumerate(turned["root"]):
            left, back = where[p][f]
            # The camera's left is +X in GEM-X's world, and "back" is +Z; then all of it turned to the stage.
            x, z = timeline.turn_xz(left * size * spread + mine[p][f][0], back * size * spread + mine[p][f][1], turn)
            roots.append([round(origin[0] + x, 5), root[1], round(origin[1] + z, 5)])
        out[p] = {**turned, "root": roots}
    return out


def closest(sk, placed: dict, every: int = 2) -> dict:
    """How near any two of them come: hips to hips, and any joint of one to any joint of another."""
    names = list(placed)
    count = len(placed[names[0]]["root"])
    best = {"hips_cm": 1e9, "bodies_cm": 1e9}
    for f in range(0, count, every):
        pos = {p: sk.fk(placed[p]["root"][f], [tuple(placed[p]["rotations"][f][4 * j : 4 * j + 4]) for j in range(len(sk.joints))])[0] for p in names}
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                hips = 100.0 * math.hypot(pos[a][0][0] - pos[b][0][0], pos[a][0][2] - pos[b][0][2])
                if hips < best["hips_cm"]:
                    best.update({"hips_cm": round(hips, 1), "hips_between": [a, b], "hips_frame": f})
                near = 100.0 * min(math.dist(u, v) for u in pos[a] for v in pos[b])
                if near < best["bodies_cm"]:
                    best.update({"bodies_cm": round(near, 1), "bodies_between": [a, b], "bodies_frame": f})
    return best


def main() -> None:
    import beat as video_beat
    from soma import Skeleton

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("clip")
    parser.add_argument("--people", required=True, help="their numbers on the clip's page, with commas")
    parser.add_argument("--from", dest="from_s", type=float, required=True)
    parser.add_argument("--to", dest="to_s", type=float, required=True)
    parser.add_argument("--origin", default="0,0", help="where on the stage the middle of the group goes: x,z")
    parser.add_argument("--heading", type=float, default=0.0, help="which way the house is")
    parser.add_argument("--spread", type=float, default=1.0)
    parser.add_argument("--travel", type=float, default=1.0, help="how much of the group's own travel to keep (1: all of it; less to fit a small stage)")
    args = parser.parse_args()
    sk = Skeleton.load()
    people = [int(p) for p in args.people.split(",")]
    try:
        group = video_beat.crew(sk, {"name": "formation", "clip": args.clip, "from_s": args.from_s, "to_s": args.to_s,
                                     "formation": {"people": people, "origin": [float(v) for v in args.origin.split(",")], "heading": args.heading, "spread": args.spread, "travel": args.travel}}, 0, 0)
    except (clip_file.Stop, ValueError) as stop:
        sys.exit(f"formation: {stop}")
    for p in people:
        roots = group["placed"][p]["root"]
        xs, zs = [r[0] for r in roots], [r[2] for r in roots]
        print(f"FORMATION person {p}: starts at [{roots[0][0]:.2f}, {roots[0][2]:.2f}], ends at [{roots[-1][0]:.2f}, {roots[-1][2]:.2f}]; x {min(xs):.2f} to {max(xs):.2f}, z {min(zs):.2f} to {max(zs):.2f}")
    near = group["closest"]
    print(f"FORMATION closest: hips {near['hips_cm']} cm (persons {near['hips_between']}, {args.from_s + near['hips_frame'] / FPS:.1f} s of the clip); any two joints {near['bodies_cm']} cm (persons {near['bodies_between']}, {args.from_s + near['bodies_frame'] / FPS:.1f} s)")
    drift = group["group"]
    print(f"FORMATION as one: everyone's standing foot slides the same way {drift['slides_together_cm_in_all']} cm in all ({drift['slides_together_cm_per_s']} cm a second), over 5 cm a second on {round(100 * drift['share_of_frames_over_5_cm_per_s'], 1)}% of frames; "
          + ("moments (seconds of the clip, cm): " + ", ".join(f"{args.from_s + a / FPS:.1f}-{args.from_s + b / FPS:.1f} {c}" for a, b, c in drift["moments"]) if drift["moments"] else "no moment of it lasts a quarter of a second"))
    roots = [r for p in people for r in group["placed"][p]["root"]]
    print(f"FORMATION room: x {min(r[0] for r in roots):.2f} to {max(r[0] for r in roots):.2f}, z {min(r[2] for r in roots):.2f} to {max(r[2] for r in roots):.2f} (hips; bodies reach further)")
    print("FORMATION " + json.dumps(group["notes"]))


if __name__ == "__main__":
    main()
