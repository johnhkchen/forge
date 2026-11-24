"""Serve the gallery on the local network: the newest diorama, the world, every run, before and after, and every set.

    python3 scripts/gallery.py [--port 8028] [--runs DIR] [--shots DIR] [--marble DIR]

Serves gallery/ (the page), runs/ and comics/ (the files), sets/
(the standing sets), world/ (the toons and props that stand in the world; /marble/ is world/marble/, the Marble worlds a place's splats are read from),
dioramas/ (story moments on a base),
shots/ (what was filmed on the sets) and videos/ (clips you brought for
`just video`), plus /api/runs, /api/comics, /api/sets,
/api/takes, /api/dioramas (newest first), /api/videos and /api/world (world.json and every saved epoch), built from the folders on each
request, so a new run, comic or take shows up on reload. Binds to all
interfaces so a phone on the same Wi-Fi (or on your tailnet)
can open it; nothing here is meant for the internet.

Read-only, with two exceptions. POST /api/videos/<name>/choice keeps who you
chose to follow in each shot of a clip. It can write videos/<name>/choice.json
and no other file, and only a choice that fits the people found in that clip
(scripts/video/people.py checks it). And casting (/api/casting, casting/):
POST /api/casting/<role>/<candidate>/note gives a candidate a note,
.../status shortlists, lets go or casts it, /api/casting/<role>/shortlist
makes a headshot a candidate, and /api/casting/<role>/plan says what a step
would do and cost without doing it. They write only casting/<role>/candidates/
<candidate>/candidate.json, through scripts/casting/casting.py, which checks
every word. Nothing here starts a paid step. Everything else that is not a GET is refused.
"""
import argparse
import json
import mimetypes
import os
import re
import subprocess
import socket
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PAGE = os.path.join(ROOT, "gallery")
RUNS = os.path.join(ROOT, "runs")
SETS = os.path.join(ROOT, "sets")
SHOTS = os.path.join(ROOT, "shots")
COMICS = os.path.join(ROOT, "comics")
WORLD = os.path.join(ROOT, "world")
DIORAMAS = os.path.join(ROOT, "dioramas")
VIDEOS = os.environ.get("FORGE_VIDEOS") or os.path.join(ROOT, "videos")
MARBLE = os.path.join(WORLD, "marble")  # worlds from World Labs Marble as they were handed over: big, and kept out of git
sys.path.insert(0, os.path.join(ROOT, "scripts", "diorama"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "video"))
import diorama as diorama_file  # noqa: E402  (what a diorama is, and its card for the front page)
import people as video_people  # noqa: E402  (a clip's people, and the one thing this server may write: who you chose)
sys.path.insert(0, os.path.join(ROOT, "scripts", "casting"))
import casting as casting_file  # noqa: E402  (roles, candidates and their takes; the notes you give)
CASTING = casting_file.CASTING
CHOICE_PATH = re.compile(r"^/api/videos/([a-z0-9][a-z0-9-]{0,63})/choice$")
# /api/casting/robot/plan, /api/casting/robot/shortlist, /api/casting/robot/villager/note, .../status
CASTING_PATH = re.compile(r"^/api/casting/([a-z0-9][a-z0-9-]{0,47})(?:/([a-z0-9][a-z0-9-]{0,47}))?/(note|status|shortlist|plan)$")
CHOICE_BYTES = 64 * 1024  # a choice is a few hundred bytes; nothing bigger is read
PROFILE_ORDER = ["hero", "quads", "web", "game", "mobile", "midpoly", "lowpoly"]

mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("video/mp4", ".mp4")



