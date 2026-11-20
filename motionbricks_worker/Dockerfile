# NVIDIA MotionBricks (poses in, motion out) as a RunPod Serverless worker.
#
# This image holds only our handler and the Python packages MotionBricks runs
# on. Nothing of NVIDIA's MotionBricks release is baked in: not its code, not
# its model, not its sample clips. On its first boot the worker fetches the
# pinned release (v0.2.0) onto the network volume itself; see handler.py.
#
# TensorRT 10.8 builds a plan for the exact GPU it runs on, so the endpoint
# uses one GPU type (RTX 4090) and keeps the plan on the volume.

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/opt/venv/bin:$PATH \
    VIRTUAL_ENV=/opt/venv

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git git-lfs \
 && rm -rf /var/lib/apt/lists/* \
 && git lfs install --system --skip-smudge

# MotionBricks needs Python 3.12; Ubuntu 22.04 ships 3.10, so uv brings its own.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
RUN uv venv --seed --python 3.12 /opt/venv

# The packages MotionBricks' engine imports (its pyproject pins), minus the
# viewer (newton, pyglet, imgui). TensorRT's wheels live on NVIDIA's index.
RUN python -m pip install --extra-index-url https://pypi.nvidia.com \
      "warp-lang>=1.17.0" \
      "numpy==2.4.3" \
      "scipy==1.17.1" \
      "usd-core==26.3" \
      "tensorrt-cu12-bindings==10.8.0.43" \
      "tensorrt-cu12-libs==10.8.0.43" \
      "runpod>=1.7"

# Fail the build early if the Python side is broken. (TensorRT's own library
# may want a GPU driver to load, so only check that it is installed.)
RUN python -c "import numpy, scipy, runpod, warp; from pxr import Usd, UsdSkel; print('numpy', numpy.__version__, 'warp', warp.__version__)" \
 && python -c "import importlib.util as u; missing=[m for m in ('tensorrt','tensorrt_libs') if u.find_spec(m) is None]; assert not missing, missing"

COPY handler.py /app/handler.py
WORKDIR /app
CMD ["python", "-u", "handler.py"]
