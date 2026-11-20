"""Letters a drawn comic and lays out its page.

    python3 scripts/comic/layout.py comics/<name> [--no-png]

Reads comic.json (the words) and panels.json (where each head landed), and writes into the same folder:

    reader.json   the comic as the gallery reads it: each panel's picture, sky and lettering (SVG)
    page.html     one self-contained page: pictures and the comic font are inside the file. A strip on a wide
                  screen, one panel under another on a phone; a scroll episode is always one column.
    strip.png     the whole comic as one picture (scroll.png for a scroll episode), taken of the same HTML by a
                  headless Chrome. Skipped with a note if Chrome is not installed.

The words stay text all the way: SVG <text> over the picture, in Comic Neue (Google Fonts, OFL), with Bangers for
sound effects. Lora and Karla are only for the page around the comic. Plain Python, no Blender.
"""

import base64
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lettering  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
FONTS = os.path.join(REPO, "gallery", "vendor", "fonts")
KIT_CSS = os.path.join(REPO, "gallery", "vendor", "b28-clay.css")
COMIC_CSS = os.path.join(REPO, "gallery", "comic.css")
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
EXPORT_PANEL = {"strip": 480, "scroll": 720}  # how wide a panel is in the .png
GUTTER = 18
FORMATS = {"strip": "A four-panel strip", "scroll": "A scroll episode"}


def data_uri(path, kind):
    with open(path, "rb") as f:
        return "data:%s;base64,%s" % (kind, base64.b64encode(f.read()).decode())


def font_faces(embedded):
    """@font-face rules for the comic fonts: inside the page (base64) or beside the gallery (a path)."""
    rules = []
    for family, name in (("Comic Neue", "ComicNeue-Bold.woff2"), ("Bangers", "Bangers-Regular.woff2")):
        path = os.path.join(FONTS, name)
        if not os.path.exists(path):
            continue
        source = data_uri(path, "font/woff2") if embedded else "vendor/fonts/" + name
        rules.append('@font-face{font-family:"%s";font-weight:%d;font-display:block;src:url(%s) format("woff2");}'
                     % (family, 700 if family == "Comic Neue" else 400, source))
    return "\n".join(rules)


def lighter(folder, file, quality=86):
    """A panel's picture as WebP (a fifth of the size, same look), if cwebp is installed; else the .png it is."""
    tool = shutil.which("cwebp")
    if not tool:
        return file, "image/png"
    small = file[:-4] + ".webp"
    done = subprocess.run([tool, "-quiet", "-q", str(quality), "-alpha_q", "95", os.path.join(folder, file), "-o", os.path.join(folder, small)],
                          capture_output=True)
    return (small, "image/webp") if done.returncode == 0 else (file, "image/png")


def read(path):
    with open(path) as f:
        return f.read()


SKY_ZOOM = {"wide": 100, "two-shot": 135, "single": 175, "close-up": 230}  # a backdrop is drawn larger behind a closer shot


def sky_class(panel):
    return "sky-" + os.path.splitext(os.path.basename(panel["sky_image"]))[0] if panel.get("sky_image") else ""


def figure(panel, number, picture):
    wide, tall = panel["size"]
    sky = panel.get("sky") or ["#f2efe9", "#e9e2d4"]
    look = "aspect-ratio:%d/%d;background-color:%s;" % (wide, tall, sky[-1])
    if panel.get("sky_image"):
        look += "background-size:auto %d%%;" % SKY_ZOOM.get(panel.get("framing"), 100)
    else:
        look += "background-image:linear-gradient(%s,%s);" % (sky[0], sky[-1])
    return ('<figure class="panel %s" style="%s"><img src="%s" alt="%s" width="%d" height="%d">%s</figure>'
            % (sky_class(panel), look, picture, lettering.esc(panel["alt"]), wide, tall, panel["svg"]))


def sky_rules(folder, panels):
    """One CSS rule per painted backdrop the comic uses, with the picture inside it."""
    rules, seen = [], set()
    for panel in panels:
        if not panel.get("sky_image") or panel["sky_image"] in seen:
            continue
        seen.add(panel["sky_image"])
        comics = os.path.join(REPO, "comics")  # backdrops are kept with the cast, whatever folder the comic is in
        file, kind = lighter(comics, panel["sky_image"], 82)
        rules.append(".%s{background-image:url(%s);background-position:center 42%%;background-repeat:no-repeat}"
                     % (sky_class(panel), data_uri(os.path.join(comics, file), kind)))
    return "\n".join(rules)


def alt_text(number, panel):
    said = "; ".join('%s: "%s"' % (l["who"], l["says"]) for l in panel.get("lines") or [])
    bits = ["Panel %d" % number, panel.get("caption") or "", said, panel.get("sfx") or ""]
    return ". ".join(b for b in bits if b)


