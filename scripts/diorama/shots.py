"""Pictures of the gallery's front page, taken by a headless Chrome, and what the page had to fetch to show it.

    python3 scripts/diorama/shots.py [--port 8028] [--out evidence/diorama]

The gallery must be running (`just gallery`). The front page is opened cold
(nothing cached) at phone width (430 px) and at desktop width. When the page
says the diorama is on its shelf, the script saves

    <out>/front-phone.png, front-desktop.png             the first screen
    <out>/front-phone-full.png, front-desktop-full.png   the whole page, scrolled through
    <out>/load.json     every file fetched before the first screen was ready, in groups, in bytes on the wire

The bytes are Chrome's own count of what came over the network (compressed
where the server compresses), so three.js, the fonts and the mesh decoder are
in it too, not only our files.
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

SIZES = {"phone": (430, 932, 2, True), "desktop": (1280, 900, 1, False)}  # wide, tall, pixels per px, a phone?
DEBUG_PORT = 9348
WAIT_S = 90
GROUPS = ("the diorama", "the page itself", "three.js and the mesh decoder", "fonts", "other pictures on the page", "anything else")


def group_of(short):
    """Which pile a fetched file belongs in, from its address (ours start with /)."""
    if short.startswith("/dioramas/"):
        return "the diorama"
    if "fonts.googleapis.com" in short or "fonts.gstatic.com" in short or short.startswith("/vendor/fonts/"):
        return "fonts"
    if "cdn.jsdelivr.net" in short:
        return "three.js and the mesh decoder"
    if short.startswith(("/runs/", "/sets/", "/comics/", "/world/", "/shots/")):
        return "other pictures on the page"
    return "the page itself" if short.startswith("/") else "anything else"


class Tab(world_shots.Tab):
    """A tab that also keeps what Chrome says about the network while it waits for answers."""

    def __init__(self, ws_url):
        super().__init__(ws_url)
        self.requests, self.done = {}, {}

    def message(self):
        said = super().message()
        params = said.get("params") or {}
        if said.get("method") == "Network.responseReceived":
            self.requests[params["requestId"]] = params["response"]["url"]
        elif said.get("method") == "Network.loadingFinished":
            self.done[params["requestId"]] = params.get("encodedDataLength", 0)
        return said

    def fetched(self):
        return [(self.requests[r], size) for r, size in self.done.items() if r in self.requests and not self.requests[r].startswith(("data:", "blob:", "about:"))]


def grouped(files, base):
    """Fetched files in groups: {group: {files, bytes, list}}, and the total."""
    out = {name: {"files": 0, "bytes": 0, "list": []} for name in GROUPS}
    for url, size in sorted(files):
        short = (url[len(base) - 1:] if url.startswith(base) else url).split("?")[0]
        name = group_of("/index.html" if short == "/" else short)
        out[name]["files"] += 1
        out[name]["bytes"] += int(size)
        out[name]["list"].append(["/index.html" if short == "/" else short, int(size)])
    out = {name: part for name, part in out.items() if part["files"]}
    return out, {"files": sum(p["files"] for p in out.values()), "bytes": sum(p["bytes"] for p in out.values())}


def main():
    args = sys.argv[1:]
    opt = lambda flag, default: args[args.index(flag) + 1] if flag in args else default
    port, out = opt("--port", "8028"), os.path.abspath(opt("--out", os.path.join(REPO, "evidence", "diorama")))
    base = "http://localhost:%s/" % port
    shelf = json.load(urllib.request.urlopen(base + "api/dioramas"))
    if not shelf or not shelf[0].get("glb"):
        sys.exit("no built diorama to show: just diorama <name>")
    os.makedirs(out, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="forge-shots-")
    chrome = subprocess.Popen([world_shots.CHROME, "--headless=new", "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--hide-scrollbars", "--remote-debugging-port=%d" % DEBUG_PORT,
                               "--user-data-dir=" + profile, "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    loads = {}
    try:
        tabs = None
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % DEBUG_PORT))
                break
            except OSError:
                time.sleep(0.2)
        tab = Tab(next(t for t in tabs if t.get("type") == "page")["webSocketDebuggerUrl"])
        tab.ask("Network.enable")
        tab.ask("Network.setCacheDisabled", cacheDisabled=True)
        for size_name, (wide, tall, ratio, phone) in SIZES.items():
            tab.ask("Emulation.setDeviceMetricsOverride", width=wide, height=tall, deviceScaleFactor=ratio, mobile=phone)
            tab.ask("Page.navigate", url="about:blank")
            time.sleep(0.3)
            tab.requests, tab.done = {}, {}
            tab.ask("Page.navigate", url=base)
            began, settled = time.time(), None
            while time.time() - began < WAIT_S:
                settled = tab.value("window.forgeDiorama && window.forgeDiorama.settled ? JSON.stringify(window.forgeDiorama) : null")
                if settled:
                    break
                time.sleep(0.25)
            ready = time.time() - began
            for _ in range(6):  # a few more frames, and whatever else the first screen was still fetching
                time.sleep(0.25)
                tab.value("1")
            groups, total = grouped(tab.fetched(), base)
            path = os.path.join(out, "front-%s.png" % size_name)
            with open(path, "wb") as f:
                f.write(base64.b64decode(tab.ask("Page.captureScreenshot", format="png")["data"]))
            said = json.loads(settled) if settled else None
            loads[size_name] = {"screen": [wide, tall], "ready_s": round(ready, 1), "the_diorama_said": said, "total": total, "groups": groups}
            print("SHOT %s: %s" % (os.path.relpath(path, REPO), "%d files, %.2f MB over the network before the first screen was ready (%.1f s here); the diorama itself %.2f MB" % (
                total["files"], total["bytes"] / 1e6, ready, groups.get("the diorama", {}).get("bytes", 0) / 1e6) if said else "the page did not settle in %d s" % WAIT_S))
            for name, part in groups.items():
                print("SHOT   %-30s %3d files %8.1f kB" % (name, part["files"], part["bytes"] / 1e3))
            # The whole page, top to bottom: the diorama, then everything that follows it as before.
            high = tab.value("Math.ceil(document.documentElement.scrollHeight)") or tall
            tab.ask("Emulation.setDeviceMetricsOverride", width=wide, height=min(int(high), 6000), deviceScaleFactor=1, mobile=phone)
            time.sleep(1.5)
            tab.value("1")
            full = os.path.join(out, "front-%s-full.png" % size_name)
            with open(full, "wb") as f:
                f.write(base64.b64decode(tab.ask("Page.captureScreenshot", format="png")["data"]))
            print("SHOT %s" % os.path.relpath(full, REPO))
    finally:
        chrome.terminate()
    with open(os.path.join(out, "load.json"), "w") as f:
        json.dump({"about": "What the gallery's front page fetched, cold, before its first screen was ready: every file, in bytes over the network as Chrome counted them. "
                            "Pictures further down the page load as you scroll to them and are not in the first screen's count unless Chrome fetched them early.",
                   "views": loads}, f, indent=1)
        f.write("\n")


if __name__ == "__main__":
    main()
