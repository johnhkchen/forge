# Work out a walk that fits this character, and leave it on the rig as a
# motion for animate.py to play.
#
# Run rig.py first. Nothing here is tuned per character: the gait comes from
# what rig.py measured (leg, arm and foot length, how wide the hips and thighs
# are, how bulky the build is) and, for the part a tape measure can't tell,
# four traits from 0 to 1 that the pipeline asks Opus for once per character
# from its brief (`GaitTraits`, saved as gait.json):
#   "weight"     0 featherlight ... 1 enormous
#   "stealth"    0 doesn't care who hears ... 1 creeping
#   "swagger"    0 contained ... 1 rolling, showy
#   "stiffness"  0 loose and springy ... 1 rigid, armored or old
# Leave "traits" at None and they are guessed from the build alone.
#
# How the numbers follow:
#   - speed from the leg: walkers of any size move alike at the same Froude
#     number, speed squared / (gravity x leg length). 0.25 is an easy human
#     walk; weight and stealth bring it down.
#   - stride from that speed (stride / leg = 2.3 x Froude^0.3, Alexander's
#     rule for walking animals), a little shorter for a stiff build; cadence
#     is speed / stride, slowed again by weight; the loop is rounded to whole
#     frames and the speed set to match, so the feet never skate.
#   - stance: feet near the hip joints, wider for weight and swagger, narrower
#     for stealth, never closer than the thighs are thick.
#   - bob: an upside-down pendulum over each planted foot, more for weight,
#     less for stealth. sway: the hips ride over the standing foot, a share
#     of the stance width that grows with weight.
#   - arms hang just clear of the body (measured), swing against the legs, by
#     more at speed and with swagger, less with stealth; long arms make long
#     swings because they are long.
#   - the spine leans with weight, ape-long arms and stealth, twists against
#     the hips; the head stays level; a tail follows the hips late, more
#     toward its tip, and is lifted clear of the ground.
#   - feet: a heavy walker puts them down flat and toes out; a light one
#     peels off the heel; a stealthy one lands on the ball and lifts higher.
#
# The motion is stored in a form any source could write (see animate.py):
# where the hips go, where each foot's ball is and whether it is planted, and
# how far each bone has turned from the T-pose, all in units of the hip height.
# So this file is one motion source; animate.py is what fits a motion to the
# character (leg IK, planted feet, joint limits) and bakes the keyframes.
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down.
# Prints RESULT {json}: the gait in plain numbers. Instant. Safe-mode compatible.

PARAMS = {
    "rig": None,     # the armature rig.py made; None = the first one in the scene
    "traits": None,  # {"weight": , "stealth": , "swagger": , "stiffness": } each 0-1; None = from the build
    "fps": 30,       # frames a second
    "name": "walk",  # what the motion is called
}

import bpy
import json
import math
from mathutils import Quaternion, Vector

GRAVITY = 9.81
X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

def ease(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)

def turn(axis, degrees):
    return Quaternion(axis, math.radians(degrees))

def wave(phase):
    return math.cos(2 * math.pi * phase)

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
leg = m["hip_height"]            # hip joint above the floor: the pendulum the walk swings on
reach = m["thigh"] + m["shin"]
tall = m["height"]

# ---- what kind of walker ----
bulk = clamp((m["bulk"] - 0.015) / 0.105, 0.0, 1.0)          # 0 a lean person ... 1 a troll
ape = clamp((m["arm_long"] / leg - 0.85) / 0.5, 0.0, 1.0)     # arms long for the legs
given = PARAMS["traits"] or {}
guess = {"weight": bulk, "stealth": 0.15, "swagger": 0.3, "stiffness": 0.3 + 0.3 * bulk}
traits = {k: round(clamp(float(given.get(k, guess[k])), 0.0, 1.0), 2) for k in guess}
heft = 0.5 * bulk + 0.5 * traits["weight"]
stealth, swagger, stiff = traits["stealth"], traits["swagger"], traits["stiffness"]

