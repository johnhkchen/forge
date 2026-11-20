"""Renders a shot's raw motion in a background Blender: a short film and a strip of stills.

    Blender -b --factory-startup -P scripts/motion/render_shot.py -- <shot folder> [--strip-only] [--size 960x540]

Opens <shot>/motion.glb (the box mannequin and the set, from to_gltf.py),
lights it, and flies a camera by the shot list's camera cues. Writes
    <shot>/motion.mp4   the whole shot at 30 frames a second
    <shot>/strip.png    twelve stills, in order, as one picture

Never touches an open Blender: it starts from factory settings and exits.
"""

import json
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

STRIP = (6, 2)  # stills across, down
BLEND_FRAMES = 24  # how long the camera takes to move from one cue to the next
# Each view: (how far ahead of the character, how far to its right, height), as shares of the cue's distance.
VIEWS = {
    "three_quarter_tracking": (0.72, 0.62, 0.30),
    "low_three_quarter": (0.74, 0.60, 0.06),
    "side_tracking": (0.10, 0.96, 0.22),
    "front": (0.97, 0.08, 0.24),
}
LOOK_HEIGHT = 0.85


def to_blender(p):
    """glTF (Y up) to Blender (Z up)."""
    return Vector((p[0], -p[2], p[1]))


def smooth(points, reach):
    out = []
    for i in range(len(points)):
        lo, hi = max(0, i - reach), min(len(points), i + reach + 1)
        out.append(tuple(sum(p[a] for p in points[lo:hi]) / (hi - lo) for a in range(3)))
    return out


def camera_track(roots, cues, direction):
    """Camera position and look-at point for every frame, in glTF coordinates."""
    forward = (math.sin(direction), 0.0, math.cos(direction))
    right = (-math.cos(direction), 0.0, math.sin(direction))
    centre = smooth(roots, 12)
    cues = sorted(cues, key=lambda c: c["from_seconds"]) or [{"from_seconds": 0.0, "view": "three_quarter_tracking", "distance_m": 5.0}]

    def offset(cue):
        ahead, side, up = VIEWS[cue["view"]]
        d = float(cue["distance_m"])
        return tuple(forward[a] * ahead * d + right[a] * side * d for a in range(3)), max(0.12, up * d)

    track = []
    for f in range(len(roots)):
        current = [c for c in cues if c["from_seconds"] * 30.0 <= f] or cues[:1]
        cue = current[-1]
        off, height = offset(cue)
        if len(current) > 1:
            t = min(1.0, (f - cue["from_seconds"] * 30.0) / BLEND_FRAMES)
            t = t * t * (3.0 - 2.0 * t)
            old_off, old_height = offset(current[-2])
            off = tuple(old_off[a] + (off[a] - old_off[a]) * t for a in range(3))
            height = old_height + (height - old_height) * t
        c = centre[f]
        track.append(((c[0] + off[0], height, c[2] + off[2]), (c[0], min(c[1], 1.0) * 0.9 + 0.05, c[2])))
    eyes = smooth([t[0] for t in track], 10)
    looks = smooth([t[1] for t in track], 6)
    return list(zip(eyes, looks))


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :]
    shot = os.path.abspath(args[0])
    strip_only = "--strip-only" in args
    wide, tall = (int(v) for v in (args[args.index("--size") + 1] if "--size" in args else "960x540").split("x"))

    with open(os.path.join(shot, "motion.json")) as f:
        motion = json.load(f)
    with open(os.path.join(shot, "plan.json")) as f:
        plan = json.load(f)
    cues = []
    if os.path.exists(os.path.join(shot, "shotlist.json")):
        with open(os.path.join(shot, "shotlist.json")) as f:
            cues = json.load(f).get("camera") or []
    roots = motion["root"]
    frames = len(roots)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(shot, "motion.glb"))
    scene = bpy.context.scene
    scene.render.fps = 30
    scene.frame_start, scene.frame_end = 0, frames - 1

    # The camera looks back along the overall direction of travel.
    route = plan["path"]
    direction = math.atan2(route[-1][0] - route[0][0], route[-1][1] - route[0][1])
    cam_data = bpy.data.cameras.new("shot camera")
    cam_data.lens = 35
    cam = bpy.data.objects.new("shot camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    for f, (eye, look) in enumerate(camera_track(roots, cues, direction)):
        cam.location = to_blender(eye)
        cam.rotation_euler = (to_blender(look) - to_blender(eye)).to_track_quat("-Z", "Y").to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)

    sun_data = bpy.data.lights.new("sun", "SUN")
    sun_data.energy, sun_data.angle = 3.2, math.radians(4)
    sun = bpy.data.objects.new("sun", sun_data)
    sun.rotation_euler = (math.radians(52), 0.0, direction + math.radians(140))
    scene.collection.objects.link(sun)
    world = bpy.data.worlds.new("sky")
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs[0].default_value = (0.86, 0.87, 0.9, 1.0)
    background.inputs[1].default_value = 0.9
    scene.world = world

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = wide, tall, 100
    scene.view_settings.view_transform = "Standard"

    # The strip: stills spread evenly over the shot, tiled left to right, top to bottom.
    count = STRIP[0] * STRIP[1]
    stills = [round(i * (frames - 1) / (count - 1)) for i in range(count)]
    cell = (wide // 2, tall // 2)
    scene.render.resolution_x, scene.render.resolution_y = cell
    scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"
    import numpy as np

    sheet = np.zeros((cell[1] * STRIP[1], cell[0] * STRIP[0], 4), dtype=np.float32)
    temp = os.path.join(shot, ".strip-still.png")
    for n, frame in enumerate(stills):
        scene.frame_set(frame)
        scene.render.filepath = temp
        bpy.ops.render.render(write_still=True)
        image = bpy.data.images.load(temp)
        pixels = np.array(image.pixels[:], dtype=np.float32).reshape(cell[1], cell[0], 4)
        bpy.data.images.remove(image)
        col, row = n % STRIP[0], STRIP[1] - 1 - n // STRIP[0]
        sheet[row * cell[1] : (row + 1) * cell[1], col * cell[0] : (col + 1) * cell[0]] = pixels
    os.remove(temp)
    out = bpy.data.images.new("strip", cell[0] * STRIP[0], cell[1] * STRIP[1], alpha=True)
    out.pixels.foreach_set(sheet.ravel())
    out.filepath_raw, out.file_format = os.path.join(shot, "strip.png"), "PNG"
    out.save()
    print("RENDER strip", os.path.join(shot, "strip.png"), "frames", stills)

    if not strip_only:
        scene.render.resolution_x, scene.render.resolution_y = wide, tall
        scene.render.image_settings.media_type = "VIDEO"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
        scene.render.filepath = os.path.join(shot, "motion.mp4")
        bpy.ops.render.render(animation=True)
        print("RENDER film", os.path.join(shot, "motion.mp4"), frames, "frames")


main()
