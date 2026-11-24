"""Cuts a rigged character into rigid parts, one per bone, and pictures each part from all around.

    Blender -b --factory-startup -P scripts/impostor/bake_impostor.py -- <run> <profile>
        [--look comic|pixel|joe] [--head-px 2] [--face auto|none|FILE] [--plays painted] [--title "Detailed model"] [--soften 128] [--views 26,62] [--px 192] [--overlap 0.25] [--trunk-overlap 0.04] [--ink-cm 1.4] [--rest-pose] [--out DIR] [--name impostor]

Reads <run>/profiles/<profile>-walk.glb (the file the page plays, so a bone's frame here is exactly
its frame there) and writes <run>/profiles/<profile>-impostor/:

    impostor.json            the parts, their bones, the view sets, where each picture is on its sheet
                             ("cells": x, y, wide, tall on the sheet from its bottom left; where the bone's
                             head is in the picture; the lowest and highest its surface stands, in metres)
    views<N>-color.png       every part from every direction of set N: flat comic colour and the ink line
    views<N>-data.png        the same pictures as numbers: which way the surface faces (red, green) and
                             how far it stands toward the eye (blue; 0 means nothing is there)

How a part is cut. Every face goes to the part whose bones pull on it most (fingers fold into the hand,
toes into the foot, shoulders and neck into the chest; a bone the list does not know folds into the
nearest one above it that it does). Then each part also takes the faces next door that its bones pull
on by at least --overlap, so two parts lap over each other at a joint and a bent elbow stays closed.
The trunk's parts (hips, spine, chest, head) lap much further (--trunk-overlap): they are thick, so a card
drawn a little off its true direction slides its front surface sideways by centimetres, and they hardly
bend against each other, so a long lap never pokes out.

How a part is pictured. The part is laid in its bone's own frame and drawn with no perspective from
each direction of the set (impostor.py: views_of), by toon.py with the tones of light switched off:
the flat colours and the ink line, nothing else. Light and shade are not baked in. The page works them
out from the stored facing, so a forearm is lit from the same side whichever way it is turned.
Every part of one direction is drawn in one render, each in its own square; the squares are then
trimmed to what is in them and packed onto one sheet.

--plays names the rigged version whose clips the cards play, when the one pictured is not it: a detailed mesh
given another version's skeleton (rig_detailed.py) is pictured, and the cards then play that version's walk,
routine and fights. --title is what the page calls this choice. --soften is how many pixels wide toon.py
reads a texture at (smaller is flatter; a detailed mesh wants more than a painted one).

--look bakes a sheet for one of the page's other looks, into <version>-impostor-<look>/:
    pixel   pixel art: 48 pixels a metre, no smoothing, every colour snapped to the 32 this character is most
            made of, a line one pixel wide drawn round each picture; the page reads it without smoothing either.
            When the character has a recipe for a face drawn on this model (pixel_face.py), the head is
            pictured twice as fine as the body (--head-px says otherwise) and the face is drawn on purpose;
            --face none leaves it as rendered. A sheet with either goes into
            <version>-impostor-pixel-faces/, which pages older than it do not read. With no recipe the sheet
            is as it always was.
    joe     bold ink: no line round the parts (the page draws the outside line itself, the same width on the
            screen however small the figure), and the lines inside a part drawn into its picture

Prints IMPOSTOR lines and one RESULT {json}. Never touches an open Blender.
"""

import json
import math
import os
import sys
import time

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import impostor  # noqa: E402
import pixel_face  # noqa: E402

TOON = os.path.join(REPO, ".claude", "skills", "tidy-mesh", "scripts", "toon.py")
# The parts, and the bones each is made of. The first bone is the one the card rides on.
PARTS = [("hips", ["hips"]), ("spine", ["spine"]), ("chest", ["chest", "shoulder_l", "shoulder_r", "neck"]), ("head", ["head"])]
for side in ("l", "r"):
    PARTS += [("upper_arm_" + side, ["upper_arm_" + side]), ("forearm_" + side, ["forearm_" + side]), ("hand_" + side, ["hand_" + side]),
              ("thigh_" + side, ["thigh_" + side]), ("shin_" + side, ["shin_" + side]), ("foot_" + side, ["foot_" + side, "toe_" + side])]
