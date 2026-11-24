"""The rider's poses: one set of skating poses that any of our characters can stand in.

Made the way the fight kit's moves are (scripts/fight/moves.py, whose Body
and arithmetic this uses): a pose is turns of whole body parts on the rig.py
skeleton, and where a hand has to be somewhere (on the board's edge, on the
coping) the arm is solved to that spot from this body's own shoulder and arm.
Nothing is tuned for one character.

Everything here is in the board's frame, which is also the rider's: he stands
sideways on it, left foot in front, so x (his left) is toward the nose, y is
behind him (the heel side) and z is up off the deck. The top of the deck is
the floor: 0. Where the board is on the ramp and which way up it is, is
ride.py's business; here the board never moves.

    stance(body, crouch)     rolling: feet over the bolts, knees bent by
                             `crouch` (0 standing tall, 1 as low as he pumps),
                             chest open toward the nose, arms out for balance
    turning(body, way)       the middle of a kickturn: shoulders leading the turn
    spread(body)             an air with no grab: tucked, both arms thrown wide
    grab(body)               an air with a grab: tucked deep, the back hand on
                             the board's toe edge between the feet
    plant(body, spot)        the handplant: tucked, the front hand on a spot
                             (the coping, wherever it is from the board on
                             this frame), the back hand on the board's edge
    standing(body, wave)     rolled to a stop: upright, and a hand raised

Plain Python: no Blender, no numpy.
"""

from __future__ import annotations

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fight"))
import board  # noqa: E402
import moves  # noqa: E402
from moves import add, mix, sub, times, unit  # noqa: E402

FRONT_YAW, BACK_YAW = 14.0, -6.0   # the front foot turned a little toward the nose, the back one square
OPEN_YAW = 24.0                    # the chest turned toward the nose
LOOK_YAW = 62.0                    # and the head further: he looks where he is going
STAND_DROP, PUMP_DROP = 0.07, 0.40  # the hips this share of the hip height lower: standing tall, and at the bottom of a pump
TUCK_DROP = 0.50                   # and tucked up in the air
LIMIT_ROOM = 5.0                   # degrees a shoulder is kept inside its limit, where the elbow's side can buy it
GRAB_DROP, GRAB_BEND = 0.56, 84.0  # folded right down, chest on the knees: what it takes for a hand to reach the deck
PLANT_HAND = "r"                   # the back hand goes on the coping: it is the one beside the tail as the board goes up past the lip
PALM_UP = 0.035                    # a hand on the deck: the middle of the palm this far above the wood


def feet_of(body) -> dict:
    """Both feet on the board: the front one over the front bolts, the back one on the tail, each with its middle on the centre line."""
    card = board.card()
    long = body.card["measure"].get("foot_long") or 0.135 * body.tall
    ball_y = -0.27 * long  # the ball of the foot is ahead of the foot's middle by about this
    return {"l": [card["feet"]["front"][0], ball_y, 0.0, 0.0, FRONT_YAW], "r": [card["feet"]["back"][0], ball_y, 0.0, 0.0, BACK_YAW]}


def hips_over(body, drop, bend, side=0.0):
    """Where the hips go: over the middle of the feet, lower by `drop` hip heights, and back a little as the chest bends forward, so his weight stays over the board."""
    card = board.card()
    middle = 0.5 * (card["feet"]["front"][0] + card["feet"]["back"][0])
    return (middle + side, 0.0018 * bend * body.leg, -drop * body.leg)


def lerp(a, b, t):
    return a + (b - a) * t


def about(v, axis, degrees):
    """A vector turned about an axis."""
    k, a = unit(axis), math.radians(degrees)
    return add(add(times(v, math.cos(a)), times(moves.cross(k, v), math.sin(a))), times(k, moves.dot(k, v) * (1.0 - math.cos(a))))


