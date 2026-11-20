"""Make one or more tidy-mesh profiles of an object, in a background Blender.

    blender -b --factory-startup -P scripts/tidy_profile.py -- SOURCE OUT_DIR PROFILE [PROFILE ...]

SOURCE is a .blend (the run's scene.blend, with Claude's material fixes) or a
.glb. The object is the largest visible mesh in it. For each profile this
writes OUT_DIR/<profile>.glb, <profile>.blend (keeps quads, which GLB
can't), <profile>.png, <profile>-wire.png and <profile>.json (what each
step did).

Profiles and their steps live in .claude/skills/tidy-mesh/profiles.json; the
steps are the same scripts Claude sends to a live Blender over MCP, plus one
steps only this runner can do:

- "autoremesher" hands the mesh to the AutoRemesher program (MIT,
  github.com/huxingyi/autoremesher; install with `just autoremesher`) for
  adaptive quad remeshing. Without the program it falls back to retopo.py
  (QuadriFlow) and says so.
- "blockout" brings in Claude's low-poly block-out (the run's lowpoly.glb).
- "rebuild" builds that block-out again from its recipe (lowpoly_build.json),
  with more sides and more rings: the mid-poly version.

A character's gear stays apart in both: the .glb gets one mesh per group
("body", "gear: wool singlet"...) and an empty per attachment point. Its
colors are baked by group (bake.py): gear copies cloth, the body skin.

The "walk" profile is different in kind: it takes the low-poly and mid-poly
versions already in OUT_DIR and writes each again with a skeleton and a walk,
<version>-walk.glb and <version>-walk.json (rig.py, walk.py, animate.py). It
reads the run's gait.json (how the character carries itself, from Opus) and
lowpoly_build.json (the block-out's recipe, to place the joints) when they
are there, and manages without either.

The "run" profile is the same again with a looping run, <version>-run.glb and
<version>-run.json. The run is not worked out here: it is a clip made from a
sentence by Kimodo on the motion worker and cut into a loop
(scripts/motion/run_clip.py leaves it in the run's run/loop.json; `just runs`
does all of it). With no clip there, the profile is skipped with a note.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blockout_recipe  # noqa: E402

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


REMESH_TIMEOUT_S = 120  # per AutoRemesher attempt
RETRY_PARTS_OFF = 10.0  # worst-spot % at which a whole remesh gets a part-by-part try
REMESH_GAP_PCT = 3.0  # p95 gap, % of the object's size: good pieces stay under ~2.5 (kettle, baguette, ring posts' tops); the ring's shredded ropes 4-58


def remesh_file(mesh_in, work, tag, want, params):
    """Run AutoRemesher on one OBJ until its quad count is within 10% of
    `want` (its own target is only a starting point). Returns (obj, quads, tries)."""
    adaptivity = params.get("adaptivity", 1.0)
    target = want * (5 if adaptivity > 0.5 else 2.5)
    ceiling = want * 40  # past this AutoRemesher can grind for hours on one part
    tries, made, starved = [], [], 0
    for attempt in range(4):
        out = os.path.join(work, "%s-%d.obj" % (tag, attempt))
        report = out + ".txt"
        try:
            done = subprocess.run([
                AUTOREMESHER, "-i", mesh_in, "-o", out, "--report", report,
                "--target-quads", str(max(int(target), 50)),
                "--adaptivity", str(adaptivity),
                "--anisotropy", str(params.get("anisotropy", 1.0)),
                "--sharp-edge", str(params.get("sharp_edge", 90)),
            ], capture_output=True, timeout=REMESH_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            tries.append({"target": int(target), "quads": None, "note": "gave up after %ds" % REMESH_TIMEOUT_S})
            break
        if done.returncode != 0 or not os.path.exists(report):
            break
        with open(report) as f:
            got = int(next(l for l in f if l.strip().startswith("Quads:")).split(":")[1])
        tries.append({"target": int(target), "quads": got})
        if got:
            made.append((out, got))
        if not got or abs(got - want) <= want * 0.1:
            break
        # A part AutoRemesher can barely mesh (a thin skirt, a shell) answers a
        # big target with a handful of quads; scaling by want/got then asks for
        # millions. Grow at most 4x a round, stop at the ceiling, and give up
        # after two starved answers so the part falls back to reduction.
        if got < want * 0.2:
            starved += 1
            if starved >= 2:
                break
        target = min(target * min(want / got, 4.0), ceiling)
    # AutoRemesher's answers swing (Roosevelt's boots: 1121, 4, 1560, 20
    # quads for one budget). Nearest to the budget among the usable ones; a
    # starved answer (under half the budget) only when nothing else came back,
    # and then the fullest: a part that collapses costs more than one that runs
    # over its budget.
    usable = [m for m in made if m[1] >= want * 0.5]
    if usable:
        best = min(usable, key=lambda m: abs(m[1] - want))
    elif made:
        best = max(made, key=lambda m: m[1])
    else:
        best = None
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


def remesh_fault(part, result, layered, scale):
    """Why a remeshed piece doesn't stand in for the original, or None, plus
    the measure: how far the original's surface lies from the remesh (p95,
    as % of the whole object's size `scale`). A piece that shredded or
    collapsed leaves original surface far from anything (the ring's ropes
    and posts: 4-58%); a smoothed one stays close (the kettle, the baguette
    crust, under 2.5%). A small tear slips under it (the ring's mat in
    "web"): it covers too little of the surface. Not for a
    `layered` object (a character): its cut pieces hold inner layers and
    stray scraps that a remesh rightly drops."""
    if layered:
        return None, None
    off = surface_gap(part, result) / scale * 100
    if off > REMESH_GAP_PCT:
        return "original surface %.1f%% of the size away (p95)" % off, off
    return None, off


def surface_gap(part, result, samples=600):
    """p95 distance from points spread over `part` to the surface of `result`."""
    import bmesh
    import random
    from mathutils.bvhtree import BVHTree
    bm = bmesh.new()
    bm.from_mesh(result.data)
    bm.transform(result.matrix_world)
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    src = bmesh.new()
    src.from_mesh(part.data)
    src.transform(part.matrix_world)
    tris = src.calc_loop_triangles()
    weights = [t[0].face.calc_area() / max(len(t[0].face.verts) - 2, 1) for t in tris]
    rng = random.Random(7)
    gaps = []
    if tris:
        for t in rng.choices(tris, weights=weights, k=samples):
            a, b = rng.random(), rng.random()
            if a + b > 1:
                a, b = 1 - a, 1 - b
            v0, v1, v2 = (l.vert.co for l in t)
            point = v0 + (v1 - v0) * a + (v2 - v0) * b
            hit = tree.find_nearest(point)
            gaps.append(hit[3] if hit[0] is not None else float("inf"))
    src.free()
    if not gaps:
        return 0.0
    gaps.sort()
    return gaps[int(0.95 * (len(gaps) - 1))]


def world_size(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return [max(c[i] for c in corners) - min(c[i] for c in corners) for i in range(3)]


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
                                          "parts": [{"name": p["name"], "min": p["min"], "max": p["max"], "turn": p.get("turn"), "wraps": p.get("wraps")}
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
                result_obj = import_obj(best[0])
                fault, gap = remesh_fault(part, result_obj, params.get("layered", False), max(world_size(source)))
                if fault:
                    # A count in range can still be a wreck (the ring's ropes
                    # came back in fragments): reduce the piece instead.
                    tries.append({"rejected": fault})
                    spare = result_obj.data
                    bpy.data.objects.remove(result_obj, do_unlink=True)
                    bpy.data.meshes.remove(spare)
                    best = None
                else:
                    made.append(result_obj)
                    kind = "remeshed"
                    if gap is not None:
                        tries.append({"gap_pct": round(gap, 2)})
            if best:
                pass
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
            elif not params.get("whole_failed"):
                # AutoRemesher gave nothing for the whole object in one go (it
                # stalls on some meshes, like the fused lizardkin). Part by
                # part usually works; QuadriFlow is the last resort.
                # use_parts brings in Claude's part cuts (parts.json) even for
                # profiles that normally remesh whole: a fused body splits
                # into pieces AutoRemesher can handle.
                result = autoremesh(dict(params, per_part=True, use_parts=True, whole_failed=True))
                result["note"] = "AutoRemesher gave nothing for the whole object (%s); remeshed part by part" % tries
                return result
            else:
                result = run_script("retopo.py", {"target_quads": want})
                result["note"] = "AutoRemesher gave nothing, whole or by piece; used QuadriFlow"
                return result
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
    web viewer can draw the true topology. GLB meshes are always triangles.
    A mesh in groups (body, gear) gets one set of lines per group, tagged the
    same way, so the viewer can hide a gear piece's lines with the piece."""
    import bmesh
    obj = largest_mesh()
    tags = json.loads(obj.get("forge_groups", "[]"))
    masks = json.loads(obj.get("forge_masks", "[[]]")) if obj.data.attributes.get("forge_under") else [[]]
    made = []
    jobs = [(None, None, 0)]
    if len(tags) > 1:  # the body's lines come apart where drape.py hid faces under gear, like its mesh
        jobs = [(index, tag, cut) for index, tag in enumerate(tags) for cut in (range(len(masks)) if tag.get("forge") == "body" else [0])]
    for index, tag, cut in jobs:
        lines = obj.copy()
        lines.data = obj.data.copy()
        lines.modifiers.clear()
        lines.data.materials.clear()
        for key in list(lines.keys()):
            del lines[key]
        for c in obj.users_collection:
            c.objects.link(lines)
        bm = bmesh.new()
        bm.from_mesh(lines.data)
        if tag:
            mark = bm.faces.layers.int.get("forge_group")
            under = bm.faces.layers.int.get("forge_under")
            gone = [f for f in bm.faces if f[mark] != index or (under is not None and tag.get("forge") == "body" and f[under] != cut)]
            if cut and len(gone) == len(bm.faces):
                bm.free()
                bpy.data.objects.remove(lines, do_unlink=True)
                continue
            bmesh.ops.delete(bm, geom=gone, context="FACES")
            lines.name = "lines: " + tag["name"] + (" under: " + " + ".join(masks[cut]) if cut else "")
            for key in ("forge", "gear"):
                if tag.get(key):
                    lines[key] = tag[key]
            if cut:
                lines["under"] = "|".join(masks[cut])
        bmesh.ops.delete(bm, geom=list(bm.faces), context="FACES_ONLY")
        bm.to_mesh(lines.data)
        bm.free()
        made.append(lines)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for lines in made:
        lines.select_set(True)
    bpy.context.view_layer.objects.active = made[0]
    obj.hide_set(True)
    try:
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                                  use_mesh_edges=True, export_materials="NONE", export_extras=True,
                                  export_normals=False, export_texcoords=False)
    finally:
        obj.hide_set(False)
        for lines in made:
            bpy.data.objects.remove(lines, do_unlink=True)


