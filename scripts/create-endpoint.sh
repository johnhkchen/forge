#!/usr/bin/env bash
# Creates the TRELLIS.2 serverless endpoint on RunPod (REST API v2).
#
# Scales to zero: no workers run, and nothing is billed, until a job arrives.
# RTX 4090 first, A100 as a fallback: the two Ampere/Ada cards EU-RO-1 has
# (the volume's datacenter; workers must run where the volume is).
#
# One worker at most: two first boots would download the same weights onto
# the shared volume at once. Raise it once the cache is warm if you need more.
#
# initTimeout is 30 minutes because the very first worker downloads ~17 GB of
# weights onto the volume before it is ready; later boots load from the volume.
#
# The DINOv3 image encoder is gated on Hugging Face, so the worker needs an
# HF token with access granted. Store it as a RunPod secret named `hf_token`
# (Settings -> Secrets) and it is passed in as HF_TOKEN.
set -euo pipefail
: "${RUNPOD_API_KEY:?set RUNPOD_API_KEY in .env}"
: "${RUNPOD_VOLUME_ID:?set RUNPOD_VOLUME_ID in .env}"
: "${TRELLIS_IMAGE:?set TRELLIS_IMAGE in .env}"

body=$(cat <<JSON
{
  "name": "trellis2",
  "type": "QUEUE",
  "image": "${TRELLIS_IMAGE}",
  "gpu": { "pools": ["ADA_24", "AMPERE_80"], "count": 1, "minCudaVersion": "12.4" },
  "workers": { "min": 0, "max": 1, "idleTimeout": 60, "initTimeout": 1800 },
  "scaling": { "type": "QUEUE_DELAY", "queueDelay": 4 },
  "dataCenterIds": ["EU-RO-1"],
  "mounts": { "network": [{ "volumeId": "${RUNPOD_VOLUME_ID}" }] },
  "flashboot": "FLASHBOOT",
  "timeout": 1800000,
  "disk": 30,
  "env": { "HF_HOME": "/runpod-volume/hf_cache", "HF_TOKEN": "{{ RUNPOD_SECRET_hf_token }}" }
}
JSON
)

curl -sS -X POST https://api.runpod.io/v2/serverless \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "${body}"
echo
echo "Put the endpoint's id in .env as TRELLIS_ENDPOINT_ID."