def card_thumbnail(run_dir, name):
    """card.jpg beside the run's picture: 480 px, made once with macOS's sips (and again if the picture changes).
    The gallery's cards use it; the full picture is still there for the object page."""
    if not name:
        return None
    source = os.path.join(run_dir, name)
    card = os.path.join(run_dir, "card.jpg")
    if not os.path.exists(card) or os.path.getmtime(card) < os.path.getmtime(source):
        try:
            subprocess.run(["sips", "-Z", "480", "-s", "format", "jpeg", "-s", "formatOptions", "82", source, "--out", card],
                           capture_output=True, timeout=30, check=True)
        except (OSError, subprocess.SubprocessError):
            return name
    return "card.jpg"


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def profile_summary(run_dir, name):
    record = read_json(os.path.join(run_dir, "profiles", name + ".json")) or {}
    shape = record.get("shape") or {}
    steps = {s.get("script"): s.get("result") or {} for s in record.get("steps", [])}
    light = (steps.get("autoremesher") or steps.get("blockout") or steps.get("rebuild") or steps.get("retopo.py")
             or steps.get("decimate.py") or {})
    bake = steps.get("bake.py") or {}
    export = record.get("export") or {}
    # A character's low-poly and mid-poly versions may also come with a skeleton and a walk.
    walking = read_json(os.path.join(run_dir, "profiles", name + "-walk.json")) or {}
    gait = (walking.get("walk") or {}).get("gait") or {}
    has_walk = os.path.exists(os.path.join(run_dir, "profiles", name + "-walk.glb"))
    # ...and with a hero shot: a longer clip from poses of our own, with its prop (scripts/motion/apply_shot.py).
    hero = read_json(os.path.join(run_dir, "profiles", name + "-hero.json")) or {}
    has_hero = os.path.exists(os.path.join(run_dir, "profiles", name + "-hero.glb"))
    # ...and with a run: a loop cut from a clip made from one sentence (scripts/motion/run_clip.py, the `run` profile).
    running = (read_json(os.path.join(run_dir, "profiles", name + "-run.json")) or {}).get("run") or {}
    has_run = os.path.exists(os.path.join(run_dir, "profiles", name + "-run.glb"))
    # ...and maybe a second cut of it, where some beats were made from a sentence instead of our poses.
    has_mixed = os.path.exists(os.path.join(run_dir, "profiles", name + "-hero-mixed.glb"))
    return {
        "name": name,
        "about": record.get("about"),
        "glb": "profiles/%s.glb" % name,
        "edges": "profiles/%s-edges.glb" % name if os.path.exists(os.path.join(run_dir, "profiles", name + "-edges.glb")) else None,
        "faces": light.get("faces") or export.get("faces"),
        "quads": light.get("quads"),
        "triangles": export.get("triangles"),
        "bytes": record.get("bytes"),
        "shape_typical": (shape.get("shape_lost") or {}).get("p95_%"),
        "shape_worst": (shape.get("shape_lost") or {}).get("max_%"),
        "maps": bake.get("maps"),
        "seconds": record.get("seconds"),
        # Low-poly and mid-poly characters: the gear that comes off, and where props attach.
        "gear": record.get("gear") or [],
        "sockets": record.get("sockets") or [],
        "walk": "profiles/%s-walk.glb" % name if has_walk else None,
        "gait": {k: gait.get(k) for k in ("speed_m_s", "stride_m", "cadence_steps_per_min", "stance_width_m", "bob_cm", "sway_cm")} if has_walk else None,
        "bones": len((walking.get("rig") or {}).get("bones") or []) or None,
        # Loose cloth (a kilt, a hood) has bones of its own that hang and swing.
        "cloth_bones": len((walking.get("cloth") or {}).get("cloth_bones") or []) or None,
        "run": "profiles/%s-run.glb" % name if has_run else None,
        "run_gait": {k: running.get(k) for k in ("speed_m_s", "steps_per_minute", "loop_s")} if has_run else None,
        "hero": "profiles/%s-hero.glb" % name if has_hero else None,
        "hero_mixed": "profiles/%s-hero-mixed.glb" % name if has_mixed else None,
        "hero_seconds": (hero.get("animation") or {}).get("seconds") if has_hero else None,
        "hero_prop": (hero.get("prop") or {}).get("prop") if has_hero else None,
    }


def slug(name):
    """'Ruffled Skirt!' -> 'ruffled-skirt', the way the pipeline names files."""
    return "-".join("".join(c if c.isascii() and c.isalnum() else " " for c in name.lower()).split())


