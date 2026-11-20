"""A segment: a shot list written once, for roles and marks, and played by whoever you cast.

    python3 scripts/motion/segment.py <take plan: motion/shots/<name>.json> <take folder: shots/<name>>

A talk show does the same few things every night: a guest walks on, shakes
the host's hand, sits down. A segment (motion/segments/<name>.json) is that
routine as a template. It holds one shot list per role, written in marks
(`start_mark`, and beats that say `to` or `at` a mark), never coordinates, so
it plays on any set that has those marks. The only things a take adds are who
plays each role and, if you like, other sentences for the walks:

    {"name": "studio-guest-entrance", "set": "studio", "segment": "guest-entrance",
     "roles": {"host": "young-lincoln-frontier-wrestler", "guest": "roosevelt-wrestler-1890s"},
     "sentences": {"guest_walks_on": "A person strides forward, waving."},
     "marks": {"couch_1": "couch_2"}}

`marks` swaps one mark for another (sit the guest in the far seat).

This writes, into the take folder:
    <role>/shotlist.json   that role's shot list, ready for plan_shot.py (which stands it on the set)
    take.json              who is in the take, on which set, and where each role's files are

and checks what a template must get right for two people to share a stage:
every role's shot is the same length, and beats listed under `together` (the
handshake) start and end on the same frames for everyone in them.

Plain Python: no Blender, no numpy.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SEGMENTS = os.path.join(REPO, "motion", "segments")
FPS = 30


class SegmentProblem(ValueError):
    """Something wrong with a segment or with the take that uses it."""


def load(name: str) -> dict:
    path = name if os.path.exists(name) else os.path.join(SEGMENTS, name + ".json")
    if not os.path.exists(path):
        have = sorted(f[:-5] for f in os.listdir(SEGMENTS) if f.endswith(".json")) if os.path.isdir(SEGMENTS) else []
        raise SegmentProblem(f"no segment named {name!r} (segments: {', '.join(have) or 'none'})")
    with open(path) as f:
        return json.load(f)


def beat_frames(beat: dict) -> int:
    """How many frames a beat plays for, the way plan_shot.py and timeline.py count them."""
    if beat.get("source", "poses") == "poses":
        return sum(4 * int(m["tokens"]) - 7 - int(m.get("early_frames", 0)) for m in beat.get("moves") or [])
    return int(beat["frames"]) if beat.get("frames") else int(round(float(beat["seconds"]) * FPS))


def spans(shot: dict) -> dict:
    """{beat name: (first frame, last frame)} for a role's shot list."""
    out, frame = {}, 0
    for beat in shot["beats"]:
        out[beat["name"]] = (frame, frame + beat_frames(beat))
        frame += beat_frames(beat)
    return out


def expand(template: dict, take: dict) -> dict:
    """{role: shot list} for a take of a segment: the sentences filled in, the marks swapped, and the timing checked."""
    roles = take.get("roles") or {}
    missing = [r for r in template["needs"]["roles"] if r not in roles]
    if missing:
        raise SegmentProblem(f"the segment \"{template['name']}\" needs someone to play: {', '.join(missing)}")
    sentences = dict(template.get("sentences") or {})
    unknown = sorted(set(take.get("sentences") or {}) - set(sentences))
    if unknown:
        raise SegmentProblem(f"the segment has no sentence called {', '.join(unknown)} (it has: {', '.join(sorted(sentences))})")
    sentences.update(take.get("sentences") or {})
    swap = take.get("marks") or {}
    unknown = sorted(set(swap) - set(template["needs"]["marks"]))
    if unknown:
        raise SegmentProblem(f"the segment does not use the mark {', '.join(unknown)} (it uses: {', '.join(template['needs']['marks'])})")

    def marked(name):
        return swap.get(name, name)

    shots = {}
    for role in template["needs"]["roles"]:
        shot = copy.deepcopy(template["roles"][role])
        shot["start_mark"] = marked(shot["start_mark"])
        for beat in shot["beats"]:
            for key in ("from", "to", "at"):
                if beat.get(key):
                    beat[key] = marked(beat[key])
            for move in beat.get("moves") or []:
                if move.get("at"):
                    move["at"] = marked(move["at"])
            if beat.get("prompt"):
                try:
                    beat["prompt"] = beat["prompt"].format(**sentences)
                except KeyError as e:
                    raise SegmentProblem(f"{role}, beat \"{beat['name']}\": the segment has no sentence called {e}") from None
        shots[role] = shot

    lengths = {role: sum(beat_frames(b) for b in shot["beats"]) for role, shot in shots.items()}
    if len(set(lengths.values())) > 1:
        raise SegmentProblem("the roles' shots are not the same length: " + ", ".join(f"{r} {n} frames" for r, n in lengths.items()))
    for name in template.get("together") or []:
        at = {role: spans(shot)[name] for role, shot in shots.items() if name in spans(shot)}
        if len(at) < 2 or len(set(at.values())) > 1:
            raise SegmentProblem(f"the beat \"{name}\" is done together, but: " + ", ".join(f"{r} frames {a}-{b}" for r, (a, b) in at.items()))
    return shots


def write_take(plan_file: str, folder: str) -> dict:
    with open(plan_file) as f:
        take = json.load(f)
    template = load(take["segment"])
    shots = expand(template, take)
    for role, shot in shots.items():
        os.makedirs(os.path.join(folder, role), exist_ok=True)
        text = json.dumps(shot, indent=1) + "\n"
        path = os.path.join(folder, role, "shotlist.json")
        if not os.path.exists(path) or open(path).read() != text:
            with open(path, "w") as f:
                f.write(text)
    record_path = os.path.join(folder, "take.json")
    record = {}
    if os.path.exists(record_path):
        with open(record_path) as f:
            record = json.load(f)
    frames = sum(beat_frames(b) for b in next(iter(shots.values()))["beats"])
    record.update({
        "name": take["name"], "title": template["title"], "about": template["about"], "set": take["set"], "segment": template["name"],
        "fps": FPS, "frames": frames + 1, "seconds": round(frames / FPS, 2),
        "roles": {role: {"character": take["roles"][role], "folder": role} for role in shots},
        "together": {name: list(spans(next(iter(shots.values())))[name]) for name in template.get("together") or []},
    })
    with open(record_path, "w") as f:
        json.dump(record, f, indent=1)
    return {"shots": shots, "take": record}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan")
    parser.add_argument("folder")
    args = parser.parse_args()
    try:
        made = write_take(args.plan, args.folder)
    except SegmentProblem as e:
        sys.exit(f"segment: {e}")
    for role, shot in made["shots"].items():
        beats = ", ".join(f"{b['name']} ({beat_frames(b)})" for b in shot["beats"])
        print(f"SEGMENT {role} ({made['take']['roles'][role]['character']}): {beats}")
    print(f"SEGMENT {made['take']['segment']} on the set \"{made['take']['set']}\": {len(made['shots'])} roles, {made['take']['frames']} frames, {made['take']['seconds']} s")


if __name__ == "__main__":
    main()
