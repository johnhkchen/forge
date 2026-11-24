// Forge gallery: a part drawn as a cloud of dots instead of a card. An experiment, on the watch page only, and only
// when the page's address has "?head=dots" (README: "From more angles").
//
// A card shows the one picture taken from nearest to where the eye is, and searches it. Here every picture of the
// part is used at once: each pixel of each picture (and of the layer behind) is a place on the part's surface, with
// a colour and a facing. All of them are put in the bone's own frame, and of the ones that fall in the same little
// box (one sheet pixel across) the one its picture saw most square-on is kept. Each dot is then drawn as a flat disc
// lying on the surface, seen from its own side only, nearest winning pixel by pixel. There is no nearest picture,
// nothing to swap as the eye moves, and the eye's own lines are right by themselves.
// (scripts/impostor/impostor.py: dots_of and draw_dots are the same thing done slowly, for the judges.)
import * as THREE from "three";
import { density } from "./impostor-math.js";

export const DOTS = { grid: 1, size: 1, on: new URLSearchParams(globalThis.location?.search || "").get("head") === "dots" };

const DOT_VERTEX = `
uniform float headPass;
uniform float fineHead;
uniform vec2 nudge;
uniform float radius;
attribute vec3 place;
attribute vec3 facing;
attribute vec3 tint;
varying vec3 vView;
flat varying vec3 vMiddle;
flat varying vec3 vFacing;
flat varying vec3 vTint;
flat varying float vReach;
void main() {
  vMiddle = (modelViewMatrix * vec4(place, 1.0)).xyz;
  vFacing = normalize(mat3(modelViewMatrix) * facing);
  vTint = tint;
  vReach = radius * length(modelViewMatrix[0].xyz);
  vView = vMiddle + vec3(position.xy * vReach, 0.0);
  gl_Position = projectionMatrix * vec4(vView, 1.0);
  if (dot(vFacing, vMiddle) >= 0.0 || (headPass > 0.5) != (fineHead > 0.5)) gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
  else if (headPass > 0.5) gl_Position.xy += nudge * gl_Position.w;
}`.replaceAll("flat varying", "flat out").replace("varying vec3 vView", "out vec3 vView");
const DOT_FRAGMENT = `
uniform mat4 projectionMatrix;
uniform float who;
uniform vec3 light;
uniform vec3 shadeMid;
uniform vec3 shadeDark;
uniform vec2 edges;
uniform float punch;
uniform float rim;
in vec3 vView;
flat in vec3 vMiddle;
flat in vec3 vFacing;
flat in vec3 vTint;
flat in float vReach;
void main() {
  // where the eye's line through this pixel meets the dot's own flat disc
  vec3 ray = normalize(vView);
  float along = dot(vMiddle, vFacing) / min(dot(ray, vFacing), -1e-6);
  vec3 at = ray * along;
  if (dot(at - vMiddle, at - vMiddle) > vReach * vReach) discard;
  vec4 clip = projectionMatrix * vec4(at, 1.0);
  gl_FragDepth = clip.z / clip.w * 0.5 + 0.5;
  vec3 colour = pow(vTint, vec3(2.2));
  float lit = dot(vFacing, light);
  vec3 tone = lit > edges.x ? vec3(1.0) : lit > edges.y ? shadeMid : shadeDark;
  vec3 paint = mix(vec3(dot(colour, vec3(0.2126, 0.7152, 0.0722))), colour, punch);
  gl_FragColor = vec4(paint * tone + rim * pow(1.0 - clamp(vFacing.z, 0.0, 1.0), 3.0) * step(edges.x, lit), who);
  #include <colorspace_fragment>
}`;

const unfold = (ex, ey) => {
  let x = ex * 2 - 1, y = ey * 2 - 1;
  const z = 1 - Math.abs(x) - Math.abs(y), t = Math.min(1, Math.max(0, -z));
  x += x >= 0 ? -t : t;
  y += y >= 0 ? -t : t;
  const n = Math.hypot(x, y, z) || 1;
  return [x / n, y / n, z / n];
};

// A picture's pixels, as numbers: rows from the top, four numbers a pixel.
function pixelsOf(image) {
  const scrap = document.createElement("canvas");
  scrap.width = image.width;
  scrap.height = image.height;
  const pen = scrap.getContext("2d", { willReadFrequently: true });
  pen.drawImage(image, 0, 0);
  return pen.getImageData(0, 0, image.width, image.height).data;
}

