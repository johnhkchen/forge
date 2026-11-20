"""Measures a generated motion against the shot it was made for.

    python3 scripts/motion/checks.py <shot folder>

Reads <shot>/motion.json (what the worker sent back) and <shot>/plan.json
(what was asked for), and writes <shot>/checks.json. It prints one CHECK line
per measurement. These are measurements, not a pass or fail: the numbers say
how the raw motion behaves before anyone tidies it.

  feet     how far each heel and toe slides while it is on the ground
  floor    how deep anything sinks below the roof
  wall     how deep anything cuts into the wall
  hand     whether the pinned hand stays on the wall top
  beats    how far the hips are from each planned point when a move ends
  path     how far the hips stray from the planned route
  seams    how smoothly one beat's motion runs into the next: the jump in
           speed and in pose at each join, next to what is usual for the shot

Joint positions are worked out here from the rotations (and compared with the
ones the worker sent, when it sent them), so the same numbers can be had for
any motion in this format.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from soma import Skeleton, heading_of, qangle, qconj, qmul  # noqa: E402

FPS = 30
ON_GROUND = 0.5  # the model's own contact confidence, 0..1
CONTACTS = (("left_heel", "LeftFoot"), ("left_toe", "LeftToeBase"), ("right_heel", "RightFoot"), ("right_toe", "RightToeBase"))
PIN_JOINT = {"left_hand": "LeftHand", "right_hand": "RightHand", "left_foot": "LeftFoot", "right_foot": "RightFoot"}
# Rough body thickness around each joint, in metres, for "is it inside something".
RADIUS = {
    "Hips": 0.10,
    "Spine1": 0.10,
    "Spine2": 0.10,
    "Chest": 0.11,
    "Head": 0.09,
    "LeftLeg": 0.07,
    "RightLeg": 0.07,
    "LeftShin": 0.055,
    "RightShin": 0.055,
    "LeftArm": 0.045,
    "RightArm": 0.045,
    "LeftForeArm": 0.04,
    "RightForeArm": 0.04,
    "LeftHand": 0.03,
    "RightHand": 0.03,
}
PALM = 0.03  # a wrist rests about this far above what the palm is on


def cm(metres: float) -> float:
    return round(metres * 100.0, 2)


def ground_dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[2] - b[2])


def world_positions(sk: Skeleton, motion: dict):
    """Every joint's world position and rotation per frame, by the skeleton's joint order."""
    order = [motion["joints"].index(name) for name in sk.joints]
    frames = []
    for root, row in zip(motion["root"], motion["rotations"]):
        frames.append(sk.fk(root, [tuple(row[4 * j : 4 * j + 4]) for j in order]))
    return frames


def fk_agrees(sk: Skeleton, motion: dict, frames) -> float:
    """Largest gap (m) between our joint positions and the worker's, or -1 if it sent none."""
    if "positions" not in motion:
        return -1.0
    order = [motion["joints"].index(name) for name in sk.joints]
    worst = 0.0
    for (pos, _), row in zip(frames, motion["positions"]):
        for i, j in enumerate(order):
            worst = max(worst, math.dist(pos[i], row[3 * j : 3 * j + 3]))
    return worst


def runs(flags):
    """[(first, last), ...] for each unbroken stretch of True."""
    out, start = [], None
    for i, on in enumerate(flags):
        if on and start is None:
            start = i
        if not on and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(flags) - 1))
    return out


def feet(sk: Skeleton, motion: dict, frames) -> dict:
    """Sliding of each heel and toe over the frames the model says it is on the ground."""
    out = {}
    for column, (label, joint) in enumerate(CONTACTS):
        j = sk.index[joint]
        track = [pos[j] for pos, _ in frames]
        on = [c[column] > ON_GROUND for c in motion["contacts"]]
        travel, worst_step, worst_step_frame = 0.0, 0.0, -1
        drift, drift_run = 0.0, None
        for first, last in runs(on):
            for f in range(first, last):
                step = ground_dist(track[f], track[f + 1])
                travel += step
                if step > worst_step:
                    worst_step, worst_step_frame = step, f + 1
            moved = max(ground_dist(track[first], track[f]) for f in range(first, last + 1))
            if moved > drift:
                drift, drift_run = moved, [first, last]
        frames_on = sum(on)
        out[label] = {
            "frames_on_ground": frames_on,
            "slide_total_cm": cm(travel),
            "slide_speed_cm_per_s": round(cm(travel) / (frames_on / FPS), 2) if frames_on else 0.0,
            "worst_step_cm": cm(worst_step),
            "worst_step_frame": worst_step_frame,
            "worst_stretch_drift_cm": cm(drift),
            "worst_stretch_frames": drift_run,
        }
    return out


