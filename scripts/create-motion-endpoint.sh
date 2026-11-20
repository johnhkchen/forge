#!/usr/bin/env bash
# Creates the MotionBricks serverless endpoint on RunPod (REST API v2).
#
# Scales to zero: no workers run, and nothing is billed, until a job arrives.
#
# RTX 4090 only. MotionBricks runs on a TensorRT plan, and a plan only works
# on the kind of GPU it was built on. The worker keeps the plan on the network
# volume, so every later boot on a 4090 loads it instead of building it again.
#
# One worker at most: two first boots would fetch the same model onto the
# shared volume at once.
#
# initTimeout is 20 minutes because the very first worker fetches the model
# (~760 MB) and builds the plan (minutes) before it is ready.
#
# A job itself takes seconds, but jobs time out after 30 minutes: Kimodo (text
# to motion) starts inside the first job that asks for it, and the first time
# ever that job also fetches 17.5 GB onto the volume.
#
# HF_TOKEN comes from the RunPod secret `hf_token` (Settings -> Secrets), the
# same one the TRELLIS.2 endpoint uses. Kimodo's text encoder is built on
# Meta's Llama 3, which is gated: that account must have been given access at
# https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct. MotionBricks
# needs no token.
set -euo pipefail
: "${RUNPOD_API_KEY:?set RUNPOD_API_KEY in .env}"
: "${RUNPOD_VOLUME_ID:?set RUNPOD_VOLUME_ID in .env}"
: "${MOTIONBRICKS_IMAGE:?set MOTIONBRICKS_IMAGE in .env}"

body=$(cat <<JSON
{
  "name": "motionbricks",
  "type": "QUEUE",
  "image": "${MOTIONBRICKS_IMAGE}",
  "gpu": { "pools": ["ADA_24"], "count": 1, "minCudaVersion": "12.4" },
  "workers": { "min": 0, "max": 1, "idleTimeout": 60, "initTimeout": 1200 },
  "scaling": { "type": "QUEUE_DELAY", "queueDelay": 4 },
  "dataCenterIds": ["EU-RO-1"],
  "mounts": { "network": [{ "volumeId": "${RUNPOD_VOLUME_ID}" }] },
  "flashboot": "FLASHBOOT",
  "timeout": 1800000,
  "disk": 15,
  "env": { "HF_TOKEN": "{{ RUNPOD_SECRET_hf_token }}" }
}
JSON
)

curl -sS -X POST https://api.runpod.io/v2/serverless \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "${body}"
echo
echo "Put the endpoint's id in .env as MOTIONBRICKS_ENDPOINT_ID."
