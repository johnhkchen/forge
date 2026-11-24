"""Tries the standing sets with no Blender and no GPU.

    python3 scripts/sets/test_sets.py

What it shows:
  set-check        every set in sets/ is sound, and a broken one is told what is wrong with it
  marks            a shot list that names marks comes out with a path, distances, facings, a hand's
                   spot and a seat; one that names none comes out untouched
  cameras          every camera holds the marks it says it sees; turn one away and the check says so
  rooftop parity   the two hero shots, now filmed on the rooftop set, plan to the very requests they
                   did when the roof was written inside each shot
  placing          every set has an origin, a front and a footprint, and can be put down anywhere as one piece
  doors            a door mark names the set it leads into and the door it comes out at there; one that
                   leads nowhere, or to a mark that is not a door, or is not led back to, is told
  segment          the guest-entrance template: both roles the same length, the handshake on the same
                   frames, the two wrists planned a palm's length either side of one spot

`cases()` hands the same checks to scripts/test_tools.py.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
import plan_shot  # noqa: E402
import segment  # noqa: E402
import standing  # noqa: E402
import timeline  # noqa: E402
from soma import Skeleton  # noqa: E402

# What the hero shots' requests were when the rooftop's ledge, roof and wall were written inside each
# shot's plan (planned at 6df4955, before sets): the sha256 of request.json, and the pieces' names in
# the cache, which are the hashes of their content.
ROOFTOP_REQUEST_SHA256 = "af007bfb5d6b01db5b38dee75ff621928333287c8b9fad8b55d152e78d7255ca"
ROOFTOP_MIXED_PIECES = ["00ebff129536aad1addd", "10db58c5ff0d68348176", "5afcd9bfcd4bafc905bb", "a7e6eb7242a1fc753292", "f4e720097fdd1695d1a2", "fb60b3b06a6864e6e1c6"]
ROOFTOP_WALL = {"name": "wall", "kind": "wall", "center": [5.654, 0.375, 6.143], "size": [3.2, 0.75, 0.3], "heading": 50.0}


def check(label, ok, detail=""):
    print("    %s  %s%s" % ("ok  " if ok else "FAIL", label, ("  (%s)" % (str(detail)[:600],)) if detail and not ok else ""))
    if not ok:
        raise AssertionError(label)


def library():
    with open(os.path.join(REPO, "motion", "poses.json")) as f:
        return json.load(f)


def test_set_check():
    """every set in sets/ is sound, and a broken one is told what is wrong with it."""
    found = standing.names()
    check("the repo has the rooftop, the ring and the studio (%s)" % ", ".join(found), {"rooftop", "ring", "studio"} <= set(found))
    for name in found:
        problems, seen = standing.check(standing.load(name))
        check("%s is sound: %d blocks, %d marks, %d cameras" % (name, seen["blocks"], sum(len(v) for v in seen["marks"].values()), len(seen["cameras"])), not problems, problems[:3])
    studio = standing.load("studio")
    broken = copy.deepcopy(studio)
    broken["marks"]["couch_1"]["seat_height_m"] = 0.9
    broken["marks"]["centre"]["at"] = [2.2, 2.1]  # inside the desk
    broken["marks"]["monologue"]["at"] = [-2.2, 9.0]  # off the floor
    broken["marks"]["meet_right"]["at"] = [1.2, 2.75]  # too far for a handshake
    broken["paths"].append({"from": "desk_chair", "to": "couch_2"})  # straight through the desk's corner and the couch
    problems = "\n".join(standing.check(broken)[0])
    for told in ("a seat 0.9 m high is not one our sit pose fits", "mark \"centre\" stands 0 cm from \"desk\"", "mark \"monologue\" stands off the floor",
                 "share a hand's spot but stand", "path desk_chair to couch_2 passes"):
        check("a broken set is told: %s" % told, told in problems, problems[:400])
    ring = standing.load("ring")
    mat = standing.placed_bounds(ring)
    check("the ring's floor is its mat: its geometry is built around the set's origin, the mat's top at 0, the hall floor %.2f m below, the highest post %.2f m up" % (-mat[0][1], mat[1][1]),
          ring["geometry"]["move"] == [0.0, 0.0, 0.0] and 1.3 < mat[1][1] < 1.7 and -1.45 < mat[0][1] < -1.3 and abs(mat[0][0] + mat[1][0]) < 0.1, mat)
    in_the_way = {b["kind"] for b in standing.in_the_way(ring)}
    check("the ring's ropes and posts are in the way, and its steps are a mark to come in by", in_the_way == {"rope", "post"} and ring["marks"]["steps"]["kind"] == "stand")
    blocks = standing.plan_blocks(studio)
    check("a set's blocks go into a plan in the form the contact step reads (name, kind, center, size, heading)", all(list(b) == list(standing.BLOCK_KEYS) for b in blocks) and len(blocks) == len(studio["blocks"]))


def test_marks():
    """a shot list that names marks gets its path, distances, facings, hand spot and seat from the set."""
    studio, lib = standing.load("studio"), library()
    shots = segment.expand(segment.load("guest-entrance"), {"roles": {"host": "a", "guest": "b"}})
    guest = standing.stage_marks(shots["guest"], studio, lib)
    host = standing.stage_marks(shots["host"], studio, lib)
    check("the staged shot list names no marks any more, and has a path (%d points for the guest, %d for the host)" % (len(guest["path"]), len(host["path"])),
          not standing.names_marks(guest) and len(guest["path"]) >= 4 and len(host["path"]) >= 6)
    first, last = guest["path"][0], guest["path"][-1]
    check("the guest's path runs from the wings to the couch seat", [first["x"], first["z"]] == studio["marks"]["wings"]["at"] and [last["x"], last["z"]] == studio["marks"]["couch_1"]["at"])
    line = standing.curve([[p["x"], p["z"]] for p in guest["path"]])
    walk, sit = guest["beats"][1], guest["beats"][4]
    x, z, _ = line.at(walk["to_m"])
    check("the walk on ends at meet_left, %.2f m along (%.2f, %.2f)" % (walk["to_m"], x, z), math.dist((x, z), studio["marks"]["meet_left"]["at"]) < 0.01 and walk["from_m"] == 0.0)
    stand_x, stand_z, _ = line.at(sit["moves"][0]["at_m"])
    seat_x, seat_z, heading = line.at(sit["moves"][1]["at_m"])
    mark = studio["marks"]["couch_1"]
    check("standing in front of the couch, then sitting on it: the stand pose at stand_at, the sit pose over the seat",
          math.dist((stand_x, stand_z), mark["stand_at"]) < 0.01 and math.dist((seat_x, seat_z), mark["at"]) < 0.01)
    faces = standing.wrap(heading + sit["moves"][1]["facing_deg"])
    check("seated, the guest faces the way the mark does (%.1f degrees)" % faces, abs(faces - mark["facing_deg"]) < 0.5)
    back = [m for b in host["beats"] for m in b.get("moves") or []]
    check("the host's distances never run backwards, though the route doubles back to the desk", all(b["at_m"] >= a["at_m"] - 1e-6 for a, b in zip(back, back[1:])))
    touch_g, touch_h = guest["stage"]["touches"][0], host["stage"]["touches"][0]
    check("both are given the same spot for the handshake, each wrist a palm's length back from it (%.0f cm between the wrists)" % (100 * math.dist(touch_g["wrist"], touch_h["wrist"])),
          touch_g["palm"] == touch_h["palm"] and abs(math.dist(touch_g["wrist"], touch_h["wrist"]) - 2 * standing.PALM) < 0.001)
    sk = Skeleton.load()
    record, _ = timeline.lay_out(host, lib, sk, None)
    standing.into_plan(record, studio, host)
    pins = [m for m in record["moves"] if m["pin_points"]]
    check("in the plan, every pinned move of the handshake holds the wrist on the set's spot (the pose alone put it %.1f cm away)" % pins[0]["pose_put_it_cm_away"],
          len(pins) == 5 and all(m["pin_points"]["right_hand"] == touch_h["wrist"] for m in pins) and pins[0]["pose_put_it_cm_away"] < 5.0)
    seats = record["stage"]["seats"]
    check("the plan says when the host is seated: frames %s, at %s" % ([[s["from_frame"], s["to_frame"]] for s in seats], seats[0]["seat"]),
          [s["from_frame"] for s in seats] == [0, 424] and all(s["seat"] == "host chair seat" and s["seat_height_m"] == 0.46 for s in seats))
    check("the plan carries the set's blocks for the contact step (%d), and names the set" % len(record["set"]), record["standing_set"] == "studio" and len(record["set"]) == len(studio["blocks"]))
    hero = json.load(open(os.path.join(REPO, "motion", "shots", "hero-rooftop.shotlist.json")))
    check("a shot list that names no mark comes back untouched (the very same object)", standing.stage_marks(hero, standing.load("rooftop"), lib) is hero)
    for wrong, told in (({"start_mark": "the green room"}, "has no mark called"), ({"beats": [dict(shots["guest"]["beats"][0], at="couch_1")]}, "is at \"couch_1\", but the character is at \"wings\"")):
        try:
            standing.stage_marks(dict(shots["guest"], **wrong), studio, lib)
            said = ""
        except standing.SetProblem as e:
            said = str(e)
        check("blocking the set cannot do is refused: %s" % told, told in said, said)
    swapped = segment.expand(segment.load("guest-entrance"), {"roles": {"host": "a", "guest": "b"}, "marks": {"couch_1": "couch_2"}})
    far = standing.stage_marks(swapped["guest"], studio, lib)["path"][-1]
    check("a take can swap a mark: the guest sits in the far seat instead", [far["x"], far["z"]] == studio["marks"]["couch_2"]["at"])


def test_cameras():
    """every camera holds the marks it says it sees; turn one away and the check says so."""
    for name in ("studio", "ring"):
        st = standing.load(name)
        for cam_name, cam in st["cameras"].items():
            worst = 0.0
            for seen in cam["sees"]:
                for part, point in standing.head_and_feet(st["marks"][seen]):
                    ok, across, rise, depth = standing.in_frame(cam, point)
                    worst = max(worst, abs(across), abs(rise))
                    if not ok or depth <= 0:
                        raise AssertionError("%s: camera %s does not hold the %s at %s" % (name, cam_name, part, seen))
            check("%s: the %s camera (%d mm) holds %s; the furthest point is %.0f%% of the way to the frame's edge" % (name, cam_name, cam["lens_mm"], ", ".join(cam["sees"]), 100 * worst), worst <= 1.0 - standing.FRAME_MARGIN)
    studio = standing.load("studio")
    check("the studio's cameras are the wide, the host's, the guests' and the front-of-house one for a crew", list(studio["cameras"]) == ["wide", "host", "guest", "crew"])
    turned = copy.deepcopy(studio)
    turned["cameras"]["host"]["aim"] = [-3.0, 1.0, 1.2]
    turned["cameras"]["guest"]["at"] = [-0.1, 0.9, 0.3]  # behind the couch
    problems = "\n".join(standing.check(turned)[0])
    check("a camera turned away is told it does not hold its mark", "camera \"host\" does not hold the head at \"desk_chair\"" in problems, problems[:300])
    check("a camera with the couch's back in front of it is told what is in the way", "camera \"guest\" cannot see the" in problems or "camera \"guest\" does not hold" in problems, problems[:600])
    blocked = standing.sight_blocked(studio, [2.2, 0.4, 6.0], [2.2, 0.5, 0.95], skip=("host chair seat",))
    check("from low out front the desk hides a seated host's lap (%s)" % blocked, blocked == "desk")
    ring = standing.load("ring")
    check("ropes stop a body, not a camera: the ring's wide camera sees the far corners through them", standing.sight_blocked(ring, ring["cameras"]["wide"]["at"], [1.3, 1.6, -1.2]) == "")


def plan_into(folder, name):
    shot_file = os.path.join(REPO, "motion", "shots", name + ".shotlist.json")
    with open(shot_file) as f:
        shot = json.load(f)
    with open(os.path.join(REPO, "motion", "shots", name + ".json")) as f:
        brief = json.load(f)
    st, lib, sk = standing.load(brief["set"]), library(), Skeleton.load()
    staged = standing.stage_marks(shot, st, lib)
    if any(b.get("source", "poses") != "poses" for b in staged["beats"]):
        record, requests = timeline.lay_out(staged, lib, sk, None)
        made = sorted(requests)
    else:
        request, record = plan_shot.plan(staged, lib, sk, None)
        made = hashlib.sha256(json.dumps(request, separators=(",", ":")).encode()).hexdigest()
    return standing.into_plan(record, st, staged), made, brief


def test_rooftop_parity():
    """the hero shots, now on the rooftop set, plan to the very requests they did before sets."""
    with tempfile.TemporaryDirectory() as folder:
        record, sha, brief = plan_into(folder, "hero-rooftop")
        check("hero-rooftop names the set (\"set\": \"rooftop\") instead of describing a roof", brief["set"] == "rooftop")
        check("hero-rooftop: request.json is byte for byte what it was (sha256 %s...)" % sha[:12], sha == ROOFTOP_REQUEST_SHA256, sha)
        check("hero-rooftop: the plan still has the wall, for the checks and for the contact step", record["wall"] == ROOFTOP_WALL and record["set"][-1] == ROOFTOP_WALL and len(record["set"]) == 16)
        mixed, pieces, brief = plan_into(folder, "hero-rooftop-mixed")
        check("hero-rooftop-mixed: its six pieces' requests are the same six (%s...)" % ", ".join(p[:6] for p in pieces), pieces == ROOFTOP_MIXED_PIECES and brief["set"] == "rooftop", pieces)
        check("hero-rooftop-mixed: the same blocks as the other cut, from the one set", mixed["set"] == record["set"] and mixed["standing_set"] == "rooftop")


def test_segment():
    """the guest-entrance template: roles the same length, the handshake together, sentences and marks a take may change."""
    template = segment.load("guest-entrance")
    shots = segment.expand(template, {"roles": {"host": "a", "guest": "b"}, "sentences": {"guest_walks_on": "A person strides forward, waving."}})
    spans = {role: segment.spans(shot) for role, shot in shots.items()}
    check("both roles' shots are the same length (%d frames)" % spans["host"]["Sit at the desk"][1], spans["host"]["Sit at the desk"][1] == spans["guest"]["Sit on the couch"][1] == 474)
    check("the handshake is on the same frames for both (%d-%d)" % spans["host"]["Handshake"], spans["host"]["Handshake"] == spans["guest"]["Handshake"] == (175, 268))
    check("a take's own sentence replaces the template's", shots["guest"]["beats"][1]["prompt"] == "A person strides forward, waving." and shots["host"]["beats"][1]["prompt"].startswith("A person walks forward"))
    for wrong, told in (({"roles": {"host": "a"}}, "needs someone to play: guest"), ({"roles": {"host": "a", "guest": "b"}, "sentences": {"finale": "x"}}, "no sentence called finale"),
                        ({"roles": {"host": "a", "guest": "b"}, "marks": {"balcony": "wings"}}, "does not use the mark balcony")):
        try:
            segment.expand(template, wrong)
            said = ""
        except segment.SegmentProblem as e:
            said = str(e)
        check("a take the segment cannot play is refused: %s" % told, told in said, said)
    late = copy.deepcopy(template)
    late["roles"]["host"]["beats"][1]["frames"] = 90
    try:
        segment.expand(late, {"roles": {"host": "a", "guest": "b"}})
        said = ""
    except segment.SegmentProblem as e:
        said = str(e)
    check("a template whose roles fall out of step is refused", "not the same length" in said, said)
    with tempfile.TemporaryDirectory() as folder:
        made = segment.write_take(os.path.join(REPO, "motion", "shots", "studio-guest-entrance.json"), folder)
        check("the demo take writes a shot list per role and a take.json (%s)" % ", ".join(sorted(made["shots"])),
              all(os.path.exists(os.path.join(folder, role, "shotlist.json")) for role in ("host", "guest")) and made["take"]["roles"]["guest"]["character"] == "roosevelt-wrestler-1890s")


def test_placing():
    """a set is written in its own frame, with a footprint, so it can be put down anywhere in a world as one piece."""
    for name in standing.names():
        st = standing.load(name)
        outline = st["footprint"]["outline"]
        held = all(standing.inside(outline, *m["at"]) for m in st["marks"].values()) and all(standing.inside(outline, c["at"][0], c["at"][2]) for c in st["cameras"].values())
        check("%s: an origin, a front, and a footprint that holds its marks and cameras; its geometry is built around the origin" % name,
              st["frame"]["origin"] == [0.0, 0.0, 0.0] and held and st["geometry"]["move"] == [0.0, 0.0, 0.0] and st["geometry"]["turn_deg"] == 0.0)
    studio = standing.load("studio")
    point, heading = standing.placed(studio, at=(100.0, -40.0), facing_deg=90.0)
    desk, couch = studio["marks"]["desk_chair"], studio["marks"]["couch_1"]
    moved = math.dist(point(desk["at"]), point(couch["at"]))
    check("put down 100 m east, turned a quarter: the origin lands there, the front faces 90, and nothing inside moves against anything else (desk chair to couch still %.2f m)" % moved,
          point([0.0, 0.0]) == [100.0, -40.0] and heading(0.0) == 90.0 and abs(moved - math.dist(desk["at"], couch["at"])) < 1e-3 and point([0.0, 1.0, 2.0]) == [102.0, 1.0, -40.0], (point([0.0, 0.0]), heading(0.0), point([0.0, 1.0, 2.0])))
    same, _ = standing.placed(studio)
    check("left where it is, a set's points are unchanged", same(desk["at"]) == desk["at"])
    ring = standing.load("ring")
    xs = [p[0] for p in ring["footprint"]["outline"]]
    check("the ring keeps one side clear to grow on (toward %.0f degrees): its footprint ends %.1f m from the ropes there, %.1f m on the other side" % (ring["footprint"]["open_toward_deg"], max(xs) - 1.97, -min(xs) - 1.97),
          ring["footprint"]["open_toward_deg"] == 90.0 and max(xs) - 1.97 < -min(xs) - 1.97)
    broken = copy.deepcopy(studio)
    broken["footprint"]["outline"] = [[-2.0, 0.0], [2.0, 0.0], [2.0, 3.0], [-2.0, 3.0]]
    broken["geometry"]["move"] = [1.0, 0.0, 0.0]
    problems = "\n".join(standing.check(broken)[0])
    check("a footprint too small for the set, or geometry off the origin, is told", "outside the set's footprint: mark \"wings\"" in problems and "not built around the set's origin" in problems, problems[:300])


def test_doors():
    """a door mark names the set it leads into and the door it comes out at there; a door that dangles is told."""
    studio = standing.load("studio")

    def door_said(leads_to, name="studio"):
        st = copy.deepcopy(studio)
        st["name"] = name
        st["marks"]["way_out"] = dict(copy.deepcopy(st["marks"]["wings"]), kind="door", **({"leads_to": leads_to} if leads_to else {}))
        return "\n".join(p for p in standing.check(st)[0] if "way_out" in p)

    check("a door with nowhere to lead is told", "a door needs leads_to" in door_said(None))
    check("a door into a set that is not there is told", "which is not a set" in door_said({"set": "no-such-place", "mark": "hatch"}))
    check("...unless it says the other side is still to come", door_said({"set": "no-such-place", "mark": "hatch", "built": False}) == "")
    check("a door onto a mark that is not a door is told", "which is not a door there" in door_said({"set": "ring", "mark": "steps"}))
    doors = [(name, m) for st in map(standing.load, standing.names()) for name, m in st["marks"].items() if m.get("kind") == "door"]
    check("the sets have a door to try (the Niantic saloon's)", bool(doors))
    with tempfile.TemporaryDirectory() as tmp:  # two made-up sets whose doors name each other, and then one that names the wrong one back
        was = standing.SETS
        try:
            standing.SETS = tmp
            for name, other, back in (("inside", "outside", "hatch"), ("outside", "inside", "door")):
                st = copy.deepcopy(studio)
                st.pop("dir")
                st["name"] = name
                st["marks"]["hatch" if name == "outside" else "door"] = dict(copy.deepcopy(st["marks"]["wings"]), kind="door", leads_to={"set": other, "mark": back})
                os.makedirs(os.path.join(tmp, name))
                with open(os.path.join(tmp, name, "set.json"), "w") as f:
                    json.dump(st, f)
            inside = standing.load("inside")
            check("two doors that name each other are sound", not [p for p in standing.check(inside)[0] if "\"door\"" in p], standing.check(inside)[0])
            inside["marks"]["door"]["leads_to"]["built"] = False
            check("a door that still says its other side is not built, when it is, is told", "take \"built\": false off" in "\n".join(standing.check(inside)[0]))
            inside["marks"]["side_door"] = dict(copy.deepcopy(inside["marks"]["door"]), leads_to={"set": "outside", "mark": "hatch"})
            check("a second door onto a door that leads back to the first is told", "not back here" in "\n".join(standing.check(inside)[0]))
        finally:
            standing.SETS = was


TESTS = [test_set_check, test_marks, test_cameras, test_rooftop_parity, test_segment, test_placing, test_doors]


def cases():
    """The tests, for scripts/test_tools.py: [(name, what it shows, the function)]."""
    return [(t.__name__[5:], t.__doc__, t) for t in TESTS]


def main() -> int:
    failed = 0
    for test in TESTS:
        print("%s: %s" % (test.__name__[5:], test.__doc__))
        try:
            test()
        except Exception as e:  # a failed check, or something a check reads that is missing
            failed += 1
            print("    FAILED: %s: %s" % (type(e).__name__, str(e)[:800]))
    print("%d set case(s) failed" % failed if failed else "all %d set cases passed" % len(TESTS))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
