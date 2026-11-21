"""One picture of an empty set, for its card in the gallery, in a background Blender.

    Blender -b --factory-startup -P scripts/sets/set_still.py -- <set> [--camera wide] [--out sets/<set>/card.png]

The set is stood up exactly as it is filmed (its geometry, backdrop, dressing
and lights: scripts/motion/set_contact.py) and looked at through one of its
own cameras: the one named, or its first. A set with no cameras (the rooftop,
whose camera follows the character) is looked at from out front and above.
Never touches an open Blender.
"""

import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
import set_contact  # noqa: E402
import standing  # noqa: E402


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    st = standing.load(args[0])
    out = os.path.abspath(args[args.index("--out") + 1]) if "--out" in args else os.path.join(st["dir"], "card.png")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    cameras = set_contact.stand_up(st, scene)
    wanted = args[args.index("--camera") + 1] if "--camera" in args else None
    if cameras:
        cam = cameras.get(wanted) or next(iter(cameras.values()))
    else:
        lo, hi = standing.placed_bounds(st)
        mid = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
        reach = max(hi[0] - lo[0], hi[2] - lo[2])
        data = bpy.data.cameras.new("out front")
        data.lens = 35.0
        cam = bpy.data.objects.new("out front", data)
        scene.collection.objects.link(cam)
        set_contact.look(cam, [mid[0] + 0.75 * reach, hi[1] + 0.45 * reach, mid[2] - 0.35 * reach], [mid[0], mid[1], mid[2]])
    scene.camera = cam
    scene.render.engine = "BLENDER_EEVEE"
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 640, 360, 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("STILL", out)


main()
