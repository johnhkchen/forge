"""A shot as pieces from different makers, joined into one motion.

    python3 scripts/motion/timeline.py <shot folder>

A shot list's beats can each get their motion from somewhere else:

    poses   our own poses, with MotionBricks filling in between them
    text    a sentence, made into motion by Kimodo, steered along the shot's
            path and, where the beat says so, through one of our poses or
            with a hand or foot on a spot
    video   a stretch of a clip's motion (`just video`), read off a real
            person by GEM-X; the shot says where it stands, the video how it
            moves (scripts/video/beat.py). It is on hand already, so it asks
            no worker for anything

Each beat is made on its own, as a piece. Where two pieces meet is a seam, and
every seam is made the same way: MotionBricks is shown the four frames that
end piece A and the frames piece B begins with, and fills in the stretch
between them (a tween).

How much a tween replaces. It has to cover enough for the body to change what
it is doing, and MotionBricks' shortest motion is 17 frames. So a tween takes
the place of the last frames of A and the first frames of B:

    from the end of A      4 frames if A is "poses" (its last pose was chosen
                           on purpose; keep nearly all of it)
                           12 frames if A is "text" (a sentence's motion has
                           no exact last frame worth keeping) or "video" (which
                           brings that many frames of the clip past the stretch
                           asked for, so the stretch itself stays whole)
    from the start of B    13 frames (a text piece spends its start getting
                           going; a later poses piece starts by holding still
                           in its first pose, which is what a tween should
                           arrive in)

That makes 17 frames between two poses pieces and 25 after a text piece. A
beat can say otherwise with `join_out_frames` and `join_in_frames` (the vault
keeps every frame up to the wall: 0). If the two do not add up to a length
MotionBricks makes (17, 21, 25 ... 57), B gives up a few more.

Re-anchoring. A tween ends close to where B begins, not exactly on it. So B is
picked up whole and set down where the tween ended: slid over the ground and
turned about its hips until its first kept frame stands where the tween's last
frame stands, facing the same way. Nothing inside B changes, so its feet stay
planted where they were planted. What little is left (a knee a few degrees
off) is eased out over B's next 6 frames. A piece that was moved carries the
tween after it along, so misses add up down the shot; join.json says how far
each tween missed and how far each piece ended up from its plan.

Caching. Every request to a worker is kept under the sha256 of its content
(<shot>/cache/<hash>.request.json), and so is its answer (<hash>.json). A
request that already has an answer is never sent again. A seam's request is
made from the two pieces as they were planned, before any re-anchoring, so it
depends on those two pieces and nothing else: change one beat, and only that
piece and the seam at each of its ends are made again.

This file does the planning and the joining. It never calls a worker: it
writes <shot>/todo.json, the requests that still need an answer, and whoever
runs it (`baml run shoot`) sends those and runs it again. Three passes: the
pieces, the seams, the join. When todo.json is empty, motion.json is written.

Plain Python: no Blender, no numpy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from soma import Skeleton, heading_of, qconj, qmul, qnorm, qrot, qslerp, yaw  # noqa: E402

FPS = 30
TAKE_FROM_END = {"poses": 4, "text": 12, "video": 12}  # frames of its end a seam may replace, by where the piece comes from
TAKE_FROM_START = 13  # frames of its start
SHORTEST_TWEEN, LONGEST_TWEEN = 17, 57  # what MotionBricks makes: 4 * tokens - 7 frames, tokens 6..16
EASE_FRAMES = 6  # frames over which what is left of a seam's mismatch is eased out of B
CONTACT_ORDER = ["left_heel", "left_toe", "right_heel", "right_toe"]
SOURCES = ("poses", "text", "video")
MADE_BY = {"poses": "our poses, MotionBricks between them", "text": "Kimodo, from a sentence", "video": "GEM-X, from a video"}


def digest(request: dict) -> str:
    """A request's name in the cache: the sha256 of its content."""
    return hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]


