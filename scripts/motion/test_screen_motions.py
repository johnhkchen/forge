"""Offline tests for the screen-test motions: the list, the jobs, the scores, the keeping, the cost, playing them.

    python3 scripts/motion/test_screen_motions.py

No GPU, no worker, no Blender. A pretend worker stands in for Kimodo: for each
sentence in the library it makes a stick figure doing that move (a squat, a
turn on the spot, a walk out and back...) built from the SOMA skeleton, its
legs solved to where its feet stand. Each seed is one of five takes: one done
well, one done by half, one whose planted feet slide, one that throws its head
back, one that never comes back to standing. The scoring has to keep the one
done well. Nobody would want to watch any of them; none of it comes from
anyone's motion data. `screen_motions.py rehearse` uses the same pretend
worker to try `just screen-play` on real characters before anything is paid.
"""

from __future__ import annotations

import io
import json
import math
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import screen_motions  # noqa: E402
from run_clip import digest  # noqa: E402
from soma import X, Y, Z, Skeleton, add, cross, dot, length, qaxis, qconj, qmul, qnorm, qrot, scale, sub, unit, yaw  # noqa: E402
from timeline import CONTACT_ORDER  # noqa: E402

SK = Skeleton.load()
FPS = 30
I = SK.index
THIGH = length(sub(SK.rest_world_pos[I["LeftShin"]], SK.rest_world_pos[I["LeftLeg"]]))
SHIN = length(sub(SK.rest_world_pos[I["LeftFoot"]], SK.rest_world_pos[I["LeftShin"]]))
REST_HIPS = SK.rest_world_pos[0][1]
ANKLE_Y = SK.rest_world_pos[I["LeftFoot"]][1]
TOE_Y = SK.rest_world_pos[I["LeftToeBase"]][1]
VARIANTS = ("good", "shallow", "slide", "head", "ends")


# ---- the pretend body ----------------------------------------------------------------


def turned(joint: str, axis, degrees: float) -> tuple:
    """A joint's local rotation when it is turned from rest about an axis of the body (as it lies at rest)."""
    j = I[joint]
    world = SK.rest_world_rot[j]
    return qmul(SK.rest_rot[j], qmul(qconj(world), qmul(qaxis(axis, degrees), world)))


def shortest(a: tuple, b: tuple) -> tuple:
    """The smallest turn taking direction a onto direction b, as [x, y, z, w]."""
    a, b = unit(a), unit(b)
    c, w = cross(a, b), 1.0 + dot(a, b)
    if w < 1e-6:  # opposite: any axis square to a
        c = unit(cross(a, X if abs(a[0]) < 0.9 else Y))
        return (c[0], c[1], c[2], 0.0)
    return qnorm((c[0], c[1], c[2], w))


