"""Does a bent joint read as the joint it is? A take's cast drawn as cards, joint by joint, against the real
models posed the same.

    Blender -b --factory-startup -P scripts/impostor/judge_joints.py -- --out <folder> [--tag before]
        [--runs runs] [--shots shots] [--take crew-candy-shop] [--model detailed] [--sheets joined|skinned|necked|bent]
        [--at 38] [--deep 2] [--kinds knee,elbow,hip,shoulder|neck|yoke] [--eyes crew,2,1] [--looks joe,pixel-both]
        [--only left] [--core 0.6] [--stills left@38:shin_l:1,...|asked] [--parts left@38:shin_l:1]

judge_seams.py counts pixels the cards leave bare. A knee can have none bare and still not be a knee: a hollow
plugged with one flat colour, with the rim of the part drawn round it, is a socket. So this one compares what
is drawn. For every one of the cast, at each of --at seconds of the take (both knees) and at the --deep moments
where each of --kinds is bent furthest (that joint), it draws the character from the same eye twice: as cards,
by impostor.py, in each look; and the real model those cards were pictured from, posed by the same bones and
drawn the comic way, twice as fine. The eyes: the set's crew camera, and a square 55 cm across round the joint
as the screen would show it from 2 m and from 1 m off, on the crew camera's side. In a disc about the joint (the
ring where its two parts meet and 6 cm more), over the real model's own body:

    likeness   how well the cards' light and dark follows the real model's: 1 is the same shapes in the same
               places, 0 is nothing in common (the two blurred over 4 mm, the cards slid up to a centimetre)
    blots      the share of the disc where the cards are a good deal darker than the model (50 of 255, both
               blurred over 6 mm): a dark ring, a hollow, a black scratch
    colour     how far the cards' colour is from the model's, of 255, a typical pixel. The looks paint
               differently from the comic way the model is drawn, so this is for one look before and after
    bare       pixels of the model's body the cards do not cover, in pixels of the screen

--kinds may also name "neck" (the head's joint, as any other joint) and "yoke": the neck, the collar and both
shoulders together, in one disc about the foot of the neck that reaches 4 cm past the further shoulder (the square
round it from close by is 80 cm). The yoke is looked at where the dance asks most of it, --deep moments of each:
"turn" (the head turned furthest against the chest), "raise" (an arm raised highest), "shrug" (a collar bone
turned furthest against the chest) and "twist" (the chest turned furthest against the hips). Its rows have two
things more. "over": pixels the cards cover and the model does not (what sticks out; every row has it). And
the skin itself, measured on the model and not on a picture (Yoke, below): "held_cm" is how far a rigid card
holds the skin of the neck and collar from where the model has it (and "held_worst_cm": 95 points of a hundred
are nearer), "off_cm" the same for what is drawn there, which is the neck's piece when the cards have one
(bake_joints.py). --stills yoke writes a still of every such moment from every eye.

"shaft" rows are the same disc laid on the middle of a thigh or an upper arm, where nothing bends: what the
cards score when nothing is wrong. --sheets says which baked cards to read: joined (as they were: rigid parts,
a ball in each joint), skinned (those, with a piece of the real model bending in each big joint: bake_joints.py),
necked (those, and a piece for the neck and collar too: what the pages read, and what is read unless told)
or bent (joint cards pictured bent: bake_impostor.py --bent).

Writes <out>/joints[-tag].json and, for --stills (role@seconds:bone:eye), <tag>-<role>-<seconds>-<bone>-<eye>.png:
the real model, then the cards in each look. --parts writes the same square with the upper part's card alone and
the lower part's alone: what each picture holds at the joint. Never touches an open Blender.
"""

import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import impostor  # noqa: E402

