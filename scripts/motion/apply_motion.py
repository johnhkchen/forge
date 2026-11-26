"""The one way a motion from elsewhere gets onto one of our characters, inside a background Blender.

A shot (apply_shot.py) and a run (the `run` profile in scripts/tidy_profile.py)
both come through here. The motion arrives in animate.py's plain form
(soma_to_plain.py makes that from the motion worker's answer), and goes
through the same tidy-mesh steps as the walk:

    drape.py     the clothes onto the body, and the body faces they hide
    rig.py       the skeleton, fitted to this character, with its joint limits
    cloth.py     clothes take the body's weights; loose cloth gets its bones
    animate.py   the motion fitted to the character: planted feet stay
                 planted, its real shoes and shins stay out of the floor (and
                 out of a shot's wall), every joint stays inside its limits;
                 baked, measured
    swing.py     (and anything else the rig asks for after a bake) loose cloth
                 hangs and swings with what was just baked
    export.py    one .glb

Nothing here is a second way to animate a character. `fit` does everything up
to the bake and leaves the rigged character in the scene, so a caller can add
to it (a prop on its sockets) before `write` saves the file.

A tail. A motion model's skeleton has no tail, so a character with one would
carry it stiff. With `tail=True` the tail is given a motion of its own, the
way the walk does it: each tail bone turns as the hips did a moment ago, more
toward the tip, and the whole tail is lifted clear of the ground.

Blender only (imports bpy). Never touches an open Blender.
"""

import json
import math
import os
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import blockout_recipe  # noqa: E402

SCRIPTS = os.path.join(REPO, ".claude", "skills", "tidy-mesh", "scripts")
TAIL_LATE_FRAMES = 2  # how many frames behind the bone above it each tail bone turns (at 30 a second)


def run_script(name, params, echo=None):
    """Run a tidy-mesh skill script with its PARAMS updated, as the profile runner does, and return the JSON it printed.
    `echo` is a print to pass every line on to; None keeps the script quiet."""
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
        if echo:
            echo(*args, **kwargs)

    namespace["print"] = capture
    exec("import " + tail, namespace)
    return captured[-1] if captured else None


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def about_z_then_x(z_degrees, x_degrees):
    """[w, x, y, z]: a turn about x (nose up or down), then about z (left or right), in the character's axes."""
    a, b = math.radians(z_degrees) / 2.0, math.radians(x_degrees) / 2.0
    return [round(math.cos(a) * math.cos(b), 6), round(math.cos(a) * math.sin(b), 6), round(math.sin(a) * math.sin(b), 6), round(math.sin(a) * math.cos(b), 6)]


def at_true_size(plain, stretch):
    """The plain motion with its distances over the ground (and the set's blocks and hand spots) multiplied by `stretch`.

    A motion's lengths are in hip heights, so a character normally plays it in its own strides and
    covers ground in proportion to its legs. On a set, where the marks and seats are in metres, a
    character keeps its own size instead, and the motion is stretched so it covers the same metres:
    stretch is the motion body's hip height over this character's. The hips and both feet move
    together, so a planted foot stays planted; only the hips' height and how high a foot lifts stay
    the character's own. Blocks and hand spots are things in the world, so all of their lengths stretch."""
    if abs(stretch - 1.0) < 1e-6:
        return plain

    def flat(row):
        return [round(row[0] * stretch, 5), round(row[1] * stretch, 5)] + list(row[2:])

    out = dict(plain)
    out["hips"] = [flat(h) for h in plain["hips"]]
    out["feet"] = {tag: [flat(row) for row in rows] for tag, rows in plain["feet"].items()}
    out["travel"] = plain.get("travel", 0.0) * stretch
    if plain.get("hands"):
        out["hands"] = {tag: [None if row is None else [round(c * stretch, 5) for c in row[:3]] + list(row[3:]) for row in rows]
                        for tag, rows in plain["hands"].items()}
    if plain.get("set"):
        out["set"] = [dict(block, center=[round(c * stretch, 5) for c in block["center"]], size=[round(c * stretch, 5) for c in block["size"]])
                      for block in plain["set"]]
    return out


