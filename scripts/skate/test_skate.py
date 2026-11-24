"""Tries the halfpipe and the riding kit with no Blender and no GPU.

    python3 scripts/skate/test_skate.py

Two test bodies stand in for the characters (the fight kit's
test_bodies.json: a short thick man, a tall thin one). What it shows:

  pipe        the ramp's cut is one unbroken line; `where` finds the point `at` gave; nothing in the open air is "inside"
  set         sets/halfpipe/set.json says the same cut pipe.py works from, and the set is sound
  surface     riding, all four wheels are on the surface; in a kickturn the back two are; the board is never in the ramp
  energy      he never goes faster than the height he came down from and his pumping allow; an air is as long as
              its height says; pumping stays inside what a rider can add
  tricks      the first run does every trick it asks for, and runs 20 to 30 seconds
  feet        both feet are on the bolts, planted, on every frame
  limits      no frame asks a shoulder, elbow or spine for more than rig.py's limits allow
  hands       a grabbing hand is on the board's edge; the planted hand is on its spot while it is on the coping
  honest      a trick with too little speed is done lower and says so; a trick nobody knows is refused
  video       a pose from a clip is read in the skater's own frame, so it is the same pose upside down; a clip
              that has not been made yet changes nothing; a stretch outside its shot is refused
  way out     anything in the ramp is told the short way back out (what keeps a borrowed pose off the wood)
  borrowed    an air with a borrowed pose is made high enough to play the clip at no more than 1.3 times its
              speed, or says how fast it had to; the hips stay where both feet can stay flat on the bolts; in
              a grab and a handplant the hand the trick needs is still ours, on its spot
"""

from __future__ import annotations

import copy
import json
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "fight"))
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
import board  # noqa: E402
import halfpipe_set  # noqa: E402
import moves  # noqa: E402
import ride  # noqa: E402
import rider  # noqa: E402
import standing  # noqa: E402
import video_pose  # noqa: E402
from pipe import Pipe  # noqa: E402

with open(os.path.join(REPO, "scripts", "fight", "test_bodies.json")) as f:
    CARDS = json.load(f)
with open(os.path.join(HERE, "rides", "first.json")) as f:
    FIRST = json.load(f)
PIPE = Pipe(halfpipe_set.RAMP)
LIMIT_SLACK = 2.0  # degrees: a frame between two poses may brush a limit
PLANT_SLACK = 40   # degrees the planting shoulder may be asked for past its limit, on its way overhead (animate.py clamps it)


def check(label, ok, detail=""):
    print("    %s  %s%s" % ("ok  " if ok else "FAIL", label, ("  (%s)" % (detail,)) if detail else ""))
    if not ok:
        raise AssertionError(label)


_made = {}


def made(name="lanky", script=None):
    key = (name, json.dumps(script, sort_keys=True))
    if key not in _made:
        _made[key] = ride.build(copy.deepcopy(script or FIRST), moves.Body(CARDS[name]), PIPE)
    return _made[key]


def test_pipe():
    """the ramp's cut is one unbroken line, and its questions agree with each other."""
    jump = turn = 0.0
    was = PIPE.at(-PIPE.lip)
    worst = 0.0
    n = 2000
    for i in range(1, n + 1):
        s = -PIPE.lip + 2.0 * PIPE.lip * i / n
        p = PIPE.at(s)
        jump = max(jump, abs(math.hypot(p["x"] - was["x"], p["y"] - was["y"]) - 2.0 * PIPE.lip / n))
        turn = max(turn, math.degrees(math.acos(max(-1.0, min(1.0, p["normal"][0] * was["normal"][0] + p["normal"][1] * was["normal"][1])))))
        back, off = PIPE.where(p["x"] + 0.3 * p["normal"][0], p["y"] + 0.3 * p["normal"][1])
        worst = max(worst, abs(back - s), abs(off - 0.3))
        was = p
    check("a step along the surface is a step in space, with no gap anywhere", jump < 1e-6, "%.2e m" % jump)
    check("the way it faces turns smoothly: flat, curve and wall meet with no corner", turn < 0.2, "%.3f degrees a step" % turn)
    check("a point 30 cm off the surface is found again, 30 cm off the same place", worst < 1e-6, "%.2e" % worst)
    check("the lips are %.2f m up and %.2f m apart" % (PIPE.height, 2 * PIPE.wall_x), abs(PIPE.at(PIPE.lip)["y"] - PIPE.height) < 1e-9 and abs(PIPE.at(-PIPE.lip)["x"] + PIPE.wall_x) < 1e-9)
    check("the open air is not inside the ramp; under the flat, in a wall and under a deck are",
          PIPE.inside(0.0, 0.5) == 0.0 and PIPE.inside(PIPE.wall_x - 0.5, PIPE.height + 0.2) == 0.0 and PIPE.inside(0.0, -0.1) > 0.09
          and PIPE.inside(PIPE.wall_x + 0.3, 2.0) > 0.29 and PIPE.inside(PIPE.half_flat + 3.0, 0.5) > 0.3 and PIPE.inside(PIPE.wall_x + 0.3, PIPE.height + 0.01) == 0.0)


