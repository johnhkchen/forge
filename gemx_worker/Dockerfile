# The video worker for RunPod Serverless. It holds one model, NVIDIA GEM-X,
# which reads a person's full-body motion off ordinary video and writes it on
# the SOMA skeleton our other motion models use.
#
# Like the motion worker (motionbricks_worker/), the model gets a Python
# environment of its own under /opt/envs/, and the router that answers RunPod
# gets another.
#
# This image holds only our code and the Python packages the model runs on.
# Nothing of the model's is baked in: not GEM-X's code, not its weights, not
# the YOLOX person detector, not the SOMA body, and no sample film. On its
# first boot the worker fetches each at a pinned revision onto the network
# volume; see models/gemx_model.py. (py-soma-x, from PyPI, is SOMA's code
# only; the body it needs is one of the things fetched.)

FROM nvidia/cuda:12.6.3-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# git fetches GEM-X's code on first boot; the two libraries are what OpenCV's
# wheel asks of the system.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git libglib2.0-0 libgomp1 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

# The router: only what it takes to answer RunPod.
RUN uv venv --seed --python 3.12 /opt/envs/router \
 && /opt/envs/router/bin/python -m pip install "runpod>=1.7" \
 && /opt/envs/router/bin/python -c "import runpod; print('runpod', runpod.__version__)"

# GEM-X: Python 3.12, PyTorch 2.10 or newer (its setup.cfg), and the packages
# its inference imports, with its own pins. onnxruntime-gpu runs the person
# detector on the GPU, using the CUDA and cuDNN libraries PyTorch brings.
RUN uv venv --seed --python 3.12 /opt/envs/gemx \
 && /opt/envs/gemx/bin/python -m pip install --index-url https://download.pytorch.org/whl/cu126 "torch>=2.10,<2.12" \
 && /opt/envs/gemx/bin/python -m pip install \
      "transformers==5.3.0" \
      "py-soma-x==0.3.3" \
      "numpy>=1.26,<3" \
      "scipy>=1.11,<2" \
      "einops>=0.8,<1" \
      "pillow>=10,<13" \
      "opencv-python-headless>=4.10,<5" \
      "omegaconf>=2.3,<2.4" \
      "onnxruntime-gpu>=1.21,<2" \
      "huggingface-hub>=1.6" \
      "hf-xet>=1.4"

# Fail the build early if the Python side is broken, or if installing the rest
# quietly swapped PyTorch for a build without CUDA.
RUN /opt/envs/gemx/bin/python -c "import torch, transformers, soma, onnxruntime, cv2, omegaconf, scipy, einops, numpy, huggingface_hub; from scipy.spatial.transform import Rotation; assert soma.__version__ == '0.3.3', soma.__version__; assert torch.version.cuda, 'PyTorch has no CUDA'; assert 'CUDAExecutionProvider' in onnxruntime.get_available_providers(), onnxruntime.get_available_providers(); print('torch', torch.__version__, 'cuda', torch.version.cuda, 'transformers', transformers.__version__, 'onnxruntime', onnxruntime.__version__, 'opencv', cv2.__version__)"

COPY handler.py tracks.py /app/
COPY models /app/models
WORKDIR /app
RUN /opt/envs/gemx/bin/python -c "import ast, sys; [ast.parse(open(p).read(), p) for p in ('/app/handler.py', '/app/tracks.py', '/app/models/gemx_model.py')]; sys.path.insert(0, '/app'); import tracks; print('worker code parses')"
CMD ["/opt/envs/router/bin/python", "-u", "handler.py"]
