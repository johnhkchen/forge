# Bake an object's look into plain textures that glTF can carry.
#
# Two modes:
#   "materials"  Same mesh, same UVs. Bakes whatever the shader computes
#                (color ramps, mixes, hand-set metallic/roughness) into
#                base-color, metallic and roughness images, and swaps in one
#                simple material that uses them. Do this before exporting a
#                GLB whenever the material is more than plain textures, or
#                the export silently drops your fixes.
#   "onto"       Bakes the full mesh's color, metallic, roughness AND surface
#                detail (a normal map) onto another, lighter mesh: usually the
#                "(quads)" mesh from retopo.py, or a decimated copy. Gives the
#                target fresh UVs first.
#
# "onto" a block-out that has gear (build.py's groups) bakes by group: each
# piece of gear copies only the surface that is its own, the outermost one
# near it, and the body copies skin. Where a piece has no surface of its own
# to copy (a hem that hangs lower than the real one, a lining, skin under a
# coat) it gets the average color the rest of that piece found, not whatever
# lies behind it. "groups" in the result says how much of each piece was
# copied and how much was filled in.
#
# Send this whole file through the blender MCP `execute_blender_code` tool
# after editing PARAMS. Prints RESULT {json}.
#
# It renders with Cycles on Blender's main thread, so Blender is frozen while
# it runs: about 10-60 s at 1024, several times that at 2048. Tell the person
# before you start it.
#
# Safe-mode compatible: bpy, bmesh, mathutils, math and json only.

PARAMS = {
    "object": None,          # mesh object name; None = the largest visible mesh
    "mode": "materials",     # "materials" or "onto"
    "target": None,          # "onto" only: the mesh to bake onto; None = the "(quads)" or "(light)" mesh
    "texture_size": 1024,    # 1024 for web/game, 2048 for close-ups, 256 for low poly
    "maps": ["color", "roughness", "metallic", "normal"],  # normal: "onto" only
    "metallic": True,        # bake a metallic map (skip for objects with no metal)
    "roughness": 0.85,       # used when no roughness map is baked
    # "onto" only: how far from the light mesh to look for the full one, as a
    # share of the object's size (0.02 = 2%). None = 1%, or more for a coarse
    # mesh. A list looks near first, then farther for what that missed:
    # [0.02, 0.07] suits a block-out, which sits well off the full mesh in places.
    "reach": None,
    # Low-poly style: bake the full mesh's soft shadows (ambient occlusion)
    # into the color, so one texture carries the shading a normal map would.
    "ao": False,
    "ao_strength": 0.8,
    # "onto" a block-out: where it sits too far from the full mesh for the
    # bake to find anything (a hat brim built flat, a hand built as a
    # mitten), use the block-out's own painted color there instead of black.
    "fill": False,
    # "onto" a block-out with gear: bake by group (see above). None = whenever
    # the target has gear; False = the plain bake, every piece alike.
    "by_group": None,
    # With by_group: the boxes of the part-finding step (parts.json's "parts"). A box named like
    # a piece of gear ("kilt front" for "hide kilt") says where that piece is on the full mesh:
    # nothing else copies from inside it, and the piece copies from outside it only what is close.
    "parts": None,
    # With a flat-color block-out: bake nothing to keep; set the painted colors
    # from what the detailed mesh shows. The body's become the average found
    # for each (skin, hair). A piece of gear's all move by the same amount, so
    # the kilt is the kilt's brown and stripes painted on it stay stripes.
    "repaint": False,
}

import bpy
import bmesh
import json
import math
import mathutils
from collections import deque
from mathutils.bvhtree import BVHTree



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


def size_of(obj):
    return max(obj.dimensions)


def select_only(objs, active):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def principled(mat):
    if not mat or not mat.use_nodes:
        return None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    return None


def output_node(mat):
    for node in mat.node_tree.nodes:
        if node.type == "OUTPUT_MATERIAL" and node.is_active_output:
            return node
    return None


def route_to_emission(mat, channel):
    """Show one Principled input as pure emission, so an EMIT bake records
    exactly that value. "Position" shows where the surface is instead (inside
    the box `frame`, as 0 to 1). Returns what to undo."""
    bsdf = principled(mat)
    out = output_node(mat)
    if bsdf is None or out is None:
        return None
    tree = mat.node_tree
    emit = tree.nodes.new("ShaderNodeEmission")
    emit.inputs["Strength"].default_value = 1.0
    added = [emit]
    if channel == "Position":
        place = tree.nodes.new("ShaderNodeNewGeometry")
        fit = tree.nodes.new("ShaderNodeMapping")
        fit.inputs["Scale"].default_value = (frame[1], frame[1], frame[1])
        fit.inputs["Location"].default_value = tuple(-c * frame[1] for c in frame[0])
        tree.links.new(place.outputs["Position"], fit.inputs["Vector"])
        tree.links.new(fit.outputs["Vector"], emit.inputs["Color"])
        added += [place, fit]
    elif not channel:  # plain white: a bake of it is white wherever the bake found the surface
        emit.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    else:
        sock = bsdf.inputs[channel]
        if sock.is_linked:
            tree.links.new(sock.links[0].from_socket, emit.inputs["Color"])
        else:
            v = sock.default_value
            emit.inputs["Color"].default_value = (v[0], v[1], v[2], 1.0) if channel == "Base Color" else (v, v, v, 1.0)
    old = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].is_linked else None
    tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return (mat, added, out, old)


