"""Make a small made-up character for testing the base-body tools: a
T-pose figure of tubes in a long red skirt, as a picture and a mesh, and the
same figure without the skirt. Every face's owner is known, so a cut can be
checked exactly.

    blender -b --factory-startup -P scripts/base_fixture.py -- OUT_DIR

Writes, laid out like a run:
    OUT_DIR/image.png, mesh.glb             clothed (body, legs under the skirt, skirt)
    OUT_DIR/base/image.png, mesh.glb        the same body, legs in black, no skirt
    OUT_DIR/moved/image.png                 the base picture with the figure slid sideways
    OUT_DIR/small/mesh.glb                  the base body shrunk and shifted
    OUT_DIR/posed/mesh.glb                  the base body with its arms down
    OUT_DIR/truth.json                      how many faces are skirt, and how many in all
Prints RESULT {json}.
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

SKIN, BLACK, RED = 0, 1, 2
COLORS = [(0.78, 0.6, 0.45), (0.06, 0.06, 0.07), (0.75, 0.1, 0.1), (0.9, 0.9, 0.9)]


def texture():
    image = bpy.data.images.new("fixture colors", 64, 16)
    flat = []
    for _ in range(16):
        for u in range(64):
            flat.extend(COLORS[u // 16] + (1.0,))
    image.pixels.foreach_set(flat)
    image.pack()
    material = bpy.data.materials.new("fixture")
    material.use_nodes = True
    node = material.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    node.interpolation = "Closest"
    shader = material.node_tree.nodes["Principled BSDF"]
    material.node_tree.links.new(node.outputs["Color"], shader.inputs["Base Color"])
    return material


def tube(bm, low, high, r_low, r_high, color, caps=True, rings=14, around=40):
    """A tube between two points, in one color; returns its faces."""
    low, high = Vector(low), Vector(high)
    turn = Vector((0, 0, 1)).rotation_difference(high - low).to_matrix()
    loops = []
    for k in range(rings + 1):
        t = k / rings
        radius = r_low + (r_high - r_low) * t
        loops.append([bm.verts.new(low + (high - low) * t + turn @ Vector((radius * math.cos(2 * math.pi * j / around), radius * math.sin(2 * math.pi * j / around), 0)))
                      for j in range(around)])
    faces = []
    for k in range(rings):
        for j in range(around):
            faces.append(bm.faces.new((loops[k][j], loops[k][(j + 1) % around], loops[k + 1][(j + 1) % around], loops[k + 1][j])))
    if caps:
        faces.append(bm.faces.new(list(reversed(loops[0]))))
        faces.append(bm.faces.new(loops[-1]))
    paint(bm, faces, color)
    return faces


def ball(bm, at, radius, color):
    made = bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=radius)
    bmesh.ops.translate(bm, verts=made["verts"], vec=Vector(at))
    paint(bm, list({f for v in made["verts"] for f in v.link_faces}), color)


def paint(bm, faces, color):
    uv = bm.loops.layers.uv.verify()
    for f in faces:
        for loop in f.loops:
            loop[uv].uv = ((color * 16 + 8) / 64.0, 0.5)


def figure(name, material, skirt, legs, arms_down=False):
    """The figure as one mesh object, centered like a TRELLIS.2 mesh (-0.5 to 0.5 tall, front -Y)."""
    bm = bmesh.new()
    ball(bm, (0, 0, 0.43), 0.07, SKIN)
    tube(bm, (0, -0.05, 0.43), (0, -0.1, 0.42), 0.02, 0.012, SKIN, rings=3, around=12)  # a nose, so front and back differ
    tube(bm, (0, 0, 0.0), (0, 0, 0.36), 0.09, 0.075, BLACK)
    for side in (-1, 1):
        hand = (side * 0.2, 0, -0.02) if arms_down else (side * 0.46, 0, 0.3)
        tube(bm, (side * 0.07, 0, 0.3), hand, 0.03, 0.025, SKIN)
        tube(bm, (side * 0.05, 0, -0.5), (side * 0.05, 0, 0.02), 0.04, 0.047, legs)
        tube(bm, (side * 0.05, 0.02, -0.48), (side * 0.05, -0.13, -0.48), 0.02, 0.02, BLACK, rings=4, around=16)  # a foot, pointing front
    skirt_faces = 0
    if skirt:
        skirt_faces = len(tube(bm, (0, 0, -0.4), (0, 0, 0.03), 0.27, 0.094, RED, caps=False, rings=24, around=64))
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    skirt_faces = sum(1 for f in bm.faces if skirt and f.loops[0][bm.loops.layers.uv.verify()].uv.x > 0.5 and f.loops[0][bm.loops.layers.uv.verify()].uv.x < 0.75)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    total = len(bm.faces)
    bm.free()
    me.materials.append(material)
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj, skirt_faces, total


def show_only(obj):
    for o in bpy.context.scene.objects:
        if o.type == "MESH":
            o.hide_render = o != obj
            o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj


def picture(obj, path, slide=0.0):
    show_only(obj)
    scene = bpy.context.scene
    scene.camera.location = (slide, -5, 0)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def mesh(obj, path):
    show_only(obj)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, use_active_scene=True)


def main(out):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for folder in ("", "base", "moved", "small", "posed"):
        os.makedirs(os.path.join(out, folder), exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "TEXTURE"
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x = scene.render.resolution_y = 512
    scene.world = bpy.data.worlds.new("gray")
    scene.world.color = (0.5, 0.5, 0.5)
    camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 1.25
    camera.rotation_euler = (math.pi / 2, 0, 0)

    material = texture()
    clothed, skirt_faces, total = figure("clothed", material, skirt=True, legs=SKIN)
    base, _, base_total = figure("base", material, skirt=False, legs=BLACK)
    posed, _, _ = figure("posed", material, skirt=False, legs=BLACK, arms_down=True)
    picture(clothed, os.path.join(out, "image.png"))
    picture(base, os.path.join(out, "base", "image.png"))
    picture(base, os.path.join(out, "moved", "image.png"), slide=0.06)
    mesh(clothed, os.path.join(out, "mesh.glb"))
    mesh(base, os.path.join(out, "base", "mesh.glb"))
    mesh(posed, os.path.join(out, "posed", "mesh.glb"))
    base.data.transform(Matrix.Translation((0.02, 0.01, -0.03)) @ Matrix.Scale(0.9, 4))
    mesh(base, os.path.join(out, "small", "mesh.glb"))
    truth = {"skirt_faces": skirt_faces, "faces": total, "base_faces": base_total, "skirt_top": 0.53, "skirt_bottom": 0.1,
             "small": {"scale": 0.9, "shift": [0.02, 0.01, -0.03]}}
    with open(os.path.join(out, "truth.json"), "w") as f:
        json.dump(truth, f, indent=1)
    print("RESULT " + json.dumps(truth))


main(os.path.abspath(sys.argv[sys.argv.index("--") + 1]))
