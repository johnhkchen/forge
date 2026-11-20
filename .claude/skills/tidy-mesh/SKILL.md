---
name: tidy-mesh
description: Clean up, optimize, retopologize or resize a generated 3D mesh (TRELLIS.2 output or any messy GLB) in Blender. Use when asked to tidy a mesh, fix its topology, make it lighter or game/web/AR-ready, make LODs or quad topology, bake its materials or textures, or produce a named profile (hero, quads, web, game, mobile) of a finished object in runs/.
---

# tidy-mesh

Turns a raw generated mesh into something a 3D modeler would hand over: real
parts only, clean quad topology that follows the form, materials baked into
textures a GLB can carry, at the size the job needs.

## What is wrong with a raw TRELLIS.2 mesh

Measured on a real run (`runs/*-iron-kettle/mesh.glb`):

- **An even soup of ~300k triangles** with no edge loops. TRELLIS.2 builds the
  surface from voxels, so density ignores the form: flat sides get as many
  triangles as the lid rim.
- **It looks like 1,300 pieces with 42k open edges.** That is mostly glTF's
  fault: it splits vertices along every texture seam. Welding them (clean.py)
  reveals the real topology: a handful of parts (body, handle, lid knob…)
  plus a few floating specks and a few dozen non-manifold edges.
- **Materials are one baked atlas** (base color plus metallic/roughness) with
  lighting partly baked in. Metallic is often wrong across the whole object.
- **Size is normalized to about 1 m**; the real size comes from the brief.
- **Shader-node fixes don't survive export.** Anything done with color ramps,
  mixes or bump nodes in Blender is dropped by the GLB exporter unless baked
  (bake.py, mode "materials").

## Profiles: pick by what the object is for

| Profile | For | Mesh | Textures | Shape error, typical / worst (kettle) |
|---|---|---|---|---|
| `hero` | close-up renders, printing | cleaned, 200k triangles | 2048, materials baked | — |
| `quads` | keep modeling it | ~15k adaptive quads | 2048 + normal map | 0.26% / 2.4% |
| `web` | web pages, product viewers | ~8k adaptive quads, Draco | 1024 WebP + normal map | 0.36% / 2.4% |
| `game` | real-time games | ~4k adaptive quads | 1024 + normal map | 0.51% / 2.2% |
| `mobile` | phones, AR | ~3k adaptive quads, Draco | 512 WebP + normal map | 0.89% / 2.7% |

**What a good result looks like.** Mostly rectangular quads (~99%) in
regular loops (most vertices with four edges), a little denser where the
shape curves (spout, knob, rims) and larger on flat areas. That is normal,
editable modeling topology. We do not chase the last percent of shape error
with exotic geometry: slivers and triangle fans are harder to edit than a
tip that is a millimetre short. The worst spot on the kettle (~2.4%) is
where the handle's metal straps tuck into the handle, which barely shows.

**How:** the light profiles use AutoRemesher (MIT,
github.com/huxingyi/autoremesher, `just autoremesher` installs it into
`tools/`), which sizes quads to the curvature (`adaptivity`). It runs only in
the background runner, not over MCP. Its quad target is a starting point, so
the runner re-runs it until the count is within 10%. Without it installed,
profiles fall back to `retopo.py` (QuadriFlow: even quad size, so thin tips
come out a quad short) and say so in `<profile>.json`. Below ~3k quads the
thin handle brackets start to break up on an object like the kettle.

Not used, and why (researched Nov 2026): shape-aware triangle decimation
(faithful but slivers, hard to edit); QuadWild (prebuilt only as a 2023
build); Exoside Quad Remesher (licence forbids automated use); open AI
"artist mesh" models (triangles only, drop small parts); cloud retopology
(Tencent Smart Topology, Meshy remesh) is a possible future comparison.

## Parts: remesh the pieces a modeler would build separately

TRELLIS.2 fuses touching parts into one surface: the kettle's lid, knob and
spout are one piece with its body, which is 93% of the mesh. One remesh over
all of it makes every part share one quad layout. Nothing in the mesh says
where a part ends (we tried cutting along creases: TRELLIS blends the joins
too softly), so someone who knows what the object is has to say.

That's Claude, in pipeline step 4b (`FindParts`, in `baml_src/4_polish`): in
a "Parts" scene of the live Blender it places one axis-aligned box per part,
checks them with `split.py` in "color" mode and `look`, and saves the boxes
as `runs/<run>/parts.json`. The profile runner then cuts with `split.py`
("split" mode: each part becomes its own piece, its cut opening capped
inside the joint) and remeshes every piece on its own budget, which grows
with area^0.75 so thin parts aren't starved. Delete `parts.json` to go back
to one remesh; `just resume` asks Claude again.

To do it by hand in the live Blender: run `split.py` in "color" mode with
your boxes, `look`, adjust, then write the boxes to `parts.json`
(`{"parts": [{"name", "why", "min", "max"}], "notes"}`).

## Run a profile (default: in the background)

Heavy steps (retopology, baking) lock Blender's window while they run, so by
default run them in a separate background Blender, which never touches the
person's open session:

