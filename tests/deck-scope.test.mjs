import assert from "node:assert/strict";
import test from "node:test";

import {
  scopeCardsToSelection,
  summarizeMastery,
} from "../app/deck-scope.ts";

const cards = [
  {
    card_id: "a",
    categories: ["Demo/School/Class"],
    mastery_state: "learning",
  },
  {
    card_id: "b",
    categories: ["Demo/School/After class"],
    mastery_state: "fluent",
  },
  {
    card_id: "c",
    categories: ["Demo/Weekend/Park", "Demo/Review/This week"],
    mastery_state: "practicing",
  },
  {
    card_id: "d",
    categories: ["Demo/Weekend/Restaurant"],
    mastery_state: "unassessed",
  },
];

test("a selected parent folder includes all descendant cards", () => {
  const scoped = scopeCardsToSelection(cards, new Set(["Demo/School"]));

  assert.deepEqual(
    scoped.map((card) => card.card_id),
    ["a", "b"],
  );
  assert.deepEqual(summarizeMastery(scoped), {
    unassessed: 0,
    learning: 1,
    practicing: 0,
    fluent: 1,
  });
});

test("multiple selected branches form a de-duplicated union", () => {
  const scoped = scopeCardsToSelection(
    cards,
    new Set(["Demo/Weekend", "Demo/Review"]),
  );

  assert.deepEqual(
    scoped.map((card) => card.card_id),
    ["c", "d"],
  );
});

test("clearing the selection restores the whole deck", () => {
  assert.deepEqual(scopeCardsToSelection(cards, new Set()), cards);
});
