"""Run tidy-mesh skill scripts in a background Blender, for testing them
without a live Blender session or MCP.

    blender -b --factory-startup -P scripts/tidy_headless.py -- MESH.glb|SCENE.blend|- SCRIPT.py [SCRIPT.py ...] [--params '{"script.py": {...}}'] [--save OUT.blend]

Each script's PARAMS dict is updated from --params before it runs, the same
edit Claude makes before sending a script over MCP. Every script runs in a
fresh namespace, as every MCP call does. To run one script twice with
different PARAMS, list it twice and key the second one "script.py#2".
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

if mesh == "-":  # nothing to load: the scripts bring their own files
    bpy.ops.wm.read_factory_settings(use_empty=True)
elif mesh.endswith(".blend"):
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(mesh))
else:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.abspath(mesh))

seen = {}
for path in scripts:
    with open(path) as f:
        source = f.read()
    namespace = {"__name__": "__main__"}
    name = os.path.basename(path)
    seen[name] = seen.get(name, 0) + 1
    if seen[name] > 1:
        name = "%s#%d" % (name, seen[name])
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
