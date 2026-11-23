"""One picture of an empty set, for its card in the gallery, in a background Blender.

    Blender -b --factory-startup -P scripts/sets/set_still.py -- <set> [--camera wide] [--out sets/<set>/card.png] [--size 640x360]
                                                                 [--stand <character.glb> <mark> [--second 0.5]]

The set is stood up exactly as it is filmed (its geometry, backdrop, dressing
and lights: scripts/motion/set_contact.py) and looked at through one of its
own cameras: the one named, or its first. A set with no cameras (the rooftop,
whose camera follows the character) is looked at from out front and above.
Never touches an open Blender.

`--stand` puts one character on one of the set's marks for the picture, at the
size its file has, facing the way the mark faces: its clip held at `--second`
(a moment it is standing), its hips over the mark. That is for judging a place
with somebody in it; a set's card is still taken empty.
"""

import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
import set_contact  # noqa: E402
import standing  # noqa: E402


def stand(st, scene, glb, mark_name, second):
    """One character on a mark, still: the clip in its file held at `second`, the hips brought over the mark."""
    m = standing.mark(st, mark_name)
    holder, new = set_contact.bring_in(os.path.abspath(glb), "standing: " + mark_name)
    scene.frame_set(int(round(second * scene.render.fps)))
    bpy.context.view_layer.update()
    rig = set_contact.rig_of(new)
    off = (rig.matrix_world @ rig.pose.bones["hips"].head) if rig and "hips" in rig.pose.bones else holder.location.copy()
    turn = math.radians(m["facing_deg"])
    spot = set_contact.to_blender([standing.stand_spot(m)[0], 0.0, standing.stand_spot(m)[1]])
    holder.rotation_euler = (0.0, 0.0, turn)
    holder.location = (spot.x - (off.x * math.cos(turn) - off.y * math.sin(turn)), spot.y - (off.x * math.sin(turn) + off.y * math.cos(turn)), 0.0)
    print("STILL %s stands on \"%s\"" % (os.path.basename(glb), mark_name))


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    st = standing.load(args[0])
    out = os.path.abspath(args[args.index("--out") + 1]) if "--out" in args else os.path.join(st["dir"], "card.png")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    cameras = set_contact.stand_up(st, scene)
    wanted = args[args.index("--camera") + 1] if "--camera" in args else None
    if "--stand" in args:
        stand(st, scene, args[args.index("--stand") + 1], args[args.index("--stand") + 2], float(args[args.index("--second") + 1]) if "--second" in args else 0.0)
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
    wide, tall = [int(v) for v in (args[args.index("--size") + 1] if "--size" in args else "640x360").split("x")]
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = wide, tall, 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("STILL", out)


main()
