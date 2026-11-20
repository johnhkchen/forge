# Make loose cloth hang and swing with a baked motion: the last pass after
# animate.py, for a rig that cloth.py gave cloth bones.
#
# animate.py bakes the body's motion and leaves the cloth bones still. This
# plays that action through once more and lets each chain of cloth bones
# trail behind the body like a row of weights on strings (the "spring bone"
# way games and VRM avatars move skirts and hair; no cloth solver, nothing a
# .glb can't carry). On every frame, for each bone from the top of a chain
# down:
#   - its end keeps the speed it had ("drag" takes some away),
#   - is pulled back toward where it hangs at rest ("stiffness"), down by
#     "gravity", and back by the air the character walks through ("air"),
#   - stays one bone-length from the joint above it,
#   - is pushed out of the thighs, shins and chest (round-ended cylinders
#     around those bones, sized from the build), so a kilt rides up over a
#     knee and never passes through it,
#   - and the turn that puts it there is clamped to the bone's "limit_deg".
# The result is keyed on the cloth bones, one key a frame, into the same
# action. A motion that loops is run through three times and the last round
# kept (or, for a chain that never settles, the average of a few more),
# then its end is eased onto its start, so the loop has no seam.
#
# "check" in the result: turns outside a limit, how far any cloth joint is
# inside a leg, the seam, how far the hems travel.
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down.
# Prints RESULT {json}. A second or two. Safe-mode compatible.

PARAMS = {
    "rig": None,        # the armature; None = the first one in the scene
    "stiffness": 1.2,   # how hard a bone is pulled back to where it hangs at rest (0 = a rag, 3 = starched)
    "drag": 0.35,       # the share of its speed a bone's end loses each frame (0 = swings for ever, 1 = never swings)
    "gravity": 0.6,     # how hard it is pulled down
    "air": 0.25,        # how much the air of walking pushes it back (uses the motion's speed)
    "rounds": 3,        # a looping motion is played this many times; the last round is kept
    "check": True,      # play the result back and measure it
}

import bpy
import json
import math
from mathutils import Euler, Quaternion, Vector

RODS = ("thigh_l", "thigh_r", "shin_l", "shin_r", "chest")
MORE_ROUNDS = 6  # a loop whose cloth has not settled is played this many more times, and the rounds averaged


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

def held(basis, lim):
    """A turn (in the bone's own axes) brought inside its limits."""
    e = basis.to_euler("XYZ")
    want = [clamp(math.degrees(e[k]), lim[2 * k], lim[2 * k + 1]) for k in range(3)]
    if all(abs(want[k] - math.degrees(e[k])) < 0.02 for k in range(3)):
        return basis
    return Euler([math.radians(v) for v in want], "XYZ").to_matrix()

def off_segment(a, b, p):
    """From the nearest point of the segment a-b to `p`: (which way, how far)."""
    ab = b - a
    t = clamp((p - a).dot(ab) / max(ab.length_squared, 1e-12), 0.0, 1.0)
    away = p - (a + ab * t)
    return away, away.length

def between(a, b, c, d):
    """Two segments, a rod a-b and a bone c-d, at their nearest: (from the rod to the bone, how far, how far along the bone 0-1)."""
    u, v, w = b - a, d - c, a - c
    uu, uv, vv, uw, vw = u.dot(u), u.dot(v), v.dot(v), u.dot(w), v.dot(w)
    den = uu * vv - uv * uv
    s = clamp((uv * vw - vv * uw) / den, 0.0, 1.0) if den > 1e-12 else 0.0
    t = clamp((uv * s + vw) / vv, 0.0, 1.0) if vv > 1e-12 else 0.0
    s = clamp((uv * t - uw) / uu, 0.0, 1.0) if uu > 1e-12 else 0.0
    away = (c + v * t) - (a + u * s)
    return away, away.length, t

def curves_of(action):
    curves = []
    if getattr(action, "layers", None):
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    curves += list(bag.fcurves)
    else:
        curves = list(getattr(action, "fcurves", []))
    return curves


scene = bpy.context.scene
rig = bpy.data.objects.get(PARAMS["rig"]) if PARAMS["rig"] else None
if rig is None:
    rigs = [o for o in scene.objects if o.type == "ARMATURE"]
    if not rigs:
        raise ValueError("no skeleton in the scene: run rig.py first")
    rig = rigs[0]
chains = json.loads(rig.get("forge_cloth", "{}")).get("chains", [])
chains = [c for c in chains if all(name in rig.data.bones for name in c["bones"] + [c["parent"]])]
action = rig.animation_data.action if rig.animation_data else None
if action is None:
    raise ValueError("the rig has no baked motion: run animate.py first")
about = json.loads(action.get("forge_motion", "{}"))
frames = int(about.get("frames") or round(action.frame_range[1]))
loops = bool(about.get("loop", False))
fps = about.get("fps") or scene.render.fps
known = json.loads(rig.get("forge_rig", "{}"))
measure = known.get("measure", {})
limits = known.get("limits", {})
tall = measure.get("height", 1.8)
result = {"rig": rig.name, "action": action.name, "frames": frames, "loops": loops, "chains": len(chains), "bones": sum(len(c["bones"]) for c in chains)}

