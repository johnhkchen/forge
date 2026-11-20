"""Try the Blender tools against real runs, in a background Blender.

    python3 scripts/test_tools.py [RUNS_DIR] [--only NAME] [--keep DIR]

RUNS_DIR (default: runs) must hold the cave-troll and iron-kettle runs (the
base-body cases also use the flamenco-dancer runs when they are there). The
live Blender is never touched: every case starts its own `blender -b`, loads
a run's file through scripts/tidy_headless.py, and runs the same script text
Claude would send, with PARAMS filled in. A few minutes, one Blender at a
time. Nothing is written into the runs; outputs go to a temp folder (--keep
DIR to look at them afterwards). The midpoly cases copy a run's scene.blend
into that folder and make real profiles of the copy.

What each case shows is in its docstring; `--only build` runs the cases
whose name contains "build".
"""
import contextlib
import glob
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", ".claude", "skills", "tidy-mesh", "scripts")
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
sys.path.insert(0, HERE)
import blockout_recipe  # noqa: E402
import check_safe  # noqa: E402


def blender(base, steps, save=None):
    """Run [(script, params)] in one background Blender; return each RESULT."""
    cmd = [BLENDER, "-b", "--factory-startup", "-P", os.path.join(HERE, "tidy_headless.py"), "--", base]
    params, count = {}, {}
    for script, values in steps:
        cmd.append(os.path.join(TOOLS, script))
        count[script] = count.get(script, 0) + 1
        params[script if count[script] == 1 else "%s#%d" % (script, count[script])] = values
    cmd += ["--params", json.dumps(params)]
    if save:
        cmd += ["--save", save]
    out = subprocess.run(cmd, capture_output=True, text=True)
    results = [json.loads(line[7:]) for line in out.stdout.splitlines() if line.startswith("RESULT ")]
    if len(results) != len(steps):
        raise AssertionError("%d of %d scripts finished:\n%s" % (len(results), len(steps), (out.stdout + out.stderr)[-1500:]))
    return results


