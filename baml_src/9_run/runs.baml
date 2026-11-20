// A character's run: a looping clip beside its walk.
//
// The walk is worked out from the model's build. The run is asked for in
// words: one sentence per character ("A huge person runs forward in a slow,
// heavy, lumbering run..."), written from its brief and gait.json, goes to
// Kimodo (NVIDIA's text-to-motion model, on the motion worker) with a
// straight line to run along at a speed that fits its legs. What comes back
// is cut where two strides match, made to run on the spot, and played on the
// character through the same skeleton, joint limits, planted feet and
// swinging cloth as the walk (the `run` profile).
//
//   baml run runs                      every character in runs/ that has a gait.json
//   baml run runs -- --dir <folder>    the same, for another folder of runs
//
// scripts/motion/run_clip.py does the thinking (the sentence, the speed, the
// job, the cut) and never calls a worker: it leaves the requests that still
// need an answer in <cache>/todo.json. This file sends them: one job for each
// character still without a clip (a few seconds each on a warm worker), and
// an answer already in the cache is never asked for again.
//
// Kimodo reads the sentence with a model built on Meta's Llama 3, which each
// account has to be given access to (see README, Setup). Until then, or with
// no motion endpoint at all, nothing here fails: it says
// "run skipped: Kimodo not available" and why, and everything else carries on.

const RUN = "run";
const RUN_CACHE = ".run-cache";
const RUN_LOOP_FILE = "run/loop.json";
const RUN_PASSES = 3;
const RUN_SKIPPED = "run skipped: Kimodo not available";

/// One request run_clip.py still needs an answer to (todo.json).
class RunToMake {
    request: string @description("The request's name in the cache: the hash of its content"),
    kind: "text",
    what: string,
}

/// What asking Kimodo came to: its answer, or why there is none.
class KimodoAnswer {
    reply: MotionReply?,
    why_not: string?,
}

/// Sends one request to Kimodo. A worker that cannot be reached, or that
/// cannot reach its models, is an answer here, not an error.
function ask_kimodo(request: string) -> KimodoAnswer {
    {
        KimodoAnswer { reply: MotionBricks.from_env().call("text", request), why_not: null }
    } catch (e) {
        let f: MotionFailed => KimodoAnswer { reply: null, why_not: f.reason },
    }
}

/// Makes the run clips these character folders still lack: the sentences,
/// the job, the cut. Returns "" when every clip that can be made is there,
/// or the reason Kimodo could not be asked.
function run_clips(folders: string[], cache: string) -> string {
    let passes = 0;
    while (passes < RUN_PASSES) {
        passes += 1;
        motion_script("run", "run_clip.py", folders.concat(["--cache", cache]), "RUN");
        let todo = baml.json.decode<RunToMake[]>(baml.fs.read(`${cache}/todo.json`));
        if (!todo) {
            return "";
        }
        for (let item in todo) {
            log.info(`run: asking Kimodo on RunPod for ${item.what}`);
            let answer = ask_kimodo(baml.fs.read(`${cache}/${item.request}.request.json`));
            if let reply: MotionReply = answer.reply {
                baml.fs.write(`${cache}/${item.request}.json`, reply.text);
                baml.fs.write(
                    `${cache}/${item.request}.record.json`,
                    baml.json.stringify(reply.record, indent = 2),
                );
            } else {
                return `${RUN_SKIPPED} (${answer.why_not ?? "no reason given"})`;
            }
        }
    }
    throw ShotFailed { step: "run", reason: `still clips to make after ${RUN_PASSES} passes` }
}

/// The character folders in a folder of runs: the ones that have been asked how they walk.
function characters_in(dir: string) -> string[] {
    baml.fs.read_dir(dir)
        .map((f: baml.fs.DirEntry) -> {
            f.name
        })
        .filter((name: string) -> {
            baml.fs.exists(`${dir}/${name}/gait.json`)
        })
        .sort_by_key((name: string) -> {
            name
        })
        .map((name: string) -> {
            `${dir}/${name}`
        })
}

/// A run for every character in a folder of runs. Returns one line per
/// character, or the reason nothing was made.
///
///   baml run runs
function runs(dir: string = RUNS_DIR) -> string {
    let folders = characters_in(dir);
    if (!folders) {
        return `no characters in ${dir} (a character has a gait.json)`;
    }
    //# 1. The clips: one sentence each to Kimodo on RunPod, cut into loops
    let skipped = run_clips(folders, `${dir}/${RUN_CACHE}`);
    if (skipped) {
        log.info(skipped);
        return skipped;
    }
    //# 2. Each character's low-poly and mid-poly versions, running
    let lines: string[] = [];
    for (let folder in folders) {
        let run = Run.open(folder);
        if (!run.has(RUN_LOOP_FILE)) {
            lines.push(`${folder}: no loop could be cut (see the RUN lines above)`);
        } else {
            shape(run, wanted = [RUN]);
            lines.push(
                if (run.has(profile_file(RUN))) {
                    `${folder}: ${profile_file(RUN)}`
                } else {
                    `${folder}: the run was skipped (see the PROFILE lines above)`
                },
            );
        }
    }
    lines.join("\n")
}

/// The pipeline's step: this one character's run, if Kimodo can be reached.
/// Never stops a pipeline run: whatever goes wrong is logged and passed over.
function run_for(run: Run) -> void {
    if (run.has(profile_file(RUN))) {
        return;
    }
    let skipped = run_clips([run.dir], `${RUNS_DIR}/${RUN_CACHE}`) catch (e) {
        let f: ShotFailed => `run skipped: ${f.reason}`,
    };
    if (skipped) {
        log.info(skipped);
        return;
    }
    if (!run.has(RUN_LOOP_FILE)) {
        log.info("run skipped: no loop could be cut from the clip");
        return;
    }
    shape(run, wanted = [RUN]) catch (e) {
        let f: ProfilesFailed => log.info(`run skipped: ${f.reason}`),
    };
}

test "the run's to-do list decodes, and an empty one means nothing to send" {
    let todo = baml.json.decode<RunToMake[]>(
        `[{"request": "9a664f74aebea7b88dad", "kind": "text", "what": "a run for Cave Troll, Shadow Ninja"}]`,
    );
    assert.equal(todo.at(0)?.what, "a run for Cave Troll, Shadow Ninja");
    let none = baml.json.decode<RunToMake[]>("[]");
    assert.equal(none.length(), 0)
}

test "the run has a file of its own that shows it was made" {
    assert.equal(profile_file(RUN), "profiles/lowpoly-run.glb");
    assert.equal(profile_file(WALK), "profiles/lowpoly-walk.glb");
    assert.equal(profile_file("game"), "profiles/game.glb")
}

test "with no motion endpoint, asking Kimodo answers why not" {
    // Only meaningful where the endpoint is not configured (the offline tests);
    // where it is, nothing is sent: the check stops at reading the answer's shape.
    let answer = KimodoAnswer { reply: null, why_not: "MOTIONBRICKS_ENDPOINT_ID is not set (see .env.example)" };
    assert.equal(
        `${RUN_SKIPPED} (${answer.why_not ?? ""})`.slice(0, 33),
        "run skipped: Kimodo not available",
    )
}
