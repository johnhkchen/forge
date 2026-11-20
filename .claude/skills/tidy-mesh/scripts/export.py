# Export one object as a GLB, with modifiers applied, and nothing else.
#
# Blender's glTF exporter writes every scene in the file unless told
# otherwise, so "selected only" still drags in meshes from other scenes.
# This exports the open scene only, then reads the file back and counts what
# is in it ("file" in the result; "only_this_object" should be true).
#
# glTF carries plain textures and plain values only. If the material uses
# color ramps, mixes or other nodes, run bake.py (mode "materials") first,
# or the GLB silently loses those changes.
#
# A block-out with gear or sockets (build.py) goes out in pieces, so a game
# can take gear off or swap it: one mesh per group, named "body", "gear: wool
# singlet"..., each gear mesh tagged (glTF extras) with its "gear" name,
# "kind" and "slot", plus one empty per attachment point, "socket:
# hand_right"... The first mesh also carries build.py's recipe
# ("forge_build"), which the mid-poly profile rebuilds from. "file" in the
# result lists what was written; "only_this_object" is still the check.
#
# After drape.py the body is written in more than one mesh: "body" is what
# always shows, and each "body under: wool trousers" holds the faces that gear
# hides completely, tagged "under" with the gear's name (several names when
# more than one piece each hide them). Show such a mesh only while every gear
# it names is off: dressed, the skin under the clothes isn't drawn, so it
# can't show through; undressed, the body is whole. "masks" in the result.
#
# A rigged character (rig.py, then animate.py) goes out whole with "rig": the
# skeleton, every mesh bound to it, the sockets riding on their bones, and
# the baked action as the file's animation ("walk"). Each joint carries its
# "limit_deg" in glTF extras. "file" then also counts the bones and names
# the animations.
#
# Send this whole file through the blender MCP `execute_blender_code` tool
# after editing PARAMS. Prints RESULT {json}. About a second.
# Safe-mode compatible.

PARAMS = {
    "object": None,          # object to export; None = the largest visible mesh
    "path": None,            # absolute path of the .glb to write (required)
    "materials": True,       # False = shape and vertex colors only (a low-poly block-out)
    "image_format": "AUTO",  # "AUTO" (PNG/JPEG as given), "JPEG" or "WEBP" (smallest)
    "draco": False,          # Draco-compress the mesh (web viewers need a Draco decoder)
    "apart": True,           # a block-out with gear or sockets: one mesh per group and the socket empties
    "rig": None,             # the armature's name (True = the scene's first): export it, its meshes, sockets and animation instead of one object
    "check": True,           # read the file back to confirm it holds just this object
}

import bpy
import bmesh
import json


def face_count(obj):
    return len(obj.data.polygons)

def pick_object(name):
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise ValueError("no object named %r" % name)
        return obj
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get()]
    if not meshes:
        raise ValueError("the scene has no visible mesh objects")
    return max(meshes, key=face_count)

def read_back(path):
    """What the written file holds, by importing it into a throwaway scene."""
    window = bpy.context.window
    if not window:
        return None
    kinds = (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.collections, bpy.data.actions, bpy.data.armatures)
    before = [set(kind) for kind in kinds]
    home = window.scene
    scratch = bpy.data.scenes.new("export check")
    window.scene = scratch
    try:
        if "disable_bone_shape" in bpy.ops.import_scene.gltf.get_rna_type().properties.keys():
            bpy.ops.import_scene.gltf(filepath=path, disable_bone_shape=True)
        else:
            bpy.ops.import_scene.gltf(filepath=path)
        found = [o for o in scratch.objects if o.type == "MESH"]
        held = {"meshes": len(found), "names": [o.name for o in found][:24],
                "bones": sum(len(o.data.bones) for o in scratch.objects if o.type == "ARMATURE"),
                "animations": sorted(a.name for a in bpy.data.actions if a not in before[5]),
                "empties": sum(1 for o in scratch.objects if o.type == "EMPTY"),
                "triangles": sum(len(p.vertices) - 2 for o in found for p in o.data.polygons),
                "vertex_colors": any(len(o.data.color_attributes) for o in found)}
    finally:
        window.scene = home
        for kind, old in zip(kinds, before):
            for item in [i for i in kind if i not in old]:
                kind.remove(item)
        bpy.data.scenes.remove(scratch)
    return held


