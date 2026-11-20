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
("body", "gear: wool singlet"...) and an empty per attachment point.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import bpy

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
    made = []
    for index, tag in enumerate(tags if len(tags) > 1 else [None]):
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
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f[mark] != index], context="FACES")
            lines.name = "lines: " + tag["name"]
            for key in ("forge", "gear"):
                if tag.get(key):
                    lines[key] = tag[key]
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


GROUP_KEYS = ("forge", "gear", "kind", "slot", "socket", "socket_of", "forge_build")


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
    meshes.sort(key=lambda o: o.get("forge") != "body")  # the body first, as build.py lists it
    sockets = [o for o in new if o.type == "EMPTY" and o.get("forge") == "socket"]
    tags = []
    for index, o in enumerate(meshes):
        name = blockout_recipe.tag_name(o)
        if name:
            tags.append({k: o[k] for k in ("forge", "gear", "kind", "slot") if k in o} | {"name": name})
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
    if len(tags) == len(meshes):
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


def skin_under_gear(low):
    """After a bake, the body under a coat is painted like the coat: the bake
    copies whatever the detailed mesh shows there. So body faces that gear
    covers get a plain material in the color Claude gave the piece instead.
    Take the gear off and there is skin, not a second coat."""
    from mathutils.bvhtree import BVHTree
    tags = json.loads(low.get("forge_groups", "[]"))
    if len(tags) < 2 or tags[0].get("forge") != "body":
        return None
    me = low.data
    marks = [0] * len(me.polygons)
    me.attributes["forge_group"].data.foreach_get("value", marks)
    gear = [tuple(p.vertices) for p in me.polygons if marks[p.index]]
    tree = BVHTree.FromPolygons([tuple(v.co) for v in me.vertices], gear)
    reach = max(low.dimensions) * 0.04
    paint = me.color_attributes[0] if me.color_attributes else None
    slots, covered = {}, 0
    for p in me.polygons:
        if marks[p.index] or tree.ray_cast(p.center + p.normal * 1e-4, p.normal, reach)[0] is None:
            continue
        color = (0.6, 0.6, 0.6)
        if paint:
            at = p.loop_start if paint.domain == "CORNER" else p.vertices[0]
            color = tuple(round(c, 2) for c in paint.data[at].color[:3])
        if color not in slots:
            mat = bpy.data.materials.new("under the gear %d" % (len(slots) + 1))
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes["Principled BSDF"]
            bsdf.inputs["Base Color"].default_value = color + (1.0,)
            bsdf.inputs["Roughness"].default_value = 0.85
            me.materials.append(mat)
            slots[color] = len(me.materials) - 1
        p.material_index = slots[color]
        covered += 1
    return {"body_faces_under_gear": covered, "plain_colors": len(slots)}


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
    if spec.get("flat_colors") and wants_flat_colors(os.path.dirname(source)):
        spec = dict(spec, **spec["flat_colors"])
        record["about"] = spec.get("about", record["about"])
        record["flat_colors"] = True
    plan = read_plan(source)
    if plan.get("parts"):
        record["parts"] = [p["name"] for p in plan["parts"]]
    for name, params in spec["steps"]:
        if name == "autoremesher":
            result = autoremesh(dict(params, parts_plan=plan))
        elif name == "blockout":
            result = blockout(os.path.dirname(source))
            if params.get("keep_colors"):
                color_preview_material(bpy.data.objects[result["object"]])
        elif name == "rebuild":
            result = rebuild(os.path.dirname(source), params)
        else:
            result = run_script(name, params)
        record["steps"].append({"script": name, "result": result})
    light = [n for n, _ in spec["steps"]]
    built = {"blockout", "rebuild"} & set(light)
    if {"retopo.py", "autoremesher"} & set(light) or built or any(p.get("as_copy") for _, p in spec["steps"]):
        record["shape"] = run_script("match.py", {})
    if built:
        low = largest_mesh()
        if "bake.py" in light:
            record["under_gear"] = skin_under_gear(low)
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
