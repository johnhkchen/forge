"""Judges a character drawn as flat cards against the real model, with no browser.

    Blender -b --factory-startup -P scripts/impostor/judge_impostor.py -- <impostor folder> --out <folder>
        --clip walk=<walk.glb> [--clip fight=<fight.glb> ...] [--views 26,62] [--eyes front,quarter,side,high]
        [--step 1] [--stills walk:0,7,13] [--film walk:quarter,fight:quarter] [--loops 4] [--no-stretch] [--tag NAME]

For every clip, eye and view set it draws each frame twice: the cards, by impostor.py (the page's own
arithmetic, a pixel at a time), and the real model, by Blender, drawn by toon.py from the same eye in
the same light. The eye stands off the character and goes along with its hips, so it sees a fighter
who crosses the ring as closely as one who walks on the spot. Then it measures:

    outline      how much of the two outlines is shared (1.0 = the same shape), and the worst frame
    colour       how far the colours are apart where both have the character (0..255, a typical pixel)
    gap          the widest place where the real model has body and the cards have none: anywhere, and
                 within 12 cm of a joint (a seam). In cm on the character
    spill        the widest place where the cards stick out past the real model
    pops         how often a part's picture is swapped for another (per second, whole character), and
                 how much of the character's picture changes on a frame when it does

It writes <out>/judge[-tag].json, and when asked:

    <clip>-<eye>-<views>-stills.png     rows of: cards, real model, where they differ (--stills)
    <clip>-<eye>-<views>.mp4            cards beside the real model, playing (--film)
    turn-<views>.mp4                    the eye going once round a figure that stands still (--film turn)

Never touches an open Blender.
"""

import json
import math
import os
import subprocess
import sys
import time

import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import impostor  # noqa: E402

TOON = os.path.join(REPO, ".claude", "skills", "tidy-mesh", "scripts", "toon.py")
FPS = 30
SIZE = (480, 540)
FOV = 30.0
AWAY = 4.4            # how far the eye stands from the character (m)
AIM_UP = 0.95         # the height it looks at
# name: (degrees round from the front, degrees above level)
EYES = {"front": (0.0, 5.0), "quarter": (35.0, 12.0), "side": (90.0, 5.0), "back": (160.0, 10.0), "high": (35.0, 45.0), "low": (-30.0, -12.0)}
SEAM_M = 0.12         # a gap this close to a joint is a seam
PAPER = (250, 248, 245)
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")


def run_toon(**params):
    with open(TOON) as f:
        source = f.read()
    space = {"__name__": "__main__"}
    head, _, tail = source.partition("\nimport ")
    exec(head, space)
    space["PARAMS"].update(params)
    exec("import " + tail, space)


def to_blender(p):
    return Vector((p[0], -p[2], p[1]))


def eye_for(name, hips, turn_deg=None):
    """The eye `name`, standing off the point on the floor under the hips. turn_deg replaces how far round it is."""
    around, above = EYES[name]
    if turn_deg is not None:
        around = turn_deg
    a, e = math.radians(around), math.radians(above)
    aim = np.array([hips[0], AIM_UP, hips[2]])
    at = aim + AWAY * np.array([math.sin(a) * math.cos(e), math.sin(e), math.cos(a) * math.cos(e)])
    return impostor.Eye(at, aim, FOV, SIZE)


