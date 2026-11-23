"""Tries the fight kit with no Blender and no GPU.

    python3 scripts/fight/test_fight.py

Two test bodies stand in for the characters (test_bodies.json: a short thick
man with short arms, a tall thin one with long arms, as apply_fight.py
measured two real runs). What it shows:

  frame data       every attack has startup, active and recovery frames, reaches its stretched pose on
                   the contact frame and holds it for the active ones
  reaction         the defender stands in guard until the attacker's first active frame, and his
                   reaction starts on that frame
  hitstop          on the contact frame both fighters hold still for the blow's hitstop frames
  fist             on the contact frame the fist is within a few cm of the spot it was built for, and
                   that spot is on the other man: his face, his chest, or the arms he blocks with
  mat              nothing goes under the mat, and a man knocked down ends on it, lying still
  limits           no pose asks a joint for more than rig.py's limits allow (what animate.py reports as "clamped")
  every body       the same moves, every one of them landed and blocked, fit either body against the
                   other, in either stance
  feet             a planted foot stays where it was put; shuffle steps move one foot at a time
  mirror           the other stance is the same motion in a mirror
  script           a fight script that asks for what can't be is told why

`scripts/test_tools.py` runs the same checks, and one more in a background
Blender: the first fight baked onto the real characters and measured there.
"""

from __future__ import annotations

import copy
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import moves  # noqa: E402
import schedule  # noqa: E402

with open(os.path.join(HERE, "test_bodies.json")) as f:
    CARDS = json.load(f)
with open(os.path.join(HERE, "fights", "first.json")) as f:
    FIRST = json.load(f)
MARKS = {"left": {"at": [-0.1, 0.0], "facing_deg": 90.0}, "right": {"at": [0.9, 0.0], "facing_deg": -90.0}}
FIST_CM = 1.0      # the fist against the spot it was built for
ON_HIM_CM = 22.0   # that spot against the middle of the other man's head (or chest, or guarding fists)
LIMIT_SLACK = 1.5  # degrees: a frame between two key poses may brush a limit


def check(label, ok, detail=""):
    print("    %s  %s%s" % ("ok  " if ok else "FAIL", label, ("  (%s)" % (detail,)) if detail else ""))
    if not ok:
        raise AssertionError(label)


def laid_out(fight=None, left="stocky", right="lanky"):
    bodies = {"left": moves.Body(CARDS[left]), "right": moves.Body(CARDS[right])}
    made = schedule.schedule(fight or FIRST, bodies, MARKS)
    return made["timeline"], made["motions"], bodies


def row(motion, f):
    """Everything a plain motion says about one frame."""
    return [motion["hips"][f], motion["feet"]["l"][f], motion["feet"]["r"][f]] + [motion["turns"][name][f] for name in sorted(motion["turns"])]


def everything(final="knockdown"):
    """A fight with every attack landed and blocked, by each side, and a knockdown to end on."""
    beats = [{"both": "guard", "seconds": 0.3}]
    for name in sorted(moves.STRIKES):
        for side in ("left", "right"):
            result = moves.STRIKES[name]["causes"]
            beats.append({"by": side, "move": name, "result": "heavy" if result == "knockdown" else result, "wait": 0.2})
            beats.append({"by": side, "move": name, "result": "blocked", "wait": 0.2})
    beats.append({"by": "left", "move": "haymaker", "result": final, "wait": 0.2})
    beats.append({"both": "guard", "seconds": 1.5})
    return {"start_apart_m": 1.6, "beats": beats}


def test_frame_data():
    """every attack has startup, active and recovery frames, reaches its stretched pose on the contact frame and holds it."""
    body, other = moves.Body(CARDS["stocky"]), moves.Body(CARDS["lanky"])
    stood = moves.guard(other)
    for name, card in sorted(moves.STRIKES.items()):
        def spot_of(side, under):
            spot = moves.target_on(other, stood, card["aims"], (0.0, -1.0, 0.0), side, under)
            return (-spot[0], -1.0 - spot[1], spot[2])
        blow = moves.strike(body, name, spot_of)
        at = {k["at"]: k for k in blow["keys"]}
        s, a, r = card["startup"], card["active"], card["recovery"]
        check("%s: startup %d, active %d, recovery %d; contact on frame %d, held to %d, back in guard by %d" % (name, s, a, r, s, s + a - 1, s + a - 1 + r),
              s >= 2 and a >= 1 and r > a and blow["contact"] == s and at[s]["pose"] is at[s + a - 1]["pose"] and max(at) == s + a - 1 + r
              and min(at) < s and card["causes"] in moves.REACTIONS and card["hitstop"] >= 2)
        check("%s: wind-up shorter than the way back (snappy out, slower home)" % name, s <= r)


