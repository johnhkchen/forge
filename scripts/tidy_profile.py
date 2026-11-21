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


HEAD_PART = "head, whole"  # the name of the piece a character's head is cut off as
HEAD_SHARE = 0.12  # and the least share of the quads it gets
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
    # The other answers, nearest the budget first, for when the best one turns out torn (remesh_fault).
    spare = sorted([m for m in usable if m is not best and m[1] <= want * 3], key=lambda m: abs(m[1] - want))
    return best, tries, spare


def export_obj(obj, path):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True, apply_modifiers=True,
                          export_materials=False, export_uv=False, export_normals=False,
                          export_triangulated_mesh=True, forward_axis="Y", up_axis="Z")


# A remesh is torn when more than this share of what shows of the original has no remeshed surface within
# this reach: [reach as % of the object's size, share %]. Small holes all over, or a few big ones. On
# Lincoln's pieces, sound remeshes lose 0-6% at 0.5% and 0-2% at 1%; his torn head and hair 20-70% and 7-50%.
TORN = [(0.5, 15.0), (1.0, 4.0)]
HEAD_TORN = [(0.5, 8.0), (1.0, 1.5)]  # for a character's head: 4% of it at 1% is the chin


def remesh_fault(part, result, layered, scale, outside=None, allowed=None):
    """Why a remeshed piece doesn't stand in for the original, or None, plus
    the measures. Two ways to fail:

    - The original's surface lies far from the remesh (p95, as % of the whole
      object's size `scale`): a piece that shredded or collapsed (the ring's
      ropes and posts: 4-58%; the kettle, the baguette crust, under 2.5%).
      Not asked of a `layered` object (a character): its cut pieces hold
      inner layers and stray scraps that a remesh rightly drops.
    - It is torn: too much of what shows from outside has nothing near it.
      This is what happened to faces. A character's head came back with
      holes where the hair, brow and cheeks were (27-95% of the head's front
      on six characters), and the first test never saw it: it was off for
      characters, and a hole a few centimeters across is close to its own
      rim anyway. `outside` is the whole object's surface, to tell which
      points show: nothing in the way, straight out."""
    gaps = surface_gaps(part, result, outside)
    if not gaps:
        return None, {}
    far = sorted(g for g, _ in gaps)
    off = far[int(0.95 * (len(far) - 1))] / scale * 100
    shown = [g for g, seen in gaps if seen]
    measures = {"gap_pct": round(off, 2)}
    if not layered and off > REMESH_GAP_PCT:
        return "original surface %.1f%% of the size away (p95)" % off, measures
    if outside is not None and len(shown) >= 30:
        measures["torn_pct"] = []
        for reach, most in allowed or TORN:
            torn = 100.0 * sum(1 for g in shown if g > reach / 100 * scale) / len(shown)
            measures["torn_pct"].append(round(torn, 1))
            if torn > most:
                return "torn: %.0f%% of what shows has no surface within %.1f%% of the size" % (torn, reach), measures
    return None, measures


def surface_tree(obj):
    import bmesh
    from mathutils.bvhtree import BVHTree
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    return tree


def surface_gaps(part, result, outside=None, samples=600):
    """For points spread over `part`: (distance to the surface of `result`, does the point show from outside)."""
    import bmesh
    import random
    tree = surface_tree(result)
    src = bmesh.new()
    src.from_mesh(part.data)
    src.transform(part.matrix_world)
    tris = src.calc_loop_triangles()
    weights = [t[0].face.calc_area() / max(len(t[0].face.verts) - 2, 1) for t in tris]
    rng = random.Random(7)
    gaps = []
    if tris and sum(weights) > 0:
        for t in rng.choices(tris, weights=weights, k=samples):
            a, b = rng.random(), rng.random()
            if a + b > 1:
                a, b = 1 - a, 1 - b
            v0, v1, v2 = (l.vert.co for l in t)
            point = v0 + (v1 - v0) * a + (v2 - v0) * b
            hit = tree.find_nearest(point)
            normal = t[0].face.normal
            # Shows from outside: nothing in the way straight out. TRELLIS winds some faces backwards, so either way out counts.
            seen = outside is None or None in (outside.ray_cast(point + normal * 1e-4, normal)[0], outside.ray_cast(point - normal * 1e-4, -normal)[0])
            gaps.append((hit[3] if hit[0] is not None else float("inf"), seen))
    src.free()
    return gaps


def drop_object(obj):
    old = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(old)


def accept(part, answers, tries, layered, scale, outside, allowed=None):
    """The first of AutoRemesher's answers [(file, quads)] that stands in for `part`, brought in as an object, or None.
    A count in range can still be a wreck (the ring's ropes came back in fragments, a character's head with holes in it)."""
    for path, quads in answers:
        result = import_obj(path)
        fault, measures = remesh_fault(part, result, layered, scale, outside, allowed or TORN)
        if not fault:
            if measures:
                tries.append(measures)
            return result
        tries.append({"rejected": fault, "quads": quads})
        drop_object(result)
    return None


