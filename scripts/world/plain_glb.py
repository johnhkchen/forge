"""Writes .glb files again without Draco, in place, in a background Blender.

    Blender -b --factory-startup -P scripts/world/plain_glb.py -- <file.glb> [<file.glb> ...]

A run's light versions are Draco-packed, which a browser can only open after
fetching a decoder. The world's first view should need nothing but the files
themselves, so the copies the world keeps (scripts/world/world.py stock) are
unpacked here once. They are a few hundred triangles each: unpacked they are
still small. Pictures stay WebP. Never touches an open Blender.
"""

import os
import sys

import bpy


def main():
    for path in sys.argv[sys.argv.index("--") + 1:]:
        before = os.path.getsize(path)
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=path)
        for o in [o for o in bpy.data.objects if o.type == "MESH" and o.find_armature() is None and o.name.startswith("Icosphere")]:
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_active_scene=True, export_apply=False, export_animations=False,
                                  export_draco_mesh_compression_enable=False, export_image_format="WEBP", export_extras=True)
        print("PLAIN %s: %d -> %d bytes" % (os.path.basename(path), before, os.path.getsize(path)))


main()