class Skip(Exception):
    pass


def is_character(run_dir):
    path = os.path.join(run_dir, "brief.json")
    if not os.path.exists(path):
        return False
    with open(path) as f:
        return bool(json.load(f).get("character"))


def wants_flat_colors(run_dir):
    """The brief's low-poly style asks for flat colors (old-school RuneScape
    and the like): keep Claude's per-part vertex colors instead of baking a
    texture, which turns muddy at a few hundred triangles."""
    path = os.path.join(run_dir, "brief.json")
    if not os.path.exists(path):
        return False
    with open(path) as f:
        style = (json.load(f).get("lowpoly_style") or "").lower()
    return ("flat" in style and ("color" in style or "colour" in style)) or "vertex color" in style


def color_preview_material(obj):
    """A material that shows the vertex colors in Blender (previews, .blend).
    The GLB is exported without materials, so viewers use the colors as-is."""
    mat = bpy.data.materials.new(obj.name + " flat colors")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    attr = nodes.new("ShaderNodeVertexColor")
    bsdf = nodes["Principled BSDF"]
    mat.node_tree.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    obj.data.materials.clear()
    obj.data.materials.append(mat)


GROUP_KEYS = ("forge", "gear", "kind", "slot", "socket", "socket_of", "forge_build", "under")


