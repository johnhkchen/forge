"""NVIDIA Kimodo, as one model behind the worker's router (../handler.py).

Kimodo makes motion from a sentence. "A person sneaks forward, low." comes
back as a few seconds of movement at 30 frames a second on NVIDIA's SOMA
skeleton. It can also be told where to go (a path over the ground), what pose
to be in at a moment (one of our own poses), and where a hand or foot must be.

This file runs in its own Python environment (/opt/envs/kimodo) as a child of
the router. It starts on the first `text` job, not with the worker, so jobs
for the other model never wait for it or share the GPU's memory with it.

Job kinds it answers:

  text
    prompts      [PROMPT, ...] played one after the other
    heading      degrees the character faces at the start (default 0: +Z)
    seed         a whole number; the same seed and input give the same motion
    steps        denoising steps, 10..300 (default 100)
    guidance     [text, constraints] strengths (default [2, 2])
    tidy         true (default) to run Kimodo's own clean-up: planted feet
                 stop sliding, and constraints are met exactly
    blend_frames frames each later prompt spends joining the one before (default 5)
    positions    true to also get every joint's world position per frame

    PROMPT
      text         what happens. Kimodo likes "A person ..." and one or two
                   actions per prompt
      seconds      how long, up to 10 (or `frames`)
      constraints  [CONSTRAINT, ...]; frame numbers count from this prompt's
                   first frame

    CONSTRAINT, one of
      {"type": "path", "frames": [...], "points": [[x, z], ...]}
          where the body is over the ground at each of those frames. Give a
          point for every frame to draw a whole route. Optional "headings":
          degrees faced at each.
      {"type": "pose", "frames": [f], "poses": [POSE]}
          the whole body, at that frame
      {"type": "reach", "frames": [f], "poses": [POSE], "parts": ["right_hand"]}
          only those hands and feet (and the hips' height), where the pose
          puts them; the rest is free. parts: left_hand, right_hand,
          left_foot, right_foot

    POSE is the same as the other model's: rotations by SOMA joint name,
    root, at, heading. Optional "stands_at": [x, z] is where the body counts
    as being on the path (default: under `at`).

    The character starts at x 0, z 0. Kimodo does best with fewer than 20
    pose and reach frames in a job; a path may be given for every frame.

  text_info   what is fetched and loaded, with revisions and timings

What `text` answers is the repo's motion format, "forge-soma-motion/1", the
same as the other model's `inbetween`: fps, joints by SOMA name, and per frame
the root position, each joint's local rotation [x, y, z, w], and whether each
heel and toe is on the ground.

Licensing. The image holds none of this. On first use the worker fetches, onto
the network volume (/runpod-volume/kimodo), each pinned to an exact revision:

  Kimodo's code          github.com/nv-tlabs/kimodo            Apache-2.0
  Kimodo-SOMA-RP-v1.2    huggingface.co/nvidia/...             NVIDIA Open Model License
  LLM2Vec adapters (2)   huggingface.co/McGill-NLP/...         MIT
  Meta Llama 3 8B Instruct  huggingface.co/meta-llama/...      Llama 3 Community License

The last one reads the sentence, and Meta gates it: the Hugging Face account
behind HF_TOKEN must already have asked for and been given access on the
model's page. This worker only checks. It never asks for access or accepts a
license; without access it stops and says so.

Kimodo's sample motions (its demo examples) are deleted from the volume copy
right after the fetch and are never read.
"""

import hashlib
import json
import logging
import math
import os
import shutil
import subprocess
import sys
import time
import traceback

PROCESS_STARTED = time.time()
HERE = os.path.dirname(os.path.abspath(__file__))

VOLUME = os.environ.get("VOLUME_DIR", "/runpod-volume")
ROOT = f"{VOLUME}/kimodo"

# Kimodo's code, by commit.
CODE_REPO = "https://github.com/nv-tlabs/kimodo.git"
CODE_COMMIT = "e1c219c99b4b94ba48be1fb6a1cbc64ecee4c954"
SRC = f"{ROOT}/src-{CODE_COMMIT[:12]}"
BUILT = f"{SRC}/.forge-built"

