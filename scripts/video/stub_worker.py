"""A stand-in for GEM-X, for trying everything around it with no GPU: `python3 scripts/video/test_video.py`.

It speaks the same JSON lines as gemx_worker/models/gemx_model.py and answers
the same two kinds in the same shapes, so the worker's router, the client, the
conversion and the joining all run for real. What it makes up:

  people   two or three "people" a shot, as boxes that move over the picture
           (one of them smaller, in the same colours, moving as a mirror image
           of the first: a studio mirror), fed frame by frame to the worker's
           real tracker. The small pictures are cut from the clip with ffmpeg.

  motion   a made-up dance on the spot: knees bounce, arms wave (the left one
           higher), the chest twists. It is written the way GEM-X writes: on a
           body with its own proportions (taller, shins leaning), as world
           turns from that body's rest pose, in a world that starts somewhere
           else and faces another way for every shot. The dance itself depends
           only on the clip's frame number, so two shots that follow each
           other in the film are two stretches of one continuous dance: what
           a cut between two cameras is.

None of it comes from anyone's motion data or from NVIDIA's samples.
"""

from __future__ import annotations

import base64
import json
import math
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
sys.path.insert(0, os.path.join(REPO, "motionbricks_worker", "models"))
sys.path.insert(0, os.path.join(REPO, "gemx_worker"))
from soma import SKELETON_FILE, X, Y, Z, Skeleton, qaxis, qconj, qmul, qnorm, qrot  # noqa: E402
from soma_bridge import Bridge  # noqa: E402

FPS = 30
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
IDENTITY = (0.0, 0.0, 0.0, 1.0)
CONTACT_ORDER = ["left_ankle", "left_toes", "right_ankle", "right_toes", "left_wrist", "right_wrist"]
MARKS = ("LeftHand", "RightHand", "LeftToeBase", "RightToeBase", "Head")
SPINE = ("Spine1", "Spine2", "Chest")


def dance_pose(sk: Skeleton, clip_frame: int) -> tuple:
    """One frame of the made-up dance on our skeleton: (root, local rotations). Feet stay where they stand."""
    t = clip_frame / float(FPS)
    knee = 32.0 * (0.5 - 0.5 * math.cos(2.0 * math.pi * 1.2 * t))
    twist = 22.0 * math.sin(2.0 * math.pi * 0.45 * t)
    left_arm = 25.0 + 30.0 * math.sin(2.0 * math.pi * 0.6 * t)  # degrees below level; the left arm is the high one
    right_arm = 65.0 + 12.0 * math.sin(2.0 * math.pi * 0.6 * t + 1.0)
    bend = 40.0 + 25.0 * math.sin(2.0 * math.pi * 0.9 * t)
    nod = 10.0 * math.sin(2.0 * math.pi * 1.2 * t)
    # How far each joint has turned from the rest pose, in the world.
    turned = {name: IDENTITY for name in sk.joints}
    for k, name in enumerate(SPINE):
        turned[name] = qaxis(Y, twist * (k + 1) / len(SPINE))
    chest = turned["Chest"]
    for name in ("Neck1", "Neck2", "LeftShoulder", "RightShoulder"):
        turned[name] = chest
    for name in ("Head", "Jaw", "LeftEye", "RightEye"):
        turned[name] = qmul(chest, qaxis(X, nod))
    for side, sign, drop in (("Left", -1.0, left_arm), ("Right", 1.0, right_arm)):
        arm = qmul(chest, qaxis(Z, sign * drop))
        fore = qmul(arm, qaxis(Y, sign * bend))
        turned[f"{side}Arm"] = arm
        for name in (f"{side}ForeArm", f"{side}Hand", f"{side}HandThumbEnd", f"{side}HandMiddleEnd"):
            turned[name] = fore
        turned[f"{side}Leg"] = qaxis(X, -knee)
        turned[f"{side}Shin"] = qaxis(X, knee)
    world = [qnorm(qmul(turned[name], sk.rest_world_rot[i])) for i, name in enumerate(sk.joints)]
    local = [world[i] if p < 0 else qnorm(qmul(qconj(world[p]), world[i])) for i, p in enumerate(sk.parents)]
    # Bending the knees lowers the hips by whatever keeps the left foot on its spot.
    foot = sk.index["LeftFoot"]
    pos, _ = sk.fk(sk.rest_pos[0], local)
    root = tuple(sk.rest_pos[0][a] - (pos[foot][a] - sk.rest_world_pos[foot][a]) for a in range(3))
    return root, local


def dance(sk: Skeleton, first: int, last: int) -> dict:
    """Frames first..last of the dance, in the repo's motion format: what the conversion should give back."""
    rows = [dance_pose(sk, f) for f in range(first, last + 1)]
    return {
        "format": "forge-soma-motion/1",
        "fps": FPS,
        "joints": list(sk.joints),
        "root": [list(root) for root, _ in rows],
        "rotations": [[c for q in local for c in q] for _, local in rows],
        "contact_order": ["left_heel", "left_toe", "right_heel", "right_toe"],
        "contacts": [[1.0, 1.0, 1.0, 1.0] for _ in rows],
    }


