# Play a motion on a rigged character: fit it to this character's bones, keep
# planted feet planted, keep feet out of the floor and legs out of the set,
# keep every joint inside its limits, and bake it to keyframes as an action the
# .glb can carry.
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
# and two things only a shot has (both optional):
#   "hands":  {"l": per frame None or [x, y, z, how much], "r": ...}: a spot
#             the wrist must be on (a wall top, the floor), measured like the
#             feet; "how much" runs 0 to 1, so a hand can ease on and off it
#   "set":    [{"name", "center": [x, y, z], "size": [across, through, tall],
#             "turn": degrees}]: blocks standing in the way (a wall), measured
#             like the feet; "turn" is about z, 0 with "across" along x
#
# What happens to it here, in order:
#   1. Fit. Lengths are scaled by this character's hip height; each bone is
#      turned from its own rest pose by the motion's amount.
#   2. Hands. A hand with a spot is put on it: the arm is solved from shoulder
#      to wrist (two bones and a one-way elbow), and the hand is laid flat,
#      palm down. A character's arms are not the motion's: where they are a
#      little short the hips move over (a twentieth of the hip height at
#      most); past that, or past what the shoulder can do, the hand goes as
#      far as it can and lets go gently. A spot on the floor that is out of
#      reach is moved in toward the shoulder, so the hand still lands on the
#      floor. Any hand that would go into the floor is lifted out.
#   3. Plant the feet. Each leg is solved from the hip joint to where the foot
#      must be (two bones and a hinge: exact, no iteration), so the ball of a
#      planted foot stays where it was put and moves back at exactly "travel".
#      If an ankle would bend past its limit the heel lifts. Only if a planted
#      foot is out of the leg's reach do the hips come down (for a whole loop;
#      in a shot, only around the frames that need it). A foot in the air that
#      is out of reach just comes up short.
#   4. Contact. The floor and the set are tested against the real mesh: the
#      outermost points of the shoe, foot, shin and thigh, not the bones. (A
#      heeled shoe's toe reaches twice as far forward as the toe bone does.)
#        - toes fall in line with the foot only as far as the floor lets them;
#        - a planted foot whose toes still dig in (heel up, toes bent as far
#          as they go) lowers its heel, if the leg still reaches;
#        - anything else below the floor lifts the foot straight up: a heel
#          coming down first, a foot in the air. Never sideways, so a planted
#          foot does not slide;
#        - a leg inside a block is moved out the short way: over the top, or
#          back out the face the hips are on when that is much nearer;
#        - what moving the foot cannot cure, the hips cure by rising: a knee
#          in the floor in a deep crouch on thicker legs, a leg folded as far
#          as it goes and still under the top of a wall it is passing over.
#      Each correction comes on and goes off over a few frames, and the leg is
#      solved again with it, so limits still hold and a loop still closes.
#   5. Limits. Every bone's turn is clamped to its "limit_deg" (the same
#      numbers as its Limit Rotation constraint). "clamped" says which bones
#      needed it and how often; a clamp on a leg can let a foot slide, and the
#      check below will show it.
#   6. Bake: one key per frame on every bone, in an action named for the motion.
#
# "contact" in the result says what steps 2 and 4 did. "then" names what to run
# next on the baked action: a rig with cloth bones (cloth.py) asks for swing.py,
# which makes loose cloth hang and swing with whatever motion was just baked.
#
# "check": True then plays the baked action back in Blender and measures it on
# the mesh: how far a planted foot slid over the ground (cm per step, and the
# furthest it got from where it landed), how far anything went through the
# floor and which bone's part it was, how deep anything is inside the set and
# which part, how far a hand is from its spot while held there, turns outside
# a limit, and whether the last frame equals the first. `"contact": False`
# plays the motion as it was written, to measure against.
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down.
# Prints RESULT {json}. A second or two; a ten-second shot takes half a minute. Safe-mode compatible.

PARAMS = {
    "rig": None,       # the armature rig.py made; None = the first one in the scene
    "motion": "walk",  # the name of a motion a source left on the rig, or the motion itself as a dict
    "action": None,    # what to call the baked action; None = the motion's name
    "contact": True,   # step 4: keep the real mesh out of the floor and the set. False plays the motion as it was written
    "check": True,     # play it back and measure foot slide, floor, set, hands, limits and the loop
}

import bpy
import json
import math
from mathutils import Euler, Matrix, Quaternion, Vector

STRAIGHT = 0.985  # a leg never opens past this share of its full length: a locked knee snaps
TOUCH = 0.0002    # metres: nearer the floor or a block than this counts as touching, not through
CLEAR = 0.004     # metres: how far out of a block a leg is moved
EASE_FRAMES = 3   # a correction comes on and goes off over this many frames each side
SET_FRAMES = 8    # and over this many where there is a set to get over
DROP_FRAMES = 12  # the hips come down (in a shot) or rise, and go back, over this many frames each side
RISE_ROUNDS = 5    # how many times the hips may be raised and everything solved again
MOST_RISE = 0.3    # the hips are never raised by more than this share of the hip height
HAND_LIFT = 0.03   # a hand on its spot is lifted at most this share of the hip height to get its fingers out of what it rests on
OVER_FIRST = 2.5   # a point in a block goes out over the top unless a face is this many times nearer
HIPS_FOR_A_HAND = 0.05  # the hips move at most this share of the hip height to bring a pinned hand to its spot
OUTLINE = 120     # at most this many points stand for one bone's part of the mesh
UP = Vector((0.0, 0.0, 1.0))


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
    """A bone's axes when it points `along` with its hinge axis (x) toward `side`."""
    y = along.normalized()
    x = (side - y * side.dot(y)).normalized()
    out = Matrix((x, y, x.cross(y)))
    out.transpose()
    return out

