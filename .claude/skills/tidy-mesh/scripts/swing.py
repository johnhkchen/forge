# Make loose cloth hang and swing with a baked motion: the last pass after
# animate.py, for a rig that cloth.py gave cloth bones.
#
# animate.py bakes the body's motion and leaves the cloth bones still. This
# plays that action through once more and lets each chain of cloth bones
# trail behind the body like a row of weights on strings (the "spring bone"
# way games and VRM avatars move skirts and hair; no cloth solver, nothing a
# .glb can't carry). On every frame:
#   - each bone's end, from the top of a chain down, keeps the speed it had
#     ("drag" takes some away), is pulled back toward where it hangs at rest
#     ("stiffness"), down by "gravity", and back by the air the character
#     walks through ("air"), and stays one bone-length from the joint above;
#   - then the cloth is kept out of the legs and off the floor, all chains
#     together, a dozen times over. For a garment whose chains hang from the
#     hips or the spine (a skirt, a tunic, a coat's tails) each thigh and
#     shin is a rod as thick as the body is there, all along it and each way
#     round it (a thigh is wider front to back; a shin has its calf), found
#     by rays out to the skin as the body was made, plus "clearance". Kept
#     out of the rods are the chains, the panels of cloth between neighbouring
#     chains (a knee that slips between two chains goes through the panel,
#     not a chain), and the garment's own points, skinned as the mesh is (its
#     flounces stand off the chains, its hem hangs below the last joint, and
#     a point a thigh carries part of goes where neither puts it). A place in
#     a rod pushes the joints it hangs on out of it; cloth on the inner side
#     of a leg is taken round to the outer side ("wrap": the legs are inside
#     the garment). A place that was inside a rod as the cloth was made (a
#     waistband over the top of a thigh) may stay that far in, and no
#     further. Every point of the cloth stays above the floor;
#   - a push is not all turned into speed ("contact_damping"), so the cloth
#     slides over a leg rather than bouncing off it;
#   - and the turn that puts each bone where it is now is clamped to the
#     bone's "limit_deg" (wider for a skirt's: cloth.py).
# Before a motion that does not loop, the legs come into its first pose from
# how they stood as the cloth was made, so the cloth starts outside them.
# Each turn is then eased with the frames either side ("smooth"), and keyed
# on the cloth bones, one key a frame, into the same action. A motion that
# loops is run through three times and the last round kept (or, for a chain
# that never settles, the average of a few more), then its end is eased onto
# its start, so the loop has no seam.
#
# "check" in the result: turns outside a limit, how far the cloth (chains,
# panels and its own points) goes into a leg's skin past what it did as made,
# on how many frames, and where; how far the cloth itself, as the bones bend
# it, is below the floor; the seam; how far the hems travel.
# (scripts/impostor/judge_legs.py measures the same against the real mesh.)
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down.
# Prints RESULT {json}. A few seconds. Safe-mode compatible.

PARAMS = {
    "rig": None,        # the armature; None = the first one in the scene
    "stiffness": 1.2,   # how hard a bone is pulled back to where it hangs at rest (0 = a rag, 3 = starched)
    "drag": 0.35,       # the share of its speed a bone's end loses each frame (0 = swings for ever, 1 = never swings)
    "gravity": 0.6,     # how hard it is pulled down
    "air": 0.25,        # how much the air of walking pushes it back (uses the motion's speed)
    "rounds": 3,        # a looping motion is played this many times; the last round is kept
    "legs": True,       # keep a skirt's chains, the cloth between neighbouring chains and the cloth itself out of the thighs and shins
    "floor": True,      # keep the hem above the floor
    "wrap": True,       # cloth a leg has gone through is put back on the outside of the leg, not pushed further in
    "clearance": 0.01,  # how far the cloth keeps off the skin, as a share of the height (0.01: 17 mm on a 1.7 m body)
    "smooth": 1,        # how many times each turn is eased with the frames either side (0 = not at all)
    "contact_damping": 0.6,  # the share of a push out of a leg (or up off the floor) that does not become speed (0 = bounces, 1 = slides)
    "iterations": 12,   # how many times a frame's pushes and bone lengths are worked over
    "check": True,      # play the result back and measure it
}

import bpy
import json
import math
import numpy as np
from mathutils import Euler, Quaternion, Vector
from mathutils.bvhtree import BVHTree

RODS = ("thigh_l", "thigh_r", "shin_l", "shin_r")
SKIRT_FROM = ("hips", "spine")  # chains that hang from these hang over the legs (a skirt, a tunic, a coat's tails); a hood's hang from the head
MORE_ROUNDS = 6   # a loop whose cloth has not settled is played this many more times, and the rounds averaged
BINS = 8          # a rod's thickness is measured at this many places along it...
AROUND = 12       # ... and this many ways round it
ACROSS = (0.25, 0.5, 0.75)        # where a panel between two chains is tried, across it...
DOWN = (0.0, 1.0 / 3, 2.0 / 3, 1.0)  # ... and down it
NEIGHBOURS = 1.6  # two chains of a garment are neighbours when no further apart round it than this many times the usual gap


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

