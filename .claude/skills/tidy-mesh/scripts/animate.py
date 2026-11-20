# Play a motion on a rigged character: fit it to this character's bones, keep
# planted feet planted, keep every joint inside its limits, and bake it to
# keyframes as an action the .glb can carry.
#
# Run rig.py first, then a motion source. walk.py is one (it leaves a motion
# named "walk" on the rig); a motion from anywhere else (a motion-capture clip,
# an AI motion model's output turned into this form) goes through the same
# steps. A motion is plain data:
#   "fps", "frames" (frame `frames` is frame 0 again when "loop" is true)
#   "hips":   per frame [x, y, z], where the hips are from where they rest
#   "feet":   {"l": per frame [x, y, z, pitch, yaw, planted], "r": ...}: the
#             ball of the foot, from the floor under the resting hips; pitch in
#             degrees (toes down is +), yaw in degrees, planted 1 or 0
#   "turns":  {bone: per frame [w, x, y, z]}: how far that bone has turned
#             from the T-pose, in the character's own axes (x left, y back, z
#             up). Bones the motion leaves out follow their parent; bones the
#             character lacks (a tail on a person) are skipped.
#   "travel": how fast the ground slides back under a planted foot
#   lengths are in units of the hip height, so one motion fits any size.
#
# What happens to it here, in order:
#   1. Fit. Lengths are scaled by this character's hip height; each bone is
#      turned from its own rest pose by the motion's amount.
#   2. Plant the feet. Each leg is solved from the hip joint to where the foot
#      must be (two bones and a hinge: exact, no iteration), so the ball of a
#      planted foot stays on the floor and moves back at exactly "travel". If
#      the legs can't reach, the hips are lowered for the whole loop (never the
#      foot moved). If an ankle would bend past its limit the heel lifts.
#   3. Limits. Every bone's turn is clamped to its "limit_deg" (the same
#      numbers as its Limit Rotation constraint). "clamped" says which bones
#      needed it and how often; a clamp on a leg can let a foot slide, and the
#      check below will show it.
#   4. Bake: one key per frame on every bone, in an action named for the motion.
#
# "then" in the result names what to run next on the baked action: a rig with
# cloth bones (cloth.py) asks for swing.py, which makes loose cloth hang and
# swing with whatever motion was just baked.
#
# "check": True then plays the baked action back in Blender and measures it:
# how far a planted foot slid (cm per step), how far anything went through the
# floor, turns outside a limit, and whether the last frame equals the first.
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down.
# Prints RESULT {json}. A second or two. Safe-mode compatible.

PARAMS = {
    "rig": None,       # the armature rig.py made; None = the first one in the scene
    "motion": "walk",  # the name of a motion a source left on the rig, or the motion itself as a dict
    "action": None,    # what to call the baked action; None = the motion's name
    "check": True,     # play it back and measure foot slide, floor, limits and the loop
}

import bpy
import json
import math
from mathutils import Euler, Matrix, Quaternion, Vector

STRAIGHT = 0.985  # a leg never opens past this share of its full length: a locked knee snaps


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

def held(basis, lim):
    """A bone's turn (in its own axes) brought inside its limits. Returns (turn, was it changed)."""
    if lim is None:
        return basis, False
    e = basis.to_euler("XYZ")
    want = [clamp(math.degrees(e[k]), lim[2 * k], lim[2 * k + 1]) for k in range(3)]
    if all(abs(want[k] - math.degrees(e[k])) < 0.02 for k in range(3)):
        return basis, False
    return Euler([math.radians(v) for v in want], "XYZ").to_matrix(), True

def frame_of(side, along):
    """A bone's axes when it points `along` with its hinge axis toward `side`."""
    y = along.normalized()
    x = (side - y * side.dot(y)).normalized()
    out = Matrix((x, y, x.cross(y)))
    out.transpose()
    return out

def spin(axis, degrees):
    return Quaternion(axis, math.radians(degrees)).to_matrix()


rig = bpy.data.objects.get(PARAMS["rig"]) if PARAMS["rig"] else None
if rig is None:
    found = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    if not found:
        raise ValueError("no skeleton in the scene: run rig.py first")
    rig = found[0]
motion = PARAMS["motion"]
if not isinstance(motion, dict):
    if "forge_motion: " + motion not in rig:
        raise ValueError("the rig has no motion named %r: run walk.py (or another motion source) first" % motion)
    motion = json.loads(rig["forge_motion: " + motion])
