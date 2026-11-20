# Paint a character's face from a picture of it, onto the detailed mesh.
#
# TRELLIS.2 gets a head's shape about right and its texture wrong: eyes come
# out as dark smudges, lips as a blur, glasses as black blobs. The picture
# the mesh was made from shows the same face front-on and sharp. This lays
# that picture over the front of the head like a slide projector: every
# point that faces front, with nothing in the way, takes the picture's color
# there; toward the sides, under the chin and behind anything, the mesh
# keeps its own. Shape and UVs are untouched.
#
# "picture" is the run's image.png (the whole figure, front-on), or a head
# turnaround sheet (heads/sheet.png: front, three-quarter and side views
# side by side), which shows the face much larger. With a sheet, say where
# the front view is with "panel": [left, bottom, right, top] as shares of
# the picture, or "panel": "front" to take the first view from the left.
#
# It finds where the picture sits on the mesh by itself: first by the head's
# outline (how wide it is, row by row, from the top down), then by sliding
# and scaling the picture until its light and dark agree best with the
# mesh's own texture (a smudged eye is still a dark spot in the right place).
# "fit" in the result says how well they agree (0-1) and "painted" is False
# when they don't ("least": 0.45), so a picture that doesn't match (another
# pose, a head turned away) changes nothing. Measured: the right picture on
# five characters agrees 0.60 to 0.78; another character's picture, or a
# head whose box was found wrong, 0.25 to 0.39.
#
# The paint is shader nodes named "face paint: ..." on the object's
# material, mixed in by a point attribute "face_paint" (0 = the mesh's own
# color, 1 = the picture's). Like every shader fix it reaches a .glb only
# through a bake: bake.py "materials" for this mesh, "onto" for a lighter
# one. The profile runner runs this before its bakes, so every sized
# version gets the face. "remove": True takes the nodes out again.
#
# "box" is the head: chin (or beard) to the top of the hair or hat, ears in.
# None finds it on a T-pose facing "facing": the column above the arms, down
# to where it narrows into a neck or widens into shoulders. A head sunk
# between the shoulders (a troll) needs its box given.
#
# Send through the blender MCP `execute_blender_code` tool from PARAMS down.
# Prints RESULT {json}. 5-15 s in plain Python. Safe-mode compatible.

PARAMS = {
    "object": None,     # the detailed mesh; None = the largest visible mesh
    "picture": None,    # absolute path of the picture (required unless "remove")
    "panel": None,      # None = the picture is the whole figure; "front" or [left, bottom, right, top] = a head sheet's front view
    "box": None,        # the head: {"min": [x, y, z], "max": [x, y, z]} in world meters; None = find it
    "facing": "-y",     # which way the face looks: "-y", "+y", "-x" or "+x"
    "strength": 1.0,    # how much of the picture's color to take where it is painted
    "least": 0.45,      # paint only if the picture and the mesh agree at least this well (0-1)
    "remove": False,    # True = take the paint off again
}

import bpy
import json
from mathutils import Vector

FACING = {"-y": (1, -1.0, 1.0), "+y": (1, 1.0, -1.0), "-x": (0, -1.0, -1.0), "+x": (0, 1.0, 1.0)}  # axis, which way, which way is right in the picture
CELLS = 44  # the head is compared on a grid this fine


def face_count(obj):
    return len(obj.data.polygons)

def pick_object(name):
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise ValueError("no mesh object named %r" % name)
        return obj
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get() and not o.name.endswith(" (light)")]
    if not meshes:
        raise ValueError("the scene has no visible mesh objects")
    return max(meshes, key=face_count)

def principled(mat):
    if not mat or not mat.use_nodes:
        return None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    return None

def color_image(obj):
    """The picture that colors the surface, or None if it is one flat color."""
    for mat in obj.data.materials:
        shader = principled(mat)
        if not shader or not obj.data.uv_layers.active:
            continue
        queue, met = [link.from_node for link in shader.inputs["Base Color"].links], set()
        while queue:  # retouch.py can leave hundreds of nodes between the shader and its picture
            node = queue.pop(0)
            if node.name in met:
                continue
            met.add(node.name)
            if node.type == "TEX_IMAGE" and node.image and not node.name.startswith("face paint"):
                return node.image
            for socket in node.inputs:
                queue += [link.from_node for link in socket.links]
    return None

def linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def clamp(v, low, high):
    return low if v < low else high if v > high else v

def ramp(v, low, high):
    t = clamp((v - low) / (high - low), 0.0, 1.0)
    return t * t * (3 - 2 * t)

def unpaint(obj):
    """Take the paint's nodes out, joining each material back up as it was."""
    gone = 0
    for mat in obj.data.materials:
        shader = principled(mat)
        if not shader:
            continue
        tree = mat.node_tree
        mixer = tree.nodes.get("face paint: mix")
        if mixer:
            before = mixer.inputs[6].links[0].from_socket if mixer.inputs[6].is_linked else None
            if before:
                tree.links.new(before, shader.inputs["Base Color"])
            else:
                for link in list(shader.inputs["Base Color"].links):
                    tree.links.remove(link)
                shader.inputs["Base Color"].default_value = mixer.inputs[6].default_value
        for node in [n for n in tree.nodes if n.name.startswith("face paint: ")]:
            tree.nodes.remove(node)
            gone += 1
    old = obj.data.attributes.get("face_paint")
    if old:
        obj.data.attributes.remove(old)
    if "face_paint" in obj:
        del obj["face_paint"]
    return gone

def find_head(obj, world, a, u):
    """The head of a T-pose: the column above the arms, down to the neck or the shoulders."""
    points = [world @ v.co for v in obj.data.vertices]
    low, top = min(p.z for p in points), max(p.z for p in points)
    tall = top - low
    middle = (min(p[u] for p in points) + max(p[u] for p in points)) / 2  # between the hands
    step = tall / 200
    widths = [0.0] * 70
    column = [p for p in points if abs(p[u] - middle) < 0.2 * tall and p.z > top - 70 * step]
    for p in column:
        i = min(int((top - p.z) / step), 69)
        widths[i] = max(widths[i], abs(p[u] - middle))
    head_w, neck = 0.0, None
    for i in range(70):
        w = widths[i]
        if i * step < 0.07 * tall:
            head_w = max(head_w, w)
            continue
        if w < 0.72 * head_w:
            neck = i
            while neck + 1 < 70 and widths[neck + 1] <= widths[neck] and (neck - i) * step < 0.03 * tall:
                neck += 1
            break
        if w > 1.45 * head_w:
            neck = i
            break
        head_w = max(head_w, w)
    if neck is None:
        neck = int(0.15 * tall / step)
    bottom = top - neck * step
    inside = [p[a] for p in column if p.z >= bottom and abs(p[u] - middle) <= 1.05 * head_w]
    lo, hi = [0.0, 0.0, bottom], [0.0, 0.0, top]
    lo[u], hi[u] = middle - head_w, middle + head_w
    lo[a], hi[a] = min(inside), max(inside)
    return lo, hi


obj = pick_object(PARAMS["object"])
if PARAMS["remove"]:
    print("RESULT " + json.dumps({"object": obj.name, "painted": False, "removed_nodes": unpaint(obj)}))
elif not PARAMS["picture"]:
    raise ValueError("set PARAMS['picture'] to the picture's path")