def frame_about(along, hinge):
    """A bone's axes when it points `along` with its hinge axis (z) toward `hinge`."""
    y = along.normalized()
    z = (hinge - y * hinge.dot(y)).normalized()
    out = Matrix((y.cross(z), y, z))
    out.transpose()
    return out

def spin(axis, degrees):
    return Quaternion(axis, math.radians(degrees)).to_matrix()

def near_turn(degrees):
    """An angle brought to between -180 and 180."""
    return (degrees + 180.0) % 360.0 - 180.0

def spread(values, reach, around):
    """Each value, or more where a frame within `reach` of it needs more: a correction then comes
    on and goes off over a few frames and is never less than was needed."""
    n = len(values)
    out = []
    for i in range(n):
        best = values[i]
        for k in range(1, reach + 1):
            w = 1.0 - k / (reach + 1.0)
            w = w * w * (3.0 - 2.0 * w)
            for j in (i - k, i + k):
                if around:
                    j %= n
                elif not 0 <= j < n:
                    continue
                best = max(best, w * values[j])
        out.append(best)
    return out

def outline(points, most):
    """The outermost of some points: the furthest one along each of `most` directions. What can touch a flat floor or wall first."""
    seen, kept = set(), []
    for p in points:
        key = (round(p.x / 0.003), round(p.y / 0.003), round(p.z / 0.003))
        if key not in seen:
            seen.add(key)
            kept.append(p)
    if len(kept) <= most:
        return kept
    chosen = set()
    for i in range(most):
        z = 1.0 - 2.0 * (i + 0.5) / most
        r = math.sqrt(max(0.0, 1.0 - z * z))
        d = Vector((r * math.cos(2.399963 * i), r * math.sin(2.399963 * i), z))
        scores = [p.dot(d) for p in kept]
        chosen.add(scores.index(max(scores)))
    return [kept[i] for i in sorted(chosen)]


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
unrest = {name: rest[name].inverted() for name in rest}
scale = head["thigh_l"].z - floor  # this character's hip height: the motion's unit
frames, fps = motion["frames"], motion["fps"]
count = frames + 1
looped = bool(motion.get("loop", True))
span = frames if looped else count  # how many different frames there are
legs = {}
for tag in ("l", "r"):
    legs[tag] = {"thigh": (head["shin_" + tag] - head["thigh_" + tag]).length, "shin": (head["foot_" + tag] - head["shin_" + tag]).length,
                 "sole": head["toe_" + tag] - head["foot_" + tag]}
leg_bones = {"thigh_l", "shin_l", "foot_l", "toe_l", "thigh_r", "shin_r", "foot_r", "toe_r"}
ground = Vector((head["hips"].x, head["hips"].y, 0.0))
careful = bool(PARAMS.get("contact", True))
spots = motion.get("hands") or {}
hands = spots if careful else {}  # with the contact step off, hands go where the motion had them; the check still measures them

# The set: each block as where it is, which way it faces and half its size, in metres.
blocks = []
for card in motion.get("set") or []:
    a = math.radians(card.get("turn", 0.0))
    mid = ground + Vector((card["center"][0] * scale, card["center"][1] * scale, floor + card["center"][2] * scale))
    top = mid.z + card["size"][2] * scale / 2.0
    if top < floor + 0.01:
        continue  # a slab to stand on: its top is the floor
    blocks.append({"name": card.get("name", "block"), "mid": Vector((mid.x, mid.y, (top + floor) / 2.0)), "across": Vector((math.cos(a), math.sin(a), 0.0)),
                   "through": Vector((-math.sin(a), math.cos(a), 0.0)), "half": (card["size"][0] * scale / 2.0, card["size"][1] * scale / 2.0, (top - floor) / 2.0)})

# The mesh, as the bones carry it: for each leg and hand bone, the outermost points of what mostly follows it.
skinned = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.find_armature() == rig]
shape = {name: [] for name in rest if name[:-2] in ("thigh", "shin", "foot", "toe", "hand")}
to_rig = rig.matrix_world.inverted()
if careful:
    for obj in skinned:
        names = [g.name for g in obj.vertex_groups]
        here = to_rig @ obj.matrix_world
        for v in obj.data.vertices:
            most, which = 0.5, None
            for g in v.groups:
                if g.weight >= most:
                    most, which = g.weight, names[g.group]
            if which in shape:
                shape[which].append(here @ v.co - head[which])
    for name in shape:
        shape[name] = outline(shape[name], OUTLINE)
    for tag in ("l", "r"):  # a foot with no mesh of its own: the bones stand for it, with the sole on the floor
        foot, toe = "foot_" + tag, "toe_" + tag
        if not shape[foot]:
            shape[foot] = [Vector((0.0, 0.0, floor - head[foot].z)), Vector((0.0, head[toe].y - head[foot].y, floor - head[foot].z))]
        if not shape[toe]:
            shape[toe] = [Vector((0.0, 0.0, floor - head[toe].z)), Vector((0.0, rig.data.bones[toe].tail_local.y - head[toe].y, floor - head[toe].z))]


def lowest(points, where, turn):
    """The height of the lowest of a bone's points, with the bone's head at `where` and turned by `turn` from rest."""
    if not points:
        return where.z
    row = turn[2]
    return where.z + min(row.dot(p) for p in points)

