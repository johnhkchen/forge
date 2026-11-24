// Forge gallery: a toon drawn as flat cards, beside the real model. #/cards/<run>
//
// The toon is cut into rigid parts, one per bone, and each part was pictured ahead of time from a fixed set of
// directions (scripts/impostor/bake_impostor.py). Here a skeleton plays any clip; every bone gets one flat card
// that faces you and shows the picture taken from nearest to where you are as that bone sees it, turned and
// foreshortened to how the bone now shows (impostor-math.js). Each picture also holds, for every pixel, which way
// the surface faces and how far it stands toward you. The first gives light and shade. The second slides each
// pixel to where the real surface would be, lets cards hide each other, and lets the ropes of the ring pass in
// front of an arm.
//
// The same skeleton drives both halves of the view. Left: the cards, the mesh hidden. Right: the mesh, drawn
// the comic way too (flat tones from a light fixed to the eye, an ink line), so the two can be told apart only
// by what the cards get wrong.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { eyeInBone, choose, place, corners, marchSteps, density } from "./impostor-math.js";
import { LOOKS, lookOf, bakedFor, modelsOf, paintOf, setPaint, Screen } from "./looks.js";

const PAPER = 0xebe6dc;

export const CARD_VERTEX = `
varying vec2 vSheet;
varying vec3 vView;
void main() {
  vSheet = uv;
  vView = (viewMatrix * vec4(position, 1.0)).xyz;
  gl_Position = projectionMatrix * vec4(vView, 1.0);
}`;

