"""Offline tests for `just video`: the cuts, the people, the choice, the worker's plumbing, the conversion, the join.

    python3 scripts/video/test_video.py                 # part of `just check`: no GPU, no RunPod, no Blender
    python3 scripts/video/test_video.py --cast RUNS     # also films the shot and puts a character from RUNS in it,
                                                        # in a background Blender (a few minutes)

No model is run and nothing is fetched. The clip is one ffmpeg draws (test
patterns with cuts at known frames). The worker is the real router
(gemx_worker/handler.py) on this Mac, with scripts/video/stub_worker.py
standing in for GEM-X: made-up boxes for people, and a made-up dance written
the way GEM-X writes motion. So everything around the model runs for real:
upload in parts, the tracker, the pictures, same-person and reflection marks,
the gallery's save, the conversion onto our skeleton, the join across cuts,
checks.py, and (with --cast) the film and a character.

The last cases put a stretch of that clip in a shot beside the other two ways
of making motion: a pose of ours, a sentence (Kimodo) and the clip, with a
MotionBricks tween at every change. The two motion models are the pretend
worker from scripts/motion/test_timeline.py; with --cast, a sentence gets a
real Kimodo answer instead where one is in the cache of a shot beside RUNS.

What this cannot show: that the real GEM-X answers in the shapes and axes the
worker's code expects. Only a real job on the endpoint shows that.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
sys.path.insert(0, os.path.join(REPO, "gemx_worker"))

import clip as clip_file  # noqa: E402
import endpoint as endpoint_file  # noqa: E402
import people as people_file  # noqa: E402
import soma77  # noqa: E402
import soma_to_plain  # noqa: E402
import stub_worker  # noqa: E402
import timeline  # noqa: E402
import tracks  # noqa: E402
import video  # noqa: E402
from soma import SKELETON_FILE, Skeleton  # noqa: E402

SK = Skeleton.load()
with open(SKELETON_FILE) as _f:
    CARD = json.load(_f)
CUTS = [60, 105, 165]  # where the drawn clip cuts: 2 s, 1.5 s, 2 s, 1 s
FRAMES = 195
TEMP = tempfile.mkdtemp(prefix="forge-video-test-")
QUIET = lambda line: None  # noqa: E731
CAST_RUNS = None


def drawn_clip(path: str) -> None:
    """A clip with cuts at known frames: four test patterns one after the other, and a tone."""
    clip_file.run(
        clip_file.FFMPEG, "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=360x640:rate=30:duration=2",
        "-f", "lavfi", "-i", "color=c=0x44679b:size=360x640:rate=30:duration=1.5",
        "-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=2",
        "-f", "lavfi", "-i", "smptebars=size=360x640:rate=30:duration=1",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6.5",
        "-filter_complex", "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[v]", "-map", "[v]", "-map", "4:a", "-pix_fmt", "yuv420p", "-shortest", path,
    )


class Bench:
    """One clip taken as far as the choice, shared by the tests that need it (made once)."""

    made = None

    def __init__(self):
        self.videos, self.shots, self.volume = (os.path.join(TEMP, n) for n in ("videos", "shots", "volume"))
        drawn = os.path.join(TEMP, "Drawn Clip.mp4")
        drawn_clip(drawn)
        self.folder = clip_file.add(drawn, videos=self.videos)
        self.name = os.path.basename(self.folder)
        self.worker = endpoint_file.Direct(self.volume, os.path.join(HERE, "stub_worker.py"), log=QUIET)
        self.first = video.advance(self.name, self.videos, self.shots, connect=lambda: self.worker, log=QUIET)

    @classmethod
    def get(cls) -> "Bench":
        if cls.made is None:
            cls.made = cls()
        return cls.made

    def go(self) -> dict:
        return video.advance(self.name, self.videos, self.shots, connect=lambda: self.worker, log=QUIET, film=False)


def positions(motion: dict, frame: int):
    return SK.fk(motion["root"][frame], [tuple(motion["rotations"][frame][4 * j : 4 * j + 4]) for j in range(len(SK.joints))])[0]


# ---- the cuts --------------------------------------------------------------------


def test_a_drawn_clip_is_cut_at_the_frames_it_was_drawn_with():
    bench = Bench.get()
    assert bench.name == "drawn-clip", bench.name
    card = clip_file.read(os.path.join(bench.folder, "clip.json"))
    assert card["clip"]["frames"] == FRAMES and card["clip"]["fps"] == 30.0 and card["clip"]["sound"], card["clip"]
    record = clip_file.read(os.path.join(bench.folder, "shots.json"))
    assert record["cuts"] == CUTS, record["cuts"]
    assert [(s["first_frame"], s["last_frame"]) for s in record["shots"]] == [(0, 59), (60, 104), (105, 164), (165, 194)]


def test_slivers_join_the_shot_before_and_a_long_shot_is_split():
    # A flash 4 frames after a cut is not a shot; nor are the last few frames.
    shots = clip_file.shots_from([100, 104, 300, 595], 600)
    assert [(s["first_frame"], s["last_frame"]) for s in shots] == [(0, 99), (100, 299), (300, 599)], shots
    # Two and a half minutes without a cut: three parts of 50 seconds, marked as parts.
    long = clip_file.shots_from([], 4500)
    assert [(s["first_frame"], s["last_frame"]) for s in long] == [(0, 1499), (1500, 2999), (3000, 4499)] and all(s["part_of_a_long_shot"] for s in long)


def test_a_trim_is_kept_and_cuts_written_by_hand_are_left_alone():
    videos = os.path.join(TEMP, "trim-videos")
    folder = clip_file.add(os.path.join(TEMP, "Drawn Clip.mp4"), "trimmed", start=1.0, end=4.0, videos=videos)
    card = clip_file.ready(folder)
    assert card["clip"]["frames"] == 90, card["clip"]
    assert clip_file.cuts(folder)["cuts"] == [30, 75]  # the same cuts, a second earlier
    clip_file.write(os.path.join(folder, "shots.json"), {"by_hand": True, "cuts": [45]})
    assert [(s["first_frame"], s["last_frame"]) for s in clip_file.cuts(folder)["shots"]] == [(0, 44), (45, 89)]
    # Adding the same file again is fine; another video under the same name is refused.
    clip_file.add(os.path.join(TEMP, "Drawn Clip.mp4"), "trimmed", start=1.0, end=4.0, videos=videos)
    other = os.path.join(TEMP, "other.mp4")
    clip_file.run(clip_file.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=30:duration=1", "-pix_fmt", "yuv420p", other)
    for bad in (lambda: clip_file.add(other, "trimmed", videos=videos), lambda: clip_file.add(other, "../escape", videos=videos), lambda: clip_file.add(other, "x", start=5, end=2, videos=videos)):
        try:
            bad()
        except clip_file.Stop:
            continue
        raise AssertionError("expected a refusal")


# ---- following people ------------------------------------------------------------


def test_two_people_who_pass_each_other_keep_their_numbers():
    tracker = tracks.Tracker()
    for f in range(60):
        a = [100 + 6 * f, 100, 180 + 6 * f, 400]  # walks right
        b = [500 - 6 * f, 120, 570 - 6 * f, 380]  # walks left, crossing in front around frame 33
        tracker.see(f, [a, b], [0.9, 0.85])
    assert len(tracker.tracks) == 2 and all(len(boxes) == 60 for boxes in tracker.tracks.values())
    first, second = tracker.tracks[1], tracker.tracks[2]
    assert first[59][0] > 400 and second[59][0] < 200, (first[59], second[59])  # each kept going its own way


def test_someone_lost_for_a_moment_is_joined_back_if_the_clothes_match():
    tracker = tracks.Tracker()
    for f in list(range(0, 30)) + list(range(60, 90)):  # gone for a second (a spin the detector lost)
        tracker.see(f, [[200 + f, 100, 280 + f, 400]], [0.9])
    assert len(tracker.tracks) == 2
    red, blue = stub_worker.colours(0), stub_worker.colours(1)
    joined, how = tracks.join_pieces(tracker.tracks, {1: red, 2: red})
    assert list(joined) == [1] and len(joined[1]) == 60 and how == {1: [2]}
    apart, _ = tracks.join_pieces(tracker.tracks, {1: red, 2: blue})  # someone else stepped into the same spot
    assert len(apart) == 2
    # The page gets a box (or null) for every frame; the motion job gets one for every frame, gaps filled.
    found = tracks.people_of(joined, 0, 89, 640, 480)
    assert len(found) == 1 and found[0]["frames_seen"] == 60 and found[0]["boxes"][45] is None
    filled, seen = tracks.fill(found[0]["boxes"])
    assert seen.count(False) == 30 and abs(filled[45][0] - 245.0) < 1e-6, filled[45]  # half way through the gap, half way between
    assert tracks.alike(red, red) > 0.99 and tracks.alike(red, blue) < 0.2


def test_the_people_found_get_same_person_and_reflection_marks():
    bench = Bench.get()
    assert bench.first["waiting_for"] == "choice" and bench.first["done"] == ["ready", "cuts", "people"], bench.first
    page = clip_file.read(os.path.join(bench.folder, "people.json"))
    assert [len(shot["people"]) for shot in page["shots"]] == [2, 3, 2, 3]
    for shot in page["shots"]:
        dancer, mirrored = shot["people"][0], next(p for p in shot["people"] if p["reflection_of"])
        assert dancer["id"] == 1 and dancer["reflection_of"] is None and mirrored["reflection_of"] == 1, shot["people"]
        assert dancer["person"] == 1, "the dancer is the same person in every shot"
        assert mirrored["person"] != 1, "within a shot no two people share a number"
        others = [p for p in shot["people"] if p is not dancer and p is not mirrored]
        assert all(p["reflection_of"] is None and p["person"] not in (1, mirrored["person"]) for p in others)
        # Pictures: a frame or two to draw the boxes on, a small one of each person, and a box on each frame shown.
        for key in shot["keyframes"]:
            assert os.path.getsize(os.path.join(bench.folder, key["picture"])) > 500
            assert len(dancer["boxes"][str(key["frame"])]) == 4
        assert all(os.path.getsize(os.path.join(bench.folder, t)) > 200 for p in shot["people"] for t in p["thumbs"])
    raw = clip_file.read(os.path.join(bench.folder, "people-raw.json"))
    assert len(raw["shots"][1]["people"][0]["boxes"]) == 45 and "jpeg" not in json.dumps(raw)


# ---- the worker's front door -----------------------------------------------------


def test_a_clip_goes_up_in_parts_and_only_whole():
    worker = endpoint_file.Direct(os.path.join(TEMP, "volume-2"), os.path.join(HERE, "stub_worker.py"), log=QUIET)
    path = os.path.join(TEMP, "Drawn Clip.mp4")
    sha = clip_file.sha256_of(path)
    assert endpoint_file.upload(worker, path, sha, part_bytes=20000)["parts"] >= 3
    kept = os.path.join(TEMP, "volume-2", "gemx", "clips", sha + ".mp4")
    assert clip_file.sha256_of(kept) == sha and os.listdir(os.path.dirname(kept)) == [sha + ".mp4"]
    assert endpoint_file.upload(worker, path, sha)["already_there"]
    # Parts that do not add up to the clip they claim to be are thrown away.
    wrong = hashlib.sha256(b"not this").hexdigest()
    refused = [
        {"kind": "upload", "clip": wrong, "index": 0, "total": 1, "data": base64.b64encode(b"something else").decode()},
        {"kind": "upload", "clip": "../../etc/passwd", "index": 0, "total": 1, "data": "aGk="},
        {"kind": "upload", "clip": sha[:-1] + "0", "index": 3, "total": 2, "data": "aGk="},
        {"kind": "upload", "clip": sha[:-1] + "0", "index": 0, "total": 1, "data": "not base64!"},
        {"kind": "people", "clip": wrong, "shots": [[0, 10]]},  # never uploaded
        {"kind": "people", "clip": "/etc/hosts", "shots": [[0, 10]]},
        {"kind": "shell", "run": "anything"},
        {"kind": "motion", "clip": sha, "first": 0, "last": 59, "boxes": [[0, 0, 10, 10]]},  # one box for sixty frames
    ]
    for job in refused:
        try:
            worker.call(job)
        except endpoint_file.WorkerFailed:
            continue
        raise AssertionError(f"the worker took {job}")
    assert os.listdir(os.path.dirname(kept)) == [sha + ".mp4"], "nothing but the one whole clip is on the volume"
    info, record = worker.call({"kind": "info"})
    assert info["gpu"].startswith("none") and record["seconds"]["work"] >= 0
    worker.close()


def test_an_answer_that_arrives_damaged_is_not_believed():
    data = json.dumps({"hello": "world"}).encode()
    items = [{"kind": "chunk", "index": 1, "total": 2, "data": base64.b64encode(data[8:]).decode()}, {"kind": "chunk", "index": 0, "total": 2, "data": base64.b64encode(data[:8]).decode()},
             {"kind": "done", "sha256": hashlib.sha256(data).hexdigest()}]
    assert json.loads(endpoint_file.join_chunks(items)) == {"hello": "world"}  # out of order is fine
    for broken in (items[1:], items[:2], [items[0], items[0], items[2]]):
        try:
            endpoint_file.join_chunks(broken)
        except endpoint_file.WorkerFailed:
            continue
        raise AssertionError("a damaged answer was believed")
    assert "GEMX_ENDPOINT_ID" in str(_fails(lambda: _without_env(endpoint_file.Endpoint.from_env)))


def _without_env(call):
    saved = {k: os.environ.pop(k, None) for k in ("GEMX_ENDPOINT_ID",)}
    os.environ.setdefault("RUNPOD_API_KEY", "not-a-key")
    try:
        return call()
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
        if os.environ.get("RUNPOD_API_KEY") == "not-a-key":
            del os.environ["RUNPOD_API_KEY"]


def _fails(call):
    try:
        call()
    except Exception as error:  # noqa: BLE001
        return error
    raise AssertionError("expected a refusal")


# ---- the choice ------------------------------------------------------------------


def test_only_a_choice_that_fits_the_people_found_is_kept():
    people = {"shots": [{"index": 0, "people": [{"id": 1}, {"id": 2}]}, {"index": 1, "people": [{"id": 1}]}]}
    assert people_file.clean({"shots": {"0": 2, "1": "skip"}}, people) == {"format": "forge-video-choice/1", "camera": "still", "shots": {"0": 2, "1": "skip"}}
    assert people_file.clean({"shots": {"1": 1, "0": 1}, "camera": "moving"}, people)["camera"] == "moving"
    for bad in (
        None, [], "x", {"shots": {"0": 2}},  # a shot left undecided
        {"shots": {"0": 3, "1": 1}},  # nobody has that number
        {"shots": {"0": "2", "1": 1}}, {"shots": {"0": True, "1": 1}}, {"shots": {"0": 1.0, "1": 1}},
        {"shots": {"0": 1, "1": 1, "2": 1}}, {"shots": {"0": "skip", "1": "skip"}},  # nobody to follow at all
        {"shots": {"0": 1, "1": 1}, "camera": "vipe"}, {"shots": {"0": 1, "1": 1}, "path": "../../x"}, {"shots": [1, 1]},
    ):
        assert isinstance(_fails(lambda: people_file.clean(bad, people)), ValueError), bad


def test_the_gallery_saves_a_choice_and_nothing_else():
    import gallery

    bench = Bench.get()
    gallery.VIDEOS, gallery.SHOTS = bench.videos, bench.shots
    server = gallery.ThreadingHTTPServer(("127.0.0.1", 0), gallery.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    def ask(method, path, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        conn.request(method, path, body=data, headers={"Content-Type": "application/json", **(headers or {})} if data is not None else (headers or {}))
        response = conn.getresponse()
        text = response.read()
        conn.close()
        return response.status, text

    def files():
        return sorted(os.path.relpath(os.path.join(base, n), TEMP) for base, _, names in os.walk(TEMP) for n in names)

    choice_file = os.path.join(bench.folder, "choice.json")
    good = {"shots": {"0": 1, "1": 1, "2": "skip", "3": 1}, "camera": "still"}
    before = files()
    refused = [
        ("POST", "/api/videos/drawn-clip/people", good, None, 404),  # another file of the clip
        ("POST", "/api/videos/drawn-clip/choice.json", good, None, 404),
        ("POST", "/api/videos/../videos/drawn-clip/choice", good, None, 404),
        ("POST", "/api/videos/drawn-clip/../../shots/x/choice", good, None, 404),
        ("POST", "/api/videos/%2e%2e/choice", good, None, 404),
        ("POST", "/api/videos/drawn-clip%2f..%2fx/choice", good, None, 404),
        ("POST", "/api/videos/Drawn-Clip/choice", good, None, 404),
        ("POST", "/api/videos/no-such-clip/choice", good, None, 404),
        ("POST", "/videos/drawn-clip/choice.json", good, None, 404),
        ("POST", "/runs/x/brief.json", good, None, 404),
        ("POST", "/api/runs", good, None, 404),
        ("POST", "/api/videos/drawn-clip/choice", {"shots": {"0": 9, "1": 1, "2": 1, "3": 1}}, None, 400),  # nobody is number 9
        ("POST", "/api/videos/drawn-clip/choice", {"shots": {"0": 1}}, None, 400),
        ("POST", "/api/videos/drawn-clip/choice", {**good, "file": "../x"}, None, 400),
        ("POST", "/api/videos/drawn-clip/choice", good, {"Content-Type": "text/plain"}, 415),  # what a form on another site could send
        ("POST", "/api/videos/drawn-clip/choice", good, {"Origin": "http://elsewhere.example"}, 403),
        ("PUT", "/api/videos/drawn-clip/choice", good, None, 501),
        ("DELETE", "/videos/drawn-clip/clip.json", None, None, 501),
    ]
    for method, path, body, headers, want in refused:
        status, _ = ask(method, path, body, headers)
        assert status == want, (method, path, status, want)
    assert ask("POST", "/api/videos/drawn-clip/choice", raw=b"{not json")[0] == 400
    assert ask("POST", "/api/videos/drawn-clip/choice", raw=b" " * (70 * 1024))[0] == 413
    assert files() == before and not os.path.exists(choice_file), "a refused POST wrote something"

    status, text = ask("POST", "/api/videos/drawn-clip/choice", good, {"Origin": f"http://127.0.0.1:{port}"})
    assert status == 200 and json.loads(text)["choice"]["shots"] == good["shots"], (status, text)
    assert files() == sorted(before + [os.path.relpath(choice_file, TEMP)]), "exactly one new file: the choice"
    assert people_file.load_choice(bench.folder)["shots"] == {"0": 1, "1": 1, "2": "skip", "3": 1}
    # Reading still works, a film can be asked for a piece at a time (a phone does), and nothing outside is served.
    listed = json.loads(ask("GET", "/api/videos")[1])
    assert listed[0]["id"] == "drawn-clip" and listed[0]["choice"]["shots"]["2"] == "skip" and len(listed[0]["people"]) == 4
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", "/videos/drawn-clip/clip.mp4", headers={"Range": "bytes=100-199"})
    piece = conn.getresponse()
    size = os.path.getsize(os.path.join(bench.folder, "clip.mp4"))
    assert piece.status == 206 and piece.getheader("Content-Range") == f"bytes 100-199/{size}" and len(piece.read()) == 100
    conn.close()
    assert ask("GET", "/videos/drawn-clip/clip.mp4")[0] == 200 and ask("GET", "/videos/../justfile")[0] == 404 and ask("GET", "/videos/%2e%2e/justfile")[0] == 404
    # A choice.json that is a link to somewhere else is not written through.
    os.remove(choice_file)
    target = os.path.join(TEMP, "elsewhere.json")
    os.symlink(target, choice_file)
    assert ask("POST", "/api/videos/drawn-clip/choice", good)[0] == 400 and not os.path.exists(target)
    os.remove(choice_file)
    server.shutdown()
    server.server_close()


# ---- conversion ------------------------------------------------------------------


def test_a_gemx_answer_becomes_our_motion_by_what_it_looks_like():
    truth = stub_worker.dance(SK, 30, 89)
    # Their body: taller, shins leaning, in a world that faces another way and starts somewhere else.
    raw = stub_worker.as_gemx(SK, CARD, truth, 30, world_turn_deg=70.0, world_at=(2.0, 0.0, -3.0))
    assert len(raw["joints"]) == 77 and len(raw["turns"][0]) == 77 * 4 and len(raw["contacts"][0]) == 6
    motion, report = soma77.convert(raw, SK, CARD)
    assert motion["format"] == "forge-soma-motion/1" and motion["joints"] == SK.joints and len(motion["contacts"][0]) == 4
    assert 0.92 < report["size_ours_over_theirs"] < 0.95 and report["upright"] > 0.95 and abs(report["floor_moved_cm"]) < 0.5, report
    assert max(v["worst"] for v in report["ours_vs_gemx_cm"].values()) < 0.5, report["ours_vs_gemx_cm"]
    # Set facing forward at the origin, it is the dance that went in: every joint within a millimetre or two.
    back = timeline.moved(motion, -timeline.facing(SK, motion, 0), 0.0, 0.0)
    back = timeline.moved(back, 0.0, truth["root"][0][0] - back["root"][0][0], truth["root"][0][2] - back["root"][0][2])
    worst = max(math.dist(a, b) for f in range(0, 60, 3) for a, b in zip(positions(back, f), positions(truth, f)))
    assert worst < 0.003, worst
    # The left arm is the high one in the dance, and still is: nothing got mirrored on the way.
    pos = positions(back, 10)
    assert pos[SK.index["LeftHand"]][1] > pos[SK.index["RightHand"]][1] + 0.15 and pos[SK.index["LeftHand"]][0] > 0 > pos[SK.index["RightHand"]][0]
    # A body whose rest pose stands the other way round comes out the same.
    turned, about = soma77.convert(stub_worker.as_gemx(SK, CARD, truth, 30, world_turn_deg=70.0, world_at=(2.0, 0.0, -3.0), stands_turned_deg=180.0), SK, CARD)
    assert abs(about["rest_pose_turned_deg"] - 180.0) < 0.01
    assert max(math.dist(a, b) for a, b in zip(positions(turned, 20), positions(motion, 20))) < 0.002
    # Upside down, or without our joints, it is refused in plain words.
    flipped = json.loads(json.dumps(raw))
    for row in flipped["turns"]:
        for j in range(77):
            x, y, z, w = row[4 * j : 4 * j + 4]
            row[4 * j : 4 * j + 4] = [w, -z, y, -x]  # half a turn about X, put in front of every joint's turn
    assert "upside down" in str(_fails(lambda: soma77.convert(flipped, SK, CARD)))
    short = {**raw, "joints": raw["joints"][:40]}
    assert "lacks joints" in str(_fails(lambda: soma77.convert(short, SK, CARD)))
    assert "not a motion" in str(_fails(lambda: soma77.convert({"format": "gemx-people/1"}, SK, CARD)))


def test_shots_join_into_one_motion_that_follows_the_film():
    bench = Bench.get()
    people_file.save_choice(bench.videos, bench.name, {"shots": {"0": 1, "1": 1, "2": 1, "3": 1}})
    jobs_before = len(bench.worker.jobs)
    result = bench.go()
    assert result["waiting_for"] is None and result["done"] == ["motion", "shot"], result
    assert bench.worker.jobs[jobs_before:] == ["have", "motion", "motion", "motion", "motion"], bench.worker.jobs[jobs_before:]
    shot = result["shot"]
    assert os.path.basename(shot) == "video-drawn-clip"
    with open(os.path.join(shot, "motion.json")) as f:
        motion = json.load(f)
    source, plan, checks = (clip_file.read(os.path.join(shot, n)) for n in ("source.json", "plan.json", "checks.json"))
    assert len(motion["root"]) == FRAMES == plan["frames"] == source["frames"] == checks["frames"]
    assert [(p["clip_first_frame"], p["first_frame"]) for p in source["pieces"]] == [(0, 0), (60, 60), (105, 105), (165, 165)]
    assert [j["boundary_frame"] for j in plan["seams"]] == CUTS
    # Each shot came back in a world of its own (the stand-in turns every one another way); joined, the body
    # does not jump: across each cut it faces the same way and is where it was heading.
    for cut in CUTS:
        turn = (timeline.facing(SK, motion, cut) - timeline.facing(SK, motion, cut - 1) + 180.0) % 360.0 - 180.0
        step = math.hypot(motion["root"][cut][0] - motion["root"][cut - 1][0], motion["root"][cut][2] - motion["root"][cut - 1][2])
        assert abs(turn) < 3.0 and step < 0.05, (cut, turn, step)
    assert all(abs(j["turned_deg"]) > 10.0 for j in source["joins"]), "every shot had to be turned to carry on from the last"
    # The film's shots are stretches of one continuous dance; the joined motion is that dance, frame for frame.
    truth = stub_worker.dance(SK, 0, FRAMES - 1)
    worst = max(math.dist(a, b) for f in range(0, FRAMES, 2) for a, b in zip(positions(motion, f), positions(truth, f)))
    assert worst < 0.05, worst
    # checks.py took it: feet that never leave the floor barely slide, nothing is under it, and each cut is a seam it measured.
    assert all(foot["frames_on_ground"] == FRAMES and foot["slide_speed_cm_per_s"] < 2.0 for foot in checks["feet"].values()), checks["feet"]
    assert checks["floor"]["worst"]["depth_cm"] < 1.0 and len(checks["seams"]["seams"]) == 3, checks["floor"]
    assert all(seam["pose_jump_deg_per_frame"] < 25.0 for seam in checks["seams"]["seams"]), checks["seams"]["seams"]
    # And it goes in where a Kimodo beat does: soma_to_plain.py reads it, and plants the feet.
    plain, converted = soma_to_plain.convert(motion, SK, "hero")
    assert plain["frames"] == FRAMES - 1 and converted["planted_feet"]["l"]["frames_planted"] > 150, converted


def test_changing_one_shot_remakes_only_that_shot():
    bench = Bench.get()
    assert bench.go()["done"] == [], "nothing to do when nothing changed"
    before = len(bench.worker.jobs)
    # Shot 2 has someone else in it (number 2, the other person). Follow them there, and leave shot 3 out.
    people_file.save_choice(bench.videos, bench.name, {"shots": {"0": 1, "1": 2, "2": "skip", "3": 1}})
    result = bench.go()
    assert bench.worker.jobs[before:] == ["have", "motion"] and result["done"] == ["motion", "shot"], (bench.worker.jobs[before:], result)
    source = clip_file.read(os.path.join(result["shot"], "source.json"))
    assert [p["shot"] for p in source["pieces"]] == [0, 1, 3] and source["frames"] == FRAMES - 60
    assert [(p["clip_first_frame"], p["first_frame"]) for p in source["pieces"]] == [(0, 0), (60, 60), (165, 105)]
    # Back to the first choice: every motion is still there, so nothing is asked of the worker.
    people_file.save_choice(bench.videos, bench.name, {"shots": {"0": 1, "1": 1, "2": 1, "3": 1}})
    record = clip_file.read(os.path.join(bench.folder, "motion", "shot-001.record.json"))
    assert record["person"] == 2
    before = len(bench.worker.jobs)
    assert bench.go()["done"] == ["motion", "shot"] and bench.worker.jobs[before:] == ["have", "motion"]  # shot 2 again, for person 1


def test_filmed_beside_the_clip_and_cast_in_blender():
    """Only with --cast RUNS: the mannequin filmed next to the clip, in step, and a character put in the shot."""
    if not CAST_RUNS:
        return
    bench = Bench.get()
    result = video.advance(bench.name, bench.videos, bench.shots, connect=lambda: bench.worker, log=QUIET)
    assert result["done"] == ["film"], result
    film = clip_file.probe(result["film"])
    # An upright clip and an upright mannequin, side by side, as long as the kept frames, with the clip's sound.
    assert film["width"] == 1080 and film["height"] == 960 and film["sound"] and abs(film["seconds"] - FRAMES / 30.0) < 0.15, film
    assert os.path.exists(os.path.join(result["shot"], "strip.png")) and os.path.exists(os.path.join(result["shot"], "motion.glb"))
    runs = [os.path.join(CAST_RUNS, r) for r in sorted(os.listdir(CAST_RUNS)) if os.path.exists(os.path.join(CAST_RUNS, r, "lowpoly.glb")) and os.path.exists(os.path.join(CAST_RUNS, r, "gait.json"))]
    assert runs, f"no character with a low-poly version in {CAST_RUNS}"
    character = next((r for r in runs if "villager" in r), runs[0])
    done = subprocess.run([film_blender(), "-b", "--factory-startup", "--python-exit-code", "1", "-P", os.path.join(REPO, "scripts", "motion", "apply_shot.py"), "--", result["shot"], character, "--versions", "lowpoly", "--name", "hero"],
                          capture_output=True, text=True)
    assert done.returncode == 0, (done.stdout + done.stderr)[-2000:]
    record = clip_file.read(os.path.join(result["shot"], "lowpoly-hero.json"))
    assert os.path.getsize(os.path.join(result["shot"], "lowpoly-hero.glb")) > 50000 and record["animation"]["frames"] == FRAMES - 1, record["animation"]
    print(f"      cast {os.path.basename(character)}: {[line for line in done.stdout.splitlines() if line.startswith('APPLY')][0][:260]}")
    # And the shot of three makers: our poses, sentences (real Kimodo answers from a cache, where there are any) and the clip.
    mixed = os.path.join(bench.shots, "mixed-cast")
    made = shoot_offline(mixed, mixed_shot_list({"clip": "drawn-clip", "shot": 3, "from_s": 4.0, "to_s": 5.0}), bench.videos)
    done = subprocess.run([film_blender(), "-b", "--factory-startup", "--python-exit-code", "1", "-P", os.path.join(REPO, "scripts", "motion", "apply_shot.py"), "--", mixed, character, "--versions", "lowpoly", "--name", "hero"],
                          capture_output=True, text=True)
    assert done.returncode == 0, (done.stdout + done.stderr)[-2000:]
    record = clip_file.read(os.path.join(mixed, "lowpoly-hero.json"))
    assert os.path.getsize(os.path.join(mixed, "lowpoly-hero.glb")) > 50000 and record["animation"]["frames"] == made["plan"]["frames"] - 1, record["animation"]
    for seam in made["notes"]["seams"]:
        print(f"      join {seam['from']} to {seam['to']}: the tween ended {seam['tween_missed_by_cm']} cm and {seam['tween_missed_by_deg']} deg from the next piece")
    print(f"      mixed shot cast: {[line for line in done.stdout.splitlines() if line.startswith('APPLY')][0][:200]}")


# ---- a clip as one beat of a shot ------------------------------------------------


def mixed_shot_list(routine: dict) -> dict:
    """Stand in the wings (our pose), walk on (a sentence), the routine (the clip), a bow (a sentence), stand (our pose)."""
    stand = {"pose": "stand", "at_m": 0.0, "side_m": 0.0, "facing_deg": 0.0, "speed_mps": 0.0, "tokens": 9, "early_frames": 0, "pins": [], "hold_pins_frames": 0}
    return {
        "title": "Three ways of moving in one shot", "start_pose": "stand", "start_mark": "wings", "path": [], "props": [], "camera": [],
        "beats": [
            {"name": "Waits in the wings", "seconds": 0.97, "source": "poses", "moves": [dict(stand)], "at": "wings"},
            {"name": "Walks on", "seconds": 3.5, "source": "text", "moves": [], "prompt": "A person walks forward at an easy pace, then stops.", "from_m": 0.0, "to_m": 0.0,
             "keys": [{"pose": "stand", "at_seconds": 0.0, "at_m": 0.0, "side_m": 0.0, "facing_deg": 0.0, "only": [], "where": "start"}], "from": "wings", "to": "monologue"},
            {"name": "The routine", "seconds": 1.0, "source": "video", "moves": [], "at": "monologue", **routine},
            {"name": "Takes a bow", "seconds": 2.0, "source": "text", "moves": [], "prompt": "A person bows deeply, then straightens up.", "from_m": 0.0, "to_m": 0.0, "keys": None, "at": "monologue"},
            {"name": "Stands easy", "seconds": 0.97, "source": "poses", "moves": [dict(stand)], "at": "monologue"},
        ],
    }


def kimodo_from_a_cache(request: dict):
    """With --cast: a real Kimodo answer from a shot made before, for a sentence that goes about as far. None if there is none."""
    shots = os.path.join(os.path.dirname(CAST_RUNS), "shots") if CAST_RUNS else ""
    if not os.path.isdir(shots):
        return None
    need = request["prompts"][0]["frames"]
    far = lambda r: math.hypot(*next(c for c in r["prompts"][0]["constraints"] if c["type"] == "path")["points"][-1])  # noqa: E731
    best = None
    for shot in sorted(os.listdir(shots)):
        cache = os.path.join(shots, shot, "cache")
        for name in sorted(os.listdir(cache)) if os.path.isdir(cache) else []:
            if not name.endswith(".request.json") or not os.path.exists(os.path.join(cache, name.replace(".request", ""))):
                continue
            asked = clip_file.read(os.path.join(cache, name)) or {}
            if asked.get("kind") == "text" and asked["prompts"][0]["frames"] >= need:
                off = abs(far(asked) - far(request))
                if "walks" in request["prompts"][0]["text"] and not any(word in asked["prompts"][0]["text"] for word in ("walk", "jog", "run")):
                    off += 100.0  # for a walk, a sentence about going somewhere on foot before any other
                if best is None or off < best[0]:
                    best = (off, os.path.join(cache, name.replace(".request", "")), asked["prompts"][0]["text"])
    if best is None:
        return None
    answer = clip_file.read(best[1])
    print(f"      a real Kimodo answer for \"{request['prompts'][0]['text'][:40]}...\": \"{best[2][:60]}...\" ({os.path.relpath(best[1], shots)})")
    return {**answer, **{key: answer[key][:need] for key in ("root", "rotations", "contacts")}}


def shoot_offline(folder: str, shot_list: dict, videos: str) -> dict:
    """What `just shoot` does after the shot list, with no worker: plan_shot.py as it is run, then timeline.py's
    passes with the pretend models answering, then checks.py and to_gltf.py."""
    import test_timeline

    os.makedirs(folder, exist_ok=True)
    clip_file.write(os.path.join(folder, "shotlist.json"), shot_list)
    brief = os.path.join(folder, "brief.json")
    clip_file.write(brief, {"name": "mixed", "set": "studio"})
    env = {**os.environ, "FORGE_VIDEOS": videos}
    planned = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "motion", "plan_shot.py"), folder, "--brief", brief], capture_output=True, text=True, env=env)
    if planned.returncode != 0:
        raise ValueError(planned.stderr.strip().splitlines()[-1])
    asked = []
    for _ in range(4):
        result = timeline.step(folder, SK)
        if not result["todo"]:
            break
        for item in result["todo"]:
            request = clip_file.read(timeline.cache_path(folder, item["request"], "request"))
            asked.append((item["kind"], item["what"]))
            answer = (kimodo_from_a_cache(request) if item["kind"] == "text" else None) or test_timeline.pretend(request)
            clip_file.write(timeline.cache_path(folder, item["request"]), answer, indent=None)
    assert result["joined"], result
    for script in ("checks.py", "to_gltf.py"):
        done = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "motion", script), folder], capture_output=True, text=True)
        assert done.returncode == 0, done.stderr[-800:]
    with open(os.path.join(folder, "motion.json")) as f:
        motion = json.load(f)
    return {"planned": planned.stdout, "asked": asked, "motion": motion, "plan": clip_file.read(os.path.join(folder, "plan.json")), "notes": result["notes"], "checks": clip_file.read(os.path.join(folder, "checks.json"))}


def test_a_stretch_of_a_clip_is_one_beat_between_a_pose_and_two_sentences():
    bench = Bench.get()
    folder = os.path.join(bench.shots, "mixed")
    # Shot 3 of the clip is frames 105 to 164; the stretch wanted is its seconds 4 to 5 (frames 120 to 150).
    made = shoot_offline(folder, mixed_shot_list({"clip": "drawn-clip", "shot": 3, "from_s": 4.0, "to_s": 5.0}), bench.videos)
    plan, motion = made["plan"], made["motion"]
    assert [p["source"] for p in plan["pieces"]] == ["poses", "text", "video", "text", "poses"]
    # Nothing was asked of a worker for the clip: its motion was on hand. The opening pose, the two sentences and four joins were.
    assert [kind for kind, _ in made["asked"]] == ["inbetween", "text", "text", "inbetween", "inbetween", "inbetween", "inbetween"], made["asked"]
    routine = plan["pieces"][2]
    assert routine["clip_frames"] == [107, 162] and routine["handles"] == [13, 12] and routine["asked_for"] == [13, 43] and routine["person"] == 1, routine
    assert "request" not in routine and os.path.exists(timeline.cache_path(folder, routine["video"]))
    into, out = plan["seams"][1], plan["seams"][2]
    assert (into["to"], into["take_from_start"], out["from"], out["take_from_end"]) == ("The routine", 13, "The routine", 12)
    # In the joined shot: Kimodo, a tween, the clip, a tween, Kimodo, with our poses at the two ends.
    by = [s["made_by"] for s in motion["segments"]]
    assert by == ["our poses, MotionBricks between them", "MotionBricks, a tween across the seam", "Kimodo, from a sentence", "MotionBricks, a tween across the seam", "GEM-X, from a video",
                  "MotionBricks, a tween across the seam", "Kimodo, from a sentence", "MotionBricks, a tween across the seam", "our poses, MotionBricks between them"], by
    assert len(motion["root"]) == plan["frames"] == made["checks"]["frames"]
    # The stretch asked for is whole: the joins used up the handles, not the dance. From its second frame (the first
    # is where the tween arrives) to its last, every joint is turned as the clip's dancer turned it.
    kept = next(s for s in motion["segments"] if s["made_by"].startswith("GEM-X"))
    start = plan["pieces"][2]["first_frame"] + 13
    assert (kept["first_frame"], kept["last_frame"]) == (start + 1, start + 30), (kept, start)
    truth = stub_worker.dance(SK, 120, 150)
    for f in range(1, 31):
        ours, theirs = motion["rotations"][start + f], truth["rotations"][f]
        worst = max(abs(abs(sum(ours[4 * j + k] * theirs[4 * j + k] for k in range(4))) - 1.0) for j in range(1, len(SK.joints)))
        # (To four places above the hips; the legs to within a degree or two, where a held foot bent a knee a little.)
        upper = max(abs(abs(sum(ours[4 * j + k] * theirs[4 * j + k] for k in range(4))) - 1.0) for j in range(1, len(SK.joints)) if "Leg" not in SK.joints[j] and "Shin" not in SK.joints[j] and "Foot" not in SK.joints[j] and "Toe" not in SK.joints[j])
        assert (upper < 1e-4 or (f <= timeline.EASE_FRAMES and upper < 1e-3)) and worst < 3e-3, (f, upper, worst)
    # It stands where the set says: on the monologue mark, facing the way that mark faces, though the stand-in's
    # world for that shot faced somewhere else entirely.
    with open(os.path.join(REPO, "sets", "studio", "set.json")) as f:
        mark = json.load(f)["marks"]["monologue"]
    at = motion["root"][start + 1]
    hips_ahead = truth["root"][1][2] - truth["root"][0][2]
    assert math.hypot(at[0] - mark["at"][0], at[2] - mark["at"][1]) < 0.05 + abs(hips_ahead), (at, mark["at"])
    assert abs((timeline.facing(SK, motion, start + 1) - mark["facing_deg"] + 180.0) % 360.0 - 180.0) < 2.0
    assert routine["ends_from_its_mark_cm"] < 2.0 and routine["placement"]["travels"] is False
    assert "The routine: frames 107-162 of the clip drawn-clip (shot 3, person 1), 13 and 12 of them for the joins" in made["planned"]
    # checks.py measured every join, and the box figure was made.
    assert len(made["checks"]["seams"]["seams"]) == 4 and os.path.getsize(os.path.join(folder, "motion.glb")) > 10000
    assert all(seam["tween_missed_by_cm"] < 1.0 for seam in made["notes"]["seams"]), made["notes"]["seams"]


def test_a_video_beat_that_asks_for_what_is_not_there_is_told_so():
    bench = Bench.get()
    refused = [
        ({"clip": "drawn-clip", "from_s": 3.0, "to_s": 4.5}, "a cut falls between them"),
        ({"clip": "drawn-clip", "shot": 2, "from_s": 4.0, "to_s": 5.0}, "shot 2 of \"drawn-clip\" runs from 2.00 to 3.47 s"),
        ({"clip": "drawn-clip", "shot": 9, "from_s": 4.0, "to_s": 5.0}, "has shots 1 to 4"),
        ({"clip": "no-such-clip", "from_s": 4.0, "to_s": 5.0}, "there is no clip \"no-such-clip\""),
        ({"clip": "../etc", "from_s": 4.0, "to_s": 5.0}, "names its clip"),
        ({"clip": "drawn-clip", "from_s": 4.0}, "which seconds of the clip"),
        ({"clip": "drawn-clip", "from_s": 4.0, "to_s": 4.2}, "lasts 0.5 to 60 seconds"),
        ({"clip": "drawn-clip", "shot": 3, "from_s": 4.0, "to_s": 5.0, "person": 2}, "has motion for person 1, not 2"),
        ({"clip": "drawn-clip", "shot": 3, "from_s": 4.0, "to_s": 5.0, "drift": "sideways"}, "drift is keep or flatten"),
    ]
    for n, (routine, said) in enumerate(refused):
        error = _fails(lambda: shoot_offline(os.path.join(bench.shots, f"refused-{n}"), mixed_shot_list(routine), bench.videos))
        assert said in str(error), (routine, str(error))
    # A shot whose motion was never made (it was skipped on the clip's page) says what to do about it.
    os.rename(os.path.join(bench.folder, "motion", "shot-002.json"), os.path.join(bench.folder, "motion", "hidden.json"))
    try:
        error = _fails(lambda: shoot_offline(os.path.join(bench.shots, "refused-none"), mixed_shot_list({"clip": "drawn-clip", "from_s": 4.0, "to_s": 5.0}), bench.videos))
        assert "has no motion for shot 3 yet" in str(error) and "just video drawn-clip" in str(error), str(error)
    finally:
        os.rename(os.path.join(bench.folder, "motion", "hidden.json"), os.path.join(bench.folder, "motion", "shot-002.json"))


def test_another_dancer_of_the_same_shot_can_be_asked_for_by_number():
    bench = Bench.get()
    before = len(bench.worker.jobs)
    result = video.advance(bench.name, bench.videos, bench.shots, connect=lambda: bench.worker, log=QUIET, film=False, also=[(2, 2)])
    assert bench.worker.jobs[before:] == ["have", "motion"] and result["done"] == ["motion"], (bench.worker.jobs[before:], result)
    record = clip_file.read(os.path.join(bench.folder, "motion", "shot-001-person-2.record.json"))
    assert record["person"] == 2 and clip_file.read(os.path.join(bench.folder, "motion", "shot-001.record.json"))["person"] == 1
    assert video.advance(bench.name, bench.videos, bench.shots, connect=lambda: bench.worker, log=QUIET, film=False, also=[(2, 2)])["done"] == []
    assert "no person 7 in shot 2" in str(_fails(lambda: video.advance(bench.name, bench.videos, bench.shots, connect=lambda: bench.worker, log=QUIET, film=False, also=[(2, 7)])))
    # Shot 2 is frames 60 to 104. A beat that names person 2 reads their file; one that names nobody, the chosen one's.
    for who, want in ((2, 2), (None, 1)):
        routine = {"clip": "drawn-clip", "shot": 2, "from_s": 2.5, "to_s": 3.2, **({"person": who} if who else {})}
        made = shoot_offline(os.path.join(bench.shots, f"person-{want}"), mixed_shot_list(routine), bench.videos)
        assert made["plan"]["pieces"][2]["person"] == want


def test_a_dancer_who_drifts_is_kept_put_or_walked_to_a_mark_on_request():
    bench = Bench.get()
    # The same clip, but in shot 3 the dancer creeps 1.2 m sideways and 0.6 m back over the two seconds (a camera
    # that drifted, or a dance that wanders).
    videos = os.path.join(TEMP, "drifting-videos")
    shutil.copytree(bench.videos, videos)
    path = os.path.join(videos, "drawn-clip", "motion", "shot-002.json")
    answer = clip_file.read(path)
    for f, root in enumerate(answer["root"]):
        root[0] += 1.2 * f / 59.0
        root[2] -= 0.6 * f / 59.0
    clip_file.write(path, answer, indent=None)
    import_made = {}
    saved = os.environ.get("FORGE_VIDEOS")
    os.environ["FORGE_VIDEOS"] = videos
    try:
        def lay(routine: dict) -> tuple:
            import_made.clear()
            stand = {"pose": "stand", "at_m": 0.0, "side_m": 0.0, "facing_deg": 0.0, "speed_mps": 0.0, "tokens": 9, "early_frames": 0, "pins": [], "hold_pins_frames": 0}
            shot = {"start_pose": "stand", "path": [{"x": 0.0, "z": 0.0}, {"x": 0.0, "z": 4.0}],
                    "beats": [{"name": "Waits", "seconds": 0.97, "source": "poses", "moves": [stand]},
                              {"name": "The routine", "seconds": 1.0, "source": "video", "clip": "drawn-clip", "shot": 3, "from_s": 4.0, "to_s": 5.0, "from_m": 0.0, "to_m": 0.0, "lock_feet": False, **routine}]}
            with open(os.path.join(REPO, "motion", "poses.json")) as f:
                record, _ = timeline.lay_out(shot, json.load(f), SK, made=import_made)
            piece = record["pieces"][1]
            return piece, import_made[piece["video"]]

        size = 0.9346  # our legs over the stand-in body's
        crept = math.hypot(1.2, 0.6) * 30.0 / 59.0 * size  # over the second asked for
        kept, motion = lay({})
        a, b = kept["asked_for"]
        assert abs(kept["ends_from_its_mark_cm"] - 100.0 * crept) < 1.5 and kept["drift_taken_out_cm"] == 0.0, kept
        assert math.hypot(motion["root"][a][0], motion["root"][a][2]) < 0.01, "it starts on its spot"
        flat, motion = lay({"drift": "flatten"})
        assert flat["ends_from_its_mark_cm"] < 0.5 and abs(flat["drift_taken_out_cm"] - 100.0 * crept) < 1.5, flat
        assert math.hypot(motion["root"][b][0], motion["root"][b][2]) < 0.01, "and ends on it"
        # Asked to go somewhere, it is turned to travel the way the path runs and ends on the far point.
        goes, motion = lay({"to_m": 0.5})
        assert goes["placement"]["travels"] and goes["ends_from_its_mark_cm"] < 0.5, goes
        assert abs(motion["root"][b][0]) < 0.01 and abs(motion["root"][b][2] - 0.5) < 0.01 and 0.1 < motion["root"][(a + b) // 2][2] < 0.4
        # Facing: turned a quarter turn on the path, it faces a quarter turn round.
        side, motion = lay({"facing_deg": 90.0})
        assert abs(timeline.facing(SK, motion, a) - 90.0) < 0.5
        # That was with the feet left alone. This dancer's feet never leave the floor, so held where they are down
        # (as they are unless a beat says otherwise) the creep has nothing to carry it: it would take a step.
        # (That was with the feet left alone. Held where they are down, as they are unless a beat says otherwise, a
        # creep slow enough to be a foot at rest has nothing to carry it; the cases further down try that.)
        held, _ = lay({"lock_feet": True})
        assert held["feet"]["locked"] and not kept["feet"]["locked"]
        # With no handles asked for, the joins eat the stretch's own ends.
        bare, _ = lay({"handles": False})
        assert bare["handles"] == [0, 0] and bare["clip_frames"] == [120, 150]
    finally:
        if saved is None:
            del os.environ["FORGE_VIDEOS"]
        else:
            os.environ["FORGE_VIDEOS"] = saved


# ---- a crew: several dancers of one clip, in formation ---------------------------


def test_where_people_stand_is_read_from_their_boxes():
    import formation

    width, height, focal = 960, 540, math.hypot(960, 540)
    camera, horizon = 0.8, 250.0  # a low camera, tilted a little

    def box(x_left: float, far: float, tall: float, pan: float = 0.0):
        cx = width / 2.0 - x_left * focal / far + pan
        top, bottom = horizon + focal * (camera - tall) / far, horizon + focal * camera / far
        wide = 0.25 * tall * focal / far
        return [cx - wide, top, cx + wide, min(bottom, height - 1.0)]

    people, truth = {1: {"boxes": [], "top": [], "tall": []}, 2: {"boxes": [], "top": [], "tall": []}, 3: {"boxes": [], "top": [], "tall": []}}, {1: [], 2: [], 3: []}
    for f in range(240):
        t = f / 30.0
        pan = 60.0 * math.sin(0.5 * t)  # the camera swings: everyone moves across the picture together
        spots = {1: (0.1 * math.sin(t), 2.4 + 0.2 * math.sin(0.7 * t)),  # out front: so near that the picture cuts their feet off
                 2: (-0.9, 4.2 + 0.3 * math.sin(0.4 * t)), 3: (0.8 + 0.2 * math.sin(0.3 * t), 5.4)}
        for p, (x, z) in spots.items():
            tall = 1.7 - (0.5 * abs(math.sin(1.3 * t)) if p == 2 else 0.0)  # person 2 keeps crouching: no further away for it
            people[p]["boxes"].append(box(x, z, tall, pan))
            people[p]["tall"].append(tall)
            people[p]["top"].append(tall)
            truth[p].append((x, z))
    assert all(b[3] >= height - 3 for b in people[1]["boxes"]), "person 1's feet are out of the picture"
    seen, notes = formation.seen_from_boxes(people, width, height)
    assert abs(notes["camera_height_m"] - camera) < 0.05 and notes["feet_cut_off_share"]["1"] == 1.0, notes
    for p in (2, 3):  # whole in the picture: how far is exact, crouching or not
        assert max(abs(s[1] - z) for s, (_, z) in zip(seen[p], truth[p])) < 0.02
    assert max(abs(s[1] - z) for s, (_, z) in zip(seen[1], truth[1])) < 0.15, "cut off at the feet, read from the top of the box"
    # Places in the group: the camera's swing is gone (it moved everyone alike); who is left, right, front and back is kept.
    where = formation.places(seen, reach=5)
    for f in range(20, 220, 10):
        mx, mz = sum(truth[p][f][0] for p in truth) / 3.0, sum(truth[p][f][1] for p in truth) / 3.0
        for p in truth:
            # The swing shifts everyone sideways by the same pixels, which is a little more metres the further off they are.
            assert abs(where[p][f][0] - (truth[p][f][0] - mx)) < 0.12 and abs(where[p][f][1] - (truth[p][f][1] - mz)) < 0.12, (p, f, where[p][f])
    assert where[1][100][1] < where[2][100][1] and where[2][100][0] < where[1][100][0] < where[3][100][0]


def test_the_floor_follows_the_feet_when_the_models_floor_creeps():
    truth = stub_worker.dance(SK, 0, 239)
    raw = stub_worker.as_gemx(SK, CARD, truth, 0)
    for f, root in enumerate(raw["root"]):
        root[1] += 0.6 * f / 239.0  # GEM-X's world climbs 60 cm in eight seconds, as it does on a long shot
    motion, report = soma77.convert(raw, SK, CARD)
    toes = (SK.index["LeftToeBase"], SK.index["RightToeBase"])
    rest = min(SK.rest_world_pos[t][1] for t in toes)
    off = [min(positions(motion, f)[t][1] for t in toes) - rest for f in range(0, 240, 6)]
    assert max(abs(v) for v in off) < 0.03, off  # feet that never left the floor are on it from first frame to last
    assert 40.0 < report["floor_followed_cm"] < 60.0, report


# ---- feet that are down stay down ------------------------------------------------


def gliding(first: int, last: int, steps: bool = False, pivot: bool = False) -> dict:
    """The stand-in's dance (feet planted) made to skate: the whole body slid 60 cm sideways and 30 cm back over
    four seconds, as a camera's creep or a formation's nudging would. With `steps`, the model's contacts say the
    feet take turns (left down, both, right down, both, ...). With `pivot`, the left foot is up on its ball and
    turns a quarter turn about it."""
    from soma import Y, qaxis, qmul as mul

    motion = stub_worker.dance(SK, first, last)
    count = len(motion["root"])
    ankle = SK.index["LeftFoot"]
    for f in range(count):
        t = f / float(count - 1)
        motion["root"][f] = [motion["root"][f][0] + 0.6 * t, motion["root"][f][1], motion["root"][f][2] - 0.3 * t]
        if steps:
            phase = (f // 20) % 4
            motion["contacts"][f] = [1.0, 1.0, 1.0, 1.0] if phase in (1, 3) else ([1.0, 1.0, 0.0, 0.0] if phase == 0 else [0.0, 0.0, 1.0, 1.0])
        if pivot:
            motion["contacts"][f][0] = 0.0  # the left heel is up: only the ball is down
            row = motion["rotations"][f]
            pos, rot = SK.fk(motion["root"][f], [tuple(row[4 * j : 4 * j + 4]) for j in range(len(SK.joints))])
            turned = mul(qaxis(Y, 90.0 * t), rot[ankle])
            row[4 * ankle : 4 * ankle + 4] = list(mul(soma_conj(rot[SK.parents[ankle]]), turned))
    return motion


def soma_conj(q):
    return (-q[0], -q[1], -q[2], q[3])


def test_feet_that_are_down_are_held_and_drift_becomes_steps():
    import footlock

    toes = {"l": SK.index["LeftToeBase"], "r": SK.index["RightToeBase"]}
    # 1. Both feet down the whole time, the body skating 67 cm: held, the feet do not move and the body stays over them.
    skating = gliding(0, 119)
    locked, report = footlock.lock(SK, skating)
    before, after = footlock.slide(SK, skating), footlock.slide(SK, locked)
    assert report["slides_cm_per_s"] == after["cm_per_s"] == report["slides_where_held_cm_per_s"], "the model's contacts and the held stances are the same here"
    assert min(before["cm_per_s"].values()) > 15.0 and max(after["cm_per_s"].values()) < 0.3, (before, after)
    assert max(after["worst_stretch_cm"].values()) < 0.5 and report["frames_a_leg_could_not_reach"] == 0, (after, report)
    assert math.dist(locked["root"][0][::2], locked["root"][119][::2]) < 0.02, "nothing carried the hips anywhere"
    # The legs still reach the floor and nothing above the hips changed.
    for f in (0, 60, 119):
        for j, name in enumerate(SK.joints):
            if not any(part in name for part in ("Leg", "Shin", "Foot", "Toe")):
                assert locked["rotations"][f][4 * j : 4 * j + 4] == [round(c, 6) for c in skating["rotations"][f][4 * j : 4 * j + 4]], name
        assert abs(positions(locked, f)[toes["l"]][1] - SK.rest_world_pos[toes["l"]][1]) < 0.01
    # 2. The feet take turns. Each stance is held on one spot; the body's travel is still there, taken in steps:
    #    every time a foot comes down again it is further along.
    stepping = gliding(0, 159, steps=True)
    locked, report = footlock.lock(SK, stepping)
    after = footlock.slide(SK, locked)
    # The motion now says which feet are down as they were held: a held toe is 1, a foot let go is 0.
    assert locked["contacts"][10] == [1.0, 1.0, 0.0, 0.0] and locked["contacts"][50][2:] == [1.0, 1.0] and set(c for row in locked["contacts"] for c in row) == {0.0, 1.0}
    assert max(after["cm_per_s"].values()) < 1.0 and report["feet"]["l"]["spots"] >= 2 and report["feet"]["r"]["spots"] >= 2, (after, report)
    world = [(SK.fk(stepping["root"][f], [tuple(stepping["rotations"][f][4 * j : 4 * j + 4]) for j in range(len(SK.joints))])) for f in range(160)]
    stances = footlock.stances(SK, stepping, world)
    spots = [positions(locked, (s["first"] + s["last"]) // 2)[toes["l"]] for s in stances["l"]]
    for s in stances["l"]:
        inside = [positions(locked, f)[toes["l"]] for f in range(s["first"], s["last"] + 1)]
        assert max(math.dist(p[::2], inside[0][::2]) for p in inside) < 0.004, "a foot that is down does not move"
    assert all(b[0] - a[0] > 0.15 for a, b in zip(spots, spots[1:])), spots  # 60 cm in 160 frames, a step every 80
    assert math.dist(locked["root"][159][::2], locked["root"][0][::2]) > 0.45, "the body got where it was going, by stepping"
    assert max(math.dist(a[::2], b[::2]) for a, b in zip(locked["root"], stepping["root"])) < 0.25
    # 3. A pivot is still a pivot: up on the ball of the left foot and turning, the ball is held and the foot turns about it.
    turning = gliding(0, 89, pivot=True)
    locked, _ = footlock.lock(SK, turning)
    ball = [positions(locked, f)[toes["l"]] for f in range(90)]
    assert max(math.dist(p[::2], ball[0][::2]) for p in ball) < 0.005
    heel_before, heel_after = positions(locked, 0)[SK.index["LeftFoot"]], positions(locked, 89)[SK.index["LeftFoot"]]
    assert math.dist(heel_before[::2], heel_after[::2]) > 0.08, "the heel swung round the ball"
    # 4. In the air, nothing is held: a motion with no foot down comes back as it was.
    flying = gliding(0, 59)
    for row in flying["contacts"]:
        row[:] = [0.0, 0.0, 0.0, 0.0]
    flying["root"] = [[r[0], r[1] + 0.5, r[2]] for r in flying["root"]]
    locked, report = footlock.lock(SK, flying)
    assert report["feet"]["l"]["spots"] == 0 and locked["root"] == [[round(c, 5) for c in r] for r in flying["root"]]
    # The switch: FORGE_FOOT_LOCK=0 turns it off everywhere, and a beat can say "lock_feet": false.
    assert footlock.wanted() and footlock.wanted(True) and not footlock.wanted(False)
    os.environ["FORGE_FOOT_LOCK"] = "0"
    try:
        assert not footlock.wanted(True)
    finally:
        del os.environ["FORGE_FOOT_LOCK"]


def crew_of_two(routine: dict) -> tuple:
    """A segment for two roles on the studio set (a wait, a walk on, the routine in formation, a stand) and its take."""
    def stand(tokens):
        return {"pose": "stand", "at_m": 0, "side_m": 0, "facing_deg": 0, "speed_mps": 0, "tokens": tokens, "early_frames": 0, "pins": [], "hold_pins_frames": 0}

    def part(person, wings, place, wait, walk, hold, more):
        return {"title": f"person {person}", "start_pose": "stand", "start_mark": wings, "path": [], "beats": [
            {"name": "Waits", "seconds": 1.0, "source": "poses", "at": wings, "moves": [stand(wait)]},
            {"name": "Walks on", "seconds": walk / 30.0, "source": "text", "moves": [], "frames": walk, "to": place, "prompt": "{walk_on}", "keys": [{"pose": "stand", "at_seconds": 0, "at_m": 0, "side_m": 0, "facing_deg": 0, "only": [], "where": "start"}]},
            {"name": "Takes his place", "seconds": 1.0, "source": "poses", "at": place, "moves": [stand(hold)]},
            {"name": "The routine", "seconds": 0.5, "source": "video", "moves": [], "clip": "drawn-clip", "person": person, "from": place, "to": place + "_after",
             "formation": {"people": [1, 2], "at": "centre", "spread": 1.0}, **routine, **more},
            {"name": "Stands easy", "seconds": 1.0, "source": "poses", "at": place + "_after", "moves": [stand(9)]}]}

    segment = {"name": "two-dancers", "title": "Two dancers", "about": "Two walk on and dance as the two in the clip did.",
               "needs": {"roles": ["front", "side"], "marks": ["wings", "wings_2", "centre", "crew_front", "crew_right", "crew_front_after", "crew_right_after"]},
               "sentences": {"walk_on": "A person walks forward and stops."}, "together": ["The routine"], "beats": [],
               "roles": {"front": part(1, "wings_2", "crew_front", 13, 134, 12, {}), "side": part(2, "wings", "crew_right", 9, 150, 12, {})}}
    take = {"name": "two-dancers", "brief": "a test", "beats": [], "set": "studio", "segment": os.path.join(TEMP, "takes", "two-dancers.json"), "roles": {"front": "plain-young-villager", "side": "plain-young-villager"}}
    return segment, take


def test_a_take_dances_a_clip_in_the_formation_it_was_filmed_in():
    import formation
    import rehearse
    import segment as segment_file

    bench = Bench.get()
    assert os.path.exists(os.path.join(bench.folder, "motion", "shot-001-person-2.json")), "an earlier case made person 2 of shot 2"
    folder = os.path.join(TEMP, "takes")
    os.makedirs(folder, exist_ok=True)
    saved = os.environ.get("FORGE_VIDEOS")
    os.environ["FORGE_VIDEOS"] = bench.videos
    try:
        # Shot 2 of the clip is frames 60 to 104; the routine is its seconds 2.5 to 3.0, for both roles.
        template, take = crew_of_two({"from_s": 2.5, "to_s": 3.0})
        clip_file.write(os.path.join(folder, "two-dancers.json"), template)
        plan_file = os.path.join(folder, "take-plan.json")
        clip_file.write(plan_file, take)
        made = rehearse.rehearse(plan_file, os.path.join(folder, "rehearsal"), log=QUIET)
        front, side = made["roles"]["front"], made["roles"]["side"]
        # Both roles are the same length, the routine on the same frames, and neither asked a worker for it.
        assert len(front["motion"]["root"]) == len(side["motion"]["root"]) == made["frames"] == clip_file.read(os.path.join(folder, "rehearsal", "take.json"))["frames"]
        a, b = front["plan"]["pieces"][3], side["plan"]["pieces"][3]
        assert (a["first_frame"], a["last_frame"], a["clip_frames"]) == (b["first_frame"], b["last_frame"], b["clip_frames"]) and a["clip_frames"] == [62, 102]
        assert (a["person"], b["person"]) == (1, 2) and front["asked"].count("text") == 1
        # One formation: the same middle (the set's centre mark) and heading for both, and each placed from it by
        # where the picture had them. The stand-in's dancers stay on their own spot, so where they stand is the picture's doing alone.
        with open(os.path.join(REPO, "sets", "studio", "set.json")) as f:
            centre = json.load(f)["marks"]["centre"]["at"]
        assert a["formation"]["origin"] == b["formation"]["origin"] == centre and a["formation"]["heading"] == b["formation"]["heading"] == 0.0
        places = a["formation"]["places_in_the_group_m"]
        assert places == b["formation"]["places_in_the_group_m"]
        start = a["first_frame"] + 13
        size = 0.9346
        for f in range(start + 1, start + 15, 3):
            between = (front["motion"]["root"][f][0] - side["motion"]["root"][f][0], front["motion"]["root"][f][2] - side["motion"]["root"][f][2])
            # Facing the house (heading 0) from the camera's side (heading 180): the camera's left is the stage's -X, its far side the stage's -Z.
            want = (-(places["1"]["at_the_start"][0] - places["2"]["at_the_start"][0]) * size, -(places["1"]["at_the_start"][1] - places["2"]["at_the_start"][1]) * size)
            assert math.hypot(between[0] - want[0], between[1] - want[1]) < 0.06, (f, between, want)
            middle = ((front["motion"]["root"][f][0] + side["motion"]["root"][f][0]) / 2.0, (front["motion"]["root"][f][2] + side["motion"]["root"][f][2]) / 2.0)
            assert math.hypot(middle[0] - centre[0], middle[1] - centre[1]) < 0.06, middle
        # They were turned together, not each to face the front on their own.
        assert abs((timeline.facing(SK, front["motion"], start + 5) - timeline.facing(SK, side["motion"], start + 5) + 180.0) % 360.0 - 180.0) < 1.0
        # How close they come is measured, in the formation and over the whole take.
        assert a["formation"]["closest"]["hips_cm"] > 30.0 and made["together"]["hips_cm"] > 30.0 and "The routine" in made["together"]["by_beat"]
        assert os.path.exists(os.path.join(folder, "rehearsal", "front", "motion.glb")) and os.path.exists(os.path.join(folder, "rehearsal", "side", "checks.json"))
        # A rehearsal is not let near the real shots (its pretend answers would be taken for real ones).
        assert "somewhere other than shots/" in str(_fails(lambda: rehearse.rehearse(plan_file, os.path.join(REPO, "shots", "two-dancers"), log=QUIET)))
        # Roles that do not mean the same formation are told so, as is a role that is nobody in it.
        for change, said in (({"from_s": 2.6}, "do not ask for the same clip, seconds, people and mark"), ({"person": 7}, "is not one of the formation's people"), ({"person": 1}, "two roles are the same person")):
            broken, _ = crew_of_two({"from_s": 2.5, "to_s": 3.0})
            broken["roles"]["side"]["beats"][3].update(change)
            assert said in str(_fails(lambda: segment_file.expand(broken, take))), said
        missing, _ = crew_of_two({"from_s": 2.5, "to_s": 3.0})
        for part in missing["roles"].values():
            part["beats"][3]["formation"] = {"people": [1, 3], "at": "centre"}
        missing["roles"]["side"]["beats"][3]["person"] = 3
        clip_file.write(os.path.join(folder, "two-dancers.json"), missing)
        assert "has motion for person 1, not 3" in str(_fails(lambda: rehearse.rehearse(plan_file, os.path.join(folder, "rehearsal-3"), log=QUIET)))
    finally:
        if saved is None:
            del os.environ["FORGE_VIDEOS"]
        else:
            os.environ["FORGE_VIDEOS"] = saved


def test_a_stretch_runs_on_through_a_split_that_is_not_a_cut():
    import beat as video_beat

    bench = Bench.get()
    # The same clip, as if its first two shots were one long take that was only split for its length.
    videos = os.path.join(TEMP, "long-take-videos")
    shutil.copytree(bench.videos, videos)
    record = clip_file.read(os.path.join(videos, "drawn-clip", "shots.json"))
    for shot in record["shots"][:2]:
        shot["part_of_a_long_shot"] = True
    clip_file.write(os.path.join(videos, "drawn-clip", "shots.json"), record)
    want = video_beat.find({"name": "r", "clip": "drawn-clip", "from_s": 1.5, "to_s": 2.6}, videos)
    assert [s["index"] for s in want["shots"]] == [0, 1] and (want["first"], want["last"]) == (45, 78)
    whole, base, report = video_beat.joined(SK, want, "r")
    assert base == 0 and len(whole["root"]) == 105
    # One dance through the split: no jump in place, and each joint turned as the dance has it, either side.
    truth = stub_worker.dance(SK, 0, 104)
    assert max(math.dist(whole["root"][f], whole["root"][f + 1]) for f in range(55, 65)) < 0.03
    for f in (50, 59, 72, 100):
        worst = max(abs(abs(sum(whole["rotations"][f][4 * j + k] * truth["rotations"][f][4 * j + k] for k in range(4))) - 1.0) for j in range(1, len(SK.joints)))
        assert worst < 1e-4, (f, worst)
    # And the second part was not turned to "carry on facing": a camera that did not cut has not turned the world.
    assert abs((timeline.facing(SK, whole, 80) - timeline.facing(SK, soma77.convert(clip_file.read(want["files"][1]), SK)[0], 20) + 180.0) % 360.0 - 180.0) < 0.01
    # A real cut between the two is still refused (the unchanged clip).
    assert "a cut falls between them" in str(_fails(lambda: video_beat.find({"name": "r", "clip": "drawn-clip", "from_s": 1.5, "to_s": 2.6}, bench.videos)))


def film_blender() -> str:
    import film

    return film.BLENDER


def main() -> None:
    global CAST_RUNS
    if "--cast" in sys.argv:
        CAST_RUNS = os.path.abspath(sys.argv[sys.argv.index("--cast") + 1])
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    failed = 0
    try:
        for name, fn in tests:
            if name == "test_filmed_beside_the_clip_and_cast_in_blender" and not CAST_RUNS:
                continue
            try:
                fn()
                print(f"ok    {name[5:].replace('_', ' ')}")
            except Exception as error:  # noqa: BLE001
                failed += 1
                import traceback

                print(f"FAIL  {name[5:].replace('_', ' ')}: {type(error).__name__}: {error}")
                traceback.print_exc()
    finally:
        if Bench.made is not None:
            Bench.made.worker.close()
        if "--keep" in sys.argv:
            print(f"kept {TEMP}")
        else:
            shutil.rmtree(TEMP, ignore_errors=True)
    ran = len(tests) - (0 if CAST_RUNS else 1)
    print(f"{ran - failed} of {ran} video tests pass")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
