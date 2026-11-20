"""Offline tests for joining a shot from pieces. No GPU, no worker, no Blender.

    python3 scripts/motion/test_timeline.py

A pretend worker stands in for the two models. For `inbetween` it slides and
turns evenly from where it starts to each target; for `text` it glides along
the path it was given. That is not motion anyone would want to watch, but it
has the right number of frames in the right places, which is all the joining
has to get right. The pretend worker can also be told to miss its target, the
way a real one does, so re-anchoring has something to do.
"""

from __future__ import annotations

import copy
import json
import math
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "motionbricks_worker", "models"))

import checks  # noqa: E402
import timeline  # noqa: E402
from soma import Skeleton, heading_of, qconj, qmul, qslerp, yaw  # noqa: E402
from soma_bridge import Bridge, qbetween  # noqa: E402

SK = Skeleton.load()
with open(os.path.join(REPO, "motion", "poses.json")) as f:
    LIBRARY = json.load(f)
with open(os.path.join(REPO, "motion", "shots", "hero-rooftop-mixed.shotlist.json")) as f:
    MIXED = json.load(f)
with open(os.path.join(REPO, "motion", "shots", "hero-rooftop-mixed.json")) as f:
    SET = json.load(f)["set"]


# ---- the pretend worker ----------------------------------------------------------


def frame_of(pose: dict) -> tuple:
    """A POSE of the worker's input as (root, rotation row)."""
    one = timeline.held(SK, {"rotations": pose.get("rotations") or {}, "root": pose.get("root", SK.rest_pos[0]), "at": pose.get("at", (0.0, 0.0, 0.0)), "heading": pose.get("heading", 0.0)}, 1)
    return one["root"][0], one["rotations"][0]


def between(a, b, t: float) -> tuple:
    root = [a[0][k] + (b[0][k] - a[0][k]) * t for k in range(3)]
    row = []
    for j in range(len(SK.joints)):
        row += list(qslerp(tuple(a[1][4 * j : 4 * j + 4]), tuple(b[1][4 * j : 4 * j + 4]), t))
    return [round(v, 5) for v in root], [round(c, 6) for c in row]


def pretend(request: dict, miss=(0.0, 0.0, 0.0)) -> dict:
    """What a worker would answer, in shape. `miss` makes an inbetween end (x, z, degrees) off its target."""
    roots, rows = [], []
    if request["kind"] == "inbetween":
        now = frame_of(request["seed"] if "seed" in request else request["context"][-1])
        roots.append(now[0])
        rows.append(now[1])
        for target in request["targets"]:
            goal = frame_of(target["poses"][0])
            turned = list(goal[1])
            turned[0:4] = [round(c, 6) for c in qmul(yaw(miss[2]), tuple(goal[1][0:4]))]
            goal = ([goal[0][0] + miss[0], goal[0][1], goal[0][2] + miss[1]], turned)
            count = 4 * target["tokens"] - 7 - target.get("transition_early_by", 0)
            for f in range(1, count + 1):
                root, row = between(now, goal, f / count)
                roots.append(root)
                rows.append(row)
            now = goal
    else:
        prompt = request["prompts"][0]
        path = next(c for c in prompt["constraints"] if c["type"] == "path")
        rest = [c for q in SK.rest_rot for c in q]
        # A different sentence or seed gives a (slightly) different motion: the hips ride at another height.
        height = 0.90 + int(timeline.digest({"text": prompt["text"], "seed": request.get("seed", 0)})[:4], 16) % 60 / 1000.0
        for f in range(prompt["frames"]):
            x, z = path["points"][f]
            nx, nz = path["points"][min(f + 1, prompt["frames"] - 1)]
            px, pz = path["points"][max(f - 1, 0)]
            heading = math.degrees(math.atan2(nx - px, nz - pz)) if (nx, nz) != (px, pz) else 0.0
            row = list(rest)
            row[0:4] = [round(c, 6) for c in qmul(yaw(heading), SK.rest_rot[0])]
            roots.append([x, height, z])
            rows.append(row)
    return {
        "format": "forge-soma-motion/1",
        "fps": 30,
        "joints": list(SK.joints),
        "root": roots,
        "rotations": rows,
        "contact_order": list(timeline.CONTACT_ORDER),
        "contacts": [[1.0, 1.0, 1.0, 1.0] for _ in roots],
    }


