# Make a rigged character's clothes move with its body, and give loose cloth
# bones of its own to hang and swing from.
#
# Run it after drape.py and rig.py (drape.py leaves notes on the gear's points
# saying what is tight, what is loose and how far down a loose piece each
# point hangs; rig.py binds every mesh by its nearest bones). Two things
# happen here:
#
# 1. Clothes take the body's weights. Every point of a tight or loose piece
#    (and of a belt or band) is given the weights the body has at the nearest
#    spot under it, so cloth and skin bend as one and neither cuts through the
#    other. A point with no body close under it, or whose nearest body faces
#    the other way (the far side of an armpit), gets its weights from the cloth
#    around it instead: they are spread in from the points that did find the
#    body. Stiff pieces (a hat, a buckle, the foot of a boot) keep what rig.py
#    gave them; only a boot's shaft goes with the shin under it.
#
# 2. Loose cloth gets bones. Each loose piece that hangs (a kilt, a coat's
#    skirts, the back of a hood) gets a few short chains of bones from the line
#    it hangs from down to its hem, spaced around it ("cloth_<gear>_<chain>_
#    <bone>"), each chain a child of the body bone that part of the piece is
#    worn on (hips, head...). The hanging points are weighted to them, more
#    the lower they are and the further they stand off the body: where a
#    kilt's side rests on a thigh it stays with the thigh, and the panels
#    between swing. The bones are not joined end to end: each carries its own
#    patch of the cloth, and may slide as well as turn.
#    Nothing moves yet: swing.py, run after animate.py, makes them hang and
#    swing with the motion. The rig remembers to ask for it ("then" in
#    animate.py's result).
#
# 3. Each hanging piece is said to be a kind of garment, from where it hangs
#    and how (kind_of): a long skirt, a short one (a kilt, a tunic's hem), an
#    apron, a coat's tails, a cape, a hood, a sleeve, a sash, or a collar.
#    "kinds" below says what each kind is like: how many chains and bones it
#    gets, how stiff and heavy it is and how far it may swing, which parts of
#    the body it is kept out of, and how flat cards show it. That one
#    description is kept on the rig ("forge_cloth": its "garments" and
#    "chains"), goes into every .glb, and is all that swing.py, the cards
#    (scripts/impostor) and the judges (scripts/fabric_judge.py) read: nothing
#    downstream asks what a garment is called or who wears it. A collar is
#    too short to swing: it gets no chains, stays with the body, and is only
#    written down (the cards hold it back from the neck's turn).
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down.
# Prints RESULT {json}. A second or two. Safe-mode compatible.

