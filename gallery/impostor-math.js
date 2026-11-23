// Forge gallery: where a flat card goes, and how its picture is read. The arithmetic of
// scripts/impostor/impostor.py, kept apart from three.js so that scripts/impostor/test_impostor.py can run it in
// node and hold the two against each other.
//
// A bone is its 4x4 matrix in the world as three.js keeps it (16 numbers, column by column). A view is one
// entry of impostor.json's "views": d (from the part to the eye, in the bone's frame) and the picture's own
// right and up, r and u. A cell is one picture on its sheet: x, y, wide, tall (pixels, from the sheet's bottom
// left), where the bone's head is in it (ax, ay), and the lowest and highest its surface stands (metres).

const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const scale = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const unit = (a) => scale(a, 1 / Math.max(Math.hypot(a[0], a[1], a[2]), 1e-12));
const turned = (m, v) => [m[0] * v[0] + m[4] * v[1] + m[8] * v[2], m[1] * v[0] + m[5] * v[1] + m[9] * v[2], m[2] * v[0] + m[6] * v[1] + m[10] * v[2]];
const turnedBack = (m, v) => [m[0] * v[0] + m[1] * v[1] + m[2] * v[2], m[4] * v[0] + m[5] * v[1] + m[6] * v[2], m[8] * v[0] + m[9] * v[1] + m[10] * v[2]];
const angle = (a, b) => (Math.acos(Math.max(-1, Math.min(1, dot(a, b)))) * 180) / Math.PI;

// The direction from the middle of a part to the eye, in the bone's frame.
export function eyeInBone(bone, center, eye) {
  const middle = add([bone[12], bone[13], bone[14]], turned(bone, center));
  return unit(turnedBack(bone, sub(eye, middle)));
}

// Which view to show, which is next nearest, and how much of the first to show (1 = all of it). `held` is the
// view shown last time: it is kept until another is nearer by holdDeg. The share falls to a half as the eye
// reaches the line between the two views, across blendDeg.
export function choose(dirs, v, held, holdDeg, blendDeg) {
  let first = -1, second = -1, a1 = 999, a2 = 999;
  for (let i = 0; i < dirs.length; i++) {
    const a = angle(dirs[i], v);
    if (a < a1) { second = first; a2 = a1; first = i; a1 = a; } else if (a < a2) { second = i; a2 = a; }
  }
  if (held !== undefined && held !== null && held !== first) {
    const heldAngle = angle(dirs[held], v);
    if (heldAngle - a1 < holdDeg) {
      return { first: held, second: first, share: Math.min(1, Math.max(0, 0.5 + (0.5 * (a1 - heldAngle)) / blendDeg)), off: heldAngle };
    }
  }
  return { first, second, share: Math.min(1, 0.5 + (0.5 * (a2 - a1)) / blendDeg), off: a1 };
}

// Where one part's card stands, and how its picture is read, for one view. The card is a flat sheet through the
// bone's head, square on to the eye. A place on it is two numbers P (metres at the bone's own size): across,
// along e2, and up, along e1; e1 is the bone itself as it shows from here.
//
// The picture was taken from the view's direction d, not from where the eye now is. A point of it X right, Y up
// and h toward its own eye shows on the sheet at  P = turnXY . (X, Y) + h * lean.  Read backwards, a pixel at P
// looks along the line (X, Y) = back . (P - h * lean) for every h, and shows the first place on it where the
// picture's surface is at least h high (the card's shader walks down that line). `deep` gives how far toward the
// eye a point stands: X, Y, h times its three numbers.
export function place(view, bone, center, eye) {
  const size = Math.cbrt(Math.abs(
    bone[0] * (bone[5] * bone[10] - bone[9] * bone[6]) - bone[4] * (bone[1] * bone[10] - bone[9] * bone[2]) + bone[8] * (bone[1] * bone[6] - bone[5] * bone[2])));
  const head = [bone[12], bone[13], bone[14]];
  const middle = add(head, turned(bone, center));
  const toward = unit(sub(eye, middle));
  let axis = scale([bone[4], bone[5], bone[6]], 1 / size);
  let flat = sub(axis, scale(toward, dot(axis, toward)));
  if (Math.hypot(flat[0], flat[1], flat[2]) < 1e-4) { // the bone points straight at the eye: its x will do
    axis = scale([bone[0], bone[1], bone[2]], 1 / size);
    flat = sub(axis, scale(toward, dot(axis, toward)));
  }
  const e1 = unit(flat);
  const e2 = cross(e1, toward);
  const inBone = (w) => scale(turnedBack(bone, w), 1 / size);
  const a1 = inBone(e1), a2 = inBone(e2), v = inBone(toward);
  const { r, u, d } = view;
  const m = [dot(r, a2), dot(u, a2), dot(r, a1), dot(u, a1)]; // turnXY, row by row
  const det = m[0] * m[3] - m[1] * m[2];
  return {
    head, toward, size, e1, e2, turnXY: m,
    back: [m[3] / det, -m[1] / det, -m[2] / det, m[0] / det],
    lean: [dot(d, a2), dot(d, a1)],
    deep: [dot(r, v), dot(u, v), dot(d, v)],
  };
}

// The part of the sheet a card must cover: [left, bottom, right, top] in the sheet's own metres. The picture's
// four corners as they now show, and (relief) room for its pixels to lean, by how low and high its surface goes.
export function box(card, cell, pxPerM, relief = true) {
  const [, , w, h, ax, ay, low, high] = cell;
  const m = card.turnXY;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [cx, cy] of [[0, 0], [w, 0], [w, h], [0, h]]) {
    const X = (cx - ax) / pxPerM, Y = (cy - ay) / pxPerM;
    const px = m[0] * X + m[1] * Y, py = m[2] * X + m[3] * Y;
    x0 = Math.min(x0, px); x1 = Math.max(x1, px); y0 = Math.min(y0, py); y1 = Math.max(y1, py);
  }
  const [lx, ly] = relief ? card.lean : [0, 0];
  return [x0 + Math.min(lx * low, lx * high), y0 + Math.min(ly * low, ly * high), x1 + Math.max(lx * low, lx * high), y1 + Math.max(ly * low, ly * high)];
}

// The four corners of a card in the world (left-bottom, right-bottom, right-top, left-top), and the same four
// as places on the sheet.
export function corners(card, cell, pxPerM, relief = true) {
  const [x0, y0, x1, y1] = box(card, cell, pxPerM, relief);
  const sheet = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
  return { sheet, world: sheet.map(([x, y]) => add(card.head, scale(add(scale(card.e2, x), scale(card.e1, y)), card.size))) };
}

// How many steps the search down a pixel's line takes: enough that none is longer than march.px of the picture.
export function marchSteps(card, cell, pxPerM, march) {
  const b = card.back, l = card.lean;
  const reach = Math.hypot(b[0] * l[0] + b[1] * l[1], b[2] * l[0] + b[3] * l[1]) * (cell[7] - cell[6]) * pxPerM;
  return Math.min(march.max, Math.max(1, Math.ceil(reach / march.px)));
}
