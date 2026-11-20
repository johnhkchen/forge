"""Offline tests for the run clips: the sentence and speed, the job, the loop, the run on the spot.

    python3 scripts/motion/test_run_clip.py

No GPU, no worker, no Blender. A pretend worker stands in for Kimodo: for each
sentence it makes a stick-figure run along the path it was given, with legs
that swing at a steady beat, feet that stay where they land, and a body that
drifts a little from stride to stride (so no two strides are quite alike and
the cut has something to choose between). Nobody would want to watch it, but
it has a stride to find, feet to plant and a seam to hide, which is what the
tools here have to get right. None of it comes from anyone's motion data.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import run_clip  # noqa: E402
from soma import X, Y, Skeleton, qaxis, qconj, qmul, qrot, sub  # noqa: E402

SK = Skeleton.load()
FPS = 30

# Three characters as the pipeline leaves them: a brief, how they walk (scripts/test_gaits.json has the
# same answers), and the leg rig.py measured. Numbers from the real runs, Nov 2026.
CAST = {
    "troll": {
        "brief": {"name": "Cave Troll", "description": "A huge, heavy-set cave troll standing in a T-pose, about two and a half meters tall, with short stumpy legs on wide flat feet.", "size_m": 2.6},
        "gait": {"weight": 0.95, "stealth": 0.05, "swagger": 0.6, "stiffness": 0.7, "why": "It lumbers."},
        "measure": {"hip_height": 0.994, "bulk": 0.1688},
    },
    "ninja": {
        "brief": {"name": "Shadow Ninja", "description": "A stocky ninja standing in a T-pose, in a close-fitting hooded cloth suit.", "size_m": 1.75},
        "gait": {"weight": 0.35, "stealth": 0.8, "swagger": 0.12, "stiffness": 0.2, "why": "He moves low."},
        "measure": {"hip_height": 0.922, "bulk": 0.0278},
    },
    "roosevelt": {
        "brief": {"name": "Roosevelt Wrestler 1890s", "description": "A stocky, barrel-chested man in his late thirties. He stands about 1.78 m tall in a T-pose.", "size_m": 1.78},
        "gait": {"weight": 0.6, "stealth": 0.1, "swagger": 0.75, "stiffness": 0.45, "why": "Chest out."},
        "measure": {"hip_height": 0.831, "bulk": 0.0301},
    },
    "lincoln": {
        "brief": {"name": "Young Lincoln Frontier Wrestler", "description": "A tall, lanky young Abraham Lincoln, with a long, rangy build.", "size_m": 1.94},
        "gait": {"weight": 0.35, "stealth": 0.2, "swagger": 0.4, "stiffness": 0.25, "why": "A loping stride."},
        "measure": {"hip_height": 1.001, "bulk": 0.0147},
    },
}


def cast_folders(root: str, names=("troll", "ninja", "roosevelt")) -> dict:
    out = {}
    for name in names:
        card = CAST[name]
        run = os.path.join(root, "2026-11-20T00-00-00-" + name)
        os.makedirs(os.path.join(run, "profiles"), exist_ok=True)
        for file, value in (("brief.json", card["brief"]), ("gait.json", card["gait"]), ("profiles/lowpoly-walk.json", {"rig": {"measure": card["measure"]}})):
            with open(os.path.join(run, file), "w") as f:
                json.dump(value, f)
        out[name] = run
    return out


# ---- the pretend worker ----------------------------------------------------------


def turned(joint: str, axis, degrees: float) -> tuple:
    """A joint's local rotation when it is turned from rest about an axis of the world (as the world lies at rest)."""
    j = SK.index[joint]
    world = SK.rest_world_rot[j]
    return qmul(SK.rest_rot[j], qmul(qconj(world), qmul(qaxis(axis, degrees), world)))