PARAMS = {
    "rig": None,          # the armature rig.py made; None = the first one in the scene
    "weights": True,      # give clothes the body's weights
    "bones": True,        # give loose, hanging pieces bones of their own
    "chain_every": 0.16,  # one chain about every this share of the height around a piece (4 to 8 all the way round, 1 to 4 on a part of the way)
    "bone_long": 0.07,    # a chain's bones are about this share of the height long (1 to 3 bones)
    "grip_over": 0.6,     # how far down a hanging piece, in bone lengths, the chains take it over from the body (below this it is all theirs)
    "limits": [-180, 180, -180, 180, -180, 180],  # a cloth bone's joint limit, degrees: free. Cloth lies along a thigh raised past level and hangs straight down off a bowed back, and a limit that stops it short leaves the leg through it. How far each kind may swing and slide is its own "swing" and "reach", below
    # What each kind of garment is like. A kind is worked out from where a piece hangs and how (kind_of); to say
    # otherwise, "kind": {"<gear name>": "<kind>"}. For each:
    #   chains      [fewest, most] chains of bones; None = none at all (it stays with the body)
    #   every       one chain about every this share of the height round it
    #   bones       the most bones a chain has; "bone_long": about how long each is, as a share of the height
    #   centre      a chain at the very front and the very back (cloth folds between the legs there), not either side of them
    #   mass        how heavy the cloth is, kg a point of its mesh (swing.py's cloth simulation)
    #   bend        how it resists folding (0.5 = silk, 4 = canvas)
    #   damp        how much the air slows it (0.2 = a skirt that falls back at once; more, and a thrown skirt stays up like a parasol)
    #   shape       how hard it is held to the shape it was made in, riding the bone it hangs from (0 = a rag; 0.25 = a hood that keeps its form)
    #   swing       how far a bone may turn from how it was made, degrees; "reach": how far it may slide, in bone lengths
    #   collide     the parts of the body its own points are kept out of once it has moved: "legs", "arms", "trunk", "head"
    #   floor       kept off the floor
    #   card        how flat cards show it: "piece" = a card of its own and one skinned piece of the model moved by its
    #               chains (a dress); "rides" = it stays in the card of the bone it hangs from (a hood, on the head's);
    #               "held" = no chains, and the neck's piece gives "hold" of what the neck and head pull on it back to the chest
    "kinds": {
        "skirt":       {"chains": [8, 8], "every": 0.16, "bones": 4, "bone_long": 0.1, "centre": True, "mass": 0.15, "bend": 2.0, "damp": 0.2, "shape": 0.0,
                        "swing": 170, "reach": 2.0, "collide": ["legs", "arms", "trunk"], "floor": True, "card": "piece"},
        "short skirt": {"chains": [4, 8], "every": 0.16, "bones": 3, "bone_long": 0.07, "centre": False, "mass": 0.12, "bend": 3.0, "damp": 0.2, "shape": 0.0,
                        "swing": 150, "reach": 1.5, "collide": ["legs", "arms", "trunk"], "floor": True, "card": "piece"},
        "apron":       {"chains": [2, 4], "every": 0.1, "bones": 3, "bone_long": 0.07, "centre": False, "mass": 0.1, "bend": 2.0, "damp": 0.3, "shape": 0.0,
                        "swing": 150, "reach": 1.5, "collide": ["legs", "arms", "trunk"], "floor": True, "card": "piece"},
        "tails":       {"chains": [2, 4], "every": 0.1, "bones": 3, "bone_long": 0.07, "centre": False, "mass": 0.12, "bend": 3.0, "damp": 0.2, "shape": 0.0,
                        "swing": 150, "reach": 1.5, "collide": ["legs", "arms", "trunk"], "floor": True, "card": "piece"},
        "cape":        {"chains": [3, 5], "every": 0.12, "bones": 4, "bone_long": 0.1, "centre": False, "mass": 0.12, "bend": 1.0, "damp": 0.3, "shape": 0.0,
                        "swing": 170, "reach": 2.0, "collide": ["legs", "arms", "trunk"], "floor": True, "card": "piece"},
        "hood":        {"chains": [1, 4], "every": 0.16, "bones": 3, "bone_long": 0.07, "centre": False, "mass": 0.1, "bend": 4.0, "damp": 0.5, "shape": 0.25,
                        "swing": 80, "reach": 0.6, "collide": ["trunk", "arms"], "floor": False, "card": "rides"},
        "sleeve":      {"chains": [1, 2], "every": 0.16, "bones": 2, "bone_long": 0.07, "centre": False, "mass": 0.1, "bend": 1.5, "damp": 0.3, "shape": 0.05,
                        "swing": 100, "reach": 1.0, "collide": ["trunk", "legs"], "floor": False, "card": "rides"},
        "sash":        {"chains": [1, 1], "every": 0.16, "bones": 3, "bone_long": 0.07, "centre": False, "mass": 0.08, "bend": 0.5, "damp": 0.4, "shape": 0.0,
                        "swing": 170, "reach": 2.0, "collide": ["legs", "arms"], "floor": True, "card": "rides"},
        "collar":      {"chains": None, "card": "held", "hold": 0.5},
    },
    "kind": {},           # {"<gear name>": "<kind>"}: say what a piece is, where kind_of gets it wrong
}

import bpy
import json
import math
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
from mathutils.interpolate import poly_3d_calc


TRUNK = ("hips", "spine", "chest", "neck", "head")


