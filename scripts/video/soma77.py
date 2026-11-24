"""A video's motion, shot by shot, as one motion our characters can play: converted, joined, written as a shot.

    python3 scripts/video/soma77.py <clip folder> <shot folder>

In: what the video worker answers for each shot ("gemx-soma77/1", GEM-X's SOMA
body with 77 joints). Out: a shot folder like the ones `just shoot` makes, with
the repo's own motion format in it ("forge-soma-motion/1": 30 frames a second,
joints by SOMA name, root, local rotations, which feet are down). From there
it is `just cast`'s as any shot is: soma_to_plain.py, the character's own
skeleton and limits, planted feet.

Converting one shot. GEM-X gives each person their own proportions and says how
far each joint has turned from that person's own rest pose. Our skeleton has
its proportions and its own rest pose. So a pose is carried across by what it
looks like, as Kimodo's is (motionbricks_worker/models/soma_bridge.py does
both): every bone ends up pointing the way it points on GEM-X's body. Three
things are ours to settle:

  size     the hips' path is scaled by our leg length over the person's, so a
           step that was one leg-length long still is
  ground   the lowest the toes go, bar a few stray frames, is the floor
  check    GEM-X's own hands, toes and head are compared with where ours end
           up (`ours_vs_gemx_cm`); a few centimetres is the two bodies'
           proportions, a lot would mean the two skeletons are not being
           read the same way

Joining shots. A cut is the camera jumping, not the dancer. But each shot's
motion comes back in a world of its own: where the person stands and which way
they face start from nothing every time. So across a cut the hips' place and
facing are carried over: each shot is picked up whole (timeline.py's `anchor`,
as a seam does it) and set down where the last one ended, facing the same way
and still moving as it was. Inside a shot nothing changes. What is left at
the join, the body's pose a frame apart in the film but made separately, is
eased out over the first frames of the new shot (BLEND_FRAMES). Every frame
of the film that was kept is a frame of the motion, so the two stay in step.

(MotionBricks could make a tween at each cut through the same seam code. It
would put half a second of made-up movement in place of the dance at every
cut, and each one is a paid call, so the join here is a blend.)

Plain Python: no Blender, no numpy.
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
sys.path.insert(0, os.path.join(REPO, "motionbricks_worker", "models"))
import clip as clip_file  # noqa: E402
import timeline  # noqa: E402
from soma import SKELETON_FILE, Skeleton, cross, dot, qconj, qfrom_axes, qmul, qnorm, qrot, qslerp, scale, sub, unit  # noqa: E402
from soma_bridge import Bridge  # noqa: E402

FPS = 30
BLEND_FRAMES = 8  # frames of a new shot over which the jump in pose at a cut is eased out
GROUND_SHARE = 0.03  # the floor is where the lowest toe is, leaving out this share of the lowest frames
INVERTED_SHARE = 0.9  # refuse a shot as the wrong way up only when the body is upside down in more than this share of it
CONTACT_ORDER = ["left_heel", "left_toe", "right_heel", "right_toe"]
TOP_SPEED = 4.0  # m/s; the hips are not carried across a cut faster than this
STEADY_DEG_PER_FRAME = 12.0  # a joint turning less than this a frame is carried on across a cut at the rate it was turning


def stands(rest: dict) -> tuple:
    """Which way a body stands in its rest pose, as a rotation: its left, its up, its front."""
    up = unit(sub(rest["Head"], rest["Hips"]))
    across = sub(rest["LeftLeg"], rest["RightLeg"])
    left = unit(sub(across, scale(up, dot(across, up))))
    return qfrom_axes(left, up, cross(left, up))


def convert(raw: dict, sk: Skeleton, card: dict = None) -> tuple:
    """One shot's GEM-X answer in the repo's motion format. Returns (motion, what was measured)."""
    if raw.get("format") != "gemx-soma77/1":
        raise clip_file.Stop(f"the worker answered {raw.get('format')!r}, not a motion")
    if card is None:
        with open(SKELETON_FILE) as f:
            card = json.load(f)
    names = list(raw["joints"])
    missing = [name for name in sk.joints if name not in names]
    if missing:
        raise clip_file.Stop(f"the motion lacks joints our skeleton has: {', '.join(missing)}")
    at = {name: names.index(name) for name in sk.joints}
    count = len(raw["root"])
    hips = raw["rest"][at["Hips"]]
    rest = {name: tuple(raw["rest"][at[name]][a] - hips[a] for a in range(3)) for name in sk.joints}
    # If their rest pose stands another way round than ours, turn everything of theirs to stand as ours does.
    ours_rest = {name: sk.rest_world_pos[i] for i, name in enumerate(sk.joints)}
    turn = qnorm(qmul(stands(rest), qconj(stands(ours_rest))))  # carries our rest stance onto theirs
    rest = {name: qrot(qconj(turn), p) for name, p in rest.items()}
    bridge = Bridge(card, rest, 0.0)

    def leg(of: dict) -> float:
        return of["Hips"][1] - (of["LeftToeBase"][1] + of["RightToeBase"][1]) / 2.0

    size = leg(ours_rest) / leg(rest)
    order = [at[name] for name in bridge.joints]
    root_rows, rotation_rows = [], []
    for f in range(count):
        row = raw["turns"][f]
        turned = [qmul(qnorm(tuple(row[4 * j : 4 * j + 4])), turn) for j in order]
        _, local = bridge.from_kimodo((0.0, 0.0, 0.0), turned)
        root_rows.append([raw["root"][f][a] * size for a in range(3)])
        rotation_rows.append([round(c, 6) for q in local for c in q])

    # Where our body ends up: the floor under it, whether it is upright, and how near its hands, toes and head are to GEM-X's.
    toes = (sk.index["LeftToeBase"], sk.index["RightToeBase"])
    toe_rest = min(sk.rest_world_pos[t][1] for t in toes)
    lows, ups, apart = [], [], {name: [] for name in (raw.get("marks") or {}) if name in sk.index}
    for f in range(count):
        pos, _ = sk.fk(root_rows[f], [tuple(rotation_rows[f][4 * j : 4 * j + 4]) for j in range(len(sk.joints))])
        lows.append(min(pos[t][1] for t in toes) - toe_rest)
        ups.append(unit(sub(pos[sk.index["Head"]], pos[0]))[1])
        for name in apart:
            theirs = [(raw["marks"][name][f][a] - raw["root"][f][a]) * size for a in range(3)]
            apart[name].append(math.dist(sub(pos[sk.index[name]], pos[0]), theirs))
    upright = sorted(ups)[count // 2]
    # A person can be upside down for a while (a handplant, a cartwheel, a flip), so only a shot that is upside
    # down nearly all the way through says the worker's world is the wrong way up.
    inverted = sum(u < 0.0 for u in ups) / count
    if inverted > INVERTED_SHARE:
        raise clip_file.Stop("the motion came back upside down (%d%% of its frames): the worker's world is not Y-up the way this conversion expects" % round(100 * inverted))
    floor = sorted(lows)[min(count - 1, int(GROUND_SHARE * count))]
    for row in root_rows:
        row[1] -= floor
    contacts = [[round(float(c), 3) for c in row[:4]] for row in raw["contacts"]]
    motion = {
        "format": "forge-soma-motion/1",
        "fps": FPS,
        "up": "+Y",
        "forward_at_heading_0": "+Z",
        "joints": list(bridge.joints),
        "root": [[round(c, 5) for c in row] for row in root_rows],
        "rotations": rotation_rows,
        "contact_order": list(CONTACT_ORDER),
        "contacts": contacts,
    }
    report = {
        "frames": count,
        "size_ours_over_theirs": round(size, 4),
        "rest_pose_turned_deg": round(math.degrees(2.0 * math.acos(min(1.0, abs(turn[3])))), 2),
        "floor_moved_cm": round(100.0 * floor, 2),
        "upright": round(upright, 3),
        "ours_vs_gemx_cm": {name: {"typical": round(100.0 * sorted(d)[len(d) // 2], 1), "worst": round(100.0 * max(d), 1)} for name, d in apart.items()},
        "feet_down_share": round(sum(1 for c in contacts if max(c) > 0.5) / float(count), 3),
    }
    return motion, report


# ---- joining ---------------------------------------------------------------------


def carried(sk: Skeleton, b: dict, onto: dict) -> tuple:
    """Shot B set down where `onto` ends: its first frame where the hips were heading next, facing as they faced."""
    b, (turn, _, _) = timeline.anchor(sk, b, 0, onto)
    last = len(onto["root"]) - 1
    back = min(3, last)
    step = [(onto["root"][last][a] - onto["root"][last - back][a]) / back if back else 0.0 for a in (0, 2)]
    speed = math.hypot(*step) * FPS
    if speed > TOP_SPEED:
        step = [c * TOP_SPEED / speed for c in step]
    b = timeline.moved(b, 0.0, step[0], step[1])
    return b, {"turned_deg": round(turn, 1), "carried_at_m_per_s": round(min(speed, TOP_SPEED), 2)}


def blend_in(b: dict, onto: dict, frames: int = BLEND_FRAMES) -> float:
    """Eases the jump in pose at a cut out of B's first frames (as timeline.py's ease_in does for a seam, over
    more frames). The jump is between B's first frame and where `onto` was heading one frame on.
    Changes B in place; returns the largest joint turn eased, in degrees."""
    last = len(onto["root"]) - 1
    joints = len(b["joints"])
    end, have = onto["rotations"][last], b["rotations"][0]
    before = onto["rotations"][last - 1] if last else end
    want, height = [], onto["root"][last][1] + (onto["root"][last][1] - onto["root"][last - 1][1] if last else 0.0)
    for j in range(joints):
        a, z = tuple(before[4 * j : 4 * j + 4]), tuple(end[4 * j : 4 * j + 4])
        # B's first frame is one frame after `onto`'s last: where each joint was heading, not where it was.
        # (A joint turning faster than a body does is noise; that one is taken as it was.)
        going = math.degrees(2.0 * math.acos(min(1.0, abs(sum(x * y for x, y in zip(a, z))))))
        want.append(qslerp(a, z, 2.0) if going < STEADY_DEG_PER_FRAME else z)
    off = [qmul(want[j], qconj(tuple(have[4 * j : 4 * j + 4]))) for j in range(joints)]
    rise = height - b["root"][0][1]
    worst = max(math.degrees(2.0 * math.acos(min(1.0, abs(q[3])))) for q in off)
    for f in range(min(frames, len(b["root"]))):
        t = (f + 1.0) / (frames + 1.0)
        w = 1.0 - t * t * (3.0 - 2.0 * t)
        row = b["rotations"][f]
        for j in range(joints):
            q = tuple(row[4 * j : 4 * j + 4])
            row[4 * j : 4 * j + 4] = [round(c, 6) for c in qslerp(q, qnorm(qmul(off[j], q)), w)]
        b["root"][f] = [b["root"][f][0], round(b["root"][f][1] + rise * w, 5), b["root"][f][2]]
    return round(worst, 2)


def stitch(sk: Skeleton, pieces: list, blend: int = BLEND_FRAMES) -> tuple:
    """The shots' motions, in order, as one. `pieces` is [(name, motion)]. Returns (motion, joins, segments)."""
    out, joins, segments = None, [], []
    for name, piece in pieces:
        piece = {**piece, "root": [list(r) for r in piece["root"]], "rotations": [list(r) for r in piece["rotations"]], "contacts": [list(c) for c in piece["contacts"]]}
        if out is None:
            # The first shot starts at the middle of the floor, facing forward (heading 0).
            piece = timeline.moved(piece, -timeline.facing(sk, piece, 0), 0.0, 0.0)
            piece = timeline.moved(piece, 0.0, -piece["root"][0][0], -piece["root"][0][2])
            out = piece
            segments.append({"name": name, "first_frame": 0, "last_frame": len(piece["root"]) - 1, "made_by": "GEM-X, from the video"})
            continue
        boundary = len(out["root"])
        piece, how = carried(sk, piece, out)
        how["pose_eased_deg"] = blend_in(piece, out, blend)
        joins.append({"from": segments[-1]["name"], "to": name, "boundary_frame": boundary, "tween_frames": [boundary, min(boundary + blend, boundary + len(piece["root"]) - 1)], "made_by": f"carried over, then a blend of {blend} frames", **how})
        for key in ("root", "rotations", "contacts"):
            out[key] = out[key] + piece[key]
        segments.append({"name": name, "first_frame": boundary, "last_frame": len(out["root"]) - 1, "made_by": "GEM-X, from the video"})
    return out, joins, segments


