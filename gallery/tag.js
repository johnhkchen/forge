// Forge gallery: a field of Roosevelts playing tag, drawn five ways, to time flat cards against meshes. #/tag/<run>
//
// One game, many ways to draw it. The game (who is "it", who runs where, which move each is in and how far
// through it) is worked out from a seed in fixed steps, so every way of drawing sees exactly the same field.
//
//   meshes, one by one      every runner is his own skinned meshes, drawn the comic way with the ink shell
//   meshes, all at once     the same meshes, every runner in one draw per piece: the bones come from a picture
//   low-poly, all at once   the cheapest real mesh there is of him (1,695 triangles, plain colours), drawn the same way
//   meshes near, cards far  the painted meshes within a few metres of the eye, cards beyond
//   cards, one by one       the cards page as it is: 16 cards a runner, each placed here and drawn on its own
//   cards, all at once      every card of every runner in one draw: the graphics card picks each card's picture
//                           and places it, from the same picture of bones
//   ... search off far away the same, and past a few metres a card's picture is laid flat (no search by depth)
//
// Moving the skeletons costs the same whichever way they are drawn, so it is timed apart, and it can be shared:
// every move is sampled once, thirty poses a second, into a table (a picture the graphics card can read), and
// a runner is then just a place, a heading and a row of that table. Or every runner can work his own skeleton
// out each frame, the plain way. Both are offered to every way of drawing.
//
// The moves come from MOVES below: a name, a .glb, which frames, and whether it loops. Swapping a move is an
// edit of that table.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { clone as cloneSkinned } from "three/addons/utils/SkeletonUtils.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { eyeInBone, choose, place, corners, marchSteps, density, FILL, inBone } from "./impostor-math.js";
import { CARD_VERTEX, CARD_FRAGMENT, JOINT_FRAGMENT, TOON_FRAGMENT, INK_FRAGMENT, picture, lineUniforms, setBalls, sheetBalls, skinFor } from "./impostor.js";
import { LOOKS, lookOf, bakedFor, modelsOf, paintOf, setPaint, cardLine, cardNumber, Screen, FINE_FROM, withoutHeads } from "./looks.js";

// name: where its poses come from.
//   glb      a file in the run's folder ("profiles/...") or anywhere the gallery serves ("shots/...")
//   from,to  the frames to use, 30 a second (left out: the whole clip)
//   loop     true: the last frame is the first again;  "find": look for the cleanest loop inside the frames;
//            left out: played once and held
//   shot     the clip was cut from a filmed shot, so he is somewhere on a set facing anywhere: he is brought to
//            the middle and turned to face ahead first (a move that travels: by the way it travels; one that
//            stays put: by the way his hips face on its first frame), and what travel is left is taken out,
//            because the game moves the runner
//   speed    metres a second over the ground at normal playing speed; left out for a shot's loop, it is
//            measured from how far the loop travels
//   frame    hold this one frame instead of playing
//   like     no clip of its own: stand in with another move
//   or       the move to use instead if the file can't be fetched
// The tag moves are one shot (shots/tag-moves: a run, a dodge, a tag, being tagged, catching breath, a laugh, a
// sprint), cut by frame. plain_run is the run made without it, kept to fall back on.
const SHOT = "shots/tag-moves/painted-tag.glb";
export const MOVES = {
  run: { glb: SHOT, from: 42, to: 197, loop: "find", shot: true, or: "plain_run" },
  sprint: { glb: SHOT, from: 582, to: 737, loop: "find", shot: true, or: "plain_run" },
  dodge: { glb: SHOT, from: 222, to: 257, shot: true, or: "plain_run" },
  tag: { glb: SHOT, from: 282, to: 317, shot: true, speed: 0, or: "plain_tag" },
  tagged: { glb: SHOT, from: 342, to: 392, shot: true, speed: 0, or: "plain_tagged" },
  breath: { glb: SHOT, from: 417, to: 497, shot: true, speed: 0, or: "plain_breath" },
  laugh: { glb: SHOT, from: 522, to: 557, shot: true, speed: 0, or: "plain_laugh" },
  walk: { glb: "profiles/painted-walk.glb", loop: true, speed: 1.31 },
  plain_run: { glb: "profiles/painted-run.glb", loop: true, speed: 3.26 },
  plain_tag: { like: "plain_run", frame: 10, speed: 0 },
  plain_tagged: { like: "walk", frame: 6, speed: 0 },
  plain_breath: { like: "walk", frame: 0, speed: 0 },
  plain_laugh: { like: "walk", frame: 13, speed: 0 },
};
const LOW = "profiles/lowpoly-walk.glb";   // the same man in his low-poly version: the same skeleton, plain colours on its points
const BODY = "profiles/painted-walk.glb"; // the meshes, bones and binds every move is played on (the file the cards were cut from)
const FPS = 30;
const COLUMNS = 12;       // the pose table's columns a bone: where the bone is (4), its bind for the painted mesh (4), for the low-poly one (4)
const COUNTS = [10, 50, 100, 250, 500, 1000];
const WAYS = [
  { id: "mesh-each", name: "Meshes, one by one", most: 500 },
  { id: "mesh-batch", name: "Meshes, all at once" },
  { id: "mesh-low", name: "Low-poly meshes, all at once" },
  { id: "card-each", name: "Cards, one by one", most: 500 },
  { id: "card-batch", name: "Cards, all at once" },
  { id: "card-far", name: "Cards, all at once, search off far away" },
  { id: "mix", name: "Meshes near, cards far" },
];
const NEAR_M = 9;          // "meshes near, cards far": a runner nearer the eye than this is a mesh
const FAR_M = 12;         // "search off far away": past this a card's picture is laid flat
const JOINTS_M = 8;       // cards drawn all at once: a runner nearer than this has a piece of the real model in each big joint (bake_joints.py); further off his joints are the cards' own
const STEP = 1 / 60;      // the game's own clock
const SKY = 0xcfdde6;

// ---------- the game ----------

const RUN = 0, WANDER = 1, DODGE = 2, BREATH = 3, TAGGING = 4, TAGGED = 5, LAUGH = 6;
const MOVE_OF = ["run", "walk", "dodge", "breath", "tag", "tagged", "laugh"];

function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Tag, with simple steering. Every runner has a place, a heading, a state and how far through its move he is.
class Game {
  constructor(count, seed, speeds, lengths) {
    this.count = count;
    this.speeds = speeds;
    this.lengths = lengths; // how long each move plays, in seconds
    this.half = Math.min(30, Math.max(8, 3 + 0.9 * Math.sqrt(count))); // the field: a square this far each way
    this.rand = rng(seed);
    const n = count;
    this.x = new Float32Array(n); this.z = new Float32Array(n); this.heading = new Float32Array(n);
    this.state = new Uint8Array(n); this.left = new Float32Array(n); this.breath = new Float32Array(n).fill(1);
    this.safe = new Float32Array(n); this.clock = new Float32Array(n); this.sprinting = new Uint8Array(n);
    this.side = new Int8Array(n); this.wait = new Float32Array(n); this.lean = new Float32Array(n);
    this.scare = Math.min(10, this.half * 0.55); // how near "it" must be before a runner bolts
    for (let i = 0; i < n; i++) {
      this.x[i] = (this.rand() * 2 - 1) * this.half * 0.9;
      this.z[i] = (this.rand() * 2 - 1) * this.half * 0.9;
      this.heading[i] = this.rand() * Math.PI * 2;
      this.state[i] = WANDER;
      this.clock[i] = this.rand() * 2;
      this.breath[i] = 0.4 + this.rand() * 0.6;
      this.lean[i] = (this.rand() * 2 - 1) * 0.7;
    }
    this.it = 0;
    this.tags = 0;
    this.cells = new Map();
  }

  move(i) { return this.state[i] === RUN && this.sprinting[i] ? "sprint" : MOVE_OF[this.state[i]]; }

  step(dt) {
    const { x, z, heading, state, left, breath, safe, clock, count, half, speeds } = this;
    const rand = this.rand, it = this.it;
    // who is near whom: a grid of 2 m squares
    const cells = this.cells;
    cells.clear();
    for (let i = 0; i < count; i++) {
      const key = (Math.floor(x[i] / 2) + 64) * 256 + Math.floor(z[i] / 2) + 64;
      const list = cells.get(key);
      if (list) list.push(i); else cells.set(key, [i]);
    }
    // "it" goes for the nearest runner he may tag
    let prey = -1, nearest = 1e9;
    if (state[it] === RUN || state[it] === WANDER) {
      for (let i = 0; i < count; i++) {
        if (i === it || safe[i] > 0 || state[i] === TAGGED) continue;
        const d = Math.hypot(x[i] - x[it], z[i] - z[it]) + (state[i] === BREATH ? -1.5 : 0); // a winded man is easy
        if (d < nearest) { nearest = d; prey = i; }
      }
    }
    for (let i = 0; i < count; i++) {
      if (safe[i] > 0) safe[i] -= dt;
      let want = heading[i], speed = 0, turn = 6;
      this.sprinting[i] = 0;
      if (state[i] === BREATH || state[i] === TAGGING || state[i] === TAGGED || state[i] === LAUGH) {
        left[i] -= dt;
        if (state[i] === BREATH) breath[i] = Math.min(1, breath[i] + dt * 0.3);
        if (left[i] <= 0) {
          if (state[i] === TAGGING) { state[i] = LAUGH; left[i] = this.lengths.laugh; } else state[i] = RUN; // the tagger has his laugh, then is off
          clock[i] = 0;
        }
      } else if (i === it) {
        if (this.wait[i] > 0) { this.wait[i] -= dt; } else if (prey >= 0) {
          const dx = x[prey] - x[i], dz = z[prey] - z[i], d = Math.hypot(dx, dz);
          want = Math.atan2(dx, dz);
          state[i] = RUN;
          this.sprinting[i] = 1;
          speed = Math.max(speeds.sprint, speeds.run * 1.12) * 1.08; // a little faster than anyone he is after
          turn = 9;
          if (d < 0.95) { // tag!
            state[i] = TAGGING; left[i] = this.lengths.tag; clock[i] = 0;
            state[prey] = TAGGED; left[prey] = this.lengths.tagged; clock[prey] = 0;
            heading[prey] = Math.atan2(-dx, -dz);
            safe[i] = 5;
            this.it = prey;
            this.wait[prey] = this.lengths.tagged + 1.0; // he counts before he comes after anyone
            this.tags += 1;
            speed = 0;
          }
        }
      } else {
        const dx = x[i] - x[it], dz = z[i] - z[it], d = Math.hypot(dx, dz);
        if (state[i] === DODGE) {
          left[i] -= dt;
          want = Math.atan2(dx, dz) + this.side[i] * 1.35;
          speed = speeds.run * 1.15;
          turn = 14;
          if (left[i] <= 0) { state[i] = RUN; clock[i] = 0; }
        } else if (d < this.scare) {
          if (state[i] !== RUN) clock[i] = 0;
          state[i] = RUN;
          want = Math.atan2(dx, dz) + this.lean[i]; // each breaks away a little to his own side, so they scatter
          speed = speeds.run * (d < 4 ? 1.12 : 1); // flat out when he is close
          breath[i] -= dt * (d < 4 ? 0.16 : 0.09);
          if (d < 2.3 && rand() < dt * 3) { state[i] = DODGE; left[i] = Math.min(0.7, this.lengths.dodge); clock[i] = 0; this.side[i] = rand() < 0.5 ? -1 : 1; }
          if (breath[i] <= 0) { state[i] = BREATH; left[i] = Math.max(2.5 + rand() * 2, this.lengths.breath); clock[i] = 0; speed = 0; }
        } else {
          if (state[i] !== WANDER) clock[i] = 0;
          state[i] = WANDER;
          if (rand() < dt * 0.5) this.side[i] = rand() < 0.5 ? -1 : 1;
          want = heading[i] + this.side[i] * 0.4;
          speed = speeds.walk;
          breath[i] = Math.min(1, breath[i] + dt * 0.06);
        }
      }
      if (speed > 0) {
        // stay on the field, and keep an arm's length from the others
        let px = Math.sin(want), pz = Math.cos(want);
        const edge = half - 1.5;
        if (Math.abs(x[i]) > edge) px -= Math.sign(x[i]) * (Math.abs(x[i]) - edge);
        if (Math.abs(z[i]) > edge) pz -= Math.sign(z[i]) * (Math.abs(z[i]) - edge);
        const cx = Math.floor(x[i] / 2) + 64, cz = Math.floor(z[i] / 2) + 64;
        for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) {
          const list = cells.get((cx + a) * 256 + cz + b);
          if (!list) continue;
          for (const j of list) {
            if (j === i || (i === it && j === prey)) continue;
            const ox = x[i] - x[j], oz = z[i] - z[j], d = Math.hypot(ox, oz);
            if (d < 1.5 && d > 1e-4) { px += (ox / d) * (1.5 - d) * 2.5; pz += (oz / d) * (1.5 - d) * 2.5; }
          }
        }
        want = Math.atan2(px, pz);
        const off = Math.atan2(Math.sin(want - heading[i]), Math.cos(want - heading[i]));
        heading[i] += Math.max(-turn * dt, Math.min(turn * dt, off));
        x[i] = Math.max(-half, Math.min(half, x[i] + Math.sin(heading[i]) * speed * dt));
        z[i] = Math.max(-half, Math.min(half, z[i] + Math.cos(heading[i]) * speed * dt));
      }
      // the move's own clock: feet that go over the ground keep step with it
      const pace = speeds[this.move(i)];
      clock[i] += dt * (pace > 0 && speed > 0 ? speed / pace : 1);
    }
  }
}

