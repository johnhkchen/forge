"""A clip in, motion for our characters out: does whatever step comes next, and stops where it needs you.

    python3 scripts/video/video.py <name> [--again <step>] [--also 1:2,1:3] [--shots DIR]

The steps, in order. Each keeps what it made in videos/<name>/, and a step
whose file is already there is skipped, so running this again carries on.

  ready    clip.mp4: the stretch you asked for, 30 pictures a second  (this Mac)
  cuts     shots.json: where the camera cuts                          (this Mac)
  people   people.json: who is in each shot, followed through it      (RunPod)
           -- stops here until you have chosen: the gallery's page for the
              clip (#/video/<name>) shows every shot with a numbered box on
              each person; tap who to follow, or skip the shot, and save --
  motion   motion/shot-NNN.json: that person's motion, shot by shot   (RunPod)
  shot     shots/video-<name>/: the shots joined into one motion our
           characters can play, measured by checks.py                 (this Mac)
  film     videos/<name>/side-by-side.mp4: the mannequin doing it,
           next to the clip, in step                                  (this Mac)

The two RunPod steps use your GPU endpoint (GEMX_ENDPOINT_ID in .env) and cost
what it costs while it runs; the clip is sent to it once. Nothing else leaves
this Mac. A motion already made for a shot is kept: choose someone else in one
shot and only that shot is made again.

--again <step> forgets that step and everything after it first (ready, cuts,
people, choice, motion, shot, film).

--also 1:2 makes one more motion: person 2 of shot 1, beside whoever was
chosen there (motion/shot-000-person-2.json). The shot and the film still
follow your choice; the extra motion is for a shot list that asks for that
person by number (a beat with "source": "video", see scripts/video/beat.py),
so three dancers in a clip can become three characters.

After it: `just cast video-<name> runs/<character>` puts a character in it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import clip as clip_file  # noqa: E402
import endpoint as endpoint_file  # noqa: E402
import film as film_file  # noqa: E402
import people as people_file  # noqa: E402
import soma77  # noqa: E402

SHOTS = os.path.join(REPO, "shots")


def shot_dir_of(name: str, shots: str = None) -> str:
    return os.path.join(shots or SHOTS, f"video-{name}")


def motion_request(clip_sha: str, shot: dict, who: int, camera: str) -> dict:
    """What the worker is asked for one shot: the clip, the frames, and the chosen person's box on every one of them."""
    person = next(p for p in shot["people"] if p["id"] == who)
    return {"kind": "motion", "clip": clip_sha, "first": shot["first_frame"], "last": shot["last_frame"], "boxes": person["boxes"], "camera": people_file.CAMERAS[camera], "postprocess": True}


def digest(request: dict) -> str:
    return hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]


def wanted(folder: str, choice: dict) -> list:
    """[(shot, request, digest)] for every shot with someone to follow."""
    card, raw = clip_file.read(os.path.join(folder, "clip.json")), clip_file.read(os.path.join(folder, "people-raw.json"))
    out = []
    for shot in raw["shots"]:
        who = choice["shots"][str(shot["index"])]
        if who != "skip":
            request = motion_request(card["clip"]["sha256"], shot, who, choice["camera"])
            out.append((shot, request, digest(request)))
    return out


