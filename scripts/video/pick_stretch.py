"""Which 10 to 15 seconds of a clip's dance make the best short film: every stretch scored, the best few listed.

    python3 scripts/video/pick_stretch.py <shot folder: shots/video-<clip>> [--shortest 10] [--longest 15]
        [--keep-off 1.5] [--top 6] [--json out.json]

A short segment (for a restyle, a trailer, a loop on a page) wants a stretch
that is lively, that reads from the front, that has the dancer's arms up over
her head now and then, a turn if there is one, and that starts and ends on a
pose you could freeze on. It must keep clear of a seam, where two of the
model's pieces were joined and the hands can jump. All of that is in the
shot's motion.json, so it is measured, not guessed:

  lively     how fast the hands and feet move, against the hips (m/s), on
             average over the stretch
  overhead   the share of the stretch with a wrist above the top of the head
  turn       the most the hips' heading swings inside the stretch (degrees):
             a turn, or a quarter-turn to show a profile
  still      how still the whole body is at the first and last frames
             (m/s, low is good): a clean pose to start and end on
  travel     the furthest the hips get from where they start (m): a stage has
             only so much room
  seam       seconds to the nearest seam (a join between two pieces)

Each stretch's ends are moved to the stillest frame within half a second, so
it starts and ends on a held pose. Then every stretch gets one score, and the
best that do not overlap are listed.

Plain Python, no numpy.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
from soma import Skeleton, heading_of  # noqa: E402

LIMBS = ["LeftHand", "RightHand", "LeftFoot", "RightFoot"]
BODY = ["Head", "Chest", "LeftHand", "RightHand", "LeftForeArm", "RightForeArm", "LeftShin", "RightShin", "LeftFoot", "RightFoot"]
SNAP_S = 0.5  # an end may move this far to land on a still frame
STEP_S = 0.5  # stretches start every this many seconds


def world(sk: Skeleton, motion: dict) -> list:
    """Every frame's joint positions, by the skeleton's joint order, and the hips' heading (degrees)."""
    order = [motion["joints"].index(name) for name in sk.joints]
    out = []
    for root, row in zip(motion["root"], motion["rotations"]):
        pos, rot = sk.fk(root, [tuple(row[4 * j: 4 * j + 4]) for j in order])
        out.append((pos, heading_of(rot[0])))
    return out


def per_frame(sk: Skeleton, frames: list, fps: int) -> dict:
    """What each frame says: limb speed against the hips, whole-body speed, a wrist overhead, the heading unwrapped."""
    ix = sk.index
    head_top = ix["Head"]
    n = len(frames)
    lively, still, overhead, heading, hips = [0.0] * n, [0.0] * n, [False] * n, [0.0] * n, []
    turned = 0.0
    for f in range(n):
        pos, h = frames[f]
        hips.append(pos[0])
        if f:
            d = h - frames[f - 1][1]
            d = (d + 180.0) % 360.0 - 180.0
            turned += d
        heading[f] = turned
        # a wrist above the head (its joint is low in the skull, so 12 cm over it counts as the top)
        top = pos[head_top][1] + 0.12
        overhead[f] = pos[ix["LeftHand"]][1] > top or pos[ix["RightHand"]][1] > top
        if 0 < f < n - 1:
            a, b = frames[f - 1][0], frames[f + 1][0]
            rel = []
            for name in LIMBS:
                j = ix[name]
                da = [(b[j][k] - b[0][k]) - (a[j][k] - a[0][k]) for k in range(3)]
                rel.append(math.sqrt(sum(x * x for x in da)) * fps / 2.0)
            lively[f] = sum(rel) / len(rel)
            body = []
            for name in BODY:
                j = ix[name]
                body.append(math.sqrt(sum((b[j][k] - a[j][k]) ** 2 for k in range(3))) * fps / 2.0)
            still[f] = sum(body) / len(body)
    lively[0], lively[-1] = lively[1], lively[-2]
    still[0], still[-1] = still[1], still[-2]
    return {"lively": lively, "still": still, "overhead": overhead, "heading": heading, "hips": hips}