def inside(point, side_of):
    """How to get a point out of the blocks the short way: over the top, or out the face on the side `side_of` is.
    Returns (the move, how deep it is, how far under the top it is), or None if it is in no block."""
    for block in blocks:
        d = point - block["mid"]
        u, v, w = d.dot(block["across"]), d.dot(block["through"]), d.z
        hu, hv, hw = block["half"]
        if abs(u) >= hu or abs(v) >= hv or w >= hw:
            continue
        over = hw - w
        home = (side_of - block["mid"]).dot(block["through"])
        face = 1.0 if (home if abs(home) > hv else v) > 0 else -1.0
        back = hv - face * v
        end = hu - abs(u)
        if end < min(over, back):
            return block["across"] * ((end + CLEAR) * (1.0 if u > 0 else -1.0)), end, over
        if over <= OVER_FIRST * back:  # a leg low against a wall steps back from it; anything near the top goes over
            return UP * (over + CLEAR), over, over
        return block["through"] * (face * (back + CLEAR)), back, over
    return None

def foot_target(tag, f):
    """Where the ball of a foot must be on a frame, and the foot's pitch and yaw."""
    x, y, z, pitch, yaw, planted = motion["feet"][tag][f]
    return ground + Vector((x * scale, y * scale, head["toe_" + tag].z + z * scale)), pitch, yaw, planted

def body(f, off, tally):
    """Everything but the legs on one frame: {bone: its turn in its own axes}, plus where each bone sits and faces. `off` moves the hips."""
    basis, faces, at = {}, {}, {}
    for name in order:
        if name in leg_bones:
            continue
        up = parent[name]
        follow = rest[name] if up is None else faces[up] @ unrest[up] @ rest[name]
        want = follow
        if name in motion["turns"]:
            want = Quaternion(motion["turns"][name][f]).to_matrix() @ rest[name]
        basis[name], changed = held(follow.inverted() @ want, limits.get(name))
        if changed:
            tally[name] = tally.get(name, 0) + 1
        faces[name] = follow @ basis[name]
        if up is None:
            at[name] = head[name] + (Vector(motion["hips"][f]) * scale + off if name == "hips" else Vector())
        else:
            at[name] = at[up] + faces[up] @ (unrest[up] @ (head[name] - head[up]))
    return basis, faces, at

def arm_to(tag, goal, basis, faces, at, level, way):
    """One arm solved from the shoulder to a spot for the wrist: two bones and the elbow's one-way hinge.
    `level` (0 to 1) is how far the hand is laid flat, palm down, fingers pointing `way`, as a hand resting on something is."""
    upper, fore, hand = "upper_arm_" + tag, "forearm_" + tag, "hand_" + tag
    palm = faces[hand].copy()
    l1, l2 = (head[fore] - head[upper]).length, (head[hand] - head[fore]).length
    shoulder = at[upper]
    gap = goal - shoulder
    far = clamp(gap.length, abs(l1 - l2) + 1e-4, 0.999 * (l1 + l2))
    along = gap.normalized()
    out = at[fore] - shoulder
    out = out - along * out.dot(along)
    if out.length < 0.02 * l1:  # a straight arm has no elbow side: it bends down and back
        out = Vector((0.0, 0.5, -1.0))
        out = out - along * out.dot(along)
    out.normalize()
    open_by = math.acos(clamp((l1 * l1 + far * far - l2 * l2) / (2 * l1 * far), -1.0, 1.0))
    first = along * math.cos(open_by) + out * math.sin(open_by)
    second = shoulder + along * far - (shoulder + first * l1)
    hinge = first.cross(second) * (-1.0 if tag == "l" else 1.0)  # an elbow folds the hand forward: the left one about -z, the right about +z
    if hinge.length < 1e-6:
        hinge = faces[upper].col[2].copy()
    up = parent[upper]
    follow = faces[up] @ unrest[up] @ rest[upper]
    basis[upper] = held(follow.inverted() @ frame_about(first, hinge), limits.get(upper))[0]
    faces[upper] = follow @ basis[upper]
    at[fore] = at[upper] + faces[upper] @ (unrest[upper] @ (head[fore] - head[upper]))
    follow = faces[upper] @ unrest[upper] @ rest[fore]
    second = goal - at[fore]
    if second.length > 1e-6:
        basis[fore] = held(follow.inverted() @ frame_about(second, faces[upper].col[2]), limits.get(fore))[0]
    faces[fore] = follow @ basis[fore]
    at[hand] = at[fore] + faces[fore] @ (unrest[fore] @ (head[hand] - head[fore]))
    follow = faces[fore] @ unrest[fore] @ rest[hand]
    if level > 0 and way is not None:
        palm = palm.to_quaternion().slerp(frame_about(way, UP).to_quaternion(), level).to_matrix()
    # A wrist bends up and down and hardly twists: the forearm turns about its own length to bring the hand round.
    # Of the turns it can make, the one that leaves the hand nearest to how it should lie is kept.
    hinged, turns = basis[fore].copy(), limits.get(fore)
    best = None
    for step in range(-4, 5) if turns is not None and level > 0 else [0]:
        twist = 0.0 if turns is None else (turns[3] if step > 0 else -turns[2]) * step / 4.0
        twisted = hinged @ spin(Vector((0, 1, 0)), twist)
        follow = faces[upper] @ unrest[upper] @ rest[fore] @ twisted @ unrest[fore] @ rest[hand]
        turn = held(follow.inverted() @ palm, limits.get(hand))[0]
        off = (follow @ turn).to_quaternion().rotation_difference(palm.to_quaternion()).angle + 0.0005 * abs(twist)
        if best is None or off < best[0]:
            best = (off, twisted, follow, turn)
    basis[fore] = best[1]
    faces[fore] = faces[upper] @ unrest[upper] @ rest[fore] @ basis[fore]
    basis[hand] = best[3]  # as the motion had it or flat, as far as the wrist allows
    faces[hand] = best[2] @ basis[hand]

