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

// How fine a part's pictures are, pixels a metre: its own when it was pictured finer than the rest (a head).
export const density = (card, part) => part.px_per_m || card.px_per_m;

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

// Filling a bent joint. Where two parts meet, a bend opens the figure: each card's picture never saw what lies
// beyond its own edge there, and the open end of a limb shows as a hollow. Two things mend it, both in the card's
// shader (CARD_FRAGMENT):
//   - a ball in every joint, small enough to lie inside the body (FILL.inner of the ball the bake found room for).
//     It shows wherever the eye meets it before it meets the picture's surface, which only happens where a bend
//     has opened the figure. Both parts that meet at the joint draw it, each in its own colour near the joint
//     (looked for FILL.tintIn of the ring's radius in from the joint, FILL.tintReach of the ball's radius round
//     there), and the part whose body is not behind the ball, as the eye sees it, stands its own back by up to
//     FILL.ballBackM: looking in at the open end of a thigh, the ball is the thigh's colour;
//   - a see-through pixel is filled where its line runs under the part's own surface inside a wider ball about
//     the joint (FILL.ball of the radius of the ring where the two parts meet): the limb goes on into the next
//     part there. FILL.backM: how far behind its place such a pixel stands, so anything truly there covers it.
// FILL.aPart: a part meets at most this many others. scripts/impostor/impostor.py has the same numbers.
export const FILL = { ball: 1.0, backM: 0.02, inner: 0.8, tintReach: 0.6, tintIn: 0.8, ballBackM: 0.01, aPart: 4 };

// The colour a part gives the ball of one of its joints: the middle colour (each of red, green and blue by itself)
// of what the part's own pictures show round a place on it (`at`, in the bone's frame, metres; reachM round it),
// seen from the side. `sheet` is one view set of the card (views, cells); pixel(x, y) gives the colour sheet's
// pixel x from the left and y from the bottom, four numbers 0 to 255. Returns three numbers 0 to 1, as the sheet
// stores colour. (impostor.py: own_tint.)
export function ownTint(card, sheet, part, at, reachM, pixel) {
  const ppm = density(card, part), reach = Math.max(2, reachM * ppm);
  const seen = [[], [], []];
  sheet.views.forEach((view, v) => {
    const [x0, y0, wide, tall, ax, ay] = sheet.cells[part.name][v];
    if (Math.abs(view.d[1]) >= 0.5 || wide <= 0 || tall <= 0) return;
    const mx = ax + ppm * dot(at, view.r), my = ay + ppm * dot(at, view.u);
    for (let cy = Math.max(0, Math.floor(my - reach)); cy < Math.min(tall, Math.ceil(my + reach) + 1); cy++) {
      for (let cx = Math.max(0, Math.floor(mx - reach)); cx < Math.min(wide, Math.ceil(mx + reach) + 1); cx++) {
        if ((cx + 0.5 - mx) ** 2 + (cy + 0.5 - my) ** 2 > reach * reach) continue;
        const got = pixel(x0 + cx, y0 + cy);
        if (got[3] >= 128) for (let k = 0; k < 3; k++) seen[k].push(got[k]);
      }
    }
  });
  if (!seen[0].length) return [0.5, 0.5, 0.5];
  return seen.map((channel) => channel.sort((a, b) => a - b)[Math.floor(channel.length / 2)] / 255);
}

// Where on a part to look for that colour: FILL.tintIn of the joint's ring radius in from the joint, toward the
// middle of the part: its own skin, past what it borrows from next door. All in the bone's frame.
export const tintPlace = (jointAt, center, ring) => add(jointAt, scale(unit(sub(center, jointAt)), FILL.tintIn * ring));

// A place in the world as a bone has it (the bone as three.js keeps it), at the bone's own size.
export function inBone(bone, at) {
  const size = Math.cbrt(Math.abs(
    bone[0] * (bone[5] * bone[10] - bone[9] * bone[6]) - bone[4] * (bone[1] * bone[10] - bone[9] * bone[2]) + bone[8] * (bone[1] * bone[6] - bone[5] * bone[2])));
  return scale(turnedBack(bone, sub(at, [bone[12], bone[13], bone[14]])), 1 / (size * size));
}

// How far back a part stands the ball of one of its joints (m): nothing when the part's own body is straight behind
// the ball as the eye sees it, FILL.ballBackM when it is straight in front. jointAt, middle (of the part) and eye
// are in the world.
export const ballBack = (jointAt, middle, eye) => (FILL.ballBackM * (1 - dot(unit(sub(middle, jointAt)), unit(sub(jointAt, eye))))) / 2;

// For every part of a baked character, in order, the joints it has: [{ bone: the bone whose head is the joint,
// radius: within which a see-through pixel is filled, inner: of the ball in it (metres at the bone's own size) }].
// A sheet baked before the joints were mended says nothing of them: no balls.
export function partBalls(card) {
  const out = card.parts.map(() => []);
  for (const joint of card.joints || []) for (const name of joint.between) {
    const p = card.parts.findIndex((part) => part.name === name);
    if (p >= 0 && out[p].length < FILL.aPart) out[p].push({ bone: joint.bone, radius: (FILL.ball * joint.ring_cm) / 100, inner: (FILL.inner * joint.ball_cm) / 100 });
  }
  return out;
}

// How many steps the search down a pixel's line takes: enough that none is longer than march.px of the picture.
export function marchSteps(card, cell, pxPerM, march) {
  const b = card.back, l = card.lean;
  const reach = Math.hypot(b[0] * l[0] + b[1] * l[1], b[2] * l[0] + b[3] * l[1]) * (cell[7] - cell[6]) * pxPerM;
  return Math.min(march.max, Math.max(1, Math.ceil(reach / march.px)));
}
