// BUY HOUSE: a toon's own house, designed by Opus from their brief, checked,
// built as a set and ready to be put down in the world.
//
//   baml run buy_house -- --toon flamenco-dancer --runs runs
//
//   1. the toon's brief (runs/<run>/brief.json) and who they are (canon/CANON.md)
//   2. Opus designs the house (DesignHouse); code checks the plan and, if it
//      cannot be built as drawn, shows Opus what is wrong and asks once more
//   3. the design is kept: sets/<house>/design.json, and what it cost
//      (design_cost.json)
//   4. scripts/world/build_house.py turns the plan into a set (set.json,
//      build.json, its sign), builds it in a background Blender and checks it
//
// Asking again makes a different house, in a folder of its own: nothing is
// written over. world.json says which house stands in the world, and where.
// `rebuild_house` builds a kept design again without asking anyone.

const HOUSE_SCRIPTS = "scripts/world";
const CANON_FILE = "canon/CANON.md";
const HOUSE_WIDE_M = (8.0, 14.0);
const HOUSE_DEEP_M = (7.0, 12.0);
const HOUSE_AREAS = (3, 6);
const AREA_MIN_M = 2.0;
const STAGE_WIDE_M = (2.5, 5.0);
const STAGE_DEEP_M = (2.0, 4.0);
const PRACTICE_MIN_M = 3.0;
const SIGN_MAX_LETTERS = 22;
const PLAN_SLACK_M = 0.01;
const HOUSE_BUILD_MINUTES = 10;

/// Opus drew a house twice and neither can be built.
class HouseRejected {
    toon: string,
    problems: string[],

    implements baml.ToString {
        function to_string(self) -> string {
            `the house for ${self.toon} cannot be built as designed: ${self.problems.join("; ")}`
        }
    }
}

/// Nobody by that name has a run to read a brief from.
class ToonUnknown {
    toon: string,
    runs: string,

    implements baml.ToString {
        function to_string(self) -> string {
            `no run in ${self.runs} is named for "${self.toon}"`
        }
    }
}

/// Building the set from a design stopped.
class HouseBuildFailed {
    house: string,
    reason: string,

    implements baml.ToString {
        function to_string(self) -> string {
            `the house ${self.house} was designed but not built: ${self.reason}`
        }
    }
}

/// What a design cost: Opus's tokens over every ask, and how long it took.
/// (The Writer is a logged-in CLI, so this is subscription time, not a bill.)
class HouseCost {
    toon: string,
    model: string,
    asks: int,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    seconds: bigint,
    fixed: string[],
}

class DesignedHouse {
    design: HouseDesign,
    cost: HouseCost,
}

function is_hex(text: string) -> bool {
    // A colour like "#c0392b": a hash, then exactly six hex digits.
    baml.regex.new(`^#[0-9a-fA-F]{6}$`).has_match(text)
}

function areas_overlap(a: HouseArea, b: HouseArea) -> bool {
    a.x_m + a.wide_m > b.x_m + PLAN_SLACK_M
        && b.x_m + b.wide_m > a.x_m + PLAN_SLACK_M
        && a.z_m + a.deep_m > b.z_m + PLAN_SLACK_M
        && b.z_m + b.deep_m > a.z_m + PLAN_SLACK_M
}

function area_problems(design: HouseDesign, area: HouseArea) -> string[] {
    let small: string[] = if (area.wide_m < AREA_MIN_M || area.deep_m < AREA_MIN_M) {
        [
            `"${area.name}" is ${area.wide_m} by ${area.deep_m} m: every area is at least ${AREA_MIN_M} m each way`,
        ]
    } else {
        []
    };
    let outside: string[] = if (
        area.x_m < 0.0 - PLAN_SLACK_M
            || area.z_m < 0.0 - PLAN_SLACK_M
            || area.x_m + area.wide_m > design.wide_m + PLAN_SLACK_M
            || area.z_m + area.deep_m > design.deep_m + PLAN_SLACK_M
    ) {
        [`"${area.name}" runs outside the house (${design.wide_m} by ${design.deep_m} m)`]
    } else {
        []
    };
    let sized: string[] = match (area.kind) {
        AreaKind.Stage => {
            if (
                area.wide_m < STAGE_WIDE_M.0
                    || area.wide_m > STAGE_WIDE_M.1
                    || area.deep_m < STAGE_DEEP_M.0
                    || area.deep_m > STAGE_DEEP_M.1
            ) {
                [
                    `the stage "${area.name}" is ${area.wide_m} by ${area.deep_m} m: a stage is ${STAGE_WIDE_M.0} to ${STAGE_WIDE_M.1} m wide and ${STAGE_DEEP_M.0} to ${STAGE_DEEP_M.1} m deep`,
                ]
            } else {
                []
            }
        },
        AreaKind.PracticeFloor => {
            if (area.wide_m < PRACTICE_MIN_M || area.deep_m < PRACTICE_MIN_M) {
                [
                    `the practice floor "${area.name}" is ${area.wide_m} by ${area.deep_m} m: it needs ${PRACTICE_MIN_M} m each way`,
                ]
            } else {
                []
            }
        },
        _ => [],
    };
    let colour: string[] = if (is_hex(area.floor.hex)) {
        []
    } else {
        [`"${area.name}": the floor colour "${area.floor.hex}" is not #rrggbb`]
    };
    small.concat(outside).concat(sized).concat(colour)
}

