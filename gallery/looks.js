// Forge gallery: the looks a toon can be drawn in, on the cards page and on the tag field, as cards or as meshes.
//
//   comic      what the comics use: three flat tones, an ink line of a fixed width on the body
//   pixel      pixel art, at either or both of two levels:
//                baked    the cards' sheet is a small one (48 pixels a metre), a few colours, hard edges,
//                         a one-pixel line, read without smoothing. Cards only.
//                screen   the whole picture is drawn small and blown up, every pixel square and on one grid.
//                         Cards and meshes alike.
//   joe        bold comic-book ink: two flat tones with a hard shadow, strong colour, a little light on the rim,
//              a thick black line round every figure that stays the same width on the screen however small he
//              gets, and thinner lines inside where one part passes in front of another or the surface folds
//
// A look is: which baked sheet the cards read, numbers for the paint (tones, colour, rim), whether the meshes
// keep their ink shell (bold ink draws every line on the finished picture instead, for cards and meshes alike),
// and what is done to the finished picture (Screen, below).
import * as THREE from "three";

export const LOOKS = [
  { id: "comic", name: "Comic", sheet: "", shade: [[0.86, 0.85, 0.9], [0.62, 0.6, 0.74]], edges: [0.2, -0.2], punch: 1, rim: 0, screen: null },
  { id: "pixel-baked", name: "Pixels, baked", sheet: "pixel", shade: [[0.8, 0.78, 0.88], [0.58, 0.55, 0.72]], edges: [0.2, -0.2], punch: 1.1, rim: 0, screen: null, cardsOnly: true },
  { id: "pixel-screen", name: "Pixels, on screen", sheet: "", shade: [[0.8, 0.78, 0.88], [0.58, 0.55, 0.72]], edges: [0.2, -0.2], punch: 1.1, rim: 0, screen: { rows: 270, levels: 12 } },
  { id: "pixel-both", name: "Pixels, both", sheet: "pixel", shade: [[0.8, 0.78, 0.88], [0.58, 0.55, 0.72]], edges: [0.2, -0.2], punch: 1.1, rim: 0, screen: { rows: 270, levels: 12 }, cardsOnly: true },
  { id: "joe", name: "Bold ink", sheet: "joe", shade: [[0.5, 0.46, 0.66], [0.5, 0.46, 0.66]], edges: [0.08, -2], punch: 1.45, rim: 0.35, hull: false, screen: { lines: { outer: 3.2, inner: 1.2 } } },
];
export const lookOf = (id) => LOOKS.find((look) => look.id === id) || LOOKS[0];

// The models a run's cards were pictured from: the rigged version itself first ("painted"), then any other model
// given its skeleton (the detailed mesh). Each has a name for the page.
export function modelsOf(run) {
  const seen = new Map();
  for (const c of run.cards) if (!seen.has(c.profile)) seen.set(c.profile, { id: c.profile, name: c.title || `${c.profile[0].toUpperCase()}${c.profile.slice(1)} model`, own: c.plays === c.profile });
  return [...seen.values()].sort((a, b) => Number(b.own) - Number(a.own));
}

// Which of a run's baked card sets a look reads, for one model: the look's own ("...-impostor-pixel"; for pixel
// art the one with a finer head and a drawn face, "...-impostor-pixel-faces", when there is one), or the plain
// one if that was never baked.
export function bakedFor(run, look, model) {
  const mine = run.cards.filter((c) => c.profile === (model || modelsOf(run)[0].id));
  const plain = mine.find((c) => c.folder.endsWith("-impostor")) || mine[0];
  return (look.sheet && (mine.find((c) => c.folder.endsWith(`-impostor-${look.sheet}-faces`)) || mine.find((c) => c.folder.endsWith(`-impostor-${look.sheet}`)))) || plain;
}

