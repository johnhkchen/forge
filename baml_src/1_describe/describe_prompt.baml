// Step 1: turn a loose idea into a brief that the next three steps can use.
//
// The brief is written by Opus through the Claude Code CLI (the subscription,
// not a metered key). It stays short on purpose: the image model and the 3D
// model each read only a paragraph, and a long brief invites details neither
// of them can render.

class ObjectBrief {
    name: string @description("A short, plain name for the object, 2 to 5 words, like 'Brass Diving Helmet'"),
    description: string @description(
        "Two or three sentences: what it is, its shape and proportions, what it is made of",
    ),
    subject: string @description(
        "One paragraph describing ONLY the object's appearance for an image model: silhouette, parts, materials, colors, surface wear. No background, lighting, camera or style words",
    ),
    materials: Material[] @description("The 1 to 4 visually distinct materials, largest area first"),
    size_m: float @description("The object's largest real-world dimension, in meters"),
    // Optional so briefs from earlier runs still load.
    character: bool? @description(
        "true if it is a creature or person meant to be rigged and animated; it is then drawn and built standing in a T-pose, facing front",
    ),
    lowpoly_triangles: int? @description(
        "Triangle budget for the low-poly version, from the style the idea asks for (early real-time props 300-800; old-school RuneScape-like characters 600-1500)",
    ),
    gear: GearItem[]? @description(
        "For characters: every piece of clothing, armor and equipment, so each can be built separately and taken off or swapped. Empty for objects",
    ),
    lowpoly_style: string? @description(
        "One line on the low-poly look the idea calls for, like 'faceted flat-shaded, chunky proportions, colors painted in'",
    ),
}

// Gear is kept separate from a character's body, the way games do it: worn
// pieces sit over a complete body, attached and held props hang off a named
// point (a hand, the head, the back) so they can be shown, hidden or swapped.
class GearItem {
    name: string @description("Short plain name, like 'wool singlet' or 'umbrella'")
    kind: "worn" | "attached" | "held" @description(
        "worn: clothing or armor that follows the body; attached: a rigid piece fixed to one spot (hat, backpack, sheathed sword); held: carried in a hand",
    )
    slot: string @description(
        "Where it goes: one of head, face, neck, torso, arms, hands, hip, legs, feet, back, hand_right, hand_left",
    )
    look: string @description("Its shape, material and color in one line")
}

class Material {
    part: string @description("Which part of the object, like 'shell' or 'viewport rims'"),
    look: string @description("The surface, like 'polished brass, slightly tarnished' or 'matte red rubber'"),
    metallic: bool,
}

function Describe(idea: string) -> ObjectBrief {
    client: Writer
    prompt: `
        ${role("system")}
        You write briefs for a pipeline that turns one idea into one 3D object:
        an image model draws the object alone on a plain background, an
        image-to-3D model (TRELLIS.2) lifts that picture into a textured mesh,
        and an artist finishes it in Blender.

        Pick ONE concrete, physical object that fits the idea. Favor a clear,
        readable silhouette and a few chunky parts over thin wires, glass,
        fur, smoke or text, since image-to-3D reconstructs those badly.

        For a character (a creature or person to be rigged): describe it
        standing in a T-pose, arms straight out to the sides, legs slightly
        apart, empty hands, nothing loose (no capes, loose hair strands,
        dangling straps or held weapons). Clothing and gear fit close to the
        body. Size is its standing height. Give it a face that still reads
        when built from a handful of flat shapes: head level, looking
        straight ahead, eyes not hidden by hair or a brim, and two or three
        bold features named plainly (a heavy brow, a big nose, a beard,
        tusks, pointed ears). List every piece of clothing, armor and
        equipment in gear. Held props (a weapon, an umbrella, a tool) go in
        gear only, never in the subject: the picture shows the character
        with empty hands, and props are made separately.

        ${ctx.output_format()}

        ${role("user")}
        Idea: ${idea}
    `
}