```
just tidy runs/<run folder> web game        # one or more profiles
just tidy runs/<run folder> hero quads web game mobile
```

Each profile's `<profile>.json` records `shape` (from match.py): how far the
light mesh strays from the full one. Read it, not just the previews.

This reads the run's `scene.blend` (with Claude's material fixes; falls back
to `mesh.glb`) and writes into `runs/<run>/profiles/`: `<profile>.glb`,
`<profile>.blend` (GLB can only store triangles, so the real quads live
here), a preview `<profile>.png`, a wireframe preview `<profile>-wire.png`, and
`<profile>.json` with what every step did. About 10 s per profile, 20 s for
`quads`. **Always look at both previews** before saying a profile is good.

To show a result in the live Blender, import it over MCP
(`bpy.ops.import_scene.gltf(filepath=...)`): that is light.

## Work in the live Blender (when the person wants to watch or steer)

The scripts in `scripts/` are the same steps, written to be sent whole
through the blender MCP `execute_blender_code` tool. Read the file, edit the
`PARAMS` block at the top, send it, and read the `RESULT {json}` line it
prints. They use only bpy, bmesh, mathutils, math and json, so they pass the
add-on's safe mode.

| Script | Does | Cost in live Blender |
|---|---|---|
| `inspect.py` | measures everything below, changes nothing | instant |
| `clean.py` | welds seams, deletes specks and loose bits, closes small holes, fixes normals, smooth shading with sharp edges | ~2 s |
| `decimate.py` | shape-aware reduction to a triangle budget, keeping UVs; `as_copy` + `quadify` make a light "(light)" copy to bake onto | a few s |
| `match.py` | how far a light mesh strays from the full one, and where (both directions, % of size) | ~2 s |
| `retopo.py` | rebuilds each part as quads with QuadriFlow, on the part's own repaired surface when it can (voxel remesh only as a fallback for big parts), shrinkwrapped back onto the original; `routes` says which way each part went | 5–30 s, freezes Blender |
| `bake.py` | "materials": bakes the shader into plain textures; "onto": bakes color, metal, roughness and a normal map from the full mesh onto a lighter one | 5–60 s, freezes Blender |
| `export.py` | writes one object as GLB (WebP, Draco optional) | ~1 s |
| `preview.py` | renders a quick three-quarter PNG, optionally with wireframe | ~2 s |
| `split.py` | splits an object into named parts from one box per part ("color" mode just paints them, to check the boxes) | ~1 s |
| `lineup.py` | shows a run's raw mesh and its profiles side by side in a new "Profiles" scene, labelled, wireframe on | ~2 s |

Rules for the live session:

- **Every call freezes the person's Blender until it returns.** Warn before
  `retopo.py` or `bake.py`, or run them in the background instead.
- Check with `look` using shading `"material"` or `"solid"`; `"rendered"`
  runs Cycles and is slow.
- Order: `inspect` → `clean` → (`decimate` or `retopo`) → `match` → `bake`
  → `export`. Run `inspect` again after each step and compare.
- Judge shape with `match.py`: under ~0.5% worst error is invisible at
  normal distance; over ~1.5% shows in the silhouette.
- Keep the full mesh: `retopo.py` and `bake.py` hide it rather than delete it.

## Reading inspect.py

- `pieces` / `largest_pieces`: real separate parts after welding. A handle or
  lid can be its own part; specks are tiny in both share and size.
- `seam_split_vertices`: vertices glTF duplicated along seams. Not a defect;
  clean.py welds them.
- `non_manifold_edges`, `boundary_edges`: holes and tangles. Small numbers
  are normal for TRELLIS output; a mug's mouth is a legitimate boundary.
- `unapplied_transform`, `bottom_z`, `origin`: whether it is ready to place.
- `materials[].principled`: what is textured vs. a flat value, and whether
  there is a normal map.

## Known limits

- Thin straps and brackets are the weak spot at every size (~2.4% on the
  kettle's handle brackets); below ~3k quads they break up. Raise the
  profile's `quads` for objects with fine detail.
- In the live Blender (MCP) there is no AutoRemesher: `retopo.py` gives even
  QuadriFlow quads, which lose about one quad at thin tips. For adaptive
  quads, run the profile in the background and import the result.
- QuadriFlow refuses some parts that pass every manifold check we can run;
  retopo.py then falls back to a fine voxel remesh (big parts) or plain
  reduction (small parts) and says so in `routes`. The voxel route's error
  varies with `detail`; 450 measured steadiest.
- At very low budgets a bake can miss parts of the surface, which shows as
  black patches. bake.py widens its reach for coarse meshes; if patches
  remain, raise the budget.
- For close-up renders, `hero` (the cleaned dense mesh) stays the most
  faithful.

## Testing a script change

```
blender -b --factory-startup -P scripts/tidy_headless.py -- MESH.glb \
  .claude/skills/tidy-mesh/scripts/clean.py .claude/skills/tidy-mesh/scripts/inspect.py \
  --params '{"inspect.py": {}}'
```

runs scripts against a GLB with no live Blender. Re-run the five profiles on
the kettle run and compare previews before calling a change done.
