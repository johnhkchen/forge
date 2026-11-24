"""A film of a take as the watch page draws it, a picture at a time, taken by a headless Chrome.

    python3 scripts/video/watch_film.py <out folder> [--base http://localhost:8052/] [--take groove-flamenco]
        [--eye push_in] [--look joe] [--model midpoly] [--pass ""|plate|mask] [--fps 24] [--size 1280x720]
        [--only 0,150,328]

The gallery must be running on that port. The looks (bold ink above all) are
drawn by the page itself (gallery/looks.js), so the truest film of a look is
the page's own pictures. With the take stopped, the picture fixed at --size
(one picture pixel a screen pixel) and the eye on --eye (a camera of the set,
or one of the shot's own moving cameras), each moment of a film at --fps is
drawn and kept: <out>/0000.png, 0001.png, ... and frames.json.

    --pass plate   the set alone, nobody on it
    --pass mask    the cast alone, white on black

ffmpeg makes the pictures a film (scripts/video/omni.py pack does). Prints
FILM lines.
"""

import base64
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts", "world"))
sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
import camera_path  # noqa: E402
import test_walkabout  # noqa: E402  (the gallery in a headless Chrome tab)

BOX = """(() => {
  const c = window.forgeWatch.viewer.renderer.domElement;
  window.scrollTo(0, 0);
  const b = c.getBoundingClientRect();
  return JSON.stringify([b.left + window.scrollX, b.top + window.scrollY, b.width, b.height]);
})()"""


def settle(page):
    page.value("new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(1))))", wait=True)


def main():
    args = sys.argv[1:]
    flag = lambda name, default: args[args.index(name) + 1] if name in args else default  # noqa: E731
    out = os.path.abspath(args[0])
    base, take, eye, look = flag("--base", "http://localhost:8052/"), flag("--take", "groove-flamenco"), flag("--eye", "push_in"), flag("--look", "joe")
    model, kind, fps = flag("--model", "midpoly"), flag("--pass", ""), float(flag("--fps", "24"))
    wide, tall = (int(v) for v in flag("--size", "1280x720").split("x"))
    only = [int(v) for v in flag("--only", "").split(",") if v]
    os.makedirs(out, exist_ok=True)
    page = test_walkabout.Page(base, gpu=True)
    try:
        page.size(wide + 80, tall + 500, 1, False)
        page.open("#/watch/%s" % take)
        page.until("window.forgeWatch && window.forgeWatch.state().ready && !document.querySelector('.watch-pane .status')", 180)
        state = json.loads(page.value("JSON.stringify(window.forgeWatch.state())"))
        if state.get("model") != model:
            # the model is chosen as the cast is brought on: press its chip, and wait for the cast again
            page.value("[...document.querySelectorAll('.versions[aria-label=Model] button')].find((b) => b.textContent === %s).click(); 1" % json.dumps({"midpoly": "Mid poly", "lowpoly": "Low poly"}[model]))
            time.sleep(1.0)
            page.until("window.forgeWatch && window.forgeWatch.state().ready && window.forgeWatch.state().model === %s && !document.querySelector('.watch-pane .status')" % json.dumps(model), 180)
        page.value("window.forgeWatch.set({ playing: false, cards: false, pass: %s }); 1" % json.dumps(kind))
        page.value("window.forgeWatch.look(%s).then(() => 1)" % json.dumps(look), wait=True)
        page.value("window.forgeWatch.eye(%s); 1" % json.dumps(eye))
        page.value("window.forgeWatch.film(%d, %d)" % (wide, tall))
        state = json.loads(page.value("JSON.stringify(window.forgeWatch.state())"))
        if state["eye"] != eye:
            sys.exit("the take has no camera called %s" % eye)
        times = camera_path.frames_at(state["length"], fps)
        settle(page)
        box = json.loads(page.value(BOX))
        if round(box[2]) != wide or round(box[3]) != tall:
            sys.exit("the picture came out %dx%d, not %dx%d" % (box[2], box[3], wide, tall))
        clip = {"x": box[0], "y": box[1], "width": wide, "height": tall, "scale": 1}
        began = time.time()
        for n in (only or range(len(times))):
            page.value("window.forgeWatch.frame(%r)" % times[n])
            settle(page)
            got = page.tab.ask("Page.captureScreenshot", format="png", clip=clip, captureBeyondViewport=True)
            with open(os.path.join(out, "%04d.png" % n), "wb") as f:
                f.write(base64.b64decode(got["data"]))
            if n % 48 == 0:
                print("FILM %s %s frame %d of %d (%.2f s)" % (kind or look, eye, n, len(times) - 1, times[n]), flush=True)
        said = page.value("window.forgeWatch.state().error")
        if said:
            print("FILM the page said: %s" % said)
        with open(os.path.join(out, "frames.json"), "w") as f:
            json.dump({"take": take, "camera": eye, "look": look, "model": model, "pass": kind or "look", "fps": fps, "size": [wide, tall], "frames": len(times),
                       "seconds": state["length"], "drawn_by": "the gallery's watch page (gallery/watch.js, looks.js) in a headless Chrome"}, f, indent=1)
        print("FILM done: %d pictures in %.0f s -> %s" % (len(only or times), time.time() - began, out))
    finally:
        page.close()


main()
