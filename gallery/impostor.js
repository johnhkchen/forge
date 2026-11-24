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
import { eyeInBone, choose, place, corners, marchSteps, density, FILL, partBalls, ownTint, tintPlace, inBone, ballBack, jointNumber, behindOf, deepest, MARCH_MORE } from "./impostor-math.js";
import { LOOKS, lookOf, bakedFor, modelsOf, paintOf, setPaint, cardLine, cardNumber, Screen } from "./looks.js";

const PAPER = 0xebe6dc;

// headPass, fineHead and nudge are for a head on a finer grid (looks.js: Screen): a card that goes there
// (fineHead) is left out of the small picture and drawn in the heads' own drawing, slid by nudge.
export const CARD_VERTEX = `
uniform float headPass;
uniform float fineHead;
uniform vec2 nudge;
varying vec2 vSheet;
varying vec3 vView;
void main() {
  vSheet = uv;
  vView = (viewMatrix * vec4(position, 1.0)).xyz;
  gl_Position = projectionMatrix * vec4(vView, 1.0);
  if ((headPass > 0.5) != (fineHead > 0.5)) gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
  else if (headPass > 0.5) gl_Position.xy += nudge * gl_Position.w;
}`;

// One card. The colour sheet holds flat colour and the ink line; the data sheet holds the facing (two numbers,
// unfolded here) and the depth (0: nothing there). A pixel of the card looks down a line through the picture
// (impostor-math.js: place) and shows the first place where the picture's surface is as high as the line: a
// search in short steps, then halved in on. A place found far under the surface is the side of something the
// picture never saw the back of (the rim of a sleeve, the edge of the part): the search goes on from there, under
// it, to the next place the line comes down onto the surface, and only gives up when there is none. Mixing two
// views is done by a fixed pattern of pixels, each pixel one view or the other, so every pixel still has one
// true depth.
//
// A bent joint is filled here, two ways (impostor-math.js: FILL). `balls` are this part's joints as the eye has
// them: where each is, and one number more: the radius it is filled within in whole millimetres, and after the
// point how far back this part stands the ball (0 to a half: none to all of ballBackM). TINT(k) is the colour this
// part gives each ball, and the ball's radius.
//   - A pixel whose line went in only by the side of something and came down on no surface after would show
//     nothing, and where two parts meet that is the tear in the figure. It is filled where its line first runs
//     under the part's surface near a joint: there is body there, the limb going on into the next part. It takes
//     the colour of the surface over that place and stands a little behind it (fillBackM), so anything truly
//     there covers it. Along the side of a limb, away from any joint, nothing is filled.
//   - Every joint has a ball in it, small enough to lie inside the body. Where the eye meets a ball before it
//     meets the picture's surface, the ball shows: the eye is looking in at the open end of the part, at the
//     inside of its far wall, and the ball stops the hollow. Skin is nearer than the ball everywhere else. Where
//     the picture has no surface at all no ball is drawn (beside a thin arm in a wide sleeve it would be a knob). The two parts that meet there each draw it
//     in their own colour; the one whose body is behind the ball, as the eye sees it, is the one that shows.
//   - A joint with a piece of the real model in it (a knee, an elbow, a hip, a shoulder: JOINT_VERTEX, below) has a
//     zone, ZONE(k): its radius and its core's. It is on when the joint's fourth number is under 0. Inside the zone
//     the card shows only what is within the core's radius of its own bone's line, stood zoneBackM further back
//     (impostor-math.js: partBalls): the piece is what is there.
//
// A layer behind the first (impostor-math.js: behindOf). cellB, anchorB and lowB are the picture of what lay behind
// this one's surface: where it is on the sheet, where the bone's head is in it, and the lowest it stands (cellB's
// width 0: there is none, and nothing here is done). It is searched as the first is, step for step: the line goes
// under it, the place is halved in on, and it counts if that is the surface and not the side of something; of the
// two layers met in one step the higher shows. A layer behind may stand lower than the first ever does, so the
// search goes on down for it alone, up to MARCH_MORE steps. One thing more: the line may pass under the edge of
// something (a hat's brim) and come down on what is below (the crown) just where the brim's picture ends and the
// crown's own begins, both in the first layer. So where the first layer's surface has dropped by more than a wall
// since the last step and the line is now only just under it, that counts as coming down on it.
//
// The ink line round the part is marked in the data sheet (both of the facing's numbers are 0) and painted here.
// `line` says what becomes of it (looks.js: cardLine): over 0, it stands that many metres behind the surface, so
// the part next door covers it where two parts meet; under 0, it is left out, because the look draws one line
// round the whole figure on the finished picture, and `who` is then this card's number for that (cardNumber).
export const CARD_FRAGMENT = `
uniform mat4 projectionMatrix;
uniform sampler2D colourMap;
uniform sampler2D dataMap;
uniform vec2 sheetSize;
uniform float pxPerM;
uniform vec4 cell;
uniform vec2 anchor;
uniform vec2 heights;
uniform vec4 cellB;
uniform vec2 anchorB;
uniform float lowB;
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
uniform float line;
uniform float who;
uniform vec3 lineInk;
uniform float keepDark;
uniform vec4 balls[4];
uniform vec4 ballTint[4];
#define TINT(k) ballTint[k]
uniform vec2 zone[4];
#define ZONE(k) zone[k]
uniform float zoneBackM;
uniform float fillBackM;
uniform float ballBackM;
varying vec2 vSheet;
varying vec3 vView;
// How far toward the eye a place of the picture stands from the card, and whether it is near a joint.
float outAt(vec2 p, float h) {
  return (p.x * deep.x + p.y * deep.y + h * deep.z) * size;
}
bool inBall(vec2 p, float h) {
  vec3 here = vView + normalize(-vView) * outAt(p, h);
  for (int k = 0; k < 4; k++) {
    vec3 off = here - balls[k].xyz;
    float ring = floor(abs(balls[k].w)) / 1000.0;
    if (dot(off, off) < ring * ring) return true;
  }
  return false;
}
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
// The same of the layer behind.
bool readB(vec2 xy, out float height, out vec3 data) {
  vec2 c = xy * pxPerM + anchorB;
  if (!(c.x >= 0.0 && c.x < cellB.z && c.y >= 0.0 && c.y < cellB.w)) return false;
  data = textureLod(dataMap, (cellB.xy + c) / sheetSize, 0.0).rgb;
  height = (data.z * 2.0 - 1.0) * depthM;
  return data.z > 0.5 / 255.0;
}
void main() {
  if (mix_ == 1 && pattern(gl_FragCoord.xy) >= share) discard;
  if (mix_ == 2 && pattern(gl_FragCoord.xy) < share) discard;
  vec2 xy;
  float height;
  vec3 data;
  bool ok;
  bool behind = false;
  if (steps > 0) {
    float top = heights.y + 0.002, bottom = heights.x - 0.002;
    float above = top, below = bottom;
    bool found = false, was = false, filled = false;
    float fillAt = bottom;
    bool layered = cellB.z > 0.0, wasB = false, thereWas = false;
    float heightWas = 0.0, slack = (top - bottom) / float(steps) / 32.0;
    int more = layered && lowB < heights.x ? int(min(float(MARCH_MORE_), ceil((heights.x - lowB) * float(steps) / (top - bottom)))) : 0;
    for (int i = 1; i <= 32 + MARCH_MORE_; i++) {
      if (i > steps + more || found) break;
      float at = top + (bottom - top) * float(i) / float(steps);
      vec2 spot = inPicture(vSheet - at * lean);
      bool there = i <= steps && readAt(spot, height, data);  // (below the first layer's lowest only the layer behind is searched)
      bool under = there && height >= at;
      float heightNow = height;
      if (under && !was) { // the line has just gone under the surface: halve in on where
        float a = above, b = at;
        for (int k = 0; k < 5; k++) {
          float mid = (a + b) * 0.5;
          if (readAt(inPicture(vSheet - mid * lean), height, data) && height >= mid) b = mid; else a = mid;
        }
        // the surface itself, or the side of something? Under a side the search goes on
        if (readAt(inPicture(vSheet - b * lean), height, data) && height - b < wallM + (top - bottom) / float(steps) / 32.0) { below = b; found = true; }
      }
      // under the surface with no surface found, and inside a joint's ball: the first such place is kept for the filling
      if (under && !found && !filled && inBall(spot, at)) { filled = true; fillAt = at; }
      if (layered) {
        float last = top + (bottom - top) * float(i - 1) / float(steps);
        if (under && was && thereWas && heightWas - heightNow > wallM && heightNow - at < wallM) { // down past an edge onto what is below it
          float a = last, b = at, lid = heightNow + wallM * 0.5;
          for (int k = 0; k < 5; k++) {
            float mid = (a + b) * 0.5;
            if (readAt(inPicture(vSheet - mid * lean), height, data) && height >= mid && height < lid) b = mid; else a = mid;
          }
          if (readAt(inPicture(vSheet - b * lean), height, data) && height >= b && height - b < wallM + slack && height < lid && (!found || b > below)) { below = b; found = true; }
        }
        float heightB;
        vec3 dataB;
        bool underB = readB(spot, heightB, dataB) && heightB >= at;
        if (underB && !wasB) {
          float a = last, b = at;
          for (int k = 0; k < 5; k++) {
            float mid = (a + b) * 0.5;
            if (readB(inPicture(vSheet - mid * lean), heightB, dataB) && heightB >= mid) b = mid; else a = mid;
          }
          if (readB(inPicture(vSheet - b * lean), heightB, dataB) && heightB >= b && heightB - b < wallM + slack && (!found || b > below)) { below = b; found = true; behind = true; }
        }
        wasB = underB;
        thereWas = there;
        heightWas = heightNow;
      }
      if (!under) above = at;
      was = under;
    }
    if (!found) below = fillAt;
    xy = inPicture(vSheet - below * lean);
    ok = behind ? readB(xy, height, data) : (found || filled) && readAt(xy, height, data);
    if (ok && !found) {
      // the edge of a picture is its ink line: the colour is taken from a little further in along the pixel's line
      float run = length(inPicture(lean)) * pxPerM;
      for (int k = 0; k < 3; k++) {
        if (line == 0.0 || data.x >= 0.5 / 255.0 || data.y >= 0.5 / 255.0 || run < 1e-6) break;
        float further = below - 2.0 / run, height2;
        vec3 data2;
        vec2 spot = inPicture(vSheet - further * lean);
        if (!(readAt(spot, height2, data2) && height2 >= further)) break;
        below = further; xy = spot; height = height2; data = data2;
      }
      height = below - fillBackM;
    }
  } else {
    xy = inPicture(vSheet);
    ok = readAt(xy, height, data);
  }
  bool inked = ok && line != 0.0 && data.x + data.y < 0.5 / 255.0;
  if (inked && line < 0.0) ok = false;
  vec4 colour = vec4(0.0);
  vec4 cellNow = behind ? cellB : cell;      // the picture the pixel shown is read from: the first layer's, or the one behind
  vec2 anchorNow = behind ? anchorB : anchor;
  if (ok) {
    colour = textureLod(colourMap, (cellNow.xy + xy * pxPerM + anchorNow) / sheetSize, 0.0);
    // at the edge of a layer behind, smoothing mixes in the empty pixels beside it: the one sheet pixel it falls in
    if (behind && colour.a < 0.5) colour = texelFetch(colourMap, ivec2(floor(cellNow.xy + xy * pxPerM + anchorNow)), 0);
    if (colour.a < 0.5) ok = false;
  }
  if (!ok) discard;
  float out_ = outAt(xy, height - (inked ? line : 0.0));
  // inside a joint's zone the piece of the model there is what shows: the card keeps only what is near its own
  // bone's line, and stands that back
  float surfaceOut = out_;
  vec3 here = vView + normalize(-vView) * out_;
  for (int k = 0; k < 4; k++) {
    if (balls[k].w >= 0.0) continue;
    vec3 off = here - balls[k].xyz;
    vec2 z = ZONE(k);
    float far2 = dot(off, off);
    if (far2 >= z.x * z.x) continue;
    float along = dot(off, normalize(facingToEye[1]));
    if (far2 - along * along > z.y * z.y) discard;
    out_ = surfaceOut - zoneBackM;
  }
  // the ball in a joint: the nearest one the eye's own line through this pixel meets, if it meets it before the surface
  vec3 ray = normalize(vView);
  float nearest = length(vView) - surfaceOut;
  int ball = -1;
  float stoodBack = 0.0;
  for (int k = 0; k < 4; k++) {
    float inner = TINT(k).a, along = dot(ray, balls[k].xyz), back_ = fract(abs(balls[k].w)) * 2.0 * ballBackM;
    float root = along * along - dot(balls[k].xyz, balls[k].xyz) + inner * inner;
    if (inner <= 0.0 || root < 0.0) continue;
    float far = along - sqrt(root) + back_;
    if (far > back_ && far < nearest) { nearest = far; ball = k; stoodBack = back_; }
  }
  if (ball >= 0) {
    vec3 at = ray * nearest, seen = normalize(ray * (nearest - stoodBack) - balls[ball].xyz), tint = TINT(ball).rgb;
    float facing = dot(seen, light);
    vec3 tone = facing > edges.x ? vec3(1.0) : facing > edges.y ? shadeMid : shadeDark;
    vec4 clip = projectionMatrix * vec4(at, 1.0);
    gl_FragDepth = clip.z / clip.w * 0.5 + 0.5;
    gl_FragColor = vec4(mix(vec3(dot(tint, vec3(0.2126, 0.7152, 0.0722))), tint, punch) * tone + rim * pow(1.0 - clamp(seen.z, 0.0, 1.0), 3.0) * step(edges.x, facing), who);
    #include <colorspace_fragment>
    return;
  }
  if (keepDark > 0.5 && !inked) {
    // Shown smaller than it was pictured (one pixel here covers more than one of the sheet's), a pixel takes the
    // darkest of what it covers when that is a good deal darker than its middle and on the same surface: an eye
    // or a fold one sheet pixel wide is kept, where reading only the middle would drop it every other frame.
    float covers = pxPerM * length(dFdx(vSheet));
    if (covers > 1.0) {
      float reach = min(covers, 3.0) / 3.0, middle = dot(pow(colour.rgb, vec3(1.0 / 2.2)), vec3(0.2126, 0.7152, 0.0722)), best = middle;
      for (int i = 0; i < 4; i++) {
        vec2 c = xy * pxPerM + anchorNow + (i == 0 ? vec2(reach, 0.0) : i == 1 ? vec2(-reach, 0.0) : i == 2 ? vec2(0.0, reach) : vec2(0.0, -reach));
        if (c.x < 0.0 || c.x >= cellNow.z || c.y < 0.0 || c.y >= cellNow.w) continue;
        vec4 near = textureLod(colourMap, (cellNow.xy + c) / sheetSize, 0.0);
        vec3 nearData = textureLod(dataMap, (cellNow.xy + c) / sheetSize, 0.0).rgb;
        float grey = dot(pow(near.rgb, vec3(1.0 / 2.2)), vec3(0.2126, 0.7152, 0.0722));
        if (near.a > 0.5 && nearData.z > 0.5 / 255.0 && nearData.x + nearData.y > 0.5 / 255.0 && abs((nearData.z * 2.0 - 1.0) * depthM - height) < 0.02 && grey < best && grey < middle - 0.12) { best = grey; colour = near; }
      }
    }
  }
  vec3 seen = inked ? vec3(0.0, 0.0, 1.0) : facingToEye * unfold(data.xy);
  float facing = dot(seen, light);
  vec3 tone = facing > edges.x ? vec3(1.0) : facing > edges.y ? shadeMid : shadeDark;
  vec3 point = vView + normalize(-vView) * out_;
  vec4 clip = projectionMatrix * vec4(point, 1.0);
  gl_FragDepth = clip.z / clip.w * 0.5 + 0.5;
  vec3 paint = mix(vec3(dot(colour.rgb, vec3(0.2126, 0.7152, 0.0722))), colour.rgb, punch);
  gl_FragColor = vec4(inked ? lineInk : paint * tone + rim * pow(1.0 - clamp(seen.z, 0.0, 1.0), 3.0) * step(edges.x, facing), who);
  #include <colorspace_fragment>
}`.replaceAll("MARCH_MORE_", String(MARCH_MORE));
// Tell a card of the layer behind the picture it is showing (`behind`: behindOf's cell, or null), and give back the
// first layer's cell as its corners must have it (deepest): room for the lower layer to lean.
export function setBehind(quad, cell, behind) {
  const u = quad.material.uniforms;
  if (behind) {
    u.cellB.value.set(behind[0], behind[1], behind[2], behind[3]);
    u.anchorB.value.set(behind[4], behind[5]);
    u.lowB.value = behind[6];
  } else u.cellB.value.set(0, 0, 0, 0);
  return deepest(cell, behind);
}
// What every card's shader needs about the sheet's ink line, to go in with a material's other uniforms.
export const lineUniforms = () => ({ cellB: { value: new THREE.Vector4() }, anchorB: { value: new THREE.Vector2() }, lowB: { value: 0 }, line: { value: 0 }, who: { value: 1 }, lineInk: { value: new THREE.Color(0x1c1721) }, headPass: { value: 0 }, fineHead: { value: 0 }, nudge: { value: new THREE.Vector2() }, keepDark: { value: 0 },
  balls: { value: [0, 1, 2, 3].map(() => new THREE.Vector4()) }, ballTint: { value: [0, 1, 2, 3].map(() => new THREE.Vector4()) }, fillBackM: { value: FILL.backM }, ballBackM: { value: FILL.ballBackM },
  zone: { value: [0, 1, 2, 3].map(() => new THREE.Vector2()) }, zoneBackM: { value: FILL.zoneBackM } });
