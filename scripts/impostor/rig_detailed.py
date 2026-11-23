"""Gives a character's detailed mesh the skeleton of one of its rigged versions, so it can be baked as cards.

    Blender -b --factory-startup -P scripts/impostor/rig_detailed.py -- <run> [--from painted] [--mesh final.glb] [--name detailed]

A card costs the same to draw however fine the model it was pictured from, so the cards may as well be
pictured from the best model there is. That model (final.glb: the raw mesh, some 290,000 triangles, stood
up and sized, with its own texture) has no skeleton. This puts the skeleton of <from>-walk.glb on it:

  1. both are brought in as they rest (the rigged version's walk file, and the detailed mesh);
  2. how far apart the two surfaces are is measured, from every point of the detailed mesh to the nearest
     place on the rigged one (they are the same character built two ways, so centimetres are expected);
  3. every point of the detailed mesh takes the bone weights of that nearest place (the weights of the
     corners of the face it lies on, the nearer corners counting more);
  4. the detailed mesh, the skeleton and the walk are written as profiles/<name>-walk.glb.

It is only ever pictured, never played: nothing else reads the file. Prints RIG lines and RESULT {json}.
Never touches an open Blender.
"""

import json
import os
import sys
import time

import bpy
import numpy as np
from mathutils.bvhtree import BVHTree


def bring(path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.context.scene.objects if o not in before]


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    run = os.path.abspath(args[0])
    rigged, mesh, name = flag("--from", "painted"), flag("--mesh", "final.glb"), flag("--name", "detailed")
    began = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = 30
    old = bring(os.path.join(run, "profiles", rigged + "-walk.glb"))
    rig = next(o for o in old if o.type == "ARMATURE")
    donors = [o for o in old if o.type == "MESH" and o.find_armature() and not o.get("under")]
    fine = [o for o in bring(os.path.join(run, mesh)) if o.type == "MESH"]

    # the rigged version's surface, and each corner's weights by bone name
    points, faces, weights = [], [], []
    for obj in donors:
        start = len(points)
        names = [g.name for g in obj.vertex_groups]
        for v in obj.data.vertices:
            points.append(obj.matrix_world @ v.co)
            weights.append({names[g.group]: g.weight for g in v.groups if g.weight > 0})
        faces += [tuple(start + i for i in p.vertices) for p in obj.data.polygons]
    tree = BVHTree.FromPolygons(points, faces)

    bones = [b.name for b in rig.data.bones]
    apart = []
    for obj in fine:
        groups = {b: obj.vertex_groups.new(name=b) for b in bones}
        for v in obj.data.vertices:
            at = obj.matrix_world @ v.co
            spot, _, face, far = tree.find_nearest(at)
            apart.append(far)
            total = {}
            for corner in faces[face]:
                share = 1.0 / max((points[corner] - spot).length, 1e-5)
                for bone, w in weights[corner].items():
                    total[bone] = total.get(bone, 0.0) + w * share
            best = sorted(total.items(), key=lambda pair: -pair[1])[:4]
            whole = sum(w for _, w in best) or 1.0
            for bone, w in best:
                groups[bone].add([v.index], w / whole, "REPLACE")
        world = obj.matrix_world.copy()
        obj.parent = rig
        obj.matrix_world = world
        obj.modifiers.new("Armature", "ARMATURE").object = rig
        obj.name = "body"
    apart = np.array(apart)
    said = {"points": int(len(apart)), "triangles": sum(len(p.vertices) - 2 for o in fine for p in o.data.polygons),
            "apart_cm": {"typical": round(float(np.median(apart)) * 100, 2), "mean": round(float(apart.mean()) * 100, 2),
                         "p95": round(float(np.percentile(apart, 95)) * 100, 2), "worst": round(float(apart.max()) * 100, 2)}}
    print("RIG the two surfaces are %(typical)s cm apart at a typical point, %(p95)s cm at the 95th in a hundred, %(worst)s cm at worst" % said["apart_cm"], flush=True)

    for obj in old:
        if obj.type != "ARMATURE":
            bpy.data.objects.remove(obj)
    for obj in list(bpy.context.scene.objects):
        if obj.type == "MESH" and obj not in fine:
            bpy.data.objects.remove(obj)  # a bone's display shape
    out = os.path.join(run, "profiles", name + "-walk.glb")
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_animations=True, export_yup=True)
    said.update({"glb": out, "bytes": os.path.getsize(out), "seconds": round(time.time() - began, 1), "skeleton_from": rigged + "-walk.glb", "mesh": mesh})
    with open(os.path.join(run, "profiles", name + "-walk.json"), "w") as f:
        json.dump({"rig_detailed": said}, f, indent=1)
    print("RESULT " + json.dumps(said))


main()
