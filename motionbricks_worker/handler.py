"""NVIDIA MotionBricks on RunPod Serverless: a shot list of poses in, motion out.

MotionBricks fills in the movement between poses. You give it the pose the
character is in and the poses it should reach, each placed somewhere in the
scene; it gives back the frames in between, at 30 a second, on NVIDIA's SOMA
skeleton (30 joints, Y up, metres, facing +Z at heading 0).

Input (job["input"]):
    action   "generate" (default) | "skeleton" | "selftest" | "info"

  generate
    seed     POSE the character starts in, held still
    targets  [TARGET, ...] reached one after the other
    positions  true to also get every joint's world position per frame

    POSE
      rotations  {"Hips": [x, y, z, w], ...} local joint rotations; joints left
                 out keep the skeleton's rest rotation
      root       [x, y, z] of the hips before placement (y is height above the
                 ground); default is the rest height
      at         [x, y, z] where the pose stands in the scene; default origin
      heading    degrees turned about +Y; default 0

    TARGET
      name                 a label, echoed back
      poses                1 to 4 POSEs, 1/30 s apart. One pose is a place to
                           stop; more say how the body is moving there
      poses_to_use         how many of them to give the model (default: all)
      tokens               6..16, or [min, max]; each token is 4 frames, and
                           the motion is 4 * tokens - 6 frames long
      transition_early_by  frames before the end to move on to the next target
      pins                 of "left_hand", "right_hand", "left_foot",
                           "right_foot": eased onto this target's first pose
                           with two-bone IK as the motion arrives
      hold_pins            frames to keep the previous target's pins fully on
                           at the start of this one (default 0)
      release_pins         frames over which they then let go (default 6)

  skeleton   the SOMA joints, parents and rest pose, to author poses against
  selftest   the same two chained generations as MotionBricks'
             docs/examples/generate_once.py, from its sample walk clip.
             Returns only frame counts, timings and where the root went.
  info       versions, the GPU, and how long this worker took to boot

Output: like the TRELLIS.2 worker, the handler is a generator. /stream/{job}
gives, in order:
    {"kind": "info", "stage": "...", "gpu": "..."}
    {"kind": "chunk", "index": i, "total": n, "data": "<base64>"}
    {"kind": "done", "bytes": N, "sha256": "...", "seconds": {...}}
Join the chunks' data in index order, base64-decode, check sha256: that is one
JSON document. For generate it holds, per frame, the root position, the 30
joints' local rotations, and how firmly each heel and toe is on the ground.

Licensing. The image this file ships in holds none of NVIDIA's MotionBricks
release. On first boot the worker clones the pinned release from GitHub onto
the network volume (mounted at /runpod-volume) and pulls, with Git LFS, only
what it runs: the SOMA model (NVIDIA Open Model Agreement), the SOMA skeleton,
and one sample walk clip used by `selftest` alone (NVIDIA Sample Data
Evaluation License: evaluation and testing only). `generate` never reads a
sample clip. The TensorRT plan built from the model is kept on the volume too,
in a folder named for the GPU, TensorRT and driver it was built with.
"""

import base64
import glob
import hashlib
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import time
import traceback

PROCESS_STARTED = time.time()

VOLUME = os.environ.get("VOLUME_DIR", "/runpod-volume")
ROOT = f"{VOLUME}/motionbricks"

# The MotionBricks release this worker runs: tag v0.2.0, checked by commit.
MB_REPO = "https://github.com/NVlabs/motionbricks.git"
MB_TAG = "v0.2.0"
MB_COMMIT = "54fc563aeaaf819a753d72cc9fdc6713989cdd43"
SRC = f"{ROOT}/src-{MB_COMMIT[:12]}"
FETCHED = f"{SRC}/.forge-fetched.json"

# The Git LFS files the worker pulls, with the sha256 the release pins for each.
MODEL = "motionbricks/assets/onnx/soma/mmm_v6_soma_fp32.onnx"
SKELETON = "motionbricks/assets/human/soma_base_skel_minimal_no_root.usd"
SAMPLE_WALK = "assets/motions/soma/locomotion/bs_1d_linear/Neutral_walk_forward_002__A057.bvh"
LFS_FILES = {
    MODEL: "856419dc72aeb14e591eebf4dd0ea05734a2506ddb00bcd39dd6dac2ad60f4fb",
    SKELETON: "4ab93d78a0f1c06d3bcbedee5ceebb5d9d5b002fd0a88638e9399ed80b61871d",
    SAMPLE_WALK: "c0f4e63cec94c58196105a6d9f03a2ed1c94c8ff4fba15dd0a33cc512877904a",
}

