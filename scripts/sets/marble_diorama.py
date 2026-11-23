"""A Marble room as a diorama: clean pictures from high up at three quarters, on a plain background, in a background Blender.

    Blender -b --factory-startup -P scripts/sets/marble_diorama.py -- <set> <world folder> [--out evidence/marble/diorama] [--splats full_res] [--size 1536]
    (`just marble-diorama <set> <world folder>`, which also takes the splat pictures)

These are the pictures for the round trip Marble -> picture -> Codex tidying
it -> TRELLIS -> a mesh that should still be the same room
(scripts/sets/fit_to_marble.py measures that). TRELLIS wants one object, whole,
on a plain background, seen from outside. A room seen from outside is a box,
so it is opened the way a doll's house is:

    the ceiling comes off, and what hangs from it (lanterns) with it;
    the walls on the camera's side come off: a wall goes when it faces away
    from the camera, which is what the nearest part of the collision mesh says.

For every view it writes

    <out>/<set>-<view>-mesh.png     the painted mesh (set.glb), opened, through that camera
    <out>/cut/<set>-<view>.spz      the world's splats with the same parts taken away
                                    (kept out of git: the gallery draws them, see below)
    <out>/views.json                each view's camera, and what to open in the gallery

and `python3 scripts/sets/marble_shots.py <set> --views <out>/views.json` then
has the gallery draw each cut .spz through the same camera and saves
<set>-<view>-splats.png beside the mesh picture. Nothing is sent anywhere.

Views are named by where the camera stands: front (the set's +z side), back,
left (-x) and right, so front-left looks in over the front-left corner.
"""

from __future__ import annotations

import json
import math
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
import fit_to_marble  # noqa: E402
import from_marble  # noqa: E402
import set_contact  # noqa: E402

# name: (degrees round from the front, toward +x; degrees up)
VIEWS = {"front": (0.0, 42.0), "front-right": (38.0, 36.0), "front-left": (-38.0, 36.0), "back-right": (142.0, 36.0), "back-left": (-142.0, 36.0)}
LENS_MM = 70.0
HANGS_FROM = 0.6  # share of the room's height above which something well inside the room is hanging from the ceiling
PAPER = (1.0, 1.0, 1.0)