def base_summary(run_dir):
    """A character whose clothes hide its body: the real body made from a second picture, and
    each hiding garment cut from the clothed mesh. Twice over: beside the raw mesh, and (once the
    object is finished) where the finished object stands."""
    cut = read_json(os.path.join(run_dir, "base", "cut.json"))
    if not cut or not os.path.exists(os.path.join(run_dir, "base", "body.glb")):
        return None
    has = lambda f: os.path.exists(os.path.join(run_dir, f))

    def pieces(body, folder):
        if not has(body):
            return None
        garments = [{"name": g["name"], "glb": "%s/%s.glb" % (folder, slug(g["name"]))} for g in cut.get("garments") or []]
        return {"body": body, "garments": [g for g in garments if has(g["glb"])]}

    fit = cut.get("fit") or {}
    return {
        "raw": pieces("base/body.glb", "base/cut"),
        "finished": pieces("base/final.glb", "garments"),
        "picture": "base/image.png" if has("base/image.png") else None,
        "sheet": "base/sheet.png" if has("base/sheet.png") else None,
        "garments": [g["name"] for g in cut.get("garments") or []],
        "apart_pct": (fit.get("off_pct") or {}).get("median"),
    }


def cards_summary(run_id, run_dir):
    """A character baked as flat cards (scripts/impostor/bake_impostor.py: profiles/<version>-impostor/, and
    <version>-impostor-<look>/ for a look with a sheet of its own: pixel art, bold ink): the view
    sets it has, and every clip it can play: the version's own walk, routine and run, and any shot on a set that
    cast this same version (a fight)."""
    out = []
    profiles = os.path.join(run_dir, "profiles")
    for name in sorted(os.listdir(profiles)) if os.path.isdir(profiles) else []:
        card = read_json(os.path.join(profiles, name, "impostor.json")) if name.endswith("-impostor") or "-impostor-" in name else None
        if not card:
            continue
        pictured = card.get("profile") or name.split("-impostor")[0]
        version = card.get("plays") or pictured  # a detailed mesh given another version's skeleton plays that version's clips
        motions = [{"id": clip, "name": label, "glb": "runs/%s/profiles/%s-%s.glb" % (run_id, version, clip)}
                   for clip, label in (("walk", "Walk"), ("rom", "Warm-up"), ("run", "Run"))
                   if os.path.isfile(os.path.join(profiles, "%s-%s.glb" % (version, clip)))]
        for shot in sorted(os.listdir(SHOTS)) if os.path.isdir(SHOTS) else []:
            for file in sorted(os.listdir(os.path.join(SHOTS, shot))) if os.path.isdir(os.path.join(SHOTS, shot)) else []:
                cast = read_json(os.path.join(SHOTS, shot, file)) if file.startswith("cast-") and file.endswith(".json") else None
                for role, part in ((cast or {}).get("roles") or {}).items():
                    if part.get("character", "").endswith("%s/profiles/%s.glb" % (run_id, version)) and os.path.isfile(os.path.join(SHOTS, shot, part.get("glb", ""))):
                        take = read_json(os.path.join(SHOTS, shot, "take.json")) or {}
                        mark = ((read_json(os.path.join(SHOTS, shot, "fight.json")) or {}).get("marks") or {}).get(role) or {}
                        motions.append({"id": shot, "name": take.get("title") or shot.replace("-", " ").capitalize(), "glb": "shots/%s/%s" % (shot, part["glb"]),
                                        "at": mark.get("at"), "facing_deg": mark.get("facing_deg", 0.0)})
        if motions:
            out.append({"profile": pictured, "plays": version, "title": card.get("title") or "", "folder": "profiles/" + name, "parts": len(card.get("parts") or []), "views": list(card.get("sets") or {}), "motions": motions})
    return out


