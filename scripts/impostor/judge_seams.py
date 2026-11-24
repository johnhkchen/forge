"""Counts what shows at the joints of characters drawn as flat cards: dark lines and see-through gaps.

    Blender -b --factory-startup -P scripts/impostor/judge_seams.py -- --out <folder> [--tag before]
        [--runs runs] [--shots shots] [--take crew-candy-shop] [--model detailed] [--sheets old|new]
        [--times 9,13.5,18,...] [--walk 6] [--eyes crew,close] [--looks comic,pixel-baked,pixel-both,joe]
        [--why] [--stills left@24:close,right@31.5:crew]

For every one of the take's cast, at each of --times seconds of it (and at --walk moments of his own walk),
through the set's crew camera and from 2 m off, it draws the character twice from the same eye: as cards, by
impostor.py (the page's own arithmetic and its lines on the finished picture), in each look; and the real model
those cards were pictured from, posed by the same bones and drawn by toon.py in the same light with its own ink
line. Then it counts, in pixels of the picture:

    line         pixels of ink line the cards show well inside the body (a part's own line from its sheet, or a
                 line drawn on the finished picture) where the real model, drawn the same way with its own ink
                 line, has nothing dark within 1.2 cm: a line that is not there
    see-through  body the real model has (a pixel in from its edge) and the cards do not. Much of that is the
                 outline falling a little short (the real model's skin stretches into a web at an armpit; the
                 cards' does not). So two smaller counts say what is a gap: "holes" are shut in on every side by
                 the cards, and "between cards" has cards within a centimetre and a half on both sides

each over the whole figure and within 12 cm of a joint, and as a share of the real body's pixels.

--why also draws the cards with one thing changed at a time, to say what the see-through pixels come from:
the parts as rigid pieces of the real model riding the bones (no pictures at all: what the cut alone leaves
open); the search by depth in steps a quarter the length; the test that drops a pixel found far under the
surface left out; the outline taken from the data sheet alone (no cover test on the colour).

--sheets old reads the sheets as they were baked before the joints were mended (<model>-impostor,
-impostor-pixel-faces) and draws them as the page then did (a search by depth that gave up on the side of
something); new (the default) reads <model>-impostor-<look>-joined where there is one.

Writes <out>/seams[-tag].json and, for --stills, <tag>-<role>-<seconds>-<eye>-<look>.png: cards, real model,
and the cards again with the dark pixels marked red and the see-through ones blue. Never touches an open Blender.
"""

import json
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import impostor  # noqa: E402
import bake_impostor  # noqa: E402  (how a character is cut into parts)

TOON = os.path.join(REPO, ".claude", "skills", "tidy-mesh", "scripts", "toon.py")
SIZE = (1080, 608)
SEAM_M = 0.12          # this close to a joint is "at a joint"
CLOSE_M = 2.0
DARK = 80              # the real model's picture is "dark" where no colour of a pixel is over this (its ink is 33)
TO_BL = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))  # a .glb's y-up to Blender's z-up
# name: (which sheet, how many screen pixels one of the picture's is, the lines drawn on the finished picture)
LOOKS = {"comic": ("comic", 1, None), "pixel-baked": ("pixel", 1, None), "pixel-screen": ("comic", 2, "grid"), "pixel-both": ("pixel", 2, "grid"), "joe": ("joe", 1, "bold")}
PAPER = (250, 248, 245)


def run_toon(**params):
    with open(TOON) as f:
        source = f.read()
    space = {"__name__": "__main__"}
    head, _, tail = source.partition("\nimport ")
    exec(head, space)
    space["PARAMS"].update(params)
    exec("import " + tail, space)


def sheet_folder(profiles, model, sheet, which):
    """The baked cards a look reads, as gallery/looks.js picks them (bakedFor)."""
    names = ["%s-impostor-%s-joined" % (model, sheet)] if which == "new" else []
    if sheet != "comic":
        names += ["%s-impostor-%s-faces" % (model, sheet), "%s-impostor-%s" % (model, sheet)]
    names += ["%s-impostor-comic-joined" % model] if which == "new" else []
    names.append("%s-impostor" % model)
    return next(os.path.join(profiles, n) for n in names if os.path.isfile(os.path.join(profiles, n, "impostor.json")))


