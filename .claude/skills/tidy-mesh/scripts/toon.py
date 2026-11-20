# Draw the scene the way our comics are drawn: flat color in two or three
# tones of light, a steady ink line around every shape, and each texture
# simplified to a few steps of light and dark. It is one "hand" for every
# character, prop and set, so rough low-poly shapes read as a style.
#
# What it changes, and nothing else:
#   - every material that renders gets a "comic paint" node after whatever fed
#     its Base Color (a texture, a flat color, point colors). The old shader
#     stays in the material, unplugged; "undo": True plugs it back in.
#   - every mesh gets a "comic ink" modifier: a black shell a hair bigger than
#     the mesh, seen only from inside, so it shows as a line around the shape
#     and wherever one piece passes in front of another. The shell grows with
#     its distance from the camera, so the line is "line_px" wide on screen
#     near and far. Change the camera or the picture size and run this again.
#   - the render: EEVEE, the Standard view (colors come out as painted), and
#     no lamps needed: light and shade are worked out from "light" alone, which
#     is given as the camera sees it, so every panel is lit from the same side.
#
# "drawn" lays a flat picture over part of a material, in front of the paint
# and under the tones of light (the comics use it for a drawn face on a head;
# face_swap.py fills it in). Leave it alone otherwise.
#
# Give "path" to render a .png with the scene's camera. With "background":
# None the picture has no background (alpha), so a page can put a flat color,
# a gradient or a painted backdrop behind it.
#
# Send this whole file through the blender MCP `execute_blender_code` tool
# after editing PARAMS. Prints RESULT {json}. A second or two a picture.
# Safe-mode compatible.

PARAMS = {
    "objects": None,       # mesh names to draw this way; None = every mesh that renders
    "tones": 3,            # 2 or 3 flat tones of light
    "levels": 8,           # steps of light-to-dark a texture is simplified to (5 = bold, 10 = gentle)
    "soften": 128,         # textures larger than this many pixels are read from a smaller, smoother copy; 0 = as they are
    "keep_sharp": ["head"],  # materials with one of these words in the name keep twice that (a face needs its eyes)
    "line_px": 3.2,        # ink line width in pixels of the finished picture; 0 = no lines
    "ink": [0.11, 0.09, 0.13],     # the line's color, as you see it on screen (so is "background")
    "gain": 1.5,           # brighter or dimmer: a texture holds a surface's own color, which is darker than it looks under lamps
    "halftone": 0.0,       # 0 to 1: dots in the darkest tone
    "light": [-0.55, 0.5, 0.67],   # where the light comes from, as the camera sees it: right, up, toward the camera
    "shade": [[0.86, 0.85, 0.90], [0.62, 0.60, 0.74]],  # what the middle and the dark tone multiply a color by
    "background": None,    # [r, g, b] for a flat one; None = no background (alpha)
    "samples": 16,
    "size": None,          # [wide, tall] in pixels; None = as the scene has it
    "path": None,          # absolute path of a .png to render; None = only set things up
    "undo": False,         # True = take the comic look off again (materials, lines)
}

import bpy
import json
import math
from mathutils import Vector

TONE = "comic tone"
INK = "comic ink"
PAINT = "comic paint"
GLOW = "comic color"


def socket(group, name, way, kind):
    return group.interface.new_socket(name=name, in_out=way, socket_type=kind)


def link(tree, a, b):
    tree.links.new(a, b)


def number(tree, operation, a, b=None, clamp=False):
    """A Math node; `a` and `b` are sockets or plain numbers. Returns its output."""
    node = tree.nodes.new("ShaderNodeMath")
    node.operation = operation
    node.use_clamp = clamp
    for i, value in enumerate((a, b)):
        if value is None:
            continue
        if isinstance(value, (int, float)):
            node.inputs[i].default_value = value
        else:
            link(tree, value, node.inputs[i])
    return node.outputs[0]