class Real:
    """The real model in a background Blender, drawn the comic way."""

    def __init__(self, glb, ink_m):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = bpy.context.scene
        self.scene.render.fps = FPS  # before the import, so keys land one per frame
        bpy.ops.import_scene.gltf(filepath=glb)
        for obj in self.scene.objects:
            if obj.type == "MESH" and (obj.get("under") or not obj.find_armature()):
                obj.hide_render = True
        data = bpy.data.cameras.new("eye")
        data.sensor_fit, data.angle_y, data.clip_start, data.clip_end = "VERTICAL", math.radians(FOV), 0.1, 100.0
        self.cam = bpy.data.objects.new("eye", data)
        self.scene.collection.objects.link(self.cam)
        self.scene.camera = self.cam
        self.scene.render.resolution_x, self.scene.render.resolution_y, self.scene.render.resolution_percentage = SIZE[0], SIZE[1], 100
        self.cam.location = (0.0, -AWAY, AIM_UP)
        # the ink as wide on the character as the cards have it
        run_toon(line_px=ink_m / AWAY * data.lens * max(SIZE) / data.sensor_width, background=None, samples=16, light=list(impostor.LIGHT), shade=[list(s) for s in impostor.SHADE])
        self.scene.render.image_settings.file_format, self.scene.render.image_settings.color_mode = "PNG", "RGBA"
        self.tmp = os.path.join(bpy.app.tempdir, "judge-real.png")
        self.tone = bpy.data.node_groups["comic tone"].nodes["Light"]

    def draw(self, eye, frame):
        self.cam.location = to_blender(eye.at)
        look = (to_blender(eye.aim) - self.cam.location).normalized()
        self.cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
        self.scene.frame_set(frame)
        bpy.context.view_layer.update()
        toward = (self.cam.matrix_world.to_quaternion() @ Vector(impostor.LIGHT).normalized()).normalized()
        for i in range(3):  # the light is fixed to the eye: move it with the eye
            self.tone.inputs[i].default_value = toward[i]
        self.scene.render.filepath = self.tmp
        bpy.ops.render.render(write_still=True)
        image = bpy.data.images.load(self.tmp)
        got = np.empty(SIZE[0] * SIZE[1] * 4, dtype=np.float32)
        image.pixels.foreach_get(got)
        bpy.data.images.remove(image)
        return np.round(got.reshape(SIZE[1], SIZE[0], 4) * 255.0).astype(np.uint8)


def shrink(mask):
    out = mask.copy()
    out[1:] &= mask[:-1]
    out[:-1] &= mask[1:]
    out[:, 1:] &= mask[:, :-1]
    out[:, :-1] &= mask[:, 1:]
    out[0] = out[-1] = False
    out[:, 0] = out[:, -1] = False
    return out


def widest(mask, where=None):
    """The width in pixels of the widest place of a mask (inside `where`, if given): how many times it can be
    shrunk by a pixel all round before nothing is left."""
    rounds = 0
    while (mask & where).any() if where is not None else mask.any():
        mask = shrink(mask)
        rounds += 1
    return max(0, 2 * rounds - 1)


def compare(real, cards, joints_px, per_px):
    a, b = real[..., 3] > 127, cards[..., 3] > 127
    both, either = a & b, a | b
    ys, xs = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    near = np.zeros_like(a)
    for x, y in joints_px:
        near |= (xs + 0.5 - x) ** 2 + (ys + 0.5 - y) ** 2 < (SEAM_M / per_px) ** 2
    gap, spill = a & ~b, b & ~a
    apart = np.abs(real[..., :3].astype(np.int32) - cards[..., :3].astype(np.int32)).mean(axis=-1)
    return {
        "outline": float(both.sum()) / max(1, int(either.sum())),
        "colour": float(apart[both].mean()) if both.any() else 0.0,
        "gap_cm": widest(gap) * per_px * 100.0, "seam_cm": widest(gap, near) * per_px * 100.0,
        "spill_cm": widest(spill) * per_px * 100.0,
        "gap_pct": 100.0 * gap.sum() / max(1, int(a.sum())), "spill_pct": 100.0 * spill.sum() / max(1, int(a.sum())),
    }


def over_paper(picture):
    cover = picture[..., 3:4].astype(np.float32) / 255.0
    return np.round(picture[..., :3] * cover + np.array(PAPER, dtype=np.float32) * (1.0 - cover)).astype(np.uint8)


def differ(real, cards):
    """Where the two differ: body only the real model has in red, only the cards in blue, a clear change of colour in grey."""
    a, b = real[..., 3] > 127, cards[..., 3] > 127
    out = np.empty(a.shape + (3,), dtype=np.uint8)
    out[:] = PAPER
    apart = np.abs(real[..., :3].astype(np.int32) - cards[..., :3].astype(np.int32)).max(axis=-1)
    out[a & b] = (232, 228, 222)
    out[a & b & (apart > 60)] = (150, 146, 140)
    out[a & ~b] = (200, 60, 50)
    out[b & ~a] = (68, 103, 155)
    return out