def make(body, hips, turns, arms, feet):
    """A pose from its parts, like the fight kit's, with one more care: which side an elbow is on is ours to choose,
    so where the side first asked for would turn a shoulder past its limit, the elbow comes round, by the least
    that brings the shoulder back inside it. The hand stays where it was asked to be."""
    arms = dict(arms)
    pose = moves.make(body, hips, turns, arms, feet)
    for tag in ("l", "r"):
        def over(p):
            past = moves.past_limits(body, p, slack=-LIMIT_ROOM)
            return past.get("upper_arm_" + tag, 0.0) + past.get("forearm_" + tag, 0.0)

        best = over(pose)
        if best <= 0.0:
            continue
        best += LIMIT_ROOM
        kind, a, b = arms[tag]
        axis = a if kind == "arm" else sub(a, body.joints(pose)["shoulder_" + tag])  # along the upper arm, or from the shoulder to the hand's spot
        for step in (15, -15, 30, -30, 45, -45, 60, -60, 80, -80, 100, -100, 125, -125, 150, -150, 180):
            trial = dict(arms)
            trial[tag] = (kind, a, about(b, axis, step))
            tried = moves.make(body, hips, turns, trial, feet)
            now = over(tried) + (LIMIT_ROOM if over(tried) > 0.0 else 0.0)
            if now < best - 0.25:
                best, arms, pose = now, trial, tried
                if best <= 0.0:
                    break
    return pose


def arms_out(low):
    """Arms for balance: by his sides and a little forward standing tall, wider and higher as he gets low."""
    left = ("arm", mix((0.55, -0.28, -0.78), (0.86, -0.30, -0.30), low), mix((0.62, -0.50, -0.55), (0.84, -0.48, 0.02), low))
    right = ("arm", mix((-0.50, -0.10, -0.86), (-0.84, -0.12, -0.42), low), mix((-0.52, -0.52, -0.62), (-0.78, -0.50, -0.10), low))
    return {"l": left, "r": right}


def stance(body, crouch, twist=0.0, lean=0.0, look=LOOK_YAW, arms=None):
    """Rolling. crouch 0 to 1; twist turns the shoulders further (degrees, toward the nose +); lean tips him along the board."""
    crouch = moves.clamp(crouch, 0.0, 1.25)
    drop = lerp(STAND_DROP, PUMP_DROP, crouch)
    bend = lerp(8.0, 34.0, crouch)
    turns = moves.trunk(OPEN_YAW + twist, roll=lean, bend=bend, head_yaw=look + 0.5 * twist, head_bend=-0.75 * bend)
    return make(body, hips_over(body, drop, bend), turns, arms or arms_out(min(1.0, crouch)), feet_of(body))


def turning(body, way):
    """The middle of a kickturn: knees bent, the shoulders ahead of the board in the turn (`way` +1: the nose swings to his right)."""
    arms = {"l": ("arm", (0.70, -0.52 if way > 0 else -0.05, -0.30), (0.55, -0.78 if way > 0 else -0.30, -0.05)),
            "r": ("arm", (-0.78, 0.25 if way > 0 else -0.40, -0.40), (-0.80, 0.05 if way > 0 else -0.62, -0.05))}
    return stance(body, 0.55, twist=-30.0 * way, look=LOOK_YAW - 26.0 * way, arms=arms)


def spread(body):
    """An air with no grab: knees up, both arms thrown wide and high."""
    turns = moves.trunk(OPEN_YAW - 6.0, bend=30.0, head_yaw=LOOK_YAW - 14.0, head_bend=-20.0)
    arms = {"l": ("arm", (0.86, -0.22, 0.38), (0.72, -0.30, 0.62)), "r": ("arm", (-0.88, -0.05, 0.30), (-0.74, -0.25, 0.60))}
    return make(body, hips_over(body, TUCK_DROP - 0.06, 30.0), turns, arms, feet_of(body))


def edge_spot():
    """Where a grabbing hand goes: the board's toe edge, between the feet."""
    x, y, z = board.card()["grabs"]["toe_edge"]
    return (x - 0.02, y + 0.01, z + PALM_UP)