def masks_of(obj):
    """The gear sets drape.py found body faces hidden under ([] first: never hidden), or None."""
    if obj.data.attributes.get("forge_under") is None or not obj.get("forge_masks"):
        return None
    return json.loads(obj["forge_masks"])

def under_name(masks, cut):
    return "body under: " + " + ".join(masks[cut])

def split_groups(obj, scene):
    """A block-out's groups as objects of their own for the length of the export, named and tagged for the file.
    The body comes apart once more where drape.py marked faces as hidden under gear."""
    made = []
    masks = masks_of(obj)
    for index, tag in enumerate(json.loads(obj["forge_groups"])):
        for cut in (range(len(masks)) if masks and tag.get("forge") == "body" else [None]):
            me = obj.data.copy()
            bm = bmesh.new()
            bm.from_mesh(me)
            mark = bm.faces.layers.int.get("forge_group")
            under = bm.faces.layers.int.get("forge_under")
            gone = [f for f in bm.faces if f[mark] != index or (cut is not None and f[under] != cut)]
            if len(gone) == len(bm.faces) and cut:
                bm.free()
                bpy.data.meshes.remove(me)
                continue
            bmesh.ops.delete(bm, geom=gone, context="FACES")
            bm.faces.layers.int.remove(mark)
            bm.to_mesh(me)
            bm.free()
            name = under_name(masks, cut) if cut else tag["name"]
            me.name = name
            part = bpy.data.objects.new(name, me)
            part.matrix_world = obj.matrix_world.copy()
            for key, value in tag.items():
                if key != "name":
                    part[key] = value
            if cut:
                part["under"] = "|".join(masks[cut])
            if masks and tag.get("forge") == "body":
                part["draped"] = 1
            if tag.get("gear") and obj.get("drape"):  # what drape.py took each part of this gear for, so it is read the same way again
                part["drape"] = json.dumps({tag["gear"]: json.loads(obj["drape"]).get(tag["gear"], [])})
            scene.collection.objects.link(part)
            made.append(part)
    if made and "forge_build" in obj:
        made[0]["forge_build"] = obj["forge_build"]
    return made

def mask_parts(obj, scene):
    """A rigged body as one bound mesh per mask, for the length of the export: [] when it has no masks."""
    masks = masks_of(obj)
    made = []
    for cut in range(len(masks or [])):
        part = obj.copy()
        part.data = obj.data.copy()
        bm = bmesh.new()
        bm.from_mesh(part.data)
        under = bm.faces.layers.int.get("forge_under")
        gone = [f for f in bm.faces if f[under] != cut]
        if len(gone) == len(bm.faces) and cut:
            bm.free()
            spare = part.data
            bpy.data.objects.remove(part)
            bpy.data.meshes.remove(spare)
            continue
        bmesh.ops.delete(bm, geom=gone, context="FACES")
        bm.to_mesh(part.data)
        bm.free()
        part.name = part.data.name = under_name(masks, cut) if cut else "body"
        if cut:
            part["under"] = "|".join(masks[cut])
        scene.collection.objects.link(part)
        made.append(part)
    return made


if not PARAMS["path"]:
    raise ValueError("set PARAMS['path'] to where the .glb should go")
scene = bpy.context.scene
rig = None
if PARAMS["rig"]:
    rigs = [o for o in scene.objects if o.type == "ARMATURE" and (PARAMS["rig"] is True or o.name == PARAMS["rig"])]
    if not rigs:
        raise ValueError("no armature %s in the open scene: run rig.py first" % ("" if PARAMS["rig"] is True else repr(PARAMS["rig"])))
    rig = rigs[0]
    bound = [o for o in scene.objects if o.type == "MESH" and o.find_armature() == rig]
    if not bound:
        raise ValueError("no mesh is bound to %r" % rig.name)
    PARAMS["object"] = sorted(bound, key=face_count)[-1].name
obj = pick_object(PARAMS["object"])
if obj.name not in scene.objects:
    raise ValueError("%r is not in the open scene %r; switch to its scene first "
                     "(bpy.context.window.scene = ...)" % (obj.name, scene.name))