class Real:
    """The real model in a background Blender: posed by a set of bone frames, drawn the comic way. And the same
    model cut into the cards' parts, each a rigid piece riding its bone."""

    def __init__(self, glb, card, round_=None):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = scene = bpy.context.scene
        bpy.ops.import_scene.gltf(filepath=glb)
        self.rig = rig = next(o for o in scene.objects if o.type == "ARMATURE")
        self.bodies = [o for o in scene.objects if o.type == "MESH" and o.find_armature() and not o.get("under")]
        for obj in scene.objects:
            if obj.type == "MESH" and obj not in self.bodies:
                obj.hide_render = True
        rest = impostor.Glb(glb).pose(None)
        # the parts, cut exactly as the bake cuts them (arms hanging), each in its bone's own frame
        bake_impostor.hang_arms(scene, rig)
        graph = bpy.context.evaluated_depsgraph_get()
        posed = {o.name: bpy.data.meshes.new_from_object(o.evaluated_get(graph)) for o in self.bodies}
        round_ = round_ or card.get("cut")  # sheets baked since the joints were mended say how they were cut
        if round_:
            chosen, _, _ = bake_impostor.cut_round(self.bodies, rig, posed, round_["lap"], round_["smooth_m"], round_.get("ball", 0.0), round_.get("overlap", card["overlap"]), round_.get("trunk_overlap", card["trunk_overlap"]))
        else:
            chosen, _ = bake_impostor.cut(self.bodies, rig, card["overlap"], card["trunk_overlap"])
        white = bpy.data.materials.new("piece")
        white.use_nodes = True
        white.node_tree.nodes.clear()
        glow, out = white.node_tree.nodes.new("ShaderNodeEmission"), white.node_tree.nodes.new("ShaderNodeOutputMaterial")
        white.node_tree.links.new(glow.outputs[0], out.inputs["Surface"])
        self.pieces = []
        for name, bones in bake_impostor.PARTS:
            if not chosen[name] or bones[0] not in rest:
                continue
            moved = rig.pose.bones[bones[0]].matrix @ rig.data.bones[bones[0]].matrix_local.inverted()
            into = Matrix(np.linalg.inv(rest[bones[0]]).tolist()) @ bake_impostor.TO_GLB @ moved.inverted()
            for obj, faces, _, *ball in chosen[name]:
                made = bake_impostor.piece(obj, posed[obj.name], faces, into, ball[0] if ball else None)
                made.data.materials.clear()
                made.data.materials.append(white)
                made.hide_render = True
                self.pieces.append((bones[0], made))
        for b in rig.pose.bones:
            b.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        # how a bone's frame in the .glb sits in Blender's own frame for that bone (the same frame, as a rule)
        self.fit = {b.name: (TO_BL @ Matrix(rest[b.name].tolist())).inverted() @ (rig.matrix_world @ b.matrix_local) for b in rig.data.bones if b.name in rest}
        data = bpy.data.cameras.new("eye")
        data.sensor_fit, data.clip_start, data.clip_end = "VERTICAL", 0.1, 100.0
        self.cam = bpy.data.objects.new("eye", data)
        scene.collection.objects.link(self.cam)
        scene.camera = self.cam
        scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = SIZE[0], SIZE[1], 100
        run_toon(objects=[o.name for o in self.bodies], line_px=1.0, background=None, samples=16, soften=512, light=list(impostor.LIGHT), shade=[list(s) for s in impostor.SHADE])
        scene.render.image_settings.file_format, scene.render.image_settings.color_mode = "PNG", "RGBA"
        self.tmp = os.path.join(bpy.app.tempdir, "seams-real.png")
        self.tone = bpy.data.node_groups["comic tone"].nodes["Light"]
        self.ink = bpy.data.node_groups["comic ink"].nodes["Per Distance"]

    def pose(self, frames):
        """Stand the skeleton in a set of bone frames ({bone: 4x4 in a .glb's world})."""
        self.frames = frames
        back = self.rig.matrix_world.inverted()
        stood = {}
        todo = [b for b in self.rig.data.bones if b.parent is None]
        while todo:
            bone = todo.pop()
            todo += list(bone.children)
            pb = self.rig.pose.bones[bone.name]
            if bone.name in frames and bone.name in self.fit:
                stood[bone.name] = back @ TO_BL @ Matrix(np.asarray(frames[bone.name]).tolist()) @ self.fit[bone.name]
                if bone.parent is None:
                    pb.matrix_basis = bone.matrix_local.inverted() @ stood[bone.name]
                else:
                    pb.matrix_basis = (bone.parent.matrix_local.inverted() @ bone.matrix_local).inverted() @ stood[bone.parent.name].inverted() @ stood[bone.name]
            else:  # a bone the clip does not move rides its parent
                pb.matrix_basis = Matrix.Identity(4)
                stood[bone.name] = (stood[bone.parent.name] @ bone.parent.matrix_local.inverted() @ bone.matrix_local) if bone.parent else bone.matrix_local.copy()
        for bone, piece in self.pieces:
            piece.matrix_world = TO_BL @ Matrix(np.asarray(frames[bone]).tolist())
        bpy.context.view_layer.update()

    def shoot(self, eye):
        self.cam.data.angle_y = math.radians(eye.fov_deg)
        self.scene.render.resolution_x, self.scene.render.resolution_y = eye.size
        self.cam.location = Vector((eye.at[0], -eye.at[2], eye.at[1]))
        look = (Vector((eye.aim[0], -eye.aim[2], eye.aim[1])) - self.cam.location).normalized()
        self.cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        toward = (self.cam.matrix_world.to_quaternion() @ Vector(impostor.LIGHT).normalized()).normalized()
        for i in range(3):  # the light is fixed to the eye: it moves with it
            self.tone.inputs[i].default_value = toward[i]
        self.scene.render.filepath = self.tmp
        bpy.ops.render.render(write_still=True)
        image = bpy.data.images.load(self.tmp)
        got = np.empty(eye.size[0] * eye.size[1] * 4, dtype=np.float32)
        image.pixels.foreach_get(got)
        bpy.data.images.remove(image)
        return np.round(got.reshape(eye.size[1], eye.size[0], 4) * 255.0).astype(np.uint8)

    def draw(self, eye, line_m):
        """The real model through an eye, its ink line line_m wide on it (metres)."""
        for obj in self.bodies:
            obj.hide_render = False
        for _, piece in self.pieces:
            piece.hide_render = True
        self.ink.outputs[0].default_value = line_m / max(0.1, float(np.linalg.norm(eye.at - self.frames["hips"][:3, 3])))
        return self.shoot(eye)

    def body(self, eye):
        """Where the real model's own surface is, without its ink line."""
        return self.draw(eye, 0.0)[..., 3] > 127

    def draw_pieces(self, eye):
        """Where the rigid pieces cover, through an eye."""
        for obj in self.bodies:
            obj.hide_render = True
        for _, piece in self.pieces:
            piece.hide_render = False
        return self.shoot(eye)[..., 3] > 127


