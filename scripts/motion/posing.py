"""Builds one body pose on the SOMA skeleton from plain anatomical terms.

A pose is described the way you would talk a life model into it: where the
hips are, how the spine bends, where each foot stands and which way the knee
points, where each hand is. `build` turns that into joint rotations.

Everything is in "pose space": the character stands at the origin, faces +Z,
left is +X, up is +Y, metres and degrees.

Bends are written as (axis, degrees) turns in the body's own axes:
    X  the left-right axis: +X tips the top of a part forward (a bow, a nod);
       on a part that hangs down, like a thigh, +X swings it backward
    Y  the up axis: +Y turns a part to the character's left
    Z  the front-back axis: +Z tips the top of a part to the character's right
Several turns are applied outermost first: [("Y", 30), ("X", 20)] turns left,
then bows forward in that turned frame.
"""

from __future__ import annotations

import math

from soma import (
    IDENTITY,
    X,
    Y,
    Z,
    Skeleton,
    add,
    angle_between,
    cross,
    dot,
    length,
    qangle,
    qaxis,
    qconj,
    qfrom_to,
    qmul,
    qnorm,
    qrot,
    scale,
    sub,
    unit,
)

AXES = {"X": X, "Y": Y, "Z": Z}

SPINE = ("Spine1", "Spine2", "Chest")
NECK = ("Neck1", "Neck2", "Head")
LEGS = {"left": ("LeftLeg", "LeftShin", "LeftFoot", "LeftToeBase"), "right": ("RightLeg", "RightShin", "RightFoot", "RightToeBase")}
ARMS = {
    "left": ("LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand"),
    "right": ("RightShoulder", "RightArm", "RightForeArm", "RightHand"),
}


def turns(spec) -> tuple:
    """[(axis, degrees), ...] as one rotation, outermost turn first."""
    q = IDENTITY
    for axis, degrees in spec or ():
        q = qmul(q, qaxis(AXES[axis], degrees))
    return q


def mirror_turns(spec):
    """The same bend on the other side of the body: left-right (X) turns keep
    their sign, turns about the up and front axes flip."""
    return [(axis, degrees if axis == "X" else -degrees) for axis, degrees in spec or ()]


def mirror(desc: dict) -> dict:
    """A pose description flipped left for right."""

    def flip(p):
        return (-p[0], p[1], p[2])

    def side(limb):
        if limb is None:
            return None
        out = dict(limb)
        for key in ("at", "pole"):
            if key in out:
                out[key] = flip(out[key])
        for key in ("turn", "toes", "clavicle", "upper", "fore", "hand", "flat", "thigh", "shin"):
            if key in out:
                out[key] = mirror_turns(out[key])
        return out

    out = dict(desc)
    out["hips"] = flip(desc["hips"])
    for key in ("pelvis", "spine", "chest", "neck", "head"):
        if key in desc:
            out[key] = mirror_turns(desc[key])
    for part in ("foot", "hand"):
        out[f"left_{part}"] = side(desc.get(f"right_{part}"))
        out[f"right_{part}"] = side(desc.get(f"left_{part}"))
    if "planted" in desc:
        swap = {"left": "right", "right": "left"}
        out["planted"] = [f"{swap[p.split('_')[0]]}_{p.split('_')[1]}" for p in desc["planted"]]
    return out


def two_bone(a, target, l1, l2, pole):
    """Where the middle joint goes when a two-bone limb from `a` reaches for
    `target`, bending toward `pole`. Returns (middle, tip, reach) with reach
    the fraction of full extension used (1.0 = fully straight)."""
    to = sub(target, a)
    d = length(to)
    full = l1 + l2
    reach = d / full
    d = max(abs(l1 - l2) + 1e-4, min(d, full * 0.999))
    direction = unit(to)
    side = sub(pole, scale(direction, dot(pole, direction)))
    if length(side) < 1e-6:
        raise ValueError("the pole points straight along the limb")
    side = unit(side)
    cos_a = (l1 * l1 + d * d - l2 * l2) / (2.0 * l1 * d)
    cos_a = max(-1.0, min(1.0, cos_a))
    mid = add(a, add(scale(direction, l1 * cos_a), scale(side, l1 * math.sqrt(1.0 - cos_a * cos_a))))
    return mid, add(a, scale(direction, d)), reach


