"""Casting: finding a new member of the cast the way a casting director does, in plain files.

    python3 scripts/casting/casting.py status [role]
    python3 scripts/casting/casting.py plan <step> <role> [candidate] [--more n] [--variations n] [--shots a,b.2]
                                                                             what a step would do, and what it costs
    python3 scripts/casting/casting.py note <role> <candidate> "<words>" [--about look|moves|cards] [--take n]
    python3 scripts/casting/casting.py shortlist <role> <shot>               a headshot ("clerk", "clerk.2") becomes a candidate
    python3 scripts/casting/casting.py top <role> [n]                        the screen test's best n headshots, one a look first
    python3 scripts/casting/casting.py add-mesh <role> <shot> <run folder>   a headshot the mesh screen built
    python3 scripts/casting/casting.py unbuilt <role> <a,b.2>                of those, the ones not built yet
    python3 scripts/casting/casting.py screen-3d <role> [--again]            the mesh screen's free half: stood up, pictured, measured
    python3 scripts/casting/casting.py status-of <role> <candidate> shortlisted|let go|cast
    python3 scripts/casting/casting.py add-take <role> <candidate> <run folder> [--answers 1,2]
    python3 scripts/casting/casting.py retake <role> <candidate>             a new take of the same build, for notes on moves or cards
    python3 scripts/casting/casting.py has-look-notes <role> <candidate>     exits 0 when a revised take must be paid for
    python3 scripts/casting/casting.py add-look <role> '<brief json>'        a look Opus wrote, kept in role.json
    python3 scripts/casting/casting.py tape <role> <candidate> [--take n] [--runs runs] [--shots shots]
    python3 scripts/casting/casting.py judge <role> <candidate> [--take n] [--runs runs] [--shots shots]
    python3 scripts/casting/casting.py baseline <role>                       the judges on the cast member a candidate stands in for

A role is casting/<role>/role.json: the breakdown (who they are, the look, what must read as cards), canon
options for you to choose from, looks to draw headshots from (each a whole brief, as 1_describe writes one),
and how the chemistry read is set up. Each candidate is casting/<role>/candidates/<id>/candidate.json: where its
picture is, whether it is shortlisted, its takes (each a run folder in runs/) and your notes. The camera-test
scores of a take are casting/<role>/candidates/<id>/scores-<n>.json. Headshots are casting/<role>/headshots/.

Everything a take is filmed with is worked out again from the files, so nothing here goes stale:
  - the reel (casting/reel.json): the same scenes for every candidate. Most are the run's own clips
    (profiles/<version>-sides.glb, -walk, -run); the rest are made by `tape` into shots/casting/<role>/<id>-<n>/:
    the crew's dance with the candidate in one dancer's place (the chemistry read), the tag moves, and a
    sparring bout opposite Lincoln. Big files, so they stay out of git like the rest of shots/.
  - the stage a role has reached, from what its candidates have.

Paid steps (headshots, a first take, a revised take) are BAML (baml_src/12_casting) and are never started from
here: `plan` says what each would do and cost, and `just casting-*` runs one only when told `go`.
Free steps (`tape`, `judge`, `baseline`) run headless Blender, one at a time, and never touch an open Blender.
"""

import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CASTING = os.path.join(ROOT, "casting")
RUNS = os.path.join(ROOT, "runs")
SHOTS = os.path.join(ROOT, "shots")
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")  # a role's, a candidate's or a look's id: "robot", "tin-toy"
STATUSES = ("submitted", "shortlisted", "let go", "cast")
NOTE_ABOUT = {
    "look": "how it looks: a new picture and a new mesh",
    "moves": "how it moves: its walk, its sides, the way it is rigged",
    "cards": "how it reads as cards: baked again, or a note for the renderer",
}
NOTE_WORDS = 1000  # characters in one note
STAGES = [
    ("breakdown", "Breakdown", "Who the part is, what they look like, and what must read on screen."),
    ("headshots", "Headshots", "Pictures of possible looks, cheap to make; most are let go."),
    ("screen", "Screen test", "Every headshot measured on what the breakdown asks for, free, so the shortlist is picked on evidence."),
    ("shortlist", "Shortlist", "The few worth building."),
    ("tapes", "Tapes", "Built and rigged, each performs the same reel."),
    ("callbacks", "Callbacks", "Your notes, and the takes that answer them."),
    ("cast", "Cast", "Chosen. Then a place in canon and in the world, and an arrival by gachapon."),
]
FPS = 30

# What paid steps cost. Opus finishing a character in Blender is measured from the runs' own logs (each step's
# transcript ends with Claude Code's total_cost_usd); the rest are estimates, said as such on the page.
OPUS_SHORT_USD = (0.05, 0.20)   # one short structured reply with no tools (a brief, a gait, a revision): an estimate
RUNPOD_USD_PER_S = 0.00031      # an RTX 4090 on RunPod serverless, per second: an assumption; check your bill
FINISH_STEPS = ("polish", "parts", "lowpoly")
OPUS_LOOKS_USD = 1.80           # Opus writing four more looks for the robot, 2026-11-26: the Claude Code CLI's own cost_usd
VISION_USD = 0.21               # Haiku looking at 24 small headshots at once, 2026-11-26: the CLI's own cost_usd
MESH_SCREEN_SHOTS = 5           # how many of the screen test's best go on to be built as meshes, by default
UV_IMAGES = ["uv", "run", "--no-project", "--python", "3.12", "--with", "pillow", "--with", "numpy", "--with", "scipy", "python"]


SHOT = re.compile(r"^(?P<look>[a-z0-9][a-z0-9-]{0,47})(?:\.(?P<n>\d{1,3})(?:-(?P<colourway>[a-z0-9][a-z0-9-]{0,31}))?)?$")


def parse_shot(stem):
    """A headshot's name: "clerk" (picture 1), "clerk.2" (picture 2), "clerk.2-lilac" (picture 2 in the lilac
    colourway; the first picture's is "clerk.1-lilac"). Returns (look, n, colourway or None), or None."""
    m = SHOT.match(stem or "")
    return (m["look"], int(m["n"] or 1), m["colourway"]) if m else None


def shot_name(look, n=1, colourway=None):
    if colourway:
        return "%s.%d-%s" % (look, n, colourway)
    return look if n == 1 else "%s.%d" % (look, n)


def candidate_id(look, n=1, colourway=None):
    """The candidate a headshot makes: its look's id for the first picture, "<look>-<n>" for picture n, and
    "<look>-<n>-<colourway>" for one in another colourway."""
    if colourway:
        return "%s-%d-%s" % (look, n, colourway)
    return look if n == 1 else "%s-%d" % (look, n)


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w") as f:
        json.dump(value, f, indent=2)
        f.write("\n")
    os.replace(temp, path)


def checked(name, what="name"):
    if not isinstance(name, str) or not NAME.match(name):
        raise ValueError("not a %s: %r" % (what, name))
    return name


