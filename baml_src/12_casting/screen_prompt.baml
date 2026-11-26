// The screen test's one question for a model: what the breakdown rules out that
// only eyes can see (text, a held thing, a glow, a menacing face). Everything
// else the screen measures from the pictures itself (scripts/casting/screen.py).

// Haiku through the logged-in CLI, as every model call here, kept lean
// (scripts/claude-lean: no MCP servers, skills or user settings in its context).
client Looker = claude_code.ClaudeCodeClient.new(model = "haiku", executable = "scripts/claude-lean", timeout_ms = 300000);

/// What one headshot breaks of the breakdown's must-nots, as seen.
class SeenShot {
    id: string @description("The headshot's id, exactly as given above its picture"),
    breaks: string[] @description(
        "Each must-not this picture breaks, in a few plain words (\"an antenna on its head\", \"its eyes glow\"); empty when it breaks none",
    ),
    pose: "t-pose" | "other" @description("t-pose when it stands front on, arms straight out to the sides, hands empty"),
}

class SeenShots {
    shots: SeenShot[],
}

/// Every headshot shown at once, each under its id; the must-nots and the
/// must-haves of the breakdown beside them.
function ScreenMustNots(must_not: string[], must_have: string[], ids: string[], pictures: image[]) -> SeenShots {
    client: Looker
    prompt: `
        ${role("system")}
        You check character pictures for a casting director against a short
        list of rules. Be literal and brief. Only report what you can see.

        ${role("user")}
        Must not have:
        ${must_not.map((m) -> { `- ${m}` }).join("\n")}

        Must have (for the pose only):
        ${must_have.map((m) -> { `- ${m}` }).join("\n")}

        The pictures, in this order: ${ids.join(", ")}.
        ${pictures}

        For every picture, in the same order, say which must-nots it breaks.

        ${ctx.output_format()}
    `
}
