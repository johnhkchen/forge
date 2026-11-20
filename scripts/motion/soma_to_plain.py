"""Turns a SOMA motion into the plain form animate.py plays on any of our characters.

    python3 scripts/motion/soma_to_plain.py <motion.json> <out.json> [--name hero]

In: the repo's motion format, "forge-soma-motion/1" (what the motion worker
answers): fps, joints by SOMA name, and per frame the root position, every
joint's local rotation [x, y, z, w], and how firmly each heel and toe is down.
Any set of SOMA joints will do as long as it holds the ones bones.json names;
extra joints (fingers, a 77-joint skeleton's twist bones) are ignored, because
joints are looked up by name and a joint the file lacks keeps its rest pose.

Out: animate.py's plain motion (see its header): where the hips are, where
the ball of each foot is and whether it is planted, and how far each of our
bones has turned from the T-pose, in units of the hip height, in our axes
(x left, y back, z up). The renaming is bones.json's; a SOMA joint listed
there as `soma_also` (Spine2, Neck2) has its turn folded into the bone above.

Feet. A motion model's feet drift a little while they are meant to be down.
Here each stretch where the model says a foot is on the ground becomes one
fixed spot (the average of where the ball was), eased in and out over a few
frames (never over frames held on the spot before), and the foot is marked planted, so animate.py's leg solve holds it
there. `planted_feet` in the result says how far each foot was moved to do so.

Plain Python: no Blender, no numpy.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from soma import REPO, Skeleton, Z, add, cross, dot, length, qconj, qfrom_to, qmul, qrot, scale, sub  # noqa: E402
from soma import unit as unit_of  # noqa: E402

BONES_FILE = os.path.join(REPO, ".claude", "skills", "tidy-mesh", "bones.json")
ON_GROUND = 0.5  # the model's contact confidence above which a foot counts as down
STILL_M_PER_FRAME = 0.015  # a ball of the foot moving less than this a frame (0.45 m/s) can be pinned
MIN_PLANT = 4  # frames; shorter touches are left as the model made them
EASE = 4  # frames to ease a foot onto and off its planted spot
CONTACT_COLUMNS = {"l": (0, 1), "r": (2, 3)}  # heel, toe


def ours(v):
    """A SOMA vector or quaternion's vector part (x left, y up, z forward) in our axes (x left, y back, z up)."""
    return (v[0], -v[2], v[1])


def stretches(flags, least):
    out, start = [], None
    for i, on in enumerate(list(flags) + [False]):
        if on and start is None:
            start = i
        if not on and start is not None:
            if i - start >= least:
                out.append((start, i - 1))
            start = None
    return out