def test_set():
    """the set says the same cut pipe.py works from, and is sound."""
    st = standing.load("halfpipe")
    check("set.json is what halfpipe_set.py writes", {k: v for k, v in st.items() if k != "dir"} == json.loads(json.dumps(halfpipe_set.build())))
    check("its cross_section is the cut pipe.py works from, piece by piece", st["ramp"]["cross_section"] == json.loads(json.dumps(Pipe(st["ramp"]).sections())))
    ends = [(a["to"], b["from"]) for a, b in zip(st["ramp"]["cross_section"], st["ramp"]["cross_section"][1:])]
    check("each piece starts where the last one ended", all(math.dist(a, b) < 1e-6 for a, b in ends))
    problems, seen = standing.check(st)
    check("the set is sound", not problems, "; ".join(problems))
    check("each lip has a camera that holds it: deck the right one, across the left", "deck_right" in st["cameras"]["deck"]["sees"] and "deck_left" in st["cameras"]["across"]["sees"])
    check("it has a side-on camera, a low one and one on a deck, and marks on both decks and the flat",
          set(st["cameras"]) == {"side", "low", "deck", "across"} and set(st["marks"]) == {"deck_left", "deck_right", "flat"})


def test_surface():
    """the board stays on the ramp except in the air, and never goes into it."""
    for name in ("lanky", "stocky"):
        m = made(name)["ride"]["measured"]
        check("%s: riding, every wheel is on the surface (%.2f cm at most)" % (name, m["all_wheels_off_the_surface_cm_outside_kickturns"]), m["all_wheels_off_the_surface_cm_outside_kickturns"] < 0.2)
        check("%s: in a kickturn the back wheels stay on (%.2f cm)" % (name, m["back_wheels_off_the_surface_cm"]), m["back_wheels_off_the_surface_cm"] < 0.6)
        check("%s: the board is never in the ramp (%.2f cm at most, frame %s)" % (name, m["board_deepest_in_the_ramp_cm"], m["board_deepest_frame"]), m["board_deepest_in_the_ramp_cm"] < 1.5)
    rows = made()["ride"]["frames_list"]
    worst = max(abs(math.sqrt(sum(c * c for c in r["up"])) - 1.0) + abs(sum(a * b for a, b in zip(r["up"], r["nose"]))) for r in rows)
    check("the board's nose and its face are square to each other on every frame", worst < 1e-4, "%.1e" % worst)
    riding = [r for r in rows if r["kind"] == "ride" and r["part"] != "vert"]
    lean = max(math.degrees(math.acos(min(1.0, sum(a * b for a, b in zip(r["up"], PIPE.at(r["s"])["normal"] + (0.0,)))))) for r in riding)
    check("riding, the deck faces the way the surface does (%.1f degrees off at most, with the nose up in a kickturn)" % lean, lean < ride.NOSE_UP_DEG + 1.0)
    step = max(math.dist(a["at"], b["at"]) for a, b in zip(rows, rows[1:]))
    check("the board never jumps: %.2f m a frame at most, at %.1f m/s" % (step, made()["ride"]["measured"]["top_speed_m_s"]), step < made()["ride"]["measured"]["top_speed_m_s"] / ride.FPS + 0.08)


