# Forge

Type an idea, get a finished 3D object: a cleaned-up mesh, a `.blend` file, and a render.

```
just make "a brass diving helmet"
```

## What happens

Each AI does the part it's good at:

1. **Opus writes a short brief.** It picks one object, describes it in a few sentences, and lists its materials and real-world size. (`baml_src/1_describe`)
2. **Codex draws it.** You get one object, centered, on a plain gray background, which is the kind of picture image-to-3D handles well. (`baml_src/2_picture`)
3. **TRELLIS.2 turns the picture into a textured mesh.** It runs on your own RunPod endpoint, which scales to zero, so it costs nothing while idle and has no daily cap. (`baml_src/3_mesh`, `worker/`)
4. **Claude finishes it in Blender.** It fixes orientation, size, origin and normals, sets the materials, adds a ground plane, lights and a camera, then renders, checking its own work against the picture as it goes. Then it marks out the object's parts (lid, knob, spout...) and builds a low-poly version from simple shapes; a character's face is measured off the detailed head first, so it keeps its brow, eyes, nose and mouth, and its clothes and armor are built as separate pieces over a whole body, so a game can take them off. The work that repeats in every run (bringing the mesh in, measuring a part, staging, exporting) is done by ready-made scripts Claude fills in, not rewritten each time. (`baml_src/4_polish`, `.claude/skills/tidy-mesh`)
5. **Sized versions for wherever it's going.** A background Blender rebuilds the mesh as clean quads and bakes the detail into textures, once per profile (`web`, `game` and `lowpoly` by default; a character also gets `midpoly`). (`baml_src/5_profiles`, `.claude/skills/tidy-mesh`)
   A character's low-poly and mid-poly versions then learn to walk: bones placed from its own shape, joints that stop where a body's do, and a walk worked out from its leg length and bulk, plus one question to Opus about how it carries itself. The troll lumbers; the ninja creeps. (`baml_src/7_walk`)
6. **Props, if you ask.** A character is drawn and built with empty hands. With `props=held`, each thing it carries (an umbrella, a sword) gets a brief of its own and goes through the same steps as a small object, and the character's folder notes which hand it goes in. (`baml_src/6_props`)

The whole pipeline is BAML (the new language, toolchain pinned in `baml.toml`). Steps 1 and 4 go through the `claude` CLI and step 2 through the `codex` CLI, so they use your subscriptions, not metered API keys.

Every run gets its own folder, `runs/<time>-<name>/`:

| File | From |
|---|---|
| `brief.json` | step 1 |
| `image.png` | step 2 |
| `mesh.glb`, `mesh.json` | step 3 (raw TRELLIS.2 output, plus timings) |
| `render.png`, `final.glb`, `scene.blend`, `polish.json` | step 4 |
| `parts.json`, `lowpoly.glb`, `lowpoly.json`, `lowpoly_build.json` | step 4 (the parts, the low-poly block-out, and the recipe it was built from) |
| `profiles/<profile>.glb`, `.png`, `-wire.png`, `.json` | step 5 |
| `gait.json`, `profiles/lowpoly-walk.glb`, `profiles/midpoly-walk.glb` (each with a `.json`) | step 5, characters: how it walks, and the two versions with a skeleton and a walk |
| `props.json` | step 6 (which prop goes where, and the folder each one was made in) |

A step is skipped if its file is already there, so `just resume runs/<folder>` picks up where a run stopped.

## Setup

You need the `baml`, `claude`, `codex`, `uv`, `gh` and `just` CLIs, and Blender. Run `just autoremesher` once for the quad profiles, and `just forge-addon` once (then restart Blender) so Claude's Blender tools are one-liners.

1. **Blender add-on (one time).** Run `just blender-addon`, then `just blender`. The add-on starts its server whenever Blender opens.
2. **TRELLIS.2 worker image.** Push this repo to GitHub. `.github/workflows/worker.yml` builds `worker/` into `ghcr.io/<you>/trellis2-worker`. It only installs prebuilt wheels, so the build is quick and needs no GPU.
3. **RunPod.**
   - Copy `.env.example` to `.env` and fill in your API key and the EU-RO-1 network volume ID.
   - Add a RunPod secret `hf_token`. The DINOv3 image encoder is gated on Hugging Face, so your account needs access to it.
   - Run `just endpoint` and put the new endpoint's ID in `.env`.
4. Run `just check`, then `just make "…"`.

The first job on a fresh endpoint downloads whichever weights the volume doesn't already have, about 17 GB at most. After that, a job takes about a minute on an RTX 4090.

## Commands

