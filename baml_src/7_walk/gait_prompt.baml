// How a character carries itself, as four numbers. The walk itself is worked
// out in Blender from the model's measured build (walk.py); this is only the
// part a tape measure can't tell: is it heavy-footed, sneaking, showing off,
// stiff? Asked once per character, from its brief.

class GaitTraits {
    weight: float @description(
        "0 to 1. How heavy it moves for its size: 0.1 a dancer or a cat, 0.4 an ordinary adult, 0.7 a big brawler in armor, 1.0 a giant or an ogre",
    ),
    stealth: float @description(
        "0 to 1. How quiet and careful: 0 doesn't care who hears, 0.3 ordinary, 0.9 an assassin creeping on bent knees",
    ),
    swagger: float @description(
        "0 to 1. How much show in the walk: 0 contained and plain, 0.4 relaxed, 0.9 a rolling sailor's strut or a boss's stomp",
    ),
    stiffness: float @description(
        "0 to 1. How rigid the body is: 0.1 loose and springy, 0.4 ordinary, 0.8 plate armor, great age, or a hide like stone",
    ),
    why: string @description("One plain sentence on the walk you pictured"),
}

function HowItWalks(name: string, description: string, subject: string) -> GaitTraits {
    client: Writer
    prompt: `
        ${role("system")}
        You direct character animation for a game. Given a character, you
        say how it walks, as four numbers an animation tool will use. Picture
        this one character walking across a room at its usual pace, then
        answer. Use the whole range: a troll and a ninja should come out far
        apart. Judge from what it is and how it is built, not from its gear's
        colors.

        ${ctx.output_format()}

        ${role("user")}
        ${name}

        ${description}

        ${subject}
    `
}
