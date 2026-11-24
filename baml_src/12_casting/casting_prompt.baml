// Casting's two questions for Opus (casting.baml does the rest). Both return a
// whole ObjectBrief, so whatever comes back goes through the make pipeline as
// any brief does.

/// More looks for a part: briefs of characters who could play it, each a
/// different reading of the breakdown.
function CastingLooks(breakdown: string, have: string[], count: int) -> ObjectBrief[] {
    client: Writer
    prompt: `
        ${role("system")}
        You are a casting director for a small 3D toy world, writing briefs for
        a pipeline that turns one brief into one character: an image model
        draws it alone on a plain background in a T-pose, an image-to-3D model
        (TRELLIS.2) lifts the picture into a mesh, and it is rigged and drawn as
        flat cards, one card a bone, in a comic look, in bold ink and as pixel
        art.

        Write ${count} briefs, each a different way the part below could be
        played, as headshots a casting director would ask for. Keep to the
        breakdown: its height, its colours, its must-haves and must-nots. Each
        is a character (character: true), standing in a T-pose, arms straight
        out, empty hands, nothing loose, a face that reads from across a stage.
        Do not repeat a look already written: ${have.join(", ")}.

        ${role("user")}
        The part:
        ${breakdown}

        ${ctx.output_format()}
    `
}

/// A brief revised to answer a casting director's notes on the last take.
function Revise(brief: ObjectBrief, breakdown: string, notes: string[]) -> ObjectBrief {
    client: Writer
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