if chains:
    rest = {b.name: b.matrix_local.copy() for b in rig.data.bones}
    span = {b.name: b.length for b in rig.data.bones}
    for c in chains:
        c["local"] = [(rest[c["bones"][i - 1] if i else c["parent"]]).inverted() @ rest[name] for i, name in enumerate(c["bones"])]
    down = (rig.matrix_world.to_3x3().inverted() @ Vector((0, 0, -1))).normalized()
    wind = rig.matrix_world.to_3x3().inverted() @ Vector((0, 1, 0)) * (about.get("speed_m_s") or 0.0)  # it faces -y: the air comes at it and blows back
    # A rod around each thigh, shin and the chest, as thick as the body is there: nine in ten of the points that bone carries lie inside it.
    rods = []
    flesh = [o for o in scene.objects if o.type == "MESH" and o.find_armature() == rig and o.get("forge") != "gear"]
    for name in RODS:
        if name not in rest:
            continue
        a, b = rest[name].translation, rest[name] @ Vector((0, span[name], 0))
        off = []
        for obj in flesh:
            group = obj.vertex_groups.get(name)
            if group is None:
                continue
            place = rig.matrix_world.inverted() @ obj.matrix_world
            for v in obj.data.vertices:
                if any(g.group == group.index and g.weight > 0.6 for g in v.groups):
                    off.append(off_segment(a, b, place @ v.co)[1])
        off.sort()
        if off:
            rods.append((name, off[int(0.9 * (len(off) - 1))] + 0.005 * tall))
    # A rod is never so thick that the cloth is inside it while standing still: cloth that rests against a leg stays resting.
    for c in chains:
        c["room"] = []
        for name in c["bones"]:
            end = rest[name] @ Vector((0, span[name], 0))
            c["room"].append({rod: max(0.0, min(radius, between(rest[rod].translation, rest[rod] @ Vector((0, span[rod], 0)), rest[name].translation, end)[1]))
                              for rod, radius in rods})

    # ---- the body's motion, frame by frame: where each chain's parent is, and where the legs are ----
    taken = []
    for f in range(frames + 1):
        scene.frame_set(f)
        pose = rig.pose.bones
        taken.append({"parent": {c["parent"]: pose[c["parent"]].matrix.copy() for c in chains},
                      "rods": {name: (pose[name].head.copy(), pose[name].tail.copy()) for name, radius in rods}})

    def step(c, state, shot, dt):
        """One frame for one chain: returns each bone's turn (in its own axes) and leaves the new ends in `state`."""
        above, turns = shot["parent"][c["parent"]], []
        for i, name in enumerate(c["bones"]):
            follow = above @ c["local"][i]  # where the bone would be if it were stiff
            head = follow.translation
            axes = follow.to_3x3()
            hangs = axes.col[1].normalized()
            if state["now"][i] is None:
                state["now"][i] = state["was"][i] = head + hangs * span[name]
            now, was = state["now"][i], state["was"][i]
            speed = (now - was) / dt
            end = now + (now - was) * (1.0 - PARAMS["drag"])
            end += hangs * (PARAMS["stiffness"] * span[name] * dt * 8.0)
            end += down * (PARAMS["gravity"] * span[name] * dt * 8.0)
            end += (wind - speed) * (PARAMS["air"] * dt * 0.3)
            end = head + (end - head).normalized() * span[name]
            for _ in range(3):
                for rod in shot["rods"]:  # the whole bone, not only its end, stays out of the rod: the sheet of cloth along it does too
                    radius = c["room"][i][rod]
                    away, far, along = between(shot["rods"][rod][0], shot["rods"][rod][1], head, end)
                    if 1e-9 < far < radius and along > 0.05:
                        end = end + away * ((radius - far) / (far * along))
                end = head + (end - head).normalized() * span[name]
            want = axes.inverted() @ (end - head).normalized()
            basis = held(Vector((0, 1, 0)).rotation_difference(want).to_matrix(), limits.get(name) or [-180, 180, -180, 180, -180, 180])
            end = head + axes @ basis @ Vector((0, span[name], 0))
            state["was"][i], state["now"][i] = now, end
            turns.append(basis)
            above = follow @ basis.to_4x4()
        return turns

    dt = 1.0 / fps
    played = []
    for c in chains:
        state = {"now": [None] * len(c["bones"]), "was": [None] * len(c["bones"])}
        if loops:
            for _ in range(max(1, int(PARAMS["rounds"])) - 1):
                for f in range(frames):
                    step(c, state, taken[f], dt)
            # A chain that a leg knocks about may never settle into the loop: every round ends some degrees from
            # where it started, a different way each time (the troll's kilt, thrown 80 degrees by thighs 40 cm
            # thick). Then it is played round a few more times, each round starting where the last one ended, and
            # the rounds are averaged frame by frame: what the ends are short of the starts shrinks by as many
            # times as there are rounds.
            rounds = [[step(c, state, taken[f], dt) for f in range(frames + 1)]]
            short = max(math.degrees(a.to_quaternion().rotation_difference(b.to_quaternion()).angle) for a, b in zip(rounds[0][0], rounds[0][frames]))
            kept = (short, rounds[0])
            if short >= 1.0:
                for again in range(MORE_ROUNDS):
                    rounds.append([rounds[-1][frames]] + [step(c, state, taken[f], dt) for f in range(1, frames + 1)])
                middle = []
                for f in range(frames + 1):
                    row = []
                    for i in range(len(c["bones"])):
                        first_q = rounds[0][f][i].to_quaternion()
                        total = [0.0, 0.0, 0.0, 0.0]
                        for one in rounds:
                            q = one[f][i].to_quaternion()
                            if q.dot(first_q) < 0:
                                q.negate()
                            total = [t + v for t, v in zip(total, q)]
                        row.append(held(Quaternion(total).normalized().to_matrix(), limits.get(c["bones"][i]) or [-180, 180, -180, 180, -180, 180]))
                    middle.append(row)
                kept = (0.0, middle)
            played.append(kept[1])
            continue
        for _ in range(30):  # let it settle into the first pose before the motion starts
            step(c, state, taken[0], dt)
        played.append([step(c, state, taken[f], dt) for f in range(frames + 1)])

    # ---- key it; a loop's last frame is its first, and the little left over is eased out across the round ----
    worst_seam = 0.0
    for c, turns in zip(chains, played):
        for i, name in enumerate(c["bones"]):
            bone = rig.pose.bones[name]
            bone.rotation_mode = "QUATERNION"
            quats = [t[i].to_quaternion() for t in turns]
            for f in range(1, len(quats)):
                if quats[f].dot(quats[f - 1]) < 0:
                    quats[f].negate()
            if loops:
                left = [a - b for a, b in zip(quats[0], quats[frames])]  # what the end is short of the start
                worst_seam = max(worst_seam, math.degrees(quats[0].rotation_difference(quats[frames]).angle))
                for f in range(1, frames + 1):
                    eased = Quaternion([q + d * f / frames for q, d in zip(quats[f], left)]).normalized()
                    quats[f] = held(eased.to_matrix(), limits.get(name) or [-180, 180, -180, 180, -180, 180]).to_quaternion()
                    if quats[f].dot(quats[f - 1]) < 0:
                        quats[f].negate()
                quats[frames] = quats[0].copy()
            for f in range(frames + 1):
                bone.rotation_quaternion = quats[f]
                bone.keyframe_insert("rotation_quaternion", frame=f, group=name)
    for curve in curves_of(action):
        if 'pose.bones["cloth_' in curve.data_path:
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"
    result["eased_at_the_seam_deg"] = round(worst_seam, 3)

    # ---- play it back and measure ----
    if PARAMS["check"]:
        outside, inside_cm, seam, swing, first_pose, lowest, highest = {}, 0.0, 0.0, 0.0, {}, {}, {}
        for f in range(frames + 1):
            scene.frame_set(f)
            pose = rig.pose.bones
            for c in chains:
                for i, name in enumerate(c["bones"]):
                    bone = pose[name]
                    e = bone.matrix_basis.to_3x3().to_euler("XYZ")
                    lim = limits.get(name)
                    if lim and any(not lim[2 * k] - 0.1 <= math.degrees(e[k]) <= lim[2 * k + 1] + 0.1 for k in range(3)):
                        outside[name] = outside.get(name, 0) + 1
                    swing = max(swing, math.degrees(bone.matrix_basis.to_quaternion().angle))
                    for rod, radius in rods:
                        away, far, along = between(pose[rod].head, pose[rod].tail, bone.head, bone.tail)
                        if along > 0.05:
                            inside_cm = max(inside_cm, 100 * (c["room"][i][rod] - far))
                    now = list(bone.rotation_quaternion)
                    if f == 0:
                        first_pose[name] = now
                    elif f == frames and loops:
                        seam = max(seam, max(abs(a - b) for a, b in zip(now, first_pose[name])))
                tip = pose[c["bones"][-1]]
                at = (pose[c["parent"]].matrix.inverted() @ tip.tail)
                key = c["bones"][-1]
                lowest[key] = at.copy() if key not in lowest else Vector([min(lowest[key][k], at[k]) for k in range(3)])
                highest[key] = at.copy() if key not in highest else Vector([max(highest[key][k], at[k]) for k in range(3)])
        scene.frame_set(0)
        result["check"] = {
            "limit_violations": sum(outside.values()), "outside": outside,
            "deepest_in_a_leg_cm": round(max(inside_cm, 0.0), 2),
            "loop_seam": round(seam, 6), "most_swing_deg": round(swing, 1),
            "hem_travels_cm": round(100 * max([(highest[k] - lowest[k]).length for k in lowest] or [0.0]), 1),
        }
print("RESULT " + json.dumps(result))
