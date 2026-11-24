// Forge gallery: the looks a toon can be drawn in, on the cards page and on the tag field, as cards or as meshes.
//
//   comic      what the comics use: three flat tones, an ink line of a fixed width on the body
//   pixel      pixel art, at either or both of two levels:
//                baked    the cards' sheet is a small one (48 pixels a metre), a few colours, hard edges,
//                         a one-pixel line, read without smoothing. Cards only.
//                screen   the whole picture is drawn small and blown up, every pixel square and on one grid.
//                         Cards and meshes alike.
//                both     the two together, and a face kept clear: the cards' heads are pictured at 192 pixels a
//                         metre with their folds drawn in ("...-impostor-pixel-clear") and drawn on a grid twice
//                         as fine as the body's (FINE_FROM, below; Screen)
//   joe        bold comic-book ink: two flat tones with a hard shadow, strong colour, a little light on the rim,
//              a thick black line round every figure that stays the same width on the screen however small he
//              gets, and thinner lines inside where one part passes in front of another or the surface folds
//
// A look is: which baked sheet the cards read, numbers for the paint (tones, colour, rim), whether the meshes
// keep their ink shell (bold ink draws every line on the finished picture instead, for cards and meshes alike),
// and what is done to the finished picture (Screen, below).
//
// The line round a figure drawn as cards. A sheet pictures every part with its own ink line all the way round,
// and marks which pixels are line (bake_impostor.py). Shown as they are, a line would cross the figure at every
// joint, where one part's edge lies on the next part. So a look does one of two things with them (cardLine):
//   - a look drawn straight to the screen (comic; pixels, baked) keeps the line as a shell a little behind the
//     part's surface, the way a mesh's ink shell is: the part next door covers it where they meet, and it shows
//     only where nothing of the figure is beside it;
//   - a look that goes by way of a picture of its own (pixels on screen, bold ink) leaves the sheet's line out and
//     draws the line once, on the finished picture: every card pixel says which figure and which part it is
//     (cardNumber, in the picture's fourth channel), and a line goes just outside a figure, or inside it only
//     where the surface really steps back.
import * as THREE from "three";

export const LOOKS = [
  { id: "comic", name: "Comic", sheet: "", shade: [[0.86, 0.85, 0.9], [0.62, 0.6, 0.74]], edges: [0.2, -0.2], punch: 1, rim: 0, screen: null },
  { id: "pixel-baked", name: "Pixels, baked", sheet: "pixel", shade: [[0.8, 0.78, 0.88], [0.58, 0.55, 0.72]], edges: [0.2, -0.2], punch: 1.1, rim: 0, screen: null, cardsOnly: true },
  { id: "pixel-screen", name: "Pixels, on screen", sheet: "", shade: [[0.8, 0.78, 0.88], [0.58, 0.55, 0.72]], edges: [0.2, -0.2], punch: 1.1, rim: 0, screen: { rows: 270, levels: 12 } },
  { id: "pixel-both", name: "Pixels, both", sheet: "pixel", first: "pixel-clear", shade: [[0.8, 0.78, 0.88], [0.58, 0.55, 0.72]], edges: [0.2, -0.2], punch: 1.1, rim: 0, screen: { rows: 270, levels: 12, heads: 2 }, cardsOnly: true },
  { id: "joe", name: "Bold ink", sheet: "joe", shade: [[0.5, 0.46, 0.66], [0.5, 0.46, 0.66]], edges: [0.08, -2], punch: 1.45, rim: 0.35, hull: false, screen: { lines: { outer: 3.2, inner: 1.2 } } },
];
export const lookOf = (id) => LOOKS.find((look) => look.id === id) || LOOKS[0];
// A head on a finer grid. "Pixels, both" draws every card but the head's on the picture's big pixels, and the head
// on pixels half as big each way (screen.heads), once a metre at the head is at least FINE_FROM big pixels (a face
// five or six wide; further off there is no face to show, and the head is drawn with the body). The head's picture
// is slid by part of a fine pixel so the bone's head lands on a corner of one: as he moves his face moves a whole
// pixel at a time, as a sprite does. scripts/impostor/impostor.py has the same numbers (FINE, FINE_FROM).
export const FINE_FROM = 40;
// The same look with no finer grid, for a picture that has no cards in it (meshes): the copy onto the finer
// picture would be work for nothing.
const plain = new Map();
export function withoutHeads(look) {
  if (!look.screen?.heads) return look;
  if (!plain.has(look.id)) plain.set(look.id, { ...look, screen: { ...look.screen, heads: 0 } });
  return plain.get(look.id);
}

