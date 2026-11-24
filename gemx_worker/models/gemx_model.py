"""NVIDIA GEM-X, as the one model behind the video worker's router (../handler.py).

GEM-X reads a person's full-body motion off ordinary video: one camera, no
markers. What it writes is the SOMA body, 77 joints, the same skeleton NVIDIA's
Kimodo writes for us from a sentence. So a dance from a video can go onto our
characters the way a sentence's motion does.

This file runs in its own Python environment (/opt/envs/gemx) as a child of
the router. Job kinds it answers:

  people     who is in each shot
    clip       the clip's sha256 (uploaded first; the router adds clip_path)
    shots      [[first frame, last frame], ...] of the clip, both included
    stride     look at every n-th frame (default 1; boxes between are filled in)
    keep       at most this many people a shot (default 8)

    Answer, per shot: its people, biggest first and numbered from 1, each with
    a box for every frame they are seen on (null where they are not), their
    clothing colours as a short list of numbers (for telling the same person
    in another shot), and a small picture or two; and a few whole frames of
    the shot to show the boxes on. Pictures are JPEG, base64.

    Finding people is GEM-X's own bundled YOLOX person detector. Following
    them is ../tracks.py, kept simple on purpose.

  motion     one person's motion over one shot
    clip         as above
    first, last  the shot's frames in the clip
    boxes        one [x1, y1, x2, y2] per frame of the shot for the person to
                 follow (null where they are not seen: filled in between)
    camera       "static" (default: the camera does not move during the shot)
                 or "background" (GEM-X estimates how the camera turns from
                 what is behind the person)
    postprocess  true (default) for GEM-X's contact clean-up: planted feet
                 hold still and the lowest joint is put on the ground

    This is GEM-X's `motion-video` with the person's boxes supplied in place
    of its own choice of "the biggest person": the same steps in the same
    order (its 2D keypoint model on the boxes, the camera, its body-pose
    features, the motion model, then contact and IK), then its `--postprocess`.

    Answer: "gemx-soma77/1", for scripts/video/soma77.py to turn into the
    repo's own motion format:
      joints    the 77 SOMA joint names
      rest      where each joint is with nothing bent (this person's own
                proportions), [x, y, z]
      root      per frame, where the hips are in GEM-X's world (Y up, metres)
      turns     per frame, how far each joint has turned from that rest pose,
                in the world, [x, y, z, w] for each joint in a row
      contacts  per frame, how sure the model is that the left ankle, left
                toes, right ankle, right toes, left wrist, right wrist are
                held still against something (0..1)
      marks     per frame, where GEM-X's own hands, toes and head are, so the
                conversion can be measured against them
      camera_root
                per frame, where the hips are in the camera's own space (x to
                the right of the picture, y down, z away, metres). Everyone in
                a clip shares the camera, so this is what says where several
                people stand relative to each other (each one's `root` is in a
                world of their own). Left out if it could not be worked out

  info       what is fetched and loaded, with revisions and sizes

Licensing. The image holds none of this. On first boot the worker fetches onto
the network volume (/runpod-volume/gemx), each pinned to an exact revision:

  GEM-X's code                     github.com/NVlabs/gem-x     Apache-2.0
  GEM-X weights (body pose,        huggingface.co/nvidia/GEM-X NVIDIA Open Model License
    2D keypoints, motion)
  YOLOX-X HumanArt person detector download.openmmlab.com      as OpenMMLab publishes it (see README)
  SOMA body assets, v0.3.3         huggingface.co/nvidia/SOMA-X Apache-2.0

GEM-X's sample films (its assets/ folder) are deleted from the volume copy
right after the fetch and are never read. HF_TOKEN (the RunPod secret
`hf_token`) is used if it is set; none of these is gated today.

Moving cameras. GEM-X's best answer for a moving camera is a second NVIDIA
tool, ViPE, which is not installed here; "static" and "background" are.
"""

import base64
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import traceback
import zipfile

PROCESS_STARTED = time.time()
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # ../tracks.py

VOLUME = os.environ.get("VOLUME_DIR", "/runpod-volume")
ROOT = f"{VOLUME}/gemx"

CODE_REPO = "https://github.com/NVlabs/gem-x.git"
CODE_COMMIT = "4aef1452e5df171deff4f293c08e643eb450981e"
SRC = f"{ROOT}/src-{CODE_COMMIT[:12]}"

