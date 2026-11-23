"""Lays a fight out on one timeline: two fighters, a plain list of exchanges.

    python3 scripts/fight/schedule.py <fight.json> <left body.json> <right body.json> <out folder>

A fight script is plain data (scripts/fight/fights/first.json is one):

    {"set": "ring", "marks": {"left": "fight_left", "right": "fight_right"},
     "fighters": {"left": {"stance": "usual"}, "right": {"stance": "mirror"}},
     "start_apart_m": 1.9,
     "beats": [
       {"both": "guard", "seconds": 1.0},
       {"both": "shuffle", "apart_m": 1.4},          both step in (or out) until they stand this far apart
       {"both": "circle", "deg": 20},                both step round the middle, this far (the way a clock doesn't turn is +)
       {"by": "left", "move": "jab", "result": "blocked"},
       {"by": "right", "move": "jab"},               lands, and causes the reaction the move names
       {"by": "right", "move": "uppercut", "result": "knockdown", "wait": 0.2},
       {"by": "left", "move": "get_up", "wait": 1.5},  a man who is down gets back to his feet
       {"by": "right", "move": "victory"}             the winner raises both fists and holds it to the end
     ]}

"result" is the fight script's choice: "blocked", or left out (the blow lands
and the move's own reaction follows), or a reaction by name (light_high,
light_low, heavy, knockdown). "wait" is the seconds both stand in guard
before the exchange (0.5 if left out).

What the scheduler does with it:

  - Fixed spacing. The two fight marks are a known range apart, and before
    any exchange both fighters are stepped back onto them (a stagger moves a
    man off his). Every blow is then built to reach across that range
    (moves.strike): the fist arrives at a spot on the other man's head or
    body, as he stands on that frame.
  - One timeline. The attacker's blow starts; the defender stands in guard
    (or, blocking, gets his arms up) until the attacker's first active frame,
    and on that frame his reaction starts.
  - Hitstop. On that same frame both fighters freeze for the blow's hitstop
    frames: the frame is simply held, in both motions, and everything after
    it comes later by that much.
  - In between: guard, with its light bounce, and footwork in short shuffle
    steps, one foot at a time.

It writes, into the out folder:

    left.motion.json, right.motion.json   one plain motion per fighter, in the
        form animate.py plays (see there). Each is in that fighter's own axes,
        from his fight mark, facing the other mark.
    fight.json   the timeline: every exchange with its frames, and "hits":
        for each blow {frame, hitstop, at (the set's axes, metres), power,
        blocked, move, by, on, reaction}: what the film needs for its freeze,
        camera shake and flash.

Plain Python: no Blender, no numpy.
"""

from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import moves  # noqa: E402
from moves import Z, about_z, add, length, sub, times, unit  # noqa: E402

FPS = 30
STEP_FRAMES = 7       # one shuffle step: one foot goes, then the other
STEP_M = 0.30         # how far one shuffle step covers, as a share of the hip height
BOUNCE_FRAMES = 14    # the guard's bounce: one dip every this many frames
BOUNCE_M = 0.03       # and how deep, as a share of the hip height
WAIT_S = 0.5          # guard before an exchange, when the script names no wait
A_STEP = 0.015        # metres: a foot that moves further than this between two keys is stepping, not planted
LANE_M = 0.17         # each man stands this far to his own left of the line between the marks ("lane_m" in a fight script changes it)
OTHER = {"left": "right", "right": "left"}


def eased(kind, t):
    t = moves.clamp(t, 0.0, 1.0)
    if kind == "out":
        return 1.0 - (1.0 - t) ** 3
    if kind == "in":
        return t * t
    if kind == "inout":
        return t * t * (3.0 - 2.0 * t)
    if kind == "cut":
        return 1.0 if t >= 1.0 else 0.0
    return t  # "hold": the two keys are the same pose


