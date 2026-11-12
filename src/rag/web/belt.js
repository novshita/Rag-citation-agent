// "Page to proof": real pages from the indexed documents drift past a scanner. Each page dissolves
// into particles at the line, and the exact quote the system cites for it is printed on the other
// side. The pages are DOM, the quote is text, the dissolve is a 2D canvas drawn every frame. No video.
// Everything shown comes from showcase.json, whose quotes are checked against the real files by a test.

import {
  cardX, clamp, counterTarget, crossingIndex, cutOf, dissolveProbability, hash, ofWordsLabel, splitAround, targetSpeed,
} from "./belt-math.js";

const TOP = 64;            // px from the top of the belt to the top of the cards (room for the counter)
const BOTTOM = 36;
const RADIUS = 14;         // card corner radius in px
const CELL = 3;            // the dissolve grid, in px

// Deep to pale. Light theme: the line edge is the deepest colour. Dark theme: the line edge is the palest.
const PALETTE = {
  light: { colors: ["#3730a3", "#4338ca", "#4f46e5", "#6366f1", "#818cf8", "#a5b4fc", "#c7d2fe"], rgb: "79,70,229", haze: 0.3 },
  dark: { colors: ["#6366f1", "#818cf8", "#a5b4fc", "#c7d2fe", "#e0e7ff", "#eef2ff", "#ffffff"], rgb: "129,140,248", haze: 0.38 },
};

function el(tag, className, ...children) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  for (const child of children) if (child != null) node.append(child);
  return node;
}

/** The page as a visitor would see it: a mini document with the cited sentence already highlighted. */
function buildPage(card) {
  const body = el("div", "pg-body",
    el("p", "pg-kicker", "FastAPI documentation"),
    el("div", "pg-title", card.title));
  for (const text of card.paragraphs) {
    const parts = splitAround(text, card.quote);
    body.append(parts
      ? el("p", "pg-p", parts.before, el("mark", null, parts.match), parts.after)
      : el("p", "pg-p", text));
  }
  if (card.code) body.append(el("pre", "pg-code", card.code));
  body.append(el("div", "pg-skel", el("i"), el("i"), el("i")));
  return el("div", "pg",
    el("div", "pg-bar", el("span", "pg-dots", el("i"), el("i"), el("i")), el("span", "pg-url", card.doc)),
    body,
    el("p", "pg-foot", `… ${card.page_words.toLocaleString("en-US")} words on this page`));
}

/** What the page turns into: the question, the exact quote, and the result of the check. */
function buildProof(card) {
  return el("div", "pf",
    el("p", "pf-label", "Question"),
    el("p", "pf-q", card.question),
    el("p", "pf-label", `Cited quote · ${card.doc}`),
    el("p", "pf-quote", "“", el("mark", null, card.quote), "”"),
    el("p", "pf-ok", "✓ Verified in code. Found in the source."));
}

/**
 * Build the demo. Returns { element, destroy }. The animation runs only while the element is on
 * screen and the tab is visible, and `destroy()` stops it for good.
 */
