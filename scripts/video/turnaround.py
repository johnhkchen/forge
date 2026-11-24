"""A character from the front, the side, the back and three-quarters, on plain grey, in a background Blender.

    Blender -b --factory-startup -P scripts/video/turnaround.py -- <file.glb> <out folder> [--size 1024]
        [--views front,side,back,quarter] [--grey 0.741]

For a model sheet, the reference pictures an AI video model is shown: the
run's own picture is the front, and nothing else shows her side or back. So
the detailed mesh (final.glb, the picture's own colours) is stood up and
pictured without perspective from each side, evenly lit, the whole figure
filling the height, on the same grey as the run's picture. Writes
<out>/<view>.png. Prints TURN lines. Never touches an open Blender.
"""

import math
import os
import sys

import bpy
from mathutils import Vector

VIEWS = {"front": 0.0, "quarter": 35.0, "side": 90.0, "back": 180.0}  # degrees the camera goes round, from the front toward her left


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    glb, out = os.path.abspath(args[0]), os.path.abspath(args[1])
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default  # noqa: E731
    size, grey = int(flag("--size", "1024")), float(flag("--grey", "0.741"))
    views = flag("--views", "front,side,back,quarter").split(",")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.import_scene.gltf(filepath=glb)
    meshes = [o for o in scene.objects if o.type == "MESH" and not o.get("under")]
    for o in scene.objects:
        if o.type == "MESH" and o.get("under"):
            o.hide_render = True
    bpy.context.view_layer.update()
    corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector([min(c[i] for c in corners) for i in range(3)])
    hi = Vector([max(c[i] for c in corners) for i in range(3)])
    middle, tall, wide = (lo + hi) / 2.0, hi.z - lo.z, max(hi.x - lo.x, hi.y - lo.y)

    world = bpy.data.worlds.new("grey")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0  # even light from all round, as a picture on grey is lit
    scene.world = world
    sun = bpy.data.objects.new("key", bpy.data.lights.new("key", "SUN"))
    sun.data.energy, sun.data.angle = 1.6, math.radians(20)
    sun.rotation_euler = (math.radians(50), 0.0, math.radians(-30))
    scene.collection.objects.link(sun)
    scene.render.engine = "BLENDER_EEVEE"
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.film_transparent = True
    scene.render.image_settings.file_format, scene.render.image_settings.color_mode = "PNG", "RGBA"
    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    cam.data.type, cam.data.ortho_scale = "ORTHO", max(tall, wide) * 1.06
    scene.collection.objects.link(cam)
    scene.camera = cam
    os.makedirs(out, exist_ok=True)
    # The figure faces -y (a glTF faces +z); the camera goes round from in front of her.
    for name in views:
        turn = math.radians(VIEWS[name])
        away = Vector((math.sin(turn), -math.cos(turn), 0.0)) * (tall * 4.0)
        cam.location = middle + away
        cam.rotation_euler = (-away).to_track_quat("-Z", "Y").to_euler()
        path = os.path.join(out, name + "-clear.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        # onto the grey the run's picture stands on
        picture = bpy.data.images.load(path)
        px = list(picture.pixels[:])
        for i in range(0, len(px), 4):
            a = px[i + 3]
            for k in range(3):
                px[i + k] = px[i + k] * a + grey * (1.0 - a)
            px[i + 3] = 1.0
        flat = bpy.data.images.new(name, size, size, alpha=False)
        flat.pixels.foreach_set(px)
        flat.filepath_raw, flat.file_format = os.path.join(out, name + ".png"), "PNG"
        flat.save()
        os.remove(path)
        print("TURN %s -> %s" % (name, os.path.join(out, name + ".png")), flush=True)


main()