# The motion model. Only this one: its license allows commercial use.
MODEL_KEY = "kimodo-soma-rp-v1.2"
MODEL_NAME = "Kimodo-SOMA-RP-v1.2"
MODEL_LICENSE = "NVIDIA Open Model License"
CHECKPOINTS = f"{ROOT}/checkpoints"

# Every Hugging Face repo fetched: its exact revision, which files, and the
# sha256 and size of each large one.
REPOS = {
    "nvidia/Kimodo-SOMA-RP-v1.2": {
        "revision": "0e3c89024d896064b6851201373f7834784a386b",
        "license": MODEL_LICENSE,
        "gated": False,
        "into": f"{CHECKPOINTS}/{MODEL_NAME}",
        "patterns": ["config.yaml", "model.safetensors", "stats/**", "LICENSE", "README.md"],
        "files": {
            "model.safetensors": ("fdcef624140a12c0a4840192ce0b75cafb4e73228a893da3864b4a990d3e919e", 1133177724),
        },
    },
    "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp": {
        "revision": "31474e395ada192e8ed1586db6be79fb3b70c9c0",
        "license": "MIT",
        "gated": False,
        "patterns": ["*"],
        "files": {
            "adapter_model.safetensors": ("de9c8736618a13173c6a1623cdef1b75e86c69317f1073ae82cd516ac36a632d", 167829552),
        },
    },
    "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised": {
        "revision": "baa8ebf04a1c2500e61288e7dad65e8ae42601a7",
        "license": "MIT",
        "gated": False,
        "patterns": ["*"],
        "files": {
            "adapter_model.safetensors": ("53f8f94ebdf396667ba99dd96e78203edae27bbcdbd1cf5f12b611e1d916b225", 167829552),
        },
    },
    "meta-llama/Meta-Llama-3-8B-Instruct": {
        "revision": "8afb486c1db24fe5011ec46dfbe5b5dccdb575c2",
        "license": "Llama 3 Community License",
        "gated": True,
        # Not `original/`: that is the same model a second time, 16 GB more.
        "patterns": ["config.json", "generation_config.json", "model-0000*-of-00004.safetensors", "model.safetensors.index.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "LICENSE", "USE_POLICY.md"],
        "files": {
            "model-00001-of-00004.safetensors": ("d8cf9c4d0dd972e1a2131bfe656235ee98221679711a3beef6d46dadf0f20b5c", 4976698672),
            "model-00002-of-00004.safetensors": ("8d4782b4a69ef03845159ce1a15e272aadaaf134dc138d68f616098e8531729c", 4999802720),
            "model-00003-of-00004.safetensors": ("3acdd690e65c24f42a24581b8467af98bd3ca357444580f8012aacd2bd607921", 4915916176),
            "model-00004-of-00004.safetensors": ("67e9ad31c8c32abf3a55ee7fc7217b3ecb35fd3c74d98a5bd233e0e4d6964f46", 1168138808),
        },
    },
}
ENCODER_REPOS = [name for name in REPOS if "into" not in REPOS[name]]
HF_HOME = f"{ROOT}/hf"
PINS = hashlib.sha256(json.dumps([CODE_COMMIT, {k: v["revision"] for k, v in REPOS.items()}], sort_keys=True).encode()).hexdigest()[:12]
FETCHED = f"{ROOT}/.forge-fetched-{PINS}.json"
TEXT_CACHE = f"{ROOT}/text-cache-{PINS}"

FPS = 30
MAX_SECONDS = 10.0
PARTS = {"left_hand": "left-hand", "right_hand": "right-hand", "left_foot": "left-foot", "right_foot": "right-foot"}
CONTACT_ORDER = ("left_heel", "left_toe", "right_heel", "right_toe")
# Kimodo's T-pose stands with its hips 1 m up (its somaskel77_standard_tpose.bvh).
KIMODO_TPOSE_HIPS_Y = 1.0

logging.basicConfig(level=logging.INFO, format="[kimodo] %(message)s")
log = logging.getLogger("forge")


class Blocked(RuntimeError):
    """Something a person has to do first; the message says what."""


def sh(*args: str, cwd: str | None = None, env: dict | None = None) -> str:
    done = subprocess.run(args, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:3])}... failed: {(done.stderr or done.stdout).strip()[-1500:]}")
    return done.stdout.strip()


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def folder_bytes(path: str) -> int:
    total = 0
    for base, _, files in os.walk(path):
        for name in files:
            full = os.path.join(base, name)
            if not os.path.islink(full):
                total += os.path.getsize(full)
    return total


