"""Give a finished character an anatomical body, in a background Blender, without asking Claude.

    blender -b --factory-startup -P scripts/auto_body.py -- RUN_DIR OUT_DIR [--follow 1.0] [--chunky 1.0]
        [--limbs 1.0] [--head-size 1.0] [--keep NAME,NAME] [--drop NAME,NAME] [--extra PIECES.json]
        [--head-box x0,y0,z0,x1,y1,z1] [--kind human|creature]

It does what the block-out step does by hand, with the same tools Claude sends
(open.py, landmarks.py, face.py, build.py, drape.py, export.py):

1. brings in RUN_DIR/final.glb as "Reference", and RUN_DIR/base/final.glb (the
   real body under clothes that hide it) as "Body" when the run has one;
2. finds the landmarks and reads the body's surface (landmarks.py), off the
   base body when there is one;
3. builds a "body" piece from them, and with it every piece of the run's own
   block-out that is not body: the head and face, hair, and all the gear
   (lowpoly_build.json). The old trunk, neck, arms, hands, legs and feet go;
4. lays the clothes on the new body (drape.py) and writes OUT_DIR/lowpoly.glb
   and OUT_DIR/lowpoly_build.json.

OUT_DIR is never the run's own folder unless you say so: the run's block-out
is left alone. Point `just tidy` at a copy of the run with these two files in
it to make the profiles and the walk.

Which old pieces are body is told by name (torso, arm, leg, hand, foot...);
--keep and --drop put a wrong guess right. A run with no recipe gets a body
and, with --head-box, a head from face.py; --extra adds pieces of your own.

Where clothes or armor that stay cover the new body, the body is drawn in a
little so it sits under them, not through them: 0.7% of the height under
cloth, 1.4% under what is stiff or was never marked as gear, 2% for a foot in
a shoe.
"""
import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", ".claude", "skills", "tidy-mesh", "scripts")
sys.path.insert(0, HERE)
import blockout_recipe  # noqa: E402

BODY_WORDS = ("torso", "trunk", "chest", "belly", "abdomen", "hips", "pelvis", "waist", "neck", "arm", "shoulder", "hand", "thumb",
              "fist", "palm", "finger", "leg", "thigh", "shin", "calf", "knee", "foot", "feet", "toe", "heel", "body")
STRETCH_WORDS = {"trunk": ("torso", "trunk", "chest", "belly", "hips", "body"), "neck": ("neck",), "arm": ("arm",), "hand": ("hand", "fist", "palm"),
                 "leg": ("leg", "thigh"), "foot": ("foot", "feet")}


def run_script(name, params):
    """Run a skill script with its PARAMS updated, as Claude would over MCP, and return the JSON it printed."""
    with open(os.path.join(SCRIPTS, name)) as f:
        source = f.read()
    head, _, tail = source.partition("\nimport ")
    namespace = {"__name__": "__main__"}
    exec(head, namespace)
    namespace["PARAMS"].update(params)
    captured = []

    def capture(*args, **kwargs):
        text = " ".join(str(a) for a in args)
        if text.startswith("RESULT "):
            captured.append(json.loads(text[len("RESULT "):]))

    namespace["print"] = capture
    exec("import " + tail, namespace)
    return captured[-1] if captured else None


def is_body(piece, keep, drop):
    """Is this piece of the old block-out part of the body the new one replaces?"""
    name = piece["name"].lower()
    if piece["name"] in keep:
        return False
    if piece["name"] in drop:
        return True
    if piece.get("gear") or "head" in piece or "head" in name or "lumps" in piece or "box" in piece:
        return False
    words = name.replace("_", " ").replace("-", " ").split()
    return any(w.rstrip("s") in BODY_WORDS or w in BODY_WORDS for w in words)


def old_color(dropped, stretch):
    for piece in dropped:
        words = piece["name"].lower().replace("_", " ").split()
        if any(w in STRETCH_WORDS[stretch] for w in words) and piece.get("color"):
            return piece["color"]
    return None


