// Forge gallery: walking around the world. A toon you steer, seen from behind and a little above.
//
// Nothing here is fetched until "Walk around" is pressed: this file, its style sheet and the walker's two
// files (profiles/lowpoly-walk.glb and lowpoly-run.glb: the skeleton, the gear, the prop points and the clips
// are all in them). The world view (WorldViewer in app.js) hands over its scene, camera and places, and gets
// them back when walking stops.
//
//   avatars(epoch, runs)        who could be walked as: every toon of the epoch whose run has a walk and a run
//   READY                       who can be picked today. Add a toon's name here to switch them on.
//   startWalk({ viewer, ... })  begins; returns the Walkabout (stop() ends it)
//
// How it moves. The clips run on the spot and each says how fast its feet go over the ground (1.31 m/s for
// Roosevelt's walk, 3.26 for his run). So the body is moved at exactly that speed times the clip's playback
// rate, and a foot that is down stays where it is. Standing still is made here: straight legs from the
// skeleton's own rest, the arms and back as they hang in the middle of the walk, and a slow breath.
import * as THREE from "three";

export const READY = new Set(["roosevelt"]);

// What each toon says when you come close. The ninja never speaks.
const HELLO = { roosevelt: "Bully!", lincoln: "Hello, friend.", pirate: "Ahoy!", ninja: "(a small nod)", dancer: "Pull up a chair.", troll: "Tea?", lizardkin: "The bread's fresh." };

const BODY_R = 0.32;        // the walker, as a circle on the floor (m): at least this, wider for a wide toon
const HEAD_M = 2.0;         // a block that starts above this is over your head, not in your way
const DEAD = 0.14;          // stick: closer to the middle than this is "not pushing"
const RUN_AT = 0.86;        // stick: pushed further than this is a run
const SPEED_UP = 6.0, SLOW_DOWN = 9.0; // m/s per second
const TURN = 11.0;          // how quickly the body turns to face the way it is going (1/s)
const NEAR_TOON = 3.0, NEAR_THING = 2.7, NEAR_PLACE = 6.0; // m
const STEP_UP = 0.3;        // a floor raised by less than this can be stepped onto
const CAMERA = { fov: 46, near: 0.12, distance: 5.4, pitch: 0.34, low: 0.06, high: 1.25, closest: 1.0, furthest: 14 };

const rad = (d) => THREE.MathUtils.degToRad(d || 0);
const clamp = THREE.MathUtils.clamp;
const smooth = (lo, hi, v) => THREE.MathUtils.smoothstep(v, lo, hi);
const turnTo = (from, to) => Math.atan2(Math.sin(to - from), Math.cos(to - from)); // the short way round

// Every toon of this epoch that has a walk and a run in its low-poly version: who the walker could be.
export function avatars(epoch, runs) {
  return epoch.toons.map((toon) => {
    const run = runs.find((r) => r.id.endsWith(`-${toon.run}`));
    const low = run?.profiles.find((p) => p.name === "lowpoly");
    const walkSpeed = low?.gait?.speed_m_s, runSpeed = low?.run_gait?.speed_m_s;
    if (!low?.walk || !low?.run || !walkSpeed || !runSpeed) return null;
    const at = (rel) => `runs/${encodeURIComponent(run.id)}/${rel}`;
    return { toon: toon.toon, name: toon.name, walk: at(low.walk), run: at(low.run), walkSpeed, runSpeed, ready: READY.has(toon.toon) };
  }).filter(Boolean);
}

// ---------- what is solid ----------

// The world's solid things as boxes on the floor, in world metres: every block of every place (the same boxes
// the sets' contact pass uses) and the developer's grey cubes. The ring's own blocks are up on its mat; from
// the hall floor the ring is one block of the boxing house, so a place inside another adds nothing.
function solidBoxes(viewer, epoch) {
  const boxes = [];
  for (const entry of Object.values(viewer.places)) {
    if (entry.place.inside) continue;
    const turn = entry.group.rotation.y;
    for (const block of entry.set.blocks || []) {
      const bottom = block.center[1] - block.size[1] / 2;
      if (bottom > HEAD_M) continue;
      const c = entry.inner.localToWorld(new THREE.Vector3(...block.center));
      const a = turn + rad(block.heading);
      boxes.push({ name: block.name, place: entry.name, x: c.x, z: c.z, hx: block.size[0] / 2, hz: block.size[2] / 2, cos: Math.cos(a), sin: Math.sin(a), bottom, top: bottom + block.size[1] });
    }
  }
  for (const cube of epoch.ground.cubes || []) {
    boxes.push({ name: "a grey cube", place: null, x: cube.at[0], z: cube.at[1], hx: cube.size_m / 2, hz: cube.size_m / 2, cos: 1, sin: 0, bottom: 0, top: cube.size_m });
  }
  return boxes;
}

// A point in a box's own frame (the box turned by its heading about y).
const intoBox = (box, x, z) => [(x - box.x) * box.cos - (z - box.z) * box.sin, (x - box.x) * box.sin + (z - box.z) * box.cos];

// Circle against box: if the circle is in the box, move it out the short way. Says whether it had to.
function pushOutOfBox(p, r, box) {
  const [lx, lz] = intoBox(box, p.x, p.z);
  const nx = lx - clamp(lx, -box.hx, box.hx), nz = lz - clamp(lz, -box.hz, box.hz);
  const d = Math.hypot(nx, nz);
  if (d >= r) return false;
  let ox = 0, oz = 0;
  if (d > 1e-6) {
    ox = nx * (r - d) / d;
    oz = nz * (r - d) / d;
  } else { // the middle is inside: out through the nearest side
    const px = box.hx - Math.abs(lx), pz = box.hz - Math.abs(lz);
    if (px < pz) ox = (lx < 0 ? -1 : 1) * (px + r);
    else oz = (lz < 0 ? -1 : 1) * (pz + r);
  }
  p.x += ox * box.cos + oz * box.sin;
  p.z += -ox * box.sin + oz * box.cos;
  return true;
}

