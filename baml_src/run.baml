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