def smooth(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def bump(t: float, start: float, end: float, ramp: float = 0.08) -> float:
    """0 before start, up to 1 over `ramp`, held, back down to 0 by end."""
    return smooth((t - start) / ramp) * (1.0 - smooth((t - end + ramp) / ramp))


def body_to_world(heading: float, v) -> tuple:
    return qrot(yaw(heading), tuple(v))


def arm_dir(side: str, elevation: float, forward: float = 0.0) -> tuple:
    """An arm's direction in the body's frame: elevation 0 hangs down, 90 out to the side, 180 straight up; forward swings it ahead (+) or behind (-)."""
    out = 1.0 if side == "Left" else -1.0
    e, f = math.radians(elevation), math.radians(forward)
    return (out * math.sin(e) * math.cos(f), -math.cos(e) * math.cos(f), math.sin(f))


def leg_ik(hip: tuple, target: tuple, forward: tuple) -> tuple:
    """Thigh and shin directions that put the ankle on `target` (or as near as the leg reaches), the knee ahead."""
    d = sub(target, hip)
    reach = min(length(d), 0.995 * (THIGH + SHIN))
    u = unit(d)
    pole = sub(forward, scale(u, dot(forward, u)))
    pole = unit(pole) if length(pole) > 1e-6 else unit(cross(u, X))
    cos1 = max(-1.0, min(1.0, (THIGH ** 2 + reach ** 2 - SHIN ** 2) / (2.0 * THIGH * reach)))
    thigh = add(scale(u, cos1), scale(pole, math.sqrt(max(0.0, 1.0 - cos1 * cos1))))
    knee = add(hip, scale(thigh, THIGH))
    return thigh, unit(sub(target, knee))


def pose(p: dict) -> tuple:
    """One frame of the pretend body: (root, local rotations). p says where the hips are and how each part is held."""
    heading = p.get("heading", 0.0)
    local = [tuple(q) for q in SK.rest_rot]
    local[0] = qmul(yaw(heading), SK.rest_rot[0])
    pitch, roll, twist = p.get("spine", (0.0, 0.0, 0.0))
    for joint in ("Spine1", "Spine2", "Chest"):
        q = turned(joint, Y, twist / 3.0)
        q = qmul(q, qmul(qconj(SK.rest_rot[I[joint]]), turned(joint, X, pitch / 3.0)))
        local[I[joint]] = qmul(q, qmul(qconj(SK.rest_rot[I[joint]]), turned(joint, Z, roll / 3.0)))
    nod, look = p.get("neck", (0.0, 0.0))
    for joint, share in (("Neck1", 0.4), ("Head", 0.6)):
        q = turned(joint, Y, look * share)
        local[I[joint]] = qmul(q, qmul(qconj(SK.rest_rot[I[joint]]), turned(joint, X, nod * share)))
    shrug = p.get("shrug", 0.0)
    local[I["LeftShoulder"]] = turned("LeftShoulder", Z, shrug)
    local[I["RightShoulder"]] = turned("RightShoulder", Z, -shrug)
    root = (p.get("x", 0.0), REST_HIPS - p.get("drop", 0.0), p.get("z", 0.0))
    pos, rot = SK.fk(root, local)

    def aim(chain: list, dirs: list) -> None:
        parent_rot = rot[SK.parents[I[chain[0]]]]
        for (joint, child), want in zip(zip(chain, chain[1:]), dirs):
            j = I[joint]
            world = qmul(parent_rot, local[j])
            now = qrot(world, SK.rest_pos[I[child]])
            world = qmul(shortest(now, want), world)
            local[j] = qmul(qconj(parent_rot), world)
            parent_rot = world

    forward = body_to_world(heading, Z)
    for side in ("Left", "Right"):
        upper, fore = p.get("arms", {}).get(side) or (arm_dir(side, 12), arm_dir(side, 6, 12))
        aim([side + "Arm", side + "ForeArm", side + "Hand"], [body_to_world(heading, upper), body_to_world(heading, fore)])
        rest_ankle = SK.rest_world_pos[I[side + "Foot"]]
        target = p.get("feet", {}).get(side) or plant(0.0, 0.0, heading, side)  # unless told, a foot stands where it started
        thigh, shin = leg_ik(pos[I[side + "Leg"]], target, forward)
        toe = unit(body_to_world(p.get("toes", {}).get(side, heading), sub(SK.rest_world_pos[I[side + "ToeBase"]], rest_ankle)))  # a planted foot keeps its own way
        aim([side + "Leg", side + "Shin", side + "Foot", side + "ToeBase"], [thigh, shin, toe])
    return root, local


def plant(root_x: float, root_z: float, heading: float, side: str, lead: float = 0.0, lift: float = 0.0) -> tuple:
    """Where an ankle stands for a body at (x, z) facing `heading`: under its own hip, `lead` ahead, `lift` up."""
    rest = SK.rest_world_pos[I[side + "Foot"]]
    v = body_to_world(heading, (rest[0], 0.0, rest[2] + lead))
    return (root_x + v[0], ANKLE_Y + lift, root_z + v[2])


def stepping(ground, frames: int, step_frames: int = 14) -> list:
    """Feet that step where the body goes: per frame {"feet": {side: ankle}, "toes": {side: heading}}. ground(f) -> (x, z,
    heading). Each foot is planted where it last landed, facing the way it landed, and moves (lifted, along a straight
    line) only in its own half of each stride."""
    out = []
    landed = {side: plant(*ground(0), side) for side in ("Left", "Right")}
    facing = {side: ground(0)[2] for side in ("Left", "Right")}
    for f in range(frames):
        feet, toes = {}, {}
        for n, side in enumerate(("Left", "Right")):
            swing = (f // step_frames) % 2 == n
            start = (f // step_frames) * step_frames
            end = min(frames - 1, start + step_frames)
            x, z, h = ground(end)
            x0, z0, h0 = ground(start)
            goal = plant(x, z, h, side, lead=0.5 * math.hypot(x - x0, z - z0))
            if swing and (math.dist(goal, landed[side]) > 0.02 or abs(h - facing[side]) > 3.0):  # a step only where there is somewhere to go
                u = (f - start + 1) / step_frames
                s, a = smooth(u), landed[side]
                where = tuple(a[k] + (goal[k] - a[k]) * s for k in range(3))
                feet[side] = (where[0], where[1] + 0.09 * math.sin(math.pi * u), where[2])
                toes[side] = facing[side] + (h - facing[side]) * s
                if f - start + 1 == step_frames:
                    landed[side], facing[side] = goal, h
            else:
                feet[side], toes[side] = landed[side], facing[side]
        out.append({"feet": feet, "toes": toes})
    return out


def hang(side: str) -> tuple:
    return arm_dir(side, 12), arm_dir(side, 6, 12)


def choreography(motion_id: str, frames: int, amp: float) -> list:
    """Per frame, how the pretend body is held for one library motion, done at `amp` of its full size."""
    out = []
    t_of = lambda f: f / max(1, frames - 1)  # noqa: E731
    if motion_id == "walk-turn-back":
        far = 1.8 * amp

        def ground(f):
            t = t_of(f)
            if t < 0.4:
                return 0.0, far * smooth(t / 0.4), 0.0
            if t < 0.6:
                return 0.0, far, 180.0 * amp * smooth((t - 0.4) / 0.2)
            return 0.0, far * (1.0 - smooth((t - 0.6) / 0.38)), 180.0 * amp
        feet = stepping(ground, frames)
        for f in range(frames):
            x, z, h = ground(f)
            swing = 18.0 * math.sin(2 * math.pi * f / 28.0) * (1.0 if 0.03 < t_of(f) < 0.97 else 0.0)
            out.append({"x": x, "z": z, "heading": h, "drop": 0.07, **feet[f],
                        "arms": {"Left": (arm_dir("Left", 10, swing), arm_dir("Left", 6, swing + 15)), "Right": (arm_dir("Right", 10, -swing), arm_dir("Right", 6, -swing + 15))}})
        return out
    if motion_id == "turn-circle":
        def ground(f):
            return 0.0, 0.0, 360.0 * amp * smooth((t_of(f) - 0.08) / 0.84)
        feet = stepping(ground, frames, 10)
        return [{"heading": ground(f)[2], "drop": 0.04, **feet[f]} for f in range(frames)]
    for f in range(frames):
        t = t_of(f)
        p = {"drop": 0.015}
        if motion_id == "stand-easy":
            p["x"] = 0.05 * amp * math.sin(2 * math.pi * 1.4 * t)
        elif motion_id == "jog-in-place":
            phase = 2 * math.pi * 1.35 * f / FPS
            on = bump(t, 0.05, 0.95, 0.06)
            lifts = {"Left": max(0.0, math.sin(phase)), "Right": max(0.0, -math.sin(phase))}
            p.update(drop=0.03 - 0.015 * math.cos(2 * phase) * on,
                     feet={s: plant(0.0, 0.0, 0.0, s, lead=0.1 * lifts[s] * on, lift=0.6 * amp * lifts[s] * on) for s in lifts})
            pump = 30.0 * math.sin(phase) * on
            p["arms"] = {"Left": (arm_dir("Left", 15, -pump), arm_dir("Left", 70 * on + 6, 80 * on)), "Right": (arm_dir("Right", 15, pump), arm_dir("Right", 70 * on + 6, 80 * on))}
        elif motion_id == "deep-squat":
            b = bump(t, 0.15, 0.85, 0.2)
            p.update(drop=0.45 * amp * b, spine=(25.0 * b * amp, 0.0, 0.0))
            p["arms"] = {s: (arm_dir(s, 12 + 70 * b * amp, 70 * b), arm_dir(s, 6 + 70 * b * amp, 80 * b)) for s in ("Left", "Right")}
        elif motion_id == "reach-stretch":
            up = bump(t, 0.08, 0.92, 0.12)
            lean = 20.0 * (bump(t, 0.35, 0.6, 0.08) - bump(t, 0.6, 0.85, 0.08))
            p["spine"] = (0.0, -lean * amp, 0.0)
            e = 12 + 158 * amp * up
            p["arms"] = {s: (arm_dir(s, e), arm_dir(s, e)) for s in ("Left", "Right")}
        elif motion_id == "look-around":
            look = 55.0 * (bump(t, 0.08, 0.3) - bump(t, 0.33, 0.55))
            nod = 35.0 * (bump(t, 0.78, 0.92) - bump(t, 0.6, 0.75))
            p["neck"] = (nod * amp, look * amp)
        elif motion_id == "wave-both":
            arms = {}
            for side, a, b in (("Right", 0.06, 0.46), ("Left", 0.54, 0.94)):
                up = bump(t, a, b, 0.08)
                wag = 25.0 * math.sin(2 * math.pi * 2.0 * f / FPS) * up
                e = 12 + 128 * amp * up
                arms[side] = (arm_dir(side, e, 10 * up), arm_dir(side, 6 + (170 - 6) * amp * up - wag * (1 if side == "Left" else -1), 20 * up))
            p["arms"] = arms
        elif motion_id == "pick-up":
            b = bump(t, 0.2, 0.8, 0.2)
            p.update(drop=0.4 * amp * b, spine=(90.0 * amp * b, 0.0, 0.0), neck=(-20.0 * b, 0.0))
            p["arms"] = {s: hang(s) if b < 1e-3 else (unit(add(scale(hang(s)[0], 1 - b), scale((0.05 if s == "Left" else -0.05, -1.0, 0.25), b))),
                                                      unit(add(scale(hang(s)[1], 1 - b), scale((0.0, -1.0, 0.2), b)))) for s in ("Left", "Right")}
        elif motion_id == "arm-circles":
            on = bump(t, 0.06, 0.94, 0.1)
            phase = 2 * math.pi * 1.2 * f / FPS
            r = 0.6 * amp * on
            p["arms"] = {s: (unit((1.0 if s == "Left" else -1.0, r * math.sin(phase) - 1.6 * (1 - on), -r * math.cos(phase))),) * 2 for s in ("Left", "Right")}
        elif motion_id == "lunge":
            out_ = bump(t, 0.12, 0.88, 0.18)
            down = bump(t, 0.3, 0.7, 0.12)
            step = 0.85 * amp * out_
            lift = 0.08 * math.sin(math.pi * min(1.0, max(0.0, (t - 0.12) / 0.18))) + 0.08 * math.sin(math.pi * min(1.0, max(0.0, (t - 0.7) / 0.18)))
            p.update(z=0.45 * step, drop=0.35 * amp * down, feet={"Left": plant(0.0, 0.0, 0.0, "Left"), "Right": plant(0.0, 0.0, 0.0, "Right", lead=step, lift=lift)})
        elif motion_id == "shrug-bow":
            p.update(shrug=15.0 * amp * bump(t, 0.08, 0.38, 0.1), spine=(45.0 * amp * bump(t, 0.48, 0.88, 0.15), 0.0, 0.0), neck=(15.0 * amp * bump(t, 0.48, 0.88, 0.15), 0.0))
        elif motion_id == "twist":
            on = bump(t, 0.05, 0.95, 0.12)
            turn = 35.0 * amp * math.sin(2 * math.pi * 2.0 * t) * on
            p["spine"] = (0.0, 0.0, turn)
            p["arms"] = {s: (arm_dir(s, 25, turn * (-1 if s == "Left" else 1)), arm_dir(s, 20, 40)) for s in ("Left", "Right")}
        elif motion_id == "kick":
            stance = bump(t, 0.05, 0.95, 0.1)
            k = bump(t, 0.32, 0.55, 0.09)
            rest = plant(0.0, 0.0, 0.0, "Right")
            goal = (rest[0], ANKLE_Y + (0.95 - ANKLE_Y) * amp, 0.75 * amp)
            p.update(drop=0.06 * stance, feet={"Right": tuple(rest[n] + (goal[n] - rest[n]) * k for n in range(3))})
            p["arms"] = {s: (arm_dir(s, 12 + 20 * stance, 40 * stance), arm_dir(s, 6 + 140 * stance, 60 * stance)) for s in ("Left", "Right")}
        out.append(p)
    return out


def made_badly(frames: list, variant: str) -> list:
    """The same choreography, spoilt the way a bad take is."""
    count = len(frames)
    if variant == "slide":  # every foot that stands drifts sideways over the floor
        out = []
        for f, p in enumerate(frames):
            p = dict(p)
            drift = 0.25 * f / count
            feet = {}
            for side in ("Left", "Right"):
                at = (p.get("feet") or {}).get(side) or plant(0.0, 0.0, p.get("heading", 0.0), side)
                feet[side] = (at[0] + drift, at[1], at[2])
            p["feet"] = feet
            out.append(p)
        return out
    if variant == "head":  # the head flung back, fast, in the middle
        out = []
        for f, p in enumerate(frames):
            p = dict(p)
            nod, look = p.get("neck", (0.0, 0.0))
            p["neck"] = (nod - 75.0 * bump(f / count, 0.45, 0.53, 0.03), look)
            out.append(p)
        return out
    if variant == "ends":  # never comes back: it stops where it was halfway, and sinks
        half = frames[: count // 2]
        out = half + [dict(half[-1]) for _ in range(count - len(half))]
        for f in range(count):
            out[f] = dict(out[f], drop=out[f].get("drop", 0.0) + 0.2 * smooth((f / count - 0.7) / 0.3))
        return out
    return frames


def contacts_of(local_rows: list, roots: list) -> list:
    out = []
    for root, local in zip(roots, local_rows):
        pos, _ = SK.fk(root, local)
        row = []
        for side in ("Left", "Right"):
            row += [1.0 if pos[I[side + "Foot"]][1] < ANKLE_Y + 0.015 else 0.0, 1.0 if pos[I[side + "ToeBase"]][1] < TOE_Y + 0.015 else 0.0]
        out.append(row)
    return out


LIBRARY_SENTENCES = {m["sentence"]: m["id"] for m in json.load(open(os.path.join(REPO, "motion", "library", "library.json")))["motions"]}


def variant_of(text: str, seed: int) -> str:
    """Which of the five a seed makes. The good one falls on a different take for each sentence."""
    return VARIANTS[(seed + int(digest(text)[:2], 16)) % len(VARIANTS)]


def pretend_motion(motion_id: str, frames: int, variant: str) -> dict:
    held = made_badly(choreography(motion_id, frames, 0.35 if variant == "shallow" else 1.0), variant)
    roots, rows = [], []
    for p in held:
        root, local = pose(p)
        roots.append([round(v, 5) for v in root])
        rows.append([round(c, 6) for q in local for c in q])
    return {"format": "forge-soma-motion/1", "fps": FPS, "up": "+Y", "forward_at_heading_0": "+Z", "joints": list(SK.joints),
            "root": roots, "rotations": rows, "contact_order": list(CONTACT_ORDER),
            "contacts": contacts_of([[tuple(r[4 * j : 4 * j + 4]) for j in range(len(SK.joints))] for r in rows], roots)}


def pretend(request: dict) -> dict:
    """What the worker's `text` kind would answer, in shape: every sentence's stretch, one after the other."""
    assert request["kind"] == "text" and 1 <= len(request["prompts"]) <= 8
    answer, segments = None, []
    for prompt in request["prompts"]:
        assert 8 <= prompt["frames"] <= 300 and not prompt.get("constraints")
        motion_id = LIBRARY_SENTENCES.get(prompt["text"], "stand-easy")
        part = pretend_motion(motion_id, prompt["frames"], variant_of(prompt["text"], request["seed"]))
        if answer is None:
            answer = part
        else:  # the next sentence goes on from where the last one stands
            end = answer["root"][-1]
            part["root"] = [[r[0] + end[0], r[1], r[2] + end[2]] for r in part["root"]]
            for key in ("root", "rotations", "contacts"):
                answer[key] = answer[key] + part[key]
        segments.append({"name": prompt["text"], "first_frame": len(answer["root"]) - prompt["frames"], "last_frame": len(answer["root"]) - 1})
    answer["segments"] = segments
    answer["made_by"] = {"model": "a pretend worker (scripts/motion/test_screen_motions.py)", "seed": request["seed"], "steps": request["steps"]}
    return answer


def to_the_end(library: str, sent: list = None, **more) -> dict:
    """What `baml run screen_motions` does: a pass, send what it asks for, a pass again."""
    for _ in range(3):
        result = screen_motions.step(library, sk=SK, **more)
        if not result["todo"]:
            return result
        for item in result["todo"]:
            cache = os.path.join(library, ".cache")
            with open(os.path.join(cache, item["request"] + ".request.json")) as f:
                request = json.load(f)
            if sent is not None:
                sent.append(request)
            with open(os.path.join(cache, item["request"] + ".json"), "w") as f:
                json.dump(pretend(request), f)
    raise AssertionError("still something to make after three passes")


def a_library(root: str) -> str:
    folder = os.path.join(root, "library")
    os.makedirs(folder)
    shutil.copyfile(os.path.join(REPO, "motion", "library", "library.json"), os.path.join(folder, "library.json"))
    return folder


# ---- the list -------------------------------------------------------------------------


def test_the_library_is_a_short_plain_list_that_covers_every_hard_joint():
    lib = screen_motions.load()
    motions = lib["motions"]
    assert 10 <= len(motions) <= 14, len(motions)
    for m in motions:
        assert m["seconds"] <= 8 and m["sentence"].startswith("A person ") and len(m["sentence"].split()) <= 24, m
        assert len(m["why"]) > 40 and m["joints"] and m["asks"], m["id"]
    joints = " ".join(j for m in motions for j in m["joints"])
    for needed in ("knees", "hips", "shoulders", "shoulders behind", "elbows", "neck", "spine twist", "spine bend", "spine side bend", "ankles", "collar bones"):
        assert needed in joints, needed
    asked = {(a["measure"], a.get("at_least")) for m in motions for a in m["asks"]}
    # A deep bend of the knees, both arms overhead, a full turn on the spot, a quick turn back, a hand to the floor.
    assert ("hips_drop", 0.35) in asked and ("hands_over_head", 0.2) in asked and ("turn", 300) in asked and ("turn", 140) in asked
    assert any(a["measure"] == "hand_low" for m in motions for a in m["asks"])
    assert len({m["id"] for m in motions}) == len(motions)


def test_a_library_that_cannot_be_made_is_refused():
    lib = screen_motions.load()
    for spoil, said in ((lambda m: m.update(seconds=12), "2 to 8"), (lambda m: m.update(sentence="Squat."), "A person"),
                        (lambda m: m["asks"].append({"measure": "joy", "at_least": 1}), "known measure"), (lambda m: m.update(id="Deep Squat"), "lowercase")):
        broken = json.loads(json.dumps(lib))
        spoil(broken["motions"][0])
        try:
            screen_motions.check(broken)
        except ValueError as why:
            assert said in str(why), why
        else:
            raise AssertionError("a broken library was let through: " + said)


# ---- measuring --------------------------------------------------------------------------


def test_every_motion_done_well_does_what_it_is_asked_and_done_by_half_does_not():
    for m in screen_motions.load()["motions"]:
        frames = int(m["seconds"] * FPS)
        good = screen_motions.score_take(SK, pretend_motion(m["id"], frames, "good"), m["asks"])
        assert good["does_what_was_asked"], (m["id"], good["missed"], good["measures"])
        assert good["parts"]["slide"] < 1.0 and good["parts"]["head"] == 0 and good["parts"]["ends"] < 5, (m["id"], good["parts"], good["measures"])
        half = screen_motions.score_take(SK, pretend_motion(m["id"], frames, "shallow"), m["asks"])
        assert not half["does_what_was_asked"] and half["score"] > good["score"] + 25, (m["id"], half["measures"])


def test_what_a_bad_take_gets_wrong_is_what_it_is_scored_down_for():
    m = next(m for m in screen_motions.load()["motions"] if m["id"] == "deep-squat")
    frames = int(m["seconds"] * FPS)
    scored = {v: screen_motions.score_take(SK, pretend_motion(m["id"], frames, v), m["asks"]) for v in VARIANTS}
    assert scored["slide"]["measures"]["slide_cm"] > 10 and scored["slide"]["parts"]["slide"] > 9
    assert scored["head"]["measures"]["chin_up_deg"] > 60 and scored["head"]["measures"]["head_speed_deg_s"] > 400 and scored["head"]["parts"]["head"] > 10
    assert not scored["ends"]["measures"]["ends_standing"] and scored["ends"]["parts"]["ends"] > 15
    assert min(scored, key=lambda v: scored[v]["score"]) == "good"
    # The measures read the body the right way round: hips down in the squat, a hand to the floor in the pick-up.
    assert 0.45 < scored["good"]["measures"]["hips_drop"] < 0.5
    pick = next(m for m in screen_motions.load()["motions"] if m["id"] == "pick-up")
    low = screen_motions.measures(SK, pretend_motion("pick-up", int(pick["seconds"] * FPS), "good"))
    assert low["hand_low"] < 0.35 and low["bow"] > 60


# ---- the jobs and the keeping --------------------------------------------------------------


def test_five_takes_each_on_its_own_seed_and_the_one_done_well_is_kept():
    root = tempfile.mkdtemp(prefix="forge-screen-")
    try:
        library = a_library(root)
        only = ["deep-squat", "turn-circle", "walk-turn-back"]
        sent = []
        result = to_the_end(library, sent, only=only)
        assert len(sent) == 15 and all(len(r["prompts"]) == 1 for r in sent)
        assert len({r["seed"] for r in sent}) == 15, "every take rolls its own dice"
        assert all(not r["prompts"][0].get("constraints") and r["steps"] == 100 and r["tidy"] for r in sent)
        assert set(result["state"].values()) == {"made"} and set(result["state"]) == set(only)
        for mid in only:
            kept = json.load(open(os.path.join(library, mid, "motion.json")))
            scores = json.load(open(os.path.join(library, mid, "scores.json")))
            assert kept["format"] == "forge-soma-motion/1" and kept["joints"] == SK.joints and kept["id"] == mid
            assert len(kept["root"]) == int(kept["seconds"] * FPS) and kept["ask"] == scores["ask"]
            assert len(scores["takes"]) == 5 and scores["does_what_was_asked"]
            assert variant_of(kept["prompt"], kept["seed"]) == "good", (mid, scores["kept"], [s["score"] for s in scores["takes"]])
            assert all("measures" in s and "parts" in s for s in scores["takes"])
        # Asked again, nothing is sent: the kept motions and the cached answers stand.
        again = screen_motions.step(library, sk=SK, only=only)
        assert not again["todo"] and not again["jobs"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_changed_sentence_makes_only_that_motion_again_and_the_rest_stand():
    root = tempfile.mkdtemp(prefix="forge-screen-")
    try:
        library = a_library(root)
        to_the_end(library, only=["deep-squat", "look-around"], takes=2)
        lib = json.load(open(os.path.join(library, "library.json")))
        lib["motions"][[m["id"] for m in lib["motions"]].index("look-around")]["sentence"] = "A person looks around slowly, to the left and to the right."
        json.dump(lib, open(os.path.join(library, "library.json"), "w"))
        result = screen_motions.step(library, sk=SK, only=["deep-squat", "look-around"], takes=2)
        assert result["state"]["deep-squat"] == "made" and result["state"]["look-around"] == "waiting for Kimodo"
        assert [t["id"] for j in result["jobs"] for t in j["takes"]] == ["look-around", "look-around"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_several_sentences_can_share_a_job_and_each_comes_back_from_the_start():
    root = tempfile.mkdtemp(prefix="forge-screen-")
    try:
        library = a_library(root)
        sent = []
        to_the_end(library, sent, only=["stand-easy", "deep-squat", "kick"], takes=2, size=3)
        assert len(sent) == 2 and all(len(r["prompts"]) == 3 for r in sent), [len(r["prompts"]) for r in sent]
        for mid in ("stand-easy", "deep-squat", "kick"):
            kept = json.load(open(os.path.join(library, mid, "motion.json")))
            assert abs(kept["root"][0][0]) < 1e-3 and abs(kept["root"][0][2]) < 1e-3, (mid, kept["root"][0])
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---- the dry run and its cost -------------------------------------------------------------


def test_the_dry_run_prints_every_job_and_its_cost_and_sends_nothing():
    root = tempfile.mkdtemp(prefix="forge-screen-")
    try:
        library = a_library(root)
        printed = io.StringIO()
        with redirect_stdout(printed):
            assert screen_motions.main(["plan", "--library", library]) == 0
        lines = printed.getvalue().splitlines()
        motions = screen_motions.load(library)["motions"]
        jobs = [l for l in lines if l.startswith("SCREEN job ")]
        assert len(jobs) == 5 * len(motions), len(jobs)
        assert any('deep-squat take 3' in l and "A person slowly squats" in l for l in jobs)
        cost = json.loads(next(l for l in lines if l.startswith("RESULT "))[7:])["cost"]
        assert cost["takes"] == 5 * len(motions) and cost["jobs"] == 5 * len(motions)
        # About three seconds of GPU a take (README), then the worker's idle minute; a cold worker adds its boot and the encoder.
        assert 2.3 * cost["takes"] < cost["gpu_s"]["takes"] < 3.3 * cost["takes"], cost
        assert 0.02 < cost["low_usd"] < cost["high_usd"] < 0.2, cost
        assert any(l.startswith("SCREEN cost: about $") for l in lines) and any("just screen-motions go" in l for l in lines)
        todo = json.load(open(os.path.join(library, ".cache", "todo.json")))
        assert len(todo) == 5 * len(motions)
        assert not any(os.path.isdir(os.path.join(library, m["id"])) for m in motions), "a dry run keeps nothing"
        only = screen_motions.estimate([{"answered": False, "takes": [{"frames": 240}]}], answered_before=False)
        assert only["fetch_usd"] and only["jobs"] == 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_rehearsing_never_writes_into_the_real_library():
    try:
        screen_motions.rehearse(screen_motions.LIBRARY, log=lambda *a: None)
    except ValueError as why:
        assert "folder of your own" in str(why)
    else:
        raise AssertionError("rehearse wrote pretend answers into motion/library")


# ---- playing them, and where the gallery and the reel find them -------------------------------


def test_screen_play_lines_the_cast_up_for_the_watch_page_and_the_reel_reads_the_library():
    import screen_play

    root = tempfile.mkdtemp(prefix="forge-screen-")
    try:
        runs, shots = os.path.join(root, "runs"), os.path.join(root, "shots")
        library = a_library(root)
        to_the_end(library, only=["deep-squat"], takes=1)
        names = ["2026-11-20T14-02-41-young-lincoln-frontier-wrestler", "2026-11-20T13-52-46-stocky-pirate-deckhand"]
        for name in names:
            os.makedirs(os.path.join(runs, name, "profiles"))
            json.dump({"name": name.split("-", 3)[-1].replace("-", " ").title(), "size_m": 1.8}, open(os.path.join(runs, name, "brief.json"), "w"))
            for version in ("lowpoly", "midpoly"):
                open(os.path.join(runs, name, "profiles", "%s-screen-deep-squat.glb" % version), "wb").close()
                json.dump({"screen": {"id": "deep-squat", "ask": json.load(open(os.path.join(library, "deep-squat", "motion.json")))["ask"]}},
                          open(os.path.join(runs, name, "profiles", "%s-screen-deep-squat.json" % version), "w"))
        for name in names:  # the versions it is played on
            open(os.path.join(runs, name, "lowpoly.glb"), "wb").close()
            open(os.path.join(runs, name, "profiles", "midpoly.glb"), "wb").close()
        # Up to date: nothing to play again. Played from another take, or never: played again.
        first = os.path.join(runs, names[0])
        assert screen_play.missing(first, ["deep-squat", "kick"], ["lowpoly", "midpoly"], library) == []
        record = os.path.join(first, "profiles", "midpoly-screen-deep-squat.json")
        kept = json.load(open(record))
        json.dump({"screen": {"id": "deep-squat", "ask": "an older take"}}, open(record, "w"))
        assert screen_play.missing(first, ["deep-squat"], ["lowpoly", "midpoly"], library) == ["deep-squat"]
        assert screen_play.missing(first, ["deep-squat"], ["lowpoly"], library) == []
        json.dump(kept, open(record, "w"))
        assert screen_play.find_run("lincoln", runs) == first
        made = screen_play.lineups(["deep-squat"], runs, shots, library)
        cast = json.load(open(os.path.join(shots, "screen-deep-squat", "cast-screen.json")))
        take = json.load(open(os.path.join(shots, "screen-deep-squat", "take.json")))
        assert made == [os.path.join(shots, "screen-deep-squat")] and take["title"].startswith("Deep squat")
        assert sorted(cast["roles"]) == ["stocky-pirate-deckhand", "young-lincoln-frontier-wrestler"] and cast["set"] == "studio" and set(cast["marks"]) == set(cast["roles"])
        spots = sorted(m["at"][0] for m in cast["marks"].values())
        assert abs(spots[1] - spots[0]) >= 1.0, "side by side, with room between"
        for role, part in cast["roles"].items():
            assert part["true_size"] and os.path.isfile(os.path.join(shots, "screen-deep-squat", part["glb"])), part
        # The gallery's watch page reads it as any take, each on its mark.
        sys.path.insert(0, os.path.join(REPO, "scripts"))
        import gallery

        found = gallery.takes_in(os.path.join(shots, "screen-deep-squat"), "screen-deep-squat")
        assert found and len(found[0]["roles"]) == 2 and all(r["mark"] and r["size"] == 1.0 and r["midpoly"] for r in found[0]["roles"]), found
        # The casting reel: a library side plays the run's own screen-test clip.
        sys.path.insert(0, os.path.join(REPO, "scripts", "casting"))
        import casting

        office = os.path.join(root, "casting")
        os.makedirs(os.path.join(office, "robot", "candidates", "tin"))
        shutil.copyfile(os.path.join(REPO, "casting", "reel.json"), os.path.join(office, "reel.json"))
        json.dump({"title": "Robot", "chemistry": {}}, open(os.path.join(office, "robot", "role.json"), "w"))
        json.dump({"name": "Tin", "takes": [{"n": 1, "run": names[0]}]}, open(os.path.join(office, "robot", "candidates", "tin", "candidate.json"), "w"))
        cast_office = casting.Casting(office, runs, shots)
        reel = {s["id"]: s for s in cast_office.reel_for("robot", "tin", {"n": 1, "run": names[0]})}
        library_sides = [s for s in json.load(open(os.path.join(office, "reel.json")))["sides"] if s["clip"] == "library"]
        assert len(library_sides) == len(screen_motions.load()["motions"])
        squat = next(s for s in library_sides if s["motion"] == "deep-squat")
        assert reel[squat["id"]]["ready"] and reel[squat["id"]]["glb"] == "runs/%s/profiles/lowpoly-screen-deep-squat.glb" % names[0]
        kick = next(s for s in library_sides if s["motion"] == "kick")
        assert not reel[kick["id"]]["ready"] and "screen-play" in reel[kick["id"]]["made_by"]
        assert reel["walk"]["glb"] == "runs/%s/profiles/lowpoly-walk.glb" % names[0], "the other sides are as they were"
        assert casting.library_wanted(cast_office.reel(), os.path.join(runs, names[0]), "lowpoly", library) == []
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL", name, "-", type(e).__name__, e)
    print("%d passed, %d failed" % (len(tests) - failed, failed))
    sys.exit(1 if failed else 0)
