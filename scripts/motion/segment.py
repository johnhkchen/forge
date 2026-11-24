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
sys.path.insert(0, HERE)
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


def beat_frames(beat: dict, before: dict = None, after: dict = None) -> int:
    """How many frames a beat plays for, the way plan_shot.py and timeline.py count them. A beat from a video
    also brings the frames the joins at its two ends use up, so it needs to know its neighbours."""
    source = beat.get("source", "poses")
    if source == "poses":
        return sum(4 * int(m["tokens"]) - 7 - int(m.get("early_frames", 0)) for m in beat.get("moves") or [])
    if source == "video":
        import timeline

        def takes(a: dict, b: dict) -> tuple:
            from_end = int(a["join_out_frames"]) if a.get("join_out_frames") is not None else timeline.TAKE_FROM_END[a.get("source", "poses")]
            from_start = int(b["join_in_frames"]) if b.get("join_in_frames") is not None else timeline.TAKE_FROM_START
            return timeline.tween_length(from_end, from_start)

        if beat.get("from_s") is None or beat.get("to_s") is None:
            raise SegmentProblem(f"beat \"{beat['name']}\": a video beat says which seconds of the clip it wants (from_s, to_s)")
        handles = beat.get("handles", True) is not False
        lead = takes(before, beat)[1] if before and handles else 0
        tail = takes(beat, after)[0] if after and handles else 0
        return int(round(float(beat["to_s"]) * FPS)) - int(round(float(beat["from_s"]) * FPS)) + lead + tail
    return int(beat["frames"]) if beat.get("frames") else int(round(float(beat["seconds"]) * FPS))


def frames_of(shot: dict) -> list:
    """Each beat's length in frames, in order."""
    beats = shot["beats"]
    return [beat_frames(beat, beats[i - 1] if i else None, beats[i + 1] if i + 1 < len(beats) else None) for i, beat in enumerate(beats)]


def spans(shot: dict) -> dict:
    """{beat name: (first frame, last frame)} for a role's shot list."""
    out, frame = {}, 0
    for beat, count in zip(shot["beats"], frames_of(shot)):
        out[beat["name"]] = (frame, frame + count)
        frame += count
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
            if (beat.get("formation") or {}).get("at"):
                beat["formation"]["at"] = marked(beat["formation"]["at"])
            for move in beat.get("moves") or []:
                if move.get("at"):
                    move["at"] = marked(move["at"])
            if beat.get("prompt"):
                try:
                    beat["prompt"] = beat["prompt"].format(**sentences)
                except KeyError as e:
                    raise SegmentProblem(f"{role}, beat \"{beat['name']}\": the segment has no sentence called {e}") from None
        shots[role] = shot

    # People who dance one formation have to mean the same one: the same clip, seconds, people and mark.
    crews = {}
    for role, shot in shots.items():
        for beat in shot["beats"]:
            if beat.get("formation"):
                crews.setdefault(beat["name"], {})[role] = json.dumps([beat.get("clip"), beat.get("from_s"), beat.get("to_s"), beat["formation"]], sort_keys=True)
                if beat.get("person") not in (beat["formation"].get("people") or []):
                    raise SegmentProblem(f"{role}, beat \"{beat['name']}\": its person ({beat.get('person')}) is not one of the formation's people {beat['formation'].get('people')}")
    for name, by_role in crews.items():
        if len(set(by_role.values())) > 1:
            raise SegmentProblem(f"the beat \"{name}\" is one formation, but the roles do not ask for the same clip, seconds, people and mark: {', '.join(by_role)}")
        people = [next(b for b in shots[role]["beats"] if b["name"] == name)["person"] for role in by_role]
        if len(set(people)) != len(people):
            raise SegmentProblem(f"the beat \"{name}\": two roles are the same person of the clip ({people})")

    lengths = {role: sum(frames_of(shot)) for role, shot in shots.items()}
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
    frames = sum(frames_of(next(iter(shots.values()))))
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
        beats = ", ".join(f"{b['name']} ({n})" for b, n in zip(shot["beats"], frames_of(shot)))
        print(f"SEGMENT {role} ({made['take']['roles'][role]['character']}): {beats}")
    print(f"SEGMENT {made['take']['segment']} on the set \"{made['take']['set']}\": {len(made['shots'])} roles, {made['take']['frames']} frames, {made['take']['seconds']} s")


if __name__ == "__main__":
    main()