def floor(sk: Skeleton, frames) -> dict:
    """How far below the roof (y = 0) each part gets. A foot joint is 'below'
    when it is lower than it sits with the foot flat."""
    rest = {name: sk.rest_world_pos[sk.index[name]][1] for _, name in CONTACTS}
    worst = {"depth_cm": 0.0, "joint": None, "frame": -1}
    per_joint = {}
    frames_below = 0
    for f, (pos, _) in enumerate(frames):
        below = False
        for i, name in enumerate(sk.joints):
            allow = rest.get(name, RADIUS.get(name))
            if allow is None:
                continue
            depth = allow - pos[i][1]
            if depth > 0.005:
                below = True
            if depth > per_joint.get(name, 0.0):
                per_joint[name] = depth
            if depth > worst["depth_cm"] / 100.0:
                worst = {"depth_cm": cm(depth), "joint": name, "frame": f}
        frames_below += below
    return {
        "worst": worst,
        "frames_with_anything_below": frames_below,
        "deepest_by_joint_cm": {k: cm(v) for k, v in sorted(per_joint.items(), key=lambda kv: -kv[1]) if v > 0.005},
    }


class Wall:
    def __init__(self, card: dict):
        self.center, self.size = card["center"], card["size"]  # size: across, height, thickness
        h = math.radians(card.get("heading", 0.0))
        self.forward = (math.sin(h), math.cos(h))
        self.left = (math.cos(h), -math.sin(h))
        self.top = self.center[1] + self.size[1] / 2.0

    def local(self, p):
        """(across, along, height above the top) of a point."""
        dx, dz = p[0] - self.center[0], p[2] - self.center[2]
        return dx * self.left[0] + dz * self.left[1], dx * self.forward[0] + dz * self.forward[1], p[1] - self.top

    def depth(self, p, radius: float) -> float:
        """How deep a ball at p is inside the wall (0 if clear)."""
        across, along, above = self.local(p)
        if abs(across) > self.size[0] / 2.0:
            return 0.0
        return max(0.0, min(self.size[2] / 2.0 + radius - abs(along), radius - above))

    def over_top(self, p) -> bool:
        across, along, _ = self.local(p)
        return abs(across) <= self.size[0] / 2.0 and abs(along) <= self.size[2] / 2.0


def wall_cut(sk: Skeleton, frames, wall: Wall, skip: set) -> dict:
    """Deepest cut into the wall by any joint, or by the middle of any bone."""
    worst = {"depth_cm": 0.0, "part": None, "frame": -1}
    frames_cut = 0
    for f, (pos, _) in enumerate(frames):
        cut = False
        for i, name in enumerate(sk.joints):
            if name in skip:
                continue
            radius = RADIUS.get(name, 0.03)
            samples = [(name, pos[i], radius)]
            p = sk.parents[i]
            if p >= 0:
                mid = tuple((pos[i][a] + pos[p][a]) / 2.0 for a in range(3))
                samples.append((f"{sk.joints[p]}-{name}", mid, min(radius, RADIUS.get(sk.joints[p], 0.03))))
            for label, point, r in samples:
                depth = wall.depth(point, r)
                if depth > 0.005:
                    cut = True
                if depth > worst["depth_cm"] / 100.0:
                    worst = {"depth_cm": cm(depth), "part": label, "frame": f}
        frames_cut += cut
    return {"worst": worst, "frames_cutting": frames_cut}