def reach(tag, f, basis, faces, at, final):
    """A hand on one frame: onto its spot if the motion gives it one, and out of the floor and the set.
    Returns how far the wrist is still from its spot (None without one). On the `final` solve a spot the
    arm cannot reach is moved toward the shoulder at its own height: a hand meant for the floor still lands on the floor."""
    upper, hand = "upper_arm_" + tag, "hand_" + tag
    if hand not in at or upper not in at or "forearm_" + tag not in at:
        return None
    pin = (hands.get(tag) or [None] * span)[f]
    goal = spot = None
    level, risen = 0.0, 0.0
    if pin and pin[3] > 0:
        level = clamp(pin[3], 0.0, 1.0)
        spot = ground + Vector((pin[0] * scale, pin[1] * scale, floor + pin[2] * scale))
        if final:
            most = 0.999 * ((head["forearm_" + tag] - head[upper]).length + (head[hand] - head["forearm_" + tag]).length)
            gap = spot - at[upper]
            if gap.length > most and abs(gap.z) < most:
                along = Vector((gap.x, gap.y, 0.0)).normalized()
                spot = at[upper] + along * math.sqrt(most * most - gap.z * gap.z) + UP * gap.z
        goal = at[hand].lerp(spot, level)
    arm = (upper, "forearm_" + tag, hand)
    was = [(basis[name].copy(), faces[name].copy(), at[name].copy()) for name in arm]  # the arm as the motion had it
    for attempt in range(4):
        if goal is not None:
            # As far toward the spot as the shoulder's and elbow's limits let the wrist follow: an arm asked for more
            # than it can do would fold up somewhere else entirely. Short of the spot, the hand lets go gently.
            lo, hi, share = 0.0, 1.0, 1.0
            for step in range(7):
                for name, kept in zip(arm, was):
                    basis[name], faces[name], at[name] = kept[0].copy(), kept[1].copy(), kept[2].copy()
                aim = was[2][2].lerp(goal, share)
                arm_to(tag, aim, basis, faces, at, level, ways[tag][f])
                if (at[hand] - aim).length < 0.01:
                    if share == 1.0 or step == 6:
                        break
                    lo = share
                else:
                    hi = share
                share = lo if step == 5 else (lo + hi) / 2.0
        if not careful:
            break
        turn = faces[hand] @ unrest[hand]
        deep = floor - lowest(shape[hand], at[hand], turn)
        top = 0.0
        for p in shape[hand] if blocks and careful else []:  # and out of a block, over its top: a hand rests on a wall, not in it
            way = inside(at[hand] + turn @ p, at[upper] + UP * (2.0 * scale))
            if way is not None and way[2] < 0.25 * scale:
                top = max(top, way[2] + CLEAR)
        if spot is not None:  # held on its spot it stays near it: fingers a little into a wall top show less than a hand floating over it
            top = min(top, HAND_LIFT * scale / max(level, 0.05) ** 6 - risen)
        deep = max(deep, top)
        if deep <= TOUCH:
            break
        risen += deep
        goal = (goal if goal is not None else at[hand].copy()) + UP * deep
        lifted["hands"] = max(lifted["hands"], deep)
    return (goal - at[hand]) if spot is not None else None

def posed(f, off, tally, final):
    """The body on one frame with its hands where they must be. Returns (turns, facings, places, how far a hand with a spot is still off it)."""
    basis, faces, at = body(f, off, tally)
    miss, n = Vector(), 0
    for tag in ("l", "r"):
        left = reach(tag, f, basis, faces, at, final)
        if left is not None:
            miss, n = miss + left, n + 1
    return basis, faces, at, (miss / n if n else None)

def hip_of(tag, faces, at):
    return at["hips"] + faces["hips"] @ (unrest["hips"] @ (head["thigh_" + tag] - head["hips"]))

def ankle_of(tag, f):
    ball, pitch, yaw, planted = foot_target(tag, f)
    turned = spin(UP, yaw) @ spin(Vector((1, 0, 0)), pitch)
    return ball - turned @ legs[tag]["sole"]

def pitch_of(turned):
    """How far a foot's toes point down, in degrees."""
    return math.degrees(math.asin(clamp(-(turned @ Vector((0, -1, 0))).z, -1.0, 1.0)))