def label_strip(words, wide, tall=30):
    """A strip of paper with words on it, drawn by Blender (rows from the bottom up). Made once per wording."""
    key = (tuple(words), wide)
    if key in label_strip.made:
        return label_strip.made[key]
    scene = bpy.data.scenes.new("labels")
    data = bpy.data.cameras.new("label eye")
    data.type, data.ortho_scale = "ORTHO", float(wide)
    cam = bpy.data.objects.new("label eye", data)
    scene.collection.objects.link(cam)
    cam.location = (wide / 2.0, tall / 2.0, 10.0)
    scene.camera = cam
    ink = bpy.data.materials.new("label ink")
    ink.use_nodes = True
    ink.node_tree.nodes.clear()
    glow, out = ink.node_tree.nodes.new("ShaderNodeEmission"), ink.node_tree.nodes.new("ShaderNodeOutputMaterial")
    glow.inputs["Color"].default_value = (0.012, 0.01, 0.009, 1.0)
    ink.node_tree.links.new(glow.outputs[0], out.inputs["Surface"])
    each = wide / float(len(words))
    for i, word in enumerate(words):
        curve = bpy.data.curves.new("label", "FONT")
        curve.body, curve.size, curve.align_x, curve.align_y = word, 15.0, "CENTER", "CENTER"
        curve.materials.append(ink)
        text = bpy.data.objects.new("label", curve)
        scene.collection.objects.link(text)
        text.location = (each * (i + 0.5), tall / 2.0, 0.0)
    world = bpy.data.worlds.new("paper")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = tuple((c / 255.0) ** 2.2 for c in PAPER) + (1.0,)
    scene.world = world
    scene.render.engine = "BLENDER_EEVEE"
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = wide, tall, 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = os.path.join(bpy.app.tempdir, "judge-label.png")
    bpy.ops.render.render(write_still=True, scene=scene.name)
    image = bpy.data.images.load(scene.render.filepath)
    got = np.empty(wide * tall * 4, dtype=np.float32)
    image.pixels.foreach_get(got)
    bpy.data.images.remove(image)
    bpy.data.scenes.remove(scene)
    strip = np.round(got.reshape(tall, wide, 4)[..., :3] * 255.0).astype(np.uint8)
    label_strip.made[key] = strip
    return strip


label_strip.made = {}


class Film:
    """Frames (rows from the bottom up, RGB) piped to ffmpeg as an H.264 .mp4."""

    def __init__(self, path, wide, tall):
        self.path = path
        self.pipe = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (wide, tall), "-r", str(FPS), "-i", "-",
                                      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", path], stdin=subprocess.PIPE)

    def add(self, frame):
        self.pipe.stdin.write(np.ascontiguousarray(frame[::-1]).tobytes())

    def close(self):
        self.pipe.stdin.close()
        self.pipe.wait()


