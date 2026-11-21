// Forge gallery: the newest diorama out front, the world seen whole, the shelf of runs, a before/after viewer for each, and the sets they are filmed on.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { clone as cloneSkinned } from "three/addons/utils/SkeletonUtils.js";

const app = document.getElementById("app");
const VERSION_NAMES = { raw: "Raw TRELLIS.2", hero: "Hero", quads: "Quads", web: "Web", game: "Game", mobile: "Mobile", midpoly: "Mid poly", lowpoly: "Low poly" };
const SOCKET_NAMES = { hand_right: "right hand", hand_left: "left hand", head: "head", back: "back", hip: "hip" };
const RAW_WIREFRAME_LIMIT = 400000; // triangles; above this the raw wireframe is too heavy for a phone

const draco = new DRACOLoader().setDecoderPath("https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/libs/draco/gltf/");
const loader = new GLTFLoader().setDRACOLoader(draco);
const cache = new Map();
const load = (url) => {
  if (!cache.has(url)) cache.set(url, loader.loadAsync(url));
  return cache.get(url);
};

let runs = [];
let sets = [];
let takes = [];
let comics = [];
let dioramas = [];
let world = null;
let viewer = null;

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
const file = (run, rel) => `runs/${encodeURIComponent(run.id)}/${rel}`;
const mb = (bytes) => (bytes ? `${(bytes / 1e6).toFixed(bytes < 1e6 ? 2 : 1)} MB` : "—");
const num = (n) => (n || n === 0 ? n.toLocaleString() : "—");

// ---------- the shelf ----------

function shelf() {
  const objects = runs.length
    ? h("div", { class: "shelf" }, runs.map((run) =>
      h("a", { class: "card clay-surface", href: `#/run/${encodeURIComponent(run.id)}` },
        run.card || run.portrait || run.render || run.picture ? h("img", { src: file(run, run.card || run.portrait || run.render || run.picture), alt: "", loading: "lazy" }) : null,
        h("div", { class: "label" },
          h("h2", {}, run.name),
          h("p", {}, `${run.profiles.length ? `${run.profiles.length} versions` : "raw mesh only"} · ${run.made.slice(0, 10)}`),
        ),
      ),
    ))
    : h("p", { class: "empty" }, "Nothing here yet. Run ", h("code", {}, 'just make "an idea"'), " and reload.");
  if (!sets.length) return objects;
  // A set is a place of our own to film in: built once, shot many times.
  return h("div", {},
    objects,
    h("section", { class: "sets" },
      h("h2", {}, "Places"),
      h("p", { class: "lede" }, "Each place on its own. It is built once and keeps its marks, cameras and lights, so a new shot only needs to say who stands where."),
      h("div", { class: "shelf" }, sets.map((set) => {
        const marks = Object.keys(set.marks || {}).length, cameras = Object.keys(set.cameras || {}).length;
        const filmed = takes.filter((t) => t.set === set.id).length;
        return h("a", { class: "card wide clay-surface", href: `#/set/${encodeURIComponent(set.id)}` },
          set.picture ? h("img", { src: `sets/${set.id}/${set.picture}`, alt: "", loading: "lazy" }) : null,
          h("div", { class: "label" },
            h("h2", {}, set.title || set.name),
            h("p", {}, `${marks} marks · ${cameras ? `${cameras} cameras` : "a camera that follows"}${filmed ? ` · ${filmed} ${filmed > 1 ? "shots" : "shot"} to play` : ""}`),
          ),
        );
      })),
    ),
  );
}

// ---------- one set ----------

const MARK_WORDS = { stand: "stand here", sit: "sit here", touch: "stand here, hand out", lean: "stand here, hand on it" };

function setPage(set, wantedTake, wantedCamera) {
  const filmed = takes.filter((t) => t.set === set.id);
  const cameraNames = Object.keys(set.cameras || {});
  // Marks and cameras show from the start: they are what the page is for. What is heavier, or only for
  // checking (the boxes people are kept out of, a shot's characters), waits until it is asked for.
  // A link can open a shot already playing, through a camera: #/set/<set>/<shot>/<camera>.
  const state = { marks: true, cameras: true, blocks: false, off: new Set(), take: filmed.find((t) => t.id === wantedTake) || null, look: null };
  state.look = cameraNames.includes(wantedCamera) ? wantedCamera : state.take && cameraNames.length ? cameraNames[0] : null;
  if (state.take) state.marks = false;
  const link = () => history.replaceState(null, "", `#/set/${encodeURIComponent(set.id)}${state.take ? `/${encodeURIComponent(state.take.id)}${state.look ? `/${state.look}` : ""}` : ""}`);
  const stage = h("div", { class: "stage set-stage clay-well" });
  const press = (btn, on) => btn.setAttribute("aria-pressed", String(on));
  const toggle = (label, key, apply) => {
    const btn = h("button", { class: "toggle clay-button clay-button--soft", type: "button", "aria-pressed": String(state[key]), onclick: () => { state[key] = !state[key]; press(btn, state[key]); apply(state[key]); } }, label);
    return btn;
  };
  const marksBtn = toggle("Marks", "marks", (on) => viewer?.show("marks", on));
  const camsBtn = toggle("Cameras", "cameras", (on) => viewer?.show("cameras", on));
  const blocksBtn = toggle("What's in the way", "blocks", (on) => viewer?.show("blocks", on));
  // Look through one of the set's fixed cameras, or walk around freely.
  const looks = [[null, "Look around"], ...cameraNames.map((name) => [name, name[0].toUpperCase() + name.slice(1)])];
  const lookChips = looks.map(([name, label]) =>
    h("button", { class: "chip clay-chip", type: "button", "aria-pressed": String(state.look === name), onclick: () => look(name) }, label));
  function look(name) {
    state.look = name;
    lookChips.forEach((chip, i) => press(chip, looks[i][0] === name));
    viewer?.look(name);
    showFilm();
    link();
  }
  // Dressing is kept apart from the set, so any piece can be taken away.
  const dressing = (set.dressing || []).map((item) => {
    const chip = h("button", { class: "chip clay-chip", type: "button", "aria-pressed": "true", title: `on the ${item.slot.replace(/_/g, " ")}`, onclick: () => {
      if (state.off.has(item.prop)) state.off.delete(item.prop); else state.off.add(item.prop);
      press(chip, !state.off.has(item.prop));
      viewer?.setDressing(state.off);
    } }, item.prop);
    return chip;
  });
  // A shot filmed here: pressed in, its characters come onto the set and play it, over and over.
  const film = h("div", { class: "film" });
  const takeBtns = filmed.map((take) => {
    const btn = h("button", { class: "toggle clay-button clay-button--soft", type: "button", "aria-pressed": String(state.take === take), onclick: () => {
      state.take = state.take === take ? null : take;
      takeBtns.forEach((b, i) => press(b, filmed[i] === state.take));
      // While a shot plays the marks step aside (press Marks to see them under the cast); they come back after.
      state.marks = !state.take;
      press(marksBtn, state.marks);
      viewer?.show("marks", state.marks);
      viewer?.play(state.take);
      if (state.take && !state.look && cameraNames.length) look(cameraNames[0]); else { showFilm(); link(); }
    } }, `Play: ${take.title}`);
    return btn;
  });
  function showFilm() {
    const take = state.take;
    const mp4 = take && state.look && take.films[state.look];
    if (!take) return film.replaceChildren();
    const shake = take.handshakes[0];
    film.replaceChildren(
      h("p", { class: "about" }, `${take.about || ""} ${Math.round(take.seconds)} seconds, played by ${take.roles.map((r) => r.character.replace(/^[0-9T-]+-/, "").replace(/-/g, " ")).join(" and ")}.${shake ? ` In the handshake their palms are ${shake.palms_apart_cm.typical} cm apart.` : ""}`),
      mp4 ? h("figure", { class: "clay-surface" },
        h("video", { src: `shots/${take.id}/${mp4}`, controls: true, loop: true, muted: true, playsinline: true, preload: "none" }),
        h("figcaption", {}, `The same take as Blender filmed it, from the ${state.look} camera.`)) : null,
    );
  }

  // A stage whose backdrop can be swapped: each choice is a real place in the world.
  const behind = set.backdrop_options?.options || [];
  const behindChips = behind.map((option) => h("button", { class: "chip clay-chip", type: "button", "aria-pressed": String(option.image === set.backdrop?.image), onclick: () => {
    behindChips.forEach((chip, i) => press(chip, behind[i] === option));
    viewer?.setBackdrop(option.image);
  } }, option.title));
  const marks = Object.entries(set.marks || {});
  const inWorld = world?.epochs?.length ? Object.entries(world.epochs[world.epochs.length - 1].places).find(([, p]) => p.set === set.id) : null;
  const page = h("article", { class: "object" },
    inWorld ? h("a", { class: "back", href: `#/world/${world.epochs[world.epochs.length - 1].name}/${encodeURIComponent(inWorld[0])}` }, "← The world") : h("a", { class: "back", href: "#/" }, "← Everything"),
    h("h1", {}, set.title || set.name),
    set.about ? h("p", { class: "lede" }, set.about) : null,
    h("div", { class: "versions", role: "group", "aria-label": "Look from" }, lookChips),
    h("div", { class: "controls" }, h("div", { class: "toggles" }, marksBtn, cameraNames.length ? camsBtn : null, blocksBtn, takeBtns)),
    dressing.length ? h("div", { class: "gear", role: "group", "aria-label": "Dressing" }, h("span", { class: "hint" }, "Dressing"), dressing, h("span", { class: "hint" }, "Tap a piece to take it away.")) : null,
    behind.length ? h("div", { class: "gear", role: "group", "aria-label": "Through the window" }, h("span", { class: "hint" }, "Through the window"), behindChips) : null,
    stage,
    film,
    h("section", { class: "making" },
      h("h2", {}, "What's here"),
      h("div", { class: "notes clay-surface" }, h("h3", {}, "Marks"), h("ul", {}, marks.map(([name, m]) =>
        h("li", {}, h("strong", {}, name.replace(/_/g, " ")), ` · ${MARK_WORDS[m.kind] || m.kind}${m.about ? `. ${m.about[0].toUpperCase()}${m.about.slice(1)}.` : ""}`)))),
      cameraNames.length ? h("div", { class: "notes clay-surface" }, h("h3", {}, "Cameras"), h("ul", {}, cameraNames.map((name) =>
        h("li", {}, h("strong", {}, name), ` · ${set.cameras[name].about || ""}, ${set.cameras[name].lens_mm} mm`))),
        h("p", { class: "hint" }, "They never move. One take is filmed from all of them at once, and the cut is picked afterwards.")) : null,
      set.backdrop ? h("div", { class: "pictures" }, h("figure", { class: "clay-surface" },
        h("img", { class: "backdrop", src: `sets/${set.id}/${set.backdrop.image}`, alt: "The painted backdrop", loading: "lazy" }),
        h("figcaption", {}, `The backdrop: ${set.backdrop.about || "a painted picture"}. Nothing behind the set is modelled.`))) : null,
    ),
  );
  queueMicrotask(() => { viewer?.dispose(); viewer = new SetViewer(stage, set, state); showFilm(); });
  return page;
}