def convert(motion: dict, sk: Skeleton, name: str = "motion", plant: bool = True) -> tuple:
    with open(BONES_FILE) as f:
        table = json.load(f)["bones"]
    have = {joint: j for j, joint in enumerate(motion["joints"])}
    missing = sorted({card["soma"] for card in table.values()} - set(have))
    if missing:
        raise ValueError(f"the motion lacks joints our bones need: {', '.join(missing)}")
    count = len(motion["root"])
    unit = sk.rest_world_pos[sk.index["LeftLeg"]][1]  # SOMA's hip height: the plain form's unit of length
    rest_hips = sk.rest_world_pos[0]

    # Each of our bones follows one SOMA joint; with soma_also, the last of them (its turn already includes the ones above).
    follows = {bone: (card.get("soma_also") or [card["soma"]])[-1] for bone, card in table.items()}
    turns = {bone: [] for bone in table}
    hips, balls, feet_turn = [], {"l": [], "r": []}, {"l": [], "r": []}
    for f in range(count):
        row = motion["rotations"][f]
        local = [tuple(row[4 * have[j] : 4 * have[j] + 4]) if j in have else sk.rest_rot[i] for i, j in enumerate(sk.joints)]
        pos, rot = sk.fk(motion["root"][f], local)
        for bone, joint in follows.items():
            i = sk.index[joint]
            q = qmul(rot[i], qconj(sk.rest_world_rot[i]))  # how far it has turned from the T-pose, in the world
            v = ours(q)
            turns[bone].append([round(q[3], 6), round(v[0], 6), round(v[1], 6), round(v[2], 6)])
        # Arms: our elbows are one-way hinges, and a motion model is free to share an arm's twist
        # between the upper arm and the forearm however it likes. So the two arm bones are set from
        # where the shoulder, elbow and wrist ARE: the upper arm points at the elbow, the forearm
        # at the wrist, and both turn so the elbow's hinge lies square to the plane the arm bends in.
        for side, tag in (("Left", "l"), ("Right", "r")):
            a, b, c = (sk.index[f"{side}{part}"] for part in ("Arm", "ForeArm", "Hand"))
            d1, d2 = unit_of(sub(pos[b], pos[a])), unit_of(sub(pos[c], pos[b]))
            r1 = unit_of(sub(sk.rest_world_pos[b], sk.rest_world_pos[a]))
            r2 = unit_of(sub(sk.rest_world_pos[c], sk.rest_world_pos[b]))
            hinge_rest = unit_of(cross(r1, Z))  # in the T-pose an elbow folds the hand forward
            bend = cross(d1, d2)
            carried = qrot(qmul(rot[a], qconj(sk.rest_world_rot[a])), hinge_rest)  # the hinge as the model's own upper arm carries it
            folded = min(1.0, length(bend) / 0.26)  # 0 for a straight arm (no plane to read), 1 from about 15 degrees of bend
            if length(bend) > 1e-6 and dot(bend, carried) < 0 and folded < 1.0:
                bend = scale(bend, -1.0)  # nearly straight: don't let a hair of bend the wrong way flip the arm over
            hinge = unit_of(add(scale(carried, 1.0 - folded), scale(unit_of(bend) if length(bend) > 1e-6 else carried, folded)))
            for bone, rest_dir, now_dir in ((f"upper_arm_{tag}", r1, d1), (f"forearm_{tag}", r2, d2)):
                q = qfrom_to(rest_dir, hinge_rest, now_dir, hinge)
                v = ours(q)
                turns[bone][-1] = [round(q[3], 6), round(v[0], 6), round(v[1], 6), round(v[2], 6)]
        hips.append(tuple(c / unit for c in ours(tuple(pos[0][a] - rest_hips[a] for a in range(3)))))
        for tag, side in (("l", "Left"), ("r", "Right")):
            toe, foot = sk.index[f"{side}ToeBase"], sk.index[f"{side}Foot"]
            ball = ours(pos[toe])
            lift = pos[toe][1] - sk.rest_world_pos[toe][1]
            points = qrot(qmul(rot[foot], qconj(sk.rest_world_rot[foot])), Z)
            balls[tag].append([ball[0] / unit, ball[1] / unit, lift / unit])
            feet_turn[tag].append(
                (math.degrees(math.asin(max(-1.0, min(1.0, -points[1])))), math.degrees(math.atan2(points[0], points[2])))
            )

    planted = {"l": [0] * count, "r": [0] * count}
    moved = {}
    for tag, columns in CONTACT_COLUMNS.items():
        # Down: the model says so, and the ball is in fact (nearly) still. A foot the model calls down
        # while it is still travelling is a slide too big to pin without a visible snap, and is left alone.
        still = [
            unit * math.hypot(balls[tag][min(f + 1, count - 1)][0] - balls[tag][max(f - 1, 0)][0], balls[tag][min(f + 1, count - 1)][1] - balls[tag][max(f - 1, 0)][1]) / 2.0
            < STILL_M_PER_FRAME
            for f in range(count)
        ]
        down = [max(c[columns[0]], c[columns[1]]) > ON_GROUND and still[f] for f, c in enumerate(motion["contacts"])]
        worst, total, spots = 0.0, 0, 0
        for first, last in stretches(down, MIN_PLANT) if plant else []:
            spot = [sum(balls[tag][f][a] for f in range(first, last + 1)) / (last - first + 1) for a in (0, 1)]
            spots += 1
            for f in range(max(0, first - EASE), min(count, last + EASE + 1)):
                # Fully on the spot while down; easing toward it just before and away just after.
                edge = max(first - f, f - last, 0)
                if edge and planted[tag][f]:
                    continue  # this frame is held on the spot before: easing toward the next one would slide a planted foot
                w = 1.0 - edge / (EASE + 1.0)
                w = w * w * (3.0 - 2.0 * w)
                before = list(balls[tag][f])
                balls[tag][f][0] += (spot[0] - balls[tag][f][0]) * w
                balls[tag][f][1] += (spot[1] - balls[tag][f][1]) * w
                if edge == 0:
                    balls[tag][f][2] = 0.0
                    planted[tag][f] = 1
                    total += 1
                    worst = max(worst, unit * math.hypot(balls[tag][f][0] - before[0], balls[tag][f][1] - before[1]))
        moved[tag] = {"spots": spots, "frames_planted": total, "most_moved_cm": round(100 * worst, 2)}

    feet = {
        tag: [
            [round(b[0], 5), round(b[1], 5), round(b[2], 5), round(feet_turn[tag][f][0], 3), round(feet_turn[tag][f][1], 3), planted[tag][f]]
            for f, b in enumerate(balls[tag])
        ]
        for tag in ("l", "r")
    }
    plain = {
        "name": name,
        "version": 1,
        "fps": motion.get("fps", 30),
        "frames": count - 1,
        "loop": False,
        "unit": "hip_height",
        "axes": "x left, y back, z up; the character faces -y",
        "travel": 0.0,  # the motion carries its own travel in `hips`; the ground stays still
        "hips": [[round(c, 5) for c in h] for h in hips],
        "feet": feet,
        "turns": turns,
    }
    return plain, {"frames": count, "bones": sorted(turns), "soma_hip_height_m": round(unit, 4), "planted_feet": moved}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("motion")
    parser.add_argument("out")
    parser.add_argument("--name", default="hero")
    parser.add_argument("--raw-feet", action="store_true", help="leave the feet as the model made them (no planting)")
    args = parser.parse_args()
    with open(args.motion) as f:
        motion = json.load(f)
    plain, report = convert(motion, Skeleton.load(), args.name, plant=not args.raw_feet)
    with open(args.out, "w") as f:
        json.dump(plain, f, separators=(",", ":"))
    print("PLAIN " + json.dumps(report))


if __name__ == "__main__":
    main()