const FULL_VERTEX = `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}`;
// The finished picture, put on the screen. Blown up from a small one, each pixel read whole (and its colours
// cut to a few steps); or at full size with ink lines added from the depth of every pixel: a thick line just
// outside anything that stands well in front of what is behind it, a thin one where one thing passes just in
// front of another, and a thin one where the surface folds.
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
varying vec2 vUv;
float away(vec2 uv) {
  float z = texture2D(depths, uv).x * 2.0 - 1.0;
  return 2.0 * near * far / (far + near - z * (far - near));
}
void main() {
  vec4 colour = texture2D(picture, vUv);
  if (levels > 0.0) colour.rgb = pow(floor(pow(colour.rgb, vec3(1.0 / 2.2)) * levels + 0.5) / levels, vec3(2.2)); // cut as the eye sees them
  if (outer > 0.0) {
    float here = away(vUv);
    float line = 0.0;
    float wide[8];
    float close[8];
    for (int i = 0; i < 8; i++) {
      float a = float(i) * 0.7853982;
      vec2 step_ = vec2(cos(a), sin(a)) * pixel;
      wide[i] = away(vUv + step_ * outer);
      close[i] = away(vUv + step_ * inner);
    }
    for (int i = 0; i < 8; i++) {
      // nearer on this side by more than the ground's own slope would make it (the far side says what that is)
      float drop = here - wide[i], slope = abs(wide[(i + 4) % 8] - here);
      if (drop > 0.3 + 0.03 * wide[i] && drop > 2.5 * slope) line = 1.0;       // something stands well in front, close by: the outside line
      drop = here - close[i];
      slope = abs(close[(i + 4) % 8] - here);
      if (drop > 0.04 + 0.004 * close[i] && drop > 2.5 * slope) line = 1.0;    // one part passing in front of another
    }
    // a fold: the depth bends here (flat ground does not bend, whatever its slope)
    float raw = texture2D(depths, vUv).x;
    float bend = abs(texture2D(depths, vUv + vec2(pixel.x * inner, 0.0)).x + texture2D(depths, vUv - vec2(pixel.x * inner, 0.0)).x - 2.0 * raw)
               + abs(texture2D(depths, vUv + vec2(0.0, pixel.y * inner)).x + texture2D(depths, vUv - vec2(0.0, pixel.y * inner)).x - 2.0 * raw);
    if (here < 40.0 && bend * here * here * (far - near) / (near * far) > 0.02 + 0.004 * here) line = 1.0; // far off, the depth is too coarse to tell
    colour.rgb = mix(colour.rgb, ink, line);
  }
  gl_FragColor = colour;
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
        levels: { value: 0 }, outer: { value: 0 }, inner: { value: 0 }, ink: { value: new THREE.Color(0x120e16) } } }));
    this.quad.frustumCulled = false;
    this.flat = new THREE.Scene();
    this.flat.add(this.quad);
    this.eye = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
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

  render(scene, camera, look, halves = [{ x: 0, y: 0, w: 1, h: 1 }]) {
    const renderer = this.renderer;
    const size = renderer.getDrawingBufferSize(new THREE.Vector2());
    const ratio = renderer.getPixelRatio();
    const screen = look.screen;
    const k = screen?.rows ? Math.max(2, Math.round(size.y / (screen.rows * (halves.some((p) => p.h < 1) ? 2 : 1)))) : 1;
    const wide = Math.max(1, Math.floor(size.x / k)), tall = Math.max(1, Math.floor(size.y / k));
    const target = screen ? this.target(wide, tall, false) : null;
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
    renderer.setRenderTarget(null);
    renderer.setScissorTest(false);
    renderer.setViewport(0, 0, size.x / ratio, size.y / ratio);
    const u = this.quad.material.uniforms;
    u.picture.value = target.texture;
    u.depths.value = target.depthTexture;
    u.pixel.value.set(1 / wide, 1 / tall);
    u.near.value = camera.near;
    u.far.value = camera.far;
    u.levels.value = screen.levels || 0;
    u.outer.value = screen.lines ? screen.lines.outer * ratio : 0;
    u.inner.value = screen.lines ? screen.lines.inner * ratio : 0;
    renderer.render(this.flat, this.eye);
  }

  dispose() {
    this.held?.dispose();
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