def covers(owner, marks, tall, base):
    """Where what stays covers each stretch of the body, as [from, to, how far to draw the body in]. Read off
    the pieces build.py just made: a piece covers a stretch where its box holds the limb's middle."""
    if base:  # the body was read off the real one: nothing to make room for
        return {}
    spots = {
        "trunk": (2, marks["crotch"][2], marks["neck_base"][2], [0.0, marks["waist"][1]]),
        "arm": (0, marks["armpit"][0], marks["wrist"][0], [marks["elbow"][1], marks["elbow"][2]]),
        "hand": (0, marks["wrist"][0], marks["fingertip"][0], [marks["wrist"][1], marks["wrist"][2]]),
        "leg": (2, marks["ankle"][2], marks["crotch"][2], [marks["knee"][0], marks["knee"][1]]),
        "foot": (1, marks["toe"][1], marks["heel"][1], [marks["ankle"][0], 0.5 * marks["ankle"][2]]),
    }
    under = {}
    for obj in bpy.data.objects:
        if obj.get("piece_of") != owner or obj.get("of"):
            continue
        spec = json.loads(obj["spec"])
        if "head" in spec or not obj.data.vertices:
            continue
        side = [v.co for v in obj.data.vertices if v.co.x >= -1e-6 or not spec.get("mirror")]  # a mirrored piece: its +x twin
        lo = [min(p[i] for p in side) for i in range(3)]
        hi = [max(p[i] for p in side) for i in range(3)]
        if lo[2] > marks["chin"][2] - 0.01 * tall:  # on the head
            continue
        stiff = spec.get("fit") == "stiff" or not spec.get("gear")
        for stretch, (axis, start, end, middle) in spots.items():
            others = [i for i in range(3) if i != axis]
            if not all(lo[i] - 0.01 * tall <= m <= hi[i] + 0.01 * tall for i, m in zip(others, middle)):
                continue
            a, b = max(lo[axis], min(start, end)), min(hi[axis], max(start, end))
            if b - a < 0.03 * tall:
                continue
            under.setdefault(stretch, []).append([round(a - 0.01 * tall, 4), round(b + 0.01 * tall, 4), round((0.02 if stretch == "foot" else 0.014 if stiff else 0.007) * tall, 4)])
    return under


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    flags = {}
    while len(args) > 2 and args[-2].startswith("--"):
        flags[args[-2][2:]] = args[-1]
        args = args[:-2]
    if len(args) != 2:
        sys.exit(__doc__)
    run, out = os.path.abspath(args[0]), os.path.abspath(args[1])
    os.makedirs(out, exist_ok=True)
    keep = [n for n in flags.get("keep", "").split(",") if n]
    drop = [n for n in flags.get("drop", "").split(",") if n]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    run_script("open.py", {"mesh": os.path.join(run, "final.glb"), "scene": "Low poly", "name": "Reference"})
    base = os.path.exists(os.path.join(run, "base", "final.glb"))
    if base:
        run_script("open.py", {"mesh": os.path.join(run, "base", "final.glb"), "scene": "Low poly", "name": "Body", "add": True})
    scene = bpy.context.scene

    recipe = {"pieces": [], "gear": [], "scans": {}, "shading": "flat"}
    if os.path.exists(os.path.join(run, "lowpoly_build.json")):
        with open(os.path.join(run, "lowpoly_build.json")) as f:
            recipe = json.load(f)
    for name, scan in (recipe.get("scans") or {}).items():
        scene["face: " + name] = json.dumps(scan)
    stays = [p for p in recipe["pieces"] if not is_body(p, keep, drop) and not p.get("of")]
    goes = [p for p in recipe["pieces"] if is_body(p, keep, drop) or p.get("of")]
    if flags.get("extra"):
        with open(flags["extra"]) as f:
            stays += json.load(f)
    heads = [p for p in stays if "head" in p and p.get("box")]
    box = heads[0]["box"] if heads else None
    made_head = None
    if not heads and flags.get("head-box"):
        v = [float(x) for x in flags["head-box"].split(",")]
        box = {"min": v[:3], "max": v[3:]}
        made_head = run_script("face.py", {"object": "Reference", "box": box, "kind": flags.get("kind", "human"), "show": False})
        stays = [p for p in stays if "head" not in p["name"].lower()] + [dict(made_head["head"], eyes="flat")]
        heads = [made_head["head"]]

    found = run_script("landmarks.py", {"object": "Body" if base else "Reference", "head": box, "name": "body", "show": False})
    if base:
        bpy.data.objects["Body"].hide_set(True)
    marks, tall = found["landmarks"], found["proportions"]["height_m"]

    under = {}
    if stays:  # build what stays first, to see where it covers the body
        first = run_script("build.py", {"reference": "Reference", "parts": stays, "gear": recipe.get("gear") or [], "check": 0,
                                        "shading": recipe.get("shading", "flat")})
        under = covers(first["object"], marks, tall, base)
    skin = (heads[0].get("color") if heads else None) or [0.6, 0.5, 0.4]
    colors = {s: old_color(goes, s) or skin for s in STRETCH_WORDS}
    body = dict(found["body"], follow=float(flags.get("follow", 1.0)), under=under, color=skin, colors=colors,
                style={"chunky": float(flags.get("chunky", 1.0)), "limbs": float(flags.get("limbs", 1.0)), "head": float(flags.get("head-size", 1.0))})
    built = run_script("build.py", {"reference": "Reference", "parts": [body], "gear": recipe.get("gear") or [], "sockets": True,
                                    "shading": recipe.get("shading", "flat")})
    draped = None
    if any(g.get("forge") == "gear" for g in built.get("groups", [])):
        draped = run_script("drape.py", {"object": built["object"]})
    glb = os.path.join(out, "lowpoly.glb")
    wrote = run_script("export.py", {"object": built["object"], "path": glb, "materials": False})
    blockout_recipe.main(glb)
    print("AUTOBODY " + json.dumps({
        "run": run, "out": out, "read_off": "the base body" if base else "the reference", "kept": [p["name"] for p in stays],
        "replaced": [p["name"] for p in goes], "triangles": built["triangles"], "body": built["body"], "shape_lost": built.get("shape_lost"),
        "under": under, "proportions": found["proportions"], "found": {k: v for k, v in found["found"].items() if v != "shape"},
        "draped": bool(draped), "skin_showing_through": (draped or {}).get("skin_showing_through"), "file": wrote.get("path", glb),
        "head_made": bool(made_head),
    }))


main()