def run_summary(folder):
    run_dir = os.path.join(RUNS, folder)
    brief = read_json(os.path.join(run_dir, "brief.json")) or {}
    polish = read_json(os.path.join(run_dir, "polish.json")) or {}
    mesh = read_json(os.path.join(run_dir, "mesh.json")) or {}
    has = lambda f: os.path.exists(os.path.join(run_dir, f))
    names = [p for p in PROFILE_ORDER if has("profiles/%s.glb" % p)]
    return {
        "id": folder,
        "made": "%s %s:%s UTC" % (folder[:10], folder[11:13], folder[14:16]),
        "name": brief.get("name") or folder[20:].replace("-", " ").title(),
        "description": brief.get("description"),
        "size_m": brief.get("size_m"),
        "character": bool(brief.get("character")),
        "picture": "image.png" if has("image.png") else None,
        # The shadow ninja's portrait of this toon (canon: his photoshoots), used as its card when there is one.
        "portrait": "portrait.png" if has("portrait.png") else None,
        # A small copy of whichever picture the card shows, so the front page doesn't pull full-size PNGs.
        "card": card_thumbnail(run_dir, "portrait.png" if has("portrait.png") else "render.png" if has("render.png") else "image.png" if has("image.png") else None),
        "render": "render.png" if has("render.png") else None,
        "raw": "profiles/raw.glb" if has("profiles/raw.glb") else ("mesh.glb" if has("mesh.glb") else None),
        "gpu": mesh.get("gpu"),
        "mesh_seconds": (mesh.get("seconds") or {}),
        "score": polish.get("score"),
        "fixes": polish.get("fixes") or [],
        "problems": polish.get("problems") or [],
        "profiles": [profile_summary(run_dir, p) for p in names],
        "base": base_summary(run_dir),
        "cards": cards_summary(folder, run_dir),
        "props": [dict(p, run=os.path.basename(p.get("run", "").rstrip("/")))
                  for p in (read_json(os.path.join(run_dir, "props.json")) or {}).get("props", [])],
        "prop_of": os.path.basename(((read_json(os.path.join(run_dir, "prop_of.json")) or {}).get("character") or "").rstrip("/")) or None,
    }


def all_runs():
    if not os.path.isdir(RUNS):
        return []
    folders = [f for f in os.listdir(RUNS) if os.path.isdir(os.path.join(RUNS, f)) and not f.startswith(".")]
    return [run_summary(f) for f in sorted(folders, reverse=True)]


def all_sets():
    """Every standing set (sets/<name>/set.json), as its page needs it: the set.json itself, and which of its files are there."""
    out = []
    if not os.path.isdir(SETS):
        return out
    for name in sorted(os.listdir(SETS)):
        card = read_json(os.path.join(SETS, name, "set.json"))
        if not card:
            continue
        has = lambda f: bool(f) and os.path.isfile(os.path.join(SETS, name, f))
        card["id"] = name
        card["glb"] = (card.get("geometry") or {}).get("glb", "set.glb") if has((card.get("geometry") or {}).get("glb", "set.glb")) else None
        card["picture"] = "card.png" if has("card.png") else ((card.get("backdrop") or {}).get("image") if has((card.get("backdrop") or {}).get("image")) else None)
        card["dressing"] = [d for d in card.get("dressing") or [] if has(d.get("glb"))]
        if card.get("backdrop") and not has(card["backdrop"].get("image")):
            card["backdrop"] = None
        out.append(card)
    return out


def the_world():
    """The world (world.json) and every saved epoch of it, oldest first. An epoch is the whole world at one moment:
    where each place stands, who is where, and what the ground is like (scripts/world/world.py)."""
    world = read_json(os.path.join(ROOT, "world.json"))
    if not world:
        return None
    epochs = []
    folder = os.path.join(WORLD, "epochs")
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        epoch = read_json(os.path.join(folder, name)) if name.endswith(".json") else None
        if epoch and epoch.get("places"):
            epochs.append(epoch)
    epochs.sort(key=lambda e: e.get("number", 0))
    return {"title": world.get("title"), "about": world.get("about"), "now": world.get("epoch"), "epochs": epochs}


def all_takes():
    """Every shot filmed on a standing set with a cast (shots/<name>/cast-<clip>.json, from render_take.py): who is in
    it, each one's file and size, and the film from each camera."""
    if not os.path.isdir(SHOTS):
        return []
    return [t for name in sorted(os.listdir(SHOTS)) for t in takes_in(os.path.join(SHOTS, name), name)]


