"""Builds a diorama from its plan, in a background Blender.

    Blender -b --factory-startup -P scripts/diorama/build_diorama.py -- <name> [--runs runs] [--out DIR] [--draft [cameras]] [--no-stills]

Reads dioramas/<name>/diorama.json (scripts/diorama/diorama.py says what it holds) and

    cuts the slice of the set that is kept, stands its dressing and its backdrop behind it
    brings each toon in from its run, strikes its pose, stands it on its spot, turns its head
    puts each prop in its hand, beside it, on the floor or under another prop
    builds the wooden base under it all, with the brass plate on the front
    measures: nobody in anybody, feet on the floor, props in hands and on surfaces, everyone seen from the front

and writes, into dioramas/<name>/ (or --out):

    diorama.glb           everything on the base in one light file: no bones, Draco, WebP
    stills/<camera>.jpg   a picture through each camera named in `stills`, on a shelf in the basement
    stills/<camera>-small.jpg
    card.png              the first of those, small, for a card
    build.json            what was built and measured, and each camera as the gallery's view of it

--draft [camera,camera] takes small quick pictures into draft/ and writes nothing else: for trying a pose.
The runs are only read. Never touches an open Blender.
"""

import json
import math
import os
import sys
import time

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
for folder in ("diorama", "comic", "motion", "sets"):
    sys.path.insert(0, os.path.join(REPO, "scripts", folder))
import diorama  # noqa: E402
import set_contact  # noqa: E402
import stage  # noqa: E402
import standing  # noqa: E402

to_blender = set_contact.to_blender
from_blender = set_contact.from_blender
FONTS = ("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", "/System/Library/Fonts/Supplemental/Georgia.ttf")
STILL = (1600, 1000)
SMALL = (480, 300)
CARD = (800, 500)
DRAFT = (1120, 700)
SKIN_M = 0.015   # how far something is lifted before it is tried against what it stands on
HAND_M = 0.30    # a held thing may touch its holder this close to the hand
ON_M = 0.012     # feet and props are on their surface within this
SEEN = 0.4       # the share of a head that must show from the front
PEEK = 0.2       # ...and of someone who is only peeking in


# ---- small pieces ---------------------------------------------------------------


def collection(name, parent):
    made = bpy.data.collections.new(name)
    parent.children.link(made)
    return made


def move_to(objects, into):
    for obj in objects:
        for held in list(obj.users_collection):
            held.objects.unlink(obj)
        into.objects.link(obj)


def plain(name, color, rough=0.8, metal=0.0, glow=0.0):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
    shader.inputs["Roughness"].default_value = rough
    shader.inputs["Metallic"].default_value = metal
    if glow:
        shader.inputs["Emission Color"].default_value = (color[0], color[1], color[2], 1.0)
        shader.inputs["Emission Strength"].default_value = glow
    return mat