def read_glb(path):
    """What a .glb holds, read straight from the file."""
    with open(path, "rb") as f:
        f.read(12)
        size, _ = struct.unpack("<II", f.read(8))
        doc = json.loads(f.read(size))
    prims = [p for m in doc.get("meshes", []) for p in m["primitives"]]
    return {
        "meshes": len(doc.get("meshes", [])),
        "triangles": sum(doc["accessors"][p["indices"]]["count"] // 3 for p in prims),
        "vertex_colors": any("COLOR_0" in p["attributes"] for p in prims),
        "materials": len(doc.get("materials", [])),
        "images": len(doc.get("images", [])),
    }


def check(label, ok, detail=""):
    print("    %s  %s%s" % ("ok  " if ok else "FAIL", label, ("  (%s)" % (detail,)) if detail else ""))
    if not ok:
        raise AssertionError(label)


def parts_of(run):
    with open(os.path.join(run, "parts.json")) as f:
        return json.load(f)["parts"]


# ---- the cases -----------------------------------------------------------

def test_safe(ctx):
    """check_safe.py passes every skill script and catches what safe mode refuses."""
    for path in sorted(glob.glob(os.path.join(TOOLS, "*.py"))):
        with open(path) as f:
            found = check_safe.problems(f.read())
        check("%s passes" % os.path.basename(path), not found, found[:2])
    refused = {
        "lambda": "f = lambda x: x",
        "numpy": "import numpy",
        "import alias": "import bpy as b",
        "from bpy": "from bpy import ops",
        "__import__": "m = __import__('os')",
        "open()": "import bpy\nf = open('/tmp/x')",
        "class": "class A:\n    pass",
        "computed getattr": "import bpy\nn = 'name'\nx = getattr(bpy.context, n)",
        "bpy.data.texts": "import bpy\nt = bpy.data.texts.get('a')",
        "preferences via a subscript": "import bpy\np = bpy.context.preferences.addons['cycles'].preferences",
        "a variable named max": "max = 3",
        "calling a passed-in function": "def run(f):\n    return f(1)",
        "handlers": "import bpy\nbpy.app.handlers.frame_change_post.append(print)",
        "walrus": "if (n := 3) > 2:\n    pass",
    }
    for label, code in refused.items():
        check("refuses %s" % label, bool(check_safe.problems(code)))
    allowed = "import bpy\nfrom mathutils import Vector\n\ndef size(o):\n    return len(o.data.polygons)\n\nprint(max(bpy.data.objects, key=size), getattr(bpy.context.scene, 'name'), Vector((0, 0, 1)))"
    check("allows ordinary bpy code", not check_safe.problems(allowed))


def test_open_stand(ctx):
    """open.py + stand.py redo the troll's import, sizing and cleanup (11 calls in the transcript) in two."""
    opened, stood = blender(ctx["kettle"] + "/scene.blend", [
        ("open.py", {"mesh": ctx["troll"] + "/mesh.glb", "name": "Cave Troll", "empty_first": True}),
        ("stand.py", {"size": 2.6, "size_of": "height"}),
    ])
    check("imports the raw mesh as one object", opened["triangles"] == 293921 and opened["joined"] == 1, opened["triangles"])
    check("left the person's own scene alone and worked in a fresh one",
          opened["removed_first"] == 0 and opened["kept_scene"] and opened["scene"].startswith("Forge"),
          (opened["removed_first"], opened["kept_scene"], opened["scene"]))
    check("stands 2.6 m tall on z = 0", abs(stood["size"][2] - 2.6) < 1e-3 and abs(stood["min"][2]) < 1e-4, stood["size"])
    check("same result as Claude's by-hand run: 141,134 vertices, 293,305 triangles",
          stood["vertices"] == 141134 and stood["triangles"] == 293305, (stood["vertices"], stood["triangles"]))
    check("smooth shading by angle is on", "Smooth by Angle" in stood["modifiers"], stood["modifiers"])


def test_measure(ctx):
    """measure.py: each troll part sits inside its parts.json box; the kettle's bracket feet stay out of its body."""
    plan = parts_of(ctx["troll"])
    regions = blender(ctx["troll"] + "/final.glb", [("measure.py", {"parts": plan})])[0]["regions"]
    by_name = {r["name"]: r for r in regions}
    for part in plan:
        r = by_name[part["name"]]
        inside = r["vertices"] > 0 and all(part["min"][i] - 1e-3 <= r["min"][i] and r["max"][i] <= part["max"][i] + 1e-3 for i in range(3))
        check("troll %s: %d vertices inside its box" % (part["name"], r["vertices"]), inside)
    check("the rest is reported as body", by_name["body"]["vertices"] > 50000, by_name["body"]["vertices"])

    slices = {"along": "z", "at": [0.105, 0.117, 0.1298], "thick": 0.012}
    alone, crowded = blender(ctx["kettle"] + "/final.glb", [("measure.py", {"parts": parts_of(ctx["kettle"]), "measure": [
        dict(slices, name="body alone", part="body"),
        dict(slices, name="body and neighbors", box={"min": [-0.083, -0.2, 0], "max": [0.2, 0.2, 0.1298]}),
    ]})])[0]["regions"]
    skew = 2 * (crowded["rows"][-1][3] - alone["rows"][-1][3])
    check("kettle: the bracket feet make the top of the body read %.1f mm wider unless the body is measured alone" % (skew * 1000), skew > 0.004)
    check("rows are [position, middle, middle, half-width, half-width]", len(alone["rows"][0]) == 5 and alone["columns"][0] == "z")


def kettle_pieces(ctx):
    """The kettle's pieces straight from measure.py rows, shaped like its lowpoly.json says."""
    jobs = [{"part": "body", "along": "z", "slices": 11}, {"part": "lid", "along": "z", "slices": 5},
            {"part": "knob", "along": "z", "slices": 5}, {"part": "spout", "along": "x", "slices": 7},
            {"part": "handle", "along": "x", "slices": 11}, {"part": "bracket left", "along": "z", "slices": 3},
            {"part": "bracket right", "along": "z", "slices": 3}]
    regions = blender(ctx["kettle"] + "/final.glb", [("measure.py", {"parts": parts_of(ctx["kettle"]), "measure": jobs})])[0]["regions"]
    rows = {r["name"]: r["rows"] for r in regions}
    iron, oak = [0.12, 0.12, 0.13], [0.45, 0.3, 0.16]
    return [
        {"name": "body", "color": iron, "loft": "z", "sides": 16, "rings": [[z, x, y, ry] for z, x, y, rx, ry in rows["body"]]},
        {"name": "lid", "color": iron, "loft": "z", "sides": 12, "rings": rows["lid"], "caps": [False, True]},
        {"name": "knob", "color": iron, "loft": "z", "sides": 8, "rings": rows["knob"]},
        {"name": "spout", "color": iron, "loft": "x", "sides": 8, "rings": rows["spout"]},
        {"name": "handle", "color": oak, "sides": 6, "tube": [[x, y, z, ry, min(rz, 0.014)] for x, y, z, ry, rz in rows["handle"]]},
        {"name": "bracket left", "color": iron, "loft": "z", "sides": 4, "rings": rows["bracket left"]},
        {"name": "bracket right", "color": iron, "loft": "z", "sides": 4, "rings": rows["bracket right"]},
    ]


def test_build_kettle(ctx):
    """measure.py rows go straight into build.py: the kettle's seven pieces with no hand-tuning."""
    out = os.path.join(ctx["out"], "kettle-lowpoly.glb")
    opened, built, matched, exported = blender(ctx["kettle"] + "/scene.blend", [
        ("open.py", {"mesh": ctx["kettle"] + "/final.glb", "scene": "Low poly"}),
        ("build.py", {"parts": kettle_pieces(ctx)}),
        ("match.py", {"full": "Reference", "light": "Reference (light)"}),
        ("export.py", {"object": "Reference (light)", "path": out, "materials": False}),
    ], save=os.path.join(ctx["out"], "kettle-lowpoly.blend"))
    tris = {p["name"]: p["triangles"] for p in built["pieces"]}
    check("the lathed body is 348 triangles, the lid 106, the handle 128, as in the kettle's lowpoly.json",
          (tris["body"], tris["lid"], tris["handle"]) == (348, 106, 128), tris)
    check("%d triangles in all (Claude's hand-tuned kettle: 790)" % built["triangles"], 700 <= built["triangles"] <= 900)
    lost = built["shape_lost"]
    check("untuned, it strays %.2f%% typically, %.2f%% at worst (hand-tuned: 2.26 / 4.52)" % (lost["p95_%"], lost["max_%"]),
          lost["p95_%"] < 3.5 and lost["max_%"] < 8)
    check("build.py's shape check agrees with match.py (%.2f vs %.2f)" % (lost["p95_%"], matched["shape_lost"]["p95_%"]),
          abs(lost["p95_%"] - matched["shape_lost"]["p95_%"]) < 0.3)
    check("the file had another scene with the full kettle in it", "Scene" in opened["other_scenes"])
    held = read_glb(out)
    check("the exported .glb holds one mesh, %d triangles, vertex colors, no textures" % held["triangles"],
          held == {"meshes": 1, "triangles": built["triangles"], "vertex_colors": True, "materials": 0, "images": 0}, held)
    check("export.py's own read-back says so too", exported["only_this_object"] is True)


SKIN, DARK, LEATHER, ROPE = [0.30, 0.38, 0.29], [0.25, 0.32, 0.24], [0.36, 0.22, 0.12], [0.55, 0.44, 0.28]
IVORY, IRON, STONE = [0.88, 0.84, 0.68], [0.27, 0.28, 0.30], [0.42, 0.41, 0.37]
# The ring tables Claude worked out by hand in the troll's lowpoly transcript.
TORSO = [(0.66, 0.42, 0.30, 0.30), (0.95, 0.60, 0.46, 0.42), (1.2, 0.58, 0.58, 0.45), (1.45, 0.56, 0.64, 0.45), (1.68, 0.57, 0.58, 0.49),
         (1.92, 0.63, 0.46, 0.58), (2.15, 0.63, 0.36, 0.60), (2.35, 0.55, 0.28, 0.53), (2.5, 0.30, 0.06, 0.38)]
HEAD = [(-0.12, 0.30, 1.90, 2.42), (-0.38, 0.28, 1.88, 2.38), (-0.53, 0.20, 1.90, 2.32), (-0.64, 0.14, 1.95, 2.22)]
ARM = [(0.42, 0.10, 2.05, 0.26, 0.27), (0.62, 0.10, 2.06, 0.28, 0.28), (0.80, 0.11, 2.02, 0.25, 0.23), (0.92, 0.10, 1.98, 0.21, 0.21),
       (1.02, 0.09, 1.99, 0.24, 0.22), (1.16, 0.09, 2.00, 0.26, 0.23), (1.31, 0.02, 1.98, 0.22, 0.17), (1.46, -0.03, 1.96, 0.21, 0.13),
       (1.62, -0.05, 1.96, 0.25, 0.14), (1.80, -0.04, 1.97, 0.23, 0.13), (1.93, -0.02, 1.97, 0.15, 0.07)]
LEG = [(1.05, 0.33, 0.02, 0.24, 0.30), (0.80, 0.38, 0.03, 0.22, 0.27), (0.60, 0.40, 0.01, 0.21, 0.25), (0.48, 0.42, 0.04, 0.21, 0.23),
       (0.40, 0.44, 0.06, 0.21, 0.20), (0.32, 0.44, 0.06, 0.21, 0.20), (0.16, 0.45, 0.03, 0.20, 0.22)]
FOOT = [(0.29, 0.28, 0.66, 0.14), (0.05, 0.24, 0.72, 0.20), (-0.25, 0.24, 0.74, 0.15), (-0.40, 0.30, 0.68, 0.08)]
KILT = [(1.19, 0.61, 0.57, 0.49, 0.22), (0.95, 0.63, 0.52, 0.50, 0.12), (0.68, 0.65, 0.52, 0.54, 0.0), (0.72, 0.55, 0.42, 0.44, 0.0), (0.95, 0.48, 0.36, 0.34, 0.0)]
BELT_OUT, BELT_IN = {"back": 0.51, "slope": 0.22}, {"back": 0.45, "slope": 0.22}
TROLL_PIECES = [
    {"name": "torso", "color": SKIN, "loft": "z", "sides": 10, "square": 2.4, "rings": [[z, 0, 0, rx, f, {"back": b}] for z, rx, f, b in TORSO]},
    {"name": "head", "color": SKIN, "loft": "y", "sides": 8, "square": 2.8, "caps": [False, True],
     "rings": [[y, 0, (lo + hi) / 2, hx, (hi - lo) / 2] for y, hx, lo, hi in HEAD]},
    {"name": "arms", "color": SKIN, "loft": "x", "sides": 8, "square": 2.4, "caps": [False, True], "mirror": True,
     "rings": [list(a) + ([{"square": 3.0}] if a[0] > 1.4 else []) for a in ARM]},
    {"name": "legs", "color": SKIN, "loft": "z", "sides": 8, "square": 2.4, "caps": [False, True], "mirror": True, "rings": [list(r) for r in LEG]},
    {"name": "feet", "color": DARK, "loft": "y", "sides": 6, "square": 3, "mirror": True,
     "rings": [[y, (x0 + x1) / 2, top / 2, (x1 - x0) / 2, top / 2] for y, x0, x1, top in FOOT]},
    {"name": "kilt", "color": LEATHER, "loft": "z", "sides": 10, "square": 2.4, "caps": [False, False],
     "rings": [[z, 0, 0, rx, f, {"back": b, "slope": s}] for z, rx, f, b, s in KILT]},
    {"name": "belt", "color": ROPE, "loft": "z", "sides": 10, "square": 2.4, "closed": True, "rings": [
        [1.26, 0, 0, 0.625, 0.60, BELT_OUT], [1.16, 0, 0, 0.625, 0.60, BELT_OUT], [1.16, 0, 0, 0.56, 0.53, BELT_IN], [1.26, 0, 0, 0.56, 0.53, BELT_IN]]},
    {"name": "tusks", "color": IVORY, "tube": [[0.095, -0.60, 2.05, 0.035], [0.115, -0.645, 2.20, 0]], "sides": 5, "mirror": True},
    {"name": "wrist band", "color": IRON, "loft": "x", "sides": 8, "square": 2.4, "closed": True, "rings": [
        [-1.29, 0, 1.975, 0.27, 0.215], [-1.47, 0, 1.975, 0.27, 0.215], [-1.47, 0, 1.975, 0.20, 0.15], [-1.29, 0, 1.975, 0.20, 0.15]]},
    {"name": "back crust", "color": STONE, "mirror": True, "jitter": 0.2, "seed": 3, "lumps": [
        [0.0, 0.24, 2.48, 0.19, 0.17, 0.12], [0.30, 0.22, 2.43, 0.15, 0.14, 0.11], [0.52, 0.14, 2.31, 0.13, 0.13, 0.10],
        [0.24, 0.55, 2.26, 0.13, 0.10, 0.12], [0.0, 0.63, 2.08, 0.12, 0.08, 0.12]]},
]
TROLL_RECORDED = {"torso": 176, "head": 54, "arms": 332, "legs": 204, "feet": 88, "kilt": 80, "belt": 80, "tusks": 16, "wrist band": 64, "back crust": 160}


def test_build_troll(ctx):
    """build.py rebuilds the troll's whole block-out (10 calls in the transcript) from its ring tables, in one."""
    out = os.path.join(ctx["out"], "troll-lowpoly.glb")
    shorter_tusks = [{"name": "tusks", "color": IVORY, "tube": [[0.095, -0.60, 2.05, 0.035], [0.11, -0.63, 2.15, 0]], "sides": 5, "mirror": True}]
    opened, built, again, exported = blender(ctx["troll"] + "/scene.blend", [
        ("open.py", {"mesh": ctx["troll"] + "/final.glb", "scene": "Low poly"}),
        ("build.py", {"parts": TROLL_PIECES}),
        ("build.py", {"parts": shorter_tusks, "remove": ["wrist band"]}),
        ("export.py", {"object": "Reference (light)", "path": out, "materials": False}),
    ], save=os.path.join(ctx["out"], "troll-lowpoly.blend"))
    tris = {p["name"]: p["triangles"] for p in built["pieces"]}
    check("every piece has the triangle count Claude reported", tris == TROLL_RECORDED, tris)
    check("1,254 triangles in all, as recorded", built["triangles"] == 1254, built["triangles"])
    lost = built["shape_lost"]
    check("strays %.2f%% typically, %.2f%% at worst (recorded with match.py: 2.21 / 4.01)" % (lost["p95_%"], lost["max_%"]),
          lost["p95_%"] < 2.6 and lost["max_%"] < 4.6)
    check("as wide and tall as the reference", abs(built["size"][0] - built["reference_size"][0]) < 0.02
          and abs(built["size"][2] - built["reference_size"][2]) < 0.05, (built["size"], built["reference_size"]))
    check("it says where the reference pokes out most", len(built["most_missing_at"]) >= 3)
    check("a second call with one changed piece and one removed keeps the other eight",
          len(again["pieces"]) == 9 and again["triangles"] == 1254 - 64, (len(again["pieces"]), again["triangles"]))
    check("it did not empty the person's own scene of the same name", opened["scene"] != "Low poly" and opened["removed_first"] == 0, opened["scene"])
    check("the file had %d other scenes" % len(opened["other_scenes"]), len(opened["other_scenes"]) > 3)
    held = read_glb(out)
    check("the exported .glb holds one mesh of %d triangles (the old export picked up the 293k reference too)" % held["triangles"],
          held["meshes"] == 1 and held["triangles"] == again["triangles"] and held["vertex_colors"], held)
    check("export.py's own read-back says so too", exported["only_this_object"] is True)


# Each run's parts.json cut with the split.py from before this change.
SPLIT_BEFORE = {
    "kettle": {"knob": 3172, "handle": 25446, "bracket left": 16955, "bracket right": 4992, "lid": 73741, "spout": 5282, "body": 153822},
    "troll": {"tusk left": 176, "tusk right": 158, "wrist band": 9804, "hand left": 3681, "belt front": 24204, "belt sides": 12532,
              "belt back left": 21792, "belt back right": 18360, "kilt front": 5311, "kilt back left": 5954, "kilt back right": 5044,
              "back crust": 23529, "body": 162760},
}
WRAPPED = [
    {"name": "tusks", "min": [0.04, -0.68, 2.06], "max": [0.15, -0.56, 2.2]},
    {"name": "tusks", "min": [-0.15, -0.68, 2.06], "max": [-0.04, -0.56, 2.2]},
    {"name": "wrist band", "min": [-1.52, -0.32, 1.72], "max": [-1.25, 0.32, 2.22], "wraps": True},
    {"name": "belt", "min": [-0.7, -0.75, 1.12], "max": [0.7, 0.67, 1.34], "turn": [11, 0, 0], "wraps": True},
    {"name": "kilt", "min": [-0.7, -0.75, 0.6], "max": [0.7, 0.67, 1.3], "turn": [11, 0, 0], "wraps": True},
    {"name": "back crust", "min": [-0.8, 0.05, 2.0], "max": [0.8, 0.7, 2.62]},
]


def test_split(ctx):
    """split.py: old plans cut exactly as before; a tilted, wrapping belt takes 1 box where the troll needed 4."""
    for name in ("kettle", "troll"):
        got = blender(ctx[name] + "/final.glb", [("split.py", {"parts": parts_of(ctx[name]), "mode": "color"})])[0]["parts"]
        check("%s: its parts.json gives the same faces per part as before" % name, {p["part"]: p["faces"] for p in got} == SPLIT_BEFORE[name])
    got = blender(ctx["troll"] + "/final.glb", [("split.py", {"parts": WRAPPED, "mode": "color"}),
                                                 ("measure.py", {"parts": WRAPPED, "measure": [{"part": "body"}]})])
    share = {p["part"]: p["share"] for p in got[0]["parts"]}
    check("6 boxes make 5 parts (the saved plan needed 12 boxes)", list(share) == ["tusks", "wrist band", "belt", "kilt", "back crust", "body"], list(share))
    check("belt and kilt each come out whole", share["belt"] > 0.1 and share["kilt"] > 0.08, share)
    check("legs and the hand beyond the band stay body (%.0f%% of the surface)" % (share["body"] * 100), share["body"] > 0.55)
    faces = {p["part"]: p["faces"] for p in got[0]["parts"]}
    check("both tusks are in the one part (two boxes, one name)", faces["tusks"] >= 176 + 158, faces["tusks"])


BAND = {"name": "band", "where": {"box": {"min": [-1.5, -0.4, 1.7], "max": [-1.25, 0.4, 2.3]}, "value": [0, 0.045]},
        "set": {"metallic": 1.0, "roughness": 0.55, "saturation": 0.7, "value": 0.85}}
BROW = {"name": "brow", "where": {"box": {"min": [-0.3, -0.75, 2.1], "max": [0.3, -0.4, 2.4]}, "value": [0, 0.03]},
        "set": {"color": [0.08, 0.1, 0.07, 0.6]}}


def test_polish(ctx):
    """retouch.py, frame.py, stage.py and export.py on the troll: the band and the eye smear as areas, the staging, the export."""
    out = os.path.join(ctx["out"], "troll-final.glb")
    overall = {"metallic": 0, "roughness": [0.72, 0.95], "saturation": 1.12, "value": 0.88, "bump": 0.2, "grain": 0.1, "subsurface": 0.06}
    _, _, touched, shown, framed, staged, restaged, exported = blender(ctx["kettle"] + "/scene.blend", [
        ("open.py", {"mesh": ctx["troll"] + "/mesh.glb", "name": "Cave Troll", "empty_first": True}),
        ("stand.py", {"size": 2.6, "size_of": "height"}),
        ("retouch.py", {"overall": overall, "regions": [BAND, BROW]}),
        ("retouch.py", {"overall": overall, "regions": [BAND, BROW], "show": "band"}),
        ("frame.py", {"spots": {"head": {"min": [-0.4, -0.75, 1.9], "max": [0.4, 0.1, 2.5]}}}),
        ("stage.py", {}),
        ("stage.py", {"around": -30, "above": 25}),
        ("export.py", {"object": "Cave Troll", "path": out}),
    ], save=os.path.join(ctx["out"], "troll-polish.blend"))
    areas = {a["region"]: a for a in touched["texture_in"]}
    check("the wrist band is its own area: %.1f%% of the surface" % areas["band"]["covers_%"], 0.5 < areas["band"]["covers_%"] < 5)
    check("the dark smear over the eyes is its own area: %.2f%%" % areas["brow"]["covers_%"], 0 < areas["brow"]["covers_%"] < 1)
    check("it says the band's texture is darker than the hide (median %.3f vs %.3f)"
          % (areas["band"]["in_box"]["value"][1], areas["all"]["texture"]["value"][1]),
          areas["band"]["in_box"]["value"][1] < areas["all"]["texture"]["value"][1])
    check("every number is a knob", touched["knobs"]["band.metallic"] == 1.0 and touched["knobs"]["all.roughness from"] == 0.72
          and "brow.color amount" in touched["knobs"])
    check("running it again rebuilds, it doesn't pile up", shown["knobs"] == dict(touched["knobs"], show=1.0) and shown["showing"] == "band")
    check("frame.py made a target for look", framed["targets"] == ["Look: head"])
    check("key light %.0f W (Claude chose 2500 by hand)" % staged["lights_watts"]["Key"], abs(staged["lights_watts"]["Key"] - 2500) < 150)
    check("camera %.1f m away fits the whole T-pose (Claude settled on 7.2)" % staged["camera"]["distance"], 6 < staged["camera"]["distance"] < 8)
    check("Cycles, 64 samples, 1024 square", (staged["render"]["engine"], staged["render"]["samples"], staged["render"]["size"]) == ("CYCLES", 64, [1024, 1024]))
    check("staging again replaces its floor, lights and camera", staged["replaced"] == 0 and restaged["replaced"] == 5 and restaged["object"] == "Cave Troll")
    check("final.glb holds only the troll", exported["only_this_object"] is True and read_glb(out)["meshes"] == 1)


HEAD_BOX = {"min": [-0.24, -0.7, 1.93], "max": [0.24, -0.25, 2.42]}   # the troll's head: chin to the top of the skull, ears in, back where it sinks into the hump
LOOSE_BOX = {"min": [-0.3, -0.66, 1.9], "max": [0.3, -0.12, 2.42]}    # the size of the head Claude built: chest and shoulders are inside too
# Where the troll's features are, read by eye off the detailed mesh: [height, give or take].
TROLL_FACE = {"chin": [1.96, 0.02], "mouth": [2.09, 0.03], "nose": [2.18, 0.02], "eyes": [2.24, 0.02], "brow": [2.28, 0.02]}

# Glue PNGs into one sheet, row by row. Runs in Blender only because it can read and write PNGs.
SHEET = """
import bpy, json, sys
rows, out = json.loads(sys.argv[-2]), sys.argv[-1]
tiles = [[bpy.data.images.load(p) for p in row] for row in rows]
w, h = tiles[0][0].size
sheet = bpy.data.images.new("sheet", w * len(rows[0]), h * len(rows))
pixels = []
for row in reversed(tiles):
    parts = [list(t.pixels) for t in row]
    for y in range(h):
        for part in parts:
            pixels += part[4 * w * y:4 * w * (y + 1)]
sheet.pixels = pixels
sheet.filepath_raw, sheet.file_format = out, "PNG"
sheet.save()
"""


def test_face(ctx):
    """face.py + build.py's "head": the troll's face rebuilt from measurements alone, next to the 54-triangle head Claude made by hand."""
    final = ctx["troll"] + "/final.glb"
    snug, loose = blender(final, [("face.py", {"box": HEAD_BOX}), ("face.py", {"box": LOOSE_BOX})])
    head, found = snug["head"], snug["found"]
    for key, (z, slack) in TROLL_FACE.items():
        check("%s at %.2f m, found by %s (by eye: %.2f)" % (key, found[key]["z"], found[key]["by"], z),
              abs(found[key]["z"] - z) <= slack and found[key]["by"] != "guess")
        check("  and within 2 cm of that from a loose box that takes in the chest", abs(loose["found"][key]["z"] - found[key]["z"]) <= 0.02,
              loose["found"][key]["z"])
    check("eyes and mouth come from the texture's dark bands, the rest from the shape",
          [found[k]["by"] for k in ("eyes", "mouth", "nose", "brow", "chin")] == ["texture", "texture", "shape", "shape", "shape"])
    check("the lower lip sits %.0f cm ahead of the upper: an underbite" % (head["face"]["underbite"] * 100), 0.06 < head["face"]["underbite"] < 0.13)
    check("tusks found rising from the lower lip, %.0f cm off the center line (parts.json: 9.5)" % (head["tusks"]["at"] * 100),
          head["tusks"]["from"] == "below" and abs(head["tusks"]["at"] - 0.095) < 0.025, head["tusks"])
    check("the eye sockets' color is much darker than the skin's", sum(head["colors"]["socket"]) < 0.3 * sum(head["color"]), head["colors"])
    check("the piece names its six rows, climbing", [head["rows"][k][0] for k in ("chin", "mouth", "nose", "eyes", "brow", "top")]
          == sorted(head["rows"][k][0] for k in head["rows"]) and len(head["rows"]) == 6)

    # The same body three times: with the hand-built head and tusks, with a plain head from the rows
    # alone (the first version of this tool), and with the head laid on the reference's surface.
    body = [p for p in TROLL_PIECES if p["name"] not in ("head", "tusks")]
    fitted = dict(head, color=SKIN)
    plain = {key: value for key, value in fitted.items() if key not in ("scan", "ears")}
    got, sheet, again = compare_heads(ctx, final, "Cave Troll", "troll", HEAD_BOX, {"min": [-0.45, -0.85, 1.75], "max": [0.45, 0.05, 2.55]},
                                      [("hand-built", TROLL_PIECES), ("plain", body + [plain]), ("fitted", body + [fitted])],
                                      # this run's final.glb uses its color picture as its metal and roughness maps too, which renders as chrome
                                      before_shots=[("retouch.py", {"object": "Cave Troll", "overall": {"metallic": 0, "roughness": 0.9}})])
    check("face.py also runs on the built head, which has no texture, and finds its chin by shape within 2 cm",
          not again["textured"] and abs(again["found"]["chin"]["z"] - found["chin"]["z"]) <= 0.02, again["found"])
    old = {p["name"]: p["triangles"] for p in got["hand-built"][0]["pieces"]}
    new = {p["name"]: p["triangles"] for p in got["fitted"][0]["pieces"]}
    total = got["fitted"][0]["triangles"]
    check("the hand-built head is 54 triangles plus 16 of tusks", (old["head"], old["tusks"]) == (54, 16))
    check("the fitted head is %d triangles, tusks and ears included: %.0f%% of %d" % (new["head"], 100 * new["head"] / total, total), 150 <= new["head"] <= 260)
    check("the whole troll stays inside its budget (1,200, give or take a quarter)", 900 <= total <= 1500, total)
    for label in ("hand-built", "plain", "fitted"):
        print(head_scores(label, got[label]))
    was, now = got["plain"][2], got["fitted"][2]
    check("the fitted head shares more of the reference's outline than the plain one, front and side",
          all(now[v]["overlap_%"] > was[v]["overlap_%"] for v in ("front", "side")))
    check("its outline's edges sit within 2 cm of the reference's on average, front and side",
          all(now[v]["edge_off_cm"] < 2.0 for v in ("front", "side")), now)
    check("its surface sits within 2.5 cm of the reference's on average, seen from the front and from the side (plain: %.1f / %.1f)"
          % (was["front"]["relief_off_cm"], was["side"]["relief_off_cm"]),
          all(now[v]["relief_off_cm"] < 2.5 and now[v]["relief_off_cm"] < was[v]["relief_off_cm"] for v in ("front", "side")), now)
    check("and inside the head box the reference strays from it less than from either other head",
          all(got["fitted"][1]["shape_lost"]["p95_%"] < got[label][1]["shape_lost"]["p95_%"] for label in ("hand-built", "plain")))
    check("the whole-object score does not get worse: %.2f%% typical (hand-built head: %.2f)"
          % (got["fitted"][0]["shape_lost"]["p95_%"], got["hand-built"][0]["shape_lost"]["p95_%"]),
          got["fitted"][0]["shape_lost"]["p95_%"] < got["hand-built"][0]["shape_lost"]["p95_%"] + 0.2)
    check("front and side: reference, hand-built, plain, fitted, then the fitted head as wire over the reference: %s" % sheet, os.path.exists(sheet))


def head_scores(label, scores):
    """One line: how well a head follows the reference. The outline numbers are for the head alone;
    the two 'strays' pairs (typical / worst, % of the object's size) are for the whole model inside the head box."""
    _, fit, alone = scores
    return ("          %-10s outline shared front %.0f%%, side %.0f%%; edges off %.1f / %.1f cm; surface off %.1f / %.1f cm; "
            "reference strays %.2f%% / %.2f%%; model strays %.2f%% / %.2f%%"
            % (label, alone["front"]["overlap_%"], alone["side"]["overlap_%"], alone["front"]["edge_off_cm"], alone["side"]["edge_off_cm"],
               alone["front"]["relief_off_cm"], alone["side"]["relief_off_cm"], fit["shape_lost"]["p95_%"], fit["shape_lost"]["max_%"],
               fit["shape_added"]["p95_%"], fit["shape_added"]["max_%"]))


def compare_heads(ctx, final, reference, tag, box, close, versions, before_shots=(), kind="creature"):
    """In one Blender: measure the head (which stores its surface in the scene), build each version of
    the model, score each inside the head box, and render the reference, each version, and the last
    version as wire over the reference, front and side. versions = [(label, pieces)].
    Returns {label: (build.py's result, match.py's result for the model, the outline scores of its head alone)},
    the sheet's path, and face.py's result on the last version."""
    def view_path(who, view):
        return os.path.join(ctx["out"], "%s-head-%s-%s.png" % (tag, who, view))
    def shots(who, obj, over=None):
        return [("preview.py", {"object": obj, "path": view_path(who, view), "view": view, "box": close, "size": 480, "over": over}) for view in ("front", "side")]
    steps = [("face.py", {"box": box, "kind": kind, "show": False})]
    for label, pieces in versions:
        name, alone = "%s (light)" % label, "%s head (light)" % label
        steps += [("build.py", {"parts": pieces, "name": name}), ("match.py", {"full": reference, "light": name, "box": box}),
                  # the head and its tusks without the body, to score the head's own surface
                  ("build.py", {"parts": [p for p in pieces if p["name"] in ("head", "tusks")], "name": alone, "check": 0}),
                  ("match.py", {"full": reference, "light": alone, "box": box, "samples": 2000})]
    last = "%s (light)" % versions[-1][0]
    steps += list(before_shots) + shots("reference", reference)
    for label, _ in versions:
        steps += shots(label, "%s (light)" % label)
    steps += shots("overlay", reference, over="%s head (light)" % versions[-1][0])
    steps += [("face.py", {"object": last, "box": box, "kind": kind, "show": False, "name": "check"})]
    results = blender(final, steps, save=os.path.join(ctx["out"], "%s-head.blend" % tag))
    got = {label: (results[1 + 4 * n], results[2 + 4 * n], results[4 + 4 * n]["outline"]) for n, (label, _) in enumerate(versions)}
    rows = ["reference"] + [label for label, _ in versions] + ["overlay"]
    sheet = sheet_of(ctx, "%s-head-compared" % tag, [[view_path(who, view) for view in ("front", "side")] for who in rows])
    return got, sheet, results[-1]


def sheet_of(ctx, name, grid):
    """Glue a grid of PNG paths into <out>/<name>.png and return its path."""
    path = os.path.join(ctx["out"], name + ".png")
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python-expr", SHEET, "--", json.dumps(grid), path], capture_output=True, text=True)
    return path


PIRATE_BOX = {"min": [-0.17, -0.22, 1.38], "max": [0.17, 0.2, 1.64]}  # beard to hat brim, face to the back of the hair


def test_face_human(ctx):
    """face.py on a person: the pirate has a beard, an eye patch, a hat and a white collar, each a way to go wrong."""
    runs = sorted(glob.glob(os.path.join(os.path.dirname(ctx["troll"]), "*stocky-pirate-deckhand", "final.glb")))
    if not runs:
        print("    skipped: no stocky-pirate-deckhand run with a final.glb")
        return
    measured = blender(runs[-1], [("face.py", {"box": PIRATE_BOX, "kind": "human"})])[0]
    head, found = measured["head"], measured["found"]
    check("eyes at %.2f m by the texture (by eye: 1.59), under the hat's dark brim" % found["eyes"]["z"],
          abs(found["eyes"]["z"] - 1.59) <= 0.015 and found["eyes"]["by"] == "texture")
    check("nose at %.2f m (by eye: 1.53), sticking out %.0f cm" % (found["nose"]["z"], head["face"]["nose_out"] * 100),
          abs(found["nose"]["z"] - 1.53) <= 0.02 and 0.05 < head["face"]["nose_out"] < 0.1)
    check("each eye sits between 2 and 12 cm from the center line", 0.02 <= head["face"]["eye_in"] < head["face"]["eye_out"] <= 0.12, head["face"])
    check("the beard is found as a color of its own, darker than the skin", sum(head["colors"]["beard"]) < 0.5 * sum(head["color"]), head["colors"])
    check("the skin color comes from the cheeks, not the beard or hat (red over green over blue)", head["color"][0] > head["color"][1] > head["color"][2] > 0.04, head["color"])
    check("the white collar is not taken for tusks", "tusks" not in head)
    plain = {key: value for key, value in head.items() if key not in ("scan", "ears")}
    got, sheet, _ = compare_heads(ctx, runs[-1], "Stocky Pirate Deckhand", "pirate", PIRATE_BOX, {"min": [-0.3, -0.35, 1.3], "max": [0.3, 0.25, 1.9]},
                                  [("plain", [plain]), ("fitted", [head])], kind="human")
    check("the head alone is %d triangles" % got["fitted"][0]["triangles"], 150 <= got["fitted"][0]["triangles"] <= 260)
    for label in ("plain", "fitted"):
        print(head_scores(label, got[label]))
    was, now = got["plain"][2], got["fitted"][2]
    check("the fitted head's surface is nearer the reference's than the plain one's, seen from the front and from the side",
          all(now[v]["relief_off_cm"] < was[v]["relief_off_cm"] for v in ("front", "side")))
    check("from the side it shares %.0f%% of the reference's outline (plain: %.0f%%); from the front %.0f%% (plain: %.0f%%), where the collar in the box widens the jaw"
          % (now["side"]["overlap_%"], was["side"]["overlap_%"], now["front"]["overlap_%"], was["front"]["overlap_%"]),
          now["side"]["overlap_%"] > was["side"]["overlap_%"] and now["front"]["overlap_%"] > 88)
    check("front and side: reference, plain, fitted, then the fitted head as wire over the reference: %s" % sheet, os.path.exists(sheet))


def body_under(piece, color, by=0.88):
    """A loft or tube a little thinner than `piece`, in a skin color: the body under that piece of gear."""
    def thinner(row):
        nums = [v * by if i in (3, 4) else v for i, v in enumerate(row) if not isinstance(v, dict)]
        more = [dict(v, back=v["back"] * by) if "back" in v else v for v in row if isinstance(v, dict)]
        return nums + more
    key = "rings" if "loft" in piece else "tube"
    return dict(piece, name=piece["name"] + " (body)", color=color, **{key: [thinner(r) for r in piece[key]]})


def geared(case):
    """One of test_blockouts.json's block-outs as Claude is now asked to build it: gear pieces say which
    gear item they are, and there is a body under them. The saved block-outs predate that (the coat was
    the torso), so the body under each piece in "under" is made here, a thinner copy in the skin color."""
    pieces = []
    for piece in case["pieces"]:
        gear = case["wear"].get(piece["name"])
        if piece["name"] in case["under"]:
            pieces.append(body_under(piece, case["skin"]))
        pieces.append(dict(piece, gear=gear) if gear else dict(piece))
    return pieces


def pirate_dressed(case):
    """The pirate as a case for loose cloth. `geared` makes the body under his coat a thinner copy of the
    coat, skirts and all, so there would be nothing for the skirts to hang off. Here the body narrows to
    hips below the belt, as a body does, and the coat's own piece says it is loose (the "fit" Claude is
    now asked to give such a piece)."""
    pieces = geared(case)
    for piece in pieces:
        if piece["name"] == "torso (body)":
            piece["rings"] = [[z, x, y, min(rx, 0.21 if z > 0.75 else 0.2), min(ry, 0.155 if z > 0.75 else 0.15)] if z < 0.9 else [z, x, y, rx, ry]
                              for z, x, y, rx, ry in piece["rings"]]
        if piece["name"] == "torso":
            piece["fit"] = "loose"
    return pieces


TROLL_GEAR = [{"name": "hide kilt", "kind": "worn", "slot": "legs"}, {"name": "rope belt", "kind": "worn", "slot": "hip"},
              {"name": "iron wrist band", "kind": "worn", "slot": "arms"}, {"name": "club", "kind": "held", "slot": "hand_right"}]
TROLL_WEARS = {"kilt": "hide kilt", "belt": "rope belt", "wrist band": "iron wrist band"}
SOCKETS = ["back", "hand_left", "hand_right", "head", "hip"]


def troll_with_gear(head=None):
    """The troll's block-out with its kilt, belt and wrist band named as gear. Its torso and legs were
    already built whole under them. `head` swaps the hand-built head and tusks for a face.py one."""
    pieces = [dict(p, gear=TROLL_WEARS[p["name"]]) if p["name"] in TROLL_WEARS else dict(p) for p in TROLL_PIECES]
    if head:
        pieces = [p for p in pieces if p["name"] not in ("head", "tusks")] + [dict(head, color=SKIN)]
    return pieces


def keep_recipe(glb):
    """What the pipeline does right after the block-out: name the nodes for their tags, save lowpoly_build.json."""
    with contextlib.redirect_stdout(io.StringIO()):
        blockout_recipe.main(glb)


def nodes_of(path):
    """A .glb's nodes: {name: (its tags, where it is, how many triangles)}."""
    doc = blockout_recipe.read(path)[0]
    def triangles(node):
        if "mesh" not in node:
            return 0
        return sum(doc["accessors"][p["indices"]]["count"] // 3 for p in doc["meshes"][node["mesh"]]["primitives"])
    return {n["name"]: (n.get("extras") or {}, n.get("translation"), triangles(n)) for n in doc["nodes"]}


def test_gear(ctx):
    """Gear comes off: build.py keeps the troll's kilt, belt and wrist band as groups over a whole body and finds the sockets; export.py writes them apart."""
    out = os.path.join(ctx["out"], "gear", "lowpoly.glb")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    built, again, exported = blender(ctx["troll"] + "/final.glb", [
        ("build.py", {"parts": troll_with_gear(), "gear": TROLL_GEAR, "sockets": True, "name": "Troll (light)"}),
        # a later round: one piece changes, one socket is moved by hand; the gear list and the other sockets are remembered
        ("build.py", {"parts": [dict(TROLL_PIECES[7], name="tusks")], "sockets": {"head": [0, -0.4, 2.44]}, "name": "Troll (light)", "check": 0}),
        ("export.py", {"object": "Troll (light)", "path": out, "materials": False}),
    ])
    groups = {g["name"]: g for g in built["groups"]}
    check("four groups: the body and three gear items", list(groups) == ["body", "gear: hide kilt", "gear: rope belt", "gear: iron wrist band"], list(groups))
    check("the body is everything else: %d of 1,254 triangles" % groups["body"]["triangles"],
          groups["body"]["triangles"] == 1254 - 80 - 80 - 64 and built["triangles"] == 1254)
    check("each gear group carries its kind and slot from the gear list",
          (groups["gear: rope belt"]["kind"], groups["gear: rope belt"]["slot"]) == ("worn", "hip"), groups["gear: rope belt"])
    check("nothing worn is missing; the held club is not expected on the body", built["gear_not_built"] == [])
    check("the shape check still sees one object: %.2f%% typical" % built["shape_lost"]["p95_%"], built["shape_lost"]["p95_%"] < 2.6)
    at = built["sockets"]
    check("five sockets", sorted(at) == SOCKETS, sorted(at))
    check("the right hand's is at -x, inside the hand (the arm ends at x = -1.93): x = %.2f" % at["hand_right"][0], -1.93 < at["hand_right"][0] < -1.6)
    check("the left hand's mirrors it", at["hand_left"] == [-at["hand_right"][0]] + at["hand_right"][1:], at["hand_left"])
    check("back: behind the spine at shoulder height (y = %.2f); hip: on the left side at belt height (x = %.2f, z = %.2f)"
          % (at["back"][1], at["hip"][0], at["hip"][2]), at["back"][1] > 0.3 and 0.4 < at["hip"][0] < 0.7 and 1.0 < at["hip"][2] < 1.4)
    check("a later call keeps the groups and sockets, and a socket moved by hand stays where it was put",
          len(again["groups"]) == 4 and again["sockets"]["head"] == [0, -0.4, 2.44] and again["sockets"]["hip"] == at["hip"], again["sockets"])

    found = nodes_of(out)
    meshes = [n for n in found if found[n][2]]
    check("the .glb has one mesh per group, named for it", meshes == ["body", "gear: hide kilt", "gear: iron wrist band", "gear: rope belt"], meshes)
    check("each gear mesh is tagged with its name, kind and slot",
          found["gear: hide kilt"][0] == {"forge": "gear", "gear": "hide kilt", "kind": "worn", "slot": "legs"}, found["gear: hide kilt"][0])
    check("and has its own triangles (kilt 80, belt 80, band 64)", [found[n][2] for n in meshes[1:]] == [80, 64, 80])
    check("five empties named socket: ...", sorted(n for n in found if n.startswith("socket: ")) == ["socket: " + k for k in SOCKETS])
    x, y, z = again["sockets"]["hand_right"]
    check("each where build.py put it (glTF has y up)", all(abs(a - b) < 1e-4 for a, b in zip(found["socket: hand_right"][1], [x, z, -y])), found["socket: hand_right"][1])
    check("export.py's read-back counts 4 meshes and 5 empties and still says only_this_object",
          exported["only_this_object"] is True and (exported["file"]["meshes"], exported["file"]["empties"]) == (4, 5), exported["file"])

    # What outlives the session rides in the file: the recipe, and tags that put the names right.
    doc, rest = blockout_recipe.read(out)
    doc["nodes"][0]["name"] += ".001"  # what Blender writes when the session already holds an object of that name
    blockout_recipe.write(out, doc, rest)
    keep_recipe(out)
    check("blockout_recipe.py puts a node name right from its tag", "body" in nodes_of(out))
    with open(os.path.join(os.path.dirname(out), "lowpoly_build.json")) as f:
        recipe = json.load(f)
    check("and saves the recipe beside the .glb: %d pieces, the gear list, the sockets" % len(recipe["pieces"]),
          len(recipe["pieces"]) == 10 and len(recipe["gear"]) == 4 and recipe["sockets"]["head"] == [0, -0.4, 2.44])
    check("a recipe piece is what build.py was given", [p for p in recipe["pieces"] if p["name"] == "kilt"][0]["gear"] == "hide kilt")

    try:
        blender(ctx["troll"] + "/final.glb", [("build.py", {"parts": [dict(TROLL_PIECES[5], gear="cape")], "gear": TROLL_GEAR, "check": 0})])
        refused = ""
    except AssertionError as err:
        refused = str(err)
    check("a piece naming gear the list doesn't have is refused, with the names it could be", "which the gear list doesn't have: hide kilt, rope belt" in refused)


def test_denser(ctx):
    """The mid-poly rebuild's arithmetic, no Blender: more sides, rings eased in between, nothing bulging past the block-out."""
    knob = {"name": "knob", "loft": "z", "sides": 8, "rings": [[0, 0, 0, 0.0], [1, 0, 0, 1.0], [2, 0, 0, 1.0, 1.2, {"back": 0.5}], [3, 0, 0, 0.2]]}
    twice = blockout_recipe.denser(knob, 2, 2, 10)
    check("8 sides become 16, 4 rings become 7", (twice["sides"], len(twice["rings"])) == (16, 7))
    check("the block-out's own rings are all still there", [r[:4] for r in twice["rings"][::2]] == [r[:4] for r in knob["rings"]])
    check("a ring eased in lies between the rings either side of it, never past them", all(min(a[3], b[3]) <= m[3] <= max(a[3], b[3])
          for a, m, b in zip(twice["rings"][0::2], twice["rings"][1::2], twice["rings"][2::2])))
    check("a ring's flat back is eased too", 0.5 < twice["rings"][3][5]["back"] < 1.0, twice["rings"][3][5])
    band = {"name": "belt", "loft": "z", "sides": 10, "closed": True, "rings": [[1, 0, 0, 1], [0, 0, 0, 1], [0, 0, 0, 0.9], [1, 0, 0, 0.9]]}
    check("a band keeps its four rings and gets more sides", blockout_recipe.denser(band, 2, 2, 10) == dict(band, sides=20))
    post = {"name": "post", "loft": "z", "sides": 4, "rings": [[0, 0, 0, 1], [1, 0, 0, 1]]}
    check("a square post stays square", blockout_recipe.denser(post, 3, 1, 10)["sides"] == 4)
    check("rocks and heads are split finer, boxes are left alone",
          (blockout_recipe.denser({"lumps": []}, 2, 2, 1)["detail"], blockout_recipe.denser({"head": "-y"}, 2, 2, 1)["finer"],
           blockout_recipe.denser({"box": {}}, 2, 2, 1)) == (2, 1, {"box": {}}))
    close = {"name": "elbow", "loft": "x", "rings": [[0, 0, 0, 1], [0.05, 0, 0, 1], [1, 0, 0, 1]]}
    check("two rings set close for a joint get nothing between them", len(blockout_recipe.denser(close, 2, 2, 10)["rings"]) == 4)


def profiles(ctx, run, pieces, gear, names, before=()):
    """A copy of `run` in the output folder with a fresh block-out made of `pieces`, then the named
    profiles made from it by the real runner. Nothing is written into `run`. Returns the copy's folder,
    {profile: its .json}, and build.py's result."""
    copy = os.path.join(ctx["out"], "runs", os.path.basename(run))
    os.makedirs(copy, exist_ok=True)
    for name in ("scene.blend", "brief.json", "parts.json"):
        if not os.path.exists(os.path.join(copy, name)):
            shutil.copy(os.path.join(run, name), os.path.join(copy, name))
    glb = os.path.join(copy, "lowpoly.glb")
    results = blender(run + "/final.glb", list(before) + [
        ("build.py", {"parts": pieces, "gear": gear, "sockets": True, "name": "Block-out (light)", "check": 0}),
        ("export.py", {"object": "Block-out (light)", "path": glb, "materials": False}),
    ])
    keep_recipe(glb)
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", os.path.join(HERE, "tidy_profile.py"), "--",
                          os.path.join(copy, "scene.blend"), os.path.join(copy, "profiles")] + names, capture_output=True, text=True)
    records = {}
    for name in names:
        path = os.path.join(copy, "profiles", name + ".json")
        if not os.path.exists(path):
            raise AssertionError("no %s profile:\n%s" % (name, (out.stdout + out.stderr)[-1500:]))
        with open(path) as f:
            records[name] = json.load(f)
    return copy, records, results[-2]