def test_reaction_starts_on_the_active_frame():
    """the defender stands in guard until the attacker's first active frame, and his reaction starts on that frame."""
    timeline, motions, bodies = laid_out()
    cards = [b for b in timeline["beats"] if "contact" in b]
    check("the first fight has %d exchanges, each with its frames" % len(cards), len(cards) == len(timeline["hits"]) >= 10)
    for card, hit in zip(cards, timeline["hits"]):
        c = hit["frame"]
        taker, hitter = motions[hit["on"]], motions[hit["by"]]
        check("%s %s: contact on frame %d = its start %d + startup %d" % (hit["by"], hit["move"], c, card["start"], card["startup"]), c == card["start"] + card["startup"] == card["contact"])
        turned = max(abs(a - b) for name in ("head", "chest") for a, b in zip(taker["turns"][name][c], taker["turns"][name][c - 1]))
        moved = max(abs(a - b) for a, b in zip(taker["hips"][c], taker["hips"][c - 1]))
        check("   the man hit changes on frame %d (a turn of %.3f, the hips %.3f)" % (c, turned, moved), turned > 0.02 or moved > 0.01)
        if not hit["blocked"]:
            quiet = max(abs(a - b) for f in range(card["start"], c) for name in taker["turns"] for a, b in zip(taker["turns"][name][f], taker["turns"][name][card["start"]]))
            check("   and stood in guard for the %d frames before it" % (c - card["start"]), quiet < 1e-6)
        check("   the attacker's stretched pose is held for its %d active frames" % card["active"],
              all(row(hitter, f) == row(hitter, c) for f in range(c, c + hit["hitstop"] + card["active"])))


def test_hitstop():
    """on the contact frame both fighters hold still for the blow's hitstop frames, and then go on."""
    timeline, motions, bodies = laid_out()
    for hit in timeline["hits"]:
        c, stop = hit["frame"], hit["hitstop"]
        want = moves.KNOCKOUT_HITSTOP if hit["reaction"] == "knockdown" else max(2, round(moves.STRIKES[hit["move"]]["hitstop"] * (moves.BLOCKED_HITSTOP if hit["blocked"] else 1.0)))
        still = all(row(m, f) == row(m, c) for m in motions.values() for f in range(c, c + stop + 1))
        goes_on = any(row(m, c + stop + 1) != row(m, c) for m in motions.values())
        check("%s %s at %d: both still for %d frames, moving again on frame %d" % (hit["by"], hit["move"], c, stop, c + stop + 1), still and goes_on and stop == want)
    stops = {h["move"] + (" blocked" if h["blocked"] else ""): h["hitstop"] for h in timeline["hits"]}
    check("a jab freezes 3 frames, a heavy blow 6 to 8, the knockout longest (%s)" % stops,
          stops["jab"] == 3 and 6 <= stops["cross"] <= 8 and max(stops.values()) == timeline["hits"][-1]["hitstop"] == moves.KNOCKOUT_HITSTOP)
    total = sum(h["hitstop"] for h in timeline["hits"])
    check("the fight is %d frames (%.1f s), %d of them freezes" % (timeline["frames"], timeline["seconds"], total), 20.0 <= timeline["seconds"] <= 25.0)


def fist_checks(timeline, motions, bodies, label):
    off = schedule.fist_and_spot(timeline, motions, bodies, MARKS)
    check("%s: every fist is on its spot on the contact frame (furthest %.1f cm)" % (label, max(off)), max(off) <= FIST_CM, off)
    for hit in timeline["hits"]:
        taker, body = motions[hit["on"]], bodies[hit["on"]]
        at = body.joints(schedule.pose_of(taker, body, hit["frame"] - 1))  # the man hit, the frame before
        most = ON_HIM_CM
        if hit["blocked"]:
            aimed, what = moves.mix(at["fist_l"], at["fist_r"], 0.5), "guarding fists"
        elif moves.STRIKES[hit["move"]]["aims"] == "low":
            aimed, what = moves.mix(at["spine"], at["chest"], 0.55), "chest"
            most = 100.0 * body.chest_front + 10.0  # a thick chest keeps a fist further from its middle
        else:
            aimed, what = at["head_middle"], "head"
        gap = 100.0 * math.dist(schedule.set_point(MARKS[hit["on"]], aimed), hit["at"])
        check("   %s %s%s at %d: the fist is %.1f cm from the middle of his %s" % (hit["by"], hit["move"], " (blocked)" if hit["blocked"] else "", hit["frame"], gap, what),
              (0.0 if hit["blocked"] else 3.0) <= gap <= most)


