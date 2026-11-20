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

        ${ctx.output_format()}

        ${role("user")}
        Idea: ${idea}
    `
}