def held(basis, lim):
    """A turn (in the bone's own axes) brought inside its limits."""
    e = basis.to_euler("XYZ")
    want = [clamp(math.degrees(e[k]), lim[2 * k], lim[2 * k + 1]) for k in range(3)]
    if all(abs(want[k] - math.degrees(e[k])) < 0.02 for k in range(3)):
        return basis
    return Euler([math.radians(v) for v in want], "XYZ").to_matrix()

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

def thick_at(profile, t, way, x_axis, z_axis):
    """A rod's radius at `t` along it (0 at its head, 1 at its tail) the way `way` (unit, [n, 3]) out of it, from its
    thickness at BINS places along it and AROUND ways round it (in its bone's x and z): a thigh is wider front to
    back than side to side, and a shin has its calf behind."""
    steps, around = profile.shape
    at = np.clip(t, 0.0, 1.0) * steps - 0.5
    lo = np.clip(np.floor(at).astype(int), 0, steps - 1)
    hi = np.clip(lo + 1, 0, steps - 1)
    f = np.clip(at - lo, 0.0, 1.0)
    turn = (np.arctan2(way @ z_axis, way @ x_axis) % (2.0 * math.pi)) / (2.0 * math.pi) * around
    a0 = np.floor(turn).astype(int) % around
    a1 = (a0 + 1) % around
    g = turn - np.floor(turn)
    ring = lambda s: profile[s, a0] * (1.0 - g) + profile[s, a1] * g
    return ring(lo) * (1.0 - f) + ring(hi) * f

def in_rods(points, rods, allow, outward=None):
    """How far each point is inside each rod past what it may be: [points, rods] (m, negative = clear), and for each
    point and rod the move that takes it out [points, rods, 3].

    A leg is inside the garment, so cloth that a leg has gone through is put back on the leg's outside: `outward`
    (for each point, the way out of the garment there, or nought) says which side that is. A point on the inner side
    of a rod is taken round it to the outer side, not pushed further in (a chain that hung straight while a knee came
    up through it goes over the knee, not under it)."""
    over = np.full((len(points), len(rods)), -1.0)
    move = np.zeros((len(points), len(rods), 3))
    for r, (a, b, profile, x_axis, z_axis) in enumerate(rods):
        ab = b - a
        t = np.clip((points - a) @ ab / max(float(ab @ ab), 1e-12), 0.0, 1.0)
        on = a + t[:, None] * ab
        away = points - on
        far = np.linalg.norm(away, axis=1)
        way = away / np.maximum(far, 1e-9)[:, None]
        reach = thick_at(profile, t, way, x_axis, z_axis) - allow[:, r]
        if outward is not None:
            facing = (way * outward).sum(axis=1)
            wrong = (facing < 0.0) & (allow[:, r] <= 0.0) & (far < reach)
            way[wrong] -= 2.0 * facing[wrong][:, None] * outward[wrong]  # the same way round the rod, but on its outer side
            reach[wrong] = thick_at(profile, t[wrong], way[wrong], x_axis, z_axis)
        target = on + way * reach[:, None]
        move[:, r] = target - points
        over[:, r] = np.where(far < reach, np.linalg.norm(move[:, r], axis=1), reach - far)
        over[far < 1e-6, r] = -1.0  # on the rod's very line there is no way out: left to the next frame
    return over, move


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
free = [-180, 180, -180, 180, -180, 180]