# ---- first boot: fetch ---------------------------------------------------------


def fetch_code() -> dict:
    """Kimodo's code at the pinned commit, with its foot clean-up compiled for this Python."""
    if os.path.exists(f"{BUILT}/done.json"):
        with open(f"{BUILT}/done.json") as f:
            return {**json.load(f), "fetched_now": False}
    started = time.time()
    partial = f"{SRC}.partial"
    shutil.rmtree(partial, ignore_errors=True)
    os.makedirs(partial)
    log.info("first boot: fetching %s at %s", CODE_REPO, CODE_COMMIT[:12])
    quiet = {"GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0"}
    sh("git", "init", "-q", cwd=partial)
    sh("git", "remote", "add", "origin", CODE_REPO, cwd=partial)
    sh("git", "fetch", "-q", "--depth", "1", "origin", CODE_COMMIT, cwd=partial, env=quiet)
    sh("git", "checkout", "-q", "--detach", "FETCH_HEAD", cwd=partial, env=quiet)
    commit = sh("git", "rev-parse", "HEAD", cwd=partial)
    if commit != CODE_COMMIT:
        raise RuntimeError(f"fetched {commit}, expected {CODE_COMMIT}")
    # Keep the code and the skeletons. Drop the sample motions (the demo's
    # examples), the benchmark, the docs and the pictures: none is ever read.
    for unused in (".git", "kimodo/assets/demo", "assets", "benchmark", "docs"):
        shutil.rmtree(f"{partial}/{unused}", ignore_errors=True)

    log.info("compiling Kimodo's motion clean-up (MotionCorrection)")
    built = f"{partial}/.forge-built"
    package = f"{built}/motion_correction"
    os.makedirs(f"{built}/cmake")
    os.makedirs(package)
    pybind = sh(sys.executable, "-m", "pybind11", "--cmakedir")
    sh(
        "cmake",
        f"{partial}/MotionCorrection",
        f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={package}",
        f"-DPython3_EXECUTABLE={sys.executable}",
        f"-Dpybind11_DIR={pybind}",
        "-DCMAKE_BUILD_TYPE=Release",
        cwd=f"{built}/cmake",
    )
    sh("cmake", "--build", ".", "--", f"-j{os.cpu_count() or 4}", cwd=f"{built}/cmake")
    for name in os.listdir(f"{partial}/MotionCorrection/python/motion_correction"):
        if name.endswith(".py"):
            shutil.copy(f"{partial}/MotionCorrection/python/motion_correction/{name}", package)
    if not [n for n in os.listdir(package) if n.startswith("_motion_correction") and n.endswith(".so")]:
        raise RuntimeError(f"MotionCorrection built no library: {os.listdir(package)}")
    shutil.rmtree(f"{built}/cmake", ignore_errors=True)
    record = {
        "repo": CODE_REPO,
        "commit": CODE_COMMIT,
        "license": "Apache-2.0",
        "python": sys.version.split()[0],
        "seconds": round(time.time() - started, 1),
        "bytes": folder_bytes(partial),
    }
    with open(f"{built}/done.json", "w") as f:
        json.dump(record, f, indent=2)
    shutil.rmtree(SRC, ignore_errors=True)
    os.rename(partial, SRC)
    return {**record, "fetched_now": True}


