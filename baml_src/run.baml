// One run of the pipeline lives in one folder under runs/, named for when it
// started and what it made, so a run can be read back, resumed, or shown.

const RUNS_DIR = "runs";

class Run {
    dir: string,

    /// A fresh folder for an object, like runs/2026-11-20T03-20-51-brass-helmet.
    function start(name: string) -> Run throws baml.errors.Io {
        // "2026-11-20T03:20:51.957744Z" -> "2026-11-20T03-20-51"
        let stamp = baml.time.Instant.now().to_string().slice(0, 19).replace_all(":", "-");
        let run = Run { dir: `${RUNS_DIR}/${stamp}-${slug(name)}` };
        baml.fs.mkdir(run.dir, baml.fs.MkdirOptions { recursive: true });
        run
    }

    /// An existing run folder, for resuming from a later step.
    function open(dir: string) -> Run throws baml.errors.InvalidArgument | baml.errors.Io {
        if (!baml.fs.exists(dir)) {
            throw baml.errors.InvalidArgument { message: `no run folder at ${dir}` }
        }
        let trimmed = if (dir.ends_with("/")) {
            dir.slice(0, dir.length() - 1)
        } else {
            dir
        };
        Run { dir: trimmed }
    }

    function path(self, file: string) -> string {
        `${self.dir}/${file}`
    }

    function absolute(self, file: string) -> string {
        `${baml.sys.current_dir()}/${self.path(file)}`
    }

    function has(self, file: string) -> bool {
        baml.fs.exists(self.path(file))
    }

    function save<T>(self, file: string, value: T) -> void {
        baml.fs.write(self.path(file), baml.json.stringify(value, indent = 2));
    }

    function load<T>(self, file: string) -> T {
        baml.json.decode<T>(baml.fs.read(self.path(file)))
    }
}

const TRANSCRIPTS = "runs/.transcripts";

/// Files the newest Claude event log (scripts/claude-logged) into the run as
/// transcripts/<step>.jsonl. Call it right after a step's Claude call.
function keep_transcript(run: Run, step: string) -> void {
    let none: baml.fs.DirEntry[] = [];
    let entries: baml.fs.DirEntry[] = baml.fs.read_dir(TRANSCRIPTS) catch (e) {
        baml.errors.Io => none,
    };
    let logs: string[] = entries
        .filter((f: baml.fs.DirEntry) -> {
            f.is_file && f.name.ends_with(".jsonl")
        })
        .map((f: baml.fs.DirEntry) -> {
            f.name
        });
    let newest = logs
        .sort_by_key((n: string) -> {
            n
        })
        .at(logs.length() - 1);
    if let name: string = newest {
        baml.fs.mkdir(run.path("transcripts"), baml.fs.MkdirOptions { recursive: true });
        baml.fs.rename(`${TRANSCRIPTS}/${name}`, run.path(`transcripts/${step}.jsonl`));
    }
}

/// "Brass Diving Helmet!" -> "brass-diving-helmet"
function slug(name: string) -> string {
    name.to_lower_case()
        .chars()
        .map((c) -> {
            if (c.is_ascii_alphanumeric()) {
                c
            } else {
                " "
            }
        })
        .join("")
        .split(" ")
        .filter((w) -> {
            !w.is_empty()
        })
        .join("-")
}

test "slug keeps letters and digits, joined by single dashes" {
    assert.equal(slug("Brass Diving Helmet!"), "brass-diving-helmet");
    assert.equal(slug("  R2 -- unit "), "r2-unit")
}