def second(pair):
    return pair[1]

def note(obj, name):
    """One of drape.py's notes on a mesh's points, as a list; None if it was never draped."""
    held = obj.data.attributes.get(name)
    if held is None:
        return None
    values = [0.0 if name == "forge_hang" else 0] * len(obj.data.vertices)
    held.data.foreach_get("value", values)
    return values

def weights_of(obj):
    """Each point's weights as {bone name: weight}."""
    names = {g.index: g.name for g in obj.vertex_groups}
    return [{names[g.group]: g.weight for g in v.groups if g.weight > 1e-5} for v in obj.data.vertices]

def blend(parts):
    """Weights mixed together: [(weights, share)] -> one {bone: weight} adding up to 1, at most four bones."""
    out = {}
    for weights, share in parts:
        for name, w in weights.items():
            out[name] = out.get(name, 0.0) + w * share
    kept = sorted(out.items(), key=second, reverse=True)[:4]
    total = sum(w for name, w in kept)
    return {name: w / total for name, w in kept} if total > 1e-9 else {}

def slug_of(text):
    out = "".join(c if c.isalnum() else "_" for c in (text or "cloth").lower()).strip("_")
    while "__" in out:
        out = out.replace("__", "_")
    return out[:18] or "cloth"

def kind_of(anchor, around, facing, wide, drop, line):
    """What kind of garment a hanging piece is, from how it hangs alone (never its name, never who wears it).
    anchor: the bone its top is worn on; around: it goes all the way round; facing: which way an open piece
    faces from the middle of the body ("front", "back" or "side"); wide: how far round an open piece goes, drop:
    how far down it hangs, line: how high its top is, all three as shares of the body's height."""
    if anchor.split("_")[0] in ("shoulder", "upper", "forearm", "hand"):
        return "sleeve"
    if anchor in ("head", "neck"):
        return "collar" if drop < 0.06 else "hood"
    if drop < 0.06 and line > 0.68:
        return "collar"  # a neckline, a lapel: too short to swing
    if anchor == "chest" or line > 0.68:  # from the shoulders
        return "cape" if not around or drop < 0.3 else "skirt"  # (a robe goes all the way round, to the knee or lower: it is a skirt from the chest)
    if around:
        return "skirt" if drop >= 0.3 else "short skirt"
    if wide < 0.12:
        return "sash"
    return "apron" if facing == "front" else "tails"

def facing_of(angle):
    """Which way an angle round the body's middle is: the character faces -y."""
    return "front" if math.sin(angle) < -0.5 else "back" if math.sin(angle) > 0.5 else "side"

def turn_to(angle, start):
    """An angle brought to within half a turn of `start`."""
    while angle - start > math.pi:
        angle -= 2 * math.pi
    while angle - start < -math.pi:
        angle += 2 * math.pi
    return angle


scene = bpy.context.scene
rig = bpy.data.objects.get(PARAMS["rig"]) if PARAMS["rig"] else None
if rig is None:
    rigs = [o for o in scene.objects if o.type == "ARMATURE"]
    if not rigs:
        raise ValueError("no skeleton in the scene: run rig.py first")
    rig = rigs[0]
bound = [o for o in scene.objects if o.type == "MESH" and o.find_armature() == rig]
bodies = [o for o in bound if o.get("forge") == "body"]
gear = [o for o in bound if o.get("forge") == "gear" and note(o, "forge_fit") is not None]
if not bodies or not gear:
    raise ValueError("nothing to dress: this needs a \"body\" mesh and \"gear: ...\" meshes that drape.py has been over, all bound by rig.py")
known = json.loads(rig.get("forge_rig", "{}"))
tall = known.get("measure", {}).get("height") or max((o.matrix_world @ v.co).z for o in bodies for v in o.data.vertices)
floor_z = known.get("measure", {}).get("floor", 0.0)

