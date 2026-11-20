"""Before and after: each character standing easy, as a plain render and in the comic style, side by side.

    Blender -b --factory-startup -P scripts/comic/style_stills.py -- <out folder> <rigged .glb> [<rigged .glb> ...]
        [--pose stand] [--toon '{"levels": 5}']

Writes <out folder>/<name>.png for each file (name: the run folder's, without its date) and one STILLS line with
the seconds each picture took. Blender only; never touches an open Blender.
"""

import json
import os
import sys
import time

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stage  # noqa: E402

SIZE = (640, 860)
PAPER = [0.96, 0.94, 0.90]


def name_of(glb):
    folder = os.path.basename(os.path.dirname(os.path.dirname(glb)))
    return folder[20:] if len(folder) > 20 and folder[4] == "-" else folder


def plain_light(scene):
    """What the picture looks like with ordinary lamps: a sun from the upper left and a soft sky."""
    sun = bpy.data.objects.new("plain sun", bpy.data.lights.new("plain sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (0.9, 0.0, -0.7)
    scene.collection.objects.link(sun)
    world = bpy.data.worlds.new("plain sky")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = tuple(PAPER) + (1.0,)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    scene.world = world
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "PNG"
    return sun


def pixels(path):
    image = bpy.data.images.load(path)
    wide, tall = image.size
    grid = np.array(image.pixels[:], dtype=np.float32).reshape(tall, wide, 4)
    bpy.data.images.remove(image)
    os.remove(path)
    return grid


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    pose_name, toon = "stand", {}
    if "--pose" in args:
        i = args.index("--pose")
        pose_name = args[i + 1]
        del args[i:i + 2]
    if "--toon" in args:
        i = args.index("--toon")
        toon = json.loads(args[i + 1])
        del args[i:i + 2]
    out = os.path.abspath(args[0])
    os.makedirs(out, exist_ok=True)
    pose = stage.load_poses()[pose_name]
    made = []
    for glb in args[1:]:
        scene = stage.fresh_scene()
        character = stage.load_character(os.path.abspath(glb))
        stage.strike(character, pose)
        stage.stand_at(character, (0.0, 0.0), 0.0, 0.0)
        cam = stage.add_camera(scene, lens=60)
        points = stage.shape_points(character)
        stage.fit_camera(cam, points, (0.42, -1.0, 0.1), SIZE, margin=1.12)
        scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = SIZE[0], SIZE[1], 100
        name = name_of(os.path.abspath(glb))
        still = os.path.join(out, name + ".still.png")
        sun = plain_light(scene)
        started = time.time()
        scene.render.filepath = still
        bpy.ops.render.render(write_still=True)
        plain_seconds = time.time() - started
        before = pixels(still)
        bpy.data.objects.remove(sun)
        started = time.time()
        result = stage.run_script("toon.py", dict({"path": still, "size": list(SIZE), "background": PAPER}, **toon))
        comic_seconds = time.time() - started
        after = pixels(still)
        both = np.concatenate([before, after], axis=1)
        picture = bpy.data.images.new("stills", SIZE[0] * 2, SIZE[1], alpha=True)
        picture.pixels.foreach_set(both.ravel())
        picture.filepath_raw, picture.file_format = os.path.join(out, name + ".png"), "PNG"
        picture.save()
        made.append({"name": name, "file": os.path.join(out, name + ".png"), "plain_s": round(plain_seconds, 2),
                     "comic_s": round(comic_seconds, 2), "materials": result["materials"]})
    print("STILLS " + json.dumps(made))


main()
