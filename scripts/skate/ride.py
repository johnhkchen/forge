"""Lays out a run on the halfpipe: where the board is on every frame, and what the rider does on it.

    python3 scripts/skate/ride.py <ride.json> <body.json> <out folder>

A ride script is plain data (scripts/skate/rides/first.json is one):

    {"set": "halfpipe",
     "passes": [
       {"trick": "kickturn"},                      up the wall, stall, turn back
       {"trick": "air", "height_m": 0.6},          leave the top by this much, turn in the air, land back on the wall
       {"trick": "air grab", "height_m": 0.9},     the same, tucked, a hand on the board's edge
       {"trick": "handplant"},                     a hand on the coping and the body over it
       {"trick": "air", "pose_from": {"video": "halfpipe", "shot": 4, "from_s": 22.0, "to_s": 23.6}}
     ]}                                            ... the body's pose in that trick taken from a video (video_pose.py)

He starts at the top of the left wall. A pass is one crossing of the pipe,
ending in its trick on the wall he reaches; after the last one he rolls to a
stop on the flat.

Two things are worked out here, and kept apart:

  The ride: the board. It stays on the ramp's surface (scripts/skate/pipe.py)
  with both trucks on it, so its up is the way the surface faces. Its speed
  is simple energy: gravity along the surface, a little drag, and pumping,
  which adds (or scrubs) a little speed through each transition, as much as
  the next trick needs and no more than a rider can (MOST_PUMP). A trick that
  asks for more height than the speed gives is done lower, or as a kickturn,
  and the result says so. Past the lip the board is in the air: straight up
  and back down under gravity alone, turning half way round as it goes. In a
  handplant the board swings up over the planted hand and back.

  The rider: a body standing on that board. His poses (rider.py) are in the
  board's own frame, feet over the bolts on every frame, so his motion is an
  ordinary plain motion that animate.py plays like a walk, with the deck as
  his floor. Knees bend into the bottom of each transition and push out of
  it, he crouches into each air, tucks, grabs.

It writes, into the out folder:

    rider.motion.json   the rider's plain motion, in the board's frame
    ride.json           the run: for every frame where the middle of the deck
                        is and which way the board points and faces (the
                        set's axes), what each pass turned out to be, and
                        what was measured: how far the wheels are from the
                        surface, how fast he went

apply_ride.py bakes the motion onto a character and carries rider and board
along the ride. Plain Python: no Blender, no numpy.
"""

from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "fight"))
import board  # noqa: E402
import moves  # noqa: E402
import rider  # noqa: E402
from moves import add, cross, dot, mix, sub, times, unit  # noqa: E402
from pipe import Pipe  # noqa: E402

FPS = 30
SUB = 20                 # steps of the arithmetic per frame
DT = 1.0 / (FPS * SUB)
G = 9.81
DRAG = 0.035             # what rolling and the air take, per second, as a share of the speed
MOST_PUMP = 1.3          # m/s2 along the surface through a transition: the most a rider adds by pumping (or scrubs)
STOP_DRAG = 1.15         # the same on the flat, once he is done and lets the board run out         # the same, once he is done and lets the board run down
KICKTURN_BELOW = 0.55    # in a kickturn the middle of the board stops this far under the lip
KICKTURN_S = 0.9         # how long the turn takes
NOSE_UP_DEG = 9.0        # how far the nose lifts in a kickturn (the back wheels stay on)
LEAST_AIR = 0.2          # an air lower than this is not an air: it is done as a kickturn
AIR_TILT_DEG = 32.0      # at the top of an air the board has tipped this far toward level
AIR_IN = 0.14            # and drifted this far in over the pipe, per metre of height (at most 0.25 m)
PLANT_S = 1.9            # how long a handplant takes, hand down to hand up
PLANT_TILT_DEG = 84.0    # how far over the board goes: nearly upside down
PLANT_SPEED = 1.5        # he comes to the lip at about this speed for it (m/s)
PLANT_RISE = 0.44        # before it goes over, the board rides this far up past the lip: its tail comes level with the hand
PALM_THICK = 0.03        # the middle of a hand is this far off what it rests on
PLANT_REACH = 0.30       # the hand goes down this far along the coping from the middle of the board
HOLD_S = 1.4             # standing still at the end
TRICKS = ("kickturn", "air", "air grab", "handplant")
L = (0.0, 0.0, 1.0)      # along the pipe