def check_access(token: str | None) -> None:
    """Can this Hugging Face account read the gated repos? Only looks; never asks for access."""
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import GatedRepoError, HfHubHTTPError, RepositoryNotFoundError

    for repo, card in REPOS.items():
        if not card["gated"]:
            continue
        page = f"https://huggingface.co/{repo}"
        if not token:
            raise Blocked(
                f"{repo} is gated and the worker has no Hugging Face token. Set HF_TOKEN on the endpoint "
                f"(the RunPod secret hf_token), from an account that has been given access at {page}."
            )
        try:
            hf_hub_download(repo, "config.json", revision=card["revision"], token=token)
        except GatedRepoError as error:
            raise Blocked(
                f"{repo} is gated ({card['license']}) and this Hugging Face account has not been given access. "
                f"A person has to open {page}, read the license, and ask for access with the account HF_TOKEN belongs to. "
                f"Nothing was accepted on anyone's behalf, and nothing gated was fetched."
            ) from error
        except RepositoryNotFoundError as error:
            raise Blocked(f"{repo}: Hugging Face says not found, which for a gated repo usually means the token is wrong or expired. Check the RunPod secret hf_token.") from error
        except HfHubHTTPError as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            if status in (401, 403):
                raise Blocked(
                    f"{repo}: Hugging Face answered {status}. The token is missing, expired, or its account has no access yet at {page}. "
                    f"Nothing was accepted on anyone's behalf."
                ) from error
            raise


def fetch_weights() -> dict:
    """The model and the text encoder, each at its pinned revision, checked by sha256."""
    if os.path.exists(FETCHED):
        with open(FETCHED) as f:
            return {**json.load(f), "fetched_now": False}
    from huggingface_hub import snapshot_download

    token = os.environ.get("HF_TOKEN") or None
    started = time.time()
    check_access(token)
    repos = {}
    for repo, card in REPOS.items():
        t = time.time()
        log.info("first boot: fetching %s at %s", repo, card["revision"][:12])
        kwargs = {"local_dir": card["into"]} if "into" in card else {}
        folder = snapshot_download(repo, revision=card["revision"], allow_patterns=card["patterns"], token=token, max_workers=8, **kwargs)
        for name, (expected, size) in card["files"].items():
            path = os.path.join(folder, name)
            if os.path.getsize(path) != size:
                raise RuntimeError(f"{repo}/{name}: {os.path.getsize(path)} bytes, expected {size}")
            got = sha256_of(path)
            if got != expected:
                raise RuntimeError(f"{repo}/{name}: sha256 {got}, expected {expected}")
        if "into" not in card:
            # Later boots load with the network off, by the repo's name. That
            # looks up `main` in the cache, so point `main` at the pinned revision.
            refs = os.path.join(os.path.dirname(os.path.dirname(folder)), "refs")
            os.makedirs(refs, exist_ok=True)
            with open(os.path.join(refs, "main"), "w") as f:
                f.write(card["revision"])
        repos[repo] = {
            "revision": card["revision"],
            "license": card["license"],
            "gated": card["gated"],
            "bytes": sum(os.path.getsize(os.path.join(base, n)) for base, _, names in os.walk(folder) for n in names),
            "seconds": round(time.time() - t, 1),
        }
    record = {
        "repos": repos,
        "bytes": sum(r["bytes"] for r in repos.values()),
        "seconds": round(time.time() - started, 1),
        "token_used": bool(token),
    }
    os.makedirs(ROOT, exist_ok=True)
    with open(FETCHED + ".partial", "w") as f:
        json.dump(record, f, indent=2)
    os.rename(FETCHED + ".partial", FETCHED)
    return {**record, "fetched_now": True}


def fetch_main() -> None:
    """`kimodo_model.py --fetch`: run as its own process, with the network on. Prints one JSON line."""
    try:
        os.makedirs(ROOT, exist_ok=True)
        print(json.dumps({"ok": True, "code": fetch_code(), "weights": fetch_weights()}))
    except Blocked as error:
        print(json.dumps({"ok": False, "blocked": True, "error": str(error)}))
    except Exception:
        print(json.dumps({"ok": False, "blocked": False, "error": traceback.format_exc()[-3000:]}))