// For every part of a baked character, its joints for the filling (impostor-math.js: partBalls), each with
// tintAt(where the joint is in the part's bone's frame): the colour the part gives that joint's ball, looked up in
// the colour sheet the first time it is asked for and kept, as light adds up (the way the shader has every other
// colour). `sheet` is a view set with its colour picture loaded (colour: a texture).
const scrap = typeof document === "undefined" ? null : document.createElement("canvas");
export function sheetBalls(card, sheet) {
  const image = sheet.colour?.image;
  // the sheet is read a square at a time, each begun a little before the pixel asked for: the pixels round a place
  // are asked for row by row, left to right and upward
  const SIDE = 96;
  let left = 0, bottom = 0, block = null;
  const pixel = (x, y) => {
    if (!block || x < left || x >= left + SIDE || y < bottom || y >= bottom + SIDE) {
      const pen = scrap.getContext("2d", { willReadFrequently: true });
      if (scrap.width !== SIDE) scrap.width = scrap.height = SIDE;
      left = Math.max(0, x - 8);
      bottom = Math.max(0, y - 8);
      pen.clearRect(0, 0, SIDE, SIDE);
      pen.drawImage(image, left, image.height - bottom - SIDE, SIDE, SIDE, 0, 0, SIDE, SIDE);
      block = pen.getImageData(0, 0, SIDE, SIDE).data;
    }
    const i = ((SIDE - 1 - (y - bottom)) * SIDE + (x - left)) * 4;
    return [block[i], block[i + 1], block[i + 2], block[i + 3]];
  };
  const lit = new THREE.Color();
  return partBalls(card).map((joints, p) => joints.map((joint) => {
    let tint = null;
    const tintAt = (at) => {
      if (!tint) {
        const seen = image && scrap ? ownTint(card, sheet, card.parts[p], tintPlace(at, card.parts[p].center, joint.radius), FILL.tintReach * joint.inner, pixel) : [0.5, 0.5, 0.5];
        tint = lit.setRGB(seen[0], seen[1], seen[2], THREE.SRGBColorSpace).toArray();
      }
      return tint;
    };
    return { ...joint, tintAt };
  }));
}
// Tell a card where its part's joints are now, as the eye has them, for the filling of a bent joint. `joints` is
// the part's list from sheetBalls; `center` the part's middle in its bone's frame; `world` the part's bone;
// `at(bone)` gives where a bone's head is in the world now, or nothing if the skeleton has no such bone; `size` is
// how big the bone is drawn (1: as it was pictured).
// `zones` is whether the pieces of the model are being drawn in the joints that have one (skinFor, below): then
// the cards step aside in those joints' zones.
const jointSpot = new THREE.Vector3();
export function setBalls(quad, joints, center, world, camera, at, size = 1, zones = false) {
  const u = quad.material.uniforms, eye = camera.position;
  const middle = [world[12] + world[0] * center[0] + world[4] * center[1] + world[8] * center[2], world[13] + world[1] * center[0] + world[5] * center[1] + world[9] * center[2],
    world[14] + world[2] * center[0] + world[6] * center[1] + world[10] * center[2]];
  for (let k = 0; k < FILL.aPart; k++) {
    const joint = joints[k], p = joint && at(joint.bone);
    if (!p) { u.balls.value[k].set(0, 0, 0, 0); u.ballTint.value[k].set(0, 0, 0, 0); u.zone.value[k].set(0, 0); continue; }
    jointSpot.set(p[0], p[1], p[2]).applyMatrix4(camera.matrixWorldInverse);
    const tint = joint.tintAt(inBone(world, p));
    u.balls.value[k].set(jointSpot.x, jointSpot.y, jointSpot.z, jointNumber(joint.radius * size, ballBack(p, middle, [eye.x, eye.y, eye.z]), zones && joint.zone > 0));
    u.zone.value[k].set(joint.zone * size, joint.core * size);
    u.ballTint.value[k].set(tint[0], tint[1], tint[2], joint.inner * size);
  }
}
// Tell a head's card whether it goes on the finer grid this frame, and how far it is slid there (looks.js: headGrid).
// `at` is the bone's head in the world, as place() gives it.
const spot = new THREE.Vector3();
export function setHeadGrid(quad, screen, look, camera, at, part) {
  const slid = screen.headGrid(look, camera, spot.set(at[0], at[1], at[2]), part);
  const u = quad.material.uniforms;
  u.fineHead.value = slid ? 1 : 0;
  u.keepDark.value = slid ? 1 : 0;
  if (slid) u.nudge.value.set(slid[0], slid[1]);
}

