"""The screen-test motions: a small set of whole-body moves, each made once from one sentence, for every rig.

    python3 scripts/motion/screen_motions.py plan [--only id,id] [--takes 5] [--batch 1]
    python3 scripts/motion/screen_motions.py step [--only id,id] [--cache DIR]
    python3 scripts/motion/screen_motions.py status
    python3 scripts/motion/screen_motions.py rehearse <folder> [--only id,id]

motion/library/library.json lists them: an id, one plain sentence in the words
Kimodo knows ("A person slowly squats down as low as they can..."), how many
seconds (at most eight), why it is there (which joints it pushes), and what it
must be seen to do (`asks`: the hips at least this far down, both hands over
the head, a full turn...). They belong to no one character: any member of the
cast, or anyone trying out for a part, plays the same set (`just screen-play`).

Several takes, the best one kept. As with a character's run (run_clip.py), a
sentence gives a motion, not the motion, so each is made five times on
different seeds and every take is scored on what can be measured from its
joints. Lower is better, in rough centimetres of wrongness:

    slide    a foot the model says is down, moving over the floor anyway
    head     the head flung about: turning faster than a person turns it, or
             thrown back past what the sentence asks
    ends     it should start and end standing, and end near the pose it
             started in, so it can be cut, looped or held
    floor    toes through the floor
    asked    each of the motion's `asks` not met (squat depth, hands over the
             head, how far it turned...): 30, and more the further short

All the numbers behind the score are kept, for every take, so it can be seen
what was passed over and why. A take that does everything asked always beats
one that does not.

Jobs. Each take is a `text` job for Kimodo on the RunPod motion worker, the
same kind run_clip.py sends: one sentence, no path (each motion finds its own
way about the spot). A job can carry up to eight sentences one after another
(--batch), but a sentence made as the continuation of another comes out worse
(run_clip.py says how that was found), so one a job is the default. Like
run_clip.py and timeline.py this never calls a worker: `step` writes each
request under the sha256 of its content in the cache and leaves the ones
without an answer in <cache>/todo.json; `baml run screen_motions` sends those
and runs `step` again. An answer in the cache is never asked for again, and a
motion is only made again when its sentence, length, seed or number of takes
changes.

What it keeps, per motion, in motion/library/<id>/:

    motion.json   the kept take as the worker made it (forge-soma-motion/1:
                  30 frames a second, SOMA joints, root, rotations, contacts)
    scores.json   every take's score and measures, and which was kept

`plan` prints every job still to send and what it would cost, and sends
nothing. `rehearse` does the whole thing with the pretend worker the tests use
(scripts/motion/test_screen_motions.py) in a folder of your choosing, so
`just screen-play` can be tried on real characters before anything is paid
for. Nothing it makes is fit to keep.

Plain Python: no Blender, no numpy.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from run_clip import digest, read_json, write_json  # noqa: E402
from soma import Y, Z, Skeleton, heading_of, qconj, qmul, qrot  # noqa: E402
from timeline import by_our_joints, cut  # noqa: E402

LIBRARY = os.path.join(REPO, "motion", "library")
FPS = 30
TAKES = 5  # times each motion is made, on different seeds (run_clip.py's TAKES); the best-scoring take is kept
BATCH = 8  # the most sentences one Kimodo job takes
ALONE = 1  # sentences a job unless asked otherwise: one made after another comes out worse
MOST_SECONDS = 8.0  # a screen-test motion is short; Kimodo makes at most 10 a sentence
STEPS, GUIDANCE = 100, [2.0, 2.0]  # what run_clip.py asks for

# What a take costs on the GPU, from the motion worker's own records of the runs it made (runs/.run-cache,
# Nov 2026, an RTX 4090): a warm job spent 2.35 to 2.67 s, of which 1.61 to 1.75 s was Kimodo making 6 s of
# motion, so about 0.9 s a job plus 0.28 s a second of motion: 2.6 s for six seconds, 3.1 for eight (the README's
# "about three seconds of GPU a take"). A cold worker waited 7.8 s to boot and then spent 49 s loading the
# sentence encoder (Llama 3) before its first job. After the last job the worker idles 60 s before it stops
# (idleTimeout in scripts/create-motion-endpoint.sh), and that is billed too.
JOB_S, PER_MOTION_S = 0.9, 0.28
BOOT_S, ENCODER_S, IDLE_S = 8.0, 49.0, 60.0
FETCH_S = 1800.0  # a volume that has never had Kimodo fetches 17.5 GB first: up to half an hour (README, Setup 6)
WALL_S = 4.5  # seconds from asking to answer for a warm job, sending and polling included (wall_seconds in the records)


def usd_per_s() -> float:
    """The GPU price casting.py assumes (one number for the whole repo, said to be an assumption)."""
    sys.path.insert(0, os.path.join(REPO, "scripts", "casting"))
    try:
        import casting

        return casting.RUNPOD_USD_PER_S
    except Exception:  # noqa: BLE001 - the estimate must never stop a dry run
        return 0.00031


# ---- the list ------------------------------------------------------------------


def load(library: str = LIBRARY) -> dict:
    found = read_json(os.path.join(library, "library.json"))
    if not found:
        raise ValueError(f"no library.json in {library}")
    check(found)
    return found


MEASURES = (
    "weight_shift", "wander", "hips_drop", "turn", "out", "back", "knee_lift", "elbow_bend", "hands_over_head",
    "side_bend", "head_turn", "head_nod", "hand_over_shoulder", "hand_low", "hands_over_shoulders", "hands_behind",
    "feet_apart", "shrug", "bow", "twist", "foot_high",
)


def check(library: dict) -> None:
    """A library that cannot be made is refused here, before anything is sent."""
    seen = set()
    for m in library.get("motions") or []:
        for key in ("id", "name", "sentence", "seconds", "why", "joints", "asks"):
            if not m.get(key):
                raise ValueError(f"motion {m.get('id')!r} has no {key}")
        if m["id"] in seen or not m["id"].replace("-", "").isalnum() or m["id"] != m["id"].lower():
            raise ValueError(f"a motion id is lowercase letters, digits and dashes, and used once: {m['id']!r}")
        seen.add(m["id"])
        if not 2.0 <= float(m["seconds"]) <= MOST_SECONDS:
            raise ValueError(f"{m['id']}: a screen-test motion lasts 2 to {MOST_SECONDS:g} seconds")
        if not m["sentence"].startswith("A person ") or not m["sentence"].endswith("."):
            raise ValueError(f"{m['id']}: Kimodo's sentences are about \"A person ...\" and end with a full stop")
        for ask in m["asks"]:
            if ask.get("measure") not in MEASURES or ("at_least" in ask) == ("at_most" in ask):
                raise ValueError(f"{m['id']}: an ask is a known measure with at_least or at_most: {ask}")
    if not seen:
        raise ValueError("the library has no motions")


def chosen(library: dict, only=None) -> list:
    motions = library["motions"]
    if not only:
        return motions
    wanted = [w for w in only if w]
    unknown = sorted(set(wanted) - {m["id"] for m in motions})
    if unknown:
        raise ValueError("no such motion: %s (the library has %s)" % (", ".join(unknown), ", ".join(m["id"] for m in motions)))
    return [m for m in motions if m["id"] in wanted]


def ask_for(motion: dict, takes: int = TAKES) -> dict:
    """Everything that decides a motion. Its `hash` is the kept clip's fingerprint."""
    ask = {
        "prompt": motion["sentence"],
        "frames": int(round(float(motion["seconds"]) * FPS)),
        # Each motion rolls its own dice, the same ones every time (as run_clip.py does for each character).
        "seed": int(digest(motion["id"])[:6], 16) % 100000,
        "steps": STEPS,
        "guidance": list(GUIDANCE),
        "takes": int(takes),
    }
    return {"id": motion["id"], **ask, "hash": digest(ask)}