function count_of(design: HouseDesign, kind: AreaKind) -> int {
    design.areas
        .filter((a) -> {
            a.kind == kind
        })
        .length()
}

/// What stops a design from being built. Empty when it is sound.
function house_problems(design: HouseDesign) -> string[] {
    let size: string[] = if (
        design.wide_m < HOUSE_WIDE_M.0
            || design.wide_m > HOUSE_WIDE_M.1
            || design.deep_m < HOUSE_DEEP_M.0
            || design.deep_m > HOUSE_DEEP_M.1
    ) {
        [
            `the house is ${design.wide_m} by ${design.deep_m} m: it is ${HOUSE_WIDE_M.0} to ${HOUSE_WIDE_M.1} m wide and ${HOUSE_DEEP_M.0} to ${HOUSE_DEEP_M.1} m deep`,
        ]
    } else {
        []
    };
    let count: string[] = if (design.areas.length() < HOUSE_AREAS.0 || design.areas.length() > HOUSE_AREAS.1) {
        [`a house has ${HOUSE_AREAS.0} to ${HOUSE_AREAS.1} areas, not ${design.areas.length()}`]
    } else {
        []
    };
    let names = design.areas.map((a) -> {
        a.name
    });
    let doubled = design.areas
        .filter((a) -> {
            names
                .filter((n) -> {
                    n == a.name
                })
                .length()
                > 1
        })
        .map((a) -> {
            `two areas are both called "${a.name}"`
        });
    let overlapping = design.areas.flat_map((a) -> {
        design.areas
            .filter((b) -> {
                a.name < b.name && areas_overlap(a, b)
            })
            .map((b) -> {
                `"${a.name}" and "${b.name}" overlap on the plan`
            })
    });
    let wanted_once: (AreaKind, string)[] = [(AreaKind.Stage, "Stage"), (AreaKind.PracticeFloor, "PracticeFloor")];
    let one_each = wanted_once
        .filter((kind) -> {
            count_of(design, kind.0) != 1
        })
        .map((kind) -> {
            `a house has exactly one ${kind.1}, not ${count_of(design, kind.0)}`
        });
    let mic_area = design.areas.find((a) -> {
        a.name == design.microphone_area
    });
    let mic: string[] = match (mic_area?.kind) {
        AreaKind.Stage | AreaKind.PracticeFloor => [],
        null => {
            [`the microphone stands in "${design.microphone_area}", which is not one of the areas`]
        },
        _ => {
            [
                `the microphone stands in "${design.microphone_area}": it belongs on the stage or the practice floor`,
            ]
        },
    };
    let features = design.features
        .filter((f) -> {
            !names.includes(f.area)
        })
        .map((f) -> {
            `the ${f.kind} belong to "${f.area}", which is not one of the areas`
        });
    let colours = [("walls", design.walls), ("roof", design.roof), ("trim", design.trim)]
        .filter((c) -> {
            !is_hex(c.1.hex)
        })
        .map((c) -> {
            `the ${c.0} colour "${c.1.hex}" is not #rrggbb`
        });
    let sign: string[] = if (!design.sign || design.sign.length() > SIGN_MAX_LETTERS || design.sign.includes("\"")) {
        [
            `the sign "${design.sign}" should be 1 to ${SIGN_MAX_LETTERS} letters with no quotation marks`,
        ]
    } else {
        []
    };
    let in_areas = design.areas.flat_map((a) -> {
        area_problems(design, a)
    });
    size.concat(count)
        .concat(doubled)
        .concat(in_areas)
        .concat(overlapping)
        .concat(one_each)
        .concat(mic)
        .concat(features)
        .concat(colours)
        .concat(sign)
}

/// A toon's brief, in the few words a house needs.
function brief_words(brief: ObjectBrief) -> string {
    let gear = (brief.gear ?? [])
        .map((g) -> {
            `${g.name} (${g.look})`
        })
        .join("; ");
    `
        ${brief.description}
        What they wear and carry: ${gear}
    `
}

/// What the story says about a toon: their row of the cast table, and how the dancer's house came about.
function who_is(name: string, canon: string) -> string {
    let wanted = name.to_lower_case();
    let rows = canon.lines().filter((line) -> {
        line.starts_with("|") && line.to_lower_case().includes(wanted)
    });
    if (!rows) {
        return "A toon of this world. Nothing more is written about them yet.";
    }
    rows.join("\n")
}