else:
    unpaint(obj)
    a, sign, right = FACING[PARAMS["facing"]]
    u = 1 - a
    bpy.context.view_layer.update()
    world = obj.matrix_world
    inverse = world.inverted()
    if PARAMS["box"]:
        lo, hi = list(PARAMS["box"]["min"]), list(PARAMS["box"]["max"])
        box_by = "given"
    else:
        lo, hi = find_head(obj, world, a, u)
        box_by = "found"
    tall, wide = hi[2] - lo[2], hi[u] - lo[u]
    middle = (lo[u] + hi[u]) / 2
    front = max(sign * lo[a], sign * hi[a])  # the wall of the box the face looks through
    deep = abs(hi[a] - lo[a])

    # The mesh's head seen from the front, on a grid over the box and a margin: is anything there, and how light is it.
    # Column 0 is the left of the picture. Rows run from the top.
    margin = 0.15
    span_u, span_z = wide * (1 + 2 * margin), tall * (1 + 2 * margin)
    left_edge, top_edge = -right * span_u / 2, hi[2] + margin * tall  # along "right", from the middle; and in height
    aim = [0.0, 0.0, 0.0]
    aim[a] = -sign
    aim_local = (inverse.to_3x3() @ Vector(aim)).normalized()
    image = color_image(obj)
    if image:
        tex_w, tex_h = image.size
        texels = image.pixels[:]
        uvs = obj.data.uv_layers.active.data
        as_srgb = image.colorspace_settings.name == "sRGB"  # how the shader reads it
    polygons, vertices, loops = obj.data.polygons, obj.data.vertices, obj.data.loops
    seen, light, tint = [], [], []
    for r in range(CELLS):
        z = top_edge - (r + 0.5) / CELLS * span_z
        s_row, l_row, t_row = [], [], []
        for c in range(CELLS):
            along = -span_u / 2 + (c + 0.5) / CELLS * span_u  # along the picture's right
            start = [0.0, 0.0, z]
            start[u], start[a] = middle + right * along, sign * (front + deep)
            hit, where, normal, index = obj.ray_cast(inverse @ Vector(start), aim_local)
            there = bool(hit) and sign * (world @ where)[a] >= front - 1.2 * deep
            s_row.append(there)
            if there and image:
                near, gap = None, None
                for corner in polygons[index].loop_indices:
                    away = (vertices[loops[corner].vertex_index].co - where).length
                    if gap is None or away < gap:
                        near, gap = corner, away
                x, y = uvs[near].uv
                at = 4 * (int(y % 1 * tex_h) % tex_h * tex_w + int(x % 1 * tex_w) % tex_w)
                rgb = texels[at:at + 3]
                l_row.append(0.3 * rgb[0] + 0.6 * rgb[1] + 0.1 * rgb[2])
                t_row.append([linear(v) if as_srgb else v for v in rgb])
            else:
                l_row.append(None)
                t_row.append(None)
        seen.append(s_row)
        light.append(l_row)
        tint.append(t_row)
    texels = None
    if sum(1 for row in seen for s in row if s) < 0.1 * CELLS * CELLS:
        raise ValueError("almost nothing inside the box faces %s: check the box and 'facing'" % PARAMS["facing"])

    # The picture: its background color, and where the figure is.
    picture = bpy.data.images.load(PARAMS["picture"], check_existing=True)
    pic_w, pic_h = picture.size
    pixels = picture.pixels[:]
    ground = [sum(pixels[4 * (y * pic_w + x) + k] for x in range(4) for y in range(pic_h - 4, pic_h)) / 16 for k in range(3)]

    def figure(x, y):
        """Is this pixel the figure (not background)? Off the picture is background."""
        if not (0 <= x < pic_w and 0 <= y < pic_h):
            return False
        at = 4 * (int(y) * pic_w + int(x))
        return abs(pixels[at] - ground[0]) + abs(pixels[at + 1] - ground[1]) + abs(pixels[at + 2] - ground[2]) > 0.12

    def lightness(x, y):
        at = 4 * (clamp(int(y), 0, pic_h - 1) * pic_w + clamp(int(x), 0, pic_w - 1))
        return 0.3 * pixels[at] + 0.6 * pixels[at + 1] + 0.1 * pixels[at + 2]

    panel = PARAMS["panel"]
    if panel == "front":
        # The first view from the left: columns with figure in them, up to the first clear gap.
        step = max(1, pic_h // 200)
        busy = [any(figure(x, y) for y in range(0, pic_h, step)) for x in range(0, pic_w, step)]
        first = busy.index(True) if True in busy else 0
        last = first
        while last + 1 < len(busy) and (busy[last + 1] or any(busy[last + 1:last + 1 + max(2, len(busy) // 60)])):
            last += 1
        last = min(last, first + len(busy) // 2)
        panel = [max(0.0, (first - 2) * step / pic_w), 0.0, min(1.0, (last + 3) * step / pic_w), 1.0]
    x0, y0, x1, y1 = [0, 0, pic_w, pic_h] if not panel else [int(panel[0] * pic_w), int(panel[1] * pic_h), int(panel[2] * pic_w), int(panel[3] * pic_h)]
    # Rows of the figure from its top down: the left and right end of each.
    step = max(1, (y1 - y0) // 400)
    ends = []
    for y in range(y1 - 1, y0, -step):
        xs = [x for x in range(x0, x1, step) if figure(x, y)]
        if xs or ends:
            ends.append((y, xs[0], xs[-1]) if xs else (y, None, None))
    if len(ends) < 10:
        raise ValueError("the picture has no figure on a plain background%s" % (" in that panel" if panel else ""))
    top_px = ends[0][0]
    figure_px = ends[0][0] - min(e[0] for e in ends if e[1] is not None)

    # The mesh's outline, row by row from the top of what it shows: half-widths and middles, in meters.
    rows_seen = [r for r in range(CELLS) if any(seen[r])]
    mesh_top = top_edge - rows_seen[0] / CELLS * span_z
    outline = []
    for r in rows_seen:
        cols = [c for c in range(CELLS) if seen[r][c]]
        outline.append((mesh_top - (top_edge - (r + 0.5) / CELLS * span_z), (cols[-1] - cols[0] + 1) / CELLS * span_u))
    outline = [o for o in outline if o[0] <= 0.8 * tall]  # the head, not the shoulders

    def width_at(px_down):
        """How wide the figure is, in pixels, this far below its top."""
        i = clamp(int(px_down / step), 0, len(ends) - 1)
        return (ends[i][2] - ends[i][1] + step) if ends[i][1] is not None else 0

    # 1. Scale by outline: the pixels per meter at which the picture's head is as wide as the mesh's, row by row.
    if panel:
        guesses = [figure_px / tall * (0.35 + 0.01 * i) for i in range(90)]  # a head and shoulders fill the panel
    else:
        bound = [world @ Vector(corner) for corner in obj.bound_box]
        whole = max(p.z for p in bound) - min(p.z for p in bound)
        guesses = [figure_px / whole * (0.9 + 0.01 * i) for i in range(21)]  # the whole figure is in the picture
    per_m, miss = None, None
    for guess in guesses:
        off = sum(abs(width_at(down * guess) / guess - w) for down, w in outline) / len(outline)
        if miss is None or off < miss:
            per_m, miss = guess, off
    # The head's middle column in the picture, at that scale.
    mids = [(ends[i][1] + ends[i][2]) / 2 for i in range(min(len(ends), max(2, int(0.6 * tall * per_m / step)))) if ends[i][1] is not None]
    mid_px = sorted(mids)[len(mids) // 2]
    # (the mesh's own middle, the same way)
    mesh_mids = sorted((min(c for c in range(CELLS) if seen[r][c]) + max(c for c in range(CELLS) if seen[r][c]) + 1) / 2 for r in rows_seen
                       if mesh_top - (top_edge - (r + 0.5) / CELLS * span_z) <= 0.6 * tall)
    mesh_mid = -span_u / 2 + mesh_mids[len(mesh_mids) // 2] / CELLS * span_u

    # 2. Slide and scale until light and dark agree: the picture against the mesh's own texture.
    cells = [(r, c) for r in range(CELLS) for c in range(CELLS) if seen[r][c] and light[r][c] is not None]

    def agree(scale, slide, drop):
        """How well the picture, placed so, matches the mesh: its light and dark (-1 to 1) and its outline (0 to 1)."""
        n = sa = sb = saa = sbb = sab = 0.0
        both = either = 0
        for r in range(0, CELLS, 1):
            z_down = mesh_top - (top_edge - (r + 0.5) / CELLS * span_z)
            y = top_px - (z_down * scale + drop)
            for c in range(0, CELLS, 1):
                x = mid_px + ((-span_u / 2 + (c + 0.5) / CELLS * span_u) - mesh_mid) * scale + slide
                fig = figure(x, y)
                if seen[r][c] or fig:
                    either += 1
                    if seen[r][c] and fig:
                        both += 1
                        m = light[r][c]
                        if m is not None:
                            p = lightness(x, y)
                            n += 1
                            sa += m
                            sb += p
                            saa += m * m
                            sbb += p * p
                            sab += m * p
        shared = both / max(either, 1)
        if n < 20:
            return -1.0, shared
        var = (saa - sa * sa / n) * (sbb - sb * sb / n)
        return ((sab - sa * sb / n) / var ** 0.5 if var > 1e-9 else 0.0), shared

    def score(scale, slide, drop):
        alike, outline_shared = agree(scale, slide, drop)
        return (alike + 0.5 * outline_shared) if image else outline_shared

    start = (per_m, 0.0, 0.0)
    best, best_score = start, score(per_m, 0.0, 0.0)
    unit = tall * per_m  # the head's height in pixels
    for reach_s, reach_d, count in ((0.03, 0.02, 3), (0.01, 0.007, 2), (0.004, 0.003, 2)):
        base = best
        for i in range(-count, count + 1):
            for j in range(-count, count + 1):
                for k in range(-count, count + 1):
                    trial = (base[0] * (1 + reach_s * i), base[1] + reach_d * unit * j, base[2] + reach_d * unit * k)
                    got = score(trial[0], trial[1], trial[2])
                    if got > best_score:
                        best, best_score = trial, got
    scale, slide, drop = best
    alike, outline_shared = agree(scale, slide, drop)
    fit = (alike if image else outline_shared)

    def spot(p):
        """Where a world point lands in the picture, in pixels."""
        along = (p[u] - middle) * right
        return mid_px + (along - mesh_mid) * scale + slide, top_px - ((mesh_top - p.z) * scale + drop)

    result = {"object": obj.name, "picture": PARAMS["picture"], "panel": panel, "box": {"min": [round(v, 3) for v in lo], "max": [round(v, 3) for v in hi]},
              "box_by": box_by, "fit": round(fit, 3), "outline_shared": round(outline_shared, 3),
              "pixels_per_meter": round(scale, 1), "head_px": round(tall * scale), "moved_px": [round(slide, 1), round(drop, 1)],
              "scale_by_outline": round(per_m, 1)}
    if fit < PARAMS["least"]:
        result.update(painted=False, why="the picture and the mesh agree only %.2f here (least %.2f): nothing painted" % (fit, PARAMS["least"]))
        print("RESULT " + json.dumps(result))
    else:
        # The picture's colors run a little lighter or darker than the mesh's: match them where both are skin and cloth.
        sums_m, sums_p, n = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 0
        for r, c in cells:
            z_down = mesh_top - (top_edge - (r + 0.5) / CELLS * span_z)
            x = mid_px + ((-span_u / 2 + (c + 0.5) / CELLS * span_u) - mesh_mid) * scale + slide
            y = top_px - (z_down * scale + drop)
            if figure(x, y):
                at = 4 * (int(y) * pic_w + int(x))
                for k in range(3):
                    sums_m[k] += tint[r][c][k]
                    sums_p[k] += linear(pixels[at + k])
                n += 1
        gain = [clamp(sums_m[k] / sums_p[k], 0.4, 1.6) if n and sums_p[k] > 1e-6 else 1.0 for k in range(3)]

        # Each point's share of paint: facing front, nothing in front of it, on the figure in the picture,
        # fading out toward the neck and the back of the head.
        me = obj.data
        weights = [0.0] * len(me.vertices)
        turn = world.to_3x3()
        toward = -Vector(aim)
        edge_px = max(2.0, 0.012 * tall * scale)
        near = set()
        for v in me.vertices:
            p = world @ v.co
            if not (lo[2] - 0.02 * tall <= p.z <= hi[2] + 0.05 * tall and abs(p[u] - middle) <= 0.6 * wide):
                continue
            # The front half of the head and a little more, never the back: through a hole in the mesh (TRELLIS
            # leaves some at the eyes) the picture would otherwise land on the inside of the back of the skull.
            if sign * p[a] < front - 0.6 * deep:
                continue
            # TRELLIS winds some faces backwards (lips, eyelids), so a point that looks away but has nothing in front of it counts too.
            facing = abs((turn @ v.normal).normalized().dot(toward))
            if facing <= 0.15:
                continue
            # Hidden: something stands well in front of it. A skin a few millimeters in front is the same surface twice
            # (TRELLIS builds lips, lids and teeth in layers), and both layers take the paint.
            hit, where, _, _ = obj.ray_cast(inverse @ (p + toward * 0.002 * tall), -aim_local)
            if hit and (world @ where - p).length > 0.03 * tall:
                continue
            x, y = spot(p)
            if not (figure(x, y) and figure(x - edge_px, y) and figure(x + edge_px, y) and figure(x, y + edge_px)):
                continue
            w = ramp(facing, 0.15, 0.45) * ramp(p.z, lo[2] - 0.08 * tall, lo[2] + 0.02 * tall)
            if w > 0.0:
                weights[v.index] = w
                near.add(v.index)
        # Lips, lids and hair are bumpy, and a bumpy patch's points face every which way: fill the gaps
        # from the points around them, then soften the edge of the paint.
        links = {}
        for edge in me.edges:
            i, j = edge.vertices
            if i in near or j in near:
                links.setdefault(i, []).append(j)
                links.setdefault(j, []).append(i)
        for fill in (True, False):
            spread = {}
            for i, others in links.items():
                around = (weights[i] + sum(weights[j] for j in others)) / (len(others) + 1)
                spread[i] = max(weights[i], around) if fill and i in near else around
            for i, w in spread.items():
                weights[i] = w
        painted = sum(1 for i in links if weights[i] > 0.5)
        layer = me.attributes.new("face_paint", "FLOAT", "POINT")
        layer.data.foreach_set("value", weights)

        # The projector, as shader nodes: where a point is -> where that is in the picture -> its color, mixed over the mesh's own.
        ku, kv = scale / pic_w * right, scale / pic_h
        u0 = (mid_px - mesh_mid * scale + slide) / pic_w - middle * ku
        v0 = (top_px - drop - mesh_top * scale) / pic_h
        done = 0
        for mat in me.materials:
            shader = principled(mat)
            if not shader:
                continue
            tree = mat.node_tree
            place = tree.nodes.new("ShaderNodeNewGeometry")
            place.name = "face paint: where"
            split = tree.nodes.new("ShaderNodeSeparateXYZ")
            split.name = "face paint: split"
            tree.links.new(place.outputs["Position"], split.inputs[0])
            across = tree.nodes.new("ShaderNodeMath")
            across.name, across.operation = "face paint: across", "MULTIPLY_ADD"
            across.inputs[1].default_value, across.inputs[2].default_value = ku, u0
            tree.links.new(split.outputs[u], across.inputs[0])
            up = tree.nodes.new("ShaderNodeMath")
            up.name, up.operation = "face paint: up", "MULTIPLY_ADD"
            up.inputs[1].default_value, up.inputs[2].default_value = kv, v0
            tree.links.new(split.outputs[2], up.inputs[0])
            join = tree.nodes.new("ShaderNodeCombineXYZ")
            join.name = "face paint: join"
            tree.links.new(across.outputs[0], join.inputs[0])
            tree.links.new(up.outputs[0], join.inputs[1])
            slide_node = tree.nodes.new("ShaderNodeTexImage")
            slide_node.name, slide_node.image = "face paint: picture", picture
            slide_node.extension, slide_node.interpolation = "CLIP", "Cubic"
            tree.links.new(join.outputs[0], slide_node.inputs["Vector"])
            tone = tree.nodes.new("ShaderNodeMix")
            tone.name, tone.data_type, tone.blend_type = "face paint: tone", "RGBA", "MULTIPLY"
            tone.inputs[0].default_value = 1.0
            tone.inputs[7].default_value = (gain[0], gain[1], gain[2], 1.0)
            tree.links.new(slide_node.outputs["Color"], tone.inputs[6])
            share = tree.nodes.new("ShaderNodeAttribute")
            share.name, share.attribute_name = "face paint: share", "face_paint"
            much = tree.nodes.new("ShaderNodeMath")
            much.name, much.operation = "face paint: strength", "MULTIPLY"
            much.inputs[1].default_value = PARAMS["strength"]
            tree.links.new(share.outputs["Fac"], much.inputs[0])
            mixer = tree.nodes.new("ShaderNodeMix")
            mixer.name, mixer.data_type = "face paint: mix", "RGBA"
            tree.links.new(much.outputs[0], mixer.inputs[0])
            base = shader.inputs["Base Color"]
            if base.is_linked:
                tree.links.new(base.links[0].from_socket, mixer.inputs[6])
            else:
                mixer.inputs[6].default_value = base.default_value
            tree.links.new(tone.outputs[2], mixer.inputs[7])
            tree.links.new(mixer.outputs[2], base)
            done += 1
        obj["face_paint"] = json.dumps({"picture": PARAMS["picture"], "fit": round(fit, 3)})
        result.update(painted=True, points_painted=painted, materials=done, tone=[round(g, 2) for g in gain],
                      next="bake it to keep it: bake.py \"materials\" for this mesh, or \"onto\" for a lighter one")
        print("RESULT " + json.dumps(result))
