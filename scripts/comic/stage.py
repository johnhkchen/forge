"""What a comic panel is built from, inside a background Blender: a character brought in once, frozen in a pose
or at a moment of one of its clips, stood on a spot facing a way; a camera fitted to what it should show; and
where each head lands in the picture, so the lettering can point at it.

Used by render_panels.py, style_stills.py and face_fit.py. Blender only (imports bpy); never touches an open Blender.
"""

import json
import math
import os

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SKILL = os.path.join(REPO, ".claude", "skills", "tidy-mesh", "scripts")
POSES = os.path.join(REPO, "motion", "comic_poses.json")
FPS = 30  # what every clip is made at; set before an import so its keys land one per frame
FRONT = (0.0, -1.0, 0.0)  # the way a character faces as it is built


def run_script(name, params):
    """Run a tidy-mesh skill script with its PARAMS updated and return the JSON it printed."""
    with open(os.path.join(SKILL, name)) as f:
        source = f.read()
    head, _, tail = source.partition("\nimport ")
    namespace = {"__name__": "__main__"}
    exec(head, namespace)
    namespace["PARAMS"].update(params)
    captured = []

    def capture(*args, **kwargs):
        text = " ".join(str(a) for a in args)
        if text.startswith("RESULT "):
            captured.append(json.loads(text[len("RESULT "):]))

    namespace["print"] = capture
    exec("import " + tail, namespace)
    return captured[-1] if captured else None


def fresh_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    return scene


def bring_in(path):
    """Import a .glb and return the objects it added."""
    before = set(bpy.data.objects)
    bpy.context.scene.render.fps = FPS
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def load_character(path):
    """A rigged character file (profiles/<version>-walk.glb, -run.glb, -hero.glb), ready to pose.
    Skin that clothes hide and the bones' display shapes are kept out of the picture."""
    added = bring_in(path)
    rig = next((o for o in added if o.type == "ARMATURE"), None)
    if rig is None:
        raise ValueError("%s has no skeleton: comics need a -walk, -run or -hero file" % path)
    meshes = []
    for o in added:
        if o.type != "MESH":
            continue
        if o.get("under") or not o.data.materials or (o.find_armature() is None and o.name.startswith("Icosphere")):
            o.hide_render = o.hide_viewport = True
            continue
        meshes.append(o)
    action = rig.animation_data.action if rig.animation_data else None
    sockets = {o.get("socket"): o for o in added if o.get("forge") == "socket"}
    rig.rotation_mode = "QUATERNION"
    return {"path": path, "rig": rig, "meshes": meshes, "sockets": sockets, "action": action, "objects": added,
            "rest": (rig.location.copy(), rig.rotation_quaternion.copy())}


def show(character, visible):
    for o in character["meshes"]:
        o.hide_render = o.hide_viewport = not visible


def freeze(character, seconds):
    """Hold the character as it is `seconds` into its clip: the keys are read once and the clip let go,
    so two characters in one panel can each be at a moment of their own."""
    rig, action = character["rig"], character["action"]
    if action is None:
        raise ValueError("%s has no clip to take a moment from" % character["path"])
    rig.location, rig.rotation_quaternion = character["rest"]
    rig.animation_data.action = action
    slots = getattr(action, "slots", None)
    if slots and rig.animation_data.action_slot is None:
        rig.animation_data.action_slot = slots[0]
    first, last = action.frame_range
    frame = max(first, min(last, first + seconds * FPS))
    bpy.context.scene.frame_set(int(frame), subframe=frame - int(frame))
    held = [(b.name, b.location.copy(), b.rotation_quaternion.copy(), b.rotation_euler.copy(), b.scale.copy(), b.rotation_mode)
            for b in rig.pose.bones]
    rig.animation_data.action = None
    for name, loc, quat, euler, scale, mode in held:
        bone = rig.pose.bones[name]
        bone.rotation_mode = mode
        bone.location, bone.rotation_quaternion, bone.rotation_euler, bone.scale = loc, quat, euler, scale
    bpy.context.view_layer.update()
    return {"clip": action.name, "second": round((frame - first) / FPS, 3), "of_seconds": round((last - first) / FPS, 3)}


def clip_seconds(character):
    action = character["action"]
    return (action.frame_range[1] - action.frame_range[0]) / FPS if action else 0.0