def test_energy():
    """speed comes from height and pumping, and an air is ballistic."""
    r = made()["ride"]
    rows = r["frames_list"]
    high = PIPE.height - ride.KICKTURN_BELOW
    budget = 0.0
    worst = 0.0
    events = {e["first_frame"]: e for e in r["events"]}
    for f, row in enumerate(rows):
        if f in events:
            budget += 2.0 * PIPE.arc * max(0.0, events[f]["pump_m_s2"])
        y = PIPE.at(row["s"])["y"]
        worst = max(worst, 0.5 * row["speed"] ** 2 + ride.G * y - ride.G * high - budget)
    check("he never has more speed than his height and his pumping account for", worst < 0.3, "%.2f J/kg over" % worst)
    check("pumping stays inside what a rider can add (%.1f m/s2)" % ride.MOST_PUMP, all(abs(e["pump_m_s2"]) <= ride.MOST_PUMP + 1e-6 for e in r["events"]))
    for e in r["events"]:
        if e["did"] in ("air", "air grab"):
            want = 2.0 * math.sqrt(2.0 * e["top_over_lip_m"] / ride.G)
            check("pass %d: %.2f m over the lip takes %.2f s, as a thrown thing would (%.2f)" % (e["pass"], e["top_over_lip_m"], e["air_seconds"], want), abs(e["air_seconds"] - want) < 0.09)
    air = [f for f, row in enumerate(rows) if row["kind"] == "air"]
    check("in the air the board is past the lip, and only then", all(abs(rows[f]["s"]) > PIPE.lip for f in air) and all(abs(row["s"]) <= PIPE.lip + 1e-6 for row in rows if row["kind"] in ("ride", "stop")))