def leg_angle(side: str, ahead: float) -> float:
    """Degrees to swing a straight leg forward so the ball of its foot is `ahead` metres in front of where it rests."""
    reach = sub(SK.rest_world_pos[SK.index[side + "ToeBase"]], SK.rest_world_pos[SK.index[side + "Leg"]])
    lo, hi = -70.0, 70.0
    for _ in range(30):
        mid = (lo + hi) / 2.0
        if qrot(qaxis(X, -mid), reach)[2] - reach[2] < ahead:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def pretend_run(points: list, stride: int, drift: float = 1.0, wander: float = 0.0) -> dict:
    """A stick-figure run along a path of [x, z] points, one a frame: `stride` frames to a stride.

    `drift` scales how much the body changes from one stride to the next; `wander` turns the whole
    clip by that many degrees, as a model that does not quite keep to its path would."""
    count = len(points)
    half = stride / 2.0
    speeds = [math.dist(points[min(f + 1, count - 1)], points[max(f - 1, 0)]) * FPS / (min(f + 1, count - 1) - max(f - 1, 0)) for f in range(count)]
    roots, rows, contacts = [], [], []
    plant = {"Left": None, "Right": None}  # where each foot stands (z), while it is down
    left_off = {"Left": 0.0, "Right": 0.0}
    for f in range(count):
        x, z = points[f]
        slow = math.sin(2 * math.pi * f / 171.0)  # a slow change with no beat in common with the stride
        row = [list(q) for q in SK.rest_rot]
        down = {}
        for side, lead in (("Left", 0.0), ("Right", 0.5)):
            phase = (f / stride + lead) % 1.0
            landing = 0.5 * speeds[f] * half / FPS  # how far ahead of the hips a foot comes down
            knee = 0.0
            if phase < 0.5:
                if plant[side] is None:
                    plant[side] = z + landing - speeds[f] * (phase * stride) / FPS
                ahead = max(-0.6, min(0.6, plant[side] - z))
                left_off[side] = ahead
            else:
                plant[side] = None
                s = (phase - 0.5) / 0.5
                ahead = left_off[side] + (min(0.6, landing) - left_off[side]) * run_clip.smooth(s)
                knee = 70.0 * math.sin(math.pi * s)
            down[side] = phase < 0.5
            row[SK.index[side + "Leg"]] = list(turned(side + "Leg", X, -leg_angle(side, ahead)))
            row[SK.index[side + "Shin"]] = list(turned(side + "Shin", X, knee))
            swing = (25.0 + 8.0 * drift * f / count) * math.cos(2 * math.pi * (f / stride + lead))
            row[SK.index[side + "Arm"]] = list(turned(side + "Arm", Y, swing if side == "Left" else -swing))
        row[SK.index["Spine1"]] = list(turned("Spine1", X, 6.0 + 3.0 * drift * slow))
        root = [x, SK.rest_pos[0][1] - 0.04 + 0.02 * math.cos(4 * math.pi * f / stride) + 0.008 * drift * slow, z]
        roots.append([round(v, 5) for v in root])
        rows.append([round(c, 6) for q in row for c in q])
        contacts.append([1.0 if down["Left"] else 0.0] * 2 + [1.0 if down["Right"] else 0.0] * 2)
    motion = {
        "format": "forge-soma-motion/1",
        "fps": FPS,
        "joints": list(SK.joints),
        "root": roots,
        "rotations": rows,
        "contact_order": list(run_clip.CONTACT_ORDER),
        "contacts": contacts,
    }
    return run_clip.moved(motion, wander, 0.0, 0.0) if wander else motion


def pretend(request: dict) -> dict:
    """What the worker's `text` kind would answer, in shape: every sentence's stretch, one after the other."""
    assert request["kind"] == "text" and 1 <= len(request["prompts"]) <= 8
    points, segments = [], []
    for prompt in request["prompts"]:
        path = next(c for c in prompt["constraints"] if c["type"] == "path")
        assert path["frames"] == list(range(prompt["frames"])) and len(path["points"]) == prompt["frames"]
        segments.append({"name": prompt["text"], "first_frame": len(points), "last_frame": len(points) + prompt["frames"] - 1})
        points += path["points"]
    stride = 18 + int(run_clip.digest(request["prompts"][0]["text"])[:4], 16) % 5
    answer = pretend_run(points, stride)
    answer["segments"] = segments
    answer["made_by"] = {"model": "a pretend worker (scripts/motion/test_run_clip.py)", "seed": request.get("seed", 0)}
    return answer


