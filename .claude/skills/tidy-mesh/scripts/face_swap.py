# Put a drawn face on the front of a rigged character's head, for a comic
# panel: the same body and pose, a different expression. Run toon.py first;
# this fills in the "drawn" part of its comic paint.
#
# How: like a slide projector riding on the head bone. A picture (a face
# drawn flat, from the front, with a see-through background) is aimed at the
# front of the head, and every point of the head that is in its beam takes
# the picture's color where the picture is not see-through. It reaches only
# as deep as "reach" of the head (so not the back of the hood), and only
# points that follow the head bone (so not a hand held up in front of it).
# The projector is an empty parented to the head bone, so the face stays on
# when the head turns, nods or the whole character moves.
#
# "plane" says where the picture sits on the head as it was built (the
# T-pose, facing -y): the middle of the picture [x, z], its size [wide,
# tall], where the front of the face is (y) and how deep the head is, all in
# metres in the character's own space. scripts/comic/face_fit.py measures it
# when it cuts a character's expression sheet (comics/cast/<who>/face.json).
#
# Swapping the expression is running this again with another "image": the
# nodes are reused. "off": True takes the drawn face away.
#
# Send this whole file through the blender MCP `execute_blender_code` tool
# after editing PARAMS. Prints RESULT {json}. Instant. Safe-mode compatible.

PARAMS = {
    "rig": None,        # the character's skeleton, by name; None = the only one in the scene
    "image": None,      # absolute path of the drawn face (.png with alpha)
    "plane": {"center": [0.0, 1.6], "size": [0.3, 0.3], "front": -0.12, "depth": 0.25},
    "reach": 0.62,      # how far back through the head the picture goes: 0 = the very front, 1 = all the way
    "bone": "head",
    "off": False,       # True = take the drawn face off
}

import bpy
import json
from mathutils import Matrix

PAINT = "comic paint"
FACE = "comic face"
MARK = "comic_head"  # a point attribute: 1 where the mesh follows the head bone


def find_rig(name):
    if name:
        rig = bpy.data.objects.get(name)
        if rig is None or rig.type != "ARMATURE":
            raise ValueError("no skeleton named %r" % name)
        return rig
    rigs = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    if len(rigs) != 1:
        raise ValueError("the scene has %d skeletons: say which with \"rig\"" % len(rigs))
    return rigs[0]


def mark_head(mesh_object, bone):
    """Write the head bone's pull on every point as an attribute the paint can read. Returns how many points it holds."""
    group = mesh_object.vertex_groups.get(bone)
    data = mesh_object.data
    layer = data.attributes.get(MARK) or data.attributes.new(MARK, "FLOAT", "POINT")
    held = 0
    index = group.index if group else -1
    for v in data.vertices:
        pull = 0.0
        for g in v.groups:
            if g.group == index:
                pull = g.weight
        layer.data[v.index].value = pull
        if pull > 0.5:
            held += 1
    return held


def number(tree, operation, a, b=None, clamp=False):
    node = tree.nodes.new("ShaderNodeMath")
    node.operation = operation
    node.use_clamp = clamp
    node.label = FACE
    for i, value in enumerate((a, b)):
        if value is None:
            continue
        if isinstance(value, (int, float)):
            node.inputs[i].default_value = value
        else:
            tree.links.new(value, node.inputs[i])
    return node.outputs[0]