def with_tail(plain, measure):
    """The plain motion with turns for tail_1..tail_n added, worked out from what the hips do. Returns (motion, what was added)."""
    count = int(measure.get("tail_bones") or 0)
    if not count or "tail_1" in plain["turns"] or "hips" not in plain["turns"]:
        return plain, None
    frames = len(plain["hips"])
    around = plain["frames"] if plain.get("loop") else None  # a loop's tail looks back around the seam
    yaws = [math.degrees(math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))) for w, x, y, z in plain["turns"]["hips"]]
    for f in range(1, frames):  # no jump where the angle wraps
        yaws[f] -= 360.0 * round((yaws[f] - yaws[f - 1]) / 360.0)
    steady = sum(yaws) / frames
    height = [h[2] for h in plain["hips"]]
    level = sum(height) / frames
    # Lifted until the tip clears the ground at the lowest the hips go, as the walk lifts it.
    need = -min(height) * measure["hip_height"] + 0.035 * measure["height"] - measure.get("tail_tip_height", 0.0)
    rise = clamp(math.degrees(math.asin(clamp(need / max(measure.get("tail_long", 0.0), 1e-6), 0.0, 0.42))), 0.0, 24.0)
    turns = dict(plain["turns"])
    widest = 0.0
    for i in range(count):
        rows = []
        for f in range(frames):
            g = f - TAIL_LATE_FRAMES * (i + 1)
            g = g % around if around else max(g, 0)
            swing = clamp(0.3 * (yaws[f] - steady) + 0.5 * (1.0 + 0.35 * i) * (yaws[g] - steady), -30.0, 30.0)
            widest = max(widest, abs(swing))
            # The hips drop and the tail, late, is still up; they rise and it is still down.
            bounce = clamp(-60.0 * (height[g] - level) * (0.5 + 0.25 * i), -8.0, 8.0)
            rows.append(about_z_then_x(steady + swing, rise + bounce))
        if around:
            rows[-1] = list(rows[0])
        turns["tail_%d" % (i + 1)] = rows
    return dict(plain, turns=turns), {"bones": count, "rise_deg": round(rise, 1), "widest_swing_deg": round(widest, 1), "late_frames_per_bone": TAIL_LATE_FRAMES}


def fit(source, plain, name, recipe=None, spec=None, tail=False, echo=None, true_size=None):
    """A fresh scene with the character from `source` (.glb), rigged, dressed and playing `plain` as the action `name`.

    true_size: the hip height (m) of the body the motion was made on. Given, the character keeps its own
    size and the motion is stretched to cover the same metres (at_true_size); record["true_size"] says by how much.
    Returns what each step reported. The rig is bpy.data.objects[record["rig"]["rig"]].
    rig.py raises ValueError for a character it cannot fit a skeleton to (not in a T-pose)."""
    spec = spec or {}
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = plain["fps"]
    bpy.ops.import_scene.gltf(filepath=source)
    record = {}
    dressed = any(o.type == "MESH" and o.get("forge") == "gear" for o in bpy.context.scene.objects)
    if dressed:  # clothes onto the body, and the body faces they hide (a version draped when it was made is only read)
        record["drape"] = run_script("drape.py", {"pieces": recipe["pieces"] if recipe else None, "rings": False}, echo)
    record["rig"] = run_script("rig.py", dict(spec.get("rig", {}), recipe=recipe["pieces"] if recipe else None,
                                              template=blockout_recipe.wardrobe_template(bpy.data.materials)), echo)
    if dressed:  # clothes take the body's weights; loose cloth gets bones to hang from
        record["cloth"] = run_script("cloth.py", spec.get("cloth", {}), echo)
    if true_size:
        stretch = true_size / record["rig"]["measure"]["hip_height"]
        plain = at_true_size(plain, stretch)
        record["true_size"] = {"stretch": round(stretch, 4), "height_m": round(record["rig"]["measure"]["height"], 3)}
    if tail:
        plain, added = with_tail(plain, record["rig"]["measure"])
        if added:
            record["tail"] = added
    record["animation"] = run_script("animate.py", dict(spec.get("animate", {}), motion=plain, action=name, check=True), echo)
    for script in record["animation"].get("then", []):  # what the rig asks for after any bake: swing.py, for cloth bones
        started = time.time()
        record[script[:-3]] = run_script(script, spec.get(script[:-3], {}), echo)
        record[script[:-3]]["seconds"] = round(time.time() - started, 2)
    return record


def write(record, glb, materials=True, export=None, echo=None):
    """Save the scene `fit` left as one .glb: the character, its skeleton and the action. Adds "export" and "bytes" to the record."""
    params = dict(export or {"image_format": "WEBP", "draco": False}, rig=True, path=glb, materials=materials)
    params.setdefault("check", True)
    record["export"] = run_script("export.py", params, echo)
    doc, rest = blockout_recipe.read(glb)
    if blockout_recipe.tidy_names(doc):
        blockout_recipe.write(glb, doc, rest)
    record["bytes"] = os.path.getsize(glb)
    return record
