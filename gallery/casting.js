// Forge gallery: casting, the way a casting director finds a new member of the cast. #/casting[/<role>[/<candidate>[/<take>]]]
//
// A role (scripts/casting, casting/<role>/role.json) goes Breakdown -> Headshots -> Shortlist -> Tapes -> Callbacks
// -> Cast. Its page is the board, the breakdown, the headshots, and everyone on the shortlist side by side. A
// candidate's page is one take at a time and the takes before it: the reel (the same scenes for everyone, played as
// flat cards beside the real model by the cards page, in any look), the chemistry read (the crew's dance with the
// candidate in one dancer's place, and a sparring bout, on the watch page), the line-up beside the cast, the camera
// test's scores against the cast member it stands in for, and your notes, which become the next take.
//
// The page writes only notes and choices (POST /api/casting/..., which scripts/casting/casting.py checks). A step
// that costs money is never started from here: "Try it first" asks the server what it would do and what it costs.
import * as THREE from "three";

const STATUS_WORDS = { submitted: "Sent in", shortlisted: "On the shortlist", "let go": "Let go", cast: "Cast" };
const ABOUT_WORDS = { look: "The look", moves: "The moves", cards: "The cards" };
const ABOUT_HINTS = {
  look: "A new picture and a new build. This one costs money.",
  moves: "Its walk, its sides, how it is rigged. Free to try again.",
  cards: "Baked again, or a note for the renderer. Free.",
};
const SCORE_LOOKS = ["joe", "pixel-both", "comic"];
const FPS = 30;

const money = (usd) => `$${Number(usd).toFixed(2)}`;
const metres = (m) => (m ? `${Number(m).toFixed(2)} m` : "—");

async function post(url, body) {
  const answer = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const said = await answer.json().catch(() => ({}));
  if (!answer.ok) throw new Error(said.error || `the gallery said ${answer.status}`);
  return said.result;
}

// ---------- the front page's card, and the list of roles ----------

export function castingCard(roles, h) {
  if (!roles.length) return null;
  return h("section", { class: "casting-shelf" },
    h("h2", { class: "shelf-heading" }, "Casting"),
    h("div", { class: "shelf" }, roles.map((role) => {
      const now = role.board.stages.find((s) => s.id === role.board.now);
      const face = role.candidates.find((c) => !c.stand_in && c.picture) || role.candidates.find((c) => c.picture);
      return h("a", { class: "card clay-surface casting-card", href: `#/casting/${encodeURIComponent(role.id)}` },
        face ? h("img", { src: face.picture, alt: "", loading: "lazy" }) : h("div", { class: "casting-card-blank" }, "?"),
        h("div", { class: "label" },
          h("h2", {}, role.title),
          h("p", {}, `Now at ${now.name.toLowerCase()} · ${role.candidates.length} trying out`)));
    })));
}

export function castingList(roles, h) {
  return h("article", { class: "object casting" },
    h("a", { class: "back", href: "#/" }, "← Everything"),
    h("h1", {}, "Casting"),
    h("p", { class: "lede" }, "New members of the cast are found here, one part at a time: who the part is, pictures of who might play it, the few worth building, the same scenes for each of them, your notes, and the one you choose."),
    castingCard(roles, h) || h("p", { class: "empty" }, "No parts being cast. A part is a folder in casting/ with a role.json."));
}

// ---------- one role ----------

function board(role, h, here) {
  return h("ol", { class: "casting-board", "aria-label": "How far this part has come" }, role.board.stages.map((s) =>
    h("li", { class: `casting-stage clay-surface${s.reached ? " reached" : ""}${s.id === role.board.now ? " now" : ""}${s.id === here ? " here" : ""}`, title: s.about },
      h("a", { href: `#/casting/${encodeURIComponent(role.id)}`, onclick: (e) => {
        const target = document.getElementById(`stage-${s.id}`);
        if (target) { e.preventDefault(); target.scrollIntoView({ behavior: "smooth", block: "start" }); }
      } },
      h("span", { class: "casting-stage-name" }, s.name),
      h("span", { class: "casting-stage-count" }, s.id === "breakdown" ? (s.count ? "Written" : "Not yet") : String(s.count))))));
}

function list(h, title, items) {
  return items?.length ? h("div", { class: "casting-list" }, h("h3", {}, title), h("ul", {}, items.map((i) => h("li", {}, i)))) : null;
}

function breakdown(role, h) {
  const b = role.breakdown || {};
  return h("section", { class: "casting-section", id: "stage-breakdown" },
    h("h2", {}, "The breakdown"),
    h("p", { class: "casting-drafted" }, role.drafted || ""),
    h("div", { class: "casting-two" },
      h("div", { class: "clay-surface casting-panel" },
        h("p", { class: "casting-logline" }, b.logline),
        h("h3", {}, "Who they are"), h("p", {}, b.essence),
        h("h3", {}, "What they look like"), h("p", {}, b.look),
        h("h3", {}, "From across the stage"), h("p", {}, b.silhouette),
        h("h3", {}, `How tall: ${metres(b.height_m)}`), h("p", {}, b.height_why),
        h("h3", {}, "Where they fit"), h("p", {}, b.in_the_ensemble)),
      h("div", { class: "clay-surface casting-panel" },
        h("h3", {}, "Colours, chosen against the cast"),
        h("div", { class: "casting-swatches" }, (b.palette || []).map((p) =>
          h("div", { class: "casting-swatch" }, h("span", { class: "chip-colour", style: `background:${p.hex}` }), h("span", {}, h("b", {}, p.name), ` ${p.where}`)))),
        h("p", { class: "about" }, b.palette_why),
        list(h, "Why it reads as cards", b.reads_as_cards),
        list(h, "In bold ink", b.reads_in_bold_ink),
        list(h, "In “Pixels, both”", b.reads_in_pixels_both),
        list(h, "Must have", b.must_have),
        list(h, "Must not have", b.must_not),
        b.the_sides_it_must_pass ? h("p", { class: "about" }, b.the_sides_it_must_pass) : null)),
    canonOptions(role, h));
}