// ---------- the moves, sampled once ----------

// Every move's poses in one table: a row a frame; in a row, for every bone, where the bone is (4 numbers by 4)
// and the same times the bone's bind (what a mesh's points are moved by). All measured from the runner's feet.
async function sampleMoves(loader, runFolder, base, low) {
  const names = base.bones.map((b) => b.name);
  const hips = names.indexOf("hips");
  const fetched = new Map();
  const fetch_ = (glb) => {
    const url = glb.startsWith("profiles/") ? `${runFolder}/${glb}` : glb;
    if (!fetched.has(url)) fetched.set(url, loader.loadAsync(url).catch(() => null));
    return fetched.get(url);
  };
  // which entry of the table a move really plays: its own, the one it is like, or the one to fall back on
  const settle = async (name) => {
    let card = MOVES[name], frame = card.frame, speed = card.speed;
    for (let tries = 0; tries < 6; tries++) {
      if (card.like) { card = MOVES[card.like]; continue; }
      const gltf = await fetch_(card.glb);
      if (gltf) return { card, gltf, frame, speed: speed ?? card.speed };
      if (!card.or) break;
      card = MOVES[card.or];
      frame ??= card.frame;
      speed = card.speed ?? speed;
    }
    throw new Error(`no clip for the move "${name}"`);
  };
  const rows = [];
  const ranges = {};
  const done = new Map(); // a clip sampled once, however many moves stand on it
  for (const name of Object.keys(MOVES)) {
    const { card, gltf, frame, speed } = await settle(name);
    const key = `${card.glb}|${card.from ?? ""}|${card.to ?? ""}|${card.loop}`;
    if (!done.has(key)) {
      const clip = gltf.animations[0];
      const mixer = new THREE.AnimationMixer(gltf.scene);
      mixer.clipAction(clip).play();
      const bones = names.map((n) => gltf.scene.getObjectByName(n));
      const first = card.from ?? 0, last = card.to ?? Math.round(clip.duration * FPS);
      let frames = [];
      for (let f = first; f <= last; f++) {
        mixer.setTime(f / FPS);
        gltf.scene.updateMatrixWorld(true);
        frames.push(bones.map((b) => b.matrixWorld.clone()));
      }
      mixer.stopAllAction();
      const spot = (frame_) => new THREE.Vector3().setFromMatrixPosition(frame_[hips]);
      let found = null, measured = null;
      if (card.loop === "find") {
        found = cleanLoop(frames, hips);
        frames = frames.slice(found.start, found.start + found.length + 1);
      }
      if (card.shot) {
        // to the middle, facing ahead: by the way he travels if he does, else by the way his hips face
        const a = spot(frames[0]), b = spot(frames[frames.length - 1]);
        const gone = Math.hypot(b.x - a.x, b.z - a.z);
        const ahead = new THREE.Vector3(0, 0, 1).transformDirection(new THREE.Matrix4().multiplyMatrices(frames[0][hips], base.boneInverses[hips]));
        const facing = gone > 1.0 ? Math.atan2(b.x - a.x, b.z - a.z) : Math.atan2(ahead.x, ahead.z);
        measured = gone / ((frames.length - 1) / FPS);
        const home = new THREE.Matrix4().makeRotationY(-facing).multiply(new THREE.Matrix4().makeTranslation(-a.x, 0, -a.z));
        frames.forEach((frame_, f) => {
          const t = frames.length > 1 ? f / (frames.length - 1) : 0; // and the travel taken out, evenly from first frame to last
          const back = new THREE.Matrix4().makeTranslation(0, 0, -gone * t * (gone > 1.0 ? 1 : 0));
          frame_.forEach((m) => m.premultiply(home).premultiply(back));
        });
        if (gone <= 1.0) { // a move that stays put may still drift a little: that is taken out too
          const end = spot(frames[frames.length - 1]);
          frames.forEach((frame_, f) => {
            const t = frames.length > 1 ? f / (frames.length - 1) : 0;
            const back = new THREE.Matrix4().makeTranslation(-end.x * t, 0, -end.z * t);
            frame_.forEach((m) => m.premultiply(back));
          });
        }
      }
      const use = card.loop ? frames.slice(0, -1) : frames; // a loop's last frame is its first again
      done.set(key, { start: rows.length, frames: use.length, loop: Boolean(card.loop), found, measured });
      rows.push(...use);
    }
    const got = done.get(key);
    ranges[name] = frame !== undefined ? { ...got, start: got.start + Math.min(frame, got.frames - 1), frames: 1, loop: false } : { ...got };
    ranges[name].speed = speed ?? (got.loop && got.measured ? got.measured : 0);
    ranges[name].from = card.glb;
  }
  const wide = names.length * COLUMNS;
  const data = new Float32Array(rows.length * wide * 4);
  const skin = new THREE.Matrix4();
  const lowBone = low ? low.bones.map((b) => names.indexOf(b.name)) : []; // the low-poly mesh numbers its bones its own way
  rows.forEach((frame, r) => frame.forEach((m, b) => {
    data.set(m.elements, (r * wide + b * COLUMNS) * 4);
    data.set(skin.multiplyMatrices(m, base.boneInverses[b]).elements, (r * wide + b * COLUMNS + 4) * 4);
    if (lowBone[b] >= 0) data.set(skin.multiplyMatrices(frame[lowBone[b]], low.boneInverses[b]).elements, (r * wide + b * COLUMNS + 8) * 4);
  }));
  return { data, wide, tall: rows.length, ranges, names, rows };
}

// One move as a clip a skeleton can play by itself: every bone's place and turn in its parent, a key a frame,
// worked back out of the table. So a runner who works his own skeleton out plays exactly the table's poses.
function clipOf(name, range, table, base) {
  const parents = base.bones.map((b) => base.bones.indexOf(b.parent));
  const count = Math.max(2, range.frames + (range.loop ? 1 : 0));
  const times = Float32Array.from({ length: count }, (_, f) => f / FPS);
  const tracks = [];
  const local = new THREE.Matrix4(), at = new THREE.Vector3(), turn = new THREE.Quaternion(), size = new THREE.Vector3();
  base.bones.forEach((bone, b) => {
    const places = new Float32Array(count * 3), turns = new Float32Array(count * 4);
    for (let f = 0; f < count; f++) {
      const row = table.rows[range.start + (f % range.frames)];
      if (parents[b] >= 0) local.copy(row[parents[b]]).invert().multiply(row[b]); else local.copy(row[b]);
      local.decompose(at, turn, size);
      at.toArray(places, f * 3);
      turn.toArray(turns, f * 4);
    }
    tracks.push(new THREE.VectorKeyframeTrack(`${bone.name}.position`, times, places), new THREE.QuaternionKeyframeTrack(`${bone.name}.quaternion`, times, turns));
  });
  return new THREE.AnimationClip(name, (count - 1) / FPS, tracks);
}

// The cleanest loop inside some frames: the start and length where the pose and its motion match best a loop later.
function cleanLoop(frames, hipsAt) {
  const spots = frames.map((frame) => {
    const hips = frame[hipsAt].elements;
    return frame.flatMap((m) => [m.elements[12] - hips[12], m.elements[13], m.elements[14] - hips[14]]);
  });
  const apart = (a, b) => { let s = 0; for (let i = 0; i < a.length; i++) s += Math.abs(a[i] - b[i]); return s; };
  let best = { start: 0, length: frames.length - 1, cost: Infinity };
  for (let length = 16; length < frames.length - 1; length++) {
    for (let start = 0; start + length + 1 < frames.length; start++) {
      const here = spots[start], there = spots[start + length];
      const going = spots[start + 1].map((v, i) => v - here[i]), coming = spots[start + length + 1].map((v, i) => v - there[i]);
      const cost = apart(here, there) + 3 * apart(going, coming);
      if (cost < best.cost) best = { start, length, cost };
    }
  }
  return best;
}

// ---------- shaders for drawing every runner at once ----------

// What a runner is, to the graphics card: where his feet are (x, z), which way he faces, and his row of the table.
const RUNNER = `
precision highp sampler2D;
uniform sampler2D poseTex;
uniform vec2 keep;      // only runners this near to this far from the eye are drawn (metres)
attribute vec4 runner;
bool putAway() {
  float gone = distance(cameraPosition, vec3(runner.x, 1.0, runner.y));
  return gone < keep.x || gone >= keep.y;
}
mat4 fromTable(int column, float row) {
  int y = int(row + 0.5);
  return mat4(texelFetch(poseTex, ivec2(column, y), 0), texelFetch(poseTex, ivec2(column + 1, y), 0),
              texelFetch(poseTex, ivec2(column + 2, y), 0), texelFetch(poseTex, ivec2(column + 3, y), 0));
}
mat4 feet() {
  float c = cos(runner.z), s = sin(runner.z);
  return mat4(c, 0.0, -s, 0.0, 0.0, 1.0, 0.0, 0.0, s, 0.0, c, 0.0, runner.x, 0.0, runner.y, 1.0);
}`;

