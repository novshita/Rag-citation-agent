import test from "node:test";
import assert from "node:assert/strict";
import {
  cardX, counterTarget, crossingIndex, cutOf, dissolveProbability, hash, mod, ofWordsLabel, splitAround, targetSpeed,
} from "../../src/rag/web/belt-math.js";

test("mod stays positive for negative numbers", () => {
  assert.equal(mod(-1, 5), 4);
  assert.equal(mod(11, 5), 1);
});

test("cards wrap from the far left back to the far right", () => {
  const span = 100, count = 5;
  const xs = [-250, -150, 0, 125, 499].map((offset) => cardX(offset, 0, span, count));
  for (const x of xs) assert.ok(x >= -span && x < span * (count - 1), `x=${x} is outside the belt range`);
  // moving the belt left by one full span moves every card left by one span, wrapping the first
  assert.equal(cardX(0, 1, span, count), 100);
  assert.equal(cardX(-100, 1, span, count), 0);
  assert.equal(cardX(-100, 0, span, count), -100);   // the first card sits one span to the left, still on the belt
});

test("cut is how far a card is past the scanner, limited to the card", () => {
  assert.equal(cutOf(500, 400, 300), 0);      // card still to the right of the line
  assert.equal(cutOf(300, 400, 300), 100);    // 100px past the line
  assert.equal(cutOf(0, 400, 300), 300);      // fully past
});

test("the crossing card is the one partly past the line", () => {
  assert.equal(crossingIndex([300, 120, 0], 300), 1);
  assert.equal(crossingIndex([300, 300, 0], 300), -1);
  assert.equal(crossingIndex([0, 0], 300), -1);
});

test("hash is deterministic and in [0, 1)", () => {
  assert.equal(hash(3, 4, 5), hash(3, 4, 5));
  assert.notEqual(hash(3, 4, 5), hash(4, 3, 5));
  for (let i = -50; i < 50; i++) {
    const v = hash(i, i * 7, 31);
    assert.ok(v >= 0 && v < 1, `hash out of range: ${v}`);
  }
});

test("dissolve is solid at the line and gone at the reach", () => {
  assert.equal(dissolveProbability(0, 100), 1);
  assert.equal(dissolveProbability(100, 100), 0);
  assert.ok(dissolveProbability(30, 100) > dissolveProbability(60, 100));
  assert.equal(dissolveProbability(-5, 100), 1);
});

test("counter counts the quote's words up as the card crosses", () => {
  assert.equal(counterTarget(20, 0), 0);
  assert.equal(counterTarget(20, 0.5), 10);
  assert.equal(counterTarget(20, 1), 20);
  assert.equal(counterTarget(20, 3), 20);     // never past the total
});

test("labels and speed", () => {
  assert.equal(ofWordsLabel(1204), "of 1,204 words");
  assert.equal(targetSpeed(1000, 0, true), 0);                                  // paused
  assert.equal(targetSpeed(1000, 0, false), -75);                               // drifts left
  assert.ok(Math.abs(targetSpeed(1000, 1, false) - -26.25) < 1e-9);             // hover slows to 35%
});

test("the quote is split out of its paragraph, or null if absent", () => {
  assert.deepEqual(splitAround("a b c d", "b c"), { before: "a ", match: "b c", after: " d" });
  assert.equal(splitAround("a b c d", "x"), null);
});