def tween_length(from_end: int, from_start: int) -> tuple:
    """(frames taken from A's end, frames taken from B's start), grown until MotionBricks can make that many."""
    if from_end < 0 or from_start < 1:
        raise ValueError("a seam takes 0 or more frames from the end of one piece and at least 1 from the start of the next")
    total = max(from_end + from_start, SHORTEST_TWEEN)
    while (total + 7) % 4:
        total += 1
    if total > LONGEST_TWEEN:
        raise ValueError(f"a seam of {total} frames is longer than MotionBricks makes ({LONGEST_TWEEN})")
    return from_end, total - from_end


# ---- how fast along the path ---------------------------------------------------


def pace(from_m: float, to_m: float, speed_in: float, speed_out: float, seconds: float):
    """Metres along the route at a time into the beat: starts at one speed, ends at another, smoothly.
    Before the beat it runs on at the first speed, after it at the last."""

    def at(t: float) -> float:
        if t <= 0.0:
            return from_m + speed_in * t
        if t >= seconds:
            return to_m + speed_out * (t - seconds)
        u = t / seconds
        return (
            (2 * u**3 - 3 * u**2 + 1) * from_m
            + (u**3 - 2 * u**2 + u) * seconds * speed_in
            + (-2 * u**3 + 3 * u**2) * to_m
            + (u**3 - u**2) * seconds * speed_out
        )

    return at


# ---- moving a motion about -----------------------------------------------------


def turn_xz(x: float, z: float, degrees: float) -> tuple:
    """A ground point turned about the origin; a positive heading turns +Z toward +X."""
    h = math.radians(degrees)
    return x * math.cos(h) + z * math.sin(h), -x * math.sin(h) + z * math.cos(h)


def moved(motion: dict, heading: float, x: float, z: float) -> dict:
    """The same motion turned about the origin by a heading, then slid by (x, z). Nothing inside it changes."""
    turn = yaw(heading)
    hips = motion["joints"].index("Hips")
    out = dict(motion)
    out["root"], out["rotations"] = [], []
    for root, row in zip(motion["root"], motion["rotations"]):
        rx, rz = turn_xz(root[0], root[2], heading)
        out["root"].append([round(rx + x, 5), root[1], round(rz + z, 5)])
        row = list(row)
        row[4 * hips : 4 * hips + 4] = [round(c, 6) for c in qmul(turn, tuple(row[4 * hips : 4 * hips + 4]))]
        out["rotations"].append(row)
    return out


def cut(motion: dict, first: int, last: int) -> dict:
    """Frames first..last of a motion, both included."""
    out = dict(motion)
    for key in ("root", "rotations", "contacts"):
        out[key] = motion[key][first : last + 1]
    out.pop("positions", None)
    return out


def facing(sk: Skeleton, motion: dict, frame: int) -> float:
    """Which way the pelvis faces on a frame, in degrees."""
    hips = motion["joints"].index("Hips")
    q = tuple(motion["rotations"][frame][4 * hips : 4 * hips + 4])
    return heading_of(qmul(q, qconj(sk.rest_rot[0])))


def pose_of(motion: dict, frame: int) -> dict:
    """One frame as a POSE of the worker's input."""
    row = motion["rotations"][frame]
    return {"root": motion["root"][frame], "rotations": {name: row[4 * j : 4 * j + 4] for j, name in enumerate(motion["joints"])}}


def held(sk: Skeleton, placed_pose: dict, frames: int) -> dict:
    """A placed pose, standing still for a number of frames, as a motion."""
    turn = yaw(placed_pose["heading"])
    rotations = sk.rotation_list(placed_pose["rotations"])
    rotations[0] = qmul(turn, rotations[0])
    root = qrot(turn, tuple(placed_pose["root"]))
    at = placed_pose["at"]
    row = [round(c, 6) for q in rotations for c in q]
    spot = [round(at[0] + root[0], 5), round(at[1] + root[1], 5), round(at[2] + root[2], 5)]
    return {
        "format": "forge-soma-motion/1",
        "fps": FPS,
        "joints": list(sk.joints),
        "root": [list(spot) for _ in range(frames)],
        "rotations": [list(row) for _ in range(frames)],
        "contact_order": list(CONTACT_ORDER),
        "contacts": [[1.0, 1.0, 1.0, 1.0] for _ in range(frames)],
    }