function canonOptions(role, h) {
  if (!role.canon_options.length) return null;
  return h("div", { class: "casting-canon" },
    h("h3", {}, "How it could arrive: yours to choose"),
    h("p", { class: "about" }, role.canon_choice ? `Chosen: ${role.canon_choice}.` : "None of these is canon. Pick one (or none) and it goes in canon/CANON.md when a strip shows it."),
    h("div", { class: "casting-grid" }, role.canon_options.map((o) =>
      h("div", { class: `clay-surface casting-panel${role.canon_choice === o.id ? " chosen" : ""}` },
        h("h4", {}, o.name),
        h("p", {}, o.pitch),
        h("p", { class: "about" }, h("b", {}, "Who paid: "), o.who_paid),
        h("p", { class: "about" }, h("b", {}, "Where it lives: "), o.where),
        h("p", { class: "about" }, h("b", {}, "Names to try: "), (o.names || []).join(", ")),
        h("p", { class: "about" }, o.touches)))));
}

function stepBox(step, role, candidate, h) {
  const out = h("div", { class: "casting-plan", hidden: true });
  const tryIt = async () => {
    out.hidden = false;
    out.replaceChildren(h("p", {}, "Asking…"));
    try {
      const plan = await post(`api/casting/${encodeURIComponent(role.id)}/plan`, { step: step.id, candidate: candidate?.id || null });
      const command = h("code", {}, plan.command);
      out.replaceChildren(
        h("p", {}, h("b", {}, "Nothing was started. "), plan.what),
        h("p", {}, h("b", {}, plan.paid ? "It costs: " : "Cost: "), plan.cost),
        plan.warning ? h("p", { class: "casting-warning" }, plan.warning) : null,
        plan.notes?.length ? h("p", { class: "about" }, `It would answer ${plan.notes.length} open note${plan.notes.length > 1 ? "s" : ""}.`) : null,
        h("p", { class: "casting-command" }, "To run it, in Terminal: ", command, " ",
          h("button", { class: "chip clay-chip", type: "button", onclick: (e) => { navigator.clipboard?.writeText(plan.command); e.target.textContent = "Copied"; } }, "Copy")));
    } catch (err) {
      out.replaceChildren(h("p", { class: "casting-warning" }, String(err.message || err)));
    }
  };
  return h("div", { class: `clay-surface casting-step${step.paid ? " paid" : " free"}` },
    h("div", { class: "casting-step-head" },
      h("h4", {}, step.name),
      h("span", { class: `casting-price${step.paid ? " paid" : ""}` }, step.paid ? (step.high ? (step.low === step.high ? `about ${money(step.high)}` : `${step.low ? money(step.low) : "Free"}–${money(step.high)}`) : "Pictures") : "Free")),
    h("p", { class: "about" }, step.what),
    h("button", { class: "clay-button clay-button--soft casting-try", type: "button", onclick: tryIt }, step.paid ? "See what it would cost" : "See what it would do"),
    out);
}

// Put one headshot on the shortlist: `shot` is a look's id for its first picture, "<look>.<n>" for another.
function shortlister(role, refresh) {
  return async (shot, button) => {
    button.disabled = true;
    try { await post(`api/casting/${encodeURIComponent(role.id)}/shortlist`, { look: shot }); refresh(); }
    catch (err) { button.disabled = false; button.textContent = String(err.message || err); }
  };
}

function shortlistButton(shot, candidate, shortlist, h, label = "Put on the shortlist") {
  return candidate ? h("span", { class: "casting-done" }, label === "Put on the shortlist" ? "On the shortlist" : `${label}: on the shortlist`)
    : h("button", { class: "clay-button clay-button--soft", type: "button", onclick: (e) => shortlist(shot, e.target) }, label);
}