def ease(t):
    t = moves.clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def bump(u, ramp):
    """0 at both ends, 1 through the middle, easing over `ramp` of the way at each end."""
    return ease(u / ramp) * ease((1.0 - u) / ramp)


def keyed(keys, u):
    """A value that passes through each of `keys` [(when, value)], in straight lines."""
    for (ua, a), (ub, b) in zip(keys, keys[1:]):
        if u <= ub:
            return mix(a, b, (u - ua) / (ub - ua))
    return keys[-1][1]


def about_l(v, degrees):
    """A vector turned about the pipe's long axis."""
    a = math.radians(degrees)
    return (v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a), v[2])


# ---- the ride: energy on the surface ----


def step(pipe, s, v, pump, drag):
    p = pipe.at(s)
    a = -G * p["tangent"][1]
    if p["part"] == "transition" and abs(v) > 1e-6:
        a += pump if v > 0 else -pump
    if p["part"] != "air":
        a -= drag * v
    v += a * DT
    return s + v * DT, v


def one_pass(pipe, s, v, toward, pump, drag=DRAG, stop_at_lip=False):
    """From where he is to the top of his climb on the wall he is heading `toward` (+1 right, -1 left).
    Returns (the trail of (s, v), one per step; how far along the surface the top is; his speed crossing the lip going up, or 0)."""
    trail, over_lip = [], 0.0
    for n in range(int(20.0 / DT)):
        was = s
        s, v = step(pipe, s, v, pump, drag)
        trail.append((s, v))
        if was * toward < pipe.lip <= s * toward:
            over_lip = abs(v)
            if stop_at_lip:
                break
        if s * toward > 0 and v * toward <= 0:
            break
    return trail, s * toward, over_lip


def pump_for(pipe, s, v, toward, target):
    """How hard he pumps on this pass so the climb tops out at `target` (metres along the surface): (pump, where it tops out)."""
    lo, hi = -MOST_PUMP, MOST_PUMP
    top_hi = one_pass(pipe, s, v, toward, hi)[1]
    if top_hi <= target:
        return hi, top_hi
    top_lo = one_pass(pipe, s, v, toward, lo)[1]
    if top_lo >= target:
        return lo, top_lo
    for again in range(22):
        mid = (lo + hi) / 2.0
        if one_pass(pipe, s, v, toward, mid)[1] < target:
            lo = mid
        else:
            hi = mid
    return hi, one_pass(pipe, s, v, toward, hi)[1]


