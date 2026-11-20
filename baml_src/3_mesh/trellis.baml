// Step 3: TRELLIS.2 turns the picture into a textured mesh, on a RunPod
// Serverless endpoint running worker/ (scales to zero, so it costs nothing
// while idle).
//
// A GLB is bigger than RunPod's inline result limit, so the worker streams it
// back in base64 chunks: poll /stream/{job} until the job ends, join the
// chunks in order, and check the sha256 the worker sent with them.
//
// Needs RUNPOD_API_KEY and TRELLIS_ENDPOINT_ID in the environment (.env).

const RUNPOD_API = "https://api.runpod.ai/v2";
const POLL_SECONDS = 3;
// The first job on a cold endpoint loads ~17 GB of weights; later ones take
// about a minute.
const MESH_TIMEOUT_MINUTES = 25n;

class MeshSettings {
    seed: int,
    pipeline_type: "512" | "1024" | "1024_cascade" | "1536_cascade",
    decimation_target: int,
    texture_size: int,
}

const DEFAULT_MESH = MeshSettings {
    seed: 42,
    pipeline_type: "1024_cascade",
    decimation_target: 300000,
    texture_size: 2048,
};

class MeshFailed {
    reason: string,

    implements baml.ToString {
        function to_string(self) -> string {
            `TRELLIS.2 did not make the mesh: ${self.reason}`
        }
    }
}

/// What the worker sends on /stream, one item at a time.
class StreamItem {
    kind: "info" | "chunk" | "done",
    index: int?,
    total: int?,
    data: string?,
    bytes: int?,
    sha256: string?,
    stage: string?,
    gpu: string?,
    volume_path: string?,
    seconds: map<string, float>?,
}

/// What one poll of /stream/{job} returns.
class StreamPoll {
    status: string,
    stream: StreamOutput[]?,
    error: string?,
}

class StreamOutput {
    output: StreamItem,
}

/// Saved as mesh.json next to the mesh.
class MeshRecord {
    job_id: string,
    gpu: string?,
    bytes: int,
    volume_path: string?,
    seconds: map<string, float>?,
    wall_seconds: bigint,
    settings: MeshSettings,
}

class Trellis {
    endpoint: string,
    api_key: string @trace.redact,

    function from_env() -> Trellis {
        let key = baml.env.get("RUNPOD_API_KEY")
            ?? throw MeshFailed { reason: "RUNPOD_API_KEY is not set (see .env.example)" };
        let id = baml.env.get("TRELLIS_ENDPOINT_ID")
            ?? throw MeshFailed { reason: "TRELLIS_ENDPOINT_ID is not set (see .env.example)" };
        Trellis { endpoint: `${RUNPOD_API}/${id}`, api_key: key }
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
            throw MeshFailed { reason: `RunPod ${method} ${path} answered ${response.status_code}: ${text}` }
        }
        text
    }

    /// Queues one job and returns its id.
    function submit(self, picture: uint8array, settings: MeshSettings) -> string {
        let body = baml.json.stringify(
            {
                "input": {
                    "image": picture.to_base64(),
                    "seed": settings.seed,
                    "pipeline_type": settings.pipeline_type,
                    "decimation_target": settings.decimation_target,
                    "texture_size": settings.texture_size,
                },
            },
        );
        let queued = baml.json.parse(self.request("POST", "/run", body));
        baml.json.path_or<string?>(queued, ".id", null)
            ?? throw MeshFailed { reason: `RunPod gave no job id: ${baml.json.stringify(queued)}` }
    }

    /// Polls the job's stream until it ends; returns every item it sent.
    function collect(self, job: string) -> StreamItem[] {
        let started = baml.time.Instant.now();
        let items: StreamItem[] = [];
        let status = "IN_QUEUE";
        while (!is_finished(status)) {
            if (started.elapsed().to_minutes() >= MESH_TIMEOUT_MINUTES) {
                let _ = self.request("POST", `/cancel/${job}`, "");
                throw MeshFailed { reason: `still ${status} after ${MESH_TIMEOUT_MINUTES} minutes, cancelled` }
            }
            baml.sys.sleep(baml.time.Duration.from_seconds(POLL_SECONDS));
            let poll = baml.json.decode<StreamPoll>(self.request("GET", `/stream/${job}`, ""));
            for (let s in poll.stream ?? []) {
                report_progress(s.output);
                items.push(s.output);
            }
            if (poll.status != status) {
                log.info(`mesh: job ${job} ${poll.status.to_lower_case()}`);
            }
            status = poll.status;
            if (status != "COMPLETED" && is_finished(status)) {
                throw MeshFailed { reason: `job ${job} ended ${status}: ${poll.error ?? "no error given"}` }
            }
        }
        items
    }
}