CHUNK_BYTES = 512 * 1024  # base64 grows it to ~700 KB, under /stream's 1 MB per item
MAX_TARGETS = 64
PIN_NAMES = ("left_hand", "right_hand", "left_foot", "right_foot")
CONTACT_ORDER = ("left_heel", "left_toe", "right_heel", "right_toe")

# Warp compiles its kernels on first use; keeping them on the volume saves
# that on every later boot.
os.environ.setdefault("WARP_CACHE_PATH", f"{ROOT}/warp-cache")

logging.basicConfig(level=logging.INFO, format="[motionbricks] %(message)s")
log = logging.getLogger("forge")


def sh(*args: str, cwd: str | None = None, env: dict | None = None) -> str:
    done = subprocess.run(args, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:3])}... failed: {done.stderr.strip()[-800:]}")
    return done.stdout.strip()


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_release() -> dict:
    """Puts the pinned MotionBricks release on the volume, once.

    Cloned into a .partial folder and renamed only after every file's sha256
    matches, so a boot that dies halfway leaves nothing that looks finished.
    """
    if os.path.exists(FETCHED):
        with open(FETCHED) as f:
            return {**json.load(f), "fetched_now": False}
    started = time.time()
    os.makedirs(ROOT, exist_ok=True)
    partial = f"{SRC}.partial"
    shutil.rmtree(partial, ignore_errors=True)
    log.info("first boot: cloning %s at %s", MB_REPO, MB_TAG)
    sh("git", "clone", "--depth", "1", "--branch", MB_TAG, MB_REPO, partial, env={"GIT_LFS_SKIP_SMUDGE": "1"})
    commit = sh("git", "rev-parse", "HEAD", cwd=partial)
    if commit != MB_COMMIT:
        raise RuntimeError(f"{MB_TAG} is now {commit}, expected {MB_COMMIT}")
    log.info("pulling the model, the skeleton and the self-test clip with Git LFS")
    sh("git", "lfs", "pull", "--include", ",".join(LFS_FILES), "--exclude", "", cwd=partial)
    for path, expected in LFS_FILES.items():
        got = sha256_of(f"{partial}/{path}")
        if got != expected:
            raise RuntimeError(f"{path}: sha256 {got}, expected {expected}")
    # Only the checked-out files are needed from here on.
    shutil.rmtree(f"{partial}/.git", ignore_errors=True)
    record = {
        "repo": MB_REPO,
        "tag": MB_TAG,
        "commit": MB_COMMIT,
        "files": LFS_FILES,
        "fetch_seconds": round(time.time() - started, 1),
    }
    with open(f"{partial}/.forge-fetched.json", "w") as f:
        json.dump(record, f, indent=2)
    shutil.rmtree(SRC, ignore_errors=True)
    os.rename(partial, SRC)
    return {**record, "fetched_now": True}


def gpu_driver() -> str:
    try:
        return sh("nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader").splitlines()[0].strip()
    except Exception:
        return "unknown"


class State:
    """Everything loaded once at boot and reused by every job."""


S = State()
BOOT: dict = {}
BOOT_ERROR: str | None = None