# ---- speed, stride, cadence ----
froude = clamp(0.25 * (1 - 0.55 * heft) * (1 - 0.15 * stealth) * (1 + 0.2 * (swagger - 0.3)), 0.06, 0.36)
stride = leg * 2.3 * froude ** 0.3 * (1 - 0.12 * stiff)
duty = clamp(0.6 + 0.06 * heft + 0.05 * stealth - 0.03 * swagger, 0.56, 0.7)  # share of the loop each foot is down
# Stance: feet near the hip joints, wider for weight and swagger, never closer than the thighs are thick.
# Sway: the hips ride toward the standing foot, a share of the stance.
half_stance = clamp(m["hip_half_width"] * (0.55 + 0.55 * heft + 0.25 * swagger - 0.3 * stealth), 0.9 * m["leg_thick"], 1.1 * m["foot_x"])
sway = half_stance * clamp(0.15 + 0.3 * heft + 0.15 * swagger - 0.1 * stealth, 0.08, 0.6)
aside = abs(half_stance - m["hip_half_width"]) + 0.5 * sway  # how far a foot stands to the side of its hip joint

# The hips ride highest over a planted foot and lowest with both feet down, like an upside-down
# pendulum. How high: the knee a little bent, more for stealth and weight. How low: what the style
# asks (a heavy walker drops into each step, a stealthy one glides), or what the legs need to reach
# the front and back of the stride, whichever is lower. A stride that would need a deep drop is
# shortened instead.
ankle_drop = leg - m["ankle_height"]
high = 0.012 * reach + leg * (0.008 + 0.07 * stealth + 0.008 * heft)  # below standing straight, at the top of each step
shortened = 0
while True:
    step = stride / 2
    pendulum = leg - math.sqrt(max(leg ** 2 - (step / 2) ** 2, 0.0))
    open_to = (0.975 * reach) ** 2 - (duty * stride / 2) ** 2 - aside ** 2
    need = ankle_drop - math.sqrt(open_to) if open_to > 0 else leg
    low = max(high + 2 * pendulum * clamp(0.5 + 0.9 * heft - 0.35 * stealth, 0.15, 1.5), need)
    if low - high <= 0.16 * leg or shortened >= 60:
        break
    stride *= 0.97
    shortened += 1
bob, crouch = (low - high) / 2, (low + high) / 2
tempo = 1.1 - 0.25 * heft
frames = max(12, int(round(PARAMS["fps"] * stride / (math.sqrt(froude * GRAVITY * leg) * tempo))))
seconds = frames / PARAMS["fps"]
speed = stride / seconds

hip_turn = 4 + 5 * swagger + 3 * heft - 2 * stiff
hip_drop = 2 + 3 * heft + 3 * swagger
chest_turn = hip_turn * (0.9 + 0.5 * swagger) * (1 - 0.4 * stiff)
chest_roll = clamp(1 + 5 * heft + 3 * swagger - 2 * stealth, 0.0, 12.0)
lean = 2 + 4 * heft + 5 * heft * ape + 9 * stealth + 20 * (froude - 0.15)

# ---- arms ----
shoulder_z, shoulder_x, arm = m["shoulder_height"], m["shoulder_half_width"], m["arm_long"]
hang = 4.0
for i in range(6, 11):  # the smallest angle off straight down that keeps the forearm and hand clear of the body
    along = arm * i / 10
    z = shoulder_z - along
    row = int(clamp(z / tall * len(m["body_half_widths"]), 0, len(m["body_half_widths"]) - 1))
    need = (m["body_half_widths"][row] + m["arm_thick"] - shoulder_x) / along
    hang = max(hang, math.degrees(math.asin(clamp(need, 0.0, 0.8))))
arm_swing = 22 * math.sqrt(froude / 0.25) * clamp(1 + 0.5 * swagger - 0.6 * stealth - 0.3 * stiff, 0.2, 1.6)
elbow = 8 + 14 * swagger + 22 * stealth + 8 * heft
arm_late = 0.03 + 0.05 * heft

