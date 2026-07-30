import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("live session is transcript-first and no longer renders the tutor orb", async () => {
  const source = await readFile(
    new URL("../app/VoiceSession.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /<main className="transcript-panel">/);
  assert.match(source, /className="transcript-list"[\s\S]*aria-live="polite"/);
  assert.match(
    source,
    /className="transcript-hanzi"[\s\S]*<TranscriptPinyin[\s\S]*text=\{turn\.text\}/,
  );
  assert.doesNotMatch(source, /tutor-orb|orb-character|orb-ring/);
});

test("streaming transcript keeps a stable pinyin line without smooth-scroll bounce", async () => {
  const source = await readFile(
    new URL("../app/VoiceSession.tsx", import.meta.url),
    "utf8",
  );
  const styles = await readFile(
    new URL("../app/globals.css", import.meta.url),
    "utf8",
  );
  const transcriptListStyles =
    styles.match(/\.transcript-list\s*\{([^}]*)\}/)?.[1] ?? "";
  const transcriptPinyinStyles =
    styles.match(/\.transcript-pinyin\s*\{([^}]*)\}/)?.[1] ?? "";

  assert.doesNotMatch(source, /new MutationObserver|scrollIntoView/);
  assert.doesNotMatch(source, /behavior:\s*["']smooth["']/);
  assert.match(source, /useLayoutEffect\(\(\) => \{[\s\S]*stickTranscriptToBottom/);
  assert.match(source, /\{value \|\| "\\u00a0"\}/);
  assert.match(transcriptPinyinStyles, /display:\s*block/);
  assert.match(transcriptPinyinStyles, /min-height:\s*1\.5em/);
  assert.match(transcriptListStyles, /overflow-anchor:\s*none/);
  assert.doesNotMatch(transcriptListStyles, /scroll-behavior:\s*smooth/);
  assert.match(styles, /\.transcript-hanzi\s*\{/);
});

test("focus-word checks use monotonic learner-spoken session progress", async () => {
  const source = await readFile(
    new URL("../app/VoiceSession.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /payload\.type === "learner_spoken_targets"/);
  assert.match(source, /payload\.learner_spoken_target_card_ids/);
  assert.match(
    source,
    /const active = learnerSpokenTargetIds\.has\(card\.card_id\)/,
  );
  assert.match(
    source,
    /cards\.filter\(\(card\) => learnerSpokenTargetIds\.has\(card\.card_id\)\)/,
  );
  assert.doesNotMatch(
    source,
    /const active =[\s\S]{0,220}card\.mastery_state === "practicing"/,
  );
});