// The 3D view of a set: the set, its backdrop and dressing, markers for marks and cameras, and (when asked) a
// shot's characters playing on it. A set is written y-up in metres, the way a .glb is, so nothing is turned.
class SetViewer {
  constructor(stage, set, state) {
    this.stage = stage;
    this.set = set;
    stage.replaceChildren();
    this.el = h("div", { class: "pane" });
    this.status = h("div", { class: "status" }, "Loading…");
    this.el.append(this.status);
    stage.append(this.el);
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    const air = set.world?.color || [0.92, 0.9, 0.86];
    this.renderer.setClearColor(new THREE.Color(air[0], air[1], air[2]).convertLinearToSRGB());
    this.el.prepend(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.scene.environment = new THREE.PMREMGenerator(this.renderer).fromScene(new RoomEnvironment(), 0.04).texture;
    this.free = new THREE.PerspectiveCamera(36, 16 / 9, 0.05, 400);
    this.camera = this.free;
    this.controls = new OrbitControls(this.free, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.addEventListener("change", () => this.draw());
    this.groups = { marks: this.markMarkers(), cameras: this.cameraMarkers(), blocks: this.blockLines() };
    for (const [key, group] of Object.entries(this.groups)) { group.visible = state[key]; this.scene.add(group); }
    this.fixed = {};
    for (const [name, card] of Object.entries(set.cameras || {})) {
      // A lens on a 36 mm wide sensor, in a 16:9 picture.
      const cam = new THREE.PerspectiveCamera(THREE.MathUtils.radToDeg(2 * Math.atan(36 / (16 / 9) / 2 / card.lens_mm)), 16 / 9, 0.05, 400);
      cam.position.fromArray(card.at);
      cam.lookAt(new THREE.Vector3().fromArray(card.aim));
      this.fixed[name] = cam;
    }
    this.dressing = [];
    this.cast = [];
    this.resize = new ResizeObserver(() => this.layout());
    this.resize.observe(this.el);
    this.fill(state);
    this.layout();
  }

  async fill(state) {
    const { set } = this;
    try {
      const box = new THREE.Box3();
      if (set.glb) {
        const model = (await load(`sets/${set.id}/${set.glb}`)).scene.clone(true);
        const move = set.geometry?.move || [0, 0, 0];
        model.position.fromArray(move);
        model.rotation.y = THREE.MathUtils.degToRad(set.geometry?.turn_deg || 0);
        this.scene.add(model);
      }
      if (set.ground) {
        const ground = new THREE.Mesh(new THREE.PlaneGeometry(set.ground.size_m || 40, set.ground.size_m || 40), new THREE.MeshStandardMaterial({ color: new THREE.Color(...(set.ground.color || [0.8, 0.78, 0.74])), roughness: 0.9 }));
        ground.rotation.x = -Math.PI / 2;
        ground.position.y = (set.ground.y || 0) - 0.004;
        this.scene.add(ground);
      }
      if (set.backdrop) {
        const picture = await new THREE.TextureLoader().loadAsync(`sets/${set.id}/${set.backdrop.image}`);
        picture.colorSpace = THREE.SRGBColorSpace;
        const flat = new THREE.Mesh(new THREE.PlaneGeometry(set.backdrop.width_m, set.backdrop.height_m), new THREE.MeshBasicMaterial({ map: picture, toneMapped: false }));
        flat.position.fromArray(set.backdrop.center);
        flat.rotation.y = THREE.MathUtils.degToRad(set.backdrop.heading || 0);
        this.scene.add(flat);
        this.backdrop = flat;
      }
      for (const sign of set.signs || []) {
        // A sign is a small painted flat that is part of the place: a shop sign, a wall painting.
        const picture = await new THREE.TextureLoader().loadAsync(`sets/${set.id}/${sign.image}`);
        picture.colorSpace = THREE.SRGBColorSpace;
        const flat = new THREE.Mesh(new THREE.PlaneGeometry(sign.width_m, sign.height_m), new THREE.MeshBasicMaterial({ map: picture, toneMapped: false }));
        flat.position.fromArray(sign.center);
        flat.rotation.y = THREE.MathUtils.degToRad(sign.heading || 0);
        this.scene.add(flat);
      }
      for (const item of set.dressing || []) {
        const slot = set.slots[item.slot];
        const prop = (await load(`sets/${set.id}/${item.detail || item.glb}`)).scene.clone(true);
        prop.position.fromArray(slot.at);
        prop.rotation.y = THREE.MathUtils.degToRad(slot.heading || 0);
        prop.userData.prop = item.prop;
        this.dressing.push(prop);
        this.scene.add(prop);
      }
      this.setDressing(state.off);
      for (const light of set.lights || []) {
        const lamp = new THREE.DirectionalLight(new THREE.Color(...(light.color || [1, 1, 1])), light.kind === "sun" ? 1.4 : 0.9);
        lamp.position.fromArray(light.at);
        lamp.target.position.fromArray(light.aim || [0, 0, 0]);
        this.scene.add(lamp, lamp.target);
      }
      // Start with the whole set in view, from out front and a little above.
      // (Framed on where people stand, not on the walls: a stage's walls run well past what the cameras see.)
      for (const m of Object.values(set.marks || {})) box.expandByPoint(new THREE.Vector3(m.at[0], 0, m.at[1])).expandByPoint(new THREE.Vector3(m.at[0], 1.8, m.at[1]));
      const centre = box.getCenter(new THREE.Vector3());
      const size = Math.max(box.getSize(new THREE.Vector3()).length(), 4);
      this.free.position.set(centre.x + size * 0.4, size * 0.6, centre.z + size * 1.45);
      this.controls.target.set(centre.x, 0.8, centre.z);
      this.controls.update();
      this.status.remove();
      if (state.look) this.look(state.look);
      if (state.take) this.play(state.take);
      this.draw();
    } catch (err) {
      this.status.textContent = "Couldn't load this set.";
      console.error(err);
    }
  }

  // A ball on the floor (or on the seat) at every mark, a short line the way it faces, and its name.
  markMarkers() {
    const group = new THREE.Group();
    const blue = new THREE.MeshBasicMaterial({ color: 0x44679b, depthTest: false });
    const line = new THREE.LineBasicMaterial({ color: 0x44679b, depthTest: false });
    for (const [name, m] of Object.entries(this.set.marks || {})) {
      const y = m.kind === "sit" ? m.seat_height_m : 0.02;
      const at = new THREE.Vector3(m.at[0], y, m.at[1]);
      const dot = new THREE.Mesh(new THREE.SphereGeometry(0.06, 16, 12), blue);
      dot.position.copy(at);
      dot.renderOrder = 2;
      const a = THREE.MathUtils.degToRad(m.facing_deg || 0);
      const way = new THREE.Line(new THREE.BufferGeometry().setFromPoints([at, at.clone().add(new THREE.Vector3(Math.sin(a) * 0.4, 0, Math.cos(a) * 0.4))]), line);
      way.renderOrder = 2;
      const label = labelSprite(name.replace(/_/g, " "));
      label.position.copy(at).add(new THREE.Vector3(0, 0.34, 0));
      label.scale.multiplyScalar(0.24);
      group.add(dot, way, label);
      if (m.touch) {
        const hand = new THREE.Mesh(new THREE.SphereGeometry(0.035, 12, 8), new THREE.MeshBasicMaterial({ color: 0xc2703d, depthTest: false }));
        hand.position.fromArray(m.touch.at);
        hand.renderOrder = 2;
        group.add(hand);
      }
    }
    return group;
  }

  // Each fixed camera: a small box where it stands, a line to what it aims at, and its name.
  cameraMarkers() {
    const group = new THREE.Group();
    const ink = new THREE.MeshBasicMaterial({ color: 0x1c1917 });
    for (const [name, card] of Object.entries(this.set.cameras || {})) {
      const body = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.2, 0.36), ink);
      body.position.fromArray(card.at);
      body.lookAt(new THREE.Vector3().fromArray(card.aim));
      const aim = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3().fromArray(card.at), new THREE.Vector3().fromArray(card.aim)]),
        new THREE.LineDashedMaterial({ color: 0x1c1917, dashSize: 0.2, gapSize: 0.15, transparent: true, opacity: 0.45 }));
      aim.computeLineDistances();
      const label = labelSprite(`${name} camera`);
      label.position.fromArray(card.at).add(new THREE.Vector3(0, 0.36, 0));
      label.scale.multiplyScalar(0.34);
      group.add(body, aim, label);
    }
    return group;
  }

  // The boxes people are kept out of, as outlines. Each counts as solid from the floor to its top.
  blockLines() {
    const group = new THREE.Group();
    const material = new THREE.LineBasicMaterial({ color: 0xc2703d });
    for (const block of this.set.blocks || []) {
      const top = block.center[1] + block.size[1] / 2;
      if (top < 0.05) continue;
      const lines = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(block.size[0], top, block.size[2])), material);
      lines.position.set(block.center[0], top / 2, block.center[2]);
      lines.rotation.y = THREE.MathUtils.degToRad(block.heading || 0);
      group.add(lines);
    }
    return group;
  }

  // Hang another picture where the backdrop is (the ninja's stage: any place in the world, behind the sitter).
  async setBackdrop(image) {
    if (!this.backdrop) return;
    const picture = await new THREE.TextureLoader().loadAsync(`sets/${this.set.id}/${image}`);
    picture.colorSpace = THREE.SRGBColorSpace;
    this.backdrop.material.map = picture;
    this.backdrop.material.needsUpdate = true;
    this.draw();
  }

  show(key, on) { this.groups[key].visible = on && !(key === "cameras" && this.camera !== this.free); this.shown = { ...(this.shown || {}), [key]: on }; this.draw(); }

  setDressing(off) { this.dressing.forEach((prop) => { prop.visible = !off.has(prop.userData.prop); }); this.draw(); }

  // Through a fixed camera (which cannot be moved), or back to walking around.
  look(name) {
    this.camera = (name && this.fixed[name]) || this.free;
    this.controls.enabled = this.camera === this.free;
    this.groups.cameras.visible = this.camera === this.free && (this.shown?.cameras ?? true);
    this.draw();
  }

  // Bring a take's characters onto the set and play it. Each character's file plays the motion at its own
  // size; dividing by that size puts everyone on the same marks. One clock drives them all.
  async play(take) {
    this.cast.forEach((c) => { c.mixer.stopAllAction(); this.scene.remove(c.holder); });
    this.cast = [];
    this.take = take;
    if (!take) return this.draw();
    this.status.textContent = "Bringing the cast on…";
    this.el.append(this.status);
    try {
      for (const role of take.roles) {
        const gltf = await load(`shots/${take.id}/${role.glb}`);
        if (this.take !== take) return;
        const holder = new THREE.Group();
        holder.scale.setScalar(1 / (role.size || 1));
        holder.add(gltf.scene);
        this.scene.add(holder);
        const mixer = new THREE.AnimationMixer(gltf.scene);
        const clip = gltf.animations[0];
        if (clip) mixer.clipAction(clip).play();
        this.cast.push({ holder, mixer, seconds: clip ? clip.duration : 0 });
      }
    } catch (err) {
      this.status.textContent = "Couldn't load this shot.";
      console.error(err);
      return;
    }
    this.status.remove();
    const length = Math.max(...this.cast.map((c) => c.seconds), 0.1);
    const began = performance.now();
    const step = (now) => {
      if (this.take !== take || this.gone) return;
      const t = ((now - began) / 1000) % length;
      this.cast.forEach((c) => c.mixer.setTime(Math.min(t, c.seconds)));
      this.draw();
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  layout() {
    const { width, height } = this.el.getBoundingClientRect();
    if (!width || !height) return;
    this.renderer.setSize(width, height, false);
    this.free.aspect = width / height;
    this.free.updateProjectionMatrix();
    this.draw();
  }

  draw() {
    if (this.pending) return;
    this.pending = requestAnimationFrame(() => { this.pending = null; this.renderer.render(this.scene, this.camera); });
  }

  dispose() {
    this.gone = true;
    this.take = null;
    this.cast.forEach((c) => c.mixer.stopAllAction());
    this.resize.disconnect();
    this.controls.dispose();
    this.renderer.dispose();
  }
}

// ---------- the world ----------
// Every place on one ground, seen whole: like the full miniature set of a stop-motion film. An epoch is the
// whole world at one moment; the timeline steps through the ones that have been saved.

const deg = (d) => THREE.MathUtils.degToRad(d || 0);
const words = (name) => name.replace(/[_-]/g, " ");

function worldCard() {
  if (!world?.epochs?.length) return null;
  const now = world.epochs[world.epochs.length - 1];
  const places = Object.values(now.places).filter((p) => !p.inside);
  const peek = sets.find((s) => s.id === "boxing-house" && s.picture) || sets.find((s) => places.some((p) => p.set === s.id) && s.picture);
  return h("a", { class: "card world-card clay-surface", href: "#/world" },
    h("div", { class: "peek" }, peek ? h("img", { src: `sets/${peek.id}/${peek.picture}`, alt: "", loading: "lazy" }) : null),
    h("div", { class: "label" },
      h("h2", {}, world.title || "The world"),
      h("p", {}, `See every place at once · ${places.length} places, ${now.toons.length} toons at home`),
      h("span", { class: "go" }, "Look around →"),
    ),
  );
}

function worldPage(wantedEpoch, wantedPlace, wantedWalker) {
  const epoch = world.epochs.find((e) => e.name === wantedEpoch) || world.epochs.find((e) => e.name === world.now) || world.epochs[world.epochs.length - 1];
  const state = { place: epoch.places[wantedPlace] ? wantedPlace : null, marks: false, walking: false };
  const press = (btn, on) => btn.setAttribute("aria-pressed", String(on));
  const link = () => history.replaceState(null, "", `#/world/${epoch.name}${state.walking ? "/walk" : state.place ? `/${encodeURIComponent(state.place)}` : ""}`);
  const stage = h("div", { class: "stage world-stage clay-well" });
  const card = h("div", {});
  const loadLine = h("p", { class: "load-line" });
  // The timeline: every saved epoch, and room for the next.
  const at = world.epochs.indexOf(epoch);
  const go = (e) => { location.hash = `#/world/${e.name}`; };
  const timeline = h("div", { class: "timeline", role: "group", "aria-label": "Epochs" },
    world.epochs.length > 1 ? h("button", { class: "chip clay-chip step", type: "button", disabled: at === 0, "aria-label": "Earlier", onclick: () => go(world.epochs[at - 1]) }, "←") : null,
    world.epochs.map((e) => h("button", { class: "chip clay-chip", type: "button", "aria-pressed": String(e === epoch), onclick: () => go(e) }, `Epoch ${e.number} · ${e.title}`)),
    world.epochs.length > 1 ? h("button", { class: "chip clay-chip step", type: "button", disabled: at === world.epochs.length - 1, "aria-label": "Later", onclick: () => go(world.epochs[at + 1]) }, "→") : null,
    h("button", { class: "chip clay-chip", type: "button", disabled: true, title: "Saved when the world next changes" }, `Epoch ${world.epochs[world.epochs.length - 1].number + 1} · not yet`),
  );
  const placeNames = Object.keys(epoch.places);
  const chips = [[null, "The whole world"], ...placeNames.map((name) => [name, epoch.places[name].label || words(name)])];
  const chipEls = chips.map(([name, label]) => h("button", { class: "chip clay-chip", type: "button", "aria-pressed": String(state.place === name), onclick: () => choose(name) }, label));
  function choose(name, jump = false) {
    if (state.walking) walk(false);
    state.place = name;
    chipEls.forEach((chip, i) => press(chip, chips[i][0] === name));
    viewer?.goTo(name, jump);
    showCard();
    link();
  }
  function showCard() {
    const place = state.place && epoch.places[state.place];
    if (!place) {
      return card.replaceChildren(h("div", { class: "place-card clay-surface" },
        h("h2", {}, `Epoch ${epoch.number}: ${epoch.title}`),
        h("p", {}, "Tap a place to go there. Drag to walk round it, pinch or scroll to come closer."),
      ));
    }
    const set = sets.find((s) => s.id === place.set) || {};
    const marks = Object.keys(set.marks || {}).length, cameras = Object.keys(set.cameras || {}).length;
    const filmed = takes.filter((t) => t.set === set.id).length;
    const here = epoch.toons.filter((t) => t.place === state.place).map((t) => t.name);
    const things = epoch.artifacts.filter((a) => a.place === state.place || epoch.toons.some((t) => t.toon === a.held_by && t.place === state.place));
    const marksBtn = h("button", { class: "toggle clay-button clay-button--soft", type: "button", "aria-pressed": String(state.marks), onclick: () => { state.marks = !state.marks; press(marksBtn, state.marks); viewer?.showMarks(state.marks); } }, "Marks");
    card.replaceChildren(h("div", { class: "place-card clay-surface" },
      h("h2", {}, place.label || set.title || words(state.place)),
      h("p", {}, place.about || set.about || ""),
      here.length ? h("p", { class: "who" }, h("strong", {}, "Here now: "), here.join(", "), ".") : null,
      things.map((a) => h("p", { class: "who" }, h("strong", {}, `${a.title}. `), a.about, ` ${a.whose}.`)),
      h("div", { class: "actions" },
        h("a", { class: "clay-button", href: `#/set/${encodeURIComponent(place.set)}` }, "Open this place"),
        marks ? marksBtn : null,
        h("span", { class: "hint" }, `${marks} marks · ${cameras ? `${cameras} cameras` : "a camera that follows"}${filmed ? ` · ${filmed} ${filmed > 1 ? "shots" : "shot"} to play` : ""}`),
      ),
    ));
  }
  // Walk around: steer a toon through the world yourself (walkabout.js, fetched when this is first pressed).
  const walkBtn = h("button", { class: "clay-button", type: "button", onclick: () => walk(!state.walking) }, "Walk around");
  const walkNote = h("span", { class: "hint" }, "Steer Roosevelt round the world yourself.");
  const walkBar = h("div", { class: "walk-bar" }, walkBtn, walkNote);
  async function walk(on) {
    if (on === state.walking) return;
    state.walking = on;
    walkBar.hidden = on; // while walking, the one way out is "Stop walking" on the picture itself
    walkNote.textContent = "Steer Roosevelt round the world yourself.";
    link();
    if (!on) {
      const here = state.place;
      viewer?.walkabout?.stop();
      return choose(here); // the view from above, at the place you walked to
    }
    try {
      stage.scrollIntoView({ block: "center", behavior: "smooth" });
      await walkAround(viewer, epoch, wantedWalker, {
        onStop: () => walk(false),
        onPlace: (name) => { state.place = name; chipEls.forEach((chip, i) => press(chip, chips[i][0] === name)); viewer?.arrive(name); showCard(); },
      });
      if (!state.walking) viewer?.walkabout?.stop(); // stopped while it was still fetching
    } catch (err) {
      console.error(err);
      state.walking = false;
      walkBar.hidden = false;
      walkNote.textContent = "Couldn't start the walk: nobody here has a walk and a run to load.";
      link();
    }
  }
  const page = h("article", { class: "object" },
    h("a", { class: "back", href: "#/" }, "← Everything"),
    h("h1", {}, world.title || "The world"),
    world.about ? h("p", { class: "lede" }, world.about) : null,
    timeline,
    h("p", { class: "caption" }, epoch.caption),
    h("div", { class: "places", role: "group", "aria-label": "Places" }, chipEls),
    walkBar,
    stage,
    card,
    loadLine,
  );
  queueMicrotask(() => {
    viewer?.dispose();
    viewer = new WorldViewer(stage, epoch, state, { onPick: (name) => choose(name), onLoad: (text) => { loadLine.textContent = text; } });
    showCard();
    if (wantedPlace === "walk") walk(true); // #/world/<epoch>/walk
  });
  return page;
}

// A miniature: something small to look at from outside. Orbit, zoom, a camera that can fly from one view to
// another, and a count of what was fetched. The world view is one. One combined .glb is another (a diorama on
// its plinth): `new Miniature(stage).show("dioramas/meet-the-cast/diorama.glb")` is the whole of it, and
// DioramaViewer, below, adds the front page's manners: a gentle first angle and a slow idle turn.
class Miniature {
  constructor(stage, { status = "Loading…", hint = null, background = 0xe9e4da } = {}) {
    this.fetched = new Set();
    stage.replaceChildren();
    this.el = h("div", { class: "pane" });
    this.status = h("div", { class: "status" }, status);
    this.el.append(this.status, hint ? h("div", { class: "hint" }, hint) : "");
    stage.append(this.el);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.setClearColor(background);
    this.el.prepend(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.scene.environment = new THREE.PMREMGenerator(this.renderer).fromScene(new RoomEnvironment(), 0.04).texture;
    const sun = new THREE.DirectionalLight(0xfff4e0, 1.6);
    sun.position.set(-30, 50, 30);
    this.scene.add(sun);
    this.camera = new THREE.PerspectiveCamera(32, 16 / 10, 0.5, 600);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.maxPolarAngle = Math.PI / 2 - 0.06; // never under the floor
    this.controls.addEventListener("change", () => this.draw());
    this.controls.addEventListener("start", () => { this.touched = true; this.flight = null; });
    this.resize = new ResizeObserver(() => this.layout());
    this.resize.observe(this.el);
    this.layout();
  }

  get(url) { this.fetched.add(url); return load(url); }

  async picture(url) {
    this.fetched.add(url);
    const texture = await new THREE.TextureLoader().loadAsync(url);
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
  }

  // One .glb, whole, framed from a little above. Returns what was added.
  async show(url) {
    try {
      const model = (await this.get(url)).scene.clone(true);
      this.scene.add(model);
      this.all = new THREE.Box3().setFromObject(model);
      this.camera.near = Math.max(0.01, this.all.getSize(new THREE.Vector3()).length() / 200);
      this.camera.updateProjectionMatrix();
      this.fly(...this.home(), true);
      this.status.remove();
      return model;
    } catch (err) {
      this.status.textContent = "Couldn't load this.";
      console.error(err);
      return null;
    }
  }

  // How far back the camera stands to hold something `across` metres wide, on this screen.
  back(across) {
    const half = deg(this.camera.fov / 2);
    return (across / 2) / Math.tan(half) / Math.min(1, this.camera.aspect);
  }

  // All of it (`this.all`, a box), from a little above: like looking down at a studio's miniature set.
  home() {
    const centre = this.all.getCenter(new THREE.Vector3()), size = this.all.getSize(new THREE.Vector3());
    const d = this.back(Math.max(size.x, size.z * 1.2, size.y * 1.4) * 0.86);
    return [new THREE.Vector3(centre.x + d * 0.22, this.all.min.y + d * 0.55, centre.z + d * 0.8), new THREE.Vector3(centre.x, this.all.min.y + size.y * 0.25, centre.z)];
  }

  // Move the camera to a view: at once, or gliding there.
  fly(toPos, toAim, jump = false) {
    const fromPos = this.camera.position.clone(), fromAim = this.controls.target.clone();
    const began = performance.now(), time = jump || !this.moved ? 0 : 750;
    this.moved = true;
    const flight = (this.flight = {});
    const step = (now) => {
      if (this.flight !== flight || this.gone) return;
      const t = time ? Math.min(1, (now - began) / time) : 1;
      const k = t * t * (3 - 2 * t); // ease in and out
      this.camera.position.lerpVectors(fromPos, toPos, k);
      this.controls.target.lerpVectors(fromAim, toAim, k);
      this.controls.update();
      this.draw();
      if (t < 1) requestAnimationFrame(step);
    };
    step(performance.now());
  }

  // How much was fetched so far.
  loadedSoFar() {
    const sizes = new Map(performance.getEntriesByType("resource").map((r) => [new URL(r.name).pathname, r.encodedBodySize || r.transferSize || 0]));
    let bytes = 0;
    for (const url of this.fetched) bytes += sizes.get(new URL(url, location.href).pathname) || 0;
    return { files: this.fetched.size, bytes };
  }

  // What to show when the pane changes shape and nobody has moved the camera yet.
  rest() { return this.all ? this.home() : null; }

  layout() {
    const { width, height } = this.el.getBoundingClientRect();
    if (!width || !height) return;
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    const view = !this.touched && this.rest();
    if (view) this.fly(...view, true);
    this.draw();
  }

  draw() {
    if (this.pending) return;
    this.pending = requestAnimationFrame(() => { this.pending = null; this.renderer.render(this.scene, this.camera); });
  }

  dispose() {
    this.gone = true;
    this.resize.disconnect();
    this.controls.dispose();
    this.renderer.dispose();
  }
}

// The 3D view of the world. Each place is its set, put down where the epoch says (the same arithmetic as
// standing.placed: turn about the set's origin, then slide it to `at`). The first view loads only what can be
// seen from far off: each place's block-out, its larger dressing and the toons, all low-poly. What is small
// or heavy (a kettle, the ring's full mesh, the hall's painting, marks) waits until you come close to its place.
class WorldViewer extends Miniature {
  constructor(stage, epoch, state, hooks) {
    super(stage, { status: "Setting out the world…", hint: "Tap a place" });
    this.began = performance.now();
    window.forgeWorld = null;
    this.epoch = epoch;
    this.hooks = hooks;
    this.controls.minDistance = 4;
    this.controls.maxDistance = 260;
    this.places = {};
    this.picks = [];
    // A tap (not a drag) on a place goes there.
    let down = null;
    this.renderer.domElement.addEventListener("pointerdown", (e) => { down = [e.clientX, e.clientY]; });
    this.renderer.domElement.addEventListener("pointerup", (e) => {
      if (this.walkabout || !down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 6) return; // while walking, a tap is "walk there"
      const name = this.pick(e.clientX, e.clientY);
      if (name) this.hooks.onPick(name);
    });
    this.ground();
    this.filled = this.fill(state);
  }

  // The developer's unfinished floor: plain grey with a faint grid, a few scale cubes, a note or two.
  ground() {
    const g = this.epoch.ground;
    const [w, d] = g.size_m;
    const grey = new THREE.Color(...g.color);
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(w, d), new THREE.MeshStandardMaterial({ color: grey, roughness: 1 }));
    floor.rotation.x = -Math.PI / 2;
    floor.position.set(g.center[0], -0.03, g.center[1]);
    this.scene.add(floor);
    const step = g.grid_m || 2, lines = [];
    for (let x = -w / 2; x <= w / 2 + 1e-6; x += step) lines.push(x, 0, -d / 2, x, 0, d / 2);
    for (let z = -d / 2; z <= d / 2 + 1e-6; z += step) lines.push(-w / 2, 0, z, w / 2, 0, z);
    const grid = new THREE.LineSegments(new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(lines, 3)),
      new THREE.LineBasicMaterial({ color: 0x1c1917, transparent: true, opacity: 0.07 }));
    grid.position.set(g.center[0], -0.02, g.center[1]);
    this.scene.add(grid);
    const cube = new THREE.MeshStandardMaterial({ color: grey.clone().multiplyScalar(0.94), roughness: 1 });
    for (const c of g.cubes || []) {
      const box = new THREE.Mesh(new THREE.BoxGeometry(c.size_m, c.size_m, c.size_m), cube);
      box.position.set(c.at[0], c.size_m / 2, c.at[1]);
      this.scene.add(box);
    }
    for (const note of g.notes || []) {
      const label = labelSprite(note.text);
      label.material.sizeAttenuation = false;
      label.material.opacity = 0.7;
      label.material.transparent = true;
      label.scale.multiplyScalar(0.02);
      label.position.set(note.at[0], 1.6, note.at[1]);
      this.scene.add(label);
    }
  }

  async fill(state) {
    const { epoch } = this;
    try {
      await document.fonts?.load("600 30px Karla").catch(() => null); // the labels are drawn in the page's own lettering
      const all = new THREE.Box3();
      const waiting = [];
      for (const [name, place] of Object.entries(epoch.places)) {
        const set = sets.find((s) => s.id === place.set);
        if (!set) continue;
        const origin = set.frame?.origin || [0, 0, 0];
        const group = new THREE.Group();
        group.position.set(place.at[0], place.lift_m || 0, place.at[1]);
        group.rotation.y = deg((place.facing_deg ?? set.frame?.front_deg ?? 0) - (set.frame?.front_deg || 0));
        const inner = new THREE.Group(); // the set's own frame: everything in set.json is measured from its origin
        inner.position.set(-origin[0], -origin[1], -origin[2]);
        group.add(inner);
        this.scene.add(group);
        group.updateMatrixWorld(true);
        const xs = set.footprint.outline.map((p) => p[0]), zs = set.footprint.outline.map((p) => p[1]);
        const lo = [Math.min(...xs), Math.min(...zs)], hi = [Math.max(...xs), Math.max(...zs)];
        const tall = Math.max(3, ...(set.blocks || []).map((b) => b.center[1] + b.size[1] / 2));
        const entry = { name, place, set, group, inner, close: false, extras: [], lo, hi, tall, area: (hi[0] - lo[0]) * (hi[1] - lo[1]) };
        this.places[name] = entry;
        // What a tap lands on: a box over the footprint, never drawn.
        const pick = new THREE.Mesh(new THREE.BoxGeometry(hi[0] - lo[0], tall, hi[1] - lo[1]));
        pick.position.set((lo[0] + hi[0]) / 2, tall / 2, (lo[1] + hi[1]) / 2);
        pick.visible = false;
        pick.userData.place = name;
        inner.add(pick);
        this.picks.push(pick);
        const label = labelSprite(place.label || set.title || words(name));
        label.material.sizeAttenuation = false;
        label.scale.multiplyScalar(place.inside ? 0.022 : 0.028);
        label.position.set((lo[0] + hi[0]) / 2, tall + (place.inside ? 0.6 : 1.6), (lo[1] + hi[1]) / 2);
        inner.add(label);
        entry.label = label;
        for (const p of set.footprint.outline) all.expandByPoint(inner.localToWorld(new THREE.Vector3(p[0], 0, p[1])));
        if (place.inside) continue; // drawn by the place it stands in (the ring is the boxing house's dressing)
        if (set.glb) waiting.push(this.get(`sets/${set.id}/${set.glb}`).then((gltf) => inner.add(gltf.scene.clone(true))));
        for (const item of set.dressing || []) {
          if (item.small) continue;
          waiting.push(this.get(`sets/${set.id}/${item.glb}`).then((gltf) => { entry[`dressing:${item.prop}`] = this.onSlot(entry, item, gltf.scene.clone(true)); }));
        }
        for (const sign of set.signs || []) if (!sign.detail) waiting.push(this.sign(entry, sign));
      }
      for (const toon of epoch.toons) {
        const entry = this.places[toon.place];
        const mark = entry?.set.marks?.[toon.mark];
        if (!mark) continue;
        waiting.push(this.get(toon.glb).then((gltf) => {
          const body = gltf.scene.clone(true);
          const spot = mark.kind === "sit" ? mark.stand_at : mark.at;
          body.position.set(spot[0], mark.floor_y || 0, spot[1]);
          body.rotation.y = deg(mark.facing_deg);
          body.userData.toon = toon.toon;
          entry.inner.add(body);
          entry[`toon:${toon.toon}`] = body;
        }));
      }
      this.all = all;
      this.goTo(state.place, true);
      await Promise.all(waiting);
      this.ready = true;
      this.status.remove();
      this.draw();
      this.report();
      if (this.places[this.at]) this.comeClose(this.places[this.at]);
    } catch (err) {
      this.status.textContent = "Couldn't set out the world.";
      console.error(err);
    }
  }

  onSlot(entry, item, object) {
    const slot = entry.set.slots[item.slot];
    object.position.fromArray(slot.at);
    object.rotation.y = deg(slot.heading);
    entry.inner.add(object);
    return object;
  }

  async sign(entry, sign) {
    const flat = new THREE.Mesh(new THREE.PlaneGeometry(sign.width_m, sign.height_m), new THREE.MeshBasicMaterial({ map: await this.picture(`sets/${entry.set.id}/${sign.image}`), toneMapped: false }));
    flat.position.fromArray(sign.center);
    flat.rotation.y = deg(sign.heading);
    entry.inner.add(flat);
    this.draw();
  }

  // What waits until you come close to a place: its small dressing, heavier versions, wall paintings, what its
  // toons hold, and the names of who and what is there.
  async comeClose(entry) {
    if (entry.close) return;
    entry.close = true;
    const { set, inner } = entry, waiting = [];
    const name = (text, at, size = 0.024) => {
      const label = labelSprite(text);
      label.material.sizeAttenuation = false;
      label.scale.multiplyScalar(size);
      label.position.copy(at);
      inner.add(label);
      entry.extras.push(label);
      return label;
    };
    for (const item of set.dressing || []) {
      if (item.small) waiting.push(this.get(`sets/${set.id}/${item.glb}`).then((gltf) => { entry[`dressing:${item.prop}`] = this.onSlot(entry, item, gltf.scene.clone(true)); }));
      if (item.detail) {
        waiting.push(this.get(`sets/${set.id}/${item.detail}`).then((gltf) => {
          const light = entry[`dressing:${item.prop}`];
          if (light) inner.remove(light);
          entry[`dressing:${item.prop}`] = this.onSlot(entry, item, gltf.scene.clone(true));
        }));
      }
    }
    for (const sign of set.signs || []) if (sign.detail) waiting.push(this.sign(entry, sign));
    if (set.backdrop) waiting.push(this.sign(entry, set.backdrop));
    for (const toon of this.epoch.toons.filter((t) => t.place === entry.name)) {
      const mark = set.marks[toon.mark], body = entry[`toon:${toon.toon}`];
      if (!mark || !body) continue;
      const tag = name(toon.name, body.position.clone().add(new THREE.Vector3(0, toon.toon === "troll" ? 3.0 : 2.15, 0)));
      tag.userData.toon = toon.toon; // whoever is out walking takes their name with them
      tag.visible = this.walkabout?.who.toon !== toon.toon;
      for (const thing of this.epoch.artifacts.filter((a) => a.held_by === toon.toon && a.glb)) {
        waiting.push(this.get(thing.glb).then((gltf) => {
          const held = gltf.scene.clone(true);
          held.position.fromArray(thing.offset || [0, 1.1, 0.3]);
          body.add(held);
        }));
      }
    }
    for (const thing of this.epoch.artifacts.filter((a) => a.place === entry.name)) {
      const slot = set.slots?.[thing.slot];
      if (slot) name(thing.title, new THREE.Vector3(slot.at[0], slot.at[1] + (thing.name === "gachapon" ? 3.0 : thing.name === "microphone" ? 2.0 : thing.name === "buy-house" ? 2.5 : 0.75), slot.at[2]), 0.02);
    }
    await Promise.all(waiting).catch((err) => console.error(err));
    entry.settled = true;
    this.draw();
    this.report();
  }

  showMarks(on) {
    const entry = this.places[this.at];
    for (const other of Object.values(this.places)) if (other.marks) other.marks.visible = on && other === entry;
    if (entry && on && !entry.marks) {
      entry.marks = SetViewer.prototype.markMarkers.call({ set: entry.set });
      entry.inner.add(entry.marks);
    }
    this.draw();
  }

  pick(x, y) {
    const box = this.renderer.domElement.getBoundingClientRect();
    const ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2(((x - box.left) / box.width) * 2 - 1, -((y - box.top) / box.height) * 2 + 1), this.camera);
    const hits = ray.intersectObjects(this.picks, false).map((hit) => this.places[hit.object.userData.place]);
    // The smallest place under the finger wins: the ring, not the hall around it.
    return hits.sort((a, b) => a.area - b.area)[0]?.name;
  }

  view(name) {
    const entry = this.places[name];
    if (!entry) return this.home();
    const { lo, hi, tall, inner } = entry;
    const middle = inner.localToWorld(new THREE.Vector3((lo[0] + hi[0]) / 2, tall * 0.25, (lo[1] + hi[1]) / 2));
    const d = this.back(Math.max(hi[0] - lo[0], (hi[1] - lo[1]) * 0.9) * (this.camera.aspect < 1 ? 1.12 : 0.82));
    // From out front of the place (its own +z) and a little to one side, looking down into it.
    const from = inner.localToWorld(new THREE.Vector3((lo[0] + hi[0]) / 2 + d * 0.3, d * 0.5, (lo[1] + hi[1]) / 2 + d * 0.8));
    return [from, middle];
  }

  goTo(name, jump = false) {
    this.arrive(name);
    this.fly(...this.view(name), jump);
  }

  // Be at a place (or at none) without moving the camera: its small things and names show, its big label hides.
  arrive(name) {
    this.at = name;
    const entry = this.places[name];
    for (const other of Object.values(this.places)) {
      other.extras.forEach((o) => { o.visible = other === entry && !(o.userData.toon && o.userData.toon === this.walkabout?.who.toon); });
      if (other.marks) other.marks.visible = false;
      other.label.visible = other !== entry;
    }
    if (entry && this.ready) this.comeClose(entry);
    if (this.walkabout) this.report();
  }

  rest() { return this.all ? this.view(this.at) : null; }

  // How much was fetched, said plainly under the view.
  report() {
    this.loaded = this.loadedSoFar();
    // For whoever is checking the page from outside (scripts/world/shots.py): what has loaded, and that it has.
    window.forgeWorld = { ...this.loaded, seconds: (performance.now() - this.began) / 1000, place: this.at || null, settled: !this.places[this.at] || this.places[this.at].settled === true };
    this.hooks.onLoad(`Loaded so far: ${this.loaded.files} files, ${(this.loaded.bytes / 1e6).toFixed(2)} MB. Small things and heavier versions load when you come close to their place.`);
  }

  dispose() {
    this.walkabout?.stop();
    super.dispose();
  }
}

