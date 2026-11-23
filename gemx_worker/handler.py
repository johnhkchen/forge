"""The video worker's front door on RunPod Serverless: a clip in, who is in it and how they move out.

One model lives here, NVIDIA GEM-X, which reads a person's full-body motion
off ordinary video and writes it on the SOMA skeleton (77 joints), the same
skeleton our other motion models use. Like the motion worker next door
(motionbricks_worker/), this file only routes: the model runs as a child
process in a Python environment of its own (models/gemx_model.py), and the two
talk in JSON lines.

Input (job["input"]):
    kind     which job
             "upload"   one part of a clip, kept on the network volume. A clip
                        is sent once, in parts small enough for RunPod, and
                        named by its sha256. This file answers it; no model.
                          clip   the whole clip's sha256 (64 hex digits)
                          index  which part, from 0
                          total  how many parts
                          data   the part, base64
             "have"     is a clip already on the volume? {clip}
             "people"   who is in each shot: everyone found and followed
                        (see models/gemx_model.py)
             "motion"   one person's motion over one shot, from their boxes
             "info"     what is fetched and loaded
    ...      the rest is that kind's own input

Output: the handler is a generator, like our other workers. /stream/{job}
gives, in order:
    {"kind": "info", "stage": "...", "gpu": "..."}
    {"kind": "chunk", "index": i, "total": n, "data": "<base64>"}
    {"kind": "done", "bytes": N, "sha256": "...", "seconds": {...}, "boot": {...}}
Join the chunks' data in index order, base64-decode, check sha256: that is one
JSON document, the answer.

Nothing of the model's is in the image: not GEM-X's code, not its weights, not
the person detector, not the SOMA body. The model fetches them onto the
network volume the first time it boots (models/gemx_model.py says what, from
where, and under which license).

Clips are other people's videos. They are kept on your own volume only, under
gemx/clips/, and a clip not asked for in two weeks is deleted the next time
one is uploaded.

To try the plumbing with no GPU, point GEMX_MODEL_SCRIPT at a stand-in that
speaks the same JSON lines (scripts/video/stub_worker.py) and VOLUME_DIR at a
temp folder; scripts/video/test_video.py does.
"""

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time

VOLUME = os.environ.get("VOLUME_DIR", "/runpod-volume")
CLIPS = os.path.join(VOLUME, "gemx", "clips")
MODEL_PYTHON = os.environ.get("GEMX_MODEL_PYTHON", "/opt/envs/gemx/bin/python")
MODEL_SCRIPT = os.environ.get("GEMX_MODEL_SCRIPT", "/app/models/gemx_model.py")
MODEL_KINDS = ("people", "motion", "info")
CHUNK_BYTES = 512 * 1024  # base64 grows it to ~700 KB, under /stream's 1 MB per item
MAX_PARTS = 400
KEEP_CLIPS_DAYS = 14
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def clip_path(clip: str) -> str:
    """Where a clip is kept. The name is its sha256 and nothing else, so no input can name another file."""
    if not isinstance(clip, str) or not SHA256.match(clip):
        raise ValueError("clip must be the clip's sha256: 64 hex digits")
    return os.path.join(CLIPS, clip + ".mp4")


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def forget_old_clips() -> int:
    """Deletes clips (and parts of clips) nobody has asked for in two weeks."""
    gone = 0
    if not os.path.isdir(CLIPS):
        return gone
    for name in os.listdir(CLIPS):
        path = os.path.join(CLIPS, name)
        if time.time() - os.path.getatime(path) > KEEP_CLIPS_DAYS * 86400 and time.time() - os.path.getmtime(path) > KEEP_CLIPS_DAYS * 86400:
            os.remove(path)
            gone += 1
    return gone


def upload(params: dict) -> dict:
    """Keeps one part of a clip; when every part is there, joins them and checks the sha256."""
    path = clip_path(params.get("clip"))
    if os.path.exists(path):
        return {"complete": True, "bytes": os.path.getsize(path), "already_there": True}
    index, total = params.get("index"), params.get("total")
    if not isinstance(index, int) or not isinstance(total, int) or not 0 <= index < total <= MAX_PARTS:
        raise ValueError(f"index and total must be whole numbers with 0 <= index < total <= {MAX_PARTS}")
    try:
        data = base64.b64decode(params.get("data") or "", validate=True)
    except Exception as error:
        raise ValueError("data is not base64") from error
    if not data:
        raise ValueError("the part is empty")
    os.makedirs(CLIPS, exist_ok=True)
    forgotten = forget_old_clips()
    part = f"{path}.part{index:03d}of{total:03d}"
    with open(part + ".partial", "wb") as f:
        f.write(data)
    os.replace(part + ".partial", part)
    parts = [f"{path}.part{i:03d}of{total:03d}" for i in range(total)]
    have = [i for i, p in enumerate(parts) if os.path.exists(p)]
    if len(have) < total:
        return {"complete": False, "have": have, "forgot_old_clips": forgotten}
    with open(path + ".partial", "wb") as out:
        for p in parts:
            with open(p, "rb") as f:
                out.write(f.read())
    got = sha256_of(path + ".partial")
    for p in parts:
        os.remove(p)
    if got != params["clip"]:
        os.remove(path + ".partial")
        raise ValueError(f"the parts joined to sha256 {got}, not the clip's own; send it again")
    os.replace(path + ".partial", path)
    return {"complete": True, "bytes": os.path.getsize(path), "forgot_old_clips": forgotten}