def by_our_joints(sk: Skeleton, motion: dict) -> dict:
    """A worker's answer with its joints in the skeleton's order and nothing we do not join on."""
    if motion.get("format") != "forge-soma-motion/1":
        raise ValueError(f"not a motion in the repo's format: {motion.get('format')!r}")
    order = [motion["joints"].index(name) for name in sk.joints]
    return {
        "format": "forge-soma-motion/1",
        "fps": motion.get("fps", FPS),
        "joints": list(sk.joints),
        "root": [list(r) for r in motion["root"]],
        "rotations": [[c for j in order for c in row[4 * j : 4 * j + 4]] for row in motion["rotations"]],
        "contact_order": list(CONTACT_ORDER),
        "contacts": [list(c) for c in motion["contacts"]],
    }


# ---- laying a shot out as pieces -----------------------------------------------


def lay_out(shot: dict, library: dict, sk: Skeleton, set_card: dict = None, made: dict = None) -> tuple:
    """A shot list as pieces and seams. Returns (plan.json's content, {hash: request} for the pieces).
    A video beat's motion is on hand already: it is put in `made`, {hash: motion}, for the caller to keep in the cache."""
    from plan_shot import FPS as PLAN_FPS, Stage, move_frames, set_blocks, stand

    assert PLAN_FPS == FPS
    stage = Stage(shot, library, sk)
    path = stage.path
    start = dict(at_m=0.0, side_m=0.0, facing_deg=float(shot.get("start_facing_deg", 0.0)))
    sx, sz, _, sheading = stage.placed(start)
    requests, marks, beats, pieces = {}, [], [], []
    frame, end_m = 0, 0.0

    def seam_takes(a: dict, b: dict) -> tuple:
        """(frames of beat A's end, frames of beat B's start) the tween between them takes the place of."""
        if a.get("source", "poses") not in SOURCES:
            return 0, 0  # refused below, by name
        from_end = int(a["join_out_frames"]) if a.get("join_out_frames") is not None else TAKE_FROM_END[a.get("source", "poses")]
        from_start = int(b["join_in_frames"]) if b.get("join_in_frames") is not None else TAKE_FROM_START
        return tween_length(from_end, from_start)

    for number, beat in enumerate(shot["beats"]):
        source = beat.get("source", "poses")
        first = frame
        piece = {"name": beat["name"], "source": source, "first_frame": first}
        if source == "poses":
            moves = beat.get("moves") or []
            if not moves:
                raise ValueError(f"{beat['name']}: a poses beat needs at least one move")
            targets = []
            for n, move in enumerate(moves):
                name = f"{beat['name']} {n + 1}: {move['pose']}"
                target = stage.target(name, move)
                frame += move_frames(move)
                targets.append(target)
                marks.append(stage.mark(name, beat["name"], move, frame, target["poses"][0]))
                end_m = max(end_m, float(move["at_m"]))
            if number == 0:
                # The shot's first piece starts from the pose the shot starts in.
                request = {"kind": "inbetween", "seed": stand(stage.poses[shot["start_pose"]], sx, sz, sheading), "targets": targets}
            else:
                # A later piece starts already in its first pose, holding still for as long as its first
                # move lasts. The seam's tween is what arrives in that pose, from wherever the piece before left off.
                piece["hold"] = {"pose": targets[0]["poses"][0], "frames": move_frames(moves[0])}
                piece["arrive_pins"] = moves[0].get("pins") or []
                request = {"kind": "inbetween", "seed": targets[0]["poses"][0], "targets": targets[1:]} if targets[1:] else None
        elif source == "text":
            request, more_marks, count = text_piece(stage, beat, first, piece)
            frame += count
            marks += more_marks
            end_m = max(end_m, float(beat["to_m"]))
        elif source == "video":
            import_video_beat()
            import beat as video_beat

            before = seam_takes(shot["beats"][number - 1], beat)[1] if number else 0
            after = seam_takes(beat, shot["beats"][number + 1])[0] if number + 1 < len(shot["beats"]) else 0
            request = None
            motion, more_marks, count = video_beat.piece(stage, beat, first, piece, sk, before, after)
            if made is not None:
                made[piece["video"]] = {"format": "forge-soma-motion/1", "fps": FPS, **{k: motion[k] for k in ("joints", "root", "rotations", "contact_order", "contacts")}}
            frame += count
            marks += more_marks
            end_m = max(end_m, float(beat["to_m"]))
        else:
            raise ValueError(f"beat \"{beat['name']}\": a beat's motion comes from {' or '.join(SOURCES)}, not \"{source}\"")
        piece["last_frame"] = frame
        if request is not None:
            piece["request"] = digest(request)
            requests[piece["request"]] = request
        pieces.append(piece)
        beats.append(
            {
                "name": beat["name"],
                "source": source,
                "first_frame": first,
                "last_frame": frame,
                "planned_seconds": float(beat.get("seconds") or (frame - first) / FPS),
                "seconds": round((frame - first) / FPS, 3),
            }
        )

    seams = []
    for i, (a, b) in enumerate(zip(pieces, pieces[1:])):
        from_end, from_start = seam_takes(shot["beats"][i], shot["beats"][i + 1])
        edge = a["last_frame"]
        seams.append(
            {
                "from": a["name"],
                "to": b["name"],
                "boundary_frame": edge,
                "take_from_end": from_end,
                "take_from_start": from_start,
                "context_frames": [edge - from_end - 3, edge - from_end - 2, edge - from_end - 1, edge - from_end],
                "tween_frames": [edge - from_end, edge + from_start],
                "tokens": (from_end + from_start + 7) // 4,
                "pins": b.get("arrive_pins") or [],
                "target": f"the start of {b['name']}",
                "made_by": "MotionBricks inbetween",
            }
        )
    for i, piece in enumerate(pieces):
        taken = (seams[i - 1]["take_from_start"] if i else 0) + (seams[i]["take_from_end"] + 3 if i < len(seams) else 0)
        if taken > piece["last_frame"] - piece["first_frame"]:
            raise ValueError(f"{piece['name']}: its seams would replace {taken} of its {piece['last_frame'] - piece['first_frame']} frames; make the beat longer or the joins shorter")

    record = {
        "fps": FPS,
        "frames": frame + 1,
        "seconds": round(frame / FPS, 3),
        "start": {"pose": shot["start_pose"], "x": round(sx, 4), "z": round(sz, 4), "heading": round(sheading, 2)},
        "beats": beats,
        "moves": marks,
        "path": [[round(p[0], 3), round(p[1], 3)] for p in path.points[::5]] + [[round(v, 3) for v in path.points[-1]]],
        "path_length_m": round(path.length, 3),
        "seams": seams,
        "pieces": pieces,
    }
    if set_card:
        record["set"], record["wall"] = set_blocks(path, set_card, end_m)
    return record, requests


