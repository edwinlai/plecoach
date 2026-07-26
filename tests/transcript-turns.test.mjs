import assert from "node:assert/strict";
import test from "node:test";

import {
  groupTranscriptTurns,
  mergeTranscriptText,
} from "../app/transcript-turns.ts";

function fragment(
  identity,
  text,
  id,
  { timestamp = 1_000, trackId = "microphone" } = {},
) {
  return {
    text,
    participantInfo: { identity },
    streamInfo: {
      id: `stream-${id}`,
      timestamp,
      attributes: {
        "lk.segment_id": id,
        "lk.transcribed_track_id": trackId,
      },
    },
  };
}

test("groups adjacent speech segments into one speaker turn", () => {
  const turns = groupTranscriptTurns([
    fragment("learner", "如果我去那个城", "one"),
    fragment("learner", "旅游", "two"),
    fragment("learner", "哪个城市哪个", "three"),
    fragment("learner", "还没说", "four"),
    fragment("learner", "城市去旅游", "five"),
  ]);

  assert.equal(turns.length, 1);
  assert.equal(
    turns[0].text,
    "如果我去那个城旅游哪个城市哪个还没说城市去旅游",
  );
  assert.deepEqual(turns[0].segmentIds, [
    "one",
    "two",
    "three",
    "four",
    "five",
  ]);
});

test("speaker changes remain hard turn boundaries", () => {
  const turns = groupTranscriptTurns([
    fragment("learner", "我想去北京。", "learner-one"),
    fragment("tutor", "你想去哪里看看？", "tutor-one"),
    fragment("learner", "我想去故宫。", "learner-two"),
  ]);

  assert.deepEqual(
    turns.map((turn) => [turn.participantIdentity, turn.text]),
    [
      ["learner", "我想去北京。"],
      ["tutor", "你想去哪里看看？"],
      ["learner", "我想去故宫。"],
    ],
  );
});

test("intentional repetition across different segments is preserved", () => {
  const turns = groupTranscriptTurns([
    fragment("learner", "很好", "one"),
    fragment("learner", "很好", "two"),
    fragment("learner", "我喜欢这个城市", "three"),
    fragment("learner", "城市很漂亮", "four"),
  ]);

  assert.equal(turns[0].text, "很好很好我喜欢这个城市城市很漂亮");
});

test("revisions with the same LiveKit segment id keep only the latest text", () => {
  const turns = groupTranscriptTurns([
    fragment("learner", "我想", "same"),
    fragment("learner", "我想去北京", "same"),
  ]);

  assert.equal(turns.length, 1);
  assert.equal(turns[0].text, "我想去北京");
  assert.deepEqual(turns[0].segmentIds, ["same"]);
});

test("turn keys stay stable while live text grows", () => {
  const partial = groupTranscriptTurns([
    fragment("learner", "我想", "first"),
  ]);
  const final = groupTranscriptTurns([
    fragment("learner", "我想去北京", "first"),
    fragment("learner", "看看故宫", "second"),
  ]);

  assert.equal(partial[0].id, "learner:first");
  assert.equal(final[0].id, partial[0].id);
});

test("a learner pause does not split the turn before the tutor answers", () => {
  const turns = groupTranscriptTurns([
    fragment("learner", "你好", "one", { timestamp: 1_000 }),
    fragment("learner", "我的", "two", { timestamp: 20_000 }),
    fragment("learner", "是你的意思是什么？", "three", {
      timestamp: 40_000,
    }),
    fragment("tutor", "没关系，我们重新来。", "four", {
      timestamp: 41_000,
    }),
  ]);

  assert.equal(turns.length, 2);
  assert.equal(turns[0].text, "你好我的是你的意思是什么？");
});

test("track metadata changes do not split one uninterrupted speaker run", () => {
  const turns = groupTranscriptTurns([
    fragment("learner", "断线以前", "one", { trackId: "old-track" }),
    fragment("learner", "重新连接", "two", { trackId: "new-track" }),
  ]);

  assert.equal(turns.length, 1);
  assert.equal(turns[0].text, "断线以前重新连接");
});

test("missing timing or track metadata still groups by speaker", () => {
  const turns = groupTranscriptTurns([
    {
      text: "第一句",
      participantInfo: { identity: "learner" },
      streamInfo: { id: "one", attributes: { "lk.segment_id": "one" } },
    },
    {
      text: "第二句",
      participantInfo: { identity: "learner" },
      streamInfo: { id: "two", attributes: { "lk.segment_id": "two" } },
    },
  ]);

  assert.equal(turns.length, 1);
  assert.equal(turns[0].text, "第一句第二句");
});

test("Latin fragments receive a readable space while Mandarin does not", () => {
  assert.equal(mergeTranscriptText("good", "morning"), "good morning");
  assert.equal(mergeTranscriptText("早上", "动身"), "早上动身");
});