def load_poses():
    with open(POSES) as f:
        return json.load(f)["poses"]


def turn(degrees, mirrored):
    x, y, z = [math.radians(v) for v in degrees]
    if mirrored:
        y, z = -y, -z
    return Matrix.Rotation(z, 3, "Z") @ Matrix.Rotation(y, 3, "Y") @ Matrix.Rotation(x, 3, "X")


def strike(character, pose):
    """Put the character in a hand-written pose (motion/comic_poses.json): every bone back to the T-pose, then the turns."""
    rig = character["rig"]
    if rig.animation_data:
        rig.animation_data.action = None
    rig.location, rig.rotation_quaternion = character["rest"]
    turns = {}
    for name, degrees in pose["bones"].items():
        if name.endswith("_l") or name.endswith("_r"):
            turns[name] = turn(degrees, name.endswith("_r"))
        elif name + "_l" in rig.pose.bones:
            turns.setdefault(name + "_l", turn(degrees, False))
            turns.setdefault(name + "_r", turn(degrees, True))
        else:
            turns[name] = turn(degrees, False)
    for bone in rig.pose.bones:
        bone.rotation_mode = "QUATERNION"
        bone.location = (0.0, 0.0, 0.0)
        bone.scale = (1.0, 1.0, 1.0)
        rest = bone.bone.matrix_local.to_3x3()
        delta = turns.get(bone.name)
        bone.rotation_quaternion = (rest.inverted() @ delta @ rest).to_quaternion() if delta else Quaternion()
    bpy.context.view_layer.update()


def bare(character):
    """Measure the character itself, not its ink line: the line is a shell a little bigger than the mesh, and it is
    only needed in the render. Returns the dependency graph to measure with."""
    changed = False
    for o in character["meshes"]:
        for modifier in o.modifiers:
            if modifier.name == "comic ink" and modifier.show_viewport:
                modifier.show_viewport = False
                changed = True
    if changed:
        bpy.context.view_layer.update()
    return bpy.context.evaluated_depsgraph_get()


def lowest(character):
    """The lowest point of the posed character, in the scene (a prop it carries is not counted)."""
    graph = bare(character)
    low = None
    for o in character["meshes"]:
        if o.get("forge") == "prop":
            continue
        made = o.evaluated_get(graph)
        mesh = made.to_mesh()
        world = made.matrix_world
        for v in mesh.vertices:
            z = (world @ v.co).z
            if low is None or z < low:
                low = z
        made.to_mesh_clear()
    return low or 0.0


def shape_points(character, every=5):
    """Points all over the posed character, in the scene: what a camera must keep in frame to show all of it."""
    graph = bare(character)
    points = []
    for o in character["meshes"]:
        made = o.evaluated_get(graph)
        mesh = made.to_mesh()
        world = made.matrix_world
        points.extend(world @ v.co for i, v in enumerate(mesh.vertices) if i % every == 0)
        made.to_mesh_clear()
    return points


def bone_point(character, bone, tail=False):
    rig = character["rig"]
    b = rig.pose.bones[bone]
    return rig.matrix_world @ (b.tail if tail else b.head)


def carried(character, bone, direction):
    """A direction of the T-pose (in the character's own axes) as `bone` carries it now, in the scene."""
    rig = character["rig"]
    b = rig.pose.bones[bone]
    turned = b.matrix.to_3x3() @ b.bone.matrix_local.to_3x3().inverted()
    return (rig.matrix_world.to_3x3() @ (turned @ Vector(direction))).normalized()


def facing_now(character):
    """Which way the body faces, flat on the floor, as an angle: 0 = toward -y, + turns it toward +x."""
    way = carried(character, "hips", FRONT)
    return math.atan2(way.x, -way.y)


def stand_at(character, spot=None, facing=None, floor=None):
    """Move the posed character so its hips are over `spot` (x, y), turned to face `facing` (radians: 0 looks
    toward -y, + turns it toward +x), and set down on `floor` (z). None leaves that part as the clip has it."""
    rig = character["rig"]
    bpy.context.view_layer.update()
    if facing is not None:
        about = bone_point(character, "hips")
        spin = Matrix.Rotation(facing - facing_now(character), 4, "Z")
        rig.matrix_world = Matrix.Translation(about) @ spin @ Matrix.Translation(-about) @ rig.matrix_world
        bpy.context.view_layer.update()
    if spot is not None:
        hips = bone_point(character, "hips")
        rig.location.x += spot[0] - hips.x
        rig.location.y += spot[1] - hips.y
        bpy.context.view_layer.update()
    if floor is not None:
        rig.location.z += floor - lowest(character)
        bpy.context.view_layer.update()


