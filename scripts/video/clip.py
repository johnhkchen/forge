"""A clip you bring: kept in videos/<name>/, made ready, and cut into its shots. All on this Mac, with ffmpeg.

    python3 scripts/video/clip.py add <file> [name] [--start S] [--end S]
    python3 scripts/video/clip.py ready <name>      # clip.mp4
    python3 scripts/video/clip.py cuts <name>       # shots.json

add     copies the file to videos/<name>/source.mp4 (the file itself is left
        alone) and notes the stretch you want, in seconds. Nothing is
        downloaded: you bring the file.
ready   makes clip.mp4 from that stretch: 30 pictures a second (what the
        motion model works at), at most 960 pixels on its long side, sound
        kept. Every later step counts frames of this file.
cuts    finds where the camera cuts. ffmpeg scores how much each picture
        differs from the one before; a jump is a cut. shots.json lists the
        shots between them, by first and last frame. A fade or a dissolve has
        no single jump and can be missed or found twice; you can fix
        shots.json by hand (`cuts`: the first frame of every shot after the
        first) and run `just video <name>` again.

videos/ is not in git: the clips are other people's work and stay here.

Plain Python and ffmpeg: nothing else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
VIDEOS = os.environ.get("FORGE_VIDEOS") or os.path.join(REPO, "videos")
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = os.environ.get("FFPROBE") or shutil.which("ffprobe") or os.path.join(os.path.dirname(FFMPEG), "ffprobe")

FPS = 30
LONG_SIDE = 960
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
CUT_SCORE = 0.30  # ffmpeg's scene score (0..1) above which a picture starts a new shot
SHORTEST_SHOT = 12  # frames; a "shot" shorter than this is a flash or a fade, and joins the shot before it
LONGEST_SHOT = 60 * FPS  # the motion model takes a minute at most; a longer shot is split


class Stop(Exception):
    """Something a person has to see to; the message says what, in plain words."""


def slug(text: str) -> str:
    """'My Dance (final).mp4' -> 'my-dance-final'."""
    return "-".join("".join(c if c.isascii() and c.isalnum() else " " for c in os.path.splitext(text)[0].lower()).split())[:64]


def folder_of(name: str, videos: str = None) -> str:
    if not NAME.match(name or ""):
        raise Stop(f"a clip's name is lower-case letters, numbers and dashes, like summer-dance: not {name!r}")
    return os.path.join(videos or VIDEOS, name)


def run(*args: str) -> subprocess.CompletedProcess:
    try:
        done = subprocess.run(args, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise Stop(f"{args[0]} is not installed (ffmpeg does the cutting and the filming)") from error
    if done.returncode != 0:
        raise Stop(f"{os.path.basename(args[0])} failed: {(done.stderr or done.stdout).strip()[-800:]}")
    return done


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read(path: str):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write(path: str, value, indent=1) -> None:
    """Writes JSON whole or not at all."""
    with open(path + ".partial", "w") as f:
        json.dump(value, f, indent=indent)
    os.replace(path + ".partial", path)


def probe(path: str) -> dict:
    """What a video file is: its size, speed, length, and whether it has sound."""
    out = run(FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,width,height,avg_frame_rate,nb_frames:format=duration", "-of", "json", path)
    card = json.loads(out.stdout)
    video = next((s for s in card.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise Stop(f"{os.path.basename(path)} has no picture in it")
    top, _, bottom = (video.get("avg_frame_rate") or "0/1").partition("/")
    fps = float(top) / float(bottom or 1) if float(bottom or 1) else 0.0
    return {
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps": round(fps, 3),
        "seconds": round(float(card.get("format", {}).get("duration") or 0.0), 3),
        "frames": int(video["nb_frames"]) if str(video.get("nb_frames", "")).isdigit() else None,
        "sound": any(s.get("codec_type") == "audio" for s in card.get("streams", [])),
    }


# ---- add -------------------------------------------------------------------------


def add(file: str, name: str = None, start: float = None, end: float = None, videos: str = None) -> str:
    """Copies a video of yours into videos/<name>/source.mp4. Returns the clip's folder."""
    if not os.path.isfile(file):
        raise Stop(f"there is no file at {file}")
    name = name or slug(os.path.basename(file))
    folder = folder_of(name, videos)
    if start is not None and start < 0 or end is not None and end <= (start or 0.0):
        raise Stop("start and end are seconds into the video, and end comes after start")
    about = probe(file)
    if end is not None and about["seconds"] and (start or 0.0) >= about["seconds"]:
        raise Stop(f"the video is {about['seconds']} seconds long; start is past its end")
    os.makedirs(folder, exist_ok=True)
    source = os.path.join(folder, "source.mp4")
    card = read(os.path.join(folder, "clip.json")) or {}
    same = os.path.exists(source) and card.get("source_sha256") == sha256_of(file)
    if os.path.exists(source) and not same:
        raise Stop(f"{folder} already holds another video. Pick another name, or delete that folder to start over")
    if not same:
        if os.path.splitext(file)[1].lower() in (".mp4", ".m4v", ".mov"):
            shutil.copyfile(file, source)
        else:
            # Another container (.webm, .mkv): the same pictures and sound, moved into an .mp4 untouched.
            done = subprocess.run([FFMPEG, "-v", "error", "-y", "-i", file, "-c", "copy", source], capture_output=True, text=True)
            if done.returncode != 0:
                shutil.copyfile(file, source)  # ffmpeg reads a file by what is in it, whatever it is called
    trimmed = card.get("start") != start or card.get("end") != end
    card.update({"name": name, "from_file": os.path.basename(file), "source_sha256": sha256_of(file), "source": about, "start": start, "end": end, "added": card.get("added") or time.strftime("%Y-%m-%d %H:%M")})
    write(os.path.join(folder, "clip.json"), card)
    if trimmed and os.path.exists(os.path.join(folder, "clip.mp4")):
        forget(folder, "ready")  # another stretch of the video: everything after is for the old one
    return folder