function pushOutOfCircle(p, r, c) {
  const dx = p.x - c.x, dz = p.z - c.z, d = Math.hypot(dx, dz), reach = r + c.r;
  if (d >= reach) return false;
  const k = d > 1e-6 ? (reach - d) / d : 0;
  p.x += d > 1e-6 ? dx * k : reach;
  p.z += dz * k;
  return true;
}

// How far along a line (from `from`, along the unit `dir`, at most `far`) before it enters a box. For the camera.
function reachBeforeBox(from, dir, far, box) {
  const [ox, oz] = intoBox(box, from.x, from.z);
  const dx = dir.x * box.cos - dir.z * box.sin, dz = dir.x * box.sin + dir.z * box.cos;
  let enter = 0, leave = far;
  for (const [o, d, lo, hi] of [[ox, dx, -box.hx, box.hx], [from.y, dir.y, box.bottom, box.top], [oz, dz, -box.hz, box.hz]]) {
    if (Math.abs(d) < 1e-9) {
      if (o < lo || o > hi) return far;
      continue;
    }
    const a = (lo - o) / d, b = (hi - o) / d;
    enter = Math.max(enter, Math.min(a, b));
    leave = Math.min(leave, Math.max(a, b));
    if (enter > leave) return far;
  }
  return enter;
}

// ---------- standing still ----------

// No clip stands still, so one is made from the walk: the legs straight as the skeleton was built (both feet
// flat, where the walk's feet land), everything else as it is on average through the walk (arms hanging in
// mid swing, the back at its usual lean), then a slow breath through the chest and a slower look about.
function idleClip(walk, root) {
  const LEGS = /^(hips|thigh|shin|foot|toe)/;
  const LOOP = 8.0, KEYS = 49;
  const times = Float32Array.from({ length: KEYS }, (_, i) => (i / (KEYS - 1)) * LOOP);
  const q = new THREE.Quaternion(), more = new THREE.Quaternion(), euler = new THREE.Euler();
  const tracks = [];
  for (const track of walk.tracks) {
    const dot = track.name.lastIndexOf(".");
    const bone = track.name.slice(0, dot), what = track.name.slice(dot + 1);
    const node = root.getObjectByName(bone);
    const size = track.getValueSize(), count = Math.max(1, track.times.length - 1); // the last key is the first again
    let base;
    if (LEGS.test(bone) && node) {
      base = (what === "quaternion" ? node.quaternion : node[what]).toArray();
    } else {
      base = new Array(size).fill(0);
      for (let k = 0; k < count; k++) {
        let sign = 1;
        if (what === "quaternion") { // q and -q are the same turn: add them the same way round
          let same = 0;
          for (let i = 0; i < 4; i++) same += track.values[i] * track.values[k * 4 + i];
          sign = same < 0 ? -1 : 1;
        }
        for (let i = 0; i < size; i++) base[i] += (sign * track.values[k * size + i]) / count;
      }
      if (what === "quaternion") base = q.fromArray(base).normalize().toArray();
    }
    const values = new Float32Array(KEYS * size);
    for (let k = 0; k < KEYS; k++) {
      const breath = Math.sin((times[k] / 4) * Math.PI * 2), late = Math.sin((times[k] / 4) * Math.PI * 2 - 0.9), look = Math.sin((times[k] / LOOP) * Math.PI * 2);
      let now = base;
      if (what === "quaternion") {
        euler.set(0, 0, 0);
        if (bone === "chest") euler.x = rad(-1.1 * breath);
        else if (bone === "spine") euler.x = rad(0.4 * breath);
        else if (bone === "head") euler.set(rad(0.7 * breath), rad(3.5 * look), 0);
        else if (bone === "upper_arm_l") euler.z = rad(-0.9 * late);
        else if (bone === "upper_arm_r") euler.z = rad(0.9 * late);
        now = q.fromArray(base).multiply(more.setFromEuler(euler)).toArray();
      } else if (what === "scale" && bone === "chest") {
        now = base.map((v) => v * (1 + 0.012 * breath));
      }
      values.set(now, k * size);
    }
    tracks.push(new track.constructor(track.name, times, values));
  }
  return new THREE.AnimationClip("idle", LOOP, tracks);
}

// A soft dark spot under the walker.
function blobShadow(wide) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  const ctx = canvas.getContext("2d"), fade = ctx.createRadialGradient(32, 32, 2, 32, 32, 32);
  fade.addColorStop(0, "rgba(28,25,23,0.42)");
  fade.addColorStop(1, "rgba(28,25,23,0)");
  ctx.fillStyle = fade;
  ctx.fillRect(0, 0, 64, 64);
  const spot = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, depthWrite: false, toneMapped: false }));
  spot.rotation.x = -Math.PI / 2;
  spot.scale.setScalar(wide);
  spot.position.y = 0.015;
  spot.renderOrder = 1;
  return spot;
}

let styled = null;
function styleSheet() {
  styled ||= new Promise((done) => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "walkabout.css";
    link.onload = link.onerror = done;
    document.head.append(link);
  });
  return styled;
}

// ---------- the walk ----------

export async function startWalk(options) {
  const walk = new Walkabout(options);
  await walk.begin();
  return walk;
}