// One card. The colour sheet holds flat colour and the ink line; the data sheet holds the facing (two numbers,
// unfolded here) and the depth (0: nothing there). A pixel of the card looks down a line through the picture
// (impostor-math.js: place) and shows the first place where the picture's surface is as high as the line: a
// search in short steps, then halved in on. Mixing two views is done by a fixed pattern of pixels, each pixel
// one view or the other, so every pixel still has one true depth.
export const CARD_FRAGMENT = `
uniform mat4 projectionMatrix;
uniform sampler2D colourMap;
uniform sampler2D dataMap;
uniform vec2 sheetSize;
uniform float pxPerM;
uniform vec4 cell;
uniform vec2 anchor;
uniform vec2 heights;
uniform vec4 back;
uniform vec2 lean;
uniform vec3 deep;
uniform float size;
uniform float depthM;
uniform float wallM;
uniform int steps;
uniform mat3 facingToEye;
uniform float share;
uniform int mix_;
uniform vec3 light;
uniform vec3 shadeMid;
uniform vec3 shadeDark;
uniform vec2 edges;
uniform float punch;
uniform float rim;
varying vec2 vSheet;
varying vec3 vView;
float pattern(vec2 at) {
  int x = int(mod(at.x, 4.0)), y = int(mod(at.y, 4.0));
  int i = y * 4 + x;
  float v = i == 0 ? 0.0 : i == 1 ? 8.0 : i == 2 ? 2.0 : i == 3 ? 10.0 : i == 4 ? 12.0 : i == 5 ? 4.0 : i == 6 ? 14.0 : i == 7 ? 6.0
    : i == 8 ? 3.0 : i == 9 ? 11.0 : i == 10 ? 1.0 : i == 11 ? 9.0 : i == 12 ? 15.0 : i == 13 ? 7.0 : i == 14 ? 13.0 : 5.0;
  return v / 16.0 + 1.0 / 32.0;
}
vec3 unfold(vec2 e) {
  e = e * 2.0 - 1.0;
  vec3 n = vec3(e, 1.0 - abs(e.x) - abs(e.y));
  float t = clamp(-n.z, 0.0, 1.0);
  n.x += n.x >= 0.0 ? -t : t;
  n.y += n.y >= 0.0 ? -t : t;
  return normalize(n);
}
vec2 inPicture(vec2 p) {
  return vec2(back.x * p.x + back.y * p.y, back.z * p.x + back.w * p.y);
}
// The data sheet at a place of the picture: is there surface here, how high, and the pixel's numbers.
bool readAt(vec2 xy, out float height, out vec3 data) {
  vec2 c = xy * pxPerM + anchor;
  data = textureLod(dataMap, (cell.xy + c) / sheetSize, 0.0).rgb;
  height = (data.z * 2.0 - 1.0) * depthM;
  return c.x >= 0.0 && c.x < cell.z && c.y >= 0.0 && c.y < cell.w && data.z > 0.5 / 255.0;
}
void main() {
  vec2 xy;
  float height;
  vec3 data;
  bool ok;
  if (steps > 0) {
    float top = heights.y + 0.002, bottom = heights.x - 0.002;
    float above = top, below = bottom;
    bool found = false;
    for (int i = 1; i <= 32; i++) {
      if (i > steps || found) break;
      float at = top + (bottom - top) * float(i) / float(steps);
      if (readAt(inPicture(vSheet - at * lean), height, data) && height >= at) { below = at; found = true; } else above = at;
    }
    if (!found) discard;
    for (int k = 0; k < 5; k++) {
      float mid = (above + below) * 0.5;
      if (readAt(inPicture(vSheet - mid * lean), height, data) && height >= mid) below = mid; else above = mid;
    }
    xy = inPicture(vSheet - below * lean);
    ok = readAt(xy, height, data) && height - below < wallM + (top - bottom) / float(steps) / 32.0;
  } else {
    xy = inPicture(vSheet);
    ok = readAt(xy, height, data);
  }
  if (!ok) discard;
  vec4 colour = textureLod(colourMap, (cell.xy + xy * pxPerM + anchor) / sheetSize, 0.0);
  if (colour.a < 0.5) discard;
  if (mix_ == 1 && pattern(gl_FragCoord.xy) >= share) discard;
  if (mix_ == 2 && pattern(gl_FragCoord.xy) < share) discard;
  vec3 seen = facingToEye * unfold(data.xy);
  float facing = dot(seen, light);
  vec3 tone = facing > edges.x ? vec3(1.0) : facing > edges.y ? shadeMid : shadeDark;
  float out_ = (xy.x * deep.x + xy.y * deep.y + height * deep.z) * size;
  vec3 point = vView + normalize(-vView) * out_;
  vec4 clip = projectionMatrix * vec4(point, 1.0);
  gl_FragDepth = clip.z / clip.w * 0.5 + 0.5;
  vec3 paint = mix(vec3(dot(colour.rgb, vec3(0.2126, 0.7152, 0.0722))), colour.rgb, punch);
  gl_FragColor = vec4(paint * tone + rim * pow(1.0 - clamp(seen.z, 0.0, 1.0), 3.0) * step(edges.x, facing), 1.0);
  #include <colorspace_fragment>
}`;

