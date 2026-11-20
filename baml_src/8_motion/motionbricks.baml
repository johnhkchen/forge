// Motion: the motion worker on RunPod Serverless (motionbricks_worker/), which
// scales to zero like the TRELLIS.2 one. It holds two NVIDIA models and sorts
// jobs by kind: MotionBricks fills in the movement between poses
// ("inbetween"), and Kimodo makes motion from a sentence ("text").
//
// The worker answers the same way the TRELLIS.2 worker does: poll
// /stream/{job} until the job ends, join the base64 chunks in order, and check
// the sha256 sent with them. What comes out is one JSON document.
//
// Needs RUNPOD_API_KEY and MOTIONBRICKS_ENDPOINT_ID in the environment (.env).

const MOTION_POLL_SECONDS = 2;
// The first job on a fresh volume waits while the worker fetches a model: a
// few minutes for MotionBricks, and up to half an hour the first time Kimodo
// is asked for (17 GB, most of it the encoder that reads the sentence). After
// that a job takes seconds.
const MOTION_TIMEOUT_MINUTES = 40n;

class MotionFailed {
    reason: string,

    implements baml.ToString {
        function to_string(self) -> string {
            `MotionBricks did not make the motion: ${self.reason}`
        }
    }
}

/// How the model that answered was set up. Each model says what it has to
/// say: MotionBricks its TensorRT plan, Kimodo what it fetched.
class WorkerBoot {
    gpu: string,
    fetched_this_boot: bool,
    driver: string?,
    tensorrt: string?,
    plan_was_cached: bool?,
    plan_dir: string?,
    torch: string?,
    kimodo: KimodoCard?,
}

class KimodoCard {
    model: string,
    license: string,
    code_commit: string,
}

/// What the worker sends on /stream, one item at a time.
class MotionItem {
    kind: "info" | "chunk" | "done",
    index: int?,
    total: int?,
    data: string?,
    bytes: int?,
    sha256: string?,
    stage: string?,
    gpu: string?,
    seconds: map<string, float>?,
    boot: WorkerBoot?,
}

/// What one poll of /stream/{job} returns.
class MotionPoll {
    status: string,
    stream: MotionOutput[]?,
    error: string?,
}

class MotionOutput {
    output: MotionItem,
}

/// One finished call: the worker's JSON document, and what it cost in time.
class MotionReply {
    job_id: string,
    text: string,
    record: MotionRecord,
}

/// Saved next to what a call made, like mesh.json.
class MotionRecord {
    job_id: string,
    action: string,
    bytes: int,
    seconds: map<string, float>?,
    boot: WorkerBoot?,
    // From RunPod: how long the job waited for a worker (a cold start shows
    // up here) and how long the worker spent on it.
    delay_ms: int?,
    execution_ms: int?,
    wall_seconds: bigint,
}

class MotionBricks {
    endpoint: string,
    api_key: string @trace.redact,

    function from_env() -> MotionBricks {
        let key = baml.env.get("RUNPOD_API_KEY")
            ?? throw MotionFailed { reason: "RUNPOD_API_KEY is not set (see .env.example)" };
        let id = baml.env.get("MOTIONBRICKS_ENDPOINT_ID")
            ?? throw MotionFailed { reason: "MOTIONBRICKS_ENDPOINT_ID is not set (see .env.example)" };
        MotionBricks { endpoint: `${RUNPOD_API}/${id}`, api_key: key }
    }

    function request(self, method: "GET" | "POST", path: string, body: string) -> string {
        let response = baml.http.send(
            baml.http.Request.from_url(`${self.endpoint}${path}`)
                .set_method(method)
                .set_headers(
                    {
                        "authorization": `Bearer ${self.api_key}`,
                        "content-type": "application/json",
                    },
                )
                .set_body(body)
                .set_timeout(baml.time.Duration.from_seconds(60)),
        );
        let text = response.text();
        if (!response.ok()) {
            throw MotionFailed { reason: `RunPod ${method} ${path} answered ${response.status_code}: ${text}` }
        }
        text
    }

    /// Queues one job (`input` is the worker's input, as JSON) and returns its id.
    function submit(self, input: string) -> string {
        let queued = baml.json.parse(self.request("POST", "/run", `{"input": ${input}}`));
        baml.json.path_or<string?>(queued, ".id", null)
            ?? throw MotionFailed { reason: `RunPod gave no job id: ${baml.json.stringify(queued)}` }
    }