# ---- feet ----
toe_out = clamp(4 + 10 * heft + 6 * swagger - 5 * stealth, 0.0, 18.0)
heel_lift = clamp(38 - 26 * heft - 8 * stiff, 4.0, 40.0)
toe_first = 10 * stealth
foot_lift = leg * (0.05 + 0.05 * stealth + 0.03 * (1 - heft))

# ---- a tail ----
tail_count = m["tail_bones"]
tail_swing = 5 + 6 * swagger + 4 * heft
tail_rise = 0.0
if tail_count:
    need = crouch + bob + 0.035 * tall - m["tail_tip_height"]
    tail_rise = clamp(math.degrees(math.asin(clamp(need / max(m["tail_long"], 1e-6), 0.0, 0.42))), 0.0, 24.0)

# ---- the motion, frame by frame ----
unit = 1.0 / leg
ankle = Vector(bone["foot_l"].head_local)
ball = Vector(bone["toe_l"].head_local)
hip = Vector(bone["thigh_l"].head_local)
middle = hip.y + (ball.y - ankle.y) - Vector(bone["hips"].head_local).y  # the ball of the foot, front to back from the hips, when the ankle is under the hip joint
hinge = {"l": Z, "r": Z}  # each elbow's axis with the arm straight out to the side: animate.py turns arm bones from a true T-pose
hips_track, feet, turns = [], {"l": [], "r": []}, {}
names = ["hips", "spine", "chest", "neck", "head", "upper_arm_l", "upper_arm_r", "forearm_l", "forearm_r"] + ["tail_%d" % (i + 1) for i in range(tail_count)]
for name in names:
    turns[name] = []
for f in range(frames + 1):
    phase = (f % frames) / frames
    over = wave(phase - duty / 2)  # +1 with the weight on the left foot, -1 on the right
    hips_track.append([round(sway * over * unit, 5), 0.0, round((-crouch + bob * wave(2 * (phase - duty / 2))) * unit, 5)])
    hips_yaw = -hip_turn * wave(phase)
    chest_yaw = chest_turn * wave(phase)
    turns["hips"].append(listed(turn(Z, hips_yaw) @ turn(Y, -hip_drop * over) @ turn(X, 0.25 * lean)))
    turns["spine"].append(listed(turn(Z, 0.6 * hips_yaw + 0.4 * chest_yaw) @ turn(Y, 0.5 * (chest_roll - hip_drop) * over) @ turn(X, 0.6 * lean)))
    turns["chest"].append(listed(turn(Z, chest_yaw) @ turn(Y, chest_roll * over) @ turn(X, lean)))
    turns["neck"].append(listed(turn(Z, 0.5 * chest_yaw) @ turn(Y, 0.5 * chest_roll * over) @ turn(X, 0.55 * lean)))
    turns["head"].append(listed(turn(Z, 0.25 * chest_yaw) @ turn(X, 0.25 * lean)))
    for tag, flip, lead in (("l", 1.0, 0.0), ("r", -1.0, 0.5)):
        back = wave(phase - arm_late - lead)  # +1 arm back, -1 arm forward: against the leg on its own side
        upper = turn(Z, 0.5 * chest_yaw) @ turn(X, arm_swing * back - 3 - 0.3 * lean) @ turn(Y, flip * (90 - hang))
        turns["upper_arm_" + tag].append(listed(upper))
        turns["forearm_" + tag].append(listed(upper @ turn(hinge[tag], -flip * (elbow + 0.8 * arm_swing * (1 - back) / 2))))
        own = (phase + lead) % 1.0
        if own < duty:  # planted: carried straight back at walking speed
            forward = stride * (duty / 2 - own)
            up = 0.0
            pitch = toe_first * (1 - ease(own / (0.2 * duty))) + heel_lift * clamp((own / duty - 0.55) / 0.45, 0.0, 1.0) ** 2
        else:  # swinging through, leaving and landing at walking speed so nothing jerks
            s = (own - duty) / (1 - duty)
            a, b, slope = -stride * duty / 2, stride * duty / 2, -stride * (1 - duty)
            forward = (2 * s ** 3 - 3 * s ** 2 + 1) * a + (s ** 3 - 2 * s ** 2 + s) * slope + (-2 * s ** 3 + 3 * s ** 2) * b + (s ** 3 - s ** 2) * slope
            up = foot_lift * math.sin(math.pi * s) ** 2
            pitch = heel_lift * (1 - ease(s / 0.45)) + toe_first * ease((s - 0.6) / 0.4)
        feet[tag].append([round(flip * half_stance * unit, 5), round((middle - forward) * unit, 5), round(up * unit, 5),
                          round(pitch, 3), round(flip * -toe_out, 3), 1 if own < duty else 0])
    for i in range(tail_count):  # each tail bone turns as the hips did a moment ago, more toward the tip
        late = phase - 0.07 * (i + 1)
        turns["tail_%d" % (i + 1)].append(listed(turn(Z, -tail_swing * (1 + 0.5 * i) * wave(late) * 0.6 + hips_yaw * 0.4)
                                                 @ turn(X, tail_rise + 1.5 * wave(2 * (late - duty / 2)))))