TO_GLB = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))  # Blender's z-up to a .glb's y-up
EYE_AWAY = 10.0   # how far off the eye stands while picturing (m); nothing depends on it
GUTTER = 2        # empty pixels between pictures on a sheet
ROW_PX = 1400     # how wide one render of all the parts may be
TRUNK = ("hips", "spine", "chest", "head")  # thick parts that hardly bend against each other: they lap over each other much further
HANG = ("shoulder", "upper_arm", "forearm", "hand")  # the bones that are pictured as they hang in the clip, not as they rest


def hang_arms(scene, rig):
    """Stand the skeleton as it is pictured: at rest, but with the arms where they are on average through the
    file's own clip. A rig rests with its arms straight out; nobody walks or fights like that, and a part is only
    exact near the pose it was cut in, so the arms are cut hanging. Returns how far each upper arm was lowered (deg)."""
    action = rig.animation_data.action if rig.animation_data else None
    first, last = (int(action.frame_range[0]), int(action.frame_range[1])) if action else (0, 0)
    arms = [b for b in rig.pose.bones if b.name.startswith(HANG)]
    total = {b.name: np.zeros(4) for b in arms}
    for f in range(first, last + 1):
        scene.frame_set(f)
        for b in arms:
            q = np.array(b.rotation_quaternion[:]) if b.rotation_mode == "QUATERNION" else np.array(b.rotation_euler.to_quaternion()[:])
            total[b.name] += q if q @ (total[b.name] if total[b.name].any() else q) >= 0 else -q
    if rig.animation_data:
        rig.animation_data_clear()
    lowered = {}
    for b in rig.pose.bones:
        b.location, b.scale = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
        b.rotation_mode = "QUATERNION"
        q = total.get(b.name)
        b.rotation_quaternion = tuple(q / np.linalg.norm(q)) if q is not None and q.any() else (1.0, 0.0, 0.0, 0.0)
        if b.name.startswith("upper_arm"):
            lowered[b.name] = round(math.degrees(2.0 * math.acos(min(1.0, abs(b.rotation_quaternion[0])))), 1)
    bpy.context.view_layer.update()
    return lowered


def run_toon(**params):
    with open(TOON) as f:
        source = f.read()
    space = {"__name__": "__main__"}
    head, _, tail = source.partition("\nimport ")
    exec(head, space)
    space["PARAMS"].update(params)
    exec("import " + tail, space)


def part_of_bone(rig):
    """{bone name: part name}: a bone no part names folds into the nearest bone above it that one does."""
    known = {bone: name for name, bones in PARTS for bone in bones}
    out = {}
    for bone in rig.data.bones:
        up = bone
        while up is not None and up.name not in known:
            up = up.parent
        out[bone.name] = known[up.name] if up is not None else "hips"
    return out


def cut(objects, rig, overlap, trunk_overlap):
    """{part name: [(object, [face indices], lapped over from next door?)]} and how many triangles each part owns outright."""
    folds = part_of_bone(rig)
    names = [name for name, _ in PARTS]
    column = {name: i for i, name in enumerate(names)}
    out, own = {name: [] for name in names}, {name: 0 for name in names}
    for obj in objects:
        me = obj.data
        pull = np.zeros((len(me.vertices), len(names)), dtype=np.float32)
        groups = [folds.get(g.name) for g in obj.vertex_groups]
        for v in me.vertices:
            for g in v.groups:
                part = groups[g.group]
                if part is not None:
                    pull[v.index, column[part]] += g.weight
        pull /= np.maximum(pull.sum(axis=1, keepdims=True), 1e-9)
        chosen, lapped = {name: [] for name in names}, {name: [] for name in names}
        for poly in me.polygons:
            share = pull[list(poly.vertices)].mean(axis=0)
            best = int(share.argmax())
            own[names[best]] += len(poly.vertices) - 2
            chosen[names[best]].append(poly.index)
            for i, name in enumerate(names):
                if i != best and share[i] >= (trunk_overlap if name in TRUNK else overlap):
                    lapped[name].append(poly.index)
        for name in names:
            if chosen[name]:
                out[name].append((obj, chosen[name], False))
            if lapped[name]:
                out[name].append((obj, lapped[name], True))
    return out, own


