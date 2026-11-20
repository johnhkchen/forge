// Step 6 (only when asked): a character's props get briefs of their own.
//
// A character is drawn and built with empty hands, so that a game can give
// it the umbrella, take it away, or hand it a sword instead. The umbrella is
// still wanted: it becomes a small object of its own, made by the same
// pipeline, and the character's run records which attachment point (socket)
// it goes on. Opus writes the prop's brief from the gear item, with the
// character's brief in view so size and style match.

class PropBrief {
    brief: ObjectBrief @description("The prop alone, as an object of its own"),
    grip: string @description(
        "Where the prop meets the character, in plain words, like 'the handle, a hand's width from its lower end' or 'the inside of the crown'",
    ),
}

function DescribeProp(character: ObjectBrief, item: GearItem, socket: Socket) -> PropBrief {
    client: Writer
    prompt: `
        ${role("system")}
        You write briefs for a pipeline that turns one idea into one 3D object:
        an image model draws the object alone on a plain background, an
        image-to-3D model (TRELLIS.2) lifts that picture into a textured mesh,
        and an artist finishes it in Blender.

        This object is a prop for a game character that already exists. The
        character was made with empty hands; the prop is made alone, and a
        game attaches it to the character at a named point.

        Write the brief for the prop ALONE: no hand, no character, nothing
        else in the picture. Favor a clear, readable silhouette and a few
        chunky parts over thin wires, glass, fur or text, since image-to-3D
        reconstructs those badly. If it opens or folds (an umbrella, a fan, a
        book), describe it in the one state it is carried in.
        - size_m is its largest real-world dimension, in proportion to the
          character.
        - character is false and gear is empty.
        - Match the character's look: the same low-poly style, and a
          triangle budget of 60 to 300.
        - grip says where it meets the character.

        ${ctx.output_format()}

        ${role("user")}
        The character: ${character.name}, ${character.size_m} m tall. ${character.description}
        Its low-poly style: ${character.lowpoly_style ?? "early real-time game character: clean simple shapes"}

        The prop: ${item.name} (${item.kind}, goes on the character's ${socket}). ${item.look}
    `
}