function headshots(role, h, refresh) {
  const looks = role.looks;
  const standIns = role.candidates.filter((c) => c.stand_in);
  const shortlist = shortlister(role, refresh);
  const arrival = (id) => role.canon_options.find((o) => o.id === id)?.name;
  return h("section", { class: "casting-section", id: "stage-headshots" },
    h("h2", {}, "Headshots"),
    h("p", { class: "lede" }, `${looks.length} looks, each a whole brief. Codex draws each a few times, a different design each time, on your ChatGPT plan. ${role.board.drawn ? `${role.board.drawn} pictures so far.` : "None drawn yet: that is the first step that spends anything."}`),
    h("div", { class: "casting-grid casting-looks" }, looks.map((look) => {
      const pictures = look.pictures || [];
      // The first picture large, the others small beside it; every drawn one can go on the shortlist.
      return h("figure", { class: "clay-surface casting-look" },
        pictures.length ? h("img", { src: pictures[0].picture, alt: `Headshot: ${look.name}`, loading: "lazy" }) : h("div", { class: "casting-blank" }, h("span", {}, "Not drawn yet"), h("small", {}, look.brief?.size_m ? `${look.brief.size_m} m tall` : "")),
        pictures.length > 1 ? h("div", { class: "casting-more-pictures" }, pictures.slice(1).map((p) => h("a", { href: p.picture, target: "_blank", title: p.shot }, h("img", { src: p.picture, alt: `Picture ${p.n} of ${look.name}`, loading: "lazy" })))) : null,
        h("figcaption", {}, h("b", {}, look.name), h("span", {}, look.why),
          look.suits && arrival(look.suits) ? h("span", { class: "casting-suits" }, `Fits “${arrival(look.suits)}”`) : null,
          h("details", {}, h("summary", {}, "What Codex was asked to draw"), h("p", {}, look.brief?.subject)),
          pictures.length && !role.screen ? h("div", { class: "casting-chips" }, pictures.map((p) => shortlistButton(p.shot, p.candidate, shortlist, h, pictures.length > 1 ? `Shortlist picture ${p.n}` : "Put on the shortlist"))) : null));
    }),
    standIns.map((c) => h("figure", { class: "clay-surface casting-look stand-in" },
      h("img", { src: c.picture, alt: `${c.name}, standing in`, loading: "lazy" }),
      h("figcaption", {}, h("b", {}, `${c.name} (standing in)`), h("span", {}, c.why))))),
    stepBox(role.steps.find((s) => s.id === "headshots"), role, null, h));
}

// ---------- the screen test: every headshot measured, best first (scripts/casting/screen.py) ----------

const SCREEN_MEASURES = [
  ["builds", "Builds", "One figure, whole, on a plain background, front on, arms straight out: what TRELLIS builds well."],
  ["stands_apart", "Stands apart", "Its outline at the crew camera's size against everyone in the cast: how little it shares with the nearest, and how square its head is."],
  ["face", "Face", "Shrunk to the crew camera's pixels in the pixel look's colours: a dark face plate, two light eyes on it, the grille."],
  ["colours", "Colours", "How much of it is the breakdown's five colours, mustard leading, and how far its mustard is from the cast's colours."],
  ["cards", "Cards", "Nothing thin or loose (wires, antennae, springs): that's where cards come apart."],
];

function scoreBars(scores, h) {
  return h("dl", { class: "casting-bars" }, SCREEN_MEASURES.flatMap(([key, name]) => [
    h("dt", {}, name),
    h("dd", {}, h("span", { class: "casting-bar" }, h("span", { style: `width:${Math.round(100 * (scores[key] || 0))}%` })), h("small", {}, (scores[key] ?? 0).toFixed(2))),
  ]));
}

function meshBox(mesh, h) {
  if (!mesh?.turn) return mesh ? h("p", { class: "about" }, "Built as a mesh; not pictured yet (just casting-mesh-screen).") : null;
  const a = mesh.against || {};
  return h("details", { class: "casting-mesh" },
    h("summary", {}, "Its mesh, from all round"),
    h("img", { src: mesh.turn, alt: "The mesh from eight sides, and at the crew camera's size", loading: "lazy" }),
    h("p", { class: "about" }, `${a.front_is === "as drawn" ? "Faces the way it was drawn" : "Came in turned round"}; keeps ${Math.round(100 * (a.outline_kept || 0))}% of its picture's outline; ${mesh.mesh?.pieces ?? "?"} loose pieces.`));
}

