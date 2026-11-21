// A house for a toon, to their own specification.
//
// In the story, a toon who has saved enough presses the BUY HOUSE button and
// gets a house they chose themselves. Here that is one ask of Opus: it reads
// the toon's own brief and who they believe they are, and designs the house
// they would want. Code checks the design, builds it as a set and puts it in
// the world (house.baml). Asking again makes a different house.
//
// The design is a floor plan in plain rectangles, so that it can be built from
// simple pieces without anyone looking at it first.

class HouseColour {
    name: string @description("What you would call it, like 'sun-baked terracotta'"),
    hex: string @description("The colour as #rrggbb"),
}

enum AreaKind {
    Stage @description("A small raised platform to perform on"),
    PracticeFloor @description("A clear floor to dance or train on"),
    SittingRoom,
    Bedroom,
    Kitchen,
    DressingRoom,
    Patio @description("Paved and open to the sky"),
    Garden @description("Planted and open to the sky"),
    Porch @description("A covered strip along the front"),
}

class HouseArea {
    name: string @description("A short name of her own for it, like 'the tablao'"),
    kind: AreaKind,
    x_m: float @description("Its left edge, in metres from the house's left side"),
    z_m: float @description("Its back edge, in metres from the back of the house"),
    wide_m: float,
    deep_m: float,
    floor: HouseColour,
    about: string @description("One plain sentence: what it is for and what is in it"),
}

class HouseFeature {
    kind: "arches"
        | "flower_pots"
        | "lanterns"
        | "string_lights"
        | "mirror_wall"
        | "awning"
        | "fountain"
        | "shutters",
    area: string @description("The name of the area it belongs to, exactly as written in areas"),
    about: string @description("One short sentence"),
}

class HouseMaterial {
    part: string,
    look: string,
}

class HouseDesign {
    name: string @description("What the house is called, 2 to 4 words, a name you could say aloud"),
    style: string @description("One sentence: the kind of house it is"),
    why: string @description(
        "One or two sentences in plain words: why this is the house this toon would ask for",
    ),
    wide_m: float @description("The whole house, side to side, 8 to 14"),
    deep_m: float @description("The whole house, back to front, 7 to 12"),
    faces: "the grass" | "the spawn spot" | "the morning sun" | "the open ground" @description(
        "What the open front looks out on: the grass is to the west, the spawn spot to the north, the morning sun to the east, open unbuilt ground to the south",
    ),
    faces_why: string @description("One short sentence"),
    walls: HouseColour,
    roof: HouseColour,
    trim: HouseColour @description("Doors, posts, window frames, the edge of the stage"),
    materials: HouseMaterial[] @description("2 to 4 materials, largest first"),
    areas: HouseArea[] @description("3 to 6 rooms and outdoor areas, each a rectangle on the plan"),
    microphone_area: string @description(
        "The name of the area her microphone stands in: the stage or the practice floor",
    ),
    features: HouseFeature[] @description("2 to 5 touches that make it hers"),
    sign: string @description("A few words for a small sign by the front, at most 22 letters"),
}

function DesignHouse(toon: string, brief: string, who: string, wish: string) -> HouseDesign {
    client: Writer
    prompt: `
        ${role("system")}
        You design houses for the characters of a small, kind, cosy story
        world, the way a patient architect would for a friend. The world is
        a game being built a little at a time; its characters call
        themselves toons. One of them has saved up and bought a house built
        to their own specification. You are given who they are. Design the
        house THEY would ask for: it should be plainly theirs, in its
        colours, its rooms and what it is for. Warm and charming, never
        grand: a home, not a palace.

        HOW THE PLAN WORKS
        The house is drawn on a rectangle, wide_m by deep_m, as plain
        rectangles that do not overlap. x_m counts from the left side, z_m
        from the back wall; the front is at z = deep_m. The house is built
        like a film set: back and side walls, a roof over the back rooms,
        and the front left open so you can see in. So put what should be
        seen (the stage, the practice floor) where the front can see it, and
        private rooms (bedroom, dressing room) along the back.

        RULES (the design is checked against these)
        - wide_m is 8 to 14, deep_m is 7 to 12.
        - 3 to 6 areas. Every area is at least 2 m each way and lies wholly
          inside the house. No two areas overlap; they may share an edge.
        - Exactly one Stage, 2.5 to 5 m wide and 2 to 4 m deep.
        - Exactly one PracticeFloor, at least 3 m each way.
        - microphone_area names the Stage or the PracticeFloor.
        - Each feature's area is the name of one of the areas.
        - Colours are #rrggbb.
        - sign is at most 22 letters, with no quotation marks.

        ${ctx.output_format()}

        ${role("user")}
        THE TOON: ${toon}

        HOW THEY LOOK (their own brief)
        ${brief}

        WHO THEY ARE (from the story so far)
        ${who}

        ${wish}
    `
}