# ---- the body: where it is, and what it weighs there ----
points, triangles, given, facing = [], [], [], []
for obj in bodies:
    start = len(points)
    points += [obj.matrix_world @ v.co for v in obj.data.vertices]
    given += weights_of(obj)
    turn = obj.matrix_world.to_3x3()
    for poly in obj.data.polygons:
        for i in range(1, len(poly.vertices) - 1):
            triangles.append((start + poly.vertices[0], start + poly.vertices[i], start + poly.vertices[i + 1]))
            facing.append(turn @ poly.normal)
body_tree = BVHTree.FromPolygons(points, triangles)

def same_place(points, within=1e-4):
    """Which place each point is, and how many places: points closer than `within` (m) are one place. A .glb
    splits a point wherever the texture layout has a seam, and the copies can come back a few hundredths of a
    millimetre apart. Rounded to a grid, a pair either side of a grid line would be two places, and a garment
    could come apart into scraps along a seam (Roosevelt's singlet did: two of them were then taken for stiff
    little pieces, and tore away from the rest in motion)."""
    tree = KDTree(len(points))
    for i, p in enumerate(points):
        tree.insert(p, i)
    tree.balance()
    place, count = [-1] * len(points), 0
    for i, p in enumerate(points):
        if place[i] >= 0:
            continue
        for co, j, d in tree.find_range(p, within):
            if place[j] < 0:
                place[j] = count
        place[i] = count
        count += 1
    return place, count

def body_weights(p):
    """The body's weights at the spot nearest `p`: (weights, how far, which way that spot faces)."""
    hit = body_tree.find_nearest(p)
    if hit[0] is None:
        return None, 1e9, None
    corners = triangles[hit[2]]
    shares = poly_3d_calc([points[i] for i in corners], hit[0])
    return blend([(given[i], max(s, 0.0)) for i, s in zip(corners, shares)]), hit[3], facing[hit[2]]

# ---- each gear mesh: its points gathered where they share a place, and what drape.py said of them ----
report, chains, new_bones, garments = [], [], [], []
dressed = {}
for obj in gear:
    world = [obj.matrix_world @ v.co for v in obj.data.vertices]
    fit, hang, island = note(obj, "forge_fit"), note(obj, "forge_hang"), note(obj, "forge_island")
    at, spot_of, spots = {}, [], []
    place = same_place(world)[0]
    for vi, p in enumerate(world):
        key = place[vi]
        if key not in at:
            at[key] = len(spots)
            spots.append({"p": p, "verts": [], "n": Vector(), "links": set(), "fit": fit[vi], "hang": hang[vi], "island": island[vi]})
        spot_of.append(at[key])
        spots[at[key]]["verts"].append(vi)
    turn = obj.matrix_world.to_3x3()
    for poly in obj.data.polygons:
        ring = [spot_of[vi] for vi in poly.vertices]
        for i, k in enumerate(ring):
            spots[k]["n"] += (turn @ poly.normal) * poly.area
            spots[k]["links"].add(ring[i - 1])
            spots[ring[i - 1]]["links"].add(k)
    was = weights_of(obj)
    found = inpainted = 0
    for spot in spots:
        spot["w"], spot["off"] = None, 1e9
        spot["was"] = blend([(was[vi], 1.0) for vi in spot["verts"]])
        shaft = any(bone.startswith("shin") for bone in spot["was"]) and not any(bone.startswith(("foot", "toe")) for bone in spot["was"])
        if not PARAMS["weights"] or (spot["fit"] == 3 and not shaft):
            spot["w"] = spot["was"]  # a stiff piece (a hat, a buckle, the foot of a boot) keeps what rig.py gave it; a boot's shaft goes with the shin
            spot["kept"] = True
            continue
        weights, far, way = body_weights(spot["p"])
        spot["off"] = far
        if weights and far < 0.05 * tall and (spot["n"].length < 1e-9 or way.dot(spot["n"]) > 0):
            spot["w"] = weights
            found += 1
    todo = [k for k, spot in enumerate(spots) if spot["w"] is None]
    for _ in range(80):  # spread in from the points that found the body, across the cloth
        fresh = {}
        for k in todo:
            near = [(spots[j]["w"] or spots[j].get("guess"), 1.0) for j in spots[k]["links"] if spots[j]["w"] or spots[j].get("guess")]
            if near:
                fresh[k] = blend(near)
        for k, weights in fresh.items():
            spots[k]["guess"] = weights
    for k in todo:
        spots[k]["w"] = spots[k].get("guess") or body_weights(spots[k]["p"])[0] or spots[k]["was"]
        inpainted += 1
    dressed[obj.name] = (obj, spots)
    report.append({"mesh": obj.name, "points": len(spots), "from_the_body_under_it": found, "spread_in_from_the_cloth_around": inpainted,
                   "kept_from_rig": sum(1 for s in spots if s.get("kept"))})