function screenSection(role, h, refresh) {
  const screen = role.screen;
  const shortlist = shortlister(role, refresh);
  const steps = ["screen", "mesh"].map((id) => role.steps.find((s) => s.id === id)).filter(Boolean);
  if (!screen?.shots?.length) {
    return h("section", { class: "casting-section", id: "stage-screen" },
      h("h2", {}, "Screen test"),
      h("p", { class: "lede" }, "Once there are headshots, each one is measured here on what the breakdown asks for, for free, so the shortlist is picked on evidence."),
      h("div", { class: "casting-grid casting-steps" }, steps.map((s) => stepBox(s, role, null, h))));
  }
  const vision = screen.vision;
  return h("section", { class: "casting-section", id: "stage-screen" },
    h("h2", {}, "Screen test"),
    h("p", { class: "lede" }, `Every headshot measured on what the breakdown asks for, best first. ${screen.shots.length} pictures, measured on this Mac for free. Beside each: what the crew camera sees, and its face on the pixel look's grid.`),
    h("details", { class: "casting-legend clay-surface casting-panel" },
      h("summary", {}, "What each score means"),
      h("dl", {}, SCREEN_MEASURES.flatMap(([, name, about]) => [h("dt", {}, name), h("dd", {}, about)])),
      h("p", { class: "about" }, `Each is out of 1. The total weighs them ${Object.entries(screen.how?.weights || {}).map(([k, w]) => `${SCREEN_MEASURES.find((m) => m[0] === k)?.[1] || k} ${Math.round(100 * w)}%`).join(", ")}, and takes ${screen.how?.flag_cost ?? 0.1} off for each thing the breakdown rules out. ${vision ? `Haiku also looked at every picture once for those (${vision.made}).` : ""}`),
      h("p", { class: "about" }, h("a", { href: screen.sheet, target: "_blank" }, "All of them on one page"))),
    screen.colourway_sheet ? h("p", { class: "about" }, h("a", { href: screen.colourway_sheet, target: "_blank" }, "The colourways side by side, beside the cast in their own colours")) : null,
    h("ol", { class: "casting-screen" }, screen.shots.filter((row) => !row.colourway).map((row) =>
      h("li", { class: `clay-surface casting-shot${row.flags?.length ? " flagged" : ""}${colourwaysOf(screen, row).length ? " has-colourways" : ""}` },
        h("div", { class: "casting-shot-pictures" },
          h("img", { class: "casting-shot-picture", src: row.picture, alt: `Headshot ${row.id}`, loading: "lazy" }),
          h("div", { class: "casting-shot-small" },
            h("img", { class: "pixelated casting-shot-crew", src: row.small, alt: "As the crew camera sees it", title: "As the crew camera sees it", loading: "lazy" }),
            h("img", { class: "pixelated casting-shot-face", src: row.face, alt: "Its face on the pixel look's grid", title: "Its face on the pixel look's grid", loading: "lazy" }))),
        h("div", { class: "casting-shot-label" },
          h("span", { class: "casting-rank" }, `#${row.rank}`),
          h("b", {}, row.name), h("span", { class: "about" }, row.n > 1 ? ` picture ${row.n}` : ""),
          h("span", { class: "casting-total" }, row.scores.total.toFixed(2))),
        scoreBars(row.scores, h),
        row.flags?.length ? h("ul", { class: "casting-flags" }, row.flags.map((f) => h("li", {}, f))) : null,
        meshBox(row.mesh, h),
        shortlistButton(row.id, row.candidate, shortlist, h),
        colourwayStrip(colourwaysOf(screen, row), shortlist, h)))),
    h("div", { class: "casting-grid casting-steps" }, steps.map((s) => stepBox(s, role, null, h))));
}

// A headshot's colourways: the same picture drawn again in other colours, screened like any headshot.
const colourwaysOf = (screen, row) => screen.shots.filter((r) => r.colourway?.of === row.id);

function colourwayStrip(ways, shortlist, h) {
  if (!ways.length) return null;
  return h("div", { class: "casting-colourways" },
    h("h4", {}, "In other colours"),
    h("ul", {}, ways.map((w) => h("li", { class: `clay-well casting-colourway${w.flags?.length ? " flagged" : ""}` },
      h("img", { class: "casting-colourway-picture", src: w.picture, alt: `${w.colourway.name}`, loading: "lazy" }),
      h("img", { class: "pixelated casting-colourway-crew", src: w.small, alt: "As the crew camera sees it", loading: "lazy" }),
      h("div", { class: "casting-colourway-label" },
        h("b", {}, w.colourway.name),
        h("span", { class: "casting-swatches-row" }, w.colourway.swatches.map((hex) => h("span", { class: "chip-colour", title: hex, style: `background:${hex}` }))),
        h("span", { class: "about" }, `#${w.rank} · total ${w.scores.total.toFixed(2)} · colours ${w.scores.colours.toFixed(2)} · stands apart ${w.scores.stands_apart.toFixed(2)}`),
        w.flags?.length ? h("span", { class: "casting-flags" }, w.flags.join("; ")) : null,
        shortlistButton(w.id, w.candidate, shortlist, h))))));
}

function shortlistSection(role, h) {
  const people = role.candidates.filter((c) => c.status !== "submitted");
  return h("section", { class: "casting-section", id: "stage-shortlist" },
    h("h2", {}, "The shortlist"),
    h("p", { class: "lede" }, "Everyone worth building, side by side. Open one to watch its reel, see it beside the cast, read its scores and give it a note."),
    h("div", { class: "casting-grid" }, people.map((c) => {
      const last = c.takes[c.takes.length - 1];
      return h("a", { class: `card clay-surface casting-person${c.status === "let go" ? " gone" : ""}`, href: `#/casting/${encodeURIComponent(role.id)}/${encodeURIComponent(c.id)}` },
        c.picture ? h("img", { src: c.picture, alt: "", loading: "lazy" }) : h("div", { class: "casting-blank" }, "No picture"),
        h("div", { class: "label" },
          h("h2", {}, c.name),
          h("p", {}, `${STATUS_WORDS[c.status] || c.status}${c.stand_in ? " · standing in" : ""}`),
          h("p", {}, `${c.takes.length ? `${c.takes.length} take${c.takes.length > 1 ? "s" : ""}` : "Not built yet"}${last?.reel?.length ? ` · ${last.reel.filter((s) => s.ready).length} of ${last.reel.length} scenes taped` : ""}${c.open_notes.length ? ` · ${c.open_notes.length} open note${c.open_notes.length > 1 ? "s" : ""}` : ""}`),
          last?.scores ? h("p", {}, `Camera test: ${headline(last.scores, role.baseline)}`) : null));
    })),
    h("h3", { class: "casting-subhead", id: "stage-tapes" }, "What each step costs"),
    h("p", { class: "about" }, "Paid steps never start from this page. “See what it would cost” asks what would happen and prints the command to run in Terminal; the casting recipes in the justfile do nothing until you add go."),
    h("div", { class: "casting-grid casting-steps" }, role.steps.filter((s) => !["headshots", "screen", "mesh"].includes(s.id)).map((s) => stepBox(s, role, null, h))));
}