def simulate(script, pipe):
    """The whole run as steps of (s, v, None or (pass, how far through its handplant)), and what each pass turned out to be."""
    passes = script.get("passes") or []
    for n, card in enumerate(passes):
        if card.get("trick") not in TRICKS:
            raise ValueError("pass %d: the trick is %r; a ride knows %s" % (n + 1, card.get("trick"), ", ".join(TRICKS)))
    s, v, toward = -(pipe.lip - KICKTURN_BELOW), 0.0, 1.0
    steps, events = [], []
    for n, card in enumerate(passes):
        asked, did, note = card["trick"], card["trick"], None
        want = float(card.get("height_m", 0.8))
        if asked == "kickturn":
            target = pipe.lip - float(card.get("below_m", KICKTURN_BELOW))
        elif asked == "handplant":
            target = pipe.lip + PLANT_SPEED ** 2 / (2.0 * G)
        else:
            target = pipe.lip + want
        pump, top = pump_for(pipe, s, v, toward, target)
        if asked != "kickturn" and top < pipe.lip + (LEAST_AIR if asked != "handplant" else 0.04):
            did, note = "kickturn", "not enough speed for %s: the climb tops out %.2f m %s the lip" % (
                "a handplant" if asked == "handplant" else "an air", abs(top - pipe.lip), "over" if top > pipe.lip else "under")
            pump, top = pump_for(pipe, s, v, toward, min(top, pipe.lip - KICKTURN_BELOW))
        elif asked in ("air", "air grab") and top < target - 0.05:
            note = "asked for %.2f m of air, had the speed for %.2f" % (want, top - pipe.lip)
        first = len(steps)
        trail, top, over = one_pass(pipe, s, v, toward, pump, stop_at_lip=(did == "handplant"))
        steps += [(a, b, None) for a, b in trail]
        event = {"pass": n + 1, "wall": "right" if toward > 0 else "left", "asked": asked, "did": did, "pump_m_s2": round(pump, 3), "first_step": first, "top_step": len(steps) - 1,
                 "top_over_lip_m": round(top - pipe.lip, 3), "speed_at_the_bottom_m_s": round(max(abs(b) for a, b in trail if abs(a) <= pipe.half_flat + 0.2) if any(abs(a) <= pipe.half_flat + 0.2 for a, b in trail) else 0.0, 2)}
        if note:
            event["note"] = note
        if card.get("pose_from"):
            event["pose_from"] = card["pose_from"]
        if did == "handplant":
            count = int(round(PLANT_S / DT))
            steps += [(toward * pipe.lip, 0.0, (n, (k + 1) / float(count))) for k in range(count)]
            event["speed_at_the_lip_m_s"] = round(over, 2)
            s, v = toward * pipe.lip, -toward * over
            event["top_step"] = len(steps) - 1
        else:
            s, v = trail[-1]
        events.append(event)
        toward = -toward
    # Done: he rides down off the wall and lets the board run out across the flat, and stands up as it stops.
    rolled = len(steps)
    for n in range(int(12.0 / DT)):
        s, v = step(pipe, s, v, 0.0, STOP_DRAG if abs(s) <= pipe.half_flat else DRAG)
        steps.append((s, v, None))
        if abs(v) < 0.7 and abs(s) < pipe.half_flat and n * DT > 1.0:
            break
    slow = int(round(0.8 / DT))
    v0 = v
    for k in range(slow):
        v = v0 * (1.0 - ease((k + 1) / float(slow)))
        s += v * DT
        steps.append((s, v, None))
    steps += [(s, 0.0, None)] * int(round(HOLD_S / DT))
    return steps, events, rolled


# ---- the board on each frame ----


def frame_on(pipe, s, psi, z):
    """The board sitting on the surface with both trucks on it: (the middle of the top of the deck, the way the nose points, the way the deck faces)."""
    h = board.TRUCK_X
    c, sn = math.cos(math.radians(psi)), math.sin(math.radians(psi))
    pf, pr, p = pipe.at(s + h * c), pipe.at(s - h * c), pipe.at(s)
    front, rear = (pf["x"], pf["y"], z + h * sn), (pr["x"], pr["y"], z - h * sn)
    nose = unit(sub(front, rear))
    n = (p["normal"][0], p["normal"][1], 0.0)
    up = unit(sub(n, times(nose, dot(n, nose))))
    return add(mix(front, rear, 0.5), times(up, board.DECK_TOP)), nose, up


def to_set(at, nose, up, point):
    """A point of the board's frame (x to the nose, y to the heel side, z up off the deck) in the set's axes."""
    side = cross(up, nose)
    return tuple(at[i] + nose[i] * point[0] + side[i] * point[1] + up[i] * point[2] for i in range(3))


def to_board(at, nose, up, point):
    side, d = cross(up, nose), sub(point, at)
    return (dot(d, nose), dot(d, side), dot(d, up))