def pictured(name, image, rough=0.8, glow=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes["Principled BSDF"]
    picture = nodes.new("ShaderNodeTexImage")
    picture.image = image
    links.new(picture.outputs["Color"], shader.inputs["Base Color"])
    shader.inputs["Roughness"].default_value = rough
    if glow:
        links.new(picture.outputs["Color"], shader.inputs["Emission Color"])
        shader.inputs["Emission Strength"].default_value = glow
    return mat


class Shape:
    """A mesh put together from boxes, tubes and discs, each in a material, in Blender's axes."""

    def __init__(self, name):
        self.name, self.bm, self.materials = name, bmesh.new(), []
        self.uv = self.bm.loops.layers.uv.new("UVMap")

    def slot(self, material):
        if material not in self.materials:
            self.materials.append(material)
        return self.materials.index(material)

    def face(self, points, material, grain=None):
        """`grain` (a length in metres) lays a wood picture along the face's longer flat side."""
        verts = [self.bm.verts.new(p) for p in points]
        face = self.bm.faces.new(verts)
        face.material_index = self.slot(material)
        if grain:
            normal = (Vector(points[1]) - Vector(points[0])).cross(Vector(points[2]) - Vector(points[1])).normalized()
            along = Vector((0, 1, 0)) if abs(normal.x) > 0.9 else Vector((1, 0, 0))
            across = normal.cross(along).normalized()
            for loop in face.loops:
                loop[self.uv].uv = (loop.vert.co.dot(along) / grain, loop.vert.co.dot(across) / (grain * 0.25))
        return face

    def box(self, lo, hi, material, grain=None):
        (x0, y0, z0), (x1, y1, z1) = lo, hi
        c = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        for quad in ((3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self.face([c[i] for i in quad], material, grain)

    def tube(self, a, b, ra, rb, material, sides=6, caps=True):
        a, b = Vector(a), Vector(b)
        axis = (b - a).normalized()
        side = axis.orthogonal().normalized()
        other = axis.cross(side)
        ring = lambda at, r: [at + (side * math.cos(i * 2 * math.pi / sides) + other * math.sin(i * 2 * math.pi / sides)) * r for i in range(sides)]
        low, high = ring(a, ra), ring(b, rb)
        for i in range(sides):
            j = (i + 1) % sides
            self.face([low[i], low[j], high[j], high[i]], material)
        if caps:
            self.face(list(reversed(low)), material)
            self.face(high, material)

    def finish(self, into, smooth=False):
        mesh = bpy.data.meshes.new(self.name)
        self.bm.normal_update()
        self.bm.to_mesh(mesh)
        self.bm.free()
        for material in self.materials:
            mesh.materials.append(material)
        for poly in mesh.polygons:
            poly.use_smooth = smooth
        obj = bpy.data.objects.new(self.name, mesh)
        into.objects.link(obj)
        return obj


def mesh_points(objects):
    """Every point of some mesh objects, where they are in the scene."""
    points = []
    for obj in objects:
        if obj.type == "MESH":
            world = obj.matrix_world
            points.extend(world @ v.co for v in obj.data.vertices)
    return points


def bounds(points):
    return Vector([min(p[i] for p in points) for i in range(3)]), Vector([max(p[i] for p in points) for i in range(3)])


def tree_of(objects, lift=0.0):
    """Something to try against other things: its triangles, where they are in the scene (lifted a little, to forgive standing on something)."""
    verts, polys = [], []
    for obj in objects:
        if obj.type != "MESH":
            continue
        base, world = len(verts), obj.matrix_world
        verts.extend(world @ v.co + Vector((0.0, 0.0, lift)) for v in obj.data.vertices)
        polys.extend([base + i for i in p.vertices] for p in obj.data.polygons)
    return (BVHTree.FromPolygons(verts, polys, epsilon=0.0) if polys else None), verts, polys


def meshes_under(holder):
    return [o for o in holder.children_recursive if o.type == "MESH"]


# ---- the set, cut like a cake -----------------------------------------------------


def cut_to(obj, keep, top, floor):
    """Keep only what of a mesh is inside the slice; the cut faces are closed and take the color beside them."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    color = bm.loops.layers.color.active or bm.loops.layers.float_color.active
    walls = [((keep["x"][0], 0, 0), (-1, 0, 0)), ((keep["x"][1], 0, 0), (1, 0, 0)), ((0, -keep["z"][1], 0), (0, -1, 0)), ((0, -keep["z"][0], 0), (0, 1, 0)),
             ((0, 0, top), (0, 0, 1)), ((0, 0, floor), (0, 0, -1))]
    for at, out in walls:
        cut = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-5, plane_co=at, plane_no=out, clear_outer=True)
        edges = [e for e in cut["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
        if not edges or out[2] < 0:  # what is under the floor is inside the base: left open
            continue
        for face in bmesh.ops.edgeloop_fill(bm, edges=edges)["faces"]:
            beside = next((f for e in face.edges for f in e.link_faces if f is not face), None)
            if color and beside:
                for loop in face.loops:
                    loop[color] = beside.loops[0][color]
            if beside:
                face.smooth = False
    left = len(bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.parent = None
    obj.matrix_world = Matrix.Identity(4)
    return left


def cropped_picture(st, option, keep, top, out_dir):
    """The part of a backdrop picture that hangs behind the slice, as its own small picture, and where it stands."""
    backdrop = st["backdrop"]
    cx, cy, _ = backdrop["center"]
    w, h = backdrop["width_m"], backdrop["height_m"]
    window = [b for b in st["blocks"] if b["name"] in ("window sill", "window header")]
    x0 = max(keep["x"][0] + 0.05, cx - w / 2, min((b["center"][0] - b["size"][0] / 2 for b in window), default=keep["x"][0]) - 0.35)
    x1 = min(keep["x"][1] - 0.05, cx + w / 2, max((b["center"][0] + b["size"][0] / 2 for b in window), default=keep["x"][1]) + 0.35)
    y0, y1 = max(0.0, cy - h / 2), min(top, cy + h / 2)
    image = bpy.data.images.load(os.path.join(st["dir"], option["image"]))
    wide, tall = image.size
    px = [int(round((x0 - (cx - w / 2)) / w * wide)), int(round((x1 - (cx - w / 2)) / w * wide)), int(round((y0 - (cy - h / 2)) / h * tall)), int(round((y1 - (cy - h / 2)) / h * tall))]
    import numpy

    pixels = numpy.empty(wide * tall * 4, dtype=numpy.float32)
    image.pixels.foreach_get(pixels)
    part = pixels.reshape(tall, wide, 4)[px[2]:px[3], px[0]:px[1]]
    small = bpy.data.images.new("backdrop: " + option["place"], part.shape[1], part.shape[0])
    small.pixels.foreach_set(part.ravel())
    small.filepath_raw = os.path.join(out_dir, "backdrop-part.png")
    small.file_format = "PNG"
    small.save()
    bpy.data.images.remove(image)
    return small, (x0, x1, y0, y1)


def stand_set(spec, st, into, out_dir):
    """The slice of the set, its dressing and its backdrop. Returns (the set's objects, the dressing's)."""
    card = spec["set"]
    keep, top = card["keep"], float(card["keep"].get("top_m", 3.5))
    geometry = st.get("geometry") or {}
    _, new = set_contact.bring_in(os.path.join(st["dir"], geometry.get("glb", "set.glb")), "set: whole", at=geometry.get("move", [0.0, 0.0, 0.0]), heading=geometry.get("turn_deg", 0.0))
    bpy.context.view_layer.update()
    kept = []
    for obj in new:
        if obj.type == "MESH" and cut_to(obj, keep, top, -0.004):
            obj.name = "set: " + st["name"]
            kept.append(obj)
        elif obj.type == "MESH":
            bpy.data.objects.remove(obj, do_unlink=True)
    for obj in [o for o in bpy.data.objects if o.name.startswith("set: whole")]:
        bpy.data.objects.remove(obj, do_unlink=True)
    move_to(kept, into)

    dressing = []
    slots = st.get("slots") or {}
    wanted = card.get("dressing")
    for item in st.get("dressing") or []:
        slot = slots[item["slot"]]
        inside = keep["x"][0] <= slot["at"][0] <= keep["x"][1] and keep["z"][0] <= slot["at"][2] <= keep["z"][1]
        if (item["prop"] not in wanted) if wanted is not None else not inside:
            continue
        holder, new = set_contact.bring_in(os.path.join(st["dir"], item["glb"]), "set dressing: " + item["prop"], at=slot["at"], heading=slot.get("heading", 0.0))
        move_to([holder] + new, into)
        dressing.append(holder)

    option = next((o for o in (st.get("backdrop_options") or {}).get("options") or [] if o["place"] == card.get("backdrop")), None)
    if option and st.get("backdrop"):
        image, (x0, x1, y0, y1) = cropped_picture(st, option, keep, top, out_dir)
        z = -(keep["z"][0] + 0.06)
        flat = Shape("set: backdrop")
        uv = flat.uv
        front = flat.face([(x0, z, y0), (x1, z, y0), (x1, z, y1), (x0, z, y1)], pictured("backdrop: " + option["place"], image, rough=1.0, glow=0.55))
        for loop, spot in zip(front.loops, ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))):
            loop[uv].uv = spot
        flat.box((x0, z + 0.004, y0), (x1, z + 0.03, y1), plain("backdrop: card", (0.74, 0.66, 0.54)))  # the card it is printed on, seen from behind
        kept.append(flat.finish(into))
    return kept, dressing


# ---- toons ----------------------------------------------------------------------


def hand_point(character, side):
    """The middle of a palm: the file's own prop point for that hand, or a little way along the hand's bone."""
    socket = character["sockets"].get("hand_" + side)
    if socket is not None:
        return socket.matrix_world.translation.copy()
    rig = character["rig"]
    bone = rig.pose.bones["hand_" + side[0]]
    return rig.matrix_world @ (bone.head + (bone.tail - bone.head) * 0.6)


def look(character, target, most_deg=62.0):
    """Turn the head (and the neck a little) so the face looks at a point of the scene."""
    rig = character["rig"]
    for name, share in (("neck", 0.35), ("head", 1.0)):
        if name not in rig.pose.bones:
            continue
        head = stage.head_of(character)
        want = (Vector(target) - head["center"]).normalized()
        turn = head["front"].rotation_difference(want)
        turn = Quaternion(turn.axis, min(turn.angle, math.radians(most_deg)) * share)
        bone = rig.pose.bones[name]
        pivot = rig.matrix_world @ bone.head
        moved = Matrix.Translation(pivot) @ turn.to_matrix().to_4x4() @ Matrix.Translation(-pivot)
        bone.matrix = rig.matrix_world.inverted() @ moved @ rig.matrix_world @ bone.matrix
        bpy.context.view_layer.update()


def stand_toon(card, spec, st, runs, poses):
    """One toon, brought in, posed and stood on its spot. Its skeleton is still on: hands and head are read from it."""
    character = stage.load_character(diorama.toon_file(runs, card, poses))
    kind = diorama.read_pose(card["pose"], poses)
    if kind[0] == "pose":
        stage.strike(character, kind[1])
        how = {"pose": card["pose"]}
    else:
        how = stage.freeze(character, kind[2])
    spot, floor, _ = diorama.spot_of(spec, st, card)
    heading = diorama.facing_of(spec, st, card)
    stage.stand_at(character, spot=(spot[0], -spot[1]), facing=math.radians(heading), floor=floor)
    character.update(card=card, spot=spot, floor=floor, heading=heading, how=how)
    return character


def freeze_toon(character, into):
    """The toon as it stands, with the pose in its meshes and the skeleton left behind."""
    graph = bpy.context.evaluated_depsgraph_get()
    holder = bpy.data.objects.new("toon: " + character["card"]["toon"], None)
    into.objects.link(holder)
    kept = []
    for obj in character["meshes"]:
        if obj.hide_render or obj.get("forge") == "prop":
            continue
        made = obj.evaluated_get(graph)
        mesh = bpy.data.meshes.new_from_object(made, preserve_all_data_layers=True, depsgraph=graph)
        still = bpy.data.objects.new("%s %s" % (character["card"]["toon"], obj.name.split(".")[0]), mesh)
        still.matrix_world = made.matrix_world.copy()
        into.objects.link(still)
        still.parent = holder
        if mesh.color_attributes:
            mesh.color_attributes.active_color = mesh.color_attributes[0]
            mesh.color_attributes.render_color_index = 0
        kept.append(still)
    for obj in character["objects"]:
        bpy.data.objects.remove(obj, do_unlink=True)
    set_contact.painted(kept)
    return holder, kept


# ---- props ----------------------------------------------------------------------

WOOD = (0.42, 0.27, 0.14)
BRASS = (0.72, 0.5, 0.17)


def legs(shape, tall, spread, thick, wood, brass):
    """Three legs from a small crown down to the floor."""
    crown = tall - 0.07
    for i in range(3):
        angle = math.radians(-90 + i * 120)  # one leg out front, two behind: room for whoever stands at it
        foot = (math.cos(angle) * spread, math.sin(angle) * spread, 0.0)
        shape.tube(foot, (math.cos(angle) * 0.035, math.sin(angle) * 0.035, crown), thick * 0.75, thick, wood)
        shape.tube(foot, (foot[0], foot[1], 0.035), thick * 1.25, thick * 0.9, brass)
    shape.tube((0, 0, crown - 0.07), (0, 0, crown + 0.02), 0.06, 0.06, brass, sides=8)


def build_prop(name, card, into):
    """A prop made here from a few plain shapes, standing at 0, 0, 0 and facing -y (the way a character is built)."""
    kind, size = card["built"], float(card.get("scale", 1.0))
    shape = Shape("prop: " + name)
    wood, brass = plain("prop: wood", card.get("wood", WOOD), rough=0.6), plain("prop: brass", BRASS, rough=0.35, metal=1.0)
    if kind == "tripod":
        tall = float(card.get("height_m", 1.1))
        legs(shape, tall, tall * 0.3, 0.028, wood, brass)
        shape.tube((0, 0, tall - 0.07), (0, 0, tall - 0.02), 0.03, 0.03, brass, sides=8)
        shape.box((-0.11, -0.11, tall - 0.025), (0.11, 0.11, tall), wood)
    elif kind == "teacup":
        cream, blue, tea = plain("prop: cup", (0.96, 0.94, 0.89), rough=0.3), plain("prop: cup rim", (0.267, 0.404, 0.608), rough=0.3), plain("prop: tea", (0.55, 0.3, 0.1), rough=0.2)
        shape.tube((0, 0, 0), (0, 0, 0.012 * size), 0.085 * size, 0.1 * size, cream, sides=10)
        shape.tube((0, 0, 0.012 * size), (0, 0, 0.075 * size), 0.036 * size, 0.062 * size, cream, sides=10, caps=False)
        shape.tube((0, 0, 0.075 * size), (0, 0, 0.088 * size), 0.062 * size, 0.064 * size, blue, sides=10, caps=False)
        shape.tube((0, 0, 0.07 * size), (0, 0, 0.078 * size), 0.055 * size, 0.058 * size, tea, sides=10)
        shape.box((0.058 * size, -0.008 * size, 0.03 * size), (0.092 * size, 0.008 * size, 0.07 * size), cream)
    elif kind == "softbox":
        tall = float(card.get("height_m", 1.9))
        black, glow = plain("prop: lamp", (0.08, 0.08, 0.09), rough=0.6), plain("prop: lamp light", (1.0, 0.93, 0.8), rough=0.9, glow=2.2)
        legs(shape, tall * 0.5, tall * 0.2, 0.024, black, brass)
        shape.tube((0, 0, tall * 0.5 - 0.07), (0, 0, tall - 0.3), 0.022, 0.018, black)
        tilt = Matrix.Translation((0, 0, tall - 0.3)) @ Matrix.Rotation(math.radians(-14), 4, "X")
        box = [(-0.34, -0.22, 0.0), (0.34, -0.22, 0.0), (0.34, 0.06, 0.0), (-0.34, 0.06, 0.0), (-0.34, -0.22, 0.6), (0.34, -0.22, 0.6), (0.34, 0.06, 0.6), (-0.34, 0.06, 0.6)]
        c = [tilt @ Vector(p) for p in box]
        for quad, material in (((3, 2, 1, 0), black), ((4, 5, 6, 7), black), ((0, 1, 5, 4), glow), ((1, 2, 6, 5), black), ((2, 3, 7, 6), black), ((3, 0, 4, 7), black)):
            shape.face([c[i] for i in quad], material)
    obj = shape.finish(into)
    holder = bpy.data.objects.new("prop: " + name, None)
    into.objects.link(holder)
    obj.parent = holder
    return holder


def bring_prop(name, card, runs, into):
    """A prop as an empty with its meshes under it: from a run's file, or built here."""
    if card.get("built"):
        return build_prop(name, card, into)
    holder, new = set_contact.bring_in(diorama.prop_file(runs, card), "prop: " + name, scale=float(card.get("scale", 1.0)))
    move_to([holder] + new, into)
    bpy.context.view_layer.update()
    return holder


def grip_point(holder, grip):
    """A named point of a prop, in the scene: the top, the bottom, the middle, the front, or a point of its own [x, y, z]."""
    bpy.context.view_layer.update()
    if isinstance(grip, list):
        return holder.matrix_world @ to_blender(grip)
    low, high = bounds(mesh_points(meshes_under(holder)))
    mid = (low + high) / 2
    if grip == "bottom":
        return Vector((mid.x, mid.y, low.z))
    if grip == "centre":
        return mid
    if grip == "front":
        return holder.matrix_world.translation + (holder.matrix_world.to_3x3() @ Vector((0, -1, 0))).normalized() * ((high - low).length / 2 * 0.6) + Vector((0, 0, mid.z - holder.matrix_world.translation.z))
    return Vector((mid.x, mid.y, high.z))


def put(holder, heading, point=None, at=None):
    """Turn a prop to a heading, then slide it so `point` (one of its own points, found again after the turn) lands on `at`."""
    holder.rotation_euler = (0.0, 0.0, math.radians(heading))
    bpy.context.view_layer.update()
    if at is not None:
        holder.location += Vector(at) - (point() if callable(point) else holder.matrix_world.translation)
        bpy.context.view_layer.update()


# ---- the base -------------------------------------------------------------------


def wood_picture(out_dir):
    """A small strip of wood grain, made from nothing: streaks along its length."""
    import numpy

    wide, tall = 256, 64
    rng = numpy.random.default_rng(28)
    v = numpy.linspace(0, 1, tall)[:, None]
    u = numpy.linspace(0, 1, wide)[None, :]
    streaks = sum(numpy.sin((v * f + rng.random()) * 2 * numpy.pi + numpy.sin(u * 2 * numpy.pi * k) * 0.6) * a for f, k, a in ((3, 1, 0.5), (7, 2, 0.3), (17, 1, 0.2), (31, 3, 0.12)))
    grain = 0.5 + 0.5 * streaks / 1.12 + (rng.random((tall, wide)) - 0.5) * 0.08
    light, dark = numpy.array([0.50, 0.31, 0.16]), numpy.array([0.38, 0.22, 0.11])
    rgb = dark + (light - dark) * numpy.clip(grain, 0, 1)[..., None]
    pixels = numpy.concatenate([rgb, numpy.ones((tall, wide, 1))], axis=2).astype(numpy.float32)
    image = bpy.data.images.new("wood grain", wide, tall)
    image.pixels.foreach_set(pixels.ravel())
    image.filepath_raw = os.path.join(out_dir, "wood-grain.png")
    image.file_format = "PNG"
    image.save()
    return image


def lettering(text, size, font, into, material, name):
    curve = bpy.data.curves.new(name, "FONT")
    curve.body, curve.size, curve.align_x, curve.align_y, curve.resolution_u = text, size, "CENTER", "CENTER", 2
    if font:
        curve.font = font
    made = bpy.data.objects.new(name + " curve", curve)
    into.objects.link(made)
    bpy.context.view_layer.update()
    mesh = bpy.data.meshes.new_from_object(made.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(made, do_unlink=True)
    mesh.materials.clear()
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    into.objects.link(obj)
    return obj


def build_plinth(spec, st, into, out_dir):
    """The wooden collector's base under the slice, with a brass plate on the front that says what this is."""
    card, keep = spec["plinth"], spec["set"]["keep"]
    m, tall = float(card["margin_m"]), float(card["height_m"])
    x0, x1, y0, y1 = keep["x"][0] - m, keep["x"][1] + m, -(keep["z"][1] + m), -(keep["z"][0] - m)
    wood = pictured("plinth: wood", wood_picture(out_dir), rough=0.45)
    shape = Shape("plinth: base")
    step, foot, lip = 0.12, 0.16, 0.07
    shape.box((x0 - step, y0 - step, -tall), (x1 + step, y1 + step, -tall + foot), wood, grain=1.8)
    shape.box((x0, y0, -tall + foot), (x1, y1, -lip), wood, grain=1.8)
    shape.box((x0 - step * 0.5, y0 - step * 0.5, -lip), (x1 + step * 0.5, y1 + step * 0.5, -0.006), wood, grain=1.8)
    ground = st.get("ground", {}).get("color", [0.8, 0.78, 0.74])
    shape.box((keep["x"][0], -keep["z"][1], -0.008), (keep["x"][1], -keep["z"][0], -0.004), plain("plinth: floor", card.get("floor", ground), rough=0.9))
    base = shape.finish(into)

    plate = card.get("label") or {}
    when = diorama.epoch(spec["epoch"]) or {}
    lines = plate.get("lines") or [spec["title"], "Epoch %s · %s" % (when.get("number", "?"), when.get("title", spec["epoch"]))]
    wide = min(float(plate.get("width_m", 2.3)), (x1 - x0) * 0.6)
    high = min(float(plate.get("height_m", 0.2)), tall - foot - lip - 0.04) if len(lines) < 2 else min(float(plate.get("height_m", 0.26)), tall - foot - lip - 0.03)
    mid_x, mid_z, front = (x0 + x1) / 2, (-tall + foot - lip) / 2, y0
    brass = plain("plinth: brass", BRASS, rough=0.42, metal=0.85)
    shape = Shape("plinth: plate")
    shape.box((mid_x - wide / 2, front - 0.012, mid_z - high / 2), (mid_x + wide / 2, front, mid_z + high / 2), brass)
    for side in (-1, 1):
        at = mid_x + side * (wide / 2 - 0.06)
        shape.tube((at, front - 0.012, mid_z), (at, front - 0.02, mid_z), 0.018, 0.014, plain("plinth: screw", (0.5, 0.36, 0.12), rough=0.4, metal=1.0), sides=6)
    made = [base, shape.finish(into)]
    font = next((bpy.data.fonts.load(path) for path in FONTS if os.path.isfile(path)), None)
    ink = plain("plinth: engraving", (0.07, 0.04, 0.02), rough=0.7)
    sizes = [high * 0.52, high * 0.26] if len(lines) > 1 else [high * 0.6]
    rows = [mid_z + high * 0.17, mid_z - high * 0.27] if len(lines) > 1 else [mid_z]
    for line, size, row in zip(lines, sizes, rows):
        text = lettering(line if font else line.replace("·", "-"), size, font, into, ink, "plinth: plate words")
        text.rotation_euler = (math.radians(90), 0.0, 0.0)
        text.location = (mid_x, front - 0.0135, row)
        made.append(text)
    bpy.context.view_layer.update()
    return made, {"across_m": round(x1 - x0 + 2 * step, 2), "deep_m": round(y1 - y0 + 2 * step, 2), "tall_m": tall, "plate": lines,
                  "toy": "1:%g, so %.0f cm across on the shelf" % (card.get("toy_scale", 12), (x1 - x0 + 2 * step) / float(card.get("toy_scale", 12)) * 100)}


def build_basement(spec, into, plinth_points):
    """Where the base stands, in the pictures only: a shelf under it and a plain warm wall behind."""
    card = spec.get("basement") or {}
    low, high = bounds(plinth_points)
    shape = Shape("basement: shelf")
    shape.box((low.x - 30, low.y - 1.3, low.z - 0.45), (high.x + 30, high.y + 2.4, low.z), plain("basement: shelf", card.get("shelf", (0.3, 0.19, 0.11)), rough=0.55))
    shape.box((low.x - 30, high.y + 2.4, low.z - 20), (high.x + 30, high.y + 2.6, low.z + 30), plain("basement: wall", card.get("wall", (0.78, 0.69, 0.58)), rough=0.95))
    return shape.finish(into)


# ---- the pictures ---------------------------------------------------------------


def add_lights(spec, scene, into):
    for card in spec.get("lights") or []:
        kind = {"area": "AREA", "spot": "SPOT", "sun": "SUN", "point": "POINT"}[card["kind"]]
        data = bpy.data.lights.new(card["name"], kind)
        data.energy = float(card["power"])
        data.color = card.get("color", [1.0, 1.0, 1.0])
        if kind == "AREA":
            data.size = float(card.get("size_m", 2.0))
        if kind in ("SPOT", "POINT"):
            data.shadow_soft_size = float(card.get("size_m", 0.5))
        light = bpy.data.objects.new(card["name"], data)
        into.objects.link(light)
        set_contact.look(light, card["at"], card.get("aim", [card["at"][0], 0.0, card["at"][2]]))
    air = (spec.get("basement") or {}).get("air") or {}
    world = bpy.data.worlds.new("basement air")
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs[0].default_value = tuple(air.get("color", [1.0, 0.9, 0.78])) + (1.0,)
    background.inputs[1].default_value = float(air.get("strength", 0.18))
    scene.world = world


def point_of(target, things):
    """A point of the scene to look at or focus on: a toon's head, the middle of a prop, or a point of the set."""
    if isinstance(target, list):
        return to_blender(target)
    thing = things[target]
    return thing["head"].copy() if "head" in thing else thing["middle"].copy()


def set_camera(scene, name, card, things, plinth_points, size, toy):
    """A camera from its card: put where it says, or backed off round the front until what it frames is in the picture."""
    data = bpy.data.cameras.new("camera: " + name)
    data.lens, data.sensor_width = float(card.get("lens_mm", 50.0)), 36.0
    cam = bpy.data.objects.new("camera: " + name, data)
    scene.collection.objects.link(cam)
    if "at" in card:
        set_contact.look(cam, card["at"], card["aim"])
        aim = to_blender(card["aim"])
    else:
        points = [p for who in card.get("frames") or [] for p in things[who]["points"]] or (plinth_points + [p for thing in things.values() for p in thing["points"]])
        low, high = bounds(points)
        f, a = math.radians(card["round_deg"]), math.radians(card["above_deg"])
        toward = Vector((math.sin(f) * math.cos(a), -math.cos(f) * math.cos(a), math.sin(a)))
        stage.fit_camera(cam, points, toward, size, margin=float(card.get("margin", 1.08)))
        aim = (low + high) / 2
    data.clip_start, data.clip_end = 0.1, 500.0
    bpy.context.view_layer.update()
    away = (cam.matrix_world.translation - aim).length
    focus = point_of(card["focus"], things) if card.get("focus") is not None else aim
    data.dof.use_dof = True
    data.dof.focus_distance = (focus - cam.matrix_world.translation).dot(cam.matrix_world.to_3x3() @ Vector((0, 0, -1)))
    data.dof.aperture_fstop = max(0.05, float(card.get("fstop", 4.0)) / toy)  # the toy is 1:12, so the same blur needs the lens 12 times as open
    half = math.atan(data.sensor_width / 2 / data.lens * min(1.0, size[0] / size[1]))
    return cam, {"at": [round(v, 3) for v in from_blender(cam.matrix_world.translation)], "aim": [round(v, 3) for v in from_blender(aim)], "lens_mm": data.lens,
                 "holds_m": round(2 * away * math.tan(half), 2), "about": card.get("about")}



def take(scene, cam, path, size, samples):
    scene.camera = cam
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = size[0], size[1], 100
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 90
    scene.render.filepath = path
    scene.eevee.taa_render_samples = samples
    for key, value in (("use_raytracing", True), ("use_shadows", True)):
        if hasattr(scene.eevee, key):
            setattr(scene.eevee, key, value)
    scene.view_settings.view_transform = "Filmic" if "Filmic" in [i.identifier for i in type(scene.view_settings).bl_rna.properties["view_transform"].enum_items] else "Standard"
    try:
        scene.view_settings.look = "Medium High Contrast"
    except TypeError:
        pass
    bpy.ops.render.render(write_still=True)


def smaller(path, out, size, kind="JPEG"):
    image = bpy.data.images.load(path)
    image.scale(*size)
    image.filepath_raw = out
    image.file_format = kind
    image.save()
    bpy.data.images.remove(image)


# ---- measuring ------------------------------------------------------------------


def measure(things, set_objects, dressing, plinth, links, keep, hero):
    """What is wrong with the scene as it stands, in words, and the numbers behind that."""
    problems, numbers = [], {"touching": {}, "feet_off_floor_cm": {}, "hand_to_prop_cm": {}, "prop_off_surface_cm": {}, "seen_from_front": {}}
    say = problems.append
    trees = {name: tree_of(thing["objects"]) for name, thing in things.items()}
    lifted = {name: tree_of(thing["objects"], SKIN_M)[0] for name, thing in things.items()}
    ground = tree_of(set_objects + [o for holder in dressing for o in meshes_under(holder)])[0]
    names = sorted(things)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if trees[a][0] is None or trees[b][0] is None:
                continue
            pairs = trees[a][0].overlap(trees[b][0])
            if not pairs:
                continue
            link = links.get((a, b)) or links.get((b, a))
            if link and link["kind"] == "stands":
                continue  # one stands on the other: they touch
            if link and link["kind"] == "holds":
                toon, side = (a, 0) if "head" in things[a] else (b, 1)
                verts, polys = trees[toon][1], trees[toon][2]
                far = max(min((verts[v] - link["hand"]).length for v in polys[pair[side]]) for pair in pairs)
                numbers["touching"]["%s + %s" % (a, b)] = "at the hand (within %.0f cm of it)" % (far * 100)
                if far > HAND_M:
                    say("%s is in %s, %.0f cm from the hand that holds it" % (link["prop"], toon, far * 100))
                continue
            numbers["touching"]["%s + %s" % (a, b)] = len(pairs)
            say("%s and %s are in each other (%d triangles cross)" % (a, b, len(pairs)))
    for name in names:
        thing = things[name]
        if ground is not None and (thing.get("on_floor") or "head" in thing) and lifted[name] is not None and lifted[name].overlap(ground):
            say("%s is in the set" % name)
        low = min(p.z for p in thing["points"])
        if "head" in thing:
            off = abs(low - thing["floor"])
            numbers["feet_off_floor_cm"][name] = round(off * 100, 2)
            if off > ON_M:
                say("%s's feet are %.1f cm off the floor" % (name, off * 100))
        elif thing.get("on_floor"):
            off = abs(low - thing["floor"])
            numbers["prop_off_surface_cm"][name] = round(off * 100, 2)
            if off > ON_M:
                say("%s is %.1f cm off the floor it stands on" % (name, off * 100))
        xs, zs = [p.x for p in thing["points"]], [-p.y for p in thing["points"]]
        if min(xs) < keep["x"][0] or max(xs) > keep["x"][1] or min(zs) < keep["z"][0] or max(zs) > keep["z"][1]:
            say("%s hangs over the edge of the base" % name)
    for (a, b), link in links.items():
        if link["kind"] == "holds":
            gap = (link["hand"] - link["grip"]).length
            numbers["hand_to_prop_cm"]["%s holds %s" % (a, b)] = round(gap * 100, 2)
            if gap > 0.02:
                say("%s is %.1f cm from %s's hand" % (b, gap * 100, a))
        if link["kind"] == "stands":
            gap = abs(min(p.z for p in things[a]["points"]) - max(p.z for p in things[b]["points"]))
            numbers["prop_off_surface_cm"]["%s on %s" % (a, b)] = round(gap * 100, 2)
            if gap > ON_M:
                say("%s is %.1f cm off the %s it stands on" % (a, gap * 100, b))
    around = set_objects + [o for holder in dressing for o in meshes_under(holder)] + plinth
    eye = hero.matrix_world.translation
    right, up = hero.matrix_world.to_3x3() @ Vector((1, 0, 0)), hero.matrix_world.to_3x3() @ Vector((0, 1, 0))
    for name in names:
        thing = things[name]
        if "head" not in thing:
            continue
        r, shown, tried = thing["head_radius"], 0, 0
        others = tree_of([o for other, it in things.items() if other != name for o in it["objects"]] + around)[0]  # its own hat is not in its way
        for dx in (-0.6, 0.0, 0.6):
            for dy in (-0.6, 0.0, 0.6):
                point = thing["head"] + right * dx * r + up * dy * r
                way = point - eye
                hit = others.ray_cast(eye, way.normalized(), way.length)
                tried += 1
                shown += hit[0] is None
        numbers["seen_from_front"][name] = round(shown / tried, 2)
        if shown / tried < (PEEK if thing.get("peeks") else SEEN):
            say("%s's head is hidden from the front (%d%% of it shows)" % (name, round(100 * shown / tried)))
    return problems, numbers


# ---- the whole build ------------------------------------------------------------


def slim_pictures(objects, most_px):
    """Keep a toy's paint and nothing else: color pictures no bigger than `most_px`, no bump or shine maps."""
    seen = set()
    for obj in objects:
        for slot in obj.material_slots:
            mat = slot.material
            if not mat or not mat.use_nodes or mat.name in seen:
                continue
            seen.add(mat.name)
            shader = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if shader is None:
                continue
            for socket in ("Normal", "Metallic", "Roughness"):
                for link in list(shader.inputs[socket].links):
                    mat.node_tree.links.remove(link)
            shader.inputs["Metallic"].default_value = 0.0
            shader.inputs["Roughness"].default_value = 0.78
            for node in mat.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image and node.outputs["Color"].links and max(node.image.size) > most_px:
                    wide, tall = node.image.size
                    node.image.scale(max(1, round(wide * most_px / max(wide, tall))), max(1, round(tall * most_px / max(wide, tall))))


def export(objects, path):
    for obj in bpy.data.objects:
        obj.select_set(False)
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    options = {"filepath": path, "export_format": "GLB", "use_selection": True, "export_apply": True, "export_animations": False, "export_skins": False, "export_extras": False,
               "export_cameras": False, "export_lights": False, "export_draco_mesh_compression_enable": True, "export_draco_mesh_compression_level": 6, "export_image_format": "WEBP",
               "export_image_quality": 80}
    known = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    if "export_vertex_color" in known:
        options["export_vertex_color"] = "ACTIVE"  # a block-out's colors are painted on its corners: say so, or they are left behind
    bpy.ops.export_scene.gltf(**{k: v for k, v in options.items() if k in known})


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    opt = lambda flag, default=None: args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else default
    spec = diorama.load(args[0])
    runs = os.path.abspath(opt("--runs", os.path.join(REPO, "runs")))
    out = os.path.abspath(opt("--out", spec["dir"]))
    draft = "--draft" in args
    draft_cameras = [c for c in (opt("--draft", "") or "").split(",") if c in spec["cameras"]] or spec["stills"][:1]
    began = time.time()
    wrong, _ = diorama.check(spec, runs)
    if wrong:
        for line in wrong:
            print("DIORAMA PROBLEM %s: %s" % (spec["name"], line))
        print("DIORAMA %s: not built, the plan has %d problems" % (spec["name"], len(wrong)))
        sys.exit(1)
    os.makedirs(os.path.join(out, "draft" if draft else "stills"), exist_ok=True)
    st = standing.load(spec["set"]["name"])
    poses = diorama.poses_of(spec)
    scene = stage.fresh_scene()
    shown = collection("diorama", scene.collection)      # what is on the base: this is the .glb
    around = collection("basement", scene.collection)    # the shelf, the wall, the lights: the pictures only
    work = os.path.join(bpy.app.tempdir, "diorama")
    os.makedirs(work, exist_ok=True)

    set_objects, dressing = stand_set(spec, st, shown, work)
    characters = {card["toon"]: stand_toon(card, spec, st, runs, poses) for card in spec["toons"]}
    props = {name: bring_prop(name, card, runs, shown) for name, card in (spec.get("props") or {}).items()}
    links = {}
    floor_y = float(st.get("ground", {}).get("y", 0.0))
    prop_floor = {}

    for who, character in characters.items():
        for held in character["card"].get("holds") or []:
            holder, hand = props[held["prop"]], hand_point(character, held["hand"])
            grip = held.get("grip", "top")
            put(holder, character["heading"] + float(held.get("turn_deg", 0.0)), lambda holder=holder, grip=grip: grip_point(holder, grip), hand)
            links[(who, held["prop"])] = {"kind": "holds", "prop": held["prop"], "hand": hand, "grip": grip_point(holder, grip)}
        for near in character["card"].get("beside") or []:
            holder = props[near["prop"]]
            h = math.radians(character["heading"])
            right, forward = near["offset"]
            x = character["spot"][0] - math.cos(h) * right + math.sin(h) * forward
            z = character["spot"][1] + math.sin(h) * right + math.cos(h) * forward
            floor = standing.top_of(standing.block_named(st, near["on"])) if near.get("on") else floor_y
            put(holder, character["heading"] + float(near.get("turn_deg", 0.0)), lambda holder=holder: grip_point(holder, "bottom"), to_blender([x, floor, z]))
            prop_floor[near["prop"]] = floor
    later = []
    for free in spec.get("free_props") or []:
        if free.get("under"):
            later.append(free)
            continue
        holder = props[free["prop"]]
        heading = float(free["facing_deg"]) if "facing_deg" in free else (diorama.heading_to(free["at"], free["faces"] if isinstance(free.get("faces"), list) else characters[free["faces"]]["spot"]) if free.get("faces") else 0.0)
        put(holder, heading, lambda holder=holder: grip_point(holder, "bottom"), to_blender([free["at"][0], floor_y, free["at"][1]]))
        prop_floor[free["prop"]] = floor_y
    for free in later:  # something that stands under another prop is built to reach it: a tripod under a camera
        above = props[free["under"]]
        under = grip_point(above, "bottom")
        card = dict(spec["props"][free["prop"]], height_m=under.z - floor_y)
        bpy.data.objects.remove(props[free["prop"]].children[0], do_unlink=True)
        bpy.data.objects.remove(props[free["prop"]], do_unlink=True)
        holder = props[free["prop"]] = build_prop(free["prop"], card, shown)
        put(holder, math.degrees(above.rotation_euler.z), None, Vector((under.x, under.y, floor_y)))
        prop_floor[free["prop"]] = floor_y
        links[(free["under"], free["prop"])] = {"kind": "stands"}

    bpy.context.view_layer.update()
    prop_middle = {name: sum(mesh_points(meshes_under(holder)), Vector()) / max(1, len(mesh_points(meshes_under(holder)))) for name, holder in props.items()}
    heads = {who: stage.head_of(character)["center"] for who, character in characters.items()}
    for who, character in characters.items():
        target = character["card"].get("looks_at")
        if target is None:
            continue
        look(character, to_blender(target) if isinstance(target, list) else heads[target] if target in heads else prop_middle[target])

    things = {}
    for who, character in characters.items():
        head = stage.head_of(character)
        record = {"head": head["center"].copy(), "head_radius": head["radius"], "floor": character["floor"], "peeks": bool(character["card"].get("peeks"))}
        holder, kept = freeze_toon(character, shown)
        bpy.context.view_layer.update()
        record.update(objects=kept, points=mesh_points(kept), holder=holder, triangles=sum(len(p.vertices) - 2 for o in kept for p in o.data.polygons))
        things[who] = record
    for name, holder in props.items():
        objects = meshes_under(holder)
        things[name] = {"objects": objects, "points": mesh_points(objects), "middle": prop_middle[name], "holder": holder, "on_floor": name in prop_floor and not any(a == name and l["kind"] == "stands" for (a, b), l in links.items()),
                        "floor": prop_floor.get(name, floor_y), "triangles": sum(len(p.vertices) - 2 for o in objects for p in o.data.polygons)}
    slim_pictures([o for who in characters for o in things[who]["objects"]], int(spec.get("paint_px", 512)))

    plinth, plinth_facts = build_plinth(spec, st, shown, work)
    plinth_points = mesh_points([plinth[0]])
    cameras, views = {}, {}
    for name, card in spec["cameras"].items():
        cameras[name], views[name] = set_camera(scene, name, card, things, plinth_points, STILL, float(spec["plinth"].get("toy_scale", 12)))
    hero = cameras[spec["stills"][0]]

    problems, numbers = measure(things, set_objects, dressing, plinth, links, spec["set"]["keep"], hero)
    for who in characters:
        low, high = bounds(things[who]["points"])
        print("DIORAMA %s toon %s: %s, %s, at (%.2f, %.2f) facing %.0f, %d triangles; x %.2f to %.2f, z %.2f to %.2f, %.2f m tall" % (
            spec["name"], who, characters[who]["card"].get("version", "lowpoly"), characters[who]["card"]["pose"], characters[who]["spot"][0], characters[who]["spot"][1], characters[who]["heading"], things[who]["triangles"],
            low.x, high.x, -high.y, -low.y, high.z - characters[who]["floor"]))

    record = {"format": "forge-diorama-build/1", "name": spec["name"], "plinth": plinth_facts, "cameras": views, "measured": numbers, "problems": problems,
              "toons": {who: {"version": characters[who]["card"].get("version", "lowpoly"), "pose": characters[who]["how"], "at": [round(v, 3) for v in characters[who]["spot"]],
                              "floor_m": round(characters[who]["floor"], 3), "facing_deg": round(characters[who]["heading"], 1), "triangles": things[who]["triangles"]} for who in characters},
              "props": {name: {"at": [round(v, 3) for v in from_blender(things[name]["holder"].matrix_world.translation)], "triangles": things[name]["triangles"]} for name in props}}

    exported = [o for o in shown.all_objects]
    if not draft:
        path = os.path.join(out, "diorama.glb")
        export(exported, path)
        record["glb"] = diorama.glb_facts(path)
        for key, most in diorama.BUDGET.items():
            if record["glb"][key] > most:
                problems.append("diorama.glb is %s %s: more than the %s a phone should be asked for" % (format(record["glb"][key], ","), key, format(most, ",")))
        print("DIORAMA %s: diorama.glb, %d triangles, %.2f MB, %s, pictures %s" % (spec["name"], record["glb"]["triangles"], record["glb"]["bytes"] / 1e6,
                                                                               "Draco" if record["glb"]["draco"] else "not packed", ", ".join(record["glb"]["pictures"]) or "none"))

    record["stills"] = []
    if "--no-stills" not in args:
        build_basement(spec, around, plinth_points)
        add_lights(spec, scene, around)
        for name in draft_cameras if draft else spec["stills"]:
            picture = os.path.join(out, "draft", name + ".jpg") if draft else os.path.join(out, "stills", name + ".jpg")
            take(scene, cameras[name], picture, DRAFT if draft else STILL, 16 if draft else 64)
            if not draft:
                smaller(picture, os.path.join(out, "stills", name + "-small.jpg"), SMALL)
            record["stills"].append({"camera": name, "about": spec["cameras"][name].get("about"), "picture": "stills/%s.jpg" % name, "small": "stills/%s-small.jpg" % name})
            print("DIORAMA %s still: %s" % (spec["name"], os.path.relpath(picture, REPO)))
        if not draft:
            smaller(os.path.join(out, "stills", spec["stills"][0] + ".jpg"), os.path.join(out, "card.png"), CARD, "PNG")

    if not draft:
        # Does the file open again, with everything in it?
        stage.fresh_scene()
        bpy.ops.import_scene.gltf(filepath=os.path.join(out, "diorama.glb"))
        back = [o for o in bpy.data.objects if o.type == "MESH"]
        record["opens_again"] = {"meshes": len(back), "triangles": sum(len(p.vertices) - 2 for o in back for p in o.data.polygons)}
        if not back or record["opens_again"]["triangles"] != record["glb"]["triangles"]:
            problems.append("diorama.glb does not open again as it was written")
    record["seconds"] = round(time.time() - began, 1)
    record["problems"] = problems
    if not draft:
        with open(os.path.join(out, "build.json"), "w") as f:
            json.dump(record, f, indent=1)
            f.write("\n")
    for key, values in numbers.items():
        print("DIORAMA %s %s: %s" % (spec["name"], key.replace("_", " "), json.dumps(values)))
    for line in problems:
        print("DIORAMA PROBLEM %s: %s" % (spec["name"], line))
    print("DIORAMA %s: %s, %.0f s" % (spec["name"], "built, nothing wrong" if not problems else "%d problems" % len(problems), record["seconds"]))
    sys.exit(1 if problems else 0)


main()
