# A range-of-motion routine: the same short workout for every character, to
# see what its skin, clothes and joints do when the body is pushed further
# than a walk pushes it. Leaves it on the rig as a motion for animate.py to
# play, like walk.py does.
#
# Run rig.py first. The routine stands in place, feet planted under the hips,
# and goes through, one after another, easing between them and holding each
# a moment:
#   arms overhead, a twist to each side (hands up in a guard), a side bend
#   to each side (the far arm over the head), a bend forward, a squat with
#   the arms out in front, a straight punch with each hand, and back to rest.
# Nothing is tuned per character: the poses are turns of whole body parts,
# the feet go where the hips are, and the arms hang clear of the body by what
# rig.py measured (as in walk.py). animate.py fits it, solves the legs to the
# planted feet (a deep squat lifts the heels if the ankles ask), and clamps
# every joint to its limit, so what it reports ("clamped") says which joints
# this routine asks too much of.
#
# The motion is in the plain form animate.py reads (see there): it does not
# loop and does not travel.
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down.
# Prints RESULT {json}. Instant. Safe-mode compatible.

PARAMS = {
    "rig": None,    # the armature rig.py made; None = the first one in the scene
    "fps": 30,      # frames a second
    "name": "rom",  # what the motion is called
    "move_s": 0.6,  # seconds to go from one pose to the next
    "hold_s": 0.4,  # seconds to hold each pose
}

import bpy
import json
import math
from mathutils import Quaternion, Vector

X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
TRUNK = ("hips", "spine", "chest", "neck", "head")
ARMS = ("upper_arm_l", "upper_arm_r", "forearm_l", "forearm_r")


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

def ease(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)

def turn(axis, degrees):
    return Quaternion(axis, math.radians(degrees))

def listed(q):
    return [round(c, 5) for c in q]


rig = bpy.data.objects.get(PARAMS["rig"]) if PARAMS["rig"] else None
if rig is None:
    found = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    if not found:
        raise ValueError("no skeleton in the scene: run rig.py first")
    rig = found[0]
if "forge_rig" not in rig:
    raise ValueError("%r was not made by rig.py (it has no measurements)" % rig.name)
m = json.loads(rig["forge_rig"])["measure"]
bone = rig.data.bones
leg, tall = m["hip_height"], m["height"]

# The arms hang just clear of the body, as in walk.py.
shoulder_z, shoulder_x, arm = m["shoulder_height"], m["shoulder_half_width"], m["arm_long"]
hang = 4.0
for i in range(6, 11):
    along = arm * i / 10
    row = int(clamp((shoulder_z - along) / tall * len(m["body_half_widths"]), 0, len(m["body_half_widths"]) - 1))
    need = (m["body_half_widths"][row] + m["arm_thick"] - shoulder_x) / along
    hang = max(hang, math.degrees(math.asin(clamp(need, 0.0, 0.8))))


def arm(tag, *turns, elbow=8.0):
    """Upper arm and forearm, from hanging by the side: `turns` (axis, degrees) applied after it, outermost first."""
    flip = 1.0 if tag == "l" else -1.0
    upper = turn(Y, flip * (90 - hang))
    for axis, degrees in reversed(turns):
        upper = turn(axis, degrees) @ upper
    return {"upper_arm_" + tag: upper, "elbow_" + tag: elbow}


def guard(tag, yaw=0.0):
    """Fists up in front of the chin: upper arm forward and down, elbow bent well within a person's reach."""
    return arm(tag, (Z, yaw), (X, -60), elbow=100)


def trunk(yaw=0.0, roll=0.0, bend=0.0, head_yaw=None):
    """The hips, spine, chest, neck and head share a twist (yaw), a side bend (roll) and a bend forward, more toward the chest."""
    shares = {"hips": 0.15, "spine": 0.55, "chest": 1.0, "neck": 1.0, "head": 1.0}
    out = {}
    for name in TRUNK:
        s = shares[name]
        y = (head_yaw if head_yaw is not None else 0.6 * yaw) if name == "head" else yaw * s
        b = bend * (0.4 if name in ("neck", "head") else s)
        out[name] = turn(Z, y) @ turn(Y, roll * s) @ turn(X, b)
    return out


def pose(hips_drop=0.0, **parts):
    q = {}
    for part in parts.values():
        q.update(part)
    return {"drop": hips_drop, "turns": q}


