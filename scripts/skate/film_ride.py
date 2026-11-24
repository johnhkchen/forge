"""Films a ride on its set, from every one of the set's cameras, in a background Blender.

    Blender -b --factory-startup -P scripts/skate/film_ride.py -- <ride folder>
        [--version lowpoly] [--cameras side,low] [--size 960x540] [--strip-only] [--stills 120,333]

The ride folder is what apply_ride.py wrote: ride.json and <version>-ride.glb.
The set is stood up as a take's is (its geometry, lights and cameras, from
set.json) and the rider's file is put down at the set's origin: the ride is
already in the set's own place inside the file, so nothing else is moved.
The cameras never move.

It writes, as a take and a fight do, one film and one strip of twelve stills
per camera, and the cards the gallery reads:

    <version>-<camera>.mp4, <version>-<camera>-strip.png    960x540, 30 frames a second, H.264
    films.json                                               what was filmed
    cast-ride.json                                           who rides, on which set, and the films: what the
                                                             set's page in the gallery lists and plays
    take.json                                                the run's title and a line about it (kept if there)

--stills renders single frames instead (stills/<camera>-<frame>.png).
Never touches an open Blender.
"""

import json
import os
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
import set_contact  # noqa: E402
import standing  # noqa: E402

STRIP = (6, 2)  # stills across, down


def load(path):
    with open(path) as f:
        return json.load(f)


def strip_and_film(scene, folder, name, frames, size, strip_only):
    """One camera's strip of stills and its film, as render_take.py makes them. Returns {"strip", "mp4"} (file names)."""
    import numpy as np

    wide, tall = size
    count = STRIP[0] * STRIP[1]
    stills = [round(i * (frames - 1) / (count - 1)) for i in range(count)]
    cell = (wide // 2, tall // 2)
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = cell[0], cell[1], 100
    scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"
    sheet = np.zeros((cell[1] * STRIP[1], cell[0] * STRIP[0], 4), dtype=np.float32)
    temp = os.path.join(folder, ".strip-still-%s.png" % name)
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
    made = {"strip": name + "-strip.png", "strip_frames": stills}
    print("FILM strip", os.path.join(folder, name + "-strip.png"))
    if not strip_only:
        scene.render.resolution_x, scene.render.resolution_y = wide, tall
        scene.render.image_settings.media_type = "VIDEO"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
        scene.render.filepath = os.path.join(folder, name + ".mp4")
        bpy.ops.render.render(animation=True)
        made["mp4"] = name + ".mp4"
        print("FILM film", os.path.join(folder, name + ".mp4"), frames, "frames")
    return made


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    folder = os.path.abspath(args[0])
    ride = load(os.path.join(folder, "ride.json"))
    version = args[args.index("--version") + 1] if "--version" in args else (ride.get("rider") or {}).get("version", "lowpoly")
    size = tuple(int(v) for v in (args[args.index("--size") + 1] if "--size" in args else "960x540").split("x"))
    strip_only = "--strip-only" in args
    stills = [int(v) for v in args[args.index("--stills") + 1].split(",")] if "--stills" in args else None
    st = standing.load(ride["set"])
    frames = ride["frames"]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = ride["fps"]  # before any import, so keys land one per frame
    cameras = set_contact.stand_up(st, scene)
    if "--cameras" in args:
        wanted = args[args.index("--cameras") + 1].split(",")
        cameras = {name: cam for name, cam in cameras.items() if name in wanted}
    if not cameras:
        sys.exit("the set \"%s\" has no cameras to film from" % st["name"])
    set_contact.bring_in(os.path.join(folder, "%s-ride.glb" % version), "rider", at=[0.0, 0.0, 0.0], heading=0.0)
    scene.frame_start, scene.frame_end = 0, frames - 1
    scene.render.engine = "BLENDER_EEVEE"
    scene.view_settings.view_transform = "Standard"

    made = {}
    for name, cam in cameras.items():
        scene.camera = cam
        if stills:
            os.makedirs(os.path.join(folder, "stills"), exist_ok=True)
            scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = size[0], size[1], 100
            scene.render.image_settings.file_format = "PNG"
            for frame in stills:
                scene.frame_set(frame)
                scene.render.filepath = os.path.join(folder, "stills", "%s-%04d.png" % (name, frame))
                bpy.ops.render.render(write_still=True)
                print("FILM still", scene.render.filepath)
            continue
        made[name] = strip_and_film(scene, folder, "%s-%s" % (version, name), frames, size, strip_only)
    if stills:
        return
    # Several cameras may be filmed at once, one Blender each, and all of them add to the same cards: one at a
    # time, behind a lock file, so none writes over what another just added.
    lock = os.path.join(folder, ".films.lock")
    for attempt in range(600):
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            if time.time() - os.path.getmtime(lock) > 60:
                os.remove(lock)
            time.sleep(0.1)
    try:
        listed = load(os.path.join(folder, "films.json")) if os.path.exists(os.path.join(folder, "films.json")) else {}
        listed.setdefault(version, {}).update(made)
        listed["frames"], listed["seconds"], listed["set"] = frames, round(frames / float(ride["fps"]), 2), st["name"]
        with open(os.path.join(folder, "films.json") + ".part", "w") as f:
            json.dump(listed, f, indent=1)
        os.replace(os.path.join(folder, "films.json") + ".part", os.path.join(folder, "films.json"))
        # The card the gallery's page for the set reads (as render_take.py writes one for a take).
        cast_file = os.path.join(folder, "cast-ride.json")
        cast = load(cast_file) if os.path.exists(cast_file) else {"set": st["name"], "clip": "ride", "films": {}}
        cast.update({"version": version, "frames": frames, "seconds": listed["seconds"], "cameras": list(st["cameras"]), "handshakes": []})
        cast["films"].update(listed[version])
        cast["roles"] = {"rider": {"character": (ride.get("rider") or {}).get("character"), "glb": "%s-ride.glb" % version, "true_size": True}}
        with open(cast_file + ".part", "w") as f:
            json.dump(cast, f, indent=1)
        os.replace(cast_file + ".part", cast_file)
        if not os.path.exists(os.path.join(folder, "take.json")):
            with open(os.path.join(folder, "take.json"), "w") as f:
                json.dump({"name": os.path.basename(folder), "title": ride.get("title") or "A run on the halfpipe", "about": ride.get("about_the_run") or ""}, f, indent=1)
    finally:
        if os.path.exists(lock):
            os.remove(lock)


main()
