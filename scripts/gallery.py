"""Serve the gallery on the local network: the newest diorama, the world, every run, before and after, and every set.

    python3 scripts/gallery.py [--port 8028] [--runs DIR] [--shots DIR]

Read-only. Serves gallery/ (the page), runs/ and comics/ (the files), sets/
(the standing sets), world/ (the toons and props that stand in the world),
dioramas/ (story moments on a base) and
shots/ (what was filmed on the sets), plus /api/runs, /api/comics, /api/sets,
/api/takes, /api/dioramas (newest first) and /api/world (world.json and every saved epoch), built from the folders on each
request, so a new run, comic or take shows up on reload. Binds to all
interfaces so a phone on the same Wi-Fi
can open it; nothing here is meant for the internet.
"""
import argparse
import json
import mimetypes
import os
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
sys.path.insert(0, os.path.join(ROOT, "scripts", "diorama"))
import diorama as diorama_file  # noqa: E402  (what a diorama is, and its card for the front page)
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
        version = card.get("profile") or name[:-len("-impostor")]
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
            out.append({"profile": version, "folder": "profiles/" + name, "parts": len(card.get("parts") or []), "views": list(card.get("sets") or {}), "motions": motions})
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
    out = []
    if not os.path.isdir(SHOTS):
        return out
    for name in sorted(os.listdir(SHOTS)):
        folder = os.path.join(SHOTS, name)
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
                roles.append({"role": role, "character": os.path.basename(os.path.dirname(card.get("character", ""))), "size": 1.0 if card.get("true_size") else card.get("size_against_soma", 1.0),
                              "glb": card["glb"], "midpoly": mid if mid != card["glb"] and os.path.isfile(os.path.join(folder, mid)) else None})
            out.append({
                "id": name, "clip": cast.get("clip"), "set": cast.get("set"), "title": take.get("title") or name.replace("-", " ").capitalize(),
                "about": take.get("about"), "seconds": cast.get("seconds"), "roles": roles,
                "films": {camera: film.get("mp4") for camera, film in (cast.get("films") or {}).items() if film.get("mp4") and os.path.isfile(os.path.join(folder, film["mp4"]))},
                "handshakes": cast.get("handshakes") or [],
            })
    return out
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
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        with open(path, "rb") as f:
            while chunk := f.read(1 << 20):
                self.wfile.write(chunk)

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
        if path.startswith("/world/"):
            return self.send_file(WORLD, path[len("/world/"):])
        if path == "/api/comics":
            return self.send_json(all_comics())
        if path == "/api/dioramas":
            return self.send_json(diorama_file.shelf())
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
    args = parser.parse_args()
    RUNS = os.path.abspath(args.runs)
    SHOTS = os.path.abspath(args.shots)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print("Forge gallery", flush=True)
    print("  on this Mac:   http://localhost:%d" % args.port)
    print("  on your phone: http://%s:%d   (same Wi-Fi)" % (lan_address(), args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
