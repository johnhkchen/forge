"""Tries the Omni packing, sending and drift check with no network, no GPU and no Blender.

    python3 scripts/video/test_omni.py

What it shows:
  routes      each route sends what it should, in the order it should, with the duration and size asked for;
              edit takes our film and two pictures, frames two pictures and at most 10 s, generate six pictures
  limits      too many pictures, or too long a film, is refused before anything is sent
  cost        14 s of 720p out is about $0.97, and the estimate says which part is known and which is a guess
  no go       without `go` nothing touches the network, whether or not there is a key
  answers     the film is found in an answer wherever it is (inline or by address), and the copy kept on disk
              holds no base64
  sound       what comes back is kept with no sound
  drift       a motion against itself is 0 cm and in step; shifted by 4 frames it is found 4 frames late
  stretch     the picker's best 10 to 15 s stay clear of a seam and end on a held pose
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "motion"))
import omni  # noqa: E402
from soma import Skeleton, qaxis, qmul  # noqa: E402

TEMP = tempfile.mkdtemp(prefix="omni-test-")
SK = Skeleton.load()


def fake_export(seconds: float = 14.0) -> str:
    out = os.path.join(TEMP, "export-%d" % int(seconds * 100))
    if os.path.exists(out):
        return out
    for rel in ["source.mp4", "first.png", "last.png", "refs/character-sheet.png", "refs/set.png"] + ["refs-6/%d-x.png" % n for n in range(1, 7)]:
        os.makedirs(os.path.dirname(os.path.join(out, rel)), exist_ok=True)
        with open(os.path.join(out, rel), "wb") as f:
            f.write(b"\0" * 1000)
    for name, text in (("prompt.txt", "Restyle it. Keep everything else the same."), ("prompt-frames.txt", "Between the two."), ("prompt-generate.txt", "A new one.")):
        with open(os.path.join(out, name), "w") as f:
            f.write(text + "\n")
    omni.write(os.path.join(out, "manifest.json"), {"name": "no-such-restyle", "film_seconds": seconds, "model": "gemini-omni-1.2-flash", "resolution": "720p",
                                                    "refs": {"edit": ["refs/character-sheet.png", "refs/set.png"], "six": ["%d-x.png" % n for n in range(1, 7)], "first": "first.png", "last": "last.png"}})
    return out


def test_each_route_sends_what_it_should():
    export = fake_export()
    edit = omni.plan_request(export, "edit")
    assert [u["file"] for u in edit["uploads"]] == ["source.mp4", "refs/character-sheet.png", "refs/set.png"]
    assert [p["type"] for p in edit["body"]["input"]] == ["video", "image", "image", "text"]
    assert edit["body"]["input"][-1]["text"].endswith("Keep everything else the same.")
    rf = edit["body"]["response_format"]
    assert rf == {"type": "video", "duration": "14s", "resolution": "720p", "aspect_ratio": "16:9", "delivery": "uri"}, rf
    assert edit["body"]["model"] == "gemini-omni-1.2-flash"
    frames = omni.plan_request(export, "frames")
    assert [u["file"] for u in frames["uploads"]] == ["first.png", "last.png"] and frames["body"]["response_format"]["duration"] == "10s"
    generate = omni.plan_request(export, "generate")
    assert len(generate["uploads"]) == 6 and all(p["type"] == "image" for p in generate["body"]["input"][:-1]) and generate["seconds"] == 14


def test_too_many_pictures_or_too_long_is_refused():
    export = fake_export()
    card = omni.read(os.path.join(export, "manifest.json"))
    card["refs"]["edit"].append("first.png")
    omni.write(os.path.join(export, "manifest.json"), card)
    try:
        omni.plan_request(export, "edit")
        raise AssertionError("three pictures went with an edit")
    except omni.Stop as stop:
        assert "at most 2" in str(stop)
    finally:
        card["refs"]["edit"].pop()
        omni.write(os.path.join(export, "manifest.json"), card)
    long = fake_export(16.0)
    for route in ("edit", "generate"):
        try:
            omni.plan_request(long, route)
            raise AssertionError(f"16 s went as {route}")
        except omni.Stop as stop:
            assert "3 to 15" in str(stop)
    try:
        omni.plan_request(export, "sideways")
        raise AssertionError("a made-up route went")
    except omni.Stop:
        pass


def test_the_cost_is_mostly_the_film_out():
    cost = omni.estimate(omni.plan_request(fake_export(), "edit"))
    assert cost["video_out_tokens"] == 14 * 5792 and abs(cost["video_out_usd"] - 0.973) < 0.001, cost
    assert 0.95 < cost["total_usd"] < 1.05 and cost["per_second_usd"] == 0.0695, cost
    said = omni.describe(omni.plan_request(fake_export(), "edit"), cost, "no GEMINI_API_KEY ...")
    assert "x-goog-api-key" in said and "about $" in said and "<Files API address of source.mp4>" in said


def test_without_go_nothing_touches_the_network():
    def no(*a, **k):
        raise AssertionError("the network was touched")

    was = omni.http, omni.upload
    omni.http, omni.upload = no, no
    saved = os.environ.get("GEMINI_API_KEY")
    try:
        for key in ("pretend-key", None):
            if key:
                os.environ["GEMINI_API_KEY"] = key
            else:
                os.environ.pop("GEMINI_API_KEY", None)
            got = omni.send(fake_export(), "edit", go=False)
            assert got["sent"] is False and got["cost"]["total_usd"] > 0
    finally:
        omni.http, omni.upload = was
        if saved is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = saved


def test_the_film_is_found_wherever_the_answer_puts_it_and_kept_without_base64():
    inline = {"steps": [{"type": "user_input"}, {"type": "model_output", "content": [{"type": "video", "mime_type": "video/mp4", "data": "QUFB" * 100}]}]}
    by_uri = {"output_video": {"uri": "https://generativelanguage.googleapis.com/v1beta/files/abc-123:download?alt=media"}}
    assert omni.find_video(inline)["data"].startswith("QUFB") and omni.find_video(by_uri)["uri"].endswith("alt=media")
    assert omni.find_video({"steps": []}) == {}
    kept = json.dumps(omni.redact(inline))
    assert "QUFBQUFB" not in kept and "characters of base64" in kept


def test_what_comes_back_has_no_sound():
    noisy, quiet = os.path.join(TEMP, "noisy.mp4"), os.path.join(TEMP, "quiet.mp4")
    subprocess.run([omni.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x36:d=1", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", noisy], check=True)
    omni.silent(noisy, quiet)
    streams = subprocess.run([omni.clip_file.FFPROBE, "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", quiet], capture_output=True, text=True).stdout.split()
    assert streams == ["video"], streams


def dance(frames: int, lag: int = 0) -> dict:
    """A made-up dance on the SOMA skeleton: arms and a knee swinging at their own beats, the whole body turning."""
    rows, roots = [], []
    swing = {"LeftArm": (0.9, 50.0), "RightArm": (1.3, 40.0), "LeftShin": (0.7, 35.0), "Spine2": (0.5, 15.0)}
    for f in range(frames):
        t = (f - lag) / 30.0
        row = []
        for j, name in enumerate(SK.joints):
            q = SK.rest_rot[j]
            if name in swing:
                hz, deg = swing[name]
                q = qmul(q, qaxis((1.0, 0.0, 0.0), deg * math.sin(2 * math.pi * hz * t)))
            if j == 0:
                q = qmul(qaxis((0.0, 1.0, 0.0), 20.0 * t), q)
            row += list(q)
        rows.append(row)
        roots.append([0.3 * t, SK.rest_world_pos[0][1], 0.0])
    return {"fps": 30, "joints": list(SK.joints), "root": roots, "rotations": rows}


def test_the_drift_check_finds_how_far_and_how_late():
    ours = dance(150)
    same = omni.compare(ours, dance(150), SK)
    assert same["best_lag_frames"] == 0 and same["mean_cm"] < 0.05, same
    late = omni.compare(ours, dance(150, lag=4), SK)
    assert late["best_lag_frames"] == 4 and late["mean_cm"] < 0.5 and late["best_lag_ms"] == 133, (late["best_lag_frames"], late["mean_cm"])
    assert all(w["best_lag_frames"] == 4 for w in late["timing_windows"]) and late["timing_drift_frames"] == 0
    assert set(late["joints"]) == set(SK.joints) and "p95_cm" in late["joints"]["LeftHand"]


def test_the_stretch_picker_keeps_clear_of_a_seam_and_ends_on_a_still_frame():
    import pick_stretch

    shot = os.path.join(TEMP, "shot")
    os.makedirs(shot, exist_ok=True)
    motion = dance(1500)
    for f in range(1500):  # a held pose every 4 s: the arms stop for a third of a second
        if f % 120 < 10:
            motion["rotations"][f] = list(motion["rotations"][f - f % 120])
            motion["root"][f] = list(motion["root"][f - f % 120])
    omni.write(os.path.join(shot, "motion.json"), motion)
    omni.write(os.path.join(shot, "checks.json"), {"seams": {"seams": [{"joins_at_frames": [700, 708]}]}})
    got = pick_stretch.pick(shot, 10.0, 15.0, keep_off=1.5, top=3, sk=SK)
    assert got["seams"] == [700, 708] and got["best"], got
    for m in got["best"]:
        assert 10.0 - 0.05 <= m["seconds"] <= 15.0 and m["seam_s"] >= 1.5, m
        assert not m["first_frame"] <= 700 <= m["last_frame"] and not m["first_frame"] <= 708 <= m["last_frame"], m
        assert m["still_ends_m_per_s"] < 0.5, m


def main() -> None:
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    failed = 0
    try:
        for name, fn in tests:
            try:
                fn()
                print(f"ok    {name[5:].replace('_', ' ')}")
            except Exception as error:  # noqa: BLE001
                failed += 1
                print(f"FAIL  {name[5:].replace('_', ' ')}: {type(error).__name__}: {error}")
    finally:
        shutil.rmtree(TEMP, ignore_errors=True)
    print(f"{len(tests) - failed} of {len(tests)} omni tests pass")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
