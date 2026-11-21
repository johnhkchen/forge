"""Tries walking around the world, in a headless Chrome at phone size. No Blender, no model.

    python3 scripts/world/test_walkabout.py [RUNS_DIR] [--port 8028] [--shots DIR] [--gpu]

It starts a gallery of its own on a free port (or uses the one on --port), opens
`#/world/<epoch>/walk`, and steers Roosevelt the way a visitor would: real key
presses, a real finger on the thumb stick, a real tap on "Stop walking". The
page tells it where he is (`window.forgeWalk`). What it shows:

  light    the world view fetches nothing of the walk until walking is asked for; then one script, one style
           sheet and the walker's two files, under a megabyte
  start    the link drops Roosevelt where he lives, on Theodore's grass, with his still figure put away;
           everyone with a walk and a run is in the picker, and only Roosevelt can be picked
  feet     W walks him, Shift runs him, and the body goes over the ground as fast as the clip says its feet
           do (within 10%), so the foot that is down hardly slides; standing still is a pose, not the T
  solid    he can't walk through a block (the troll's den), another toon (Lincoln) or off the world; a
           stage is stepped up onto
  places   in a place its card shows, with who is there and "Open this place"; by the stall, the kettle's
           line from the story; by a toon, a hello
  phone    the thumb stick walks him and, pushed to its edge, runs him; a tap on the ground walks him there
  stop     "Stop walking" puts everything back

--shots DIR also saves pictures, phone and desktop: walking on the grass, and at the settlement's stall.
RUNS_DIR (default: runs) must hold Roosevelt's run. `run(runs)` hands the same checks to scripts/test_tools.py.
"""

import base64
import glob
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import shots  # noqa: E402  (Chrome over its debugging socket, in plain Python)

PHONE, DESKTOP = (430, 932, 2, True), (1280, 900, 1, False)  # wide, tall, pixels per px, a phone?
EXTRA_MB = 1.0     # what starting a walk may fetch
WITHIN = 0.10      # body speed against clip speed
SLIDE = 0.12       # how far the planted foot may slide, as a share of the ground covered
KEYS = {"w": ("KeyW", 87), "a": ("KeyA", 65), "s": ("KeyS", 83), "d": ("KeyD", 68), "shift": ("ShiftLeft", 16)}


def check(label, ok, detail=""):
    print("    %s  %s%s" % ("ok  " if ok else "FAIL", label, ("  (%s)" % (str(detail)[:600],)) if detail and not ok else ""))
    if not ok:
        raise AssertionError(label)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def in_world(world, place, x, z):
    """A point of a place's set, in world metres (the arithmetic of world.py and the world view: turn, then slide)."""
    card = world["places"][place]
    with open(os.path.join(REPO, "sets", card["set"], "set.json")) as f:
        st = json.load(f)
    turn = math.radians(card.get("facing_deg", 0.0) - st["frame"].get("front_deg", 0.0))
    ox, _, oz = st["frame"]["origin"]
    x, z = x - ox, z - oz
    return [card["at"][0] + x * math.cos(turn) + z * math.sin(turn), card["at"][1] - x * math.sin(turn) + z * math.cos(turn)], st


