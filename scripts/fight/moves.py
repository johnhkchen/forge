"""The fight kit's moves: one set of attacks, reactions and footwork that every character shares.

Done the way fighting games and WoW animate a fight: a few held key poses
and fast snaps between them, not flowing motion. Nothing is tuned for one
character. A pose is turns of whole body parts on the rig.py skeleton (as in
the tidy-mesh rom.py), and where a hand must be somewhere (a fist by the chin,
a fist on the other man's jaw) the arm is solved to that spot from this
body's own shoulder and arm lengths. So one move fits a short thick man and a
tall thin one.

    attacks     jab, cross, left_hook, uppercut, body_shot, haymaker
                Each has startup, active and recovery frames (STRIKES): a
                quick wind-up, a snap out to a fully stretched pose held for
                the active frames, a slower return to guard. Each names where
                it aims (high or low), the reaction it causes when it lands,
                how many frames both fighters freeze on contact (hitstop) and
                how hard it is.
    reactions   light_high (the head snaps), light_low (a fold over the
                body), heavy (a stagger back a step or two), block (the
                forearms take it, a small push back), knockdown (a long fall
                onto the mat, a small bounce, lying still)
    the rest    guard (with a light bounce), block (the arms up, before the
                blow lands), footwork (shuffle steps, in schedule.py)

A fighter is built in the usual stance (left foot and left hand in front).
The other stance is the same move in a mirror (mirrored()).

Everything here is in a fighter's own axes, as animate.py takes a motion:
x left, y back, z up, facing -y, in metres from the floor under the resting
hips. schedule.py puts two fighters on one timeline and writes the plain
motion; this file only makes poses.

Plain Python: no Blender, no numpy.
"""

from __future__ import annotations

import math

X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
TRUNK = ("hips", "spine", "chest", "neck", "head")
ARMS = ("upper_arm_l", "upper_arm_r")

# What each attack is. Frames are at 30 a second.
#   hand      which fist: "lead" (the front one) or "rear"
#   startup   frames from the first twitch to contact; contact is the first active frame
#   active    frames the stretched pose is held
#   recovery  frames to come back to guard
#   aims      "high" (the head) or "low" (the body)
#   causes    the reaction when it lands and the fight script names no other
#   hitstop   frames both fighters freeze on contact
#   power     how hard, for the film: 1 light, 2 heavy, 3 a knockout
#   reach     how far the arm is stretched at contact, as a share of its full length
STRIKES = {
    "jab": {"hand": "lead", "startup": 3, "active": 2, "recovery": 6, "aims": "high", "causes": "light_high", "hitstop": 3, "power": 1, "reach": 0.97},
    "cross": {"hand": "rear", "startup": 5, "active": 3, "recovery": 9, "aims": "high", "causes": "heavy", "hitstop": 7, "power": 2, "reach": 0.97},
    "left_hook": {"hand": "lead", "startup": 6, "active": 3, "recovery": 10, "aims": "high", "causes": "light_high", "hitstop": 5, "power": 1.5, "reach": 0.72},
    "uppercut": {"hand": "rear", "startup": 7, "active": 3, "recovery": 12, "aims": "high", "causes": "heavy", "hitstop": 7, "power": 2, "reach": 0.66},
    "body_shot": {"hand": "rear", "startup": 5, "active": 3, "recovery": 9, "aims": "low", "causes": "light_low", "hitstop": 5, "power": 1.5, "reach": 0.9},
    "haymaker": {"hand": "rear", "startup": 10, "active": 4, "recovery": 14, "aims": "high", "causes": "knockdown", "hitstop": 8, "power": 2.5, "reach": 0.88},
}
# How long each reaction lasts, in frames from contact, and what a blocked blow does to the freeze and the flash.
REACTIONS = {"light_high": 13, "light_low": 17, "heavy": 30, "block": 9, "knockdown": 34}
KNOCKOUT_HITSTOP = 12   # the blow that puts a man down freezes longest
BLOCKED_HITSTOP = 0.6   # a blocked blow freezes for this share of its hitstop (never fewer than 2 frames)
BLOCKED_POWER = 0.5
MOST_LUNGE = 0.5        # a blow that falls short steps in, by at most this share of the hip height


# ---- a little arithmetic: points are (x, y, z), turns are [w, x, y, z] ----

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def times(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)

def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

def length(a):
    return math.sqrt(dot(a, a))

def unit(a):
    n = length(a)
    return times(a, 1.0 / n) if n > 1e-9 else (0.0, 0.0, 0.0)