def shrink(mask, rounds=1):
    for _ in range(rounds):
        out = mask.copy()
        out[1:] &= mask[:-1]
        out[:-1] &= mask[1:]
        out[:, 1:] &= mask[:, :-1]
        out[:, :-1] &= mask[:, 1:]
        mask = out
    return mask


def grow(mask, rounds=1):
    return ~shrink(~mask, rounds)


def outside(solid):
    """The pixels not `solid` that can be reached from the picture's edge without crossing it."""
    out = np.zeros_like(solid)
    out[0], out[-1], out[:, 0], out[:, -1] = ~solid[0], ~solid[-1], ~solid[:, 0], ~solid[:, -1]
    while True:
        more = grow(out) & ~solid & ~out
        if not more.any():
            return out
        out |= more


def compare(real, body, cards, inked, joints_px, per_px, k):
    """What the cards show at the joints that the real model does not. real: the model with its ink line; body:
    where its own surface is. k: screen pixels to one of the picture's."""
    a, b = real[..., 3] > 127, cards[..., 3] > 127
    ys, xs = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    zone = np.zeros_like(a)
    for x, y in joints_px:
        zone |= (xs + 0.5 - x) ** 2 + (ys + 0.5 - y) ** 2 < (SEAM_M / per_px) ** 2
    reach = max(1, int(round(0.012 / per_px)))  # a line a centimetre from where the real model has one is the same line
    dark = b & inked & shrink(a, reach + 1) & ~grow(~a | (real[..., :3].max(axis=-1) < DARK), reach)
    open_ = shrink(body, 1) & ~b
    hole = open_ & ~outside(b)
    out = b & ~grow(a, 1)
    wide = max(1, int(round(0.015 / per_px)))
    crack = open_ & shrink(grow(b, wide), wide)  # cards close by on both sides: a gap between two of them, not an edge that fell short
    return {"crack": int(crack.sum()), "body": int(body.sum()), "zone": int((body & zone).sum()), "dark": int(dark.sum()), "dark_zone": int((dark & zone).sum()),
            "open": int(open_.sum()), "open_zone": int((open_ & zone).sum()), "hole": int(hole.sum()), "hole_zone": int((hole & zone).sum()),
            "out": int(out.sum())}, dark, open_, hole


