"""Pictures of the casting pages at phone and desktop width, taken by a headless Chrome, one for each stage.

    python3 scripts/casting/shots.py [--port 8050] [--out evidence/casting] [--role robot] [--candidate villager]

The gallery must be running on that port. Each picture is a page opened cold, scrolled to one stage, and
(for the stages that play something) left until its stage says it is ready. Saves <out>/<stage>-phone.png and
<stage>-desktop.png, and prints any error the page threw.
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts", "world"))
import shots as world_shots  # noqa: E402  (the tab that speaks to Chrome)

SIZES = {"phone": (430, 932, 2, True), "desktop": (1280, 1000, 1, False)}
DEBUG_PORT = 9351
WAIT_S = 90
CATCH = "window.__castingErrors = []; addEventListener('error', (e) => window.__castingErrors.push(String(e.message))); addEventListener('unhandledrejection', (e) => window.__castingErrors.push(String(e.reason)));"


def stages(role, candidate):
    """(name, hash, what to do once there, what says it is ready): one picture each."""
    scroll = lambda target: "document.getElementById('%s')?.scrollIntoView({block: 'start'}); true" % target
    cards_ready = "window.forgeCards && window.forgeCards.state().ready"
    watch_ready = "window.forgeWatch && window.forgeWatch.state().ready && window.forgeWatch.state().time > 2 && (window.forgeWatch.set({time: 31}), true)"
    click = lambda words: "[...document.querySelectorAll('button')].find((b) => b.textContent.trim() === %s)?.click(); true" % json.dumps(words)
    page, person = "#/casting/%s" % role, "#/casting/%s/%s" % (role, candidate)
    return [
        ("1-board-and-breakdown", page, "true", "document.querySelector('.casting-board')"),
        ("2-headshots", page, scroll("stage-headshots"), "document.querySelector('.casting-looks')"),
        ("3-shortlist", page, scroll("stage-shortlist"), "document.querySelector('.casting-person')"),
        ("4-tape-the-reel", person, scroll("stage-tapes"), cards_ready),
        ("5-chemistry-crew-dance", person, click("The crew dance") + ";" + scroll("stage-tapes"), watch_ready),
        ("6-beside-the-cast", person, "document.querySelector('.casting-lineup')?.scrollIntoView({block: 'start'}); true", "document.querySelectorAll('.casting-palette .chip-colour').length > 10"),
        ("7-camera-test", person, "document.querySelector('.casting-scores, .casting-section:nth-of-type(3)')?.scrollIntoView({block: 'start'}); true", "true"),
        ("8-callbacks", person, scroll("stage-callbacks"), "document.querySelector('.casting-notes')"),
        ("9-cost-of-a-step", page, "document.querySelector('.casting-steps .casting-try')?.click(); document.querySelector('.casting-steps')?.scrollIntoView({block: 'start'}); true", "document.querySelector('.casting-plan:not([hidden]) code')"),
    ]


def main():
    args = sys.argv[1:]
    opt = lambda flag, default: args[args.index(flag) + 1] if flag in args else default
    base = "http://localhost:%s/" % opt("--port", "8050")
    out = os.path.abspath(opt("--out", os.path.join(REPO, "evidence", "casting")))
    only = opt("--only", "")
    os.makedirs(out, exist_ok=True)
    urllib.request.urlopen(base + "api/casting").read()
    profile = tempfile.mkdtemp(prefix="forge-casting-shots-")
    chrome = subprocess.Popen([world_shots.CHROME, "--headless=new", "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--hide-scrollbars",
                               "--remote-debugging-port=%d" % DEBUG_PORT, "--user-data-dir=" + profile, "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        tabs = None
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % DEBUG_PORT))
                break
            except OSError:
                time.sleep(0.2)
        tab = world_shots.Tab(next(t for t in tabs if t.get("type") == "page")["webSocketDebuggerUrl"])
        tab.ask("Page.enable")
        tab.ask("Page.addScriptToEvaluateOnNewDocument", source=CATCH)
        for name, where, do, ready in stages(opt("--role", "robot"), opt("--candidate", "villager")):
            if only and only not in name:
                continue
            for size, (wide, tall, ratio, phone) in SIZES.items():
                tab.ask("Emulation.setDeviceMetricsOverride", width=wide, height=tall, deviceScaleFactor=ratio, mobile=phone)
                tab.ask("Page.navigate", url="about:blank")
                tab.ask("Page.navigate", url=base + where)
                began = time.time()
                while time.time() - began < WAIT_S and not tab.value("Boolean(document.querySelector('.casting'))"):
                    time.sleep(0.25)
                time.sleep(0.8)
                tab.value(do)
                ok = False
                while time.time() - began < WAIT_S:
                    ok = bool(tab.value("Boolean(%s)" % ready))
                    if ok:
                        break
                    time.sleep(0.4)
                time.sleep(1.5)  # a few frames, and the scroll at rest
                # the scroll again (what loaded above it may have moved it), but never a click again: that would start the stage over
                tab.value(";".join(part for part in do.split(";") if "scrollIntoView" in part) or "true")
                time.sleep(0.4)
                path = os.path.join(out, "%s-%s.png" % (name, size))
                with open(path, "wb") as f:
                    f.write(base64.b64decode(tab.ask("Page.captureScreenshot", format="png")["data"]))
                errors = tab.value("JSON.stringify(window.__castingErrors || [])")
                print("SHOT %s%s%s" % (os.path.relpath(path, REPO), "" if ok else " (not ready in %d s)" % WAIT_S, " errors: %s" % errors if errors and errors != "[]" else ""), flush=True)
    finally:
        chrome.terminate()


if __name__ == "__main__":
    main()
