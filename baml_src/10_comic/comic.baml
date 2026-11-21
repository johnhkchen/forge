// Comics, start to finish, from one premise:
//
//   1. Code reads the kit off the disk: the cast, each one's poses,   (scripts/comic/kit.py)
//      clip moments and expressions, the places, the framings
//   2. Opus writes the comic as panels of data                         (WriteComic)
//      code checks it against the kit and the room for lettering,
//      and asks once more with what was wrong
//   3. One background Blender draws every panel in the comic style     (scripts/comic/render_panels.py)
//   4. Code letters it (balloons, tails, captions) and lays out the    (scripts/comic/layout.py)
//      page: a strip or a vertical scroll, one .html, and a .png
//
//   baml run comic -- --premise "Lincoln teaches Roosevelt to wait" --layout strip
//
// Everything lands in comics/<name>/. comic.json there is the whole comic as
// data; edit it by hand and run `just comic-again <name>` to redraw without
// asking Opus again.

const COMICS_DIR = "comics";
const COMIC_SCRIPTS = "scripts/comic";
const COMIC_RENDER_TIMEOUT_MINUTES = 20;

// Room for lettering. A balloon wraps to about 20 characters a line.
const MAX_BALLOON_CHARS = 90;
const MAX_PANEL_LINES = 3;
const CLOSE_UP_CHARS = 70;
const SINGLE_CHARS = 110;
const TWO_SHOT_CHARS = 150;
const WIDE_CHARS = 170;
const MAX_CAPTION_CHARS = 80;
const MAX_SFX_CHARS = 12;
const MAX_PANEL_CAST = 3;
const STRIP_PANELS = 4;
const SCROLL_MIN_PANELS = 6;
const SCROLL_MAX_PANELS = 10;
const SPOTS: string[] = ["left", "center", "right"];
// A spot: where the clip itself has the character at that moment.
const SPOT_THERE = "there";
const NEUTRAL = "neutral";

class KitPose {
    name: string,
    about: string,
}

class KitMoment {
    name: string,
    about: string,
    second: float,
}

/// A clip that was made from a shot: how long it runs, what happens when,
/// and the places it belongs to, where a moment of it can stay "there".
class KitShotClip {
    clip: string,
    seconds: float,
    beats: string[],
    places: string[],
}

class KitMember {
    id: string,
    name: string,
    about: string,
    poses: KitPose[],
    moments: KitMoment[],
    clips: string[],
    expressions: string[],
    shot_clips: KitShotClip[],
    silent: bool,

    /// Whether `pose` names something this cast member can do: a pose, a
    /// moment, or clip@seconds for one of its clips.
    function can_pose(self, pose: string) -> bool {
        let named = self.poses.some((p) -> {
            p.name == pose
        })
            || self.moments.some((m) -> {
                m.name == pose
            });
        if (named) {
            return true;
        }
        // "run@0.4" or "run@0.4s": 0.4 seconds into the clip "run".
        let parts = pose.split("@");
        let clip = parts.at(0) ?? "";
        let seconds = (parts.at(1) ?? "").replace_all("s", "");
        let is_time = baml.Float.parse(seconds) catch (e) {
            baml.errors.ParseError => -1.0
        };
        parts.length() == 2 && self.clips.includes(clip) && is_time >= 0.0
    }

    /// Whether `pose` is a moment of a shot's clip ("hero:draw", "hero@4.2")
    /// that belongs to `place`, so it can stand "there".
    function at_home(self, pose: string, place: string) -> bool {
        let clip = pose.split(":").at(0)?.split("@").at(0) ?? "";
        (pose.includes(":") || pose.includes("@"))
            && self.shot_clips.some((s) -> {
                s.clip == clip && s.places.includes(place)
            })
    }
}

class KitPlace {
    name: string,
    about: string,
    marks: string[],
    cameras: string[],
}

class KitFraming {
    name: string,
    about: string,
}

class ComicKit {
    cast: KitMember[],
    places: KitPlace[],
    framings: KitFraming[],

    /// Only these cast ids and places (empty = all), for a premise that names its own.
    function only(self, cast: string[], places: string[]) -> ComicKit {
        ComicKit {
            cast: self.cast.filter((m) -> {
                !cast || cast.includes(m.id)
            }),
            places: self.places.filter((p) -> {
                !places || places.includes(p.name)
            }),
            framings: self.framings,
        }
    }

