// Forge gallery: a place grown by a world model (World Labs Marble), shown as it really is.
//
// A Marble world is a cloud of soft colored blobs ("splats"), not a mesh. This page draws the blobs with
// World Labs' own open renderer, Spark, at true size with the floor at 0, in the frame of the standing set
// made from the same world (`just set-from-marble`), so the set's marks and cameras fit it exactly. One of
// our toons stands in it, so we can see how a drawn character sits in a place like this.
//
//   #/marble/<set>[/<camera>][?detail=100k|500k|full_res&show=mesh&bare=1&...]
//
// Nothing here is fetched until the page is opened: this file, its style sheet, Spark from the CDN, and the
// world's own files from /marble/<world>/ (world/marble/, kept out of git: see scripts/gallery.py --marble).
//
// The arithmetic, from set.json's `marble` block (scripts/sets/from_marble.py writes it):
//   point in the set = turn_y(turn_deg) * [x * scale, ground - y * scale, -z * scale] + move
// which in three.js is a group (move, turn) holding the raw files under a half turn about x, sized by scale
// and lifted by ground.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

// Spark 0.1.10 (October 2025): the last release that asks nothing of three.js newer than our 0.170.
const SPARK = "https://cdn.jsdelivr.net/npm/@sparkjsdev/spark@0.1.10/dist/spark.module.js";
const DETAIL = [
  ["100k", "Quick", "100 thousand dots"],
  ["500k", "Sharper", "half a million dots"],
  ["full_res", "Sharpest", "every dot"],
];
const WHO = { run: "roosevelt-wrestler-1890s", name: "Roosevelt", mark: "bar", files: [["shots/tag-moves/painted-tag.glb", 0.5], ["profiles/painted-walk.glb", 0]] };
const EYE = 1.6, BODY = 0.28, WALK_MPS = 1.6, RUN_MPS = 3.4, STICK_REACH = 46;
const SENSOR_MM = 36, FILM = 16 / 9;

const rad = (d) => THREE.MathUtils.degToRad(d || 0);
const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid);
  return el;
};
const mb = (bytes) => `${(bytes / 1e6).toFixed(bytes < 1e7 ? 1 : 0)} MB`;

function styles() {
  if (document.querySelector("link[data-marble]")) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = new URL("marble.css", import.meta.url).href;
  link.dataset.marble = "1";
  document.head.append(link);
}

