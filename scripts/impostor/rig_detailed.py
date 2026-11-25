"""Gives a character's detailed mesh the skeleton of one of its rigged versions, so it can be baked as cards.

    Blender -b --factory-startup -P scripts/impostor/rig_detailed.py -- <run> [--from painted] [--mesh final.glb|dressed] [--name detailed]

A card costs the same to draw however fine the model it was pictured from, so the cards may as well be
pictured from the best model there is. That model (final.glb: the raw mesh, some 290,000 triangles, stood
up and sized, with its own texture) has no skeleton. This puts the skeleton of <from>-walk.glb on it:

  1. both are brought in as they rest (the rigged version's walk file, and the detailed mesh);
  2. how far apart the two surfaces are is measured, from every point of the detailed mesh to the nearest
     place on the rigged one (they are the same character built two ways, so centimetres are expected);
  3. every point of the detailed mesh takes the bone weights of that nearest place (the weights of the
     corners of the face it lies on, the nearer corners counting more);
  4. the detailed mesh, the skeleton and the walk are written as profiles/<name>-walk.glb.

A body under the clothes (README: "A real body under the clothes"). A character whose clothes hide its body (a
long skirt) has a base body made for real (base/final.glb) and each hiding garment cut out of the clothed mesh
(garments/<gear>.glb). final.glb has the skirt and a guess under it; so when both are there the detailed model is
the two together, "dressed" (--mesh final.glb asks for the old one). The legs under a skirt are then legs, for
the cards to show when the skirt swings up, and the skirt is a mesh of its own, "gear: <its name>", for the cards
to treat as the dress it is (bake_impostor.py: chains_of). Weights go kind to kind: a garment's points take the
weights of the same garment in the rigged version (its swing chains among them), the body's take the body's,
the skin each garment hides included ("body under: ..."), never the garment's.

It is only ever pictured, never played: nothing else reads the file. Prints RIG lines and RESULT {json}.
Never touches an open Blender.
"""

import glob
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


def gear_of(obj):
    """The garment a rigged version's mesh is ("gear: ruffled skirt" is the ruffled skirt), or None for the body."""
    return obj.get("gear") or (obj.name[len("gear: "):] if obj.name.startswith("gear: ") else None)


def surface(objects):
    """(a tree of the objects' faces, every corner's place, every face's corners, every corner's weights by bone)."""
    points, faces, weights = [], [], []
    for obj in objects:
        start = len(points)
        names = [g.name for g in obj.vertex_groups]
        for v in obj.data.vertices:
            points.append(obj.matrix_world @ v.co)
            weights.append({names[g.group]: g.weight for g in v.groups if g.weight > 0})
        faces += [tuple(start + i for i in p.vertices) for p in obj.data.polygons]
    return BVHTree.FromPolygons(points, faces), points, faces, weights


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default
    run = os.path.abspath(args[0])
    rigged, name = flag("--from", "painted"), flag("--name", "detailed")
    worn = sorted(glob.glob(os.path.join(run, "garments", "*.glb")))
    mesh = flag("--mesh", "dressed" if worn and os.path.isfile(os.path.join(run, "base", "final.glb")) else "final.glb")
    began = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = 30
    old = bring(os.path.join(run, "profiles", rigged + "-walk.glb"))
    rig = next(o for o in old if o.type == "ARMATURE")
    rigged_meshes = [o for o in old if o.type == "MESH" and o.find_armature()]
    if mesh == "dressed":
        # the base body, and each garment put back on it as a mesh of its own (follow.py stood them where final.glb stands)
        fine = [o for o in bring(os.path.join(run, "base", "final.glb")) if o.type == "MESH"]
        for o in fine:
            o["kind"] = "body"
        for path in worn:
            for o in bring(path):
                if o.type == "MESH":
                    o["gear"] = o.get("gear") or os.path.splitext(os.path.basename(path))[0].replace("-", " ")
                    o["kind"] = "gear"
                    fine.append(o)
        put_back = {o["gear"] for o in fine if o["kind"] == "gear"}
        print("RIG dressed: the base body and %s" % ", ".join(sorted(put_back)), flush=True)
        # kind to kind: a garment from the same garment; the body from everything else, the skin it hides included
        donors_of = {gear: [o for o in rigged_meshes if gear_of(o) == gear] for gear in put_back}
        donors_of[None] = [o for o in rigged_meshes if gear_of(o) not in put_back]
    else:
        fine = [o for o in bring(os.path.join(run, mesh)) if o.type == "MESH"]
        donors_of = {None: [o for o in rigged_meshes if not o.get("under")]}
    trees = {k: surface(v) for k, v in donors_of.items() if v}

    bones = [b.name for b in rig.data.bones]
    apart = []
    for obj in fine:
        gear = obj.get("gear") if obj.get("kind") == "gear" else None
        tree, points, faces, weights = trees.get(gear) or trees[None]
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
        obj["named"] = "gear: %s" % gear if gear else "body"
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
    for obj in fine:  # (named once the rigged version's own meshes are gone, so a name is not taken)
        obj.name = obj["named"]
        del obj["named"]
    out = os.path.join(run, "profiles", name + "-walk.glb")
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_animations=True, export_yup=True)
    said.update({"glb": out, "bytes": os.path.getsize(out), "seconds": round(time.time() - began, 1), "skeleton_from": rigged + "-walk.glb", "mesh": mesh,
                 **({"garments": sorted(o["gear"] for o in fine if o.get("kind") == "gear")} if mesh == "dressed" else {})})
    with open(os.path.join(run, "profiles", name + "-walk.json"), "w") as f:
        json.dump({"rig_detailed": said}, f, indent=1)
    print("RESULT " + json.dumps(said))


main()
