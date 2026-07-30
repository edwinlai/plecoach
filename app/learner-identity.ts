export const LEARNER_ID_STORAGE_KEY = "plecoach-learner-id";

export interface LearnerIdStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

type RequestFunction = (
  input: string,
  init: { method: "DELETE" },
) => Promise<Response>;

export function getOrCreateLearnerId(
  storage: LearnerIdStorage,
  generateId: () => string,
) {
  const existing = storage.getItem(LEARNER_ID_STORAGE_KEY);
  if (existing) return existing;

  const learnerId = generateId();
  storage.setItem(LEARNER_ID_STORAGE_KEY, learnerId);
  return learnerId;
}

export function createFreshLearnerId(
  storage: LearnerIdStorage,
  generateId: () => string,
) {
  const learnerId = generateId();
  storage.setItem(LEARNER_ID_STORAGE_KEY, learnerId);
  return learnerId;
}

export async function deleteLearnerData(
  apiBase: string,
  learnerId: string,
  request: RequestFunction = fetch,
) {
  const response = await request(
    `${apiBase}/api/learners/${encodeURIComponent(learnerId)}`,
    { method: "DELETE" },
  );
  if (response.ok) return;

  const payload = (await response.json().catch(() => ({}))) as {
    detail?: unknown;
  };
  const detail =
    typeof payload.detail === "string"
      ? payload.detail
      : "Plecoach couldn’t delete the current learner data.";
  throw new Error(detail);
}

export async function resetLearnerIdentity({
  apiBase,
  learnerId,
  storage,
  generateId,
  request = fetch,
}: {
  apiBase: string;
  learnerId: string;
  storage: LearnerIdStorage;
  generateId: () => string;
  request?: RequestFunction;
}) {
  await deleteLearnerData(apiBase, learnerId, request);
  return createFreshLearnerId(storage, generateId);
}