# ---- boot ----------------------------------------------------------------------


class State:
    """Everything loaded once at boot and reused by every job."""


S = State()
BOOT: dict = {}


class TextEncoder:
    """Kimodo's sentence reader (LLM2Vec on Llama 3), loaded only when a sentence is new.

    What it makes of a sentence is one row of 4096 numbers, and that is kept on
    the volume. A sentence seen before never needs the 16 GB encoder at all.
    """

    def __init__(self, device: str):
        self.device = device
        self.encoder = None
        self.load_seconds = 0.0
        self.hits = self.misses = 0

    def path(self, text: str) -> str:
        return f"{TEXT_CACHE}/{hashlib.sha256(text.encode()).hexdigest()}.npy"

    def load(self) -> None:
        if self.encoder is not None:
            return
        t = time.time()
        log.info("loading the text encoder (16 GB, from the volume)")
        from kimodo.model.llm2vec import LLM2VecEncoder
        from kimodo.model.load_model import TEXT_ENCODER_PRESETS

        kwargs = dict(TEXT_ENCODER_PRESETS["llm2vec"]["kwargs"])
        kwargs["device"] = os.environ.get("TEXT_ENCODER_DEVICE") or self.device
        self.encoder = LLM2VecEncoder(**kwargs)
        self.load_seconds = round(time.time() - t, 1)
        log.info("text encoder ready after %.1fs", self.load_seconds)

    def __call__(self, texts):
        np, torch = S.np, S.torch
        single = isinstance(texts, str)
        rows = []
        for text in [texts] if single else list(texts):
            if not text.strip():
                rows.append(np.zeros((4096,), dtype=np.float32))
                continue
            path = self.path(text)
            if os.path.exists(path):
                self.hits += 1
                rows.append(np.load(path))
                continue
            self.load()
            self.misses += 1
            made, _ = self.encoder(text)
            row = made.detach().float().cpu().numpy().reshape(-1)[:4096].astype(np.float32)
            os.makedirs(TEXT_CACHE, exist_ok=True)
            np.save(path + ".partial.npy", row)
            os.rename(path + ".partial.npy", path)
            rows.append(row)
        out = torch.tensor(np.stack(rows)[:, None, :]).to(self.device)
        lengths = [1] * len(rows)
        return (out[0], lengths[0]) if single else (out, lengths)

    def to(self, device):
        return self

    def eval(self):
        return self