class Page:
    """The gallery in a headless Chrome tab."""

    def __init__(self, base, gpu=False):
        self.base = base
        self.debug = free_port()
        self.profile = tempfile.mkdtemp(prefix="forge-walk-")
        how = ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"] if gpu else ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"]
        # A page nobody is looking at stops drawing frames (with the Mac's screen asleep, a headless one counts): keep it awake.
        awake = ["--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding", "--disable-background-timer-throttling", "--disable-features=CalculateNativeWinOcclusion"]
        self.chrome = subprocess.Popen([shots.CHROME, "--headless=new", "--hide-scrollbars", "--remote-debugging-port=%d" % self.debug, "--user-data-dir=" + self.profile] + how + awake + ["about:blank"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tabs = None
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % self.debug))
                break
            except OSError:
                time.sleep(0.2)
        self.tab = shots.Tab(next(t for t in tabs if t.get("type") == "page")["webSocketDebuggerUrl"])
        self.tab.sock.settimeout(90)  # a page that stops answering is a failure, not a wait
        self.tab.ask("Emulation.setFocusEmulationEnabled", enabled=True)

    def size(self, wide, tall, ratio, phone):
        self.tab.ask("Emulation.setDeviceMetricsOverride", width=wide, height=tall, deviceScaleFactor=ratio, mobile=phone)
        self.tab.ask("Emulation.setTouchEmulationEnabled", enabled=phone, maxTouchPoints=5 if phone else 1)

    def open(self, hash_):
        self.tab.ask("Page.navigate", url="about:blank")
        self.tab.ask("Page.navigate", url=self.base + hash_)

    def value(self, expression, wait=False):
        reply = self.tab.ask("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=wait)
        if reply.get("exceptionDetails"):
            raise AssertionError("the page threw: %s" % json.dumps(reply["exceptionDetails"])[:500])
        return (reply.get("result") or {}).get("value")

    def until(self, expression, seconds=60):
        began = time.time()
        while time.time() - began < seconds:
            got = self.value(expression)
            if got:
                return got
            time.sleep(0.2)
        raise AssertionError("waited %d s for: %s" % (seconds, expression))

    def state(self):
        return json.loads(self.value("JSON.stringify(window.forgeWalk.state())"))

    def record(self, seconds):
        return json.loads(self.value("window.forgeWalk.record(%s).then(JSON.stringify)" % seconds, wait=True))

    def key(self, name, down):
        code, number = KEYS[name]
        self.tab.ask("Input.dispatchKeyEvent", type="rawKeyDown" if down else "keyUp", code=code, key="Shift" if name == "shift" else name, windowsVirtualKeyCode=number, nativeVirtualKeyCode=number)

    def touch(self, kind, x=None, y=None):
        self.tab.ask("Input.dispatchTouchEvent", type=kind, touchPoints=[{"x": x, "y": y}] if x is not None else [])

    def box(self, selector):
        return json.loads(self.value("(() => { const b = document.querySelector(%s).getBoundingClientRect(); return JSON.stringify([b.left, b.top, b.width, b.height]); })()" % json.dumps(selector)))

    def picture(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(base64.b64decode(self.tab.ask("Page.captureScreenshot", format="png")["data"]))

    def close(self):
        self.chrome.terminate()


def start_walk(page, epoch):
    page.open("#/world/%s/walk" % epoch)
    page.until("window.forgeWalk && window.forgeWalk.ready")
    time.sleep(0.4)
    return page.state()


def walk_checks(page, world, runs):
    epoch = world["name"]
    me = next(t for t in world["toons"] if t["toon"] == "roosevelt")

    print("  light: the world view fetches nothing of the walk until it is asked for")
    page.open("#/world/%s" % epoch)
    page.until("window.forgeWorld && window.forgeWorld.settled")
    fetched = json.loads(page.value("JSON.stringify(performance.getEntriesByType('resource').map((r) => r.name))"))
    early = [u for u in fetched if "walkabout" in u or "-walk.glb" in u or "-run.glb" in u]
    check("the world view alone fetches no walk script, style sheet or walking toon", not early, early)
    check("it offers a \"Walk around\" button", page.value("[...document.querySelectorAll('.walk-bar button')].map((b) => b.textContent).join()") == "Walk around")
    before = json.loads(page.value("JSON.stringify(window.forgeWorld)"))

    print("  start: the link drops Roosevelt on Theodore's grass")
    said = start_walk(page, epoch)
    home, _ = in_world(world, me["place"], *json.load(open(os.path.join(REPO, "sets", world["places"][me["place"]]["set"], "set.json")))["marks"][me["mark"]]["at"])
    check("he stands on his own mark on the grass (%.1f, %.1f)" % tuple(home), said["who"] == "roosevelt" and math.hypot(said["x"] - home[0], said["z"] - home[1]) < 0.05, said)
    extra = said["extra"]
    check("walking fetched %d more files, %.2f MB (at most %.1f MB)" % (extra["files"], extra["bytes"] / 1e6, EXTRA_MB), extra["files"] == 4 and 1e5 < extra["bytes"] <= EXTRA_MB * 1e6, extra)
    have = sorted(t["toon"] for t in world["toons"] if all(glob.glob(os.path.join(runs, "*-" + t["run"], "profiles", "lowpoly-%s.glb" % clip)) for clip in ("walk", "run")))
    check("the picker lists everyone with a walk and a run (%d toons), and only Roosevelt can be picked today" % len(have),
          sorted(a["toon"] for a in said["cast"]) == have and [a["toon"] for a in said["cast"] if a["ready"]] == ["roosevelt"], said["cast"])
    check("the page says who is walking, and how to stop", page.value("document.querySelector('.walk-who').textContent").startswith("Walking as: Roosevelt") and page.value("document.querySelector('.walk-stop').textContent") == "Stop walking")
    check("his still figure is put away while he is out walking", page.value("window.forgeWalk.stillFigureShown()") is False)
    check("the place card says where he is: %s" % world["places"][me["place"]]["label"], page.until("document.querySelector('.walk-card h3')?.textContent", 10) == world["places"][me["place"]]["label"])
    with open(os.path.join(glob.glob(os.path.join(runs, "*-" + me["run"]))[-1], "profiles", "lowpoly-walk.json")) as f:
        walk_speed = json.load(f)["walk"]["gait"]["speed_m_s"]
    with open(os.path.join(glob.glob(os.path.join(runs, "*-" + me["run"]))[-1], "profiles", "lowpoly-run.json")) as f:
        run_speed = json.load(f)["run"]["speed_m_s"]
    check("the speeds are the clips' own: walk %.2f m/s, run %.2f m/s" % (walk_speed, run_speed), abs(said["walk_speed"] - walk_speed) < 0.01 and abs(said["run_speed"] - run_speed) < 0.01, said)

    print("  feet: the body goes as fast as the clip's feet do")
    still = page.record(1.0)
    check("standing still he does not move, and is in the idle pose", still["path_m"] < 0.01 and still["gait"] == "idle", still)
    pose = json.loads(page.value("JSON.stringify(window.forgeWalk.pose())"))
    check("that pose is not the T: his hands hang %.2f m below his shoulders, %.2f m out from them" % (pose["hand_below_shoulder_m"], pose["hand_out_from_shoulder_m"]),
          pose["hand_below_shoulder_m"] > 0.35 and pose["hand_out_from_shoulder_m"] < 0.35 and pose["feet_off_floor_m"] < 0.12, pose)
    page.key("w", True)
    time.sleep(0.8)
    walking = page.record(3.0)
    page.key("w", False)
    off = abs(walking["speed_m_s"] - walk_speed) / walk_speed
    check("W walks him: %.2f m in %.1f s, %.2f m/s against the clip's %.2f (%.0f%% off; at most %d%%)" % (walking["path_m"], walking["seconds"], walking["speed_m_s"], walk_speed, off * 100, WITHIN * 100),
          walking["gait"] == "walk" and off <= WITHIN and abs(walking["clip_speed_m_s"] - walking["speed_m_s"]) / walk_speed <= WITHIN, walking)
    check("the foot that is down slid %.0f cm over %.1f m of ground (%.0f%%; at most %d%%)" % (walking["foot_slid_m"] * 100, walking["path_m"], 100 * walking["foot_slid_m"] / walking["path_m"], SLIDE * 100),
          walking["foot_slid_m"] / walking["path_m"] <= SLIDE, walking)
    time.sleep(0.6)
    page.key("shift", True)
    page.key("w", True)
    time.sleep(1.0)
    running = page.record(2.5)
    page.key("w", False)
    page.key("shift", False)
    off = abs(running["speed_m_s"] - run_speed) / run_speed
    check("Shift runs him: %.2f m/s against the clip's %.2f (%.0f%% off)" % (running["speed_m_s"], run_speed, off * 100), running["gait"] == "run" and off <= WITHIN, running)
    time.sleep(0.8)
    check("letting go, he comes to a stand", page.state()["gait"] == "idle" and page.state()["speed"] < 0.01, page.state())

    print("  solid: blocks, toons and the edge of the world")
    place, name = "settlement", "troll den"
    _, st = in_world(world, place, 0, 0)
    den = next(b for b in st["blocks"] if b["name"] == name)
    front, _ = in_world(world, place, den["center"][0], den["center"][2] + den["size"][2] / 2)   # the middle of its front face
    start, _ = in_world(world, place, den["center"][0], den["center"][2] + den["size"][2] / 2 + 2.5)
    toward = math.degrees(math.atan2(front[0] - start[0], front[1] - start[1]))
    page.value("window.forgeWalk.put(%f, %f, %f)" % (start[0], start[1], toward))
    page.key("w", True)
    blocked = page.record(4.0)   # 4 s at a walk is more than 5 m: he would be well inside it
    page.key("w", False)
    gap = math.hypot(blocked["x"] - front[0], blocked["z"] - front[1])
    check("walking at the %s for 4 s he stops at its wall: %.2f m from it, his middle never inside" % (name, gap), 0.28 <= gap <= 0.4 and blocked["touching"] == name, blocked)
    check("and stands there, not treading on the spot", page.state()["gait"] == "idle", page.state())
    him = next(t for t in world["toons"] if t["toon"] == "lincoln")
    with open(os.path.join(REPO, "sets", world["places"][him["place"]]["set"], "set.json")) as f:
        mark = json.load(f)["marks"][him["mark"]]
    lincoln, _ = in_world(world, him["place"], *mark["at"])
    start, _ = in_world(world, him["place"], mark["at"][0], mark["at"][1] + 2.4)
    toward = math.degrees(math.atan2(lincoln[0] - start[0], lincoln[1] - start[1]))
    page.value("window.forgeWalk.put(%f, %f, %f)" % (start[0], start[1], toward))
    page.key("w", True)
    met = page.record(3.5)
    page.key("w", False)
    apart = math.hypot(met["x"] - lincoln[0], met["z"] - lincoln[1])
    said = page.state()
    check("walking at Lincoln he is stopped %.2f m from him" % apart, 0.55 <= apart <= 1.2 and met["touching"] == him["name"], met)
    upstairs = [name for name, card in world["places"].items() if card.get("inside") == him["place"] and card.get("lift_m", 0) > 2.0]
    if upstairs:   # an upper floor over this place (the boxing house roof): nothing of it is in the way down here, and the camera stays under it
        lift = world["places"][upstairs[0]]["lift_m"]
        page.value("window.forgeWalk.put(%f, %f, %f, %f, 70)" % (start[0], start[1], toward, toward))
        time.sleep(0.8)
        under = page.state()
        check("under %s (%.1f m up) he walked the hall floor freely, and the camera, tipped right up, stays below it (%.1f m)" % (world["places"][upstairs[0]]["label"], lift, under["camera"][1]),
              met["path_m"] > 1.0 and upstairs == under["ceilings"] and under["camera"][1] < lift - 0.4 and under["y"] == 0, under)
        page.value("window.forgeWalk.put(%f, %f, %f, %f, 19.5)" % (met["x"], met["z"], toward, toward))
        time.sleep(0.6)
    check("Lincoln says hello, and the card says he is in %s" % world["places"][him["place"]]["label"],
          said["hello"] == "lincoln" and said["place"] == him["place"] and page.value("document.querySelector('.walk-card h3').textContent") == world["places"][him["place"]]["label"], said)
    ground = world["ground"]
    edge = ground["center"][0] + ground["size_m"][0] / 2
    page.value("window.forgeWalk.put(%f, %f, 90)" % (edge - 2.0, ground["center"][1] + ground["size_m"][1] / 2 - 3.0))
    page.key("shift", True)
    page.key("w", True)
    off_edge = page.record(2.0)
    page.key("w", False)
    page.key("shift", False)
    check("running at the edge of the world he stays on it (x %.2f, the edge is at %.1f)" % (off_edge["x"], edge), off_edge["x"] <= edge - 0.3 and off_edge["touching"] == "the edge of the world", off_edge)
    dancer = next(t for t in world["toons"] if t["toon"] == "dancer")
    with open(os.path.join(REPO, "sets", world["places"][dancer["place"]]["set"], "set.json")) as f:
        stage = json.load(f)["marks"][dancer["mark"]]
    on_stage, _ = in_world(world, dancer["place"], stage["at"][0] - 1.2, stage["at"][1])
    page.value("window.forgeWalk.put(%f, %f, 0)" % tuple(on_stage))
    check("on the dancer's stage he stands %.2f m up, as she does" % stage["floor_y"], abs(page.state()["y"] - stage["floor_y"]) < 0.01, page.state())

    print("  places: the card, the story's line, a hello")
    with open(os.path.join(REPO, "sets", "settlement", "set.json")) as f:
        customer = json.load(f)["marks"]["customer"]
    spot, _ = in_world(world, "settlement", *customer["at"])
    page.value("window.forgeWalk.put(%f, %f, %f)" % (spot[0], spot[1], world["places"]["settlement"].get("facing_deg", 0) + customer["facing_deg"]))
    line = page.until("document.querySelector('.walk-line:not([hidden])')?.textContent", 10)
    said = page.state()
    told = next(a for a in world["artifacts"] if a["name"] == said["line"])
    check("in front of the stall, the story's line for what is on it: \"%s\"" % line, said["line"] in ("kettle", "bread") and told["about"] in line and told["title"] in line, said)
    card = page.value("document.querySelector('.walk-card').innerText")
    check("the card names the place, who is there, and opens it", world["places"]["settlement"]["label"] in card and "The troll" in card and "Open this place" in card
          and page.value("document.querySelector('.walk-card a').getAttribute('href')") == "#/set/settlement", card)
    page.until("window.forgeWorld && window.forgeWorld.settled", 20)
    return before


def phone_checks(page, world):
    print("  phone: the thumb stick and a tap on the ground")
    me = next(t for t in world["toons"] if t["toon"] == "roosevelt")
    start_walk(page, world["name"])
    left, top, wide, tall = page.box(".walk-stick")
    check("there is a thumb stick, big enough for a thumb (%d px)" % wide, wide >= 96 and tall >= 96)
    cx, cy = left + wide / 2, top + tall / 2
    page.touch("touchStart", cx, cy)
    page.touch("touchMove", cx, cy - wide * 0.2)
    time.sleep(0.7)
    gentle = page.record(1.5)
    page.touch("touchMove", cx, cy - wide * 0.5)
    time.sleep(0.9)
    hard = page.record(1.5)
    page.touch("touchEnd")
    said = page.state()
    check("pushed a little he walks (%.2f m/s), pushed to the edge he runs (%.2f m/s), let go he stops" % (gentle["speed_m_s"], hard["speed_m_s"]),
          gentle["gait"] == "walk" and 0.4 < gentle["speed_m_s"] <= said["walk_speed"] * 1.05 and hard["gait"] == "run" and abs(hard["speed_m_s"] - said["run_speed"]) / said["run_speed"] <= WITHIN, [gentle, hard])
    check("at a gentle walk too the body keeps to the clip's feet", abs(gentle["clip_speed_m_s"] - gentle["speed_m_s"]) / gentle["speed_m_s"] <= WITHIN, gentle)
    time.sleep(0.8)
    # a tap on the ground, a little ahead of him on the screen
    left, top, wide, tall = page.box(".pane.walking canvas")
    was = page.state()
    x, y = left + wide * 0.5, top + tall * 0.42
    page.touch("touchStart", x, y)
    page.touch("touchEnd")
    goal = page.until("JSON.stringify(window.forgeWalk.state().walking_to)", 5)
    goal = json.loads(goal)
    check("a tap on the ground sets him walking there", goal is not None and math.hypot(goal[0] - was["x"], goal[1] - was["z"]) > 1.0, goal)
    page.until("window.forgeWalk.state().walking_to === null && window.forgeWalk.state().speed < 0.01", 40)
    said = page.state()
    check("and he arrives (%.2f m from where the finger was)" % math.hypot(said["x"] - goal[0], said["z"] - goal[1]), math.hypot(said["x"] - goal[0], said["z"] - goal[1]) < 0.4, said)
    frames = page.record(4.0)
    print("    frames at phone size (%d x %d at %dx), standing: %.0f a second, median %.1f ms, 95th %.1f ms" % (PHONE[0], PHONE[1], PHONE[2], frames["fps"], frames["frame_ms_median"], frames["frame_ms_p95"]))

    print("  stop: everything goes back")
    left, top, wide, tall = page.box(".walk-stop")
    page.touch("touchStart", left + wide / 2, top + tall / 2)
    page.touch("touchEnd")
    page.until("window.forgeWalk === null", 10)
    back = json.loads(page.value("""JSON.stringify({ hash: location.hash, panel: Boolean(document.querySelector('.walk-panel')), button: document.querySelector('.walk-bar button').textContent })"""))
    check("\"Stop walking\" takes the panel away and the page is the world view again", not back["panel"] and back["button"] == "Walk around" and back["hash"].startswith("#/world/%s" % world["name"]) and "walk" not in back["hash"], back)
    return frames


def take_shots(page, world, out):
    """Pictures for a person to look at: walking on the grass, and at the settlement's stall, phone and desktop."""
    with open(os.path.join(REPO, "sets", "settlement", "set.json")) as f:
        customer = json.load(f)["marks"]["customer"]
    stall, _ = in_world(world, "settlement", customer["at"][0] + 0.9, customer["at"][1] + 0.5)
    taken = []
    for size_name, size in (("phone", PHONE), ("desktop", DESKTOP)):
        page.size(*size)
        start_walk(page, world["name"])
        page.key("w", True)
        time.sleep(2.2)
        path = os.path.join(out, "grass-%s.png" % size_name)
        page.picture(path)
        page.key("w", False)
        taken.append(path)
        page.value("window.forgeWalk.put(%f, %f, 200, 205)" % tuple(stall))
        page.until("Boolean(document.querySelector('.walk-line:not([hidden])'))", 10)
        page.until("window.forgeWorld && window.forgeWorld.settled", 20)
        time.sleep(1.2)
        path = os.path.join(out, "stall-%s.png" % size_name)
        page.picture(path)
        taken.append(path)
        frames = page.record(3.0)
        print("    %s: %.0f frames a second at the stall" % (size_name, frames["fps"]))
    for path in taken:
        print("SHOT %s" % os.path.relpath(path, REPO))


def run(runs, port=None, shots_dir=None, gpu=False):
    """Every check. Raises AssertionError at the first that fails. Returns the numbers worth keeping."""
    if not os.path.exists(shots.CHROME):
        print("    skipped: no Chrome at %s" % shots.CHROME)
        return None
    if not glob.glob(os.path.join(runs, "*-roosevelt-wrestler-1890s", "profiles", "lowpoly-walk.glb")):
        print("    skipped: Roosevelt's run, with its walk, is not under %s" % runs)
        return None
    server = None
    if not port:
        port = free_port()
        server = subprocess.Popen([sys.executable, os.path.join(REPO, "scripts", "gallery.py"), "--port", str(port), "--runs", runs], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:%s/" % port
    page = None
    try:
        for _ in range(60):
            try:
                served = json.load(urllib.request.urlopen(base + "api/world"))
                break
            except OSError:
                time.sleep(0.25)
        world = next(e for e in served["epochs"] if e["name"] == served["now"])
        page = Page(base, gpu)
        page.size(*PHONE)
        before = walk_checks(page, world, runs)
        frames = phone_checks(page, world)
        if shots_dir:
            take_shots(page, world, shots_dir)
        return {"overview": before, "frames": frames}
    finally:
        if page:
            page.close()
        if server:
            server.terminate()


def main():
    args = sys.argv[1:]
    opt = lambda flag: args[args.index(flag) + 1] if flag in args else None
    named = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in ("--port", "--shots"))]
    runs = os.path.abspath(named[0] if named else os.path.join(REPO, "runs"))
    print("walk: a scripted walk in a headless Chrome at phone size")
    try:
        run(runs, opt("--port"), opt("--shots") and os.path.abspath(opt("--shots")), "--gpu" in args)
    except Exception as e:  # a failed check, or a page that never answered
        print("    FAILED: %s: %s" % (type(e).__name__, str(e)[:800]))
        print("1 walk case failed")
        return 1
    print("the walk case passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