def lay_out(script, pipe, body=None):
    """The ride, frame by frame. Returns {"frames": [...], "events": [...], ...}: see the top of this file."""
    steps, events, rolled = simulate(script, pipe)
    count = len(steps) // SUB + 1
    at_frame = lambda f: steps[min(f * SUB, len(steps) - 1)]  # noqa: E731
    z0 = float(script.get("ride_line_z", pipe.ramp.get("ride_line_z", 0.0)))
    to_frame = lambda n: min(count - 1, int(round(n / float(SUB))))  # noqa: E731

    # What each frame is: on the ramp, in the air (past the lip), or in a handplant.
    kind = []
    for f in range(count):
        s, v, plant = at_frame(f)
        kind.append("plant" if plant else "air" if abs(s) > pipe.lip else "ride")
    # Each pass's trick, as frames: the stretch it takes, and the frame it turns about.
    for event in events:
        top = to_frame(event["top_step"])
        if event["did"] == "kickturn":
            half = int(round(KICKTURN_S * FPS / 2.0))
            event["from_frame"], event["to_frame"], event["top_frame"] = max(0, top - half), min(count - 1, top + half), top
        elif event["did"] == "handplant":
            frames = [f for f in range(count) if at_frame(f)[2] and at_frame(f)[2][0] == event["pass"] - 1]
            event["from_frame"], event["to_frame"] = frames[0] - 1, frames[-1]
            event["top_frame"] = (frames[0] + frames[-1]) // 2
        else:
            a = b = top
            while a > 0 and kind[a - 1] == "air":
                a -= 1
            while b < count - 1 and kind[b + 1] == "air":
                b += 1
            event["from_frame"], event["to_frame"], event["top_frame"] = a - 1, b + 1, top
            event["air_seconds"] = round((b - a + 1) / float(FPS), 2)
    stop_frame = to_frame(rolled)

    # Which way the nose points along the surface: 0 toward the right wall, 180 toward the left. Each trick
    # turns it half way round: one way on the right wall, back the other way on the left.
    psi, turn_of = [0.0] * count, [None] * count
    now, f = 0.0, 0
    for event in events:
        a, b = event["from_frame"], event["to_frame"]
        way = 1.0 if event["wall"] == "right" else -1.0
        if event["did"] != "kickturn":  # the turn happens in the middle of an air or a handplant, not as he leaves or lands
            trim = max(1, int(round((0.28 if event["did"] == "handplant" else 0.14) * (b - a))))
            a, b = a + trim, b - trim
        while f < a:
            psi[f] = now
            f += 1
        while f <= b:
            psi[f] = now + 180.0 * way * ease((f - a) / float(max(1, b - a)))
            turn_of[f] = event
            f += 1
        now += 180.0 * way
        event["turns"] = "frontside" if way > 0 else "backside"
    while f < count:
        psi[f] = now
        f += 1

    # Along the pipe. A handplant sets the board down a little further along than it went up (the body turns
    # about the planted hand); afterwards he drifts back to his line.
    z = [z0] * count
    reach = rider.plant_reach(body) if body else ((0.03, -0.1, 1.2), 1.2)
    frames = [None] * count
    for event in events:
        if event["did"] != "handplant":
            continue
        a, b = event["from_frame"], event["to_frame"]
        side = 1.0 if event["wall"] == "right" else -1.0
        c0, nose0, up0 = frame_on(pipe, side * pipe.lip, psi[a], z[a])
        toe0 = times(cross(up0, nose0), -1.0)  # the way his toes point
        cx, cy = pipe.coping(side)
        hand = (cx - side * 0.02, cy + pipe.coping_r + PALM_THICK, c0[2] + PLANT_REACH * toe0[2])  # the middle of a palm resting on the tube
        z1 = hand[2] + PLANT_REACH * toe0[2]  # where the board comes down: the hand is on his toe side again, and he faces the other way
        c1, nose1, up1 = frame_on(pipe, side * pipe.lip, psi[b], z1)
        h0, h1 = to_board(c0, nose0, up0, hand), to_board(c1, nose1, up1, hand)
        peak = reach[0]
        # First the board carries on up past the lip until its tail is level with the hand (the hand, on the
        # coping, slides back along the board); only then does it go over. Coming back it is the nose that
        # is level with the hand, and the board slides down onto the wall nose first.
        rise0, rise1 = add(h0, (-PLANT_RISE, 0.0, 0.0)), add(h1, (PLANT_RISE, 0.0, 0.0))
        # Between there and overhead the hand goes round the shoulder, not through it: out beyond his toes on
        # the way up, across in front of his chest on the way down. (Both ways it stays in front of him: a shoulder reaches forward, not back.)
        wide0, wide1 = (rise0[0] - 0.04, rise0[1] - 0.30, 0.45 * peak[2]), (rise1[0] - 0.14, rise1[1] - 0.14, 0.5 * peak[2])
        keys = [(0.0, h0), (0.17, rise0), (0.30, wide0), (0.43, peak), (0.57, peak), (0.70, wide1), (0.83, rise1), (1.0, h1)]
        path = [keyed(keys, (f - a) / float(b - a)) for f in range(a, b + 1)]
        for again in range(4):  # evened out, so the board swings over in one movement; the two ends stay where they are
            path = [path[0]] + [mix(mix(path[i - 1], path[i + 1], 0.5), path[i], 0.5) for i in range(1, len(path) - 1)] + [path[-1]]
        event["hand_on_the_coping"] = [round(c, 4) for c in hand]
        event["moves_along_m"] = round(z1 - z[a], 3)
        spots, deep = {}, {}
        for f in range(a, b + 1):
            u = (f - a) / float(b - a)
            over = ease((u - 0.12) / 0.3) * ease((0.88 - u) / 0.3)   # how far over the board has gone
            h = path[f - a]
            deep[f] = 1.0 - ease((u - 0.2) / 0.2) * ease((0.8 - u) / 0.2)  # folded right down while the hand is beside the board
            _, nose, up = frame_on(pipe, side * pipe.lip, psi[f], 0.0)
            tilt = side * PLANT_TILT_DEG * over     # the deck's face goes from "into the pipe" round to "down"
            nose, up = about_l(nose, tilt), about_l(up, tilt)
            at = sub(hand, to_set((0.0, 0.0, 0.0), nose, up, h))  # the board is wherever puts that spot on the hand
            frames[f] = (at, nose, up)
            spots[f] = h
            z[f] = at[2]
        event["hand_in_the_board_frame"] = {str(f): [round(c, 4) for c in h] for f, h in spots.items()}
        event["folded"] = {str(f): round(d, 3) for f, d in deep.items()}
        event["hand"], event["hand_on_from_frame"], event["hand_off_at_frame"] = rider.PLANT_HAND, a + int(math.ceil(0.27 * (b - a))), b - int(math.ceil(0.27 * (b - a)))
        back = int(round(2.4 * FPS))
        for f in range(b + 1, count):
            z[f] = z0 + (z1 - z0) * (1.0 - ease((f - b) / float(back)))

    out_frames = []
    for f in range(count):
        s, v, plant = at_frame(f)
        side = 1.0 if s > 0 else -1.0
        if frames[f] is not None:
            at, nose, up = frames[f]
        else:
            at, nose, up = frame_on(pipe, s, psi[f], z[f])
            event = turn_of[f]
            if kind[f] == "air":
                event = next(e for e in events if e["did"] in ("air", "air grab") and e["from_frame"] <= f <= e["to_frame"])
                u = (f - event["from_frame"]) / float(event["to_frame"] - event["from_frame"])
                high = max(0.0, event["top_over_lip_m"])
                tilt = -side * AIR_TILT_DEG * math.sin(math.pi * u) ** 2 * min(1.0, high / 0.5)
                nose, up = about_l(nose, tilt), about_l(up, tilt)
                at = add(at, (-side * min(0.25, AIR_IN * high) * math.sin(math.pi * u), 0.0, 0.0))
            elif event is not None and event["did"] == "kickturn":
                u = (f - event["from_frame"]) / float(event["to_frame"] - event["from_frame"])
                lift = math.radians(NOSE_UP_DEG * math.sin(math.pi * u) ** 2)
                axle = sub(sub(at, times(nose, board.TRUCK_X)), times(up, board.DECK_TOP))  # under the back truck, on the surface
                nose, up = add(times(nose, math.cos(lift)), times(up, math.sin(lift))), sub(times(up, math.cos(lift)), times(nose, math.sin(lift)))
                at = add(add(axle, times(nose, board.TRUCK_X)), times(up, board.DECK_TOP))
        p = pipe.at(s)
        out_frames.append({"s": round(s, 4), "speed": round(v, 3), "kind": kind[f] if f < stop_frame else "stop" if kind[f] == "ride" else kind[f], "part": p["part"],
                           "heading_deg": round(psi[f], 2), "at": [round(c, 5) for c in at], "nose": [round(c, 6) for c in nose], "up": [round(c, 6) for c in up]})
    for event in events:
        event["first_frame"] = to_frame(event.pop("first_step"))
        event.pop("top_step")
    ride = {"format": "forge-ride/1", "name": script.get("name", "ride"), "set": script.get("set", "halfpipe"), "fps": FPS, "frames": count, "seconds": round(count / float(FPS), 2),
            "about": "Where the board is on every frame, in the set's axes (x across the pipe, y up, z along it): `at` is the middle of the top of the deck, `nose` the way the board points, `up` the way the deck faces. The rider's own motion is in the board's frame (rider.motion.json).",
            "stops_from_frame": stop_frame, "events": events, "frames_list": out_frames, "board": board.card()}
    ride["measured"] = measure(ride, pipe)
    return ride