def boot() -> None:
    seconds: dict = {}
    t = time.time()
    os.makedirs(ROOT, exist_ok=True)
    os.environ["HF_HOME"] = HF_HOME
    # The fetch runs as a process of its own so that this one can load with the
    # network off: nothing but the pinned files on the volume can be read.
    done = subprocess.run([sys.executable, "-u", os.path.abspath(__file__), "--fetch"], stdout=subprocess.PIPE, text=True, env={**os.environ, "HF_HOME": HF_HOME})
    lines = [line for line in done.stdout.splitlines() if line.startswith("{")]
    fetched = json.loads(lines[-1]) if lines else {"ok": False, "error": f"the fetch ended with exit {done.returncode} and no answer"}
    if not fetched["ok"]:
        raise (Blocked if fetched.get("blocked") else RuntimeError)(fetched["error"])
    seconds["fetch"] = round(time.time() - t, 1)

    t = time.time()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["CHECKPOINT_DIR"] = CHECKPOINTS
    os.environ["TEXT_ENCODER_MODE"] = "local"
    sys.path.insert(0, SRC)
    sys.path.insert(0, BUILT)
    sys.path.insert(0, HERE)
    import numpy as np
    import torch
    from scipy.spatial.transform import Rotation

    from kimodo import load_model
    from kimodo.constraints import load_constraints_lst
    from kimodo.tools import seed_everything
    from motion_correction import motion_postprocess  # noqa: F401  fail at boot, not in a job, if the clean-up did not build
    from soma_bridge import Bridge

    seconds["imports"] = round(time.time() - t, 1)
    if not torch.cuda.is_available():
        raise RuntimeError("no GPU: torch.cuda.is_available() is false")

    t = time.time()
    S.np, S.torch, S.Rotation = np, torch, Rotation
    S.device = "cuda:0"
    S.encoder = TextEncoder(S.device)
    S.model = load_model(MODEL_KEY, device=S.device, text_encoder=S.encoder)
    S.load_constraints, S.seed = load_constraints_lst, seed_everything
    S.skeleton = S.model.skeleton
    S.out_skeleton = S.model.output_skeleton
    S.bridge = None
    seconds["model"] = round(time.time() - t, 1)
    if int(round(float(S.model.fps))) != FPS:
        raise RuntimeError(f"Kimodo runs at {S.model.fps} fps, expected {FPS}")

    seconds["boot"] = round(time.time() - PROCESS_STARTED, 1)
    BOOT.update(
        {
            "gpu": torch.cuda.get_device_name(0),
            "torch": str(torch.__version__),
            "kimodo": {"model": MODEL_NAME, "license": MODEL_LICENSE, "code_commit": CODE_COMMIT},
            "fetched_this_boot": bool(fetched["code"]["fetched_now"] or fetched["weights"]["fetched_now"]),
            "fetched": {
                "code": {k: fetched["code"][k] for k in ("commit", "seconds", "bytes", "license")},
                "weights": {k: fetched["weights"][k] for k in ("repos", "bytes", "seconds", "token_used")},
            },
            "text_cache": TEXT_CACHE,
            "seconds": seconds,
        }
    )
    log.info("ready: %s", json.dumps(BOOT))


def bridge_for(card: dict):
    """The pose carrier between the repo's SOMA poses and Kimodo's, built from the two rest poses."""
    if S.bridge is None:
        from soma_bridge import Bridge

        rest = S.skeleton.neutral_joints.detach().cpu().numpy()
        names = list(S.skeleton.bone_order_names)
        S.bridge = Bridge(card, {name: [float(v) for v in rest[i]] for i, name in enumerate(names)}, KIMODO_TPOSE_HIPS_Y)
        if S.bridge.joints != names:
            raise RuntimeError("Kimodo's 30 joints are not in the same order as the repo's SOMA joints")
        S.out_rows = [S.out_skeleton.bone_index[name] for name in S.bridge.joints]
    return S.bridge


# ---- the job -------------------------------------------------------------------


def frames_of(prompt: dict, number: int) -> int:
    if "frames" in prompt:
        frames = int(prompt["frames"])
    else:
        frames = int(round(float(prompt.get("seconds", 0.0)) * FPS))
    if not 8 <= frames <= int(MAX_SECONDS * FPS):
        raise ValueError(f"prompt {number}: a prompt lasts 8 frames to {MAX_SECONDS:.0f} seconds, not {frames} frames")
    return frames