# The steps in order, and the files each one makes. Doing a step again forgets everything after it.
STEP_FILES = [
    ("ready", ["clip.mp4"]),
    ("cuts", ["shots.json"]),
    ("people", ["upload.json", "people-raw.json", "people.json", "people"]),
    ("choice", ["choice.json"]),
    ("motion", ["motion"]),
    ("shot", []),
    ("film", []),
]
STEPS = [step for step, _ in STEP_FILES]


def forget(folder: str, step: str) -> list:
    """Deletes what `step` and every step after it made in the clip's folder (the shot folder is the caller's)."""
    gone = []
    for _, files in STEP_FILES[STEPS.index(step) :]:
        for name in files:
            path = os.path.join(folder, name)
            if os.path.isdir(path):
                shutil.rmtree(path)
                gone.append(name)
            elif os.path.exists(path):
                os.remove(path)
                gone.append(name)
    return gone


# ---- ready -----------------------------------------------------------------------


def ready(folder: str) -> dict:
    """source.mp4 (the stretch asked for) as clip.mp4: 30 a second, at most 960 px, even sides. Returns clip.json."""
    card = read(os.path.join(folder, "clip.json")) or {}
    source, clip = os.path.join(folder, "source.mp4"), os.path.join(folder, "clip.mp4")
    if not os.path.exists(source):
        raise Stop(f"{folder} has no source.mp4: add a clip with `just video-add <file>`")
    cut = []
    if card.get("start"):
        cut += ["-ss", f"{float(card['start']):.3f}"]
    if card.get("end"):
        cut += ["-to", f"{float(card['end']):.3f}"]
    shape = f"fps={FPS},scale=w='if(gte(iw,ih),min(iw,{LONG_SIDE}),-2)':h='if(gte(iw,ih),-2,min(ih,{LONG_SIDE}))',pad=ceil(iw/2)*2:ceil(ih/2)*2"
    # No B-frames and a key frame every second, so frame 123 is frame 123 to every reader.
    run(FFMPEG, "-v", "error", "-nostdin", "-y", *cut, "-i", source, "-map", "0:v:0", "-map", "0:a:0?", "-vf", shape, "-c:v", "libx264", "-crf", "20", "-preset", "medium",
        "-g", str(FPS), "-bf", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", clip + ".partial.mp4")
    os.replace(clip + ".partial.mp4", clip)
    counted = run(FFPROBE, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", clip)
    about = probe(clip)
    about["frames"] = int(counted.stdout.strip().split(",")[0])
    if about["frames"] < SHORTEST_SHOT:
        raise Stop("the clip is shorter than half a second: nothing to follow")
    card["clip"] = {**about, "sha256": sha256_of(clip), "bytes": os.path.getsize(clip)}
    write(os.path.join(folder, "clip.json"), card)
    return card


# ---- cuts ------------------------------------------------------------------------


def jumps(path: str, score: float = CUT_SCORE) -> list:
    """[(frame, score)] for every picture ffmpeg scores as a jump from the one before."""
    done = run(FFMPEG, "-v", "error", "-nostdin", "-i", path, "-an", "-vf", f"select='gt(scene,{score})',metadata=print:file=-", "-f", "null", "-")
    found, at = [], None
    for line in done.stdout.splitlines():
        stamp = re.search(r"pts_time:([0-9.]+)", line)
        if stamp:
            at = int(round(float(stamp.group(1)) * FPS))
        got = re.search(r"lavfi\.scene_score=([0-9.]+)", line)
        if got and at is not None:
            found.append((at, round(float(got.group(1)), 3)))
            at = None
    return found


def shots_from(cut_frames: list, frames: int) -> list:
    """The shots between the cuts: [{index, first_frame, last_frame, seconds}]. A sliver joins the shot before it;
    a shot over a minute is split into equal parts."""
    starts = [0]
    for f in sorted(set(int(c) for c in cut_frames)):
        if 0 < f < frames and f - starts[-1] >= SHORTEST_SHOT:
            starts.append(f)
    if len(starts) > 1 and frames - starts[-1] < SHORTEST_SHOT:
        starts.pop()
    spans = []
    for first, after in zip(starts, starts[1:] + [frames]):
        parts = -(-(after - first) // LONGEST_SHOT)
        size = -(-(after - first) // parts)
        for p in range(parts):
            spans.append((first + p * size, min(after, first + (p + 1) * size) - 1, parts > 1))
    return [{"index": i, "first_frame": a, "last_frame": b, "seconds": round((b - a + 1) / FPS, 2), **({"part_of_a_long_shot": True} if split else {})} for i, (a, b, split) in enumerate(spans)]


def cuts(folder: str, score: float = None) -> dict:
    """Finds the cuts in clip.mp4 and writes shots.json. Cuts already written there by hand are kept as they are."""
    card = read(os.path.join(folder, "clip.json")) or {}
    if not card.get("clip") or not os.path.exists(os.path.join(folder, "clip.mp4")):
        raise Stop("the clip is not ready yet: run `just video <name>`")
    kept = read(os.path.join(folder, "shots.json")) or {}
    if kept.get("by_hand"):
        found, frames = [(f, None) for f in kept.get("cuts") or []], kept.get("cuts") or []
    else:
        score = score or card.get("cut_score") or CUT_SCORE
        found = jumps(os.path.join(folder, "clip.mp4"), score)
        frames = [f for f, _ in found]
    record = {
        "format": "forge-video-shots/1",
        "frames": card["clip"]["frames"],
        "fps": FPS,
        "cuts": [s["first_frame"] for s in shots_from(frames, card["clip"]["frames"])[1:]],
        "found": [{"frame": f, "score": s} for f, s in found] if not kept.get("by_hand") else kept.get("found", []),
        "by_hand": bool(kept.get("by_hand")),
        "shots": shots_from(frames, card["clip"]["frames"]),
    }
    write(os.path.join(folder, "shots.json"), record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="what", required=True)
    adding = sub.add_parser("add")
    adding.add_argument("file")
    adding.add_argument("name", nargs="?", default="")
    adding.add_argument("--start", default="")
    adding.add_argument("--end", default="")
    for step in ("ready", "cuts"):
        sub.add_parser(step).add_argument("name")
    args = parser.parse_args()
    try:
        if args.what == "add":
            folder = add(args.file, args.name or None, float(args.start) if args.start else None, float(args.end) if args.end else None)
            name = os.path.basename(folder)
            print(f"VIDEO {name}: kept in {os.path.relpath(folder, REPO)}/source.mp4. Next: just video {name}")
        elif args.what == "ready":
            card = ready(folder_of(args.name))
            print(f"VIDEO {args.name}: clip.mp4 ready, {card['clip']['frames']} frames ({card['clip']['seconds']} s), {card['clip']['width']}x{card['clip']['height']}")
        else:
            record = cuts(folder_of(args.name))
            print(f"VIDEO {args.name}: {len(record['shots'])} shots, cut at frames {record['cuts']}")
    except Stop as stop:
        print(f"VIDEO stopped: {stop}")
        sys.exit(1)


if __name__ == "__main__":
    main()