def to_the_end(folders: list, cache: str, sent: list = None, **more) -> dict:
    """What `baml run runs` does: run a pass, send what it asks for, run it again."""
    for _ in range(3):
        result = run_clip.step(folders, cache, SK, **more)
        if not result["todo"]:
            return result
        for item in result["todo"]:
            with open(os.path.join(cache, item["request"] + ".request.json")) as f:
                request = json.load(f)
            if sent is not None:
                sent.append(request)
            with open(os.path.join(cache, item["request"] + ".json"), "w") as f:
                json.dump(pretend(request), f)
    raise AssertionError("still something to make after three passes")


def steady(speed: float, frames: int = 180) -> list:
    return [[0.0, round(speed * f / FPS, 4)] for f in range(frames)]


# ---- the sentence and the speed ----------------------------------------------------


def test_each_character_gets_a_sentence_and_a_speed_of_its_own():
    root = tempfile.mkdtemp(prefix="forge-run-")
    try:
        runs = cast_folders(root, ("troll", "ninja", "roosevelt", "lincoln"))
        asks = {name: run_clip.ask_for(run, SK) for name, run in runs.items()}
        for name, ask in asks.items():
            # Kimodo's sentences are about "A person": a word on the build, then one manner of running.
            assert ask["prompt"].startswith(("A ", "An ")) and " person runs forward " in ask["prompt"] and ask["prompt"].endswith("."), ask["prompt"]
            assert len(ask["prompt"].split()) <= 28, ask["prompt"]
            assert 90 <= ask["frames"] <= 300, "a sentence makes 3 to 10 seconds"
            # The speed is the leg's: the Froude number times gravity times the leg, square-rooted.
            assert abs(ask["speed_mps"] - math.sqrt(ask["froude"] * 9.81 * ask["leg_m"])) < 0.01, ask
            assert run_clip.SOMA_SPEEDS[0] <= ask["soma_speed_mps"] <= run_clip.SOMA_SPEEDS[1]
            assert ask["leg_from"] == "its lowpoly walk" and ask["traits_from"] == "gait.json"
        assert "huge" in asks["troll"]["prompt"] and "lumbering" in asks["troll"]["prompt"] and "stiff" in asks["troll"]["prompt"]
        assert "low crouch" in asks["ninja"]["prompt"] and "quick" in asks["ninja"]["prompt"] and "stocky" in asks["ninja"]["prompt"]
        assert "proudly" in asks["roosevelt"]["prompt"] and "upright" in asks["roosevelt"]["prompt"]
        assert "tall lanky" in asks["lincoln"]["prompt"] and "loping" in asks["lincoln"]["prompt"]
        # The troll lumbers, the ninja is quick, the long-legged light one is quickest.
        assert asks["troll"]["speed_mps"] < asks["roosevelt"]["speed_mps"] < asks["lincoln"]["speed_mps"]
        assert asks["troll"]["speed_mps"] + 0.5 < asks["ninja"]["speed_mps"]
        assert 2.0 < asks["troll"]["speed_mps"] < 3.0 and 3.0 < asks["ninja"]["speed_mps"] < 4.2
        assert len({ask["hash"] for ask in asks.values()}) == 4
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_character_with_no_walk_or_gait_still_gets_an_ordinary_run():
    root = tempfile.mkdtemp(prefix="forge-run-")
    try:
        run = os.path.join(root, "someone")
        os.makedirs(run)
        with open(os.path.join(run, "brief.json"), "w") as f:
            json.dump({"name": "Someone", "description": "A person in a T-pose.", "size_m": 1.8}, f)
        ask = run_clip.ask_for(run, SK)
        assert ask["prompt"] == "A person runs forward at a steady, even pace."
        assert ask["leg_m"] == 0.9 and "half its height" in ask["leg_from"] and "ordinary adult" in ask["traits_from"]
        assert 2.5 < ask["speed_mps"] < 3.6
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_heavier_is_slower_and_a_longer_leg_is_faster():
    ordinary = dict(run_clip.ORDINARY)
    speeds = [run_clip.run_speed(0.9, dict(ordinary, weight=w))["speed_mps"] for w in (0.1, 0.4, 0.7, 1.0)]
    assert speeds == sorted(speeds, reverse=True) and speeds[0] > 1.3 * speeds[-1]
    assert run_clip.run_speed(1.2, ordinary)["speed_mps"] > run_clip.run_speed(0.6, ordinary)["speed_mps"]
    # Same manner, same Froude number, whatever the size.
    assert run_clip.run_speed(1.2, ordinary)["froude"] == run_clip.run_speed(0.6, ordinary)["froude"]
    # Nothing runs below the speed where walking turns into running.
    assert run_clip.run_speed(0.9, {"weight": 1.0, "stealth": 1.0, "swagger": 0.0, "stiffness": 1.0}, bulk=0.2)["froude"] >= 0.55