WEIGHTS = f"{ROOT}/weights"
SOMA_ASSETS = f"{ROOT}/soma-0.3.3"
# Every Hugging Face repo fetched: its exact revision, which files, and the sha256 and size of each large one.
REPOS = {
    "nvidia/GEM-X": {
        "revision": "b111f2dcf3ebcf57965fd53499cb645dfa5ba25c",
        "license": "NVIDIA Open Model License",
        "into": WEIGHTS,
        "patterns": ["body_s240000.ckpt", "vitpose.pth", "motion_native77_e774_s292175.ckpt", "motion_stats_raw.npz", "body_video_native77.yaml", "LICENSE", "README.md"],
        "files": {
            "body_s240000.ckpt": ("e244d27f2834eb6382c5f6b9cbf2a38681b685514a1b2e86f8f3d2592d614959", 3538753341),
            "vitpose.pth": ("8e3eec71dbd6bb745eba8c6debe3e4b97bcfd1d01f300099f2eedf50b9a80c8e", 3388483384),
            "motion_native77_e774_s292175.ckpt": ("c7790f4587e518bcea40cb8281c9be2233d37f6caa668835462542760dcf82aa", 187134331),
            "motion_stats_raw.npz": ("b7719b634e0fc1f001005605d117d77448c8d4a110923149df58529c68112ed6", 21320),
        },
    },
    "nvidia/SOMA-X": {
        "revision": "d281db2d01553f7230c56e764cec00fe27ef23f7",  # the v0.3.3 tag
        "license": "Apache-2.0",
        "into": SOMA_ASSETS,
        # What contact and IK need: the rig, the shape data, the twist rules. Not the sample animation.
        "patterns": ["SOMA_neutral.npz", "SOMA_template_rig.usda", "SOMA_procedural_transforms.json", "LICENSE"],
        "files": {
            "SOMA_neutral.npz": ("5829af4a5333abdba5ad449360b868faacee99d395971e62f35c0e7169432b63", 26608121),
            "SOMA_template_rig.usda": ("a952cb7bdf4ccd801e355d53122d395b985b69d0d9181439edad5081bb171856", 28306038),
        },
    },
}
# The person detector GEM-X's docs name: an ONNX file inside a zip OpenMMLab publishes.
DETECTOR_URL = "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/yolox_x_8xb8-300e_humanart-a39d44ed.zip"
DETECTOR_ZIP_MD5, DETECTOR_ZIP_BYTES = "b6697607fa4ae8fdd3c91091e4114779", 368200375
DETECTOR = f"{WEIGHTS}/yolox_humanart.onnx"
CONFIG = f"{WEIGHTS}/body_video_native77.yaml"

PINS = hashlib.sha256(json.dumps([CODE_COMMIT, {k: v["revision"] for k, v in REPOS.items()}, DETECTOR_ZIP_MD5], sort_keys=True).encode()).hexdigest()[:12]
FETCHED = f"{ROOT}/.forge-fetched-{PINS}.json"

FPS = 30
MAX_SHOT_FRAMES = 60 * FPS  # GEM-X's own limit for one clip
MIN_SHOT_FRAMES = 8
MAX_PEOPLE = 8
KEYFRAME_WIDE, THUMB_TALL, JPEG_QUALITY = 640, 192, 78
CAMERAS = ("static", "background")
CONTACT_ORDER = ["left_ankle", "left_toes", "right_ankle", "right_toes", "left_wrist", "right_wrist"]
MARKS = ("LeftHand", "RightHand", "LeftToeBase", "RightToeBase", "Head")

logging.basicConfig(level=logging.INFO, format="[gemx] %(message)s")
log = logging.getLogger("forge")


def sh(*args: str, cwd: str | None = None, env: dict | None = None) -> str:
    done = subprocess.run(args, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:3])}... failed: {(done.stderr or done.stdout).strip()[-1500:]}")
    return done.stdout.strip()


def digest_of(path: str, kind: str = "sha256") -> str:
    digest = hashlib.new(kind)
    with open(path, "rb") as f:
        while chunk := f.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def folder_bytes(path: str) -> int:
    return sum(os.path.getsize(os.path.join(base, n)) for base, _, names in os.walk(path) for n in names if not os.path.islink(os.path.join(base, n)))


# ---- first boot: fetch ---------------------------------------------------------


def fetch_code() -> dict:
    """GEM-X's code at the pinned commit, without its sample films, docs and tests."""
    done = f"{SRC}/.forge-fetched.json"
    if os.path.exists(done):
        with open(done) as f:
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
    # Keep the code. Drop NVIDIA's sample films and pictures (assets/), the docs and the tests: none is ever read.
    for unused in (".git", "assets", "docs", "tests", "scripts"):
        shutil.rmtree(f"{partial}/{unused}", ignore_errors=True)
    record = {"repo": CODE_REPO, "commit": CODE_COMMIT, "license": "Apache-2.0", "seconds": round(time.time() - started, 1), "bytes": folder_bytes(partial)}
    with open(f"{partial}/.forge-fetched.json", "w") as f:
        json.dump(record, f, indent=2)
    shutil.rmtree(SRC, ignore_errors=True)
    os.rename(partial, SRC)
    return {**record, "fetched_now": True}


