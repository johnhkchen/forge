"""Run tidy-mesh skill scripts in a background Blender, for testing them
without a live Blender session or MCP.

    blender -b --factory-startup -P scripts/tidy_headless.py -- MESH.glb|SCENE.blend SCRIPT.py [SCRIPT.py ...] [--params '{"script.py": {...}}'] [--save OUT.blend]

Each script's PARAMS dict is updated from --params before it runs, the same
edit Claude makes before sending a script over MCP.
"""
import json
import os
import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1 :]
save = None
overrides = {}
if "--save" in args:
    i = args.index("--save")
    save = args[i + 1]
    del args[i : i + 2]
if "--params" in args:
    i = args.index("--params")
    overrides = json.loads(args[i + 1])
    del args[i : i + 2]
mesh, scripts = args[0], args[1:]

if mesh.endswith(".blend"):
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(mesh))
else:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.abspath(mesh))

for path in scripts:
    with open(path) as f:
        source = f.read()
    namespace = {"__name__": "__main__"}
    name = os.path.basename(path)
    if name in overrides:
        # Run the PARAMS block first, patch it, then run the rest.
        head, _, tail = source.partition("\nimport ")
        exec(head, namespace)
        namespace["PARAMS"].update(overrides[name])
        exec("import " + tail, namespace)
    else:
        exec(source, namespace)

if save:
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(save))
