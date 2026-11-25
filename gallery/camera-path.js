// Forge gallery: a camera that moves, as a shot's plan keeps it (plan.json's moving_cameras). The same arithmetic as
// scripts/sets/camera_path.py, which the films use, so the watch page and a background Blender put the lens in the
// same place at the same moment (scripts/sets/test_camera_path.py checks the two agree, in node).
//
// A moving camera is a few keys: {at_s, at, aim, lens_mm, ease}. Before the first key it waits on it, after the last
// it stays on it; between two keys the lens, the point it looks at and the focal length go in a straight line,
// eased as the later key says.

export function ease(kind, t) {
  t = Math.min(1, Math.max(0, t));
  if (kind === "linear") return t;
  if (kind === "in") return 1 - Math.cos((t * Math.PI) / 2);
  if (kind === "out") return Math.sin((t * Math.PI) / 2);
  if (kind === "hold") return t >= 1 ? 1 : 0;
  return 0.5 - 0.5 * Math.cos(t * Math.PI); // in_out
}

// Where the camera is at t seconds: {at, aim, lens_mm}.
export function sample(camera, t) {
  const keys = camera.keys;
  const copy = (k) => ({ at: [...k.at], aim: [...k.aim], lens_mm: k.lens_mm });
  if (t <= keys[0].at_s || keys.length === 1) return copy(keys[0]);
  for (let i = 1; i < keys.length; i++) {
    const a = keys[i - 1], b = keys[i];
    if (t <= b.at_s) {
      const span = b.at_s - a.at_s;
      const u = ease(b.ease, span > 0 ? (t - a.at_s) / span : 1);
      const mix = (p, q) => p.map((v, k) => v + (q[k] - v) * u);
      return { at: mix(a.at, b.at), aim: mix(a.aim, b.aim), lens_mm: a.lens_mm + (b.lens_mm - a.lens_mm) * u };
    }
  }
  return copy(keys[keys.length - 1]);
}

// The up-down field of view (degrees) of a lens on a 36 mm wide picture, as three.js wants it.
export function fovOf(lensMm, aspect = 16 / 9) {
  return (2 * Math.atan(36 / aspect / 2 / lensMm) * 180) / Math.PI;
}
