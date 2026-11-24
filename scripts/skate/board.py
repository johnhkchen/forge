"""The skateboard's numbers: what the builder builds and what the riding motion stands on.

    python3 scripts/skate/board.py          # writes world/props/skateboard.json

Everything is in the board's own frame, in metres: x toward the nose, y
toward the heel side (the rider's back, when he stands sideways on it with
his left foot in front), z up, and 0, 0, 0 is the middle of the top of the
deck, where the feet stand. The ground the wheels roll on is DECK_TOP below.

build_board.py makes world/props/skateboard.glb from these numbers;
ride.py puts the feet over the bolts and a grabbing hand on the edge from the
same ones, so the two cannot drift apart.

Plain Python: no Blender.
"""

from __future__ import annotations

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CARD = os.path.join(REPO, "world", "props", "skateboard.json")
GLB = os.path.join(REPO, "world", "props", "skateboard.glb")

LONG, WIDE, THICK = 0.81, 0.21, 0.012
KICK_FROM, KICK_DEG = 0.265, 20.0    # past this far from the middle the deck turns up: the kicktails
ROUND_FROM = 0.30                    # and from here the outline rounds in to the tip
TRUCK_X = 0.22                       # each truck's axle, from the middle
TRACK = 0.085                        # each wheel's middle, from the centre line
WHEEL_R, WHEEL_W = 0.027, 0.034
DECK_TOP = 0.115                     # the top of the deck above the ground it rolls on
BOLT_DX, BOLT_DY = 0.027, 0.021      # four bolts round each truck


def top_at(x: float) -> float:
    """How high the top of the deck is at x: flat between the kicktails, rising past them."""
    return max(0.0, abs(x) - KICK_FROM) * math.tan(math.radians(KICK_DEG))


def half_width_at(x: float) -> float:
    a = abs(x)
    if a <= ROUND_FROM:
        return WIDE / 2.0
    t = min(1.0, (a - ROUND_FROM) / (LONG / 2.0 - ROUND_FROM))
    return (WIDE / 2.0) * math.sqrt(max(0.0, 1.0 - 0.86 * t * t))


def bolts() -> list:
    return [(sx * TRUCK_X + dx, dy, 0.0) for sx in (1.0, -1.0) for dx in (BOLT_DX, -BOLT_DX) for dy in (BOLT_DY, -BOLT_DY)]


def wheels() -> list:
    """Where each wheel touches the ground: front left, front right, back left, back right ("left" is the toe side, -y)."""
    return [(sx * TRUCK_X, sy * TRACK, -DECK_TOP) for sx in (1.0, -1.0) for sy in (-1.0, 1.0)]


def card() -> dict:
    return {
        "format": "forge-skateboard/1",
        "about": "A skateboard, in its own frame: x toward the nose, y toward the heel side, z up, 0 at the middle of the top of the deck. Metres.",
        "glb": "world/props/skateboard.glb",
        "long_m": LONG, "wide_m": WIDE, "deck_top_m": DECK_TOP, "wheelbase_m": 2.0 * TRUCK_X,
        "feet": {"front": [TRUCK_X - 0.005, 0.0, 0.0], "back": [-(TRUCK_X + 0.035), 0.0, 0.0], "about": "the middle of each foot: the front one over the front bolts, the back one just behind the back bolts, on the tail"},
        "bolts": [[round(c, 4) for c in b] for b in bolts()],
        "wheels_touch": [[round(c, 4) for c in w] for w in wheels()],
        "grabs": {
            "toe_edge": [0.0, -WIDE / 2.0, 0.0],
            "heel_edge": [0.0, WIDE / 2.0, 0.0],
            "nose": [LONG / 2.0 - 0.06, 0.0, round(top_at(LONG / 2.0 - 0.06), 4)],
            "tail": [-(LONG / 2.0 - 0.06), 0.0, round(top_at(LONG / 2.0 - 0.06), 4)],
        },
    }


def main() -> None:
    os.makedirs(os.path.dirname(CARD), exist_ok=True)
    with open(CARD, "w") as f:
        json.dump(card(), f, indent=1)
        f.write("\n")
    print("BOARD wrote", os.path.relpath(CARD, REPO))


if __name__ == "__main__":
    main()
