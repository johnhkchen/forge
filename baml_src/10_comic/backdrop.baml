// A painted backdrop: one picture Codex draws once, put behind every panel
// set in a place. Panels are drawn with no background of their own, so the
// page lays them over this picture (or over a flat sky when there is none).
// It is the cheapest scenery there is: far things, painted once, reused.
//
//   baml run backdrop -- --place rooftop --scene "a city skyline at night..."
//
// Saved as comics/backdrops/<place>.png; scripts/comic/kit.py picks it up by
// name. Costs one Codex image.

const BACKDROPS_DIR = "comics/backdrops";

const BACKDROP_RULES = `
    A painted background for a webcomic panel: scenery only, far away, for
    characters to stand in front of. Square image. Drawn like a clean
    webcomic: flat colors in two or three tones, simple bold shapes, a soft
    even ink line on the nearest shapes only, no gradients except one in the
    sky, no texture, no photographic detail. Nothing in the foreground: the
    bottom third is plain and quiet, because characters and a floor are
    drawn over it. The horizon sits a little below the middle. No people
    close up, no animals, no text, no letters, no signs with writing, no
    borders, no frame.
`;

function backdrop_request(scene: string) -> string {
    `
        Use your built-in image_gen tool to generate exactly one square image,
        then reply with the single word: done. Do not run shell commands and
        do not edit files.

        Image: ${BACKDROP_RULES}

        The scene: ${scene}
    `
}

/// Has Codex paint a place's backdrop; returns the file.
function backdrop(place: string, scene: string) -> string {
    baml.fs.mkdir(BACKDROPS_DIR, baml.fs.MkdirOptions { recursive: true });
    codex_picture(BACKDROPS_DIR, backdrop_request(scene), [], `${BACKDROPS_DIR}/${slug(place)}.png`)
}

test "a backdrop is asked for as far scenery with a quiet bottom third and no writing" {
    let asked = backdrop_request("a city skyline at night");
    assert.is_true(asked.includes("exactly one square image"));
    assert.is_true(asked.includes("bottom third is plain"));
    assert.is_true(asked.includes("no text"));
    assert.is_true(asked.includes("The scene: a city skyline at night"))
}
