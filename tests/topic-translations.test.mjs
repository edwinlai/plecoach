import assert from "node:assert/strict";
import test from "node:test";

import { translateConversationTopic } from "../app/topic-translations.ts";

test("translates the category template and preserves the quoted folder title", () => {
  assert.equal(
    translateConversationTopic("围绕“餐厅”聊一个真实生活场景"),
    "Explore a real-life scenario around “餐厅”.",
  );
});

test("translates the target-word template and preserves its quoted words", () => {
  assert.equal(
    translateConversationTopic("用“迷路、地图、计划”聊聊你的经历"),
    "Talk about your experience using “迷路、地图、计划”.",
  );
});

test("translates the deterministic story template", () => {
  assert.equal(
    translateConversationTopic("一起编一个小故事，自然地用上今天的词"),
    "Make up a short story using today’s words naturally.",
  );
});

test("provides a clear English line for an unfamiliar topic", () => {
  assert.equal(
    translateConversationTopic("聊聊你今天最开心的事"),
    "Discuss this topic in a natural Mandarin conversation.",
  );
});