motion = {
    "name": PARAMS["name"], "version": 1, "fps": PARAMS["fps"], "frames": frames, "loop": True,
    "unit": "hip_height", "axes": "x left, y back, z up; the character faces -y",
    "travel": round(speed * unit, 5),  # hip heights a second the ground slides back under a planted foot (the walk stays in place)
    "hips": hips_track,                # [x, y, z] from where the hips rest
    "feet": feet,                      # per frame [x, y, z of the ball of the foot from the floor under the resting hips, pitch (toes down +), yaw, planted]
    "turns": turns,                    # per bone, per frame: how far it has turned from the T-pose, a quaternion [w, x, y, z] in the character's axes
}
rig["forge_motion: " + PARAMS["name"]] = json.dumps(motion)

gait = {
    "speed_m_s": round(speed, 2), "stride_m": round(stride, 2), "step_m": round(step, 2),
    "cadence_steps_per_min": round(120 / seconds), "loop_s": round(seconds, 3), "frames": frames,
    "froude": round(froude, 3), "foot_down_share": round(duty, 2),
    "stance_width_m": round(2 * half_stance, 2), "bob_cm": round(200 * bob, 1), "sway_cm": round(200 * sway, 1),
    "crouch_cm": round(100 * crouch, 1), "lean_deg": round(lean, 1),
    "hip_turn_deg": round(hip_turn, 1), "hip_drop_deg": round(hip_drop, 1), "chest_turn_deg": round(chest_turn, 1), "chest_roll_deg": round(chest_roll, 1),
    "arm_swing_deg": round(arm_swing, 1), "hand_travel_m": round(2 * arm * math.sin(math.radians(arm_swing)), 2),
    "arm_hang_deg": round(hang, 1), "elbow_deg": round(elbow, 1),
    "toe_out_deg": round(toe_out, 1), "heel_lift_deg": round(heel_lift, 1), "foot_lift_cm": round(100 * foot_lift, 1),
    "tail_swing_deg": round(tail_swing, 1) if tail_count else None, "tail_rise_deg": round(tail_rise, 1) if tail_count else None,
}
result = {
    "rig": rig.name, "motion": PARAMS["name"], "gait": gait, "traits": traits, "traits_from": "given" if PARAMS["traits"] else "the build",
    "stride_shortened_to_reach": shortened > 0,
    "from_the_model": {"leg_m": leg, "arm_m": m["arm_long"], "arm_to_leg": round(m["arm_long"] / leg, 2), "leg_to_height": round(leg / tall, 2),
                       "hip_width_m": round(2 * m["hip_half_width"], 2), "thigh_thick_m": round(2 * m["leg_thick"], 2),
                       "bulk": m["bulk"], "heft": round(heft, 2), "tail_m": m["tail_long"]},
}
print("RESULT " + json.dumps(result))