def import_video_beat() -> None:
    """scripts/video is where a video beat is read (beat.py); it is only looked for when a shot has one."""
    there = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "video")
    if there not in sys.path:
        sys.path.insert(0, there)


def text_piece(stage, beat: dict, first: int, piece: dict) -> tuple:
    """A text beat as Kimodo's input. Kimodo starts every motion at x 0, z 0 facing +Z, so the
    request is written in a frame of its own: the origin is where this piece starts on the
    path, +Z the way the path runs there. `placement` says how to put the answer back."""
    from plan_shot import stand

    path = stage.path
    prompt = str(beat.get("prompt") or "").strip()
    if not prompt:
        raise ValueError(f"{beat['name']}: a text beat needs a prompt")
    if beat.get("from_m") is None or beat.get("to_m") is None:
        raise ValueError(f"{beat['name']}: a text beat says where it starts and ends on the path (from_m, to_m)")
    count = int(beat["frames"]) if beat.get("frames") else int(round(float(beat["seconds"]) * FPS))
    seconds = count / FPS
    from_m, to_m = float(beat["from_m"]), float(beat["to_m"])
    even = (to_m - from_m) / seconds
    speed_in = float(beat["speed_in_mps"]) if beat.get("speed_in_mps") is not None else even
    speed_out = float(beat["speed_out_mps"]) if beat.get("speed_out_mps") is not None else even
    lead, tail = int(beat.get("lead_frames") or 0), int(beat.get("tail_frames") or 0)
    if lead < 0 or tail < 0 or lead + count + 1 + tail > 10 * FPS:
        raise ValueError(f"{beat['name']}: with its run-up and follow-through a text beat is at most 10 seconds")
    along = pace(from_m, to_m, speed_in, speed_out, seconds)
    x0, z0, h0 = path.at(along(-lead / FPS))

    def local(x: float, z: float) -> list:
        lx, lz = turn_xz(x - x0, z - z0, -h0)
        return [round(lx, 4), round(lz, 4)]

    total = lead + count + 1 + tail
    points = []
    for f in range(total):
        x, z, _ = path.at(along((f - lead) / FPS))
        points.append(local(x, z))
    constraints = [{"type": "path", "frames": list(range(total)), "points": points}]
    marks, keyed = [], set()
    for n, key in enumerate(beat.get("keys") or []):
        at_frame = int(round(float(key["at_seconds"]) * FPS))
        if not 0 <= at_frame <= count:
            raise ValueError(f"{beat['name']}: key {n + 1} is at {key['at_seconds']} s, outside the beat")
        x, z, _, heading = stage.placed(key)
        placed = stand(stage.poses[key["pose"]], x, z, heading)
        mine = local(x, z)
        pose = {"rotations": placed["rotations"], "root": placed["root"], "at": [mine[0], 0.0, mine[1]], "heading": round(heading - h0, 3), "stands_at": mine}
        only = key.get("only") or []
        if only:
            constraints.append({"type": "reach", "frames": [lead + at_frame], "poses": [pose], "parts": only})
        else:
            constraints.append({"type": "pose", "frames": [lead + at_frame], "poses": [pose]})
        name = f"{beat['name']} key {n + 1}: {key['pose']}" + (f" ({', '.join(only)})" if only else "")
        marks.append(stage.mark(name, beat["name"], {**key, "pins": only}, first + at_frame, placed))
        keyed.add(at_frame)
    if count not in keyed:
        # Where the beat should end: on the path, facing along it.
        x, z, heading = path.at(to_m)
        marks.append(
            {
                "name": f"{beat['name']}: ends",
                "beat": beat["name"],
                "pose": None,
                "frame": first + count,
                "x": round(x, 4),
                "z": round(z, 4),
                "heading": round(heading, 2),
                "stands_at": [round(x, 4), round(z, 4)],
                "speed_mps": round(speed_out, 3),
                "early_frames": 0,
                "pins": [],
                "pin_points": {},
                "hold_pins_frames": 0,
            }
        )
    marks.sort(key=lambda m: m["frame"])
    request = {
        "kind": "text",
        "prompts": [{"text": prompt, "frames": total, "constraints": constraints}],
        "seed": int(beat.get("seed") or 0),
        "steps": int(beat.get("steps") or 100),
        "guidance": [float(v) for v in (beat.get("guidance") or (2.0, 2.0))],
        "tidy": True,
    }
    piece["prompt"] = prompt
    piece["keep"] = [lead, lead + count]
    piece["placement"] = {"x": round(x0, 4), "z": round(z0, 4), "heading": round(h0, 3)}
    return request, marks, count