    /// The kit as Opus reads it.
    function to_prompt(self) -> string {
        let cast = self.cast.map((m) -> {
            let poses = m.poses.map((p) -> {
                `    ${p.name}: ${p.about}`
            });
            let moments = m.moments.map((k) -> {
                `    ${k.name}: ${k.about} (${k.second} s into its clip)`
            });
            let shots = m.shot_clips.map((s) -> {
                `  the clip "${s.clip}" is one continuous ${s.seconds} s action that belongs to ${s.places.join(" or ")}; there, at "there", any moment of it stays where it happened. ${s.beats.join("; ")}`
            });
            let voice = if (m.silent) {
                ["  NEVER SPEAKS ALOUD: every line of theirs is \"think\""]
            } else {
                []
            };
            let clips = if (m.clips) {
                `  clips, as clip@seconds: ${m.clips.join(", ")}`
            } else {
                "  no clips"
            };
            let faces = if (m.expressions) {
                m.expressions.join(", ")
            } else {
                `${NEUTRAL} only`
            };
            [`- ${m.id} (${m.name}): ${m.about}`].concat(voice)
                .concat([`  expressions: ${faces}`, "  poses:"])
                .concat(poses)
                .concat(moments)
                .concat([clips])
                .concat(shots)
                .join("\n")
        });
        let places = self.places.map((p) -> {
            let marks = if (p.marks) {
                `; marks: ${p.marks.join(", ")}`
            } else {
                ""
            };
            let cameras = if (p.cameras) {
                `; cameras: ${p.cameras.join(", ")}`
            } else {
                ""
            };
            `- ${p.name}: ${p.about}${marks}${cameras}`
        });
        let framings = self.framings.map((f) -> {
            `- ${f.name}: ${f.about}`
        });
        `
            CAST
            ${cast.join("\n")}

            PLACES
            ${places.join("\n")}

            FRAMINGS
            ${framings.join("\n")}
        `
    }
}

class ComicFailed {
    step: string,
    reason: string,

    implements baml.ToString {
        function to_string(self) -> string {
            `the comic stopped at ${self.step}: ${self.reason}`
        }
    }
}

/// "strip" or "scroll", as typed on the command line.
function as_layout(layout: string) -> "strip" | "scroll" {
    match (layout) {
        "strip" => "strip",
        "scroll" => "scroll",
        _ => throw ComicFailed { step: "layout", reason: `"${layout}" is not strip or scroll` },
    }
}

/// What the format asks for, in words, for the prompt.
function format_rules(layout: "strip" | "scroll") -> string {
    match (layout) {
        "strip" => {
            `a gag strip of exactly ${STRIP_PANELS} panels, every panel square. Setup, build, turn, punchline.`
        },
        "scroll" => {
            `a vertical-scroll episode of ${SCROLL_MIN_PANELS} to ${SCROLL_MAX_PANELS} panels, read on a phone one panel at a time. Vary the shapes: wide to establish, tall for a big moment, square for talk.`
        },
    }
}

/// How many characters of dialogue a framing has room for.
function panel_room(framing: "wide" | "two-shot" | "single" | "close-up" | "pov") -> int {
    match (framing) {
        "pov" => SINGLE_CHARS,
        "wide" => WIDE_CHARS,
        "two-shot" => TWO_SHOT_CHARS,
        "single" => SINGLE_CHARS,
        "close-up" => CLOSE_UP_CHARS,
    }
}

/// What is wrong with one panel's lettering: too much for the room it has.
function lettering_problems(tag: string, panel: ComicPanel) -> string[] {
    let problems: string[] = [];
    if (panel.lines.length() > MAX_PANEL_LINES) {
        problems.push(
            `${tag}: ${panel.lines.length()} balloons; a panel holds at most ${MAX_PANEL_LINES}`,
        );
    }
    for (let line in panel.lines) {
        if (!line.says.trim()) {
            problems.push(`${tag}: ${line.who} has an empty balloon`);
        }
        if (line.says.length() > MAX_BALLOON_CHARS) {
            problems.push(
                `${tag}: ${line.who}'s balloon is ${line.says.length()} characters; at most ${MAX_BALLOON_CHARS} fit`,
            );
        }
    }
    let said = panel.lines.reduce(
        (total, line) -> {
            total + line.says.length()
        },
        0,
    );
    let room = panel_room(panel.framing);
    if (said > room) {
        problems.push(
            `${tag}: ${said} characters of dialogue; a ${panel.framing} panel has room for about ${room}. Cut words or split the panel`,
        );
    }
    if ((panel.caption ?? "").length() > MAX_CAPTION_CHARS) {
        problems.push(`${tag}: the caption is over ${MAX_CAPTION_CHARS} characters`);
    }
    if ((panel.sfx ?? "").length() > MAX_SFX_CHARS) {
        problems.push(`${tag}: the sound effect is over ${MAX_SFX_CHARS} characters`);
    }
    problems
}

