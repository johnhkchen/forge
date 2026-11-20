"""Picture every comic pose on one character, in the comic style, side by side: the way to check a new pose.

    Blender -b --factory-startup -P scripts/comic/pose_sheet.py -- <rigged .glb> <out.png> [pose ...]

Reads motion/comic_poses.json. Prints one POSES line. Blender only; never touches an open Blender.
"""

import math
import os
import sys
import time

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stage  # noqa: E402

CELL = (420, 560)
COLUMNS = 7


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    glb, out, wanted = os.path.abspath(args[0]), os.path.abspath(args[1]), args[2:]
    scene = stage.fresh_scene()
    character = stage.load_character(glb)
    poses = stage.load_poses()
    cam = stage.add_camera(scene, lens=60)
    names = wanted or list(poses)
    tiles = []
    started = time.time()
    for name in names:
        stage.strike(character, poses[name])
        stage.stand_at(character, (0.0, 0.0), 0.0, 0.0)
        points = stage.shape_points(character)
        stage.fit_camera(cam, points, (0.45, -1.0, 0.12), CELL, margin=1.12)
        still = "%s.%s.png" % (out, name)
        stage.run_script("toon.py", {"path": still, "size": list(CELL), "background": [0.96, 0.94, 0.9]})
        image = bpy.data.images.load(still)
        tiles.append(np.array(image.pixels[:], dtype=np.float32).reshape(CELL[1], CELL[0], 4))
        bpy.data.images.remove(image)
        os.remove(still)
    columns = min(len(tiles), COLUMNS)
    rows = math.ceil(len(tiles) / columns)
    sheet = np.ones((rows * CELL[1], columns * CELL[0], 4), dtype=np.float32)
    for i, tile in enumerate(tiles):
        row, column = rows - 1 - i // columns, i % columns
        sheet[row * CELL[1]:(row + 1) * CELL[1], column * CELL[0]:(column + 1) * CELL[0]] = tile
    picture = bpy.data.images.new("poses", columns * CELL[0], rows * CELL[1], alpha=True)
    picture.pixels.foreach_set(sheet.ravel())
    picture.filepath_raw, picture.file_format = out, "PNG"
    picture.save()
    print("POSES", out, "poses", names, "seconds", round(time.time() - started, 1))


main()
