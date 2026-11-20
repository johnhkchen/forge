"""Try the Blender tools against real runs, in a background Blender.

    python3 scripts/test_tools.py [RUNS_DIR] [--only NAME] [--keep DIR]

RUNS_DIR (default: runs) must hold the cave-troll and iron-kettle runs. The
live Blender is never touched: every case starts its own `blender -b`, loads
a run's file through scripts/tidy_headless.py, and runs the same script text
Claude would send, with PARAMS filled in. About a minute, one Blender at a
time. Nothing is written into the runs; outputs go to a temp folder (--keep
DIR to look at them afterwards).

What each case shows is in its docstring; `--only build` runs the cases
whose name contains "build".
"""
import glob
import json
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", ".claude", "skills", "tidy-mesh", "scripts")
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
sys.path.insert(0, HERE)
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


TESTS = [test_safe, test_open_stand, test_measure, test_build_kettle, test_build_troll, test_split, test_polish, test_face, test_face_human]


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
