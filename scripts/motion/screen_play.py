"""Plays the screen-test motions on a character, and lines up everyone who has played them for the watch page.

    python3 scripts/motion/screen_play.py <run> [motion id ...] [--versions lowpoly,midpoly]
        [--library motion/library] [--runs runs] [--shots shots] [--again]

<run> is a run folder, or its name in runs/, or a word of it ("lincoln") that
names one run only. With no motion ids, every motion the library has made.

1. The motions go onto the character's low-poly and mid-poly versions in one
   background Blender (apply_library.py): runs/<run>/profiles/<version>-screen-<id>.glb
   and .json, beside its walk and its run. A motion already played from the
   same take is not played again (--again plays it anyway). The cards play the
   low-poly files, as they play the walk; the gallery's cards page lists them.
2. For each motion, a take everyone who has played it stands in, side by side
   across the middle of the studio stage facing the house, each at their own
   size: shots/screen-<id>/cast-screen.json and take.json. The watch page plays
   it at #/watch/screen-<id>, as cards or as meshes, so the cast can be
   compared doing the same thing.

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
# The line-up: across the middle of the studio stage (its `centre` mark), facing the house and the crew camera.
LINEUP_SET, LINEUP_MIDDLE, LINEUP_APART_M, LINEUP_FACING = "studio", (-0.4, 2.75), 1.3, 0.0


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


def play(run: str, ids: list, versions: list, library: str = LIBRARY, log: str = None) -> None:
    """One background Blender plays them all on this run's versions."""
    command = [BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P", os.path.join(HERE, "apply_library.py"), "--",
               run, "--motions", ",".join(ids), "--versions", ",".join(versions), "--library", library]
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


def lineups(ids: list, runs: str = RUNS, shots: str = SHOTS, library: str = LIBRARY) -> list:
    """For each motion, a take with everyone who has played it, side by side on the stage (shots/screen-<id>/). Each
    stands in the version their cards ride, so the watch page can draw them as cards and the judges can judge them."""
    have = made(library)
    out = []
    for mid in ids:
        players = [f for f in sorted(os.listdir(runs)) if os.path.isfile(os.path.join(runs, f, "profiles", "lowpoly-screen-%s.glb" % mid))] if os.path.isdir(runs) else []
        if not players or mid not in have:
            continue
        folder = os.path.join(shots, "screen-" + mid)
        roles, marks = {}, {}
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
            x = LINEUP_MIDDLE[0] + (k - (len(players) - 1) / 2.0) * LINEUP_APART_M
            marks[name] = {"at": [round(x, 3), LINEUP_MIDDLE[1]], "facing_deg": LINEUP_FACING}
        frames = have[mid]["frames"]
        write_json(os.path.join(folder, "cast-screen.json"), {"set": LINEUP_SET, "clip": "screen", "version": "lowpoly", "frames": frames, "seconds": round(frames / 30.0, 2),
                                                               "cameras": [], "films": {}, "handshakes": [], "roles": roles, "marks": marks, "motion": mid})
        names = [(read_json(os.path.join(runs, r, "brief.json")) or {}).get("name") or role_name(r) for r in players]
        write_json(os.path.join(folder, "take.json"), {
            "name": "screen-" + mid, "title": "%s, side by side" % have[mid]["name"],
            "about": "A screen test: %s, each at their own size, doing the same motion made once from one sentence (\"%s\"). Made by `just screen-play`." % (
                ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0], have[mid]["prompt"])})
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
    for folder in lineups([m for m in ids if m in have], runs, shots, library):
        cast = read_json(os.path.join(folder, "cast-screen.json"))
        print("SCREEN watch #/watch/%s: %s" % (os.path.basename(folder), ", ".join(cast["roles"])))
    print("SCREEN cards: #/cards/%s plays them as cards (once it has cards: just impostor-detailed)" % os.path.basename(run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
