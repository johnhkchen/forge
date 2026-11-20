# Set the stage around an object: a big matte floor, a warm key light from
# the upper left, a cool fill, a rim light from behind, a soft gray sky, and
# a camera at a three-quarter view that fits the whole object with a margin.
# Everything is sized from the object, so a thimble and a troll get the same
# picture. Also sets the render: Cycles, 64 samples, denoised, 1024 x 1024.
#
# Run it again with other numbers and it replaces its own floor, lights and
# camera (nothing else). To move the camera, change "around" and "above";
# to brighten or dim, change "light".
#
# Send this whole file through the blender MCP `execute_blender_code` tool
# after editing PARAMS. Prints RESULT {json}. Instant. Safe-mode compatible.

PARAMS = {
    "object": None,   # None = the largest visible mesh
    "around": 25,     # camera: degrees around from straight in front (-Y); + is toward +X, - toward -X
    "above": 15,      # camera: degrees above level
    "lens": 50,       # mm; longer flattens (85 suits small props)
    "margin": 1.15,   # 1.0 = the object just touches the frame
    "light": 1.0,     # all three lights, brighter or dimmer
    "floor": [0.42, 0.40, 0.37],  # floor color; None = no floor
    "sky": [0.75, 0.75, 0.76],    # world color (strength 0.5)
    "samples": 64,
    "size": [1024, 1024],
}

import bpy
import json
import math
from mathutils import Vector


def face_count(obj):
    return len(obj.data.polygons)

def pick_object(name):
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise ValueError("no object named %r" % name)
        return obj
    meshes = [o for o in bpy.context.scene.objects
              if o.type == "MESH" and o.visible_get() and not o.get("staging") and not o.name.startswith("Look: ")]
    if not meshes:
        raise ValueError("the scene has no visible mesh objects")
    return max(meshes, key=face_count)

def aim(thing, target):
    thing.rotation_euler = (target - thing.location).to_track_quat("-Z", "Y").to_euler()


scene = bpy.context.scene
obj = pick_object(PARAMS["object"])
replaced = 0
for o in [o for o in scene.objects if o.get("staging")]:
    bpy.data.objects.remove(o, do_unlink=True)
    replaced += 1

corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
low = Vector([min(c[i] for c in corners) for i in range(3)])
high = Vector([max(c[i] for c in corners) for i in range(3)])
center = (low + high) / 2
reach = (high - low).length / 2  # the object fits in a ball this big

def place(name, data):
    thing = bpy.data.objects.new(name, data)
    thing["staging"] = True
    scene.collection.objects.link(thing)
    return thing

if PARAMS["floor"]:
    half = reach * 25
    me = bpy.data.meshes.new("Ground")
    me.from_pydata([(-half, -half, low.z), (half, -half, low.z), (half, half, low.z), (-half, half, low.z)], [], [(0, 1, 2, 3)])
    ground = place("Ground", me)
    mat = bpy.data.materials.get("Ground") or bpy.data.materials.new("Ground")
    mat.use_nodes = True
    surface = mat.node_tree.nodes["Principled BSDF"]
    surface.inputs["Base Color"].default_value = tuple(PARAMS["floor"]) + (1.0,)
    surface.inputs["Roughness"].default_value = 0.9
    surface.inputs["Metallic"].default_value = 0.0
    me.materials.append(mat)

lights = {}
for name, direction, strength, color in (
        ("Key", (-0.58, -0.58, 0.58), 35.0, (1.0, 0.96, 0.9)),   # upper left, in front
        ("Fill", (0.8, -0.55, 0.22), 12.0, (0.9, 0.95, 1.0)),    # low right, in front
        ("Rim", (0.28, 0.8, 0.52), 25.0, (1.0, 1.0, 1.0))):      # behind
    far = reach * 3.5
    lamp = bpy.data.lights.new(name, "AREA")
    lamp.energy = strength * far * far * PARAMS["light"]
    lamp.size = reach * 1.5
    lamp.color = color
    thing = place(name, lamp)
    thing.location = center + Vector(direction).normalized() * far
    aim(thing, center)
    lights[name] = round(lamp.energy, 1)

if PARAMS["sky"]:
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    sky = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if sky:
        sky.inputs["Color"].default_value = tuple(PARAMS["sky"]) + (1.0,)
        sky.inputs["Strength"].default_value = 0.5

# Camera: back off along the view direction until every corner of the
# object's box is inside the frame, with the margin.
lens = bpy.data.cameras.new("Camera")
lens.lens = PARAMS["lens"]
camera = place("Camera", lens)
around, above = math.radians(PARAMS["around"]), math.radians(PARAMS["above"])
toward = Vector((math.sin(around) * math.cos(above), -math.cos(around) * math.cos(above), math.sin(above)))
right = Vector((0, 0, 1)).cross(toward).normalized()
up = toward.cross(right)
wide, tall = PARAMS["size"]
half_w = lens.sensor_width / 2 / lens.lens * min(1.0, wide / tall)
half_h = lens.sensor_width / 2 / lens.lens * min(1.0, tall / wide)
distance = 0.0
for c in corners:
    off = c - center
    distance = max(distance,
                   off.dot(toward) + abs(off.dot(right)) * PARAMS["margin"] / half_w,
                   off.dot(toward) + abs(off.dot(up)) * PARAMS["margin"] / half_h)
camera.location = center + toward * distance
aim(camera, center)
lens.clip_start = min(0.1, distance / 50)
lens.clip_end = max(1000.0, distance * 50)
scene.camera = camera

scene.render.engine = "CYCLES"
scene.cycles.samples = PARAMS["samples"]
scene.cycles.use_denoising = True
scene.render.resolution_x, scene.render.resolution_y = wide, tall
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
try:
    scene.cycles.device = "GPU"
except TypeError:
    pass

print("RESULT " + json.dumps({
    "object": obj.name,
    "replaced": replaced,
    "camera": {"location": [round(c, 3) for c in camera.location], "distance": round(distance, 3),
               "lens": PARAMS["lens"], "aimed_at": [round(c, 3) for c in center]},
    "lights_watts": lights,
    "render": {"engine": scene.render.engine, "samples": scene.cycles.samples, "size": [wide, tall],
               "device": scene.cycles.device},
    "note": "The device says GPU, but Cycles only uses the graphics card if one is already chosen in "
            "Blender's own preferences; safe mode can't read or change those.",
}))