class Casting:
    """The casting folder, and the runs and shots it points at."""

    def __init__(self, root=CASTING, runs=RUNS, shots=SHOTS):
        self.root, self.runs, self.shots = root, runs, shots

    # ---------- reading ----------

    def roles(self):
        if not os.path.isdir(self.root):
            return []
        return sorted(r for r in os.listdir(self.root) if NAME.match(r) and os.path.isfile(os.path.join(self.root, r, "role.json")))

    def role(self, role):
        found = read_json(os.path.join(self.root, checked(role, "role"), "role.json"))
        if not found:
            raise ValueError("no such role")
        return found

    def reel(self):
        return read_json(os.path.join(self.root, "reel.json")) or {"sides": [], "clips": {}, "version": "lowpoly"}

    def candidate_path(self, role, candidate):
        return os.path.join(self.root, checked(role, "role"), "candidates", checked(candidate, "candidate"), "candidate.json")

    def candidates(self, role):
        folder = os.path.join(self.root, checked(role, "role"), "candidates")
        out = {}
        for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
            found = read_json(os.path.join(folder, name, "candidate.json")) if NAME.match(name) else None
            if found:
                out[name] = found
        return out

    def candidate(self, role, candidate):
        found = read_json(self.candidate_path(role, candidate))
        if not found:
            raise ValueError("no such candidate")
        return found

    def headshot(self, role, look, n=1, colourway=None):
        """Picture n of a look (in a colourway), if it is drawn: the JPEG git keeps, casting/<role>/headshots/<shot>.jpg
        (screen.py keep makes it from Codex's PNG in headshots/full/), or a PNG still at the top."""
        stem = shot_name(look, n, colourway)
        for ext in ("jpg", "png"):
            if os.path.isfile(os.path.join(self.root, role, "headshots", "%s.%s" % (stem, ext))):
                return "casting/%s/headshots/%s.%s" % (role, stem, ext)
        return None

    def pictures(self, role, look, colourways=False):
        """Every picture drawn of a look, in order: [(shot id, n, path)], the shot id being "clerk" or "clerk.2";
        with colourways, [(shot id, n, path, colourway)] for those drawn again in other colours ("clerk.2-lilac")."""
        folder = os.path.join(self.root, role, "headshots")
        found = set()
        for name in os.listdir(folder) if os.path.isdir(folder) else []:
            stem, ext = os.path.splitext(name)
            parsed = parse_shot(stem) if ext in (".png", ".jpg") else None
            if parsed and parsed[0] == look and bool(parsed[2]) == colourways:
                found.add((parsed[1], parsed[2] or ""))
        if colourways:
            return [(shot_name(look, n, c), n, self.headshot(role, look, n, c), c) for n, c in sorted(found)]
        return [(shot_name(look, n), n, self.headshot(role, look, n)) for n, _ in sorted(found)]

    def screen(self, role):
        """The screen test's file (scripts/casting/screen.py), if it has been run."""
        return read_json(os.path.join(self.root, role, "screen.json"))

    def meshes(self, role):
        """The mesh screen's file: for each headshot built by TRELLIS alone, its run and what was measured."""
        return read_json(os.path.join(self.root, role, "mesh-screen.json")) or {}

    @staticmethod
    def shot(shot):
        """A shot id split: "clerk.2" is ("clerk", 2, None), "clerk" ("clerk", 1, None), "clerk.2-lilac" ("clerk", 2,
        "lilac"). The candidate it makes is "clerk-2" or "clerk-2-lilac"."""
        parsed = parse_shot(str(shot))
        if not parsed:
            raise ValueError("not a headshot: %r" % shot)
        return checked(parsed[0], "look"), parsed[1], parsed[2]

    def take_dir(self, role, candidate, n):
        """Where a take's films for the page are made: shots/casting/<role>/<candidate>-<n>/ (out of git)."""
        return os.path.join(self.shots, "casting", role, "%s-%d" % (candidate, n))

    def take_id(self, role, candidate, n):
        return "casting/%s/%s-%d" % (role, candidate, n)

    # ---------- what a take can show ----------

    def run_brief(self, run):
        return read_json(os.path.join(self.runs, run, "brief.json")) or {}

    def has_cards(self, run):
        profiles = os.path.join(self.runs, run, "profiles")
        return os.path.isdir(profiles) and any("-impostor" in f for f in os.listdir(profiles))

    def clip_file(self, role, candidate, take, clip):
        """(path on disk, path the gallery serves it at) of one of a take's clips, from casting/reel.json's table."""
        reel = self.reel()
        how = (reel.get("clips") or {}).get(clip) or {}
        version = take.get("version") or reel.get("version", "lowpoly")
        swap = (self.role(role).get("chemistry") or {}).get("swap", "right")
        rel = (how.get("file") or "").format(version=version, swap=swap)
        if how.get("from") == "own":
            return os.path.join(self.runs, take["run"], rel), "runs/%s/%s" % (take["run"], rel)
        folder = self.take_dir(role, candidate, take["n"])
        return os.path.join(folder, rel), "shots/%s/%s" % (self.take_id(role, candidate, take["n"]), rel)

    def scenes(self, path):
        """The scenes of the sides clip, from the record tidy_profile wrote beside it (sides.py's RESULT)."""
        record = read_json(path[:-4] + ".json") or {}
        return {s["scene"]: s for s in (record.get("sides") or {}).get("scenes") or []}

    def reel_for(self, role, candidate, take):
        """Each side of the reel for one take: the file to play and the stretch of it, or what is missing."""
        reel = self.reel()
        out = []
        for side in reel.get("sides") or []:
            path, url = self.clip_file(role, candidate, take, side["clip"])
            how = (reel.get("clips") or {}).get(side["clip"]) or {}
            item = {"id": side["id"], "name": side["name"], "why": side.get("why"), "clip": side["clip"], "glb": url,
                    "ready": os.path.isfile(path), "from_s": None, "to_s": None, "made_by": how.get("made_by")}
            if item["ready"] and side.get("scene"):
                scene = self.scenes(path).get(side["scene"])
                if scene:
                    item["from_s"], item["to_s"] = scene["from"] / FPS, scene["to"] / FPS
                else:
                    item["ready"], item["made_by"] = False, "%s (made before this scene was in it)" % how.get("made_by")
            elif side.get("from") is not None:
                item["from_s"], item["to_s"] = side["from"] / FPS, side["to"] / FPS
            out.append(item)
        return out

    def scores(self, role, candidate, n):
        return read_json(os.path.join(self.root, role, "candidates", candidate, "scores-%d.json" % n))

    def baseline(self, role):
        return read_json(os.path.join(self.root, role, "baseline.json"))

    def height(self, run):
        """How tall the character stands, in metres: its brief's size, or what a cast measured."""
        return self.run_brief(run).get("size_m")

    # ---------- the board ----------

    def board(self, role, candidates=None):
        """Each stage, how many are at it, and the furthest stage reached."""
        info = self.role(role)
        candidates = self.candidates(role) if candidates is None else candidates
        looks = info.get("looks") or []
        pictured = [l for l in looks if self.pictures(role, l["id"])]
        drawn = sum(len(self.pictures(role, l["id"])) for l in looks)
        live = {k: c for k, c in candidates.items() if c.get("status") != "let go"}
        screened = (self.screen(role) or {}).get("shots") or []
        counts = {
            "breakdown": 1 if info.get("breakdown") else 0,
            "headshots": drawn + sum(1 for c in candidates.values() if c.get("stand_in")),
            "screen": len(screened),
            "shortlist": sum(1 for c in live.values() if c.get("status") in ("shortlisted", "cast")),
            "tapes": sum(1 for c in live.values() if c.get("takes")),
            "callbacks": sum(1 for c in live.values() if len(c.get("takes") or []) > 1 or c.get("notes")),
            "cast": sum(1 for c in candidates.values() if c.get("status") == "cast"),
        }
        reached = max([i for i, (key, _, _) in enumerate(STAGES) if counts[key]] or [0])
        return {"stages": [{"id": key, "name": name, "about": about, "count": counts[key], "reached": i <= reached}
                           for i, (key, name, about) in enumerate(STAGES)],
                "now": STAGES[reached][0], "looks": len(looks), "pictured": len(pictured), "drawn": drawn, "screened": len(screened)}

    def summary(self, role):
        """Everything the casting page shows for one role."""
        info = self.role(role)
        candidates = self.candidates(role)
        swap = (info.get("chemistry") or {}).get("swap", "right")
        people = []
        for cid, c in candidates.items():
            takes = []
            for take in c.get("takes") or []:
                brief = self.run_brief(take["run"]) if take.get("run") else {}
                folder = self.take_dir(role, cid, take["n"])
                takes.append(dict(take,
                    run_name=brief.get("name"), height_m=brief.get("size_m"),
                    picture="runs/%s/image.png" % take["run"] if take.get("run") and os.path.isfile(os.path.join(self.runs, take["run"], "image.png")) else None,
                    cards=bool(take.get("run")) and self.has_cards(take["run"]),
                    reel=self.reel_for(role, cid, take) if take.get("run") else [],
                    chemistry=self.take_id(role, cid, take["n"]) if os.path.isfile(os.path.join(folder, "cast-crew.json")) else None,
                    fight=self.take_id(role, cid, take["n"]) + "/fight" if os.path.isfile(os.path.join(folder, "fight", "cast-fight.json")) else None,
                    scores=self.scores(role, cid, take["n"]),
                    notes=[n for n in c.get("notes") or [] if n.get("take") == take["n"]]))
            picture = c.get("picture") or {}
            people.append({"id": cid, "name": c.get("name") or cid, "stand_in": bool(c.get("stand_in")), "why": c.get("why"),
                           "look": c.get("look"), "status": c.get("status", "submitted"),
                           "picture": ("runs/%s/%s" % (picture["run"], picture.get("file", "image.png")) if picture.get("run")
                                       else self.headshot(role, c.get("look"), c.get("variation") or 1, c.get("colourway")) if c.get("look") else None),
                           "takes": takes, "notes": c.get("notes") or [],
                           "open_notes": [n for n in c.get("notes") or [] if not n.get("answered_by")]})
        meshes = self.meshes(role)
        looks = [{"id": l["id"], "name": l.get("name"), "why": l.get("why"), "suits": l.get("suits"), "picture": self.headshot(role, l["id"]),
                  "brief": l.get("brief"), "candidate": next((k for k, c in candidates.items() if c.get("look") == l["id"]), None),
                  "pictures": [{"shot": shot, "n": n, "picture": path, "candidate": candidate_id(l["id"], n) if candidate_id(l["id"], n) in candidates else None}
                               for shot, n, path in self.pictures(role, l["id"])],
                  "colourways": [dict(w, picture=self.headshot(role, *self.shot(w["headshot"])))
                                 for w in l.get("colourways") or []]}
                 for l in info.get("looks") or []]
        screen = self.screen(role)
        if screen:
            for row in screen.get("shots") or []:
                look, n, colourway = self.shot(row["id"])
                cid = candidate_id(look, n, colourway)
                row["candidate"] = cid if cid in candidates else None
                row["mesh"] = meshes.get(row["id"])
        names = (info.get("chemistry") or {}).get("names") or {}
        line_up = [{"run": r, "name": self.run_brief(r).get("name") or r, "short": names.get(r), "height_m": self.height(r),
                    "picture": "runs/%s/image.png" % r, "card": "runs/%s/card.jpg" % r} for r in (info.get("chemistry") or {}).get("line_up") or []]
        return {"id": role, "title": info.get("title") or role, "drafted": info.get("drafted"), "breakdown": info.get("breakdown"),
                "canon_options": info.get("canon_options") or [], "canon_choice": info.get("canon_choice"),
                "looks": looks, "candidates": people, "board": self.board(role, candidates), "chemistry": dict(info.get("chemistry") or {}, line_up=line_up),
                "swap": swap, "reel": self.reel(), "baseline": self.baseline(role), "costs": self.costs(), "steps": self.steps(role),
                "screen": screen, "meshes": meshes}

    # ---------- what things cost ----------

    def costs(self):
        """What a paid step costs, from what the runs so far really cost, with where each number comes from."""
        finishing, gpu = [], []
        for run in sorted(os.listdir(self.runs)) if os.path.isdir(self.runs) else []:
            if not (self.run_brief(run).get("character")):
                continue
            spent = [opus_cost(os.path.join(self.runs, run, "transcripts", step + ".jsonl")) for step in FINISH_STEPS]
            if all(s is not None for s in spent):
                finishing.append(sum(spent))
            mesh = read_json(os.path.join(self.runs, run, "mesh.json")) or {}
            if mesh.get("wall_seconds"):
                gpu.append(mesh["wall_seconds"])
        finish = {"low": round(min(finishing), 2), "typical": round(statistics.median(finishing), 2), "high": round(max(finishing), 2),
                  "characters": len(finishing)} if finishing else {"low": 2.5, "typical": 3.5, "high": 4.6, "characters": 0}
        mesh_s = statistics.median(gpu) if gpu else 180
        return {
            "finish": dict(finish, about="Claude (Opus) finishing a character in Blender: tidying, finding its parts, building its low-poly body. Measured from %d characters' logs." % finish["characters"]),
            "short": {"low": OPUS_SHORT_USD[0], "high": OPUS_SHORT_USD[1], "about": "One short answer from Opus with no tools (a brief, how it walks, a revision). An estimate."},
            "picture": {"about": "One Codex picture, on your ChatGPT plan: no bill of its own, but it counts against the plan's pictures."},
            "mesh": {"seconds": round(mesh_s), "usd": round(mesh_s * RUNPOD_USD_PER_S, 2), "about": "TRELLIS.2 on your RunPod GPU, about %d s a mesh with the worker waking up (the runs' own timings), at an assumed $%.5f a second." % (mesh_s, RUNPOD_USD_PER_S)},
            "run": {"usd": 0.05, "about": "One sentence to Kimodo on the RunPod motion worker for its run: a few seconds of GPU once it is awake. An estimate."},
        }

    def to_draw(self, role, more=0, variations=1):
        """How many Codex pictures `casting-headshots` would draw: every picture up to `variations` of each look that
        is not there yet, and `variations` of each of `more` new looks."""
        looks = self.role(role).get("looks") or []
        have = sum(min(variations, len([p for p in self.pictures(role, l["id"]) if p[1] <= variations])) for l in looks)
        return len(looks) * variations - have + more * variations

    def colourways_to_draw(self, role):
        """The colourways written in role.json whose picture is not drawn yet, though the headshot they come from is."""
        out = []
        for l in self.role(role).get("looks") or []:
            for w in l.get("colourways") or []:
                look, n, c = self.shot(w["headshot"])
                if not self.headshot(role, look, n, c) and self.headshot(role, *self.shot(w["of"])[:2]):
                    out.append(w["headshot"])
        return out

    def top_shots(self, role, n=MESH_SCREEN_SHOTS):
        """The best `n` headshots of the screen test, by total, no two of one look first, then the next best."""
        rows = (self.screen(role) or {}).get("shots") or []
        best, seen = [], set()
        for row in rows:
            if row["look"] not in seen and not row.get("flags"):
                best.append(row["id"])
                seen.add(row["look"])
        best += [r["id"] for r in rows if r["id"] not in best]
        return best[:n]

    def steps(self, role, more=0, variations=1, shots=None):
        """Every step of a casting, in order, with whether it is paid, what it costs, and the command."""
        c = self.costs()
        looks = len(self.role(role).get("looks") or [])
        drawing = self.to_draw(role, more, variations)
        short, finish, mesh = c["short"], c["finish"], c["mesh"]
        take_low = round(finish["low"] + short["low"] + mesh["usd"] + c["run"]["usd"], 2)
        take_high = round(finish["high"] + short["high"] + mesh["usd"] + c["run"]["usd"], 2)
        shots = list(shots) if shots else self.top_shots(role)
        mesh_usd = round(len(shots) * mesh["usd"], 2)
        opus = "; Opus writes %d more looks first: one ask, about $%.2f to $%.2f (the last such ask, four looks, was $%.2f by the CLI's own count)" % (
            more, short["low"], OPUS_LOOKS_USD, OPUS_LOOKS_USD) if more else ""
        return [
            {"id": "headshots", "name": "Draw the headshots", "paid": True, "low": 0, "high": OPUS_LOOKS_USD if more else 0, "pictures": drawing,
             "what": "Codex draws %d picture%s of each look in the breakdown (%d looks now), each a different design of the same brief, only those not drawn yet: %d to draw. Asking Opus for more looks first adds one answer." % (
                 variations, "s" if variations > 1 else "", looks, drawing),
             "cost": "%d Codex pictures on your ChatGPT plan%s." % (drawing, opus),
             "command": "just casting-headshots %s go %d %d" % (role, more, variations)},
            {"id": "colourways", "name": "Draw the colourways", "paid": True, "low": 0, "high": 0, "pictures": len(self.colourways_to_draw(role)),
             "what": "Codex draws a headshot again in each colourway written for it in the breakdown, shown the headshot and told to change only its colours: %d to draw." % len(self.colourways_to_draw(role)),
             "cost": "%d Codex pictures on your ChatGPT plan. Nothing on Opus." % len(self.colourways_to_draw(role)),
             "command": "just casting-colourways %s go" % role},
            {"id": "screen", "name": "Screen every headshot", "paid": False, "low": 0, "high": 0,
             "what": "Free, on this Mac, a few seconds: every headshot measured on what the breakdown asks for (does it build, does it stand apart from the cast, does its face read at the crew camera's size, its colours, anything thin or loose), then ranked.",
             "cost": "Free. Adding look=look shows Haiku every headshot once for the must-nots a picture alone can't measure (text, a glow, something held): about $%.2f by the CLI's own count." % VISION_USD,
             "command": "just casting-screen %s" % role},
            {"id": "mesh", "name": "Build the best few as meshes", "paid": True, "low": mesh_usd, "high": mesh_usd, "shots": shots,
             "what": "TRELLIS.2 alone builds the %d best headshots of the screen test (%s): no Claude, no rig, no motion. Then, free, each is stood up, sized and pictured from all round, at full size and at the crew camera's, and set against its picture. A take of one of them starts from this mesh, so it is not paid for twice." % (
                 len(shots), ", ".join(shots) or "none screened yet"),
             "cost": "About $%.2f: %d meshes at about $%.2f of RunPod GPU each (%d s with the worker waking up, the runs' own median, at an assumed $%.5f a second). Nothing on Opus." % (
                 mesh_usd, len(shots), mesh["usd"], mesh["seconds"], RUNPOD_USD_PER_S),
             "command": "just casting-mesh-screen %s %s go" % (role, ",".join(shots) or "<shots>")},
            {"id": "take", "name": "Build a first take", "paid": True, "low": take_low, "high": take_high,
             "what": "A shortlisted headshot becomes a character: TRELLIS.2 makes the mesh, Claude finishes it in Blender, it gets its low-poly body, a skeleton, a walk, and a run from Kimodo.",
             "cost": "About $%.2f to $%.2f: Claude in Blender $%.2f to $%.2f (typically $%.2f), how it walks $%.2f to $%.2f, the mesh about $%.2f of GPU, the run a few cents." % (
                 take_low, take_high, finish["low"], finish["high"], finish["typical"], short["low"], short["high"], mesh["usd"]),
             "command": "just casting-take %s <candidate> go" % role},
            {"id": "tape", "name": "Tape the reel", "paid": False, "low": 0, "high": 0,
             "what": "Free, on this Mac: the sides and the warm-up on its own skeleton, its cards baked, then the tag moves, the crew's dance in the pirate's place and a sparring bout with Lincoln. A few minutes of background Blender.",
             "cost": "Free.", "command": "just casting-tape %s <candidate>" % role},
            {"id": "judge", "name": "Run the camera test", "paid": False, "low": 0, "high": 0,
             "what": "Free: the renderer's own judges on the candidate in the crew's dance (what shows at the joints, how a bent joint reads, and the face when it has a recipe), side by side with the cast member it stands in for.",
             "cost": "Free. About ten minutes of background Blender.", "command": "just casting-judge %s <candidate>" % role},
            {"id": "revise", "name": "Make a revised take", "paid": True, "low": 0, "high": take_high,
             "what": "Your open notes become the next take. A note about the look rewrites the brief (Opus), draws it again from the last picture (Codex) and builds it again; notes about moves or cards are free and only tape and judge again.",
             "cost": "Notes on moves or cards: free. A note on the look: about $%.2f to $%.2f, as a first take." % (take_low, take_high),
             "command": "just casting-revise %s <candidate> go" % role},
        ]

    def plan(self, step, role, candidate=None, more=0, variations=1, shots=None):
        """What a step would do for this role and candidate, without doing it."""
        if shots:
            for s in shots:
                look, n, colourway = self.shot(s)
                if not self.headshot(role, look, n, colourway):
                    raise ValueError("no headshot %s" % s)
        steps = {s["id"]: s for s in self.steps(role, int(more or 0), max(1, int(variations or 1)), shots)}
        if step not in steps:
            raise ValueError("no such step: %s (one of %s)" % (step, ", ".join(steps)))
        out = dict(steps[step], role=role, candidate=candidate, dry_run=True)
        out["command"] = out["command"].replace("<candidate>", candidate or "<candidate>")
        if step == "mesh":
            built = [s for s in out["shots"] if s in self.meshes(role)]
            if built:
                out["warning"] = "Built already, and not built again: %s." % ", ".join(built)
        if candidate:
            c = self.candidate(role, candidate)
            if step == "take" and c.get("screen_run"):
                mesh = self.costs()["mesh"]["usd"]
                out["low"], out["high"] = round(out["low"] - mesh, 2), round(out["high"] - mesh, 2)
                out["cost"] = "About $%.2f to $%.2f: its mesh is built already (the mesh screen), so as a first take less the mesh." % (out["low"], out["high"])
            if step == "take" and c.get("takes"):
                out["warning"] = "It has %d take(s) already; a revised take is `revise`." % len(c["takes"])
            if step == "take" and not c.get("look"):
                out["warning"] = "A stand-in has no look of its own to build from."
            if step == "revise":
                open_notes = [n for n in c.get("notes") or [] if not n.get("answered_by")]
                paid = [n for n in open_notes if n.get("about") == "look"]
                out["notes"] = open_notes
                out["paid"] = bool(paid)
                out["cost"] = steps["revise"]["cost"] if paid else "Free: no open note is about the look."
                if not open_notes:
                    out["warning"] = "No open notes to answer. Give a note first."
                if paid and c.get("stand_in"):
                    out["warning"] = "A stand-in is not rebuilt; its notes about the look stay open."
            if step in ("tape", "judge"):
                take = (c.get("takes") or [{}])[-1]
                out["take"] = take.get("n")
                out["ready"] = [s["id"] for s in self.reel_for(role, candidate, take) if s["ready"]] if take.get("run") else []
        return out

    # ---------- writing (the only things the gallery may change) ----------

    def add_note(self, role, candidate, text, about="look", take=None):
        if about not in NOTE_ABOUT:
            raise ValueError("a note is about one of: %s" % ", ".join(NOTE_ABOUT))
        text = (text or "").strip()
        if not text:
            raise ValueError("an empty note")
        if len(text) > NOTE_WORDS:
            raise ValueError("a note is at most %d characters" % NOTE_WORDS)
        c = self.candidate(role, candidate)
        takes = [t["n"] for t in c.get("takes") or []]
        if take is None:
            take = takes[-1] if takes else None
        elif take not in takes:
            raise ValueError("no such take")
        notes = c.setdefault("notes", [])
        note = {"id": max([n["id"] for n in notes] or [0]) + 1, "take": take, "about": about, "text": text,
                "at": time.strftime("%Y-%m-%d %H:%M", time.localtime()), "answered_by": None}
        notes.append(note)
        write_json(self.candidate_path(role, candidate), c)
        return note

    def set_status(self, role, candidate, status):
        if status not in STATUSES:
            raise ValueError("a status is one of: %s" % ", ".join(STATUSES))
        c = self.candidate(role, candidate)
        if status == "cast" and c.get("stand_in"):
            raise ValueError("a stand-in is already in the cast; it cannot be cast in this part")
        if status == "cast" and not c.get("takes"):
            raise ValueError("cast someone only after a take")
        c["status"] = status
        write_json(self.candidate_path(role, candidate), c)
        return c

    def shortlist(self, role, shot):
        """A headshot you like becomes a candidate, shortlisted, with no take yet. `shot` is a look's id for its first
        picture ("clerk", candidate "clerk") or "<look>.<n>" for another ("clerk.2", candidate "clerk-2"). When the
        mesh screen built it, the candidate keeps that run, and its first take starts from it."""
        info = self.role(role)
        look, n, colourway = self.shot(shot)
        found = next((l for l in info.get("looks") or [] if l["id"] == look), None)
        if not found:
            raise ValueError("no such look")
        if colourway and not any(w["id"] == colourway for w in found.get("colourways") or []):
            raise ValueError("no colourway %s of %s in the role" % (colourway, look))
        if not self.headshot(role, look, n, colourway):
            raise ValueError("that look has no headshot yet" if n == 1 else "that look has no picture %d" % n)
        path = self.candidate_path(role, candidate_id(look, n, colourway))
        if os.path.isfile(path):
            c = read_json(path)
            c["status"] = "shortlisted" if c.get("status") in ("submitted", "let go") else c.get("status")
        else:
            way = next((w for w in found.get("colourways") or [] if w["id"] == colourway), None) if colourway else None
            if colourway and not way:
                raise ValueError("no colourway %s of %s in the role" % (colourway, look))
            c = {"name": (found.get("name") or look) + ("" if n == 1 else " (%d)" % n) + (", %s" % way["name"].lower() if way else ""),
                 "stand_in": False, "why": way["why"] if way else found.get("why"),
                 "look": look, "variation": n, "status": "shortlisted", "takes": [], "notes": []}
            if way:
                c["colourway"] = colourway
        built = self.meshes(role).get(shot_name(look, n, colourway))
        if built and not c.get("screen_run"):
            c["screen_run"] = built["run"]
        write_json(path, c)
        return c

    def add_mesh(self, role, shot, run):
        """A headshot the mesh screen built: its run (a run folder with mesh.glb and nothing more), kept in
        casting/<role>/mesh-screen.json, and on its candidate if it is shortlisted already."""
        look, n, colourway = self.shot(shot)
        run = os.path.basename(os.path.normpath(run))
        if not os.path.isfile(os.path.join(self.runs, run, "mesh.glb")):
            raise ValueError("no mesh in run %s" % run)
        meshes = self.meshes(role)
        meshes[shot] = dict(meshes.get(shot) or {}, run=run, made=time.strftime("%Y-%m-%d", time.localtime()))
        write_json(os.path.join(self.root, role, "mesh-screen.json"), meshes)
        path = self.candidate_path(role, candidate_id(look, n, colourway))
        if os.path.isfile(path):
            c = read_json(path)
            c.setdefault("screen_run", run)
            write_json(path, c)
        return meshes[shot]

    def add_take(self, role, candidate, run, answers=()):
        """A new take: a run folder made for this candidate. The notes it answers are marked answered by it."""
        run = os.path.basename(os.path.normpath(run))
        if not os.path.isfile(os.path.join(self.runs, run, "brief.json")):
            raise ValueError("no run folder %s in %s" % (run, self.runs))
        c = self.candidate(role, candidate)
        n = max([t["n"] for t in c.get("takes") or []] or [0]) + 1
        c.setdefault("takes", []).append({"n": n, "run": run, "made": time.strftime("%Y-%m-%d", time.localtime()),
                                          "how": "Answers notes %s." % ", ".join(str(a) for a in answers) if answers else "From the headshot.",
                                          "answers": list(answers)})
        for note in c.get("notes") or []:
            if note["id"] in answers:
                note["answered_by"] = n
        write_json(self.candidate_path(role, candidate), c)
        return n

    def retake(self, role, candidate):
        """The free kind of callback: the open notes about moves or cards answered by a new take of the same build,
        taped and judged again (after the sides, the rig or the renderer changed). Returns the new take's number."""
        c = self.candidate(role, candidate)
        if not c.get("takes"):
            raise ValueError("no take to tape again: build one first")
        notes = [n["id"] for n in c.get("notes") or [] if not n.get("answered_by") and n.get("about") in ("moves", "cards")]
        if not notes:
            raise ValueError("no open notes on its moves or cards to answer: give a note first")
        n = self.add_take(role, candidate, c["takes"][-1]["run"], notes)
        c = self.candidate(role, candidate)
        c["takes"][-1]["how"] = "The same build, taped and judged again%s." % (" for notes %s" % ", ".join(map(str, notes)) if notes else "")
        write_json(self.candidate_path(role, candidate), c)
        return n

    def look_notes(self, role, candidate):
        """Open notes about the look: the ones only a paid take can answer."""
        return [n for n in self.candidate(role, candidate).get("notes") or [] if not n.get("answered_by") and n.get("about") == "look"]

    def add_look(self, role, idea):
        """A look Opus wrote (CastingLooks) kept in role.json, under an id made from its name. `idea` is
        {"brief": ..., "why": ..., "suits": <a canon option's id or null>}, or a bare brief."""
        brief = idea.get("brief") if isinstance(idea, dict) and isinstance(idea.get("brief"), dict) else idea
        if not isinstance(brief, dict) or not brief.get("name") or not brief.get("subject"):
            raise ValueError("a look is a whole brief")
        info = self.role(role)
        base = "-".join("".join(ch if ch.isascii() and ch.isalnum() else " " for ch in brief["name"].lower()).split())[:40].strip("-") or "look"
        taken = {l["id"] for l in info.get("looks") or []}
        look = base if base not in taken else next("%s-%d" % (base, i) for i in range(2, 99) if "%s-%d" % (base, i) not in taken)
        entry = {"id": look, "name": brief["name"], "why": (idea.get("why") if brief is not idea else None) or "Written by Opus from the breakdown.", "brief": brief}
        suits = idea.get("suits") if brief is not idea else None
        if suits in {o.get("id") for o in info.get("canon_options") or []}:
            entry["suits"] = suits
        info.setdefault("looks", []).append(entry)
        write_json(os.path.join(self.root, role, "role.json"), info)
        return look

    def answer(self, role, candidate, ids, take):
        """Mark notes answered by a take that was taped or judged again rather than built again (notes on moves, cards)."""
        c = self.candidate(role, candidate)
        for note in c.get("notes") or []:
            if note["id"] in ids:
                note["answered_by"] = take
        write_json(self.candidate_path(role, candidate), c)