def measure(ride, pipe):
    """From the laid-out ride alone: how far each wheel is from the surface when it should be on it, how deep anything of the board is in the ramp, and the speeds."""
    wheels = board.wheels()
    worst_back, worst_all, deepest, deepest_at = 0.0, 0.0, 0.0, None
    turning = set()
    for event in ride["events"]:
        if event["did"] == "kickturn":
            turning |= set(range(event["from_frame"], event["to_frame"] + 1))
    half = board.LONG / 2.0
    hull = wheels + [(half, 0.0, board.top_at(half)), (-half, 0.0, board.top_at(half)), (0.0, board.WIDE / 2.0, 0.0), (0.0, -board.WIDE / 2.0, 0.0),
                     (half - 0.1, 0.09, 0.0), (half - 0.1, -0.09, 0.0), (-half + 0.1, 0.09, 0.0), (-half + 0.1, -0.09, 0.0)]
    for f, row in enumerate(ride["frames_list"]):
        on = row["kind"] in ("ride", "stop")
        for k, wheel in enumerate(wheels):
            x, y, zz = to_set(row["at"], row["nose"], row["up"], wheel)
            if on:
                off = abs(pipe.where(x, y, carry_on=True)[1])
                if k >= 2:
                    worst_back = max(worst_back, off)
                if f not in turning:
                    worst_all = max(worst_all, off)
        for point in hull:
            x, y, zz = to_set(row["at"], row["nose"], row["up"], point)
            deep = pipe.inside(x, y, zz)
            if deep > deepest:
                deepest, deepest_at = deep, f
    speeds = [abs(row["speed"]) for row in ride["frames_list"]]
    return {"back_wheels_off_the_surface_cm": round(100 * worst_back, 2), "all_wheels_off_the_surface_cm_outside_kickturns": round(100 * worst_all, 2),
            "board_deepest_in_the_ramp_cm": round(100 * deepest, 2), "board_deepest_frame": deepest_at, "top_speed_m_s": round(max(speeds), 2),
            "frames_in_the_air": sum(1 for row in ride["frames_list"] if row["kind"] == "air"), "frames_in_a_handplant": sum(1 for row in ride["frames_list"] if row["kind"] == "plant")}