def camera_for(lo, hi, round_deg, up_deg):
    """Where a camera stands to hold the whole room: (at, aim, lens)."""
    aim = [(lo[0] + hi[0]) / 2.0, lo[1] + 0.3 * (hi[1] - lo[1]), (lo[2] + hi[2]) / 2.0]
    a, e = math.radians(round_deg), math.radians(up_deg)
    toward = np.array([math.sin(a) * math.cos(e), math.sin(e), math.cos(a) * math.cos(e)])
    ahead = -toward
    right = np.cross(ahead, [0.0, 1.0, 0.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, ahead)
    half = math.atan(18.0 / LENS_MM) * 0.9  # a little air round it
    far = 0.0
    for x in (lo[0], hi[0]):
        for y in (lo[1], lo[1] + 0.75 * (hi[1] - lo[1])):
            for z in (lo[2], hi[2]):
                d = np.array([x, y, z]) - aim
                far = max(far, max(abs(d @ right), abs(d @ up)) / math.tan(half) - d @ ahead)
    return [round(float(v), 3) for v in np.array(aim) + toward * far], [round(float(v), 3) for v in aim], LENS_MM


def opened(points, normal, part, lo, hi, eye, aim):
    """Which points stay when the room is opened toward a camera. `part` and `normal` are the room's, at each point."""
    look = np.array(aim, float) - np.array(eye, float)
    look /= np.linalg.norm(look)
    tall = hi[1] - lo[1]
    from_edge = np.minimum(np.minimum(points[:, 0] - lo[0], hi[0] - points[:, 0]), np.minimum(points[:, 2] - lo[2], hi[2] - points[:, 2]))
    ceiling = part == fit_to_marble.PARTS.index("ceiling")
    wall = part == fit_to_marble.PARTS.index("walls")
    hanging = (points[:, 1] > lo[1] + HANGS_FROM * tall) & (from_edge > fit_to_marble.EDGE)
    away = normal @ look > 0.05
    outside = (from_edge < -0.35) | (points[:, 1] < lo[1] - 0.15) | (points[:, 1] > hi[1] + 0.1)
    return ~(ceiling | hanging | (wall & away) | outside)


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    opt = lambda flag, default: args[args.index(flag) + 1] if flag in args else default
    named = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or not args[i - 1].startswith("--"))]
    if len(named) != 2:
        sys.exit(__doc__.split("\n\n")[1])
    set_dir = os.path.join(REPO, "sets", named[0])
    with open(os.path.join(set_dir, "set.json")) as f:
        st = json.load(f)
    folder, name = os.path.abspath(named[1]), st["name"]
    out = os.path.abspath(opt("--out", os.path.join(REPO, "evidence", "marble", "diorama")))
    size, detail = int(opt("--size", "1536")), opt("--splats", "full_res")
    os.makedirs(os.path.join(out, "cut"), exist_ok=True)

    corners, triangles = from_marble.read_glb(os.path.join(set_dir, st["geometry"]["glb"]))
    normal, _ = from_marble.normals_of(corners, triangles)
    part = fit_to_marble.parts_of(corners, triangles)
    middle = corners[triangles].mean(axis=1)
    lo, hi = np.percentile(corners, 0.2, axis=0), np.percentile(corners, 99.8, axis=0)
    # Most of a collision mesh faces into its room; a triangle that faces out of it is turned to agree.
    inward = (np.array([(lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, (lo[2] + hi[2]) / 2.0]) - middle)
    shell = np.isin(part, [fit_to_marble.PARTS.index("walls"), fit_to_marble.PARTS.index("ceiling")])
    normal[shell & ((normal * inward).sum(axis=1) < 0)] *= -1.0

    # Each splat takes its part of the room from the triangle nearest to it.
    spz = from_marble.read_spz(os.path.join(folder, st["marble"]["splats"][detail]))
    at = from_marble.into_set(spz["at"], st["marble"])
    which, _ = from_marble.nearest(middle, at, 1)
    which = which[:, 0]

    # The painted mesh, in Blender, shown as it is: no lamps, a plain white world.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.import_scene.gltf(filepath=os.path.join(set_dir, st["geometry"]["glb"]))
    room = next(o for o in scene.objects if o.type == "MESH")
    faces = np.zeros(len(room.data.polygons) * 3)
    room.data.polygons.foreach_get("center", faces)
    faces = faces.reshape(-1, 3)
    faces = np.stack([faces[:, 0], faces[:, 2], -faces[:, 1]], axis=1)  # Blender's z up, back to the set's y up
    face_of, _ = from_marble.nearest(middle, faces, 1)  # the importer keeps the order, but nothing promises it
    face_of = face_of[:, 0]
    world = bpy.data.worlds.new("paper")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = PAPER + (1.0,)
    scene.world = world
    scene.render.engine = "BLENDER_EEVEE"
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    data = bpy.data.cameras.new("diorama")
    data.sensor_width, data.clip_start, data.clip_end = 36.0, 0.5, 400.0
    cam = bpy.data.objects.new("diorama", data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    views = {}
    for view, (round_deg, up_deg) in VIEWS.items():
        eye, aim, lens = camera_for(lo, hi, round_deg, up_deg)
        data.lens = lens
        set_contact.look(cam, eye, aim)
        keep = opened(middle[face_of], normal[face_of], part[face_of], lo, hi, eye, aim)
        room.data.polygons.foreach_set("hide", (~keep).tolist())
        room.data.update()
        picture = os.path.join(out, "%s-%s-mesh.png" % (name, view))
        scene.render.filepath = picture
        bpy.ops.render.render(write_still=True)
        kept = opened(at, normal[which], part[which], lo, hi, eye, aim) & (spz["alpha"] > 0.02)
        cut = os.path.join(out, "cut", "%s-%s.spz" % (name, view))
        count = from_marble.write_spz(cut, spz, kept)
        rel = os.path.relpath(cut, REPO)
        views[view] = {"at": eye, "aim": aim, "lens_mm": lens, "size": size, "mesh": os.path.basename(picture), "splats": "%s-%s-splats.png" % (name, view), "cut": rel, "kept_splats": count,
                       "open": "?file=/%s&bare=1&who=0&clear=ffffff&cam=%s" % (rel, ",".join(str(v) for v in eye + aim + [lens]))}
        print("DIORAMA %s: %s, and %d of %d splats kept in %s" % (view, os.path.relpath(picture, REPO), count, spz["count"], rel))
    with open(os.path.join(out, "views.json"), "w") as f:
        json.dump({"set": name, "about": "The room opened like a doll's house, once per view: the ceiling and what hangs from it off, and the walls on the camera's side. `open` is what follows #/marble/<set> in the gallery to see the cut splats through the same camera.",
                   "views": views}, f, indent=1)
        f.write("\n")


main()
