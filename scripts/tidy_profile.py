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


def remesh_file(mesh_in, work, tag, want, params):
    """Run AutoRemesher on one OBJ until its quad count is within 10% of
    `want` (its own target is only a starting point). Returns (obj, quads, tries)."""
    adaptivity = params.get("adaptivity", 1.0)
    target = want * (5 if adaptivity > 0.5 else 2.5)
    tries, best = [], None
    for attempt in range(4):
        out = os.path.join(work, "%s-%d.obj" % (tag, attempt))
        report = out + ".txt"
        done = subprocess.run([
            AUTOREMESHER, "-i", mesh_in, "-o", out, "--report", report,
            "--target-quads", str(max(int(target), 50)),
            "--adaptivity", str(adaptivity),
            "--anisotropy", str(params.get("anisotropy", 1.0)),
            "--sharp-edge", str(params.get("sharp_edge", 90)),
        ], capture_output=True, timeout=600)
        if done.returncode != 0 or not os.path.exists(report):
            break
        with open(report) as f:
            got = int(next(l for l in f if l.strip().startswith("Quads:")).split(":")[1])
        tries.append({"target": int(target), "quads": got})
        if got and (best is None or abs(got - want) < abs(best[1] - want)):
            best = (out, got)
        if not got or abs(got - want) <= want * 0.1:
            break
        target *= want / got
    return best, tries


def export_obj(obj, path):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True, apply_modifiers=True,
                          export_materials=False, export_uv=False, export_normals=False,
                          export_triangulated_mesh=True, forward_axis="Y", up_axis="Z")


def import_obj(path):
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path, forward_axis="Y", up_axis="Z")
    return next(o for o in bpy.data.objects if o not in before and o.type == "MESH")


def split_parts(source, weld=True):
    """The object's separate pieces (handle, pins, body...) as their own
    objects, welded first so texture seams don't count as gaps. Pieces that
    were just cut apart share their seam vertices, so they skip the weld or
    it would stitch them back together."""
    import bmesh
    copy = source.copy()
    copy.data = source.data.copy()
    copy.modifiers.clear()
    for c in source.users_collection:
        c.objects.link(copy)
    if weld:
        bm = bmesh.new()
        bm.from_mesh(copy.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=max(source.dimensions) * 1e-6)
        bm.to_mesh(copy.data)
        bm.free()
    for o in bpy.context.selected_objects:
        o.select_set(False)
    copy.select_set(True)
    bpy.context.view_layer.objects.active = copy
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")
    return list(bpy.context.selected_objects)


def area(obj):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    total = sum(f.calc_area() for f in bm.faces)
    bm.free()
    return total