def leg(tag, f, faces, at, basis, fix, tally):
    """One leg on one frame: hip to ankle by two bones and a hinge, then the foot and toes. `fix` is what the
    contact step asks for: "ease" (0 to 1: how much of the heel's lift is kept) and "move" (the foot, moved).
    Returns what came of it: how deep the foot's mesh is in the floor, how to get the leg out of a block, and so on."""
    thigh, shin, foot, toe = "thigh_" + tag, "shin_" + tag, "foot_" + tag, "toe_" + tag
    l1, l2 = legs[tag]["thigh"], legs[tag]["shin"]
    hip = hip_of(tag, faces, at)
    target, asked, yaw, planted = foot_target(tag, f)
    ball = target + fix["move"]
    turned = spin(UP, yaw) @ spin(Vector((1, 0, 0)), asked * fix["ease"] if asked > 0 else asked)
    # The knee points where the hips face, and part of the way to where the foot points.
    ahead = faces["hips"] @ (unrest["hips"] @ Vector((0, -1, 0)))
    facing = math.degrees(math.atan2(ahead.x, -ahead.y))
    knee_yaw = facing + 0.6 * near_turn(yaw - facing)
    short_by, bent, hinge = 0.0, False, False
    for attempt in range(10):
        ankle = ball - turned @ legs[tag]["sole"]
        gap = ankle - hip
        far = clamp(gap.length, abs(l1 - l2) + 1e-4, STRAIGHT * (l1 + l2))
        short_by = max(0.0, gap.length - STRAIGHT * (l1 + l2))
        along = gap.normalized()
        side = spin(UP, knee_yaw) @ Vector((1, 0, 0))
        side = (side - along * side.dot(along)).normalized()
        open_by = math.acos(clamp((l1 * l1 + far * far - l2 * l2) / (2 * l1 * far), -1.0, 1.0))
        upper = Quaternion(side, -open_by) @ along  # the knee goes forward
        knee = hip + upper * l1
        follow = faces["hips"] @ unrest["hips"] @ rest[thigh]
        basis[thigh], bent = held(follow.inverted() @ frame_of(side, upper), limits.get(thigh))
        faces[thigh] = follow @ basis[thigh]
        if bent:
            knee = hip + faces[thigh].col[1] * l1
        follow = faces[thigh] @ unrest[thigh] @ rest[shin]
        lower = hip + along * far - knee if not bent else ankle - knee
        basis[shin], hinge = held(follow.inverted() @ frame_of(faces[thigh].col[0], lower), limits.get(shin))
        faces[shin] = follow @ basis[shin]
        follow = faces[shin] @ unrest[shin] @ rest[foot]
        basis[foot], changed = held(follow.inverted() @ (turned @ rest[foot]), limits.get(foot))
        faces[foot] = follow @ basis[foot]
        if not changed:
            break
        # The ankle is at a limit. The foot goes where the ankle lets it (the heel lifts, the foot
        # rolls), and the leg is solved again so the ball of the foot stays where it was planted.
        turned = faces[foot] @ unrest[foot]
    for name, was in ((thigh, bent), (shin, hinge)):
        if was:
            tally[name] = tally.get(name, 0) + 1
    # Where the leg really is, after its limits.
    knee = hip + faces[thigh] @ (unrest[thigh] @ (head[shin] - head[thigh]))
    ankle = knee + faces[shin] @ (unrest[shin] @ (head[foot] - head[shin]))
    foot_turn = faces[foot] @ unrest[foot]
    ball_at = ankle + foot_turn @ legs[tag]["sole"]
    off = ball_at - ball
    if off.length > 1e-4:  # it did not settle: a joint is clamped and the ball has moved
        tally[foot] = tally.get(foot, 0) + 1
    pitch = pitch_of(foot_turn)
    # Toes fall in line with the foot as far as the floor lets their real shape; on the floor they lie flat.
    follow = faces[foot] @ unrest[foot] @ rest[toe]
    share = 1.0
    if careful:
        level = spin(UP, yaw)
        if lowest(shape[toe], ball_at, level @ spin(Vector((1, 0, 0)), pitch)) < floor - TOUCH:
            lo, hi = 0.0, 1.0
            for step in range(7):
                share = (lo + hi) / 2.0
                if lowest(shape[toe], ball_at, level @ spin(Vector((1, 0, 0)), share * pitch)) < floor - TOUCH:
                    hi = share
                else:
                    lo = share
            share = lo
    else:  # as the bone alone has it
        room = math.degrees(math.asin(clamp((ball.z - head[toe].z) / (1.2 * (rig.data.bones[toe].length + 1e-6)), 0.0, 1.0)))
        share = clamp(pitch, -room, room) / pitch if abs(pitch) > 1e-6 else 0.0
    flat = spin(UP, yaw) @ spin(Vector((1, 0, 0)), share * pitch)
    basis[toe], changed = held(follow.inverted() @ (flat @ rest[toe]), limits.get(toe))
    if changed:
        tally[toe] = tally.get(toe, 0) + 1
    faces[toe] = follow @ basis[toe]
    out = {"planted": planted, "asked": asked, "pitch": pitch, "short": short_by, "off": Vector((off.x, off.y, 0.0)).length, "deep": 0.0, "sunk": 0.0, "out": None, "in_set": 0.0, "under": 0.0}
    if not careful:
        return out
    toe_turn = faces[toe] @ unrest[toe]
    out["deep"] = floor - min(lowest(shape[foot], ankle, foot_turn), lowest(shape[toe], ball_at, toe_turn))
    # A knee or shin in the floor (a kneel, a deep crouch on thicker legs): no place for the foot cures it. The hips rise.
    out["sunk"] = floor - min(lowest(shape[thigh], hip, faces[thigh] @ unrest[thigh]), lowest(shape[shin], knee, faces[shin] @ unrest[shin]))
    if blocks and careful and min((hip - block["mid"]).length - max(block["half"]) for block in blocks) < 1.2 * (l1 + l2 + legs[tag]["sole"].length):
        # The deepest point of the leg inside a block says which way out. A point up the leg moves less
        # than the foot does when the foot is moved, so the foot is moved by more.
        worst = 0.0
        for points, where, turn, low, high in ((shape[thigh], hip, faces[thigh] @ unrest[thigh], 0.0, 0.5), (shape[shin], knee, faces[shin] @ unrest[shin], 0.5, 1.0),
                                               (shape[foot], ankle, foot_turn, 1.0, 1.0), (shape[toe], ball_at, toe_turn, 1.0, 1.0)):
            reach_of = max([p.length for p in points] or [1.0])
            for p in points:
                way = inside(where + turn @ p, hip)
                if way is not None and way[1] > max(worst, TOUCH):
                    worst = way[1]
                    out["out"] = way[0] / clamp(low + (high - low) * p.length / reach_of, 0.4, 1.0)
                    out["under"] = way[2] if way[0].z > 0 else 0.0  # under the top of what it should pass over: if the foot can't lift it out (the leg is folded up), the hips can
        out["in_set"] = worst
    return out