def tone_group():
    """The shared paint: simplify the color, lay the drawn picture over it, multiply by one of the flat tones."""
    old = bpy.data.node_groups.get(TONE)
    if old:
        return old
    g = bpy.data.node_groups.new(TONE, "ShaderNodeTree")
    socket(g, "Color", "INPUT", "NodeSocketColor").default_value = (0.8, 0.8, 0.8, 1.0)
    socket(g, "Drawn", "INPUT", "NodeSocketColor").default_value = (1.0, 1.0, 1.0, 1.0)
    amount = socket(g, "Drawn Amount", "INPUT", "NodeSocketFloat")
    amount.default_value, amount.min_value, amount.max_value = 0.0, 0.0, 1.0
    socket(g, "Color", "OUTPUT", "NodeSocketColor")
    n = g.nodes
    inp, out = n.new("NodeGroupInput"), n.new("NodeGroupOutput")

    # A texture to a few steps: the hue stays, light-to-dark snaps to "Levels" steps (counted the way the eye does).
    levels = n.new("ShaderNodeValue")
    levels.name = levels.label = "Levels"
    levels.outputs[0].default_value = 6.0
    split = n.new("ShaderNodeSeparateColor")
    split.mode = "HSV"
    link(g, inp.outputs["Color"], split.inputs[0])
    gain = n.new("ShaderNodeValue")
    gain.name = gain.label = "Gain"
    gain.outputs[0].default_value = 1.5
    seen = number(g, "POWER", number(g, "MULTIPLY", split.outputs[2], gain.outputs[0], clamp=True), 1.0 / 2.2)
    seen = number(g, "ADD", number(g, "MULTIPLY", seen, 0.86), 0.14)  # black cloth stays a shade above the ink, so its lines show
    step = number(g, "DIVIDE", 1.0, levels.outputs[0])
    snapped = number(g, "SNAP", number(g, "ADD", seen, number(g, "MULTIPLY", step, 0.5)), step)
    snapped = number(g, "MAXIMUM", snapped, number(g, "MULTIPLY", step, 0.55))
    value = number(g, "POWER", snapped, 2.2)
    rich = number(g, "MULTIPLY", split.outputs[1], 0.96, clamp=True)
    join = n.new("ShaderNodeCombineColor")
    join.mode = "HSV"
    link(g, split.outputs[0], join.inputs[0])
    link(g, rich, join.inputs[1])
    link(g, value, join.inputs[2])

    drawn = n.new("ShaderNodeMix")
    drawn.data_type = "RGBA"
    link(g, inp.outputs["Drawn Amount"], drawn.inputs[0])
    link(g, join.outputs[0], drawn.inputs[6])
    link(g, inp.outputs["Drawn"], drawn.inputs[7])

    # Light and shade: how far the surface faces the light picks one of the flat tones.
    light = n.new("ShaderNodeCombineXYZ")
    light.name = light.label = "Light"
    shape = n.new("ShaderNodeNewGeometry")
    facing = n.new("ShaderNodeVectorMath")
    facing.operation = "DOT_PRODUCT"
    link(g, shape.outputs["Normal"], facing.inputs[0])
    link(g, light.outputs[0], facing.inputs[1])
    edge_light, edge_dark = n.new("ShaderNodeValue"), n.new("ShaderNodeValue")
    edge_light.name = edge_light.label = "Light Edge"
    edge_dark.name = edge_dark.label = "Dark Edge"
    edge_light.outputs[0].default_value, edge_dark.outputs[0].default_value = 0.2, -0.2
    lit = number(g, "GREATER_THAN", facing.outputs["Value"], edge_light.outputs[0])
    not_dark = number(g, "GREATER_THAN", facing.outputs["Value"], edge_dark.outputs[0])
    middle, dark = n.new("ShaderNodeRGB"), n.new("ShaderNodeRGB")
    middle.name = middle.label = "Middle Tone"
    dark.name = dark.label = "Dark Tone"

    # Dots in the dark tone, a fixed size on the picture.
    dots = n.new("ShaderNodeCombineXYZ")
    dots.name = dots.label = "Dots"  # x, y: dots across and down the picture; z: how strong
    place = n.new("ShaderNodeTexCoord")
    xyz = n.new("ShaderNodeSeparateXYZ")
    link(g, place.outputs["Window"], xyz.inputs[0])
    grid = n.new("ShaderNodeSeparateXYZ")
    link(g, dots.outputs[0], grid.inputs[0])
    across = number(g, "MULTIPLY", xyz.outputs[0], grid.outputs[0])
    down = number(g, "MULTIPLY", xyz.outputs[1], grid.outputs[1])
    a = number(g, "SUBTRACT", number(g, "FRACT", number(g, "ADD", across, down)), 0.5)
    b = number(g, "SUBTRACT", number(g, "FRACT", number(g, "SUBTRACT", across, down)), 0.5)
    far = number(g, "SQRT", number(g, "ADD", number(g, "MULTIPLY", a, a), number(g, "MULTIPLY", b, b)))
    dot = number(g, "MULTIPLY", number(g, "LESS_THAN", far, 0.3), grid.outputs[2])
    dotted = n.new("ShaderNodeMix")
    dotted.data_type = "RGBA"
    dotted.blend_type = "MULTIPLY"
    link(g, dot, dotted.inputs[0])
    link(g, dark.outputs[0], dotted.inputs[6])
    dotted.inputs[7].default_value = (0.72, 0.72, 0.78, 1.0)

    low = n.new("ShaderNodeMix")
    low.data_type = "RGBA"
    link(g, not_dark, low.inputs[0])
    link(g, dotted.outputs[2], low.inputs[6])
    link(g, middle.outputs[0], low.inputs[7])
    high = n.new("ShaderNodeMix")
    high.data_type = "RGBA"
    link(g, lit, high.inputs[0])
    link(g, low.outputs[2], high.inputs[6])
    high.inputs[7].default_value = (1.0, 1.0, 1.0, 1.0)
    toned = n.new("ShaderNodeMix")
    toned.data_type = "RGBA"
    toned.blend_type = "MULTIPLY"
    toned.inputs[0].default_value = 1.0
    link(g, drawn.outputs[2], toned.inputs[6])
    link(g, high.outputs[2], toned.inputs[7])
    link(g, toned.outputs[2], out.inputs["Color"])
    return g