def takes_in(folder, name):
    """The takes cast in one shot folder (shots/<name>/), as /api/takes gives them; name is the take's id, the
    folder under shots/ (a casting take is shots/casting/<role>/<candidate>-<n>/, scripts/casting)."""
    out = []
    take = read_json(os.path.join(folder, "take.json")) or {}
    for file in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not (file.startswith("cast-") and file.endswith(".json")):
            continue
        cast = read_json(os.path.join(folder, file))
        if not cast:
            continue
        roles = []
        for role, card in (cast.get("roles") or {}).items():
            if not card.get("glb") or not os.path.isfile(os.path.join(folder, card["glb"])):
                continue
            mid = card["glb"].replace("lowpoly-", "midpoly-")
            where = card.get("character", "").replace("\\", "/").split("/")
            roles.append({"role": role, "character": os.path.basename(os.path.dirname(card.get("character", ""))),
                          # the run this character is, whichever of its versions was cast (runs/<run>/lowpoly.glb, runs/<run>/profiles/painted.glb)
                          "run": where[where.index("runs") + 1] if "runs" in where[:-1] else None,
                          # a fight stands each fighter on a mark of the set, facing the other (fight.json); other takes have the places played in
                          "mark": ((read_json(os.path.join(folder, "fight.json")) or {}).get("marks") or {}).get(role), "size": 1.0 if card.get("true_size") else card.get("size_against_soma", 1.0),
                          "glb": card["glb"], "midpoly": mid if mid != card["glb"] and os.path.isfile(os.path.join(folder, mid)) else None})
        out.append({
            "id": name, "clip": cast.get("clip"), "set": cast.get("set"), "title": take.get("title") or name.replace("-", " ").capitalize(),
            "about": take.get("about"), "seconds": cast.get("seconds"), "roles": roles,
            "films": {camera: film.get("mp4") for camera, film in (cast.get("films") or {}).items() if film.get("mp4") and os.path.isfile(os.path.join(folder, film["mp4"]))},
            "handshakes": cast.get("handshakes") or [],
        })
    return out


def all_videos():
    """Every clip in videos/ (`just video-add`), newest first: how far it has come, the shots and people found in it,
    who was chosen, and the film of the result beside the clip."""
    out = []
    if not os.path.isdir(VIDEOS):
        return out
    for name in sorted(os.listdir(VIDEOS)):
        folder = os.path.join(VIDEOS, name)
        card = read_json(os.path.join(folder, "clip.json"))
        if not card or not video_people.clip_file.NAME.match(name):
            continue
        has = lambda f: os.path.isfile(os.path.join(folder, f))
        people = read_json(os.path.join(folder, "people.json"))
        choice = video_people.load_choice(folder) if people else None
        shot_dir = os.path.join(SHOTS, "video-" + name)
        source = read_json(os.path.join(shot_dir, "source.json")) if has("side-by-side.mp4") else None
        checks = read_json(os.path.join(shot_dir, "checks.json")) if source else None
        clip = card.get("clip") or {}
        out.append({
            "id": name, "title": name.replace("-", " ").capitalize(), "added": card.get("added"), "from_file": card.get("from_file"),
            "seconds": clip.get("seconds"), "width": clip.get("width"), "height": clip.get("height"),
            "clip": "clip.mp4" if has("clip.mp4") else None,
            "shots": (read_json(os.path.join(folder, "shots.json")) or {}).get("shots") or [],
            "people": (people or {}).get("shots"),
            "choice": choice,
            "film": "side-by-side.mp4" if has("side-by-side.mp4") else None,
            "cast_films": sorted(f for f in os.listdir(folder) if f.startswith("side-by-side-") and f.endswith(".mp4")),
            "shot": {"id": "video-" + name, "frames": source.get("frames"), "pieces": source.get("pieces"), "joins": source.get("joins"), "converted": source.get("converted"),
                     "feet": (checks or {}).get("feet"), "floor": ((checks or {}).get("floor") or {}).get("worst")} if source else None,
            "_at": os.path.getmtime(os.path.join(folder, "clip.json")),
        })
    out.sort(key=lambda v: v.pop("_at"), reverse=True)
    return out