def settle(tag, f, faces, at, basis, fix):
    """What one foot needs on one frame to stay out of the floor and the set, starting from `fix`. Returns (fix, what the leg does with it)."""
    got = leg(tag, f, faces, at, basis, fix, {})
    if not careful:
        return fix, got
    if got["deep"] > TOUCH and got["planted"] and got["pitch"] > 1.0 and fix["ease"] > 0:
        # Heel up and the toes dug in: they are bent as far as they go. Lower the heel by as much as it takes, if the leg still reaches.
        base = got["short"]
        tried = leg(tag, f, faces, at, basis, dict(fix, ease=0.0), {})
        if tried["deep"] <= TOUCH and tried["short"] <= base + 0.001:
            lo, hi = 0.0, fix["ease"]
            for step in range(6):
                mid = (lo + hi) / 2.0
                tried = leg(tag, f, faces, at, basis, dict(fix, ease=mid), {})
                if tried["deep"] <= TOUCH and tried["short"] <= base + 0.001:
                    lo = mid
                else:
                    hi = mid
            fix = dict(fix, ease=lo)
        got = leg(tag, f, faces, at, basis, fix, {})
    for attempt in range(6):
        if got["deep"] > TOUCH:
            more = UP * got["deep"]  # straight up, so a planted foot stays over its spot
        elif got["out"] is not None:
            more = got["out"]
        else:
            break
        trial = dict(fix, move=fix["move"] + more)
        then = leg(tag, f, faces, at, basis, trial, {})
        if max(then["deep"], 0.0) + then["in_set"] > max(got["deep"], 0.0) + got["in_set"] - 0.2 * more.length:
            got = leg(tag, f, faces, at, basis, fix, {})  # the leg is folded as far as it goes: moving the foot no longer helps. The hips must rise.
            break
        fix, got = trial, then
    return fix, got


# ---- 3a: how far the hips must come down for a planted foot to be in reach ----
lifted = {"hands": 0.0}
need = []
for g in range(span):
    basis, faces, at = body(g, Vector(), {})
    low = 0.0
    for tag in ("l", "r"):
        if not foot_target(tag, g)[3]:
            continue  # a foot in the air that is out of reach comes up short: the hips are not lowered for it
        hip = hip_of(tag, faces, at)
        ankle = ankle_of(tag, g)
        most = STRAIGHT * (legs[tag]["thigh"] + legs[tag]["shin"])
        flat = Vector((ankle.x - hip.x, ankle.y - hip.y)).length
        if flat < most:
            low = max(low, (hip.z - ankle.z) - math.sqrt(most * most - flat * flat))
        else:
            low = max(low, hip.z - ankle.z)  # out of reach even from the floor: the motion's stride is too long for these legs
    need.append(low)
drops = [max(need)] * span if looped else spread(need, DROP_FRAMES, False)
drop = max(drops)

# ---- 1 to 5, every frame: the body fitted; pinned hands put on their spots (the hips move over where an arm is too
# short); the legs solved; and what each foot needs to stay out of the floor and the set. Where a leg is folded as far
# as it goes and a knee or shin is still in the floor (a deep crouch on thicker legs), or a leg passes through a block
# it should pass over, no place for the foot helps: the hips rise by what is left, and everything is solved again. ----
# A hand held on a spot lies flat one way for as long as it is held: the way its forearm comes in when it first gets
# there (the way a wrist bends easiest). It does not turn with the arm as the body goes by.
ways = {"l": [None] * span, "r": [None] * span}
for tag in ("l", "r"):
    rows = hands.get(tag) or [None] * span
    g = 0
    while g < span:
        if not rows[g]:
            g += 1
            continue
        last = g
        while last + 1 < span and rows[last + 1]:
            last += 1
        firm = g
        for k in range(g, last + 1):
            if rows[k][3] > rows[firm][3]:
                firm = k
        basis, faces, at = body(firm, UP * -drops[firm], {})
        spot = ground + Vector((rows[firm][0] * scale, rows[firm][1] * scale, floor + rows[firm][2] * scale))
        if "forearm_" + tag in at:
            arm_to(tag, spot, basis, faces, at, 0.0, None)
            way = Vector((faces["forearm_" + tag].col[1].x, faces["forearm_" + tag].col[1].y, 0.0))
            if way.length < 0.15:  # a forearm coming straight down: away from the shoulder
                way = Vector((spot.x - at["upper_arm_" + tag].x, spot.y - at["upper_arm_" + tag].y, 0.0))
            if way.length > 1e-4:
                for k in range(g, last + 1):
                    ways[tag][k] = way.normalized()
        g = last + 1

