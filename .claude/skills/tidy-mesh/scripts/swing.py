# Make loose cloth move with a baked motion: the last pass after animate.py,
# for a rig that cloth.py gave cloth bones. This is the one fabric step. Every
# way a motion gets onto a character (the walk, a run, a shot, a fight, a ride,
# the screen-test motions) ends here, and nothing else moves cloth.
#
# animate.py bakes the body's motion and leaves the cloth bones still. This
# plays that action through once more with each loose garment simulated as
# the sheet of cloth it is, by Blender's own cloth simulation, and carries
# what the simulated cloth does onto the garment's bones. What each garment
# is like comes from cloth.py's one description of it ("forge_cloth" on the
# rig: its kind, how heavy and stiff, how far it may swing, what it is kept
# out of); nothing here asks what it is called or who wears it.
#
#   1. The sheet. Each garment the chains pull on is copied, its points welded
#      (a .glb splits a point at every seam of its texture; unwelded, cloth
#      falls apart along them). What the body carries of it (a waistband, a
#      hood where it sits on the head) is pinned to the body; the rest is
#      free. It collides with the body's skin, with every other piece of
#      clothing (an apron lies on a tunic and trousers, not on the skin under
#      them) and with the floor.
#   2. The start. The body is first held as it was made while the cloth
#      settles on it ("settle"), then turned into the motion's first pose
#      ("preroll"), so no limb starts half through the cloth. Then the motion
#      plays. A loop is played round "rounds" times and the last two rounds
#      kept: cloth never comes round to quite where it was, so the last round
#      is faded into the one before it, frame by frame, and the loop closes on
#      itself with no seam and no frame that is not something the cloth did.
#   3. Onto the bones. Each chain bone is given the turn AND the move that
#      best carry its own patch of the cloth (the points it pulls on, by how
#      much) from where the simulated cloth settled to where it is on that
#      frame. A bone is a patch of cloth, free to slide, not a rod hung off
#      the one above (cloth.py makes them unjoined). A kind's "drape" says
#      what the patch is carried from: where the garment was made (1: it takes
#      the hang of the simulated cloth, standing still too, so a flounce built
#      standing out hangs under its weight) or where the simulated cloth
#      settled (0: it keeps the shape it was made in until something moves it:
#      a hood).
#
# The cloth has to be heavy for how stiff it is. Blender's springs do not get
# stiffer with the cloth's weight, so a light sheet (0.15 kg a point, as this
# was first set) is held up by its own stiffness: flung by a knee, a hem
# stayed 20 cm up for the rest of the clip, like a parasol. At 2 kg a point,
# soft to fold and to squash, the same hem is back down in half a second.
#   4. Kept clear. A few rigid patches cannot follow every fold, so the
#      garment's own points, skinned as the mesh is, are tried once more
#      against the body: each part its kind names (legs: thighs and shins;
#      arms: upper arms, forearms and hands; trunk; head) is a rod as thick as
#      the body is there, all along it and each way round it, found by rays out
#      to the skin as the body was made, plus "clearance". A point in a rod is
#      put out of it on the side the simulated cloth is on there (over a knee
#      that came up under it, not under; outside a hand that pressed it, not
#      behind), its faces' middles too (a thin arm goes between a coarse
#      garment's points), and each patch moves by what its points are short. A
#      point that was in a rod as the cloth was made (a waistband over the top
#      of a thigh) may stay that far in. Where a leg and an arm both want a
#      point, the leg has it. No point goes under the floor.
#   5. Each bone's turn and move are brought inside how far its kind may swing
#      and slide, eased with the frames either side ("smooth"), and keyed, one
#      key a frame, into the same action. What is keyed is only bones: a .glb
#      carries it, and whatever is skinned to the chains (the cards' pieces)
#      moves by it.
#
# "check" in the result plays it back and measures the cloth as Blender bends
# it: turns outside a limit, how far the garment's points go into the body
# past what they did as made (and into a leg alone), on how many frames, and
# where; how far the cloth is below the floor; the seam; how far the bones
# swing and slide and the hems travel. "simulated_cloth" says the same of the
# simulated sheet itself (what is lost between the two is lost in carrying it
# onto the bones), and how far it settled from the shape the garment was made
# in. (scripts/fabric_judge.py measures a finished .glb against the real mesh,
# any garment against any part; scripts/impostor/judge_legs.py a skirt
# against the legs.)
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down.
# Prints RESULT {json}. Four to ten seconds for six seconds of motion. The profile runner's own (it uses numpy, which the add-on's safe mode refuses).

PARAMS = {
    "rig": None,        # the armature; None = the first one in the scene
    "quality": 8,       # the simulation's steps a frame
    "settle": 45,       # frames the simulated cloth is left to settle on the body as it was made, before anything moves
    "preroll": 20,      # frames the body then takes to come into the motion's first pose
    "rounds": 3,        # a looping motion is played this many times (2 at least); the last round is faded into the one before
    "mass": None,       # how heavy the cloth is, kg a point. None = each garment's own (cloth.py: "kinds")
    "bend": None,       # how it resists folding (0.5 = silk, 4 = canvas). None = each garment's own
    "damp": None,       # how much the air slows it. None = each garment's own
    "drape": None,      # how far the garment itself takes the hang of the simulated cloth (1), or keeps the shape it was made in until something moves it (0). None = each garment's own
    "shape": None,      # how hard it is held to the shape it was made in, riding the bone it hangs from (0 = a rag ... 1 = it cannot move). None = each garment's own
    "friction": 5.0,    # how much the body's skin and the other clothes grip the simulated cloth (Blender's own number: 0 = ice, 80 = most). At 10 a hand at her side carried a flounce up with it and it stayed there
    "inner": 0.03,      # cloth found this far inside the body (a share of the height) is still pushed back out of it
    "stretch": 15.0,    # how stiffly the simulated cloth resists being stretched along itself
    "squash": 5.0,      # ... and being squashed along itself: little, so it folds and bunches where a coarse sheet would stand like paper
    "wind": 60.0,       # the air of moving: a wind from the front this strong for each metre a second the motion says it travels (a walk or a run, played on the spot); 0 = none
    "legs": True,       # the body is in the cloth's way: the simulated cloth collides with it, and the garment's own points are kept out of the parts of it their kind names
    "floor": True,      # ... and so is the floor
    "wrap": True,       # a point of the garment found in a limb is put out on the side of it the simulated cloth is on, not the nearest
    "clearance": 0.01,  # how far the cloth keeps off the skin, as a share of the height (0.01: 17 mm on a 1.7 m body)
    "clear_rounds": 4,  # how many times a frame's patches are moved out of the body once the cloth is carried onto the bones
    "smooth": 1,        # how many times each turn and move is eased with the frames either side (0 = not at all)
    "check": True,      # play the result back and measure it
}

import bpy
import bmesh
import json
import math
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