// Walk around the world: a toon you steer, seen from behind (gallery/walkabout.js). That file, its style sheet
// and the walker's own two files are fetched here, the first time someone asks to walk, and not before.
async function walkAround(worldViewer, epoch, who, hooks) {
  await worldViewer.filled;
  if (worldViewer.gone || !worldViewer.ready) throw new Error("the world is not set out");
  const { startWalk } = await import("./walkabout.js");
  return startWalk({ viewer: worldViewer, epoch, sets, runs, who, h, labelSprite, ...hooks });
}

// ---------- dioramas ----------

// A diorama is one moment of the story, built from the real game assets and stood on a wooden base: the toys
// on the basement shelf, where the portraits and the comics are the world as the toons imagine it. One light
// .glb each (dioramas/<name>/diorama.glb). The newest opens the front page; the others wait on a shelf under it.

const SWAY_DEG = 16, SWAY_S = 26, SWAY_AGAIN_MS = 6000; // the idle turn: this far each way, this slowly, this long after a touch

class DioramaViewer extends Miniature {
  constructor(stage, diorama, hooks = {}) {
    super(stage, { status: "Setting it on the shelf…", hint: "Drag to turn it", background: 0xe6dccb });
    this.began = performance.now();
    window.forgeDiorama = null;
    this.diorama = diorama;
    this.hooks = hooks;
    this.calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.controls.addEventListener("start", () => { this.hold(); this.el.querySelector(".hint")?.remove(); });
    this.controls.addEventListener("end", () => this.letGo());
    this.inView = true;
    this.watch = new IntersectionObserver(([entry]) => { this.inView = entry.isIntersecting; if (this.inView) this.idle(); else this.swaying = null; });
    this.watch.observe(this.el);
    this.fill();
  }

