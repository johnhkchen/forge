# One idea in, one finished 3D object out. `just` lists everything.

set dotenv-load

default:
    @just --list

# Make an object from an idea: brief, picture, mesh, Blender
make idea:
    baml run make -- --idea "{{idea}}"

# Continue a stopped run at its first missing step
resume dir:
    baml run resume -- --dir "{{dir}}"

# Only the first step: show the brief Opus would write
brief idea:
    baml run -e 'Describe("{{idea}}")'

# Compile-check and run the offline tests
check:
    baml check
    baml test

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