class Track:
    """One fighter's key poses, in order, and the pose on any frame between them."""

    def __init__(self, leg):
        self.keys = []  # (frame, pose where he really is, how it gets there)
        self.leg = leg

    def add(self, frame, pose, ease):
        while self.keys and self.keys[-1][0] >= frame:
            self.keys.pop()
        if self.keys:  # a foot asked to move less than a step has not moved: it stays planted where it is
            was = self.keys[-1][1]["feet"]
            for tag, spot in pose["feet"].items():
                if math.hypot(spot[0] - was[tag][0], spot[1] - was[tag][1]) <= A_STEP and spot[2] <= 0.004 and was[tag][2] <= 0.004:
                    spot[0], spot[1] = was[tag][0], was[tag][1]
        self.keys.append((frame, pose, ease))

    def last(self):
        return self.keys[-1]

    def at(self, frame):
        """The pose on a frame, and which feet are planted on it."""
        keys = self.keys
        if frame <= keys[0][0]:
            a = b = keys[0]
        elif frame >= keys[-1][0]:
            a = b = keys[-1]
        else:
            n = max(i for i, k in enumerate(keys) if k[0] <= frame)
            a, b = keys[n], keys[n + 1]
        t = 0.0 if a is b else (frame - a[0]) / float(b[0] - a[0])
        e = eased(b[2], t)
        pose = moves.blend(a[1], b[1], e)
        pose["facing"] = a[1]["facing"] + (b[1]["facing"] - a[1]["facing"]) * e
        planted = {}
        for tag in ("l", "r"):
            was, will = a[1]["feet"][tag], b[1]["feet"][tag]
            far = math.hypot(will[0] - was[0], will[1] - was[1])
            stepping = far > A_STEP and 0.0 < t < 1.0
            if stepping:  # a step: the foot goes over in a low arc, quick whatever the body's easing is
                s = t * t * (3.0 - 2.0 * t)
                row = list(moves.mix(was, will, s))
                row[2] += (0.035 * self.leg + 0.12 * far) * math.sin(math.pi * s)
                pose["feet"][tag] = row
            planted[tag] = 0 if stepping or pose["feet"][tag][2] > 0.004 else 1
        return pose, planted

    def cut(self, frame):
        """Whatever was planned after this frame is dropped: he is hit."""
        pose, planted = self.at(frame)
        self.keys = [k for k in self.keys if k[0] < frame]
        self.keys.append((frame, pose, "hold"))


class Fighter:
    def __init__(self, side, body, stance, apart, between, lane=0.0):
        self.side, self.body = side, body
        self.lane = lane                # how far to his own left of the line between the marks he stands
        self.mirror = stance in ("mirror", "southpaw")
        self.between = between          # the range: how far apart the two fight marks are
        self.ring, self.apart = 0.0, apart
        self.base = self.home(apart, 0.0)
        self.track = Track(body.leg)
        self.down = False               # knocked down: lies where he fell
        self.idle = moves.guard(body)

    def home(self, apart, ring):
        """Where he stands (x, y, the way he faces) when the two are `apart` and have circled the middle by `ring` degrees. In his own mark's axes."""
        middle = (0.0, -self.between / 2.0, 0.0)
        spot = add(middle, about_z((self.lane, apart / 2.0, 0.0), ring))
        # Each man stands a little to his own left of the line, so the two pairs of feet are on two lines and
        # no boot is toe to toe with another; and each turns that little way to face the other.
        return (spot[0], spot[1], ring - 0.6 * math.degrees(math.atan2(2.0 * self.lane, max(apart, 0.3))))

    def place(self, pose, base=None, stay=(), before=None):
        """A pose of the move set, put where this fighter stands: mirrored for the other stance, turned and moved to his base.
        `stay` names feet (in the usual stance) that have not moved since `before`, the pose he was in."""
        base = base or self.base
        if self.mirror:
            pose = moves.mirrored(pose)
            stay = tuple("r" if tag == "l" else "l" for tag in stay)
        yaw = base[2]
        spin = moves.turn(Z, yaw)
        out = {"hips": add(about_z(pose["hips"], yaw), (base[0], base[1], 0.0)),
               "turns": {name: moves.qmul(spin, q) for name, q in pose["turns"].items()},
               "elbow": dict(pose["elbow"]), "feet": {}, "bounce": pose["bounce"], "facing": yaw}
        for tag, row in pose["feet"].items():
            if tag in stay and before is not None:
                out["feet"][tag] = list(before["feet"][tag])
                continue
            spot = add(about_z((row[0], row[1], 0.0), yaw), (base[0], base[1], 0.0))
            out["feet"][tag] = [spot[0], spot[1], row[2], row[3], row[4] + yaw]
        return out

    def into(self, point, base=None):
        """A point in his mark's axes, as the move set sees it: from his base, in the usual stance."""
        base = base or self.base
        p = about_z(sub(point, (base[0], base[1], 0.0)), -base[2])
        return (-p[0], p[1], p[2]) if self.mirror else p

    def out_of(self, point, base=None):
        """The other way: a point of the move set in his mark's axes."""
        base = base or self.base
        p = (-point[0], point[1], point[2]) if self.mirror else point
        return add(about_z(p, base[2]), (base[0], base[1], 0.0))

    def seen_by_other(self, point):
        """A point in his mark's axes, in the other fighter's: the two marks face each other, the range apart."""
        return (-point[0], -self.between - point[1], point[2])

    def rest(self):
        """What he does when nothing else is asked: guard, or lying where he fell."""
        return self.track.last()[1] if self.down else self.place(self.idle)


