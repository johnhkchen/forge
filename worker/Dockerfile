# TRELLIS.2 (image -> textured GLB) as a RunPod Serverless worker.
#
# Nothing compiles here: the CUDA extensions come as prebuilt wheels for
# CUDA 12.4 + torch 2.6 + Python 3.11, so the image builds without a GPU in a
# few minutes (RunPod's GitHub builder or GitHub Actions both work).
# Weights are NOT baked in. They live on the network volume (see handler.py).
#
# Targets Ampere/Ada/Hopper (A100, 4090, L40S, H100). Blackwell (50xx, RTX PRO)
# needs a cu128+ stack and is not supported by this image.

FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-devel

ARG TRELLIS_COMMIT=75fbf01
ARG WHEELS=https://github.com/PozzettiAndrea/cuda-wheels/releases/download

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    OPENCV_IO_ENABLE_OPENEXR=1 \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    ATTN_BACKEND=flash_attn \
    HF_HOME=/runpod-volume/hf_cache \
    PYTHONPATH=/app/trellis

RUN apt-get update \
 && apt-get install -y --no-install-recommends git libjpeg-dev libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# TRELLIS.2's own Python dependencies (setup.sh --basic, minus gradio and
# training-only tools). transformers 5.x breaks DINOv3 (TRELLIS.2 issue #147).
RUN pip install --no-cache-dir \
      imageio imageio-ffmpeg tqdm easydict opencv-python-headless ninja trimesh \
      "transformers==4.57.3" zstandard kornia timm lpips pandas \
      "git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8" \
      "runpod>=1.7" "huggingface_hub>=0.34"

# flash-attn from its official release, matching torch's C++ ABI.
RUN ABI=$(python -c "import torch; print('TRUE' if torch._C._GLIBCXX_USE_CXX11_ABI else 'FALSE')") \
 && pip install --no-cache-dir \
      "https://github.com/Dao-AILab/flash-attention/releases/download/v2.7.3/flash_attn-2.7.3+cu12torch2.6cxx11abi${ABI}-cp311-cp311-linux_x86_64.whl"

# TRELLIS.2's CUDA extensions, prebuilt (github.com/PozzettiAndrea/cuda-wheels).
RUN pip install --no-cache-dir \
      "${WHEELS}/cumesh-latest/cumesh-0.0.1%2Bcu124torch2.6-cp311-cp311-manylinux_2_35_x86_64.whl" \
      "${WHEELS}/o_voxel-latest/o_voxel-0.0.1%2Bcu124torch2.6-cp311-cp311-manylinux_2_34_x86_64.manylinux_2_35_x86_64.whl" \
      "${WHEELS}/flex_gemm-latest/flex_gemm-1.0.0%2Bcu124torch2.6-cp311-cp311-manylinux_2_34_x86_64.manylinux_2_35_x86_64.whl" \
      "${WHEELS}/nvdiffrast-latest/nvdiffrast-0.4.0%2Bcu124torch2.6-cp311-cp311-manylinux_2_34_x86_64.manylinux_2_35_x86_64.whl"

# The TRELLIS.2 source itself, pinned.
RUN git clone https://github.com/microsoft/TRELLIS.2.git /tmp/trellis \
 && git -C /tmp/trellis checkout ${TRELLIS_COMMIT} \
 && mkdir -p /app/trellis \
 && cp -r /tmp/trellis/trellis2 /app/trellis/ \
 && rm -rf /tmp/trellis

# Fail the build early if the Python side is broken. (Importing flex_gemm or
# o_voxel needs a GPU driver for Triton, so only check that they are installed.)
RUN python -c "import torch, transformers, flash_attn, runpod, trimesh; print('torch', torch.__version__, 'cuda', torch.version.cuda)" \
 && python -c "import importlib.util as u; missing=[m for m in ('cumesh','o_voxel','flex_gemm','nvdiffrast','trellis2') if u.find_spec(m) is None]; assert not missing, missing"

COPY handler.py /app/handler.py
WORKDIR /app
CMD ["python", "-u", "handler.py"]