export function createBelt(cards) {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const dark = window.matchMedia("(prefers-color-scheme: dark)");

  const pageEls = cards.map((c) => el("div", "card-slot", buildPage(c)));
  const proofEls = cards.map((c) => el("div", "code-slot", buildProof(c)));
  const canvas = el("canvas", "fx");
  const num = el("span", "counter-num", "0");
  const of = el("span", "counter-of", ofWordsLabel(cards[0].page_words));
  const belt = el("div", "belt",
    el("div", "codes", ...proofEls),
    el("div", "cards", ...pageEls),
    canvas,
    el("div", "scan", el("i"), el("b")),
    el("div", "counter", el("span", "counter-label", "Cited from this page"), el("div", "counter-pill", num, of)));
  belt.setAttribute("aria-hidden", "true");

  const pause = el("button", "belt-pause", "Pause");
  pause.type = "button";
  const element = el("section", "belt-demo",
    el("div", "belt-head",
      el("div", null,
        el("p", "belt-eyebrow", "How it works · live example"),
        el("h2", "belt-title", "A page goes in. The exact quote comes out.")),
      pause),
    el("p", "sr-only",
      "Illustration: pages from the FastAPI documentation scroll past a scanner. Each page turns into the exact quote the system cites from it, marked as verified in code."),
    belt,
    el("p", "belt-note", "Example pages from the FastAPI docs. Hover to slow it down, drag to scrub."));
  element.setAttribute("aria-label", "How a page becomes a verified quote");

  const ctx = canvas.getContext("2d");
  const count = cards.length;

  let width = 0, cw = 0, ch = 0, span = 0, lineX = 0, dpr = 1;
  let offset = 0, velocity = 0, hover = 0, hovering = false, dragging = false;
  let paused = reduced.matches, clock = 0, shown = 0, lastCrossing = -1;
  let sparks = [], running = false, visible = false, frameId = 0, last = 0, placed = false;

  function setPaused(value) {
    paused = value;
    pause.textContent = paused ? "Play" : "Pause";
    pause.setAttribute("aria-pressed", String(paused));
    pause.setAttribute("aria-label", paused ? "Play the animation" : "Pause the animation");
  }
  setPaused(paused);
  pause.addEventListener("click", () => setPaused(!paused));

  function measure() {
    const w = belt.getBoundingClientRect().width;
    if (!w) return false;
    width = w;
    const narrow = w < 560;
    cw = Math.round(clamp(w * (narrow ? 0.84 : 0.46), 240, 420));
    ch = Math.round(cw * 0.66);
    span = cw + Math.round(cw * (narrow ? 0.12 : 0.16));
    lineX = w / 2;
    belt.style.setProperty("--cw", `${cw}px`);
    belt.style.setProperty("--ch", `${ch}px`);
    belt.style.height = `${ch + TOP + BOTTOM}px`;
    dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round((ch + TOP + BOTTOM) * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (!placed) { offset = lineX - 0.4 * cw; placed = true; }   // first page starts part-way through the scanner
    return true;
  }

  function theme() {
    const forced = document.documentElement.dataset.theme;
    const isDark = forced === "dark" || (forced !== "light" && dark.matches);
    return { ...(isDark ? PALETTE.dark : PALETTE.light), isDark };
  }

  function update(dt) {
    hover += ((hovering ? 1 : 0) - hover) * Math.min(1, dt * 4);
    if (!dragging) {
      const rate = paused ? 9 : 2.2;                       // Pause stops it quickly; hover and drift ease gently
      velocity += (targetSpeed(width, hover, paused) - velocity) * (1 - Math.exp(-rate * dt));
      offset += velocity * dt;
    }
    if (!paused) clock += dt;
  }

  function place() {
    const cuts = [];
    for (let i = 0; i < count; i++) {
      const x = cardX(offset, i, span, count);
      const cut = cutOf(x, lineX, cw);
      cuts.push(cut);
      const move = `translate3d(${x}px,0,0)`;
      const page = pageEls[i].style;
      page.transform = move;
      page.visibility = cut >= cw ? "hidden" : "visible";
      if (cut > 0) {
        page.clipPath = `inset(0 0 0 ${cut}px round 0 ${RADIUS}px ${RADIUS}px 0)`;
        page.webkitMaskImage = page.maskImage = `linear-gradient(90deg, transparent ${cut}px, #000 ${cut + 26}px)`;
      } else {
        page.clipPath = "none";
        page.webkitMaskImage = page.maskImage = "none";
      }
      const proof = proofEls[i].style;
      proof.transform = move;
      proof.visibility = cut > 0 ? "visible" : "hidden";
      proof.clipPath = `inset(0 ${cw - cut}px 0 0)`;
    }
    return cuts;
  }

  function counter(cuts, dt) {
    const i = crossingIndex(cuts, cw);
    if (i === -1) return;
    const target = counterTarget(cards[i].quote_words, cuts[i] / cw);
    if (i !== lastCrossing) {
      lastCrossing = i;
      shown = target;
      of.textContent = ofWordsLabel(cards[i].page_words);
    } else {
      shown += (target - shown) * Math.min(1, dt * 14);
    }
    num.textContent = String(Math.round(shown));
  }

  function draw(cuts, dt) {
    ctx.clearRect(0, 0, width, ch + TOP + BOTTOM);
    const { colors, rgb, haze, isDark } = theme();
    const reach = 0.3 * cw;
    const rows = Math.ceil(ch / CELL);
    const still = paused;                                  // paused: no twinkle, no jitter, no sparks
    const tick = still ? 0 : Math.floor(clock * 9);
    let any = false;

    for (let i = 0; i < count; i++) {
      const cut = cuts[i];
      const x = cardX(offset, i, span, count);
      if (cut <= 0 || x + cw <= lineX) continue;           // the card's right edge must still be past the line
      any = true;

      const glow = ctx.createLinearGradient(lineX, 0, lineX + 150, 0);
      glow.addColorStop(0, `rgba(${rgb},${haze})`);
      glow.addColorStop(1, `rgba(${rgb},0)`);
      ctx.fillStyle = glow;
      ctx.fillRect(lineX, TOP, Math.min(150, x + cw - lineX), ch);

      for (let gx = Math.floor(cut / CELL); gx <= Math.floor((cut + reach) / CELL) && gx * CELL < cw; gx++) {
        const d = gx * CELL - cut;                        // distance past the line, along the card
        if (d < 0) continue;
        const p = dissolveProbability(d, reach);
        for (let row = -5; row < rows + 5; row++) {
          const inside = row >= 0 && row < rows;
          const edge = inside ? 0 : Math.min(5, row < 0 ? -row : row - rows + 1);
          const chance = inside ? p * 0.92 : p * 0.16 * (1 - edge / 5);
          if (hash(gx, row, i) >= chance) continue;
          if (!still && hash(gx, row, tick + 97) < 0.22) continue;
          const h2 = hash(row, gx, i + 31);
          const nearLine = d < 10;
          const pick = nearLine ? (isDark ? 4 + Math.floor(h2 * 3) : Math.floor(h2 * 2)) : Math.floor(h2 * h2 * 7);
          const size = 1.1 + h2 * 1.7;
          const jx = still ? 0 : (hash(gx, row, tick + 11) - 0.5) * 1.6;
          const jy = still ? 0 : (hash(row, gx, tick + 13) - 0.5) * 1.6;
          ctx.fillStyle = colors[pick];
          ctx.fillRect(x + gx * CELL + jx, TOP + row * CELL + jy, size, size);
        }
      }
    }

    if (any && !still) {
      for (let k = 0; k < 3; k++) {
        if (Math.random() > 0.7) continue;
        sparks.push({
          x: lineX + Math.random() * 30, y: TOP - 10 + Math.random() * (ch + 20),
          vx: -30 + Math.random() * 70 + velocity * 0.6, vy: (Math.random() - 0.5) * 50,
          size: 0.8 + Math.random() * 1.8, life: 0.3 + Math.random() * 0.8, color: colors[Math.floor(Math.random() * colors.length)],
        });
      }
      if (sparks.length > 220) sparks = sparks.slice(-220);
    }
    sparks = still ? [] : sparks.filter((s) => (s.life -= dt) > 0);
    for (const s of sparks) {
      s.x += s.vx * dt;
      s.y += s.vy * dt;
      ctx.globalAlpha = Math.min(1, s.life * 2.2);
      ctx.fillStyle = s.color;
      ctx.fillRect(s.x, s.y, s.size, s.size);
    }
    ctx.globalAlpha = 1;
  }

  function frame(now) {
    frameId = 0;
    if (!running) return;
    if (!width && !measure()) { frameId = requestAnimationFrame(frame); return; }   // not laid out yet
    const dt = Math.min(0.05, Math.max(0, (now - last) / 1000));
    last = now;
    update(dt);
    const cuts = place();
    counter(cuts, dt);
    draw(cuts, dt);
    frameId = requestAnimationFrame(frame);
  }

  function sync() {
    const should = visible && !document.hidden;
    if (should === running) return;
    running = should;
    if (running && !frameId) { last = performance.now(); frameId = requestAnimationFrame(frame); }
  }

  const resizer = new ResizeObserver(() => { measure(); });
  resizer.observe(belt);
  const watcher = new IntersectionObserver((entries) => { visible = entries.some((e) => e.isIntersecting); sync(); });
  watcher.observe(element);
  document.addEventListener("visibilitychange", sync);

  // Hover slows the belt, dragging scrubs it with inertia, a sideways wheel nudges it.
  let lastX = 0, lastT = 0;
  belt.addEventListener("pointerenter", (e) => { if (e.pointerType === "mouse") hovering = true; });
  belt.addEventListener("pointerleave", () => { hovering = false; });
  belt.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    dragging = true;
    lastX = e.clientX;
    lastT = e.timeStamp;
    belt.setPointerCapture(e.pointerId);
    belt.classList.add("grabbing");
  });
  belt.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const dx = e.clientX - lastX;
    offset += dx;
    velocity = (dx / Math.max(8, e.timeStamp - lastT)) * 1000 * 0.8 + velocity * 0.2;
    lastX = e.clientX;
    lastT = e.timeStamp;
  });
  const release = () => { dragging = false; belt.classList.remove("grabbing"); };
  belt.addEventListener("pointerup", release);
  belt.addEventListener("pointercancel", release);
  belt.addEventListener("wheel", (e) => {
    if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
    velocity += -e.deltaX * 6;
    e.preventDefault();
  }, { passive: false });

  function destroy() {
    running = false;
    visible = false;
    if (frameId) cancelAnimationFrame(frameId);
    frameId = 0;
    resizer.disconnect();
    watcher.disconnect();
    document.removeEventListener("visibilitychange", sync);
  }

  return { element, destroy };
}