def midpoly_checks(label, copy, records, built):
    """What every mid-poly version must be, next to the low-poly one made from the same recipe."""
    low, mid = records["lowpoly"], records["midpoly"]
    steps = {s["script"]: s["result"] for s in mid["steps"]}
    tris = steps["rebuild"]["triangles"]
    check("%s: %s triangles, from a %s-triangle block-out (%s)" % (label, format(tris, ","), format(built["triangles"], ","), steps["rebuild"]["tried"]),
          3000 <= tris <= 8000)
    was, now = low["shape"]["shape_lost"], mid["shape"]["shape_lost"]
    check("%s: strays %.2f%% typically, %.2f%% at worst (low poly: %.2f / %.2f)" % (label, now["p95_%"], now["max_%"], was["p95_%"], was["max_%"]),
          now["p95_%"] <= was["p95_%"] + 0.25 and now["max_%"] <= was["max_%"] + 0.5)
    check("%s: color, a normal map, metal and roughness baked at 1024; what the bake couldn't find is the block-out's own color, not black" % label,
          steps["bake.py"]["maps"] == ["color", "metallic", "normal", "roughness"] and "1024 px" in steps["bake.py"]["done"][0]
          and "own colors" in steps["bake.py"]["done"][1])
    held = read_glb(os.path.join(copy, "profiles", "midpoly.glb"))
    check("%s: the .glb has its three textures and no painted colors left to darken them" % label, held["images"] == 3 and not held["vertex_colors"], held)
    check("%s: %.2f MB with WebP and Draco, made in %.0f s" % (label, mid["bytes"] / 1e6, mid["seconds"]), mid["bytes"] < 1.5e6)
    held = [nodes_of(os.path.join(copy, "profiles", name + ".glb")) for name in ("lowpoly", "midpoly")]
    whole = [sorted(n for n in h if not n.startswith("body under: ")) for h in held]  # the skin gear hides is in meshes of its own: see test_drape
    check("%s: the same nodes as the low-poly version: %s" % (label, ", ".join(n for n in whole[1] if not n.startswith("socket"))),
          whole[0] == whole[1] and "body" in held[1] and len(whole[1]) == len(built["groups"]) + 5)
    hidden = {n: held[1][n][0].get("under") for n in held[1] if n.startswith("body under: ")}
    check("%s: %d more body meshes hold the skin its gear hides, each tagged with the gear that hides it" % (label, len(hidden)),
          hidden and all(hidden[n] and n == "body under: " + " + ".join(hidden[n].split("|")) for n in hidden), hidden)
    check("%s: the gallery is told the gear and the sockets" % label,
          sorted(g["gear"] for g in mid["gear"]) == sorted(g["gear"] for g in built["groups"] if g.get("gear")) and mid["sockets"] == SOCKETS, mid["gear"])
    check("%s: sockets sit exactly where the block-out's do" % label,
          all(max(abs(a - b) for a, b in zip(held[0][n][1], held[1][n][1])) < 1e-4 for n in held[1] if n.startswith("socket")))
    under = mid["under_gear"]
    check("%s: %d body faces under gear are plain skin, not a copy of the gear's texture" % (label, under["body_faces_under_gear"]),
          under["body_faces_under_gear"] > 20 and under["plain_colors"] >= 1, under)
    edges = blockout_recipe.read(os.path.join(copy, "profiles", "midpoly-edges.glb"))[0]
    check("%s: the wireframe file has lines for every group, tagged like the group, the body's split where its mesh is" % label,
          {(n.get("extras") or {}).get("gear", "body") for n in edges["nodes"]} == {g.get("gear", "body") for g in built["groups"]}
          and sorted((n.get("extras") or {}).get("under") for n in edges["nodes"] if (n.get("extras") or {}).get("under")) == sorted(hidden.values()))
    return tris, now


