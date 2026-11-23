"""Talks to the video worker (gemx_worker/) on RunPod Serverless, the way the motion endpoint is talked to.

Queue a job, poll /stream/{job} until it ends, join the base64 chunks in
order, check the sha256 sent with them: that is one JSON document, the
worker's answer (baml_src/8_motion/motionbricks.baml does the same in BAML).

Needs RUNPOD_API_KEY and GEMX_ENDPOINT_ID in the environment (`just` loads
.env). Every call here costs GPU time on your RunPod account; nothing in this
file runs unless `just video` reaches a step that needs the worker.

A clip is sent once, in parts small enough for one RunPod job each, and kept
on the endpoint's network volume under its sha256. Later jobs name it by that.

`Direct` is the same thing with no RunPod at all: it hands each job straight to
gemx_worker/handler.py on this Mac. The offline tests use it with a stand-in
for the model.

Plain Python: urllib, nothing to install.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
RUNPOD_API = "https://api.runpod.ai/v2"
POLL_SECONDS = 2
# The first job on a fresh volume waits while the worker fetches about 7.5 GB; after that a job takes seconds to minutes.
TIMEOUT_MINUTES = 40
PART_BYTES = 5 * 1024 * 1024  # base64 grows it to 6.7 MB, under RunPod's 10 MB a job
FINISHED = ("COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT")


class WorkerFailed(Exception):
    """The worker did not answer; the message says why."""


def join_chunks(items: list) -> bytes:
    """The worker's document from what it streamed, checked against the sha256 it sent."""
    done = next((i for i in items if i.get("kind") == "done"), None)
    if done is None:
        raise WorkerFailed("the stream ended without a done item")
    chunks = sorted((i for i in items if i.get("kind") == "chunk"), key=lambda i: i.get("index", 0))
    expected = chunks[0].get("total", 0) if chunks else 0
    if len(chunks) != expected:
        raise WorkerFailed(f"got {len(chunks)} of {expected} chunks")
    try:
        data = b"".join(base64.b64decode(c.get("data") or "", validate=True) for c in chunks)
    except Exception as error:
        raise WorkerFailed("a chunk is not base64") from error
    got = hashlib.sha256(data).hexdigest()
    if got != done.get("sha256"):
        raise WorkerFailed(f"sha256 mismatch: got {got}, worker sent {done.get('sha256')}")
    return data


class Endpoint:
    """The GEM-X endpoint on RunPod."""

    def __init__(self, endpoint_id: str, api_key: str, log=print):
        self.base, self.key, self.log = f"{RUNPOD_API}/{endpoint_id}", api_key, log

    @classmethod
    def from_env(cls, log=print) -> "Endpoint":
        key, endpoint = os.environ.get("RUNPOD_API_KEY"), os.environ.get("GEMX_ENDPOINT_ID")
        if not key:
            raise WorkerFailed("RUNPOD_API_KEY is not set (see .env.example)")
        if not endpoint:
            raise WorkerFailed("GEMX_ENDPOINT_ID is not set. The video worker has to exist first: see \"From a video\" in the README, then put its id in .env")
        return cls(endpoint, key, log)

    def request(self, method: str, path: str, body: dict = None) -> dict:
        data = json.dumps(body, separators=(",", ":")).encode() if body is not None else (b"" if method == "POST" else None)
        ask = urllib.request.Request(self.base + path, data=data, method=method, headers={"authorization": f"Bearer {self.key}", "content-type": "application/json"})
        try:
            with urllib.request.urlopen(ask, timeout=90) as response:
                return json.loads(response.read().decode() or "{}")
        except urllib.error.HTTPError as error:
            raise WorkerFailed(f"RunPod {method} {path} answered {error.code}: {error.read().decode()[:500]}") from error
        except urllib.error.URLError as error:
            raise WorkerFailed(f"RunPod could not be reached: {error.reason}") from error

    def call(self, payload: dict) -> tuple:
        """Runs one job to the end. Returns (the worker's document, a record of what it cost in time)."""
        kind = payload.get("kind")
        started = time.time()
        job = self.request("POST", "/run", {"input": payload}).get("id")
        if not job:
            raise WorkerFailed("RunPod gave no job id")
        self.log(f"video: queued {kind} as job {job}")
        items, status = [], "IN_QUEUE"
        while status not in FINISHED:
            if time.time() - started > TIMEOUT_MINUTES * 60:
                self.request("POST", f"/cancel/{job}")
                raise WorkerFailed(f"still {status} after {TIMEOUT_MINUTES} minutes, cancelled")
            time.sleep(POLL_SECONDS)
            poll = self.request("GET", f"/stream/{job}")
            for item in poll.get("stream") or []:
                output = item.get("output") or {}
                if output.get("kind") == "info":
                    self.log(f"video: worker is {output.get('stage')}")
                items.append(output)
            if poll.get("status") != status:
                self.log(f"video: job {job} {str(poll.get('status')).lower()}")
            status = poll.get("status")
            if status in FINISHED and status != "COMPLETED":
                why = poll.get("error") or self.request("GET", f"/status/{job}").get("error") or "no error given"
                raise WorkerFailed(f"job {job} ended {status}: {why}")
        data = join_chunks(items)
        done = next(i for i in items if i.get("kind") == "done")
        about = self.request("GET", f"/status/{job}")
        record = {"job_id": job, "action": kind, "bytes": len(data), "seconds": done.get("seconds"), "boot": done.get("boot"), "delay_ms": about.get("delayTime"), "execution_ms": about.get("executionTime"), "wall_seconds": round(time.time() - started, 1)}
        return json.loads(data.decode()), record


