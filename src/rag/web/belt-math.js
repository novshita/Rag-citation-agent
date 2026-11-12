// Pure maths for the "page to proof" belt: no DOM, no canvas, so it can be unit-tested with Node.

/** Modulo that stays positive for negative numbers. */
export const mod = (n, m) => ((n % m) + m) % m;

export const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));

/**
 * Left edge of card `i` on a belt that wraps. Cards live in [-span, span * (count - 1)),
 * so one that leaves on the left reappears, unseen, on the far right.
 */
export function cardX(offset, i, span, count) {
  return mod(offset + i * span + span, span * count) - span;
}

/** How many pixels of a card (left edge `x`, width `cw`) are already past the scanner at `lineX`. */
export function cutOf(x, lineX, cw) {
  return clamp(lineX - x, 0, cw);
}

/** Deterministic 32-bit hash of three integers, as a number in [0, 1). */
export function hash(a, b, c) {
  let h = (Math.imul(a | 0, 374761393) + Math.imul(b | 0, 668265263) + Math.imul(c | 0, 2147483647)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

/** Chance that a pixel `d` px past the line is lit: almost solid at the line, nothing at `reach`. */
export function dissolveProbability(d, reach) {
  if (d <= 0) return 1;
  if (d >= reach) return 0;
  return Math.pow(1 - d / reach, 1.7);
}

/** How many of the quote's words the counter shows while a card is `progress` (0..1) of the way through. */
export function counterTarget(quoteWords, progress) {
  return Math.round(quoteWords * clamp(progress, 0, 1));
}

/** "of 1,204 words" */
export function ofWordsLabel(pageWords) {
  return `of ${pageWords.toLocaleString("en-US")} words`;
}

/** Index of the card that is currently crossing the scanner, or -1 when none is. */
export function crossingIndex(cuts, cw) {
  return cuts.findIndex((cut) => cut > 0 && cut < cw);
}

/** Speed (px/s): drift left, slowed to 35% while hovered, stopped while paused. */
export function targetSpeed(width, hover, paused) {
  if (paused) return 0;
  return -0.075 * width * (1 - 0.65 * clamp(hover, 0, 1));
}

/** Split a paragraph around the quote so the quote can be highlighted. Returns null if it isn't in the text. */
export function splitAround(text, quote) {
  const at = text.indexOf(quote);
  if (at === -1) return null;
  return { before: text.slice(0, at), match: quote, after: text.slice(at + quote.length) };
}
