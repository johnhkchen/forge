"""Who is in the clip, made ready for you to choose from; and the choice, checked before it is kept.

The worker's `people` answer says, shot by shot, who it found and followed.
This file does the rest on this Mac:

  pictures      the worker's small pictures are saved under videos/<name>/people/
  same person   people in different shots who wear the same colours get the
                same `person` number, so tapping someone in one shot can
                suggest them in the others. It is a suggestion from clothing
                colours and nothing cleverer: two dancers in the same outfit
                look the same to it, and a change of light can split one
                person in two. You confirm it on the page.
  reflections   a dance studio has mirrors. Someone smaller on screen who
                moves in step with someone bigger (left-right flipped beside
                a side mirror, the same way in a mirror behind) and wears the
                same colours is marked `reflection_of`. "Might be", not "is":
                a second dancer further back doing the same steps in the same
                outfit gets the mark too.

  people.json      what the page shows (boxes only on the frames it shows)
  people-raw.json  everything the worker said, minus the pictures: every
                   person's box on every frame, which the motion step sends back

The choice (choice.json) is one entry per shot: the number of the person to
follow there, or "skip". `clean` is the only way one gets written: the
gallery's save and `just video` both go through it.

Plain Python.
"""

from __future__ import annotations

import base64
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "gemx_worker"))
import clip as clip_file  # noqa: E402
from tracks import alike  # noqa: E402

SAME_PERSON = 0.6  # clothing colours at least this alike (0..1) count as the same person across shots
REFLECTION_SMALLER = 0.9  # a reflection is further away: its box is at most this tall beside the real one
REFLECTION_FRAMES = 20  # frames both must be seen on before anything is said
CAMERAS = {"still": "static", "moving": "background"}  # what the page calls it, and what GEM-X calls it


def pearson(a: list, b: list) -> float:
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    va, vb = sum((x - ma) ** 2 for x in a), sum((y - mb) ** 2 for y in b)
    if va < 1e-12 or vb < 1e-12:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def moves(person: dict, frames: list) -> tuple:
    """How a person's box moves from frame to frame, in units of their own height: (sideways, up and down)."""
    xs, ys = [], []
    for f in frames:
        a, b = person["boxes"][f], person["boxes"][f + 2]
        tall = max(1.0, a[3] - a[1])
        xs.append(((b[0] + b[2]) - (a[0] + a[2])) / 2.0 / tall)
        ys.append(((b[1] + b[3]) - (a[1] + a[3])) / 2.0 / tall)
    return xs, ys


def reflections(people: list) -> dict:
    """{person id: the id of whoever they might be a reflection of} for one shot's people."""
    out = {}
    for small in people:
        best = None
        for big in people:
            if big["id"] == small["id"] or big["id"] in out:
                continue
            both = [f for f in range(len(big["boxes"]) - 2) if big["boxes"][f] and big["boxes"][f + 2] and small["boxes"][f] and small["boxes"][f + 2]]
            if len(both) < REFLECTION_FRAMES:
                continue
            ratio = sum((small["boxes"][f][3] - small["boxes"][f][1]) / max(1.0, big["boxes"][f][3] - big["boxes"][f][1]) for f in both) / len(both)
            if ratio > REFLECTION_SMALLER:
                continue
            bx, by = moves(big, both)
            sx, sy = moves(small, both)
            sideways = math.sqrt(sum(x * x for x in bx) / len(bx))
            across, updown = pearson(bx, sx), pearson(by, sy)
            same_clothes = alike(big.get("colors"), small.get("colors")) >= 0.5
            # Two people moving about a room go opposite ways for a second or two all the time; a reflection also
            # wears what the person wears. So the clothes have to match before the movement is looked at.
            flipped = sideways > 0.004 and across < -0.6  # a mirror on a side wall: left is right
            in_step = updown > 0.5 and (across > 0.7 if sideways > 0.004 else updown > 0.75)  # a mirror behind
            if same_clothes and (flipped or in_step) and (best is None or abs(across) + updown > best[0]):
                best = (abs(across) + updown, big["id"])
        if best:
            out[small["id"]] = best[1]
    return out


def same_people(shots: list) -> None:
    """Gives every person a `person` number shared by whoever looks the same in other shots (clothing colours).
    Within one shot no two people share a number. Changes the shots in place."""
    known = []  # [colours summed, how many]
    for shot in shots:
        pairs = []
        for p, person in enumerate(shot["people"]):
            for k, (colours, count) in enumerate(known):
                score = alike(person.get("colors"), colours)
                if score >= SAME_PERSON:
                    # The real person before their reflection, the bigger before the smaller, when the clothes tie.
                    pairs.append((round(score, 1), 0 if person.get("reflection_of") else 1, person.get("share_of_picture", 0.0), -k, p, k))  # then the longest-known look
        taken_p, taken_k = set(), set()
        for _, _, _, _, p, k in sorted(pairs, reverse=True):
            if p in taken_p or k in taken_k:
                continue
            taken_p.add(p)
            taken_k.add(k)
            person = shot["people"][p]
            person["person"] = k + 1
            known[k] = [[a + b for a, b in zip(known[k][0], person["colors"])], known[k][1] + 1]
        for p, person in enumerate(shot["people"]):
            if p not in taken_p:
                known.append([list(person.get("colors") or []), 1])
                person["person"] = len(known)