def test_midpoly(ctx):
    """The midpoly profile: the troll's block-out (with a measured head) built again denser and baked; gear and sockets as in the low-poly version."""
    final = ctx["troll"] + "/final.glb"
    head = blender(final, [("face.py", {"box": HEAD_BOX, "show": False})])[0]["head"]
    copy, records, built = profiles(ctx, ctx["troll"], troll_with_gear(head), TROLL_GEAR, ["lowpoly", "midpoly"],
                                    before=[("face.py", {"box": HEAD_BOX, "show": False})])
    with open(os.path.join(copy, "lowpoly_build.json")) as f:
        recipe = json.load(f)
    check("the recipe carries the head's measured surface, so the head can be laid on it again", list(recipe["scans"]) == [head["scan"]], list(recipe["scans"]))
    midpoly_checks("troll", copy, records, built)
    was = {p["name"]: p["triangles"] for p in built["pieces"]}
    mid = blender(final, [("face.py", {"box": HEAD_BOX, "show": False}),
                          ("build.py", {"parts": [blockout_recipe.denser(p, 2, 2, 3.86) for p in recipe["pieces"]], "shading": "smooth", "crease": 40, "check": 0})])[1]
    now = {p["name"]: p["triangles"] for p in mid["pieces"]}
    check("the head goes from %d to %d triangles, the arms from %d to %d" % (was["head"], now["head"], was["arms"], now["arms"]),
          3.5 * was["head"] <= now["head"] <= 4.5 * was["head"] and 3 * was["arms"] <= now["arms"] <= 4.2 * was["arms"])
    check("the low-poly version in flat colors keeps the same groups and no textures",
          records["lowpoly"].get("flat_colors") and read_glb(os.path.join(copy, "profiles", "lowpoly.glb"))["images"] == 0)
    for view in ("midpoly.png", "lowpoly.png"):
        shutil.copy(os.path.join(copy, "profiles", view), os.path.join(ctx["out"], "troll-" + view))
    check("previews to compare: %s and troll-lowpoly.png" % os.path.join(ctx["out"], "troll-midpoly.png"), True)


def test_midpoly_others(ctx):
    """The same on the lizardkin, the pirate and the ninja, from their recorded block-outs (scripts/test_blockouts.json), where those runs are there."""
    with open(os.path.join(HERE, "test_blockouts.json")) as f:
        cases = json.load(f)
    for who, case in cases.items():
        runs = sorted(glob.glob(os.path.join(os.path.dirname(ctx["troll"]), "*" + who, "final.glb")))
        if not runs:
            print("    skipped: no %s run with a final.glb" % who)
            continue
        run = os.path.dirname(runs[-1])
        copy, records, built = profiles(ctx, run, geared(case), case["gear"], ["lowpoly", "midpoly"])
        label = who.split("-")[-2] if who.endswith("deckhand") else who.split("-")[0] if who.startswith("lizard") else who.split("-")[-1]
        midpoly_checks(label, copy, records, built)
        check("%s: nothing worn was left unbuilt" % label, built["gear_not_built"] == [], built["gear_not_built"])
        for view in ("midpoly.png", "lowpoly.png"):
            shutil.copy(os.path.join(copy, "profiles", view), os.path.join(ctx["out"], "%s-%s" % (label, view)))