def constraint_dicts(bridge, constraint: dict, offset: int, frames: int, where: str) -> list:
    """One of our constraints as Kimodo's own constraint-file entries."""
    kind = constraint.get("type")
    at = [int(f) for f in constraint.get("frames") or []]
    if not at or min(at) < 0 or max(at) >= frames:
        raise ValueError(f"{where}: frames must be inside the prompt (0..{frames - 1})")
    moved = [f + offset for f in at]
    if kind == "path":
        points = constraint.get("points") or []
        if len(points) != len(at):
            raise ValueError(f"{where}: one [x, z] point per frame")
        out = {"type": "root2d", "frame_indices": moved, "smooth_root_2d": [[float(p[0]), float(p[1])] for p in points]}
        if constraint.get("headings"):
            if len(constraint["headings"]) != len(at):
                raise ValueError(f"{where}: one heading per frame")
            out["global_root_heading"] = [[math.cos(math.radians(float(h))), math.sin(math.radians(float(h)))] for h in constraint["headings"]]
        return [out]
    if kind not in ("pose", "reach"):
        raise ValueError(f"{where}: type must be path, pose or reach")
    poses = constraint.get("poses") or []
    if len(poses) != len(at):
        raise ValueError(f"{where}: one pose per frame")
    carried = [bridge.to_kimodo(p) for p in poses]
    stands = [p.get("stands_at") or [(p.get("at") or (0.0, 0.0, 0.0))[0], (p.get("at") or (0.0, 0.0, 0.0))[2]] for p in poses]
    body = {
        "frame_indices": moved,
        "root_positions": [c["root_position"] for c in carried],
        "local_joints_rot": [c["local_joints_rot"] for c in carried],
        "smooth_root_2d": [[float(s[0]), float(s[1])] for s in stands],
    }
    if kind == "pose":
        return [{"type": "fullbody", **body}]
    parts = constraint.get("parts") or []
    if not parts or any(p not in PARTS for p in parts):
        raise ValueError(f"{where}: parts are {', '.join(PARTS)}")
    return [{"type": PARTS[p], **body} for p in parts]


