// Forge gallery: a segment we filmed, beside what an AI restyle made of it. #/restyle/<name>
//
// scripts/video/omni.py packs a segment into exports/omni/<name>/ (source.mp4 and its other passes) and, once it has
// been sent, keeps what comes back in results/. This page plays ours and a result side by side from one Play
// button, so the two stay in step, and lets you pick which result, or which of our passes, sits on each side.

export function restylePage({ restyle, h }) {
  const base = `exports/omni/${encodeURIComponent(restyle.id)}/`;
  const ours = [["source.mp4", "Ours, bold ink"], ...Object.entries(restyle.variants || {}).filter(([k]) => k !== "source").map(([k, v]) => [v, `Ours, ${k.replace(/_/g, " ")}`])];
  const theirs = restyle.results.map((r) => [r, r.replace(/^results\//, "").replace(/\.mp4$/, "").replace(/-/g, " ")]);
  const film = (file) => h("video", { class: "restyle-film clay-well", src: base + file, muted: true, playsinline: true, preload: "auto" });
  const left = film(ours[0][0]);
  const right = theirs.length ? film(theirs[0][0]) : h("div", { class: "restyle-empty clay-well" }, "Nothing back yet. When a restyle is sent (just omni-send ... go) it lands here.");
  const pick = (options, video) => h("select", { class: "restyle-pick", onchange: (e) => { video.src = base + e.target.value; } }, options.map(([v, label]) => h("option", { value: v }, label)));
  const films = () => [left, right].filter((v) => v.tagName === "VIDEO");
  const play = h("button", { class: "clay-button", type: "button", onclick: () => {
    const all = films();
    if (all.every((v) => v.paused)) { all.forEach((v) => { v.currentTime = left.currentTime; v.play(); }); play.textContent = "Pause"; } else { all.forEach((v) => v.pause()); play.textContent = "Play both"; }
  } }, "Play both");
  const again = h("button", { class: "clay-button", type: "button", onclick: () => films().forEach((v) => { v.currentTime = 0; }) }, "From the start");
  // the right side follows the left, so a result that drifts a frame is pulled back
  left.addEventListener("timeupdate", () => films().slice(1).forEach((v) => { if (Math.abs(v.currentTime - left.currentTime) > 0.08) v.currentTime = left.currentTime; }));
  return h("article", { class: "object restyle-page" },
    h("a", { class: "back", href: "#/" }, "← Everything"),
    h("h1", {}, restyle.title),
    h("p", { class: "lede" }, `${restyle.seconds ? `${restyle.seconds} seconds` : "A segment"}, ours on the left, the restyle on the right. No sound.`),
    h("div", { class: "restyle-pair" },
      h("figure", {}, left, h("figcaption", {}, pick(ours, left))),
      h("figure", {}, right, h("figcaption", {}, theirs.length ? pick(theirs, right) : "The restyle"))),
    h("div", { class: "watch-bar" }, play, again),
    restyle.notes ? h("p", { class: "about" }, restyle.notes) : null,
  );
}