def all_casting():
    """Every role being cast (casting/<role>/role.json), as its page needs it; a take's chemistry read and sparring
    bout come as the watch page takes them (takes_in), so they play there as any take does."""
    cast = casting_file.Casting(CASTING, RUNS, SHOTS)
    out = []
    for role in cast.roles():
        summary = cast.summary(role)
        for candidate in summary["candidates"]:
            for take in candidate["takes"]:
                for key in ("chemistry", "fight"):
                    found = takes_in(os.path.join(SHOTS, take[key]), take[key]) if take[key] else []
                    take[key] = found[0] if found else None
        out.append(summary)
    return out


def casting_write(role, candidate, action, body):
    """The writes /api/casting takes, each one checked by scripts/casting/casting.py. Raises ValueError to refuse."""
    cast = casting_file.Casting(CASTING, RUNS, SHOTS)
    if not isinstance(body, dict):
        raise ValueError("send an object")
    if action == "plan":
        return cast.plan(str(body.get("step", "")), role, body.get("candidate") or candidate)
    if action == "shortlist":
        return cast.shortlist(role, str(body.get("look", "")))
    if not candidate:
        raise ValueError("say which candidate")
    if action == "note":
        take = body.get("take")
        return cast.add_note(role, candidate, str(body.get("text", "")), str(body.get("about", "look")), int(take) if take is not None else None)
    return cast.set_status(role, candidate, str(body.get("status", "")))