export class Walkabout {
  // viewer: the WorldViewer. epoch, sets, runs: what the page already has. who: a toon's name, if asked for.
  // h, labelSprite: the page's own element and label makers. onStop, onPlace(name), onLoad(): tell the page.
  constructor({ viewer, epoch, sets, runs, who, h, labelSprite, onStop, onPlace }) {
    Object.assign(this, { viewer, epoch, sets, h, labelSprite, onStop, onPlace });
    this.cast = avatars(epoch, runs);
    this.who = this.cast.find((a) => a.toon === who && a.ready) || this.cast.find((a) => a.ready) || null;
    this.keys = new Set();
    this.stick = { x: 0, y: 0 };
    this.script = null;        // input from outside (the test): { x, y, run }
    this.pos = new THREE.Vector3();
    this.heading = 0;
    this.speed = 0;
    this.dir = new THREE.Vector2(0, 1);
    this.goal = null;
    this.look = { yaw: 0, pitch: CAMERA.pitch, distance: CAMERA.distance, reach: CAMERA.distance, eye: new THREE.Vector3(), held: 0 };
    this.clock = 0;
    this.frames = 0;
    this.fps = 0;
    this.says = {};            // toon -> its hello label
    this.undo = [];            // what to take back when walking stops
  }

  listen(target, kind, fn, more) {
    target.addEventListener(kind, fn, more);
    this.undo.push(() => target.removeEventListener(kind, fn, more));
  }

  async begin() {
    const { viewer } = this;
    if (!this.who) throw new Error("Nobody here has a walk and a run yet.");
    const before = performance.now();
    viewer.walkabout = this;
    viewer.flight = null;
    viewer.touched = true;
    viewer.controls.enabled = false;
    await styleSheet();
    if (this.gone) return;
    this.buildPanel();
    this.solids = solidBoxes(viewer, this.epoch);
    this.wide = this.solids.filter((b) => Math.max(b.hx, b.hz) >= 0.3 && b.top > 1.0); // what a camera can be behind: walls, not posts
    this.floors = [];
    this.things = this.artifactSpots();
    try {
      this.floors = await this.raisedFloors();
      await this.become(this.who, true);
    } catch (err) {
      this.stop();
      throw err;
    }
    if (this.gone) return; // stopped while it was still fetching
    this.was = { fov: viewer.camera.fov, near: viewer.camera.near };
    viewer.camera.fov = CAMERA.fov;
    viewer.camera.near = CAMERA.near;
    viewer.camera.updateProjectionMatrix();
    this.bind();
    this.loadMs = performance.now() - before;
    this.publish();
    this.last = performance.now();
    this.tick = this.tick.bind(this);
    this.raf = requestAnimationFrame(this.tick);
  }

  // Floors you can step up onto. Today that is a house's stage: the design says where it is, and the mark on
  // it says how high. Anything else raised (the ring, a riser) is a block, and you walk round it.
  async raisedFloors() {
    const floors = [];
    for (const entry of Object.values(this.viewer.places)) {
      const high = Object.values(entry.set.marks || {}).filter((m) => m.floor_y > 0 && m.floor_y <= STEP_UP);
      if (entry.place.inside || !high.length || typeof entry.set.design !== "string") continue;
      const design = await fetch(`sets/${entry.set.id}/${entry.set.design}`).then((r) => r.json()).catch(() => null);
      for (const area of design?.areas || []) {
        const lo = [area.x_m - design.wide_m / 2, area.z_m - design.deep_m / 2], hi = [lo[0] + area.wide_m, lo[1] + area.deep_m];
        const mark = high.find((m) => m.at[0] > lo[0] && m.at[0] < hi[0] && m.at[1] > lo[1] && m.at[1] < hi[1]);
        if (mark) floors.push({ entry, lo, hi, y: mark.floor_y });
      }
    }
    return floors;
  }

  floorAt(x, z) {
    let y = 0;
    const p = new THREE.Vector3();
    for (const floor of this.floors) {
      floor.entry.inner.worldToLocal(p.set(x, 0, z));
      if (p.x > floor.lo[0] && p.x < floor.hi[0] && p.z > floor.lo[1] && p.z < floor.hi[1]) y = Math.max(y, floor.y);
    }
    return y;
  }

  // Where each wondrous thing is, and what the story says about it.
  artifactSpots() {
    const spots = [];
    for (const thing of this.epoch.artifacts || []) {
      const entry = this.viewer.places[thing.place];
      const slot = entry?.set.slots?.[thing.slot];
      const holder = thing.held_by && this.epoch.toons.find((t) => t.toon === thing.held_by);
      if (slot) spots.push({ thing, at: entry.inner.localToWorld(new THREE.Vector3(...slot.at)), stands: slot.at[1] < STEP_UP });
      else if (holder) spots.push({ thing, holder: holder.toon });
    }
    return spots;
  }

  // The other toons, as circles on the floor. The walker's own still figure is put away while they are out.
  neighbours() {
    const out = [];
    for (const toon of this.epoch.toons) {
      const entry = this.viewer.places[toon.place];
      const body = entry?.[`toon:${toon.toon}`];
      if (!body) continue;
      body.visible = toon.toon !== this.who.toon;
      for (const o of entry.extras) if (o.userData.toon) o.visible = o.userData.toon !== this.who.toon && entry.name === this.viewer.at; // and their name goes with them
      if (!body.visible) continue;
      const box = new THREE.Box3().setFromObject(body), size = box.getSize(new THREE.Vector3());
      const at = body.getWorldPosition(new THREE.Vector3());
      out.push({ toon, entry, body, x: at.x, z: at.z, floor: at.y, r: clamp(Math.min(size.x, size.z) * 0.42, 0.3, 0.8), tall: size.y });
    }
    return out;
  }