def boot() -> None:
    seconds: dict = {}
    t = time.time()
    release = fetch_release()
    seconds["fetch"] = round(time.time() - t, 1)
    sys.path.insert(0, SRC)

    t = time.time()
    import numpy as np
    import tensorrt as trt
    import warp as wp

    wp.init()
    wp.set_device("cuda:0")
    from motionbricks.io.usd import load_skeleton_from_usd
    from motionbricks.io.utils import SOMA_SKELETON_PRIM_PATH
    from motionbricks.model.config import MotionBricksInferenceConfig
    from motionbricks.model.soma.engine import MotionBricksSOMAEngine
    from motionbricks.runtime.target_pose import IKPin, TargetPoseIKCorrector, create_soma_target_pose_ik_rig
    from motionbricks.utils.pose_utils import compute_world_poses

    seconds["imports"] = round(time.time() - t, 1)

    gpu = wp.get_device().name
    driver = gpu_driver()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", f"{gpu}_trt{trt.__version__}_driver{driver}").strip("-")
    # MotionBricks also keys each plan by the model's hash, TensorRT version
    # and GPU name; the folder name just makes that visible on the volume.
    plan_dir = f"{ROOT}/trt-cache/{slug}"
    plan_cached = bool(glob.glob(f"{plan_dir}/*.plan"))

    t = time.time()
    skeleton = load_skeleton_from_usd(f"{SRC}/{SKELETON}", SOMA_SKELETON_PRIM_PATH)
    log.info("%s the TensorRT plan for %s", "loading" if plan_cached else "building (minutes)", gpu)
    # No model_to_runtime: poses go in and come out in SOMA's own space, Y up.
    engine = MotionBricksSOMAEngine(f"{SRC}/{MODEL}", cache_dir=plan_dir)
    seconds["engine"] = round(time.time() - t, 1)

    S.np, S.wp = np, wp
    S.Config, S.IKPin = MotionBricksInferenceConfig, IKPin
    S.compute_world_poses = compute_world_poses
    S.skeleton, S.engine = skeleton, engine
    S.names = list(skeleton.joint_names)
    S.index = {name: i for i, name in enumerate(S.names)}
    S.parents = [int(p) for p in skeleton.parent_indices.numpy()]
    S.reference = skeleton.reference_local_transforms.numpy().astype(np.float32).reshape(len(S.names), 7)
    S.model_joints = list(engine.contract.joint_names)
    S.model_rows = [S.index[name] for name in S.model_joints]
    S.context = engine.create_input(skeleton)
    S.target = engine.create_input(skeleton)
    S.output = engine.create_output(skeleton)
    chains = create_soma_target_pose_ik_rig(skeleton)
    S.pin_in = TargetPoseIKCorrector(skeleton, chains)
    S.pin_hold = TargetPoseIKCorrector(skeleton, chains)
    S.pin_flags = dict(zip(PIN_NAMES, (IKPin.LEFT_HAND, IKPin.RIGHT_HAND, IKPin.LEFT_FOOT, IKPin.RIGHT_FOOT)))

    # One throwaway generation compiles the kernels and the CUDA graph, so the
    # first real job doesn't pay for them.
    t = time.time()
    rest = {"rotations": {}}
    generate({"seed": rest, "targets": [{"poses": [{**rest, "at": [0.0, 0.0, 1.0]}], "tokens": 8}]})
    seconds["warm_up"] = round(time.time() - t, 1)
    seconds["boot"] = round(time.time() - PROCESS_STARTED, 1)

    BOOT.update(
        {
            "gpu": gpu,
            "driver": driver,
            "tensorrt": str(trt.__version__),
            "warp": str(wp.__version__),
            "motionbricks": {"tag": MB_TAG, "commit": MB_COMMIT},
            "fetched_this_boot": release["fetched_now"],
            "plan_was_cached": plan_cached,
            "plan_dir": plan_dir,
            "seconds": seconds,
        }
    )
    log.info("ready: %s", json.dumps(BOOT))


# ---- poses ---------------------------------------------------------------


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def pose_rows(spec: dict):
    """One POSE as [joint, 7] local transforms (xyz, then an xyzw quaternion), placed in the scene."""
    np = S.np
    rows = S.reference.copy()
    for name, q in (spec.get("rotations") or {}).items():
        i = S.index.get(name)
        if i is None:
            raise ValueError(f"unknown joint {name!r}")
        q = np.asarray(q, dtype=np.float64)
        length = float(np.linalg.norm(q)) if q.shape == (4,) else 0.0
        if not math.isfinite(length) or length < 1e-6:
            raise ValueError(f"{name}: a rotation is four finite numbers [x, y, z, w]")
        rows[i, 3:7] = q / length
    root = np.asarray(spec.get("root", rows[0, :3]), dtype=np.float64)
    at = np.asarray(spec.get("at", (0.0, 0.0, 0.0)), dtype=np.float64)
    if root.shape != (3,) or at.shape != (3,) or not (np.isfinite(root).all() and np.isfinite(at).all()):
        raise ValueError("root and at are three finite numbers [x, y, z]")
    half = math.radians(float(spec.get("heading", 0.0))) / 2.0
    s, c = math.sin(half), math.cos(half)
    # Turning (x, y, z) about +Y by the heading.
    turned = (
        root[0] * (c * c - s * s) + root[2] * (2 * s * c),
        root[1],
        root[2] * (c * c - s * s) - root[0] * (2 * s * c),
    )
    rows[0, :3] = at + np.asarray(turned)
    rows[0, 3:7] = quat_mul((0.0, s, 0.0, c), tuple(float(v) for v in rows[0, 3:7]))
    return rows


def token_counts(value) -> tuple:
    if value is None:
        return tuple(range(8, 15))
    low, high = (value, value) if isinstance(value, int) else (int(value[0]), int(value[1]))
    if not 6 <= low <= high <= 16:
        raise ValueError(f"tokens must be 6..16 (or [min, max]), got {value!r}")
    return tuple(range(low, high + 1))