def all_comics():
    """Every lettered comic in comics/: what its reader.json holds (scripts/comic/layout.py writes it)."""
    if not os.path.isdir(COMICS):
        return []
    found = []
    for name in sorted(os.listdir(COMICS)):
        reader = read_json(os.path.join(COMICS, name, "reader.json"))
        if reader and reader.get("panels") and not name.startswith(("_", ".")):
            found.append((os.path.getmtime(os.path.join(COMICS, name, "reader.json")), dict(reader, name=name)))
    return [comic for _, comic in sorted(found, key=lambda pair: pair[0], reverse=True)]


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # quiet; the terminal shows the address and that's enough

    def send_json(self, value):
        body = json.dumps(value).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, base, rel):
        path = os.path.realpath(os.path.join(base, rel))
        if not path.startswith(os.path.realpath(base) + os.sep) or not os.path.isfile(path):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        kind = mimetypes.guess_type(path)[0] or "application/octet-stream"
        size = os.path.getsize(path)
        # A phone's video player asks for a film a piece at a time ("Range: bytes=0-1"), and will not play without an answer in kind.
        first, last = 0, size - 1
        asked = re.match(r"^bytes=(\d*)-(\d*)$", self.headers.get("Range") or "")
        if asked and (asked.group(1) or asked.group(2)) and size:
            if asked.group(1):
                first, last = int(asked.group(1)), min(int(asked.group(2)), size - 1) if asked.group(2) else size - 1
            else:
                first = max(0, size - int(asked.group(2)))
            if first > last:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.end_headers()
                return
            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header("Content-Range", "bytes %d-%d/%d" % (first, last, size))
        else:
            self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(last - first + 1 if size else 0))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            f.seek(first)
            left = last - first + 1
            while left > 0 and (chunk := f.read(min(1 << 20, left))):
                self.wfile.write(chunk)
                left -= len(chunk)

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/runs":
            return self.send_json(all_runs())
        if path == "/api/sets":
            return self.send_json(all_sets())
        if path == "/api/takes":
            return self.send_json(all_takes())
        if path == "/api/world":
            return self.send_json(the_world())
        if path.startswith("/evidence/"):  # pictures taken as proof, and the cut-away splats a diorama picture is drawn from
            return self.send_file(os.path.join(ROOT, "evidence"), path[len("/evidence/"):])
        if path.startswith("/marble/"):
            return self.send_file(MARBLE, path[len("/marble/"):])
        if path.startswith("/world/"):
            return self.send_file(WORLD, path[len("/world/"):])
        if path == "/api/casting":
            return self.send_json(all_casting())
        if path.startswith("/casting/"):
            return self.send_file(CASTING, path[len("/casting/"):])
        if path == "/api/comics":
            return self.send_json(all_comics())
        if path == "/api/dioramas":
            return self.send_json(diorama_file.shelf())
        if path == "/api/videos":
            return self.send_json(all_videos())
        if path.startswith("/videos/"):
            return self.send_file(VIDEOS, path[len("/videos/"):])
        if path.startswith("/dioramas/"):
            return self.send_file(DIORAMAS, path[len("/dioramas/"):])
        if path.startswith("/comics/"):
            return self.send_file(COMICS, path[len("/comics/"):])
        if path.startswith("/runs/"):
            return self.send_file(RUNS, path[len("/runs/"):])
        if path.startswith("/sets/"):
            return self.send_file(SETS, path[len("/sets/"):])
        if path.startswith("/shots/"):
            return self.send_file(SHOTS, path[len("/shots/"):])
        if path in ("/", ""):
            return self.send_file(PAGE, "index.html")
        return self.send_file(PAGE, path.lstrip("/"))

    do_HEAD = do_GET

    def refuse(self, status, why):
        body = json.dumps({"error": why}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_POST(self):
        """The two things this server writes: who to follow in each shot of a clip (videos/<name>/choice.json), and
        casting's notes and choices (casting/<role>/candidates/<candidate>/candidate.json)."""
        asked = CHOICE_PATH.match(urlparse(self.path).path)  # the path as sent: nothing is decoded, so nothing can hide in it
        casting = CASTING_PATH.match(urlparse(self.path).path)
        if not asked and not casting:
            return self.refuse(HTTPStatus.NOT_FOUND, "nothing here takes a POST")
        # A page from somewhere else cannot send JSON here without asking first, and is told no.
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return self.refuse(HTTPStatus.FORBIDDEN, "only the gallery's own page may save a choice")
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return self.refuse(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "send the choice as application/json")
        try:
            length = int(self.headers.get("Content-Length") or "")
        except ValueError:
            return self.refuse(HTTPStatus.LENGTH_REQUIRED, "say how long the choice is")
        if not 0 < length <= CHOICE_BYTES:
            return self.refuse(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "a choice is small")
        if casting:
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                done = casting_write(casting.group(1), casting.group(2), casting.group(3), body)
            except (ValueError, TypeError, UnicodeDecodeError) as error:
                return self.refuse(HTTPStatus.NOT_FOUND if str(error).startswith("no such") else HTTPStatus.BAD_REQUEST, str(error))
            return self.send_json({"saved": casting.group(3) != "plan", "result": done})
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            video_people.save_choice(VIDEOS, asked.group(1), body)
        except (ValueError, UnicodeDecodeError) as error:
            return self.refuse(HTTPStatus.NOT_FOUND if str(error) == "no such clip" else HTTPStatus.BAD_REQUEST, str(error))
        self.send_json({"saved": True, "choice": video_people.load_choice(os.path.join(VIDEOS, asked.group(1)))})


def lan_address():
    """The address other devices on the Wi-Fi reach this Mac at."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.168.0.1", 9))  # no packet is sent; this just picks the LAN interface
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8028)
    parser.add_argument("--runs", default=RUNS, help="the folder of runs to show (default: runs/)")
    parser.add_argument("--shots", default=SHOTS, help="the folder of shots, for takes filmed on a set (default: shots/)")
    parser.add_argument("--videos", default=VIDEOS, help="the folder of clips for `just video` (default: videos/)")
    parser.add_argument("--marble", default=MARBLE, help="the folder of Marble worlds, for places shown as splats (default: world/marble/)")
    args = parser.parse_args()
    MARBLE = os.path.abspath(args.marble)
    RUNS = os.path.abspath(args.runs)
    SHOTS = os.path.abspath(args.shots)
    VIDEOS = os.path.abspath(args.videos)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print("Forge gallery", flush=True)
    print("  on this Mac:   http://localhost:%d" % args.port)
    print("  on your phone: http://%s:%d   (same Wi-Fi)" % (lan_address(), args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