def have(params: dict) -> dict:
    path = clip_path(params.get("clip"))
    there = os.path.exists(path)
    if there:
        os.utime(path)  # asked for: keep it another two weeks
    return {"complete": there, "bytes": os.path.getsize(path) if there else 0}


class Model:
    """The model's child process, started once and asked one job at a time."""

    def __init__(self):
        self.process, self.boot, self.error = None, None, None
        self.lock = threading.Lock()

    def start(self) -> None:
        with self.lock:
            if self.process is not None:
                return
            started = time.time()
            self.process = subprocess.Popen([MODEL_PYTHON, "-u", MODEL_SCRIPT], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            hello = self._read()
            if hello.get("ready"):
                self.boot = hello["boot"]
                self.boot.setdefault("seconds", {})["model_process"] = round(time.time() - started, 1)
            else:
                self.error = hello.get("error", "the model process ended before it was ready")
            print(f"[router] gemx: {'ready' if self.boot else 'failed'} after {time.time() - started:.1f}s", flush=True)

    def _read(self) -> dict:
        line = self.process.stdout.readline()
        if not line:
            return {"ok": False, "ready": False, "error": f"the gemx process ended (exit {self.process.poll()})"}
        return json.loads(line)

    def ask(self, kind: str, params: dict) -> dict:
        self.start()
        if self.error:
            raise RuntimeError(f"gemx did not boot: {self.error}")
        with self.lock:
            self.process.stdin.write(json.dumps({"kind": kind, "input": params}, separators=(",", ":")) + "\n")
            self.process.stdin.flush()
            answer = self._read()
        if not answer.get("ok"):
            raise RuntimeError(answer.get("error", "the model gave no answer"))
        return answer

    def stop(self) -> None:
        if self.process is not None:
            self.process.stdin.close()
            self.process.wait(timeout=10)
            self.process = None


MODEL = Model()
OWN_KINDS = {"upload": upload, "have": have}


def handler(job):
    params = dict(job.get("input") or {})
    kind = params.pop("kind", None)
    if kind not in OWN_KINDS and kind not in MODEL_KINDS:
        raise ValueError(f"kind must be one of {sorted(list(OWN_KINDS) + list(MODEL_KINDS))}")
    started = time.time()
    if kind in OWN_KINDS:
        yield {"kind": "info", "stage": kind}
        result, seconds, boot = OWN_KINDS[kind](params), {"work": round(time.time() - started, 3)}, {}
    else:
        if kind != "info":
            params["clip_path"] = clip_path(params.get("clip"))
            if not os.path.exists(params["clip_path"]):
                raise ValueError("that clip is not on the volume: upload it first")
            os.utime(params["clip_path"])
        if MODEL.process is None:
            yield {"kind": "info", "stage": "starting gemx"}
        MODEL.start()
        yield {"kind": "info", "stage": kind, "gpu": (MODEL.boot or {}).get("gpu")}
        answer = MODEL.ask(kind, params)
        result = answer["result"]
        seconds = {"work": answer["seconds"], **{f"boot_{k}": v for k, v in MODEL.boot["seconds"].items()}}
        boot = {k: v for k, v in MODEL.boot.items() if k != "seconds"}

    data = json.dumps(result, separators=(",", ":")).encode()
    total = (len(data) + CHUNK_BYTES - 1) // CHUNK_BYTES
    for index in range(total):
        chunk = data[index * CHUNK_BYTES : (index + 1) * CHUNK_BYTES]
        yield {"kind": "chunk", "index": index, "total": total, "data": base64.b64encode(chunk).decode()}
    yield {"kind": "done", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "seconds": seconds, "boot": boot}


if __name__ == "__main__":
    import runpod

    # A model that fails to boot is not fatal here: the worker stays up and
    # answers each job with the reason, so it can be read from the job's error
    # instead of from a worker that vanished. Uploads work either way.
    MODEL.start()
    sys.stdout.flush()
    runpod.serverless.start({"handler": handler, "return_aggregate_stream": True})