SIZE = (1080, 608)
FINER = 2            # the real model is drawn this many times finer than the screen
K = 2                # screen pixels to one of the pixel looks' big ones, at this size (looks.js: 270 rows)
SQUARE_M = 0.55      # the square round a joint, from close by
SCREEN_FOV = 36.0    # the free eye's view on the watch page: how big a pixel is from 1 m and 2 m follows from it
REACH_M = 0.06       # a joint's disc reaches this far past the ring where its two parts meet
OFF_M = 0.01         # the cards' picture may sit this far from the model's
BLOT = 50.0          # darker than the model by this much (of 255) is a blot
LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
PAPER = (250, 248, 245)
KINDS = {"shin": "knee", "forearm": "elbow", "upper_arm": "shoulder", "thigh": "hip", "head": "neck"}
SHAFT = {"knee": "thigh", "elbow": "upper_arm"}  # where nothing bends: the middle of the part above
STEPS = (30, 60, 90)
YOKE_SQUARE_M = 0.8  # the square round the foot of the neck that holds the head, the collar and both shoulders
YOKE_REACH_M = 0.04  # the yoke's disc reaches this far past the further shoulder
YOKE_MOVES = ("turn", "raise", "shrug", "twist")
SHEETS = {"joined": {"joe": ["joe-joined"], "pixel-both": ["pixel-clear", "pixel-joined"], "comic": ["comic-joined"], "pixel-baked": ["pixel-joined"]},
          "skinned": {"joe": ["joe-skinned"], "pixel-both": ["pixel-clear-skinned"], "comic": ["comic-skinned"], "pixel-baked": ["pixel-skinned"]},
          "necked": {"joe": ["joe-necked", "joe-skinned"], "pixel-both": ["pixel-clear-necked", "pixel-clear-skinned"], "comic": ["comic-necked", "comic-skinned"], "pixel-baked": ["pixel-necked", "pixel-skinned"]},
          "bent": {"joe": ["joe-bent"], "pixel-both": ["pixel-bent"], "comic": ["comic-bent"], "pixel-baked": ["pixel-bent"]}}


def kind_of(bone):
    return KINDS.get(bone[:-2], "") or KINDS.get(bone, "")


def turned(rest, pose, a, b):
    """How far bone b is turned in bone a's frame from how it rests there, degrees."""
    r = lambda m: np.asarray(m)[:3, :3] / np.cbrt(abs(np.linalg.det(np.asarray(m)[:3, :3])))
    return math.degrees(impostor.angle_of((r(rest[a]).T @ r(rest[b])).T @ (r(pose[a]).T @ r(pose[b]))))


def yoke_moves(rest, pose):
    """What the neck and the shoulders are doing in a pose, each in degrees: "turn" (the head against the chest),
    "raise" (the higher arm above level; an arm hanging is -90), "shrug" (the collar bone turned furthest against
    the chest) and "twist" (the chest against the hips)."""
    up = lambda side: math.degrees(math.asin(max(-1.0, min(1.0, float(impostor.unit(pose["forearm" + side][:3, 3] - pose["upper_arm" + side][:3, 3])[1])))))
    return {"turn": turned(rest, pose, "chest", "head"), "raise": max(up("_l"), up("_r")),
            "shrug": max(turned(rest, pose, "chest", "shoulder_l"), turned(rest, pose, "chest", "shoulder_r")), "twist": turned(rest, pose, "hips", "chest")}


def luma(picture):
    cover = picture[..., 3:4].astype(np.float32) / 255.0
    return (picture[..., :3].astype(np.float32) * cover + np.array(PAPER, dtype=np.float32) * (1.0 - cover)) @ LUMA


def soft(a, r):
    """Each pixel the mean of the square of pixels r either side of it."""
    if r < 1:
        return a
    pad = np.pad(a, r, mode="edge")
    total = np.pad(np.cumsum(np.cumsum(pad, axis=0), axis=1), ((1, 0), (1, 0)))
    n = 2 * r + 1
    return (total[n:, n:] - total[:-n, n:] - total[n:, :-n] + total[:-n, :-n]) / float(n * n)


def blown(picture, times):
    return picture if times == 1 else np.repeat(np.repeat(picture, times, axis=0), times, axis=1)