/// What is wrong with who is in a panel and how: someone not in the kit, a
/// pose or face they do not have, a spot the place does not have.
function staging_problems(tag: string, panel: ComicPanel, kit: ComicKit) -> string[] {
    let problems: string[] = [];
    let place = kit.places.find((p) -> {
        p.name == panel.place
    });
    if (place == null) {
        let known = kit.places.map((p) -> {
            p.name
        });
        problems.push(`${tag}: no place "${panel.place}" (there is: ${known.join(", ")})`);
    }
    let cameras = place?.cameras ?? [];
    let marks = place?.marks ?? [];
    if let camera: string = panel.camera {
        if (!cameras.includes(camera)) {
            problems.push(`${tag}: ${panel.place} has no camera "${camera}"; leave camera null`);
        }
    }
    if (!panel.cast) {
        problems.push(`${tag}: nobody is in it`);
    }
    if (panel.cast.length() > MAX_PANEL_CAST) {
        problems.push(
            `${tag}: ${panel.cast.length()} characters; a panel holds at most ${MAX_PANEL_CAST}`,
        );
    }
    let here = panel.cast.map((c) -> {
        c.who
    });
    for (let placed in panel.cast) {
        let member = kit.cast.find((m) -> {
            m.id == placed.who
        });
        if let m: KitMember = member {
            if (!m.can_pose(placed.pose)) {
                problems.push(`${tag}: ${m.id} has no pose "${placed.pose}"`);
            }
            let faces = if (m.expressions) {
                m.expressions
            } else {
                [NEUTRAL]
            };
            if (!faces.includes(placed.expression)) {
                problems.push(
                    `${tag}: ${m.id} has no expression "${placed.expression}" (it has: ${faces.join(", ")})`,
                );
            }
            if (placed.at == SPOT_THERE && !m.at_home(placed.pose, panel.place)) {
                problems.push(
                    `${tag}: ${m.id} stands at "there", which needs a moment of a clip that belongs to ${panel.place}`,
                );
            }
        } else {
            let known = kit.cast.map((k) -> {
                k.id
            });
            problems.push(`${tag}: nobody called "${placed.who}" (there is: ${known.join(", ")})`);
        }
        if (!SPOTS.includes(placed.at) && placed.at != SPOT_THERE && !marks.includes(placed.at)) {
            problems.push(
                `${tag}: ${placed.who} stands at "${placed.at}", which is not ${SPOTS.concat(marks).join(", ")} or "there"`,
            );
        }
    }
    for (let line in panel.lines) {
        if (!here.includes(line.who)) {
            problems.push(`${tag}: ${line.who} has a line but is not in the panel`);
        }
        let speaker = kit.cast.find((m) -> {
            m.id == line.who
        });
        if ((speaker?.silent ?? false) && line.how != "think") {
            problems.push(
                `${tag}: ${line.who} never speaks aloud; make the line a thought ("think") or a caption`,
            );
        }
    }
    problems
}

