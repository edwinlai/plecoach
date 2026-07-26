import assert from "node:assert/strict";
import test from "node:test";

import { toTranscriptPinyin } from "../app/transcript-pinyin.ts";

test("adds tone-marked pinyin for Mandarin transcript text", () => {
  assert.equal(
    toTranscriptPinyin("你好！我想去北京。"),
    "nǐ hǎo wǒ xiǎng qù běi jīng",
  );
});

test("uses phrase context for common polyphonic characters", () => {
  assert.equal(toTranscriptPinyin("银行"), "yín háng");
});

test("applies spoken tone sandhi", () => {
  assert.equal(toTranscriptPinyin("一起去，不是。"), "yì qǐ qù bú shì");
});

test("omits non-Mandarin fragments from the supporting pinyin line", () => {
  assert.equal(
    toTranscriptPinyin("LiveKit 你好 2026"),
    "nǐ hǎo",
  );
  assert.equal(toTranscriptPinyin("LiveKit 2026"), "");
  assert.equal(toTranscriptPinyin("   "), "");
});
