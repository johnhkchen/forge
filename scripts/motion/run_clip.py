"""A looping run for each character, made from a sentence.

    python3 scripts/motion/run_clip.py <character run folder>... [--cache DIR] [--batch 8]

A character's walk is worked out from its build (walk.py). Its run is asked
for in words: Kimodo (NVIDIA's text-to-motion model, on the motion worker) is
given one sentence per character and a straight line to run along, and what
comes back is cut into a loop that runs on the spot.

The sentence and the speed. Both come from the character's brief and from
gait.json, the same four traits the walk uses (weight, stealth, swagger,
stiffness). The speed follows the leg, as the walk's does: runners of any
size move alike at the same Froude number, speed squared / (gravity x leg
length). About 1.7 is an easy human run; weight brings it well down, a stiff
build and creeping a little. The troll lumbers at 2.5 m/s; the ninja goes
low and quick at 3.4.

One job, several characters. A Kimodo job takes up to eight sentences and
makes them one after the other as one long motion, so one job carries every
character still without a run: six seconds each, slowest first, along one
straight line whose speed changes where one character's stretch ends and the
next begins. The first second and a half of each stretch (where it settles
into the new pace) is never used. `--batch 1` sends one job per character.

Caching. A character's ask (its sentence, speed, length and seed) has a
fingerprint; its clip is kept beside it, and is only made again when the ask
changes. Every request to the worker is kept under the sha256 of its content
in the cache folder, with its answer, like a shot's.

The loop. In the kept part of a clip this finds two frames a whole number of
strides apart where the body is most alike: where every joint is, how fast it
is moving, and which feet are down. It cuts there. The last few frames are
eased onto the frames that led into the first, so the end runs into the start
without a jump and the last frame is the first again. The average travel over
the ground is taken out, so the run stays in place; the speed is written down.

Like timeline.py, this never calls a worker. It writes <cache>/todo.json, the
requests that still need an answer, and whoever runs it (`baml run runs`)
sends those and runs it again. Per character it writes, in <run>/run/:

    ask.json    the sentence, the speed and how they were worked out
    clip.json   that character's six seconds, as the worker made them
    loop.json   the loop: in place, last frame equal to the first, with what
                the cut measured (strides, seam, speed)

Plain Python: no Blender, no numpy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soma_to_plain  # noqa: E402
from soma import Skeleton, heading_of, qconj, qmul, qslerp  # noqa: E402
from timeline import CONTACT_ORDER, by_our_joints, cut, moved  # noqa: E402

FPS = 30
GRAVITY = 9.81
TRAITS = ("weight", "stealth", "swagger", "stiffness")
ORDINARY = {"weight": 0.4, "stealth": 0.3, "swagger": 0.4, "stiffness": 0.4}  # gait.baml's "ordinary adult"
SECONDS = 6.0  # of running asked for per character (Kimodo makes at most 10 per sentence)
SETTLE_FRAMES = 45  # the start of a stretch is the model getting up to the new pace: never part of a loop
END_FRAMES = 6  # nor are its last few frames, where the next sentence is about to take over
RAMP_FRAMES = 24  # over which the path's speed changes from one character's to the next
SOMA_SPEEDS = (1.8, 5.5)  # m/s at the model's own size; outside this a "run" is a walk or a sprint it does badly
BATCH = 8  # sentences one Kimodo job takes
BLEND_FRAMES = 8  # the end of a loop eased onto the frames that led into its start
STRIDES_LIKED = 2  # a loop of two strides or more has a little life in it; a single stride has to match this much better
ONE_STRIDE_COSTS = 1.2
MOST_STRIDES = 3


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def smooth(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def read_json(path: str):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def write_json(path: str, value, indent=None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".partial", "w") as f:
        json.dump(value, f, indent=indent, separators=None if indent else (",", ":"))
    os.replace(path + ".partial", path)


# ---- what to ask for: the sentence and the speed -------------------------------


def build_of(run: str) -> dict:
    """The character's leg (hip joint above the floor, in metres) and bulk, from what rig.py measured for its walk."""
    for version in ("lowpoly", "midpoly"):
        walked = read_json(os.path.join(run, "profiles", version + "-walk.json"))
        measure = ((walked or {}).get("rig") or {}).get("measure") or {}
        if measure.get("hip_height"):
            return {"leg_m": float(measure["hip_height"]), "bulk": float(measure.get("bulk", 0.03)), "from": "its %s walk" % version}
    brief = read_json(os.path.join(run, "brief.json")) or {}
    size = brief.get("size_m")
    tall = float(size) if isinstance(size, (int, float)) else 1.8
    return {"leg_m": round(0.5 * tall, 3), "bulk": None, "from": "half its height (it has no walk yet)"}