# ---- skeletons and walking ----

WALKERS = [("troll", "*cave-troll"), ("ninja", "*shadow-ninja"), ("pirate", "*stocky-pirate-deckhand"), ("lizardkin", "*lizardkin-warrior")]
BODY_BONES = ["hips", "spine", "chest", "neck", "head"] + [b + s for s in ("_l", "_r") for b in
              ("shoulder", "upper_arm", "forearm", "hand", "thigh", "shin", "foot", "toe")]
SIZES = {5120: ("b", 1, 127.0), 5121: ("B", 1, 255.0), 5122: ("h", 2, 32767.0), 5123: ("H", 2, 65535.0), 5125: ("I", 4, 1.0), 5126: ("f", 4, 1.0)}
WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def glb_rows(doc, rest, index):
    """One accessor of a .glb as a list of tuples, read with plain Python (the walk files are not Draco-packed)."""
    acc = doc["accessors"][index]
    view = doc["bufferViews"][acc["bufferView"]]
    code, size, full = SIZES[acc["componentType"]]
    wide = WIDTHS[acc["type"]]
    start = 8 + view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride") or size * wide
    rows = [struct.unpack_from("<%d%s" % (wide, code), rest, start + i * stride) for i in range(acc["count"])]
    if acc.get("normalized"):
        rows = [tuple(v / full for v in row) for row in rows]
    return rows


def quat_times(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def turn_degrees(rest, now):
    """How far a joint has turned from its rest, as Blender's XYZ angles about the bone's own axes."""
    import math
    x, y, z, w = quat_times((-rest[0], -rest[1], -rest[2], rest[3]), now)
    r20, r21, r22 = 2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)
    r10, r00 = 2 * (x * y + w * z), 1 - 2 * (y * y + z * z)
    return [math.degrees(v) for v in (math.atan2(r21, r22), math.asin(max(-1.0, min(1.0, -r20))), math.atan2(r10, r00))]


def walk_file_checks(label, path, bones, tail, clip="walk"):
    """What a walking .glb must hold, read straight from the file: skeleton, weights, one looping animation inside the limits."""
    doc, rest = blockout_recipe.read(path)
    names = [n.get("name") for n in doc["nodes"]]
    skin = doc["skins"][0]
    joints = [names[j] for j in skin["joints"]]
    check("%s: the file has one skeleton of %d bones with the shared names%s" % (label, len(joints), ", and tail_1..%d" % tail if tail else ""),
          len(doc["skins"]) == 1 and sorted(joints) == sorted(bones), sorted(set(joints) ^ set(bones)))
    skinned = [n for n in doc["nodes"] if "mesh" in n]
    check("%s: every mesh in it is bound to that skeleton" % label, skinned and all(n.get("skin") == 0 for n in skinned))
    points = bare = off = bad = 0
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            weights = glb_rows(doc, rest, prim["attributes"]["WEIGHTS_0"])
            used = glb_rows(doc, rest, prim["attributes"]["JOINTS_0"])
            points += len(weights)
            bare += sum(1 for w in weights if sum(w) < 1e-4)
            off += sum(1 for w in weights if abs(sum(w) - 1) > 1e-3)
            bad += sum(1 for row, w in zip(used, weights) for j, x in zip(row, w) if x > 0 and j >= len(joints))
    check("%s: all %d points carry weights that add up to 1, none left unbound" % (label, points), points and not bare and not off and not bad, (bare, off, bad))
    clips = doc.get("animations", [])
    check("%s: it holds one animation, named %s" % (label, clip), [a.get("name") for a in clips] == [clip], [a.get("name") for a in clips])
    turning = {}
    for channel in clips[0]["channels"]:
        sampler = clips[0]["samplers"][channel["sampler"]]
        keys = glb_rows(doc, rest, sampler["output"])
        times = glb_rows(doc, rest, sampler["input"])
        seam = max(abs(a - b) for a, b in zip(keys[0], keys[-1]))
        if seam > 1e-4:
            raise AssertionError("%s: %s %s does not end where it began (%.5f)" % (label, names[channel["target"]["node"]], channel["target"]["path"], seam))
        if channel["target"]["path"] == "rotation":
            turning[names[channel["target"]["node"]]] = (keys, times)
    check("%s: every bone is keyed, and each one's last key equals its first (the loop has no seam)" % label, sorted(turning) == sorted(bones), sorted(set(bones) - set(turning)))
    frames = len(turning["hips"][0])
    check("%s: %d keys, one a frame, %.3f s" % (label, frames, turning["hips"][1][-1][0]), frames >= 13)
    over, worst = 0, 0.0
    for node in doc["nodes"]:
        lim = (node.get("extras") or {}).get("limit_deg")
        if not lim or node["name"] not in turning:
            continue
        for key in turning[node["name"]][0]:
            for k, angle in enumerate(turn_degrees(node.get("rotation", [0, 0, 0, 1]), key)):
                past = max(lim[2 * k] - angle, angle - lim[2 * k + 1])
                worst = max(worst, past)
                over += past > 0.2
    limited = sum(1 for n in doc["nodes"] if (n.get("extras") or {}).get("limit_deg"))
    check("%s: %d joints carry their limits in the file, and no key turns past one (furthest %.2f degrees over)" % (label, limited, max(worst, 0.0)),
          limited == len(bones) - 1 and over == 0, (limited, over))
    return doc


def test_walk(ctx):
    """rig.py, walk.py, animate.py: each character's low-poly version gets a skeleton read off its own build, and a walk worked out from it."""
    with open(os.path.join(HERE, "test_gaits.json")) as f:
        said = json.load(f)
    gaits = {}
    for label, pattern in WALKERS:
        runs = sorted(glob.glob(os.path.join(os.path.dirname(ctx["troll"]), pattern, "profiles", "lowpoly.glb")))
        if not runs:
            print("    skipped: no %s run with a low-poly version" % pattern)
            continue
        traits = next(v for k, v in said.items() if k in runs[-1] and k != "about")
        out = os.path.join(ctx["out"], "%s-walk.glb" % label)
        rig, walk, moved, exported = blender(runs[-1], [
            ("rig.py", {}),
            ("walk.py", {"traits": {k: v for k, v in traits.items() if k != "why"}}),
            ("animate.py", {}),
            ("export.py", {"rig": True, "path": out, "materials": False}),
        ], save=os.path.join(ctx["out"], "%s-walk.blend" % label))
        tail = rig["measure"]["tail_bones"]
        bones = BODY_BONES + ["tail_%d" % (i + 1) for i in range(tail)]
        check("%s: %d bones, placed from the %s (elbow by %s, knee by %s, wrist by the %s)" % (
              label, len(rig["bones"]), rig["placed_from"], rig["found_by"]["elbow"], rig["found_by"]["knee"], rig["found_by"]["wrist"]),
              sorted(rig["bones"]) == sorted(bones), sorted(set(rig["bones"]) ^ set(bones)))
        check("%s: every bone's head and middle is inside the mesh" % label, rig["bones_outside"] == [], rig["bones_outside"])
        j, m = rig["joints"], rig["measure"]
        check("%s: joints in order down each limb (shoulder %.2f, elbow %.2f, wrist %.2f out; hip %.2f, knee %.2f, ankle %.2f up), mirrored left to right" % (
              label, j["upper_arm_l"][0], j["forearm_l"][0], j["hand_l"][0], j["thigh_l"][2], j["shin_l"][2], j["foot_l"][2]),
              0 < j["upper_arm_l"][0] < j["forearm_l"][0] < j["hand_l"][0] and j["thigh_l"][2] > j["shin_l"][2] > j["foot_l"][2] > j["toe_l"][2] >= 0
              and j["hand_r"] == [-j["hand_l"][0]] + j["hand_l"][1:] and j["hips"][2] < j["spine"][2] < j["chest"][2] < j["neck"][2] < j["head"][2])
        check("%s: bound by %s (%s); no point left without a weight" % (label, rig["weights"], rig["why_not_automatic"] or "automatic weights held"),
              all(s["unweighted"] == 0 for s in rig["skin"].values()) and rig["weights"] in ("automatic", "pieces"))
        lim = rig["limits"]
        check("%s: knees and elbows are one-way hinges, and a bulkier build is stiffer (flexibility %.2f)" % (label, m["flexibility"]),
              lim["shin_l"] == [0.0, 150.0, 0.0, 0.0, 0.0, 0.0] and lim["forearm_l"][:2] == [0.0, 0.0] and lim["forearm_l"][4:] == [-150.0, 0.0]
              and lim["forearm_r"][4:] == [0.0, 150.0] and 0.8 <= m["flexibility"] <= 1.15)
        g, c = walk["gait"], moved["check"]
        gaits[label] = dict(g, leg=m["hip_height"], arm=m["arm_long"], bulk=m["bulk"], height=m["height"])
        check("%s walks %.2f m/s: %.2f m stride, %d steps a minute, feet %.2f m apart, bob %.1f cm, sway %.1f cm, arms swing %.0f degrees (hands travel %.2f m), lean %.0f degrees" % (
              label, g["speed_m_s"], g["stride_m"], g["cadence_steps_per_min"], g["stance_width_m"], g["bob_cm"], g["sway_cm"], g["arm_swing_deg"], g["hand_travel_m"], g["lean_deg"]),
              0.4 < g["speed_m_s"] < 2.2 and 0.5 * m["hip_height"] < g["stride_m"] < 2.2 * m["hip_height"])
        check("%s: the stride and the loop agree, so the feet can't skate: %d frames at %.2f m/s is %.3f m" % (label, g["frames"], g["speed_m_s"], g["frames"] / 30 * g["speed_m_s"]),
              abs(g["frames"] / 30 * moved["speed_m_s"] - g["stride_m"]) < 0.01)
        check("%s: a planted foot slides %.3f cm a step" % (label, c["foot_slide_cm_per_step"]), c["foot_slide_cm_per_step"] < 0.3)
        check("%s: nothing goes more than %.2f cm through the floor" % (label, c["through_floor_cm"]), c["through_floor_cm"] < 0.5)
        check("%s: no joint outside its limits on any frame; clamped on the way: %s; heel lifted up to %.0f degrees to spare the ankle; hips lowered %.1f cm for reach" % (
              label, moved["clamped"] or "nothing", moved["heel_lifted_for_ankle_deg"], moved["hips_lowered_cm"]),
              c["limit_violations"] == 0 and sum(moved["clamped"].values()) <= 6 and moved["out_of_reach_cm"] == 0)
        check("%s: the last frame is the first again" % label, c["loop_seam"] < 1e-5, c["loop_seam"])
        check("%s: the exported file holds the mesh, the %d bones and the walk, and nothing else" % (label, exported["file"]["bones"]),
              exported["only_this_object"] is True and exported["rig"]["animation"] == "walk", exported["file"]["names"])
        walk_file_checks(label, out, bones, tail)
        if tail:
            check("%s: its %.2f m tail has %d bones that follow the hips, lifted %.0f degrees to clear the floor" % (label, m["tail_long"], tail, g["tail_rise_deg"]),
                  tail >= 2 and g["tail_swing_deg"] > 0)
    if "ninja" in gaits:
        troll, ninja = gaits["troll"], gaits["ninja"]
        check("the troll (bulk %.3f) stands wider than the ninja (bulk %.3f): %.2f m against %.2f m" % (troll["bulk"], ninja["bulk"], troll["stance_width_m"], ninja["stance_width_m"]),
              troll["stance_width_m"] > 2 * ninja["stance_width_m"])
        check("it steps slower (%d against %d steps a minute) and sways more of its height (%.1f%% against %.1f%%)" % (
              troll["cadence_steps_per_min"], ninja["cadence_steps_per_min"], troll["sway_cm"] / troll["height"], ninja["sway_cm"] / ninja["height"]),
              troll["cadence_steps_per_min"] < ninja["cadence_steps_per_min"] and troll["sway_cm"] / troll["height"] > 3 * ninja["sway_cm"] / ninja["height"])
        check("its arms are %.2f of its leg length (the ninja's %.2f), so its hands travel %.2f m a swing against %.2f m" % (
              troll["arm"] / troll["leg"], ninja["arm"] / ninja["leg"], troll["hand_travel_m"], ninja["hand_travel_m"]),
              troll["hand_travel_m"] > 2 * ninja["hand_travel_m"])
        check("the ninja crouches (%.1f cm on a %.2f m leg) and lifts its feet higher (%.1f cm against %.1f); the troll's heel barely leaves the ground (%.0f degrees against %.0f)" % (
              ninja["crouch_cm"], ninja["leg"], ninja["foot_lift_cm"], troll["foot_lift_cm"], troll["heel_lift_deg"], ninja["heel_lift_deg"]),
              ninja["foot_lift_cm"] > troll["foot_lift_cm"] and troll["heel_lift_deg"] < ninja["heel_lift_deg"] and ninja["bob_cm"] < troll["bob_cm"])