/// What is wrong with a script, in words Opus can act on. Empty when it can be drawn.
function script_problems(
    script: ComicScript,
    kit: ComicKit,
    layout: "strip" | "scroll",
) -> string[] {
    let count = script.panels.length();
    let length: string[] = match (layout) {
        "strip" => {
            if (count != STRIP_PANELS) {
                [`a strip has exactly ${STRIP_PANELS} panels, not ${count}`]
            } else {
                []
            }
        },
        "scroll" => {
            if (count < SCROLL_MIN_PANELS || count > SCROLL_MAX_PANELS) {
                [
                    `a scroll episode has ${SCROLL_MIN_PANELS} to ${SCROLL_MAX_PANELS} panels, not ${count}`,
                ]
            } else {
                []
            }
        },
    };
    let numbered: (int, ComicPanel)[] = [];
    for (let panel in script.panels) {
        numbered.push((numbered.length() + 1, panel));
    }
    let in_panels = numbered.flat_map((entry) -> {
        let tag = `panel ${entry.0}`;
        let shape: string[] = if (layout == "strip" && entry.1.shape != "square") {
            [`${tag}: a strip's panels are all square`]
        } else {
            []
        };
        shape.concat(staging_problems(tag, entry.1, kit)).concat(lettering_problems(tag, entry.1))
    });
    length.concat(in_panels)
}

/// What a script cost to write: Opus's tokens over every ask, and how long it took.
class ScriptCost {
    asks: int,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    seconds: bigint,
    fixed: string[],
}

class WrittenComic {
    script: ComicScript,
    cost: ScriptCost,
}

/// One ask of Opus; returns the script and the tokens it reported.
function ask_for_comic(
    premise: string,
    layout: "strip" | "scroll",
    kit: ComicKit,
) -> (ComicScript, int, int, int) {
    let result = ai.Agent.new(client = Writer).run(
        WriteComic@spec(premise, format_rules(layout), kit.to_prompt()),
    );
    let tokens_in = result.usage.reduce(
        (total, u) -> {
            total + (u.usage.input_tokens ?? 0)
        },
        0,
    );
    let tokens_out = result.usage.reduce(
        (total, u) -> {
            total + (u.usage.output_tokens ?? 0)
        },
        0,
    );
    let tokens_cached = result.usage.reduce(
        (total, u) -> {
            total + (u.usage.cached_input_tokens ?? 0) + (u.usage.cache_write_input_tokens ?? 0)
        },
        0,
    );
    (result.value, tokens_in, tokens_out, tokens_cached)
}

/// Asks Opus for the comic; if it cannot be drawn as written, shows Opus what
/// is wrong and asks once more.
function write_comic(premise: string, layout: "strip" | "scroll", kit: ComicKit) -> WrittenComic {
    let started = baml.time.Instant.now();
    let (let first, let first_in, let first_out, let first_cached) = ask_for_comic(premise, layout, kit);
    let problems = script_problems(first, kit, layout);
    if (!problems) {
        return WrittenComic {
            script: first,
            cost: ScriptCost {
                asks: 1,
                input_tokens: first_in,
                cached_input_tokens: first_cached,
                output_tokens: first_out,
                seconds: started.elapsed().to_seconds(),
                fixed: [],
            },
        };
    }
    log.info(`comic: asking again, ${problems.length()} problems: ${problems.join("; ")}`);
    let (let again, let again_in, let again_out, let again_cached) = ask_for_comic(
        `${premise}\n\nYour last script had these problems. Keep what worked and fix every one:\n- ${problems.join("\n- ")}`,
        layout,
        kit,
    );
    let left = script_problems(again, kit, layout);
    if (left) {
        throw ComicFailed { step: "script", reason: left.join("; ") }
    }
    WrittenComic {
        script: again,
        cost: ScriptCost {
            asks: 2,
            input_tokens: first_in + again_in,
            cached_input_tokens: first_cached + again_cached,
            output_tokens: first_out + again_out,
            seconds: started.elapsed().to_seconds(),
            fixed: problems,
        },
    }
}

/// comics/<name>/comic.json: the whole comic as data, which the renderer and
/// the layout read. A person can write or edit one by hand.
class ComicFile {
    title: string,
    premise: string,
    layout: "strip" | "scroll",
    canon: bool,
    panels: ComicPanel[],
}