rest = pose(t=trunk(), a=arm("l"), b=arm("r"))
routine = [
    ("rest", rest),
    ("arms overhead", pose(t=trunk(bend=-6), a=arm("l", (Y, -165), elbow=4), b=arm("r", (Y, 165), elbow=4))),
    ("twist left", pose(t=trunk(yaw=45), a=guard("l", 45), b=guard("r", 45))),
    ("twist right", pose(t=trunk(yaw=-45), a=guard("l", -45), b=guard("r", -45))),
    ("side bend left", pose(t=trunk(roll=28), a=arm("l"), b=arm("r", (Y, 150), elbow=10))),
    ("side bend right", pose(t=trunk(roll=-28), a=arm("l", (Y, -150), elbow=10), b=arm("r"))),
    ("bend forward", pose(t=trunk(bend=70), a=arm("l"), b=arm("r"))),
    ("squat", pose(hips_drop=0.38, t=trunk(bend=25), a=arm("l", (X, -85), elbow=5), b=arm("r", (X, -85), elbow=5))),
    ("punch left", pose(t=trunk(yaw=-30), a=arm("l", (Z, -30), (X, -88), elbow=3), b=guard("r", -30))),
    ("punch right", pose(t=trunk(yaw=30), a=guard("l", 30), b=arm("r", (Z, 30), (X, -88), elbow=3))),
    ("rest again", rest),
]
KEYED = TRUNK + ("upper_arm_l", "upper_arm_r")
for name, p in routine:
    for b in KEYED + ("elbow_l", "elbow_r"):  # every pose names every bone it moves, so the easing never leaves one behind
        p["turns"].setdefault(b, rest["turns"][b])

# ---- the motion, frame by frame ----
fps = PARAMS["fps"]
move, hold = max(1, round(PARAMS["move_s"] * fps)), max(1, round(PARAMS["hold_s"] * fps))
unit = 1.0 / leg
ankle = Vector(bone["foot_l"].head_local)
ball = Vector(bone["toe_l"].head_local)
hip = Vector(bone["thigh_l"].head_local)
middle = hip.y + (ball.y - ankle.y) - Vector(bone["hips"].head_local).y  # the ball of the foot, front to back, with the ankle under the hip joint
stance = clamp(m["hip_half_width"], 0.9 * m["leg_thick"], 1.1 * m["foot_x"])

keys, f = [], 0  # (frame, pose): each pose reached, then held
for i, (name, p) in enumerate(routine):
    if i:
        f += move
    keys.append((f, p, name))
    f += hold
frames = f

hips_track, feet, turns = [], {"l": [], "r": []}, {b: [] for b in TRUNK + ARMS}
for f in range(frames + 1):
    k = max(i for i, key in enumerate(keys) if key[0] <= f)
    a = keys[k]
    b = keys[min(k + 1, len(keys) - 1)]
    t = 0.0 if b[0] <= a[0] + hold or f <= a[0] + hold else ease((f - a[0] - hold) / (b[0] - a[0] - hold))
    hips_track.append([0.0, 0.0, round(-((1 - t) * a[1]["drop"] + t * b[1]["drop"]), 5)])
    for name in KEYED:
        turns[name].append(listed(a[1]["turns"][name].slerp(b[1]["turns"][name], t)))
    # An elbow is a hinge: the forearm is the upper arm turned about it by the eased bend. (Easing the two
    # turns apart would twist the forearm sideways between poses, which no elbow can do.)
    for tag, flip in (("l", 1.0), ("r", -1.0)):
        upper = a[1]["turns"]["upper_arm_" + tag].slerp(b[1]["turns"]["upper_arm_" + tag], t)
        bend = (1 - t) * a[1]["turns"]["elbow_" + tag] + t * b[1]["turns"]["elbow_" + tag]
        turns["forearm_" + tag].append(listed(upper @ turn(Z, -flip * bend)))
    for tag, flip in (("l", 1.0), ("r", -1.0)):
        feet[tag].append([round(flip * stance * unit, 5), round(middle * unit, 5), 0.0, 0.0, 0.0, 1])

motion = {
    "name": PARAMS["name"], "version": 1, "fps": fps, "frames": frames, "loop": False,
    "unit": "hip_height", "axes": "x left, y back, z up; the character faces -y",
    "travel": 0.0, "hips": hips_track, "feet": feet, "turns": turns,
}
rig["forge_motion: " + PARAMS["name"]] = json.dumps(motion)
result = {
    "rig": rig.name, "motion": PARAMS["name"], "frames": frames, "seconds": round(frames / fps, 2),
    "poses": [{"pose": name, "frame": frame} for frame, p, name in keys], "arm_hang_deg": round(hang, 1),
}
print("RESULT " + json.dumps(result))
