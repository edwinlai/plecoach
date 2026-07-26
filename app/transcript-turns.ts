interface TranscriptStreamInfo {
  id?: string;
  attributes?: Record<string, string>;
}

export interface TranscriptFragment {
  text: string;
  participantInfo: {
    identity: string;
  };
  streamInfo?: TranscriptStreamInfo;
}

export interface TranscriptTurn {
  id: string;
  participantIdentity: string;
  text: string;
  segmentIds: string[];
}

const SEGMENT_ID_ATTRIBUTE = "lk.segment_id";

function segmentId(
  fragment: TranscriptFragment,
  fallbackIndex: number,
): string {
  return (
    fragment.streamInfo?.attributes?.[SEGMENT_ID_ATTRIBUTE] ??
    fragment.streamInfo?.id ??
    `segment-${fallbackIndex}`
  );
}

function coalesceSegmentRevisions(
  fragments: readonly TranscriptFragment[],
): Array<TranscriptFragment & { segmentId: string }> {
  const coalesced: Array<TranscriptFragment & { segmentId: string }> = [];
  const positions = new Map<string, number>();

  fragments.forEach((fragment, index) => {
    const id = segmentId(fragment, index);
    const revisionKey = `${fragment.participantInfo.identity}:${id}`;
    const existingPosition = positions.get(revisionKey);
    const withId = { ...fragment, segmentId: id };

    if (existingPosition === undefined) {
      positions.set(revisionKey, coalesced.length);
      coalesced.push(withId);
    } else {
      coalesced[existingPosition] = withId;
    }
  });

  return coalesced;
}

function boundarySeparator(left: string, right: string): string {
  const leftCharacter = left.at(-1) ?? "";
  const rightCharacter = right.at(0) ?? "";
  const latinOrNumber = /[\p{Letter}\p{Number}]/u;
  const cjk = /\p{Script=Han}/u;

  if (
    latinOrNumber.test(leftCharacter) &&
    latinOrNumber.test(rightCharacter) &&
    !cjk.test(leftCharacter) &&
    !cjk.test(rightCharacter)
  ) {
    return " ";
  }
  return "";
}

export function mergeTranscriptText(current: string, next: string): string {
  const left = current.trim();
  const right = next.trim();

  if (!left) return right;
  if (!right) return left;

  // Distinct segment IDs can contain intentional repetition or self-correction.
  // Preserve every recognized word; same-ID revisions were coalesced above.
  return `${left}${boundarySeparator(left, right)}${right}`;
}

/**
 * Present transcription segments as conversational turns. A speaker change is
 * the boundary, so the learner can pause and formulate Mandarin without every
 * finalized STT segment becoming a separate row.
 */
export function groupTranscriptTurns(
  fragments: readonly TranscriptFragment[],
): TranscriptTurn[] {
  const turns: TranscriptTurn[] = [];

  for (const fragment of coalesceSegmentRevisions(fragments)) {
    const text = fragment.text.trim();
    const participantIdentity = fragment.participantInfo.identity;
    if (!text || !participantIdentity) continue;

    const previous = turns.at(-1);
    if (previous?.participantIdentity === participantIdentity) {
      previous.text = mergeTranscriptText(previous.text, text);
      previous.segmentIds.push(fragment.segmentId);
      continue;
    }

    turns.push({
      id: `${participantIdentity}:${fragment.segmentId}`,
      participantIdentity,
      text,
      segmentIds: [fragment.segmentId],
    });
  }

  return turns;
}