def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))

def turn(axis, degrees):
    half = math.radians(degrees) / 2.0
    s = math.sin(half)
    return (math.cos(half), axis[0] * s, axis[1] * s, axis[2] * s)

def qmul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw)

def qturned(q, v):
    """A point turned by a turn."""
    w, x, y, z = q
    u = (x, y, z)
    t = times(cross(u, v), 2.0)
    return add(add(v, times(t, w)), cross(u, t))

def qslerp(a, b, t):
    d = sum(a[i] * b[i] for i in range(4))
    if d < 0.0:
        b, d = tuple(-c for c in b), -d
    if d > 0.9995:
        out = tuple(a[i] + (b[i] - a[i]) * t for i in range(4))
    else:
        angle = math.acos(clamp(d, -1.0, 1.0))
        ka, kb = math.sin((1.0 - t) * angle) / math.sin(angle), math.sin(t * angle) / math.sin(angle)
        out = tuple(ka * a[i] + kb * b[i] for i in range(4))
    n = math.sqrt(sum(c * c for c in out))
    return tuple(c / n for c in out)

def q_of_axes(cx, cy, cz):
    """The turn that takes x, y and z to the three given directions (at right angles to each other)."""
    m00, m10, m20 = cx
    m01, m11, m21 = cy
    m02, m12, m22 = cz
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        q = (0.25 * s, (m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s)
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        q = ((m21 - m12) / s, 0.25 * s, (m01 + m10) / s, (m02 + m20) / s)
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        q = ((m02 - m20) / s, (m01 + m10) / s, 0.25 * s, (m12 + m21) / s)
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        q = ((m10 - m01) / s, (m02 + m20) / s, (m12 + m21) / s, 0.25 * s)
    n = math.sqrt(sum(c * c for c in q))
    return tuple(c / n for c in q)

def about_z(p, degrees):
    """A point turned about the upright axis (to the left as the angle grows)."""
    a = math.radians(degrees)
    return (p[0] * math.cos(a) - p[1] * math.sin(a), p[0] * math.sin(a) + p[1] * math.cos(a), p[2])


# ---- a body: what the moves need to know about one character ----

class Body:
    """One character's measurements, from what rig.py reported (card_of), and where its joints are in any pose."""

    def __init__(self, card):
        self.card = card
        self.j = {name: tuple(p) for name, p in card["joints"].items()}
        m = card["measure"]
        self.leg = m["hip_height"]
        self.tall = m["height"]
        self.upper = length(sub(self.j["forearm_l"], self.j["upper_arm_l"]))
        self.fore = length(sub(self.j["hand_l"], self.j["forearm_l"]))
        self.arm = self.upper + self.fore
        self.fist = card.get("fist_m") or 0.3 * self.fore              # the wrist to the middle of the fist
        self.head_front = card.get("head_front_m") or 0.055 * self.tall  # the middle of the head to the face
        self.chest_front = card.get("chest_front_m") or 0.07 * self.tall  # the spine to the front of the chest
        self.back = card.get("back_depth_m") or 0.085 * self.tall        # the hips to the furthest thing behind them: how high the hips are, lying down
        self.head_tall = max(0.12, self.tall - self.j["head"][2])       # the head joint (the top of the neck) to the crown
        hip, ball, ankle = self.j["thigh_l"], self.j["toe_l"], self.j["foot_l"]
        self.middle = hip[1] + (ball[1] - ankle[1]) - self.j["hips"][1]  # the ball of a foot, front to back, with its ankle under the hip joint
        self.wide = max(1.25 * m["hip_half_width"], 0.14 * self.leg)     # half the fighting stance, side to side
        self.reach_leg = m["thigh"] + m["shin"]

    def joints(self, pose):
        """Where the joints are in a pose, from the floor under the resting hips: the trunk, both arms and both fists."""
        j, q = self.j, pose["turns"]
        at = {"hips": add((0.0, 0.0, j["hips"][2]), pose["hips"])}
        for child, parent in (("spine", "hips"), ("chest", "spine"), ("neck", "chest"), ("head", "neck")):
            at[child] = add(at[parent], qturned(q[parent], sub(j[child], j[parent])))
        at["crown"] = add(at["head"], qturned(q["head"], (0.0, 0.0, self.head_tall)))
        at["head_middle"] = add(at["head"], qturned(q["head"], (0.0, 0.0, 0.5 * self.head_tall)))
        for tag, out in (("l", 1.0), ("r", -1.0)):
            shoulder = add(at["chest"], qturned(q["chest"], sub(j["upper_arm_" + tag], j["chest"])))
            upper = q["upper_arm_" + tag]
            elbow = add(shoulder, qturned(upper, (out * self.upper, 0.0, 0.0)))
            along = qturned(qmul(upper, turn(Z, -out * pose["elbow"][tag])), (out, 0.0, 0.0))
            wrist = add(elbow, times(along, self.fore))
            at["shoulder_" + tag], at["elbow_" + tag], at["wrist_" + tag] = shoulder, elbow, wrist
            at["fist_" + tag] = add(wrist, times(along, self.fist))
        return at


def card_of(rig_record, extras=None):
    """A body's card from what rig.py reported ("joints", "measure", "limits"), with anything measured on the mesh added."""
    card = {"joints": rig_record["joints"], "measure": rig_record["measure"], "limits": rig_record.get("limits", {})}
    card.update(extras or {})
    return card


# ---- poses ----

def trunk(yaw=0.0, roll=0.0, bend=0.0, head_yaw=0.0, head_bend=None, head_roll=0.0):
    """The hips, spine, chest, neck and head sharing a twist (yaw, left +), a side bend (roll, left +) and a
    bend forward. The hips take half of it and the legs follow them, so no joint of the spine is asked for
    much. The head has its own yaw (where it looks) and its own bend on top of the chest's."""
    twist = {"hips": 0.5, "spine": 0.75, "chest": 1.0}
    fold = {"hips": 0.45, "spine": 0.72, "chest": 1.0}
    out = {}
    for name in ("hips", "spine", "chest"):
        out[name] = qmul(qmul(turn(Z, yaw * twist[name]), turn(Y, roll * fold[name])), turn(X, bend * fold[name]))
    nod = 0.0 if head_bend is None else head_bend
    out["neck"] = qmul(qmul(turn(Z, 0.5 * (yaw + head_yaw)), turn(Y, roll + 0.5 * head_roll)), turn(X, bend + 0.5 * nod))
    out["head"] = qmul(qmul(turn(Z, head_yaw), turn(Y, roll + head_roll)), turn(X, bend + nod))
    return out


def arm_from(tag, upper, fore, pole=(0.0, 0.0, -1.0)):
    """An arm from the two ways it points: (the upper arm's turn, the elbow's bend in degrees).
    A straight arm has no elbow side of its own: `pole` says which side the elbow would be on."""
    d, f = unit(upper), unit(fore)
    bend = math.degrees(math.acos(clamp(dot(d, f), -1.0, 1.0)))
    hinge = cross(f, d) if tag == "l" else cross(d, f)
    if length(hinge) < 1e-4:
        side = sub(pole, times(d, dot(pole, d)))
        if length(side) < 1e-6:
            side = (0.0, 0.0, -1.0) if abs(d[2]) < 0.9 else (0.0, 1.0, 0.0)
        f2 = unit(sub(d, times(unit(side), 0.01)))
        hinge = cross(f2, d) if tag == "l" else cross(d, f2)
    hinge = unit(hinge)
    if tag == "l":
        q = q_of_axes(d, cross(hinge, d), hinge)
    else:
        q = q_of_axes(times(d, -1.0), cross(d, hinge), hinge)
    return q, bend


def arm_to(body, tag, shoulder, wrist, pole):
    """An arm solved from the shoulder to a spot for the wrist: two bones and the elbow, which goes to the `pole` side.
    Returns (the upper arm's turn, the elbow's bend, the way the forearm points, how far short of the spot the wrist is)."""
    l1, l2 = body.upper, body.fore
    gap = sub(wrist, shoulder)
    far = clamp(length(gap), abs(l1 - l2) + 1e-4, 0.999 * (l1 + l2))
    along = unit(gap)
    side = sub(pole, times(along, dot(pole, along)))
    if length(side) < 1e-6:
        side = (0.0, 0.3, -1.0)
        side = sub(side, times(along, dot(side, along)))
    side = unit(side)
    open_by = math.acos(clamp((l1 * l1 + far * far - l2 * l2) / (2.0 * l1 * far), -1.0, 1.0))
    upper = add(times(along, math.cos(open_by)), times(side, math.sin(open_by)))
    elbow = add(shoulder, times(upper, l1))
    fore = unit(sub(add(shoulder, times(along, far)), elbow))
    q, bend = arm_from(tag, upper, fore, pole)
    return q, bend, fore, max(0.0, length(gap) - far)


def make(body, hips, turns, hands, feet, bounce=0.0):
    """A pose from its parts. `hands` is {"l": ..., "r": ...}, each either
       ("fist", where the middle of the fist is, which side the elbow goes), or
       ("arm", the way the upper arm points, the way the forearm points)."""
    pose = {"hips": tuple(hips), "turns": dict(turns), "elbow": {"l": 0.0, "r": 0.0}, "feet": {tag: list(row) for tag, row in feet.items()}, "bounce": bounce}
    for tag in ("l", "r"):
        pose["turns"]["upper_arm_" + tag] = (1.0, 0.0, 0.0, 0.0)
    at = body.joints(pose)
    for tag in ("l", "r"):
        kind, a, b = hands[tag]
        if kind == "arm":
            q, bend = arm_from(tag, a, b)
        else:
            shoulder = at["shoulder_" + tag]
            fore = unit(sub(a, shoulder))
            for again in range(4):  # the wrist is a fist's length short of the spot, back along the forearm
                q, bend, fore, short = arm_to(body, tag, shoulder, sub(a, times(fore, body.fist)), b)
        pose["turns"]["upper_arm_" + tag], pose["elbow"][tag] = q, bend
    return pose


def mirrored(pose):
    """The same pose in a mirror: left and right change places. The other stance is the usual one, mirrored."""
    def flip(q):
        return (q[0], q[1], -q[2], -q[3])

    turns = {}
    for name, q in pose["turns"].items():
        other = name[:-2] + ("_r" if name.endswith("_l") else "_l") if name[-2:] in ("_l", "_r") else name
        turns[other] = flip(q)
    feet = {}
    for tag, row in pose["feet"].items():
        feet["r" if tag == "l" else "l"] = [-row[0], row[1], row[2], row[3], -row[4]]
    return {"hips": (-pose["hips"][0], pose["hips"][1], pose["hips"][2]), "turns": turns,
            "elbow": {"l": pose["elbow"]["r"], "r": pose["elbow"]["l"]}, "feet": feet, "bounce": pose["bounce"]}


def blend(a, b, t):
    """Part of the way from one pose to another (the feet are schedule.py's business: it knows when one is stepping)."""
    out = {"hips": mix(a["hips"], b["hips"], t), "turns": {name: qslerp(a["turns"][name], b["turns"][name], t) for name in a["turns"]},
           "elbow": {tag: a["elbow"][tag] + (b["elbow"][tag] - a["elbow"][tag]) * t for tag in ("l", "r")},
           "feet": {tag: list(mix(a["feet"][tag], b["feet"][tag], t)) for tag in ("l", "r")},
           "bounce": a["bounce"] + (b["bounce"] - a["bounce"]) * t}
    return out


# ---- the stance everything starts from and comes back to ----

GUARD_YAW = -30.0   # the chest turned a little away, the left shoulder in front
GUARD_BEND = 8.0
GUARD_DROP = 0.06   # the knees a little bent: the hips this share of the hip height lower


def feet_of(body, lead=0.0, rear=0.0, rear_heel=8.0, rear_yaw=-40.0, wide=1.0):
    """The feet in the fighting stance: left in front, right behind and turned out. `lead` and `rear` move each forward (m)."""
    return {"l": [wide * body.wide, body.middle - 0.20 * body.leg - lead, 0.0, 0.0, -8.0],
            "r": [-wide * body.wide, body.middle + 0.22 * body.leg - rear, 0.0, rear_heel, rear_yaw]}


def by_the_chin(body, at, yaw, tag, lower=0.0, nearer=0.0):
    """Where a guarding fist is: the front one out ahead of the chin, the back one by the jaw. Measured from the head, so it goes where the head goes."""
    if tag == "l":
        off = (0.09, -(0.24 + 0.32 * body.arm) + nearer, -0.35 * body.head_tall - lower)
    else:
        off = (-0.10, -(0.12 + 0.10 * body.arm) + nearer, -0.42 * body.head_tall - lower)
    return add(at["head_middle"], about_z(off, yaw))


ELBOW_DOWN = {"l": (0.45, 0.25, -1.0), "r": (-0.45, 0.25, -1.0)}


def built(body, hips, turns, feet, hands=None, yaw=GUARD_YAW, bounce=0.0):
    """A pose whose hands, where nothing else is said, guard the chin."""
    bare = {"hips": tuple(hips), "turns": dict(turns, upper_arm_l=(1.0, 0.0, 0.0, 0.0), upper_arm_r=(1.0, 0.0, 0.0, 0.0)), "elbow": {"l": 0.0, "r": 0.0}}
    at = body.joints(bare)
    want = {}
    for tag in ("l", "r"):
        given = (hands or {}).get(tag)
        if given is None:
            want[tag] = ("fist", by_the_chin(body, at, yaw, tag), ELBOW_DOWN[tag])
        elif callable(given):
            want[tag] = given(at)
        else:
            want[tag] = given
    return make(body, hips, turns, want, feet, bounce)


def guard(body):
    """Standing ready: knees bent, the left shoulder in front, both fists up. It bounces lightly (schedule.py adds that)."""
    return built(body, (0.0, -0.02 * body.leg, -GUARD_DROP * body.leg), trunk(GUARD_YAW, bend=GUARD_BEND, head_bend=-2.0), feet_of(body), bounce=1.0)


def block(body, low=False):
    """Covered up before the blow lands: both forearms in front of the face (or, for a blow to the body, elbows in and a crouch)."""
    turns = trunk(GUARD_YAW + 12.0, bend=GUARD_BEND + (12.0 if low else 5.0), head_bend=6.0)
    drop = GUARD_DROP + (0.05 if low else 0.02)

    def cover(tag):
        def where(at):
            side = 0.07 if tag == "l" else -0.07
            if low:
                spot = add(at["chest"], about_z((side * 1.3, -(body.chest_front + 0.10), 0.02), GUARD_YAW + 12.0))
            else:
                spot = add(at["head_middle"], about_z((side, -(body.head_front + 0.11), 0.0), GUARD_YAW + 12.0))
            return ("fist", spot, (0.6 if tag == "l" else -0.6, 0.3, -1.0))
        return where

    return built(body, (0.0, 0.0, -drop * body.leg), turns, feet_of(body), {"l": cover("l"), "r": cover("r")})


def covered_spot(body, pose, toward):
    """Where a blocked blow lands: on the forearms, between the two fists."""
    at = body.joints(pose)
    middle = mix(mix(at["fist_l"], at["wrist_l"], 0.5), mix(at["fist_r"], at["wrist_r"], 0.5), 0.5)
    return add(middle, times(toward, 0.05))


def target_on(body, pose, aims, toward, side=0.0, under=False):
    """The spot on a body a blow is aimed at, as the body stands in `pose`: where the middle of the fist should arrive.
    toward: the way to the attacker, level (a unit vector). side: -1 to 1, round the head toward the attacker's
    left or right (a hook lands on the side of the jaw). under: from below the chin (an uppercut)."""
    at = body.joints(pose)
    across = cross(Z, toward)  # to the attacker's right as he faces the defender
    if aims == "low":
        middle = mix(at["spine"], at["chest"], 0.55)
        return add(middle, times(toward, body.chest_front + 0.04))
    middle = at["head_middle"]
    if under:
        chin = add(at["head"], (0.0, 0.0, 0.0))
        return add(add(chin, times(toward, 0.75 * body.head_front)), (0.0, 0.0, -0.03))
    out = add(middle, times(toward, (body.head_front + 0.03) * math.sqrt(max(0.0, 1.0 - 0.8 * side * side))))
    return add(out, times(across, side * (0.75 * body.head_front + 0.03)))


def key(at, pose, ease, back=0.0, stay=()):
    """One key pose of a move: `at` frames from its start the body is in `pose`, having got there by `ease`:
       "out"    fast at first, then settling (a snap into a pose)
       "in"     slow at first, then fast (a fist thrown, a body falling)
       "inout"  gently both ends (coming back to guard)
       "hold"   no change since the key before
       "cut"    at once, on this frame
    back: how far the man has gone back from where the move began (m). stay: feet that have not moved since the key before."""
    return {"at": at, "pose": pose, "ease": ease, "back": back, "stay": tuple(stay)}


# ---- attacks ----

# The shape of each attack, in the usual stance. Angles in degrees, lengths as shares of the hip height.
#   wind       the chest's yaw and the extra crouch at the end of the wind-up, and where the striking fist is
#              drawn back to (from that shoulder, turned with the chest)
#   hit        the chest's yaw, roll and bend at contact, and the extra crouch
#   pole       which side the elbow is on at contact (for the left arm; mirrored for the right)
#   side/under how the fist comes at the head: round the side, or from below
SHAPES = {
    "jab": {"wind": (-24.0, 0.0, (0.02, -0.16, -0.12)), "hit": (-52.0, -2.0, 7.0, 0.0), "pole": (0.3, 0.3, -1.0), "side": 0.0},
    "cross": {"wind": (-44.0, 0.02, (-0.03, -0.02, -0.10)), "hit": (38.0, 3.0, 9.0, 0.01), "pole": (0.3, 0.3, -1.0), "side": 0.0, "pivot": True},
    "left_hook": {"wind": (-6.0, 0.04, (0.20, 0.02, -0.14)), "hit": (-66.0, -4.0, 6.0, 0.02), "pole": (1.0, 0.35, 0.12), "side": -0.85},
    "uppercut": {"wind": (-46.0, 0.12, (-0.04, -0.06, -0.42)), "hit": (34.0, 0.0, -4.0, -0.03), "pole": (0.25, 0.9, -1.0), "under": True, "pivot": True},
    "body_shot": {"wind": (-44.0, 0.10, (-0.05, -0.02, -0.26)), "hit": (40.0, 6.0, 18.0, 0.13), "pole": (0.8, 0.3, -0.5), "side": 0.0, "pivot": True},
    "haymaker": {"wind": (-64.0, 0.05, (-0.26, 0.20, 0.02)), "hit": (52.0, 8.0, 12.0, 0.03), "pole": (1.0, 0.3, 0.55), "side": 0.8, "pivot": True},
}


def strike(body, name, spot_of, start=None):
    """One attack against a spot: its key poses and its frame counts.

    spot_of(side, under) says where the middle of the fist should arrive, in this fighter's own axes (in the usual
    stance: schedule.py mirrors for the other one). The blow is built to reach it: the arm is stretched by the
    move's share of its length, and where that falls short the fighter steps in with the front foot (and, for a
    long way, drags the back one after it), by MOST_LUNGE of the hip height at most.

    Returns {"keys": [key(frames from the start, pose, how it gets there)], "startup", "active", "recovery",
             "contact" (the frame the fist arrives), "fist" (where it arrives), "spot", "miss_m", "lunge_m", "hand"}."""
    card, shape = STRIKES[name], SHAPES[name]
    tag = "l" if card["hand"] == "lead" else "r"
    other = "r" if tag == "l" else "l"
    flip = 1.0 if tag == "l" else -1.0
    pole = (flip * shape["pole"][0], shape["pole"][1], shape["pole"][2])
    spot = spot_of(shape.get("side", 0.0), bool(shape.get("under")))
    yaw, roll, bend, crouch = shape["hit"]
    want = card["reach"] * body.arm

    def stretched(lunge):
        drag = max(0.0, lunge - 0.2 * body.leg)
        drop = GUARD_DROP * body.leg + crouch * body.leg + 0.3 * min(lunge, 0.2 * body.leg)
        hips = (0.0, -0.02 * body.leg - lunge, -drop)
        feet = feet_of(body, lead=lunge, rear=drag, rear_heel=28.0 if shape.get("pivot") else 8.0, rear_yaw=-14.0 if shape.get("pivot") else -40.0)
        turns = trunk(yaw, roll, bend, head_yaw=0.0, head_bend=-2.0 - 0.4 * bend)
        return built(body, hips, turns, feet, {tag: ("fist", spot, pole)}, yaw=yaw)

    def gap(lunge):
        pose = stretched(lunge)
        at = body.joints(pose)
        return length(sub(sub(spot, times(unit(sub(at["fist_" + tag], at["wrist_" + tag])), body.fist)), at["shoulder_" + tag]))

    lunge = 0.0
    if gap(0.0) > want:
        lo, hi = 0.0, MOST_LUNGE * body.leg
        for step in range(18):
            mid = (lo + hi) / 2.0
            if gap(mid) > want:
                lo = mid
            else:
                hi = mid
        lunge = hi
    hit = stretched(lunge)
    fist = body.joints(hit)["fist_" + tag]

    wind_yaw, wind_crouch, back = shape["wind"]

    def drawn(at):
        return ("fist", add(at["shoulder_" + tag], about_z((back[0], back[1] - 0.12 * body.arm, back[2]), wind_yaw)), ELBOW_DOWN[tag] if name != "haymaker" else (-1.0, 0.4, 0.2))

    wind = built(body, (0.0, 0.0, -(GUARD_DROP + wind_crouch) * body.leg), trunk(wind_yaw, bend=GUARD_BEND + 30.0 * wind_crouch, head_bend=-2.0),
                 feet_of(body), {tag: drawn}, yaw=wind_yaw)
    s, a, r = card["startup"], card["active"], card["recovery"]
    keys = [key(max(1, s - 2), wind, "out"), key(s, hit, "in"), key(s + a - 1, hit, "hold"), key(s + a - 1 + r, guard(body), "inout")]
    return {"keys": keys, "startup": s, "active": a, "recovery": r, "contact": s, "fist": fist, "spot": spot, "miss_m": length(sub(fist, spot)),
            "lunge_m": lunge, "hand": tag, "other": other}


# ---- reactions ----

def loose(body, tag, out, forward, down, bend=35.0):
    """An arm thrown loose: the upper arm out, forward and down by those shares, the forearm bent a little further forward."""
    flip = 1.0 if tag == "l" else -1.0
    upper = unit((flip * out, -forward, -down))
    a = math.radians(bend)
    side = unit(sub((0.0, -1.0, 0.3), times(upper, dot((0.0, -1.0, 0.3), upper))))
    fore = add(times(upper, math.cos(a)), times(side, math.sin(a)))
    return ("arm", upper, fore)


def reaction(body, name, side=0.0, low=False):
    """What being hit looks like: key poses from the frame of contact on.

    The first key is on the contact frame itself and is already most of the way into the hit, so the freeze
    that follows (hitstop) holds a man who has plainly been struck. side: which way the blow came round
    (-1 from the attacker's left, +1 from his right, 0 straight), as the defender sees it mirrored already.

    Returns {"keys": [key(frames from contact, pose, how it gets there, how far back the man has gone (m), feet that
    stay where they were)], "frames", "down": lies there after}."""
    leg = body.leg
    g = guard(body)
    drop = GUARD_DROP * leg
    if name == "light_high":
        hit = built(body, (0.03 * side * leg, 0.035 * leg, -drop), trunk(GUARD_YAW + 10.0 * side, roll=3.0 * side, bend=-5.0, head_yaw=24.0 * side, head_bend=-20.0, head_roll=6.0 * side),
                    feet_of(body), yaw=GUARD_YAW)
        keys = [key(0, blend(g, hit, 0.7), "cut", 0.0), key(2, hit, "out", 0.0), key(4, hit, "hold", 0.0), key(REACTIONS[name], g, "inout", 0.0)]
    elif name == "light_low":
        def tucked(tag):
            def where(at):
                return ("fist", add(at["chest"], about_z((0.10 if tag == "l" else -0.10, -(body.chest_front + 0.10), -0.10), GUARD_YAW)), (0.8 if tag == "l" else -0.8, 0.4, -0.6))
            return where
        hit = built(body, (0.0, 0.07 * leg, -drop - 0.07 * leg), trunk(GUARD_YAW, bend=30.0, head_bend=-14.0), feet_of(body), {"l": tucked("l"), "r": tucked("r")})
        keys = [key(0, blend(g, hit, 0.7), "cut", 0.0), key(2, hit, "out", 0.0), key(6, hit, "hold", 0.0), key(REACTIONS[name], g, "inout", 0.0)]
    elif name == "block":
        b = block(body, low)
        shoved = dict(block(body, low))
        shoved = built(body, (0.0, 0.05 * leg, -drop - 0.02 * leg), trunk(GUARD_YAW + 12.0, bend=GUARD_BEND - 3.0, head_bend=8.0), feet_of(body),
                       {tag: ("fist", add(body.joints(b)["fist_" + tag], (0.0, 0.035 * leg, 0.0)), (0.6 if tag == "l" else -0.6, 0.3, -1.0)) for tag in ("l", "r")})
        keys = [key(0, blend(b, shoved, 0.7), "cut", 0.0), key(2, shoved, "out", 0.0), key(4, b, "inout", 0.0), key(REACTIONS[name], g, "inout", 0.0)]
    elif name == "heavy":
        snap = built(body, (0.04 * side * leg, 0.08 * leg, -drop + 0.01 * leg), trunk(GUARD_YAW + 14.0 * side, roll=6.0 * side, bend=-16.0, head_yaw=30.0 * side, head_bend=-24.0, head_roll=8.0 * side),
                     feet_of(body), {"l": loose(body, "l", 0.5, 0.75, 0.35), "r": loose(body, "r", 0.6, 0.45, 0.6)})
        reel = built(body, (0.0, 0.05 * leg, -drop - 0.02 * leg), trunk(GUARD_YAW + 6.0 * side, roll=-3.0 * side, bend=-8.0, head_yaw=12.0 * side, head_bend=-10.0),
                     feet_of(body, wide=1.25), {"l": loose(body, "l", 0.45, 0.5, 0.75), "r": loose(body, "r", 0.5, 0.3, 0.8)})
        catch = built(body, (0.0, -0.03 * leg, -drop - 0.06 * leg), trunk(GUARD_YAW, bend=22.0, head_bend=-12.0), feet_of(body, wide=1.2),
                      {"l": loose(body, "l", 0.3, 0.7, 0.6, 60.0), "r": loose(body, "r", 0.35, 0.5, 0.75, 70.0)})
        # Two steps back: the back foot first while the front one stays, then the front foot after it.
        keys = [key(0, blend(g, snap, 0.7), "cut", 0.0), key(2, snap, "out", 0.0), key(4, snap, "hold", 0.0),
                key(10, reel, "out", 0.26 * leg, stay=("l",)), key(17, catch, "out", 0.48 * leg, stay=("r",)), key(21, catch, "hold", 0.48 * leg),
                key(REACTIONS[name], g, "inout", 0.48 * leg)]
    elif name == "knockdown":
        lying = -(body.j["hips"][2] - body.back - 0.012)  # the hips this far down: the back just on the mat
        back = 0.56 * leg                                # and this far behind where the man stood
        snap = built(body, (0.03 * side * leg, 0.09 * leg, -drop + 0.03 * leg), trunk(GUARD_YAW + 10.0 * side, roll=5.0 * side, bend=-20.0, head_yaw=22.0 * side, head_bend=-26.0),
                     feet_of(body), {"l": loose(body, "l", 0.6, 0.7, 0.1), "r": loose(body, "r", 0.7, 0.5, 0.3)})

        def laid(pitch, height, y, arms, feet, head=0.0, head_yaw=0.0):
            flat = turn(X, pitch)
            turns = {name: flat for name in ("hips", "spine", "chest")}
            turns["neck"] = qmul(flat, turn(X, 0.5 * head))
            turns["head"] = qmul(qmul(flat, turn(Z, head_yaw)), turn(X, head))
            return make(body, (0.0, y, height), turns, arms, feet)

        def legs(hips_y, near, far):
            """Both feet flat on the mat in front of the hips, knees up: how far each ankle is from the hip joint, as a share of the leg."""
            row = {}
            for tag, share in (("l", near), ("r", far)):
                flip = 1.0 if tag == "l" else -1.0
                row[tag] = [flip * (body.card["measure"]["hip_half_width"] + 0.07), hips_y - share * body.reach_leg + body.middle, 0.0, 0.0, flip * 14.0]
            return row

        def spread(up, bend, drop_by):
            """Arms thrown out to the sides: `up` toward the head, the elbows a little bent."""
            out = {}
            for tag, flip in (("l", 1.0), ("r", -1.0)):
                upper = unit((flip * 0.9, up[tag], -drop_by))
                fore = unit((flip * 0.75, up[tag] + bend, -drop_by))
                out[tag] = ("arm", upper, fore)
            return out

        tip = built(body, (0.0, 0.30 * leg, -0.30 * leg), trunk(0.0, bend=-40.0, head_bend=-10.0), feet_of(body, lead=-0.10 * leg, wide=1.1),
                    {"l": loose(body, "l", 0.8, 0.5, -0.4, 20.0), "r": loose(body, "r", 0.8, 0.4, -0.3, 20.0)})
        land = laid(-90.0, lying, back, spread({"l": 0.25, "r": 0.5}, 0.35, 0.10), legs(back, 0.80, 0.66), head=6.0)
        hop = laid(-83.0, lying + 0.05, back + 0.015, spread({"l": 0.3, "r": 0.55}, 0.45, -0.12), legs(back + 0.015, 0.80, 0.66), head=16.0)
        still = laid(-90.0, lying, back, spread({"l": 0.15, "r": 0.6}, 0.3, 0.10), legs(back, 0.86, 0.70), head=3.0, head_yaw=-18.0)
        keys = [key(0, blend(g, snap, 0.7), "cut", 0.0), key(3, snap, "out", 0.0), key(11, tip, "in", 0.0), key(17, land, "in", 0.0),
                key(20, hop, "out", 0.0), key(24, land, "in", 0.0), key(REACTIONS[name], still, "inout", 0.0)]
    else:
        raise ValueError("no reaction called %r: choose from %s" % (name, ", ".join(sorted(REACTIONS))))
    return {"keys": keys, "frames": REACTIONS[name], "down": name == "knockdown"}
