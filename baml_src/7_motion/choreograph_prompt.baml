// Motion, step 1: Opus turns a plan in words ("sneaks along the ledge, breaks
// into a sprint, vaults the wall") into a shot list a program can follow.
//
// A shot list never holds joint angles. It names poses from our own pose
// library (motion/poses.json, written by scripts/motion/author_poses.py) and
// says where along a path each one is reached, how fast the character is
// going there, and how long the motion into it lasts. scripts/motion/plan_shot.py
// places the poses, and MotionBricks fills in the movement between them.

/// One row of the plan the person approved.
class BeatPlan {
    time: string @description("When, like '2-5 s'"),
    action: string @description("What happens"),
    driven_by: string @description("Which poses drive it"),
}

// The pose library, by name. `the pose names match the library` (in
// choreograph.baml) fails if this and motion/poses.json drift apart.
type PoseName = "crouch"
    | "crouch_look_left"
    | "crouch_look_right"
    | "sneak_left"
    | "sneak_right"
    | "sprint_left"
    | "sprint_right"
    | "vault_takeoff"
    | "vault_over"
    | "land_three_point"
    | "rise"
    | "draw"
    | "hero_stance";

const POSE_CARD = `
    crouch             low crouch, both feet flat, hands near the knees, looking ahead. Still.
    crouch_look_left   the same crouch, head and chest turned to the left. Still.
    crouch_look_right  the same crouch, head and chest turned to the right. Still.
    sneak_left         a low sneaking step, left foot forward and planted. Moving, about 0.8 m/s.
    sneak_right        the mirror step, right foot forward. Moving, about 0.8 m/s. Alternate the two.
    sprint_left        mid-sprint, leaning forward, left foot striking. Moving, 4 to 5 m/s.
    sprint_right       the mirror stride, right foot striking. Moving, 4 to 5 m/s. Alternate the two.
    vault_takeoff      last step before a waist-high wall: left foot planted, right hand reaching for the wall top. Moving, about 3.5 m/s.
    vault_over         over the wall: right hand planted on the wall top, hips above it, legs tucked to the left. Moving, about 3 m/s.
    land_three_point   deep landing crouch: both feet and the left hand on the ground, right arm out behind. Still.
    rise               halfway up from the landing, weight on both feet, right hand going to the sword grip over the right shoulder. Still.
    draw               standing, right hand at the grip behind the right shoulder, about to draw. Still.
    hero_stance        feet wide, knees soft, sword held out low to the right, chin up. Still.
`;

type Pin = "left_hand" | "right_hand" | "left_foot" | "right_foot";

/// A point on the ground, in metres. The character starts at x 0, z 0 facing +z; +x is to its left.
class PathPoint {
    x: float,
    z: float,
}

class Move {
    pose: PoseName @description("The library pose the character reaches at the end of this move"),
    at_m: float @description(
        "Where it reaches the pose: metres along the path from its start. Never less than the move before it",
    ),
    side_m: float @description("Metres to the left of the path at that point (negative: right). Usually 0"),
    facing_deg: float @description(
        "Which way the body faces there, in degrees turned to the left of the path's direction. 0 faces along the path",
    ),
    speed_mps: float @description(
        "How fast it is travelling as it passes through the pose, in metres per second. 0: it arrives and holds still. Use the speed the pose is described with, or less",
    ),
    tokens: int @description(
        "How long the motion INTO this pose lasts: a whole number 6 to 16. It plays for (4 * tokens - 7 - early_frames) / 30 seconds",
    ),
    early_frames: int @description(
        "0 to 20. Frames cut off the end, so the character does not quite arrive before heading for the next pose. 0 for a pose it must hit exactly (a hold, a landing, a hand plant); 4 to 8 for poses it runs through",
    ),
    pins: Pin[] @description(
        "Hands and feet that must end exactly where the pose has them (a hand on a wall top, feet on a landing spot). Empty for most moves",
    ),
    hold_pins_frames: int @description(
        "How many frames the PREVIOUS move's pins stay put after this move starts, before letting go. 0 if it had none",
    ),
}

class ShotBeat {
    name: string @description("The beat, in two to five plain words"),
    seconds: float @description("How long the beat lasts"),
    moves: Move[] @description("One or more moves, played in order. Their lengths add up to the beat's seconds"),
}

/// Where a carried prop sits from a moment on.
class PropCue {
    prop: string @description("What it is, like 'katana'"),
    socket: "hand_right" | "hand_left" | "head" | "back" | "hip" @description(
        "The character's attachment point it sits on",
    ),
    from_seconds: float @description("From when; 0 for where it starts"),
}

class CameraCue {
    from_seconds: float,
    view: "three_quarter_tracking" | "low_three_quarter" | "side_tracking" | "front" @description(
        "three_quarter_tracking: ahead and to one side, following; low_three_quarter: the same from near the ground, looking up; side_tracking: level, from the side; front: facing the character",
    ),
    distance_m: float @description("How far the camera is from the character, 3 to 8"),
}

class ShotList {
    title: string @description("A short plain name for the shot"),
    start_pose: PoseName @description("The pose it is holding when the shot starts, at the path's start"),
    path: PathPoint[] @description(
        "The route over the ground as 4 to 12 points, in order, from where the shot starts to where it ends. Put more points on curves. A smooth curve is drawn through them",
    ),
    beats: ShotBeat[],
    props: PropCue[] @description(
        "Where each carried prop is, and when it changes hands. Empty if there are none",
    ),
    camera: CameraCue[],
}

function Choreograph(brief: string, beats: BeatPlan[]) -> ShotList {
    client: Writer
    prompt: `
        You are planning one continuous shot for an animated character. A motion model will
        fill in the movement between key poses; your job is to say which poses, where, and
        when. You never write joint angles: you pick poses by name from this library.

        THE POSE LIBRARY
        ${POSE_CARD}

        THE SHOT
        ${brief}

        THE BEATS, as approved. Keep their order and their timing.
        ${beats}

        HOW A MOVE WORKS
        - Each move generates the motion from wherever the character is to one pose at one
          place. It plays for (4 * tokens - 7 - early_frames) / 30 seconds, tokens 6 to 16.
          So one move lasts between 0.57 s (6 tokens) and 1.9 s (16 tokens).
        - Add up the moves of a beat: they must come within 0.15 s of the beat's seconds.
          Show the sum to yourself before you answer.
        - A still pose (speed 0) is a stop. To hold or shift in place, give the next move the
          same at_m. Looking left and then right is two moves at the same place.
        - Travelling poses come in left/right pairs. Alternate them, one move per step or
          stride. Sneaking steps are about 0.5 m apart; sprint strides 1.6 to 2.2 m apart.
          Distance covered in a move must fit its time and speed: do not ask for 3 m in half
          a second at walking speed.
        - To speed up or slow down, change speed_mps gradually from move to move.
        - The path's own direction sets where the character faces; facing_deg turns it away
          from that (for example to end facing a camera).
        - Obstacles are not known to the motion model. Poses that touch something (a hand on
          a wall top, a landing) must be placed where that thing is, and pinned.

        ${ctx.output_format()}
    `
}
