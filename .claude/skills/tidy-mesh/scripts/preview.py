# Render a quick, honest preview of one object to a PNG: three-quarter view,
# plain light, optionally with its wireframe drawn over it. Adds a temporary
# camera and light, and removes them afterwards.
#
# EEVEE, small image: a second or two. Safe-mode compatible.

PARAMS = {
    "object": None,      # None = the largest visible mesh
    "path": None,        # absolute path of the .png to write (required)
    "size": 640,
    "wireframe": False,  # draw the edges, to judge topology
}

import bpy
import json
from mathutils import Vector



def face_count(obj):
    return len(obj.data.polygons)

def pick_object(name):
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise ValueError("no object named %r" % name)
        return obj
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get()]
    if not meshes:
        raise ValueError("the scene has no visible mesh objects")
    return max(meshes, key=face_count)


if not PARAMS["path"]:
    raise ValueError("set PARAMS['path'] to where the .png should go")
obj = pick_object(PARAMS["object"])
scene = bpy.context.scene
corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
low = Vector([min(c[i] for c in corners) for i in range(3)])
high = Vector([max(c[i] for c in corners) for i in range(3)])
center, reach = (low + high) / 2, (high - low).length

cam = bpy.data.objects.new("preview camera", bpy.data.cameras.new("preview camera"))
sun = bpy.data.objects.new("preview light", bpy.data.lights.new("preview light", "SUN"))
for o in (cam, sun):
    scene.collection.objects.link(o)
cam.location = center + Vector((0.55, -0.8, 0.35)) * reach
cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
sun.data.energy = 4.0
sun.rotation_euler = (0.8, 0.2, -0.6)
wire = None
if PARAMS["wireframe"]:
    wire = obj.modifiers.new("preview wire", "WIREFRAME")
    wire.thickness = reach * 0.0008
    wire.use_replace = False

saved = (scene.camera, scene.render.engine, scene.render.resolution_x,
         scene.render.resolution_y, scene.render.filepath)
others = [o for o in scene.objects if o.type == "MESH" and o is not obj and not o.hide_render]
try:
    for o in others:
        o.hide_render = True
    scene.camera = cam
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = scene.render.resolution_y = PARAMS["size"]
    scene.render.filepath = PARAMS["path"]
    bpy.ops.render.render(write_still=True)
finally:
    for o in others:
        o.hide_render = False
    (scene.camera, scene.render.engine, scene.render.resolution_x,
     scene.render.resolution_y, scene.render.filepath) = saved
    if wire:
        obj.modifiers.remove(wire)
    for o in (cam, sun):
        bpy.data.objects.remove(o, do_unlink=True)

print("RESULT " + json.dumps({"object": obj.name, "path": PARAMS["path"]}))