def as_seen(color):
    """A color as it looks on screen, turned into the scene's own (linear) numbers."""
    return tuple([pow(max(c, 0.0), 2.2) for c in color]) + (1.0,)


def ink_material(color):
    mat = bpy.data.materials.get(INK) or bpy.data.materials.new(INK)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    glow, out = tree.nodes.new("ShaderNodeEmission"), tree.nodes.new("ShaderNodeOutputMaterial")
    glow.inputs["Color"].default_value = as_seen(color)
    link(tree, glow.outputs[0], out.inputs["Surface"])
    mat.use_backface_culling = True
    return mat


def ink_group():
    """The line: a copy of the mesh, welded, pushed out along its normals by a width that grows with the distance
    to the camera, turned inside out and painted with the ink. Its numbers are nodes inside it, set on every run:
    "Per Distance" (width for each unit of distance, for a camera with perspective), "Flat" (width whatever the
    distance, for one without), "Camera" and "Ink"."""
    old = bpy.data.node_groups.get(INK)
    if old:
        return old
    g = bpy.data.node_groups.new(INK, "GeometryNodeTree")
    socket(g, "Geometry", "INPUT", "NodeSocketGeometry")
    socket(g, "Geometry", "OUTPUT", "NodeSocketGeometry")
    n = g.nodes
    inp, out = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    per, flat = n.new("ShaderNodeValue"), n.new("ShaderNodeValue")
    per.name = per.label = "Per Distance"
    flat.name = flat.label = "Flat"
    weld = n.new("GeometryNodeMergeByDistance")
    weld.inputs["Distance"].default_value = 0.0005
    link(g, inp.outputs["Geometry"], weld.inputs["Geometry"])
    eye = n.new("GeometryNodeObjectInfo")
    eye.name = eye.label = "Camera"
    eye.transform_space = "RELATIVE"
    where, normal = n.new("GeometryNodeInputPosition"), n.new("GeometryNodeInputNormal")
    away = n.new("ShaderNodeVectorMath")
    away.operation = "DISTANCE"
    link(g, where.outputs[0], away.inputs[0])
    link(g, eye.outputs["Location"], away.inputs[1])
    wide = n.new("ShaderNodeMath")
    wide.operation = "MULTIPLY_ADD"
    link(g, away.outputs["Value"], wide.inputs[0])
    link(g, per.outputs[0], wide.inputs[1])
    link(g, flat.outputs[0], wide.inputs[2])
    push = n.new("ShaderNodeVectorMath")
    push.operation = "SCALE"
    link(g, normal.outputs[0], push.inputs[0])
    link(g, wide.outputs[0], push.inputs["Scale"])
    move = n.new("GeometryNodeSetPosition")
    link(g, weld.outputs["Geometry"], move.inputs["Geometry"])
    link(g, push.outputs[0], move.inputs["Offset"])
    flip = n.new("GeometryNodeFlipFaces")
    link(g, move.outputs["Geometry"], flip.inputs["Mesh"])
    paint = n.new("GeometryNodeSetMaterial")
    paint.name = paint.label = "Ink"
    link(g, flip.outputs["Mesh"], paint.inputs["Geometry"])
    both = n.new("GeometryNodeJoinGeometry")
    link(g, inp.outputs["Geometry"], both.inputs["Geometry"])
    link(g, paint.outputs["Geometry"], both.inputs["Geometry"])
    link(g, both.outputs["Geometry"], out.inputs["Geometry"])
    return g