/// One ask of Opus; returns the design and the tokens it reported (in, out, cached).
function ask_for_house(
    toon: string,
    brief: string,
    who: string,
    wish: string,
    client: ai.Client,
) -> (HouseDesign, int, int, int) {
    let result = ai.Agent.new(client = client).run(DesignHouse@spec(toon, brief, who, wish));
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

/// Asks Opus for the house; if the plan cannot be built, shows Opus what is wrong and asks once more.
function design_house(
    toon: string,
    brief: string,
    who: string,
    wish: string = "",
    client: ai.Client? = null,
) -> DesignedHouse {
    let model = client ?? Writer;
    let started = baml.time.Instant.now();
    let wished = if (wish) {
        `WHAT THEY ASKED FOR, IN THEIR OWN WORDS\n${wish}`
    } else {
        ""
    };
    let (let first, let first_in, let first_out, let first_cached) = ask_for_house(toon, brief, who, wished, model);
    let problems = house_problems(first);
    if (!problems) {
        return DesignedHouse {
            design: first,
            cost: HouseCost {
                toon: toon,
                model: "opus",
                asks: 1,
                input_tokens: first_in,
                cached_input_tokens: first_cached,
                output_tokens: first_out,
                seconds: started.elapsed().to_seconds(),
                fixed: [],
            },
        };
    }
    log.info(`house: asking again, ${problems.length()} problems: ${problems.join("; ")}`);
    let (let again, let again_in, let again_out, let again_cached) = ask_for_house(
        toon,
        brief,
        who,
        `${wished}\n\nYour last design had these problems. Keep what was good and fix every one:\n- ${problems.join("\n- ")}`,
        model,
    );
    let left = house_problems(again);
    if (left) {
        throw HouseRejected { toon: toon, problems: left }
    }
    DesignedHouse {
        design: again,
        cost: HouseCost {
            toon: toon,
            model: "opus",
            asks: 2,
            input_tokens: first_in + again_in,
            cached_input_tokens: first_cached + again_cached,
            output_tokens: first_out + again_out,
            seconds: started.elapsed().to_seconds(),
            fixed: problems,
        },
    }
}

/// A folder name nothing has yet: the house's name, then -2, -3... if it has been used.
function free_house_folder(name: string) -> string {
    let base = slug(name);
    let tries = [base].concat(
        [2, 3, 4, 5, 6, 7, 8, 9].map((n) -> {
            `${base}-${n}`
        }),
    );
    tries.find((t) -> {
        !baml.fs.exists(`${SETS_DIR}/${t}`)
    })
        ?? throw baml.errors.InvalidArgument { message: `there are already nine houses called ${name}` }
}

/// Builds a kept design (sets/<house>/design.json) as a set, in a background Blender, and checks it.
function rebuild_house(house: string, runs: string = RUNS_DIR) -> string {
    let out = baml.sys.run(
        "python3",
        args = [`${HOUSE_SCRIPTS}/build_house.py`, house, "--runs", runs],
        timeout = baml.time.Duration.from_minutes(HOUSE_BUILD_MINUTES),
        capture_output = true,
    ) catch (e) {
        baml.errors.Io => {
            throw HouseBuildFailed { house: house, reason: "python3 not found" }
        },
        baml.errors.Timeout => {
            throw HouseBuildFailed { house: house, reason: `still building after ${HOUSE_BUILD_MINUTES} minutes` }
        },
    };
    let lines = string.from_utf8(out.stdout).lines();
    for (
        let line in lines.filter((l) -> {
            l.starts_with("HOUSE")
        })
    ) {
        log.info(line);
    }
    if (!out.ok()) {
        let said = lines
            .filter((l) -> {
                l.includes("PROBLEM")
            })
            .join("; ");
        throw HouseBuildFailed { house: house, reason: `${said} ${string.from_utf8(out.stderr)}` }
    }
    `${SETS_DIR}/${house}`
}

/// A toon presses BUY HOUSE: Opus designs their house, and it is built as a set. Returns its folder.
function buy_house(
    toon: string,
    runs: string = RUNS_DIR,
    wish: string = "",
    client: ai.Client? = null,
) -> string {
    //# 1. Who is buying: their brief, and what the story says about them
    let run_dir = character_run(runs, toon) catch (e) {
        ShotFailed => {
            throw ToonUnknown { toon: toon, runs: runs }
        },
    };
    let brief = baml.json.decode<ObjectBrief>(baml.fs.read(`${run_dir}/brief.json`));
    let who = who_is(brief.name, baml.fs.read(CANON_FILE));
    //# 2. Opus designs it; code checks the plan and asks once more if it must
    log.info(`house: asking Opus what ${brief.name} would want`);
    let designed = design_house(brief.name, brief_words(brief), who, wish = wish, client = client);
    //# 3. Keep the design and what it cost, in a folder of its own
    let house = free_house_folder(designed.design.name);
    let folder = Run { dir: `${SETS_DIR}/${house}` };
    baml.fs.mkdir(folder.dir, baml.fs.MkdirOptions { recursive: true });
    folder.save("design.json", designed.design);
    folder.save("design_cost.json", designed.cost);
    log.info(
        `house: "${designed.design.name}", ${designed.design.areas.length()} areas, ${designed.cost.asks} ask(s), ${designed.cost.input_tokens} tokens in, ${designed.cost.output_tokens} out`,
    );
    //# 4. Build it as a set
    rebuild_house(house, runs = runs)
}
