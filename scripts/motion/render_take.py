"""Films a shot on a standing set from every one of the set's cameras at once, in a background Blender.

    Blender -b --factory-startup -P scripts/motion/render_take.py -- <take or shot folder>
        [--cast <clip>] [--version lowpoly] [--cameras wide,host] [--size 960x540] [--strip-only]

A TV studio films with three cameras running and picks the cut afterwards.
A shot can also bring cameras of its own that move (plan.json's
moving_cameras, scripts/sets/camera_path.py); they film alongside the set's.
So does this: the set stands still, its cameras and lights are where set.json
puts them every time, and one take comes out as one film and one strip of
stills per camera.

The folder is a take (shots/<name>/, with a take.json and a folder per role)
or a single shot on a set that has cameras. Without --cast the box figures
play it (each role's motion.glb), and the files are

    <camera>.mp4, <camera>-strip.png

With --cast <clip>, the characters apply_shot.py made play it (each role's
<version>-<clip>.glb, with its gear), and the files are

    <version>-<clip>-<camera>.mp4, <version>-<clip>-<camera>-strip.png
    cast-<clip>.json     who played whom, and what was measured with everyone
                         on the stage: each role's contact numbers, how far
                         apart the hands are in a handshake, how far each
                         seated body is from its seat

Sizes. A set is in metres and so is the motion, on the motion model's own
body (SOMA). A character keeps its real size: apply_shot.py stretches the
motion to cover the set's metres for its legs (the record's "true_size"), so
everyone is on the same marks with their hands on the same spot, and a tall
toon stands taller than a short one. (A record from before that was fitted in
its own strides; it is brought to the SOMA body's hip height instead.)

films.json lists everything filmed. Never touches an open Blender.
"""

import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
import set_contact  # noqa: E402
import standing  # noqa: E402

STRIP = (6, 2)  # stills across, down


def load(path):
    with open(path) as f:
        return json.load(f)