FABRIC = 3  # which way of moving cloth this is, written into the rig's note with every bake (1: weights on strings, before this file simulated; 2: simulated, but light cloth that stayed up where it was flung; scripts/fabric_survey.py lists clips baked by an older one)
# The parts of the body a garment can be kept out of (cloth.py: a kind's "collide"), and the bones of each.
BODY = {"legs": ("thigh_l", "thigh_r", "shin_l", "shin_r"),
        "arms": ("upper_arm_l", "upper_arm_r", "forearm_l", "forearm_r", "hand_l", "hand_r"),
        "trunk": ("hips", "spine", "chest"),
        "head": ("neck", "head")}
SKIRT_FROM = ("hips", "spine")  # chains that hang from these hang over the legs (a skirt, a tunic, a coat's tails); a hood's hang from the head
# A garment whose rig says nothing of its kind (a file made before cloth.py wrote one): plain cloth.
PLAIN = {"mass": 2.0, "bend": 0.3, "shape": 0.0, "damp": 0.2, "drape": 1.0, "swing": 170.0, "reach": 2.0, "floor": True}
BINS = 8          # a rod's thickness is measured at this many places along it...
AROUND = 12       # ... and this many ways round it
SWUNG = 0.15      # a point of a garment is its loose cloth when the chains pull on it this much; less, and the body carries it (a waistband)
PIN_UNDER = 0.3   # a point the chains pull on less than this is held to the body in the simulation, the more the less they pull
LEAN = 0.08       # a bone's patch of the simulated cloth is carried a little as the bone above it is, this share of its whole count (see rigid)
SAME_SIDE = 0.2   # a point is on another side of a rod when the way out to it and the way out to where it should be are further apart than this (a cosine)


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

# How each kind of cloth hangs, for a rig whose description was written before fabric step 3 (it says 0.15 kg a point and
# nothing of "drape"): the same numbers as cloth.py's kinds, which a new rig carries itself (scripts/test_fabric.py holds
# the two tables to each other). So a character rigged long ago hangs right with no rigging again.
HANG = {
    "skirt": {"mass": 2.0, "bend": 0.3, "drape": 1.0}, "short skirt": {"mass": 1.6, "bend": 0.5, "drape": 1.0},
    "apron": {"mass": 1.3, "bend": 0.3, "drape": 1.0}, "tails": {"mass": 1.6, "bend": 0.5, "drape": 1.0},
    "cape": {"mass": 1.6, "bend": 0.2, "drape": 1.0}, "hood": {"mass": 1.3, "bend": 2.0, "drape": 0.3},
    "sleeve": {"mass": 1.3, "bend": 0.3, "drape": 1.0}, "sash": {"mass": 1.0, "bend": 0.1, "drape": 1.0},
}

def about_of(garment, parent, params):
    """How a chain's garment is and what it is kept out of: cloth.py's description of it, or (for a rig that has
    none) plain cloth, kept out of the legs, arms and trunk if it hangs over the legs and out of the trunk and
    arms if it hangs from higher. A number in `params` is for every garment."""
    out = dict(PLAIN, collide=["legs", "arms", "trunk"] if parent in SKIRT_FROM else ["trunk", "arms"])
    out.update({k: v for k, v in (garment or {}).items() if k in out and v is not None})
    if garment and "drape" not in garment and garment.get("kind") in HANG:  # written before cloth was made heavy: its kind's weight as it is now
        out.update(HANG[garment["kind"]])
    for k in ("mass", "bend", "damp", "shape", "drape"):
        if params.get(k) is not None:
            out[k] = params[k]
    return out

def rods_for(collide, parent):
    """The bones a garment is kept out of: those of the parts its kind names, never the bone it hangs from, and
    for a sleeve never its own arm."""
    out = []
    for part in collide:
        for bone in BODY.get(part, ()):
            own_arm = parent.split("_")[0] in ("shoulder", "upper", "forearm", "hand") and bone[-2:] == parent[-2:] and bone in BODY["arms"]
            if bone != parent and not own_arm:
                out.append(bone)
    return out

def thick_at(profile, t, way, x_axis, z_axis):
    """Each rod's radius at `t` along it (0 at its head, 1 at its tail) the way `way` out of it. profile: [rods,
    BINS, AROUND], its thickness at BINS places along it and AROUND ways round it (in its bone's x and z): a
    thigh is wider front to back than side to side, and a shin has its calf behind. t: [points, rods]; way: unit,
    [points, rods, 3]; x_axis, z_axis: [rods, 3]. -> [points, rods]."""
    count, steps, around = profile.shape
    at = np.clip(t, 0.0, 1.0) * steps - 0.5
    lo = np.clip(np.floor(at).astype(int), 0, steps - 1)
    hi = np.clip(lo + 1, 0, steps - 1)
    f = np.clip(at - lo, 0.0, 1.0)
    turn = (np.arctan2((way * z_axis[None]).sum(axis=2), (way * x_axis[None]).sum(axis=2)) % (2.0 * math.pi)) / (2.0 * math.pi) * around
    a0 = np.floor(turn).astype(int) % around
    a1 = (a0 + 1) % around
    g = turn - np.floor(turn)
    rod = np.arange(count)[None, :]
    ring = lambda s: profile[rod, s, a0] * (1.0 - g) + profile[rod, s, a1] * g
    return ring(lo) * (1.0 - f) + ring(hi) * f

def local_in(points, rods):
    """Each point in each rod's own frame: [points, rods, 3] = (across it by its bone's x, along it from its head,
    across it by its bone's z), in metres."""
    a, b, _, x_axis, z_axis = rods
    ab = b - a
    long = np.sqrt(np.maximum((ab * ab).sum(axis=1), 1e-12))
    rel = points[:, None, :] - a[None]
    return np.stack([(rel * x_axis[None]).sum(axis=2), (rel * (ab / long[:, None])[None]).sum(axis=2), (rel * z_axis[None]).sum(axis=2)], axis=2)