def piece(obj, posed, faces, into):
    """A copy of some of an object's faces, as they stand in the baking pose (`posed`: the mesh with the
    skeleton's pull already in its points), moved by the matrix `into`."""
    data = posed.copy()
    bm = bmesh.new()
    bm.from_mesh(data)
    bm.faces.ensure_lookup_table()
    keep = set(faces)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
    bm.to_mesh(data)
    bm.free()
    data.transform(into)
    data.update()
    new = bpy.data.objects.new("part: " + obj.name, data)
    bpy.context.scene.collection.objects.link(new)
    return new


def data_material(name, ink):
    """Paints which way a surface faces, as the eye sees it (red: right, green: up), and how far it stands
    toward the eye from the bone's head (blue), all as plain numbers around a half. The ink line's own
    version paints nothing (black): that is how its pixels are told from the surface's afterwards."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.use_backface_culling = ink
    tree = mat.node_tree
    tree.nodes.clear()
    if ink:
        glow, out = tree.nodes.new("ShaderNodeEmission"), tree.nodes.new("ShaderNodeOutputMaterial")
        glow.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        tree.links.new(glow.outputs[0], out.inputs["Surface"])
        return mat
    shape = tree.nodes.new("ShaderNodeNewGeometry")
    seen = tree.nodes.new("ShaderNodeVectorTransform")
    seen.vector_type, seen.convert_from, seen.convert_to = "NORMAL", "WORLD", "CAMERA"
    tree.links.new(shape.outputs["Normal"], seen.inputs[0])
    split = tree.nodes.new("ShaderNodeSeparateXYZ")
    tree.links.new(seen.outputs[0], split.inputs[0])
    eye = tree.nodes.new("ShaderNodeCameraData")

    def half(socket, scale, add):
        node = tree.nodes.new("ShaderNodeMath")
        node.operation = "MULTIPLY_ADD"
        tree.links.new(socket, node.inputs[0])
        node.inputs[1].default_value, node.inputs[2].default_value = scale, add
        return node.outputs[0]

    join = tree.nodes.new("ShaderNodeCombineXYZ")
    tree.links.new(half(split.outputs[0], 0.5, 0.5), join.inputs[0])
    tree.links.new(half(split.outputs[1], 0.5, 0.5), join.inputs[1])
    tree.links.new(half(eye.outputs["View Z Depth"], -0.5, 0.5 + 0.5 * EYE_AWAY), join.inputs[2])
    glow = tree.nodes.new("ShaderNodeEmission")
    tree.links.new(join.outputs[0], glow.inputs["Color"])
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(glow.outputs[0], out.inputs["Surface"])
    return mat


def retag(group, objects):
    """Say out loud that the ink's material changed: without this the next render still draws the last one."""
    group.update_tag()
    for obj in objects:
        obj.update_tag()
    bpy.context.view_layer.update()


def pixels_of(path, plain=False):
    image = bpy.data.images.load(path)
    if plain:
        image.colorspace_settings.name = "Non-Color"
    wide, tall = image.size
    got = np.empty(wide * tall * 4, dtype=np.float32)
    image.pixels.foreach_get(got)
    bpy.data.images.remove(image)
    return got.reshape(tall, wide, 4)


def spread(values, known, rounds):
    """Fill pixels that have no value from a neighbour that has, a ring at a time."""
    values, known = values.copy(), known.copy()
    for _ in range(rounds):
        if known.all():
            break
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            near_v = np.roll(values, (dy, dx), axis=(0, 1))
            near_k = np.roll(known, (dy, dx), axis=(0, 1))
            take = near_k & ~known
            values[take] = near_v[take]
            known = known | take
    return values


