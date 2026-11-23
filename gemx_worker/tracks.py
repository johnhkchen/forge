"""Who is who in a shot: boxes from a person detector, followed from frame to frame.

The detector (YOLOX, in models/gemx_model.py) says where people are on each
frame. This file turns that into tracks: one person, one number, one box a
frame. It is a simple tracker on purpose. Each person's next box is guessed
from where they were and how fast they were going, and the detections that
overlap those guesses best are theirs. A person the detector loses for a
moment (a spin, someone crossing in front) comes back as a new track, so
afterwards pieces that follow one another closely, in nearly the same place
and in the same clothes, are joined back into one.

Plain Python: no numpy, no model. The worker and the repo's offline tests both
use it, and so does the page that suggests the same person across cuts
(`alike`, on the clothing colours the worker measures).

Boxes are [x1, y1, x2, y2] in pixels of the clip.
"""

from __future__ import annotations

MATCH_OVERLAP = 0.25  # a detection belongs to a track if it overlaps its guessed box at least this much
NEW_TRACK_SCORE = 0.5  # the detector must be this sure before a detection starts a track of its own
LOST_FRAMES = 20  # a track not seen for this long is closed
JOIN_GAP_FRAMES = 45  # two pieces at most this far apart in time can be one person
JOIN_ALIKE = 0.5  # ...if their clothes are at least this alike (0..1)
JOIN_NEAR = 0.9  # ...and the second starts within this many box-heights of where the first ended


def area(box) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def overlap(a, b) -> float:
    """Intersection over union of two boxes, 0..1."""
    inner = area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))
    total = area(a) + area(b) - inner
    return inner / total if total > 0 else 0.0


