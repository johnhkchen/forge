"""A stretch of a clip's motion as one beat of a shot, beside beats made from poses and from sentences.

A shot list's beat can say `"source": "video"`:

    {"name": "The routine", "source": "video", "seconds": 16.0,
     "clip": "candy-shop", "shot": 1, "from_s": 4.0, "to_s": 20.0, "at": "centre"}

    clip      a clip in videos/ that `just video` has made the motion for
    shot      which of its shots, counted from 1 as its page counts them. Left
              out, it is the shot those seconds fall in
    from_s, to_s
              the stretch wanted, in seconds of the clip (what a player shows
              when you scrub clip.mp4)
    person    whose motion, by their number in that shot; only needed when
              more than one person's motion was made for it
              (`just video <name> "" <shot>:<person>` makes another's)
    drift     "keep" (default) or "flatten", see below
    handles   false to give the joins the beat's own first and last frames

Where it stands is the shot's business, not the video's, as with a beat from
a sentence. On a standing set the beat is `at` a mark (it stands on it, facing
the way the mark faces as the stretch begins) or goes `from`/`to` marks; with
no set it gives from_m and to_m along the path, and facing_deg. What the video
keeps is how the dancer moves about from where they start: a step to the left
is still a step to the left.

    at a mark          the stretch begins on the mark. "keep" leaves the
                       dancer wherever the dance takes them by its end;
                       "flatten" takes out whatever they drifted over the
                       stretch, evenly, so they end on the mark again (a
                       camera that crept, or a dance that wanders)
    from one mark      the stretch is turned so that it travels the way the
    to another         path runs between the two, and its end is eased onto
                       the far mark

Joins. A seam's tween takes the place of the next piece's first 13 frames or
more, and of the last 12 of a piece like this one. So that the stretch you
asked for stays whole, the beat is cut with handles: that many frames more of
the clip before from_s and after to_s, for the tweens to use up. Where the
shot has none to give (the stretch starts with the shot), the tween takes
from the stretch itself. The beat's length in the shot includes its handles.

Nothing here calls a worker. The motion is read from videos/<clip>/motion/,
carried onto our skeleton (soma77.py), cut, placed, and handed to timeline.py
as a finished piece; plan_shot.py keeps it in the shot's cache under the hash
of its content.

Plain Python.
"""

from __future__ import annotations

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
import clip as clip_file  # noqa: E402
import soma77  # noqa: E402

FPS = 30
LONGEST_SECONDS = 60.0  # a shot of a clip is a minute at most, so a beat is too
SHORTEST_SECONDS = 0.5
FAR_FROM_MARK_M = 0.3  # a beat that ends further than this from where the next begins says so


def motion_file(folder: str, index: int, person=None) -> tuple:
    """(path, record) of the motion made for a shot of a clip: a named person's own file if there is one, else the
    file for whoever was chosen on the clip's page. ValueError, in plain words, if it is not there."""
    base = os.path.join(folder, "motion", f"shot-{index:03d}")
    name = os.path.basename(folder)
    if person is not None and os.path.exists(f"{base}-person-{person}.json"):
        return f"{base}-person-{person}.json", clip_file.read(f"{base}-person-{person}.record.json") or {}
    record = clip_file.read(base + ".record.json") or {}
    if not os.path.exists(base + ".json"):
        raise ValueError(f"the clip \"{name}\" has no motion for shot {index + 1} yet: choose who to follow there and run `just video {name}`")
    if person is not None and record.get("person") != person:
        raise ValueError(f"shot {index + 1} of \"{name}\" has motion for person {record.get('person')}, not {person}: `just video {name} \"\" {index + 1}:{person}` makes theirs")
    return base + ".json", record


def find(beat: dict, videos: str = None) -> dict:
    """Which frames of which motion a video beat asks for. ValueError says what is wrong with the asking."""
    where = f"beat \"{beat.get('name')}\""
    name = beat.get("clip")
    if not name or not clip_file.NAME.match(str(name)):
        raise ValueError(f"{where}: a video beat names its clip (a folder in videos/)")
    folder = os.path.join(videos or os.environ.get("FORGE_VIDEOS") or clip_file.VIDEOS, name)
    shots = (clip_file.read(os.path.join(folder, "shots.json")) or {}).get("shots")
    if not shots:
        raise ValueError(f"{where}: there is no clip \"{name}\" with its cuts found (`just video-add`, then `just video {name}`)")
    if beat.get("from_s") is None or beat.get("to_s") is None:
        raise ValueError(f"{where}: a video beat says which seconds of the clip it wants (from_s, to_s)")
    first, last = int(round(float(beat["from_s"]) * FPS)), int(round(float(beat["to_s"]) * FPS))
    seconds = (last - first) / FPS
    if not SHORTEST_SECONDS <= seconds <= LONGEST_SECONDS:
        raise ValueError(f"{where}: a video beat lasts {SHORTEST_SECONDS} to {LONGEST_SECONDS:.0f} seconds, not {seconds:.2f}")
    if beat.get("shot") is None:
        shot = next((s for s in shots if s["first_frame"] <= first and last <= s["last_frame"]), None)
        if shot is None:
            raise ValueError(f"{where}: seconds {beat['from_s']} to {beat['to_s']} of \"{name}\" are not inside one shot (a cut falls between them)")
    else:
        number = int(beat["shot"])
        if not 1 <= number <= len(shots):
            raise ValueError(f"{where}: \"{name}\" has shots 1 to {len(shots)}, not {number}")
        shot = shots[number - 1]
        if not (shot["first_frame"] <= first and last <= shot["last_frame"]):
            raise ValueError(f"{where}: shot {number} of \"{name}\" runs from {shot['first_frame'] / FPS:.2f} to {shot['last_frame'] / FPS:.2f} s of the clip; {beat['from_s']} to {beat['to_s']} is not inside it")
    person = int(beat["person"]) if beat.get("person") is not None else None
    path, record = motion_file(folder, shot["index"], person)
    return {"clip": name, "folder": folder, "shot": shot, "first": first, "last": last, "file": path, "person": record.get("person", person), "made_as": record.get("request")}


