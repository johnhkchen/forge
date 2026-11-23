// Forge gallery: a field of Roosevelts playing tag, drawn five ways, to time flat cards against meshes. #/tag/<run>
//
// One game, many ways to draw it. The game (who is "it", who runs where, which move each is in and how far
// through it) is worked out from a seed in fixed steps, so every way of drawing sees exactly the same field.
//
//   meshes, one by one      every runner is his own skinned meshes, drawn the comic way with the ink shell
//   meshes, all at once     the same meshes, every runner in one draw per piece: the bones come from a picture
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
import { eyeInBone, choose, place, corners, marchSteps } from "./impostor-math.js";
import { CARD_VERTEX, CARD_FRAGMENT, TOON_FRAGMENT, INK_FRAGMENT, picture } from "./impostor.js";
import { LOOKS, lookOf, bakedFor, paintOf, setPaint, Screen } from "./looks.js";

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
const BODY = "profiles/painted-walk.glb"; // the meshes, bones and binds every move is played on (the file the cards were cut from)
const FPS = 30;
const COUNTS = [10, 50, 100, 250, 500, 1000];
const WAYS = [
  { id: "mesh-each", name: "Meshes, one by one", most: 500 },
  { id: "mesh-batch", name: "Meshes, all at once" },
  { id: "card-each", name: "Cards, one by one", most: 500 },
  { id: "card-batch", name: "Cards, all at once" },
  { id: "card-far", name: "Cards, all at once, search off far away" },
];
const FAR_M = 12;         // "search off far away": past this a card's picture is laid flat
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
async function sampleMoves(loader, runFolder, base) {
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
  const wide = names.length * 8;
  const data = new Float32Array(rows.length * wide * 4);
  const skin = new THREE.Matrix4();
  rows.forEach((frame, r) => frame.forEach((m, b) => {
    data.set(m.elements, (r * wide + b * 8) * 4);
    data.set(skin.multiplyMatrices(m, base.boneInverses[b]).elements, (r * wide + b * 8 + 4) * 4);
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
attribute vec4 runner;
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
uniform float pxPerM;
uniform float marchPx;
uniform float marchMax;
uniform float farAway;
flat out vec4 cell;
flat out vec2 anchor;
flat out vec2 heights;
flat out vec4 back;
flat out vec2 lean;
flat out vec3 deep;
flat out float size;
flat out float depthM;
flat out int steps;
flat out mat3 facingToEye;
varying vec2 vSheet;
varying vec3 vView;
void main() {
  int part = gl_InstanceID % partCount;
  mat4 bone = feet() * fromTable(partBone[part] * 8, runner.w);
  mat3 turn = mat3(bone);
  vec3 head = bone[3].xyz;
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
}`;
// The cards page's own pixel shader, told that what was one card's settings now comes with each card.
const CARDS_FRAGMENT = ["vec4 cell", "vec2 anchor", "vec2 heights", "vec4 back", "vec2 lean", "vec3 deep", "float size", "float depthM", "int steps", "mat3 facingToEye"]
  .reduce((text, what) => text.replace(`uniform ${what};`, `flat in ${what};`), CARD_FRAGMENT);

// Every runner's meshes in one draw a piece: each point is moved by its bones' rows of the table.
const MESHES_VERTEX = `${RUNNER}
uniform float inkM;
attribute vec4 skinIndex;
attribute vec4 skinWeight;
varying vec2 vUv;
varying vec3 vFacing;
void main() {
  vUv = uv;
  mat4 moved = skinWeight.x * fromTable(int(skinIndex.x) * 8 + 4, runner.w) + skinWeight.y * fromTable(int(skinIndex.y) * 8 + 4, runner.w)
             + skinWeight.z * fromTable(int(skinIndex.z) * 8 + 4, runner.w) + skinWeight.w * fromTable(int(skinIndex.w) * 8 + 4, runner.w);
  mat4 whole = feet() * moved;
  vFacing = normalize(mat3(viewMatrix) * mat3(whole) * normal);
  gl_Position = projectionMatrix * viewMatrix * whole * vec4(position + normalize(normal) * inkM, 1.0);
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
    this.state = { count: 50, way: "card-batch", shared: true, views: null, paused: false, seed: 7, look: "comic" };
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
    this.table = await sampleMoves(this.loader, this.folder, this.base);
    this.poseTex = new THREE.DataTexture(this.table.data, this.table.wide, this.table.tall, THREE.RGBAFormat, THREE.FloatType);
    this.poseTex.needsUpdate = true;
    this.speeds = Object.fromEntries(Object.entries(this.table.ranges).map(([k, v]) => [k, v.speed]));
    this.lengths = Object.fromEntries(Object.entries(this.table.ranges).map(([k, v]) => [k, v.frames / FPS]));
    this.pose = { value: this.poseTex };
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
    const folder = `${this.folder}/${bakedFor(this.run, look).folder}`;
    if (folder !== this.cardFolder) {
      const card = await fetch(`${folder}/impostor.json`).then((r) => r.json());
      this.cardFolder = folder;
      this.card = card;
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
    const need = state.way === "mesh-each" || !state.shared;
    if (!need) return;
    const own = this.ownRunners();
    const m = new THREE.Matrix4(), root = new THREE.Matrix4();
    for (let i = 0; i < game.count; i++) {
      const runner = own[i];
      if (state.shared) {
        if (state.way !== "mesh-each") continue;
        root.makeRotationY(game.heading[i]).setPosition(game.x[i], 0, game.z[i]);
        const at = this.row(i) * table.wide * 4;
        const bones = runner.skeleton.bones;
        for (let b = 0; b < bones.length; b++) {
          bones[b].matrixWorldAutoUpdate = false;
          bones[b].matrixWorld.multiplyMatrices(root, m.fromArray(table.data, at + b * 32));
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
  boneSource() {
    if (this.state.shared) return { tex: this.poseTex, runner: (i, out, at) => { out[at] = this.game.x[i]; out[at + 1] = this.game.z[i]; out[at + 2] = this.game.heading[i]; out[at + 3] = this.row(i); } };
    const own = this.ownRunners(), wide = this.table.wide;
    if (!this.liveTex || this.liveTex.image.height !== own.length) {
      this.liveTex?.dispose();
      this.liveTex = new THREE.DataTexture(new Float32Array(own.length * wide * 4), wide, own.length, THREE.RGBAFormat, THREE.FloatType);
    }
    const data = this.liveTex.image.data, skin = new THREE.Matrix4(), inverses = this.base.boneInverses;
    for (let i = 0; i < own.length; i++) {
      const bones = own[i].skeleton.bones;
      for (let b = 0; b < bones.length; b++) {
        data.set(bones[b].matrixWorld.elements, (i * wide + b * 8) * 4);
        data.set(skin.multiplyMatrices(bones[b].matrixWorld, inverses[b]).elements, (i * wide + b * 8 + 4) * 4);
      }
    }
    this.liveTex.needsUpdate = true;
    return { tex: this.liveTex, runner: (i, out, at) => { out[at] = 0; out[at + 1] = 0; out[at + 2] = 0; out[at + 3] = i; } };
  }

  toonMaterial(mesh, vertex, ink) {
    if (ink) return new THREE.ShaderMaterial({ vertexShader: vertex, fragmentShader: INK_FRAGMENT, side: THREE.BackSide, uniforms: { poseTex: this.pose, inkM: { value: this.card.ink_m }, ink: { value: new THREE.Color(0x1c1721) } } });
    const map = mesh.material.map || mesh.userData.map;
    mesh.userData.map = map;
    return new THREE.ShaderMaterial({ vertexShader: vertex, fragmentShader: TOON_FRAGMENT, side: THREE.DoubleSide,
      uniforms: { ...this.shade, poseTex: this.pose, inkM: { value: 0 }, map: { value: map }, soften: { value: map ? Math.max(0, Math.log2(map.image.width / (/head/i.test(mesh.material.name) ? 512 : 256))) : 0 } } });
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
    } else if (way === "mesh-batch") {
      const spots = new THREE.InstancedBufferAttribute(new Float32Array(n * 4), 4);
      spots.setUsage(THREE.DynamicDrawUsage);
      const made = [];
      for (const piece of this.pieces) {
        const shape = new THREE.InstancedBufferGeometry();
        for (const name of ["position", "normal", "uv", "skinIndex", "skinWeight"]) shape.setAttribute(name, piece.geometry.attributes[name]);
        shape.setIndex(piece.geometry.index);
        shape.setAttribute("runner", spots);
        shape.instanceCount = n;
        for (const inked of [false, true]) {
          const mesh = new THREE.Mesh(shape, this.toonMaterial(piece, MESHES_VERTEX, inked));
          mesh.frustumCulled = false;
          group.add(mesh);
          made.push(mesh);
        }
      }
      layer.place = () => {
        const from = this.boneSource();
        this.pose.value = from.tex;
        for (const mesh of made) mesh.material.uniforms.poseTex.value = from.tex;
        for (let i = 0; i < n; i++) from.runner(i, spots.array, i * 4);
        spots.needsUpdate = true;
      };
      layer.hull = (on) => made.forEach((mesh, k) => { if (k % 2) mesh.visible = on; });
      layer.dispose = () => made.forEach((mesh) => mesh.material.dispose());
    } else if (way === "card-each") {
      const quads = [];
      for (let i = 0; i < n; i++) for (const part of card.parts) {
        const shape = new THREE.BufferGeometry();
        shape.setAttribute("position", new THREE.BufferAttribute(new Float32Array(12), 3));
        shape.setAttribute("uv", new THREE.BufferAttribute(new Float32Array(8), 2));
        shape.setIndex([0, 1, 2, 0, 2, 3]);
        const quad = new THREE.Mesh(shape, new THREE.ShaderMaterial({ vertexShader: CARD_VERTEX, fragmentShader: CARD_FRAGMENT, side: THREE.DoubleSide, uniforms: {
          colourMap: { value: sheet.colour }, dataMap: { value: sheet.data }, facingToEye: { value: new THREE.Matrix3() }, sheetSize: { value: new THREE.Vector2(...sheet.size) },
          pxPerM: { value: card.px_per_m }, cell: { value: new THREE.Vector4() }, anchor: { value: new THREE.Vector2() }, heights: { value: new THREE.Vector2() },
          back: { value: new THREE.Vector4() }, lean: { value: new THREE.Vector2() }, deep: { value: new THREE.Vector3() }, size: { value: 1 }, wallM: { value: card.march.wall_m },
          steps: { value: 0 }, depthM: { value: part.depth_m }, share: { value: 1 }, mix_: { value: 0 }, ...this.shade } }));
        quad.frustumCulled = false;
        quad.matrixAutoUpdate = false;
        group.add(quad);
        quads.push(quad);
      }
      const bones = card.parts.map((part) => this.table.names.indexOf(part.bone));
      const world = new THREE.Matrix4(), root = new THREE.Matrix4(), m = new THREE.Matrix4(), toEye = new THREE.Matrix4();
      layer.place = () => {
        const eye = this.camera.position.toArray();
        const own = this.state.shared ? null : this.ownRunners();
        for (let i = 0; i < n; i++) {
          const at = this.row(i) * this.table.wide * 4;
          if (!own) root.makeRotationY(game.heading[i]).setPosition(game.x[i], 0, game.z[i]);
          card.parts.forEach((part, p) => {
            if (own) world.copy(own[i].skeleton.bones[bones[p]].matrixWorld); else world.multiplyMatrices(root, m.fromArray(this.table.data, at + bones[p] * 32));
            const quad = quads[i * card.parts.length + p];
            const view = choose(sheet.dirs, eyeInBone(world.elements, part.center, eye), null, 0, card.blend_deg).first;
            const cell = sheet.cells[part.name][view];
            const where = place(sheet.views[view], world.elements, part.center, eye);
            const spots = corners(where, cell, card.px_per_m, true);
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
            u.steps.value = marchSteps(where, cell, card.px_per_m, card.march);
            u.facingToEye.value.setFromMatrix4(toEye.multiplyMatrices(this.camera.matrixWorldInverse, world));
          });
        }
      };
      layer.dispose = () => quads.forEach((quad) => { quad.geometry.dispose(); quad.material.dispose(); });
    } else {
      const parts = card.parts;
      const shape = new THREE.InstancedBufferGeometry();
      shape.setAttribute("position", new THREE.BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0]), 3));
      shape.setIndex([0, 1, 2, 0, 2, 3]);
      const spots = new THREE.InstancedBufferAttribute(new Float32Array(n * parts.length * 4), 4);
      spots.setUsage(THREE.DynamicDrawUsage);
      shape.setAttribute("runner", spots);
      shape.instanceCount = n * parts.length;
      const pad = (list, fill) => [...list, ...Array.from({ length: 20 - list.length }, () => fill())];
      const paint = new THREE.ShaderMaterial({ vertexShader: CARDS_VERTEX, fragmentShader: CARDS_FRAGMENT, side: THREE.DoubleSide, uniforms: {
        ...this.shade, poseTex: this.pose, cellTex: { value: sheet.cellTex }, colourMap: { value: sheet.colour }, dataMap: { value: sheet.data },
        dirs: { value: [...sheet.dirs.map((d) => new THREE.Vector3(...d)), ...Array.from({ length: 114 - sheet.dirs.length }, () => new THREE.Vector3())] },
        viewCount: { value: sheet.dirs.length }, partCount: { value: parts.length },
        partBone: { value: pad(parts.map((part) => this.table.names.indexOf(part.bone)), () => 0) },
        centers: { value: pad(parts.map((part) => new THREE.Vector3(...part.center)), () => new THREE.Vector3()) },
        depths: { value: pad(parts.map((part) => part.depth_m), () => 0) },
        sheetSize: { value: new THREE.Vector2(...sheet.size) }, pxPerM: { value: card.px_per_m }, marchPx: { value: card.march.px }, marchMax: { value: card.march.max },
        wallM: { value: card.march.wall_m }, farAway: { value: way === "card-far" ? FAR_M : 0 }, share: { value: 1 }, mix_: { value: 0 } } });
      const mesh = new THREE.Mesh(shape, paint);
      mesh.frustumCulled = false;
      group.add(mesh);
      layer.place = () => {
        const from = this.boneSource();
        paint.uniforms.poseTex.value = from.tex;
        for (let i = 0; i < n; i++) for (let p = 0; p < parts.length; p++) from.runner(i, spots.array, (i * parts.length + p) * 4);
        spots.needsUpdate = true;
      };
      layer.dispose = () => { shape.dispose(); paint.dispose(); };
    }
    this.layers[way] = layer;
    return layer;
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
    this.screen.render(this.scene, this.camera, this.look);
    const t3 = performance.now();
    let t4 = t3;
    if (this.measuring) { // wait for the graphics card to finish, so its share is in the time
      const gl = this.renderer.getContext();
      gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, this.pixel ||= new Uint8Array(4));
      t4 = performance.now();
    }
    const keep = this.times;
    keep.frame.push(took); keep.anim.push(t1 - t0); keep.place.push(t2 - t1); keep.draw.push(t3 - t2); keep.work.push(t4 - t0);
    for (const list of Object.values(keep)) if (list.length > 240) list.shift();
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
      ready: Boolean(this.game && this.table), count: this.game?.count, way: this.state.way, look: this.state.look, shared: this.state.shared, views: this.state.views,
      frame_ms: mean(t.frame), slow_ms: slow(t.frame), fps: 1000 / Math.max(mean(t.frame), 1e-6), anim_ms: mean(t.anim), place_ms: mean(t.place), draw_ms: mean(t.draw), work_ms: mean(t.work),
      work_slow_ms: slow(t.work), calls: this.info?.calls, triangles: this.info?.triangles, memory: this.table ? this.memory() : null, pixels: [size.x, size.y], tags: this.game?.tags, it: this.game?.it,
      error: this.error || null,
    };
  }

  // Time one count drawn one way for a while: the same game from its first frame each time.
  async measure(count, way, shared, seconds = 3, warm = 0.8, look = this.state.look) {
    Object.assign(this.state, { count, way, shared });
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

  layout() {
    this.renderer.setSize(this.el.clientWidth, this.el.clientHeight, false);
    this.camera.aspect = this.el.clientWidth / Math.max(1, this.el.clientHeight);
    this.camera.updateProjectionMatrix();
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
  const pause = h("button", { class: "toggle clay-button clay-button--soft", type: "button", "aria-pressed": "false", onclick: () => {
    field.state.paused = !field.state.paused;
    pause.setAttribute("aria-pressed", String(field.state.paused));
  } }, "Pause");
  const again = h("button", { class: "toggle clay-button clay-button--soft", type: "button", onclick: () => field.restart() }, "Start again");

  const show = () => {
    if (!field?.game || !field.table) return;
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
    const shared = options.shared ?? [true], looks = options.looks || [field.state.look];
    results.length = 0;
    last = [counts, ways, shared, looks];
    measure.disabled = looksButton.disabled = true;
    for (const look of looks) for (const share of shared) for (const way of ways) for (const count of counts) {
      const most = WAYS.find((w) => w.id === way).most;
      if (most && count > most && !options.all) { results.push({ way, count, shared: share, look, skipped: true }); continue; }
      measure.textContent = `Measuring ${count}, ${WAYS.find((w) => w.id === way).name.toLowerCase()}…`;
      results.push(await field.measure(count, way, share, seconds, 0.8, look));
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
  const looksButton = h("button", { class: "toggle clay-button clay-button--soft", type: "button", title: "Every look, a hundred and a thousand runners, as meshes and as cards drawn all at once",
    onclick: () => runAll({ looks: LOOKS.map((l) => l.id), ways: ["mesh-batch", "card-batch"], counts: [100, 1000] }) }, "Measure the looks");

  const page = h("article", { class: "object cards-page tag-page" },
    h("a", { class: "back", href: `#/cards/${encodeURIComponent(run.id)}` }, "← Flat cards"),
    h("h1", {}, "Tag"),
    h("p", { class: "lede" }, `A field of ${run.name.split(" ")[0]}s playing tag: the one with the ring under him is it. Pick how many, and how they are drawn, and watch what it costs. The game is the same game whichever way it is drawn.`),
    group("Runners", countChips),
    group("Drawn as", wayChips),
    group("Skeletons", shareChips),
    group("In the look", lookChips),
    h("div", { class: "controls" }, h("div", { class: "toggles" }, pause, again, measure, looksButton)),
    stage,
    facts,
    table,
  );
  queueMicrotask(() => {
    field = new Field(pane, { run, baked, set: sets.find((s) => s.id === "grass"), loader, onReady: show });
    window.forgeTag = { state: () => field.reading(), measureAll: runAll, look: (id) => field.useLook(id).then(() => field.drop()), results, text: () => text(...last), field,
      // one moment of the game, held still: for pictures of the same field drawn different ways
      still: async (count, way, look, steps = 600) => {
        Object.assign(field.state, { count, way, paused: true });
        await field.useLook(look);
        field.restart();
        for (let k = 0; k < steps; k++) field.game.step(STEP);
      } };
  });
  page.dispose = () => { clearInterval(timer); field?.dispose(); };
  return page;
}