def alike(a, b) -> float:
    """How alike two clothing-colour histograms are, 0..1 (the share they have in common)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    sa, sb = sum(a), sum(b)
    if sa <= 0 or sb <= 0:
        return 0.0
    return sum(min(x / sa, y / sb) for x, y in zip(a, b))


class Tracker:
    """Follows people through one shot. Call `see` once per detected frame, in order; read `tracks` at the end."""

    def __init__(self, match: float = MATCH_OVERLAP, lost: int = LOST_FRAMES, new_score: float = NEW_TRACK_SCORE):
        self.match, self.lost, self.new_score = match, lost, new_score
        self.tracks: dict = {}  # id -> {frame: box}
        self.live: dict = {}  # id -> (last frame, last box, velocity per frame)
        self.next_id = 1

    def guess(self, track_id: int, frame: int):
        last, box, speed = self.live[track_id]
        ahead = min(frame - last, 5)  # a guess more than a few frames ahead runs away
        return [box[i] + speed[i % 2] * ahead for i in range(4)]

    def see(self, frame: int, boxes, scores) -> None:
        for track_id in [t for t, (last, _, _) in self.live.items() if frame - last > self.lost]:
            del self.live[track_id]
        pairs = []
        for track_id in self.live:
            guessed = self.guess(track_id, frame)
            for d, box in enumerate(boxes):
                o = overlap(guessed, box)
                if o >= self.match:
                    pairs.append((o, track_id, d))
        taken_tracks, taken_boxes = set(), set()
        for _, track_id, d in sorted(pairs, reverse=True):
            if track_id in taken_tracks or d in taken_boxes:
                continue
            taken_tracks.add(track_id)
            taken_boxes.add(d)
            last, before, speed = self.live[track_id]
            box = [float(c) for c in boxes[d]]
            step = max(1, frame - last)
            now = [((box[0] + box[2]) - (before[0] + before[2])) / 2.0 / step, ((box[1] + box[3]) - (before[1] + before[3])) / 2.0 / step]
            self.live[track_id] = (frame, box, [0.5 * speed[0] + 0.5 * now[0], 0.5 * speed[1] + 0.5 * now[1]])
            self.tracks[track_id][frame] = box
        for d, box in enumerate(boxes):
            if d in taken_boxes or scores[d] < self.new_score:
                continue
            box = [float(c) for c in box]
            self.tracks[self.next_id] = {frame: box}
            self.live[self.next_id] = (frame, box, [0.0, 0.0])
            self.next_id += 1


def join_pieces(tracks: dict, colors: dict, gap: int = JOIN_GAP_FRAMES) -> tuple:
    """Joins tracks that are one person seen in two stretches. `colors` is {track id: histogram} (may lack some).
    Returns (tracks, {kept id: [ids joined into it]})."""
    tracks = {t: dict(boxes) for t, boxes in tracks.items()}
    joined: dict = {}
    while True:
        best = None
        for a, boxes_a in tracks.items():
            end = max(boxes_a)
            for b, boxes_b in tracks.items():
                start = min(boxes_b)
                if a == b or not 0 < start - end <= gap:
                    continue
                last, first = boxes_a[end], boxes_b[start]
                tall = max(1.0, last[3] - last[1], first[3] - first[1])
                apart = (((last[0] + last[2]) - (first[0] + first[2])) ** 2 + ((last[1] + last[3]) - (first[1] + first[3])) ** 2) ** 0.5 / 2.0 / tall
                same = alike(colors.get(a), colors.get(b)) if a in colors and b in colors else JOIN_ALIKE
                if apart > JOIN_NEAR or same < JOIN_ALIKE:
                    continue
                score = same - apart - (start - end) / (10.0 * gap)
                if best is None or score > best[0]:
                    best = (score, a, b)
        if best is None:
            return tracks, joined
        _, a, b = best
        tracks[a].update(tracks.pop(b))
        joined.setdefault(a, []).extend([b] + joined.pop(b, []))


def fill(boxes: list) -> tuple:
    """One box for every frame: gaps (None) filled in a straight line between the boxes either side, the first
    and last box held to the ends. Returns (boxes, seen flags)."""
    seen = [box is not None for box in boxes]
    known = [i for i, s in enumerate(seen) if s]
    if not known:
        raise ValueError("this person is not seen on any frame of the shot")
    out = [None] * len(boxes)
    for i in range(len(boxes)):
        if seen[i]:
            out[i] = [float(c) for c in boxes[i]]
            continue
        before = [k for k in known if k < i]
        after = [k for k in known if k > i]
        if not before:
            out[i] = [float(c) for c in boxes[after[0]]]
        elif not after:
            out[i] = [float(c) for c in boxes[before[-1]]]
        else:
            a, b = before[-1], after[0]
            t = (i - a) / float(b - a)
            out[i] = [boxes[a][k] + (boxes[b][k] - boxes[a][k]) * t for k in range(4)]
    return out, seen


def spread(tracks: dict, stride: int, first: int, last: int) -> dict:
    """Tracks made from every `stride`-th frame, given a box on the frames between (a straight line between two
    detections that follow one another; nothing is made up across a real gap)."""
    if stride <= 1:
        return tracks
    out = {}
    for track_id, boxes in tracks.items():
        frames = sorted(boxes)
        full = dict(boxes)
        for a, b in zip(frames, frames[1:]):
            if b - a == stride:
                for f in range(a + 1, b):
                    t = (f - a) / float(b - a)
                    full[f] = [boxes[a][k] + (boxes[b][k] - boxes[a][k]) * t for k in range(4)]
        out[track_id] = {f: box for f, box in full.items() if first <= f <= last}
    return out


def people_of(tracks: dict, first: int, last: int, width: int, height: int, keep: int = 8, least_share: float = 0.05) -> list:
    """The shot's people, biggest first and numbered 1, 2, 3: each with a box (or None) for every frame of the shot.
    Someone seen on fewer than `least_share` of the frames (and fewer than 5) is left out; at most `keep` are kept."""
    count = last - first + 1
    rows = []
    for track_id, boxes in tracks.items():
        seen = sorted(f for f in boxes if first <= f <= last)
        if len(seen) < max(5, least_share * count) and len(seen) < count:
            continue
        total = sum(area(boxes[f]) for f in seen)
        rows.append((total, track_id, seen))
    people = []
    for number, (total, track_id, seen) in enumerate(sorted(rows, reverse=True)[:keep], start=1):
        boxes = tracks[track_id]
        people.append(
            {
                "id": number,
                "track": track_id,
                "frames_seen": len(seen),
                "first_seen": seen[0],
                "last_seen": seen[-1],
                "share_of_picture": round(total / len(seen) / float(width * height), 4),
                "boxes": [[int(round(c)) for c in boxes[f]] if f in boxes else None for f in range(first, last + 1)],
            }
        )
    return people


def key_frames(people: list, first: int, last: int, count: int = 3) -> list:
    """A few frames to show the shot by: spread over it, each moved to a nearby frame where the most people are seen."""
    span = last - first
    wanted = [first + round(span * share) for share in ([0.5] if count == 1 else [0.15 + 0.7 * i / (count - 1) for i in range(count)])]
    out = []
    for f in wanted:
        reach = max(1, span // 12)
        near = range(max(first, f - reach), min(last, f + reach) + 1)
        best = max(near, key=lambda g: (sum(1 for p in people if p["boxes"][g - first]), -abs(g - f)))
        if best not in out:
            out.append(best)
    return out


def thumb_frames(person: dict, first: int, count: int = 2) -> list:
    """The frames to cut a person's small pictures from: spread over the stretch they are seen in."""
    seen = [first + i for i, box in enumerate(person["boxes"]) if box]
    if not seen:
        return []
    picks = [seen[len(seen) // 3], seen[(2 * len(seen)) // 3]][:count]
    return sorted(set(picks))