class Yoke:
    """How far what is drawn of the neck, the collar and the shoulder tops stands from where the real model has
    that skin, measured on the skin itself and not on a picture of it.

    The skin is the real model's own points that the chest's card holds: inside a ball about the foot of the neck
    (as big as bake_joints.py makes the neck piece's zone), outside the shoulders' zones. A card is rigid: it has
    each of them where it was when the cards were pictured, carried by the chest bone alone. "held" is how far
    that is from where the model has the same point now. "off" is the same for what is drawn there: the neck
    piece's points when the cards have one (the chest's card has stepped aside), each against the point of the
    model it lay on when the cards were pictured; with no piece, the rigid points, and "off" is "held"."""

    def __init__(self, real, card):
        import bpy
        import bake_impostor
        import yoke as arithmetic
        from mathutils import Matrix
        self.real, self.bpy, rig = real, bpy, real.rig
        head = lambda bone: rig.matrix_world @ rig.data.bones[bone].head_local
        foot = head("neck")
        self.zone = arithmetic.zone(foot, [head(b) for b in ("upper_arm_l", "upper_arm_r")], head("chest"))
        rings = {j["bone"]: j["ring_cm"] / 100.0 for j in card.get("joints") or []}
        shoulders = [(head(b), 1.35 * rings[b]) for b in ("upper_arm_l", "upper_arm_r") if b in rings]
        folds = bake_impostor.part_of_bone(rig)
        self.picked = []  # per mesh: (the mesh, which of its points, where each was when the cards were pictured)
        for obj in real.bodies:
            groups = [folds.get(g.name) for g in obj.vertex_groups]
            picked = []
            for v in obj.data.vertices:
                at = obj.matrix_world @ v.co
                if (at - foot).length >= self.zone or any((at - c).length < z for c, z in shoulders):
                    continue
                pull = {}
                for g in v.groups:
                    pull[groups[g.group]] = pull.get(groups[g.group], 0.0) + g.weight
                if pull and max(pull, key=pull.get) == "chest":
                    picked.append(v.index)
            hung = real.hung[obj.name]
            self.picked.append((obj, np.array(picked, dtype=np.int64), np.array([obj.matrix_world @ hung.vertices[i].co for i in picked]).reshape(-1, 3)))
        self.hung_chest = np.array(real.hung_bones["chest"])
        # the skeleton as the cards were pictured, as a clip's frames have a pose (judge_seams.py: Real.pose, backwards)
        to_glb = np.linalg.inv(np.array(Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))))
        self.hung_frames = {name: to_glb @ np.array(world) @ np.linalg.inv(np.array(real.fit[name])) for name, world in real.hung_bones.items() if name in real.fit}
        self.matched = {}

    def stand(self):
        """The real model's picked points as the pose has them now (Blender's world)."""
        shells = [m for obj, _, _ in self.picked for m in obj.modifiers if m.type != "ARMATURE" and m.show_viewport]
        for m in shells:  # (the comic way's ink shell is more points; only the skeleton's pull is wanted here)
            m.show_viewport = False
        graph = self.bpy.context.evaluated_depsgraph_get()
        graph.update()
        out = []
        for obj, picked, _ in self.picked:
            shown = obj.evaluated_get(graph)
            me = shown.to_mesh()
            co = np.empty(len(me.vertices) * 3, dtype=np.float32)
            me.vertices.foreach_get("co", co)
            world = np.array(obj.matrix_world)
            out.append(co.reshape(-1, 3)[picked].astype(np.float64) @ world[:3, :3].T + world[:3, 3])
            shown.to_mesh_clear()
        for m in shells:
            m.show_viewport = True
        return np.concatenate(out)

    def measure(self, character):
        """After real.pose(pose): {"held_cm", "held_worst_cm", "off_cm", "off_worst_cm" (worst: 95 of a hundred
        points are nearer), "piece": whether the cards have a neck piece}."""
        from mathutils import kdtree
        rig, pose = self.real.rig, self.real.frames
        now = np.array(rig.matrix_world @ rig.pose.bones["chest"].matrix) @ np.linalg.inv(self.hung_chest)
        true = self.stand()
        hung = np.concatenate([h for _, _, h in self.picked])
        held = np.linalg.norm(hung @ now[:3, :3].T + now[:3, 3] - true, axis=1) * 100.0
        skin = getattr(character, "skin", None)
        piece = next((j["bone"] for j in skin.joints if j.get("kind") == "neck" and j["bone"] in skin.pieces), None) if skin else None
        off = held
        if piece:
            to_bl = lambda at: np.stack([at[:, 0], -at[:, 2], at[:, 1]], axis=1)  # a .glb's y-up to Blender's z-up
            if id(skin) not in self.matched:  # each of the piece's points against the model's point it lay on
                tree = kdtree.KDTree(len(hung))
                for i, p in enumerate(hung):
                    tree.insert(p, i)
                tree.balance()
                found = [tree.find(p) for p in to_bl(skin.stood(piece, self.hung_frames)[0])]
                self.matched[id(skin)] = (np.array([f[1] for f in found]), np.array([f[2] for f in found]) < 0.01)
            match, close = self.matched[id(skin)]
            off = np.linalg.norm(to_bl(skin.stood(piece, pose)[0]) - true[match], axis=1)[close] * 100.0
        return {"held_cm": round(float(held.mean()), 2), "held_worst_cm": round(float(np.percentile(held, 95)), 2), "off_cm": round(float(off.mean()), 2),
                "off_worst_cm": round(float(np.percentile(off, 95)), 2), "piece": bool(piece)}


