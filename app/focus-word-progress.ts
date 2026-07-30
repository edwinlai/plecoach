export type FocusWordMasteryState =
  | "unassessed"
  | "learning"
  | "practicing"
  | "fluent";

export interface FocusWordCard {
  card_id: string;
  simplified: string;
  traditional?: string;
  pinyin: string;
  definition?: string;
  categories?: string[];
  mastery_state?: FocusWordMasteryState;
  comprehension?: number;
  independent_usage?: number;
}

const masteryStates = new Set<FocusWordMasteryState>([
  "unassessed",
  "learning",
  "practicing",
  "fluent",
]);

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value
    ? (value as Record<string, unknown>)
    : {};
}

function optionalNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : undefined;
}

export function normalizeFocusWordCard(
  value: FocusWordCard | Record<string, unknown>,
): FocusWordCard {
  const raw = asRecord(value);
  const mastery = asRecord(raw.mastery);
  const rawState = raw.mastery_state ?? mastery.state ?? "unassessed";
  const masteryState = masteryStates.has(rawState as FocusWordMasteryState)
    ? (rawState as FocusWordMasteryState)
    : "unassessed";

  return {
    card_id: String(raw.card_id ?? raw.id ?? ""),
    simplified: String(raw.simplified ?? raw.headword ?? ""),
    traditional:
      typeof raw.traditional === "string" && raw.traditional
        ? raw.traditional
        : undefined,
    pinyin: String(raw.pinyin ?? raw.pronunciation ?? ""),
    definition:
      typeof raw.definition === "string" && raw.definition
        ? raw.definition
        : undefined,
    categories: Array.isArray(raw.categories)
      ? raw.categories.map(String)
      : undefined,
    mastery_state: masteryState,
    comprehension:
      optionalNumber(raw.comprehension) ??
      optionalNumber(mastery.comprehension_score),
    independent_usage:
      optionalNumber(raw.independent_usage) ??
      optionalNumber(mastery.usage_score),
  };
}

export function mergeLearnerSpokenTargetIds(
  current: ReadonlySet<string>,
  incoming: unknown,
  knownTargetIds: ReadonlySet<string>,
): ReadonlySet<string> {
  if (!Array.isArray(incoming)) return current;

  let next: Set<string> | null = null;
  for (const value of incoming) {
    if (typeof value !== "string") continue;
    const cardId = value.trim();
    if (!knownTargetIds.has(cardId) || current.has(cardId)) continue;
    next ??= new Set(current);
    next.add(cardId);
  }
  return next ?? current;
}
