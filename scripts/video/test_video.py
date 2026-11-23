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
