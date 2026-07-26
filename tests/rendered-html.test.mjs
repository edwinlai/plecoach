import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the Plecoach learner experience", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Plecoach — 把词汇说出来<\/title>/i);
  assert.match(html, /Plecoach/);
  assert.doesNotMatch(html, /codex-preview/i);
  assert.doesNotMatch(html, /Your site is taking shape/i);
  assert.doesNotMatch(html, /react-loading-skeleton/i);
  assert.doesNotMatch(html, /\/Users\/|\/app\/\.vinext|\.vinext\/fonts/i);
});

test("ships the evaluator sample deck as a static asset", async () => {
  const sample = new URL("../public/samples/pleco-demo.xml", import.meta.url);
  const { readFile } = await import("node:fs/promises");
  const xml = await readFile(sample, "utf8");
  assert.match(xml, /<plecoflash\b/);
  assert.match(xml, /<cards>/);
  assert.ok((xml.match(/<card\b/g) ?? []).length >= 20);
});