def in_rods(points, rods, allow, side=None):
    """How far each point is inside each rod past what it may be: [points, rods] (m, negative = clear), and for each
    point and rod the move that takes it out [points, rods, 3]. rods: (heads [rods, 3], tails [rods, 3], profile
    [rods, BINS, AROUND], x axes [rods, 3], z axes [rods, 3]); allow: [points, rods], how far in each may stay.

    Cloth belongs on one side of a limb. `side` (local_in, [points, rods, 3]) is where each point should be, in
    each rod's own frame: where the simulated cloth has it. If the straight way from there to where the point is
    passes through the rod, and the point is on another side of the rod's line, the limb is between them: the
    point is put at the rod's skin on the side it should be, not pushed out the nearest way (which would leave a
    knee outside a skirt, or a hand inside it)."""
    a, b, profile, x_axis, z_axis = rods
    ab = b - a
    sq = np.maximum((ab * ab).sum(axis=1), 1e-12)
    rel = points[:, None, :] - a[None]
    t = np.clip((rel * ab[None]).sum(axis=2) / sq[None], 0.0, 1.0)
    on = a[None] + t[:, :, None] * ab[None]
    away = points[:, None, :] - on
    far = np.linalg.norm(away, axis=2)
    way = away / np.maximum(far, 1e-9)[:, :, None]
    reach = thick_at(profile, t, way, x_axis, z_axis) - allow
    through = np.zeros(far.shape, dtype=bool)
    if side is not None:
        now = local_in(points, rods)
        p0, p1 = side[:, :, [0, 2]], now[:, :, [0, 2]]
        d = p1 - p0
        s = np.clip(-(p0 * d).sum(axis=2) / np.maximum((d * d).sum(axis=2), 1e-12), 0.0, 1.0)
        gap = np.linalg.norm(p0 + s[:, :, None] * d, axis=2)  # the nearest the way between them comes to the rod's line
        along = (side[:, :, 1] + s * (now[:, :, 1] - side[:, :, 1])) / np.sqrt(sq)[None]
        r0, r1 = np.linalg.norm(p0, axis=2), np.linalg.norm(p1, axis=2)
        side0, side1 = p0 / np.maximum(r0, 1e-9)[:, :, None], p1 / np.maximum(r1, 1e-9)[:, :, None]
        way0 = side0[:, :, 0:1] * x_axis[None] + side0[:, :, 1:2] * z_axis[None]
        thick0 = thick_at(profile, along, way0, x_axis, z_axis) - allow
        through = (gap < thick0) & ((side0 * side1).sum(axis=2) < SAME_SIDE) & (along > -0.15) & (along < 1.15) & (r0 > 1e-6) & (allow < 1e8)
        way = np.where(through[:, :, None], way0, way)
        reach = np.where(through, thick_at(profile, t, way, x_axis, z_axis) - allow, reach)
    target = on + way * reach[:, :, None]
    move = target - points[:, None, :]
    over = np.where(through | (far < reach), np.linalg.norm(move, axis=2), reach - far)
    over[(far < 1e-6) & ~through] = -1.0  # on the rod's very line there is no way out
    return over, move

def rigid(a, b, w, about=None, go_with=None):
    """The turn and the move (4x4) that best carry points `a` onto `b`, each counted by `w`. A patch of a few
    points in a row says nothing of the turn about that row, and one of two or three says little at all: so a
    little is always counted (LEAN of the whole) for going as `go_with` goes (4x4: how the bone above was
    carried), by four points about `about` (the bone's own head) and a hand's breadth along each of its axes."""
    if go_with is not None:
        mine = about[None, :] + np.vstack([np.zeros(3), 0.1 * np.eye(3)])
        a, b = np.vstack([a, mine]), np.vstack([b, mine @ go_with[:3, :3].T + go_with[:3, 3]])
        w = np.concatenate([w, np.full(4, LEAN * w.sum() / 4.0)])
    w = w / w.sum()
    a_mid, b_mid = (a * w[:, None]).sum(axis=0), (b * w[:, None]).sum(axis=0)
    u, _, vt = np.linalg.svd(((a - a_mid) * w[:, None]).T @ (b - b_mid))
    turn = vt.T @ np.diag([1.0, 1.0, float(np.sign(np.linalg.det(vt.T @ u.T)) or 1.0)]) @ u.T
    out = np.eye(4)
    out[:3, :3], out[:3, 3] = turn, b_mid - turn @ a_mid
    return out


scene = bpy.context.scene
rig = bpy.data.objects.get(PARAMS["rig"]) if PARAMS["rig"] else None
if rig is None:
    rigs = [o for o in scene.objects if o.type == "ARMATURE"]
    if not rigs:
        raise ValueError("no skeleton in the scene: run rig.py first")
    rig = rigs[0]
told = json.loads(rig.get("forge_cloth", "{}"))
chains = told.get("chains", [])
chains = [c for c in chains if all(name in rig.data.bones for name in c["bones"] + [c["parent"]])]
garments = told.get("garments", [])
action = rig.animation_data.action if rig.animation_data else None
if action is None:
    raise ValueError("the rig has no baked motion: run animate.py first")
