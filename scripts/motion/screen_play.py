"""Plays the screen-test motions on a character, and lines up everyone who has played them for the watch page.

    python3 scripts/motion/screen_play.py <run> [motion id ...] [--versions lowpoly,midpoly]
        [--library motion/library] [--runs runs] [--shots shots] [--set grass|studio] [--again]

<run> is a run folder, or its name in runs/, or a word of it ("lincoln") that
names one run only. With no motion ids, every motion the library has made.

1. The motions go onto the character's low-poly and mid-poly versions in one
   background Blender (apply_library.py): runs/<run>/profiles/<version>-screen-<id>.glb
   and .json, beside its walk and its run. A motion already played from the
   same take is not played again (--again plays it anyway). The cards play the
   low-poly files, as they play the walk; the gallery's cards page lists them.
2. For each motion, a take everyone who has played it stands in, in a row on
   the grassy field (Theodore's grass), centred on the boxing circle and facing
   its ringside camera, 1.3 m apart, each at their own size:
   shots/screen-<id>/cast-screen.json and take.json. A longer row still has to
   fit in the ringside camera's picture; when it no longer does, the row faces
   the wide camera instead, and past that it closes up. The watch page plays it
   at #/watch/screen-<id>, as cards or as meshes, so the cast can be compared
   doing the same thing. --set studio stands them across the studio stage
   instead, facing its crew camera: the renderer's judges look through a set's
   crew camera, which the grass has not got, so judge a copy made that way
   (--set studio --shots <a folder of your own>).

3. Every motion made, played one after another as one looping clip
   (profiles/<version>-screen-all.glb, each eased into the next), and its
   line-up, shots/screen-all/: #/watch/screen-all cycles through them all,
   names the one playing, and can loop any one alone.

The casting reel names the same files (casting/reel.json, clip kind
"library"), and its tape plays any a candidate is missing. Free: no RunPod.
Plain Python; Blender only through a background process. Never touches an
open Blender.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
LIBRARY = os.path.join(REPO, "motion", "library")
RUNS = os.path.join(REPO, "runs")
SHOTS = os.path.join(REPO, "shots")
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
VERSION_FILES = {"lowpoly": "lowpoly.glb", "midpoly": os.path.join("profiles", "midpoly.glb"), "painted": os.path.join("profiles", "painted.glb")}
# Where the line-up stands: the set, the mark the row is centred on, and its cameras, the one to fit the row in first.
LINEUPS = {
    "grass": {"mark": "circle", "cameras": ["ringside", "wide"]},  # the default: the grassy field's boxing circle
    "studio": {"mark": "centre", "cameras": ["crew", "wide"]},     # with the crew camera the judges look through
}
LINEUP_SET = "grass"
LINEUP_APART_M = 1.3  # between two people in the row
LINEUP_CLOSEST_M = 0.8  # a row too long for any camera closes up to this, and no further
PERSON_HALF_M, PERSON_TALL_M = 0.45, 1.95  # how much room each one needs in the picture, either side and up
SENSOR_W_MM, ASPECT = 36.0, 16.0 / 9.0  # the cameras' film back and picture shape (as the gallery and the judges take them)


def sees(camera: dict, point: tuple, margin: float = 0.92) -> bool:
    """Whether a point of the set lies inside the camera's picture (with a little room to spare at the edges)."""
    at, aim = camera["at"], camera["aim"]
    f = [aim[k] - at[k] for k in range(3)]
    n = sum(c * c for c in f) ** 0.5
    f = [c / n for c in f]
    r = [f[1] * 0 - f[2] * 1, f[2] * 0 - f[0] * 0, f[0] * 1 - f[1] * 0]  # f x up
    rn = sum(c * c for c in r) ** 0.5
    r = [c / rn for c in r]
    u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]]
    d = [point[k] - at[k] for k in range(3)]
    depth = sum(a * b for a, b in zip(d, f))
    if depth <= 0.1:
        return False
    half_w = SENSOR_W_MM / 2.0 / camera["lens_mm"]
    x = sum(a * b for a, b in zip(d, r)) / depth
    y = sum(a * b for a, b in zip(d, u)) / depth
    return abs(x) <= margin * half_w and abs(y) <= margin * half_w / ASPECT


