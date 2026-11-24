"""What a dancer's cards cost when he fills the picture, one gallery against another, turn about.

    python3 scripts/impostor/close_cost.py out.json before=http://localhost:8047/?layers=off after=http://localhost:8047/ [goes]
        [--take crew-candy-shop] [--at 18] [--looks joe,pixel-both] [--eyes crew,two,close] [--frames 120]

face_cost.py and near_cost.py time the tag field, where cards are drawn all at once and a runner is small. What a
card's own search costs shows where its pixels are many: on the watch page, with the eye 2 m and 1 m from a
dancer's head (the face judge's eyes) and through the set's crew camera. With the take stopped at --at seconds,
for each of the cast it draws --frames frames one after another, waiting for the graphics card to finish each
(one pixel is read back), and says the middle frame's milliseconds. Not the page's frame rate: every frame here is
drawn as fast as it will go, 1080 by 608. `goes` times each (3), the galleries taking turns. Prints COST and
MIDDLE lines. Needs Chrome; runs it without a window on this machine's own graphics card.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "world"))
sys.path.insert(0, HERE)
import test_walkabout  # noqa: E402  (the gallery in a headless Chrome tab)
from clear_shots import EYE  # noqa: E402  (the face judge's eyes, stood on the watch page)

TIME = """(() => {
  const v = window.forgeWatch.viewer, gl = v.renderer.getContext(), one = new Uint8Array(4), took = [];
  cancelAnimationFrame(v.frame);
  for (let i = 0; i < %d + 10; i++) {
    const began = performance.now();
    v.tick();
    cancelAnimationFrame(v.frame);
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, one);
    if (i >= 10) took.push(performance.now() - began);
  }
  took.sort((a, b) => a - b);
  return JSON.stringify({ middle: took[took.length >> 1], low: took[0], high: took[took.length - 1] });
})()"""

out = sys.argv[1]
bases = dict(a.split("=", 1) for a in sys.argv[2:4])
rounds = int(sys.argv[4]) if len(sys.argv) > 4 and not sys.argv[4].startswith("--") else 3
flag = lambda name, default: sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default
take, at, frames = flag("--take", "crew-candy-shop"), flag("--at", "18"), int(flag("--frames", "120"))
looks, eyes = flag("--looks", "joe,pixel-both").split(","), flag("--eyes", "crew,two,close").split(",")
rows = []
for r in range(rounds):
    for name, base in (list(bases.items()) if r % 2 == 0 else list(bases.items())[::-1]):
        page = test_walkabout.Page(base, gpu=True)
        try:
            page.size(1280, 900, 1, False)
            page.open("#/watch/%s" % take)
            page.until("window.forgeWatch && window.forgeWatch.state().ready && !document.querySelector('.watch-pane .status')", 120)
            page.value("window.forgeWatch.set({ playing: false, time: %s }); 1" % at)
            roles = json.loads(page.value("JSON.stringify(window.forgeWatch.state().cast.map((c) => c.role))"))
            for look in looks:
                page.value("window.forgeWatch.set({ cards: true }); window.forgeWatch.look(%s).then(() => 1)" % json.dumps(look), wait=True)
                for eye in eyes:
                    for i, role in enumerate(roles if eye != "crew" else roles[:1]):
                        page.value(EYE % {"who": i, "eye": json.dumps(eye)})
                        time.sleep(0.5)
                        got = json.loads(page.value(TIME % frames))
                        who = "all" if eye == "crew" else role
                        rows.append(dict(round=r, gallery=name, look=look, eye=eye, role=who, **got))
                        print("COST round %d %-6s %-10s %-5s %-8s: a frame in %.2f ms (%.2f to %.2f)" % (r, name, look, eye, who, got["middle"], got["low"], got["high"]), flush=True)
        finally:
            page.close()
        time.sleep(2)
middle = lambda xs: sorted(xs)[len(xs) // 2]
table = {}
for key in sorted(set((x["look"], x["eye"], x["role"]) for x in rows)):
    for name in bases:
        mine = [x["middle"] for x in rows if (x["look"], x["eye"], x["role"], x["gallery"]) == key + (name,)]
        table["%s|%s|%s|%s" % (key + (name,))] = dict(ms=round(middle(mine), 2), low=round(min(mine), 2), high=round(max(mine), 2))
        print("MIDDLE %-34s %.2f ms a frame (%.2f to %.2f)" % ("%s|%s|%s|%s" % (key + (name,)), middle(mine), min(mine), max(mine)))
json.dump(dict(about="The watch page (%s at %s s), 1080 by 608, cards, headless Chrome on this Mac's GPU, every frame drawn as fast as it will go and waited for: two galleries turn about, %d goes each; ms is the middle go's middle frame" % (take, at, rounds),
               galleries=bases, table=table, rows=rows), open(out, "w"), indent=1)
