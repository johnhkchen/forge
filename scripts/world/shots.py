"""Pictures of the gallery's world view, taken by a headless Chrome: the proof that it shows what it should.

    python3 scripts/world/shots.py [--port 8028] [--out evidence/world] [--epoch epoch-0] [place ...]

The gallery must be running (`just gallery`). For the whole world and for each
place named (none: every place of the epoch that is not inside another), it
opens the page at phone width (430 px) and at desktop width, waits until the
page says the world is set out (and, at a place, that what loads on coming
close has arrived), and saves

    <out>/overview-phone.png, overview-desktop.png
    <out>/<place>-phone.png, <place>-desktop.png
    <out>/load.json     what each view had fetched by then: files and bytes

Chrome is driven over its own debugging socket, spoken here in plain Python
(no packages): that is the only way to wait for the page itself to be ready
and to ask for a true phone-sized screen.
"""

import base64
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SIZES = {"phone": (430, 932, 2, True), "desktop": (1280, 1100, 1, False)}  # wide, tall, pixels per px, a phone?
DEBUG_PORT = int(os.environ.get("FORGE_DEBUG_PORT", "9347"))  # another, when someone else is taking pictures too
WAIT_S = 60


class Tab:
    """One browser tab, over Chrome's debugging socket (a WebSocket: text frames of JSON)."""

    def __init__(self, ws_url):
        host, rest = ws_url[len("ws://"):].split("/", 1)
        name, port = host.split(":")
        self.sock = socket.create_connection((name, int(port)))
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(("GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (rest, host, key)).encode())
        reply = b""
        while b"\r\n\r\n" not in reply:
            reply += self.sock.recv(4096)
        self.left = reply.split(b"\r\n\r\n", 1)[1]
        self.count = 0

    def read(self, n):
        while len(self.left) < n:
            more = self.sock.recv(1 << 16)
            if not more:
                raise ConnectionError("Chrome closed the socket")
            self.left += more
        out, self.left = self.left[:n], self.left[n:]
        return out

    def message(self):
        text = b""
        while True:
            first, second = self.read(2)
            size = second & 0x7F
            if size == 126:
                size = struct.unpack(">H", self.read(2))[0]
            elif size == 127:
                size = struct.unpack(">Q", self.read(8))[0]
            text += self.read(size)
            if first & 0x80:
                return json.loads(text) if text[:1] == b"{" else {}

    def ask(self, method, **params):
        self.count += 1
        body = json.dumps({"id": self.count, "method": method, "params": params}).encode()
        mask = os.urandom(4)
        if len(body) < 126:
            size = bytes([0x80 | len(body)])
        elif len(body) < 65536:
            size = bytes([0x80 | 126]) + struct.pack(">H", len(body))
        else:
            size = bytes([0x80 | 127]) + struct.pack(">Q", len(body))
        self.sock.sendall(bytes([0x81]) + size + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(body)))
        while True:
            reply = self.message()
            if reply.get("id") == self.count:
                return reply.get("result") or {}

    def value(self, expression):
        return (self.ask("Runtime.evaluate", expression=expression, returnByValue=True).get("result") or {}).get("value")


def main():
    args = sys.argv[1:]
    opt = lambda flag, default: args[args.index(flag) + 1] if flag in args else default
    port, out, epoch_name = opt("--port", "8028"), os.path.abspath(opt("--out", os.path.join(REPO, "evidence", "world"))), opt("--epoch", None)
    named = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or not args[i - 1].startswith("--"))]
    base = "http://localhost:%s/" % port
    world = json.load(urllib.request.urlopen(base + "api/world"))
    epoch = next((e for e in world["epochs"] if e["name"] == (epoch_name or world["now"])), world["epochs"][-1])
    places = named or [name for name, place in epoch["places"].items() if not place.get("inside")]
    os.makedirs(out, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="forge-shots-")
    chrome = subprocess.Popen([CHROME, "--headless=new", "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--hide-scrollbars", "--remote-debugging-port=%d" % DEBUG_PORT,
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
        for place in [None] + places:
            for size_name, (wide, tall, ratio, phone) in SIZES.items():
                tab.ask("Emulation.setDeviceMetricsOverride", width=wide, height=tall, deviceScaleFactor=ratio, mobile=phone)
                tab.ask("Page.navigate", url="about:blank")
                tab.ask("Page.navigate", url="%s#/world/%s%s" % (base, epoch["name"], "/" + place if place else ""))
                began, settled = time.time(), None
                while time.time() - began < WAIT_S:
                    settled = tab.value("window.forgeWorld && window.forgeWorld.settled ? JSON.stringify(window.forgeWorld) : null")
                    if settled:
                        break
                    time.sleep(0.25)
                time.sleep(0.6)  # one more frame, and the camera at rest
                path = os.path.join(out, "%s-%s.png" % (place or "overview", size_name))
                with open(path, "wb") as f:
                    f.write(base64.b64decode(tab.ask("Page.captureScreenshot", format="png")["data"]))
                said = json.loads(settled) if settled else None
                loads["%s-%s" % (place or "overview", size_name)] = said
                print("SHOT %s: %s" % (os.path.relpath(path, REPO), "%d files, %.2f MB, set out in %.1f s" % (said["files"], said["bytes"] / 1e6, said["seconds"]) if said else "the page did not settle in %d s" % WAIT_S))
    finally:
        chrome.terminate()
    with open(os.path.join(out, "load.json"), "w") as f:
        json.dump({"about": "What the world view had fetched when each picture was taken (from the page itself: its own files, not three.js or the fonts). A place's number includes the overview, which loads first.",
                   "views": loads}, f, indent=1)
        f.write("\n")


if __name__ == "__main__":
    main()
