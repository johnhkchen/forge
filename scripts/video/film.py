"""Films a video's shot next to the clip it came from, in step, so you can judge it by eye.

    python3 scripts/video/film.py <clip folder> <shot folder> [--cast lowpoly-hero]

Three steps, each skipped if its file is newer than what it is made from:

  1. motion.glb    the motion on the box mannequin (scripts/motion/to_gltf.py)
  2. motion.mp4    the mannequin filmed from the front in a background Blender
                   (scripts/motion/render_shot.py), upright if the clip is
                   upright; and strip.png, twelve stills
  3. videos/<name>/side-by-side.mp4
                   the clip and that film together. Only the frames of the
                   shots you kept are in it, in order, so frame for frame the
                   two show the same moment; the clip's sound runs under it.
                   An upright clip sits beside the mannequin, a wide one
                   above it.

With --cast, the film of a character `just cast` put in the shot
(<shot>/lowpoly-<clip>.mp4) takes the mannequin's place, and the result is
side-by-side-<clip>.mp4.

The clip's pictures stay in videos/ (not in git); the shot folder gets only
the mannequin.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import clip as clip_file  # noqa: E402

BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
MOTION = os.path.join(REPO, "scripts", "motion")
FPS = 30


def newer(made: str, *sources: str) -> bool:
    """Is `made` there, and newer than everything it is made from?"""
    return os.path.exists(made) and all(os.path.getmtime(made) >= os.path.getmtime(s) for s in sources if os.path.exists(s))


def mannequin(shot_dir: str, upright: bool, log=print) -> str:
    """motion.glb, then motion.mp4 and strip.png, for the shot's motion. Returns the film."""
    motion, glb, film = (os.path.join(shot_dir, n) for n in ("motion.json", "motion.glb", "motion.mp4"))
    if not newer(glb, motion):
        done = subprocess.run([sys.executable, os.path.join(MOTION, "to_gltf.py"), shot_dir], capture_output=True, text=True)
        if done.returncode != 0:
            raise clip_file.Stop(f"the mannequin could not be made: {(done.stderr or done.stdout).strip()[-600:]}")
    if not newer(film, glb):
        if not os.path.exists(BLENDER):
            raise clip_file.Stop(f"Blender is not at {BLENDER} (set BLENDER): the motion is in {shot_dir}, only the film is missing")
        log("video: filming the mannequin in a background Blender")
        done = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P", os.path.join(MOTION, "render_shot.py"), "--", shot_dir, *(["--size", "540x960", "--closer", "0.72"] if upright else ["--size", "960x540"])], capture_output=True, text=True)
        if done.returncode != 0 or not os.path.exists(film):
            raise clip_file.Stop(f"Blender did not film the shot:\n{(done.stdout + done.stderr).strip()[-900:]}")
    return film


def side_by_side(folder: str, shot_dir: str, film: str, out: str) -> dict:
    """The kept frames of the clip and a film of the same length, as one video."""
    source = clip_file.read(os.path.join(shot_dir, "source.json")) or {}
    card = (clip_file.read(os.path.join(folder, "clip.json")) or {}).get("clip") or {}
    if not source.get("pieces") or not card:
        raise clip_file.Stop("the shot does not say which frames of the clip it came from")
    clip = os.path.join(folder, "clip.mp4")
    pictures = "+".join(f"between(n\\,{p['clip_first_frame']}\\,{p['clip_last_frame']})" for p in source["pieces"])
    sound = "+".join(f"between(t\\,{p['clip_first_frame'] / FPS:.4f}\\,{(p['clip_last_frame'] + 1) / FPS:.4f})" for p in source["pieces"])
    theirs = clip_file.probe(film)
    upright = card["height"] > card["width"]
    if upright:  # beside each other, the same height
        fit, stack = f"scale=-2:{theirs['height']}", "hstack=inputs=2"
    else:  # one above the other, the same width
        fit, stack = f"scale={theirs['width']}:-2", "vstack=inputs=2"
    graph = f"[0:v]select='{pictures}',setpts=N/{FPS}/TB,{fit},setsar=1[a];[1:v]setpts=N/{FPS}/TB,setsar=1[b];[a][b]{stack}[v]"
    maps = ["-map", "[v]"]
    if card.get("sound"):
        graph += f";[0:a]aselect='{sound}',asetpts=N/SR/TB[s]"
        maps += ["-map", "[s]", "-c:a", "aac", "-b:a", "128k"]
    clip_file.run(clip_file.FFMPEG, "-v", "error", "-nostdin", "-y", "-i", clip, "-i", film, "-filter_complex", graph, *maps, "-r", str(FPS), "-c:v", "libx264", "-crf", "21", "-pix_fmt", "yuv420p",
                  "-movflags", "+faststart", "-shortest", out + ".partial.mp4")
    os.replace(out + ".partial.mp4", out)
    made = clip_file.probe(out)
    return {"film": os.path.basename(out), "seconds": made["seconds"], "width": made["width"], "height": made["height"], "frames_of_the_clip": sum(p["clip_last_frame"] - p["clip_first_frame"] + 1 for p in source["pieces"])}


def film(folder: str, shot_dir: str, cast: str = None, log=print) -> dict:
    card = (clip_file.read(os.path.join(folder, "clip.json")) or {}).get("clip") or {}
    if cast:
        theirs = os.path.join(shot_dir, f"{cast}.mp4")
        if not os.path.exists(theirs):
            raise clip_file.Stop(f"there is no {cast}.mp4 in {shot_dir}: `just cast` makes it")
        out = os.path.join(folder, f"side-by-side-{cast}.mp4")
    else:
        theirs = mannequin(shot_dir, card.get("height", 0) > card.get("width", 0), log)
        out = os.path.join(folder, "side-by-side.mp4")
    if newer(out, theirs, os.path.join(shot_dir, "source.json")):
        return {"film": os.path.basename(out), "already_there": True}
    return side_by_side(folder, shot_dir, theirs, out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("clip")
    parser.add_argument("shot")
    parser.add_argument("--cast", default="")
    args = parser.parse_args()
    try:
        made = film(args.clip, args.shot, args.cast or None)
    except clip_file.Stop as stop:
        print(f"VIDEO stopped: {stop}")
        sys.exit(1)
    print(f"VIDEO film: {os.path.join(args.clip, made['film'])}")


if __name__ == "__main__":
    main()