// A piece of the real model in a joint (scripts/impostor/bake_joints.py). The cards are pictures of rigid parts,
// and a knee bent far, seen end on, is in none of them: the cloth pulled over it only exists when the model bends.
// So round every big joint the cards step aside and the model's own surface is drawn, pulled by the skeleton as
// the whole model would be: a few hundred triangles a joint. It is painted as the cards are: its colour is the
// cards' own, looked up from their sheets into one small picture (atlas), and so is which way its surface faces
// (atlasData: as the model has it at rest, folded as the sheets fold theirs), turned here as the bones have
// turned it. It is drawn inside the joint's zone and a little past it (`reach`, about `jointAt`, as the eye has
// it), from outside only: the inside of a sleeve or a trouser leg is never shown. `who` is the number of the card
// below the joint, for the lines a look draws on the finished picture. inkM over 0, back faces: its ink shell,
// for the looks that keep the line behind the surface.
export const JOINT_VERTEX = `
#include <common>
#include <skinning_pars_vertex>
uniform float inkM;
varying vec2 vAtlas;
varying vec3 vView;
varying vec3 vTurnX;
varying vec3 vTurnY;
varying vec3 vTurnZ;
void main() {
  vAtlas = vec2(uv.x, 1.0 - uv.y);
  #include <skinbase_vertex>
  #include <begin_vertex>
  transformed += normalize(normal) * inkM;
  #include <skinning_vertex>
  mat3 turn = mat3(viewMatrix) * mat3(skinWeight.x * boneMatX + skinWeight.y * boneMatY + skinWeight.z * boneMatZ + skinWeight.w * boneMatW);
  vTurnX = turn[0];
  vTurnY = turn[1];
  vTurnZ = turn[2];
  vec4 seen = modelViewMatrix * vec4(transformed, 1.0);
  vView = seen.xyz;
  gl_Position = projectionMatrix * seen;
}`;
export const JOINT_FRAGMENT = `
uniform sampler2D atlas;
uniform sampler2D atlasData;
uniform vec3 jointAt;
uniform float reach;
uniform float who;
uniform float inkM;
uniform vec3 lineInk;
uniform vec3 light;
uniform vec3 shadeMid;
uniform vec3 shadeDark;
uniform vec2 edges;
uniform float punch;
uniform float rim;
varying vec2 vAtlas;
varying vec3 vView;
varying vec3 vTurnX;
varying vec3 vTurnY;
varying vec3 vTurnZ;
vec3 unfold(vec2 e) {
  e = e * 2.0 - 1.0;
  vec3 n = vec3(e, 1.0 - abs(e.x) - abs(e.y));
  float t = clamp(-n.z, 0.0, 1.0);
  n.x += n.x >= 0.0 ? -t : t;
  n.y += n.y >= 0.0 ? -t : t;
  return normalize(n);
}
void main() {
  vec3 off = vView - jointAt;
  if (dot(off, off) > reach * reach) discard;
  if (inkM > 0.0) {
    gl_FragColor = vec4(lineInk, who);
  } else {
    vec3 colour = texture2D(atlas, vAtlas).rgb;
    vec3 seen = normalize(mat3(vTurnX, vTurnY, vTurnZ) * unfold(texture2D(atlasData, vAtlas).xy));
    float facing = dot(seen, light);
    vec3 tone = facing > edges.x ? vec3(1.0) : facing > edges.y ? shadeMid : shadeDark;
    vec3 paint = mix(vec3(dot(colour, vec3(0.2126, 0.7152, 0.0722))), colour, punch);
    gl_FragColor = vec4(paint * tone + rim * pow(1.0 - clamp(seen.z, 0.0, 1.0), 3.0) * step(edges.x, facing), who);
  }
  #include <colorspace_fragment>
}`;
// The pieces a baked character has for its joints, fetched: null when it has none. `loader` reads a .glb.
// "?joints=cards" in the page's address leaves them out, and the joints are then the cards' own as they were: for
// a picture of before and after, or to time what the pieces cost.
export async function skinFor(folder, card, loader) {
  if (!card.skin || new URLSearchParams(globalThis.location?.search || "").get("joints") === "cards") return null;
  const [gltf, colour, data] = await Promise.all([loader.loadAsync(`${folder}/${card.skin.file}`), picture(`${folder}/${card.skin.color}`, true, card.nearest), picture(`${folder}/${card.skin.data}`, false)]);
  const pieces = [];
  gltf.scene.traverse((o) => {
    const joint = o.isSkinnedMesh && card.skin.joints.find((j) => `joint ${j.bone}` === o.material.name);
    if (joint) pieces.push({ joint, geometry: o.geometry, bones: o.skeleton.bones.map((b) => b.name), inverses: o.skeleton.boneInverses, part: card.parts.findIndex((p) => p.name === joint.part) });
  });
  return { pieces, colour, data, inkM: card.ink_m || 0, dispose: () => { colour.dispose(); data.dispose(); pieces.forEach((p) => p.geometry.dispose()); } };
}
// The pieces as meshes riding a skeleton: `bones` is { name: bone } (the one the cards ride); `paint` the page's
// paint uniforms. Returns null if the skeleton lacks a bone the pieces need, else { group, set, dispose }.
// set(camera, look, card, figure) is for every frame: where each joint is as the eye has it, each piece's number,
// and whether its ink shell shows.
export function skinMeshes(skin, bones, paint) {
  if (!skin || skin.pieces.some((piece) => piece.bones.some((name) => !bones[name]))) return null;
  const group = new THREE.Group();
  const made = skin.pieces.map((piece) => {
    const skeleton = new THREE.Skeleton(piece.bones.map((name) => bones[name]), piece.inverses);
    return [0, 1].map((shell) => {
      const material = new THREE.ShaderMaterial({ vertexShader: JOINT_VERTEX, fragmentShader: JOINT_FRAGMENT, side: shell ? THREE.BackSide : THREE.FrontSide, uniforms: {
        atlas: { value: skin.colour }, atlasData: { value: skin.data }, jointAt: { value: new THREE.Vector3() }, reach: { value: 0 }, who: { value: 1 }, inkM: { value: shell ? skin.inkM : 0 },
        lineInk: { value: new THREE.Color(0x1c1721) }, ...paint } });
      const mesh = new THREE.SkinnedMesh(piece.geometry, material);
      mesh.bind(skeleton, new THREE.Matrix4());
      mesh.frustumCulled = false;
      group.add(mesh);
      return mesh;
    });
  });
  const at = new THREE.Vector3();
  return {
    group,
    set(camera, look, card, figure = 0) {
      const told = cardLine(card, look);
      skin.pieces.forEach((piece, i) => {
        const bone = bones[piece.joint.bone];
        at.setFromMatrixPosition(bone.matrixWorld).applyMatrix4(camera.matrixWorldInverse);
        const size = Math.cbrt(Math.abs(bone.matrixWorld.determinant()));
        made[i].forEach((mesh, shell) => {
          const u = mesh.material.uniforms;
          u.jointAt.value.copy(at);
          u.reach.value = (piece.joint.reach_cm / 100) * size;
          u.who.value = told.ids ? cardNumber(figure, piece.part) : 1;
          if (shell) mesh.visible = told.line > 0 && skin.inkM > 0;
        });
      });
    },
    dispose: () => made.flat().forEach((mesh) => { mesh.material.dispose(); mesh.skeleton.dispose(); }),
  };
}

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
    // the pieces of the model in the big joints, riding the skeleton of the clip that is playing
    this.joined?.dispose();
    this.joined = this.bones ? skinMeshes(this.skin, this.bones, this.paint) : null;
    if (this.joined) this.cards.add(this.joined.group);
    const line = new THREE.LineBasicMaterial({ color: 0x44679b, depthTest: false });
    const joints = sheetBalls(card, sheet);
    this.parts = card.parts.map((part, p) => {
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
            depthM: { value: part.depth_m }, share: { value: 1 }, mix_: { value: 0 }, ...lineUniforms(), ...this.paint,
          },
        });
        const quad = new THREE.Mesh(shape, paint);
        quad.frustumCulled = false;
        quad.matrixAutoUpdate = false;
        if (part.name === "head") { quad.layers.enable(1); paint.uniforms.headPass = this.screen.told.headPass; } // it may go on the finer grid
        this.cards.add(quad);
        return quad;
      });
      const outline = new THREE.LineLoop(quads[0].geometry, line);
      outline.frustumCulled = false;
      outline.renderOrder = 5;
      this.edges.add(outline);
      return { ...part, quads, joints: joints[p] };
    });
    this.setLine();
  }

  // Tell every card what this look does with the sheet's ink line.
  setLine() {
    const told = cardLine(this.card, this.look);
    (this.parts || []).forEach((part, p) => part.quads.forEach((quad) => {
      quad.material.uniforms.line.value = told.line;
      quad.material.uniforms.who.value = told.ids ? cardNumber(0, p) : 1;
    }));
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
    if (this.sheet) this.buildCards(); // the joints' pieces ride this clip's skeleton
    this.onFacts?.();
  }

  // Put every card where its bone is now, for where the eye is now.
  setCards() {
    if (!this.parts || !this.bones) return 0;
    const { card, sheet, camera, state } = this;
    const eye = camera.position.toArray();
    const toEye = new THREE.Matrix4();
    this.jointAt ||= (name) => { const e = this.bones[name]?.matrixWorld.elements; return e && [e[12], e[13], e[14]]; };
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
        const spots = corners(where, setBehind(quad, cell, state.relief ? behindOf(sheet, part.name, view) : null), density(card, part), state.relief);
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
        setBalls(quad, part.joints, part.center, world, camera, this.jointAt, where.size, Boolean(this.joined));
        if (part.name === "head") setHeadGrid(quad, this.screen, this.look, camera, where.head, this.el.classList.contains("stacked") ? { w: 1, h: 0.5 } : { w: 0.5, h: 1 });
      });
    }
    this.joined?.set(camera, this.look, card);
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
      this.skin?.dispose();
      this.skin = await skinFor(folder, this.card, this.loader);
      for (const sheet of Object.values(this.sheets)) { sheet.colour.dispose(); sheet.data.dispose(); }
      this.sheets = {};
      this.paint ||= paintOf(this.card.light);
      await this.useViews(this.card.sets[this.state.views] ? this.state.views : this.card.default_views);
    }
    setPaint(this.paint, this.look);
    this.setLine();
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
    this.joined?.dispose();
    this.skin?.dispose();
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
