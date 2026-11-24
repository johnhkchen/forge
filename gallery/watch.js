// Forge gallery: a filmed take played here, on its set, with its cast drawn as flat cards or as meshes. #/watch/<take>
//
// A take that has been cast (shots/<take>/cast-<clip>.json) has one .glb a role: that character with the whole
// take played into its skeleton. This page stands the set up, brings every role on, and plays them together from
// one clock, so it can be paused and wound back and forth. Each character whose run has baked cards
// (scripts/impostor/bake_impostor.py) can be drawn as cards riding the same skeleton: one card a bone, as on the
// cards page, and in every knee, elbow, hip and shoulder a piece of the real model that bends as the skeleton
// pulls it (scripts/impostor/bake_joints.py), when the cards have them. The eye can be any of the set's own
// cameras, or free.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { eyeInBone, choose, place, corners, marchSteps, density, behindOf } from "./impostor-math.js";
import { CARD_VERTEX, CARD_FRAGMENT, TOON_FRAGMENT, INK_FRAGMENT, picture, lineUniforms, setHeadGrid, setBalls, setBehind, sheetBalls, skinFor, skinMeshes } from "./impostor.js";
import { LOOKS, lookOf, bakedFor, modelsOf, paintOf, setPaint, cardLine, cardNumber, Screen, withoutHeads } from "./looks.js";
import { faceFolderOf, faceMarks } from "./face-marks.js";

const WATCH_LOOKS = ["pixel-both", "pixel-screen", "comic", "joe"];
const LIGHT = [-0.55, 0.5, 0.67];