rise = [0.0] * span
for attempt in range(RISE_ROUNDS):
    clamped, solved, wants, sunk, shift = {}, [], {"l": [], "r": []}, [], []
    for g in range(span):
        off = UP * (rise[g] - drops[g])
        over = Vector()
        if any((hands.get(tag) or [None] * span)[g] for tag in ("l", "r")):
            for again in range(3):
                miss = posed(g, off + over, {}, False)[3]
                if miss is None or miss.length < 0.002:
                    break
                over = over + Vector((miss.x, miss.y, max(0.0, miss.z)))  # over and up, never down: the floor is there
                if over.length > HIPS_FOR_A_HAND * scale:
                    over = over * (HIPS_FOR_A_HAND * scale / over.length)
        shift.append(over)
        basis, faces, at, miss = posed(g, off + over, clamped, True)
        solved.append((basis, faces, at))
        low = 0.0
        for tag in ("l", "r"):
            wants[tag].append(settle(tag, g, faces, at, basis, {"ease": 1.0, "move": Vector()}))
            got = wants[tag][-1][1]
            low = max(low, got["deep"], got["sunk"], got["under"] + CLEAR if got["in_set"] > TOUCH and got["short"] <= 0 else 0.0)
        sunk.append(low if low > TOUCH else 0.0)
    if not careful or max(sunk) <= TOUCH or attempt == RISE_ROUNDS - 1:
        break
    rise = [min(a + 1.2 * b, MOST_RISE * scale) for a, b in zip(rise, spread(sunk, DROP_FRAMES, looped))]  # a knee comes up by less than the hips do
did = {"lifted": 0.0, "lifted_frames": 0, "heel_lowered": 0.0, "heel_lowered_frames": 0, "moved_clear": 0.0, "moved_clear_frames": 0,
       "left_in_floor": 0.0, "left_in_set": 0.0, "planted_off": 0.0, "short": 0.0, "air_short": 0.0, "hand_off": 0.0}
heel_help = 0.0
for tag in ("l", "r"):
    eased = [1.0 - v for v in spread([1.0 - fix["ease"] for fix, got in wants[tag]], EASE_FRAMES, looped)]
    moves = []
    for axis in range(3):
        ahead = SET_FRAMES if blocks else EASE_FRAMES  # a foot starts over a wall well before it gets there
        more = spread([max(0.0, fix["move"][axis]) for fix, got in wants[tag]], ahead, looped)
        less = spread([max(0.0, -fix["move"][axis]) for fix, got in wants[tag]], ahead, looped)
        moves.append([a - b for a, b in zip(more, less)])
    for g in range(span):
        basis, faces, at = solved[g]
        own, alone = wants[tag][g]
        across = own["move"] if alone["planted"] else Vector((moves[0][g], moves[1][g], 0.0))  # a planted foot is not pushed sideways for a neighbouring frame's sake
        fix, got = settle(tag, g, faces, at, basis, {"ease": eased[g], "move": Vector((across.x, across.y, moves[2][g]))})
        if got["short"] > alone["short"] + 0.001 or got["off"] > alone["off"] + 0.001:
            fix = own  # eased toward its neighbours it no longer reaches: this frame keeps what it worked out alone
        got = leg(tag, g, faces, at, basis, fix, clamped)
        heel_help = max(heel_help, abs(got["pitch"] - got["asked"]))
        up_by, aside = fix["move"].z, Vector((fix["move"].x, fix["move"].y)).length
        did["lifted"], did["lifted_frames"] = max(did["lifted"], up_by), did["lifted_frames"] + (up_by > TOUCH)
        did["moved_clear"], did["moved_clear_frames"] = max(did["moved_clear"], aside), did["moved_clear_frames"] + (aside > TOUCH)
        if fix["ease"] < 0.999 and got["asked"] > 0:
            did["heel_lowered"], did["heel_lowered_frames"] = max(did["heel_lowered"], got["asked"] * (1.0 - fix["ease"])), did["heel_lowered_frames"] + 1
        did["left_in_floor"] = max(did["left_in_floor"], got["deep"])
        did["left_in_set"] = max(did["left_in_set"], got.get("in_set", 0.0))
        if got["planted"]:
            did["planted_off"], did["short"] = max(did["planted_off"], got["off"] if aside <= TOUCH else 0.0), max(did["short"], got["short"])
        else:
            did["air_short"] = max(did["air_short"], got["short"])
for g in range(span):
    for tag in ("l", "r"):
        pin = (hands.get(tag) or [None] * span)[g]
        if pin and pin[3] >= 1.0:
            spot = ground + Vector((pin[0] * scale, pin[1] * scale, floor + pin[2] * scale))
            did["hand_off"] = max(did["hand_off"], (solved[g][2]["hand_" + tag] - spot).length)
poses = [solved[f % span][0] for f in range(count)]
hips_at = [unrest["hips"] @ (solved[f % span][2]["hips"] - head["hips"]) for f in range(count)]

# ---- 6: bake ----
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
action["forge_motion"] = json.dumps({"name": motion.get("name"), "fps": fps, "frames": frames, "loop": looped,
                                     "speed_m_s": round(motion.get("travel", 0.0) * scale, 4)})

result = {
    "rig": rig.name, "action": action.name, "frames": frames, "fps": fps, "seconds": round(frames / fps, 3),
    "speed_m_s": round(motion.get("travel", 0.0) * scale, 3), "bones_keyed": len(poses[0]),
    "hips_lowered_cm": round(100 * drop, 1), "heel_lifted_for_ankle_deg": round(heel_help, 1),
    "clamped": clamped, "out_of_reach_cm": round(100 * did["short"], 2),
    "then": json.loads(rig.get("forge_then", "[]")),  # passes this rig asks for after any motion is baked: run each next (cloth.py asks for swing.py)
}
if careful:
    result["contact"] = {  # what step 4 did, from the solve (the check below measures the outcome on the mesh)
        "feet_lifted_cm": round(100 * did["lifted"], 2), "frames_a_foot_was_lifted": did["lifted_frames"],
        "heel_lowered_deg": round(did["heel_lowered"], 1), "frames_a_heel_was_lowered": did["heel_lowered_frames"],
        "legs_moved_clear_of_the_set_cm": round(100 * did["moved_clear"], 2), "frames_a_leg_was_moved_clear": did["moved_clear_frames"],
        "hands_lifted_off_the_floor_cm": round(100 * lifted["hands"], 2), "hips_moved_for_a_hand_cm": round(100 * max(v.length for v in shift), 2),
        "hips_raised_cm": round(100 * max(rise), 2), "frames_the_hips_were_raised": sum(1 for v in rise if v > TOUCH),
        "still_in_the_floor_cm": round(100 * max(0.0, did["left_in_floor"]), 2), "still_in_the_set_cm": round(100 * did["left_in_set"], 2),
        "planted_foot_off_its_spot_cm": round(100 * did["planted_off"], 2), "foot_in_the_air_short_of_its_spot_cm": round(100 * did["air_short"], 2),
        "hand_off_its_spot_cm": round(100 * did["hand_off"], 2), "blocks": [block["name"] for block in blocks],
        "points_tested": {name: len(points) for name, points in sorted(shape.items()) if points},
    }

