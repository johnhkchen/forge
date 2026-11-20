"""Make one or more tidy-mesh profiles of an object, in a background Blender.

    blender -b --factory-startup -P scripts/tidy_profile.py -- SOURCE OUT_DIR PROFILE [PROFILE ...]

SOURCE is a .blend (the run's scene.blend, with Claude's material fixes) or a
.glb. The object is the largest visible mesh in it. For each profile this
writes OUT_DIR/<profile>.glb, <profile>.blend (keeps quads, which GLB
can't), <profile>.png, <profile>-wire.png and <profile>.json (what each
step did).

Profiles and their steps live in .claude/skills/tidy-mesh/profiles.json; the
steps are the same scripts Claude sends to a live Blender over MCP.
"""
import json
import os
import sys
import time

import bpy

SKILL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "tidy-mesh")
SCRIPTS = os.path.join(SKILL, "scripts")


def load(source):
    if source.endswith(".blend"):
        bpy.ops.wm.open_mainfile(filepath=source)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=source)


def run_script(name, params):
    """Run a skill script with its PARAMS updated, as Claude would over MCP,
    and return the JSON it printed."""
    with open(os.path.join(SCRIPTS, name)) as f:
        source = f.read()
    head, _, tail = source.partition("\nimport ")
    namespace = {"__name__": "__main__"}
    exec(head, namespace)
    namespace["PARAMS"].update(params)
    captured = []
    real_print = print

    def capture(*args, **kwargs):
        text = " ".join(str(a) for a in args)
        if text.startswith("RESULT "):
            captured.append(json.loads(text[len("RESULT "):]))
        real_print(*args, **kwargs)

    namespace["print"] = capture
    exec("import " + tail, namespace)
    return captured[-1] if captured else None


def make(source, out_dir, profile, spec):
    started = time.time()
    load(source)
    record = {"profile": profile, "about": spec["about"], "source": source, "steps": []}
    for name, params in spec["steps"]:
        record["steps"].append({"script": name, "result": run_script(name, params)})
    glb = os.path.join(out_dir, profile + ".glb")
    record["export"] = run_script("export.py", dict(spec["export"], path=glb))
    # GLB can only store triangles; the .blend keeps the real quads for
    # anyone who will keep modeling it.
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, profile + ".blend"), copy=True, compress=True)
    run_script("preview.py", {"path": os.path.join(out_dir, profile + ".png")})
    run_script("preview.py", {"path": os.path.join(out_dir, profile + "-wire.png"), "wireframe": True})
    record["bytes"] = os.path.getsize(glb)
    record["seconds"] = round(time.time() - started, 1)
    with open(os.path.join(out_dir, profile + ".json"), "w") as f:
        json.dump(record, f, indent=2)
    print("PROFILE %s: %d faces, %.1f MB, %.0fs -> %s" % (
        profile, record["export"]["faces"], record["bytes"] / 1e6, record["seconds"], glb))


args = sys.argv[sys.argv.index("--") + 1:]
if len(args) < 3:
    sys.exit("usage: tidy_profile.py -- SOURCE OUT_DIR PROFILE [PROFILE ...]")
source, out_dir, wanted = os.path.abspath(args[0]), os.path.abspath(args[1]), args[2:]
with open(os.path.join(SKILL, "profiles.json")) as f:
    profiles = json.load(f)
unknown = [p for p in wanted if p not in profiles]
if unknown:
    sys.exit("unknown profile(s) %s; choose from %s" % (unknown, sorted(profiles)))
os.makedirs(out_dir, exist_ok=True)
for profile in wanted:
    make(source, out_dir, profile, profiles[profile])
