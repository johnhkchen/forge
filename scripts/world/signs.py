"""Letters a place's signs: small pictures of words, made by a headless Chrome from a scrap of HTML.

    python3 scripts/world/signs.py            # every sign below
    python3 scripts/world/signs.py spawn      # only one place's

    sets/spawn/sign.png        BUY HOUSE, in the developer's default lettering:
                               plain black Arial on plain grey, nothing chosen
    sets/settlement/sign.png   the stall's sign, saying which is the tea and
                               which is the bread, in a hand

No model is asked and nothing is painted: these are words, so they are typed.
A house built from a design letters its own sign the same way (`write`).
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

PAGE = """<!doctype html><meta charset="utf-8"><style>
html, body { margin: 0; width: %(w)dpx; height: %(h)dpx; overflow: hidden; }
body { display: flex; align-items: center; justify-content: center; text-align: center; box-sizing: border-box; %(css)s }
</style><body>%(body)s</body>"""

SIGNS = {
    "spawn": {"w": 650, "h": 220, "css": "background: #d6d4cf; color: #111; font: bold 96px Arial, Helvetica, sans-serif; letter-spacing: 2px; border: 6px solid #111;",
              "body": "BUY HOUSE"},
    "settlement": {"w": 600, "h": 400, "css": "background: #f2efe9; color: #1c1917; font: 44px 'Chalkboard SE', 'Marker Felt', 'Comic Sans MS', sans-serif; line-height: 1.25; border: 10px solid #5a3c26; padding: 10px;",
                   "body": "<div><b>&larr; TEA</b> &nbsp;&middot;&nbsp; <b>BREAD &rarr;</b><br><span style='font-size:30px'>The pots are for the tea.<br>The bread is the long one.</span></div>"},
}


def write(out, w, h, css, body):
    """One sign: the words in `body`, styled by `css`, as a w x h picture at `out`."""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as page:
        page.write(PAGE % {"w": w, "h": h, "css": css, "body": body})
    try:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1", "--window-size=%d,%d" % (w, h),
                        "--screenshot=" + out, "file://" + page.name], check=True, capture_output=True, timeout=60)
    finally:
        os.unlink(page.name)
    return out


def main():
    for name in sys.argv[1:] or list(SIGNS):
        out = write(os.path.join(REPO, "sets", name, "sign.png"), **SIGNS[name])
        print("SIGN", os.path.relpath(out, REPO))


if __name__ == "__main__":
    main()