// Every card of every runner. What impostor-math.js works out for one card (which picture, how it is turned,
// how its pixels lean) is worked out here, for each card, by the graphics card.
const CARDS_VERTEX = `${RUNNER}
uniform sampler2D cellTex;
uniform vec3 dirs[114];
uniform int viewCount;
uniform int partCount;
uniform int partBone[20];
uniform vec3 centers[20];
uniform float depths[20];
uniform float fine[20];
uniform float marchPx;
uniform float marchMax;
uniform float farAway;
uniform float ids;
uniform float headPass;   // a head on a finer grid (looks.js: Screen): 0 draws the small picture, 1 only the heads that go on the finer one
uniform vec2 fineSize;    // the finer picture's size in its own pixels; 0 when the look has no finer grid
uniform float fineFrom;   // a head goes there once a metre at it is this many big pixels
uniform float fineTimes;
uniform int headPart;
uniform vec4 ballBone[20];   // each part's joints, for the filling of a bent joint: the bones whose heads they are (under 0: none)
uniform vec4 ballSize[20];   // ... and the radius each is filled within
uniform vec4 ballZone[20];   // ... and whether it has a zone (a piece of the model is drawn there for a runner near enough)
uniform float zoneFar;       // how near that is (m); 0: no pieces are being drawn
flat out vec4 balls[4];
flat out int partOf;
flat out float keepDark;
flat out float who;
flat out vec4 cell;
flat out vec2 anchor;
flat out vec2 heights;
flat out vec4 back;
flat out vec2 lean;
flat out vec3 deep;
flat out float size;
flat out float depthM;
flat out float pxPerM;
flat out int steps;
flat out mat3 facingToEye;
varying vec2 vSheet;
varying vec3 vView;
void main() {
  if (putAway()) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  int part = gl_InstanceID % partCount;
  if (headPass > 0.5 && part != headPart) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  // this card's number, for a look that draws its line on the finished picture (looks.js: cardNumber)
  who = ids > 0.5 ? (1.0 + float((gl_InstanceID / partCount) % 15) * 16.0 + float(part % 16)) / 255.0 : 1.0;
  pxPerM = fine[part];
  mat4 bone = feet() * fromTable(partBone[part] * 12, runner.w);
  mat3 turn = mat3(bone);
  vec3 head = bone[3].xyz;
  // a head near enough goes on the finer grid: left out of the small picture, drawn in the heads' own drawing
  vec4 headClip = projectionMatrix * viewMatrix * vec4(head, 1.0);
  bool finer = part == headPart && fineSize.y > 0.0 && headClip.w > 0.0 && fineSize.y / fineTimes * 0.5 * projectionMatrix[1][1] / headClip.w >= fineFrom;
  if ((headPass > 0.5) != finer) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  keepDark = finer ? 1.0 : 0.0;
  vec3 middle = head + turn * centers[part];
  vec3 toward = normalize(cameraPosition - middle);
  vec3 v = toward * turn;
  int best = 0;
  float nearest = -2.0;
  for (int i = 0; i < 114; i++) {
    if (i >= viewCount) break;
    float d = dot(dirs[i], v);
    if (d > nearest) { nearest = d; best = i; }
  }
  vec3 d = dirs[best];
  vec3 u = abs(d.y) > 0.999 ? vec3(0.0, 0.0, 1.0) : normalize(vec3(0.0, 1.0, 0.0) - d.y * d);
  vec3 r = cross(u, d);
  vec3 axis = turn[1];
  vec3 lying = axis - dot(axis, toward) * toward;
  if (length(lying) < 1e-4) { axis = turn[0]; lying = axis - dot(axis, toward) * toward; }
  vec3 e1 = normalize(lying), e2 = cross(e1, toward);
  vec3 a1 = e1 * turn, a2 = e2 * turn;
  vec4 m = vec4(dot(r, a2), dot(u, a2), dot(r, a1), dot(u, a1));
  back = vec4(m.w, -m.y, -m.z, m.x) / (m.x * m.w - m.y * m.z);
  lean = vec2(dot(d, a2), dot(d, a1));
  deep = vec3(dot(r, v), dot(u, v), dot(d, v));
  // this part's joints as the eye has them now
  partOf = part;
  for (int k = 0; k < 4; k++) {
    float joint = ballBone[part][k];
    balls[k] = vec4(0.0);
    if (joint < 0.0) continue;
    vec4 at = feet() * texelFetch(poseTex, ivec2(int(joint + 0.5) * 12 + 3, int(runner.w + 0.5)), 0);
    // the radius in whole millimetres, and after the point how far back this part stands the ball: nothing when
    // its own body is straight behind the ball as the eye sees it (impostor-math.js: ballBack)
    balls[k] = vec4((viewMatrix * at).xyz, floor(ballSize[part][k] * 1000.0) + 0.25 * (1.0 - dot(normalize(middle - at.xyz), normalize(at.xyz - cameraPosition))));
    if (ballZone[part][k] > 0.5 && distance(cameraPosition, vec3(runner.x, 1.0, runner.y)) < zoneFar) balls[k].w = -balls[k].w; // his pieces are drawn: the zone is on (impostor-math.js: jointNumber)
  }
  cell = texelFetch(cellTex, ivec2(best * 2, part), 0);
  vec4 more = texelFetch(cellTex, ivec2(best * 2 + 1, part), 0);
  anchor = more.xy;
  heights = more.zw;
  bool search = farAway < 0.0 ? false : (farAway == 0.0 || distance(cameraPosition, middle) < farAway);
  float reach = length(vec2(back.x * lean.x + back.y * lean.y, back.z * lean.x + back.w * lean.y)) * (heights.y - heights.x) * pxPerM;
  steps = search ? int(min(marchMax, max(1.0, ceil(reach / marchPx)))) : 0;
  vec2 lo = vec2(1e9), hi = vec2(-1e9);
  for (int k = 0; k < 4; k++) {
    vec2 q = (vec2(k == 1 || k == 2 ? cell.z : 0.0, k >= 2 ? cell.w : 0.0) - anchor) / pxPerM;
    vec2 p = vec2(m.x * q.x + m.y * q.y, m.z * q.x + m.w * q.y);
    lo = min(lo, p);
    hi = max(hi, p);
  }
  vec2 l = search ? lean : vec2(0.0);
  lo += min(l * heights.x, l * heights.y);
  hi += max(l * heights.x, l * heights.y);
  vSheet = mix(lo, hi, position.xy);
  vView = (viewMatrix * vec4(head + vSheet.x * e2 + vSheet.y * e1, 1.0)).xyz;
  facingToEye = mat3(viewMatrix) * turn;
  size = 1.0;
  depthM = depths[part];
  gl_Position = projectionMatrix * vec4(vView, 1.0);
  if (finer) { // slid so the bone's head lands on a corner of a fine pixel: his face then moves a whole pixel at a time
    vec2 at = (headClip.xy / headClip.w * 0.5 + 0.5) * fineSize;
    gl_Position.xy += (floor(at + 0.5) - at) * 2.0 / fineSize * gl_Position.w;
  }
}`;
// The cards page's own pixel shader, told that what was one card's settings now comes with each card.
const CARDS_FRAGMENT = ["vec4 cell", "vec2 anchor", "vec2 heights", "vec4 back", "vec2 lean", "vec3 deep", "float size", "float depthM", "float pxPerM", "int steps", "mat3 facingToEye", "float who", "float keepDark", "vec4 balls[4]"]
  .reduce((text, what) => text.replace(`uniform ${what};`, `flat in ${what};`), CARD_FRAGMENT)
  // every part's balls come in one list: each ball's colour, and the radius of the ball itself
  .replace("uniform vec4 ballTint[4];\n#define TINT(k) ballTint[k]", "uniform vec4 ballTints[80];\nflat in int partOf;\n#define TINT(k) ballTints[partOf * 4 + k]")
  .replace("uniform vec2 zone[4];\n#define ZONE(k) zone[k]", "uniform vec2 zones[80];\n#define ZONE(k) zones[partOf * 4 + k]");

// Every near runner's joint pieces in one draw a joint: each point moved by its bones' rows of the table, as the
// meshes are, and painted as the cards page paints a piece (impostor.js: JOINT_FRAGMENT).
const JOINTS_VERTEX = `${RUNNER}
uniform float inkM;
uniform int jointBone;      // the bone whose head is the joint
uniform float partNumber;   // which of a runner's cards the piece says it is
uniform float ids;
attribute float figure;     // which runner this is (only the near ones are handed over)
attribute vec4 skinIndex;
attribute vec4 skinWeight;
varying vec2 vAtlas;
varying vec3 vView;
varying vec3 vTurnX;
varying vec3 vTurnY;
varying vec3 vTurnZ;
flat out vec3 jointAt;
flat out float who;
void main() {
  if (putAway()) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  vAtlas = vec2(uv.x, 1.0 - uv.y);
  mat4 moved = skinWeight.x * fromTable(int(skinIndex.x) * 12 + 4, runner.w) + skinWeight.y * fromTable(int(skinIndex.y) * 12 + 4, runner.w)
             + skinWeight.z * fromTable(int(skinIndex.z) * 12 + 4, runner.w) + skinWeight.w * fromTable(int(skinIndex.w) * 12 + 4, runner.w);
  mat4 whole = feet() * moved;
  mat3 turn = mat3(viewMatrix) * mat3(whole);
  vTurnX = turn[0];
  vTurnY = turn[1];
  vTurnZ = turn[2];
  vec4 seen = viewMatrix * whole * vec4(position + normalize(normal) * inkM, 1.0);
  vView = seen.xyz;
  jointAt = (viewMatrix * feet() * texelFetch(poseTex, ivec2(jointBone * 12 + 3, int(runner.w + 0.5)), 0)).xyz;
  who = ids > 0.5 ? (1.0 + float(int(figure + 0.5) % 15) * 16.0 + partNumber) / 255.0 : 1.0;
  gl_Position = projectionMatrix * seen;
}`;
const JOINTS_FRAGMENT = JOINT_FRAGMENT.replace("uniform vec3 jointAt;", "flat in vec3 jointAt;").replace("uniform float who;", "flat in float who;");

// Every runner's meshes in one draw a piece: each point is moved by its bones' rows of the table.
const MESHES_VERTEX = `${RUNNER}
uniform float inkM;
uniform int bindAt;     // which of a bone's binds this mesh uses: column 4 (painted) or 8 (low-poly)
attribute vec4 skinIndex;
attribute vec4 skinWeight;
attribute vec4 color;
varying vec2 vUv;
varying vec3 vFacing;
varying vec3 vColor;
void main() {
  if (putAway()) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  vUv = uv;
  vColor = color.rgb;
  mat4 moved = skinWeight.x * fromTable(int(skinIndex.x) * 12 + bindAt, runner.w) + skinWeight.y * fromTable(int(skinIndex.y) * 12 + bindAt, runner.w)
             + skinWeight.z * fromTable(int(skinIndex.z) * 12 + bindAt, runner.w) + skinWeight.w * fromTable(int(skinIndex.w) * 12 + bindAt, runner.w);
  mat4 whole = feet() * moved;
  vFacing = normalize(mat3(viewMatrix) * mat3(whole) * normal);
  gl_Position = projectionMatrix * viewMatrix * whole * vec4(position + normalize(normal) * inkM, 1.0);
}`;
// The low-poly mesh has no picture wrapped on it, only a colour at each point: the same tones and rim, on that.
const LOW_FRAGMENT = `
uniform vec3 light;
uniform vec3 shadeMid;
uniform vec3 shadeDark;
uniform vec2 edges;
uniform float punch;
uniform float rim;
varying vec3 vFacing;
varying vec3 vColor;
void main() {
  vec3 toEye = normalize(vFacing) * (gl_FrontFacing ? 1.0 : -1.0);
  float facing = dot(toEye, light);
  vec3 tone = facing > edges.x ? vec3(1.0) : facing > edges.y ? shadeMid : shadeDark;
  vec3 paint = mix(vec3(dot(vColor, vec3(0.2126, 0.7152, 0.0722))), vColor, punch) * 1.5;
  gl_FragColor = vec4(paint * tone + rim * pow(1.0 - clamp(toEye.z, 0.0, 1.0), 3.0) * step(edges.x, facing), 1.0);
  #include <colorspace_fragment>
}`;
const EACH_VERTEX = `
#include <common>
#include <skinning_pars_vertex>
uniform float inkM;
varying vec2 vUv;
varying vec3 vFacing;
void main() {
  vUv = uv;
  #include <beginnormal_vertex>
  #include <skinbase_vertex>
  #include <skinnormal_vertex>
  #include <defaultnormal_vertex>
  vFacing = normalize(transformedNormal);
  #include <begin_vertex>
  transformed += normalize(normal) * inkM;
  #include <skinning_vertex>
  #include <project_vertex>
}`;