def hand_on_wall(sk: Skeleton, frames, wall: Wall, plan: dict) -> dict:
    """For each move that pins a hand at the wall: where the wrist is when the
    move ends, and how well it stays while the next move holds the pin."""
    out = []
    moves = plan["moves"]
    for n, move in enumerate(moves):
        for pin in move["pins"]:
            if not pin.endswith("hand"):
                continue
            j = sk.index[PIN_JOINT[pin]]
            plant = frames[move["frame"]][0][j]
            if not wall.over_top(plant) and abs(wall.local(plant)[1]) > wall.size[2]:
                continue  # a hand pinned somewhere else (the ground, say)
            hold = moves[n + 1].get("hold_pins_frames", 0) if n + 1 < len(moves) else 0
            last = min(len(frames) - 1, move["frame"] + hold)
            held = [frames[f][0][j] for f in range(move["frame"], last + 1)]
            near = [
                f
                for f in range(len(frames))
                if wall.over_top(frames[f][0][j]) and abs(wall.local(frames[f][0][j])[2] - PALM) < 0.06
            ]
            out.append(
                {
                    "pin": pin,
                    "move": move["name"],
                    "plant_frame": move["frame"],
                    "held_until_frame": last,
                    "over_the_wall_top_at_plant": wall.over_top(plant),
                    "wrist_above_top_at_plant_cm": cm(wall.local(plant)[2]),
                    "drift_while_held_cm": cm(max(math.dist(plant, p) for p in held)),
                    "height_off_while_held_cm": cm(max(abs(wall.local(p)[2] - wall.local(plant)[2]) for p in held)),
                    "frames_resting_on_top": len(near),
                    "resting_on_top_from_to": [near[0], near[-1]] if near else None,
                }
            )
    return {"pins": out}


def pinned_feet_and_hands(sk: Skeleton, frames, plan: dict) -> list:
    """Every pin: how far the hand or foot is, when its move ends, from where the planned pose puts it.
    (The planned spot comes from plan.json's `pin_points`, written by plan_shot.py.)"""
    out = []
    for move in plan["moves"]:
        for pin, want in (move.get("pin_points") or {}).items():
            got = frames[move["frame"]][0][sk.index[PIN_JOINT[pin]]]
            out.append({"move": move["name"], "pin": pin, "miss_cm": cm(math.dist(got, want))})
    return out


def beats(sk: Skeleton, frames, plan: dict) -> dict:
    """Hips over the ground versus the planned point, and facing versus the planned heading, when each move ends."""
    rest = sk.rest_rot[0]
    rows = []
    for move in plan["moves"]:
        f = min(move["frame"], len(frames) - 1)
        pos, rot = frames[f]
        facing = heading_of(qmul(rot[0], qconj(rest)))
        turn = (facing - move["heading"] + 180.0) % 360.0 - 180.0
        rows.append(
            {
                "move": move["name"],
                "beat": move["beat"],
                "frame": f,
                "miss_cm": cm(math.hypot(pos[0][0] - move["x"], pos[0][2] - move["z"])),
                "facing_off_deg": round(turn, 1),
                "cut_short_by_frames": move["early_frames"],
            }
        )
    by_beat = {}
    for row in rows:
        by_beat[row["beat"]] = row  # the last move of each beat
    return {
        "moves": rows,
        "beats": [{"beat": k, "miss_cm": v["miss_cm"], "facing_off_deg": v["facing_off_deg"], "frame": v["frame"]} for k, v in by_beat.items()],
    }


def path_stray(frames, plan: dict) -> dict:
    """Largest and typical distance of the hips from the planned route."""
    route = plan["path"]
    worst, worst_frame, total = 0.0, -1, 0.0
    for f, (pos, _) in enumerate(frames):
        x, z = pos[0][0], pos[0][2]
        best = 1e9
        for a, b in zip(route, route[1:]):
            ax, az, bx, bz = a[0], a[1], b[0], b[1]
            span = (bx - ax) ** 2 + (bz - az) ** 2
            t = 0.0 if span == 0 else max(0.0, min(1.0, ((x - ax) * (bx - ax) + (z - az) * (bz - az)) / span))
            best = min(best, math.hypot(x - (ax + (bx - ax) * t), z - (az + (bz - az) * t)))
        total += best
        if best > worst:
            worst, worst_frame = best, f
    return {"worst_cm": cm(worst), "worst_frame": worst_frame, "typical_cm": cm(total / len(frames))}