def head_of(character):
    """Where the head is now: its middle, its size, which way the face looks, and its top."""
    neck_top = bone_point(character, "head")
    top_socket = character["sockets"].get("head")
    top = top_socket.matrix_world.translation.copy() if top_socket else bone_point(character, "head", tail=True)
    tall = max((top - neck_top).length, 0.05)
    up = carried(character, "head", (0.0, 0.0, 1.0))
    return {"center": neck_top + up * tall * 0.5, "radius": tall * 0.56, "front": carried(character, "head", FRONT), "up": up,
            "top": neck_top + up * tall}


def points_of(character, bones):
    """Both ends of the named bones, in the scene: what a camera should keep in frame."""
    have = character["rig"].pose.bones
    return [bone_point(character, b, tail=t) for b in bones for t in (False, True) if b in have]


def add_camera(scene, name="panel camera", lens=50.0):
    data = bpy.data.cameras.new(name)
    data.lens = lens
    cam = bpy.data.objects.new(name, data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    return cam


def aim(cam, eye, target):
    cam.location = eye
    cam.rotation_euler = (Vector(target) - Vector(eye)).to_track_quat("-Z", "Y").to_euler()


def fit_camera(cam, points, toward, size, margin=1.15, pad=(0.0, 0.0, 0.0, 0.0)):
    """Back the camera off along `toward` (a direction from the subject to the camera) until every point is in
    frame. `pad` keeps part of the picture clear of them: fractions of it (left, right, top, bottom), for lettering."""
    wide, tall = size
    toward = Vector(toward).normalized()
    right = Vector((0, 0, 1)).cross(toward).normalized()
    up = toward.cross(right)
    low = Vector([min(p[i] for p in points) for i in range(3)])
    high = Vector([max(p[i] for p in points) for i in range(3)])
    center = (low + high) / 2
    half_w = cam.data.sensor_width / 2 / cam.data.lens * min(1.0, wide / tall)
    half_h = cam.data.sensor_width / 2 / cam.data.lens * min(1.0, tall / wide)
    use_w = half_w * (1.0 - pad[0] - pad[1])
    use_h = half_h * (1.0 - pad[2] - pad[3])
    distance = 0.0
    for p in points:
        off = p - center
        distance = max(distance, off.dot(toward) + abs(off.dot(right)) * margin / use_w, off.dot(toward) + abs(off.dot(up)) * margin / use_h)
    # Slide the view so the padded edges stay clear of the subject.
    shift = right * (pad[1] - pad[0]) * half_w * distance + up * (pad[2] - pad[3]) * half_h * distance
    aim(cam, center + toward * distance + shift, center + shift)
    cam.data.clip_start = max(0.01, distance / 100)
    cam.data.clip_end = max(200.0, distance * 50)
    bpy.context.view_layer.update()
    return distance


def in_picture(scene, cam, point, size):
    """A point of the scene in pixels from the picture's top left, and how far in front of the camera it is."""
    v = world_to_camera_view(scene, cam, Vector(point))
    return [round(v.x * size[0], 1), round((1.0 - v.y) * size[1], 1)], v.z


def head_in_picture(scene, cam, character, size):
    """The head as the lettering needs it, in pixels: its middle and radius, the mouth, the top."""
    head = head_of(character)
    middle, depth = in_picture(scene, cam, head["center"], size)
    cam_right = cam.matrix_world.to_3x3() @ Vector((1, 0, 0))
    edge, _ = in_picture(scene, cam, head["center"] + cam_right * head["radius"], size)
    mouth, _ = in_picture(scene, cam, head["center"] + head["front"] * head["radius"] * 0.8 - head["up"] * head["radius"] * 0.45, size)
    top, _ = in_picture(scene, cam, head["top"], size)
    return {"center": middle, "radius": round(abs(edge[0] - middle[0]), 1), "mouth": mouth, "top": top, "depth": round(depth, 3)}