  // Become a toon: fetch its two files, stand it where it lives. `first` also points the camera.
  async become(who, first = false) {
    const { viewer } = this;
    this.status(`Fetching ${who.name}…`);
    const [walkFile, runFile] = await Promise.all([viewer.get(who.walk), viewer.get(who.run)]);
    if (this.gone) return;
    const model = walkFile.scene;
    const walkClip = walkFile.animations[0], runClip = runFile.animations[0];
    if (!walkClip || !runClip) throw new Error(`${who.name}'s files have no walk or no run in them.`);
    walkFile.idle ||= idleClip(walkClip, model); // made once, while the skeleton is still as it was built
    // All the gear is on, so the skin kept under each piece stays hidden (as on the object's own page).
    model.traverse((o) => {
      if (o.userData.under) o.visible = false;
      if (o.isSkinnedMesh) o.frustumCulled = false; // its box is the pose it was built in, not where the bones are now
    });
    this.leave();
    this.who = who;
    this.model = model;
    this.holder = new THREE.Group();
    this.holder.add(model);
    this.mixer = new THREE.AnimationMixer(model);
    this.acts = { idle: this.mixer.clipAction(walkFile.idle), walk: this.mixer.clipAction(walkClip), run: this.mixer.clipAction(runClip) };
    for (const act of Object.values(this.acts)) act.play();
    this.feet = ["foot_l", "foot_r"].map((name) => model.getObjectByName(name)).filter(Boolean);
    // Its size, from its own skeleton: how tall (the camera stands back that much further for a big toon) and how wide.
    const joint = (name) => model.getObjectByName(name)?.getWorldPosition(new THREE.Vector3());
    this.tall = (joint("head")?.y || 1.5) + 0.2;
    const left = joint("upper_arm_l"), right = joint("upper_arm_r");
    this.bodyR = clamp(left && right ? left.distanceTo(right) * 0.62 : BODY_R, BODY_R, 0.8);
    this.far = Math.max(1, this.tall / 1.75);
    this.holder.add(blobShadow(this.bodyR * 3.9));
    this.others = this.neighbours();
    // Where they live: their own mark in the world.
    const home = this.epoch.toons.find((t) => t.toon === who.toon);
    const entry = viewer.places[home.place], mark = entry.set.marks[home.mark];
    const spot = entry.inner.localToWorld(new THREE.Vector3(mark.at[0], 0, mark.at[1]));
    this.pos.set(spot.x, mark.floor_y || 0, spot.z);
    this.heading = entry.group.rotation.y + rad(mark.facing_deg);
    this.speed = 0;
    this.goal = null;
    this.settle(this.pos);
    if (first) {
      this.look.yaw = this.heading;
      this.look.eye.set(this.pos.x, this.pos.y + this.tall * 0.72, this.pos.z);
    }
    this.pose(0);
    viewer.scene.add(this.holder);
    this.nameEl.textContent = who.name;
    this.fillMenu();
    this.status(null);
    viewer.report();
    this.loaded = viewer.loadedSoFar ? this.cost([who.walk, who.run]) : null;
  }

  // What walking fetched beyond the world itself: this file, its style sheet, and the walker's two files.
  cost(files) {
    const sizes = new Map(performance.getEntriesByType("resource").map((r) => [new URL(r.name).pathname, r.encodedBodySize || r.transferSize || 0]));
    const paths = [new URL(import.meta.url).pathname, new URL("walkabout.css", import.meta.url).pathname, ...files.map((f) => new URL(f, location.href).pathname)];
    return { files: paths.length, bytes: paths.reduce((sum, p) => sum + (sizes.get(p) || 0), 0) };
  }

  leave() {
    if (!this.holder) return;
    this.mixer.stopAllAction();
    this.viewer.scene.remove(this.holder);
    this.holder = this.mixer = null;
  }

  // ----- what the hands are doing -----