def seams(sk: Skeleton, motion: dict, frames, plan: dict) -> dict:
    """How smoothly the motion runs across each seam.

    A body in steady motion moves each joint about as far in one frame as in
    the frame before. At a bad join it does not: something is suddenly faster,
    slower or somewhere else. So for every frame this takes, per joint, how far
    it is from where the two frames before would have put it (the change in
    its speed, in cm per frame), and how far it turns in one frame. A seam's
    numbers are the worst within a frame of each of its joins, and they are
    given next to what is usual across the whole shot, because a sprint is
    never as smooth as a crouch.

    A shot made in pieces has two joins a seam (where the tween starts and
    where it ends); a shot made in one go has one, the frame the beat ends on."""
    count = len(frames)
    order = [motion["joints"].index(name) for name in sk.joints]

    def jump(f: int):
        """(metres, joint): the largest change of speed on frame f."""
        worst, which = 0.0, None
        if not 1 <= f < count - 1:
            return worst, which
        for i, name in enumerate(sk.joints):
            a, b, c = frames[f - 1][0][i], frames[f][0][i], frames[f + 1][0][i]
            d = math.dist(c, tuple(2 * b[k] - a[k] for k in range(3)))
            if d > worst:
                worst, which = d, name
        return worst, which

    def turn(f: int) -> float:
        """Degrees: the largest turn of any joint, in its parent, from frame f to f + 1."""
        if not 0 <= f < count - 1:
            return 0.0
        a, b = motion["rotations"][f], motion["rotations"][f + 1]
        return max(qangle(qmul(tuple(b[4 * j : 4 * j + 4]), qconj(tuple(a[4 * j : 4 * j + 4])))) for j in order)

    def hips(f: int) -> float:
        """m/s: how much the hips' velocity changes on frame f."""
        if not 1 <= f < count - 1:
            return 0.0
        a, b, c = frames[f - 1][0][0], frames[f][0][0], frames[f + 1][0][0]
        return math.dist(c, tuple(2 * b[k] - a[k] for k in range(3))) * FPS

    jumps = sorted(jump(f)[0] for f in range(1, count - 1))
    turns = sorted(turn(f) for f in range(count - 1))
    usual_jump, usual_turn = jumps[len(jumps) // 2], turns[len(turns) // 2]
    rows = []
    for seam in plan.get("seams") or []:
        joins = list(seam["tween_frames"]) if "boundary_frame" in seam else [seam["tween_frames"][0]]
        near = [f for j in joins for f in (j - 1, j, j + 1)]
        worst, which, at = 0.0, None, joins[0]
        for f in near:
            d, name = jump(f)
            if d > worst:
                worst, which, at = d, name, f
        rows.append(
            {
                "from": seam["from"],
                "to": seam["to"],
                "joins_at_frames": joins,
                "speed_jump_cm_per_frame": cm(worst),
                "speed_jump_joint": which,
                "speed_jump_frame": at,
                "speed_jump_times_usual": round(worst / usual_jump, 1) if usual_jump > 1e-9 else None,
                "hips_speed_jump_m_per_s": round(max(hips(f) for f in near), 3),
                "pose_jump_deg_per_frame": round(max(turn(f) for j in joins for f in (j - 1, j)), 2),
            }
        )
    return {
        "usual_speed_jump_cm_per_frame": cm(usual_jump),
        "worst_speed_jump_anywhere_cm_per_frame": cm(jumps[-1]) if jumps else 0.0,
        "usual_pose_change_deg_per_frame": round(usual_turn, 2),
        "seams": rows,
    }


def check(shot: str) -> dict:
    sk = Skeleton.load()
    with open(os.path.join(shot, "motion.json")) as f:
        motion = json.load(f)
    with open(os.path.join(shot, "plan.json")) as f:
        plan = json.load(f)
    frames = world_positions(sk, motion)
    speeds = [ground_dist(frames[f][0][0], frames[f + 1][0][0]) * FPS for f in range(len(frames) - 1)]
    report = {
        "frames": len(frames),
        "seconds": round((len(frames) - 1) / FPS, 3),
        "planned_frames": plan["frames"],
        "top_speed_m_per_s": round(max(speeds), 2),
        "our_joint_positions_vs_worker_cm": cm(fk_agrees(sk, motion, frames)),
        "feet": feet(sk, motion, frames),
        "floor": floor(sk, frames),
        "beats": beats(sk, frames, plan),
        "path": path_stray(frames, plan),
        "pins": pinned_feet_and_hands(sk, frames, plan),
        "seams": seams(sk, motion, frames, plan),
    }
    if plan.get("wall"):
        wall = Wall(plan["wall"])
        # The hand that is pinned to the wall top is meant to touch it.
        touching = {PIN_JOINT[p] for m in plan["moves"] for p in m["pins"] if p.endswith("hand")}
        fingers = {j for j in sk.joints for t in touching if j.startswith(t)}
        report["wall"] = wall_cut(sk, frames, wall, fingers)
        report["hand"] = hand_on_wall(sk, frames, wall, plan)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("shot")
    args = parser.parse_args()
    report = check(args.shot)
    with open(os.path.join(args.shot, "checks.json"), "w") as f:
        json.dump(report, f, indent=1)
    print(f"CHECK frames {report['frames']} ({report['seconds']} s), planned {report['planned_frames']}; top speed {report['top_speed_m_per_s']} m/s")
    for label, foot in report["feet"].items():
        print(
            f"CHECK feet {label}: on the ground {foot['frames_on_ground']} frames, slides {foot['slide_total_cm']} cm in all "
            f"({foot['slide_speed_cm_per_s']} cm/s), worst stretch drifts {foot['worst_stretch_drift_cm']} cm"
        )
    w = report["floor"]["worst"]
    print(f"CHECK floor: deepest {w['depth_cm']} cm ({w['joint']}, frame {w['frame']}); {report['floor']['frames_with_anything_below']} frames with something below")
    if "wall" in report:
        w = report["wall"]["worst"]
        print(f"CHECK wall: deepest cut {w['depth_cm']} cm ({w['part']}, frame {w['frame']}); {report['wall']['frames_cutting']} frames cutting")
        for pin in report["hand"]["pins"]:
            print(
                f"CHECK hand {pin['pin']}: at frame {pin['plant_frame']} wrist {pin['wrist_above_top_at_plant_cm']} cm above the wall top, "
                f"over it: {pin['over_the_wall_top_at_plant']}; drifts {pin['drift_while_held_cm']} cm while held to frame {pin['held_until_frame']}; "
                f"rests on top {pin['frames_resting_on_top']} frames"
            )
    for pin in report["pins"]:
        print(f"CHECK pin {pin['pin']} at '{pin['move']}': {pin['miss_cm']} cm from its planned spot")
    for beat in report["beats"]["beats"]:
        print(f"CHECK beat '{beat['beat']}': ends {beat['miss_cm']} cm from its planned point, facing off by {beat['facing_off_deg']} deg (frame {beat['frame']})")
    for seam in report["seams"]["seams"]:
        print(
            f"CHECK seam '{seam['from']}' to '{seam['to']}': speed jumps {seam['speed_jump_cm_per_frame']} cm a frame at most ({seam['speed_jump_joint']}, frame {seam['speed_jump_frame']}, "
            f"{seam['speed_jump_times_usual']} times what is usual), hips {seam['hips_speed_jump_m_per_s']} m/s, pose {seam['pose_jump_deg_per_frame']} deg a frame"
        )
    print(f"CHECK path: hips stray {report['path']['worst_cm']} cm at most (frame {report['path']['worst_frame']}), {report['path']['typical_cm']} cm typically")


if __name__ == "__main__":
    main()