about = json.loads(action.get("forge_motion", "{}"))
frames = int(about.get("frames") or round(action.frame_range[1]))
loops = bool(about.get("loop", False))
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
        c["local"] = [np.array((rest[c["bones"][i - 1] if i else c["parent"]]).inverted() @ rest[name]) for i, name in enumerate(c["bones"])]
        c["about"] = about_of(garments[c["garment"]] if isinstance(c.get("garment"), int) and c["garment"] < len(garments) else None, c["parent"], PARAMS)
    up = -np.array((rig.matrix_world.to_3x3().inverted() @ Vector((0, 0, -1))).normalized())
    floor_at = np.array(rig.matrix_world.inverted() @ Vector((0.0, 0.0, measure.get("floor", 0.0))))
    lift = 0.006 * tall  # how far off the floor the cloth keeps (1 cm on a 1.7 m body)
    bone_list = [(k, i, name) for k, c in enumerate(chains) for i, name in enumerate(c["bones"])]  # every chain bone, each chain's from its top down
    bone_at = {name: b for b, (_, _, name) in enumerate(bone_list)}
    chain_rest_back = np.array([np.array(rest[name].inverted()) for _, _, name in bone_list]).reshape(-1, 4, 4)

    # ---- the garments: the chains of one piece of gear that hang from one bone ----
    groups = {}
    for k, c in enumerate(chains):
        groups.setdefault((c.get("gear"), c["parent"]), []).append(k)
    group_of = {k: g for g, members in enumerate(groups.values()) for k in members}
    group_about = [chains[members[0]]["about"] for members in groups.values()]
    group_parent = [parent for (_, parent) in groups]

    # ---- a rod round each part of the body some garment is kept out of, as thick as the body is there ----
    # From the bone's line out to the skin, at BINS places along it and AROUND ways round it, on the body as it was
    # made: rays, so a thigh is as wide as it is each way and a shin has its calf. A ray that finds no skin of its own
    # near by (a hole, the other leg, an arm held out from a chest) takes the thickness of the rest of that ring.
    wanted = [rods_for(g["collide"], parent) if PARAMS["legs"] else [] for g, parent in zip(group_about, group_parent)]
    rod_names, profiles = [], []
    flesh = [o for o in scene.objects if o.type == "MESH" and o.find_armature() == rig and o.get("forge") != "gear"]
    if any(wanted) and flesh:
        world_back = rig.matrix_world.inverted()
        points, faces, start = [], [], 0
        for obj in flesh:
            place = world_back @ obj.matrix_world
            points += [place @ v.co for v in obj.data.vertices]
            faces += [[start + i for i in poly.vertices] for poly in obj.data.polygons]
            start += len(obj.data.vertices)
        skin = BVHTree.FromPolygons(points, faces)
        for name in [n for part in BODY.values() for n in part if any(n in w for w in wanted)]:
            if name not in rest:
                continue
            a, b = np.array(rest[name].translation), np.array(rest[name] @ Vector((0, span[name], 0)))
            x_axis, z_axis = np.array(rest[name].to_3x3().col[0].normalized()), np.array(rest[name].to_3x3().col[2].normalized())
            reach = (0.2 if name in BODY["trunk"] or name in BODY["head"] else 0.12) * tall
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
            rod_names.append(name)
            profiles.append(profile + PARAMS["clearance"] * tall)  # and the cloth's own thickness, and a little room
    profiles = np.array(profiles).reshape(-1, BINS, AROUND)
    leg_rods = np.array([n in BODY["legs"] for n in rod_names], dtype=bool)
    first_rods = np.array([n not in BODY["arms"] for n in rod_names], dtype=bool)  # where a leg (or the trunk) and an arm both want a point, the leg has it
    kept_from = np.array([[n in w for n in rod_names] for w in wanted], dtype=bool).reshape(len(wanted), len(rod_names))  # [garments, rods]

    def rods_of(frame_of):
        """The rods as the bones stand: `frame_of(name)` -> (head, tail, x axis, z axis)."""
        got = [frame_of(n) for n in rod_names]
        return (np.array([g[0] for g in got]).reshape(-1, 3), np.array([g[1] for g in got]).reshape(-1, 3), profiles,
                np.array([g[2] for g in got]).reshape(-1, 3), np.array([g[3] for g in got]).reshape(-1, 3))
    rest_rods = rods_of(lambda n: (np.array(rest[n].translation), np.array(rest[n] @ Vector((0, span[n], 0))),
                                   np.array(rest[n].to_3x3().col[0].normalized()), np.array(rest[n].to_3x3().col[2].normalized())))
    def rods_now(pose):
        return rods_of(lambda n: (np.array(pose[n].head), np.array(pose[n].tail), np.array(pose[n].matrix.to_3x3().col[0].normalized()),
                                  np.array(pose[n].matrix.to_3x3().col[2].normalized())))
    result["rods_cm"] = {name: [[round(100 * float(r), 1) for r in (ring.min(), ring.max())] for ring in profile] for name, profile in zip(rod_names, profiles)}
    result["garments"] = [{"gear": gear_name, "hangs_from": parent, "chains": len(members), "kept_out_of": w,
                           "kind": (garments[chains[members[0]]["garment"]].get("kind") if isinstance(chains[members[0]].get("garment"), int) and chains[members[0]]["garment"] < len(garments) else None),
                           "mass": g["mass"], "bend": g["bend"], "damp": g["damp"], "shape": g["shape"], "swing": g["swing"], "reach": g["reach"]}
                          for ((gear_name, parent), members), g, w in zip(groups.items(), group_about, wanted)]

    # ---- the garments' own points: every point the chains pull on (SWUNG of its pull or more), and how it is skinned
    # (its pull shared between chain bones and, near the waist or where it rested on a thigh, the body's bones) ----
    gear = [o for o in scene.objects if o.type == "MESH" and o.find_armature() == rig and o.get("forge") == "gear"]
    body_bones, cloth_at, cloth_pulls, cloth_shares, cloth_owner, cloth_from, cloth_main, cloth_grip = [], [], [], [], [], [], [], []
    for obj in gear:
        names = {g.index: g.name for g in obj.vertex_groups}
        place = rig.matrix_world.inverted() @ obj.matrix_world
        for v in obj.data.vertices:
            pulls = sorted(((g.weight, names[g.group]) for g in v.groups if g.weight > 1e-4 and names.get(g.group) in rest), reverse=True)[:4]
            by_chains = [(w, n) for w, n in pulls if n in bone_at]
            swung = sum(w for w, _ in by_chains)
            total = sum(w for w, _ in pulls)
            if not by_chains or swung < SWUNG * total:
                continue  # a point the body carries (a waistband): it goes where the body goes
            main = bone_at[by_chains[0][1]]
            index, share = [], []
            for w, n in pulls:
                if n not in bone_at and n not in body_bones:
                    body_bones.append(n)
                index.append(bone_at[n] if n in bone_at else -1 - body_bones.index(n))
                share.append(w / total)
            while len(index) < 4:
                index.append(main)
                share.append(0.0)
            cloth_at.append(np.array(place @ v.co))
            cloth_pulls.append(index)
            cloth_shares.append(share)
            cloth_owner.append(group_of[bone_list[main][0]])
            cloth_from.append((obj.name, v.index))
            cloth_main.append(main)  # the chain bone that holds it most, and by how much
            cloth_grip.append(by_chains[0][0] / total)
    cloth_at, cloth_shares = np.array(cloth_at).reshape(-1, 3), np.array(cloth_shares).reshape(-1, 4)
    cloth_pulls = np.array(cloth_pulls, dtype=np.int64).reshape(-1, 4)
    cloth_pulls = np.where(cloth_pulls < 0, len(bone_list) + (-1 - cloth_pulls), cloth_pulls)  # chain bones first, then the body's
    cloth_owner, cloth_main, cloth_grip = np.array(cloth_owner, dtype=np.int64), np.array(cloth_main, dtype=np.int64), np.array(cloth_grip)
    cloth_floor = np.array([bool(group_about[g].get("floor", True)) for g in cloth_owner], dtype=bool)  # which points are kept off the floor (their garment's kind says)
    point_at = {source: at for at, source in enumerate(cloth_from)}
    cloth_faces = np.array([[point_at[(obj.name, i)] for i in (poly.vertices[0], poly.vertices[k], poly.vertices[k + 1])] for obj in gear for poly in obj.data.polygons
                            for k in range(1, len(poly.vertices) - 1) if all((obj.name, i) in point_at for i in poly.vertices)], dtype=np.int64).reshape(-1, 3)  # the faces whose corners are all such points
    body_rest_back = np.array([np.array(rest[n].inverted()) for n in body_bones]).reshape(-1, 4, 4)
    result["cloth_points"] = len(cloth_at)

    # A point that is inside a rod as the cloth was made (a waistband over the top of a thigh, a kilt resting on one)
    # may stay that far in. A garment is kept only from the rods its kind names: a hood never meets a shin.
    def allowed(points, owners):
        allow = np.zeros((len(points), len(rod_names)))
        if not rod_names or not len(points):
            return allow
        over, _ = in_rods(points, rest_rods, allow)
        allow = np.maximum(over, 0.0)
        allow[~kept_from[owners]] = 1e9
        return allow
    cloth_allow = allowed(cloth_at, cloth_owner)
    face_allow = allowed(cloth_at[cloth_faces].mean(axis=1), cloth_owner[cloth_faces[:, 0]]) if len(cloth_faces) else np.zeros((0, len(rod_names)))

    # ---- the body's motion, frame by frame: where each chain's parent is, where the rods are, and the body bones the cloth also hangs on ----
    taken = []
    for f in range(frames + 1):
        scene.frame_set(f)
        pose = rig.pose.bones
        taken.append({"parent": {c["parent"]: np.array(pose[c["parent"]].matrix) for c in chains}, "rods": rods_now(pose), "body": [np.array(pose[n].matrix) for n in body_bones]})

    def simulated(rounds_played):
        """Blender's cloth simulation of every garment the chains pull on, over the motion. -> (how each chain
        bone's patch of the simulated cloth has moved from where it settled as made, in the rig's frame: {bone:
        [kept + 1 of 4x4]}; where the simulated cloth has each of the garments' own points: [kept + 1, points, 3]),
        over the `kept` frames up to the end: the motion, or a loop's last two rounds. ({}, None) if there is
        nothing to simulate."""
        parent_of = {name: c["parent"] for c in chains for name in c["bones"]}
        how_of = {name: c["about"] for c in chains for name in c["bones"]}
        cloths = [o for o in gear if any(name == o.name for name, _ in cloth_from)]
        if not cloths:
            return {}, None
        others = [o for o in scene.objects if o.type == "MESH" and o.find_armature() == rig and o not in cloths]
        hold, blend = int(PARAMS["settle"]), int(PARAMS["preroll"])
        last = frames * rounds_played
        kept = frames * min(2, rounds_played) if rounds_played > 1 else frames
        made, colliders, changed, moves = [], [], [], {}
        try:
            # The body as it was made, held while the cloth settles, then turned into the motion's first pose: each
            # turn keyed at rest twice before the start. (Where the body is, is left as the first frame has it.)
            by_path = {}
            for curve in curves_of(action):
                by_path.setdefault(curve.data_path, {})[curve.array_index] = curve
            for path, group in by_path.items():
                if 'pose.bones["cloth_' in path:
                    continue
                turns = path.endswith(("rotation_quaternion", "rotation_euler"))
                if not turns and not (rounds_played > 1 and path.endswith("location")):
                    continue
                quat = path.endswith("rotation_quaternion")
                sign = -1.0 if quat and 0 in group and group[0].evaluate(0) < 0 else 1.0
                for index, curve in group.items():
                    if rounds_played > 1:  # a loop is played round more than once: its keys again, a round later each time
                        keys = [(key.co.x, key.co.y) for key in curve.keyframe_points if 0.5 < key.co.x <= frames + 0.5]
                        for again in range(1, rounds_played):
                            for x, y in keys:
                                curve.keyframe_points.insert(x + again * frames, y, options={"FAST"})
                    if turns:
                        for f in (-hold - blend, -blend):
                            curve.keyframe_points.insert(f, sign if quat and index == 0 else 0.0, options={"FAST"})
                    curve.update()
                    changed.append(curve)
            for obj in cloths:
                sim = obj.copy()
                sim.data = obj.data.copy()
                sim.name = "simulated: " + obj.name
                scene.collection.objects.link(sim)
                bm = bmesh.new()
                bm.from_mesh(sim.data)
                bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
                bm.to_mesh(sim.data)
                bm.free()
                names = {g.index: g.name for g in sim.vertex_groups}
                pin = sim.vertex_groups.new(name="forge_pin")
                patches, to_body, mass, bend, damp, total_w = {}, {}, 0.0, 0.0, 0.0, 0.0
                for v in sim.data.vertices:
                    swung = sum(g.weight for g in v.groups if names[g.group] in parent_of)
                    total = sum(g.weight for g in v.groups) or 1.0
                    shaped = 0.0
                    for g in v.groups:
                        n = names[g.group]
                        if n in parent_of and g.weight > 0:
                            # what a chain held goes to the bone it hangs from: where it is pinned, the cloth rides the body
                            to_body[(v.index, parent_of[n])] = to_body.get((v.index, parent_of[n]), 0.0) + g.weight
                            mass, bend, damp, total_w = mass + g.weight * how_of[n]["mass"], bend + g.weight * how_of[n]["bend"], damp + g.weight * how_of[n]["damp"], total_w + g.weight
                            shaped = max(shaped, how_of[n]["shape"])
                            if g.weight > 0.02:
                                patches.setdefault(n, []).append((v.index, g.weight))
                    held_by_body = max(0.0, 1.0 - (swung / total) / PIN_UNDER)
                    pin.add([v.index], max(held_by_body ** 2, shaped), "REPLACE")
                for g in [g for g in sim.vertex_groups if g.name in parent_of]:
                    sim.vertex_groups.remove(g)
                for (index, bone), w in to_body.items():
                    (sim.vertex_groups.get(bone) or sim.vertex_groups.new(name=bone)).add([index], w, "ADD")
                cloth = sim.modifiers.new("cloth", "CLOTH")
                how = cloth.settings
                how.quality = int(PARAMS["quality"])
                how.mass = mass / max(total_w, 1e-9)
                how.vertex_group_mass = "forge_pin"
                how.pin_stiffness = 1.0
                how.tension_stiffness = PARAMS["stretch"]
                how.compression_stiffness = PARAMS["squash"]
                how.shear_stiffness = 5.0
                how.bending_stiffness = bend / max(total_w, 1e-9)
                how.tension_damping = how.compression_damping = how.shear_damping = 5.0
                how.bending_damping = 0.5
                # Blender's cloth counts time in frames, not seconds: a sheet falls 4.4 m in its first second at 30 frames a second,
                # 2.8 m at 24 and 17.7 m at 60 (4.9 is right). Its weight is made up for, so cloth falls as fast at any frame rate.
                how.effector_weights.gravity = (31.56 / max(float(scene.render.fps) / scene.render.fps_base, 1.0)) ** 2
                how.air_damping = damp / max(total_w, 1e-9)  # (the air holds light cloth up: too much and a skirt a knee has thrown stays up like a parasol)
                cloth.collision_settings.use_collision = True
                cloth.collision_settings.collision_quality = 4
                cloth.collision_settings.distance_min = 0.7 * PARAMS["clearance"] * tall
                cloth.collision_settings.use_self_collision = False
                cloth.point_cache.frame_start, cloth.point_cache.frame_end = -hold - blend, last
                tree = KDTree(len(sim.data.vertices))
                for v in sim.data.vertices:
                    tree.insert(v.co, v.index)
                tree.balance()
                mine = [(at, index) for at, (name, index) in enumerate(cloth_from) if name == obj.name]
                made.append((sim, {n: (np.array([i for i, _ in vs], dtype=np.int64), np.array([w for _, w in vs])) for n, vs in patches.items()},
                             sorted({parent_of[n] for n in patches}), np.array([at for at, _ in mine], dtype=np.int64),
                             np.array([tree.find(obj.data.vertices[index].co)[1] for _, index in mine], dtype=np.int64)))
            for obj in others:  # the body's skin, and every other piece of clothing
                if PARAMS["legs"] and not any(m.type == "COLLISION" for m in obj.modifiers):
                    obj.modifiers.new("forge_collide", "COLLISION")
                    obj.collision.thickness_outer = 0.7 * PARAMS["clearance"] * tall
                    obj.collision.thickness_inner = PARAMS["inner"] * tall
                    obj.collision.cloth_friction = PARAMS["friction"]
                    colliders.append(obj)
            if PARAMS["floor"] and cloth_floor.any():
                mesh = bpy.data.meshes.new("forge_ground")
                z = measure.get("floor", 0.0)
                mesh.from_pydata([(-20, -20, z), (20, -20, z), (20, 20, z), (-20, 20, z)], [], [(0, 1, 2, 3)])
                ground = bpy.data.objects.new("forge_ground", mesh)
                scene.collection.objects.link(ground)
                ground.modifiers.new("forge_collide", "COLLISION")
                ground.collision.thickness_outer = lift
                colliders.append(ground)
            # A walk or a run is played on the spot, but the cloth should trail as if the ground went by: the air of
            # moving, a wind from the front as fast as the motion says it travels.
            speed = float(about.get("speed_m_s") or 0.0)
            if speed > 0.0 and PARAMS["wind"]:
                bpy.ops.object.effector_add(type="WIND")  # (an empty has no field of its own until it is made as one)
                air = bpy.context.view_layer.objects.active
                air.name = "forge_wind"
                air.field.strength = PARAMS["wind"] * speed
                air.field.flow = 0.0
                air.matrix_world = rig.matrix_world @ Matrix.Translation((0.0, -3.0, 0.6 * tall)) @ Matrix.Rotation(-math.pi / 2.0, 4, "X")  # (it blows along its z: turned to blow back, the way the character faces away from)
                colliders.append(air)
            back = rig.matrix_world.inverted()

            def shown(sim):
                graph = bpy.context.evaluated_depsgraph_get()
                bent = sim.evaluated_get(graph)
                mesh = bent.to_mesh()
                co = np.empty(len(mesh.vertices) * 3)
                mesh.vertices.foreach_get("co", co)
                bent.to_mesh_clear()
                m = np.array(back @ sim.matrix_world)
                return co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
            settled, made_at, sim_allow, sim_deep, sagged = {}, {}, {}, [], []
            sides = np.zeros((kept + 1, len(cloth_at), 3))
            for f in range(-hold - blend, last + 1):
                scene.frame_set(f)
                if f == -blend:  # settled on the body as made; brought back to where the body was made, if the first frame has put it somewhere else
                    for sim, patches, hung_from, _, _ in made:
                        home = np.linalg.inv(np.array(rig.pose.bones[hung_from[0]].matrix) @ np.linalg.inv(np.array(rest[hung_from[0]]))) if hung_from else np.eye(4)
                        settled[sim.name] = shown(sim) @ home[:3, :3].T + home[:3, 3]
                        m = np.array(back @ sim.matrix_world)
                        as_made = np.array([v.co for v in sim.data.vertices]) @ m[:3, :3].T + m[:3, 3]
                        loose = np.unique(np.concatenate([index for index, _ in patches.values()])) if patches else np.zeros(0, dtype=np.int64)
                        sagged.append(float(np.linalg.norm(settled[sim.name][loose] - as_made[loose], axis=1).mean()) if len(loose) else 0.0)
                        made_at[sim.name] = as_made
                if f < last - kept:
                    continue
                deep = 0.0
                for sim, patches, _, where_to, take in made:
                    now, was = shown(sim), settled[sim.name]
                    sides[f - (last - kept), where_to] = now[take]
                    for k, i, name in bone_list:  # (from the top of each chain down: a bone leans on how the one above it was carried)
                        if name not in patches:
                            continue
                        index, w = patches[name]
                        if i and chains[k]["bones"][i - 1] in moves:
                            above = moves[chains[k]["bones"][i - 1]][-1]
                        else:
                            above = np.array(rig.pose.bones[chains[k]["parent"]].matrix) @ np.linalg.inv(np.array(rest[chains[k]["parent"]]))
                        # carried from where the garment was made (it hangs as cloth of its weight hangs, standing still too) or from where
                        # the simulated cloth settled (it keeps its made shape until something moves it), as far between as its kind's "drape" says
                        start = was[index] + how_of[name]["drape"] * (made_at[sim.name][index] - was[index])
                        moves.setdefault(name, []).append(rigid(start, now[index], w, np.array(rest[name].translation), above))
                    if rod_names:  # how far the simulated cloth itself is in the body, past where it settled
                        loose = np.unique(np.concatenate([index for index, _ in patches.values()])) if patches else np.zeros(0, dtype=np.int64)
                        if sim.name not in sim_allow:
                            sim_allow[sim.name] = np.maximum(in_rods(was[loose], rest_rods, np.zeros((len(loose), len(rod_names))))[0], 0.0)
                        over = in_rods(now[loose], taken[(f - (last - kept)) % frames if kept > frames else f - (last - kept)]["rods"], sim_allow[sim.name])[0] - PARAMS["clearance"] * tall
                        deep = max(deep, float(over.max()) if over.size else 0.0)
                sim_deep.append(deep)
            result["simulated_cloth"] = {"deepest_in_the_body_cm": round(100 * max(sim_deep + [0.0]), 2), "frames_in_the_body": int(sum(d > 0.005 for d in sim_deep)),
                                         "settled_off_its_made_shape_cm": round(100 * max(sagged + [0.0]), 2), "frames_simulated": last + hold + blend + 1}
            return moves, sides
        finally:
            for sim, _, _, _, _ in made:
                mesh = sim.data
                bpy.data.objects.remove(sim, do_unlink=True)
                bpy.data.meshes.remove(mesh)
            for obj in colliders:
                if obj.name.startswith("forge_wind"):
                    bpy.data.objects.remove(obj, do_unlink=True)
                elif obj.name.startswith("forge_ground"):
                    mesh = obj.data
                    bpy.data.objects.remove(obj, do_unlink=True)
                    bpy.data.meshes.remove(mesh)
                else:
                    obj.modifiers.remove(obj.modifiers["forge_collide"])
            for curve in changed:
                for key in reversed(list(curve.keyframe_points)):
                    if key.co.x < -0.5 or key.co.x > frames + 0.5:
                        curve.keyframe_points.remove(key, fast=True)
                curve.update()
            scene.frame_set(0)

    def worn(poses, shot):
        """The garments' points with every chain bone where `poses` has it ([bones, 4, 4]), skinned as the mesh is."""
        moves = np.zeros((len(bone_list) + len(body_bones), 3, 4))
        moves[:len(bone_list)] = (poses @ chain_rest_back)[:, :3]
        if len(body_bones):
            moves[len(bone_list):] = (np.array(shot["body"]).reshape(-1, 4, 4) @ body_rest_back)[:, :3]
        out = np.zeros_like(cloth_at)
        for j in range(4):
            m = moves[cloth_pulls[:, j]]
            out += cloth_shares[:, j, None] * (np.einsum("nij,nj->ni", m[:, :, :3], cloth_at) + m[:, :, 3])
        return out

    def deepest_of(over):
        """Which rod each point is put out of: the one it is deepest in, a leg's or the trunk's before an arm's."""
        if not first_rods.any() or first_rods.all():
            return np.argmax(over, axis=1)
        first = np.where(first_rods[None, :], over, -1.0)
        best = np.argmax(first, axis=1)
        return np.where(first[np.arange(len(over)), best] > 1e-5, best, np.argmax(over, axis=1))

    def cleared(poses, shot, side):
        """Each bone's patch moved until the garments' own points, skinned as the mesh is, are out of the body and off
        the floor: a bone goes by what the points it holds most are short, least squares, a few times over. A point
        is put out on the side of a limb the simulated cloth has it (`side`), not the nearest."""
        should = local_in(side, shot["rods"]) if rod_names and PARAMS["wrap"] else None
        should_faces = local_in(side[cloth_faces].mean(axis=1), shot["rods"]) if rod_names and PARAMS["wrap"] and len(cloth_faces) else None
        for _ in range(int(PARAMS["clear_rounds"])):
            points = worn(poses, shot)
            want = np.zeros_like(points)
            if rod_names:
                over, move = in_rods(points, shot["rods"], cloth_allow, should)
                deepest = deepest_of(over)
                hit = over[np.arange(len(over)), deepest] > 1e-4
                want[hit] = move[hit, deepest[hit]]
                if len(cloth_faces):  # a thin limb goes between a coarse garment's points: its faces' middles are tried too, and move their corners
                    over, move = in_rods(points[cloth_faces].mean(axis=1), shot["rods"], face_allow, should_faces)
                    deepest = deepest_of(over)
                    hit = np.nonzero(over[np.arange(len(over)), deepest] > 1e-4)[0]
                    for corner in range(3):
                        at = cloth_faces[hit, corner]
                        longer = np.linalg.norm(move[hit, deepest[hit]], axis=1) > np.linalg.norm(want[at], axis=1)
                        want[at[longer]] = move[hit[longer], deepest[hit[longer]]]
            if PARAMS["floor"]:
                short = lift - (points + want - floor_at) @ up
                low = (short > 1e-5) & cloth_floor
                want[low] += np.outer(short[low], up)
            hit = np.abs(want).sum(axis=1) > 0
            if not hit.any():
                break
            push, weight = np.zeros((len(bone_list), 3)), np.zeros(len(bone_list))
            np.add.at(push, cloth_main[hit], want[hit] * cloth_grip[hit][:, None])
            np.add.at(weight, cloth_main[hit], cloth_grip[hit] ** 2)
            has = weight > 1e-9
            poses[has, :3, 3] += push[has] / weight[has][:, None]
        # Least squares leaves a patch's lowest point under the floor when the rest of it is clear, and cloth that hangs
        # to the floor has many such. So last, each bone is lifted by the most any point it mainly holds is short.
        for _ in range(2 if PARAMS["floor"] and cloth_floor.any() else 0):
            short = lift - (worn(poses, shot) - floor_at) @ up
            low = (short > 1e-5) & cloth_floor
            if not low.any():
                break
            most = np.zeros(len(bone_list))
            np.maximum.at(most, cloth_main[low], short[low] / np.maximum(cloth_grip[low], 0.3))
            poses[:, :3, 3] += np.outer(most, up)
        return poses

    def capped(basis, name):
        """A bone's turn and move (4x4, in its own axes) brought inside how far its garment may swing and slide."""
        how = chains[bone_list[bone_at[name]][0]]["about"]
        quat = Matrix(basis.tolist()).to_quaternion()
        angle = quat.angle if quat.angle <= math.pi else quat.angle - 2.0 * math.pi
        most = math.radians(how["swing"])
        if abs(angle) > most:
            quat = Quaternion(quat.axis, most if angle > 0 else -most)
        move = Vector(basis[:3, 3].tolist())
        far = how["reach"] * span[name]
        if move.length > far:
            move *= far / move.length
        return held(quat.to_matrix(), limits.get(name) or free), move

    # ---- simulate; then each frame's bones: where each one's patch of the simulated cloth is, kept clear, inside what its kind may do ----
    patched, sides = simulated(max(2, int(PARAMS["rounds"])) if loops else 1) if len(cloth_at) else ({}, None)
    result["simulated"] = bool(patched)
    two_rounds = bool(patched) and loops
    played = {name: [] for _, _, name in bone_list}  # {bone: [each frame's (turn, move), in the bone's own axes]}
    for f in range((2 * frames if two_rounds else frames) + 1):
        shot = taken[f % frames if two_rounds else f]
        poses = np.zeros((len(bone_list), 4, 4))
        for b, (k, i, name) in enumerate(bone_list):
            above = poses[b - 1] if i else shot["parent"][chains[k]["parent"]]
            # a bone with no cloth of its own to say goes with the bone above it
            poses[b] = patched[name][f] @ np.array(rest[name]) if name in patched else above @ chains[k]["local"][i]
        if patched:
            poses = cleared(poses, shot, sides[f])
        real = np.zeros_like(poses)
        for b, (k, i, name) in enumerate(bone_list):
            frame = (real[b - 1] if i else shot["parent"][chains[k]["parent"]]) @ chains[k]["local"][i]
            turn, move = capped(np.linalg.inv(frame) @ poses[b], name)
            basis = np.eye(4)
            basis[:3, :3], basis[:3, 3] = np.array(turn), np.array(move)
            real[b] = frame @ basis
            played[name].append((turn.to_quaternion(), move))
    # A loop's cloth never comes round to quite where it was (it flutters; a second round is not the first). So the
    # last round is faded into the round before it: frame f is the last round's, less and less, and the one before's,
    # more and more. Its first frame is the last round's first and its last is the round before's last, which are
    # the same moment: the loop closes on itself, and every frame is between two things the cloth really did.
    apart = 0.0
    if two_rounds:
        for name, rows in played.items():
            faded = []
            for f in range(frames + 1):
                (q_old, m_old), (q_new, m_new) = rows[f], rows[frames + f]
                apart = max(apart, math.degrees(q_old.rotation_difference(q_new).angle if q_old.rotation_difference(q_new).angle <= math.pi else 2.0 * math.pi - q_old.rotation_difference(q_new).angle))
                faded.append((q_new.slerp(q_old, f / frames), m_new.lerp(m_old, f / frames)))
            rows[:] = faded
    result["rounds_apart_deg"] = round(apart, 1)

    # ---- the simulation's small shakes: each turn and move is eased with the frames either side (a loop's ends are each other's neighbours) ----
    for name, rows in played.items():
        for f in range(1, len(rows)):
            if rows[f][0].dot(rows[f - 1][0]) < 0:
                rows[f][0].negate()
        for _ in range(int(PARAMS["smooth"])):
            eased = []
            for f in range(len(rows)):
                if not loops and f in (0, len(rows) - 1):
                    eased.append(rows[f])
                    continue
                # (a loop's last frame is its first again: the frame before its first is the one before its last)
                near = [rows[(f + d) % frames] if loops else rows[f + d] for d in (-1, 0, 1)]
                quats = [q.copy() for q, _ in near]
                for q in (quats[0], quats[2]):
                    if q.dot(quats[1]) < 0:
                        q.negate()
                eased.append((Quaternion([0.25 * a + 0.5 * b + 0.25 * e for a, b, e in zip(*quats)]).normalized(), 0.25 * near[0][1] + 0.5 * near[1][1] + 0.25 * near[2][1]))
            rows[:] = eased

    # ---- easing a frame with its neighbours can put a hem that lies on the floor back under it: each bone is lifted once more by the most any point it mainly holds is short ----
    if PARAMS["floor"] and patched and cloth_floor.any():
        for f in range(frames + 1):
            shot = taken[f % frames if loops else f]
            for _ in range(2):
                real, axes = np.zeros((len(bone_list), 4, 4)), []
                for b, (k, i, name) in enumerate(bone_list):
                    frame = (real[b - 1] if i else shot["parent"][chains[k]["parent"]]) @ chains[k]["local"][i]
                    basis = np.eye(4)
                    basis[:3, :3], basis[:3, 3] = np.array(played[name][f][0].to_matrix()), np.array(played[name][f][1])
                    real[b] = frame @ basis
                    axes.append(frame[:3, :3])
                short = lift - (worn(real, shot) - floor_at) @ up
                low = (short > 1e-5) & cloth_floor
                if not low.any():
                    break
                most, given = np.zeros(len(bone_list)), np.zeros(len(bone_list))
                np.maximum.at(most, cloth_main[low], short[low] / np.maximum(cloth_grip[low], 0.3))
                for b, (k, i, name) in enumerate(bone_list):
                    carried = given[b - 1] if i else 0.0  # a bone rides the one above it, and is lifted with it
                    given[b] = max(most[b], carried)
                    if most[b] > carried:
                        turn, move = played[name][f]
                        played[name][f] = (turn, move + Vector((axes[b].T @ (up * (most[b] - carried))).tolist()))

    # ---- key it; a loop's last frame is its first, and the little left over is eased out across the round ----
    worst_seam = 0.0
    for name, rows in played.items():
        bone = rig.pose.bones[name]
        bone.rotation_mode = "QUATERNION"
        quats, shifts = [q.copy() for q, _ in rows], [m.copy() for _, m in rows]
        for f in range(1, len(quats)):
            if quats[f].dot(quats[f - 1]) < 0:
                quats[f].negate()
        if loops:
            left = [a - b for a, b in zip(quats[0], quats[frames])]  # what the end is short of the start
            worst_seam = max(worst_seam, math.degrees(quats[0].rotation_difference(quats[frames]).angle))
            for f in range(1, frames + 1):
                quats[f] = Quaternion([q + d * f / frames for q, d in zip(quats[f], left)]).normalized()
                if quats[f].dot(quats[f - 1]) < 0:
                    quats[f].negate()
            quats[frames] = quats[0].copy()
            gap = shifts[0] - shifts[frames]
            shifts = [m + gap * (f / frames) for f, m in enumerate(shifts)]
            shifts[frames] = shifts[0].copy()
        for f in range(frames + 1):
            bone.rotation_quaternion = quats[f]
            bone.location = shifts[f]
            bone.keyframe_insert("rotation_quaternion", frame=f, group=name)
            bone.keyframe_insert("location", frame=f, group=name)
    for curve in curves_of(action):
        if 'pose.bones["cloth_' in curve.data_path:
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"
    result["eased_at_the_seam_deg"] = round(worst_seam, 3)
    rig["forge_cloth"] = json.dumps(dict(told, chains=[{k: v for k, v in c.items() if k not in ("local", "about")} for c in told.get("chains", [])],
                                         swung={"fabric": FABRIC, "simulated": bool(patched), "action": action.name}))

    # ---- play it back and measure: the cloth itself, as Blender bends it with what was just keyed ----
    if PARAMS["check"]:
        outside, inside_cm, leg_cm, below_cm, seam, swing, slide, first_pose, lowest, highest = {}, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {}, {}, {}
        frames_in, frames_in_leg, where = 0, 0, None
        low = np.argsort(cloth_at @ up)[:max(1, len(cloth_at) // 4)] if len(cloth_at) else np.zeros(0, dtype=np.int64)  # the lowest quarter of the garments' points: the hems
        hem_off, hem_high = [], []  # how far the hems are from where the simulated cloth has them, and how far above
        floor_bones = {name for c in chains for name in c["bones"] if c["about"].get("floor", True)}
        on_floor = [o for o in gear if PARAMS["floor"] and any(g.group in {x.index for x in o.vertex_groups if x.name in floor_bones} and g.weight > 0.05
                                                             for v in o.data.vertices for g in v.groups)]
        mine = {}
        for at, (name, index) in enumerate(cloth_from):
            mine.setdefault(name, ([], []))
            mine[name][0].append(at)
            mine[name][1].append(index)
        back = np.array(rig.matrix_world.inverted())
        for f in range(frames + 1):
            scene.frame_set(f)
            pose = rig.pose.bones
            graph = bpy.context.evaluated_depsgraph_get()
            real = np.zeros_like(cloth_at)
            for obj in gear:
                if obj.name not in mine and obj not in on_floor:
                    continue
                bent = obj.evaluated_get(graph)
                mesh = bent.to_mesh()
                co = np.empty(len(mesh.vertices) * 3)
                mesh.vertices.foreach_get("co", co)
                bent.to_mesh_clear()
                m = np.array(obj.matrix_world)
                co = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
                if obj in on_floor:  # its lowest point against the floor
                    below_cm = max(below_cm, 100 * (measure.get("floor", 0.0) - float(co[:, 2].min())))
                if obj.name in mine:
                    real[mine[obj.name][0]] = co[mine[obj.name][1]] @ back[:3, :3].T + back[:3, 3]
            if sides is not None and len(low):
                gone = real[low] - sides[f + (frames if two_rounds and f < frames else 0)][low]
                hem_off.append(float(np.linalg.norm(gone, axis=1).mean()))
                hem_high.append(float((gone @ up).mean()))
            if rod_names and len(real):
                over, _ = in_rods(real, rods_now(pose), cloth_allow)
                over -= PARAMS["clearance"] * tall  # into the skin itself, not the room kept off it
                deepest = float(over.max())
                in_leg = float(over[:, leg_rods].max()) if leg_rods.any() else 0.0
                if 100 * deepest > inside_cm:
                    at, r = np.unravel_index(int(np.argmax(over)), over.shape)
                    where = {"frame": f, "rod": rod_names[r], "point": list(cloth_from[at])}
                inside_cm, leg_cm = max(inside_cm, 100 * deepest), max(leg_cm, 100 * in_leg)
                frames_in += deepest > 0.005
                frames_in_leg += in_leg > 0.005
            for c in chains:
                for i, name in enumerate(c["bones"]):
                    bone = pose[name]
                    e = bone.matrix_basis.to_3x3().to_euler("XYZ")
                    lim = limits.get(name)
                    if lim and any(not lim[2 * k] - 0.1 <= math.degrees(e[k]) <= lim[2 * k + 1] + 0.1 for k in range(3)):
                        outside[name] = outside.get(name, 0) + 1
                    swing = max(swing, math.degrees(bone.matrix_basis.to_quaternion().angle))
                    slide = max(slide, bone.location.length)
                    now = list(bone.rotation_quaternion) + list(bone.location)
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
            "deepest_in_the_body_cm": round(max(inside_cm, 0.0), 2), "frames_in_the_body": int(frames_in), "deepest_where": where,
            "deepest_in_a_leg_cm": round(max(leg_cm, 0.0), 2), "frames_in_a_leg": int(frames_in_leg),
            "hem_below_floor_cm": round(max(below_cm, 0.0), 2) if PARAMS["floor"] else None,
            "loop_seam": round(seam, 6), "most_swing_deg": round(swing, 1), "most_slide_cm": round(100 * slide, 1),
            "hem_travels_cm": round(100 * max([(highest[k] - lowest[k]).length for k in lowest] or [0.0]), 1),
            "hem_off_the_simulated_cloth_cm": [round(100 * float(np.mean(hem_off)), 1), round(100 * float(np.max(hem_off)), 1)] if hem_off else None,
            "hem_above_the_simulated_cloth_cm": [round(100 * float(np.mean(hem_high)), 1), round(100 * float(np.max(hem_high)), 1)] if hem_high else None,
        }
print("RESULT " + json.dumps(result))