def traits_of(run: str) -> dict:
    said = read_json(os.path.join(run, "gait.json")) or {}
    return {k: clamp(float(said[k]), 0.0, 1.0) if isinstance(said.get(k), (int, float)) else ORDINARY[k] for k in TRAITS}


def run_speed(leg_m: float, traits: dict, bulk: float = None) -> dict:
    """How fast this build runs: a Froude number from its manner, then the speed its leg gives it."""
    heavy = traits["weight"]
    if bulk is not None:  # the same blend of measured bulk and stated weight the walk uses
        heavy = 0.5 * clamp((bulk - 0.015) / 0.105, 0.0, 1.0) + 0.5 * traits["weight"]
    froude = 1.7 * (1 - 0.6 * heavy) * (1 - 0.08 * traits["stealth"]) * (1 + 0.15 * (traits["swagger"] - 0.3)) * (1 - 0.15 * traits["stiffness"])
    froude = clamp(froude, 0.55, 2.2)  # below about 0.5 nothing runs: it walks
    return {"froude": round(froude, 3), "heft": round(heavy, 3), "speed_mps": round(math.sqrt(froude * GRAVITY * leg_m), 3)}


BUILDS = (  # what the brief says about the body, as Kimodo's subject: "A stocky person ..."
    ("huge", r"\b(huge|giant|gigantic|enormous|massive|hulking|towering)\b"),
    ("stocky", r"\b(stocky|barrel-chested|thick-set|heavy-set|burly|stout|squat)\b"),
    ("tall", r"\b(tall)\b(?! as)"),
    ("lanky", r"\b(lanky|rangy|gangly|slender|slim|wiry|lean)\b"),
    ("small", r"\b(small|tiny|little|short)\b(?= (man|woman|person|child|boy|girl|creature|goblin|gnome|halfling|dwarf))"),
)


def subject_of(brief: dict) -> str:
    """"A stocky person": Kimodo's sentences are about a person, and a word or two on the build is all it takes."""
    told = (" ".join(str(brief.get(k) or "") for k in ("name", "description"))).lower()
    words = [word for word, pattern in BUILDS if re.search(pattern, told)]
    if "huge" in words:
        words = ["huge"]
    elif "stocky" in words:
        words = ["stocky"]
    words = words[:2]
    if not words:
        return "A person"
    article = "An" if words[0][0] in "aeiou" else "A"
    return "%s %s person" % (article, " ".join(words))


def run_prompt(brief: dict, traits: dict) -> str:
    """One sentence for Kimodo: who runs, and how. One manner, in the middling detail its training sentences have."""
    weight, stealth, swagger, stiff = (traits[k] for k in TRAITS)
    subject = subject_of(brief)
    if stealth >= 0.6:
        how = "runs forward stealthily in a low crouch, with light, quick, quiet steps"
    elif weight >= 0.8:
        how = "runs forward in a slow, heavy, lumbering run, with pounding steps"
    elif swagger >= 0.72:
        how = "runs forward proudly, upright with the chest out, with %s steps" % ("firm, strong" if weight >= 0.55 else "springy")
    elif swagger >= 0.55:
        how = "runs forward with a confident swagger, shoulders rolling%s" % (", with heavy steps" if weight >= 0.55 else "")
    elif weight >= 0.55:
        how = "runs forward at a steady pace with heavy, solid steps"
    elif weight < 0.4:
        how = "runs forward at an easy pace with long, loose, loping strides" if "lanky" in subject else "runs forward lightly with quick, springy steps"
    else:
        how = "runs forward at a steady, even pace"
    if stiff >= 0.6:
        how += " and a stiff upper body"
    return "%s %s." % (subject, how)