def opus_cost(path):
    """total_cost_usd of the last result event in a Claude Code event log (scripts/claude-logged), or None."""
    cost = None
    try:
        with open(path) as f:
            for line in f:
                if '"total_cost_usd"' in line:
                    try:
                        cost = json.loads(line).get("total_cost_usd", cost)
                    except ValueError:
                        pass
    except OSError:
        return None
    return cost


# ---------- the camera test, summed up ----------

LOOK_NAMES = {"comic": "Comic", "pixel-baked": "Pixels, baked", "pixel-both": "Pixels, both", "joe": "Bold ink"}


def sum_seams(found, role):
    """judge_seams.py's rows for one of the cast, as a few numbers a look: per thousand of the body's pixels, ink
    lines the real model has not got (dark), and body the cards leave see-through (open); dance and walk together."""
    out = {}
    for row in (found or {}).get("rows") or []:
        if row.get("role") != role:
            continue
        look = out.setdefault(row.get("look"), {"body": 0, "dark": 0, "open": 0, "hole": 0, "frames": 0})
        for k in ("body", "dark", "open", "hole"):
            look[k] += row.get(k) or 0
        look["frames"] += 1
    return {name: {"dark": round(1000.0 * v["dark"] / v["body"], 1), "open": round(1000.0 * v["open"] / v["body"], 1),
                   "holes": round(1000.0 * v["hole"] / v["body"], 1), "frames": v["frames"]}
            for name, v in out.items() if v["body"]}