    /// Polls the job's stream until it ends; returns every item it sent.
    function collect(self, job: string) -> MotionItem[] {
        let started = baml.time.Instant.now();
        let items: MotionItem[] = [];
        let status = "IN_QUEUE";
        while (!is_finished(status)) {
            if (started.elapsed().to_minutes() >= MOTION_TIMEOUT_MINUTES) {
                let _ = self.request("POST", `/cancel/${job}`, "");
                throw MotionFailed { reason: `still ${status} after ${MOTION_TIMEOUT_MINUTES} minutes, cancelled` }
            }
            baml.sys.sleep(baml.time.Duration.from_seconds(MOTION_POLL_SECONDS));
            let poll = baml.json.decode<MotionPoll>(self.request("GET", `/stream/${job}`, ""));
            for (let s in poll.stream ?? []) {
                items.push(s.output);
            }
            if (poll.status != status) {
                log.info(`motion: job ${job} ${poll.status.to_lower_case()}`);
            }
            status = poll.status;
            if (status != "COMPLETED" && is_finished(status)) {
                throw MotionFailed { reason: `job ${job} ended ${status}: ${self.why(job, poll.error)}` }
            }
        }
        items
    }

    /// A failed job's reason. /stream often leaves it out; /status has it.
    function why(self, job: string, from_stream: string?) -> string {
        if (from_stream) {
            return from_stream;
        }
        let status = baml.json.parse(self.request("GET", `/status/${job}`, ""));
        baml.json.path_or<string>(status, ".error", "no error given")
    }

    /// Runs one worker action to the end and returns its JSON document.
    function call(self, action: string, input: string) -> MotionReply {
        let started = baml.time.Instant.now();
        let job = self.submit(input);
        log.info(`motion: queued ${action} as job ${job}`);
        let items = self.collect(job);
        let bytes = join_chunks(items);
        let done = items.find((i) -> {
            i.kind == "done"
        });
        let status = baml.json.parse(self.request("GET", `/status/${job}`, ""));
        MotionReply {
            job_id: job,
            text: string.from_utf8(bytes),
            record: MotionRecord {
                job_id: job,
                action: action,
                bytes: bytes.length(),
                seconds: done?.seconds,
                boot: done?.boot,
                delay_ms: baml.json.path_or<int?>(status, ".delayTime", null),
                execution_ms: baml.json.path_or<int?>(status, ".executionTime", null),
                wall_seconds: started.elapsed().to_seconds(),
            },
        }
    }
}

/// Joins the streamed chunks back into the worker's document and checks it
/// against the sha256 the worker sent.
function join_chunks(items: MotionItem[]) -> uint8array {
    let done = items.find((i) -> {
        i.kind == "done"
    })
        ?? throw MotionFailed { reason: "the stream ended without a done item" };
    let chunks = items
        .filter((i) -> {
            i.kind == "chunk"
        })
        .sort_by_key((i) -> {
            i.index ?? 0
        });
    let expected = chunks.at(0)?.total ?? 0;
    if (chunks.length() != expected) {
        throw MotionFailed { reason: `got ${chunks.length()} of ${expected} chunks` }
    }
    let joined = chunks.reduce(
        (acc, c) -> {
            acc.concat(
                baml.Uint8Array.from_base64(c.data ?? "") catch (e) {
                    _ => throw MotionFailed { reason: `chunk ${c.index ?? -1} is not base64` },
                },
            )
        },
        baml.Uint8Array.zeroes(0),
    );
    let hasher = baml.crypto.Sha256.new();
    hasher.update(joined);
    let digest = hasher.finish().to_hex();
    if (digest != (done.sha256 ?? "")) {
        throw MotionFailed { reason: `sha256 mismatch: got ${digest}, worker sent ${done.sha256 ?? "none"}` }
    }
    joined
}

const SKELETON_FILE = "motion/soma_skeleton.json";

/// Asks the worker for the SOMA skeleton (joints, parents, rest pose) and
/// keeps it in the repo, so poses can be written and checked with no GPU.
function motion_skeleton() -> string {
    let reply = MotionBricks.from_env().call("skeleton", `{"kind": "skeleton"}`);
    baml.fs.write(SKELETON_FILE, baml.json.stringify(baml.json.parse(reply.text), indent = 1));
    log.info(`motion: skeleton saved to ${SKELETON_FILE} (${baml.json.stringify(reply.record)})`);
    SKELETON_FILE
}