def ask_for(run: str, sk: Skeleton, seconds: float = SECONDS, seed: int = 0) -> dict:
    """Everything that decides a character's run clip. Its `hash` is the clip's fingerprint."""
    brief = read_json(os.path.join(run, "brief.json")) or {}
    traits, build = traits_of(run), build_of(run)
    pace = run_speed(build["leg_m"], traits, build["bulk"])
    soma_leg = sk.rest_world_pos[sk.index["LeftLeg"]][1]
    # The clip is made at the model's size and scaled to the character by its leg, speed and all.
    wanted = pace["speed_mps"] * soma_leg / build["leg_m"]
    ask = {
        "prompt": run_prompt(brief, traits),
        "frames": int(round(seconds * FPS)),
        "soma_speed_mps": round(clamp(wanted, *SOMA_SPEEDS), 3),
        "seed": int(seed),
        "steps": 100,
        "guidance": [2.0, 2.0],
    }
    return {
        "character": brief.get("name") or os.path.basename(run),
        **ask,
        "hash": digest(ask),
        "speed_mps": round(ask["soma_speed_mps"] * build["leg_m"] / soma_leg, 3),
        "froude": pace["froude"],
        "heft": pace["heft"],
        "leg_m": build["leg_m"],
        "leg_from": build["from"],
        "traits": traits,
        "traits_from": "gait.json" if os.path.exists(os.path.join(run, "gait.json")) else "an ordinary adult (no gait.json)",
    }


# ---- the worker's job ----------------------------------------------------------


def straight_path(asks: list) -> list:
    """Per ask, one [x, z] a frame: one straight line along +Z, each stretch at its own speed, changing smoothly."""
    out, z, before = [], 0.0, 0.0
    for ask in asks:
        points = []
        for f in range(ask["frames"]):
            speed = before + (ask["soma_speed_mps"] - before) * smooth((f + 1) / RAMP_FRAMES)
            if out or f:
                z += speed / FPS
            points.append([0.0, round(z, 4)])
        out.append(points)
        before = ask["soma_speed_mps"]
    return out


def batch_request(asks: list) -> dict:
    """One Kimodo job for these asks, in the order given."""
    prompts = [
        {"text": ask["prompt"], "frames": ask["frames"], "constraints": [{"type": "path", "frames": list(range(ask["frames"])), "points": points}]}
        for ask, points in zip(asks, straight_path(asks))
    ]
    first = asks[0]
    return {"kind": "text", "prompts": prompts, "seed": first["seed"], "steps": first["steps"], "guidance": first["guidance"], "tidy": True}


def batches(asks: list, size: int = BATCH) -> list:
    """The asks as jobs: slowest first, so each change of pace is a small one; asks that cannot share a job's settings get their own."""
    groups = {}
    for ask in sorted(asks, key=lambda a: (a["soma_speed_mps"], a["hash"])):
        groups.setdefault((ask["seed"], ask["steps"], tuple(ask["guidance"])), []).append(ask)
    out = []
    for group in groups.values():
        out += [group[i : i + size] for i in range(0, len(group), size)]
    return out


def stretch_of(answer: dict, number: int, ask: dict, sk: Skeleton) -> dict:
    """One character's frames out of a job's answer."""
    motion = by_our_joints(sk, answer)
    segments = answer.get("segments") or []
    if number >= len(segments):
        raise ValueError(f"the answer has {len(segments)} stretches, wanted number {number + 1}")
    first, last = int(segments[number]["first_frame"]), int(segments[number]["last_frame"])
    if last - first + 1 != ask["frames"] or last >= len(motion["root"]):
        raise ValueError(f"stretch {number + 1} is frames {first}-{last}, wanted {ask['frames']} frames")
    return cut(motion, first, last)


# ---- finding the loop ----------------------------------------------------------


