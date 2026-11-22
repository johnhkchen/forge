"""Write the wardrobe template as the .glb the tools read, from the .blend it is modeled in.

    blender -b --factory-startup -P scripts/wardrobe/template_glb.py -- TEMPLATE.blend OUT.glb [NAME]

TEMPLATE.blend holds one object, "template": the headless body in a T-pose (z up, feet on z = 0, facing -y),
its quads, its texture layout, a face attribute "region" (which part of the body each face is), a vertex group
per bone (rig.py's names) and two notes, "wardrobe_canon" (where its joints are) and "template_cut" (the collar).
scripts/wardrobe/README.md says how that file was made.

A .glb holds triangles only and one weight set of four bones a point, so:
  - every quad is written as two triangles one after the other, and the file says which faces were quads
    ("template_faces": one digit a face, 3 or 4), so wrap.py can put the quads back exactly;
  - "template_regions" has each face's region (one hex digit a face), "template_canon" the joints;
  - the weights ride on a plain skeleton (the canon joints, rig.py's bone names), at most four bones a point.
The file is checked after writing: read back and put together again the way wrap.py does it, it must have the
same faces in the same places with the same layout, regions and weights. Prints TEMPLATE {json}.
"""
import json
import os
import sys

import bmesh
import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree

REGIONS = ["head", "upper_torso", "lower_torso", "upper_arm_l", "lower_arm_l", "hand_l", "upper_arm_r", "lower_arm_r", "hand_r",
           "upper_leg_l", "lower_leg_l", "foot_l", "upper_leg_r", "lower_leg_r", "foot_r"]
BONES = [("hips", "hips", "spine", None), ("spine", "spine", "chest", "hips"), ("chest", "chest", "neck", "spine"),
         ("neck", "neck", "head", "chest"), ("head", "head", "head_top", "neck")]
for s in "lr":
    BONES += [("shoulder_" + s, "shoulder_" + s, "upper_arm_" + s, "chest"), ("upper_arm_" + s, "upper_arm_" + s, "forearm_" + s, "shoulder_" + s),
              ("forearm_" + s, "forearm_" + s, "hand_" + s, "upper_arm_" + s), ("hand_" + s, "hand_" + s, "hand_tip_" + s, "forearm_" + s),
              ("thigh_" + s, "thigh_" + s, "shin_" + s, "hips"), ("shin_" + s, "shin_" + s, "foot_" + s, "thigh_" + s),
              ("foot_" + s, "foot_" + s, "toe_" + s, "shin_" + s), ("toe_" + s, "toe_" + s, "toe_tip_" + s, "foot_" + s)]
COPYRIGHT = "CC0 1.0. Mesh derived from the MakeHuman base mesh (CC0 1.0); only its mesh data is used."


