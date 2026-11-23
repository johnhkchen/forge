#!/usr/bin/env bash
# Creates the GEM-X serverless endpoint on RunPod (REST API v2): motion from a
# video, for `just video`.
#
# Scales to zero: no workers run, and nothing is billed, until a job arrives.
#
# A 24 GB GPU (RTX 4090 class). GEM-X's three models together hold about 7 GB
# of weights, and nothing here is built for one exact GPU, so any 24 GB card
# would do; the 4090 pool is the one our other endpoints already use.
#
# One worker at most: two first boots would fetch the same models onto the
# shared volume at once, and a clip is uploaded in parts that have to land on
# the same disk.
#
# The network volume is the one the other endpoints use. GEM-X adds about
# 7.5 GB to it (the weights 7.1 GB, the person detector 0.4 GB, the SOMA body
# and GEM-X's code a little), plus the clips you send, which are deleted after
# two weeks unused.
#
# initTimeout is 20 minutes because the very first worker fetches all of that
# before it is ready. Jobs time out after 30 minutes: the first `motion` job
# also loads the models onto the GPU, and a long shot takes a while.
#
# HF_TOKEN comes from the RunPod secret `hf_token` (Settings -> Secrets), the
# same one the other endpoints use. Nothing GEM-X needs is gated today; the
# token is only there in case that changes.
set -euo pipefail
: "${RUNPOD_API_KEY:?set RUNPOD_API_KEY in .env}"
: "${RUNPOD_VOLUME_ID:?set RUNPOD_VOLUME_ID in .env}"
: "${GEMX_IMAGE:?set GEMX_IMAGE in .env}"

body=$(cat <<JSON
{
  "name": "gemx",
  "type": "QUEUE",
  "image": "${GEMX_IMAGE}",
  "gpu": { "pools": ["ADA_24"], "count": 1, "minCudaVersion": "12.6" },
  "workers": { "min": 0, "max": 1, "idleTimeout": 60, "initTimeout": 1200 },
  "scaling": { "type": "QUEUE_DELAY", "queueDelay": 4 },
  "dataCenterIds": ["EU-RO-1"],
  "mounts": { "network": [{ "volumeId": "${RUNPOD_VOLUME_ID}" }] },
  "flashboot": "FLASHBOOT",
  "timeout": 1800000,
  "disk": 20,
  "env": { "HF_TOKEN": "{{ RUNPOD_SECRET_hf_token }}" }
}
JSON
)

curl -sS -X POST https://api.runpod.io/v2/serverless \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "${body}"
echo
echo "Put the endpoint's id in .env as GEMX_ENDPOINT_ID."