class Posed:
    """A built pose: local rotations by joint, the hips position, and the
    world-space result for checking and drawing."""

    def __init__(self, sk: Skeleton, name: str, desc: dict, root, world_rot: list):
        self.sk, self.name, self.desc, self.root = sk, name, desc, tuple(root)
        self.rotations = {}
        for i, joint in enumerate(sk.joints):
            parent = sk.parents[i]
            local = world_rot[i] if parent < 0 else qmul(qconj(world_rot[parent]), world_rot[i])
            self.rotations[joint] = qnorm(local)
        self.pos, self.rot = sk.fk(self.root, sk.rotation_list(self.rotations))

    def at(self, joint: str):
        return self.pos[self.sk.index[joint]]

    def card(self) -> dict:
        return {
            "root": [round(v, 5) for v in self.root],
            "rotations": {j: [round(c, 6) for c in q] for j, q in self.rotations.items()},
        }


def build(sk: Skeleton, name: str, desc: dict) -> Posed:
    """Joint rotations for one pose description.

    desc keys (all but `hips` optional):
      hips        (x, y, z) of the Hips joint
      pelvis      turns for the pelvis
      spine       turns shared evenly by Spine1, Spine2 and Chest
      chest       extra turns for the Chest alone
      neck, head  turns for the neck (shared by Neck1 and Neck2) and the head
      left_foot / right_foot
          at      (x, y, z) of the ankle joint
          pole    direction the knee points (default: forward)
          turn    turns for the foot itself, from flat and pointing forward
          loose   true: `turn` is instead from how the shin carries the foot (a foot in the air)
          toes    turns for the toes
      left_hand / right_hand, either placed or posed:
          at      (x, y, z) of the wrist; pole: direction the elbow points
          hand    turns for the hand, relative to the forearm
          flat    instead: turns for the hand in the world, from palm down, fingers out to its side
        or
          clavicle, upper, fore, hand   turns for each bone in turn
    """
    n = len(sk.joints)
    world = [None] * n  # world rotation per joint
    pos = [None] * n
    idx = sk.index

    def rest_dir(a: str, b: str):
        return unit(sub(sk.rest_world_pos[idx[b]], sk.rest_world_pos[idx[a]]))

    def carry(joint: str, delta=IDENTITY):
        """Place a joint by bending it `delta` (in body axes) from how its parent carries it."""
        i = idx[joint]
        p = sk.parents[i]
        if p < 0:
            world[i] = qmul(delta, sk.rest_world_rot[i])
            pos[i] = tuple(desc["hips"])
        else:
            lean = qmul(world[p], qconj(sk.rest_world_rot[p]))
            world[i] = qnorm(qmul(qmul(lean, delta), sk.rest_world_rot[i]))
            pos[i] = add(pos[p], qrot(world[p], sk.rest_pos[i]))

    def aim(joint: str, rotation):
        """Place a joint with an explicit world rotation."""
        i = idx[joint]
        p = sk.parents[i]
        world[i] = qnorm(rotation)
        pos[i] = add(pos[p], qrot(world[p], sk.rest_pos[i]))

    def lean_of(joint: str):
        i = idx[joint]
        return qmul(world[i], qconj(sk.rest_world_rot[i]))

    def share(spec, parts: int):
        return [(axis, degrees / parts) for axis, degrees in spec or ()]

    carry("Hips", turns(desc.get("pelvis")))
    for joint in SPINE:
        extra = turns(desc.get("chest")) if joint == "Chest" else IDENTITY
        carry(joint, qmul(turns(share(desc.get("spine"), len(SPINE))), extra))
    carry("Neck1", turns(share(desc.get("neck"), 2)))
    carry("Neck2", turns(share(desc.get("neck"), 2)))
    carry("Head", turns(desc.get("head")))
    for joint in ("Jaw", "LeftEye", "RightEye"):
        carry(joint)

    def limb(root: str, mid: str, tip: str, target, pole, rest_pole):
        """Solve a two-bone limb onto `target`, bending toward `pole`."""
        above = sk.parents[idx[root]]
        a = add(pos[above], qrot(world[above], sk.rest_pos[idx[root]]))
        l1, l2 = length(sk.rest_pos[idx[mid]]), length(sk.rest_pos[idx[tip]])
        middle, reached, reach = two_bone(a, target, l1, l2, pole)
        d1, d2 = unit(sub(middle, a)), unit(sub(reached, middle))
        along = unit(sub(reached, a))
        bend = unit(cross(along, sub(middle, a))) if length(cross(along, sub(middle, a))) > 1e-6 else unit(cross(along, pole))
        r1, r2 = rest_dir(root, mid), rest_dir(mid, tip)
        rest_bend = unit(cross(unit(add(r1, r2)), rest_pole))
        aim(root, qmul(qfrom_to(r1, rest_bend, d1, bend), sk.rest_world_rot[idx[root]]))
        aim(mid, qmul(qfrom_to(r2, rest_bend, d2, bend), sk.rest_world_rot[idx[mid]]))
        return reach

    reaches = {}
    for side, (thigh, shin, foot, toes) in LEGS.items():
        spec = desc.get(f"{side}_foot")
        if spec is None:
            for joint in (thigh, shin, foot, toes):
                carry(joint)
            continue
        if "at" in spec:
            facing = qrot(turns(spec.get("turn")), Z)
            pole = spec.get("pole", (facing[0], 0.0, facing[2]))
            reaches[f"{side}_foot"] = limb(thigh, shin, foot, spec["at"], pole, Z)
        else:
            carry(thigh, turns(spec.get("thigh")))
            carry(shin, turns(spec.get("shin")))
        if spec.get("loose"):
            carry(foot, turns(spec.get("turn")))  # hanging off the shin, not set against the ground
        else:
            aim(foot, qmul(turns(spec.get("turn")), sk.rest_world_rot[idx[foot]]))
        carry(toes, turns(spec.get("toes")))

    for side, (clavicle, upper, fore, hand) in ARMS.items():
        spec = desc.get(f"{side}_hand") or {}
        carry(clavicle, turns(spec.get("clavicle")))
        if "at" in spec:
            reaches[f"{side}_hand"] = limb(upper, fore, hand, spec["at"], spec.get("pole", (0.0, -1.0, -1.0)), (0.0, 0.0, -1.0))
        else:
            carry(upper, turns(spec.get("upper")))
            carry(fore, turns(spec.get("fore")))
        if "flat" in spec:
            aim(hand, qmul(turns(spec["flat"]), sk.rest_world_rot[idx[hand]]))  # palm down, turned in the world
        else:
            carry(hand, turns(spec.get("hand")))
        for joint in sk.joints:
            if joint.startswith(hand) and joint != hand:
                carry(joint)

    missing = [sk.joints[i] for i in range(n) if world[i] is None]
    if missing:
        raise ValueError(f"{name}: joints never placed: {missing}")
    posed = Posed(sk, name, desc, desc["hips"], world)
    posed.reaches = reaches
    return posed


# ---- reading a pose back in anatomical terms ------------------------------


def bend_of(sk: Skeleton, posed: Posed, joint: str):
    """How far a joint is bent from rest, relative to its parent, in degrees."""
    i = sk.index[joint]
    return qangle(qmul(posed.rotations[joint], qconj(sk.rest_rot[i])))


def hinge(posed: Posed, a: str, b: str, c: str) -> float:
    """Flexion at b, in degrees: 0 with a-b-c in a straight line."""
    return angle_between(sub(posed.at(b), posed.at(a)), sub(posed.at(c), posed.at(b)))
