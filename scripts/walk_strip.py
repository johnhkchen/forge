"""Picture a rigged character's animation as a strip of poses, in a background Blender.

    blender -b --factory-startup -P scripts/walk_strip.py -- FILE OUT.png [--view side|front|quarter] [--frames 8] [--at 165,180,258] [--bones] [--undressed] [--size 420]

FILE is a .glb with a skeleton and an animation (profiles/lowpoly-walk.glb),
or a .blend saved after rig.py. The character is stood side by side `--frames`
times, each copy frozen at the next moment of the loop, and the row is
rendered once, straight on: from the side (looking at its left), the front,
or a three-quarter view. `--bones` draws the skeleton as red sticks inside a
see-through body, to check where the joints landed. With no animation in the
file it draws the rest pose once. A character is drawn dressed, without the
body faces its gear hides; `--undressed` draws the whole body and no gear.
`--at` picks the frames by number instead of spreading them over the clip. A
clip that travels (a shot) is drawn on the spot: each pose stands where its
place in the row is, not where the motion had carried it.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]


def option(name, default):
    if name in args:
        i = args.index(name)
        value = args[i + 1]
        del args[i:i + 2]
        return value
    return default


view = option("--view", "side")
count = int(option("--frames", "8"))
size = int(option("--size", "420"))
chosen = option("--at", "")
bones = "--bones" in args
if bones:
    args.remove("--bones")
undressed = "--undressed" in args
if undressed:
    args.remove("--undressed")
source, out = os.path.abspath(args[0]), os.path.abspath(args[1])

if source.endswith(".blend"):
    bpy.ops.wm.open_mainfile(filepath=source)
else:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = 30  # what every motion here is baked at; the importer lays keys out by the scene's rate
    bpy.ops.import_scene.gltf(filepath=source)
scene = bpy.context.scene
rig = next((o for o in scene.objects if o.type == "ARMATURE"), None)
# Dressed, as a game draws it: body faces that worn gear hides ("body under: ...") are left out. --undressed draws the body alone, whole.
meshes = [o for o in scene.objects if o.type == "MESH" and o.visible_get() and not (o.get("forge") == "gear" if undressed else o.get("under"))]
action = rig.animation_data.action if rig and rig.animation_data and rig.animation_data.action else None
if action and chosen:
    frames = [float(f) for f in chosen.split(",")]
elif action:
    first, last = [int(round(f)) for f in action.frame_range]
    frames = [first + (last - first) * i / count for i in range(count)]
else:
    frames = [scene.frame_current]


def paint(mesh, see_through):
    """A plain material showing the mesh's painted colors, for files that carry no material."""
    if mesh.materials and mesh.materials[0] and not see_through:
        return
    mat = bpy.data.materials.new("strip")
    mat.use_nodes = True
    shader = mat.node_tree.nodes["Principled BSDF"]
    shader.inputs["Roughness"].default_value = 0.9
    if mesh.color_attributes:
        color = mat.node_tree.nodes.new("ShaderNodeVertexColor")
        mat.node_tree.links.new(color.outputs["Color"], shader.inputs["Base Color"])
    if see_through:
        shader.inputs["Alpha"].default_value = 0.3
        mat.surface_render_method = "BLENDED"
    mesh.materials.clear()
    mesh.materials.append(mat)


def sticks(rig, name):
    """The skeleton as thin four-sided spindles, one per bone."""
    verts, faces = [], []
    for bone in rig.pose.bones:
        a, b = rig.matrix_world @ bone.head, rig.matrix_world @ bone.tail
        along = b - a
        side = along.cross(Vector((0.3, 0.5, 0.8))).normalized() * max(along.length * 0.07, 0.006)
        up = along.cross(side).normalized() * side.length
        waist = a + along * 0.15
        n = len(verts)
        verts += [a, waist + side, waist + up, waist - side, waist - up, b]
        faces += [(n, n + 1 + i, n + 1 + (i + 1) % 4) for i in range(4)] + [(n + 5, n + 1 + (i + 1) % 4, n + 1 + i) for i in range(4)]
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    red = bpy.data.materials.new("sticks")
    red.use_nodes = True
    shader = red.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (0, 0, 0, 1)
    shader.inputs["Emission Color"].default_value = (1.0, 0.1, 0.05, 1.0)
    shader.inputs["Emission Strength"].default_value = 1.5
    me.materials.append(red)
    return me


corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
low = Vector([min(c[i] for c in corners) for i in range(3)])
high = Vector([max(c[i] for c in corners) for i in range(3)])
tall = high.z - low.z
# Side by side across the picture: along y for a side view, along x otherwise.
across = Vector((0, -1, 0)) if view == "side" else Vector((1, 0, 0))
gap = ((high.y - low.y) if view == "side" else (high.x - low.x)) * (1.25 if view != "side" else 1.6)
if view == "side":
    gap = max(gap, 0.75 * tall)

stage = bpy.data.collections.new("strip")
scene.collection.children.link(stage)
for i, frame in enumerate(frames):
    scene.frame_set(int(frame), subframe=frame - int(frame))
    deps = bpy.context.evaluated_depsgraph_get()
    shift = across * gap * (i - (len(frames) - 1) / 2)
    if rig and "hips" in rig.pose.bones:  # a clip that travels is drawn on the spot
        gone = rig.matrix_world @ rig.pose.bones["hips"].head - rig.matrix_world @ rig.data.bones["hips"].head_local
        shift -= Vector((gone.x, gone.y, 0.0))
    for obj in meshes:
        frozen = bpy.data.meshes.new_from_object(obj.evaluated_get(deps), depsgraph=deps)
        paint(frozen, bones)
        copy = bpy.data.objects.new("pose %d %s" % (i, obj.name), frozen)
        copy.matrix_world = obj.matrix_world.copy()
        copy.location = copy.location + shift
        stage.objects.link(copy)
    if bones and rig:
        copy = bpy.data.objects.new("bones %d" % i, sticks(rig, "bones %d" % i))
        copy.location = shift
        stage.objects.link(copy)
for obj in [o for o in scene.objects if o.type == "MESH" and o.name not in stage.objects]:
    obj.hide_render = True

wide = gap * len(frames) + 0.2 * tall
center = Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, (low.z + high.z) / 2))
# Poses that leave the standing figure's box (a jump, a crouch under the floor line) are kept in the picture.
posed = [o.matrix_world @ Vector(c) for o in stage.objects for c in o.bound_box]
if posed:
    top, bottom = max(max(c.z for c in posed), high.z), min(min(c.z for c in posed), low.z)
    center.z, tall = (top + bottom) / 2, max(tall, top - bottom)
away = {"side": Vector((1, 0, 0)), "front": Vector((0, -1, 0)), "quarter": Vector((0.45, -1, 0.25)).normalized()}[view]
cam = bpy.data.objects.new("strip camera", bpy.data.cameras.new("strip camera"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = max(wide, tall * 1.2)
cam.data.clip_end = 100 * tall
cam.location = center + away * 20 * tall
cam.rotation_euler = (-away).to_track_quat("-Z", "Y").to_euler()
sun = bpy.data.objects.new("strip light", bpy.data.lights.new("strip light", "SUN"))
sun.data.energy = 3.0
sun.data.angle = 0.4
sun.rotation_euler = (-(away + Vector((0, 0, 0.9)) + away.cross(Vector((0, 0, 1))) * 0.6)).to_track_quat("-Z", "Y").to_euler()
floor = bpy.data.meshes.new("strip floor")
reach = wide + 4 * tall
floor.from_pydata([(-reach, -reach, low.z), (reach, -reach, low.z), (reach, reach, low.z), (-reach, reach, low.z)], [], [(0, 1, 2, 3)])
ground = bpy.data.materials.new("strip floor")
ground.use_nodes = True
ground.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.62, 0.6, 0.56, 1)
ground.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0
floor.materials.append(ground)
for o in (cam, sun, bpy.data.objects.new("strip floor", floor)):
    scene.collection.objects.link(o)
sky = bpy.data.worlds.new("strip sky")
sky.use_nodes = True
sky.node_tree.nodes["Background"].inputs["Color"].default_value = (0.84, 0.82, 0.78, 1.0)
sky.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.7
scene.world = sky
scene.camera = cam
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_y = size
scene.render.resolution_x = int(size * max(wide / (tall * 1.2), 1.0))
scene.render.film_transparent = False
scene.view_settings.view_transform = "Standard"
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
print("STRIP %s: %d poses, %s view" % (out, len(frames), view))
