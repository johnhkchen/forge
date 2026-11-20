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

blender_bin := env_var_or_default("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")

# Make tidy-mesh profiles of a finished run, in a background Blender (hero quads web game mobile)
tidy run +profiles:
    #!/usr/bin/env bash
    set -euo pipefail
    src="{{run}}/scene.blend"; [ -f "$src" ] || src="{{run}}/mesh.glb"
    "{{blender_bin}}" -b --factory-startup -P scripts/tidy_profile.py -- "$src" "{{run}}/profiles" {{profiles}} 2>&1 | grep -E '^PROFILE|Error|Traceback'

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
