"""The motion worker's front door on RunPod Serverless: routes each job to a model by its kind.

Each motion model lives in models/, in a Python environment of its own under
/opt/envs/, and runs as a child process that this router talks to in JSON
lines. So one model's packages never have to agree with another's, and a
second model (NVIDIA Kimodo, text to motion, wants Python 3.10 and PyTorch)
can be added beside the first by adding an environment to the Dockerfile, a
file to models/, and two lines to the tables below.

Input (job["input"]):
    kind     which job; see KINDS. "inbetween" is the main one: poses in,
             the motion between them out (models/motionbricks_model.py)
    ...      the rest is that kind's own input

Output: like the TRELLIS.2 worker, the handler is a generator. /stream/{job}
gives, in order:
    {"kind": "info", "stage": "...", "gpu": "..."}
    {"kind": "chunk", "index": i, "total": n, "data": "<base64>"}
    {"kind": "done", "bytes": N, "sha256": "...", "seconds": {...}, "boot": {...}}
Join the chunks' data in index order, base64-decode, check sha256: that is one
JSON document, the model's answer.

Model weights are never in the image. Each model fetches its own onto the
network volume the first time it boots.
"""

import base64
import hashlib
import json
import subprocess
import sys
import threading
import time

# Each model: the Python that runs it (its own environment) and its file.
# `eager` models start with the worker; the rest start on their first job.
MODELS = {
    "motionbricks": {
        "python": "/opt/envs/motionbricks/bin/python",
        "script": "/app/models/motionbricks_model.py",
        "eager": True,
    },
}
# Which model answers which kind of job.
KINDS = {
    "inbetween": "motionbricks",
    "skeleton": "motionbricks",
    "selftest": "motionbricks",
    "info": "motionbricks",
}

CHUNK_BYTES = 512 * 1024  # base64 grows it to ~700 KB, under /stream's 1 MB per item


class Model:
    """One model's child process, started once and asked one job at a time."""

    def __init__(self, name: str):
        self.name, self.card = name, MODELS[name]
        self.process, self.boot, self.error = None, None, None
        self.lock = threading.Lock()

    def start(self) -> None:
        with self.lock:
            if self.process is not None:
                return
            started = time.time()
            self.process = subprocess.Popen(
                [self.card["python"], "-u", self.card["script"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
            )
            hello = self._read()
            if hello.get("ready"):
                self.boot = hello["boot"]
                self.boot["seconds"]["model_process"] = round(time.time() - started, 1)
            else:
                self.error = hello.get("error", "the model process ended before it was ready")
            print(f"[router] {self.name}: {'ready' if self.boot else 'failed'} after {time.time() - started:.1f}s", flush=True)

    def _read(self) -> dict:
        line = self.process.stdout.readline()
        if not line:
            return {"ok": False, "ready": False, "error": f"the {self.name} process ended (exit {self.process.poll()})"}
        return json.loads(line)

    def ask(self, kind: str, params: dict) -> dict:
        self.start()
        if self.error:
            raise RuntimeError(f"{self.name} did not boot: {self.error}")
        with self.lock:
            self.process.stdin.write(json.dumps({"kind": kind, "input": params}, separators=(",", ":")) + "\n")
            self.process.stdin.flush()
            answer = self._read()
        if not answer.get("ok"):
            raise RuntimeError(answer.get("error", "the model gave no answer"))
        return answer


LOADED = {name: Model(name) for name in MODELS}


def handler(job):
    params = dict(job.get("input") or {})
    kind = params.pop("kind", "inbetween")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    model = LOADED[KINDS[kind]]
    model.start()
    yield {"kind": "info", "stage": kind, "gpu": (model.boot or {}).get("gpu")}

    answer = model.ask(kind, params)
    data = json.dumps(answer["result"], separators=(",", ":")).encode()
    seconds = {"work": answer["seconds"], **{f"boot_{k}": v for k, v in model.boot["seconds"].items()}}

    total = (len(data) + CHUNK_BYTES - 1) // CHUNK_BYTES
    for index in range(total):
        chunk = data[index * CHUNK_BYTES : (index + 1) * CHUNK_BYTES]
        yield {"kind": "chunk", "index": index, "total": total, "data": base64.b64encode(chunk).decode()}
    yield {
        "kind": "done",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "seconds": seconds,
        "boot": {k: v for k, v in model.boot.items() if k != "seconds"},
    }


if __name__ == "__main__":
    import runpod

    for name, card in MODELS.items():
        if card.get("eager"):
            # A model that fails to boot is not fatal here: the worker stays up
            # and answers each job with the reason, so it can be read from the
            # job's error instead of from a worker that vanished.
            LOADED[name].start()
    sys.stdout.flush()
    runpod.serverless.start({"handler": handler, "return_aggregate_stream": True})
