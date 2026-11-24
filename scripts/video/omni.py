"""A filmed segment packed for an AI video restyle (Gemini Omni Flash), sent only when you say go, and checked after.

    python3 scripts/video/omni.py film  <restyle> [--port 8052]          # make every picture the pack needs
    python3 scripts/video/omni.py pack  <restyle>                        # exports/omni/<restyle>/: films, pictures, prompts, manifest
    python3 scripts/video/omni.py send  <export folder> [edit|frames|generate] [go]
    python3 scripts/video/omni.py drift <export folder> <result.mp4> [go]
    python3 scripts/video/omni.py compare <our motion.json> <their motion.json>

A restyle is written down in motion/restyles/<name>.json: which shot, which of
its moving cameras, which cast and look, the frame rate, and the three prompts.

film    Draws the shot through its moving camera, a picture at a time: bold
        ink (the look the gallery draws, by the watch page in a headless
        Chrome: scripts/video/watch_film.py), the background alone in bold
        ink, the dancer alone in white on black; and in a background Blender
        (scripts/motion/render_path.py) the plain shaded film, its background
        alone, and how far each pixel is. Also the character from the side
        and the back (scripts/video/turnaround.py). Into shots/<shot>/omni/.
        Nothing is paid for. The watch page needs the gallery running.
pack    Makes those pictures films (silent, H.264) and pictures for the
        model, into exports/omni/<name>/ (kept out of git): source.mp4 (bold
        ink: what is sent), shaded.mp4, plate.mp4, plate-shaded.mp4, mask.mp4,
        depth.mp4, first.png and last.png, refs/ (the two pictures edit mode
        takes: a character sheet and the stage), refs-6/ (six pictures for the
        other two routes), prompt.txt, prompt-frames.txt,
        prompt-generate.txt and manifest.json.
send    Prints exactly what would be sent, and what it would cost, and stops.
        With `go` it sends it: each file goes up through the Files API, then
        one request to the Interactions API. What comes back has its sound
        taken off and is kept in <export>/results/, beside a record of the
        request. The routes:
            edit      our film and two reference pictures: restyle it, keep
                      the motion, timing, framing and camera (the default)
            frames    our first and last pictures: the model makes the
                      10 seconds between (3 to 10 s is all it takes)
            generate  six reference pictures and a prompt with timings: a
                      new film of the same idea, no film of ours
drift   Did the restyle keep our dance? Brings the result in as a clip
        (`just video-add`), has GEM-X read the dancer's motion off it (the
        clip goes to your RunPod endpoint: that costs), chooses the dancer
        itself when there is only one person, and compares that motion with
        ours, joint by joint and moment by moment (`compare`). Without `go`
        it says what it would do and what it would cost.

The key is GEMINI_API_KEY, from the environment or .env. Nothing here sends
anything without `go`.

Plain Python (urllib, no SDK) and ffmpeg.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import mimetypes
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
import clip as clip_file  # noqa: E402

RESTYLES = os.path.join(REPO, "motion", "restyles")
SHOTS = os.path.join(REPO, "shots")
RUNS = os.path.join(REPO, "runs")
EXPORTS = os.path.join(REPO, "exports", "omni")
API = "https://generativelanguage.googleapis.com"
BLENDER = os.environ.get("BLENDER") or "/Applications/Blender.app/Contents/MacOS/Blender"
FFMPEG = clip_file.FFMPEG

# What it costs (Gemini API pricing page, paid tier, read 2026-11-24). Output is billed by tokens: 5,792 a second of
# 720p video at $12 a million, about $0.07 a second. Input (our film, the pictures, the prompt) is $1.50 a million.
# How many tokens our input comes to is not published for Omni: the estimate takes Gemini's usual counts, high side.
PRICE = {"input_per_m": 1.50, "video_out_per_m": 12.00, "text_out_per_m": 9.00,
         "video_tokens_per_s": {"360p": 1931, "720p": 5792, "1080p": 8688, "4k": 17376}}
GUESS = {"input_video_tokens_per_s": 300, "image_tokens": 1290, "thinking_tokens": 2000}
LIMITS = {"edit": {"images": 2, "seconds": (3, 15)}, "frames": {"images": 2, "seconds": (3, 10)}, "generate": {"images": 6, "seconds": (3, 15)}}
ROUTES = ("edit", "frames", "generate")
# GEM-X on the groove clip: 10.8 s of GPU a second of clip to find and follow people, 2.2 to read the motion
GEMX = {"people_s_per_s": 10.8, "motion_s_per_s": 2.2, "boot_s": 30, "usd_per_gpu_s": 0.00031}

PASSES = {  # name in shots/<shot>/omni/: how it is drawn
    "joe": ("watch", ""), "plate-joe": ("watch", "plate"), "mask": ("watch", "mask"),
    "shaded": ("blender", "shaded"), "plate-shaded": ("blender", "plate"), "depth": ("blender", "depth"),
}


class Stop(Exception):
    pass


def read(path):
    with open(path) as f:
        return json.load(f)


def write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(value, f, indent=1)
        f.write("\n")


def recipe_of(name: str) -> dict:
    path = os.path.join(RESTYLES, name + ".json")
    if not os.path.exists(path):
        raise Stop(f"there is no restyle called {name} (motion/restyles/{name}.json)")
    return read(path)


def run(cmd, **kw):
    done = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if done.returncode != 0:
        raise Stop(f"{os.path.basename(cmd[0])} failed:\n" + (done.stderr or done.stdout)[-1500:])
    return done.stdout


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ---- film: every picture the pack needs ------------------------------------------


def frames_ready(folder: str, count: int) -> bool:
    card = os.path.join(folder, "frames.json")
    return os.path.exists(card) and all(os.path.exists(os.path.join(folder, "%04d.png" % n)) for n in (0, count - 1))


def film(name: str, port: int = 8052) -> dict:
    import camera_path

    r = recipe_of(name)
    shot = os.path.join(SHOTS, r["shot"])
    plan = read(os.path.join(shot, "plan.json"))
    count = len(camera_path.frames_at((plan["frames"] - 1) / 30.0, r["fps"]))
    out = os.path.join(shot, "omni")
    made = {}
    for pass_name, (how, kind) in PASSES.items():
        folder = os.path.join(out, pass_name)
        if frames_ready(folder, count):
            made[pass_name] = "kept"
            continue
        print(f"OMNI film {pass_name}: {count} pictures ({how})", flush=True)
        if how == "watch":
            run([sys.executable, os.path.join(HERE, "watch_film.py"), folder, "--base", f"http://localhost:{port}/", "--take", r["shot"], "--eye", r["camera"],
                 "--look", r["look"], "--model", r["version"], "--pass", kind, "--fps", str(r["fps"]), "--size", r["size"]])
        else:
            run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P", os.path.join(REPO, "scripts", "motion", "render_path.py"), "--", shot, folder,
                 "--camera", r["camera"], "--cast", r["cast"], "--version", r["version"], "--fps", str(r["fps"]), "--size", r["size"], "--pass", kind])
        made[pass_name] = "made"
    turns = os.path.join(out, "turn")
    if not all(os.path.exists(os.path.join(turns, v + ".png")) for v in ("side", "back")):
        run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P", os.path.join(HERE, "turnaround.py"), "--",
             os.path.join(RUNS, r["character_run"], "final.glb"), turns, "--views", "front,side,back,quarter"])
        made["turn"] = "made"
    print("OMNI film: " + ", ".join(f"{k} {v}" for k, v in made.items()))
    return made


# ---- pack: the export folder ---------------------------------------------------------


def encode(frames: str, out: str, fps: float) -> None:
    run([FFMPEG, "-v", "error", "-y", "-framerate", str(fps), "-i", os.path.join(frames, "%04d.png"), "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "14",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", out])


def character_sheet(run_dir: str, turns: str, out: str) -> None:
    """One clean 16:9 sheet, no text: her front (the run's own picture), side and back (the detailed mesh), and her
    head large from the front, three-quarter and side (heads/sheet.png), on the grey her picture stands on."""
    run([FFMPEG, "-v", "error", "-y", "-i", os.path.join(run_dir, "image.png"), "-i", os.path.join(turns, "side.png"), "-i", os.path.join(turns, "back.png"),
         "-i", os.path.join(run_dir, "heads", "sheet.png"), "-filter_complex",
         "color=c=0xbdbdbc:s=1920x1080[bg];[0]scale=600:600[f];[1]scale=600:600[s];[2]scale=600:600[b];[3]scale=940:470[h];"
         "[bg][f]overlay=40:10[x1];[x1][s]overlay=660:10[x2];[x2][b]overlay=1280:10[x3];[x3][h]overlay=490:605",
         "-frames:v", "1", out])


def still(film_frames: str, n: int, out: str) -> None:
    shutil.copyfile(os.path.join(film_frames, "%04d.png" % n), out)


def pack(name: str) -> str:
    import camera_path

    r = recipe_of(name)
    shot = os.path.join(SHOTS, r["shot"])
    plan = read(os.path.join(shot, "plan.json"))
    count = len(camera_path.frames_at((plan["frames"] - 1) / 30.0, r["fps"]))
    films = os.path.join(shot, "omni")
    missing = [p for p in PASSES if not frames_ready(os.path.join(films, p), count)]
    if missing:
        raise Stop(f"not drawn yet: {', '.join(missing)} (python3 scripts/video/omni.py film {name}, with the gallery running)")
    out = os.path.join(EXPORTS, name)
    os.makedirs(os.path.join(out, "refs"), exist_ok=True)
    os.makedirs(os.path.join(out, "refs-6"), exist_ok=True)
    variants = {"source": "source.mp4", "shaded": "shaded.mp4", "plate": "plate.mp4", "plate_shaded": "plate-shaded.mp4", "mask": "mask.mp4", "depth": "depth.mp4"}
    for key, folder in (("source", "joe"), ("shaded", "shaded"), ("plate", "plate-joe"), ("plate_shaded", "plate-shaded"), ("mask", "mask"), ("depth", "depth")):
        print(f"OMNI pack {variants[key]}", flush=True)
        encode(os.path.join(films, folder), os.path.join(out, variants[key]), r["fps"])
    joe, plate = os.path.join(films, "joe"), os.path.join(films, "plate-joe")
    still(joe, 0, os.path.join(out, "first.png"))
    still(joe, count - 1, os.path.join(out, "last.png"))
    still(joe, count // 2, os.path.join(out, "middle.png"))  # to look at; not sent
    run_dir = os.path.join(RUNS, r["character_run"])
    turns = os.path.join(films, "turn")
    character_sheet(run_dir, turns, os.path.join(out, "refs", "character-sheet.png"))
    still(plate, count - 1, os.path.join(out, "refs", "set.png"))  # the stage from where the push-in ends, nobody on it
    six = os.path.join(out, "refs-6")
    shutil.copyfile(os.path.join(run_dir, "image.png"), os.path.join(six, "1-front.png"))
    shutil.copyfile(os.path.join(turns, "side.png"), os.path.join(six, "2-side.png"))
    shutil.copyfile(os.path.join(turns, "back.png"), os.path.join(six, "3-back.png"))
    run([FFMPEG, "-v", "error", "-y", "-i", os.path.join(run_dir, "heads", "sheet.png"), "-vf", "crop=iw/3:ih:0:0", "-frames:v", "1", os.path.join(six, "4-face.png")])
    still(plate, 0, os.path.join(six, "5-stage-wide.png"))
    still(plate, count - 1, os.path.join(six, "6-stage-close.png"))
    for route, file in (("edit", "prompt.txt"), ("frames", "prompt-frames.txt"), ("generate", "prompt-generate.txt")):
        with open(os.path.join(out, file), "w") as f:
            f.write(r["prompts"][route].strip() + "\n")
    write(os.path.join(out, "manifest.json"), manifest(r, plan, shot, out, count, variants))
    print(f"OMNI pack done -> {out}")
    return out


def manifest(r: dict, plan: dict, shot: str, out: str, count: int, variants: dict) -> dict:
    import camera_path

    piece = plan["pieces"][0]
    cast = read(os.path.join(shot, f"{r['version']}-{r['cast']}.json"))
    check, contact = cast["animation"]["check"], cast["animation"].get("contact") or {}
    path = plan["moving_cameras"][r["camera"]]
    seconds = round((plan["frames"] - 1) / 30.0, 3)
    tidy = lambda w: {"at": [round(v, 4) for v in w["at"]], "aim": [round(v, 4) for v in w["aim"]], "lens_mm": round(w["lens_mm"], 2)}  # noqa: E731
    first, last = tidy(camera_path.sample(path, 0.0)), tidy(camera_path.sample(path, seconds))
    files = {}
    for root, _, names in os.walk(out):
        for n in sorted(names):
            p = os.path.join(root, n)
            rel = os.path.relpath(p, out)
            if rel.startswith("results") or rel == "manifest.json":
                continue
            files[rel] = {"bytes": os.path.getsize(p), "sha256": sha256(p)}
    stretch_card = read(os.path.join(shot, "stretch.json")) if os.path.exists(os.path.join(shot, "stretch.json")) else {}
    return {
        "format": "forge-omni-export/1", "name": r["name"], "title": r["title"], "about": r["about"], "made": time.strftime("%Y-%m-%d %H:%M"),
        "stretch": {"clip": piece["clip"], "clip_shot": piece["clip_shot"], "person": piece["person"], "clip_frames": piece["clip_frames"],
                    "from_s": round(piece["clip_frames"][0] / 30.0, 2), "to_s": round(piece["clip_frames"][1] / 30.0, 2), "seconds": seconds,
                    "seam_in_the_clip_at_s": 42.47, "why": stretch_card.get("why")},
        "fps": r["fps"], "size": [int(v) for v in r["size"].split("x")], "frames": count, "film_seconds": round(count / r["fps"], 3), "sound": None,
        "camera": {"name": r["camera"], "about": path.get("about"), "keys": path["keys"],
                   "starts": {**first, "tilt_up_deg": round(camera_path.tilt_deg(first), 1)}, "ends": {**last, "tilt_up_deg": round(camera_path.tilt_deg(last), 1)},
                   "lens_on": "a 36 mm wide picture", "coordinates": "the set's: x across, y up, z toward the house, metres"},
        "set": {"name": plan["standing_set"], "mark": "centre", "placement": piece["placement"], "facing": "the last frame square on to the house (facing_at end)"},
        "cast": {"character": r["character_run"], "version": r["version"], "file": f"shots/{r['shot']}/{r['version']}-{r['cast']}.glb",
                 "feet_held": piece["feet"].get("locked"), "planted_foot_strays_cm": check["planted_foot_strays_cm"], "through_the_floor_cm": check["through_floor_cm"],
                 "lowest_part": check.get("lowest_part"), "hips_lowered_cm": cast["animation"].get("hips_lowered_cm"), "hips_raised_cm": contact.get("hips_raised_cm"),
                 "limit_violations": check["limit_violations"], "true_size": cast.get("true_size")},
        "look": {"source": "bold ink (gallery/looks.js \"joe\"), drawn by the watch page in a headless Chrome", "shaded": "Blender EEVEE, the set's own lights",
                 "depth": "white at 0.5 m from the lens, black at 12 m and beyond, straight between", "mask": "the dancer white, all else black, from the same page as source.mp4 (the bold ink outline, about 3 px, lies just outside it)"},
        "variants": variants,
        "refs": {"edit": ["refs/character-sheet.png", "refs/set.png"], "six": sorted(os.listdir(os.path.join(out, "refs-6"))), "first": "first.png", "last": "last.png"},
        "prompts": {"edit": "prompt.txt", "frames": "prompt-frames.txt", "generate": "prompt-generate.txt"},
        "model": r["model"], "resolution": r["resolution"],
        "licence": r["licence"],
        "files": files,
    }


# ---- send ----------------------------------------------------------------------------


def whole_seconds(seconds: float) -> int:
    return int(round(seconds))


def plan_request(export: str, route: str = "edit") -> dict:
    """What a route sends: the files to upload (in order), and the request with a stand-in for each file's address."""
    if route not in ROUTES:
        raise Stop(f"the route is one of {', '.join(ROUTES)}")
    card = read(os.path.join(export, "manifest.json"))
    limit = LIMITS[route]
    if route == "edit":
        files = ["source.mp4"] + card["refs"]["edit"]
        prompt_file, seconds = "prompt.txt", whole_seconds(card["film_seconds"])
    elif route == "frames":
        files = [card["refs"]["first"], card["refs"]["last"]]
        prompt_file, seconds = "prompt-frames.txt", int(read(os.path.join(RESTYLES, card["name"] + ".json")).get("frames_route_seconds", 10)) if os.path.exists(os.path.join(RESTYLES, card["name"] + ".json")) else 10
    else:
        files = [os.path.join("refs-6", f) for f in card["refs"]["six"]]
        prompt_file, seconds = "prompt-generate.txt", whole_seconds(card["film_seconds"])
    images = [f for f in files if f.endswith(".png")]
    if len(images) > limit["images"]:
        raise Stop(f"{route} takes at most {limit['images']} pictures; this would send {len(images)}")
    if not limit["seconds"][0] <= seconds <= limit["seconds"][1]:
        raise Stop(f"{route} makes {limit['seconds'][0]} to {limit['seconds'][1]} seconds; this asks for {seconds}")
    for f in files + [prompt_file]:
        if not os.path.exists(os.path.join(export, f)):
            raise Stop(f"{export} has no {f}: pack it first")
    with open(os.path.join(export, prompt_file)) as f:
        prompt = f.read().strip()
    parts = [{"type": "video" if f.endswith(".mp4") else "image", "uri": f"<Files API address of {f}>"} for f in files]
    body = {"model": card.get("model", "gemini-omni-1.2-flash"),
            "input": parts + [{"type": "text", "text": prompt}],
            "response_format": {"type": "video", "duration": f"{seconds}s", "resolution": card.get("resolution", "720p"), "aspect_ratio": "16:9", "delivery": "uri"}}
    uploads = [{"file": f, "bytes": os.path.getsize(os.path.join(export, f)), "mime_type": mimetypes.guess_type(f)[0] or "application/octet-stream"} for f in files]
    return {"route": route, "export": export, "uploads": uploads, "prompt_file": prompt_file, "seconds": seconds, "body": body,
            "video_in_seconds": card["film_seconds"] if route == "edit" else 0.0}


def estimate(plan: dict) -> dict:
    """What a request would cost, in US dollars: what is known (the film out) and a high-side guess at the rest."""
    res = plan["body"]["response_format"]["resolution"]
    out_tokens = plan["seconds"] * PRICE["video_tokens_per_s"][res]
    images = sum(1 for u in plan["uploads"] if u["mime_type"].startswith("image/"))
    prompt = next(p["text"] for p in plan["body"]["input"] if p["type"] == "text")
    in_tokens = plan["video_in_seconds"] * GUESS["input_video_tokens_per_s"] + images * GUESS["image_tokens"] + len(prompt) // 4
    video_out = out_tokens * PRICE["video_out_per_m"] / 1e6
    inputs = in_tokens * PRICE["input_per_m"] / 1e6
    thinking = GUESS["thinking_tokens"] * PRICE["text_out_per_m"] / 1e6
    return {"video_out_tokens": out_tokens, "video_out_usd": round(video_out, 3), "input_tokens_guess": int(in_tokens), "input_usd_guess": round(inputs, 3),
            "thinking_usd_guess": round(thinking, 3), "total_usd": round(video_out + inputs + thinking, 2), "per_second_usd": round(PRICE["video_tokens_per_s"][res] * PRICE["video_out_per_m"] / 1e6, 4)}


def api_key() -> tuple:
    """(the key or None, where it was found or what is missing)."""
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"], "the environment"
    for env in (os.path.join(REPO, ".env"), os.path.join(os.getcwd(), ".env")):
        if os.path.exists(env):
            with open(env) as f:
                for line in f:
                    k, _, v = line.strip().partition("=")
                    if k.strip() == "GEMINI_API_KEY" and v.strip():
                        return v.strip().strip('"').strip("'"), env
    return None, "no GEMINI_API_KEY in the environment or in .env: add a line GEMINI_API_KEY=<your key from https://aistudio.google.com/apikey> to .env (a paid-tier key: Omni is not on the free tier)"


def describe(plan: dict, cost: dict, key_said: str) -> str:
    lines = [f"OMNI would send ({plan['route']}), from {plan['export']}:"]
    for n, u in enumerate(plan["uploads"], 1):
        lines.append(f"  upload {n}: {u['file']} ({u['bytes'] / 1e6:.2f} MB, {u['mime_type']}) -> POST {API}/upload/v1beta/files (resumable), then wait until ACTIVE")
    lines.append(f"  then POST {API}/v1beta/interactions  (header x-goog-api-key)")
    lines.append("  " + json.dumps(plan["body"], indent=1).replace("\n", "\n  "))
    lines.append(f"  the film that comes back: its sound taken off, kept in {os.path.join(plan['export'], 'results')}/ with a record of the request")
    lines.append(f"OMNI cost: about ${cost['total_usd']:.2f}: {plan['seconds']} s of {plan['body']['response_format']['resolution']} out is {cost['video_out_tokens']:,} tokens = ${cost['video_out_usd']:.2f} "
                 f"(${cost['per_second_usd']}/s), plus a guess of ${cost['input_usd_guess']:.3f} for what goes in ({cost['input_tokens_guess']:,} tokens) and ${cost['thinking_usd_guess']:.3f} for the model's thinking")
    lines.append(f"OMNI key: {'found in ' + key_said if key_said.startswith('/') or key_said == 'the environment' else key_said}")
    return "\n".join(lines)


def http(method: str, url: str, key: str, body=None, headers=None, raw=False, timeout=600):
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    ask = urllib.request.Request(url, data=data, method=method, headers={"x-goog-api-key": key, **({"Content-Type": "application/json"} if isinstance(body, (dict, list)) else {}), **(headers or {})})
    try:
        with urllib.request.urlopen(ask, timeout=timeout) as reply:
            got = reply.read()
            return (got, dict(reply.headers)) if raw else (json.loads(got or b"{}"), dict(reply.headers))
    except urllib.error.HTTPError as error:
        raise Stop(f"{method} {url.split('?')[0]} said {error.code}: {error.read()[:800].decode(errors='replace')}")


def upload(path: str, mime: str, key: str) -> dict:
    """One file through the Files API (a resumable upload in one go), waited on until it is ACTIVE."""
    size = os.path.getsize(path)
    _, head = http("POST", f"{API}/upload/v1beta/files", key, body={"file": {"display_name": os.path.basename(path)}},
                   headers={"X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start", "X-Goog-Upload-Header-Content-Length": str(size), "X-Goog-Upload-Header-Content-Type": mime})
    where = {k.lower(): v for k, v in head.items()}.get("x-goog-upload-url")
    if not where:
        raise Stop("the Files API gave no upload address")
    with open(path, "rb") as f:
        got, _ = http("POST", where, key, body=f.read(), headers={"Content-Length": str(size), "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"})
    card = got.get("file", got)
    for _ in range(120):
        if card.get("state") in (None, "ACTIVE"):
            return card
        if card.get("state") == "FAILED":
            raise Stop(f"the Files API could not take {os.path.basename(path)}")
        time.sleep(5)
        card, _ = http("GET", f"{API}/v1beta/{card['name']}", key)
    raise Stop(f"{os.path.basename(path)} was still processing after ten minutes")


def find_video(reply) -> dict:
    """The film in an answer: {"uri"} or {"data"}, wherever it is (steps[].content[], or output_video)."""
    if isinstance(reply, dict):
        if reply.get("type") == "video" and (reply.get("uri") or reply.get("data")):
            return reply
        if isinstance(reply.get("output_video"), dict):
            return reply["output_video"]
        for v in reply.values():
            got = find_video(v)
            if got:
                return got
    elif isinstance(reply, list):
        for v in reply:
            got = find_video(v)
            if got:
                return got
    return {}


def redact(reply):
    """An answer as kept on disk: base64 data replaced by its length."""
    if isinstance(reply, dict):
        return {k: (f"<{len(v)} characters of base64>" if k == "data" and isinstance(v, str) and len(v) > 200 else redact(v)) for k, v in reply.items()}
    if isinstance(reply, list):
        return [redact(v) for v in reply]
    return reply


def silent(raw: str, out: str) -> None:
    """The film with no sound at all: the picture copied, every audio stream dropped."""
    run([FFMPEG, "-v", "error", "-y", "-i", raw, "-map", "0:v:0", "-c", "copy", "-an", out])


def send(export: str, route: str = "edit", go: bool = False) -> dict:
    export = os.path.abspath(export)
    plan = plan_request(export, route)
    cost = estimate(plan)
    key, said = api_key()
    print(describe(plan, cost, said))
    if not go:
        print("OMNI not sent. Add `go` to send it" + ("" if key else ", once the key is there") + ".")
        return {"sent": False, "plan": plan, "cost": cost}
    if not key:
        raise Stop(said)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    results = os.path.join(export, "results")
    os.makedirs(results, exist_ok=True)
    began = time.time()
    record = {"route": route, "sent": time.strftime("%Y-%m-%d %H:%M:%S"), "estimate": cost, "uploads": []}
    body = json.loads(json.dumps(plan["body"]))
    parts = [p for p in body["input"] if p["type"] in ("video", "image")]
    for part, item in zip(parts, plan["uploads"]):
        print(f"OMNI uploading {item['file']}", flush=True)
        card = upload(os.path.join(export, item["file"]), item["mime_type"], key)
        part["uri"] = card["uri"]
        record["uploads"].append({"file": item["file"], "name": card.get("name"), "uri": card.get("uri"), "sha256": sha256(os.path.join(export, item["file"]))})
    record["request"] = body
    print("OMNI asking the model (this takes a few minutes)", flush=True)
    reply, _ = http("POST", f"{API}/v1beta/interactions", key, body=body, timeout=1800)
    record["reply"] = redact(reply)
    video = find_video(reply)
    raw = os.path.join(results, f".{route}-{stamp}-with-sound.mp4")
    if video.get("data"):
        with open(raw, "wb") as f:
            f.write(base64.b64decode(video["data"]))
    elif video.get("uri"):
        uri = video["uri"]
        name = "files/" + uri.split("files/")[1].split(":")[0].split("?")[0] if "files/" in uri else None
        for _ in range(180):
            if not name:
                break
            card, _ = http("GET", f"{API}/v1beta/{name}", key)
            if card.get("state") == "ACTIVE":
                break
            if card.get("state") == "FAILED":
                raise Stop("the model's film failed")
            time.sleep(5)
        got, _ = http("GET", f"{API}/v1beta/{name}:download?alt=media" if name else uri, key, raw=True)
        with open(raw, "wb") as f:
            f.write(got)
    else:
        write(os.path.join(results, f"{route}-{stamp}.json"), record)
        raise Stop("no film in the answer; it is kept in " + os.path.join(results, f"{route}-{stamp}.json"))
    out = os.path.join(results, f"{route}-{stamp}.mp4")
    silent(raw, out)
    os.remove(raw)
    record.update({"result": os.path.basename(out), "seconds_taken": round(time.time() - began, 1), "result_probe": clip_file.probe(out), "sound": "taken off"})
    write(os.path.join(results, f"{route}-{stamp}.json"), record)
    print(f"OMNI back: {out} (no sound), record {out[:-4]}.json")
    return {"sent": True, "result": out, "record": record}


# ---- drift: did the restyle keep our dance? -------------------------------------------


def pose_track(sk, motion: dict) -> list:
    """Per frame, every joint's place against the hips, turned so the hips face ahead, in metres of our SOMA body."""
    from soma import heading_of, qconj, qmul, qrot, sub, yaw

    order = [motion["joints"].index(name) for name in sk.joints]
    track = []
    for root, row in zip(motion["root"], motion["rotations"]):
        pos, rot = sk.fk(root, [tuple(row[4 * j: 4 * j + 4]) for j in order])
        back = yaw(-heading_of(qmul(rot[0], qconj(sk.rest_rot[0]))))  # as timeline.facing turns it
        track.append([qrot(back, sub(p, pos[0])) for p in pos])
    return track


def _err(a, b) -> float:
    return math.sqrt(sum((a[k] - b[k]) ** 2 for k in range(3)))


def compare(ours: dict, theirs: dict, sk=None, most_lag: int = 15, window: int = 60) -> dict:
    """How far apart two motions of the same dance are: per joint (cm, after the best shift in time), and the timing
    (the shift that fits best overall, and in each two-second window, so a film that slows or hurries shows)."""
    from soma import Skeleton

    sk = sk or Skeleton.load()
    a, b = pose_track(sk, ours), pose_track(sk, theirs)
    # their body is not ours: bring their size to ours by the reach from hips to head
    head = sk.index["Head"]
    reach = lambda t: sum(math.sqrt(sum(v * v for v in f[head])) for f in t) / len(t)  # noqa: E731
    k = reach(a) / max(1e-6, reach(b))
    b = [[tuple(v * k for v in p) for p in f] for f in b]

    def mean_at(lag, lo=0, hi=None):
        hi = len(a) if hi is None else hi
        pairs = [(i, i + lag) for i in range(lo, hi) if 0 <= i + lag < len(b)]
        if len(pairs) < 10:
            return float("inf")
        return sum(sum(_err(a[i][j], b[m][j]) for j in range(len(sk.joints))) / len(sk.joints) for i, m in pairs) / len(pairs)

    lags = range(-most_lag, most_lag + 1)
    best = min(lags, key=mean_at)
    joints = {}
    for j, name in enumerate(sk.joints):
        errs = sorted(_err(a[i][j], b[i + best][j]) for i in range(len(a)) if 0 <= i + best < len(b))
        joints[name] = {"typical_cm": round(100 * errs[len(errs) // 2], 1), "p95_cm": round(100 * errs[int(len(errs) * 0.95)], 1)}
    windows = []
    for lo in range(0, max(1, len(a) - window + 1), window // 2):
        lag = min(lags, key=lambda g: mean_at(g, lo, lo + window))
        windows.append({"from_frame": lo, "best_lag_frames": lag, "mean_cm": round(100 * mean_at(lag, lo, lo + window), 1)})
    worst = sorted(joints.items(), key=lambda kv: -kv[1]["typical_cm"])[:5]
    return {"frames": [len(a), len(b)], "their_size_brought_to_ours_by": round(k, 3), "best_lag_frames": best, "best_lag_ms": round(1000 * best / 30.0),
            "mean_cm": round(100 * mean_at(best), 1), "joints": joints, "worst_joints": [w[0] for w in worst],
            "timing_windows": windows, "timing_drift_frames": (windows[-1]["best_lag_frames"] - windows[0]["best_lag_frames"]) if windows else 0}


def drift(export: str, result: str, go: bool = False) -> dict:
    export, result = os.path.abspath(export), os.path.abspath(result)
    card = read(os.path.join(export, "manifest.json"))
    ours = os.path.join(SHOTS, card["name"], "motion.json")
    probe = clip_file.probe(result)
    seconds = probe.get("seconds") or card["film_seconds"]
    name = clip_file.slug(f"omni-{card['name']}-{os.path.splitext(os.path.basename(result))[0]}")[:64].rstrip("-")
    gpu = GEMX["boot_s"] + seconds * (GEMX["people_s_per_s"] + GEMX["motion_s_per_s"])
    print(f"OMNI drift: {os.path.basename(result)} ({seconds:.1f} s) against {ours}")
    print(f"  1. just video-add {result} {name}      (this Mac: copied into videos/{name}/, 30 pictures a second; free)")
    print(f"  2. just video {name}                  (RunPod GEM-X: find and follow the dancer, about {seconds * GEMX['people_s_per_s']:.0f} s of GPU)")
    print("     the one person found in each shot is chosen for you, the camera marked as moving; if there are more, choose on the clip's page and run this again")
    print(f"  3. just video {name}                  (RunPod GEM-X: read her motion, about {seconds * GEMX['motion_s_per_s']:.0f} s of GPU; then joined and filmed here)")
    print(f"  4. omni.py compare {ours} shots/video-{name}/motion.json  -> {result[:-4]}-drift.json")
    print(f"OMNI drift cost: about {gpu / 60:.1f} minutes of an RTX 4090 with boot, ${gpu * GEMX['usd_per_gpu_s']:.2f} at RunPod's flex rate (${GEMX['usd_per_gpu_s']}/s; check your endpoint's)")
    if not go:
        print("OMNI drift not run. Add `go` to run it.")
        return {"ran": False, "clip": name, "gpu_seconds": round(gpu)}
    import people as people_file

    folder = clip_file.folder_of(name)
    if not os.path.exists(os.path.join(folder, "clip.json")):
        clip_file.add(result, name)
    for _ in range(3):
        subprocess.run([sys.executable, os.path.join(HERE, "video.py"), name], check=False)
        theirs = os.path.join(SHOTS, f"video-{name}", "motion.json")
        if os.path.exists(theirs):
            break
        found = clip_file.read(os.path.join(folder, "people.json"))
        if found and not os.path.exists(os.path.join(folder, "choice.json")):
            shots = {str(s["index"]): s["people"][0]["id"] for s in found["shots"] if len(s["people"]) == 1}
            if len(shots) != len(found["shots"]):
                raise Stop(f"more than one person found: choose on the clip's page (#/video/{name}), then run this again")
            people_file.save_choice(clip_file.VIDEOS, name, {"shots": shots, "camera": "moving"})
    else:
        raise Stop("GEM-X's motion did not arrive; run `just video %s` to see where it stopped" % name)
    measured = compare(read(ours), read(theirs))
    out = result[:-4] + "-drift.json"
    write(out, {"ours": ours, "theirs": theirs, "result": os.path.basename(result), **measured})
    print(f"OMNI drift: typical joint {measured['mean_cm']} cm apart, best in step {measured['best_lag_ms']} ms off, timing drifts {measured['timing_drift_frames']} frames; -> {out}")
    return measured


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    go = "go" in args[1:]
    rest = [a for a in args[1:] if a != "go"]
    try:
        if args[0] == "film":
            film(rest[0], int(rest[rest.index("--port") + 1]) if "--port" in rest else 8052)
        elif args[0] == "pack":
            pack(rest[0])
        elif args[0] == "send":
            send(rest[0], rest[1] if len(rest) > 1 and rest[1] else "edit", go)
        elif args[0] == "drift":
            drift(rest[0], rest[1], go)
        elif args[0] == "compare":
            print(json.dumps({k: v for k, v in compare(read(rest[0]), read(rest[1])).items() if k != "joints"}, indent=1))
        else:
            sys.exit(__doc__)
    except Stop as stop:
        sys.exit(f"OMNI stopped: {stop}")


if __name__ == "__main__":
    main()