def test_fist_reaches_its_spot():
    """on the contact frame the fist is on the spot it was built for, and that spot is on the other man."""
    timeline, motions, bodies = laid_out()
    fist_checks(timeline, motions, bodies, "the first fight")


def lowest(motion, body):
    """The lowest any joint gets over the whole motion, in metres above the mat, and where."""
    low = (9.0, "", 0)
    for f in range(motion["frames"] + 1):
        at = body.joints(schedule.pose_of(motion, body, f))
        for name, p in at.items():
            if p[2] < low[0]:
                low = (p[2], name, f)
        for tag in ("l", "r"):
            if motion["feet"][tag][f][2] < 0.0:
                low = (motion["feet"][tag][f][2], "foot_" + tag, f)
    return low


def test_mat():
    """nothing goes under the mat, and a man knocked down ends on it, lying still."""
    timeline, motions, bodies = laid_out()
    for side in ("left", "right"):
        low = lowest(motions[side], bodies[side])
        check("%s: the lowest joint is %.1f cm above the mat (%s, frame %d)" % (side, 100 * low[0], low[1], low[2]), low[0] > 0.02)
    down = [side for side, f in timeline["fighters"].items() if f["down"]]
    check("one man is down at the end (%s)" % down, down == [timeline["hits"][-1]["on"]])
    m, body = motions[down[0]], bodies[down[0]]
    last = m["frames"]
    at = body.joints(schedule.pose_of(m, body, last))
    check("he lies on his back: hips %.0f cm up, head %.0f cm up, %.0f cm apart along the mat" % (100 * at["hips"][2], 100 * at["head"][2], 100 * math.dist(at["hips"][:2], at["head"][:2])),
          at["hips"][2] < body.back + 0.03 and at["head"][2] < 0.4 and math.dist(at["hips"][:2], at["head"][:2]) > 0.5)
    check("and lies still for the last second", all(row(m, f) == row(m, last) for f in range(last - 30, last)))
    hit = timeline["hits"][-1]
    fall = [body.joints(schedule.pose_of(m, body, f))["hips"][2] for f in range(hit["frame"], hit["frame"] + hit["hitstop"] + moves.REACTIONS["knockdown"] + 1)]
    land = min(range(len(fall)), key=lambda i: fall[i])
    check("a long fall (%d frames to the mat) and a small bounce (%.1f cm)" % (land - hit["hitstop"], 100 * (max(fall[land:]) - fall[land])),
          14 <= land - hit["hitstop"] <= 24 and 0.02 < max(fall[land:]) - fall[land] < 0.12)


def limit_checks(motions, bodies, label):
    for side in ("left", "right"):
        worst = {}
        for f in range(motions[side]["frames"] + 1):
            for name, over in moves.past_limits(bodies[side], schedule.pose_of(motions[side], bodies[side], f), LIMIT_SLACK).items():
                if over > worst.get(name, (0.0, 0))[0]:
                    worst[name] = (over, f)
        check("%s, %s: no joint is asked past its limit" % (label, side), not worst, worst)


def test_limits():
    """no pose asks a joint for more than rig.py's limits allow (what animate.py would report as clamped)."""
    timeline, motions, bodies = laid_out()
    limit_checks(motions, bodies, "the first fight")


def test_every_body():
    """the same moves, every one landed and blocked, fit either body against the other, in either stance."""
    for left, right, stances in (("stocky", "lanky", ("usual", "mirror")), ("lanky", "stocky", ("usual", "usual")), ("stocky", "stocky", ("mirror", "usual")), ("lanky", "lanky", ("usual", "mirror"))):
        fight = everything()
        fight["fighters"] = {"left": {"stance": stances[0]}, "right": {"stance": stances[1]}}
        timeline, motions, bodies = laid_out(fight, left, right)
        label = "%s (%s) against %s (%s)" % (left, stances[0], right, stances[1])
        check("%s: %d blows in %.1f s" % (label, len(timeline["hits"]), timeline["seconds"]), len(timeline["hits"]) == 4 * len(moves.STRIKES) + 1)
        fist_checks(timeline, motions, bodies, label)
        limit_checks(motions, bodies, label)
        for side in ("left", "right"):
            low = lowest(motions[side], bodies[side])
            check("%s, %s: nothing under the mat (lowest %.1f cm, %s)" % (label, side, 100 * low[0], low[1]), low[0] > 0.02)
        stepped = max(h["stepped_in_cm"] for h in timeline["hits"])
        check("%s: the longest step in is %.0f cm" % (label, stepped), stepped <= 100.0 * moves.MOST_LUNGE * max(b.leg for b in bodies.values()) + 0.1)