def batch_request(asks: list) -> dict:
    """One Kimodo job: these sentences one after the other, on the first one's seed. No path: each finds its own way."""
    first = asks[0]
    return {"kind": "text", "prompts": [{"text": a["prompt"], "frames": a["frames"]} for a in asks],
            "seed": first["seed"], "steps": first["steps"], "guidance": first["guidance"], "tidy": True}


def batches(wanted: list, size: int = ALONE) -> list:
    """The takes as jobs. A job has one seed, so only takes of the same number share one."""
    groups = {}
    for ask in wanted:
        groups.setdefault(ask["take"] if size > 1 else (ask["id"], ask["take"]), []).append(ask)
    out = []
    for group in groups.values():
        out += [group[i : i + size] for i in range(0, len(group), size)]
    return out


def takes_wanted(asks: list) -> list:
    return [dict(ask, seed=ask["seed"] + take, take=take) for ask in asks for take in range(ask["takes"])]


# ---- measuring a take ------------------------------------------------------------


def unwrap(angles: list) -> list:
    out = list(angles)
    for f in range(1, len(out)):
        out[f] -= 360.0 * round((out[f] - out[f - 1]) / 360.0)
    return out


def angles_of(q: tuple) -> tuple:
    """(yaw, pitch, roll) in degrees of a turn: yaw + toward the left, pitch + forward (nose down, chest over), roll + toward the right."""
    f, u = qrot(q, Z), qrot(q, Y)
    yaw = math.degrees(math.atan2(f[0], f[2]))
    pitch = math.degrees(math.atan2(-f[1], math.hypot(f[0], f[2])))
    roll = math.degrees(math.atan2(-u[0], u[1]))
    return yaw, pitch, roll


