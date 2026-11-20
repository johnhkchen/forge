"""TRELLIS.2 on RunPod Serverless: one picture in, one textured GLB out.

Input (job["input"]):
    image             base64 PNG/JPEG of one object (background is removed here)
    seed              int, default 42
    pipeline_type     "512" | "1024" | "1024_cascade" | "1536_cascade", default "1024_cascade"
    decimation_target int, default 300000 triangles
    texture_size      int, default 2048

Output: a GLB is 10-30 MB, over RunPod's inline result limit, so the handler
is a generator and streams it. Poll /stream/{job_id} and you get, in order:
    {"kind": "info", "stage": "...", ...}           progress notes
    {"kind": "chunk", "index": i, "total": n, "data": "<base64>"}
    {"kind": "done", "bytes": N, "sha256": "...", "volume_path": "...", "seconds": {...}}
Join the chunks' data in index order, base64-decode, and check sha256.
A copy also stays on the network volume at volume_path.

Weights live on the network volume (mounted at /runpod-volume):
  - TRELLIS.2-4B and TRELLIS-image-large checkpoints are used from
    /runpod-volume/models/<org>/<repo>/ckpts/ when present (the layout the
    earlier ComfyUI setup left there), and otherwise fetched once into the
    Hugging Face cache at /runpod-volume/hf_cache.
  - DINOv3 (gated: needs HF_TOKEN with access granted) and BiRefNet are
    fetched once into the same cache.
Background removal uses ZhengPeng7/BiRefNet (MIT) instead of the pipeline's
default briaai/RMBG-2.0, which is licensed for non-commercial use only.
"""

import base64
import hashlib
import io
import json
import os
import time

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("ATTN_BACKEND", "flash_attn")
os.environ.setdefault("HF_HOME", "/runpod-volume/hf_cache")

VOLUME = os.environ.get("VOLUME_DIR", "/runpod-volume")
MODELS_DIR = f"{VOLUME}/models"
WORK_DIR = f"{VOLUME}/trellis2"
OUTPUT_DIR = f"{WORK_DIR}/outputs"
TRELLIS_REPO = "microsoft/TRELLIS.2-4B"
REMBG_MODEL = "ZhengPeng7/BiRefNet"
CHUNK_BYTES = 512 * 1024  # base64 grows it to ~700 KB, under /stream's 1 MB per item
PIPELINE_TYPES = {"512", "1024", "1024_cascade", "1536_cascade"}

os.makedirs(OUTPUT_DIR, exist_ok=True)
# FlexGEMM tunes its kernels on first use; keeping the result on the volume
# saves that work on every cold start (the official Space does the same).
os.environ.setdefault("FLEX_GEMM_AUTOTUNE_CACHE_PATH", f"{WORK_DIR}/flex_gemm_autotune.json")

import runpod  # noqa: E402
import torch  # noqa: E402
import o_voxel  # noqa: E402
from huggingface_hub import hf_hub_download  # noqa: E402
from PIL import Image  # noqa: E402
from trellis2.pipelines import Trellis2ImageTo3DPipeline  # noqa: E402


def model_path(name: str) -> str:
    """Where to load one checkpoint from: the volume's plain folder if both
    files are there, otherwise a hub path that TRELLIS fetches into HF_HOME.

    `name` is as written in pipeline.json: either "ckpts/x" (inside
    TRELLIS.2-4B) or "org/repo/ckpts/x" (another repo).
    """
    hub = name if name.count("/") >= 3 else f"{TRELLIS_REPO}/{name}"
    local = f"{MODELS_DIR}/{hub}"
    if os.path.exists(f"{local}.json") and os.path.exists(f"{local}.safetensors"):
        return local
    return hub


def write_config() -> str:
    """pipeline.json from the hub, rewritten to load each checkpoint from the
    volume when it can, and to use BiRefNet for background removal."""
    with open(hf_hub_download(TRELLIS_REPO, "pipeline.json")) as f:
        config = json.load(f)
    args = config["args"]
    args["models"] = {k: model_path(v) for k, v in args["models"].items()}
    args["rembg_model"]["args"]["model_name"] = REMBG_MODEL
    os.makedirs(WORK_DIR, exist_ok=True)
    with open(f"{WORK_DIR}/pipeline.json", "w") as f:
        json.dump(config, f, indent=2)
    print("[trellis2] checkpoints:", json.dumps(args["models"], indent=2), flush=True)
    return WORK_DIR


started = time.time()
# from_pretrained tries f"{dir}/{name}" first; our names are absolute paths
# or hub ids, so that fails cleanly and it falls back to loading the name.
PIPELINE = Trellis2ImageTo3DPipeline.from_pretrained(write_config())
PIPELINE.cuda()
LOAD_SECONDS = round(time.time() - started, 1)
print(f"[trellis2] pipeline ready in {LOAD_SECONDS}s on {torch.cuda.get_device_name(0)}", flush=True)


def generate(params: dict, out_path: str) -> dict:
    image = Image.open(io.BytesIO(base64.b64decode(params["image"])))
    pipeline_type = params.get("pipeline_type", "1024_cascade")
    if pipeline_type not in PIPELINE_TYPES:
        raise ValueError(f"pipeline_type must be one of {sorted(PIPELINE_TYPES)}")

    t0 = time.time()
    mesh = PIPELINE.run(image, seed=int(params.get("seed", 42)), pipeline_type=pipeline_type)[0]
    mesh.simplify(16777216)  # nvdiffrast's limit, as in TRELLIS.2's example.py
    t1 = time.time()
    glb = o_voxel.postprocess.to_glb(
        vertices=mesh.vertices,
        faces=mesh.faces,
        attr_volume=mesh.attrs,
        coords=mesh.coords,
        attr_layout=mesh.layout,
        voxel_size=mesh.voxel_size,
        aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
        decimation_target=int(params.get("decimation_target", 300000)),
        texture_size=int(params.get("texture_size", 2048)),
        remesh=True,
        remesh_band=1,
        remesh_project=0,
    )
    glb.export(out_path, extension_webp=True)
    t2 = time.time()
    del mesh
    torch.cuda.empty_cache()
    return {"generate": round(t1 - t0, 1), "export": round(t2 - t1, 1)}


def handler(job):
    params = job["input"]
    if "image" not in params:
        raise ValueError("input.image (base64 PNG or JPEG) is required")
    yield {"kind": "info", "stage": "generating", "gpu": torch.cuda.get_device_name(0)}

    volume_path = f"{OUTPUT_DIR}/{job['id']}.glb"
    seconds = generate(params, volume_path)
    seconds["load_at_boot"] = LOAD_SECONDS
    with open(volume_path, "rb") as f:
        data = f.read()

    total = (len(data) + CHUNK_BYTES - 1) // CHUNK_BYTES
    for index in range(total):
        chunk = data[index * CHUNK_BYTES : (index + 1) * CHUNK_BYTES]
        yield {"kind": "chunk", "index": index, "total": total, "data": base64.b64encode(chunk).decode()}
    yield {
        "kind": "done",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "volume_path": volume_path,
        "seconds": seconds,
    }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