def piece(stage, beat: dict, first: int, piece_card: dict, sk, before: int = 0, after: int = 0, videos: str = None) -> tuple:
    """A video beat as a finished piece of a shot. `before` and `after` are the frames the seams at its two ends
    will replace. Fills in `piece_card` (what plan.json keeps); returns (the motion, placed; the marks; its frames)."""
    import timeline

    want = find(beat, videos)
    answer = clip_file.read(want["file"])
    whole, report = soma77.convert(answer, sk)
    shot = want["shot"]
    if len(whole["root"]) != shot["last_frame"] - shot["first_frame"] + 1:
        raise ValueError(f"beat \"{beat['name']}\": the motion for shot {shot['index'] + 1} of \"{want['clip']}\" has {len(whole['root'])} frames, the shot has {shot['last_frame'] - shot['first_frame'] + 1}: the cuts changed since it was made")
    # Handles: frames of the clip either side of the stretch, for the seams' tweens to take the place of.
    handles = beat.get("handles", True) is not False
    lead = min(before if handles else 0, want["first"] - shot["first_frame"])
    tail = min(after if handles else 0, shot["last_frame"] - want["last"])
    motion = timeline.cut(whole, want["first"] - lead - shot["first_frame"], want["last"] + tail - shot["first_frame"])
    motion = {**motion, "root": [list(r) for r in motion["root"]], "rotations": [list(r) for r in motion["rotations"]], "contacts": [list(c) for c in motion["contacts"]]}
    count = len(motion["root"]) - 1
    a, b = lead, count - tail  # the stretch asked for, as frames of the piece

    # Where the shot wants it: the stretch begins at from_m on the path, and ends (if it travels) at to_m.
    path = stage.path
    if beat.get("from_m") is None or beat.get("to_m") is None:
        raise ValueError(f"beat \"{beat['name']}\": a video beat says where it is on the path (from_m, to_m), or names a mark (at, or from and to)")
    x0, z0, h0 = path.at(float(beat["from_m"]))
    x1, z1, _ = path.at(float(beat["to_m"]))
    travels = math.hypot(x1 - x0, z1 - z0) > 0.05
    went = (motion["root"][b][0] - motion["root"][a][0], motion["root"][b][2] - motion["root"][a][2])
    if travels:
        if math.hypot(*went) < 0.05:
            raise ValueError(f"beat \"{beat['name']}\": it is asked to go somewhere, but the dancer stays on the spot in those seconds; put it `at` a mark")
        # Turned so that the way it went is the way the path goes.
        turn = math.degrees(math.atan2(x1 - x0, z1 - z0) - math.atan2(went[0], went[1]))
    else:
        turn = h0 + float(beat.get("facing_deg") or 0.0) - timeline.facing(sk, motion, a)
    motion = timeline.moved(motion, turn, 0.0, 0.0)
    motion = timeline.moved(motion, 0.0, x0 - motion["root"][a][0], z0 - motion["root"][a][2])
    drift = beat.get("drift") or "keep"
    if drift not in ("keep", "flatten"):
        raise ValueError(f"beat \"{beat['name']}\": drift is keep or flatten")
    off = (x1 - motion["root"][b][0], z1 - motion["root"][b][2])  # from where it ends to where the shot wants it
    if travels or drift == "flatten":
        for f, root in enumerate(motion["root"]):
            share = min(1.0, max(0.0, (f - a) / float(max(1, b - a))))
            root[0], root[2] = round(root[0] + off[0] * share, 5), round(root[2] + off[1] * share, 5)
        eased, off = off, (0.0, 0.0)
    else:
        eased = (0.0, 0.0)
    ends = motion["root"][b]
    marks = [
        {
            "name": f"{beat['name']}: ends",
            "beat": beat["name"],
            "pose": None,
            "frame": first + count,
            "x": round(x1, 4),
            "z": round(z1, 4),
            "heading": round(timeline.facing(sk, motion, count), 2),
            "stands_at": [round(x1, 4), round(z1, 4)],
            "speed_mps": round(math.hypot(motion["root"][count][0] - motion["root"][count - 3][0], motion["root"][count][2] - motion["root"][count - 3][2]) * FPS / 3.0, 3),
            "early_frames": 0,
            "pins": [],
            "pin_points": {},
            "hold_pins_frames": 0,
        }
    ]
    piece_card.update(
        {
            "clip": want["clip"],
            "clip_shot": shot["index"] + 1,
            "person": want["person"],
            "clip_frames": [want["first"] - lead, want["last"] + tail],
            "asked_for": [a, b],
            "handles": [lead, tail],
            "placement": {"x": round(x0, 4), "z": round(z0, 4), "turned_deg": round(turn, 2), "travels": travels},
            "drift": drift,
            "drift_taken_out_cm": round(100.0 * math.hypot(*eased), 1),
            "ends_from_its_mark_cm": round(100.0 * math.hypot(ends[0] - x1, ends[2] - z1), 1),
            "ours_vs_gemx_cm": report["ours_vs_gemx_cm"],
            "video": timeline.digest({"root": motion["root"], "rotations": motion["rotations"], "contacts": motion["contacts"]}),
        }
    )
    return motion, marks, count