def undo_route(undo):
    if undo is None:
        return
    mat, added, out, old = undo
    if old is not None:
        mat.node_tree.links.new(old, out.inputs["Surface"])
    for node in added:
        mat.node_tree.nodes.remove(node)


def new_image(name, size, data, exact=False):
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=exact)
    if data:
        img.colorspace_settings.name = "Non-Color"
    return img


def target_into(mats, img):
    """Make `img` the active image node in each material, which is where
    Cycles writes a bake. Returns the temporary nodes."""
    temp = []
    for mat in mats:
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = img
        mat.node_tree.nodes.active = node
        temp.append((mat, node))
    return temp


def drop(temp):
    for mat, node in temp:
        mat.node_tree.nodes.remove(node)


def bake_pass(kind, source_mats, target_mats, img, selected_to_active, reach):
    temp = target_into(target_mats, img)
    try:
        settings = dict(type=kind, margin=8, use_clear=True)
        if selected_to_active and cage is not None:  # by group: rays start on the cage and stop `reach` further in
            settings.update(use_selected_to_active=True, use_cage=True, cage_object=cage.name, max_ray_distance=reach)
        elif selected_to_active:
            settings.update(use_selected_to_active=True, cage_extrusion=reach, max_ray_distance=reach * 2)
        if kind == "NORMAL":
            settings.update(normal_space="TANGENT")
        bpy.ops.object.bake(**settings)
    finally:
        drop(temp)
    img.pack()


def own_colors(target, holder, img, layer=None):
    """One of the target's painted layers (its vertex colors, unless `layer` names another) as a
    texture laid out like the baked ones."""
    tree = holder.node_tree
    paint = tree.nodes.new("ShaderNodeVertexColor")
    paint.layer_name = layer or target.data.color_attributes[0].name
    emit = tree.nodes.new("ShaderNodeEmission")
    tree.links.new(paint.outputs["Color"], emit.inputs["Color"])
    out = output_node(holder)
    old = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].is_linked else None
    tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    select_only([target], target)
    try:
        bake_pass("EMIT", [holder], [holder], img, False, 0)
    finally:
        if old is not None:
            tree.links.new(old, out.inputs["Surface"])
        tree.nodes.remove(emit)
        tree.nodes.remove(paint)

def patch(img, found, other, plain):
    """Where `found` is black (the bake met nothing), take `other`'s pixel, or the `plain` color."""
    pixels = list(img.pixels)
    spare = list(other.pixels) if other else None
    missed = 0
    for i in range(0, len(pixels), 4):
        if found[i] < 0.5:
            missed += 1
            pixels[i:i + 3] = spare[i:i + 3] if spare else plain
    img.pixels[:] = pixels
    img.pack()
    return missed

def prepare_target(low):
    """Fresh UVs and a placeholder material, so the bake has somewhere to write."""
    select_only([low], low)
    for layer in list(low.data.uv_layers):
        low.data.uv_layers.remove(layer)
    low.data.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")
    low.data.materials.clear()
    holder = bpy.data.materials.new(low.name + " bake")
    holder.use_nodes = True
    low.data.materials.append(holder)


def final_material(name, maps):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    bsdf = principled(mat)
    x = -400

    def tex(img, y):
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = img
        node.location = (x - 300, y)
        return node

    tree.links.new(tex(maps["color"], 300).outputs["Color"], bsdf.inputs["Base Color"])
    if "roughness" in maps:
        tree.links.new(tex(maps["roughness"], 0).outputs["Color"], bsdf.inputs["Roughness"])
    else:
        bsdf.inputs["Roughness"].default_value = PARAMS["roughness"]
    if "metallic" in maps:
        tree.links.new(tex(maps["metallic"], -300).outputs["Color"], bsdf.inputs["Metallic"])
    else:
        bsdf.inputs["Metallic"].default_value = 0.0
    if "normal" in maps:
        nmap = tree.nodes.new("ShaderNodeNormalMap")
        nmap.location = (x, -600)
        tree.links.new(tex(maps["normal"], -600).outputs["Color"], nmap.inputs["Color"])
        tree.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return mat



# ---- by group: which surface each point of a dressed block-out should copy ----

