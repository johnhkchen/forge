"""Films a fight on its set, from every one of the set's cameras, in a background Blender.

    Blender -b --factory-startup -P scripts/fight/film_fight.py -- <fight folder>
        [--version lowpoly] [--cameras wide,ringside] [--size 960x540] [--strip-only] [--stills 94,126,507]

The fight folder is what apply_fight.py wrote: fight.json (the timeline, its
hits, the set and the two fight marks) and each fighter's <version>-<side>.glb.
The set is stood up as render_take.py stands it (its geometry, backdrop,
lights and cameras, from set.json), each fighter is put on his fight mark
facing the other, and two things are added that only a fight has, both read
from the timeline's hits:

    camera shake   from the contact frame, through the freeze and a few
                   frames after, the camera is jolted a little and settles:
                   harder for a harder blow
    impact flash   a small bright star at the spot the fist arrives, for
                   three frames: bigger for a harder blow, paler and smaller
                   for a blocked one

It writes, as render_take.py does, one film and one strip of twelve stills
per camera:

    <version>-<camera>.mp4, <version>-<camera>-strip.png    960x540, 30 frames a second, H.264
    films.json                                               what was filmed

--stills renders single frames instead (stills/<camera>-<frame>.png), for
looking closely at a contact frame. Never touches an open Blender.
"""

import json
import math
import os
import random
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
import set_contact  # noqa: E402
import standing  # noqa: E402

STRIP = (6, 2)        # stills across, down
SHAKE_DEG = 0.2       # how far the camera is jolted, in degrees, for a blow of power 1
SHAKE_AFTER = 8       # frames the shake goes on after the freeze ends
FLASH_FRAMES = 3      # how long a flash shows
FLASH_M = (0.13, 0.09)  # a flash's size: this much, and this much more for each point of power
FLASH_NEARER = 0.18   # the flash sits this far toward the camera from the spot, so a head does not hide it


def load(path):
    with open(path) as f:
        return json.load(f)