sockets = [o for o in scene.objects if o.get("socket_of") == obj.name]
groups = json.loads(obj.get("forge_groups", "[]")) if obj.type == "MESH" else []
parts = split_groups(obj, scene) if PARAMS["apart"] and groups and (len(groups) > 1 or sockets) and not rig else []
for o in bpy.context.selected_objects:
    o.select_set(False)
whole = []
if rig:
    sockets = [o for o in scene.objects if o.type == "EMPTY" and o.parent == rig and o.get("forge") == "socket"]
    apart = {o.name: mask_parts(o, scene) for o in bound if o.get("forge") == "body"}
    parts = [part for made in apart.values() for part in made]
    written = [o for o in bound if not apart.get(o.name)] + parts
    whole = [rig] + written + sockets
    names = {o: o.name for o in bound if apart.get(o.name)}
    for o in names:  # the whole body steps aside for its parts, name and all
        o.name = "whole " + names[o]
    for part in parts:
        part.name = part.name.split(".")[0]
for o in whole or ((parts + sockets) if parts else [obj]):
    o.hide_set(False)
    o.select_set(True)
masked = [o["under"].split("|") for o in parts if o.get("under")]  # the body meshes that hide with gear, by the gear that hides them
bpy.context.view_layer.objects.active = rig or (parts[0] if parts else obj)
options = {
    "filepath": PARAMS["path"],
    "export_format": "GLB",
    "use_selection": True,
    "use_active_scene": True,  # without this, every scene in the file is written
    "export_apply": True,
    "export_draco_mesh_compression_enable": PARAMS["draco"],
    "export_extras": bool(groups) or bool(rig),  # the tags and the recipe travel as custom properties
}
if rig:
    options.update({"export_animations": True, "export_skins": True, "export_animation_mode": "ACTIONS",
                    "export_force_sampling": True, "export_optimize_animation_size": False, "export_anim_single_armature": True})
if PARAMS["materials"]:
    options["export_image_format"] = PARAMS["image_format"]
else:
    options["export_materials"] = "NONE"
    if "export_vertex_color" in bpy.ops.export_scene.gltf.get_rna_type().properties.keys():
        options["export_vertex_color"] = "ACTIVE"
stowed = {}
if rig:  # the motions a source left on the rig are working data, far too long for the file
    for key in [k for k in rig.keys() if k.startswith("forge_motion")]:
        stowed[key] = rig[key]
        del rig[key]
try:
    bpy.ops.export_scene.gltf(**options)
finally:
    for key, value in stowed.items():
        rig[key] = value
    for o in parts:
        spare = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.meshes.remove(spare)
    if rig:
        for o in names:
            o.name = names[o]
    for o in sockets + [obj]:
        o.select_set(False)

deps = bpy.context.evaluated_depsgraph_get()
triangles = 0
for o in (bound if rig else [obj]):
    shown = o.evaluated_get(deps)
    triangles += sum(len(p.vertices) - 2 for p in shown.to_mesh().polygons)
    shown.to_mesh_clear()
result = {
    "object": obj.name,
    "path": PARAMS["path"],
    "faces": sum(len(o.data.polygons) for o in bound) if rig else len(obj.data.polygons),
    "triangles": triangles,
}
if PARAMS["check"]:
    held = read_back(PARAMS["path"])
    if held:
        result["file"] = held
        result["only_this_object"] = (held["meshes"] == (len(written) if rig else max(len(parts), 1)) and held["triangles"] == triangles
                                      and held["empties"] == (len(sockets) if parts or rig else 0)
                                      and held["bones"] == (len(rig.data.bones) if rig else 0))
if rig:
    result["rig"] = {"name": rig.name, "bones": len(rig.data.bones), "meshes": [o.name for o in bound], "body_in_parts": len(parts), "sockets": [o["socket"] for o in sockets],
                     "animation": rig.animation_data.action.name if rig.animation_data and rig.animation_data.action else None}
if parts and not rig:
    result["groups"] = [g["name"] for g in groups]
    result["sockets"] = [o["socket"] for o in sockets]
if masked:
    result["masks"] = masked
print("RESULT " + json.dumps(result))
