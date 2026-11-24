"""Rehearses a shot or a take with stand-ins for the motion models: everything `just shoot` does, and no RunPod.

    python3 scripts/video/rehearse.py <plan: motion/shots/<name>.json> <folder to rehearse in>

A take with beats from a video costs nothing for those beats (the clip's motion
is on hand), but its sentences and its joins are Kimodo's and MotionBricks'
on the GPU. Before paying for those, this plays the whole thing through with
the pretend worker the offline tests use (scripts/motion/test_timeline.py):
a sentence becomes a body gliding along its path in the rest pose, a join an
even blend. Nobody would watch that, but the video beats are the real thing,
everything is where and when it will be, and what can go wrong shows: a clip
whose motion is missing, roles of different lengths, a formation that puts
two people in one place.

It does what `baml run shoot` does, in order: segment.py (for a take), then
for each role plan_shot.py, timeline.py until the pieces are joined,
checks.py, to_gltf.py. Then it says, for everyone on the stage together, how
close any two come and when.

The folder must not be the shot's real one in shots/: the pretend answers are
kept in a cache like real ones, and a real `just shoot` there would use them.
Cast it and film it from the rehearsal folder like any take:

    Blender -b --factory-startup -P scripts/motion/apply_shot.py -- <folder>/<role> runs/<character> --versions lowpoly --name rehearsal
    Blender -b --factory-startup -P scripts/motion/render_take.py -- <folder> --cast rehearsal --cameras crew

Plain Python.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MOTION = os.path.join(REPO, "scripts", "motion")
sys.path.insert(0, HERE)
sys.path.insert(0, MOTION)
import clip as clip_file  # noqa: E402
import timeline  # noqa: E402
from soma import Skeleton  # noqa: E402


def run(script: str, *args: str) -> str:
    done = subprocess.run([sys.executable, os.path.join(MOTION, script), *args], capture_output=True, text=True)
    if done.returncode != 0:
        said = (done.stderr or done.stdout).strip().splitlines()
        raise clip_file.Stop(f"{script}: {said[-1] if said else 'failed'}")
    return done.stdout


def role(folder: str, plan_file: str, sk: Skeleton, answer=None, log=print) -> dict:
    """One role (or a single shot) from its shotlist.json to motion.json, checks.json and motion.glb."""
    import test_timeline

    for line in run("plan_shot.py", folder, "--brief", plan_file).splitlines():
        if "of the clip" in line or " pieces, " in line:
            log("  " + line)
    asked = []
    for _ in range(timeline_passes()):
        result = timeline.step(folder, sk)
        if not result["todo"]:
            break
        for item in result["todo"]:
            request = clip_file.read(timeline.cache_path(folder, item["request"], "request"))
            asked.append(item["kind"])
            made = (answer(item, request) if answer else None) or test_timeline.pretend(request)
            clip_file.write(timeline.cache_path(folder, item["request"]), made, indent=None)
    if not result.get("joined"):
        raise clip_file.Stop("the pieces were not joined")
    run("checks.py", folder)
    run("to_gltf.py", folder)
    with open(os.path.join(folder, "motion.json")) as f:
        motion = json.load(f)
    return {"motion": motion, "plan": clip_file.read(os.path.join(folder, "plan.json")), "notes": result["notes"], "asked": asked, "checks": clip_file.read(os.path.join(folder, "checks.json"))}


def timeline_passes() -> int:
    return 4


def together(sk: Skeleton, roles: dict, every: int = 3) -> dict:
    """With everyone on the stage: the closest any two come (hips over the floor, and any joint to any joint), and in which beat."""
    names = list(roles)
    count = min(len(roles[n]["motion"]["root"]) for n in names)
    beats = roles[names[0]]["plan"]["beats"]
    best = {"hips_cm": None, "bodies_cm": None, "by_beat": {}}
    for f in range(0, count, every):
        pos = {n: sk.fk(roles[n]["motion"]["root"][f], [tuple(roles[n]["motion"]["rotations"][f][4 * j : 4 * j + 4]) for j in range(len(sk.joints))])[0] for n in names}
        beat = next((b["name"] for b in beats if b["first_frame"] <= f <= b["last_frame"]), "")
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                hips = round(100.0 * math.hypot(pos[a][0][0] - pos[b][0][0], pos[a][0][2] - pos[b][0][2]), 1)
                near = round(100.0 * min(math.dist(u, v) for u in pos[a] for v in pos[b]), 1)
                if best["hips_cm"] is None or hips < best["hips_cm"]:
                    best.update({"hips_cm": hips, "hips_between": [a, b], "hips_frame": f, "hips_in": beat})
                if best["bodies_cm"] is None or near < best["bodies_cm"]:
                    best.update({"bodies_cm": near, "bodies_between": [a, b], "bodies_frame": f, "bodies_in": beat})
                card = best["by_beat"].setdefault(beat, {"hips_cm": hips, "between": [a, b], "frame": f})
                if hips < card["hips_cm"]:
                    card.update({"hips_cm": hips, "between": [a, b], "frame": f})
    return best


def rehearse(plan_file: str, folder: str, answer=None, log=print) -> dict:
    folder = os.path.abspath(folder)
    shots = os.path.join(REPO, "shots")
    if os.path.commonpath([folder, shots]) == shots:
        raise clip_file.Stop("rehearse somewhere other than shots/: the pretend answers are kept like real ones, and a real shoot there would use them")
    plan = clip_file.read(plan_file)
    if not plan:
        raise clip_file.Stop(f"there is no plan at {plan_file}")
    sk = Skeleton.load()
    os.makedirs(folder, exist_ok=True)
    if plan.get("segment"):
        log(run("segment.py", plan_file, folder).rstrip())
        take = clip_file.read(os.path.join(folder, "take.json"))
        roles = {}
        for name, card in take["roles"].items():
            log(f"REHEARSE the {name} ({card['character']})")
            roles[name] = role(os.path.join(folder, card["folder"]), plan_file, sk, answer, log)
    else:
        kept = os.path.splitext(plan_file)[0] + ".shotlist.json"
        if not os.path.exists(os.path.join(folder, "shotlist.json")):
            if not os.path.exists(kept):
                raise clip_file.Stop("a rehearsal needs the shot list kept with the plan (Opus is not asked)")
            clip_file.write(os.path.join(folder, "shotlist.json"), clip_file.read(kept))
        roles = {"": role(folder, plan_file, sk, answer, log)}
    out = {"roles": roles, "frames": len(next(iter(roles.values()))["motion"]["root"])}
    for name, made in roles.items():
        for piece in made["plan"].get("pieces") or []:
            if piece["source"] == "video":
                form = piece.get("formation") or {}
                log(f"REHEARSE {name or 'the shot'}, {piece['name']}: person {piece['person']} of {piece['clip']}, frames {piece['clip_frames'][0]}-{piece['clip_frames'][1]}; starts {piece['starts_from_its_mark_cm']} cm from its mark"
                    + (f" at {form['starts_at']}" if form else "") + f", ends {piece['ends_from_its_mark_cm']} cm from its mark" + (f" at {form['ends_at']}" if form else ""))
        feet = made["checks"]["feet"]
        log(f"REHEARSE {name or 'the shot'}: {made['checks']['frames']} frames; feet slide {max(f['slide_speed_cm_per_s'] for f in feet.values())} cm/s at most; asked of the pretend models: {made['asked'].count('text')} sentences, {made['asked'].count('inbetween')} poses and joins")
    if len(roles) > 1:
        out["together"] = together(sk, roles)
        near = out["together"]
        log(f"REHEARSE closest: hips {near['hips_cm']} cm ({' and '.join(near['hips_between'])}, frame {near['hips_frame']}, in \"{near['hips_in']}\"); any two joints {near['bodies_cm']} cm ({' and '.join(near['bodies_between'])}, frame {near['bodies_frame']}, in \"{near['bodies_in']}\")")
        for beat, card in near["by_beat"].items():
            log(f"REHEARSE   {beat}: hips never nearer than {card['hips_cm']} cm ({' and '.join(card['between'])}, frame {card['frame']})")
        clip_file.write(os.path.join(folder, "rehearsal.json"), {"closest": near, "frames": out["frames"]})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan")
    parser.add_argument("folder")
    args = parser.parse_args()
    try:
        rehearse(args.plan, args.folder)
    except (clip_file.Stop, ValueError) as stop:
        sys.exit(f"rehearse: {stop}")


if __name__ == "__main__":
    main()