# ---- the job ---------------------------------------------------------------------


def test_one_job_carries_every_character_along_one_straight_line():
    root = tempfile.mkdtemp(prefix="forge-run-")
    try:
        runs = cast_folders(root)
        asks = [run_clip.ask_for(run, SK) for run in runs.values()]
        (batch,) = run_clip.batches(asks)
        assert batch[0]["character"] == "Cave Troll" and [a["soma_speed_mps"] for a in batch] == sorted(a["soma_speed_mps"] for a in asks), "slowest first"
        request = run_clip.batch_request(batch)
        assert request["kind"] == "text" and request["tidy"] is True and len(request["prompts"]) == 3
        z_before, all_points = 0.0, []
        for prompt, ask in zip(request["prompts"], batch):
            (path,) = prompt["constraints"]
            assert path["type"] == "path" and prompt["frames"] == ask["frames"] == 180 and prompt["text"] == ask["prompt"]
            assert all(p[0] == 0.0 for p in path["points"]), "straight along +Z"
            steps = [b[1] - a[1] for a, b in zip(path["points"], path["points"][1:])]
            assert all(s > 0 for s in steps)
            # Once the pace has changed, every frame covers the same ground: this character's speed.
            assert all(abs(s * FPS - ask["soma_speed_mps"]) < 0.01 for s in steps[run_clip.RAMP_FRAMES :]), (ask["soma_speed_mps"], steps[30] * FPS)
            assert path["points"][0][1] >= z_before
            z_before = path["points"][-1][1]
            all_points += path["points"]
        # ...and where one character's stretch runs into the next, the line carries on with no jump.
        jumps = [b[1] - a[1] for a, b in zip(all_points, all_points[1:])]
        assert max(abs(b - a) for a, b in zip(jumps[1:], jumps[2:])) < 0.01
        assert all_points[0] == [0.0, 0.0]
        # One job per character, when asked: each line then starts at its own origin.
        alone = run_clip.batches(asks, 1)
        assert len(alone) == 3 and all(run_clip.batch_request(b)["prompts"][0]["constraints"][0]["points"][0] == [0.0, 0.0] for b in alone)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_clips_are_cached_and_only_a_changed_character_is_made_again():
    root = tempfile.mkdtemp(prefix="forge-run-")
    try:
        runs = cast_folders(root)
        folders, cache = list(runs.values()), os.path.join(root, ".run-cache")
        first = run_clip.step(folders, cache, SK)
        assert len(first["todo"]) == 1 and first["todo"][0]["kind"] == "text" and "Cave Troll" in first["todo"][0]["what"]
        assert all(state == "waiting for Kimodo" for state in first["state"].values())
        assert not os.path.exists(os.path.join(runs["troll"], "run", "loop.json"))
        sent = []
        done = to_the_end(folders, cache, sent)
        assert len(sent) == 1 and len(sent[0]["prompts"]) == 3
        files = {name: os.path.join(run, "run", "loop.json") for name, run in runs.items()}
        made = {name: os.path.getmtime(path) for name, path in files.items()}
        for name, run in runs.items():
            with open(os.path.join(run, "run", "clip.json")) as f:
                clip = json.load(f)
            assert len(clip["root"]) == 180 and clip["prompt"] == done["asks"][run]["prompt"] and clip["ask"] == done["asks"][run]["hash"]
            assert done["state"][run]["ask"] == done["asks"][run]["hash"]
        # A second go asks for nothing and writes nothing.
        again = to_the_end(folders, cache, sent)
        assert len(sent) == 1 and again["todo"] == []
        assert {name: os.path.getmtime(path) for name, path in files.items()} == made
        # The ninja is told to walk differently: only its clip is asked for again, alone in its job.
        with open(os.path.join(runs["ninja"], "gait.json"), "w") as f:
            json.dump(dict(CAST["ninja"]["gait"], stealth=0.2), f)
        changed = to_the_end(folders, cache, sent)
        assert len(sent) == 2 and len(sent[1]["prompts"]) == 1 and "low crouch" not in sent[1]["prompts"][0]["text"]
        assert os.path.getmtime(files["troll"]) == made["troll"] and os.path.getmtime(files["roosevelt"]) == made["roosevelt"]
        assert changed["state"][runs["ninja"]]["prompt"] == sent[1]["prompts"][0]["text"]
        # A folder with no gait.json is passed over, not an error.
        prop = os.path.join(root, "a-kettle")
        os.makedirs(prop)
        with_prop = run_clip.step(folders + [prop], cache, SK)
        assert with_prop["todo"] == [] and with_prop["state"][prop].startswith("skipped")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_one_job_per_character_gives_each_its_own_request():
    root = tempfile.mkdtemp(prefix="forge-run-")
    try:
        runs = cast_folders(root)
        sent = []
        done = to_the_end(list(runs.values()), os.path.join(root, ".run-cache"), sent, size=1)
        assert len(sent) == 3 and all(len(r["prompts"]) == 1 for r in sent)
        assert all(isinstance(state, dict) and state["first_equals_last"] for state in done["state"].values())
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---- the loop --------------------------------------------------------------------