def plan_for(sk: Skeleton, motion: dict, joins: list, segments: list, title: str) -> tuple:
    """plan.json and shotlist.json for a motion nobody planned: what checks.py, apply_shot.py and render_shot.py read.
    Each shot of the film is a beat; where it ended is its one "move"; the path is the path the hips took."""
    count = len(motion["root"])
    moves, beats = [], []
    for s in segments:
        f = s["last_frame"]
        before = max(s["first_frame"], f - 3)
        speed = math.hypot(motion["root"][f][0] - motion["root"][before][0], motion["root"][f][2] - motion["root"][before][2]) * FPS / max(1, f - before)
        x, z = motion["root"][f][0], motion["root"][f][2]
        moves.append({"name": f"{s['name']} ends", "beat": s["name"], "pose": None, "frame": f, "x": x, "z": z, "heading": round(timeline.facing(sk, motion, f), 2), "stands_at": [x, z],
                      "speed_mps": round(speed, 2), "early_frames": 0, "pins": [], "pin_points": {}, "hold_pins_frames": 0})
        beats.append({"name": s["name"], "source": "video", "first_frame": s["first_frame"], "last_frame": f, "seconds": round((f - s["first_frame"] + 1) / FPS, 3)})
    path = [[motion["root"][f][0], motion["root"][f][2]] for f in list(range(0, count, 6)) + [count - 1]]
    plan = {
        "fps": FPS,
        "frames": count,
        "seconds": round((count - 1) / FPS, 3),
        "start": {"pose": None, "x": 0.0, "z": 0.0, "heading": 0.0},
        "beats": beats,
        "moves": moves,
        "path": path,
        "path_length_m": round(sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:])), 3),
        "seams": joins,
        "set": [],
        # The film looks at the dancer's front: they start facing heading 0, and stay roughly there or come back to it.
        "film_direction_deg": 0.0,
    }
    shotlist = {"title": title, "props": [], "camera": [{"from_seconds": 0.0, "view": "front", "distance_m": 4.6}]}
    return plan, shotlist


