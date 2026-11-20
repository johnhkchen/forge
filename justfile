# One idea in, one finished 3D object out. `just` lists everything.

set dotenv-load

default:
    @just --list

# Make an object from an idea: brief, picture, mesh, Blender. props: none, held (what a character carries) or all (hats and backpacks too)
make idea props="none":
    baml run make -- --idea "{{idea}}" --props "{{props}}"

# Continue a stopped run at its first missing step (props as for make)
resume dir props="none":
    baml run resume -- --dir "{{dir}}" --props "{{props}}"

# Only write the briefs for a finished character's props (held, or all); `just resume` each prop's folder to make it
props dir wanted="held":
    baml run props -- --dir "{{dir}}" --wanted "{{wanted}}"

# Only the first step: show the brief Opus would write
brief idea:
    baml run -e 'Describe("{{idea}}")'

# Compile-check and run the offline tests
check:
    baml check
    baml test
    python3 scripts/motion/author_poses.py --check | tail -1
    python3 scripts/motion/test_timeline.py | tail -1
    python3 scripts/motion/test_run_clip.py | tail -1

# Would the Blender scripts get past the add-on's safe mode? (every skill script, or the files given)
check-safe *files:
    python3 scripts/check_safe.py {{files}}

# Try the Blender tools on real runs, in a background Blender (a few minutes; leaves the open Blender alone)
test-tools runs="runs":
    python3 scripts/test_tools.py "{{runs}}"

# Open Blender (the MCP add-on starts its server on launch)
blender:
    open -a Blender

# Install the MCP add-on into Blender (one time)
blender-addon:
    uvx --python 3.11 mcp-for-blender install-addon

# Create the TRELLIS.2 serverless endpoint on RunPod (one time)
endpoint:
    scripts/create-endpoint.sh

# Is the TRELLIS.2 endpoint up? (workers, queue)
health:
    curl -sS "https://api.runpod.ai/v2/$TRELLIS_ENDPOINT_ID/health" -H "Authorization: Bearer $RUNPOD_API_KEY"; echo

# Create the MotionBricks serverless endpoint on RunPod (one time)
motion-endpoint:
    scripts/create-motion-endpoint.sh

# Is the MotionBricks endpoint up? (workers, queue)
motion-health:
    curl -sS "https://api.runpod.ai/v2/$MOTIONBRICKS_ENDPOINT_ID/health" -H "Authorization: Bearer $RUNPOD_API_KEY"; echo

# Which MotionBricks worker answers, and how long it took to boot (starts one if none is up)
motion-info:
    baml run motion_info

# Prove the endpoint end to end: MotionBricks' own generate_once example, run on the worker
motion-selftest:
    baml run motion_selftest

# Fetch the SOMA skeleton from the worker into motion/soma_skeleton.json (one time)
motion-skeleton:
    baml run motion_skeleton

# Make a shot from its plan in motion/shots/<shot>.json: choreograph, place our poses, generate the motion (in pieces, if a beat is made from a sentence), measure it, film it
shoot shot="hero-rooftop":
    baml run shoot -- --shot "{{shot}}"

# Put a character in a finished shot: its skeleton, limits and planted feet, plus a prop on its sockets (writes into shots/<shot>/). clip names the cut: hero, or hero-mixed for a second cut
cast shot character prop="" clip="hero":
    baml run cast -- --shot "{{shot}}" --character "{{character}}" --prop "{{prop}}" --clip "{{clip}}"

# Copy a shot's clips into the character's own folder, so the gallery shows a Hero button for it (clip as for cast). Never writes over another cut's files
clip-to-gallery shot character clip="hero":
    #!/usr/bin/env bash
    set -euo pipefail
    for version in lowpoly midpoly; do
        for kind in glb json; do
            [ -f "shots/{{shot}}/$version-{{clip}}.$kind" ] && cp "shots/{{shot}}/$version-{{clip}}.$kind" "{{character}}/profiles/$version-{{clip}}.$kind"
        done
    done
    ls "{{character}}/profiles" | grep -- '-{{clip}}\.'

# What Kimodo (text to motion) has fetched onto the volume and loaded, with revisions and timings; the first call on a fresh volume is the one that fetches
text-info:
    baml run text_info

# Point the motion endpoint at another image tag (after the worker image is rebuilt)
motion-image tag:
    #!/usr/bin/env bash
    set -euo pipefail
    image="${MOTIONBRICKS_IMAGE%:*}:{{tag}}"
    curl -sS -X PATCH "https://api.runpod.io/v2/serverless/$MOTIONBRICKS_ENDPOINT_ID" \
      -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
      -d "{\"image\": \"$image\"}" | python3 -c "import sys, json; d = json.load(sys.stdin); print(d.get('id'), d.get('image'), 'version', d.get('version'))"

# Build the pose library (motion/poses.json) from scripts/motion/author_poses.py, checking every pose as a body
poses:
    python3 scripts/motion/author_poses.py

blender_bin := env_var_or_default("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")