def apply_modifier(obj, mod):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


def triangle_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def reduce(obj, budget):
    """Bring a piece down to about `budget` quads' worth of triangles. Decimate can't touch a tangled piece
    (the pinhole camera's spout: 25,000 faces on 7,900 points, edges shared by three or more faces) and hands
    it back as it was; then the piece is wrapped in a clean skin first and that is reduced."""
    want = budget * 2
    mod = obj.modifiers.new("Decimate", "DECIMATE")
    mod.ratio = min(1.0, want / max(triangle_count(obj), 1))
    apply_modifier(obj, mod)
    if triangle_count(obj) <= max(want * 4, 400):
        return
    skin = wrapped(obj, max(world_size(obj)))
    if skin is None:
        return
    old = obj.data
    obj.data = skin.data
    obj.matrix_world = skin.matrix_world.copy()  # the skin has the piece's turn and scale applied
    bpy.data.objects.remove(skin, do_unlink=True)
    if old.users == 0:
        bpy.data.meshes.remove(old)
    mod = obj.modifiers.new("Decimate", "DECIMATE")
    mod.ratio = min(1.0, want / max(triangle_count(obj), 1))
    apply_modifier(obj, mod)


def wrapped(part, scale):
    """A copy of the piece as one closed skin around everything in it (a voxel remesh, cells 1/150 of the
    piece's size, between 0.1% and 0.5% of the object's), or None if nothing came of it. Larger cells than
    that round a cut edge off by a centimeter. (Blender's QuadriFlow would make even quads of such a skin,
    and was tried for heads: on some it never returns, and nothing can stop it from in here.)"""
    wrap = part.copy()
    wrap.data = part.data.copy()
    wrap.modifiers.clear()
    for c in part.users_collection:
        c.objects.link(wrap)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    wrap.hide_set(False)
    wrap.select_set(True)
    bpy.context.view_layer.objects.active = wrap
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    wrap.data.remesh_voxel_size = min(max(max(world_size(part)) / 150, scale * 0.001), scale * 0.005)
    wrap.data.use_remesh_fix_poles = True
    bpy.ops.object.voxel_remesh()
    triangles = sum(len(p.vertices) - 2 for p in wrap.data.polygons)
    if triangles > 200000:  # more than a remesher needs to read, and slow for it and for what follows here
        mod = wrap.modifiers.new("Decimate", "DECIMATE")
        mod.ratio = 200000 / triangles
        apply_modifier(wrap, mod)
    # A skin around layers leaves closed pockets inside (behind the lips, under the hair): keep the outer shells.
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(wrap.data)
    left, shells = set(bm.faces), []
    while left:
        shell, edge = set(), [left.pop()]
        while edge:
            f = edge.pop()
            shell.add(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g in left:
                        left.discard(g)
                        edge.append(g)
        shells.append(shell)
    most = max((len(sh) for sh in shells), default=0)
    small = [f for sh in shells if len(sh) < 0.05 * most for f in sh]
    if small:
        bmesh.ops.delete(bm, geom=small, context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        bm.to_mesh(wrap.data)
    bm.free()
    if len(wrap.data.polygons) < 20:
        drop_object(wrap)
        return None
    return wrap


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
    cuts = [{"name": p["name"], "min": p["min"], "max": p["max"], "turn": p.get("turn"), "wraps": p.get("wraps")} for p in plan.get("parts") or []]
    head = params.get("head")
    if head:
        # A character's head is one piece, whatever else is cut: everything from the chin up, hair and hat
        # with it. Cut along the hairline (Claude's "hair" part) the face came back with holes at the brow.
        # Listed first, so it takes its faces before any other part's box does.
        lo, hi = head["min"], head["max"]
        pad = [0.4 * (hi[0] - lo[0]), 0.4 * (hi[1] - lo[1])]
        # (the cut sits a quarter of a head down the neck: along the jaw it shows, and a short stump of neck
        # left on the body is the first thing a coarse remesh rounds away, which leaves the head floating)
        cuts.insert(0, {"name": HEAD_PART, "min": [lo[0] - pad[0], lo[1] - pad[1], lo[2] - 0.25 * (hi[2] - lo[2])],
                        "max": [hi[0] + pad[0], hi[1] + pad[1], hi[2] + max(world_size(source))]})
    head_piece = None
    try:
        if cuts:
            # Cut the parts Claude found (split.py), then treat every piece
            # (cut parts and already-separate ones) as its own remesh.
            cut = run_script("split.py", {"object": source.name, "mode": "split", "parts": cuts})
            pieces = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith(source.name + " · ")]
            head_piece = next((o for o in pieces if o.name == source.name + " · " + HEAD_PART), None)
            if head_piece and len(pieces) > 1:
                pieces.remove(head_piece)
            else:
                head_piece = None
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
            if head_piece:
                parts.insert(0, head_piece)
            params = dict(params, per_part=True, cut=cut)
        if params.get("per_part", False):
            parts = parts if cuts else split_parts(source)
            # Budgets grow slower than area, so thin parts (a strap, a pin)
            # aren't starved next to a big body.
            areas = {p.name: area(p) ** 0.75 for p in parts}
            total = sum(areas.values()) or 1.0
            if head_piece and areas[head_piece.name] < HEAD_SHARE * total:  # a face is looked at more than a shin
                rest = total - areas[head_piece.name]
                areas[head_piece.name] = HEAD_SHARE * rest / (1 - HEAD_SHARE)
                total = rest + areas[head_piece.name]
            floor = params.get("min_part_quads", 60)
        else:
            parts, areas, total, floor = [source], {source.name: 1.0}, 1.0, 0
        results, made = [], []
        outside = surface_tree(source)  # what shows, to tell a torn remesh from one that dropped inner layers
        for i, part in enumerate(parts):
            budget = max(floor, int(want * areas[part.name] / total))
            mesh_in = os.path.join(work, "part%d.obj" % i)
            size = max(world_size(source))
            layered = params.get("layered", False)
            best, tries, kind, answers = None, [], "remeshed", []
            is_head = part is head_piece
            if not is_head:  # a head goes straight to the wrap: it is layers all through (hair, lids, lips, teeth)
                export_obj(part, mesh_in)
                best, tries, spare = remesh_file(mesh_in, work, "part%d" % i, budget, params)
                answers = [best] + spare if best else []
                best = accept(part, answers, tries, layered, size, outside)
            if not best and part is not source and (is_head or any("torn" in t.get("rejected", "") for t in tries)):
                # Torn every time: the piece is layers and scraps AutoRemesher can't stitch (hair over a
                # skull, a face cut open at the hairline). Wrap it in one skin, and remesh that. A head's
                # answer is held to less loss (HEAD_TORN): the usual allowance is a chin's worth of a head.
                wrap = wrapped(part, size)
                if wrap:
                    export_obj(wrap, mesh_in)
                    again, more, spare = remesh_file(mesh_in, work, "part%dw" % i, budget, params)
                    tries += more
                    best = accept(part, [again] + spare if again else [], tries, layered, size, outside, HEAD_TORN if is_head else TORN)
                    kind = "wrapped, remeshed"
                    if not best:  # the skin itself, reduced and paired into quads where its triangles line up: whole, if less regular
                        reduce(wrap, budget)
                        bpy.ops.object.mode_set(mode="EDIT")
                        bpy.ops.mesh.select_all(action="SELECT")
                        bpy.ops.mesh.tris_convert_to_quads()
                        bpy.ops.object.mode_set(mode="OBJECT")
                        best, kind = wrap, "wrapped (reduced)"
                        if not is_head and len(wrap.data.polygons) > 6 * budget and answers:
                            # A piece that is a cloud of scraps wraps into hundreds of blobs, and no blob reduces
                            # below a few faces (Lincoln's shirt fringe: 9,400 faces on a budget of 216).
                            # There a torn remesh is the lesser evil: it is scraps either way.
                            drop_object(wrap)
                            best = accept(part, answers[:1], tries, layered, size, None)
                            kind = "remeshed (torn, but its wrap would not reduce)"
                    else:
                        drop_object(wrap)
            if best:
                made.append(best)
            elif part is not source:
                # AutoRemesher gave nothing (tiny or degenerate piece): keep it,
                # reduced, rather than lose it.
                reduce(part, budget)
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
            results.append({"share": round(areas[part.name] / total, 4), "budget": budget, "result": kind, "faces": len(made[-1].data.polygons), "tries": tries}
                           | ({"part": "head"} if part is head_piece else {}))
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
    # Asked for in so many words, and no texture wanted. "Flat-shaded ... soft
    # colors ... face painted into a small texture" (the villager) is a
    # textured style: matching "flat" and "color" anywhere left its face blank.
    explicit = any(p in style for p in ("flat color", "flat colour", "flat painted", "vertex color", "vertex colour",
                                        "painted per face", "per-face color", "per-face colour", "painted in flat",
                                        "painted flat", "no texture"))
    textured = "texture" in style.replace("no texture", "")
    return explicit and not textured


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


def paint_face(run_dir):
    """A character's face, painted onto the detailed mesh from a picture of it (face_paint.py) before anything is
    baked, so every version made here carries it: TRELLIS leaves eyes and lips as smudges. The head sheet
    (heads/sheet.png, pipeline step 2b) when the run has one, since it shows the face several times larger; else, or
    if the sheet doesn't sit on this head, the picture the mesh was made from. The head's box is the block-out's
    own head piece when there is a recipe. Returns face_paint.py's result, or None for anything but a character."""
    if not is_character(run_dir):
        return None
    box = None
    recipe = read_recipe(run_dir)
    heads = [p for p in (recipe or {}).get("pieces", []) if "head" in p and p.get("box")]
    if heads:
        box = heads[0]["box"]
    tried = []
    for picture, panel in ((os.path.join(run_dir, "heads", "sheet.png"), "front"), (os.path.join(run_dir, "image.png"), None)):
        if not os.path.exists(picture):
            continue
        try:
            result = run_script("face_paint.py", {"picture": picture, "panel": panel, "box": box})
        except ValueError as why:  # no head found, no figure in the picture
            result = {"painted": False, "why": str(why), "picture": picture}
        if result.get("painted"):
            result["passed_over"] = tried
            return result
        tried.append({"picture": os.path.basename(picture), "fit": result.get("fit"), "why": result.get("why")})
    return {"painted": False, "tried": tried} if tried else None


HEAD_TEXTURE = {256: 256, 512: 256, 1024: 512, 2048: 1024}  # the object's texture size -> the head's own


def head_texture(full_name, low_name, box, params):
    """A texture of its own for the head, after the main bake. One texture shared by a whole character gives
    the head a few percent of it (Lincoln's face: about 60 pixels across at 1024), and no eye survives that.
    So the head's faces are taken off as an object of their own, baked onto by the same bake.py with the same
    settings at half the size (which is five or more times the pixels across a face), and joined back: one mesh
    again, two materials. `box` is the head's box, as face_paint.py used it."""
    import bmesh
    low = bpy.data.objects[low_name]
    lo, hi = box["min"], box["max"]
    pad = [0.15 * (hi[i] - lo[i]) for i in range(3)]
    me = low.data
    world = low.matrix_world
    inside = [all(lo[i] - pad[i] <= (world @ v.co)[i] <= hi[i] + (pad[i] if i < 2 else 1e9) for i in range(3)) for v in me.vertices]
    picked = [all(inside[i] for i in p.vertices) for p in me.polygons]
    if sum(picked) < 8 or sum(picked) > 0.6 * len(picked):
        return {"made": False, "why": "the head's box holds %d of %d faces" % (sum(picked), len(picked))}
    seam = set()  # points on the cut, to weld again after the join
    for p in me.polygons:
        if not picked[p.index]:
            seam.update(i for i in p.vertices if inside[i])
    seam = [tuple(round(c, 6) for c in me.vertices[i].co) for i in seam]
    for o in bpy.context.selected_objects:
        o.select_set(False)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    for p in me.polygons:
        p.select = picked[p.index]
    before = set(bpy.data.objects)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.separate(type="SELECTED")
    bpy.ops.object.mode_set(mode="OBJECT")
    head = next(o for o in bpy.data.objects if o not in before)
    head.name = full_name + " (head)"
    for key in list(head.keys()):  # the group tags stay with the body it rejoins
        del head[key]
    size = HEAD_TEXTURE.get(params.get("texture_size", 1024), 512)
    baked = run_script("bake.py", dict(params, object=full_name, target=head.name, texture_size=size))
    for o in bpy.context.selected_objects:
        o.select_set(False)
    head.hide_set(False)
    low.hide_set(False)
    head.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.join()
    spots = set(seam)
    bm = bmesh.new()
    bm.from_mesh(low.data)
    cut = [v for v in bm.verts if tuple(round(c, 6) for c in v.co) in spots]
    bmesh.ops.remove_doubles(bm, verts=cut, dist=1e-6)
    bm.to_mesh(low.data)
    bm.free()
    return {"made": True, "faces": sum(picked), "texture_size": size, "maps": baked["maps"]}


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
    face = paint_face(os.path.dirname(source))
    if face:
        record["face"] = face
    for name, params in spec["steps"]:
        if name == "autoremesher":
            # The head's box is trusted when the block-out gave it, or when a picture of the face fitted in it.
            sure = face and face.get("box") and (face.get("painted") or face.get("box_by") == "given")
            result = autoremesh(dict(params, parts_plan=plan, layered=is_character(os.path.dirname(source)), head=face["box"] if sure else None))
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
        if name == "bake.py" and params.get("mode") == "onto" and face and face.get("box"):
            # A character's head, baked again on a texture of its own: see head_texture.
            face["head_texture"] = head_texture(result["object"].rsplit(" (", 1)[0], result["object"], face["box"], params)
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