  bind() {
    const canvas = this.viewer.renderer.domElement;
    const KEYS = { KeyW: "up", ArrowUp: "up", KeyS: "down", ArrowDown: "down", KeyA: "left", ArrowLeft: "left", KeyD: "right", ArrowRight: "right", ShiftLeft: "run", ShiftRight: "run" };
    this.listen(window, "keydown", (e) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.code === "Escape") return this.onStop?.();
      if (!KEYS[e.code]) return;
      this.keys.add(KEYS[e.code]);
      if (KEYS[e.code] !== "run") e.preventDefault(); // the arrows would scroll the page
    });
    this.listen(window, "keyup", (e) => this.keys.delete(KEYS[e.code]));
    this.listen(window, "blur", () => this.keys.clear());

    // On the picture itself: a tap on the ground walks there, a drag turns the camera, two fingers or the wheel come closer.
    const fingers = new Map();
    let spread = 0;
    this.listen(canvas, "pointerdown", (e) => {
      fingers.set(e.pointerId, { x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY, t: performance.now(), moved: false });
      canvas.setPointerCapture?.(e.pointerId);
      spread = 0;
    });
    this.listen(canvas, "pointermove", (e) => {
      const f = fingers.get(e.pointerId);
      if (!f) return;
      const dx = e.clientX - f.x, dy = e.clientY - f.y;
      f.x = e.clientX;
      f.y = e.clientY;
      if (Math.hypot(f.x - f.x0, f.y - f.y0) > 8) f.moved = true;
      if (fingers.size === 1 && f.moved) {
        this.look.yaw -= dx * 0.0065;
        this.look.pitch = clamp(this.look.pitch + dy * 0.0045, CAMERA.low, CAMERA.high);
        this.look.held = this.clock + 2.5; // leave the camera where it was put for a moment
      } else if (fingers.size === 2) {
        const [a, b] = [...fingers.values()], now = Math.hypot(a.x - b.x, a.y - b.y);
        if (spread) this.look.distance = clamp(this.look.distance * (spread / now), CAMERA.closest + 1, CAMERA.furthest);
        spread = now;
        a.moved = b.moved = true;
      }
    });
    const lift = (e) => {
      const f = fingers.get(e.pointerId);
      fingers.delete(e.pointerId);
      spread = 0;
      if (f && !f.moved && e.type === "pointerup" && performance.now() - f.t < 450) this.tap(e.clientX, e.clientY);
    };
    this.listen(canvas, "pointerup", lift);
    this.listen(canvas, "pointercancel", lift);
    this.listen(canvas, "wheel", (e) => {
      e.preventDefault();
      this.look.distance = clamp(this.look.distance * Math.exp(e.deltaY * 0.0012), CAMERA.closest + 1, CAMERA.furthest);
    }, { passive: false });
  }

  // A tap on the ground: walk there, in a straight line, sliding round what is in the way.
  tap(x, y) {
    const box = this.viewer.renderer.domElement.getBoundingClientRect();
    const ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2(((x - box.left) / box.width) * 2 - 1, -((y - box.top) / box.height) * 2 + 1), this.viewer.camera);
    const hit = ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), new THREE.Vector3());
    if (hit) this.walkTo(hit.x, hit.z);
  }

  walkTo(x, z) {
    const g = this.epoch.ground;
    x = clamp(x, g.center[0] - g.size_m[0] / 2 + this.bodyR, g.center[0] + g.size_m[0] / 2 - this.bodyR);
    z = clamp(z, g.center[1] - g.size_m[1] / 2 + this.bodyR, g.center[1] + g.size_m[1] / 2 - this.bodyR);
    const far = Math.hypot(x - this.pos.x, z - this.pos.z);
    this.goal = { x, z, best: far, since: this.clock, run: far > 9 };
    if (!this.pin) {
      this.pin = new THREE.Mesh(new THREE.RingGeometry(0.2, 0.3, 28), new THREE.MeshBasicMaterial({ color: 0x44679b, transparent: true, opacity: 0.85, depthWrite: false, toneMapped: false }));
      this.pin.rotation.x = -Math.PI / 2;
      this.pin.renderOrder = 2;
      this.viewer.scene.add(this.pin);
    }
    this.pin.position.set(x, this.floorAt(x, z) + 0.03, z);
    this.pin.visible = true;
  }

  // Which way and how hard: { x (right), y (ahead), pace (0..1 of a walk), run }, as the camera sees it.
  input() {
    if (this.script) return { x: this.script.x, y: this.script.y, pace: 1, run: Boolean(this.script.run) };
    const k = this.keys;
    let x = (k.has("right") ? 1 : 0) - (k.has("left") ? 1 : 0), y = (k.has("up") ? 1 : 0) - (k.has("down") ? 1 : 0);
    if (x || y) {
      const n = Math.hypot(x, y);
      return { x: x / n, y: y / n, pace: 1, run: k.has("run") };
    }
    const push = Math.hypot(this.stick.x, this.stick.y);
    if (push > DEAD) return { x: this.stick.x / push, y: this.stick.y / push, pace: clamp((push - DEAD) / (RUN_AT - DEAD), 0, 1), run: push >= RUN_AT };
    return null;
  }

  // ----- each frame -----

  tick(now) {
    if (this.gone) return;
    this.raf = requestAnimationFrame(this.tick);
    const real = (now - this.last) / 1000;
    this.last = now;
    this.frames += 1;
    if (real > 0) this.fps += (1 / real - this.fps) * 0.08;
    let dt = Math.min(real, 0.25); // a long pause (a hidden tab) is not a long stride
    if (this.holder) {
      while (dt > 1e-5) { // short steps, so a slow frame can't carry anyone through a thin wall
        const step = Math.min(dt, 1 / 30);
        this.move(step);
        dt -= step;
      }
      this.aim(Math.min(real, 0.1));
      if (this.frames % 6 === 0) this.notice();
    }
    this.viewer.renderer.render(this.viewer.scene, this.viewer.camera);
    this.taking?.(real);
  }

  move(dt) {
    const A = this.who, pushed = this.input();
    let want = 0;
    if (pushed) {
      this.goal = null;
      if (this.pin) this.pin.visible = false;
      // ahead is the way the camera looks; right is its right
      const sin = Math.sin(this.look.yaw), cos = Math.cos(this.look.yaw);
      this.dir.set(sin * pushed.y - cos * pushed.x, cos * pushed.y + sin * pushed.x).normalize();
      want = pushed.run ? A.runSpeed : A.walkSpeed * (0.55 + 0.45 * pushed.pace);
    } else if (this.goal) {
      const dx = this.goal.x - this.pos.x, dz = this.goal.z - this.pos.z, far = Math.hypot(dx, dz);
      if (far < this.goal.best - 0.05) { this.goal.best = far; this.goal.since = this.clock; }
      if (far < 0.22 || this.clock - this.goal.since > 0.9) { // there, or something is in the way
        this.goal = null;
        this.pin.visible = false;
      } else {
        this.dir.set(dx / far, dz / far);
        if (far < 4) this.goal.run = false;
        want = this.goal.run ? A.runSpeed : A.walkSpeed * clamp(far / 0.6, 0.55, 1); // ease in over the last half-metre
      }
    }
    this.speed += clamp(want - this.speed, -SLOW_DOWN * dt, SPEED_UP * dt);
    if (want > 0) this.heading += turnTo(this.heading, Math.atan2(this.dir.x, this.dir.y)) * Math.min(1, TURN * dt);

    // Move, then come back out of anything solid. What is left is how far the body really went; the legs are
    // played at that speed, so walking into a wall slows to a stand instead of treading on the spot.
    const from = this.pos.clone();
    this.pos.x += this.dir.x * this.speed * dt;
    this.pos.z += this.dir.y * this.speed * dt;
    this.touching = this.settle(this.pos);
    const went = Math.hypot(this.pos.x - from.x, this.pos.z - from.z);
    this.speed = Math.min(this.speed, went / dt);
    this.pos.y += (this.floorAt(this.pos.x, this.pos.z) - this.pos.y) * Math.min(1, 14 * dt);
    this.pose(dt);
    this.clock += dt;
  }

  // Keep a point out of every solid thing and on the ground. Returns the name of what it was pushed out of.
  settle(p) {
    let hit = null;
    for (let pass = 0; pass < 3; pass++) {
      let moved = false;
      for (const box of this.solids) if (box.top > p.y + 0.06 && pushOutOfBox(p, this.bodyR, box)) { moved = true; hit = box.name; }
      for (const o of this.others) if (pushOutOfCircle(p, this.bodyR, o)) { moved = true; hit = o.toon.name; }
      for (const s of this.things) if (s.stands && pushOutOfCircle(p, this.bodyR, { x: s.at.x, z: s.at.z, r: 0.16 })) { moved = true; hit = s.thing.title; }
      if (!moved) break;
    }
    const g = this.epoch.ground, hx = g.size_m[0] / 2 - this.bodyR, hz = g.size_m[1] / 2 - this.bodyR;
    if (Math.abs(p.x - g.center[0]) > hx || Math.abs(p.z - g.center[1]) > hz) hit = "the edge of the world";
    p.x = clamp(p.x, g.center[0] - hx, g.center[0] + hx);
    p.z = clamp(p.z, g.center[1] - hz, g.center[1] + hz);
    return hit;
  }

  // Put the body where it is and play the legs at the speed it is going.
  pose(dt) {
    const A = this.who, v = this.speed;
    const moving = smooth(0, 0.42 * A.walkSpeed, v);
    const running = smooth(A.walkSpeed * 1.12, A.runSpeed * 0.88, v);
    this.acts.idle.setEffectiveWeight(1 - moving);
    this.acts.walk.setEffectiveWeight(moving * (1 - running));
    this.acts.run.setEffectiveWeight(moving * running);
    // feet over the ground = clip speed x playback rate: that is what keeps a planted foot planted
    this.acts.walk.setEffectiveTimeScale(clamp(v / A.walkSpeed, 0.45, 1.7));
    this.acts.run.setEffectiveTimeScale(clamp(v / A.runSpeed, 0.6, 1.15));
    this.gait = running > 0.5 ? "run" : moving > 0.5 ? "walk" : "idle";
    this.mixer.update(dt);
    this.holder.position.copy(this.pos);
    this.holder.rotation.y = this.heading;
  }

  // The camera: behind and a little above, following smoothly, and never the far side of a wall.
  aim(dt) {
    const { look } = this, cam = this.viewer.camera;
    if (this.speed > 0.2 && this.clock > look.held) { // drift round behind the way they are going
      look.yaw += Math.sin(turnTo(look.yaw, this.heading)) * Math.min(1, this.speed / this.who.walkSpeed) * 1.5 * dt;
    }
    const ease = 1 - Math.exp(-10 * dt);
    look.eye.x += (this.pos.x - look.eye.x) * ease;
    look.eye.y += (this.pos.y + this.tall * 0.72 - look.eye.y) * ease;
    look.eye.z += (this.pos.z - look.eye.z) * ease;
    const flat = Math.cos(look.pitch);
    const back = new THREE.Vector3(-Math.sin(look.yaw) * flat, Math.sin(look.pitch), -Math.cos(look.yaw) * flat);
    const wanted = look.distance * this.far;
    let clear = wanted;
    for (const box of this.wide) clear = Math.min(clear, reachBeforeBox(look.eye, back, wanted + 0.4, box) - 0.4);
    clear = Math.max(clear, 0.35);
    // come in at once when a wall gets between, go back out gently
    look.reach = clear < look.reach ? clear : look.reach + (clear - look.reach) * (1 - Math.exp(-3.5 * dt));
    cam.position.copy(look.eye).addScaledVector(back, look.reach);
    cam.lookAt(look.eye);
    this.model.visible = look.reach > 0.8; // backed right up against a wall: don't look out through their head
    this.viewer.controls.target.copy(look.eye); // so the orbit view picks up from here
  }

  // Where are we, who is near, what is near: the card, the hellos and the story line.
  notice() {
    const { viewer } = this, p = new THREE.Vector3();
    let inside = null;
    for (const entry of Object.values(viewer.places)) {
      if (entry.place.inside) continue;
      entry.inner.worldToLocal(p.copy(this.pos));
      const out = Math.max(entry.lo[0] - p.x, p.x - entry.hi[0], entry.lo[1] - p.z, p.z - entry.hi[1]);
      if (out < NEAR_PLACE && viewer.ready) viewer.comeClose(entry); // its small things arrive before you do
      if (out < 0 && (!inside || entry.area < inside.area)) inside = entry;
    }
    if ((inside?.name || null) !== this.place) {
      this.place = inside?.name || null;
      this.showPlace(inside);
      this.onPlace?.(this.place);
    }
    let said = null;
    for (const o of this.others) {
      const near = Math.hypot(o.x - this.pos.x, o.z - this.pos.z) < NEAR_TOON + o.r;
      if (near) said = o.toon.toon;
      if (near && !this.says[o.toon.toon]) {
        const label = this.labelSprite(HELLO[o.toon.toon] || "Hello!");
        label.material.sizeAttenuation = false;
        label.scale.multiplyScalar(0.026);
        label.position.copy(o.body.position).add(new THREE.Vector3(0, o.tall + 0.72, 0));
        o.entry.inner.add(label);
        this.says[o.toon.toon] = label;
      }
      if (this.says[o.toon.toon]) this.says[o.toon.toon].visible = near;
    }
    this.hello = said;
    let nearest = null, best = NEAR_THING;
    for (const spot of this.things) {
      const who = spot.holder && this.others.find((o) => o.toon.toon === spot.holder);
      const at = spot.at || who;
      if (!at) continue;
      const far = Math.hypot(at.x - this.pos.x, at.z - this.pos.z);
      if (far < best) { best = far; nearest = spot.thing; }
    }
    if ((nearest?.name || null) !== this.line) {
      this.line = nearest?.name || null;
      this.showLine(nearest);
    }
  }

  // ----- what is on the picture -----

  buildPanel() {
    const { h } = this, pane = this.viewer.el;
    const touch = matchMedia("(pointer: coarse)").matches || navigator.maxTouchPoints > 0 || innerWidth <= 720;
    pane.classList.add("walking");
    this.nameEl = h("strong", {}, this.who.name);
    this.menu = h("div", { class: "walk-menu clay-surface", hidden: true });
    const whoBtn = h("button", { class: "walk-who clay-chip", type: "button", "aria-haspopup": "true", "aria-expanded": "false", onclick: () => {
      this.menu.hidden = !this.menu.hidden;
      whoBtn.setAttribute("aria-expanded", String(!this.menu.hidden));
    } }, "Walking as: ", this.nameEl, h("span", { class: "caret", "aria-hidden": "true" }, "▾"));
    this.card = h("div", { class: "walk-card clay-surface", hidden: true });
    this.lineEl = h("p", { class: "walk-line clay-surface", hidden: true, role: "status" });
    this.statusEl = h("div", { class: "walk-status clay-surface", hidden: true });
    this.knob = h("div", { class: "walk-knob" });
    this.stickEl = h("div", { class: "walk-stick", role: "application", "aria-label": "Thumb stick: push to walk, push further to run" }, this.knob);
    this.panel = h("div", { class: `walk-panel${touch ? " touch" : ""}` },
      h("div", { class: "walk-top" },
        this.card,
        h("div", { class: "walk-tools" },
          h("div", { class: "walk-pick" }, whoBtn, this.menu),
          h("button", { class: "walk-stop clay-button", type: "button", onclick: () => this.onStop?.() }, "Stop walking"),
        ),
      ),
      this.statusEl,
      h("div", { class: "walk-bottom" },
        touch ? this.stickEl : h("p", { class: "walk-keys" }, h("kbd", {}, "W"), h("kbd", {}, "A"), h("kbd", {}, "S"), h("kbd", {}, "D"), " or the arrows to walk · ", h("kbd", {}, "Shift"), " to run · drag to look round · click the ground to walk there"),
        this.lineEl,
      ),
    );
    pane.append(this.panel);
    this.undo.push(() => { this.panel.remove(); pane.classList.remove("walking"); });
    if (!touch) return;
    // The thumb stick: push to walk, push further to run.
    let held = null;
    const set = (e) => {
      const box = this.stickEl.getBoundingClientRect(), reach = box.width / 2 - 22;
      let x = e.clientX - (box.left + box.width / 2), y = e.clientY - (box.top + box.height / 2);
      const far = Math.hypot(x, y);
      if (far > reach) { x *= reach / far; y *= reach / far; }
      this.stick.x = x / reach;
      this.stick.y = -y / reach;
      this.knob.style.transform = `translate(${x}px, ${y}px)`;
      this.knob.classList.toggle("run", Math.hypot(this.stick.x, this.stick.y) >= RUN_AT);
    };
    const let_go = (e) => {
      if (e.pointerId !== held) return;
      held = null;
      this.stick.x = this.stick.y = 0;
      this.knob.style.transform = "";
      this.knob.classList.remove("run");
    };
    this.listen(this.stickEl, "pointerdown", (e) => { held = e.pointerId; this.stickEl.setPointerCapture?.(e.pointerId); set(e); e.preventDefault(); });
    this.listen(this.stickEl, "pointermove", (e) => { if (e.pointerId === held) set(e); });
    this.listen(this.stickEl, "pointerup", let_go);
    this.listen(this.stickEl, "pointercancel", let_go);
  }

  // The picker: everyone who has a walk and a run. Today only the READY ones can be chosen.
  fillMenu() {
    const { h } = this;
    this.menu.replaceChildren(...this.cast.map((a) => h("button", {
      class: "walk-option", type: "button", disabled: !a.ready, "aria-pressed": String(a === this.who),
      onclick: () => { this.menu.hidden = true; if (a !== this.who) this.become(a).catch((err) => { console.error(err); this.status("Couldn't fetch them."); }); },
    }, a.name, a.ready ? null : h("small", {}, "coming soon"))));
  }

  status(text) {
    this.statusEl.hidden = !text;
    this.statusEl.textContent = text || "";
  }

  showPlace(entry) {
    const { h } = this;
    this.card.hidden = !entry;
    if (!entry) return;
    const here = this.epoch.toons.filter((t) => t.toon !== this.who.toon && (t.place === entry.name || this.epoch.places[t.place]?.inside === entry.name)).map((t) => t.name);
    this.card.replaceChildren(
      h("h3", {}, entry.place.label || entry.set.title || entry.name),
      h("p", {}, here.length ? `Here now: ${here.join(", ")}, and you.` : "Just you here for now."),
      h("a", { class: "clay-button", href: `#/set/${encodeURIComponent(entry.place.set)}` }, "Open this place"),
    );
  }

  showLine(thing) {
    this.lineEl.hidden = !thing;
    if (thing) this.lineEl.replaceChildren(this.h("strong", {}, `${thing.title}. `), thing.about, thing.whose ? this.h("em", {}, ` ${thing.whose}.`) : "");
  }

  // ----- for whoever is checking from outside (scripts/world/test_walkabout.py) -----

  publish() {
    const walk = this;
    window.forgeWalk = {
      get ready() { return Boolean(walk.holder); },
      state() {
        return {
          who: walk.who.toon, x: walk.pos.x, y: walk.pos.y, z: walk.pos.z, heading_deg: THREE.MathUtils.radToDeg(walk.heading), speed: walk.speed, gait: walk.gait,
          place: walk.place || null, line: walk.line || null, hello: walk.hello || null, touching: walk.touching || null,
          body_r: walk.bodyR, walk_speed: walk.who.walkSpeed, run_speed: walk.who.runSpeed, fps: walk.fps, frames: walk.frames, extra: walk.loaded, load_ms: walk.loadMs,
          camera: walk.viewer.camera.position.toArray(), walking_to: walk.goal ? [walk.goal.x, walk.goal.z] : null,
          solids: walk.solids.length, floors: walk.floors.length, cast: walk.cast.map((a) => ({ toon: a.toon, ready: a.ready })),
        };
      },
      steer(x, y, run) { walk.script = x === null || x === undefined ? null : { x, y, run }; },
      put(x, z, headingDeg = 0, lookDeg = headingDeg) {
        walk.pos.set(x, walk.floorAt(x, z), z);
        walk.heading = rad(headingDeg);
        walk.look.yaw = rad(lookDeg);
        walk.look.held = walk.clock + 1e6; // whoever is checking decides where the camera looks
        walk.look.eye.set(x, walk.pos.y + walk.tall * 0.72, z);
        walk.speed = 0;
        walk.goal = null;
      },
      walkTo(x, z) { walk.walkTo(x, z); },
      record(seconds) { return walk.record(seconds); },
      // Where the hands and feet are just now: is this a stand, or the T the skeleton was built in?
      pose() {
        const at = (name) => walk.model.getObjectByName(name).getWorldPosition(new THREE.Vector3());
        const hand = at("hand_l"), arm = at("upper_arm_l");
        return { hand_below_shoulder_m: arm.y - hand.y, hand_out_from_shoulder_m: Math.hypot(hand.x - arm.x, hand.z - arm.z), feet_off_floor_m: Math.max(at("foot_l").y, at("foot_r").y) - walk.pos.y };
      },
      stillFigureShown() {
        const home = walk.epoch.toons.find((t) => t.toon === walk.who.toon);
        return walk.viewer.places[home.place][`toon:${home.toon}`].visible;
      },
    };
  }

  // Watch the walk for a while and say what happened: how far and how fast the body went, how fast the clip
  // said its feet were going, how much the foot that was down slid, and how smooth the frames were.
  record(seconds) {
    return new Promise((done) => {
      const began = { clock: this.clock, x: this.pos.x, z: this.pos.z }, frames = [];
      let path = 0, feet = 0, slid = 0, planted = null, last = this.pos.clone(), lowest = Infinity;
      const at = this.feet.map(() => new THREE.Vector3());
      const samples = [];
      this.taking = (real) => {
        frames.push(real * 1000);
        path += Math.hypot(this.pos.x - last.x, this.pos.z - last.z);
        last.copy(this.pos);
        const A = this.who, clip = this.gait === "run" ? A.runSpeed * this.acts.run.getEffectiveTimeScale() : this.gait === "walk" ? A.walkSpeed * this.acts.walk.getEffectiveTimeScale() : 0;
        feet += clip * real;
        if (this.feet.length === 2) {
          this.feet.forEach((bone, i) => bone.getWorldPosition(at[i]));
          lowest = Math.min(lowest, at[0].y - this.pos.y, at[1].y - this.pos.y);
          samples.push(at.map((v) => [v.x, v.y - this.pos.y, v.z]));
        }
        if (this.clock - began.clock < seconds) return;
        this.taking = null;
        // The foot that is down: the lower ankle, while it is within 2 cm of as low as an ankle gets.
        for (let i = 1; i < samples.length; i++) {
          const now = samples[i], was = samples[i - 1];
          const foot = now[0][1] <= now[1][1] ? 0 : 1;
          if (now[foot][1] < lowest + 0.02 && planted === foot) slid += Math.hypot(now[foot][0] - was[foot][0], now[foot][2] - was[foot][2]);
          planted = now[foot][1] < lowest + 0.02 ? foot : null;
        }
        const took = this.clock - began.clock, sorted = frames.slice().sort((a, b) => a - b);
        done({
          seconds: took, went_m: Math.hypot(this.pos.x - began.x, this.pos.z - began.z), path_m: path, speed_m_s: path / took, clip_speed_m_s: feet / took,
          foot_slid_m: slid, gait: this.gait, touching: this.touching || null, x: this.pos.x, z: this.pos.z,
          frames: frames.length, fps: 1000 / (frames.reduce((a, b) => a + b, 0) / frames.length), frame_ms_median: sorted[sorted.length >> 1], frame_ms_p95: sorted[Math.floor(sorted.length * 0.95)],
        });
      };
    });
  }

  // Stop walking: everything goes back as it was, and the orbit view picks up from where the camera is.
  stop() {
    if (this.gone) return;
    this.gone = true;
    cancelAnimationFrame(this.raf);
    const { viewer } = this;
    this.undo.forEach((fn) => fn());
    this.leave();
    if (this.pin) viewer.scene.remove(this.pin);
    for (const label of Object.values(this.says)) label.removeFromParent();
    for (const toon of this.epoch.toons) { const body = viewer.places[toon.place]?.[`toon:${toon.toon}`]; if (body) body.visible = true; }
    if (this.was) { viewer.camera.fov = this.was.fov; viewer.camera.near = this.was.near; viewer.camera.updateProjectionMatrix(); }
    viewer.controls.enabled = true;
    viewer.walkabout = null;
    window.forgeWalk = null;
    if (!viewer.gone) { viewer.controls.update(); viewer.draw(); }
  }
}
