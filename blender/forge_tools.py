"""Forge tools for Blender: the tidy-mesh scripts as one operator.

Installed by `just forge-addon` into Blender's scripts/startup folder, next to
a forge_tools/ folder holding copies of .claude/skills/tidy-mesh/scripts. Blender
loads startup scripts at launch, so nothing needs enabling in preferences.

Why: the Blender MCP add-on runs every execute_blender_code call in a fresh
namespace, so Claude had to paste a whole tool script into every call. With
this installed, a call is one line:

    bpy.ops.forge.run(tool="measure", params=json.dumps({"parts": [...]}))
    print(bpy.context.scene["forge_result"])

What it can run is fixed at install time: only the bundled tool scripts, picked
by name, with data-only JSON settings. It adds no way to run arbitrary code.
"""

import json
import os
import re

import bpy

TOOLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "forge_tools")
NAME = re.compile(r"^[a-z_]+$")


def tool_names():
    if not os.path.isdir(TOOLS_DIR):
        return []
    return sorted(f[:-3] for f in os.listdir(TOOLS_DIR) if f.endswith(".py") and NAME.match(f[:-3]))


def run_tool(tool, params):
    """Run one bundled tool script with its PARAMS updated, the same way the
    pipeline's background runner does, and return its RESULT json."""
    if not NAME.match(tool) or tool not in tool_names():
        raise ValueError("no Forge tool named %r; tools: %s" % (tool, ", ".join(tool_names())))
    with open(os.path.join(TOOLS_DIR, tool + ".py")) as f:
        source = f.read()
    head, sep, tail = source.partition("\nimport ")
    if not sep:
        raise ValueError("%s.py has no PARAMS block followed by imports" % tool)
    namespace = {"__name__": "__main__"}
    exec(head, namespace)
    namespace["PARAMS"].update(params)
    results = []

    def capture(*args, **kwargs):
        text = " ".join(str(a) for a in args)
        if text.startswith("RESULT "):
            results.append(text[len("RESULT "):])
        print(*args, **kwargs)

    namespace["print"] = capture
    exec("import " + tail, namespace)
    return results[-1] if results else json.dumps({"note": "%s printed no RESULT" % tool})


class FORGE_OT_run(bpy.types.Operator):
    """Run a Forge tool (tidy-mesh script) with JSON settings; the result is in scene["forge_result"]"""

    bl_idname = "forge.run"
    bl_label = "Run Forge tool"
    bl_options = {"REGISTER", "UNDO"}

    tool: bpy.props.StringProperty(name="Tool")
    params: bpy.props.StringProperty(name="Settings (JSON)", default="{}")

    def execute(self, context):
        scene = context.scene
        try:
            settings = json.loads(self.params or "{}")
            if not isinstance(settings, dict):
                raise ValueError("params must be a JSON object")
            scene["forge_result"] = run_tool(self.tool, settings)
            return {"FINISHED"}
        except Exception as err:  # report it where Claude reads results
            scene["forge_result"] = json.dumps({"error": "%s: %s" % (type(err).__name__, err)})
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}


class FORGE_OT_list(bpy.types.Operator):
    """List the installed Forge tools in scene["forge_result"]"""

    bl_idname = "forge.list"
    bl_label = "List Forge tools"

    def execute(self, context):
        context.scene["forge_result"] = json.dumps({"tools": tool_names()})
        return {"FINISHED"}


CLASSES = (FORGE_OT_run, FORGE_OT_list)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