# ---- the pieces as motions, where they were planned ------------------------------


def piece_motion(sk: Skeleton, piece: dict, answers: dict) -> dict:
    """One piece as a motion standing where the plan put it (before any seam moves it)."""
    count = piece["last_frame"] - piece["first_frame"] + 1
    answer = by_our_joints(sk, answers[piece["request"]]) if piece.get("request") else None
    if piece["source"] == "video":
        motion = by_our_joints(sk, answers[piece["video"]])  # cut and placed when the shot was planned
    elif piece["source"] == "text":
        first, last = piece["keep"]
        if len(answer["root"]) <= last:
            raise ValueError(f"{piece['name']}: the answer has {len(answer['root'])} frames, the plan keeps up to frame {last}")
        where = piece["placement"]
        motion = moved(cut(answer, first, last), where["heading"], where["x"], where["z"])
    elif piece.get("hold"):
        motion = held(sk, piece["hold"]["pose"], piece["hold"]["frames"] + 1)
        if answer:
            for key in ("root", "rotations", "contacts"):
                motion[key] += answer[key][1:]
    else:
        motion = cut(answer, 0, len(answer["root"]) - 1)
    if len(motion["root"]) != count:
        raise ValueError(f"{piece['name']}: made {len(motion['root'])} frames, the plan has {count}")
    return motion