// What a card's shader is told about its sheet's ink line in a look: `line` is how far behind the surface the
// line stands (m), under 0 to leave it out, 0 for a sheet that marks none; `ids` is whether each card pixel
// writes its number for the lines drawn on the finished picture.
export function cardLine(card, look) {
  if (!card.line_marked) return { line: 0, ids: false };
  const onScreen = Boolean(look.screen);
  return { line: onScreen ? -1 : card.line_back_m || 0.03, ids: onScreen };
}
// A card pixel's number: 1 + 16 times which figure (they come round again after fifteen) + which of its parts.
export const cardNumber = (figure, part) => (1 + 16 * (figure % 15) + (part % 16)) / 255;

// Cracks filled on the finished picture. A look that goes by way of a picture of its own can see a crack for what
// it is: a pixel that shows no card (or another figure) with two cards of one figure on opposite sides of it,
// close by. It is filled from the nearer of the two when they are one part or two parts that meet at a joint,
// stand within CRACK.apartM of each other, and what shows through is further off than both by CRACK.behindM.
// A real gap (between the legs, between an arm and the hips, the stage seen through a bent arm) is wider than the
// two places reach, or lies between parts that do not meet, and is left alone. The pixel looks look one big pixel
// either side; bold ink as far as its thick line reaches, so a crack is not inked black from both edges.
// PART_NAMES is the order a bake lists the parts in; JOINED[a] has bit b set when parts a and b are one or meet.
// scripts/impostor/impostor.py has the same numbers and the same table (crack_fill).
export const CRACK = { behindM: 0.02, apartM: 0.12 };
export const PART_NAMES = ["hips", "spine", "chest", "head", ...["_l", "_r"].flatMap((side) => ["upper_arm", "forearm", "hand", "thigh", "shin", "foot"].map((name) => name + side))];
const MEET = [["hips", "spine"], ["spine", "chest"], ["chest", "head"], ...["_l", "_r"].flatMap((s) => [["chest", `upper_arm${s}`], [`upper_arm${s}`, `forearm${s}`], [`forearm${s}`, `hand${s}`], ["hips", `thigh${s}`], [`thigh${s}`, `shin${s}`], [`shin${s}`, `foot${s}`]])];
export const JOINED = PART_NAMES.map((name, a) => MEET.reduce((bits, [x, y]) => bits | (x === name ? 1 << PART_NAMES.indexOf(y) : y === name ? 1 << PART_NAMES.indexOf(x) : 0), 1 << a));

// The models a run's cards were pictured from: the rigged version itself first ("painted"), then any other model
// given its skeleton (the detailed mesh). Each has a name for the page.
export function modelsOf(run) {
  const seen = new Map();
  for (const c of run.cards) if (!seen.has(c.profile)) seen.set(c.profile, { id: c.profile, name: c.title || `${c.profile[0].toUpperCase()}${c.profile.slice(1)} model`, own: c.plays === c.profile });
  return [...seen.values()].sort((a, b) => Number(b.own) - Number(a.own));
}