// The page for one Marble place. `set` is its standing set (from /api/sets), `runs` the gallery's runs.
// Returns { el, dispose }.
export function marblePage(set, runs, wantedCamera, options = new URLSearchParams()) {
  styles();
  const marble = set.marble;
  const cameraNames = Object.keys(set.cameras || {});
  const coarse = window.matchMedia?.("(pointer: coarse)").matches;
  const have = DETAIL.filter(([key]) => marble.splats?.[key]);
  const state = {
    detail: have.find(([key]) => key === options.get("detail"))?.[0] || (have.find(([key]) => key === "500k") || have[0])?.[0],
    show: options.get("show") === "mesh" ? "mesh" : "splats",
    solid: options.get("solid") === "1",
    who: options.get("who") !== "0",
    shadow: options.get("shadow") !== "0",
    walking: options.get("walk") === "1",
    look: cameraNames.includes(wantedCamera) ? wantedCamera : cameraNames[0] || null,
  };
  const press = (btn, on) => btn.setAttribute("aria-pressed", String(on));
  const stage = h("div", { class: "stage set-stage marble-stage clay-well" });
  let view = null;

  const detailChips = have.map(([key, label, about]) => h("button", { class: "chip clay-chip", type: "button", title: about, "aria-pressed": String(state.detail === key), onclick: () => {
    state.detail = key;
    detailChips.forEach((chip, i) => press(chip, have[i][0] === key));
    view?.setDetail(key);
  } }, label));
  const showChips = [["splats", "As it is"], ["mesh", "As Blender films it"]].map(([key, label]) => h("button", { class: "chip clay-chip", type: "button", "aria-pressed": String(state.show === key), onclick: () => {
    state.show = key;
    showChips.forEach((chip, i) => press(chip, ["splats", "mesh"][i] === key));
    view?.setShow(key);
  } }, label));
  const toggle = (label, key, apply) => {
    const btn = h("button", { class: "toggle clay-button clay-button--soft", type: "button", "aria-pressed": String(state[key]), onclick: () => { state[key] = !state[key]; press(btn, state[key]); apply(state[key]); } }, label);
    return btn;
  };
  const solidBtn = toggle("What you'd bump into", "solid", (on) => view?.setSolid(on));
  const whoBtn = toggle(WHO.name, "who", (on) => view?.setWho(on));
  const shadowBtn = toggle("His shadow", "shadow", (on) => view?.setShadow(on));
  const walkBtn = toggle("Walk around", "walking", (on) => { view?.setWalking(on); lookChips.forEach((chip) => press(chip, false)); hint(); });
  const lookChips = cameraNames.map((name) => h("button", { class: "chip clay-chip", type: "button", "aria-pressed": String(state.look === name && !state.walking), onclick: () => {
    state.look = name;
    state.walking = false;
    press(walkBtn, false);
    lookChips.forEach((chip, i) => press(chip, cameraNames[i] === name));
    view?.setWalking(false);
    view?.look(name);
    hint();
    history.replaceState(null, "", `#/marble/${encodeURIComponent(set.id)}/${name}`);
  } }, `From the ${name.replace(/_/g, " ")}`));
  const how = h("p", { class: "hint marble-how" });
  function hint() {
    how.textContent = state.walking
      ? (coarse ? "Thumb on the lower half to walk, drag the upper half to look." : "W A S D or the arrow keys walk, Shift hurries, drag to look.")
      : "Drag to look round, pinch or scroll to come closer.";
  }
  hint();
  const speed = h("p", { class: "hint marble-speed", "aria-live": "off" }, "");

  const el = h("article", { class: "object marble" + (options.get("bare") === "1" ? " marble-bare" : "") },
    h("a", { class: "back", href: `#/set/${encodeURIComponent(set.id)}` }, "← Its marks and cameras"),
    h("h1", {}, set.title || set.name),
    h("p", { class: "lede" }, "Step inside. This room was grown by a world model from one picture, and it is shown here at its real size with ", WHO.name, " at the bar, so you can see how one of ours stands in it."),
    h("div", { class: "versions", role: "group", "aria-label": "Look from" }, lookChips),
    h("div", { class: "gear", role: "group", "aria-label": "How sharp" }, h("span", { class: "hint" }, "How sharp"), detailChips),
    h("div", { class: "gear", role: "group", "aria-label": "Show the room" }, h("span", { class: "hint" }, "The room"), showChips),
    h("div", { class: "controls" }, h("div", { class: "toggles" }, walkBtn, whoBtn, shadowBtn, solidBtn)),
    stage,
    how,
    speed,
  );
  queueMicrotask(() => { view = new MarbleView(stage, set, runs, state, options, (text) => { speed.textContent = text; }); });
  return { el, dispose: () => { view?.dispose(); view = null; } };
}