def their_body(sk: Skeleton, taller: float = 1.07, lean_m: float = 0.035, stands_turned_deg: float = 0.0) -> dict:
    """A body like the ones GEM-X answers on: not our proportions (taller, the shins leaning back a little), its
    hips somewhere of its own, and maybe standing another way round in its rest pose."""
    rest = {name: [c * taller for c in sk.rest_world_pos[i]] for i, name in enumerate(sk.joints)}
    for side in ("Left", "Right"):
        for name in (f"{side}Foot", f"{side}ToeBase"):
            rest[name][2] -= lean_m
    about = qaxis(Y, stands_turned_deg)
    return {name: list(qrot(about, tuple(p))) for name, p in rest.items()}


def as_gemx(sk: Skeleton, card: dict, motion: dict, first: int, world_turn_deg: float = 0.0, world_at=(0.0, 0.0, 0.0), stands_turned_deg: float = 0.0) -> dict:
    """A motion of ours written the way the video worker answers ("gemx-soma77/1"): our conversion, run backwards."""
    upright = their_body(sk)
    bridge = Bridge(card, upright, 0.0)
    theirs = their_body(sk, stands_turned_deg=stands_turned_deg)
    stance, world_turn = qaxis(Y, stands_turned_deg), qaxis(Y, world_turn_deg)

    def leg(of: dict) -> float:
        return of["Hips"][1] - (of["LeftToeBase"][1] + of["RightToeBase"][1]) / 2.0

    size = leg({name: sk.rest_world_pos[i] for i, name in enumerate(sk.joints)}) / leg(upright)
    names = list(card["joints"])
    roots, turns, marks = [], [], {name: [] for name in MARKS}
    for root, row in zip(motion["root"], motion["rotations"]):
        pos, world = sk.fk(root, [tuple(row[4 * j : 4 * j + 4]) for j in range(len(sk.joints))])
        # World turn from their rest pose: ours with their bones' small differences taken out, their stance undone.
        turned = {name: qnorm(qmul(world_turn, qmul(qmul(world[j], qconj(bridge.carry[j])), qconj(stance)))) for j, name in enumerate(bridge.joints)}
        turns.append([round(c, 6) for name in names for c in turned.get(name, IDENTITY)])
        place = lambda p: [round(c + world_at[a], 5) for a, c in enumerate(qrot(world_turn, tuple(v / size for v in p)))]  # noqa: E731
        roots.append(place(pos[0]))
        for name in MARKS:
            marks[name].append(place(pos[sk.index[name]]))
    return {
        "format": "gemx-soma77/1",
        "fps": FPS,
        "up": "+Y",
        "first_frame": first,
        "last_frame": first + len(roots) - 1,
        "joints": names,
        "rest": [[round(c, 5) for c in theirs.get(name, theirs["Hips"])] for name in names],
        "root": roots,
        "turns": turns,
        "contact_order": CONTACT_ORDER,
        "contacts": [[c[0], c[1], c[2], c[3], 0.0, 0.0] for c in motion["contacts"]],
        "marks": marks,
        "made_by": {"model": "a stand-in for GEM-X (scripts/video/stub_worker.py)", "camera": "static", "postprocess": True},
    }


# ---- the two jobs ----------------------------------------------------------------


def colours(kind: int) -> list:
    """Made-up clothing colours (80 numbers, as the real worker measures them): each kind of outfit its own."""
    out = [0.0] * 80
    for at, share in ((3 + 7 * kind, 0.7), (36 + kind % 4, 0.3), (40 + (5 + 11 * kind) % 36, 0.8), (76 + (kind + 1) % 4, 0.2)):
        out[at] += share
    return out


def made_up_people(first: int, last: int, width: int, height: int, shot: int) -> list:
    """Detections per frame: [(box, score, outfit)]. A dancer, their reflection, and on odd shots someone else."""
    frames = []
    for f in range(first, last + 1):
        t = f / float(FPS)
        sway, bob = math.sin(2.0 * math.pi * 0.5 * t), math.sin(2.0 * math.pi * 1.2 * t)
        tall = 0.62 * height
        cx, cy = width * (0.42 + 0.08 * sway), height * (0.56 + 0.02 * bob)
        row = [([cx - tall * 0.2, cy - tall / 2, cx + tall * 0.2, cy + tall / 2], 0.93, 0)]
        small = 0.4 * height  # the reflection: smaller, the same clothes, left and right swapped
        mx, my = width * (0.8 - 0.05 * sway), height * (0.5 + 0.013 * bob)
        row.append(([mx - small * 0.2, my - small / 2, mx + small * 0.2, my + small / 2], 0.8, 0))
        if shot % 2 == 1:
            other = 0.5 * height
            ox, oy = width * (0.16 + 0.03 * math.sin(2.0 * math.pi * 0.23 * t + 1.0)), height * 0.58
            row.append(([ox - other * 0.2, oy - other / 2, ox + other * 0.2, oy + other / 2], 0.88, 1))
        frames.append(row)
    return frames


