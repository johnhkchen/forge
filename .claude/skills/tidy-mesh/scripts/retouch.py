# Change how the surface looks, all over or one area at a time, without
# repainting the texture: metal, sheen, color, grain. Built from shader nodes
# on top of the baked texture; run it again and it rebuilds from PARAMS.
#
# An area ("regions") is picked by "where", any mix of:
#   "box": {"min": [x, y, z], "max": [x, y, z]}   a place, in world meters
#   "value": [0, 0.2]         how light the texture is there (0 black, 1 white)
#   "saturation": [0, 0.25]   how colorful (0 gray)
#   "hue": [0.02, 0.12]       which color (0 red, 0.08 orange-brown, 0.33
#                             green, 0.6 blue; [0.95, 0.05] wraps through red)
#   "soft": 0.03              how gradual the color edges are
# so "the dark band on that wrist" is a box plus a value range.
#
# "set" (for an area) and "overall" (everything) take any of:
#   "metallic": 1.0
#   "roughness": 0.55         or, in "overall" only, [0.72, 0.95] to squeeze
#                             the baked roughness into that range
#   "saturation": 1.1, "value": 0.9, "hue": 0.5    multiply color (hue 0.5 = no shift)
#   "color": [r, g, b, 0.6]   pull toward a flat color by that amount (to
#                             lift a dark smear, or deepen a washed-out part)
#   "bump": 0.2               relief from the texture's own light and dark
#   "grain": 0.1              fine pebbly relief ("grain_size" in "overall":
#                             bump size as a share of the object, 0.002)
#   "subsurface": 0.06        soft glow-through for skin, bread, wax
# Later regions win where they overlap.
#
# To check an area's reach, set "show" to its name: it glows red. `look`,
# fix the box or ranges, then set "show" back to None.
#
# Every number becomes a Value node named "retouch: <region>.<setting>"
# ("all" for overall; box edges are "<region>.min x" ... "<region>.max z"),
# listed under "knobs" in the result. To nudge one later, don't resend this
# file; one line does it:
#   bpy.data.materials[NAME].node_tree.nodes["retouch: band.metallic"].outputs[0].default_value = 0.9
#
# The result also says, for each region and for the whole surface, how light,
# colorful and what hue the texture is there (10th, 50th, 90th percentile)
# and what share of the surface the area covers: read these to pick ranges.
#
# glTF can't carry these nodes: the .blend and the render have them;
# bake.py (mode "materials") turns them into textures for a GLB.
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down
# (these comments can stay behind). Prints RESULT {json}. About 2 s.
# Safe-mode compatible.

PARAMS = {
    "object": None,  # None = the largest visible mesh (its first material)
    "overall": {},   # {"metallic": 0, "roughness": [0.72, 0.95], "saturation": 1.1, "bump": 0.2}
    "regions": [],   # [{"name": "band", "where": {"box": {...}, "value": [0, 0.2]}, "set": {"metallic": 1, "roughness": 0.55}}]
    "show": None,    # a region's name, to see its reach in red
}

import bpy
import colorsys
import json

LEVELS = {"metallic": "Metallic", "roughness": "Roughness", "subsurface": "Subsurface Weight"}
TINTS = ("hue", "saturation", "value", "color")


def face_count(obj):
    return len(obj.data.polygons)

def pick_object(name):
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise ValueError("no mesh object named %r" % name)
        return obj
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get()]
    if not meshes:
        raise ValueError("the scene has no visible mesh objects")
    return max(meshes, key=face_count)


obj = pick_object(PARAMS["object"])
mat = obj.data.materials[0]
tree = mat.node_tree
nodes, links = tree.nodes, tree.links
bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
size = max(obj.dimensions)
knobs = {}
made = [0]