# Make tidy-mesh profiles of a finished run, in a background Blender (hero quads web game mobile midpoly lowpoly; walk adds a skeleton and a walk to the last two; run adds a run, once `just runs` has made its clip)
tidy run +profiles:
    #!/usr/bin/env bash
    set -euo pipefail
    src="{{run}}/scene.blend"; [ -f "$src" ] || src="{{run}}/mesh.glb"
    "{{blender_bin}}" -b --factory-startup -P scripts/tidy_profile.py -- "$src" "{{run}}/profiles" {{profiles}} 2>&1 | grep -E '^PROFILE|Error|Traceback'

# Only ask Opus how a run's character walks (weight, stealth, swagger, stiffness); saves nothing
gait run:
    baml run how_it_walks -- --dir "{{run}}"

# A looping run for every character in a folder of runs (each one with a gait.json): one sentence each to Kimodo on the motion worker, cut into a loop, played on the low-poly and mid-poly versions. Says "run skipped: Kimodo not available" and stops cleanly if Kimodo can't be reached
runs dir="runs":
    baml run runs -- --dir "{{dir}}"

# Only show what each character would be asked to run like: its sentence and speed (sends nothing; writes run/ask.json and the request)
run-asks dir="runs":
    python3 scripts/motion/run_clip.py "{{dir}}"/*/ | grep -E '^RUN'

# Picture a walking .glb as a strip of poses (view: side, front or quarter)
walk-strip file out view="side":
    "{{blender_bin}}" -b --factory-startup -P scripts/walk_strip.py -- "{{file}}" "{{out}}" --view {{view}} 2>&1 | grep -E '^STRIP|Error|Traceback'

# Measure a dressed character's .glb (standing or walking): skin through its clothes over the clip, how far they sit off the body, cloth bones
cloth-check +files:
    "{{blender_bin}}" -b --factory-startup -P scripts/cloth_check.py -- {{files}} 2>&1 | grep -E '^CLOTH|Error|Traceback'

# For a run from before recipes were kept: rebuild its block-out from the transcript in a background Blender and save the recipe, so `just tidy <run> midpoly` works
recipe run:
    #!/usr/bin/env bash
    set -euo pipefail
    "{{blender_bin}}" -b --factory-startup -P scripts/replay_blockout.py -- "{{run}}" 2>&1 | grep -E '^REPLAY|^replay:'
    cp "{{run}}/replay/lowpoly_build.json" "{{run}}/lowpoly_build.json"

# Install AutoRemesher (MIT, adaptive quad remesher) into tools/ for the profiles (macOS)
autoremesher:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p tools/autoremesher-dl && cd tools/autoremesher-dl
    gh release download 1.2.0 -R huxingyi/autoremesher -p 'autoremesher-1.2.0.dmg' --clobber
    echo "4d3295fa2f87567e6b97a732afff511d82ec73a49825476038ce0997c641e9a7  autoremesher-1.2.0.dmg" | shasum -a 256 -c
    mnt=$(mktemp -d); hdiutil attach -nobrowse -readonly -mountpoint "$mnt" autoremesher-1.2.0.dmg >/dev/null
    rm -rf autoremesher.app; cp -R "$mnt/autoremesher.app" .; hdiutil detach "$mnt" >/dev/null
    ./autoremesher.app/Contents/MacOS/autoremesher --version

# Vendor the b28 clay style kit into the gallery
sync-kit:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p gallery/vendor
    curl -fsSL https://b28.dev/kit/b28-clay.css -o gallery/vendor/b28-clay.css
    grep -q -- '--clay-' gallery/vendor/b28-clay.css || { echo "sync-kit: not the b28 clay kit" >&2; exit 1; }
    echo "vendored gallery/vendor/b28-clay.css"

# Serve the gallery to this Mac and phones on the same Wi-Fi
gallery port="8028" runs="runs":
    python3 scripts/gallery.py --port {{port}} --runs "{{runs}}"

# Only brief, picture and mesh (leaves Blender alone); finish with `just resume`
mesh idea:
    baml run make_mesh -- --idea "{{idea}}"

# Show the Blender code Claude ran in a run's step (polish, parts, lowpoly)
transcript run step:
    python3 scripts/transcript.py "{{run}}" "{{step}}"

blender_startup := env_var("HOME") + "/Library/Application Support/Blender/5.2/scripts/startup"

# Install the Forge tools into Blender (restart Blender afterwards)
forge-addon:
    #!/usr/bin/env bash
    set -euo pipefail
    dir="{{blender_startup}}"
    mkdir -p "$dir/forge_tools"
    cp blender/forge_tools.py "$dir/forge_tools.py"
    rm -f "$dir/forge_tools/"*.py
    cp .claude/skills/tidy-mesh/scripts/*.py "$dir/forge_tools/"
    echo "Installed $(ls "$dir/forge_tools" | wc -l | tr -d ' ') tools into $dir. Restart Blender to load them."

# Remove the Forge tools from Blender
forge-addon-remove:
    rm -rf "{{blender_startup}}/forge_tools.py" "{{blender_startup}}/forge_tools"