def advance(name: str, videos: str = None, shots: str = None, connect=None, log=print, film: bool = True, also=()) -> dict:
    """Does every step that can be done now. Returns {"done": [...], "waiting_for": None | "choice"}.
    `film=False` stops before the film (the one step that needs Blender)."""
    folder = clip_file.folder_of(name, videos)
    if not os.path.exists(os.path.join(folder, "source.mp4")):
        raise clip_file.Stop(f"there is no clip called {name}: add one with `just video-add <file> {name}`")
    connect = connect or (lambda: endpoint_file.Endpoint.from_env(log))
    shot_dir = shot_dir_of(name, shots)
    done = []
    has = lambda f: os.path.exists(os.path.join(folder, f))  # noqa: E731

    if not has("clip.mp4"):
        card = clip_file.ready(folder)
        log(f"video: the clip is ready, {card['clip']['seconds']} seconds at {card['clip']['width']}x{card['clip']['height']}")
        done.append("ready")
    card = clip_file.read(os.path.join(folder, "clip.json"))

    if not has("shots.json"):
        record = clip_file.cuts(folder)
        log(f"video: {len(record['shots'])} shots" + (f", cut at {', '.join(f'{f / clip_file.FPS:.1f} s' for f in record['cuts'])}" if record["cuts"] else " (no cuts found)"))
        done.append("cuts")
    shots_record = clip_file.read(os.path.join(folder, "shots.json"))
    if shots_record.get("by_hand"):
        shots_record = clip_file.cuts(folder)  # cuts fixed by hand: the shots between them, worked out again
    spans = [[s["first_frame"], s["last_frame"]] for s in shots_record["shots"]]
    found = clip_file.read(os.path.join(folder, "people-raw.json"))
    if found and [[s["first_frame"], s["last_frame"]] for s in found["shots"]] != spans:
        raise clip_file.Stop(f"the cuts have changed since the people were found: run `just video {name} people` to find them again")

    if not has("people.json"):
        worker = connect()
        log(f"video: finding the people in {card['clip']['seconds']} seconds of clip on the GPU worker")
        sent = endpoint_file.upload(worker, os.path.join(folder, "clip.mp4"), card["clip"]["sha256"])
        clip_file.write(os.path.join(folder, "upload.json"), sent)
        answer, record = worker.call({"kind": "people", "clip": card["clip"]["sha256"], "shots": spans})
        page = people_file.digest(answer, folder)
        clip_file.write(os.path.join(folder, "people.record.json"), record)
        for shot in page["shots"]:
            log(f"video: shot {shot['index'] + 1} ({shot['seconds']} s): {len(shot['people'])} people" + "".join(f"; {p['id']} might be a reflection of {p['reflection_of']}" for p in shot["people"] if p["reflection_of"]))
        done.append("people")

    choice = people_file.load_choice(folder)
    if not choice:
        if has("choice.json"):
            log("video: the saved choice no longer fits the people found; choose again")
        return {"done": done, "waiting_for": "choice", "folder": folder}

    os.makedirs(os.path.join(folder, "motion"), exist_ok=True)
    todo = []
    for shot, request, key in wanted(folder, choice):
        base = os.path.join(folder, "motion", f"shot-{shot['index']:03d}")
        if (clip_file.read(base + ".record.json") or {}).get("request") != key or not os.path.exists(base + ".json"):
            todo.append((shot, request, key, base))
    # Others asked for by number (--also): the same job for another person of a shot, kept beside the chosen one's.
    raw = clip_file.read(os.path.join(folder, "people-raw.json"))
    for number, who in also:
        shot = next((s for s in raw["shots"] if s["index"] == number - 1), None)
        if shot is None or not any(p["id"] == who for p in shot["people"]):
            raise clip_file.Stop(f"--also {number}:{who}: there is no person {who} in shot {number} (shots are counted from 1, people as numbered on the clip's page)")
        request = motion_request(card["clip"]["sha256"], shot, who, choice["camera"])
        base = os.path.join(folder, "motion", f"shot-{shot['index']:03d}-person-{who}")
        if (clip_file.read(base + ".record.json") or {}).get("request") != digest(request) or not os.path.exists(base + ".json"):
            todo.append((shot, request, digest(request), base))
    if todo:
        worker = connect()
        endpoint_file.upload(worker, os.path.join(folder, "clip.mp4"), card["clip"]["sha256"])  # in case the volume forgot it
        for shot, request, key, base in todo:
            who = next(p["id"] for p in shot["people"] if p["boxes"] == request["boxes"])
            log(f"video: making the motion for shot {shot['index'] + 1}, person {who} ({(shot['last_frame'] - shot['first_frame'] + 1) / clip_file.FPS:.1f} s) on the GPU worker")
            answer, record = worker.call(request)
            clip_file.write(base + ".json", answer, indent=None)
            clip_file.write(base + ".record.json", {**record, "request": key, "person": who})
        done.append("motion")

    keys = sorted(key for _, _, key in wanted(folder, choice))
    source = clip_file.read(os.path.join(shot_dir, "source.json")) or {}
    if source.get("motion_requests") != keys or not os.path.exists(os.path.join(shot_dir, "checks.json")):
        source = soma77.build(folder, shot_dir)
        source["motion_requests"] = keys
        clip_file.write(os.path.join(shot_dir, "source.json"), source)
        for label, report in source["converted"].items():
            apart = max((v["typical"] for v in report["ours_vs_gemx_cm"].values()), default=0.0)
            log(f"video: {label}: {report['frames']} frames; our body sits {apart} cm from GEM-X's at the hands, toes and head, typically")
        checked = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "motion", "checks.py"), shot_dir], capture_output=True, text=True)
        if checked.returncode != 0:
            raise clip_file.Stop(f"checks.py could not measure the shot: {(checked.stderr or checked.stdout).strip()[-600:]}")
        for line in checked.stdout.splitlines():
            if line.startswith(("CHECK frames", "CHECK feet", "CHECK floor", "CHECK seam")):
                log("video: " + line[6:])
        done.append("shot")

    if not film:
        return {"done": done, "waiting_for": None, "folder": folder, "shot": shot_dir, "film": None}
    made = film_file.film(folder, shot_dir, log=log)
    if not made.get("already_there"):
        done.append("film")
    return {"done": done, "waiting_for": None, "folder": folder, "shot": shot_dir, "film": os.path.join(folder, made["film"])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name")
    parser.add_argument("--again", default="", help="forget this step and everything after it first: " + ", ".join(clip_file.STEPS))
    parser.add_argument("--also", default="", help="more people to make the motion for, as shot:person, with commas (1:2,1:3)")
    parser.add_argument("--shots", default="", help="the folder of shots (default: shots/)")
    parser.add_argument("--port", default="8028", help="the gallery's port, for the address to open")
    args = parser.parse_args()
    log = lambda line: print(line, flush=True)  # noqa: E731
    try:
        folder = clip_file.folder_of(args.name)
        shot_dir = shot_dir_of(args.name, args.shots or None)
        if args.again:
            if args.again not in clip_file.STEPS:
                raise clip_file.Stop(f"--again takes one of: {', '.join(clip_file.STEPS)}")
            gone = clip_file.forget(folder, args.again)
            if clip_file.STEPS.index(args.again) <= clip_file.STEPS.index("shot") and os.path.isdir(shot_dir):
                shutil.rmtree(shot_dir)
                gone.append(os.path.relpath(shot_dir, REPO))
            for name in os.listdir(folder) if os.path.isdir(folder) else []:
                if name.startswith("side-by-side"):
                    os.remove(os.path.join(folder, name))
            log(f"video: starting again from {args.again}" + (f" (forgot {', '.join(gone)})" if gone else ""))
        try:
            also = [tuple(int(v) for v in pair.split(":")) for pair in args.also.split(",") if pair.strip()]
            assert all(len(pair) == 2 for pair in also)
        except (ValueError, AssertionError):
            raise clip_file.Stop("--also takes shot:person pairs, like 1:2 or 1:2,1:3")
        result = advance(args.name, shots=args.shots or None, log=log, also=also)
    except (clip_file.Stop, endpoint_file.WorkerFailed) as stop:
        print(f"VIDEO stopped: {stop}")
        sys.exit(1)
    if result["waiting_for"] == "choice":
        print(f"VIDEO {args.name}: your turn. Start the gallery (`just gallery`), open #/video/{args.name}  (http://localhost:{args.port}/#/video/{args.name}, or the same on your phone),")
        print(f"VIDEO   tap who to follow in each shot, save, then run `just video {args.name}` again.")
        return
    print(f"VIDEO {args.name}: done. Watch {os.path.relpath(result['film'], REPO)} (or the gallery's #/video/{args.name}).")
    print(f"VIDEO   Put a character in it: just cast video-{args.name} runs/<character>")


if __name__ == "__main__":
    main()
