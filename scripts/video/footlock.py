"""Feet that are down stay where they are: a video's motion with its sliding taken out.

    python3 scripts/video/footlock.py <motion.json> [<out.json>]     # measures; writes the locked motion if asked

Motion read off a video slides. GEM-X's own feet creep 13 to 18 cm a second
while it says they are planted; a camera that pans or zooms is read as the
dancer gliding; and a crew held to its formation is nudged all the time. On a
stage it looks like skating. A dancer does not get from one place to another
by gliding: they step. So:

  stance   For each foot, the stretches it is down: the model's own contact
           says so (its ankle or its toes held still), it is near the floor,
           and it is not travelling fast; or it is plainly lying still on the
           floor whatever the model says.
  pin      Over a stance the foot's pivot is held on ONE spot of the floor
           (where it was on average): the ball of the foot if the toes carry
           it, the heel if only the heel is down. With heel and toes both
           down the foot is flat and its turn is held too. With only the ball
           down the foot is free to turn about it, so a pivot is still a
           pivot.
  body     The hips are carried by whichever feet are down: moved, smoothly,
           by what those feet were moved. What is left for each leg (two feet
           down that were sliding different ways) is taken up by the knee: the
           leg is solved hip to ankle, bending in the plane it bent in.
  drift    So whatever was sliding the body (the model, the camera, the
           formation) no longer moves it while a foot is down. It shows where
           it should: a foot comes down in a new place. Drift becomes steps.

Nothing above the hips is touched, and frames with no foot down (a jump) are
left as they were, eased into the stances either side.

Plain Python: no Blender, no numpy. Used by soma77.py (a clip's own shot) and
beat.py (a stretch of a clip in a shot, a crew in formation), after the
motion is placed.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
sys.path.insert(0, os.path.join(REPO, "motionbricks_worker", "models"))
from soma import Skeleton, add, cross, dot, length, qconj, qmul, qnorm, qrot, qslerp, scale, sub, unit  # noqa: E402
from soma_bridge import qbetween  # noqa: E402

FPS = 30
ON_GROUND = 0.5  # the model's contact confidence above which a heel or toe counts as down
LOW_M = 0.10  # ...if it is also within this of the floor
SLOW_M_PER_S = 0.6  # ...and not travelling faster than this (a foot the model calls down while it flies is not pinned)
LYING_STILL = (0.03, 0.12)  # within this of the floor (m) and slower than this (m/s): down, whatever the model says
SHORTEST_STANCE = 3  # frames
BRIDGE = 2  # frames: a stance broken for this long or less is one stance
EASE = 6  # frames over which a pinned foot is let go, and taken hold of
BODY_SMOOTH = 4  # frames either side the hips' correction is averaged over
STRAIGHTEST = 0.995  # a leg is not stretched past this share of its length
MOST_DROP_M = 0.12  # the hips are not lowered more than this to let a leg reach its foot
HANGS = 0.5  # a foot in the air keeps this share of its height over the floor when the hips come down
MOST_LIFT_M = 0.08  # a pinned pivot is not moved up or down by more than this to reach the floor
SIDES = (("l", "Left", 0, 1), ("r", "Right", 2, 3))  # tag, joint prefix, heel and toe columns of `contacts`


def horizontal(a, b) -> float:
    return math.hypot(a[0] - b[0], a[2] - b[2])


def stretches(flags: list, shortest: int = 1, bridge: int = 0) -> list:
    """[(first, last)] of the stretches that are True, short gaps closed and short stretches dropped."""
    flags = list(flags)
    count = len(flags)
    f = 0
    while f < count:  # close short gaps
        if not flags[f]:
            g = f
            while g < count and not flags[g]:
                g += 1
            if 0 < f and g < count and g - f <= bridge:
                for k in range(f, g):
                    flags[k] = True
            f = g
        else:
            f += 1
    out, start = [], None
    for i, on in enumerate(flags + [False]):
        if on and start is None:
            start = i
        if not on and start is not None:
            if i - start >= shortest:
                out.append((start, i - 1))
            start = None
    return out


def stances(sk: Skeleton, motion: dict, world: list) -> dict:
    """{"l": [stance, ...], "r": [...]}: when each foot is down, and what it is down on.
    A stance is {"first", "last", "pivot": "toe" | "heel", "flat": [(first, last), ...]}."""
    count = len(world)
    out = {}
    for tag, side, heel_col, toe_col in SIDES:
        ankle, toe = sk.index[f"{side}Foot"], sk.index[f"{side}ToeBase"]
        rest = {ankle: sk.rest_world_pos[ankle][1], toe: sk.rest_world_pos[toe][1]}
        down = []
        for f in range(count):
            pos = world[f][0]
            a, b = max(0, f - 1), min(count - 1, f + 1)
            speed = max(horizontal(world[b][0][j], world[a][0][j]) for j in (ankle, toe)) * FPS / max(1, b - a)
            height = min(pos[ankle][1] - rest[ankle], pos[toe][1] - rest[toe])
            said = max(motion["contacts"][f][heel_col], motion["contacts"][f][toe_col]) > ON_GROUND
            down.append((said and height < LOW_M and speed < SLOW_M_PER_S) or (height < LYING_STILL[0] and speed < LYING_STILL[1]))
        found = []
        for first, last in stretches(down, SHORTEST_STANCE, BRIDGE):
            heel_on = [motion["contacts"][f][heel_col] > ON_GROUND for f in range(first, last + 1)]
            toe_on = [motion["contacts"][f][toe_col] > ON_GROUND for f in range(first, last + 1)]
            both = [h and t for h, t in zip(heel_on, toe_on)]
            found.append({"first": first, "last": last, "pivot": "toe" if sum(toe_on) >= sum(heel_on) else "heel",
                          "flat": [(first + a, first + b) for a, b in stretches(both, SHORTEST_STANCE, BRIDGE)]})
        out[tag] = found
    return out


def eased(edge: int) -> float:
    """1 inside a stance, falling smoothly to 0 over EASE frames outside it."""
    if edge <= 0:
        return 1.0
    w = max(0.0, 1.0 - edge / (EASE + 1.0))
    return w * w * (3.0 - 2.0 * w)


def lock(sk: Skeleton, motion: dict) -> tuple:
    """The motion with its planted feet held still. Returns (motion, what was done)."""
    count, joints = len(motion["root"]), len(sk.joints)
    rows = [[tuple(row[4 * j : 4 * j + 4]) for j in range(joints)] for row in motion["rotations"]]
    world = [sk.fk(motion["root"][f], rows[f]) for f in range(count)]
    found = stances(sk, motion, world)

    # What each foot needs, frame by frame: where its ankle should be, and (flat on the floor) which way it is turned.
    feet = {}
    for tag, side, _, _ in SIDES:
        ankle, toe = sk.index[f"{side}Foot"], sk.index[f"{side}ToeBase"]
        want = [None] * count  # (weight, ankle target, foot rotation or None)
        moved, spots = 0.0, 0
        for stance in found[tag]:
            first, last = stance["first"], stance["last"]
            pivot = toe if stance["pivot"] == "toe" else ankle
            floor = sk.rest_world_pos[pivot][1]
            # Flat stretches: the foot's turn is held as it was in the middle of each, eased at its ends.
            turn = {f: world[f][1][ankle] for f in range(max(0, first - EASE), min(count, last + EASE + 1))}
            for a, b in stance["flat"]:
                held = world[(a + b) // 2][1][ankle]
                for f in range(max(first, a - 2), min(last, b + 2) + 1):
                    w = eased(max(a - f, f - b, 0) * (EASE + 1) // 3)
                    turn[f] = qslerp(world[f][1][ankle], held, w)

            def pivot_at(f: int):
                """Where the pivot would be on frame f with the foot turned as it will be."""
                if pivot == ankle:
                    return world[f][0][ankle]
                off = qrot(qconj(world[f][1][ankle]), sub(world[f][0][toe], world[f][0][ankle]))  # the ball, in the foot's own frame
                return add(world[f][0][ankle], qrot(turn[f], off))

            inside = [pivot_at(f) for f in range(first, last + 1)]
            pin = (sum(p[0] for p in inside) / len(inside), 0.0, sum(p[2] for p in inside) / len(inside))
            spots += 1
            for f in range(max(0, first - EASE), min(count, last + EASE + 1)):
                edge = max(first - f, f - last, 0)
                w = eased(edge)
                if want[f] is not None and want[f][0] >= w:
                    continue  # this frame is nearer another stance of the same foot
                here = pivot_at(min(max(f, first), last)) if edge else pivot_at(f)  # outside: what the foot was moved by as it let go
                lift = max(-MOST_LIFT_M, min(MOST_LIFT_M, floor - here[1]))
                shift = (pin[0] - here[0], lift, pin[2] - here[2])
                if not edge:
                    moved = max(moved, math.hypot(shift[0], shift[2]))
                want[f] = (w, shift, turn.get(f) if not edge else None)
        held = set(f for s in found[tag] for f in range(s["first"], s["last"] + 1))
        said = [f for f in range(count) if max(motion["contacts"][f][SIDES[0 if tag == "l" else 1][2]], motion["contacts"][f][SIDES[0 if tag == "l" else 1][3]]) > ON_GROUND]
        feet[tag] = {"want": want, "ankle": ankle, "toe": toe, "spots": spots, "most_moved_cm": round(100.0 * moved, 1), "frames_down": len(held),
                     # Frames the model calls the foot down while it is plainly travelling or off the floor: left as they are.
                     "called_down_but_moving_frames": sum(1 for f in said if f not in held)}

    # The hips go with the feet that are down: the average of what those feet were moved, smoothed.
    carry = [None] * count
    for f in range(count):
        total, sums = 0.0, [0.0, 0.0]
        for tag in feet:
            if feet[tag]["want"][f]:
                w, shift, _ = feet[tag]["want"][f]
                total += w
                sums[0] += w * shift[0]
                sums[1] += w * shift[2]
        if total > 1e-6:
            carry[f] = (sums[0] / total, sums[1] / total)
    known = [f for f in range(count) if carry[f]]
    body, before = [], None
    after = iter(known + [None])
    ahead = next(after)
    for f in range(count):
        while ahead is not None and ahead < f:
            ahead = next(after)
        if carry[f]:
            body.append(carry[f])
            before = f
        elif before is not None and ahead is not None:  # in the air between two stances: carried evenly from one to the other
            t = (f - before) / float(ahead - before)
            t = t * t * (3.0 - 2.0 * t)
            body.append((carry[before][0] + (carry[ahead][0] - carry[before][0]) * t, carry[before][1] + (carry[ahead][1] - carry[before][1]) * t))
        elif before is not None or ahead is not None:
            body.append(carry[before if before is not None else ahead])
        else:
            body.append((0.0, 0.0))
    smooth = []
    for f in range(count):
        reach = min(BODY_SMOOTH, f, count - 1 - f)  # the same either side, so a steady correction is not bent at the ends
        near = body[f - reach : f + reach + 1]
        smooth.append((sum(b[0] for b in near) / len(near), sum(b[1] for b in near) / len(near)))

    # A leg that is nearly straight cannot reach a foot held a little further off. The hips come down by what
    # the longest reach needs (a bent knee, not a foot let go), and never jump: the drop is spread over its neighbours.
    need = [0.0] * count
    for f in range(count):
        pos = world[f][0]
        for tag, side, _, _ in SIDES:
            if not feet[tag]["want"][f]:
                continue
            w, pinned, _ = feet[tag]["want"][f]
            hip, knee, ankle = sk.index[f"{side}Leg"], sk.index[f"{side}Shin"], feet[tag]["ankle"]
            # (A leg already straighter than that is let be as straight as it was.)
            most = max(STRAIGHTEST * (length(sub(pos[knee], pos[hip])) + length(sub(pos[ankle], pos[knee]))), length(sub(pos[ankle], pos[hip])))
            target = add(pos[ankle], scale(sub(pinned, (smooth[f][0], 0.0, smooth[f][1])), w))
            h = pos[hip]
            across = horizontal(target, h)
            if across < most and length(sub(target, h)) > most:
                need[f] = max(need[f], min(MOST_DROP_M, (h[1] - target[1]) - math.sqrt(most * most - across * across)))
    widest = [max(need[max(0, f - BODY_SMOOTH) : f + BODY_SMOOTH + 1]) for f in range(count)]
    drop = [sum(widest[max(0, f - BODY_SMOOTH) : f + BODY_SMOOTH + 1]) / len(widest[max(0, f - BODY_SMOOTH) : f + BODY_SMOOTH + 1]) for f in range(count)]

    # Each leg, hip to ankle: the ankle put where the pinned foot needs it, the knee bending in the plane it bent in.
    out_root, out_rows, reach_short = [], [], 0
    for f in range(count):
        pos, rot = world[f]
        local = list(rows[f])
        shift = (smooth[f][0], -drop[f], smooth[f][1])
        for tag, side, _, _ in SIDES:  # a leg whose foot is not held still has its foot where it was, under hips that came down
            if drop[f] > 1e-4 and not feet[tag]["want"][f]:
                feet[tag]["want"][f] = (0.0, (0.0, 0.0, 0.0), None)
        for tag, side, _, _ in SIDES:
            card = feet[tag]
            if not card["want"][f]:
                continue
            w, pinned, turn = card["want"][f]
            hip, knee, ankle = sk.index[f"{side}Leg"], sk.index[f"{side}Shin"], card["ankle"]
            foot_rot = turn or rot[ankle]
            # The ankle goes where the foot's pivot needs it: by the pin's shift, less what the hips already moved.
            # (A held turn is in the pin already: the pivot was worked out with the foot turned as it will be.)
            target = add(pos[ankle], scale(sub(pinned, (shift[0], 0.0, shift[2])), w))
            target = (target[0], target[1] + drop[f] * (1.0 if w > 0.0 else HANGS), target[2])  # in the hips' frame, which came down
            h, k, a = pos[hip], pos[knee], pos[ankle]
            l1, l2 = length(sub(k, h)), length(sub(a, k))
            reach = sub(target, h)
            far = length(reach)
            if far > l1 + l2 + 1e-3:
                reach_short += 1  # held further off than the leg is long: it gets as near as it can
            d = max(abs(l1 - l2) + 1e-4, min(l1 + l2 - 1e-4, far))
            along = unit(reach) if far > 1e-9 else unit(sub(a, h))
            bend = sub(sub(k, h), scale(along, dot(sub(k, h), along)))
            if length(bend) < 1e-5:
                bend = qrot(rot[hip], (0.0, 0.0, 1.0))  # a dead straight leg: the knee goes the way the thigh faces
                bend = sub(bend, scale(along, dot(bend, along)))
            bend = unit(bend)
            reach_a = (l1 * l1 - l2 * l2 + d * d) / (2.0 * d)
            new_knee = add(h, add(scale(along, reach_a), scale(bend, math.sqrt(max(0.0, l1 * l1 - reach_a * reach_a)))))
            new_ankle = add(h, scale(along, d))
            first = qbetween(sub(k, h), sub(new_knee, h))
            thigh = qnorm(qmul(first, rot[hip]))
            second = qbetween(qrot(first, sub(a, k)), sub(new_ankle, new_knee))
            shin = qnorm(qmul(second, qmul(first, rot[knee])))
            parent = rot[sk.parents[hip]]
            local[hip] = qnorm(qmul(qconj(parent), thigh))
            local[knee] = qnorm(qmul(qconj(thigh), shin))
            local[ankle] = qnorm(qmul(qconj(shin), foot_rot))
        out_root.append([round(motion["root"][f][0] + shift[0], 5), round(motion["root"][f][1] - drop[f], 5), round(motion["root"][f][2] + shift[2], 5)])
        out_rows.append([round(c, 6) for q in local for c in q])
    locked = {**motion, "root": out_root, "rotations": out_rows}
    report = {
        "feet": {tag: {k: feet[tag][k] for k in ("spots", "frames_down", "most_moved_cm", "called_down_but_moving_frames")} for tag in feet},
        "hips_moved_cm_at_most": round(100.0 * max(math.hypot(*s) for s in smooth), 1),
        "hips_lowered_cm_at_most": round(100.0 * max(drop), 1),
        "frames_a_leg_could_not_reach": reach_short,
    }
    return locked, report


def slide(sk: Skeleton, motion: dict) -> dict:
    """How much the feet slide while down, the way checks.py measures it (per heel and toe, while the model says
    it is on the ground): {"cm_per_s": {...}, "worst_stretch_cm": {...}}."""
    import checks

    feet = checks.feet(sk, motion, checks.world_positions(sk, motion))
    return {"cm_per_s": {k: v["slide_speed_cm_per_s"] for k, v in feet.items()}, "worst_stretch_cm": {k: v["worst_stretch_drift_cm"] for k, v in feet.items()}}


def wanted(setting=None) -> bool:
    """Is foot locking on? A beat or a caller can say; FORGE_FOOT_LOCK=0 turns it off everywhere, to compare."""
    if os.environ.get("FORGE_FOOT_LOCK", "").strip().lower() in ("0", "no", "off", "false"):
        return False
    return setting is not False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("motion")
    parser.add_argument("out", nargs="?")
    args = parser.parse_args()
    sk = Skeleton.load()
    with open(args.motion) as f:
        motion = json.load(f)
    locked, report = lock(sk, motion)
    before, after = slide(sk, motion), slide(sk, locked)
    for foot in before["cm_per_s"]:
        print(f"FOOTLOCK {foot}: slides {before['cm_per_s'][foot]} -> {after['cm_per_s'][foot]} cm a second while down; worst stretch {before['worst_stretch_cm'][foot]} -> {after['worst_stretch_cm'][foot]} cm")
    print("FOOTLOCK " + json.dumps(report))
    if args.out:
        with open(args.out, "w") as f:
            json.dump(locked, f, separators=(",", ":"))


if __name__ == "__main__":
    main()
