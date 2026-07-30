import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("keeps app typography at or above the 13px readability floor", async () => {
  const styles = await readFile(
    new URL("../app/globals.css", import.meta.url),
    "utf8",
  );
  const undersizedDeclarations = [
    ...styles.matchAll(/font-size:\s*([^;]+);/g),
  ]
    .filter((match) =>
      [...match[1].matchAll(/(\d+(?:\.\d+)?)px/g)].some(
        (size) => Number(size[1]) < 13,
      ),
    )
    .map((match) => match[0]);

  assert.match(styles, /--font-size-min:\s*13px;/);
  assert.match(
    styles,
    /body\s*{[^}]*font-size:\s*var\(--font-size-min\);/s,
  );
  assert.deepEqual(undersizedDeclarations, []);
});