def color_source(tree):
    """(the socket that says what color this material is, or None; its plain color; the output node)."""
    out = next((x for x in tree.nodes if x.type == "OUTPUT_MATERIAL" and x.is_active_output), None)
    if out is None:
        return None, None, None
    shader = next((x for x in tree.nodes if x.type == "BSDF_PRINCIPLED"), None)
    entry = shader.inputs["Base Color"] if shader else None
    if entry is None:
        other = next((x for x in tree.nodes if x.type in ("EMISSION", "BSDF_DIFFUSE") and x.name != GLOW), None)
        entry = other.inputs["Color"] if other else None
    if entry is None:
        return None, (0.8, 0.8, 0.8, 1.0), out
    return (entry.links[0].from_socket if entry.is_linked else None), tuple(entry.default_value), out


def softer(mat, limit):
    """Point the material's color textures at smaller copies; returns how many were swapped."""
    tree = mat.node_tree
    textures = [x for x in tree.nodes if x.type == "TEX_IMAGE" and x.image is not None]
    swaps = json.loads(mat.get("comic_images") or "{}")
    for node in textures:
        image = node.image
        if node.name in swaps or (len(textures) > 1 and "color" not in image.name.lower()):
            continue
        if not limit or max(image.size[0], image.size[1]) <= limit:
            continue
        small = bpy.data.images.get("comic: " + image.name)
        if small is None:
            small = image.copy()
            small.name = "comic: " + image.name
            ratio = limit / max(image.size[0], image.size[1])
            small.scale(max(1, int(image.size[0] * ratio)), max(1, int(image.size[1] * ratio)))
        swaps[node.name] = image.name
        node.image = small
    mat["comic_images"] = json.dumps(swaps)
    return len(swaps)


def paint(mat, group, limit):
    """Put the comic paint in a material (once). Returns "painted", "kept" or "skipped"."""
    if not mat.use_nodes:
        mat.use_nodes = True
    tree = mat.node_tree
    if tree.nodes.get(PAINT):
        return "kept"
    source, plain, out = color_source(tree)
    if out is None:
        return "skipped"
    softer(mat, limit)
    node = tree.nodes.new("ShaderNodeGroup")
    node.name = node.label = PAINT
    node.node_tree = group
    if source:
        link(tree, source, node.inputs["Color"])
    else:
        node.inputs["Color"].default_value = plain
    glow = tree.nodes.new("ShaderNodeEmission")
    glow.name = glow.label = GLOW
    link(tree, node.outputs["Color"], glow.inputs["Color"])
    was = out.inputs["Surface"].links[0].from_node.name if out.inputs["Surface"].is_linked else ""
    mat["comic_was"] = was
    link(tree, glow.outputs[0], out.inputs["Surface"])
    return "painted"


def unpaint(mat):
    tree = mat.node_tree if mat.use_nodes else None
    node = tree.nodes.get(PAINT) if tree else None
    if node is None:
        return False
    out = next((x for x in tree.nodes if x.type == "OUTPUT_MATERIAL" and x.is_active_output), None)
    before = tree.nodes.get(mat.get("comic_was") or "")
    if out and before:
        link(tree, before.outputs[0], out.inputs["Surface"])
    for extra in [x for x in tree.nodes if x.name in (PAINT, GLOW)]:
        tree.nodes.remove(extra)
    swaps = json.loads(mat.get("comic_images") or "{}")
    for name in swaps:
        tex = tree.nodes.get(name)
        if tex:
            tex.image = bpy.data.images.get(swaps[name]) or tex.image
    mat["comic_images"] = "{}"
    return True


scene = bpy.context.scene
if PARAMS["objects"]:
    meshes = [bpy.data.objects[name] for name in PARAMS["objects"]]
else:
    meshes = [o for o in scene.objects if o.type == "MESH" and not o.hide_render and len(o.data.materials) > 0]
if PARAMS["size"]:
    scene.render.resolution_x, scene.render.resolution_y = PARAMS["size"]
    scene.render.resolution_percentage = 100
