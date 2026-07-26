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
    /className="transcript-hanzi"[\s\S]*<TranscriptPinyin text=\{turn\.text\}/,
  );
  assert.doesNotMatch(source, /tutor-orb|orb-character|orb-ring/);
});

test("pinyin is styled as a supporting line beneath the Hanzi", async () => {
  const styles = await readFile(
    new URL("../app/globals.css", import.meta.url),
    "utf8",
  );

  assert.match(styles, /\.transcript-pinyin\s*\{[\s\S]*display:\s*block/);
  assert.match(styles, /\.transcript-hanzi\s*\{/);
});