// ---------- the field ----------

class Field {
  constructor(pane, { run, baked, set, loader, onReady }) {
    Object.assign(this, { run, baked, set, loader });
    this.folder = `runs/${encodeURIComponent(run.id)}`;
    this.el = pane;
    this.status = pane.querySelector(".status");
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(SKY);
    this.renderer.info.autoReset = false; // a frame may be several passes: count them all
    pane.prepend(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.scene.environment = new THREE.PMREMGenerator(this.renderer).fromScene(new RoomEnvironment(), 0.04).texture;
    this.camera = new THREE.PerspectiveCamera(36, 1, 0.3, 400);
    this.scene.add(this.camera);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.maxPolarAngle = Math.PI * 0.49;
    this.controls.minDistance = 2;
    this.controls.maxDistance = 140;
    this.state = { count: 50, way: "card-batch", shared: true, views: null, paused: false, seed: 7, look: "comic", model: modelsOf(run)[0].id };
    this.look = lookOf("comic");
    this.screen = new Screen(this.renderer);
    this.times = { frame: [], anim: [], place: [], draw: [], work: [] };
    this.layers = {};
    this.last = performance.now();
    this.owed = 0;
    this.resize = new ResizeObserver(() => this.layout());
    this.resize.observe(pane);
    this.layout();
    this.ready = this.fill().then(onReady).catch((err) => { this.status.textContent = "Couldn't set the field out."; this.error = String(err?.stack || err); console.error(err); });
    this.frame = requestAnimationFrame(() => this.tick());
  }

  async fill() {
    const { set } = this;
    if (set?.glb) {
      const model = (await this.loader.loadAsync(`sets/${set.id}/${set.glb}`)).scene;
      this.scene.add(model);
    }
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(140, 140), new THREE.MeshBasicMaterial({ color: 0x8fae6b }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.03;
    this.scene.add(ground, new THREE.HemisphereLight(0xffffff, 0x8a8f7a, 2.2));
    // the runner himself: the meshes, bones and binds of the first move's file
    const gltf = await this.loader.loadAsync(`${this.folder}/${BODY}`);
    this.source = gltf.scene;
    const keep = [];
    this.source.traverse((o) => { if (o.isSkinnedMesh && !o.userData.under) keep.push(o); });
    this.pieces = keep;
    this.base = keep[0].skeleton;
    const lowFile = await this.loader.loadAsync(`${this.folder}/${LOW}`).catch(() => null);
    this.lowPieces = [];
    lowFile?.scene.traverse((o) => { if (o.isSkinnedMesh && !o.userData.under) this.lowPieces.push(o); });
    this.low = this.lowPieces[0]?.skeleton || null;
    this.lowBone = this.low ? this.low.bones.map((b) => this.base.bones.findIndex((x) => x.name === b.name)) : [];
    this.table = await sampleMoves(this.loader, this.folder, this.base, this.low);
    this.poseTex = new THREE.DataTexture(this.table.data, this.table.wide, this.table.tall, THREE.RGBAFormat, THREE.FloatType);
    this.poseTex.needsUpdate = true;
    this.speeds = Object.fromEntries(Object.entries(this.table.ranges).map(([k, v]) => [k, v.speed]));
    this.lengths = Object.fromEntries(Object.entries(this.table.ranges).map(([k, v]) => [k, v.frames / FPS]));
    this.pose = { value: this.poseTex };
    this.keepAll = { value: new THREE.Vector2(0, 1e9) };
    this.marker = new THREE.Group();
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.55, 0.78, 28), new THREE.MeshBasicMaterial({ color: 0xd9502b, side: THREE.DoubleSide }));
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.02;
    const arrow = new THREE.Mesh(new THREE.ConeGeometry(0.22, 0.45, 10), new THREE.MeshBasicMaterial({ color: 0xd9502b }));
    arrow.rotation.x = Math.PI;
    arrow.position.y = 2.45;
    this.marker.add(ring, arrow);
    this.scene.add(this.marker);
    await this.useLook(this.state.look);
    this.restart();
    this.status.remove();
  }

  // Change the look: the paint's numbers, and (when the look has a sheet of its own) which baked cards are read.
  async useLook(id) {
    const look = lookOf(id);
    const folder = `${this.folder}/${bakedFor(this.run, look, this.state.model).folder}`;
    if (folder !== this.cardFolder) {
      const card = await fetch(`${folder}/impostor.json`).then((r) => r.json());
      this.cardFolder = folder;
      this.card = card;
      this.skin?.dispose();
      this.skin = await skinFor(folder, card, this.loader); // a piece of the model for each big joint, when the cards have them
      this.sheets = {};
      this.shade ||= paintOf(card.light);
      await this.useViews(card.default_views);
    }
    this.look = look;
    this.state.look = look.id;
    setPaint(this.shade, look);
  }

  async useViews(name) {
    this.sheets ||= {};
    if (!this.sheets[name]) {
      const sheet = this.card.sets[name];
      const folder = this.cardFolder;
      const [colour, data] = await Promise.all([picture(`${folder}/${sheet.color}`, true, this.card.nearest), picture(`${folder}/${sheet.data}`, false)]);
      const parts = this.card.parts;
      const cells = new Float32Array(parts.length * sheet.views.length * 8);
      parts.forEach((part, p) => sheet.cells[part.name].forEach((cell, v) => cells.set(cell, (p * sheet.views.length + v) * 8)));
      const cellTex = new THREE.DataTexture(cells, sheet.views.length * 2, parts.length, THREE.RGBAFormat, THREE.FloatType);
      cellTex.needsUpdate = true;
      this.sheets[name] = { ...sheet, colour, data, cellTex, dirs: sheet.views.map((v) => v.d) };
    }
    this.state.views = name;
    this.sheet = this.sheets[name];
    this.drop();
  }

  // A new game of the same seed, and the camera set to see all of it.
  restart() {
    this.game = new Game(this.state.count, this.state.seed, this.speeds, this.lengths);
    this.drop();
    const h = this.game.half;
    this.camera.position.set(h * 0.5, h * 0.75 + 4, h * 1.55 + 6);
    this.controls.target.set(0, 0.8, 0);
    this.controls.update();
    this.owed = 0;
  }

  // Throw away whatever was built to draw the last field.
  drop() {
    for (const layer of Object.values(this.layers)) {
      this.scene.remove(layer.group);
      layer.dispose?.();
    }
    this.layers = {};
    if (this.own) { this.own = null; }
  }

  row(i) {
    const range = this.table.ranges[this.game.move(i)];
    const f = Math.floor(this.game.clock[i] * FPS);
    return range.start + (range.loop ? f % range.frames : Math.min(f, range.frames - 1));
  }

  // ---- every runner working his own skeleton out (the plain way), for whoever needs it ----
  ownRunners() {
    if (this.own) return this.own;
    const clips = Object.fromEntries(Object.entries(this.table.ranges).map(([name, range]) => [name, clipOf(name, range, this.table, this.base)]));
    this.own = Array.from({ length: this.game.count }, () => {
      const body = cloneSkinned(this.source);
      const meshes = [];
      body.traverse((o) => { if (o.isSkinnedMesh && !o.userData.under) meshes.push(o); else if (o.isMesh) o.visible = false; });
      const skeleton = meshes[0].skeleton;
      for (const mesh of meshes) { mesh.bind(skeleton, mesh.bindMatrix); mesh.frustumCulled = false; }
      const mixer = new THREE.AnimationMixer(body);
      const actions = Object.fromEntries(Object.entries(clips).map(([k, clip]) => [k, mixer.clipAction(clip)]));
      const holder = new THREE.Group();
      holder.add(body);
      return { holder, body, meshes, skeleton, mixer, actions, playing: null };
    });
    return this.own;
  }

  // Stand every skeleton as the game has it. Shared: the bones are copied out of the table. Own: each mixer works.
  animate() {
    const { game, table, state } = this;
    const need = state.way === "mesh-each" || !this.sharing();
    if (!need) return;
    const own = this.ownRunners();
    const m = new THREE.Matrix4(), root = new THREE.Matrix4();
    for (let i = 0; i < game.count; i++) {
      const runner = own[i];
      if (this.sharing()) {
        if (state.way !== "mesh-each") continue;
        root.makeRotationY(game.heading[i]).setPosition(game.x[i], 0, game.z[i]);
        const at = this.row(i) * table.wide * 4;
        const bones = runner.skeleton.bones;
        for (let b = 0; b < bones.length; b++) {
          bones[b].matrixWorldAutoUpdate = false;
          bones[b].matrixWorld.multiplyMatrices(root, m.fromArray(table.data, at + b * COLUMNS * 4));
        }
      } else {
        const name = game.move(i);
        const range = table.ranges[name];
        if (runner.playing !== name) {
          runner.actions[runner.playing]?.stop();
          runner.actions[name].play();
          runner.playing = name;
          for (const bone of runner.skeleton.bones) bone.matrixWorldAutoUpdate = true;
        }
        const length = range.frames / FPS;
        const action = runner.actions[name];
        // the same frame the table would give (not a blend of two), so both kinds of skeleton draw the same picture
        action.time = Math.floor((range.loop ? game.clock[i] % length : Math.min(game.clock[i], length - 1 / FPS)) * FPS + 1e-4) / FPS;
        runner.mixer.update(0);
        runner.holder.position.set(game.x[i], 0, game.z[i]);
        runner.holder.rotation.y = game.heading[i];
        runner.holder.updateMatrixWorld(true);
      }
    }
  }

  // The bones of every runner, for the ways that read them from a picture. Shared: the table itself, and each
  // runner is a row of it. Own: a picture written afresh each frame, a row a runner.
  // "meshes near, cards far" sorts runners by how far their feet are, which only shared poses carry
  sharing() { return this.state.shared || this.state.way === "mix"; }

  boneSource() {
    if (this.sharing()) return { tex: this.poseTex, runner: (i, out, at) => { out[at] = this.game.x[i]; out[at + 1] = this.game.z[i]; out[at + 2] = this.game.heading[i]; out[at + 3] = this.row(i); } };
    const own = this.ownRunners(), wide = this.table.wide;
    if (!this.liveTex || this.liveTex.image.height !== own.length) {
      this.liveTex?.dispose();
      this.liveTex = new THREE.DataTexture(new Float32Array(own.length * wide * 4), wide, own.length, THREE.RGBAFormat, THREE.FloatType);
    }
    const data = this.liveTex.image.data, skin = new THREE.Matrix4(), inverses = this.base.boneInverses;
    for (let i = 0; i < own.length; i++) {
      const bones = own[i].skeleton.bones;
      for (let b = 0; b < bones.length; b++) {
        data.set(bones[b].matrixWorld.elements, (i * wide + b * COLUMNS) * 4);
        data.set(skin.multiplyMatrices(bones[b].matrixWorld, inverses[b]).elements, (i * wide + b * COLUMNS + 4) * 4);
        if (this.lowBone[b] >= 0) data.set(skin.multiplyMatrices(bones[this.lowBone[b]].matrixWorld, this.low.boneInverses[b]).elements, (i * wide + b * COLUMNS + 8) * 4);
      }
    }
    this.liveTex.needsUpdate = true;
    return { tex: this.liveTex, runner: (i, out, at) => { out[at] = 0; out[at + 1] = 0; out[at + 2] = 0; out[at + 3] = i; } };
  }

