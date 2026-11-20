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

| Profile | For | Mesh | Textures |
|---|---|---|---|
| `hero` | close-up renders, printing | cleaned, 200k triangles | 2048, materials baked |
| `quads` | keep modeling it | ~20k quads, follows the form | 2048 + normal map |
| `web` | web pages, product viewers | ~8k quads, Draco-compressed | 1024 WebP + normal map |
| `game` | real-time games | ~4k quads | 1024 + normal map |
| `mobile` | phones, AR | ~2.5k quads, Draco | 512 WebP + normal map |

Profiles are defined in `profiles.json` (steps and their PARAMS); edit or add
one there rather than hand-running a different recipe each time.

## Run a profile (default: in the background)

Heavy steps (retopology, baking) lock Blender's window while they run, so by
default run them in a separate background Blender, which never touches the
person's open session:

```
just tidy runs/<run folder> web game        # one or more profiles
just tidy runs/<run folder> hero quads web game mobile
```

This reads the run's `scene.blend` (with Claude's material fixes; falls back
to `mesh.glb`) and writes into `runs/<run>/profiles/`: `<profile>.glb`, a
preview `<profile>.png`, a wireframe preview `<profile>-wire.png`, and
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
| `decimate.py` | reduces to a triangle budget, keeping UVs and textures | a few s |
| `retopo.py` | rebuilds each part as quads (voxel remesh, QuadriFlow, shrinkwrap back onto the original) | 5–20 s, freezes Blender |
| `bake.py` | "materials": bakes the shader into plain textures; "onto": bakes color, metal, roughness and a normal map from the full mesh onto a lighter one | 5–60 s, freezes Blender |
| `export.py` | writes one object as GLB (WebP, Draco optional) | ~1 s |
| `preview.py` | renders a quick three-quarter PNG, optionally with wireframe | ~2 s |

Rules for the live session:

- **Every call freezes the person's Blender until it returns.** Warn before
  `retopo.py` or `bake.py`, or run them in the background instead.
- Check with `look` using shading `"material"` or `"solid"`; `"rendered"`
  runs Cycles and is slow.
- Order: `inspect` → `clean` → (`decimate` or `retopo`) → `bake` → `export`.
  Run `inspect` again after each step and compare.
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

- QuadriFlow spreads quads evenly. Small features on a big part (a lid knob
  on the body) get few quads and turn faceted below ~5k quads. Raise
  `target_quads` or `detail` if that matters.
- Thin rims and lips (a spout's mouth) can tear; retopo.py closes the tears
  and reports `tears_closed`. Check the wireframe preview there.
- At very low budgets a bake can miss parts of the surface, which shows as
  black patches. bake.py widens its reach for coarse meshes; if patches
  remain, raise the quad budget.
- For close-up renders, `hero` (the cleaned dense mesh) stays more faithful
  than any retopology.

## Testing a script change

```
blender -b --factory-startup -P scripts/tidy_headless.py -- MESH.glb \
  .claude/skills/tidy-mesh/scripts/clean.py .claude/skills/tidy-mesh/scripts/inspect.py \
  --params '{"inspect.py": {}}'
```

runs scripts against a GLB with no live Blender. Re-run the five profiles on
the kettle run and compare previews before calling a change done.