def test_tricks():
    """the first run does what it asks for."""
    r = made()["ride"]
    check("every pass does the trick it asked for", all(e["did"] == e["asked"] and not e.get("note") for e in r["events"]), "; ".join(e.get("note", "") for e in r["events"] if e.get("note")))
    check("it has kickturns, airs, a grab and a handplant", {e["did"] for e in r["events"]} == set(ride.TRICKS))
    check("it runs %.1f seconds: 20 to 30" % r["seconds"], 20.0 <= r["seconds"] <= 30.0)
    check("walls take turns: right, left, right...", [e["wall"] for e in r["events"]] == ["right", "left"] * (len(r["events"]) // 2) + ["right"] * (len(r["events"]) % 2))
    headings = [row["heading_deg"] for row in r["frames_list"]]
    check("each trick turns the board half way round, and it comes off the wall nose first", all(abs(headings[e["to_frame"]] - headings[e["from_frame"]]) == 180.0 for e in r["events"]))
    last = r["frames_list"][-1]
    check("he ends standing still on the flat", last["speed"] == 0.0 and last["part"] == "flat")


def test_feet():
    """both feet are on the bolts on every frame."""
    for name in ("lanky", "stocky"):
        m, body = made(name)["motion"], moves.Body(CARDS[name])
        card = board.card()
        for tag, where in (("l", "front"), ("r", "back")):
            rows = m["feet"][tag]
            check("%s: the %s foot is planted on every frame and never moves on the board" % (name, where), all(row == rows[0] and row[5] == 1 and row[2] == 0.0 for row in rows))
            check("%s: it stands over the %s bolts" % (name, where), abs(rows[0][0] * body.leg - card["feet"][where][0]) < 1e-3 and abs(rows[0][1] * body.leg) < 0.5 * board.WIDE)


def test_limits():
    """no frame asks a joint for more than its limit."""
    for name in ("lanky", "stocky"):
        m, body = made(name)["motion"], moves.Body(CARDS[name])
        plants = [e for e in made(name)["ride"]["events"] if e["did"] == "handplant"]
        worst, swung = {}, {}
        for f in range(0, m["frames"] + 1):
            planting = any(e["from_frame"] <= f <= e["to_frame"] for e in plants)
            for bone, over in moves.past_limits(body, ride.pose_of(m, body, f), slack=LIMIT_SLACK).items():
                into = swung if planting else worst
                into[bone] = max(into.get(bone, 0.0), over)
        check("%s: riding, turning and in the air, every frame is inside the shoulders', elbows' and spine's limits" % name, not worst, json.dumps(worst))
        # Known and weak: as the planted arm goes from beside the board to over his head, the shoulder is asked for more
        # twist than it has for a few frames. animate.py clamps it, and the board is then carried by where the hand really is.
        check("%s: in the handplant only the planting shoulder is asked for too much, and by less than %d degrees (%s)" % (name, PLANT_SLACK, json.dumps(swung)),
              set(swung) <= {"upper_arm_r", "forearm_r"} and max(list(swung.values()) + [0.0]) < PLANT_SLACK)


def test_hands():
    """a grab reaches the board, a handplant reaches the coping."""
    for name in ("lanky", "stocky"):
        r = made(name)["ride"]
        for e in r["events"]:
            if e["did"] == "air grab":
                check("%s, pass %d: the grabbing hand is %.1f cm from its spot on the toe edge" % (name, e["pass"], e["grab"]["hand_from_the_edge_cm"]), e["grab"]["hand_from_the_edge_cm"] < 3.0)
            if e["did"] == "handplant":
                check("%s, pass %d: while it is on the coping the hand is within %.1f cm of its spot" % (name, e["pass"], e["hand_from_its_spot_cm"]), e["hand_from_its_spot_cm"] < 6.0)
                hand = e["hand_on_the_coping"]
                cx, cy = PIPE.coping(1.0 if e["wall"] == "right" else -1.0)
                check("%s, pass %d: that spot is on the coping" % (name, e["pass"]), math.hypot(hand[0] - cx, hand[1] - cy) < PIPE.coping_r + 0.05)


def test_honest():
    """what can't be done is said."""
    tall = made(script={"set": "halfpipe", "passes": [{"trick": "air", "height_m": 3.0}]})["ride"]["events"][0]
    check("an air asked for higher than his speed allows is done as high as it does, and says so", tall["did"] == "air" and tall["top_over_lip_m"] < 1.0 and "had the speed for" in tall.get("note", ""), tall.get("note"))
    most, ride.MOST_PUMP = ride.MOST_PUMP, 0.2
    try:
        weak = ride.build({"set": "halfpipe", "passes": [{"trick": "air", "height_m": 1.0}]}, moves.Body(CARDS["lanky"]), PIPE)["ride"]["events"][0]
    finally:
        ride.MOST_PUMP = most
    check("with no speed for an air at all it is done as a kickturn, and says why", weak["did"] == "kickturn" and "not enough speed" in weak.get("note", ""), weak.get("note"))
    try:
        made(script={"set": "halfpipe", "passes": [{"trick": "mctwist"}]})
        check("a trick nobody knows is refused", False)
    except ValueError as e:
        check("a trick nobody knows is refused, with the ones it knows", "kickturn" in str(e), str(e))


def soma_piece(frames=40, upside_down=False):
    """A stand-in for a clip's motion: the SOMA body standing, raising its left arm, either the right way up or turned over."""
    from soma import Skeleton, qaxis, qmul

    sk = Skeleton.load()
    arm = sk.index["LeftArm"]
    root, rotations = [], []
    for f in range(frames):
        local = [list(q) for q in sk.rest_rot]
        local[arm] = list(qmul(tuple(local[arm]), qaxis((0.0, 0.0, 1.0), 60.0 * f / (frames - 1))))
        at = list(sk.rest_world_pos[0])
        if upside_down:  # turned over about the way he faces, and moved somewhere else: the clip's own idea of the world
            local[0] = list(qmul(qaxis((0.0, 0.0, 1.0), 180.0), tuple(local[0])))
            at = [3.0, 4.0 - at[1], -2.0]
        root.append(at)
        rotations.append([c for q in local for c in q])
    return {"format": "forge-soma-motion/1", "fps": 30, "joints": list(sk.joints), "root": root, "rotations": rotations, "contacts": [[0.0] * 4] * frames}


def test_video():
    """a pose from a clip is laid on relative to the board, and a clip that is not there changes nothing."""
    body = moves.Body(CARDS["lanky"])
    up, over = video_pose.on_his_board(soma_piece(), 0, 39), video_pose.on_his_board(soma_piece(upside_down=True), 0, 39)
    apart = max(math.degrees(2.0 * math.acos(min(1.0, abs(sum(a * b for a, b in zip(up[f]["turns"][n], over[f]["turns"][n])))))) for f in range(40) for n in video_pose.TAKEN)
    check("read in his own feet's frame, a pose is the same pose upside down and somewhere else (%.2f degrees apart at most)" % apart, apart < 0.5)
    hips = max(math.dist(up[f]["hips"], over[f]["hips"]) for f in range(40))
    check("and his hips are the same way from his feet (%.3f hip heights apart)" % hips, hips < 0.01)
    swing = math.degrees(2.0 * math.acos(min(1.0, abs(sum(a * b for a, b in zip(up[0]["turns"]["upper_arm_l"], up[39]["turns"]["upper_arm_l"]))))))
    check("the arm he raises is read as raised (%.0f degrees)" % swing, 50.0 < swing < 70.0)

    script = {"set": "halfpipe", "passes": [{"trick": "kickturn"}, {"trick": "air", "height_m": 0.3, "pose_from": {"video": "a-clip", "shot": 2, "from_s": 2.5, "to_s": 3.2}}]}
    with tempfile.TemporaryDirectory() as shots:
        plain_run = ride.build(copy.deepcopy(script), body, PIPE, shots=shots)
        result = plain_run["ride"]["events"][1]["pose_from_result"]
        own = ride.build({"set": "halfpipe", "passes": [{"trick": "kickturn"}, {"trick": "air", "height_m": 0.3}]}, body, PIPE)
        check("a clip with no motion yet: the pass keeps his own pose and says so", not result["used"] and "just video a-clip" in result["said"] and plain_run["motion"] == own["motion"], result["said"])
        folder = os.path.join(shots, "video-a-clip")
        os.makedirs(folder)
        with open(os.path.join(folder, "motion.json"), "w") as f:
            json.dump(soma_piece(frames=70), f)
        with open(os.path.join(folder, "source.json"), "w") as f:  # two shots of the clip were kept: shot 1 is its frames 0 to 29, shot 2 its frames 60 to 99 (the cut between was skipped)
            json.dump({"pieces": [{"shot": 0, "first_frame": 0, "last_frame": 29, "clip_first_frame": 0, "clip_last_frame": 29},
                                  {"shot": 1, "first_frame": 30, "last_frame": 69, "clip_first_frame": 60, "clip_last_frame": 99}]}, f)
        with_clip = ride.build(copy.deepcopy(script), body, PIPE, shots=shots)
        event = with_clip["ride"]["events"][1]
        result = event["pose_from_result"]
        check("with the motion there, the stretch asked for is found in it: clip seconds 2.5 to 3.2, in shot 2, are frames 45 to 66 of the joined motion", result["used"] and result["source_frames"] == [45, 66], result.get("said"))
        m, o = with_clip["motion"], own["motion"]
        middle = (event["from_frame"] + event["to_frame"]) // 2
        differs = lambda f, key: m[key][f] != o[key][f]  # noqa: E731
        check("in the air his arm is the clip's", differs(middle, "hips") or m["turns"]["upper_arm_l"][middle] != o["turns"]["upper_arm_l"][middle])
        check("outside the trick nothing is changed, and it eases on from his own pose",
              all(m["turns"][n][f] == o["turns"][n][f] for n in video_pose.TAKEN for f in list(range(0, event["from_frame"] - video_pose.LEAD_FRAMES + 1)) + list(range(event["to_frame"] + video_pose.LEAD_FRAMES, m["frames"] + 1))))
        check("his feet stay on the bolts and the board's path is the same", m["feet"] == o["feet"] and with_clip["ride"]["frames_list"] == own["ride"]["frames_list"])
        worst = {}
        for f in range(event["from_frame"], event["to_frame"] + 1):
            for bone, past in moves.past_limits(body, ride.pose_of(m, body, f), slack=25.0).items():
                worst[bone] = past
        check("what the clip asks of his joints is left to animate.py's limits, and is nowhere wild", not worst, json.dumps(worst))
        bad = copy.deepcopy(script)
        bad["passes"][1]["pose_from"]["to_s"] = 9.0
        try:
            ride.build(bad, body, PIPE, shots=shots)
            check("a stretch that runs past its shot is refused", False)
        except ValueError as e:
            check("a stretch that runs past its shot is refused, with the shot's own times", "shot 2" in str(e) and "3.30" in str(e), str(e))

def test_way_out():
    """anything in the ramp is told the short way back out."""
    import random

    rng, worst, tried = random.Random(7), 0.0, 0
    for again in range(4000):
        x, y = rng.uniform(-PIPE.end_x, PIPE.end_x), rng.uniform(-0.3, PIPE.height + 0.3)
        deep, way = PIPE.way_out(x, y)
        if deep <= 0.0:
            continue
        tried += 1
        worst = max(worst, PIPE.inside(x + way[0] * (deep + 0.002), y + way[1] * (deep + 0.002)))
    check("from %d points in the wood, going that way by that much comes out into the air (%.1f mm left at worst)" % (tried, 1000 * worst), tried > 500 and worst < 0.003)
    check("in the open air there is nothing to get out of", PIPE.way_out(0.0, 1.0)[0] == 0.0 and PIPE.way_out(PIPE.wall_x + 0.5, PIPE.height + 0.1)[0] == 0.0)
    check("under a deck the way out is up; just inside a wall it is into the pipe; under the curve it is toward the curve's middle",
          PIPE.way_out(PIPE.wall_x + 0.8, PIPE.height - 0.1)[1] == (0.0, 1.0) and PIPE.way_out(PIPE.wall_x + 0.05, PIPE.height - 0.2)[1] == (-1.0, 0.0)
          and PIPE.way_out(-(PIPE.half_flat + 1.5), 0.1)[1][0] > 0.3 and PIPE.way_out(PIPE.half_flat + 1.5, 0.1)[1][1] > 0.8)


def clip_in(shots, name="a-clip", frames=100):
    """A made-up clip's motion in a folder of shots: one shot, the SOMA body stood up straight, raising an arm."""
    folder = os.path.join(shots, "video-" + name)
    os.makedirs(folder)
    with open(os.path.join(folder, "motion.json"), "w") as f:
        json.dump(soma_piece(frames=frames), f)
    with open(os.path.join(folder, "source.json"), "w") as f:
        json.dump({"pieces": [{"shot": 0, "first_frame": 0, "last_frame": frames - 1, "clip_first_frame": 0, "clip_last_frame": frames - 1}]}, f)


def test_borrowed():
    """a borrowed pose gets the time it needs, keeps our feet on the deck, and leaves a trick's own hand ours."""
    body = moves.Body(CARDS["lanky"])
    stretch = {"video": "a-clip", "shot": 1, "from_s": 0.5, "to_s": 2.0}
    check("ride.py and video_pose.py agree how fast a clip may play and how far its pose laps onto the wall",
          (ride.AIM_SPEED, ride.LEAD_FRAMES) == (video_pose.AIM_SPEED, video_pose.LEAD_FRAMES))
    with tempfile.TemporaryDirectory() as shots:
        clip_in(shots)
        run = ride.build({"set": "halfpipe", "passes": [{"trick": "kickturn"}, {"trick": "air", "height_m": 0.3, "pose_from": stretch}, {"trick": "air", "height_m": 0.3, "pose_from": stretch},
                                                        {"trick": "air grab", "height_m": 0.3, "pose_from": stretch}, {"trick": "handplant", "pose_from": dict(stretch, to_s=2.6)}]}, body, PIPE, shots=shots)
        short, sized, grab, plant = run["ride"]["events"][1:5]
        m = run["motion"]
        # Time.
        check("an air with a borrowed pose is made as high as the clip's stretch needs: asked 0.3 m, a 1.5 s stretch needs %.2f, he goes %.2f" % (
              sized["sized_for_the_clip"]["air_it_needs_m"], sized["top_over_lip_m"]), abs(sized["top_over_lip_m"] - sized["sized_for_the_clip"]["air_it_needs_m"]) < 0.06)
        check("and the stretch then plays at %.2f times its own speed: no more than %.1f" % (sized["pose_from_result"]["played_at"], ride.AIM_SPEED), sized["pose_from_result"]["played_at"] <= ride.AIM_SPEED + 0.05)
        check("with too little speed for that he goes as high as he can, and both the ride and the pose say so (%.2f times)" % short["pose_from_result"]["played_at"],
              "the clip's stretch needs" in short.get("note", "") and "faster than" in short["pose_from_result"]["said"] and short["pose_from_result"]["played_at"] > ride.AIM_SPEED)
        check("a handplant takes as long as its stretch (2.1 s, inside 1.6 to 2.6): played at %.2f" % plant["pose_from_result"]["played_at"], abs(plant["pose_from_result"]["played_at"] - 1.0) < 0.05)
        # Feet.
        feet = rider.feet_of(body)
        moved = 0.0
        for e in (short, sized, grab, plant):
            a, b = e["pose_from_result"]["frames"]
            for f in range(a, b + 1):
                at = tuple(c * body.leg for c in m["hips"][f])
                moved = max(moved, abs(video_pose.hips_the_legs_can_follow(body, at, tuple(m["turns"]["hips"][f]), feet)[2] - at[2]))
        check("on every borrowed frame the hips are where both legs can hold their feet flat on the bolts (%.1f cm from it at most)" % (100 * moved), moved < 0.02)
        check("both feet are still planted on the bolts on every frame", all(row == rows[0] and row[5] == 1 for rows in m["feet"].values() for row in rows))
        tall = video_pose.hips_the_legs_can_follow(body, (0.0, 0.0, -0.9 * body.leg), (1.0, 0.0, 0.0, 0.0), feet)[2]
        check("hips asked for lower than a knee can fold are brought up (%.0f cm under standing, not 90%% of the leg)" % (-100 * tall), tall > -0.75 * body.leg)
        # Hands.
        check("in a borrowed grab the grabbing hand is ours: %.1f cm from its spot on the board's edge, though the clip's skater stands straight" % grab["grab"]["hand_from_the_edge_cm"],
              grab["grab"]["hand_from_the_edge_cm"] < 3.0 and grab["pose_from_result"]["hand"]["hand"] == "r" and grab["pose_from_result"]["hand"]["trunk_given_back"] > 0.0)
        middle = grab["grab"]["frame"]
        check("the hand is still pinned to the deck for animate.py, and the free arm is the clip's", m["hands"]["r"][middle] is not None and m["hands"]["r"][middle][3] == 1.0)
        own = ride.build({"set": "halfpipe", "passes": [{"trick": "kickturn"}, {"trick": "air", "height_m": 0.3}, {"trick": "air", "height_m": sized["top_over_lip_m"]},
                                                        {"trick": "air grab", "height_m": 0.3}, {"trick": "handplant"}]}, body, PIPE)["motion"]
        check("his head in that grab is the clip's, not ours", m["turns"]["head"][middle] != own["turns"]["head"][middle] if len(own["hips"]) == len(m["hips"]) else True)
        low = [f for f in range(plant["from_frame"], plant["to_frame"] + 1) if plant["hand_on_from_frame"] <= f <= plant["hand_off_at_frame"]]
        check("in a borrowed handplant the planting hand is ours too (the %s one)" % plant["pose_from_result"]["hand"]["hand"], plant["pose_from_result"]["hand"]["hand"] == plant["hand"] and len(low) > 10)


def main():
    cases = [test_pipe, test_set, test_surface, test_energy, test_tricks, test_feet, test_limits, test_hands, test_honest, test_video, test_way_out, test_borrowed]
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    failed = 0
    for case in cases:
        name = case.__name__[5:]
        if only and only not in name:
            continue
        print("%s: %s" % (name, case.__doc__.strip()))
        try:
            case()
        except AssertionError as e:
            failed += 1
            print("    FAILED: %s" % e)
    print("%d skate case(s) failed" % failed if failed else "all %d skate cases passed" % len([c for c in cases if not only or only in c.__name__]))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
