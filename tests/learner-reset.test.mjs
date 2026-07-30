import assert from "node:assert/strict";
import test from "node:test";

import {
  deleteLearnerData,
  resetLearnerIdentity,
} from "../app/learner-identity.ts";

test("deletes the current learner through the API", async () => {
  let requestUrl = "";
  let requestInit = null;

  await deleteLearnerData(
    "http://localhost:8000",
    "learner-current",
    async (url, init) => {
      requestUrl = url;
      requestInit = init;
      return new Response(null, { status: 204 });
    },
  );

  assert.equal(
    requestUrl,
    "http://localhost:8000/api/learners/learner-current",
  );
  assert.deepEqual(requestInit, { method: "DELETE" });
});

test("rotates identity only after Redis cleanup succeeds", async () => {
  let cleanupCompleted = false;
  let storedLearnerId = "learner-current";

  const learnerId = await resetLearnerIdentity({
    apiBase: "http://localhost:8000",
    learnerId: "learner-current",
    storage: {
      getItem() {
        return storedLearnerId;
      },
      setItem(_key, value) {
        storedLearnerId = value;
      },
    },
    generateId() {
      assert.equal(cleanupCompleted, true);
      return "learner-fresh";
    },
    async request() {
      cleanupCompleted = true;
      return new Response(null, { status: 204 });
    },
  });

  assert.equal(learnerId, "learner-fresh");
  assert.equal(storedLearnerId, "learner-fresh");
});

test("keeps the current identity when Redis cleanup fails", async () => {
  let storedLearnerId = "learner-current";
  let generated = false;

  await assert.rejects(
    resetLearnerIdentity({
      apiBase: "http://localhost:8000",
      learnerId: "learner-current",
      storage: {
        getItem() {
          return storedLearnerId;
        },
        setItem(_key, value) {
          storedLearnerId = value;
        },
      },
      generateId() {
        generated = true;
        return "learner-fresh";
      },
      request: async () =>
        Response.json(
          { detail: "Redis is unavailable." },
          { status: 503 },
        ),
    }),
    /Redis is unavailable/,
  );

  assert.equal(storedLearnerId, "learner-current");
  assert.equal(generated, false);
});