def test_feet():
    """a planted foot stays where it was put; shuffle steps move one foot at a time."""
    timeline, motions, bodies = laid_out()
    for side, m in motions.items():
        slid, both_up = 0.0, 0
        for f in range(1, m["frames"] + 1):
            for tag in ("l", "r"):
                a, b = m["feet"][tag][f - 1], m["feet"][tag][f]
                if a[5] and b[5]:
                    slid = max(slid, math.hypot(b[0] - a[0], b[1] - a[1]) * bodies[side].leg)
        walk = [b for b in timeline["beats"] if b["beat"].get("both") in ("shuffle", "circle")]
        for beat in walk:
            both_up += sum(1 for f in range(beat["from_frame"], beat["to_frame"] + 1) if not m["feet"]["l"][f][5] and not m["feet"]["r"][f][5])
        check("%s: a planted foot slides %.2f cm at most; in %d stretches of footwork both feet are never off the mat at once" % (side, 100 * slid, len(walk)), slid < 0.001 and both_up == 0)
    first = timeline["beats"][0]
    dips = [motions["left"]["hips"][f][2] for f in range(first["from_frame"], first["to_frame"])]
    check("guard bounces lightly: the hips rise and fall %.1f cm" % (100 * (max(dips) - min(dips)) * bodies["left"].leg), 0.01 < (max(dips) - min(dips)) * bodies["left"].leg < 0.05)


def test_mirror():
    """the other stance is the same motion in a mirror."""
    fight = {"start_apart_m": 1.5, "beats": [{"both": "guard", "seconds": 0.5}, {"both": "shuffle", "apart_m": 0.9}, {"both": "guard", "seconds": 0.3}]}
    usual = laid_out(dict(fight, fighters={"left": {"stance": "usual"}}))[1]["left"]
    other = laid_out(dict(fight, fighters={"left": {"stance": "mirror"}}))[1]["left"]
    worst = 0.0
    for f in range(usual["frames"] + 1):
        worst = max(worst, abs(usual["hips"][f][0] + other["hips"][f][0]), abs(usual["feet"]["l"][f][0] + other["feet"]["r"][f][0]),
                    abs(usual["feet"]["l"][f][4] + other["feet"]["r"][f][4]))
        a, b = usual["turns"]["upper_arm_l"][f], other["turns"]["upper_arm_r"][f]
        sign = 1.0 if a[0] * b[0] + a[1] * b[1] - a[2] * b[2] - a[3] * b[3] > 0 else -1.0
        worst = max(worst, max(abs(a[i] - sign * (b[i] if i < 2 else -b[i])) for i in range(4)))
    check("left and right change places, to %.5f" % worst, worst < 1e-4)


def test_script():
    """a fight script that asks for what can't be is told why."""
    def told(beats, word):
        try:
            laid_out({"beats": beats})
        except ValueError as why:
            return word in str(why)
        return False

    check("an attack nobody knows", told([{"by": "left", "move": "headbutt"}], "headbutt"))
    check("a result nobody knows", told([{"by": "left", "move": "jab", "result": "explodes"}], "explodes"))
    check("a blow at a man who is down", told([{"by": "left", "move": "jab", "result": "knockdown"}, {"by": "left", "move": "jab"}], "down"))
    timeline = laid_out({"beats": [{"by": "left", "move": "jab"}]})[0]
    check("a blow with no result named causes the move's own reaction (%s)" % timeline["hits"][0]["reaction"], timeline["hits"][0]["reaction"] == moves.STRIKES["jab"]["causes"])
    before = copy.deepcopy(FIRST)
    laid_out()
    check("the fight script is only read", before == FIRST)


TESTS = [test_frame_data, test_reaction_starts_on_the_active_frame, test_hitstop, test_fist_reaches_its_spot, test_mat, test_limits, test_every_body, test_feet, test_mirror, test_script]


def main() -> int:
    failed = 0
    for test in TESTS:
        print("%s: %s" % (test.__name__[5:], test.__doc__))
        try:
            test()
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("    FAILED: %s: %s" % (type(e).__name__, str(e)[:800]))
    print("%d of %d fight tests pass" % (len(TESTS) - failed, len(TESTS)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
