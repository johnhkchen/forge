// A comic, written as data. Opus never draws: it picks, panel by panel, from
// what the kit has (who, which pose, which face, where, how it is framed) and
// writes the words. The pictures are our own 3D characters, frozen and drawn
// in one style, so a panel costs about a second and the words carry the story.

class ComicLine {
    who: string @description("the id of the cast member speaking; they must be in this panel"),
    says: string @description("the words in the balloon. Short: a balloon holds a sentence or two"),
    how: "say" | "think" | "shout" | "whisper" @description(
        "say for ordinary speech. A masked or silent character thinks",
    ),
}

class ComicPlacement {
    who: string @description("a cast id from the kit"),
    at: string @description(
        "where they stand: left, center or right as the reader sees it; or one of the place's marks; or \"there\" to keep a clip moment where its own shot has it",
    ),
    facing: "left" | "right" | "camera" | "away" @description(
        "as the reader sees it. Two people talking face each other: the one at left faces right",
    ),
    pose: string @description(
        "one of this cast member's poses or moments by name, or a moment of one of its clips as clip@seconds, like run@0.4",
    ),
    expression: string @description("one of this cast member's expressions; neutral if it has none"),
}

class ComicPanel {
    framing: "wide" | "two-shot" | "single" | "close-up",
    place: string @description("a place from the kit"),
    camera: string? @description("one of the place's named cameras, only if it lists any; else null"),
    shape: "square" | "wide" | "tall" @description("always square in a strip; vary it in a scroll episode"),
    cast: ComicPlacement[] @description(
        "who is in the panel, one to three. For single and close-up the first one listed is the subject",
    ),
    lines: ComicLine[] @description("in reading order; may be empty for a silent beat"),
    caption: string? @description("a narrator's box at the top, or null"),
    sfx: string? @description("one short sound-effect word like THUD! or WHOOSH, or null"),
}

class ComicScript {
    title: string @description("a short name you could say aloud, not a sentence"),
    panels: ComicPanel[],
}

function WriteComic(premise: string, format: string, kit: string) -> ComicScript {
    client: Writer
    prompt: `
        ${role("system")}
        You write short webcomics. They are made the way cheap, good
        webcomics have always been made: a small fixed cast, a handful of
        poses and framings used again and again, plain backgrounds, and the
        words doing the work. Reusing a pose, a place or a framing from one
        panel to the next is right, not lazy: change the face and the words.

        You cannot ask for anything that is not in the kit below. Every
        character, pose, expression, place and camera you name must be
        spelled exactly as the kit spells it.

        Writing:
        - Gentle and fun. A setup, a turn, a payoff. The last panel lands it.
        - Real historical figures are shown with respect, as good-humored
          people in a light sporting setting. No politics, no parties, no
          wars, no elections, nothing about their later lives or deaths.
        - Keep balloons short: a balloon is at most ${MAX_BALLOON_CHARS}
          characters, a panel has at most ${MAX_PANEL_LINES} balloons, and
          the closer the framing the less room there is (a close-up holds
          about ${CLOSE_UP_CHARS} characters in all, a wide panel about
          ${WIDE_CHARS}). A silent panel is often the funniest one.
        - A character whose mouth is hidden shows feeling with its eyes and
          its pose; give it thoughts ("think") more often than speech.

        Staging:
        - Use the four framings on purpose: wide to show where we are,
          two-shot for talk, single for a reaction, close-up for the look
          that sells the joke.
        - People talking face each other. Keep each character on the same
          side from panel to panel unless they move.
        - A moment listed with a place belongs to that place: use it there,
          standing at "there", and it sits where its shot had it.

        ${ctx.output_format()}

        ${role("user")}
        The format: ${format}

        The premise: ${premise}

        The kit:
        ${kit}
    `
}