// One line for a card: bold ink's lines-that-are-not-there and see-through against the cast member it stands in for.
function headline(scores, baseline) {
  const mine = scores?.seams?.joe;
  if (!mine) return "not run yet";
  const theirs = baseline?.seams?.joe;
  const total = (s) => s.dark + s.open;
  return theirs ? `${total(mine).toFixed(0)} stray pixels a thousand in bold ink (${baseline.who || "the cast member"}: ${total(theirs).toFixed(0)})` : `${total(mine).toFixed(0)} stray pixels a thousand in bold ink`;
}

export function rolePage({ role, h, refresh }) {
  return h("article", { class: "object casting" },
    h("a", { class: "back", href: "#/casting" }, "← Casting"),
    h("p", { class: "kicker" }, "Casting"),
    h("h1", {}, role.title),
    h("p", { class: "lede" }, role.breakdown?.logline || ""),
    board(role, h),
    breakdown(role, h),
    headshots(role, h, refresh),
    screenSection(role, h, refresh),
    shortlistSection(role, h));
}

// ---------- one candidate ----------

// The reel on the cards page (impostor.js): the run's own cards, with the reel's scenes as what it plays. A scene
// that is a stretch of a longer clip is cut out of it once the clip is on (AnimationUtils.subclip).
function reelStage({ role, candidate, take, runs, sets, h, loader, mount }) {
  const run = runs.find((r) => r.id === take.run);
  const sides = take.reel.filter((s) => s.ready);
  const missing = take.reel.filter((s) => !s.ready);
  const holder = h("div", { class: "casting-reel" });
  const status = h("p", { class: "about" });
  if (!run?.cards?.length || !sides.length) {
    holder.append(h("div", { class: "clay-surface casting-panel" },
      h("p", {}, !run?.cards?.length ? "No cards baked for this take yet, so the reel cannot be played as cards." : "Nothing taped yet."),
      stepBox(role.steps.find((s) => s.id === "tape"), role, candidate, h)));
    return holder;
  }
  const motions = sides.map((s) => ({ id: s.id, name: s.name, glb: s.glb, side: s }));
  const reelRun = { ...run, cards: run.cards.map((c) => ({ ...c, motions })) };
  let current = motions[0];
  const cut = (viewer, side) => {
    if (side.from_s === null || side.from_s === undefined || !viewer.clip) return;
    const whole = viewer.clip;
    const from = Math.max(0, Math.round(side.from_s * FPS));
    const to = Math.min(Math.round(whole.duration * FPS), Math.round(side.to_s * FPS));
    if (to <= from + 1) return;
    const part = THREE.AnimationUtils.subclip(whole, side.id, from, to, FPS);
    viewer.mixer.stopAllAction();
    viewer.mixer.clipAction(part).play();
    viewer.clip = part;
  };
  const why = h("p", { class: "casting-why" }, motions[0].side.why);
  let viewer = null;
  const chips = motions.map((m, i) => h("button", { class: "chip clay-chip", type: "button", "aria-pressed": String(i === 0), onclick: async () => {
    chips.forEach((c, k) => c.setAttribute("aria-pressed", String(k === i)));
    current = m;
    why.textContent = m.side.why;
    if (!viewer) return;
    await viewer.play(m);
    if (current === m) cut(viewer, m.side);
  } }, m.name));
  holder.append(
    h("div", { class: "versions casting-sides", role: "group", "aria-label": "Scene" }, h("span", { class: "row-label" }, "Scene"), chips),
    why);
  import("./impostor.js").then(({ cardsPage }) => {
    const page = cardsPage({ run: reelRun, sets, h, loader });
    page.classList.add("casting-cards");
    holder.append(page, status);
    mount(page);
    queueMicrotask(() => queueMicrotask(async () => {
      viewer = page.viewer;
      await viewer?.ready;
      if (viewer) cut(viewer, current.side);
    }));
  });
  if (missing.length) status.textContent = `Not taped yet: ${missing.map((s) => s.name.toLowerCase()).join(", ")} (${missing[0].made_by}).`;
  return holder;
}

function watchStage({ take, which, runs, sets, h, loader, mount }) {
  const holder = h("div", { class: "casting-watch" });
  import("./watch.js").then(({ watchPage }) => {
    const page = watchPage({ take: which, sets, runs, h, loader });
    page.classList.add("casting-cards");
    holder.append(page);
    mount(page);
  });
  return holder;
}