def body_frame(heading: float, v: tuple) -> tuple:
    """A world vector seen from a body facing `heading`: x to its left, y up, z ahead."""
    h = math.radians(heading)
    return (v[0] * math.cos(h) - v[2] * math.sin(h), v[1], v[0] * math.sin(h) + v[2] * math.cos(h))


def frames_of(sk: Skeleton, motion: dict) -> list:
    """Per frame: every joint's world position and rotation, and the turn of each from its rest."""
    joints = len(sk.joints)
    out = []
    for root, row in zip(motion["root"], motion["rotations"]):
        pos, rot = sk.fk(root, [tuple(row[4 * j : 4 * j + 4]) for j in range(joints)])
        out.append((pos, [qmul(rot[j], qconj(sk.rest_world_rot[j])) for j in range(joints)]))
    return out


def relative(turns: list, child: int, parent: int) -> tuple:
    return qmul(qconj(turns[parent]), turns[child])


def measures(sk: Skeleton, motion: dict) -> dict:
    """Everything the asks and the score read, from the joints. Lengths are in hip heights of the model's body."""
    i = sk.index
    unit = sk.rest_world_pos[i["LeftLeg"]][1]
    rest_hips = sk.rest_world_pos[0][1]
    rest_knee = sk.rest_world_pos[i["LeftShin"]][1]
    frames = frames_of(sk, motion)
    count = len(frames)
    headings = unwrap([heading_of(t[0]) for _, t in frames])
    start = frames[0][0][0]
    out = {}

    def flat(a, b):
        return math.hypot(a[0] - b[0], a[2] - b[2])

    away = [flat(p[0], start) for p, _ in frames]
    out["wander"] = max(away) / unit
    out["out"] = max(away) / unit
    out["back"] = away[-1] / max(max(away), 1e-6)
    out["turn"] = max(headings) - min(headings)
    out["hips_drop"] = max(rest_hips - p[0][1] for p, _ in frames) / unit
    # Weight from foot to foot: the hips over the feet, side to side, in the body's own frame.
    side = [body_frame(h, tuple(p[0][k] - (p[i["LeftFoot"]][k] + p[i["RightFoot"]][k]) / 2.0 for k in range(3)))[0] for (p, _), h in zip(frames, headings)]
    out["weight_shift"] = (max(side) - min(side)) / unit
    out["knee_lift"] = min(max(p[i[s + "Shin"]][1] - rest_knee for p, _ in frames) for s in ("Left", "Right")) / unit

    def bend(p, s):
        a, b, c = p[i[s + "Arm"]], p[i[s + "ForeArm"]], p[i[s + "Hand"]]
        u = tuple(b[k] - a[k] for k in range(3))
        v = tuple(c[k] - b[k] for k in range(3))
        cos = sum(x * y for x, y in zip(u, v)) / max(1e-9, math.hypot(*u) * math.hypot(*v))
        return math.degrees(math.acos(max(-1.0, min(1.0, cos))))

    out["elbow_bend"] = min(max(bend(p, s) for p, _ in frames) for s in ("Left", "Right"))
    head = i["Head"]
    out["hands_over_head"] = max(min(p[i["LeftHand"]][1], p[i["RightHand"]][1]) - p[head][1] for p, _ in frames) / unit
    out["hand_over_shoulder"] = min(max(p[i[s + "Hand"]][1] - p[i[s + "Arm"]][1] for p, _ in frames) for s in ("Left", "Right")) / unit
    out["hands_over_shoulders"] = out["hand_over_shoulder"]
    out["hand_low"] = min(min(p[i["LeftHand"]][1], p[i["RightHand"]][1]) for p, _ in frames) / unit
    chest = i["Chest"]

    def behind(p, h, s):
        return -body_frame(h, tuple(p[i[s + "Hand"]][k] - p[chest][k] for k in range(3)))[2]

    out["hands_behind"] = min(max(behind(p, h, s) for (p, _), h in zip(frames, headings)) for s in ("Left", "Right")) / unit
    out["feet_apart"] = max(abs(body_frame(h, tuple(p[i["LeftFoot"]][k] - p[i["RightFoot"]][k] for k in range(3)))[2]) for (p, _), h in zip(frames, headings)) / unit
    out["foot_high"] = max(max(p[i["LeftToeBase"]][1], p[i["RightToeBase"]][1]) for p, _ in frames) / unit
    # The spine on the hips, and the head on the chest: each way, the lesser of the two sides.
    spine = [angles_of(relative(t, chest, 0)) for _, t in frames]
    out["twist"] = min(max(a[0] for a in spine), -min(a[0] for a in spine))
    out["side_bend"] = min(max(a[2] for a in spine), -min(a[2] for a in spine))
    out["bow"] = max(angles_of(t[chest])[1] for _, t in frames)
    neck = [angles_of(relative(t, head, chest)) for _, t in frames]
    out["head_turn"] = min(max(a[0] for a in neck), -min(a[0] for a in neck))
    out["head_nod"] = max(a[1] for a in neck) - min(a[1] for a in neck)
    # A shrug: the shoulders lifted on the chest, in the chest's own frame (so a bow does not count).
    def lift(f):
        p, t = frames[f]
        mid = tuple((p[i["LeftArm"]][k] + p[i["RightArm"]][k]) / 2.0 - p[chest][k] for k in range(3))
        return qrot(qconj(t[chest]), mid)[1]
    out["shrug"] = (max(lift(f) for f in range(count)) - lift(0)) / unit

    # ---- what every take is scored on, whatever it was asked for ----
    # Feet: while the model says a heel (or a toe) is down, how far the ankle (or the ball of the foot) moves over the
    # floor in that stretch. Heel and toe apart, so a heel rolling up off a planted toe is not a slide.
    worst, slid = 0.0, []
    for col, joint in enumerate(("LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase")):
        j = i[joint]
        f = 0
        while f < count:
            if motion["contacts"][f][col] < 0.5:
                f += 1
                continue
            first = f
            while f < count and motion["contacts"][f][col] >= 0.5:
                f += 1
            if f - first >= 4:
                spot = frames[first][0][j]
                drift = max(flat(frames[g][0][j], spot) for g in range(first, f))
                slid.append(drift)
                worst = max(worst, drift)
    out["slide_cm"] = round(100.0 * worst, 2)
    out["slide_typical_cm"] = round(100.0 * sorted(slid)[len(slid) // 2], 2) if slid else 0.0
    # The head on the chest: how fast it turns at its quickest, and how far it is thrown back (chin up).
    speeds = [math.degrees(2.0 * math.acos(min(1.0, abs(qmul(qconj(relative(frames[f][1], head, chest)), relative(frames[f + 1][1], head, chest))[3])))) * FPS
              for f in range(count - 1)]
    speeds.sort()
    out["head_speed_deg_s"] = round(speeds[int(0.98 * (len(speeds) - 1))], 1) if speeds else 0.0  # all but the quickest 2%: one bad frame is not a throw
    out["chin_up_deg"] = round(max(0.0, -min(a[1] for a in neck)), 1)
    out["floor_cm"] = round(100.0 * max(0.0, -min(min(p[i["LeftToeBase"]][1], p[i["RightToeBase"]][1]) - 0.005 for p, _ in frames)), 2)
    # The ends: standing at both, and the last pose near the first (every joint about the hips, in the body's frame).
    def posture(f):
        p, _ = frames[f]
        return [body_frame(headings[f], tuple(q[k] - p[0][k] for k in range(3))) for q in p]
    a, b = posture(0), posture(count - 1)
    out["ends_apart_cm"] = round(100.0 * math.sqrt(sum(math.dist(x, y) ** 2 for x, y in zip(a, b)) / len(a)), 2)
    out["starts_standing"] = (rest_hips - frames[0][0][0][1]) / unit < 0.12
    out["ends_standing"] = (rest_hips - frames[-1][0][0][1]) / unit < 0.12
    return {k: round(v, 3) if isinstance(v, float) else v for k, v in out.items()}


HEAD_FAST_DEG_S = 400.0  # a head turned quickly by a person; faster than this is flung
CHIN_UP_DEG = 40.0  # thrown back past this, unless the sentence asks for a look up (then 60)


def score_take(sk: Skeleton, motion: dict, asks: list) -> dict:
    """One take, weighed. Lower is better: rough centimetres of wrongness. Every measure is kept beside it."""
    m = measures(sk, motion)
    chin_limit = 60.0 if any(a["measure"] == "head_nod" for a in asks) else CHIN_UP_DEG
    missed = []
    for ask in asks:
        got = m[ask["measure"]]
        if "at_least" in ask and got < ask["at_least"]:
            missed.append({**ask, "got": got, "short": round((ask["at_least"] - got) / max(abs(ask["at_least"]), 1e-6), 3)})
        elif "at_most" in ask and got > ask["at_most"]:
            missed.append({**ask, "got": got, "short": round((got - ask["at_most"]) / max(abs(ask["at_most"]), 1e-6), 3)})
    parts = {
        "slide": round(max(0.0, m["slide_cm"] - 1.0), 2),
        "head": round(0.05 * max(0.0, m["head_speed_deg_s"] - HEAD_FAST_DEG_S) + 0.5 * max(0.0, m["chin_up_deg"] - chin_limit), 2),
        "ends": round(0.5 * max(0.0, m["ends_apart_cm"] - 6.0) + (0 if m["starts_standing"] else 15) + (0 if m["ends_standing"] else 15), 2),
        "floor": round(m["floor_cm"], 2),
        "asked": round(sum(30.0 + 50.0 * min(2.0, miss["short"]) for miss in missed), 2),
    }
    return {"score": round(sum(parts.values()), 2), "does_what_was_asked": not missed, "parts": parts, "missed": missed, "measures": m}


# ---- one pass ---------------------------------------------------------------------


def stretch_of(sk: Skeleton, answer: dict, number: int, ask: dict) -> dict:
    """One sentence's frames out of a job's answer, joints in the skeleton's order."""
    motion = by_our_joints(sk, answer)
    segments = answer.get("segments") or []
    if number >= len(segments):
        raise ValueError(f"the answer has {len(segments)} stretches, wanted number {number + 1}")
    first, last = int(segments[number]["first_frame"]), int(segments[number]["last_frame"])
    if last - first + 1 != ask["frames"] or last >= len(motion["root"]):
        raise ValueError(f"stretch {number + 1} is frames {first}-{last}, wanted {ask['frames']} frames")
    clip = cut(motion, first, last)
    # A stretch after the first starts wherever the one before ended: bring it back to the origin, facing ahead.
    if first:
        from timeline import facing, moved

        turned = moved(clip, -facing(sk, clip, 0), 0.0, 0.0)
        clip = moved(turned, 0.0, -turned["root"][0][0], -turned["root"][0][2])
    return clip


def step(library: str = LIBRARY, cache: str = None, sk: Skeleton = None, only=None, takes: int = None, size: int = ALONE) -> dict:
    """Do as much as the answers on hand allow. Returns the jobs still to send and where each motion stands."""
    sk = sk or Skeleton.load()
    cache = cache or os.path.join(library, ".cache")
    os.makedirs(cache, exist_ok=True)
    lib = load(library)
    asks = {m["id"]: ask_for(m, takes or lib.get("takes") or TAKES) for m in chosen(lib, only)}
    by_id = {m["id"]: m for m in lib["motions"]}
    state, wanting = {}, []
    for mid, ask in asks.items():
        kept = read_json(os.path.join(library, mid, "motion.json")) or {}
        if kept.get("ask") == ask["hash"]:
            state[mid] = "made"
        else:
            wanting.append(ask)
    todo, made, jobs = [], {}, []
    for batch in batches(takes_wanted(wanting), size):
        request = batch_request(batch)
        name = digest(request)
        if not os.path.exists(os.path.join(cache, name + ".request.json")):
            write_json(os.path.join(cache, name + ".request.json"), request)
        answer = read_json(os.path.join(cache, name + ".json"))
        jobs.append({"request": name, "takes": [{"id": a["id"], "take": a["take"], "seed": a["seed"], "frames": a["frames"], "prompt": a["prompt"]} for a in batch],
                     "answered": answer is not None})
        if answer is None:
            what = ", ".join("%s (take %d)" % (a["id"], a["take"] + 1) for a in batch)
            todo.append({"request": name, "kind": "text", "what": "screen-test motion " + what})
            for a in batch:
                state[a["id"]] = "waiting for Kimodo"
            continue
        for number, a in enumerate(batch):
            clip = stretch_of(sk, answer, number, a)
            clip.update({"ask": a["hash"], "prompt": a["prompt"], "request": name, "stretch": number, "take": a["take"], "seed": a["seed"], "made_by": answer.get("made_by")})
            made.setdefault(a["id"], {})[a["take"]] = clip
    for mid, clips in made.items():
        ask = asks[mid]
        if len(clips) < ask["takes"]:
            continue
        scores = [dict(score_take(sk, clips[t], by_id[mid]["asks"]), take=t, seed=clips[t]["seed"]) for t in sorted(clips)]
        # One that does everything asked beats one that does not; then the lowest score; then the first.
        best = min(scores, key=lambda s: (not s["does_what_was_asked"], s["score"], s["take"]))
        kept = dict(clips[best["take"]], id=mid, name=by_id[mid]["name"], seconds=round(ask["frames"] / FPS, 3))
        write_json(os.path.join(library, mid, "motion.json"), kept)
        write_json(os.path.join(library, mid, "scores.json"), {
            "id": mid, "prompt": ask["prompt"], "ask": ask["hash"], "kept": best["take"], "does_what_was_asked": best["does_what_was_asked"],
            "asks": by_id[mid]["asks"], "takes": scores}, indent=1)
        state[mid] = "made"
    write_json(os.path.join(cache, "todo.json"), todo, indent=1)
    return {"todo": todo, "jobs": jobs, "asks": asks, "state": state}


# ---- what it costs ---------------------------------------------------------------


def kimodo_has_answered(runs: str = None) -> bool:
    """Whether Kimodo has made anything on this volume before (a character's run): then nothing is fetched first."""
    for loop in glob.glob(os.path.join(runs or os.path.join(REPO, "runs"), "*", "run", "loop.json"))[:1]:
        return "Kimodo" in json.dumps((read_json(loop) or {}).get("loop", {}).get("made_by") or {})
    return False


def estimate(jobs: list, answered_before: bool = None, runs: str = None) -> dict:
    """What sending these jobs would cost, low (a warm worker) to high (a cold one that loads the encoder first)."""
    price = usd_per_s()
    sending = [j for j in jobs if not j["answered"]]
    seconds = sum(t["frames"] / FPS for j in sending for t in j["takes"])
    work = len(sending) * JOB_S + PER_MOTION_S * seconds
    answered_before = kimodo_has_answered(runs) if answered_before is None else answered_before
    low = work + IDLE_S if sending else 0.0
    high = low + BOOT_S + ENCODER_S if sending else 0.0
    return {
        "jobs": len(sending), "takes": sum(len(j["takes"]) for j in sending), "seconds_of_motion": round(seconds, 1),
        "gpu_s": {"takes": round(work, 1), "idle_after": IDLE_S if sending else 0.0, "cold_start": BOOT_S, "encoder_load": ENCODER_S},
        "low_usd": round(low * price, 3), "high_usd": round(high * price, 3), "usd_per_s": price,
        "wall_minutes": round((len(sending) * WALL_S + (BOOT_S + ENCODER_S if sending else 0)) / 60.0, 1),
        "kimodo_on_volume": answered_before,
        "fetch_usd": None if answered_before else round(FETCH_S * price, 2),
    }


def plan_lines(result: dict, cost: dict, command: str) -> list:
    lines = []
    sending = [j for j in result["jobs"] if not j["answered"]]
    for n, job in enumerate(sending, 1):
        for t in job["takes"]:
            lines.append('SCREEN job %d/%d (%s): %s take %d, seed %d, %g s: "%s"' % (
                n, len(sending), job["request"], t["id"], t["take"] + 1, t["seed"], t["frames"] / FPS, t["prompt"]))
    made = sorted(k for k, v in result["state"].items() if v == "made")
    if made:
        lines.append("SCREEN already made, not sent again: %s" % ", ".join(made))
    if not sending:
        lines.append("SCREEN nothing to send: every motion asked for is made (or answered and waiting for `step`)")
        return lines
    lines.append("SCREEN %d jobs, %d takes, %.0f s of motion; about %.0f s of GPU for the takes (%.1f s a job and %.2f s a second of motion, from the worker's own records)" % (
        cost["jobs"], cost["takes"], cost["seconds_of_motion"], cost["gpu_s"]["takes"], JOB_S, PER_MOTION_S))
    lines.append("SCREEN cost: about $%.2f with the worker already awake, $%.2f if it has to wake up and load the sentence encoder first (+%.0f s boot, +%.0f s encoder), counting the %.0f s it idles after the last job; at an assumed $%.5f a GPU second (casting.py's RUNPOD_USD_PER_S: check your bill). About %.0f minutes start to end." % (
        cost["low_usd"], cost["high_usd"], BOOT_S, ENCODER_S, IDLE_S, cost["usd_per_s"], max(1.0, cost["wall_minutes"])))
    if cost["kimodo_on_volume"]:
        lines.append("SCREEN Kimodo has made runs on this volume before, so nothing should need fetching (if it does, `just text-info` first: up to half an hour)")
    else:
        lines.append("SCREEN no sign Kimodo has run on this volume: run `just text-info` first (it fetches 17.5 GB once, up to half an hour of GPU, about $%.2f)" % cost["fetch_usd"])
    lines.append("SCREEN to send it: %s" % command)
    return lines


# ---- rehearsing with the pretend worker --------------------------------------------


def rehearse(folder: str, only=None, takes: int = None, log=print) -> dict:
    """The library made in `folder` from the pretend worker's answers: a copy of library.json, a cache, the kept motions."""
    import test_screen_motions

    if os.path.abspath(folder) == os.path.abspath(LIBRARY):
        raise ValueError("rehearse in a folder of your own, not motion/library: pretend answers must never be kept as real ones")
    os.makedirs(folder, exist_ok=True)
    shutil.copyfile(os.path.join(LIBRARY, "library.json"), os.path.join(folder, "library.json"))
    sk = Skeleton.load()
    for _ in range(3):
        result = step(folder, sk=sk, only=only, takes=takes)
        if not result["todo"]:
            break
        cache = os.path.join(folder, ".cache")
        for item in result["todo"]:
            request = read_json(os.path.join(cache, item["request"] + ".request.json"))
            write_json(os.path.join(cache, item["request"] + ".json"), test_screen_motions.pretend(request))
    for mid, state in sorted(result["state"].items()):
        log("SCREEN rehearsed %s: %s" % (mid, state))
    return result


# ---- the command line ---------------------------------------------------------------


def status_lines(library: str = LIBRARY) -> list:
    lines = []
    lib = load(library)
    for m in lib["motions"]:
        ask = ask_for(m, lib.get("takes") or TAKES)
        kept = read_json(os.path.join(library, m["id"], "motion.json")) or {}
        scores = read_json(os.path.join(library, m["id"], "scores.json")) or {}
        if kept.get("ask") != ask["hash"]:
            lines.append("SCREEN %-15s not made yet%s" % (m["id"], " (made from an older sentence)" if kept else ""))
            continue
        told = ", ".join("take %d %s%s" % (s["take"] + 1, s["score"], "" if s["does_what_was_asked"] else " (misses %s)" % "/".join(x["measure"] for x in s["missed"])) for s in scores.get("takes") or [])
        lines.append("SCREEN %-15s kept take %d of %d%s; scores, lower is better: %s" % (
            m["id"], scores.get("kept", 0) + 1, len(scores.get("takes") or []), "" if scores.get("does_what_was_asked") else " (NONE did all it was asked: look at it)", told))
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("what", choices=("plan", "step", "status", "rehearse"))
    parser.add_argument("folder", nargs="?", help="rehearse: the folder to rehearse in (never motion/library)")
    parser.add_argument("--only", default="", help="motion ids, joined by commas (default: all of them)")
    parser.add_argument("--library", default=LIBRARY)
    parser.add_argument("--cache", help="where requests and answers are kept (default: <library>/.cache)")
    parser.add_argument("--runs", help="plan: the folder of runs, to see whether Kimodo has made a run on this volume before (default: runs/)")
    parser.add_argument("--takes", type=int, help="times each motion is made, on different seeds (default: library.json's takes)")
    parser.add_argument("--batch", type=int, default=ALONE, help="sentences a job, 1 to 8 (more is one job instead of several, and worse)")
    args = parser.parse_args(argv)
    only = [w for w in args.only.split(",") if w]
    if not 1 <= args.batch <= BATCH or (args.takes is not None and not 1 <= args.takes <= 8):
        sys.exit("a job takes 1 to 8 sentences, and a motion is made 1 to 8 times")
    try:
        if args.what == "status":
            print("\n".join(status_lines(args.library)))
            return 0
        if args.what == "rehearse":
            if not args.folder:
                sys.exit("rehearse needs a folder of your own")
            rehearse(args.folder, only, args.takes)
            print("\n".join(status_lines(args.folder)))
            return 0
        result = step(args.library, args.cache, only=only, takes=args.takes, size=args.batch)
    except ValueError as refused:
        print("screen-motions: %s" % refused, file=sys.stderr)
        return 2
    if args.what == "plan":
        cost = estimate(result["jobs"], runs=args.runs)
        command = "just screen-motions go" + (" " + ",".join(only) if only else "")
        print("\n".join(plan_lines(result, cost, command)))
        print("RESULT " + json.dumps({"jobs": [j for j in result["jobs"] if not j["answered"]], "cost": cost, "dry_run": True}))
        return 0
    for mid, state in sorted(result["state"].items()):
        print("SCREEN %s: %s" % (mid, state))
    for item in result["todo"]:
        print("SCREEN to make: %s (%s)" % (item["what"], item["request"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
