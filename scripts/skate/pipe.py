"""A halfpipe's shape, cut across: where the surface is and which way it faces.

    python3 scripts/skate/pipe.py [set]        # the ramp's numbers, and a few points along it

A halfpipe is the same shape all the way along, so everything about it is in
one cut across it: a flat bottom, a quarter circle up each side (the
transition), a short straight piece of wall on top of that (the vert), a
steel tube along the top edge (the coping) and a platform behind it (the
deck). A set that has one says so in its set.json, under "ramp":

    flat_m      the flat bottom, across
    radius_m    the transitions' radius
    vert_m      the straight wall above each transition
    deck_m      how deep each platform is
    width_m     how long the ramp is (along z)
    coping_radius_m, coping_proud_m   the tube on each lip, and how far it stands out

x is across the pipe, y is up, z is along it; the middle of the flat is 0, 0.

The motion code asks for the surface by how far along it a point is, `s`,
in metres from the middle of the flat (minus to the left, plus to the
right), going up the wall as it grows: the flat, then the transition, then
the vert, ending at the lip. Past the lip `s` carries straight on up, as a
board leaving the ramp does.

    Pipe.at(s)         {x, y, tangent, normal}: the point, the way the surface
                       runs there (toward +s) and the way it faces (off the
                       surface, into the pipe)
    Pipe.where(x, y)   (s, off): the nearest point of the riding surface to a
                       point in the cut, and how far off it the point is
                       (minus: behind the surface)
    Pipe.inside(x, y, z)   how deep a point is in the ramp itself (surface,
                       walls and decks; 0 in the open air)

Plain Python: no Blender, no numpy.
"""

from __future__ import annotations

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
KEYS = ("flat_m", "radius_m", "vert_m", "deck_m", "width_m")