if chains:
    rest = {b.name: b.matrix_local.copy() for b in rig.data.bones}
    span = {b.name: b.length for b in rig.data.bones}
    for c in chains:
        c["local"] = [(rest[c["bones"][i - 1] if i else c["parent"]]).inverted() @ rest[name] for i, name in enumerate(c["bones"])]
    turn = rig.matrix_world.to_3x3()
    down = (turn.inverted() @ Vector((0, 0, -1))).normalized()
    wind = turn.inverted() @ Vector((0, 1, 0)) * (about.get("speed_m_s") or 0.0)  # it faces -y: the air comes at it and blows back
    up = -np.array(down)
    floor_at = np.array(rig.matrix_world.inverted() @ Vector((0.0, 0.0, measure.get("floor", 0.0))))

    # ---- the joints: every chain's, in one array; a chain's first is where it hangs from and never moves ----
    first_joint, count = [], 0
    for c in chains:
        first_joint.append(count)
        count += len(c["bones"]) + 1
    movable = np.ones(count, dtype=bool)
    movable[first_joint] = False
    def rest_joints():
        out = np.zeros((count, 3))
        for c, j in zip(chains, first_joint):
            out[j] = np.array(rest[c["bones"][0]].translation)
            for i, name in enumerate(c["bones"]):
                out[j + i + 1] = np.array(rest[name] @ Vector((0, span[name], 0)))
        return out
    resting = rest_joints()

    # ---- neighbours: the chains of one garment, in order round where they hang from, next to each other ----
    links, groups = [], {}
    for k, c in enumerate(chains):
        groups.setdefault((c.get("gear"), c["parent"]), []).append(k)
    for (_, parent), members in groups.items():
        if len(members) < 2:
            continue
        middle = np.array(rest[parent].translation)
        side = np.cross(up, [1.0, 0.0, 0.0]) if abs(up[0]) < 0.9 else np.cross(up, [0.0, 1.0, 0.0])
        side /= np.linalg.norm(side)
        other = np.cross(up, side)
        def angle_of(k):
            v = resting[first_joint[k] + len(chains[k]["bones"])] - middle  # where its hem is, round the middle
            return math.atan2(float(v @ other), float(v @ side))
        ring = sorted(members, key=angle_of)
        angles = [angle_of(k) for k in ring]
        gaps = [(angles[i + 1] - angles[i], ring[i], ring[i + 1]) for i in range(len(ring) - 1)]
        if len(ring) > 2:
            gaps.append((2 * math.pi - (angles[-1] - angles[0]), ring[-1], ring[0]))
        usual = sorted(g for g, _, _ in gaps)[len(gaps) // 2]
        links += [(a, b) for g, a, b in gaps if g <= NEIGHBOURS * usual + 1e-9]

    # ---- the places the cloth is tried at: along every chain, and across every panel between neighbours ----
    # (not the upper part of the top bones: cloth there is held by the body's own weights, cloth.py, and goes with the hips and thighs)
    group_of = {k: g for g, members in enumerate(groups.values()) for k in members}
    corners, shares, owner = [], [], []
    for k, c in enumerate(chains):
        j = first_joint[k]
        for i in range(len(c["bones"])):
            for v in DOWN[1:]:
                if i == 0 and v < 0.5:
                    continue
                corners.append([j + i, j + i + 1, j + i, j + i + 1])
                shares.append([1.0 - v, v, 0.0, 0.0])
                owner.append(group_of[k])
    on_chains = len(corners)  # the places before these are on the chains themselves
    for a, b in links:
        for i in range(min(len(chains[a]["bones"]), len(chains[b]["bones"]))):
            ja, jb = first_joint[a] + i, first_joint[b] + i
            for v in DOWN:
                if i == 0 and v < 0.5:
                    continue
                for u in ACROSS:
                    corners.append([ja, jb, ja + 1, jb + 1])
                    shares.append([(1 - u) * (1 - v), u * (1 - v), (1 - u) * v, u * v])
                    owner.append(group_of[a])
    corners, shares, owner = np.array(corners, dtype=np.int64), np.array(shares), np.array(owner, dtype=np.int64)
    pushable = shares * movable[corners]
    weight_sq = (pushable ** 2).sum(axis=1)

    def tried(joints):
        return (shares[:, :, None] * joints[corners]).sum(axis=1)

    # ---- each garment's middle: a line down from the middle of where its chains hang, the way they hang, in the frame
    # of the bone they hang from. Out of the garment is away from it (for a garment of three chains or more) ----
    middles = []
    for (_, parent), members in groups.items():
        tops = np.array([resting[first_joint[k]] for k in members])
        ends = np.array([resting[first_joint[k] + len(chains[k]["bones"])] for k in members])
        hang = (ends - tops).mean(axis=0)
        hang = hang / max(float(np.linalg.norm(hang)), 1e-9)
        back = rest[parent].inverted()
        middles.append((parent, np.array(back @ Vector(tops.mean(axis=0).tolist())), np.array(back.to_3x3() @ Vector(hang.tolist())), len(members) >= 3))

    def outward_of(points, shot, owners):
        """For each place tried, the way out of its garment there (nought for a garment too open to say)."""
        out = np.zeros_like(points)
        for g, (parent, top, hang, around) in enumerate(middles):
            if not around:
                continue
            frame = shot["parent"][parent]
            top_now = np.array(frame @ Vector(top.tolist()))
            hang_now = np.array(frame.to_3x3() @ Vector(hang.tolist()))
            hang_now /= max(float(np.linalg.norm(hang_now)), 1e-9)
            mine = owners == g
            rel = points[mine] - top_now
            side = rel - np.outer(np.maximum(rel @ hang_now, 0.0), hang_now)  # from the nearest point of the line down
            size = np.linalg.norm(side, axis=1)
            out[mine] = np.where(size[:, None] > 1e-6, side / np.maximum(size, 1e-9)[:, None], 0.0)
        return out

    # ---- a rod round each thigh and shin, as thick as the body is there, all along it ----
    # From the bone's line out to the skin, at BINS places along it and AROUND ways round it, on the body as it was
    # made: rays, so a thigh is as wide as it is each way and a shin has its calf. A ray that finds no skin of its own
    # bone's side near by (a hole, the other leg) takes the thickness of the rest of that ring.
    rods = []
    flesh = [o for o in scene.objects if o.type == "MESH" and o.find_armature() == rig and o.get("forge") != "gear"]
    if PARAMS["legs"] and flesh:
        world_back = rig.matrix_world.inverted()
        points, faces, start = [], [], 0
        for obj in flesh:
            place = world_back @ obj.matrix_world
            points += [place @ v.co for v in obj.data.vertices]
            faces += [[start + i for i in poly.vertices] for poly in obj.data.polygons]
            start += len(obj.data.vertices)
        skin = BVHTree.FromPolygons(points, faces)
    for name in RODS if PARAMS["legs"] and flesh else ():
        if name not in rest:
            continue
        a, b = np.array(rest[name].translation), np.array(rest[name] @ Vector((0, span[name], 0)))
        x_axis, z_axis = np.array(rest[name].to_3x3().col[0].normalized()), np.array(rest[name].to_3x3().col[2].normalized())
        reach = 0.12 * tall
        profile = np.zeros((BINS, AROUND))
        for s in range(BINS):
            middle = a + (b - a) * ((s + 0.5) / BINS)
            for k in range(AROUND):
                angle = 2.0 * math.pi * k / AROUND
                hit = skin.ray_cast(Vector(middle.tolist()), Vector((math.cos(angle) * x_axis + math.sin(angle) * z_axis).tolist()), reach)
                profile[s, k] = hit[3] if hit[3] is not None else 0.0
            found = profile[s][profile[s] > 0]
            if len(found):
                usual = float(np.median(found))
                profile[s][(profile[s] <= 0) | (profile[s] > 1.6 * usual)] = usual
        if not profile.any():
            continue
        for s in range(BINS):  # a ring with no skin at all (past the end of the body) takes its neighbour's
            if not profile[s].any():
                profile[s] = profile[s - 1] if s else profile[min(BINS - 1, s + 1)]
        rods.append((name, profile + PARAMS["clearance"] * tall))  # and the cloth's own thickness, and a little room
    rest_rods = [(np.array(rest[name].translation), np.array(rest[name] @ Vector((0, span[name], 0))), profile,
                  np.array(rest[name].to_3x3().col[0].normalized()), np.array(rest[name].to_3x3().col[2].normalized())) for name, profile in rods]
    result["rods_cm"] = {name: [[round(100 * float(r), 1) for r in (ring.min(), ring.max())] for ring in profile] for name, profile in rods}
    result["panels"] = len(links) * max([len(c["bones"]) for c in chains] or [0])

    # ---- the cloth itself: every point of the garment the chains pull on, skinned as the mesh is (its pull shared
    # between chain bones and, near the waist or where it rested on a thigh, the body's bones). The chains are a few
    # lines through the cloth; its flounces stand off them, its hem hangs below the last joint, and a point a thigh
    # carries part of goes where neither the thigh nor the chain puts it. So the legs and the floor are kept from
    # these points too, each pushing the end of the chain bone that pulls on it most, as far again as it is short ----
    lift = 0.006 * tall  # how far off the floor the cloth keeps (1 cm on a 1.7 m body)
    gear = [o for o in scene.objects if o.type == "MESH" and o.find_armature() == rig and o.get("forge") == "gear"]
    bone_list = [(k, i, name) for k, c in enumerate(chains) for i, name in enumerate(c["bones"])]
    bone_at = {name: b for b, (_, _, name) in enumerate(bone_list)}
    rest_way = np.array([np.array(rest[name].to_3x3().col[1].normalized()) for _, _, name in bone_list]).reshape(-1, 3)
    rest_head = np.array([np.array(rest[name].translation) for _, _, name in bone_list]).reshape(-1, 3)
    rest_turn = {c["parent"]: np.array(rest[c["parent"]].to_3x3().normalized()) for c in chains}
    body_bones, cloth_at, cloth_pulls, cloth_shares, cloth_end, cloth_lever, cloth_owner = [], [], [], [], [], [], []
    for obj in gear:
        names = {g.index: g.name for g in obj.vertex_groups}
        place = rig.matrix_world.inverted() @ obj.matrix_world
        for v in obj.data.vertices:
            pulls = sorted(((g.weight, names[g.group]) for g in v.groups if g.weight > 1e-4 and names.get(g.group) in rest), reverse=True)[:4]
            by_chains = [(w, n) for w, n in pulls if n in bone_at]
            swung = sum(w for w, _ in by_chains)
            total = sum(w for w, _ in pulls)
            if not by_chains or swung < 0.3 * total:
                continue  # a point the body carries (a waistband): it goes where the body goes
            at = np.array(place @ v.co)
            main = bone_at[by_chains[0][1]]
            k, i, name = bone_list[main]
            index, share = [], []
            for w, n in pulls:
                if n not in bone_at and n not in body_bones:
                    body_bones.append(n)
                index.append(bone_at[n] if n in bone_at else -1 - body_bones.index(n))
                share.append(w / total)
            while len(index) < 4:
                index.append(main)
                share.append(0.0)
            cloth_at.append(at)
            cloth_pulls.append(index)
            cloth_shares.append(share)
            cloth_end.append(first_joint[k] + i + 1)
            # how far the point moves for each step of its bone's end: less near the top of the bone, and less the less the chains pull on it
            cloth_lever.append(clamp(float((at - rest_head[main]) @ rest_way[main]) / span[name], 0.5, 1.0) * clamp(swung / total, 0.3, 1.0))
            cloth_owner.append(group_of[k])
    cloth_at, cloth_shares = np.array(cloth_at).reshape(-1, 3), np.array(cloth_shares).reshape(-1, 4)
    cloth_pulls = np.array(cloth_pulls, dtype=np.int64).reshape(-1, 4)
    cloth_pulls = np.where(cloth_pulls < 0, len(bone_list) + (-1 - cloth_pulls), cloth_pulls)  # chain bones first, then the body's
    cloth_end, cloth_owner, cloth_lever = np.array(cloth_end, dtype=np.int64), np.array(cloth_owner, dtype=np.int64), np.array(cloth_lever)
    cloth_bone = cloth_end  # (how many there are)
    body_rest_back = [np.array(rest[n].inverted()) for n in body_bones]
    result["cloth_points"] = len(cloth_at)

    # Cloth that is inside a rod as it was made (a waistband over the top of a thigh, a kilt resting on one) may stay
    # that far in. Only a garment that hangs over the legs is kept from them: a hood's chains swing free as they did.
    def allowed(points, owners):
        allow = np.zeros((len(points), len(rods)))
        if not rods:
            return allow
        over, _ = in_rods(points, rest_rods, allow)
        allow = np.maximum(over, 0.0)
        for g, (parent, _, _, _) in enumerate(middles):
            for r, (name, _) in enumerate(rods):
                if not (parent in SKIRT_FROM and name.startswith(("thigh", "shin"))):
                    allow[owners == g, r] = 1e9
        return allow
    allow = allowed(tried(resting), owner)
    cloth_allow = allowed(cloth_at, cloth_owner)

    def turn_between(a, b):
        """The least turn (3x3) that takes unit `a` to unit `b`."""
        axis, cos = np.cross(a, b), float(a @ b)
        if cos < -0.999999:
            side = np.cross(a, [1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.cross(a, [0.0, 1.0, 0.0])
            side /= np.linalg.norm(side)
            return 2.0 * np.outer(side, side) - np.eye(3)
        k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        return np.eye(3) + k + k @ k / (1.0 + cos)

    def cloth_now(joints, shot):
        """Where the cloth's points are with every chain bone between its joints as they are now: each carried by its
        bone turned the least way from how it hangs at rest, after the turn of the bone the chain hangs from."""
        moves = np.zeros((len(bone_list) + len(body_bones), 3, 4))  # how each bone moves a point, from where it was made
        for b, (k, i, name) in enumerate(bone_list):
            parent = chains[k]["parent"]
            spin = np.array(shot["parent"][parent].to_3x3().normalized()) @ rest_turn[parent].T
            head = joints[first_joint[k] + i]
            way = joints[first_joint[k] + i + 1] - head
            turn = turn_between(spin @ rest_way[b], way / max(float(np.linalg.norm(way)), 1e-9)) @ spin
            moves[b, :, :3], moves[b, :, 3] = turn, head - turn @ rest_head[b]
        for n, (now, back) in enumerate(zip(shot["body"], body_rest_back)):
            moves[len(bone_list) + n] = (now @ back)[:3]
        out = np.zeros_like(cloth_at)
        for j in range(4):
            m = moves[cloth_pulls[:, j]]
            out += cloth_shares[:, j, None] * (np.einsum("nij,nj->ni", m[:, :, :3], cloth_at) + m[:, :, 3])
        return out

    # ---- the body's motion, frame by frame: where each chain's parent is, and where the rods are ----
    def rods_now(pose):
        return [(np.array(pose[name].head), np.array(pose[name].tail), profile, np.array(pose[name].matrix.to_3x3().col[0].normalized()),
                 np.array(pose[name].matrix.to_3x3().col[2].normalized())) for name, profile in rods]
    taken = []
    for f in range(frames + 1):
        scene.frame_set(f)
        pose = rig.pose.bones
        taken.append({"parent": {c["parent"]: pose[c["parent"]].matrix.copy() for c in chains},
                      "rods": rods_now(pose), "body": [np.array(pose[n].matrix) for n in body_bones]})

    def swing_chain(c, state, shot, dt):
        """Where each bone's end would go, swinging free: its speed, the pulls on it, one bone-length from the joint above."""
        above, ends = shot["parent"][c["parent"]], []
        for i, name in enumerate(c["bones"]):
            follow = above @ c["local"][i]
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
            want = axes.inverted() @ (end - head).normalized()
            basis = held(Vector((0, 1, 0)).rotation_difference(want).to_matrix(), limits.get(name) or free)
            end = head + axes @ basis @ Vector((0, span[name], 0))
            ends.append(end)
            above = follow @ basis.to_4x4()
        return ends

    def lengths(joints):
        """Each chain's joints brought back to a bone-length apart, from the top down."""
        for c, j in zip(chains, first_joint):
            for i, name in enumerate(c["bones"]):
                way = joints[j + i + 1] - joints[j + i]
                joints[j + i + 1] = joints[j + i] + way * (span[name] / max(float(np.linalg.norm(way)), 1e-9))

    def kept_clear(joints, shot):
        """The cloth pushed out of the rods and up off the floor, a few times over, its bones kept their length."""
        for _ in range(int(PARAMS["iterations"])):
            who, wants = [], []  # which joint, and how far each push would move it
            if rods:
                points = tried(joints)
                over, move = in_rods(points, shot["rods"], allow, outward_of(points, shot, owner) if PARAMS["wrap"] else None)
                deepest = np.argmax(over, axis=1)  # each place is pushed out of the rod it is deepest in
                depth = over[np.arange(len(over)), deepest]
                hit = np.nonzero((depth > 1e-5) & (weight_sq > 1e-9))[0]
                if len(hit):
                    # a place between joints: its move shared out among the joints at its corners by how much each holds it
                    push = move[hit, deepest[hit]] / weight_sq[hit][:, None]
                    who.append(corners[hit].ravel())
                    wants.append((push[:, None, :] * pushable[hit][:, :, None]).reshape(-1, 3))
            if len(cloth_bone):
                points = cloth_now(joints, shot)
                if rods:
                    over, move = in_rods(points, shot["rods"], cloth_allow, outward_of(points, shot, cloth_owner) if PARAMS["wrap"] else None)
                    deepest = np.argmax(over, axis=1)
                    depth = over[np.arange(len(over)), deepest]
                    hit = np.nonzero(depth > 1e-5)[0]
                    if len(hit):  # a point of the cloth: the end of its bone, moved as far again as the point is short of it
                        who.append(cloth_end[hit])
                        wants.append(move[hit, deepest[hit]] / cloth_lever[hit][:, None])
                if PARAMS["floor"]:
                    short = lift - (points - floor_at) @ up
                    hit = np.nonzero(short > 1e-5)[0]
                    if len(hit):
                        who.append(cloth_end[hit])
                        wants.append(np.outer(short[hit] / cloth_lever[hit], up))
            if PARAMS["floor"]:
                short = lift - (joints - floor_at) @ up
                hit = np.nonzero(movable & (short > 1e-5))[0]
                if len(hit):
                    who.append(hit)
                    wants.append(np.outer(short[hit], up))
            if not who:
                break
            # a joint that several pushes want to move goes as far as the one that wants it moved furthest
            who, wants = np.concatenate(who), np.concatenate(wants)
            order = np.argsort(np.linalg.norm(wants, axis=1))
            best = np.zeros_like(joints)
            best[who[order]] = wants[order]  # the furthest is written last
            joints += best
            lengths(joints)
        return joints

    def turns_to(c, j, joints, shot):
        """The turn of each bone (in its own axes, inside its limits) that points it at the joint below, from the top down; and where its end is then."""
        above, turns, ends = shot["parent"][c["parent"]], [], []
        for i, name in enumerate(c["bones"]):
            follow = above @ c["local"][i]
            head = follow.translation
            axes = follow.to_3x3()
            way = Vector(joints[j + i + 1].tolist()) - head
            want = axes.inverted() @ (way.normalized() if way.length > 1e-9 else axes.col[1])
            basis = held(Vector((0, 1, 0)).rotation_difference(want).to_matrix(), limits.get(name) or free)
            ends.append(head + axes @ basis @ Vector((0, span[name], 0)))
            turns.append(basis)
            above = follow @ basis.to_4x4()
        return turns, ends

    def step(states, shot, dt):
        """One frame for every chain together: returns each chain's bones' turns, and leaves the new ends in `states`."""
        joints = np.zeros((count, 3))
        free_ends = []
        for c, j, state in zip(chains, first_joint, states):
            joints[j] = np.array((shot["parent"][c["parent"]] @ c["local"][0]).translation)
            ends = swing_chain(c, state, shot, dt)
            free_ends.append(ends)
            for i, end in enumerate(ends):
                joints[j + i + 1] = np.array(end)
        joints = kept_clear(joints, shot)
        out = []
        for c, j, state, ends in zip(chains, first_joint, states, free_ends):
            turns, final = turns_to(c, j, joints, shot)
            for i in range(len(c["bones"])):
                # what the push moved it by mostly does not become speed: the cloth slides over a leg, it does not bounce off it
                state["was"][i], state["now"][i] = state["now"][i] + (final[i] - ends[i]) * PARAMS["contact_damping"], final[i]
            out.append(turns)
        return out

    dt = 1.0 / fps
    states = [{"now": [None] * len(c["bones"]), "was": [None] * len(c["bones"])} for c in chains]
    if loops:
        for _ in range(max(1, int(PARAMS["rounds"])) - 1):
            for f in range(frames):
                step(states, taken[f], dt)
        # A chain that a leg knocks about may never settle into the loop: every round ends some degrees from
        # where it started, a different way each time (the troll's kilt, thrown 80 degrees by thighs 40 cm
        # thick). Then it is played round a few more times, each round starting where the last one ended, and
        # the rounds are averaged frame by frame: what the ends are short of the starts shrinks by as many
        # times as there are rounds.
        rounds = [[step(states, taken[f], dt) for f in range(frames + 1)]]
        shorts = [max(math.degrees(a.to_quaternion().rotation_difference(b.to_quaternion()).angle) for a, b in zip(rounds[0][0][k], rounds[0][frames][k])) for k in range(len(chains))]
        if max(shorts) >= 1.0:
            for again in range(MORE_ROUNDS):
                rounds.append([rounds[-1][frames]] + [step(states, taken[f], dt) for f in range(1, frames + 1)])
        played = []
        for k, c in enumerate(chains):
            if shorts[k] < 1.0:
                played.append([rounds[0][f][k] for f in range(frames + 1)])
                continue
            middle = []
            for f in range(frames + 1):
                row = []
                for i in range(len(c["bones"])):
                    first_q = rounds[0][f][k][i].to_quaternion()
                    total = [0.0, 0.0, 0.0, 0.0]
                    for one in rounds:
                        q = one[f][k][i].to_quaternion()
                        if q.dot(first_q) < 0:
                            q.negate()
                        total = [t + v for t, v in zip(total, q)]
                    row.append(held(Quaternion(total).normalized().to_matrix(), limits.get(c["bones"][i]) or free))
                middle.append(row)
            played.append(middle)
    else:
        # Let it settle into the first pose before the motion starts. The legs come into that pose from how they
        # stood as the cloth was made, over the first two thirds of the settling, so the cloth is pushed aside the
        # way a leg would push it, from outside, and is never found with a leg already half through it.
        first = taken[0]
        anchor = np.array(first["parent"][chains[0]["parent"]])
        back_now, back_rest = np.linalg.inv(anchor), np.linalg.inv(np.array(rest[chains[0]["parent"]]))
        for s in range(30):
            mix = min(1.0, s / 20.0)
            def between_(at_rest, now):  # a point, or a bone's frame, part way from where it was made to where it is now, carried by the anchor
                return anchor @ ((1.0 - mix) * (back_rest @ at_rest) + mix * (back_now @ now))
            point = lambda a, b: between_(np.append(a, 1.0), np.append(b, 1.0))[:3]
            rods_then = [(point(ra, a), point(rb, b), profile, (1 - mix) * (anchor[:3, :3] @ back_rest[:3, :3] @ rx) + mix * x, (1 - mix) * (anchor[:3, :3] @ back_rest[:3, :3] @ rz) + mix * z)
                         for (ra, rb, profile, rx, rz), (a, b, _, x, z) in zip(rest_rods, first["rods"])]
            body_then = [between_(np.array(rest[n]), now) for n, now in zip(body_bones, first["body"])]
            step(states, {"parent": first["parent"], "rods": rods_then, "body": body_then}, dt)
        steps = [step(states, taken[f], dt) for f in range(frames + 1)]
        played = [[steps[f][k] for f in range(frames + 1)] for k in range(len(chains))]

    # ---- a leg's pushes come a frame at a time; each turn is eased with the frames either side of it, so the cloth
    # does not flicker where a leg holds it (a loop's ends are each other's neighbours) ----
    for _ in range(int(PARAMS["smooth"])):
        for k, c in enumerate(chains):
            turns = played[k]
            eased = []
            for f in range(len(turns)):
                if not loops and f in (0, len(turns) - 1):
                    eased.append(turns[f])
                    continue
                row = []
                for i in range(len(c["bones"])):
                    qs = [turns[(f + d) % len(turns)][i].to_quaternion() for d in (-1, 0, 1)]
                    for q in (qs[0], qs[2]):
                        if q.dot(qs[1]) < 0:
                            q.negate()
                    mix = Quaternion([0.25 * a + 0.5 * b + 0.25 * e for a, b, e in zip(*qs)]).normalized()
                    row.append(held(mix.to_matrix(), limits.get(c["bones"][i]) or free))
                eased.append(row)
            played[k] = eased

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
                    quats[f] = held(eased.to_matrix(), limits.get(name) or free).to_quaternion()
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
        outside, inside_cm, below_cm, seam, swing, first_pose, lowest, highest = {}, 0.0, 0.0, 0.0, 0.0, {}, {}, {}
        frames_in, where = 0, None
        swung_bones = {name for c in chains for name in c["bones"]}
        worn = [o for o in gear if PARAMS["floor"] and any(g.group in {x.index for x in o.vertex_groups if x.name in swung_bones} and g.weight > 0.05
                                                         for v in o.data.vertices for g in v.groups)]
        for f in range(frames + 1):
            scene.frame_set(f)
            pose = rig.pose.bones
            joints = np.zeros((count, 3))
            for c, j in zip(chains, first_joint):
                joints[j] = np.array(pose[c["bones"][0]].head)
                for i, name in enumerate(c["bones"]):
                    joints[j + i + 1] = np.array(pose[name].tail)
            if rods:
                over, _ = in_rods(tried(joints), rods_now(pose), allow)
                over -= PARAMS["clearance"] * tall  # into the skin itself, not the room kept off it
                deepest = float(over.max())
                if 100 * deepest > inside_cm:
                    s, r = np.unravel_index(int(np.argmax(over)), over.shape)
                    where = {"frame": f, "rod": rods[r][0], "on": "a chain" if s < on_chains else "a panel", "joints": [int(x) for x in corners[s]]}
                if len(cloth_bone):
                    shot = {"parent": {c["parent"]: pose[c["parent"]].matrix.copy() for c in chains}, "body": [np.array(pose[n].matrix) for n in body_bones]}
                    over, _ = in_rods(cloth_now(joints, shot), rods_now(pose), cloth_allow)
                    over -= PARAMS["clearance"] * tall
                    if float(over.max()) > deepest:
                        deepest = float(over.max())
                        if 100 * deepest > inside_cm:
                            s, r = np.unravel_index(int(np.argmax(over)), over.shape)
                            where = {"frame": f, "rod": rods[r][0], "on": "the cloth", "joint": int(cloth_end[s])}
                inside_cm = max(inside_cm, 100 * deepest)
                frames_in += deepest > 0.005
            if worn:  # the cloth itself, as the bones bend it: its lowest point against the floor
                graph = bpy.context.evaluated_depsgraph_get()
                for obj in worn:
                    held_obj = obj.evaluated_get(graph)
                    mesh = held_obj.to_mesh()
                    co = np.empty(len(mesh.vertices) * 3)
                    mesh.vertices.foreach_get("co", co)
                    held_obj.to_mesh_clear()
                    m = np.array(obj.matrix_world)
                    low = float((co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3])[:, 2].min())
                    below_cm = max(below_cm, 100 * (measure.get("floor", 0.0) - low))
            for c in chains:
                for i, name in enumerate(c["bones"]):
                    bone = pose[name]
                    e = bone.matrix_basis.to_3x3().to_euler("XYZ")
                    lim = limits.get(name)
                    if lim and any(not lim[2 * k] - 0.1 <= math.degrees(e[k]) <= lim[2 * k + 1] + 0.1 for k in range(3)):
                        outside[name] = outside.get(name, 0) + 1
                    swing = max(swing, math.degrees(bone.matrix_basis.to_quaternion().angle))
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
            "deepest_in_a_leg_cm": round(max(inside_cm, 0.0), 2), "frames_in_a_leg": int(frames_in), "deepest_where": where,
            "hem_below_floor_cm": round(max(below_cm, 0.0), 2) if PARAMS["floor"] else None,
            "loop_seam": round(seam, 6), "most_swing_deg": round(swing, 1),
            "hem_travels_cm": round(100 * max([(highest[k] - lowest[k]).length for k in lowest] or [0.0]), 1),
        }
print("RESULT " + json.dumps(result))