// The height line-up: everyone at their height, side by side, the candidate in the middle of the cast.
// Each is their own full-length picture (the T-pose every character is drawn in), stood on one floor and scaled
// to their height against lines every half metre, as a casting office's height chart.
function lineUp(role, candidate, take, h) {
  const cast = role.chemistry.line_up.map((p) => ({ name: p.short || p.name, height: p.height_m, picture: p.picture, me: false }));
  const me = { name: candidate.name.replace(/^The /, ""), height: take.height_m, picture: take.picture || candidate.picture, me: true };
  const people = [cast[0], me, ...cast.slice(1)].filter(Boolean);
  const top = Math.max(2.5, Math.ceil(Math.max(...people.map((p) => p.height || 0)) * 2) / 2 + 0.25);
  const rules = [0.5, 1, 1.5, 2, 2.5].filter((m) => m < top).map((m) => h("div", { class: "casting-rule", style: `bottom:${(100 * m) / top}%` }, h("span", {}, `${m} m`)));
  return h("div", { class: "casting-lineup-wrap", role: "img", "aria-label": people.map((p) => `${p.name} ${metres(p.height)}`).join(", ") },
    h("div", { class: "clay-well casting-lineup" },
      rules,
      people.map((p) => h("div", { class: `casting-tall${p.me ? " me" : ""}` },
        // A character picture leaves about a twentieth empty above the head and below the feet.
        h("div", { class: "casting-figure", style: `height:${(100 * (p.height || 0) * 1.1) / top}%` }, p.picture ? cutOut(p.picture, h) : null)))),
    h("div", { class: "casting-names" }, people.map((p) => h("div", { class: p.me ? "me" : "" }, h("b", {}, p.name), h("span", {}, metres(p.height))))));
}

// A character picture with its plain background taken out (the colour of its corners), so the figures can stand
// close and overlap on the chart as people in a line-up do.
function cutOut(url, h) {
  const canvas = h("canvas", { class: "casting-cutout" });
  const img = new Image();
  img.onload = () => {
    const size = 360;
    canvas.width = canvas.height = size;
    const g = canvas.getContext("2d", { willReadFrequently: true });
    g.drawImage(img, 0, 0, size, size);
    const picture = g.getImageData(0, 0, size, size);
    const px = picture.data;
    const corner = [px[0], px[1], px[2]];
    for (let i = 0; i < px.length; i += 4) {
      const off = Math.abs(px[i] - corner[0]) + Math.abs(px[i + 1] - corner[1]) + Math.abs(px[i + 2] - corner[2]);
      px[i + 3] = off < 18 ? 0 : off < 36 ? Math.round((255 * (off - 18)) / 18) : px[i + 3];
    }
    g.putImageData(picture, 0, 0);
  };
  img.src = url;
  return canvas;
}

// Colour harmony: the five colours each picture is most made of, worked out here from the picture itself (the
// background, which is the picture's corners, left out), beside the colours the breakdown asks for.
function palette(url, h) {
  const row = h("div", { class: "casting-palette" });
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.onload = () => {
    const size = 64;
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = size;
    const g = canvas.getContext("2d", { willReadFrequently: true });
    g.drawImage(img, 0, 0, size, size);
    const px = g.getImageData(0, 0, size, size).data;
    const back = [0, size - 1, size * (size - 1), size * size - 1].map((i) => [px[4 * i], px[4 * i + 1], px[4 * i + 2]]);
    const near = (a, b, d) => Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]) < d;
    const buckets = new Map();
    for (let i = 0; i < size * size; i++) {
      const c = [px[4 * i], px[4 * i + 1], px[4 * i + 2]];
      if (back.some((b) => near(c, b, 40))) continue;
      const key = (c[0] >> 5) * 64 + (c[1] >> 5) * 8 + (c[2] >> 5);
      const b = buckets.get(key) || { n: 0, r: 0, g: 0, b: 0 };
      b.n++; b.r += c[0]; b.g += c[1]; b.b += c[2];
      buckets.set(key, b);
    }
    const picked = [];
    for (const b of [...buckets.values()].sort((x, y) => y.n - x.n)) {
      const c = [b.r / b.n, b.g / b.n, b.b / b.n].map(Math.round);
      if (!picked.some((p) => near(p, c, 60))) picked.push(c);
      if (picked.length === 5) break;
    }
    row.replaceChildren(...picked.map((c) => h("span", { class: "chip-colour", title: `rgb(${c.join(", ")})`, style: `background:rgb(${c.join(",")})` })));
  };
  img.src = url;
  return row;
}

function harmony(role, candidate, take, h) {
  const wanted = (role.breakdown?.palette || []).map((p) => h("span", { class: "chip-colour", title: p.name, style: `background:${p.hex}` }));
  const rows = [
    ...role.chemistry.line_up.map((p) => [p.short || p.name, palette(p.picture, h)]),
    [`${candidate.name} (take ${take.n})`, take.picture ? palette(take.picture, h) : h("span", {}, "—")],
    ["What the breakdown asks for", h("div", { class: "casting-palette" }, wanted)],
  ];
  return h("div", { class: "clay-surface casting-panel casting-harmony" },
    h("h3", {}, "Colours beside the cast"),
    rows.map(([name, swatches]) => h("div", { class: "casting-harmony-row" }, h("span", {}, name), swatches)),
    h("p", { class: "about" }, "Each row is the five colours that picture is most made of. A new face should share none of the cast's main colour and sit well beside all of them."));
}