def test_walk_profile(ctx):
    """The walk profile, by the real runner: a copy of the troll's low-poly version comes back as lowpoly-walk.glb; a run with a recipe, gear and sockets (if one is there) keeps them all on the bones."""
    with open(os.path.join(HERE, "test_gaits.json")) as f:
        said = json.load(f)
    newer = [os.path.dirname(os.path.dirname(p)) for p in sorted(glob.glob(os.path.join(os.path.dirname(ctx["troll"]), "*", "profiles", "midpoly.glb")))
             if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(p)), "lowpoly_build.json"))]
    for run in [ctx["troll"]] + newer[-1:]:
        copy = os.path.join(ctx["out"], "walks", os.path.basename(run))
        os.makedirs(os.path.join(copy, "profiles"), exist_ok=True)
        versions = [v for v in ("lowpoly", "midpoly") if os.path.exists(os.path.join(run, "profiles", v + ".glb"))]
        for name in ["brief.json", "lowpoly_build.json"] + ["profiles/%s%s" % (v, end) for v in versions for end in (".glb", ".json")]:
            if os.path.exists(os.path.join(run, name)):
                shutil.copy(os.path.join(run, name), os.path.join(copy, name))
        traits = next((v for k, v in said.items() if k in run and k != "about"), None)
        if traits:
            with open(os.path.join(copy, "gait.json"), "w") as f:
                json.dump(traits, f)
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", os.path.join(HERE, "tidy_profile.py"), "--",
                              os.path.join(copy, "scene.blend"), os.path.join(copy, "profiles"), "walk"], capture_output=True, text=True)
        label = os.path.basename(run)[20:]
        for version in versions:
            path = os.path.join(copy, "profiles", version + "-walk")
            if not os.path.exists(path + ".json"):
                raise AssertionError("no %s-walk for %s:\n%s" % (version, label, (out.stdout + out.stderr)[-1500:]))
            with open(path + ".json") as f:
                record = json.load(f)
            rig, c = record["rig"], record["animation"]["check"]
            check("%s %s: walks at %.2f m/s, joints placed from the %s, traits %s" % (label, version, record["walk"]["gait"]["speed_m_s"], rig["placed_from"], record["walk"]["traits_from"]),
                  rig["placed_from"] == ("recipe" if os.path.exists(os.path.join(copy, "lowpoly_build.json")) else "mesh")
                  and record["walk"]["traits_from"] == ("given" if traits else "the build"))
            check("%s %s: feet slide %.3f cm, %.2f cm through the floor, no limit broken, no bone outside the mesh" % (label, version, c["foot_slide_cm_per_step"], c["through_floor_cm"]),
                  c["foot_slide_cm_per_step"] < 0.3 and c["through_floor_cm"] < 0.5 and c["limit_violations"] == 0 and rig["bones_outside"] == [])
            cloth_bones = (record.get("cloth") or {}).get("cloth_bones") or []
            doc = walk_file_checks("%s %s" % (label, version), path + ".glb", rig["bones"] + cloth_bones, rig["measure"]["tail_bones"])
            names = [n.get("name") for n in doc["nodes"]]
            if record["sockets"]:
                held = {n["name"]: [names[c] for c in n.get("children", [])] for n in doc["nodes"]}
                check("%s %s: each socket hangs on its bone (hands, head, chest, hips), so a prop there follows" % (label, version),
                      "socket: hand_right" in held["hand_r"] and "socket: hand_left" in held["hand_l"] and "socket: head" in held["head"]
                      and "socket: back" in held["chest"] and "socket: hip" in held["hips"])
            if record["gear"]:
                meshes = sorted(n["name"] for n in doc["nodes"] if "mesh" in n and not n["name"].startswith("body under: "))
                check("%s %s: the body and each gear piece are still meshes of their own, tagged, on the one skeleton: %s" % (label, version, ", ".join(meshes)),
                      meshes == sorted(["body"] + ["gear: " + g["gear"] for g in record["gear"]])
                      and all((n.get("extras") or {}).get("forge") in ("body", "gear") for n in doc["nodes"] if "mesh" in n))
        if len(versions) == 2:
            both = []
            for version in versions:
                with open(os.path.join(copy, "profiles", version + "-walk.json")) as f:
                    both.append(json.load(f))
            check("%s: the low-poly and mid-poly versions get the same body skeleton and the same walk" % label,
                  both[0]["rig"]["joints"] == both[1]["rig"]["joints"] and both[0]["walk"]["gait"]["frames"] == both[1]["walk"]["gait"]["frames"])


def test_run_profile(ctx):
    """The run profile, by the real runner, with no worker: with no clip it is skipped with a note and nothing fails; with a clip (a stick-figure run from the offline tests' pretend worker, cut into a loop) the troll, and a character with a tail if one is there, come back as lowpoly-run.glb, looping, inside their limits."""
    sys.path.insert(0, os.path.join(HERE, "motion"))
    import test_run_clip
    with open(os.path.join(HERE, "test_gaits.json")) as f:
        said = json.load(f)
    tailed = sorted(glob.glob(os.path.join(os.path.dirname(ctx["troll"]), "*lizardkin-warrior")))
    copies = []
    for run in [ctx["troll"]] + tailed[-1:]:
        copy = os.path.join(ctx["out"], "running", os.path.basename(run))
        os.makedirs(os.path.join(copy, "profiles"), exist_ok=True)
        for name in ["brief.json", "lowpoly_build.json", "profiles/lowpoly.glb", "profiles/lowpoly.json", "profiles/lowpoly-walk.json"]:
            if os.path.exists(os.path.join(run, name)):
                shutil.copy(os.path.join(run, name), os.path.join(copy, name))
        with open(os.path.join(copy, "gait.json"), "w") as f:
            json.dump(next(v for k, v in said.items() if k in run and k != "about"), f)
        copies.append(copy)

    def runner(copy):
        return subprocess.run([BLENDER, "-b", "--factory-startup", "-P", os.path.join(HERE, "tidy_profile.py"), "--",
                               os.path.join(copy, "scene.blend"), os.path.join(copy, "profiles"), "run"], capture_output=True, text=True)

    out = runner(copies[0])
    check("with no run clip the profile is skipped, says why, and the runner still ends well",
          out.returncode == 0 and "run skipped: Kimodo not available" in out.stdout and not os.path.exists(os.path.join(copies[0], "profiles", "lowpoly-run.glb")),
          out.stdout[-300:])
    done = test_run_clip.to_the_end(copies, os.path.join(ctx["out"], "running", ".run-cache"))
    speeds = {}
    for copy in copies:
        label = os.path.basename(copy)[20:]
        loop = done["state"][copy]
        out = runner(copy)
        path = os.path.join(copy, "profiles", "lowpoly-run")
        if not os.path.exists(path + ".json"):
            raise AssertionError("no lowpoly-run for %s:\n%s" % (label, (out.stdout + out.stderr)[-1500:]))
        with open(path + ".json") as f:
            record = json.load(f)
        rig, moved, c = record["rig"], record["animation"], record["animation"]["check"]
        speeds[label] = moved["speed_m_s"]
        check("%s: \"%s\"" % (label, done["asks"][copy]["prompt"]), record["run"]["prompt"] == done["asks"][copy]["prompt"])
        check("%s runs on the spot at %.2f m/s (asked for %.2f), %d steps a minute, a loop of %d frames cut from a whole number of strides (%d)" % (
            label, moved["speed_m_s"], done["asks"][copy]["speed_mps"], record["run"]["steps_per_minute"], moved["frames"], loop["strides"]),
              abs(moved["speed_m_s"] - done["asks"][copy]["speed_mps"]) < 0.08 * done["asks"][copy]["speed_mps"]
              and moved["frames"] == loop["frames"] == loop["strides"] * loop["stride_frames"])
        check("%s: the last frame is the first again, and no joint is turned past its limit (%s were held back)" % (label, ", ".join(sorted(moved["clamped"])) or "none"),
              c["loop_seam"] < 1e-4 and c["limit_violations"] == 0, c)
        walk_file_checks(label, path + ".glb", rig["bones"] + ((record.get("cloth") or {}).get("cloth_bones") or []), rig["measure"]["tail_bones"], clip="run")
        if rig["measure"]["tail_bones"]:
            check("%s: its tail has a motion of its own, following the hips (%s)" % (label, record.get("tail")),
                  (record.get("tail") or {}).get("bones") == rig["measure"]["tail_bones"])
    if os.path.exists(os.path.join(ctx["troll"], "profiles", "lowpoly-walk.json")):
        with open(os.path.join(ctx["troll"], "profiles", "lowpoly-walk.json")) as f:
            walks = json.load(f)["walk"]["gait"]["speed_m_s"]
        check("the troll runs faster than it walks (%.2f against %.2f m/s)" % (speeds["cave-troll"], walks), speeds["cave-troll"] > 1.5 * walks)
    # A new clip puts the old files out of date: they are removed, so the runner makes them again.
    with open(os.path.join(copies[0], "gait.json"), "w") as f:
        json.dump(dict(next(v for k, v in said.items() if k in copies[0] and k != "about"), weight=0.5), f)
    test_run_clip.to_the_end(copies, os.path.join(ctx["out"], "running", ".run-cache"))
    check("told to run differently, the troll's old run is cleared away to be made again", not os.path.exists(os.path.join(copies[0], "profiles", "lowpoly-run.glb"))
          and os.path.exists(os.path.join(copies[-1], "profiles", "lowpoly-run.glb")) == (len(copies) > 1))


def test_bone_names(ctx):
    """bones.json: every bone rig.py makes has a SOMA and a Mixamo name, and every SOMA joint is accounted for."""
    with open(os.path.join(TOOLS, "..", "bones.json")) as f:
        table = json.load(f)
    check("all %d body bones are in the table, each with a SOMA and a Mixamo name" % len(BODY_BONES),
          sorted(table["bones"]) == sorted(BODY_BONES) and all(b.get("soma") and b.get("mixamo") for b in table["bones"].values()))
    taken = [b["soma"] for b in table["bones"].values()] + [j for b in table["bones"].values() for j in b.get("soma_also", [])] + list(table["soma_unused"])
    check("SOMA's 30 joints are each mapped, folded into a neighbor, or listed as unused", sorted(taken) == sorted(table["soma_joints"]) and len(table["soma_joints"]) == 30,
          sorted(set(table["soma_joints"]) ^ set(taken)))
    check("no two bones claim the same SOMA or Mixamo joint", len({b["soma"] for b in table["bones"].values()}) == len(BODY_BONES)
          and len({b["mixamo"] for b in table["bones"].values()}) == len(BODY_BONES))


# ---- clothes that sit on the body and move with it ----

def test_drape(ctx):
    """drape.py on the troll: the belt goes on the body, the kilt hangs from under it, the skin they hide is marked; export.py writes that skin apart."""
    out = os.path.join(ctx["out"], "drape", "lowpoly.glb")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    built, draped, again, exported = blender(ctx["troll"] + "/final.glb", [
        ("build.py", {"parts": troll_with_gear(), "gear": TROLL_GEAR, "sockets": True, "name": "Troll (light)", "check": 0}),
        ("drape.py", {}),
        ("drape.py", {}),
        ("export.py", {"object": "Troll (light)", "path": out, "materials": False}),
    ])
    pieces = {p["gear"].split()[-1] if p["gear"] != "iron wrist band" else "wrist band": p for p in draped["pieces"]}
    check("the kilt is taken for loose cloth, the belt and the wrist band for bands: %s" % {n: (p["fit"], p["why"]) for n, p in pieces.items()},
          (pieces["kilt"]["fit"], pieces["belt"]["fit"], pieces["wrist band"]["fit"]) == ("loose", "band", "band"))
    kilt = pieces["kilt"]
    check("the kilt hangs %.2f m from under the belt (z = %.2f), not from wherever it was built" % (kilt["hangs_m"], kilt["hangs_from_z"]),
          kilt["belted_at_z"] is not None and abs(kilt["hangs_from_z"] - kilt["belted_at_z"]) < 1e-6 and 0.2 < kilt["hangs_m"] < 0.5, kilt)
    gap = draped["gap_where_it_touches_cm"]
    check("where cloth touches the body it sat %.1f cm off (worst %.1f); now %.2f cm, one step, all round" % (gap["before"]["median"], gap["before"]["max"], gap["after"]["median"]),
          gap["before"]["median"] > 2.5 and abs(gap["after"]["median"] - draped["clearance_cm"]) < 0.05 and gap["after"]["p95"] < 1.6 * draped["clearance_cm"], gap)
    check("no cloth point is left inside the body, and no skin shows through cloth standing still",
          draped["points_inside_the_body"]["after"] == 0 and draped["skin_showing_through"]["points"] == 0, draped["skin_showing_through"])
    check("it stayed inside the budget: %d triangles before, %d after" % (draped["triangles"]["before"], draped["triangles"]["after"]),
          draped["triangles"]["before"] == built["triangles"] and draped["triangles"]["after"] <= 1.15 * built["triangles"])
    masks = {" + ".join(m["under"]): m["body_triangles"] for m in draped["masks"]}
    check("the skin each piece hides is marked: %s" % masks, masks.get("hide kilt", 0) >= 8, masks)
    check("run again it moves nothing, and takes each piece for what it was", again["moved"] is False
          and {p["piece"]: p["fit"] for p in again["pieces"]} == {p["piece"]: p["fit"] for p in draped["pieces"]}
          and [m["under"] for m in again["masks"]] == [m["under"] for m in draped["masks"]], again["pieces"])
    found = nodes_of(out)
    under = sorted(n for n in found if n.startswith("body under: "))
    check("the .glb has the hidden skin as meshes of its own: %s" % ", ".join(under), "body under: hide kilt" in under and "body" in found)
    check("each tagged with the gear that hides it", found["body under: hide kilt"][0].get("under") == "hide kilt" and found["body under: hide kilt"][0].get("forge") == "body",
          found["body under: hide kilt"][0])
    check("body and hidden skin add up to the whole body: %d triangles" % sum(found[n][2] for n in ["body"] + under),
          sum(found[n][2] for n in ["body"] + under) + sum(found[n][2] for n in found if n.startswith("gear: ")) == draped["triangles"]["after"])
    check("the file says it was draped, and what each part of the kilt was taken for", found["body"][0].get("draped") == 1
          and json.loads(found["gear: hide kilt"][0]["drape"])["hide kilt"][0]["fit"] == "loose", found["gear: hide kilt"][0])
    check("export.py's read-back still says only_this_object", exported["only_this_object"] is True and exported["masks"], exported.get("masks"))
    # A piece says how it is worn; that wins over what its name suggests.
    told = blender(ctx["troll"] + "/final.glb", [
        ("build.py", {"parts": [dict(p, fit="tight") if p["name"] == "kilt" else p for p in troll_with_gear()], "gear": TROLL_GEAR, "name": "Troll (light)", "check": 0}),
        ("drape.py", {"move": False}),
    ])[1]
    check("a piece's own \"fit\" wins over its name", {p["piece"]: (p["fit"], p["why"]) for p in told["pieces"]}["kilt"] == ("tight", "its piece says so"))


CLOTH_LIMITS = {  # the most skin that may come through over a walk: (share of covered point-frames %, deepest cm)
    "lincoln": (6, 4), "ninja": (4, 3), "roosevelt": (2, 1.5), "pirate": (5, 6),
    "troll": (12, 9),  # low poly: eight cloth chains around thighs 43 cm thick; see SKILL.md, "What is weak"
}
CLOTHED = [("lincoln", "*young-lincoln-frontier-wrestler", ["wool trousers", "linen work shirt"], []),
           ("ninja", "*shadow-ninja", ["cloth suit", "shin wraps"], ["hood and mask"]),
           ("roosevelt", "*roosevelt-wrestler-1890s", ["wool singlet", "wool tights"], []),
           ("troll", "*cave-troll", [], ["hide kilt"]),
           ("pirate", "*stocky-pirate-deckhand", ["striped trousers"], ["navy coat"])]