def judge(real, cards, disc, per_px):
    """The cards' picture against the real model's inside a disc, both the fine size (per_px: metres a pixel):
    {"likeness", "blots", "colour", "bare" (fine pixels), "ground" (fine pixels of the model in the disc)}."""
    there = real[..., 3] > 127
    region = disc & there
    ground = int(region.sum())
    if ground < 12:
        return None
    tall, wide = there.shape
    ys, xs = np.nonzero(region)
    truth, mine = luma(real), luma(cards)
    blur = max(1, int(round(0.004 / per_px)))
    a, b = soft(truth, blur), soft(mine, blur)
    reach = max(1, int(round(OFF_M / per_px)))
    av = a[ys, xs] - a[ys, xs].mean()
    best = -1.0
    for dx in range(-reach, reach + 1, max(1, reach // 2)):
        for dy in range(-reach, reach + 1, max(1, reach // 2)):
            bv = b[np.clip(ys + dy, 0, tall - 1), np.clip(xs + dx, 0, wide - 1)]
            bv = bv - bv.mean()
            best = max(best, float((av * bv).sum() / max(1e-6, math.sqrt(float((av * av).sum() * (bv * bv).sum())))))
    wider = max(1, int(round(0.006 / per_px)))
    a, b = soft(truth, wider), soft(mine, wider)
    both = region & (cards[..., 3] > 127)
    off = np.abs(real[..., :3].astype(np.float32) - cards[..., :3].astype(np.float32)).mean(axis=-1)
    return {"likeness": max(0.0, best), "blots": float((a[ys, xs] - b[ys, xs] > BLOT).mean()), "colour": float(off[both].mean()) if both.any() else None,
            "bare": int((region & ~(cards[..., 3] > 127)).sum()), "over": int((disc & ~there & (cards[..., 3] > 127)).sum()), "ground": ground}


def over_paper(picture):
    cover = picture[..., 3:4].astype(np.float32) / 255.0
    return np.round(picture[..., :3] * cover + np.array(PAPER, dtype=np.float32) * (1.0 - cover)).astype(np.uint8)


def still(path, pictures, disc=None, tall=420, crop=None):
    """Pictures side by side, blown up whole to about `tall` pixels; the disc that was judged ringed on the first.
    crop: (x0, y0, x1, y1) in the pictures' pixels, to show only that much of each."""
    if crop is not None:
        x0, y0, x1, y1 = crop
        pictures, disc = [p[y0:y1, x0:x1] for p in pictures], None if disc is None else disc[y0:y1, x0:x1]
    times = max(1, tall // pictures[0].shape[0])
    cuts = []
    for n, picture in enumerate(pictures):
        shown = over_paper(picture)
        if n == 0 and disc is not None:
            edge = disc & ~(np.roll(disc, 1, 0) & np.roll(disc, -1, 0) & np.roll(disc, 1, 1) & np.roll(disc, -1, 1))
            shown[edge] = (40, 200, 90)
        cuts += [blown(shown, times), np.full((shown.shape[0] * times, 10, 3), 255, dtype=np.uint8)]
    impostor.write_png(path, np.concatenate(cuts[:-1], axis=1))


def draw_look(character, pose, eye, look, only=None):
    """The cards as the page draws them in a look, through an eye the size of the screen's picture, blown up to
    FINER times that."""
    who = np.zeros((eye.size[1], eye.size[0]), dtype=np.int32)
    marked = bool(character.card.get("line_marked"))
    if look == "pixel-both":
        small = impostor.Eye(eye.at, eye.aim, eye.fov_deg, (eye.size[0] // K, eye.size[1] // K))
        if only is None:
            picture = impostor.draw_fine_heads(character, pose, small, paint=impostor.PAINTS["pixel"])[0]
            return blown(impostor.cut_levels(picture, impostor.PAINTS["pixel"]["levels"]), K * FINER // impostor.FINE)
        picture = impostor.draw(character, pose, small, line="off", paint=impostor.PAINTS["pixel"], only=only)[0]
        return blown(impostor.cut_levels(picture, impostor.PAINTS["pixel"]["levels"]), K * FINER)
    if look == "joe":
        picture, depth, _ = impostor.draw(character, pose, eye, line="off" if marked else "shell", who=who, paint=impostor.PAINTS["joe"], only=only)
        lines = impostor.bold_lines(depth, who if marked else None, eye) & (who > 0)
        if marked and "screen" in impostor.FILL:
            picture, depth, who, filled = impostor.crack_fill(picture, depth, who, impostor.bold_offsets())
            lines &= ~filled
        return blown(impostor.with_lines(picture, lines), FINER)
    paint = impostor.PAINTS["pixel" if look == "pixel-baked" else "comic"]
    return blown(impostor.draw(character, pose, eye, line="shell", paint=paint, only=only)[0], FINER)


def main():
    import judge_seams  # the real model in a background Blender (needs bpy)
    args = sys.argv[sys.argv.index("--") + 1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    out = os.path.abspath(flag("--out", "evidence/knees"))
    os.makedirs(out, exist_ok=True)
    tag, model, which = flag("--tag", ""), flag("--model", "detailed"), flag("--sheets", "necked")
    runs, shots = os.path.abspath(flag("--runs", os.path.join(REPO, "runs"))), os.path.abspath(flag("--shots", os.path.join(REPO, "shots")))
    take = os.path.join(shots, flag("--take", "crew-candy-shop"))
    at = [float(t) for t in flag("--at", "38").split(",") if t]
    deep = int(flag("--deep", "2"))
    kinds = flag("--kinds", "knee,elbow,hip,shoulder").split(",")
    eyes, looks = flag("--eyes", "crew,2,1").split(","), flag("--looks", "joe,pixel-both").split(",")
    only = flag("--only", "").split(",") if flag("--only", "") else None
    impostor.ZONE_CORE = float(flag("--core", str(impostor.ZONE_CORE)))  # to try: how much of a card is kept inside a joint's zone (0: nothing)
    stills, parts_of = set(flag("--stills", "").split(",")) - {""}, set(flag("--parts", "").split(",")) - {""}
    with open(os.path.join(take, next(f for f in sorted(os.listdir(take)) if f.startswith("cast-") and f.endswith(".json")))) as f:
        cast = json.load(f)
    with open(os.path.join(REPO, "sets", cast["set"], "set.json")) as f:
        crew = json.load(f)["cameras"]["crew"]
    crew_fov = math.degrees(2.0 * math.atan(36.0 / (16.0 / 9.0) / 2.0 / crew["lens_mm"]))
    report = {"take": os.path.basename(take), "model": model, "sheets": which, "size": list(SIZE), "rows": [], "folders": {}}
    began = time.time()

    # (any other name: cards with pieces baked under that name, bake_joints.py --name)
    # (a look with no cards of that name keeps the ones with pieces: "Pixels, baked" has none baked with layers, --sheets layered-skinned)
    sheets = SHEETS.get(which) or {look: [n.replace("skinned", which) for n in names] + names for look, names in SHEETS["skinned"].items()}
    for role, part in cast["roles"].items():
        if only and role not in only:
            continue
        run = part["character"].split("/runs/")[1].split("/")[0]
        profiles = os.path.join(runs, run, "profiles")
        characters = {}
        for look in looks:
            folder = next(os.path.join(profiles, "%s-impostor-%s" % (model, n)) for n in sheets[look] if os.path.isfile(os.path.join(profiles, "%s-impostor-%s" % (model, n), "impostor.json")))
            characters[look] = characters.get(folder) or impostor.Character(folder)
            characters[folder] = characters[look]
            report["folders"].setdefault(role, {})[look] = os.path.basename(folder)
        first = characters[looks[0]].card
        real = judge_seams.Real(os.path.join(profiles, first["source"]), first, pieces=False)
        motion = impostor.Glb(os.path.join(take, part["glb"]))
        rings = {j["bone"]: j["ring_cm"] / 100.0 for j in first.get("joints") or []}
        above = {j["bone"]: next(p["bone"] for p in first["parts"] if p["name"] == j["between"][1]) for j in first.get("joints") or []}
        # the moments, and the joints looked at in each: (seconds, [bones])
        moments = [(t, [b for b in rings if kind_of(b) == "knee"], "") for t in at if "knee" in kinds]
        rest = motion.pose(None)
        yoke = Yoke(real, first) if "yoke" in kinds else None
        if deep:
            looked = [(t, real.bends(motion.pose(t))) for t in np.arange(0.0, motion.seconds, 0.25)]
            for kind in kinds:
                picked = []
                for _, bone, t in sorted(((max((v, b) for b, v in bends.items() if kind_of(b) == kind) + (t,)) for t, bends in looked if any(kind_of(b) == kind for b in bends)), reverse=True):
                    if len(picked) < deep and all(abs(t - u) >= 1.0 for u, _, _ in picked):
                        picked.append((float(t), [bone], ""))
                moments += picked
            if "yoke" in kinds:  # the moments the neck and shoulders are asked most of: the head turned, an arm raised, a shrug, a twist
                moves = [(t, yoke_moves(rest, motion.pose(t))) for t in np.arange(0.0, motion.seconds, 0.25)]
                for why in YOKE_MOVES:
                    picked = []
                    for _, t in sorted(((m[why], t) for t, m in moves), reverse=True):
                        if len(picked) < deep and all(abs(t - u) >= 1.0 for u, _, _ in picked):
                            picked.append((float(t), ["neck"], why))
                    moments += picked
        for t, bones, why in sorted(moments):
            pose = motion.pose(t)
            real.pose(pose)
            bends = real.bends(pose)
            # every big joint is judged through the crew camera; the ones this moment is for from close by too
            spots = [(b, kind_of(b), pose[b][:3, 3], rings[b] + REACH_M) for b in rings if kind_of(b) in kinds]
            spots += [(above[b], "shaft", (pose[above[b]][:3, 3] + pose[b][:3, 3]) / 2.0, rings[b] + REACH_M) for b in rings if kind_of(b) in SHAFT and kind_of(b) in kinds]
            if "yoke" in kinds:  # the head's foot, the collar and both shoulders in one disc about the foot of the neck
                foot = pose["neck"][:3, 3]
                spots.append(("neck", "yoke", foot, max(float(np.linalg.norm(pose[b][:3, 3] - foot)) for b in ("upper_arm_l", "upper_arm_r")) + YOKE_REACH_M))
                bends = dict(bends, neck=yoke_moves(rest, pose).get(why, 0.0))
                slip = yoke.measure(characters[looks[0]])
            for eye_name in eyes:
                if eye_name == "crew":
                    views = [(impostor.Eye(np.array(crew["at"], dtype=float), np.array(crew["aim"], dtype=float), crew_fov, SIZE), spots, "")]
                else:  # a square round the joint, as the screen shows it from that many metres
                    away = float(eye_name)
                    views = []
                    for bone in bones:
                        square = YOKE_SQUARE_M if bone == "neck" else SQUARE_M
                        side = int(round(square * SIZE[1] / (2.0 * away * math.tan(math.radians(SCREEN_FOV) / 2.0)) / 4.0)) * 4
                        joint = pose[bone][:3, 3] + (np.array([0.0, 0.08, 0.0]) if bone == "neck" else 0.0)
                        toward = impostor.unit(np.array([crew["at"][0] - joint[0], 0.0, crew["at"][2] - joint[2]]))
                        eye = impostor.Eye(joint + away * toward + np.array([0.0, 0.12 * away, 0.0]), joint, math.degrees(2.0 * math.atan(square / 2.0 / away)), (side, side))
                        views.append((eye, [s for s in spots if s[0] in (bone, above.get(bone)) or (bone == "neck" and s[1] in ("neck", "shoulder"))], bone))
                for eye, judged, focus in views:
                    fine = impostor.Eye(eye.at, eye.aim, eye.fov_deg, (eye.size[0] * FINER, eye.size[1] * FINER))
                    truth = real.draw(fine, 0.0)
                    ys, xs = np.mgrid[0:fine.size[1], 0:fine.size[0]]
                    drawn = {look: draw_look(characters[look], pose, eye, look) for look in looks}
                    discs = {}
                    for bone, kind, where, radius in judged:
                        centre, ahead = fine.to_pixels(where)
                        per_px = 2.0 * float(ahead) * fine.tan / fine.size[1]
                        disc = (xs + 0.5 - centre[0]) ** 2 + (ys + 0.5 - centre[1]) ** 2 < (radius / per_px) ** 2
                        discs[(bone, kind)] = disc
                        for look in looks:
                            got = judge(truth, drawn[look], disc, per_px)
                            if got is None:
                                continue
                            got["bare"], got["over"] = round(got["bare"] / float(FINER * FINER), 1), round(got["over"] / float(FINER * FINER), 1)
                            report["rows"].append(dict(got, role=role, seconds=round(t, 2), eye=eye_name, look=look, bone=bone, kind=kind, bend=round(bends.get(bone, 0.0), 1) if kind != "shaft" else 0.0,
                                                       why=why if kind == "yoke" else "", **(slip if kind == "yoke" else {}), focus=bool(focus == bone or (eye_name == "crew" and bone in bones))))
                    name = "%s@%g:%s:%s" % (role, t, focus or "all", eye_name)
                    if name in stills or ("asked" in stills and focus and eye_name == eyes[-1]) or ("yoke" in stills and why and focus):
                        still(os.path.join(out, "%s-%s-%g-%s-%s.png" % (tag or which, role, t, why or focus or "all", eye_name)), [truth] + [drawn[look] for look in looks], discs.get((focus, "yoke" if why else kind_of(focus))) if focus else None)
                    if "yoke" in stills and why and not focus:  # through the crew camera: the same, cut out round the yoke
                        centre, ahead = fine.to_pixels(pose["neck"][:3, 3])
                        half = int(0.45 / (2.0 * float(ahead) * fine.tan / fine.size[1]))
                        x0, y0 = int(np.clip(centre[0] - half, 0, fine.size[0] - 2 * half)), int(np.clip(centre[1] - half, 0, fine.size[1] - 2 * half))
                        still(os.path.join(out, "%s-%s-%g-%s-%s.png" % (tag or which, role, t, why, eye_name)), [truth] + [drawn[look] for look in looks], discs.get(("neck", "yoke")), crop=(x0, y0, x0 + 2 * half, y0 + 2 * half))
                    if name in parts_of and focus:
                        lower = next(p["name"] for p in first["parts"] if p["bone"] == focus)
                        upper = next(p["name"] for p in first["parts"] if p["bone"] == above[focus])
                        for look in looks:
                            still(os.path.join(out, "%s-%s-%g-%s-%s-%s-parts.png" % (tag or which, role, t, focus, eye_name, look)),
                                  [truth, drawn[look], draw_look(characters[look], pose, eye, look, [upper]), draw_look(characters[look], pose, eye, look, [lower])])
            print("JOINTS %s %.2f s (%s)" % (role, t, ", ".join(bones)), flush=True)

    # the sums: for every eye, look and kind of joint, by how far it is bent; and the joints each moment was for
    table = {}
    mean = lambda xs: round(float(np.mean(xs)), 3) if len(xs) else None
    for row in report["rows"]:
        step = "shaft" if row["kind"] == "shaft" else ["under 30", "30 to 60", "60 to 90", "90 and over"][sum(row["bend"] >= s for s in STEPS)]
        if row["kind"] == "yoke":  # the neck and shoulders together: by what they were doing, not by how far one joint is bent
            keys = ["%s|%s|yoke|%s" % (row["eye"], row["look"], row["why"] or "other"), "%s|%s|yoke|all" % (row["eye"], row["look"])]
        else:
            keys = ["%s|%s|%s|%s" % (row["eye"], row["look"], row["kind"], step)]
            if row["kind"] != "shaft":
                keys.append("%s|%s|%s|all" % (row["eye"], row["look"], row["kind"]))
                if row["bend"] >= 60:
                    keys.append("%s|%s|any|60 and over" % (row["eye"], row["look"]))
            if row["focus"] and row["kind"] != "shaft":
                keys.append("%s|%s|%s|asked" % (row["eye"], row["look"], row["kind"]))
        for key in keys:
            e = table.setdefault(key, {"joints": 0, "likeness": [], "blots": [], "colour": [], "bare": [], "over": []})
            e["joints"] += 1
            for k in ("likeness", "blots", "colour", "bare", "over"):
                if row[k] is not None:
                    e[k].append(row[k])
            for k in ("held_cm", "held_worst_cm", "off_cm", "off_worst_cm"):  # the yoke's skin itself (Yoke)
                if k in row:
                    e.setdefault(k, []).append(row[k])
    for key in sorted(table):
        e = table[key]
        e.update(worst=round(float(min(e["likeness"])), 3), likeness=mean(e["likeness"]), blots=mean(e["blots"]), colour=mean(e["colour"]), bare=mean(e["bare"]), over=mean(e["over"]))
        skin = ""
        if "off_cm" in e:
            e.update({k: mean(e[k]) for k in ("held_cm", "held_worst_cm", "off_cm", "off_worst_cm")})
            skin = "; the skin a rigid card would hold %.1f cm off (%.1f at worst), what is drawn %.1f cm (%.1f)" % (e["held_cm"], e["held_worst_cm"], e["off_cm"], e["off_worst_cm"])
        print("JOINTS %-44s %3d joints: likeness %.3f (worst %.3f), blots %4.1f%%, colour off %4.1f, bare %5.1f px, over %5.1f px%s" % (key, e["joints"], e["likeness"], e["worst"], 100.0 * e["blots"], e["colour"] or 0.0, e["bare"], e["over"], skin), flush=True)
    report["table"] = table
    report["seconds"] = round(time.time() - began, 1)
    with open(os.path.join(out, "joints%s.json" % (tag and "-" + tag)), "w") as f:
        json.dump(report, f, indent=1)
    print("RESULT " + json.dumps({"out": out, "seconds": report["seconds"]}))


if __name__ == "__main__":
    main()