  toonMaterial(mesh, vertex, ink, keep = this.keepAll, bindAt = 4) {
    const more = { poseTex: this.pose, keep, bindAt: { value: bindAt } };
    if (ink) return new THREE.ShaderMaterial({ vertexShader: vertex, fragmentShader: INK_FRAGMENT, side: THREE.BackSide, uniforms: { ...more, inkM: { value: 0.014 }, ink: { value: new THREE.Color(0x1c1721) } } });
    if (bindAt === 8) return new THREE.ShaderMaterial({ vertexShader: vertex, fragmentShader: LOW_FRAGMENT, side: THREE.DoubleSide, uniforms: { ...this.shade, ...more, inkM: { value: 0 } } });
    const map = mesh.material.map || mesh.userData.map;
    mesh.userData.map = map;
    return new THREE.ShaderMaterial({ vertexShader: vertex, fragmentShader: TOON_FRAGMENT, side: THREE.DoubleSide,
      uniforms: { ...this.shade, ...more, inkM: { value: 0 }, map: { value: map }, soften: { value: map ? Math.max(0, Math.log2(map.image.width / (/head/i.test(mesh.material.name) ? 512 : 256))) : 0 } } });
  }

  // ---- the five ways ----
  layer(way) {
    if (this.layers[way]) return this.layers[way];
    const { game, card, sheet } = this;
    const group = new THREE.Group();
    const layer = { group };
    const n = game.count;
    if (way === "mesh-each") {
      const own = this.ownRunners();
      const paints = this.pieces.map((piece) => this.toonMaterial(piece, EACH_VERTEX, false));
      const ink = this.toonMaterial(null, EACH_VERTEX, true);
      for (const runner of own) {
        if (!runner.dressed) {
          runner.dressed = true;
          runner.lines = [];
          runner.meshes.slice().forEach((mesh, k) => {
            mesh.material = paints[k];
            const line = new THREE.SkinnedMesh(mesh.geometry, ink);
            runner.lines.push(line);
            line.bind(runner.skeleton, mesh.bindMatrix);
            line.frustumCulled = false;
            mesh.parent.add(line);
          });
        }
        group.add(runner.holder);
      }
      layer.hull = (on) => { for (const runner of own) for (const line of runner.lines) line.visible = on; };
      layer.dispose = () => { for (const runner of own) group.remove(runner.holder); };
    } else if (way === "mesh-batch" || way === "mesh-low") {
      const made = this.meshesAtOnce(group, way === "mesh-low" ? this.lowPieces : this.pieces, way === "mesh-low" ? 8 : 4, this.keepAll);
      layer.place = made.place;
      layer.hull = made.hull;
      layer.dispose = made.dispose;
    } else if (way === "card-each") {
      const quads = [];
      for (let i = 0; i < n; i++) for (const part of card.parts) {
        const shape = new THREE.BufferGeometry();
        shape.setAttribute("position", new THREE.BufferAttribute(new Float32Array(12), 3));
        shape.setAttribute("uv", new THREE.BufferAttribute(new Float32Array(8), 2));
        shape.setIndex([0, 1, 2, 0, 2, 3]);
        const quad = new THREE.Mesh(shape, new THREE.ShaderMaterial({ vertexShader: CARD_VERTEX, fragmentShader: CARD_FRAGMENT, side: THREE.DoubleSide, uniforms: {
          colourMap: { value: sheet.colour }, dataMap: { value: sheet.data }, facingToEye: { value: new THREE.Matrix3() }, sheetSize: { value: new THREE.Vector2(...sheet.size) },
          pxPerM: { value: density(card, part) }, cell: { value: new THREE.Vector4() }, anchor: { value: new THREE.Vector2() }, heights: { value: new THREE.Vector2() },
          back: { value: new THREE.Vector4() }, lean: { value: new THREE.Vector2() }, deep: { value: new THREE.Vector3() }, size: { value: 1 }, wallM: { value: card.march.wall_m },
          steps: { value: 0 }, depthM: { value: part.depth_m }, share: { value: 1 }, mix_: { value: 0 }, ...lineUniforms(), ...this.shade } }));
        quad.frustumCulled = false;
        quad.matrixAutoUpdate = false;
        group.add(quad);
        quads.push(quad);
      }
      const bones = card.parts.map((part) => this.table.names.indexOf(part.bone));
      const joints = sheetBalls(card, sheet);
      const world = new THREE.Matrix4(), root = new THREE.Matrix4(), m = new THREE.Matrix4(), toEye = new THREE.Matrix4();
      // where a bone's head is now, for the runner being placed: his own skeleton's, or the shared table's row
      let mine = null, rowAt = 0;
      const spot = new THREE.Vector3();
      const jointAt = (name) => {
        const b = this.table.names.indexOf(name);
        if (b < 0) return null;
        if (mine) spot.setFromMatrixPosition(mine.skeleton.bones[b].matrixWorld);
        else spot.fromArray(this.table.data, rowAt + b * COLUMNS * 4 + 12).applyMatrix4(root);
        return [spot.x, spot.y, spot.z];
      };
      layer.place = () => {
        const eye = this.camera.position.toArray();
        const own = this.sharing() ? null : this.ownRunners();
        const told = cardLine(card, this.look); // what this look does with the sheet's ink line
        for (let i = 0; i < n; i++) {
          const at = this.row(i) * this.table.wide * 4;
          if (!own) root.makeRotationY(game.heading[i]).setPosition(game.x[i], 0, game.z[i]);
          mine = own ? own[i] : null;
          rowAt = at;
          card.parts.forEach((part, p) => {
            if (own) world.copy(own[i].skeleton.bones[bones[p]].matrixWorld); else world.multiplyMatrices(root, m.fromArray(this.table.data, at + bones[p] * COLUMNS * 4));
            const quad = quads[i * card.parts.length + p];
            const view = choose(sheet.dirs, eyeInBone(world.elements, part.center, eye), null, 0, card.blend_deg).first;
            const cell = sheet.cells[part.name][view];
            const where = place(sheet.views[view], world.elements, part.center, eye);
            const spots = corners(where, cell, density(card, part), true);
            const pos = quad.geometry.attributes.position, uv = quad.geometry.attributes.uv;
            spots.world.forEach((s, k) => pos.setXYZ(k, s[0], s[1], s[2]));
            spots.sheet.forEach((s, k) => uv.setXY(k, s[0], s[1]));
            pos.needsUpdate = uv.needsUpdate = true;
            const u = quad.material.uniforms;
            u.cell.value.set(cell[0], cell[1], cell[2], cell[3]);
            u.anchor.value.set(cell[4], cell[5]);
            u.heights.value.set(cell[6], cell[7]);
            u.back.value.set(...where.back);
            u.lean.value.set(...where.lean);
            u.deep.value.set(...where.deep);
            u.steps.value = marchSteps(where, cell, density(card, part), card.march);
            u.line.value = told.line;
            u.who.value = told.ids ? cardNumber(i, p) : 1;
            setBalls(quad, joints[p], part.center, world.elements, this.camera, jointAt);
            u.facingToEye.value.setFromMatrix4(toEye.multiplyMatrices(this.camera.matrixWorldInverse, world));
          });
        }
      };
      layer.dispose = () => quads.forEach((quad) => { quad.geometry.dispose(); quad.material.dispose(); });
    } else {
      const far = { value: way === "mix" ? new THREE.Vector2(NEAR_M, 1e9) : this.keepAll.value };
      const cards = this.cardsAtOnce(group, way === "card-far" ? FAR_M : 0, far);
      const near = way === "mix" ? this.meshesAtOnce(group, this.pieces, 4, { value: new THREE.Vector2(0, NEAR_M) }) : null;
      layer.place = () => { cards.place(); near?.place(); };
      layer.hull = near?.hull;
      layer.dispose = () => { cards.dispose(); near?.dispose(); };
    }
    this.layers[way] = layer;
    return layer;
  }

  // Every runner's meshes in one draw a piece (and one more a piece for its ink shell).
  meshesAtOnce(group, pieces, bindAt, keep) {
    const n = this.game.count;
    const spots = new THREE.InstancedBufferAttribute(new Float32Array(n * 4), 4);
    spots.setUsage(THREE.DynamicDrawUsage);
    const made = [];
    for (const piece of pieces) {
      const shape = new THREE.InstancedBufferGeometry();
      for (const name of ["position", "normal", "uv", "color", "skinIndex", "skinWeight"]) if (piece.geometry.attributes[name]) shape.setAttribute(name, piece.geometry.attributes[name]);
      shape.setIndex(piece.geometry.index);
      shape.setAttribute("runner", spots);
      shape.instanceCount = n;
      for (const inked of [false, true]) {
        const mesh = new THREE.Mesh(shape, this.toonMaterial(piece, MESHES_VERTEX, inked, keep, bindAt));
        mesh.frustumCulled = false;
        group.add(mesh);
        made.push(mesh);
      }
    }
    return {
      place: () => {
        const from = this.boneSource();
        for (const mesh of made) mesh.material.uniforms.poseTex.value = from.tex;
        for (let i = 0; i < n; i++) from.runner(i, spots.array, i * 4);
        spots.needsUpdate = true;
      },
      hull: (on) => made.forEach((mesh, k) => { if (k % 2) mesh.visible = on; }),
      dispose: () => made.forEach((mesh) => mesh.material.dispose()),
    };
  }