def cloth_numbers(paths):
    """scripts/cloth_check.py on some .glb files, in one background Blender: one dict a file."""
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", os.path.join(HERE, "cloth_check.py"), "--"] + list(paths), capture_output=True, text=True)
    rows = [json.loads(line[6:]) for line in out.stdout.splitlines() if line.startswith("CLOTH ")]
    if len(rows) != len(paths):
        raise AssertionError("cloth_check.py measured %d of %d files:\n%s" % (len(rows), len(paths), (out.stdout + out.stderr)[-1500:]))
    return rows


def dressed_run(ctx, label, pattern):
    """A copy of a character's run with low-poly, mid-poly and walking versions made by the real runner.
    Lincoln, the ninja and Roosevelt have block-outs with gear and recipes of their own; the troll and the
    pirate predate gear, so theirs are the recorded block-outs with gear named. Returns (the copy, its run)."""
    runs = sorted(glob.glob(os.path.join(os.path.dirname(ctx["troll"]), pattern)))
    if not runs:
        return None, None
    run = runs[-1]
    if label == "troll":
        copy = profiles(ctx, run, troll_with_gear(), TROLL_GEAR, ["lowpoly", "midpoly"])[0]
    elif label == "pirate":
        with open(os.path.join(HERE, "test_blockouts.json")) as f:
            case = json.load(f)["stocky-pirate-deckhand"]
        copy = profiles(ctx, run, pirate_dressed(case), case["gear"], ["lowpoly", "midpoly"])[0]
    else:
        copy = os.path.join(ctx["out"], "runs", os.path.basename(run))
        os.makedirs(copy, exist_ok=True)
        for name in ("scene.blend", "brief.json", "parts.json", "lowpoly.glb", "lowpoly_build.json", "gait.json"):
            if os.path.exists(os.path.join(run, name)):
                shutil.copy(os.path.join(run, name), os.path.join(copy, name))
    with open(os.path.join(HERE, "test_gaits.json")) as f:
        said = json.load(f)
    traits = next((v for k, v in said.items() if k in run and k != "about"), None)
    if traits:
        with open(os.path.join(copy, "gait.json"), "w") as f:
            json.dump(traits, f)
    wanted = ["walk"] if label in ("troll", "pirate") else ["lowpoly", "midpoly", "walk"]
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", os.path.join(HERE, "tidy_profile.py"), "--",
                          os.path.join(copy, "scene.blend"), os.path.join(copy, "profiles")] + wanted, capture_output=True, text=True)
    for version in ("lowpoly", "midpoly"):
        if not os.path.exists(os.path.join(copy, "profiles", version + "-walk.json")):
            raise AssertionError("no %s-walk for %s:\n%s" % (version, label, (out.stdout + out.stderr)[-1500:]))
    return copy, run


def test_cloth(ctx):
    """Clothes sit on the body and move with it: five characters, low poly and mid poly, made by the real runner and measured over every frame of their walk."""
    for label, pattern, tight, loose in CLOTHED:
        copy, run = dressed_run(ctx, label, pattern)
        if not copy:
            print("    skipped: no %s run" % pattern)
            continue
        old = [os.path.join(run, "profiles", v + "-walk.glb") for v in ("lowpoly", "midpoly")]
        old = [p for p in old if os.path.exists(p)] if label not in ("troll", "pirate") else []
        new = [os.path.join(copy, "profiles", v + "-walk.glb") for v in ("lowpoly", "midpoly")]
        numbers = cloth_numbers(new + old)
        for i, version in enumerate(("lowpoly", "midpoly")):
            who = "%s %s" % (label, version)
            now = numbers[i]
            before = numbers[2 + i] if len(old) == 2 else None
            with open(os.path.join(copy, "profiles", version + ".json")) as f:
                made = json.load(f)
            with open(os.path.join(copy, "profiles", version + "-walk.json")) as f:
                walked = json.load(f)
            draped = [s["result"] for s in made["steps"] if s["script"] == "drape.py"][0]
            fits = {(p["gear"], p["fit"]) for p in draped["pieces"]}
            check("%s: worn tight: %s; loose: %s" % (who, ", ".join(tight) or "nothing", ", ".join(loose) or "nothing"),
                  all((g, "tight") in fits for g in tight) and all((g, "loose") in fits for g in loose), sorted(fits))

            # the gap: tight clothes lie one step off the body
            gap = draped["gap_where_it_touches_cm"]
            check("%s: where clothes touch the body they sat %.2f cm off it (95 in 100 within %.2f); now %.2f cm (%.2f)" % (
                  who, gap["before"]["median"], gap["before"]["p95"], gap["after"]["median"], gap["after"]["p95"]),
                  gap["after"]["median"] < gap["before"]["median"] and gap["after"]["median"] <= 2 * draped["clearance_cm"] and gap["after"]["p95"] < gap["before"]["p95"] + 0.5, gap)
            for g in tight:
                off = now["gap_cm"][g]
                check("%s: the %s sits %.2f cm off the body, in the walking file too" % (who, g, off["median"]), off["median"] <= 2.2 * draped["clearance_cm"], off)
            inside = draped["points_inside_the_body"]
            check("%s: %d cloth points were inside the body, %d are" % (who, inside["before"], inside["after"]),
                  inside["after"] <= max(8, inside["before"] // 2), inside)

            # poke-through, over every frame of the walk
            poke, share, deep = now["poke_through"], CLOTH_LIMITS[label][0], CLOTH_LIMITS[label][1]
            was = " (before: %d, %.2f%%, %.1f cm)" % (before["poke_through"]["point_frames"], before["poke_through"]["share_%"], before["poke_through"]["deepest_cm"]) if before else ""
            check("%s: over %d frames of its walk, skin is through its clothes on %d point-frames, %.2f%% of those covered, %.1f cm at the deepest%s" % (
                  who, now["frames"], poke["point_frames"], poke["share_%"], poke["deepest_cm"], was),
                  now["frames"] >= 13 and poke["share_%"] <= share and poke["deepest_cm"] <= deep, poke)
            if before:
                check("%s: no more than before, give or take" % who, poke["point_frames"] <= 1.25 * before["poke_through"]["point_frames"] + 20,
                      (poke["point_frames"], before["poke_through"]["point_frames"]))
            check("%s: %d body triangles are hidden while it is dressed, in %d meshes tagged with the gear that hides them" % (
                  who, now["triangles"]["body_hidden_when_dressed"], len(now["body_meshes"]) - 1),
                  now["triangles"]["body_hidden_when_dressed"] > 0 and "body" in now["body_meshes"] and len(now["body_meshes"]) > 1)

            # the budget
            block = draped["triangles"]["before"]
            check("%s: %d triangles as built, %d in the file, %d drawn with everything on" % (who, block, now["triangles"]["in_the_file"], now["triangles"]["drawn_dressed"]),
                  now["triangles"]["in_the_file"] <= 1.25 * block and now["triangles"]["drawn_dressed"] <= 1.1 * block
                  and (version == "lowpoly" or now["triangles"]["in_the_file"] <= 8000 * 1.2), now["triangles"])  # the new edge loops may add 12%, a last cut a little more, and a .glb counts a few more than build.py does

            # weights from the body; loose cloth on bones of its own, inside their limits, with no seam
            cloth = walked["cloth"]
            moved = sum(m["from_the_body_under_it"] + m["spread_in_from_the_cloth_around"] for m in cloth["meshes"])
            check("%s: %d cloth points take the body's weights (%d of them spread in from the cloth around)" % (
                  who, moved, sum(m["spread_in_from_the_cloth_around"] for m in cloth["meshes"])), moved > 50)
            bones = walked["rig"]["bones"] + cloth["cloth_bones"]
            walk_file_checks(who, new[i], bones, walked["rig"]["measure"]["tail_bones"])
            check("%s: the walk itself is as it was: feet slide %.3f cm, no limit broken" % (who, walked["animation"]["check"]["foot_slide_cm_per_step"]),
                  walked["animation"]["check"]["foot_slide_cm_per_step"] < 0.3 and walked["animation"]["check"]["limit_violations"] == 0)
            if loose:
                swing = walked["swing"]
                check("%s: %d cloth bones in %d chains hang from the %s" % (who, len(cloth["cloth_bones"]), swing["chains"], ", ".join(sorted({c["hangs_from"] for c in cloth["loose"]}))),
                      cloth["cloth_bones"] and all(c["hangs_from"] in ("hips", "spine", "chest", "neck", "head") for c in cloth["loose"]) and walked["animation"]["then"] == ["swing.py"])
                c = swing["check"]
                check("%s: they swing up to %.0f degrees and the hem travels %.1f cm, every turn inside its limit, no joint more than %.2f cm into a leg" % (
                      who, c["most_swing_deg"], c["hem_travels_cm"], c["deepest_in_a_leg_cm"]),
                      c["limit_violations"] == 0 and c["most_swing_deg"] > 1 and c["deepest_in_a_leg_cm"] < 8 and now["cloth_bones"]["bones"] == len(cloth["cloth_bones"]), c)
                check("%s: the loop has no seam in the cloth either (eased %.3f degrees onto its start)" % (who, swing["eased_at_the_seam_deg"]),
                      c["loop_seam"] < 1e-5 and swing["eased_at_the_seam_deg"] < 3)
            else:
                check("%s: nothing hangs, so no cloth bones" % who, cloth["cloth_bones"] == [] and walked["animation"]["then"] == [])


# ---- the base body: a real body under clothes that hide it ------------------

def cut_params(run, out, **more):
    """garment.py's PARAMS for a run-shaped folder (image.png, mesh.glb, base/image.png, base/mesh.glb)."""
    os.makedirs(os.path.join(out, "cut"), exist_ok=True)
    params = {"picture": run + "/image.png", "base_picture": run + "/base/image.png", "clothed": run + "/mesh.glb", "base": run + "/base/mesh.glb",
              "out": os.path.join(out, "cut"), "body_out": os.path.join(out, "body.glb"), "overlay": os.path.join(out, "votes")}
    params.update(more)
    return params


def made_up_character(ctx):
    """A T-pose figure of tubes in a long skirt, with and without it (scripts/base_fixture.py), made once."""
    out = os.path.join(ctx["out"], "made-up")
    if not os.path.exists(os.path.join(out, "truth.json")):
        done = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", os.path.join(HERE, "base_fixture.py"), "--", out], capture_output=True, text=True)
        if "RESULT " not in done.stdout:
            raise AssertionError("base_fixture.py failed:\n%s" % (done.stdout + done.stderr)[-1500:])
    with open(os.path.join(out, "truth.json")) as f:
        return out, json.load(f)


def test_garment_made_up(ctx):
    """garment.py on a made-up figure whose every face is known: the skirt comes out exactly, a shrunk base body is laid back on, and a moved picture, an unchanged picture and a different pose are each turned down with numbers."""
    run, truth = made_up_character(ctx)
    skirt = [{"name": "long skirt", "slot": "hip", "kind": "worn"}]
    out = os.path.join(ctx["out"], "made-up-cut")
    got = blender("-", [("garment.py", cut_params(run, out, garments=skirt))])[0]
    check("the pictures line up: no edge moved, %.0f%% of the figure changed" % got["pictures"]["changed_pct"],
          got["pictures"]["ok"] and all(abs(e["moved_pct"]) < 0.5 for e in got["pictures"]["edges"].values()) and 40 < got["pictures"]["changed_pct"] < 80, got["pictures"])
    check("the framing is found: seen from the front the mesh covers %.0f%% of the figure, not mirrored" % got["view"]["clothed"]["overlap_pct"],
          got["view"]["clothed"]["overlap_pct"] > 75 and not got["view"]["clothed"]["mirrored"] and abs(got["view"]["clothed"]["stretch"] - 1) < 0.02, got["view"])
    check("the base body already fits: uncovered parts %.2f%% of the height apart" % got["fit"]["off_pct"]["median"],
          got["fit"]["ok"] and got["fit"]["off_pct"]["p90"] < 0.1 and abs(got["fit"]["scale"] - 1) < 0.002, got["fit"])
    piece = got["garments"][0]
    check("the skirt is cut exactly: %d faces of %d, in one piece" % (piece["faces"], truth["faces"]),
          got["ok"] and piece["faces"] == truth["skirt_faces"] and piece["pieces"] == 1, (piece["faces"], truth["skirt_faces"]))
    check("it runs from %.2f to %.2f of the height, whole round its top, none of it in the body's colors" % (piece["bottom"], piece["top"]),
          abs(piece["top"] - truth["skirt_top"]) < 0.02 and abs(piece["bottom"] - truth["skirt_bottom"]) < 0.02
          and piece["closed_round_its_top_pct"] == 100 and piece["other_colors_pct"] == 0, piece)
    votes = got["votes"]["said_garment"]
    check("each clue alone says more or less than the skirt (picture %d, color %d, distance %d faces); two agreeing say %d" % (
          votes["picture"]["faces"], votes["color"]["faces"], votes["distance"]["faces"], got["votes"]["two_or_more"]["faces"]),
          votes["picture"]["faces"] > truth["skirt_faces"] and votes["color"]["faces"] == truth["skirt_faces"]
          and got["votes"]["two_or_more"]["faces"] == truth["skirt_faces"], got["votes"]["agreement"])
    written = read_glb(piece["file"])
    check("the file holds the skirt and nothing else, with its texture", written["meshes"] == 1 and written["triangles"] == truth["skirt_faces"] and written["images"] >= 1, written)
    check("the body is written too, and the three vote pictures", read_glb(got["body"])["triangles"] == truth["base_faces"]
          and all(os.path.getsize(path) > 2000 for path in got["overlay"]) and len(got["overlay"]) == 3, got["overlay"])

    # a base body that came out at another size and place is laid back on, by its uncovered parts
    small = blender("-", [("garment.py", cut_params(run, out + "-small", garments=skirt, base=run + "/small/mesh.glb", overlay=None))])[0]
    fit = small["fit"]
    check("a base body made 10%% small and shifted sat %.1f%% off; scaled x%.3f it sits %.2f%% off, and the same skirt is cut" % (fit["before_pct"], fit["scale"], fit["off_pct"]["median"]),
          small["ok"] and fit["before_pct"] > 1 and abs(fit["scale"] - 1 / truth["small"]["scale"]) < 0.005 and fit["off_pct"]["p90"] < 0.2
          and small["garments"][0]["faces"] == truth["skirt_faces"], fit)

    # what doesn't line up is turned down, with the numbers
    moved = blender("-", [("garment.py", cut_params(run, out + "-moved", garments=skirt, base_picture=run + "/moved/image.png"))])[0]
    check("a second picture with the figure slid sideways is turned down: %s" % (moved["why"] or [""])[0],
          not moved["ok"] and not moved["pictures"]["ok"] and "garments" not in moved and abs(moved["pictures"]["edges"]["left"]["moved_pct"]) > 4
          and "edge moved" in moved["why"][0], moved["pictures"])
    same = blender("-", [("garment.py", cut_params(run, out + "-same", garments=skirt, base_picture=run + "/image.png"))])[0]
    check("the same picture twice is turned down: %s" % (same["why"] or [""])[0], not same["ok"] and "nothing changed" in same["why"][0], same["why"])
    posed = blender("-", [("garment.py", cut_params(run, out + "-posed", garments=skirt, base=run + "/posed/mesh.glb"))])[0]
    check("a base body in another pose is turned down, and nothing is cut: %s" % (posed["why"] or [""])[0],
          not posed["ok"] and posed["pictures"]["ok"] and "garments" not in posed and not os.listdir(os.path.join(out + "-posed", "cut")), posed["why"])
    only = blender("-", [("garment.py", {"picture": run + "/image.png", "base_picture": run + "/base/image.png"})])[0]
    check("with no meshes it only compares the pictures", only["ok"] and "fit" not in only and "garments" not in only)

    # two garments share the cut by where their slots sit
    two = blender("-", [("garment.py", cut_params(run, out + "-two", overlay=None, garments=[
        {"name": "long skirt", "slot": "hip"}, {"name": "hood", "slot": "head"}]))])[0]
    check("named with a hood too, the skirt still gets every face and the hood none",
          [g["faces"] for g in two["garments"]] == [truth["skirt_faces"], 0] and two["garments"][1]["file"] is None, two["garments"])


def dancer_runs(ctx):
    """The flamenco dancer's clothed run and its hand-made base run, if this machine has them."""
    runs = os.path.dirname(ctx["troll"])
    clothed = sorted(glob.glob(os.path.join(runs, "*flamenco-dancer")))
    base = sorted(glob.glob(os.path.join(runs, "*flamenco-dancer-base")))
    return (clothed[-1], base[-1]) if clothed and base else None


def test_garment_dancer(ctx):
    """garment.py on the flamenco dancer (read only): her base body fits without help, and the skirt comes out whole up to the waistband, where cutting by distance alone tore the upper skirt away, with no tights or shoes in it."""
    found = dancer_runs(ctx)
    if not found:
        check("no flamenco-dancer runs here: skipped", True)
        return
    clothed, base = found
    out = os.path.join(ctx["out"], "dancer")
    got = blender("-", [("garment.py", cut_params(clothed, out, garments=[{"name": "ruffled skirt", "slot": "hip", "kind": "worn"}],
                                                   base_picture=base + "/image.png", base=base + "/mesh.glb"))])[0]
    pictures = got["pictures"]
    check("the edited picture kept the figure in place: edges moved %s%%, %.2f%% of it changed in slivers" % (
          [e["moved_pct"] for e in pictures["edges"].values()], pictures["slivers_pct"]),
          pictures["ok"] and all(abs(e["moved_pct"]) < 1 for e in pictures["edges"].values()) and pictures["slivers_pct"] < 2, pictures)
    check("the framing: from the front the clothed mesh covers %.0f%% of the figure in the picture and the base body %.0f%%" % (
          got["view"]["clothed"]["overlap_pct"], got["view"]["base"]["overlap_pct"]),
          min(got["view"]["clothed"]["overlap_pct"], got["view"]["base"]["overlap_pct"]) > 80 and not got["view"]["clothed"]["mirrored"], got["view"])
    fit = got["fit"]
    check("the two meshes line up as they came: uncovered parts %.2f%% of the height apart before, %.2f%% after (nine in ten within %.2f%%), scale x%.4f" % (
          fit["before_pct"], fit["off_pct"]["median"], fit["off_pct"]["p90"], fit["scale"]),
          fit["ok"] and fit["before_pct"] < 0.4 and fit["off_pct"]["median"] < 0.3 and fit["off_pct"]["p90"] < 1.2 and abs(fit["scale"] - 1) < 0.01, fit)
    agree = got["votes"]["agreement"]
    said = got["votes"]["said_garment"]
    check("the clues: picture %.0f%%, color %.0f%%, distance %.0f%% of the surface; all three agree on %.0f%%" % (
          said["picture"]["area_pct"], said["color"]["area_pct"], said["distance"]["area_pct"], agree["picture + color + distance"]["area_pct"]),
          all(50 < said[k]["area_pct"] < 85 for k in said) and agree["picture + color + distance"]["area_pct"] > 45, said)
    check("the upper skirt, which hugs the hips, is kept by picture and color where distance says no: %d faces, %.1f%% of the surface" % (
          agree["picture + color"]["faces"], agree["picture + color"]["area_pct"]),
          agree["picture + color"]["faces"] > 15000 and agree["picture + color"]["area_pct"] > 4, agree["picture + color"])
    skirt = got["garments"][0]
    check("the skirt: %d faces, %.0f%% of the surface, from %.3f up to %.3f of the height" % (skirt["faces"], skirt["area_pct"], skirt["bottom"], skirt["top"]),
          got["ok"] and skirt["faces"] > 170000 and skirt["top"] > 0.6 and 0.095 < skirt["bottom"] < 0.13, skirt)
    check("whole at the waistband: faces all the way round just under its top (%s%%)" % skirt["closed_round_its_top_pct"], skirt["closed_round_its_top_pct"] == 100)
    check("no tights or shoe scraps: %d piece(s), %.1f%% of it in colors of the rest of the figure, nothing below the hem" % (skirt["pieces"], skirt["other_colors_pct"]),
          skirt["pieces"] <= 2 and skirt["other_colors_pct"] < 8, skirt)
    clean = got["cleanup"]
    check("cleaned up: %d faces grown to the color seam, %d scraps dropped (%d faces), %d holes closed (%d faces)" % (
          clean["faces_grown_to_the_color_seam"], clean["crumbs_dropped"]["pieces"], clean["crumbs_dropped"]["faces"], clean["holes_closed"]["holes"], clean["holes_closed"]["faces"]),
          clean["faces_grown_to_the_color_seam"] > 1000 and clean["crumbs_dropped"]["pieces"] > 0 and clean["holes_closed"]["holes"] > 0, clean)
    check("where the real hips are fuller than the guess, %d skirt points are lifted onto the body, %.2f%% of the height at most" % (
          skirt["points_lifted_onto_the_body"], skirt["lifted_at_most_pct"]), 0 < skirt["points_lifted_onto_the_body"] < 30000 and skirt["lifted_at_most_pct"] < 3, skirt)
    written = read_glb(skirt["file"])
    check("the skirt's file holds one textured mesh of %d triangles" % written["triangles"], written["meshes"] == 1 and written["triangles"] == skirt["faces"] and written["images"] >= 1, written)
    sheet = os.path.join(ctx["out"], "dancer-sheet.png")
    done = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", os.path.join(HERE, "base_shots.py"), "--", got["body"], sheet, skirt["file"],
                           "--votes", os.path.join(out, "votes")], capture_output=True, text=True)
    check("pictures to judge it by: %s (body, skirt, both; front and quarter; then the votes)" % sheet, os.path.exists(sheet) and os.path.getsize(sheet) > 100000, done.stdout[-300:])
    ctx["dancer_cut"] = {"clothed": clothed, "body": got["body"], "skirt": skirt["file"], "top": skirt["top"]}