def seam_request(seam: dict, a: dict, b: dict) -> dict:
    """What MotionBricks is asked for at a seam: carry on from A's last kept frames, arrive in B's first kept ones."""
    end = len(a["root"]) - 1 - seam["take_from_end"]
    start = seam["take_from_start"]
    target = {
        "name": f"{seam['from']} to {seam['to']}",
        "poses": [pose_of(b, f) for f in range(start, min(start + 4, len(b["root"])))],
        "tokens": seam["tokens"],
        "transition_early_by": 0,
    }
    if seam.get("pins"):
        target["pins"] = seam["pins"]
    return {"kind": "inbetween", "context": [pose_of(a, f) for f in range(end - 3, end + 1)], "targets": [target]}


# ---- the join --------------------------------------------------------------------


def anchor(sk: Skeleton, b: dict, frame: int, onto: dict) -> tuple:
    """Pick piece B up and set it down so that its `frame` stands where the last frame of `onto`
    stands, facing the same way. Returns (B moved, (the turn, then the slide, that moved it))."""
    last = len(onto["root"]) - 1
    turn = (facing(sk, onto, last) - facing(sk, b, frame) + 180.0) % 360.0 - 180.0
    bx, bz = turn_xz(b["root"][frame][0], b["root"][frame][2], turn)
    ex, ez = onto["root"][last][0], onto["root"][last][2]
    return moved(b, turn, ex - bx, ez - bz), (turn, ex - bx, ez - bz)


def gap(sk: Skeleton, b: dict, frame: int, onto: dict) -> tuple:
    """(cm over the ground, degrees of facing) between the last frame of `onto` and B's `frame`."""
    last = len(onto["root"]) - 1
    turn = (facing(sk, onto, last) - facing(sk, b, frame) + 180.0) % 360.0 - 180.0
    return round(100.0 * math.hypot(onto["root"][last][0] - b["root"][frame][0], onto["root"][last][2] - b["root"][frame][2]), 2), round(turn, 2)


def ease_in(b: dict, frame: int, onto: dict) -> float:
    """Ease what is left of the mismatch between `onto`'s last frame and B's `frame` out of the
    frames of B that follow. Changes B in place; returns the largest joint turn eased, in degrees."""
    last = len(onto["root"]) - 1
    joints = len(b["joints"])
    want, have = onto["rotations"][last], b["rotations"][frame]
    off = [qmul(tuple(want[4 * j : 4 * j + 4]), qconj(tuple(have[4 * j : 4 * j + 4]))) for j in range(joints)]
    rise = onto["root"][last][1] - b["root"][frame][1]
    worst = max(math.degrees(2.0 * math.acos(min(1.0, abs(q[3])))) for q in off)
    for i in range(EASE_FRAMES + 1):
        f = frame + i
        if f >= len(b["root"]):
            break
        t = i / (EASE_FRAMES + 1.0)
        w = 1.0 - t * t * (3.0 - 2.0 * t)
        row = b["rotations"][f]
        for j in range(joints):
            q = tuple(row[4 * j : 4 * j + 4])
            row[4 * j : 4 * j + 4] = [round(c, 6) for c in qslerp(q, qnorm(qmul(off[j], q)), w)]
        b["root"][f] = [b["root"][f][0], round(b["root"][f][1] + rise * w, 5), b["root"][f][2]]
    return round(worst, 2)