wide, tall = scene.render.resolution_x, scene.render.resolution_y
camera = scene.camera
counts = {"painted": 0, "kept": 0, "skipped": 0, "lines": 0}

if PARAMS["undo"]:
    undone = 0
    for o in meshes:
        for mod in [m for m in o.modifiers if m.name == INK]:
            o.modifiers.remove(mod)
        for mat in o.data.materials:
            if mat and unpaint(mat):
                undone += 1
    print("RESULT " + json.dumps({"undone_materials": undone, "meshes": len(meshes)}))
else:
    group = tone_group()
    nodes = group.nodes
    nodes["Levels"].outputs[0].default_value = float(PARAMS["levels"])
    nodes["Gain"].outputs[0].default_value = float(PARAMS["gain"])
    middle, dark = PARAMS["shade"]
    if PARAMS["tones"] < 3:
        middle = [1.0, 1.0, 1.0]
    nodes["Middle Tone"].outputs[0].default_value = tuple(middle) + (1.0,)
    nodes["Dark Tone"].outputs[0].default_value = tuple(dark) + (1.0,)
    # The light is given as the camera sees it; the paint needs it in the scene's own directions.
    toward = Vector(PARAMS["light"]).normalized()
    if camera:
        toward = (camera.matrix_world.to_quaternion() @ toward).normalized()
    for i in range(3):
        nodes["Light"].inputs[i].default_value = toward[i]
    pitch = 7.0  # pixels between dots
    nodes["Dots"].inputs[0].default_value = wide / pitch
    nodes["Dots"].inputs[1].default_value = tall / pitch
    nodes["Dots"].inputs[2].default_value = float(PARAMS["halftone"])

    for o in meshes:
        for mat in o.data.materials:
            if mat and mat.name != INK:
                sharp = any(word in mat.name.lower() for word in PARAMS["keep_sharp"])
                counts[paint(mat, group, PARAMS["soften"] * (2 if sharp else 1))] += 1

    per_distance = flat = 0.0
    if PARAMS["line_px"] and camera:
        if camera.data.type == "ORTHO":
            flat = PARAMS["line_px"] * camera.data.ortho_scale / max(wide, tall)
        else:
            per_distance = PARAMS["line_px"] * camera.data.sensor_width / (camera.data.lens * max(wide, tall))
    if per_distance or flat:
        lines = ink_group()
        lines.nodes["Per Distance"].outputs[0].default_value = per_distance
        lines.nodes["Flat"].outputs[0].default_value = flat
        lines.nodes["Camera"].inputs["Object"].default_value = camera
        lines.nodes["Ink"].inputs["Material"].default_value = ink_material(PARAMS["ink"])
        for o in meshes:
            mod = o.modifiers.get(INK) or o.modifiers.new(INK, "NODES")
            mod.node_group = lines
            o.update_tag()
            counts["lines"] += 1
    else:
        for o in meshes:
            for mod in [m for m in o.modifiers if m.name == INK]:
                o.modifiers.remove(mod)

    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = PARAMS["samples"]
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.dither_intensity = 0.0
    scene.render.image_settings.file_format = "PNG"
    if PARAMS["background"] is None:
        scene.render.film_transparent = True
        scene.render.image_settings.color_mode = "RGBA"
    else:
        scene.render.film_transparent = False
        world = scene.world or bpy.data.worlds.new("comic sky")
        scene.world = world
        world.use_nodes = True
        sky = next((x for x in world.node_tree.nodes if x.type == "BACKGROUND"), None)
        if sky:
            sky.inputs["Color"].default_value = as_seen(PARAMS["background"])
            sky.inputs["Strength"].default_value = 1.0
    rendered = None
    if PARAMS["path"]:
        if camera is None:
            raise ValueError("the scene has no camera to render with: add one (stage.py does) or leave \"path\" as None")
        scene.render.filepath = PARAMS["path"]
        bpy.ops.render.render(write_still=True)
        rendered = PARAMS["path"]
    print("RESULT " + json.dumps({
        "meshes": len(meshes), "materials": counts, "tones": PARAMS["tones"], "levels": PARAMS["levels"],
        "line": {"px": PARAMS["line_px"], "per_distance": round(per_distance, 6), "flat": round(flat, 6)},
        "light_in_scene": [round(c, 3) for c in toward], "size": [wide, tall], "path": rendered,
    }))