def read_template(path):
    """The template .glb as wrap.py reads it: one welded mesh with its quads and regions back. Returns (object, notes)."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path, merge_vertices=True)
    new = [o for o in bpy.data.objects if o not in before]
    obj = next(o for o in new if o.type == "MESH" and o.get("template"))
    world = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = world
    for mod in list(obj.modifiers):
        obj.modifiers.remove(mod)
    for o in new:
        if o is not obj:
            bpy.data.objects.remove(o, do_unlink=True)
    sizes = obj["template_faces"]
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    region = bm.faces.layers.int.new("region")
    order = bm.faces.layers.int.new("order")
    cuts, at = [], 0
    for number, (size, code) in enumerate(zip(sizes, obj["template_regions"])):
        mine = [bm.faces[at], bm.faces[at + 1]] if size == "4" else [bm.faces[at]]
        for f in mine:
            f[region], f[order] = int(code, 16), number
        if size == "4":  # two triangles in a row that were one quad: the edge they share goes
            cuts.append(next(e for e in mine[0].edges if mine[1] in e.link_faces))
        at += len(mine)
    bmesh.ops.dissolve_edges(bm, edges=cuts, use_verts=False)
    bm.faces.sort(key=lambda f: f[order])  # the faces in the order the template has them
    bm.faces.layers.int.remove(order)
    bm.to_mesh(obj.data)
    bm.free()
    return obj, {"canon": json.loads(obj["template_canon"]), "cut": json.loads(obj["template_cut"]), "name": obj["template"]}


def nearest_corner(here, p):
    best, best_d = 0, 1e9
    for k, q in enumerate(here):
        d = (q - p).length
        if d < best_d:
            best, best_d = k, d
    return best, best_d


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    source, out = os.path.abspath(args[0]), os.path.abspath(args[1])
    name = args[2] if len(args) > 2 else os.path.splitext(os.path.basename(out))[0]
    bpy.ops.wm.open_mainfile(filepath=source)
    src = bpy.data.objects["template"]
    me = src.data
    canon = json.loads(src["wardrobe_canon"])
    uv = me.uv_layers.active.data
    regions = [0] * len(me.polygons)
    me.attributes["region"].data.foreach_get("value", regions)

    # the same points; each quad as two triangles, one after the other
    tris, tri_uv, sizes = [], [], ""
    for p in me.polygons:
        v, l = list(p.vertices), list(p.loop_indices)
        if len(v) not in (3, 4):
            raise ValueError("a face with %d sides: the template is quads and triangles only" % len(v))
        for a, b, c in ((0, 1, 2), (0, 2, 3))[:len(v) - 2]:
            tris.append((v[a], v[b], v[c]))
            tri_uv += [uv[l[a]].uv.copy(), uv[l[b]].uv.copy(), uv[l[c]].uv.copy()]
        sizes += str(len(v))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([v.co.copy() for v in me.vertices], [], tris)
    layer = mesh.uv_layers.new(name="UVMap")
    for i, at in enumerate(tri_uv):
        layer.data[i].uv = at
    for p in mesh.polygons:
        p.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    scene = bpy.context.scene
    scene.collection.objects.link(obj)

    # weights: the template's own, the four strongest a point, adding up to 1
    names = [g.name for g in src.vertex_groups]
    groups = {n: obj.vertex_groups.new(name=n) for n in names}
    cut_down = 0
    for v in me.vertices:
        pairs = sorted(((g.weight, names[g.group]) for g in v.groups if g.weight > 1e-4), reverse=True)
        cut_down += len(pairs) > 4
        total = sum(w for w, _ in pairs[:4])
        for w, n in pairs[:4]:
            groups[n].add([v.index], w / total, "REPLACE")

    # a plain skeleton on the canon joints to carry them
    arm = bpy.data.armatures.new(name + " bones")
    rig = bpy.data.objects.new(name + " bones", arm)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for bone, a, b, parent in BONES:
        eb = arm.edit_bones.new(bone)
        eb.head, eb.tail = Vector(canon[a]), Vector(canon[b])
        if parent:
            eb.parent = arm.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.parent = rig
    obj.modifiers.new("Armature", "ARMATURE").object = rig

    obj["template"] = name
    obj["template_faces"] = sizes
    obj["template_regions"] = "".join("%x" % r for r in regions)
    obj["template_region_names"] = json.dumps(REGIONS)
    obj["template_canon"] = json.dumps({k: [round(c, 5) for c in v] for k, v in canon.items()})
    obj["template_cut"] = src["template_cut"]
    obj["license"] = COPYRIGHT
    bpy.data.objects.remove(src, do_unlink=True)
    for o in scene.objects:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_extras=True, export_skins=True,
                              export_animations=False, export_materials="NONE", export_copyright=COPYRIGHT)

    # read it back, as wrap.py will, and compare it face by face with what went in
    bpy.ops.wm.open_mainfile(filepath=source)
    src = bpy.data.objects["template"]
    a = src.data
    back, notes = read_template(out)
    b = back.data
    same = len(a.polygons) == len(b.polygons) and len(a.vertices) == len(b.vertices)
    worst = worst_uv = weights_off = 0.0
    wrong_region = -1
    if same:
        kept = [0] * len(b.polygons)
        b.attributes["region"].data.foreach_get("value", kept)
        wrong_region = sum(1 for x, y in zip(regions, kept) if x != y)
        for p, q in zip(a.polygons, b.polygons):
            if len(p.vertices) != len(q.vertices):
                same = False
                break
            here = [back.matrix_world @ b.vertices[i].co for i in q.vertices]
            for i, li in zip(p.vertices, p.loop_indices):
                near, off = nearest_corner(here, a.vertices[i].co)
                worst = max(worst, off)
                worst_uv = max(worst_uv, (b.uv_layers.active.data[q.loop_indices[near]].uv - a.uv_layers.active.data[li].uv).length)
        tree = KDTree(len(b.vertices))
        for v in b.vertices:
            tree.insert(back.matrix_world @ v.co, v.index)
        tree.balance()
        bnames = [g.name for g in back.vertex_groups]
        for v in a.vertices:
            w = b.vertices[tree.find(v.co)[1]]
            got = {bnames[g.group]: g.weight for g in w.groups}
            pairs = sorted(((g.weight, names[g.group]) for g in v.groups if g.weight > 1e-4), reverse=True)[:4]
            total = sum(x for x, _ in pairs)
            for x, n in pairs:
                weights_off = max(weights_off, abs(got.get(n, 0.0) - x / total))
    bm = bmesh.new()
    bm.from_mesh(b)
    collar = sum(1 for e in bm.edges if e.is_boundary)
    bm.free()
    report = {"file": out, "bytes": os.path.getsize(out), "name": name, "points": len(b.vertices), "faces": len(b.polygons),
              "quads": sizes.count("4"), "triangles": sizes.count("3") + 2 * sizes.count("4"), "bones": len(BONES),
              "points_cut_down_to_four_bones": cut_down, "same_faces_read_back": same, "worst_point_off_m": round(worst, 7),
              "worst_layout_off": round(worst_uv, 7), "faces_with_the_wrong_region": wrong_region, "worst_weight_off": round(weights_off, 5),
              "collar_edges": collar, "joints": sorted(notes["canon"])}
    print("TEMPLATE " + json.dumps(report))
    if not (same and worst < 1e-5 and worst_uv < 1e-5 and wrong_region == 0 and weights_off < 1e-3):
        sys.exit("the file does not read back as the template went in")


if __name__ == "__main__":
    main()