def world_tree(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    return tree


def facing(tree, point, normal, above, below, step):
    """Heights along `normal`, from `above` the point down to `below` it, where the full mesh has a
    surface you would see looking in from outside: one that faces the same way as `normal` with
    air over it. Not the far side of a limb, and not a layer buried inside the body."""
    loc, way, index, dist = tree.ray_cast(point + normal * above, normal, (above + below) * 40)
    buried = loc is not None and way.dot(normal) > 0.0  # the look starts inside something
    got, top = [], above
    for _ in range(40):
        if top <= -below:
            break
        loc, way, index, dist = tree.ray_cast(point + normal * top, -normal, top + below)
        if loc is None:
            break
        top -= dist
        if way.dot(normal) > 0.0:
            if not buried and way.dot(normal) > 0.1:
                got.append(top)
            buried = True
        else:
            buried = False
        top -= step
    return got


def words(name):
    """A name as a set of plain words: no plurals, and no words that only say which one of two."""
    plain = "".join(c if c.isalnum() else " " for c in name.lower()).split()
    aside = ("left", "right", "front", "back", "side", "l", "r", "low", "mid", "high", "upper", "lower", "top", "bottom")
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in plain} - set(aside)


def part_boxes(parts, tags, pad):
    """[(box, group)] in the parts' order: the group is the gear a part is named like, or -1 for a
    part that is no gear's (a tusk, hair). A box is (low, high, turn-back matrix or None, center)."""
    boxes = []
    for part in parts or []:
        box = part.get("box", part)
        low, high = mathutils.Vector(box["min"]), mathutils.Vector(box["max"])
        turn = part.get("turn") or box.get("turn")
        back = mathutils.Euler([math.radians(a) for a in turn]).to_matrix().inverted() if turn and any(turn) else None
        said = words(part["name"])
        fits = []
        for g, tag in enumerate(tags):
            named = words(tag.get("gear") or "")
            if g and said and named and (said <= named or named <= said):
                fits.append((len(said ^ named), g))
        fits.sort()
        clear = len(fits) == 1 or (len(fits) > 1 and fits[0][0] < fits[1][0])
        grow = mathutils.Vector((pad, pad, pad))
        boxes.append(((low - grow, high + grow, back, (low + high) / 2), fits[0][1] if clear else -1))
    return boxes


def owners(p, boxes):
    """The gear groups whose boxes a place on the full mesh is in (boxes overlap: a belt's knot hangs over the kilt)."""
    got = set()
    for box, g in boxes:
        low, high, back, center = box
        q = back @ (p - center) + center if back else p
        if g > 0 and low[0] <= q[0] <= high[0] and low[1] <= q[1] <= high[1] and low[2] <= q[2] <= high[2]:
            got.add(g)
    return got