def join(sk: Skeleton, plan: dict, motions: list, tweens: list) -> tuple:
    """The pieces and the seams' tweens as one motion. Returns (motion, what the join did)."""
    out = {key: [] for key in ("root", "rotations", "contacts")}
    made, notes = [], []
    carried = (0.0, 0.0, 0.0)  # how the piece being laid down was moved: a turn, then a slide
    b = motions[0]
    for i, piece in enumerate(plan["pieces"]):
        seam = plan["seams"][i] if i < len(plan["seams"]) else None
        keep_from = plan["seams"][i - 1]["take_from_start"] + 1 if i else 0
        keep_to = len(b["root"]) - 1 - (seam["take_from_end"] if seam else 0)
        first = len(out["root"])
        for key in out:
            out[key] += b[key][keep_from : keep_to + 1]
        made.append({"name": piece["name"], "first_frame": first, "last_frame": len(out["root"]) - 1, "made_by": MADE_BY[piece["source"]]})
        if not seam:
            break
        # The tween was made where A was planned to stand; it goes wherever A went.
        made_at = by_our_joints(sk, tweens[i])
        tween = moved(made_at, *carried)
        want = seam["take_from_end"] + seam["take_from_start"] + 1
        if len(tween["root"]) != want:
            raise ValueError(f"the tween from {seam['from']} to {seam['to']} has {len(tween['root'])} frames, the plan has {want}")
        first = len(out["root"])
        for key in out:
            out[key] += tween[key][1:]
        made.append({"name": f"{seam['from']} to {seam['to']}", "first_frame": first, "last_frame": len(out["root"]) - 1, "made_by": "MotionBricks, a tween across the seam"})
        planned = motions[i + 1]
        missed = gap(sk, planned, seam["take_from_start"], made_at)
        b, carried = anchor(sk, planned, seam["take_from_start"], tween)
        from_plan = gap(sk, planned, seam["take_from_start"], tween)
        notes.append(
            {
                "from": seam["from"],
                "to": seam["to"],
                "tween_frames": seam["tween_frames"],
                # How far this tween ended from where the next piece begins: this seam's own miss.
                "tween_missed_by_cm": missed[0],
                "tween_missed_by_deg": missed[1],
                # Where that leaves the next piece, against its plan: every miss so far, added up.
                "next_piece_from_its_plan_cm": from_plan[0],
                "next_piece_from_its_plan_deg": from_plan[1],
                "eased_deg": ease_in(b, seam["take_from_start"], tween),
            }
        )
    if len(out["root"]) != plan["frames"]:
        raise ValueError(f"joined {len(out['root'])} frames, the plan has {plan['frames']}")
    motion = {
        "format": "forge-soma-motion/1",
        "fps": FPS,
        "up": "+Y",
        "forward_at_heading_0": "+Z",
        "joints": list(sk.joints),
        "root": out["root"],
        "rotations": out["rotations"],
        "contact_order": list(CONTACT_ORDER),
        "contacts": out["contacts"],
        "segments": made,
    }
    return motion, {"seams": notes, "ease_frames": EASE_FRAMES}


# ---- one pass ------------------------------------------------------------------


def cache_path(shot: str, name: str, kind: str = "") -> str:
    return os.path.join(shot, "cache", f"{name}{'.' + kind if kind else ''}.json")