known = json.loads(rig.get("forge_rig", "{}"))
limits = known.get("limits", {})
floor = known.get("measure", {}).get("floor", 0.0)

order, rest, head, parent = [], {}, {}, {}
todo = [b for b in rig.data.bones if b.parent is None]
while todo:
    b = todo.pop(0)
    order.append(b.name)
    rest[b.name], head[b.name] = b.matrix_local.to_3x3(), b.head_local.copy()
    parent[b.name] = b.parent.name if b.parent else None
    todo += list(b.children)
for name in ("hips", "thigh_l", "shin_l", "foot_l", "toe_l", "thigh_r", "shin_r", "foot_r", "toe_r"):
    if name not in rest:
        raise ValueError("the rig has no %r bone: it was not made by rig.py" % name)
scale = head["thigh_l"].z - floor  # this character's hip height: the motion's unit
frames, fps = motion["frames"], motion["fps"]
count = frames + 1
legs = {}
for tag in ("l", "r"):
    legs[tag] = {"thigh": (head["shin_" + tag] - head["thigh_" + tag]).length, "shin": (head["foot_" + tag] - head["shin_" + tag]).length,
                 "sole": head["toe_" + tag] - head["foot_" + tag]}
leg_bones = {"thigh_l", "shin_l", "foot_l", "toe_l", "thigh_r", "shin_r", "foot_r", "toe_r"}
ground = Vector((head["hips"].x, head["hips"].y, 0.0))


def foot_target(tag, f):
    """Where the ball of a foot must be on a frame, and the foot's pitch and yaw."""
    x, y, z, pitch, yaw, planted = motion["feet"][tag][f]
    return ground + Vector((x * scale, y * scale, head["toe_" + tag].z + z * scale)), pitch, yaw, planted

def body(f, drop):
    """Everything but the legs on one frame: {bone: its turn in its own axes}, plus where each bone sits and faces."""
    basis, faces, at = {}, {}, {}
    for name in order:
        if name in leg_bones:
            continue
        up = parent[name]
        follow = rest[name] if up is None else faces[up] @ rest[up].inverted() @ rest[name]
        want = follow
        if name in motion["turns"]:
            want = Quaternion(motion["turns"][name][f]).to_matrix() @ rest[name]
        basis[name], changed = held(follow.inverted() @ want, limits.get(name))
        if changed:
            clamped[name] = clamped.get(name, 0) + 1
        faces[name] = follow @ basis[name]
        if up is None:
            at[name] = head[name] + (Vector(motion["hips"][f]) * scale if name == "hips" else Vector()) - Vector((0, 0, drop))
        else:
            at[name] = at[up] + faces[up] @ (rest[up].inverted() @ (head[name] - head[up]))
    return basis, faces, at

def hip_of(tag, faces, at):
    return at["hips"] + faces["hips"] @ (rest["hips"].inverted() @ (head["thigh_" + tag] - head["hips"]))

def ankle_of(tag, f):
    ball, pitch, yaw, planted = foot_target(tag, f)
    turned = spin(Vector((0, 0, 1)), yaw) @ spin(Vector((1, 0, 0)), pitch)
    return ball - turned @ legs[tag]["sole"], turned, yaw, ball

def pitch_of(turned):
    """How far a foot's toes point down, in degrees."""
    return math.degrees(math.asin(clamp(-(turned @ Vector((0, -1, 0))).z, -1.0, 1.0)))