def blockout(run_dir):
    """Claude's hand-built low-poly mesh (lowpoly.glb, step 4c), brought in
    as the light mesh to bake onto. Same world space as scene.blend.

    It comes back as one object, which is what the bake, the shape check and
    the previews work on. If the file holds groups (a body and gear) or
    sockets, each face remembers its group and export.py writes them apart
    again."""
    path = os.path.join(run_dir, "lowpoly.glb")
    if not os.path.exists(path):
        raise Skip("no lowpoly.glb yet (just resume asks Claude to block it out)")
    full = largest_mesh()
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    meshes.sort(key=lambda o: (o.get("forge") != "body", bool(o.get("under"))))  # the body first, as build.py lists it
    sockets = [o for o in new if o.type == "EMPTY" and o.get("forge") == "socket"]
    tags, named = [], 0
    for o in meshes:
        # A draped block-out has its body in several meshes ("body under: wool trousers"): one group again here.
        name = "body" if o.get("forge") == "body" else blockout_recipe.tag_name(o)
        named += bool(name)
        if name and name not in [t["name"] for t in tags]:
            tags.append({k: o[k] for k in ("forge", "gear", "kind", "slot") if k in o} | {"name": name})
        index = [t["name"] for t in tags].index(name) if name else len(tags)
        mark = o.data.attributes.new("forge_group", "INT", "FACE")
        mark.data.foreach_set("value", [index] * len(o.data.polygons))
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
    for o in [o for o in bpy.data.objects if o not in before and o is not low and o not in sockets]:
        bpy.data.objects.remove(o, do_unlink=True)
    low.name = full.name + " (light)"
    low.data.materials.clear()
    for key in [k for k in GROUP_KEYS if k in low]:
        del low[key]
    if named == len(meshes):
        low["forge_groups"] = json.dumps(tags)
    for o in sockets:
        o.matrix_world = o.matrix_world.copy()
        o["socket_of"] = low.name
    full.hide_set(True)
    full.hide_render = True
    faces = low.data.polygons
    return {"object": low.name, "faces": len(faces),
            "triangles": sum(len(p.vertices) - 2 for p in faces),
            "quads": sum(1 for p in faces if len(p.vertices) == 4)}