# ---- play it back and measure ----
if PARAMS["check"]:
    meshes = [o for o in scene.objects if o.type == "MESH" and o.find_armature() == rig]
    owner = {}
    for obj in meshes:  # which bone each point mostly follows
        names = [g.name for g in obj.vertex_groups]
        owner[obj.name] = [max([(g.weight, names[g.group]) for g in v.groups] or [(0.0, "")])[1] for v in obj.data.vertices]
    step = Vector((0, motion.get("travel", 0.0) * scale / fps, 0))
    slid, worst_slide, lowest_z, outside, was = {"l": 0.0, "r": 0.0}, 0.0, 1e9, {}, {}
    first_pose, seam, lowest_frame, lowest_part = {}, 0.0, 0, ""
    landed, drift = {}, 0.0
    in_set = {"cm": 0.0, "part": "", "frame": -1, "block": "", "frames": 0, "by_part": {}}
    hand_miss = {}
    reach_all = max((v.co.length for obj in meshes for v in obj.data.vertices), default=1.0)
    for f in range(count):
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
        shown = rig.evaluated_get(deps)
        for tag in ("l", "r"):
            ball = shown.matrix_world @ shown.pose.bones["toe_" + tag].head
            planted = motion["feet"][tag][f % span][5] and motion["feet"][tag][(f - 1) % span][5]
            if f and planted:
                moved = ball - was[tag] - step
                slid[tag] += Vector((moved.x, moved.y)).length  # over the ground: a ball of the foot may rise and fall on its spot
                if tag not in landed:
                    landed[tag] = (was[tag], f - 1)
                gone = ball - landed[tag][0] - step * (f - landed[tag][1])
                drift = max(drift, Vector((gone.x, gone.y)).length)
            elif f:
                worst_slide = max(worst_slide, slid[tag])
                slid[tag] = 0.0
                landed.pop(tag, None)
            was[tag] = ball
            pin = (spots.get(tag) or [None] * span)[f % span]
            if pin and pin[3] >= 1.0:
                spot = ground + Vector((pin[0] * scale, pin[1] * scale, floor + pin[2] * scale))
                wrist = shown.matrix_world @ shown.pose.bones["hand_" + tag].head
                hand_miss[tag] = max(hand_miss.get(tag, 0.0), (wrist - rig.matrix_world @ spot).length)
        hips_now = shown.matrix_world @ shown.pose.bones["hips"].head
        near_set = [block for block in blocks if (hips_now - block["mid"]).length < reach_all + max(block["half"])]
        cut = False
        for obj in meshes:
            me = obj.evaluated_get(deps).to_mesh()
            points = [obj.matrix_world @ v.co for v in me.vertices]
            obj.evaluated_get(deps).to_mesh_clear()
            low, at_point = min((p.z, i) for i, p in enumerate(points))
            if low < lowest_z:
                lowest_z, lowest_frame, lowest_part = low, f, owner[obj.name][at_point] if at_point < len(owner[obj.name]) else ""
            for block in near_set:
                hu, hv, hw = block["half"]
                for i, p in enumerate(points):
                    d = p - block["mid"]
                    if d.z >= hw:
                        continue
                    u, v = abs(d.dot(block["across"])), abs(d.dot(block["through"]))
                    if u >= hu or v >= hv:
                        continue
                    deep = min(hw - d.z, hv - v, hu - u)
                    part = owner[obj.name][i] if i < len(owner[obj.name]) else ""
                    if deep > TOUCH:
                        cut = True
                        in_set["by_part"][part] = max(in_set["by_part"].get(part, 0.0), deep)
                    if deep > in_set["cm"]:
                        in_set.update({"cm": deep, "part": part, "frame": f, "block": block["name"]})
        in_set["frames"] += cut
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
        "planted_foot_strays_cm": round(100 * drift, 3),  # the furthest a planted foot gets from where it landed
        "through_floor_cm": round(100 * max(0.0, floor - lowest_z), 2), "lowest_frame": lowest_frame, "lowest_part": lowest_part,
        "limit_violations": sum(outside.values()), "outside": outside,
        "loop_seam": round(seam, 6), "meshes": len(meshes),
    }
    if blocks:
        result["check"]["in_the_set"] = {"deepest_cm": round(100 * in_set["cm"], 2), "part": in_set["part"], "frame": in_set["frame"], "block": in_set["block"],
                                         "frames": in_set["frames"], "deepest_by_part_cm": {k: round(100 * v, 2) for k, v in sorted(in_set["by_part"].items())}}
    if spots:
        result["check"]["hand_from_its_spot_cm"] = {tag: round(100 * v, 2) for tag, v in sorted(hand_miss.items())}
print("RESULT " + json.dumps(result))