  // Every card of every runner in one draw.
  cardsAtOnce(group, farAway, keep) {
    const { card, sheet } = this;
    const n = this.game.count, parts = card.parts;
    const shape = new THREE.InstancedBufferGeometry();
    shape.setAttribute("position", new THREE.BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0]), 3));
    shape.setIndex([0, 1, 2, 0, 2, 3]);
    const spots = new THREE.InstancedBufferAttribute(new Float32Array(n * parts.length * 4), 4);
    spots.setUsage(THREE.DynamicDrawUsage);
    shape.setAttribute("runner", spots);
    shape.instanceCount = n * parts.length;
    const pad = (list, fill) => [...list, ...Array.from({ length: 20 - list.length }, () => fill())];
    const ballBone = new Float32Array(80).fill(-1), ballSize = new Float32Array(80), ballTints = new Float32Array(320), ballZone = new Float32Array(80), zones = new Float32Array(160);
    const joined = this.jointsAtOnce(group, keep);
    // each ball's colour is looked up with the joints where the first pose of the table has them
    const first = (bone) => this.table.data.subarray(bone * COLUMNS * 4, bone * COLUMNS * 4 + 16);
    sheetBalls(card, sheet).forEach((joints, p) => joints.forEach((joint, k) => {
      const bone = this.table.names.indexOf(joint.bone), mine = this.table.names.indexOf(parts[p].bone);
      if (p >= 20 || k >= FILL.aPart || bone < 0 || mine < 0) return;
      const tint = joint.tintAt(inBone(first(mine), [first(bone)[12], first(bone)[13], first(bone)[14]]));
      ballBone[p * 4 + k] = bone;
      ballSize[p * 4 + k] = joint.radius;
      ballTints.set([tint[0], tint[1], tint[2], joint.inner], (p * 4 + k) * 4);
      ballZone[p * 4 + k] = joined && joint.zone > 0 ? 1 : 0;
      zones.set([joint.zone, joint.core], (p * 4 + k) * 2);
    }));
    const paint = new THREE.ShaderMaterial({ vertexShader: CARDS_VERTEX, fragmentShader: CARDS_FRAGMENT, side: THREE.DoubleSide, uniforms: {
      ...this.shade, poseTex: this.pose, keep, cellTex: { value: sheet.cellTex }, colourMap: { value: sheet.colour }, dataMap: { value: sheet.data },
      dirs: { value: [...sheet.dirs.map((d) => new THREE.Vector3(...d)), ...Array.from({ length: 114 - sheet.dirs.length }, () => new THREE.Vector3())] },
      viewCount: { value: sheet.dirs.length }, partCount: { value: parts.length },
      partBone: { value: pad(parts.map((part) => this.table.names.indexOf(part.bone)), () => 0) },
      centers: { value: pad(parts.map((part) => new THREE.Vector3(...part.center)), () => new THREE.Vector3()) },
      depths: { value: pad(parts.map((part) => part.depth_m), () => 0) },
      fine: { value: pad(parts.map((part) => density(card, part)), () => 0) }, ballBone: { value: ballBone }, ballSize: { value: ballSize }, ballTints: { value: ballTints },
      ballZone: { value: ballZone }, zones: { value: zones }, zoneFar: { value: joined ? JOINTS_M : 0 },
      sheetSize: { value: new THREE.Vector2(...sheet.size) }, marchPx: { value: card.march.px }, marchMax: { value: card.march.max },
      wallM: { value: card.march.wall_m }, farAway: { value: farAway }, share: { value: 1 }, mix_: { value: 0 }, ...lineUniforms(), ids: { value: 0 },
      headPass: this.screen.told.headPass, fineSize: { value: new THREE.Vector2() }, fineFrom: { value: FINE_FROM }, fineTimes: { value: 1 }, headPart: { value: parts.findIndex((part) => part.name === "head") } } });
    const mesh = new THREE.Mesh(shape, paint);
    mesh.layers.enable(1); // its heads may go on the finer grid
    mesh.frustumCulled = false;
    group.add(mesh);
    return {
      place: () => {
        const from = this.boneSource();
        const told = cardLine(card, this.look); // what this look does with the sheet's ink line
        paint.uniforms.line.value = told.line;
        paint.uniforms.ids.value = told.ids ? 1 : 0;
        const times = this.look.screen?.heads || 0, [wide, tall] = this.screen.small(this.look);
        paint.uniforms.fineSize.value.set(wide * times, tall * times);
        paint.uniforms.fineTimes.value = times || 1;
        paint.uniforms.poseTex.value = from.tex;
        for (let i = 0; i < n; i++) for (let p = 0; p < parts.length; p++) from.runner(i, spots.array, (i * parts.length + p) * 4);
        spots.needsUpdate = true;
        joined?.place(from, told);
      },
      dispose: () => { shape.dispose(); paint.dispose(); joined?.dispose(); },
    };
  }

  // The pieces of the model in the big joints of every runner near the eye, a draw a joint (and one more for its
  // ink shell, in a look that keeps the line behind the surface). Null when the cards have no pieces, or the
  // table lacks a bone they need. `keep` is which runners the cards themselves are drawn for. Only the near
  // runners are handed to the graphics card at all (with shared poses, where the page knows where each one is):
  // a piece is some hundreds of triangles, and a thousand runners' worth is what the cards were there to save.
  jointsAtOnce(group, keep) {
    const { skin, card } = this;
    const names = this.table.names;
    if (!skin || skin.pieces.some((piece) => piece.bones.some((name) => names.indexOf(name) < 0))) return null;
    const n = this.game.count;
    const spots = new THREE.InstancedBufferAttribute(new Float32Array(n * 4), 4), figures = new THREE.InstancedBufferAttribute(new Float32Array(n), 1);
    spots.setUsage(THREE.DynamicDrawUsage);
    figures.setUsage(THREE.DynamicDrawUsage);
    const near = { value: new THREE.Vector2(keep.value.x, Math.min(keep.value.y, JOINTS_M)) };
    const made = [], shapes = [], one = new Float32Array(4);
    for (const piece of skin.pieces) {
      const shape = new THREE.InstancedBufferGeometry();
      for (const name of ["position", "normal", "uv", "skinWeight"]) shape.setAttribute(name, piece.geometry.attributes[name]);
      // the piece counts its bones its own way: here they are the table's rows
      const was = piece.geometry.attributes.skinIndex, bones = new Float32Array(was.count * 4);
      for (let i = 0; i < was.count * 4; i++) bones[i] = names.indexOf(piece.bones[was.array[i]]);
      shape.setAttribute("skinIndex", new THREE.BufferAttribute(bones, 4));
      shape.setIndex(piece.geometry.index);
      shape.setAttribute("runner", spots);
      shape.setAttribute("figure", figures);
      shape.instanceCount = n;
      shapes.push(shape);
      for (const shell of [false, true]) {
        const mesh = new THREE.Mesh(shape, new THREE.ShaderMaterial({ vertexShader: JOINTS_VERTEX, fragmentShader: JOINTS_FRAGMENT, side: shell ? THREE.BackSide : THREE.FrontSide, uniforms: {
          ...this.shade, poseTex: this.pose, keep: near, atlas: { value: skin.colour }, atlasData: { value: skin.data }, reach: { value: piece.joint.reach_cm / 100 }, inkM: { value: shell ? skin.inkM : 0 },
          lineInk: { value: new THREE.Color(0x1c1721) }, jointBone: { value: names.indexOf(piece.joint.bone) }, partNumber: { value: piece.part % 16 }, ids: { value: 0 } } }));
        mesh.frustumCulled = false;
        group.add(mesh);
        made.push(mesh);
      }
    }
    return {
      place: (from, told) => {
        made.forEach((mesh, k) => {
          mesh.material.uniforms.poseTex.value = from.tex;
          mesh.material.uniforms.ids.value = told.ids ? 1 : 0;
          if (k % 2) mesh.visible = told.line > 0 && skin.inkM > 0;
        });
        const eye = this.camera.position, sorted = this.sharing();
        let count = 0;
        for (let i = 0; i < n; i++) {
          from.runner(i, one, 0);
          const gone = Math.hypot(eye.x - one[0], eye.y - 1, eye.z - one[1]); // as the shaders measure it (RUNNER: putAway)
          if (sorted && (gone < near.value.x || gone >= near.value.y)) continue;
          spots.array.set(one, count * 4);
          figures.array[count++] = i;
        }
        for (const shape of shapes) shape.instanceCount = count;
        spots.needsUpdate = figures.needsUpdate = true;
        this.jointsDrawn = { runners: count, triangles: count * skin.pieces.reduce((sum, piece) => sum + piece.geometry.index.count / 3, 0) };
      },
      dispose: () => made.forEach((mesh, k) => { mesh.material.dispose(); if (k % 2 === 0) mesh.geometry.dispose(); }),
    };
  }

  // One frame: the game, the skeletons, the placing, the drawing; each timed.
  tick() {
    this.frame = requestAnimationFrame(() => this.tick());
    if (!this.game) return;
    const now = performance.now();
    const took = now - this.last;
    this.last = now;
    const { state, game } = this;
    if (!state.paused) {
      if (this.measuring) game.step(STEP); // a timed run plays the same frames whatever the frame rate
      else {
        this.owed = Math.min(this.owed + took / 1000, 5 * STEP);
        while (this.owed >= STEP) { game.step(STEP); this.owed -= STEP; }
      }
    }
    const t0 = performance.now();
    this.animate();
    const t1 = performance.now();
    const layer = this.layer(state.way);
    for (const [way, other] of Object.entries(this.layers)) {
      if (way !== state.way) { this.scene.remove(other.group); other.dispose?.(); delete this.layers[way]; }
    }
    if (!layer.group.parent) this.scene.add(layer.group);
    this.controls.update();
    this.camera.updateMatrixWorld();
    layer.place?.();
    const it = game.it;
    this.marker.position.set(game.x[it], 0, game.z[it]);
    layer.hull?.(this.look.hull !== false); // bold ink draws its lines on the finished picture, for cards and meshes alike
    const t2 = performance.now();
    this.screen.render(this.scene, this.camera, /^(card|mix)/.test(state.way) ? this.look : withoutHeads(this.look));
    const t3 = performance.now();
    let t4 = t3;
    if (this.measuring) { // wait for the graphics card to finish, so its share is in the time
      const gl = this.renderer.getContext();
      gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, this.pixel ||= new Uint8Array(4));
      t4 = performance.now();
    }
    const keep = this.times;
    keep.frame.push(took); keep.anim.push(t1 - t0); keep.place.push(t2 - t1); keep.draw.push(t3 - t2); keep.work.push(t4 - t0);
    for (const list of Object.values(keep)) if (list.length > 900) list.shift();
    this.info = { calls: this.renderer.info.render.calls, triangles: this.renderer.info.render.triangles };
    this.renderer.info.reset();
  }

  // What is being held in memory for pictures, in MB: the two sheets, the pose table, the meshes' own pictures.
  memory() {
    const sheet = (this.sheet.size[0] * this.sheet.size[1] * 8) / 1e6;
    const poses = (this.table.data.byteLength + (this.liveTex && !this.state.shared ? this.liveTex.image.data.byteLength : 0)) / 1e6;
    const maps = new Set(this.pieces.map((p) => p.userData.map || p.material.map).filter(Boolean));
    let mesh = 0;
    for (const map of maps) mesh += (map.image.width * map.image.height * 4 * 4) / 3 / 1e6;
    return { sheet, poses, mesh };
  }

  reading() {
    const mean = (list) => (list.length ? list.reduce((a, b) => a + b, 0) / list.length : 0);
    const slow = (list) => { const s = [...list].sort((a, b) => b - a); return mean(s.slice(0, Math.max(1, Math.ceil(s.length * 0.05)))); };
    const t = this.times;
    const size = this.renderer.getDrawingBufferSize(new THREE.Vector2());
    return {
      ready: Boolean(this.game && this.table), count: this.game?.count, way: this.state.way, look: this.state.look, model: this.state.model, shared: this.state.shared, views: this.state.views,
      frame_ms: mean(t.frame), slow_ms: slow(t.frame), fps: 1000 / Math.max(mean(t.frame), 1e-6), anim_ms: mean(t.anim), place_ms: mean(t.place), draw_ms: mean(t.draw), work_ms: mean(t.work),
      work_slow_ms: slow(t.work), calls: this.info?.calls, triangles: this.info?.triangles, memory: this.table && this.sheet ? this.memory() : null, pixels: [size.x, size.y], tags: this.game?.tags, it: this.game?.it,
      error: this.error || null,
    };
  }

  // Time one count drawn one way for a while: the same game from its first frame each time.
  async measure(count, way, shared, seconds = 3, warm = 0.8, look = this.state.look, model = this.state.model) {
    Object.assign(this.state, { count, way, shared, model });
    await this.useLook(look);
    this.drop();
    this.measuring = true;
    this.restart();
    const wait = (ms) => new Promise((done) => setTimeout(done, ms));
    await wait(warm * 1000);
    for (const list of Object.values(this.times)) list.length = 0;
    await wait(seconds * 1000);
    const got = this.reading();
    this.measuring = false;
    return got;
  }

  // The picture is as big as its place on the page, unless a test has fixed it (so a phone and a Mac, or a phone
  // held upright and on its side, draw exactly the same number of pixels).
  layout() {
    const [wide, tall] = this.fixed || [this.el.clientWidth, this.el.clientHeight];
    this.renderer.setPixelRatio(this.fixed ? 1 : Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(wide, tall, false);
    this.camera.aspect = wide / Math.max(1, tall);
    this.camera.updateProjectionMatrix();
  }

  // Time one setting once, for the phone test: the work in a frame, and the real gaps between frames.
  async timeOnce(setting, warm, seconds) {
    Object.assign(this.state, { count: setting.count, way: setting.way, shared: true, model: setting.model || this.state.model, paused: false });
    await this.useLook(setting.look);
    this.measuring = true;
    this.restart();
    const wait = (ms) => new Promise((done) => setTimeout(done, ms));
    await wait(warm * 1000);
    for (const list of Object.values(this.times)) list.length = 0;
    await wait(seconds * 1000);
    const t = this.times;
    const sorted = (list) => [...list].sort((a, b) => a - b);
    const middle = (list) => { const x = sorted(list); return x.length ? x[Math.floor(x.length / 2)] : 0; };
    const mean = (list) => (list.length ? list.reduce((a, b) => a + b, 0) / list.length : 0);
    const slow = (list) => { const x = sorted(list); return mean(x.slice(Math.floor(x.length * 0.95))); };
    this.measuring = false;
    return { work: middle(t.work), work_mean: mean(t.work), work_slow: slow(t.work), frame: middle(t.frame), frame_mean: mean(t.frame), frame_slow: slow(t.frame),
      anim: mean(t.anim), place: mean(t.place), frames: t.frame.length, calls: this.info?.calls, triangles: this.info?.triangles };
  }

  dispose() {
    cancelAnimationFrame(this.frame);
    this.resize.disconnect();
    this.controls.dispose();
    this.drop();
    this.screen.dispose();
    this.renderer.dispose();
    delete window.forgeTag;
  }
}

