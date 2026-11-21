"""Stands the world's toons up: each one in its pose, as a small still .glb, in a background Blender.

    Blender -b --factory-startup -P scripts/world/pose_toons.py -- <runs folder> [toon ...]

For every toon in world.json (or only the ones named): its low-poly, rigged
file (runs/<run>/profiles/lowpoly-walk.glb) is brought in, put in the pose
world.json gives it (a name from motion/comic_poses.json), set down on the
floor, and written with the pose baked in and the skeleton left behind:

    world/toons/<toon>.glb    its meshes, still, standing at 0, 0, 0, facing the way it was built

The world view places these on their marks. A toon in the world does not
move, so it needs no bones: this is the lightest file that still looks like
them. The run is only read. Never touches an open Blender.
"""

import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "comic"))
import stage  # noqa: E402
import world as world_file  # noqa: E402


def stand_still(toon, runs, poses):
    run = world_file.newest_run(runs, toon["run"])
    stage.fresh_scene()
    character = stage.load_character(os.path.join(run, "profiles", "lowpoly-walk.glb"))
    stage.strike(character, poses[toon["pose"]])
    stage.stand_at(character, spot=(0.0, 0.0), facing=0.0, floor=0.0)
    graph = bpy.context.evaluated_depsgraph_get()
    kept = []
    for o in character["meshes"]:
        if o.hide_render or o.get("forge") == "prop":
            continue
        made = o.evaluated_get(graph)
        mesh = bpy.data.meshes.new_from_object(made, preserve_all_data_layers=True, depsgraph=graph)
        still = bpy.data.objects.new(o.name + " still", mesh)
        still.matrix_world = made.matrix_world.copy()
        kept.append(still)
    for o in [o for o in bpy.data.objects if o not in kept]:
        bpy.data.objects.remove(o, do_unlink=True)
    # The pieces stay apart (joining them loses the colours painted on all but one), each with the pose baked in.
    options = {"filepath": os.path.join(REPO, toon["glb"]), "export_format": "GLB", "use_active_scene": True, "export_apply": True, "export_animations": False,
               "export_skins": False, "export_extras": False}
    for o in kept:
        bpy.context.scene.collection.objects.link(o)
        if o.data.color_attributes:
            o.data.color_attributes.active_color = o.data.color_attributes[0]
            o.data.color_attributes.render_color_index = 0
    if any(o.data.color_attributes for o in kept) and "export_vertex_color" in bpy.ops.export_scene.gltf.get_rna_type().properties.keys():
        options["export_vertex_color"] = "ACTIVE"  # a block-out's colours are painted on its corners: say so, or they are left behind
    out = options["filepath"]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.ops.export_scene.gltf(**options)
    bpy.context.view_layer.update()
    tall = max((o.matrix_world @ v.co).z for o in kept for v in o.data.vertices)
    triangles = sum(len(p.vertices) - 2 for o in kept for p in o.data.polygons)
    return {"toon": toon["toon"], "pose": toon["pose"], "triangles": triangles, "tall_m": round(tall, 2), "bytes": os.path.getsize(out)}


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    runs, only = os.path.abspath(args[0]), args[1:]
    poses = stage.load_poses()
    for toon in world_file.load()["toons"]:
        if only and toon["toon"] not in only:
            continue
        made = stand_still(toon, runs, poses)
        print("TOON %(toon)s: %(pose)s, %(triangles)d triangles, %(tall_m)s m tall, %(bytes)d bytes" % made)


main()