  async fill() {
    const model = await this.show(`dioramas/${encodeURIComponent(this.diorama.name)}/${this.diorama.glb}`);
    if (!model || this.gone) return;
    const across = this.all.getSize(new THREE.Vector3()).length();
    this.controls.minDistance = across * 0.12;
    this.controls.maxDistance = across * 3;
    const loaded = this.loadedSoFar();
    // For whoever is checking the page from outside (scripts/diorama/shots.py): what has loaded, and that it has.
    window.forgeDiorama = { ...loaded, seconds: (performance.now() - this.began) / 1000, settled: true };
    this.hooks.onLoad?.(loaded);
    this.idle();
  }

  // A camera of the diorama's own (build.json), as this screen can hold it: the same direction, far enough back
  // to keep what that camera framed in the picture.
  viewOf(view) {
    const aim = new THREE.Vector3(...view.aim), from = new THREE.Vector3(...view.at).sub(aim).normalize();
    const half = Math.tan(deg(this.camera.fov / 2));
    const away = Math.max(view.holds_m / 2 / (half * this.camera.aspect), view.holds_m / 1.6 / 2 / half) * 0.94;
    return [aim.clone().addScaledVector(from, away), aim];
  }

  home() {
    const first = Object.values(this.diorama.views || {})[0];
    return first ? this.viewOf(first) : super.home();
  }

