"""Film characters side by side in a background Blender: a short .mp4 and a strip of stills.

    blender -b --factory-startup -P scripts/wardrobe/showcase.py -- OUT_STEM KIND FILE.glb [FILE.glb ...] [--seconds 6] [--size 960x540]

KIND is what they do:
    turn    standing files (profiles/painted.glb): each makes one slow full turn on the spot
    walk    walking files (profiles/painted-walk.glb): each walks its own loop on the spot, over and over
    rom     range-of-motion files (profiles/painted-rom.glb): the whole routine, once

Writes OUT_STEM.mp4 (30 frames a second, H.264) and OUT_STEM-strip.png (twelve stills in order, as one
picture). The look is scripts/motion/render_shot.py's, so these sit beside the shots' films: the same sun and
sky, EEVEE, 960 by 540, a 35 mm lens; a plain floor stands in for a set. Skin that worn gear hides
("body under: ...") is left out, as a game leaves it out. Never touches an open Blender.
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

STRIP = (6, 2)   # stills across, down
APART = 1.9      # metres between two characters standing side by side
# Where the camera stands for each kind: (how far in front, how far to the side, height) as shares of its
# distance, and the distance in metres for one character (each more adds room).
VIEWS = {"turn": ((0.97, 0.08, 0.20), 3.4), "walk": ((0.74, 0.56, 0.24), 4.7), "rom": ((0.86, 0.42, 0.24), 3.7)}
LOOK_HEIGHT = 0.95


def bring_in(path, x):
    """One character from its .glb, set down at x. Returns (what to move to move it, its skeleton or None)."""
    before = set(bpy.data.objects)
    options = {"filepath": path}
    if "disable_bone_shape" in bpy.ops.import_scene.gltf.get_rna_type().properties.keys():
        options["disable_bone_shape"] = True
    bpy.ops.import_scene.gltf(**options)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        if o.type == "MESH" and (o.get("under") or (not o.find_armature() and o.name.startswith("Icosphere"))):
            o.hide_render = True
    stand = bpy.data.objects.new("stand: " + os.path.basename(path), None)
    bpy.context.scene.collection.objects.link(stand)
    for o in new:
        if o.parent is None:
            o.parent = stand
    stand.location = (x, 0.0, 0.0)
    return stand, next((o for o in new if o.type == "ARMATURE"), None)


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    seconds = float(args[args.index("--seconds") + 1]) if "--seconds" in args else 6.0
    wide, tall = (int(v) for v in (args[args.index("--size") + 1] if "--size" in args else "960x540").split("x"))
    for flag in ("--seconds", "--size"):
        if flag in args:
            i = args.index(flag)
            del args[i:i + 2]
    stem, kind, files = os.path.abspath(args[0]), args[1], [os.path.abspath(a) for a in args[2:]]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 30  # before the import, so its keys land one per frame
    cast = [bring_in(path, (n - (len(files) - 1) / 2.0) * APART) for n, path in enumerate(files)]
    frames = int(round(seconds * 30))
    if kind == "turn":
        for stand, rig in cast:
            for f, turn in ((0, 0.0), (frames, 2 * math.pi)):
                stand.rotation_euler = (0.0, 0.0, turn)
                stand.keyframe_insert("rotation_euler", frame=f)
            for curve in stand.animation_data.action.layers[0].strips[0].channelbag(stand.animation_data.action_slot).fcurves:
                for key in curve.keyframe_points:
                    key.interpolation = "LINEAR"
    else:
        longest = 0
        for stand, rig in cast:
            action = rig.animation_data.action
            first, last = action.frame_range
            longest = max(longest, int(round(last - first)))
            if kind == "walk":  # its own loop, again and again for as long as the film runs
                slot = rig.animation_data.action_slot
                track = rig.animation_data.nla_tracks.new()
                strip = track.strips.new(action.name, int(first), action)
                strip.action_slot = slot
                strip.repeat = math.ceil(frames / max(last - first, 1.0)) + 1
                rig.animation_data.action = None
        if kind == "rom":
            frames = longest
    scene.frame_start, scene.frame_end = 0, frames - 1

    floor = bpy.data.meshes.new("floor")
    floor.from_pydata([(-60, -60, 0), (60, -60, 0), (60, 60, 0), (-60, 60, 0)], [], [(0, 1, 2, 3)])
    ground = bpy.data.objects.new("floor", floor)
    paint = bpy.data.materials.new("floor")
    paint.use_nodes = True
    shader = paint.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (0.42, 0.40, 0.37, 1.0)
    shader.inputs["Roughness"].default_value = 0.9
    floor.materials.append(paint)
    scene.collection.objects.link(ground)

    (ahead, aside, up), reach = VIEWS[kind]
    reach += 0.9 * (len(files) - 1)
    cam_data = bpy.data.cameras.new("camera")
    cam_data.lens = 35
    cam = bpy.data.objects.new("camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    eye, look = Vector((aside * reach, -ahead * reach, up * reach + 0.6)), Vector((0.0, 0.0, LOOK_HEIGHT))  # the characters face -y
    cam.location = eye
    cam.rotation_euler = (look - eye).to_track_quat("-Z", "Y").to_euler()

    # the shots' own light: scripts/motion/render_shot.py
    sun_data = bpy.data.lights.new("sun", "SUN")
    sun_data.energy, sun_data.angle = 1.7, math.radians(4)
    sun = bpy.data.objects.new("sun", sun_data)
    sun.rotation_euler = (math.radians(52), 0.0, math.radians(140) + math.pi)
    scene.collection.objects.link(sun)
    world = bpy.data.worlds.new("sky")
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs[0].default_value = (0.36, 0.42, 0.55, 1.0)
    background.inputs[1].default_value = 0.8
    scene.world = world
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "Standard"

    count = STRIP[0] * STRIP[1]
    stills = [round(i * (frames - 1) / (count - 1)) for i in range(count)]
    cell = (wide // 2, tall // 2)
    scene.render.resolution_x, scene.render.resolution_y = cell
    scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"
    sheet = np.zeros((cell[1] * STRIP[1], cell[0] * STRIP[0], 4), dtype=np.float32)
    temp = stem + ".still.png"
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
    out.filepath_raw, out.file_format = stem + "-strip.png", "PNG"
    out.save()
    print("SHOWCASE strip", stem + "-strip.png", "frames", stills)

    scene.render.resolution_x, scene.render.resolution_y = wide, tall
    scene.render.image_settings.media_type = "VIDEO"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.filepath = stem + ".mp4"
    bpy.ops.render.render(animation=True)
    print("SHOWCASE film", stem + ".mp4", frames, "frames")


main()
