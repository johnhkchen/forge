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
    "texture_size": 1024,    # 1024 for web/game, 2048 for close-ups
    "metallic": True,        # bake a metallic map (skip for objects with no metal)
}

import bpy
import json
import math



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
    exactly that value. Returns what to undo."""
    bsdf = principled(mat)
    out = output_node(mat)
    if bsdf is None or out is None:
        return None
    tree = mat.node_tree
    emit = tree.nodes.new("ShaderNodeEmission")
    emit.inputs["Strength"].default_value = 1.0
    sock = bsdf.inputs[channel]
    if sock.is_linked:
        tree.links.new(sock.links[0].from_socket, emit.inputs["Color"])
    else:
        v = sock.default_value
        emit.inputs["Color"].default_value = (v[0], v[1], v[2], 1.0) if channel == "Base Color" else (v, v, v, 1.0)
    old = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].is_linked else None
    tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return (mat, emit, out, old)


def undo_route(undo):
    if undo is None:
        return
    mat, emit, out, old = undo
    if old is not None:
        mat.node_tree.links.new(old, out.inputs["Surface"])
    mat.node_tree.nodes.remove(emit)


def new_image(name, size, data):
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=False)
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
        if selected_to_active:
            settings.update(use_selected_to_active=True, cage_extrusion=reach, max_ray_distance=reach * 2)
        if kind == "NORMAL":
            settings.update(normal_space="TANGENT")
        bpy.ops.object.bake(**settings)
    finally:
        drop(temp)
    img.pack()


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
    tree.links.new(tex(maps["roughness"], 0).outputs["Color"], bsdf.inputs["Roughness"])
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
saved = (scene.render.engine, scene.cycles.samples)
scene.render.engine = "CYCLES"
scene.cycles.samples = 1  # an emission bake needs a single sample
size = PARAMS["texture_size"]
reach = size_of(obj) * 0.01

if mode == "onto":
    target = bpy.data.objects.get(PARAMS["target"] or obj.name + " (quads)") or bpy.data.objects.get(obj.name + " (light)")
    if target is None or target.type != "MESH":
        raise ValueError("no mesh to bake onto: %r" % (PARAMS["target"] or obj.name + " (quads)"))
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
base = target.name

channels = [("color", "Base Color", False), ("roughness", "Roughness", True)]
if PARAMS["metallic"]:
    channels.append(("metallic", "Metallic", True))

maps = {}
try:
    for key, socket, data in channels:
        img = new_image("%s %s" % (base, key), size, data)
        undo = [route_to_emission(m, socket) for m in source_mats]
        try:
            bake_pass("EMIT", source_mats, target_mats, img, selected_to_active, reach)
        finally:
            for u in undo:
                undo_route(u)
        maps[key] = img
    if selected_to_active:
        scene.cycles.samples = 4
        img = new_image("%s normal" % base, size, True)
        bake_pass("NORMAL", source_mats, target_mats, img, True, reach)
        maps["normal"] = img
finally:
    scene.render.engine, scene.cycles.samples = saved

baked = final_material(base + " baked", maps)
target.data.materials.clear()
target.data.materials.append(baked)
done = ["baked %s at %d px" % (", ".join(sorted(maps)), size)]
if mode == "onto":
    obj.hide_set(True)
    obj.hide_render = True
    done.append("baked onto %r (%d faces); hid the full mesh" % (target.name, len(target.data.polygons)))
else:
    done.append("replaced the material with %r, which glTF can carry" % baked.name)

print("RESULT " + json.dumps({"object": target.name, "maps": sorted(maps), "done": done}))
