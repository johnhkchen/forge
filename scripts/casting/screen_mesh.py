"""The mesh screen's free half: a TRELLIS.2 mesh stood up, sized and pictured from all round, before anyone pays for a
take. Background Blender only; never touches an open Blender.

    Blender -b --factory-startup -P scripts/casting/screen_mesh.py -- <run>/mesh.glb <out dir> <height m> [--crew-px-per-m 100]

Writes into <out dir>:
    turn-<deg>.png        the mesh from eye level, every 45 degrees round, 512 pixels, flat colour from its own texture
                          (no light baked in), no perspective: what a card is pictured as
    crew-<deg>-<up>.png   the same at the crew camera's size (its true height at --crew-px-per-m pixels a metre),
                          from eye level (up 0) and from 25 degrees above (up 25), as the crew camera sees a figure
and prints RESULT {json}: its triangles, how many loose pieces and how much of the surface is outside the biggest,
how tall, wide and deep it stands once sized, and which way up it came in.

Rigging, motion and the per-bone cards need a skeleton, which a take's low-poly build gives; this pictures the mesh as
it comes, so it can be judged before any of that is paid for.
"""

import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

VIEWS = list(range(0, 360, 45))
UPS = (0, 25)
TURN_PX = 512
WELD_M = 0.0005           # points closer than half a millimetre are one point


def args():
    a = sys.argv[sys.argv.index("--") + 1:]
    flag = lambda name, default: a[a.index(name) + 1] if name in a else default
    return a[0], a[1], float(a[2]), float(flag("--crew-px-per-m", 100))


def bring(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in bpy.context.scene.objects:
        o.select_set(o in meshes)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def extent(obj):
    vs = [v.co for v in obj.data.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    return lo, hi


def stand(obj, height):
    """Upright (its tallest side up, unless that is the T-pose's arm span), feet on the floor, centred, sized."""
    lo, hi = extent(obj)
    size = hi - lo
    came = "z up"
    if size.y > size.z and size.y >= 0.6 * size.x:
        obj.data.transform(Matrix.Rotation(math.radians(90), 4, "X"))
        came = "y up, turned"
    lo, hi = extent(obj)
    k = height / max(1e-6, hi.z - lo.z)
    obj.data.transform(Matrix.Scale(k, 4))
    lo, hi = extent(obj)
    obj.data.transform(Matrix.Translation(Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z))))
    obj.data.update()
    lo, hi = extent(obj)
    return came, hi - lo


def pieces(obj):
    """Loose pieces, and the share of the surface outside the biggest."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    # TRELLIS splits points along its texture's seams: join points that lie on one another (in a copy) first
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=WELD_M)
    bm.faces.ensure_lookup_table()
    seen, areas = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, area = [f], 0.0
        seen.add(f.index)
        while stack:
            g = stack.pop()
            area += g.calc_area()
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        areas.append(area)
    tris = sum(len(f.verts) - 2 for f in bm.faces)
    bm.free()
    total = sum(areas) or 1.0
    return tris, len(areas), 1.0 - max(areas or [0.0]) / total


def setup(size):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "FLAT"
    shading.color_type = "TEXTURE"
    shading.show_object_outline = False
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    cam_data = bpy.data.cameras.new("eye")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("eye", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    return scene, cam


def shoot(scene, cam, size, deg, up, px, path, frame):
    """From `deg` round (0 is in front, looking at its face along +Y) and `up` degrees above, framing `frame` metres."""
    a, e = math.radians(deg), math.radians(up)
    far = 10.0
    centre = Vector((0, 0, size.z / 2))
    where = centre + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * far
    cam.location = where
    cam.rotation_euler = (centre - where).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = frame
    scene.render.resolution_x = scene.render.resolution_y = px
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    mesh, out, height, crew = args()
    os.makedirs(out, exist_ok=True)
    obj = bring(mesh)
    came, size = stand(obj, height)
    tris, loose, outside = pieces(obj)
    scene, cam = setup(size)
    frame = max(size.x, size.y, size.z) * 1.08
    for deg in VIEWS:
        shoot(scene, cam, size, deg, 0, TURN_PX, os.path.join(out, "turn-%03d.png" % deg), frame)
        for up in UPS:
            shoot(scene, cam, size, deg, up, max(8, round(frame * crew)), os.path.join(out, "crew-%03d-%02d.png" % (deg, up)), frame)
    print("RESULT " + json.dumps({"triangles": tris, "pieces": loose, "outside_biggest": round(outside, 4), "came_in": came,
                                  "height_m": round(size.z, 3), "width_m": round(size.x, 3), "depth_m": round(size.y, 3),
                                  "views": VIEWS, "ups": list(UPS), "frame_m": round(frame, 3)}), flush=True)


main()