def lineup(count: int, set_name: str = LINEUP_SET) -> dict:
    """Where `count` people stand in a row on the set: {"spots": [[x, z]...], "facing_deg", "cameras", "apart_m"}.

    The row is centred on the set's mark and square to the line from the mark to a camera, everyone facing that
    camera. The first camera whose picture holds the whole row (each person's feet and head, and half a metre either
    side) is used; when none does at 1.3 m apart, the row faces the last camera and closes up until it fits."""
    import math

    card = read_json(os.path.join(REPO, "sets", set_name, "set.json")) or {}
    plan = LINEUPS[set_name]
    mx, mz = card["marks"][plan["mark"]]["at"]
    cameras = [c for c in plan["cameras"] if c in card.get("cameras", {})]

    def row(camera, apart):
        cam = card["cameras"][camera]["at"]
        facing = math.degrees(math.atan2(cam[0] - mx, cam[2] - mz))
        h = math.radians(facing)
        across = (math.cos(h), -math.sin(h))  # square to the way they face
        spots = [[round(mx + across[0] * (k - (count - 1) / 2.0) * apart, 3), round(mz + across[1] * (k - (count - 1) / 2.0) * apart, 3)] for k in range(count)]
        fits = all(sees(card["cameras"][camera], (x + across[0] * side, y, z + across[1] * side))
                   for x, z in spots for side in (-PERSON_HALF_M, PERSON_HALF_M) for y in (0.0, PERSON_TALL_M))
        return {"spots": spots, "facing_deg": round(facing, 1), "cameras": [camera] + [c for c in cameras if c != camera], "apart_m": apart, "fits": fits}

    for camera in cameras:
        found = row(camera, LINEUP_APART_M)
        if found["fits"]:
            return found
    apart = LINEUP_APART_M
    while apart > LINEUP_CLOSEST_M:
        apart = round(apart - 0.05, 2)
        found = row(cameras[-1], apart)
        if found["fits"]:
            return found
    return found


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".partial", "w") as f:
        json.dump(value, f, indent=1)
    os.replace(path + ".partial", path)


def find_run(word: str, runs: str = RUNS) -> str:
    """A run folder from a path, a folder name in runs/, or one word of a name that only one run has."""
    for path in (word, os.path.join(runs, word)):
        if os.path.isdir(path):
            return os.path.abspath(path.rstrip("/"))
    found = [f for f in sorted(os.listdir(runs)) if word.lower() in f.lower() and os.path.isdir(os.path.join(runs, f))] if os.path.isdir(runs) else []
    if len(found) != 1:
        raise ValueError("%s names %s" % (word, "no run" if not found else "%d runs: %s" % (len(found), ", ".join(found))))
    return os.path.join(runs, found[0])


def made(library: str) -> dict:
    """{id: the kept motion's ask and take} for every motion the library has made from its sentence as it now stands
    (one kept from an older sentence is waiting to be made again, and is not played)."""
    sys.path.insert(0, HERE)
    import screen_motions

    lib = read_json(os.path.join(library, "library.json")) or {}
    listed = lib.get("motions") or []
    out = {}
    for m in listed:
        kept = read_json(os.path.join(library, m["id"], "motion.json"))
        if m.get("mirror_of"):
            source = read_json(os.path.join(library, m["mirror_of"], "motion.json")) or {}
            current = bool(source) and kept and kept.get("ask") == screen_motions.mirror_ask(source.get("ask", "") + ":%s" % source.get("take"))
        else:
            current = kept and kept.get("ask") == screen_motions.ask_for(m, lib.get("takes") or screen_motions.TAKES)["hash"]
        if current and kept.get("ask") and (not m.get("mirror_of") or m["mirror_of"] in out):
            out[m["id"]] = {"ask": kept["ask"], "take": kept.get("take"), "name": m["name"], "frames": len(kept["root"]), "prompt": kept.get("prompt")}
    return out


def missing(run: str, ids: list, versions: list, library: str = LIBRARY) -> list:
    """The motions this run has not played from the library's kept take, on any version it has."""
    have = made(library)
    out = []
    for mid in ids:
        if mid not in have:
            continue
        for version in versions:
            if not os.path.isfile(os.path.join(run, VERSION_FILES[version])):
                continue
            record = read_json(os.path.join(run, "profiles", "%s-screen-%s.json" % (version, mid))) or {}
            if not os.path.isfile(os.path.join(run, "profiles", "%s-screen-%s.glb" % (version, mid))) or [(record.get("screen") or {}).get(k) for k in ("ask", "take")] != [have[mid]["ask"], have[mid]["take"]]:
                out.append(mid)
                break
    return out


