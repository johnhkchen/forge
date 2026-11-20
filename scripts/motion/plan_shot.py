"""Turns a shot list into the MotionBricks worker's input.

    python3 scripts/motion/plan_shot.py <shot folder> [--brief motion/shots/<name>.json] [--poses motion/poses.json]

Reads <shot>/shotlist.json (what Choreograph wrote) and the pose library.
Draws a smooth curve through the shot list's path points, then for every move
stands the named pose on that curve: at_m metres along it, side_m to its left,
facing along the curve plus facing_deg. A pose the character passes through at
speed is sent as four poses 1/30 s apart, sliding along the curve at that speed
and easing toward the next pose of its gait, so the motion model knows how the
body is moving there, not only where it is.

A shot whose beats all come from our poses is made in one go. If any beat
comes from somewhere else (`"source": "text"`), the shot is made in pieces and
joined: see timeline.py, which this hands the planning to.

Writes:
    <shot>/request.json   the worker's input (seed pose and targets); for a
                          shot made in pieces, <shot>/cache/<hash>.request.json
                          per piece instead
    <shot>/plan.json      where and when each move should end, for the checks:
                          frames, ground points, headings, pins, the curve,
                          and the set (ledge, roof, wall) as plain blocks,
                          stood along the same curve from the brief's `set`

Nothing here reads a motion clip. Every rotation it sends comes from
motion/poses.json.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from soma import REPO, Skeleton, add, heading_of, qconj, qmul, qrot, qslerp, yaw  # noqa: E402

FPS = 30
STEP_M = 0.02  # spacing of the points the curve is measured with
PIN_JOINT = {"left_hand": "LeftHand", "right_hand": "RightHand", "left_foot": "LeftFoot", "right_foot": "RightFoot"}
BLOCK_DEPTH = 0.3  # how thick the roof and ledge blocks are, below the walking surface


def catmull_rom(points, step=STEP_M):
    """A smooth curve through ground points [(x, z), ...], as closely spaced points."""
    if len(points) < 2:
        raise ValueError("a path needs at least two points")
    pts = [points[0]] + list(points) + [points[-1]]
    out = [tuple(points[0])]
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        span = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        pieces = max(2, int(math.ceil(span / step)))
        for k in range(1, pieces + 1):
            t = k / pieces
            out.append(
                tuple(
                    0.5
                    * (
                        2 * p1[a]
                        + (-p0[a] + p2[a]) * t
                        + (2 * p0[a] - 5 * p1[a] + 4 * p2[a] - p3[a]) * t * t
                        + (-p0[a] + 3 * p1[a] - 3 * p2[a] + p3[a]) * t * t * t
                    )
                    for a in (0, 1)
                )
            )
    return out


class Path:
    """A route over the ground you can ask "where am I after s metres?"."""

    def __init__(self, points):
        self.points = catmull_rom([(float(p["x"]), float(p["z"])) for p in points])
        self.along = [0.0]
        for a, b in zip(self.points, self.points[1:]):
            self.along.append(self.along[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        self.length = self.along[-1]

    def at(self, s: float):
        """(x, z, heading in degrees) after s metres. Past either end, the route runs straight on."""
        pts, along = self.points, self.along
        if s <= 0.0:
            i = 0
        elif s >= self.length:
            i = len(pts) - 2
        else:
            lo, hi = 0, len(along) - 1
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if along[mid] <= s:
                    lo = mid
                else:
                    hi = mid
            i = lo
        a, b = pts[i], pts[i + 1]
        seg = along[i + 1] - along[i]
        t = (s - along[i]) / seg
        dx, dz = (b[0] - a[0]) / seg, (b[1] - a[1]) / seg
        return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, math.degrees(math.atan2(dx, dz))


def stand(pose: dict, x: float, z: float, heading: float) -> dict:
    return {"rotations": pose["rotations"], "root": pose["root"], "at": [round(x, 4), 0.0, round(z, 4)], "heading": round(heading, 3)}


def blend(a: dict, b: dict, t: float) -> dict:
    """A pose part-way from a to b."""
    return {
        "root": [a["root"][i] + (b["root"][i] - a["root"][i]) * t for i in range(3)],
        "rotations": {j: list(qslerp(tuple(a["rotations"][j]), tuple(b["rotations"][j]), t)) for j in a["rotations"]},
    }


class Stage:
    """The pose library stood along a shot's path: where a move's pose goes, and what the body looks like there."""

    def __init__(self, shot: dict, library: dict, sk: Skeleton):
        self.poses, self.sk = library["poses"], sk
        self.path = Path(shot["path"])

    def placed(self, move: dict):
        """(x, z, the path's heading there, the heading the body faces) for a move or anything with at_m."""
        x, z, along = self.path.at(float(move["at_m"]))
        left = float(move.get("side_m", 0.0))
        # Left of a heading h is (cos h, -sin h) on the ground.
        x += left * math.cos(math.radians(along))
        z -= left * math.sin(math.radians(along))
        return x, z, along, along + float(move.get("facing_deg", 0.0))

    def target_poses(self, move: dict):
        pose = self.poses[move["pose"]]
        x, z, along, heading = self.placed(move)
        speed = float(move.get("speed_mps", 0.0))
        if speed <= 0.0:
            return [stand(pose, x, z, heading)]
        nxt = self.poses.get(pose.get("next") or "")
        step_seconds = float(pose.get("step_seconds") or 0.0)
        x0, z0, _ = self.path.at(float(move["at_m"]))
        out = []
        for k in range(4):
            t = k / FPS
            body = blend(pose, nxt, min(1.0, t / step_seconds)) if nxt and step_seconds > 0 else pose
            xk, zk, _ = self.path.at(float(move["at_m"]) + speed * t)
            out.append(stand(body, x + xk - x0, z + zk - z0, heading))
        return out

    def body_of(self, placed_pose: dict):
        """Joint positions and rotations of a placed pose, in the scene."""
        sk = self.sk
        turn = yaw(placed_pose["heading"])
        rotations = sk.rotation_list(placed_pose["rotations"])
        rotations[0] = qmul(turn, rotations[0])
        return sk.fk(add(tuple(placed_pose["at"]), qrot(turn, tuple(placed_pose["root"]))), rotations)

    def pin_points(self, pins: list, pos) -> dict:
        """Where the placed pose puts each pinned hand or foot, in the scene."""
        return {pin: [round(v, 4) for v in pos[self.sk.index[PIN_JOINT[pin]]]] for pin in pins or []}

    def mark(self, name: str, beat: str, move: dict, frame: int, placed_pose: dict) -> dict:
        """What the checks need to know about a moment: where the hips should be, facing where, and what is pinned."""
        sk = self.sk
        x, z, _, _ = self.placed(move)
        pos, rot = self.body_of(placed_pose)
        return {
            "name": name,
            "beat": beat,
            "pose": move["pose"],
            "frame": frame,
            # Where the hips themselves should be, and which way the pelvis should face:
            # the pose's own offset and turn, on top of where it stands.
            "x": round(pos[0][0], 4),
            "z": round(pos[0][2], 4),
            "heading": round(heading_of(qmul(rot[0], qconj(sk.rest_rot[0]))), 2),
            "stands_at": [round(x, 4), round(z, 4)],
            "speed_mps": float(move.get("speed_mps", 0.0)),
            "early_frames": int(move.get("early_frames", 0)),
            "pins": move.get("pins") or [],
            "pin_points": self.pin_points(move.get("pins"), pos),
            "hold_pins_frames": int(move.get("hold_pins_frames", 0)),
        }

    def target(self, name: str, move: dict) -> dict:
        """One move as a target of the worker's `inbetween`."""
        tokens, early = int(move["tokens"]), int(move.get("early_frames", 0))
        if not 6 <= tokens <= 16 or not 0 <= early <= 20:
            raise ValueError(f"{name}: tokens are 6..16 and early_frames 0..20")
        target = {"name": name, "poses": self.target_poses(move), "tokens": tokens, "transition_early_by": early}
        if move.get("pins"):
            target["pins"] = move["pins"]
        if move.get("hold_pins_frames"):
            target["hold_pins"] = int(move["hold_pins_frames"])
        return target


def move_frames(move: dict) -> int:
    """How many frames a move plays for."""
    return 4 * int(move["tokens"]) - 7 - int(move.get("early_frames", 0))


def plan(shot: dict, library: dict, sk: Skeleton, set_card: dict = None) -> tuple:
    stage = Stage(shot, library, sk)
    poses, path = stage.poses, stage.path
    start = dict(at_m=0.0, side_m=0.0, facing_deg=float(shot.get("start_facing_deg", 0.0)))
    sx, sz, _, sheading = stage.placed(start)
    request = {"kind": "inbetween", "positions": True, "seed": stand(poses[shot["start_pose"]], sx, sz, sheading), "targets": []}
    marks, beats = [], []
    frame = 0
    for beat in shot["beats"]:
        first = frame
        for number, move in enumerate(beat["moves"]):
            name = f"{beat['name']} {number + 1}: {move['pose']}"
            target = stage.target(name, move)
            frame += move_frames(move)
            request["targets"].append(target)
            marks.append(stage.mark(name, beat["name"], move, frame, target["poses"][0]))
        beats.append(
            {
                "name": beat["name"],
                "source": beat.get("source", "poses"),
                "first_frame": first,
                "last_frame": frame,
                "planned_seconds": float(beat["seconds"]),
                "seconds": round((frame - first) / FPS, 3),
            }
        )
    record = {
        "fps": FPS,
        "frames": frame + 1,
        "seconds": round(frame / FPS, 3),
        "start": {"pose": shot["start_pose"], "x": round(sx, 4), "z": round(sz, 4), "heading": round(sheading, 2)},
        "beats": beats,
        "moves": marks,
        "path": [[round(p[0], 3), round(p[1], 3)] for p in path.points[::5]] + [[round(v, 3) for v in path.points[-1]]],
        "path_length_m": round(path.length, 3),
    }
    record["seams"] = seams(beats, marks)
    if set_card:
        end_m = max(float(m["at_m"]) for b in shot["beats"] for m in b["moves"])
        record["set"], record["wall"] = set_blocks(path, set_card, end_m)
    return request, record


def seams(beats: list, marks: list) -> list:
    """Where one beat's motion meets the next, written down so a seam can be redone alone.

    A seam is tweened by MotionBricks from the four frames that end beat A
    (its `context_frames`) toward the first pose of beat B. For a "poses" beat
    that tween is the beat's own first move; a beat from another source (text,
    walk) would bring frames of its own, and the tween would end where those begin."""
    out = []
    for a, b in zip(beats, beats[1:]):
        first_move = next(m for m in marks if m["beat"] == b["name"])
        last = a["last_frame"]
        out.append(
            {
                "from": a["name"],
                "to": b["name"],
                "context_frames": [last - 3, last - 2, last - 1, last],
                "tween_frames": [last, first_move["frame"]],
                "target": first_move["name"],
                "made_by": "MotionBricks inbetween",
            }
        )
    return out


def context_from(motion: dict, last_frame: int) -> list:
    """The four frames of a motion that end at last_frame, as the worker's `context`:
    what an inbetween needs to carry on from the middle of any motion in the repo's format."""
    poses = []
    for f in range(last_frame - 3, last_frame + 1):
        f = max(0, f)
        row = motion["rotations"][f]
        poses.append({"root": motion["root"][f], "rotations": {name: row[4 * j : 4 * j + 4] for j, name in enumerate(motion["joints"])}})
    return poses


def set_blocks(path: Path, card: dict, end_m: float) -> tuple:
    """The set as plain blocks standing along the path: a ledge in short
    pieces that follow the curve, one roof slab, and the wall. The walking
    surface is y = 0 everywhere."""
    blocks, wall = [], None

    def block(name, kind, s, size, y):
        x, z, heading = path.at(s)
        return {"name": name, "kind": kind, "center": [round(x, 4), y, round(z, 4)], "size": size, "heading": round(heading, 2)}

    ledge = card.get("ledge")
    if ledge:
        piece = 0.2
        count = max(1, int(round((ledge["to_m"] - ledge["from_m"]) / piece)))
        for i in range(count):
            s = ledge["from_m"] + (i + 0.5) * (ledge["to_m"] - ledge["from_m"]) / count
            blocks.append(block(f"ledge {i + 1}", "ledge", s, [ledge["width_m"], BLOCK_DEPTH, piece * 1.25], -BLOCK_DEPTH / 2.0))
        blocks.append(block("roof edge", "roof", ledge["from_m"] - 0.45, [1.6, BLOCK_DEPTH, 0.9], -BLOCK_DEPTH / 2.0 - 0.001))
    roof = card.get("roof")
    if roof:
        last = end_m + roof.get("past_the_end_m", 2.0)
        span = last - roof["from_m"]
        blocks.append(block("roof", "roof", roof["from_m"] + span / 2.0, [roof["width_m"], BLOCK_DEPTH, span], -BLOCK_DEPTH / 2.0 - 0.002))
    if card.get("wall"):
        w = card["wall"]
        wall = block("wall", "wall", w["at_m"], [w["width_m"], w["height_m"], w["thickness_m"]], w["height_m"] / 2.0)
        blocks.append(wall)
    return blocks, wall


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("shot")
    parser.add_argument("--poses", default=os.path.join(REPO, "motion", "poses.json"))
    parser.add_argument("--brief", help="the shot's plan (motion/shots/<name>.json); its `set` is stood along the path")
    args = parser.parse_args()
    with open(os.path.join(args.shot, "shotlist.json")) as f:
        shot = json.load(f)
    with open(args.poses) as f:
        library = json.load(f)
    set_card = None
    if args.brief:
        with open(args.brief) as f:
            set_card = json.load(f).get("set")
    sk = Skeleton.load()
    if any(beat.get("source", "poses") != "poses" for beat in shot["beats"]):
        # Beats from more than one maker: the shot is made in pieces and joined (timeline.py).
        import timeline

        record, requests = timeline.lay_out(shot, library, sk, set_card)
        for request in requests.values():
            timeline.keep_request(args.shot, request)
        with open(os.path.join(args.shot, "plan.json"), "w") as f:
            json.dump(record, f, indent=1)
        for beat in record["beats"]:
            print(f"PLAN {beat['name']} ({beat['source']}): {beat['seconds']} s (planned {beat['planned_seconds']} s), frames {beat['first_frame']}-{beat['last_frame']}")
        for seam in record["seams"]:
            print(f"PLAN seam {seam['from']} to {seam['to']}: MotionBricks fills frames {seam['tween_frames'][0]}-{seam['tween_frames'][1]}")
        print(f"PLAN {len(record['pieces'])} pieces, {len(record['seams'])} seams, {record['frames']} frames, {record['seconds']} s, path {record['path_length_m']} m")
        return
    request, record = plan(shot, library, sk, set_card)
    with open(os.path.join(args.shot, "request.json"), "w") as f:
        json.dump(request, f, separators=(",", ":"))
    with open(os.path.join(args.shot, "plan.json"), "w") as f:
        json.dump(record, f, indent=1)
    for beat in record["beats"]:
        print(f"PLAN {beat['name']}: {beat['seconds']} s (planned {beat['planned_seconds']} s), frames {beat['first_frame']}-{beat['last_frame']}")
    print(f"PLAN {len(request['targets'])} moves, {record['frames']} frames, {record['seconds']} s, path {record['path_length_m']} m")


if __name__ == "__main__":
    main()