def moves_per_frame(loop: dict) -> list:
    """The furthest any joint moves between each frame of a loop and the next, in metres."""
    body = run_clip.bodies(SK, loop)
    whole = [[(p[0] + root[0], p[1], p[2] + root[2]) for p in frame] for frame, root in zip(body, loop["root"])]
    return [max(math.dist(a, b) for a, b in zip(whole[f], whole[f + 1])) for f in range(len(whole) - 1)]


def test_the_cut_is_a_whole_number_of_strides_and_the_best_match_there_is():
    for stride, speed in ((20, 3.0), (23, 2.4), (17, 3.6)):
        clip = pretend_run(steady(speed), stride)
        found = run_clip.find_loop(SK, clip)
        assert found["stride_frames"] == stride and found["stride_sureness"] > 0.9, found
        assert found["frames"] == found["strides"] * stride and 1 <= found["strides"] <= run_clip.MOST_STRIDES, found
        assert found["first_frame"] >= run_clip.SETTLE_FRAMES and found["last_frame"] <= 179 - run_clip.END_FRAMES, found
        # Nothing else it could have chosen is a better match: not another start, not a frame either side.
        straight = run_clip.straightened(SK, clip, found["first_frame"], found["last_frame"])
        body = run_clip.bodies(SK, straight)
        chosen = run_clip.unlike(body, straight, found["first_frame"], found["last_frame"])["cost"]
        for a in range(run_clip.SETTLE_FRAMES, 173 - found["frames"]):
            assert run_clip.unlike(body, straight, a, a + found["frames"])["cost"] >= chosen - 1e-12
        for off in (-3, 3, stride // 2):
            assert run_clip.unlike(body, straight, found["first_frame"], found["last_frame"] + off)["cost"] > 4 * chosen
        assert found["seam_before_blend"]["joints_apart_cm"] < 2.0, found


def test_a_single_stride_wins_only_when_it_matches_much_better():
    # With no drift every stride is the same, so one stride matches exactly as well as two: two are kept.
    even = run_clip.find_loop(SK, pretend_run(steady(3.0), 20, drift=0.0))
    assert even["strides"] >= run_clip.STRIDES_LIKED and even["seam_before_blend"]["worst_joint_cm"] < 0.05, even


def test_the_loop_ends_where_it_began_and_runs_on_the_spot():
    for stride, speed, wander in ((20, 3.0, 0.0), (22, 2.5, 7.0)):
        clip = pretend_run(steady(speed), stride, wander=wander)
        loop = run_clip.make_loop(SK, clip, run_clip.find_loop(SK, clip))
        card = loop["loop"]
        count = card["frames"]
        assert len(loop["root"]) == len(loop["rotations"]) == len(loop["contacts"]) == count + 1
        assert loop["root"][0] == loop["root"][-1] and loop["rotations"][0] == loop["rotations"][-1] and card["first_equals_last"]
        assert count == card["strides"] * stride and abs(card["seconds"] - count / FPS) < 1e-3
        # On the spot: the hips start and end over the origin and never wander more than a few centimetres...
        assert loop["root"][0][0] == 0.0 and loop["root"][0][2] == 0.0
        assert max(math.hypot(r[0], r[2]) for r in loop["root"]) < 0.05
        # ...the speed taken out is the speed it ran at, and it faces the way it ran even if the clip wandered off line.
        assert abs(card["speed_mps"] - speed) < 0.02 * speed, card
        assert max(abs(v) for v in card["faces_deg"]) < 1.0, card
        assert card["steps_per_minute"] == round(2 * 60 * FPS / stride)
        # No jump at the seam: across it, nothing moves further in a frame than it does elsewhere in the loop.
        moves = moves_per_frame(loop)
        blend = card["blend_frames"]
        assert max(moves[-blend:] + moves[:2]) < 1.25 * max(moves[2:-blend]), (max(moves[-blend:]), max(moves[2:-blend]))
        # Played twice over, the join between the two rounds is as smooth as any other frame.
        twice = run_clip.travelling(loop, 2)
        again = moves_per_frame(twice)
        assert all(abs(again[count + k] - again[k]) < 1e-3 for k in range(count)), "the second round moves as the first did"
        assert again[count - 1] < 1.25 * max(again[: count - 1])


def test_the_plain_run_loops_in_place_with_planted_feet_sliding_back_at_its_speed():
    clip = pretend_run(steady(3.0), 20)
    loop = run_clip.make_loop(SK, clip, run_clip.find_loop(SK, clip))
    plain, report = run_clip.loop_to_plain(loop, SK)
    count = loop["loop"]["frames"]
    unit = report["soma_hip_height_m"]
    assert plain["loop"] is True and plain["frames"] == count and plain["name"] == "run" and plain["unit"] == "hip_height"
    assert all(len(rows) == count + 1 for rows in list(plain["turns"].values()) + [plain["hips"], plain["feet"]["l"], plain["feet"]["r"]])
    # How fast the ground slides back, in hip heights a second: the run's speed.
    assert abs(plain["travel"] * unit - loop["loop"]["speed_mps"]) < 1e-3
    # The loop closes: hips, feet and every bone's turn end where they began.
    assert report["loop_seam_hip_heights"] < 2e-3, report
    assert all(max(abs(a - b) for a, b in zip(rows[0], rows[-1])) < 1e-6 for rows in plain["turns"].values())
    # In place: the hips do not travel.
    assert max(abs(h[1]) for h in plain["hips"]) < 0.06 and max(abs(h[0]) for h in plain["hips"]) < 0.02
    per_frame = plain["travel"] / FPS
    for tag in ("l", "r"):
        feet = plain["feet"][tag]
        planted = [f for f in range(1, count + 1) if feet[f][5] and feet[f - 1][5]]
        assert len(planted) >= count // 4, "each foot is down for a good part of the loop"
        # A planted foot goes straight back at exactly the run's speed, and not sideways at all.
        assert max(abs(feet[f][1] - feet[f - 1][1] - per_frame) for f in planted) < 2e-4
        assert max(abs(feet[f][0] - feet[f - 1][0]) for f in planted) < 2e-4
        assert report["planted_feet"][tag]["most_moved_cm"] < 1.0, report["planted_feet"]
        # Both feet take turns: neither is down all the time.
        assert any(not feet[f][5] for f in range(count))


def test_a_clip_with_no_run_in_it_says_so():
    still = pretend_run(steady(0.0), 20)
    still["rotations"] = [list(still["rotations"][0]) for _ in still["rotations"]]
    try:
        run_clip.find_loop(SK, still)
    except ValueError as why:
        assert "stride" in str(why)
    else:
        raise AssertionError("a figure standing still has no stride to cut at")
    short = pretend_run(steady(3.0, 30), 20)
    try:
        run_clip.find_loop(SK, short, first=8)
    except ValueError:
        pass
    else:
        raise AssertionError("a clip shorter than a stride cannot be looped")


def main() -> None:
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name[5:].replace('_', ' ')}")
        except Exception as error:  # noqa: BLE001
            failed += 1
            import traceback

            print(f"FAIL  {name[5:].replace('_', ' ')}: {type(error).__name__}: {error}")
            traceback.print_exc()
    print(f"{len(tests) - failed} of {len(tests)} run clip tests pass")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