def joined_ask(library: str = LIBRARY):
    """The fingerprint of every made motion played in turn (screen_motions.joined), or None when none is made."""
    sys.path.insert(0, HERE)
    import screen_motions

    kept = screen_motions.made_motions(library)
    return screen_motions.digest([{"id": mid, "ask": m.get("ask"), "take": m.get("take")} for mid, _, m in kept] + [screen_motions.JOIN_FRAMES]) if kept else None


def missing_joined(run: str, versions: list, library: str = LIBRARY) -> bool:
    """Whether the run's clip of every motion in turn is missing or older than the motions it is made of."""
    want = joined_ask(library)
    for version in versions:
        if not want or not os.path.isfile(os.path.join(run, VERSION_FILES[version])):
            continue
        record = read_json(os.path.join(run, "profiles", "%s-screen-all.json" % version)) or {}
        if (record.get("screen") or {}).get("ask") != want:
            return True
    return False


def play(run: str, ids: list, versions: list, library: str = LIBRARY, log: str = None, joined: bool = False) -> None:
    """One background Blender plays them all on this run's versions (or, joined, all of them in turn as one clip)."""
    command = [BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P", os.path.join(HERE, "apply_library.py"), "--",
               run, "--motions", ",".join(ids), "--versions", ",".join(versions), "--library", library] + (["--joined"] if joined else [])
    done = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=REPO)
    if log:
        with open(log, "a") as f:
            f.write(done.stdout)
    for line in done.stdout.splitlines():
        if line.startswith("SCREEN") or "Error" in line or "Traceback" in line:
            print(line, flush=True)
    if done.returncode:
        raise RuntimeError("apply_library.py failed on %s" % os.path.basename(run))


def role_name(run_folder: str) -> str:
    """'2026-11-20T14-02-41-young-lincoln-frontier-wrestler' -> 'young-lincoln-frontier-wrestler'."""
    return re.sub(r"^\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d-", "", run_folder)


def cards_play(run: str) -> str:
    """The version whose skeleton a run's cards ride (impostor.json's `plays`): its detailed cards' if it has them,
    else any; lowpoly if it has none. The flamenco dancer's detailed cards ride her mid-poly skeleton."""
    found = {}
    profiles = os.path.join(run, "profiles")
    for name in sorted(os.listdir(profiles)) if os.path.isdir(profiles) else []:
        card = read_json(os.path.join(profiles, name, "impostor.json")) if "-impostor" in name else None
        if card and card.get("plays"):
            found.setdefault(card.get("profile") or name.split("-impostor")[0], card["plays"])
    return found.get("detailed") or next(iter(found.values()), "lowpoly")