def pop_sizes(character, pose, eye, before, after, stretch):
    """For the parts whose view changed between two frames: how many pixels of the picture change if only the
    view is swapped (the pose and the eye held at the later frame)."""
    changed = 0
    for name in after:
        if name not in before or before[name]["view"] == after[name]["view"]:
            continue
        old, _, _ = impostor.draw(character, pose, eye, stretch=stretch, only=[name], forced={name: before[name]["view"]})
        new, _, _ = impostor.draw(character, pose, eye, stretch=stretch, only=[name], forced={name: after[name]["view"]})
        a, b = old[..., 3] > 127, new[..., 3] > 127
        apart = np.abs(old[..., :3].astype(np.int32) - new[..., :3].astype(np.int32)).max(axis=-1)
        changed += int((a ^ b).sum() + (a & b & (apart > 40)).sum())
    return changed


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    folder = os.path.abspath(args[0])
    out = os.path.abspath(flag("--out", os.path.join(folder, "judge")))
    os.makedirs(out, exist_ok=True)
    clips = dict(pair.split("=", 1) for pair in [args[i + 1] for i, a in enumerate(args) if a == "--clip"])
    eyes = flag("--eyes", "front,quarter,side,high").split(",")
    step = int(flag("--step", "1"))
    loops = int(flag("--loops", "4"))
    stretch = "--no-stretch" not in args
    tag = flag("--tag", "")
    stills = dict((pair.split(":")[0], [int(v) for v in pair.split(":")[1].split(",")]) for pair in flag("--stills", "").split(";") if pair)
    films = [pair.split(":") for pair in flag("--film", "").split(",") if pair]
    character = impostor.Character(folder)
    sets = flag("--views", ",".join(character.card["sets"])).split(",")
    report = {"folder": folder, "size": list(SIZE), "eye_away_m": AWAY, "stretch": stretch, "clips": {}}
    began = time.time()

    for clip, glb in clips.items():
        motion = impostor.Glb(glb)
        real = Real(glb, character.card["ink_m"])
        frames = int(round(motion.seconds * FPS)) + 1
        measured = list(range(0, frames, step))
        poses = {f: motion.pose(f / float(FPS)) for f in range(frames)}
        hips = {f: poses[f]["hips"][:3, 3] for f in poses}
        heads = [p["bone"] for p in character.parts]
        entry = report["clips"][clip] = {"glb": glb, "frames": frames, "seconds": round(motion.seconds, 2), "triangles": motion.triangles(), "eyes": {}}
        for eye_name in eyes:
            reals = {}
            for set_name in sets:
                character.use(set_name)
                rows, last, swaps, jumps = [], None, 0, []
                for f in range(frames):
                    eye = eye_for(eye_name, hips[f])
                    if f in measured:
                        if f not in reals:
                            reals[f] = real.draw(eye, f)
                        cards, _, said = impostor.draw(character, poses[f], eye, stretch=stretch)
                        joints, _ = eye.to_pixels(np.array([poses[f][b][:3, 3] for b in heads]))
                        rows.append(compare(reals[f], cards, joints, eye.m_per_px(eye.aim)))
                        body = int((cards[..., 3] > 127).sum())
                    else:
                        said = {p["name"]: {"view": impostor.choose(character.dirs, impostor.eye_in_bone(poses[f][p["bone"]], p["center"], eye.at))[0]} for p in character.parts}
                    if last is not None:
                        changed = sum(1 for n in said if said[n]["view"] != last[n]["view"])
                        swaps += changed
                        if changed and f in measured:
                            jumps.append(100.0 * pop_sizes(character, poses[f], eye, last, said, stretch) / max(1, body))
                    last = said
                col = lambda key: [r[key] for r in rows]
                entry["eyes"].setdefault(eye_name, {})[set_name] = {
                    "frames_measured": len(rows),
                    "outline": round(float(np.mean(col("outline"))), 4), "outline_worst": round(float(np.min(col("outline"))), 4),
                    "colour": round(float(np.mean(col("colour"))), 1),
                    "gap_cm": round(float(np.mean(col("gap_cm"))), 2), "gap_cm_worst": round(float(np.max(col("gap_cm"))), 2),
                    "seam_cm": round(float(np.mean(col("seam_cm"))), 2), "seam_cm_worst": round(float(np.max(col("seam_cm"))), 2),
                    "spill_cm": round(float(np.mean(col("spill_cm"))), 2), "spill_cm_worst": round(float(np.max(col("spill_cm"))), 2),
                    "gap_pct": round(float(np.mean(col("gap_pct"))), 2), "spill_pct": round(float(np.mean(col("spill_pct"))), 2),
                    "pops_per_s": round(swaps / max(motion.seconds, 1e-6), 2),
                    "pop_pct": round(float(np.mean(jumps)), 2) if jumps else 0.0, "pop_pct_worst": round(float(np.max(jumps)), 2) if jumps else 0.0,
                }
                print("JUDGE %s %s views %s: %s" % (clip, eye_name, set_name, json.dumps(entry["eyes"][eye_name][set_name])), flush=True)

                if clip in stills and eye_name == flag("--stills-eye", "quarter"):
                    picked = stills[clip]
                    wide, tall = SIZE
                    sheet = np.empty((tall * len(picked) + 30, wide * 3, 3), dtype=np.uint8)
                    sheet[:] = PAPER
                    sheet[tall * len(picked):] = label_strip(["Flat cards", "Real 3D model", "Where they differ"], wide * 3)
                    for row, f in enumerate(picked):
                        eye = eye_for(eye_name, hips[f])
                        shot = reals.get(f)
                        if shot is None:
                            shot = real.draw(eye, f)
                        cards, _, _ = impostor.draw(character, poses[f], eye, stretch=stretch)
                        y = tall * (len(picked) - 1 - row)
                        sheet[y:y + tall, :wide] = over_paper(cards)
                        sheet[y:y + tall, wide:2 * wide] = over_paper(shot)
                        sheet[y:y + tall, 2 * wide:] = differ(shot, cards)
                    path = os.path.join(out, "%s-%s-%s%s-stills.png" % (clip, eye_name, set_name, tag and "-" + tag))
                    impostor.write_png(path, sheet)
                    print("JUDGE stills", path, flush=True)

            for film_clip, film_eye in films:
                if film_clip != clip or film_eye != eye_name:
                    continue
                for set_name in sets:
                    character.use(set_name)
                    wide, tall = SIZE
                    path = os.path.join(out, "%s-%s-%s%s.mp4" % (clip, eye_name, set_name, tag and "-" + tag))
                    film = Film(path, wide * 2, tall + 30)
                    strip = label_strip(["Flat cards (%s pictures a part)" % set_name, "Real 3D model"], wide * 2)
                    made = []
                    for f in range(frames):
                        eye = eye_for(eye_name, hips[f])
                        if f not in reals:
                            reals[f] = real.draw(eye, f)
                        cards, _, _ = impostor.draw(character, poses[f], eye, stretch=stretch)
                        frame = np.concatenate([strip, np.concatenate([over_paper(cards), over_paper(reals[f])], axis=1)], axis=0)
                        made.append(frame)
                    for _ in range(loops if frames < 120 else 1):
                        for frame in made:
                            film.add(frame)
                    film.close()
                    print("JUDGE film", path, flush=True)

        # The eye going once round the figure as it stands at one frame: every swap here is the eye's doing.
        if ("turn", clip) in [tuple(f) for f in films] or flag("--turn", "") == clip:
            f0 = int(flag("--turn-frame", "0"))
            for set_name in sets:
                character.use(set_name)
                wide, tall = SIZE
                path = os.path.join(out, "turn-%s-%s%s.mp4" % (clip, set_name, tag and "-" + tag))
                film = Film(path, wide * 2, tall + 30)
                strip = label_strip(["Flat cards (%s pictures a part)" % set_name, "Real 3D model"], wide * 2)
                last, swaps, jumps, rows = None, 0, [], []
                for deg in range(0, 360, 2):
                    eye = eye_for("quarter", hips[f0], turn_deg=float(deg))
                    shot = real.draw(eye, f0)
                    cards, _, said = impostor.draw(character, poses[f0], eye, stretch=stretch)
                    joints, _ = eye.to_pixels(np.array([poses[f0][b][:3, 3] for b in heads]))
                    rows.append(compare(shot, cards, joints, eye.m_per_px(eye.aim)))
                    if last is not None:
                        changed = sum(1 for n in said if said[n]["view"] != last[n]["view"])
                        swaps += changed
                        if changed:
                            jumps.append(100.0 * pop_sizes(character, poses[f0], eye, last, said, stretch) / max(1, int((cards[..., 3] > 127).sum())))
                    last = said
                    film.add(np.concatenate([strip, np.concatenate([over_paper(cards), over_paper(shot)], axis=1)], axis=0))
                film.close()
                entry.setdefault("turn", {})[set_name] = {
                    "frame": f0, "swaps_in_one_turn": swaps, "pop_pct": round(float(np.mean(jumps)), 2) if jumps else 0.0,
                    "pop_pct_worst": round(float(np.max(jumps)), 2) if jumps else 0.0,
                    "outline": round(float(np.mean([r["outline"] for r in rows])), 4), "outline_worst": round(float(np.min([r["outline"] for r in rows])), 4),
                    "seam_cm_worst": round(float(np.max([r["seam_cm"] for r in rows])), 2), "colour": round(float(np.mean([r["colour"] for r in rows])), 1),
                }
                print("JUDGE turn %s views %s: %s" % (clip, set_name, json.dumps(entry["turn"][set_name])), flush=True)
                print("JUDGE film", path, flush=True)

    report["seconds"] = round(time.time() - began, 1)
    with open(os.path.join(out, "judge%s.json" % (tag and "-" + tag)), "w") as f:
        json.dump(report, f, indent=1)
    print("RESULT " + json.dumps({"out": out, "seconds": report["seconds"]}))


main()
