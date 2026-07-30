import assert from "node:assert/strict";
import test from "node:test";

import {
  createFreshLearnerId,
  getOrCreateLearnerId,
  LEARNER_ID_STORAGE_KEY,
} from "../app/learner-identity.ts";

function memoryStorage(initialValue = null) {
  const values = new Map();
  if (initialValue) values.set(LEARNER_ID_STORAGE_KEY, initialValue);
  return {
    getItem(key) {
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
  };
}

test("reuses the learner already assigned to this browser", () => {
  const storage = memoryStorage("learner-existing");
  let generated = false;

  const learnerId = getOrCreateLearnerId(storage, () => {
    generated = true;
    return "learner-new";
  });

  assert.equal(learnerId, "learner-existing");
  assert.equal(generated, false);
});

test("creates and stores an identity for a new browser", () => {
  const storage = memoryStorage();

  const learnerId = getOrCreateLearnerId(
    storage,
    () => "learner-first-visit",
  );

  assert.equal(learnerId, "learner-first-visit");
  assert.equal(storage.getItem(LEARNER_ID_STORAGE_KEY), "learner-first-visit");
});

test("reset replaces the current identity with a fresh learner", () => {
  const storage = memoryStorage("learner-existing");

  const learnerId = createFreshLearnerId(
    storage,
    () => "learner-fresh-start",
  );

  assert.equal(learnerId, "learner-fresh-start");
  assert.equal(storage.getItem(LEARNER_ID_STORAGE_KEY), "learner-fresh-start");
});