def leg(tag, f, faces, at, basis):
    """One leg on one frame: hip to ankle by two bones and a hinge, then the foot and toes."""
    thigh, shin, foot, toe = "thigh_" + tag, "shin_" + tag, "foot_" + tag, "toe_" + tag
    l1, l2 = legs[tag]["thigh"], legs[tag]["shin"]
    hip = hip_of(tag, faces, at)
    ankle, turned, yaw, ball = ankle_of(tag, f)
    asked = pitch_of(turned)
    for attempt in range(10):
        ankle = ball - turned @ legs[tag]["sole"]
        gap = ankle - hip
        far = clamp(gap.length, abs(l1 - l2) + 1e-4, STRAIGHT * (l1 + l2))
        if gap.length > STRAIGHT * (l1 + l2) + 1e-5:
            short[tag] = max(short[tag], gap.length - STRAIGHT * (l1 + l2))
        along = gap.normalized()
        side = spin(Vector((0, 0, 1)), 0.6 * yaw) @ Vector((1, 0, 0))
        side = (side - along * side.dot(along)).normalized()
        open_by = math.acos(clamp((l1 * l1 + far * far - l2 * l2) / (2 * l1 * far), -1.0, 1.0))
        upper = Quaternion(side, -open_by) @ along  # the knee goes forward
        knee = hip + upper * l1
        follow = faces["hips"] @ rest["hips"].inverted() @ rest[thigh]
        basis[thigh], bent = held(follow.inverted() @ frame_of(side, upper), limits.get(thigh))
        faces[thigh] = follow @ basis[thigh]
        if bent:
            knee = hip + faces[thigh].col[1] * l1
        follow = faces[thigh] @ rest[thigh].inverted() @ rest[shin]
        lower = hip + along * far - knee if not bent else ankle - knee
        basis[shin], hinge = held(follow.inverted() @ frame_of(faces[thigh].col[0], lower), limits.get(shin))
        faces[shin] = follow @ basis[shin]
        follow = faces[shin] @ rest[shin].inverted() @ rest[foot]
        basis[foot], changed = held(follow.inverted() @ (turned @ rest[foot]), limits.get(foot))
        faces[foot] = follow @ basis[foot]
        if not changed:
            break
        # The ankle is at a limit. The foot goes where the ankle lets it (the heel lifts, the foot
        # rolls), and the leg is solved again so the ball of the foot stays where it was planted.
        turned = faces[foot] @ rest[foot].inverted()
    for name, was in ((thigh, bent), (shin, hinge)):
        if was:
            clamped[name] = clamped.get(name, 0) + 1
    off = (faces[foot] @ rest[foot].inverted() @ legs[tag]["sole"] + ankle - ball).length
    if off > 1e-4:  # it did not settle: the foot is clamped and the ball has moved
        clamped[foot] = clamped.get(foot, 0) + 1
    pitch = pitch_of(faces[foot] @ rest[foot].inverted())
    # Toes lie flat on the floor, and fall in line with the foot only as far as its height lets them without touching down.
    room = math.degrees(math.asin(clamp((ball.z - head[toe].z) / (1.2 * (rig.data.bones[toe].length + 1e-6)), 0.0, 1.0)))
    follow = faces[foot] @ rest[foot].inverted() @ rest[toe]
    flat = spin(Vector((0, 0, 1)), yaw) @ spin(Vector((1, 0, 0)), clamp(pitch, -room, room))
    basis[toe], changed = held(follow.inverted() @ (flat @ rest[toe]), limits.get(toe))
    if changed:
        clamped[toe] = clamped.get(toe, 0) + 1
    return abs(pitch - asked)


# ---- 1 and 2a: fit the body, and find how far the hips must come down for the legs to reach ----
clamped, short = {}, {"l": 0.0, "r": 0.0}
drop = 0.0
for f in range(frames):
    basis, faces, at = body(f, 0.0)
    for tag in ("l", "r"):
        hip = hip_of(tag, faces, at)
        ankle = ankle_of(tag, f)[0]
        most = STRAIGHT * (legs[tag]["thigh"] + legs[tag]["shin"])
        flat = Vector((ankle.x - hip.x, ankle.y - hip.y)).length
        if flat < most:
            drop = max(drop, (hip.z - ankle.z) - math.sqrt(most * most - flat * flat))
        else:
            drop = max(drop, hip.z - ankle.z)  # out of reach even from the floor: the motion's stride is too long for these legs

# ---- 2b, 3: every frame, solved and clamped ----
clamped, short = {}, {"l": 0.0, "r": 0.0}
poses, hips_at, heel_help = [], [], 0.0
for f in range(count):
    g = f % frames if motion.get("loop", True) else f
    basis, faces, at = body(g, drop)
    for tag in ("l", "r"):
        heel_help = max(heel_help, abs(leg(tag, g, faces, at, basis)))
    poses.append(basis)
    hips_at.append(rest["hips"].inverted() @ (at["hips"] - head["hips"]))

# ---- 4: bake ----
name = PARAMS["action"] or motion.get("name", "motion")
old = bpy.data.actions.get(name)
if old is not None:
    bpy.data.actions.remove(old)
