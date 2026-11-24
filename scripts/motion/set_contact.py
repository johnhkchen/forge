"""What a standing set adds to a shot inside Blender: the set itself, stood up
to be filmed, and the measurements only a set makes possible.

Used by render_take.py. Nothing here changes a character or its motion: the
skeleton, the planted feet, the legs kept out of the set's blocks and the hand
put on its spot are all still animate.py's work, reached through
apply_shot.py as before. A standing set only hands that step different
numbers (its blocks, and the spot two people's hands share), through
plan.json. This module then looks at the result with everyone on the stage
together, which no single character's file can show:

    hands_apart   how far apart two people's hands are while they shake
    seat_gap      how far a seated body is from what it sits on
    stand_up      the set's geometry, backdrop, dressing, lights and cameras

Coordinates. A set is written in the shot's axes (x, y up, z toward the
cameras). Blender is z up, and its glTF import turns a file that way, so a
point [x, y, z] of the set is at (x, -z, y) here.

Blender only (imports bpy). Never touches an open Blender.
"""

import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
import standing  # noqa: E402

WRIST = ("hand_r", "RightHand")  # the right wrist's bone: on one of our characters, on the box figure
UNDERSIDE = 0.30  # metres above a seat: what is lower than this, over the seat, is what sits on it


def to_blender(p):
    return Vector((p[0], -p[2], p[1]))


def from_blender(v):
    return (v.x, v.z, -v.y)


def look(obj, at, aim):
    obj.location = to_blender(at)
    obj.rotation_euler = (to_blender(aim) - to_blender(at)).to_track_quat("-Z", "Y").to_euler()


