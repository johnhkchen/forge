"""Serve the gallery on the local network: every run, before and after.

    python3 scripts/gallery.py [--port 8028] [--runs DIR]

Read-only. Serves gallery/ (the page) and runs/ (the files), plus
/api/runs, a list of runs built from the folders on each request, so a new
run shows up on reload. Binds to all interfaces so a phone on the same Wi-Fi
can open it; nothing here is meant for the internet.
"""
import argparse
import json
import mimetypes
import os
import socket
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PAGE = os.path.join(ROOT, "gallery")
RUNS = os.path.join(ROOT, "runs")
PROFILE_ORDER = ["hero", "quads", "web", "game", "mobile", "midpoly", "lowpoly"]

mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("text/javascript", ".js")


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
        "picture": "image.png" if has("image.png") else None,
        "render": "render.png" if has("render.png") else None,
        "raw": "profiles/raw.glb" if has("profiles/raw.glb") else ("mesh.glb" if has("mesh.glb") else None),
        "gpu": mesh.get("gpu"),
        "mesh_seconds": (mesh.get("seconds") or {}),
        "score": polish.get("score"),
        "fixes": polish.get("fixes") or [],
        "problems": polish.get("problems") or [],
        "profiles": [profile_summary(run_dir, p) for p in names],
        "base": base_summary(run_dir),
        "props": [dict(p, run=os.path.basename(p.get("run", "").rstrip("/")))
                  for p in (read_json(os.path.join(run_dir, "props.json")) or {}).get("props", [])],
        "prop_of": os.path.basename(((read_json(os.path.join(run_dir, "prop_of.json")) or {}).get("character") or "").rstrip("/")) or None,
    }


def all_runs():
    if not os.path.isdir(RUNS):
        return []
    folders = [f for f in os.listdir(RUNS) if os.path.isdir(os.path.join(RUNS, f)) and not f.startswith(".")]
    return [run_summary(f) for f in sorted(folders, reverse=True)]


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
        if path.startswith("/runs/"):
            return self.send_file(RUNS, path[len("/runs/"):])
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
    args = parser.parse_args()
    RUNS = os.path.abspath(args.runs)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print("Forge gallery", flush=True)
    print("  on this Mac:   http://localhost:%d" % args.port)
    print("  on your phone: http://%s:%d   (same Wi-Fi)" % (lan_address(), args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
