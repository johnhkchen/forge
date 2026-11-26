// Opus for casting: one short structured answer through the lean CLI
// (scripts/claude-lean). Through the plain `claude` the same ask carried about
// 189,000 tokens of tool schemas, MCP servers and skills it never used ($1.80
// for four looks); lean, that overhead is about 1,600 tokens.
client CastingWriter = claude_code.ClaudeCodeClient.new(model = "opus", executable = "scripts/claude-lean", timeout_ms = 180000);

// Casting's two questions for Opus (casting.baml does the rest). Both carry a
// whole ObjectBrief, so whatever comes back goes through the make pipeline as
// any brief does.

/// A look Opus wrote: the brief, why it is worth a headshot, and which way the
/// part could arrive in the story it suits.
class CastingIdea {
    brief: ObjectBrief,
    why: string @description(
        "One plain sentence a visitor can read: what reading of the part this is, and what it is for",
    ),
    suits: string? @description(
        "The id of the way it could arrive (from the list given) that this look suits best, or null if none",
    ),
}

/// The looks of one answer (a class, not a bare list: the Claude Code client
/// hands the answer's shape over as a tool's input, which must be an object).
class CastingIdeas {
    looks: CastingIdea[],
}

/// More looks for a part: briefs of characters who could play it, each a
/// different reading of the breakdown. `arrivals` are the ways it could come
/// into the story (ids, names and pitches); `wanted` are the ids no look
/// written so far suits, which the new ones should cover between them.
function CastingLooks(breakdown: string, have: string[], arrivals: string, wanted: string[], count: int) -> CastingIdeas {
    client: CastingWriter
    prompt: `
        ${role("system")}
        You are a casting director for a small 3D toy world, writing briefs for
        a pipeline that turns one brief into one character: an image model
        draws it alone on a plain background in a T-pose, an image-to-3D model
        (TRELLIS.2) lifts the picture into a mesh, and it is rigged and drawn as
        flat cards, one card a bone, in a comic look, in bold ink and as pixel
        art. From the crew camera a head is only a few pixels across, so big
        simple shapes and a face of big round eyes win over fine detail.

        Write ${count} briefs, each a different way the part below could be
        played, as headshots a casting director would ask for. Keep to the
        breakdown: its height, its colours, its must-haves and must-nots. Each
        is a character (character: true), standing in a T-pose, arms straight
        out, empty hands, nothing loose, a face that reads from across a stage.
        Do not repeat a look already written: ${have.join(", ")}.

        The ways the part could arrive in the story are below. Between them, the
        new looks must suit each of these, which no look written so far suits:
        ${if (wanted) { wanted.join(", ") } else { "(all are suited already)" }}.
        A look can hint at its job by its shape and what it wears, never by
        anything in its hands: whatever the story has it carry is a prop, made
        on its own afterwards. Say in each look's "suits" which way it fits.

        ${role("user")}
        The part:
        ${breakdown}

        The ways it could arrive:
        ${arrivals}

        ${ctx.output_format()}
    `
}

/// A brief revised to answer a casting director's notes on the last take.
function Revise(brief: ObjectBrief, breakdown: string, notes: string[]) -> ObjectBrief {
    client: CastingWriter
    prompt: `
        ${role("system")}
        You revise a character brief for a callback. The character was built
        from the brief below and performed; the notes say what to change. Change
        what the notes ask and nothing else: keep the name unless a note asks
        otherwise, keep the T-pose and every rule a character brief keeps, and
        stay inside the part's breakdown.

        ${role("user")}
        The part:
        ${breakdown}

        The brief as it was:
        ${baml.json.stringify(brief, indent = 2)}

        The notes:
        ${notes.map((n) -> { `- ${n}` }).join("\n")}

        ${ctx.output_format()}
    `
}