if rig.animation_data is None:
    rig.animation_data_create()
action = bpy.data.actions.new(name)
rig.animation_data.action = action
last = {}
for f in range(count):
    for bone in rig.pose.bones:
        if bone.name not in poses[f]:
            continue
        q = poses[f][bone.name].to_quaternion()
        if bone.name in last and q.dot(last[bone.name]) < 0:
            q.negate()
        last[bone.name] = q
        bone.rotation_mode = "QUATERNION"
        bone.rotation_quaternion = q
        bone.keyframe_insert("rotation_quaternion", frame=f, group=bone.name)
        if bone.name == "hips":
            bone.location = hips_at[f]
            bone.keyframe_insert("location", frame=f, group=bone.name)
curves = []
if getattr(action, "layers", None):
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                curves += list(bag.fcurves)
else:
    curves = list(getattr(action, "fcurves", []))
for curve in curves:
    for key in curve.keyframe_points:
        key.interpolation = "LINEAR"
scene = bpy.context.scene
scene.render.fps = fps
scene.frame_start, scene.frame_end = 0, frames
action["forge_motion"] = json.dumps({"name": motion.get("name"), "fps": fps, "frames": frames, "loop": bool(motion.get("loop", True)),
                                     "speed_m_s": round(motion.get("travel", 0.0) * scale, 4)})

result = {
    "rig": rig.name, "action": action.name, "frames": frames, "fps": fps, "seconds": round(frames / fps, 3),
    "speed_m_s": round(motion.get("travel", 0.0) * scale, 3), "bones_keyed": len(poses[0]),
    "hips_lowered_cm": round(100 * drop, 1), "heel_lifted_for_ankle_deg": round(heel_help, 1),
    "clamped": clamped, "out_of_reach_cm": round(100 * max(short.values()), 2),
    "then": json.loads(rig.get("forge_then", "[]")),  # passes this rig asks for after any motion is baked: run each next (cloth.py asks for swing.py)
}

# ---- play it back and measure ----
if PARAMS["check"]:
    meshes = [o for o in scene.objects if o.type == "MESH" and o.find_armature() == rig]
    step = Vector((0, motion.get("travel", 0.0) * scale / fps, 0))
    slid, worst_slide, lowest, outside, was = {"l": 0.0, "r": 0.0}, 0.0, 1e9, {}, {}
    first_pose, seam, lowest_frame = {}, 0.0, 0
    for f in range(count):
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
        shown = rig.evaluated_get(deps)
        for tag in ("l", "r"):
            ball = shown.matrix_world @ shown.pose.bones["toe_" + tag].head
            planted = motion["feet"][tag][f % frames][5] and motion["feet"][tag][(f - 1) % frames][5]
            if f and planted:
                slid[tag] += (ball - was[tag] - step).length
            elif f:
                worst_slide = max(worst_slide, slid[tag])
                slid[tag] = 0.0
            was[tag] = ball
        for obj in meshes:
            me = obj.evaluated_get(deps).to_mesh()
            low = min((obj.matrix_world @ v.co).z for v in me.vertices)
            obj.evaluated_get(deps).to_mesh_clear()
            if low < lowest:
                lowest, lowest_frame = low, f
        for bone in rig.pose.bones:
            lim = limits.get(bone.name)
            e = bone.matrix_basis.to_3x3().to_euler("XYZ")
            if lim and any(not lim[2 * k] - 0.1 <= math.degrees(e[k]) <= lim[2 * k + 1] + 0.1 for k in range(3)):
                outside[bone.name] = outside.get(bone.name, 0) + 1
            now = list(bone.rotation_quaternion) + list(bone.location)
            if f == 0:
                first_pose[bone.name] = now
            elif f == frames:
                seam = max(seam, max(abs(a - b) for a, b in zip(now, first_pose[bone.name])))
    scene.frame_set(0)
    result["check"] = {
        "foot_slide_cm_per_step": round(100 * max(worst_slide, slid["l"], slid["r"]), 3),
        "through_floor_cm": round(100 * max(0.0, floor - lowest), 2), "lowest_frame": lowest_frame,
        "limit_violations": sum(outside.values()), "outside": outside,
        "loop_seam": round(seam, 6), "meshes": len(meshes),
    }
print("RESULT " + json.dumps(result))