def grab(body, other=None):
    """An air with a grab: tucked deep, the back hand on the toe edge between the feet, the front arm out for balance."""
    arms = {"l": other or ("arm", (0.84, -0.20, 0.40), (0.62, -0.25, 0.74)), "r": ("fist", edge_spot(), (-0.75, 0.45, 0.25))}
    pose = None
    for more in range(6):  # a shorter arm folds him further: lower, and the grabbing shoulder dropped, until the hand is there
        turns = moves.trunk(OPEN_YAW - 14.0, roll=-10.0 - 3.0 * more, bend=GRAB_BEND + 1.0 * more, head_yaw=LOOK_YAW - 10.0, head_bend=-55.0)
        pose = make(body, hips_over(body, GRAB_DROP + 0.025 * more, 0.6 * GRAB_BEND), turns, arms, feet_of(body))
        if moves.length(sub(body.joints(pose)["fist_r"], edge_spot())) < 0.01:
            break
    return pose


def plant(body, spot, deep=0.0):
    """The handplant: tucked, the back hand on `spot` (the coping, in the board's frame; out of reach, the arm
    points at it), the front arm out for balance. `deep` (0 to 1) is how far he folds down to reach a spot
    beside the board: all the way as the hand goes on and comes off, less with the board over his head."""
    bend = lerp(44.0, GRAB_BEND, deep)
    turns = moves.trunk(OPEN_YAW - 12.0, roll=lerp(-4.0, -10.0, deep), bend=bend, head_yaw=LOOK_YAW - 40.0, head_bend=lerp(-28.0, -55.0, deep))
    arms = {"l": ("arm", (0.30, -0.62, -0.72), (-0.35, -0.80, 0.48)), "r": ("fist", tuple(spot), (-0.6, 0.7, 0.1))}  # the front arm folded in by his knee, out of the deck's way
    return make(body, hips_over(body, lerp(TUCK_DROP - 0.04, GRAB_DROP, deep), 0.6 * bend), turns, arms, feet_of(body))


def plant_reach(body):
    """Where the planted hand is from the board with the board over his head: as far up as his arm goes from that tuck. (the spot, how high)."""
    at = body.joints(plant(body, (-0.1, -0.1, 0.4)))
    shoulder = at["shoulder_r"]
    top = shoulder[2] + 0.95 * (body.arm + body.fist)
    return (round(shoulder[0] * 0.8, 4), round(shoulder[1] * 0.8, 4), round(top, 4)), top


def standing(body, wave=0.0):
    """Rolled to a stop: upright on the board, arms easy; `wave` (0 to 1) raises the back hand in a greeting."""
    turns = moves.trunk(8.0, bend=3.0, head_yaw=0.0, head_bend=-2.0)
    easy = ("arm", (-0.30, -0.02, -0.95), (-0.24, -0.20, -0.95))
    up = ("arm", (-0.62, -0.22, 0.30), (-0.20, -0.28, 0.94))
    right = ("arm", unit(mix(easy[1], up[1], wave)), unit(mix(easy[2], up[2], wave)))
    arms = {"l": ("arm", (0.30, -0.02, -0.95), (0.24, -0.20, -0.95)), "r": right}
    return make(body, hips_over(body, STAND_DROP - 0.02, 3.0), turns, arms, feet_of(body))


def wrist_for_grab(body):
    """Where the wrist goes for a hand laid on the deck at the toe edge (animate.py lays a pinned hand flat, fingers the way the forearm comes in: from the toe side)."""
    x, y, z = edge_spot()
    return (x, y - 0.5 * body.fist, 0.03)


def hand_at(body, pose, tag):
    """Where the middle of a hand is in a pose, in the board's frame."""
    return body.joints(pose)["fist_" + tag]


__all__ = ["stance", "turning", "spread", "grab", "plant", "plant_reach", "standing", "feet_of", "edge_spot", "hand_at", "add", "sub", "times"]