def strip_and_film(scene, folder, name, frames, size, strip_only):
    """One camera's strip of stills and its film. Returns {"strip", "mp4"} (file names)."""
    import numpy as np

    wide, tall = size
    count = STRIP[0] * STRIP[1]
    stills = [round(i * (frames - 1) / (count - 1)) for i in range(count)]
    cell = (wide // 2, tall // 2)
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = cell[0], cell[1], 100
    scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"
    sheet = np.zeros((cell[1] * STRIP[1], cell[0] * STRIP[0], 4), dtype=np.float32)
    temp = os.path.join(folder, ".strip-still.png")
    for n, frame in enumerate(stills):
        scene.frame_set(frame)
        scene.render.filepath = temp
        bpy.ops.render.render(write_still=True)
        image = bpy.data.images.load(temp)
        pixels = np.array(image.pixels[:], dtype=np.float32).reshape(cell[1], cell[0], 4)
        bpy.data.images.remove(image)
        col, row = n % STRIP[0], STRIP[1] - 1 - n // STRIP[0]
        sheet[row * cell[1]:(row + 1) * cell[1], col * cell[0]:(col + 1) * cell[0]] = pixels
    os.remove(temp)
    out = bpy.data.images.new("strip", cell[0] * STRIP[0], cell[1] * STRIP[1], alpha=True)
    out.pixels.foreach_set(sheet.ravel())
    out.filepath_raw, out.file_format = os.path.join(folder, name + "-strip.png"), "PNG"
    out.save()
    bpy.data.images.remove(out)
    made = {"strip": name + "-strip.png"}
    print("RENDER strip", os.path.join(folder, name + "-strip.png"))
    if not strip_only:
        scene.render.resolution_x, scene.render.resolution_y = wide, tall
        scene.render.image_settings.media_type = "VIDEO"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
        scene.render.filepath = os.path.join(folder, name + ".mp4")
        bpy.ops.render.render(animation=True)
        made["mp4"] = name + ".mp4"
        print("RENDER film", os.path.join(folder, name + ".mp4"), frames, "frames")
    return made


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    folder = os.path.abspath(args[0])
    clip = args[args.index("--cast") + 1] if "--cast" in args else None
    version = args[args.index("--version") + 1] if "--version" in args else "lowpoly"
    size = tuple(int(v) for v in (args[args.index("--size") + 1] if "--size" in args else "960x540").split("x"))
    strip_only = "--strip-only" in args

    # Who is in it: a take's roles, or the one figure of a single shot.
    take = load(os.path.join(folder, "take.json")) if os.path.exists(os.path.join(folder, "take.json")) else None
    roles = {role: os.path.join(folder, card["folder"]) for role, card in take["roles"].items()} if take else {"": folder}
    plans = {role: load(os.path.join(where, "plan.json")) for role, where in roles.items()}
    first = next(iter(plans.values()))
    if not first.get("standing_set"):
        sys.exit("render_take.py films shots on a standing set; this one has none (render_shot.py films it)")
    st = standing.load(first["standing_set"])
    frames = first["frames"]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 30  # before any import, so keys land one per frame
    cameras = set_contact.stand_up(st, scene)
    cameras.update(set_contact.moving_cameras(first, scene, first["frames"]))  # the shot's own cameras that move, if it has any
    if "--cameras" in args:
        wanted = args[args.index("--cameras") + 1].split(",")
        cameras = {name: cam for name, cam in cameras.items() if name in wanted}
    if not cameras:
        sys.exit("the set \"%s\" has no cameras to film from" % st["name"])

    # The cast: our characters at the SOMA body's size, or the box figures (already that size).
    figures, cast = {}, {}
    for role, where in roles.items():
        label = "role: " + (role or "the figure")
        if clip:
            record = load(os.path.join(where, "%s-%s.json" % (version, clip)))
            # A character fitted at its true size (apply_motion.at_true_size) already covers the set's metres.
            grow = 1.0 if record.get("true_size") else 1.0 / record["size_against_soma"]
            holder, new = set_contact.bring_in(os.path.join(where, "%s-%s.glb" % (version, clip)), label, scale=grow)
            cast[role] = record
        else:
            holder, new = set_contact.bring_in(os.path.join(where, "motion.glb"), label)
            blocks, kept = {block["name"] for block in plans[role].get("set") or []}, []
            for obj in new:  # the plan's blocks ride along in a box figure's file; the set itself is already standing
                if obj.name.split(".")[0] in blocks:
                    bpy.data.objects.remove(obj)
                else:
                    kept.append(obj)
            new = kept
        figures[role] = (set_contact.rig_of(new), new)
    scene.frame_start, scene.frame_end = 0, frames - 1
    scene.render.engine = "BLENDER_EEVEE"
    scene.view_settings.view_transform = "Standard"

    # What only shows with everyone on the stage together.
    measured = {"roles": {}, "handshakes": []}
    stages = {role: plan.get("stage") or {} for role, plan in plans.items()}
    by_spot = {}
    for role, stage in stages.items():
        for touch in stage.get("touches") or []:
            if touch.get("from_frame") is not None:
                by_spot.setdefault(tuple(touch["palm"]), []).append((role, touch))
    for spot, pair in by_spot.items():
        if len(pair) != 2:
            continue
        (role_a, a), (role_b, b) = pair
        lo, hi = max(a["from_frame"], b["from_frame"]), min(a["to_frame"], b["to_frame"])
        apart = set_contact.hands_apart(scene, figures[role_a], figures[role_b], lo, hi)
        if apart:
            apart.update({"between": [role_a, role_b], "marks": [a["mark"], b["mark"]], "spot": list(spot),
                          "planned_wrists_apart_cm": round(100.0 * sum((a["wrist"][i] - b["wrist"][i]) ** 2 for i in range(3)) ** 0.5, 1)})
            measured["handshakes"].append(apart)
            print("RENDER handshake %s and %s, frames %d-%d: palms %.1f cm apart typically (%.1f to %.1f), wrists %.1f (planned %.1f)" % (
                role_a, role_b, lo, hi, apart["palms_apart_cm"]["typical"], apart["palms_apart_cm"]["least"], apart["palms_apart_cm"]["most"],
                apart["wrists_apart_cm"]["typical"], apart["planned_wrists_apart_cm"]))
    for role, stage in stages.items():
        rig, objects = figures[role]
        seats = [set_contact.seat_gap(scene, objects, rig, st, span) for span in stage.get("seats") or []]
        seats = [s for s in seats if s]
        card = {"seats": seats}
        if role in cast:
            check, contact = cast[role]["animation"]["check"], cast[role]["animation"].get("contact") or {}
            card.update({
                "character": cast[role]["character"], "glb": "%s/%s-%s.glb" % (take["roles"][role]["folder"], version, clip) if take else "%s-%s.glb" % (version, clip),
                "size_against_soma": cast[role]["size_against_soma"],
                "true_size": cast[role].get("true_size"),  # fitted at its real size: shown at scale 1, not by size_against_soma
                "planted_foot_strays_cm": check["planted_foot_strays_cm"], "foot_slide_cm_per_step": check["foot_slide_cm_per_step"],
                "through_floor_cm": check["through_floor_cm"], "in_the_set": check.get("in_the_set"),
                "hand_from_its_spot_cm": check.get("hand_from_its_spot_cm"), "limit_violations": check["limit_violations"],
                "hips_raised_cm": contact.get("hips_raised_cm"), "legs_moved_clear_of_the_set_cm": contact.get("legs_moved_clear_of_the_set_cm"),
            })
        measured["roles"][role or "figure"] = card
        for seat in seats:
            if seat.get("over_the_seat"):
                print("RENDER seat %s at %s, frames %d-%d: %.1f cm from the seat typically (%.1f to %.1f), %.1f at the end" % (
                    role or "figure", seat["mark"], seat["frames"][0], seat["frames"][1], seat["gap_cm"]["typical"], seat["gap_cm"]["least"], seat["gap_cm"]["most"], seat["last_frame_gap_cm"]))
    scene.frame_set(0)

    prefix = "%s-%s-" % (version, clip) if clip else ""
    films = {}
    for name, cam in cameras.items():
        scene.camera = cam
        films[name] = strip_and_film(scene, folder, prefix + name, frames, size, strip_only)

    listed = load(os.path.join(folder, "films.json")) if os.path.exists(os.path.join(folder, "films.json")) else {}
    listed.setdefault(prefix.rstrip("-") or "motion", {}).update(films)
    with open(os.path.join(folder, "films.json"), "w") as f:
        json.dump(listed, f, indent=1)
    if clip:
        summary = {"set": st["name"], "clip": clip, "version": version, "frames": frames, "seconds": round((frames - 1) / 30.0, 2),
                   "cameras": list(cameras), "films": films, **measured}
        with open(os.path.join(folder, "cast-%s.json" % clip), "w") as f:
            json.dump(summary, f, indent=1)
        print("RENDER cast", os.path.join(folder, "cast-%s.json" % clip))


main()