def autoremesh(params):
    """Adaptive quad remesh with AutoRemesher: denser quads where the shape
    curves, larger ones on flat areas, in regular loops.

    With "per_part", each separate piece of the object (body, handle,
    pins...) is remeshed on its own with a share of the quads in proportion
    to its area, never fewer than "min_part_quads". Off by default: on the
    kettle the pieces TRELLIS keeps separate are only the handle bits (the
    lid, knob and spout are fused into the body), so it changed little at
    web/game size and starved the thin handle brackets at mobile size."""
    want = params["quads"]
    if not os.access(AUTOREMESHER, os.X_OK):
        result = run_script("retopo.py", {"target_quads": want})
        result["note"] = "AutoRemesher not installed (just autoremesher); used QuadriFlow instead"
        return result
    source = largest_mesh()
    work = tempfile.mkdtemp(prefix="autoremesher-")
    # Part-by-part pays off at larger budgets; at a few thousand quads each
    # part's hidden cap and minimum budget cost more shape than they save.
    plan = (params.get("parts_plan") or {}) if params.get("use_parts", True) else {}
    try:
        if plan.get("parts"):
            # Cut the parts Claude found (split.py), then treat every piece
            # (cut parts and already-separate ones) as its own remesh.
            cut = run_script("split.py", {"object": source.name, "mode": "split",
                                          "parts": [{"name": p["name"], "box": {"min": p["min"], "max": p["max"]}}
                                                    for p in plan["parts"]]})
            pieces = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith(source.name + " · ")]
            for o in bpy.context.selected_objects:
                o.select_set(False)
            for o in pieces:
                o.select_set(True)
            bpy.context.view_layer.objects.active = pieces[0]
            bpy.ops.object.join()
            parted = bpy.context.view_layer.objects.active
            parted.name = source.name + " (parted)"
            parts = split_parts(parted, weld=False)
            bpy.data.objects.remove(parted, do_unlink=True)
            params = dict(params, per_part=True, cut=cut)
        if params.get("per_part", False):
            parts = parts if plan.get("parts") else split_parts(source)
            # Budgets grow slower than area, so thin parts (a strap, a pin)
            # aren't starved next to a big body.
            areas = {p.name: area(p) ** 0.75 for p in parts}
            total = sum(areas.values()) or 1.0
            floor = params.get("min_part_quads", 60)
        else:
            parts, areas, total, floor = [source], {source.name: 1.0}, 1.0, 0
        results, made = [], []
        for i, part in enumerate(parts):
            budget = max(floor, int(want * areas[part.name] / total))
            mesh_in = os.path.join(work, "part%d.obj" % i)
            export_obj(part, mesh_in)
            best, tries = remesh_file(mesh_in, work, "part%d" % i, budget, params)
            if best:
                made.append(import_obj(best[0]))
                kind = "remeshed"
            elif part is not source:
                # AutoRemesher gave nothing (tiny or degenerate piece): keep it,
                # reduced, rather than lose it.
                mod = part.modifiers.new("Decimate", "DECIMATE")
                mod.ratio = min(1.0, budget * 2 / max(len(part.data.polygons), 1))
                for o in bpy.context.selected_objects:
                    o.select_set(False)
                part.select_set(True)
                bpy.context.view_layer.objects.active = part
                bpy.ops.object.modifier_apply(modifier=mod.name)
                made.append(part)
                kind = "kept (reduced)"
            else:
                raise RuntimeError("AutoRemesher produced nothing for %s" % source.name)
            results.append({"share": round(areas[part.name] / total, 4), "budget": budget, "result": kind, "tries": tries})
        for p in parts:
            if p is not source and p not in made:
                bpy.data.objects.remove(p, do_unlink=True)
        for o in bpy.context.selected_objects:
            o.select_set(False)
        for o in made:
            o.hide_set(False)
            o.select_set(True)
        bpy.context.view_layer.objects.active = made[0]
        if len(made) > 1:
            bpy.ops.object.join()
        new = bpy.context.view_layer.objects.active
        new.name = source.name + " (quads)"
        new.data.materials.clear()
        bpy.ops.object.shade_smooth_by_angle(angle=0.61)
        source.hide_set(True)
        source.hide_render = True
        faces = new.data.polygons
        return {
            "object": new.name,
            "faces": len(faces),
            "quads": sum(1 for p in faces if len(p.vertices) == 4),
            "parts": results,
            "settings": {k: params.get(k) for k in ("adaptivity", "anisotropy", "sharp_edge", "per_part")},
            "cut": (params.get("cut") or {}).get("parts"),
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


class Skip(Exception):
    pass


def blockout(run_dir):
    """Claude's hand-built low-poly mesh (lowpoly.glb, step 4c), brought in
    as the light mesh to bake onto. Same world space as scene.blend."""
    path = os.path.join(run_dir, "lowpoly.glb")
    if not os.path.exists(path):
        raise Skip("no lowpoly.glb yet (just resume asks Claude to block it out)")
    full = largest_mesh()
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    low = bpy.context.view_layer.objects.active
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in [o for o in bpy.data.objects if o not in before and o is not low]:
        bpy.data.objects.remove(o, do_unlink=True)
    low.name = full.name + " (light)"
    low.data.materials.clear()
    full.hide_set(True)
    full.hide_render = True
    faces = low.data.polygons
    return {"object": low.name, "faces": len(faces),
            "triangles": sum(len(p.vertices) - 2 for p in faces),
            "quads": sum(1 for p in faces if len(p.vertices) == 4)}


def read_plan(source):
    """The run's parts.json (Claude's part boxes), if it has one."""
    path = os.path.join(os.path.dirname(source), "parts.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def make(source, out_dir, profile, spec):
    started = time.time()
    load(source)
    record = {"profile": profile, "about": spec["about"], "source": source, "steps": []}
    plan = read_plan(source)
    if plan.get("parts"):
        record["parts"] = [p["name"] for p in plan["parts"]]
    for name, params in spec["steps"]:
        if name == "autoremesher":
            result = autoremesh(dict(params, parts_plan=plan))
        elif name == "blockout":
            result = blockout(os.path.dirname(source))
        else:
            result = run_script(name, params)
        record["steps"].append({"script": name, "result": result})
    light = [n for n, _ in spec["steps"]]
    if {"retopo.py", "autoremesher", "blockout"} & set(light) or any(p.get("as_copy") for _, p in spec["steps"]):
        record["shape"] = run_script("match.py", {})
    glb = os.path.join(out_dir, profile + ".glb")
    record["export"] = run_script("export.py", dict(spec["export"], path=glb))
    if {"autoremesher", "retopo.py", "blockout"} & set(light):
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
    try:
        make(source, out_dir, profile, profiles[profile])
    except Skip as why:
        print("PROFILE %s: skipped, %s" % (profile, why))
