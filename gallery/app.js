// Forge gallery: the shelf of runs, and a before/after viewer for each.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const app = document.getElementById("app");
const VERSION_NAMES = { raw: "Raw TRELLIS.2", hero: "Hero", quads: "Quads", web: "Web", game: "Game", mobile: "Mobile", lowpoly: "Low poly" };
const RAW_WIREFRAME_LIMIT = 400000; // triangles; above this the raw wireframe is too heavy for a phone

const draco = new DRACOLoader().setDecoderPath("https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/libs/draco/gltf/");
const loader = new GLTFLoader().setDRACOLoader(draco);
const cache = new Map();
const load = (url) => {
  if (!cache.has(url)) cache.set(url, loader.loadAsync(url));
  return cache.get(url);
};

let runs = [];
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
  return [
    ["Faces", num(v.faces), quadShare !== null ? `${quadShare}% quads` : "triangles"],
    ["Off the original", v.shape_typical !== null && v.shape_typical !== undefined ? `${v.shape_typical}%` : "—", v.shape_worst ? `typically · ${v.shape_worst}% at worst` : ""],
    ["File", mb(v.bytes), ""],
    ["Textures", v.maps ? v.maps.length : "—", v.maps ? v.maps.join(", ") : ""],
  ];
}

function objectPage(run, wanted) {
  const versions = versionsOf(run);
  const start = versions.find((v) => v.name === wanted) || versions.find((v) => v.name === "web") || versions[versions.length - 1];
  const state = { version: start, compare: versions.length > 1, wire: true };

  const stage = h("div", { class: "stage clay-well" });
  const factsBox = h("div", { class: "facts" });
  const about = h("p", { class: "about" });
  const chips = versions.map((v) =>
    h("button", { class: "chip clay-chip", type: "button", "aria-pressed": String(v === state.version), onclick: () => select(v) }, VERSION_NAMES[v.name] || v.name),
  );
  const compareBtn = h("button", { class: "toggle clay-button clay-button--soft", type: "button", "aria-pressed": String(state.compare), onclick: () => { state.compare = !state.compare; compareBtn.setAttribute("aria-pressed", String(state.compare)); render(); } }, "Before / after");
  const wireBtn = h("button", { class: "toggle clay-button clay-button--soft", type: "button", "aria-pressed": String(state.wire), onclick: () => { state.wire = !state.wire; wireBtn.setAttribute("aria-pressed", String(state.wire)); viewer?.setWire(state.wire); } }, "Wireframe");

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
    viewer = new Viewer(stage, panes.map((x) => ({
      label: panes.length > 1 ? (x === raw ? "Before" : `After · ${VERSION_NAMES[x.name]}`) : VERSION_NAMES[x.name],
      glb: file(run, x.glb),
      edges: x.edges ? file(run, x.edges) : null,
      onTriangles: x === raw ? (n) => { raw.triangles = n; if (state.version === raw) showFacts(); } : null,
    })), state.wire);
    showFacts();
  }

  function showFacts() {
    const v = state.version;
    factsBox.replaceChildren(...facts(run, v).map(([k, val, small]) =>
      h("div", { class: "fact clay-surface" }, h("div", { class: "k" }, k), h("div", { class: "v" }, String(val), small ? h("br") : null, small ? h("small", {}, small) : null)),
    ));
    about.textContent = v.about || (v.name === "raw" ? "Straight from TRELLIS.2: an even soup of triangles with no edge loops." : "");
  }

  const page = h("article", { class: "object" },
    h("a", { class: "back", href: "#/" }, "← All objects"),
    h("h1", {}, run.name),
    run.description ? h("p", { class: "lede" }, run.description) : null,
    h("div", { class: "versions", role: "group", "aria-label": "Version" }, chips),
    h("div", { class: "controls" }, h("div", { class: "toggles" }, compareBtn, wireBtn)),
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
  ].filter(Boolean);
  return h("section", { class: "making" },
    h("h2", {}, "How it was made"),
    pictures.length ? h("div", { class: "pictures" }, pictures.map(([caption, rel]) =>
      h("figure", { class: "clay-surface" }, h("img", { src: file(run, rel), alt: caption, loading: "lazy" }), h("figcaption", {}, caption)),
    )) : null,
    run.fixes.length ? h("div", { class: "notes clay-surface" }, h("h3", {}, "What Claude fixed in Blender"), h("ul", {}, run.fixes.map((f) => h("li", {}, f)))) : null,
    run.problems.length ? h("div", { class: "notes clay-surface" }, h("h3", {}, "What it couldn't fix"), h("ul", {}, run.problems.map((f) => h("li", {}, f)))) : null,
  );
}

// ---------- the 3D view: one camera shared by every pane ----------

class Viewer {
  constructor(stage, specs, wire) {
    this.stage = stage;
    this.panes = [];
    this.wire = wire;
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
    const pane = { el, renderer, scene, controls, wire: null, status };
    this.fill(pane, spec);
    return pane;
  }

  async fill(pane, spec) {
    try {
      const gltf = await load(spec.glb);
      if (!this.panes.includes(pane)) return;
      const model = gltf.scene.clone(true);
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
      pane.wire = await this.wireFor(model, spec, triangles);
      if (pane.wire) { pane.wire.visible = this.wire; pane.scene.add(pane.wire); }
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
      group.add(lines);
    });
    return group;
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

  setWire(on) {
    this.wire = on;
    this.panes.forEach((p) => { if (p.wire) p.wire.visible = on; });
    this.draw();
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
    this.resize.disconnect();
    this.panes.forEach((p) => { p.controls.dispose(); p.renderer.dispose(); });
    this.panes = [];
  }
}

// ---------- routing ----------

async function route() {
  if (!runs.length) runs = await fetch("api/runs").then((r) => r.json()).catch(() => []);
  // #/run/<run id>[/<version>]: a link can open a given version
  const match = location.hash.match(/^#\/run\/([^/]+)(?:\/([a-z]+))?$/);
  viewer?.dispose();
  viewer = null;
  const run = match && runs.find((r) => r.id === decodeURIComponent(match[1]));
  app.replaceChildren(run ? objectPage(run, match[2]) : shelf());
  window.scrollTo(0, 0);
}

window.addEventListener("hashchange", route);
route();