# ---- loose pieces that hang: chains of bones, from the line they hang from to the hem ----
if PARAMS["bones"]:
    for name in sorted(dressed):
        obj, spots = dressed[name]
        for number in sorted({s["island"] for s in spots if s["fit"] == 2 and s["hang"] > 0}):
            mine = [s for s in spots if s["island"] == number]
            hanging = [s for s in mine if s["hang"] > 0]
            top = [s for s in mine if s["hang"] <= 0.25] or mine
            line, drop = json.loads(obj.get("forge_hangs", "{}")).get(str(number), [max(s["p"].z for s in hanging), 0.0])
            if drop < 0.03 * tall:
                continue
            votes, arms = {}, {}
            for s in top:
                for bone, w in s["w"].items():
                    if bone in TRUNK:  # cloth hangs from the trunk, never from a leg: those swing under it
                        votes[bone] = votes.get(bone, 0.0) + w
                    elif bone.split("_")[0] in ("upper", "forearm"):
                        arms[bone] = arms.get(bone, 0.0) + w
            anchor = sorted(votes.items(), key=second)[-1][0] if votes else "hips"
            if arms and sum(arms.values()) > 3.0 * sum(votes.values()):  # ... or from an arm, when its whole top is worn on one (a loose sleeve)
                anchor = sorted(arms.items(), key=second)[-1][0]
            mid = sum((s["p"] for s in top), Vector()) / len(top)
            for s in hanging:
                s["angle"] = math.atan2(s["p"].y - mid.y, s["p"].x - mid.x)
                flat = Vector((s["p"].x - mid.x, s["p"].y - mid.y, 0.0))
                s["lining"] = flat.length > 1e-4 and s["n"].length > 1e-9 and s["n"].normalized().dot(flat.normalized()) < -0.2  # the inside wall of a doubled piece
            # where around the middle the cloth is: all the way round, or an arc of it (the back of a hood, a coat's tails)
            angles = sorted(s["angle"] for s in hanging)
            gap, gap_at = 2 * math.pi - (angles[-1] - angles[0]), len(angles) - 1
            for i in range(len(angles) - 1):
                if angles[i + 1] - angles[i] > gap:
                    gap, gap_at = angles[i + 1] - angles[i], i
            around = gap < math.radians(100)
            reach = sum(math.hypot(s["p"].x - mid.x, s["p"].y - mid.y) for s in hanging) / len(hanging)
            start = angles[(gap_at + 1) % len(angles)]
            arc = 2 * math.pi if around else 2 * math.pi - gap
            gear_name = obj.get("gear") or obj.name
            kind = PARAMS["kind"].get(gear_name) or kind_of(anchor, around, facing_of(start + arc / 2), arc * reach / tall, drop / tall, (line - floor_z) / tall)
            about = PARAMS["kinds"].get(kind) or PARAMS["kinds"]["short skirt"]
            slug = slug_of(gear_name)
            if not about.get("chains"):  # a collar: too short to swing. It stays with the body, and is only written down
                garments.append({"gear": gear_name, "slug": slug, "kind": kind, "parent": anchor, "chains": 0, "card": about.get("card", "held"), "hold": about.get("hold", 0.5),
                                 "drop_cm": round(100 * drop, 1)})
                continue
            fewest, most = about["chains"]
            every = about.get("every", PARAMS["chain_every"]) * tall
            if around:
                count = int(min(max(most, 4), max(fewest, 4, 2 * round(math.pi * reach / every))))  # an even number
                count += count % 2
                # the same on the left as on the right: a chain either side of the front and the back, or (for a kind that folds between the legs) one at each
                centers = [math.pi / 2 + 2 * math.pi * (i + (0.0 if about.get("centre") else 0.5)) / count for i in range(count)]
                half = math.pi / count
            else:
                count = int(min(most, max(fewest, round(arc * reach / every))))
                centers = [start + arc * (i + 0.5) / count for i in range(count)]
                half = arc / (2 * count)
                for s in hanging:
                    s["angle"] = turn_to(s["angle"], start + arc / 2)
            long = int(min(about.get("bones", 3), max(1, round(drop / (about.get("bone_long", PARAMS["bone_long"]) * tall)))))
            if any(c["slug"] == slug for c in chains if c["island"] != (name, number)):
                slug = "%s_%d" % (slug[:15], number)
            made = []
            for ci, center in enumerate(centers):
                share = [s for s in hanging if not s["lining"] and abs(turn_to(s["angle"], center) - center) <= half * 1.3] or hanging
                joints = []
                for level in range(long + 1):
                    near = [s for s in share if abs(s["hang"] - level / long) <= 0.6 / long]
                    joints.append(sum((s["p"] for s in near), Vector()) / len(near) if near else None)
                low = [j for j in joints if j is not None][-1]
                for level in range(long, -1, -1):  # a level with no points of its own (a skirt with one ring at the hem): straight above the one below
                    if joints[level] is None:
                        below = joints[level + 1] if level < long else low
                        joints[level] = Vector((below.x, below.y, line - drop * level / long))
                for level in range(long + 1):
                    if level and (joints[level] - joints[level - 1]).length < 0.01 * tall:
                        joints[level] = joints[level - 1] - Vector((0, 0, 0.5 * drop / long))
                out = Vector((math.cos(center), math.sin(center), 0.0))
                names = ["cloth_%s_%d_%d" % (slug, ci + 1, level + 1) for level in range(long)]
                made.append({"bones": names, "joints": joints, "out": out, "center": center})
            # weights: more of the chain the lower a point hangs; between two chains, some of each
            for s in hanging:
                order = sorted([(abs(turn_to(s["angle"], c["center"]) - c["center"]), i) for i, c in enumerate(made)])
                near = order[:2]
                span = near[0][0] + near[1][0] if len(near) > 1 else 0.0
                mix = [(near[0][1], 1.0)] if span < 1e-9 or len(near) < 2 or near[1][0] > 2.6 * half else [(near[0][1], near[1][0] / span), (near[1][1], near[0][0] / span)]
                level = s["hang"] * long
                along = {}
                for b in range(long):
                    w = max(0.0, 1.0 - abs(level - (b + 0.5)))
                    if b == 0 and level < 0.5:
                        w = 1.0
                    if b == long - 1 and level > long - 0.5:
                        w = 1.0
                    if w > 0:
                        along[b] = w
                total = sum(along.values())
                cloth = {}
                for ci, share in mix:
                    for b, w in along.items():
                        cloth[made[ci]["bones"][b]] = share * w / total
                grip = min(1.0, s["hang"] * long / PARAMS["grip_over"])
                grip = grip * grip * (3 - 2 * grip)
                # Cloth that rests against the body (a kilt's side on a thigh) stays with the body there; cloth that stands off it swings.
                loose = min(1.0, max(0.0, (s["off"] - 0.0075 * tall) / (0.03 * tall)))
                grip *= loose * loose * (3 - 2 * loose)
                s["w"] = blend([(blend([(s["w"], 1.0)]) if grip < 1 else {}, 1.0 - grip), (cloth, grip)])
            for c in made:
                chains.append({"slug": slug, "island": (name, number), "gear": gear_name, "parent": anchor, "bones": c["bones"],
                               "joints": c["joints"], "out": c["out"], "kind": kind, "garment": len(garments)})
            garments.append(dict({k: about[k] for k in ("mass", "bend", "damp", "shape", "swing", "reach", "collide", "floor", "card") if k in about},
                                 gear=gear_name, slug=slug, kind=kind, parent=anchor, around=bool(around), facing=None if around else facing_of(start + arc / 2),
                                 chains=len(made), bones_a_chain=long, drop_cm=round(100 * drop, 1)))

    if chains:
        for o in bpy.context.selected_objects:
            o.select_set(False)
        rig.hide_set(False)
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode="EDIT")
        back = rig.matrix_world.inverted()
        for c in chains:
            for i, bone_name in enumerate(c["bones"]):
                old = rig.data.edit_bones.get(bone_name)
                if old is not None:
                    rig.data.edit_bones.remove(old)
                bone = rig.data.edit_bones.new(bone_name)
                bone.head, bone.tail = back @ c["joints"][i], back @ c["joints"][i + 1]
                bone.parent = rig.data.edit_bones[c["bones"][i - 1] if i else c["parent"]]
                bone.use_connect = False  # (swing.py may slide a bone as well as turn it: each carries its own patch of the cloth)
                bone.align_roll(back.to_3x3() @ c["out"])  # its z axis points out of the cloth: x swings it out and in, z from side to side
                new_bones.append(bone_name)
        bpy.ops.object.mode_set(mode="OBJECT")
        limits = known.setdefault("limits", {})
        hangs_from = {name: c["parent"] for c in chains for name in c["bones"]}
        for bone_name in new_bones:
            bone = rig.pose.bones[bone_name]
            bone.rotation_mode = "QUATERNION"
            lim = [float(v) for v in PARAMS["limits"]]
            for old in [r for r in bone.constraints if r.type == "LIMIT_ROTATION"]:
                bone.constraints.remove(old)
            rule = bone.constraints.new("LIMIT_ROTATION")
            rule.name = "Joint limit"
            rule.owner_space = "LOCAL"
            rule.euler_order = "XYZ"
            rule.use_limit_x = rule.use_limit_y = rule.use_limit_z = True
            rule.min_x, rule.max_x, rule.min_y, rule.max_y, rule.min_z, rule.max_z = [math.radians(v) for v in lim]
            rig.data.bones[bone_name]["limit_deg"] = lim
            rig.data.bones[bone_name]["cloth"] = 1
            limits[bone_name] = lim
        rig["forge_rig"] = json.dumps(known)

