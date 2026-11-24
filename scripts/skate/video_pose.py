"""A trick's pose taken from a video: the body from the clip, laid on the board our ride already has.

A motion read off a video (`just video`, NVIDIA's GEM-X) knows a floor: it
cleans feet up against flat ground, and where the skater is in the world is
a guess from a moving camera. A ramp would fight all of that. So a ride
never takes its path from a clip. The board's path, its turning and the
rider's place on it are ride.py's; what a clip can give is what the body
does during a trick. A pass in a ride script says so:

    {"trick": "air", "pose_from": {"video": "halfpipe", "shot": 4, "from_s": 22.0, "to_s": 23.6}}

    video     the clip's name: the motion is shots/video-<name>/motion.json,
              as `just video <name>` leaves it
    shot      which of the clip's shots, numbered as the clip's page numbers
              them (Shot 1, Shot 2, ...)
    from_s, to_s   the stretch to use, in seconds on the clip's own clock
              (what a player shows). It has to lie inside that shot.

or, for any motion in our SOMA form that did not come from a video (a piece
Kimodo made, say):

    "pose_from": {"motion": "shots/grass-workout/cache/<name>.json", "from_s": 0.4, "to_s": 1.6}

What is taken, and how:

  1. On every frame of the stretch the clip's skater is given a board of his
     own: a frame laid through his two feet, x from his right foot to his
     left, z the way his soles face. Upside down over a coping, that frame
     is upside down with him, which is the point: nothing here looks at
     which way the clip thinks is up.
  2. In that frame we read how every part of him is turned (hips, spine,
     chest, neck, head, both arms) and where his hips are from his feet, in
     hip heights, so it fits a body of any size.
  3. That is retimed to the length of our trick and eased on over the first
     frames and off over the last, in place of our own pose. Our feet stay on
     our board's bolts: the legs are solved to them as always, and the hips
     are kept where both legs can hold their feet flat on the deck.
  4. A hand the trick itself puts somewhere stays ours. In a grab the back
     hand is solved onto the board's edge on top of the borrowed pose, and in
     a handplant the planting hand onto the coping; if the clip's skater is
     stood too tall for the hand to get there, the trunk comes part of the
     way back to our own pose, by the least that lets it. The clip gives the
     rest: the trunk, how far the legs fold, the free arm.

Time. Our airs are usually shorter than a real skater's, and a stretch
squeezed into a short air plays fast. So ride.py sizes a borrowed air to the
clip: as high as it takes to play the stretch at no more than AIM_SPEED
times its own speed, if his speed and the ramp allow; what it did is in the
result ("played_at"), and it says so when it had to go faster.

The root is not taken: not where he is, not which way the board points.

If the clip's motion is not there yet (the video worker has not run), the
pass keeps its own pose and the result says so; nothing fails.

Plain Python: no Blender, no numpy.
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
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
import moves  # noqa: E402
import rider  # noqa: E402
from moves import add, cross, dot, mix, sub, times, unit  # noqa: E402

FPS = 30
TAKEN = ("hips", "spine", "chest", "neck", "head", "upper_arm_l", "upper_arm_r", "forearm_l", "forearm_r")
EASE_FRAMES = 6      # the clip's pose comes on, and goes off, over this many frames
SMOOTH = 2           # the clip's feet shake: his board's frame is evened out over this many frames each side
LOWEST, HIGHEST = -0.58, 0.02   # the hips, in hip heights from standing: as low as a deep tuck, no higher than standing
SIDEWAYS = 0.12      # along the board, this far from over the middle of the feet, at most
FORWARD, BACK = -0.08, 0.20   # and across it: a little over the toes, further over the heels (where a crouch puts them)
HIPS_TURN = 28.0     # degrees the hips may turn from our own pose: the legs under them still have to stand on the board
KNEE_FOLDS = 135.0   # degrees a knee is asked to fold, at most (its limit is 150; the ankle needs the rest)
LEAD_FRAMES = 4      # an air's pose is laid on from this many frames before he leaves the lip to this many after he lands
GIVE_FRAMES = 6      # a trunk that comes back toward our own pose for a hand's sake does it over this many frames
AIM_SPEED = 1.3      # a clip's stretch is played at most this many times its own speed, where the ride can give it the time


class NotThere(Exception):
    """The motion a pose_from names has not been made yet."""


def read(path):
    with open(path) as f:
        return json.load(f)


def stretch_of(card, shots=None):
    """The motion a pose_from names and the frames of it to use: (motion, first, last, what it is, in words)."""
    shots = shots or os.path.join(REPO, "shots")
    if "from_s" not in card or "to_s" not in card or float(card["to_s"]) <= float(card["from_s"]):
        raise ValueError("pose_from needs from_s and to_s, in seconds, the second after the first")
    if card.get("motion"):
        path = card["motion"] if os.path.isabs(card["motion"]) else os.path.join(REPO, card["motion"])
        if not os.path.exists(path):
            raise NotThere("there is no %s" % card["motion"])
        motion = read(path)
        first, last = int(round(float(card["from_s"]) * FPS)), int(round(float(card["to_s"]) * FPS))
        count = len(motion["root"])
        if first < 0 or last > count - 1:
            raise ValueError("pose_from asks for %.2f to %.2f s of %s, which is %.2f s long" % (card["from_s"], card["to_s"], card["motion"], (count - 1) / float(FPS)))
        return motion, first, last, "%s, %.2f to %.2f s" % (os.path.basename(card["motion"]), card["from_s"], card["to_s"])
    if not card.get("video"):
        raise ValueError("pose_from names a video (and a shot) or a motion file")
    folder = os.path.join(shots, "video-" + card["video"])
    if not os.path.exists(os.path.join(folder, "motion.json")) or not os.path.exists(os.path.join(folder, "source.json")):
        raise NotThere("the clip \"%s\" has no motion yet (%s is not there): run `just video %s` once the video worker is up" % (card["video"], os.path.relpath(folder, REPO), card["video"]))
    source = read(os.path.join(folder, "source.json"))
    number = int(card.get("shot", 0))
    piece = next((p for p in source.get("pieces") or [] if p.get("shot") == number - 1), None)
    if piece is None:
        have = ", ".join(str(p["shot"] + 1) for p in source.get("pieces") or [])
        raise ValueError("the clip \"%s\" has no motion for shot %s (it has shots %s: a skipped shot has none)" % (card["video"], card.get("shot"), have or "none"))
    a, b = int(round(float(card["from_s"]) * FPS)), int(round(float(card["to_s"]) * FPS))
    if a < piece["clip_first_frame"] or b > piece["clip_last_frame"]:
        raise ValueError("shot %d of \"%s\" runs from %.2f to %.2f s of the clip; pose_from asks for %.2f to %.2f" % (
            number, card["video"], piece["clip_first_frame"] / float(FPS), piece["clip_last_frame"] / float(FPS), card["from_s"], card["to_s"]))
    first = piece["first_frame"] + (a - piece["clip_first_frame"])
    return read(os.path.join(folder, "motion.json")), first, first + (b - a), "the clip \"%s\", shot %d, %.2f to %.2f s" % (card["video"], number, card["from_s"], card["to_s"])


def on_his_board(motion, first, last, sk=None):
    """A stretch of a SOMA motion, each frame read in a frame laid through the body's own two feet.
    Returns [{"hips": (x, y, z) from the middle of the feet in hip heights, "turns": {bone: [w, x, y, z]}}]."""
    import soma_to_plain
    from soma import Skeleton

    sk = sk or Skeleton.load()
    piece = {"fps": motion.get("fps", FPS), "joints": motion["joints"], "root": motion["root"][first:last + 1], "rotations": motion["rotations"][first:last + 1],
             "contacts": (motion.get("contacts") or [[0.0] * 4] * len(motion["root"]))[first:last + 1]}
    plain, _ = soma_to_plain.convert(piece, sk, "pose", plant=False)
    count = len(plain["hips"])
    unit_m = sk.rest_world_pos[sk.index["LeftLeg"]][1]
    toe = sk.rest_world_pos[sk.index["LeftToeBase"]][1] / unit_m                # the ball of a foot above the floor, standing
    standing = sk.rest_world_pos[0][1] / unit_m - toe                          # the hips above the balls of the feet, standing, in hip heights
    across, soles, middles, hips = [], [], [], []
    for f in range(count):
        left, right = tuple(plain["feet"]["l"][f][:3]), tuple(plain["feet"]["r"][f][:3])  # the balls of the feet (their height is from where they rest)
        across.append(sub(left, right))
        soles.append(add(moves.qturned(tuple(plain["turns"]["foot_l"][f]), moves.Z), moves.qturned(tuple(plain["turns"]["foot_r"][f]), moves.Z)))
        middles.append(mix(left, right, 0.5))
        hips.append(add(tuple(plain["hips"][f]), (0.0, 0.0, standing)))  # from the same level as the feet's heights
    out = []
    for f in range(count):
        near = range(max(0, f - SMOOTH), min(count, f + SMOOTH + 1))
        x = unit(tuple(sum(across[g][i] for g in near) for i in range(3)))
        n = tuple(sum(soles[g][i] for g in near) for i in range(3))
        z = sub(n, times(x, dot(n, x)))
        if moves.length(z) < 0.3:  # the soles say nothing square to the feet: the way to the hips will do
            n = sub(hips[f], middles[f])
            z = sub(n, times(x, dot(n, x)))
        z = unit(z)
        frame = moves.q_of_axes(x, cross(z, x), z)
        back = moves.qback(frame)
        turns = {name: moves.qmul(back, tuple(plain["turns"][name][f])) for name in TAKEN}
        out.append({"hips": moves.qturned(back, sub(hips[f], middles[f])), "turns": turns, "standing": standing})
    return out


def retimed(rows, count):
    """`count` frames spread evenly over the stretch."""
    out = []
    for i in range(count):
        t = i * (len(rows) - 1) / float(max(1, count - 1))
        a = min(int(t), len(rows) - 1)
        b, part = min(a + 1, len(rows) - 1), t - int(t)
        out.append({"hips": mix(rows[a]["hips"], rows[b]["hips"], part), "standing": rows[a]["standing"],
                    "turns": {name: moves.qslerp(rows[a]["turns"][name], rows[b]["turns"][name], part) for name in TAKEN}})
    return out


def pose_at(motion, body, f):
    """One frame of the plain motion as a pose the Body can find the joints of."""
    turns = {name: tuple(rows[f]) for name, rows in motion["turns"].items()}
    elbow = {}
    for tag in ("l", "r"):
        d = sum(p * q for p, q in zip(turns["upper_arm_" + tag], turns["forearm_" + tag]))
        elbow[tag] = math.degrees(2.0 * math.acos(moves.clamp(abs(d), -1.0, 1.0)))
    return {"hips": tuple(c * body.leg for c in motion["hips"][f]), "turns": turns, "elbow": elbow}


def hips_the_legs_can_follow(body, hips, turn, feet):
    """The hips' height (metres from standing) brought to where both legs can hold their feet flat on the bolts:
    not so low that a knee would have to fold past what it can (the foot would lift off the deck), not so
    high that a leg would have to be longer than it is."""
    j, m = body.j, body.card["measure"]
    longest = 0.98 * (m["thigh"] + m["shin"])
    fold = math.radians(180.0 - KNEE_FOLDS)
    shortest = math.sqrt(m["thigh"] ** 2 + m["shin"] ** 2 - 2.0 * m["thigh"] * m["shin"] * math.cos(fold))
    x, y, z = hips
    for again in range(80):
        low = high = False
        for tag in ("l", "r"):
            row = feet[tag]
            sole = moves.about_z(sub(j["toe_" + tag], j["foot_" + tag]), row[4])
            ankle = sub((row[0], row[1], j["toe_" + tag][2]), sole)
            hip = add((x, y, j["hips"][2] + z), moves.qturned(turn, sub(j["thigh_" + tag], j["hips"])))
            far = moves.length(sub(ankle, hip))
            low, high = low or far < shortest, high or far > longest
        if low and not high:
            z += 0.008
        elif high and not low:
            z -= 0.008
        else:
            break
    return (x, y, z)


def hand_onto(body, motion, own, frames, tag, spot_of, weight_of, must_reach=lambda f: True):
    """A hand of ours put on its spot on top of a borrowed pose: the arm is solved to the spot from wherever the
    borrowed shoulder is. Where the spot is out of that shoulder's reach (the clip's skater is stood taller than
    a hand on the deck allows), the hips, spine and chest come part of the way back to our own pose for the
    trick, by the least that brings the hand there on that frame (evened out over the frames round it); the
    head and the other arm stay the clip's. On frames where `must_reach` says no, the arm only points at the
    spot as far as it goes. Returns {"trunk_given_back": the most, 0 to 1, "short_cm": how far short at worst}."""
    out = 1.0 if tag == "l" else -1.0
    reach = 0.97 * (body.arm + body.fist)
    trunk = ("hips", "spine", "chest")

    def with_back(f, t):
        pose = pose_at(motion, body, f)
        mine = own[f]
        for name in trunk:
            pose["turns"][name] = moves.qslerp(pose["turns"][name], tuple(mine["turns"][name]), t)
        pose["hips"] = mix(pose["hips"], tuple(c * body.leg for c in mine["hips"]), t)
        return pose

    frames = list(frames)
    needs = []
    for f in frames:
        t = 0.0
        if weight_of(f) > 0.0 and must_reach(f):
            for t in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
                shoulder = body.joints(with_back(f, t))["shoulder_" + tag]
                if moves.length(sub(spot_of(f), shoulder)) <= reach:
                    break
        needs.append(t)
    evened = []
    for i in range(len(needs)):  # never less than a frame needs, and coming on and going off over a few frames
        best = needs[i]
        for k in range(1, GIVE_FRAMES + 1):
            share = 1.0 - k / (GIVE_FRAMES + 1.0)
            share = share * share * (3.0 - 2.0 * share)
            for j in (i - k, i + k):
                if 0 <= j < len(needs):
                    best = max(best, share * needs[j])
        evened.append(best)
    need = max(evened + [0.0])
    short = 0.0
    for f, give in zip(frames, evened):
        w = weight_of(f)
        if w <= 0.0:
            continue
        pose = with_back(f, give * w)
        for name in trunk:
            motion["turns"][name][f] = [round(c, 5) for c in pose["turns"][name]]
        motion["hips"][f] = [round(c / body.leg, 5) for c in pose["hips"]]
        shoulder = body.joints(pose)["shoulder_" + tag]
        spot = spot_of(f)
        fore = unit(sub(spot, shoulder))
        pole = moves.qturned(pose["turns"]["chest"], (out * 0.75, 0.45, 0.25))  # the elbow out to the side and a little back, as the chest sees it
        for again in range(4):
            q, bend, fore, miss = moves.arm_to(body, tag, shoulder, sub(spot, times(fore, body.fist)), pole)
        lower = moves.qmul(q, moves.turn(moves.Z, -out * bend))
        motion["turns"]["upper_arm_" + tag][f] = [round(c, 5) for c in moves.qslerp(tuple(motion["turns"]["upper_arm_" + tag][f]), q, w)]
        motion["turns"]["forearm_" + tag][f] = [round(c, 5) for c in moves.qslerp(tuple(motion["turns"]["forearm_" + tag][f]), lower, w)]
        if w >= 0.99 and must_reach(f):
            short = max(short, miss)
    return {"hand": tag, "trunk_given_back": round(need, 2), "short_cm": round(100 * short, 1)}


def lay_on(motion, body, event, shots=None, sk=None):
    """Puts the pose a pass's pose_from names onto the rider's plain motion, over that pass's trick. Changes `motion`; returns what it did, in words too."""
    card = event["pose_from"]
    try:
        source, first, last, label = stretch_of(card, shots)
    except NotThere as gone:
        return {"used": False, "said": "pose_from skipped, his own pose is used: %s" % gone}
    total = len(motion["hips"])
    lead = LEAD_FRAMES if event["did"] in ("air", "air grab") else 0  # an air's pose starts in the crouch before the lip and ends after the landing
    a, b = max(0, event["from_frame"] - lead), min(total - 1, event["to_frame"] + lead)
    count = b - a + 1
    rows = retimed(on_his_board(source, first, last, sk), count)
    own = {f: {"hips": list(motion["hips"][f]), "turns": {name: list(motion["turns"][name][f]) for name in TAKEN}} for f in range(a, b + 1)}
    feet = rider.feet_of(body)
    middle = (0.5 * (feet["l"][0] + feet["r"][0]) / body.leg, 0.5 * (feet["l"][1] + feet["r"][1]) / body.leg)
    ramp = min(EASE_FRAMES, max(2, count // 3))
    weights = {}
    for i, row in enumerate(rows):
        f = a + i
        w = moves.clamp(min(i, count - 1 - i) / float(ramp), 0.0, 1.0)
        w = weights[f] = w * w * (3.0 - 2.0 * w)
        if w <= 0.0:
            continue  # the first and last frames are his own pose, untouched
        # The hips turn no further from our own pose than our legs can follow with both feet flat on the deck.
        tilt = math.degrees(2.0 * math.acos(moves.clamp(abs(sum(p * q for p, q in zip(own[f]["turns"]["hips"], row["turns"]["hips"]))), 0.0, 1.0)))
        hip_turn = moves.qslerp(tuple(own[f]["turns"]["hips"]), row["turns"]["hips"], w * min(1.0, HIPS_TURN / max(tilt, 1e-6)))
        for name in TAKEN:
            now = hip_turn if name == "hips" else moves.qslerp(tuple(own[f]["turns"][name]), row["turns"][name], w)
            motion["turns"][name][f] = [round(c, 5) for c in now]
        # The hips: where the clip has them from the feet, kept to where our legs can follow.
        want = (moves.clamp(row["hips"][0], -SIDEWAYS, SIDEWAYS) + middle[0], moves.clamp(row["hips"][1], FORWARD, BACK) + middle[1],
                moves.clamp(row["hips"][2] - row["standing"], LOWEST, HIGHEST))
        at = mix(tuple(own[f]["hips"]), want, w)
        at = hips_the_legs_can_follow(body, tuple(c * body.leg for c in at), hip_turn, feet)
        motion["hips"][f] = [round(c / body.leg, 5) for c in at]
    result = {"used": True, "source": label, "source_frames": [first, last], "frames": [a, b], "played_at": round((last - first) / float(max(1, count - 1)), 2)}
    # A hand the trick puts somewhere stays ours: the clip gives the trunk, the legs' fold and the free arm.
    hands = motion.get("hands") or {}
    if event["did"] == "air grab":
        wrist = hands.get("r") or [None] * total
        spot = rider.edge_spot()
        result["hand"] = hand_onto(body, motion, own, range(a, b + 1), "r", lambda f: spot, lambda f: (wrist[f][3] if wrist[f] else 0.0))
    elif event["did"] == "handplant":
        spots, on, off = event["hand_in_the_board_frame"], event["from_frame"], event["to_frame"]

        def held(f):
            u = (f - on) / float(off - on)
            return (1.0 - moves.clamp(abs(u - 0.5) - 0.38, 0.0, 0.12) / 0.12) if 0.0 <= u <= 1.0 else 0.0

        top = max(spot[2] for spot in spots.values())
        # Beside the board the hand has to get to the coping, whatever that takes. With the board over his head it only has
        # to point there: the board is carried by where the hand really is (apply_ride.py), so the clip's own shape is kept.
        result["hand"] = hand_onto(body, motion, own, range(a, b + 1), event["hand"], lambda f: tuple(spots[str(min(max(f, on), off))]), held,
                                   must_reach=lambda f: spots[str(min(max(f, on), off))][2] < 0.35 * top)
    else:
        for pinned in hands.values():  # a hand our own pose had on the board is let go: the clip's arms are used as they are
            for f in range(a, b + 1):
                if pinned[f] is not None and weights.get(f, 0.0) > 0.0:
                    pinned[f] = pinned[f][:3] + [round(pinned[f][3] * (1.0 - weights[f]), 4)] if weights[f] < 1.0 else None
    speed = (last - first) / float(max(1, count - 1))
    result["said"] = "the body's pose from %s (%d frames of it, played over our %d: %.2f times its own speed%s); the board, the feet and the path are ours%s" % (
        label, last - first + 1, count, speed, ", faster than the %.1f we aim for" % AIM_SPEED if speed > AIM_SPEED + 0.05 else "",
        "; the %s hand is ours too, on its spot%s" % ("right" if result["hand"]["hand"] == "r" else "left",
                                                     ", with the hips and chest up to %d%% of the way back to our own pose to reach it" % round(100 * result["hand"]["trunk_given_back"]) if result["hand"]["trunk_given_back"] else "") if result.get("hand") else "")
    return result