def lineups(ids: list, runs: str = RUNS, shots: str = SHOTS, library: str = LIBRARY, set_name: str = LINEUP_SET) -> list:
    """For each motion, a take with everyone who has played it, side by side on the stage (shots/screen-<id>/). Each
    stands in the version their cards ride, so the watch page can draw them as cards and the judges can judge them."""
    have = dict(made(library))
    want = joined_ask(library)
    if want:  # every motion in turn: named "all", its chapters in its record
        have["all"] = {"name": "Every screen test, in turn", "prompt": None}
    out = []
    for mid in ids + (["all"] if want else []):
        players = [f for f in sorted(os.listdir(runs)) if os.path.isfile(os.path.join(runs, f, "profiles", "lowpoly-screen-%s.glb" % mid))] if os.path.isdir(runs) else []
        if mid == "all":  # only those whose clip is of the motions as they now are
            players = [f for f in players if ((read_json(os.path.join(runs, f, "profiles", "lowpoly-screen-all.json")) or {}).get("screen") or {}).get("ask") == want]
        if not players or mid not in have:
            continue
        folder = os.path.join(shots, "screen-" + mid)
        roles, marks = {}, {}
        row = lineup(len(players), set_name)
        for k, run in enumerate(players):
            name = role_name(run)
            version = cards_play(os.path.join(runs, run))
            glb = os.path.join(runs, run, "profiles", "%s-screen-%s.glb" % (version, mid))
            if not os.path.isfile(glb):
                version, glb = "lowpoly", os.path.join(runs, run, "profiles", "lowpoly-screen-%s.glb" % mid)
            record = read_json(glb[:-4] + ".json") or {}
            roles[name] = {"character": os.path.join(runs, run, "lowpoly.glb" if version == "lowpoly" else os.path.join("profiles", version + ".glb")),
                           "glb": os.path.relpath(glb, folder), "true_size": True,
                           "size_against_soma": record.get("size_against_soma"), "clamped": (record.get("animation") or {}).get("clamped")}
            marks[name] = {"at": row["spots"][k], "facing_deg": row["facing_deg"]}
        chapters = None
        if mid == "all":
            screen = (read_json(os.path.join(runs, players[0], "profiles", "lowpoly-screen-all.json")) or {}).get("screen") or {}
            chapters = [{"id": c["id"], "name": c["name"], "from_s": c["from_s"], "to_s": c["to_s"]} for c in screen.get("chapters") or []]
            frames = int(round(float(screen.get("seconds") or 0) * 30))
        else:
            frames = have[mid]["frames"]
        write_json(os.path.join(folder, "cast-screen.json"), {"set": set_name, "clip": "screen", "version": "lowpoly", "frames": frames, "seconds": round(frames / 30.0, 2),
                                                               "cameras": row["cameras"], "films": {}, "handshakes": [], "roles": roles, "marks": marks, "motion": mid,
                                                               "row": {"apart_m": row["apart_m"], "fits": row["fits"]}, **({"chapters": chapters} if chapters else {})})
        names = [(read_json(os.path.join(runs, r, "brief.json")) or {}).get("name") or role_name(r) for r in players]
        together = ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]
        write_json(os.path.join(folder, "take.json"), {
            "name": "screen-" + mid, "title": "%s, side by side" % have[mid]["name"] if mid != "all" else "Screen tests, side by side",
            "about": ("A screen test: %s, each at their own size, doing the same motion made once from one sentence (\"%s\"). Made by `just screen-play`." % (together, have[mid]["prompt"]))
            if mid != "all" else "Screen tests: %s, each at their own size, doing every move in the library one after another, round and round. Pick one to watch it alone." % together})
        out.append(folder)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run")
    parser.add_argument("motions", nargs="*")
    parser.add_argument("--versions", default="lowpoly,midpoly")
    parser.add_argument("--library", default=LIBRARY)
    parser.add_argument("--runs", default=RUNS)
    parser.add_argument("--shots", default=SHOTS)
    parser.add_argument("--again", action="store_true", help="play them again even where they are up to date")
    parser.add_argument("--set", default=LINEUP_SET, choices=sorted(LINEUPS), help="where the line-ups stand (default: the grassy field)")
    args = parser.parse_args(argv)
    library, runs, shots = (os.path.abspath(p) for p in (args.library, args.runs, args.shots))
    try:
        run = find_run(args.run, runs)
        have = made(library)
        ids = args.motions or list(have)
        unknown = [m for m in ids if m not in {x["id"] for x in (read_json(os.path.join(library, "library.json")) or {}).get("motions") or []}]
        if unknown:
            raise ValueError("no such motion in the library: %s" % ", ".join(unknown))
    except ValueError as refused:
        print("screen-play: %s" % refused, file=sys.stderr)
        return 2
    if not have:
        print("SCREEN nothing to play: the library has no motions made yet (just screen-motions, then go)")
        return 0
    not_made = [m for m in ids if m not in have]
    if not_made:
        print("SCREEN not made yet, skipped: %s" % ", ".join(not_made))
    versions = args.versions.split(",")
    todo = [m for m in ids if m in have] if args.again else missing(run, ids, versions, library)
    if todo:
        print("SCREEN playing %d motion(s) on %s (%s): %s" % (len(todo), os.path.basename(run), ", ".join(versions), ", ".join(todo)), flush=True)
        play(run, todo, versions, library, log=os.path.join(run, "profiles", "screen-play.log"))
    else:
        print("SCREEN %s has played every motion asked for already" % os.path.basename(run))
    if missing_joined(run, versions, library) or args.again:
        print("SCREEN playing every motion in turn, as one clip, on %s" % os.path.basename(run), flush=True)
        play(run, [m for m in have], versions, library, log=os.path.join(run, "profiles", "screen-play.log"), joined=True)
    for folder in lineups([m for m in ids if m in have], runs, shots, library, args.set):
        cast = read_json(os.path.join(folder, "cast-screen.json"))
        print("SCREEN watch #/watch/%s: %s%s" % (os.path.basename(folder), ", ".join(cast["roles"]), " (every motion in turn)" if cast.get("chapters") else ""))
    print("SCREEN cards: #/cards/%s plays them as cards (once it has cards: just impostor-detailed)" % os.path.basename(run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
