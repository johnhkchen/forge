# The motion worker for RunPod Serverless. It holds two models: NVIDIA
# MotionBricks (poses in, the motion between them out) and NVIDIA Kimodo
# (sentences in, motion out).
#
# Each model gets a Python environment of its own under /opt/envs/, and the
# router that answers RunPod gets another, so one model's packages never have
# to agree with another's. To add a model: one more environment here, one more
# file in models/, two lines in handler.py.
#
# This image holds only our code and the Python packages the models run on.
# Nothing of NVIDIA's is baked in: not MotionBricks' or Kimodo's code, not a
# model, not a sample clip, and not the text encoder Kimodo reads sentences
# with (Meta's Llama 3). On first use each model fetches its own pinned release
# onto the network volume; see models/motionbricks_model.py and
# models/kimodo_model.py.
#
# TensorRT 10.8 builds a plan for the exact GPU it runs on, so the endpoint
# uses one GPU type (RTX 4090) and keeps the plan on the volume.

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git git-lfs \
 && rm -rf /var/lib/apt/lists/* \
 && git lfs install --system --skip-smudge

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

# The router: only what it takes to answer RunPod.
RUN uv venv --seed --python 3.12 /opt/envs/router \
 && /opt/envs/router/bin/python -m pip install "runpod>=1.7" \
 && /opt/envs/router/bin/python -c "import runpod; print('runpod', runpod.__version__)"

# MotionBricks: Python 3.12 and the packages its engine imports (its
# pyproject's pins), minus the viewer (newton, pyglet, imgui). TensorRT's
# wheels live on NVIDIA's index.
RUN uv venv --seed --python 3.12 /opt/envs/motionbricks \
 && /opt/envs/motionbricks/bin/python -m pip install --extra-index-url https://pypi.nvidia.com \
      "warp-lang>=1.17.0" \
      "numpy==2.4.3" \
      "scipy==1.17.1" \
      "usd-core==26.3" \
      "tensorrt-cu12==10.8.0.43" \
      "tensorrt-cu12-bindings==10.8.0.43" \
      "tensorrt-cu12-libs==10.8.0.43"

# Fail the build early if the Python side is broken. (TensorRT's own library
# may want a GPU driver to load, so only check that it is installed.)
RUN /opt/envs/motionbricks/bin/python -c "import numpy, scipy, warp; from pxr import Usd, UsdSkel; print('numpy', numpy.__version__, 'warp', warp.__version__)" \
 && /opt/envs/motionbricks/bin/python -c "import importlib.util as u; missing=[m for m in ('tensorrt','tensorrt_bindings','tensorrt_libs') if u.find_spec(m) is None]; assert not missing, missing"

# Kimodo: Python 3.10 and PyTorch, with the versions Kimodo's own lock file
# pins. On its first boot the worker compiles Kimodo's motion clean-up (C++),
# so the compiler, CMake and Eigen are here; pybind11 comes with pip.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential cmake libeigen3-dev \
 && rm -rf /var/lib/apt/lists/*
RUN uv venv --seed --python 3.10 /opt/envs/kimodo \
 && /opt/envs/kimodo/bin/python -m pip install --index-url https://download.pytorch.org/whl/cu124 "torch==2.5.1" \
 && /opt/envs/kimodo/bin/python -m pip install \
      "numpy==1.26.4" \
      "scipy==1.15.3" \
      "einops==0.8.2" \
      "hydra-core==1.3.2" \
      "omegaconf==2.3.0" \
      "transformers==5.1.0" \
      "peft==0.18.1" \
      "accelerate==1.13.0" \
      "huggingface-hub==1.6.0" \
      "hf-xet==1.4.0" \
      "safetensors==0.7.0" \
      "tokenizers==0.22.2" \
      "tqdm==4.67.3" \
      "pydantic==2.12.5" \
      "packaging==26.0" \
      "pybind11==2.13.6"

# Fail the build early if Kimodo's Python side is broken, or if a C++ Python
# extension cannot be built here the way the worker will build Kimodo's.
COPY build_check /tmp/build_check
RUN /opt/envs/kimodo/bin/python -c "import torch, numpy, scipy, einops, hydra, omegaconf, transformers, peft, safetensors, huggingface_hub; from scipy.spatial.transform import Rotation; print('torch', torch.__version__, 'transformers', transformers.__version__, 'hub', huggingface_hub.__version__)" \
 && mkdir /tmp/build_check/out && cd /tmp/build_check/out \
 && cmake /tmp/build_check -DPython3_EXECUTABLE=/opt/envs/kimodo/bin/python -Dpybind11_DIR="$(/opt/envs/kimodo/bin/python -m pybind11 --cmakedir)" -DCMAKE_BUILD_TYPE=Release \
 && cmake --build . -- -j4 \
 && /opt/envs/kimodo/bin/python -c "import _build_check; assert _build_check.trace_of_identity(3) == 3.0; print('a C++ extension builds and loads')" \
 && rm -rf /tmp/build_check

COPY handler.py /app/handler.py
COPY models /app/models
WORKDIR /app
CMD ["/opt/envs/router/bin/python", "-u", "handler.py"]