def picture(clip: str, frame: int, crop=None, wide: int = 320) -> str:
    """One frame of the clip (or a box of it) as a small JPEG, base64, cut with ffmpeg."""
    cut = f"crop={int(crop[2] - crop[0])}:{int(crop[3] - crop[1])}:{max(0, int(crop[0]))}:{max(0, int(crop[1]))}," if crop else ""
    done = subprocess.run([FFMPEG, "-v", "error", "-nostdin", "-i", clip, "-vf", f"select=eq(n\\,{frame}),{cut}scale={wide}:-2", "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-"], capture_output=True)
    if done.returncode != 0 or not done.stdout:
        raise RuntimeError(f"ffmpeg could not cut frame {frame}: {done.stderr.decode()[-300:]}")
    return base64.b64encode(done.stdout).decode()


def clip_size(clip: str) -> tuple:
    done = subprocess.run([os.path.join(os.path.dirname(FFMPEG), "ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", clip], capture_output=True, text=True)
    width, height = done.stdout.strip().split(",")[:2]
    return int(width), int(height)


def people(params: dict) -> dict:
    import tracks as T

    width, height = clip_size(params["clip_path"])
    out = []
    for number, (first, last) in enumerate(params.get("shots") or []):
        tracker, outfit_of = T.Tracker(), {}
        for i, row in enumerate(made_up_people(first, last, width, height, number)):
            tracker.see(first + i, [box for box, _, _ in row], [score for _, score, _ in row])
            for track_id, boxes in tracker.tracks.items():
                if first + i in boxes and track_id not in outfit_of:
                    outfit_of[track_id] = next(outfit for box, _, outfit in row if box == boxes[first + i])
        found = T.people_of(tracker.tracks, first, last, width, height)
        keys = T.key_frames(found, first, last, count=2)
        for person in found:
            person["colors"] = colours(outfit_of[person.pop("track")])
            person["joined_from_pieces"] = 1
            person["thumbs"] = [{"frame": f, "jpeg": picture(params["clip_path"], f, crop=person["boxes"][f - first], wide=64)} for f in T.thumb_frames(person, first, count=1)]
        out.append({"index": number, "first_frame": first, "last_frame": last, "width": width, "height": height, "people": found, "keyframes": [{"frame": f, "jpeg": picture(params["clip_path"], f)} for f in keys]})
    return {"format": "gemx-people/1", "fps": FPS, "shots": out, "detector": {"model": "a stand-in (made-up boxes)", "runs_on": "nothing", "frames_looked_at": sum(b - a + 1 for a, b in params.get("shots") or []), "seconds": 0.0}}


def motion(params: dict) -> dict:
    import tracks as T

    first, last = int(params["first"]), int(params["last"])
    boxes = params.get("boxes") or []
    if len(boxes) != last - first + 1:
        raise ValueError(f"one box per frame: the shot has {last - first + 1} frames, {len(boxes)} boxes came")
    _, seen = T.fill(boxes)
    sk = Skeleton.load()
    with open(SKELETON_FILE) as f:
        card = json.load(f)
    # Every shot's world starts somewhere else and faces another way, as a new camera's does.
    answer = as_gemx(sk, card, dance(sk, first, last), first, world_turn_deg=37.0 * (1 + first % 7), world_at=(0.4 * (first % 5), 0.0, 2.0 + 0.3 * (first % 3)))
    answer["boxes_seen"] = seen
    answer["made_by"].update({"camera": params.get("camera", "static"), "postprocess": bool(params.get("postprocess", True)), "frames_with_a_box": sum(seen)})
    return answer


BOOT = {"gpu": "none (a stand-in)", "fetched_this_boot": False, "seconds": {"boot": 0.0}}
KINDS = {"people": people, "motion": motion, "info": lambda params: BOOT}


def serve() -> None:
    answers = os.fdopen(os.dup(1), "w")
    os.dup2(2, 1)

    def say(message: dict) -> None:
        answers.write(json.dumps(message, separators=(",", ":")) + "\n")
        answers.flush()

    say({"ready": True, "boot": BOOT})
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            job = json.loads(line)
            t0 = time.time()
            result = KINDS[job["kind"]](job.get("input") or {})
            say({"ok": True, "result": result, "seconds": round(time.time() - t0, 3)})
        except Exception as error:  # noqa: BLE001
            say({"ok": False, "error": f"{type(error).__name__}: {error}"})


if __name__ == "__main__":
    serve()
