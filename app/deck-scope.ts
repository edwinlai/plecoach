export type PracticeMasteryState =
  | "unassessed"
  | "learning"
  | "practicing"
  | "fluent";

export interface PracticeCard {
  categories?: readonly string[];
  mastery_state?: PracticeMasteryState;
}

export type PracticeSummary = Record<PracticeMasteryState, number>;

function normalizePath(path: string): string {
  return path.trim().replace(/^\/+|\/+$/g, "");
}

export function scopeCardsToSelection<T extends PracticeCard>(
  cards: readonly T[],
  selectedPaths: ReadonlySet<string>,
): T[] {
  const paths = Array.from(selectedPaths, normalizePath).filter(Boolean);
  if (!paths.length) return [...cards];

  return cards.filter((card) =>
    card.categories?.some((category) => {
      const normalizedCategory = normalizePath(category);
      return paths.some(
        (path) =>
          normalizedCategory === path ||
          normalizedCategory.startsWith(`${path}/`),
      );
    }),
  );
}

export function summarizeMastery(
  cards: readonly PracticeCard[],
): PracticeSummary {
  const summary: PracticeSummary = {
    unassessed: 0,
    learning: 0,
    practicing: 0,
    fluent: 0,
  };

  cards.forEach((card) => {
    summary[card.mastery_state ?? "unassessed"] += 1;
  });
  return summary;
}