def over_paper(picture):
    cover = picture[..., 3:4].astype(np.float32) / 255.0
    return np.round(picture[..., :3] * cover + np.array(PAPER, dtype=np.float32) * (1.0 - cover)).astype(np.uint8)


def still(path, cards, real, dark, open_, tall=560):
    """Cards, the real model, and the cards with what is wrong marked: side by side, cut to the figure, blown up whole."""
    a = (real[..., 3] > 127) | (cards[..., 3] > 127)
    ys, xs = np.where(a)
    y0, y1, x0, x1 = max(0, ys.min() - 6), min(a.shape[0], ys.max() + 7), max(0, xs.min() - 6), min(a.shape[1], xs.max() + 7)
    times = max(1, tall // (y1 - y0))
    marked = over_paper(cards)
    marked = (marked * 0.45 + np.array(PAPER) * 0.55).astype(np.uint8)
    marked[open_] = (40, 90, 220)
    marked[dark] = (220, 40, 30)
    cuts = [np.repeat(np.repeat(p[y0:y1, x0:x1], times, axis=0), times, axis=1) for p in (over_paper(cards), over_paper(real), marked)]
    gap = np.full((cuts[0].shape[0], 10, 3), 255, dtype=np.uint8)
    impostor.write_png(path, np.concatenate([cuts[0], gap, cuts[1], gap, cuts[2]], axis=1))


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    out = os.path.abspath(flag("--out", "evidence/seams"))
    os.makedirs(out, exist_ok=True)
    tag, which, model = flag("--tag", ""), flag("--sheets", "new"), flag("--model", "detailed")
    runs, shots = os.path.abspath(flag("--runs", os.path.join(REPO, "runs"))), os.path.abspath(flag("--shots", os.path.join(REPO, "shots")))
    take = os.path.join(shots, flag("--take", "crew-candy-shop"))
    times = [float(t) for t in flag("--times", "9,13.5,18,22.5,27,31.5,36,40.5,45,49.5").split(",") if t]
    walk = int(flag("--walk", "6"))
    eyes = flag("--eyes", "crew,close").split(",")
    looks = flag("--looks", "comic,pixel-baked,pixel-both,joe").split(",")
    only = flag("--only", "").split(",") if flag("--only", "") else None
    why = "--why" in args
    try_cut = dict((k, float(v)) for k, v in (pair.split("=") for pair in flag("--try-cut", "").split(",") if pair)) or None
    pieces_only = "--pieces-only" in args
    stills = set(flag("--stills", "").split(",")) - {""}
    with open(os.path.join(take, next(f for f in sorted(os.listdir(take)) if f.startswith("cast-") and f.endswith(".json")))) as f:
        cast = json.load(f)
    with open(os.path.join(REPO, "sets", cast["set"], "set.json")) as f:
        crew = json.load(f)["cameras"]["crew"]
    crew_fov = math.degrees(2.0 * math.atan(36.0 / (16.0 / 9.0) / 2.0 / crew["lens_mm"]))
    impostor.GO_ON = which == "new"  # the page as it was: a search that came down on the side of something gave up
    report = {"take": os.path.basename(take), "sheets": which, "model": model, "size": list(SIZE), "seam_m": SEAM_M, "rows": [], "why": []}
    began = time.time()

    for role, part in cast["roles"].items():
        if only and role not in only:
            continue
        run = part["character"].split("/runs/")[1].split("/")[0]
        profiles = os.path.join(runs, run, "profiles")
        characters = {}
        for look in looks:
            folder = sheet_folder(profiles, model, LOOKS[look][0], which)
            if folder not in characters:
                characters[folder] = impostor.Character(folder)
            characters[look] = characters[folder]
        first = characters[looks[0]].card
        real = Real(os.path.join(profiles, first["source"]), first, try_cut)
        clips = [("dance", impostor.Glb(os.path.join(take, part["glb"])), times, eyes)]
        if walk:
            stride = impostor.Glb(os.path.join(profiles, "%s-walk.glb" % first["plays"]))
            clips.append(("walk", stride, [stride.seconds * i / walk for i in range(walk)], ["quarter"]))
        for clip, motion, moments, clip_eyes in clips:
            for t in moments:
                pose = motion.pose(t)
                hips = pose["hips"][:3, 3]
                real.pose(pose)
                for eye_name in clip_eyes:
                    if eye_name == "crew":
                        at, aim, fov = np.array(crew["at"], dtype=float), np.array(crew["aim"], dtype=float), crew_fov
                    elif eye_name == "close":  # from 2 m, on the crew camera's side of him
                        toward = np.array([crew["at"][0] - hips[0], 0.0, crew["at"][2] - hips[2]])
                        at, aim, fov = hips + CLOSE_M * toward / np.linalg.norm(toward) + np.array([0.0, 0.35, 0.0]), hips + np.array([0.0, 0.1, 0.0]), 36.0
                    else:  # the judge's three-quarter eye
                        a, e = math.radians(35.0), math.radians(12.0)
                        aim = np.array([hips[0], 0.95, hips[2]])
                        at, fov = aim + 4.4 * np.array([math.sin(a) * math.cos(e), math.sin(e), math.cos(a) * math.cos(e)]), 30.0
                    reals, covers, bodies = {}, {}, {}
                    if pieces_only:  # only the cut is being tried: the parts as rigid pieces against the model
                        eye = impostor.Eye(at, aim, fov, SIZE)
                        body, pieces = real.body(eye), real.draw_pieces(eye)
                        report["why"].append({"role": role, "clip": clip, "seconds": round(t, 2), "eye": eye_name, "look": "pieces", "body": int(body.sum()),
                                              "as_drawn": 0, "rigid_pieces": int((shrink(body, 1) & ~pieces).sum()), "rigid_out": int((pieces & ~grow(body, 1)).sum()), "finer_search": 0, "no_wall": 0, "no_cover_test": 0})
                        if "%s@%g:%s" % (role, t, eye_name) in stills:  # grey: both; blue: only the model; red: only the pieces
                            shown = np.full(body.shape + (3,), 250, dtype=np.uint8)
                            shown[body & pieces], shown[body & ~pieces], shown[pieces & ~body] = (205, 200, 195), (40, 90, 220), (220, 40, 30)
                            impostor.write_png(os.path.join(out, "%s-%s-%g-%s-pieces.png" % (tag or which, role, t, eye_name)), shown)
                        continue
                    for look in looks:
                        sheet, k, lines = LOOKS[look]
                        character = characters[look]
                        card = character.card
                        eye = impostor.Eye(at, aim, fov, (SIZE[0] // k, SIZE[1] // k))
                        per_px = eye.m_per_px(hips)
                        if k not in reals:
                            reals[k], bodies[k] = real.draw(eye, per_px if k > 1 else 0.014), real.body(eye)

                        def cards_now(inked=None):
                            who = np.zeros((eye.size[1], eye.size[0]), dtype=np.int32)
                            marked = bool(card.get("line_marked"))
                            picture, depth, _ = impostor.draw(character, pose, eye, line="off" if marked and lines else "shell", who=who, lines=inked)
                            drawn = None
                            if lines == "grid" and marked:
                                drawn = impostor.grid_line(depth, who, eye)
                            elif lines == "bold":
                                drawn = impostor.bold_lines(depth, who if marked else None, eye) & (who > 0)
                            if drawn is not None:
                                picture = impostor.with_lines(picture, drawn)
                                if inked is not None:
                                    inked |= drawn
                            return picture

                        inked = np.zeros((eye.size[1], eye.size[0]), dtype=bool)
                        cards = cards_now(inked)
                        joints, _ = eye.to_pixels(np.array([pose[p["bone"]][:3, 3] for p in character.parts]))
                        row, dark, open_, hole = compare(reals[k], bodies[k], cards, inked, joints, per_px, k)
                        row.update({"role": role, "clip": clip, "seconds": round(t, 2), "eye": eye_name, "look": look, "m_per_px": round(per_px, 4)})
                        report["rows"].append(row)
                        name = "%s@%g:%s" % (role, t, eye_name)
                        if name in stills and clip == "dance":
                            still(os.path.join(out, "%s-%s-%g-%s-%s.png" % (tag or which, role, t, eye_name, look)), cards, reals[k], dark, open_)
                        if why and look in ("comic", "pixel-both"):
                            a = shrink(bodies[k], 1)
                            if k not in covers:
                                covers[k] = real.draw_pieces(eye)
                            said = {"role": role, "clip": clip, "seconds": round(t, 2), "eye": eye_name, "look": look, "body": int(bodies[k].sum()),
                                    "as_drawn": row["open"], "rigid_pieces": int((a & ~covers[k]).sum()), "rigid_out": int((covers[k] & ~grow(bodies[k], 1)).sum())}
                            keep = (impostor.MARCH_PX, impostor.MARCH_MAX, impostor.WALL_M)
                            impostor.MARCH_PX, impostor.MARCH_MAX = keep[0] / 4.0, keep[1] * 4
                            said["finer_search"] = int((a & ~(cards_now()[..., 3] > 127)).sum())
                            impostor.MARCH_PX, impostor.MARCH_MAX, impostor.WALL_M = keep[0], keep[1], 1e9
                            said["no_wall"] = int((a & ~(cards_now()[..., 3] > 127)).sum())
                            impostor.WALL_M = keep[2]
                            cover = character.colour[..., 3].copy()
                            character.colour[..., 3] = character.data[..., 2] > 0.5 / 255.0
                            said["no_cover_test"] = int((a & ~(cards_now()[..., 3] > 127)).sum())
                            character.colour[..., 3] = cover
                            report["why"].append(said)
                print("SEAMS %s %s %.1f s" % (role, clip, t), flush=True)

    # the sums: for every clip, eye and look, a typical frame of one character
    table = {}
    for row in report["rows"]:
        entry = table.setdefault("%s|%s|%s" % (row["clip"], row["eye"], row["look"]), {"frames": 0, "body": 0, "zone": 0, "dark": 0, "dark_zone": 0, "open": 0, "open_zone": 0, "hole": 0, "hole_zone": 0, "out": 0, "crack": 0, "worst_dark": 0, "worst_open": 0, "worst_crack": 0})
        entry["frames"] += 1
        for key in ("body", "zone", "dark", "dark_zone", "open", "open_zone", "hole", "hole_zone", "out", "crack"):
            entry[key] += row[key]
        entry["worst_dark"], entry["worst_open"], entry["worst_crack"] = max(entry["worst_dark"], row["dark"]), max(entry["worst_open"], row["open"]), max(entry["worst_crack"], row["crack"])
    for key, e in table.items():
        e["dark_pct"], e["open_pct"], e["hole_pct"], e["crack_pct"] = (round(100.0 * e[k] / max(1, e["body"]), 3) for k in ("dark", "open", "hole", "crack"))
        print("SEAMS %-28s %3d pictures: line %5.1f px a picture (%.2f%% of the body, worst %d; %.1f at a joint), see-through %5.1f (%.2f%%, worst %d; %.1f at a joint; holes %.1f; between cards %.1f, %.2f%%, worst %d), sticks out %.1f" % (
            key, e["frames"], e["dark"] / e["frames"], e["dark_pct"], e["worst_dark"], e["dark_zone"] / e["frames"], e["open"] / e["frames"], e["open_pct"], e["worst_open"], e["open_zone"] / e["frames"], e["hole"] / e["frames"], e["crack"] / e["frames"], e["crack_pct"], e["worst_crack"], e["out"] / e["frames"]), flush=True)
    report["table"] = table
    causes = {}
    for said in report["why"]:
        entry = causes.setdefault("%s|%s|%s" % (said["clip"], said["eye"], said["look"]), {"frames": 0, "body": 0, "as_drawn": 0, "rigid_pieces": 0, "rigid_out": 0, "finer_search": 0, "no_wall": 0, "no_cover_test": 0})
        entry["frames"] += 1
        for key in ("body", "as_drawn", "rigid_pieces", "rigid_out", "finer_search", "no_wall", "no_cover_test"):
            entry[key] += said[key]
    for key, e in causes.items():
        print("WHY   %-28s see-through pixels a picture: %.1f as drawn; %.1f with the parts as rigid pieces of the model (the cut alone; they stick out %.1f); %.1f with a finer search; %.1f with nothing dropped for being far under the surface; %.1f with no cover test" % (
            key, e["as_drawn"] / e["frames"], e["rigid_pieces"] / e["frames"], e["rigid_out"] / e["frames"], e["finer_search"] / e["frames"], e["no_wall"] / e["frames"], e["no_cover_test"] / e["frames"]), flush=True)
    report["causes"] = causes
    report["seconds"] = round(time.time() - began, 1)
    with open(os.path.join(out, "seams%s.json" % (tag and "-" + tag)), "w") as f:
        json.dump(report, f, indent=1)
    print("RESULT " + json.dumps({"out": out, "seconds": report["seconds"]}))


if __name__ == "__main__":
    main()