// Which of a run's baked card sets a look reads, for one model: the look's own ("...-impostor-pixel"; for pixel
// art the one with a finer head and a drawn face, "...-impostor-pixel-faces", when there is one), or the plain
// one if that was never baked. "Pixels, both" reads "...-impostor-pixel-clear" first: the head at 192 pixels a
// metre with its folds drawn in, for the finer grid its head is drawn on.
// Sheets baked since the joints were mended are in "...-impostor-<look>-joined" (the comic one too) and are
// read first; the older ones stay where they were for pages older than this.
// The same cards with a piece of the real model for every big joint (scripts/impostor/bake_joints.py) are in the
// folder of that name with "-skinned" for "-joined" (or added), and are read before those.
// Cards whose pictures go more than one surface deep (bake_impostor.py --layers: what lay behind the first surface
// and can be seen from a little to one side) are in the folder of that name with "-layered" for "-joined" (or
// added), their pieces in "-layered-skinned", and are read first of all. "?layers=off" in the page's address
// reads the cards as if there were none: for a picture of before and after, or to time what the layers cost.
const LAYERED = new URLSearchParams(globalThis.location?.search || "").get("layers") !== "off";
export function bakedFor(run, look, model, layered = LAYERED) {
  const mine = run.cards.filter((c) => c.profile === (model || modelsOf(run)[0].id));
  const ends = (tail) => mine.find((c) => c.folder.endsWith(tail));
  const plain = ends("-impostor-comic-joined") || ends("-impostor") || mine[0];
  const cards = (look.first && ends(`-impostor-${look.first}`)) || (look.sheet && (ends(`-impostor-${look.sheet}-joined`) || ends(`-impostor-${look.sheet}-faces`) || ends(`-impostor-${look.sheet}`))) || plain;
  const named = (tail) => cards && mine.find((c) => c.folder === `${cards.folder.replace(/-joined$/, "")}${tail}`);
  return (layered && (named("-layered-skinned") || named("-layered"))) || named("-skinned") || cards;
}