def add(kind, name):
    n = nodes.new(kind)
    n.name = n.label = "retouch: " + name
    n.location = (-2400 + 200 * (made[0] % 9), 900 + 220 * (made[0] // 9))
    made[0] += 1
    return n

def knob(name, value):
    n = add("ShaderNodeValue", name)
    n.outputs[0].default_value = value
    knobs[name] = round(value, 4)
    return n.outputs[0]

def feed(socket, value):
    if isinstance(value, (int, float)):
        socket.default_value = value
    else:
        links.new(value, socket)

def calc(operation, a, b, clamp=False):
    n = add("ShaderNodeMath", operation.lower())
    n.operation = operation
    n.use_clamp = clamp
    feed(n.inputs[0], a)
    feed(n.inputs[1], b)
    return n.outputs[0]

def blend(amount, a, b, color=False):
    n = add("ShaderNodeMix", "mix")
    n.data_type = "RGBA" if color else "FLOAT"
    feed(n.inputs[0], amount)
    links.new(a, n.inputs[6 if color else 2])
    links.new(b, n.inputs[7 if color else 3])
    return n.outputs[2 if color else 0]

def tinted(color, wanted, who):
    """`color` with this region's hue / saturation / value / flat color applied."""
    if any(k in wanted for k in ("hue", "saturation", "value")):
        n = add("ShaderNodeHueSaturation", who + " tint")
        links.new(color, n.inputs["Color"])
        for key, label in (("hue", "Hue"), ("saturation", "Saturation"), ("value", "Value")):
            if key in wanted:
                links.new(knob("%s.%s" % (who, key), wanted[key]), n.inputs[label])
        color = n.outputs["Color"]
    if "color" in wanted:
        flat = add("ShaderNodeRGB", who + ".color")
        flat.outputs[0].default_value = tuple(wanted["color"][:3]) + (1.0,)
        color = blend(knob(who + ".color amount", wanted["color"][3]), color, flat.outputs[0], True)
    return color


# Start again from the texture as it was: drop an earlier retouch, put the first links back.
for n in [n for n in nodes if n.name.startswith("retouch: ")]:
    nodes.remove(n)
if "retouch_was" not in mat:
    was = {"emission": list(bsdf.inputs["Emission Color"].default_value)}
    for label in ("Base Color", "Roughness", "Metallic", "Normal"):
        if bsdf.inputs[label].is_linked:
            link = bsdf.inputs[label].links[0]
            was[label] = [link.from_node.name, link.from_socket.identifier]
    mat["retouch_was"] = json.dumps(was)
was = json.loads(mat["retouch_was"])
first = {}
for label in ("Base Color", "Roughness", "Metallic", "Normal"):
    if label in was:
        first[label] = next(s for s in nodes[was[label][0]].outputs if s.identifier == was[label][1])
        links.new(first[label], bsdf.inputs[label])
bsdf.inputs["Emission Color"].default_value = was["emission"]

color = first.get("Base Color")
if color is None:
    flat = add("ShaderNodeRGB", "all.base color")
    flat.outputs[0].default_value = bsdf.inputs["Base Color"].default_value
    color = flat.outputs[0]
texture = color
split = add("ShaderNodeSeparateColor", "hue saturation value")
split.mode = "HSV"
links.new(texture, split.inputs[0])
place = add("ShaderNodeSeparateXYZ", "place")
links.new(add("ShaderNodeNewGeometry", "geometry").outputs["Position"], place.inputs[0])

masks = {}
for region in PARAMS["regions"]:
    who, where, terms = region["name"], region.get("where", {}), []
    if "box" in where:
        for i, axis in enumerate("xyz"):
            terms.append(calc("GREATER_THAN", place.outputs[i], knob("%s.min %s" % (who, axis), where["box"]["min"][i])))
            terms.append(calc("LESS_THAN", place.outputs[i], knob("%s.max %s" % (who, axis), where["box"]["max"][i])))
    for i, key in enumerate(("hue", "saturation", "value")):
        if key in where:
            low, high = sorted(where[key])
            soft = where.get("soft", 0.03)
            # 1 inside the range, fading to 0 over `soft` outside each end
            rise = calc("ADD", calc("DIVIDE", calc("SUBTRACT", split.outputs[i], knob("%s.%s from" % (who, key), low)), soft), 1.0, True)
            fall = calc("ADD", calc("DIVIDE", calc("SUBTRACT", knob("%s.%s to" % (who, key), high), split.outputs[i]), soft), 1.0, True)
            inside = calc("MULTIPLY", rise, fall)
            terms.append(calc("SUBTRACT", 1.0, inside) if where[key][0] > where[key][1] else inside)
    mask = terms[0] if terms else knob(who + ".everywhere", 1.0)
    for term in terms[1:]:
        mask = calc("MULTIPLY", mask, term)
    masks[who] = mask

overall = PARAMS["overall"]
color = tinted(color, overall, "all")
for region in PARAMS["regions"]:
    wanted = region.get("set", {})
    if any(k in wanted for k in TINTS):
        color = blend(masks[region["name"]], color, tinted(color, wanted, region["name"]), True)
links.new(color, bsdf.inputs["Base Color"])

levels = {}
for key in ("metallic", "roughness", "subsurface", "bump", "grain"):
    level = first.get(LEVELS.get(key))
    if isinstance(overall.get(key), (list, tuple)) and level is not None:
        squeeze = add("ShaderNodeMapRange", "all.roughness squeeze")
        links.new(level, squeeze.inputs["Value"])
        links.new(knob("all.roughness from", overall[key][0]), squeeze.inputs["To Min"])
        links.new(knob("all.roughness to", overall[key][1]), squeeze.inputs["To Max"])
        level = squeeze.outputs["Result"]
    elif key in overall:
        value = overall[key]
        level = knob("all." + key, sum(value) / 2 if isinstance(value, (list, tuple)) else value)
    for region in PARAMS["regions"]:
        if key in region.get("set", {}):
            if level is None:
                level = knob("all." + key, bsdf.inputs[LEVELS[key]].default_value if key in LEVELS else 0.0)
            level = blend(masks[region["name"]], level, knob("%s.%s" % (region["name"], key), region["set"][key]))
    levels[key] = level
    if level is not None and key in LEVELS:
        links.new(level, bsdf.inputs[LEVELS[key]])
if levels["subsurface"] is not None:
    bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.45, 0.25)
    bsdf.inputs["Subsurface Scale"].default_value = 0.008 * size
if levels["bump"] is not None or levels["grain"] is not None:
    gray = add("ShaderNodeRGBToBW", "texture light and dark")
    links.new(texture, gray.inputs[0])
    noise = add("ShaderNodeTexNoise", "grain")
    noise.inputs["Scale"].default_value = 1 / (overall.get("grain_size", 0.002) * size)
    noise.inputs["Detail"].default_value = 6
    links.new(add("ShaderNodeTexCoord", "coordinates").outputs["Object"], noise.inputs["Vector"])
    height = calc("ADD", calc("MULTIPLY", gray.outputs[0], levels["bump"] if levels["bump"] is not None else 0.0),
                  calc("MULTIPLY", noise.outputs[0], levels["grain"] if levels["grain"] is not None else 0.0))
    bump = add("ShaderNodeBump", "bump")
    bump.inputs["Distance"].default_value = 0.001 * size
    links.new(height, bump.inputs["Height"])
    if "Normal" in first:
        links.new(first["Normal"], bump.inputs["Normal"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
if PARAMS["show"]:
    if PARAMS["show"] not in masks:
        raise ValueError("show: no region named %r" % PARAMS["show"])
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.0, 0.0, 1.0)
    links.new(calc("MULTIPLY", masks[PARAMS["show"]], knob("show", 1.0)), bsdf.inputs["Emission Strength"])

# What the texture is like in each area, to pick ranges by.
def spread_of(values):
    ordered = sorted(values)
    return [round(ordered[int(q * (len(ordered) - 1))], 3) for q in (0.1, 0.5, 0.9)]

def linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

report = []
image = texture.node.image if texture.node.type == "TEX_IMAGE" else None
if image and obj.data.uv_layers.active:
    wide, tall = image.size
    pixels = image.pixels[:]
    srgb = image.colorspace_settings.name == "sRGB"
    uvs = obj.data.uv_layers.active.data
    world = obj.matrix_world
    polygons = obj.data.polygons
    seen = []
    for index in range(0, len(polygons), max(1, len(polygons) // 40000)):
        poly = polygons[index]
        u, v = uvs[poly.loop_start].uv
        at = 4 * (int(min(max(v, 0), 0.9999) * tall) * wide + int(min(max(u, 0), 0.9999) * wide))
        rgb = [linear(c) if srgb else c for c in pixels[at:at + 3]]
        seen.append((world @ poly.center, colorsys.rgb_to_hsv(rgb[0], rgb[1], rgb[2]), poly.area))
    total = sum(s[2] for s in seen) or 1.0
    for region in [{"name": "all"}] + PARAMS["regions"]:
        where = region.get("where", {})
        boxed = seen
        if "box" in where:
            low, high = where["box"]["min"], where["box"]["max"]
            boxed = [s for s in seen if all(low[i] <= s[0][i] <= high[i] for i in range(3))]
        picked = boxed
        for i, key in enumerate(("hue", "saturation", "value")):
            if key in where:
                a, b = where[key]
                picked = [s for s in picked if (a <= s[1][i] <= b if a <= b else s[1][i] >= a or s[1][i] <= b)]
        entry = {"region": region["name"], "covers_%": round(100 * sum(s[2] for s in picked) / total, 2)}
        if boxed:
            entry["in_box" if "box" in where else "texture"] = {
                key: spread_of([s[1][i] for s in boxed]) for i, key in enumerate(("hue", "saturation", "value"))}
        report.append(entry)

print("RESULT " + json.dumps({
    "object": obj.name,
    "material": mat.name,
    "set": sorted(k for k, v in levels.items() if v is not None) + (["color"] if color != texture else []),
    "showing": PARAMS["show"],
    "knobs": knobs,
    "texture_in": report,
}))
