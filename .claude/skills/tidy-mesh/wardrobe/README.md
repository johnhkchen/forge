# The wardrobe template

One body that every character can wear under its own head, so clothes painted
for one fit all of them. `wrap.py` lays it on a character; `paint.py` paints
skin-tight clothes into its texture; `rig.py` gives it its own weights.

| File | What it is |
|---|---|
| `headless-1.0.glb` | What the tools read. Triangles, with a note saying which pairs were quads, so `wrap.py` puts the quads back exactly. |
| `headless-1.0.blend` | The same body to keep modeling: real quads, the face attribute `region`, a vertex group per bone. |

The body: a person in a T-pose, 1.8 m, feet on z = 0, facing -y, cut off at a
ring round the neck (the collar: 40 edges at 81% of the height). 3,722 points,
3,742 faces (3,660 quads, 82 triangles; 7,402 triangles in a file). One
texture layout, every part at the same density. Each face knows its part of
the body (`region`: upper arm, lower leg and so on). Each point has weights
for rig.py's bones (the same names), at most four bones a point.

## License

The mesh is derived from the MakeHuman base mesh (`base.obj`), which the
MakeHuman project released as **CC0 1.0** (public domain dedication) in
September 2020: <https://creativecommons.org/publicdomain/zero/1.0/>.

Only that mesh's data is used: its points, faces, texture layout and the
joint markers that ship inside the same file. No MakeHuman code, targets,
skins, textures or other assets are used or included. The template built
from it here is released the same way, CC0 1.0.

## How it was made

1. The base mesh's body, in meters, feet on the floor. Its joint markers gave
   a plain skeleton (rig.py's bone names); Blender's automatic weights were
   made on it once, on the clean closed body, where they work well.
2. Its A-pose arms were turned out into a T-pose with those weights.
3. Each face got its `region` from the weights.
4. The head was cut off at the closed ring of edges nearest 40% of the way
   from the neck joint to the head joint. A character keeps its own head.
5. It was made lighter by dissolving whole edge loops, densest first, so it
   stays quads in clean loops (hands and feet are left finer).
6. The texture layout's pieces were set to one density and packed again.

To write the .glb again after changing the .blend:

    blender -b --factory-startup -P scripts/wardrobe/template_glb.py -- \
      .claude/skills/tidy-mesh/wardrobe/headless-1.0.blend \
      .claude/skills/tidy-mesh/wardrobe/headless-1.0.glb

It reads the file back the way `wrap.py` does and stops if the faces, the
layout, the regions or the weights came back any different.

A new shape or a new layout is a new template: give it a new name
(`headless-1.1`), because outfits painted for one layout do not fit another.