def digest(answer: dict, folder: str) -> dict:
    """The worker's `people` answer, made into people.json, people-raw.json and the pictures. Returns people.json."""
    if answer.get("format") != "gemx-people/1":
        raise clip_file.Stop(f"the worker answered {answer.get('format')!r}, not a list of people")
    pictures = os.path.join(folder, "people")
    os.makedirs(pictures, exist_ok=True)

    def keep(name: str, data: str) -> str:
        with open(os.path.join(pictures, name), "wb") as f:
            f.write(base64.b64decode(data))
        return f"people/{name}"

    page_shots = []
    for shot in answer["shots"]:
        first = shot["first_frame"]
        marked = reflections(shot["people"])
        for person in shot["people"]:
            person["reflection_of"] = marked.get(person["id"])
        keys = [{"frame": k["frame"], "picture": keep(f"shot-{shot['index']:03d}-frame-{k['frame']:06d}.jpg", k.pop("jpeg"))} for k in shot["keyframes"]]
        shot["keyframes"] = keys
        for person in shot["people"]:
            person["thumbs"] = [keep(f"shot-{shot['index']:03d}-person-{person['id']}-{n}.jpg", t["jpeg"]) for n, t in enumerate(person["thumbs"])]
    same_people(answer["shots"])
    for shot in answer["shots"]:
        first = shot["first_frame"]
        page_shots.append(
            {
                "index": shot["index"],
                "first_frame": first,
                "last_frame": shot["last_frame"],
                "seconds": round((shot["last_frame"] - first + 1) / answer.get("fps", 30), 2),
                "width": shot["width"],
                "height": shot["height"],
                "keyframes": shot["keyframes"],
                "people": [
                    {
                        "id": p["id"],
                        "person": p["person"],
                        "reflection_of": p["reflection_of"],
                        "seen_share": round(p["frames_seen"] / float(shot["last_frame"] - first + 1), 2),
                        "share_of_picture": p["share_of_picture"],
                        "thumbs": p["thumbs"],
                        # Where they are on each of the frames the page shows (null if not seen on it).
                        "boxes": {str(k["frame"]): p["boxes"][k["frame"] - first] for k in shot["keyframes"]},
                    }
                    for p in shot["people"]
                ],
            }
        )
    clip_file.write(os.path.join(folder, "people-raw.json"), answer, indent=None)
    page = {"format": "forge-video-people/1", "shots": page_shots, "detector": answer.get("detector")}
    clip_file.write(os.path.join(folder, "people.json"), page)
    return page


# ---- the choice ------------------------------------------------------------------


def clean(body, people: dict) -> dict:
    """A choice as it will be kept, or ValueError saying what is wrong with it.

    {"shots": {"0": 2, "1": "skip", ...}, "camera": "still" | "moving"}: for every shot, the number of one of
    the people found in it, or "skip". Nothing else is let through."""
    if not isinstance(body, dict) or set(body) - {"shots", "camera"}:
        raise ValueError("a choice has `shots` and, if you like, `camera`: nothing else")
    camera = body.get("camera", "still")
    if camera not in CAMERAS:
        raise ValueError("camera is still or moving")
    picked = body.get("shots")
    if not isinstance(picked, dict):
        raise ValueError("`shots` says who to follow in each shot")
    known = {str(shot["index"]): {p["id"] for p in shot["people"]} for shot in people.get("shots") or []}
    if set(picked) != set(known):
        raise ValueError(f"one entry for every shot ({', '.join(sorted(known, key=int))}), no more and no fewer")
    out = {}
    for shot in sorted(known, key=int):
        who = picked[shot]
        if who == "skip":
            out[shot] = "skip"
        elif isinstance(who, int) and not isinstance(who, bool) and who in known[shot]:
            out[shot] = who
        else:
            raise ValueError(f"shot {shot}: pick one of the people found in it ({sorted(known[shot])}) or skip")
    if all(who == "skip" for who in out.values()):
        raise ValueError("every shot is skipped: there is nobody to follow")
    return {"format": "forge-video-choice/1", "camera": camera, "shots": out}


def save_choice(videos: str, name: str, body) -> str:
    """Checks a choice and writes videos/<name>/choice.json. The only file this can ever write."""
    if not isinstance(name, str) or not clip_file.NAME.match(name):
        raise ValueError("no such clip")
    folder = os.path.join(os.path.realpath(videos), name)
    if os.path.realpath(folder) != folder or not os.path.isdir(folder):
        raise ValueError("no such clip")
    people = clip_file.read(os.path.join(folder, "people.json"))
    if not people:
        raise ValueError("nobody has been found in this clip yet")
    choice = clean(body, people)
    choice["saved"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path = os.path.join(folder, "choice.json")
    if os.path.islink(path):
        raise ValueError("choice.json is not a plain file")
    clip_file.write(path, choice)
    return path


def load_choice(folder: str) -> dict:
    """The saved choice if it still fits the people found, else None."""
    choice, people = clip_file.read(os.path.join(folder, "choice.json")), clip_file.read(os.path.join(folder, "people.json"))
    if not choice or not people:
        return None
    try:
        return clean({"shots": choice.get("shots"), "camera": choice.get("camera", "still")}, people)
    except ValueError:
        return None
