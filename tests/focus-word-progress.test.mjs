import assert from "node:assert/strict";
import test from "node:test";

import {
  mergeLearnerSpokenTargetIds,
  normalizeFocusWordCard,
} from "../app/focus-word-progress.ts";

test("normalizes aggregate mastery values returned by session polling", () => {
  const card = normalizeFocusWordCard({
    card_id: "map",
    simplified: "地图",
    traditional: "地圖",
    pinyin: "di4tu2",
    mastery: {
      state: "practicing",
      comprehension_score: 0.82,
      usage_score: 0.76,
    },
  });

  assert.equal(card.mastery_state, "practicing");
  assert.equal(card.comprehension, 0.82);
  assert.equal(card.independent_usage, 0.76);
});

test("spoken target IDs remain checked across stale or empty polling results", () => {
  const known = new Set(["map", "lost"]);
  const afterRealtimeEvent = mergeLearnerSpokenTargetIds(
    new Set(),
    ["map"],
    known,
  );
  const afterStalePoll = mergeLearnerSpokenTargetIds(
    afterRealtimeEvent,
    [],
    known,
  );

  assert.deepEqual([...afterStalePoll], ["map"]);
  assert.equal(afterStalePoll, afterRealtimeEvent);
});

test("polling and realtime IDs form a de-duplicated monotonic union", () => {
  const known = new Set(["map", "lost"]);
  const first = mergeLearnerSpokenTargetIds(
    new Set(),
    ["map", "unknown", "map"],
    known,
  );
  const second = mergeLearnerSpokenTargetIds(
    first,
    ["lost", "map"],
    known,
  );

  assert.deepEqual([...second], ["map", "lost"]);
});

test("malformed progress payloads cannot clear current spoken words", () => {
  const current = new Set(["map"]);

  assert.equal(
    mergeLearnerSpokenTargetIds(current, null, new Set(["map"])),
    current,
  );
  assert.equal(
    mergeLearnerSpokenTargetIds(current, { card_ids: [] }, new Set(["map"])),
    current,
  );
});