def set_point(mark, point):
    """A point in a fighter's own axes (x left, y back, z up, from his mark) in the set's (x, y up, z)."""
    p = about_z(point, mark["facing_deg"])
    return [round(mark["at"][0] + p[0], 4), round(p[2], 4), round(mark["at"][1] - p[1], 4)]


def walk(fighter, start, apart, ring):
    """Shuffle steps from where he is to where `apart` and `ring` put him: one foot goes, then the other. Returns the frame he arrives."""
    was = fighter.base
    goal = fighter.home(apart, ring)
    far = math.hypot(goal[0] - was[0], goal[1] - was[1])
    turn_by = abs(goal[2] - was[2])
    if far < 0.01 and turn_by < 0.5:
        return start
    steps = max(1, int(math.ceil(far / (STEP_M * fighter.body.leg) - 0.15)), int(math.ceil(turn_by / 25.0)))
    # Along the way he keeps facing the middle: the apartness and the angle round it both change evenly,
    # from wherever a stagger left him.
    track, frame = fighter.track, start
    track.add(frame, fighter.rest(), "inout")
    for n in range(1, steps + 1):
        u = n / float(steps)
        there = moves.mix(was, goal, u)
        half = moves.mix(was, goal, u - 0.5 / steps)
        before = track.last()[1]
        full = fighter.place(fighter.idle, there)
        go = (there[0] - before["hips"][0], there[1] - before["hips"][1])
        ahead = {tag: (full["feet"][tag][0] - there[0]) * go[0] + (full["feet"][tag][1] - there[1]) * go[1] for tag in ("l", "r")}
        first = "l" if ahead["l"] >= ahead["r"] else "r"  # the foot on the side he is going to goes first
        mid = fighter.place(fighter.idle, half)
        mid["feet"][first] = list(full["feet"][first])
        mid["feet"]["r" if first == "l" else "l"] = list(before["feet"]["r" if first == "l" else "l"])
        track.add(frame + STEP_FRAMES // 2, mid, "inout")
        track.add(frame + STEP_FRAMES, full, "inout")
        frame += STEP_FRAMES
    fighter.base, fighter.apart, fighter.ring = goal, apart, ring
    return frame


def schedule(fight, bodies, marks=None):
    """The whole fight. bodies: {"left": Body, "right": Body}. marks: {"left": {at, facing_deg}, "right": ...} from the set
    (left out: two marks a metre apart). Returns {"motions": {side: plain motion}, "timeline": what happened when}."""
    if marks is None:
        marks = {"left": {"at": [-0.5, 0.0], "facing_deg": 90.0}, "right": {"at": [0.5, 0.0], "facing_deg": -90.0}}
    between = math.hypot(marks["left"]["at"][0] - marks["right"]["at"][0], marks["left"]["at"][1] - marks["right"]["at"][1])
    apart = float(fight.get("start_apart_m", between))
    lane = float(fight.get("lane_m", LANE_M))
    who = {side: Fighter(side, bodies[side], (fight.get("fighters") or {}).get(side, {}).get("stance", "usual"), apart, between, lane) for side in ("left", "right")}
    for f in who.values():
        f.track.add(0, f.rest(), "hold")
    now, ring = 0, 0.0
    hits, beats = [], []

    def stand(until):
        for f in who.values():
            if f.track.last()[0] < until:
                f.track.add(until, f.rest(), "inout")

    for beat in fight["beats"]:
        card = {"beat": beat, "from_frame": now}
        if "both" in beat:
            kind = beat["both"]
            if kind == "guard":
                now += max(1, int(round(beat.get("seconds", 0.5) * FPS)))
            elif kind in ("shuffle", "circle"):
                if kind == "shuffle":
                    apart = float(beat["apart_m"])
                else:
                    ring += float(beat["deg"])
                stand(now)
                now = max(walk(f, now, apart, ring) for f in who.values() if not f.down) if not all(f.down for f in who.values()) else now
            else:
                raise ValueError("a beat for both can be guard, shuffle or circle, not %r" % kind)
            stand(now)
        else:
            side, name = beat["by"], beat["move"]
            if name == "victory":  # the winner raises his fists, and holds it for as long as the fight goes on
                winner = who[side]
                if winner.down:
                    raise ValueError("%s can't raise his fists: he is down" % side)
                stand(now)
                now += int(round(beat.get("wait", 0.0) * FPS))
                stand(now)
                winner.idle = moves.victory(winner.body)
                card["start"] = now
                now += 12
                winner.track.add(now, winner.place(winner.idle), "out")
                stand(now)
                card["to_frame"] = now
                beats.append(card)
                continue
            if name == "get_up":  # a man on the mat gets back to his feet; the other waits in guard
                faller = who[side]
                if not faller.down:
                    raise ValueError("%s can't get up: he is not down" % side)
                stand(now)
                now += int(round(beat.get("wait", 0.0) * FPS))
                stand(now)
                base = faller.base
                for k in moves.get_up(faller.body)["keys"]:
                    moved = add((base[0], base[1], 0.0), about_z((0.0, k["back"], 0.0), base[2]))
                    there = (moved[0], moved[1], base[2])
                    faller.track.add(now + k["at"], faller.place(k["pose"], there, k["stay"], faller.track.last()[1]), k["ease"])
                    faller.base = there
                faller.down = False
                card["start"] = now
                now = faller.track.last()[0]
                stand(now)
                card["to_frame"] = now
                beats.append(card)
                continue
            if name not in moves.STRIKES:
                raise ValueError("no attack called %r: choose from %s" % (name, ", ".join(sorted(moves.STRIKES))))
            hitter, taker = who[side], who[OTHER[side]]
            if hitter.down or taker.down:
                raise ValueError("%s can't %s: a man is down" % (side, name))
            # Back onto the fight marks: every blow is built for that range.
            stand(now)
            if any(length(sub(f.base, f.home(between, ring))) > 0.01 for f in who.values()) or apart != between:
                apart = between
                now = max(walk(f, now, apart, ring) for f in who.values())
                stand(now)
            now += int(round(beat.get("wait", WAIT_S) * FPS))
            stand(now)
            move = moves.STRIKES[name]
            result = beat.get("result") or move["causes"]
            blocked = result == "blocked"
            react = "block" if blocked else result
            if react not in moves.REACTIONS:
                raise ValueError("no result called %r: choose blocked or one of %s" % (result, ", ".join(sorted(moves.REACTIONS))))
            start, contact = now, now + move["startup"]
            low = move["aims"] == "low"
            # The defender up to the frame before contact: in guard, or with his arms already up.
            ready = moves.block(taker.body, low) if blocked else taker.idle
            if blocked:
                taker.track.add(contact - 1, taker.place(ready), "out")
            stood = taker.place(ready)

            # Where the fist must arrive: a spot on the defender as he stands, seen from the attacker.
            def spot_of(round_side, under, hitter=hitter, taker=taker, stood=stood, low=low, blocked=blocked):
                toward = taker.seen_by_other((hitter.base[0], hitter.base[1], 0.0))
                toward = unit((toward[0] - stood["hips"][0], toward[1] - stood["hips"][1], 0.0))
                if hitter.mirror:
                    round_side = -round_side
                if blocked:
                    spot = moves.covered_spot(taker.body, stood, toward, swung=bool(under or round_side))
                else:
                    spot = moves.target_on(taker.body, stood, "low" if low else "high", toward, round_side, under)
                return hitter.into(taker.seen_by_other(spot))

            blow = moves.strike(hitter.body, name, spot_of)
            for k in blow["keys"]:
                hitter.track.add(start + k["at"], hitter.place(k["pose"]), k["ease"])
            # Which way the blow came round, as the defender's own move set sees it: his head goes the other way.
            came = moves.SHAPES[name].get("side", 0.0) or (-0.35 if move["hand"] == "lead" else 0.35)
            came = -came if hitter.mirror else came
            turn_to = came if taker.mirror else -came
            taker.track.cut(contact - 1)
            answer = moves.reaction(taker.body, react, side=turn_to, low=low)
            base = taker.base
            for k in answer["keys"]:
                moved = add((base[0], base[1], 0.0), about_z((0.0, k["back"], 0.0), base[2]))
                there = (moved[0], moved[1], base[2])
                taker.track.add(contact + k["at"], taker.place(k["pose"], there, k["stay"], taker.track.last()[1]), k["ease"])
                taker.base = there
            taker.down = answer["down"]
            hitstop = moves.KNOCKOUT_HITSTOP if react == "knockdown" else move["hitstop"]
            if blocked:
                hitstop = max(2, int(round(hitstop * moves.BLOCKED_HITSTOP)))
            spot_here = hitter.out_of(blow["fist"])  # the fist, in the attacker's mark's axes
            hits.append({"live_frame": contact, "hitstop": hitstop, "at": set_point(marks[side], spot_here),
                         "power": moves.BLOCKED_POWER if blocked else (3 if react == "knockdown" else move["power"]),
                         "blocked": blocked, "move": name, "by": side, "on": OTHER[side], "reaction": react, "hand": blow["hand"] if not hitter.mirror else blow["other"],
                         "fist_from_spot_cm": round(100.0 * blow["miss_m"], 1), "stepped_in_cm": round(100.0 * blow["lunge_m"], 1)})
            card.update({"start": start, "contact": contact, "startup": move["startup"], "active": move["active"], "recovery": move["recovery"],
                         "reaction": react, "reaction_frames": answer["frames"]})
            now = max(hitter.track.last()[0], taker.track.last()[0])
            stand(now)
        card["to_frame"] = now
        beats.append(card)

    # ---- every frame, as it was planned ----
    live = {side: [f.track.at(n) for n in range(now + 1)] for side, f in who.items()}
    # ---- hitstop: the contact frame is held, in both motions ----
    order, shift = [], 0
    stops = {h["live_frame"]: h for h in hits}
    for n in range(now + 1):
        order.append(n)
        if n in stops:
            stops[n]["frame"] = len(order) - 1
            order += [n] * stops[n]["hitstop"]
    film_of = {}
    for i, n in enumerate(order):
        film_of.setdefault(n, i)
    for card in beats:
        for name in ("from_frame", "to_frame", "start", "contact"):  # the same frames, counted on the film (after the freezes)
            if name in card:
                card[name] = film_of[card[name]]
    motions = {}
    for side, f in who.items():
        motions[side] = plain(f, [live[side][n] for n in order], order, 0 if side == "left" else BOUNCE_FRAMES // 2)
    for h in hits:
        del h["live_frame"]
        if h["reaction"] == "knockdown":  # where the man ends up, so whoever films it can see he is still on the mat
            side = h["on"]
            landed = min(len(order) - 1, h["frame"] + h["hitstop"] + moves.REACTIONS["knockdown"])
            at = bodies[side].joints(pose_of(motions[side], bodies[side], landed))
            h["lies"] = {"hips": set_point(marks[side], at["hips"]), "head": set_point(marks[side], at["crown"])}
    timeline = {"fps": FPS, "frames": len(order), "seconds": round(len(order) / float(FPS), 2), "range_m": round(between, 3),
                "fighters": {side: {"stance": "mirror" if f.mirror else "usual", "down": f.down} for side, f in who.items()},
                "hits": hits, "beats": beats}
    return {"motions": motions, "timeline": timeline}


def plain(fighter, frames, order, bounce_late):
    """One fighter's frames as a plain motion, the form animate.py plays: lengths in hip heights, turns from the T-pose."""
    leg = fighter.body.leg
    hips, feet, knees = [], {"l": [], "r": []}, {"l": [], "r": []}
    names = list(moves.TRUNK) + ["upper_arm_l", "upper_arm_r", "forearm_l", "forearm_r"]
    turns = {name: [] for name in names}

    def listed(q):
        return [round(c, 5) for c in q]

    for (pose, planted), n in zip(frames, order):
        dip = BOUNCE_M * leg * pose["bounce"] * (0.5 - 0.5 * math.cos(2.0 * math.pi * (n + bounce_late) / BOUNCE_FRAMES))
        hips.append([round(pose["hips"][0] / leg, 5), round(pose["hips"][1] / leg, 5), round((pose["hips"][2] - dip) / leg, 5)])
        for name in moves.TRUNK + moves.ARMS:
            turns[name].append(listed(pose["turns"][name]))
        for tag, out in (("l", 1.0), ("r", -1.0)):  # an elbow is a hinge: the forearm is the upper arm turned about it
            turns["forearm_" + tag].append(listed(moves.qmul(pose["turns"]["upper_arm_" + tag], moves.turn(Z, -out * pose["elbow"][tag]))))
        # Which way the knees point: where the hips face, part of the way to where each foot points. A man on
        # his back has hips that face the ceiling, so there it is the way he stood.
        ahead = moves.qturned(pose["turns"]["hips"], (0.0, -1.0, 0.0))
        level = math.hypot(ahead[0], ahead[1])
        facing = math.degrees(math.atan2(ahead[0], -ahead[1])) if level > 0.5 else pose["facing"]
        for tag in ("l", "r"):
            row = pose["feet"][tag]
            feet[tag].append([round(row[0] / leg, 5), round(row[1] / leg, 5), round(max(0.0, row[2]) / leg, 5), round(row[3], 3), round(row[4], 3), planted[tag]])
            way = facing + 0.6 * ((row[4] - facing + 180.0) % 360.0 - 180.0)
            knees[tag].append([round(math.cos(math.radians(way)), 5), round(math.sin(math.radians(way)), 5), 0.0])
    return {"name": "fight", "version": 1, "fps": FPS, "frames": len(frames) - 1, "loop": False,
            "unit": "hip_height", "axes": "x left, y back, z up; the character faces -y", "travel": 0.0,
            "hips": hips, "feet": feet, "turns": turns, "knees": knees}


def fist_and_spot(timeline, motions, bodies, marks):
    """For each hit, from the plain motions themselves: how far the attacker's fist is from the spot it was built for
    on the contact frame, in cm. (What the move set meant and what the motion says are worked out separately, so
    this is a real check on the scheduler's bookkeeping.)"""
    out = []
    for h in timeline["hits"]:
        m, body = motions[h["by"]], bodies[h["by"]]
        pose = pose_of(m, body, h["frame"])
        fist = body.joints(pose)["fist_" + h["hand"]]
        out.append(round(100.0 * length(sub(set_point(marks[h["by"]], fist), h["at"])), 1))
    return out


def pose_of(motion, body, frame):
    """One frame of a plain motion as a pose the Body can find the joints of."""
    leg = body.leg
    turns = {name: tuple(rows[frame]) for name, rows in motion["turns"].items()}
    elbow = {}
    for tag in ("l", "r"):
        d = sum(a * b for a, b in zip(turns["upper_arm_" + tag], turns["forearm_" + tag]))
        elbow[tag] = math.degrees(2.0 * math.acos(moves.clamp(abs(d), -1.0, 1.0)))
    return {"hips": tuple(c * leg for c in motion["hips"][frame]), "turns": turns, "elbow": elbow}


def marks_of(fight):
    """The two fight marks, from the set the fight names."""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "sets"))
    import standing

    st = standing.load(fight["set"])
    return {side: {"at": st["marks"][name]["at"], "facing_deg": st["marks"][name]["facing_deg"]} for side, name in fight["marks"].items()}


def main():
    fight_file, left, right, out = sys.argv[1:5]
    with open(fight_file) as f:
        fight = json.load(f)
    bodies = {}
    for side, path in (("left", left), ("right", right)):
        with open(path) as f:
            bodies[side] = moves.Body(json.load(f))
    marks = marks_of(fight) if fight.get("set") else None
    made = schedule(fight, bodies, marks)
    os.makedirs(out, exist_ok=True)
    for side, motion in made["motions"].items():
        with open(os.path.join(out, side + ".motion.json"), "w") as f:
            json.dump(motion, f)
    with open(os.path.join(out, "fight.json"), "w") as f:
        json.dump(made["timeline"], f, indent=1)
    t = made["timeline"]
    print("FIGHT %d frames (%.1f s), %d hits: %s" % (t["frames"], t["seconds"], len(t["hits"]),
          ", ".join("%s %s%s at %d" % (h["by"], h["move"], " (blocked)" if h["blocked"] else "", h["frame"]) for h in t["hits"])))


if __name__ == "__main__":
    main()