def wire(mat, projector, picture, reach):
    """Add (or reuse) the face nodes in one material and point them at the picture. False if it has no comic paint."""
    tree = mat.node_tree if mat.use_nodes else None
    paint = tree.nodes.get(PAINT) if tree else None
    if paint is None:
        return False
    shot = tree.nodes.get(FACE)
    if shot is None:
        beam = tree.nodes.new("ShaderNodeTexCoord")
        beam.name = FACE + " beam"
        split = tree.nodes.new("ShaderNodeSeparateXYZ")
        split.label = FACE
        tree.links.new(beam.outputs["Object"], split.inputs[0])
        spot = tree.nodes.new("ShaderNodeCombineXYZ")
        spot.label = FACE
        tree.links.new(number(tree, "ADD", split.outputs[0], 0.5), spot.inputs[0])
        tree.links.new(number(tree, "ADD", split.outputs[2], 0.5), spot.inputs[1])
        shot = tree.nodes.new("ShaderNodeTexImage")
        shot.name = shot.label = FACE
        shot.extension = "CLIP"
        tree.links.new(spot.outputs[0], shot.inputs["Vector"])
        # In the beam's own measure the head runs from 0 (the front of the face) to 1 (the back of the head).
        deep = tree.nodes.new("ShaderNodeMapRange")
        deep.name = FACE + " reach"
        deep.interpolation_type = "SMOOTHSTEP"
        deep.inputs["To Min"].default_value, deep.inputs["To Max"].default_value = 1.0, 0.0
        tree.links.new(split.outputs[1], deep.inputs["Value"])
        held = tree.nodes.new("ShaderNodeAttribute")
        held.label = FACE
        held.attribute_type = "GEOMETRY"
        held.attribute_name = MARK
        on_head = number(tree, "GREATER_THAN", held.outputs["Fac"], 0.5)
        amount = number(tree, "MULTIPLY", number(tree, "MULTIPLY", shot.outputs["Alpha"], deep.outputs[0]), on_head, clamp=True)
        tree.links.new(shot.outputs["Color"], paint.inputs["Drawn"])
        tree.links.new(amount, paint.inputs["Drawn Amount"])
    tree.nodes[FACE + " beam"].object = projector
    reach_node = tree.nodes[FACE + " reach"]
    reach_node.inputs["From Min"].default_value = max(0.0, reach - 0.18)
    reach_node.inputs["From Max"].default_value = reach
    shot.image = picture
    return True


def unwire(mat):
    tree = mat.node_tree if mat.use_nodes else None
    if tree is None or tree.nodes.get(FACE) is None:
        return False
    for node in [x for x in tree.nodes if x.name.startswith(FACE) or x.label == FACE]:
        tree.nodes.remove(node)
    paint = tree.nodes.get(PAINT)
    if paint:
        paint.inputs["Drawn Amount"].default_value = 0.0
    return True


rig = find_rig(PARAMS["rig"])
bone_name = PARAMS["bone"]
if bone_name not in rig.pose.bones:
    raise ValueError("%s has no bone %r" % (rig.name, bone_name))
meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.find_armature() == rig and not o.hide_render]
spare = "comic face of " + rig.name

if PARAMS["off"]:
    cleared = 0
    for o in meshes:
        for mat in o.data.materials:
            if mat and unwire(mat):
                cleared += 1
    old = bpy.data.objects.get(spare)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    print("RESULT " + json.dumps({"rig": rig.name, "off": True, "materials": cleared}))
else:
    if not PARAMS["image"]:
        raise ValueError("set PARAMS['image'] to the drawn face (.png)")
    plane = PARAMS["plane"]
    picture = bpy.data.images.load(PARAMS["image"], check_existing=True)
    projector = bpy.data.objects.get(spare)
    if projector is None:
        projector = bpy.data.objects.new(spare, None)
        projector.empty_display_size = 0.5
        bpy.context.scene.collection.objects.link(projector)
        projector.parent = rig
        projector.parent_type = "BONE"
        projector.parent_bone = bone_name
    projector.hide_render = True
    # Where the picture sits on the head as built, carried to where the head bone is now.
    wide, tall = plane["size"]
    built = Matrix.Translation((plane["center"][0], plane["front"], plane["center"][1])) @ Matrix.Diagonal((wide, plane["depth"], tall, 1.0))
    bone = rig.pose.bones[bone_name]
    bpy.context.view_layer.update()
    projector.matrix_world = rig.matrix_world @ bone.matrix @ bone.bone.matrix_local.inverted() @ built
    held = 0
    wired = []
    for o in meshes:
        on_head = mark_head(o, bone_name)
        if not on_head:
            continue
        held += on_head
        for mat in o.data.materials:
            if mat and mat.name not in wired and wire(mat, projector, picture, PARAMS["reach"]):
                wired.append(mat.name)
    if not wired:
        raise ValueError("no material on %s's head has the comic paint: run toon.py first" % rig.name)
    print("RESULT " + json.dumps({"rig": rig.name, "image": PARAMS["image"], "materials": wired, "head_points": held,
                                  "projector": projector.name}))
