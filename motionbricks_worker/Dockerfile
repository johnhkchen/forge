# The motion worker for RunPod Serverless. Today it holds one model, NVIDIA
# MotionBricks (poses in, the motion between them out).
#
# Each model gets a Python environment of its own under /opt/envs/, and the
# router that answers RunPod gets another, so one model's packages never have
# to agree with another's. To add a model: one more environment here, one more
# file in models/, two lines in handler.py.
#
# This image holds only our code and the Python packages the models run on.
# Nothing of NVIDIA's MotionBricks release is baked in: not its code, not its
# model, not its sample clips. On its first boot the worker fetches the pinned
# release (v0.2.0) onto the network volume itself; see
# models/motionbricks_model.py.
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

COPY handler.py /app/handler.py
COPY models /app/models
WORKDIR /app
CMD ["/opt/envs/router/bin/python", "-u", "handler.py"]