def smooth(values: list, half: int) -> list:
    out = []
    for f in range(len(values)):
        lo, hi = max(0, f - half), min(len(values), f + half + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return out


def snap(still: list, at: int, reach: int, lo: int, hi: int) -> int:
    """The stillest frame within reach of `at`, kept inside [lo, hi]."""
    best = min(range(max(lo, at - reach), min(hi, at + reach) + 1), key=lambda f: still[f])
    return best


def measure(pf: dict, first: int, last: int, seams: list, fps: int) -> dict:
    span = range(first, last + 1)
    lively = sum(pf["lively"][f] for f in span) / len(span)
    overhead = sum(1 for f in span if pf["overhead"][f]) / len(span)
    hd = [pf["heading"][f] for f in span]
    turn = max(hd) - min(hd)
    still = (pf["still_s"][first] + pf["still_s"][last]) / 2.0
    h0 = pf["hips"][first]
    travel = max(math.hypot(pf["hips"][f][0] - h0[0], pf["hips"][f][2] - h0[2]) for f in span)
    seam = min([min(abs(s - first), abs(s - last)) / fps if not (first <= s <= last) else 0.0 for s in seams] or [999.0])
    return {"first_frame": first, "last_frame": last, "from_s": round(first / fps, 2), "to_s": round(last / fps, 2), "seconds": round((last - first) / fps, 2),
            "lively_m_per_s": round(lively, 3), "overhead_share": round(overhead, 3), "turn_deg": round(turn, 1), "still_ends_m_per_s": round(still, 3),
            "travel_m": round(travel, 2), "seam_s": round(seam, 2)}


def score(m: dict) -> float:
    """One number: lively and overhead count most, a turn helps (up to a half turn), still ends and staying put help."""
    return round(
        1.0 * m["lively_m_per_s"]
        + 1.5 * min(m["overhead_share"], 0.4)
        + 0.4 * min(m["turn_deg"], 180.0) / 180.0
        - 0.8 * m["still_ends_m_per_s"]
        - 0.15 * max(0.0, m["travel_m"] - 1.2),
        4,
    )


def candidates(pf: dict, seams: list, fps: int, shortest: float, longest: float, keep_off: float) -> list:
    n = len(pf["lively"])
    reach = int(SNAP_S * fps)
    out = []
    for length in (shortest, (shortest + longest) / 2.0, longest):
        start = 0
        while start + length * fps < n:
            a = snap(pf["still_s"], start, reach, 0, n - 1)
            b = snap(pf["still_s"], int(a + length * fps), reach, 0, n - 1)
            if shortest * fps - 1 <= b - a <= longest * fps:
                m = measure(pf, a, b, seams, fps)
                if m["seam_s"] >= keep_off:
                    m["score"] = score(m)
                    out.append(m)
            start += int(STEP_S * fps)
    return out


def best_apart(found: list, top: int) -> list:
    """The best stretches, none overlapping another already picked by more than a third."""
    picked = []
    for m in sorted(found, key=lambda m: -m["score"]):
        if all(min(m["last_frame"], p["last_frame"]) - max(m["first_frame"], p["first_frame"]) < (m["last_frame"] - m["first_frame"]) / 3 for p in picked):
            picked.append(m)
        if len(picked) == top:
            break
    return picked


def seam_frames(shot: str) -> list:
    """Every frame where two pieces of the shot were joined (checks.json's seams; source.json's joins)."""
    out = []
    for name, key in (("checks.json", "seams"), ("source.json", "joins")):
        path = os.path.join(shot, name)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            card = json.load(f)
        if key == "seams":
            for s in (card.get("seams") or {}).get("seams") or []:
                out += list(s["joins_at_frames"])
        else:
            for j in card.get("joins") or []:
                out += list(j.get("tween_frames") or [j["boundary_frame"]])
    return sorted(set(out))


def pick(shot: str, shortest: float = 10.0, longest: float = 15.0, keep_off: float = 1.5, top: int = 6, sk: Skeleton = None) -> dict:
    with open(os.path.join(shot, "motion.json")) as f:
        motion = json.load(f)
    fps = int(motion.get("fps", 30))
    sk = sk or Skeleton.load()
    pf = per_frame(sk, world(sk, motion), fps)
    pf["still_s"] = smooth(pf["still"], 3)
    seams = seam_frames(shot)
    found = candidates(pf, seams, fps, shortest, longest, keep_off)
    return {"shot": os.path.basename(os.path.normpath(shot)), "fps": fps, "frames": len(motion["root"]), "seams": seams,
            "looked_at": len(found), "best": best_apart(found, top)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("shot")
    p.add_argument("--shortest", type=float, default=10.0)
    p.add_argument("--longest", type=float, default=15.0)
    p.add_argument("--keep-off", type=float, default=1.5, help="seconds to keep clear of a seam")
    p.add_argument("--top", type=int, default=6)
    p.add_argument("--json")
    a = p.parse_args()
    out = pick(a.shot, a.shortest, a.longest, a.keep_off, a.top)
    print("STRETCH %s: %d frames, seams at %s, %d stretches looked at" % (out["shot"], out["frames"], out["seams"], out["looked_at"]))
    for n, m in enumerate(out["best"], 1):
        print("STRETCH %d. %.2f-%.2f s (%.1f s): score %.3f, lively %.2f m/s, arms overhead %.0f%%, turn %.0f deg, ends still %.2f m/s, travels %.2f m, %.1f s from a seam" % (
            n, m["from_s"], m["to_s"], m["seconds"], m["score"], m["lively_m_per_s"], 100 * m["overhead_share"], m["turn_deg"], m["still_ends_m_per_s"], m["travel_m"], m["seam_s"]))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