def text_to_motion(params: dict) -> dict:
    np, torch = S.np, S.torch
    card = params.get("soma_skeleton")
    if not card:
        raise ValueError("the router did not pass the SOMA skeleton")
    bridge = bridge_for(card)
    prompts = params.get("prompts") or []
    if not 1 <= len(prompts) <= 8:
        raise ValueError("text needs 1 to 8 prompts")
    steps = int(params.get("steps", 100))
    guidance = [float(v) for v in params.get("guidance", (2.0, 2.0))]
    blend = int(params.get("blend_frames", 5))
    if not 10 <= steps <= 300 or len(guidance) != 2 or not 1 <= blend <= 15:
        raise ValueError("steps are 10..300, guidance is [text, constraints], blend_frames 1..15")
    seed = int(params.get("seed", 0))
    tidy = bool(params.get("tidy", True))

    texts, counts, entries, segments = [], [], [], []
    offset = 0
    for number, prompt in enumerate(prompts):
        text = str(prompt.get("text") or "").strip()
        if not text:
            raise ValueError(f"prompt {number}: no text")
        frames = frames_of(prompt, number)
        for c, constraint in enumerate(prompt.get("constraints") or []):
            entries += constraint_dicts(bridge, constraint, offset, frames, f"prompt {number}, constraint {c}")
        texts.append(text)
        counts.append(frames)
        segments.append({"name": text, "first_frame": offset, "last_frame": offset + frames - 1})
        offset += frames
    keyed = sum(len(e["frame_indices"]) for e in entries if e["type"] != "root2d")

    hits, misses, loaded = S.encoder.hits, S.encoder.misses, S.encoder.encoder is not None
    started = time.perf_counter()
    S.seed(seed)
    constraints = S.load_constraints(entries, S.skeleton) if entries else []
    output = S.model(
        texts,
        counts,
        num_denoising_steps=steps,
        multi_prompt=True,
        constraint_lst=constraints,
        cfg_weight=guidance,
        cfg_type="separated",
        num_samples=1,
        return_numpy=True,
        first_heading_angle=torch.tensor([math.radians(float(params.get("heading", 0.0)))], device=S.device),
        num_transition_frames=blend,
        post_processing=tidy,
        progress_bar=lambda steps_: steps_,
    )
    took = time.perf_counter() - started

    turned = np.asarray(output["global_rot_mats"])[0][:, S.out_rows]  # [T, 30, 3, 3]
    roots = np.asarray(output["root_positions"])[0]
    count = len(roots)
    if not (np.isfinite(turned).all() and np.isfinite(roots).all()):
        raise RuntimeError("Kimodo answered numbers that are not finite")
    quats = S.Rotation.from_matrix(turned.reshape(-1, 3, 3)).as_quat().reshape(count, len(bridge.joints), 4)
    root_rows, rotation_rows = [], []
    for f in range(count):
        root, local = bridge.from_kimodo(roots[f], quats[f])
        root_rows.append([round(v, 5) for v in root])
        rotation_rows.append([round(c, 6) for q in local for c in q])
    # How far our skeleton's hands, feet and head end up from Kimodo's own: the two
    # skeletons' bones differ by a few millimetres, so this should be a centimetre or so.
    theirs = np.asarray(output["posed_joints"])[0][:, S.out_rows]
    apart = {name: 0.0 for name in ("LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase", "LeftHand", "RightHand", "Head")}
    placed_frames = []
    for f in range(count):
        placed, _ = bridge.fk(tuple(root_rows[f]), [tuple(rotation_rows[f][4 * j : 4 * j + 4]) for j in range(len(bridge.joints))])
        placed_frames.append(placed)
        for name in apart:
            j = bridge.index[name]
            there = (float(theirs[f][j][0]), float(theirs[f][j][1]) + bridge.lift, float(theirs[f][j][2]))
            apart[name] = max(apart[name], math.dist(placed[j], there))
    # Kimodo's 77-joint answer has six contacts (heel, toe, toe end per foot); ours has four.
    touching = np.asarray(output["foot_contacts"])[0].astype(np.float32)
    columns = [0, 1, 3, 4] if touching.shape[-1] == 6 else [0, 1, 2, 3]
    smooth = np.asarray(output["smooth_root_pos"])[0]
    result = {
        "format": "forge-soma-motion/1",
        "fps": FPS,
        "up": "+Y",
        "forward_at_heading_0": "+Z",
        "joints": bridge.joints,
        "root": root_rows,
        "rotations": rotation_rows,
        "contact_order": list(CONTACT_ORDER),
        "contacts": touching[:, columns].round(3).tolist(),
        "segments": segments,
        "path_followed": [[round(float(p[0]), 4), round(float(p[2]), 4)] for p in smooth],
        "made_by": {
            "model": MODEL_NAME,
            "revision": REPOS[f"nvidia/{MODEL_NAME}"]["revision"],
            "seed": seed,
            "steps": steps,
            "guidance": guidance,
            "tidy": tidy,
            "blend_frames": blend,
            "pose_and_reach_frames": keyed,
        },
        "text_encoder": {
            "sentences_from_cache": S.encoder.hits - hits,
            "sentences_encoded": S.encoder.misses - misses,
            "loaded_for_this_job": (S.encoder.encoder is not None) and not loaded,
            "load_seconds": S.encoder.load_seconds if (S.encoder.encoder is not None) and not loaded else 0.0,
        },
        "our_joints_vs_kimodos_cm": {name: round(100.0 * d, 2) for name, d in apart.items()},
        "generate_seconds": round(took, 3),
        "seconds_of_motion": round(count / FPS, 3),
        "seconds_per_second_of_motion": round(took / (count / FPS), 3),
        "gpu_memory_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2),
    }
    if params.get("positions"):
        result["positions"] = [[round(c, 5) for p in placed for c in p] for placed in placed_frames]
    return result


KINDS = {
    "text": text_to_motion,
    "text_info": lambda params: BOOT,
}


def serve() -> None:
    """Answer the router: one JSON job per line in, one JSON answer per line out."""
    answers = os.fdopen(os.dup(1), "w")
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    def say(message: dict) -> None:
        answers.write(json.dumps(message, separators=(",", ":")) + "\n")
        answers.flush()

    try:
        boot()
    except Blocked as error:
        say({"ready": False, "error": f"BLOCKED: {error}"})
        return
    except Exception:
        say({"ready": False, "error": traceback.format_exc()[-3000:]})
        return
    say({"ready": True, "boot": BOOT})
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            job = json.loads(line)
            t0 = time.time()
            result = KINDS[job["kind"]](job.get("input") or {})
            say({"ok": True, "result": result, "seconds": round(time.time() - t0, 3)})
        except Exception as error:
            log.error("job failed:\n%s", traceback.format_exc())
            say({"ok": False, "error": f"{type(error).__name__}: {error}"})


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        fetch_main()
    else:
        serve()