// ---------- the page ----------

export function tagPage({ run, sets, h, loader }) {
  const baked = run.cards[0];
  const pane = h("div", { class: "pane tag-pane" }, h("div", { class: "status" }, "Setting the field out…"));
  const stage = h("div", { class: "stage clay-surface" }, pane);
  const facts = h("div", { class: "facts tag-facts" });
  const table = h("div", { class: "tag-table" });
  const fact = (k, v, small) => h("div", { class: "fact clay-surface" }, h("div", { class: "k" }, k), h("div", { class: "v" }, v, small ? h("small", {}, ` ${small}`) : null));
  let field = null;
  const chip = (label, pressed, onclick) => h("button", { class: "chip clay-chip", type: "button", "aria-pressed": String(pressed), onclick }, label);
  const group = (label, chips) => h("div", { class: "versions", role: "group", "aria-label": label }, h("span", { class: "row-label" }, label), chips);
  const press = (chips, i) => chips.forEach((c, k) => c.setAttribute("aria-pressed", String(k === i)));
  const countChips = COUNTS.map((n, i) => chip(String(n), n === 50, () => { press(countChips, i); field.state.count = n; field.restart(); }));
  const wayChips = WAYS.map((way, i) => chip(way.name, way.id === "card-batch", () => { press(wayChips, i); field.state.way = way.id; }));
  const shareChips = [chip("Sampled once, shared", true, () => { press(shareChips, 0); field.state.shared = true; field.drop(); }),
    chip("Each works his own out", false, () => { press(shareChips, 1); field.state.shared = false; field.drop(); })];
  const lookChips = LOOKS.map((look, i) => chip(look.name, i === 0, () => { press(lookChips, i); field.useLook(look.id).then(() => field.drop()); }));
  const models = modelsOf(run);
  const modelChips = models.map((model, i) => chip(model.name, i === 0, () => { press(modelChips, i); field.state.model = model.id; field.useLook(field.state.look).then(() => field.drop()); }));
  const pause = h("button", { class: "toggle clay-button clay-button--soft", type: "button", "aria-pressed": "false", onclick: () => {
    field.state.paused = !field.state.paused;
    pause.setAttribute("aria-pressed", String(field.state.paused));
  } }, "Pause");
  const again = h("button", { class: "toggle clay-button clay-button--soft", type: "button", onclick: () => field.restart() }, "Start again");

  const show = () => {
    if (!field?.game || !field.table || !field.sheet) return;
    const r = field.reading();
    facts.replaceChildren(
      fact("Frames a second", r.fps.toFixed(0), `${r.frame_ms.toFixed(1)} ms a frame, ${r.slow_ms.toFixed(1)} in the slow 5%`),
      fact("Moving the skeletons", `${r.anim_ms.toFixed(2)} ms`, "each frame"),
      fact("Placing", `${r.place_ms.toFixed(2)} ms`, "cards or runners"),
      fact("Drawing", `${r.draw_ms.toFixed(2)} ms`, `${(r.calls || 0).toLocaleString()} draws, ${(r.triangles || 0).toLocaleString()} triangles`),
      fact("Pictures in memory", `${(r.way.startsWith("card") ? r.memory.sheet : r.memory.mesh).toFixed(1)} MB`, `and ${r.memory.poses.toFixed(1)} MB of poses`),
      fact("Tags so far", String(r.tags), `on a picture ${r.pixels[0]} by ${r.pixels[1]}`),
    );
  };
  const timer = setInterval(show, 500);

  // "Measure all": every count, every way, a few seconds each; a table to read and to copy.
  const results = [];
  let last = [COUNTS, WAYS.map((w) => w.id), [true], ["comic"]];
  const runAll = async (options = {}) => {
    const counts = options.counts || COUNTS, ways = options.ways || WAYS.map((w) => w.id), seconds = options.seconds || 3;
    const shared = options.shared ?? [true], looks = options.looks || [field.state.look], model = options.model || field.state.model;
    results.length = 0;
    last = [counts, ways, shared, looks];
    measure.disabled = looksButton.disabled = true;
    for (const look of looks) for (const share of shared) for (const way of ways) for (const count of counts) {
      const most = WAYS.find((w) => w.id === way).most;
      if (most && count > most && !options.all) { results.push({ way, count, shared: share, look, skipped: true }); continue; }
      measure.textContent = `Measuring ${count}, ${WAYS.find((w) => w.id === way).name.toLowerCase()}…`;
      results.push(await field.measure(count, way, share, seconds, 0.8, look, model));
      draw(counts, ways, shared, looks);
    }
    measure.disabled = looksButton.disabled = false;
    measure.textContent = "Measure all";
    press(lookChips, LOOKS.findIndex((l) => l.id === field.state.look));
    press(countChips, COUNTS.indexOf(field.state.count));
    press(wayChips, WAYS.findIndex((w) => w.id === field.state.way));
    press(shareChips, field.state.shared ? 0 : 1);
    return results;
  };
  const text = (counts, ways, shared, looks) => {
    const lines = [["look", "skeletons", "way", ...counts].join("\t")];
    for (const look of looks) for (const share of shared) for (const way of ways) {
      lines.push([lookOf(look).name, share ? "shared" : "own", WAYS.find((w) => w.id === way).name, ...counts.map((count) => {
        const r = results.find((x) => x.way === way && x.count === count && x.shared === share && x.look === look);
        return !r ? "" : r.skipped ? "-" : `${r.work_ms.toFixed(1)} ms work (${r.anim_ms.toFixed(1)} skeletons, ${r.place_ms.toFixed(1)} placing), ${r.fps.toFixed(0)} fps, slow ${r.slow_ms.toFixed(0)} ms, ${r.calls} draws, ${r.triangles} tris`;
      })].join("\t"));
    }
    return lines.join("\n");
  };
  const draw = (counts, ways, shared, looks) => {
    const blocks = [];
    for (const look of looks) for (const share of shared) {
      blocks.push(h("h3", {}, `${lookOf(look).name}: ${share ? "poses sampled once and shared" : "each runner works his own skeleton out"}`));
      blocks.push(h("div", { class: "tag-scroll" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", {}, "Runners"), counts.map((c) => h("th", {}, String(c))))),
        h("tbody", {}, ways.map((way) => h("tr", {}, h("th", {}, WAYS.find((w) => w.id === way).name), counts.map((count) => {
          const r = results.find((x) => x.way === way && x.count === count && x.shared === share && x.look === look);
          if (!r) return h("td", {}, "");
          if (r.skipped) return h("td", { class: "skipped", title: "Too many draws to be worth the wait" }, "not run");
          return h("td", {}, h("b", {}, `${r.work_ms.toFixed(1)} ms`), h("small", {}, `${r.fps.toFixed(0)} a second`), h("small", {}, `${r.calls.toLocaleString()} draws`));
        })))))));
    }
    const copy = h("button", { class: "toggle clay-button clay-button--soft", type: "button", onclick: () => navigator.clipboard?.writeText(text(counts, ways, shared, looks)).then(() => { copy.textContent = "Copied"; }) }, "Copy the table");
    table.replaceChildren(...blocks, h("p", { class: "about" }, "The big number is the work in one frame: moving the skeletons, placing, drawing, and waiting for the graphics card to finish. Frames a second can't go past what the screen shows, so the work is the fairer number when both are fast."), copy);
  };
  const measure = h("button", { class: "clay-button", type: "button", onclick: () => runAll() }, "Measure all");

  // ---- the phone test: a narrow one, built to give the same answer twice ----
  // Four ways, two looks, four crowds; poses shared; one seed, one fixed eye, one fixed size of picture. Every
  // setting is timed three times, the three spread through the test (so a phone warming up is shared out, not
  // dumped on whatever comes last), and the first setting is timed once more at the very end to see whether the
  // phone slowed as it warmed.
  const TEST = {
    size: [1080, 608], warm: 1.2, seconds: 2.6, repeats: 3, counts: [100, 250, 500, 1000],
    ways: [{ id: "mesh-low", name: "Low-poly meshes", cards: false }, { id: "mesh-batch", name: "Painted meshes", cards: false },
      { id: "card-batch", name: "Cards", cards: true }, { id: "card-far", name: "Cards, search off far away", cards: true }],
    looks: [{ id: "comic", name: "Comic", mesh: "comic", cards: "comic" }, { id: "pixels", name: "Pixel art", mesh: "pixel-screen", cards: "pixel-both" }],
  };
  const answer = h("div", { class: "tag-answer" });
  let testing = null;
  const median = (list) => { const x = [...list].sort((a, b) => a - b); return x[Math.floor(x.length / 2)]; };
  const phoneTest = async (options = {}) => {
    const plan = { ...TEST, ...options };
    const settings = [];
    for (const look of plan.looks) for (const way of plan.ways) for (const count of plan.counts) settings.push({ key: `${look.id}|${way.id}|${count}`, lookId: look.id, look: way.cards ? look.cards : look.mesh, way: way.id, count, model: "painted" });
    // three passes, each starting a third of the way round from the last and every other one backwards
    const order = [];
    const shares = (a, b) => (b ? shares(b, a % b) : a);
    const stride = [5, 7, 11, 13, 3, 1].find((n) => shares(n, settings.length) === 1); // a step that visits every setting before coming round
    for (let r = 0; r < plan.repeats; r++) {
      const turned = settings.map((_, i) => settings[(i * stride + r * 11) % settings.length]); // every setting once, heavy and light mixed
      order.push(...(r % 2 ? turned.reverse() : turned));
    }
    order.push(order[0]); // the first setting once more at the end: has the phone slowed as it warmed?
    const each = plan.warm + plan.seconds + 0.25;
    const runs = [];
    testing = { stop: false };
    const lock = await navigator.wakeLock?.request?.("screen").catch(() => null);
    const was = { ...field.state };
    field.fixed = plan.size;
    pane.classList.add("testing");
    field.controls.enabled = false;
    field.layout();
    for (const b of [measure, looksButton, testButton]) b.disabled = true;
    const began = performance.now();
    for (let k = 0; k < order.length && !testing.stop; k++) {
      const left = Math.round(((order.length - k) * each) / 60 * 10) / 10;
      answer.replaceChildren(h("p", { class: "tag-progress" }, h("b", {}, `Testing: ${k + 1} of ${order.length}`), ` · about ${left < 1 ? "under a minute" : `${left.toFixed(1)} minutes`} left. Leave the page open and the phone alone.`),
        h("button", { class: "toggle clay-button clay-button--soft", type: "button", onclick: () => { testing.stop = true; } }, "Stop the test"));
      const setting = order[k];
      runs.push({ ...setting, at: Math.round((performance.now() - began) / 100) / 10, last: k === order.length - 1, ...(await field.timeOnce(setting, plan.warm, plan.seconds)) });
    }
    lock?.release?.();
    field.fixed = null;
    pane.classList.remove("testing");
    field.controls.enabled = true;
    Object.assign(field.state, { count: was.count, way: was.way, shared: was.shared, model: was.model });
    await field.useLook(was.look);
    field.layout();
    field.restart();
    for (const b of [measure, looksButton, testButton]) b.disabled = false;
    const result = judge(plan, settings, runs, testing.stop, (performance.now() - began) / 1000);
    testing = null;
    showAnswer(result);
    return result;
  };
  // What the runs say: for every setting the middle of its three, the screen's own frame gap, who holds it, and
  // how much faster cards are than the cheapest meshes where meshes give out.
  const judge = (plan, settings, runs, stopped, took) => {
    const main = runs.filter((r) => !r.last);
    const rows = settings.map((setting) => {
      const mine = main.filter((r) => r.key === setting.key);
      if (!mine.length) return { ...setting, runs: 0 };
      return { ...setting, runs: mine.length, work: median(mine.map((r) => r.work)), work_low: Math.min(...mine.map((r) => r.work)), work_high: Math.max(...mine.map((r) => r.work)),
        frame: median(mine.map((r) => r.frame)), frame_low: Math.min(...mine.map((r) => r.frame)), frame_high: Math.max(...mine.map((r) => r.frame)), frame_slow: median(mine.map((r) => r.frame_slow)),
        calls: mine[0].calls, triangles: mine[0].triangles };
    });
    const done = rows.filter((r) => r.runs);
    // the screen's own gap between frames, which nothing can beat: the quickest setting's, taken as the nearest of the usual screens (120, 90 or 60 a second)
    const quickest = done.length ? Math.min(...done.map((r) => r.frame)) : 16.67;
    const gap = [1000 / 60, 1000 / 90, 1000 / 120].find((g) => g <= quickest * 1.04) || quickest;
    const full = Math.round(1000 / gap);
    for (const r of done) r.holds = r.frame <= gap * 1.08 && r.frame_slow <= gap * 2.2; // the middle frame on time, and the slow ones no worse than one missed
    const first = runs[0], again = runs.find((r) => r.last);
    const warmed = first && again ? { first: first.work, last: again.work, slower_pct: Math.round((again.work / first.work - 1) * 100), first_frame: first.frame, last_frame: again.frame } : null;
    const looks = plan.looks.map((look) => {
      const ways = plan.ways.map((way) => {
        const mine = done.filter((r) => r.lookId === look.id && r.way === way.id).sort((a, b) => a.count - b.count);
        let most = 0;
        for (const r of mine) { if (r.holds) most = r.count; else break; }
        return { id: way.id, name: way.name, cards: way.cards, holds_up_to: most, tried_up_to: mine.length ? mine[mine.length - 1].count : 0, rows: mine };
      });
      const low = ways.find((w) => w.id === "mesh-low"), cards = ways.filter((w) => w.cards);
      const dropAt = low?.rows.find((r) => !r.holds)?.count || null;
      const at = dropAt || low?.tried_up_to;
      const meshAt = low?.rows.find((r) => r.count === at);
      const best = cards.map((w) => ({ w, r: w.rows.find((r) => r.count === at) })).filter((x) => x.r).sort((a, b) => a.r.work - b.r.work)[0];
      return { id: look.id, name: look.name, ways, meshes_drop_at: dropAt, compared_at: at, low_poly_ms: meshAt?.work, best_cards: best?.w.name, best_cards_ms: best?.r.work,
        times_faster: meshAt && best ? Math.round((meshAt.work / best.r.work) * 10) / 10 : null };
    });
    return { test: "forge tag phone test/1", when: new Date().toISOString(), device: navigator.userAgent, platform: navigator.platform, cores: navigator.hardwareConcurrency,
      pixel_ratio: window.devicePixelRatio, screen: [screen.width, screen.height], window: [innerWidth, innerHeight], picture: plan.size, warm_s: plan.warm, measure_s: plan.seconds,
      repeats: plan.repeats, took_s: Math.round(took), stopped, frame_gap_ms: Math.round(gap * 100) / 100, full_speed_fps: full, warmed, looks, rows, runs };
  };
  const ms = (v) => (v === undefined ? "" : `${v.toFixed(1)} ms`);
  const showAnswer = (result) => {
    const lines = [];
    for (const look of result.looks) {
      const held = look.ways.map((w) => `${w.name.toLowerCase()} to ${w.holds_up_to ? (w.holds_up_to === w.tried_up_to ? `${w.holds_up_to}, the most tried` : w.holds_up_to) : "none of them"}`).join("; ");
      const versus = look.times_faster ? (look.meshes_drop_at
        ? ` At ${look.compared_at}, where the low-poly meshes give out, ${look.best_cards.toLowerCase()} do a frame's work in ${ms(look.best_cards_ms)} against ${ms(look.low_poly_ms)}: ${look.times_faster} times ${look.times_faster >= 1 ? "faster" : "as fast"}.`
        : ` The low-poly meshes never gave out; at ${look.compared_at}, ${look.best_cards.toLowerCase()} do a frame's work in ${ms(look.best_cards_ms)} against ${ms(look.low_poly_ms)}: ${look.times_faster} times ${look.times_faster >= 1 ? "faster" : "as fast"}.`) : "";
      lines.push(h("p", {}, h("b", {}, `${look.name}. `), `Holds ${result.full_speed_fps} frames a second: ${held}.${versus}`));
    }
    const heat = result.warmed ? (result.warmed.slower_pct > 15
      ? h("p", { class: "tag-warn" }, `The phone slowed down as it warmed: the first setting took ${ms(result.warmed.first)} at the start and ${ms(result.warmed.last)} at the end (${result.warmed.slower_pct}% slower). Let it cool and run the test again before trusting these.`)
      : h("p", { class: "about" }, `It did not slow as it warmed: the first setting took ${ms(result.warmed.first)} at the start and ${ms(result.warmed.last)} at the end.`)) : null;
    const copy = h("button", { class: "clay-button tag-big", type: "button", onclick: () => {
      const text = JSON.stringify(result);
      const done = () => { copy.textContent = "Copied"; };
      (navigator.clipboard?.writeText(text) || Promise.reject()).then(done, () => {
        const box = h("textarea", { class: "tag-json" }, text);
        answer.append(box);
        box.select();
        try { document.execCommand("copy"); done(); } catch { copy.textContent = "Select the text below and copy it"; }
      });
    } }, "Copy results");
    const blocks = result.looks.map((look) => [h("h3", {}, look.name), h("div", { class: "tag-scroll" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Runners"), result.rows.filter((r) => r.lookId === look.id && r.way === look.ways[0].id).map((r) => h("th", {}, String(r.count))))),
      h("tbody", {}, look.ways.map((w) => h("tr", {}, h("th", {}, w.name), w.rows.map((r) => h("td", { class: r.holds ? "holds" : "drops" },
        h("b", {}, ms(r.work)), h("small", {}, `${(1000 / r.frame).toFixed(0)} a second`), h("small", {}, `${r.work_low.toFixed(1)} to ${r.work_high.toFixed(1)}`))))))))]).flat();
    answer.replaceChildren(
      h("h2", {}, result.stopped ? "Phone test (stopped early)" : "Phone test"),
      ...lines, heat,
      h("p", { class: "about" }, `Drawn ${result.picture[0]} by ${result.picture[1]} whatever the screen, poses shared, ${result.repeats} goes at each setting; the big number is the middle one's work in a frame, under it the frames a second really shown and the least and most work of the goes. A setting "holds" when its middle frame is on time and its slow ones miss no more than one. Took ${Math.round(result.took_s / 6) / 10} minutes.`),
      copy, ...blocks);
    answer.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const testButton = h("button", { class: "clay-button tag-big", type: "button", onclick: () => phoneTest() }, "Phone test");
  const looksButton = h("button", { class: "toggle clay-button clay-button--soft", type: "button", title: "Every look, a hundred and a thousand runners, as meshes and as cards drawn all at once",
    onclick: () => runAll({ looks: LOOKS.map((l) => l.id), ways: ["mesh-batch", "mesh-low", "card-batch", "mix"], counts: [100, 1000] }) }, "Measure the looks");

  const page = h("article", { class: "object cards-page tag-page" },
    h("a", { class: "back", href: `#/cards/${encodeURIComponent(run.id)}` }, "← Flat cards"),
    h("h1", {}, "Tag"),
    h("p", { class: "lede" }, `A field of ${run.name.split(" ")[0]}s playing tag: the one with the ring under him is it. Pick how many, and how they are drawn, and watch what it costs. The game is the same game whichever way it is drawn.`),
    group("Runners", countChips),
    group("Drawn as", wayChips),
    group("Skeletons", shareChips),
    group("In the look", lookChips),
    models.length > 1 ? group("Cards pictured from", modelChips) : null,
    h("div", { class: "controls" }, h("div", { class: "toggles" }, pause, again, measure, looksButton)),
    h("div", { class: "controls" }, testButton, h("span", { class: "about" }, "Six and a half minutes: which ways hold full speed at 100 to 1000 runners, and how much faster cards are than the cheapest meshes.")),
    answer,
    stage,
    facts,
    table,
  );
  queueMicrotask(() => {
    field = new Field(pane, { run, baked, set: sets.find((s) => s.id === "grass"), loader, onReady: show });
    window.forgeTag = { state: () => field.reading(), measureAll: runAll, look: (id) => field.useLook(id).then(() => field.drop()), results, text: () => text(...last), field, phoneTest,
      // one moment of the game, held still: for pictures of the same field drawn different ways
      // the eye brought up close to one runner
      near: (i = 0, away = 3.6) => {
        const g = field.game;
        field.controls.target.set(g.x[i], 0.95, g.z[i]);
        field.camera.position.set(g.x[i] + away * 0.45, 1.5, g.z[i] + away * 0.9);
        field.controls.update();
      },
      still: async (count, way, look, steps = 600, model = field.state.model) => {
        Object.assign(field.state, { count, way, model, paused: true });
        await field.useLook(look);
        field.restart();
        for (let k = 0; k < steps; k++) field.game.step(STEP);
      } };
  });
  page.dispose = () => { clearInterval(timer); field?.dispose(); };
  return page;
}