def make(shot_list: dict, folder: str, miss=(0.0, 0.0, 0.0), calls: list = None) -> dict:
    """Plan a shot into a folder and run it to the end against the pretend worker, the way `baml run shoot` does."""
    record, requests = timeline.lay_out(shot_list, LIBRARY, SK, SET)
    os.makedirs(folder, exist_ok=True)
    for request in requests.values():
        timeline.keep_request(folder, request)
    with open(os.path.join(folder, "plan.json"), "w") as f:
        json.dump(record, f)
    for _ in range(4):
        result = timeline.step(folder, SK)
        if not result["todo"]:
            break
        for item in result["todo"]:
            with open(timeline.cache_path(folder, item["request"], "request")) as f:
                request = json.load(f)
            if calls is not None:
                calls.append(item["what"])
            # Only seams miss: a piece that starts a shot or follows a hold has nothing to miss.
            with open(timeline.cache_path(folder, item["request"]), "w") as f:
                json.dump(pretend(request, miss if "context" in request else (0.0, 0.0, 0.0)), f)
    assert result["joined"], "the shot was not joined after four passes"
    with open(os.path.join(folder, "motion.json")) as f:
        return {"plan": record, "motion": json.load(f), "notes": result["notes"], "requests": requests}


# ---- tests -----------------------------------------------------------------------


def test_tween_lengths():
    # Between two poses pieces: 4 + 13 is MotionBricks' shortest motion.
    assert timeline.tween_length(4, 13) == (4, 13)
    # After a text piece: 12 + 13 = 25, which it also makes.
    assert timeline.tween_length(12, 13) == (12, 13)
    # The vault gives up nothing; the landing gives up enough to make 17.
    assert timeline.tween_length(0, 13) == (0, 17)
    # 10 + 13 = 23 is not a length it makes; the next one is 25.
    assert timeline.tween_length(10, 13) == (10, 15)
    for a, b in ((0, 1), (4, 13), (12, 13), (20, 30)):
        a2, b2 = timeline.tween_length(a, b)
        assert a2 == a and (a2 + b2 + 7) % 4 == 0 and 6 <= (a2 + b2 + 7) // 4 <= 16
    try:
        timeline.tween_length(40, 30)
    except ValueError as error:
        assert "longer than MotionBricks makes" in str(error)
    else:
        raise AssertionError("a 70-frame seam should be refused")


def test_pace():
    at = timeline.pace(2.0, 5.0, 0.5, 2.0, 2.0)
    assert abs(at(0.0) - 2.0) < 1e-9 and abs(at(2.0) - 5.0) < 1e-9
    assert abs((at(0.001) - at(0.0)) / 0.001 - 0.5) < 0.01, "starts at the first speed"
    assert abs((at(2.0) - at(1.999)) / 0.001 - 2.0) < 0.01, "ends at the last speed"
    assert abs(at(-1.0) - 1.5) < 1e-9 and abs(at(3.0) - 7.0) < 1e-9, "runs on before and after"
    assert all(at(t / 30.0) < at((t + 1) / 30.0) for t in range(60)), "never goes backwards"


def test_layout_of_the_mixed_hero_cut():
    record, requests = timeline.lay_out(MIXED, LIBRARY, SK, SET)
    # Same beats and length as the in-house cut.
    assert record["frames"] == 361
    assert [(b["first_frame"], b["last_frame"]) for b in record["beats"]] == [(0, 62), (62, 151), (151, 209), (209, 255), (255, 301), (301, 360)]
    assert [b["source"] for b in record["beats"]] == ["poses", "text", "text", "text", "poses", "poses"]
    assert [s["tween_frames"] for s in record["seams"]] == [[58, 75], [139, 164], [197, 222], [255, 272], [297, 314]]
    assert [s["tokens"] for s in record["seams"]] == [6, 8, 8, 6, 6]
    # The landing's pins ride on the tween that arrives in it.
    assert record["seams"][3]["pins"] == ["left_hand", "left_foot", "right_foot"]
    assert len(requests) == 6 and all(p.get("request") for p in record["pieces"])
    for piece in record["pieces"]:
        request = requests[piece["request"]]
        if piece["source"] != "text":
            assert request["kind"] == "inbetween" and "seed" in request
            continue
        prompt = request["prompts"][0]
        assert request["kind"] == "text" and prompt["text"].startswith("A person ")
        path = prompt["constraints"][0]
        # Kimodo starts at the origin facing +Z: so does every request.
        assert path["points"][0] == [0.0, 0.0] and len(path["points"]) == prompt["frames"] <= 300
        assert abs(path["points"][1][0]) < 0.01 and path["points"][1][1] >= 0.0
        first, last = piece["keep"]
        assert last - first == piece["last_frame"] - piece["first_frame"] and last < prompt["frames"]
        keyed = sum(len(c["frames"]) for c in prompt["constraints"] if c["type"] != "path")
        assert keyed < 20, "Kimodo does best with fewer than 20 keyed frames"
    vault = requests[record["pieces"][3]["request"]]["prompts"][0]
    reach = [c for c in vault["constraints"] if c["type"] == "reach"]
    assert len(reach) == 1 and reach[0]["parts"] == ["right_hand"]
    assert reach[0]["frames"] == [record["pieces"][3]["keep"][1]], "the hand is on the wall on the beat's last frame"
    # The hand's planned spot is on the wall top, as in the in-house cut.
    mark = next(m for m in record["moves"] if m["pins"] == ["right_hand"])
    assert mark["frame"] == 255 and abs(mark["pin_points"]["right_hand"][1] - (0.75 + checks.PALM)) < 0.02


