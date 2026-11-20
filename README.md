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
4. **Claude finishes it in Blender.** It fixes orientation, size, origin and normals, sets the materials, adds a ground plane, lights and a camera, then renders. It checks its own work against the picture as it goes. (`baml_src/4_polish`)

The whole pipeline is BAML (the new language, toolchain pinned in `baml.toml`). Steps 1 and 4 go through the `claude` CLI and step 2 through the `codex` CLI, so they use your subscriptions, not metered API keys.

Every run gets its own folder, `runs/<time>-<name>/`:

| File | From |
|---|---|
| `brief.json` | step 1 |
| `image.png` | step 2 |
| `mesh.glb`, `mesh.json` | step 3 (raw TRELLIS.2 output, plus timings) |
| `render.png`, `final.glb`, `scene.blend`, `polish.json` | step 4 |

A step is skipped if its file is already there, so `just resume runs/<folder>` picks up where a run stopped.

## Setup

You need the `baml`, `claude`, `codex`, `uv` and `just` CLIs, and Blender.

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
| `just resume <run folder>` | continue a stopped run |
| `just brief "<idea>"` | only step 1, to try ideas |
| `just check` | compile and run the offline tests |
| `just health` | is the RunPod endpoint up? |