def flat_color(name, color, glow=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
    shader.inputs["Roughness"].default_value = 0.85
    if glow:
        shader.inputs["Emission Color"].default_value = (color[0], color[1], color[2], 1.0)
        shader.inputs["Emission Strength"].default_value = glow
    return mat


def painted(objects):
    """A block-out carries its colors on its corners, with no material: give each such mesh one that shows them."""
    for obj in objects:
        if obj.type != "MESH" or not obj.data.color_attributes:
            continue
        if any(slot.material for slot in obj.material_slots):
            continue
        mat = bpy.data.materials.new("corner colors")
        mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        paint = nodes.new("ShaderNodeAttribute")
        paint.attribute_name = obj.data.color_attributes[0].name
        links.new(paint.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
        nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.85
        obj.data.materials.append(mat)


def bring_in(path, name, scale=1.0, at=None, heading=0.0):
    """Import a .glb under one empty, which can then be sized, moved and turned as a whole. Returns (the empty, what came in)."""
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.context.scene.objects if o not in before]
    holder = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(holder)
    for obj in new:
        if obj.parent is None:
            obj.parent = holder
        if obj.type == "MESH" and not obj.find_armature() and obj.name.startswith("Icosphere"):
            obj.hide_render = True  # a bone's display shape is not part of the picture
        if obj.type == "MESH" and obj.get("under"):
            obj.hide_render = True  # skin that worn gear hides ("body under: ..."), left out as a game leaves it out
    holder.scale = (scale, scale, scale)
    if at is not None:
        holder.location = to_blender(at)
    holder.rotation_euler = (0.0, 0.0, math.radians(heading))
    painted(new)
    return holder, new


def stand_up(st, scene):
    """The set in the scene: its geometry on the floor, the ground around it, the backdrop, the dressing on
    its slots, the lights and the cameras. Returns {camera name: camera object}."""
    geometry = st.get("geometry") or {}
    bring_in(os.path.join(st["dir"], geometry.get("glb", "set.glb")), "set: " + st["name"], at=geometry.get("move", [0.0, 0.0, 0.0]), heading=geometry.get("turn_deg", 0.0))

    ground = st.get("ground")
    if ground:
        bpy.ops.mesh.primitive_plane_add(size=float(ground.get("size_m", 40.0)), location=(0.0, 0.0, float(ground.get("y", 0.0)) - 0.002))
        plane = bpy.context.active_object
        plane.name = "ground"
        plane.data.materials.append(flat_color("ground", ground.get("color", [0.8, 0.78, 0.74])))

    flats = [dict(st["backdrop"], name="backdrop")] if st.get("backdrop") else []
    for backdrop in flats + list(st.get("signs") or []):  # a sign is a small painted flat, stood up the same way
        w, h = backdrop["width_m"] / 2.0, backdrop["height_m"] / 2.0
        mesh = bpy.data.meshes.new(backdrop["name"])
        mesh.from_pydata([(-w, 0.0, -h), (w, 0.0, -h), (w, 0.0, h), (-w, 0.0, h)], [], [(0, 1, 2, 3)])
        uv = mesh.uv_layers.new(name="UVMap")
        for corner, spot in zip(uv.data, ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))):
            corner.uv = spot
        flat = bpy.data.objects.new(backdrop["name"], mesh)
        scene.collection.objects.link(flat)
        flat.location = to_blender(backdrop["center"])
        flat.rotation_euler = (0.0, 0.0, math.radians(backdrop.get("heading", 0.0)))
        mat = bpy.data.materials.new(backdrop["name"])
        mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        nodes.remove(nodes["Principled BSDF"])
        picture = nodes.new("ShaderNodeTexImage")
        picture.image = bpy.data.images.load(os.path.join(st["dir"], backdrop["image"]))
        glow = nodes.new("ShaderNodeEmission")  # a painted flat is lit evenly: it shows its picture as it is
        glow.inputs["Strength"].default_value = float(backdrop.get("glow", 1.0))
        links.new(picture.outputs["Color"], glow.inputs["Color"])
        links.new(glow.outputs["Emission"], nodes["Material Output"].inputs["Surface"])
        mesh.materials.append(mat)

    slots = st.get("slots") or {}
    for item in st.get("dressing") or []:
        slot = slots[item["slot"]]
        bring_in(os.path.join(st["dir"], item.get("detail") or item["glb"]), "dressing: " + item["prop"], at=slot["at"], heading=slot.get("heading", 0.0))

    for card in st.get("lights") or []:
        kind = {"area": "AREA", "spot": "SPOT", "sun": "SUN"}[card["kind"]]
        data = bpy.data.lights.new(card["name"], kind)
        data.energy = float(card["power"])
        data.color = card.get("color", [1.0, 1.0, 1.0])
        if kind == "AREA":
            data.size = float(card.get("size_m", 2.0))
        if kind == "SUN":
            data.angle = math.radians(4)
        light = bpy.data.objects.new(card["name"], data)
        scene.collection.objects.link(light)
        look(light, card["at"], card.get("aim", [card["at"][0], 0.0, card["at"][2]]))

    sky = st.get("world") or {}
    world = bpy.data.worlds.new("set air")
    world.use_nodes = True
    air = world.node_tree.nodes["Background"]
    air.inputs[0].default_value = tuple(sky.get("color", [0.8, 0.8, 0.8])) + (1.0,)
    air.inputs[1].default_value = float(sky.get("strength", 0.5))
    scene.world = world

    cameras = {}
    for name, card in (st.get("cameras") or {}).items():
        data = bpy.data.cameras.new("camera: " + name)
        data.lens, data.sensor_width = float(card["lens_mm"]), standing.SENSOR_MM
        data.clip_start, data.clip_end = 0.1, 200.0
        cam = bpy.data.objects.new("camera: " + name, data)
        scene.collection.objects.link(cam)
        look(cam, card["at"], card["aim"])
        cameras[name] = cam
    return cameras


def place_camera(cam, where):
    """Put a camera where a moving camera is at one moment (camera_path.sample: at, aim, lens_mm)."""
    look(cam, where["at"], where["aim"])
    cam.data.lens = float(where["lens_mm"])