# ---- the rider on each frame ----


def crouch_of(ride, pipe):
    """How low he rides on each frame, 0 to 1: down into the bottom of each transition, pushing up out of it, and down again before an air."""
    rows, count = ride["frames_list"], ride["frames"]
    low = []
    airs = [e for e in ride["events"] if e["did"] in ("air", "air grab", "handplant")]
    for f, row in enumerate(rows):
        s, v = row["s"], row["speed"]
        high = moves.clamp(pipe.at(s)["y"] / pipe.height, 0.0, 1.0)
        rising = s * v > 0
        if row["part"] == "flat":
            c = 0.5
        elif rising:
            c = 0.9 - 0.8 * ease(high / 0.7)
        else:
            c = 0.3 + 0.6 * ease(1.0 - high / 0.8)
        for event in airs:  # the crouch into an air: the last third of a second before he leaves the lip
            before = event["from_frame"] - f
            if 0 <= before <= 14:
                c = max(c, 0.95 * ease(1.0 - before / 14.0))
        low.append(c)
    for again in range(3):
        low = [(low[max(0, f - 2)] + 2 * low[max(0, f - 1)] + 3 * low[f] + 2 * low[min(count - 1, f + 1)] + low[min(count - 1, f + 2)]) / 9.0 for f in range(count)]
    return low