def page(comic, panels, pictures, skies="", embedded=True, export=False):
    layout = comic.get("layout", "strip")
    figures = "\n".join(figure(p, n, pictures[n - 1]) for n, p in enumerate(panels, 1))
    count = len(panels)
    kicker = "%s · %d panels" % (FORMATS.get(layout, "A comic"), count) if layout != "strip" else FORMATS["strip"]
    style = "\n".join([read(KIT_CSS), font_faces(embedded), read(COMIC_CSS), skies])
    if export:
        width = EXPORT_PANEL[layout] * (count if layout == "strip" else 1) + GUTTER * ((count if layout == "strip" else 1) + 1)
        return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>%s</title><style>%s\n'
                'html,body{margin:0;padding:0;background:#faf8f5}'
                '.export{width:%dpx;padding:%dpx;box-sizing:border-box}'
                '.export .comic{gap:%dpx;max-width:none}'
                '.export .comic.strip{grid-template-columns:repeat(%d,1fr)}'
                '.export .credit{font:600 15px "Karla",system-ui,sans-serif;color:#736b66;margin:12px 2px 0;display:flex;justify-content:space-between}'
                '</style></head><body class="b28-clay"><div class="export"><div class="comic %s">%s</div>'
                '<p class="credit"><span>%s</span><span>Forge comics</span></p></div></body></html>'
                % (lettering.esc(comic["title"]), style, width, GUTTER, GUTTER, count, layout, figures, lettering.esc(comic["title"])))
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#faf8f5">
<title>%(title)s</title>
<meta name="description" content="%(kicker)s. %(premise)s">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Karla:wght@400;600;700&family=Lora:wght@500;600&display=swap" rel="stylesheet">
<style>
%(style)s
</style>
</head>
<body class="b28-clay comic-page">
<header class="comic-head">
  <p class="kicker">%(kicker)s</p>
  <h1>%(title)s</h1>
</header>
<main class="comic-sheet clay-surface">
<div class="comic %(layout)s">
%(figures)s
</div>
</main>
<footer class="comic-foot">
  <p>Drawn from our own 3D characters, posed and inked by the same hand every time. The words are real text: select them, or have them read aloud.</p>
</footer>
</body>
</html>
""" % {"title": lettering.esc(comic["title"]), "kicker": kicker, "premise": lettering.esc(comic.get("premise", "")), "style": style,
       "layout": layout, "figures": figures}


def screenshot(html_path, png_path, width, height):
    if not os.path.exists(CHROME):
        return "no Chrome at %s (set CHROME): the .png was not made" % CHROME
    done = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                           "--virtual-time-budget=3000", "--window-size=%d,%d" % (width, height), "--screenshot=" + png_path,
                           "file://" + html_path], capture_output=True, text=True, timeout=120)
    if done.returncode != 0 or not os.path.exists(png_path):
        return "Chrome could not take the picture: " + done.stderr.strip()[-300:]
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    folder = os.path.abspath(args[0])
    with open(os.path.join(folder, "comic.json")) as f:
        comic = json.load(f)
    with open(os.path.join(folder, "panels.json")) as f:
        drawn = json.load(f)
    layout = comic.get("layout", "strip")
    panels, problems = [], []
    for number, (panel, meta) in enumerate(zip(comic["panels"], drawn["panels"]), 1):
        lettered = lettering.letter(meta, panel)
        for problem in lettered["problems"]:
            problems.append("panel %d: %s" % (number, problem))
        file, kind = lighter(folder, meta["file"])
        panels.append({"file": file, "kind": kind, "size": meta["size"], "sky": meta.get("sky"), "sky_image": meta.get("sky_image"),
                       "framing": meta.get("framing"), "alt": alt_text(number, panel),
                       "svg": lettering.to_svg(lettered, meta["size"]), "lettering": lettered})
    embedded = [data_uri(os.path.join(folder, p["file"]), p["kind"]) for p in panels]
    skies = sky_rules(folder, panels)
    with open(os.path.join(folder, "page.html"), "w") as f:
        f.write(page(comic, panels, embedded, skies))
    png_name = "strip.png" if layout == "strip" else "scroll.png"
    note = None
    if "--no-png" not in sys.argv:
        count = len(panels)
        across = EXPORT_PANEL[layout]
        if layout == "strip":
            width = across * count + GUTTER * (count + 1)
            height = GUTTER * 2 + max(int(across * p["size"][1] / p["size"][0]) for p in panels) + 40
        else:
            width = across + GUTTER * 2
            height = GUTTER * (count + 1) + sum(int(round(across * p["size"][1] / p["size"][0])) for p in panels) + 40
        export_path = os.path.join(folder, ".export.html")
        with open(export_path, "w") as f:
            f.write(page(comic, panels, embedded, skies, export=True))
        note = screenshot(export_path, os.path.join(folder, png_name), width, height)
        os.remove(export_path)
    with open(os.path.join(folder, "reader.json"), "w") as f:
        json.dump({"name": os.path.basename(folder), "title": comic["title"], "premise": comic.get("premise", ""), "layout": layout,
                   "panels": [dict({k: p[k] for k in ("file", "size", "sky", "alt", "svg")},
                                    sky_image=p["sky_image"][:-4] + ".webp" if p.get("sky_image") and shutil.which("cwebp") else p.get("sky_image"),
                                    sky_zoom=SKY_ZOOM.get(p.get("framing"), 100)) for p in panels],
                   "png": png_name if note is None and "--no-png" not in sys.argv else None, "html": "page.html",
                   "draw_seconds": drawn.get("seconds"), "problems": problems}, f, indent=1)
    print("PAGE %s: %d panels, %s" % (os.path.join(folder, "page.html"), len(panels), png_name if not note else note))
    for problem in problems:
        print("PAGE problem: " + problem)


if __name__ == "__main__":
    main()