def moving_cameras(plan, scene, frames, fps=30):
    """A shot's own cameras that move (plan.json's moving_cameras, scripts/sets/camera_path.py), keyed on every
    frame so a film of the whole shot follows them. Returns {camera name: camera object}."""
    import camera_path

    out = {}
    for name, path in (plan.get("moving_cameras") or {}).items():
        data = bpy.data.cameras.new("camera: " + name)
        data.sensor_width, data.clip_start, data.clip_end = standing.SENSOR_MM, 0.1, 200.0
        cam = bpy.data.objects.new("camera: " + name, data)
        scene.collection.objects.link(cam)
        for f in range(frames):
            place_camera(cam, camera_path.sample(path, f / float(fps)))
            cam.keyframe_insert("location", frame=f)
            cam.keyframe_insert("rotation_euler", frame=f)
            data.keyframe_insert("lens", frame=f)
        out[name] = cam
    return out


# ---- measuring, with everyone on the stage -----------------------------------------


def spread(values):
    values = sorted(values)
    return {"least": round(values[0], 1), "typical": round(values[len(values) // 2], 1), "most": round(values[-1], 1)}


def rig_of(objects):
    return next((o for o in objects if o.type == "ARMATURE"), None)


def wrist_and_palm(rig, objects):
    """Where a figure's right wrist is, and the middle of its right palm (the prop point in that hand, if the file has one)."""
    shown = rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
    bone = next((shown.pose.bones[name] for name in WRIST if name in shown.pose.bones), None)
    if bone is None:
        return None, None
    wrist = shown.matrix_world @ bone.head
    socket = next((o for o in objects if o.type == "EMPTY" and o.get("socket") == "hand_right"), None)
    if socket is not None:
        return wrist, socket.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.translation.copy()
    return wrist, shown.matrix_world @ (bone.head + (bone.tail - bone.head) * 0.5)


def hands_apart(scene, a, b, first, last):
    """Two people's right hands over a stretch of frames: {wrists, palms} apart, in cm, at least, typically and at most."""
    wrists, palms = [], []
    for f in range(first, last + 1):
        scene.frame_set(f)
        wa, pa = wrist_and_palm(*a)
        wb, pb = wrist_and_palm(*b)
        if wa is None or wb is None:
            return None
        wrists.append(100.0 * (wa - wb).length)
        palms.append(100.0 * (pa - pb).length)
    return {"frames": [first, last], "wrists_apart_cm": spread(wrists), "palms_apart_cm": spread(palms)}


def seat_gap(scene, objects, rig, st, span, every=4):
    """How far a seated figure is from its seat, in cm: the lowest point of its mesh over the seat, against the
    seat's top. Positive floats above it; negative is sunk into it."""
    block = standing.block_named(st, span["seat"])
    if block is None or rig is None:
        return None
    top = standing.top_of(block)
    meshes = [o for o in objects if o.type == "MESH" and o.find_armature() == rig]
    gaps = []
    for f in range(span["from_frame"], span["to_frame"] + 1, every):
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
        low = None
        for obj in meshes:
            shown = obj.evaluated_get(deps)
            me = shown.to_mesh()
            for v in me.vertices:
                x, y, z = from_blender(shown.matrix_world @ v.co)
                if y < top + UNDERSIDE and standing.gap_to(block, x, z) == 0.0 and (low is None or y < low):
                    low = y
            shown.to_mesh_clear()
        if low is not None:
            gaps.append(100.0 * (low - top))
    if not gaps:
        return {"mark": span["mark"], "seat": span["seat"], "frames": [span["from_frame"], span["to_frame"]], "over_the_seat": False}
    return {"mark": span["mark"], "seat": span["seat"], "frames": [span["from_frame"], span["to_frame"]], "over_the_seat": True, "gap_cm": spread(gaps),
            "last_frame_gap_cm": round(gaps[-1], 1)}