def test_follow(ctx):
    """follow.py: the base body and its skirt make the same move the finish made (turned, sized, stood on the floor), from what stand.py kept or, without that, from a fit; a move it can't find is turned down."""
    cut = ctx.get("dancer_cut")
    if cut:
        who, raw, pieces, size = "the dancer", cut["clothed"] + "/mesh.glb", [cut["body"], cut["skirt"]], 1.65
    else:
        run, _ = made_up_character(ctx)
        who, raw, pieces, size = "the made-up figure", run + "/mesh.glb", [run + "/base/mesh.glb"], 1.8
    out = os.path.join(ctx["out"], "follow")
    os.makedirs(out, exist_ok=True)
    stood = blender("-", [("open.py", {"mesh": raw, "name": "Finished"}), ("stand.py", {"turn": [0, 0, 180], "size": size, "size_of": "height"}),
                          ("export.py", {"path": os.path.join(out, "final.glb"), "object": "Finished"})], save=os.path.join(out, "scene.blend"))[1]
    check("%s is finished the way the Blender step does it: turned 180, %.2f m tall, on the floor; stand.py reports the move" % (who, stood["size"][2]),
          abs(stood["size"][2] - size) < 1e-3 and len(stood["placed"]) == 16 and abs(abs(stood["placed"][0]) - stood["placed"][10]) < 1e-4 and stood["placed"][0] < 0, stood["placed"])

    def jobs(tag):
        return [{"from": path, "to": os.path.join(out, "%s-%s" % (tag, os.path.basename(path)))} for path in pieces]

    kept = blender(os.path.join(out, "scene.blend"), [("follow.py", {"raw": raw, "follow": jobs("kept")})])[0]
    check("from the saved scene, the move is the one stand.py kept; the raw mesh moved by it lands %.3f%% of the height from the finished one" % kept["check"]["typical_pct"],
          kept["ok"] and kept["move_from"] == "kept by stand.py" and kept["check"]["typical_pct"] < 0.01
          and max(abs(a - b) for a, b in zip(kept["placed"], stood["placed"])) < 1e-4, kept["check"])
    fitted = blender(os.path.join(out, "final.glb"), [("follow.py", {"raw": raw, "follow": jobs("fitted")})])[0]
    check("from the finished .glb alone, the move is fitted: same turn, scale within %.2f%%, the raw mesh lands %.3f%% away" % (
          100 * abs(fitted["scale"] / kept["scale"] - 1), fitted["check"]["typical_pct"]),
          fitted["ok"] and fitted["move_from"] == "fitted" and abs(fitted["scale"] / kept["scale"] - 1) < 0.005 and fitted["check"]["typical_pct"] < 0.3
          and fitted["placed"][0] < 0 and fitted["placed"][5] < 0, fitted["placed"])
    body = kept["written"][0]
    check("the base body follows: it stands on the floor (lowest point %.3f m), %.2f m tall, centered" % (body["min"][2], body["max"][2] - body["min"][2]),
          abs(body["min"][2]) < 0.02 * size and abs((body["max"][2] - body["min"][2]) - size) < 0.03 * size and abs(body["min"][0] + body["max"][0]) < 0.05 * size, body)
    check("each followed file is written and holds its mesh", all(read_glb(w["to"])["triangles"] == read_glb(w["from"])["triangles"] for w in kept["written"]),
          [w["to"] for w in kept["written"]])
    if cut:
        skirt = kept["written"][1]
        check("the skirt follows too: its top is at %.2f m, where the waistband is on the finished dancer" % skirt["max"][2],
              abs(skirt["max"][2] - cut["top"] * size) < 0.02 * size and skirt["min"][2] > 0.08 * size, skirt)

    # a move that isn't a quarter turn: kept, it is followed; fitted, it is turned down
    odd = blender("-", [("open.py", {"mesh": raw, "name": "Finished"}), ("stand.py", {"turn": [0, 0, 30], "size": size, "size_of": "height"}),
                        ("follow.py", {"raw": raw, "follow": []}),
                        ("follow.py", {"raw": raw, "follow": jobs("odd"), "placed": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]})])
    check("a 30 degree turn is followed from what stand.py kept (%.3f%% off)" % odd[2]["check"]["typical_pct"], odd[2]["ok"] and odd[2]["check"]["typical_pct"] < 0.01)
    check("a wrong move is turned down and nothing is written: %s" % (odd[3]["why"] or [""])[0],
          not odd[3]["ok"] and odd[3]["written"] == [] and not os.path.exists(os.path.join(out, "odd-" + os.path.basename(pieces[0]))), odd[3]["check"])
    twice = blender("-", [("open.py", {"mesh": raw, "name": "Finished"}), ("stand.py", {"size": size, "size_of": "height"}), ("stand.py", {"turn": [0, 0, 90]}),
                          ("follow.py", {"raw": raw, "follow": []})])
    check("stand.py run twice (size, then a quarter turn) keeps both moves multiplied up", twice[3]["ok"] and twice[3]["move_from"] == "kept by stand.py"
          and twice[3]["check"]["typical_pct"] < 0.01 and abs(twice[3]["placed"][1]) > 0.5, twice[3]["placed"])


def test_open_add(ctx):
    """open.py "add": a second mesh comes in beside the first (a base body beside the clothed mesh) and nothing is removed."""
    run, truth = made_up_character(ctx)
    first, second, again = blender("-", [
        ("open.py", {"mesh": run + "/mesh.glb", "scene": "Low poly", "name": "Reference"}),
        ("open.py", {"mesh": run + "/base/mesh.glb", "scene": "Low poly", "name": "Body", "add": True}),
        ("measure.py", {"object": "Body"}),
    ])
    check("the base body comes in as \"Body\" and the reference stays", second["object"] == "Body" and second["removed_first"] == 0 and second["scene"] == first["scene"]
          and second["triangles"] == truth["base_faces"], second)
    check("measure.py measures the one it is told to", again["regions"] and again["regions"][0]["vertices"] > 0, again["regions"][:1])


TESTS = [test_safe, test_open_stand, test_measure, test_build_kettle, test_build_troll, test_split, test_polish, test_face, test_face_human,
         test_gear, test_denser, test_midpoly, test_midpoly_others, test_bone_names, test_walk, test_walk_profile, test_run_profile, test_drape, test_cloth,
         test_garment_made_up, test_garment_dancer, test_follow, test_open_add]


def main(argv):
    only = keep = None
    if "--only" in argv:
        i = argv.index("--only")
        only = argv[i + 1]
        del argv[i:i + 2]
    if "--keep" in argv:
        i = argv.index("--keep")
        keep = os.path.abspath(argv[i + 1])
        del argv[i:i + 2]
        os.makedirs(keep, exist_ok=True)
    runs = os.path.abspath(argv[0] if argv else os.path.join(HERE, "..", "runs"))
    ctx = {"out": keep or tempfile.mkdtemp(prefix="forge-tools-")}
    for key, pattern in (("troll", "*cave-troll"), ("kettle", "*iron-kettle")):
        found = sorted(glob.glob(os.path.join(runs, pattern)))
        if not found:
            print("no %s run in %s" % (pattern, runs))
            return 2
        ctx[key] = found[-1]
    failed = 0
    for test in TESTS:
        if only and only not in test.__name__:
            continue
        print("%s: %s" % (test.__name__[5:], test.__doc__))
        try:
            test(ctx)
        except Exception as e:  # a failed check, or a result missing what a check reads
            failed += 1
            print("    FAILED: %s: %s" % (type(e).__name__, str(e)[:1500]))
    print("%s (outputs in %s)" % ("%d case(s) failed" % failed if failed else "all passed", ctx["out"]))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