class Direct:
    """The worker's own handler, called on this Mac with no RunPod: for the offline tests.

    `model_script` is what stands in for the model (scripts/video/stub_worker.py) and `volume` a folder that
    stands in for the network volume."""

    def __init__(self, volume: str, model_script: str, log=print):
        os.environ.update({"VOLUME_DIR": volume, "GEMX_MODEL_PYTHON": sys.executable, "GEMX_MODEL_SCRIPT": model_script})
        sys.path.insert(0, os.path.join(REPO, "gemx_worker"))
        sys.modules.pop("handler", None)  # it reads those settings when it is imported
        import handler

        self.handler, self.log, self.jobs = handler, log, []

    def call(self, payload: dict) -> tuple:
        started = time.time()
        if len(json.dumps(payload)) > 10 * 1024 * 1024:
            raise WorkerFailed("a job over 10 MB: RunPod would refuse it")
        self.jobs.append(payload.get("kind"))
        try:
            items = list(self.handler.handler({"id": f"local-{len(self.jobs)}", "input": json.loads(json.dumps(payload))}))
        except Exception as error:  # noqa: BLE001  on RunPod this is the job's error
            raise WorkerFailed(f"job ended FAILED: {type(error).__name__}: {error}") from error
        data = join_chunks(items)
        done = next(i for i in items if i.get("kind") == "done")
        return json.loads(data.decode()), {"job_id": f"local-{len(self.jobs)}", "action": payload.get("kind"), "bytes": len(data), "seconds": done.get("seconds"), "boot": done.get("boot"), "wall_seconds": round(time.time() - started, 2)}

    def close(self) -> None:
        self.handler.MODEL.stop()


def upload(endpoint, path: str, sha256: str, part_bytes: int = PART_BYTES) -> dict:
    """Puts a clip on the worker's volume unless it is there already. Returns what happened."""
    size = os.path.getsize(path)
    there, _ = endpoint.call({"kind": "have", "clip": sha256})
    if there.get("complete"):
        return {"clip": sha256, "bytes": size, "parts": 0, "already_there": True}
    total = max(1, -(-size // part_bytes))
    answer = {}
    with open(path, "rb") as f:
        for index in range(total):
            data = f.read(part_bytes)
            endpoint.log(f"video: sending the clip, part {index + 1} of {total}")
            answer, _ = endpoint.call({"kind": "upload", "clip": sha256, "index": index, "total": total, "data": base64.b64encode(data).decode()})
    if not answer.get("complete"):
        raise WorkerFailed(f"the clip did not arrive whole: the worker has parts {answer.get('have')} of {total}")
    return {"clip": sha256, "bytes": size, "parts": total, "already_there": False}