def pack(sizes):
    """Shelves: [(w, h)] to ([(x, y)], sheet width, sheet height). The width is picked to leave the sheet near square."""
    area = sum((w + GUTTER) * (h + GUTTER) for w, h in sizes)
    best = None
    for wide in (256, 512, 1024, 2048, 4096):
        if wide < max(w for w, _ in sizes) + GUTTER:
            continue
        spots, x, y, shelf = [None] * len(sizes), GUTTER, GUTTER, 0
        for i in sorted(range(len(sizes)), key=lambda i: -sizes[i][1]):
            w, h = sizes[i]
            if x + w + GUTTER > wide:
                x, y, shelf = GUTTER, y + shelf + GUTTER, 0
            spots[i] = (x, y)
            x, shelf = x + w + GUTTER, max(shelf, h)
        tall = (y + shelf + GUTTER + 3) // 4 * 4
        if best is None or max(wide, tall) < max(best[1], best[2]) or (max(wide, tall) == max(best[1], best[2]) and wide * tall < best[1] * best[2]):
            best = (spots, wide, tall)
    return best + (area,)


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    run, profile = os.path.abspath(args[0]), args[1]
    look = flag("--look", "comic")
    sets = flag("--views", "26,62" if look == "comic" else "26").split(",")
    ppm = float(flag("--px", "48" if look == "pixel" else "192"))
    overlap = float(flag("--overlap", "0.25"))
    trunk_overlap = float(flag("--trunk-overlap", "0.04"))
    # pixel art: the line is one pixel of the sheet. bold ink: no line round the part at all (the page draws it)
    ink_m = float(flag("--ink-cm", str(100.0 / ppm) if look == "pixel" else "0" if look == "joe" else "1.4")) / 100.0
    colours = int(flag("--colours", "32" if look == "pixel" else "0"))
    source = flag("--source", os.path.join(run, "profiles", profile + "-walk.glb"))
    # Pixel art: the head finer than the body, and a face drawn on purpose from the character's recipe.
    face = flag("--face", "auto" if look == "pixel" else "none")
    if face == "auto":
        # A recipe was drawn on one model's head and fits no other: the painted head's eyes are not where the
        # detailed head's are. Left to itself the bake uses it only for the model it says it was drawn on.
        recipe = pixel_face.recipe_for(run)
        if recipe and recipe.get("drawn_on", profile) != profile:
            print("IMPOSTOR face: the recipe was drawn on the %s model, not %s: left off (--face FILE to use one anyway)" % (recipe["drawn_on"], profile), flush=True)
            recipe = None
    elif face == "none":
        recipe = None
    else:
        with open(face) as f:
            recipe = json.load(f)
    head_px = float(flag("--head-px", "2" if recipe else "1"))  # a finer head comes with a drawn face, unless asked for
    finer = {"head": head_px} if head_px != 1.0 else {}
    plain = "impostor" if look == "comic" else "impostor-" + look
    out = os.path.abspath(flag("--out", os.path.join(run, "profiles", "%s-%s" % (profile, flag("--name", plain + "-faces" if look == "pixel" and (finer or recipe) else plain)))))
    os.makedirs(out, exist_ok=True)
    began = time.time()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.import_scene.gltf(filepath=source)
    rig = next(o for o in scene.objects if o.type == "ARMATURE")
    bodies = [o for o in scene.objects if o.type == "MESH" and o.find_armature() and not o.get("under")]
    rest = impostor.Glb(source).pose(None)
    lowered = hang_arms(scene, rig) if "--rest-pose" not in args else {}
    graph = bpy.context.evaluated_depsgraph_get()
    posed = {o.name: bpy.data.meshes.new_from_object(o.evaluated_get(graph)) for o in bodies}
    whole_triangles = sum(len(p.vertices) - 2 for o in bodies for p in o.data.polygons)

    # The parts, each in its bone's own frame.
    chosen, own = cut(bodies, rig, overlap, trunk_overlap)
    parts, made = [], {}
    for name, bones in PARTS:
        if not chosen[name] or bones[0] not in rest:
            continue
        # where the bone's frame is in the baking pose: the bone's own move from rest, then its rest frame
        moved = rig.pose.bones[bones[0]].matrix @ rig.data.bones[bones[0]].matrix_local.inverted()
        into = Matrix(np.linalg.inv(rest[bones[0]]).tolist()) @ TO_GLB @ moved.inverted()
        objects = []
        for obj, faces, lap in chosen[name]:
            objects.append(piece(obj, posed[obj.name], faces, into))
            objects[-1]["lap"] = lap
        points = np.array([v.co[:] for o in objects for v in o.data.vertices])
        reach = float(np.linalg.norm(points, axis=1).max()) + ink_m
        lo, hi = points.min(axis=0), points.max(axis=0)
        made[name] = objects
        parts.append({"name": name, "bone": bones[0], "bones": bones, **({"px_per_m": ppm * finer[name]} if name in finer else {}), "center": [round(float(c), 4) for c in (lo + hi) / 2.0],
                      "depth_m": round(reach + 0.01, 4), "reach_m": round(reach, 4),
                      "triangles": sum(len(p.vertices) - 2 for o in objects for p in o.data.polygons), "own_triangles": own[name]})
    for obj in list(scene.objects):
        if obj.type in ("MESH", "ARMATURE", "EMPTY") and not obj.name.startswith("part: "):
            bpy.data.objects.remove(obj)

    # The face: each of the recipe's marks found on the head's own surface, from straight in front.
    marks = []
    if recipe and "head" in made:
        points, faces = [], []
        for obj in made["head"]:
            first = len(points)
            points += [v.co.copy() for v in obj.data.vertices]
            faces += [[first + i for i in poly.vertices] for poly in obj.data.polygons]
        tree = BVHTree.FromPolygons(points, faces)

        def front_at(x, y):
            hit = tree.ray_cast(Vector((x, y, 2.0)), Vector((0.0, 0.0, -1.0)))
            return None if hit[0] is None else hit[0].z

        marks = pixel_face.place(recipe, front_at)
        print("IMPOSTOR face: %d of the recipe's %d marks found on the head" % (len(marks), len(recipe.get("marks", []))), flush=True)

    # One square each, in rows: where every part's bone head sits in the render.
    half = {p["name"]: int(math.ceil((p["reach_m"] * ppm + 3) * finer.get(p["name"], 1.0))) for p in parts}
    spots, x, y, shelf = {}, 0, 0, 0
    for p in sorted(parts, key=lambda p: -half[p["name"]]):
        side = 2 * half[p["name"]]
        if x + side > ROW_PX and x > 0:
            x, y, shelf = 0, y + shelf, 0
        spots[p["name"]] = (x + side // 2, y + side // 2)
        x, shelf = x + side, max(shelf, side)
    wide, tall = max(sx + half[n] for n, (sx, sy) in spots.items()), y + shelf
    wide, tall = wide + wide % 2, tall + tall % 2

    cam_data = bpy.data.cameras.new("eye")
    cam_data.type, cam_data.ortho_scale, cam_data.clip_start, cam_data.clip_end = "ORTHO", max(wide, tall) / ppm, 0.1, 2.0 * EYE_AWAY
    cam = bpy.data.objects.new("eye", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = wide, tall, 100
    # Pixel art gets its line afterwards, one pixel all round each picture: a shell on so coarse a grid speckles
    # every fold of a detailed mesh with ink.
    run_toon(shade=[[1.0, 1.0, 1.0], [1.0, 1.0, 1.0]], line_px=0 if look == "pixel" else ink_m * ppm, background=None, samples=16, **({"levels": 6} if look == "pixel" else {}), **({"soften": int(flag("--soften", "64"))} if look == "pixel" or "--soften" in args else {}))
    # The faces a part borrows from next door get no ink line of their own: the line there is the neighbour's
    # to draw. Left on, a limb's line ran on up into the shoulder and showed as scratches over the chest.
    for objects in made.values():
        for obj in objects:
            if obj.get("lap"):
                for mod in [m for m in obj.modifiers if m.name == "comic ink"]:
                    obj.modifiers.remove(mod)
    data_mat, data_ink = data_material("impostor data", False), data_material("impostor data ink", True)
    ink_group = bpy.data.node_groups.get("comic ink")
    ink_mat = bpy.data.materials.get("comic ink")
    part_objects = [o for objects in made.values() for o in objects]
    painted = {o.name: list(o.data.materials) for o in part_objects}
    tmp_colour, tmp_data = os.path.join(out, ".bake-colour.png"), os.path.join(out, ".bake-data.exr")

    card = {"format": "forge-impostor/1", "source": os.path.basename(source), "profile": profile, "look": look, "nearest": look == "pixel", "plays": flag("--plays", profile), "title": flag("--title", ""), "px_per_m": ppm, "ink_m": ink_m, "overlap": overlap, "trunk_overlap": trunk_overlap, "arms_lowered_deg": lowered,
            "light": list(impostor.LIGHT), "shade": [list(s) for s in impostor.SHADE], "edges": list(impostor.EDGES),
            "march": {"px": impostor.MARCH_PX, "max": impostor.MARCH_MAX, "refine": impostor.REFINE, "wall_m": impostor.WALL_M}, "blend_deg": impostor.BLEND_DEG, "hold_deg": impostor.HOLD_DEG,
            "parts": parts, "triangles": whole_triangles, "default_views": sets[0], "sets": {}}
    for set_name in sets:
        views = impostor.views_of(set_name)
        pictures = []  # (part, view, colour, data)
        heads = []     # the head's pictures, kept as they stand to have the face drawn on: (view, colour, height, where the head is, where the bone's head is)
        for vi, view in enumerate(views):
            d, r, u = Vector(view["d"]), Vector(view["r"]), Vector(view["u"])
            cam.matrix_world = Matrix(((r.x, u.x, d.x, d.x * EYE_AWAY), (r.y, u.y, d.y, d.y * EYE_AWAY), (r.z, u.z, d.z, d.z * EYE_AWAY), (0, 0, 0, 1)))
            for p in parts:
                sx, sy = spots[p["name"]]
                at = r * ((sx - wide / 2.0) / ppm) + u * ((sy - tall / 2.0) / ppm)
                for obj in made[p["name"]]:
                    obj.matrix_world = Matrix.Translation(at) @ Matrix.Diagonal((finer.get(p["name"], 1.0),) * 3 + (1.0,))  # a finer part is pictured larger
            # colour and line
            for obj in part_objects:
                for i, mat in enumerate(painted[obj.name]):
                    obj.data.materials[i] = mat
            if ink_group:
                ink_group.nodes["Ink"].inputs["Material"].default_value = ink_mat
                retag(ink_group, part_objects)
            # pixel art is not smoothed: a pixel is one colour of the surface under its middle
            scene.eevee.taa_render_samples, scene.render.filter_size = (1, 0.01) if look == "pixel" else (16, 0.8)
            scene.render.image_settings.file_format, scene.render.image_settings.color_mode = "PNG", "RGBA"
            scene.render.image_settings.color_depth = "8"
            scene.render.filepath = tmp_colour
            bpy.ops.render.render(write_still=True)
            colour = pixels_of(tmp_colour)
            # facing and depth
            for obj in part_objects:
                for i in range(len(obj.data.materials)):
                    obj.data.materials[i] = data_mat
            if ink_group:
                ink_group.nodes["Ink"].inputs["Material"].default_value = data_ink
                retag(ink_group, part_objects)
            scene.eevee.taa_render_samples, scene.render.filter_size = 1, 0.01
            scene.render.image_settings.file_format, scene.render.image_settings.color_mode = "OPEN_EXR", "RGBA"
            scene.render.image_settings.color_depth = "32"
            scene.render.filepath = tmp_data
            bpy.ops.render.render(write_still=True)
            data = pixels_of(tmp_data, plain=True)
            for p in parts:
                sx, sy = spots[p["name"]]
                hs = half[p["name"]]
                fine = finer.get(p["name"], 1.0)
                col = colour[sy - hs:sy + hs, sx - hs:sx + hs].copy()
                dat = data[sy - hs:sy + hs, sx - hs:sx + hs]
                if fine != 1.0:  # pictured larger, so everything stood further forward too
                    dat = dat.copy()
                    dat[..., 2] = (dat[..., 2] - 0.5) / fine + 0.5
                # The outline is the unsmoothed one: a pixel is the part or it is not. A soft edge would lose the
                # thin ink line when the card is drawn (it is kept where the cover is over a half). The colour
                # under it is the smoothed render's, carried a pixel outward where that one had not reached.
                there = dat[..., 3] > 0.5
                if look == "pixel":
                    grown = there
                    for _ in range(max(1, int(round(fine)))):  # the line is as wide on a finer part as on the rest
                        grown = grown | np.roll(grown, 1, 0) | np.roll(grown, -1, 0) | np.roll(grown, 1, 1) | np.roll(grown, -1, 1)
                    ring = grown & ~there
                    dat = dat.copy()
                    dat[ring] = (0.0, 0.0, 0.0, 1.0)  # marked as line, as the shell's pixels are: it takes its depth from the surface beside it
                    col[..., :3] = np.where(ring[..., None], (0.11, 0.09, 0.13), col[..., :3])
                    col[..., 3] = np.where(ring, 1.0, col[..., 3])
                    there = there | ring
                col[..., :3] = spread(col[..., :3], col[..., 3] > 0.5, 3)
                col[..., 3] = there
                if not there.any():
                    pictures.append((p, vi, None, None, (0, 0), (0.0, 0.0)))
                    continue
                ys, xs = np.where(there)
                x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
                # the facing as the bone has it, and the depth as a share of the part's reach
                known = dat[..., 3] > 0.5
                # The ink line is a shell behind the part, centimetres further back than the surface it outlines.
                # Left there it would be slid apart from its own outline when the card is drawn from a little to one
                # side. So the line takes the depth of the surface next to it, and faces the eye.
                line = known & (dat[..., 0] < 0.02) & (dat[..., 1] < 0.02) & (dat[..., 2] < 0.02)
                dat = dat.copy()
                dat[..., :3] = np.where(line[..., None], (0.5, 0.5, 0.5), dat[..., :3])
                dat[..., 2] = spread(dat[..., 2], known & ~line, 8)
                nx, ny = dat[..., 0] * 2.0 - 1.0, dat[..., 1] * 2.0 - 1.0
                nz = np.sqrt(np.clip(1.0 - nx * nx - ny * ny, 0.0, 1.0))
                normal = nx[..., None] * np.array(view["r"]) + ny[..., None] * np.array(view["u"]) + nz[..., None] * np.array(view["d"])
                height = (dat[..., 2] * 2.0 - 1.0) / p["depth_m"]
                # blue 0 is kept to mean "nothing here": the page's search down a pixel's line must know air from surface
                packed = np.concatenate([impostor.pack_normal(normal), np.clip(height * 0.5 + 0.5, 1.0 / 255.0, 1.0)[..., None]], axis=-1)
                packed[~known] = (0.5, 0.5, 0.0)
                if look == "joe":
                    # Bold ink: the lines inside a part are drawn here, into its picture: where the surface steps
                    # back by more than 2 cm from one pixel to the next (one fold of the body in front of another)
                    # or turns by more than about 70 degrees (a crease). The line goes on the further pixel.
                    metres_all = (dat[..., 2] * 2.0 - 1.0)
                    inked = np.zeros_like(known)
                    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                        near_h, near_n, near_k = np.roll(metres_all, (dy, dx), axis=(0, 1)), np.roll(normal, (dy, dx), axis=(0, 1)), np.roll(known, (dy, dx), axis=(0, 1))
                        inked |= known & near_k & ((near_h - metres_all > 0.02) | (((normal * near_n).sum(axis=-1) < 0.3) & (near_h >= metres_all)))
                    inked |= np.roll(inked, 1, axis=0) & known  # two pixels wide: about a centimetre
                    col[..., :3] = np.where(inked[..., None], (0.07, 0.055, 0.086), col[..., :3])
                metres = (np.round(packed[..., 2][known] * 255.0) / 255.0 * 2.0 - 1.0) * p["depth_m"]
                if marks and p["name"] == "head":
                    heads.append((vi, col[y0:y1, x0:x1], (dat[..., 2] * 2.0 - 1.0)[y0:y1, x0:x1], (known & ~line)[y0:y1, x0:x1], (hs - x0, hs - y0)))
                pictures.append((p, vi, col[y0:y1, x0:x1], packed[y0:y1, x0:x1], (hs - x0, hs - y0), (float(metres.min()), float(metres.max()))))
            if vi % 8 == 0:
                print("IMPOSTOR views %s: %d of %d pictured" % (set_name, vi + 1, len(views)), flush=True)
        palette, keep = None, []
        if heads:
            # The face, drawn into every picture of the head. What a wash finds is found once, from the front.
            head_ppm = ppm * finer.get("head", 1.0)
            least = pixel_face.least_for(head_ppm)
            vi, col, height, there, anchor = max(heads, key=lambda h: views[h[0]]["d"][2])
            found = pixel_face.find_colours(marks, col, height, there, views[vi], head_ppm, anchor)
            drawn = {}
            for vi, col, height, there, anchor in heads:
                for name, count in pixel_face.draw(col, height, there, views[vi], head_ppm, anchor, marks, recipe.get("colours", {}), found, least).items():
                    drawn[name] = drawn.get(name, 0) + (1 if count else 0)
            keep = pixel_face.kept_colours(marks, recipe.get("colours", {}), found)
            card["face"] = {"least_px": least, "marks": pixel_face.for_page(marks, recipe.get("colours", {}), found), "pictures_with": drawn}
            print("IMPOSTOR face: drawn in %s" % ", ".join("%s %d" % (k, v) for k, v in drawn.items()), flush=True)
        if colours:
            # Pixel art keeps to a few colours: the ones this character is most made of. Every pixel takes the nearest.
            seen = np.concatenate([pic[2][pic[2][..., 3] > 0.5][:, :3] for pic in pictures if pic[2] is not None])
            palette = pixel_face.few_colours(seen[:: max(1, len(seen) // 200000)], colours, keep)
            drawn_as = pixel_face.folded(palette, (recipe or {}).get("same"))  # colours the recipe says are one thing
            for pic in pictures:
                if pic[2] is not None:
                    pic[2][..., :3] = pixel_face.snap(pic[2][..., :3], palette, drawn_as)
            palette = np.unique(np.round(drawn_as * 255.0), axis=0).astype(np.float32) / 255.0
            card["palette"] = [[int(round(c * 255)) for c in colour] for colour in palette]
        sizes = [(pic[2].shape[1], pic[2].shape[0]) if pic[2] is not None else (1, 1) for pic in pictures]
        where, sheet_w, sheet_h, used = pack(sizes)
        colour_sheet = np.zeros((sheet_h, sheet_w, 4), dtype=np.uint8)
        data_sheet = np.zeros((sheet_h, sheet_w, 3), dtype=np.uint8)
        cells = {p["name"]: [None] * len(views) for p in parts}
        for (p, vi, col, dat, anchor, heights), (x, y), (w, h) in zip(pictures, where, sizes):
            if col is None:
                cells[p["name"]][vi] = [0, 0, 0, 0, 0, 0, 0.0, 0.0]
                continue
            colour_sheet[y:y + h, x:x + w] = np.round(np.clip(col, 0.0, 1.0) * 255.0)
            data_sheet[y:y + h, x:x + w] = np.round(np.clip(dat, 0.0, 1.0) * 255.0)
            cells[p["name"]][vi] = [int(x), int(y), int(w), int(h), int(anchor[0]), int(anchor[1]), round(heights[0], 4), round(heights[1], 4)]
        names = ("views%s-color.png" % set_name, "views%s-data.png" % set_name)
        impostor.write_png(os.path.join(out, names[0]), colour_sheet)
        impostor.write_png(os.path.join(out, names[1]), data_sheet)
        card["sets"][set_name] = {
            "color": names[0], "data": names[1], "size": [sheet_w, sheet_h], "views": views, "cells": cells,
            "pictures": len(pictures), "filled": round(used / float(sheet_w * sheet_h), 3),
            "bytes": {"color": os.path.getsize(os.path.join(out, names[0])), "data": os.path.getsize(os.path.join(out, names[1]))},
            # two sheets, four bytes a pixel each once a graphics card holds them
            "memory_mb": round(sheet_w * sheet_h * 8 / 1e6, 2),
        }
        print("IMPOSTOR views %s: %d pictures on a %dx%d sheet, %.1f MB in memory" % (set_name, len(pictures), sheet_w, sheet_h, sheet_w * sheet_h * 8 / 1e6), flush=True)
    for path in (tmp_colour, tmp_data):
        if os.path.exists(path):
            os.remove(path)
    card["seconds"] = round(time.time() - began, 1)
    with open(os.path.join(out, "impostor.json"), "w") as f:
        json.dump(card, f, indent=1)
    print("RESULT " + json.dumps({"folder": out, "parts": len(parts), "triangles": whole_triangles, "seconds": card["seconds"],
                                   "sets": {k: {"size": v["size"], "memory_mb": v["memory_mb"], "pictures": v["pictures"]} for k, v in card["sets"].items()}}))


main()
