"""Pictures of a Marble place in the gallery, and how fast it draws, taken by a headless Chrome on this Mac's own GPU.

    python3 scripts/sets/marble_shots.py <set> [--port 8028] [--out evidence/marble] [--camera bar] [--seconds 6]
    python3 scripts/sets/marble_shots.py <set> --one "<what follows #/marble/<set>>" <out.png> [--size 1280x720]
    python3 scripts/sets/marble_shots.py <set> --views <diorama folder>/views.json

The gallery must be running, and able to find the world's own files
(`python3 scripts/gallery.py --marble <main checkout>/world/marble`). The first
form opens the place through one of the set's cameras at each sharpness (100
thousand dots, half a million, every dot), waits until the page says the room
has arrived, lets it draw for a few seconds, and saves

    <out>/<set>-<camera>-<detail>.png     only the picture, 1280 x 720: the view Blender's still is set beside
    <out>/<set>-mesh.png                  the same view of the painted mesh
    <out>/<set>-phone.png                 the whole page at phone width
    <out>/<set>-speed.json                pictures a second at each sharpness, and what was fetched

A headless Chrome draws at most 60 pictures a second, so 60 means "at least
60"; how long one picture really takes is timed too, drawn back to back, at
1280 x 720 and at twice that each way. The second form takes one picture of any view of the page (the pictures
for the TRELLIS round trip are made this way: scripts/sets/marble_diorama.py).
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts", "world"))
import test_walkabout  # noqa: E402  (the gallery in a headless Chrome tab)

DETAILS = ("100k", "500k", "full_res")


def settle(page, seconds=240):
    began = time.time()
    while time.time() - began < seconds:
        said = json.loads(page.value("JSON.stringify(window.forgeMarble || null)") or "null")
        if said and (said.get("settled") or said.get("error")):
            return said
        time.sleep(0.25)
    raise AssertionError("the page did not say the room had arrived in %d s" % seconds)


def one(page, name, rest, path, size=(1280, 720), ratio=1, phone=False, wait=2.5):
    """One picture of #/marble/<name><rest>. Returns what the page said once the room had arrived."""
    page.size(size[0], size[1], ratio, phone)
    page.open("#/marble/%s%s" % (name, rest))
    said = settle(page)
    if said.get("error"):
        raise AssertionError("the page could not show the room: %s" % said["error"])
    time.sleep(wait)
    page.picture(path)
    return said


def main():
    args = sys.argv[1:]
    opt = lambda flag, default: args[args.index(flag) + 1] if flag in args else default
    name = args[0]
    base = "http://localhost:%s/" % opt("--port", "8028")
    page = test_walkabout.Page(base, gpu=True)
    try:
        if "--views" in args:  # every view of a diorama (scripts/sets/marble_diorama.py wrote the list)
            listed = os.path.abspath(args[args.index("--views") + 1])
            with open(listed) as f:
                views = json.load(f)["views"]
            for view, card in views.items():
                path = os.path.join(os.path.dirname(listed), card["splats"])
                one(page, name, card["open"], path, (card["size"], card["size"]), wait=4.0)
                print("SHOT %s" % os.path.relpath(path, REPO))
            return
        if "--one" in args:
            rest, path = args[args.index("--one") + 1], os.path.abspath(args[args.index("--one") + 2])
            wide, tall = [int(v) for v in opt("--size", "1280x720").split("x")]
            one(page, name, rest, path, (wide, tall))
            print("SHOT %s" % path)
            return
        out, camera, seconds = os.path.abspath(opt("--out", os.path.join(REPO, "evidence", "marble"))), opt("--camera", "bar"), float(opt("--seconds", "6"))
        os.makedirs(out, exist_ok=True)
        speed = {}
        for detail in DETAILS:
            path = os.path.join(out, "%s-%s-%s.png" % (name, camera, detail))
            said = one(page, name, "/%s?detail=%s&bare=1" % (camera, detail), path, wait=1.0)
            time.sleep(seconds)  # the count is of the last few seconds, after the room has arrived
            now = json.loads(page.value("JSON.stringify(window.forgeMarble)"))
            page.picture(path)
            each = page.value("window.forgeMarble.bench(40)")
            page.size(1280, 720, 2, False)  # the same picture on a screen with twice the dots each way, as this Mac's is
            page.value("window.dispatchEvent(new Event('resize'))")
            time.sleep(1.0)
            sharp = page.value("window.forgeMarble.bench(40)")
            across = page.value("document.querySelector('.marble-stage canvas').width")
            assert across == 2560, "the picture is %s dots across, not 2560" % across
            speed[detail] = {"pictures_a_second": now.get("fps"), "ms_a_picture": round(each, 2), "could_draw_a_second": round(1000.0 / each), "ms_a_picture_at_2560x1440": round(sharp, 2),
                             "could_draw_a_second_at_2560x1440": round(1000.0 / sharp), "dots": now.get("splats"), "mb": round((now.get("bytes") or 0) / 1e6, 1), "arrived_in_s": round(said.get("seconds") or 0, 1)}
            print("SHOT %s: %s dots, %.1f MB, there in %.1f s, %s pictures a second on the page; one takes %.1f ms (%.1f ms at 2560 x 1440)"
                  % (os.path.relpath(path, REPO), now.get("splats"), speed[detail]["mb"], speed[detail]["arrived_in_s"], now.get("fps"), each, sharp))
        path = os.path.join(out, "%s-mesh.png" % name)
        one(page, name, "/%s?show=mesh&bare=1" % camera, path)
        print("SHOT %s" % os.path.relpath(path, REPO))
        path = os.path.join(out, "%s-phone.png" % name)
        said = one(page, name, "/%s" % camera, path, (430, 932), 2, True, wait=4.0)
        now = json.loads(page.value("JSON.stringify(window.forgeMarble)"))
        speed["phone_size_page"] = {"detail": now.get("detail"), "pictures_a_second": now.get("fps")}
        print("SHOT %s: the page at phone size, %s, %s pictures a second" % (os.path.relpath(path, REPO), now.get("detail"), now.get("fps")))
        with open(os.path.join(out, "%s-speed.json" % name), "w") as f:
            json.dump({"about": "How fast the Marble page draws in a headless Chrome on this Mac's GPU, 1280 x 720, through the %s camera with %s in it. A headless Chrome stops at 60." % (camera, "Roosevelt"),
                       "who": now.get("who"), "views": speed}, f, indent=1)
            f.write("\n")
    finally:
        page.close()


if __name__ == "__main__":
    main()
