import assert from "node:assert/strict";
import { test } from "node:test";
import { cueIndexAt } from "../public/shared/lyrics/js/paint.js";

const cues = [
  { start_ms: 0, end_ms: 1000 },
  { start_ms: 1000, end_ms: 2000 },
  { start_ms: 3000, end_ms: 4000 }
];

test("inside a cue returns that cue", () => {
  assert.equal(cueIndexAt(cues, 0), 0);
  assert.equal(cueIndexAt(cues, 500), 0);
  assert.equal(cueIndexAt(cues, 1500), 1);
  assert.equal(cueIndexAt(cues, 3500), 2);
});

test("before the first cue and in gaps returns the upcoming cue", () => {
  assert.equal(cueIndexAt(cues, -1), 0);
  assert.equal(cueIndexAt(cues, 2000), 2);
  assert.equal(cueIndexAt(cues, 2500), 2);
  assert.equal(cueIndexAt(cues, 3999), 2);
});

test("past the final cue returns cues.length so nothing is current or upcoming", () => {
  // Regression: the player used to pin cue N-1 as "next" forever, so the
  // three-line face ended on the second-to-last lyric.
  assert.equal(cueIndexAt(cues, 4000), cues.length);
  assert.equal(cueIndexAt(cues, 99999), cues.length);
});

test("empty document returns -1", () => {
  assert.equal(cueIndexAt([], 0), -1);
  assert.equal(cueIndexAt(null, 0), -1);
});
