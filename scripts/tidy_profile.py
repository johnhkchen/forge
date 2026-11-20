"""Make one or more tidy-mesh profiles of an object, in a background Blender.

    blender -b --factory-startup -P scripts/tidy_profile.py -- SOURCE OUT_DIR PROFILE [PROFILE ...]

SOURCE is a .blend (the run's scene.blend, with Claude's material fixes) or a
.glb. The object is the largest visible mesh in it. For each profile this
writes OUT_DIR/<profile>.glb, <profile>.blend (keeps quads, which GLB
can't), <profile>.png, <profile>-wire.png and <profile>.json (what each
step did).

Profiles and their steps live in .claude/skills/tidy-mesh/profiles.json; the
steps are the same scripts Claude sends to a live Blender over MCP, plus one
step only this runner can do: "autoremesher", which hands the mesh to the
AutoRemesher program (MIT, github.com/huxingyi/autoremesher; install with
`just autoremesher`) for adaptive quad remeshing. Without the program it falls
back to retopo.py (QuadriFlow) and says so.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import bpy

SKILL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "tidy-mesh")
SCRIPTS = os.path.join(SKILL, "scripts")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
AUTOREMESHER = os.environ.get("AUTOREMESHER") or os.path.join(
    ROOT, "tools", "autoremesher-dl", "autoremesher.app", "Contents", "MacOS", "autoremesher")


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


def largest_mesh():
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get()]
    return max(meshes, key=lambda o: len(o.data.polygons))


def autoremesh(params):
    """Adaptive quad remesh with AutoRemesher: denser quads where the shape
    curves, larger ones on flat areas, in regular loops. Its quad target is a
    starting point, not a promise, so this re-runs (a few seconds each) until
    the result lands within 10% of the wanted count."""
    want = params["quads"]
    if not os.access(AUTOREMESHER, os.X_OK):
        result = run_script("retopo.py", {"target_quads": want})
        result["note"] = "AutoRemesher not installed (just autoremesher); used QuadriFlow instead"
        return result
    source = largest_mesh()
    work = tempfile.mkdtemp(prefix="autoremesher-")
    try:
        for o in bpy.context.selected_objects:
            o.select_set(False)
        source.select_set(True)
        bpy.context.view_layer.objects.active = source
        mesh_in = os.path.join(work, "in.obj")
        bpy.ops.wm.obj_export(filepath=mesh_in, export_selected_objects=True, apply_modifiers=True,
                              export_materials=False, export_uv=False, export_normals=False,
                              export_triangulated_mesh=True, forward_axis="Y", up_axis="Z")
        adaptivity = params.get("adaptivity", 1.0)
        target = want * (5 if adaptivity > 0.5 else 2.5)
        tries, best = [], None
        for attempt in range(4):
            out = os.path.join(work, "out%d.obj" % attempt)
            report = out + ".txt"
            subprocess.run([
                AUTOREMESHER, "-i", mesh_in, "-o", out, "--report", report,
                "--target-quads", str(int(target)),
                "--adaptivity", str(adaptivity),
                "--anisotropy", str(params.get("anisotropy", 1.0)),
                "--sharp-edge", str(params.get("sharp_edge", 90)),
            ], check=True, capture_output=True, timeout=600)
            with open(report) as f:
                got = int(next(l for l in f if l.strip().startswith("Quads:")).split(":")[1])
            tries.append({"target": int(target), "quads": got})
            if best is None or abs(got - want) < abs(best[1] - want):
                best = (out, got)
            if abs(got - want) <= want * 0.1 or got == 0:
                break
            target *= want / max(got, 1)
        before = set(bpy.data.objects)
        bpy.ops.wm.obj_import(filepath=best[0], forward_axis="Y", up_axis="Z")
        new = next(o for o in bpy.data.objects if o not in before and o.type == "MESH")
        new.name = source.name + " (quads)"
        for o in bpy.context.selected_objects:
            o.select_set(False)
        new.select_set(True)
        bpy.context.view_layer.objects.active = new
        bpy.ops.object.shade_smooth_by_angle(angle=0.61)
        source.hide_set(True)
        source.hide_render = True
        faces = new.data.polygons
        return {
            "object": new.name,
            "faces": len(faces),
            "quads": sum(1 for p in faces if len(p.vertices) == 4),
            "tries": tries,
            "settings": {"adaptivity": adaptivity, "sharp_edge": params.get("sharp_edge", 90)},
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def export_edges(path):
    """The light mesh's real edges (quads included) as a lines-only GLB, so a
    web viewer can draw the true topology. GLB meshes are always triangles."""
    import bmesh
    obj = largest_mesh()
    lines = obj.copy()
    lines.data = obj.data.copy()
    lines.modifiers.clear()
    lines.data.materials.clear()
    for c in obj.users_collection:
        c.objects.link(lines)
    bm = bmesh.new()
    bm.from_mesh(lines.data)
    bmesh.ops.delete(bm, geom=list(bm.faces), context="FACES_ONLY")
    bm.to_mesh(lines.data)
    bm.free()
    for o in bpy.context.selected_objects:
        o.select_set(False)
    lines.select_set(True)
    bpy.context.view_layer.objects.active = lines
    obj.hide_set(True)
    try:
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                                  use_mesh_edges=True, export_materials="NONE",
                                  export_normals=False, export_texcoords=False)
    finally:
        obj.hide_set(False)
        bpy.data.objects.remove(lines, do_unlink=True)


def make(source, out_dir, profile, spec):
    started = time.time()
    load(source)
    record = {"profile": profile, "about": spec["about"], "source": source, "steps": []}
    for name, params in spec["steps"]:
        result = autoremesh(params) if name == "autoremesher" else run_script(name, params)
        record["steps"].append({"script": name, "result": result})
    light = [n for n, _ in spec["steps"]]
    if {"retopo.py", "autoremesher"} & set(light) or any(p.get("as_copy") for _, p in spec["steps"]):
        record["shape"] = run_script("match.py", {})
    glb = os.path.join(out_dir, profile + ".glb")
    record["export"] = run_script("export.py", dict(spec["export"], path=glb))
    if {"autoremesher", "retopo.py"} & set(light):
        export_edges(os.path.join(out_dir, profile + "-edges.glb"))
    # GLB can only store triangles; the .blend keeps the real quads for
    # anyone who will keep modeling it.
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, profile + ".blend"), copy=True, compress=True)
    run_script("preview.py", {"path": os.path.join(out_dir, profile + ".png")})
    run_script("preview.py", {"path": os.path.join(out_dir, profile + "-wire.png"), "wireframe": True})
    record["bytes"] = os.path.getsize(glb)
    record["seconds"] = round(time.time() - started, 1)
    with open(os.path.join(out_dir, profile + ".json"), "w") as f:
        json.dump(record, f, indent=2)
    shape = record.get("shape")
    off = " worst %.2f%% off" % shape["shape_lost"]["max_%"] if shape else ""
    print("PROFILE %s: %d faces,%s %.1f MB, %.0fs -> %s" % (
        profile, record["export"]["faces"], off, record["bytes"] / 1e6, record["seconds"], glb))


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
# The raw mesh as the scene placed it (real size, Claude's orientation), so a
# before/after view lines up. Same TRELLIS.2 geometry as mesh.glb.
raw = os.path.join(out_dir, "raw.glb")
if not os.path.exists(raw):
    load(source)
    run_script("export.py", {"path": raw, "image_format": "WEBP", "draco": False})
for profile in wanted:
    make(source, out_dir, profile, profiles[profile])