def test_a_text_piece_is_put_back_where_it_was_planned():
    record, requests = timeline.lay_out(MIXED, LIBRARY, SK, SET)
    from plan_shot import Path

    path = Path(MIXED["path"])
    for piece, beat in zip(record["pieces"], MIXED["beats"]):
        if piece["source"] != "text":
            continue
        motion = timeline.piece_motion(SK, piece, {piece["request"]: pretend(requests[piece["request"]])})
        for local, along in ((0, beat["from_m"]), (len(motion["root"]) - 1, beat["to_m"])):
            x, z, heading = path.at(along)
            assert math.hypot(motion["root"][local][0] - x, motion["root"][local][2] - z) < 0.002, piece["name"]
        # Halfway along it faces the way the path runs there, in the world.
        mid = len(motion["root"]) // 2
        dx = motion["root"][mid + 1][0] - motion["root"][mid - 1][0]
        dz = motion["root"][mid + 1][2] - motion["root"][mid - 1][2]
        off = (timeline.facing(SK, motion, mid) - math.degrees(math.atan2(dx, dz)) + 180.0) % 360.0 - 180.0
        assert abs(off) < 1.0, (piece["name"], off)


def test_moving_a_motion_changes_nothing_inside_it():
    motion = pretend({"kind": "inbetween", "seed": {"rotations": LIBRARY["poses"]["crouch"]["rotations"], "root": LIBRARY["poses"]["crouch"]["root"]}, "targets": [{"poses": [{"rotations": LIBRARY["poses"]["hero_stance"]["rotations"], "root": LIBRARY["poses"]["hero_stance"]["root"], "at": [1.0, 0.0, 2.0], "heading": 40.0}], "tokens": 6}]})
    other = timeline.moved(motion, 73.0, -2.0, 5.0)
    before, after = checks.world_positions(SK, motion), checks.world_positions(SK, other)
    hand, foot = SK.index["LeftHand"], SK.index["RightFoot"]
    for f in (0, 8, 17):
        assert abs(math.dist(before[f][0][hand], before[f][0][foot]) - math.dist(after[f][0][hand], after[f][0][foot])) < 1e-4
        assert abs(before[f][0][hand][1] - after[f][0][hand][1]) < 1e-4, "heights do not change"
    assert abs(math.dist(before[0][0][0], before[17][0][0]) - math.dist(after[0][0][0], after[17][0][0])) < 1e-4
    turned = (timeline.facing(SK, other, 5) - timeline.facing(SK, motion, 5) + 180.0) % 360.0 - 180.0
    assert abs(turned - 73.0) < 0.01


def test_joining_keeps_the_length_and_has_no_gaps():
    folder = tempfile.mkdtemp(prefix="forge-timeline-")
    try:
        made = make(MIXED, folder)
        motion, plan = made["motion"], made["plan"]
        assert len(motion["root"]) == len(motion["rotations"]) == len(motion["contacts"]) == 361
        # Every frame is spoken for exactly once, in order.
        cover = [(s["first_frame"], s["last_frame"]) for s in motion["segments"]]
        assert cover[0][0] == 0 and cover[-1][1] == 360 and all(b[0] == a[1] + 1 for a, b in zip(cover, cover[1:]))
        assert len(motion["segments"]) == 11, "six pieces and five tweens"
        # The pretend worker hits its targets, so nothing needed moving and no frame jumps.
        for seam in made["notes"]["seams"]:
            assert seam["tween_missed_by_cm"] < 0.01 and abs(seam["tween_missed_by_deg"]) < 0.01
            assert seam["next_piece_from_its_plan_cm"] < 0.01 and abs(seam["next_piece_from_its_plan_deg"]) < 0.01
        steps = [math.dist(a, b) for a, b in zip(motion["root"], motion["root"][1:])]
        assert max(steps) < 0.12, f"the hips jump {max(steps):.3f} m in one frame"
        # A tween starts on the very frame piece A was cut at.
        frames = checks.world_positions(SK, motion)
        report = checks.seams(SK, motion, frames, plan)
        assert len(report["seams"]) == 5 and all(len(s["joins_at_frames"]) == 2 for s in report["seams"])
    finally:
        shutil.rmtree(folder)