def strip_and_film(scene, folder, name, frames, size, strip_only):
    """One camera's strip of stills and its film, as render_take.py makes them. Returns {"strip", "mp4"} (file names)."""
    import numpy as np

    wide, tall = size
    count = STRIP[0] * STRIP[1]
    stills = [round(i * (frames - 1) / (count - 1)) for i in range(count)]
    cell = (wide // 2, tall // 2)
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = cell[0], cell[1], 100
    scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"
    sheet = np.zeros((cell[1] * STRIP[1], cell[0] * STRIP[0], 4), dtype=np.float32)
    temp = os.path.join(folder, ".strip-still-%s.png" % name)  # its own name: several cameras may be filmed at once, one Blender each
    for n, frame in enumerate(stills):
        scene.frame_set(frame)
        scene.render.filepath = temp
        bpy.ops.render.render(write_still=True)
        image = bpy.data.images.load(temp)
        pixels = np.array(image.pixels[:], dtype=np.float32).reshape(cell[1], cell[0], 4)
        bpy.data.images.remove(image)
        col, row = n % STRIP[0], STRIP[1] - 1 - n // STRIP[0]
        sheet[row * cell[1]:(row + 1) * cell[1], col * cell[0]:(col + 1) * cell[0]] = pixels
    os.remove(temp)
    out = bpy.data.images.new("strip", cell[0] * STRIP[0], cell[1] * STRIP[1], alpha=True)
    out.pixels.foreach_set(sheet.ravel())
    out.filepath_raw, out.file_format = os.path.join(folder, name + "-strip.png"), "PNG"
    out.save()
    bpy.data.images.remove(out)
    made = {"strip": name + "-strip.png", "strip_frames": stills}
    print("FILM strip", os.path.join(folder, name + "-strip.png"))
    if not strip_only:
        scene.render.resolution_x, scene.render.resolution_y = wide, tall
        scene.render.image_settings.media_type = "VIDEO"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
        scene.render.filepath = os.path.join(folder, name + ".mp4")
        bpy.ops.render.render(animation=True)
        made["mp4"] = name + ".mp4"
        print("FILM film", os.path.join(folder, name + ".mp4"), frames, "frames")
    return made


def shake(cam, hits, frames, seed):
    """Keys the camera's aim on every frame: still, but for a jolt that dies away after each hit."""
    rng = random.Random(seed)
    steady = cam.rotation_euler.copy()
    for f in range(frames):
        up = across = 0.0
        for hit in hits:
            since = f - hit["frame"]
            span = hit["hitstop"] + SHAKE_AFTER
            if 0 <= since < span:
                left = (1.0 - since / float(span)) ** 2
                size = math.radians(SHAKE_DEG * hit["power"]) * left
                up += size * rng.uniform(-1.0, 1.0)
                across += size * rng.uniform(-1.0, 1.0)
        cam.rotation_euler = (steady.x + up, steady.y, steady.z + across)
        cam.keyframe_insert("rotation_euler", frame=f)
    cam.rotation_euler = steady
    return steady


def star(name, color):
    """A flat eight-pointed star, lit from within: long points and short ones, turn about."""
    points = [(0.0, 0.0, 0.0)]
    for i in range(16):
        r = 0.3 if i % 2 else (1.0 if i % 4 == 0 else 0.62)
        a = math.pi * 2.0 * i / 16.0
        points.append((r * math.cos(a), r * math.sin(a), 0.0))
    faces = [(0, 1 + i, 1 + (i + 1) % 16) for i in range(16)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, [], faces)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.remove(nodes["Principled BSDF"])
    glow = nodes.new("ShaderNodeEmission")
    glow.inputs["Color"].default_value = (color[0], color[1], color[2], 1.0)
    glow.inputs["Strength"].default_value = 3.0
    links.new(glow.outputs["Emission"], nodes["Material Output"].inputs["Surface"])
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def flashes(hits):
    """One star per hit, keyed to show for a few frames from contact: it bursts, then shrinks. Returns [(star, the spot)]."""
    made = []
    for n, hit in enumerate(hits):
        obj = star("flash %d" % n, (0.82, 0.9, 1.0) if hit["blocked"] else (1.0, 0.93, 0.62))
        size = FLASH_M[0] + FLASH_M[1] * hit["power"]
        for frame, share in ((hit["frame"] - 1, 0.0), (hit["frame"], 0.75), (hit["frame"] + 1, 1.0), (hit["frame"] + 2, 0.55), (hit["frame"] + FLASH_FRAMES, 0.0)):
            obj.scale = (size * share,) * 3
            obj.keyframe_insert("scale", frame=frame)
        obj.rotation_euler = (0.0, 0.0, 0.0)
        for curve in fcurves_of(obj.animation_data.action):
            for key in curve.keyframe_points:
                key.interpolation = "CONSTANT"
        made.append((obj, set_contact.to_blender(hit["at"]), n))
    return made


def fcurves_of(action):
    curves = []
    if getattr(action, "layers", None):
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    curves += list(bag.fcurves)
    else:
        curves = list(getattr(action, "fcurves", []))
    return curves


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    folder = os.path.abspath(args[0])
    version = args[args.index("--version") + 1] if "--version" in args else "lowpoly"
    size = tuple(int(v) for v in (args[args.index("--size") + 1] if "--size" in args else "960x540").split("x"))
    strip_only = "--strip-only" in args
    stills = [int(v) for v in args[args.index("--stills") + 1].split(",")] if "--stills" in args else None
    timeline = load(os.path.join(folder, "fight.json"))
    if not timeline.get("set"):
        sys.exit("this fight names no set: film_fight.py films on a standing set's own cameras")
    st = standing.load(timeline["set"])
    frames, hits = timeline["frames"], timeline["hits"]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = timeline["fps"]  # before any import, so keys land one per frame
    cameras = set_contact.stand_up(st, scene)
    if "--cameras" in args:
        wanted = args[args.index("--cameras") + 1].split(",")
        cameras = {name: cam for name, cam in cameras.items() if name in wanted}
    if not cameras:
        sys.exit("the set \"%s\" has no cameras to film from" % st["name"])

    # Each fighter on his mark, facing the other. A motion is measured from the floor under the resting hips,
    # so that point, not the file's own origin, is what goes on the mark.
    for side, mark in timeline["marks"].items():
        holder, new = set_contact.bring_in(os.path.join(folder, "%s-%s.glb" % (version, side)), "fighter: " + side,
                                           at=[mark["at"][0], 0.0, mark["at"][1]], heading=mark["facing_deg"])
        rig = set_contact.rig_of(new)
        hips = rig.data.bones["hips"].head_local
        a = math.radians(mark["facing_deg"])
        holder.location.x -= hips.x * math.cos(a) - hips.y * math.sin(a)
        holder.location.y -= hips.x * math.sin(a) + hips.y * math.cos(a)
    scene.frame_start, scene.frame_end = 0, frames - 1
    scene.render.engine = "BLENDER_EEVEE"
    scene.view_settings.view_transform = "Standard"

    stars = flashes(hits)
    made = {}
    for n, (name, cam) in enumerate(cameras.items()):
        steady = shake(cam, hits, frames, seed=7 + n)
        for obj, spot, _ in stars:  # each star faces this camera, a little nearer to it than the spot
            toward = (cam.location - spot).normalized()
            obj.location = spot + toward * FLASH_NEARER
            obj.rotation_euler = steady
        scene.camera = cam
        if stills:
            os.makedirs(os.path.join(folder, "stills"), exist_ok=True)
            scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = size[0], size[1], 100
            scene.render.image_settings.file_format = "PNG"
            for frame in stills:
                scene.frame_set(frame)
                scene.render.filepath = os.path.join(folder, "stills", "%s-%04d.png" % (name, frame))
                bpy.ops.render.render(write_still=True)
                print("FILM still", scene.render.filepath)
            continue
        made[name] = strip_and_film(scene, folder, "%s-%s" % (version, name), frames, size, strip_only)
    if stills:
        return
    listed = load(os.path.join(folder, "films.json")) if os.path.exists(os.path.join(folder, "films.json")) else {}
    listed.setdefault(version, {}).update(made)
    listed["frames"], listed["seconds"], listed["set"] = frames, round(frames / float(timeline["fps"]), 2), st["name"]
    with open(os.path.join(folder, "films.json"), "w") as f:
        json.dump(listed, f, indent=1)


main()