function scoreTable(take, role, h) {
  const s = take.scores;
  const base = role.baseline;
  const who = base?.who || "the cast member";
  if (!s) {
    return h("div", { class: "clay-surface casting-panel" },
      h("p", {}, "The camera test has not been run on this take."),
      stepBox(role.steps.find((x) => x.id === "judge"), role, { id: take.candidate }, h));
  }
  const looks = SCORE_LOOKS.filter((l) => s.seams?.[l] || s.joints?.[l]);
  const vs = (mine, theirs, digits, lower) => {
    if (mine === undefined || mine === null) return h("td", {}, "—");
    const better = theirs === undefined || theirs === null ? null : lower ? mine <= theirs : mine >= theirs;
    return h("td", { class: better === null ? "" : better ? "better" : "worse" }, Number(mine).toFixed(digits),
      theirs === undefined || theirs === null ? null : h("small", {}, ` ${Number(theirs).toFixed(digits)}`));
  };
  const rows = looks.map((look) => {
    const seam = s.seams?.[look] || {}, bseam = base?.seams?.[look] || {};
    const joint = s.joints?.[look]?.all || {}, bjoint = base?.joints?.[look]?.all || {};
    const knee = s.joints?.[look]?.knee || {}, bknee = base?.joints?.[look]?.knee || {};
    return h("tr", {}, h("th", {}, (s.looks || {})[look] || look),
      vs(seam.dark, bseam.dark, 1, true), vs(seam.open, bseam.open, 1, true),
      vs(joint.likeness, bjoint.likeness, 2, false), vs(knee.likeness, bknee.likeness, 2, false), vs(joint.blots, bjoint.blots, 3, true));
  });
  return h("div", { class: "clay-surface casting-panel casting-scores" },
    h("div", { class: "casting-table" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Look"), h("th", {}, "Stray lines"), h("th", {}, "See-through"),
        h("th", {}, "Joints"), h("th", {}, "Knees"), h("th", {}, "Blots"))),
      h("tbody", {}, rows))),
    h("p", { class: "about" }, `In the crew's dance, in ${who}'s place, through the crew camera and from close by. Stray lines are ink the real model hasn't got and see-through is body the cards leave open, both in pixels a thousand of the body (fewer is better). Joints and knees say how well a bent joint's light and dark follows the real model's (1 is the same); blots are the share of a joint drawn too dark. The small number is ${who}, judged the same way in the same place: green is better than ${who}, red is worse.`),
    s.why ? h("p", { class: "casting-warning" }, s.why) : null,
    h("p", { class: "about" }, s.face_recipe ? "" : "The face is not scored yet: that needs a face recipe for it in scripts/impostor/faces/ (where its eyes, brows and mouth are), written once it is built."),
    h("p", { class: "about" }, `Judged ${s.made}.`));
}

function notesBox(role, candidate, take, h, refresh) {
  const text = h("textarea", { class: "casting-note-text", rows: "3", maxlength: "1000", placeholder: "Try it bigger. The knees fold in the squat. Warmer eyes." });
  let about = "look";
  const hint = h("p", { class: "about" }, ABOUT_HINTS.look);
  const aboutChips = Object.entries(ABOUT_WORDS).map(([key, word], i) => h("button", { class: "chip clay-chip", type: "button", "aria-pressed": String(i === 0), onclick: () => {
    about = key;
    aboutChips.forEach((c, k) => c.setAttribute("aria-pressed", String(k === i)));
    hint.textContent = ABOUT_HINTS[key];
  } }, word));
  const said = h("p", { class: "about", "aria-live": "polite" });
  const give = h("button", { class: "clay-button", type: "button", onclick: async () => {
    give.disabled = true;
    try {
      await post(`api/casting/${encodeURIComponent(role.id)}/${encodeURIComponent(candidate.id)}/note`, { text: text.value, about, take: take.n });
      refresh();
    } catch (err) {
      said.textContent = String(err.message || err);
      give.disabled = false;
    }
  } }, "Give a note");
  const notes = candidate.notes;
  return h("div", { class: "clay-surface casting-panel casting-notes", id: "stage-callbacks" },
    h("h3", {}, "Notes"),
    notes.length ? h("ul", { class: "casting-note-list" }, notes.map((n) => h("li", { class: n.answered_by ? "answered" : "open" },
      h("span", { class: "casting-note-meta" }, `${ABOUT_WORDS[n.about] || n.about} · take ${n.take} · ${n.at}${n.by ? ` · from ${n.by}` : ""}`),
      h("span", {}, n.text),
      h("span", { class: "casting-note-meta" }, n.answered_by ? `Answered by take ${n.answered_by}` : "Open: the next take answers it")))) : h("p", { class: "about" }, "No notes yet."),
    h("label", { class: "casting-label" }, `A note on take ${take.n}`, text),
    h("div", { class: "versions", role: "group", "aria-label": "What the note is about" }, h("span", { class: "row-label" }, "About"), aboutChips),
    hint, give, said,
    stepBox(role.steps.find((s) => s.id === "revise"), role, candidate, h));
}

function statusRow(role, candidate, h, refresh) {
  const set = async (status, button) => {
    if (status === "cast" && !confirm(`Cast ${candidate.name} as ${role.title.toLowerCase()}? Nothing is written to canon; that stays yours to do.`)) return;
    button.disabled = true;
    try { await post(`api/casting/${encodeURIComponent(role.id)}/${encodeURIComponent(candidate.id)}/status`, { status }); refresh(); }
    catch (err) { button.disabled = false; button.textContent = String(err.message || err); }
  };
  const button = (status, label, extra = {}) => h("button", { class: "clay-button clay-button--soft", type: "button", "aria-pressed": String(candidate.status === status), onclick: (e) => set(status, e.target), ...extra }, label);
  return h("div", { class: "casting-status" },
    h("span", { class: "casting-status-now" }, STATUS_WORDS[candidate.status] || candidate.status),
    candidate.status !== "shortlisted" ? button("shortlisted", "Put back on the shortlist") : null,
    candidate.status !== "let go" ? button("let go", "Let go") : null,
    candidate.status !== "cast" ? button("cast", "Cast in the part", { disabled: candidate.stand_in || !candidate.takes.length, title: candidate.stand_in ? "A stand-in is already in the cast" : "" }) : null);
}