// One part's dots: { places, facings, tints (three numbers a dot), count, grid }. `sheet` is a view set with its
// two pictures loaded (colour, data: textures).
export function dotsOf(card, sheet, part) {
  const ppm = density(card, part), grid = DOTS.grid / ppm, wide = sheet.size[0], tall = sheet.size[1];
  const colour = pixelsOf(sheet.colour.image), data = pixelsOf(sheet.data.image);
  const best = new Map();
  const joe = card.look === "joe"; // (bold ink's sheet has its folds drawn into every picture: left out, or the same fold from 26 eyes is a scatter of black dots)
  for (const cells of [sheet.cells, ...(sheet.behind || [])]) {
    sheet.views.forEach((view, v) => {
      const [x0, y0, w, h, ax, ay] = cells[part.name][v];
      const { r, u, d } = view;
      for (let cy = 0; cy < h; cy++) for (let cx = 0; cx < w; cx++) {
        const i = ((tall - 1 - (y0 + cy)) * wide + x0 + cx) * 4;
        if (data[i + 2] < 1 || colour[i + 3] < 128 || data[i] + data[i + 1] < 1) continue;
        if (joe && Math.abs(colour[i] - 18) < 6 && Math.abs(colour[i + 1] - 14) < 6 && Math.abs(colour[i + 2] - 22) < 6) continue;
        const n = unfold(data[i] / 255, data[i + 1] / 255);
        const square = n[0] * d[0] + n[1] * d[1] + n[2] * d[2];
        if (square <= 0.15) continue;
        const X = (cx + 0.5 - ax) / ppm, Y = (cy + 0.5 - ay) / ppm, H = (data[i + 2] / 255 * 2 - 1) * part.depth_m;
        const p = [X * r[0] + Y * u[0] + H * d[0], X * r[1] + Y * u[1] + H * d[1], X * r[2] + Y * u[2] + H * d[2]];
        // a dot is told from its neighbours by its box and by which of six ways it faces: the two sides of a thin brim are two dots
        const a = Math.abs(n[0]) >= Math.abs(n[1]) && Math.abs(n[0]) >= Math.abs(n[2]) ? 0 : Math.abs(n[1]) >= Math.abs(n[2]) ? 1 : 2;
        const key = (((Math.floor(p[0] / grid) + 4096) * 8192 + Math.floor(p[1] / grid) + 4096) * 8192 + Math.floor(p[2] / grid) + 4096) * 8 + a * 2 + (n[a] > 0 ? 1 : 0);
        const was = best.get(key);
        if (!was || square > was[0]) best.set(key, [square, p, n, colour[i], colour[i + 1], colour[i + 2]]);
      }
    });
  }
  const count = best.size, places = new Float32Array(count * 3), facings = new Float32Array(count * 3), tints = new Uint8Array(count * 3);
  let k = 0;
  for (const [, p, n, red, green, blue] of best.values()) {
    places.set(p, k * 3);
    facings.set(n, k * 3);
    tints.set([red, green, blue], k * 3);
    k++;
  }
  return { places, facings, tints, count, grid };
}

// The dots as something to draw: one small square a dot, all in one draw. Set mesh.matrix to the part's bone every
// frame. `paint` is the page's paint uniforms; headPass the screen's (looks.js: a head on a finer grid).
export function dotsMesh(dots, paint, headPass) {
  const shape = new THREE.InstancedBufferGeometry();
  shape.setAttribute("position", new THREE.BufferAttribute(new Float32Array([-1, -1, 0, 1, -1, 0, 1, 1, 0, -1, 1, 0]), 3));
  shape.setIndex([0, 1, 2, 0, 2, 3]);
  shape.setAttribute("place", new THREE.InstancedBufferAttribute(dots.places, 3));
  shape.setAttribute("facing", new THREE.InstancedBufferAttribute(dots.facings, 3));
  shape.setAttribute("tint", new THREE.InstancedBufferAttribute(dots.tints, 3, true));
  shape.instanceCount = dots.count;
  const mesh = new THREE.Mesh(shape, new THREE.ShaderMaterial({ vertexShader: DOT_VERTEX, fragmentShader: DOT_FRAGMENT, uniforms: {
    radius: { value: DOTS.size * dots.grid }, who: { value: 1 }, headPass, fineHead: { value: 0 }, nudge: { value: new THREE.Vector2() }, keepDark: { value: 0 }, ...paint } }));
  mesh.frustumCulled = false;
  mesh.matrixAutoUpdate = false;
  mesh.layers.enable(1);
  return mesh;
}
