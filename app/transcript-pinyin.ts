import { pinyin } from "pinyin-pro";

const HAN_CHARACTER = /\p{Script=Han}/u;
const MAX_CACHE_ENTRIES = 200;
const cache = new Map<string, string>();

export function toTranscriptPinyin(text: string): string {
  const normalized = text.trim();
  if (!normalized || !HAN_CHARACTER.test(normalized)) return "";

  const cached = cache.get(normalized);
  if (cached !== undefined) {
    cache.delete(normalized);
    cache.set(normalized, cached);
    return cached;
  }

  const value = pinyin(normalized, {
    toneType: "symbol",
    toneSandhi: true,
    type: "string",
    nonZh: "removed",
  })
    .replace(/\s+/g, " ")
    .trim();
  cache.set(normalized, value);
  if (cache.size > MAX_CACHE_ENTRIES) {
    const oldest = cache.keys().next().value;
    if (oldest !== undefined) cache.delete(oldest);
  }
  return value;
}
