// Forge gallery: a drawn face for a mesh shown as pixel art.
//
// A low-poly mesh drawn small has the same trouble a small card has: an eye is less than a pixel, or was never
// modelled at all. The cards get their face drawn into their pictures when they are baked, from the character's
// recipe (scripts/impostor/pixel_face.py), and the bake keeps the recipe's marks in impostor.json: where each is
// on the head, which way the face looks there, how big it is and its colours. Here the same marks are laid on a
// mesh's head as small flat patches that ride the head bone: eyes, brows, a mouth, round spectacles, an eye patch.
//
// A mark's place is on the detailed model's surface, and a low-poly head is a centimetre or two off that. So each
// mark is dropped onto the mesh actually shown: a line from in front of the face, straight back, and the first
// place it meets the mesh.
import * as THREE from "three";

const VERTEX = `
attribute vec3 paint;
attribute vec3 inside;
attribute vec3 shape;   // kind (0 block, 1 disc, 2 ring), where the rim starts (share of the way out), unused
varying vec2 vUv;
varying vec3 vPaint;
varying vec3 vInside;
varying vec3 vShape;
void main() {
  vUv = uv;
  vPaint = paint;
  vInside = inside;
  vShape = shape;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;
const FRAGMENT = `
varying vec2 vUv;
varying vec3 vPaint;
varying vec3 vInside;
varying vec3 vShape;
void main() {
  float out_ = length(vUv);
  if (vShape.x > 0.5 && out_ > 1.0) discard;
  bool lens = vShape.x > 1.5 && out_ < vShape.y;
  if (lens && vInside.x < 0.0) discard;   // a rim with nothing in it
  gl_FragColor = vec4(lens ? vInside : vPaint, 1.0);
  #include <colorspace_fragment>
}`;

// The folder of a run's baked cards that may have a drawn face, for one model ("detailed"), or null: the pixel
// sheet baked since the joints were mended, or the older one that was kept apart for having a face.
export function faceFolderOf(run, model) {
  const cards = run?.cards || [];
  const found = cards.find((c) => c.profile === model && c.folder.endsWith("-impostor-pixel-joined")) || cards.find((c) => c.profile === model && c.folder.endsWith("-faces")) || cards.find((c) => c.folder.endsWith("-faces"));
  return found ? found.folder : null;
}

// The marks as one small mesh riding a head bone. `meshes` are the skinned meshes shown (each mark is dropped onto
// them); with none, or where the line back from a mark misses them, the mark stays where the recipe has it.
export function faceMarks(marks, bone, meshes = []) {
  const front = new THREE.Vector3(0, 0, 1), up = new THREE.Vector3(0, 1, 0);
  bone.updateWorldMatrix(true, false);
  const toWorld = bone.matrixWorld, toBone = new THREE.Matrix4().copy(toWorld).invert();
  const size = new THREE.Vector3().setFromMatrixScale(toWorld).x || 1;
  const ray = new THREE.Raycaster();
  const at = [], uv = [], paint = [], inside = [], shape = [], index = [];
  const colour = (c) => new THREE.Color().setRGB(c[0] / 255, c[1] / 255, c[2] / 255, THREE.SRGBColorSpace);
  let dropped = 0;
  marks.forEach((mark, k) => {
    const p = new THREE.Vector3(...mark.p), n = new THREE.Vector3(...mark.n).normalize();
    if (meshes.length) {
      const from = p.clone().addScaledVector(front, 0.3).applyMatrix4(toWorld);
      ray.set(from, front.clone().transformDirection(toWorld).negate());
      ray.far = 0.6 * size;
      const hit = ray.intersectObjects(meshes, false)[0];
      if (hit) { p.copy(hit.point).applyMatrix4(toBone); dropped += 1; }
    }
    const across = new THREE.Vector3().crossVectors(up, n).normalize(), rise = new THREE.Vector3().crossVectors(n, across);
    const [w, h] = mark.size;
    const lift = 0.003 + 0.0006 * k;   // each mark a hair in front of the one before it, so later ones show over earlier ones
    const c = colour(mark.colour), l = mark.lens ? colour(mark.lens) : null;
    const kind = mark.kind === "ring" ? 2 : mark.kind === "disc" ? 1 : 0;
    const rim = kind === 2 ? Math.max(0, 1 - mark.rim_m / (Math.min(w, h) / 2)) : 0;
    [[-1, -1], [1, -1], [1, 1], [-1, 1]].forEach(([sx, sy]) => {
      const q = p.clone().addScaledVector(across, sx * w / 2).addScaledVector(rise, sy * h / 2).addScaledVector(n, lift);
      at.push(q.x, q.y, q.z);
      uv.push(sx, sy);
      paint.push(c.r, c.g, c.b);
      inside.push(...(l ? [l.r, l.g, l.b] : [-1, -1, -1]));
      shape.push(kind, rim, 0);
    });
    index.push(k * 4, k * 4 + 1, k * 4 + 2, k * 4, k * 4 + 2, k * 4 + 3);
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(at, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  geometry.setAttribute("paint", new THREE.Float32BufferAttribute(paint, 3));
  geometry.setAttribute("inside", new THREE.Float32BufferAttribute(inside, 3));
  geometry.setAttribute("shape", new THREE.Float32BufferAttribute(shape, 3));
  geometry.setIndex(index);
  const face = new THREE.Mesh(geometry, new THREE.ShaderMaterial({ vertexShader: VERTEX, fragmentShader: FRAGMENT, side: THREE.FrontSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
  face.frustumCulled = false;
  face.userData.dropped = dropped;
  bone.add(face);
  return face;
}
