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
     our board's bolts: the legs are solved to them as always, from wherever
     the clip put the hips.

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
SIDEWAYS = 0.22      # and this far from over the board, at most


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


def lay_on(motion, body, event, shots=None, sk=None):
    """Puts the pose a pass's pose_from names onto the rider's plain motion, over that pass's trick. Changes `motion`; returns what it did, in words too."""
    card = event["pose_from"]
    try:
        source, first, last, label = stretch_of(card, shots)
    except NotThere as gone:
        return {"used": False, "said": "pose_from skipped, his own pose is used: %s" % gone}
    a, b = event["from_frame"], event["to_frame"]
    count = b - a + 1
    rows = retimed(on_his_board(source, first, last, sk), count)
    feet = rider.feet_of(body)
    middle = (0.5 * (feet["l"][0] + feet["r"][0]) / body.leg, 0.5 * (feet["l"][1] + feet["r"][1]) / body.leg)
    ramp = min(EASE_FRAMES, max(2, count // 3))
    for i, row in enumerate(rows):
        f = a + i
        w = moves.clamp(min(i, count - 1 - i) / float(ramp), 0.0, 1.0)
        w = w * w * (3.0 - 2.0 * w)
        if w <= 0.0:
            continue  # the first and last frames are his own pose, untouched
        for name in TAKEN:
            was = tuple(motion["turns"][name][f])
            now = moves.qslerp(was, row["turns"][name], w)
            motion["turns"][name][f] = [round(c, 5) for c in now]
        # The hips: where the clip has them from the feet, kept to where our legs can follow.
        want = (moves.clamp(row["hips"][0], -SIDEWAYS, SIDEWAYS) + middle[0], moves.clamp(row["hips"][1], -SIDEWAYS, SIDEWAYS) + middle[1],
                moves.clamp(row["hips"][2] - row["standing"], LOWEST, HIGHEST))
        motion["hips"][f] = [round(c, 5) for c in mix(tuple(motion["hips"][f]), want, w)]
        for rows in (motion.get("hands") or {}).values():  # a hand our own pose had on the board is let go: the clip's arms are used as they are
            if rows[f] is not None:
                rows[f] = rows[f][:3] + [round(rows[f][3] * (1.0 - w), 4)] if w < 1.0 else None
    return {"used": True, "source": label, "source_frames": [first, last], "frames": [a, b], "played_at": round((last - first) / float(max(1, count - 1)), 2),
            "said": "the body's pose from %s (%d frames of it, played over our %d: %.2f times its own speed); the board, the feet and the path are ours" % (
                label, last - first + 1, count, (last - first) / float(max(1, count - 1)))}