def straightened(sk: Skeleton, motion: dict, first: int, last: int) -> dict:
    """The motion turned about the origin so that its travel from frame `first` to frame `last` is along +Z."""
    dx = motion["root"][last][0] - motion["root"][first][0]
    dz = motion["root"][last][2] - motion["root"][first][2]
    if math.hypot(dx, dz) < 1e-6:
        return motion
    return moved(motion, -math.degrees(math.atan2(dx, dz)), 0.0, 0.0)


def bodies(sk: Skeleton, motion: dict) -> list:
    """Per frame, every joint's position with the hips' place over the ground taken out."""
    joints = len(sk.joints)
    out = []
    for root, row in zip(motion["root"], motion["rotations"]):
        pos, _ = sk.fk(root, [tuple(row[4 * j : 4 * j + 4]) for j in range(joints)])
        out.append([(p[0] - root[0], p[1], p[2] - root[2]) for p in pos])
    return out


def stride_frames(sk: Skeleton, body: list, first: int, last: int) -> tuple:
    """How many frames one stride (left step and right step) takes, and how sure that is (1 = the legs repeat exactly).

    Read off the legs: how far the left toe is ahead of the right, compared with itself a while later."""
    left, right = sk.index["LeftToeBase"], sk.index["RightToeBase"]
    ahead = [body[f][left][2] - body[f][right][2] for f in range(first, last + 1)]
    mean = sum(ahead) / len(ahead)
    ahead = [a - mean for a in ahead]
    power = sum(a * a for a in ahead) / len(ahead)
    if power < 1e-8:
        raise ValueError("the legs do not move: there is no stride to find")
    alike = {}
    for lag in range(8, min(76, len(ahead) // 2 + 1)):
        pairs = len(ahead) - lag
        alike[lag] = sum(ahead[f] * ahead[f + lag] for f in range(pairs)) / pairs / power
    best = max(alike.values())
    if best < 0.3:
        raise ValueError("the legs never repeat themselves: this is not a steady run")
    for lag in sorted(alike):  # the first clear peak: later ones are two strides, three...
        if alike[lag] >= 0.85 * best and alike[lag] >= alike.get(lag - 1, -1.0) and alike[lag] >= alike.get(lag + 1, -1.0):
            return lag, round(alike[lag], 3)
    lag = max(alike, key=alike.get)
    return lag, round(alike[lag], 3)


def unlike(body: list, motion: dict, a: int, b: int) -> dict:
    """How unlike two frames are: where the joints are, how they are moving, which feet are down."""
    joints = len(body[a])

    def speed(f: int, j: int) -> tuple:
        return tuple((body[f + 1][j][k] - body[f - 1][j][k]) / 2.0 for k in range(3))

    def over_ground(f: int) -> tuple:
        return ((motion["root"][f + 1][0] - motion["root"][f - 1][0]) / 2.0, (motion["root"][f + 1][2] - motion["root"][f - 1][2]) / 2.0)

    pose = sum(math.dist(body[a][j], body[b][j]) ** 2 for j in range(joints)) / joints
    moving = sum(math.dist(speed(a, j), speed(b, j)) ** 2 for j in range(joints)) / joints + math.dist(over_ground(a), over_ground(b)) ** 2
    feet = sum((x - y) ** 2 for x, y in zip(motion["contacts"][a], motion["contacts"][b])) / 4.0
    # One number, in metres squared: a joint's speed counts as where it would be three frames on, and a foot down against a foot up as 8 cm.
    return {"pose": pose, "moving": moving, "feet": feet, "cost": pose + 9.0 * moving + 0.0064 * feet}


def find_loop(sk: Skeleton, motion: dict, first: int = SETTLE_FRAMES, last: int = None) -> dict:
    """The two frames to cut at: a whole number of strides apart, most alike in pose, movement and feet."""
    count = len(motion["root"])
    last = count - 1 - END_FRAMES if last is None else last
    first = max(first, BLEND_FRAMES, 1)
    last = min(last, count - 2)
    motion = straightened(sk, motion, first, last)
    body = bodies(sk, motion)
    stride, sure = stride_frames(sk, body, first, last)
    if last - first < stride + 2:
        raise ValueError(f"only {last - first} frames to look in, and one stride takes {stride}")
    best = None
    for strides in range(1, MOST_STRIDES + 1):
        slack = max(1, int(round(0.08 * strides * stride)))
        for frames in range(strides * stride - slack, strides * stride + slack + 1):
            for a in range(first, last - frames + 1):
                score = unlike(body, motion, a, a + frames)
                # (2 mm of slack, so that among perfect matches the longer loop still wins)
                weighed = (score["cost"] + 4e-6) * (ONE_STRIDE_COSTS if strides < STRIDES_LIKED else 1.0)
                if best is None or weighed < best["weighed"]:
                    best = {"weighed": weighed, "first": a, "last": a + frames, "strides": strides, **score}
    if best is None:
        raise ValueError("no two frames a whole stride apart in the part of the clip that may be used")
    a, b = best["first"], best["last"]
    joints = len(sk.joints)
    return {
        "first_frame": a,
        "last_frame": b,
        "frames": b - a,
        "strides": best["strides"],
        "stride_frames": stride,
        "stride_sureness": sure,
        "looked_in_frames": [first, last],
        # What the cut found, before anything was eased: the two frames it joins.
        "seam_before_blend": {
            "joints_apart_cm": round(100.0 * math.sqrt(best["pose"]), 2),
            "worst_joint_cm": round(100.0 * max(math.dist(body[a][j], body[b][j]) for j in range(joints)), 2),
            "speeds_apart_cm_per_frame": round(100.0 * math.sqrt(best["moving"]), 2),
            "feet_down_differ": round(math.sqrt(best["feet"]), 3),
        },
    }


# ---- cutting it ----------------------------------------------------------------


def make_loop(sk: Skeleton, motion: dict, found: dict, blend: int = BLEND_FRAMES) -> dict:
    """Frames first..last of the clip as a loop on the spot: the last frame is the first again."""
    a, b = found["first_frame"], found["last_frame"]
    motion = straightened(sk, motion, a, b)
    count = b - a
    blend = max(1, min(blend, count // 3, a))
    step_x = (motion["root"][b][0] - motion["root"][a][0]) / count
    step_z = (motion["root"][b][2] - motion["root"][a][2]) / count
    joints = len(sk.joints)

    def on_the_spot(f: int) -> list:
        root = motion["root"][f]
        return [root[0] - motion["root"][a][0] - step_x * (f - a), root[1], root[2] - motion["root"][a][2] - step_z * (f - a)]

    roots, rows, contacts = [], [], []
    for t in range(count + 1):
        f = a + t
        root, row, down = on_the_spot(f), list(motion["rotations"][f]), list(motion["contacts"][f])
        if t > count - blend:
            # The frames that led into the first one are where the end has to arrive: ease onto them.
            w = smooth((t - (count - blend)) / blend)
            g = f - count
            lead, lead_row, lead_down = on_the_spot(g), motion["rotations"][g], motion["contacts"][g]
            root = [root[k] + (lead[k] - root[k]) * w for k in range(3)]
            row = [c for j in range(joints) for c in qslerp(tuple(row[4 * j : 4 * j + 4]), tuple(lead_row[4 * j : 4 * j + 4]), w)]
            down = [x + (y - x) * w for x, y in zip(down, lead_down)]
        roots.append([round(v, 5) for v in root])
        rows.append([round(c, 6) for c in row])
        contacts.append([round(c, 3) for c in down])
    roots[-1], rows[-1], contacts[-1] = list(roots[0]), list(rows[0]), list(contacts[0])
    speed = math.hypot(step_x, step_z) * FPS
    hips = motion["joints"].index("Hips")
    faces = [heading_of(qmul(tuple(row[4 * hips : 4 * hips + 4]), qconj(sk.rest_rot[0]))) for row in rows]
    return {
        "format": "forge-soma-motion/1",
        "fps": FPS,
        "up": "+Y",
        "forward_at_heading_0": "+Z",
        "joints": list(sk.joints),
        "root": roots,
        "rotations": rows,
        "contact_order": list(CONTACT_ORDER),
        "contacts": contacts,
        "loop": {
            **found,
            "seconds": round(count / FPS, 3),
            "blend_frames": blend,
            "in_place": True,
            "speed_mps": round(speed, 4),  # at the model's size: how fast the ground would have to slide back under it
            "steps_per_minute": round(2 * found["strides"] * 60.0 * FPS / count),
            "faces_deg": [round(min(faces), 2), round(max(faces), 2)],  # 0 is straight ahead
            "first_equals_last": roots[0] == roots[-1] and rows[0] == rows[-1],
        },
    }


def travelling(loop: dict, rounds: int = 3) -> dict:
    """The loop played `rounds` times with its travel put back, as one motion over the ground."""
    count = len(loop["root"]) - 1
    step = loop["loop"]["speed_mps"] / FPS
    out = {key: loop[key] for key in ("format", "fps", "joints", "contact_order")}
    out["root"], out["rotations"], out["contacts"] = [], [], []
    for f in range(rounds * count + 1):
        root = loop["root"][f % count]
        out["root"].append([root[0], root[1], root[2] + step * f])
        out["rotations"].append(loop["rotations"][f % count])
        out["contacts"].append(loop["contacts"][f % count])
    return out


def loop_to_plain(loop: dict, sk: Skeleton, name: str = "run") -> tuple:
    """The loop as animate.py's plain motion: looping, in place, with `travel` saying how fast the ground slides back.

    Feet are planted the way any motion's are (soma_to_plain.py), but on the loop played three times
    over the ground, so a foot that is down across the seam is planted the same at both ends. The
    middle round is kept and its travel taken out again: a planted foot then moves straight back at
    exactly `travel`, which is what animate.py holds it to."""
    count = len(loop["root"]) - 1
    plain, report = soma_to_plain.convert(travelling(loop), sk, name)
    unit = report["soma_hip_height_m"]
    per_frame = loop["loop"]["speed_mps"] / FPS / unit  # hip heights the ground slides back each frame
    keep = range(count, 2 * count + 1)
    plain["hips"] = [[h[0], round(h[1] + per_frame * f, 5), h[2]] for f, h in ((f, plain["hips"][f]) for f in keep)]
    for tag in ("l", "r"):
        plain["feet"][tag] = [[b[0], round(b[1] + per_frame * f, 5)] + b[2:] for f, b in ((f, plain["feet"][tag][f]) for f in keep)]
    plain["turns"] = {bone: [rows[f] for f in keep] for bone, rows in plain["turns"].items()}
    plain.update({"frames": count, "loop": True, "travel": round(per_frame * FPS, 5)})
    seam = max(
        [abs(x - y) for x, y in zip(plain["hips"][0], plain["hips"][-1])]
        + [abs(x - y) for tag in ("l", "r") for x, y in zip(plain["feet"][tag][0][:3], plain["feet"][tag][-1][:3])]
    )
    report.update({"frames": count, "loop_seam_hip_heights": round(seam, 5), "travel_hip_heights_per_s": plain["travel"]})
    return plain, report


# ---- one pass ------------------------------------------------------------------


def step(folders: list, cache: str, sk: Skeleton = None, size: int = BATCH, seconds: float = SECONDS, seed: int = 0) -> dict:
    """Do as much as the answers on hand allow. Returns what is still to make and what each character has."""
    sk = sk or Skeleton.load()
    os.makedirs(cache, exist_ok=True)
    asks, state = {}, {}
    for run in folders:
        if not os.path.exists(os.path.join(run, "gait.json")):
            state[run] = "skipped: no gait.json (not a character that walks)"
            continue
        asks[run] = ask_for(run, sk, seconds, seed)
        write_json(os.path.join(run, "run", "ask.json"), asks[run], indent=1)
    wanting = [run for run in asks if (read_json(os.path.join(run, "run", "clip.json")) or {}).get("ask") != asks[run]["hash"]]
    by_hash = {}
    for run in wanting:
        by_hash.setdefault(asks[run]["hash"], []).append(run)
    todo = []
    for batch in batches([asks[runs[0]] for runs in by_hash.values()], size):
        request = batch_request(batch)
        name = digest(request)
        request_file = os.path.join(cache, name + ".request.json")
        if not os.path.exists(request_file):
            write_json(request_file, request)
        answer = read_json(os.path.join(cache, name + ".json"))
        if answer is None:
            who = [asks[run]["character"] for ask in batch for run in by_hash[ask["hash"]]]
            todo.append({"request": name, "kind": "text", "what": "a run for " + ", ".join(who)})
            for ask in batch:
                for run in by_hash[ask["hash"]]:
                    state[run] = "waiting for Kimodo"
            continue
        for number, ask in enumerate(batch):
            clip = stretch_of(answer, number, ask, sk)
            clip.update({"ask": ask["hash"], "prompt": ask["prompt"], "request": name, "stretch": number, "made_by": answer.get("made_by")})
            for run in by_hash[ask["hash"]]:
                write_json(os.path.join(run, "run", "clip.json"), clip)
    for run, ask in asks.items():
        clip = read_json(os.path.join(run, "run", "clip.json")) or {}
        if clip.get("ask") != ask["hash"]:
            continue
        loop_file = os.path.join(run, "run", "loop.json")
        loop = read_json(loop_file) or {}
        if (loop.get("loop") or {}).get("ask") != ask["hash"]:
            try:
                loop = make_loop(sk, clip, find_loop(sk, clip))
            except ValueError as why:
                state[run] = "no loop: %s" % why
                continue
            loop["loop"].update({"ask": ask["hash"], "prompt": ask["prompt"], "made_by": clip.get("made_by")})
            write_json(loop_file, loop)
            # A new loop: the versions made from the old one are out of date. Gone, the `run` profile makes them again.
            for version in ("lowpoly", "midpoly"):
                for kind in ("glb", "json"):
                    stale = os.path.join(run, "profiles", "%s-run.%s" % (version, kind))
                    if os.path.exists(stale):
                        os.remove(stale)
        state[run] = loop["loop"]
    write_json(os.path.join(cache, "todo.json"), todo, indent=1)
    return {"todo": todo, "asks": asks, "state": state}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folders", nargs="+", help="character run folders (each with a gait.json)")
    parser.add_argument("--cache", help="where requests and answers are kept (default: .run-cache beside the first folder)")
    parser.add_argument("--batch", type=int, default=BATCH, help="characters per Kimodo job, 1 to 8")
    parser.add_argument("--seconds", type=float, default=SECONDS)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.batch <= BATCH or not 3.0 <= args.seconds <= 10.0:
        sys.exit("a job takes 1 to 8 characters, and a sentence makes 3 to 10 seconds")
    folders = [os.path.abspath(f.rstrip("/")) for f in args.folders if os.path.isdir(f)]
    cache = os.path.abspath(args.cache or os.path.join(os.path.dirname(folders[0]), ".run-cache"))
    result = step(folders, cache, size=args.batch, seconds=args.seconds, seed=args.seed)
    for run in folders:
        name = os.path.basename(run)
        ask, state = result["asks"].get(run), result["state"].get(run)
        if ask:
            print(f"RUN {name}: \"{ask['prompt']}\" at {ask['speed_mps']} m/s (Froude {ask['froude']}, leg {ask['leg_m']} m from {ask['leg_from']})")
        if isinstance(state, dict):
            seam = state["seam_before_blend"]
            print(
                f"RUN {name}: loop of {state['frames']} frames ({state['seconds']} s), {state['strides']} strides of {state['stride_frames']}, "
                f"{state['steps_per_minute']} steps a minute, cut at frames {state['first_frame']}-{state['last_frame']}; the two ends were "
                f"{seam['joints_apart_cm']} cm apart (worst joint {seam['worst_joint_cm']} cm) before {state['blend_frames']} frames were eased"
            )
        elif state:
            print(f"RUN {name}: {state}")
    for item in result["todo"]:
        print(f"RUN to make: {item['what']} ({item['request']})")


if __name__ == "__main__":
    main()