def test_a_piece_is_set_down_where_its_tween_ended():
    folder = tempfile.mkdtemp(prefix="forge-timeline-")
    try:
        miss = (0.05, -0.03, 4.0)  # every tween ends 5 cm and 3 cm off, turned 4 degrees
        made = make(MIXED, folder, miss)
        motion, plan = made["motion"], made["plan"]
        true = make(MIXED, folder + "-true")["motion"]
        for seam, note in zip(plan["seams"], made["notes"]["seams"]):
            assert abs(note["tween_missed_by_cm"] - 100 * math.hypot(miss[0], miss[1])) < 0.05, note
            assert abs(note["tween_missed_by_deg"] - miss[2]) < 0.05, note
            # No gap where the tween hands over: the next frame is one ordinary step on.
            end = seam["tween_frames"][1]
            step = math.dist(motion["root"][end], motion["root"][end + 1])
            usual = math.dist(true["root"][end], true["root"][end + 1])
            assert abs(step - usual) < 0.005, (seam["to"], step, usual)
            assert abs((timeline.facing(SK, motion, end + 1) - timeline.facing(SK, motion, end) + 180) % 360 - 180) < 3.0
        # Inside a piece nothing changed: it covers the same ground as when nothing missed.
        for piece in plan["pieces"][1:]:
            a, b = piece["first_frame"] + 20, piece["last_frame"] - 16
            assert abs(math.dist(motion["root"][a], motion["root"][b]) - math.dist(true["root"][a], true["root"][b])) < 1e-3, piece["name"]
        # Five misses add up: the end of the shot has drifted, and the join says by how much at each seam.
        assert math.dist(motion["root"][360], true["root"][360]) > 0.05
        drift = [note["next_piece_from_its_plan_deg"] for note in made["notes"]["seams"]]
        assert all(abs(d - 4.0 * (i + 1)) < 0.1 for i, d in enumerate(drift)), drift
    finally:
        shutil.rmtree(folder, ignore_errors=True)
        shutil.rmtree(folder + "-true", ignore_errors=True)


def test_changing_one_beat_remakes_it_and_its_two_seams_only():
    folder = tempfile.mkdtemp(prefix="forge-timeline-")
    try:
        first_calls: list = []
        before = make(MIXED, folder, calls=first_calls)
        assert len(first_calls) == 11
        # Nothing changed: nothing is made again.
        again: list = []
        make(MIXED, folder, calls=again)
        assert again == []
        # A new sentence for the sprint.
        changed = copy.deepcopy(MIXED)
        changed["beats"][2]["prompt"] = "A person runs forward fast, pumping the arms."
        calls: list = []
        after = make(changed, folder, calls=calls)
        assert calls == ["Break into sprint", "Sneak along ledge to Break into sprint", "Break into sprint to Vault the wall"], calls
        was, now = before["notes"]["requests"], after["notes"]["requests"]
        same = [name for name in was["pieces"] if was["pieces"][name] == now["pieces"][name]]
        assert sorted(same) == sorted(n for n in was["pieces"] if n != "Break into sprint")
        same = [name for name in was["seams"] if was["seams"][name] == now["seams"][name]]
        assert sorted(same) == ["Crouch and look to Sneak along ledge", "Three-point landing to Rise and draw", "Vault the wall to Three-point landing"]
        # A new seed for a seam's neighbour would not matter to the other pieces either.
        assert timeline.digest({"a": 1, "b": [1, 2]}) == timeline.digest({"b": [1, 2], "a": 1})
    finally:
        shutil.rmtree(folder)