def sum_joints(found, role):
    """judge_joints.py's rows for one of the cast: likeness (1 is the model's own light and dark) and blots (share
    of a joint that is darker than it should be), a look and a kind of joint, and over all its joints."""
    out = {}
    for row in (found or {}).get("rows") or []:
        if row.get("role") != role or row.get("kind") == "shaft":
            continue
        for kind in (row.get("kind"), "all"):
            cell = out.setdefault(row.get("look"), {}).setdefault(kind, {"likeness": [], "blots": []})
            cell["likeness"].append(row.get("likeness") or 0)
            cell["blots"].append(row.get("blots") or 0)
    return {look: {kind: {"likeness": round(statistics.mean(v["likeness"]), 3), "blots": round(statistics.mean(v["blots"]), 3), "joints": len(v["likeness"])}
                   for kind, v in kinds.items()} for look, kinds in out.items()}


def sum_faces(found, role):
    """judge_faces.py's table for one of the cast: how much of the face is kept, a look and an eye."""
    out = {}
    for key, cell in ((found or {}).get("table") or {}).items():
        eye, look, who = key.split("|")
        if who == role:
            out.setdefault(look, {})[eye] = {"kept": cell.get("kept"), "likeness": cell.get("likeness")}
    return out


def summed(folder, role, tag):
    seams = read_json(os.path.join(folder, "seams-%s.json" % tag))
    joints = read_json(os.path.join(folder, "joints-%s.json" % tag))
    faces = read_json(os.path.join(folder, "faces-%s.json" % tag))
    return {"seams": sum_seams(seams, role) if seams else None, "joints": sum_joints(joints, role) if joints else None,
            "faces": sum_faces(faces, role) if faces else None, "looks": LOOK_NAMES,
            "made": time.strftime("%Y-%m-%d %H:%M", time.localtime())}