def plan(target, tree, size, far, boxes):
    """For every point of the target, the height above it (along its normal, negative = below) of
    the surface it should copy, or None when the full mesh has no surface that is this piece's own.

    - Under another piece (skin under a kilt, a kilt under its belt) a face is "hidden" and copies
      nothing. The picture showed the character dressed, so what the full mesh has there is the
      piece on top. That is every body face drape.py marked as hidden, every point of the body
      with gear close over it, and any face of gear whose every point has another piece close
      over it: a surface facing away from the point, or one facing it with its other side
      close behind (cloth, not a limb).
    - Otherwise the outermost surface you would see from outside (`facing`), within 2% of the
      size first and as far as `far` only when nothing is that close. Never past the next limb,
      so a shirt's side doesn't take the arm.
    - "doubt": gear that found its surface deeper than its own lining, or about where the body
      is under a piece that hangs clear of it. The geometry can't say whether that is the kilt
      or the leg behind its hem; the color can (see settle).
    - With part boxes: a piece of gear that has boxes takes a surface outside every gear's box
      only when it is close by. So a hem that hangs lower than the real one doesn't take the leg
      behind it. (The boxes are loose, a belt's box holds some belly and some kilt, so they are
      not used to keep one piece out of another's.)"""
    me = target.data
    world = target.matrix_world
    turn = world.to_3x3()
    points = [world @ v.co for v in me.vertices]
    normals = [(turn @ v.normal).normalized() for v in me.vertices]
    marks = [0] * len(me.polygons)
    if me.attributes.get("forge_group") is not None:
        me.attributes["forge_group"].data.foreach_get("value", marks)
    own = BVHTree.FromPolygons([tuple(p) for p in points], [tuple(p.vertices) for p in me.polygons])
    group = [None] * len(points)
    for p in me.polygons:
        for v in p.vertices:
            group[v] = marks[p.index]
    boxed = {g for box, g in boxes if g > 0}
    hidden = [0] * len(me.polygons)
    if me.attributes.get("forge_under") is not None:
        me.attributes["forge_under"].data.foreach_get("value", hidden)
    hidden = [bool(h) and not marks[i] for i, h in enumerate(hidden)]
    step, cover, close, near, hang, slack = size * 0.001, size * 0.04, size * 0.015, size * 0.02, size * 0.015, size * 0.02
    lifts = [None] * len(points)
    covered = [False] * len(points)
    doubt = [False] * len(points)
    for i, point in enumerate(points):
        g, normal = group[i], normals[i]
        if g is None:
            continue
        above = far * 0.6
        loc, way, index, dist = own.ray_cast(point + normal * step, normal, far)
        if loc is not None:
            if marks[index] != g and dist < cover:
                over = way.dot(normal) > 0.0 or not g  # over skin, anything worn this close is cloth
                if not over:
                    behind = own.ray_cast(loc + normal * step, normal, cover * 0.6)
                    over = behind[0] is not None and marks[behind[2]] == marks[index] and behind[1].dot(normal) > 0.0
                covered[i] = over
            if way.dot(normal) < 0.0 and not covered[i]:  # the next limb, facing this one
                above = min(above, dist)
        if covered[i] and not g:  # skin with cloth over it: the full mesh has the cloth there
            continue
        wall = gap = None
        if g:  # what lies under this point of gear: the piece's own lining or far wall, then the body
            loc, way, index, dist = own.ray_cast(point - normal * step, -normal, far)
            if loc is not None and marks[index] == g:
                wall = dist
                loc, way, index, dist = own.ray_cast(loc - normal * step, -normal, far)
                dist = dist + wall if loc is not None else None
            if loc is not None and marks[index] == 0:
                gap = dist
        for high, deep in ((min(near, above), near), (above, far)):  # close by first, as far as `far` only if nothing is
            for h in facing(tree, point, normal, high, deep, step):
                whose = owners(point + normal * h, boxes) if boxes else ()
                if whose or g not in boxed or abs(h) <= close:
                    lifts[i] = h
                    break
            if lifts[i] is not None:
                break
        # Gear whose surface was found deeper than its own lining, or that hangs clear of the body
        # and found a surface about where the body is: that may be the leg behind a hem.
        # settle() keeps it only if its color is the piece's, not the body's.
        if lifts[i] is not None:
            doubt[i] = (wall is not None and lifts[i] < -wall) or (gap is not None and gap > hang and lifts[i] < slack - gap)
    crest = [lift or 0.0 for lift in lifts]  # how high the surface stands over each point and the faces around it
    for p in me.polygons:
        if all(covered[v] for v in p.vertices):  # a face with another piece over all of it is hidden too
            hidden[p.index] = True
        if hidden[p.index] or any(lifts[v] is None for v in p.vertices):
            continue
        normal = (turn @ p.normal).normalized()
        middle = facing(tree, world @ p.center, normal, near, near, step)
        top = max([lifts[v] for v in p.vertices] + middle[:1])  # a bulge between the points counts too
        for v in p.vertices:
            crest[v] = max(crest[v], top)
    return {"points": points, "normals": normals, "lifts": lifts, "group": group, "marks": marks, "hidden": hidden,
            "doubt": doubt, "crest": crest, "boxed": sorted(boxed)}


def make_cage(target, found, size):
    """A copy of the target swollen so that every point sits just above the surface it should copy
    (and above what its faces' other points and middles found, so no ray starts under it). The
    bake's rays start on it. Returns (the cage, how far a ray must reach)."""
    lifts = found["lifts"]
    cage = target.copy()
    cage.data = target.data.copy()
    cage.name = target.name + " cage"
    for c in target.users_collection:
        c.objects.link(cage)
    back = target.matrix_world.inverted()
    margin, reach = size * 0.004, size * 0.02
    for i, v in enumerate(cage.data.vertices):
        height = max(found["crest"][i], 0.0) + margin
        v.co = back @ (found["points"][i] + found["normals"][i] * height)
        if lifts[i] is not None:
            reach = max(reach, height - lifts[i] + size * 0.01)
    return cage, reach


def paint_layers(target, found):
    """Two painted layers a bake of the target itself can read back per pixel: where the surface
    to copy should be ("bake expect", in the box `frame`), and which group the pixel is in and
    whether its points found a surface, and whether that surface is in doubt ("bake marks")."""
    me = target.data
    expect = me.color_attributes.new("bake expect", "FLOAT_COLOR", "POINT")
    for i, point in enumerate(found["points"]):
        lift = found["lifts"][i] or 0.0
        at = (point + found["normals"][i] * lift - frame[0]) * frame[1]
        expect.data[i].color = (at[0], at[1], at[2], 1.0)
    marks = me.color_attributes.new("bake marks", "FLOAT_COLOR", "CORNER")
    for p in me.polygons:
        g = found["marks"][p.index] / 64.0
        for loop in p.loop_indices:
            v = me.loops[loop].vertex_index
            ok = found["lifts"][v] is not None and not found["hidden"][p.index]
            marks.data[loop].color = (g, 1.0 if ok else 0.0, 1.0 if found["doubt"][v] else 0.5, 1.0)
    return [expect.name, marks.name]