/// MotionBricks' own generate_once example, run on the worker: proof the
/// endpoint works end to end. Prints what it made and what it cost in time.
function motion_selftest() -> string {
    let reply = MotionBricks.from_env().call("selftest", `{"kind": "selftest"}`);
    `${reply.text}\n${baml.json.stringify(reply.record, indent = 2)}`
}

/// What Kimodo has fetched and loaded, with revisions and timings. The first
/// call on a fresh volume is the one that fetches.
function text_info() -> string {
    let reply = MotionBricks.from_env().call("text_info", `{"kind": "text_info"}`);
    `${baml.json.stringify(baml.json.parse(reply.text), indent = 2)}\n${baml.json.stringify(reply.record, indent = 2)}`
}

/// Which worker answers, and how long it took to boot.
function motion_info() -> string {
    let reply = MotionBricks.from_env().call("info", `{"kind": "info"}`);
    baml.json.stringify(reply.record, indent = 2)
}

test "join_chunks joins chunks in order and checks the hash" {
    // "hello world" split in two, sent out of order.
    let part = (index: int, data: string) -> {
        MotionItem {
            kind: "chunk",
            index: index,
            total: 2,
            data: data,
            bytes: null,
            sha256: null,
            stage: null,
            gpu: null,
            seconds: null,
            boot: null,
        }
    };
    let done = MotionItem {
        kind: "done",
        index: null,
        total: null,
        data: null,
        bytes: 11,
        sha256: "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
        stage: null,
        gpu: null,
        seconds: null,
        boot: null,
    };
    assert.equal(
        string.from_utf8(join_chunks([part(1, "IHdvcmxk"), part(0, "aGVsbG8="), done])),
        "hello world",
    );
    let wrong = MotionItem { ...done, sha256: "00" };
    let caught = {
        let _ = join_chunks([part(1, "IHdvcmxk"), part(0, "aGVsbG8="), wrong]);
        "no error"
    } catch (e) {
        let f: MotionFailed => f.reason.slice(0, 15),
    };
    assert.equal(caught, "sha256 mismatch")
}

test "a Kimodo job's boot card decodes too" {
    let poll = baml.json.decode<MotionPoll>(
        `
            {"status": "COMPLETED", "stream": [{"output": {"kind": "info", "stage": "starting kimodo"}},
              {"output": {"kind": "done", "bytes": 12, "sha256": "ab",
              "seconds": {"work": 9.5, "boot_fetch": 0.4, "boot_model": 6.0},
              "boot": {"gpu": "NVIDIA GeForce RTX 4090", "torch": "2.5.1+cu124",
                       "kimodo": {"model": "Kimodo-SOMA-RP-v1.2", "license": "NVIDIA Open Model License", "code_commit": "e1c2"},
                       "fetched_this_boot": false, "fetched": {"code": {}, "weights": {}}, "text_cache": "/runpod-volume/kimodo/text-cache"}}}]}
        `,
    );
    let done = poll.stream?.at(1)?.output;
    assert.equal(done?.boot?.kimodo?.model, "Kimodo-SOMA-RP-v1.2");
    assert.equal(done?.boot?.plan_was_cached, null);
    assert.equal(poll.stream?.at(0)?.output.stage, "starting kimodo")
}

test "a motion stream poll decodes, boot card included" {
    let poll = baml.json.decode<MotionPoll>(
        `
            {"status": "COMPLETED", "stream": [{"output": {"kind": "done", "bytes": 12, "sha256": "ab",
              "seconds": {"work": 0.4, "boot_engine": 3.1},
              "boot": {"gpu": "NVIDIA GeForce RTX 4090", "driver": "570.1", "tensorrt": "10.8.0.43", "warp": "1.17.0",
                       "motionbricks": {"tag": "v0.2.0"}, "fetched_this_boot": false, "plan_was_cached": true,
                       "plan_dir": "/runpod-volume/motionbricks/trt-cache/x"}}}]}
        `,
    );
    let done = poll.stream?.at(0)?.output;
    assert.equal(done?.boot?.plan_was_cached, true);
    assert.approx_equal(done?.seconds?.get("work") ?? 0.0, 0.4, 0.0001)
}
