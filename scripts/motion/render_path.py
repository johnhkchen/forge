"""Films a cast shot through one of its moving cameras, a picture at a time, at any frame rate, in a background Blender.

    Blender -b --factory-startup -P scripts/motion/render_path.py -- <shot folder> <out folder>
        --camera push_in [--cast groove] [--version midpoly] [--fps 24] [--size 1280x720]
        [--pass shaded|plate|mask|depth] [--from 0] [--to 99999] [--only 0,150,299] [--near 0.5] [--far 12]

render_take.py films a whole shot from every camera at the motion's own 30
frames a second. This one is for a film that goes somewhere else (an AI
restyle, an edit): one camera, at the frame rate asked for, as numbered
pictures (<out>/0000.png, ...) that ffmpeg then makes into a film. A frame at
24 a second falls between two of the motion's, so the character is posed at
that moment exactly (Blender's subframes) and the camera is put where
camera_path.py says it is then, not where the nearest key was.

What is drawn (--pass):

    shaded   the set and the character as render_take.py draws them (EEVEE,
             the set's own lights)
    plate    the same with nobody on the stage: the background alone
    mask     the character white, everything else black
    depth    how far each pixel is from the lens: white at --near metres,
             black at --far and beyond, in a straight line between

The cast is the shot's <version>-<clip>.glb (apply_shot.py), one figure. Prints
PATH lines. Never touches an open Blender.
"""

import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
import camera_path  # noqa: E402
import set_contact  # noqa: E402
import standing  # noqa: E402

PASSES = ("shaded", "plate", "mask", "depth")


def load(path):
    with open(path) as f:
        return json.load(f)


def emission(name, color=None, depth=None):
    """A flat material: one colour, or (depth=(near, far)) the distance from the lens as grey."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.remove(nodes["Principled BSDF"])
    glow = nodes.new("ShaderNodeEmission")
    glow.inputs["Strength"].default_value = 1.0
    if depth:
        view = nodes.new("ShaderNodeCameraData")
        ramp = nodes.new("ShaderNodeMapRange")
        ramp.inputs["From Min"].default_value, ramp.inputs["From Max"].default_value = depth
        ramp.inputs["To Min"].default_value, ramp.inputs["To Max"].default_value = 1.0, 0.0
        ramp.clamp = True
        links.new(view.outputs["View Distance"], ramp.inputs["Value"])
        links.new(ramp.outputs["Result"], glow.inputs["Color"])
    else:
        glow.inputs["Color"].default_value = tuple(color) + (1.0,)
    links.new(glow.outputs["Emission"], nodes["Material Output"].inputs["Surface"])
    return mat


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    shot, out = os.path.abspath(args[0]), os.path.abspath(args[1])
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default  # noqa: E731
    name, clip, version = flag("--camera", ""), flag("--cast", "groove"), flag("--version", "midpoly")
    fps, size, kind = float(flag("--fps", "24")), [int(v) for v in flag("--size", "1280x720").split("x")], flag("--pass", "shaded")
    near, far = float(flag("--near", "0.5")), float(flag("--far", "12"))
    if kind not in PASSES:
        sys.exit("--pass is one of " + ", ".join(PASSES))
    plan = load(os.path.join(shot, "plan.json"))
    paths = plan.get("moving_cameras") or {}
    if name not in paths:
        sys.exit("the shot has no moving camera called \"%s\" (it has: %s)" % (name, ", ".join(paths) or "none"))
    st = standing.load(plan["standing_set"])

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 30  # the motion's own rate, so its keys land one a frame; frames between are subframes
    set_contact.stand_up(st, scene)
    data = bpy.data.cameras.new("camera: " + name)
    data.sensor_width, data.clip_start, data.clip_end = standing.SENSOR_MM, 0.1, 200.0
    cam = bpy.data.objects.new("camera: " + name, data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    figure = []
    if kind != "plate":
        record = load(os.path.join(shot, "%s-%s.json" % (version, clip)))
        grow = 1.0 if record.get("true_size") else 1.0 / record["size_against_soma"]
        _, figure = set_contact.bring_in(os.path.join(shot, "%s-%s.glb" % (version, clip)), "role: dancer", scale=grow)
    scene.render.engine = "BLENDER_EEVEE"
    scene.view_settings.view_transform = "Standard"
    if kind in ("mask", "depth"):
        mine = set(figure)
        if kind == "mask":
            for obj in scene.objects:
                if obj.type in ("MESH", "CURVE") and obj not in mine:
                    obj.hide_render = True
            scene.view_layers[0].material_override = emission("mask white", color=(1.0, 1.0, 1.0))
        else:
            scene.view_layers[0].material_override = emission("depth", depth=(near, far))
        scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.0, 0.0, 0.0, 1.0)
        scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.0
        scene.eevee.taa_render_samples = 1 if kind == "depth" else 16
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = size[0], size[1], 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False

    seconds = (plan["frames"] - 1) / 30.0
    times = camera_path.frames_at(seconds, fps)
    first, last = int(flag("--from", "0")), min(int(flag("--to", "99999")), len(times) - 1)
    os.makedirs(out, exist_ok=True)
    only = [int(v) for v in flag("--only", "").split(",") if v]
    for n in (only or range(first, last + 1)):
        t = times[n]
        whole = int(t * 30.0 + 1e-6)
        scene.frame_set(whole, subframe=t * 30.0 - whole)
        set_contact.place_camera(cam, camera_path.sample(paths[name], t))
        scene.render.filepath = os.path.join(out, "%04d.png" % n)
        bpy.ops.render.render(write_still=True)
        if n % 24 == 0 or n == last:
            print("PATH %s %s frame %d of %d (%.2f s)" % (kind, name, n, len(times) - 1, t), flush=True)
    with open(os.path.join(out, "frames.json"), "w") as f:
        json.dump({"shot": os.path.basename(shot), "camera": name, "pass": kind, "fps": fps, "size": size, "frames": len(times), "seconds": round(seconds, 4),
                   "cast": None if kind == "plate" else "%s-%s.glb" % (version, clip), "depth_near_far_m": [near, far] if kind == "depth" else None}, f, indent=1)
    print("PATH done %s -> %s" % (kind, out))


main()