class Pipe:
    def __init__(self, ramp: dict):
        missing = [k for k in KEYS if k not in ramp]
        if missing:
            raise ValueError("the ramp needs %s" % ", ".join(missing))
        self.ramp = ramp
        self.flat, self.radius, self.vert = float(ramp["flat_m"]), float(ramp["radius_m"]), float(ramp["vert_m"])
        self.deck, self.width = float(ramp["deck_m"]), float(ramp["width_m"])
        self.half_flat = self.flat / 2.0
        self.arc = self.radius * math.pi / 2.0            # the length of one transition
        self.lip = self.half_flat + self.arc + self.vert  # s at the top edge
        self.height = self.radius + self.vert             # how high the decks are
        self.wall_x = self.half_flat + self.radius        # where the vert stands
        self.end_x = self.wall_x + self.deck              # the outer edge of a deck
        self.coping_r = float(ramp.get("coping_radius_m", 0.03))
        self.coping_proud = float(ramp.get("coping_proud_m", 0.012))

    @classmethod
    def of_set(cls, name: str = "halfpipe") -> "Pipe":
        sys.path.insert(0, os.path.join(REPO, "scripts", "sets"))
        import standing

        st = standing.load(name)
        if "ramp" not in st:
            raise ValueError("the set \"%s\" has no ramp" % st.get("name"))
        return cls(st["ramp"])

    def part(self, s: float) -> str:
        a = abs(s)
        if a <= self.half_flat:
            return "flat"
        if a <= self.half_flat + self.arc:
            return "transition"
        return "vert" if a <= self.lip + 1e-9 else "air"

    def at(self, s: float) -> dict:
        """The surface `s` metres from the middle of the flat. Past the lip it carries straight on up."""
        side = -1.0 if s < 0 else 1.0
        a = abs(s)
        if a <= self.half_flat:
            x, y, t, n = a, 0.0, (1.0, 0.0), (0.0, 1.0)
        elif a <= self.half_flat + self.arc:
            th = (a - self.half_flat) / self.radius
            x, y = self.half_flat + self.radius * math.sin(th), self.radius * (1.0 - math.cos(th))
            t, n = (math.cos(th), math.sin(th)), (-math.sin(th), math.cos(th))
        else:
            x, y, t, n = self.wall_x, self.radius + (a - self.half_flat - self.arc), (0.0, 1.0), (-1.0, 0.0)
        # The left side is the right side in a mirror; the tangent still runs toward +s.
        return {"x": side * x, "y": y, "tangent": (t[0], side * t[1]), "normal": (side * n[0], n[1]),
                "slope_deg": math.degrees(math.atan2(side * t[1], t[0])), "part": self.part(s)}

    def where(self, x: float, y: float) -> tuple:
        """(s, off): the nearest point of the riding surface, and how far off it (x, y) is. Off is minus behind the surface."""
        side = -1.0 if x < 0 else 1.0
        a = abs(x)
        if a <= self.half_flat:
            return side * a, y
        if y <= self.radius:
            dx, dy = a - self.half_flat, self.radius - y
            th = min(max(math.atan2(dx, dy), 0.0), math.pi / 2.0)
            return side * (self.half_flat + self.radius * th), self.radius - math.hypot(dx, dy)
        if y <= self.height:
            return side * (self.half_flat + self.arc + y - self.radius), self.wall_x - a
        away = math.hypot(self.wall_x - a, y - self.height)  # above the lip: the lip is the nearest of it
        return side * self.lip, away if a <= self.wall_x else -away

    def inside(self, x: float, y: float, z: float = 0.0) -> float:
        """How deep a point is in the ramp itself, in metres: under the riding surface, in a wall or under a deck. 0 in the open air."""
        a = abs(x)
        if abs(z) > self.width / 2.0 or a > self.end_x:
            return 0.0
        if y < 0.0:
            return -y
        if a <= self.half_flat:
            return 0.0
        under_arc = math.hypot(a - self.half_flat, self.radius - y) - self.radius  # past the transition's curve by this much
        if a < self.wall_x:
            return max(0.0, under_arc) if y < self.radius else 0.0
        if y >= self.height:
            return 0.0
        return min(a - self.wall_x, self.height - y) if y >= self.radius else min(self.height - y, under_arc)

    def coping(self, side: float) -> tuple:
        """The middle of the tube on one lip (side -1 or 1), in the cut: (x, y)."""
        return side * (self.wall_x + self.coping_r - self.coping_proud), self.height - self.coping_r + self.coping_proud

    def sections(self) -> list:
        """The cut as a list of pieces, left to right, for a set.json to carry in words and numbers."""
        hf, r, w, h, e = self.half_flat, self.radius, self.wall_x, self.height, self.end_x

        def rnd(v):
            return round(v, 4)

        out = []
        for side, name in ((-1.0, "left"), (1.0, "right")):
            pieces = [
                {"part": "deck " + name, "kind": "line", "from": [rnd(side * e), rnd(h)], "to": [rnd(side * w), rnd(h)], "about": "the platform: stand here, drop in from here"},
                {"part": "vert " + name, "kind": "line", "from": [rnd(side * w), rnd(h)], "to": [rnd(side * w), rnd(r)],
                 "s": [rnd(side * self.lip), rnd(side * (hf + self.arc))], "about": "the straight wall under the coping"},
                {"part": "transition " + name, "kind": "arc", "centre": [rnd(side * hf), rnd(r)], "radius_m": rnd(r), "from": [rnd(side * w), rnd(r)], "to": [rnd(side * hf), 0.0],
                 "s": [rnd(side * (hf + self.arc)), rnd(side * hf)], "about": "a quarter circle from the wall down to the flat"},
            ]
            if side < 0:
                out += pieces
                out.append({"part": "flat", "kind": "line", "from": [rnd(-hf), 0.0], "to": [rnd(hf), 0.0], "s": [rnd(-hf), rnd(hf)], "about": "the flat bottom"})
            else:
                for piece in reversed(pieces):  # left to right: up the right side
                    piece = dict(piece)
                    piece["from"], piece["to"] = piece["to"], piece["from"]
                    if "s" in piece:
                        piece["s"] = piece["s"][::-1]
                    out.append(piece)
        return out


def main() -> None:
    pipe = Pipe.of_set(sys.argv[1] if len(sys.argv) > 1 else "halfpipe")
    print("PIPE flat %.2f m, transitions of %.2f m, %.2f m of vert, decks %.2f m up and %.2f m deep, %.1f m long; %.2f m along the surface from the middle to a lip" % (
        pipe.flat, pipe.radius, pipe.vert, pipe.height, pipe.deck, pipe.width, pipe.lip))
    for share in (0.0, 0.25, 0.5, 0.75, 1.0):
        p = pipe.at(share * pipe.lip)
        print("PIPE %.2f m along: x %.2f, y %.2f, the surface tilts %.0f degrees (%s)" % (share * pipe.lip, p["x"], p["y"], p["slope_deg"], p["part"]))


if __name__ == "__main__":
    main()