def fetch_detector() -> dict:
    """The YOLOX person detector: one .onnx out of OpenMMLab's zip, the zip checked against the md5 its server gives."""
    import urllib.request

    started = time.time()
    archive = f"{WEIGHTS}/yolox_humanart.zip"
    log.info("first boot: fetching the person detector (%d MB)", DETECTOR_ZIP_BYTES // 1_000_000)
    with urllib.request.urlopen(urllib.request.Request(DETECTOR_URL, headers={"User-Agent": "forge-gemx-worker"}), timeout=120) as response, open(archive, "wb") as out:
        shutil.copyfileobj(response, out, 8 * 1024 * 1024)
    if os.path.getsize(archive) != DETECTOR_ZIP_BYTES or digest_of(archive, "md5") != DETECTOR_ZIP_MD5:
        raise RuntimeError(f"the person detector's zip is {os.path.getsize(archive)} bytes with md5 {digest_of(archive, 'md5')}, not the pinned one")
    with zipfile.ZipFile(archive) as z:
        member = next(name for name in z.namelist() if name.endswith("/end2end.onnx"))
        with z.open(member) as source, open(DETECTOR + ".partial", "wb") as target:
            shutil.copyfileobj(source, target, 8 * 1024 * 1024)
    os.replace(DETECTOR + ".partial", DETECTOR)
    os.remove(archive)
    return {"url": DETECTOR_URL, "zip_md5": DETECTOR_ZIP_MD5, "sha256": digest_of(DETECTOR), "bytes": os.path.getsize(DETECTOR), "seconds": round(time.time() - started, 1)}


def fetch_weights() -> dict:
    """The models and the SOMA body, each at its pinned revision, checked by sha256; and the person detector."""
    if os.path.exists(FETCHED):
        with open(FETCHED) as f:
            return {**json.load(f), "fetched_now": False}
    from huggingface_hub import snapshot_download

    token = os.environ.get("HF_TOKEN") or None
    started = time.time()
    repos = {}
    for repo, card in REPOS.items():
        t = time.time()
        log.info("first boot: fetching %s at %s", repo, card["revision"][:12])
        folder = snapshot_download(repo, revision=card["revision"], allow_patterns=card["patterns"], token=token, max_workers=8, local_dir=card["into"])
        for name, (expected, size) in card["files"].items():
            path = os.path.join(folder, name)
            if os.path.getsize(path) != size:
                raise RuntimeError(f"{repo}/{name}: {os.path.getsize(path)} bytes, expected {size}")
            got = digest_of(path)
            if got != expected:
                raise RuntimeError(f"{repo}/{name}: sha256 {got}, expected {expected}")
        repos[repo] = {"revision": card["revision"], "license": card["license"], "bytes": folder_bytes(folder), "seconds": round(time.time() - t, 1)}
    detector = fetch_detector()
    record = {"repos": repos, "detector": detector, "bytes": sum(r["bytes"] for r in repos.values()) + detector["bytes"], "seconds": round(time.time() - started, 1), "token_used": bool(token)}
    with open(FETCHED + ".partial", "w") as f:
        json.dump(record, f, indent=2)
    os.rename(FETCHED + ".partial", FETCHED)
    return {**record, "fetched_now": True}


def fetch_main() -> None:
    """`gemx_model.py --fetch`: run as its own process, with the network on. Prints one JSON line."""
    try:
        os.makedirs(WEIGHTS, exist_ok=True)
        print(json.dumps({"ok": True, "code": fetch_code(), "weights": fetch_weights()}))
    except Exception:
        print(json.dumps({"ok": False, "error": traceback.format_exc()[-3000:]}))


# ---- boot ----------------------------------------------------------------------


class State:
    """Everything loaded once and reused by every job. The big models load on the first job that needs them."""

    detector = pose2d = pose = predictor = contact = None


S = State()
BOOT: dict = {}


def boot() -> None:
    seconds: dict = {}
    t = time.time()
    os.makedirs(ROOT, exist_ok=True)
    # The fetch runs as a process of its own so that this one can load with the
    # network off: nothing but the pinned files on the volume can be read.
    done = subprocess.run([sys.executable, "-u", os.path.abspath(__file__), "--fetch"], stdout=subprocess.PIPE, text=True)
    lines = [line for line in done.stdout.splitlines() if line.startswith("{")]
    fetched = json.loads(lines[-1]) if lines else {"ok": False, "error": f"the fetch ended with exit {done.returncode} and no answer"}
    if not fetched["ok"]:
        raise RuntimeError(fetched["error"])
    seconds["fetch"] = round(time.time() - t, 1)

    t = time.time()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ.setdefault("TORCH_ALLOW_TF32_CUBLAS_OVERRIDE", "0")  # as GEM-X's own Dockerfile sets it
    sys.path.insert(0, SRC)
    import cv2
    import numpy as np
    import onnxruntime
    import torch
    from scipy.spatial.transform import Rotation

    if hasattr(onnxruntime, "preload_dlls"):
        onnxruntime.preload_dlls()  # find CUDA and cuDNN among PyTorch's own packages
    import gem  # noqa: F401  fail at boot, not in a job, if the code did not arrive
    from gem.inference.body_video import load_body_video_config
    from gem.common.soma.body import SomaFixedGs1ShapeSpec

    # SOMA's adapter wants the body's overall scale exactly 1.0 (it is fixed by design) and refuses anything
    # else. On long shots GEM-X's own steps hand it values a hair off (float32 rounding when windows are
    # blended), inside its code where we cannot set it first. Snap values within 1e-3 of one to exactly one
    # before the check; anything further off is still refused. BOOT records the largest slip seen.
    exact_check = SomaFixedGs1ShapeSpec.split_external_scale

    def split_external_scale(self, scale57):
        if torch.is_tensor(scale57) and scale57.shape[-1:] == (self.external_scale_dim,):
            slip = (scale57[..., :1].float() - 1.0).abs()
            if slip.numel() and bool((slip > 0).any()) and bool((slip < 1e-3).all()):
                BOOT["scale_slip_snapped"] = max(BOOT.get("scale_slip_snapped", 0.0), float(slip.max()))
                scale57 = scale57.clone()
                scale57[..., 0] = 1.0
        return exact_check(self, scale57)

    SomaFixedGs1ShapeSpec.split_external_scale = split_external_scale

    seconds["imports"] = round(time.time() - t, 1)
    if not torch.cuda.is_available():
        raise RuntimeError("no GPU: torch.cuda.is_available() is false")
    S.cv2, S.np, S.torch, S.Rotation = cv2, np, torch, Rotation
    S.device = "cuda"
    S.config = load_body_video_config(CONFIG)
    # The config that ships with the weights points at files beside itself; the detector is ours to place.
    S.config.setdefault("detector", {})["checkpoint"] = DETECTOR
    S.detector_on = "cuda" if "CUDAExecutionProvider" in onnxruntime.get_available_providers() else "cpu"
    seconds["boot"] = round(time.time() - PROCESS_STARTED, 1)
    BOOT.update(
        {
            "gpu": torch.cuda.get_device_name(0),
            "torch": str(torch.__version__),
            "gemx": {"code_commit": CODE_COMMIT, "weights_revision": REPOS["nvidia/GEM-X"]["revision"], "license": REPOS["nvidia/GEM-X"]["license"]},
            "detector_runs_on": S.detector_on,
            "fetched_this_boot": bool(fetched["code"]["fetched_now"] or fetched["weights"]["fetched_now"]),
            "fetched": {"code": {k: fetched["code"][k] for k in ("commit", "seconds", "bytes", "license")}, "weights": {k: fetched["weights"][k] for k in ("repos", "detector", "bytes", "seconds", "token_used")}},
            "seconds": seconds,
        }
    )
    log.info("ready: %s", json.dumps(BOOT))


# ---- the clip ------------------------------------------------------------------


class Frames:
    """Frames first..last of a clip as RGB arrays, read from disk as they are asked for (what GEM-X's own
    VideoFrames is for a whole file). Reading forward is cheap; going back seeks."""

    def __init__(self, path: str, first: int, last: int):
        self.path = path
        self.capture = S.cv2.VideoCapture(path)
        if not self.capture.isOpened():
            raise OSError("the clip cannot be opened")
        total = int(self.capture.get(S.cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self.capture.get(S.cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.capture.get(S.cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = float(self.capture.get(S.cv2.CAP_PROP_FPS))
        if not 0 <= first <= last < total:
            raise ValueError(f"frames {first}..{last} are not inside the clip (it has {total})")
        if abs(self.fps - FPS) > 0.01:
            raise ValueError(f"the clip runs at {self.fps} frames a second; it must be {FPS} (scripts/video/clip.py makes it so)")
        self.first, self.count = first, last - first + 1
        self.at = None  # the clip frame the next read gives

    def __len__(self):
        return self.count

    def __iter__(self):
        return (self[i] for i in range(self.count))

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(self.count))]
        if index < 0:
            index += self.count
        if not 0 <= index < self.count:
            raise IndexError("frame index out of range")
        want = self.first + index
        if self.at is None or want < self.at or want - self.at > 60:
            self.capture.set(S.cv2.CAP_PROP_POS_FRAMES, want)
            self.at = want
        while self.at < want:
            if not self.capture.grab():
                raise OSError(f"cannot read frame {self.at} of the clip")
            self.at += 1
        ok, frame = self.capture.read()
        if not ok:
            raise OSError(f"cannot read frame {want} of the clip")
        self.at = want + 1
        return S.cv2.cvtColor(frame, S.cv2.COLOR_BGR2RGB)

    def close(self):
        self.capture.release()


def jpeg(rgb, wide: int = 0, tall: int = 0) -> str:
    """A frame (or a piece of one) as a small JPEG, base64."""
    cv2 = S.cv2
    h, w = rgb.shape[:2]
    scale = min(1.0, wide / w if wide else 1.0, tall / h if tall else 1.0)
    if scale < 1.0:
        rgb = cv2.resize(rgb, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    ok, data = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise RuntimeError("a picture could not be written as JPEG")
    return base64.b64encode(data.tobytes()).decode()


def cut_out(rgb, box, pad: float = 0.06):
    h, w = rgb.shape[:2]
    px, py = (box[2] - box[0]) * pad, (box[3] - box[1]) * pad
    x1, y1, x2, y2 = max(0, int(box[0] - px)), max(0, int(box[1] - py)), min(w, int(box[2] + px) + 1), min(h, int(box[3] + py) + 1)
    return rgb[y1:y2, x1:x2]


def clothing_colors(rgb, box) -> list:
    """What someone is wearing, as numbers: the colours of the middle of their top half and of their bottom half.

    Per half: 36 bins of hue by how strong the colour is, for pixels with real colour, and 4 bins of
    dark-to-light for the ones without (black, greys, white). 80 numbers that add up to 2. Two people in the
    same clothes come out alike; ../tracks.py's `alike` compares them."""
    cv2, np = S.cv2, S.np
    x1, y1, x2, y2 = [float(c) for c in box]
    w, h = x2 - x1, y2 - y1
    out = []
    for top, bottom in ((0.18, 0.52), (0.52, 0.9)):
        piece = rgb[max(0, int(y1 + top * h)) : max(1, int(y1 + bottom * h)), max(0, int(x1 + 0.28 * w)) : max(1, int(x1 + 0.72 * w))]
        if piece.size == 0:
            out += [0.0] * 40
            continue
        hsv = cv2.cvtColor(piece, cv2.COLOR_RGB2HSV).reshape(-1, 3).astype(np.int32)
        strong = (hsv[:, 1] > 60) & (hsv[:, 2] > 50)
        colour = np.zeros(36)
        if strong.any():
            bins = (hsv[strong, 0] * 12 // 180) * 3 + np.clip((hsv[strong, 1] - 60) * 3 // 196, 0, 2)
            colour = np.bincount(bins, minlength=36).astype(np.float64)
        grey = np.bincount(np.clip(hsv[~strong, 2] * 4 // 256, 0, 3), minlength=4).astype(np.float64) if (~strong).any() else np.zeros(4)
        both = np.concatenate([colour, grey])
        out += (both / max(1.0, both.sum())).round(4).tolist()
    return out


# ---- people ----------------------------------------------------------------------


def detector():
    if S.detector is None:
        from gem.common.detectors import YOLOXONNX

        options = {k: v for k, v in S.config["detector"].items() if k not in ("checkpoint", "device")}
        try:
            S.detector = YOLOXONNX(DETECTOR, device=S.detector_on, **options)
        except RuntimeError as error:
            if S.detector_on == "cpu":
                raise
            # ONNX Runtime lists CUDA but could not start it (its CUDA or cuDNN build does not match the
            # libraries it found). The person detector is one pass over the clip, so the CPU will do; say why.
            import onnxruntime

            BOOT["detector_gpu_refused"] = {"error": str(error), "onnxruntime": onnxruntime.__version__, "torch_cuda": S.torch.version.cuda}
            log.warning("person detector falls back to the CPU: %s", json.dumps(BOOT["detector_gpu_refused"]))
            S.detector_on = "cpu"
            BOOT["detector_runs_on"] = "cpu"
            S.detector = YOLOXONNX(DETECTOR, device="cpu", **options)
    return S.detector


def people(params: dict) -> dict:
    import tracks as T

    shots = params.get("shots") or []
    if not shots or len(shots) > 200:
        raise ValueError("people needs 1 to 200 shots, each [first frame, last frame]")
    stride = int(params.get("stride", 1))
    keep = int(params.get("keep", MAX_PEOPLE))
    if not 1 <= stride <= 6 or not 1 <= keep <= 20:
        raise ValueError("stride is 1..6 and keep is 1..20")
    find = detector()
    out, detect_seconds = [], 0.0
    for number, (first, last) in enumerate(shots):
        first, last = int(first), int(last)
        frames = Frames(params["clip_path"], first, last)
        try:
            tracker = T.Tracker()
            t = time.perf_counter()
            for i in range(0, len(frames), stride):
                boxes, scores = find.detect(frames[i][..., ::-1].copy())
                good = [(b, s) for b, s in zip(boxes.tolist(), scores.tolist()) if b[2] > b[0] and b[3] > b[1]]
                tracker.see(first + i, [b for b, _ in good], [s for _, s in good])
            detect_seconds += time.perf_counter() - t
            # Clothing colours for every piece of track, from a few of its frames, so that pieces can be joined.
            tracked = T.spread(tracker.tracks, stride, first, last)
            wanted: dict = {}
            for track_id, boxes in tracked.items():
                seen = sorted(boxes)
                for f in {seen[len(seen) // 4], seen[len(seen) // 2], seen[(3 * len(seen)) // 4]}:
                    wanted.setdefault(f, []).append(track_id)
            sums: dict = {}
            for f in sorted(wanted):
                rgb = frames[f - first]
                for track_id in wanted[f]:
                    colours = clothing_colors(rgb, tracked[track_id][f])
                    sums[track_id] = [a + b for a, b in zip(sums.get(track_id, [0.0] * len(colours)), colours)]
            tracked, joined = T.join_pieces(tracked, sums)
            for kept, others in joined.items():
                for other in others:
                    sums[kept] = [a + b for a, b in zip(sums[kept], sums.pop(other))]
            found = T.people_of(tracked, first, last, frames.width, frames.height, keep=keep)
            # The pictures: each person twice, small; and a few whole frames to draw the boxes on.
            keys = T.key_frames(found, first, last)
            thumbs = {p["id"]: T.thumb_frames(p, first) for p in found}
            pictures = {f: None for f in keys}
            for person in found:
                total = sum(sums[person["track"]]) or 1.0
                person["colors"] = [round(2.0 * c / total, 4) for c in sums[person["track"]]]
                person["joined_from_pieces"] = 1 + len(joined.get(person["track"], []))
                person["thumbs"] = []
            for f in sorted(set(keys) | {f for fs in thumbs.values() for f in fs}):
                rgb = frames[f - first]
                if f in pictures:
                    pictures[f] = jpeg(rgb, wide=KEYFRAME_WIDE)
                for person in found:
                    if f in thumbs[person["id"]]:
                        person["thumbs"].append({"frame": f, "jpeg": jpeg(cut_out(rgb, person["boxes"][f - first]), tall=THUMB_TALL)})
            for person in found:
                del person["track"]
            out.append({"index": number, "first_frame": first, "last_frame": last, "width": frames.width, "height": frames.height, "people": found, "keyframes": [{"frame": f, "jpeg": pictures[f]} for f in keys]})
        finally:
            frames.close()
    looked_at = sum((int(b) - int(a)) // stride + 1 for a, b in shots)
    return {"format": "gemx-people/1", "fps": FPS, "shots": out, "detector": {"model": "YOLOX-X HumanArt (ONNX)", "runs_on": S.detector_on, "frames_looked_at": looked_at, "seconds": round(detect_seconds, 2)}}


# ---- motion ----------------------------------------------------------------------


def conditions_from_boxes(frames: Frames, boxes_xyxy, camera_mode: str) -> tuple:
    """GEM-X's build_body_conditions (gem/inference/body_video.py), with the person's boxes handed in where it
    would detect and pick the biggest person itself. The same steps, in its order, with its own functions."""
    torch, np = S.torch, S.np
    from dataclasses import asdict

    from gem.common.detectors import smooth_boxes, square_crops
    from gem.common.pose2d import load_native77_detector
    from gem.inference.body_video import body_release, extract_body_features, motion_intrinsics
    from gem.inference.camera_motion import camera_motion
    from gem.motion.api import MotionConditionSpec
    from gem.motion.frontend.joint_sets import get_observation_schema
    from gem.pose.api import load_pose_checkpoint

    config = S.config
    expected = MotionConditionSpec(**config["motion"]["condition_spec"])
    schema = get_observation_schema(expected.observation_joint_set)
    release = body_release(config)
    intrinsics = motion_intrinsics(frames.width, frames.height, config.get("camera", {}).get("intrinsics"))
    boxes_xyxy = np.asarray(boxes_xyxy, dtype=np.float32)
    boxes_xyxy[:, [0, 2]] = np.clip(boxes_xyxy[:, [0, 2]], 0, frames.width - 1)
    boxes_xyxy[:, [1, 3]] = np.clip(boxes_xyxy[:, [1, 3]], 0, frames.height - 1)
    boxes_xys = square_crops(smooth_boxes(boxes_xyxy), 1.2)

    seconds = {}
    t = time.perf_counter()
    if S.pose2d is None:
        observations = config["observations"]
        S.pose2d = load_native77_detector(observations["checkpoint"], release_id=observations["release_id"], device=S.device, batch_size=observations.get("batch_size", 4))
    keypoints = S.pose2d.predict(frames, boxes_xys)
    seconds["keypoints_2d"] = round(time.perf_counter() - t, 2)

    t = time.perf_counter()
    camera = camera_motion(frames, intrinsics.numpy(), boxes_xyxy, mode=camera_mode, keypoints=keypoints.numpy(), **config.get("camera", {}).get("options", {}))
    seconds["camera"] = round(time.perf_counter() - t, 2)

    t = time.perf_counter()
    if S.pose is None:
        S.pose = load_pose_checkpoint(config["pose"]["checkpoint"], release, device=S.device)
    features, feature_version = extract_body_features(frames, boxes_xys, intrinsics, S.pose, batch_size=config["pose"].get("batch_size", 4), device=S.device)
    seconds["body_features"] = round(time.perf_counter() - t, 2)

    actual = MotionConditionSpec(feature_version, S.pose2d.release_id, schema.name)
    sequence = {
        "condition_spec": asdict(actual),
        "length": torch.tensor([len(frames)]),
        "f_imgseq": features.unsqueeze(0),
        "kp2d_native77": keypoints.unsqueeze(0),
        "bbx_xys": torch.from_numpy(np.asarray(boxes_xys, dtype=np.float32)).unsqueeze(0),
        "K_fullimg": intrinsics.expand(len(frames), 3, 3).unsqueeze(0).clone(),
        "cam_angvel": camera["cam_angvel"].unsqueeze(0),
        "frame_times": (torch.arange(len(frames), dtype=torch.float64) / FPS).unsqueeze(0),
        "sampling_fps": float(FPS),
    }
    seen = (keypoints[..., 2] > 0.5).float().mean().item()
    return sequence, camera, seconds, round(seen, 3)


def proper(matrices):
    """The nearest true rotations to a stack of 3x3 matrices (a body's joint transforms can carry scale)."""
    torch = S.torch
    u, _, vt = torch.linalg.svd(matrices.double())
    flip = torch.ones(matrices.shape[:-2] + (3,), dtype=torch.float64, device=matrices.device)
    flip[..., 2] = torch.linalg.det(u @ vt)
    return (u * flip[..., None, :]) @ vt


def motion(params: dict) -> dict:
    import tracks as T

    torch, np = S.torch, S.np
    from gem.inference.motion import load_predictor, run_motion
    from gem.inference.postprocess import postprocess_motion_result
    from gem.motion.frontend.joint_sets import SOMA77_JOINT_NAMES
    from gem.motion.postprocess.api import SomaContactPostprocessor

    first, last = int(params.get("first", -1)), int(params.get("last", -1))
    count = last - first + 1
    if not MIN_SHOT_FRAMES <= count <= MAX_SHOT_FRAMES:
        raise ValueError(f"a shot is {MIN_SHOT_FRAMES} frames to {MAX_SHOT_FRAMES // FPS} seconds, not {count} frames")
    boxes = params.get("boxes") or []
    if len(boxes) != count:
        raise ValueError(f"one box per frame: the shot has {count} frames, {len(boxes)} boxes came")
    for box in boxes:
        if box is not None and not (len(box) == 4 and box[2] > box[0] and box[3] > box[1]):
            raise ValueError("a box is [x1, y1, x2, y2] with x2 > x1 and y2 > y1, or null where the person is not seen")
    camera_mode = params.get("camera", "static")
    if camera_mode not in CAMERAS:
        raise ValueError(f"camera is one of {', '.join(CAMERAS)} (GEM-X's `vipe`, for a camera that travels, is not installed here)")
    tidy = bool(params.get("postprocess", True))
    filled, seen = T.fill(boxes)

    started = time.perf_counter()
    frames = Frames(params["clip_path"], first, last)
    try:
        sequence, camera, seconds, keypoints_seen = conditions_from_boxes(frames, filled, camera_mode)
        width, height = frames.width, frames.height
    finally:
        frames.close()

    t = time.perf_counter()
    if S.predictor is None:
        S.predictor = load_predictor(S.config["motion"]["checkpoint"], S.config["motion"], stats_path=S.config["motion"].get("stats"), device=S.device)
    result = run_motion(S.predictor, sequence, device=S.device)
    seconds["motion"] = round(time.perf_counter() - t, 2)
    for key in ("pred_soma_params_global", "pred_soma_params_incam"):
        params_out = result.get(key)
        if isinstance(params_out, dict) and torch.is_tensor(params_out.get("scale_params")):
            exact = params_out["scale_params"].clone()
            exact[..., 0] = 1.0  # SOMA's adapter wants the overall scale exactly 1.0; prediction can leave it a hair off
            params_out["scale_params"] = exact

    t = time.perf_counter()
    if S.contact is None:
        S.contact = SomaContactPostprocessor(SOMA_ASSETS, device=S.device)
    diagnostics = None
    if tidy:
        result = postprocess_motion_result(result, soma_assets=SOMA_ASSETS, device=S.device, processor=S.contact)
        diagnostics = result.get("postprocessing")
    seconds["contact_and_ik"] = round(time.perf_counter() - t, 2)

    # What the body looks like: every joint's place and turn in GEM-X's world, and the same with nothing bent.
    t = time.perf_counter()
    world = {k: v.detach().to(S.device).float() for k, v in result["pred_soma_params_global"].items()}
    # SOMA's adapter takes the body's overall scale as exactly 1.0 (it is fixed, not learned) and refuses
    # anything else; what comes back from prediction and post-processing can be a hair off in float32.
    world["scale_params"] = world["scale_params"].clone()
    world["scale_params"][..., 0] = 1.0
    body = S.contact.body_model
    with torch.inference_mode(), torch.autocast(torch.device(S.device).type, enabled=False):
        posed = body(**world, return_joints_only=True)
        still = {
            "global_orient": torch.zeros_like(world["global_orient"][:, :2]),
            "body_pose": torch.zeros_like(world["body_pose"][:, :2]),
            "identity_coeffs": world["identity_coeffs"].mean(dim=1, keepdim=True).expand(-1, 2, -1).contiguous(),
            "scale_params": world["scale_params"].mean(dim=1, keepdim=True).expand(-1, 2, -1).contiguous(),
            "transl": torch.zeros_like(world["transl"][:, :2]),
        }
        rest = body(**still, return_joints_only=True)
    joints = posed["joints"][0]  # [T, 77, 3]
    seen_from_camera = None
    try:  # the same body through the camera's own parameters: where the hips are as the camera sees them
        incam = {k: v.detach().to(S.device).float() for k, v in result["pred_soma_params_incam"].items()}
        with torch.inference_mode(), torch.autocast(torch.device(S.device).type, enabled=False):
            hips = body(**incam, return_joints_only=True)["joints"][0][:, 0].cpu().numpy()
        if hips.shape == (count, 3) and np.isfinite(hips).all():
            seen_from_camera = hips.round(4).tolist()
    except Exception as error:  # noqa: BLE001  nothing else in the answer depends on it
        log.warning("no camera_root: %s", error)
    names = list(SOMA77_JOINT_NAMES)
    if joints.shape != (count, len(names), 3):
        raise RuntimeError(f"GEM-X answered joints shaped {tuple(joints.shape)}, expected ({count}, {len(names)}, 3)")

    def rotations(transforms):
        public = transforms[..., -len(names) :, :3, :3]  # the body's own list starts with one extra root above the hips
        return proper(public)

    turned = rotations(posed["transforms"][0]) @ rotations(rest["transforms"][0][0]).transpose(-1, -2)
    quats = S.Rotation.from_matrix(turned.reshape(-1, 3, 3).cpu().numpy()).as_quat().reshape(count, len(names), 4)
    roots = joints[:, 0].cpu().numpy()
    if not (np.isfinite(quats).all() and np.isfinite(roots).all()):
        raise RuntimeError("GEM-X answered numbers that are not finite")
    rest_joints = rest["joints"][0, 0].cpu().numpy()
    touching = torch.sigmoid(result["static_conf_logits"][0].float()).cpu().numpy()
    seconds["export"] = round(time.perf_counter() - t, 2)
    took = time.perf_counter() - started
    return {
        "format": "gemx-soma77/1",
        "fps": FPS,
        "up": "+Y",
        "first_frame": first,
        "last_frame": last,
        "joints": names,
        "rest": rest_joints.round(5).tolist(),
        "root": roots.round(5).tolist(),
        "turns": quats.reshape(count, -1).round(6).tolist(),
        "contact_order": CONTACT_ORDER,
        "contacts": touching.round(3).tolist(),
        "marks": {name: joints[:, names.index(name)].cpu().numpy().round(4).tolist() for name in MARKS},
        **({"camera_root": seen_from_camera} if seen_from_camera else {}),
        "boxes_seen": seen,
        "made_by": {
            "model": "GEM-X body motion (native77)",
            "code_commit": CODE_COMMIT,
            "weights_revision": REPOS["nvidia/GEM-X"]["revision"],
            "camera": camera_mode,
            "camera_notes": {k: v for k, v in (camera.get("diagnostics") or {}).items() if isinstance(v, (str, int, float, bool))},
            "postprocess": tidy,
            "postprocess_notes": diagnostics,
            "picture": [width, height],
            "frames_with_a_box": sum(seen),
            "share_of_2d_points_seen": keypoints_seen,
            "world": result.get("coordinates", {}).get("global"),
        },
        "seconds": seconds,
        "seconds_per_second_of_clip": round(took / (count / FPS), 2),
        "gpu_memory_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2),
    }


KINDS = {"people": people, "motion": motion, "info": lambda params: BOOT}


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