/// Runs a command for a comic step and logs the lines it marks for us.
function comic_step(step: string, program: string, args: string[], mark: string) -> void {
    let out = baml.sys.run(
        program,
        args = args,
        timeout = baml.time.Duration.from_minutes(COMIC_RENDER_TIMEOUT_MINUTES),
        capture_output = true,
    ) catch (e) {
        baml.errors.Io => throw ComicFailed { step: step, reason: `${program} not found` },
        baml.errors.Timeout => {
            throw ComicFailed { step: step, reason: `still running after ${COMIC_RENDER_TIMEOUT_MINUTES} minutes` }
        },
    };
    let lines = string.from_utf8(out.stdout).lines();
    for (
        let line in lines.filter((l) -> {
            l.starts_with(mark)
        })
    ) {
        log.info(`${step}: ${line.slice(mark.length() + 1, line.length())}`);
    }
    if (!out.ok()) {
        let tail = lines.slice(baml.Int.max(0, lines.length() - 12), lines.length()).join("\n");
        throw ComicFailed { step: step, reason: `exited ${out.exit_code}:\n${tail}\n${string.from_utf8(out.stderr)}` }
    }
}

/// One of scripts/comic's Blender scripts, in a background Blender.
function comic_blender(step: string, script: string, args: string[], mark: string) -> void {
    let blender = baml.env.get("BLENDER") ?? BLENDER_APP;
    comic_step(
        step,
        blender,
        ["-b", "--factory-startup", "--python-exit-code", "1", "-P", `${COMIC_SCRIPTS}/${script}`, "--"].concat(args),
        mark,
    )
}

/// The kit as it is on the disk right now.
function read_kit(runs: string) -> ComicKit {
    let file = `${COMICS_DIR}/kit.json`;
    comic_step("kit", "python3", [`${COMIC_SCRIPTS}/kit.py`, "--runs", runs, "--out", file], "KIT");
    baml.json.decode<ComicKit>(baml.fs.read(file))
}

/// "lincoln, roosevelt" -> ["lincoln", "roosevelt"]; "" -> [].
function listed(names: string) -> string[] {
    names.split(",")
        .map((n) -> {
            n.trim()
        })
        .filter((n) -> {
            !n.is_empty()
        })
}

/// Draws and letters comics/<name>/comic.json: every panel in one background
/// Blender, then the page. No model is asked anything.
function draw_comic(name: string, runs: string = RUNS_DIR) -> string {
    let folder = `${COMICS_DIR}/${name}`;
    if (!baml.fs.exists(`${folder}/comic.json`)) {
        throw ComicFailed { step: "draw", reason: `no ${folder}/comic.json` }
    }
    //# Draw every panel in one background Blender
    comic_blender("panels", "render_panels.py", [folder, "--runs", runs], "PANEL");
    //# Letter it and lay out the page
    comic_step("page", "python3", [`${COMIC_SCRIPTS}/layout.py`, folder], "PAGE");
    folder
}

/// `canon` "no" marks a comic kept outside the main story (the page and the
/// gallery label it "Side story").
/// Makes a comic from a premise; returns its folder. `cast` and `place`
/// narrow the kit ("lincoln, roosevelt", "ring"); empty means anything goes.
///
///   baml run comic -- --premise "..." --layout strip --cast "lincoln, roosevelt" --place ring
function comic(
    premise: string,
    layout: string = "strip",
    name: string = "",
    cast: string = "",
    place: string = "",
    runs: string = RUNS_DIR,
    canon: string = "yes",
) -> string {
    let format = as_layout(layout);
    //# 1. What there is to make a comic from
    let kit = read_kit(runs).only(listed(cast), listed(place));
    if (!kit.cast || !kit.places) {
        throw ComicFailed { step: "kit", reason: "nobody to cast or nowhere to set it: check --cast, --place and --runs" }
    }
    //# 2. Opus writes it; code checks it and asks once more if it must
    log.info(`comic: asking Opus for a ${layout}`);
    let written = write_comic(premise, format, kit);
    let folder_name = if (name) {
        name
    } else {
        slug(written.script.title)
    };
    let folder = Run { dir: `${COMICS_DIR}/${folder_name}` };
    baml.fs.mkdir(folder.dir, baml.fs.MkdirOptions { recursive: true });
    folder.save(
        "comic.json",
        ComicFile {
            title: written.script.title,
            premise: premise,
            layout: format,
            canon: canon != "no",
            panels: written.script.panels,
        },
    );
    folder.save("script_cost.json", written.cost);
    log.info(
        `comic: "${written.script.title}", ${written.script.panels.length()} panels, ${written.cost.asks} ask(s), ${written.cost.input_tokens} tokens in, ${written.cost.output_tokens} out`,
    );
    //# 3. Draw and letter it
    draw_comic(folder_name, runs = runs)
}
