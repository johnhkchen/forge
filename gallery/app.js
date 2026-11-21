// Forge gallery: the shelf of runs, and a before/after viewer for each.
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
let comics = [];
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
  if (!runs.length) {
    return h("p", { class: "empty" }, "Nothing here yet. Run ", h("code", {}, 'just make "an idea"'), " and reload.");
  }
  return h("div", { class: "shelf" }, runs.map((run) =>
    h("a", { class: "card clay-surface", href: `#/run/${encodeURIComponent(run.id)}` },
      run.render || run.picture ? h("img", { src: file(run, run.render || run.picture), alt: "", loading: "lazy" }) : null,
      h("div", { class: "label" },
        h("h2", {}, run.name),
        h("p", {}, `${run.profiles.length ? `${run.profiles.length} versions` : "raw mesh only"} · ${run.made.slice(0, 10)}`),
      ),
    ),
  ));
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
  } }, "Without clothes");
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
      h("span", { class: "hint" }, bare ? "This is the real body, made from a second picture. Tap a piece to put it on." : "Tap a piece to take it off."),
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
      ? h("div", { class: "controls" }, h("div", { class: "toggles" }, compareBtn, wireBtn, run.base ? bareBtn : null, clipBtns.walk, clipBtns.run, clipBtns.hero, clipBtns.hero_mixed, socketsBtn))
      : null,
    gearRow,
    stage,
    factsBox,
    about,
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
  if (!runs.length) runs = await fetch("api/runs").then((r) => r.json()).catch(() => []);
  comics = await fetch("api/comics").then((r) => r.json()).catch(() => []);
  const reading = location.hash.match(/^#\/comic\/([^/]+)$/);
  const comic = reading && comics.find((c) => c.name === decodeURIComponent(reading[1]));
  if (comic) {
    viewer?.dispose();
    viewer = null;
    app.replaceChildren(comicPage(comic));
    window.scrollTo(0, 0);
    return;
  }
  // #/run/<run id>[/<version>]: a link can open a given version
  const match = location.hash.match(/^#\/run\/([^/]+)(?:\/([a-z]+))?$/);
  viewer?.dispose();
  viewer = null;
  const run = match && runs.find((r) => r.id === decodeURIComponent(match[1]));
  app.replaceChildren(...(run ? [objectPage(run, match[2])] : [comicShelf(), shelfHeading(), shelf()].filter(Boolean)));
  window.scrollTo(0, 0);
}

window.addEventListener("hashchange", route);
route();