def shade_key(pixels, i):
    return (int(pixels[i] * 15 + 0.5) * 16 + int(pixels[i + 1] * 15 + 0.5)) * 16 + int(pixels[i + 2] * 15 + 0.5)


def settle(maps, layers, tolerance, flat, side):
    """Keep a pixel only where the bake hit the surface its piece was looking for. Every other
    pixel is filled in: next to kept pixels of the same piece it continues their color, and
    further off it fades to the average of the kept pixels with the same piece and painted color
    (its own painted color if there are none). Its normal is flat. Returns (per group
    [pixels, kept], {(group, painted color): (average color, pixels)})."""
    seen = layers[0]
    where, expect, marks, own = (list(img.pixels) if img else None for img in layers[1:])
    count = len(seen) // 4
    keep = bytearray(count)
    bare = bytearray(count)  # skin under gear: the body's average, never a neighbor's color (that neighbor may be cloth)
    cluster = [0] * count
    groups = {}
    limit = (tolerance * frame[1]) ** 2
    for j in range(count):
        i = j * 4
        g = int(marks[i] * 64 + 0.5)
        cluster[j] = g * 4096 + (shade_key(own, i) if own else 0)
        bare[j] = not g and marks[i + 1] <= 0.3
        if seen[i] > 0.5 and marks[i + 1] > 0.3:
            dx, dy, dz = where[i] - expect[i], where[i + 1] - expect[i + 1], where[i + 2] - expect[i + 2]
            if dx * dx + dy * dy + dz * dz < limit:
                keep[j] = 2 if g and marks[i + 2] > 0.7 else 1
    # A gear pixel in doubt (see plan) is kept only if it looks more like the rest of its piece than like the body.
    color = list(maps["color"].pixels)
    tones = {}
    for j in range(count):
        if keep[j] == 1:
            total = tones.setdefault(cluster[j] // 4096, [0.0, 0.0, 0.0, 0])
            for c in range(3):
                total[c] += color[j * 4 + c]
            total[3] += 1
    tones = {g: [t[c] / t[3] for c in range(3)] for g, t in tones.items() if t[3] >= 50}
    for j in range(count):
        if keep[j] == 2:
            mine, skin = tones.get(cluster[j] // 4096), tones.get(0)
            if mine and skin and sum((color[j * 4 + c] - skin[c]) ** 2 for c in range(3)) < sum((color[j * 4 + c] - mine[c]) ** 2 for c in range(3)):
                keep[j] = 0
            else:
                keep[j] = 1
    used = {}
    for j in range(count):
        if marks[j * 4 + 2] > 0.25:  # a pixel some face uses
            tally = groups.setdefault(cluster[j] // 4096, [0, 0])
            tally[0] += 1
            tally[1] += keep[j]
            used[cluster[j]] = used.get(cluster[j], 0) + 1
    del where, expect, marks, color
    # each pixel to fill: the nearest kept pixel of its group, and how many steps away it is
    fade = max(side // 40, 4)
    origin = [-1] * count
    steps = [0] * count
    queue = deque(j for j in range(count) if keep[j])
    for j in queue:
        origin[j] = j
    while queue:
        j = queue.popleft()
        if steps[j] >= fade:
            continue
        x = j % side
        for k in (j - 1 if x else -1, j + 1 if x < side - 1 else -1, j - side, j + side):
            if 0 <= k < count and origin[k] < 0 and not bare[k] and cluster[k] // 4096 == cluster[j] // 4096:
                origin[k] = origin[j]
                steps[k] = steps[j] + 1
                queue.append(k)
    averages = {}
    for key, img in maps.items():
        pixels = list(img.pixels)
        if key == "normal":
            for j in range(count):
                if not keep[j]:
                    pixels[j * 4:j * 4 + 3] = [0.5, 0.5, 1.0]
        else:
            sums = {}
            for j in range(count):
                if keep[j]:
                    total = sums.setdefault(cluster[j], [0.0, 0.0, 0.0, 0])
                    i = j * 4
                    total[0] += pixels[i]
                    total[1] += pixels[i + 1]
                    total[2] += pixels[i + 2]
                    total[3] += 1
            mean = {c: [t[0] / t[3], t[1] / t[3], t[2] / t[3]] for c, t in sums.items()}
            if key == "color":
                # The average is only as good as the pixels kept. Some of a body's are cloth (a collar's edge, a strap),
                # so start from the middle value of each channel and take the half nearest it, twice: the color most
                # of them agree on. And where only a little of a painted color was kept (a body nearly all under
                # clothes), trust the painted color instead.
                lists = {}
                for j in range(count):
                    if keep[j]:
                        held = lists.setdefault(cluster[j], ([], [], []))
                        for c in range(3):
                            held[c].append(pixels[j * 4 + c])
                mean = {c: [sorted(v)[len(v) // 2] for v in held] for c, held in lists.items()}
                del lists
                for _ in range(2):
                    off = {}
                    for j in range(count):
                        if keep[j]:
                            m, i = mean[cluster[j]], j * 4
                            off.setdefault(cluster[j], []).append((pixels[i] - m[0]) ** 2 + (pixels[i + 1] - m[1]) ** 2 + (pixels[i + 2] - m[2]) ** 2)
                    middle = {c: sorted(d)[len(d) // 2] for c, d in off.items()}
                    sums = {}
                    for j in range(count):
                        if keep[j]:
                            m, i = mean[cluster[j]], j * 4
                            if (pixels[i] - m[0]) ** 2 + (pixels[i + 1] - m[1]) ** 2 + (pixels[i + 2] - m[2]) ** 2 <= middle[cluster[j]]:
                                total = sums.setdefault(cluster[j], [0.0, 0.0, 0.0, 0])
                                total[0] += pixels[i]
                                total[1] += pixels[i + 1]
                                total[2] += pixels[i + 2]
                                total[3] += 1
                    mean = {c: [t[0] / t[3], t[1] / t[3], t[2] / t[3]] for c, t in sums.items()}
                mean = {c: m for c, m in mean.items() if not own or len(off[c]) >= 0.25 * used.get(c, 0)}
                averages = {c: (mean[c], len(off[c])) for c in mean}
            for j in range(count):
                if not keep[j]:
                    i = j * 4
                    plain = mean.get(cluster[j]) or (own[i:i + 3] if own and key == "color" else flat[key])
                    if origin[j] >= 0:
                        o, t = origin[j] * 4, steps[j] / fade
                        plain = [pixels[o + c] * (1.0 - t) + plain[c] * t for c in range(3)]
                    pixels[i:i + 3] = plain
        img.pixels[:] = pixels
        img.pack()
    return groups, averages


def repaint(target, found, averages):
    """Flat colors, set from what the bake found. On the body each painted color becomes the
    average found for it: skin the skin's, hair the hair's. On a piece of gear all its painted
    colors move by the same amount, so that on average they are the piece's: the kilt becomes
    the kilt's brown, and stripes someone painted on it stay stripes.
    Returns {group: [average before, average after]}."""
    me = target.data
    paint = me.color_attributes[0]
    shift, body = {}, {}
    for key, pair in averages.items():
        shade = key % 4096
        was = [(shade // 256) / 15.0, (shade // 16 % 16) / 15.0, (shade % 16) / 15.0]
        if not key // 4096 and pair[1] >= 16:
            body[shade] = pair[0]
        total = shift.setdefault(key // 4096, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0])
        for c in range(3):
            total[c] += was[c] * pair[1]
            total[c + 3] += pair[0][c] * pair[1]
        total[6] += pair[1]
    done = set()
    for p in me.polygons:
        g = found["marks"][p.index]
        move = shift.get(g)
        if not move or move[6] < 16:
            continue
        for loop in p.loop_indices:
            at = loop if paint.domain == "CORNER" else me.loops[loop].vertex_index
            if at in done:
                continue
            done.add(at)
            was = paint.data[at].color_srgb
            if g:
                paint.data[at].color_srgb = [min(max(was[c] + (move[c + 3] - move[c]) / move[6], 0.0), 1.0) for c in range(3)] + [was[3]]
                continue
            near = [int(was[c] * 15 + 0.5) for c in range(3)]
            for shade, now in body.items():  # the same painted color, give or take the rounding
                if max(abs(shade // 256 - near[0]), abs(shade // 16 % 16 - near[1]), abs(shade % 16 - near[2])) <= (0 if near[0] * 256 + near[1] * 16 + near[2] in body else 1):
                    paint.data[at].color_srgb = [now[0], now[1], now[2], was[3]]
                    break
    return {g: [[round(t[c] / t[6], 3) for c in range(3)], [round(t[c + 3] / t[6], 3) for c in range(3)]] for g, t in shift.items() if t[6] >= 16}


mode = PARAMS["mode"]
if mode not in ("materials", "onto"):
    raise ValueError("mode must be 'materials' or 'onto'")
obj = pick_object(PARAMS["object"]) if mode == "materials" or PARAMS["object"] else None
if obj is None:
    # "onto" with no source named: the hidden full mesh retopo.py or
    # decimate.py (as_copy) left behind next to the light one.
    lights = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.name.endswith((" (quads)", " (light)"))]
    if not lights:
        raise ValueError("name the source object, or run retopo.py or decimate.py (as_copy) first")
    PARAMS["target"] = PARAMS["target"] or lights[0].name
    obj = bpy.data.objects.get(lights[0].name.rsplit(" (", 1)[0])
    if obj is None:
        raise ValueError("cannot find the full mesh for %r" % lights[0].name)
source_mats = [s.material for s in obj.material_slots if principled(s.material)]
if not source_mats:
    raise ValueError("%s has no Principled BSDF material to bake from" % obj.name)

scene = bpy.context.scene
cage = None   # by group: the swollen copy of the target the rays start from
frame = None  # by group: (corner, 1 / side) of a box around both meshes, so a place can be stored as a color
worn = []
saved = (scene.render.engine, scene.cycles.samples)
scene.render.engine = "CYCLES"
size = PARAMS["texture_size"]
reach = size_of(obj) * 0.01

if mode == "onto":
    target = bpy.data.objects.get(PARAMS["target"] or obj.name + " (quads)") or bpy.data.objects.get(obj.name + " (light)")
    if target is None or target.type != "MESH":
        raise ValueError("no mesh to bake onto: %r" % (PARAMS["target"] or obj.name + " (quads)"))
    worn = list(target.data.materials)
    prepare_target(target)
    select_only([obj, target], target)
    target_mats = [s.material for s in target.material_slots]
else:
    target = obj
    select_only([obj], obj)
    target_mats = source_mats
selected_to_active = mode == "onto"
if selected_to_active:
    # A coarse target sits further from the true surface, so the bake has to
    # look further to find it; too short a reach leaves black patches.
    edges = target.data.edges
    verts = target.data.vertices
    mean_edge = sum((verts[e.vertices[0]].co - verts[e.vertices[1]].co).length for e in edges) / max(len(edges), 1)
    reach = max(reach, mean_edge * max(target.scale) * 0.75)
reaches = [reach]
if selected_to_active and PARAMS["reach"]:
    asked = PARAMS["reach"] if isinstance(PARAMS["reach"], list) else [PARAMS["reach"]]
    reaches = [size_of(obj) * share for share in asked]
base = target.name
filled = None
tags = json.loads(target.get("forge_groups", "[]")) if selected_to_active else []
by_group = bool(selected_to_active and PARAMS["by_group"] is not False and (
    PARAMS["by_group"] or PARAMS["repaint"] or (len(tags) > 1 and target.data.attributes.get("forge_group") is not None)))
flat_colors = bool(by_group and PARAMS["repaint"] and target.data.color_attributes)
spots = groups = averages = None
if by_group:
    full_size = size_of(obj)
    asked = PARAMS["reach"] if isinstance(PARAMS["reach"], list) else [PARAMS["reach"] or 0.07]
    spots = plan(target, world_tree(obj), full_size, full_size * max(asked), part_boxes(PARAMS["parts"], tags, full_size * 0.01))
    corners = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box] + spots["points"]
    low = mathutils.Vector([min(c[i] for c in corners) - full_size * 0.1 for i in range(3)])
    side = max(max(c[i] for c in corners) - low[i] for i in range(3)) + full_size * 0.1
    frame = (low, 1.0 / side)
    cage, reach = make_cage(target, spots, full_size)
    reaches = [reach]
    select_only([obj, target], target)

wanted = {"color"} if flat_colors else set(PARAMS["maps"])
if not PARAMS["metallic"]:
    wanted.discard("metallic")
channels = [c for c in (("color", "Base Color", False), ("roughness", "Roughness", True),
                        ("metallic", "Metallic", True)) if c[0] in wanted]

def bake_set(reach, tag, with_mask):
    """Every wanted map baked with one reach. Returns {map: image} and, with `with_mask`, which
    pixels the bake found the full mesh for (a list like an image's pixels: 1 found, 0 not)."""
    got = {}
    scene.cycles.samples = 1  # an emission bake needs a single sample
    for key, socket, data in channels:
        img = new_image("%s %s%s" % (base, key, tag), size, data)
        undo = [route_to_emission(m, socket) for m in source_mats]
        try:
            bake_pass("EMIT", source_mats, target_mats, img, selected_to_active, reach)
        finally:
            for u in undo:
                undo_route(u)
        got[key] = img
    if selected_to_active and "normal" in wanted:
        scene.cycles.samples = 4
        img = new_image("%s normal%s" % (base, tag), size, True)
        bake_pass("NORMAL", source_mats, target_mats, img, True, reach)
        got["normal"] = img
    seen = None
    if with_mask:
        scene.cycles.samples = 1
        mask = new_image("%s found" % base, size, True)
        undo = [route_to_emission(m, None) for m in source_mats]
        try:
            bake_pass("EMIT", source_mats, target_mats, mask, True, reach)
        finally:
            for u in undo:
                undo_route(u)
        seen = list(mask.pixels)
        bpy.data.images.remove(mask)
    return got, seen

fill = bool(PARAMS["fill"] and selected_to_active and target.data.color_attributes)
try:
    maps, found = bake_set(reaches[0], "", fill or len(reaches) > 1 or by_group)
    if by_group:  # where each ray landed, to check against where its piece was looking
        scene.cycles.samples = 1
        where = new_image("%s where" % base, size, True, True)
        undo = [route_to_emission(m, "Position") for m in source_mats]
        try:
            bake_pass("EMIT", source_mats, target_mats, where, True, reaches[0])
        finally:
            for u in undo:
                undo_route(u)
    for far in reaches[1:]:  # what the near look missed, taken from a farther one
        more, seen = bake_set(far, " far", True)
        select_only([obj, target], target)
        for key, img in maps.items():
            patch(img, found, more[key], None)
            bpy.data.images.remove(more[key])
        found = [max(pair) for pair in zip(found, seen)]
    if PARAMS["ao"]:
        if scene.world is None:
            scene.world = bpy.data.worlds.new("bake world")
        scene.world.light_settings.distance = size_of(obj) * 0.08
        scene.cycles.samples = 32
        ao = new_image("%s shadows" % base, size, True)
        bake_pass("AO", source_mats, target_mats, ao, selected_to_active, reaches[0])
        color = maps["color"]
        k = PARAMS["ao_strength"]
        shade = list(ao.pixels)
        pixels = list(color.pixels)
        for i in range(0, len(pixels), 4):
            f = 1.0 - k + k * shade[i]
            pixels[i] *= f
            pixels[i + 1] *= f
            pixels[i + 2] *= f
        color.pixels[:] = pixels
        color.pack()
        bpy.data.images.remove(ao)
    if by_group:
        scene.cycles.samples = 1
        painted = len(target.data.color_attributes) > 0
        cage = None
        layers = [found, where]
        for layer in paint_layers(target, spots):
            img = new_image("%s %s" % (base, layer), size, True, True)
            own_colors(target, target_mats[0], img, layer)
            layers.append(img)
        layers.append(new_image("%s own colors" % base, size, False) if painted else None)
        if painted:
            own_colors(target, target_mats[0], layers[4])
        flat = {"color": [0.5, 0.5, 0.5], "roughness": [PARAMS["roughness"]] * 3, "metallic": [0.0, 0.0, 0.0]}
        groups, averages = settle(maps, layers, full_size * 0.02, flat, size)
        for img in layers[1:]:
            if img:
                bpy.data.images.remove(img)
        for layer in ("bake expect", "bake marks"):
            target.data.color_attributes.remove(target.data.color_attributes[layer])
    elif fill:
        scene.cycles.samples = 1
        own = new_image("%s own colors" % base, size, False)
        own_colors(target, target_mats[0], own)
        flat = {"normal": [0.5, 0.5, 1.0], "roughness": [PARAMS["roughness"]] * 3, "metallic": [0.0, 0.0, 0.0]}
        for key, img in maps.items():
            filled = patch(img, found, own if key == "color" else None, flat.get(key))
        bpy.data.images.remove(own)
finally:
    scene.render.engine, scene.cycles.samples = saved
    for o in [o for o in bpy.data.objects if o.name == target.name + " cage"]:
        spare = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.meshes.remove(spare)

result = {}
if flat_colors:
    changed = repaint(target, spots, averages)
    for img in maps.values():
        bpy.data.images.remove(img)
    holder = target.data.materials[0]
    target.data.materials.clear()
    bpy.data.materials.remove(holder)
    for mat in worn:
        target.data.materials.append(mat)
    target.data.uv_layers.remove(target.data.uv_layers[0])
    maps = {}
    result["repainted"] = [{"group": tags[g]["name"] if g < len(tags) else "all", "was": pair[0], "now": pair[1]} for g, pair in sorted(changed.items())]
    done = ["set the painted colors of %d pieces from what the detailed mesh shows there; no textures" % len(changed)]
else:
    baked = final_material(base + " baked", maps)
    target.data.materials.clear()
    target.data.materials.append(baked)
    done = ["baked %s%s at %d px" % (", ".join(sorted(maps)), " with soft shadows in the color" if PARAMS["ao"] else "", size)]
if groups is not None:
    result["groups"] = [{"name": tags[g]["name"] if g < len(tags) else "all", "pixels": n[0], "copied_%": round(100.0 * n[1] / max(n[0], 1), 1)}
                        for g, n in sorted(groups.items()) if n[0]]
    result["faces_hidden_under_another_piece"] = sum(1 for h in spots["hidden"] if h)
    result["found_by_part_boxes"] = [tags[g]["name"] for g in spots["boxed"]]
    done.append("by group: each piece copied only its own surface; the rest of it has that piece's average color")
if filled is not None:
    done.append("where the bake found nothing to copy, the texture has the block-out's own colors")
if mode == "onto":
    obj.hide_set(True)
    obj.hide_render = True
    done.append("baked onto %r (%d faces); hid the full mesh" % (target.name, len(target.data.polygons)))
else:
    done.append("replaced the material with %r, which glTF can carry" % baked.name)

print("RESULT " + json.dumps(dict(result, object=target.name, maps=sorted(maps), done=done)))
