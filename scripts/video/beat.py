"""A stretch of a clip's motion as one beat of a shot, beside beats made from poses and from sentences.

A shot list's beat can say `"source": "video"`:

    {"name": "The routine", "source": "video", "seconds": 16.0,
     "clip": "candy-shop", "shot": 1, "from_s": 4.0, "to_s": 20.0, "at": "centre"}

    clip      a clip in videos/ that `just video` has made the motion for
    shot      which of its shots, counted from 1 as its page counts them. Left
              out, it is the shot those seconds fall in; and the stretch may
              then run on from one shot into the next where the clip was only
              split for its length (a take of over a minute), not cut
    from_s, to_s
              the stretch wanted, in seconds of the clip (what a player shows
              when you scrub clip.mp4)
    person    whose motion, by their number in that shot; only needed when
              more than one person's motion was made for it
              (`just video <name> "" <shot>:<person>` makes another's)
    drift     "keep" (default) or "flatten", see below
    handles   false to give the joins the beat's own first and last frames
    lock_feet false to leave the feet as the video's motion has them. By
              default a foot that is down is held on its spot and the body
              carried by it, so drift shows as steps, not as skating
              (footlock.py)

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

A crew. Several dancers filmed together are several roles of a take, each
with a beat of its own for the same seconds, and they should stand to each
other as they did in the clip. `formation` says so:

    "person": 3, "formation": {"people": [1, 2, 3], "at": "crew", "spread": 1.0}

Every role's beat carries the same `formation`. The middle of the group goes
on that mark (the set fills in `origin` and `heading` from it; with no set,
write them), facing the house the way the dancers faced the camera, and each
person is placed from it by where they were in the picture (formation.py says
how, and what that can and cannot know). `drift` does not apply: nobody's
place is their own any more. The beat still says where the role's own walk
on ends and where it stands afterwards (`from` and `to` marks); how far the
formation puts them from those is in the plan, and the join covers it.

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
import footlock  # noqa: E402
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
        inside = [s for s in shots if s["last_frame"] >= first and s["first_frame"] <= last]
        whole = bool(inside) and inside[0]["first_frame"] <= first and last <= inside[-1]["last_frame"]
        # One shot; or shots that are one take the clip was only split into for its length.
        if not whole or (len(inside) > 1 and not all(s.get("part_of_a_long_shot") for s in inside)):
            raise ValueError(f"{where}: seconds {beat['from_s']} to {beat['to_s']} of \"{name}\" are not inside one shot (a cut falls between them)")
    else:
        number = int(beat["shot"])
        if not 1 <= number <= len(shots):
            raise ValueError(f"{where}: \"{name}\" has shots 1 to {len(shots)}, not {number}")
        inside = [shots[number - 1]]
        if not (inside[0]["first_frame"] <= first and last <= inside[0]["last_frame"]):
            raise ValueError(f"{where}: shot {number} of \"{name}\" runs from {inside[0]['first_frame'] / FPS:.2f} to {inside[0]['last_frame'] / FPS:.2f} s of the clip; {beat['from_s']} to {beat['to_s']} is not inside it")
    person = int(beat["person"]) if beat.get("person") is not None else None
    files = [motion_file(folder, shot["index"], person) for shot in inside]
    return {"clip": name, "folder": folder, "shots": inside, "first": first, "last": last, "files": [path for path, _ in files], "person": files[0][1].get("person", person)}


def joined(sk, want: dict, name: str) -> tuple:
    """The motion of the shots a beat reaches into, on our skeleton, as one: (motion, first clip frame, report).

    More than one shot here is one take the clip was split into for its length. The camera did not cut, so the
    second part's world faces the way the first's did; only its middle starts from nothing again. So the second
    is slid (not turned) to carry on where the first was heading, and the pose at the split is eased."""
    import timeline

    out, reports, camera = None, [], []
    for shot, path in zip(want["shots"], want["files"]):
        answer = clip_file.read(path)
        motion, report = soma77.convert(answer, sk)
        camera = None if camera is None or not answer.get("camera_root") else camera + list(answer["camera_root"])
        if len(motion["root"]) != shot["last_frame"] - shot["first_frame"] + 1:
            raise ValueError(f"beat \"{name}\": the motion for shot {shot['index'] + 1} of \"{want['clip']}\" has {len(motion['root'])} frames, the shot has {shot['last_frame'] - shot['first_frame'] + 1}: the cuts changed since it was made")
        motion = {**motion, "root": [list(r) for r in motion["root"]], "rotations": [list(r) for r in motion["rotations"]], "contacts": [list(c) for c in motion["contacts"]]}
        reports.append(report)
        if out is None:
            out = motion
            continue
        last = len(out["root"]) - 1
        step = [(out["root"][last][a] - out["root"][last - 3][a]) / 3.0 for a in (0, 2)]
        motion = timeline.moved(motion, 0.0, out["root"][last][0] + step[0] - motion["root"][0][0], out["root"][last][2] + step[1] - motion["root"][0][2])
        soma77.blend_in(motion, out)
        for key in ("root", "rotations", "contacts"):
            out[key] = out[key] + motion[key]
    report = {
        "size_ours_over_theirs": round(sum(r["size_ours_over_theirs"] for r in reports) / len(reports), 4),
        "ours_vs_gemx_cm": {mark: {"typical": max(r["ours_vs_gemx_cm"][mark]["typical"] for r in reports), "worst": max(r["ours_vs_gemx_cm"][mark]["worst"] for r in reports)} for mark in reports[0]["ours_vs_gemx_cm"]},
        "floor_followed_cm": max(r.get("floor_followed_cm", 0.0) for r in reports),
        "camera_root": camera,  # where the camera saw the hips, if the worker said (newer ones do)
    }
    return out, want["shots"][0]["first_frame"], report


def handles_for(beat: dict, want: dict, before: int, after: int) -> tuple:
    """How many frames of the clip the beat brings either side of the stretch asked for, for the joins to use up."""
    on = beat.get("handles", True) is not False
    return min(before if on else 0, want["first"] - want["shots"][0]["first_frame"]), min(after if on else 0, want["shots"][-1]["last_frame"] - want["last"])


CREWS: dict = {}  # a crew is worked out once, however many of its roles are planned in one go


def crew(sk, beat: dict, before: int, after: int, videos: str = None) -> dict:
    """Everyone in a beat's `formation`, set down together on the stage for the beat's frames (with its handles)."""
    import formation
    import timeline

    form = beat.get("formation") or {}
    people = [int(p) for p in form.get("people") or []]
    if len(people) < 2 or len(set(people)) != len(people):
        raise ValueError(f"beat \"{beat['name']}\": a formation names the people in it, two or more (\"people\": [1, 2, 3])")
    if form.get("origin") is None:
        raise ValueError(f"beat \"{beat['name']}\": a formation says where the middle of the group goes: `at` a mark of the set, or `origin` [x, z] and `heading`")
    wants = {p: find({**beat, "person": p}, videos) for p in people}
    one = wants[people[0]]
    lead, tail = handles_for(beat, one, before, after)
    first, last = one["first"] - lead, one["last"] + tail
    locking = footlock.wanted(beat.get("lock_feet"))
    key = timeline.digest({"clip": one["clip"], "frames": [first, last], "form": form, "lock": locking, "hold": formation.holding_the_group(), "files": {str(p): [os.path.getmtime(f) for f in wants[p]["files"]] for p in people}})
    if key in CREWS:
        return CREWS[key]
    motions, sizes, reports, seen = {}, {}, {}, {}
    for p in people:
        whole, base, report = joined(sk, wants[p], beat["name"])
        motions[p] = timeline.cut(whole, first - base, last - base)
        sizes[p], reports[p] = report["size_ours_over_theirs"], report
        seen[p] = report["camera_root"][first - base : last - base + 1] if report.get("camera_root") else None
    where, notes = formation.measure(one["folder"], people, first, last, motions, sizes, sk, camera=seen if all(seen.values()) else None)
    placed = formation.stand(sk, motions, where, sizes, tuple(form["origin"]), float(form.get("heading") or 0.0), float(form.get("spread") or 1.0), float(form["travel"]) if form.get("travel") is not None else 1.0)
    feet = {}
    for p in people:
        # Held to a place in the group, a body is nudged all the time. With its feet locked the nudging waits for a step.
        feet[p] = {"locked": locking, "slid_cm_per_s": footlock.slide(sk, placed[p])["cm_per_s"]}
        if locking:
            in_formation = placed[p]
            placed[p], done = footlock.lock(sk, in_formation)
            feet[p].update({**done,
                            "from_its_place_in_the_group_cm_at_most": round(100.0 * max(math.hypot(a[0] - b[0], a[2] - b[2]) for a, b in zip(placed[p]["root"], in_formation["root"])), 1)})
    CREWS[key] = {"placed": placed, "people": people, "frames": [first, last], "handles": [lead, tail], "reports": reports, "feet": feet, "notes": notes, "closest": formation.closest(sk, placed), "group": formation.group_drift(sk, placed),
                  "places_in_the_group_m": {str(p): {"at_the_start": [round(c, 2) for c in where[p][lead]], "at_the_end": [round(c, 2) for c in where[p][len(where[p]) - 1 - tail]]} for p in people}}
    return CREWS[key]


def piece(stage, beat: dict, first: int, piece_card: dict, sk, before: int = 0, after: int = 0, videos: str = None) -> tuple:
    """A video beat as a finished piece of a shot. `before` and `after` are the frames the seams at its two ends
    will replace. Fills in `piece_card` (what plan.json keeps); returns (the motion, placed; the marks; its frames)."""
    import timeline

    path = stage.path
    if beat.get("from_m") is None or beat.get("to_m") is None:
        raise ValueError(f"beat \"{beat['name']}\": a video beat says where it is on the path (from_m, to_m), or names a mark (at, or from and to)")
    x0, z0, h0 = path.at(float(beat["from_m"]))
    x1, z1, _ = path.at(float(beat["to_m"]))
    travels = math.hypot(x1 - x0, z1 - z0) > 0.05
    drift = beat.get("drift") or "keep"
    if drift not in ("keep", "flatten"):
        raise ValueError(f"beat \"{beat['name']}\": drift is keep or flatten")
    eased, turn, group, feet = (0.0, 0.0), 0.0, None, None
    if beat.get("formation"):
        # One of a crew: everyone is set down together, each where the picture had them in the group.
        if beat.get("person") is None or int(beat["person"]) not in [int(p) for p in beat["formation"].get("people") or []]:
            raise ValueError(f"beat \"{beat['name']}\": in a formation the beat says which of its people this role is (\"person\")")
        want = find(beat, videos)
        group = crew(sk, beat, before, after, videos)
        lead, tail = group["handles"]
        placed = group["placed"][int(beat["person"])]
        motion = {**placed, "root": [list(r) for r in placed["root"]], "rotations": [list(r) for r in placed["rotations"]], "contacts": [list(c) for c in placed["contacts"]]}
        report = group["reports"][int(beat["person"])]
        feet = group["feet"][int(beat["person"])]
        count = len(motion["root"]) - 1
        a, b = lead, count - tail
    else:
        want = find(beat, videos)
        whole, base, report = joined(sk, want, beat["name"])
        # Handles: frames of the clip either side of the stretch, for the seams' tweens to take the place of.
        lead, tail = handles_for(beat, want, before, after)
        motion = timeline.cut(whole, want["first"] - lead - base, want["last"] + tail - base)
        motion = {**motion, "root": [list(r) for r in motion["root"]], "rotations": [list(r) for r in motion["rotations"]], "contacts": [list(c) for c in motion["contacts"]]}
        count = len(motion["root"]) - 1
        a, b = lead, count - tail  # the stretch asked for, as frames of the piece
        # Where the shot wants it: the stretch begins at from_m on the path, and ends (if it travels) at to_m.
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
        off = (x1 - motion["root"][b][0], z1 - motion["root"][b][2])  # from where it ends to where the shot wants it
        if travels or drift == "flatten":
            for f, root in enumerate(motion["root"]):
                share = min(1.0, max(0.0, (f - a) / float(max(1, b - a))))
                root[0], root[2] = round(root[0] + off[0] * share, 5), round(root[2] + off[1] * share, 5)
            eased = off
        feet = {"locked": footlock.wanted(beat.get("lock_feet")), "slid_cm_per_s": footlock.slide(sk, motion)["cm_per_s"]}
        if feet["locked"]:
            motion, done = footlock.lock(sk, motion)
            feet.update(done)
    begins, ends = motion["root"][a], motion["root"][b]
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
            "clip_shot": want["shots"][0]["index"] + 1,
            "clip_shots": [shot["index"] + 1 for shot in want["shots"]],
            "person": want["person"],
            "clip_frames": [want["first"] - lead, want["last"] + tail],
            "asked_for": [a, b],
            "handles": [lead, tail],
            "placement": {"x": round(x0, 4), "z": round(z0, 4), "turned_deg": round(turn, 2), "travels": travels},
            "drift": drift,
            "drift_taken_out_cm": round(100.0 * math.hypot(*eased), 1),
            "starts_from_its_mark_cm": round(100.0 * math.hypot(begins[0] - x0, begins[2] - z0), 1),
            "ends_from_its_mark_cm": round(100.0 * math.hypot(ends[0] - x1, ends[2] - z1), 1),
            "ours_vs_gemx_cm": report["ours_vs_gemx_cm"],
            "feet": feet,
            "video": timeline.digest({"root": motion["root"], "rotations": motion["rotations"], "contacts": motion["contacts"]}),
        }
    )
    if group:
        piece_card["formation"] = {**beat["formation"], "starts_at": [round(begins[0], 3), round(begins[2], 3)], "ends_at": [round(ends[0], 3), round(ends[2], 3)],
                                   "places_in_the_group_m": group["places_in_the_group_m"], "closest": group["closest"], "read_from": group["notes"],
                                   "slides_as_one": {k: v for k, v in group["group"].items() if k != "moments"}}
    return motion, marks, count
