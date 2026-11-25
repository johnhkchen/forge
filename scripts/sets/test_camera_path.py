"""Tries the moving cameras with no Blender: the easing, the keys, the shorthand, what is refused, the page's
arithmetic against Python's, and plan_shot.py carrying the cameras into plan.json.

    python3 scripts/sets/test_camera_path.py
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
import camera_path  # noqa: E402

PUSH = {"keys": [
    {"at_s": 0.0, "at": [0.0, 0.4, 8.0], "aim": [0.0, 1.0, 2.0], "lens_mm": 24},
    {"at_s": 10.0, "at": [0.0, 0.5, 5.0], "aim": [0.0, 1.3, 2.0], "lens_mm": 32},
]}


def test_easing_starts_and_stops_gently_and_passes_the_middle_halfway():
    for kind in ("in_out", "in", "out", "linear"):
        assert camera_path.ease(kind, 0.0) == 0.0 and abs(camera_path.ease(kind, 1.0) - 1.0) < 1e-12, kind
    assert abs(camera_path.ease("in_out", 0.5) - 0.5) < 1e-12
    assert camera_path.ease("in_out", 0.05) < 0.01, "in_out barely moves at first"
    assert camera_path.ease("in", 0.5) < 0.5 < camera_path.ease("out", 0.5)
    assert camera_path.ease("hold", 0.99) == 0.0 and camera_path.ease("hold", 1.0) == 1.0
    assert camera_path.ease("in_out", -1) == 0.0 and camera_path.ease("in_out", 2) == 1.0


def test_a_push_in_waits_moves_and_stays():
    cam = camera_path.expand("push", PUSH)
    assert cam["keys"][1]["ease"] == "in_out", "in_out unless told"
    first, mid, last = (camera_path.sample(cam, t) for t in (-1.0, 5.0, 99.0))
    assert first["at"] == [0.0, 0.4, 8.0] and first["lens_mm"] == 24
    assert last["at"] == [0.0, 0.5, 5.0] and last["lens_mm"] == 32
    assert abs(mid["at"][2] - 6.5) < 1e-9 and abs(mid["lens_mm"] - 28.0) < 1e-9
    early = camera_path.sample(cam, 1.0)
    assert 7.9 < early["at"][2] < 8.0, "slow at first"
    assert camera_path.tilt_deg(first) > 0 and camera_path.tilt_deg(last) > camera_path.tilt_deg(first), "it tilts up as it comes in"


def test_from_and_to_are_two_keys_the_shot_long():
    cam = camera_path.expand("push", {"from": PUSH["keys"][0], "to": PUSH["keys"][1], "ease": "linear"}, seconds=12.5)
    assert [k["at_s"] for k in cam["keys"]] == [0.0, 12.5] and cam["keys"][1]["ease"] == "linear"
    assert abs(camera_path.sample(cam, 6.25)["at"][2] - 6.5) < 1e-9


def test_a_bad_camera_is_told_what_is_wrong():
    bad = [
        ({}, "keys"),
        ({"keys": [{"at_s": 0, "at": [0, 1], "aim": [0, 1, 0], "lens_mm": 30}]}, "three numbers"),
        ({"keys": [{"at_s": 0, "at": [0, 1, 0], "aim": [0, 1, 0], "lens_mm": 30}]}, "its own lens"),
        ({"keys": [{"at_s": 0, "at": [0, 1, 5], "aim": [0, 1, 0]}]}, "lens_mm"),
        ({"keys": [PUSH["keys"][1], dict(PUSH["keys"][0], at_s=-1)]}, "comes before"),
        ({"keys": [PUSH["keys"][0], dict(PUSH["keys"][1], ease="wobble")]}, "eases"),
        ({"from": PUSH["keys"][0], "to": PUSH["keys"][1]}, "length"),
    ]
    for card, said in bad:
        try:
            camera_path.expand("x", card)
        except camera_path.PathProblem as problem:
            assert said in str(problem), (said, str(problem))
        else:
            raise AssertionError(f"taken: {card}")


def test_a_film_lasts_as_long_as_the_shot():
    times = camera_path.frames_at(14.0, 24)
    assert len(times) == 336 and times[0] == 0.0 and abs(times[1] - 1 / 24) < 1e-6 and times[-1] < 14.0, "336 pictures at 24 a second are 14.0 s"
    assert len(camera_path.frames_at(12.467, 24)) == 299 and len(camera_path.frames_at(1.0, 30)) == 30


def test_the_page_puts_the_lens_where_python_does():
    node = shutil.which("node")
    if not node:
        print("    skipped  the page's arithmetic against camera_path.py (no node here)")
        return
    cam = camera_path.expand("push", {"keys": PUSH["keys"] + [{"at_s": 14.0, "at": [1.0, 0.6, 4.0], "aim": [0.0, 1.2, 2.0], "lens_mm": 40, "ease": "out"},
                                                             {"at_s": 15.0, "at": [2.0, 0.6, 4.0], "aim": [0.0, 1.2, 2.0], "lens_mm": 40, "ease": "hold"}]})
    times = [-1.0, 0.0, 0.3, 2.5, 5.0, 9.99, 10.0, 11.0, 13.9, 14.5, 14.999, 15.0, 30.0]
    script = (f"import {{ sample, ease, fovOf }} from {json.dumps('file://' + os.path.join(REPO, 'gallery', 'camera-path.js'))};"
              "let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{const {cam,times}=JSON.parse(d);"
              "console.log(JSON.stringify({s:times.map(t=>sample(cam,t)),fov:fovOf(35)}));});")
    out = subprocess.run([node, "--input-type=module", "-e", script], input=json.dumps({"cam": cam, "times": times}), capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-800:]
    got = json.loads(out.stdout)
    for t, js in zip(times, got["s"]):
        py = camera_path.sample(cam, t)
        assert max(abs(a - b) for a, b in zip(py["at"] + py["aim"] + [py["lens_mm"]], js["at"] + js["aim"] + [js["lens_mm"]])) < 1e-12, (t, py, js)
    # The page's lens is the set cameras' lens: a 36 mm wide picture, 16 by 9.
    assert abs(got["fov"] - math.degrees(2 * math.atan(36 / (16 / 9) / 2 / 35))) < 1e-9


def test_a_shot_brief_carries_its_moving_cameras_into_the_plan():
    folder = tempfile.mkdtemp(prefix="camera-path-")
    try:
        shot = {"title": "stand", "start_pose": "stand", "start_mark": "centre", "path": [], "props": [], "camera": [],
                "beats": [{"name": "Stands", "seconds": 2.0, "source": "poses", "at": "centre",
                           "moves": [{"pose": "stand", "at_m": 0.0, "side_m": 0.0, "facing_deg": 0.0, "speed_mps": 0.0, "tokens": 9, "early_frames": 0, "pins": [], "hold_pins_frames": 0}]}]}
        with open(os.path.join(folder, "shotlist.json"), "w") as f:
            json.dump(shot, f)
        brief = os.path.join(folder, "brief.json")
        with open(brief, "w") as f:
            json.dump({"name": "t", "set": "studio", "moving_cameras": {"push": {"from": PUSH["keys"][0], "to": PUSH["keys"][1]}}}, f)
        done = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "motion", "plan_shot.py"), folder, "--brief", brief], capture_output=True, text=True)
        assert done.returncode == 0, done.stderr[-800:]
        with open(os.path.join(folder, "plan.json")) as f:
            plan = json.load(f)
        keys = plan["moving_cameras"]["push"]["keys"]
        assert len(keys) == 2 and keys[1]["at_s"] == plan["seconds"] and plan["standing_set"] == "studio", keys
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def main() -> None:
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name[5:].replace('_', ' ')}")
        except Exception as error:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {name[5:].replace('_', ' ')}: {type(error).__name__}: {error}")
    print(f"{len(tests) - failed} of {len(tests)} moving-camera tests pass")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