def pin_mask(names):
    mask = S.IKPin.NONE
    for name in names or ():
        if name not in S.pin_flags:
            raise ValueError(f"unknown pin {name!r}; use {', '.join(PIN_NAMES)}")
        mask |= S.pin_flags[name]
    return mask


def smoothstep(low: float, high: float, x: float) -> float:
    t = min(1.0, max(0.0, (x - low) / (high - low)))
    return t * t * (3.0 - 2.0 * t)


# ---- actions -------------------------------------------------------------


def generate(params: dict) -> dict:
    """Chains one generation per target, the way MotionBricks' Inbetweener does:
    play each to its transition point, and start the next from the last four
    frames that were shown."""
    np, wp = S.np, S.wp
    engine, stream = S.engine, S.engine.stream
    targets = params.get("targets") or []
    if "seed" not in params or not 1 <= len(targets) <= MAX_TARGETS:
        raise ValueError(f"generate needs a seed pose and 1 to {MAX_TARGETS} targets")

    seed = pose_rows(params["seed"])
    shown = [seed]
    contacts: list = [None]
    segments = []
    held_mask = S.IKPin.NONE
    S.pin_hold.clear_pins()
    started = time.perf_counter()
    with wp.ScopedStream(stream):
        context_poses = wp.array(np.repeat(seed[None], 4, axis=0), dtype=wp.transform, device=engine.device)
        for number, target in enumerate(targets):
            poses = target.get("poses") or []
            if not 1 <= len(poses) <= 4:
                raise ValueError(f"target {number}: 1 to 4 poses")
            use = int(target.get("poses_to_use", len(poses)))
            if not 1 <= use <= len(poses):
                raise ValueError(f"target {number}: poses_to_use must be 1 to {len(poses)}")
            target_poses = wp.array(
                np.stack([pose_rows(p) for p in poses[:use]]), dtype=wp.transform, device=engine.device
            )
            mask = pin_mask(target.get("pins"))
            early = int(target.get("transition_early_by", 0))
            hold = int(target.get("hold_pins", 0))
            release = max(1, int(target.get("release_pins", 6)))
            if not 0 <= early <= 20 or hold < 0:
                raise ValueError(f"target {number}: transition_early_by is 0..20 and hold_pins is 0 or more")

            t0 = time.perf_counter()
            S.context.update_from_poses(context_poses, stream=stream)
            S.target.update_from_poses(target_poses, stream=stream)
            S.pin_in.capture_pins(target_poses[0], mask, stream=stream)
            engine.generate_animation(
                S.context, S.target, S.output, config=S.Config(allowed_token_counts=token_counts(target.get("tokens")))
            )
            frames = S.output.num_frames
            # Frame 0 is the pose already shown; at least four frames play,
            # because the next generation starts from the last four.
            end = max(3, frames - 1 - early)
            for f in range(1, end + 1):
                row = S.output.poses[f]
                if held_mask != S.IKPin.NONE and hold > 0:
                    S.pin_hold.apply(row, 1.0 - smoothstep(0.0, 1.0, (f - hold) / release), stream=stream)
                if mask != S.IKPin.NONE:
                    S.pin_in.apply(row, smoothstep(0.5, 1.0, f / end), stream=stream)
            engine.synchronize()
            played = S.output.poses.numpy()[: end + 1].copy()
            touching = S.output.foot_contacts.numpy()[: end + 1].copy()
            if contacts[0] is None:
                contacts[0] = touching[0]
            first = len(shown)
            shown.extend(played[1:])
            contacts.extend(touching[1:])
            context_poses = wp.clone(S.output.poses[end - 3 : end + 1])
            S.pin_hold.capture_pins(target_poses[0], mask, stream=stream)
            held_mask = mask
            segments.append(
                {
                    "name": target.get("name", f"target {number}"),
                    "first_frame": first,
                    "last_frame": len(shown) - 1,
                    "tokens": (frames + 6) // 4,
                    "frames_generated": frames,
                    "model_ms": {k: round(v, 2) for k, v in engine.timer.milliseconds.items()},
                    "wall_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                }
            )

        motion = np.stack(shown)
        result = {
            "format": "forge-soma-motion/1",
            "fps": 30,
            "up": "+Y",
            "forward_at_heading_0": "+Z",
            "joints": S.model_joints,
            "root": motion[:, 0, :3].round(5).tolist(),
            "rotations": motion[:, S.model_rows, 3:7].round(6).reshape(len(motion), -1).tolist(),
            "contact_order": list(CONTACT_ORDER),
            "contacts": np.stack(contacts).round(3).tolist(),
            "segments": segments,
        }
        if params.get("positions"):
            local = wp.array(motion, dtype=wp.transform, device=engine.device)
            world = wp.empty_like(local)
            S.compute_world_poses(local, S.skeleton.parent_indices, world, stream=stream)
            engine.synchronize()
            result["positions"] = (
                world.numpy()[:, S.model_rows, :3].round(5).reshape(len(motion), -1).tolist()
            )
    result["generate_seconds"] = round(time.perf_counter() - started, 3)
    return result


def skeleton_card() -> dict:
    return {
        "format": "forge-soma-skeleton/1",
        "source": f"{MB_REPO} {MB_TAG} {SKELETON}",
        "up": "+Y",
        "joints": S.names,
        "parents": S.parents,
        "rest": S.reference.round(6).tolist(),
        "model_joints": S.model_joints,
        "contact_joints": ["LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"],
    }


def selftest() -> dict:
    """MotionBricks' docs/examples/generate_once.py: generate from the sample
    walk clip to two later moments of it, the second starting from the last
    four frames of the first. Only counts, timings and the root's path leave."""
    np, wp = S.np, S.wp
    from motionbricks.io.bvh import load_bvh

    engine, stream = S.engine, S.engine.stream
    context_end, target_times = 1.0, (1.8, 3.4)
    generations = []
    with wp.ScopedStream(stream):
        clip = load_bvh(f"{SRC}/{SAMPLE_WALK}", S.skeleton)

        def window(start: float, poses) -> None:
            for i in range(4):
                clip.sample(start + i / 30.0, poses[i], stream=stream)

        context_poses = wp.empty_like(S.context.poses)
        target_poses = wp.empty_like(S.context.poses)
        window(context_end - 3 / 30.0, context_poses)
        for target_time in target_times:
            window(target_time, target_poses)
            t0 = time.perf_counter()
            S.context.update_from_poses(context_poses, stream=stream)
            S.target.update_from_poses(target_poses, stream=stream)
            engine.generate_animation(S.context, S.target, S.output)
            engine.synchronize()
            wall_ms = (time.perf_counter() - t0) * 1000.0
            frames = S.output.num_frames
            root = S.output.root_transforms()[:frames, :3]
            goal = target_poses.numpy()[0, 0, :3]
            generations.append(
                {
                    "target_clip_time": target_time,
                    "frames": frames,
                    "seconds": round(frames / 30.0, 2),
                    "root_from": np.round(root[0], 3).tolist(),
                    "root_to": np.round(root[-1], 3).tolist(),
                    "root_miss_m": round(float(np.linalg.norm(root[-1] - goal)), 4),
                    "finite": bool(np.isfinite(S.output.poses.numpy()[:frames]).all()),
                    "model_ms": {k: round(v, 2) for k, v in engine.timer.milliseconds.items()},
                    "wall_ms": round(wall_ms, 1),
                }
            )
            context_poses = wp.clone(S.output.poses[frames - 4 : frames])
    return {"example": "docs/examples/generate_once.py (soma)", "generations": generations}


ACTIONS = {
    "generate": generate,
    "skeleton": lambda params: skeleton_card(),
    "selftest": lambda params: selftest(),
    "info": lambda params: {},
}


def handler(job):
    if BOOT_ERROR:
        raise RuntimeError(f"the worker did not boot: {BOOT_ERROR}")
    params = job.get("input") or {}
    action = params.get("action", "generate")
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {sorted(ACTIONS)}")
    yield {"kind": "info", "stage": action, "gpu": BOOT["gpu"]}

    t0 = time.time()
    data = json.dumps(ACTIONS[action](params), separators=(",", ":")).encode()
    seconds = {"work": round(time.time() - t0, 3), **{f"boot_{k}": v for k, v in BOOT["seconds"].items()}}

    total = (len(data) + CHUNK_BYTES - 1) // CHUNK_BYTES
    for index in range(total):
        chunk = data[index * CHUNK_BYTES : (index + 1) * CHUNK_BYTES]
        yield {"kind": "chunk", "index": index, "total": total, "data": base64.b64encode(chunk).decode()}
    yield {
        "kind": "done",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "seconds": seconds,
        "boot": {k: v for k, v in BOOT.items() if k != "seconds"},
    }


if __name__ == "__main__":
    import runpod

    try:
        boot()
    except Exception:
        # Stay up and answer every job with the reason, so a broken boot can
        # be read from the job's error instead of from a worker that vanished.
        BOOT_ERROR = traceback.format_exc()[-3000:]
        log.error("boot failed:\n%s", BOOT_ERROR)
    runpod.serverless.start({"handler": handler, "return_aggregate_stream": True})