class MarbleView {
  constructor(stage, set, runs, state, options, say) {
    Object.assign(this, { stage, set, runs, state, options, say });
    this.marble = set.marble;
    this.base = `marble/${encodeURIComponent(this.marble.world)}/`;
    this.el = h("div", { class: "pane" });
    this.status = h("div", { class: "status" }, "Fetching the room…");
    this.el.append(this.status);
    stage.replaceChildren(this.el);
    // Spark sorts and blends the blobs itself; the canvas's own smoothing only costs time.
    this.renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: options.get("bare") === "1" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    const clear = options.get("clear");
    this.renderer.setClearColor(new THREE.Color(clear ? `#${clear}` : "#14100c"));
    this.el.prepend(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(50, 16 / 9, 0.05, 200);
    this.lens = 28;
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.minDistance = 0.3;
    this.controls.maxDistance = 14;
    this.controls.zoomSpeed = 0.7;

    // The raw files sit in here; the group is the set's frame.
    this.frame = new THREE.Group();
    this.frame.position.fromArray(this.marble.move);
    this.frame.rotation.y = rad(this.marble.turn_deg);
    this.raw = new THREE.Group();
    this.raw.quaternion.set(1, 0, 0, 0); // a half turn about x: Marble's y is down and its z is forward
    this.raw.scale.setScalar(this.marble.scale);
    this.raw.position.y = this.marble.ground;
    this.frame.add(this.raw);
    this.scene.add(this.frame);

    // Light for whoever is brought in: the set's own lamps, as the film has them.
    const air = set.world?.color || [0.5, 0.45, 0.4];
    this.scene.add(new THREE.HemisphereLight(new THREE.Color(air[0], air[1], air[2]), new THREE.Color(0.16, 0.12, 0.09), 2.2 * (set.world?.strength ?? 0.5) + 0.6));
    for (const lamp of set.lights || []) {
      const light = new THREE.PointLight(new THREE.Color(...(lamp.color || [1, 1, 1])), (lamp.power || 100) / 22, 0, 2);
      light.position.fromArray(lamp.at);
      this.scene.add(light);
    }

    this.gltf = new GLTFLoader().setDRACOLoader(new DRACOLoader().setDecoderPath("https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/libs/draco/gltf/"));
    this.clock = new THREE.Clock();
    this.frames = 0;
    this.since = performance.now();
    this.fps = null;
    this.keys = new Set();
    this.yaw = 0;
    this.pitch = 0;
    this.alive = true;
    window.forgeMarble = { settled: false, detail: null, fps: null, splats: null, seconds: null, error: null, bench: (n) => this.bench(n), eye: () => this.camera.position.toArray().map((v) => Math.round(v * 100) / 100) };

    this.resize = this.resize.bind(this);
    this.observer = new ResizeObserver(this.resize);
    this.observer.observe(this.el);
    window.addEventListener("resize", this.resize);
    this.resize();
    this.listen();
    const custom = options.get("cam")?.split(",").map(Number);
    if (custom?.length >= 6 && custom.every(Number.isFinite)) this.place(custom.slice(0, 3), custom.slice(3, 6), custom[6] || 28);
    else if (state.look) this.look(state.look);
    else this.place([0, EYE, 2], [0, 1, 0], 24);
    if (state.walking) this.setWalking(true);
    this.renderer.setAnimationLoop(() => this.frameNow());
    this.start().catch((error) => this.fail(error));
  }

  async start() {
    const began = performance.now();
    const spark = await import(SPARK);
    if (!this.alive) return;
    this.spark = spark;
    this.sparkRenderer = new spark.SparkRenderer({ renderer: this.renderer });
    this.scene.add(this.sparkRenderer);
    const waiting = [this.state.show === "mesh" ? this.setShow("mesh") : this.setDetail(this.state.detail)];
    if (this.state.who) waiting.push(this.setWho(true));
    if (this.state.solid) waiting.push(this.setSolid(true));
    await Promise.all(waiting);
    if (!this.alive) return;
    window.forgeMarble.seconds = (performance.now() - began) / 1000;
    window.forgeMarble.settled = true;
  }

  fail(error) {
    console.error(error);
    window.forgeMarble.error = String(error?.message || error);
    this.status.hidden = false;
    this.status.textContent = `The room's files aren't here. They are kept out of git, in world/marble/${this.marble.world}/ of the main checkout: start the gallery with --marble pointing at that world/marble folder.`;
  }

  // How sharp: one of the world's splat files. The old one goes when the new one is ready.
  async setDetail(key) {
    // ?file=/evidence/...: some other .spz stood in the same frame (a cut-away of the room, for a diorama picture).
    const other = this.options.get("file");
    const url = other?.startsWith("/") ? other.slice(1) : this.base + (other || this.marble.splats[key]);
    const file = url.split("/").pop();
    const asked = (this.asked = (this.asked || 0) + 1);
    this.status.hidden = false;
    this.status.textContent = "Fetching the room…";
    const head = await fetch(url, { method: "HEAD" });
    if (!head.ok) throw new Error(`${file}: ${head.status}`);
    const bytes = Number(head.headers.get("Content-Length")) || 0;
    if (bytes) this.status.textContent = `Fetching the room (${mb(bytes)})…`;
    const mesh = new this.spark.SplatMesh({ url });
    await mesh.initialized;
    if (!this.alive || asked !== this.asked) return mesh.dispose?.();
    if (this.splats) { this.raw.remove(this.splats); this.splats.dispose?.(); }
    this.splats = mesh;
    mesh.visible = this.state.show === "splats";
    this.raw.add(mesh);
    this.status.hidden = true;
    this.fps = null;
    Object.assign(window.forgeMarble, { detail: key, splats: mesh.packedSplats?.numSplats ?? mesh.numSplats ?? null, bytes, fps: null });
  }

  // The room as the blobs themselves, or as the painted mesh Blender films (sets/<set>/set.glb).
  async setShow(what) {
    if (what === "mesh" && !this.painted) {
      this.status.hidden = false;
      this.status.textContent = "Fetching the painted mesh…";
      const gltf = await this.gltf.loadAsync(`sets/${encodeURIComponent(this.set.id)}/${this.set.glb || "set.glb"}`);
      if (!this.alive) return;
      this.painted = gltf.scene;
      this.scene.add(this.painted);
      this.status.hidden = true;
    }
    if (what === "splats" && !this.splats) await this.setDetail(this.state.detail);
    if (this.painted) this.painted.visible = what === "mesh";
    if (this.splats) this.splats.visible = what === "splats";
    this.setShadow(this.state.shadow);
    this.fps = null;
  }

  // The collision mesh Marble hands over, as lines: every surface a body would be stopped by.
  async setSolid(on) {
    if (on && !this.collider) {
      const gltf = await this.gltf.loadAsync(this.base + "collider.glb");
      if (!this.alive) return;
      const lines = new THREE.MeshBasicMaterial({ color: 0x7fb2ff, wireframe: true, transparent: true, opacity: 0.35, depthWrite: false });
      gltf.scene.traverse((o) => { if (o.isMesh) o.material = lines; });
      this.collider = gltf.scene;
      this.raw.add(this.collider);
    }
    if (this.collider) this.collider.visible = on && this.state.solid;
  }

  // One of our toons, at true size, on a mark of the set.
  async setWho(on) {
    if (on && !this.who) {
      const run = this.runs.find((r) => r.id.endsWith(`-${WHO.run}`));
      const tries = WHO.files.map(([rel, at]) => [rel.startsWith("shots/") ? rel : run && `runs/${encodeURIComponent(run.id)}/${rel}`, at]).filter(([url]) => url);
      let gltf = null, at = 0;
      for (const [url, when] of tries) {
        try { gltf = await this.gltf.loadAsync(url); at = when; break; } catch { /* the next file */ }
      }
      if (!this.alive || !gltf) return;
      const body = gltf.scene;
      body.traverse((o) => {
        if ((o.userData.name || o.name).startsWith("body under")) o.visible = false; // skin that worn gear hides
        if (o.isMesh) o.frustumCulled = false;
      });
      // Stood still: the clip held at a moment he is standing, then slid so his hips are over the mark.
      if (gltf.animations[0]) {
        this.mixer = new THREE.AnimationMixer(body);
        this.mixer.clipAction(gltf.animations[0]).play();
        this.mixer.setTime(at);
      }
      body.updateMatrixWorld(true);
      const hips = body.getObjectByName("hips");
      const middle = hips ? hips.getWorldPosition(new THREE.Vector3()) : new THREE.Vector3();
      const low = new THREE.Box3().setFromObject(body, true).min.y;
      body.position.set(-middle.x, 0, -middle.z); // his height is left as the file has it: how the feet meet the floor is what we are here to see
      const mark = this.set.marks[WHO.mark] || Object.values(this.set.marks)[0];
      this.who = new THREE.Group();
      this.who.add(body);
      this.who.position.set(mark.at[0], 0, mark.at[1]);
      this.who.rotation.y = rad(mark.facing_deg);
      this.who.userData.height = new THREE.Box3().setFromObject(body, true).max.y;
      this.scene.add(this.who);
      // A soft dark patch under the feet: the least a body needs to look stood on a floor. On the painted mesh
      // it is a flat disc. The blobs cannot be drawn over (they have no surface to lie on), so there the floor's
      // own blobs are dimmed where he stands, which Spark does for us inside a squashed ball.
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 128;
      const pen = canvas.getContext("2d"), fade = pen.createRadialGradient(64, 64, 4, 64, 64, 62);
      fade.addColorStop(0, "rgba(0,0,0,0.55)");
      fade.addColorStop(0.55, "rgba(0,0,0,0.28)");
      fade.addColorStop(1, "rgba(0,0,0,0)");
      pen.fillStyle = fade;
      pen.fillRect(0, 0, 128, 128);
      this.disc = new THREE.Mesh(new THREE.CircleGeometry(0.55, 32), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 }));
      this.disc.rotation.x = -Math.PI / 2;
      this.disc.position.set(mark.at[0], 0.03, mark.at[1]);
      this.scene.add(this.disc);
      const { SplatEdit, SplatEditSdf, SplatEditSdfType, SplatEditRgbaBlendMode } = this.spark;
      this.dim = new SplatEdit({ rgbaBlendMode: SplatEditRgbaBlendMode.MULTIPLY, softEdge: 0.3 });
      const ball = new SplatEditSdf({ type: SplatEditSdfType.ELLIPSOID, color: new THREE.Color(0.32, 0.3, 0.3) });
      ball.scale.set(0.4, 0.07, 0.28);
      this.dim.add(ball);
      this.dim.position.set(mark.at[0], 0, mark.at[1]);
      this.dim.rotation.y = rad(mark.facing_deg);
      this.scene.add(this.dim);
      window.forgeMarble.who = { height_m: this.who.userData.height, lowest_m: low, at: mark.at };
    }
    if (this.who) this.who.visible = on;
    this.setShadow(this.state.shadow);
  }

  setShadow(on) {
    const cast = on && this.state.who && !!this.who;
    if (this.disc) this.disc.visible = cast && this.state.show === "mesh";
    if (this.dim) {
      if (cast && !this.dim.parent) this.scene.add(this.dim);
      if (!cast && this.dim.parent) this.scene.remove(this.dim);
    }
  }

  // Stand the camera somewhere, looking at something, through a lens (mm on a 36 mm frame, as the set's cameras are).
  place(at, aim, lens) {
    this.lens = lens;
    this.camera.position.fromArray(at);
    this.controls.target.fromArray(aim);
    this.controls.maxDistance = Math.max(14, this.camera.position.distanceTo(this.controls.target) * 1.2); // a camera asked for from far outside stays there
    this.camera.lookAt(this.controls.target);
    this.controls.update();
    this.resize();
  }

  look(name) {
    const card = this.set.cameras[name];
    if (card) this.place(card.at, card.aim, card.lens_mm);
  }

  // Walking: your own eyes at head height, the room solid around you (the set's blocks and its floor).
  setWalking(on) {
    this.controls.enabled = !on;
    this.walking = on;
    if (!on) {
      const ahead = this.camera.getWorldDirection(new THREE.Vector3());
      this.controls.target.copy(this.camera.position).addScaledVector(ahead, 2.5);
      return;
    }
    const ahead = this.camera.getWorldDirection(new THREE.Vector3());
    this.yaw = Math.atan2(-ahead.x, -ahead.z);
    this.pitch = Math.asin(THREE.MathUtils.clamp(ahead.y, -1, 1));
    const spot = this.free(this.camera.position.x, this.camera.position.z) ? [this.camera.position.x, this.camera.position.z] : (this.set.marks.centre || Object.values(this.set.marks)[0]).at;
    this.camera.position.set(spot[0], EYE, spot[1]);
    this.lens = 22;
    this.resize();
  }

  free(x, z) {
    const onFloor = (this.set.floor?.areas || []).some(([[x0, z0], [x1, z1]]) => x >= Math.min(x0, x1) + BODY && x <= Math.max(x0, x1) - BODY && z >= Math.min(z0, z1) + BODY && z <= Math.max(z0, z1) - BODY);
    if (!onFloor) return false;
    for (const block of this.set.blocks || []) {
      if (block.center[1] + block.size[1] / 2 < 0.3) continue;
      const turn = rad(block.heading), dx = x - block.center[0], dz = z - block.center[2];
      const across = dx * Math.cos(turn) - dz * Math.sin(turn), through = dx * Math.sin(turn) + dz * Math.cos(turn);
      if (Math.abs(across) < block.size[0] / 2 + BODY && Math.abs(through) < block.size[2] / 2 + BODY) return false;
    }
    if (this.who?.visible && Math.hypot(x - this.who.position.x, z - this.who.position.z) < BODY + 0.3) return false;
    return true;
  }

  listen() {
    const dom = this.renderer.domElement;
    dom.tabIndex = 0;
    dom.style.touchAction = "none";
    this.onKey = (e) => {
      if (!this.walking || e.metaKey || e.ctrlKey) return;
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      if (!["w", "a", "s", "d", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Shift"].includes(key)) return;
      if (e.type === "keydown") this.keys.add(key); else this.keys.delete(key);
      if (key !== "Shift") e.preventDefault();
    };
    window.addEventListener("keydown", this.onKey);
    window.addEventListener("keyup", this.onKey);
    const fingers = new Map();
    dom.addEventListener("pointerdown", (e) => {
      if (!this.walking) return;
      const box = dom.getBoundingClientRect();
      const stick = e.pointerType === "touch" && e.clientY > box.top + box.height / 2 && ![...fingers.values()].some((f) => f.stick);
      fingers.set(e.pointerId, { stick, x0: e.clientX, y0: e.clientY, x: e.clientX, y: e.clientY });
      dom.setPointerCapture(e.pointerId);
      if (stick) {
        this.knob = h("div", { class: "marble-stick" }, h("div", { class: "marble-knob" }));
        this.knob.style.left = `${e.clientX - box.left}px`;
        this.knob.style.top = `${e.clientY - box.top}px`;
        this.el.append(this.knob);
      }
    });
    dom.addEventListener("pointermove", (e) => {
      const finger = fingers.get(e.pointerId);
      if (!finger || !this.walking) return;
      if (finger.stick) {
        const dx = e.clientX - finger.x0, dy = e.clientY - finger.y0, far = Math.hypot(dx, dy), pull = Math.min(far, STICK_REACH) / (far || 1);
        this.push = [dx * pull / STICK_REACH, dy * pull / STICK_REACH];
        this.knob.firstChild.style.transform = `translate(${dx * pull}px, ${dy * pull}px)`;
      } else {
        this.yaw -= (e.clientX - finger.x) * 0.0042;
        this.pitch = THREE.MathUtils.clamp(this.pitch - (e.clientY - finger.y) * 0.0042, -1.2, 1.2);
      }
      finger.x = e.clientX;
      finger.y = e.clientY;
    });
    const up = (e) => {
      const finger = fingers.get(e.pointerId);
      fingers.delete(e.pointerId);
      if (finger?.stick) { this.push = null; this.knob?.remove(); this.knob = null; }
    };
    dom.addEventListener("pointerup", up);
    dom.addEventListener("pointercancel", up);
  }

  step(dt) {
    const k = this.keys;
    let side = (k.has("d") || k.has("ArrowRight") ? 1 : 0) - (k.has("a") || k.has("ArrowLeft") ? 1 : 0);
    let ahead = (k.has("w") || k.has("ArrowUp") ? 1 : 0) - (k.has("s") || k.has("ArrowDown") ? 1 : 0);
    let pace = k.has("Shift") ? RUN_MPS : WALK_MPS;
    if (this.push) { side = this.push[0]; ahead = -this.push[1]; pace = Math.hypot(side, ahead) > 0.86 ? RUN_MPS : WALK_MPS; }
    const far = Math.hypot(side, ahead);
    if (far > 0.05) {
      const go = Math.min(far, 1) * pace * dt / far;
      const dx = (side * Math.cos(this.yaw) - ahead * Math.sin(this.yaw)) * go, dz = (-side * Math.sin(this.yaw) - ahead * Math.cos(this.yaw)) * go;
      const p = this.camera.position;
      if (this.free(p.x + dx, p.z)) p.x += dx; // one way at a time, so a wall is slid along, not stuck to
      if (this.free(p.x, p.z + dz)) p.z += dz;
    }
    this.camera.rotation.set(this.pitch, this.yaw, 0, "YXZ");
  }

  resize() {
    const wide = this.el.clientWidth, tall = this.el.clientHeight;
    if (!wide || !tall) return;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); // a window dragged to another screen changes this
    this.renderer.setSize(wide, tall, false);
    this.camera.aspect = wide / tall;
    // A set's camera frames 16:9. On a narrower pane, keep what it sees from side to side.
    const half = Math.atan(SENSOR_MM / 2 / this.lens);
    const shape = Math.min(this.camera.aspect, FILM);
    this.camera.fov = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(half) / shape));
    this.camera.updateProjectionMatrix();
  }

  frameNow() {
    const dt = Math.min(this.clock.getDelta(), 0.1);
    if (this.walking) this.step(dt); else this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this.frames += 1;
    const now = performance.now();
    if (now - this.since >= 1000) {
      const fps = this.frames * 1000 / (now - this.since);
      this.fps = this.fps === null ? fps : this.fps * 0.5 + fps * 0.5;
      this.frames = 0;
      this.since = now;
      window.forgeMarble.fps = Math.round(this.fps * 10) / 10;
      const count = window.forgeMarble.splats;
      this.say(window.forgeMarble.settled ? `${Math.round(this.fps)} pictures a second${this.state.show === "splats" && count ? ` · ${count.toLocaleString()} dots` : ""}` : "");
    }
  }

  // How long one picture really takes, drawn back to back with the GPU made to finish each: a screen shows at
  // most 60 (or 120) a second, so the count on the page cannot say how much is to spare. Milliseconds a picture.
  bench(pictures = 40) {
    const gl = this.renderer.getContext(), px = new Uint8Array(4);
    const draw = () => { this.renderer.render(this.scene, this.camera); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); };
    for (let i = 0; i < 5; i++) draw();
    const began = performance.now();
    for (let i = 0; i < pictures; i++) draw();
    return (performance.now() - began) / pictures;
  }

  dispose() {
    this.alive = false;
    this.renderer.setAnimationLoop(null);
    this.observer.disconnect();
    window.removeEventListener("resize", this.resize);
    window.removeEventListener("keydown", this.onKey);
    window.removeEventListener("keyup", this.onKey);
    this.controls.dispose();
    this.splats?.dispose?.();
    this.scene.traverse((o) => {
      o.geometry?.dispose?.();
      for (const m of [].concat(o.material || [])) { m.map?.dispose?.(); m.dispose?.(); }
    });
    this.renderer.dispose();
    this.renderer.forceContextLoss?.();
    this.el.remove();
  }
}