def load_answer(shot: str, name: str):
    path = cache_path(shot, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def keep_request(shot: str, request: dict) -> str:
    name = digest(request)
    os.makedirs(os.path.join(shot, "cache"), exist_ok=True)
    path = cache_path(shot, name, "request")
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(request, f, separators=(",", ":"))
    return name


def step(shot: str, sk: Skeleton = None) -> dict:
    """Do as much as the answers on hand allow. Returns what is still to make and what was done."""
    sk = sk or Skeleton.load()
    with open(os.path.join(shot, "plan.json")) as f:
        plan = json.load(f)
    if "pieces" not in plan:
        raise ValueError("this shot's plan has no pieces: it is made in one go, not joined")
    todo = [{"request": p["request"], "kind": {"poses": "inbetween", "text": "text"}[p["source"]], "what": p["name"]} for p in plan["pieces"] if p.get("request") and load_answer(shot, p["request"]) is None]
    done = {"pieces": len(plan["pieces"]), "seams": len(plan["seams"]), "joined": False}
    if not todo:
        answers = {p["request"]: load_answer(shot, p["request"]) for p in plan["pieces"] if p.get("request")}
        for p in plan["pieces"]:
            if p.get("video"):
                answers[p["video"]] = load_answer(shot, p["video"])
                if answers[p["video"]] is None:
                    raise ValueError(f"{p['name']}: its motion from the clip is not in the shot's cache; plan the shot again (plan_shot.py)")
        motions = [piece_motion(sk, p, answers) for p in plan["pieces"]]
        names = [keep_request(shot, seam_request(seam, motions[i], motions[i + 1])) for i, seam in enumerate(plan["seams"])]
        todo = [{"request": name, "kind": "inbetween", "what": f"{seam['from']} to {seam['to']}"} for name, seam in zip(names, plan["seams"]) if load_answer(shot, name) is None]
        done["seam_requests"] = names
        if not todo:
            motion, notes = join(sk, plan, motions, [load_answer(shot, name) for name in names])
            notes["requests"] = {"pieces": {p["name"]: p.get("request") for p in plan["pieces"]}, "seams": {f"{s['from']} to {s['to']}": n for s, n in zip(plan["seams"], names)}}
            if any(p["source"] == "video" for p in plan["pieces"]):
                # A dancer from a video rarely stands exactly where the beats either side were planned, and a join
                # that covers the difference slides the body there with its feet still called down (30 to 40 cm,
                # on the crew). So the joined shot's feet are held where they are down, as the video's own are:
                # the difference is taken in a step. (scripts/video/footlock.py; FORGE_FOOT_LOCK=0 leaves it.)
                import_video_beat()
                import footlock

                if footlock.wanted(all((p.get("feet") or {}).get("locked", True) for p in plan["pieces"] if p["source"] == "video")):
                    slid = footlock.slide(sk, motion)
                    motion, held = footlock.lock(sk, motion)
                    notes["feet"] = {"locked": True, "slid_cm_per_s": slid["cm_per_s"], "worst_stretch_was_cm": slid["worst_stretch_cm"], **held}
            with open(os.path.join(shot, "motion.json"), "w") as f:
                json.dump(motion, f, separators=(",", ":"))
            with open(os.path.join(shot, "join.json"), "w") as f:
                json.dump(notes, f, indent=1)
            done["joined"] = True
            done["notes"] = notes
    with open(os.path.join(shot, "todo.json"), "w") as f:
        json.dump(todo, f, indent=1)
    return {"todo": todo, **done}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("shot")
    args = parser.parse_args()
    result = step(args.shot)
    for item in result["todo"]:
        print(f"TIMELINE to make: {item['kind']} for {item['what']} ({item['request']})")
    if result["joined"]:
        for seam in result["notes"]["seams"]:
            print(
                f"TIMELINE seam {seam['from']} to {seam['to']}: frames {seam['tween_frames'][0]}-{seam['tween_frames'][1]}; "
                f"the tween ended {seam['tween_missed_by_cm']} cm and {seam['tween_missed_by_deg']} deg from the next piece, which now stands "
                f"{seam['next_piece_from_its_plan_cm']} cm and {seam['next_piece_from_its_plan_deg']} deg from its plan; {seam['eased_deg']} deg eased out"
            )
        print(f"TIMELINE joined {result['pieces']} pieces across {result['seams']} seams into motion.json")
    elif not result["todo"]:
        print("TIMELINE nothing to make and nothing joined")


if __name__ == "__main__":
    main()