// A skinned mesh drawn the comic way, or (inkM over 0, back faces) its ink shell. A mesh with no picture wrapped
// on it has a colour at each point instead.
const BODY_VERTEX = `
#include <common>
#include <skinning_pars_vertex>
uniform float inkM;
attribute vec4 color;
varying vec2 vUv;
varying vec3 vFacing;
varying vec3 vColor;
void main() {
  vUv = uv;
  vColor = color.rgb;
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
const PLAIN_FRAGMENT = `
uniform vec3 light;
uniform vec3 shadeMid;
uniform vec3 shadeDark;
uniform vec2 edges;
uniform float punch;
uniform float rim;
uniform vec3 tint;
varying vec3 vFacing;
varying vec3 vColor;
void main() {
  vec3 toEye = normalize(vFacing) * (gl_FrontFacing ? 1.0 : -1.0);
  float facing = dot(toEye, light);
  vec3 tone = facing > edges.x ? vec3(1.0) : facing > edges.y ? shadeMid : shadeDark;
  vec3 own = vColor * tint;
  vec3 paint = mix(vec3(dot(own, vec3(0.2126, 0.7152, 0.0722))), own, punch) * 1.5;
  gl_FragColor = vec4(paint * tone + rim * pow(1.0 - clamp(toEye.z, 0.0, 1.0), 3.0) * step(edges.x, facing), 1.0);
  #include <colorspace_fragment>
}`;

class TakeViewer {
  constructor(pane, { take, set, runs, loader, state, onReady }) {
    Object.assign(this, { take, set, runs, loader, state });
    this.el = pane;
    this.status = pane.querySelector(".status");
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    const air = set?.world?.color || [0.92, 0.9, 0.86];
    this.renderer.setClearColor(new THREE.Color(air[0], air[1], air[2]).convertLinearToSRGB());
    pane.prepend(this.renderer.domElement);
    this.screen = new Screen(this.renderer);
    this.scene = new THREE.Scene();
    this.scene.environment = new THREE.PMREMGenerator(this.renderer).fromScene(new RoomEnvironment(), 0.04).texture;
    this.scene.environmentIntensity = 0.55;
    this.free = new THREE.PerspectiveCamera(36, 16 / 9, 0.1, 300);
    this.camera = this.free;
    this.controls = new OrbitControls(this.free, this.renderer.domElement);
    this.fixed = {};
    for (const [name, card] of Object.entries(set?.cameras || {})) {
      const cam = new THREE.PerspectiveCamera(THREE.MathUtils.radToDeg(2 * Math.atan(36 / (16 / 9) / 2 / card.lens_mm)), 16 / 9, 0.1, 300); // a lens on a 36 mm wide sensor
      cam.position.fromArray(card.at);
      cam.lookAt(new THREE.Vector3().fromArray(card.aim));
      this.fixed[name] = cam;
    }
    this.paint = paintOf(LIGHT);
    this.look = lookOf(state.look);
    setPaint(this.paint, this.look);
    this.cast = [];
    this.time = 0;
    this.length = 0.1;
    this.clock = new THREE.Clock();
    this.resize = new ResizeObserver(() => this.layout());
    this.resize.observe(pane);
    this.layout();
    this.ready = this.fill().then(onReady).catch((err) => { this.status.textContent = "Couldn't bring this take on."; this.error = String(err?.stack || err); console.error(err); });
    this.frame = requestAnimationFrame(() => this.tick());
  }

  async fill() {
    const { set } = this;
    if (set) {
      if (set.glb) {
        const model = (await this.loader.loadAsync(`sets/${set.id}/${set.glb}`)).scene;
        model.position.fromArray(set.geometry?.move || [0, 0, 0]);
        model.rotation.y = THREE.MathUtils.degToRad(set.geometry?.turn_deg || 0);
        this.scene.add(model);
      }
      if (set.ground) {
        const ground = new THREE.Mesh(new THREE.PlaneGeometry(set.ground.size_m || 40, set.ground.size_m || 40), new THREE.MeshStandardMaterial({ color: new THREE.Color(...(set.ground.color || [0.8, 0.78, 0.74])), roughness: 0.9 }));
        ground.rotation.x = -Math.PI / 2;
        ground.position.y = (set.ground.y || 0) - 0.004;
        this.scene.add(ground);
      }
      for (const flat of [set.backdrop, ...(set.signs || [])].filter(Boolean)) { // painted flats: the backdrop and any signs
        const map = await new THREE.TextureLoader().loadAsync(`sets/${set.id}/${flat.image}`);
        map.colorSpace = THREE.SRGBColorSpace;
        const sheet = new THREE.Mesh(new THREE.PlaneGeometry(flat.width_m, flat.height_m), new THREE.MeshBasicMaterial({ map, toneMapped: false }));
        sheet.position.fromArray(flat.center);
        sheet.rotation.y = THREE.MathUtils.degToRad(flat.heading || 0);
        this.scene.add(sheet);
      }
      for (const item of set.dressing || []) {
        const slot = set.slots[item.slot];
        const prop = (await this.loader.loadAsync(`sets/${set.id}/${item.detail || item.glb}`)).scene;
        prop.position.fromArray(slot.at);
        prop.rotation.y = THREE.MathUtils.degToRad(slot.heading || 0);
        this.scene.add(prop);
      }
      for (const light of set.lights || []) {
        const lamp = new THREE.DirectionalLight(new THREE.Color(...(light.color || [1, 1, 1])), light.kind === "sun" ? 0.9 : 0.4); // no tone mapping here (the looks draw by way of a picture of their own), so the lamps are gentler than on the set's page
        lamp.position.fromArray(light.at);
        lamp.target.position.fromArray(light.aim || [0, 0, 0]);
        this.scene.add(lamp, lamp.target);
      }
    }
    const box = new THREE.Box3();
    for (const m of Object.values(set?.marks || {})) box.expandByPoint(new THREE.Vector3(m.at[0], 0, m.at[1])).expandByPoint(new THREE.Vector3(m.at[0], 1.8, m.at[1]));
    if (box.isEmpty()) box.set(new THREE.Vector3(-2, 0, -2), new THREE.Vector3(2, 1.8, 2));
    const centre = box.getCenter(new THREE.Vector3()), size = Math.max(box.getSize(new THREE.Vector3()).length(), 4);
    this.free.position.set(centre.x + size * 0.35, size * 0.45, centre.z + size * 1.2);
    this.controls.target.set(centre.x, 0.9, centre.z);
    this.controls.update();
    this.status.textContent = "Bringing the cast on…";
    for (const role of this.take.roles) this.cast.push(await this.bringOn(role));
    this.length = Math.max(...this.cast.map((c) => c.seconds), 0.1);
    await this.useLook(this.state.look);
    this.useEye(this.state.eye);
    this.status.remove();
  }

  // One role: its file with the take played in, its meshes painted the comic way with an ink shell, its bones.
  async bringOn(role) {
    const gltf = await this.loader.loadAsync(`shots/${this.take.id}/${role.glb}`);
    const holder = new THREE.Group();
    holder.scale.setScalar(1 / (role.size || 1));
    holder.add(gltf.scene);
    this.scene.add(holder);
    if (role.mark) { // a fighter goes on his mark facing the other: the floor under his resting hips is what stands on it
      const hips = gltf.scene.getObjectByName("hips");
      const turn = THREE.MathUtils.degToRad(role.mark.facing_deg || 0);
      const off = new THREE.Vector3(hips?.position.x || 0, 0, hips?.position.z || 0).applyAxisAngle(new THREE.Vector3(0, 1, 0), turn);
      holder.position.set(role.mark.at[0] - off.x, 0, role.mark.at[1] - off.z);
      holder.rotation.y = turn;
    }
    const actor = { role, holder, bones: {}, meshes: [], lines: [], quads: [], held: {}, run: this.runs.find((r) => r.id === role.run || r.id === role.character) };
    const ink = new THREE.ShaderMaterial({ vertexShader: BODY_VERTEX, fragmentShader: INK_FRAGMENT, side: THREE.BackSide, uniforms: { inkM: { value: 0.014 }, ink: { value: new THREE.Color(0x1c1721) } } });
    const found = [];
    gltf.scene.traverse((o) => {
      if (o.isBone) actor.bones[o.name] = o;
      if (o.isSkinnedMesh && !o.userData.under) found.push(o); else if (o.isMesh) o.visible = false; // skin that worn gear hides, and a bone's display shape
    });
    for (const mesh of found) {
      const was = mesh.material, map = was.map;
      mesh.material = map
        ? new THREE.ShaderMaterial({ vertexShader: BODY_VERTEX, fragmentShader: TOON_FRAGMENT, side: THREE.DoubleSide,
          uniforms: { ...this.paint, inkM: { value: 0 }, map: { value: map }, soften: { value: Math.max(0, Math.log2(map.image.width / (/head/i.test(was.name) ? 512 : 256))) } } })
        : new THREE.ShaderMaterial({ vertexShader: BODY_VERTEX, fragmentShader: PLAIN_FRAGMENT, side: THREE.DoubleSide,
          uniforms: { ...this.paint, inkM: { value: 0 }, tint: { value: mesh.geometry.attributes.color ? new THREE.Color(1, 1, 1) : (was.color || new THREE.Color(0.8, 0.8, 0.8)) } } });
      if (!mesh.geometry.attributes.color) { // no colour at its points: white, so the tint alone colours it
        mesh.geometry.setAttribute("color", new THREE.BufferAttribute(new Float32Array(mesh.geometry.attributes.position.count * 4).fill(1), 4));
      }
      const line = new THREE.SkinnedMesh(mesh.geometry, ink);
      line.bind(mesh.skeleton, mesh.bindMatrix);
      line.frustumCulled = mesh.frustumCulled = false;
      mesh.parent.add(line);
      actor.meshes.push(mesh);
      actor.lines.push(line);
    }
    // which way the face looks, as the head bone has it: the figure rests facing +z
    holder.updateMatrixWorld(true);
    actor.front = actor.bones.head ? new THREE.Vector3(0, 0, 1).applyQuaternion(holder.getWorldQuaternion(new THREE.Quaternion())).applyQuaternion(actor.bones.head.getWorldQuaternion(new THREE.Quaternion()).invert()) : new THREE.Vector3(0, 0, 1);
    // A drawn face for the mesh when it is shown as pixel art: the marks the cards' bake kept, dropped onto this mesh's head.
    const faces = faceFolderOf(actor.run, "detailed");
    if (faces && actor.bones.head && actor.meshes.length) {
      const baked = await fetch(`runs/${encodeURIComponent(actor.run.id)}/${faces}/impostor.json`).then((r) => r.json()).catch(() => null);
      if (baked?.face?.marks?.length) actor.face = faceMarks(baked.face.marks, actor.bones.head, actor.meshes);
    }
    actor.mixer = new THREE.AnimationMixer(gltf.scene);
    const clip = gltf.animations[0];
    if (clip) actor.mixer.clipAction(clip).play();
    actor.seconds = clip ? clip.duration : 0;
    actor.cards = new THREE.Group();
    this.scene.add(actor.cards);
    return actor;
  }

  // Change the look: the paint's numbers, and for each of the cast the baked cards that look reads.
  async useLook(id) {
    this.look = lookOf(id);
    this.state.look = this.look.id;
    setPaint(this.paint, this.look);
    for (const [who, actor] of this.cast.entries()) {
      if (!actor.run?.cards?.length) continue;
      const models = modelsOf(actor.run);
      const model = (models.find((m) => m.id === "detailed") || models[0]).id; // the detailed model's cards when there are some
      const folder = `runs/${encodeURIComponent(actor.run.id)}/${bakedFor(actor.run, this.look, model).folder}`;
      // what this look does with the sheet's ink line: a shell behind the surface, or one line on the finished picture
      const line = () => { const told = cardLine(actor.card, this.look); actor.quads.forEach((quad, p) => { quad.material.uniforms.line.value = told.line; quad.material.uniforms.who.value = told.ids ? cardNumber(who, p) : 1; }); };
      if (folder === actor.folder) { line(); continue; }
      actor.folder = folder;
      const card = await fetch(`${folder}/impostor.json`).then((r) => r.json());
      const sheet = card.sets[card.default_views];
      const [colour, data, skin] = await Promise.all([picture(`${folder}/${sheet.color}`, true, card.nearest), picture(`${folder}/${sheet.data}`, false), skinFor(folder, card, this.loader)]);
      actor.sheet?.colour.dispose();
      actor.sheet?.data.dispose();
      actor.joined?.dispose();
      actor.skin?.dispose();
      Object.assign(actor, { card, sheet: { ...sheet, colour, data, dirs: sheet.views.map((v) => v.d) }, held: {} });
      actor.joints = sheetBalls(card, actor.sheet);
      actor.jointAt = (name) => { const e = actor.bones[name]?.matrixWorld.elements; return e && [e[12], e[13], e[14]]; };
      actor.cards.clear();
      actor.quads = card.parts.map((part) => {
        const shape = new THREE.BufferGeometry();
        shape.setAttribute("position", new THREE.BufferAttribute(new Float32Array(12), 3));
        shape.setAttribute("uv", new THREE.BufferAttribute(new Float32Array(8), 2));
        shape.setIndex([0, 1, 2, 0, 2, 3]);
        const quad = new THREE.Mesh(shape, new THREE.ShaderMaterial({ vertexShader: CARD_VERTEX, fragmentShader: CARD_FRAGMENT, side: THREE.DoubleSide, uniforms: {
          colourMap: { value: colour }, dataMap: { value: data }, facingToEye: { value: new THREE.Matrix3() }, sheetSize: { value: new THREE.Vector2(...sheet.size) }, pxPerM: { value: density(card, part) },
          cell: { value: new THREE.Vector4() }, anchor: { value: new THREE.Vector2() }, heights: { value: new THREE.Vector2() }, back: { value: new THREE.Vector4() }, lean: { value: new THREE.Vector2() },
          deep: { value: new THREE.Vector3() }, size: { value: 1 }, wallM: { value: card.march.wall_m }, steps: { value: 0 }, depthM: { value: part.depth_m }, share: { value: 1 }, mix_: { value: 0 }, ...lineUniforms(), ...this.paint } }));
        quad.frustumCulled = false;
        quad.matrixAutoUpdate = false;
        if (part.name === "head") { quad.layers.enable(1); quad.material.uniforms.headPass = this.screen.told.headPass; } // it may go on the finer grid
        actor.cards.add(quad);
        return quad;
      });
      // the pieces of the model in the big joints, riding the same skeleton
      actor.skin = skin;
      actor.joined = skinMeshes(skin, actor.bones, this.paint);
      if (actor.joined) actor.cards.add(actor.joined.group);
      line();
    }
  }

  useEye(name) {
    this.state.eye = this.fixed[name] ? name : "";
    this.camera = this.fixed[name] || this.free;
    this.controls.enabled = !this.fixed[name];
  }

  // Put every card of one of the cast where its bone is now, for where the eye is now.
  setCards(actor) {
    const { card, sheet } = actor;
    const eye = this.camera.position.toArray();
    const toEye = new THREE.Matrix4();
    card.parts.forEach((part, p) => {
      const bone = actor.bones[part.bone], quad = actor.quads[p];
      if (!bone) { quad.visible = false; return; }
      const world = bone.matrixWorld.elements;
      const pick = choose(sheet.dirs, eyeInBone(world, part.center, eye), actor.held[part.name], card.hold_deg, card.blend_deg);
      actor.held[part.name] = pick.first;
      const cell = sheet.cells[part.name][pick.first];
      const where = place(sheet.views[pick.first], world, part.center, eye);
      const spots = corners(where, setBehind(quad, cell, behindOf(sheet, part.name, pick.first)), density(card, part), true);
      const at = quad.geometry.attributes.position, uv = quad.geometry.attributes.uv;
      spots.world.forEach((s, k) => at.setXYZ(k, s[0], s[1], s[2]));
      spots.sheet.forEach((s, k) => uv.setXY(k, s[0], s[1]));
      at.needsUpdate = uv.needsUpdate = true;
      const u = quad.material.uniforms;
      u.cell.value.set(cell[0], cell[1], cell[2], cell[3]);
      u.anchor.value.set(cell[4], cell[5]);
      u.heights.value.set(cell[6], cell[7]);
      u.back.value.set(...where.back);
      u.lean.value.set(...where.lean);
      u.deep.value.set(...where.deep);
      u.size.value = where.size;
      u.steps.value = marchSteps(where, cell, density(card, part), card.march);
      u.facingToEye.value.setFromMatrix4(toEye.multiplyMatrices(this.camera.matrixWorldInverse, bone.matrixWorld)).multiplyScalar(1 / where.size);
      setBalls(quad, actor.joints[p], part.center, world, this.camera, actor.jointAt, where.size, Boolean(actor.joined));
      if (part.name === "head") setHeadGrid(quad, this.screen, this.look, this.camera, where.head);
    });
    actor.joined?.set(this.camera, this.look, card, this.cast.indexOf(actor));
  }

  tick() {
    this.frame = requestAnimationFrame(() => this.tick());
    const dt = Math.min(this.clock.getDelta(), 0.1);
    if (!this.cast.length || !this.cast[0].mixer) return;
    if (this.state.playing) this.time = (this.time + dt) % this.length;
    for (const actor of this.cast) actor.mixer.setTime(Math.min(this.time, actor.seconds));
    this.scene.updateMatrixWorld();
    if (this.camera === this.free) this.controls.update();
    this.camera.updateMatrixWorld();
    for (const actor of this.cast) {
      const cards = this.state.cards && Boolean(actor.sheet); // one with no baked cards is drawn as a mesh either way
      actor.cards.visible = cards;
      for (const mesh of actor.meshes) mesh.visible = !cards;
      for (const line of actor.lines) line.visible = !cards && this.look.hull !== false;
      if (actor.face) actor.face.visible = !cards && Boolean(this.look.screen?.rows); // the drawn face is for a mesh drawn small
      if (cards) this.setCards(actor);
    }
    this.screen.render(this.scene, this.camera, this.state.cards ? this.look : withoutHeads(this.look));
    this.onTime?.(this.time, this.length);
  }

  layout() {
    this.renderer.setSize(this.el.clientWidth, this.el.clientHeight, false);
    const aspect = this.el.clientWidth / Math.max(1, this.el.clientHeight);
    for (const cam of [this.free, ...Object.values(this.fixed)]) { cam.aspect = aspect; cam.updateProjectionMatrix(); }
  }

  report() {
    return { ready: this.cast.length === this.take.roles.length && this.cast.every((c) => c.mixer), take: this.take.id, time: this.time, length: this.length, look: this.look.id, eye: this.state.eye || "free",
      cards: this.state.cards, cast: this.cast.map((c) => ({ role: c.role.role, run: c.run?.id || null, cards: c.folder || null, quads: c.quads.length, joints: c.joined ? c.skin.pieces.length : 0, meshes: c.meshes.length, face: c.face ? { marks: c.face.geometry.index.count / 6, dropped: c.face.userData.dropped } : null })), error: this.error || null };
  }

  dispose() {
    cancelAnimationFrame(this.frame);
    this.resize.disconnect();
    this.controls.dispose();
    for (const actor of this.cast) { actor.sheet?.colour.dispose(); actor.sheet?.data.dispose(); actor.joined?.dispose(); actor.skin?.dispose(); }
    this.screen.dispose();
    this.renderer.dispose();
    delete window.forgeWatch;
  }
}

const clock = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

export function watchPage({ take, sets, runs, h, loader }) {
  const set = sets.find((s) => s.id === take.set);
  const state = { look: "pixel-both", eye: set?.cameras?.crew ? "crew" : Object.keys(set?.cameras || {})[0] || "", cards: true, playing: true };
  const pane = h("div", { class: "pane watch-pane" }, h("div", { class: "status" }, "Setting the stage…"));
  const stage = h("div", { class: "stage clay-surface" }, pane);
  let viewer = null;
  const chip = (label, pressed, onclick) => h("button", { class: "chip clay-chip", type: "button", "aria-pressed": String(pressed), onclick }, label);
  const group = (label, chips) => h("div", { class: "versions", role: "group", "aria-label": label }, h("span", { class: "row-label" }, label), chips);
  const press = (chips, i) => chips.forEach((c, k) => c.setAttribute("aria-pressed", String(k === i)));
  const asChips = [chip("Cards", true, () => { press(asChips, 0); state.cards = true; }), chip("Meshes", false, () => { press(asChips, 1); state.cards = false; })];
  const looks = WATCH_LOOKS.map((id) => LOOKS.find((l) => l.id === id));
  const lookChips = looks.map((look, i) => chip(look.name, look.id === state.look, () => { press(lookChips, i); viewer.useLook(look.id); }));
  const eyes = [...Object.keys(set?.cameras || {}), ""];
  const eyeName = (name) => (name ? `${name[0].toUpperCase()}${name.slice(1).replace(/_/g, " ")}` : "Look around");
  const eyeChips = eyes.map((name, i) => chip(eyeName(name), name === state.eye, () => { press(eyeChips, i); viewer.useEye(name); }));
  const play = h("button", { class: "clay-button watch-play", type: "button", onclick: () => { state.playing = !state.playing; play.textContent = state.playing ? "Pause" : "Play"; } }, "Pause");
  const wind = h("input", { class: "watch-wind", type: "range", min: "0", max: "1000", value: "0", "aria-label": "Wind the take back and forth" });
  const told = h("span", { class: "watch-time" }, "0:00");
  let winding = false;
  wind.addEventListener("input", () => { winding = true; viewer.time = (Number(wind.value) / 1000) * viewer.length; });
  wind.addEventListener("change", () => { winding = false; });
  const who = take.roles.map((r) => (runs.find((x) => x.id === r.run || x.id === r.character)?.name || r.role).split(" ").slice(0, 2).join(" ")).join(", ");
  const note = h("p", { class: "about" });
  const page = h("article", { class: "object cards-page watch-page" },
    h("a", { class: "back", href: take.set ? `#/set/${encodeURIComponent(take.set)}` : "#/" }, `← ${set?.title || "Everything"}`),
    h("h1", {}, take.title),
    h("p", { class: "lede" }, take.about || `${who}, playing the take here on its set.`),
    group("Drawn as", asChips),
    group("In the look", lookChips),
    group("Seen from", eyeChips),
    stage,
    h("div", { class: "watch-bar" }, play, wind, told),
    note,
  );
  queueMicrotask(() => {
    viewer = new TakeViewer(pane, { take, set, runs, loader, state, onReady: () => {
      const drawn = viewer.cast.filter((c) => c.sheet).length;
      note.textContent = `${who}. As cards, each is a handful of flat pictures riding the same skeleton the meshes do${drawn < viewer.cast.length ? `; ${viewer.cast.length - drawn} of them has no cards baked yet and stays a mesh` : ""}. No sound.`;
    } });
    viewer.onTime = (t, length) => { if (!winding) wind.value = String(Math.round((t / length) * 1000)); told.textContent = `${clock(t)} of ${clock(length)}`; };
    window.forgeWatch = { state: () => viewer.report(), viewer, look: (id) => viewer.useLook(id), eye: (name) => viewer.useEye(name),
      set: (what) => { Object.assign(state, what); if (what.time !== undefined) viewer.time = what.time; },
      // the free eye brought up close to one of the cast, for a picture
      THREE,
      // the free eye stood in front of one of the cast's faces, a little to one side
      face: (i, away = 1.3) => {
        const actor = viewer.cast[i], head = actor.bones.head;
        const at = new THREE.Vector3().setFromMatrixPosition(head.matrixWorld);
        at.y += 0.1 / (actor.role.size || 1);
        const out = actor.front.clone().applyQuaternion(head.getWorldQuaternion(new THREE.Quaternion()));
        out.y = 0;
        out.normalize().applyAxisAngle(new THREE.Vector3(0, 1, 0), 0.3);
        viewer.useEye("");
        viewer.controls.target.copy(at);
        viewer.free.position.copy(at).addScaledVector(out, away).add(new THREE.Vector3(0, 0.05 * away, 0));
        viewer.controls.update();
      },
      near: (i, away = 2.6) => {
        const hips = new THREE.Vector3().setFromMatrixPosition(viewer.cast[i].bones.hips.matrixWorld);
        viewer.useEye("");
        viewer.controls.target.set(hips.x, hips.y + 0.1, hips.z);
        viewer.free.position.set(hips.x + away * 0.25, hips.y + 0.35, hips.z + away);
        viewer.controls.update();
      } };
  });
  page.dispose = () => viewer?.dispose();
  return page;
}