  view(name) {
    const view = (this.diorama.views || {})[name];
    if (!view) return;
    this.hold();
    this.touched = true;
    this.fly(...this.viewOf(view));
    this.letGo(900);
  }

  hold() {
    clearTimeout(this.again);
    this.swaying = null;
  }

  letGo(after = 0) {
    clearTimeout(this.again);
    this.again = setTimeout(() => this.idle(), SWAY_AGAIN_MS + after);
  }

  // The idle turn: a slow sway either side of wherever the camera was left, so the front stays the front.
  idle() {
    if (this.calm || this.gone || !this.all || !this.inView || this.swaying) return;
    const sway = (this.swaying = { from: this.camera.position.clone().sub(this.controls.target), began: performance.now() });
    const up = new THREE.Vector3(0, 1, 0);
    const step = (now) => {
      if (this.swaying !== sway || this.gone) return;
      if (!document.hidden) {
        const angle = deg(SWAY_DEG) * Math.sin(((now - sway.began) / 1000) * ((2 * Math.PI) / SWAY_S));
        this.camera.position.copy(this.controls.target).add(sway.from.clone().applyAxisAngle(up, angle));
        this.camera.lookAt(this.controls.target);
        this.draw();
      }
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  layout() {
    const swaying = this.swaying;
    this.swaying = null;
    super.layout();
    if (swaying) this.idle();
  }

  dispose() {
    this.hold();
    this.watch.disconnect();
    super.dispose();
  }
}

// One diorama, laid out: what it is called, the thing itself to turn over, other angles, and its pictures.
function dioramaView(diorama, kicker, beside = []) {
  const stage = h("div", { class: "stage diorama-stage clay-well" });
  const loadLine = h("p", { class: "load-line" });
  const views = Object.entries(diorama.views || {});
  const pictures = `dioramas/${encodeURIComponent(diorama.name)}/`;
  queueMicrotask(() => {
    viewer?.dispose();
    viewer = new DioramaViewer(stage, diorama, {
      onLoad: (loaded) => { loadLine.textContent = `One file, ${mb(loaded.bytes || diorama.bytes)}${diorama.triangles ? `, ${num(diorama.triangles)} triangles` : ""}. The pictures open full size when you tap them.`; },
    });
  });
  return h("section", { class: "state" },
    h("header", { class: "words" },
      h("p", { class: "kicker" }, kicker),
      h("h1", {}, diorama.title),
      h("p", { class: "caption" }, diorama.caption),
      diorama.epoch?.title ? h("a", { class: "epoch", href: `#/world/${encodeURIComponent(diorama.epoch.name)}` }, `Epoch ${diorama.epoch.number} · ${diorama.epoch.title}`) : null,
    ),
    h("div", { class: "show" },
      stage,
      views.length > 1 ? h("div", { class: "angles", role: "group", "aria-label": "Look from" },
        views.map(([name, view]) => h("button", { class: "chip clay-chip", type: "button", onclick: () => viewer?.view?.(name) }, view.about || words(name)))) : null,
      loadLine,
    ),
    h("aside", { class: "beside" },
      diorama.stills.length ? h("div", { class: "stills" }, diorama.stills.map((still) =>
        h("a", { class: "still clay-surface", href: pictures + still.picture, target: "_blank", rel: "noopener", title: still.about || words(still.camera) },
          h("img", { src: pictures + still.small, alt: still.about || words(still.camera), width: 480, height: 300, loading: "lazy", decoding: "async" })))) : null,
      beside,
    ),
  );
}

// The front page opens with the newest diorama: the state of the world. The world card sits beside it, and
// the earlier dioramas wait on a shelf, newest first.
function stateOfTheWorld() {
  const built = dioramas.filter((d) => d.glb);
  if (!built.length) return worldCard();
  const [now, ...earlier] = built;
  const past = h("div", { class: "past" },
    h("h2", {}, "Earlier moments"),
    earlier.length
      ? h("div", { class: "past-row" }, earlier.map((d) =>
        h("a", { class: "card clay-surface past-card", href: `#/diorama/${encodeURIComponent(d.name)}` },
          d.card ? h("img", { src: `dioramas/${encodeURIComponent(d.name)}/${d.card}`, alt: "", loading: "lazy" }) : null,
          h("div", { class: "label" }, h("h3", {}, d.title), h("p", {}, `Epoch ${d.epoch.number}`)))))
      : h("p", { class: "none" }, "This is the first one. When the next is made, this one moves down here."),
  );
  return dioramaView(now, "State of the world", [worldCard(), past]);
}

function dioramaPage(diorama) {
  return h("article", { class: "object" },
    h("a", { class: "back", href: "#/" }, "← Everything"),
    dioramaView(diorama, `Diorama ${diorama.number}`),
  );
}

// ---------- one object ----------

function versionsOf(run) {
  const list = [];
  if (run.raw) list.push({ name: "raw", glb: run.raw, edges: null });
  return list.concat(run.profiles);
}

function facts(run, v) {
  if (v.name === "raw") {
    return [
      ["Faces", `${num(v.triangles)}`, "triangles"],
      ["Made on", run.gpu ? run.gpu.replace("NVIDIA GeForce ", "") : "—", ""],
      ["Mesh time", run.mesh_seconds.generate ? `${Math.round(run.mesh_seconds.generate + (run.mesh_seconds.export || 0))} s` : "—", ""],
    ];
  }
  const quadShare = v.quads && v.faces ? Math.round((100 * v.quads) / v.faces) : null;
  const rows = [
    ["Faces", num(v.faces), quadShare !== null ? `${quadShare}% quads` : "triangles"],
    ["Off the original", v.shape_typical !== null && v.shape_typical !== undefined ? `${v.shape_typical}%` : "—", v.shape_worst ? `typically · ${v.shape_worst}% at worst` : ""],
    ["File", mb(v.bytes), ""],
    ["Textures", v.maps ? v.maps.length : "—", v.maps ? v.maps.join(", ") : ""],
  ];
  // How it walks, worked out from its own build: pace, then the steps behind it.
  if (v.hero && v.hero_seconds) rows.push(["Hero shot", `${Math.round(v.hero_seconds)} s`, v.hero_mixed ? "two cuts: all our poses, or some beats from a sentence" : v.hero_prop ? `with its ${v.hero_prop}` : "from poses of our own"]);
  if (v.walk && v.cloth_bones) rows.push(["Loose cloth", `${v.cloth_bones} bones`, "it hangs and swings as the character moves"]);
  if (v.walk && v.gait?.speed_m_s) rows.push(["Walks at", `${v.gait.speed_m_s} m/s`, `${v.gait.cadence_steps_per_min} steps a minute · ${v.gait.stride_m} m stride`]);
  if (v.run && v.run_gait?.speed_m_s) rows.push(["Runs at", `${v.run_gait.speed_m_s} m/s`, `${v.run_gait.steps_per_minute} steps a minute · made from one sentence`]);
  return rows;
}

function objectPage(run, wanted) {
  const versions = versionsOf(run);
  const start = versions.find((v) => v.name === wanted) || versions.find((v) => v.name === "web") || versions[versions.length - 1];
  // `off` holds the gear the visitor took off; it carries over between the versions that have gear.
  const state = { version: start, compare: false, wire: false, off: new Set(), sockets: false, clip: "walk", bare: false };
  const hasGear = versions.some((v) => v.gear?.length);
  // A character whose clothes hide its body has a real body made from a second picture, and each
  // of those clothes cut out on its own. They stand where the raw mesh stands and, once the object
  // is finished, where the finished one does. The low-poly and mid-poly versions have their own gear.
  const bareOf = (v) => (v.gear?.length || !run.base ? null : v.name === "raw" ? run.base.raw : run.base.finished);

  const stage = h("div", { class: run.character ? "stage clay-well" : "stage stage--object clay-well" });
  const factsBox = h("div", { class: "facts" });
  const about = h("p", { class: "about" });
  const chips = versions.map((v) =>
    h("button", { class: "chip clay-chip", type: "button", "aria-pressed": String(v === state.version), onclick: () => select(v) }, VERSION_NAMES[v.name] || v.name),
  );
  const compareBtn = h("button", { class: "toggle clay-button clay-button--soft", type: "button", "aria-pressed": String(state.compare), onclick: () => { state.compare = !state.compare; compareBtn.setAttribute("aria-pressed", String(state.compare)); render(); } }, "Before / after");
  const wireBtn = h("button", { class: "toggle clay-button clay-button--soft", type: "button", "aria-pressed": String(state.wire), onclick: () => { state.wire = !state.wire; wireBtn.setAttribute("aria-pressed", String(state.wire)); viewer?.setWire(state.wire); } }, "Wireframe");

  // Pressed in, the clothed mesh steps aside for the body that is really under it; the clothes that
  // hid it become chips, off to begin with, and each goes back on with a tap.
  const bareBtn = h("button", { class: "toggle clay-button clay-button--soft", type: "button", "aria-pressed": "false", onclick: () => {
    state.bare = !state.bare;
    bareBtn.setAttribute("aria-pressed", String(state.bare));
    for (const name of run.base.garments) if (state.bare) state.off.add(name); else state.off.delete(name);
    render();
  } }, "Show the fitting form");
  const socketsBtn = h("button", { class: "toggle clay-button clay-button--soft", type: "button", "aria-pressed": "false", onclick: () => { state.sockets = !state.sockets; socketsBtn.setAttribute("aria-pressed", String(state.sockets)); viewer?.setSockets(state.sockets); } }, "Where props go");
  // One clip at a time. Pressed in, the character walks or runs on the spot, or plays a hero shot from start
  // to end, over and over, with the view following it; let go, it stands still in its T-pose.
  // A character can have two cuts of its hero shot: every beat from our own poses, or some beats
  // made from a sentence.
  const clipBtn = (clip, label) => h("button", { class: "toggle clay-button clay-button--soft", type: "button", "aria-pressed": String(state.clip === clip), onclick: () => { state.clip = state.clip === clip ? null : clip; showClips(); render(); } }, label);
  const clipBtns = { walk: clipBtn("walk", "Walk"), run: clipBtn("run", "Run"), hero: clipBtn("hero", "Hero"), hero_mixed: clipBtn("hero_mixed", "Hero: text + poses") };
  function showClips() {
    for (const [clip, btn] of Object.entries(clipBtns)) btn.setAttribute("aria-pressed", String(state.clip === clip));
  }
  // The clip to play on a version: the one pressed in, if that version has it.
  const playing = (x) => (state.clip && x[state.clip] ? state.clip : null);
  const gearRow = h("div", { class: "gear", role: "group", "aria-label": "Gear" });

  // One chip per piece of gear: pressed in means it's on. Only the low-poly and mid-poly versions have gear that comes off.
  function showGear() {
    const bare = state.bare ? bareOf(state.version) : null;
    const gear = bare ? bare.garments.map((g) => ({ gear: g.name, kind: "worn", slot: "cut from the clothed mesh" })) : state.version.gear || [];
    bareBtn.hidden = !bareOf(state.version);
    socketsBtn.hidden = !(state.version.sockets || []).length;
    for (const [clip, btn] of Object.entries(clipBtns)) btn.hidden = !state.version[clip];
    clipBtns.hero.textContent = state.version.hero_mixed ? "Hero: our poses" : "Hero";
    gearRow.hidden = !hasGear && !bare;
    if (!gear.length) {
      gearRow.replaceChildren(h("span", { class: "hint" }, "Gear comes off in the Low poly and Mid poly versions."));
      return;
    }
    gearRow.replaceChildren(
      h("span", { class: "hint" }, bare ? "Put back on" : "Wearing"),
      ...gear.map((g) => {
        const chip = h("button", { class: "chip clay-chip", type: "button", "aria-pressed": String(!state.off.has(g.gear)), title: `${g.kind}, ${g.slot}`, onclick: () => {
          if (state.off.has(g.gear)) state.off.delete(g.gear); else state.off.add(g.gear);
          chip.setAttribute("aria-pressed", String(!state.off.has(g.gear)));
          viewer?.setGear(state.off);
        } }, g.gear);
        return chip;
      }),
      h("span", { class: "hint" }, bare ? "The fitting form her clothes were cut to fit. Tap a piece to put it back on." : "Tap a piece to take it off."),
    );
  }

  function select(v) {
    state.version = v;
    history.replaceState(null, "", `#/run/${encodeURIComponent(run.id)}/${v.name}`);
    chips.forEach((c, i) => c.setAttribute("aria-pressed", String(versions[i] === v)));
    render();
  }

  function render() {
    const v = state.version;
    const raw = versions.find((x) => x.name === "raw");
    const panes = state.compare && raw && v !== raw ? [raw, v] : [v];
    viewer?.dispose();
    viewer = new Viewer(stage, panes.map((x) => {
      const bare = state.bare ? bareOf(x) : null;
      if (bare) return {
        label: `${x === raw ? "Raw" : VERSION_NAMES[x.name]} · the body underneath`,
        glb: file(run, bare.body),
        pieces: bare.garments.map((g) => ({ gear: g.name, glb: file(run, g.glb) })),
        walk: null, follow: false, edges: null, onTriangles: null,
      };
      return {
      label: panes.length > 1 ? (x === raw ? "Before" : `After · ${VERSION_NAMES[x.name]}`) : VERSION_NAMES[x.name],
      glb: file(run, x.glb),
      walk: playing(x) ? file(run, x[playing(x)]) : null,
      follow: Boolean(playing(x)) && playing(x) !== "walk" && playing(x) !== "run",
      edges: x.edges ? file(run, x.edges) : null,
      onTriangles: x === raw ? (n) => { raw.triangles = n; if (state.version === raw) showFacts(); } : null,
      };
    }), state.wire, state.off, state.sockets);
    showFacts();
    showGear();
  }

  function showFacts() {
    const v = state.version;
    factsBox.replaceChildren(...facts(run, v).map(([k, val, small]) =>
      h("div", { class: "fact clay-surface" }, h("div", { class: "k" }, k), h("div", { class: "v" }, String(val), small ? h("br") : null, small ? h("small", {}, small) : null)),
    ));
    if (state.bare && bareOf(v)) {
      about.textContent = `The body under the ${run.base.garments.join(" and ")}, made for real instead of guessed: Codex drew the same picture again without ${run.base.garments.length > 1 ? "them" : "it"}, TRELLIS.2 built that, and the ${run.base.garments.join(" and ")} ${run.base.garments.length > 1 ? "were" : "was"} cut out of the clothed mesh to go back on.${run.base.apart_pct !== null && run.base.apart_pct !== undefined ? ` Where nothing covers it, the two bodies sit ${run.base.apart_pct}% of the height apart.` : ""}`;
      return;
    }
    about.textContent = v.about || (v.name === "raw" ? "Straight from TRELLIS.2: an even soup of triangles with no edge loops." : "");
  }

  const page = h("article", { class: "object" },
    h("a", { class: "back", href: "#/" }, "← All objects"),
    h("h1", {}, run.name),
    run.description ? h("p", { class: "lede" }, run.description) : null,
    // An object (a camera, a ring, a kettle) has nothing to play or put on: its few controls share the
    // versions' row, and its stage is a landscape one that fits a thing on a table, not a standing figure.
    run.character
      ? h("div", { class: "versions", role: "group", "aria-label": "Version" }, chips)
      : h("div", { class: "versions object-row", role: "group", "aria-label": "Version" }, chips, h("span", { class: "row-gap" }), compareBtn, wireBtn),
    run.character
      ? h("div", { class: "controls" }, h("div", { class: "toggles" }, compareBtn, wireBtn, clipBtns.walk, clipBtns.run, clipBtns.hero, clipBtns.hero_mixed, socketsBtn))
      : null,
    gearRow,
    stage,
    factsBox,
    about,
    // How a hiding garment was made is a note for the curious, kept below the fold and phrased with care:
    // the fitting form, not "without clothes".
    run.base ? h("div", { class: "notes clay-surface" }, h("h3", {}, "How the clothes were made"),
      h("p", {}, "The clothes were cut from the first picture and fitted onto a form made from a second one, so nothing under them is guessed."),
      bareBtn) : null,
    making(run),
  );
  queueMicrotask(render);
  return page;
}

function making(run) {
  const pictures = [
    run.picture && ["The picture Codex drew", run.picture],
    run.render && [`Claude's finished render${run.score ? ` · matches the picture ${run.score}/5` : ""}`, run.render],
    run.base?.picture && [`The same picture with the ${run.base.garments.join(" and ")} off, for the body underneath`, run.base.picture],
    run.base?.sheet && ["The body, the clothes cut for it, and both; below, which clues picked each face", run.base.sheet],
  ].filter(Boolean);
  return h("section", { class: "making" },
    h("h2", {}, "How it was made"),
    pictures.length ? h("div", { class: "pictures" }, pictures.map(([caption, rel]) =>
      h("figure", { class: "clay-surface" }, h("img", { src: file(run, rel), alt: caption, loading: "lazy" }), h("figcaption", {}, caption)),
    )) : null,
    run.props.length ? h("div", { class: "notes clay-surface" }, h("h3", {}, "What it carries"), h("ul", {}, run.props.map((p) =>
      h("li", {}, h("a", { href: `#/run/${encodeURIComponent(p.run)}` }, p.name || p.gear), ` · goes on the ${SOCKET_NAMES[p.socket] || p.socket}. Made on its own, so it can be put down or swapped.`)))) : null,
    run.prop_of ? h("div", { class: "notes clay-surface" }, h("h3", {}, "Made for"), h("p", {}, h("a", { href: `#/run/${encodeURIComponent(run.prop_of)}` }, "the character that carries it"))) : null,
    run.fixes.length ? h("div", { class: "notes clay-surface" }, h("h3", {}, "What Claude fixed in Blender"), h("ul", {}, run.fixes.map((f) => h("li", {}, f)))) : null,
    run.problems.length ? h("div", { class: "notes clay-surface" }, h("h3", {}, "What it couldn't fix"), h("ul", {}, run.problems.map((f) => h("li", {}, f)))) : null,
  );
}

// ---------- the 3D view: one camera shared by every pane ----------

class Viewer {
  constructor(stage, specs, wire, off = new Set(), sockets = false) {
    this.stage = stage;
    this.panes = [];
    this.wire = wire;
    this.off = off;
    this.sockets = sockets;
    this.camera = new THREE.PerspectiveCamera(32, 1, 0.001, 100);
    this.camera.position.set(0.55, 0.35, 0.8);
    this.framed = false;
    stage.className = `stage clay-well${specs.length > 1 ? " compare" : ""}`;
    stage.replaceChildren();
    for (const spec of specs) this.panes.push(this.makePane(spec));
    this.resize = new ResizeObserver(() => this.layout());
    this.panes.forEach((p) => this.resize.observe(p.el));
    this.layout();
  }

  makePane(spec) {
    const el = h("div", { class: "pane" });
    const status = h("div", { class: "status" }, "Loading…");
    el.append(status, h("span", { class: "tag" }, spec.label));
    this.stage.append(el);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.setClearColor(0xebe6dc);
    el.prepend(renderer.domElement);
    const scene = new THREE.Scene();
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    const controls = new OrbitControls(this.camera, renderer.domElement);
    controls.enableDamping = false;
    controls.addEventListener("change", () => this.draw());
    const pane = { el, renderer, scene, controls, wire: null, model: null, markers: null, mixer: null, status };
    this.fill(pane, spec);
    return pane;
  }

  async fill(pane, spec) {
    try {
      const gltf = await load(spec.walk || spec.glb);
      if (!this.panes.includes(pane)) return;
      // A model with a skeleton needs its bones copied along with it.
      const model = spec.walk ? cloneSkinned(gltf.scene) : gltf.scene.clone(true);
      // Clothes cut for a base body come in files of their own; each joins the model under its gear name.
      for (const piece of spec.pieces || []) {
        const cloth = (await load(piece.glb)).scene.clone(true);
        cloth.userData.gear = piece.gear;
        model.add(cloth);
      }
      if (!this.panes.includes(pane)) return;
      let triangles = 0;
      model.traverse((o) => {
        if (!o.isMesh) return;
        const g = o.geometry;
        triangles += (g.index ? g.index.count : g.attributes.position.count) / 3;
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        mats.forEach((m) => { m.polygonOffset = true; m.polygonOffsetFactor = 1; m.polygonOffsetUnits = 1; });
      });
      spec.onTriangles?.(Math.round(triangles));
      pane.scene.add(model);
      pane.model = model;
      // The wireframe (and its edges file) is only made once it is wanted: off by default, so a page opens faster.
      pane.spec = spec;
      pane.triangles = triangles;
      if (this.wire) await this.addWire(pane);
      pane.markers = this.markersFor(model, Boolean(spec.walk));
      if (pane.markers) { pane.markers.visible = this.sockets; if (!spec.walk) pane.scene.add(pane.markers); }
      if (spec.walk && gltf.animations.length) {
        pane.mixer = new THREE.AnimationMixer(model);
        pane.mixer.clipAction(gltf.animations[0]).play();
        // A clip that travels (the hero shot) is kept on the stage: see play().
        if (spec.follow) model.traverse((o) => { if (o.isBone && o.name === "hips") pane.follow = { bone: o, was: null }; });
        this.play();
      }
      this.setGear(this.off);
      pane.status.remove();
      if (!this.framed) this.frame(model);
      this.draw();
    } catch (err) {
      pane.status.textContent = "Couldn't load this version.";
      console.error(err);
    }
  }

  async wireFor(model, spec, triangles) {
    // Fade the lines as the mesh gets denser: a 1k-triangle block-out gets
    // bold lines, a 300k-triangle raw mesh faint ones, so it doesn't turn
    // into a solid blue blob.
    const opacity = Math.min(0.75, Math.max(0.07, 0.75 * Math.sqrt(4000 / Math.max(triangles, 1))));
    const material = new THREE.LineBasicMaterial({ color: 0x5b84c4, transparent: true, opacity });
    if (spec.edges) {
      // The real quad edges, exported alongside the GLB (which only holds triangles).
      const gltf = await load(spec.edges);
      const group = new THREE.Group();
      gltf.scene.traverse((o) => {
        if (o.isLineSegments || o.isLine) {
          const lines = new THREE.LineSegments(o.geometry, material);
          lines.applyMatrix4(o.matrixWorld);
          lines.userData.gear = o.userData.gear;
          lines.userData.under = o.userData.under;
          group.add(lines);
        }
      });
      return group;
    }
    if (triangles > RAW_WIREFRAME_LIMIT) return null;
    const group = new THREE.Group();
    model.updateMatrixWorld(true);
    model.traverse((o) => {
      if (!o.isMesh) return;
      const lines = new THREE.LineSegments(new THREE.WireframeGeometry(o.geometry), material);
      lines.applyMatrix4(o.matrixWorld);
      lines.userData.gear = gearOf(o);
      lines.userData.under = underOf(o);
      group.add(lines);
    });
    return group;
  }

  // A walking model's lines have to move with it: a second, see-through copy of each mesh on the
  // same bones, drawn as wire. (These are the file's triangles; the standing version shows the real quads.)
  walkingWire(model, triangles) {
    const opacity = Math.min(0.75, Math.max(0.07, 0.75 * Math.sqrt(4000 / Math.max(triangles, 1))));
    const material = new THREE.MeshBasicMaterial({ color: 0x5b84c4, wireframe: true, transparent: true, opacity });
    const skinned = [];
    model.traverse((o) => { if (o.isSkinnedMesh) skinned.push(o); });
    const lines = skinned.map((o) => {
      const copy = new THREE.SkinnedMesh(o.geometry, material);
      copy.bind(o.skeleton, o.bindMatrix);
      copy.userData.gear = gearOf(o);
      copy.userData.under = underOf(o);
      o.parent.add(copy);
      return copy;
    });
    return together(lines);
  }

  // Keep the picture moving while anything on the stage is walking.
  play() {
    if (this.playing) return;
    this.playing = true;
    let last = performance.now();
    const step = (now) => {
      const moving = this.panes.filter((p) => p.mixer);
      if (!moving.length) { this.playing = false; return; }
      moving.forEach((p) => {
        p.mixer.update(Math.min((now - last) / 1000, 0.1));
        if (!p.follow) return;
        // Slide the whole model back by however far the hips have gone over the ground, so the
        // character stays on the stage (it still rises and drops: only the travel is taken out).
        const at = p.follow.bone.getWorldPosition(new THREE.Vector3());
        if (!p.follow.was) p.follow.was = at.clone();
        p.model.position.x += p.follow.was.x - at.x;
        p.model.position.z += p.follow.was.z - at.z;
      });
      last = now;
      this.draw();
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  // A small ball and a label at each point the file marks for props ("socket: hand_right"...).
  // On a walking model each one rides on its socket, which rides on a bone.
  markersFor(model, riding = false) {
    const sockets = [];
    model.updateMatrixWorld(true);
    model.traverse((o) => { if (o.userData.socket) sockets.push(o); });
    if (!sockets.length) return null;
    const size = new THREE.Box3().setFromObject(model).getSize(new THREE.Vector3()).length();
    const group = new THREE.Group();
    const ball = new THREE.SphereGeometry(size * 0.009, 16, 12);
    const paint = new THREE.MeshBasicMaterial({ color: 0x44679b, depthTest: false });
    const riders = [];
    for (const socket of sockets) {
      const at = riding ? new THREE.Vector3() : socket.getWorldPosition(new THREE.Vector3());
      const dot = new THREE.Mesh(ball, paint);
      dot.position.copy(at);
      dot.renderOrder = 2;
      const label = labelSprite(SOCKET_NAMES[socket.userData.socket] || socket.userData.socket);
      label.position.copy(at).add(new THREE.Vector3(0, size * 0.028, 0));
      label.scale.multiplyScalar(size * 0.026);
      if (riding) { socket.add(dot, label); riders.push(dot, label); } else group.add(dot, label);
    }
    return riding ? together(riders) : group;
  }

  // Show or hide each gear piece, by the name its node carries in the file. The skin a piece hides
  // ("body under: wool trousers") is its own mesh: it shows only once every piece over it is off, so
  // skin can't poke through clothes that are on, and there is a whole body under clothes that are off.
  setGear(off) {
    this.off = off;
    const shown = (o) => (o.userData.gear ? !off.has(o.userData.gear) : hiddenBy(o).every((g) => off.has(g)));
    this.panes.forEach((p) => {
      p.model?.traverse((o) => { if (o.userData.gear || o.userData.under) o.visible = shown(o); });
      p.wire?.children.forEach((o) => { if (o.userData.gear || o.userData.under) o.visible = shown(o) && (!o.isSkinnedMesh || p.wire.visible); });
    });
    this.draw();
  }

  setSockets(on) {
    this.sockets = on;
    this.panes.forEach((p) => { if (p.markers) p.markers.visible = on; });
    this.draw();
  }

  frame(model) {
    const box = new THREE.Box3().setFromObject(model);
    const size = box.getSize(new THREE.Vector3()).length();
    const center = box.getCenter(new THREE.Vector3());
    const dir = new THREE.Vector3(0.62, 0.38, 0.92).normalize();
    this.camera.position.copy(center).addScaledVector(dir, size * 1.55);
    this.camera.near = size / 100;
    this.camera.far = size * 20;
    this.camera.updateProjectionMatrix();
    this.panes.forEach((p) => { p.controls.target.copy(center); p.controls.update(); });
    this.framed = true;
  }

  async addWire(pane) {
    if (pane.wire || !pane.model) return;
    const spec = pane.spec;
    pane.wire = spec.walk ? this.walkingWire(pane.model, pane.triangles) : await this.wireFor(pane.model, spec, pane.triangles);
    if (pane.wire) { pane.wire.visible = this.wire; if (!spec.walk) pane.scene.add(pane.wire); }
  }

  async setWire(on) {
    this.wire = on;
    if (on) await Promise.all(this.panes.map((p) => this.addWire(p)));
    this.panes.forEach((p) => { if (p.wire) p.wire.visible = on; });
    this.setGear(this.off);
  }

  layout() {
    const first = this.panes[0];
    if (!first) return;
    const { width, height } = first.el.getBoundingClientRect();
    if (!width || !height) return;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.panes.forEach((p) => {
      const r = p.el.getBoundingClientRect();
      p.renderer.setSize(r.width, r.height, false);
    });
    this.draw();
  }

  draw() {
    if (this.pending) return;
    this.pending = requestAnimationFrame(() => {
      this.pending = null;
      // Every pane's controls move the same camera; keep their targets together.
      const target = this.panes[0]?.controls.target;
      this.panes.forEach((p) => { if (target && p.controls.target !== target) p.controls.target.copy(target); p.renderer.render(p.scene, this.camera); });
    });
  }

  dispose() {
    this.panes.forEach((p) => { p.mixer?.stopAllAction(); p.mixer = null; });
    this.resize.disconnect();
    this.panes.forEach((p) => { p.controls.dispose(); p.renderer.dispose(); });
    this.panes = [];
  }
}

// Several things already placed in the scene, shown and hidden as one (what a Group does for things it holds).
function together(children) {
  let shown = true;
  return {
    children,
    get visible() { return shown; },
    set visible(on) { shown = on; children.forEach((o) => { o.visible = on; }); },
  };
}

// The gear that hides a piece of the body, by name: the file lists it on the mesh, joined with "|".
function hiddenBy(o) {
  return o.userData.under ? String(o.userData.under).split("|") : [];
}

function underOf(o) {
  for (let at = o; at; at = at.parent) if (at.userData.under) return at.userData.under;
  return undefined;
}

// The gear piece a mesh belongs to: the tag on it or on the node above it.
function gearOf(o) {
  for (let at = o; at; at = at.parent) if (at.userData.gear) return at.userData.gear;
  return undefined;
}

// A word on a small off-white pill that always faces the viewer.
function labelSprite(text) {
  const canvas = document.createElement("canvas");
  const pad = 18, height = 56;
  const ctx = canvas.getContext("2d");
  ctx.font = "600 30px Karla, sans-serif";
  canvas.width = Math.ceil(ctx.measureText(text).width) + pad * 2;
  canvas.height = height;
  ctx.font = "600 30px Karla, sans-serif";
  ctx.fillStyle = "#faf8f5";
  ctx.beginPath();
  ctx.roundRect(0, 0, canvas.width, height, height / 2);
  ctx.fill();
  ctx.fillStyle = "#1c1917";
  ctx.textBaseline = "middle";
  ctx.fillText(text, pad, height / 2 + 2);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false, toneMapped: false }));
  sprite.scale.set(canvas.width / height, 1, 1);
  sprite.renderOrder = 3;
  return sprite;
}

// ---------- comics ----------
// A comic is a row of drawn panels with its lettering laid over each as SVG, so the words stay text.

function panelFigure(comic, panel) {
  const figure = h("figure", { class: "panel" });
  const [wide, tall] = panel.size;
  figure.style.aspectRatio = `${wide} / ${tall}`;
  const sky = panel.sky || ["#f2efe9", "#e9e2d4"];
  figure.style.backgroundColor = sky[sky.length - 1];
  if (panel.sky_image && panel.sky_css) {
    // layout.py worked out where the backdrop hangs so its horizon is level with the camera's
    figure.style.cssText += panel.sky_css;
    figure.style.backgroundImage = `url("comics/${panel.sky_image}")`;
  } else if (panel.sky_image) {
    figure.style.backgroundImage = `url("comics/${panel.sky_image}")`;
    figure.style.backgroundSize = `auto ${panel.sky_zoom || 100}%`;
    figure.style.backgroundPosition = "center 42%";
    figure.style.backgroundRepeat = "no-repeat";
  } else {
    figure.style.backgroundImage = `linear-gradient(${sky[0]}, ${sky[sky.length - 1]})`;
  }
  figure.append(h("img", { src: `comics/${encodeURIComponent(comic.name)}/${panel.file}`, alt: panel.alt, loading: "lazy", width: wide, height: tall }));
  // The lettering is SVG our own layout step wrote (scripts/comic/layout.py), read from this same server.
  const holder = document.createElement("div");
  holder.innerHTML = panel.svg;
  if (holder.firstElementChild) figure.append(holder.firstElementChild);
  return figure;
}

function comicShelf() {
  if (!comics.length) return null;
  return h("section", { class: "comics" },
    h("h2", { class: "shelf-heading" }, "Comics"),
    h("div", { class: "shelf" }, comics.map((comic) =>
      h("a", { class: "card clay-surface comic-card", href: `#/comic/${encodeURIComponent(comic.name)}` },
        h("div", { class: "cover" }, panelFigure(comic, comic.panels[0])),
        h("div", { class: "label" },
          h("h2", {}, comic.title),
          comic.canon === false ? h("p", {}, h("span", { class: "side-story", title: "Not part of the main story" }, "Side story")) : null,
          h("p", {}, `Read it · ${comic.layout === "strip" ? "a four-panel strip" : `${comic.panels.length} panels, top to bottom`}`),
        ),
      ),
    )),
  );
}

function shelfHeading() {
  return comics.length && runs.length ? h("h2", { class: "shelf-heading" }, "Objects") : null;
}

function comicPage(comic) {
  return h("article", { class: "object comic-reader" },
    h("a", { class: "back", href: "#/" }, "← Everything"),
    h("p", { class: "kicker" }, comic.layout === "strip" ? "A four-panel strip" : `A scroll episode · ${comic.panels.length} panels`,
      comic.canon === false ? h("span", { class: "side-story", title: "Not part of the main story" }, "Side story") : null),
    h("h1", {}, comic.title),
    h("div", { class: "comic-sheet clay-surface" },
      h("div", { class: `comic ${comic.layout}` }, comic.panels.map((panel) => panelFigure(comic, panel))),
    ),
    h("p", { class: "about" },
      comic.html ? h("a", { href: `comics/${encodeURIComponent(comic.name)}/${comic.html}` }, "Open it as a page of its own") : null,
      comic.html && comic.png ? " · " : null,
      comic.png ? h("a", { href: `comics/${encodeURIComponent(comic.name)}/${comic.png}` }, "Save it as a picture") : null,
    ),
  );
}

// ---------- routing ----------

async function route() {
  if (!runs.length) {
    [runs, sets, takes] = await Promise.all(["api/runs", "api/sets", "api/takes"].map((url) => fetch(url).then((r) => r.json()).catch(() => [])));
  }
  if (!world) world = await fetch("api/world").then((r) => r.json()).catch(() => null);
  [comics, dioramas] = await Promise.all(["api/comics", "api/dioramas"].map((url) => fetch(url).then((r) => r.json()).catch(() => [])));
  const reading = location.hash.match(/^#\/comic\/([^/]+)$/);
  const comic = reading && comics.find((c) => c.name === decodeURIComponent(reading[1]));
  if (comic) {
    viewer?.dispose();
    viewer = null;
    app.replaceChildren(comicPage(comic));
    window.scrollTo(0, 0);
    return;
  }
  // #/world[/<epoch>[/<place>]]: the whole world at one epoch, maybe already standing at a place.
  // #/world/<epoch>/walk[/<toon>]: walking around it.
  const inWorld = location.hash.match(/^#\/world(?:\/([^/]+))?(?:\/([^/]+))?(?:\/([^/]+))?$/);
  if (inWorld && world?.epochs?.length) {
    app.replaceChildren(worldPage(inWorld[1] && decodeURIComponent(inWorld[1]), inWorld[2] && decodeURIComponent(inWorld[2]), inWorld[3] && decodeURIComponent(inWorld[3])));
    window.scrollTo(0, 0);
    return;
  }
  // #/diorama/<name>: one diorama on its own (the newest is the front page).
  const shown = location.hash.match(/^#\/diorama\/([^/]+)$/);
  const diorama = shown && dioramas.find((d) => d.name === decodeURIComponent(shown[1]) && d.glb);
  if (diorama) {
    app.replaceChildren(dioramaPage(diorama));
    window.scrollTo(0, 0);
    return;
  }
  // #/run/<run id>[/<version>]: a link can open a given version. #/set/<set name>[/<shot>[/<camera>]]: a standing set.
  const match = location.hash.match(/^#\/run\/([^/]+)(?:\/([a-z]+))?$/);
  const onSet = location.hash.match(/^#\/set\/([^/]+)(?:\/([^/]+))?(?:\/([a-z_]+))?$/);
  viewer?.dispose();
  viewer = null;
  const run = match && runs.find((r) => r.id === decodeURIComponent(match[1]));
  const set = onSet && sets.find((x) => x.id === decodeURIComponent(onSet[1]));
  const page = set ? [setPage(set, onSet[2] && decodeURIComponent(onSet[2]), onSet[3])] : run ? [objectPage(run, match[2])] : [stateOfTheWorld(), comicShelf(), shelfHeading(), shelf()];
  app.replaceChildren(...page.filter(Boolean));
  window.scrollTo(0, 0);
}

window.addEventListener("hashchange", route);
route();