| | |
|---|---|
| `just make "<idea>"` | the whole pipeline |
| `just make "<idea>" held` | the same, and then each thing the character carries as an object of its own (`all` adds hats, backpacks and the like) |
| `just resume <run folder>` | continue a stopped run (`just resume <run folder> held` to add its props) |
| `just props <run folder>` | only write the briefs for a finished character's props; `just resume` each prop's folder to make it |
| `just brief "<idea>"` | only step 1, to try ideas |
| `just check` | compile and run the offline tests |
| `just health` | is the RunPod endpoint up? |
| `just tidy <run folder> <profile>…` | make sized versions: `hero`, `quads`, `web`, `game`, `mobile`, `midpoly`, `lowpoly` |
| `just tidy <run folder> walk` | give a character's low-poly and mid-poly versions a skeleton and a walk |
| `just gait <run folder>` | only ask Opus how the character walks (weight, stealth, swagger, stiffness) |
| `just walk-strip <file.glb> <out.png> [side or front]` | a picture of the walk, eight moments side by side |
| `just recipe <run folder>` | for a run from before recipes were kept: get its block-out's recipe back from the transcript, so `midpoly` can be made |
| `just gallery` | look at every object, raw vs cleaned-up, on this Mac or a phone on the same Wi-Fi |
| `just transcript <run folder> <step>` | read the Blender code Claude ran in a step (`polish`, `parts`, `lowpoly`) |
| `just test-tools` | try the Blender scripts on real runs in a background Blender (your open Blender is left alone) |
| `just check-safe` | check that the Blender scripts will get past the add-on's safe mode |

## Profiles

TRELLIS.2 hands back an even soup of ~300k triangles. The `tidy-mesh` skill (`.claude/skills/tidy-mesh/`) turns it into what a modeler would hand over: real parts only, quads that follow the form, and materials baked into textures a GLB can carry.

| Profile | For | Mesh | Textures |
|---|---|---|---|
| `hero` | close-up renders, printing | 200k triangles, cleaned | 2048 |
| `quads` | keep modeling it | ~15k quads | 2048 + normal map |
| `web` | web pages, product viewers | ~8k quads, Draco | 1024 WebP + normal map |
| `game` | real-time games | ~4k quads, Draco | 1024 WebP + normal map |
| `mobile` | phones, AR | ~3k quads, Draco | 512 WebP + normal map |
| `midpoly` | phone games on today's hardware | the low-poly pieces built again rounder and smooth, about 3,000 to 8,000 triangles, Draco | 1024 WebP + normal map |
| `lowpoly` | old-school real-time look (think early Warcraft or RuneScape) | a few hundred to ~1,500 triangles, built by Claude from simple shapes | one 256 px texture with shading painted in, or flat colors per part when the style asks |

The quads come from [AutoRemesher](https://github.com/huxingyi/autoremesher) (MIT): mostly rectangular faces in regular loops, a little denser where the shape curves. Install it once with `just autoremesher`. Each profile records how far it strays from the full mesh (`shape` in `<profile>.json`); typically under 1% of the object's size.

## Gear comes off

A game needs the pirate without his hat, or in different boots. So on the two versions Claude builds from simple shapes (`lowpoly` and `midpoly`), a character is not one lump:

- **The brief lists the gear**: every piece of clothing, armor and equipment, each marked as worn, attached (a hat, a backpack) or held.
- **The body is built whole.** Take the coat off and there is a chest under it, not a hole.
- **Each gear item is its own mesh in the file**, named `gear: navy coat`, `gear: boots`..., next to `body`, and tagged with its kind and where it goes. Hide one, or swap in another.
- **Five named points say where props attach**: `socket: hand_right`, `socket: hand_left`, `socket: head`, `socket: back`, `socket: hip`.
- **Things carried in a hand are never part of the character.** They are made as objects of their own when you ask (`just make "<idea>" held`), and `props.json` says which hand each goes in.

In the gallery, a character's Low poly and Mid poly versions have a row of its gear (tap a piece to take it off) and a "Where props go" button.

## Walking

Those two versions also come with a skeleton and a walk (`profiles/lowpoly-walk.glb`, `midpoly-walk.glb`): 21 bones with plain names (`hips`, `thigh_l`, `forearm_r`...), a few more for a tail, each joint with its limits written in the file. Gear pieces follow the same bones and the prop points ride on them. The walk is worked out from the model, not drawn by hand, so each character gets its own. In the gallery, press "Walk" to see it on the spot. `.claude/skills/tidy-mesh/bones.json` says what each bone is called in SOMA (NVIDIA MotionBricks) and Mixamo, for bringing in motion from elsewhere later.

The detailed versions (`hero`, `quads`, `web`, `game`, `mobile`) still have the clothes as part of the body. They come from the picture, and the picture shows the character dressed.

In a Claude Code session here, ask for any of these ("make a game version of the kettle") and Claude uses the skill, either in the background or step by step in your open Blender.