// The real model the comic way (toon.py's paint, near enough): the texture read small and soft, its light-to-dark
// snapped to a few steps, then one of three flat tones by how far the surface faces a light fixed to the eye.
const TOON_VERTEX = `
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
export const TOON_FRAGMENT = `
uniform sampler2D map;
uniform float soften;
uniform vec3 light;
uniform vec3 shadeMid;
uniform vec3 shadeDark;
uniform vec2 edges;
uniform float punch;
uniform float rim;
varying vec2 vUv;
varying vec3 vFacing;
vec3 toHsv(vec3 c) {
  vec4 k = vec4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
  vec4 p = mix(vec4(c.bg, k.wz), vec4(c.gb, k.xy), step(c.b, c.g));
  vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
  float d = q.x - min(q.w, q.y);
  return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + 1e-10)), d / (q.x + 1e-10), q.x);
}
vec3 fromHsv(vec3 c) {
  vec3 p = abs(fract(c.xxx + vec3(1.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - 3.0);
  return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}
void main() {
  vec3 hsv = toHsv(texture2D(map, vUv, soften).rgb);
  float seen = pow(clamp(hsv.z * 1.5, 0.0, 1.0), 1.0 / 2.2) * 0.86 + 0.14;
  float snapped = max(floor((seen + 0.0625) * 8.0) / 8.0, 0.06875);
  vec3 paint = fromHsv(vec3(hsv.x, min(hsv.y * 0.96, 1.0), pow(snapped, 2.2)));
  vec3 toEye = normalize(vFacing) * (gl_FrontFacing ? 1.0 : -1.0);
  float facing = dot(toEye, light);
  vec3 tone = facing > edges.x ? vec3(1.0) : facing > edges.y ? shadeMid : shadeDark;
  paint = mix(vec3(dot(paint, vec3(0.2126, 0.7152, 0.0722))), paint, punch);
  gl_FragColor = vec4(paint * tone + rim * pow(1.0 - clamp(toEye.z, 0.0, 1.0), 3.0) * step(edges.x, facing), 1.0);
  #include <colorspace_fragment>
}`;
export const INK_FRAGMENT = `
uniform vec3 ink;
void main() {
  gl_FragColor = vec4(ink, 1.0);
  #include <colorspace_fragment>
}`;

export async function picture(url, colour, blocky = false) {
  const map = await new THREE.TextureLoader().loadAsync(url);
  map.colorSpace = colour ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  map.generateMipmaps = false;
  map.minFilter = map.magFilter = colour && !blocky ? THREE.LinearFilter : THREE.NearestFilter;
  return map;
}

class CardViewer {
  constructor(stage, { run, baked, set, state, onFacts, loader }) {
    Object.assign(this, { run, baked, set, state, onFacts, loader }); // the gallery's own loader: it can read the set's packed mesh
    this.look = lookOf(state.look);
    this.folder = "";
    this.el = stage;
    this.status = stage.querySelector(".status");
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(PAPER);
    this.screen = new Screen(this.renderer);
    stage.prepend(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.scene.environment = new THREE.PMREMGenerator(this.renderer).fromScene(new RoomEnvironment(), 0.04).texture;
    this.camera = new THREE.PerspectiveCamera(30, 1, 0.1, 200);
    this.camera.position.set(2.0, 2.3, 4.5);
    this.scene.add(this.camera);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(0, 0.95, 0);
    this.controls.minDistance = 1.2;
    this.controls.maxDistance = 30;
    this.controls.update();
    this.cards = new THREE.Group();
    this.edges = new THREE.Group();
    this.scene.add(this.cards, this.edges);
    this.sheets = {};
    this.held = {};
    this.swaps = [];
    this.clock = new THREE.Clock();
    this.resize = new ResizeObserver(() => this.layout());
    this.resize.observe(stage);
    this.layout();
    this.ready = this.fill().catch((err) => { this.status.textContent = "Couldn't load this toon."; this.error = String(err?.stack || err); console.error(err); });
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
      for (const light of set.lights || []) {
        const lamp = new THREE.DirectionalLight(new THREE.Color(...(light.color || [1, 1, 1])), 0.9);
        lamp.position.fromArray(light.at);
        lamp.target.position.fromArray(light.aim || [0, 0, 0]);
        this.scene.add(lamp, lamp.target);
      }
    }
    await this.useLook(this.state.look);
    await this.play(this.state.motion);
    this.status.remove();
  }

  // Which set of pictures to draw from (26 a part, 62, ...): its two sheets are fetched the first time.
  async useViews(name) {
    if (!this.sheets[name]) {
      const sheet = this.card.sets[name];
      const [colour, data] = await Promise.all([picture(`${this.folder}/${sheet.color}`, true, this.card.nearest), picture(`${this.folder}/${sheet.data}`, false)]);
      this.sheets[name] = { ...sheet, colour, data, dirs: sheet.views.map((v) => v.d) };
    }
    this.state.views = name;
    this.sheet = this.sheets[name];
    this.held = {};
    this.buildCards();
    this.onFacts?.();
  }

  // Two cards a part (the second only shows while two views are being mixed) and an outline for each.
  buildCards() {
    this.cards.clear();
    this.edges.clear();
    const { card, sheet } = this;
    const line = new THREE.LineBasicMaterial({ color: 0x44679b, depthTest: false });
    this.parts = card.parts.map((part) => {
      const quads = [0, 1].map(() => {
        const shape = new THREE.BufferGeometry();
        shape.setAttribute("position", new THREE.BufferAttribute(new Float32Array(12), 3));
        shape.setAttribute("uv", new THREE.BufferAttribute(new Float32Array(8), 2));
        shape.setIndex([0, 1, 2, 0, 2, 3]);
        const paint = new THREE.ShaderMaterial({
          vertexShader: CARD_VERTEX, fragmentShader: CARD_FRAGMENT, side: THREE.DoubleSide,
          uniforms: {
            colourMap: { value: sheet.colour }, dataMap: { value: sheet.data }, facingToEye: { value: new THREE.Matrix3() },
            sheetSize: { value: new THREE.Vector2(...sheet.size) }, pxPerM: { value: density(card, part) }, cell: { value: new THREE.Vector4() },
            anchor: { value: new THREE.Vector2() }, heights: { value: new THREE.Vector2() }, back: { value: new THREE.Vector4() },
            lean: { value: new THREE.Vector2() }, deep: { value: new THREE.Vector3() }, size: { value: 1 }, wallM: { value: card.march.wall_m }, steps: { value: 0 },
            depthM: { value: part.depth_m }, share: { value: 1 }, mix_: { value: 0 }, ...this.paint,
          },
        });
        const quad = new THREE.Mesh(shape, paint);
        quad.frustumCulled = false;
        quad.matrixAutoUpdate = false;
        this.cards.add(quad);
        return quad;
      });
      const outline = new THREE.LineLoop(quads[0].geometry, line);
      outline.frustumCulled = false;
      outline.renderOrder = 5;
      this.edges.add(outline);
      return { ...part, quads };
    });
  }

  // Bring a clip on: its .glb holds the same toon and skeleton, so the cards ride whichever is playing.
  async play(motion) {
    this.state.motion = motion;
    const gltf = await this.loader.loadAsync(motion.glb);
    if (this.state.motion !== motion) return;
    if (this.model) this.scene.remove(this.model);
    this.model = new THREE.Group();
    this.model.add(gltf.scene);
    if (motion.at) this.model.position.set(motion.at[0], 0, motion.at[1]);
    this.model.rotation.y = THREE.MathUtils.degToRad(motion.facing_deg || 0);
    this.scene.add(this.model);
    this.bones = {};
    this.meshes = [];
    const shade = this.paint;
    this.lines = [];
    const ink = new THREE.ShaderMaterial({ vertexShader: TOON_VERTEX, fragmentShader: INK_FRAGMENT, side: THREE.BackSide,
      uniforms: { inkM: { value: this.card.ink_m }, ink: { value: new THREE.Color(0x1c1721) } } });
    gltf.scene.traverse((o) => {
      if (o.isBone) this.bones[o.name] = o;
      if (o.isSkinnedMesh && !o.userData.under) this.meshes.push(o);
      else if (o.isMesh) o.visible = false; // skin that worn gear hides, and the skeleton's own display shape
    });
    for (const mesh of [...this.meshes]) {
      const map = mesh.material.map;
      const sharp = /head/i.test(mesh.material.name) ? 512 : 256;
      mesh.material = new THREE.ShaderMaterial({ vertexShader: TOON_VERTEX, fragmentShader: TOON_FRAGMENT, side: THREE.DoubleSide,
        uniforms: { ...shade, inkM: { value: 0 }, map: { value: map }, soften: { value: map ? Math.max(0, Math.log2(map.image.width / sharp)) : 0 } } });
      const line = new THREE.SkinnedMesh(mesh.geometry, ink);
      line.bind(mesh.skeleton, mesh.bindMatrix);
      line.frustumCulled = mesh.frustumCulled = false;
      mesh.parent.add(line);
      this.lines.push(line);
    }
    this.mixer = new THREE.AnimationMixer(gltf.scene);
    this.clip = gltf.animations[0];
    if (this.clip) this.mixer.clipAction(this.clip).play();
    this.held = {};
    this.follow = null;
    this.onFacts?.();
  }

  // Put every card where its bone is now, for where the eye is now.
  setCards() {
    if (!this.parts || !this.bones) return 0;
    const { card, sheet, camera, state } = this;
    const eye = camera.position.toArray();
    const toEye = new THREE.Matrix4();
    let swapped = 0;
    for (const part of this.parts) {
      const bone = this.bones[part.bone];
      if (!bone) continue;
      const world = bone.matrixWorld.elements;
      const v = eyeInBone(world, part.center, eye);
      const pick = choose(sheet.dirs, v, state.soften ? null : this.held[part.name], card.hold_deg, card.blend_deg);
      if (this.held[part.name] !== undefined && this.held[part.name] !== pick.first) swapped += 1;
      this.held[part.name] = pick.first;
      const mixing = state.soften && pick.share < 1;
      toEye.multiplyMatrices(camera.matrixWorldInverse, bone.matrixWorld);
      [pick.first, pick.second].forEach((view, n) => {
        const quad = part.quads[n];
        quad.visible = n === 0 || mixing;
        if (!quad.visible) return;
        const cell = sheet.cells[part.name][view];
        const where = place(sheet.views[view], world, part.center, eye);
        const at = quad.geometry.attributes.position, uv = quad.geometry.attributes.uv;
        const spots = corners(where, cell, density(card, part), state.relief);
        spots.world.forEach((p, i) => at.setXYZ(i, p[0], p[1], p[2]));
        spots.sheet.forEach((p, i) => uv.setXY(i, p[0], p[1]));
        at.needsUpdate = uv.needsUpdate = true;
        const u = quad.material.uniforms;
        u.cell.value.set(cell[0], cell[1], cell[2], cell[3]);
        u.anchor.value.set(cell[4], cell[5]);
        u.heights.value.set(cell[6], cell[7]);
        u.back.value.set(...where.back);
        u.lean.value.set(...where.lean);
        u.deep.value.set(...where.deep);
        u.size.value = where.size;
        u.steps.value = state.relief ? marchSteps(where, cell, density(card, part), card.march) : 0;
        u.facingToEye.value.setFromMatrix4(toEye).multiplyScalar(1 / where.size);
        u.share.value = pick.share;
        u.mix_.value = mixing ? n + 1 : 0;
      });
    }
    return swapped;
  }

  tick() {
    this.frame = requestAnimationFrame(() => this.tick());
    const dt = Math.min(this.clock.getDelta(), 0.1);
    const { state } = this;
    if (this.mixer && !state.paused) this.mixer.update(dt * (state.slow ? 0.25 : 1));
    this.scene.updateMatrixWorld();
    // The eye goes along with the hips, so a fighter who crosses the ring stays in view.
    const hips = this.bones?.hips;
    if (hips) {
      const now = new THREE.Vector3().setFromMatrixPosition(hips.matrixWorld);
      if (this.follow) {
        const step = new THREE.Vector3(now.x - this.follow.x, 0, now.z - this.follow.z);
        this.camera.position.add(step);
        this.controls.target.add(step);
      }
      this.follow = now;
    }
    this.controls.update();
    this.camera.updateMatrixWorld();
    const swapped = this.setCards();
    const time = performance.now();
    if (swapped) this.swaps.push([time, swapped]);
    while (this.swaps.length && time - this.swaps[0][0] > 1000) this.swaps.shift();
    this.draw();
  }

  draw() {
    const size = this.renderer.getSize(new THREE.Vector2());
    const stacked = this.el.classList.contains("stacked");
    this.camera.aspect = (stacked ? size.x : size.x / 2) / (stacked ? size.y / 2 : size.y);
    this.camera.updateProjectionMatrix();
    const show = (cards) => () => {
      this.cards.visible = cards;
      this.edges.visible = cards && this.state.edges;
      for (const mesh of this.meshes || []) mesh.visible = !cards;
      for (const line of this.lines || []) line.visible = !cards && this.look.hull !== false; // bold ink draws its lines on the finished picture
    };
    this.screen.render(this.scene, this.camera, this.look, stacked
      ? [{ x: 0, y: 0.5, w: 1, h: 0.5, before: show(true) }, { x: 0, y: 0, w: 1, h: 0.5, before: show(false) }]
      : [{ x: 0, y: 0, w: 0.5, h: 1, before: show(true) }, { x: 0.5, y: 0, w: 0.5, h: 1, before: show(false) }]);
  }

  // Change the look: the paint's numbers, and (when the look has a sheet of its own) which baked cards are read.
  async useLook(id) {
    this.look = lookOf(id);
    this.state.look = this.look.id;
    const folder = `runs/${encodeURIComponent(this.run.id)}/${bakedFor(this.run, this.look, this.state.model).folder}`;
    if (folder !== this.folder || !this.card) {
      this.folder = folder;
      this.card = await fetch(`${folder}/impostor.json`).then((r) => r.json());
      for (const sheet of Object.values(this.sheets)) { sheet.colour.dispose(); sheet.data.dispose(); }
      this.sheets = {};
      this.paint ||= paintOf(this.card.light);
      await this.useViews(this.card.sets[this.state.views] ? this.state.views : this.card.default_views);
    }
    setPaint(this.paint, this.look);
    this.onFacts?.();
  }

  layout() {
    const stacked = this.el.clientWidth < 620;
    this.el.classList.toggle("stacked", stacked);
    this.renderer.setSize(this.el.clientWidth, this.el.clientHeight, false);
  }

  // What the page and the tests ask: is it up, what is showing, how busy the swapping is.
  report() {
    return {
      ready: Boolean(this.parts && this.mixer), look: this.look.id, motion: this.state.motion?.id, views: this.state.views, cards: this.parts?.length || 0,
      showing: Object.fromEntries((this.parts || []).map((p) => [p.name, this.held[p.name]])),
      swaps_last_second: this.swaps.reduce((sum, s) => sum + s[1], 0), time: this.mixer?.time || 0, error: this.error || null,
    };
  }

  dispose() {
    cancelAnimationFrame(this.frame);
    this.resize.disconnect();
    this.controls.dispose();
    for (const sheet of Object.values(this.sheets)) { sheet.colour.dispose(); sheet.data.dispose(); }
    this.screen.dispose();
    this.renderer.dispose();
    delete window.forgeCards;
  }
}

// The page: the toon's name, the two halves, what to play, and the plain numbers.
export function cardsPage({ run, sets, h, loader }) {
  const models = modelsOf(run);
  const baked = bakedFor(run, LOOKS[0], models[0].id);
  const state = { motion: baked.motions[0], views: null, look: "comic", model: models[0].id, soften: false, relief: true, edges: false, paused: false, slow: false };
  const stage = h("div", { class: "stage clay-surface cards-stage" },
    h("div", { class: "pane cards-pane" },
      h("span", { class: "tag" }, "Flat cards"),
      h("span", { class: "tag tag-right" }, "Real model"),
      h("div", { class: "status" }, "Loading…")));
  const pane = stage.firstChild;
  const facts = h("div", { class: "facts" });
  const fact = (k, v, small) => h("div", { class: "fact clay-surface" }, h("div", { class: "k" }, k), h("div", { class: "v" }, v, small ? h("small", {}, ` ${small}`) : null));
  let viewer = null;
  const showFacts = () => {
    const card = viewer?.card;
    if (!card) return;
    const sheet = card.sets[state.views];
    facts.replaceChildren(
      fact("Cards", String(card.parts.length), "one a bone"),
      fact("Triangles", String(card.parts.length * 2), `the model has ${card.triangles.toLocaleString()}`),
      fact("Pictures", String(sheet.pictures), `${sheet.views.length} a part`),
      fact("Held in memory", `${sheet.memory_mb.toFixed(0)} MB`, `${((sheet.bytes.color + sheet.bytes.data) / 1e6).toFixed(1)} MB to fetch`),
    );
  };
  const chip = (label, pressed, onclick) => h("button", { class: "chip clay-chip", type: "button", "aria-pressed": String(pressed), onclick }, label);
  const group = (label, chips) => h("div", { class: "versions", role: "group", "aria-label": label }, h("span", { class: "row-label" }, label), chips);
  const motionChips = baked.motions.map((m) => chip(m.name, m === state.motion, () => {
    motionChips.forEach((c, i) => c.setAttribute("aria-pressed", String(baked.motions[i] === m)));
    viewer.play(m);
  }));
  const viewChips = baked.views.map((name, i) => chip(name, i === 0, () => {
    viewChips.forEach((c, k) => c.setAttribute("aria-pressed", String(k === i)));
    viewer.useViews(name);
  }));
  const lookChips = LOOKS.map((look, i) => chip(look.name, i === 0, () => {
    lookChips.forEach((c, k) => c.setAttribute("aria-pressed", String(k === i)));
    viewer.useLook(look.id).then(() => viewChips.forEach((c, k) => { c.hidden = !viewer.card.sets[baked.views[k]]; c.setAttribute("aria-pressed", String(baked.views[k] === state.views)); }));
  }));
  const showViews = () => viewChips.forEach((c, k) => { c.hidden = !viewer.card.sets[baked.views[k]]; c.setAttribute("aria-pressed", String(baked.views[k] === state.views)); });
  // which model the cards were pictured from: the rigged one itself, or the detailed mesh given its skeleton
  const modelChips = models.map((model, i) => chip(model.name, i === 0, () => {
    modelChips.forEach((c, k) => c.setAttribute("aria-pressed", String(k === i)));
    state.model = model.id;
    viewer.useLook(state.look).then(showViews);
  }));
  const toggle = (key, label, title) => {
    const btn = h("button", { class: "toggle clay-button clay-button--soft", type: "button", title, "aria-pressed": String(state[key]), onclick: () => {
      state[key] = !state[key];
      btn.setAttribute("aria-pressed", String(state[key]));
    } }, label);
    return btn;
  };
  const page = h("article", { class: "object cards-page" },
    h("a", { class: "back", href: `#/run/${encodeURIComponent(run.id)}` }, `← ${run.name}`),
    h("h1", {}, "Flat cards"),
    h("p", { class: "lede" }, `${run.name}, drawn two ways. On the left he is ${baked.parts} flat pictures, one for each bone, that turn to face you. On the right he is the real model. Drag to look around; the closer the two match, the better the trick.`),
    group("Play", motionChips),
    group("Pictures a part", viewChips),
    group("Drawn as", lookChips),
    models.length > 1 ? group("Pictured from", modelChips) : null,
    h("div", { class: "controls" }, h("div", { class: "toggles" },
      toggle("soften", "Soften the swaps", "When a part changes to its next picture, mix the two for a moment instead of jumping"),
      toggle("relief", "Use the depth", "Slide every pixel of a picture by how far it stands out, so a picture taken from a little to one side still lands where the real surface is. Off: each picture is laid flat on its card"),
      toggle("edges", "Show the cards", "Draw the edge of every card"),
      toggle("slow", "Slow", "Quarter speed"),
      toggle("paused", "Pause", "Hold the pose; you can still look around"))),
    stage,
    facts,
    h("p", { class: "about" }, h("a", { href: `#/tag/${encodeURIComponent(run.id)}` }, "Play tag"), ": a whole field of him, drawn as cards or as meshes, to see what each costs."),
    h("p", { class: "about" }, "How it works: each part was pictured ahead of time from all around. A card shows the picture taken from nearest to where you stand, so any move plays without a new picture ever being drawn. Watch the joints, and watch for a part jumping as its picture is swapped."),
  );
  queueMicrotask(() => {
    viewer = new CardViewer(pane, { run, baked, set: sets.find((s) => s.id === "ring"), state, onFacts: showFacts, loader });
    page.viewer = viewer;
    window.forgeCards = { state: () => viewer.report(), viewer, look: (id, model) => { state.model = model || state.model; return viewer.useLook(id); } };
  });
  page.dispose = () => viewer?.dispose();
  return page;
}