def test_a_seam_that_misses_shows_up_in_the_checks():
    folder = tempfile.mkdtemp(prefix="forge-timeline-")
    try:
        made = make(MIXED, folder)
        motion, plan = made["motion"], made["plan"]
        smooth = checks.seams(SK, motion, checks.world_positions(SK, motion), plan)
        # Break one join by hand: everything after frame 164 is 6 cm to the side.
        broken = copy.deepcopy(motion)
        for f in range(165, 361):
            broken["root"][f][0] += 0.06
        rough = checks.seams(SK, broken, checks.world_positions(SK, broken), plan)
        assert rough["seams"][1]["speed_jump_cm_per_frame"] > smooth["seams"][1]["speed_jump_cm_per_frame"] + 5.0
        assert rough["seams"][1]["hips_speed_jump_m_per_s"] > 1.5
        for i in (0, 2, 3, 4):
            assert rough["seams"][i]["speed_jump_cm_per_frame"] == smooth["seams"][i]["speed_jump_cm_per_frame"]
    finally:
        shutil.rmtree(folder)


def test_what_cannot_be_made_is_refused_in_plain_words():
    walk = copy.deepcopy(MIXED)
    walk["beats"][1]["source"] = "walk"
    short = copy.deepcopy(MIXED)
    short["beats"][2]["frames"] = 20
    wordless = copy.deepcopy(MIXED)
    wordless["beats"][1]["prompt"] = " "
    for bad, said in ((walk, 'not "walk"'), (short, "make the beat longer"), (wordless, "needs a prompt")):
        try:
            timeline.lay_out(bad, LIBRARY, SK, SET)
        except ValueError as error:
            assert said in str(error), str(error)
        else:
            raise AssertionError(f"expected a refusal mentioning {said!r}")


def test_poses_cross_between_the_two_skeletons_by_what_they_look_like():
    """soma_bridge.py, with a pretend Kimodo T-pose: ours with the shins leaning and the hips 2 cm lower."""
    with open(os.path.join(REPO, "motion", "soma_skeleton.json")) as f:
        card = json.load(f)
    theirs = {name: list(SK.rest_world_pos[i]) for i, name in enumerate(SK.joints)}
    for side in ("Left", "Right"):
        for name in (f"{side}Foot", f"{side}ToeBase"):
            theirs[name][2] -= 0.04
    bridge = Bridge(card, theirs, SK.rest_pos[0][1] - 0.02)
    assert bridge.joints == SK.joints and abs(bridge.lift - 0.02) < 1e-9
    lean = math.degrees(2 * math.acos(abs(bridge.fix[SK.index["LeftShin"]][3])))
    assert 4.0 < lean < 7.0, lean

    def from_axis_angle(v):
        angle = math.sqrt(sum(c * c for c in v))
        if angle < 1e-12:
            return (0.0, 0.0, 0.0, 1.0)
        s = math.sin(angle / 2.0) / angle
        return (v[0] * s, v[1] * s, v[2] * s, math.cos(angle / 2.0))

    for name, pose in LIBRARY["poses"].items():
        placed = {"rotations": pose["rotations"], "root": pose["root"], "at": [1.0, 0.0, 2.0], "heading": 30.0}
        there = bridge.to_kimodo(placed)
        local = [from_axis_angle(v) for v in there["local_joints_rot"]]
        turned = []
        for j, parent in enumerate(bridge.parents):
            turned.append(local[j] if parent < 0 else qmul(turned[parent], local[j]))
        # In Kimodo's convention the T-pose is all zeros; ours is not. A shin's world turn from the
        # T-pose there, times the lean, lays the shin where ours lies.
        root, back = bridge.from_kimodo(there["root_position"], turned)
        want_root, want = bridge.place(placed)
        assert math.dist(root, want_root) < 1e-9, name
        for j in range(len(SK.joints)):
            assert abs(sum(a * b for a, b in zip(back[j], want[j]))) > 1.0 - 1e-9, (name, SK.joints[j])
        assert abs(there["root_position"][1] - (want_root[1] - 0.02)) < 1e-9
    assert qbetween((0, 0, 1), (0, 0, 1)) == (0.0, 0.0, 0.0, 1.0)


def test_the_in_house_cut_is_still_planned_in_one_go():
    from plan_shot import plan

    with open(os.path.join(REPO, "motion", "shots", "hero-rooftop.shotlist.json")) as f:
        shot = json.load(f)
    request, record = plan(shot, LIBRARY, SK, SET)
    assert "pieces" not in record and record["frames"] == 361 and len(request["targets"]) == 16
    # Its seams are single joins, where a beat ends; the checks read them as such.
    assert all("boundary_frame" not in s for s in record["seams"])


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
    print(f"{len(tests) - failed} of {len(tests)} timeline tests pass")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