def poses_of(ride, pipe, body):
    """The rider's pose on every frame, in the board's frame."""
    rows, count = ride["frames_list"], ride["frames"]
    low = crouch_of(ride, pipe)
    poses = [rider.stance(body, low[f]) for f in range(count)]
    pins = {"l": [None] * count, "r": [None] * count}  # a hand laid on the board: where its wrist goes and how firmly, for animate.py
    for event in ride["events"]:
        a, b = event["from_frame"], event["to_frame"]
        way = 1.0 if event["wall"] == "right" else -1.0
        if event["did"] == "kickturn":
            pose = rider.turning(body, way)
            for f in range(a, b + 1):
                poses[f] = moves.blend(poses[f], pose, bump((f - a) / float(b - a), 0.4))
        elif event["did"] in ("air", "air grab"):
            pose = rider.grab(body) if event["did"] == "air grab" else rider.spread(body)
            on, off = max(4, int(0.3 * (b - a))), max(5, int(0.3 * (b - a)))
            for f in range(max(0, a - 2), min(count, b + 4)):
                w = ease((f - (a - 2)) / float(on)) * ease(((b + 3) - f) / float(off))
                poses[f] = moves.blend(poses[f], pose, w)
                if event["did"] == "air grab" and w > 0.5:
                    pins["r"][f] = [round(c / body.leg, 5) for c in rider.wrist_for_grab(body)] + [round(ease((w - 0.5) / 0.5), 4)]
            event["held_frames"] = [a - 2 + on, b + 3 - off]
        elif event["did"] == "handplant":
            spots = event["hand_in_the_board_frame"]
            for f in range(max(0, a - 6), min(count, b + 7)):
                key = str(min(max(f, a), b))
                w = ease((f - (a - 6)) / 7.0) * ease(((b + 6) - f) / 7.0)
                poses[f] = moves.blend(poses[f], rider.plant(body, spots[key], event["folded"][key]), w)
    # Rolled to a stop: he straightens up over the last second of rolling, and raises a hand.
    stop = ride["stops_from_frame"]
    still = next((f for f in range(count - 1, stop, -1) if abs(rows[f - 1]["speed"]) >= 0.02), count - 1)
    for f in range(max(stop, still - FPS), count):
        wave = ease((f - still - 3) / 12.0)
        poses[f] = moves.blend(poses[f], rider.standing(body, wave), ease((f - (still - FPS)) / float(FPS)))
    return poses, pins


def plain(body, poses, name="ride", pins=None):
    """The poses as a plain motion, the form animate.py plays: lengths in hip heights, turns from the T-pose. Both feet are planted on every frame."""
    leg = body.leg
    hips, feet, knees = [], {"l": [], "r": []}, {"l": [], "r": []}
    names = list(moves.TRUNK) + ["upper_arm_l", "upper_arm_r", "forearm_l", "forearm_r"]
    turns = {n: [] for n in names}
    for pose in poses:
        hips.append([round(c / leg, 5) for c in pose["hips"]])
        for n in moves.TRUNK + moves.ARMS:
            turns[n].append([round(c, 5) for c in pose["turns"][n]])
        for tag, out in (("l", 1.0), ("r", -1.0)):
            turns["forearm_" + tag].append([round(c, 5) for c in moves.qmul(pose["turns"]["upper_arm_" + tag], moves.turn(moves.Z, -out * pose["elbow"][tag]))])
        ahead = moves.qturned(pose["turns"]["hips"], (0.0, -1.0, 0.0))
        facing = math.degrees(math.atan2(ahead[0], -ahead[1]))
        for tag in ("l", "r"):
            row = pose["feet"][tag]
            feet[tag].append([round(row[0] / leg, 5), round(row[1] / leg, 5), 0.0, round(row[3], 3), round(row[4], 3), 1])
            way = facing + 0.6 * ((row[4] - facing + 180.0) % 360.0 - 180.0)
            knees[tag].append([round(math.cos(math.radians(way)), 5), round(math.sin(math.radians(way)), 5), 0.0])
    out = {"name": name, "version": 1, "fps": FPS, "frames": len(poses) - 1, "loop": False, "unit": "hip_height",
           "axes": "x left (toward the board's nose), y back (the heel side), z up off the deck; the character faces -y", "travel": 0.0,
           "hips": hips, "feet": feet, "turns": turns, "knees": knees}
    if pins and any(row for rows in pins.values() for row in rows):
        out["hands"] = {tag: rows for tag, rows in pins.items() if any(rows)}
    return out


