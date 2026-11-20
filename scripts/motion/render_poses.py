"""Draws the pose library as one sheet, in a background Blender, so the poses can be looked at.

    Blender -b --factory-startup -P scripts/motion/render_poses.py -- <poses.glb> <sheet.png> [--only name,name]

<poses.glb> comes from `to_gltf.py --poses`: the box mannequin holding one
pose per frame. Each pose is drawn twice, from the front-left and from its
right side, in library order, left to right and top to bottom.
"""

import json
import math
import os
import struct
import sys

import bpy
import numpy as np
from mathutils import Vector

CELL = (300, 380)
PER_ROW = 5
VIEWS = ((35.0, 2.9), (-90.0, 2.9))  # (degrees round from the front, toward the character's left; distance)


def pose_names(path: str) -> list:
    with open(path, "rb") as f:
        f.seek(12)
        size, _ = struct.unpack("<I4s", f.read(8))
        return json.loads(f.read(size)).get("extras", {}).get("poses", [])


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :]
    source, out = os.path.abspath(args[0]), os.path.abspath(args[1])
    names = pose_names(source)
    only = args[args.index("--only") + 1].split(",") if "--only" in args else names
    frames = [i for i, n in enumerate(names) if n in only]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    # The file holds one pose a second; at one frame a second, frame n is pose n.
    bpy.context.scene.render.fps = 1
    bpy.ops.import_scene.gltf(filepath=source)
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=6.0, location=(0.0, 0.0, 0.0))
    floor = bpy.context.object
    mat = bpy.data.materials.new("floor")
    mat.diffuse_color = (0.42, 0.41, 0.39, 1.0)
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.42, 0.41, 0.39, 1.0)
    floor.data.materials.append(mat)

    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    sun_data = bpy.data.lights.new("sun", "SUN")
    sun_data.energy = 1.6
    sun = bpy.data.objects.new("sun", sun_data)
    sun.rotation_euler = (math.radians(50), 0.0, math.radians(30))
    scene.collection.objects.link(sun)
    world = bpy.data.worlds.new("sky")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.56, 0.6, 1.0)
    scene.world = world
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = CELL[0], CELL[1], 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Standard"

    cols = PER_ROW * len(VIEWS)
    rows = math.ceil(len(frames) / PER_ROW)
    sheet = np.ones((rows * CELL[1], cols * CELL[0], 4), dtype=np.float32)
    temp = out + ".cell.png"
    for n, frame in enumerate(frames):
        scene.frame_set(frame)
        for v, (around, distance) in enumerate(VIEWS):
            # glTF's +Z (the character's front) is Blender's -Y; its +X (left) stays +X.
            a = math.radians(around)
            eye = Vector((math.sin(a) * distance, -math.cos(a) * distance, 1.05))
            look = Vector((0.0, 0.0, 0.8))
            cam.location = eye
            cam.rotation_euler = (look - eye).to_track_quat("-Z", "Y").to_euler()
            scene.render.filepath = temp
            bpy.ops.render.render(write_still=True)
            image = bpy.data.images.load(temp)
            pixels = np.array(image.pixels[:], dtype=np.float32).reshape(CELL[1], CELL[0], 4)
            bpy.data.images.remove(image)
            col = (n % PER_ROW) * len(VIEWS) + v
            row = rows - 1 - n // PER_ROW
            sheet[row * CELL[1] : (row + 1) * CELL[1], col * CELL[0] : (col + 1) * CELL[0]] = pixels
    os.remove(temp)
    picture = bpy.data.images.new("sheet", cols * CELL[0], rows * CELL[1], alpha=True)
    picture.pixels.foreach_set(sheet.ravel())
    picture.filepath_raw, picture.file_format = out, "PNG"
    picture.save()
    print("POSES sheet", out, [names[f] for f in frames])


main()
