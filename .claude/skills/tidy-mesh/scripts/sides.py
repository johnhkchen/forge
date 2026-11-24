# The audition sides: the same short scenes for every character trying out for
# a part, so they can be compared fairly (scripts/casting). Like rom.py it is
# a routine standing in place that leaves a motion on the rig for animate.py
# to play, and nothing in it is tuned per character.
#
# It holds the moments a walk never asks for and the flat cards find hardest:
#   standing easy, breathing (does the figure hold still without shimmering),
#   a wave with the right hand (a shoulder and an elbow up high),
#   a head turn each way (the neck),
#   the right arm raised straight overhead (a shoulder at its furthest),
#   a deep squat, held (the knees, the place they broke before),
# and back to rest. The range-of-motion routine (rom.py) has the rest of what
# an audition asks for: both arms overhead, twists, a squat, punches.
#
# The poses are turns of whole body parts as in rom.py; the feet stay where the
# hips are; animate.py fits it, solves the legs to the planted feet (a deep
# squat lifts the heels if the ankles ask) and clamps every joint to its
# limit, so its "clamped" report says which joints these sides ask too much of.
# RESULT lists each scene with the frames it takes, for the casting page.
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down.
# Prints RESULT {json}. Instant. Safe-mode compatible.

PARAMS = {
    "rig": None,      # the armature rig.py made; None = the first one in the scene
    "fps": 30,        # frames a second
    "name": "sides",  # what the motion is called
    "squat": 0.55,    # how far the hips drop in the deep squat, in hip heights (rom.py's squat is 0.38)
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

# The arms hang just clear of the body, as in walk.py and rom.py.
shoulder_z, shoulder_x, arm_long = m["shoulder_height"], m["shoulder_half_width"], m["arm_long"]
hang = 4.0
for i in range(6, 11):
    along = arm_long * i / 10
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


def wave(swing):
    """The right hand up by the head, palm out: the upper arm out to the side and forward, the forearm up. `swing`
    turns the whole arm about the front-to-back line, which carries the hand side to side."""
    return arm("r", (Y, swing), (Z, -55), (X, -95), elbow=95)


def trunk(yaw=0.0, roll=0.0, bend=0.0, neck=None, head=None):
    """The hips, spine, chest, neck and head share a twist (yaw), a side bend (roll) and a bend forward, more toward
    the chest. A turn is where a bone faces, not how far it is from the one before, so a head turn names the neck's
    and the head's own."""
    shares = {"hips": 0.15, "spine": 0.55, "chest": 1.0, "neck": 1.0, "head": 1.0}
    out = {}
    for name in TRUNK:
        s = shares[name]
        y = yaw * s
        if name == "neck" and neck is not None:
            y = neck
        if name == "head":
            y = head if head is not None else 0.6 * yaw
        b = bend * (0.4 if name in ("neck", "head") else s)
        out[name] = turn(Z, y) @ turn(Y, roll * s) @ turn(X, b)
    return out


def pose(hips_drop=0.0, **parts):
    q = {}
    for part in parts.values():
        q.update(part)
    return {"drop": hips_drop, "turns": q}


rest = pose(t=trunk(), a=arm("l"), b=arm("r"))
breathe = pose(t=trunk(bend=-3, roll=1.5), a=arm("l", elbow=12), b=arm("r", elbow=12))
squat = PARAMS["squat"]
# (scene, pose, seconds to get there, seconds to hold it). A scene is the poses that share its name.
routine = [
    ("stand easy", rest, 0.0, 0.6),
    ("stand easy", breathe, 1.2, 0.2),
    ("stand easy", rest, 1.2, 0.2),
    ("stand easy", breathe, 1.2, 0.2),
    ("stand easy", rest, 1.2, 0.4),
    ("wave", pose(t=trunk(roll=-3), a=arm("l"), b=wave(-14)), 0.6, 0.1),
    ("wave", pose(t=trunk(roll=-3), a=arm("l"), b=wave(14)), 0.3, 0.05),
    ("wave", pose(t=trunk(roll=-3), a=arm("l"), b=wave(-14)), 0.3, 0.05),
    ("wave", pose(t=trunk(roll=-3), a=arm("l"), b=wave(14)), 0.3, 0.05),
    ("wave", pose(t=trunk(roll=-3), a=arm("l"), b=wave(-14)), 0.3, 0.1),
    ("wave", rest, 0.6, 0.3),
    ("head turn", pose(t=trunk(yaw=8, neck=35, head=70), a=arm("l"), b=arm("r")), 0.7, 0.6),
    ("head turn", pose(t=trunk(yaw=-8, neck=-35, head=-70), a=arm("l"), b=arm("r")), 1.0, 0.6),
    ("head turn", rest, 0.7, 0.3),
    ("arm overhead", pose(t=trunk(roll=6, bend=-4), a=arm("l"), b=arm("r", (Y, 172), elbow=3)), 0.7, 0.8),
    ("arm overhead", rest, 0.7, 0.3),
    ("deep squat", pose(hips_drop=squat, t=trunk(bend=32), a=arm("l", (X, -85), elbow=5), b=arm("r", (X, -85), elbow=5)), 1.0, 1.0),
    ("deep squat", rest, 1.0, 0.6),
]
KEYED = TRUNK + ("upper_arm_l", "upper_arm_r")
for name, p, _, _ in routine:
    for b in KEYED + ("elbow_l", "elbow_r"):  # every pose names every bone it moves, so the easing never leaves one behind
        p["turns"].setdefault(b, rest["turns"][b])

# ---- the motion, frame by frame ----
fps = PARAMS["fps"]
unit = 1.0 / leg
ankle = Vector(bone["foot_l"].head_local)
ball = Vector(bone["toe_l"].head_local)
hip = Vector(bone["thigh_l"].head_local)
middle = hip.y + (ball.y - ankle.y) - Vector(bone["hips"].head_local).y  # the ball of the foot, front to back, with the ankle under the hip joint
stance = clamp(m["hip_half_width"], 0.9 * m["leg_thick"], 1.1 * m["foot_x"])

keys, f = [], 0  # (frame reached, frame left, pose, scene): each pose reached, then held
for i, (name, p, move_s, hold_s) in enumerate(routine):
    if i:
        f += max(1, round(move_s * fps))
    reached = f
    f += max(1, round(hold_s * fps))
    keys.append((reached, f, p, name))
frames = f

hips_track, feet, turns = [], {"l": [], "r": []}, {b: [] for b in TRUNK + ARMS}
for f in range(frames + 1):
    k = max(i for i, key in enumerate(keys) if key[0] <= f)
    a = keys[k]
    b = keys[min(k + 1, len(keys) - 1)]
    t = 0.0 if b[0] <= a[1] or f <= a[1] else ease((f - a[1]) / (b[0] - a[1]))
    hips_track.append([0.0, 0.0, round(-((1 - t) * a[2]["drop"] + t * b[2]["drop"]), 5)])
    for name in KEYED:
        turns[name].append(listed(a[2]["turns"][name].slerp(b[2]["turns"][name], t)))
    # An elbow is a hinge: the forearm is the upper arm turned about it by the eased bend.
    for tag, flip in (("l", 1.0), ("r", -1.0)):
        upper = a[2]["turns"]["upper_arm_" + tag].slerp(b[2]["turns"]["upper_arm_" + tag], t)
        bend = (1 - t) * a[2]["turns"]["elbow_" + tag] + t * b[2]["turns"]["elbow_" + tag]
        turns["forearm_" + tag].append(listed(upper @ turn(Z, -flip * bend)))
    for tag, flip in (("l", 1.0), ("r", -1.0)):
        feet[tag].append([round(flip * stance * unit, 5), round(middle * unit, 5), 0.0, 0.0, 0.0, 1])

# Each scene: from the frame its first pose starts to move (the end of the scene before) to the frame its last pose is left.
scenes = []
for i, (reached, left, p, name) in enumerate(keys):
    if scenes and scenes[-1]["scene"] == name:
        scenes[-1]["to"] = left
    else:
        scenes.append({"scene": name, "from": keys[i - 1][1] if i else 0, "to": left})

motion = {
    "name": PARAMS["name"], "version": 1, "fps": fps, "frames": frames, "loop": False,
    "unit": "hip_height", "axes": "x left, y back, z up; the character faces -y",
    "travel": 0.0, "hips": hips_track, "feet": feet, "turns": turns,
}
rig["forge_motion: " + PARAMS["name"]] = json.dumps(motion)
result = {
    "rig": rig.name, "motion": PARAMS["name"], "frames": frames, "seconds": round(frames / fps, 2),
    "scenes": scenes, "squat_drop": squat, "arm_hang_deg": round(hang, 1),
}
print("RESULT " + json.dumps(result))
