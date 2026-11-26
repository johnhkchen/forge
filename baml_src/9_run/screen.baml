// The screen-test motions: a short set of whole-body moves (a deep squat, a
// turn on the spot, a wave with each hand...) made once from one sentence
// each by Kimodo on the RunPod motion worker, and kept as SOMA motion in
// motion/library/, so every rig in the cast plays the same set.
//
//   baml run screen_motions                         every motion not yet made
//   baml run screen_motions -- --only deep-squat,kick
//
// scripts/motion/screen_motions.py does the thinking (the jobs, the scoring,
// which take to keep) and never calls a worker: it leaves the requests still
// without an answer in motion/library/.cache/todo.json. This file sends them,
// one job a take, exactly as `just runs` sends a character's run. An answer
// already in the cache is never asked for again. PAID: `just screen-motions`
// prints every job and what it would cost first, and only calls this with `go`.
//
// Without Kimodo (no endpoint, or no access to the model that reads the
// sentence) nothing fails: it says "screen-test motions skipped: Kimodo not
// available" and why.

const SCREEN = "screen";
const SCREEN_CACHE = "motion/library/.cache";
const SCREEN_SKIPPED = "screen-test motions skipped: Kimodo not available";

/// Makes the screen-test motions still missing. Returns one line saying
/// what was made, or why nothing could be.
function screen_motions(only: string = "") -> string {
    let args = ["step", "--cache", SCREEN_CACHE];
    if (only) {
        args = args.concat(["--only", only]);
    }
    let passes = 0;
    while (passes < RUN_PASSES) {
        passes += 1;
        motion_script(SCREEN, "screen_motions.py", args, "SCREEN");
        let todo = baml.json.decode<RunToMake[]>(baml.fs.read(`${SCREEN_CACHE}/todo.json`));
        if (!todo) {
            return "every screen-test motion asked for is made (motion/library/)";
        }
        for (let item in todo) {
            log.info(`screen: asking Kimodo on RunPod for ${item.what}`);
            let answer = ask_kimodo(baml.fs.read(`${SCREEN_CACHE}/${item.request}.request.json`));
            if let reply: MotionReply = answer.reply {
                baml.fs.write(`${SCREEN_CACHE}/${item.request}.json`, reply.text);
                baml.fs.write(
                    `${SCREEN_CACHE}/${item.request}.record.json`,
                    baml.json.stringify(reply.record, indent = 2),
                );
            } else {
                return `${SCREEN_SKIPPED} (${answer.why_not ?? "no reason given"})`;
            }
        }
    }
    throw ShotFailed { step: SCREEN, reason: `still motions to make after ${RUN_PASSES} passes` }
}

test "the screen-test to-do list decodes like a run's" {
    let todo = baml.json.decode<RunToMake[]>(
        `[{"request": "3f1c2a9b8e7d6c5b4a39", "kind": "text", "what": "screen-test motion deep-squat (take 1)"}]`,
    );
    assert.equal(todo.at(0)?.what, "screen-test motion deep-squat (take 1)");
    assert.equal(SCREEN_SKIPPED.slice(0, 22), "screen-test motions sk")
}