# ---- mid poly: the block-out's recipe, built again with more sides and rings ----

def read_recipe(run_dir):
    """What build.py was given for the block-out: lowpoly_build.json, or the
    copy riding in lowpoly.glb (scripts/blockout_recipe.py explains why)."""
    path = os.path.join(run_dir, "lowpoly_build.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    glb = os.path.join(run_dir, "lowpoly.glb")
    if os.path.exists(glb):
        return blockout_recipe.contents(blockout_recipe.read(glb)[0])["recipe"]
    return None


def rebuild(run_dir, params):
    """The mid-poly mesh: the block-out's own pieces, built again by build.py
    with about 2-4 times the sides and rings and smooth shading, until the
    triangle count is in range. Gear groups and sockets come along as in the
    block-out, the sockets exactly where they were."""
    recipe = read_recipe(run_dir)
    if not recipe:
        raise Skip("no recipe for the block-out (lowpoly_build.json): it was made before recipes were kept; "
                   "`just recipe <run>` gets one back from the transcript, or delete lowpoly.glb and `just resume` to block it out again")
    full = largest_mesh()
    size = max(full.dimensions)
    for name, scan in recipe.get("scans", {}).items():
        bpy.context.scene["face: " + name] = json.dumps(scan)
    low, high = params.get("triangles", [3000, 8000])
    level, tried, result = 1, [], None
    while True:
        sides, rings = blockout_recipe.DENSER[level]
        result = run_script("build.py", {
            "reference": full.name, "check": 0, "shading": "smooth", "crease": params.get("crease", 40),
            "parts": [blockout_recipe.denser(p, sides, rings, size) for p in recipe["pieces"]],
            "gear": recipe.get("gear") or [], "sockets": recipe.get("sockets") or False,
        })
        tried.append({"sides": sides, "rings": rings, "triangles": result["triangles"]})
        went = [t["triangles"] for t in tried]
        if result["triangles"] < low and level + 1 < len(blockout_recipe.DENSER) and max(went) < low:
            level += 1
        elif result["triangles"] > high and level > 0 and min(went) > high:
            level -= 1
        else:
            break
    full.hide_set(True)
    full.hide_render = True
    made = bpy.data.objects[result["object"]]
    del made["forge_build"]  # the denser recipe has no reader; keep it out of the .glb
    faces = made.data.polygons
    return {"object": result["object"], "faces": len(faces), "triangles": result["triangles"],
            "quads": sum(1 for p in faces if len(p.vertices) == 4),
            "pieces": len(recipe["pieces"]),
            "tried": tried, "groups": [g["name"] for g in result.get("groups", [])], "sockets": result.get("sockets")}


def drape(run_dir, name):
    """Lay the block-out's clothes on its body and mark the body faces they hide (drape.py), for a
    block-out that has gear. The recipe, where there is one, gives each part its piece's name and "fit"."""
    low = bpy.data.objects[name]
    tags = json.loads(low.get("forge_groups", "[]"))
    if len(tags) < 2 or tags[0].get("forge") != "body":
        return None
    recipe = read_recipe(run_dir)
    return run_script("drape.py", {"object": name, "pieces": recipe["pieces"] if recipe else None})


def read_plan(source):
    """The run's parts.json (Claude's part boxes), if it has one."""
    path = os.path.join(os.path.dirname(source), "parts.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def walk(source, out_dir, profile, spec):
    """Each block-out version in OUT_DIR again, with a skeleton, joint limits and a walk that fits the build."""
    run_dir = os.path.dirname(source)
    traits = None
    if os.path.exists(os.path.join(run_dir, "gait.json")):
        with open(os.path.join(run_dir, "gait.json")) as f:
            said = json.load(f)
        traits = {k: said[k] for k in ("weight", "stealth", "swagger", "stiffness") if isinstance(said.get(k), (int, float))}
    recipe = read_recipe(run_dir)
    versions = [v for v in spec["of"] if os.path.exists(os.path.join(out_dir, v + ".glb"))]
    if not versions:
        raise Skip("no %s in %s yet: the walk is added to those" % (" or ".join(v + ".glb" for v in spec["of"]), out_dir))
    for version in versions:
        started = time.time()
        made = {}
        if os.path.exists(os.path.join(out_dir, version + ".json")):
            with open(os.path.join(out_dir, version + ".json")) as f:
                made = json.load(f)
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=os.path.join(out_dir, version + ".glb"))
        name = version + "-walk"
        record = {"profile": name, "about": spec["about"], "source": os.path.join(out_dir, version + ".glb"), "of": version}
        dressed = any(o.type == "MESH" and o.get("forge") == "gear" for o in bpy.context.scene.objects)
        if dressed:  # clothes onto the body (a version draped when it was made is only read), and the faces they hide
            record["drape"] = run_script("drape.py", {"pieces": recipe["pieces"] if recipe else None, "rings": False})
        try:
            record["rig"] = run_script("rig.py", dict(spec.get("rig", {}), recipe=recipe["pieces"] if recipe else None))
        except ValueError as why:  # not a T-pose character: nothing to fit a skeleton to
            raise Skip(str(why))
        if dressed:  # clothes take the body's weights; loose cloth gets bones to hang from
            record["cloth"] = run_script("cloth.py", spec.get("cloth", {}))
        record["walk"] = run_script("walk.py", dict(spec.get("walk", {}), traits=traits or None))
        record["animation"] = run_script("animate.py", spec.get("animate", {}))
        for script in record["animation"].get("then", []):  # what the rig asks for after a bake: swing.py, for cloth bones
            record[script[:-3]] = run_script(script, spec.get(script[:-3], {}))
        glb = os.path.join(out_dir, name + ".glb")
        record["export"] = run_script("export.py", dict(spec["export"], rig=True, path=glb, materials=not made.get("flat_colors")))
        doc, rest = blockout_recipe.read(glb)
        if blockout_recipe.tidy_names(doc):
            blockout_recipe.write(glb, doc, rest)
        record["gear"], record["sockets"] = made.get("gear") or [], made.get("sockets") or []
        record["bytes"] = os.path.getsize(glb)
        record["seconds"] = round(time.time() - started, 1)
        with open(os.path.join(out_dir, name + ".json"), "w") as f:
            json.dump(record, f, indent=2)
        gait, check = record["walk"]["gait"], record["animation"]["check"]
        cloth = len((record.get("cloth") or {}).get("cloth_bones") or [])
        print("PROFILE %s: %d bones%s, %s weights, %.2f m/s at %d steps a minute, feet slide %.2f cm a step, %.2f MB, %.0fs -> %s" % (
            name, len(record["rig"]["bones"]), " and %d for loose cloth" % cloth if cloth else "", record["rig"]["weights"], gait["speed_m_s"],
            gait["cadence_steps_per_min"], check["foot_slide_cm_per_step"], record["bytes"] / 1e6, record["seconds"], glb))


def running(source, out_dir, profile, spec):
    """Each block-out version in OUT_DIR again, with a skeleton and the run cut from this character's clip (run/loop.json)."""
    run_dir = os.path.dirname(source)
    loop_file = os.path.join(run_dir, "run", "loop.json")
    if not os.path.exists(loop_file):
        # Not a failure: the clip comes from Kimodo on the motion worker, and that may not be reachable (yet).
        print("PROFILE run skipped: Kimodo not available (no run clip at %s; `just runs` makes it once the motion worker can reach Kimodo)" % loop_file)
        return None
    sys.path.insert(0, os.path.join(ROOT, "scripts", "motion"))
    import apply_motion
    import run_clip
    from soma import Skeleton
    with open(loop_file) as f:
        loop = json.load(f)
    plain, converted = run_clip.loop_to_plain(loop, Skeleton.load(), spec["clip"])
    ask = {}
    if os.path.exists(os.path.join(run_dir, "run", "ask.json")):
        with open(os.path.join(run_dir, "run", "ask.json")) as f:
            ask = json.load(f)
    recipe = read_recipe(run_dir)
    versions = [v for v in spec["of"] if os.path.exists(os.path.join(out_dir, v + ".glb"))]
    if not versions:
        raise Skip("no %s in %s yet: the run is added to those" % (" or ".join(v + ".glb" for v in spec["of"]), out_dir))
    cut = ("prompt", "made_by", "frames", "seconds", "strides", "stride_frames", "steps_per_minute", "first_frame", "last_frame", "blend_frames", "seam_before_blend")
    for version in versions:
        started = time.time()
        made = {}
        if os.path.exists(os.path.join(out_dir, version + ".json")):
            with open(os.path.join(out_dir, version + ".json")) as f:
                made = json.load(f)
        name = "%s-%s" % (version, spec["clip"])
        record = {"profile": name, "about": spec["about"], "source": os.path.join(out_dir, version + ".glb"), "of": version,
                  "clip": {k: loop["loop"].get(k) for k in cut}, "from_soma": converted}
        try:  # the shared steps: clothes, skeleton, the motion fitted and baked, loose cloth swung
            record.update(apply_motion.fit(record["source"], plain, spec["clip"], recipe, spec, tail=True, echo=print))
        except ValueError as why:  # not a T-pose character: nothing to fit a skeleton to
            raise Skip(str(why))
        glb = os.path.join(out_dir, name + ".glb")
        apply_motion.write(record, glb, materials=not made.get("flat_colors"), export=spec["export"], echo=print)
        moved, check = record["animation"], record["animation"]["check"]
        # What the gallery says about it, in one place: how fast, how many steps, and the sentence it came from.
        record["run"] = {"speed_m_s": moved["speed_m_s"], "steps_per_minute": loop["loop"]["steps_per_minute"], "loop_s": moved["seconds"],
                         "frames": moved["frames"], "asked_speed_m_s": ask.get("speed_mps"), "froude": ask.get("froude"), "prompt": loop["loop"].get("prompt")}
        record["gear"], record["sockets"] = made.get("gear") or [], made.get("sockets") or []
        record["seconds"] = round(time.time() - started, 1)
        with open(os.path.join(out_dir, name + ".json"), "w") as f:
            json.dump(record, f, indent=2)
        cloth = len((record.get("cloth") or {}).get("cloth_bones") or [])
        print("PROFILE %s: %d bones%s, runs %.2f m/s at %d steps a minute, a loop of %d frames, feet slide %.2f cm a step, %d turns outside a limit, seam %s, %.2f MB, %.0fs -> %s" % (
            name, len(record["rig"]["bones"]), " and %d for loose cloth" % cloth if cloth else "", moved["speed_m_s"], loop["loop"]["steps_per_minute"],
            moved["frames"], check["foot_slide_cm_per_step"], check["limit_violations"], check["loop_seam"], record["bytes"] / 1e6, record["seconds"], glb))


def make(source, out_dir, profile, spec):
    if spec.get("clip"):
        return running(source, out_dir, profile, spec)
    if spec.get("of"):
        return walk(source, out_dir, profile, spec)
    started = time.time()
    load(source)
    record = {"profile": profile, "about": spec["about"], "source": source, "steps": []}
    if spec.get("flat_colors") and wants_flat_colors(os.path.dirname(source)):
        spec = dict(spec, **spec["flat_colors"])
        record["about"] = spec.get("about", record["about"])
        record["flat_colors"] = True
    plan = read_plan(source)
    if plan.get("parts"):
        record["parts"] = [p["name"] for p in plan["parts"]]
    for name, params in spec["steps"]:
        if name == "autoremesher":
            result = autoremesh(dict(params, parts_plan=plan, layered=is_character(os.path.dirname(source))))
        elif name == "blockout":
            result = blockout(os.path.dirname(source))
            if params.get("keep_colors"):
                color_preview_material(bpy.data.objects[result["object"]])
        elif name == "rebuild":
            result = rebuild(os.path.dirname(source), params)
        elif name == "bake.py" and plan.get("parts"):  # the part boxes say where a kilt or a shirt is on the detailed mesh
            result = run_script(name, dict(params, parts=plan["parts"]))
        else:
            result = run_script(name, params)
        record["steps"].append({"script": name, "result": result})
        if name in ("blockout", "rebuild"):  # before the bake, so the texture lands on the clothes where they end up
            draped = drape(os.path.dirname(source), result["object"])
            if draped:
                record["steps"].append({"script": "drape.py", "result": draped})
                record["drape"] = {k: draped[k] for k in ("gap_where_it_touches_cm", "points_inside_the_body", "rings_added", "triangles", "masks")}
    light = [n for n, _ in spec["steps"]]
    built = {"blockout", "rebuild"} & set(light)
    if {"retopo.py", "autoremesher"} & set(light) or built or any(p.get("as_copy") for _, p in spec["steps"]):
        record["shape"] = run_script("match.py", {})
    if built:
        low = largest_mesh()
        baked = next((s["result"] for s in record["steps"] if s["script"] == "bake.py"), None)
        if baked and baked.get("groups"):
            # bake.py baked by group: gear copied cloth, the body skin, and the skin under a
            # piece of gear has the body's own average color (not a copy of the coat over it).
            record["by_group"] = {k: baked[k] for k in ("groups", "faces_hidden_under_another_piece", "found_by_part_boxes")}
        # A later step that repaints part of the texture (a face, say) goes here: after the
        # bake, before the painted colors go and the file is written.
        if baked and not record.get("flat_colors"):
            # The texture has taken over from the painted colors. Left on the
            # mesh they would go into the .glb, where viewers multiply them
            # into the texture and darken it.
            for paint in list(low.data.color_attributes):
                low.data.color_attributes.remove(paint)
        # What the gallery offers to show and hide.
        record["gear"] = [{k: g.get(k) for k in ("gear", "kind", "slot")} for g in json.loads(low.get("forge_groups", "[]")) if g.get("gear")]
        record["sockets"] = sorted(o["socket"] for o in bpy.context.scene.objects if o.get("socket_of") == low.name)
    glb = os.path.join(out_dir, profile + ".glb")
    record["export"] = run_script("export.py", dict(spec["export"], path=glb))
    if built:
        # Blender keeps names unique across the file, so a scene that already
        # had a "body" would write "body.001"; the tags say what each node is.
        doc, rest = blockout_recipe.read(glb)
        if blockout_recipe.tidy_names(doc):
            blockout_recipe.write(glb, doc, rest)
    if {"autoremesher", "retopo.py"} & set(light) or built:
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
    return record


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
if not os.path.exists(raw) and any(not profiles[p].get("of") for p in wanted):
    load(source)
    run_script("export.py", {"path": raw, "image_format": "WEBP", "draco": False})
def worst_off(record):
    return ((record or {}).get("shape") or {}).get("shape_lost", {}).get("max_%", 0.0)


def make_best(source, out_dir, profile, spec):
    """Make the profile; when a profile that remeshes whole (use_parts false)
    comes out badly off and Claude cut the object into parts, build it part
    by part too and keep whichever is closer. Whole is usually better at a
    few thousand quads (the kettle), but it dissolves thin separate pieces
    (the wrestling ring's ropes: 23% off)."""
    record = make(source, out_dir, profile, spec)
    whole = [p for n, p in spec.get("steps", []) if n == "autoremesher" and p.get("use_parts") is False]
    if not whole or worst_off(record) <= RETRY_PARTS_OFF or not read_plan(source).get("parts"):
        return record
    print("PROFILE %s: %.1f%% off remeshed whole; trying part by part" % (profile, worst_off(record)))
    trial = tempfile.mkdtemp(prefix="forge-%s-parts-" % profile)
    try:
        steps = [[n, dict(p, use_parts=True) if n == "autoremesher" else p] for n, p in spec["steps"]]
        other = make(source, trial, profile, dict(spec, steps=steps))
        keep = worst_off(other) < worst_off(record)
        if keep:
            for name in os.listdir(trial):
                os.replace(os.path.join(trial, name), os.path.join(out_dir, name))
        kept = other if keep else record
        kept["tried"] = {"whole": worst_off(record), "part by part": worst_off(other),
                         "kept": "part by part" if keep else "whole"}
        with open(os.path.join(out_dir, profile + ".json"), "w") as f:
            json.dump(kept, f, indent=2)
        print("PROFILE %s: kept %s (whole %.1f%%, part by part %.1f%% off)" % (
            profile, kept["tried"]["kept"], worst_off(record), worst_off(other)))
        return kept
    finally:
        shutil.rmtree(trial, ignore_errors=True)


for profile in wanted:
    try:
        make_best(source, out_dir, profile, profiles[profile])
    except Skip as why:
        print("PROFILE %s: skipped, %s" % (profile, why))