function history(role, candidate, take, h) {
  if (candidate.takes.length < 2) return null;
  return h("div", { class: "casting-history" },
    h("h3", {}, "Every take"),
    h("div", { class: "casting-grid" }, candidate.takes.map((t) => h("a", { class: `card clay-surface casting-take${t.n === take.n ? " here" : ""}`, href: `#/casting/${encodeURIComponent(role.id)}/${encodeURIComponent(candidate.id)}/${t.n}` },
      t.picture ? h("img", { src: t.picture, alt: "", loading: "lazy" }) : null,
      h("div", { class: "label" }, h("h2", {}, `Take ${t.n}`), h("p", {}, `${t.made} · ${t.how}`), t.scores ? h("p", {}, headline(t.scores, role.baseline)) : null)))));
}

export function candidatePage({ role, candidate, wantedTake, runs, sets, h, loader, refresh }) {
  const take = candidate.takes.find((t) => String(t.n) === String(wantedTake)) || candidate.takes[candidate.takes.length - 1];
  let shown = null;
  const dispose = () => { shown?.dispose?.(); shown = null; };
  const mount = (page) => { shown = page; };
  const page = h("article", { class: "object casting casting-candidate" },
    h("a", { class: "back", href: `#/casting/${encodeURIComponent(role.id)}` }, `← ${role.title}`),
    h("p", { class: "kicker" }, `Trying out for ${role.title.toLowerCase()}`),
    h("h1", {}, candidate.name),
    candidate.stand_in ? h("p", { class: "lede" }, candidate.why) : h("p", { class: "lede" }, candidate.why || ""),
    statusRow(role, candidate, h, refresh));
  if (!take) {
    page.append(h("div", { class: "clay-surface casting-panel" },
      candidate.picture ? h("img", { class: "casting-headshot", src: candidate.picture, alt: "" }) : null,
      h("p", {}, "Not built yet. The next step makes this headshot into a character with a skeleton, a walk and a run."),
      stepBox(role.steps.find((s) => s.id === "take"), role, candidate, h)));
    page.dispose = dispose;
    return page;
  }
  take.candidate = candidate.id;
  const takeChips = candidate.takes.length > 1 ? h("div", { class: "versions", role: "group", "aria-label": "Take" }, h("span", { class: "row-label" }, "Take"),
    candidate.takes.map((t) => h("a", { class: "chip clay-chip", href: `#/casting/${encodeURIComponent(role.id)}/${encodeURIComponent(candidate.id)}/${t.n}`, "aria-pressed": String(t.n === take.n) }, `Take ${t.n}`))) : null;
  // One stage at a time (a phone holds one picture well): the reel, the crew dance, or the bout.
  const stageHolder = h("div", { class: "casting-stage-holder" });
  const stages = [
    ["reel", "The reel", () => reelStage({ role, candidate, take, runs, sets, h, loader, mount })],
    take.chemistry ? ["crew", "The crew dance", () => watchStage({ take, which: take.chemistry, runs, sets, h, loader, mount })] : null,
    take.fight ? ["bout", "The sparring bout", () => watchStage({ take, which: take.fight, runs, sets, h, loader, mount })] : null,
  ].filter(Boolean);
  const stageChips = stages.map(([id, name, make], i) => h("button", { class: "chip clay-chip", type: "button", "aria-pressed": String(i === 0), onclick: () => {
    stageChips.forEach((c, k) => c.setAttribute("aria-pressed", String(k === i)));
    dispose();
    stageHolder.replaceChildren(make());
  } }, name));
  stageHolder.append(stages[0][2]());
  page.append(
    takeChips,
    h("p", { class: "about" }, `Take ${take.n}: ${take.how} ${take.run_name ? `Built as “${take.run_name}”.` : ""}`),
    h("section", { class: "casting-section", id: "stage-tapes" },
      h("h2", {}, "On stage"),
      h("div", { class: "versions casting-stage-pick", role: "group", "aria-label": "What to watch" }, h("span", { class: "row-label" }, "Watch"), stageChips),
      stageHolder),
    h("section", { class: "casting-section" },
      h("h2", {}, "Beside the cast"),
      h("div", { class: "casting-two" },
        h("div", { class: "clay-surface casting-panel" }, h("h3", {}, "Heights"), lineUp(role, candidate, take, h)),
        harmony(role, candidate, take, h))),
    h("section", { class: "casting-section" },
      h("h2", {}, "Camera test"),
      scoreTable(take, role, h)),
    h("section", { class: "casting-section" },
      h("h2", {}, "Callbacks"),
      notesBox(role, candidate, take, h, refresh),
      history(role, candidate, take, h)),
    h("section", { class: "casting-section" },
      h("h2", {}, "Steps for this one"),
      h("div", { class: "casting-grid casting-steps" }, ["tape", "judge"].map((id) => stepBox(role.steps.find((s) => s.id === id), role, candidate, h)))));
  page.dispose = dispose;
  return page;
}