# ---- write the weights ----
for name in sorted(dressed):
    obj, spots = dressed[name]
    for group in list(obj.vertex_groups):
        obj.vertex_groups.remove(group)
    groups = {}
    for spot in spots:
        for bone, w in blend([(spot["w"], 1.0)]).items():
            if bone not in groups:
                groups[bone] = obj.vertex_groups.new(name=bone)
            groups[bone].add(spot["verts"], w, "REPLACE")

# ---- what swing.py needs, kept on the rig; and the note that makes animate.py ask for it ----
kept = [{"gear": c["gear"], "parent": c["parent"], "bones": c["bones"], "kind": c["kind"], "garment": c["garment"]} for c in chains]
rig["forge_cloth"] = json.dumps({"chains": kept, "garments": garments})
then = [t for t in json.loads(rig.get("forge_then", "[]")) if t != "swing.py"]
rig["forge_then"] = json.dumps(then + (["swing.py"] if chains else []))

pieces = {}
for c in chains:
    entry = pieces.setdefault(c["island"], {"gear": c["gear"], "mesh": c["island"][0], "kind": c["kind"], "hangs_from": c["parent"], "chains": 0, "bones_a_chain": len(c["bones"])})
    entry["chains"] += 1
result = {
    "rig": rig.name, "meshes": report, "cloth_bones": new_bones, "loose": list(pieces.values()), "garments": garments,
    "bones_in_all": len(rig.data.bones), "then": json.loads(rig["forge_then"]),
}
print("RESULT " + json.dumps(result))
