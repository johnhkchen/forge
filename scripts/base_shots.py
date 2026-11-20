"""Pictures of a base body and the clothes cut for it, to judge the cut by eye.

    blender -b --factory-startup -P scripts/base_shots.py -- BODY.glb OUT.png GARMENT.glb [GARMENT.glb ...] [--votes STEM]

Writes one sheet, OUT.png: the body alone, the clothes alone and both
together, each from the front and from a quarter turn, in their own colors.
With --votes it adds garment.py's three vote renders (STEM-front.png,
STEM-quarter.png, STEM-back.png) as a third row. Everything must be in one
frame: the raw cut (base/body.glb and base/cut/) or the finished pieces
(base/final.glb and garments/). Prints RESULT {json}.
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

SIZE = 700


def bring(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.abspath(path))
    return [o for o in bpy.data.objects if o not in before and o.type == "MESH"]


def shot(scene, camera, mid, turn, shown, everything, path):
    for o in everything:
        o.hide_render = o not in shown
    angle = math.radians(turn)
    camera.location = mid + Vector((5 * math.sin(angle), -5 * math.cos(angle), 0))
    camera.rotation_euler = (math.pi / 2, 0, angle)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def pixels(path, size):
    image = bpy.data.images.load(path)
    if image.size[0] != size or image.size[1] != size:
        image.scale(size, size)
    flat = np.zeros(size * size * 4, dtype=np.float32)
    image.pixels.foreach_get(flat)
    bpy.data.images.remove(image)
    return flat.reshape(size, size, 4)


def main(argv):
    votes = None
    if "--votes" in argv:
        i = argv.index("--votes")
        votes = argv[i + 1]
        del argv[i:i + 2]
    body_path, out = argv[0], os.path.abspath(argv[1])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    body = bring(body_path)
    clothes = [o for path in argv[2:] for o in bring(path)]
    everything = body + clothes
    corners = [o.matrix_world @ Vector(c) for o in everything for c in o.bound_box]
    low = Vector([min(c[i] for c in corners) for i in range(3)])
    high = Vector([max(c[i] for c in corners) for i in range(3)])

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.display.shading.show_specular_highlight = False
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x = scene.render.resolution_y = SIZE
    scene.world = bpy.data.worlds.new("shots")
    scene.world.color = (0.955, 0.94, 0.915)
    camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max(high - low) * 1.06

    stem = os.path.splitext(out)[0]
    rows = []
    for turn, view in ((0, "front"), (45, "quarter")):
        row = []
        for name, shown in (("body", body), ("clothes", clothes), ("both", everything)):
            path = "%s-%s-%s.png" % (stem, name, view)
            shot(scene, camera, (low + high) / 2, turn, shown, everything, path)
            row.append(path)
        rows.append(row)
    if votes:
        rows.append(["%s-%s.png" % (votes, view) for view in ("front", "quarter", "back")])
    sheet = np.concatenate([np.concatenate([pixels(p, SIZE) for p in row], axis=1) for row in reversed(rows)], axis=0)
    image = bpy.data.images.new("sheet", sheet.shape[1], sheet.shape[0], alpha=True)
    image.pixels.foreach_set(sheet.ravel())
    image.filepath_raw = out
    image.file_format = "PNG"
    image.save()
    for row in rows[:2]:
        for path in row:
            os.remove(path)
    print("RESULT " + json.dumps({"sheet": out, "rows": ["front: body, clothes, both", "quarter: body, clothes, both"] + (["votes: front, quarter, back"] if votes else [])}))


main(sys.argv[sys.argv.index("--") + 1:])