const FULL_VERTEX = `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}`;
// The finished picture, put on the screen. Blown up from a small one, each pixel read whole (and its colours
// cut to a few steps), with a line one of its pixels wide round every figure drawn as cards; or at full size
// with ink lines added from the depth of every pixel: a thick line just outside anything that stands well in
// front of what is behind it, a thin one where one thing passes just in front of another, and a thin one where
// the surface folds. A card pixel's number (cardNumber) is in the picture's fourth channel; anything else has
// 255 there. scripts/impostor/impostor.py has the same two sets of lines in Python (grid_line, bold_lines).
const FULL_FRAGMENT = `
uniform sampler2D picture;
uniform sampler2D depths;
uniform vec2 pixel;      // one pixel of the picture, as a share of it
uniform float near;
uniform float far;
uniform float levels;    // colour steps a channel; 0 leaves colours alone
uniform float outer;     // the outside line's width in pixels; 0 draws no lines
uniform float inner;
uniform vec3 ink;
uniform float grid;      // over 0: a line one big pixel wide round every figure drawn as cards
uniform int fine;        // how many of the picture's pixels a big pixel is across (2 when heads are on a finer grid)
uniform vec3 gridInk;
uniform float pixelM;    // how big one pixel of the picture is, a metre away
uniform float breakM;    // within one figure the grid's line needs the surface to step back by more than this
uniform float seamM;     // bold ink's thin lines leave a step under this alone where two cards of one figure meet
uniform int joined[16];  // bit b of joined[a]: parts a and b of a figure are one part or meet at a joint
uniform float behindM;   // a crack: what shows through is this much further off than the cards on both sides of it
uniform float apartM;    // ... which stand no further than this from each other
varying vec2 vUv;
float away(vec2 uv) {
  float z = texture2D(depths, uv).x * 2.0 - 1.0;
  return 2.0 * near * far / (far + near - z * (far - near));
}
float card(vec2 uv) {    // which card a pixel shows: 1 + 16 * figure + part, or 0 for anything that is not a card
  float a = floor(texture2D(picture, uv).a * 255.0 + 0.5);
  return a > 240.5 ? 0.0 : a;
}
float figureOf(float c) {
  return floor((c - 1.0) / 16.0);
}
// Two cards either side of this pixel, of one figure that this pixel does not show, one part or two that meet.
bool sides(vec2 step_, float me) {
  float a = card(vUv + step_), b = card(vUv - step_);
  if (a < 0.5 || b < 0.5 || figureOf(a) != figureOf(b) || (me > 0.5 && figureOf(me) == figureOf(a))) return false;
  return ((joined[int(mod(a - 1.0, 16.0))] >> int(mod(b - 1.0, 16.0))) & 1) == 1;
}
// ... and the crack between them: filled from the nearer of the two.
bool crack(vec2 step_, float here, float me, inout vec4 colour) {
  if (!sides(step_, me)) return false;
  float a = away(vUv + step_), b = away(vUv - step_);
  if (abs(a - b) >= apartM || here - max(a, b) <= behindM) return false;
  colour = texture2D(picture, vUv + (a <= b ? step_ : -step_));
  return true;
}
void main() {
  vec4 colour = texture2D(picture, vUv);
  bool filled = false;
  if (grid > 0.0 && behindM > 0.0) {
    float here = away(vUv), me = card(vUv);
    filled = crack(vec2(pixel.x * float(fine), 0.0), here, me, colour) || crack(vec2(0.0, pixel.y * float(fine)), here, me, colour);
  }
  if (levels > 0.0) colour.rgb = pow(floor(pow(colour.rgb, vec3(1.0 / 2.2)) * levels + 0.5) / levels, vec3(2.2)); // cut as the eye sees them
  if (grid > 0.0 && !filled) {
    // just outside a card: this pixel is not that figure and is the further of the two. Or inside one figure,
    // where the surface steps back by more than a slope would make it: an arm in front of a chest.
    // The pixels beside it are looked at up to one big pixel off, so the line is one big pixel wide round a head
    // on the finer grid too.
    float here = away(vUv), me = card(vUv), line = 0.0;
    for (int i = 0; i < 4; i++) {
      vec2 one = (i == 0 ? vec2(1.0, 0.0) : i == 1 ? vec2(-1.0, 0.0) : i == 2 ? vec2(0.0, 1.0) : vec2(0.0, -1.0)) * pixel;
      for (int s = 1; s <= 2; s++) {
        if (s > fine) break;
        vec2 step_ = one * float(s);
        float it = card(vUv + step_);
        if (it < 0.5) continue;
        float there = away(vUv + step_), drop = here - there;
        if (me < 0.5 || figureOf(me) != figureOf(it)) {
          if (drop > 0.0) line = 1.0;
          continue;
        }
        if (s < fine) continue;
        float past = card(vUv - step_);
        float slope = past > 0.5 && figureOf(past) == figureOf(me) ? abs(away(vUv - step_) - here) : 0.0;
        if (drop > max(breakM, 1.5 * pixelM * there) && drop > 2.5 * slope) line = 1.0;
      }
    }
    colour.rgb = mix(colour.rgb, gridInk, line);
  }
  if (outer > 0.0) {
    float here = away(vUv), me = card(vUv);
    float line = 0.0;
    float wide[8];
    float close[8];
    for (int i = 0; i < 8; i++) {
      float a = float(i) * 0.7853982;
      vec2 step_ = vec2(cos(a), sin(a)) * pixel;
      wide[i] = away(vUv + step_ * outer);
      close[i] = away(vUv + step_ * inner);
    }
    // a crack between two cards that meet: filled, and not inked (only the depths already read are looked at
    // until two of them say there may be one)
    for (int i = 0; i < 4; i++) {
      if (filled || behindM <= 0.0 || abs(wide[i] - wide[i + 4]) >= apartM || here - max(wide[i], wide[i + 4]) <= behindM) continue;
      float a = float(i) * 0.7853982;
      filled = crack(vec2(cos(a), sin(a)) * pixel * outer, here, me, colour);
    }
    for (int i = 0; i < 8; i++) {
      if (filled) break;
      // nearer on this side by more than the ground's own slope would make it (the far side says what that is)
      float drop = here - wide[i], slope = abs(wide[(i + 4) % 8] - here);
      if (drop > 0.3 + 0.03 * wide[i] && drop > 2.5 * slope) line = 1.0;       // something stands well in front, close by: the outside line
      drop = here - close[i];
      slope = abs(close[(i + 4) % 8] - here);
      if (drop > 0.04 + 0.004 * close[i] && drop > 2.5 * slope) {              // one part passing in front of another
        float it = card(vUv + vec2(cos(float(i) * 0.7853982), sin(float(i) * 0.7853982)) * pixel * inner);
        // ... unless it is two cards of one figure meeting at a joint, a little out of step
        if (!(me > 0.5 && it > 0.5 && it != me && figureOf(it) == figureOf(me) && drop < seamM)) line = 1.0;
      }
    }
    // a fold: the depth bends here (flat ground does not bend, whatever its slope)
    float raw = texture2D(depths, vUv).x;
    float bend = abs(texture2D(depths, vUv + vec2(pixel.x * inner, 0.0)).x + texture2D(depths, vUv - vec2(pixel.x * inner, 0.0)).x - 2.0 * raw)
               + abs(texture2D(depths, vUv + vec2(0.0, pixel.y * inner)).x + texture2D(depths, vUv - vec2(0.0, pixel.y * inner)).x - 2.0 * raw);
    if (!filled && here < 40.0 && bend * here * here * (far - near) / (near * far) > 0.02 + 0.004 * here) { // far off, the depth is too coarse to tell
      bool joint = false; // where two cards of one figure meet the depth bends too, and that is not a fold
      for (int i = 0; i < 4; i++) {
        float it = card(vUv + (i == 0 ? vec2(pixel.x, 0.0) : i == 1 ? vec2(-pixel.x, 0.0) : i == 2 ? vec2(0.0, pixel.y) : vec2(0.0, -pixel.y)) * inner);
        if (me > 0.5 && it > 0.5 && it != me && figureOf(it) == figureOf(me)) joint = true;
      }
      if (!joint) line = 1.0;
    }
    colour.rgb = mix(colour.rgb, ink, line);
  }
  gl_FragColor = vec4(colour.rgb, 1.0);
  #include <colorspace_fragment>
}`;

