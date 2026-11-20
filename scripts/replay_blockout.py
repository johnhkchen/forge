"""Get the recipe of a block-out made before recipes were kept, by running
its transcript again in a background Blender.

    blender -b --factory-startup -P scripts/replay_blockout.py -- RUN_DIR [OUT_DIR]

A run's transcripts/lowpoly.jsonl holds every script Claude sent to Blender
in step 4c. This sends the same scripts, in order, to an empty background
Blender with today's tools (so build.py keeps the recipe), and writes
OUT_DIR/lowpoly_build.json: what the `midpoly` profile rebuilds from. It
also writes OUT_DIR/lowpoly.glb, the block-out as today's tools export it.
OUT_DIR defaults to RUN_DIR/replay, so the run's own lowpoly.glb is never
replaced; copy lowpoly_build.json up beside it to use it.

It only works for runs that used the Forge add-on's one-line tool calls
(`bpy.ops.forge.run`). The pieces carry no gear names: the old block-outs
had clothing built into the body.
"""
import importlib.util
import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import blockout_recipe  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
if not args:
    sys.exit("usage: replay_blockout.py -- RUN_DIR [OUT_DIR]")
run = os.path.abspath(args[0])
out = os.path.abspath(args[1]) if len(args) > 1 else os.path.join(run, "replay")
os.makedirs(out, exist_ok=True)

# The Forge add-on, pointed at this repo's scripts instead of an installed copy.
spec = importlib.util.spec_from_file_location("forge_tools", os.path.join(HERE, "..", "blender", "forge_tools.py"))
forge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(forge)
forge.TOOLS_DIR = os.path.join(HERE, "..", ".claude", "skills", "tidy-mesh", "scripts")
real_run = forge.run_tool


def run_tool(tool, params):
    """Files are read from this run folder and written to OUT_DIR, wherever the run was when it was made."""
    if tool == "open" and params.get("mesh"):
        params["mesh"] = os.path.join(run, os.path.basename(params["mesh"]))
    if tool == "export" and params.get("path"):
        params["path"] = os.path.join(out, os.path.basename(params["path"]))
    return real_run(tool, params)


forge.run_tool = run_tool
forge.register()
bpy.ops.wm.read_factory_settings(use_empty=True)

calls = failed = 0
with open(os.path.join(run, "transcripts", "lowpoly.jsonl")) as f:
    for line in f:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") != "assistant":
            continue
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "tool_use" and block.get("name", "").endswith("execute_blender_code"):
                calls += 1
                try:
                    exec(block["input"].get("code", ""), {"bpy": bpy})
                except Exception as err:  # calls failed in the live session too; the next one usually recovers
                    failed += 1
                    print("replay: call %d failed: %s: %s" % (calls, type(err).__name__, err))

glb = os.path.join(out, "lowpoly.glb")
recipe = None
if os.path.exists(glb):
    blockout_recipe.main(glb)
    recipe = os.path.exists(os.path.join(out, "lowpoly_build.json"))
print("REPLAY " + json.dumps({"calls": calls, "failed": failed, "recipe": bool(recipe), "out": out}))