def build(folder: str, shot_dir: str, sk: Skeleton = None) -> dict:
    """Makes the shot folder from the clip's motion/ answers and its choice. Returns source.json."""
    import people as people_file

    sk = sk or Skeleton.load()
    choice = people_file.load_choice(folder)
    raw_people = clip_file.read(os.path.join(folder, "people-raw.json"))
    if not choice or not raw_people:
        raise clip_file.Stop("there is no choice of who to follow yet")
    name = os.path.basename(os.path.normpath(folder))
    pieces, used, reports = [], [], {}
    for shot in raw_people["shots"]:
        who = choice["shots"][str(shot["index"])]
        if who == "skip":
            continue
        answer = clip_file.read(os.path.join(folder, "motion", f"shot-{shot['index']:03d}.json"))
        if not answer:
            raise clip_file.Stop(f"shot {shot['index'] + 1} has no motion yet")
        label = f"Shot {shot['index'] + 1}"
        motion, report = convert(answer, sk)
        pieces.append((label, motion))
        reports[label] = {**report, "camera": (answer.get("made_by") or {}).get("camera"), "boxes_on_frames": (answer.get("made_by") or {}).get("frames_with_a_box")}
        used.append({"shot": shot["index"], "name": label, "person": who, "clip_first_frame": shot["first_frame"], "clip_last_frame": shot["last_frame"]})
    motion, joins, segments = stitch(sk, pieces)
    motion["segments"] = segments
    motion["made_by"] = {"model": "GEM-X body motion (native77), from a video", "clip": name, "joined": "the hips' place and facing carried across each cut; pose blended over a few frames"}
    for piece, segment in zip(used, segments):
        piece.update({"first_frame": segment["first_frame"], "last_frame": segment["last_frame"]})
    plan, shotlist = plan_for(sk, motion, joins, segments, f"From the clip {name}")
    os.makedirs(shot_dir, exist_ok=True)
    with open(os.path.join(shot_dir, "motion.json"), "w") as f:
        json.dump(motion, f, separators=(",", ":"))
    clip_file.write(os.path.join(shot_dir, "plan.json"), plan)
    clip_file.write(os.path.join(shot_dir, "shotlist.json"), shotlist)
    card = clip_file.read(os.path.join(folder, "clip.json")) or {}
    source = {"format": "forge-video-shot/1", "clip": name, "clip_sha256": (card.get("clip") or {}).get("sha256"), "frames": len(motion["root"]), "pieces": used, "joins": joins, "converted": reports, "choice": choice}
    clip_file.write(os.path.join(shot_dir, "source.json"), source)
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("clip")
    parser.add_argument("shot")
    args = parser.parse_args()
    try:
        source = build(args.clip, args.shot)
    except clip_file.Stop as stop:
        print(f"VIDEO stopped: {stop}")
        sys.exit(1)
    for label, report in source["converted"].items():
        print(f"VIDEO {label}: {report['frames']} frames, floor moved {report['floor_moved_cm']} cm, ours against GEM-X's {json.dumps(report['ours_vs_gemx_cm'])}")
    for join in source["joins"]:
        print(f"VIDEO join {join['from']} to {join['to']}: turned {join['turned_deg']} deg, pose eased {join['pose_eased_deg']} deg")
    print(f"VIDEO shot: {source['frames']} frames from {len(source['pieces'])} shots -> {args.shot}")


if __name__ == "__main__":
    main()