// The small picture copied onto the finer one, colour, card numbers and depth, before the heads are drawn there.
const COPY_FRAGMENT = `
uniform sampler2D picture;
uniform sampler2D depths;
varying vec2 vUv;
void main() {
  gl_FragColor = texture2D(picture, vUv);
  gl_FragDepth = texture2D(depths, vUv).x;
  #include <colorspace_fragment>
}`;

// Draws a scene the way a look wants its finished picture: straight to the screen, or by way of a picture of its
// own that is then blown up or inked. `halves` are the parts of the canvas to draw (x, y, wide, tall as shares
// of it, and a function to call before each), so a page with two views side by side goes through as one picture.
export class Screen {
  constructor(renderer) {
    this.renderer = renderer;
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({
      vertexShader: FULL_VERTEX, fragmentShader: FULL_FRAGMENT, depthTest: false, depthWrite: false,
      uniforms: { picture: { value: null }, depths: { value: null }, pixel: { value: new THREE.Vector2() }, near: { value: 0.1 }, far: { value: 100 },
        levels: { value: 0 }, outer: { value: 0 }, inner: { value: 0 }, ink: { value: new THREE.Color(0x120e16) },
        grid: { value: 0 }, fine: { value: 1 }, gridInk: { value: new THREE.Color(0x1c1721) }, pixelM: { value: 0 }, breakM: { value: 0.05 }, seamM: { value: 0.09 },
        joined: { value: JOINED }, behindM: { value: CRACK.behindM }, apartM: { value: CRACK.apartM } } }));
    this.quad.frustumCulled = false;
    this.flat = new THREE.Scene();
    this.flat.add(this.quad);
    this.copy = new THREE.Mesh(this.quad.geometry, new THREE.ShaderMaterial({ vertexShader: FULL_VERTEX, fragmentShader: COPY_FRAGMENT, depthFunc: THREE.AlwaysDepth,
      uniforms: { picture: { value: null }, depths: { value: null } } }));
    this.copy.frustumCulled = false;
    this.copied = new THREE.Scene();
    this.copied.add(this.copy);
    // What every card's shader is told about the finer grid (a page puts these among its cards' uniforms): which
    // of the two drawings this is (0: the small picture, heads on the finer grid left out; 1: only those heads).
    this.told = { headPass: { value: 0 } };
    this.eye = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    this.spot = new THREE.Vector3();
  }

  finer(wide, tall) {
    if (!this.fine || this.fine.width !== wide || this.fine.height !== tall) {
      this.fine?.dispose();
      this.fine = new THREE.WebGLRenderTarget(wide, tall, { depthTexture: new THREE.DepthTexture(wide, tall), magFilter: THREE.NearestFilter, minFilter: THREE.NearestFilter });
      this.fine.depthTexture.type = THREE.UnsignedIntType;
      this.fine.texture.colorSpace = THREE.SRGBColorSpace;
    }
    return this.fine;
  }

  target(wide, tall, smooth) {
    if (!this.held || this.held.width !== wide || this.held.height !== tall || this.smooth !== smooth) {
      this.held?.dispose();
      this.held = new THREE.WebGLRenderTarget(wide, tall, { depthTexture: new THREE.DepthTexture(wide, tall), magFilter: THREE.NearestFilter, minFilter: THREE.NearestFilter });
      this.held.depthTexture.type = THREE.UnsignedIntType;
      this.held.texture.colorSpace = THREE.SRGBColorSpace;
      this.smooth = smooth;
    }
    return this.held;
  }

  // How big the small picture is for a look: [wide, tall, screen pixels to one of its own].
  small(look, halves = [{ x: 0, y: 0, w: 1, h: 1 }]) {
    const size = this.renderer.getDrawingBufferSize(new THREE.Vector2());
    const rows = (look.screen?.rows || 0) * (halves.some((p) => p.h < 1) ? 2 : 1);
    // with heads on a grid twice as fine a big pixel is an even number of the screen's, so a head's pixel is a whole number of them
    const k = !rows ? 1 : look.screen.heads ? 2 * Math.max(1, Math.round(size.y / (2 * rows))) : Math.max(2, Math.round(size.y / rows));
    return [Math.max(1, Math.floor(size.x / k)), Math.max(1, Math.floor(size.y / k)), k];
  }

  // Whether a head at a place in the world goes on the finer grid in this look, and if so how far its card is
  // slid, as a share of the view (x and y, -1 to 1 across it), to bring the bone's head onto a corner of a fine
  // pixel: null, or [x, y]. `part` is the share of the picture this view is drawn in (a page with two views).
  headGrid(look, camera, at, part = { w: 1, h: 1 }) {
    const times = look.screen?.heads;
    if (!times) return null;
    const [wide, tall] = this.small(look, part.h < 1 || part.w < 1 ? [part] : undefined);
    const w = Math.round(part.w * wide), h = Math.round(part.h * tall);
    const p = this.spot.copy(at).applyMatrix4(camera.matrixWorldInverse);
    if (p.z > -camera.near || h / (2 * -p.z * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2)) < FINE_FROM) return null;
    p.applyMatrix4(camera.projectionMatrix);
    const x = (p.x * 0.5 + 0.5) * w * times, y = (p.y * 0.5 + 0.5) * h * times;
    return [(Math.round(x) - x) * 2 / (w * times), (Math.round(y) - y) * 2 / (h * times)];
  }

  render(scene, camera, look, halves = [{ x: 0, y: 0, w: 1, h: 1 }]) {
    const renderer = this.renderer;
    const size = renderer.getDrawingBufferSize(new THREE.Vector2());
    const ratio = renderer.getPixelRatio();
    const screen = look.screen;
    const [wide, tall] = this.small(look, halves);
    const target = screen ? this.target(wide, tall, false) : null;
    this.told.headPass.value = 0;
    renderer.setRenderTarget(target);
    renderer.setScissorTest(false);
    renderer.clear();
    for (const part of halves) {
      part.before?.();
      if (target) {
        target.viewport.set(Math.round(part.x * wide), Math.round(part.y * tall), Math.round(part.w * wide), Math.round(part.h * tall));
        target.scissor.copy(target.viewport);
        target.scissorTest = true;
        renderer.setRenderTarget(target);
      } else {
        const box = [part.x * size.x / ratio, part.y * size.y / ratio, part.w * size.x / ratio, part.h * size.y / ratio];
        renderer.setViewport(...box);
        renderer.setScissor(...box);
        renderer.setScissorTest(true);
      }
      renderer.render(scene, camera);
    }
    if (!target) return;
    let shown = target, times = 1;
    if (screen.heads) {
      // Heads on a finer grid: the small picture is copied onto one `heads` times as big each way, depth and all,
      // and the heads' cards (the things in layer 1 that answer to headPass) are drawn onto that, in front of or
      // behind the body pixel by pixel.
      times = screen.heads;
      const finer = this.finer(wide * times, tall * times);
      finer.scissorTest = false;
      finer.viewport.set(0, 0, wide * times, tall * times);
      renderer.setRenderTarget(finer);
      this.copy.material.uniforms.picture.value = target.texture;
      this.copy.material.uniforms.depths.value = target.depthTexture;
      renderer.render(this.copied, this.eye);
      this.told.headPass.value = 1;
      const layers = camera.layers.mask, auto = renderer.autoClear;
      camera.layers.set(1);
      renderer.autoClear = false;
      for (const part of halves) {
        part.before?.();
        finer.viewport.set(Math.round(part.x * wide) * times, Math.round(part.y * tall) * times, Math.round(part.w * wide) * times, Math.round(part.h * tall) * times);
        finer.scissor.copy(finer.viewport);
        finer.scissorTest = true;
        renderer.setRenderTarget(finer);
        renderer.render(scene, camera);
      }
      camera.layers.mask = layers;
      renderer.autoClear = auto;
      this.told.headPass.value = 0;
      shown = finer;
    }
    renderer.setRenderTarget(null);
    renderer.setScissorTest(false);
    renderer.setViewport(0, 0, size.x / ratio, size.y / ratio);
    const u = this.quad.material.uniforms;
    u.picture.value = shown.texture;
    u.depths.value = shown.depthTexture;
    u.pixel.value.set(1 / (wide * times), 1 / (tall * times));
    u.fine.value = times;
    u.near.value = camera.near;
    u.far.value = camera.far;
    u.levels.value = screen.levels || 0;
    u.outer.value = screen.lines ? screen.lines.outer * ratio : 0;
    u.inner.value = screen.lines ? screen.lines.inner * ratio : 0;
    u.grid.value = screen.rows ? 1 : 0;
    u.pixelM.value = (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov || 30) / 2)) / Math.max(1, Math.round(halves[0].h * tall));
    renderer.render(this.flat, this.eye);
  }

  dispose() {
    this.held?.dispose();
    this.fine?.dispose();
    this.copy.material.dispose();
    this.quad.geometry.dispose();
    this.quad.material.dispose();
  }
}

// The paint's numbers as one set of uniforms every material of a page shares, and setting them for a look.
export function paintOf(light) {
  return { light: { value: new THREE.Vector3(...light).normalize() }, shadeMid: { value: new THREE.Vector3() }, shadeDark: { value: new THREE.Vector3() },
    edges: { value: new THREE.Vector2() }, punch: { value: 1 }, rim: { value: 0 } };
}
export function setPaint(paint, look) {
  paint.shadeMid.value.set(...look.shade[0]);
  paint.shadeDark.value.set(...look.shade[1]);
  paint.edges.value.set(...look.edges);
  paint.punch.value = look.punch;
  paint.rim.value = look.rim;
}