# ---------- free steps: headless Blender ----------

def blender(script, args, log):
    """One background Blender; its marked lines go to the log as they come. Raises when it fails."""
    command = [BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P", os.path.join(ROOT, script), "--"] + args
    print("CASTING running %s" % os.path.basename(script), flush=True)
    with open(log, "a") as out:
        out.write("$ %s\n" % " ".join(command))
        out.flush()
        done = subprocess.run(command, stdout=out, stderr=subprocess.STDOUT, cwd=ROOT)
    if done.returncode:
        raise RuntimeError("%s failed: see %s" % (os.path.basename(script), log))


def pick_take(candidate, n=None):
    """Take n of a candidate, or its newest; None when it has none (or no such take)."""
    takes = candidate.get("takes") or []
    if n is None:
        return takes[-1] if takes else None
    return next((t for t in takes if t["n"] == n), None)


def copy_motion(source, folder):
    """A shot role's motion, ready for apply_shot.py to play on someone else: its three plain files."""
    os.makedirs(folder, exist_ok=True)
    for name in ("motion.json", "plan.json", "shotlist.json"):
        shutil.copyfile(os.path.join(source, name), os.path.join(folder, name))


def run_json(command, log):
    """A command whose last RESULT line is JSON; its output to the log. Raises when it fails."""
    with open(log, "a") as out:
        out.write("$ %s\n" % " ".join(command))
        out.flush()
        done = subprocess.run(command, stdout=subprocess.PIPE, stderr=out, cwd=ROOT, text=True)
        out.write(done.stdout)
    if done.returncode:
        raise RuntimeError("%s failed: see %s" % (os.path.basename(command[-1] if command else "?"), log))
    found = [line[7:] for line in done.stdout.splitlines() if line.startswith("RESULT ")]
    return json.loads(found[-1]) if found else {}


def screen_3d(cast, role, again=False):
    """The mesh screen's free half, for every headshot the paid half built: each mesh stood up, sized and pictured
    from all round in background Blender (screen_mesh.py), then set against its headshot (screen.py turn). Writes
    casting/<role>/screen/<shot>-turn.png and the numbers into casting/<role>/mesh-screen.json."""
    info = cast.role(role)
    looks = {l["id"]: l for l in info.get("looks") or []}
    meshes = cast.meshes(role)
    folder = os.path.join(cast.root, role, "screen")
    os.makedirs(folder, exist_ok=True)
    log = os.path.join(folder, "mesh-screen.log")
    for shot, record in sorted(meshes.items()):
        if record.get("turn") and not again:
            continue
        look, n, colourway = cast.shot(shot)
        height = (looks.get(look, {}).get("brief") or {}).get("size_m") or (info.get("breakdown") or {}).get("height_m") or 1.5
        renders = os.path.join(cast.shots, "casting", role, "mesh-" + shot)
        mesh = run_json([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P", os.path.join(ROOT, "scripts", "casting", "screen_mesh.py"), "--",
                         os.path.join(cast.runs, record["run"], "mesh.glb"), renders, str(height)], log)
        sheet = os.path.join(folder, shot + "-turn.png")
        against = run_json(UV_IMAGES + [os.path.join(ROOT, "scripts", "casting", "screen.py"), "turn",
                                        os.path.join(ROOT, cast.headshot(role, look, n, colourway)), renders, str(height), sheet], log)
        meshes[shot] = dict(record, mesh=mesh, against=against, turn="casting/%s/screen/%s-turn.png" % (role, shot))
        write_json(os.path.join(cast.root, role, "mesh-screen.json"), meshes)
        print("CASTING mesh screen %s: %s" % (shot, json.dumps(dict(mesh, **against))), flush=True)
    return meshes


def tape(cast, role, candidate, n=None):
    """Everything a take's reel and chemistry need that is free to make: the sides and the warm-up on its own
    skeleton, cards (from the detailed mesh, on the low-poly skeleton, as the crew's), the tag moves, the crew's
    dance in the swapped dancer's place, and a sparring bout opposite Lincoln. Skips whatever is there already."""
    take = pick_take(cast.candidate(role, candidate), n)
    if not take or not take.get("run"):
        raise ValueError("no take to tape: build one first")
    info, reel = cast.role(role), cast.reel()
    version = take.get("version") or reel.get("version", "lowpoly")
    run = os.path.join(cast.runs, take["run"])
    folder = cast.take_dir(role, candidate, take["n"])
    os.makedirs(folder, exist_ok=True)
    log = os.path.join(folder, "tape.log")
    profiles = os.path.join(run, "profiles")
    source = os.path.join(run, "scene.blend") if os.path.isfile(os.path.join(run, "scene.blend")) else os.path.join(run, "mesh.glb")
    #  1. the sides and the warm-up, on its own skeleton (tidy-mesh: sides.py, rom.py)
    wanted = [p for p in ("sides", "rom") if not os.path.isfile(os.path.join(profiles, "%s-%s.glb" % (version, p)))]
    if wanted:
        blender("scripts/tidy_profile.py", [source, profiles] + wanted, log)
    #  2. cards, pictured from the detailed mesh given the low-poly skeleton (just impostor-detailed <run> lowpoly)
    if not cast.has_cards(take["run"]):
        blender("scripts/impostor/rig_detailed.py", [run, "--from", version], log)
        for look in (["--look", "pixel", "--px", "96"], ["--views", "26"], ["--look", "joe", "--views", "26"]):
            blender("scripts/impostor/bake_impostor.py", [run, "detailed"] + look + ["--soften", "512", "--plays", version, "--title", "Detailed model"], log)
        blender("scripts/impostor/bake_joints.py", [run, "detailed"], log)
    #  3. the tag moves (shots/tag-moves), played on it
    tag = os.path.join(folder, "tag")
    if not os.path.isfile(os.path.join(tag, "%s-tag.glb" % version)):
        copy_motion(os.path.join(cast.shots, "tag-moves"), tag)
        blender("scripts/motion/apply_shot.py", [tag, run, "--versions", version, "--name", "tag"], log)
    #  4. the chemistry read: the crew's take with the candidate in one dancer's place
    chem = info.get("chemistry") or {}
    crew = os.path.join(cast.shots, chem.get("take", "crew-candy-shop"))
    swap = chem.get("swap", "right")
    mine = os.path.join(folder, swap)
    if not os.path.isfile(os.path.join(mine, "%s-crew.glb" % version)):
        copy_motion(os.path.join(crew, swap), mine)
        blender("scripts/motion/apply_shot.py", [mine, run, "--versions", version, "--name", "crew"], log)
    write_chemistry(cast, role, candidate, take, crew, swap, version)
    #  5. a sparring bout from the fight kit, the candidate in the left corner, opposite the role's chosen partner
    bout = os.path.join(folder, "fight")
    if not os.path.isfile(os.path.join(bout, "cast-left.glb")):
        os.makedirs(bout, exist_ok=True)
        fight = os.path.join(ROOT, "scripts", "fight", "fights", "%s.json" % chem.get("fight", "first"))
        blender("scripts/fight/apply_fight.py", [fight, bout, "--left", run, "--right", os.path.join(cast.runs, chem["opposite"]),
                                                 "--left-version", version, "--right-version", "lowpoly"], log)
    write_bout(cast, role, candidate, take, bout, chem)
    return {"take": take["n"], "folder": folder, "reel": [s["id"] for s in cast.reel_for(role, candidate, take) if s["ready"]]}


def write_chemistry(cast, role, candidate, take, crew, swap, version):
    """The take file the watch page and the judges read: the crew's own cast file with one role replaced."""
    folder = cast.take_dir(role, candidate, take["n"])
    original = read_json(os.path.join(crew, next(f for f in sorted(os.listdir(crew)) if f.startswith("cast-") and f.endswith(".json"))))
    up = os.path.relpath(crew, folder)
    roles = {}
    for name, part in original["roles"].items():
        roles[name] = dict(part, glb=os.path.join(up, part["glb"]))
    record = read_json(os.path.join(folder, swap, "%s-crew.json" % version)) or {}
    brief = cast.run_brief(take["run"])
    who = os.path.join(cast.runs, take["run"], "lowpoly.glb" if version == "lowpoly" else os.path.join("profiles", version + ".glb"))
    roles[swap] = {"character": who, "glb": "%s/%s-crew.glb" % (swap, version),
                   "size_against_soma": record.get("size_against_soma", 1.0), "true_size": record.get("true_size")}
    write_json(os.path.join(folder, "cast-crew.json"), dict(original, roles=roles, films={}))
    take_file = read_json(os.path.join(crew, "take.json")) or {}
    name = brief.get("name") or candidate
    write_json(os.path.join(folder, "take.json"), dict(take_file, name=cast.take_id(role, candidate, take["n"]),
               title="The candy-shop routine, with the %s in the %s's place" % (name.lower(), (cast.role(role).get("chemistry") or {}).get("swap_name", swap).replace("the ", "")),
               about="A chemistry read: the crew's dance as it was filmed, with one dancer's part played by a candidate for %s." % (cast.role(role).get("title") or role).lower()))


def write_bout(cast, role, candidate, take, bout, chem):
    if not os.path.isfile(os.path.join(bout, "cast-left.glb")):
        return
    fight = read_json(os.path.join(bout, "fight.json")) or {}
    opposite = os.path.join(cast.runs, chem["opposite"], "lowpoly.glb")
    version = take.get("version") or cast.reel().get("version", "lowpoly")
    me = os.path.join(cast.runs, take["run"], "lowpoly.glb" if version == "lowpoly" else os.path.join("profiles", version + ".glb"))
    write_json(os.path.join(bout, "cast-fight.json"), {"set": fight.get("set", "ring"), "clip": "fight", "version": "cast", "frames": fight.get("frames"),
               "seconds": fight.get("seconds"), "cameras": [], "films": {}, "handshakes": [],
               "roles": {"left": {"character": me, "glb": "cast-left.glb", "true_size": True},
                         "right": {"character": opposite, "glb": "cast-right.glb", "true_size": True}}})
    write_json(os.path.join(bout, "take.json"), {"name": cast.take_id(role, candidate, take["n"]) + "/fight", "title": "A sparring bout with %s" % chem.get("opposite_name", "Lincoln"),
               "about": "The fight kit's first bout, the one Roosevelt and Lincoln had, with the candidate in Roosevelt's corner. Friendly, as theirs was: it ends with the candidate on the mat and Lincoln's fists up."})


def judge(cast, role, candidate, n=None, take_dir=None, only=None, tag="take", again=False):
    """The renderer's judges on one of a take's cast: what shows at the joints (seams), how a bent joint reads
    (joints), and the face, when there is a face recipe for it (scripts/impostor/faces/). Sums them up into
    casting/<role>/candidates/<candidate>/scores-<n>.json, or returns the sums (for the baseline)."""
    chem = cast.role(role).get("chemistry") or {}
    only = only or chem.get("swap", "right")
    if take_dir is None:
        take = pick_take(cast.candidate(role, candidate), n)
        if not take:
            raise ValueError("no take to judge")
        take_dir, take_name = cast.take_dir(role, candidate, take["n"]), cast.take_id(role, candidate, take["n"])
        if not os.path.isfile(os.path.join(take_dir, "cast-crew.json")):
            raise ValueError("tape it first: there is no chemistry take to judge it in")
        run = take["run"]
    else:
        take_name = os.path.relpath(take_dir, cast.shots)
        part = read_json(os.path.join(take_dir, next(f for f in sorted(os.listdir(take_dir)) if f.startswith("cast-") and f.endswith(".json"))))["roles"][only]
        run = part["character"].split("/runs/")[1].split("/")[0]
    out = os.path.join(take_dir, "judges")
    os.makedirs(out, exist_ok=True)
    log = os.path.join(out, "judge.log")
    common = ["--runs", cast.runs, "--shots", cast.shots, "--take", take_name, "--tag", tag, "--out", out, "--only", only]
    made = lambda kind: not again and os.path.isfile(os.path.join(out, "%s-%s.json" % (kind, tag)))  # a judge already run is not run again
    how_file = os.path.join(out, "pieces-%s.json" % tag)
    how = (read_json(how_file) if made("seams") else None) or {"pieces": True, "missing": None}
    # The pieces of the real model in each big joint (bake_joints.py) are weighted to the walk's skeleton. A
    # character with loose cloth has cloth bones in its walk that a shot's clip leaves out, and the pieces cannot
    # be posed: then it is judged as cards alone, and the scores say so.
    if not made("seams"):
        open(log, "w").close()  # this judging's lines only: missing_bone() reads it
        try:
            blender("scripts/impostor/judge_seams.py", common + ["--looks", "comic,pixel-both,joe"], log)
        except RuntimeError:
            if not missing_bone(log):
                raise
            how = {"pieces": False, "missing": missing_bone(log)}
            blender("scripts/impostor/judge_seams.py", common + ["--looks", "comic,pixel-both,joe", "--joints", "cards"], log)
        write_json(how_file, how)
    pieces = how["pieces"]
    if not made("joints"):
        blender("scripts/impostor/judge_joints.py", common + ([] if pieces else ["--sheets", "joined"]), log)
    if face_recipe(run) and not made("faces"):
        blender("scripts/impostor/judge_faces.py", common + ([] if pieces else ["--joints", "cards"]), log)
    sums = dict(summed(out, only, tag), role=only, face_recipe=bool(face_recipe(run)), joint_pieces=pieces,
                why=None if pieces else "Judged as cards alone: the pieces in its joints need its cloth bones (%s), which this clip has not got." % how["missing"])
    if candidate:
        write_json(os.path.join(cast.root, role, "candidates", candidate, "scores-%d.json" % take["n"]), sums)
    return sums


def missing_bone(log):
    """The bone a judge last stopped on for want of it in the clip (KeyError: 'cloth_linen_tunic_1_1'), or None."""
    try:
        with open(log) as f:
            found = re.findall(r"KeyError: '([^']+)'", f.read())
    except OSError:
        return None
    return found[-1] if found else None


def face_recipe(run):
    """Whether a run's character has a face recipe: scripts/impostor/faces/<the run's name without its date>.json,
    as pixel_face.recipe_for finds it (that module needs numpy, which this Python may not have)."""
    name = os.path.basename(os.path.normpath(run))
    words = name.split("-")
    while words and (words[0][:1].isdigit() or words[0][:1] == "T" and words[0][1:3].isdigit()):
        words = words[1:]
    return any(os.path.isfile(os.path.join(ROOT, "scripts", "impostor", "faces", slug + ".json")) for slug in ("-".join(words), name))


def baseline(cast, role):
    """The same judges on the cast member the candidate stands in for, in the crew's own take: what to beat."""
    chem = cast.role(role).get("chemistry") or {}
    sums = judge(cast, role, None, take_dir=os.path.join(cast.shots, chem.get("take", "crew-candy-shop")), only=chem.get("swap", "right"), tag="baseline")
    sums["who"] = chem.get("swap_name")
    write_json(os.path.join(cast.root, role, "baseline.json"), sums)
    return sums


# ---------- the command line ----------

def main(argv):
    flag = lambda name, default=None: argv[argv.index(name) + 1] if name in argv else default
    words = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or not argv[i - 1].startswith("--"))]
    cast = Casting(runs=os.path.abspath(flag("--runs", RUNS)), shots=os.path.abspath(flag("--shots", SHOTS)))
    if not words:
        print(__doc__)
        return 1
    what, rest = words[0], words[1:]
    take = int(flag("--take")) if flag("--take") else None
    if what == "status":
        for role in rest or cast.roles():
            s = cast.summary(role)
            print("CASTING %s: %s" % (role, " -> ".join("%s%s %d" % ("*" if st["reached"] else "", st["name"], st["count"]) for st in s["board"]["stages"])))
            for c in s["candidates"]:
                print("  %-12s %-12s %d take(s), %d open note(s)%s" % (c["id"], c["status"], len(c["takes"]), len(c["open_notes"]), " (stand-in)" if c["stand_in"] else ""))
        return 0
    if what == "plan":
        shots = [s for s in (flag("--shots") or "").split(",") if s]
        plan = cast.plan(rest[0], rest[1], rest[2] if len(rest) > 2 else None, more=int(flag("--more", 0)),
                         variations=int(flag("--variations", 1)), shots=shots or None)
        print("PLAN %s (dry run: nothing is started)" % plan["name"])
        print("  what:    %s" % plan["what"])
        print("  costs:   %s" % plan["cost"])
        if plan.get("warning"):
            print("  note:    %s" % plan["warning"])
        print("  run it:  %s" % plan["command"])
        print("RESULT " + json.dumps(plan))
        return 0
    if what == "note":
        print("RESULT " + json.dumps(cast.add_note(rest[0], rest[1], rest[2], flag("--about", "look"), take)))
        return 0
    if what == "shortlist":
        print("RESULT " + json.dumps(cast.shortlist(rest[0], rest[1])))
        return 0
    if what == "add-mesh":
        print("RESULT " + json.dumps(cast.add_mesh(rest[0], rest[1], rest[2])))
        return 0
    if what == "screen-3d":
        print("RESULT " + json.dumps(screen_3d(cast, rest[0], again="--again" in argv)))
        return 0
    if what == "top":  # the screen test's best few, comma-separated, for the mesh screen
        print(",".join(cast.top_shots(rest[0], int(rest[1]) if len(rest) > 1 else MESH_SCREEN_SHOTS)))
        return 0
    if what == "unbuilt":  # of the headshots named, those the mesh screen has not built yet
        built = cast.meshes(rest[0])
        print(",".join(s for s in rest[1].split(",") if s and s not in built))
        return 0
    if what == "status-of":
        print("RESULT " + json.dumps(cast.set_status(rest[0], rest[1], " ".join(rest[2:]))))
        return 0
    if what == "add-take":
        answers = [int(a) for a in (flag("--answers") or "").split(",") if a]
        print("RESULT " + json.dumps({"take": cast.add_take(rest[0], rest[1], rest[2], answers)}))
        return 0
    if what == "retake":
        print("RESULT " + json.dumps({"take": cast.retake(rest[0], rest[1])}))
        return 0
    if what == "has-look-notes":  # exit 0 when a revised take needs paying for
        return 0 if cast.look_notes(rest[0], rest[1]) else 1
    if what == "is-stand-in":  # exit 0 for a candidate already in the cast, which is never rebuilt
        return 0 if cast.candidate(rest[0], rest[1]).get("stand_in") else 1
    if what == "has-free-notes":  # exit 0 when open notes on moves or cards can be answered for free
        c = cast.candidate(rest[0], rest[1])
        return 0 if any(not n.get("answered_by") and n.get("about") in ("moves", "cards") for n in c.get("notes") or []) else 1
    if what == "add-look":
        print("RESULT " + json.dumps({"look": cast.add_look(rest[0], json.loads(rest[1]))}))
        return 0
    if what == "tape":
        print("RESULT " + json.dumps(tape(cast, rest[0], rest[1], take)))
        return 0
    if what == "judge":
        print("RESULT " + json.dumps(judge(cast, rest[0], rest[1], take, again="--again" in argv)))
        return 0
    if what == "baseline":
        print("RESULT " + json.dumps(baseline(cast, rest[0])))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except ValueError as refused:  # a name, a note or a step that does not fit: said plainly, not as a traceback
        print("casting: %s" % refused, file=sys.stderr)
        sys.exit(2)