function is_finished(status: string) -> bool {
    ["COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"].includes(status)
}

function report_progress(item: StreamItem) -> void {
    match (item.kind) {
        "info" => log.info(`mesh: ${item.stage ?? "working"} on ${item.gpu ?? "a GPU"}`),
        "chunk" => {
            let index = item.index ?? 0;
            if (index == 0) {
                log.info(`mesh: receiving ${item.total ?? 0} chunks`);
            }
        },
        "done" => {
            log.info(
                `mesh: ${(item.bytes ?? 0) / 1024} KB, timings ${baml.json.stringify(item.seconds)}`,
            )
        },
    }
}

/// Joins the streamed chunks back into the GLB and checks it against the
/// worker's sha256.
function assemble(items: StreamItem[]) -> uint8array {
    let done = items.find((i) -> {
        i.kind == "done"
    })
        ?? throw MeshFailed { reason: "the stream ended without a done item" };
    let chunks = items
        .filter((i) -> {
            i.kind == "chunk"
        })
        .sort_by_key((i) -> {
            i.index ?? 0
        });
    let expected = chunks.at(0)?.total ?? 0;
    if (chunks.length() != expected) {
        throw MeshFailed { reason: `got ${chunks.length()} of ${expected} chunks` }
    }
    let glb = chunks.reduce(
        (acc, c) -> {
            acc.concat(
                baml.Uint8Array.from_base64(c.data ?? "") catch (e) {
                    _ => throw MeshFailed { reason: `chunk ${c.index ?? -1} is not base64` },
                },
            )
        },
        baml.Uint8Array.zeroes(0),
    );
    let hasher = baml.crypto.Sha256.new();
    hasher.update(glb);
    let digest = hasher.finish().to_hex();
    if (digest != (done.sha256 ?? "")) {
        throw MeshFailed { reason: `sha256 mismatch: got ${digest}, worker sent ${done.sha256 ?? "none"}` }
    }
    glb
}

/// Sends the run's picture to TRELLIS.2 and saves the result as mesh.glb.
function sculpt(run: Run, settings: MeshSettings = DEFAULT_MESH) -> string {
    let started = baml.time.Instant.now();
    let trellis = Trellis.from_env();
    //# Queue the job on RunPod
    let job = trellis.submit(baml.fs.open(run.path("image.png"), "r").bytes(), settings);
    log.info(`mesh: queued job ${job}`);
    //# Stream the GLB back and check it
    let items = trellis.collect(job);
    let glb = assemble(items);
    baml.fs.write_bytes(run.path("mesh.glb"), glb);
    let done = items.find((i) -> {
        i.kind == "done"
    });
    run.save(
        "mesh.json",
        MeshRecord {
            job_id: job,
            gpu: items
                .find((i) -> {
                    i.kind == "info"
                })
                ?.gpu,
            bytes: glb.length(),
            volume_path: done?.volume_path,
            seconds: done?.seconds,
            wall_seconds: started.elapsed().to_seconds(),
            settings: settings,
        },
    );
    run.path("mesh.glb")
}

test "assemble joins chunks in order and checks the hash" {
    // "hello world" split in two, sent out of order.
    let items = [
        StreamItem {
            kind: "chunk",
            index: 1,
            total: 2,
            data: "IHdvcmxk",
            bytes: null,
            sha256: null,
            stage: null,
            gpu: null,
            volume_path: null,
            seconds: null,
        },
        StreamItem {
            kind: "chunk",
            index: 0,
            total: 2,
            data: "aGVsbG8=",
            bytes: null,
            sha256: null,
            stage: null,
            gpu: null,
            volume_path: null,
            seconds: null,
        },
        StreamItem {
            kind: "done",
            index: null,
            total: null,
            data: null,
            bytes: 11,
            sha256: "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
            stage: null,
            gpu: null,
            volume_path: null,
            seconds: null,
        },
    ];
    assert.equal(string.from_utf8(assemble(items)), "hello world")
}

test "a stream poll decodes" {
    let poll = baml.json.decode<StreamPoll>(
        `
            {"status": "IN_PROGRESS", "stream": [{"output": {"kind": "info", "stage": "generating", "gpu": "NVIDIA GeForce RTX 4090"}}]}
        `,
    );
    assert.equal(poll.stream?.at(0)?.output.gpu, "NVIDIA GeForce RTX 4090")
}
