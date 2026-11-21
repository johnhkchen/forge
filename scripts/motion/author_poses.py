"""Our own pose library (the hero shot's poses, and standing, sitting and shaking hands for a set), written here and nowhere else.

    python3 scripts/motion/author_poses.py            # check, then write motion/poses.json
    python3 scripts/motion/author_poses.py --check    # only check what is written

Every pose below is described by hand, in the terms posing.py understands:
where the hips are, how the spine bends, where the feet stand, where the hands
are. Sizes are in units of the skeleton (H is the standing hip height), so the
poses fit the SOMA body they are built on. No motion capture, no sample clip
and no generated motion goes into this file or comes out of it: the only
inputs are the numbers in POSES and the skeleton's bone lengths.

Each pose is then read back as a body and checked:
  - every limb reaches its target without overstretching
  - knees and elbows bend the way they do, and not past 155 degrees
  - no joint is turned further from rest than a body allows
  - planted feet are flat on the ground, planted hands at the height they claim
  - nothing is under the ground
  - a pose that stands still has its weight over what it stands on
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import posing  # noqa: E402
from soma import REPO, Skeleton, length, qangle, qconj, qmul, sub  # noqa: E402

LIBRARY = os.path.join(REPO, "motion", "poses.json")
WALL_TOP = 0.75  # the wall the vault poses are written for
PALM = 0.03  # a wrist sits this far above the surface its palm is on
SEAT = 0.46  # the seat the sitting poses are written for (scripts/sets/standing.py lets a set's seats differ a little)
SEAT_TO_HIPS = 0.13  # the hips joint sits this far above what is sat on
SHAKE_HEIGHT, SHAKE_REACH = 1.05, 0.26  # where the wrist is in a handshake: up, and out in front on the body's middle line

# How far each joint may turn from its rest pose, relative to its parent, in degrees.
LIMITS = {
    "Spine1": 35, "Spine2": 35, "Chest": 35, "Neck1": 35, "Neck2": 35, "Head": 50,
    "LeftShoulder": 40, "RightShoulder": 40, "LeftArm": 175, "RightArm": 175,
    "LeftForeArm": 160, "RightForeArm": 160, "LeftHand": 85, "RightHand": 85,
    "LeftLeg": 140, "RightLeg": 140, "LeftShin": 160, "RightShin": 160,
    "LeftFoot": 75, "RightFoot": 75, "LeftToeBase": 70, "RightToeBase": 70,
}  # fmt: skip
HINGE_MAX = 155.0
# Head turn against the hips, all the spine and neck joints together.
LOOK_MAX = 95.0


def poses_for(sk: Skeleton) -> dict:
    """The library, as pose descriptions sized to the skeleton."""
    H = sk.rest_world_pos[0][1]
    hip = abs(sk.rest_pos[sk.index["LeftLeg"]][0])  # half the distance between the hip joints
    ankle = sk.rest_world_pos[sk.index["LeftFoot"]][1]  # ankle height with the foot flat
    shoulder = sk.rest_world_pos[sk.index["LeftArm"]][1] / H  # shoulder height, in H

    crouch = {
        "about": "low crouch, both feet flat, hands near the knees, looking ahead",
        "hips": (0.0, 0.50 * H, -0.04),
        "pelvis": [("X", 22)],
        "spine": [("X", 30)],
        "neck": [("X", -22)],
        "head": [("X", -18)],
        "left_foot": {"at": (hip + 0.07, ankle, 0.16), "turn": [("Y", 12)]},
        "right_foot": {"at": (-hip - 0.07, ankle, -0.06), "turn": [("Y", -14)]},
        "left_hand": {"at": (hip + 0.10, 0.44 * H, 0.40), "pole": (1.0, -0.4, -0.6)},
        "right_hand": {"at": (-hip - 0.12, 0.42 * H, 0.26), "pole": (-1.0, -0.4, -0.6)},
        "planted": ["left_foot", "right_foot"],
        "still": True,
    }
    look_left = dict(crouch, about="the same crouch, head and chest turned to the left")
    look_left.update(spine=[("Y", 24), ("X", 30)], neck=[("Y", 26), ("X", -20)], head=[("Y", 24), ("X", -14)])
    look_right = dict(crouch, about="the same crouch, head and chest turned to the right")
    look_right.update(spine=[("Y", -24), ("X", 30)], neck=[("Y", -26), ("X", -20)], head=[("Y", -24), ("X", -14)])

    sneak_left = {
        "about": "a low sneaking step, left foot forward and planted, right foot behind on its toes",
        "hips": (0.0, 0.66 * H, 0.0),
        "pelvis": [("X", 14), ("Y", -8)],
        "spine": [("X", 26), ("Y", 10)],
        "neck": [("X", -16)],
        "head": [("X", -14)],
        "left_foot": {"at": (hip + 0.02, ankle, 0.30), "turn": [("Y", 6)]},
        "right_foot": {"at": (-hip - 0.02, ankle + 0.085, -0.30), "turn": [("Y", -6), ("X", 42)], "toes": [("X", -40)]},
        "left_hand": {"at": (hip + 0.14, 0.68 * H, -0.04), "pole": (1.0, -0.2, -1.0)},
        "right_hand": {"at": (-hip - 0.12, 0.70 * H, 0.34), "pole": (-1.0, -0.6, -0.6)},
        "planted": ["left_foot"],
        "still": False,
        "next": "sneak_right",
        "step_seconds": 0.62,
    }

    sprint_left = {
        "about": "mid-sprint, leaning forward, left foot striking under the body, right heel kicked up behind",
        "hips": (0.0, 0.93 * H, 0.0),
        "pelvis": [("X", 14), ("Y", -10)],
        "spine": [("X", 14), ("Y", 16)],
        "neck": [("X", -10)],
        "head": [("X", -10)],
        "left_foot": {"at": (hip * 0.5, ankle, 0.26)},
        "right_foot": {"at": (-hip * 0.6, 0.50 * H, -0.50), "pole": (0.0, -0.2, 1.0), "loose": True, "turn": [("X", 30)]},
        "left_hand": {"at": (hip + 0.14, 0.98 * H, -0.26), "pole": (0.6, 0.2, -1.0)},
        "right_hand": {"at": (-hip + 0.02, 1.20 * H, 0.44), "pole": (-0.8, -1.0, -0.3)},
        "planted": ["left_foot"],
        "still": False,
        "next": "sprint_right",
        "step_seconds": 0.24,
    }

    vault_takeoff = {
        "about": "last step before a waist-high wall: left foot planted, right knee driving up, right hand reaching for the wall top",
        "hips": (0.0, 0.90 * H, 0.0),
        "pelvis": [("X", 12)],
        "spine": [("X", 22), ("Y", -10)],
        "neck": [("X", -10)],
        "head": [("X", -8)],
        "left_foot": {"at": (hip * 0.6, ankle, 0.10)},
        "right_foot": {"at": (-hip, 0.52 * H, 0.26), "pole": (0.0, 0.3, 1.0), "loose": True, "turn": [("X", 15)]},
        "left_hand": {"at": (hip + 0.16, 1.02 * H, -0.12), "pole": (0.8, 0.0, -1.0)},
        "right_hand": {"at": (-hip - 0.10, WALL_TOP + 0.26, 0.52), "pole": (-1.0, -0.6, -0.4)},
        "planted": ["left_foot"],
        "still": False,
    }

    vault_over = {
        "about": "over the wall: right hand planted on the wall top, hips above it, legs tucked and swung to the left",
        "hips": (0.10, WALL_TOP + 0.31, 0.0),
        "pelvis": [("Z", 40), ("X", 22), ("Y", 14)],
        "spine": [("Z", 12), ("X", 18)],
        "neck": [("Z", -16), ("X", -10)],
        "head": [("Z", -12), ("X", -8)],
        "left_foot": {"at": (0.62, WALL_TOP + 0.34, 0.10), "pole": (0.2, 0.6, 1.0), "loose": True, "turn": [("X", 20)]},
        "right_foot": {"at": (0.42, WALL_TOP + 0.20, -0.22), "pole": (0.0, 0.4, 1.0), "loose": True, "turn": [("X", 25)]},
        "left_hand": {"at": (0.36, WALL_TOP + 0.75, 0.34), "pole": (1.0, -0.4, -0.6)},
        "right_hand": {"at": (-0.24, WALL_TOP + PALM, 0.0), "pole": (-1.0, 0.2, -0.8), "flat": [("Y", 60), ("Z", 40)]},
        "planted": ["right_hand"],
        "planted_height": WALL_TOP,
        "still": False,
    }

    land = {
        "about": "deep landing crouch: left foot flat in front, right foot behind on its toes, left hand on the ground, right arm out behind",
        "hips": (0.0, 0.41 * H, -0.12),
        "pelvis": [("X", 28), ("Y", 10)],
        "spine": [("X", 56), ("Y", -8)],
        "neck": [("X", -30)],
        "head": [("X", -24)],
        "left_foot": {"at": (hip + 0.10, ankle, 0.22), "turn": [("Y", 14)]},
        "right_foot": {"at": (-hip - 0.10, ankle + 0.085, -0.36), "pole": (-0.5, 0.0, 1.0), "turn": [("Y", -10), ("X", 68)], "toes": [("X", -66)]},
        "left_hand": {"at": (0.22, PALM, 0.31), "pole": (1.0, 0.2, -0.6), "flat": [("Y", -90)]},
        "right_hand": {"at": (-0.42, 0.62 * H, -0.04), "pole": (-0.4, 0.6, -1.0)},
        "planted": ["left_foot", "left_hand"],
        "also_on": ["RightToeBase"],
        "pins": ["left_foot", "right_foot", "left_hand"],
        "still": True,
    }

    rise = {
        "about": "halfway up from the landing, weight on both feet, right hand going to the sword grip over the right shoulder",
        "hips": (0.0, 0.74 * H, -0.02),
        "pelvis": [("X", 12)],
        "spine": [("X", 18)],
        "neck": [("X", -12)],
        "head": [("X", -10)],
        "left_foot": {"at": (hip + 0.09, ankle, 0.16), "turn": [("Y", 12)]},
        "right_foot": {"at": (-hip - 0.09, ankle, -0.14), "turn": [("Y", -16)]},
        "left_hand": {"at": (hip + 0.20, 0.80 * H, 0.22), "pole": (1.0, -0.2, -0.8)},
        "right_hand": {"at": (-0.16, (shoulder + 0.06) * H * 0.80 + 0.10, 0.02), "pole": (-1.0, 0.6, 0.2)},
        "planted": ["left_foot", "right_foot"],
        "still": True,
    }

    draw = {
        "about": "standing, right hand at the sword grip behind the right shoulder, left hand at the hip",
        "hips": (0.0, 0.95 * H, 0.0),
        "pelvis": [("Y", 12)],
        "spine": [("X", 4), ("Y", 8)],
        "head": [("Y", -18), ("X", -4)],
        "left_foot": {"at": (hip + 0.12, ankle, 0.14), "turn": [("Y", 18)]},
        "right_foot": {"at": (-hip - 0.10, ankle, -0.16), "turn": [("Y", -24)]},
        "left_hand": {"at": (hip + 0.14, 0.98 * H, 0.10), "pole": (1.0, 0.0, -1.0)},
        "right_hand": {"at": (-0.20, shoulder * H + 0.13, -0.10), "pole": (-1.0, 1.0, 0.6)},
        "planted": ["left_foot", "right_foot"],
        "still": True,
    }

    hero = {
        "about": "feet wide, knees soft, sword held out low to the right, left hand a fist at the hip, chin up",
        "hips": (0.0, 0.88 * H, 0.0),
        "pelvis": [("Y", 16)],
        "spine": [("X", -4), ("Y", -10)],
        "neck": [("X", -4)],
        "head": [("Y", -6), ("X", -6)],
        "left_foot": {"at": (hip + 0.22, ankle, 0.16), "turn": [("Y", 30)]},
        "right_foot": {"at": (-hip - 0.24, ankle, -0.14), "turn": [("Y", -30)]},
        "left_hand": {"at": (hip + 0.16, 0.99 * H, 0.06), "pole": (1.0, 0.0, -1.0)},
        "right_hand": {"at": (-0.42, 0.87 * H, 0.10), "pole": (-0.6, 0.2, -1.0)},
        "planted": ["left_foot", "right_foot"],
        "still": True,
    }

    # ---- for a standing set: standing, sitting, shaking hands (scripts/sets/standing.py) ----

    def hang(side: float) -> dict:
        """An arm hanging by the body: the hand a little in front of the hip, the elbow behind."""
        return {"at": (side * (hip + 0.15), 0.89 * H, 0.07), "pole": (side * 0.3, 0.0, -1.0)}

    stand = {
        "about": "standing easy, feet under the hips, arms by the sides, looking ahead",
        "hips": (0.0, H - 0.015, 0.0),
        "left_foot": {"at": (hip + 0.03, ankle, 0.02), "turn": [("Y", 8)]},
        "right_foot": {"at": (-hip - 0.03, ankle, 0.02), "turn": [("Y", -8)]},
        "left_hand": hang(1.0),
        "right_hand": hang(-1.0),
        "planted": ["left_foot", "right_foot"],
        "still": True,
    }

    sit = {
        "about": f"sitting on a seat {SEAT} m high, back straight, knees over the feet, hands on the thighs",
        "hips": (0.0, SEAT + SEAT_TO_HIPS, 0.0),
        "spine": [("X", 4)],
        "left_foot": {"at": (hip + 0.05, ankle, 0.42), "pole": (0.1, 1.0, 0.3), "turn": [("Y", 6)]},
        "right_foot": {"at": (-hip - 0.05, ankle, 0.42), "pole": (-0.1, 1.0, 0.3), "turn": [("Y", -6)]},
        "left_hand": {"at": (hip + 0.06, SEAT + 0.21, 0.27), "pole": (1.0, -0.3, -0.6)},
        "right_hand": {"at": (-hip - 0.06, SEAT + 0.21, 0.27), "pole": (-1.0, -0.3, -0.6)},
        "planted": ["left_foot", "right_foot"],
        "also_on": ["Hips"],
        "seated": True,
        "still": True,
    }
    sit_talk = dict(sit, about="sitting the same way, leaning in a little, right hand lifted in mid-sentence, head turned to the right")
    sit_talk.update(
        spine=[("X", 10), ("Y", -8)],
        head=[("Y", -16)],
        right_hand={"at": (-hip - 0.16, SEAT + 0.50, 0.36), "pole": (-1.0, -0.8, -0.2)},
    )

    shake = {
        "about": "standing, a small lean in, right hand held out in front at elbow height for a handshake",
        "hips": (0.0, H - 0.025, 0.01),
        "spine": [("X", 6)],
        "head": [("X", -4)],
        "left_foot": {"at": (hip + 0.04, ankle, -0.06), "turn": [("Y", 10)]},
        "right_foot": {"at": (-hip - 0.02, ankle, 0.14), "turn": [("Y", -6)]},
        "left_hand": hang(1.0),
        "right_hand": {"at": (-0.02, SHAKE_HEIGHT, SHAKE_REACH), "pole": (-1.0, -0.8, -0.4)},
        "planted": ["left_foot", "right_foot"],
        "pins": ["right_hand"],
        "still": True,
    }
    shake_dip = dict(shake, about="the same handshake a beat later: knees a touch softer, a nod, the hand where it was")
    shake_dip.update(hips=(0.0, H - 0.05, 0.02), spine=[("X", 11)], head=[("X", 8)])

    return {
        "crouch": crouch,
        "crouch_look_left": look_left,
        "crouch_look_right": look_right,
        "sneak_left": sneak_left,
        "sneak_right": dict(posing.mirror(sneak_left), about="the mirror step: right foot forward and planted", next="sneak_left"),
        "sprint_left": sprint_left,
        "sprint_right": dict(posing.mirror(sprint_left), about="the mirror stride: right foot striking", next="sprint_left"),
        "vault_takeoff": vault_takeoff,
        "vault_over": vault_over,
        "land_three_point": land,
        "rise": rise,
        "draw": draw,
        "hero_stance": hero,
        "stand": stand,
        "sit": sit,
        "sit_talk": sit_talk,
        "shake": shake,
        "shake_dip": shake_dip,
    }


# ---- checks ---------------------------------------------------------------


def sanity(sk: Skeleton, name: str, posed: posing.Posed) -> list:
    """What is anatomically wrong with a built pose, in words. Empty when nothing is."""
    desc, problems = posed.desc, []
    ankle = sk.rest_world_pos[sk.index["LeftFoot"]][1]
    toe = sk.rest_world_pos[sk.index["LeftToeBase"]][1]

    for limb, reach in posed.reaches.items():
        if reach > 0.985:
            problems.append(f"{limb} is stretched to {reach:.0%} of the limb's length to reach its target")
        if reach < 0.28:
            problems.append(f"{limb} is folded to {reach:.0%} of the limb's length")
    for side in ("Left", "Right"):
        knee = posing.hinge(posed, f"{side}Leg", f"{side}Shin", f"{side}Foot")
        elbow = posing.hinge(posed, f"{side}Arm", f"{side}ForeArm", f"{side}Hand")
        if knee > HINGE_MAX:
            problems.append(f"{side} knee is bent {knee:.0f} degrees (more than {HINGE_MAX:.0f})")
        if elbow > HINGE_MAX:
            problems.append(f"{side} elbow is bent {elbow:.0f} degrees (more than {HINGE_MAX:.0f})")
        # A knee bends so the shin folds back under the thigh, never forward of it.
        thigh = sub(posed.at(f"{side}Shin"), posed.at(f"{side}Leg"))
        shin = sub(posed.at(f"{side}Foot"), posed.at(f"{side}Shin"))
        front = posing.qrot(posed.rot[sk.index[f"{side}Leg"]], posing.qrot(qconj(sk.rest_world_rot[sk.index[f"{side}Leg"]]), posing.Z))
        if knee > 8 and posing.dot(posing.cross(thigh, shin), posing.cross(thigh, front)) > 0:
            problems.append(f"{side} knee bends backwards")
    for joint, limit in LIMITS.items():
        bent = posing.bend_of(sk, posed, joint)
        if bent > limit:
            problems.append(f"{joint} is turned {bent:.0f} degrees from rest (limit {limit})")
    head = qmul(posed.rot[sk.index["Head"]], qconj(sk.rest_world_rot[sk.index["Head"]]))
    hips = qmul(posed.rot[0], qconj(sk.rest_world_rot[0]))
    look = qangle(qmul(qconj(hips), head))
    if look > LOOK_MAX:
        problems.append(f"the head is turned {look:.0f} degrees against the hips (limit {LOOK_MAX:.0f})")

    for i, joint in enumerate(sk.joints):
        floor = toe if joint.endswith("ToeBase") else ankle if joint.endswith("Foot") else 0.0 if joint.endswith("End") else 0.02
        if posed.pos[i][1] < floor - 0.012:
            problems.append(f"{joint} is {100 * (floor - posed.pos[i][1]):.1f} cm under the ground")
    base = desc.get("planted_height", 0.0)
    for part in desc.get("planted", []):
        side = part.split("_")[0].capitalize()
        if part.endswith("foot"):
            for joint, rest in ((f"{side}Foot", ankle), (f"{side}ToeBase", toe)):
                off = posed.at(joint)[1] - rest
                if abs(off) > 0.012:
                    problems.append(f"{part} is planted but {joint} is {100 * off:+.1f} cm off the ground")
        else:
            off = posed.at(f"{side}Hand")[1] - base - PALM
            if abs(off) > 0.012:
                problems.append(f"{part} is planted but the wrist is {100 * off:+.1f} cm off where the palm would rest")

    if desc.get("still"):
        # Weight over the feet: the hips' ground point inside the box around what is planted, with a hand's width to spare.
        on = [posed.at(f"{p.split('_')[0].capitalize()}{'Foot' if p.endswith('foot') else 'Hand'}") for p in desc.get("planted", [])]
        on += [posed.at(f"{p.split('_')[0].capitalize()}ToeBase") for p in desc.get("planted", []) if p.endswith("foot")]
        on += [posed.at(j) for j in desc.get("also_on", [])]
        if on:
            centre = [sum(p[a] for p in posed.pos) / len(posed.pos) for a in (0, 2)]
            lo = [min(p[a] for p in on) - 0.10 for a in (0, 2)]
            hi = [max(p[a] for p in on) + 0.10 for a in (0, 2)]
            if not (lo[0] <= centre[0] <= hi[0] and lo[1] <= centre[1] <= hi[1]):
                problems.append(f"it would fall over: the body's middle ({centre[0]:+.2f}, {centre[1]:+.2f}) is outside what it stands on")
    return problems


def build_all(sk: Skeleton) -> tuple:
    built, problems = {}, {}
    for name, desc in poses_for(sk).items():
        posed = posing.build(sk, name, desc)
        built[name] = posed
        found = sanity(sk, name, posed)
        if found:
            problems[name] = found
    return built, problems


def library_card(sk: Skeleton, built: dict) -> dict:
    poses = {}
    for name, posed in built.items():
        card = posed.card()
        card["about"] = posed.desc["about"]
        card["still"] = bool(posed.desc.get("still"))
        for key in ("next", "step_seconds", "seated"):
            if key in posed.desc:
                card[key] = posed.desc[key]
        poses[name] = card
    return {
        "format": "forge-soma-poses/1",
        "made_by": "scripts/motion/author_poses.py, from hand-written pose descriptions. No motion capture or sample clip was used.",
        "space": "SOMA local joint rotations [x, y, z, w]; root is the hips position with the pose standing at the origin, facing +Z, Y up, metres",
        "poses": poses,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="check only; fail if motion/poses.json is not what this file builds")
    parser.add_argument("--out", default=LIBRARY)
    parser.add_argument("--draft", action="store_true", help="write --out even if poses fail, to look at them; never the library itself")
    args = parser.parse_args()
    sk = Skeleton.load()
    built, problems = build_all(sk)
    for name, posed in built.items():
        knees = [round(posing.hinge(posed, f"{s}Leg", f"{s}Shin", f"{s}Foot")) for s in ("Left", "Right")]
        elbows = [round(posing.hinge(posed, f"{s}Arm", f"{s}ForeArm", f"{s}Hand")) for s in ("Left", "Right")]
        print(f"POSE {name}: hips {posed.root[1]:.2f} m, knees {knees}, elbows {elbows}, {'ok' if name not in problems else 'PROBLEMS'}")
        if args.draft:
            print("POSE   shoulders", [tuple(round(v, 2) for v in posed.at(j)) for j in ("LeftArm", "RightArm")])
        for line in problems.get(name, []):
            print(f"POSE   - {line}")
    if problems and not (args.draft and os.path.abspath(args.out) != LIBRARY):
        sys.exit(f"{len(problems)} poses fail their checks; nothing written")
    text = json.dumps(library_card(sk, built), indent=1) + "\n"
    if args.check:
        with open(args.out) as f:
            if f.read() != text:
                sys.exit(f"{args.out} is not what author_poses.py builds; run it without --check")
        print(f"POSE {len(built)} poses check out and match {os.path.relpath(args.out, REPO)}")
        return
    with open(args.out, "w") as f:
        f.write(text)
    print(f"POSE wrote {len(built)} poses to {os.path.relpath(args.out, REPO)}")


if __name__ == "__main__":
    main()