def pose_of(motion, body, frame):
    """One frame of the plain motion as a pose the Body can find the joints of (as the fight kit's schedule.pose_of)."""
    turns = {name: tuple(rows[frame]) for name, rows in motion["turns"].items()}
    elbow = {}
    for tag in ("l", "r"):
        d = sum(a * b for a, b in zip(turns["upper_arm_" + tag], turns["forearm_" + tag]))
        elbow[tag] = math.degrees(2.0 * math.acos(moves.clamp(abs(d), -1.0, 1.0)))
    return {"hips": tuple(c * body.leg for c in motion["hips"][frame]), "turns": turns, "elbow": elbow}


def build(script, body, pipe=None, shots=None, log=None):
    """A ride script laid out for one body: {"ride": ..., "motion": ...}."""
    pipe = pipe or Pipe.of_set(script.get("set", "halfpipe"))
    ride = lay_out(script, pipe, body)
    poses, pins = poses_of(ride, pipe, body)
    motion = plain(body, poses, script.get("name", "ride"), pins)
    import video_pose

    for event in ride["events"]:
        if event.get("pose_from"):
            event["pose_from_result"] = video_pose.lay_on(motion, body, event, shots=shots)
            if log:
                log("pass %d: %s" % (event["pass"], event["pose_from_result"]["said"]))
    # Where the hands are, as the motion has them, for whoever checks a grab or a handplant on the baked character.
    for event in ride["events"]:
        if event["did"] == "air grab" and "held_frames" in event:
            mid = sum(event["held_frames"]) // 2
            hand = body.joints(pose_of(motion, body, mid))["fist_r"]
            event["grab"] = {"hand": "r", "frame": mid, "spot": [round(c, 4) for c in rider.edge_spot()], "hand_from_the_edge_cm": round(100 * moves.length(sub(hand, rider.edge_spot())), 1)}
        if event["did"] == "handplant":
            worst = 0.0
            for f in range(event["hand_on_from_frame"], event["hand_off_at_frame"] + 1):  # while the hand is on the coping
                hand = body.joints(pose_of(motion, body, f))["fist_" + event["hand"]]
                worst = max(worst, moves.length(sub(hand, event["hand_in_the_board_frame"][str(f)])))
            event["hand_from_its_spot_cm"] = round(100 * worst, 1)
    return {"ride": ride, "motion": motion}


def said(ride):
    """The run in a few lines, for a person."""
    lines = ["%d frames (%.1f s), top speed %.1f m/s" % (ride["frames"], ride["seconds"], ride["measured"]["top_speed_m_s"])]
    for e in ride["events"]:
        what = e["did"] if e["did"] == e["asked"] else "%s (asked: %s)" % (e["did"], e["asked"])
        high = "%.2f m over the lip, %.2f s in the air" % (e["top_over_lip_m"], e.get("air_seconds", 0.0)) if e["did"] in ("air", "air grab") else \
               "stalls %.2f m under the lip" % -e["top_over_lip_m"] if e["did"] == "kickturn" else "over the coping"
        lines.append("pass %d, %s wall, frames %d to %d: %s, %s; pumping %+.2f m/s2%s" % (e["pass"], e["wall"], e["from_frame"], e["to_frame"], what, high, e["pump_m_s2"],
                                                                                         "; " + e["note"] if e.get("note") else ""))
    return lines


def main():
    script_file, body_file, out = sys.argv[1:4]
    with open(script_file) as f:
        script = json.load(f)
    with open(body_file) as f:
        card = json.load(f)
    if "joints" not in card:  # a file of several bodies (the fight kit's test_bodies.json): the tall one
        card = card.get("lanky") or next(v for v in card.values() if isinstance(v, dict))
    made = build(script, moves.Body(card), log=lambda line: print("RIDE " + line))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "rider.motion.json"), "w") as f:
        json.dump(made["motion"], f)
    with open(os.path.join(out, "ride.json"), "w") as f:
        json.dump(made["ride"], f)
    for line in said(made["ride"]):
        print("RIDE " + line)
    print("RIDE measured " + json.dumps(made["ride"]["measured"]))


if __name__ == "__main__":
    main()
